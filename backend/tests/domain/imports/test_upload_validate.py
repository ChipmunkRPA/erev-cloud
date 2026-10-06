"""DIN-1 upload and validation (04 T-IMP-01 to T-IMP-03, tables 15.4-A and 15.4-B, §16.6; 05
IPL-01 to IPL-06, UPL-06, UPL-07; PRD IMP copy; 03 REQ-DAT-007, REQ-DAT-016; BUILD_SPEC DIN-1).

World: ``support.factories.import_world``, a Revenue Accountant (``import.upload``) of a provisioned
tenant. Files are uploaded through ``POST /files``, imports are created through ``POST /imports``,
and the ``IMPORT_VALIDATE`` job runs as the worker runs it.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.release import current_release
from erev_api.db.tables import exception_item, import_row, job
from erev_api.domain.imports import csv_v2, legacy_templates, parse, validate
from erev_api.files.store import LocalFileStore
from erev_api.jobs.registry import RELEASE_PARAM, handler_params
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    IMPORT_TEMPLATES_PATH,
    IMPORTS_PATH,
    SKU_SSP_FIXTURE,
    ImportWorld,
    create_import,
    import_world,
    imported,
    run_import_job,
    upload_import_source,
    workbook_bytes,
)
from support.reference import get

SKU_SSP_HEADERS = (
    "SKU Unique ID",
    "SKU Name",
    "Distinct or Nondistinct",
    "SKU Unit List Price",
    "ASC 606 Stratification",
    "Midpoint Discount Percentage",
    "SSP Range Method (+-)",
    "SSP Version",
    "Revenue Account",
)
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
LEGACY_CODES = (
    "legacy_sku_ssp",
    "legacy_contract_setup",
    "legacy_progress_tracking",
    "legacy_contract_modification",
)
CSV_V2_CODES = (
    "customers",
    "products",
    "bundles",
    "ssp_values",
    "contracts",
    "invoices",
    "progress_events",
    "usage",
    "modifications",
    "estimates",
    "fx_rates",
    "cost_events",
    "pre_standard_revenue",
    "gl_accounts",
    "account_mapping",
)
EFFECTIVE_DATE = {"name": "effective_date", "type": "date", "allowed_values": None}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ImportWorld:
    return import_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _rows(world: ImportWorld, import_id: str) -> list[dict[str, Any]]:
    response = get(world.app, f"{IMPORTS_PATH}/{import_id}/rows", world.actor, {"limit": 100})
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def test_import_templates_seeded(world: ImportWorld) -> None:
    response = get(world.app, IMPORT_TEMPLATES_PATH, world.actor)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 19
    assert [item["code"] for item in items] == [*LEGACY_CODES, *CSV_V2_CODES]
    by_code = {item["code"]: item for item in items}
    assert [len(by_code[code]["headers"]) for code in LEGACY_CODES] == [9, 16, 9, 15]
    assert [header["name"] for header in by_code["legacy_sku_ssp"]["headers"]] == list(
        SKU_SSP_HEADERS
    )
    assert [header["name"] for header in by_code["legacy_progress_tracking"]["headers"]] == list(
        PROGRESS_HEADERS
    )
    assert by_code["legacy_sku_ssp"]["headers"][3] == {
        "name": "SKU Unit List Price",
        "type": "amount",
        "required": True,
        "rule_ids": ["REQUIRED_VALUE_BLANK", "VALUE_NOT_NUMERIC"],
    }
    assert by_code["legacy_sku_ssp"]["required_parameters"] == []
    assert by_code["legacy_contract_setup"]["required_parameters"] == []
    assert by_code["legacy_progress_tracking"]["required_parameters"] == [EFFECTIVE_DATE]
    assert by_code["legacy_contract_modification"]["required_parameters"] == [
        EFFECTIVE_DATE,
        {
            "name": "mode",
            "type": "text",
            "allowed_values": ["prospective", "retrospective", "pob_price_change"],
        },
    ]
    for code in LEGACY_CODES:
        item = by_code[code]
        assert (item["family"], item["file_format"], item["version"]) == ("LEGACY_V1", "XLSX", 1)
        assert item["download_href"] == f"/api/v1/import-templates/{code}/download"
        seeded = [
            (header["name"], header["type"], header["required"], tuple(header["rule_ids"]))
            for header in item["headers"]
        ]
        assert seeded == list(legacy_templates.LEGACY_HEADERS[code])
    for code in CSV_V2_CODES:
        item = by_code[code]
        assert (item["family"], item["file_format"]) == ("CSV_V2", "CSV")
        # BUILD_SPEC DIN-9: a template with an emitter lists its flattened columns (NC-19); the
        # templates without one (L5-1-Q-23) keep the seeded empty headers.
        assert (item["headers"] == []) == (code not in csv_v2.TEMPLATES), code


def test_sku_ssp_upload_validates(world: ImportWorld) -> None:
    file_id = upload_import_source(world, "SKU SSP Template.xlsx", SKU_SSP_FIXTURE.read_bytes())
    created = create_import(world, file_id, "legacy_sku_ssp")
    assert created.status_code == 202, created.text
    job_body = created.json()
    job_id = UUID(job_body["id"])
    assert (job_body["kind"], job_body["state"]) == ("IMPORT_VALIDATE", "QUEUED")
    assert created.headers["Location"] == f"/api/v1/jobs/{job_id}"
    import_id = created.headers["X-Erev-Import-Id"]
    (queued,) = world.rows(
        select(job.c.queue, job.c.subject_type, job.c.subject_id, job.c.params).where(
            job.c.id == job_id
        )
    )
    # 05 REL-05 / DG-KRN-JOB-13: every enqueue records the enqueuing process's stamped release as
    # the reserved `params.engine_release_id`; the handler sees the caller's params only
    # (`handler_params`). The import world is a stamped process (`stamp_test_release`).
    stamped = current_release()
    assert stamped is not None
    assert {key: value for key, value in queued.items() if key != "params"} == {
        "queue": "imports",
        "subject_type": "import_upload",
        "subject_id": UUID(import_id),
    }
    assert handler_params(queued["params"]) == {"import_upload_id": import_id}
    assert queued["params"][RELEASE_PARAM] == str(stamped.id)
    uploaded = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor).json()
    assert uploaded["status"] == "UPLOADED"
    assert uploaded["template"] == {"code": "legacy_sku_ssp", "version": 1, "name": "SKU SSP"}
    assert uploaded["file"]["original_filename"] == "SKU SSP Template.xlsx"
    assert uploaded["counts"]["rows"] is None

    run_import_job(world, job_id)

    shown = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor).json()
    assert shown["status"] == "VALIDATED"
    assert shown["counts"] == {
        "rows": 7,
        "valid": 7,
        "warnings": 0,
        "errors": 0,
        "aggregated": 0,
        "blank": 0,
    }
    assert shown["finding_counts"] == []
    assert shown["header_match"] == []
    source = shown["control_totals"]["source"]
    assert (source["rows"], source["amount_sums"]) == (7, {"SKU Unit List Price": "603"})
    rows = _rows(world, import_id)
    assert [row["row_number"] for row in rows] == [2, 3, 4, 5, 6, 7, 8]
    assert {row["status"] for row in rows} == {"VALID"}
    assert {row["sheet_name"] for row in rows} == {"SKU Setup"}
    first = rows[0]
    assert first["business_key"] == "Hardware 1 / Hardware 1 / 2023-01-01"
    assert first["raw"] == {
        "SKU Unique ID": "1",
        "SKU Name": "Hardware 1",
        "Distinct or Nondistinct": "Distinct",
        "SKU Unit List Price": "100",
        "ASC 606 Stratification": "Hardware 1",
        "Midpoint Discount Percentage": "0.1",
        "SSP Range Method (+-)": "0.15",
        "SSP Version": "2023-01-01",
        "Revenue Account": "5001",
    }
    assert first["normalized"] == first["raw"]
    assert (first["messages"], first["lineage"]) == ([], [])
    assert rows[6]["normalized"]["SKU Unit List Price"] == "0"
    (finished,) = world.rows(select(job.c.state, job.c.result).where(job.c.id == job_id))
    assert finished["state"] == "SUCCEEDED"
    assert finished["result"] == {
        "href": f"/api/v1/imports/{import_id}",
        "counts": {"rows": 7, "valid": 7, "warnings": 0, "errors": 0},
    }


def test_cell_coercion(world: ImportWorld) -> None:
    sheet = parse.read_csv(io.BytesIO("﻿Amount,Identifier\r\n0.1,00042\r\n".encode()))
    assert sheet.headers == ("Amount", "Identifier")
    assert sheet.rows == ((2, ("0.1", "00042")),)
    amount, identifier = sheet.rows[0][1]
    assert parse.cell_text(amount) == "0.1"
    assert validate.coerce("amount", amount) == (Decimal("0.1"), None)
    assert validate.coerce("identifier", identifier) == ("00042", None)
    assert (parse.cell_text(0.1), parse.cell_text(100.0), parse.cell_text(1e-05)) == (
        "0.1",
        "100",
        "0.00001",
    )
    assert validate.coerce("date", 45292) == (date(2024, 1, 1), None)
    assert validate.coerce("date", "2023-01-31") == (date(2023, 1, 31), None)
    assert validate.coerce("date", "31/01/2023") == (None, "DATE_INVALID")
    assert validate.coerce("quantity", "ten") == (None, "VALUE_NOT_NUMERIC")

    content = workbook_bytes(
        "Progress Tracking",
        PROGRESS_HEADERS,
        [("Contract 1", "POB #1", "Hardware 1", 5, "=D2*100", 0, "Delivered", "Inv 1", "A")],
    )
    import_id, shown = imported(
        world,
        "progress.xlsx",
        content,
        "legacy_progress_tracking",
        {"effective_date": "2023-01-31"},
    )
    assert shown["status"] == "INVALID"
    assert shown["finding_counts"] == [
        {"code": "FORMULA_NO_CACHED_VALUE", "severity": "ERROR", "rows": 1}
    ]
    (row,) = _rows(world, import_id)
    assert (row["row_number"], row["status"], row["normalized"]) == (2, "ERROR", None)
    assert row["business_key"] == "Contract 1 / POB #1 / Hardware 1"
    assert row["messages"] == [
        {
            "rule_id": "FORMULA_NO_CACHED_VALUE",
            "severity": "ERROR",
            "field": "Current Billing",
            "message": (
                "Sheet Progress Tracking, row 2, column Current Billing: the cell holds a formula "
                "without a saved value. Open the file in Excel, save it and upload it again."
            ),
        }
    ]


def test_header_only_file_invalid(world: ImportWorld) -> None:
    content = workbook_bytes("SKU Setup", SKU_SSP_HEADERS, [])
    import_id, shown = imported(world, "headers-only.xlsx", content, "legacy_sku_ssp")
    assert shown["status"] == "INVALID"
    assert shown["counts"] == {
        "rows": 0,
        "valid": 0,
        "warnings": 0,
        "errors": 0,
        "aggregated": 0,
        "blank": 0,
    }
    assert shown["finding_counts"] == [
        {"code": "IMPORT_NO_DATA_ROWS", "severity": "ERROR", "rows": 0}
    ]
    items = world.rows(
        select(
            exception_item.c.source,
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.status,
            exception_item.c.message,
            exception_item.c.import_row_id,
        ).where(exception_item.c.import_upload_id == UUID(import_id))
    )
    assert items == [
        {
            "source": "IMPORT",
            "code": "IMPORT_NO_DATA_ROWS",
            "severity": "BLOCKING",
            "status": "OPEN",
            "message": "The file has headers but no data rows.",
            "import_row_id": None,
        }
    ]
    assert _rows(world, import_id) == []


def test_row_limit(world: ImportWorld) -> None:
    rows = [
        (number, f"SKU {number}", "Distinct", 100, "Hardware 1", 0.1, 0.15, "2023-01-01", 5001)
        for number in range(1, 50_002)
    ]
    content = workbook_bytes("SKU Setup", SKU_SSP_HEADERS, rows)
    import_id, shown = imported(world, "too-many-rows.xlsx", content, "legacy_sku_ssp")
    assert shown["status"] == "INVALID"
    assert shown["finding_counts"] == [
        {"code": "IMPORT_ROW_LIMIT_EXCEEDED", "severity": "ERROR", "rows": 0}
    ]
    assert shown["counts"]["rows"] == 50_001
    messages = world.rows(
        select(exception_item.c.message).where(exception_item.c.import_upload_id == UUID(import_id))
    )
    assert messages == [
        {
            "message": (
                "Sheet SKU Setup has 50,001 data rows. "
                "Split the file so that each sheet has at most 50,000 rows."
            )
        }
    ]
    written = select(func.count()).where(import_row.c.import_upload_id == UUID(import_id))
    assert world.scalar(written) == 0
