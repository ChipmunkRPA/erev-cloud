"""LMG-3 migration reconciliation, the pure part (BUILD_SPEC LMG-3
``test_reconciliation_lines_wld_x_27`` figures,
``test_difference_without_deviation_raises_exception`` marking; 04 T-MIG-03; PRD BR-MIG-02,
WLD-X-27; D-17) and the GPB-3 point-in-time equivalence oracle (BUILD_SPEC GPB-3; dev-guide §9.6
kind ``point_in_time_equivalence``; DEVIATIONS OQ-D7; legacy 07 GT-20).

The eRev side of the WLD-X-27 lines is the golden step-04 replay output
(``docs/legacy/golden/04-…/contract_live.csv``, the harness rows the shipped database equals),
so the comparison logic is exercised on the real 24 × 71 oracle without a tenant. No database.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from erev_api.domain.migration import legacy_db, reconciliation
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.domain.migration.reconciliation import DeviationIndex
from erev_api.domain.reports.builders import migration_reconciliation as report
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
GOLDEN = ROOT / "docs/legacy/golden"
STEP_04 = GOLDEN / "04-delivery-billing-2023-01-31/contract_live.csv"
STEP_14 = GOLDEN / "14-full-delivery-2023-10-31/contract_live.csv"
HARNESS_DIFFS = GOLDEN / "compare-shipped/point_in_time_column_diffs.csv"
C1_POB1_ALLOCATION = ("Contract 1", "POB #1", "ALLOCATION")


def _latest() -> tuple[LegacyRow, ...]:
    return legacy_db.latest_rows(legacy_db.rows(FIXTURE))


def _csv_rows(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value if value != "" else None) for key, value in record.items()}
            for record in csv.DictReader(handle)
        ]


def _near(value: Fraction, expected: str) -> bool:
    return abs(value - Fraction(Decimal(expected))) <= Fraction(1, 200)  # to the cent shown


def test_reconciliation_lines_wld_x_27() -> None:
    # WLD-X-27: TP C1 1,300 / C2 900 / C3 1,300 / C4 950; revenue C1 295.69, C2 58.85; billed C1
    # 300, C2 0; differences above tolerance 0; unexplained 0 when eRev reproduces the legacy
    # values.
    source = reconciliation.legacy_values(_latest())
    tp = {
        c: source[(c, None, "TRANSACTION_PRICE")]
        for c in ("Contract 1", "Contract 2", "Contract 3", "Contract 4")
    }
    assert all(
        abs(tp[c] - Fraction(expected)) <= reconciliation.TOLERANCE
        for c, expected in (
            ("Contract 1", 1300),
            ("Contract 2", 900),
            ("Contract 3", 1300),
            ("Contract 4", 950),
        )
    )
    assert _near(source[("Contract 1", None, "REVENUE_CUM")], "295.69")
    assert _near(source[("Contract 2", None, "REVENUE_CUM")], "58.85")
    assert source[("Contract 1", None, "BILLED_CUM")] == 300
    assert source[("Contract 2", None, "BILLED_CUM")] == 0
    assert source[("Contract 1", None, "POB_COUNT")] == 4
    assert source[("Contract 2", None, "POB_COUNT")] == 3  # the VC row is not an obligation
    assert _near(source[("Contract 2", None, "RECLASS")], "58.85")
    assert len(source) == 4 * len(reconciliation.CONTRACT_MEASURES) + 16 * len(
        reconciliation.OBLIGATION_MEASURES
    )
    lines = reconciliation.lines(source, source)
    totals = reconciliation.control_totals(lines)
    assert (
        totals.line_count,
        totals.differences_above_tolerance,
        totals.explained,
        totals.unexplained,
    ) == (136, 0, 0, 0)  # 4 × 6 contract measures + 16 × 7 obligation measures (rev 1.35)
    assert reconciliation.tie_out_result(totals) == {
        "code": "TO_MIGRATION_UNEXPLAINED_ZERO",
        "result": "PASS",
        "expected": 0,
        "actual": 0,
    }
    assert lines[0].row_key == "line:Contract 1::BILLED_CUM"


def test_difference_without_deviation_needs_an_exception() -> None:
    source = reconciliation.legacy_values(_latest())
    erev = dict(source)
    erev[C1_POB1_ALLOCATION] = source[C1_POB1_ALLOCATION] + Fraction(1, 1000)
    lines = reconciliation.lines(source, erev)
    (line,) = [item for item in lines if not item.is_within_tolerance]
    assert (line.contract_external_id, line.obligation_key, line.measure) == C1_POB1_ALLOCATION
    assert (
        line.difference == Fraction(1, 1000) and line.deviation_ref is None and line.needs_exception
    )
    totals = reconciliation.control_totals(lines)
    assert (totals.differences_above_tolerance, totals.explained, totals.unexplained) == (1, 0, 1)
    assert reconciliation.tie_out_result(totals)["result"] == "FAIL"
    # within tolerance: 0.00005 is not a difference
    erev[C1_POB1_ALLOCATION] = source[C1_POB1_ALLOCATION] + Fraction(1, 20000)
    assert (
        reconciliation.control_totals(
            reconciliation.lines(source, erev)
        ).differences_above_tolerance
        == 0
    )


def test_difference_with_deviation_reference_is_explained() -> None:
    source = reconciliation.legacy_values(_latest())
    erev = dict(source)
    erev[C1_POB1_ALLOCATION] = source[C1_POB1_ALLOCATION] + 1
    # a documented applicable difference: legacy value → corrected value (+1) for this key
    documented = reconciliation.Deviation(
        "DEV-052", source[C1_POB1_ALLOCATION], source[C1_POB1_ALLOCATION] + 1
    )
    index = DeviationIndex({C1_POB1_ALLOCATION: documented})
    lines = reconciliation.lines(source, erev, index)
    (line,) = [item for item in lines if not item.is_within_tolerance]
    assert line.deviation_ref == "DEV-052" and not line.needs_exception
    totals = reconciliation.control_totals(lines)
    assert (totals.explained, totals.unexplained) == (1, 0)
    assert reconciliation.tie_out_result(totals)["result"] == "PASS"


def test_value_missing_on_one_side_is_a_whole_difference() -> None:
    source = reconciliation.legacy_values(_latest())
    erev = {key: value for key, value in source.items() if key != C1_POB1_ALLOCATION}
    lines = reconciliation.lines(source, erev)
    (line,) = [item for item in lines if not item.is_within_tolerance]
    assert line.erev_value == 0 and line.source_value == source[C1_POB1_ALLOCATION]
    assert len(lines) == len(source)


def test_deviation_index_from_the_golden_documents() -> None:
    # Codex R1 (PRODUCTION-F-LMG-SLICE1-INDEPENDENT-ed5173f, D-98 candidate 44) and the Q-4 ruling
    # (D-98 candidate 48; 04 rev 1.35): DEV-052 (DEVIATIONS §7.2) documents `Original allocation`
    # null → 1,268.1139 on Contract 3 POB #5 — the ORIGINAL_ALLOCATION measure, its own line — while
    # the final allocation (`Final allocation (rev cum + remaining)`, the ALLOCATION measure) is
    # 1,268.1139 on both sides and stays unexplained by DEV-052.
    index = DeviationIndex.from_golden(GOLDEN / "golden-tests.json", GOLDEN / "deviations.json")
    documented = reconciliation.Deviation(
        "DEV-052", Fraction(0), Fraction(Decimal("1268.1139")), Fraction(1, 10000)
    )
    assert dict(index.refs) == {("Contract 3", "POB #5", "ORIGINAL_ALLOCATION"): documented}
    assert index.lookup("Contract 3", "POB #5", "ALLOCATION") is None
    # only a golden field that IS a T-MIG-03 measure maps (dev-guide §9.6 kind sources)
    assert reconciliation.FIELD_MEASURES["Original allocation"] == "ORIGINAL_ALLOCATION"
    assert "Remaining allocation" not in reconciliation.FIELD_MEASURES
    assert reconciliation.FIELD_MEASURES["Final allocation (rev cum + remaining)"] == "ALLOCATION"
    # ruling Q-3 follow-up: the index records the digests of the documents it was built from
    digests = {
        name: hashlib.sha256((GOLDEN / name).read_bytes()).hexdigest()
        for name in ("golden-tests.json", "deviations.json")
    }
    assert dict(index.source_digests) == digests
    # since 04 rev 1.35 every documented B-case difference is a measure: nothing is unmeasured
    assert dict(index.unmeasured) == {}


def test_deviation_reference_binds_to_the_documented_difference() -> None:
    # Codex R1 counterexamples, exact inputs: the index built from the golden documents, source
    # 1,268.1139 and eRev 1,368.1139 / 1,168.1139 on (Contract 3, POB #5, ALLOCATION) — on ed5173f
    # both were explained by DEV-052 with tie-out PASS; they must be unexplained and FAIL.
    index = DeviationIndex.from_golden(GOLDEN / "golden-tests.json", GOLDEN / "deviations.json")
    key = ("Contract 3", "POB #5", "ALLOCATION")
    correct = Fraction(Decimal("1268.1139"))
    for delta in (Fraction(100), Fraction(-100)):
        (line,) = reconciliation.lines({key: correct}, {key: correct + delta}, index)
        totals = reconciliation.control_totals((line,))
        assert line.needs_exception and line.deviation_ref is None, delta
        assert reconciliation.tie_out_result(totals)["result"] == "FAIL", delta
    # controls kept: an unchanged final allocation passes; no index → FAIL; the reference does not
    # leak to another POB
    same = reconciliation.lines({key: correct}, {key: correct}, index)
    assert reconciliation.tie_out_result(reconciliation.control_totals(same))["result"] == "PASS"
    bare = reconciliation.lines({key: correct}, {key: correct + 100})
    assert reconciliation.tie_out_result(reconciliation.control_totals(bare))["result"] == "FAIL"
    other = ("Contract 3", "POB #6", "ALLOCATION")
    assert reconciliation.lines({other: correct}, {other: correct + 100}, index)[0].needs_exception
    # the LMG-4 creation-time line (PRD J-21.3): legacy NULL (0) → eRev 1,268.1139 on
    # ORIGINAL_ALLOCATION is explained by DEV-052; any other value on that line is not
    original = ("Contract 3", "POB #5", "ORIGINAL_ALLOCATION")
    (creation,) = reconciliation.lines({original: Fraction(0)}, {original: correct}, index)
    assert creation.deviation_ref == "DEV-052" and not creation.needs_exception
    (drift,) = reconciliation.lines({original: Fraction(0)}, {original: correct + 100}, index)
    assert drift.needs_exception
    # binding: a documented (legacy, corrected) pair explains exactly that pair — equality as
    # DG-PAR-07 defines it for a documented value (within the entry's own tolerance 0.0001, not
    # the caller's line tolerance)
    documented = DeviationIndex({key: reconciliation.Deviation("DEV-999", correct, correct + 100)})

    def _one(source: Fraction, erev: Fraction) -> reconciliation.Line:
        (line,) = reconciliation.lines({key: source}, {key: erev}, documented)
        return line

    assert _one(correct, correct + 100).deviation_ref == "DEV-999"
    assert _one(correct, correct + 100 + Fraction(1, 20000)).deviation_ref == "DEV-999"
    assert _one(correct, correct + 50).needs_exception
    assert _one(correct, correct - 100).needs_exception
    assert _one(correct + 1, correct + 101).needs_exception  # the source is not the documented one
    # the caller's tolerance widens no pair: a wide line tolerance still refuses +50
    wide = reconciliation.lines(
        {key: correct}, {key: correct + 50}, documented, tolerance=Fraction(1)
    )
    assert wide[0].needs_exception


def test_point_in_time_equivalence_shipped_against_golden_step_04() -> None:
    # GPB-3 oracle (GT-20): 24 rows, 69 compared columns, no column with a mismatch; the per-column
    # classification equals the harness's compare-shipped/point_in_time_column_diffs.csv; the two
    # excluded columns and the synthetic __rows__ column are reported, never compared.
    schema = legacy_db.schema(FIXTURE)
    legacy = legacy_db.load_legacy_rows(FIXTURE)
    result = reconciliation.compare_point_in_time(legacy, _csv_rows(STEP_04), schema=schema)
    assert (result.rows, result.legacy_rows, result.erev_rows) == (24, 24, 24)
    assert result.columns_with_mismatch == ()
    assert result.unmatched_legacy == () and result.unmatched_erev == ()
    compared = [
        c for c in result.columns.values() if c.status != "excluded" and c.column != "__rows__"
    ]
    assert len(compared) == 69
    assert Counter(c.kind for c in compared) == {"numeric": 54, "text": 15}
    assert {c.column for c in result.columns.values() if c.status == "excluded"} == {
        "Processing Time Log",
        "Record Unique ID",
    }
    assert result.columns["__rows__"].status == "match"
    harness = {record["column"]: record["status"] for record in _csv_rows(HARNESS_DIFFS)}
    assert {c.column: c.kind for c in compared} == harness
    assert all(c.mismatch_count == 0 and c.status == "match" for c in compared)
    assert max(c.max_abs_diff for c in compared if c.max_abs_diff is not None) == 0
    as_json = result.to_json()
    assert as_json["rows"] == 24 and as_json["columns_with_mismatch"] == []
    assert [row["column"] for row in as_json["columns"]] == list(harness)
    assert {row["status"] for row in as_json["columns"]} == {"numeric", "text"}
    assert all(row["mismatches"] == 0 for row in as_json["columns"])
    # without a schema the numeric columns are recognised by parsing both sides (the harness rule)
    inferred = reconciliation.compare_point_in_time(legacy, _csv_rows(STEP_04))
    assert inferred.columns_with_mismatch == () and inferred.rows == 24
    assert {
        c.column: c.kind
        for c in inferred.columns.values()
        if c.status != "excluded" and c.column != "__rows__"
    } == harness


@pytest.mark.parametrize(
    ("column", "delta", "flagged"),
    [
        ("Original Allocation", Fraction(1, 1000), True),
        ("Original Allocation", Fraction(1, 20000), False),
        ("Current Rev Rec - Cumulative", Fraction(1, 10000), False),
        ("Current Rev Rec - Cumulative", Fraction(10001, 100000000), True),
    ],
)
def test_point_in_time_numeric_tolerance(column: str, delta: Fraction, flagged: bool) -> None:
    schema = legacy_db.schema(FIXTURE)
    legacy = legacy_db.load_legacy_rows(FIXTURE)
    erev = _csv_rows(STEP_04)
    target = next(row for row in erev if row[column] not in (None, "0", "0.0"))
    target[column] = str(
        Decimal(str(target[column])) + Decimal(delta.numerator) / Decimal(delta.denominator)
    )
    result = reconciliation.compare_point_in_time(legacy, erev, schema=schema)
    assert (column in result.columns_with_mismatch) is flagged
    status = result.columns[column]
    assert status.mismatch_count == (1 if flagged else 0)
    assert status.max_abs_diff == delta
    if flagged:
        (mismatch,) = status.mismatches
        assert (
            mismatch.diff == delta
            and mismatch.row_key.split(":", 1)[1] == target["Record Unique ID without time"]
        )
        assert isinstance(mismatch.diff, Fraction)


def test_point_in_time_text_row_and_exclusion_rules() -> None:
    schema = legacy_db.schema(FIXTURE)
    legacy = legacy_db.load_legacy_rows(FIXTURE)
    # a text change is a mismatch, exactly, with both values reported
    erev = _csv_rows(STEP_04)
    erev[0]["Selling Entity"] = "Mock Entity 9"
    result = reconciliation.compare_point_in_time(legacy, erev, schema=schema)
    assert result.columns_with_mismatch == ("Selling Entity",)
    (mismatch,) = result.columns["Selling Entity"].mismatches
    assert (mismatch.legacy, mismatch.erev, mismatch.diff) == (
        "Mock Entity 1",
        "Mock Entity 9",
        None,
    )
    # the excluded columns are never compared
    erev = _csv_rows(STEP_04)
    for row in erev:
        row["Record Unique ID"] = "changed"
    assert (
        reconciliation.compare_point_in_time(legacy, erev, schema=schema).columns_with_mismatch
        == ()
    )
    # a missing eRev row leaves 23 aligned rows and surfaces as a __rows__ mismatch
    erev = _csv_rows(STEP_04)[1:]
    result = reconciliation.compare_point_in_time(legacy, erev, schema=schema)
    assert (result.rows, result.erev_rows, len(result.unmatched_legacy)) == (23, 23, 1)
    assert result.columns_with_mismatch == ("__rows__",)
    assert result.columns["__rows__"].mismatches[0].erev is None
    # a column absent from every eRev row is reported, not silently skipped
    erev = [
        {key: value for key, value in row.items() if key != "Memo 3"} for row in _csv_rows(STEP_04)
    ]
    result = reconciliation.compare_point_in_time(legacy, erev, schema=schema)
    assert (
        result.columns["Memo 3"].mismatch_count == 24 and "Memo 3" in result.columns_with_mismatch
    )


def test_tol_1_documented_pair_matching_boundary() -> None:
    # F-LMG-TOL-1 (record §17): the rule as implemented — each side is compared with the entry's own
    # tolerance (0.0001; DG-PAR-07 equality for a documented value), never with the line's. A
    # documented 100 → 200 therefore explains 100.0001 → 199.9999 (the difference then differs from
    # the documented one by 0.0002) and not 100.0002 → 199.9999; stated, not widened.
    key = ("Contract 9", "POB #1", "REVENUE_CUM")
    index = DeviationIndex({key: reconciliation.Deviation("DEV-TOL", Fraction(100), Fraction(200))})

    def explained(source: str, erev: str, tolerance: Fraction = reconciliation.TOLERANCE) -> bool:
        (line,) = reconciliation.lines(
            {key: Fraction(Decimal(source))},
            {key: Fraction(Decimal(erev))},
            index,
            tolerance=tolerance,
        )
        return line.deviation_ref == "DEV-TOL" and not line.needs_exception

    assert explained("100", "200")
    assert explained("100.0001", "199.9999")
    assert explained("99.9999", "200.0001")
    assert not explained("100.0002", "199.9999")
    assert not explained("100", "200.0002")
    assert not explained("100", "150")
    # the line tolerance neither widens nor narrows the documented match
    assert explained("100.0001", "199.9999", tolerance=Fraction(0))
    assert not explained("100.0002", "199.9999", tolerance=Fraction(1))


def _step_14_rows() -> tuple[LegacyRow, ...]:
    with STEP_14.open(newline="", encoding="utf-8") as handle:
        return tuple(
            LegacyRow(index, {k: (v if v != "" else None) for k, v in record.items()})
            for index, record in enumerate(csv.DictReader(handle), start=1)
        )


def test_creation_time_allocation_line_renders_under_its_measure() -> None:
    # LMG-4 / PRD J-21.3 (WLD-X-28) through the pure path, with a SUPPLIED eRev value: over the
    # after-step-14 legacy rows the source ORIGINAL_ALLOCATION of Contract 3 POB #5 is 0 (legacy
    # stores NULL, DEV-052); the eRev side is set here to 1,268.1139 — the golden pob_position
    # expected value, standing in for obligation_version.original_allocated_exact, which no engine
    # run, stored row or replay produces in this test. Proven: the reconciliation and RPT-41
    # rendering of that supplied pair (explained by DEV-052 under ORIGINAL_ALLOCATION, tie-out
    # PASS, "Original allocation" row); not proven: eRev value extraction, a full-population replay.
    latest = legacy_db.latest_rows(_step_14_rows())
    source = reconciliation.legacy_values(latest)
    key = ("Contract 3", "POB #5", "ORIGINAL_ALLOCATION")
    assert source[key] == 0
    erev = dict(source)
    erev[key] = Fraction(Decimal("1268.1139"))
    index = DeviationIndex.from_golden(GOLDEN / "golden-tests.json", GOLDEN / "deviations.json")
    lines = reconciliation.lines(source, erev, index)
    (line,) = [item for item in lines if not item.is_within_tolerance]
    assert (line.contract_external_id, line.obligation_key, line.measure) == key
    assert line.deviation_ref == "DEV-052" and not line.needs_exception
    totals = reconciliation.control_totals(lines)
    assert (totals.differences_above_tolerance, totals.explained, totals.unexplained) == (1, 1, 0)
    assert reconciliation.tie_out_result(totals)["result"] == "PASS"
    data = report.report_data(lines, only_differences=True)
    (row,) = data.rows
    assert row["row_key"] == "line:Contract 3:POB #5:ORIGINAL_ALLOCATION"
    assert (row["measure"], row["source_value"], row["erev_value"], row["deviation_ref"]) == (
        "Original allocation",
        "0",
        "1268.1139",
        "DEV-052",
    )
    assert row["is_within_tolerance"] == "No" and row["exception_item_id"] is None
    assert data.tie_out_results[0]["result"] == "PASS"


def test_row_key_is_injective_and_marks_the_contract_level_by_an_empty_component() -> None:
    # Codex RPT41-ID-1 (SCREENS_B rev 1.13): (C1, null, REVENUE_CUM) and (C1, "contract",
    # REVENUE_CUM) are distinct rows with distinct keys; (C:A, P1) and (C, A:P1) too — components
    # are percent-encoded (% → %25, then : → %3A) and the contract level is the empty component.
    def line(
        contract: str, obligation: str | None, measure: str = "REVENUE_CUM"
    ) -> reconciliation.Line:
        (found,) = reconciliation.lines({(contract, obligation, measure): Fraction(1)}, {})
        return found

    assert line("C1", None).row_key == "line:C1::REVENUE_CUM"
    assert line("C1", "contract").row_key == "line:C1:contract:REVENUE_CUM"
    assert line("C:A", "P1").row_key == "line:C%3AA:P1:REVENUE_CUM"
    assert line("C", "A:P1").row_key == "line:C:A%3AP1:REVENUE_CUM"
    assert line("C%3AA", "P1").row_key == "line:C%253AA:P1:REVENUE_CUM"  # % escaped first
    keys = {
        line(c, o).row_key
        for c, o in (
            ("C1", None),
            ("C1", "contract"),
            ("C:A", "P1"),
            ("C", "A:P1"),
            ("C%3AA", "P1"),
        )
    }
    assert len(keys) == 5
    assert line("C1", None).key == ("C1", None, "REVENUE_CUM")
    assert reconciliation.encode_key_component("a%b:c") == "a%25b%3Ac"
    # Codex packet 1006 completion: an empty-string obligation key (not a legitimate key) encodes as
    # `%`, which no encoded component can otherwise produce — never the contract level's empty
    # component
    assert line("C1", "").row_key == "line:C1:%:REVENUE_CUM"
    assert line("C1", "").row_key != line("C1", None).row_key
    assert (
        line("C1", "%").row_key == "line:C1:%25:REVENUE_CUM"
    )  # a literal % stays distinct from the marker
