"""Makefile target contract (docs/dev-guide.md §4.1 DG-MK-00a to 00c and 00g; PHASES §13;
BUILD_SPEC FND-18, BS1-D-11, EKC-7; REQ-OPS-007)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAKEFILE = ROOT / "Makefile"
GATE_REPORT = ROOT / "scripts" / "gate_report.py"

# PHASES §13: the phase that implements each target. An item that implements a later phase's
# target adds its phase to BUILT_PHASES or moves the target (BS1-D-11).
PHASE_TARGETS: dict[str, frozenset[str]] = {
    "FND": frozenset(
        {
            "setup",
            "backend",
            "frontend",
            "migrate",
            "db-reset",
            "revision",
            "fixtures",
            "tokens",
            "registry-seed",
            "openapi",
            "fmt",
            "lint",
            "design-check",
            "vocab-check",
            "licence-check",
            "secrets-check",
            "typecheck",
            "test",
            "build",
            "ci",
            "test-pg",
            "controls-report",
        }
    ),
    "PLF": frozenset({"dev-up", "dev-down", "status", "worker", "doctor"}),
    "WEB": frozenset({"seed", "e2e"}),
    "EKC": frozenset({"answer-keys", "properties"}),
    "GPA": frozenset({"parity"}),
    "PRF": frozenset({"perf", "perf-seed"}),
    "SOP": frozenset({"release-manifest"}),
    # dev-guide §4.5 supervisor targets: scripts only, never run by the loop. `restore-verify` is
    # the DEP-6 restore drill of 05 OPR-11 (3) and OPR-12 (lane P6; DG-MK-restore-verify);
    # `restore-drill` rehearses backup, destruction and restore on a throwaway server (lane OPS,
    # dev-guide rev 1.97; DG-MK-restore-drill).
    "DEP": frozenset(
        {
            "audit-deps",
            "zap-baseline",
            "docker-build",
            "compose-verify",
            "tf-validate",
            "backup",
            "restore-verify",
            "restore-drill",
        }
    ),
}
BUILT_PHASES = ("FND", "PLF")
# Targets of a phase not yet complete whose item has implemented them (BS1-D-11): EKC-7, EKC-12,
# WEB-10, WEB-11, GPA-1; SOP-2 `release-manifest` and the DEP-5 `docker-build` part (lane P1);
# the DEP-5 `backup` and DEP-6 `restore-verify` parts (lane P6).
BUILT_TARGETS = frozenset(
    {
        "properties",
        "answer-keys",
        "seed",
        "e2e",
        "parity",
        "release-manifest",
        "docker-build",
        "tf-validate",
        "backup",
        "restore-verify",
        "perf",  # PRF-3 (lane P7): scripts/perf.sh behind the GATE-BIND-1 wrapper
        "perf-seed",  # PRF-2 (lane P7): migrate, erev perf seed, ANALYZE (DG-MK-perf-seed)
        "audit-deps",
        "compose-verify",
        "zap-baseline",
        "restore-drill",  # lane OPS: scripts/restore_drill.sh behind the GATE-BIND-1 wrapper
    }
)
# GATE-BIND-1 (DG-MK-00i): each offline gate target wraps an inner <gate>-gate recipe.
WRAPPED_GATES = ("ci", "test-pg", "properties", "parity", "answer-keys", "controls-report")
# e2e and perf are wrapped too, with the worktree run directory exported for PID files and the
# ports lock (DG-MK-e2e, DG-MK-perf).
WRAPPED_WITH_RUN_DIR = ("e2e", "perf")
# tf-validate is a supervisor target (banner first, DG-MK-00h) wrapped the same way; its script
# belongs to the deploy lane (DEP-5) and may be absent from a tree.
WRAPPED_SUPERVISOR = ("tf-validate",)
# The DEP-5 `backup` and DEP-6 `restore-verify` parts (lane P6) are supervisor targets wrapped the
# same way, with this worktree's backup directory exported ahead of the wrapper.
WRAPPED_P6 = ("backup", "restore-verify")
# The remaining DEP-5 supervisor targets (lane P6, D-98 148 A2 (1)): wrapped on the tf-validate
# pattern
# because they produce gate evidence; docker-build stays unwrapped (it builds from `git archive`).
WRAPPED_DEP5 = ("audit-deps", "compose-verify", "zap-baseline")
# DG-MK-restore-drill (lane OPS): wrapped with nothing exported; its directory lies in the context.
WRAPPED_DRILL = ("restore-drill",)
INTERNAL_TARGETS = frozenset(
    f"{gate}-gate"
    for gate in WRAPPED_GATES
    + WRAPPED_WITH_RUN_DIR
    + WRAPPED_SUPERVISOR
    + WRAPPED_P6
    + WRAPPED_DEP5
    + WRAPPED_DRILL
)
RULE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]*):(?![:=])")


@pytest.fixture
def scratch_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _makefile_lines() -> list[str]:
    return MAKEFILE.read_text(encoding="utf-8").splitlines()


def _phony() -> set[str]:
    targets: set[str] = set()
    for line in _makefile_lines():
        if line.startswith(".PHONY:"):
            targets.update(line.removeprefix(".PHONY:").split())
    return targets


def _rules() -> set[str]:
    return {m.group(1) for line in _makefile_lines() if (m := RULE.match(line))}


def _recipe(target: str) -> str:
    return MAKEFILE.read_text(encoding="utf-8").split(f"\n{target}:\n", 1)[1].split("\n\n", 1)[0]


def _env() -> dict[str, str]:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "PYTEST_")
    return {k: v for k, v in os.environ.items() if not k.startswith(prefixes)}


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", *args],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _gate_report(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_REPORT), *args],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_req_ops_007_fnd_targets_exist_and_are_phony() -> None:
    every = frozenset().union(*PHASE_TARGETS.values())
    built = frozenset().union(*(PHASE_TARGETS[phase] for phase in BUILT_PHASES)) | BUILT_TARGETS
    later = every - built
    assert len(PHASE_TARGETS["FND"]) == 22
    assert BUILT_TARGETS <= every
    assert _rules() == built | INTERNAL_TARGETS
    assert _phony() == built | INTERNAL_TARGETS
    assert not _rules() & later


def test_dg_mk_00b_missing_venv_message() -> None:
    result = _make("typecheck", "PY=.run/tmp/missing/python")
    assert result.returncode != 0
    assert result.stdout.splitlines()[-1] == "FAIL typecheck: run make setup first"


def test_dg_mk_00c_exports() -> None:
    lines = _makefile_lines()
    assert "export TMPDIR := $(CURDIR)/.run/tmp" in lines
    assert "export PYTHONDONTWRITEBYTECODE := 1" in lines


def test_dg_mk_00a_ok_line() -> None:
    result = _make("vocab-check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK vocab-check"


def test_dg_mk_00g_ci_report_fields(scratch_dir: Path) -> None:
    # The ci recipe runs its five stages through gate_report.py with both JUnit summaries.
    recipe = _recipe("ci-gate")
    assert "scripts/gate_report.py ci" in recipe
    stages = re.findall(r'--stage "(\w+)=', recipe)
    assert stages == ["env", "lint", "typecheck", "test", "build"]
    assert re.findall(r'--junit "(\w+)=', recipe) == ["backend", "vitest"]

    # The same writer, with stand-in stages, into a scratch reports directory.
    backend = '<testsuites><testsuite tests="5" failures="0" errors="0" skipped="1"/></testsuites>'
    vitest = '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>'
    (scratch_dir / "backend.src").write_text(backend, encoding="utf-8")
    (scratch_dir / "vitest.src").write_text(vitest, encoding="utf-8")
    copy = f"cp '{scratch_dir}/backend.src' '{scratch_dir}/backend.xml' && " + (
        f"cp '{scratch_dir}/vitest.src' '{scratch_dir}/vitest.xml'"
    )
    # HEAD is read BEFORE the gate run: gate_report captures build_sha at its start, and a commit
    # landing between the run and a later read compared two heads (the S2 status chain artefact).
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    result = _gate_report(
        "ci",
        "--command",
        "make ci",
        "--reports-dir",
        str(scratch_dir / "reports"),
        "--stage",
        "env=true",
        "--stage",
        f"test={copy}",
        "--junit",
        f"backend={scratch_dir}/backend.xml",
        "--junit",
        f"vitest={scratch_dir}/vitest.xml",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK ci"

    report = json.loads((scratch_dir / "reports" / "ci" / "report.json").read_text("utf-8"))
    assert report["target"] == "ci"
    assert report["command"] == "make ci"
    assert report["build_sha"] == head
    assert isinstance(report["worktree_dirty"], bool)
    timestamp = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    assert timestamp.match(report["started_at"]) and timestamp.match(report["finished_at"])
    assert report["exit_code"] == 0
    assert report["counts"]["backend"] == {"passed": 4, "failed": 0, "skipped": 1, "xfailed": 0}
    assert report["counts"]["vitest"]["passed"] == 3
    assert report["counts"]["vitest"]["failed"] == 0
    assert report["failures"] == []


def _report_of(reports: Path, target: str) -> dict[str, object]:
    report: dict[str, object] = json.loads((reports / target / "report.json").read_text("utf-8"))
    return report


def test_dg_mk_ci_refuses_narrowing_variables(scratch_dir: Path) -> None:
    # Ruling D-78 (FR-G-01): make ci takes no narrowing variables.
    ran, reports = scratch_dir / "ran", scratch_dir / "reports"

    def run(tests: str, k: str, frontend: str) -> subprocess.CompletedProcess[str]:
        ran.unlink(missing_ok=True)
        return _gate_report(
            "ci",
            "--command",
            f"make ci TESTS={tests}" if tests else "make ci",
            "--refuse",
            f"TESTS={tests}",
            "--refuse",
            f"K={k}",
            "--refuse",
            f"FRONTEND={frontend}",
            "--stage",
            f"env=touch '{ran}'",
            "--reports-dir",
            str(reports),
        )

    result = run("backend/tests/engine", "", "")
    assert result.returncode == 1, result.stdout + result.stderr
    assert not ran.exists()
    assert result.stdout.splitlines()[-1] == (
        "FAIL ci: TESTS, K and FRONTEND are not accepted (DG-MK-ci)"
    )
    report = _report_of(reports, "ci")
    assert report["exit_code"] == 1
    assert report["failures"] == [{"stage": "variables", "exit_code": 1, "variables": ["TESTS"]}]

    for values, name in ((("", "canonical", ""), "K"), (("", "", "0"), "FRONTEND")):
        refused = run(*values)
        assert refused.returncode == 1
        assert not ran.exists()
        assert _report_of(reports, "ci")["failures"] == [
            {"stage": "variables", "exit_code": 1, "variables": [name]}
        ]

    clean = run("", "", "")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert ran.exists()
    assert clean.stdout.splitlines()[-1] == "OK ci"

    recipe = _recipe("ci-gate")
    for name in ("TESTS", "K", "FRONTEND"):
        assert f'--refuse "{name}=$({name})"' in recipe


def test_dg_mk_ci_refuses_command_line_overrides(scratch_dir: Path) -> None:
    # ER-G-04: any command-line variable fails make ci before the first stage (ruling D-79).
    ran, reports = scratch_dir / "ran", scratch_dir / "reports"
    override = "PYTEST_PATHS=backend/tests/engine/kernel/test_money.py"

    def run(overrides: str) -> subprocess.CompletedProcess[str]:
        ran.unlink(missing_ok=True)
        return _gate_report(
            "ci",
            "--command",
            f"make ci {override}",
            "--refuse",
            "TESTS=",
            "--refuse",
            "K=",
            "--refuse",
            "FRONTEND=",
            "--refuse",
            f"OVERRIDES={overrides}",
            "--stage",
            f"env=touch '{ran}'",
            "--reports-dir",
            str(reports),
        )

    refused = run(override)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert not ran.exists()
    assert _report_of(reports, "ci")["failures"] == [
        {"stage": "variables", "exit_code": 1, "variables": ["OVERRIDES"]}
    ]

    clean = run("")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert ran.exists()
    assert clean.stdout.splitlines()[-1] == "OK ci"
    # Checked on the Makefile text: `make -n ci` would execute its $(MAKE) lines.
    assert '--refuse "OVERRIDES=$(strip $(MAKEOVERRIDES))"' in _recipe("ci-gate")


def test_g5_skipped_property_test_fails_properties(scratch_dir: Path) -> None:
    # ER-G-03: make properties fails on any skipped test (ruling D-79; DG-TST-09, G5).
    reports, junit = scratch_dir / "reports", scratch_dir / "junit.xml"
    skipped_source = scratch_dir / "three-passed-one-skipped.xml"
    skipped_source.write_text(
        '<testsuites><testsuite tests="4" failures="0" errors="0" skipped="1"/></testsuites>',
        encoding="utf-8",
    )
    clean_source = scratch_dir / "three-passed.xml"
    clean_source.write_text(
        '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )

    def run(fixture: Path, *summary: str) -> subprocess.CompletedProcess[str]:
        return _gate_report(
            "properties",
            "--command",
            "make properties",
            "--stage",
            f"properties=cp '{fixture}' '{junit}'",
            *summary,
            "--fail-on-skipped",
            "properties",
            "--reports-dir",
            str(reports),
        )

    skipped = run(skipped_source, "--counts-junit", str(junit))
    assert skipped.returncode == 1, skipped.stdout + skipped.stderr
    assert skipped.stdout.splitlines()[-1] == (
        "FAIL properties: 1 skipped test in properties (DG-TST-09)"
    )
    report = _report_of(reports, "properties")
    assert report["exit_code"] == 1
    assert report["counts"]["skipped"] == 1  # type: ignore[index]
    assert report["failures"] == [{"stage": "skipped", "exit_code": 1, "label": "properties"}]

    passed = run(clean_source, "--counts-junit", str(junit))
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert passed.stdout.splitlines()[-1] == "OK properties"
    assert _report_of(reports, "properties")["counts"]["passed"] == 3  # type: ignore[index]

    unsummarised = run(clean_source)
    assert unsummarised.returncode != 0
    assert "properties" in unsummarised.stderr
    assert "--fail-on-skipped properties" in _recipe("properties-gate")


def test_g6_skipped_pg_test_fails_test_pg(scratch_dir: Path) -> None:
    # FR-G-02: make test-pg fails on any skipped test (ruling D-78; DG-TST-09).
    reports, junit = scratch_dir / "reports", scratch_dir / "junit.xml"
    source = scratch_dir / "one-passed-one-skipped.xml"
    source.write_text(
        '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="1"/></testsuites>',
        encoding="utf-8",
    )
    clean = scratch_dir / "two-passed.xml"
    clean.write_text(
        '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )

    def run(fixture: Path) -> subprocess.CompletedProcess[str]:
        return _gate_report(
            "test-pg",
            "--command",
            "make test-pg",
            "--stage",
            f"pg=cp '{fixture}' '{junit}'",
            "--junit",
            f"backend={junit}",
            "--fail-on-skipped",
            "backend",
            "--reports-dir",
            str(reports),
        )

    skipped = run(source)
    assert skipped.returncode == 1, skipped.stdout + skipped.stderr
    assert skipped.stdout.splitlines()[-1] == "FAIL test-pg: 1 skipped test in backend (DG-TST-09)"
    assert _report_of(reports, "test-pg")["exit_code"] == 1

    passed = run(clean)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert passed.stdout.splitlines()[-1] == "OK test-pg"
    assert "--fail-on-skipped backend" in _recipe("test-pg-gate")


def test_dg_mk_00g_missing_junit_fails(scratch_dir: Path) -> None:
    # FR-G-04: a gate whose JUnit summary is missing fails (ruling D-78).
    reports = scratch_dir / "reports"
    result = _gate_report(
        "ci",
        "--command",
        "make ci",
        "--stage",
        "env=true",
        "--junit",
        f"backend={scratch_dir}/absent.xml",
        "--reports-dir",
        str(reports),
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "FAIL ci: JUnit summary backend missing (DG-MK-ci)"
    report = _report_of(reports, "ci")
    assert report["exit_code"] == 1
    assert report["failures"] == [{"stage": "junit", "exit_code": 1, "label": "backend"}]

    # The writer (make test) and the reader (ci-gate's --junit options) name the same files: the
    # ci stage overrides TEST_REPORTS with CI_REPORTS so both land in the gate's own directory.
    test, ci = _recipe("test"), _recipe("ci-gate")
    (test_stage,) = re.findall(r'--stage "test=([^"]*)"', ci)
    assert test_stage.endswith("TEST_REPORTS=$(CI_REPORTS)"), test_stage
    backend = [
        p.replace("$(TEST_REPORTS)", "$(CI_REPORTS)")
        for p in re.findall(r"--junitxml=([^,\s]+)", test)
    ]
    vitest = [
        p.replace("$(TEST_REPORTS)", "$(CI_REPORTS)")
        for p in re.findall(r"--outputFile\.junit=([^,\s]+)", test)
    ]
    assert backend and backend == re.findall(r'--junit "backend=([^"]+)"', ci)
    assert vitest and vitest == re.findall(r'--junit "vitest=([^"]+)"', ci)


def _dry_run(target: str, api_port: str | None, *variables: str, dotenv: Path | None = None) -> str:
    """``make -n`` without port variables; ``dotenv`` replaces ``.env`` (an absent file by
    default, so the defaults apply)."""
    env = {k: v for k, v in _env().items() if k not in ("EREV_API_PORT", "EREV_WEB_PORT")}
    env["EREV_DOTENV"] = str(dotenv or ROOT / ".run" / "tmp" / "absent.env")
    if api_port is not None:
        env["EREV_API_PORT"] = api_port
    result = subprocess.run(
        ["make", "-n", "--no-print-directory", target, *variables],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _web_start(commands: str) -> str:
    """The ``proc.sh start web`` line of a ``make -n dev-up``."""
    (line,) = [line for line in commands.splitlines() if "scripts/proc.sh start web " in line]
    return line


def test_dg_run_01_port_override(scratch_dir: Path) -> None:
    # FR-C-03: make backend and make frontend honour EREV_API_PORT (ruling D-78).
    for recipe in (_recipe("backend"), _recipe("frontend")):
        assert "$(MAKE)" not in recipe  # so make -n executes nothing
    backend = _dry_run("backend", "8192")
    assert "lsof -nP -iTCP:8192" in backend
    assert "--port 8192" in backend
    assert "EREV_API_PROXY_TARGET=http://127.0.0.1:8192" in _dry_run("frontend", "8192")

    default = _dry_run("backend", None)
    assert "lsof -nP -iTCP:8190" in default
    assert "--port 8190" in default
    assert "EREV_API_PROXY_TARGET=http://127.0.0.1:8190" in _dry_run("frontend", None)

    # PR-R-07, S-2 (ruling D-80): the .env named by EREV_DOTENV, then the environment, reach
    # proc.sh and Vite; nothing from the file is printed.
    dotenv = scratch_dir / "review.env"
    dotenv.write_text(
        "EREV_API_PORT=8192\nEREV_WEB_PORT=5272\nEREV_SENTINEL=do-not-print\n", encoding="utf-8"
    )
    up = _dry_run("dev-up", None, "MAKE=true", dotenv=dotenv)
    assert "scripts/proc.sh start api 8192 -- " in up
    assert "scripts/proc.sh start web 5272 -- " in up
    assert "EREV_WEB_PORT=5272 " in _web_start(up)
    assert "do-not-print" not in up
    exported = _dry_run("dev-up", "8193", "MAKE=true", dotenv=dotenv)
    assert "scripts/proc.sh start api 8193 -- " in exported
    assert "scripts/proc.sh start web 5272 -- " in exported
    given = _dry_run("dev-up", None, "MAKE=true", "API_PORT=8192", "WEB_PORT=5272")
    assert "EREV_WEB_PORT=5272 " in _web_start(given)
    assert "EREV_API_PROXY_TARGET=http://127.0.0.1:8192 " in _web_start(given)


def test_plf_worker_target() -> None:
    # DG-MK-worker: the foreground worker of DG-RUN-02 on all eight queues (DG-KRN-JOB-11).
    assert "worker" in _phony()
    assert "worker" in _rules()
    recipe = _recipe("worker")
    assert "$(MAKE)" not in recipe  # so make -n executes nothing
    commands = _dry_run("worker", None)
    assert "backend/.venv/bin/erev worker" in commands
    assert "--queues" not in commands


def test_web_seed_target() -> None:
    # DG-MK-seed (WEB-10): the password check, db-reset only with RESET=1, then erev seed demo.
    assert "seed" in _phony()
    assert "seed" in _rules()
    recipe = _recipe("seed")
    assert "FAIL $@: EREV_DEMO_PASSWORD is not set. Copy it from .env.example." in recipe
    assert "$(EREV_DEMO_PASSWORD)" not in recipe  # the shell tests the value; make never expands it

    # make -n executes $(MAKE) lines, so MAKE=true turns the reset step into a no-op.
    default = _dry_run("seed", None, "MAKE=true").splitlines()
    (seed_line,) = [line for line in default if "erev seed demo" in line]
    assert 'EREV_ENV=dev backend/.venv/bin/erev seed demo --tenants "all" ||' in seed_line
    assert not any("db-reset" in line for line in default)
    assert default[-1] == 'echo "OK seed"'

    reset = _dry_run("seed", None, "MAKE=true", "RESET=1", "TENANTS=avenmoor,fernhill")
    lines = reset.splitlines()
    reset_at = next(
        n for n, line in enumerate(lines) if line.startswith("true --no-print-directory db-reset")
    )
    seed_at = next(n for n, line in enumerate(lines) if "erev seed demo" in line)
    assert reset_at < seed_at
    assert '--tenants "avenmoor,fernhill"' in lines[seed_at]

    # CLO-22 (dev-guide rev 1.221): the close of the demo world is a stage a seed runs only when
    # asked; without CLOSE=1 the command is the one above, whatever else is set.
    assert "--with-close" not in seed_line and "--with-close" not in lines[seed_at]
    closing = _dry_run("seed", None, "MAKE=true", "CLOSE=1", "TENANTS=avenmoor").splitlines()
    (closing_line,) = [line for line in closing if "erev seed demo" in line]
    assert 'erev seed demo --tenants "avenmoor" --with-close ||' in closing_line
    unasked = _dry_run("seed", None, "MAKE=true", "CLOSE=0").splitlines()
    assert not any("--with-close" in line for line in unasked)


def test_web_e2e_target() -> None:
    # DG-MK-e2e (WEB-11): `e2e` is phony and runs scripts/e2e.sh with SPEC and PROJECT.
    assert "e2e" in _phony()
    assert "e2e" in _rules()
    recipe = _recipe("e2e-gate")
    assert "$(MAKE)" not in recipe  # so make -n executes nothing
    assert "$(REQUIRE_SETUP)" in recipe
    assert 'EREV_REPORTS_DIR="$(CURDIR)/.run/reports"' in recipe
    outer = [line.strip() for line in _recipe("e2e").splitlines() if line.strip()]
    assert outer == [
        "@$(REQUIRE_SETUP)",
        '@EREV_RUN_DIR="$(RUN_DIR)" scripts/gate_context.sh e2e -- '
        "$(GATE_MAKE) --no-print-directory e2e-gate $(MAKEOVERRIDES)",
    ]

    given = _dry_run(
        "e2e-gate", None, "SPEC=frontend/e2e/projects/screens.spec.ts", "PROJECT=screens"
    ).splitlines()
    (line,) = [row for row in given if "scripts/e2e.sh" in row]
    assert line.startswith('SPEC="frontend/e2e/projects/screens.spec.ts" PROJECT="screens" ')
    assert 'EREV_E2E_COMMAND="make e2e ' in line
    assert " scripts/e2e.sh || " in line
    assert given[-1] == 'echo "OK e2e"'

    default = _dry_run("e2e-gate", None).splitlines()
    (line,) = [row for row in default if "scripts/e2e.sh" in row]
    assert line.startswith('SPEC="" PROJECT="" ')


def test_prf_perf_target() -> None:
    # DG-MK-perf (PRF-3): `perf` is phony, wrapped like e2e (GATE-BIND-1 with the run directory),
    # and its inner recipe runs scripts/perf.sh with the reports directory and the command label.
    assert "perf" in _phony()
    assert "perf" in _rules()
    recipe = _recipe("perf-gate")
    assert "$(MAKE)" not in recipe
    assert "$(REQUIRE_SETUP)" in recipe
    assert 'EREV_REPORTS_DIR="$(CURDIR)/.run/reports"' in recipe
    outer = [line.strip() for line in _recipe("perf").splitlines() if line.strip()]
    assert outer == [
        "@$(REQUIRE_SETUP)",
        '@EREV_RUN_DIR="$(RUN_DIR)" scripts/gate_context.sh perf -- '
        "$(GATE_MAKE) --no-print-directory perf-gate $(MAKEOVERRIDES)",
    ]
    given = _dry_run("perf-gate", None).splitlines()
    (line,) = [row for row in given if "scripts/perf.sh" in row]
    assert 'EREV_PERF_COMMAND="make perf' in line
    assert " scripts/perf.sh || " in line
    assert given[-1] == 'echo "OK perf"'


def test_prf_perf_seed_target() -> None:
    # DG-MK-perf-seed (PRF-2): the password check, migrate DB=dev, erev perf seed (steps 1-3), the
    # 05 PERF-27 ANALYZE of the four hot tables through erev doctor (step 4), then the stored
    # snapshot through `erev perf seed --snapshot-only` (step 5; D-98 148 A5 Q6: ANALYZE before
    # the snapshot); no port, no reset.
    assert "perf-seed" in _phony()
    assert "perf-seed" in _rules()
    recipe = _recipe("perf-seed")
    assert "FAIL $@: EREV_DEMO_PASSWORD is not set. Copy it from .env.example." in recipe
    assert "$(EREV_DEMO_PASSWORD)" not in recipe  # the shell tests the value; make never expands it
    assert "db-reset" not in recipe

    # make -n executes $(MAKE) lines, so MAKE=true turns the migrate step into a no-op.
    given = _dry_run("perf-seed", None, "MAKE=true").splitlines()
    migrate_at = next(
        n for n, line in enumerate(given) if line.startswith("true --no-print-directory migrate")
    )
    assert "DB=dev" in given[migrate_at]
    seed_lines = [n for n, line in enumerate(given) if "erev perf seed" in line]
    assert len(seed_lines) == 2  # steps 3 and 5, nothing else invokes the seed
    seed_at, snapshot_at = seed_lines
    assert "EREV_ENV=dev backend/.venv/bin/erev perf seed ||" in given[seed_at]
    assert "--snapshot-only" not in given[seed_at]
    assert "EREV_ENV=dev backend/.venv/bin/erev perf seed --snapshot-only ||" in given[snapshot_at]
    analyze_at = next(n for n, line in enumerate(given) if "doctor --analyze" in line)
    assert (
        "EREV_ENV=dev backend/.venv/bin/erev doctor --analyze "
        "schedule_line,subledger_line,contract_event,obligation_version ||" in given[analyze_at]
    )
    assert migrate_at < seed_at < analyze_at < snapshot_at  # the governed order, pinned
    assert given[-1] == 'echo "OK perf-seed"'


def test_plf_targets_exist() -> None:
    # PHASES §13 PLF targets (DG-MK-dev-up, dev-down, status, worker, doctor; BUILD_SPEC PLF-30).
    assert PHASE_TARGETS["PLF"] <= _phony()
    assert PHASE_TARGETS["PLF"] <= _rules()

    # make -n executes $(MAKE) lines, so MAKE=true turns the migrate step into a no-op.
    up = _dry_run("dev-up", None, "MAKE=true").splitlines()
    starts = [
        (m.group(1), m.group(2), m.group(3), m.group(4), number)
        for number, line in enumerate(up)
        if (m := re.match(r"^(.*?)scripts/proc\.sh start (\S+) (\S+) -- (.+?) \|\| ", line))
    ]
    assert [start[1:4] for start in starts] == [
        (
            "api",
            "8190",
            "backend/.venv/bin/uvicorn erev_api.main:create_app --factory --host 127.0.0.1 "
            "--port 8190 --no-access-log",
        ),
        ("worker", "-", "backend/.venv/bin/erev worker"),
        (
            "web",
            "5270",
            "node frontend/node_modules/vite/bin/vite.js --config frontend/vite.config.ts",
        ),
    ]
    assert [start[0] for start in starts] == [
        "",
        "",
        "EREV_API_PROXY_TARGET=http://127.0.0.1:8190 EREV_WEB_PORT=5270 EREV_VITE_MODE=dev "
        "VITE_EREV_DESIGN_GALLERY=1 ",
    ]
    migrate = next(n for n, line in enumerate(up) if line.startswith("true --no-print-directory"))
    assert "migrate DB=dev" in up[migrate]
    assert migrate < starts[0][4]
    assert up[-3:] == [
        'echo "API http://127.0.0.1:8190/api/v1"',
        'echo "Web http://127.0.0.1:5270"',
        'echo "OK dev-up"',
    ]

    down = _dry_run("dev-down", None)
    assert re.findall(r"scripts/proc\.sh (\w+) (\S+)", down) == [
        ("stop", "web"),
        ("stop", "worker"),
        ("stop", "api"),
    ]
    assert "scripts/proc.sh status ||" in _dry_run("status", None)
    assert "EREV_ENV=dev backend/.venv/bin/erev doctor --db dev ||" in _dry_run("doctor", None)
    assert "EREV_ENV=test backend/.venv/bin/erev doctor --db test ||" in _dry_run(
        "doctor", None, "DB=test"
    )


def build_imports_findings(makefile_text: str, root: Path) -> list[str]:
    """DG-MK-build: the modules make build imports (ruling D-78)."""
    match = re.search(r"^BUILD_IMPORTS := (.*)$", makefile_text, re.MULTILINE)
    modules = set(re.findall(r"\berev_[a-z_]+(?:\.[a-z_]+)*", match.group(1) if match else ""))
    required = ["erev_api.main", "erev_engine"]
    if (root / "backend" / "erev_api" / "worker.py").is_file():
        required.append("erev_api.worker")
    return [
        f"DG-MK-build: {module} missing from make build imports"
        for module in required
        if module not in modules
    ]


def test_dg_mk_build_imports_worker_when_present(scratch_dir: Path) -> None:
    # FR-B-03: make build imports erev_api.worker whenever it exists.
    assert build_imports_findings(MAKEFILE.read_text(encoding="utf-8"), ROOT) == []
    (scratch_dir / "backend" / "erev_api").mkdir(parents=True)
    (scratch_dir / "backend" / "erev_api" / "worker.py").write_text("", encoding="utf-8")
    stand_in = "BUILD_IMPORTS := erev_api.cli, erev_api.main, erev_engine\n"
    assert build_imports_findings(stand_in, scratch_dir) == [
        "DG-MK-build: erev_api.worker missing from make build imports"
    ]

    # The expanded import line follows the file's presence.
    line = next(row for row in _dry_run("build", None).splitlines() if '-c "import ' in row)
    worker_present = (ROOT / "backend" / "erev_api" / "worker.py").is_file()
    assert ("erev_api.worker" in line) is worker_present
    assert "erev_api.main" in line and "erev_engine" in line


def test_dg_mk_answer_keys_recipe() -> None:
    # DG-MK-answer-keys: the report driver validates every key, runs the selection and writes
    # .run/reports/answer-keys/report.json (EKC-12).
    recipe = _recipe("answer-keys-gate")
    assert "EREV_ENV=test PYTHONPATH=backend/tests" in recipe
    assert "-m support.answer_keys.report" in recipe
    # The selection reaches the writer through $(AK_SELECTION): the plain branch forwards the
    # variables, the canonical AK_SCOPE=full branch clears them (REL-COV-1; Codex 1510).
    assert "$(AK_SELECTION)" in recipe
    makefile = MAKEFILE.read_text(encoding="utf-8")
    for name in ("FAMILY", "ID", "REQ"):
        assert f'{name}="$({name})"' in makefile
    assert (
        'EREV_AK_SCOPE=full EREV_AK_PLATFORM=db EREV_AK_CLEARED="$(AK_CLEARED)" '
        'FAMILY="" ID="" REQ=""'
    ) in makefile
    assert '--command "$(strip make answer-keys $(MAKEOVERRIDES))"' in recipe
    assert "--basetemp $(CURDIR)/.run/pytest-answer-keys" in recipe


def test_rel_cov_1_filtered_answer_keys_runs_are_a_named_diagnostic() -> None:
    # REL-COV-1: with any of FAMILY / ID / REQ the wrapper's gate (and so the report directory) is
    # `answer-keys-filtered`; without them it is the canonical `answer-keys`. The Makefile condition
    # is the one the writer applies (any selection variable non-empty after strip).
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert (
        "AK_TARGET := $(if $(AK_FULL),answer-keys,"
        "$(if $(strip $(FAMILY)$(ID)$(REQ)),answer-keys-filtered,answer-keys))"
    ) in makefile
    default = _dry_run("answer-keys", None, "GATE_MAKE=true")
    assert "scripts/gate_context.sh answer-keys -- true" in default
    assert "answer-keys-filtered" not in default
    for variables in (("ID=RND-CHK-001",), ("FAMILY=RND",), ("REQ=REQ-X",), ("ID= ",)):
        printed = _dry_run("answer-keys", None, "GATE_MAKE=true", *variables)
        expected = "answer-keys" if variables == ("ID= ",) else "answer-keys-filtered"
        assert f"scripts/gate_context.sh {expected} -- true" in printed, (variables, printed)


def test_rel_cov_1_canonical_run_clears_inherited_filters() -> None:
    # Codex 1510: the G4 release run `make answer-keys AK_SCOPE=full` clears any inherited FAMILY /
    # ID / REQ explicitly (recorded for the writer in EREV_AK_CLEARED), exports EREV_AK_SCOPE=full
    # and EREV_AK_PLATFORM=db, and names the canonical gate whatever filter was inherited.
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "AK_SCOPE ?=" in makefile
    wrapper = _dry_run("answer-keys", None, "GATE_MAKE=true", "AK_SCOPE=full", "ID=RND-CHK-001")
    assert "scripts/gate_context.sh answer-keys -- true" in wrapper
    assert "answer-keys-filtered" not in wrapper
    inner = _dry_run("answer-keys-gate", None, "AK_SCOPE=full", "ID=RND-CHK-001", "REQ=REQ-X")
    joined = inner.replace("\\\n", " ")
    (line,) = [row for row in joined.splitlines() if "support.answer_keys.report" in row]
    for fragment in (
        "EREV_AK_SCOPE=full",
        "EREV_AK_PLATFORM=db",
        'EREV_AK_CLEARED="ID REQ"',
        'FAMILY="" ID="" REQ=""',
    ):
        assert fragment in line, (fragment, line)
    assert 'ID="RND-CHK-001"' not in line
    plain = _dry_run("answer-keys-gate", None, "ID=RND-CHK-001")
    joined = plain.replace("\\\n", " ")
    (line,) = [row for row in joined.splitlines() if "support.answer_keys.report" in row]
    assert 'ID="RND-CHK-001"' in line and "EREV_AK_SCOPE" not in line
    # Any other AK_SCOPE value is refused before the writer runs.
    bad = subprocess.run(
        ["make", "-n", "answer-keys-gate", "AK_SCOPE=fool"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert bad.returncode != 0 and "AK_SCOPE" in bad.stderr + bad.stdout


def test_dg_mk_properties_report_counts(scratch_dir: Path) -> None:
    # DG-MK-properties: the property suite under the thorough profile, counts at the top level.
    recipe = _recipe("properties-gate")
    assert "scripts/gate_report.py properties" in recipe
    assert re.findall(r'--stage "(\w+)=', recipe) == ["properties"]
    assert "HYPOTHESIS_PROFILE=thorough" in recipe
    assert "backend/tests/properties -m property" in recipe
    assert '--counts-junit ".run/reports/properties/backend-junit.xml"' in recipe

    junit = '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>'
    (scratch_dir / "properties.src").write_text(junit, encoding="utf-8")
    result = _gate_report(
        "properties",
        "--command",
        'make properties K="p02 or p03 or p04"',
        "--reports-dir",
        str(scratch_dir / "reports"),
        "--stage",
        f"properties=cp '{scratch_dir}/properties.src' '{scratch_dir}/properties.xml'",
        "--counts-junit",
        str(scratch_dir / "properties.xml"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-2:] == [
        "properties counts: 3 passed, 0 failed, 0 skipped",
        "OK properties",
    ]
    report = json.loads((scratch_dir / "reports" / "properties" / "report.json").read_text("utf-8"))
    assert report["counts"] == {
        "stages": {"properties": "pass"},
        "passed": 3,
        "failed": 0,
        "skipped": 0,
        "xfailed": 0,
    }


def test_dep5_audit_compose_zap_are_wrapped_supervisor_targets() -> None:
    # DG-MK-audit-deps, DG-MK-compose-verify, DG-MK-zap-baseline (D-48a; DG-MK-00h) under
    # GATE-BIND-1
    # (DG-MK-00i; D-98 148 A2 (1)): banner first, then the context wrapper; the inner <target>-gate
    # recipe refuses a missing script and calls it with the make command in its environment; no
    # tool name (docker, npm, uv, pip-audit, zap) appears in either recipe: the scripts own every
    # call.
    for target, script in (
        ("audit-deps", "scripts/audit_deps.sh"),
        ("compose-verify", "scripts/compose_verify.sh"),
        ("zap-baseline", "scripts/zap_baseline.sh"),
    ):
        assert target in _phony() and f"{target}-gate" in _phony(), target
        assert target in _rules() and f"{target}-gate" in _rules(), target
        lines = [line.strip() for line in _recipe(target).splitlines() if line.strip()]
        assert lines == [
            f'@echo "SUPERVISOR TARGET {target} (D-48a)"',
            "@$(REQUIRE_SETUP)",
            f"@scripts/gate_context.sh {target} -- "
            f"$(GATE_MAKE) --no-print-directory {target}-gate $(MAKEOVERRIDES)",
        ], target
        inner = _recipe(f"{target}-gate")
        assert "$(MAKE)" not in inner and "$(REQUIRE_SETUP)" in inner and script in inner
        assert f"test -x {script}" in inner
        for word in ("docker", "npm", "uv ", "pip-audit", "zap-baseline.py", "terraform"):
            assert word not in inner and word not in _recipe(target), (target, word)
        dry = _dry_run(target, None, "GATE_MAKE=true").splitlines()
        assert dry[0] == f'echo "SUPERVISOR TARGET {target} (D-48a)"'
        assert any(f"scripts/gate_context.sh {target} -- true" in line for line in dry), target
        gate = _dry_run(f"{target}-gate", None).splitlines()[-1]
        variable = {
            "audit-deps": "EREV_AUDIT_DEPS_COMMAND",
            "compose-verify": "EREV_COMPOSE_VERIFY_COMMAND",
            "zap-baseline": "EREV_ZAP_BASELINE_COMMAND",
        }[target]
        assert gate.startswith(f'{variable}="make {target}" {script}'), gate


def test_dep_backup_and_restore_verify_are_wrapped_supervisor_targets() -> None:
    # DG-MK-backup and DG-MK-restore-verify (D-48a; DG-MK-00h) under GATE-BIND-1 (DG-MK-00i): the
    # banner first, then the context wrapper with this worktree's backup directory exported; the
    # inner <target>-gate recipe hands its variables to the script through the environment; no
    # URL, no secret and no database name appears in either recipe (the scripts read .env).
    # Rev 1.81 (lane OPS, first runs on a clean tree): the deployment's live data stays in the
    # worktree, so the recipes also export where it is — the worktree's run directory for both
    # (the PID files of DG-MK-backup step 0; the restore directory that must outlive the context)
    # and the worktree itself for the backup (a relative EREV_FILE_ROOT resolves against it).
    prefixes = {
        "backup": (
            'EREV_BACKUP_DIR="$(CURDIR)/.data/backups" EREV_BACKUP_DATA_ROOT="$(CURDIR)" '
            'EREV_RUN_DIR="$(RUN_DIR)"'
        ),
        "restore-verify": 'EREV_BACKUP_DIR="$(CURDIR)/.data/backups" EREV_RUN_DIR="$(RUN_DIR)"',
    }
    for target, script in (
        ("backup", "scripts/backup.sh"),
        ("restore-verify", "scripts/restore_verify.sh"),
    ):
        prefix = prefixes[target]
        assert target in _phony() and f"{target}-gate" in _phony(), target
        assert target in _rules() and f"{target}-gate" in _rules(), target
        lines = [line.strip() for line in _recipe(target).splitlines() if line.strip()]
        assert lines == [
            f'@echo "SUPERVISOR TARGET {target} (D-48a)"',
            "@$(REQUIRE_SETUP)",
            f"@{prefix} scripts/gate_context.sh {target} -- "
            f"$(GATE_MAKE) --no-print-directory {target}-gate $(MAKEOVERRIDES)",
        ], target
        inner = _recipe(f"{target}-gate")
        assert "$(MAKE)" not in inner and "$(REQUIRE_SETUP)" in inner and script in inner
        for forbidden in ("EREV_DB_OWNER_URL", "pg_dump", "pg_restore", "DROP", "$(EREV)"):
            assert forbidden not in inner and forbidden not in _recipe(target), (target, forbidden)
        dry = _dry_run(target, None, "GATE_MAKE=true").splitlines()
        assert dry[0] == f'echo "SUPERVISOR TARGET {target} (D-48a)"'
        assert any(f"scripts/gate_context.sh {target} -- true" in line for line in dry), target
        # the exports are absolute paths of this worktree, resolved before the wrapper clones
        wrapper = next(line for line in dry if f"scripts/gate_context.sh {target} " in line)
        assert f'EREV_BACKUP_DIR="{ROOT}/.data/backups"' in wrapper, target
        assert f'EREV_RUN_DIR="{ROOT}/.run"' in wrapper, target
        assert (f'EREV_BACKUP_DATA_ROOT="{ROOT}"' in wrapper) == (target == "backup"), target

    backup = _dry_run("backup-gate", None).splitlines()[-1]
    assert backup.startswith('EREV_BACKUP_COMMAND="make backup" scripts/backup.sh')

    restore = _dry_run(
        "restore-verify-gate", None, "BACKUP=erev-20260919T120000Z", "RESET=1"
    ).splitlines()[-1]
    assert 'BACKUP="erev-20260919T120000Z"' in restore
    assert 'RESET="1"' in restore
    (command,) = re.findall(r'EREV_RESTORE_COMMAND="([^"]*)"', restore)
    assert command.startswith("make restore-verify ")
    assert set(command.split()[2:]) == {"BACKUP=erev-20260919T120000Z", "RESET=1"}
    default = _dry_run("restore-verify-gate", None).splitlines()[-1]
    assert default.startswith('BACKUP="" RESET="" EREV_RESTORE_COMMAND="make restore-verify" ')


def test_dep_restore_drill_is_a_wrapped_supervisor_target() -> None:
    # DG-MK-restore-drill (D-48a; DG-MK-00h) under GATE-BIND-1 (DG-MK-00i): the banner first, then
    # the context wrapper with nothing exported ahead of it — the drill reads and writes nothing
    # of the deployment, and its directory lies inside the execution context — and the inner
    # recipe hands the three variables and the make command to the script. No tool, URL, role or
    # directory of the deployment appears in either recipe: the script owns every call.
    target, script = "restore-drill", "scripts/restore_drill.sh"
    assert target in _phony() and f"{target}-gate" in _phony()
    assert target in _rules() and f"{target}-gate" in _rules()
    lines = [line.strip() for line in _recipe(target).splitlines() if line.strip()]
    assert lines == [
        f'@echo "SUPERVISOR TARGET {target} (D-48a)"',
        "@$(REQUIRE_SETUP)",
        f"@scripts/gate_context.sh {target} -- "
        f"$(GATE_MAKE) --no-print-directory {target}-gate $(MAKEOVERRIDES)",
    ]
    inner = _recipe(f"{target}-gate")
    assert "$(MAKE)" not in inner and "$(REQUIRE_SETUP)" in inner and script in inner
    for forbidden in (
        "docker",
        "pg_dump",
        "pg_restore",
        "EREV_DB_OWNER_URL",
        "EREV_BACKUP_DIR",
        "EREV_RUN_DIR",
        "erev_backup",
        "DROP",
        "$(EREV)",
    ):
        assert forbidden not in inner and forbidden not in _recipe(target), forbidden
    dry = _dry_run(target, None, "GATE_MAKE=true").splitlines()
    assert dry[0] == f'echo "SUPERVISOR TARGET {target} (D-48a)"'
    (wrapper,) = [line for line in dry if f"scripts/gate_context.sh {target} " in line]
    assert wrapper.startswith(f"scripts/gate_context.sh {target} -- true "), "nothing is exported"

    default = _dry_run(f"{target}-gate", None).splitlines()[-1]
    assert default == (
        'DRILL_PORT="" RESET="" TENANTS="all" EREV_RESTORE_DRILL_COMMAND="make restore-drill" '
        "scripts/restore_drill.sh"
    )
    chosen = _dry_run(
        f"{target}-gate", None, "DRILL_PORT=5447", "RESET=1", "TENANTS=avenmoor"
    ).splitlines()[-1]
    assert chosen.startswith('DRILL_PORT="5447" RESET="1" TENANTS="avenmoor" ')
    (command,) = re.findall(r'EREV_RESTORE_DRILL_COMMAND="([^"]*)"', chosen)
    assert command.startswith("make restore-drill ")
    assert set(command.split()[2:]) == {"DRILL_PORT=5447", "RESET=1", "TENANTS=avenmoor"}


def test_sop_release_manifest_target() -> None:
    # DG-MK-release-manifest (SOP-2): `release-manifest` is .PHONY and runs
    # $(PY) scripts/release_manifest.py offline, without running any gate; STRICT=1 adds --strict.
    assert "release-manifest" in _phony()
    assert "release-manifest" in _rules()
    recipe = _recipe("release-manifest")
    assert "$(MAKE)" not in recipe  # so make -n executes nothing
    assert "$(REQUIRE_SETUP)" in recipe
    for gate in ("gate_report.py", "pytest", "$(PYTEST)", "support.", "docker"):
        assert gate not in recipe, gate

    default = _dry_run("release-manifest", None).splitlines()
    (line,) = [row for row in default if "scripts/release_manifest.py" in row]
    assert line.startswith("backend/.venv/bin/python scripts/release_manifest.py ")
    assert '--command "make release-manifest"' in line
    assert "--strict" not in line
    assert default[-1] == line, "the script prints the OK or FAIL line itself (DG-MK-00a)"

    strict = _dry_run("release-manifest", None, "STRICT=1").splitlines()
    (line,) = [row for row in strict if "scripts/release_manifest.py" in row]
    assert '--command "make release-manifest STRICT=1"' in line
    assert line.rstrip().endswith("--strict")
    # DG-MK-release-manifest step (7), P1-VL-S2 (Codex packet 1041): the declaration is DATA
    # passed through the environment — never interpolated into the recipe's shell line — and the
    # report's --command omits the raw value. A dry run only prints; nothing authored executes.
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "export VALIDATION_LEVEL" in makefile
    assert "--validation-level" not in recipe, "no interpolation of the value into shell source"
    for value in ("MINOR", 'MIN"OR"', "MINOR --validation-level MAJOR"):
        printed = _dry_run("release-manifest", None, f"VALIDATION_LEVEL={value}").splitlines()
        (line,) = [row for row in printed if "scripts/release_manifest.py" in row]
        assert "MIN" not in line and "validation-level" not in line, line
        assert '--command "make release-manifest"' in line, line
    embedded = _dry_run("release-manifest", None, "EMBEDDED=1").splitlines()
    (line,) = [row for row in embedded if "scripts/release_manifest.py" in row]
    assert line.rstrip().endswith("--embedded") and "--strict" not in line


def test_dep_docker_build_target() -> None:
    # DG-MK-docker-build (D-48a; DG-MK-00h): the supervisor banner first, then
    # scripts/docker_build.sh; never push or login. Rev 1.97 (ruling R-53 (4)): the recipe no longer
    # runs `make release-manifest EMBEDDED=1` — that step wrote release-manifest.json at the
    # repository root and left it there; the script writes the embedded manifest under the run
    # directory (test_docker_build), so nothing in the recipe writes into the working tree.
    assert "docker-build" in _phony()
    assert "docker-build" in _rules()
    recipe = _recipe("docker-build")
    assert "docker push" not in recipe and "docker login" not in recipe
    assert "$(REQUIRE_SETUP)" in recipe
    assert "$(MAKE)" not in recipe and "release-manifest" not in recipe
    assert "release_manifest.py" not in recipe, "the manifest step belongs to the script"

    # make -n executes $(MAKE) lines; MAKE=true would neutralise one, and none may be left.
    lines = _dry_run("docker-build", None, "MAKE=true", "NO_CACHE=1", "STRICT=1").splitlines()
    assert lines[0] == 'echo "SUPERVISOR TARGET docker-build (D-48a)"'
    assert not any(line.startswith("true ") or "release-manifest" in line for line in lines)
    (script_line,) = [line for line in lines if "scripts/docker_build.sh" in line]
    assert 'NO_CACHE="1"' in script_line
    assert 'STRICT="1"' in script_line, "STRICT=1 reaches the script's manifest step"
    (command,) = re.findall(r'EREV_DOCKER_BUILD_COMMAND="([^"]*)"', script_line)
    assert command.startswith("make docker-build ")
    assert set(command.split()[2:]) == {"MAKE=true", "NO_CACHE=1", "STRICT=1"}  # make orders them
    assert lines[-1] == script_line, "the script prints the OK or FAIL line itself"
    assert 'STRICT=""' in _dry_run("docker-build", None).splitlines()[-1]


def test_gate_bind_1_offline_gates_run_through_the_context_wrapper() -> None:
    # GATE-BIND-1 (DG-MK-00i): every offline gate target runs `scripts/gate_context.sh <gate> --
    # make <gate>-gate` and nothing else; the inner target holds the recipe the gate had before.
    for gate in WRAPPED_GATES:
        recipe = _recipe(gate)
        assert "$(MAKE)" not in recipe and "${MAKE}" not in recipe, gate  # make -n only prints
        assert not any(line.lstrip().startswith("+") for line in recipe.splitlines()), gate
        lines = [line.strip() for line in recipe.splitlines() if line.strip()]
        assert lines[0] == "@$(REQUIRE_SETUP)", gate
        # answer-keys names its gate from the selection: the canonical `answer-keys` or the
        # diagnostic `answer-keys-filtered` (REL-COV-1), through $(AK_TARGET).
        gate_name = "$(AK_TARGET)" if gate == "answer-keys" else gate
        assert lines[1] == (
            f"@scripts/gate_context.sh {gate_name} -- "
            f"$(GATE_MAKE) --no-print-directory {gate}-gate $(MAKEOVERRIDES)"
        ), gate
        assert len(lines) == 2, gate
        assert f"{gate}-gate" in _phony() and f"{gate}-gate" in _rules()
    # The wrapper's PYTHONPATH entry survives the parity and answer-keys recipes (the context's
    # packages must stay ahead of the editable install).
    for gate in ("parity", "answer-keys"):
        assert "PYTHONPATH=backend/tests$(if $(PYTHONPATH),:$(PYTHONPATH))" in _recipe(
            f"{gate}-gate"
        ), gate


def test_gate_bind_1_tf_validate_is_a_wrapped_supervisor_target() -> None:
    # GATE-BIND-1 addition: the validate-only Terraform check runs through the wrapper; the banner
    # comes first (DG-MK-00h); the inner target calls the deploy lane's script.
    lines = [line.strip() for line in _recipe("tf-validate").splitlines() if line.strip()]
    assert lines == [
        '@echo "SUPERVISOR TARGET tf-validate (D-48a)"',
        "@$(REQUIRE_SETUP)",
        "@scripts/gate_context.sh tf-validate -- "
        "$(GATE_MAKE) --no-print-directory tf-validate-gate $(MAKEOVERRIDES)",
    ]
    inner = _recipe("tf-validate-gate")
    assert "scripts/tf_validate.sh" in inner and "$(MAKE)" not in inner
    dry = _dry_run("tf-validate", None, "GATE_MAKE=true").splitlines()
    assert dry[0] == 'echo "SUPERVISOR TARGET tf-validate (D-48a)"'
    assert any("scripts/gate_context.sh tf-validate -- true" in line for line in dry)


# P1-VL-S3 (Codex packet 1101): a scratch makefile that includes the real one and adds a CONSTANT
# collector recipe (it prints two environment variables to a file; the authored value is data the
# shell expands as a variable, never a command).
COLLECTOR = (
    "include Makefile\n"
    "p1-env-collector:\n"
    '\t@printf \'%s|%s\' "$$VALIDATION_LEVEL" "$$EREV_VALIDATION_LEVEL_RAW" > "$(P1_COLLECT_OUT)"\n'
)


def _collect(scratch_dir: Path, *variables: str, env_value: str | None = None) -> tuple[str, str]:
    makefile = scratch_dir / "collector.mk"
    makefile.write_text(COLLECTOR, encoding="utf-8")
    out = scratch_dir / "collected.txt"
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("VALIDATION_LEVEL", "EREV_VALIDATION_LEVEL_RAW")
    }
    if env_value is not None:
        env["VALIDATION_LEVEL"] = env_value
    subprocess.run(
        [
            "make",
            "-s",
            "-f",
            str(makefile),
            "p1-env-collector",
            f"P1_COLLECT_OUT={out}",
            *variables,
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    plain, raw = out.read_text(encoding="utf-8").split("|", 1)
    return plain, raw


def test_validation_level_authored_bytes_survive_make_unexpanded(scratch_dir: Path) -> None:
    # Make expands a command-line variable when exporting it (MIN$(P1_UNSET)OR → MINOR); the
    # $(value) capture EREV_VALIDATION_LEVEL_RAW carries the authored bytes to the generator.
    assert "export EREV_VALIDATION_LEVEL_RAW := $(value VALIDATION_LEVEL)" in MAKEFILE.read_text(
        encoding="utf-8"
    )
    plain, raw = _collect(scratch_dir, "VALIDATION_LEVEL=MIN$(P1_UNSET)OR")
    assert plain == "MINOR", "the plain export is Make's expansion (the defect Codex measured)"
    assert raw == "MIN$(P1_UNSET)OR", "the authored bytes, unexpanded"
    assert _collect(scratch_dir, "VALIDATION_LEVEL=MIN$$OR") == ("MIN$OR", "MIN$$OR")
    for literal in ("PATCH", "MINOR", "MAJOR"):
        assert _collect(scratch_dir, f"VALIDATION_LEVEL={literal}") == (literal, literal)
    assert _collect(scratch_dir) == ("", "")  # unset: omission
    assert _collect(scratch_dir, "VALIDATION_LEVEL=") == ("", "")  # empty: omission
    assert _collect(scratch_dir, env_value='MIN"OR"') == ('MIN"OR"', 'MIN"OR"')  # env origin
    whole = "MINOR --validation-level MAJOR"
    assert _collect(scratch_dir, f"VALIDATION_LEVEL={whole}") == (whole, whole)


def test_gate_bind_1_ci_junit_files_live_in_the_gate_directory() -> None:
    # JUnit retention (DG-MK-00i): the wrapper copies back only <ctx>/.run/reports/<gate>/, so the
    # ci gate's test stage writes its JUnit files there (TEST_REPORTS=$(CI_REPORTS)) and names the
    # same files in its --junit options; `make test` alone keeps .run/reports/test/. The 209120c
    # wrapped run retained the counts but not the per-test JUnit. No dry run of ci-gate here: its
    # recipe names $(MAKE) inside the stage strings, which `make -n` would execute.
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "CI_REPORTS ?= $(CURDIR)/.run/reports/ci" in makefile
    recipe = _recipe("ci-gate")
    (test_stage,) = re.findall(r'--stage "test=([^"]*)"', recipe)
    assert test_stage.endswith("test SLOW=1 TEST_REPORTS=$(CI_REPORTS)"), test_stage
    junits = dict(re.findall(r'--junit "(\w+)=([^"]*)"', recipe))
    assert junits == {
        "backend": "$(CI_REPORTS)/backend-junit.xml",
        "vitest": "$(CI_REPORTS)/vitest-junit.xml",
    }
    assert "TEST_REPORTS" not in _recipe("test").replace("$(TEST_REPORTS)", "")  # unchanged target
    assert "$(TEST_REPORTS)/backend-junit.xml" in _recipe("test")


def test_gate_bind_1_dry_run_creates_no_context(scratch_dir: Path) -> None:
    # Supervisor ruling: `make -n <gate>` must only print. The wrapper line names $(GATE_MAKE), a
    # plain variable, so GNU make does not execute it under -n and no .run/gates/ctx-* appears.
    gates = ROOT / ".run" / "gates"
    before = set(gates.glob("ctx-*")) if gates.is_dir() else set()
    lines = _dry_run("ci", None).splitlines()
    (wrapper,) = [line for line in lines if "scripts/gate_context.sh ci -- " in line]
    assert wrapper.startswith("scripts/gate_context.sh ci -- make --no-print-directory ci-gate")
    after = set(gates.glob("ctx-*")) if gates.is_dir() else set()
    assert after == before, "a dry run cloned an execution context"
    assert "GATE_MAKE ?= make" in MAKEFILE.read_text(encoding="utf-8")


def test_dg_mk_00a_the_fail_line_is_last_on_stdout_and_make_adds_its_own_on_stderr() -> None:
    # DG-MK-00a rev 1.97 (ruling R-53 (9)): a failing target ends its standard output with
    # `FAIL <target>: <reason>`; GNU make then writes `make: *** [<target>] Error <n>` on standard
    # error, which no recipe can prevent. The Makefile's own `step` macro is run here in a scratch
    # Makefile, alone and under an inner make as the DG-MK-00i wrappers run one.
    (step,) = [
        line for line in MAKEFILE.read_text("utf-8").splitlines() if line.startswith("step = ")
    ]
    assert step == 'step = $(1) || { echo "FAIL $@: $(2)"; exit 1; }'
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        scratch = Path(directory) / "Makefile"
        scratch.write_text(
            f"{step}\n"
            ".PHONY: probe wrapped passing\n"
            "probe:\n"
            '\t@echo "probe: working"\n'
            "\t@$(call step,false,the step failed)\n"
            '\t@echo "OK probe"\n'
            "wrapped:\n"
            "\t@$(MAKE) --no-print-directory probe\n"
            "passing:\n"
            "\t@$(call step,true,never printed)\n"
            '\t@echo "OK passing"\n',
            encoding="utf-8",
        )

        def run(target: str) -> subprocess.CompletedProcess[str]:
            env = {k: v for k, v in os.environ.items() if not k.startswith(("MAKE", "MFLAGS"))}
            return subprocess.run(
                ["make", "-f", str(scratch), target],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

        failed = run("probe")
        assert failed.returncode == 2
        assert failed.stdout.splitlines() == ["probe: working", "FAIL probe: the step failed"]
        (own,) = failed.stderr.splitlines()
        assert re.fullmatch(r"make: \*\*\* \[(?:\S+:\d+: )?probe\] Error 1", own), own

        nested = run("wrapped")
        assert nested.returncode == 2
        assert nested.stdout.splitlines()[-1] == "FAIL probe: the step failed"
        inner, outer = nested.stderr.splitlines()
        assert re.fullmatch(r"make\[1\]: \*\*\* \[(?:\S+:\d+: )?probe\] Error 1", inner), inner
        assert re.fullmatch(r"make: \*\*\* \[(?:\S+:\d+: )?wrapped\] Error 2", outer), outer

        passed = run("passing")
        assert (passed.returncode, passed.stdout, passed.stderr) == (0, "OK passing\n", "")
