"""Controls report and control marker validation (dev-guide DG-MK-controls-report, DG-TST-06).

``erev controls-report`` runs in a subprocess over small suites written into the test's temporary
directory, so the assertions never depend on which repository tests carry control markers.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final

import pytest

ROOT: Final = Path(__file__).resolve().parents[3]
TESTS_ROOT: Final = ROOT / "backend" / "tests"
EREV: Final = ROOT / "backend" / ".venv" / "bin" / "erev"
PYTEST: Final = ROOT / "backend" / ".venv" / "bin" / "pytest"
CONTROL_IDS: Final = [f"CTL-{number:03d}" for number in range(1, 50)]
PYTEST_INI: Final = "[pytest]\nmarkers =\n    control(control_id): designated system control\n"
# Gate markers and their directories (DG-TST-07); the tree's conftest runs the repository check.
GATE_AREAS: Final = {
    "pg": "pg",
    "parity": "parity",
    "answer_key": "answer_keys",
    "property": "properties",
}
GATE_INI: Final = PYTEST_INI + "".join(
    f"    {name}: gate marker\n" for name in ("parity", "answer_key", "property", "pg", "perf")
)
GATE_CONFTEST: Final = (
    "import sys\n"
    "\n"
    f"sys.path.insert(0, {str(TESTS_ROOT)!r})\n"
    "\n"
    "from support import markers  # noqa: E402\n"
    "\n"
    "\n"
    "def pytest_collection_modifyitems(config, items):\n"
    "    markers.check(items, root=config.rootpath)\n"
)
MARKER_CONFTEST: Final = (
    "from erev_api.controls.registry import check_control_markers\n"
    "\n"
    "\n"
    "def pytest_collection_modifyitems(items):\n"
    "    check_control_markers(items)\n"
)
TAGGED_SUITE: Final = (
    "import pytest\n"
    "\n"
    "\n"
    '@pytest.mark.control("CTL-014")\n'
    "def test_self_approval_blocked():\n"
    "    assert 1 == 1\n"
    "\n"
    "\n"
    '@pytest.mark.control("CTL-034")\n'
    "def test_sod_conflict_blocked():\n"
    "    assert 1 == 2\n"
)


def _erev(*args: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    return subprocess.run(
        [str(EREV), "controls-report", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _suite(root: Path, **modules: str) -> Path:
    root.mkdir()
    (root / "pytest.ini").write_text(PYTEST_INI, encoding="utf-8")
    for name, source in modules.items():
        (root / f"{name}.py").write_text(source, encoding="utf-8")
    return root


def _report(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = json.loads((out / "report.json").read_text(encoding="utf-8"))
    return report


def _collect_tagged(pytester: pytest.Pytester, decorators: str) -> pytest.RunResult:
    for existing in pytester.path.glob("test_*.py"):
        existing.unlink()
    # CTL-050 and CTL-014 have equal sizes; a stale bytecode cache would replay the previous file.
    shutil.rmtree(pytester.path / "__pycache__", ignore_errors=True)
    pytester.makepyfile(
        test_tagged=f"import pytest\n\n\n{decorators}\ndef test_tagged():\n    assert 1 == 1\n"
    )
    return pytester.runpytest_subprocess("--collect-only", "-q")


def test_dg_tst_06_malformed_or_unknown_marker_fails_collection(pytester: pytest.Pytester) -> None:
    pytester.makefile(".ini", pytest=PYTEST_INI)
    pytester.makeconftest(MARKER_CONFTEST)

    malformed = _collect_tagged(pytester, '@pytest.mark.control("CTL-50")')
    assert malformed.ret == pytest.ExitCode.USAGE_ERROR
    assert r"control id must match ^CTL-\d{3}$" in malformed.stderr.str()

    unknown = _collect_tagged(pytester, '@pytest.mark.control("CTL-050")')
    assert unknown.ret == pytest.ExitCode.USAGE_ERROR
    assert "unknown control CTL-050" in unknown.stderr.str()

    known = _collect_tagged(pytester, '@pytest.mark.control("CTL-014")')
    assert known.ret == pytest.ExitCode.OK

    skipped = _collect_tagged(
        pytester, '@pytest.mark.control("CTL-014")\n@pytest.mark.skip(reason="FND-12 probe")'
    )
    assert skipped.ret == pytest.ExitCode.USAGE_ERROR
    assert "control tests may not carry skip, skipif or xfail" in skipped.stderr.str()


def _collect_module(pytester: pytest.Pytester, relative: str, source: str) -> pytest.RunResult:
    path = pytester.path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)
    path.write_text(source, encoding="utf-8")
    try:
        return pytester.runpytest_subprocess(
            relative, "--collect-only", "-q", "-p", "no:cacheprovider"
        )
    finally:
        path.unlink()


def _marked_module(marker: str | None, decorator: str = "") -> str:
    head = f"import pytest\n\npytestmark = pytest.mark.{marker}\n\n\n" if marker else ""
    return f"{head}{decorator}\ndef test_probe():\n    assert True\n"


def test_dg_tst_09_skip_or_xfail_on_marked_tests_fails_collection(
    pytester: pytest.Pytester,
) -> None:
    pytester.makefile(".ini", pytest=GATE_INI)
    pytester.makeconftest(GATE_CONFTEST)
    decorators = (
        '@pytest.mark.skip(reason="probe")',
        "@pytest.mark.xfail",
        '@pytest.mark.skipif(True, reason="probe")',
    )
    for marker, area in GATE_AREAS.items():
        for decorator in decorators:
            source = _marked_module(marker, decorator)
            result = _collect_module(pytester, f"{area}/test_probe.py", source)
            assert result.ret == pytest.ExitCode.USAGE_ERROR, (marker, decorator)
            expected = f"{marker} tests may not carry skip, skipif or xfail (DG-TST-09)"
            assert expected in result.stderr.str()


def test_dg_tst_07_marker_outside_its_directory_fails_collection(pytester: pytest.Pytester) -> None:
    pytester.makefile(".ini", pytest=GATE_INI)
    pytester.makeconftest(GATE_CONFTEST)

    outside = _collect_module(pytester, "unit/test_probe.py", _marked_module("pg"))
    assert outside.ret == pytest.ExitCode.USAGE_ERROR
    assert "DG-TST-07" in outside.stderr.str()

    unmarked = _collect_module(pytester, "pg/test_probe.py", _marked_module(None))
    assert unmarked.ret == pytest.ExitCode.USAGE_ERROR
    assert "DG-TST-07" in unmarked.stderr.str()

    architecture = _collect_module(pytester, "architecture/test_probe.py", _marked_module("pg"))
    assert architecture.ret == pytest.ExitCode.OK, architecture.stderr.str()

    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    repository = subprocess.run(
        [str(PYTEST), str(TESTS_ROOT), "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert repository.returncode == 0, repository.stdout[-2000:] + repository.stderr[-2000:]


ROOT_HOOK_FINDING: Final = "DG-TST-07: backend/tests/conftest.py does not call markers.check"


def _is_tryfirst(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and ast.unparse(decorator.func) == "pytest.hookimpl"
        and any(
            keyword.arg == "tryfirst"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in decorator.keywords
        )
    )


def root_hook_findings(source: str) -> list[str]:
    """DG-TST-07 (ER-G-05): the tryfirst collection hook calls ``markers.check(items, TESTS_ROOT)``
    before ``items.sort(...)``."""
    for node in ast.parse(source).body:
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == "pytest_collection_modifyitems"
            and any(_is_tryfirst(decorator) for decorator in node.decorator_list)
        ):
            continue
        checks, sorts = [], []
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                call = ast.unparse(inner)
                if call == "markers.check(items, TESTS_ROOT)":
                    checks.append(inner.lineno)
                elif ast.unparse(inner.func) == "items.sort":
                    sorts.append(inner.lineno)
        if checks and (not sorts or min(checks) < min(sorts)):
            return []
    return [ROOT_HOOK_FINDING]


def test_dg_tst_07_root_hook_calls_markers_check() -> None:
    source = (TESTS_ROOT / "conftest.py").read_text(encoding="utf-8")
    assert root_hook_findings(source) == []

    call = "    markers.check(items, TESTS_ROOT)\n"
    assert source.count(call) == 1
    assert root_hook_findings(source.replace(call, "")) == [ROOT_HOOK_FINDING]

    # A call after the sort does not guard collection order either.
    sort = "    items.sort(key=lambda item: collection_rank(item.path))\n"
    assert source.count(sort) == 1
    moved = source.replace(call, "").replace(sort, sort + call)
    assert root_hook_findings(moved) == [ROOT_HOOK_FINDING]


def test_mk_controls_report_writes_report(tmp_path: Path) -> None:
    suite = _suite(tmp_path / "suite", test_untagged="def test_untagged():\n    assert 1 == 1\n")
    out = tmp_path / "controls-report"

    completed = _erev("--tests", str(suite), "--out", str(out), "--command", "make controls-report")
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "controls-report: 0 of 49 controls have a passing tagged test" in completed.stdout

    report = _report(out)
    assert report["target"] == "controls-report"
    assert report["command"] == "make controls-report"
    assert report["exit_code"] == 1
    assert {"build_sha", "worktree_dirty", "started_at", "finished_at"} <= set(report)
    assert [control["id"] for control in report["controls"]] == CONTROL_IDS
    assert all(control["tagged_tests"] == [] for control in report["controls"])
    assert {control["outcome"] for control in report["controls"]} == {"MISSING"}
    assert report["counts"] == {
        "controls": 49,
        "passing": 0,
        "failing": 0,
        "missing": 49,
        "tagged_tests": 0,
    }
    assert [failure["control_id"] for failure in report["failures"]] == CONTROL_IDS

    markdown = (out / "report.md").read_text(encoding="utf-8").splitlines()
    assert len([line for line in markdown if line.startswith("| CTL-")]) == 49

    tags_only = _erev("--tags-only")
    assert tags_only.returncode == 0, tags_only.stdout + tags_only.stderr
    assert "control markers valid" in tags_only.stdout


def test_controls_report_records_tagged_outcomes(tmp_path: Path) -> None:
    suite = _suite(tmp_path / "suite", test_tagged=TAGGED_SUITE)
    out = tmp_path / "controls-report"

    completed = _erev("--tests", str(suite), "--out", str(out))
    assert completed.returncode == 1, completed.stdout + completed.stderr

    report = _report(out)
    rows = {control["id"]: control for control in report["controls"]}
    assert rows["CTL-014"]["tagged_tests"] == ["test_tagged.py::test_self_approval_blocked"]
    assert rows["CTL-014"]["outcome"] == "PASS"
    assert rows["CTL-034"]["test_outcomes"] == {
        "test_tagged.py::test_sod_conflict_blocked": "failed"
    }
    assert rows["CTL-034"]["outcome"] == "FAIL"
    assert report["counts"] == {
        "controls": 49,
        "passing": 1,
        "failing": 1,
        "missing": 47,
        "tagged_tests": 2,
    }
    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert "| CTL-014 |" in markdown
    assert "`test_tagged.py::test_self_approval_blocked` (passed)" in markdown
