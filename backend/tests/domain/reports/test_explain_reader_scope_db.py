"""A report cell is explained as the run's job read it, and a reader is named the contributors
her entity scope reaches (item RPT-EXPLAIN-READER-SCOPE-1; 04 §16.11 rev 1.239; dev-guide
DG-KRN-DB-05 rev 1.227; the supervisor's ruling of 2026-10-01). PostgreSQL-bound, through
``POST /report-runs`` and ``GET /explain/report-runs/{id}/cell``.

World: PRD WLD-K-04 ``SF-ORD-UK-2001`` (``support.worlds.k04_saltmarsh``), contracted by AVM-UK in
GBP: O1 performed by AVM-US (allocated 58,285.71; revenue 4,790.61 in April 2026), O2 performed
by AVM-UK (allocated 9,714.29; half complete on 30 April, 4,857.14). A report run reads every row
its figures need; a reader's role may name one of the two entities alone.

PRODUCT DEFECT, measured through the product on 2026-10-01: the explainer read under the caller's
own scope. For a Revenue Accountant of AVM-UK alone the RPO's cell of the contract — a cell of her
own run — answered 422 under S15-R-01, O1's schedule lines being AVM-US's rows; for one of AVM-US
alone the waterfall's cell of O1 answered 422 "The run holds no cell …", the contract's row being
AVM-UK's.

What a reader is named is judged as the address of each contributor judges it
(``GET /explain/{object_type}/{id}/{measure}``): a schedule line and a subledger line by the
line's entity, an obligation version by its contract's contracting entity. The rest is one sum
per entity — the entity's reference and an amount.

The oracle stands outside the explainer: the allocation of WLD-X-14 and the ledger give the
figures; each contributor's own address, asked by the reader, says whether she reaches it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import legal_entity
from erev_api.enums import ContractEventType
from erev_api.events.payloads import ProgressRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.factories import appended, booked_contract, computed
from support.principals import Actor, colleague
from support.reference import get, holding
from support.worlds import (
    AVM_UK,
    AVM_US,
    IMPLEMENTATION_UK,
    K04,
    K04World,
    ReportWorld,
    report_run,
)
from tests.domain.reports.test_waterfall_entity_db import ALLOCATION, BOOKS, gbp, parameters

CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"
APRIL: Final = "FY2026-P04"
CONTRACT_ROW: Final = f"contract:{K04}"
O1_ROW: Final = f"obligation:{K04}:O1"
O1_ALLOCATED: Final = Decimal("58285.71")  # WLD-X-14
O2_ALLOCATED: Final = Decimal("9714.29")
# What the RPO of 30 April holds of each obligation: its allocation less the ledger's April.
O1_REMAINING: Final = O1_ALLOCATED - BOOKS[(AVM_US, "O1")][0]  # eleven schedule lines of AVM-US
O2_AWAITING: Final = O2_ALLOCATED - BOOKS[(AVM_UK, "O2")][0]  # awaiting its trigger
SECOND: Final = "SF-ORD-UK-2002"
SECOND_ROW: Final = f"obligation:{SECOND}:O1"
SECOND_PRICE: Final = Decimal("8000.00")
RPO: Final = {"entity_codes": [AVM_UK], "book": "ASC606", "period_key": APRIL}


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


def reader_of(world: ReportWorld, entity_id: UUID, name: str) -> Actor:
    """A Revenue Accountant whose role names one entity."""
    return holding(
        world.app, colleague(world.tenant_id, name), "revenue_accountant", entity_ids=[entity_id]
    )


def reference(world: ReportWorld, code: str) -> dict[str, str]:
    """API-S-Ref of an entity, from its row."""
    (row,) = world.place.rows(
        select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name).where(
            legal_entity.c.code == code
        )
    )
    return {"id": str(row["id"]), "code": str(row["code"]), "name": str(row["name"])}


def explained(
    world: ReportWorld, reader: Actor, code: str, given: Mapping[str, Any], row: str, column: str
) -> dict[str, Any]:
    """The cell of a run of the reader's own."""
    run, _ = report_run(world, code, given, actor=reader)
    answer = get(
        world.app, CELL.format(run_id=run["id"]), reader, {"row_key": row, "column_key": column}
    )
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def kinds(body: Mapping[str, Any]) -> list[tuple[str, dict[str, str]]]:
    return sorted(
        ((str(item["object_type"]), dict(item["value"])) for item in body["contributors"]["items"]),
        key=lambda found: (found[0], Decimal(found[1]["amount"])),
    )


def answers(world: ReportWorld, reader: Actor, items: Sequence[Mapping[str, Any]]) -> set[int]:
    """What the contributors' own addresses answer the reader."""
    return {get(world.app, str(item["href"]), reader).status_code for item in items}


@pytest.mark.slow
def test_the_rpo_cell_names_what_the_reader_reaches_and_sums_the_rest_per_entity(
    world: ReportWorld, k04: K04World
) -> None:
    """The RPO of AVM-UK at 30 April 2026, cell ``total`` of the contract: 68,000.00 less the
    April revenue of both entities' books. A reader of every entity is named all twelve
    contributors — O1's eleven schedule lines and O2's obligation version — and no entity is
    summed. A Revenue Accountant of AVM-UK alone gets the same figure: she is named the
    obligation version, whose address answers her, and told AVM-US's part as one sum, the
    schedule lines whose addresses answer her 404. The parts add up to the figure.

    Fail-first: 422 under S15-R-01 for the reader of AVM-UK alone."""
    figure = ALLOCATION - sum((months[0] for months in BOOKS.values()), Decimal(0))
    assert O1_REMAINING + O2_AWAITING == figure
    whole = explained(world, world.maya, "rpo", RPO, CONTRACT_ROW, "total")
    assert whole["value"] == gbp(figure)
    lines = [i for i in whole["contributors"]["items"] if i["object_type"] == "schedule_line"]
    versions = [
        i for i in whole["contributors"]["items"] if i["object_type"] == "obligation_version"
    ]
    assert len(lines) == 11 and len(versions) == 1
    assert len(whole["contributors"]["items"]) == 12
    assert sum((Decimal(i["value"]["amount"]) for i in lines), Decimal(0)) == O1_REMAINING
    assert [i["value"] for i in versions] == [gbp(O2_AWAITING)]

    kit = reader_of(world, k04.uk_entity_id, "kit")
    assert answers(world, kit, lines) == {404}  # AVM-US's rows: outside her scope
    assert answers(world, kit, versions) == {200}  # the contract is her entity's
    own = explained(world, kit, "rpo", RPO, CONTRACT_ROW, "total")
    assert own["value"] == gbp(figure)
    assert whole["other_entities"] == []
    assert kinds(own) == [("obligation_version", gbp(O2_AWAITING))]
    assert [i["id"] for i in own["contributors"]["items"]] == [versions[0]["id"]]
    assert answers(world, kit, own["contributors"]["items"]) == {200}
    assert own["other_entities"] == [
        {"entity": reference(world, AVM_US), "value": gbp(O1_REMAINING)}
    ]


@pytest.mark.slow
def test_the_waterfall_cell_of_a_performing_entitys_reader_is_explained(
    world: ReportWorld, k04: K04World
) -> None:
    """The waterfall of AVM-US, cell of O1 in April 2026: a Revenue Accountant of AVM-US alone —
    for whom ``GET /contracts/{id}`` of the contract, AVM-UK's, answers 404 — is given what a
    reader of every entity is given: AVM-US's revenue of the month, the schedule line and the
    subledger line that posted it, both rows of her entity whose addresses answer her.

    Fail-first: 422 "The run holds no cell obligation:SF-ORD-UK-2001:O1 / period:FY2026-P04."
    (RPT-R-09) for the reader of AVM-US alone."""
    given, column = parameters(AVM_US), f"period:{APRIL}"
    april = BOOKS[(AVM_US, "O1")][0]
    whole = explained(world, world.maya, "revenue_waterfall", given, O1_ROW, column)
    assert whole["value"] == gbp(april)
    assert kinds(whole) == [("schedule_line", gbp(april)), ("subledger_line", gbp(-april))]

    ulla = reader_of(world, k04.us_entity_id, "ulla")
    closed = get(world.app, f"/api/v1/contracts/{k04.contract_id}", ulla)
    assert closed.status_code == 404, closed.text
    own = explained(world, ulla, "revenue_waterfall", given, O1_ROW, column)
    assert own["value"] == whole["value"]
    assert own["contributors"] == whole["contributors"]
    assert own["other_entities"] == whole["other_entities"] == []
    assert answers(world, ulla, own["contributors"]["items"]) == {200}


@pytest.mark.slow
def test_an_obligation_version_of_another_entitys_contract_is_summed_not_named(
    world: ReportWorld, k04: K04World
) -> None:
    """Reach is judged per kind, as the kind's own address judges it. A second contract of AVM-UK,
    ``SF-ORD-UK-2002``, holds one obligation of 8,000.00 that AVM-US performs, half complete on
    30 April: 4,000.00 is AVM-US's revenue of April and 4,000.00 awaits its trigger. The
    waterfall of AVM-US names, in the cell ``awaiting_trigger``, the obligation's version — a
    tenant-wide row whose address answers by the contract's row, AVM-UK's. A reader of every
    entity is named it; a Revenue Accountant of AVM-US alone, whom that address answers 404, is
    told the amount as AVM-UK's part and named nothing. In ``total`` she is named the lines of
    her entity and told the same part.

    Fail-first: 422 "The run holds no cell …" for the reader of AVM-US alone; with every
    obligation version named, she is named one whose address answers her 404."""
    customer = world.contracts[K04].contract["customer_id"]
    second = booked_contract(
        world.place,
        {
            "external_id": SECOND,
            "customer_id": str(customer),
            "contracting_entity_code": AVM_UK,
            "transaction_currency": "GBP",
            "inception_date": "2026-04-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": IMPLEMENTATION_UK,
                    "quantity": "1",
                    "total_price": {"amount": f"{SECOND_PRICE:.2f}", "currency": "GBP"},
                    "performing_entity_code": AVM_US,
                }
            ],
        },
        activate=True,
    )
    half = ProgressRecordedV1(
        obligation_key="O1", cumulative_progress_ratio="0.50", measure="OUTPUT_PERCENT"
    )
    appended(
        world.place,
        UUID(str(second.contract["id"])),
        2,
        [
            EventIn(
                event_type=ContractEventType.PROGRESS_RECORDED,
                effective_date=date(2026, 4, 30),
                payload=half,
            )
        ],
    )
    computed(world.place, UUID(str(second.combination_group["id"])))
    awaiting = SECOND_PRICE / 2
    given = parameters(AVM_US)

    whole = explained(world, world.maya, "revenue_waterfall", given, SECOND_ROW, "awaiting_trigger")
    assert whole["value"] == gbp(awaiting)
    assert kinds(whole) == [("obligation_version", gbp(awaiting))]

    ulla = reader_of(world, k04.us_entity_id, "ulla")
    assert answers(world, ulla, whole["contributors"]["items"]) == {404}  # the contract is AVM-UK's
    part = [{"entity": reference(world, AVM_UK), "value": gbp(awaiting)}]
    own = explained(world, ulla, "revenue_waterfall", given, SECOND_ROW, "awaiting_trigger")
    assert own["value"] == gbp(awaiting)
    assert own["contributors"]["items"] == []
    assert own["other_entities"] == part
    assert whole["other_entities"] == []

    total = explained(world, ulla, "revenue_waterfall", given, SECOND_ROW, "total")
    assert total["other_entities"] == part
    named = total["contributors"]["items"]
    assert {item["object_type"] for item in named} == {"schedule_line", "subledger_line"}
    assert answers(world, ulla, named) == {200}
    recognised = [
        Decimal(i["value"]["amount"]) for i in named if i["object_type"] == "schedule_line"
    ]
    assert sum(recognised, Decimal(0)) == SECOND_PRICE - awaiting
    assert Decimal(total["value"]["amount"]) == SECOND_PRICE
