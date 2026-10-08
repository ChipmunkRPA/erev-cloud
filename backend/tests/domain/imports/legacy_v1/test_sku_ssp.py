"""DIN-4 legacy v1 SKU SSP template (ENGINE_SPEC S01-R-05; 04 T-IMP-01, §17.3 LM-SSP-01 to
LM-SSP-09, T-REF-28 to T-REF-31; PRD J-01.6, J-01.7, WLD-F-01; 03 REQ-SSP-013; BUILD_SPEC DIN-4).

World: ``support.legacy_replay.legacy_world`` (J-01.2 to J-01.5). Maya uploads, Priya approves, and
the jobs run as the worker runs them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    exception_item,
    gl_account,
    import_row,
    import_row_lineage,
    pob_template,
    product,
    source_record,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
)
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import imported, run_import_job, workbook_bytes
from support.legacy_replay import (
    SKU_SSP,
    LegacyWorld,
    committed,
    diffed,
    job_of,
    legacy_world,
    shown,
    submit,
    workbook_rows,
)
from support.reference import approve
from support.rows import publish_registry_version

# WLD-F-01 rows: (SKU, stratification, list price, midpoint discount, range, flag, revenue account).
WLD_F_01 = (
    ("Hardware 1", "Hardware 1", "100", "0.1", "0.15", "distinct", "5001"),
    ("Software 1", "Software 1", "200", "0.2", "0.15", "distinct", "5002"),
    ("Consulting 1", "Consulting 1", "300", "0.5", "0", "nondistinct", "5003"),
    ("Material Right - Hardware", "Material Right - Hardware", "1", "0", "0", "distinct", "5001"),
    ("Material Right - Software", "Material Right - Software", "1", "0", "0", "distinct", "5002"),
    (
        "Material Right - Services",
        "Material Right - Services",
        "1",
        "0",
        "0",
        "nondistinct",
        "5003",
    ),
    ("Variable Consideration", "VC", "0", "0", "0", "nondistinct", "5004"),
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


def _versions(world: LegacyWorld) -> list[dict[str, Any]]:
    return world.imports.rows(
        select(
            ssp_book_version.c.id,
            ssp_book_version.c.version_no,
            ssp_book_version.c.legacy_version_label,
            ssp_book_version.c.status,
            ssp_book_version.c.approval_request_id,
            ssp_book_version.c.content_sha256,
            ssp_book_version.c.published_at,
            ssp_book_version.c.entry_count,
        )
        .join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
        .where(ssp_book.c.code == "LEGACY-SKU-SSP")
        .order_by(ssp_book_version.c.version_no)
    )


def _entries(world: LegacyWorld, version_id: UUID) -> list[dict[str, Any]]:
    return world.imports.rows(
        select(
            product.c.code,
            ssp_entry.c.stratification,
            ssp_entry.c.method,
            ssp_entry.c.unit_list_price,
            ssp_entry.c.midpoint_discount_ratio,
            ssp_entry.c.range_ratio,
            ssp_entry.c.distinctness,
            gl_account.c.code.label("revenue_account"),
            ssp_range.c.band_dimension,
            ssp_range.c.low_value,
            ssp_range.c.mid_value,
            ssp_range.c.high_value,
        )
        .join(product, product.c.id == ssp_entry.c.product_id)
        .join(gl_account, gl_account.c.id == ssp_entry.c.revenue_gl_account_id)
        .join(ssp_range, ssp_range.c.ssp_entry_id == ssp_entry.c.id)
        .where(ssp_entry.c.ssp_book_version_id == version_id)
        .order_by(product.c.code)
    )


def test_sku_ssp_creates_legacy_book_version(legacy: LegacyWorld) -> None:
    done = committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    assert (done["counts"]["rows"], done["counts"]["errors"]) == (7, 0), done

    (book,) = legacy.imports.rows(
        select(ssp_book.c.code, ssp_book.c.resolution_mode).where(
            ssp_book.c.code == "LEGACY-SKU-SSP"
        )
    )
    assert str(book["resolution_mode"]) == "BY_LABEL"
    (version,) = _versions(legacy)
    assert (version["legacy_version_label"], str(version["status"]), version["entry_count"]) == (
        "2023-01-01",
        "APPROVED",
        7,
    )
    # APPROVED by the import approval (S01-R-05).
    assert str(version["approval_request_id"]) == done["approval_request_id"]
    assert version["published_at"] is not None

    entries = _entries(legacy, UUID(str(version["id"])))
    assert len(entries) == 7
    expected = sorted(WLD_F_01)
    for row, (code, stratification, price, discount, spread, flag, account) in zip(
        entries, expected, strict=True
    ):
        assert (row["code"], row["stratification"], str(row["method"])) == (
            code,
            stratification,
            "legacy_range",
        )
        assert (Decimal(row["unit_list_price"]), Decimal(row["midpoint_discount_ratio"])) == (
            Decimal(price),
            Decimal(discount),
        )
        assert Decimal(row["range_ratio"]) == Decimal(spread)
        assert (str(row["distinctness"]), row["revenue_account"]) == (flag, account)
        # One NONE band at full precision: mid = L × (1 − d), low = mid × (1 − r),
        # high = mid × (1 + r).
        mid = Decimal(price) * (1 - Decimal(discount))
        assert row["band_dimension"] == "NONE"
        assert (
            Decimal(row["low_value"]),
            Decimal(row["mid_value"]),
            Decimal(row["high_value"]),
        ) == (mid * (1 - Decimal(spread)), mid, mid * (1 + Decimal(spread)))

    products = legacy.imports.rows(
        select(
            product.c.code,
            product.c.name,
            product.c.sku_number,
            product.c.distinctness_default,
            product.c.principal_agent,
            pob_template.c.code.label("template_code"),
        )
        .outerjoin(pob_template, pob_template.c.id == product.c.default_pob_template_id)
        .order_by(product.c.sku_number)
    )
    assert [
        (row["code"], row["name"], row["sku_number"], str(row["distinctness_default"]))
        for row in products
    ] == [
        (code, code, str(number), flag)
        for number, (code, _, _, _, _, flag, _) in enumerate(WLD_F_01, start=1)
    ]
    assert {str(row["principal_agent"]) for row in products} == {"PRINCIPAL"}
    assert [row["template_code"] for row in products] == [
        "LEGACY-DISTINCT" if flag == "distinct" else "LEGACY-NONDISTINCT"
        for _, _, _, _, _, flag, _ in WLD_F_01
    ]
    accounts = legacy.imports.rows(
        select(gl_account.c.code, gl_account.c.account_type, gl_account.c.source_system)
        .where(gl_account.c.code.in_(["5001", "5002", "5003", "5004"]))
        .order_by(gl_account.c.code)
    )
    assert [(row["code"], str(row["account_type"])) for row in accounts] == [
        ("5001", "REVENUE"),
        ("5002", "REVENUE"),
        ("5003", "REVENUE"),
        ("5004", "REVENUE"),
    ]
    assert {str(row["source_system"]) for row in accounts} == {"LEGACY_TEMPLATE_V1"}


def test_upload_appends_versions(legacy: LegacyWorld) -> None:
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    (before,) = _versions(legacy)
    entries_before = _entries(legacy, UUID(str(before["id"])))

    headers, rows = workbook_rows(SKU_SSP)
    label = headers.index("SSP Version")
    price = headers.index("SKU Unit List Price")
    later = [[*row[:label], "2024-01-01", *row[label + 1 :]] for row in rows[:2]]
    later[0][price] = 110
    content = workbook_bytes("SKU Setup", headers, later)
    done = committed(legacy, "SKU SSP Template 2024.xlsx", content, "legacy_sku_ssp")
    assert done["counts"]["rows"] == 2

    first, second = _versions(legacy)
    assert first == before  # 2023-01-01 unchanged
    assert _entries(legacy, UUID(str(first["id"]))) == entries_before
    assert (second["legacy_version_label"], str(second["status"]), second["entry_count"]) == (
        "2024-01-01",
        "APPROVED",
        2,
    )
    assert str(second["approval_request_id"]) == done["approval_request_id"]
    hardware = _entries(legacy, UUID(str(second["id"])))[0]
    assert (hardware["code"], Decimal(hardware["mid_value"])) == ("Hardware 1", Decimal("99"))


def test_r109_quarantine_mode_loads_an_ssp_version_whole_or_not_at_all(legacy: LegacyWorld) -> None:
    """Supervisor ruling R-109 (c), on R-98 (10): in quarantine mode (REQ-DAT-008) the subject
    the rows of a legacy SKU SSP file build is the SSP book version, and the commit APPROVES it
    (S01-R-05) — a version approved without its refused rows is not the study that was
    uploaded. The delivered seven rows of version 2023-01-01, one with a distinct flag that is
    none, and two rows of version 2024-01-01: the six other rows of 2023-01-01 are refused with
    the bad one, by name, and only 2024-01-01 is diffed, approved and committed. Before, the
    2023-01-01 version was approved with six of its seven entries."""
    imports = legacy.imports
    context = DbContext(tenant_id=legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=legacy.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )
    headers, rows = workbook_rows(SKU_SSP)
    label, flag = headers.index("SSP Version"), headers.index("Distinct or Nondistinct")
    study = [list(row) for row in rows]
    study[2][flag] = "Sometimes"  # worksheet row 4
    later = [[*row[:label], "2024-01-01", *row[label + 1 :]] for row in rows[:2]]
    content = workbook_bytes("SKU Setup", headers, [*study, *later])

    import_id, validated = imported(imports, "SKU SSP mixed.xlsx", content, "legacy_sku_ssp")
    assert validated["is_quarantine_mode"] is True
    found = imports.rows(
        select(import_row.c.row_number, exception_item.c.code, exception_item.c.message)
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number, exception_item.c.code)
    )
    assert [(row["row_number"], str(row["code"])) for row in found] == [
        (2, "IMPORT_CONTRACT_INCOMPLETE"),
        (3, "IMPORT_CONTRACT_INCOMPLETE"),
        (4, "SSP_DISTINCT_FLAG_INVALID"),
        (5, "IMPORT_CONTRACT_INCOMPLETE"),
        (6, "IMPORT_CONTRACT_INCOMPLETE"),
        (7, "IMPORT_CONTRACT_INCOMPLETE"),
        (8, "IMPORT_CONTRACT_INCOMPLETE"),
    ], found
    assert (
        "Another row of SSP version 2023-01-01 was refused, so none of its rows is loaded. "
        "Correct that row and upload the version's rows again."
    ) in str(found[0]["message"]), found[0]
    assert (
        validated["status"],
        validated["counts"]["valid"],
        validated["counts"]["errors"],
    ) == ("VALIDATED", 2, 7), validated

    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_DIFF"))
    assert shown(imports, import_id)["status"] == "DIFF_READY"
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == "COMMITTED", done
    loaded = done["control_totals"]["loaded"]
    assert (loaded["rows"], loaded["quarantined"]) == (2, 7)
    assert loaded["amount_sums"] == done["control_totals"]["source"]["amount_sums"]
    assert all(check["source"] == check["stored"] for check in loaded["monetary_checks"])
    assert [
        (row["legacy_version_label"], str(row["status"]), row["entry_count"])
        for row in _versions(legacy)
    ] == [("2024-01-01", "APPROVED", 2)]


@pytest.mark.parametrize("corruption", [None, "price", "discount", "missing_band"])
def test_legacy_ssp_monetary_readback(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch, corruption: str | None
) -> None:
    from erev_api.domain.imports.legacy_v1 import sku_ssp
    from sqlalchemy import delete

    imports = legacy.imports
    import_id = diffed(imports, "sku-readback.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    approved = approve(legacy.app, str(submitted.json()["approval_request_id"]), legacy.priya)
    assert approved.status_code == 200, approved.text
    original = sku_ssp.upsert_ssp_entries

    def changed(uow: Any, version_id: Any, *, body: Any) -> Any:
        entries = list(body.entries)
        if corruption == "price":
            # Preserve aggregate list price; each source entry must still match.
            entries[0] = entries[0].model_copy(update={"unit_list_price": "101"})
            entries[1] = entries[1].model_copy(update={"unit_list_price": "199"})
        elif corruption == "discount":
            entries[0] = entries[0].model_copy(update={"midpoint_discount_ratio": "0.11"})
        ids = original(uow, version_id, body=body.model_copy(update={"entries": entries}))
        if corruption == "missing_band":
            uow.session.execute(delete(ssp_range).where(ssp_range.c.ssp_entry_id == ids[0]))
        return ids

    monkeypatch.setattr(sku_ssp, "upsert_ssp_entries", changed)
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == ("COMMITTED" if corruption is None else "FAILED"), done
    loaded = done["control_totals"]["loaded"]
    (check,) = loaded["monetary_checks"]
    if corruption is None:
        assert check["source"] == check["stored"]
        assert len(check["stored"]["entries"]) == 7
        assert Decimal(loaded["amount_sums"]["SKU Unit List Price"]) == Decimal("603")
        assert loaded["amount_sums"] == done["control_totals"]["source"]["amount_sums"]
    else:
        assert check["source"] != check["stored"]
        assert _versions(legacy) == []
        for table in (source_record, import_row_lineage):
            assert (
                imports.rows(select(table.c.id).where(table.c.import_upload_id == UUID(import_id)))
                == []
            )
        (finding,) = imports.rows(
            select(exception_item).where(
                exception_item.c.import_upload_id == UUID(import_id),
                exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
            )
        )
        assert finding["severity"] == "BLOCKING"
