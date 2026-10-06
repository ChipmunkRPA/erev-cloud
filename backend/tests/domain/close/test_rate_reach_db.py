"""The close runs around a corrected rate, and the rows its approval takes (item
FX-REPUBLISH-DIRTY-1; supervisor ruling R-116 (b) and the rulings of 2026-10-02 on the lane's
pre-build line and of 21:37Z on a rate corrected between two closed periods; 04 T-REF-11 "The
groups a changed rate reaches" rev 1.297; 05 RCP-17, RCP-19 rev 1.206; dev-guide DG-KRN-DB-08 rev
1.281; PRD IMP-144 rev 1.200; BUILD_SPEC CLO-19).

The approval of an FX rate set version marks the contract groups its changed rates reach
(``close.rate_reach``), in front of the finding of a rate changed after a lock
(``close.rate_changes``). The mark and its trigger in the world of one contract are
``tests/domain/contracts/test_fx_republish_mark.py``; here, through the product's close:

- a closing rate corrected in a closed period that is followed by another closed period: which
  groups are marked, which period's lock the finding holds, and what the next open period's run
  posts for a balance open through both and for one settled inside the second, to the cent;
- the approval's group rows against a computation: the approval waits for one that holds a
  group it marks, and one that arrives waits for the approval and reads its version;
- the limit: a group that a computation in flight puts into the reach is not marked — stored
  on the earlier rate where the computation commits before the approval does or the version
  is published after its cutoff, and not stored at all where the approval commits first and
  the cutoff admits the version.

World: ``close_run_worlds.eur_receivable`` — AVM-US (USD); the PRD §2.5 EUR to USD rates, 1.100000
for every rate of January to July, August average 1.100000 and closing 1.105000, September
average 1.110000 and closing 1.120000; ``SF-ORD-EU-3001`` delivers 100 hours at EUR 100.00 on 31
August and is never invoiced.
"""

from __future__ import annotations

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
    combination_group,
    contract,
    contract_computation,
    exception_item,
    fx_rate_set_version,
    period,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.contracts import compute_job, period_ends
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import out_of_period_register as register
from erev_api.enums import ComputationStatus, ComputationTrigger
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import and_, select, text
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.close_world import periods_closed_before
from support.db import TestDatabase
from support.factories import booked_contract
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import PERIODS, approve, get, post, slug

AVM_US = worlds.AVM_US
JULY, AUGUST, SEPTEMBER = "FY2026-P07", "FY2026-P08", "FY2026-P09"
FX = "FX_REMEASUREMENT"
FX_REPUBLISH = ComputationTrigger.FX_REPUBLISH.value
CODE = "FX_RATE_CHANGED_AFTER_LOCK"
EXCEPTIONS = "/api/v1/exceptions"
FIRST = close_run_worlds.EUR_CONTRACT  # begins on 1 August
OPEN, SETTLED, RESTING = "SF-ORD-EU-3002", "SF-ORD-EU-3003", "SF-ORD-EU-3004"
WAIT_SECONDS = 8.0  # under the sessions' lock_timeout of 10 s
JOIN_SECONDS = 120.0
# ``rate_reach.rows_statement`` as the server shows a backend that waits in it:
# ``pg_stat_activity.query`` holds the first 1,024 bytes of a statement
# (``track_activity_query_size``) and this one begins with its CTE — the words
# ``combination_group`` and ``FOR UPDATE`` come after them. The statement is known by its head,
# and the row it waits for by the lock the waiting backend holds meanwhile (``_rows_awaited``).
ROWS_HEAD = "with reach as"
TUPLES_HELD = text(
    "SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid = l.relation "
    "WHERE l.pid = :pid AND l.locktype = 'tuple' AND l.granted ORDER BY c.relname"
)
# The tables whose rows a backend has locked, or asked for, so far in its transaction: a
# ``FOR UPDATE`` or ``FOR SHARE`` takes ``RowShareLock`` on each table it locks rows of when the
# statement starts, and keeps it to the transaction's end.
ROW_LOCKED = text(
    "SELECT DISTINCT c.relname FROM pg_locks l JOIN pg_class c ON c.oid = l.relation "
    "WHERE l.pid = :pid AND l.locktype = 'relation' AND l.mode = 'RowShareLock' AND l.granted "
    "ORDER BY c.relname"
)
# PRD IMP-144 rev 1.200, the last part of the message, for an item whose difference posts to
# September.
POSTED = (
    " The difference is not computed here. What remains of it to post goes to FY2026-P09. The "
    "contracts the changed rates reach are recalculated by the next close run of their "
    "contracting entity or by the next change to them: what the rates change in the amounts "
    "of their events is posted with the closed period of each event as origin period, and the "
    "out-of-period register lists it as Fx republish or with the event that carried it. The "
    "close run of FY2026-P09 posts what remains of a period-end remeasurement as an amount of "
    "that period, without an origin period. Where nothing remains nothing is posted: a closing "
    "rate of a period that is followed by another closed period moves an amount between the two "
    "for a balance open through both."
)

Line = tuple[str, str, str, str, str]  # contract, posting period, origin period, role, functional


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


# --- the world's further contracts and what is read of them ---------------------------------------


def _hours(
    world: worlds.ReportWorld, external_id: str, start: str, *, delivered_on: str | None
) -> tuple[UUID, UUID]:
    """Another EUR contract of AVM-US like ``SF-ORD-EU-3001`` — 100 hours at EUR 100.00 from
    ``start`` — booked and activated, its hours delivered on ``delivered_on`` (Priya approves
    Maya's delivery, and the approval computes) or not at all. (contract id, group id)."""
    first = world.contracts[FIRST].contract
    booked = booked_contract(
        world.place,
        {
            "external_id": external_id,
            "customer_id": str(first["customer_id"]),
            "contracting_entity_code": AVM_US,
            "transaction_currency": "EUR",
            "inception_date": start,
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": close_run_worlds.EUR_HOURS,
                    "quantity": "100",
                    "total_price": {"amount": "0.00", "currency": "EUR"},
                    "unit_price": "100.00",
                    "start_date": start,
                    "end_date": "2026-12-31",
                }
            ],
        },
        activate=True,
    )
    contract_id = UUID(str(booked.contract["id"]))
    if delivered_on is not None:
        recorded = worlds.approved_manual_events(
            world.place,
            world.priya,
            contract_id,
            _delivery(delivered_on, "100"),
            evidence_file_ids=[],
        )
        assert recorded["computation"]["status"] == "SUCCEEDED", recorded["computation"]
    return contract_id, UUID(str(booked.combination_group["id"]))


def _delivery(on: str, hours: str) -> dict[str, Any]:
    return {
        "event_type": "DELIVERY_RECORDED",
        "effective_date": on,
        "payload": {"obligation_key": "O1", "quantity": hours, "trigger": "DELIVERY"},
    }


def _invoice(number: str, on: str, amount: str) -> dict[str, Any]:
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": on,
        "payload": {
            "invoice_number": number,
            "line_external_id": f"{number}-1",
            "obligation_key": "O1",
            "amount": {"amount": amount, "currency": "EUR"},
            "issue_date": on,
        },
    }


def _mark(world: worlds.ReportWorld, group_id: UUID) -> tuple[Any, str | None]:
    """(``dirty_since``, ``dirty_trigger``) of the group."""
    (row,) = close_run_worlds.rows(
        world.tenant_id,
        select(combination_group.c.dirty_since, combination_group.c.dirty_trigger).where(
            combination_group.c.id == group_id
        ),
    )
    trigger = row["dirty_trigger"]
    return row["dirty_since"], None if trigger is None else str(getattr(trigger, "value", trigger))


def _published_at(world: worlds.ReportWorld, set_code: str) -> Any:
    """``published_at`` of the latest version of the rate set: the instant of its approval."""
    listed = get(world.app, close_run_worlds.FX_RATE_SETS, world.maya, {"limit": 50})
    assert listed.status_code == 200, listed.text
    (found,) = [item for item in listed.json()["items"] if item["code"] == set_code]
    (row,) = close_run_worlds.rows(
        world.tenant_id,
        select(fx_rate_set_version.c.published_at, fx_rate_set_version.c.id)
        .where(fx_rate_set_version.c.fx_rate_set_id == UUID(str(found["id"])))
        .order_by(fx_rate_set_version.c.version_no.desc())
        .limit(1),
    )
    return row["published_at"]


def _fx_lines(world: worlds.ReportWorld, period_key: str) -> list[Line]:
    """The ``FX_REMEASUREMENT`` lines posted in the period, of every contract: (contract,
    posting period, origin period or "-", account role, functional amount, debit positive)."""
    origin = period.alias("origin_period")
    found = close_run_worlds.rows(
        world.tenant_id,
        select(
            contract.c.external_id,
            period.c.period_key,
            origin.c.period_key.label("origin_key"),
            subledger_line.c.account_role,
            subledger_line.c.amount_functional,
        )
        .select_from(
            subledger_line.join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            )
            .join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
            .outerjoin(
                origin,
                and_(
                    origin.c.tenant_id == subledger_line.c.tenant_id,
                    origin.c.id == subledger_line.c.origin_period_id,
                ),
            )
        )
        .where(subledger_line.c.entry_kind == FX, period.c.period_key == period_key),
    )
    return sorted(
        (
            str(row["external_id"]),
            str(row["period_key"]),
            str(row["origin_key"] or "-"),
            str(row["account_role"]),
            f"{Decimal(row['amount_functional']):.2f}",
        )
        for row in found
    )


def _computations(world: worlds.ReportWorld, group_id: UUID) -> list[tuple[str, int]]:
    """(trigger, number of lines posted) of the group's computations, oldest first."""
    found = close_run_worlds.rows(
        world.tenant_id,
        select(contract_computation.c.id, contract_computation.c.trigger)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at, contract_computation.c.id),
    )
    listed = []
    for row in found:
        lines = close_run_worlds.rows(
            world.tenant_id,
            select(subledger_line.c.id)
            .select_from(
                subledger_line.join(
                    subledger_posting,
                    and_(
                        subledger_posting.c.tenant_id == subledger_line.c.tenant_id,
                        subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                    ),
                )
            )
            .where(subledger_posting.c.contract_computation_id == row["id"]),
        )
        listed.append((str(getattr(row["trigger"], "value", row["trigger"])), len(lines)))
    return listed


def _items(world: worlds.ReportWorld) -> list[dict[str, Any]]:
    return close_run_worlds.rows(
        world.tenant_id,
        select(exception_item)
        .where(exception_item.c.code == CODE)
        .order_by(exception_item.c.exception_no),
    )


def _soft_closed(world: worlds.ReportWorld, period_key: str, comment: str) -> None:
    state = worlds.period_state(world, AVM_US, period_key)
    started = post(
        world.app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": comment},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text


def _august_locked(
    world: worlds.ReportWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> tuple[worlds.ReportWorld, dict[str, Any]]:
    """August closed through the product on its own close run, as
    ``close_run_worlds.august_locked`` takes it there. (the world, API-S-CloseRun)."""
    _soft_closed(world, AUGUST, "August close")
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None), run
    world = close_run_worlds.journal_and_reconciliations(world, clock, run)
    requested = close_run_worlds.request_lock(world)
    assert requested.status_code == 200, requested.text
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    decided = approve(world.app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, AVM_US, AUGUST)["state"] == "closed"
    return world, run


def _register(world: worlds.ReportWorld, clock: FrozenClock) -> list[dict[str, Any]]:
    """RPT-16, the out-of-period register of AVM-US over 2026, built as a live run: its rows."""
    with world.place.uow() as uow:
        data = register.build(
            uow,
            ReportParams(
                report_code=register.CODE,
                report_version=1,
                parameters={"from_period_key": "FY2026-P01", "to_period_key": "FY2026-P12"},
                entity_ids=(world.entity_id,),
                known_at=clock.now(),
                historical=False,
            ),
        )
    return [dict(row) for row in data.rows]


# --- a closing rate corrected between two closed periods -----------------------------------------


def test_a_closing_rate_corrected_between_two_closed_periods_posts_what_remains(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor's case of 2026-10-02 21:37Z. Three contracts of AVM-US in EUR:

    - ``SF-ORD-EU-3002`` delivers EUR 10,000.00 on 31 July and is never invoiced: a balance open
      through July and August;
    - ``SF-ORD-EU-3003`` delivers the same on 31 July and is invoiced in full on 20 August: a
      balance settled inside the second period;
    - ``SF-ORD-EU-3001``, the world's, begins on 1 August.

    July is closed (fixture state, as the world closes its earlier periods), August through the
    product on its own run, which posts August's remeasurement of the two open balances: 50.00
    each at the closing rate 1.105000 against 1.100000. Then July's closing rate is corrected
    from 1.100000 to 1.110000.

    The approval marks the two groups at work in July and not the one that begins after it. The
    finding is ONE item, of July — the closed period that holds the changed date — and an item
    of September, the first postable period after it, past August: it is September's lock it
    holds. September's run then computes the two marked groups under ``FX_REPUBLISH`` and
    posts, to the cent:

    - for the balance open through both: its 150.00 of September and no more — July's
      remeasurement would have been 100.00 more and August's 100.00 less, and at August's end
      nothing remains;
    - for the balance settled in August: the recompute posts the difference at the settlement,
      -100.00, with August as origin period, and the run's pass posts July's remeasurement,
      100.00, without one — nil in all, and the register lists the first as "Fx republish";
    - for the contract that began in August: its own 150.00."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    first_group = UUID(str(world.contracts[FIRST].combination_group["id"]))
    _, open_group = _hours(world, OPEN, "2026-07-01", delivered_on="2026-07-31")
    settled_id, settled_group = _hours(world, SETTLED, "2026-07-01", delivered_on="2026-07-31")
    periods_closed_before(
        world.place, app, world.maya, entity_id=world.entity_id, before=AUGUST, entity_code=AVM_US
    )
    invoiced = worlds._appended_through_api(
        world.place, settled_id, _invoice("INV-EU-3003", "2026-08-20", "10000.00")
    )
    assert invoiced["computation"]["status"] == "SUCCEEDED", invoiced["computation"]
    world, august_run = _august_locked(world, clock, monkeypatch)
    assert _fx_lines(world, AUGUST) == [
        (FIRST, AUGUST, "-", "CONTRACT_LIABILITY", "50.00"),
        (FIRST, AUGUST, "-", "FX_GAIN_LOSS", "-50.00"),
        (OPEN, AUGUST, "-", "CONTRACT_LIABILITY", "50.00"),
        (OPEN, AUGUST, "-", "FX_GAIN_LOSS", "-50.00"),
    ]
    assert [_mark(world, group) for group in (first_group, open_group, settled_group)] == [
        (None, None)
    ] * 3

    # --- July's closing rate is corrected: two periods are closed behind it --------------------
    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {JULY: "1.110000"})
    stamped = _published_at(world, close_run_worlds.CLOSING_SET)
    assert _mark(world, open_group) == (stamped, FX_REPUBLISH)
    assert _mark(world, settled_group) == (stamped, FX_REPUBLISH)
    assert _mark(world, first_group) == (None, None)  # it begins after the reach's last day

    (item,) = _items(world)
    july = worlds.period_state(world, AVM_US, JULY)
    september = worlds.period_state(world, AVM_US, SEPTEMBER)
    assert item["source_payload"]["period_state_id"] == str(july["id"])
    assert item["source_payload"]["posting_period_key"] == SEPTEMBER
    assert item["period_id"] == UUID(str(september["period"]["id"]))
    assert item["message"] == (
        f"{JULY} is closed for {AVM_US} in book ASC606. The approval of version 2 of rate set "
        "AVM-RATES-CLOSING changed 1 exchange rate dated in it: EUR/USD closing rate of "
        "2026-07-31 from 1.1 to 1.11. To restate it, reopen the later closed periods first and "
        "then this one; or request a waiver to accept the difference." + POSTED
    )

    # --- the difference is accepted, and September is run -----------------------------------------
    asked = post(
        app,
        f"{EXCEPTIONS}/{item['id']}/request-waiver",
        world.maya,
        {"comment": "July's closing rate corrected after its lock; taken in September."},
    )
    assert asked.status_code == 200, asked.text
    world = worlds.verified(world, clock, "priya")
    waived = approve(app, str(asked.json()["approval_request_id"]), world.priya)
    assert (waived.status_code, waived.json()["status"]) == (200, "APPROVED"), waived.text
    _soft_closed(world, SEPTEMBER, "September close")
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None), run

    assert _computations(world, open_group)[-1] == (FX_REPUBLISH, 0)
    assert _computations(world, settled_group)[-1] == (FX_REPUBLISH, 2)
    assert [_mark(world, group) for group in (open_group, settled_group)] == [(None, None)] * 2
    assert _fx_lines(world, SEPTEMBER) == [
        (FIRST, SEPTEMBER, "-", "CONTRACT_LIABILITY", "150.00"),
        (FIRST, SEPTEMBER, "-", "FX_GAIN_LOSS", "-150.00"),
        (OPEN, SEPTEMBER, "-", "CONTRACT_LIABILITY", "150.00"),
        (OPEN, SEPTEMBER, "-", "FX_GAIN_LOSS", "-150.00"),
        (SETTLED, SEPTEMBER, "-", "CONTRACT_LIABILITY", "100.00"),
        (SETTLED, SEPTEMBER, "-", "FX_GAIN_LOSS", "-100.00"),
        (SETTLED, SEPTEMBER, AUGUST, "CONTRACT_LIABILITY", "-100.00"),
        (SETTLED, SEPTEMBER, AUGUST, "FX_GAIN_LOSS", "100.00"),
    ]
    assert _fx_lines(world, AUGUST) == [
        (FIRST, AUGUST, "-", "CONTRACT_LIABILITY", "50.00"),
        (FIRST, AUGUST, "-", "FX_GAIN_LOSS", "-50.00"),
        (OPEN, AUGUST, "-", "CONTRACT_LIABILITY", "50.00"),
        (OPEN, AUGUST, "-", "FX_GAIN_LOSS", "-50.00"),
    ]
    assert _fx_lines(world, JULY) == []
    (row,) = _register(world, clock)
    assert (
        row["origin_period_key"],
        row["posting_period_key"],
        row["attribution_kind"],
        row["event_type_label"],
        row["contract_external_id"],
    ) == (AUGUST, SEPTEMBER, "TRIGGER", "Fx republish", SETTLED)
    assert august_run["id"] != run["id"]


# --- the approval's group rows and a computation --------------------------------------------------


def _rows_awaited(session: Any, pid: int) -> list[str]:
    """The tables of the rows backend ``pid`` waits for. A backend that waits for a row another
    transaction has locked holds that row's ``tuple`` lock while it waits, and ``pg_locks`` is
    read live: no statistics snapshot stands between this read and the lock table."""
    return [str(name) for name in session.execute(TUPLES_HELD, {"pid": pid}).scalars()]


def _row_locked(session: Any, pid: int) -> list[str]:
    """The tables in which backend ``pid`` has locked rows, or asked to (``ROW_LOCKED``)."""
    return [str(name) for name in session.execute(ROW_LOCKED, {"pid": pid}).scalars()]


def _august_run_done(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[worlds.ReportWorld, UUID, UUID]:
    """August in soft close with its close run ``SUCCEEDED``: a computation of the world's
    contract is inside a window (dev-guide DG-KRN-DB-08 (1c)). (world, contract id, group id)."""
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    run = runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=AUGUST)
    assert (run["status"], run["current_step_code"]) == ("SUCCEEDED", None), run
    booked = world.contracts[FIRST]
    return world, UUID(str(booked.contract["id"])), UUID(str(booked.combination_group["id"]))


def test_the_approval_waits_for_a_computation_that_holds_a_group_it_marks(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The computation first. T1 — the computation of an invoice of 10 September, inside
    August's window — holds its group row and has read its bundle on the rates in force. T2 —
    Marcus's approval of the version that corrects August's closing rate — is observed WAITING
    for T1, blocked in the ``FOR UPDATE`` of the group rows it marks (``rows_statement``, known
    by its head; the row by the ``tuple`` lock the waiting backend holds), before it has shared
    a period state — its backend holds the table lock of a row-locking statement on
    ``combination_group`` and none on ``period_state``: the mark's hook runs in front of the
    finding's (fail-first 2026-10-03 with the two hooks in the other order). T1 ends; the
    approval then marks the group, raises nothing (August is not closed) and is answered 200.
    The group is marked although the computation that was in flight has ended since: the next
    computation is the republication's.

    The two take the group row before a period-state row, the order of dev-guide DG-KRN-DB-08:
    neither waits for the other in a cycle."""
    world, contract_id, group_id = _august_run_done(app, keyring, clock, files, monkeypatch)
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: "1.115000"})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    outcome: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def approve_meanwhile() -> None:
        try:
            outcome["response"] = approve(app, sent["approval_request_id"], world.marcus)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    approving = threading.Thread(target=approve_meanwhile, name="rate-approval-meets-computation")
    window_held = period_ends.window_held

    def held_then_meet_the_approval(uow: UnitOfWork, bundle: Any, held_group: UUID) -> Any:
        held = window_held(uow, bundle, held_group)
        if approving.ident is None and held_group == group_id:
            with observing_checkouts() as backends:
                computing_pid = backend_pid(uow.session)
                approving.start()
                waiting_pid, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=computing_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect=ROWS_HEAD,
                )
                seen["rows"] = _rows_awaited(uow.session, waiting_pid)
                seen["row_locked"] = _row_locked(uow.session, waiting_pid)
            seen["waiting"] = approving.is_alive() and not outcome
            seen["mark"] = _mark(world, group_id)
        return held

    monkeypatch.setattr(period_ends, "window_held", held_then_meet_the_approval)
    try:
        invoiced = worlds._appended_through_api(
            world.place, contract_id, _invoice("INV-EU-1", "2026-09-10", "2000.00")
        )
    finally:
        if approving.ident is not None:
            approving.join(timeout=JOIN_SECONDS)
    assert invoiced["computation"]["status"] == "SUCCEEDED", invoiced["computation"]
    assert not approving.is_alive() and seen["waiting"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    assert seen["blocked_in"].lower().startswith(ROWS_HEAD), seen["blocked_in"]
    assert seen["rows"] == ["combination_group"], seen
    # group rows first, period states after (dev-guide DG-KRN-DB-08 rev 1.281): the approval
    # has asked for the rows of its mark and has shared no period state yet
    assert "combination_group" in seen["row_locked"], seen
    assert "period_state" not in seen["row_locked"], seen
    approved = outcome["response"]
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    stamp, trigger = _mark(world, group_id)
    assert stamp == _published_at(world, close_run_worlds.CLOSING_SET) and trigger == FX_REPUBLISH
    assert _items(world) == []  # August is in soft close: the gate asks for a run, no finding

    monkeypatch.setattr(period_ends, "window_held", window_held)
    with world.place.uow() as uow:
        again = compute_job.compute_group(uow, group_id, trigger=ComputationTrigger.COMMAND)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED and again.computation is not None
    assert _computations(world, group_id)[-1][0] == FX_REPUBLISH
    assert _mark(world, group_id) == (None, None)


def test_a_computation_that_arrives_waits_for_the_approval_and_reads_its_version(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approval first. T1 — Marcus's approval of the corrected version — has run its hooks
    and is NOT committed: it holds the group row it marked and August's state row. T2 — an
    invoice of 10 September on the marked contract — is observed WAITING for T1 on the group
    row, before it has read a rate. T1 commits; the invoice is then recorded and computed on
    the version: its computation pins the version, brings an event and so stays ``COMMAND``,
    and ends the mark."""
    world, contract_id, group_id = _august_run_done(app, keyring, clock, files, monkeypatch)
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: "1.115000"})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    outcome: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def invoice_meanwhile() -> None:
        try:
            outcome["sent"] = worlds._appended_through_api(
                world.place, contract_id, _invoice("INV-EU-1", "2026-09-10", "2000.00")
            )
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    invoicing = threading.Thread(target=invoice_meanwhile, name="invoice-meets-rate-approval")
    hooks = list(subjects.FX_RATE_VERSION_APPROVED)

    def approved_then_meet_the_invoice(uow: UnitOfWork, version_id: UUID, request_id: UUID) -> None:
        for hook in hooks:
            hook(uow, version_id, request_id)
        seen["version"] = version_id
        with observing_checkouts() as backends:
            approval_pid = backend_pid(uow.session)
            invoicing.start()
            _, seen["blocked_in"] = await_lock_wait(
                uow.session,
                holder_pid=approval_pid,
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="combination_group",
            )
        seen["waiting"] = invoicing.is_alive() and not outcome

    monkeypatch.setattr(subjects, "FX_RATE_VERSION_APPROVED", [approved_then_meet_the_invoice])
    try:
        approved = approve(app, sent["approval_request_id"], world.marcus)
    finally:
        if invoicing.ident is not None:
            invoicing.join(timeout=JOIN_SECONDS)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    assert not invoicing.is_alive() and seen["waiting"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    computed = outcome["sent"]["computation"]
    assert computed["status"] == "SUCCEEDED", computed
    (stored,) = close_run_worlds.rows(
        world.tenant_id,
        select(contract_computation.c.trigger, contract_computation.c.pinned_refs).where(
            contract_computation.c.id == UUID(str(computed["id"]))
        ),
    )
    assert str(getattr(stored["trigger"], "value", stored["trigger"])) == "COMMAND"
    assert str(seen["version"]) in stored["pinned_refs"]["fx_rate_set_version_ids"]
    assert _mark(world, group_id) == (None, None)


# --- the limit: what is committed -----------------------------------------------------------------


def test_an_approval_that_waits_for_a_group_row_beyond_the_lock_timeout_is_refused(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the approver is answered when the mark cannot have its rows. The row of the group
    the corrected rate reaches is held ``FOR UPDATE`` — as a computation or a period-end step
    of a close run holds it — for longer than the platform waits. The approval waits in the
    mark's lock statement for the request's ``lock_timeout`` (10 s) and is then answered 409
    ``lock-conflict``, "Another change was in progress", under rule ``LOCK_TIMEOUT`` with that
    rule's sentence. Nothing of the decision is stored: the version is still submitted and its
    request pending, the group is not marked and no item is raised. Sent again once the row is
    free, it is approved and marks the group."""
    world, _, group_id = _august_run_done(app, keyring, clock, files, monkeypatch)
    sent = close_run_worlds.closing_rates_submitted(world, {AUGUST: "1.115000"})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    held = world.place.uow()
    uow = held.__enter__()
    try:
        uow.session.execute(
            select(combination_group.c.id)
            .where(combination_group.c.id == group_id)
            .with_for_update()
        )
        started = time.monotonic()
        refused = approve(app, sent["approval_request_id"], world.marcus)
        waited = time.monotonic() - started
    finally:
        held.__exit__(None, None, None)
    assert refused.status_code == 409, refused.text  # answered at all, and not approved
    assert slug(refused) == "lock-conflict"
    assert refused.json()["title"] == "Another change was in progress"
    assert refused.json()["detail"] == problems.LOCK_TIMEOUT_DETAIL
    assert {error["rule_id"]: error["message"] for error in refused.json()["errors"]} == {
        problems.RULE_LOCK_TIMEOUT: problems.LOCK_TIMEOUT_DETAIL
    }
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
    statuses = [str(getattr(row["status"], "value", row["status"])) for row in (version, request)]
    assert statuses == ["SUBMITTED", "PENDING"]
    assert _mark(world, group_id) == (None, None)
    assert _items(world) == []

    approved = approve(app, sent["approval_request_id"], world.marcus)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    stamp, trigger = _mark(world, group_id)
    assert stamp == _published_at(world, close_run_worlds.CLOSING_SET) and trigger == FX_REPUBLISH


def _average_republished(
    world: worlds.ReportWorld, clock: FrozenClock, changed: dict[str, str]
) -> dict[str, str]:
    """A new version of the average rate set over the same coverage, submitted by Maya — every
    rate as the world states it but those of ``changed`` (period key to rate).
    ``{"version_id", "approval_request_id"}``."""
    app = world.app
    listed = get(app, close_run_worlds.FX_RATE_SETS, world.maya, {"limit": 50})
    assert listed.status_code == 200, listed.text
    (average,) = [item for item in listed.json()["items"] if item["code"] == "AVM-RATES-AVERAGE"]
    rates = [
        {**row, "rate": changed.get(row["period_key"], row["rate"])}
        for row in close_run_worlds._eur_rates("average")
    ]
    draft = post(
        app,
        f"{close_run_worlds.FX_RATE_SETS}/{average['id']}/versions",
        world.maya,
        {
            "coverage_from": "2026-01-01",
            "coverage_to": worlds.THROUGH_SEPTEMBER.isoformat(),
            "rates": rates,
        },
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        world.maya,
        {"comment": "Average rates republished"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    return {
        "version_id": str(draft.json()["id"]),
        "approval_request_id": str(submitted.json()["pending_approval_request_id"]),
    }


def _revenue(world: worlds.ReportWorld, contract_id: UUID) -> Decimal:
    """The contract's posted revenue in the functional currency, credit negative."""
    found = close_run_worlds.rows(
        world.tenant_id,
        select(subledger_line.c.amount_functional).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.account_role == "REVENUE",
        ),
    )
    return sum((Decimal(row["amount_functional"]) for row in found), Decimal(0))


def _a_first_delivery_across_the_approval(
    world: worlds.ReportWorld,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
    *,
    the_approval_commits_first: bool,
    published_after: timedelta | None = None,
) -> tuple[worlds.ReportWorld, UUID, UUID, dict[str, Any]]:
    """``SF-ORD-EU-3004`` — booked and activated on 1 August, nothing delivered: at rest before
    September, dirty since its activation and never computed — and two transactions.

    T1, the approval of its first delivery (50 hours on 10 September), has read its bundle,
    September's average rate 1.110000 in it, and stands (``period_ends.window_held``). T2, the
    approval of the version that states September's average at 1.120000, runs meanwhile: the
    group is not at work in September as its facts stand committed, so T2 takes no row of it
    and waits for nothing.

    With ``the_approval_commits_first`` T2 ends — hooks and commit — while T1 stands. Without,
    T2 runs its hooks and stands before its commit until T1 has posted and committed. With
    ``published_after`` the application clock is moved on by that much before T2 begins: the
    instant of its version is then later than T1's — where the world's clock is the record
    clock, later than T1's cutoff.

    (the world, the contract, the group, what was seen: ``computation`` as the route answered
    the delivery, ``approval`` as (status code, status), ``trigger_then`` — the group's trigger
    as committed while T1 stood, after T2's hooks.)"""
    contract_id, group_id = _hours(world, RESTING, "2026-08-01", delivered_on=None)
    sent = _average_republished(world, clock, {SEPTEMBER: "1.120000"})
    clock.advance(timedelta(minutes=1))
    world = worlds.verified(world, clock, "marcus")
    seen: dict[str, Any] = {}
    read, committed = threading.Event(), threading.Event()

    def approve_meanwhile() -> None:
        try:
            response = approve(world.app, sent["approval_request_id"], world.marcus)
            seen["approval"] = (response.status_code, response.json().get("status"))
        except Exception as error:  # noqa: BLE001 - surfaced by the callers' assertions
            seen["error"] = error

    approving = threading.Thread(target=approve_meanwhile, name="rate-approval-beside-computation")
    hooks = list(subjects.FX_RATE_VERSION_APPROVED)

    def approved_then_stand(uow: UnitOfWork, version_id: UUID, request_id: UUID) -> None:
        for hook in hooks:
            hook(uow, version_id, request_id)
        read.set()
        if not the_approval_commits_first:
            seen["released"] = committed.wait(JOIN_SECONDS)

    monkeypatch.setattr(subjects, "FX_RATE_VERSION_APPROVED", [approved_then_stand])
    window_held = period_ends.window_held

    def held_then_the_approval(uow: UnitOfWork, bundle: Any, held_group: UUID) -> Any:
        held = window_held(uow, bundle, held_group)
        if approving.ident is None and held_group == group_id:
            if published_after is not None:
                clock.advance(published_after)
            approving.start()
            seen["read"] = read.wait(JOIN_SECONDS)
            if the_approval_commits_first:
                approving.join(timeout=JOIN_SECONDS)
                seen["ended_first"] = not approving.is_alive()
            seen["trigger_then"] = _mark(world, group_id)[1]
        return held

    monkeypatch.setattr(period_ends, "window_held", held_then_the_approval)
    try:
        recorded = worlds.approved_manual_events(
            world.place,
            world.priya,
            contract_id,
            _delivery("2026-09-10", "50"),
            evidence_file_ids=[],
        )
    finally:
        committed.set()
        if approving.ident is not None:
            approving.join(timeout=JOIN_SECONDS)
    monkeypatch.setattr(period_ends, "window_held", window_held)
    monkeypatch.setattr(subjects, "FX_RATE_VERSION_APPROVED", hooks)
    seen["computation"] = recorded["computation"]
    assert not approving.is_alive() and seen.get("read") is True and "error" not in seen, seen
    assert seen["approval"] == (200, "APPROVED"), seen
    return world, contract_id, group_id, seen


def test_a_group_a_computation_in_flight_puts_into_the_reach_is_not_marked(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 T-REF-11 "The groups a changed rate reaches", *Limits* (i): the mark is decided on
    what is committed when the approval reads.

    The approval of the version reads the groups while the delivery's computation is in flight
    and commits after it (``_a_first_delivery_across_the_approval``). Both are in force: the
    delivery's revenue stands at 1.110000 — USD 5,550.00 where the rate in force gives 5,600.00
    — and the group is clean and carries no trigger. The group's next computation posts the
    50.00, under the trigger its caller names."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    world, contract_id, group_id, seen = _a_first_delivery_across_the_approval(
        world, clock, monkeypatch, the_approval_commits_first=False
    )
    assert seen["released"] is True, seen
    assert seen["computation"]["status"] == "SUCCEEDED", seen
    assert seen["trigger_then"] is None  # the approval read the group at rest: no mark of its own
    assert _mark(world, group_id) == (None, None)  # clean, and on the earlier rate
    assert _revenue(world, contract_id) == Decimal("-5550.00")
    with world.place.uow() as uow:
        again = compute_job.compute_group(uow, group_id, trigger=ComputationTrigger.COMMAND)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED and again.computation is not None
    assert _computations(world, group_id)[-1] == ("COMMAND", 2)
    assert _revenue(world, contract_id) == Decimal("-5600.00")


def test_a_computation_that_posts_after_the_approval_has_committed_is_not_stored(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other order of the same two transactions, measured with the first (2026-10-03): the
    approval ends — hooks AND commit — while the delivery's computation stands between its
    bundle and its posting.

    The computation then posts. It reads again which rates are in force at its cutoff
    (``bundles.fx_rate_ids``) and finds the version: committed now, and its instant not later
    than the cutoff — this world's clock stands behind the server's, and so does the instant of
    any approval that began before the computation did. The rates the bundle pinned are no
    longer the ones in force, ``computation._rate_stamp`` refuses the line (REQ-FX-006) and the
    computation is stored ``FAILED`` with its exception item: nothing is posted at the earlier
    rate. The delivery stays recorded and the group owed — dirty, without a trigger: the
    approval did not mark it — and its next computation posts at the rate in force, USD
    5,600.00.

    Not the mark's doing: measured the same with the hook switched off. The form of the answer
    — a failed computation where the bundle is behind the rates — is not this item's to
    change (04 T-REF-11, *Limits* (i))."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    world, contract_id, group_id, seen = _a_first_delivery_across_the_approval(
        world, clock, monkeypatch, the_approval_commits_first=True
    )
    assert seen["ended_first"] is True, seen
    assert seen["computation"]["status"] == "FAILED", seen
    assert seen["trigger_then"] is None
    assert _revenue(world, contract_id) == Decimal("0.00")  # nothing at the earlier rate
    assert _computations(world, group_id) == [("COMMAND", 0)]
    stamp, trigger = _mark(world, group_id)
    assert stamp is not None and trigger is None  # owed, and not by the approval's mark
    with world.place.uow() as uow:
        again = compute_job.compute_group(uow, group_id, trigger=ComputationTrigger.COMMAND)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED and again.computation is not None
    assert _computations(world, group_id)[-1] == ("COMMAND", 2)
    assert _revenue(world, contract_id) == Decimal("-5600.00")
    assert _mark(world, group_id) == (None, None)


def test_a_version_published_after_a_computations_cutoff_is_not_read_by_it(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The third order (2026-10-03). The approval ends — hooks and commit — while the
    delivery's computation stands, as in the case above; but its instant is LATER than the
    computation's cutoff. The world stands on the record clock (dev-guide DG-TST-14), so that
    an application instant can lie after the server's present, and the clock is moved on two
    minutes before the approval begins.

    When the computation posts, the version is committed and is not in force at its cutoff:
    the rates its bundle pinned still answer. It is stored on the earlier rate — USD 5,550.00
    — and the group is clean and unmarked, as where the computation commits before the
    approval does. The next computation, begun at the version's instant, posts the 50.00."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    world = worlds.on_record_clock(world, clock)
    world, contract_id, group_id, seen = _a_first_delivery_across_the_approval(
        world,
        clock,
        monkeypatch,
        the_approval_commits_first=True,
        published_after=timedelta(minutes=2),
    )
    assert seen["ended_first"] is True, seen
    assert seen["computation"]["status"] == "SUCCEEDED", seen
    assert seen["trigger_then"] is None
    assert _mark(world, group_id) == (None, None)  # clean, and on the earlier rate
    assert _revenue(world, contract_id) == Decimal("-5550.00")
    with world.place.uow() as uow:
        again = compute_job.compute_group(uow, group_id, trigger=ComputationTrigger.COMMAND)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED and again.computation is not None
    assert _computations(world, group_id)[-1] == ("COMMAND", 2)
    assert _revenue(world, contract_id) == Decimal("-5600.00")
