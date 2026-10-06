"""GPB-3 reader support (docs/dev-guide.md §9.6 kind row ``point_in_time_equivalence``, DG-PAR-07,
DG-PAR-09; BUILD_SPEC GPB-3; DEVIATIONS OQ-D7): the pure parts of ``support.parity.equivalence``
on the shipped database, without a tenant or a database.

The eRev stand-in of the comparison tests is the golden step-04 harness output
(``docs/legacy/golden/04-…/contract_live.csv``), the rows the shipped database equals (the same
stand-in F-LMG's ``test_reconciliation.py`` uses), so the reader's translation of the F-LMG result
into DG-PAR-08 mismatches is exercised on the real 24 × 71 oracle. Each seeded mutation reintroduces
one defect (a moved cell, a lost row, an extra row, an envelope key, a shifted plan date, a foreign
digest) and asserts the exact failure it must produce; the controls assert that a difference inside
the tolerance and the intact inputs produce none (fail-first evidence, T1 record). GPB-3.1 (Codex
source review of 7605b060): the run's ``row_count`` metadata check (S1), the tenant-wide import
check against the plan (S2) and the exact expected-object members (S3), each with its fail-first
cases.
"""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from erev_api.domain.migration import legacy_db, reconciliation, replay
from support import golden_streams
from support.parity import equivalence
from support.parity.equivalence import EquivalenceInputError

ROOT = Path(__file__).resolve().parents[4]
GOLDEN = ROOT / "docs" / "legacy" / "golden"
STEP_04 = GOLDEN / "04-delivery-billing-2023-01-31" / "contract_live.csv"
EXPECTED = {"rows": 24, "columns_with_mismatch": []}  # deviations.json shipped-db-equivalence
SHIPPED_STEPS = ("01", "02", "03", "04")
UPLOADS = (
    ("legacy_sku_ssp", None, None),
    ("legacy_contract_setup", None, None),
    ("legacy_contract_setup", None, None),
    ("legacy_progress_tracking", None, date(2023, 1, 31)),
)
ALLOCATION = "Original Allocation"
REVENUE_CUM = "Current Rev Rec - Cumulative"
SKU = "SKU Name"
ROWS = reconciliation.ROWS_COLUMN


def _csv_rows(path: Path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value if value != "" else None) for key, value in record.items()}
            for record in csv.DictReader(handle)
        ]


@pytest.fixture(scope="module")
def legacy() -> equivalence.LegacySide:
    return equivalence.legacy_side("04")


@pytest.fixture(scope="module")
def erev_rows() -> list[dict[str, str | None]]:
    return _csv_rows(STEP_04)


def _shift(rows: list[dict[str, str | None]], index: int, column: str, delta: str) -> None:
    value = rows[index][column]
    assert value is not None
    rows[index][column] = str(Decimal(value) + Decimal(delta))


def _fields(found: list) -> list[str]:
    return [item.field for item in found]


# --- legacy side and the prescribed plan ----------------------------------------------------------


def test_legacy_side_reads_the_pinned_shipped_database(legacy: equivalence.LegacySide) -> None:
    manifest = json.loads(equivalence.MANIFEST.read_text(encoding="utf-8"))
    pinned = next(
        e["sha256"] for e in manifest if e["path"] == "legacy_db/ASC606-shipped-step04.db"
    )
    assert legacy.source_sha256 == pinned == equivalence.manifest_sha256()
    assert len(legacy.schema) == 71
    assert sum(column.is_numeric for column in legacy.schema) == 54
    assert len(legacy.rows) == 24
    assert (legacy.profile.contract_live_rows, legacy.profile.sku_ssp_rows) == (24, 7)
    assert len(legacy.profile.version_tokens) == 3
    # J-20-AC-2: reading the source never changes it
    assert legacy_db.file_sha256(equivalence.FIXTURE) == pinned


def test_prescribed_plan_is_the_four_golden_uploads(legacy: equivalence.LegacySide) -> None:
    steps = golden_streams.steps("04")
    assert [item.step for item in legacy.plan] == list(SHIPPED_STEPS)
    assert [item.order for item in legacy.plan] == [1, 2, 3, 4]
    for item, step, (template_code, mode, day) in zip(legacy.plan, steps, UPLOADS, strict=True):
        assert item.parameters == replay.UploadParameters(
            template_code=template_code,
            mode=mode,
            date_input=day,
            file_sha256=step.file_sha256.lower(),
        )
        assert item.file_name == step.workbook.name
        assert replay.infer_template(step.workbook.name) == (template_code, mode)


def test_window_spans_the_legacy_periods(legacy: equivalence.LegacySide) -> None:
    assert equivalence.window_of(legacy.rows) == (date(2023, 1, 1), date(2023, 12, 31))
    with pytest.raises(EquivalenceInputError):
        equivalence.window_of([{legacy_db.CURRENT_PERIOD: None}])


def test_plan_refuses_a_shifted_date(legacy: equivalence.LegacySide) -> None:
    # mutation: the dated upload carries 2023-02-28 while the reference version is 2023-01-31
    steps = list(golden_streams.steps("04"))
    steps[3] = replace(steps[3], date_input=date(2023, 2, 28))
    with pytest.raises(EquivalenceInputError, match=r"plan\[3\]\.effective_date"):
        equivalence.prescribed_plan(legacy.profile, legacy_db.rows(equivalence.FIXTURE), steps)


def test_plan_refuses_a_missing_or_extra_step(legacy: equivalence.LegacySide) -> None:
    rows = legacy_db.rows(equivalence.FIXTURE)
    with pytest.raises(EquivalenceInputError, match="Add 4 files in order"):
        equivalence.prescribed_plan(legacy.profile, rows, golden_streams.steps("03"))
    with pytest.raises(EquivalenceInputError, match="Add 4 files in order"):
        equivalence.prescribed_plan(legacy.profile, rows, golden_streams.steps("05"))


def test_plan_refuses_a_handler_that_disagrees_with_the_file_name(
    legacy: equivalence.LegacySide,
) -> None:
    steps = list(golden_streams.steps("04"))
    steps[1] = replace(steps[1], template_code="legacy_progress_tracking")
    with pytest.raises(EquivalenceInputError, match="infer_template"):
        equivalence.prescribed_plan(legacy.profile, legacy_db.rows(equivalence.FIXTURE), steps)


def test_plan_refuses_a_foreign_workbook_digest(legacy: equivalence.LegacySide) -> None:
    steps = list(golden_streams.steps("04"))
    steps[0] = replace(steps[0], file_sha256="0" * 64)
    with pytest.raises(EquivalenceInputError, match="step.json pins"):
        equivalence.prescribed_plan(legacy.profile, legacy_db.rows(equivalence.FIXTURE), steps)


def test_legacy_side_refuses_an_unpinned_fixture(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    fixture = tmp_path / "legacy_db" / "ASC606-shipped-step04.db"
    fixture.parent.mkdir()
    fixture.write_bytes(equivalence.FIXTURE.read_bytes())
    manifest.write_text(
        json.dumps([{"path": "legacy_db/ASC606-shipped-step04.db", "sha256": "f" * 64}]),
        encoding="utf-8",
    )
    with pytest.raises(EquivalenceInputError, match="manifest pins"):
        equivalence.legacy_side("04", fixture=fixture, manifest=manifest)
    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(EquivalenceInputError, match="lists no entry"):
        equivalence.legacy_side("04", fixture=fixture, manifest=manifest)
    with pytest.raises(EquivalenceInputError, match="missing"):
        equivalence.legacy_side("04", fixture=tmp_path / "absent.db", manifest=manifest)


# --- export shape ---------------------------------------------------------------------------------


def test_project_rows_keeps_the_71_legacy_columns(erev_rows: list[dict[str, str | None]]) -> None:
    exported = [{"row_key": f"version:x:{i}", **row} for i, row in enumerate(erev_rows)]
    projected = equivalence.project_rows(exported)
    assert len(projected) == 24 and all(len(row) == 71 for row in projected)
    assert all("row_key" not in row for row in projected)
    with pytest.raises(EquivalenceInputError, match="extra \\['section'\\]"):
        equivalence.project_rows([{**exported[0], "section": "x"}])
    short = dict(exported[0])
    del short[SKU]
    with pytest.raises(EquivalenceInputError, match=f"missing \\['{SKU}'\\]"):
        equivalence.project_rows([short])


# --- comparison and DG-PAR-08 mismatches ---------------------------------------------------------


def _compare(
    legacy: equivalence.LegacySide, erev: list[dict[str, str | None]]
) -> reconciliation.EquivalenceResult:
    return reconciliation.compare_point_in_time(legacy.rows, erev, schema=legacy.schema)


def test_intact_inputs_match_the_expected_object(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    result = _compare(legacy, erev_rows)
    assert (result.rows, result.columns_with_mismatch) == (24, ())
    assert equivalence.mismatches(EXPECTED, result) == []


def test_a_difference_inside_the_tolerance_is_no_mismatch(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    rows = [dict(row) for row in erev_rows]
    _shift(rows, 0, ALLOCATION, "0.00005")  # control: within 1/10000
    assert equivalence.mismatches(EXPECTED, _compare(legacy, rows)) == []


def test_a_moved_numeric_cell_fails_the_case(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    rows = [dict(row) for row in erev_rows]
    _shift(rows, 0, ALLOCATION, "0.001")  # mutation: one allocation off by 0.001
    found = equivalence.mismatches(EXPECTED, _compare(legacy, rows))
    assert _fields(found) == ["columns_with_mismatch", f"columns[{ALLOCATION}]"]
    assert found[0].actual == [ALLOCATION] and found[0].expected == []
    detail = found[1].actual
    assert (detail["kind"], detail["mismatches"]) == ("numeric", 1)
    assert detail["max_abs_diff"] == "1/1000"
    assert detail["first"][0]["row_key"].endswith(":" + str(rows[0][legacy_db.RECORD_KEY]))


def test_a_changed_text_cell_fails_the_case(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    rows = [dict(row) for row in erev_rows]
    rows[5][SKU] = "Hardware 1 "  # mutation: trailing space in a text column
    found = equivalence.mismatches(EXPECTED, _compare(legacy, rows))
    assert _fields(found) == ["columns_with_mismatch", f"columns[{SKU}]"]
    assert found[1].actual["kind"] == "text" and found[1].actual["max_abs_diff"] is None


def test_a_lost_or_extra_row_fails_the_rows_assertion(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    lost = [dict(row) for row in erev_rows[1:]]  # mutation: the replay lost one row
    found = equivalence.mismatches(EXPECTED, _compare(legacy, lost))
    assert _fields(found) == ["rows", "columns_with_mismatch", f"columns[{ROWS}]"]
    assert (found[0].actual, found[1].actual) == (23, [ROWS])
    extra = [dict(row) for row in erev_rows]
    extra.append({**extra[0], legacy_db.RECORD_KEY: "Contract 9 POB #1 Hardware 1"})
    found = equivalence.mismatches(EXPECTED, _compare(legacy, extra))
    assert _fields(found) == ["columns_with_mismatch", f"columns[{ROWS}]"]
    assert found[1].actual["first"][0]["legacy"] is None


def test_the_envelope_key_would_be_a_column_without_the_projection(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    exported = [{"row_key": f"version:x:{i}", **row} for i, row in enumerate(erev_rows)]
    unprojected = reconciliation.compare_point_in_time(legacy.rows, exported)  # no schema
    assert "row_key" in unprojected.columns_with_mismatch
    projected = _compare(legacy, list(equivalence.project_rows(exported)))
    assert projected.columns_with_mismatch == ()


def test_expected_object_is_compared_exactly(
    legacy: equivalence.LegacySide, erev_rows: list[dict[str, str | None]]
) -> None:
    result = _compare(legacy, erev_rows)
    assert _fields(equivalence.mismatches({}, result)) == ["rows", "columns_with_mismatch"]
    assert _fields(equivalence.mismatches({"rows": 24}, result)) == ["columns_with_mismatch"]
    assert _fields(equivalence.mismatches({"columns_with_mismatch": []}, result)) == ["rows"]
    only_rows = equivalence.mismatches({"rows": 24}, result)[0]
    assert (only_rows.expected, only_rows.actual) == (None, "missing from the expected object")
    assert _fields(equivalence.mismatches({"rows": 25, "columns_with_mismatch": []}, result)) == [
        "rows"
    ]
    assert _fields(equivalence.mismatches({**EXPECTED, "columns": 69}, result)) == ["columns"]
    assert _fields(equivalence.mismatches({"rows": "24", "columns_with_mismatch": []}, result)) == [
        "rows"
    ]
    assert _fields(equivalence.mismatches({"rows": True, "columns_with_mismatch": []}, result)) == [
        "rows"
    ]
    assert _fields(equivalence.mismatches({"rows": 24, "columns_with_mismatch": ()}, result)) == [
        "columns_with_mismatch"
    ]


# --- GPB-3.1: row_count metadata (S1) and the tenant-wide import check (S2) -----------------------


def test_row_count_must_be_an_integer_equal_to_the_rows_read() -> None:
    rows = [object()] * 24
    assert equivalence.checked_row_count({"row_count": 24}, rows, "run") == 24
    for run in (
        {},
        {"row_count": None},
        {"row_count": "24"},
        {"row_count": True},
        {"row_count": 24.0},
    ):
        with pytest.raises(EquivalenceInputError, match="no integer row_count"):
            equivalence.checked_row_count(
                run, rows, "run"
            )  # mutation: metadata missing or mistyped
    with pytest.raises(EquivalenceInputError, match="counts 23 rows; its data pages hold 24"):
        equivalence.checked_row_count({"row_count": 23}, rows, "run")


def _import(item: equivalence.PlannedUpload, **changes: object) -> dict[str, object]:
    """An API-S-Import as the tenant would show the planned upload, with optional mutations."""
    parameters: dict[str, object] = {}
    if item.parameters.mode is not None:
        parameters["mode"] = item.parameters.mode
    if item.parameters.date_input is not None:
        parameters["effective_date"] = item.parameters.date_input.isoformat()
    shown: dict[str, object] = {
        "id": f"imp-{item.step}",
        "status": "COMMITTED",
        "template": {"code": item.parameters.template_code, "version": 1, "name": "x"},
        "file": {"sha256": item.parameters.file_sha256, "original_filename": item.file_name},
        "parameters": parameters,
    }
    shown.update(changes)
    return shown


def test_tenant_imports_that_equal_the_plan_raise_no_problem(
    legacy: equivalence.LegacySide,
) -> None:
    persisted = [_import(item) for item in legacy.plan]
    committed = {item.step: _import(item) for item in legacy.plan}
    assert equivalence.import_problems(legacy.plan, persisted, committed) == []
    # order of the persisted list is irrelevant
    assert equivalence.import_problems(legacy.plan, persisted[::-1], committed) == []


def test_an_import_outside_the_plan_is_refused(legacy: equivalence.LegacySide) -> None:
    committed = {item.step: _import(item) for item in legacy.plan}
    persisted = [_import(item) for item in legacy.plan]
    # mutation: a fifth import the scenario never recorded (a re-upload of step 04 under another id)
    persisted.append(_import(legacy.plan[3], id="imp-extra"))
    problems = equivalence.import_problems(legacy.plan, persisted, committed)
    assert any("persists 5 imports; the plan has 4" in p for p in problems)
    assert any("matches 2 persisted imports" in p for p in problems)
    # mutation: a foreign import (different digest) instead of the extra copy
    persisted[-1] = _import(legacy.plan[3], id="imp-foreign", file={"sha256": "f" * 64})
    problems = equivalence.import_problems(legacy.plan, persisted, committed)
    assert any("imp-foreign" in p and "outside the plan" in p for p in problems)


def test_a_missing_or_altered_import_is_refused(legacy: equivalence.LegacySide) -> None:
    committed = {item.step: _import(item) for item in legacy.plan}
    persisted = [_import(item) for item in legacy.plan[:-1]]  # mutation: step 04 never persisted
    problems = equivalence.import_problems(legacy.plan, persisted, committed)
    assert any("persists 3 imports; the plan has 4" in p for p in problems)
    assert any("batch 4 (step 04" in p and "matches 0 persisted imports" in p for p in problems)
    # mutation: the dated upload persisted with another effective date
    altered = [_import(item) for item in legacy.plan]
    altered[3] = _import(legacy.plan[3], parameters={"effective_date": "2023-02-28"})
    problems = equivalence.import_problems(legacy.plan, altered, committed)
    assert any("matches 0 persisted imports" in p for p in problems)
    assert any("outside the plan" in p for p in problems)
    # mutation: a persisted import that is not COMMITTED
    pending = [_import(item) for item in legacy.plan]
    pending[0] = _import(legacy.plan[0], status="DIFF_READY")
    assert equivalence.import_problems(legacy.plan, pending, committed)


def test_the_scenario_record_must_also_agree_with_the_plan(legacy: equivalence.LegacySide) -> None:
    persisted = [_import(item) for item in legacy.plan]
    committed = {item.step: _import(item) for item in legacy.plan}
    del committed["03"]  # mutation: the scenario forgot a step
    problems = equivalence.import_problems(legacy.plan, persisted, committed)
    assert problems == [
        "the replay committed steps ['01', '02', '04']; the plan has ['01', '02', '03', '04']"
    ]
    committed = {item.step: _import(item) for item in legacy.plan}
    committed["02"] = _import(legacy.plan[1], file={"sha256": "0" * 64})  # mutation: other digest
    problems = equivalence.import_problems(legacy.plan, persisted, committed)
    assert len(problems) == 1 and "was recorded by the replay as" in problems[0]
