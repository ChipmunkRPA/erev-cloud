"""DIN-7 legacy setup and SSP template defects, and DIN-8 progress, modification and POB-specific
VC template defects, made explicit with row-level messages (04 table 15.4-A, T-IMP-05 ``message``;
DEVIATIONS §5 #3, #5 to #9, #11 to #14, #18, #20, #21, #27 and "Aggregated finding rows"; D-30a;
legacy 01 §7.3 TC-setup-13 to TC-setup-20, legacy 02 §7.3 TC-delivery-12, 14, 17, legacy 04 §7.3
TC-RM-09, 10, 16, legacy 05 §7.3 TC-pob-vc-10, 15; PRD CPY-06, IMP-03, IMP-05 to IMP-09, IMP-11 to
IMP-14, IMP-18, IMP-20, IMP-21, IMP-27; 03 REQ-DAT-005, REQ-DAT-006, REQ-DAT-007; BUILD_SPEC DIN-7,
DIN-8, BS3-D-12).

World: ``support.legacy_replay.legacy_world`` (J-01.2 to J-01.5). Maya uploads the UAT files with
one defect each, Priya approves, and the jobs run as the worker runs them. ``replayed`` commits the
golden steps a defect needs (DG-PAR-04 order). TC-delivery-13, 15 and 16 are proved by the DIN-5
tests of ``test_progress.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    contract,
    exception_item,
    import_row,
    import_upload,
    obligation_version,
    ssp_book_version,
)
from erev_api.domain.imports import findings, validate
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import golden_streams
from support.db import TestDatabase
from support.factories import (
    IMPORTS_PATH,
    LEGACY_UAT,
    create_import,
    imported,
    upload_import_source,
    workbook_bytes,
)
from support.legacy_replay import (
    SETUP_2023,
    SKU_SSP,
    LegacyWorld,
    committed,
    legacy_world,
    replayed,
    submit,
    workbook_rows,
)
from support.reference import get, slug

SKU = "legacy_sku_ssp"
SETUP = "legacy_contract_setup"
PROGRESS = "legacy_progress_tracking"
MODIFICATION = "legacy_contract_modification"
SSP_SHEET = "SKU Setup"  # WLD-F-01
SETUP_SHEET = "Sheet1"  # WLD-F-02
PROGRESS_SHEET = "Progress Tracking"
MOD_SHEET = "Sheet1"  # the UAT modification workbooks
PROGRESS_HEADERS = (
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
RETRO_MOD = (
    LEGACY_UAT
    / "08-retro-mod-2023-05-15-vc-pob-increase"
    / "Contract Modification Template 05.15.2023 - retrospective vc + POB increases.xlsx"
)
PRICE_CHANGE = (
    LEGACY_UAT
    / "09-pob-specific-vc-2023-05-31"
    / "Contract Modification Template 05.31.2023 - retrospective POB specific VC.xlsx"
)


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


def _ssp_committed(world: LegacyWorld) -> None:
    committed(world, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), SKU)


def _rejected(
    world: LegacyWorld,
    name: str,
    sheet: str,
    headers: list[str] | tuple[str, ...],
    rows: list[list[Any]],
    code: str,
    parameters: Mapping[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Upload and validate a file that validation rejects; its row findings by row and code."""
    import_id, validated = imported(
        world.imports, name, workbook_bytes(sheet, headers, rows), code, parameters
    )
    assert validated["status"] == "INVALID", validated
    items = world.imports.rows(
        select(
            import_row.c.row_number,
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.field,
            exception_item.c.message,
        )
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number, exception_item.c.code)
    )
    return import_id, items


def _located(items: list[dict[str, Any]]) -> list[tuple[int, str, str, str]]:
    return [
        (item["row_number"], item["code"], str(item["severity"]), item["field"]) for item in items
    ]


def _contracts(world: LegacyWorld) -> list[dict[str, Any]]:
    return world.imports.rows(select(contract.c.external_id, contract.c.status))


def _setup_rows(name: str = "Contract 1") -> tuple[list[str], list[list[Any]]]:
    headers, rows = workbook_rows(SETUP_2023)
    return headers, [list(row) for row in rows if name is None or row[0] == name]


def test_tc_setup_13_duplicate_ssp_key_rejected(legacy: LegacyWorld) -> None:
    headers, rows = workbook_rows(SKU_SSP)
    price = headers.index("SKU Unit List Price")
    again = list(rows[0])
    again[price] = 120  # Hardware 1 at list 100 and 120
    _, items = _rejected(
        legacy, "SKU SSP duplicate key.xlsx", SSP_SHEET, headers, [*rows, again], SKU
    )
    assert _located(items) == [
        (2, "SSP_DUPLICATE_KEY", "BLOCKING", "SKU Name"),
        (9, "SSP_DUPLICATE_KEY", "BLOCKING", "SKU Name"),
    ]
    assert items[0]["message"] == (
        "SKU Setup row 2, column SKU Name: SSP key Hardware 1 / Hardware 1 / 2023-01-01 appears "
        "more than once or already exists in an approved version. Rows 2, 9. (SSP_DUPLICATE_KEY)"
    )
    assert legacy.imports.rows(select(ssp_book_version.c.id)) == []

    # A key equal to a row of an approved version is the same finding (DEVIATIONS §5 #8).
    _ssp_committed(legacy)
    _, repeated = _rejected(legacy, "SKU SSP Hardware 1.xlsx", SSP_SHEET, headers, [again], SKU)
    assert _located(repeated) == [(2, "SSP_DUPLICATE_KEY", "BLOCKING", "SKU Name")]
    assert repeated[0]["message"] == (
        "SKU Setup row 2, column SKU Name: SSP key Hardware 1 / Hardware 1 / 2023-01-01 appears "
        "more than once or already exists in an approved version. (SSP_DUPLICATE_KEY)"
    )


def test_tc_setup_14_duplicate_pob_rejected(legacy: LegacyWorld) -> None:
    _ssp_committed(legacy)
    headers, rows = workbook_rows(SETUP_2023)
    import_id, items = _rejected(
        legacy, "Contract Setup duplicate POB.xlsx", SETUP_SHEET, headers, [*rows, rows[0]], SETUP
    )
    assert _located(items) == [
        (2, "SETUP_DUPLICATE_POB", "BLOCKING", "POB Unique ID"),
        (10, "SETUP_DUPLICATE_POB", "BLOCKING", "POB Unique ID"),
    ]
    assert items[1]["message"] == (
        "Sheet1 row 10, column POB Unique ID: Contract Contract 1 has obligation POB #1 more than "
        "once in this file. Rows 2, 10. Key Contract 1 / POB #1 / Hardware 1. (SETUP_DUPLICATE_POB)"
    )
    refused = submit(legacy.imports, import_id)
    assert refused.status_code == 409, refused.text
    assert _contracts(legacy) == []


def test_tc_setup_15_numeric_pob_ids_kept_as_text(legacy: LegacyWorld) -> None:
    _ssp_committed(legacy)
    headers, rows = _setup_rows()
    pob = headers.index("POB Unique ID")
    for number, row in enumerate(rows, start=1):
        row[pob] = number  # numeric cells 1 to 4
    done = committed(
        legacy,
        "Contract Setup numeric POB ids.xlsx",
        workbook_bytes(SETUP_SHEET, headers, rows),
        SETUP,
    )
    assert (done["counts"]["rows"], done["counts"]["errors"]) == (4, 0), done

    stored = legacy.imports.rows(
        select(import_row.c.normalized, import_row.c.business_key)
        .where(import_row.c.import_upload_id == UUID(done["id"]))
        .order_by(import_row.c.row_number)
    )
    assert [item["normalized"]["POB Unique ID"] for item in stored] == ["1", "2", "3", "4"]
    assert stored[0]["business_key"] == "Contract 1 / 1 / Hardware 1"
    (found,) = legacy.imports.rows(
        select(contract.c.id, contract.c.status).where(contract.c.external_id == "Contract 1")
    )
    assert str(found["status"]) == "ACTIVE"
    keys = legacy.imports.rows(
        select(obligation_version.c.obligation_key)
        .where(obligation_version.c.contract_id == found["id"])
        .distinct()
    )
    assert sorted(item["obligation_key"] for item in keys) == ["1", "2", "3", "4"]


def test_tc_setup_16_blank_price_row_error(legacy: LegacyWorld) -> None:
    _ssp_committed(legacy)
    headers, rows = _setup_rows()
    rows[1][headers.index("Original POB Total Selling Price")] = None  # Contract 1 POB #2
    _, items = _rejected(
        legacy, "Contract Setup blank price.xlsx", SETUP_SHEET, headers, rows, SETUP
    )
    assert _located(items) == [
        (3, "REQUIRED_VALUE_BLANK", "BLOCKING", "Original POB Total Selling Price")
    ]
    assert items[0]["message"] == (
        "Sheet1 row 3, column Original POB Total Selling Price: Original POB Total Selling Price "
        "is required. Key Contract 1 / POB #2 / Software 1. (REQUIRED_VALUE_BLANK)"
    )
    assert _contracts(legacy) == []


def test_tc_setup_17_zero_quantity_row_error(legacy: LegacyWorld) -> None:
    _ssp_committed(legacy)
    headers, rows = _setup_rows()
    rows[0][headers.index("Original POB Total Qty")] = 0
    _, items = _rejected(legacy, "Contract Setup zero qty.xlsx", SETUP_SHEET, headers, rows, SETUP)
    assert _located(items) == [(2, "SETUP_QUANTITY_ZERO", "BLOCKING", "Original POB Total Qty")]
    assert items[0]["message"] == (
        "Sheet1 row 2, column Original POB Total Qty: Original POB Total Qty must not be 0. "
        "Key Contract 1 / POB #1 / Hardware 1. (SETUP_QUANTITY_ZERO)"
    )


def test_tc_setup_18_contract_with_only_vc_row(legacy: LegacyWorld) -> None:
    _ssp_committed(legacy)
    headers, rows = workbook_rows(SETUP_2023)
    only_vc = [list(row) for row in rows if row[1] == "VC #1"]
    only_vc[0][0] = "Contract 5"
    contract_1 = [list(row) for row in rows if row[0] == "Contract 1"]
    _, items = _rejected(
        legacy, "Contract Setup only VC.xlsx", SETUP_SHEET, headers, [*contract_1, *only_vc], SETUP
    )
    assert _located(items) == [(6, "TOTAL_SSP_ZERO", "BLOCKING", "Contract Unique Name")]
    assert items[0]["message"] == (
        "Sheet1 row 6, column Contract Unique Name: Contract Contract 5 has a total SSP of 0, so "
        "its transaction price cannot be allocated. Key Contract 5 / VC #1 / Variable "
        "Consideration. (TOTAL_SSP_ZERO)"
    )


def test_tc_setup_19_discount_out_of_range(legacy: LegacyWorld) -> None:
    headers, rows = workbook_rows(SKU_SSP)
    rows = [list(row) for row in rows]
    rows[0][headers.index("Midpoint Discount Percentage")] = 10  # Hardware 1
    _, items = _rejected(legacy, "SKU SSP discount 10.xlsx", SSP_SHEET, headers, rows, SKU)
    assert _located(items) == [
        (2, "SSP_PERCENT_OUT_OF_RANGE", "BLOCKING", "Midpoint Discount Percentage")
    ]
    assert items[0]["message"] == (
        "SKU Setup row 2, column Midpoint Discount Percentage: Midpoint Discount Percentage must "
        "be at least 0 and below 1. Key Hardware 1 / Hardware 1 / 2023-01-01. "
        "(SSP_PERCENT_OUT_OF_RANGE)"
    )
    assert legacy.imports.rows(select(ssp_book_version.c.id)) == []


def test_tc_setup_20_unmapped_product_row_message(legacy: LegacyWorld) -> None:
    _ssp_committed(legacy)
    headers, rows = workbook_rows(SETUP_2023)
    rows = [list(row) for row in rows]
    rows[0][headers.index("SKU Name")] = "Hardware X"
    import_id, items = _rejected(
        legacy, "Contract Setup Hardware X.xlsx", SETUP_SHEET, headers, rows, SETUP
    )
    assert _located(items) == [(2, "SSP_KEY_NOT_FOUND", "BLOCKING", "SKU Name")]
    message = items[0]["message"]
    assert message == (
        "Sheet1 row 2, column SKU Name: No approved SSP for Hardware X / Hardware 1 / 2023-01-01. "
        "Key Contract 1 / POB #1 / Hardware X. (SSP_KEY_NOT_FOUND)"
    )
    # Worksheet, Excel row, column, key and rule id (REQ-DAT-006; legacy 01 FIX-08).
    for part in ("Sheet1", "row 2", "SKU Name", "Hardware X / Hardware 1 / 2023-01-01"):
        assert part in message
    listed = get(legacy.app, f"{IMPORTS_PATH}/{import_id}/rows", legacy.maya).json()["items"]
    (row_2,) = [item for item in listed if item["row_number"] == 2]
    assert row_2["messages"] == [
        {
            "rule_id": "SSP_KEY_NOT_FOUND",
            "severity": "ERROR",
            "field": "SKU Name",
            "message": message,
        }
    ]
    # The whole file is rejected: nothing can be submitted and nothing is written.
    refused = submit(legacy.imports, import_id)
    assert refused.status_code == 409, refused.text
    assert _contracts(legacy) == []


def test_end_before_start_and_negative_range(legacy: LegacyWorld) -> None:
    ssp_headers, ssp_rows = workbook_rows(SKU_SSP)
    ssp_rows = [list(row) for row in ssp_rows]
    ssp_rows[1][ssp_headers.index("SSP Range Method (+-)")] = -0.15  # Software 1
    _, negative = _rejected(
        legacy, "SKU SSP negative range.xlsx", SSP_SHEET, ssp_headers, ssp_rows, SKU
    )
    assert _located(negative) == [
        (3, "SSP_PERCENT_OUT_OF_RANGE", "BLOCKING", "SSP Range Method (+-)")
    ]
    assert negative[0]["message"] == (
        "SKU Setup row 3, column SSP Range Method (+-): SSP Range Method (+-) must be at least 0. "
        "Key Software 1 / Software 1 / 2023-01-01. (SSP_PERCENT_OUT_OF_RANGE)"
    )

    _ssp_committed(legacy)
    headers, rows = _setup_rows()
    rows[0][headers.index("POB Start Date")] = datetime(2023, 12, 31)
    rows[0][headers.index("POB End Date")] = datetime(2023, 1, 1)
    _, inverted = _rejected(
        legacy, "Contract Setup inverted dates.xlsx", SETUP_SHEET, headers, rows, SETUP
    )
    assert _located(inverted) == [(2, "DATE_RANGE_INVERTED", "BLOCKING", "POB End Date")]
    assert inverted[0]["message"] == (
        "Sheet1 row 2, column POB End Date: POB End Date (2023-01-01) is before POB Start Date "
        "(2023-12-31). Key Contract 1 / POB #1 / Hardware 1. (DATE_RANGE_INVERTED)"
    )


# --- DIN-8: progress, modification and POB-specific VC templates ---------------------------------


def _progress_row(name: Any, pob: Any, sku: Any, delivery: Any, billing: Any) -> list[Any]:
    return [name, pob, sku, delivery, billing, 0, "Delivery 1", "Delivery 2", "Delivery 3"]


def _file_items(world: LegacyWorld, import_id: str) -> list[dict[str, Any]]:
    """The file-level exception items of an import (``import_row_id`` null)."""
    return world.imports.rows(
        select(
            exception_item.c.source,
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.status,
            exception_item.c.message,
            exception_item.c.import_row_id,
        ).where(exception_item.c.import_upload_id == UUID(import_id))
    )


def _header_only(
    world: LegacyWorld,
    name: str,
    sheet: str,
    headers: list[str] | tuple[str, ...],
    code: str,
    parameters: Mapping[str, Any],
) -> None:
    """A header-only workbook is INVALID with one file-level IMPORT_NO_DATA_ROWS item (DEV-017)."""
    import_id, validated = imported(
        world.imports, name, workbook_bytes(sheet, headers, []), code, parameters
    )
    assert validated["status"] == "INVALID", validated
    assert validated["finding_counts"] == [
        {"code": "IMPORT_NO_DATA_ROWS", "severity": "ERROR", "rows": 0}
    ]
    assert [
        (item["code"], str(item["severity"]), item["message"], item["import_row_id"])
        for item in _file_items(world, import_id)
    ] == [("IMPORT_NO_DATA_ROWS", "BLOCKING", findings.NO_DATA_ROWS, None)]
    assert (
        world.imports.rows(
            select(import_row.c.id).where(import_row.c.import_upload_id == UUID(import_id))
        )
        == []
    )


def _mod_row(pob: str, billing: Any, quantity: Any, source: Any) -> list[Any]:
    """A Contract 2 row with the attributes of the UAT modification workbook ``source``."""
    headers, rows = workbook_rows(source)
    row = list(rows[0])
    row[headers.index("POB Unique ID")] = pob
    row[headers.index("Mod Billing")] = billing
    row[headers.index("Mod Qty")] = quantity
    return row


def test_tc_delivery_12_unknown_contract_names_excel_row(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    rows = [
        _progress_row("Contract 1", "POB #1", "Hardware 1", 1, 0),
        _progress_row("Contract 9", "POB #1", "Hardware 1", 1, 0),  # data row 2 (E06)
    ]
    import_id, items = _rejected(
        legacy,
        "Progress unmatched 1.31.2023.xlsx",
        PROGRESS_SHEET,
        PROGRESS_HEADERS,
        rows,
        PROGRESS,
        {"effective_date": "2023-01-31"},
    )
    assert _located(items) == [(3, "CONTRACT_NOT_FOUND", "BLOCKING", "Contract Unique Name")]
    assert items[0]["message"] == (
        "Progress Tracking row 3, column Contract Unique Name: Contract Contract 9 does not exist "
        "in this workspace. Key Contract 9 / POB #1 / Hardware 1. (CONTRACT_NOT_FOUND)"
    )
    # Excel row 3 and the key, never the merged index ("9"; DEV-019, REQ-DAT-006).
    listed = get(legacy.app, f"{IMPORTS_PATH}/{import_id}/rows", legacy.maya).json()["items"]
    (row_3,) = [item for item in listed if item["row_number"] == 3]
    assert [message["rule_id"] for message in row_3["messages"]] == ["CONTRACT_NOT_FOUND"]
    # No orphan contract is created (DEV-018), and the file cannot be submitted.
    assert "Contract 9" not in {item["external_id"] for item in _contracts(legacy)}
    refused = submit(legacy.imports, import_id)
    assert refused.status_code == 409, refused.text


def test_tc_delivery_14_numeric_pob_id_explicit_error(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    rows = [_progress_row("Contract 1", 1, "Hardware 1", 1, 50)]  # a numeric POB Unique ID (E02)
    import_id, items = _rejected(
        legacy,
        "Progress numeric POB 1.31.2023.xlsx",
        PROGRESS_SHEET,
        PROGRESS_HEADERS,
        rows,
        PROGRESS,
        {"effective_date": "2023-01-31"},
    )
    assert _located(items) == [(2, "POB_NOT_FOUND", "BLOCKING", "POB Unique ID")]
    assert items[0]["message"] == (
        "Progress Tracking row 2, column POB Unique ID: Obligation 1 does not exist on contract "
        "Contract 1. Key Contract 1 / 1 / Hardware 1. (POB_NOT_FOUND)"
    )
    (stored,) = legacy.imports.rows(
        select(import_row.c.raw, import_row.c.business_key, import_row.c.status).where(
            import_row.c.import_upload_id == UUID(import_id)
        )
    )
    assert (stored["raw"]["POB Unique ID"], stored["business_key"], str(stored["status"])) == (
        "1",
        "Contract 1 / 1 / Hardware 1",
        "ERROR",
    )


def test_tc_delivery_17_header_only_and_duplicate_file(legacy: LegacyWorld) -> None:
    # E05: a header-only progress file is rejected, not a success popup with 0 rows.
    _header_only(
        legacy,
        "Progress headers only.xlsx",
        PROGRESS_SHEET,
        PROGRESS_HEADERS,
        PROGRESS,
        {"effective_date": "2023-01-31"},
    )

    # E08: the committed 1.31 file uploaded again is refused before validation (DEV-011).
    done = replayed(legacy, "04")
    (step,) = [item for item in golden_streams.steps("04") if item.number == "04"]
    assert step.date_input is not None
    uploads = legacy.imports.scalar(select(func.count()).select_from(import_upload))
    file_id = upload_import_source(legacy.imports, step.workbook.name, step.workbook.read_bytes())
    refused = create_import(
        legacy.imports, file_id, PROGRESS, {"effective_date": step.date_input.isoformat()}
    )
    assert (refused.status_code, slug(refused)) == (409, "duplicate-import"), refused.text
    expected = findings.duplicate_file(
        done["04"]["import_no"], date.fromisoformat(done["04"]["created_at"][:10])
    )
    body = refused.json()
    assert body["detail"] == expected
    assert [(error["rule_id"], error["message"]) for error in body["errors"]] == [
        ("IMPORT_FILE_DUPLICATE", expected)
    ]
    assert legacy.imports.scalar(select(func.count()).select_from(import_upload)) == uploads


def test_tc_rm_09_header_only_modification_rejected(legacy: LegacyWorld) -> None:
    headers, _ = workbook_rows(RETRO_MOD)
    _header_only(
        legacy,
        "Retrospective mod headers only.xlsx",
        MOD_SHEET,
        headers,
        MODIFICATION,
        {"effective_date": "2023-04-30", "mode": "retrospective"},
    )


def test_tc_rm_10_duplicate_modification_rows_rejected(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    headers, _ = workbook_rows(RETRO_MOD)
    twice = [_mod_row("POB #1", 200, 1, RETRO_MOD), _mod_row("POB #1", 200, 1, RETRO_MOD)]
    import_id, items = _rejected(
        legacy,
        "Retrospective mod duplicate rows.xlsx",
        MOD_SHEET,
        headers,
        twice,
        MODIFICATION,
        {"effective_date": "2023-04-30", "mode": "retrospective"},
    )
    assert _located(items) == [
        (2, "MOD_DUPLICATE_KEY", "BLOCKING", "POB Unique ID"),
        (3, "MOD_DUPLICATE_KEY", "BLOCKING", "POB Unique ID"),
    ]
    assert items[1]["message"] == (
        "Sheet1 row 3, column POB Unique ID: Contract 2, obligation POB #1 (Hardware 1) appears "
        "more than once in this modification file. Rows 2, 3. Key Contract 2 / POB #1 / Hardware "
        "1. (MOD_DUPLICATE_KEY)"
    )
    refused = submit(legacy.imports, import_id)
    assert refused.status_code == 409, refused.text


def test_tc_rm_16_duplicate_ssp_key_row_rejected(legacy: LegacyWorld) -> None:
    """[J] The UAT 05.15 retrospective file prices Contract 2 POB #1 through the approved key
    Hardware 1 / Hardware 1 / 2023-01-01. A second row for that key is refused at the SSP upload, so
    the modification's key resolves to one approved row whatever the contract state (S18 fan-out;
    DEV-015)."""
    replayed(legacy, "01")
    headers, rows = workbook_rows(SKU_SSP)
    price = headers.index("SKU Unit List Price")
    again = list(rows[0])
    again[price] = 120  # Hardware 1 at list 100 and 120
    _, items = _rejected(legacy, "SKU SSP 05.15.2023.xlsx", SSP_SHEET, headers, [again], SKU)
    assert _located(items) == [(2, "SSP_DUPLICATE_KEY", "BLOCKING", "SKU Name")]
    assert items[0]["message"] == (
        "SKU Setup row 2, column SKU Name: SSP key Hardware 1 / Hardware 1 / 2023-01-01 appears "
        "more than once or already exists in an approved version. (SSP_DUPLICATE_KEY)"
    )
    assert len(legacy.imports.rows(select(ssp_book_version.c.id))) == 1


def test_tc_pob_vc_10_identical_price_rows_rejected(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    headers, _ = workbook_rows(PRICE_CHANGE)
    twice = [_mod_row("POB #1", -100, 0, PRICE_CHANGE), _mod_row("POB #1", -100, 0, PRICE_CHANGE)]
    _, items = _rejected(
        legacy,
        "POB specific VC identical rows.xlsx",
        MOD_SHEET,
        headers,
        twice,
        MODIFICATION,
        {"effective_date": "2023-05-31", "mode": "pob_price_change"},
    )
    assert _located(items) == [
        (2, "MOD_DUPLICATE_KEY", "BLOCKING", "POB Unique ID"),
        (3, "MOD_DUPLICATE_KEY", "BLOCKING", "POB Unique ID"),
    ]
    assert items[0]["message"] == (
        "Sheet1 row 2, column POB Unique ID: Contract 2, obligation POB #1 (Hardware 1) appears "
        "more than once in this modification file. Rows 2, 3. Key Contract 2 / POB #1 / Hardware "
        "1. (MOD_DUPLICATE_KEY)"
    )


def test_tc_pob_vc_15_header_only_rejected(legacy: LegacyWorld) -> None:
    headers, _ = workbook_rows(PRICE_CHANGE)
    _header_only(
        legacy,
        "POB specific VC headers only.xlsx",
        MOD_SHEET,
        headers,
        MODIFICATION,
        {"effective_date": "2023-05-31", "mode": "pob_price_change"},
    )


def test_swallowed_exception_becomes_finding(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fails(*_: Any, **__: Any) -> Any:
        raise TypeError("a cell the rules did not expect")  # legacy `except TypeError: pass`

    monkeypatch.setattr(validate, "cross_checked", fails)
    import_id, validated = imported(
        legacy.imports, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), SKU
    )
    assert validated["status"] == "INVALID", validated
    (item,) = _file_items(legacy, import_id)
    assert (item["source"], item["code"], str(item["severity"]), item["status"]) == (
        "IMPORT",
        "IMPORT_PROCESSING_FAILED",
        "BLOCKING",
        "OPEN",
    )
    assert item["import_row_id"] is None
    assert item["message"].startswith(
        "The file could not be processed and nothing was committed. Reference job-"
    )
    assert validated["finding_counts"] == [
        {"code": "IMPORT_PROCESSING_FAILED", "severity": "ERROR", "rows": 0}
    ]
    # Nothing is committed: no rows, no SSP version, and the upload cannot be submitted.
    assert (
        legacy.imports.rows(
            select(import_row.c.id).where(import_row.c.import_upload_id == UUID(import_id))
        )
        == []
    )
    assert legacy.imports.rows(select(ssp_book_version.c.id)) == []
    refused = submit(legacy.imports, import_id)
    assert refused.status_code == 409, refused.text
