"""SSP declarations on import (04 rev 1.19 T-IMP-01 paragraph and table 15.4-A `SSP_*` declaration
codes; D-97 (3), (3a); readiness SSP-IMPORT-DECLARATION; lane F-DIN). The CSV v2 ``ssp_values``
template carries ``lines.value_basis`` and ``lines.quantity_unit`` with exactly the API-S-SspEntry
refusals, raised at validation as row-located ERROR findings (upload INVALID, nothing written), and
saved entries round-trip their declarations. World: ``j03_world`` — ``AVM-PLAT-100`` (TPL-SUB-DAILY,
a ``series`` default POB template) and ``AVM-IMPL-PLUS`` (TPL-SVC-HOURS, distinct); book US-LIST.

Fail-first (recorded in ``docs/reviews/loop/prod/F-DIN-prep.md``): before the cross rule, an
``AVM-PLAT-100`` row without ``lines.value_basis`` was accepted and committed with the default
AMOUNT.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    exception_item,
    import_row,
    import_upload,
    ssp_book_version,
    ssp_entry,
)
from erev_api.domain.imports.csv_v2.framework import flatten
from erev_api.domain.imports.csv_v2.ssp_values import SspValuesIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    IMPLEMENTATION_PLUS,
    PLATFORM_100,
    ImportWorld,
    J03World,
    Workspace,
    imported,
    j03_world,
    run_import_job,
)
from support.legacy_replay import diffed, job_of, submit
from support.principals import colleague
from support.reference import approve, assign, get, holding, post

HEADERS = [column.name for column in flatten(SspValuesIn)]


def csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def importer(place: Workspace) -> ImportWorld:
    """The workspace's author as the import world (as ``test_templates.importer``)."""
    return ImportWorld(
        app=place.app,
        actor=place.author,
        runtime=JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files),
        clock=place.clock,
    )


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _row(product: str, label: str, **members: str) -> list[str]:
    values = dict.fromkeys(HEADERS, "")
    values |= {
        "ssp_book_code": "US-LIST",
        "legacy_version_label": label,
        "effective_from_date": "2026-07-01",
        "methodology_label": "Q3 list-price study",
        "lines.product_code": product,
        "lines.currency": "USD",
        "lines.method": "observable",
        "lines.distinctness": "distinct",
        "lines.ranges.low_value": "900.00",
        "lines.ranges.mid_value": "1000.00",
        "lines.ranges.high_value": "1100.00",
    }
    values |= members
    return [values[name] for name in HEADERS]


def _findings(app: FastAPI, world: J03World, import_id: str) -> dict[int, list[dict[str, Any]]]:
    listed = get(app, f"/api/v1/imports/{import_id}/rows", world.place.author)
    assert listed.status_code == 200, listed.text
    return {item["row_number"]: item for item in listed.json()["items"]}


def _committed(imports: Any, world: J03World, name: str, content: bytes) -> dict[str, Any]:
    import_id = diffed(imports, name, content, "ssp_values")
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(imports.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    return {"import_id": import_id}


def test_series_row_without_a_value_basis_is_refused_at_validation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """D-97 (3a) on the import channel: the series product's row is refused at
    ``lines.value_basis`` (SSP_VALUE_BASIS_REQUIRED, ERROR, BLOCKING exception item), the
    non-series row of the same file stays VALID, the upload is INVALID and no version or entry is
    written; a value outside E-49 is refused at the same column."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")  # imports are approved by a Revenue Reviewer
    imports = importer(j03.place)
    rows = [_row(PLATFORM_100, "2026-H2-A"), _row(IMPLEMENTATION_PLUS, "2026-H2-A")]
    import_id, validated = imported(
        imports, "ssp-undeclared.csv", csv_bytes(HEADERS, rows), "ssp_values"
    )
    assert validated["status"] == "INVALID", validated
    assert (validated["counts"]["rows"], validated["counts"]["valid"]) == (2, 1)
    assert validated["finding_counts"] == [
        {"code": "SSP_VALUE_BASIS_REQUIRED", "severity": "ERROR", "rows": 1}
    ]
    by_row = _findings(app, j03, import_id)
    assert {number: item["status"] for number, item in by_row.items()} == {2: "ERROR", 3: "VALID"}
    assert [message["message"] for message in by_row[2]["messages"]] == [
        "Row 2, column Lines value basis: Choose the value basis of this series product's entry "
        "(AMOUNT, PER_INCREMENT or PER_BOOKED_TERM). (SSP_VALUE_BASIS_REQUIRED)"
    ]
    items = imports.rows(
        select(exception_item.c.code, exception_item.c.severity, exception_item.c.status).where(
            exception_item.c.import_upload_id == UUID(import_id)
        )
    )
    assert [(str(i["code"]), str(i["severity"]), str(i["status"])) for i in items] == [
        ("SSP_VALUE_BASIS_REQUIRED", "BLOCKING", "OPEN")
    ]
    assert (
        imports.rows(
            select(ssp_book_version.c.id).where(
                ssp_book_version.c.legacy_version_label == "2026-H2-A"
            )
        )
        == []
    )
    assert imports.rows(select(import_row.c.id).where(import_row.c.status == "AGGREGATED")) == []

    _, invalid = imported(
        imports,
        "ssp-bad-basis.csv",
        csv_bytes(HEADERS, [_row(PLATFORM_100, "2026-H2-B", **{"lines.value_basis": "PER_UNIT"})]),
        "ssp_values",
    )
    assert invalid["status"] == "INVALID", invalid
    assert invalid["finding_counts"] == [
        {"code": "SSP_VALUE_BASIS_REQUIRED", "severity": "ERROR", "rows": 1}
    ]


def test_declared_entries_commit_and_round_trip(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """An explicit AMOUNT on the series product's row and an omitted basis on the non-series row
    (T-REF-30 default) commit one DRAFT version; ``GET /ssp-book-versions/{id}/entries`` returns
    the saved declarations."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")  # imports are approved by a Revenue Reviewer
    imports = importer(j03.place)
    rows = [
        _row(PLATFORM_100, "2026-H2", **{"lines.value_basis": "AMOUNT"}),
        _row(IMPLEMENTATION_PLUS, "2026-H2"),
    ]
    _committed(imports, j03, "ssp-declared.csv", csv_bytes(HEADERS, rows))
    (drafted,) = imports.rows(
        select(
            ssp_book_version.c.id, ssp_book_version.c.status, ssp_book_version.c.entry_count
        ).where(ssp_book_version.c.legacy_version_label == "2026-H2")
    )
    assert (str(drafted["status"]), drafted["entry_count"]) == ("DRAFT", 2)
    saved = imports.rows(
        select(ssp_entry.c.value_basis).where(ssp_entry.c.ssp_book_version_id == drafted["id"])
    )
    assert sorted(str(row["value_basis"]) for row in saved) == ["AMOUNT", "AMOUNT"]
    shown = get(app, f"/api/v1/ssp-book-versions/{drafted['id']}/entries", j03.place.author)
    assert shown.status_code == 200, shown.text
    entries = {item["product_code"]: item for item in shown.json()["items"]}
    assert entries[PLATFORM_100]["value_basis"] == "AMOUNT"
    assert entries[IMPLEMENTATION_PLUS]["value_basis"] == "AMOUNT"


# --- F-DIN-SSP-R1 (Codex review of ad38da3): band rows of one entry -------------------------------


def _band_row(product: str, label: str, band: tuple[str, str, str], **members: str) -> list[str]:
    values = dict.fromkeys(HEADERS, "")
    values |= {
        "ssp_book_code": "US-LIST",
        "legacy_version_label": label,
        "effective_from_date": "2026-07-01",
        "methodology_label": "Q3 list-price study",
        "lines.product_code": product,
        "lines.currency": "USD",
        "lines.method": "observable",
        "lines.distinctness": "distinct",
        "lines.ranges.band_dimension": "QUANTITY",
        "lines.ranges.band_from": band[0],
        "lines.ranges.band_to": band[1],
        "lines.ranges.point_value": band[2],
    }
    values |= members
    return [values[name] for name in HEADERS]


@pytest.mark.parametrize(
    ("basis", "unit"), [("PER_INCREMENT", "INCREMENTS"), ("PER_BOOKED_TERM", "")]
)
@pytest.mark.parametrize("amount_first", [True, False])
def test_r1_band_rows_with_differing_declarations_are_refused_in_both_orders(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    basis: str,
    unit: str,
    amount_first: bool,
) -> None:
    """Fail-first on ad38da3: two band rows of one AVM-PLAT-100 entry, one AMOUNT and one PER_*,
    passed validation and committed ONE AMOUNT entry with both bands. Now the later row is refused
    (SSP_ENTRY_DECLARATION_DISAGREES), the upload is INVALID and nothing is written."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")
    imports = importer(j03.place)
    label = f"R1-{basis}-{'A' if amount_first else 'B'}"
    amount = _band_row(
        PLATFORM_100, label, ("0", "10", "1000.00"), **{"lines.value_basis": "AMOUNT"}
    )
    other = _band_row(
        PLATFORM_100,
        label,
        ("10", "20", "900.00"),
        **{"lines.value_basis": basis, "lines.quantity_unit": unit},
    )
    rows = [amount, other] if amount_first else [other, amount]
    import_id, validated = imported(
        imports, f"ssp-r1-{label}.csv", csv_bytes(HEADERS, rows), "ssp_values"
    )
    assert validated["status"] == "INVALID", validated
    codes = {item["code"] for item in validated["finding_counts"]}
    assert "SSP_ENTRY_DECLARATION_DISAGREES" in codes
    by_row = _findings(app, j03, import_id)
    assert by_row[3]["status"] == "ERROR"
    assert (
        imports.rows(
            select(ssp_book_version.c.id).where(ssp_book_version.c.legacy_version_label == label)
        )
        == []
    )


def test_r1_matching_amount_band_rows_still_merge_their_bands(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The legitimate multi-band positive: two AMOUNT rows of one entry commit one entry with two
    bands (L5-1-Q-22)."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")
    imports = importer(j03.place)
    rows = [
        _band_row(PLATFORM_100, "R1-OK", ("0", "10", "1000.00"), **{"lines.value_basis": "AMOUNT"}),
        _band_row(PLATFORM_100, "R1-OK", ("10", "20", "900.00"), **{"lines.value_basis": "AMOUNT"}),
    ]
    _committed(imports, j03, "ssp-r1-ok.csv", csv_bytes(HEADERS, rows))
    (drafted,) = imports.rows(
        select(ssp_book_version.c.id, ssp_book_version.c.entry_count).where(
            ssp_book_version.c.legacy_version_label == "R1-OK"
        )
    )
    assert drafted["entry_count"] == 1
    shown = get(app, f"/api/v1/ssp-book-versions/{drafted['id']}/entries", j03.place.author)
    assert shown.status_code == 200, shown.text
    (entry,) = shown.json()["items"]
    assert entry["value_basis"] == "AMOUNT" and len(entry["ranges"]) == 2


# --- Ruling (c): the legacy sku_ssp template cannot declare a series product ---------------------


def test_legacy_sku_ssp_row_for_a_series_product_fails_closed(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Fail-first on ad38da3: a legacy SKU SSP row naming the series product AVM-PLAT-100 validated
    and would commit an entry with the silent T-REF-30 default AMOUNT. Now the row is refused at
    validation (SSP_VALUE_BASIS_REQUIRED at "SKU Name"): the legacy template cannot declare a
    series product's basis; series products go through the v2 template."""
    from erev_api.domain.imports import legacy_templates as columns
    from support.factories import workbook_bytes

    j03 = j03_world(app, keyring, clock, files)
    imports = importer(j03.place)
    headers = [
        columns.SKU_ID,
        columns.SKU,
        columns.DISTINCT_FLAG,
        columns.LIST_PRICE,
        columns.STRATIFICATION,
        columns.DISCOUNT,
        columns.RANGE,
        columns.SSP_VERSION,
        columns.REVENUE_ACCOUNT,
    ]
    row = [
        "900",
        PLATFORM_100,
        "Distinct",
        "100000",
        "Platform",
        "0.1",
        "0.15",
        "2026-07-01",
        "5001",
    ]
    import_id, validated = imported(
        imports,
        "SKU SSP Template.xlsx",
        workbook_bytes("SKU Setup", headers, [row]),
        "legacy_sku_ssp",
    )
    assert validated["status"] == "INVALID", validated
    assert validated["finding_counts"] == [
        {"code": "SSP_VALUE_BASIS_REQUIRED", "severity": "ERROR", "rows": 1}
    ]
    by_row = _findings(app, j03, import_id)
    assert by_row[2]["status"] == "ERROR"
    assert any("series" in m["message"] for m in by_row[2]["messages"])


# --- the book's entity and the uploader's scope (rulings R-29, R-98 (2), (6)) -------------------

SSP_BOOKS = "/api/v1/ssp-books"
ENTITY_CODE = "IMPORT_ENTITY_NOT_AVAILABLE"
PER_INCREMENT = {"lines.value_basis": "PER_INCREMENT"}


def _book(world: J03World, code: str, entity_code: str) -> None:
    created = post(
        world.app,
        SSP_BOOKS,
        world.place.author,
        {
            "code": code,
            "name": f"{code} list prices",
            "currency": "USD",
            "entity_code": entity_code,
        },
    )
    assert created.status_code == 201, created.text


def _scoped(world: J03World, name: str, *roles: str) -> ImportWorld:
    """A member whose ``roles`` cover AVM-UK only, as an import world."""
    someone = colleague(world.place.tenant_id, name)
    for code in roles[:-1]:
        assign(someone, code, entity_ids=[world.uk_entity_id])
    place = world.place
    return ImportWorld(
        app=place.app,
        actor=holding(place.app, someone, roles[-1], entity_ids=[world.uk_entity_id]),
        runtime=JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files),
        clock=place.clock,
    )


def _named(imports: ImportWorld, import_id: str) -> list[UUID] | None:
    value = imports.scalar(
        select(import_upload.c.named_entity_ids).where(import_upload.c.id == UUID(import_id))
    )
    return None if value is None else sorted((UUID(str(item)) for item in value), key=str)


def _row_findings(imports: ImportWorld, import_id: str) -> list[tuple[int, str, str]]:
    """(row, code, message) of the row findings of an upload, read over every entity."""
    found = imports.rows(
        select(import_row.c.row_number, exception_item.c.code, exception_item.c.message)
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number, exception_item.c.code)
    )
    return [(int(row["row_number"]), str(row["code"]), str(row["message"])) for row in found]


def test_r98_a_book_outside_the_scope_is_refused_before_the_declaration_rule(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """R-98 (6): the book US-ONLY belongs to AVM-US and holds a per-increment entry of
    AVM-PLAT-100 counted in INCREMENTS. Sam's ``ssp.create`` covers AVM-UK only. His row for
    that book and product, counted in SERVICE_UNITS, was refused twice: by the scope ("SSP book
    US-ONLY is not available") and by the declaration rule, which reads the SSP tables — no
    entity scope narrows them — and told him that the book's entries of the product "declare
    the quantity unit INCREMENTS". The scope finding now comes first and the row is not
    examined further: one finding, the one a book that does not exist gets. Positive control:
    Maya, whose ``ssp.create`` covers the book, is told the unit."""
    j03 = j03_world(app, keyring, clock, files)
    assign(j03.priya.member, "revenue_reviewer")  # imports are approved by a Revenue Reviewer
    maya = importer(j03.place)
    _book(j03, "US-ONLY", "AVM-US")
    stored = _row(
        PLATFORM_100,
        "2026-H2-US",
        ssp_book_code="US-ONLY",
        **PER_INCREMENT,
        **{"lines.quantity_unit": "INCREMENTS"},
    )
    _committed(maya, j03, "ssp-us-only.csv", csv_bytes(HEADERS, [stored]))

    sam = _scoped(j03, "sam", "ssp_analyst", "revenue_accountant")
    units = {**PER_INCREMENT, "lines.quantity_unit": "SERVICE_UNITS"}
    other = _row(PLATFORM_100, "2026-H2-SAM", ssp_book_code="US-ONLY", **units)
    ghost = _row(PLATFORM_100, "2026-H2-SAM", ssp_book_code="NO-SUCH", **units)
    other_id, shown = imported(sam, "sam-us-only.csv", csv_bytes(HEADERS, [other]), "ssp_values")
    ghost_id, absent = imported(sam, "sam-no-such.csv", csv_bytes(HEADERS, [ghost]), "ssp_values")
    assert (shown["status"], absent["status"]) == ("INVALID", "INVALID"), (shown, absent)
    outside = _row_findings(maya, other_id)
    unknown = _row_findings(maya, ghost_id)
    assert [(row, code) for row, code, _ in outside] == [(2, ENTITY_CODE)], outside
    assert [(row, code) for row, code, _ in unknown] == [(2, ENTITY_CODE)], unknown
    assert "SSP book US-ONLY is not available for this import." in outside[0][2]
    assert outside[0][2] == unknown[0][2].replace("NO-SUCH", "US-ONLY")
    assert "INCREMENTS" not in outside[0][2] and "quantity unit" not in outside[0][2]
    # The upload naming the AVM-US book is scoped by that entity; the unknown book resolves to
    # nothing (ruling R-98 (2)).
    assert _named(maya, other_id) == [j03.entity_id]
    assert _named(maya, ghost_id) is None

    told_id, told = imported(maya, "maya-us-only.csv", csv_bytes(HEADERS, [other]), "ssp_values")
    assert told["status"] == "INVALID", told
    assert [(row, code) for row, code, _ in _row_findings(maya, told_id)] == [
        (2, "SSP_QUANTITY_UNIT_DISAGREES")
    ]
    assert "declare the quantity unit INCREMENTS" in _row_findings(maya, told_id)[0][2]


def test_r98_ssp_values_stay_inside_the_scope_of_ssp_create(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The ``ssp_values`` template names an entity through its book (04 §16.6 template scope).
    Sam (``ssp.create`` for AVM-UK): a row for the AVM-UK book validates and names AVM-UK; a
    row for the book US-LIST, which has no entity, is tenant-level data. Eve is a Revenue
    Accountant for AVM-UK — ``import.upload`` without ``ssp.create``: her row for the AVM-UK
    book is refused by name (she holds the write permission for no entity), and her row for
    US-LIST, which names no entity, validates as tenant-level data does (R-41 (5))."""
    j03 = j03_world(app, keyring, clock, files)
    maya = importer(j03.place)
    _book(j03, "UK-LIST", "AVM-UK")
    sam = _scoped(j03, "sam", "ssp_analyst", "revenue_accountant")
    eve = _scoped(j03, "eve", "revenue_accountant")
    amount = {"lines.value_basis": "AMOUNT"}
    uk_row = _row(PLATFORM_100, "2026-H2-UK", ssp_book_code="UK-LIST", **amount)
    open_row = _row(PLATFORM_100, "2026-H2-OPEN", **amount)

    uk_id, uk = imported(sam, "sam-uk.csv", csv_bytes(HEADERS, [uk_row]), "ssp_values")
    assert uk["status"] == "VALIDATED", (uk, _row_findings(maya, uk_id))
    assert _named(maya, uk_id) == [j03.uk_entity_id]
    open_id, opened = imported(sam, "sam-open.csv", csv_bytes(HEADERS, [open_row]), "ssp_values")
    assert opened["status"] == "VALIDATED", (opened, _row_findings(maya, open_id))
    assert _named(maya, open_id) == []

    refused_row = _row(PLATFORM_100, "2026-H2-EVE", ssp_book_code="UK-LIST", **amount)
    refused_id, refused = imported(
        eve, "eve-uk.csv", csv_bytes(HEADERS, [refused_row]), "ssp_values"
    )
    assert refused["status"] == "INVALID", refused
    found = _row_findings(maya, refused_id)
    assert [(row, code) for row, code, _ in found] == [(2, ENTITY_CODE)], found
    assert "SSP book UK-LIST is not available for this import." in found[0][2]
    level_row = _row(PLATFORM_100, "2026-H2-EVE-OPEN", **amount)
    level_id, level = imported(eve, "eve-open.csv", csv_bytes(HEADERS, [level_row]), "ssp_values")
    assert level["status"] == "VALIDATED", (level, _row_findings(maya, level_id))
    assert _named(maya, level_id) == []
