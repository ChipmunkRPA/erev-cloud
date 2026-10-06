"""The reports state an obligation at their date (item RPT-ASOF-FIGURES-1; ENGINE_SPEC_B S15-R-01,
S15-R-02, S15-R-08, S15-R-12 rev 1.127; 04 table 10-T rev 1.179; SCREENS_B RPT-01, RPT-06, RPT-07
and RPT-11 rev 1.55; supervisor ruling R-116 (c)).

A contract version holds an obligation's scheduled and awaiting-trigger amounts at the version's
date, and a computation recognises revenue past that date through every open period. The revenue
waterfall, the RPO report with its rollforward, the dashboard panels on them and the datasets a
lock freezes added the stored awaiting-trigger amount to what was recognised since.

Worlds, built with the product's commands at the frozen clock 2026-09-12T12:00:00Z, the periods
FY2026-P01 to P09 open, so that both ledgers hold revenue through September:

- K-08 ``SF-ORD-10003`` (``support.worlds.k08_ulvane``): a usage obligation of 80,000.00 over
  2026, recognised as time elapses, no usage reported; its one version is dated 1 January and
  stores 219.18 recognised and a remainder of 79,780.82 — scheduled since ENGINE_SPEC_B rev 1.126
  (item ENG-USAGE-FIXED-SCHEDULE-1; supervisor ruling R-116 (a)), awaiting trigger until then.
  Before item RPT-ASOF-FIGURES-1 its waterfall read 59,835.62 + 0.00 + 79,780.82 = 139,616.44 and
  its RPO 79,780.82.
- K-01 ``SF-ORD-10001`` (``support.worlds.k01_pellworth``): O1 118,800.00 recognised daily over
  2026 and O2 16,200.00 by output percent, complete on 27 February, the date of its one version.
  Right at the last posted period before this item; at an earlier as-of its waterfall stated the
  periods in between twice (164,944.11 at 30 June for an allocation of 135,000.00).

The oracles stand outside the builders: the arithmetic of the two rules (ALG-01 daily series,
output percent) and the ledger — the revenue posted through the as-of period.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import obligation_version, period_lock
from erev_api.domain.reports import locked
from erev_api.files.store import LocalFileStore, open_file
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import close_runs, worlds
from support.close_world import reviewed_reconciliations_for
from support.db import TestDatabase
from support.reference import approve, assign, get, post
from support.worlds import (
    AVM_US,
    K01,
    K08,
    ReportWorld,
    k01_pellworth,
    k08_ulvane,
    report_run,
)
from tests.domain.contracts.test_to_date_reads import (
    O1_ALLOCATED,
    O2_ALLOCATED,
    daily,
    k01_billed,
    k01_o1,
    k01_o2,
    posted_revenue,
)

HOME: Final = "/api/v1/dashboard/home"
BASE: Final = {"entity_codes": [AVM_US], "book": "ASC606"}
YEAR: Final = {**BASE, "from_period_key": "FY2026-P01", "to_period_key": "FY2026-P12"}
ZERO: Final = Decimal(0)
# (the as-of date, its period)
AS_OFS: Final = (
    (date(2026, 9, 30), "FY2026-P09"),  # the last posted period
    (date(2026, 6, 30), "FY2026-P06"),  # three posted periods lie after it
    (date(2026, 1, 31), "FY2026-P01"),
)
PERIODS: Final = tuple(f"FY2026-P{month:02d}" for month in range(1, 13))


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def usd(amount: Decimal | str) -> dict[str, str]:
    return {"amount": f"{Decimal(amount):.2f}", "currency": "USD"}


def amount(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(value["amount"])


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def ties(run: Mapping[str, Any]) -> dict[str, str]:
    return {str(item["code"]): str(item["result"]) for item in run["tie_out_results"]}


# --- the oracles: (recognised, scheduled, awaiting trigger) of the contract at a date -------------


def k08_at(day: date) -> tuple[Decimal, Decimal, Decimal]:
    """Time alone recognises the stated consideration and no event moves it: the engine calls its
    remainder scheduled (ENGINE_SPEC_B S09-R-45 rev 1.126; item ENG-USAGE-FIXED-SCHEDULE-1;
    supervisor ruling R-116 (a)). Until that revision it called it awaiting trigger; the
    classification moved and no total did (``K08_REMAINDER``)."""
    revenue = daily(Decimal("80000.00"), date(2026, 1, 1), 365, day)
    return revenue, Decimal("80000.00") - revenue, ZERO


# K-08's remainder at the three as-of dates — its RPO, and the waterfall's total less what is
# recognised: the figures these tests held while the remainder was called awaiting trigger.
K08_REMAINDER: Final = {
    date(2026, 9, 30): Decimal("20164.38"),
    date(2026, 6, 30): Decimal("40328.77"),
    date(2026, 1, 31): Decimal("73205.48"),
}


def k01_at(day: date) -> tuple[Decimal, Decimal, Decimal]:
    """O1's remainder is scheduled; what O2 has not earned at the date awaits its trigger."""
    o1, o2 = k01_o1(day), k01_o2(day)
    return o1 + o2, O1_ALLOCATED - o1, O2_ALLOCATED - o2


Oracle = Callable[[date], tuple[Decimal, Decimal, Decimal]]
# the contract → (its world, its oracle, its allocation)
WORLDS: Final[Mapping[str, tuple[Callable[..., ReportWorld], Oracle, Decimal]]] = {
    K08: (k08_ulvane, k08_at, Decimal("80000.00")),
    K01: (k01_pellworth, k01_at, Decimal("135000.00")),
}


@pytest.mark.slow
@pytest.mark.parametrize("external_id", [K08, K01])
def test_the_waterfall_the_rpo_and_its_rollforward_state_the_as_of(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    external_id: str,
) -> None:
    """At the last posted period, at an as-of three posted periods back and at the first period:
    the waterfall's recognised + scheduled + awaiting trigger is the allocation (S15-R-02), with
    recognised only up to the as-of period and scheduled only after it; the RPO is the remainder
    at the date and equals the contract read's; the rollforward from the first period to the
    as-of period explains its closing without a difference."""
    build, at, allocation = WORLDS[external_id]
    world: ReportWorld = build(app, keyring, clock, files)
    contract_id = str(world.contracts[external_id].contract["id"])
    row_key = f"contract:{external_id}"
    for day, period_key in AS_OFS:
        recognised, scheduled, awaiting = at(day)
        assert recognised + scheduled + awaiting == allocation
        if external_id == K08:  # scheduled since rev 1.126; the remainder is the figure of before
            assert (scheduled + awaiting, awaiting) == (K08_REMAINDER[day], ZERO)
        # the ledger agrees with the oracle before any report is asserted against either
        assert posted_revenue(world.place, contract_id, day) == recognised

        run, rows = report_run(
            world, "revenue_waterfall", {**YEAR, "as_of": day.isoformat(), "measure": "BY_STATE"}
        )
        assert run["control_totals"] == {
            "recognized_total": {"USD": f"{recognised:.2f}"},
            "scheduled_total": {"USD": f"{scheduled:.2f}"},
            "awaiting_trigger_total": {"USD": f"{awaiting:.2f}"},
        }, day
        for row in (keyed(rows)[row_key], keyed(rows)["TOTAL:USD"]):
            assert (row["awaiting_trigger"], row["total"]) == (usd(awaiting), usd(allocation)), day
            cells = {
                key: (
                    amount(row[f"period:{key}:recognized"]),
                    amount(row[f"period:{key}:scheduled"]),
                )
                for key in PERIODS
            }
            # nothing is recognised after the as-of period and nothing scheduled up to it
            assert all(cells[key][1] == 0 for key in PERIODS if key <= period_key), day
            assert all(cells[key][0] == 0 for key in PERIODS if key > period_key), day
            assert sum(found[0] for found in cells.values()) == recognised
            assert sum(found[1] for found in cells.values()) == scheduled

        # RPO and its rollforward read the version at a date (S15-R-24a), and a contract enters
        # them on the day it is activated (S15-R-12 rev 1.161; item RPT-RPO-ROLLFWD-1; supervisor
        # ruling R-121 (g)). K-01's only version is dated 27 February by the last of its
        # causes and counts from 1 January: at 31 January its remainder is stated, with the
        # 9,720.00 of O2, which was satisfied only later — in the report and in the contract read.
        # (Until that ruling this test held that both state nothing of K-01 at 31 January.)
        remainder = scheduled + awaiting
        run, rows = report_run(world, "rpo", {**BASE, "period_key": period_key})
        assert run["control_totals"]["total"] == {"USD": f"{remainder:.2f}"}, day
        assert keyed(rows)[row_key]["total"] == usd(remainder)
        assert ties(run) == {"TO_RPO_ROLLFORWARD_EQ_RPO": "PASS"}
        contract = get(app, f"/api/v1/contracts/{contract_id}", world.maya, {"as_of": str(day)})
        assert contract.status_code == 200, contract.text
        assert contract.json()["kpis"]["rpo"] == usd(remainder)

        # The rollforward from the first period to the as-of period: the whole allocation enters
        # as a new contract, the revenue of the range leaves, and nothing is unexplained.
        run, rows = report_run(
            world,
            "rpo_rollforward",
            {**BASE, "from_period_key": "FY2026-P01", "to_period_key": period_key},
        )
        lines = {
            key: amount(row["rpo"]) for key, row in keyed(rows).items() if row.get("section") == 1
        }
        stated = {
            "OPENING": ZERO,
            "NEW_CONTRACTS": allocation,
            "MODIFICATIONS": ZERO,
            "VC_ESTIMATE_CHANGES": ZERO,
            "LATE_EVENTS": ZERO,  # the row of S15-R-12 (rev 1.161): one version at both ends
            "REVENUE": -recognised,
            "CANCELLATIONS": ZERO,
            "FX": ZERO,
            "UNEXPLAINED": ZERO,
            "CLOSING": remainder,
        }
        assert lines == stated, day
        assert ties(run) == {
            "TO_ROLLFORWARD_BALANCES": "PASS",
            "TO_RPO_ROLLFORWARD_EQ_RPO": "PASS",
        }, day


def month_end(period_key: str) -> date:
    """The end of ``FY<year>-P<month>`` in the worlds' calendar: months, the year from January."""
    year, month = int(period_key[2:6]), int(period_key[8:10])
    return date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def k01_rows(day: date) -> dict[str, tuple[Decimal, Decimal, Decimal, Decimal]]:
    """Obligation → (allocated, recognised, scheduled, awaiting trigger) at ``day``."""
    o1, o2 = k01_o1(day), k01_o2(day)
    return {
        "O1": (O1_ALLOCATED, o1, O1_ALLOCATED - o1, ZERO),
        "O2": (O2_ALLOCATED, o2, ZERO, O2_ALLOCATED - o2),
    }


@pytest.mark.slow
@pytest.mark.parametrize("external_id", [K08, K01])
def test_the_dashboard_and_the_latest_status_state_the_as_of(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    external_id: str,
) -> None:
    """At the context periods September, June and January: the home page's revenue chart states
    recognised revenue up to the context period and scheduled amounts after it, each period by
    the oracle, and the awaiting-trigger amount with its count at the period's end; its RPO is
    the remainder of that date. RPT-11 states one date in every figure — revenue, the two parts
    of the remainder and the balances of the as-of — while RPT-09 keeps printing the version's
    own columns at its effective date."""
    build, at, _ = WORLDS[external_id]
    world = build(app, keyring, clock, files)
    contract_id = str(world.contracts[external_id].contract["id"])
    for day, period_key in AS_OFS:
        recognised, scheduled, awaiting = at(day)
        if external_id == K08:  # scheduled since rev 1.126; the remainder is the figure of before
            assert (scheduled + awaiting, awaiting) == (K08_REMAINDER[day], ZERO)
        shown = get(
            app, HOME, world.maya, {"entity": AVM_US, "period": period_key, "book": "ASC606"}
        )
        assert shown.status_code == 200, shown.text
        body = shown.json()
        chart = body["revenue_chart"]
        assert (chart["awaiting_trigger"], chart["pending_trigger_count"]) == (
            usd(awaiting),
            1 if awaiting else 0,
        ), day
        assert chart["totals"]["awaiting_trigger"] == usd(awaiting)
        assert period_key in {item["period_key"] for item in chart["periods"]}
        for item in chart["periods"]:
            end = month_end(item["period_key"])
            before = end.replace(day=1) - timedelta(days=1)
            moved = [now - then for now, then in zip(at(end), at(before), strict=True)]
            # recognised up to the context period; after it what leaves the scheduled part
            expected = (moved[0], ZERO) if item["period_key"] <= period_key else (ZERO, -moved[1])
            assert (item["recognized"], item["scheduled"]) == (
                usd(expected[0]),
                usd(expected[1]),
            ), (day, item["period_key"])
        # K-01's only version is dated 27 February by the last of its causes; the RPO and RPT-11
        # read it from 1 January on, the day the contract was activated (S15-R-12 rev 1.161;
        # item RPT-RPO-ROLLFWD-1), and state it at 31 January as every other date
        remainder = scheduled + awaiting
        assert body["rpo"] == {"total": usd(remainder), "within_12_months": usd(remainder)}, day

        run, rows = report_run(world, "latest_contract_status", {**BASE, "as_of": str(day)})
        expected_rows = (
            {"O1": (Decimal("80000.00"), recognised, scheduled, awaiting)}
            if external_id == K08
            else k01_rows(day)
        )
        billed = ZERO if external_id == K08 else sum(k01_billed(day), ZERO)
        liability, asset = max(billed - recognised, ZERO), max(recognised - billed, ZERO)
        assert {
            row["obligation_key"]: (
                row["allocated_amount"],
                row["revenue_cum"],
                row["remaining_allocation"],
                row["scheduled_amount"],
                row["awaiting_trigger_amount"],
                row["contract_liability"],
                row["contract_asset_and_unbilled"],
            )
            for row in rows
        } == {
            key: (
                usd(allocated),
                usd(revenue),
                usd(allocated - revenue),
                usd(planned),
                usd(waiting),
                usd(liability),
                usd(asset),
            )
            for key, (allocated, revenue, planned, waiting) in expected_rows.items()
        }, day
        assert run["control_totals"]["revenue_cum"] == {"USD": f"{recognised:.2f}"}
        # the contract read of the same date states the same balances
        contract = get(app, f"/api/v1/contracts/{contract_id}", world.maya, {"as_of": str(day)})
        assert contract.status_code == 200, contract.text
        (entry,) = contract.json()["kpis"]["balances"]
        assert entry["contract_liability"] == usd(liability)
        assert amount(entry["contract_asset"]) + amount(entry["unbilled_receivable"]) == asset

    if external_id == K08:
        _, rows = report_run(world, "contract_history", {**BASE, "contract_external_id": K08})
        (row,) = rows
        # RPT-09 prints the version's own columns: the remainder of 1 January, 79,780.82 as
        # before, in the scheduled column
        assert (
            row["effective_date"],
            row["revenue_cum"],
            row["remaining_allocation"],
            row["scheduled_amount"],
            row["awaiting_trigger_amount"],
        ) == ("2026-01-01", usd("219.18"), usd("79780.82"), usd("79780.82"), usd("0.00"))


# --- the lock -------------------------------------------------------------------------------------

SEPTEMBER: Final = "FY2026-P09"


def _locks(world: ReportWorld) -> list[dict[str, Any]]:
    """The ``LOCK`` records of September 2026 of AVM-US, oldest first."""
    period_id = UUID(str(worlds.period_state(world, AVM_US, SEPTEMBER)["period"]["id"]))
    return world.place.rows(
        select(period_lock)
        .where(period_lock.c.period_id == period_id, period_lock.c.kind == "LOCK")
        .order_by(period_lock.c.created_at, period_lock.c.id)
    )


def _locked_again(
    world: ReportWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> ReportWorld:
    """The reopened September closed and locked again, as a user closes it. The invoice was
    computed inside the window of the period's first close run and lowered the group's period-end
    mark, so the lock asks for the close run again (gate ``CLOSE_RUN_COMPLETED``; 04 §16.8 "The
    close-run gate"; item CLO-GATE-RUN-1). It is the real run (``support.close_runs.closed``):
    the fixture row ``worlds.period_locked`` writes clears no mark. With an invoice against the
    obligation the period end has something to post — the netting reclass of September and its
    reversal in October — so the run's journal run goes through its life before the
    reconciliations are reviewed again and the lock is requested."""
    app = world.app
    state = worlds.period_state(world, AVM_US, SEPTEMBER)
    started = post(
        app,
        f"/api/v1/periods/{state['id']}/start-close",
        world.maya,
        {"comment": "September close restarted after the reopen"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    run = close_runs.closed(world, monkeypatch, entity_code=AVM_US, period_key=SEPTEMBER)
    assert run["status"] == "SUCCEEDED", run
    world = close_runs.journal_posted(world, clock, run["journal_run_id"])
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=UUID(str(state["entity"]["id"])),
            period_id=UUID(str(state["period"]["id"])),
            now=clock.now(),
        )
    state = worlds.period_state(world, AVM_US, SEPTEMBER)
    requested = post(
        app,
        f"/api/v1/periods/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": "September 2026 re-lock complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    world = worlds.verified(world, clock, "marcus")
    decided = approve(app, str(requested.json()["approval_request_id"]), world.marcus)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert worlds.period_state(world, AVM_US, SEPTEMBER)["state"] == "closed"
    return world


def _frozen(world: ReportWorld, lock_id: UUID, report_code: str) -> list[dict[str, Any]]:
    with world.place.uow() as uow:
        data = locked.report_data(
            locked.locked_dataset(uow, report_code=report_code, lock_id=lock_id)
        )
    return [dict(row) for row in data.rows]


@pytest.mark.slow
def test_a_lock_freezes_the_figures_of_its_period_end_and_a_relock_shows_no_movement(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """September 2026 of AVM-US locked through the product with K-08 in it: the WATERFALL row of
    the obligation holds September's revenue, 6,575.35, and the RPO row the remainder of 30
    September, 20,164.38, where the lock froze 79,780.82 before item RPT-ASOF-FIGURES-1.

    Since ENGINE_SPEC_B rev 1.126 (item ENG-USAGE-FIXED-SCHEDULE-1; supervisor ruling R-116 (a))
    that remainder is scheduled, not awaiting trigger. A lock's WATERFALL row holds the cells of
    its one period and the obligation's awaiting-trigger amount (``snapshots.freeze_waterfall``),
    so K-08's row now reads as a time-elapsed obligation's does — the period's revenue alone; its
    awaiting-trigger amount, 20,164.38 until that revision, is 0.00 and the row's own sum follows
    it. The remainder of the lock's date did not move: it is the RPO row.

    Then the period is reopened, an invoice dated 15 September is recorded — a new version, dated
    15 September, whose stored scheduled amount is the remainder of that day — and the period is
    locked again, on a new close run. Nothing of the obligation's revenue or remainder at 30
    September has changed, and the re-lock's difference report says so: the WATERFALL and the RPO
    dataset are the same files. Before item RPT-ASOF-FIGURES-1 both showed a movement that was
    only the distance between the two version dates."""
    world = k08_ulvane(app, keyring, clock, files)
    contract_id = UUID(str(world.contracts[K08].contract["id"]))
    recognised, remainder, awaiting = k08_at(date(2026, 9, 30))
    september = recognised - k08_at(date(2026, 8, 31))[0]
    assert (september, remainder, awaiting) == (Decimal("6575.35"), Decimal("20164.38"), ZERO)
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=SEPTEMBER)
    (first,) = _locks(world)

    (row,) = _frozen(world, first["id"], "revenue_waterfall")
    assert (row["recognised"], row["scheduled"], row["awaiting_trigger"], row["total"]) == (
        f"{september:.2f}",
        "0.00",  # nothing is scheduled in the lock's own period at its end
        f"{awaiting:.2f}",
        f"{september + awaiting:.2f}",
    )
    # the remainder of the lock's date, the figure of before: the RPO row
    (row,) = _frozen(world, first["id"], "rpo")
    assert (row["total"], row["within_12_months"]) == (f"{remainder:.2f}", f"{remainder:.2f}")

    world = worlds.period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=SEPTEMBER,
        comment="INV-US-1203 of 15 September was not recorded.",
    )
    invoiced = worlds._appended_through_api(
        world.place,
        contract_id,
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-09-15",
            "payload": {
                "invoice_number": "INV-US-1203",
                "line_external_id": "INV-US-1203-1",
                "obligation_key": "O1",
                "amount": {"amount": "20000.00", "currency": "USD"},
                "issue_date": "2026-09-15",
            },
        },
    )
    assert invoiced["computation"]["status"] == "SUCCEEDED", invoiced["computation"]
    # the version moved: its date, and with it the stored scheduled amount — the remainder of
    # each date, as before; nothing of either version awaits a trigger
    stored = world.place.rows(
        select(
            obligation_version.c.effective_date,
            obligation_version.c.scheduled_amount,
            obligation_version.c.awaiting_trigger_amount,
        )
        .where(obligation_version.c.contract_id == contract_id)
        .order_by(obligation_version.c.version_no)
    )
    assert [
        (row["effective_date"], row["scheduled_amount"], row["awaiting_trigger_amount"])
        for row in stored
    ] == [
        (date(2026, 1, 1), Decimal("79780.82"), ZERO),
        (date(2026, 9, 15), Decimal("80000.00") - k08_at(date(2026, 9, 15))[0], ZERO),
    ]
    world = _locked_again(world, clock, monkeypatch)
    first, second = _locks(world)
    assert second["diff_report_file_id"] is not None
    with world.place.uow() as uow:
        _, stream = open_file(
            uow.session,
            UUID(str(second["diff_report_file_id"])),
            files=world.place.files,
            keyring=world.place.keyring,
        )
        report = json.loads(stream.read().decode("utf-8"))
    kinds = report["kinds"]
    assert (kinds["WATERFALL"]["changed"], kinds["RPO"]["changed"]) == (False, False)
    # the invoice is in the difference where it belongs: the contract's balances
    assert kinds["CONTRACT_BALANCES"]["changed"] is True
    (row,) = _frozen(world, second["id"], "rpo")
    assert row["total"] == f"{remainder:.2f}"
