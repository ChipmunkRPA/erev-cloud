"""RPT-01 revenue waterfall rows are grouped by identity — DB witness of supervisor ruling R-40 (a)
(2026-09-30; SCREENS_B RPT-01 rev 1.26; D-98 104; ENGINE_SPEC CV-21; found by the key audit of
ruling R-16). DB-bound.

The world is WLD-K-01 plus, for the K-01 customer, two contracts of one 2026 PLATFORM line of
120,000.00 USD each — contract ``A:B`` with obligation ``C`` and contract ``A`` with obligation
``B:C`` — whose raw-joined row key was the same text ``obligation:A:B:C``. September revenue of
each is 120,000.00 × 30 ÷ 365 = 9,863.01 (PRD J-05.3); K-01's O1 is 9,764.38 (WLD-X-02).
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.factories import booked_contract, computed
from support.reference import get, slug
from support.worlds import (
    AVM_US,
    K01,
    SEPTEMBER_2026,
    ReportWorld,
    journal_run,
    k01_body,
    k01_pellworth,
    report_run,
)

CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
COLUMN: Final = f"period:{SEPTEMBER_2026}"
PAIR: Final = (("A:B", "C"), ("A", "B:C"))  # an unescaped ``:`` join makes both ``A:B:C``
PAIR_REVENUE: Final = "9863.01"
K01_REVENUE: Final = "9764.38"
TOTAL: Final = "29490.40"  # 2 × 9,863.01 + 9,764.38


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    built = k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    customer = UUID(str(built.contracts[K01].contract["customer_id"]))
    for external_id, obligation_key in PAIR:
        body = k01_body(customer)
        body["external_id"] = external_id
        body["lines"] = [{**body["lines"][0], "obligation_key": obligation_key}]
        found = booked_contract(built.place, body, activate=True)
        computed(built.place, UUID(str(found.combination_group["id"])))
    return built


def _keyed(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows)  # no two rows share a key
    return found


def test_r40_obligations_whose_joined_identifiers_coincide_are_two_rows(
    world: ReportWorld,
) -> None:
    """Two contracts, two rows of 9,863.01, each under its own contract and obligation, and the
    report still ties to the revenue journal. Fail-first: ONE row ``obligation:A:B:C`` — labelled
    contract ``A``, obligation ``B:C`` — of 19,726.02, the contract ``A:B`` not shown."""
    journal_run(world)  # September: the tie-out's revenue journal
    run, rows = report_run(world, "revenue_waterfall", {**SEPTEMBER, "row_dimension": "OBLIGATION"})
    assert run["status"] == "SUCCEEDED"
    assert {
        key: (row["contract_external_id"], row["obligation_key"], row[COLUMN])
        for key, row in _keyed(rows).items()
    } == {
        "obligation:A%3AB:C": ("A:B", "C", usd(PAIR_REVENUE)),
        "obligation:A:B%3AC": ("A", "B:C", usd(PAIR_REVENUE)),
        f"obligation:{K01}:O1": (K01, "O1", usd(K01_REVENUE)),
        "TOTAL:USD": (None, None, usd(TOTAL)),
    }
    assert run["control_totals"]["recognized_total"] == {"USD": TOTAL}
    assert [(item["code"], item["result"]) for item in run["tie_out_results"]] == [
        ("TO_WATERFALL_EQ_JE_REVENUE", "PASS")
    ]
    # the cell drill resolves each row by its own key; the former merged key names no row
    for row_key in ("obligation:A%3AB:C", "obligation:A:B%3AC"):
        explained = get(
            world.app,
            CELL.format(run_id=run["id"]),
            world.maya,
            {"row_key": row_key, "column_key": COLUMN},
        )
        assert explained.status_code == 200, explained.text
        body = explained.json()
        assert body["value"] == usd(PAIR_REVENUE), row_key
        assert [
            item["value"]
            for item in body["contributors"]["items"]
            if item["object_type"] == "schedule_line"
        ] == [usd(PAIR_REVENUE)], row_key
    merged = get(
        world.app,
        CELL.format(run_id=run["id"]),
        world.maya,
        {"row_key": "obligation:A:B:C", "column_key": COLUMN},
    )
    assert (merged.status_code, slug(merged)) == (422, "validation-failed"), merged.text

    by_contract = _keyed(report_run(world, "revenue_waterfall", SEPTEMBER)[1])
    assert {key: row[COLUMN] for key, row in by_contract.items()} == {
        "contract:A%3AB": usd(PAIR_REVENUE),
        "contract:A": usd(PAIR_REVENUE),
        f"contract:{K01}": usd(K01_REVENUE),  # an identifier without a delimiter keeps its key
        "TOTAL:USD": usd(TOTAL),
    }
