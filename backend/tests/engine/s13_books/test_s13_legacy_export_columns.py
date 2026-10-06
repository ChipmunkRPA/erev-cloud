"""D-98 candidates 88 and 90 (supervisor rulings of 2026-09-20; lane ENG-T1F slice T1F-2): the
legacy step-04 export columns eRev never produced, measured against the shipped legacy database
``backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db`` (read-only; DG-LAY-11) for Contracts 1
and 2 at setup (golden step 02, 2023-01-01) and after the 2023-01-31 deliveries (golden step 04).

- 88 (a): ``obligation_version.memo_1..3`` pass through unchanged — the setup line's memos, then the
  memos of the latest ``MEMO_UPDATED`` event on or before the version date (a progress upload writes
  "Delivery 1 01.31.23" for the delivered rows and keeps "Initial setup 1" for the others).
- 88 (b): ``original_unit_revenue_rate`` = x_p ÷ Q (S05-R-16) and ``remaining_unit_revenue_rate`` =
  exact remaining allocation ÷ remaining quantity (legacy 01 §3.6 / §3.7), exact from the trace;
  the shipped values are legacy float64 (64.42021803766104), so the comparison tolerates 1e-9.
- 90: the export's ``Current Remaining SSP`` follows the legacy per-delivery definition (remaining
  quantity × unit SSP = remaining SSP − Σ deliveries × unit SSP) as a DERIVED export value — 300 /
  184
  / 75 / 535.5 for the four delivered POBs — while ``obligation_version.remaining_ssp`` (allocation
  semantics, re-based at stage-06 boundaries only) is unchanged (500 / 368 / 150 / 612).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from erev_api.domain.migration import legacy_db
from erev_api.domain.reports import legacy_columns
from erev_engine import compute
from support import golden_streams, intent_totals

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "legacy_db" / "ASC606-shipped-step04.db"
)
TOLERANCE = Fraction(1, 10**9)
CASES = (
    ("Contract 1", "02", date(2023, 1, 1)),
    ("Contract 1", "04", date(2023, 1, 31)),
    ("Contract 2", "02", date(2023, 1, 1)),
    ("Contract 2", "04", date(2023, 1, 31)),
)
MANIFEST = FIXTURE.parents[1] / "manifest.json"


def _legacy_rows() -> dict[tuple[str, str, date], Mapping[str, str | None]]:
    """The shipped ``Contract_Live`` rows through the product's read-only legacy reader
    (``erev_api.domain.migration.legacy_db``, DG-LAY-11), keyed by contract, POB and period, after
    checking the fixture's digest against ``backend/tests/fixtures/manifest.json``."""
    pinned = next(
        item["sha256"]
        for item in json.loads(MANIFEST.read_text())
        if item["path"] == "legacy_db/ASC606-shipped-step04.db"
    )
    assert legacy_db.file_sha256(FIXTURE) == pinned
    found: dict[tuple[str, str, date], Mapping[str, str | None]] = {}
    for row in legacy_db.load_legacy_rows(FIXTURE):
        period = date.fromisoformat(str(row["Current Period"])[:10])
        found[(str(row["Contract Unique Name"]), str(row["POB Unique ID"]), period)] = row
    return found


def _versions(contract: str, step: str) -> dict[str, object]:
    stream = golden_streams.stream(contract, step)
    bundle = intent_totals.activated(stream.input_bundle(preset="LEGACY_PARITY", books=("ASC606",)))
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    return {str(item.columns["obligation_key"]): item for item in book.obligation_versions}


def _export_column(name: str) -> legacy_columns.LegacyColumn:
    for value in vars(legacy_columns).values():
        if isinstance(value, tuple) and value and isinstance(value[0], legacy_columns.LegacyColumn):
            return next(column for column in value if column.name == name)
    raise AssertionError("legacy_columns exposes no LegacyColumn tuple")


def _close(actual: object, legacy: object) -> bool:
    if actual is None or legacy is None:
        return actual is None and legacy is None
    return abs(Fraction(actual) - Fraction(Decimal(str(legacy)))) <= TOLERANCE  # type: ignore[arg-type]


@pytest.mark.parametrize(("contract", "step", "period"), CASES, ids=lambda v: str(v))
def test_legacy_export_columns_equal_the_shipped_step_04_rows(
    contract: str, step: str, period: date
) -> None:
    legacy = _legacy_rows()
    versions = _versions(contract, step)
    remaining_ssp_export = _export_column("Current Remaining SSP")
    defects: list[tuple[object, ...]] = []
    for obligation_key, version in sorted(versions.items()):
        row = legacy[(contract, obligation_key, period)]
        columns = version.columns
        where = (contract, step, obligation_key)
        # 88 (a): memos pass through.
        memos = (columns.get("memo_1"), columns.get("memo_2"), columns.get("memo_3"))
        expected_memos = (row["Memo 1"], row["Memo 2"], row["Memo 3"])
        if memos != expected_memos:
            defects.append((*where, "memo_1..3", memos, expected_memos))
        # 88 (b): unit revenue rates, exact against legacy float64 (VC lines: 0 in legacy).
        for column, name in (
            ("original_unit_revenue_rate", "Original Unit Rev Rec"),
            ("remaining_unit_revenue_rate", "Current Remaining Unit Rev Rec"),
        ):
            if not _close(columns.get(column), row[name]):
                defects.append((*where, column, columns.get(column), row[name]))
        # 90: the export's Current Remaining SSP follows the per-delivery definition; the stored
        # allocation column keeps the extended SSP at the last boundary (setup: both equal).
        exported = remaining_ssp_export.value(dict(columns), None)
        if exported != legacy_columns.decimal_text(row["Current Remaining SSP"]):
            defects.append(
                (*where, "export Current Remaining SSP", exported, row["Current Remaining SSP"])
            )
        if not _close(columns["remaining_ssp"], row["Original Extended SSP"]):
            defects.append(
                (*where, "remaining_ssp", columns["remaining_ssp"], row["Original Extended SSP"])
            )
    assert len(versions) >= 3
    assert defects == []
