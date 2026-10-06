"""Golden parity gate driver and report (docs/dev-guide.md §4.4 DG-MK-parity; §9.6 DG-PAR-08;
BUILD_SPEC GPA-1).

``make parity`` verifies the fixtures (``make fixtures CHECK=1``), then runs ``python -m
support.parity.report`` from the repository root with ``PYTHONPATH=backend/tests``. The driver runs
``backend/tests/parity`` in process with ``-m parity`` and the ``K`` expression. Each case hands its
outcome to :func:`record` through ``config.stash``. The driver writes
``.run/reports/parity/report.json``: the DG-MK-00g fields; per id ``{kind, classification, dev_id,
passed, mismatches: [{field, expected, actual, legacy}]}``; counts by kind and class; and the B ids
of ``deviations.json`` ``signoff_required``, each with its sign-off unit and status (the DEV-002
cases carry the single class sign-off, D-17a). It prints ``OK parity`` only when every selected case
passed and none was skipped, else ``FAIL parity: <reason>`` (DG-MK-00a).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pytest
from support.parity import integrity
from support.parity.compare import Mismatch
from support.parity.integrity import GoldenCase

__all__ = [
    "OUTCOMES",
    "CaseOutcome",
    "build_report",
    "case_entry",
    "main",
    "record",
    "signoff_entries",
]

TARGET: Final = "parity"
REPO_ROOT: Final = integrity.REPO_ROOT
TESTS_DIR: Final = REPO_ROOT / "backend" / "tests" / "parity"
REPORTS_DIR: Final = REPO_ROOT / ".run" / "reports"
# DEVIATIONS.md §9.2 names the approval units; no sign-off is recorded in the repository yet.
SIGNOFF_PENDING: Final = "pending revenue-accountant sign-off (DEVIATIONS.md §9.2)"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """How one case ended: passed, or failed with its mismatches or a message."""

    passed: bool
    mismatches: tuple[Mismatch, ...] = ()
    message: str | None = None


OUTCOMES: Final = pytest.StashKey[dict[str, CaseOutcome]]()


def record(config: pytest.Config, case: GoldenCase, outcome: CaseOutcome) -> None:
    """Keep a case's outcome for the report; a session the driver did not start keeps none."""
    outcomes = config.stash.get(OUTCOMES, None)
    if outcomes is not None:
        outcomes[case.id] = outcome


def case_entry(case: GoldenCase, outcome: CaseOutcome | None) -> dict[str, Any]:
    """DG-PAR-08 entry of one case; a selected case without an outcome did not pass."""
    return {
        "kind": case.kind,
        "classification": case.classification,
        "dev_id": case.dev_id,
        "passed": outcome is not None and outcome.passed,
        "mismatches": [] if outcome is None else [item.to_json() for item in outcome.mismatches],
        "message": "not run" if outcome is None else outcome.message,
    }


def signoff_entries(
    deviations: Mapping[str, Any], selected_ids: frozenset[str]
) -> list[dict[str, Any]]:
    """The B ids of ``signoff_required`` with their approval unit and sign-off status."""
    units: dict[str, Mapping[str, Any]] = {}
    for unit in deviations.get("signoff_units") or ():
        for test_id in unit.get("tests") or ():
            units[str(test_id)] = unit
    entries: list[dict[str, Any]] = []
    for test_id in deviations.get("signoff_required") or ():
        unit = units.get(str(test_id), {})
        entries.append(
            {
                "id": str(test_id),
                "unit": unit.get("unit"),
                "approval": unit.get("approval"),
                "class_signoff": unit.get("unit") == "DEV-002",
                "status": SIGNOFF_PENDING,
                "selected": str(test_id) in selected_ids,
            }
        )
    return entries


def build_report(
    *,
    command: str,
    selected: Sequence[GoldenCase],
    outcomes: Mapping[str, CaseOutcome],
    skipped: int,
    started_at: str,
    finished_at: str,
    exit_code: int,
    failures: Sequence[Mapping[str, Any]],
    build_sha: str,
    worktree_dirty: bool,
    deviations: Mapping[str, Any],
) -> dict[str, Any]:
    """The report document: DG-MK-00g fields, the DG-PAR-08 entries and their counts."""
    entries = {case.id: case_entry(case, outcomes.get(case.id)) for case in selected}
    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    passed_by_kind: Counter[str] = Counter()
    for case in selected:
        by_kind[case.kind][case.classification or "unclassified"] += 1
        if entries[case.id]["passed"]:
            passed_by_kind[case.kind] += 1
    passed = sum(1 for entry in entries.values() if entry["passed"])
    return {
        "target": TARGET,
        "command": command,
        "build_sha": build_sha,
        "worktree_dirty": worktree_dirty,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "counts": {
            "selected": len(selected),
            "passed": passed,
            "failed": len(selected) - passed,
            "skipped": skipped,
            "by_kind": {
                kind: dict(sorted(counts.items())) for kind, counts in sorted(by_kind.items())
            },
            "by_class": dict(
                sorted(Counter(case.classification or "unclassified" for case in selected).items())
            ),
            "passed_by_kind": dict(sorted(passed_by_kind.items())),
        },
        "failures": [dict(failure) for failure in failures],
        "cases": entries,
        "signoff_required": signoff_entries(deviations, frozenset(entries)),
    }


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _git(*args: str) -> str | None:
    """Git output for the DG-MK-00g fields, read as scripts/gate_report.py reads them."""
    try:
        completed = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


@dataclass(slots=True)
class _Collector:
    """Plugin: gives the session the outcome mapping, and keeps the selection and skipped ids."""

    outcomes: dict[str, CaseOutcome]
    selected: list[str] = field(default_factory=list)
    skipped: set[str] = field(default_factory=set)

    def pytest_configure(self, config: pytest.Config) -> None:
        config.stash[OUTCOMES] = self.outcomes

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        for item in session.items:
            callspec = getattr(item, "callspec", None)
            case = None if callspec is None else callspec.params.get("case")
            if isinstance(case, GoldenCase):
                self.selected.append(case.id)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.skipped:
            self.skipped.add(report.nodeid)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="make parity (DG-MK-parity)")
    parser.add_argument("--command", required=True)
    parser.add_argument("--basetemp", type=Path, default=REPO_ROOT / ".run" / "pytest-parity")
    # Tests write their reports elsewhere so they never replace a real gate report.
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)
    started_at = _utc_now()
    build_sha = (_git("rev-parse", "HEAD") or "nogit").strip()
    worktree_dirty = bool((_git("status", "--porcelain") or "").strip())
    expression = os.environ.get("K", "").strip()
    deviations = json.loads(integrity.deviations_file().read_text(encoding="utf-8"))
    every = {case.id: case for case in integrity.cases()}
    collector = _Collector(outcomes={})
    options = [str(TESTS_DIR), "-m", "parity", f"--basetemp={args.basetemp}"]
    if expression:
        options += ["-k", expression]
    pytest_exit = int(pytest.main(options, plugins=[collector]))
    selected = [every[test_id] for test_id in collector.selected if test_id in every]
    failures: list[dict[str, Any]] = []
    reasons: list[str] = []
    not_passed = [case.id for case in selected if not _passed(collector.outcomes.get(case.id))]
    if not selected:
        failures.append({"stage": "select", "exit_code": 1, "expression": expression})
        reasons.append("the selection holds no golden parity case")
    elif pytest_exit != 0 or not_passed or collector.skipped:
        failures.append(
            {
                "stage": "cases",
                "exit_code": pytest_exit or 1,
                "cases": not_passed,
                "skipped": sorted(collector.skipped),
            }
        )
        if collector.skipped:
            reasons.append(f"{len(collector.skipped)} parity cases skipped (DG-PAR-09)")
        elif not_passed:
            reasons.append(f"{len(not_passed)} of {len(selected)} selected parity cases failed")
        else:
            reasons.append(f"pytest exited {pytest_exit}")
    exit_code = int(failures[0]["exit_code"]) if failures else 0
    document = build_report(
        command=args.command,
        selected=selected,
        outcomes=collector.outcomes,
        skipped=len(collector.skipped),
        started_at=started_at,
        finished_at=_utc_now(),
        exit_code=exit_code,
        failures=failures,
        build_sha=build_sha,
        worktree_dirty=worktree_dirty,
        deviations=deviations,
    )
    out_dir = args.reports_dir / TARGET
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    (out_dir / "report.json").write_text(text, encoding="utf-8")
    counts = document["counts"]
    _say(
        f"{TARGET} counts: {counts['selected']} selected; {counts['passed']} passed, "
        f"{counts['failed']} failed, {counts['skipped']} skipped; by kind and class "
        f"{json.dumps(counts['by_kind'], sort_keys=True)}"
    )
    _say(f"OK {TARGET}" if exit_code == 0 else f"FAIL {TARGET}: {reasons[0]}")
    return exit_code


def _passed(outcome: CaseOutcome | None) -> bool:
    return outcome is not None and outcome.passed


if __name__ == "__main__":
    # Run the copy that test modules import, so record() and the collector share OUTCOMES.
    from support.parity import report as _report

    sys.exit(_report.main())
