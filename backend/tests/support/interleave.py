"""Participant-bound lock-wait observation for two-session interleaving tests (dev-guide
DG-KRN-DB-08 rev 1.36; D-98 candidates 101c (d) and 101d; lane P5 slices P5-LOCK-R3c / R3d).

A holder session takes a row lock; a request runs in another connection and must be observed
WAITING for it before the test's next step. The observation names both participants: one of the
request's own backends (every connection checked out of the app engine while the observation is
open, by ``pg_backend_pid``) blocked with ``wait_event_type = 'Lock'`` by the holder's backend
(``pg_blocking_pids``). A sleep, or any same-database waiter whose SQL happens to mention a table,
proves nothing (Codex packets 1130 and 1304).

Every read of ``pg_stat_activity`` here goes through :func:`fresh_activity` (lane FIX-A; the
cause READ-SIDE-BLOCK-1 had left OPEN). PostgreSQL copies the backend status array ONCE per
transaction — ``state``, ``query``, ``xact_start`` and ``query_start`` are read from that copy
until the transaction ends or ``pg_stat_clear_snapshot()`` is called — while ``wait_event_type``
/ ``wait_event`` (read from the live PGPROC), ``pg_locks`` and ``pg_blocking_pids`` are live. The
holder's transaction is open for the whole observation, so an un-refreshed poll pairs a LIVE Lock
wait with the statement the backend was executing at the holder's FIRST read of the view: the
"blocked" ``SET TRANSACTION READ ONLY``, attachments ``SELECT``, idempotency ``INSERT`` and idle
``COMMIT`` of integrated batches #6 / #7 were that stale text, never a read-side lock (measured
on PostgreSQL 17.11, ``stats_fetch_consistency = cache``: the same transaction read ``idle`` /
the previous statement beside ``wait_event_type = 'Lock'`` until the snapshot was discarded).
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from erev_api.db.session import app_engine
from sqlalchemy import Integer, bindparam, event, text
from sqlalchemy.dialects.postgresql import ARRAY

BLOCKED_BY_HOLDER = text(
    "SELECT pid, wait_event, query FROM pg_stat_activity WHERE pid = ANY(:pids) "
    "AND wait_event_type = 'Lock' AND :holder = ANY(pg_blocking_pids(pid))"
).bindparams(bindparam("pids", type_=ARRAY(Integer)), bindparam("holder", type_=Integer))
MY_PID = text("SELECT pg_backend_pid()")
CLEAR_SNAPSHOT = text("SELECT pg_stat_clear_snapshot()")


def fresh_activity(holder: Any, statement: Any, params: Mapping[str, Any]) -> Any:
    """Execute an activity read on the holder's session against a FRESH statistics snapshot (the
    module docstring): the holder's per-transaction copy of the backend status array is discarded
    first, so ``query`` is the statement the backend is in NOW — the one its live Lock wait
    belongs to. Discarding the snapshot releases nothing: the holder's transaction and its locks
    stand."""
    holder.execute(CLEAR_SNAPSHOT)
    return holder.execute(statement, params)


class RequestBackends:
    """The PostgreSQL backend pids of every connection checked out of the app engine while the
    observation is open — the request's, and the holder's own (excluded by pid). ``checkouts`` is
    the pool's checkout map (D-98 candidate 147): pid → the checking-out thread and the checkout
    times, so a diagnostic can say which request-side call a backend served."""

    def __init__(self) -> None:
        self.pids: set[int] = set()
        self.checkouts: dict[int, list[tuple[str, str]]] = {}

    def __call__(self, dbapi_connection: Any, connection_record: Any, proxy: Any) -> None:
        pid = int(dbapi_connection.info.backend_pid)
        self.pids.add(pid)
        self.checkouts.setdefault(pid, []).append(
            (threading.current_thread().name, datetime.now(UTC).isoformat(timespec="milliseconds"))
        )

    def checkout_map(self) -> str:
        return "\n".join(
            f"pid={pid} checkouts={[f'{name}@{at}' for name, at in entries]}"
            for pid, entries in sorted(self.checkouts.items())
        )


@contextmanager
def observing_checkouts() -> Iterator[RequestBackends]:
    """Record the backend pid of every app-engine connection checked out inside the block."""
    backends = RequestBackends()
    engine = app_engine()
    event.listen(engine, "checkout", backends)
    try:
        yield backends
    finally:
        event.remove(engine, "checkout", backends)


def backend_pid(session: Any) -> int:
    """The PostgreSQL backend pid of ``session``'s connection (the holder)."""
    return int(session.execute(MY_PID).scalar_one())


BLOCKED_WAITERS = text(
    "SELECT pid, wait_event, query, pg_blocking_pids(pid) AS blockers FROM pg_stat_activity "
    "WHERE pid = ANY(:pids) AND wait_event_type = 'Lock'"
).bindparams(bindparam("pids", type_=ARRAY(Integer)))
LOCKS_OF = text(
    "SELECT l.pid, l.locktype, l.relation::regclass::text AS relation, l.mode, l.granted, "
    "l.classid, l.objid, l.objsubid, l.transactionid::text AS transactionid, "
    "l.virtualtransaction, l.page AS page_no, l.tuple AS tuple_no, a.state, a.xact_start, "
    "a.query_start, "
    "a.wait_event_type, a.wait_event, a.backend_xid::text AS backend_xid, a.application_name, "
    "pg_blocking_pids(l.pid) AS blockers, left(a.query, 200) AS query FROM pg_locks l "
    "JOIN pg_stat_activity a ON a.pid = l.pid WHERE l.pid = ANY(:pids) "
    "ORDER BY l.pid, l.granted, l.locktype"
).bindparams(bindparam("pids", type_=ARRAY(Integer)))
DIAGNOSTICS_DIR = Path(__file__).resolve().parents[2] / ".run" / "diagnostics"


def _transitive_blockers(blockers_of: Mapping[int, Iterable[int]], holder_pid: int) -> set[int]:
    """The waiters blocked by the holder DIRECTLY or through other waiters: PostgreSQL queues row
    lockers on a TUPLE lock, so the second waiter for a row is reported blocked by the FIRST waiter
    (``pg_blocking_pids``), not by the transaction that holds the row (integrated batch #6 on main
    9e7d1031; P5 record). Pure, so the CPU suite pins the closure."""
    chained = {holder_pid}
    changed = True
    while changed:
        changed = False
        for pid, blockers in blockers_of.items():
            if pid not in chained and any(b in chained for b in blockers):
                chained.add(pid)
                changed = True
    chained.discard(holder_pid)
    return chained


def format_lock_rows(rows: Iterable[Any]) -> str:
    """One line per ``pg_locks`` × ``pg_stat_activity`` row (D-98 candidate 147): locktype, mode,
    granted, relation, the advisory key (classid / objid / objsubid), transactionid,
    virtualtransaction, page / tuple (read as ``page_no`` / ``tuple_no`` — a SQLAlchemy ``Row``'s
    ``.tuple`` is a METHOD, Codex 2239 ROW-1), the backend's state, xact_start, query_start, wait
    event, backend_xid, application_name, its blockers and its statement. Pure — pinned on CPU."""
    return "\n".join(
        f"pid={r.pid} {r.locktype} rel={r.relation} mode={r.mode} granted={r.granted} "
        f"advisory=({r.classid},{r.objid},{r.objsubid}) xid={r.transactionid} "
        f"vxid={r.virtualtransaction} page/tuple={r.page_no}/{r.tuple_no} state={r.state} "
        f"xact_start={r.xact_start} query_start={r.query_start} "
        f"wait={r.wait_event_type}/{r.wait_event} backend_xid={r.backend_xid} "
        f"app={r.application_name!r} blockers={list(r.blockers or [])} query={r.query!r}"
        for r in rows
    )


def lock_dump(holder: Any, *, pids: Iterable[int]) -> str:
    """The lock evidence of the named backends, executed on the holder's connection."""
    return format_lock_rows(fresh_activity(holder, LOCKS_OF, {"pids": sorted(set(pids))}).all())


def _unavailable(what: str, exc: BaseException) -> str:
    return f"({what} unavailable: {exc!r})"


def record_observation(
    holder: Any,
    *,
    holder_pid: int,
    backends: RequestBackends,
    waiters: Mapping[int, Iterable[int]],
    label: str,
) -> str:
    """READ-SIDE-BLOCK-1 (D-98 candidate 147): at EVERY observation — success or failure — the
    lock evidence of each observed waiter, each pid in its ``pg_blocking_pids`` and the holder,
    plus the pool's checkout map, written to the test output and appended under
    ``.run/diagnostics/`` (the printed form reaches a ci log only for a failed case; the file is
    the success-path evidence). Returns the text. FAIL-SOFT (Codex 2239 FAILSOFT-1): this function
    never raises — the evidence query runs inside a SAVEPOINT on the holder's session, so a failing
    query rolls back to the savepoint and the holder's transaction and locks stand (no commit, no
    retry); formatting, the output write and the file write are each guarded and a failure is
    written into the text — the caller's poll result or timeout assertion is never replaced."""
    pids = {holder_pid, *waiters}
    for blockers in waiters.values():
        pids.update(int(b) for b in blockers)
    try:
        with holder.begin_nested():  # a savepoint: a failed diagnostic never aborts the holder
            evidence = lock_dump(holder, pids=pids)
    except Exception as exc:  # noqa: BLE001 — the diagnostic must not fail the observation
        evidence = _unavailable("lock evidence", exc)
    try:
        checkouts = backends.checkout_map()
    except Exception as exc:  # noqa: BLE001
        checkouts = _unavailable("checkout map", exc)
    text_ = (
        f"--- interleave observation [{label}] holder={holder_pid} waiters={sorted(waiters)} "
        f"at {datetime.now(UTC).isoformat(timespec='milliseconds')}\n"
        + evidence
        + "\n--- pool checkouts\n"
        + checkouts
    )
    try:
        sys.stdout.write(text_ + "\n")  # the test output (pytest shows a FAILED case's stdout)
    except Exception as exc:  # noqa: BLE001
        text_ += "\n" + _unavailable("test output", exc)
    try:
        DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        (DIAGNOSTICS_DIR / f"interleave-{label}-{stamp}.txt").write_text(text_ + "\n")
    except Exception as exc:  # noqa: BLE001 — the evidence still stands in the test output
        note = "(diagnostics file not written: " + repr(exc) + ")"
        text_ += "\n" + note
        try:
            sys.stdout.write(note + "\n")
        except Exception:  # noqa: BLE001, S110 — nothing left to report to
            pass
    return text_


def _record_population(
    holder: Any,
    *,
    holder_pid: int,
    backends: RequestBackends,
    pids: Iterable[int],
    recorded: set[int],
) -> None:
    """Codex 2239 COVERAGE-1: every captured backend currently in a Lock wait — whoever blocks it —
    is recorded at its first observation, independently of the wait's eligibility and count rules.
    Fail-soft like :func:`record_observation` (a failing population read is itself recorded)."""
    try:
        with holder.begin_nested():
            rows = fresh_activity(holder, BLOCKED_WAITERS, {"pids": sorted(set(pids))}).all()
    except Exception as exc:  # noqa: BLE001 — never replaces the caller's poll result
        rows = []
        try:
            sys.stdout.write(_unavailable("population read", exc) + "\n")
        except Exception:  # noqa: BLE001, S110
            pass
    waiting = {
        int(row.pid): [int(b) for b in (row.blockers or [])]
        for row in rows
        if int(row.pid) not in recorded
    }
    if waiting:
        recorded.update(waiting)
        record_observation(
            holder,
            holder_pid=holder_pid,
            backends=backends,
            waiters=waiting,
            label="population-" + "-".join(str(pid) for pid in sorted(waiting)),
        )


def await_lock_wait(
    holder: Any,
    *,
    holder_pid: int,
    backends: RequestBackends,
    timeout: float,
    expect: str | None = None,
    while_running: Callable[[], bool] | None = None,
) -> tuple[int, str]:
    """Poll ``pg_stat_activity`` until one of the REQUEST's backends is blocked (``wait_event_type
    = 'Lock'``) by the HOLDER's backend (``pg_blocking_pids``); returns that backend's pid and the
    statement it waits in. With ``expect``, only a blocked statement containing that text counts
    (integrated batch #6: a case saw a backend blocked in an attachments SELECT before — or instead
    of — the group-row lock; that text was the holder's stale activity snapshot, module docstring;
    the diagnostic below names the lock when the expected statement never comes). The interleaving
    step follows only then.

    ``while_running`` (the request thread's ``is_alive``) ends the watch as soon as it answers
    False: a request that has answered can no longer come to wait, so the assertion below is
    raised at once and not after ``timeout``. A caller that passes it can afford a ``timeout``
    as long as a loaded machine needs — measured at load 50: 12.5 seconds from the holder's
    first statement to the request's lock wait — because a request that runs past the holder
    is known by its answer, not by the clock."""
    deadline = time.monotonic() + timeout
    seen: dict[int, str] = {}
    recorded: set[int] = set()
    answered = False
    while time.monotonic() < deadline:
        pids = sorted(backends.pids - {holder_pid})
        if pids:
            _record_population(
                holder, holder_pid=holder_pid, backends=backends, pids=pids, recorded=recorded
            )
            for found in fresh_activity(
                holder, BLOCKED_BY_HOLDER, {"pids": pids, "holder": holder_pid}
            ):
                seen[int(found.pid)] = str(found.query)
                if expect is None or expect in str(found.query).lower():
                    return int(found.pid), str(found.query)
        if while_running is not None and not while_running():
            answered = True
            break
        time.sleep(0.05)
    pids = sorted(backends.pids - {holder_pid})
    raise AssertionError(
        f"none of the request's backends {pids} was blocked by the holder {holder_pid}"
        + (f" in a statement mentioning {expect!r}" if expect else "")
        + (" before the request had answered" if answered else f" within {timeout}s")
        + f"; blocked statements seen: {seen}; locks:\n"
        + lock_dump(holder, pids=[holder_pid, *pids])
    )


def await_lock_waits(
    holder: Any,
    *,
    holder_pid: int,
    backends: RequestBackends,
    count: int,
    timeout: float,
    expect: str | None = None,
) -> dict[int, str]:
    """``count`` DISTINCT request backends observed blocked (``wait_event_type = 'Lock'``) by the
    HOLDER's backend directly OR through a chain of the request's own blocked backends — the
    two-units-of-work interleaving (P5-LOCK-R4: two approvals over the same group rows, both waiting
    for the first shared row on the ruled order). PostgreSQL queues the second row locker on the
    TUPLE lock held by the first waiter, so ``pg_blocking_pids`` names the first waiter, not the
    holder (integrated batch #6 on main 9e7d1031 measured exactly that: "only [A] of [A, B] were
    blocked by the holder"); the closure is :func:`_transitive_blockers`. With ``expect``, only a
    waiter blocked in a statement mentioning that text is counted (integrated batch #7 on main
    104a954c: the closure had counted a captured backend reported blocked in a GET-side ``SET
    TRANSACTION READ ONLY`` — no read-side waiter: the holder's stale activity snapshot, module
    docstring; the others are carried in the failure message with the lock dump). Matches
    ACCUMULATE across poll snapshots: the wait proves ``count`` OBSERVED matching waits, not one
    simultaneous snapshot (Codex 2040). Returns pid → the statement each waits in; the participant
    binding is the captured backends + the known holder."""
    deadline = time.monotonic() + timeout
    found: dict[int, str] = {}
    unexpected: dict[int, str] = {}
    recorded: set[int] = set()
    while time.monotonic() < deadline:
        pids = sorted(backends.pids - {holder_pid})
        if pids:
            waiting = {
                int(row.pid): (str(row.query), [int(b) for b in (row.blockers or [])])
                for row in fresh_activity(holder, BLOCKED_WAITERS, {"pids": pids})
            }
            chained = _transitive_blockers(
                {pid: blockers for pid, (_, blockers) in waiting.items()}, holder_pid
            )
            fresh = [pid for pid in waiting if pid not in recorded]  # the WHOLE population
            if fresh:  # D-98 147 / Codex 2239 COVERAGE-1: independent of eligibility and count
                recorded.update(fresh)
                record_observation(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    waiters={pid: waiting[pid][1] for pid in fresh},
                    label="population-" + "-".join(str(pid) for pid in sorted(fresh)),
                )
            for pid in chained:
                statement = waiting[pid][0]
                if expect is None or expect in statement.lower():
                    found[pid] = statement
                else:
                    unexpected[pid] = statement
            if len(found) >= count:
                return found
        time.sleep(0.05)
    pids = sorted(backends.pids - {holder_pid})
    raise AssertionError(
        f"only {sorted(found)} of the request backends {pids} were blocked by the holder "
        f"{holder_pid} (directly or through the request's own waiters)"
        + (f" in a statement mentioning {expect!r}" if expect else "")
        + f" within {timeout}s (wanted {count}); other blocked statements seen: {unexpected}; "
        f"locks:\n" + lock_dump(holder, pids=[holder_pid, *pids])
    )
