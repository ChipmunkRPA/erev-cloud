"""CLO-7 reopen with dual approval and the re-lock diff (BUILD_SPEC CLO-7 acceptance; REQ-CLS-001,
-011; SM-07 ``closed → reopened``; BR-CLS-02, BR-CLS-05, BR-CLS-07; ERR-16; NTF-07; T-CLS-04
``REOPEN``; SM-09; D-98 61, 63; F-CLO record §22).

DB-bound (``CloseWorld`` with Revenue Reviewer and Controller personas of the same tenant). NOT RUN
on the authoring worktree (databases not provisioned); measured by the integrated batch on merged
main. The reopen scenarios build the ``closed`` state through the lock's own writer
(``_persist_lock`` with an APPROVED ``PERIOD_LOCK`` request — the admitted fixture of record
§20.1), so they need no gate and no producer of another lane; ``test_relock_writes_diff_report``
locks through the real path and is the acceptance of the finished tree (``JE_COMPLETE`` carries
the real CLO-10 signal — PASSED 0 over a period without sealed activity; the producers by name).
Owed in slice 7b (record §22): ``test_relock_diff_k03``,
``test_post_reopen_lines_flagged_and_human_approved``, ``test_estimate_change_vs_error_paths``,
``test_period_state_machine_complete``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from erev_api import periods as period_kernel
from erev_api.approvals import engine as approvals
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    judgement_record,
    lock_snapshot,
    period_lock,
    period_reopen_basis,
    period_state_transition,
    reconciliation,
    subledger_line,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates, posting_guard
from erev_api.domain.close import snapshots as close_snapshots
from erev_api.domain.journals import subledger
from erev_api.domain.reports import evidence_certification, evidence_relock, evidence_selection
from erev_api.domain.reports import snapshots as registry
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ControlResult,
    FilePurpose,
    LockKind,
    PeriodState,
    SnapshotKind,
)
from erev_api.files.store import LocalFileStore, open_file, store_file
from erev_api.main import create_app
from erev_api.schemas.evidence_packs import ClosePackCreateIn
from erev_api.schemas.periods import PeriodLockRequestIn
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session
from support.close_world import (
    CloseWorld,
    acknowledged_run,
    actor_with_role,
    close_run_succeeded,
    close_world,
    contract_of,
    earlier_periods_closed,
    other_entity,
    reviewed_reconciliations,
    system_session,
)
from support.close_world import (
    reviewed_error_judgement as _reviewed_error_judgement,
)
from support.db import TestDatabase
from support.factories import booked_contract, computed
from support.principals import Actor, colleague, enrolled
from support.reference import PERIODS, approve, assign, get, periods, post, slug
from support.rows import approval_request_values
from support.worlds import (
    AUGUST_2026,
    AVM_US,
    FEBRUARY_2026,
    K01,
    approved_manual_events,
    k01_body,
    k01_pellworth,
    on_record_clock,
    period_locked,
    period_reopened,
    posted_journal,
    report_run,
    reviewed_reopen_judgement,
    verified,
)
from support.worlds import period_state as period_shown

REASON = "Costs of 20,500.00 on PRJ-CB-2026-01 incurred on 29 Sep 2026 were omitted."
LATER_CLOSED = "Reopen Sep 2026 first. A later period of AVM-US in book ASC606 is closed."  # ERR-16
EARLIER_OPEN = (
    "Lock Aug 2026 first. An earlier period of AVM-US in book ASC606 is not closed."  # ERR-65
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _value(stored: Any) -> str:
    return str(getattr(stored, "value", stored))


def _state(world: CloseWorld, key: str = "FY2026-P09") -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == key
    ]
    return found


def _scope(session: Session, state_id: UUID) -> gates.PeriodScope:
    scope = gates.period_scope(session, state_id, lock=True)
    assert scope is not None
    return scope


def _approved_lock_request(session: Session, world: CloseWorld, state_id: UUID) -> UUID:
    request = approval_request_values(
        world.tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        entity_id=world.entity_id,
        subject_type="PERIOD_LOCK",
        subject_id=state_id,
        summary="Fixture lock request",
    )
    session.execute(insert(approval_request).values(**request))
    return UUID(str(request["id"]))


def _lock_by_writer(world: CloseWorld, key: str = "FY2026-P09") -> UUID:
    """``open → closing → closed`` through the domain's own writers (record §20.1 (4), (5)); the
    fixture for a period whose reopen is under test. Returns the LOCK id."""
    state_id = UUID(str(_state(world, key)["id"]))
    lock_id = new_id()
    with world.place.uow() as uow:
        session = uow.session
        scope = _scope(session, state_id)
        assert scope.state == PeriodState.OPEN.value
        close_commands._record_transition(
            uow,
            state_id=state_id,
            current=close_commands._current(session, scope),
            from_state=PeriodState.OPEN,
            to_state=PeriodState.CLOSING,
            action=close_commands.START_CLOSE_ACTION,
            reason_code=None,
            comment="Fixture soft close",
        )
        scope = _scope(session, state_id)
        close_commands._persist_lock(
            uow,
            scope,
            kind=LockKind.LOCK,
            lock_id=lock_id,
            transition_id=new_id(),
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=close_commands.LOCK_ACTION,
            approval_request_id=_approved_lock_request(session, world, state_id),
            comment="Fixture lock",
            certification=[],
            snapshot_manifest_sha256=None,
            heads=close_commands._heads(session, scope),
            cutoff_known_at=uow.now,  # 04 T-CLS-04 rev 1.113 (R-40 (c)): a LOCK names its cutoff
        )
        uow.commit()
    return lock_id


def _request_reopen(
    world: CloseWorld, requester: Actor, key: str = "FY2026-P09", reason: str = "ERROR_CORRECTION"
) -> Any:
    citation = _reviewed_error_judgement(world) if reason == "ERROR_CORRECTION" else None
    shown = _state(world, key)
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-reopen",
        requester,
        {
            "reason_code": reason,
            "comment": REASON,
            "judgement_record_id": None if citation is None else str(citation),
        },
        if_match=f'"r{shown["row_version"]}"',
    )


def _request_status(world: CloseWorld, request_id: str) -> str:
    with system_session(world) as session:
        return _value(
            session.execute(
                select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
            ).scalar_one()
        )


def _locks(world: CloseWorld) -> list[dict[str, Any]]:
    with system_session(world) as session:
        return [
            dict(row)
            for row in session.execute(
                select(period_lock)
                .where(period_lock.c.period_id == world.period_id)
                .order_by(period_lock.c.created_at, period_lock.c.id)
            ).mappings()
        ]


def _seed_snapshot(world: CloseWorld, lock_id: UUID) -> UUID:
    """One T-CLS-05 row bound to the fixture lock — CLO-8c: the CONTRACT_BALANCES dataset produced
    by the F-RPS registry adapter for the lock's scope at this instant and stored as F-CLO's
    machine artefact, so the reopen's "snapshots stay" assertion preserves something real."""
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id, lock=True)
        assert scope is not None
        encoded = registry.SNAPSHOT_DATASETS[SnapshotKind.CONTRACT_BALANCES.value](
            uow,
            registry.SnapshotScope(
                entity_id=scope.entity_id,
                book_code=scope.book_code,
                period_id=scope.period_id,
                known_at=uow.now,
            ),
        )
        stored = store_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=BytesIO(bytes(encoded.content)),
            original_filename=f"{encoded.kind}{close_snapshots.FILE_SUFFIX}",
            media_type=close_snapshots.MEDIA_TYPE,
        )
        assert str(stored["sha256"]) == encoded.file_sha256  # S15-INV-06
        row = {
            "tenant_id": world.tenant_id,
            "id": new_id(),
            "period_lock_id": lock_id,
            "snapshot_kind": encoded.kind,
            "report_run_id": None,
            "file_id": stored["id"],
            "file_sha256": encoded.file_sha256,
            "row_count": encoded.row_count,
            "control_totals": dict(encoded.control_totals),
            "created_at": uow.now,
            "created_by": None,
            "created_by_kind": "SYSTEM",
        }
        uow.session.execute(insert(lock_snapshot).values(**row))
        uow.commit()
        return UUID(str(row["id"]))


def _snapshot_count(world: CloseWorld, lock_id: UUID) -> int:
    with system_session(world) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(lock_snapshot)
                .where(lock_snapshot.c.period_lock_id == lock_id)
            ).scalar_one()
        )


# --- the CLO-7 domain tests --------------------------------------------------------------------


def test_reopen_dual_approval(world: CloseWorld, clock: FrozenClock) -> None:
    """J-14.1 to J-14.3, J-14-ALT-1; BR-CLS-02: Priya (Revenue Reviewer) requests the reopen of
    Sep 2026 with ``ERROR_CORRECTION``; Marcus approves (1 of 2); Priya's decision is 403
    ``self-approval``; Marcus's second decision 409 ``approver-already-decided``; Elena's approval
    reopens the period with a ``REOPEN`` record whose ``previous_lock_id`` names the lock; the lock
    snapshots stay (REQ-CLS-011)."""
    lock_id = _lock_by_writer(world)
    _seed_snapshot(world, lock_id)
    snapshots_before = _snapshot_count(world, lock_id)
    assert snapshots_before > 0  # REQ-CLS-011 needs something to preserve
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="elena")
    requested = _request_reopen(world, priya)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    first = approve(world.app, request_id, marcus)
    assert first.status_code == 200, first.text
    assert _request_status(world, request_id) == "PENDING"
    assert _state(world)["state"] == PeriodState.CLOSED.value
    own = approve(world.app, request_id, priya)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    again = approve(world.app, request_id, marcus)
    assert (again.status_code, slug(again)) == (409, "approver-already-decided"), again.text
    second = approve(world.app, request_id, elena)
    assert second.status_code == 200, second.text
    assert _request_status(world, request_id) == "APPROVED"
    shown = _state(world)
    assert shown["state"] == PeriodState.REOPENED.value
    lock, reopen = _locks(world)
    assert (UUID(str(lock["id"])), _value(lock["kind"])) == (lock_id, LockKind.LOCK.value)
    assert (_value(reopen["kind"]), reopen["previous_lock_id"]) == (LockKind.REOPEN.value, lock_id)
    assert (_value(reopen["reason_code"]), reopen["comment"]) == ("ERROR_CORRECTION", REASON)
    assert (str(reopen["approval_request_id"]), reopen["snapshot_manifest_sha256"]) == (
        request_id,
        None,
    )
    assert reopen["certification"] == []
    assert UUID(str(shown["current_lock"]["id"])) == UUID(str(reopen["id"]))
    assert _snapshot_count(world, lock_id) == snapshots_before


@pytest.mark.control("CTL-018")
def test_ctl_018_reopen_needs_a_controller(world: CloseWorld, clock: FrozenClock) -> None:
    """Two Revenue Reviewer approvals leave the request PENDING and the period ``closed``; a
    Controller's approval completes it (PRD §2.5 ``PERIOD_REOPEN``; D-75 Q12; REQ-CLS-011)."""
    _lock_by_writer(world)
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    reviewer_one = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="rr1"
    )
    reviewer_two = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="rr2"
    )
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    requested = _request_reopen(world, priya)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    for reviewer in (reviewer_one, reviewer_two):
        decided = approve(world.app, request_id, reviewer)
        assert decided.status_code == 200, decided.text
    assert _request_status(world, request_id) == "PENDING"
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert [_value(row["kind"]) for row in _locks(world)] == [LockKind.LOCK.value]
    completed = approve(world.app, request_id, marcus)
    assert completed.status_code == 200, completed.text
    assert _request_status(world, request_id) == "APPROVED"
    assert _state(world)["state"] == PeriodState.REOPENED.value
    assert [_value(row["kind"]) for row in _locks(world)] == [
        LockKind.LOCK.value,
        LockKind.REOPEN.value,
    ]


@pytest.mark.control("CTL-018")
def test_ctl_018_reopen_needs_a_controller_of_the_periods_entity(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Security review SC-N5 (supervisor ruling R-25; REQ-CLS-011 rev 1.19; 04 T-PLT-18 rev
    1.104): the Controller among the two reopen approvers holds the role for the PERIOD'S entity.
    Rhys approves for AVM-US as a Revenue Reviewer and is a Controller of AVM-UK only. With a
    second Revenue Reviewer's approval the request stays PENDING and the period ``closed`` —
    before the fix his Controller role for another entity completed the quorum. A Controller of
    AVM-US completes it."""
    _lock_by_writer(world)
    with system_session(world) as session:
        uk_entity_id = other_entity(session, world)
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    reviewer = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="rr1")
    rhys_member = colleague(world.tenant_id, "rhys")
    assign(rhys_member, "revenue_reviewer", entity_ids=[world.entity_id])
    assign(rhys_member, "controller", entity_ids=[uk_entity_id])
    rhys = enrolled(world.app, clock, rhys_member)
    marcus_member = colleague(world.tenant_id, "marcus")
    assign(marcus_member, "controller", entity_ids=[world.entity_id])
    marcus = enrolled(world.app, clock, marcus_member)

    requested = _request_reopen(world, priya)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    for approver in (reviewer, rhys):
        decided = approve(world.app, request_id, approver)
        assert decided.status_code == 200, decided.text
    assert _request_status(world, request_id) == "PENDING"
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert [_value(row["kind"]) for row in _locks(world)] == [LockKind.LOCK.value]

    # Positive control: a Controller whose assignment covers AVM-US completes the quorum.
    completed = approve(world.app, request_id, marcus)
    assert completed.status_code == 200, completed.text
    assert _request_status(world, request_id) == "APPROVED"
    assert _state(world)["state"] == PeriodState.REOPENED.value
    assert [_value(row["kind"]) for row in _locks(world)] == [
        LockKind.LOCK.value,
        LockKind.REOPEN.value,
    ]


def test_reopen_later_period_closed(world: CloseWorld, clock: FrozenClock) -> None:
    """BR-CLS-05 (ERR-16; J-14-ALT-3): with Aug and Sep 2026 ``closed``, a reopen request for Aug
    2026 is 409 ``later-period-closed`` with the verbatim detail naming Sep 2026."""
    _lock_by_writer(world, "FY2026-P08")
    _lock_by_writer(world, "FY2026-P09")
    assert _state(world, "FY2026-P09")["period"]["name"] == "Sep 2026"
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    refused = _request_reopen(world, priya, key="FY2026-P08")
    assert (refused.status_code, slug(refused)) == (409, "later-period-closed"), refused.text
    body = refused.json()
    assert body["detail"] == LATER_CLOSED
    # 04 §15.2 `later-period-closed` (409, ERR-16): errors "none" — the rule lives in the detail
    # and the machine's refusal (`RULE_LATER_PERIOD`), not in an errors list.
    assert body["errors"] == []
    assert _state(world, "FY2026-P08")["state"] == PeriodState.CLOSED.value


def test_br_cls_08_lock_decision_refused_after_an_earlier_period_reopened(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """PRD BR-CLS-08 / ERR-65 at the decision (supervisor ruling R-6: "checked at the request AND
    at the approval execution … a request can outlive an earlier period's state"). September is
    submitted for lock with January to August closed; before a Controller decides, August is
    reopened — BR-CLS-05 admits that, because no later period is closed. The lock decision is then
    409 ``earlier-period-open`` naming August: the request stays PENDING, September stays in soft
    close and nothing of a lock is written. Until this ruling the decision locked September above
    the reopened August."""
    earlier_periods_closed(world)
    shown = _state(world)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    acknowledged_run(world)
    with system_session(world) as session:
        reviewed_reconciliations(session, world)
        close_run_succeeded(session, world)
    with world.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=world.state_id,
            body=PeriodLockRequestIn(certification_comment="September 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    request_id = str(out.approval_request_id)

    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="elena")
    reopen = _request_reopen(world, priya, key="FY2026-P08")
    assert reopen.status_code == 200, reopen.text
    reopen_id = str(reopen.json()["approval_request_id"])
    assert approve(world.app, reopen_id, marcus).status_code == 200
    assert approve(world.app, reopen_id, elena).status_code == 200
    assert _state(world, "FY2026-P08")["state"] == PeriodState.REOPENED.value

    refused = approve(world.app, request_id, marcus)
    assert (refused.status_code, slug(refused)) == (409, "earlier-period-open"), refused.text
    assert refused.json()["detail"] == EARLIER_OPEN
    assert refused.json()["errors"] == []
    assert _request_status(world, request_id) == "PENDING"
    assert _state(world)["state"] == PeriodState.CLOSING.value
    assert _locks(world) == []


def test_reopen_reason_subset(world: CloseWorld, clock: FrozenClock) -> None:
    """``CLOSE_RESTARTED`` is not of the request-reopen subset (04 table 3.4-R): 422
    ``validation-failed`` with ``rule_id`` ``REASON_CODE_NOT_ALLOWED``; nothing is requested."""
    _lock_by_writer(world)
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    refused = _request_reopen(world, priya, reason="CLOSE_RESTARTED")
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [(error["field"], error["rule_id"]) for error in refused.json()["errors"]] == [
        ("reason_code", "REASON_CODE_NOT_ALLOWED")
    ]
    with system_session(world) as session:
        pending = session.execute(
            select(func.count())
            .select_from(approval_request)
            .where(approval_request.c.subject_type == "PERIOD_REOPEN")
        ).scalar_one()
    assert int(pending) == 0


def _reconciliation_rows(world: CloseWorld) -> list[tuple[str, str, UUID | None]]:
    with system_session(world) as session:
        return sorted(
            (_value(row.kind), _value(row.status), row.period_lock_id)
            for row in session.execute(
                select(
                    reconciliation.c.kind, reconciliation.c.status, reconciliation.c.period_lock_id
                ).where(reconciliation.c.period_id == world.period_id)
            )
        )


def test_relock_writes_diff_report(world: CloseWorld, clock: FrozenClock) -> None:
    """J-14.7; BR-CLS-07; S15-R-20: lock Sep 2026 through the real path, reopen it (two approvers),
    close and lock it again. The re-lock's ``LOCK`` names the ``REOPEN`` as ``previous_lock_id`` and
    stores the diff report against the first lock: both ids and manifests, the twelve kinds with
    the stored hashes, the certification before and after. SM-09 / D-98 63: the first lock's
    reconciliations are REOPENED and keep its id; the reconciliations generated after the reopen
    are CERTIFIED against the re-lock. Acceptance of the finished tree (CLO-10; the producers).
    January to August are closed first (PRD WLD-P-02; BR-CLS-08, supervisor ruling R-6)."""
    earlier_periods_closed(world)
    shown = _state(world)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    acknowledged_run(world)
    with system_session(world) as session:
        reviewed_reconciliations(session, world)
        close_run_succeeded(session, world)
    with world.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=world.state_id,
            body=PeriodLockRequestIn(certification_comment="September 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    assert approve(world.app, str(out.approval_request_id), marcus).status_code == 200
    (first,) = _locks(world)
    first_id = UUID(str(first["id"]))
    assert _reconciliation_rows(world) == [
        ("BILLING_TO_SUBLEDGER", "CERTIFIED", first_id),
        ("SUBLEDGER_TO_GL", "CERTIFIED", first_id),
    ]
    # Reopen: Priya requests, Marcus and Elena approve.
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="elena")
    requested = _request_reopen(world, priya)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    assert approve(world.app, request_id, marcus).status_code == 200
    assert approve(world.app, request_id, elena).status_code == 200
    assert _state(world)["state"] == PeriodState.REOPENED.value
    assert _reconciliation_rows(world) == [
        ("BILLING_TO_SUBLEDGER", "REOPENED", first_id),
        ("SUBLEDGER_TO_GL", "REOPENED", first_id),
    ]
    _, reopen = _locks(world)
    # Close again: the acknowledged run still stands; the reconciliations are regenerated as new
    # rows (04 §20 OQ-15).
    shown = _state(world)
    restarted = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close restarted after the reopen"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert restarted.status_code == 200, restarted.text
    with system_session(world) as session:
        reviewed_reconciliations(session, world)
    with world.place.uow() as uow:
        again = close_commands.request_lock(
            uow,
            state_id=world.state_id,
            body=PeriodLockRequestIn(certification_comment="September 2026 re-lock complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    relocked = approve(world.app, str(again.approval_request_id), marcus)
    assert relocked.status_code == 200, relocked.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    _, _, second = _locks(world)
    second_id = UUID(str(second["id"]))
    assert (_value(second["kind"]), second["previous_lock_id"]) == (
        LockKind.LOCK.value,
        UUID(str(reopen["id"])),
    )
    assert second["diff_report_file_id"] is not None
    assert _reconciliation_rows(world) == [
        ("BILLING_TO_SUBLEDGER", "CERTIFIED", second_id),
        ("BILLING_TO_SUBLEDGER", "REOPENED", first_id),
        ("SUBLEDGER_TO_GL", "CERTIFIED", second_id),
        ("SUBLEDGER_TO_GL", "REOPENED", first_id),
    ]
    with system_session(world) as session:
        _, stream = open_file(
            session,
            UUID(str(second["diff_report_file_id"])),
            files=world.place.files,
            keyring=world.place.keyring,
        )
        report = json.loads(stream.read().decode("utf-8"))
        hashes = {
            (str(row.period_lock_id), _value(row.snapshot_kind)): str(row.file_sha256)
            for row in session.execute(
                select(
                    lock_snapshot.c.period_lock_id,
                    lock_snapshot.c.snapshot_kind,
                    lock_snapshot.c.file_sha256,
                ).where(lock_snapshot.c.period_lock_id.in_([first_id, second_id]))
            )
        }
    assert (report["format"], report["previous_lock_id"], report["lock_id"]) == (
        "erev.relock_diff.v1",
        str(first_id),
        str(second_id),
    )
    assert report["manifest"]["previous"] == first["snapshot_manifest_sha256"]
    assert report["manifest"]["current"] == second["snapshot_manifest_sha256"]
    assert sorted(report["kinds"]) == sorted(kind.value for kind in SnapshotKind)
    for kind, entry in report["kinds"].items():
        assert entry["previous_file_sha256"] == hashes[(str(first_id), kind)]
        assert entry["current_file_sha256"] == hashes[(str(second_id), kind)]
        assert entry["changed"] == (entry["previous_file_sha256"] != entry["current_file_sha256"])
    assert [row["gate_check_code"] for row in report["certification"]["previous"]] == list(
        gates.GATE_CHECK_CODES
    )
    assert [row["gate_check_code"] for row in report["certification"]["current"]] == list(
        gates.GATE_CHECK_CODES
    )
    # RPS-16's collector consumes the real approved re-lock's saved evidence. This
    # explicit read principal tests collection; pack HTTP guards/download remain separate.
    reader = replace(
        world.place.principal,
        permissions=frozenset({"report.run", "audit.read"}),
        permission_scopes={"report.run": "*", "audit.read": "*"},
    )
    with world.place.uow(reader) as uow:
        selection = evidence_selection.resolve(
            uow,
            ClosePackCreateIn.model_validate(
                {
                    "kind": "CLOSE",
                    "entity_code": "AVM-US",
                    "book": "ASC606",
                    "period_key": "FY2026-P09",
                    "period_lock_id": second_id,
                }
            ),
        )
        packed = evidence_relock.collect(uow, selection)
        saved = next(
            file.content for file in packed if file.path == "relock/stored_comparison.json"
        )
        assert json.loads(saved) == report
        approvals = evidence_certification.collect(uow, selection)
        assert evidence_certification.collect(uow, selection) == approvals
        proof = json.loads(approvals[0].content)
        assert proof["period_lock_id"] == str(second_id)
        assert proof["lock_approval"]["request"]["status"] == "APPROVED"
        assert proof["lock_approval"]["decisions"]
        prior = evidence_selection.resolve(
            uow,
            ClosePackCreateIn.model_validate(
                {
                    "kind": "CLOSE",
                    "entity_code": "AVM-US",
                    "book": "ASC606",
                    "period_key": "FY2026-P09",
                    "period_lock_id": first_id,
                }
            ),
        )
        earlier_proof = json.loads(evidence_certification.collect(uow, prior)[0].content)
        assert earlier_proof["period_lock_id"] == str(first_id)
        assert earlier_proof["lock_approval"]["request"]["id"] == str(out.approval_request_id)
        assert (
            earlier_proof["lock_approval"]["request"]["id"]
            != proof["lock_approval"]["request"]["id"]
        )
        assert {waiver["gate_check_code"] for waiver in proof["waivers"]} == {
            item["gate_check_code"]
            for item in report["certification"]["current"]
            if item["status"] == "WAIVED"
        }


# --- 7b: the SM-07 sweep and the BR-CLS-06 predicate -------------------------------------------

TRANSITION_ACTIONS = (
    "period.open",
    "period.start_close",
    "period.cancel_close",
    "period.lock",
    "period.reopen",
    "period.permanent_lock",
)
# SM-07 (PRD §5.2): the commands each state accepts; every other command is 409 invalid-transition.
ALLOWED_COMMANDS: dict[str, frozenset[str]] = {
    "future": frozenset({"open"}),
    "open": frozenset({"start-close"}),
    "closing": frozenset({"cancel-close", "request-lock"}),
    "closed": frozenset({"request-reopen", "request-permanent-lock"}),
    "reopened": frozenset({"start-close"}),
    "permanently_locked": frozenset(),
}
COMMAND_BODIES: dict[str, dict[str, Any]] = {
    "open": {"comment": "Open for the sweep"},
    "start-close": {"comment": "Close in progress"},
    "cancel-close": {"reason_code": "CLOSE_RESTARTED", "comment": "Close restarted"},
    "request-lock": {"certification_comment": "Close complete for the sweep"},
    "request-reopen": {"reason_code": "ERROR_CORRECTION", "comment": REASON},
    "request-permanent-lock": {"comment": "Audit complete; freeze the period"},
}


def _command(world: CloseWorld, actor: Actor, key: str, name: str) -> Any:
    shown = _state(world, key)
    body = dict(COMMAND_BODIES[name])
    if name == "request-reopen" and shown["state"] == "closed":
        body["judgement_record_id"] = str(_reviewed_error_judgement(world))
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/{name}",
        actor,
        body,
        if_match=f'"r{shown["row_version"]}"',
    )


def _refused_elsewhere(
    world: CloseWorld, maya: Actor, priya: Actor, key: str, *, controller: Actor
) -> None:
    """Every command SM-07 does not list for the period's current state is 409
    ``invalid-transition`` and leaves state and version unchanged. Each command is sent by a
    holder of its permission, so that the refusal is the state's: ``period.reopen_request`` for
    the reopen request (Priya), ``period.lock`` for the permanent-lock request (a Controller; PRD
    ACT-27, supervisor ruling R-83 (a)), ``period.close`` for the others (Maya)."""
    holders = {"request-reopen": priya, "request-permanent-lock": controller}
    before = _state(world, key)
    for name in sorted(set(COMMAND_BODIES) - ALLOWED_COMMANDS[before["state"]]):
        actor = holders.get(name, maya)
        refused = _command(world, actor, key, name)
        assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), (
            before["state"],
            name,
            refused.text,
        )
    after = _state(world, key)
    assert (after["state"], after["row_version"]) == (before["state"], before["row_version"])


def test_period_state_machine_complete(world: CloseWorld, clock: FrozenClock) -> None:
    """REQ-CLS-001 (BUILD_SPEC CLO-7): every SM-07 pair of PRD §5.2 succeeds through its command —
    ``future → open`` on FY2026-P10; on FY2026-P01 (no earlier period, so the permanent lock needs
    no fixture; opened ``future → open`` by the world) ``open → closing → open → closing → closed →
    reopened → closing → closed → permanently_locked`` — and in every state reached every other
    command is 409 ``invalid-transition``. Each transition writes one audit event with the acting
    user, the reason where the command carries one and a UTC instant. Acceptance of the finished
    tree: the two locks need ``JE_COMPLETE`` (CLO-10) and the producers by name."""
    maya = world.maya
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="elena")
    # future → open
    _refused_elsewhere(world, maya, priya, "FY2026-P10", controller=marcus)
    opened = _command(world, maya, "FY2026-P10", "open")
    assert opened.status_code == 200, opened.text
    assert _state(world, "FY2026-P10")["state"] == PeriodState.OPEN.value
    # open → closing → open (cancel) → closing
    key = "FY2026-P01"
    january = _state(world, key)
    period_id = UUID(str(january["period"]["id"]))
    state_id = UUID(str(january["id"]))
    _refused_elsewhere(world, maya, priya, key, controller=marcus)
    assert _command(world, maya, key, "start-close").status_code == 200
    _refused_elsewhere(world, maya, priya, key, controller=marcus)
    assert _command(world, maya, key, "cancel-close").status_code == 200
    assert _state(world, key)["state"] == PeriodState.OPEN.value
    assert _command(world, maya, key, "start-close").status_code == 200
    # closing → closed (lock)
    acknowledged_run(world, period_id)
    with system_session(world) as session:
        reviewed_reconciliations(session, world, period_id)
        close_run_succeeded(session, world, period_id)
    requested = _command(world, maya, key, "request-lock")
    assert requested.status_code == 200, requested.text
    assert (
        approve(world.app, str(requested.json()["approval_request_id"]), marcus).status_code == 200
    )
    assert _state(world, key)["state"] == PeriodState.CLOSED.value
    _refused_elsewhere(world, maya, priya, key, controller=marcus)
    # closed → reopened
    reopen = _command(world, priya, key, "request-reopen")
    assert reopen.status_code == 200, reopen.text
    reopen_id = str(reopen.json()["approval_request_id"])
    assert approve(world.app, reopen_id, marcus).status_code == 200
    assert approve(world.app, reopen_id, elena).status_code == 200
    assert _state(world, key)["state"] == PeriodState.REOPENED.value
    _refused_elsewhere(world, maya, priya, key, controller=marcus)
    # reopened → closing → closed (re-lock; the reconciliations regenerated as new rows, D-98 79)
    assert _command(world, maya, key, "start-close").status_code == 200
    with system_session(world) as session:
        reviewed_reconciliations(session, world, period_id)
    relock = _command(world, maya, key, "request-lock")
    assert relock.status_code == 200, relock.text
    assert approve(world.app, str(relock.json()["approval_request_id"]), marcus).status_code == 200
    assert _state(world, key)["state"] == PeriodState.CLOSED.value
    # closed → permanently_locked: requested by one Controller, decided by another (PRD ACT-27,
    # SM-07; supervisor ruling R-83 (a) — Maya, who holds ``period.close`` alone, requested it
    # until then).
    permanent = _command(world, marcus, key, "request-permanent-lock")
    assert permanent.status_code == 200, permanent.text
    assert (
        approve(world.app, str(permanent.json()["approval_request_id"]), elena).status_code == 200
    )
    assert _state(world, key)["state"] == PeriodState.PERMANENTLY_LOCKED.value
    _refused_elsewhere(world, maya, priya, key, controller=marcus)
    # One audit event per transition, with user, reason and UTC time (REQ-CLS-001). January's
    # history begins with the world's own opening — ``world_calendar`` opens FY2026-P01 to P09
    # through ``POST /periods/{id}/open`` as Maya — because a period state is created ``future``
    # and only then opens (04 T-REF-07 ``to_state``: "Allowed: NULL→future, future→open, …"; DB-07);
    # the creation row (``from_state`` NULL; the AUD-FACT ``period_state_transition.create``) is
    # outside the filter.
    audited = (
        audit_event.c.action,
        audit_event.c.actor_id,
        audit_event.c.actor_kind,
        audit_event.c.reason_code,
        audit_event.c.occurred_at,
        audit_event.c.before,
        audit_event.c.after,
    )
    with system_session(world) as session:
        transitions = session.execute(
            select(
                period_state_transition.c.id,
                period_state_transition.c.from_state,
                period_state_transition.c.to_state,
            )
            .where(
                period_state_transition.c.period_state_id == state_id,
                period_state_transition.c.from_state.is_not(None),
            )
            .order_by(period_state_transition.c.created_at, period_state_transition.c.id)
        ).all()
        events = session.execute(
            select(*audited)
            .where(
                audit_event.c.object_type == "period_state",
                audit_event.c.object_id == state_id,
                audit_event.c.action.in_(TRANSITION_ACTIONS),
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
        # RFD-2's ``open`` audits on the transition row it writes (``period.open`` on
        # ``period_state_transition``, the pair in ``after``); the close commands of CLO-3 to
        # CLO-7 audit on the period state.
        opening = session.execute(
            select(*audited).where(
                audit_event.c.object_type == "period_state_transition",
                audit_event.c.object_id == transitions[0].id,
            )
        ).all()
    assert transitions_pairs(transitions) == [
        ("future", "open"),
        ("open", "closing"),
        ("closing", "open"),
        ("open", "closing"),
        ("closing", "closed"),
        ("closed", "reopened"),
        ("reopened", "closing"),
        ("closing", "closed"),
        ("closed", "permanently_locked"),
    ]
    (opened,) = opening
    assert (opened.action, opened.after["from_state"], opened.after["to_state"]) == (
        "period.open",
        "future",
        "open",
    )
    assert [event.action for event in events] == [
        "period.start_close",
        "period.cancel_close",
        "period.start_close",
        "period.lock",
        "period.reopen",
        "period.start_close",
        "period.lock",
        "period.permanent_lock",
    ]
    assert [(event.before["state"], event.after["state"]) for event in events] == transitions_pairs(
        transitions[1:]
    )
    every = [opened, *events]  # nine transitions, nine events
    assert all(event.actor_id is not None and _value(event.actor_kind) == "USER" for event in every)
    assert [_value(event.reason_code) if event.reason_code else None for event in every] == [
        None,
        None,
        "CLOSE_RESTARTED",
        None,
        None,
        "ERROR_CORRECTION",
        None,
        None,
        None,
    ]
    assert all(
        event.occurred_at.tzinfo is not None
        and event.occurred_at.utcoffset() == UTC.utcoffset(None)
        for event in every
    )


def transitions_pairs(rows: list[Any]) -> list[tuple[str, str]]:
    return [(_value(row.from_state), _value(row.to_state)) for row in rows]


def test_posting_guard_restricts_closing_and_reopened_periods(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """BR-CLS-04 / BR-CLS-06: the predicate the posting commands pass as ``auto_approval=not …`` —
    False for an open period, True while the period is ``closing`` and after it is ``reopened``;
    False for a closed period (the posting itself is refused by DB-07) and for a date without a
    postable period."""
    september = date(2026, 9, 15)

    def restricted(day: date) -> bool:
        with system_session(world) as session:
            return posting_guard.posts_into_restricted_period(
                session, entity_id=world.entity_id, book_code=BookCode.ASC606, effective_date=day
            )

    assert restricted(september) is False
    assert restricted(date(2031, 1, 1)) is False  # no period of that year
    shown = _state(world)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    assert restricted(september) is True  # closing (BR-CLS-04)
    shown = _state(world)
    cancelled = post(
        world.app,
        f"{PERIODS}/{shown['id']}/cancel-close",
        world.maya,
        {"reason_code": "CLOSE_RESTARTED", "comment": "Back to open for the fixture"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert cancelled.status_code == 200, cancelled.text
    _lock_by_writer(world)
    assert restricted(september) is False  # closed: DB-07 refuses the posting itself
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="elena")
    requested = _request_reopen(world, priya)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    assert approve(world.app, request_id, marcus).status_code == 200
    assert approve(world.app, request_id, elena).status_code == 200
    assert _state(world)["state"] == PeriodState.REOPENED.value
    assert restricted(september) is True  # reopened (BR-CLS-06)
    assert restricted(date(2026, 8, 15)) is False  # August stays open


def test_cancel_close_returns_a_reopened_period_to_reopened(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """CLO-CANCEL-CLOSE-REOPENED-1 (PRD SM-07 "End soft close"; BR-CLS-06; 04 T-REF-07, DB-07 rev
    1.170): ``cancel-close`` returns a period to the state its soft close started from. WLD-K-01
    through 31 Aug 2026; August of AVM-US is locked and reopened through the product (Priya's
    request, two approvals), soft-closed again and the soft close ended. The period is
    ``reopened`` again — it was locked once — so what posts into it afterwards is post-reopen
    activity under BR-CLS-06: the lines of a later posting carry ``is_post_reopen`` and the
    posting commands' predicate still asks for a human approval.

    Until this change the period read ``open``: one holder of ``period.close`` turned a reopened
    period into an ordinary open one with two commands, its later lines lost the flag and its
    postings were open to the auto-approval rules again."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run and the reopen
    world = on_record_clock(world, clock)  # a close runs on the record-time clock
    _, world = period_locked(world, clock, entity_code=AVM_US, period_key=AUGUST_2026)
    elena = actor_with_role(app, clock, world.tenant_id, "controller", name="elena")
    shown = period_shown(world, AVM_US, AUGUST_2026)
    state_id, period_id = UUID(str(shown["id"])), UUID(str(shown["period"]["id"]))
    world = verified(world, clock, "priya")
    citation, world = reviewed_reopen_judgement(world, clock, entity_code=AVM_US, comment=REASON)
    requested = post(
        app,
        f"{PERIODS}/{state_id}/request-reopen",
        world.priya,
        {"reason_code": "ERROR_CORRECTION", "comment": REASON, "judgement_record_id": citation},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    reopen_id = str(requested.json()["approval_request_id"])
    world = verified(world, clock, "marcus")
    assert approve(app, reopen_id, world.marcus).status_code == 200
    assert approve(app, reopen_id, elena).status_code == 200
    assert period_shown(world, AVM_US, AUGUST_2026)["state"] == PeriodState.REOPENED.value

    def command(name: str, body: dict[str, Any]) -> Any:
        current = period_shown(world, AVM_US, AUGUST_2026)
        return post(
            app,
            f"{PERIODS}/{state_id}/{name}",
            world.maya,
            body,
            if_match=f'"r{current["row_version"]}"',
        )

    def restricted() -> bool:
        context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            return posting_guard.posts_into_restricted_period(
                session,
                entity_id=world.entity_id,
                book_code=BookCode.ASC606,
                effective_date=date(2026, 8, 15),
            )

    assert command("start-close", {"comment": "August close, again"}).status_code == 200
    ended = command(
        "cancel-close", {"reason_code": "CLOSE_RESTARTED", "comment": "August close restarted"}
    )
    assert ended.status_code == 200, ended.text
    # The soft close started from ``reopened`` and returns there.
    assert ended.json()["state"] == PeriodState.REOPENED.value
    assert period_shown(world, AVM_US, AUGUST_2026)["state"] == PeriodState.REOPENED.value
    assert restricted() is True  # BR-CLS-06 still holds for the period

    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        history = session.execute(
            select(
                period_state_transition.c.from_state,
                period_state_transition.c.to_state,
                period_state_transition.c.reason_code,
                period_state_transition.c.approval_request_id,
                period_state_transition.c.period_lock_id,
            )
            .where(period_state_transition.c.period_state_id == state_id)
            .order_by(period_state_transition.c.created_txid, period_state_transition.c.id)
        ).all()
        (reopen_record,) = session.execute(
            select(period_lock.c.id).where(
                period_lock.c.period_id == period_id, period_lock.c.kind == LockKind.REOPEN.value
            )
        ).scalars()
    reopened, restarted, returned = history[-3:]
    assert (reopened.from_state, reopened.to_state) == ("closed", "reopened")
    assert (str(reopened.approval_request_id), reopened.period_lock_id) == (
        reopen_id,
        reopen_record,
    )
    assert (restarted.from_state, restarted.to_state) == ("reopened", "closing")
    # T-REF-07: the row that returns the period carries the reason of the cancel and neither an
    # approval request nor a lock record — nothing was approved; the period stays under the
    # REOPEN record it had.
    assert (returned.from_state, returned.to_state, _value(returned.reason_code)) == (
        "closing",
        "reopened",
        "CLOSE_RESTARTED",
    )
    assert (returned.approval_request_id, returned.period_lock_id) == (None, None)
    current = period_shown(world, AVM_US, AUGUST_2026)["current_lock"]
    assert (current["id"], current["kind"]) == (str(reopen_record), LockKind.REOPEN.value)

    # A posting after the cancel: a second contract of the customer that begins on 1 August is
    # computed. Its lines of August are post-reopen lines, and the ledger chain verifies.
    body = k01_body(UUID(str(world.contracts[K01].contract["customer_id"])))
    body["external_id"] = "LATE-ARRIVAL-02"
    body["inception_date"] = "2026-08-01"
    body["lines"] = [{**body["lines"][0], "start_date": "2026-08-01"}]
    late = booked_contract(world.place, body, activate=True)
    stored = computed(world.place, UUID(str(late.combination_group["id"])))[2]
    posting_id = UUID(str(stored["subledger_posting_ids"]["ASC606"]))
    with tenant_session(context, read_only=True) as session:
        flags = set(
            session.scalars(
                select(subledger_line.c.is_post_reopen).where(
                    subledger_line.c.subledger_posting_id == posting_id,
                    subledger_line.c.period_id == period_id,
                )
            )
        )
        chain = subledger.verify_ledger_chain(session, book_code="ASC606")
    assert flags == {True}
    assert (chain.result, chain.first_failure_seq) == (ControlResult.PASS, None)


def test_a_line_posted_in_the_soft_close_after_a_reopen_is_a_post_reopen_line(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """REOPEN-CLOSING-FLAG-1 (supervisor ruling R-117 (c); 04 T-SL-04 and DB-07 rev 1.184,
    revision 0113; PRD BR-CLS-06 rev 1.113): a line is a post-reopen line while its period is
    under its ``REOPEN`` record — locked once and not locked now — whatever the state reads.

    WLD-K-01 through 26 Feb 2026. February of AVM-US is locked through the product (run 1
    journalises O1's February revenue), reopened by two approvals and soft-closed AGAIN: the
    period reads ``closing`` under its ``REOPEN`` record. Maya then records what was missing — O2
    complete on 27 Feb 2026 and INV-US-1044 — which posts 9,720.00 into February, and run 2
    journalises it. Every reader of the flag states the correction as post-reopen activity: the
    line read (``is_post_reopen``), the journal entry and the JE population (``is_post_close``,
    T-SL-08), and the two predicates of the approval rule.

    Until revision 0113 the guard stored ``state = 'reopened'``: these lines were stored false —
    "Post-reopen: No" on the line views — and the JE population listed run 2 as "Post-close: No",
    as the JE population frozen by the re-lock would have."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 2, 26))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: a journal run is hers to approve
    world = on_record_clock(world, clock)
    first, world = period_locked(world, clock, entity_code=AVM_US, period_key=FEBRUARY_2026)
    world = period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=FEBRUARY_2026,
        comment="Implementation completed on 27 Feb 2026 was not recorded.",
    )
    shown = period_shown(world, AVM_US, FEBRUARY_2026)
    state_id, period_id = UUID(str(shown["id"])), UUID(str(shown["period"]["id"]))
    started = post(
        app,
        f"{PERIODS}/{state_id}/start-close",
        world.maya,
        {"comment": "February close, again"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    shown = period_shown(world, AVM_US, FEBRUARY_2026)
    assert (shown["state"], shown["current_lock"]["kind"]) == (
        PeriodState.CLOSING.value,
        LockKind.REOPEN.value,
    )
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    scope = {"entity_id": world.entity_id, "book_code": BookCode.ASC606, "period_id": period_id}
    with tenant_session(context, read_only=True) as session:
        # the one reading of "locked once and not locked now", and the approval rule on it
        assert period_kernel.under_reopen(session, **scope) is True
        assert period_kernel.auto_approval_barred(session, **scope) is True
        assert posting_guard.posts_into_restricted_period(
            session,
            entity_id=world.entity_id,
            book_code=BookCode.ASC606,
            effective_date=date(2026, 2, 27),
        )

    contract_id = UUID(str(world.contracts[K01].contract["id"]))

    def february_lines() -> dict[str, tuple[str, bool]]:
        listed = get(
            app,
            "/api/v1/subledger-lines",
            world.maya,
            {"contract": str(contract_id), "period": FEBRUARY_2026, "book": "ASC606", "limit": 200},
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["next_cursor"] is None
        return {item["id"]: (item["posting_id"], item["is_post_reopen"]) for item in body["items"]}

    before = february_lines()
    assert before and {flag for _, flag in before.values()} == {False}  # posted before the lock
    # BUILD_SPEC CTR-6: the correction holds a progress event a person records, so Maya's
    # request waits whole (the invoice with it) and Priya's approval appends and computes it.
    corrected = approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "PROGRESS_RECORDED",
            "effective_date": "2026-02-27",
            "payload": {
                "obligation_key": "O2",
                "cumulative_progress_ratio": "1",
                "measure": "OUTPUT_PERCENT",
            },
        },
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-02-27",
            "payload": {
                "invoice_number": "INV-US-1044",
                "line_external_id": "INV-US-1044-1",
                "obligation_key": "O2",
                "amount": {"amount": "15000.00", "currency": "USD"},
                "issue_date": "2026-02-27",
            },
        },
    )
    assert corrected["computation"]["status"] == "SUCCEEDED", corrected["computation"]
    assert period_shown(world, AVM_US, FEBRUARY_2026)["state"] == PeriodState.CLOSING.value
    after = february_lines()
    posted = {line_id: found for line_id, found in after.items() if line_id not in before}
    # the line read: what was posted before the lock stays as it was; every February line of
    # the correction is a post-reopen line although the period reads ``closing``
    assert {line_id: after[line_id] for line_id in before} == before
    assert posted and {flag for _, flag in posted.values()} == {True}
    assert not {posting for posting, _ in posted.values()} & {p for p, _ in before.values()}

    second, world = posted_journal(world, clock, entity_code=AVM_US, period_key=FEBRUARY_2026)
    assert (first["run_no"], second["run_no"]) == ("JR-000001", "JR-000002")
    _, rows = report_run(
        world,
        "je_population",
        {
            "entity_codes": [AVM_US],
            "from_period_key": FEBRUARY_2026,
            "to_period_key": FEBRUARY_2026,
        },
    )
    # T-SL-08 through the JE population: the entry made of the correction is post-close
    assert {(row["run_no"], row["is_post_close"]) for row in rows} == {
        ("JR-000001", False),
        ("JR-000002", True),
    }
    assert {row["row_key"] for row in rows if row["run_no"] == "JR-000002"} == {
        "line:JE-AVM-US-000002:1",
        "line:JE-AVM-US-000002:2",
    }
    with tenant_session(context, read_only=True) as session:
        chain = subledger.verify_ledger_chain(session, book_code="ASC606")
    assert (chain.result, chain.first_failure_seq) == (ControlResult.PASS, None)


def _manual_task(
    world: CloseWorld, admin: Actor, *, owner_role_id: UUID | None = None
) -> dict[str, Any]:
    created = post(
        world.app,
        "/api/v1/close-checklist-templates",
        admin,
        {
            "code": "CONTROLLER-TASK",
            "name": "Controller close review",
            "gate_kind": "MANUAL",
            "is_blocking": True,
            "due_offset_days": 1,
            "owner_role_id": None if owner_role_id is None else str(owner_role_id),
        },
    )
    assert created.status_code == 201, created.text
    return _shown_task(world)


def _shown_task(world: CloseWorld) -> dict[str, Any]:
    response = get(world.app, f"{PERIODS}/{world.state_id}/cockpit", world.maya)
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["checklist"] if item["code"] == "CONTROLLER-TASK")


def _sign_task(world: CloseWorld, signer: Actor, task: dict[str, Any]) -> Any:
    state = _state(world)
    return post(
        world.app,
        f"{PERIODS}/{world.state_id}/checklist/{task['id']}/sign",
        signer,
        {"statement_accepted": True},
        if_match=f'"r{state["row_version"]}"',
    )


@pytest.mark.parametrize("assignment", ["none", "other_entity", "this_entity", "all_entities"])
def test_task_signer_holds_owner_role_for_period_entity(
    world: CloseWorld, clock: FrozenClock, assignment: str
) -> None:
    from erev_api.db.tables import role, signoff

    admin = actor_with_role(world.app, clock, world.tenant_id, "tenant_admin", name="task-admin")
    with system_session(world) as session:
        owner = session.execute(select(role.c.id).where(role.c.code == "controller")).scalar_one()
        other = other_entity(session, world)
    task = _manual_task(world, admin, owner_role_id=owner)
    candidate = colleague(world.tenant_id, "task-signer")
    assign(candidate, "revenue_accountant")  # permission for the period is insufficient by itself
    if assignment != "none":
        ids = {"other_entity": [other], "this_entity": [world.entity_id], "all_entities": []}
        assign(candidate, "controller", entity_ids=ids[assignment])
    signer = enrolled(world.app, clock, candidate)
    result = _sign_task(world, signer, task)
    expected = 200 if assignment in {"this_entity", "all_entities"} else 403
    assert result.status_code == expected, result.text
    with system_session(world) as session:
        count = session.execute(
            select(func.count())
            .select_from(signoff)
            .where(signoff.c.subject_id == UUID(task["id"]))
        ).scalar_one()
    assert count == (1 if expected == 200 else 0)
    assert _shown_task(world)["status"] == ("PASSED" if expected == 200 else "NOT_STARTED")


def test_reopen_requires_new_task_signoff_and_preserves_history(
    world: CloseWorld, clock: FrozenClock
) -> None:
    from erev_api.db.tables import signoff

    admin = actor_with_role(world.app, clock, world.tenant_id, "tenant_admin", name="task-admin")
    signer = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_accountant", name="task-signer"
    )
    task = _manual_task(world, admin)
    first = _sign_task(world, signer, task)
    assert first.status_code == 200, first.text
    with system_session(world) as session:
        old = dict(
            session.execute(select(signoff).where(signoff.c.subject_id == UUID(task["id"])))
            .mappings()
            .one()
        )
    _lock_by_writer(world)
    priya = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="task-priya"
    )
    marcus = actor_with_role(world.app, clock, world.tenant_id, "controller", name="task-marcus")
    elena = actor_with_role(world.app, clock, world.tenant_id, "controller", name="task-elena")
    request = _request_reopen(world, priya)
    assert request.status_code == 200, request.text
    request_id = str(request.json()["approval_request_id"])
    assert approve(world.app, request_id, marcus).status_code == 200
    assert _shown_task(world)["status"] == "PASSED"  # first approval alone does not reopen
    second = approve(world.app, request_id, elena)
    assert second.status_code == 200, second.text
    reset = _shown_task(world)
    assert (reset["status"], reset["signoff"]) == ("NOT_STARTED", None)
    with system_session(world) as session:
        scope = _scope(session, world.state_id)
        assert "CONTROLLER-TASK" in {
            item.code for item in gates.unsigned_blocking_tasks(session, scope)
        }
        assert (
            dict(session.execute(select(signoff).where(signoff.c.id == old["id"])).mappings().one())
            == old
        )
        cleared = (
            session.execute(
                select(audit_event).where(
                    audit_event.c.object_id == UUID(task["id"]),
                    audit_event.c.action == close_commands.SIGNOFF_CLEARED_ACTION,
                )
            )
            .mappings()
            .one()
        )
        assert cleared["approval_request_id"] == UUID(request_id)
    signed_again = _sign_task(world, signer, reset)
    assert signed_again.status_code == 200, signed_again.text
    with system_session(world) as session:
        rows = list(
            session.execute(
                select(signoff).where(signoff.c.subject_id == UUID(task["id"]))
            ).mappings()
        )
        assert len(rows) == 2
        assert len({row["subject_content_sha256"] for row in rows}) == 2
        assert {row["signer_id"] for row in rows} == {signer.member.user_id}
        assert gates.unsigned_blocking_tasks(session, _scope(session, world.state_id)) == ()
    assert _sign_task(world, signer, reset).status_code == 409


def test_closed_period_cannot_receive_a_new_task_signature(
    world: CloseWorld, clock: FrozenClock
) -> None:
    admin = actor_with_role(world.app, clock, world.tenant_id, "tenant_admin", name="task-admin")
    signer = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_accountant", name="task-signer"
    )
    task = _manual_task(world, admin)
    _lock_by_writer(world)
    refused = _sign_task(world, signer, task)
    assert refused.status_code == 409, refused.text
    assert _shown_task(world)["signoff"] is None


@pytest.mark.parametrize(
    "citation_kind",
    [
        "missing",
        "unknown",
        "draft",
        "submitted",
        "superseded",
        "wrong_topic",
        "wrong_book",
        "other_entity",
        "other_tenant",
    ],
)
def test_error_correction_reopen_requires_reviewed_evidence(
    world: CloseWorld,
    clock: FrozenClock,
    keyring: KeyRing,
    files: LocalFileStore,
    citation_kind: str,
) -> None:
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    _lock_by_writer(world)
    before = _state(world)
    citation = None
    if citation_kind == "unknown":
        citation = new_id()
    elif citation_kind == "draft":
        citation = _reviewed_error_judgement(
            world, status="DRAFT", reviewer_id=None, reviewed_at=None
        )
    elif citation_kind in {"submitted", "superseded"}:
        citation = _reviewed_error_judgement(world, status=citation_kind.upper())
    elif citation_kind == "wrong_topic":
        citation = _reviewed_error_judgement(world, topic="PRINCIPAL_AGENT")
    elif citation_kind == "wrong_book":
        citation = _reviewed_error_judgement(world, book_code="IFRS15")
    elif citation_kind == "other_entity":
        from support.close_world import other_entity

        with system_session(world) as session:
            entity_id = other_entity(session, world)
            contract_id, _, _ = contract_of(session, world, entity_id)
        citation = _reviewed_error_judgement(world, contract_id=contract_id, subject_id=contract_id)
    elif citation_kind == "other_tenant":
        other = close_world(world.app, keyring, clock, files)
        citation = _reviewed_error_judgement(other)
    response = post(
        world.app,
        f"{PERIODS}/{world.state_id}/request-reopen",
        requester,
        {
            "reason_code": "ERROR_CORRECTION",
            "comment": REASON,
            "judgement_record_id": None if citation is None else str(citation),
        },
        if_match=f'"r{before["row_version"]}"',
    )
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["rule_id"] == "REOPEN_REVIEWED_JUDGEMENT"
    after = _state(world)
    assert (after["state"], after["row_version"]) == ("closed", before["row_version"])
    assert len(_locks(world)) == 1


def test_reopen_history_keeps_the_reviewed_citation(world: CloseWorld, clock: FrozenClock) -> None:
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    _lock_by_writer(world)
    first = actor_with_role(world.app, clock, world.tenant_id, "controller", name="first")
    second = actor_with_role(world.app, clock, world.tenant_id, "controller", name="second")
    requested = _request_reopen(world, requester)
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    with system_session(world) as session:
        citation = session.execute(
            select(period_reopen_basis.c.judgement_record_id).where(
                period_reopen_basis.c.period_state_id == world.state_id
            )
        ).scalar_one()
    assert citation is not None
    shown = get(world.app, f"/api/v1/approvals/{request_id}", first)
    assert shown.status_code == 200, shown.text
    assert shown.json()["reopen_judgement"]["id"] == str(citation)
    assert shown.json()["reopen_judgement"]["reviewer"]["id"] == str(world.maya.member.user_id)
    assert approve(world.app, request_id, first).status_code == 200
    response = approve(world.app, request_id, second)
    assert response.status_code == 200, response.text
    lock, reopen = _locks(world)
    assert lock["judgement_record_id"] is None
    assert reopen["judgement_record_id"] == citation
    listed = get(world.app, f"{PERIODS}/{world.state_id}/locks", world.maya)
    assert listed.status_code == 200, listed.text
    assert any(row["judgement_record_id"] == str(citation) for row in listed.json()["items"])


@pytest.mark.parametrize("after_first", [False, True])
def test_superseded_citation_voids_reopen_before_any_period_change(
    world: CloseWorld, clock: FrozenClock, after_first: bool
) -> None:
    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    first = actor_with_role(world.app, clock, world.tenant_id, "controller", name="first")
    second = actor_with_role(world.app, clock, world.tenant_id, "controller", name="second")
    requested = _request_reopen(world, requester)
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    if after_first:
        assert approve(world.app, request_id, first).status_code == 200
    with system_session(world) as session:
        citation = session.execute(
            select(period_reopen_basis.c.judgement_record_id).where(
                period_reopen_basis.c.period_state_id == world.state_id
            )
        ).scalar_one()
        session.execute(
            update(judgement_record)
            .where(judgement_record.c.id == citation)
            .values(status="SUPERSEDED")
        )
    refused = approve(world.app, request_id, second)
    assert (refused.status_code, slug(refused)) == (409, "stale-approval"), refused.text
    assert _request_status(world, request_id) == "VOIDED"
    assert _state(world)["state"] == "closed"
    assert len(_locks(world)) == 1


def test_legacy_error_reopen_without_a_citation_cannot_complete(
    world: CloseWorld, clock: FrozenClock
) -> None:
    _lock_by_writer(world)
    first = actor_with_role(world.app, clock, world.tenant_id, "controller", name="first")
    second = actor_with_role(world.app, clock, world.tenant_id, "controller", name="second")
    # A request created before 0137: the ordinary kernel basis, with no citation on the state.
    with world.place.uow() as uow:
        request = approvals.submit(
            uow,
            subject_type=ApprovalSubjectType.PERIOD_REOPEN,
            subject_id=world.state_id,
            summary="Legacy error correction",
            comment=REASON,
            reason_code="ERROR_CORRECTION",
            auto_approval=False,
        )
        request_id = str(request["id"])
        uow.commit()
    assert approve(world.app, request_id, first).status_code == 200
    refused = approve(world.app, request_id, second)
    assert (refused.status_code, slug(refused)) == (409, "stale-approval"), refused.text
    assert _request_status(world, request_id) == "VOIDED"
    assert _state(world)["state"] == "closed"
    assert len(_locks(world)) == 1


def test_second_reopen_request_cannot_replace_the_pending_citation(
    world: CloseWorld, clock: FrozenClock
) -> None:
    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    first = _request_reopen(world, requester)
    assert first.status_code == 200, first.text
    before = _state(world)
    with system_session(world) as session:
        original = session.execute(
            select(period_reopen_basis.c.judgement_record_id).where(
                period_reopen_basis.c.period_state_id == world.state_id
            )
        ).scalar_one()
    refused = _request_reopen(world, requester)
    assert refused.status_code == 409, refused.text
    assert _state(world)["row_version"] == before["row_version"]
    with system_session(world) as session:
        assert (
            session.execute(
                select(period_reopen_basis.c.judgement_record_id).where(
                    period_reopen_basis.c.period_state_id == world.state_id
                )
            ).scalar_one()
            == original
        )


@pytest.mark.parametrize("history", [False, True])
def test_citation_migration_refuses_loss_outside_the_owners_tenant_scope(
    world: CloseWorld, clock: FrozenClock, committed_db: TestDatabase, history: bool
) -> None:
    from importlib import import_module

    from erev_api.db import migration_ops
    from sqlalchemy.exc import DBAPIError

    migration = import_module("erev_api.db.migrations.versions.0137_reopen_judgement_citations")
    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    requested = _request_reopen(world, requester)
    assert requested.status_code == 200, requested.text
    if history:
        for name in ("first", "second"):
            reviewer = actor_with_role(world.app, clock, world.tenant_id, "controller", name=name)
            assert (
                approve(world.app, requested.json()["approval_request_id"], reviewer).status_code
                == 200
            )
        with system_session(world) as session:
            session.execute(
                update(period_reopen_basis)
                .where(period_reopen_basis.c.period_state_id == world.state_id)
                .values(judgement_record_id=None)
            )
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with migration_ops.bound_to(connection), pytest.raises(DBAPIError) as error:
                migration.downgrade()
            assert getattr(error.value.orig, "sqlstate", None) == "23514"
        finally:
            transaction.rollback()
    with system_session(world) as session:
        if history:
            assert (
                session.execute(
                    select(period_lock.c.judgement_record_id).where(period_lock.c.kind == "REOPEN")
                ).scalar_one()
                is not None
            )
        else:
            assert (
                session.execute(
                    select(period_reopen_basis.c.judgement_record_id).where(
                        period_reopen_basis.c.period_state_id == world.state_id
                    )
                ).scalar_one()
                is not None
            )


def test_reopen_picker_filters_reviewed_topic_entity_and_applicable_book(world: CloseWorld) -> None:
    from support.close_world import other_entity

    specific = _reviewed_error_judgement(world)
    all_books = _reviewed_error_judgement(world, book_code=None)
    _reviewed_error_judgement(world, book_code="IFRS15")
    _reviewed_error_judgement(world, topic="PRINCIPAL_AGENT")
    _reviewed_error_judgement(world, status="DRAFT", reviewer_id=None, reviewed_at=None)
    with system_session(world) as session:
        other = other_entity(session, world)
        contract_id, _, _ = contract_of(session, world, other)
    _reviewed_error_judgement(world, contract_id=contract_id, subject_id=contract_id)
    response = get(
        world.app,
        "/api/v1/judgements",
        world.maya,
        {
            "topic": "ESTIMATE_VS_ERROR",
            "status": "REVIEWED",
            "entity_id": str(world.entity_id),
            "book": "ASC606",
        },
    )
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["items"]} == {str(specific), str(all_books)}


def test_reopen_evidence_is_inaccessible_after_its_preparer_loses_entity_scope(
    world: CloseWorld, clock: FrozenClock
) -> None:
    from erev_api.db.tables import role_assignment
    from support.close_world import other_entity

    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    requested = _request_reopen(world, requester)
    assert requested.status_code == 200, requested.text
    path = f"/api/v1/approvals/{requested.json()['approval_request_id']}"
    original = get(world.app, path, requester)
    assert original.status_code == 200, original.text
    evidence = original.json()["reopen_judgement"]
    assert evidence is not None
    with system_session(world) as session:
        other = other_entity(session, world)
        session.execute(
            update(role_assignment)
            .where(
                role_assignment.c.membership_id == requester.member.membership_id,
                role_assignment.c.revoked_at.is_(None),
            )
            .values(revoked_at=clock.now(), revoked_by_kind="SYSTEM")
        )
    assign(requester.member, "revenue_reviewer", entity_ids=[other])
    hidden = get(world.app, path, requester)
    # This single-entity request is outside every remaining grant: even its header
    # is inaccessible. Partial-scope headers are covered by the approval API suite.
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    assert evidence["id"] not in hidden.text
    assert evidence["judgement_no"] not in hidden.text
    assert evidence["rationale"] not in hidden.text


def test_a_later_request_does_not_replace_the_earlier_requests_submitted_evidence(
    world: CloseWorld, clock: FrozenClock
) -> None:
    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    requested = _request_reopen(world, requester)
    assert requested.status_code == 200, requested.text
    path = f"/api/v1/approvals/{requested.json()['approval_request_id']}"
    original = get(world.app, path, requester).json()["reopen_judgement"]
    withdrawn = post(
        world.app,
        f"{path}/withdraw",
        requester,
        {"comment": "Replace the evidence with the subsequent reviewed conclusion."},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    later = _request_reopen(world, requester)
    assert later.status_code == 200, later.text
    new_path = f"/api/v1/approvals/{later.json()['approval_request_id']}"
    assert get(world.app, new_path, requester).json()["reopen_judgement"]["id"] != original["id"]
    assert get(world.app, path, requester).json()["reopen_judgement"] == original


def test_a_busy_judgement_retries_the_final_reopen_decision_without_voiding_it(
    world: CloseWorld, clock: FrozenClock
) -> None:
    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    first = actor_with_role(world.app, clock, world.tenant_id, "controller", name="first")
    second = actor_with_role(world.app, clock, world.tenant_id, "controller", name="second")
    requested = _request_reopen(world, requester)
    assert requested.status_code == 200, requested.text
    request_id = requested.json()["approval_request_id"]
    assert approve(world.app, request_id, first).status_code == 200
    with system_session(world) as writer:
        citation = writer.execute(
            select(period_reopen_basis.c.judgement_record_id).where(
                period_reopen_basis.c.period_state_id == world.state_id
            )
        ).scalar_one()
        writer.execute(
            select(judgement_record.c.id).where(judgement_record.c.id == citation).with_for_update()
        ).one()
        busy = approve(world.app, request_id, second)
        assert (busy.status_code, slug(busy)) == (409, "invalid-transition"), busy.text
        assert _request_status(world, request_id) == "PENDING"
        assert _state(world)["state"] == "closed"
        assert len(_locks(world)) == 1
    approved = approve(world.app, request_id, second)
    assert approved.status_code == 200, approved.text
    assert _state(world)["state"] == "reopened"


def test_non_error_reopen_refuses_an_irrelevant_citation(
    world: CloseWorld, clock: FrozenClock
) -> None:
    _lock_by_writer(world)
    requester = actor_with_role(
        world.app, clock, world.tenant_id, "revenue_reviewer", name="requester"
    )
    citation = _reviewed_error_judgement(world)
    before = _state(world)
    response = post(
        world.app,
        f"{PERIODS}/{world.state_id}/request-reopen",
        requester,
        {
            "reason_code": "LATE_SOURCE_DATA",
            "comment": REASON,
            "judgement_record_id": str(citation),
        },
        if_match=f'"r{before["row_version"]}"',
    )
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["rule_id"] == "REOPEN_JUDGEMENT_REASON"
    assert _state(world)["row_version"] == before["row_version"]
