"""The lock requires the period's close run (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and
R-116 (e); 04 T-CLS-02 rev 1.172 ``CLOSE_RUN_COMPLETED``, T-CON-03 "Period-end mark", T-CLS-04,
§16.8 "The close-run gate"; 05 RCP-08, PERF-03 rev 1.111; PRD BR-CLS-01; SCREENS_B §1.1; POLICIES
CHK-010, JET-06).

The gate passes when the latest close run of the entity, book and period ``SUCCEEDED`` and no
computed contract group that is not dirty holds a period-end mark of the entity and book on or
before the period's last day. The witnesses run the run: ``worlds.chk_010_position`` — POLICIES
CHK-010, unbilled receivable 3,000.00 and contract asset 2,000.00 at 31 Jan 2026, which the
netting reclass of January's close run posts — closed through ``POST /close-runs`` and its job
(``support.close_runs.closed``), with invoices recorded through ``POST /contracts/{id}/events``.

Expected amounts are the documents'. CHK-010 at 31 Jan 2026: revenue 14,000.00 (P1 3,000.00, P2
10,000.00, P3 1,000.00) against invoices 9,000.00 (P2 4,000.00, P3 5,000.00); the unconditional
right of P1 is an unbilled receivable of 3,000.00 and the conditional net 11,000.00 less 9,000.00
is a contract asset of 2,000.00: the reclass is Dr unbilled receivable 3,000.00, Dr contract asset
2,000.00 / Cr contract liability 5,000.00. Two late facts dated 31 Jan 2026 move it:

- a further invoice of 1,000.00 on P2-MILESTONE: invoices 10,000.00, the conditional net 1,000.00,
  so the reclass becomes 3,000.00 and 1,000.00 against 4,000.00 and a second run posts the
  difference to the first, Cr contract asset 1,000.00 / Dr contract liability 1,000.00. The
  workspace bills in its ERP (``billing.posting`` = ``ERP``, POL-004): the invoice posts no line;
- the build of P3 reported at 75% instead of 50%: revenue of 2,000.00 x 0.25 = 500.00 more, which
  the computation posts into January (class ``EVENT``); the conditional net is 11,500.00 less
  9,000.00 = 2,500.00, so the second run posts Dr contract asset 500.00 / Cr contract liability
  500.00.

A ledger assertion sums the lines of an account role and never counts lines (supervisor rulings
R-11, R-12, R-44 (a)).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, app_engine, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    close_checklist_item,
    close_checklist_template,
    close_run,
    combination_group,
    contract,
    contract_computation,
    engine_release,
    exception_item,
    job,
    lock_snapshot,
    period,
    period_lock,
    period_state,
    subledger_line,
    subledger_posting,
    tenant,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates, period_end
from erev_api.domain.contracts import bundles, computation
from erev_api.domain.platform import setup
from erev_api.enums import ApprovalRequestStatus, ComputationTrigger, ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.uow import UnitOfWork
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError
from erev_engine.stages import s13_books
from fastapi import FastAPI
from sqlalchemy import and_, event, func, insert, select, update
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.close_world import (
    BOOK,
    acknowledged_run,
    close_run_succeeded,
    close_world,
    contract_of,
    earlier_periods_closed,
    other_entity,
    periods_closed_before,
    reviewed_reconciliations,
    reviewed_reconciliations_for,
    system_session,
)
from support.db import TestDatabase
from support.factories import booked_contract, computed, engine
from support.interleave import (
    BLOCKED_BY_HOLDER,
    await_lock_wait,
    backend_pid,
    fresh_activity,
    observing_checkouts,
)
from support.principals import colleague, enrolled
from support.reference import PERIODS, approve, assign, get, holding, periods, post, slug
from support.rows import (
    approval_request_values,
    close_run_values,
    combination_group_values,
    contract_computation_values,
    engine_release_values,
    exception_item_values,
)

US01 = worlds.US01
AVM_US = worlds.AVM_US
JANUARY = "FY2026-P01"
FEBRUARY = "FY2026-P02"
KEY = f"{US01}|{BOOK}"
GATE = "CLOSE_RUN_COMPLETED"
RECLASS = "NETTING_RECLASS"
MILESTONE = "P2-MILESTONE"
BUILD = "P3-BUILD"
# POLICIES CHK-010 at 31 Jan 2026, debit positive.
CHK_010 = {
    "UNBILLED_RECEIVABLE": Decimal("3000.00"),
    "CONTRACT_ASSET": Decimal("2000.00"),
    "CONTRACT_LIABILITY": Decimal("-5000.00"),
}
# What a late fact dated 31 Jan 2026 leaves a second run to post (module docstring).
LATE_INVOICE = {"CONTRACT_ASSET": Decimal("-1000.00"), "CONTRACT_LIABILITY": Decimal("1000.00")}
LATE_PROGRESS = {"CONTRACT_ASSET": Decimal("500.00"), "CONTRACT_LIABILITY": Decimal("-500.00")}
OUT_OF_DATE = "Close run out of date, run it again: 1 contracts"
JOIN_SECONDS = 120.0
WAIT_SECONDS = 30.0
NEVER_WAIVED = "Close run completed cannot be waived. The period locks only when this gate passes."
# item CLO-GATE-RUN-2
AUGUST = "FY2026-P08"
SEPTEMBER = "FY2026-P09"
FX = "FX_REMEASUREMENT"
DIRTY_GATE = "NO_DIRTY_GROUPS"
CERTIFIED_GATE = "CONTROLLER_CERTIFIED"
TEMPLATES = "/api/v1/close-checklist-templates"
EARLIER_FIRST = "{period} has period-end amounts no close run has posted; run its close first."
# 04 §16.8 rev 1.259: the sentence ends with the words of the button that starts a run.
SUPERSEDED = "{no} is not the latest close run of this period. Run close again."
NOT_OPEN = (
    "{period_key} of {entity} in book {book} is closed. A close run needs an open period, a "
    "period in soft close or a reopened one."
)
# ``close_run_worlds.eur_receivable`` at 31 Aug 2026 (PRD §2.5 AVM-RATES; POLICIES JET-10a): EUR
# 10,000.00 recognised at 1.100000 and remeasured at the closing rate 1.105000 — a gain of 50.00 —
# and the reclass of the remeasured receivable, 11,050.00 (debit positive).
EUR_FX_AUGUST = {"CONTRACT_LIABILITY": Decimal("50.00"), "FX_GAIN_LOSS": Decimal("-50.00")}
EUR_RECLASS_AUGUST = {
    "UNBILLED_RECEIVABLE": Decimal("11050.00"),
    "CONTRACT_LIABILITY": Decimal("-11050.00"),
}
# ... and at 30 Sep 2026, remeasured at 1.120000 against August's 1.105000: a gain of 150.00.
EUR_FX_SEPTEMBER = {"CONTRACT_LIABILITY": Decimal("150.00"), "FX_GAIN_LOSS": Decimal("-150.00")}
# CHK-010 at 28 Feb 2026 once INV-POS-5 (1,000.00), INV-POS-6 (500.00) and INV-POS-7 (250.00)
# are invoiced on P2-MILESTONE: invoices 10,750.00 against the conditional revenue of 11,000.00
# — a contract asset of 250.00 — beside the unbilled receivable of P1, 3,000.00.
CHK_010_FEBRUARY = {
    "UNBILLED_RECEIVABLE": Decimal("3000.00"),
    "CONTRACT_ASSET": Decimal("250.00"),
    "CONTRACT_LIABILITY": Decimal("-3250.00"),
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _mark(world: worlds.ReportWorld, group_id: UUID) -> dict[str, str]:
    """``combination_group.period_ends_open`` of the group."""
    (row,) = _rows(
        world.tenant_id,
        select(combination_group.c.period_ends_open).where(combination_group.c.id == group_id),
    )
    return dict(row["period_ends_open"])


def _cockpit(world: worlds.ReportWorld, key: str, entity: str = US01) -> dict[str, Any]:
    state = worlds.period_state(world, entity, key)
    shown = get(world.app, f"{PERIODS}/{state['id']}/cockpit", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _gate(
    world: worlds.ReportWorld, key: str = JANUARY, entity: str = US01
) -> tuple[str, int | None, str | None]:
    """(status, count, detail) of the gate's checklist row as the cockpit serves it; the row is
    never waivable."""
    (row,) = [item for item in _cockpit(world, key, entity)["checklist"] if item["code"] == GATE]
    assert row["is_waivable"] is False
    return row["status"], row["result"]["count"], row["result"]["detail"]


def _soft_closed(world: worlds.ReportWorld, key: str = JANUARY) -> None:
    state = worlds.period_state(world, US01, key)
    started = post(
        world.app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": f"{state['period']['name']} close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text


def _lock_requested(world: worlds.ReportWorld, key: str = JANUARY) -> Any:
    state = worlds.period_state(world, US01, key)
    return post(
        world.app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": f"{state['period']['name']} close complete"},
        if_match=f'"r{state["row_version"]}"',
    )


def _invoiced(
    world: worlds.ReportWorld, contract_id: UUID, number: str, amount: str, day: str
) -> dict[str, Any]:
    """An invoice line on P2-MILESTONE through ``POST /contracts/{id}/events``; the append
    computes. Returns API-S-EventAppend."""
    sent = worlds._appended_through_api(
        world.place,
        contract_id,
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": day,
            "payload": {
                "invoice_number": number,
                "line_external_id": f"{number}-1",
                "obligation_key": MILESTONE,
                "amount": {"amount": amount, "currency": "USD"},
                "issue_date": day,
            },
        },
    )
    assert sent["computation"]["status"] == "SUCCEEDED", sent["computation"]
    return sent


def _progressed(
    world: worlds.ReportWorld, contract_id: UUID, ratio: str, day: str
) -> dict[str, Any]:
    """P3-BUILD reported at ``ratio`` of its output through ``POST /contracts/{id}/events``. A
    person's progress event waits for another user (BUILD_SPEC CTR-6; 04 §16.3 "Manual events"):
    Maya submits it with its evidence, Priya approves, and the approval appends and computes.
    Returns what a direct append answers (``worlds.approved_manual_events``)."""
    sent = worlds.approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "PROGRESS_RECORDED",
            "effective_date": day,
            "payload": {
                "obligation_key": BUILD,
                "cumulative_progress_ratio": ratio,
                "measure": "OUTPUT_PERCENT",
            },
        },
    )
    assert sent["computation"]["status"] == "SUCCEEDED", sent["computation"]
    return sent


def _reconciled(world: worlds.ReportWorld, clock: FrozenClock, key: str = JANUARY) -> None:
    """The two required reconciliations of the period, reviewed: the stand-in of
    ``worlds.period_locked`` (fixture state for ``RECONCILIATIONS_GENERATED``)."""
    state = worlds.period_state(world, US01, key)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )


def _reclass(world: worlds.ReportWorld, run: dict[str, Any], key: str) -> dict[str, Decimal]:
    """Σ functional amount per account role of the reclass lines the run sealed in the period,
    the roles that sum to nothing left out."""
    found = runs.by_role(
        runs.posted(world.tenant_id, run["id"]), period_key=key, entry_kind=RECLASS
    )
    return {role: amount for role, amount in found.items() if amount}


class _EngineRuns:
    """Counts the engine's runs: ``erev_engine.compute`` and a close-run pass each walk the books
    once (``s13_books.run_books``)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._count = 0
        run_books: Callable[..., Any] = s13_books.run_books

        def counted(*args: Any, **kwargs: Any) -> Any:
            self._count += 1
            return run_books(*args, **kwargs)

        monkeypatch.setattr(s13_books, "run_books", counted)

    def taken(self) -> int:
        """The runs since the last reading."""
        count, self._count = self._count, 0
        return count


# --- the gate's read (04 §16.8 "The close-run gate", (1) and (2)) ---------------------------------


def test_the_gate_reads_the_latest_run_and_the_marks_of_its_scope(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``gates.close_run_facts`` over rows: without a run there is no fact; the latest run — by
    ``created_at`` — is the one read, whatever an earlier one ended as; and a ``SUCCEEDED`` run
    counts the computed groups that hold a period end still to post (04 §16.8 rev 1.228; item
    CLO-GATE-RUN-2): a group that holds a contract and either a mark of the entity and book on or
    before the period's last day — dirty or not — or no mark of that scope and a contract of the
    entity. Not counted: a mark after that day, a group never computed, a group that holds no
    contract, another entity's group without a mark of the scope, and a dirty group whose
    quarantine stands waived (``NO_DIRTY_GROUPS`` alone holds it).

    STALE EXPECTATION by the supervisor's ruling of 2026-10-01 on the pre-build line of item
    CLO-GATE-RUN-2: until then the groups of this test held no contract, and "a group without a
    mark" and "a dirty group" were pinned as not counted (3 of 8 rows); a group without a
    contract is no longer counted at all, so each row now has the contract its case needs."""
    world = close_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    key = f"AVM-US|{BOOK}"
    now = clock.now()
    with system_session(world) as session:
        scope = gates.scope_of_period(session, world.entity_id, BOOK, world.period_id)
        assert scope is not None and scope.end_date.isoformat() == "2026-09-30"
        assert gates.close_run_facts(session, scope, known_at=now) is None
        release = engine_release_values()
        session.execute(insert(engine_release).values(**release))
        uk = other_entity(session, world)

        def computation_of(group_id: UUID, **columns: Any) -> UUID:
            row = contract_computation_values(
                tenant_id, combination_group_id=group_id, engine_release_id=release["id"], **columns
            )
            session.execute(insert(contract_computation).values(**row))
            return UUID(str(row["id"]))

        def group(
            mark: dict[str, str],
            *,
            computed: bool = True,
            dirty: bool = False,
            of: UUID | None = world.entity_id,
        ) -> UUID:
            """A group with one contract of the entity ``of`` (None: a group without a contract),
            its mark, and its head computation when ``computed``."""
            columns = {"period_ends_open": mark, "dirty_since": now if dirty else None}
            if of is None:
                row = combination_group_values(tenant_id, **columns)
                session.execute(insert(combination_group).values(**row))
                group_id = UUID(str(row["id"]))
            else:
                _, _, group_id = contract_of(session, world, of)
                session.execute(
                    update(combination_group)
                    .where(combination_group.c.id == group_id)
                    .values(**columns)
                )
            if computed:
                session.execute(
                    update(combination_group)
                    .where(combination_group.c.id == group_id)
                    .values(head_computation_id=computation_of(group_id, created_at=now))
                )
            return group_id

        group({key: "2026-09-01"})  # counted: the period's first day
        group({key: "2026-09-30"})  # counted: its last day
        group({key: "2026-08-15", "AVM-UK|ASC606": "2026-10-01"})  # counted: an earlier period
        group({})  # counted: no mark, a contract of the entity
        group({"AVM-UK|ASC606": "2026-09-01", "AVM-US|IFRS15": "2026-01-01"})  # counted: none of it
        group({key: "2026-09-01"}, dirty=True)  # counted: dirty, a period end to post
        group({key: "2026-09-01"}, of=uk)  # counted: another entity's contract, a mark of the scope
        group({key: "2026-10-01"})  # the day after the last day: posted through September
        group({key: "2026-09-01"}, computed=False)  # never computed
        group({key: "2026-09-01"}, of=None)  # holds no contract: no period end
        group({}, of=uk)  # another entity's group without a mark of the scope
        # dirty, its quarantine waived and standing: the latest computation — a minute after the
        # head — refused, no stream moved since (no member has one), the latest blocking engine
        # item WAIVED
        waived = group({key: "2026-09-01"}, dirty=True)
        computation_of(
            waived,
            status="QUARANTINED",
            problem={"code": "ENGINE_INVARIANT_VIOLATION"},
            created_at=now + timedelta(minutes=1),
        )
        item = exception_item_values(
            tenant_id, combination_group_id=waived, status="WAIVED", resolution="Accepted."
        )
        waiver = approval_request_values(
            tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            subject_type="EXCEPTION_WAIVER",
            subject_id=item["id"],
            entity_id=world.entity_id,
        )
        session.execute(insert(approval_request).values(**waiver))
        session.execute(
            insert(exception_item).values(**item, waiver_approval_request_id=waiver["id"])
        )

        def run(status: str, *, after: int) -> str:
            row = close_run_values(
                tenant_id,
                entity_id=world.entity_id,
                period_id=world.period_id,
                status=status,
                created_at=now + timedelta(minutes=after),
            )
            session.execute(insert(close_run).values(**row))
            return str(row["close_run_no"])

        failed = run("FAILED", after=1)
        assert gates.close_run_facts(session, scope, known_at=now) == gates.CloseRunFacts(
            failed, "FAILED"
        )
        succeeded = run("SUCCEEDED", after=2)
        assert gates.close_run_facts(session, scope, known_at=now) == gates.CloseRunFacts(
            succeeded, "SUCCEEDED", out_of_date=7
        )
        cancelled = run("CANCELLED", after=3)
        assert gates.close_run_facts(session, scope, known_at=now) == gates.CloseRunFacts(
            cancelled, "CANCELLED"
        )
        # another period of the entity has no run of its own
        august = session.execute(
            select(period.c.id).where(period.c.period_key == "FY2026-P08")
        ).scalar_one()
        earlier = gates.scope_of_period(session, world.entity_id, BOOK, UUID(str(august)))
        assert earlier is not None and gates.close_run_facts(session, earlier, known_at=now) is None


def test_the_gate_reads_the_same_for_a_decider_scoped_to_one_entity_of_two(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Supervisor ruling R-42 (d) — "a control's result must not depend on who decides" — after
    lane SECFIX-APR's merge: the ``PERIOD_LOCK`` hook evaluates the gates under the tenant's
    SYSTEM scope. The workspace has two entities. A contract group whose only contract is
    AVM-UK's — a row no caller scoped to AVM-US alone can read — holds a period end of AVM-US
    still to post: its member of AVM-US and the book lies on September's first day (the group
    performs for AVM-US). The request of the tenant-wide accountant, the request of an accountant
    whose role names AVM-US alone and the cockpit that accountant reads give one answer, "Close
    run out of date, run it again: 1 contracts"; so does the decision of a Controller whose role
    names AVM-US alone, and it writes nothing. With the member past the period's last day that
    Controller locks the period and the gate is certified ``PASSED``."""
    world = close_world(app, keyring, clock, files)
    tenant_id, key = world.tenant_id, f"AVM-US|{BOOK}"
    earlier_periods_closed(world)

    def state() -> dict[str, Any]:
        (found,) = [
            item
            for item in periods(app, world.maya, entity="AVM-US")
            if item["period"]["period_key"] == "FY2026-P09"
        ]
        return dict(found)

    shown = state()
    started = post(
        app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text

    def marked(day: str) -> None:
        with system_session(world) as session:
            session.execute(
                update(combination_group)
                .where(combination_group.c.id == group_id)
                .values(period_ends_open={key: day})
            )

    with system_session(world) as session:
        acknowledged_run(session, world)
        reviewed_reconciliations(session, world)
        close_run_succeeded(session, world)
        uk = other_entity(session, world)
        contract_id, _, group_id = contract_of(session, world, uk)
        release = engine_release_values()
        session.execute(insert(engine_release).values(**release))
        computation = contract_computation_values(
            tenant_id, combination_group_id=group_id, engine_release_id=release["id"]
        )
        session.execute(insert(contract_computation).values(**computation))
        session.execute(
            update(combination_group)
            .where(combination_group.c.id == group_id)
            .values(head_computation_id=computation["id"], period_ends_open={key: "2026-09-01"})
        )

    # the contract is AVM-UK's: a session scoped to AVM-US alone does not see it, the group it does
    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(world.entity_id,))
    with tenant_session(scoped, read_only=True) as session:
        assert (
            session.execute(select(contract.c.id).where(contract.c.id == contract_id)).first()
            is None
        )
        assert session.execute(
            select(combination_group.c.id).where(combination_group.c.id == group_id)
        ).first()

    # personas whose roles name AVM-US alone: a Revenue Accountant and a Controller (fresh TOTP)
    rita = holding(
        app, colleague(tenant_id, "rita"), "revenue_accountant", entity_ids=[world.entity_id]
    )
    cole_member = colleague(tenant_id, "cole")
    assign(cole_member, "controller", entity_ids=[world.entity_id])
    cole = enrolled(app, clock, cole_member)

    def request_lock(actor: Any) -> Any:
        current = state()
        return post(
            app,
            f"{PERIODS}/{current['id']}/request-lock",
            actor,
            {"certification_comment": "September 2026 close complete"},
            if_match=f'"r{current["row_version"]}"',
        )

    for actor in (world.maya, rita):
        refused = request_lock(actor)
        assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
        assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
            (GATE, OUT_OF_DATE)
        ]
        cockpit = get(app, f"{PERIODS}/{shown['id']}/cockpit", actor)
        assert cockpit.status_code == 200, cockpit.text
        (row,) = [item for item in cockpit.json()["checklist"] if item["code"] == GATE]
        assert (row["status"], row["result"]["count"], row["result"]["detail"]) == (
            "FAILED",
            1,
            OUT_OF_DATE,
        )

    # a close run passed the group: the AVM-US-only accountant submits the period for lock
    marked("2026-10-01")
    requested = request_lock(rita)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])

    # at the decision the group holds a period end again: the AVM-US-only Controller is refused
    marked("2026-09-01")
    blocked = approve(app, request_id, cole)
    assert (blocked.status_code, slug(blocked)) == (409, "close-gates-failed"), blocked.text
    assert [(error["rule_id"], error["message"]) for error in blocked.json()["errors"]] == [
        (GATE, OUT_OF_DATE)
    ]
    assert state()["state"] == "closing"
    assert not _rows(
        tenant_id, select(period_lock.c.id).where(period_lock.c.period_id == world.period_id)
    )

    # positive control: with the period end posted the same Controller locks the period
    marked("2026-10-01")
    decided = approve(app, request_id, cole)
    assert decided.status_code == 200, decided.text
    assert state()["state"] == "closed"
    (lock,) = _rows(
        tenant_id,
        select(period_lock.c.certification).where(period_lock.c.period_id == world.period_id),
    )
    (certified,) = [row for row in lock["certification"] if row["gate_check_code"] == GATE]
    assert (certified["status"], certified["count"]) == ("PASSED", 0)


# --- the lock waits for the run -------------------------------------------------------------------


def test_the_lock_is_refused_until_the_periods_close_run_succeeded(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-114 (b): without a close run January's lock is refused by name, the
    gate cannot be waived, a run that did not succeed is named with its status, and the run that
    succeeds passes the gate and marks the contract's period ends posted through 31 Jan 2026."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    group_id = UUID(str(world.contracts[worlds.C_POS].combination_group["id"]))
    _soft_closed(world)
    assert _gate(world) == ("FAILED", 1, "Close run not completed")
    assert _mark(world, group_id) == {}

    shown = _cockpit(world, JANUARY)
    (row,) = [item for item in shown["checklist"] if item["code"] == GATE]
    assert (row["name"], row["gate_kind"]) == ("Close run completed", "AUTOMATIC")
    waiver = post(
        app,
        f"{PERIODS}/{shown['period']['id']}/checklist/{row['id']}/waive",
        world.maya,
        {"reason": "The close run is not needed for January."},
        if_match=f'"r{shown["period"]["row_version"]}"',
    )
    assert (waiver.status_code, slug(waiver)) == (409, "invalid-transition"), waiver.text
    assert waiver.json()["detail"] == NEVER_WAIVED

    refused = _lock_requested(world)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    errors = {error["rule_id"]: error["message"] for error in refused.json()["errors"]}
    assert errors[GATE] == "Close run not completed"
    assert "Close run completed" in refused.json()["detail"]

    # a run that was cancelled is the period's latest run: the gate names it
    run_id, _ = runs.started(app, world.maya, entity_code=US01, period_key=JANUARY)
    cancelled = runs.cancel(app, world.maya, run_id, "Started before the invoices were in.")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    number = cancelled.json()["close_run_no"]
    assert _gate(world) == ("FAILED", 1, f"Close run {number} is Cancelled")
    errors = {
        error["rule_id"]: error["message"] for error in _lock_requested(world).json()["errors"]
    }
    assert errors[GATE] == f"Close run {number} is Cancelled"

    run = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert run["status"] == "SUCCEEDED"
    assert _reclass(world, run, JANUARY) == CHK_010
    assert _gate(world) == ("PASSED", 0, None)
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    still = _lock_requested(world)  # the other gates of an unposted journal still hold the lock
    assert (still.status_code, slug(still)) == (409, "close-gates-failed"), still.text
    assert GATE not in {error["rule_id"] for error in still.json()["errors"]}


# --- what a computation does to the mark (05 RCP-08 and PERF-03 rev 1.111) ------------------------


def test_a_computation_is_judged_by_the_passes_only_inside_a_window(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-116 (e). Outside a window — no close run of the entity has posted a
    period end that is still postable — a computation runs the engine once and writes no mark.
    Inside January's window it runs the engine four times, its own run and the three passes dry:
    an invoice dated in February finds January's amounts posted and moves nothing, so the gate
    holds; progress dated 31 Jan 2026 — whose computation posts an ``EVENT`` line into January,
    the period under close: revenue of 500.00 — leaves a reclass of January to post, the mark
    goes back to 1 Jan 2026 and the gate fails with the count. The run that is run again posts
    exactly that difference and the gate passes."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    engine = _EngineRuns(monkeypatch)

    _invoiced(world, contract_id, "INV-POS-3", "2000.00", "2026-02-15")
    assert engine.taken() == 1
    assert _mark(world, group_id) == {}

    first = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert first["status"] == "SUCCEEDED"
    assert _reclass(world, first, JANUARY) == CHK_010
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    assert _gate(world) == ("PASSED", 0, None)
    engine.taken()

    # a later period's fact: January's period end stays posted
    _invoiced(world, contract_id, "INV-POS-4", "1000.00", "2026-02-20")
    assert engine.taken() == 4
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    assert _gate(world) == ("PASSED", 0, None)

    # a late fact of the period under close
    late = _progressed(world, contract_id, "0.75", "2026-01-31")
    assert engine.taken() == 4
    line, posting = subledger_line, subledger_posting
    revenue = _rows(
        world.tenant_id,
        select(posting.c.posting_kind, func.sum(line.c.amount_functional).label("amount"))
        .select_from(
            line.join(
                posting,
                and_(
                    posting.c.tenant_id == line.c.tenant_id,
                    posting.c.id == line.c.subledger_posting_id,
                ),
            ).join(
                period,
                and_(period.c.tenant_id == line.c.tenant_id, period.c.id == line.c.period_id),
            )
        )
        .where(
            posting.c.contract_computation_id == UUID(str(late["computation"]["id"])),
            period.c.period_key == JANUARY,
            line.c.account_role == "REVENUE",
        )
        .group_by(posting.c.posting_kind),
    )
    # the computation's own posting: revenue of 500.00 in January (a credit), class EVENT
    assert [(str(row["posting_kind"]), Decimal(row["amount"])) for row in revenue] == [
        ("ENGINE_COMPUTE", Decimal("-500.00"))
    ]
    assert _mark(world, group_id) == {KEY: "2026-01-01"}
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)

    second = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert second["status"] == "SUCCEEDED"
    assert _reclass(world, second, JANUARY) == LATE_PROGRESS
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    assert _gate(world) == ("PASSED", 0, None)


# --- a reopened period (supervisor ruling R-116 (e), "the reopen order") --------------------------


def test_a_reopened_period_needs_a_new_close_run(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """January is locked on its close run — the certification lists the fourteen gates, the close
    run ``PASSED`` — and reopened. The earlier run's first period-end step is ``SUCCEEDED`` and
    the period is postable again, so the correction computed in it is inside a window: the mark
    goes back to 1 Jan 2026 and the re-lock is refused until a new close run, which posts the
    difference; then the period locks again."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    period_id = UUID(str(worlds.period_state(world, US01, JANUARY)["period"]["id"]))

    _soft_closed(world)
    first = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert first["status"] == "SUCCEEDED"
    world = runs.journal_posted(world, clock, first["journal_run_id"])
    _reconciled(world, clock)
    requested = _lock_requested(world)
    assert requested.status_code == 200, requested.text
    world = worlds.verified(world, clock, "marcus")
    decided = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.certification).where(period_lock.c.period_id == period_id),
    )
    certified = {row["gate_check_code"]: row for row in lock["certification"]}
    assert list(certified) == list(gates.GATE_CHECK_CODES) and len(certified) == 14
    assert {row["status"] for row in certified.values()} == {"PASSED"}
    assert set(certified[GATE]) == {"gate_check_code", "status", "count", "evaluated_at"}
    assert certified[GATE]["count"] == 0

    world = worlds.period_reopened(
        world,
        clock,
        entity_code=US01,
        period_key=JANUARY,
        comment="The invoice INV-POS-5 of 31 Jan 2026 was not recorded.",
    )
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    _invoiced(world, contract_id, "INV-POS-5", "1000.00", "2026-01-31")
    assert _mark(world, group_id) == {KEY: "2026-01-01"}

    _soft_closed(world)
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)
    refused = _lock_requested(world)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    errors = {error["rule_id"]: error["message"] for error in refused.json()["errors"]}
    assert errors[GATE] == OUT_OF_DATE

    second = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert second["status"] == "SUCCEEDED"
    assert _reclass(world, second, JANUARY) == LATE_INVOICE
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    assert _gate(world) == ("PASSED", 0, None)

    # the re-lock: the journal run of the correction through its life, the reconciliations again
    world = runs.journal_posted(world, clock, second["journal_run_id"])
    _reconciled(world, clock)
    again = _lock_requested(world)
    assert again.status_code == 200, again.text
    world = worlds.verified(world, clock, "marcus")
    relocked = approve(app, str(again.json()["approval_request_id"]), world.marcus)
    assert (relocked.status_code, relocked.json()["status"]) == (200, "APPROVED"), relocked.text
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"


# --- a period end that cannot be posted (05 RCP-08 rev 1.111, a refused dry pass) -----------------


def test_a_period_end_that_cannot_be_posted_holds_the_lock_by_name(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chart of ``worlds.k01_pellworth`` maps no contract asset. K-01 is invoiced in advance
    and January's close run succeeds. A second contract of the customer, never invoiced, is then
    computed inside January's window: the reclass of its revenue cannot be built
    (``ACCOUNT_MAPPING_MISSING``), so the dry pass is refused, the contract is marked from the
    first day of the earliest postable period of its contracting entity and the gate fails with
    the count. The run that is run again stops at the reclass and names the contract group and
    the code; the gate then names that run. Its first period-end step did pass the group and set
    its mark — the gate reads a mark only beside a run that ``SUCCEEDED``."""
    world = worlds.on_record_clock(
        worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 31)), clock
    )
    key = f"{AVM_US}|{BOOK}"
    first = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=JANUARY)
    assert first["status"] == "SUCCEEDED"
    assert _gate(world, entity=AVM_US) == ("PASSED", 0, None)
    k01_group = UUID(str(world.contracts[worlds.K01].combination_group["id"]))
    assert _mark(world, k01_group) == {key: "2026-02-01"}

    # O1 of K-01 alone, 120,000.00 over 2026, for the same customer and never invoiced
    body = worlds.k01_body(UUID(str(world.contracts[worlds.K01].contract["customer_id"])))
    body["external_id"] = "SF-ORD-10001-B"
    body["lines"] = [body["lines"][0]]
    unbilled = booked_contract(world.place, body, activate=True)
    group_id = UUID(str(unbilled.combination_group["id"]))
    computed(world.place, group_id)
    assert _mark(world, group_id) == {key: "2026-01-01"}
    assert _mark(world, k01_group) == {key: "2026-02-01"}
    assert _gate(world, entity=AVM_US) == ("FAILED", 1, OUT_OF_DATE)

    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=JANUARY)
    assert second["status"] == "FAILED"
    reclass = runs.step(second, RECLASS)
    assert reclass["status"] == "FAILED"
    assert reclass["problem"]["detail"] == (
        f"The contract balance reclassification of contract group "
        f"{unbilled.combination_group['code']} stopped: ACCOUNT_MAPPING_MISSING: a stage "
        "collected a blocking finding (CV-15)"
    )
    assert _gate(world, entity=AVM_US) == (
        "FAILED",
        1,
        f"Close run {second['close_run_no']} is Failed",
    )
    assert _mark(world, group_id) == {key: "2026-02-01"}


# --- the decision and a computation inside the window (04 DB-07; dev-guide DG-KRN-DB-08) ----------


@dataclass(frozen=True)
class _Pending:
    """January of US01 with its lock requested on a succeeded close run; Marcus decides."""

    world: worlds.ReportWorld
    request_id: str
    contract_id: UUID
    group_id: UUID
    period_id: UUID
    state_id: UUID


def _january_lock_pending(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> _Pending:
    """``worlds.chk_010_position`` with January in soft close, closed by its close run, the
    journal run through its life, the reconciliations reviewed, the lock requested and Marcus
    verified: the decision is all that is left. Tenant setup is complete — while
    ``tenant.setup_completed_at`` is NULL an approval takes the tenant row ``FOR UPDATE``, a wait
    that would stand in for the one under test."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    _soft_closed(world)
    run = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert run["status"] == "SUCCEEDED"
    world = runs.journal_posted(world, clock, run["journal_run_id"])
    _reconciled(world, clock)
    requested = _lock_requested(world)
    assert requested.status_code == 200, requested.text
    world = worlds.verified(world, clock, "marcus")
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    (completed,) = _rows(world.tenant_id, select(tenant.c.setup_completed_at))
    assert completed["setup_completed_at"] is not None
    state = worlds.period_state(world, US01, JANUARY)
    return _Pending(
        world=world,
        request_id=str(requested.json()["approval_request_id"]),
        contract_id=UUID(str(booked.contract["id"])),
        group_id=UUID(str(booked.combination_group["id"])),
        period_id=UUID(str(state["period"]["id"])),
        state_id=UUID(str(state["id"])),
    )


def _late_invoice() -> EventIn:
    """INV-POS-5: 1,000.00 on P2-MILESTONE dated 31 Jan 2026. The workspace bills in its ERP, so
    its computation posts no line; it moves January's reclass (module docstring)."""
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 1, 31),
        payload=BillingRecordedV1(
            invoice_number="INV-POS-5",
            line_external_id="INV-POS-5-1",
            obligation_key=MILESTONE,
            amount=MoneyIn(amount="1000.00", currency="USD"),
            issue_date=date(2026, 1, 31),
        ),
    )


def _recorded(uow: UnitOfWork, pending: _Pending) -> None:
    """The late invoice appended to the contract's stream inside ``uow``."""
    head = uow.session.execute(
        select(contract.c.head_stream_version).where(contract.c.id == pending.contract_id)
    ).scalar_one()
    append_events(
        uow,
        contract_id=pending.contract_id,
        expected_stream_version=int(head),
        events=[_late_invoice()],
        origin="UI",
    )


def _lines_of(tenant_id: UUID, computation_id: object) -> int:
    """The subledger lines of a computation's postings."""
    (row,) = _rows(
        tenant_id,
        select(func.count().label("lines"))
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == subledger_line.c.tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
        )
        .where(subledger_posting.c.contract_computation_id == UUID(str(computation_id))),
    )
    return int(row["lines"])


def _decision_wrote(pending: _Pending) -> dict[str, Any]:
    """What a lock decision writes, read back."""
    tenant_id = pending.world.tenant_id

    def count(table: Any, *where: Any) -> int:
        (row,) = _rows(tenant_id, select(func.count().label("n")).select_from(table).where(*where))
        return int(row["n"])

    (state,) = _rows(
        tenant_id,
        select(period_state.c.state, period_state.c.row_version).where(
            period_state.c.id == pending.state_id
        ),
    )
    (request,) = _rows(
        tenant_id,
        select(approval_request.c.status).where(approval_request.c.id == UUID(pending.request_id)),
    )
    return {
        "state": str(getattr(state["state"], "value", state["state"])),
        "state_row_version": int(state["row_version"]),
        "locks": count(period_lock, period_lock.c.period_id == pending.period_id),
        "snapshots": count(lock_snapshot),
        "decisions": count(
            approval_decision, approval_decision.c.approval_request_id == UUID(pending.request_id)
        ),
        "request_status": str(getattr(request["status"], "value", request["status"])),
    }


def test_a_computation_in_flight_that_moves_only_the_mark_is_waited_for_by_the_lock_decision(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SC-1 interleaving with a computation that inserts no line (supervisor ruling of
    2026-10-01 02:35 on item CLO-GATE-RUN-1; 04 DB-07; dev-guide DG-KRN-DB-08 rev 1.155). T1 — the
    late invoice recorded and computed inside January's window — has lowered the contract's mark
    and is NOT committed; it holds January's state row ``FOR SHARE``, as a posting into the period
    would, though it posts nothing. T2 — Marcus's real approval — is observed WAITING for T1,
    blocked in its ``FOR UPDATE`` of that row, and writes nothing meanwhile. T1 commits; the
    decision then reads the mark: the gate refuses the lock by name and nothing is written.

    Fail-first (measured on the head before the share lock): the approval did not wait — it
    answered 200 and locked January while T1 was in flight, and T1 then committed a mark that
    says January's period end is still to post."""
    pending = _january_lock_pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    before = _decision_wrote(pending)
    assert (before["state"], before["locks"], before["request_status"]) == ("closing", 0, "PENDING")
    outcome: dict[str, Any] = {}

    def decide() -> None:
        try:
            outcome["response"] = approve(world.app, pending.request_id, world.marcus)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    request = threading.Thread(target=decide, name="close-run-gate-decision")
    held = world.place.uow()
    uow = held.__enter__()
    started = False
    try:
        _recorded(uow, pending)  # T1: the event, its computation and the mark, in flight
        bundle = bundles.build(
            uow.session, pending.group_id, uow.now, (), ComputationTrigger.COMMAND
        )
        stored: Mapping[str, Any] = computation.persist(uow, bundle, engine()(bundle))
        uow.session.flush()
        assert stored["status"] == "SUCCEEDED"
        assert _mark(world, pending.group_id) == {KEY: "2026-02-01"}  # T1's mark is not committed
        with observing_checkouts() as backends:
            holder_pid = backend_pid(uow.session)
            request.start()
            started = True
            blocked_pid, blocked_in = await_lock_wait(
                uow.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="period_state",
            )
        assert blocked_pid != holder_pid and "for update" in blocked_in.lower(), blocked_in
        assert request.is_alive() and "response" not in outcome
        assert _decision_wrote(pending) == before
        uow.commit()  # T1 commits while the decision waits for it
    finally:
        held.__exit__(None, None, None)
        if started:
            request.join(timeout=JOIN_SECONDS)
    assert not request.is_alive() and "error" not in outcome, outcome
    assert _lines_of(world.tenant_id, stored["id"]) == 0  # the computation posted no line at all
    assert _mark(world, pending.group_id) == {KEY: "2026-01-01"}
    refused = outcome["response"]
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    errors = {error["rule_id"]: error["message"] for error in refused.json()["errors"]}
    assert errors[GATE] == OUT_OF_DATE
    assert _decision_wrote(pending) == before


def test_a_computation_that_arrives_while_the_lock_is_decided_waits_and_finds_no_window(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other order. The decision has evaluated its gates, frozen its datasets and holds
    January's state row; the late invoice is then recorded and its computation reaches the read
    that finds the window: it is observed WAITING — blocked by the decision's backend in its
    ``FOR SHARE`` of the state row, before it posts or marks anything. The decision completes:
    January is locked on the gate it read, ``PASSED``. The computation then finds the period
    closed and no window: it runs no pass, leaves the mark where the run set it and completes —
    a fact recorded after the lock, as a late event is.

    Fail-first (measured on the head before the share lock): the computation did not wait — it
    committed during the decision with the mark lowered to 1 Jan 2026, and the decision locked
    January on the gate result it had read before."""
    pending = _january_lock_pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    freeze_datasets = close_commands.snapshots.freeze_datasets
    arriving: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def compute_late() -> None:
        try:
            arriving["stored"] = computed(world.place, pending.group_id)[2]
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            arriving["error"] = error

    computing = threading.Thread(target=compute_late, name="close-run-gate-late-computation")

    def freeze_then_meet_the_computation(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(uow, *args, **kwargs)
        if computing.ident is None:  # once: the fact arrives after the gates and the freeze
            with world.place.uow() as late:
                _recorded(late, pending)
                late.commit()
            with observing_checkouts() as backends:
                decision_pid = backend_pid(uow.session)
                computing.start()
                _, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=decision_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
            seen["waiting"] = computing.is_alive() and not arriving
            seen["mark"] = _mark(world, pending.group_id)
        return datasets

    monkeypatch.setattr(
        close_commands.snapshots, "freeze_datasets", freeze_then_meet_the_computation
    )
    try:
        decided = approve(world.app, pending.request_id, world.marcus)
    finally:
        if computing.ident is not None:
            computing.join(timeout=JOIN_SECONDS)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert not computing.is_alive() and seen["waiting"] is True, (seen, arriving)
    assert "for share" in seen["blocked_in"].lower(), seen["blocked_in"]
    assert seen["mark"] == {KEY: "2026-02-01"}
    # the decision locked the period on the gate it read
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"
    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.certification).where(period_lock.c.period_id == pending.period_id),
    )
    (certified,) = [row for row in lock["certification"] if row["gate_check_code"] == GATE]
    assert (certified["status"], certified["count"]) == ("PASSED", 0)
    # the computation: after the lock, outside any window
    assert "error" not in arriving, arriving
    stored = arriving["stored"]
    assert stored["status"] == "SUCCEEDED"
    assert _lines_of(world.tenant_id, stored["id"]) == 0
    assert _mark(world, pending.group_id) == {KEY: "2026-02-01"}


def test_a_computation_outside_any_window_reads_the_window_once_and_holds_no_state_row(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The share lock costs an ordinary computation nothing (supervisor ruling of 2026-10-01
    02:35, condition 4). No close run exists in the workspace. The statements of one computation
    are recorded: exactly one reads ``close_run`` — the read that finds the window, the only
    ``FOR SHARE`` of ``period_state`` the computation's own code issues — it follows the group
    row's ``FOR UPDATE``, precedes the computation's first INSERT and returns no row: no state
    row is locked and nothing is waited for. The head before the share lock made the same two
    reads, the second without a lock, after the postings instead of before them."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    group_id = UUID(str(booked.combination_group["id"]))
    pending = _Pending(
        world=world,
        request_id="",
        contract_id=UUID(str(booked.contract["id"])),
        group_id=group_id,
        period_id=UUID(int=0),
        state_id=UUID(int=0),
    )
    with world.place.uow() as uow:
        _recorded(uow, pending)  # a new fact, so that the computation is not a replay
        uow.commit()
    statements: list[tuple[str, int]] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append((" ".join(statement.split()), int(cursor.rowcount)))

    recorded_on = app_engine()
    event.listen(recorded_on, "after_cursor_execute", record)
    try:
        stored = computed(world.place, group_id)[2]
    finally:
        event.remove(recorded_on, "after_cursor_execute", record)
    assert stored["status"] == "SUCCEEDED" and stored["replayed"] is False
    window = [i for i, (sql, _) in enumerate(statements) if "FROM erev.close_run" in sql]
    assert len(window) == 1, [statements[i] for i in window]
    sql, rows = statements[window[0]]
    assert sql.startswith("SELECT erev.period_state.id FROM erev.period_state JOIN ")
    assert sql.endswith("FOR SHARE OF period_state")
    assert rows == 0  # outside a window: no row found, so no row locked
    group_lock = next(
        i
        for i, (text, _) in enumerate(statements)
        if "FROM erev.combination_group" in text and text.endswith("FOR UPDATE")
    )
    first_insert = next(
        i for i, (text, _) in enumerate(statements) if text.startswith("INSERT INTO ")
    )
    assert group_lock < window[0] < first_insert
    assert statements[first_insert][0].startswith("INSERT INTO erev.contract_computation ")
    assert _mark(world, group_id) == {}


# --- item CLO-GATE-RUN-2: the mark, the gate and the decision (review of 2026-10-01) --------------


def _invoice(
    number: str, amount: str, day: date, *, key: str = MILESTONE, currency: str = "USD"
) -> EventIn:
    """An invoice line of ``amount`` on the obligation ``key``, issued on ``day``."""
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=day,
        payload=BillingRecordedV1(
            invoice_number=number,
            line_external_id=f"{number}-1",
            obligation_key=key,
            amount=MoneyIn(amount=amount, currency=currency),
            issue_date=day,
        ),
    )


def _deferred(world: worlds.ReportWorld, contract_id: UUID, fact: EventIn) -> None:
    """``fact`` appended to the contract's stream and committed without its computation — an
    append whose computation is left to a job: the contract's group is dirty."""
    with world.place.uow() as uow:
        head = uow.session.execute(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        ).scalar_one()
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=int(head),
            events=[fact],
            origin="UI",
        )
        uow.commit()


def _run_statuses(pending: _Pending) -> list[str]:
    """The statuses of January's close runs, oldest first."""
    return [
        str(getattr(row["status"], "value", row["status"]))
        for row in _rows(
            pending.world.tenant_id,
            select(close_run.c.status)
            .where(close_run.c.period_id == pending.period_id)
            .order_by(close_run.c.created_at, close_run.c.id),
        )
    ]


def test_a_later_periods_run_leaves_the_mark_of_an_unposted_period_end(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GATE-RUN-2, finding F1 (independent review of 2026-10-01; 04 T-CON-03 "Period-end
    mark"; supervisor ruling R-112 (a)). January's lock is requested on its succeeded close run.
    A late invoice of 31 Jan 2026 is then recorded: its computation, inside January's window,
    leaves a reclass of January to post and sets the mark back to 1 Jan 2026 — the gate fails.
    Somebody starts February's close run. Whatever that run does, it is not January's run: the
    mark still says that January's period end is to post, January's gate still fails by name and
    the Controller's decision is refused. January's own run then posts the difference, the gate
    passes, and February's run, resumed, ends and marks February.

    Fail-first (measured on the head before the remedy): the first period-end step of February's
    run passed the group and wrote its mark as 1 Mar 2026, over the lowered one; the run then
    stopped at its reclass, naming January. January's gate read ``PASSED`` and the Controller's
    approval locked January with the reclass of the late invoice unposted."""
    pending = _january_lock_pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    _invoiced(world, pending.contract_id, "INV-POS-5", "1000.00", "2026-01-31")
    assert _mark(world, pending.group_id) == {KEY: "2026-01-01"}
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)

    february = runs.closed(world, monkeypatch, entity_code=US01, period_key=FEBRUARY)
    assert february["status"] == "FAILED"
    (stopped,) = [step for step in february["steps"] if step["status"] == "FAILED"]
    january = worlds.period_state(world, US01, JANUARY)["period"]["name"]
    assert stopped["problem"]["detail"] == EARLIER_FIRST.format(period=january)
    assert runs.posted(world.tenant_id, february["id"]) == []

    # the decision first: what the product does with the period
    world = worlds.verified(world, clock, "marcus")
    refused = approve(world.app, pending.request_id, world.marcus)
    left = (stopped["step_code"], _mark(world, pending.group_id))
    assert refused.status_code == 409, (refused.text, left)
    assert slug(refused) == "close-gates-failed", refused.text
    errors = {error["rule_id"]: error["message"] for error in refused.json()["errors"]}
    assert errors[GATE] == OUT_OF_DATE
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closing"
    assert _mark(world, pending.group_id) == {KEY: "2026-01-01"}
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)

    second = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert second["status"] == "SUCCEEDED"
    assert _reclass(world, second, JANUARY) == LATE_INVOICE
    assert _mark(world, pending.group_id) == {KEY: "2026-02-01"}
    assert _gate(world) == ("PASSED", 0, None)

    done = runs.resumed(world, monkeypatch, february["id"])
    assert done["status"] == "SUCCEEDED"
    assert _mark(world, pending.group_id) == {KEY: "2026-03-01"}
    assert _gate(world) == ("PASSED", 0, None)


def test_a_group_computed_while_the_first_period_end_step_runs_holds_the_gate(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GATE-RUN-2, finding F3 (04 T-CON-03 "Period-end mark"; 05 RCP-08). The EUR
    receivable of ``close_run_worlds.eur_receivable`` — August's close remeasures it, a gain of
    50.00 — holds no mark: no run has passed it; January to July are closed, so August is the
    earliest postable period. August's run has recomputed its dirty groups
    when an invoice of September is recorded with its computation left to a job, so the group is
    dirty when the first period-end step reads its groups; the job computes the group while that
    step runs. The step leaves the group out, and the release and the reclass pass it: the run
    ``SUCCEEDED`` without the group's remeasurement. Nothing recorded says that the group's
    period ends are posted, so the gate fails with the count; the run that is run again posts
    the remeasurement, and the reclass of what the first run could not yet see, and the gate
    passes.

    Fail-first (measured on the head before the remedy): the gate read ``PASSED`` after the
    first run — a group without a mark was read as posted — with no remeasurement in the
    ledger."""
    world = worlds.on_record_clock(
        close_run_worlds.eur_receivable(app, keyring, clock, files), clock
    )
    booked = world.contracts[close_run_worlds.EUR_CONTRACT]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    key = f"{AVM_US}|{BOOK}"
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=world.entity_id, before=AUGUST
    )
    read_groups = period_end._groups
    reads: list[list[tuple[UUID, bool]]] = []

    def read_while_a_computation_is_due(session: Any, scope: Any) -> list[tuple[UUID, bool]]:
        if reads:
            found = read_groups(session, scope)
            reads.append(found)
            return found
        # the first period-end step: the fact arrived after RECOMPUTE_DIRTY, its computation is due
        fact = _invoice("INV-EU-1", "2000.00", date(2026, 9, 10), key="O1", currency="EUR")
        _deferred(world, contract_id, fact)
        found = read_groups(session, scope)
        reads.append(found)
        computed(world.place, group_id)  # the job computes the group while the step runs
        return found

    monkeypatch.setattr(period_end, "_groups", read_while_a_computation_is_due)
    first = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert first["status"] == "SUCCEEDED"
    assert reads[0] == [(group_id, True)]
    assert runs.step(first, FX)["counts"]["groups_skipped"] == 1
    lines = runs.posted(world.tenant_id, first["id"])
    assert runs.by_role(lines, period_key=AUGUST, entry_kind=FX) == {}

    assert _gate(world, AUGUST, AVM_US) == ("FAILED", 1, OUT_OF_DATE), _mark(world, group_id)

    second = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert second["status"] == "SUCCEEDED"
    lines += runs.posted(world.tenant_id, second["id"])
    assert runs.by_role(lines, period_key=AUGUST, entry_kind=FX) == EUR_FX_AUGUST
    assert runs.by_role(lines, period_key=AUGUST, entry_kind=RECLASS) == EUR_RECLASS_AUGUST
    assert _mark(world, group_id) == {key: "2026-09-01"}
    assert _gate(world, AUGUST, AVM_US) == ("PASSED", 0, None)


def test_a_group_with_a_period_end_to_post_holds_the_gate_when_it_is_dirty(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GATE-RUN-2, finding F8 (04 T-CLS-02 ``CLOSE_RUN_COMPLETED``, "never waivable";
    supervisor ruling R-114 (b)). January's close run succeeded. The late invoice of 31 Jan 2026
    is computed inside January's window and leaves a reclass of January to post: the gate fails
    with the count. A further invoice is then recorded with its computation left to a job, so
    the group is dirty, and ``NO_DIRTY_GROUPS`` is waived through the product — Maya asks, Priya
    approves. The period end that was not posted is still not posted: the close-run gate fails
    as before, and the lock request is refused by its name whatever was waived. The run that is
    run again computes the group, posts the difference, and the gate passes.

    Fail-first (measured on the head before the remedy): the close-run gate left a dirty group
    out whatever its mark, so it read ``PASSED`` once the group was dirty, and with
    ``NO_DIRTY_GROUPS`` waived the lock request was accepted with January's reclass unposted."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    _soft_closed(world)
    first = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert first["status"] == "SUCCEEDED"
    world = runs.journal_posted(world, clock, first["journal_run_id"])
    _invoiced(world, contract_id, "INV-POS-5", "1000.00", "2026-01-31")
    assert _mark(world, group_id) == {KEY: "2026-01-01"}
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)

    _deferred(world, contract_id, _invoice("INV-POS-6", "500.00", date(2026, 2, 10)))
    shown = _cockpit(world, JANUARY)
    (dirty,) = [item for item in shown["checklist"] if item["code"] == DIRTY_GATE]
    assert (dirty["status"], dirty["result"]["count"]) == ("FAILED", 1)
    (once_dirty,) = [item for item in shown["checklist"] if item["code"] == GATE]
    waiver = post(
        app,
        f"{PERIODS}/{shown['period']['id']}/checklist/{dirty['id']}/waive",
        world.maya,
        {"reason": "INV-POS-6 is a February invoice; its computation follows the close."},
        if_match=f'"r{shown["period"]["row_version"]}"',
    )
    assert waiver.status_code == 200, waiver.text
    world = worlds.verified(world, clock, "priya")
    waived = approve(app, str(waiver.json()["approval_request_id"]), world.priya)
    assert (waived.status_code, waived.json()["status"]) == (200, "APPROVED"), waived.text
    _reconciled(world, clock)

    # the lock request first: what the product does with the period
    refused = _lock_requested(world)
    served = (once_dirty["status"], once_dirty["result"]["count"], once_dirty["result"]["detail"])
    assert refused.status_code == 409, (refused.text, served)
    assert slug(refused) == "close-gates-failed", refused.text
    errors = {error["rule_id"]: error["message"] for error in refused.json()["errors"]}
    assert errors == {GATE: OUT_OF_DATE}
    assert served == ("FAILED", 1, OUT_OF_DATE)
    assert _gate(world) == ("FAILED", 1, OUT_OF_DATE)
    assert _mark(world, group_id) == {KEY: "2026-01-01"}

    second = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert second["status"] == "SUCCEEDED"
    assert runs.step(second, "RECOMPUTE_DIRTY")["counts"]["groups_recomputed"] == 1
    assert _reclass(world, second, JANUARY) == LATE_INVOICE
    assert _mark(world, group_id) == {KEY: "2026-02-01"}
    assert _gate(world) == ("PASSED", 0, None)


# --- the decision and the other requests of its period (findings F5 and F6) -----------------------


@dataclass(frozen=True)
class _Met:
    """A request that met the lock decision: whether it was seen waiting for the decision's
    backend, the statement it waited in, what it answered and what the decision answered."""

    waited: bool
    blocked_in: str
    answered: Any
    decided: Any


def _task_items(pending: _Pending, template_id: UUID) -> int:
    """The items January holds of the close task ``template_id``."""
    (row,) = _rows(
        pending.world.tenant_id,
        select(func.count().label("items"))
        .select_from(close_checklist_item)
        .where(
            close_checklist_item.c.close_checklist_template_id == template_id,
            close_checklist_item.c.period_id == pending.period_id,
        ),
    )
    return int(row["items"])


def _during_the_decision(
    pending: _Pending, monkeypatch: pytest.MonkeyPatch, request: Callable[[], Any], *, name: str
) -> _Met:
    """Marcus decides January's lock; ``request`` is made from another session once the decision
    has evaluated its gates and frozen its datasets, before it writes the lock. The request is
    watched until it has answered or one of its backends is blocked by the decision's backend;
    the decision then completes."""
    world = pending.world
    freeze_datasets = close_commands.snapshots.freeze_datasets
    outcome: dict[str, Any] = {}
    seen: dict[str, Any] = {"waited": False, "blocked_in": ""}

    def make() -> None:
        try:
            outcome["answered"] = request()
        except Exception as error:  # noqa: BLE001 - surfaced by the assertion below
            outcome["error"] = error

    other = threading.Thread(target=make, name=name)

    def freeze_then_meet_the_request(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(uow, *args, **kwargs)
        if other.ident is not None:
            return datasets
        with observing_checkouts() as backends:
            decision_pid = backend_pid(uow.session)
            other.start()
            deadline = time.monotonic() + WAIT_SECONDS
            while other.is_alive() and time.monotonic() < deadline:
                pids = sorted(backends.pids - {decision_pid})
                blocked = fresh_activity(
                    uow.session, BLOCKED_BY_HOLDER, {"pids": pids, "holder": decision_pid}
                ).all()
                if blocked:
                    seen["waited"] = other.is_alive() and not outcome
                    seen["blocked_in"] = str(blocked[0].query)
                    break
                time.sleep(0.05)
        return datasets

    monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_meet_the_request)
    try:
        decided = approve(world.app, pending.request_id, world.marcus)
    finally:
        if other.ident is not None:
            other.join(timeout=JOIN_SECONDS)
    assert not other.is_alive() and "error" not in outcome, outcome
    return _Met(
        waited=bool(seen["waited"]),
        blocked_in=str(seen["blocked_in"]),
        answered=outcome["answered"],
        decided=decided,
    )


def test_a_close_run_started_while_the_lock_is_decided_waits_and_is_refused(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-RUN-START-PIN-1 (finding F5 of the review of 2026-10-01; from lane F-CLO-A's
    reading, 05 §5.6; 04 DB-07; dev-guide DG-KRN-DB-08). The decision has read its gates — the
    latest close run ``SUCCEEDED`` — and holds January's state row. ``POST /close-runs`` for
    January arrives: it is seen waiting for the decision, in its read of the state row, and once
    January is ``closed`` it is refused by name and starts nothing. January keeps one close run,
    the one its lock certified.

    Fail-first (measured on the head before the pin): the start read the state without the row,
    answered 202 while the decision was in flight, and left a ``PENDING`` close run with a queued
    job in a period that was ``closed`` a moment later."""
    pending = _january_lock_pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    assert _run_statuses(pending) == ["SUCCEEDED"]
    met = _during_the_decision(
        pending,
        monkeypatch,
        lambda: runs.start(world.app, world.maya, entity_code=US01, period_key=JANUARY),
        name="close-run-start",
    )
    decided, started = met.decided, met.answered
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"
    assert met.waited, (started.status_code, started.text, _run_statuses(pending))
    assert "period_state" in met.blocked_in and "for share" in met.blocked_in.lower()
    assert (started.status_code, slug(started)) == (409, "invalid-transition"), started.text
    assert started.json()["detail"] == NOT_OPEN.format(period_key=JANUARY, entity=US01, book=BOOK)
    assert _run_statuses(pending) == ["SUCCEEDED"]


def test_a_superseded_close_run_is_not_resumed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-RUN-START-PIN-1, the resume (finding F5; 04 §16.8 rev 1.228). A close run of
    January fails — its worker dies — and a second run is started and succeeds: the gate reads
    the second, the period's latest. ``POST /close-runs/{id}/resume`` for the first is refused by
    name; it stays ``FAILED`` and no job is deferred for it. Positive control: a third run that
    fails the same way is the period's latest run and is resumed.

    Fail-first (measured on the head before the rule): the resume answered 202. Beside a lock
    decision that meant a run ``RUNNING`` while the gate read the succeeded run alone — the lock
    was approved, and the resumed run's job then executed its thirteen steps in the closed
    period."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)

    def failed_run() -> dict[str, Any]:
        run_id, job_id = runs.started(app, world.maya, entity_code=US01, period_key=JANUARY)
        died = runs.dead_lettered(world.tenant_id, world.runtime, job_id)
        assert str(getattr(died["state"], "value", died["state"])) == "FAILED"
        found = runs.shown(app, world.maya, run_id)
        assert found["status"] == "FAILED"
        return found

    def jobs_of(run_id: str) -> int:
        (row,) = _rows(
            world.tenant_id,
            select(func.count().label("n"))
            .select_from(job)
            .where(job.c.subject_id == UUID(run_id)),
        )
        return int(row["n"])

    first = failed_run()
    second = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert second["status"] == "SUCCEEDED"
    assert _gate(world) == ("PASSED", 0, None)

    refused = runs.resume(app, world.maya, first["id"])
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "invalid-transition"
    assert refused.json()["detail"] == SUPERSEDED.format(no=first["close_run_no"])
    assert runs.shown(app, world.maya, first["id"])["status"] == "FAILED"
    assert jobs_of(first["id"]) == 1
    assert _gate(world) == ("PASSED", 0, None)

    third = failed_run()
    assert _gate(world) == ("FAILED", 1, f"Close run {third['close_run_no']} is Failed")
    resumed = runs.resume(app, world.maya, third["id"])
    assert resumed.status_code == 202, resumed.text
    assert runs.shown(app, world.maya, third["id"])["status"] == "RUNNING"
    assert jobs_of(third["id"]) == 2


def test_a_resume_pins_the_state_row_before_its_run_row(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item CLO-RUN-START-PIN-1 and the lock order (dev-guide DG-KRN-DB-08 rev 1.216). Of the
    statements of ``POST /close-runs/{id}/resume``: the advisory key of the entity, book and
    period, then the read of the period's state row ``FOR SHARE``, then the run's own row ``FOR
    UPDATE`` — the state row before a ``close_run`` row, the order of the lock decision. The
    head before the pin locked the run row first and read the state without a lock."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    run_id, job_id = runs.started(app, world.maya, entity_code=US01, period_key=JANUARY)
    runs.dead_lettered(world.tenant_id, world.runtime, job_id)
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append(" ".join(statement.split()))

    recorded_on = app_engine()
    event.listen(recorded_on, "after_cursor_execute", record)
    try:
        resumed = runs.resume(app, world.maya, run_id)
    finally:
        event.remove(recorded_on, "after_cursor_execute", record)
    assert resumed.status_code == 202, resumed.text

    def first(found: Callable[[str], bool]) -> int:
        return next(index for index, sql in enumerate(statements) if found(sql))

    key = first(lambda sql: "pg_advisory_xact_lock" in sql)
    pin = first(
        lambda sql: "FROM erev.period_state" in sql and sql.endswith("FOR SHARE OF period_state")
    )
    row = first(lambda sql: "FROM erev.close_run" in sql and sql.endswith("FOR UPDATE"))
    assert key < pin < row, (key, pin, row)


def test_a_cockpit_read_that_meets_the_lock_decision_leaves_the_certified_checklist(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GATE-RUN-2, finding F6 (04 T-CLS-03 "a closed period keeps the results certified
    at lock"; BUILD_SPEC CLO-6; security finding SC-8). January's lock is requested and nobody
    has read its cockpit since: the stored checklist is the one the request evaluated, and a
    reader now has something to store — the item of a close task created after the request.
    ``GET /periods/{id}/cockpit`` arrives while the lock is decided: it evaluated the gates of a
    period in soft close, and what it would store waits for the decision. Once January is
    ``closed`` the read stores nothing: the checklist holds, gate by gate, the status the lock
    certified — the Controller's certification ``PASSED`` — and the read is answered with that
    checklist.

    What the reader has to store (item CLO-LOCK-REQUEST-OWN-GATE-1; 04 §16.8 ``blockers`` rev
    1.311): until that item it was the pending lock request itself, counted among the entity's
    pending approvals — ``APPROVALS_CLEARED`` ``FAILED`` between the request and the decision.
    The request is no pending approval of its own period now, so a reader of January alone
    stores nothing and takes no lock. The world therefore gives it another difference that does
    not fail the decision: a close task that is not blocking, created after the request, whose
    item January lacks. The race is the same one, and every assertion below stands.

    Fail-first (measured on the head before the remedy): the read never looked at the period's
    state again; after the decision's commit it stored its evaluation from before the lock,
    without an audit event — the closed period's checklist said "Pending approvals: 1" and
    "Awaiting Controller certification at lock"."""
    pending = _january_lock_pending(app, keyring, clock, files, monkeypatch)
    world = pending.world
    admin_member = colleague(world.tenant_id, "tess")
    assign(admin_member, "tenant_admin")
    admin = enrolled(world.app, clock, admin_member)  # settings.manage: an MFA-verified session
    created = post(
        world.app,
        TEMPLATES,
        admin,
        {
            "code": "FYI-NOTE",
            "name": "Note for next period",
            "gate_kind": "MANUAL",
            "is_blocking": False,
            "due_offset_days": 3,
        },
    )
    assert created.status_code == 201, created.text
    task_id = UUID(str(created.json()["id"]))
    # the lock request waits and is no pending approval of January: the task is what differs
    waiting = get(world.app, f"{PERIODS}/{pending.state_id}", world.maya)
    assert waiting.json()["blockers"]["approvals_pending"] == 0, waiting.text
    assert _task_items(pending, task_id) == 0
    met = _during_the_decision(
        pending,
        monkeypatch,
        lambda: get(world.app, f"{PERIODS}/{pending.state_id}/cockpit", world.maya),
        name="cockpit-read",
    )
    decided, shown = met.decided, met.answered
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"
    assert met.waited and shown.status_code == 200, (met, shown.text)
    # the wait is the reader's pin of the state row, taken once it had found something to store
    assert "period_state" in met.blocked_in and "for share" in met.blocked_in.lower(), met

    (lock,) = _rows(
        world.tenant_id,
        select(period_lock.c.certification).where(period_lock.c.period_id == pending.period_id),
    )
    certified = {str(row["gate_check_code"]): str(row["status"]) for row in lock["certification"]}
    assert certified[CERTIFIED_GATE] == "PASSED" and len(certified) == 14
    item, template = close_checklist_item, close_checklist_template
    stored = {
        str(row["gate_check_code"]): str(getattr(row["status"], "value", row["status"]))
        for row in _rows(
            world.tenant_id,
            select(template.c.gate_check_code, item.c.status)
            .select_from(
                item.join(
                    template,
                    and_(
                        template.c.tenant_id == item.c.tenant_id,
                        template.c.id == item.c.close_checklist_template_id,
                    ),
                )
            )
            .where(item.c.period_id == pending.period_id, template.c.gate_check_code.is_not(None)),
        )
    }
    assert stored == certified
    answered = {
        str(row["code"]): str(row["status"])
        for row in shown.json()["checklist"]
        if row["code"] in certified
    }
    assert answered == certified
    # the task's item is the decision's own, created once under the state row: the read, which
    # waited to create it, stored none
    assert _task_items(pending, task_id) == 1


# --- a mark in a closed period (item CLO-GATE-RUN-2, second part) ---------------------------------


def _refusable(monkeypatch: pytest.MonkeyPatch, external_id: str) -> dict[str, bool]:
    """The engine refuses the group of the contract ``external_id`` with
    ``ENGINE_INVARIANT_VIOLATED`` while the switch it answers is on, and computes as it does
    otherwise."""
    real = computation.default_engine()
    switch = {"on": False}

    def run(bundle: InputBundle) -> OutputBundle:
        if switch["on"] and any(item.contract_key == external_id for item in bundle.events):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the allocated amounts do not sum to the transaction price",
                subject_key=f"{external_id}/{MILESTONE}",
                detail={"identity": "DB-17 V1"},
            )
        return real(bundle)

    monkeypatch.setattr(computation, "default_engine", lambda: run)
    return switch


def _stopped(run: Mapping[str, Any]) -> list[tuple[str, str]]:
    """(step, detail) of the steps of ``run`` that failed."""
    return [
        (str(step["step_code"]), str(step["problem"]["detail"]))
        for step in run["steps"]
        if step["status"] == "FAILED"
    ]


def test_a_mark_a_waived_quarantine_left_in_a_closed_period_does_not_stop_the_next_close(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GATE-RUN-2, second part (04 T-CON-03 "Period-end mark" and T-CLS-01 "Period-end
    steps" rev 1.228; T-CLS-01 "Ends of a run"; the supervisor's ruling of 2026-10-01 15:01).
    January's close run succeeded and a late invoice of 31 Jan 2026 set the group's mark back to
    1 Jan 2026. The engine then refuses the group's next computation: the group is quarantined
    and dirty, and no step passes it. Maya asks for the waiver of its exception item and of
    ``NO_DIRTY_GROUPS``, Priya approves both, and the Controller locks January: what the two
    approved waivers let pass. The mark of 1 Jan 2026 now lies in a closed period. In February
    the cause is corrected and a further fact computes the group — a computation never raises a
    mark. February's close run passes the group like one without a mark: a close run posts
    nothing into a closed period, so the mark says no more than the closed periods do. The run
    posts February's own reclass — CHK-010 at 28 Feb 2026: Dr unbilled receivable 3,000.00, Dr
    contract asset 250.00 / Cr contract liability 3,250.00 — and marks the group 1 Mar 2026.

    Fail-first (measured on the head before the second part): February's run ended ``FAILED``
    at its first period-end step, "Jan 2026 has period-end amounts no close run has posted; run
    its close first." — for a period that is closed, where no close run can be started."""
    world = worlds.on_record_clock(worlds.chk_010_position(app, keyring, clock, files), clock)
    booked = world.contracts[worlds.C_POS]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    refusing = _refusable(monkeypatch, worlds.C_POS)
    _soft_closed(world)
    first = runs.closed(world, monkeypatch, entity_code=US01, period_key=JANUARY)
    assert first["status"] == "SUCCEEDED"
    world = runs.journal_posted(world, clock, first["journal_run_id"])
    _invoiced(world, contract_id, "INV-POS-5", "1000.00", "2026-01-31")
    assert _mark(world, group_id) == {KEY: "2026-01-01"}

    # the engine refuses the group's next computation: quarantined, with a blocking engine item
    refusing["on"] = True
    sent = worlds._appended_through_api(
        world.place,
        contract_id,
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-02-10",
            "payload": {
                "invoice_number": "INV-POS-6",
                "line_external_id": "INV-POS-6-1",
                "obligation_key": MILESTONE,
                "amount": {"amount": "500.00", "currency": "USD"},
                "issue_date": "2026-02-10",
            },
        },
    )
    assert sent["computation"]["status"] == "QUARANTINED", sent["computation"]
    (item,) = _rows(
        world.tenant_id,
        select(exception_item.c.id, exception_item.c.code).where(
            exception_item.c.combination_group_id == group_id
        ),
    )
    assert item["code"] == "ENGINE_INVARIANT_VIOLATION"
    asked = post(
        app,
        f"/api/v1/exceptions/{item['id']}/request-waiver",
        world.maya,
        {"comment": "The allocation of C-POS is corrected in February; January closes without it."},
    )
    assert asked.status_code == 200, asked.text
    world = worlds.verified(world, clock, "priya")
    granted = approve(app, str(asked.json()["approval_request_id"]), world.priya)
    assert (granted.status_code, granted.json()["status"]) == (200, "APPROVED"), granted.text

    # the waived quarantine stands: NO_DIRTY_GROUPS alone holds the group, and is waived too
    shown = _cockpit(world, JANUARY)
    (dirty,) = [row for row in shown["checklist"] if row["code"] == DIRTY_GATE]
    assert (dirty["status"], dirty["result"]["count"]) == ("FAILED", 1)
    assert _gate(world) == ("PASSED", 0, None)
    waiver = post(
        app,
        f"{PERIODS}/{shown['period']['id']}/checklist/{dirty['id']}/waive",
        world.maya,
        {"reason": "The quarantine of C-POS is waived; its computation follows the close."},
        if_match=f'"r{shown["period"]["row_version"]}"',
    )
    assert waiver.status_code == 200, waiver.text
    world = worlds.verified(world, clock, "priya")
    waived = approve(app, str(waiver.json()["approval_request_id"]), world.priya)
    assert (waived.status_code, waived.json()["status"]) == (200, "APPROVED"), waived.text
    _reconciled(world, clock)
    requested = _lock_requested(world)
    assert requested.status_code == 200, requested.text
    world = worlds.verified(world, clock, "marcus")
    locked = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (locked.status_code, locked.json()["status"]) == (200, "APPROVED"), locked.text
    assert worlds.period_state(world, US01, JANUARY)["state"] == "closed"
    assert _mark(world, group_id) == {KEY: "2026-01-01"}  # in a closed period

    # a period later: the cause is corrected, and a further fact computes the group
    refusing["on"] = False
    _invoiced(world, contract_id, "INV-POS-7", "250.00", "2026-02-15")
    assert _mark(world, group_id) == {KEY: "2026-01-01"}  # a computation never raises a mark

    february = runs.closed(world, monkeypatch, entity_code=US01, period_key=FEBRUARY)
    assert february["status"] == "SUCCEEDED", _stopped(february)
    assert runs.step(february, FX)["counts"]["groups_skipped"] == 0
    assert _reclass(world, february, FEBRUARY) == CHK_010_FEBRUARY
    assert _mark(world, group_id) == {KEY: "2026-03-01"}
    assert _gate(world, FEBRUARY) == ("PASSED", 0, None)


def test_the_refusal_over_a_mark_names_a_postable_period_never_a_closed_one(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLO-GATE-RUN-2, second part (04 T-CLS-01 "Period-end steps" rev 1.228). The EUR
    receivable of ``close_run_worlds.eur_receivable``; January to July are closed and the
    group's mark is 1 Jul 2026 — set by a fixture row: the mark a group keeps when its
    quarantine stood waived over July's lock (the witness above reaches one through the
    product). September's close run is started first. Its first period-end step is refused, and
    the period it names is August — the earliest postable period that ends on or after the mark
    — never July, which no close run can be started for. August's own run then passes the
    group: it posts August's remeasurement, a gain of 50.00, and the reclass of 11,050.00, and
    marks the group 1 Sep 2026. September's run, resumed, posts its own remeasurement — 150.00
    — and marks 1 Oct 2026.

    Fail-first (measured on the head before the second part): September's run was refused
    naming "Jul 2026", and so was August's."""
    world = worlds.on_record_clock(
        close_run_worlds.eur_receivable(app, keyring, clock, files), clock
    )
    booked = world.contracts[close_run_worlds.EUR_CONTRACT]
    group_id = UUID(str(booked.combination_group["id"]))
    key = f"{AVM_US}|{BOOK}"
    periods_closed_before(
        world.place, world.app, world.maya, entity_id=world.entity_id, before=AUGUST
    )
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(combination_group)
            .where(combination_group.c.id == group_id)
            .values(period_ends_open={key: "2026-07-01"})
        )
    august_name = worlds.period_state(world, AVM_US, AUGUST)["period"]["name"]

    september = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert september["status"] == "FAILED"
    assert _stopped(september) == [(FX, EARLIER_FIRST.format(period=august_name))]
    assert runs.posted(world.tenant_id, september["id"]) == []
    assert _mark(world, group_id) == {key: "2026-07-01"}

    august = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert august["status"] == "SUCCEEDED", _stopped(august)
    lines = runs.posted(world.tenant_id, august["id"])
    assert runs.by_role(lines, period_key=AUGUST, entry_kind=FX) == EUR_FX_AUGUST
    assert runs.by_role(lines, period_key=AUGUST, entry_kind=RECLASS) == EUR_RECLASS_AUGUST
    assert _mark(world, group_id) == {key: "2026-09-01"}
    assert _gate(world, AUGUST, AVM_US) == ("PASSED", 0, None)

    done = runs.resumed(world, monkeypatch, september["id"])
    assert done["status"] == "SUCCEEDED", _stopped(done)
    lines = runs.posted(world.tenant_id, done["id"])
    assert runs.by_role(lines, period_key=SEPTEMBER, entry_kind=FX) == EUR_FX_SEPTEMBER
    assert _mark(world, group_id) == {key: "2026-10-01"}
