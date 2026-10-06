"""Controls registry and G7 report (REQ-CTL-001; dev-guide DG-MK-controls-report, DG-TST-06).

``controls.yaml`` holds the 49 designated 1.0 system controls of docs/03-REQUIREMENTS.md §4.1: the
register columns, the phase that writes the first tagged test (PHASES §7) and the release-stamping
impact globs (05 REL-04). DG-ARC-10 compares it with the register. The test collection hook
validates ``@pytest.mark.control`` markers through ``check_control_markers``, and
``erev controls-report`` runs the tagged tests and writes the report through ``write_report``.
pytest is imported only inside the functions that drive it, so the registry loads without it.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import yaml

CONTROLS_PATH: Final = Path(__file__).with_name("controls.yaml")
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
RELEASE: Final = "1.0"
REPORT_TARGET: Final = "controls-report"
CONTROL_MARKER: Final = "control"
ID_RULE: Final = r"control id must match ^CTL-\d{3}$"
_CONTROL_ID: Final = re.compile(r"^CTL-\d{3}$")
# DG-TST-09: control tests exercise a failure path and may not be skipped.
_NO_SKIP_MARKERS: Final = frozenset({"skip", "skipif", "xfail"})
_FIELDS: Final = (
    "id",
    "title",
    "r07_catalogue_id",
    "r07_feature",
    "type",
    "reqs",
    "evidence",
    "release",
    "phase",
    "impact_paths",
)
_LIST_FIELDS: Final = frozenset({"r07_feature", "reqs", "impact_paths"})
# pytest exit codes after which collection succeeded: OK, TESTS_FAILED, NO_TESTS_COLLECTED.
_COLLECTED: Final = frozenset({0, 1, 5})


class ControlsError(ValueError):
    """``controls.yaml`` is malformed."""


@dataclass(frozen=True, slots=True)
class ControlSpec:
    id: str
    title: str
    r07_catalogue_id: str
    r07_feature: tuple[str, ...]
    type: str
    reqs: tuple[str, ...]
    evidence: str
    release: str
    phase: str
    impact_paths: tuple[str, ...]


def _control(entry: object, index: int) -> ControlSpec:
    if not isinstance(entry, Mapping) or set(entry) != set(_FIELDS):
        raise ControlsError(f"controls[{index}] must have exactly the fields {', '.join(_FIELDS)}")
    values: dict[str, Any] = {}
    for name in _FIELDS:
        value = entry[name]
        if name in _LIST_FIELDS:
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                raise ControlsError(f"controls[{index}].{name} must be a list of strings")
            values[name] = tuple(value)
        elif isinstance(value, str) and value:
            values[name] = value
        else:
            raise ControlsError(f"controls[{index}].{name} must be a non-empty string")
    if not _CONTROL_ID.fullmatch(values["id"]):
        raise ControlsError(f"controls[{index}]: {ID_RULE}")
    return ControlSpec(**values)


def load_controls(path: Path = CONTROLS_PATH) -> tuple[ControlSpec, ...]:
    """Every control of ``controls.yaml`` in file order; raises ``ControlsError`` when malformed."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = document.get("controls") if isinstance(document, Mapping) else None
    if not isinstance(entries, list) or not entries:
        raise ControlsError(f"{path.name} must hold a non-empty list 'controls'")
    specs = tuple(_control(entry, index) for index, entry in enumerate(entries))
    ids = [spec.id for spec in specs]
    if len(set(ids)) != len(ids):
        raise ControlsError(f"{path.name} repeats a control id")
    return specs


@lru_cache(maxsize=1)
def controls() -> Mapping[str, ControlSpec]:
    return MappingProxyType({spec.id: spec for spec in load_controls()})


def marker_errors(
    nodeid: str,
    markers: Iterable[tuple[str, Sequence[Any], Mapping[str, Any]]],
    known: Container[str],
) -> list[str]:
    """Messages for one test's invalid control markers (DG-TST-06, DG-TST-09); empty when valid."""
    errors: list[str] = []
    names: set[str] = set()
    tagged = False
    for name, args, kwargs in markers:
        names.add(name)
        if name != CONTROL_MARKER:
            continue
        tagged = True
        if len(args) != 1 or kwargs:
            errors.append(f"{nodeid}: control marker takes exactly one id")
            continue
        control_id = args[0]
        if not isinstance(control_id, str) or not _CONTROL_ID.fullmatch(control_id):
            errors.append(f"{nodeid}: {ID_RULE}, got {control_id!r}")
        elif control_id not in known:
            errors.append(f"{nodeid}: unknown control {control_id}")
    if tagged and names & _NO_SKIP_MARKERS:
        errors.append(f"{nodeid}: control tests may not carry skip, skipif or xfail (DG-TST-09)")
    return errors


def check_control_markers(items: Iterable[Any]) -> None:
    """Collection hook body: raise ``pytest.UsageError`` listing every invalid control marker."""
    import pytest

    known = controls()
    errors = [
        error
        for item in items
        for error in marker_errors(
            item.nodeid,
            [(mark.name, mark.args, mark.kwargs) for mark in item.iter_markers()],
            known,
        )
    ]
    if errors:
        raise pytest.UsageError("\n".join(errors))


@dataclass
class TaggedRun:
    """A pytest plugin recording control tags at collection and test outcomes at run time."""

    exit_code: int = 0
    tagged: dict[str, list[str]] = field(default_factory=dict)
    outcomes: dict[str, str] = field(default_factory=dict)

    @property
    def collection_ok(self) -> bool:
        return self.exit_code in _COLLECTED

    @property
    def tagged_test_count(self) -> int:
        return len({nodeid for nodes in self.tagged.values() for nodeid in nodes})

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        for item in items:
            for mark in item.iter_markers(name=CONTROL_MARKER):
                if len(mark.args) == 1:
                    nodes = self.tagged.setdefault(str(mark.args[0]), [])
                    if item.nodeid not in nodes:
                        nodes.append(item.nodeid)

    def pytest_runtest_logreport(self, report: Any) -> None:
        current = self.outcomes.get(report.nodeid)
        if report.failed:
            self.outcomes[report.nodeid] = "failed"
        elif report.skipped and current != "failed":
            self.outcomes[report.nodeid] = "skipped"
        elif report.when == "call" and current is None:
            self.outcomes[report.nodeid] = "passed"


def run_tagged_tests(tests: Path, *, collect_only: bool, base_temp: Path) -> TaggedRun:
    """Collect ``tests`` (validating markers through its conftest) and run ``-m control``."""
    import pytest

    run = TaggedRun()
    args = [str(tests), "-m", CONTROL_MARKER, "-q", "-p", "no:cacheprovider"]
    args.append("--collect-only" if collect_only else f"--basetemp={base_temp}")
    run.exit_code = int(pytest.main(args, plugins=[run]))
    return run


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _timestamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def control_rows(specs: Sequence[ControlSpec], run: TaggedRun) -> list[dict[str, Any]]:
    """One row per 1.0 control: tagged tests, their outcomes and PASS, FAIL or MISSING."""
    rows: list[dict[str, Any]] = []
    for spec in specs:
        if spec.release != RELEASE:
            continue
        tests = sorted(run.tagged.get(spec.id, []))
        outcomes = {nodeid: run.outcomes.get(nodeid, "not run") for nodeid in tests}
        if not tests:
            outcome = "MISSING"
        elif all(value == "passed" for value in outcomes.values()):
            outcome = "PASS"
        else:
            outcome = "FAIL"
        rows.append(
            {
                "id": spec.id,
                "title": spec.title,
                "phase": spec.phase,
                "tagged_tests": tests,
                "test_outcomes": outcomes,
                "outcome": outcome,
            }
        )
    return rows


def _markdown(rows: Sequence[Mapping[str, Any]], *, build_sha: str, summary: str) -> str:
    lines = [
        "# Controls report (G7)",
        "",
        f"Build `{build_sha}`. {summary}.",
        "",
        "| Control | Title | Phase | Tagged tests | Outcome |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        tests = "<br>".join(
            f"`{nodeid}` ({row['test_outcomes'][nodeid]})".replace("|", "\\|")
            for nodeid in row["tagged_tests"]
        )
        cells = (row["id"], row["title"], row["phase"], tests or "none", row["outcome"])
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_report(
    out_dir: Path,
    *,
    specs: Sequence[ControlSpec],
    run: TaggedRun,
    command: str,
    started_at: datetime,
    finished_at: datetime,
) -> tuple[int, str]:
    """Write ``report.json`` (DG-MK-00g fields plus ``controls``) and ``report.md``.

    Returns the exit code, 1 unless collection succeeded and every 1.0 control has at least one
    tagged test and all of its tagged tests passed, and the one-line summary.
    """
    rows = control_rows(specs, run)
    passing = sum(row["outcome"] == "PASS" for row in rows)
    missing = sum(row["outcome"] == "MISSING" for row in rows)
    failures: list[dict[str, Any]] = []
    if not run.collection_ok:
        failures.append({"stage": "collection", "exit_code": run.exit_code})
    failures.extend(
        {"control_id": row["id"], "reason": "no tagged test"}
        if row["outcome"] == "MISSING"
        else {"control_id": row["id"], "reason": "a tagged test did not pass"}
        for row in rows
        if row["outcome"] != "PASS"
    )
    exit_code = 1 if failures else 0
    summary = f"{passing} of {len(rows)} controls have a passing tagged test"
    build_sha = (_git("rev-parse", "HEAD") or "nogit").strip()
    status = _git("status", "--porcelain")
    report = {
        "target": REPORT_TARGET,
        "command": command,
        "build_sha": build_sha,
        "worktree_dirty": bool(status and status.strip()),
        "started_at": _timestamp(started_at),
        "finished_at": _timestamp(finished_at),
        "exit_code": exit_code,
        "counts": {
            "controls": len(rows),
            "passing": passing,
            "failing": len(rows) - passing - missing,
            "missing": missing,
            "tagged_tests": run.tagged_test_count,
        },
        "failures": failures,
        "controls": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(
        _markdown(rows, build_sha=build_sha, summary=summary), encoding="utf-8"
    )
    return exit_code, f"{REPORT_TARGET}: {summary}"
