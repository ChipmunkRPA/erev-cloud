"""scripts/e2e.sh contract (docs/dev-guide.md DG-MK-e2e, DG-MK-00e, DG-MK-00g, DG-E2E-02; PHASES
BS-D-20; BUILD_SPEC WEB-11).

Every run uses a scratch ``EREV_RUN_DIR``, so a real e2e run of the worktree (its lock, PID files
and report) is never touched. The stack steps and Playwright are stubs; no test binds a port.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "e2e.sh"
PASSWORD_MESSAGE = "EREV_DEMO_PASSWORD is not set. Copy it from .env.example."
# Only the presence of a value matters to the script; it is never printed.
STUB_VALUE = "stub value"
CLEARED = (
    "EREV_DEMO_PASSWORD",
    "EREV_DEMO_TOTP_SECRET",
    "SPEC",
    "PROJECT",
    "CLOSE",
    "EREV_E2E_UNTIL",
    "EREV_E2E_CLOSE",
)
PLAYWRIGHT_CALL = "test -c frontend/e2e/playwright.config.ts"

PLAYWRIGHT_STUB = """#!/usr/bin/env bash
# Playwright stand-in: `--list` reports one test for the screens project, one for each of the
# projects `closed` and `qa-rc` where the configuration would list them (EREV_E2E_CLOSE=1), and
# none elsewhere; a run records its arguments, behind that variable when it is set, and writes a
# JSON report with one passed test.
args="$*"
project=""
listing=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) project="$2"; shift 2 ;;
    --list) listing=1; shift ;;
    *) shift ;;
  esac
done
if [[ "$listing" == "1" ]]; then
  echo "Listing tests:"
  if [[ "$project" == "screens" ]]; then
    echo "  [screens] › screens.spec.ts:12:3 › SF-22 Sign in › SF-22 empty form and session expired"
    echo "Total: 1 test in 1 file"
  elif [[ "$project" == "closed" && "${EREV_E2E_CLOSE:-}" == "1" ]]; then
    echo "  [closed] › closed.spec.ts:60:3 › SF-04 as locked › SF-04 as locked marcus"
    echo "Total: 1 test in 1 file"
  elif [[ "$project" == "qa-rc" && "${EREV_E2E_CLOSE:-}" == "1" ]]; then
    echo "  [qa-rc] › qa-rc.spec.ts:66:3 › qa-rc: the multi-role browser QA › [0] the world"
    echo "Total: 1 test in 1 file"
  else
    echo "Total: 0 tests in 0 files"
  fi
  exit 0
fi
echo "${EREV_E2E_CLOSE:+EREV_E2E_CLOSE=$EREV_E2E_CLOSE }$args" >>"$STUB_CALLS"
printf '{"stats": {"expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0}}\\n' \\
  >"$PLAYWRIGHT_JSON_OUTPUT_FILE"
exit 0
"""


@pytest.fixture
def run_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _env(run_dir: Path, **values: str) -> dict[str, str]:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in CLEARED and not key.startswith(prefixes)
    }
    return env | {"EREV_RUN_DIR": str(run_dir), "EREV_DOTENV": str(run_dir / "absent.env")} | values


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=120
    )


def _stubbed_main(run_dir: Path, **values: str) -> subprocess.CompletedProcess[str]:
    stub = run_dir / "playwright"
    stub.write_text(PLAYWRIGHT_STUB, encoding="utf-8")
    stub.chmod(0o755)
    script = "\n".join(
        [
            "source scripts/e2e.sh",
            f'PLAYWRIGHT="{stub}"',
            'stack_up() { echo "stack up"; }',
            'stack_down() { echo "stack down"; }',
            "main",
        ]
    )
    env = _env(run_dir, EREV_DEMO_PASSWORD=STUB_VALUE, STUB_CALLS=str(run_dir / "calls.txt"))
    return _run(["bash", "-c", script], env | values)


def test_bs_d_20_projects_without_tests_skipped(run_dir: Path) -> None:
    result = _stubbed_main(run_dir)
    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads((run_dir / "reports" / "e2e" / "report.json").read_text(encoding="utf-8"))
    assert {"project": "avenmoor-serial", "skipped": "no tests yet"} in report["projects"]
    skipped = [entry["project"] for entry in report["projects"] if "skipped" in entry]
    assert skipped == ["avenmoor-serial", "fresh-tenant", "industry", "design", "crawl"]
    for project in skipped:
        assert f"{project}: skipped, no tests yet" in result.stdout

    # The screens project runs, as its own invocation with the DG-E2E-02 worker count.
    (ran,) = [entry for entry in report["projects"] if "skipped" not in entry]
    assert ran == {
        "project": "screens",
        "workers": 2,
        "exit_code": 0,
        "report": "playwright-1-screens.json",
    }
    calls = (run_dir / "calls.txt").read_text(encoding="utf-8").splitlines()
    assert calls == ["test -c frontend/e2e/playwright.config.ts --project screens --workers=2"]

    # DG-MK-00g fields, counts from the Playwright statistics, and the lock released on exit.
    assert report["target"] == "e2e"
    assert report["exit_code"] == 0
    assert report["failures"] == []
    assert report["counts"]["passed"] == 1
    assert report["counts"]["projects"] == {
        "screens": {"passed": 1, "failed": 0, "flaky": 0, "skipped": 0}
    }
    for key in ("command", "build_sha", "worktree_dirty", "started_at", "finished_at"):
        assert key in report
    assert result.stdout.index("stack up") < result.stdout.index("stack down")
    assert not (run_dir / "locks" / "e2e-ports").exists()


def test_dg_e2e_04_spec_path_and_project_filter(run_dir: Path) -> None:
    result = _stubbed_main(
        run_dir, SPEC="frontend/e2e/projects/screens.spec.ts", PROJECT="screens,design"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((run_dir / "reports" / "e2e" / "report.json").read_text(encoding="utf-8"))
    assert [entry["project"] for entry in report["projects"]] == ["screens", "design"]
    calls = (run_dir / "calls.txt").read_text(encoding="utf-8").splitlines()
    assert calls == [
        "test -c frontend/e2e/playwright.config.ts --project screens --workers=2 "
        "frontend/e2e/projects/screens.spec.ts"
    ]

    unknown = _stubbed_main(run_dir, PROJECT="screens,visual")
    assert unknown.returncode == 1
    assert "unknown project visual" in unknown.stdout


def _report(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "reports" / "e2e" / "report.json"
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return report


def test_dg_mk_e2e_close_is_a_run_of_its_own(run_dir: Path) -> None:
    """DG-MK-e2e and DG-E2E-02 rev 1.277: ``CLOSE=1`` runs the one project ``closed``, which reads
    the months the seed closes when asked, and hands Playwright the variable its configuration
    lists that project by. No other run lists or runs it, whatever the caller's environment holds:
    the six projects need every period of 2026 open."""
    calls = run_dir / "closed.txt"
    result = _stubbed_main(run_dir, CLOSE="1", STUB_CALLS=str(calls))
    assert result.returncode == 0, result.stdout + result.stderr
    closed_run = {
        "project": "closed",
        "workers": 2,
        "exit_code": 0,
        "report": "playwright-1-closed.json",
    }
    assert _report(run_dir)["projects"] == [closed_run]
    ran = f"EREV_E2E_CLOSE=1 {PLAYWRIGHT_CALL} --project closed --workers=2"
    assert calls.read_text(encoding="utf-8").splitlines() == [ran]

    # PROJECT names that project or nothing: a project of the open world is refused by name, before
    # the lock is taken.
    named = _stubbed_main(run_dir, CLOSE="1", PROJECT="closed", STUB_CALLS=str(run_dir / "named"))
    assert named.returncode == 0, named.stdout + named.stderr
    assert _report(run_dir)["projects"] == [closed_run]
    other = _stubbed_main(run_dir, CLOSE="1", PROJECT="screens")
    assert other.returncode == 1
    assert other.stdout.splitlines() == [
        "project screens does not run on the closed world (CLOSE=1); projects: closed"
    ]

    # Without CLOSE=1 the project is none of the run's, and the refusal names the command that
    # runs it. Any other value of CLOSE is no request for the closed world.
    for values in ({}, {"CLOSE": "0"}, {"CLOSE": "yes"}):
        ordinary = _stubbed_main(run_dir, PROJECT="closed", **values)
        assert ordinary.returncode == 1, values
        assert ordinary.stdout.splitlines() == [
            "project closed runs on the closed world only: make e2e CLOSE=1 PROJECT=closed"
        ], values
    assert not (run_dir / "locks").exists() or list((run_dir / "locks").iterdir()) == []

    # A caller whose environment holds Playwright's variable still runs the ordinary projects, and
    # Playwright is not handed it.
    ambient = run_dir / "ambient.txt"
    result = _stubbed_main(run_dir, EREV_E2E_CLOSE="1", STUB_CALLS=str(ambient))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [entry["project"] for entry in _report(run_dir)["projects"]] == [
        "avenmoor-serial",
        "fresh-tenant",
        "industry",
        "screens",
        "design",
        "crawl",
    ]
    assert ambient.read_text(encoding="utf-8").splitlines() == [
        f"{PLAYWRIGHT_CALL} --project screens --workers=2"
    ]


def test_dg_e2e_14_the_qa_pass_runs_on_the_closed_world_only_when_named(run_dir: Path) -> None:
    """DG-E2E-14 and DG-E2E-02 rev 1.280: the release candidate's multi-role browser QA is the
    project ``qa-rc`` of the closed world, and no run takes it unless ``PROJECT`` names it — it
    writes a record, invites a member and locks a month. Named, it runs after ``closed`` on the
    one seeded stack, with one worker; without ``CLOSE=1`` it is refused as ``closed`` is."""
    qa_run = {"project": "qa-rc", "workers": 1, "exit_code": 0, "report": "playwright-1-qa-rc.json"}
    ran_qa = f"EREV_E2E_CLOSE=1 {PLAYWRIGHT_CALL} --project qa-rc --workers=1"
    ran_closed = f"EREV_E2E_CLOSE=1 {PLAYWRIGHT_CALL} --project closed --workers=2"

    # A closed-world run that names no project is the list's alone.
    unasked = run_dir / "unasked.txt"
    result = _stubbed_main(run_dir, CLOSE="1", STUB_CALLS=str(unasked))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [entry["project"] for entry in _report(run_dir)["projects"]] == ["closed"]
    assert unasked.read_text(encoding="utf-8").splitlines() == [ran_closed]

    # Named alone.
    alone = run_dir / "alone.txt"
    result = _stubbed_main(run_dir, CLOSE="1", PROJECT="qa-rc", STUB_CALLS=str(alone))
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(run_dir)["projects"] == [qa_run]
    assert alone.read_text(encoding="utf-8").splitlines() == [ran_qa]

    # Named with the list's project: ``closed`` first, whatever the order of the names.
    for order in ("closed,qa-rc", "qa-rc,closed"):
        both = run_dir / f"both-{order.replace(',', '-')}.txt"
        result = _stubbed_main(run_dir, CLOSE="1", PROJECT=order, STUB_CALLS=str(both))
        assert result.returncode == 0, result.stdout + result.stderr
        assert [entry["project"] for entry in _report(run_dir)["projects"]] == ["closed", "qa-rc"]
        assert both.read_text(encoding="utf-8").splitlines() == [ran_closed, ran_qa], order

    # Without CLOSE=1 the name is refused before the lock is taken, with the command that runs it.
    for values in ({}, {"CLOSE": "0"}):
        ordinary = _stubbed_main(run_dir, PROJECT="qa-rc", **values)
        assert ordinary.returncode == 1, values
        assert ordinary.stdout.splitlines() == [
            "project qa-rc runs on the closed world only: make e2e CLOSE=1 PROJECT=qa-rc"
        ], values
    assert not (run_dir / "locks").exists() or list((run_dir / "locks").iterdir()) == []


def test_dg_mk_e2e_close_seeds_the_close_stage(run_dir: Path) -> None:
    """DG-MK-e2e step (4), rev 1.277: under ``CLOSE=1`` the seed is asked for the close stage
    (DG-MK-seed rev 1.221); otherwise it is the seed of every other run."""
    stub = run_dir / "erev"
    stub.write_text('#!/usr/bin/env bash\necho "$EREV_ENV $*" >>"$STUB_CALLS"\n', encoding="utf-8")
    stub.chmod(0o755)
    script = "\n".join(["source scripts/e2e.sh", f'EREV="{stub}"', "seed_world"])
    seeds = {
        "": "e2e seed demo --tenants all",
        "0": "e2e seed demo --tenants all",
        "1": "e2e seed demo --tenants all --with-close",
    }
    for value, expected in seeds.items():
        calls = run_dir / f"seed-{value or 'unset'}.txt"
        env = _env(run_dir, STUB_CALLS=str(calls)) | ({"CLOSE": value} if value else {})
        result = _run(["bash", "-c", script], env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert calls.read_text(encoding="utf-8").splitlines() == [expected], value


def test_d_85_reset_drops_partitioned_tables_before_the_schema() -> None:
    """D-85 (L3-1-Q-24): the e2e reset drops each partitioned table in its own transaction
    (``migration_ops.drop_partitioned_tables``) after the database check and before
    ``DROP SCHEMA erev CASCADE``, so no transaction exceeds the shared lock table."""
    script = SCRIPT.read_text(encoding="utf-8")
    start = script.index("reset_database() {")
    heredoc = script[script.index("<<'PY'", start) : script.index("\nPY\n", start)]
    program = heredoc.split("\n", 1)[1]
    compile(program, "reset_database", "exec")
    drop_partitions = program.index("migration_ops.drop_partitioned_tables(engine)")
    assert program.index("if not ALLOWED.fullmatch(current)") < drop_partitions
    assert drop_partitions < program.index("DROP SCHEMA IF EXISTS erev CASCADE")


def test_dg_mk_e2e_requires_password(run_dir: Path) -> None:
    result = _run(["bash", str(SCRIPT)], _env(run_dir))
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [PASSWORD_MESSAGE]
    # Before the e2e-ports lock, so before any port is bound or process started.
    assert not (run_dir / "locks").exists()
    assert list(run_dir.glob("*.pid")) == []


def test_dg_mk_00e_port_lock(run_dir: Path) -> None:
    lock = run_dir / "locks" / "e2e-ports"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    # The password comes from the .env file named by EREV_DOTENV when the environment has none.
    dotenv = run_dir / "review.env"
    dotenv.write_text(f"EREV_DEMO_PASSWORD={STUB_VALUE}\n", encoding="utf-8")

    result = _run(["bash", str(SCRIPT)], _env(run_dir, EREV_DOTENV=str(dotenv)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == f"e2e ports busy (pid {os.getpid()})"
    assert STUB_VALUE not in result.stdout + result.stderr
    # Another run's lock stays in place; nothing was started.
    assert (lock / "pid").read_text(encoding="utf-8").strip() == str(os.getpid())
    assert list(run_dir.glob("*.pid")) == []
