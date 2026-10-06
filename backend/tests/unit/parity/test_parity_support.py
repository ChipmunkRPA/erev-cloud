"""GPA-1 parity support (docs/dev-guide.md §9.6 DG-PAR-01, DG-PAR-03, DG-PAR-05, DG-PAR-07,
DG-PAR-08, DG-PAR-09; §4.4 DG-MK-parity; BUILD_SPEC GPA-1).

The collection and stale-document tests run ``backend/tests/parity`` in a subprocess. Neither needs
the database: collection builds no fixture, and a stale ``deviations.json`` fails each case before
the scenario is requested. Scratch files live under ``.run/tmp/``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from support.parity import compare, integrity, report, values
from support.parity.compare import Mismatch

ROOT = Path(__file__).resolve().parents[4]
PARITY_MODULE = "backend/tests/parity/test_golden_parity.py"
GOLDEN_SHA256 = "31fd2a081ff01f9838b478d3d39682f2889d2a132987407b296ffb1091acc850"
KIND_COUNTS = {
    "contract_position": 50,
    "journal_entry_totals": 24,
    "pob_position": 17,
    "initial_allocation": 16,
    "cumulative_catchup": 10,
    "legacy_probe": 4,
    "point_in_time_equivalence": 1,
}


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _env(**extra: str) -> dict[str, str]:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "PYTEST_", integrity.DEVIATIONS_ENV)
    kept = {key: value for key, value in os.environ.items() if not key.startswith(prefixes)}
    return {**kept, "PYTHONDONTWRITEBYTECODE": "1", **extra}


def _pytest(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def _deviations() -> dict[str, object]:
    loaded: dict[str, object] = json.loads(integrity.DEVIATIONS.read_text(encoding="utf-8"))
    return loaded


def test_integrity_preconditions(scratch_dir: Path) -> None:
    golden_bytes = integrity.GOLDEN_TESTS.read_bytes()
    assert hashlib.sha256(golden_bytes).hexdigest() == GOLDEN_SHA256
    document = json.loads(integrity.DEVIATIONS.read_text(encoding="utf-8"))
    assert document["inputs"]["golden_tests_sha256"] == GOLDEN_SHA256
    golden_ids = [item["id"] for item in json.loads(golden_bytes)["tests"]]
    assert len(golden_ids) == len(set(golden_ids)) == 122
    assert set(golden_ids) == set(document["tests"])
    assert document["self_check_failures"] == []
    assert document["posting_rule_id"] == "EXACT-CUM"
    assert set(document["probe_status_mapping"]) == {
        "authority",
        "COMMITTED",
        "COMMITTED_WITH_FINDINGS",
        "REJECTED",
        "error_code",
    }
    checked = integrity.check()
    assert (checked.ok, checked.golden_tests_sha256) == (True, GOLDEN_SHA256), checked.problems

    # Each precondition, broken in a copy, is reported.
    def broken(change: str) -> dict[str, object]:
        copy = json.loads(integrity.DEVIATIONS.read_text(encoding="utf-8"))
        match change:
            case "sha":
                copy["inputs"]["golden_tests_sha256"] = "0" * 64
            case "ids":
                del copy["tests"]["je-step-02"]
            case "self_check":
                copy["self_check_failures"] = ["x"]
            case "posting_rule":
                copy["posting_rule_id"] = "ALG01"
            case "probe_keys":
                del copy["probe_status_mapping"]["authority"]
        return copy

    expected = {
        "sha": "inputs.golden_tests_sha256",
        "ids": "different test ids",
        "self_check": "self_check_failures",
        "posting_rule": "posting_rule_id",
        "probe_keys": "probe_status_mapping",
    }
    for change, fragment in expected.items():
        path = scratch_dir / f"deviations-{change}.json"
        path.write_text(json.dumps(broken(change)), encoding="utf-8")
        problems = integrity.check(integrity.GOLDEN_TESTS, path).problems
        assert len(problems) == 1 and fragment in problems[0], (change, problems)


def test_stale_deviations_fail_every_case(scratch_dir: Path) -> None:
    stale = scratch_dir / "deviations.json"
    document = _deviations()
    inputs = document["inputs"]
    assert isinstance(inputs, dict)
    inputs["golden_tests_sha256"] = "f" * 64
    stale.write_text(json.dumps(document), encoding="utf-8")
    junit = scratch_dir / "junit.xml"
    result = _pytest(
        PARITY_MODULE,
        "-m",
        "parity",
        "-p",
        "no:cacheprovider",
        f"--basetemp={scratch_dir / 'basetemp'}",
        f"--junitxml={junit}",
        env=_env(**{integrity.DEVIATIONS_ENV: str(stale)}),
    )
    assert result.returncode == 1, result.stdout[-4000:] + result.stderr[-4000:]
    root = ET.parse(junit).getroot()
    cases = list(root.iter("testcase"))
    assert len(cases) == 122
    failures = [failure for case in cases for failure in case.findall("failure")]
    assert len(failures) == 122
    assert all(integrity.STALE in (failure.get("message") or "") for failure in failures)
    assert not list(root.iter("skipped")) and not list(root.iter("error"))


@dataclass(frozen=True, slots=True)
class _Node:
    value: str
    rounding_residue: str | None


def test_exact_value_source() -> None:
    # DG-PAR-05: an erev.money column is read from its trace node, an erev.exact column as stored.
    assert values.column_kind("revenue_cum") == "money"
    assert values.column_kind("original_total_contract_price") == "money"
    assert values.column_kind("original_allocated_exact") == "exact"
    assert values.column_kind("original_ssp_mid") == "exact"
    nodes = {
        "revenue_cum:Contract 1 / POB #2:-": _Node("118.53", "0.003201"),
        "allocated:x": _Node("237.0664", None),
    }
    row = {
        "revenue_cum": Decimal("118.53"),
        "original_allocated_exact": Decimal("237.066402378592666"),
        "original_ssp_mid": None,
        "trace_nodes": {"revenue_cum": "revenue_cum:Contract 1 / POB #2:-"},
    }
    # CHK-007: posted 118.53, exact 118.533201.
    assert values.exact(row, "revenue_cum", nodes.get) == Fraction(Decimal("118.533201"))
    assert values.exact(row, "original_allocated_exact", nodes.get) == Fraction(
        Decimal("237.066402378592666")
    )
    assert values.exact(row, "original_ssp_mid", nodes.get) is None
    # S05-R-16: original_total_contract_price is total.posted, its own exact value (L5-1-Q-34).
    assert values.exact(
        {"original_total_contract_price": Decimal("1300.00"), "trace_nodes": {}},
        "original_total_contract_price",
        nodes.get,
    ) == Fraction(1300)
    assert values.node_exact(_Node("237.0664", None)) == Fraction(Decimal("237.0664"))
    with pytest.raises(values.ValueSourceError, match="trace_nodes has no node"):
        values.exact({"billed_cum": Decimal("5.00"), "trace_nodes": {}}, "billed_cum", nodes.get)
    with pytest.raises(values.ValueSourceError, match="is not in the calc_trace"):
        values.exact({"trace_nodes": {"billed_cum": "gone"}}, "billed_cum", nodes.get)

    # DG-PAR-07: unit amounts within 1/10000; journal amounts exact to the cent.
    expected = "322.1011"
    at = Fraction(Decimal(expected))
    assert compare.unit_equal(at + Fraction(1, 10000), expected)
    assert compare.unit_equal(at - Fraction(1, 10000), expected)
    assert not compare.unit_equal(at + Fraction(10001, 100000000), expected)
    assert compare.journal_equal(Fraction(11853, 100), "118.53")
    assert not compare.journal_equal(Fraction(Decimal("118.533201")), "118.53")
    assert not compare.journal_equal(Fraction(11854, 100), "118.53")
    # Negative zero equals zero; an expected null requires a null actual.
    assert compare.unit_equal(Fraction(0), "-0.0000") and compare.journal_equal(
        Fraction(0), "-0.00"
    )
    assert compare.unit_equal(None, None) and compare.journal_equal(None, None)
    assert not compare.unit_equal(Fraction(0), None) and not compare.unit_equal(None, "0.0000")
    assert not compare.journal_equal(Fraction(0), None)
    assert compare.exact_equal("PROGRESS_OVER_DELIVERY", "PROGRESS_OVER_DELIVERY")
    assert not compare.exact_equal(8, 16)

    mismatches = compare.unit_fields(
        {"allocation": "322.1011", "ssp_midpoint": "450.0000"},
        {"allocation": Fraction(322), "ssp_midpoint": Fraction(450)},
        {"allocation": 322.1011, "ssp_midpoint": 450.0},
    )
    assert [item.to_json() for item in mismatches] == [
        {"field": "allocation", "expected": "322.1011", "actual": "322", "legacy": 322.1011}
    ]
    assert compare.render(Fraction(Decimal("237.066402378592666"))) == "237.066402378593"

    # DG-PAR-08: entries, counts by kind and class, and the B ids of signoff_required.
    cases = [case for case in integrity.cases() if case.kind == "initial_allocation"]
    first = cases[0]
    outcomes = {
        case.id: report.CaseOutcome(True)
        if case is not first
        else report.CaseOutcome(False, tuple(mismatches), "1 mismatches")
        for case in cases
    }
    document = report.build_report(
        command="make parity K=initial_allocation",
        selected=cases,
        outcomes=outcomes,
        skipped=0,
        started_at="2026-09-15T00:00:00.000000Z",
        finished_at="2026-09-15T00:00:01.000000Z",
        exit_code=1,
        failures=[],
        build_sha="nogit",
        worktree_dirty=False,
        deviations=_deviations(),
    )
    assert document["counts"]["by_kind"] == {"initial_allocation": {"A": 14, "C": 2}}
    assert (document["counts"]["passed"], document["counts"]["failed"]) == (15, 1)
    assert document["cases"]["setup-alloc-Contract1-POB1"] == {
        "kind": "initial_allocation",
        "classification": "A",
        "dev_id": None,
        "passed": False,
        "mismatches": [Mismatch("allocation", "322.1011", Fraction(322), 322.1011).to_json()],
        "message": "1 mismatches",
    }
    assert document["cases"]["setup-alloc-Contract2-VC1"]["dev_id"] == "DEV-077"
    signoff = document["signoff_required"]
    assert [entry["id"] for entry in signoff] == [
        "je-step-08",
        "je-step-14",
        "final-pob-Contract3-POB5",
        "je-month-2023-05",
        "je-month-2023-10",
        "je-month-2023-full-year",
        "probe-P1-blank-memo-drops-progress-rows",
        "probe-P2-mod-reposts-pre-asc606-in-delta-je",
        "probe-P4-duplicate-upload-double-counts",
    ]
    assert [entry["id"] for entry in signoff if entry["class_signoff"]] == [
        "je-step-08",
        "je-step-14",
        "je-month-2023-05",
        "je-month-2023-10",
        "je-month-2023-full-year",
    ]
    assert {entry["unit"] for entry in signoff if not entry["class_signoff"]} == {
        "DEV-010",
        "DEV-011",
        "DEV-050",
        "DEV-052",
    }


def test_case_ids_and_no_skip(scratch_dir: Path) -> None:
    collected = scratch_dir / "collected.json"
    probe = scratch_dir / "parity_collect_probe.py"
    probe.write_text(
        textwrap.dedent(
            f"""
            import json
            from pathlib import Path


            def pytest_collection_finish(session):
                found = []
                for item in session.items:
                    marks = getattr(item.module, "pytestmark", [])
                    marks = marks if isinstance(marks, (list, tuple)) else [marks]
                    found.append(
                        {{
                            "id": item.callspec.id,
                            "markers": sorted({{mark.name for mark in item.iter_markers()}}),
                            "module_markers": sorted({{mark.name for mark in marks}}),
                        }}
                    )
                Path({str(collected)!r}).write_text(json.dumps(found), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    python_path = os.pathsep.join(
        item for item in (str(scratch_dir), os.environ.get("PYTHONPATH", "")) if item
    )
    result = _pytest(
        PARITY_MODULE,
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "parity_collect_probe",
        env=_env(PYTHONPATH=python_path),
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    items = json.loads(collected.read_text(encoding="utf-8"))
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)) == 122
    assert ids == [case.case_id for case in integrity.cases()]
    assert "initial_allocation::setup-alloc-Contract1-POB1" in ids
    assert "contract_position::rollforward-02-Contract1" in ids
    assert Counter(test_id.split("::", 1)[0] for test_id in ids) == KIND_COUNTS
    for item in items:
        assert "parity" in item["module_markers"], item
        assert "parity" in item["markers"], item
        assert not {"skip", "skipif", "xfail"} & set(item["markers"]), item
