"""Container heartbeat probe without importing the CLI, worker handlers or provider adapters."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from erev_api.clock import Clock, SystemClock

HEARTBEAT_MAX_AGE: Final = timedelta(seconds=60)


def heartbeat_is_fresh(path: Path, clock: Clock) -> bool:
    """Whether the heartbeat file was touched less than 60 seconds ago (DPL-02 health check)."""
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except FileNotFoundError:
        return False
    return clock.now() - modified < HEARTBEAT_MAX_AGE


def main() -> int:
    path = Path(os.environ.get("EREV_RUN_DIR", ".run")) / "worker.heartbeat"
    if not heartbeat_is_fresh(path, SystemClock()):
        sys.stdout.write("worker heartbeat is missing or older than 60 seconds\n")
        return 1
    sys.stdout.write("worker heartbeat is fresh\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
