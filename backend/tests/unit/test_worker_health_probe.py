"""The container health probe keeps the worker's heartbeat boundary without loading its handlers."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from erev_api.clock import FrozenClock
from erev_api.worker_health import heartbeat_is_fresh


def test_heartbeat_boundary(clock: FrozenClock, tmp_path: Path) -> None:
    path = tmp_path / "worker.heartbeat"
    assert not heartbeat_is_fresh(path, clock)
    path.touch()
    for age in (0, 15, 59, 60, 61):
        stamp = (clock.now() - timedelta(seconds=age)).timestamp()
        os.utime(path, (stamp, stamp))
        assert heartbeat_is_fresh(path, clock) is (age < 60)


@pytest.mark.parametrize("state,expected", [("missing", 1), ("fresh", 0), ("old", 1)])
def test_probe_process_does_not_load_worker_or_cli(
    tmp_path: Path, state: str, expected: int
) -> None:
    heartbeat = tmp_path / "worker.heartbeat"
    if state != "missing":
        heartbeat.touch()
        if state == "old":
            os.utime(heartbeat, (1, 1))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from erev_api.worker_health import main
result = main()
assert 'erev_api.worker' not in sys.modules
assert 'erev_api.cli' not in sys.modules
assert not any(name.startswith('erev_api.adapters.') for name in sys.modules)
raise SystemExit(result)
""",
        ],
        env={**os.environ, "EREV_RUN_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
