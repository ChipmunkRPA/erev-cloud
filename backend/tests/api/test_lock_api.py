"""API-R-18 lock routes (BUILD_SPEC CLO-6 ``test_lock_api.py``): ``request-lock`` refuses with
ERR-14 naming each failing gate (BS4-D-08; J-13-AC-1) and ``GET /periods/{id}/locks`` lists the
T-CLS-04 rows. DB-bound; NOT RUN on the authoring worktree (databases not provisioned). Corrected
for Codex CLO6-R3 (3) and (8): the listed lock is written by the lock's own writer with valid
parents in the D-98 61 order, and the gate-failure case is the exact two-blocker world.

Item CLO-LOCKS-READ-1 (04 §16.8 API-S-PeriodLock and the transitions list, rev 1.207): a record
of the list states what it certified and froze — its gate results, its ledger head hash, the
datasets and the number of its request — witnessed on a lock and a reopen decided through the
product.

Item CLO-LOCK-REQUEST-OWN-GATE-1 (04 §16.8 ``blockers`` rev 1.311; PRD BR-CLS-01 rev 1.205): the
period's own lock request is no pending approval of its period — the cockpit between "Submit for
lock" and the Controller's decision, read through the product; another pending request of the
entity holds the lock as before.

Item CLO-APPROVALS-WAIVER-OWN-REQUEST-1 (04 §16.8 ``blockers`` rev 1.318; PRD BR-CLS-01 rev 1.206):
the request that asks to waive the approvals gate is no pending approval of its period — the
waiver is approved after a read of the cockpit; and, with item CLO-WAIVER-COVERS-LATER-1, a waived
approvals gate is not outgrown by the period's own lock request."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import (
    approval_request,
    audit_event,
    close_checklist_item,
    close_checklist_template,
    exception_item,
    ledger_chain_head,
    legal_entity,
    lock_snapshot,
    period_lock,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.enums import ApprovalRequestStatus, LockKind, PeriodState, SnapshotKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, insert, select
from support import worlds
from support.close_world import (
    CloseWorld,
    acknowledged_run,
    actor_with_role,
    close_run_succeeded,
    close_world,
    earlier_periods_closed,
    reviewed_error_judgement,
    reviewed_reconciliations,
    system_session,
)
from support.db import TestDatabase
from support.principals import colleague
from support.reference import (
    PERIODS,
    approve,
    assign,
    entity,
    get,
    holding,
    periods,
    post,
    slug,
)
from support.rows import approval_request_values, exception_item_values

COMMENT = "September 2026 close complete"
APPROVALS = "/api/v1/approvals"
WAIVER_REASON = "Accepted by the controller for this period."
REOPEN_COMMENT = "A September invoice was recorded after the lock."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _september(world: CloseWorld) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P09"
    ]
    return found


def _start_close(world: CloseWorld) -> str:
    """Soft-close September through the API; returns the ETag of the ``closing`` state. January
    to August are closed first (PRD WLD-P-02; BR-CLS-08, supervisor ruling R-6: a period is
    submitted for lock only when no earlier period is postable)."""
    earlier_periods_closed(world)
    shown = _september(world)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    return str(started.headers["ETag"])


def test_request_lock_gates_failed(world: CloseWorld) -> None:
    """BUILD_SPEC CLO-6 / J-13-AC-1: exactly APPROVALS_CLEARED and RECONCILIATIONS_GENERATED fail —
    an acknowledged, balanced journal run makes the journal gates pass, a succeeded close run the
    close-run gate (fixture state for the gate; supervisor ruling R-114 (b)), one PENDING approval
    of the entity remains and no reconciliation exists. ``JE_COMPLETE`` carries the real CLO-10
    signal (PASSED 0: the acknowledged run covers a period without sealed activity), so the exact
    detail below is the finished path's (F-CLO record §20 (6), (8); until CLO-10 the gate also
    failed "not evaluated" on main — batch #4 / #5)."""
    etag = _start_close(world)
    shown = _september(world)
    with system_session(world) as session:
        acknowledged_run(session, world, world.period_id)
        close_run_succeeded(session, world, world.period_id)
        session.execute(
            insert(approval_request).values(
                **approval_request_values(
                    world.tenant_id,
                    entity_id=world.entity_id,
                    preparer_id=world.maya.member.user_id,
                    subject_type="CONTRACT_ACTIVATION",
                    subject_id=new_id(),
                    summary="Activate BG-AVM-0020",
                )
            )
        )
    refused = post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-lock",
        world.maya,
        {"certification_comment": COMMENT},
        if_match=etag,
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    body = refused.json()
    assert [error["rule_id"] for error in body["errors"]] == [
        "APPROVALS_CLEARED",
        "RECONCILIATIONS_GENERATED",
    ]
    assert body["detail"] == (
        "2 close gates have not passed: No pending approvals, "
        "Reconciliations generated and reviewed."
    )


# --- the lock request and its own period's gate (item CLO-LOCK-REQUEST-OWN-GATE-1) ---------------

APPROVALS_GATE = "APPROVALS_CLEARED"
CLEARED = ("PASSED", "WAIVED", "NOT_APPLICABLE")


def _ready_for_lock(world: CloseWorld) -> None:
    """September in soft close with every automatic gate passed: an acknowledged run, reviewed
    reconciliations and a succeeded close run (the fixture state of each gate)."""
    _start_close(world)
    with system_session(world) as session:
        acknowledged_run(session, world, world.period_id)
        reviewed_reconciliations(session, world, world.period_id)
        close_run_succeeded(session, world, world.period_id)


def _submitted_for_lock(world: CloseWorld) -> str:
    """Maya's "Submit for lock" of September; the id of the ``PERIOD_LOCK`` request."""
    shown = _september(world)
    asked = post(
        world.app,
        f"{PERIODS}/{world.state_id}/request-lock",
        world.maya,
        {"certification_comment": COMMENT},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert asked.status_code == 200, asked.text
    return str(asked.json()["approval_request_id"])


def _cockpit_reads(
    world: CloseWorld, actor: Any
) -> tuple[int, tuple[str, int, str | None], list[str]]:
    """What a reader of September's cockpit is told about pending approvals: the period's count,
    the gate's (status, count, detail), and the gates the screen calls failing — blocking, not
    cleared and not the certification, the guard of "Lock period" (``failingGates``)."""
    shown = get(world.app, f"{PERIODS}/{world.state_id}/cockpit", actor)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    (gate,) = [item for item in body["checklist"] if item["code"] == APPROVALS_GATE]
    failing = [
        item["code"]
        for item in body["checklist"]
        if item["is_blocking"]
        and item["status"] not in CLEARED
        and item["code"] != gates.CONTROLLER_CERTIFIED
    ]
    return (
        int(body["period"]["blockers"]["approvals_pending"]),
        (gate["status"], gate["result"]["count"], gate["result"]["detail"]),
        failing,
    )


def _approvals_item(
    world: CloseWorld,
) -> tuple[tuple[str, int | None, str | None], list[tuple[str, str | None, str | None]]]:
    """The stored row of September's ``APPROVALS_CLEARED`` item — (status, count, detail) — and
    its audit trail in order: (action, the status before, the status after)."""
    item, template = close_checklist_item, close_checklist_template
    with system_session(world) as session:
        row = session.execute(
            select(item.c.id, item.c.status, item.c.result)
            .join(
                template,
                and_(
                    template.c.tenant_id == item.c.tenant_id,
                    template.c.id == item.c.close_checklist_template_id,
                ),
            )
            .where(
                item.c.entity_id == world.entity_id,
                item.c.period_id == world.period_id,
                template.c.gate_check_code == APPROVALS_GATE,
            )
        ).one()
        events = session.execute(
            select(audit_event.c.action, audit_event.c.before, audit_event.c.after)
            .where(
                audit_event.c.object_type == gates.OBJECT_TYPE, audit_event.c.object_id == row.id
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    result = row.result or {}
    return (
        (str(getattr(row.status, "value", row.status)), result.get("count"), result.get("detail")),
        [
            (str(action), (before or {}).get("status"), (after or {}).get("status"))
            for action, before, after in events
        ],
    )


def test_the_lock_request_holds_no_gate_of_its_own_period(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Item CLO-LOCK-REQUEST-OWN-GATE-1 (04 §16.8 ``blockers`` rev 1.311; PRD BR-CLS-01 rev 1.205;
    J-13.13 and J-13.14; lane WEB-QA's row C-10). Maya submits September for lock; Marcus, the
    Controller, opens the cockpit before he decides. The request is no pending approval of its
    own period: the period's blockers count none, ``APPROVALS_CLEARED`` reads ``PASSED`` with
    count 0 — as it did when the request was made — and no blocking gate but the certification
    is left, which is what the screen asks before it takes "Lock period". The period read says
    the same; the request itself is still ``PENDING`` for its approver. The read stores nothing.
    Marcus decides: the period is ``closed``, the lock certifies the gate ``PASSED`` 0, and the
    item's audit trail holds no ``FAILED`` — it holds nothing: reads created and evaluated the
    item, and no command changed it.

    Fail-first (measured on 9ec07ed02): the Controller's cockpit read ``approvals_pending`` 1 and
    the gate ``FAILED`` "Pending approvals: 1" — the lock request itself — so the screen called
    the lock unavailable; the read stored that without an audit event, and the decision's own
    evaluation, its request ``APPROVED`` by then, wrote the item's one audit event: ``FAILED`` to
    ``PASSED``."""
    app = world.app
    _ready_for_lock(world)
    asked = (0, ("PASSED", 0, None), [])
    assert _cockpit_reads(world, world.maya) == asked
    request_id = _submitted_for_lock(world)
    marcus = actor_with_role(app, clock, world.tenant_id, "controller", name="marcus")

    assert _cockpit_reads(world, marcus) == asked
    period = get(app, f"{PERIODS}/{world.state_id}", marcus)
    assert period.status_code == 200, period.text
    assert (period.json()["state"], period.json()["blockers"]["approvals_pending"]) == (
        PeriodState.CLOSING.value,
        0,
    )
    waiting = get(app, f"{APPROVALS}/{request_id}", marcus)
    assert (waiting.status_code, waiting.json()["status"]) == (200, "PENDING"), waiting.text
    assert _approvals_item(world) == (("PASSED", 0, None), [])

    decided = approve(app, request_id, marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _september(world)["state"] == PeriodState.CLOSED.value
    assert _approvals_item(world) == (("PASSED", 0, None), [])
    with system_session(world) as session:
        (certification,) = session.execute(
            select(period_lock.c.certification).where(period_lock.c.period_id == world.period_id)
        ).scalars()
    (certified,) = [row for row in certification if row["gate_check_code"] == APPROVALS_GATE]
    assert (certified["status"], certified["count"]) == ("PASSED", 0)
    assert _cockpit_reads(world, marcus) == asked


def test_another_pending_request_holds_the_lock_after_the_submission(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Item CLO-LOCK-REQUEST-OWN-GATE-1: the request the count leaves out is the period's own
    lock request and no other. September is submitted without a read of its cockpit before: the
    item's trail is the request's evaluation — created, then ``PASSED``. Then another request
    of the entity waits (a row, as in ``test_request_lock_gates_failed``): the cockpit counts 1,
    the gate fails "Pending approvals: 1" and is the one gate the screen calls failing, and
    Marcus's decision is refused 409 ``close-gates-failed`` naming it — the lock request stays
    ``PENDING`` and the period in soft close (PRD BR-CLS-01; the decision evaluates the gates
    again)."""
    app = world.app
    _ready_for_lock(world)
    request_id = _submitted_for_lock(world)
    requested = [
        ("close_checklist_item.create", None, "NOT_STARTED"),
        ("close_checklist_item.evaluate", "NOT_STARTED", "PASSED"),
    ]
    assert _approvals_item(world) == (("PASSED", 0, None), requested)
    marcus = actor_with_role(app, clock, world.tenant_id, "controller", name="marcus")
    assert _cockpit_reads(world, marcus) == (0, ("PASSED", 0, None), [])

    with system_session(world) as session:
        session.execute(
            insert(approval_request).values(
                **approval_request_values(
                    world.tenant_id,
                    entity_id=world.entity_id,
                    preparer_id=world.maya.member.user_id,
                    subject_type="CONTRACT_ACTIVATION",
                    subject_id=new_id(),
                    summary="Activate BG-AVM-0020",
                )
            )
        )
    assert _cockpit_reads(world, marcus) == (
        1,
        ("FAILED", 1, "Pending approvals: 1"),
        [APPROVALS_GATE],
    )
    refused = approve(app, request_id, marcus)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert [error["rule_id"] for error in refused.json()["errors"]] == [APPROVALS_GATE]
    waiting = get(app, f"{APPROVALS}/{request_id}", marcus)
    assert (waiting.status_code, waiting.json()["status"]) == (200, "PENDING"), waiting.text
    assert _september(world)["state"] == PeriodState.CLOSING.value


# --- the waiver of the approvals gate (items CLO-LOCK-REQUEST-OWN-GATE-1 with ---------------------
# --- CLO-WAIVER-COVERS-LATER-1, and CLO-APPROVALS-WAIVER-OWN-REQUEST-1) ---------------------------

ONE_OTHER = (1, ("FAILED", 1, "Pending approvals: 1"), [APPROVALS_GATE])
WAIVED_AT_ONE = (1, ("WAIVED", 1, "Pending approvals: 1"), [])


def _another_request_waits(world: CloseWorld) -> None:
    """One other request of the entity is pending (a row, as in
    ``test_request_lock_gates_failed``): the count the waiver is asked for."""
    with system_session(world) as session:
        session.execute(
            insert(approval_request).values(
                **approval_request_values(
                    world.tenant_id,
                    entity_id=world.entity_id,
                    preparer_id=world.maya.member.user_id,
                    subject_type="CONTRACT_ACTIVATION",
                    subject_id=new_id(),
                    summary="Activate BG-AVM-0020",
                )
            )
        )


def _approvals_waiver_asked(world: CloseWorld) -> str:
    """Maya asks for the waiver of September's ``APPROVALS_CLEARED`` gate, by the item's id from
    the read she already made; the id of the ``EXCEPTION_WAIVER`` request."""
    item, template = close_checklist_item, close_checklist_template
    with system_session(world) as session:
        item_id = session.execute(
            select(item.c.id)
            .join(
                template,
                and_(
                    template.c.tenant_id == item.c.tenant_id,
                    template.c.id == item.c.close_checklist_template_id,
                ),
            )
            .where(
                item.c.entity_id == world.entity_id,
                item.c.period_id == world.period_id,
                template.c.gate_check_code == APPROVALS_GATE,
            )
        ).scalar_one()
    shown = _september(world)
    asked = post(
        world.app,
        f"{PERIODS}/{world.state_id}/checklist/{item_id}/waive",
        world.maya,
        {"reason": WAIVER_REASON},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert asked.status_code == 200, asked.text
    return str(asked.json()["approval_request_id"])


def _locked_over_the_waiver(world: CloseWorld, clock: FrozenClock, waiver_id: str) -> None:
    """Maya submits September for lock over the waived gate; Marcus opens the cockpit, which
    counts the one other request and calls no gate failing, and decides: the period is closed
    and the lock certifies the gate ``WAIVED`` — count 1, the waiver's count 1, its request."""
    request_id = _submitted_for_lock(world)
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    assert _cockpit_reads(world, marcus) == WAIVED_AT_ONE
    decided = approve(world.app, request_id, marcus)
    assert (decided.status_code, decided.json().get("status")) == (200, "APPROVED"), decided.text
    assert _september(world)["state"] == PeriodState.CLOSED.value
    with system_session(world) as session:
        (certification,) = session.execute(
            select(period_lock.c.certification).where(period_lock.c.period_id == world.period_id)
        ).scalars()
    (certified,) = [row for row in certification if row["gate_check_code"] == APPROVALS_GATE]
    assert (
        certified["status"],
        certified["count"],
        certified["waived_count"],
        certified["waiver_approval_request_id"],
    ) == ("WAIVED", 1, 1, waiver_id)


def test_a_waived_approvals_gate_is_not_outgrown_by_the_periods_own_lock_request(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Items CLO-LOCK-REQUEST-OWN-GATE-1 and CLO-WAIVER-COVERS-LATER-1 together (04 T-CLS-03 rev
    1.305 and 1.311; the witness on the joined base, test only). One other request of the entity
    waits; the gate is waived for it at count 1 — nobody reads the cockpit while the waiver
    waits — and September is submitted for lock. The lock request is no pending approval of its
    own period, so the Controller's cockpit still counts 1: the waiver covers it, the screen
    calls no gate failing, the decision locks, and the lock certifies ``WAIVED`` with count 1 and
    the waiver's count 1.

    Fail-first (measured on 46d47e06, index 283 without 296): the Controller's cockpit counted
    2 — the lock request itself — and the read stored the waiver's lapse, ``FAILED`` "Pending
    approvals: 2 The waiver <request no> covered 1."; the screen called the lock unavailable AND
    the decision was refused 409: the period could not be locked from either page."""
    app = world.app
    _ready_for_lock(world)
    _another_request_waits(world)
    assert _cockpit_reads(world, world.maya) == ONE_OTHER
    waiver_id = _approvals_waiver_asked(world)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    waived = approve(app, waiver_id, priya)
    assert (waived.status_code, waived.json().get("status")) == (200, "APPROVED"), waived.text
    assert _cockpit_reads(world, world.maya) == WAIVED_AT_ONE
    _locked_over_the_waiver(world, clock, waiver_id)


def test_the_waiver_of_the_approvals_gate_is_no_pending_approval_of_its_period(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Item CLO-APPROVALS-WAIVER-OWN-REQUEST-1 (04 §16.8 ``blockers`` rev 1.318; PRD BR-CLS-01
    rev 1.206). One other request of the entity waits and Maya asks for the waiver of the
    approvals gate. The request that asks to waive the count is no part of the count: whoever
    reads the cockpit while the waiver waits is told 1, "Pending approvals: 1" — what the
    request states — and Priya's approval is taken. The item is ``WAIVED`` at the count of the
    other request, and the period locks over it as it does when nobody had looked.

    Fail-first (measured on 6e04bc69d): the read while the waiver waited counted 2 — the
    waiver's own request — and stored "Pending approvals: 2"; a waiver's request states the
    count it asks to waive (rev 1.305), so the approval answered 409 ``stale-approval`` and the
    request was voided: a waiver the product offers that nobody could approve once anybody had
    opened the cockpit."""
    app = world.app
    _ready_for_lock(world)
    _another_request_waits(world)
    assert _cockpit_reads(world, world.maya) == ONE_OTHER
    waiver_id = _approvals_waiver_asked(world)
    while_it_waits = _cockpit_reads(world, world.maya)
    period = get(app, f"{PERIODS}/{world.state_id}", world.maya)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    waived = approve(app, waiver_id, priya)
    assert (waived.status_code, waived.json().get("status")) == (200, "APPROVED"), waived.text
    assert while_it_waits == ONE_OTHER
    assert period.json()["blockers"]["approvals_pending"] == 1
    assert _cockpit_reads(world, world.maya) == WAIVED_AT_ONE
    _locked_over_the_waiver(world, clock, waiver_id)


def test_locks_list(world: CloseWorld) -> None:
    """``GET /periods/{id}/locks`` returns the T-CLS-04 row as the lock stored it. The fixture is
    the lock's own writer (``_persist_lock``, D-98 61): an APPROVED ``PERIOD_LOCK`` request of the
    entity, the ``period_lock`` row first (its transition edge is the 0047 deferred key), then the
    transition row that names both — the CHECKs of T-REF-07 need both references for ``closed``."""
    _start_close(world)
    lock_id, transition_id = new_id(), new_id()
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id, lock=True)
        assert scope is not None and scope.state == PeriodState.CLOSING.value
        request = approval_request_values(
            world.tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            entity_id=world.entity_id,
            subject_type="PERIOD_LOCK",
            subject_id=world.state_id,
            summary="Lock FY2026-P09 for AVM-US in book ASC606",
        )
        uow.session.execute(insert(approval_request).values(**request))
        close_commands._persist_lock(
            uow,
            scope,
            kind=LockKind.LOCK,
            lock_id=lock_id,
            transition_id=transition_id,
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=close_commands.LOCK_ACTION,
            approval_request_id=UUID(str(request["id"])),
            comment=COMMENT,
            certification=[],
            snapshot_manifest_sha256=None,
            heads=close_commands._heads(uow.session, scope),
            cutoff_known_at=uow.now,  # 04 T-CLS-04 rev 1.113 (R-40 (c)): a LOCK names its cutoff
        )
        uow.commit()
    with system_session(world) as session:
        stored = (
            session.execute(select(period_lock).where(period_lock.c.id == lock_id)).mappings().one()
        )
    listed = get(world.app, f"{PERIODS}/{world.state_id}/locks", world.maya)
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    assert (item["id"], item["kind"], item["approval_request_id"]) == (
        str(lock_id),
        "LOCK",
        str(request["id"]),
    )
    assert (item["ledger_head_chain_seq"], item["audit_head_chain_seq"]) == (
        int(stored["ledger_head_chain_seq"]),
        int(stored["audit_head_chain_seq"]),
    )
    assert (item["snapshot_manifest_sha256"], item["previous_lock_id"]) == (None, None)
    assert item["comment"] == COMMENT
    # 04 §16.8 API-S-PeriodLock rev 1.140 (supervisor ruling R-94 (d)): the lock's freeze cutoff is
    # a read member — here the instant the fixture's writer stated, the frozen application clock
    assert stored["cutoff_known_at"] is not None
    assert datetime.fromisoformat(item["cutoff_known_at"]) == stored["cutoff_known_at"]
    assert item["cutoff_known_at"] == "2026-09-12T12:00:00Z"
    # The API row (BUILD_SPEC CLO-6 acceptance; ``PeriodLockRowOut``) carries the lock's own
    # columns, not the T-REF-07 link; that link is the table fact asserted on ``stored``.
    assert str(stored["period_state_transition_id"]) == str(transition_id)
    # rev 1.207 (item CLO-LOCKS-READ-1): what the record certified and froze — nothing, for this
    # writer's row — its head hash and its request's number; the keyed audit head is not stated
    assert (item["certification"], item["snapshots"]) == ([], [])
    assert item["ledger_head_sha256"] == stored["ledger_head_sha256"]
    assert item["approval_request_no"] == request["request_no"]
    assert "audit_head_hmac" not in item


def _request_no(world: CloseWorld, request_id: str) -> str:
    with system_session(world) as session:
        return str(
            session.execute(
                select(approval_request.c.request_no).where(
                    approval_request.c.id == UUID(request_id)
                )
            ).scalar_one()
        )


def test_locks_list_states_what_each_record_certified_and_froze(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Item CLO-LOCKS-READ-1 (04 §16.8 API-S-PeriodLock, rev 1.207). September is locked through
    the product with one gate waived — an open exception, its waiver approved by another person —
    and then reopened by two approvals. The list states, newest first:

    - the ``REOPEN`` record: no gate result and no dataset, the lock it reopens, its reason and
      the number of its request;
    - the ``LOCK`` record: the fourteen gate results as stored, in T-CLS-02 order — thirteen
      ``PASSED`` and ``EXCEPTIONS_CLEARED`` ``WAIVED`` with both counts, the waiver request and
      that request's number; the twelve datasets in E-64 order with the row count and file hash
      of each T-CLS-05 row, and no file id or control totals; the stored ledger head hash; the
      number of the lock request, the one ``GET /approvals/{id}`` shows its approver.

    No record states ``audit_head_hmac``. The transitions name the request numbers of the two
    decisions and none for the soft close. A viewer whose role names AVM-US alone, in a workspace
    of two entities, reads both lists as the tenant-wide accountant does; a viewer of the other
    entity reads neither (404)."""
    app, maya, tenant_id = world.app, world.maya, world.tenant_id
    state_id = str(world.state_id)
    _start_close(world)
    with system_session(world) as session:
        acknowledged_run(session, world, world.period_id)
        reviewed_reconciliations(session, world, world.period_id)
        close_run_succeeded(session, world, world.period_id)
        session.execute(
            insert(exception_item).values(
                **exception_item_values(tenant_id, entity_id=world.entity_id)
            )
        )
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        ).scalar_one()
    uk = UUID(str(entity(app, maya, code="AVM-UK", calendar_id=str(calendar_id))["id"]))

    def command(name: str, actor: Any, body: dict[str, Any]) -> Any:
        shown = _september(world)
        return post(
            app,
            f"{PERIODS}/{state_id}/{name}",
            actor,
            body,
            if_match=f'"r{shown["row_version"]}"',
        )

    # the waiver of the exceptions gate: Maya asks, Priya (exception.waive) approves
    cockpit = get(app, f"{PERIODS}/{state_id}/cockpit", maya)
    assert cockpit.status_code == 200, cockpit.text
    (gate,) = [item for item in cockpit.json()["checklist"] if item["code"] == "EXCEPTIONS_CLEARED"]
    assert (gate["status"], gate["result"]["count"]) == ("FAILED", 1)
    waiver = command(f"checklist/{gate['id']}/waive", maya, {"reason": WAIVER_REASON})
    assert waiver.status_code == 200, waiver.text
    waiver_id = str(waiver.json()["approval_request_id"])
    priya = actor_with_role(app, clock, tenant_id, "revenue_reviewer", name="priya")
    waived = approve(app, waiver_id, priya)
    assert (waived.status_code, waived.json()["status"]) == (200, "APPROVED"), waived.text

    # the lock: Maya requests, Marcus (Controller) decides
    requested = command("request-lock", maya, {"certification_comment": COMMENT})
    assert requested.status_code == 200, requested.text
    lock_request = str(requested.json()["approval_request_id"])
    marcus = actor_with_role(app, clock, tenant_id, "controller", name="marcus")
    locked = approve(app, lock_request, marcus)
    assert (locked.status_code, locked.json()["status"]) == (200, "APPROVED"), locked.text
    assert _september(world)["state"] == PeriodState.CLOSED.value

    # the reopen: Priya requests, two Controllers decide
    asked = command(
        "request-reopen",
        priya,
        {
            "judgement_record_id": str(reviewed_error_judgement(world)),
            "reason_code": "ERROR_CORRECTION",
            "comment": REOPEN_COMMENT,
        },
    )
    assert asked.status_code == 200, asked.text
    reopen_request = str(asked.json()["approval_request_id"])
    first = approve(app, reopen_request, marcus)
    assert (first.status_code, first.json()["status"]) == (200, "PENDING"), first.text
    elena = actor_with_role(app, clock, tenant_id, "controller", name="elena")
    second = approve(app, reopen_request, elena)
    assert (second.status_code, second.json()["status"]) == (200, "APPROVED"), second.text
    assert _september(world)["state"] == PeriodState.REOPENED.value

    with system_session(world) as session:
        stored = {
            str(row["id"]): dict(row)
            for row in session.execute(
                select(period_lock).where(period_lock.c.period_id == world.period_id)
            ).mappings()
        }
        frozen = [
            dict(row)
            for row in session.execute(
                select(lock_snapshot).where(lock_snapshot.c.period_lock_id.in_(list(stored)))
            ).mappings()
        ]
    numbers = {
        request_id: _request_no(world, request_id)
        for request_id in (waiver_id, lock_request, reopen_request)
    }
    assert len(set(numbers.values())) == 3

    listed = get(app, f"{PERIODS}/{state_id}/locks", maya)
    assert listed.status_code == 200, listed.text
    reopen, lock = listed.json()["items"]
    assert all("audit_head_hmac" not in item for item in (reopen, lock))

    lock_row = stored[lock["id"]]
    assert (lock["kind"], lock["approval_request_id"], lock["approval_request_no"]) == (
        "LOCK",
        lock_request,
        numbers[lock_request],
    )
    shown_request = get(app, f"{APPROVALS}/{lock_request}", marcus)
    assert shown_request.status_code == 200, shown_request.text
    assert shown_request.json()["request_no"] == lock["approval_request_no"]
    # (this world posts nothing, so the book has no seal: the hash is witnessed below)
    assert lock["ledger_head_sha256"] == lock_row["ledger_head_sha256"]

    certified = lock["certification"]
    assert [row["gate_check_code"] for row in certified] == list(gates.GATE_CHECK_CODES)
    assert len(certified) == 14
    for shown, kept in zip(certified, lock_row["certification"], strict=True):
        assert (shown["gate_check_code"], shown["status"], shown["count"]) == (
            kept["gate_check_code"],
            kept["status"],
            kept["count"],
        )
        assert datetime.fromisoformat(shown["evaluated_at"]) == datetime.fromisoformat(
            kept["evaluated_at"]
        )
    by_code = {row["gate_check_code"]: row for row in certified}
    exceptions = by_code.pop("EXCEPTIONS_CLEARED")
    assert {key: value for key, value in exceptions.items() if key != "evaluated_at"} == {
        "gate_check_code": "EXCEPTIONS_CLEARED",
        "status": "WAIVED",
        "count": 1,
        "waiver_approval_request_id": waiver_id,
        "waiver_approval_request_no": numbers[waiver_id],
        "waived_count": 1,
        "replayed": False,
    }
    assert {
        (
            row["status"],
            row["count"],
            row["waiver_approval_request_id"],
            row["waiver_approval_request_no"],
            row["waived_count"],
            row["replayed"],
        )
        for row in by_code.values()
    } == {("PASSED", 0, None, None, None, False)}

    assert [item["snapshot_kind"] for item in lock["snapshots"]] == [
        kind.value for kind in SnapshotKind
    ]
    assert len(lock["snapshots"]) == 12
    assert all(
        set(item) == {"snapshot_kind", "row_count", "file_sha256"} for item in lock["snapshots"]
    )
    assert {
        (item["snapshot_kind"], item["row_count"], item["file_sha256"])
        for item in lock["snapshots"]
    } == {
        (
            str(getattr(row["snapshot_kind"], "value", row["snapshot_kind"])),
            int(row["row_count"]),
            str(row["file_sha256"]),
        )
        for row in frozen
    }

    reopen_row = stored[reopen["id"]]
    assert (
        reopen["kind"],
        reopen["certification"],
        reopen["snapshots"],
        reopen["previous_lock_id"],
        reopen["reason_code"],
        reopen["approval_request_id"],
        reopen["approval_request_no"],
    ) == ("REOPEN", [], [], lock["id"], "ERROR_CORRECTION", reopen_request, numbers[reopen_request])
    assert reopen["ledger_head_sha256"] == reopen_row["ledger_head_sha256"]

    transitions = get(app, f"{PERIODS}/{state_id}/transitions", maya)
    assert transitions.status_code == 200, transitions.text
    assert [
        (
            item["from_state"],
            item["to_state"],
            item["approval_request_id"],
            item["approval_request_no"],
        )
        for item in transitions.json()["items"][:3]
    ] == [
        ("closed", "reopened", reopen_request, numbers[reopen_request]),
        ("closing", "closed", lock_request, numbers[lock_request]),
        ("open", "closing", None, None),
    ]

    # a reader of one entity of two
    vera = holding(app, colleague(tenant_id, "vera"), "viewer", entity_ids=[world.entity_id])
    assert get(app, f"{PERIODS}/{state_id}/locks", vera).json() == listed.json()
    assert get(app, f"{PERIODS}/{state_id}/transitions", vera).json() == transitions.json()
    ursula = holding(app, colleague(tenant_id, "ursula"), "viewer", entity_ids=[uk])
    for path in ("locks", "transitions"):
        hidden = get(app, f"{PERIODS}/{state_id}/{path}", ursula)
        assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text


@pytest.mark.slow
def test_locks_list_states_the_ledger_head_the_lock_sealed(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item CLO-LOCKS-READ-1 (04 §16.8 API-S-PeriodLock ``ledger_head_sha256``, rev 1.207), on a
    period with postings: WLD-K-01 with INV-US-1001, January 2026 locked through the product. The
    record states the hash of the book's last seal as the lock stored it — the head the journal
    run sealed, 64 hex digits, equal to T-CLS-04 and to the book's chain head — beside its
    sequence; the JE population among its twelve datasets holds the rows of that run."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(
        world, clock, entity_code=worlds.AVM_US, period_key=worlds.JANUARY_2026
    )
    state = worlds.period_state(world, worlds.AVM_US, worlds.JANUARY_2026)
    stored = world.place.rows(select(period_lock).where(period_lock.c.kind == "LOCK"))[0]
    head = world.place.rows(
        select(ledger_chain_head.c.last_chain_seq, ledger_chain_head.c.last_seal_sha256).where(
            ledger_chain_head.c.book_code == "ASC606"
        )
    )[0]

    listed = get(app, f"{PERIODS}/{state['id']}/locks", world.maya)
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    assert re.fullmatch(r"[0-9a-f]{64}", item["ledger_head_sha256"])
    assert (item["ledger_head_sha256"], item["ledger_head_chain_seq"]) == (
        stored["ledger_head_sha256"],
        int(stored["ledger_head_chain_seq"]),
    )
    assert (item["ledger_head_sha256"], item["ledger_head_chain_seq"]) == (
        head["last_seal_sha256"],
        int(head["last_chain_seq"]),
    )
    assert "audit_head_hmac" not in item
    assert {row["status"] for row in item["certification"]} == {"PASSED"}
    counts = {row["snapshot_kind"]: row["row_count"] for row in item["snapshots"]}
    assert list(counts) == [kind.value for kind in SnapshotKind]
    assert counts["JE_POPULATION"] > 0
