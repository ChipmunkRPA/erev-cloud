#!/usr/bin/env python3
"""Read-only lane-isolation report for a worktree's databases (common terms, 2026-09-19 amendment).

Prints ONLY named non-secret fields: backend PID, database name, role, application name, backend
start time, state; and, for processes whose working directory is the worktree, PID, parent PID,
start time, the executable's base name and the recognised stage word. It never prints a DSN, an
environment dump or full command arguments. The DSN is read from the environment variable named by
``--dsn-env`` (default ``EREV_TEST_DB_OWNER_URL``) or, with ``--dotenv``, from that file; it is used
to connect and nothing else. Any failure is reported by exception type only. Every emitted line
passes through ``redact_dsn`` as a second guard.

usage: lane_isolation.py --worktree /path/to/worktree [--dsn-env NAME] [--dotenv .env]
                         [--database-prefix erev_rv_l3_]
exit 0 when no session other than this check's exists on the matching databases and no other
gate/pytest/make process runs from the worktree; exit 1 otherwise; exit 2 on a connection failure.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

# postgresql://user:password@host, postgresql+psycopg://…, postgres://…, and key=value DSNs.
_URL_CREDENTIALS = re.compile(r"(?i)\b(postgres(?:ql)?(?:\+[a-z0-9_]+)?://)([^/\s@]*)@")
_URL_ANY = re.compile(r"(?i)\bpostgres(?:ql)?(?:\+[a-z0-9_]+)?://\S+")
_KV_SECRET = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|key)\s*=\s*\S+")
REDACTED = "[REDACTED]"
STAGE_WORDS = ("gate_report", "pytest", "make", "parity", "properties", "erev", "python")


def redact_dsn(text: str) -> str:
    """Mask any connection string or key=value secret in ``text``; the scheme and host survive."""
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{REDACTED}@", text)
    text = _URL_ANY.sub(lambda m: m.group(0) if REDACTED in m.group(0) else REDACTED, text)
    return _KV_SECRET.sub(lambda m: f"{m.group(1)}={REDACTED}", text)


def say(line: str, out: Callable[[str], None] = print) -> None:
    out(redact_dsn(line))


def describe_failure(exc: BaseException) -> str:
    """Exception type only: driver messages can quote the DSN or bound values."""
    return f"connection failed: {type(exc).__name__}"


def normalise(dsn: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql://" + dsn[len(prefix) :]
    return dsn


def dsn_from(name: str, dotenv: Path | None) -> str | None:
    value = os.environ.get(name)
    if value is None and dotenv is not None and dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
    return value


def sessions(connect: Callable[..., Any], dsn: str, prefix: str) -> list[tuple[Any, ...]]:
    """(pid, datname, usename, application_name, backend_start, state) of every other session."""
    conn = connect(normalise(dsn), application_name="lane-isolation", connect_timeout=10)
    with conn:
        conn.read_only = True
        me = conn.execute("select pg_backend_pid()").fetchone()[0]
        rows = conn.execute(
            "select pid, datname, usename, application_name, backend_start, state "
            "from pg_stat_activity where datname like %s and pid <> %s order by datname, pid",
            (prefix + "%", me),
        ).fetchall()
    return [tuple(row) for row in rows]


def worktree_processes(
    worktree: Path, ps_lines: Iterable[str], cwd_of: Callable[[str], str]
) -> list[str]:
    """Named fields only for processes whose cwd is the worktree and whose command names a stage
    word."""
    found: list[str] = []
    for line in ps_lines:
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        pid, ppid, start, command = parts[0], parts[1], " ".join(parts[2:7]), parts[7]
        try:
            cwd = cwd_of(pid)
        except Exception:  # noqa: BLE001 - a vanished process is not an error
            continue
        if not cwd.startswith(str(worktree)):
            continue
        words = [w for w in STAGE_WORDS if w in command]
        if not words:
            continue
        executable = Path(command.split()[0]).name
        found.append(f"  pid={pid} ppid={ppid} start={start} exe={executable} stage={words[0]}")
    return found


def _ps_lines() -> list[str]:
    return subprocess.run(
        ["ps", "-eo", "pid=,ppid=,lstart=,command="], capture_output=True, text=True
    ).stdout.splitlines()


def _cwd_of(pid: str) -> str:
    out = subprocess.run(
        ["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"], capture_output=True, text=True, timeout=5
    ).stdout
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return ""


def main(
    argv: Sequence[str] | None = None,
    *,
    connect: Callable[..., Any] | None = None,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--dsn-env", default="EREV_TEST_DB_OWNER_URL")
    parser.add_argument("--dotenv", type=Path, default=None)
    parser.add_argument("--database-prefix", default=None)
    args = parser.parse_args(argv)
    worktree = args.worktree.resolve()
    dsn = dsn_from(args.dsn_env, args.dotenv)
    if not dsn:
        say(f"{args.dsn_env} is not set", out)
        return 2
    if connect is None:
        import psycopg  # noqa: PLC0415 - optional at import time so the redaction test needs no driver

        connect = psycopg.connect
    prefix = args.database_prefix
    if prefix is None:
        # the database name of the DSN without its trailing environment suffix (…_test → …_)
        name = normalise(dsn).rsplit("/", 1)[-1].split("?", 1)[0]
        prefix = name.rsplit("_", 1)[0] + "_" if "_" in name else name
    try:
        rows = sessions(connect, dsn, prefix)
    except Exception as exc:  # noqa: BLE001 - reported by type only, never by message
        say(describe_failure(exc), out)
        return 2
    say(f"sessions on {prefix}* other than this check: {len(rows)}", out)
    for pid, datname, usename, app, start, state in rows:
        started = start.strftime("%H:%M:%S") if start is not None else "n/a"
        say(
            f"  backend={pid} db={datname} role={usename} app={app!r} start={started} "
            f"state={state or 'n/a'}",
            out,
        )
    procs = worktree_processes(worktree, _ps_lines(), _cwd_of)
    own = str(os.getpid())
    procs = [p for p in procs if f"pid={own} " not in p]
    say(f"gate/pytest/make processes with cwd {worktree.name}: {len(procs)}", out)
    for line in procs:
        say(line, out)
    return 0 if not rows and not procs else 1


if __name__ == "__main__":
    sys.exit(main())
