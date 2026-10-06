"""The figures behind a usage report whose period has ended (04 §16.3 "The usage period of a
report", rev 1.320; PRD BR-REC-01, IMP-148; ENGINE_SPEC_B S09-R-19; item
USAGE-REPORT-PERIOD-ENDED-1; the supervisor's rulings of 2026-10-03).

World: WLD-K-08 (``support.worlds.k08_ulvane``) — one usage obligation of 80,000.00 over 2026 by
the day, its version dated 1 January, FY2026-P01 to P09 open, the clock at 12 September 2026.

MEASURED ON MAIN 2498e096a, before the rule. ONE usage report dated inside its usage period —
50,000 calls rated 5,000.00 for 1 to 31 August, dated 24 August — was rated at once and realised
at its period's end (S09-R-19), so the version it made, dated 24 August, held the fee on a
schedule line and in no allocation, revenue or remainder (allocated 80,000.00). While that version
was the latest, every read of a date from 31 August on subtracted the fee from a remainder that
never held it: the RPO report, the waterfall's awaiting-trigger total and the contract read
stated 21,739.73 at 31 August and 15,164.38 at 30 September, their tie-out passed, and the lock
of August froze 21,739.73 with a waterfall row of 33,534.25. With a version dated at the cut the
same reads stated 26,739.73 and 20,164.38 there, and the lock froze 26,739.73 with a waterfall
row of 38,534.25 — the month's revenue and the remainder, which main called awaiting trigger.

The door now refuses that report (``tests/domain/contracts/test_usage_report_period.py``), and
each test here meets the refusal first. What it then holds is the report as the rule takes it —
the usage up to the report's date, 1 to 24 August, dated 24 August — and the figures a version at
the cut states. A later-recorded event with an earlier date does not move the version back
(a version is dated at the latest effective date it includes): a billing recorded after the
report and dated 15 August changes no figure.

WHAT THE PRODUCT STATES NOW (ENGINE_SPEC_B S09-R-45 rev 1.126; item ENG-USAGE-FIXED-SCHEDULE-1,
register index 87, returned behind this item). The stated consideration of a usage obligation is
placed by time alone, so its remainder is SCHEDULED and nothing awaits a trigger: the amounts are
those of the paragraph above — 26,739.73 at 31 August, 20,164.38 at 30 September — and the part
is the other one. The RPO report and the contract's RPO state the remainder as before; the
waterfall states it as its scheduled total, and the contract read as ``scheduled``. A lock of
August freezes the RPO row with 26,739.73 within twelve months, and a WATERFALL row of August
that holds the month's revenue, 11,794.52, alone: nothing is scheduled in the lock's own period
at its end, and the scheduled amount stands in the periods after it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_version, obligation_version, period_lock
from erev_api.domain.reports import locked
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.reference import approve, assign, get, post
from support.worlds import AVM_US, K08, ReportWorld, k08_ulvane, report_run
from tests.domain.contracts.test_to_date_reads import daily, posted_revenue

BASE: Final = {"entity_codes": [AVM_US], "book": "ASC606"}
YEAR: Final = {**BASE, "from_period_key": "FY2026-P01", "to_period_key": "FY2026-P12"}
EVENTS: Final = "/api/v1/contracts/{contract_id}/events"
AUGUST: Final = "FY2026-P08"
PRICE: Final = Decimal("80000.00")
FEE: Final = Decimal("5000.00")
REPORTED: Final = date(2026, 8, 24)
# the dates from the report's period end on, with their periods
CUTS: Final = ((date(2026, 8, 31), AUGUST), (date(2026, 9, 30), "FY2026-P09"))


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def usd(amount: Decimal) -> dict[str, str]:
    return {"amount": f"{amount:.2f}", "currency": "USD"}


def revenue_at(day: date) -> Decimal:
    """The oracle: the stated consideration by the day, and the report's fee from its date."""
    return daily(PRICE, date(2026, 1, 1), 365, day) + (FEE if day >= REPORTED else Decimal(0))


def _usage(start: str, end: str, day: str) -> dict[str, Any]:
    return {
        "event_type": "USAGE_REPORTED",
        "effective_date": day,
        "payload": {
            "obligation_key": "O1",
            "usage_period_start": start,
            "usage_period_end": end,
            "metric": "API_CALL",
            "quantity": "50000",
            "rated_amount": {"amount": "5000.00", "currency": "USD"},
        },
    }


def _sent(world: ReportWorld, contract_id: UUID, item: dict[str, Any]) -> Any:
    head = int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )
    return post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.maya,
        {"events": [item]},
        if_match=f'"s{head}"',
    )


def _reported(world: ReportWorld, contract_id: UUID) -> None:
    """The report of the measurement is refused; the usage up to the report's date is taken and
    approved by the second person."""
    refused = _sent(world, contract_id, _usage("2026-08-01", "2026-08-31", "2026-08-24"))
    # the status first: without the rule this report is stored and the figures below are short
    assert refused.status_code == 422, refused.text
    assert [error["rule_id"] for error in refused.json()["errors"]] == ["USAGE_PERIOD_NOT_ENDED"]
    sent = _sent(world, contract_id, _usage("2026-08-01", "2026-08-24", "2026-08-24"))
    assert sent.status_code == 201, sent.text
    approved = approve(world.app, sent.json()["approval_request_id"], world.priya)
    assert approved.status_code == 200, approved.text


def _latest(
    world: ReportWorld, contract_id: UUID
) -> tuple[date, Decimal, Decimal, Decimal, Decimal]:
    """The obligation in the latest version: its date, allocation, revenue to date, and the two
    parts of its remainder — scheduled, awaiting trigger."""
    row = world.place.rows(
        select(
            obligation_version.c.effective_date,
            obligation_version.c.allocated_amount,
            obligation_version.c.revenue_cum,
            obligation_version.c.scheduled_amount,
            obligation_version.c.awaiting_trigger_amount,
        )
        .select_from(
            obligation_version.join(
                contract_version, contract_version.c.id == obligation_version.c.contract_version_id
            )
        )
        .where(obligation_version.c.contract_id == contract_id)
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )[0]
    return (
        row["effective_date"],
        Decimal(row["allocated_amount"]),
        Decimal(row["revenue_cum"]),
        Decimal(row["scheduled_amount"]),
        Decimal(row["awaiting_trigger_amount"]),
    )


def _stated(world: ReportWorld, contract_id: UUID) -> None:
    """At 31 August and at 30 September the RPO report, the waterfall and the contract read state
    the remainder of an allocation that holds the fee — scheduled, with nothing awaiting a trigger
    (ENGINE_SPEC_B S09-R-45 rev 1.126) — and the ledger holds that revenue."""
    for day, period_key in CUTS:
        revenue = revenue_at(day)
        remainder = PRICE + FEE - revenue
        assert posted_revenue(world.place, contract_id, day) == revenue, day

        run, rows = report_run(world, "rpo", {**BASE, "period_key": period_key})
        assert run["control_totals"]["total"] == {"USD": f"{remainder:.2f}"}, day
        by_key = {str(row["row_key"]): row for row in rows}
        assert by_key[f"contract:{K08}"]["total"] == usd(remainder), day
        assert {str(item["code"]): str(item["result"]) for item in run["tie_out_results"]} == {
            "TO_RPO_ROLLFORWARD_EQ_RPO": "PASS"
        }, day

        run, _ = report_run(
            world, "revenue_waterfall", {**YEAR, "as_of": day.isoformat(), "measure": "BY_STATE"}
        )
        assert run["control_totals"] == {
            "recognized_total": {"USD": f"{revenue:.2f}"},
            "scheduled_total": {"USD": f"{remainder:.2f}"},
            "awaiting_trigger_total": {"USD": "0.00"},
        }, day

        shown = get(world.app, f"/api/v1/contracts/{contract_id}", world.maya, {"as_of": str(day)})
        assert shown.status_code == 200, shown.text
        kpis = shown.json()["kpis"]
        assert (
            kpis["transaction_price"],
            kpis["revenue_to_date"],
            kpis["scheduled"],
            kpis["awaiting_trigger"],
            kpis["rpo"],
        ) == (
            usd(PRICE + FEE),
            usd(revenue),
            usd(remainder),
            usd(Decimal(0)),
            usd(remainder),
        ), day


@pytest.mark.slow
def test_a_report_dated_at_its_periods_end_leaves_no_short_figure_and_a_late_event_moves_none(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The report for 1 to 24 August dated 24 August is realised in the version it makes:
    allocated 85,000.00 on 24 August, its remainder scheduled and nothing awaiting a trigger.
    At 31 August the three reads state 26,739.73 and at 30 September 20,164.38 — where main
    stated 21,739.73 and 15,164.38 behind the report dated inside its period. A billing recorded
    afterwards and dated 15 August makes a new version that is still dated 24 August, and moves
    none of the figures."""
    assert (PRICE + FEE - revenue_at(date(2026, 8, 31))) == Decimal("26739.73")
    assert (PRICE + FEE - revenue_at(date(2026, 9, 30))) == Decimal("20164.38")
    world = k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: `event.approve`
    contract_id = UUID(str(world.contracts[K08].contract["id"]))

    _reported(world, contract_id)

    to_date = revenue_at(REPORTED)
    assert _latest(world, contract_id) == (
        REPORTED,
        PRICE + FEE,
        to_date,
        PRICE + FEE - to_date,
        Decimal(0),
    )
    _stated(world, contract_id)

    # a late event: recorded after the report, effective before it
    billed = _sent(
        world,
        contract_id,
        {
            "event_type": "BILLING_RECORDED",
            "effective_date": "2026-08-15",
            "payload": {
                "invoice_number": "INV-US-1208",
                "line_external_id": "INV-US-1208-1",
                "obligation_key": "O1",
                "amount": {"amount": "1000.00", "currency": "USD"},
                "issue_date": "2026-08-15",
            },
        },
    )
    assert billed.status_code == 201, billed.text
    assert billed.json()["computation"]["status"] == "SUCCEEDED"

    assert _latest(world, contract_id) == (
        REPORTED,
        PRICE + FEE,
        to_date,
        PRICE + FEE - to_date,
        Decimal(0),
    )
    _stated(world, contract_id)


@pytest.mark.slow
def test_a_lock_freezes_the_figure_of_a_report_dated_at_its_periods_end(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """August 2026 of AVM-US locked through the product with the report in it and no later
    version: the frozen RPO row of the obligation holds 26,739.73, within twelve months, and the
    frozen WATERFALL row of August holds August's revenue with the fee, 11,794.52, and nothing
    else — the remainder is scheduled (ENGINE_SPEC_B S09-R-45 rev 1.126) and nothing is scheduled
    in the lock's own period at its end. Behind the report dated inside its period main froze an
    RPO of 21,739.73."""
    august = revenue_at(date(2026, 8, 31)) - revenue_at(date(2026, 7, 31))
    remainder = PRICE + FEE - revenue_at(date(2026, 8, 31))
    assert (august, remainder) == (Decimal("11794.52"), Decimal("26739.73"))
    world = k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # the journal run and the report are hers
    contract_id = UUID(str(world.contracts[K08].contract["id"]))
    _reported(world, contract_id)

    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=AUGUST)

    period_id = UUID(str(worlds.period_state(world, AVM_US, AUGUST)["period"]["id"]))
    (lock,) = world.place.rows(
        select(period_lock).where(
            period_lock.c.period_id == period_id, period_lock.c.kind == "LOCK"
        )
    )
    with world.place.uow() as uow:
        rpo = locked.report_data(locked.locked_dataset(uow, report_code="rpo", lock_id=lock["id"]))
        waterfall = locked.report_data(
            locked.locked_dataset(uow, report_code="revenue_waterfall", lock_id=lock["id"])
        )
    (row,) = [dict(found) for found in rpo.rows]
    assert (row["total"], row["within_12_months"]) == (f"{remainder:.2f}", f"{remainder:.2f}")
    (row,) = [dict(found) for found in waterfall.rows]
    assert (row["recognised"], row["scheduled"], row["awaiting_trigger"], row["total"]) == (
        f"{august:.2f}",
        "0.00",
        "0.00",
        f"{august:.2f}",
    )
