"""Golden event streams (BUILD_SPEC ENB-1; B3-BS2-08; DG-PAR-02; ENGINE_SPEC S01-R-05 to S01-R-09).

No database fixture (DG-TST-18); the helper reads committed fixtures only.
"""

from __future__ import annotations

import builtins
import csv
import io
import os
from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.stages import s01_canonicalize
from erev_engine.trace import TraceBuilder
from support import golden_streams

SETUP_LIVE = golden_streams.GOLDEN_ROOT / "02-contract-setup-2023-01-01" / "contract_live.csv"
RUN_TMP = golden_streams.REPO_ROOT / ".run" / "tmp"
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def _golden_rows(contract: str) -> list[dict[str, str]]:
    with SETUP_LIVE.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["Contract Unique Name"] == contract]


def test_setup_lines_equal_golden_contract_live() -> None:
    stream = golden_streams.stream("Contract 1", "02")
    header = stream.contracts[0]
    assert (header.external_id, header.contracting_entity_code, header.inception_date) == (
        "Contract 1",
        "Mock Entity 1",
        date(2023, 1, 1),
    )
    lines = {str(line["obligation_key"]): line for line in stream.booking_lines()}
    rows = _golden_rows("Contract 1")
    assert len(rows) == 4
    assert sorted(lines) == sorted(row["POB Unique ID"] for row in rows)
    (version,) = stream.ssp_versions
    assert (version.version_key, version.legacy_version_label, version.resolution_mode) == (
        "LEGACY-SKU-SSP@v1",
        "2023-01-01",
        "BY_LABEL",
    )
    entries = {entry.product_code: entry for entry in version.entries}
    for row in rows:
        line = lines[row["POB Unique ID"]]
        assert line["quantity"] == Decimal(row["Original POB Total Qty"])
        assert line["total_price"] == Decimal(row["Original POB Total Selling Price"])
        assert line["product_code"] == row["SKU Name"]
        assert line["stratification"] == row["ASC 606 Stratification"]
        assert line["ssp_version_label"] == row["SSP Version"]
        assert line["start_date"] == date.fromisoformat(row["POB Start Date"][:10])
        assert line["end_date"] == date.fromisoformat(row["POB End Date"][:10])
        assert line["performing_entity_code"] == row["Selling Entity"]
        assert line["account_overrides"] == {
            "CONTRACT_ASSET": row["Unbilled A/R Account"],
            "CONTRACT_LIABILITY": row["Deferred Revenue Account"],
            "UNBILLED_RECEIVABLE": row["Unbilled A/R Account"],
        }
        entry = entries[row["SKU Name"]]
        (band,) = entry.ranges
        quantity = Decimal(row["Original POB Total Qty"])
        assert band.band_dimension == "NONE"
        assert band.mid_value is not None and band.low_value is not None
        assert band.high_value is not None
        assert quantity * band.mid_value == Decimal(row["Original SSP - Midpoint"])
        assert quantity * band.low_value == Decimal(row["Original SSP - Lower"])
        assert quantity * band.high_value == Decimal(row["Original SSP - Higher"])
        assert entry.distinctness == row["Distinct or Nondistinct"].lower()
        assert entry.revenue_account_code == row["Revenue Account"]
    assert [event.event_type for event in stream.events] == ["CONTRACT_BOOKED"]
    assert stream.estimate_versions == ()
    material_right = next(p for p in stream.products if p.code == "Material Right - Hardware")
    assert material_right.default_template_code == "LEGACY-MATERIAL-RIGHT"
    assert [right.obligation_key for right in header.material_rights] == ["POB #4"]


def test_setup_vc_row_and_modifications() -> None:
    stream = golden_streams.stream("Contract 2", "09")
    (vc,) = stream.estimate_versions
    assert (vc.estimate_key, vc.method, vc.constrained_amount, vc.effective_date) == (
        "Contract 2/VC-VC %231",
        "ENTERED_AMOUNT",
        Decimal("-100"),
        date(2023, 1, 1),
    )
    booked, applied = stream.events[:2]
    assert (booked.event_type, applied.event_type) == ("CONTRACT_BOOKED", "ESTIMATE_CHANGED")
    assert applied.estimate_version_key == vc.version_key
    modifications = stream.contracts[0].modifications
    assert [(m.modification_key, m.kind, m.template_mode) for m in modifications] == [
        ("MOD-08", "QUANTITY_CHANGE", "retrospective"),
        ("MOD-09", "VC_CHANGE", "pob_price_change"),
    ]
    amended = [event for event in stream.events if event.event_type == "CONTRACT_AMENDED"]
    assert [event.effective_date for event in amended] == [date(2023, 5, 15), date(2023, 5, 31)]
    assert amended[0].payload["treatments"] == {
        "POB #1": "LEGACY_RETROSPECTIVE",
        "POB #2": "LEGACY_RETROSPECTIVE",
        "POB #3": "LEGACY_RETROSPECTIVE",
        "VC #1": "LEGACY_RETROSPECTIVE",
    }
    assert {line["action"] for line in modifications[0].lines} == {"CHANGE"}
    added = golden_streams.stream("Contract 3", "13").contracts[0].modifications[-1]
    assert added.kind == "ADD_OBLIGATION"
    assert [line["obligation_key"] for line in added.lines if line["action"] == "ADD"] == ["POB #5"]


def test_step_04_events() -> None:
    stream = golden_streams.stream("Contract 1", "04")
    upload = [event for event in stream.events if event.effective_date == date(2023, 1, 31)]
    assert upload, "the 1.31.2023 upload emits events"

    def amounts(event_type: str, member: str) -> dict[str, object]:
        return {
            str(event.payload["obligation_key"]): event.payload[member]
            for event in upload
            if event.event_type == event_type
        }

    assert amounts("DELIVERY_RECORDED", "quantity") == {
        "POB #1": Decimal("2"),
        "POB #2": Decimal("1"),
        "POB #3": Decimal("0.5"),
    }
    assert amounts("BILLING_RECORDED", "amount") == {
        "POB #1": Decimal("100"),
        "POB #2": Decimal("100"),
        "POB #3": Decimal("100"),
    }
    assert amounts("PRE_STANDARD_REVENUE_RECORDED", "amount") == {
        "POB #2": Decimal("66"),
        "POB #3": Decimal("88"),
    }
    assert {event.origin for event in upload} == {"IMPORT"}
    assert all(str(event.idempotency_key).startswith("imp:") for event in upload)
    cb = s01_canonicalize.run(stream.input_bundle(), TraceBuilder(engine_version=ENGINE_VERSION))
    assert cb.findings == ()
    first = cb.ledger.at("Contract 1/POB %231")
    assert (first.delivered_cum, first.billed_cum) == (2, 100)
    third = cb.ledger.at("Contract 1/POB %233")
    assert (third.delivered_cum, third.billed_cum) == (Decimal("0.5"), 100)


def _snapshot(roots: Iterable[Path]) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file():
                stat = path.stat()
                found[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return found


def _outside_tmp(path: object) -> bool:
    try:
        Path(os.fsdecode(str(path))).resolve().relative_to(RUN_TMP.resolve())
    except ValueError:
        return True
    return False


def test_streams_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, str | int]] = []
    real_open: Callable[..., object] = builtins.open
    real_os_open = os.open

    def guarded_open(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        opened.append((str(file), mode))
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        opened.append((str(path), flags))
        return real_os_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    roots = (golden_streams.FIXTURE_ROOT, golden_streams.GOLDEN_ROOT)
    before = _snapshot(roots)
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    stream = golden_streams.stream("Contract 3", "14")
    monkeypatch.undo()
    assert stream.events
    assert _snapshot(roots) == before
    workbooks = [path for path, _ in opened if path.endswith(".xlsx")]
    assert len(workbooks) == 14, "every golden workbook is read once"
    for path, mode in opened:
        if isinstance(mode, str):
            writes = any(flag in mode for flag in "wax+")
        else:
            writes = bool(mode & WRITE_FLAGS)
        assert not writes or not _outside_tmp(path), f"{path} opened for writing ({mode!r})"
