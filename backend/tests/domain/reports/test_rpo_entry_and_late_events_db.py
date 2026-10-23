"""A contract enters the RPO family on the day it is activated, and revenue a later version
recognises for an earlier period is a late event (item RPT-RPO-ROLLFWD-1; ENGINE_SPEC_B S15-R-08
and S15-R-12 rev 1.161; SCREENS_B RPT-06, RPT-07 and RPT-11 rev 1.70; 04 API-C-10 rev 1.213;
supervisor ruling R-121 (g)). PostgreSQL-bound, through the product's commands and
``POST /report-runs``.

The RPO report, its rollforward, the Home figure and RPT-11 read a contract at a date from the
last version effective on or before it, and a version was dated by the LATEST of its causing
events. A computation takes in every event recorded so far, so a first version is often caused
by the activation and by measurements dated after it. Two worlds of ``support.worlds`` are built
that way, at the frozen clock 2026-09-12 with FY2026-P01 to P09 open:

- K-01 ``SF-ORD-10001`` (``k01_pellworth``): activated on 1 January 2026, 135,000.00; its one
  version also holds the progress of 31 January and of 27 February and is dated 27 February.
  Measured before the item: no RPO at 31 January; February's rollforward opened at 0.00, showed
  135,000.00 of new contracts and −16,569.86 unexplained — January's revenue.
- K-04 ``SF-ORD-UK-2001`` (``k04_saltmarsh``, contracted by AVM-UK): activated on 1 April 2026,
  68,000.00 GBP; its one version is dated 31 May. No RPO at 30 April; May −9,647.75 unexplained.

A third world holds a late event: K-01 through 1 January, January locked, the O2 progress of 31
January imported afterwards (``k01_late_progress``). Its revenue, 6,480.00, is posted in February
with January as its origin; the version that knows it is effective in February. February's
rollforward showed −6,480.00 unexplained.

The oracle stands outside the builders: the ledger — the revenue posted in the periods up to a
date, and the origin period of each line — and the contract's allocation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import period, product, subledger_line
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from httpx import Response
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.factories import (
    booked_contract,
    computed,
    customer_id,
    published_template,
    set_default_template,
)
from support.reference import assign, get
from support.worlds import AVM_UK, AVM_US, K01, K04, ReportWorld, report_run
from tests.domain.contracts.test_to_date_reads import posted_revenue

HOME: Final = "/api/v1/dashboard/home"
ZERO: Final = Decimal(0)
LINES: Final = (
    "OPENING",
    "NEW_CONTRACTS",
    "MODIFICATIONS",
    "VC_ESTIMATE_CHANGES",
    "LATE_EVENTS",
    "REVENUE",
    "CANCELLATIONS",
    "EXEMPTIONS",
    "FX",
    "UNEXPLAINED",
    "CLOSING",
)
BALANCED: Final = {"TO_ROLLFORWARD_BALANCES": "PASS", "TO_RPO_ROLLFORWARD_EQ_RPO": "PASS"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def amount(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(value["amount"])


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def ties(run: Mapping[str, Any]) -> dict[str, str]:
    return {str(item["code"]): str(item["result"]) for item in run["tie_out_results"]}


def month_end(period_key: str) -> date:
    """The end of ``FY2026-P<month>`` in the worlds' calendar: months, the year from January."""
    month = int(period_key[8:10])
    return date(2026 + month // 12, month % 12 + 1, 1) - timedelta(days=1)


def rollforward(world: ReportWorld, entity: str, period_key: str) -> tuple[dict[str, Decimal], Any]:
    """The section 1 lines of RPT-07 for one period, by line code, and the run."""
    run, rows = report_run(
        world,
        "rpo_rollforward",
        {
            "entity_codes": [entity],
            "book": "ASC606",
            "from_period_key": period_key,
            "to_period_key": period_key,
        },
    )
    lines = {key: amount(row["rpo"]) for key, row in keyed(rows).items() if row.get("section") == 1}
    return lines, run


def stated(**movements: Decimal) -> dict[str, Decimal]:
    """Every line of S15-R-12 by code: the ones named, and zero for the rest."""
    return {code: movements.get(code, ZERO) for code in LINES}


@pytest.mark.slow
@pytest.mark.parametrize(
    ("contract", "entity", "entered", "following", "allocation"),
    [
        (K01, AVM_US, "FY2026-P01", "FY2026-P02", Decimal("135000.00")),
        (K04, AVM_UK, "FY2026-P04", "FY2026-P05", Decimal("68000.00")),
    ],
)
def test_a_contract_is_in_the_rpo_from_the_day_it_is_activated(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    contract: str,
    entity: str,
    entered: str,
    following: str,
    allocation: Decimal,
) -> None:
    """At the end of the period a contract was activated in — a date before the date of its one
    version — the RPO report, the contract read, the Home figure and RPT-11 state its remainder
    of that date: the allocation less the revenue the ledger holds through the period. The
    rollforward of that period shows the allocation as new and the period's revenue; the
    following period opens at that closing and nothing is unexplained in either.

    Fail-first, through the product: no RPO, no RPT-11 row and a Home figure of 0.00 at that
    date; the contract read stated the remainder less the obligation satisfied later; the
    following period's rollforward showed the whole allocation as new and the first period's
    revenue as unexplained, ``TO_ROLLFORWARD_BALANCES`` FAIL."""
    if contract == K04:
        k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
        world, contract_id, currency = k04.report, str(k04.contract_id), "GBP"
    else:
        world = worlds.k01_pellworth(app, keyring, clock, files)
        contract_id, currency = str(world.contracts[K01].contract["id"]), "USD"
    first, second = month_end(entered), month_end(following)
    to_first = posted_revenue(world.place, contract_id, first)
    in_second = posted_revenue(world.place, contract_id, second) - to_first
    assert to_first > 0 and in_second > 0  # the ledger holds revenue of both periods
    remainder = allocation - to_first
    base = {"entity_codes": [entity], "book": "ASC606"}

    run, rows = report_run(world, "rpo", {**base, "period_key": entered})
    assert run["control_totals"]["total"] == {currency: f"{remainder:.2f}"}
    assert amount(keyed(rows)[f"contract:{contract}"]["total"]) == remainder
    assert ties(run) == {"TO_RPO_ROLLFORWARD_EQ_RPO": "PASS"}

    shown = get(app, f"/api/v1/contracts/{contract_id}", world.maya, {"as_of": first.isoformat()})
    assert shown.status_code == 200, shown.text
    kpis = shown.json()["kpis"]
    assert amount(kpis["rpo"]) == remainder
    assert amount(kpis["scheduled"]) + amount(kpis["awaiting_trigger"]) == remainder

    home = get(app, HOME, world.maya, {"entity": entity, "period": entered, "book": "ASC606"})
    assert home.status_code == 200, home.text
    assert amount(home.json()["rpo"]["total"]) == remainder

    _, listed = report_run(world, "latest_contract_status", {**base, "as_of": first.isoformat()})
    assert sorted(row["obligation_key"] for row in listed) == ["O1", "O2"]
    assert sum((amount(row["revenue_cum"]) for row in listed), ZERO) == to_first
    assert sum((amount(row["remaining_allocation"]) for row in listed), ZERO) == remainder

    lines, run = rollforward(world, entity, entered)
    assert lines == stated(NEW_CONTRACTS=allocation, REVENUE=-to_first, CLOSING=remainder)
    assert ties(run) == BALANCED
    lines, run = rollforward(world, entity, following)
    assert lines == stated(OPENING=remainder, REVENUE=-in_second, CLOSING=remainder - in_second)
    assert ties(run) == BALANCED


@pytest.mark.slow
def test_every_period_of_k01_rolls_forward_without_a_difference(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The identity period by period, January to September 2026: each period opens at the
    closing of the one before, its revenue line is the revenue the ledger holds for it, the
    allocation is new in January alone, and no other line holds an amount — nothing is a late
    event and nothing is unexplained.

    Fail-first: January had no line at all, and February showed the allocation as new."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    contract_id = str(world.contracts[K01].contract["id"])
    allocation = Decimal("135000.00")
    closing, posted = ZERO, ZERO
    for month in range(1, 10):
        key = f"FY2026-P{month:02d}"
        to_date = posted_revenue(world.place, contract_id, month_end(key))
        lines, run = rollforward(world, AVM_US, key)
        assert lines == stated(
            OPENING=closing,
            NEW_CONTRACTS=allocation if month == 1 else ZERO,
            REVENUE=-(to_date - posted),
            CLOSING=allocation - to_date,
        ), key
        assert ties(run) == BALANCED, key
        closing, posted = lines["CLOSING"], to_date
    assert posted > 0 and closing == allocation - posted


def _february_by_origin(world: ReportWorld, contract_id: str) -> dict[str | None, Decimal]:
    """The ledger: the contract's ``REVENUE`` posted in February 2026 by origin period key (None:
    revenue of February itself), credits positive."""
    origin = period.alias("origin_period")
    rows = world.place.rows(
        select(
            origin.c.period_key.label("origin"), func.sum(subledger_line.c.amount_txn).label("sum")
        )
        .select_from(
            subledger_line.join(period, period.c.id == subledger_line.c.period_id).outerjoin(
                origin, origin.c.id == subledger_line.c.origin_period_id
            )
        )
        .where(
            subledger_line.c.contract_id == UUID(contract_id),
            subledger_line.c.book_code == "ASC606",
            subledger_line.c.account_role == "REVENUE",
            period.c.period_key == "FY2026-P02",
        )
        .group_by(origin.c.period_key)
    )
    return {row["origin"]: -Decimal(row["sum"]) for row in rows}


@pytest.mark.slow
def test_revenue_posted_with_an_earlier_origin_is_the_late_events_line(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """S15-R-12 "late events" (SCREENS_B RPT-07 rev 1.70: the row ``LATE_EVENTS``). January is
    locked with K-01's RPO at 124,910.14; the O2 progress of 31 January arrives afterwards and its
    revenue is posted in February with January as its origin. February's rollforward opens at the
    locked figure, states that revenue — the ledger's lines of February with an earlier origin —
    on the late-events line and February's own revenue on the revenue line, and closes without a
    difference. January's RPO stays the figure it was locked at.

    Fail-first: no line carried the 6,480.00; ``UNEXPLAINED`` −6,480.00 and
    ``TO_ROLLFORWARD_BALANCES`` FAIL."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: journal runs and imports are hers
    world = worlds.on_record_clock(world, clock)
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key="FY2026-P01")
    world, _, noted = worlds.k01_late_progress(world, clock)
    assert noted["computation"]["status"] == "SUCCEEDED", noted["computation"]
    contract_id = str(world.contracts[K01].contract["id"])
    by_origin = _february_by_origin(world, contract_id)
    own, late = by_origin[None], by_origin["FY2026-P01"]
    assert (own, late) == (Decimal("9113.43"), Decimal("6480.00"))  # 16,200.00 × 40% arrives late

    locked_at = Decimal("124910.14")
    run, _ = report_run(
        world, "rpo", {"entity_codes": [AVM_US], "book": "ASC606", "period_key": "FY2026-P01"}
    )
    assert run["control_totals"]["total"] == {"USD": f"{locked_at:.2f}"}

    lines, run = rollforward(world, AVM_US, "FY2026-P02")
    assert lines == stated(
        OPENING=locked_at, LATE_EVENTS=-late, REVENUE=-own, CLOSING=locked_at - late - own
    )
    assert ties(run) == BALANCED


@pytest.mark.slow
def test_usage_allocation_change_is_reported_as_variable_consideration(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A later usage version adds its fee without calling it a new contract or unexplained."""
    world = worlds.k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    contract_id = UUID(str(world.contracts[worlds.K08].contract["id"]))
    before, _ = rollforward(world, AVM_US, "FY2026-P03")
    worlds.approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "USAGE_REPORTED",
            "effective_date": "2026-03-31",
            "payload": {
                "obligation_key": "O1",
                "usage_period_start": "2026-03-01",
                "usage_period_end": "2026-03-31",
                "metric": "API_CALLS",
                "quantity": "1500",
                "rated_amount": {"amount": "150.00", "currency": "USD"},
            },
        },
    )
    after, run = rollforward(world, AVM_US, "FY2026-P03")
    assert after["NEW_CONTRACTS"] == 0
    assert after["VC_ESTIMATE_CHANGES"] == Decimal("150.00")
    assert after["OPENING"] == before["OPENING"]
    assert after["CLOSING"] == before["CLOSING"]
    assert after["REVENUE"] == before["REVENUE"] - Decimal("150.00")
    assert after["UNEXPLAINED"] == 0
    assert ties(run) == BALANCED


@pytest.mark.slow
def test_first_calculation_keeps_later_usage_out_of_earlier_rpo(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defer the initial computation, then calculate activation and March usage together."""
    with monkeypatch.context() as patch:
        patch.setattr(worlds, "computed", lambda *args, **kwargs: None)
        world = worlds.k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    contract_id = UUID(str(world.contracts[worlds.K08].contract["id"]))
    worlds.approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "USAGE_REPORTED",
            "effective_date": "2026-03-31",
            "payload": {
                "obligation_key": "O1",
                "usage_period_start": "2026-03-01",
                "usage_period_end": "2026-03-31",
                "metric": "API_CALLS",
                "quantity": "1500",
                "rated_amount": {"amount": "150.00", "currency": "USD"},
            },
        },
    )
    january_revenue = posted_revenue(world.place, str(contract_id), date(2026, 1, 31))
    january, run = rollforward(world, AVM_US, "FY2026-P01")
    assert january["NEW_CONTRACTS"] == Decimal("80000.00")
    assert january["CLOSING"] == Decimal("80000.00") - january_revenue
    assert january["UNEXPLAINED"] == 0
    assert ties(run) == BALANCED
    worlds.journal_run(world, period_key="FY2026-P01")
    waterfall, _ = report_run(
        world,
        "revenue_waterfall",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "from_period_key": "FY2026-P01",
            "to_period_key": "FY2026-P12",
            "as_of": "2026-01-31",
            "measure": "BY_STATE",
        },
    )
    assert waterfall["control_totals"] == {
        "currency_view": "transaction",
        "forecast_currency_basis": "transaction",
        "tie_out_currency_basis": "transaction",
        "translation_rates": [],
        "recognized_total": {"USD": f"{january_revenue:.2f}"},
        "scheduled_total": {"USD": f"{Decimal('80000.00') - january_revenue:.2f}"},
        "awaiting_trigger_total": {"USD": "0.00"},
    }
    assert all(item["result"] == "PASS" for item in waterfall["tie_out_results"]), waterfall[
        "tie_out_results"
    ]
    rpo, _ = report_run(
        world, "rpo", {"entity_codes": [AVM_US], "book": "ASC606", "period_key": "FY2026-P01"}
    )
    cell = get(
        world.app,
        f"/api/v1/explain/report-runs/{rpo['id']}/cell",
        world.maya,
        {"row_key": f"contract:{worlds.K08}", "column_key": "total"},
    )
    assert cell.status_code == 200, cell.text
    assert Decimal(cell.json()["value"]["amount"]) == january["CLOSING"]
    contributors = cell.json()["contributors"]["items"]
    assert contributors
    for contributor in contributors:
        assert contributor["measure"] == "scheduled_fixed_amount"
        explained = get(world.app, contributor["href"], world.maya)
        assert explained.status_code == 200, explained.text
        assert explained.json()["value"] == contributor["value"]
    march, run = rollforward(world, AVM_US, "FY2026-P03")
    assert march["NEW_CONTRACTS"] == 0
    assert march["VC_ESTIMATE_CHANGES"] == Decimal("150.00")
    assert march["UNEXPLAINED"] == 0
    assert ties(run) == BALANCED


@pytest.mark.slow
@pytest.mark.parametrize("delivered", [False, True])
def test_royalty_rpo_nets_guarantee_and_waits_for_licence_satisfaction(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, delivered: bool
) -> None:
    """A 15,000 statement adds 3,000 above a 12,000 guarantee; recognition needs delivery."""
    world = worlds.report_world(app, keyring, clock, files, contracts=())
    assign(world.priya.member, "revenue_reviewer")
    author = world.place.author
    template = published_template(
        app,
        author,
        world.marcus,
        code="TPL-ROYALTY-RPO",
        outputs={
            "obligation_kind": "LICENCE",
            "distinctness": "distinct",
            "satisfaction_pattern": "POINT_IN_TIME",
            "over_time_criterion": "NOT_APPLICABLE",
            "recognition_method": "ROYALTY",
            "licence_nature": "FUNCTIONAL",
        },
        case_line={
            "obligation_key": "O1",
            "product_code": worlds.PLATFORM,
            "quantity": "1",
            "total_price": "12000.00",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    product_id = world.place.scalar(select(product.c.id).where(product.c.code == worlds.PLATFORM))
    set_default_template(app, author, str(product_id), template["template_id"])
    customer = customer_id(app, author, code="ROY-RPO", name="Royalty report test")
    body = worlds.k01_body(customer)
    body["external_id"] = "ROY-RPO"
    body["lines"] = [{**body["lines"][0], "total_price": {"amount": "12000.00", "currency": "USD"}}]
    booked = booked_contract(world.place, body, activate=True)
    contract_id = UUID(str(booked.contract["id"]))
    computed(world.place, UUID(str(booked.combination_group["id"])))
    world = replace(world, contracts={"ROY-RPO": booked})
    if delivered:
        worlds.approved_manual_events(
            world.place,
            world.priya,
            contract_id,
            {
                "event_type": "DELIVERY_RECORDED",
                "effective_date": "2026-01-01",
                "payload": {"obligation_key": "O1", "quantity": "1", "trigger": "CONTROL_TRANSFER"},
            },
        )
    before, _ = rollforward(world, AVM_US, "FY2026-P03")
    worlds.approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "USAGE_REPORTED",
            "effective_date": "2026-03-31",
            "payload": {
                "obligation_key": "O1",
                "usage_period_start": "2026-01-01",
                "usage_period_end": "2026-03-31",
                "metric": "LICENSEE_SALES",
                "quantity": "150000",
                "rated_amount": {"amount": "15000.00", "currency": "USD"},
                "is_royalty_statement": True,
            },
        },
    )
    after, run = rollforward(world, AVM_US, "FY2026-P03")
    assert after["OPENING"] == before["OPENING"] == (ZERO if delivered else Decimal("12000.00"))
    assert after["NEW_CONTRACTS"] == ZERO
    assert after["VC_ESTIMATE_CHANGES"] == Decimal("3000.00")
    assert after["REVENUE"] == (Decimal("-3000.00") if delivered else ZERO)
    assert after["CLOSING"] == (ZERO if delivered else Decimal("15000.00"))
    assert after["UNEXPLAINED"] == ZERO
    assert ties(run) == BALANCED

    if not delivered:
        worlds.approved_manual_events(
            world.place,
            world.priya,
            contract_id,
            {
                "event_type": "DELIVERY_RECORDED",
                "effective_date": "2026-04-01",
                "payload": {"obligation_key": "O1", "quantity": "1", "trigger": "CONTROL_TRANSFER"},
            },
        )
        april, april_run = rollforward(world, AVM_US, "FY2026-P04")
        assert april["OPENING"] == Decimal("15000.00")
        assert april["REVENUE"] == Decimal("-15000.00")
        assert april["VC_ESTIMATE_CHANGES"] == april["CLOSING"] == april["UNEXPLAINED"] == ZERO
        assert ties(april_run) == BALANCED
    worlds.approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "USAGE_REPORTED",
            "effective_date": "2026-05-31",
            "payload": {
                "obligation_key": "O1",
                "usage_period_start": "2026-01-01",
                "usage_period_end": "2026-03-31",
                "metric": "LICENSEE_SALES",
                "quantity": "140000",
                "rated_amount": {"amount": "14000.00", "currency": "USD"},
                "is_royalty_statement": True,
            },
        },
    )
    corrected, corrected_run = rollforward(world, AVM_US, "FY2026-P05")
    assert corrected["VC_ESTIMATE_CHANGES"] == Decimal("-1000.00")
    assert corrected["REVENUE"] == Decimal("1000.00")
    assert corrected["OPENING"] == corrected["CLOSING"] == corrected["UNEXPLAINED"] == ZERO
    assert ties(corrected_run) == BALANCED

    from erev_api.enums import RegistryCategory
    from tests.domain.reports.test_rpo_disaggregation import publish

    clock.advance(timedelta(minutes=1))
    publish(world, RegistryCategory.PRACTICAL_EXPEDIENT, {"rpo.exemption_royalty_vc": "APPLY"})
    _, disclosure = report_run(
        world,
        "rpo",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "period_key": "FY2026-P03",
        },
    )
    exemptions = [row for row in disclosure if row.get("section") == 2]
    if delivered:
        assert exemptions == []
    else:
        assert len(exemptions) == 1
        assert exemptions[0]["expedient"] == "POL-199"
        assert amount(exemptions[0]["excluded_amount"]) == Decimal("3000")
        contract_row = next(row for row in disclosure if row["row_key"] == "contract:ROY-RPO")
        assert amount(contract_row["total"]) == Decimal("12000")
    net, net_run = rollforward(world, AVM_US, "FY2026-P03")
    assert net["CLOSING"] == (ZERO if delivered else Decimal("12000"))
    assert net["EXEMPTIONS"] == (ZERO if delivered else Decimal("-3000"))
    assert net["UNEXPLAINED"] == ZERO

    from support.reference import post

    repeated = post(app, f"/api/v1/report-runs/{net_run['id']}/rerun", world.maya, {})
    assert repeated.status_code == 202, repeated.text
    assert worlds.run_now(world, UUID(repeated.json()["id"]))["state"] == "SUCCEEDED"
    rows = get(
        app, f"/api/v1/report-runs/{repeated.headers['x-erev-report-run-id']}/data", world.maya
    ).json()["items"]
    assert {
        key: amount(row["rpo"]) for key, row in keyed(rows).items() if row.get("section") == 1
    } == net


@pytest.mark.slow
@pytest.mark.parametrize("termination_kind", ["FULL", "PARTIAL"])
@pytest.mark.parametrize("refund", [0, 40])
@pytest.mark.parametrize("amended", [False, True])
def test_same_day_usage_termination_public_report(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    termination_kind: str,
    refund: int,
    amended: bool,
) -> None:
    """An approved termination must reach the termination engine and Reporting."""
    from support.factories import AVM_US_CHART, published_mapping
    from support.modifications import confirm_answers
    from support.reference import approve, post

    original_body = worlds.k08_body

    def two_obligations(customer: UUID) -> dict[str, Any]:
        body = original_body(customer)
        body["lines"].append({**body["lines"][0], "obligation_key": "O2"})
        return body

    with monkeypatch.context() as patch:
        patch.setattr(worlds, "k08_body", two_obligations)
        patch.setattr(
            worlds,
            "published_mapping",
            lambda app, author, approver: published_mapping(
                app,
                author,
                approver,
                chart=(
                    *AVM_US_CHART,
                    ("2110", "Refund liability", "LIABILITY", "C", "REFUND_LIABILITY"),
                ),
            ),
        )
        world = worlds.k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    cid = UUID(str(world.contracts[worlds.K08].contract["id"]))

    def apply_modification(created: Response) -> dict[str, Any]:
        mid = created.json()["id"]
        classified = post(app, f"/api/v1/modifications/{mid}/classify", world.maya, {})
        assert classified.status_code == 200, classified.text
        confirm_answers(app, mid, world.maya)
        queued = post(app, f"/api/v1/modifications/{mid}/preview", world.maya, {})
        assert queued.status_code == 202, queued.text
        finished = worlds.run_now(world, UUID(queued.json()["id"]))
        assert finished["state"] == "SUCCEEDED", finished
        sent = post(
            app,
            f"/api/v1/modifications/{mid}/submit",
            world.maya,
            {"comment": "Apply the reviewed change."},
        )
        assert sent.status_code == 200, sent.text
        approved = approve(app, sent.json()["approval_request_id"], world.priya)
        assert approved.status_code == 200, approved.text
        shown = get(app, f"/api/v1/modifications/{mid}", world.maya).json()
        if shown["status"] == "SUBMITTED":
            approved = approve(app, sent.json()["approval_request_id"], world.marcus)
            assert approved.status_code == 200, approved.text
            shown = get(app, f"/api/v1/modifications/{mid}", world.maya).json()
        assert shown["status"] == "APPLIED", shown
        return shown

    worlds.approved_manual_events(
        world.place,
        world.priya,
        cid,
        {
            "event_type": "USAGE_REPORTED",
            "effective_date": "2026-01-01",
            "payload": {
                "obligation_key": "O1",
                "usage_period_start": "2026-01-01",
                "usage_period_end": "2026-01-01",
                "metric": "API_CALLS",
                "quantity": "1500",
                "rated_amount": {"amount": "150.00", "currency": "USD"},
            },
        },
    )
    if amended:
        estimate = post(
            app,
            f"/api/v1/contracts/{cid}/estimates",
            world.maya,
            {
                "estimate_kind": "VARIABLE_CONSIDERATION",
                "element_code": "BONUS-SAME-DAY",
                "vc_element_type": "BONUS",
                "method": "MOST_LIKELY_AMOUNT",
            },
        )
        assert estimate.status_code == 201, estimate.text
        worlds.estimate_version_approved(
            app,
            world.maya,
            world.priya,
            estimate.json()["id"],
            {
                "effective_date": "2026-01-01",
                "scenarios": [{"outcome": "Bonus earned", "amount": "200"}],
                "unconstrained_amount": "200",
                "most_conservative_amount": "200",
                "constrained_amount": "200",
                "rationale": "Inception-date estimate before amendment and termination.",
            },
            constraint_of="BONUS-SAME-DAY",
        )
        amendment = post(
            app,
            f"/api/v1/contracts/{cid}/modifications",
            world.maya,
            {
                "effective_date": "2026-01-01",
                "kind": "PRICE_CHANGE",
                "reference": "PRICE-SAME-DAY",
                "lines": [
                    {
                        "obligation_key": "O1",
                        "action": "CHANGE",
                        "product_code": worlds.API_CALL,
                        "quantity_delta": "0",
                        "consideration_delta": {"amount": "100", "currency": "USD"},
                    }
                ],
                "rationale": "Increase service consideration before termination.",
            },
        )
        assert amendment.status_code == 201, amendment.text
        apply_modification(amendment)
    created = post(
        app,
        f"/api/v1/contracts/{cid}/modifications",
        world.maya,
        {
            "effective_date": "2026-01-01",
            "kind": "TERMINATION",
            "reference": "TERM-SAME-DAY",
            "termination": {
                "kind": termination_kind,
                "refund_amount": {"amount": str(refund), "currency": "USD"},
            },
            "lines": [
                {
                    "obligation_key": "O1",
                    "action": "REMOVE",
                    "product_code": worlds.API_CALL,
                    "quantity_delta": "0",
                    "consideration_delta": {"amount": str(-refund), "currency": "USD"},
                }
            ],
            "rationale": "Terminate the selected scope with the stated refund.",
        },
    )
    assert created.status_code == 201, created.text
    shown = apply_modification(created)
    event = get(app, f"/api/v1/events/{shown['applied_event_id']}", world.maya).json()
    assert event["event_type"] == "CONTRACT_TERMINATED", event
    contract = get(app, f"/api/v1/contracts/{cid}", world.maya).json()
    assert contract["status"] == ("TERMINATED" if termination_kind == "FULL" else "ACTIVE"), (
        contract
    )
    lines, run = rollforward(world, AVM_US, "FY2026-P01")
    # The initial computation predates the later approved estimate: even on the
    # same effective date, its increment belongs to VC rather than new contracts.
    assert lines["NEW_CONTRACTS"] == Decimal("160000"), lines
    assert lines["VC_ESTIMATE_CHANGES"] == Decimal("150") + (200 if amended else 0), lines
    # Partial termination reallocates the nonrefundable remaining pool to O2;
    # full termination has no remaining recipient and recognizes it on termination.
    fixed = Decimal("160000") + (300 if amended else 0)
    assert lines["MODIFICATIONS"] == (100 if amended else 0)
    continuing = ((fixed - refund) * 31 / 365).quantize(Decimal("0.01"))
    expected_revenue = (
        fixed + 150 - refund if termination_kind == "FULL" else Decimal("150") + continuing
    )
    assert lines["REVENUE"] == -expected_revenue
    assert lines["CANCELLATIONS"] == -refund
    assert lines["CLOSING"] == (0 if termination_kind == "FULL" else fixed - refund - continuing)
    assert lines["UNEXPLAINED"] == 0
    assert ties(run) == BALANCED

    original = get(app, f"/api/v1/report-runs/{run['id']}/data", world.maya).json()["items"]
    rerun = post(app, f"/api/v1/report-runs/{run['id']}/rerun", world.maya, {})
    assert rerun.status_code == 202, rerun.text
    assert worlds.run_now(world, UUID(rerun.json()["id"]))["state"] == "SUCCEEDED"
    repeated = get(
        app, f"/api/v1/report-runs/{rerun.headers['x-erev-report-run-id']}/data", world.maya
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["items"] == original


@pytest.mark.slow
@pytest.mark.parametrize("with_excluded_usage", [False, True])
def test_collectibility_reentry_public_rpo(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
    with_excluded_usage: bool,
) -> None:
    """Reviewed Step 1 exits and re-entry reach the retained RPO calculation."""
    from support.factories import step1_criteria
    from support.reference import approve, post

    original_body = worlds.k08_body
    monkeypatch.setattr(
        worlds,
        "k08_body",
        lambda customer: {**original_body(customer), "document_ref": "AGR-K08"},
    )
    world = worlds.k08_ulvane(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    cid = UUID(str(world.contracts[worlds.K08].contract["id"]))

    def reviewed(probable: bool) -> str:
        topic = "COLLECTIBILITY" if probable else "NOT_A_CONTRACT"
        record = worlds.judgement_submitted(
            app,
            world.maya,
            {
                "topic": topic,
                "subject_type": "contract",
                "subject_id": str(cid),
                "book": "ASC606",
                "conclusion": "Collection reassessed for this contract.",
                "rationale": "Updated customer credit evidence.",
                "questionnaire": {
                    "criteria": step1_criteria(topic),
                    **({} if probable else {"consideration_nonrefundable": False}),
                },
            },
        )
        decided = approve(app, record["approval_request_id"], world.marcus)
        assert decided.status_code == 200, decided.text
        return record["id"]

    record = reviewed(False)
    events = [
        {
            "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
            "effective_date": "2026-06-01",
            "payload": {"description": "Customer entered financial distress."},
        },
        {
            "event_type": "COLLECTIBILITY_ASSESSED",
            "effective_date": "2026-06-01",
            "payload": {"book": "ASC606", "is_probable": False, "judgement_record_id": record},
        },
    ]
    if with_excluded_usage:
        events.append(
            {
                "event_type": "USAGE_REPORTED",
                "effective_date": "2026-06-01",
                "payload": {
                    "obligation_key": "O1",
                    "usage_period_start": "2026-06-01",
                    "usage_period_end": "2026-06-01",
                    "metric": "API_CALLS",
                    "quantity": "1500",
                    "rated_amount": {"amount": "150.00", "currency": "USD"},
                },
            }
        )
        # Step 1 and manual facts have separate approval routes. The public API
        # rejects a mixed batch; verify the supported sequence instead of weakening it.
        from erev_api.db.tables import contract_version

        versions = select(func.count()).select_from(contract_version)
        original_count = world.place.scalar(versions)
        current = get(app, f"/api/v1/contracts/{cid}", world.maya)
        rejected = post(
            app,
            f"/api/v1/contracts/{cid}/events",
            world.maya,
            {"events": events, "evidence_file_ids": [worlds.evidence_file(app, world.maya)]},
            if_match=current.headers["ETag"],
        )
        assert rejected.status_code == 422, rejected.text
        assert {error["rule_id"] for error in rejected.json()["errors"]} == {"API-R-30"}
        assert world.place.scalar(versions) == original_count
        exited = worlds._appended_through_api(world.place, cid, *events[:2])
        usage = worlds.approved_manual_events(world.place, world.priya, cid, events[2])
        assert usage["computation"]["status"] == "SUCCEEDED", usage
    else:
        exited = worlds._appended_through_api(world.place, cid, *events)
    assert exited["computation"]["status"] == "SUCCEEDED", exited
    june, june_run = rollforward(world, AVM_US, "FY2026-P06")
    june_rows = get(app, f"/api/v1/report-runs/{june_run['id']}/data", world.maya).json()["items"]
    assert june["OPENING"] == Decimal("46904.11"), june  # 80,000 less 151/365 recognized
    assert june["ELIGIBILITY_CHANGES"] + june["REVENUE"] == -june["OPENING"], june
    assert june["CLOSING"] == june["NEW_CONTRACTS"] == june["CANCELLATIONS"] == 0, june
    assert june["UNEXPLAINED"] == 0, june
    assert june["VC_ESTIMATE_CHANGES"] == 0, june

    clock.advance(timedelta(minutes=1))
    record = reviewed(True)
    worlds._appended_through_api(
        world.place,
        cid,
        {
            "event_type": "COLLECTIBILITY_ASSESSED",
            "effective_date": "2026-07-01",
            "payload": {"book": "ASC606", "is_probable": True, "judgement_record_id": record},
        },
    )
    current = get(app, f"/api/v1/contracts/{cid}", world.maya)
    assert current.status_code == 200, current.text
    submitted = post(
        app,
        f"/api/v1/contracts/{cid}/submit-activation",
        world.maya,
        {"comment": "Collection is probable again."},
        if_match=current.headers["ETag"],
    )
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, submitted.headers["x-erev-approval-request"], world.priya)
    assert decided.status_code == 200, decided.text
    july, run = rollforward(world, AVM_US, "FY2026-P07")
    assert july["OPENING"] == july["NEW_CONTRACTS"] == july["CANCELLATIONS"] == 0, july
    assert july["CLOSING"] == Decimal("33534.25"), july  # 80,000 less 212/365 recognized
    assert 0 < july["ELIGIBILITY_CHANGES"] < Decimal("80000"), july
    assert july["UNEXPLAINED"] == 0, july
    assert july["ELIGIBILITY_CHANGES"] + july["REVENUE"] == july["CLOSING"], july
    assert ties(run) == BALANCED

    repeated = post(app, f"/api/v1/report-runs/{june_run['id']}/rerun", world.maya, {})
    assert repeated.status_code == 202, repeated.text
    assert worlds.run_now(world, UUID(repeated.json()["id"]))["state"] == "SUCCEEDED"
    retained = get(
        app, f"/api/v1/report-runs/{repeated.headers['x-erev-report-run-id']}/data", world.maya
    )
    assert retained.status_code == 200, retained.text
    assert retained.json()["items"] == june_rows
