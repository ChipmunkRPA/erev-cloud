"""DIN-5 legacy v1 progress tracking template (ENGINE_SPEC S01-R-07, S01-R-08; 04 T-IMP-01
``legacy_progress_tracking``, table 15.4-A; PRD J-01.10, WLD-X-26, IMP-04, IMP-22 to IMP-25;
DEVIATIONS DEV-010, DEV-012, DEV-020, DEV-021, OQ-D11; legacy 02 §7.3 TC-delivery-01, 02, 06, 10,
13, 15, 16, 19, 20; POLICIES ALG-06; 03 REQ-REC-024, REQ-REC-025, REQ-TP-009; control CTL-008;
BUILD_SPEC DIN-5).

World: ``support.legacy_replay.legacy_world`` (J-01.2 to J-01.5) and ``replayed``, which replays the
golden steps through the import pipeline (DG-PAR-04 order). Maya uploads and Priya approves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    contract,
    contract_event,
    contract_version,
    exception_item,
    import_row,
    obligation_version,
    source_invoice,
    source_invoice_line,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import imported, workbook_bytes
from support.legacy_replay import LegacyWorld, committed, legacy_world, replayed, submit
from support.reference import get

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
TOLERANCE = Decimal("0.0001")


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


def progress_file(rows: Sequence[Sequence[Any]]) -> bytes:
    return workbook_bytes("Progress Tracking", HEADERS, rows)


def row(
    contract_name: str, pob: str, sku: str, delivery: Any, billing: Any, pre: Any = 0
) -> list[Any]:
    return [contract_name, pob, sku, delivery, billing, pre, *MEMOS]


def progress(
    world: LegacyWorld, name: str, rows: Sequence[Sequence[Any]], on: str
) -> dict[str, Any]:
    return committed(
        world, name, progress_file(rows), "legacy_progress_tracking", {"effective_date": on}
    )


def invalid(
    world: LegacyWorld, name: str, rows: Sequence[Sequence[Any]]
) -> tuple[str, list[dict[str, Any]]]:
    import_id, validated = imported(
        world.imports,
        name,
        progress_file(rows),
        "legacy_progress_tracking",
        {"effective_date": "2023-01-31"},
    )
    assert validated["status"] == "INVALID", validated
    items = world.imports.rows(
        select(
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.message,
            import_row.c.row_number,
        )
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number, exception_item.c.code)
    )
    return import_id, items


def _contract(world: LegacyWorld, name: str) -> dict[str, Any]:
    (found,) = world.imports.rows(select(contract).where(contract.c.external_id == name))
    return found


def _latest(world: LegacyWorld, name: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    found = _contract(world, name)
    (version,) = world.imports.rows(
        select(contract_version)
        .where(
            contract_version.c.combination_group_id == found["combination_group_id"],
            contract_version.c.book_code == "ASC606",
        )
        .order_by(contract_version.c.version_no.desc())
        .limit(1)
    )
    obligations = world.imports.rows(
        select(obligation_version).where(
            obligation_version.c.contract_version_id == version["id"],
            obligation_version.c.contract_id == found["id"],
        )
    )
    return version, {str(item["obligation_key"]): item for item in obligations}


def _events(world: LegacyWorld, import_id: str) -> list[dict[str, Any]]:
    return world.imports.rows(
        select(
            contract_event.c.contract_id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.origin,
            contract_event.c.payload,
            contract_event.c.idempotency_key,
        )
        .where(contract_event.c.import_upload_id == UUID(import_id))
        .order_by(contract_event.c.record_seq)
    )


def _exact(
    world: LegacyWorld, obligation: Mapping[str, Any], measure: str, period: str | None = None
) -> Decimal:
    """The exact figure behind a posted obligation measure: the traced node's value plus its
    rounding residue (API-S-Explain; DG-KRN-EXP-03). Period revenue is measure ``revenue`` of a
    period."""
    response = get(
        world.app,
        f"/api/v1/explain/obligation_version/{obligation['id']}/{measure}",
        world.maya,
        {} if period is None else {"period": period},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    (root,) = [node for node in body["nodes"] if node["id"] == body["root_node_id"]]
    return Decimal(root["value"]) + Decimal(root["rounding_residue"] or "0")


def _close(
    world: LegacyWorld,
    obligation: Mapping[str, Any],
    measure: str,
    figure: str,
    period: str | None = None,
) -> bool:
    """``revenue_cum`` is traced exactly; the revenue of a version (legacy ``Current Rev Rec``) is
    the change of the exact cumulative revenue from the previous obligation version."""
    if measure == "revenue":
        found = _exact(world, obligation, "revenue_cum")
        previous = obligation["previous_obligation_version_id"]
        if previous is not None:
            (earlier,) = world.imports.rows(
                select(obligation_version).where(obligation_version.c.id == previous)
            )
            found -= _exact(world, earlier, "revenue_cum")
    else:
        found = _exact(world, obligation, measure, period)
    assert abs(found - Decimal(figure)) <= TOLERANCE, (measure, period, found, figure)
    return True


def test_progress_rows_emit_events(legacy: LegacyWorld) -> None:
    done = replayed(legacy, "04")["04"]
    import_id = done["id"]
    rows = legacy.imports.rows(
        select(
            import_row.c.id,
            import_row.c.row_number,
            import_row.c.status,
            import_row.c.aggregated_into_row_id,
        )
        .where(import_row.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number)
    )
    by_number = {item["row_number"]: item for item in rows}
    # The two Contract 1 POB #1 rows (worksheet rows 2 and 6) are summed: row 6 into row 2.
    assert (str(by_number[2]["status"]), by_number[2]["aggregated_into_row_id"]) == ("VALID", None)
    assert (str(by_number[6]["status"]), by_number[6]["aggregated_into_row_id"]) == (
        "AGGREGATED",
        by_number[2]["id"],
    )
    assert done["counts"]["aggregated"] == 1
    contract_1 = _contract(legacy, "Contract 1")["id"]
    events = [item for item in _events(legacy, import_id) if item["contract_id"] == contract_1]
    assert {item["effective_date"] for item in events} == {date(2023, 1, 31)}
    assert {str(item["origin"]) for item in events} == {"IMPORT"}
    pob_1 = [
        (str(item["event_type"]), item["payload"])
        for item in events
        if item["payload"].get("obligation_key") == "POB #1"
    ]
    assert [kind for kind, _ in pob_1] == ["DELIVERY_RECORDED", "BILLING_RECORDED", "MEMO_UPDATED"]
    assert (pob_1[0][1]["quantity"], Decimal(pob_1[1][1]["amount"]["amount"])) == (
        "2",
        Decimal("100"),
    )
    assert pob_1[1][1]["invoice_number"] == f"{import_id}:Contract 1:POB #1"
    assert all(item["idempotency_key"].startswith("imp:") for item in events)
    _, c1 = _latest(legacy, "Contract 1")
    # TC-delivery-01: Contract 1 POB #1 revenue 128.84 (WLD-X-26).
    assert Decimal(c1["POB #1"]["revenue_cum"]).quantize(Decimal("0.01")) == Decimal("128.84")
    second, c2 = _latest(legacy, "Contract 2")
    # TC-delivery-02: Contract 2 is delivered without billing, so its position is a debit
    # (L5-1-Q-15: the figure 58.85 needs the CTR-12 VC element of the booking).
    revenue = sum(Decimal(item["revenue_cum"]) for item in c2.values())
    assert revenue > 0
    assert Decimal(second["net_position"]) == -revenue


def test_pre_standard_revenue_emitted(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    done = progress(
        legacy,
        "pre-standard 1.31.2023.xlsx",
        [
            row("Contract 1", "POB #2", "Software 1", 0, 0, 66),
            row("Contract 1", "POB #3", "Consulting 1", 0, 0, -12.5),
        ],
        "2023-01-31",
    )
    recorded = [
        (item["payload"]["obligation_key"], Decimal(item["payload"]["amount"]["amount"]))
        for item in _events(legacy, done["id"])
        if str(item["event_type"]) == "PRE_STANDARD_REVENUE_RECORDED"
    ]
    assert recorded == [("POB #2", Decimal("66")), ("POB #3", Decimal("-12.5"))]


def test_tc_delivery_06_return_and_zero_delivery_billing(legacy: LegacyWorld) -> None:
    done = replayed(legacy, "07")["07"]
    contract_1 = _contract(legacy, "Contract 1")["id"]
    events = [
        (str(item["event_type"]), item["payload"])
        for item in _events(legacy, done["id"])
        if item["contract_id"] == contract_1
    ]
    by_pob: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for kind, payload in events:
        by_pob.setdefault(str(payload.get("obligation_key")), []).append((kind, payload))
    assert [kind for kind, _ in by_pob["POB #1"]] == [
        "RETURN_RECORDED",
        "CREDIT_MEMO_RECORDED",
        "MEMO_UPDATED",
    ]
    assert (
        by_pob["POB #1"][0][1]["quantity"],
        Decimal(by_pob["POB #1"][1][1]["amount"]["amount"]),
    ) == (
        "3",
        Decimal("200"),
    )
    assert [kind for kind, _ in by_pob["POB #2"]] == ["BILLING_RECORDED", "MEMO_UPDATED"]
    assert Decimal(by_pob["POB #2"][0][1]["amount"]["amount"]) == Decimal("300")
    _, c1 = _latest(legacy, "Contract 1")
    assert _close(legacy, c1["POB #1"], "revenue", "-193.260654", "FY2023-P04")
    for item in c1.values():
        assert Decimal(item["delivered_quantity_cum"]) >= 0
        assert Decimal(item["remaining_quantity"]) >= 0


def test_legacy_cm_sign_1_a_credit_memo_is_stored_signed(legacy: LegacyWorld) -> None:
    """04 T-SRC-04 ``total_amount`` "Signed: credit memos negative" and T-SRC-05 ``amount``
    "Signed" (item LEGACY-CM-SIGN-1): the synthetic document of a negative billing — golden step
    07, Contract 1: POB #1 is refunded 200, POB #2 billed 300 — and its line are stored at
    -200, the invoice at +300. The events keep the positive Money of 04 §16.3."""
    done = replayed(legacy, "07")["07"]
    stored = legacy.imports.rows(
        select(
            source_invoice_line.c.obligation_ref,
            source_invoice.c.document_kind,
            source_invoice.c.total_amount,
            source_invoice_line.c.amount,
        )
        .join(source_invoice_line, source_invoice_line.c.source_invoice_id == source_invoice.c.id)
        .where(
            source_invoice.c.external_invoice_id.like(f"{done['id']}:Contract 1:%"),
            source_invoice_line.c.obligation_ref.in_(["POB #1", "POB #2"]),
        )
        .order_by(source_invoice_line.c.obligation_ref)
    )
    assert [
        (
            row["obligation_ref"],
            str(row["document_kind"]),
            Decimal(row["total_amount"]),
            Decimal(row["amount"]),
        )
        for row in stored
    ] == [
        ("POB #1", "CREDIT_MEMO", Decimal("-200"), Decimal("-200")),
        ("POB #2", "INVOICE", Decimal("300"), Decimal("300")),
    ]
    contract_1 = _contract(legacy, "Contract 1")["id"]
    amounts = {
        (str(item["event_type"]), str(item["payload"]["obligation_key"])): Decimal(
            item["payload"]["amount"]["amount"]
        )
        for item in _events(legacy, done["id"])
        if item["contract_id"] == contract_1
        and str(item["event_type"]) in ("CREDIT_MEMO_RECORDED", "BILLING_RECORDED")
    }
    assert amounts[("CREDIT_MEMO_RECORDED", "POB #1")] == Decimal("200")
    assert amounts[("BILLING_RECORDED", "POB #2")] == Decimal("300")


def test_tc_delivery_15_return_and_refund_above_cumulative_rejected(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    progress(
        legacy,
        "delivered 1.31.2023.xlsx",
        [row("Contract 1", "POB #1", "Hardware 1", 2, 100)],
        "2023-01-31",
    )
    head = int(_contract(legacy, "Contract 1")["head_stream_version"])
    _, items = invalid(
        legacy, "return 2.28.2023.xlsx", [row("Contract 1", "POB #1", "Hardware 1", -3, -150)]
    )
    assert [(item["code"], item["row_number"]) for item in items] == [
        ("REFUND_EXCEEDS_BILLED", 2),
        ("RETURN_EXCEEDS_DELIVERED", 2),
    ]
    # BUILD_SPEC DIN-7: row messages name worksheet, row, column, key and rule id (REQ-DAT-006).
    assert [item["message"] for item in items] == [
        "Progress Tracking row 2, column Current Billing: Credit of 150.00 exceeds the 100.00 "
        "billed on Contract 1, obligation POB #1 (Hardware 1). Key Contract 1 / POB #1 / Hardware "
        "1. (REFUND_EXCEEDS_BILLED)",
        "Progress Tracking row 2, column Current Delivery: Return of 3 units exceeds the 2 units "
        "delivered on Contract 1, obligation POB #1 (Hardware 1). Key Contract 1 / POB #1 / "
        "Hardware 1. (RETURN_EXCEEDS_DELIVERED)",
    ]
    assert int(_contract(legacy, "Contract 1")["head_stream_version"]) == head


def test_tc_delivery_19_return_after_full_delivery(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    progress(
        legacy,
        "full 1.31.2023.xlsx",
        [row("Contract 1", "POB #2", "Software 1", 2, 0)],
        "2023-01-31",
    )
    _, delivered = _latest(legacy, "Contract 1")
    assert _close(legacy, delivered["POB #2"], "revenue_cum", "237.066402")
    progress(
        legacy,
        "return 2.28.2023.xlsx",
        [row("Contract 1", "POB #2", "Software 1", -1, 0)],
        "2023-02-28",
    )
    _, returned = _latest(legacy, "Contract 1")
    pob = returned["POB #2"]
    assert _close(legacy, pob, "revenue", "-118.533201", "FY2023-P02")
    assert _close(legacy, pob, "revenue_cum", "118.533201")
    assert Decimal(pob["remaining_quantity"]) == Decimal(1)


def test_tc_delivery_20_deliver_all_then_return_one(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    progress(
        legacy,
        "all 1.31.2023.xlsx",
        [row("Contract 1", "POB #1", "Hardware 1", 5, 0)],
        "2023-01-31",
    )
    _, delivered = _latest(legacy, "Contract 1")
    pob = delivered["POB #1"]
    assert _close(legacy, pob, "revenue", "322.101090", "FY2023-P01")
    # [J] L5-1-Q-26: with no remaining quantity the remaining unit rate is not a number of its
    # own: the stored rate is null or 0, never infinite.
    assert pob["remaining_unit_revenue_rate"] in (None, Decimal(0))
    progress(
        legacy,
        "return 2.28.2023.xlsx",
        [row("Contract 1", "POB #1", "Hardware 1", -1, 0)],
        "2023-02-28",
    )
    _, returned = _latest(legacy, "Contract 1")
    pob = returned["POB #1"]
    assert _close(legacy, pob, "revenue", "-64.420218", "FY2023-P02")
    rate = pob["remaining_unit_revenue_rate"]
    assert rate is None or Decimal(rate).is_finite()


def test_tc_delivery_13_blank_memo_processed_with_warning(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    blank = ["Contract 1", "POB #2", "Software 1", 1, 50, 0, None, "Delivery 2", "Delivery 3"]
    done = progress(legacy, "blank memo 1.31.2023.xlsx", [blank], "2023-01-31")
    assert (done["counts"]["warnings"], done["counts"]["errors"]) == (1, 0)
    (item,) = legacy.imports.rows(
        select(
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.field,
            import_row.c.row_number,
        )
        .join(import_row, import_row.c.id == exception_item.c.import_row_id)
        .where(exception_item.c.import_upload_id == UUID(done["id"]))
    )
    assert (item["code"], str(item["severity"]), item["field"], item["row_number"]) == (
        "PROGRESS_MEMO_BLANK",
        "WARNING",
        "Memo 1",
        2,
    )
    _, c1 = _latest(legacy, "Contract 1")
    assert _close(legacy, c1["POB #2"], "revenue_cum", "118.533201")


def test_tc_delivery_16_different_memos_aggregated_then_over_delivery(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    first = ["Contract 1", "POB #1", "Hardware 1", 3, 0, 0, "Batch A", "", ""]
    second = ["Contract 1", "POB #1", "Hardware 1", 3, 0, 0, "Batch B", "", ""]
    import_id, items = invalid(legacy, "twice 1.31.2023.xlsx", [first, second])
    over = [item for item in items if item["code"] == "PROGRESS_OVER_DELIVERY"]
    assert [(item["row_number"], item["message"]) for item in over] == [
        (
            2,
            "Progress Tracking row 2, column Current Delivery: Contract 1, obligation POB #1 "
            "(Hardware 1): requested 6, remaining 5. Rows 2, 3. Key Contract 1 / POB #1 / Hardware "
            "1. (PROGRESS_OVER_DELIVERY)",
        )
    ]
    statuses = legacy.imports.rows(
        select(import_row.c.row_number, import_row.c.status)
        .where(import_row.c.import_upload_id == UUID(import_id))
        .order_by(import_row.c.row_number)
    )
    assert [(item["row_number"], str(item["status"])) for item in statuses] == [
        (2, "ERROR"),
        (3, "AGGREGATED"),
    ]


def test_tc_delivery_10_over_delivery_and_over_billing_rejected(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    heads = {
        name: int(_contract(legacy, name)["head_stream_version"])
        for name in ("Contract 1", "Contract 2")
    }
    _, items = invalid(
        legacy,
        "over 1.31.2023.xlsx",
        [
            row("Contract 1", "POB #1", "Hardware 1", 6, 0),
            row("Contract 1", "POB #2", "Software 1", 0, 500),
            row("Contract 2", "VC #1", "Variable Consideration", 2, 0),
        ],
    )
    assert [(item["code"], item["row_number"], item["message"]) for item in items] == [
        (
            "PROGRESS_OVER_DELIVERY",
            2,
            "Progress Tracking row 2, column Current Delivery: Contract 1, obligation POB #1 "
            "(Hardware 1): requested 6, remaining 5. Key Contract 1 / POB #1 / Hardware 1. "
            "(PROGRESS_OVER_DELIVERY)",
        ),
        (
            "PROGRESS_OVER_BILLING",
            3,
            "Progress Tracking row 3, column Current Billing: Contract 1, obligation POB #2 "
            "(Software 1): billing 500.00 exceeds the remaining billing plan 400.00. Key Contract "
            "1 / POB #2 / Software 1. (PROGRESS_OVER_BILLING)",
        ),
        (
            "PROGRESS_OVER_DELIVERY",
            4,
            "Progress Tracking row 4, column Current Delivery: Contract 2, obligation VC #1 "
            "(Variable Consideration): requested 2, remaining 1. Key Contract 2 / VC #1 / Variable "
            "Consideration. (PROGRESS_OVER_DELIVERY)",
        ),
    ]
    assert {name: int(_contract(legacy, name)["head_stream_version"]) for name in heads} == heads


@pytest.mark.control("CTL-008")
def test_ctl_008_import_over_delivery_blocks_commit(legacy: LegacyWorld) -> None:
    replayed(legacy, "02")
    head = int(_contract(legacy, "Contract 1")["head_stream_version"])
    import_id, items = invalid(
        legacy, "over 1.31.2023.xlsx", [row("Contract 1", "POB #1", "Hardware 1", 7, 0)]
    )
    assert [item["code"] for item in items] == ["PROGRESS_OVER_DELIVERY"]
    refused = submit(legacy.imports, import_id)
    assert refused.status_code == 409, refused.text
    assert refused.json()["type"].endswith("/invalid-transition")
    assert int(_contract(legacy, "Contract 1")["head_stream_version"]) == head
