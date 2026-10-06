"""Legacy v1 progress tracking bounds after contract modifications (ENGINE_SPEC Table 0.8-A
``PROGRESS_OVER_DELIVERY``, S06-R-08, §6.5 Plan_i; 04 table 15.4-A #22, #23; DEVIATIONS §5 #22,
#23, DEV-018, DEV-020; legacy 07 §7 GT-16; BUILD_SPEC DIN-5, GPA-5).

The remaining quantity and billing plan that an upload is checked against are those of the terms
in force: the booking plus every ``CONTRACT_AMENDED`` line (``quantity_delta``,
``consideration_delta``), and an added obligation from its ``ADD`` line. The golden full delivery of
2023-10-31 (step 14) delivers and bills exactly what steps 08 to 13 leave, so it validates without a
finding. World: ``support.legacy_replay.legacy_world`` and ``replayed`` (DG-PAR-04 order); Maya
uploads and Priya approves.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import exception_item, import_row
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import golden_streams
from support.db import TestDatabase
from support.factories import imported, workbook_bytes
from support.legacy_replay import LegacyWorld, legacy_world, replayed

PROGRESS = "legacy_progress_tracking"
HEADERS = (
    "Contract Unique Name",
    "POB Unique ID",
    "SKU Name",
    "Current Delivery",
    "Current Billing",
    "Current Pre-ASC606 Revenue (Net Design Only)",
    "Memo 1",
    "Memo 2",
    "Memo 3",
)
MEMOS = ("Delivery 1", "Delivery 2", "Delivery 3")
ON = {"effective_date": "2023-10-31"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


def _findings(world: LegacyWorld, import_id: str) -> list[tuple[int, str, str]]:
    items = world.imports.rows(
        select(exception_item.c.code, exception_item.c.message, import_row.c.row_number)
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number, exception_item.c.code)
    )
    return [(item["row_number"], str(item["code"]), str(item["message"])) for item in items]


def _row(contract_name: str, pob: str, sku: str, delivery: Any, billing: Any) -> list[Any]:
    return [contract_name, pob, sku, delivery, billing, 0, *MEMOS]


def _upload(world: LegacyWorld, name: str, rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
    import_id, validated = imported(
        world.imports, name, workbook_bytes("Progress Tracking", HEADERS, rows), PROGRESS, ON
    )
    return {**validated, "findings": _findings(world, import_id)}


def test_s06_r08_bounds_follow_the_amended_terms_after_step_13(legacy: LegacyWorld) -> None:
    replayed(legacy, "13")
    # Booking → terms in force after steps 08 to 13 (golden latest_contracts.csv of step 13):
    # - Contract 1 POB #1: 5 units, then Mod Qty −5 and Mod Billing −500.00 (step 10): remaining 0;
    # - Contract 3 POB #1: 500.00, then +500.00 (step 11) and −200.00 (step 12): plan 800.00;
    # - Contract 3 POB #5: added by step 13 with Mod Qty 5 and Mod Billing 1,000.00;
    # - Contract 4 POB #3: 1 unit and 150.00, then +2 / +300.00 and −0.5 / −50.00: 2.5 and 400.00.
    over = _upload(
        legacy,
        "over amended 10.31.2023.xlsx",
        [
            _row("Contract 1", "POB #1", "Hardware 1", 1, 0),
            _row("Contract 3", "POB #1", "Hardware 1", 0, 801),
            _row("Contract 3", "POB #5", "Consulting 1", 6, 0),
            _row("Contract 4", "POB #3", "Consulting 1", 2.5, 400),
        ],
    )
    assert over["status"] == "INVALID", over
    # Stored messages take the PRD CPY-06 legacy form (DIN-7, D-87 L6-1-Q-1): location, IMP copy,
    # the business key, then the code.
    assert over["findings"] == [
        (
            2,
            "PROGRESS_OVER_DELIVERY",
            "Progress Tracking row 2, column Current Delivery: Contract 1, obligation POB #1 "
            "(Hardware 1): requested 1, remaining 0. Key Contract 1 / POB #1 / Hardware 1. "
            "(PROGRESS_OVER_DELIVERY)",
        ),
        (
            3,
            "PROGRESS_OVER_BILLING",
            "Progress Tracking row 3, column Current Billing: Contract 3, obligation POB #1 "
            "(Hardware 1): billing 801.00 exceeds the remaining billing plan 800.00. "
            "Key Contract 3 / POB #1 / Hardware 1. (PROGRESS_OVER_BILLING)",
        ),
        (
            4,
            "PROGRESS_OVER_DELIVERY",
            "Progress Tracking row 4, column Current Delivery: Contract 3, obligation POB #5 "
            "(Consulting 1): requested 6, remaining 5. Key Contract 3 / POB #5 / Consulting 1. "
            "(PROGRESS_OVER_DELIVERY)",
        ),
    ]
    (step,) = [item for item in golden_streams.steps("14") if item.number == "14"]
    import_id, full = imported(
        legacy.imports, step.workbook.name, step.workbook.read_bytes(), PROGRESS, ON
    )
    # GT-16: every remaining quantity and billing plan is delivered and billed, so no finding.
    assert (full["status"], full["counts"]["errors"]) == ("VALIDATED", 0), full
    assert _findings(legacy, import_id) == []
