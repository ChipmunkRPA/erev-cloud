"""RPT-01 states an obligation under the entity that performs it (SCREENS_B RPT-01 rev 1.69;
supervisor rulings R-78 (d) and R-121 (g)). PostgreSQL-bound, through ``POST /report-runs``.

World: PRD WLD-K-04 ``SF-ORD-UK-2001`` (``support.worlds.k04_saltmarsh``), contracted by AVM-UK in
GBP: O1, 60,000.00 from 1 April 2026 to 31 March 2027, performed by AVM-US (allocated 58,285.71);
O2, 8,000.00, performed by AVM-UK (allocated 9,714.29), half complete on 30 April and complete on
31 May. The revenue of O1 is in AVM-US's books — its ``REVENUE`` lines, against the intercompany
receivable (POLICIES JET-13) — and the revenue of O2 in AVM-UK's.

PRODUCT DEFECT, measured through the product on 2026-10-01: the report read its population by the
CONTRACTING entity. A run for AVM-UK stated 9,647.75 and 9,807.44 for April and May — O1 and O2
together — where AVM-UK's books hold 4,857.14 and 4,857.15; a run for AVM-US stated no row where
its books hold 4,790.61 and 4,950.29; and ``TO_WATERFALL_EQ_JE_REVENUE``, which compares with the
journal of the run's entities, could pass for neither.

The Home reads the same population (SCREENS §2.5 rev 1.41; the supervisor's ruling of 2026-10-01)
and its three figure panels as the reports' jobs read them, so a context has one answer whoever
asks. Measured before: the Home of AVM-UK stated 9,647.75 for April, and for a Revenue Accountant
of AVM-UK alone it was refused whole — 422, rule S15-R-01, over O1's schedule lines, which are
AVM-US's rows and outside that reader's scope; the Home of AVM-US stated 0.00.

The oracle stands outside the builder: the ledger — the ``REVENUE`` subledger lines of each
entity, obligation and period — and, for the tie-out, a calculated journal run of each entity and
period.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import legal_entity, obligation, period, subledger_line
from erev_api.domain.reports import dashboard, tie_outs
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor, colleague
from support.reference import get, holding, slug
from support.worlds import AVM_UK, AVM_US, K04, K04World, ReportWorld, journal_run, report_run

CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"
HOME: Final = "/api/v1/dashboard/home"
ALLOCATION: Final = Decimal("68000.00")  # WLD-K-04: 58,285.71 for O1 and 9,714.29 for O2
READERS: Final = ("every entity", "one entity")
CUSTOMER: Final = "Saltmarsh Freight Ltd (Demo)"
APRIL, MAY = "FY2026-P04", "FY2026-P05"
O1_ROW: Final = f"obligation:{K04}:O1"
O2_ROW: Final = f"obligation:{K04}:O2"
# the ledger of the world, as measured: (entity, obligation) → (April, May), credits positive
BOOKS: Final[Mapping[tuple[str, str], tuple[Decimal, Decimal]]] = {
    (AVM_US, "O1"): (Decimal("4790.61"), Decimal("4950.29")),
    (AVM_UK, "O2"): (Decimal("4857.14"), Decimal("4857.15")),
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k04(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K04World:
    return worlds.k04_saltmarsh(app, keyring, clock, files)


@pytest.fixture
def world(k04: K04World) -> ReportWorld:
    return k04.report


def gbp(amount: Decimal | str) -> dict[str, str]:
    return {"amount": f"{Decimal(amount):.2f}", "currency": "GBP"}


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def tie(run: Mapping[str, Any]) -> Mapping[str, Any]:
    (found,) = [
        item
        for item in run["tie_out_results"]
        if item["code"] == tie_outs.TO_WATERFALL_EQ_JE_REVENUE
    ]
    return dict(found)


def parameters(*entities: str) -> dict[str, Any]:
    return {
        "entity_codes": list(entities),
        "book": "ASC606",
        "from_period_key": APRIL,
        "to_period_key": MAY,
        "row_dimension": "OBLIGATION",
    }


def ledger(world: ReportWorld) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """The ``REVENUE`` lines of April and May 2026 by posting entity and obligation."""
    rows = world.place.rows(
        select(
            legal_entity.c.code.label("entity"),
            obligation.c.obligation_key.label("obligation"),
            period.c.period_key.label("period"),
            func.sum(subledger_line.c.amount_txn).label("amount"),
        )
        .select_from(
            subledger_line.join(legal_entity, legal_entity.c.id == subledger_line.c.entity_id)
            .join(obligation, obligation.c.id == subledger_line.c.obligation_id)
            .join(period, period.c.id == subledger_line.c.period_id)
        )
        .where(
            subledger_line.c.book_code == "ASC606",
            subledger_line.c.account_role == "REVENUE",
            period.c.period_key.in_([APRIL, MAY]),
        )
        .group_by(legal_entity.c.code, obligation.c.obligation_key, period.c.period_key)
    )
    found: dict[tuple[str, str], dict[str, Decimal]] = {}
    for row in rows:
        found.setdefault((str(row["entity"]), str(row["obligation"])), {})[
            str(row["period"])
        ] = -Decimal(row["amount"])
    return {key: (months[APRIL], months[MAY]) for key, months in found.items()}


@pytest.mark.slow
def test_rpt_01_states_an_obligation_under_the_entity_that_performs_it(
    world: ReportWorld, k04: K04World
) -> None:
    """A run for AVM-US states O1 — which it performs for a contract of AVM-UK — with the revenue
    its books hold; a run for AVM-UK states O2 alone; a run for both states the contract whole.
    In each the row's entity is the performing entity, the recognized amounts are the ledger's
    lines of that entity, and with a journal run of each entity and period
    ``TO_WATERFALL_EQ_JE_REVENUE`` passes: both sides are the same entity's revenue.

    A reader of AVM-US alone reads the row of its entity's run with the contract's external id
    and the customer's name; ``GET /contracts/{id}`` stays 404 for them.

    Fail-first (the population read by the contracting entity): the run for AVM-US had no row,
    the run for AVM-UK stated both obligations — 9,647.75 and 9,807.44 against 4,857.14 and
    4,857.15 in its books — and the tie-out failed for AVM-UK and passed on nothing for AVM-US."""
    assert ledger(world) == BOOKS  # the ledger agrees with the oracle before any report is read
    for entity in (AVM_US, AVM_UK):
        for key in (APRIL, MAY):
            journal_run(world, period_key=key, entity_code=entity)
    cases = {
        (AVM_US,): {O1_ROW: (AVM_US, "O1")},
        (AVM_UK,): {O2_ROW: (AVM_UK, "O2")},
        (AVM_UK, AVM_US): {O1_ROW: (AVM_US, "O1"), O2_ROW: (AVM_UK, "O2")},
    }
    for entities, expected in cases.items():
        run, rows = report_run(world, "revenue_waterfall", parameters(*entities))
        found = keyed(rows)
        assert set(found) == {*expected, "TOTAL:GBP"}, entities
        april = may = Decimal(0)
        for row_key, held in expected.items():
            row = found[row_key]
            assert row["entity_code"] == held[0], row_key
            assert (row[f"period:{APRIL}"], row[f"period:{MAY}"]) == (
                gbp(BOOKS[held][0]),
                gbp(BOOKS[held][1]),
            ), (entities, row_key)
            april, may = april + BOOKS[held][0], may + BOOKS[held][1]
        total = found["TOTAL:GBP"]
        assert (total[f"period:{APRIL}"], total[f"period:{MAY}"]) == (gbp(april), gbp(may))
        assert run["control_totals"]["recognized_total"] == {"GBP": f"{april + may:.2f}"}
        assert tie(run) == {
            "code": "TO_WATERFALL_EQ_JE_REVENUE",
            "result": "PASS",
            "expected": [gbp(april + may)],
            "actual": [gbp(april + may)],
            "difference": [gbp("0.00")],
        }, entities
    # Consequence (4) of SCREENS_B RPT-01, [J] (the supervisor's ruling of 2026-10-01 13:54): a
    # reader whose role names AVM-US alone reads its entity's run with the contract's external
    # id and the customer's name in the row — what was performed, and for whom — while the
    # contract's own page stays closed to them.
    reader = _reader(k04, "one entity", k04.us_entity_id, "ulla")
    _, rows = report_run(world, "revenue_waterfall", parameters(AVM_US), actor=reader)
    row = keyed(rows)[O1_ROW]
    assert (row["contract_external_id"], row["customer_name"], row["entity_code"]) == (
        K04,
        CUSTOMER,
        AVM_US,
    )
    assert row[f"period:{APRIL}"] == gbp(BOOKS[(AVM_US, "O1")][0])
    closed = get(world.app, f"/api/v1/contracts/{k04.contract_id}", reader)
    assert closed.status_code == 404, closed.text


@pytest.mark.slow
def test_the_cell_of_a_performed_obligation_names_the_performing_entitys_lines(
    world: ReportWorld,
) -> None:
    """``GET /explain/report-runs/{id}/cell`` for O1 in April of a run for AVM-US: the value is
    AVM-US's revenue of the month, and every subledger line it names is a line of AVM-US's books
    (SB-R-07; REQ-RPT-017)."""
    run, _ = report_run(world, "revenue_waterfall", parameters(AVM_US))
    explained = get(
        world.app,
        CELL.format(run_id=run["id"]),
        world.maya,
        {"row_key": O1_ROW, "column_key": f"period:{APRIL}"},
    )
    assert explained.status_code == 200, explained.text
    body = explained.json()
    assert body["value"] == gbp(BOOKS[(AVM_US, "O1")][0])
    items = body["contributors"]["items"]
    line_ids = [UUID(str(item["id"])) for item in items if item["object_type"] == "subledger_line"]
    assert line_ids
    owners = world.place.rows(
        select(legal_entity.c.code)
        .select_from(
            subledger_line.join(legal_entity, legal_entity.c.id == subledger_line.c.entity_id)
        )
        .where(subledger_line.c.id.in_(line_ids))
        .distinct()
    )
    assert [str(row["code"]) for row in owners] == [AVM_US]
    assert [item["value"] for item in items if item["object_type"] == "schedule_line"] == [
        gbp(BOOKS[(AVM_US, "O1")][0])
    ]


def _reader(k04: K04World, who: str, entity_id: UUID, name: str) -> Actor:
    """Maya, who reads every entity, or a Revenue Accountant whose role names one entity."""
    world = k04.report
    if who == "every entity":
        return world.maya
    return holding(
        world.app, colleague(world.tenant_id, name), "revenue_accountant", entity_ids=[entity_id]
    )


@pytest.mark.slow
@pytest.mark.parametrize("who", READERS)
def test_the_home_states_the_revenue_its_entity_performs_whoever_asks(
    app: FastAPI, k04: K04World, who: str
) -> None:
    """The Home of AVM-UK for April 2026: revenue is what AVM-UK's books hold — O2's 4,857.14 —
    and the RPO is the contract's, 68,000.00 less the revenue both entities' books hold through
    April. A reader of every entity and a reader of AVM-UK alone get the same three figures.

    Fail-first: for the reader of every entity revenue was 9,647.75, O1's included; for the
    reader of AVM-UK alone the whole Home was refused, 422 with rule S15-R-01 on O1."""
    world = k04.report
    assert ledger(world) == BOOKS
    reader = _reader(k04, who, k04.uk_entity_id, "kit")
    home = get(app, HOME, reader, {"entity": AVM_UK, "period": APRIL, "book": "ASC606"})
    assert home.status_code == 200, home.text
    body = home.json()
    through_april = sum((months[0] for months in BOOKS.values()), Decimal(0))
    assert body["context"]["currency"] == "GBP"
    assert body["revenue"]["current"] == gbp(BOOKS[(AVM_UK, "O2")][0])
    assert body["rpo"]["total"] == gbp(ALLOCATION - through_april)
    # the liability is the contracting entity's balance: one answer, whoever asks
    stated = get(app, HOME, world.maya, {"entity": AVM_UK, "period": APRIL, "book": "ASC606"})
    assert stated.status_code == 200, stated.text
    for figure in ("revenue", "revenue_chart", "contract_liability", "rpo"):
        assert body[figure] == stated.json()[figure], figure
    assert Decimal(body["contract_liability"]["closing"]["amount"]) > 0


@pytest.mark.slow
@pytest.mark.parametrize("who", READERS)
def test_the_home_of_an_entity_that_performs_in_another_currency_is_refused_whoever_asks(
    app: FastAPI, k04: K04World, who: str
) -> None:
    """AVM-US, whose functional currency is USD, performs O1 of a GBP contract. Its Home is
    refused by the rule of every context that holds another currency — 422
    ``validation-failed`` on ``entity`` with the Home's own sentence — for a reader of every
    entity and for a reader of AVM-US alone, whose scope does not reach the contract's row.

    Fail-first: 200 with revenue 0.00 for both — the population was read by the contracting
    entity. With the population by performing entity and the panel read under the caller's own
    scope, the reader of every entity was refused and the reader of AVM-US alone still got
    0.00."""
    reader = _reader(k04, who, k04.us_entity_id, "ulla")
    home = get(app, HOME, reader, {"entity": AVM_US, "period": APRIL, "book": "ASC606"})
    assert home.status_code == 422, home.text  # the status first: a 200 has no slug
    assert slug(home) == "validation-failed"
    assert [(error["field"], error["message"]) for error in home.json()["errors"]] == [
        ("entity", dashboard.UNCONVERTED.format(currency="USD"))
    ]
