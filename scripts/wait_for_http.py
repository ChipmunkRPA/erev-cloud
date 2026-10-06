#!/usr/bin/env python3
"""Poll a loopback readiness URL or a heartbeat file (docs/dev-guide.md §3.1; DG-RUN-10 step 4).

Exit 0 when ready; exit 1 on timeout or when the watched process has exited; exit 2 on bad input.
A timeout of 0 performs a single check.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit


def http_ready(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=2) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def heartbeat_ready(path: Path, max_age: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age
    except FileNotFoundError:
        return False


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?")
    parser.add_argument("--heartbeat-file", type=Path)
    parser.add_argument("--max-age", type=float, default=60.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--pid", type=int)
    args = parser.parse_args(argv)

    if (args.url is None) == (args.heartbeat_file is None):
        print("give exactly one of URL or --heartbeat-file", file=sys.stderr)
        return 2
    if args.url is not None and urlsplit(args.url).hostname != "127.0.0.1":
        print("readiness URLs must use host 127.0.0.1", file=sys.stderr)
        return 2

    deadline = time.monotonic() + args.timeout
    while True:
        if args.url is not None:
            ready = http_ready(args.url)
        else:
            ready = heartbeat_ready(args.heartbeat_file, args.max_age)
        if ready:
            return 0
        if args.pid is not None and not pid_alive(args.pid):
            return 1
        if time.monotonic() >= deadline:
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
