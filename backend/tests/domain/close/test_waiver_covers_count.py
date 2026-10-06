"""A waiver of a close gate covers the count it was approved for, on a database (item
CLO-WAIVER-COVERS-LATER-1 — PRODUCT DEFECT, a release blocker; the supervisor's ruling of
2026-10-02 17:32; 04 T-CLS-03 rev 1.305; PRD BR-CLS-01 rev 1.202; revision 0130).

MEASURED before the item, in the close world: ``EXCEPTIONS_CLEARED`` failed at count 1 and its
waiver was asked for; a second exception arrived and the waiver was approved all the same; two
more arrived and the item stayed ``WAIVED``; the lock was requested and approved, and its
certification stores the gate ``WAIVED`` with count 4 and waived count 2. And a waiver given
before a lock stayed ``WAIVED`` through the period's reopen, whatever arrived after it.

- The request carries the count and the gate's sentence: a count that moves before the decision
  makes the request stale by the kernel's own rule.
- More than was waived: the gate fails again with the count that stands, its sentence and "The
  waiver <request no> covered <m>."; the lock request is refused, and so is the decision of a
  request made before the count grew; a waiver of what stands clears.
- A reopen ends the waivers of the close it reopens; the lock reopened keeps what it certified.
- A waiver's lapse is on the audit trail whoever stores it: a read that is the first to count
  more writes that one event as SYSTEM, a command writes it as its caller (the supervisor's
  ruling of 2026-10-02 20:22 — the one exception to "a read appends no audit event", R-32).

DB-bound (``support.close_world``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, exception_item
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.close_world import (
    CloseWorld,
    acknowledged_run,
    actor_with_role,
    close_run_succeeded,
    close_world,
    earlier_periods_closed,
    reviewed_reconciliations,
    system_session,
)
from support.db import TestDatabase
from support.principals import Actor
from support.reference import PERIODS, approve, get, periods, post, slug
from support.rows import exception_item_values

GATE = "EXCEPTIONS_CLEARED"
SEPTEMBER = "FY2026-P09"
REASON = "Accepted by the controller for this period."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _state(world: CloseWorld) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == SEPTEMBER
    ]
    return dict(found)


def _command(world: CloseWorld, actor: Actor, path: str, body: dict[str, Any]) -> Any:
    shown = _state(world)
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/{path}",
        actor,
        body,
        if_match=f'"r{shown["row_version"]}"',
    )


def _in_soft_close_with_every_other_gate_green(world: CloseWorld) -> None:
    earlier_periods_closed(world)
    started = _command(world, world.maya, "start-close", {"comment": "September close"})
    assert started.status_code == 200, started.text
    with system_session(world) as session:
        acknowledged_run(session, world)
        reviewed_reconciliations(session, world)
        close_run_succeeded(session, world)


def _exception(world: CloseWorld) -> None:
    with system_session(world) as session:
        session.execute(
            insert(exception_item).values(
                **exception_item_values(world.tenant_id, entity_id=world.entity_id)
            )
        )


def _gate(world: CloseWorld) -> dict[str, Any]:
    """The gate's row as the cockpit serves it (the read brings the stored row up to date)."""
    shown = get(world.app, f"{PERIODS}/{world.state_id}/cockpit", world.maya)
    assert shown.status_code == 200, shown.text
    (row,) = [item for item in shown.json()["checklist"] if item["code"] == GATE]
    return dict(row)


def _read(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["status"],
        row["result"]["count"],
        row["result"]["detail"],
        row["waiver_approval_request_id"] is not None,
    )


def _waiver_asked(world: CloseWorld) -> dict[str, Any]:
    asked = _command(world, world.maya, f"checklist/{_gate(world)['id']}/waive", {"reason": REASON})
    assert asked.status_code == 200, asked.text
    return dict(asked.json())


def test_a_waiver_covers_the_count_it_was_approved_for(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """The measured sequence. A waiver asked at count 1 is stale once a second exception stands:
    its decision answers 409 ``stale-approval`` and the request is void. Asked again at 2 and
    approved, the gate is ``WAIVED``, 2. Two more arrive: the gate is ``FAILED`` with 4 and "Open
    exceptions: 4 The waiver <request no> covered 2.", the item names no request, and the lock
    request is refused by the gate's name with that sentence. A waiver of what stands, approved,
    clears it, and the lock's certification states ``WAIVED`` with count 4 and waived count 4.

    Fail-first (measured before the item): the first decision was approved at count 2, the item
    stayed ``WAIVED`` at 4 and the lock went through with count 4, waived count 2."""
    app = world.app
    _in_soft_close_with_every_other_gate_green(world)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    _exception(world)
    assert _read(_gate(world)) == ("FAILED", 1, "Open exceptions: 1", False)
    first = _waiver_asked(world)

    _exception(world)  # the count moves before the decision
    assert _read(_gate(world)) == ("FAILED", 2, "Open exceptions: 2", True)
    stale = approve(app, str(first["approval_request_id"]), priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    assert _read(_gate(world)) == ("FAILED", 2, "Open exceptions: 2", False)

    second = _waiver_asked(world)  # asked for what stands, and approved
    decided = approve(app, str(second["approval_request_id"]), priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _read(_gate(world)) == ("WAIVED", 2, "Open exceptions: 2", True)

    _exception(world)
    _exception(world)  # more than was waived
    covered = f"Open exceptions: 4 The waiver {second['request_no']} covered 2."
    assert _read(_gate(world)) == ("FAILED", 4, covered, False)
    refused = _command(
        world, world.maya, "request-lock", {"certification_comment": "September 2026 complete"}
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert (GATE, covered) in [
        (error["rule_id"], error["message"]) for error in refused.json()["errors"]
    ]

    third = _waiver_asked(world)  # a waiver of what stands
    again = approve(app, str(third["approval_request_id"]), priya)
    assert (again.status_code, again.json()["status"]) == (200, "APPROVED"), again.text
    assert _read(_gate(world))[:2] == ("WAIVED", 4)
    requested = _command(
        world, world.maya, "request-lock", {"certification_comment": "September 2026 complete"}
    )
    assert requested.status_code == 200, requested.text
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    locked = approve(app, str(requested.json()["approval_request_id"]), cora)
    assert (locked.status_code, locked.json()["status"]) == (200, "APPROVED"), locked.text
    listed = get(app, f"{PERIODS}/{world.state_id}/locks", world.maya)
    (certified,) = [
        (row["status"], row["count"], row["waived_count"], row["waiver_approval_request_no"])
        for row in listed.json()["items"][0]["certification"]
        if row["gate_check_code"] == GATE
    ]
    assert certified == ("WAIVED", 4, 4, third["request_no"])


def test_the_decision_refuses_a_gate_that_outgrew_its_waiver_after_the_request(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """The lock is requested over a gate waived at count 1, and a second exception arrives before
    the Controller decides. The decision answers 409 ``close-gates-failed`` by the gate's name
    with "Open exceptions: 2 The waiver <request no> covered 1."; the period stays in its soft
    close and no lock record is written. A waiver of what stands, approved, lets the same
    Controller decide the same request: the certification states ``WAIVED``, count 2, waived
    count 2 and the second waiver.

    Fail-first (the witness of R-55 (b) before the item): the decision was approved over the
    first waiver and the certification stored ``WAIVED`` with count 2 and waived count 1."""
    app = world.app
    _in_soft_close_with_every_other_gate_green(world)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    _exception(world)
    first = _waiver_asked(world)
    assert approve(app, str(first["approval_request_id"]), priya).status_code == 200
    requested = _command(
        world, world.maya, "request-lock", {"certification_comment": "September 2026 complete"}
    )
    assert requested.status_code == 200, requested.text
    lock_request = str(requested.json()["approval_request_id"])

    _exception(world)  # after the request, before the decision
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    covered = f"Open exceptions: 2 The waiver {first['request_no']} covered 1."
    refused = approve(app, lock_request, cora)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
        (GATE, covered)
    ]
    assert _state(world)["state"] == "closing"
    assert get(app, f"{PERIODS}/{world.state_id}/locks", world.maya).json()["items"] == []
    assert _read(_gate(world)) == ("FAILED", 2, covered, False)

    second = _waiver_asked(world)  # a waiver of what stands; the lock request is still pending
    assert approve(app, str(second["approval_request_id"]), priya).status_code == 200
    decided = approve(app, lock_request, cora)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _state(world)["state"] == "closed"
    listed = get(app, f"{PERIODS}/{world.state_id}/locks", world.maya)
    (certified,) = [
        (row["status"], row["count"], row["waived_count"], row["waiver_approval_request_no"])
        for row in listed.json()["items"][0]["certification"]
        if row["gate_check_code"] == GATE
    ]
    assert certified == ("WAIVED", 2, 2, second["request_no"])


EVALUATE = "close_checklist_item.evaluate"
ASKED = "close_checklist_item.request_waiver"
WAIVE = "close_checklist_item.waive"


def _trail(world: CloseWorld, item_id: UUID) -> list[tuple[Any, ...]]:
    """The audit events of a checklist item in chain order: the action, who wrote it, what it
    states before and after, and the approval request it is linked to."""
    with system_session(world) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.actor_kind,
                audit_event.c.before,
                audit_event.c.after,
                audit_event.c.approval_request_id,
            )
            .where(audit_event.c.object_id == item_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (
            str(action),
            str(getattr(kind, "value", kind)),
            before,
            after,
            None if request is None else str(request),
        )
        for action, kind, before, after, request in rows
    ]


def _lapse(waiver_id: str, covered: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """What the event of a lapse states: the item ``WAIVED`` at 1 under its request, then
    ``FAILED`` at 2 with the sentence and no request; linked to the request that lapsed."""
    return (
        {
            "status": "WAIVED",
            "count": 1,
            "detail": "Open exceptions: 1",
            "waiver_approval_request_id": waiver_id,
        },
        {"status": "FAILED", "count": 2, "detail": covered, "waiver_approval_request_id": None},
        waiver_id,
    )


def test_a_waivers_lapse_is_audited_when_a_read_is_the_first_to_count_more(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """A read stores what it evaluates without an audit event (security finding SC-8, ruling
    R-32) — the gate's first result of this world, ``FAILED`` at 1, is stored by a cockpit read
    and leaves none. One move is on the trail whoever stores it (the supervisor's ruling of
    2026-10-02 20:22): a waiver's lapse. A second exception arrives behind a gate waived at 1 and
    a cockpit read is the first to count it: the item goes ``WAIVED`` to ``FAILED`` and ONE event
    says so, written as SYSTEM, naming the request that lapsed and linked to it. It is bounded: a
    second read and a refused lock request add nothing.

    Fail-first (measured before the ruling was built): the read moved the item and added no
    event, and the refused request and the next waiver's request added none of the move."""
    app = world.app
    _in_soft_close_with_every_other_gate_green(world)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    _exception(world)
    item_id = UUID(str(_gate(world)["id"]))
    waiver = _waiver_asked(world)
    assert approve(app, str(waiver["approval_request_id"]), priya).status_code == 200
    waiver_id = str(UUID(str(waiver["approval_request_id"])))
    before = _trail(world, item_id)
    # the first result, FAILED at 1, was stored by the read: no ``evaluate`` event of it
    assert [(action, who) for action, who, *_ in before] == [(ASKED, "USER"), (WAIVE, "USER")]

    _exception(world)
    covered = f"Open exceptions: 2 The waiver {waiver['request_no']} covered 1."
    assert _read(_gate(world)) == ("FAILED", 2, covered, False)
    assert _trail(world, item_id)[len(before) :] == [
        (EVALUATE, "SYSTEM", *_lapse(waiver_id, covered))
    ]

    assert _read(_gate(world)) == ("FAILED", 2, covered, False)  # a second read
    refused = _command(
        world, world.maya, "request-lock", {"certification_comment": "September 2026 complete"}
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert len(_trail(world, item_id)) == len(before) + 1


def test_a_waivers_lapse_is_audited_when_a_command_is_the_first_to_count_more(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """The same lapse with no read in between: the accountant asks for a waiver of what stands,
    and the command's own evaluation moves the item. The same event with the same content,
    written by her, in front of the event of her request."""
    app = world.app
    _in_soft_close_with_every_other_gate_green(world)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    _exception(world)
    item_id = UUID(str(_gate(world)["id"]))
    waiver = _waiver_asked(world)
    assert approve(app, str(waiver["approval_request_id"]), priya).status_code == 200
    waiver_id = str(UUID(str(waiver["approval_request_id"])))
    before = _trail(world, item_id)

    _exception(world)  # no read: the waive command is the first to evaluate
    covered = f"Open exceptions: 2 The waiver {waiver['request_no']} covered 1."
    asked = _command(world, world.maya, f"checklist/{item_id}/waive", {"reason": REASON})
    assert asked.status_code == 200, asked.text
    added = _trail(world, item_id)[len(before) :]
    assert [(action, who) for action, who, *_ in added] == [(EVALUATE, "USER"), (ASKED, "USER")]
    assert added[0][2:] == _lapse(waiver_id, covered)
    assert _read(_gate(world)) == ("FAILED", 2, covered, True)


def test_a_reopen_ends_the_waivers_of_the_close_it_reopens(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """A gate waived at count 1 and the period locked on it. The reopen — asked by a Revenue
    Reviewer, approved by two Controllers — returns the item to ``NOT_STARTED`` with no request;
    the next evaluation states what stands, ``FAILED`` at 1, and the lock asked again is refused
    by the gate. The lock that was reopened keeps what it certified: ``WAIVED``, count 1, waived
    count 1, its request.

    Fail-first (measured before the item): after the reopen the item read ``WAIVED``, 1, and the
    lock request was refused on the reconciliations alone."""
    app = world.app
    _in_soft_close_with_every_other_gate_green(world)
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    _exception(world)
    waiver = _waiver_asked(world)
    assert approve(app, str(waiver["approval_request_id"]), priya).status_code == 200
    requested = _command(
        world, world.maya, "request-lock", {"certification_comment": "September 2026 complete"}
    )
    assert requested.status_code == 200, requested.text
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    assert approve(app, str(requested.json()["approval_request_id"]), cora).status_code == 200

    asked = _command(
        world,
        priya,
        "request-reopen",
        {"reason_code": "ERROR_CORRECTION", "comment": "Costs of September were omitted."},
    )
    assert asked.status_code == 200, asked.text
    dana = actor_with_role(app, clock, world.tenant_id, "controller", name="dana")
    for approver in (cora, dana):
        assert approve(app, str(asked.json()["approval_request_id"]), approver).status_code == 200
    assert _state(world)["state"] == "reopened"
    assert _read(_gate(world)) == ("FAILED", 1, "Open exceptions: 1", False)

    restarted = _command(world, world.maya, "start-close", {"comment": "September close again"})
    assert restarted.status_code == 200, restarted.text
    with system_session(world) as session:
        reviewed_reconciliations(session, world)
    refused = _command(
        world, world.maya, "request-lock", {"certification_comment": "September 2026 complete"}
    )
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert [error["rule_id"] for error in refused.json()["errors"]] == [GATE]
    listed = get(app, f"{PERIODS}/{world.state_id}/locks", world.maya)
    (first_lock,) = [item for item in listed.json()["items"] if item["kind"] == "LOCK"]
    (certified,) = [
        (row["status"], row["count"], row["waived_count"], row["waiver_approval_request_id"])
        for row in first_lock["certification"]
        if row["gate_check_code"] == GATE
    ]
    assert certified == ("WAIVED", 1, 1, str(UUID(str(waiver["approval_request_id"]))))
