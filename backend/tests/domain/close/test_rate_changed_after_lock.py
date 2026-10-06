"""A rate changed after a lock (item CLO-RATE-AFTER-RUN-1, second part; the supervisor's rulings
of 2026-10-02 08:56, point 4, and 11:08; 04 §15.4, T-REF-11 "A rate changed after a lock" and
§16.8, rev 1.291; PRD IMP-144, BR-DAT-04; BUILD_SPEC CLO-20).

The gate of the first part asks a period that can still be run for another run. A period that is
``closed`` or ``permanently_locked`` takes none: the next postable period's run posts the
difference as an amount of its own. Measured before the item, in the world of this module: after
the closing rate of a locked August was corrected from 1.105000 to 1.115000 nothing was raised,
and September's run posted August's 100.00 with its own 50.00, in one amount without an origin.

So the approval of a rate set version raises, in its own transaction, ONE ``WARNING`` exception
item of source ``CLOSE`` per entity, book and period that is closed and holds a date whose rate
the version changes — an item of the period the difference posts to, so that period's cockpit
shows it and its lock waits for one of two roads: the reopen of the closed period, whose decision
settles the item, or the waiver of PRD SM-06.

And the approval reads the period states ``FOR SHARE``, while the gate reads the rates whenever
their version was published: a lock decision in flight either ends first, and the approval then
reads the period ``closed``, or evaluates after the approval's commit and reads the version.
Without the two, a decision that had judged its gates closed the period on the old rate while
the approval read it ``closing`` — neither the gate nor a finding.

World: ``close_run_worlds.eur_receivable`` — AVM-US (USD) with one EUR contract, EUR 10,000.00
delivered on 31 Aug 2026 and never invoiced; the PRD §2.5 rates (August average 1.100000 and
closing 1.105000; September closing 1.120000). Expected amounts are the documents': the
receivable stands at USD 11,000.00; at the closing rate 1.105000 it is 11,050.00, a
remeasurement of 50.00; at September's 1.120000 it is 11,200.00 — 200.00 in all, of which
September's run posts the 150.00 August's did not.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api import problems
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_request,
    audit_event,
    exception_item,
    fx_rate_set_version,
    legal_entity,
    notification,
    period,
    period_state,
    subledger_line,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.domain.contracts import bundles
from erev_api.enums import ApprovalSubjectType
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import and_, select
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.close_world import actor_with_role, periods_closed_before
from support.db import TestDatabase
from support.factories import open_periods
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import PERIODS, approve, entity, get, post, slug

AVM_US, AVM_DE = worlds.AVM_US, "AVM-DE"
JULY, AUGUST, SEPTEMBER = "FY2026-P07", "FY2026-P08", "FY2026-P09"
FX = "FX_REMEASUREMENT"
CODE = "FX_RATE_CHANGED_AFTER_LOCK"
EXCEPTIONS = "/api/v1/exceptions"
RUN_GATE, EXCEPTIONS_GATE = gates.CLOSE_RUN_COMPLETED, gates.EXCEPTIONS_CLEARED
# Item FX-REPUBLISH-DIRTY-1 (04 T-REF-11 "The groups a changed rate reaches", rev 1.297): the
# approval of the corrected version marks the group of SF-ORD-EU-3001 — its unbilled receivable
# is a position in the reach of August's closing rate — and a lock decision that reads what is
# committed is held by the gate of the marked contract beside the close run's, until a run has
# recomputed it.
DIRTY_GATE = gates.NO_DIRTY_GROUPS
MARKED = "Contracts changed since the last close run: 1"
CORRECTED = "1.115000"  # the closing rate of August as corrected; it was 1.105000
RATES_CHANGED = (
    "Close run out of date, run it again: exchange rates changed since it ran. A run posts "
    "nothing where the change moves nothing for this entity."
)
# PRD IMP-144, in its parts.
POSTED = (
    " The difference is not computed here. What remains of it to post goes to FY2026-P09. The "
    "contracts the changed rates reach are recalculated by the next close run of their "
    "contracting entity or by the next change to them: what the rates change in the amounts of "
    "their events is posted with the closed period of each event as origin period, and the "
    "out-of-period register lists it as Fx republish or with the event that carried it. The close "
    "run of FY2026-P09 posts what remains of a period-end remeasurement as an amount of that "
    "period, without an origin period. Where nothing remains nothing is posted: a closing rate of "
    "a period that is followed by another closed period moves an amount between the two for a "
    "balance open through both."
)
REOPEN_OR_ACCEPT = " Reopen the period to restate it, or request a waiver to accept the difference."
LATER_FIRST = (
    " To restate it, reopen the later closed periods first and then this one; or request a "
    "waiver to accept the difference."
)
ACCEPT_ONLY = " The period cannot be reopened. Request a waiver to accept the difference."
AUGUST_CHANGED = "EUR/USD closing rate of 2026-08-31 from 1.105 to 1.115."
WAIT_SECONDS = 8.0  # under the sessions' lock_timeout of 10 s
JOIN_SECONDS = 120.0


def _message(
    period_key: str, entity_code: str, state: str, version_no: int, rate: str, roads: str
) -> str:
    return (
        f"{period_key} is {state} for {entity_code} in book ASC606. The approval of version "
        f"{version_no} of rate set AVM-RATES-CLOSING changed 1 exchange rate dated in it: {rate}"
        f"{roads}{POSTED}"
    )


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _items(world: worlds.ReportWorld) -> list[dict[str, Any]]:
    """The items of the code, in number order, each with the code of its entity."""
    return close_run_worlds.rows(
        world.tenant_id,
        select(exception_item, legal_entity.c.code.label("entity_code"))
        .select_from(
            exception_item.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == exception_item.c.tenant_id,
                    legal_entity.c.id == exception_item.c.entity_id,
                ),
            )
        )
        .where(exception_item.c.code == CODE)
        .order_by(exception_item.c.exception_no),
    )


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _named(item: dict[str, Any]) -> tuple[str, str, int]:
    """(entity code, the closed period, the version) an item is about."""
    payload = item["source_payload"]
    return str(item["entity_code"]), str(payload["period_key"]), int(payload["version_no"])


def _told(world: worlds.ReportWorld, item: dict[str, Any]) -> list[tuple[Any, ...]]:
    found = close_run_worlds.rows(
        world.tenant_id,
        select(notification).where(notification.c.subject_id == item["id"]),
    )
    return sorted(
        (
            row["recipient_membership_id"],
            _text(row["kind"]),
            str(row["title"]),
            str(row["body"]),
            str(row["link_path"]),
        )
        for row in found
    )


def _period(
    world: worlds.ReportWorld, period_key: str, entity_code: str = AVM_US
) -> dict[str, Any]:
    """API-S-Period of one period, read by id: the row of the list carries no blocker counts."""
    state = worlds.period_state(world, entity_code, period_key)
    shown = get(world.app, f"{PERIODS}/{state['id']}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _blocking(world: worlds.ReportWorld, period_key: str) -> list[str]:
    """The numbers of the items ``blockers.exceptions_open`` of AVM-US's period counts."""
    state = worlds.period_state(world, AVM_US, period_key)
    listed = get(world.app, EXCEPTIONS, world.maya, {"blocking": state["id"], "limit": 100})
    assert listed.status_code == 200, listed.text
    return sorted(str(item["exception_no"]) for item in listed.json()["items"])


def _closed_by_fixture(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> worlds.ReportWorld:
    """``eur_receivable`` with January to August of AVM-US closed as fixture state — the state
    rows and their lock records, no run and no gate: the finding asks what a period's state is,
    not how it came to it. September is open."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    periods_closed_before(
        world.place,
        app,
        world.maya,
        entity_id=world.entity_id,
        before=SEPTEMBER,
        entity_code=AVM_US,
    )
    return world


def _august_lock_pending(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    *,
    record_clock: bool = False,
) -> tuple[worlds.ReportWorld, str]:
    """August ready for its lock decision on the product's own run, which read the closing rate
    1.105000: (the world, Maya's ``PERIOD_LOCK`` request)."""
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    if record_clock:
        world = worlds.on_record_clock(world, clock)
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None), run
    world = close_run_worlds.journal_and_reconciliations(world, clock, run)
    assert close_run_worlds.gate_shown(world, RUN_GATE) == ("PASSED", 0, None)
    requested = close_run_worlds.request_lock(world)
    assert requested.status_code == 200, requested.text
    return world, str(requested.json()["approval_request_id"])


def _errors(response: Any) -> dict[str, str]:
    return {error["rule_id"]: error["message"] for error in response.json()["errors"]}


# --- the measured case ----------------------------------------------------------------------------


def test_a_rate_changed_after_the_lock_raises_one_finding_that_holds_the_next_lock(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """August is closed through the product on a run that read the closing rate 1.105000. The
    version that corrects it to 1.115000 is approved afterwards: ONE item, of AVM-US and of
    September — the period the difference posts to — naming August, the version, the rate and
    both values, and the Revenue Accountant and the Controller are told. September's cockpit
    counts it and its ``EXCEPTIONS_CLEARED`` gate fails; no person may resolve or dismiss it. A
    version that repeats the rates raises nothing. The waiver of PRD SM-06 accepts it: asked by
    Maya with a comment, approved by Priya — the item is ``WAIVED`` under the request and the
    gate passes. September's run then posts 150.00 of remeasurement, August's 100.00 in it, and
    the lines carry no origin period.

    Fail-first (measured before the item, 2026-10-02 07:02): no exception item and no
    notification but the lock's own followed the approval; September's gates knew nothing."""
    world, august_run = close_run_worlds.august_locked(app, keyring, clock, files, monkeypatch)
    assert runs.by_role(
        runs.posted(world.tenant_id, august_run["id"]), period_key=AUGUST, entry_kind=FX
    ) == {"CONTRACT_LIABILITY": Decimal("50.0000"), "FX_GAIN_LOSS": Decimal("-50.0000")}
    september = _period(world, SEPTEMBER)
    assert september["state"] == "open"
    counted = int(september["blockers"]["exceptions_open"])
    held = _blocking(world, SEPTEMBER)
    assert _items(world) == [] and len(held) == counted

    # --- the closing rate of August is corrected after its lock ------------------------------
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {AUGUST: CORRECTED})
    (item,) = _items(world)
    august = worlds.period_state(world, AVM_US, AUGUST)
    (version,) = close_run_worlds.rows(
        world.tenant_id,
        select(fx_rate_set_version.c.id, fx_rate_set_version.c.approval_request_id).where(
            fx_rate_set_version.c.version_no == 2
        ),
    )
    text = _message(AUGUST, AVM_US, "closed", 2, AUGUST_CHANGED, REOPEN_OR_ACCEPT)
    assert {
        "source": _text(item["source"]),
        "severity": _text(item["severity"]),
        "status": _text(item["status"]),
        "title": item["title"],
        "message": item["message"],
        "entity": item["entity_id"],
        "period": item["period_id"],
        "key": item["dedupe_key"],
        "occurrences": item["occurrence_count"],
    } == {
        "source": "CLOSE",
        "severity": "WARNING",
        "status": "OPEN",
        "title": "FX rate changed after lock",
        "message": text,
        "entity": world.entity_id,
        "period": UUID(str(september["period"]["id"])),
        "key": f"CLOSE:{CODE}:{august['id']}:{version['id']}",
        "occurrences": 1,
    }
    assert item["source_payload"] == {
        "fx_rate_set_version_id": str(version["id"]),
        "fx_rate_set_code": "AVM-RATES-CLOSING",
        "version_no": 2,
        "approval_request_id": str(version["approval_request_id"]),
        "period_state_id": str(august["id"]),
        "period_key": AUGUST,
        "book_code": "ASC606",
        "state": "closed",
        "posting_period_key": SEPTEMBER,
        "rates_changed": 1,
        "rates": [
            {
                "rate_type": "closing",
                "base_currency": "EUR",
                "quote_currency": "USD",
                "effective_date": "2026-08-31",
                "before": "1.105",
                "after": "1.115",
            }
        ],
    }
    told = [
        (member, "EXCEPTION_ASSIGNED", f"Exception: {CODE}", text, f"/data/exceptions/{item['id']}")
        for member in sorted([world.maya.member.membership_id, world.marcus.member.membership_id])
    ]
    assert _told(world, item) == told  # the Revenue Accountant and the Controller; not Priya

    # --- September's cockpit shows it, and its lock waits for a road -------------------------
    assert int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"]) == counted + 1
    assert _blocking(world, SEPTEMBER) == sorted([*held, str(item["exception_no"])])
    assert close_run_worlds.gate_shown(world, EXCEPTIONS_GATE, SEPTEMBER) == (
        "FAILED",
        counted + 1,
        f"Open exceptions: {counted + 1}",
    )
    shown = get(app, f"{EXCEPTIONS}/{item['id']}", world.maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["available_actions"] == ["ASSIGN", "REQUEST_WAIVER"]
    assert shown.json()["dismiss_blocked_reason"] == "INPUT_COMMITTED"

    # --- a version that repeats the rates raises nothing --------------------------------------
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {AUGUST: CORRECTED})
    assert [row["id"] for row in _items(world)] == [item["id"]]

    # --- the second road: the difference is accepted ------------------------------------------
    comment = "Immaterial: USD 100.00 of August's remeasurement, taken in September."
    asked = post(app, f"{EXCEPTIONS}/{item['id']}/request-waiver", world.maya, {"comment": comment})
    assert asked.status_code == 200, asked.text
    world = worlds.verified(world, clock, "priya")
    waived = approve(app, str(asked.json()["approval_request_id"]), world.priya)
    assert (waived.status_code, waived.json()["status"]) == (200, "APPROVED"), waived.text
    (accepted,) = _items(world)
    assert (
        _text(accepted["status"]),
        accepted["waiver_approval_request_id"],
        accepted["resolution"],
        accepted["resolved_by"],
    ) == (
        "WAIVED",
        UUID(str(asked.json()["approval_request_id"])),
        comment,
        world.priya.member.user_id,
    )
    assert int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"]) == counted
    assert close_run_worlds.gate_shown(world, EXCEPTIONS_GATE, SEPTEMBER)[0] == (
        "PASSED" if counted == 0 else "FAILED"
    )

    # --- what September's run posts: August's 100.00 with its own 50.00, without an origin ---
    state = worlds.period_state(world, AVM_US, SEPTEMBER)
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "September close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    september_run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (september_run["status"], september_run["current_step_code"]) == ("SUCCEEDED", None)
    lines = close_run_worlds.rows(
        world.tenant_id,
        select(
            subledger_line.c.account_role,
            subledger_line.c.amount_functional,
            subledger_line.c.origin_period_id,
        )
        .select_from(
            subledger_line.join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
        )
        .where(subledger_line.c.entry_kind == FX, period.c.period_key == SEPTEMBER),
    )
    assert sorted(
        (_text(line["account_role"]), f"{Decimal(line['amount_functional']):.2f}") for line in lines
    ) == [("CONTRACT_LIABILITY", "150.00"), ("FX_GAIN_LOSS", "-150.00")]
    assert {line["origin_period_id"] for line in lines} == {None}


# --- one item per entity, book and closed period --------------------------------------------------


def test_one_item_per_entity_and_closed_period_and_none_where_the_values_stand(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Two entities on one calendar: AVM-US with January to August closed, and AVM-DE — an
    entity without a contract, which no rate can touch — with them permanently locked. One
    version changes the closing rates of July and of August: four items, one per entity and
    period, each of September, and each message states the roads its states leave — July of
    AVM-US waits for the reopen of August, August of AVM-US can be reopened, and a permanently
    locked period has the waiver alone. Tenant-wide, as the gate's read is: AVM-DE gets its
    items too.

    Then, by value: a version that repeats the rates raises nothing; one that leaves July's rate
    out names a rate that disappears, and one that brings it back a rate that appears — each a
    new item of its version, never an occurrence of an earlier one; and a version that changes
    September's rate alone, a period that is open, raises nothing."""
    world = _closed_by_fixture(app, keyring, clock, files)
    (home,) = close_run_worlds.rows(
        world.tenant_id,
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id),
    )
    other = entity(app, world.maya, code=AVM_DE, calendar_id=str(home["calendar_id"]))
    keys = [f"FY2026-P{month:02d}" for month in range(1, 10)]
    open_periods(app, world.maya, entity_code=AVM_DE, keys=keys)
    periods_closed_before(
        world.place,
        app,
        world.maya,
        entity_id=UUID(str(other["id"])),
        before=SEPTEMBER,
        entity_code=AVM_DE,
        permanently=True,
    )
    september = UUID(str(worlds.period_state(world, AVM_US, SEPTEMBER)["period"]["id"]))
    counted = int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"])

    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {JULY: "1.200000", AUGUST: CORRECTED})
    july = "EUR/USD closing rate of 2026-07-31 from 1.1 to 1.2."
    locked = "permanently locked"
    first = {_named(item): item for item in _items(world)}
    assert {key: item["message"] for key, item in first.items()} == {
        (AVM_US, JULY, 2): _message(JULY, AVM_US, "closed", 2, july, LATER_FIRST),
        (AVM_US, AUGUST, 2): _message(
            AUGUST, AVM_US, "closed", 2, AUGUST_CHANGED, REOPEN_OR_ACCEPT
        ),
        (AVM_DE, JULY, 2): _message(JULY, AVM_DE, locked, 2, july, ACCEPT_ONLY),
        (AVM_DE, AUGUST, 2): _message(AUGUST, AVM_DE, locked, 2, AUGUST_CHANGED, ACCEPT_ONLY),
    }
    assert {item["period_id"] for item in first.values()} == {september}
    assert {_text(item["severity"]) for item in first.values()} == {"WARNING"}
    assert len({item["dedupe_key"] for item in first.values()}) == 4
    for item in first.values():
        assert len(_told(world, item)) == 2, item["exception_no"]
    # each cockpit counts the items of its own entity
    assert int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"]) == counted + 2
    assert int(_period(world, SEPTEMBER, AVM_DE)["blockers"]["exceptions_open"]) == 2

    # --- by value ------------------------------------------------------------------------------
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {JULY: "1.200000", AUGUST: CORRECTED})
    assert len(_items(world)) == 4  # version 3 repeats version 2
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {JULY: None, AUGUST: CORRECTED})
    gone = "EUR/USD closing rate of 2026-07-31, none where it was 1.2."
    fourth = {_named(item): item for item in _items(world) if _named(item)[2] == 4}
    assert {key: item["message"] for key, item in fourth.items()} == {
        (AVM_US, JULY, 4): _message(JULY, AVM_US, "closed", 4, gone, LATER_FIRST),
        (AVM_DE, JULY, 4): _message(JULY, AVM_DE, locked, 4, gone, ACCEPT_ONLY),
    }
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {JULY: "1.200000", AUGUST: CORRECTED})
    back = "EUR/USD closing rate of 2026-07-31, 1.2 where there was none."
    fifth = {_named(item): item for item in _items(world) if _named(item)[2] == 5}
    assert {key: item["message"] for key, item in fifth.items()} == {
        (AVM_US, JULY, 5): _message(JULY, AVM_US, "closed", 5, back, LATER_FIRST),
        (AVM_DE, JULY, 5): _message(JULY, AVM_DE, locked, 5, back, ACCEPT_ONLY),
    }
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(
        world, clock, {JULY: "1.200000", AUGUST: CORRECTED, SEPTEMBER: "1.130000"}
    )
    found = _items(world)
    assert len(found) == 8 and {item["occurrence_count"] for item in found} == {1}
    assert {_text(item["status"]) for item in found} == {"OPEN"}


# --- the first road: the reopen -------------------------------------------------------------------


def test_the_reopen_of_the_period_settles_its_items_and_no_other(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """July and August are closed and a version changes a rate of each: two items of September.
    August is reopened — Priya asks, Marcus and a second Controller approve: its item is
    ``RESOLVED`` by the system in the decision's transaction, with the reason and its own audit
    event, and September no longer counts it. July stays closed and its item stays open."""
    world = _closed_by_fixture(app, keyring, clock, files)
    counted = int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"])
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {JULY: "1.200000", AUGUST: CORRECTED})
    before = {_named(item)[1]: item for item in _items(world)}
    assert sorted(before) == [JULY, AUGUST]
    assert int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"]) == counted + 2

    clock.advance(timedelta(minutes=5))
    world = worlds.period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=AUGUST,
        comment="The closing rate of August was corrected after its lock.",
    )
    after = {_named(item)[1]: item for item in _items(world)}
    assert (
        _text(after[AUGUST]["status"]),
        after[AUGUST]["resolution"],
        after[AUGUST]["resolved_by"],
        _text(after[AUGUST]["resolved_by_kind"]),
        after[AUGUST]["waiver_approval_request_id"],
    ) == (
        "RESOLVED",
        "FY2026-P08 was reopened for AVM-US in book ASC606. Its next lock needs a close run "
        "that read the rates in force.",
        None,
        "SYSTEM",
        None,
    )
    assert (_text(after[JULY]["status"]), after[JULY]["resolution"]) == ("OPEN", None)
    resolved = close_run_worlds.rows(
        world.tenant_id,
        select(audit_event.c.object_id).where(audit_event.c.action == "exception_item.resolve"),
    )
    assert [row["object_id"] for row in resolved] == [after[AUGUST]["id"]]
    assert int(_period(world, SEPTEMBER)["blockers"]["exceptions_open"]) == counted + 1


# --- beside the real lock decision ----------------------------------------------------------------


def test_a_lock_decision_that_meets_an_approval_in_flight_waits_and_is_refused_by_the_gate(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approval first. T1 — Marcus's approval of the corrected version — has run its hook
    and is NOT committed: it holds August's state row ``FOR SHARE``. T2 — a second Controller's
    real approval of August's lock — is observed WAITING for T1, blocked in its ``FOR UPDATE``
    of that row, before it has judged a gate. T1 commits; the decision then evaluates and its
    close-run gate reads the version: the lock is refused by name and August stays in soft
    close — refused, since item FX-REPUBLISH-DIRTY-1, by the gate of the contract the approval
    marked as well. No item is raised: the period was not closed.

    Fail-first (the hook without its row lock): the decision does not wait — nothing is observed
    blocked — and it locks August on the gates it read before the approval committed."""
    world, lock_request = _august_lock_pending(app, keyring, clock, files, monkeypatch)
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: CORRECTED})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    outcome: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def decide() -> None:
        try:
            outcome["response"] = approve(app, lock_request, cora)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    deciding = threading.Thread(target=decide, name="rate-lock-decision")
    hooks = list(subjects.FX_RATE_VERSION_APPROVED)

    def approved_then_meet_the_decision(
        uow: UnitOfWork, version_id: UUID, request_id: UUID
    ) -> None:
        for hook in hooks:
            hook(uow, version_id, request_id)
        with observing_checkouts() as backends:
            approval_pid = backend_pid(uow.session)
            deciding.start()
            _, seen["blocked_in"] = await_lock_wait(
                uow.session,
                holder_pid=approval_pid,
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="period_state",
            )
        seen["waiting"] = deciding.is_alive() and not outcome

    monkeypatch.setattr(subjects, "FX_RATE_VERSION_APPROVED", [approved_then_meet_the_decision])
    try:
        approved = approve(app, sent["approval_request_id"], world.marcus)
    finally:
        if deciding.ident is not None:
            deciding.join(timeout=JOIN_SECONDS)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    assert not deciding.is_alive() and seen["waiting"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    assert "for update" in seen["blocked_in"].lower(), seen["blocked_in"]
    refused = outcome["response"]
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert _errors(refused) == {RUN_GATE: RATES_CHANGED, DIRTY_GATE: MARKED}
    assert worlds.period_state(world, AVM_US, AUGUST)["state"] == "closing"
    assert _items(world) == []


def test_an_approval_that_meets_a_lock_decision_in_flight_waits_and_reads_the_period_closed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decision first. A second Controller's approval of August's lock has judged its gates
    — passed, on the run that read 1.105000 — and frozen its datasets; it holds August's state
    row. Marcus's approval of the corrected version then arrives: it is observed WAITING —
    blocked by the decision's backend in its ``FOR SHARE`` read of the period states — and has
    raised nothing. The decision completes and August is closed; the approval then reads the
    period ``closed`` and raises the item.

    Fail-first (the hook without its row lock): the approval does not wait; it reads August
    ``closing``, raises nothing and commits, and the decision closes August on the old rate."""
    world, lock_request = _august_lock_pending(app, keyring, clock, files, monkeypatch)
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: CORRECTED})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    outcome: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def approve_late() -> None:
        try:
            outcome["response"] = approve(app, sent["approval_request_id"], world.marcus)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    approving = threading.Thread(target=approve_late, name="rate-approval-late")
    freeze_datasets = close_commands.snapshots.freeze_datasets

    def freeze_then_meet_the_approval(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(uow, *args, **kwargs)
        if approving.ident is None:  # once: the approval arrives after the gates and the freeze
            with observing_checkouts() as backends:
                decision_pid = backend_pid(uow.session)
                approving.start()
                _, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=decision_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
            seen["waiting"] = approving.is_alive() and not outcome
            seen["items"] = len(_items(world))
        return datasets

    monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_meet_the_approval)
    try:
        decided = approve(app, lock_request, cora)
    finally:
        if approving.ident is not None:
            approving.join(timeout=JOIN_SECONDS)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert not approving.is_alive() and seen["waiting"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    assert "for share" in seen["blocked_in"].lower(), seen["blocked_in"]
    assert seen["items"] == 0
    assert worlds.period_state(world, AVM_US, AUGUST)["state"] == "closed"
    approved = outcome["response"]
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    (item,) = _items(world)
    assert item["message"] == _message(
        AUGUST, AVM_US, "closed", 2, AUGUST_CHANGED, REOPEN_OR_ACCEPT
    )
    assert item["period_id"] == UUID(
        str(worlds.period_state(world, AVM_US, SEPTEMBER)["period"]["id"])
    )


def test_a_lock_decision_begun_before_the_approvals_instant_still_reads_the_version(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never a time. The lock decision's transaction has begun and holds no row yet; the
    corrected version is then approved at an application instant LATER than the decision's
    cutoff, and commits. The decision goes on: by ``published_at`` the version is not in force
    at its cutoff — and it is committed, and in force for every reader after it. The gate reads
    the rates whenever their version was published: the lock is refused by name — and, since
    item FX-REPUBLISH-DIRTY-1, by the gate of the contract the approval marked as well.

    The clocks: the world stands on the record clock, so that an application instant can lie
    after the server's present (dev-guide DG-TST-14).

    Fail-first (the gate's read bounded by its cutoff): the gate passes and the decision closes
    August on the old rate, with the corrected version in force."""
    world, lock_request = _august_lock_pending(
        app, keyring, clock, files, monkeypatch, record_clock=True
    )
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: CORRECTED})
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    begun, released = threading.Event(), threading.Event()
    outcome: dict[str, Any] = {}
    seen: dict[str, Any] = {}
    kind = ApprovalSubjectType.PERIOD_LOCK
    lifecycle = subjects.LIFECYCLES[kind]

    def begun_and_held_before_its_row(uow: UnitOfWork, subject_id: UUID, request_id: UUID) -> None:
        seen["cutoff"] = bundles.record_cutoff(uow.session, uow.now)  # the gate's, were it bounded
        begun.set()
        seen["released"] = released.wait(JOIN_SECONDS)
        lifecycle.on_approved(uow, subject_id, request_id)

    monkeypatch.setitem(
        subjects.LIFECYCLES,
        kind,
        dataclasses.replace(lifecycle, on_approved=begun_and_held_before_its_row),
    )

    def decide() -> None:
        try:
            outcome["response"] = approve(app, lock_request, cora)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    deciding = threading.Thread(target=decide, name="rate-lock-decision-begun")
    deciding.start()
    try:
        assert begun.wait(JOIN_SECONDS), outcome
        clock.advance(timedelta(minutes=20))  # the approval's instant: after the decision's cutoff
        world = worlds.verified(world, clock, "marcus")
        approved = approve(app, sent["approval_request_id"], world.marcus)
    finally:
        released.set()
        deciding.join(timeout=JOIN_SECONDS)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    assert not deciding.is_alive() and seen["released"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    (version,) = close_run_worlds.rows(
        world.tenant_id,
        select(fx_rate_set_version.c.published_at).where(
            fx_rate_set_version.c.id == UUID(sent["version_id"])
        ),
    )
    assert version["published_at"] > seen["cutoff"]  # "published after" the decision's cutoff
    refused = outcome["response"]
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert _errors(refused) == {RUN_GATE: RATES_CHANGED, DIRTY_GATE: MARKED}
    assert worlds.period_state(world, AVM_US, AUGUST)["state"] == "closing"
    assert _items(world) == []


# --- the approval's wait is bounded ---------------------------------------------------------------


def test_an_approval_that_waits_beyond_the_lock_timeout_is_refused_and_saves_nothing(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A change of September's state is in flight — its row is held ``FOR UPDATE``, as a decision
    holds it — for longer than the platform waits. The approval of a version that changes a rate
    dated on or before September waits for the row for the request's ``lock_timeout`` (10 s) and
    is then answered 409 ``lock-conflict`` under rule ``LOCK_TIMEOUT``, with the sentence of that
    rule: nothing was saved — the version is still submitted, its request pending, no item
    raised. Sent again once the row is free, it is approved and raises its item."""
    world = _closed_by_fixture(app, keyring, clock, files)
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: CORRECTED})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    september = UUID(str(worlds.period_state(world, AVM_US, SEPTEMBER)["id"]))
    held = world.place.uow()
    uow = held.__enter__()
    try:
        uow.session.execute(
            select(period_state.c.id).where(period_state.c.id == september).with_for_update()
        )
        started = time.monotonic()
        refused = approve(app, sent["approval_request_id"], world.marcus)
        waited = time.monotonic() - started
    finally:
        held.__exit__(None, None, None)
    assert (refused.status_code, slug(refused)) == (409, "lock-conflict"), refused.text
    assert refused.json()["detail"] == problems.LOCK_TIMEOUT_DETAIL
    assert _errors(refused) == {problems.RULE_LOCK_TIMEOUT: problems.LOCK_TIMEOUT_DETAIL}
    assert 9.0 < waited < 30.0, waited
    (version,) = close_run_worlds.rows(
        world.tenant_id,
        select(fx_rate_set_version.c.status).where(
            fx_rate_set_version.c.id == UUID(sent["version_id"])
        ),
    )
    (request,) = close_run_worlds.rows(
        world.tenant_id,
        select(approval_request.c.status).where(
            approval_request.c.id == UUID(sent["approval_request_id"])
        ),
    )
    assert (_text(version["status"]), _text(request["status"])) == ("SUBMITTED", "PENDING")
    assert _items(world) == []

    approved = approve(app, sent["approval_request_id"], world.marcus)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    (item,) = _items(world)
    assert _named(item) == (AVM_US, AUGUST, 2)
