"""scripts/proc.sh contract (docs/dev-guide.md DG-RUN-10 to DG-RUN-12; BUILD_SPEC FND-1, EKC-7a)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROC = ["bash", "scripts/proc.sh"]
PROBE_COMMAND = ["backend/.venv/bin/python", "-c", "import time; time.sleep(60)"]
# A per-process name, so concurrent test runs never share the probe's PID file or log.
PROBE = f"probe-{os.getpid()}"
PID_FILE = ROOT / ".run" / f"{PROBE}.pid"
LOG_FILE = ROOT / ".run" / f"{PROBE}.log"
PORT_VARIABLES = (
    "EREV_API_PORT",
    "EREV_WEB_PORT",
    "EREV_E2E_API_PORT",
    "EREV_E2E_WEB_PORT",
    "EREV_DOTENV",
    "EREV_RUN_DIR",
)
ABSENT_DOTENV = str(ROOT / ".run" / "tmp" / "absent.env")


def _proc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*PROC, *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=90
    )


def _port_env(**values: str) -> dict[str, str]:
    """The environment without port variables; ``.env`` is replaced by an absent file unless
    ``EREV_DOTENV`` is given."""
    env = {key: value for key, value in os.environ.items() if key not in PORT_VARIABLES}
    return env | {"EREV_DOTENV": ABSENT_DOTENV} | values


def _sourced(expression: str, api_port: str | None) -> subprocess.CompletedProcess[str]:
    env = _port_env()
    if api_port is not None:
        env["EREV_API_PORT"] = api_port
    return subprocess.run(
        ["bash", "-c", f"source scripts/proc.sh && {expression}"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _pid_files() -> list[Path]:
    return sorted((ROOT / ".run").glob("*.pid"))


def test_dg_run_10_start_reuse_stop_status() -> None:
    _proc("stop", PROBE)  # clears a PID file left by an interrupted run
    try:
        started = _proc("start", PROBE, "-", "--", *PROBE_COMMAND)
        assert started.returncode == 0, started.stdout + started.stderr
        assert PID_FILE.is_file()
        pid = int(PID_FILE.read_text().strip())
        assert _alive(pid)

        again = _proc("start", PROBE, "-", "--", *PROBE_COMMAND)
        assert again.returncode == 0
        assert f"{PROBE} already running (pid {pid})" in again.stdout
        assert int(PID_FILE.read_text().strip()) == pid

        status = _proc("status")
        assert status.returncode == 0
        probe_lines = [line for line in status.stdout.splitlines() if line.startswith(f"{PROBE} ")]
        assert len(probe_lines) == 1
        assert " alive " in f" {probe_lines[0]} "

        stopped = _proc("stop", PROBE)
        assert stopped.returncode == 0
        assert not PID_FILE.exists()
        assert not _alive(pid)

        not_running = _proc("stop", PROBE)
        assert not_running.returncode == 0
        assert f"{PROBE} not running" in not_running.stdout
    finally:
        _proc("stop", PROBE)
        LOG_FILE.unlink(missing_ok=True)


def test_dg_run_10_readiness_uses_start_port() -> None:
    before = _pid_files()
    cases = [
        ("readiness api 8192", None, "http http://127.0.0.1:8192/api/v1/readyz"),
        ("readiness api 8192", "8190", "http http://127.0.0.1:8192/api/v1/readyz"),
        ("readiness web 5272", None, "http http://127.0.0.1:5272/"),
        ("readiness api -", None, "http http://127.0.0.1:8190/api/v1/readyz"),
    ]
    for expression, api_port, expected in cases:
        result = _sourced(expression, api_port)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout == f"{expected}\n", expression

    worker = _sourced("readiness worker -", None)
    assert worker.returncode == 0
    assert worker.stdout.startswith("heartbeat ")
    assert worker.stdout.count("\n") == 1
    assert _pid_files() == before


def test_dg_run_10_ports_from_dotenv() -> None:
    # PR-R-07 (ruling D-80): a review worktree's .env carries the port override.
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        scratch = Path(directory)
        dotenv = scratch / "review.env"
        dotenv.write_text("EREV_WEB_PORT=5272\nEREV_SENTINEL=do-not-print\n", encoding="utf-8")
        run_dir = scratch / "run"
        run_dir.mkdir()
        # No live process has this id, so status reports the port without probing readiness.
        (run_dir / "web.pid").write_text("99999999\n", encoding="utf-8")

        def status(**values: str) -> str:
            result = subprocess.run(
                [*PROC, "status"],
                cwd=ROOT,
                env=_port_env(EREV_RUN_DIR=str(run_dir), **values),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        from_file = status(EREV_DOTENV=str(dotenv))
        assert from_file == "web pid=99999999 stale port=5272 ready=-\n"
        assert "do-not-print" not in from_file
        assert status() == "web pid=99999999 stale port=5270 ready=-\n"
        exported = status(EREV_DOTENV=str(dotenv), EREV_WEB_PORT="5273")
        assert exported == "web pid=99999999 stale port=5273 ready=-\n"
