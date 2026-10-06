"""The participant-bound wait's chain closure (tests/support/interleave.py; integrated batch #6 on
main 9e7d1031 returned the two-approvals witness: "only [A] of [A, B] were blocked by the holder" —
PostgreSQL queues the second row locker on the TUPLE lock held by the first waiter, so
``pg_blocking_pids(B)`` names A, not the holder). CPU: the closure is a pure function."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
import support.interleave as interleave
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
from support.interleave import (
    BLOCKED_BY_HOLDER,
    BLOCKED_WAITERS,
    CLEAR_SNAPSHOT,
    LOCKS_OF,
    RequestBackends,
    _transitive_blockers,
    await_lock_wait,
    await_lock_waits,
    format_lock_rows,
    fresh_activity,
    lock_dump,
    record_observation,
)

HOLDER, A, B, C, OTHER = 10978, 10988, 11851, 12000, 500


def test_the_second_waiter_in_the_row_lock_queue_is_blocked_through_the_first() -> None:
    assert _transitive_blockers({A: [HOLDER], B: [A]}, HOLDER) == {A, B}


def test_a_waiter_blocked_by_an_unrelated_backend_is_not_counted() -> None:
    assert _transitive_blockers({A: [HOLDER], B: [OTHER]}, HOLDER) == {A}


def test_a_longer_chain_and_a_cycle_terminate() -> None:
    assert _transitive_blockers({A: [HOLDER], B: [A], C: [B, C]}, HOLDER) == {A, B, C}
    assert _transitive_blockers({A: [B], B: [A]}, HOLDER) == set()


def test_the_holder_is_never_reported_as_a_waiter() -> None:
    assert _transitive_blockers({HOLDER: [A], A: [HOLDER]}, HOLDER) == {A}


def _row(**values: object) -> SimpleNamespace:
    base = dict(
        pid=24786,
        locktype="advisory",
        relation=None,
        mode="ExclusiveLock",
        granted=False,
        classid=1,
        objid=42,
        objsubid=1,
        transactionid=None,
        virtualtransaction="7/123",
        page_no=None,
        tuple_no=None,
        state="active",
        xact_start="2026-09-21T12:04:49+00:00",
        query_start="2026-09-21T12:04:49.500+00:00",
        wait_event_type="Lock",
        wait_event="advisory",
        backend_xid=None,
        application_name="erev-app",
        blockers=[23878],
        query="SET TRANSACTION READ ONLY",
    )
    base.update(values)
    return SimpleNamespace(**base)


def test_the_lock_evidence_names_the_lock_kind_key_and_blockers() -> None:
    """D-98 candidate 147 (READ-SIDE-BLOCK-1): one line per pg_locks × pg_stat_activity row with
    the fields a native run needs to name a lock — the kind, the advisory key, the transaction id,
    the tuple, the backend's state and statement and its blockers."""
    lines = format_lock_rows(
        [
            _row(),
            _row(
                pid=23878,
                locktype="tuple",
                relation="erev.combination_group",
                mode="ExclusiveLock",
                page_no=3,
                tuple_no=7,
                blockers=[10978],
                query="SELECT … FROM erev.combination_group WHERE id = $1::UUID FOR UPDATE",
                classid=None,
                objid=None,
                objsubid=None,
                wait_event="tuple",
            ),
        ]
    ).splitlines()
    assert lines[0] == (
        "pid=24786 advisory rel=None mode=ExclusiveLock granted=False advisory=(1,42,1) xid=None "
        "vxid=7/123 page/tuple=None/None state=active xact_start=2026-09-21T12:04:49+00:00 "
        "query_start=2026-09-21T12:04:49.500+00:00 wait=Lock/advisory backend_xid=None "
        "app='erev-app' blockers=[23878] query='SET TRANSACTION READ ONLY'"
    )
    assert lines[1].startswith(
        "pid=23878 tuple rel=erev.combination_group mode=ExclusiveLock granted=False"
    )
    assert "page/tuple=3/7" in lines[1] and "blockers=[10978]" in lines[1]
    assert format_lock_rows([]) == ""


def test_the_pool_checkout_map_names_the_thread_per_backend() -> None:
    backends = RequestBackends()
    backends(SimpleNamespace(info=SimpleNamespace(backend_pid=24786)), None, None)
    backends(SimpleNamespace(info=SimpleNamespace(backend_pid=24786)), None, None)
    backends(SimpleNamespace(info=SimpleNamespace(backend_pid=23878)), None, None)
    assert backends.pids == {23878, 24786}
    lines = backends.checkout_map().splitlines()
    assert lines[0].startswith("pid=23878 checkouts=[") and lines[1].startswith(
        "pid=24786 checkouts=["
    )
    assert lines[1].count("MainThread@") == 2  # this test's own thread, twice


class _Nested:
    """A stand-in for ``Session.begin_nested()``: records whether the savepoint was rolled back."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def __enter__(self) -> _Nested:
        self.log.append("savepoint")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.log.append("rollback" if exc_type is not None else "release")
        return False  # the exception propagates to record_observation's guard


class _Rows:
    """A result stand-in: iterable and ``.all()``-able, as the waits use it both ways."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def __iter__(self) -> Any:
        return iter(self.rows)

    def all(self) -> list[Any]:
        return list(self.rows)


class _Holder:
    """A holder session stand-in: answers the population read (A → holder, B → OTHER), the
    holder-linked read (A only) and the evidence query; raises on the evidence query when told.
    ``statements`` is every statement executed, in order (the snapshot discard included)."""

    def __init__(self, *, evidence_fails: bool = False) -> None:
        self.log: list[str] = []
        self.statements: list[object] = []
        self.evidence_fails = evidence_fails

    def begin_nested(self) -> _Nested:
        return _Nested(self.log)

    def execute(self, statement: object, params: dict[str, object] | None = None) -> object:
        self.statements.append(statement)
        if statement is CLEAR_SNAPSHOT:
            return None
        assert params is not None
        if statement is BLOCKED_WAITERS:
            rows = [
                SimpleNamespace(
                    pid=A,
                    wait_event="tuple",
                    query="SELECT … FROM erev.combination_group … FOR UPDATE",
                    blockers=[HOLDER],
                ),
                SimpleNamespace(
                    pid=B,
                    wait_event="relation",
                    query="SET TRANSACTION READ ONLY",
                    blockers=[OTHER],
                ),
            ]
            return _Rows(rows)
        if statement is BLOCKED_BY_HOLDER:
            return [
                SimpleNamespace(
                    pid=A,
                    wait_event="tuple",
                    query="SELECT … FROM erev.combination_group … FOR UPDATE",
                )
            ]
        if statement is LOCKS_OF:
            if self.evidence_fails:
                raise RuntimeError("pg_locks read refused")
            pids = list(params["pids"])  # type: ignore[arg-type]
            return SimpleNamespace(all=lambda: [_row(pid=pid, blockers=[]) for pid in pids])
        raise AssertionError(f"unexpected statement {statement!r}")


def test_the_counting_wait_records_the_whole_population_not_only_the_holder_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 2239 COVERAGE-1: A waits on the holder, B waits on an UNRELATED backend. `count=1`
    is satisfied by A exactly as before (B is not eligible), yet the recorded observation names
    A, B, OTHER and the holder — the evidence covers the whole observed population."""
    recorded: list[dict[int, list[int]]] = []

    def recorder(
        holder: object,
        *,
        holder_pid: int,
        backends: object,
        waiters: dict[int, list[int]],
        label: str,
    ) -> str:
        recorded.append({pid: list(blockers) for pid, blockers in waiters.items()})
        return label

    monkeypatch.setattr(interleave, "record_observation", recorder)
    backends = RequestBackends()
    backends.pids.update({A, B})
    holder = _Holder()
    found = await_lock_waits(holder, holder_pid=HOLDER, backends=backends, count=1, timeout=1.0)
    assert found == {
        A: "SELECT … FROM erev.combination_group … FOR UPDATE"
    }  # count / eligibility unchanged
    assert recorded == [{A: [HOLDER], B: [OTHER]}]  # B and OTHER are in the evidence
    assert holder.log == []  # the recorder was stubbed: no savepoint needed here


def test_a_failing_evidence_query_is_isolated_in_a_savepoint_and_never_raises() -> None:
    """Codex 2239 FAILSOFT-1: the evidence query fails; the savepoint is rolled back (the
    holder's transaction and locks stand), the failure is written into the text, nothing raises."""
    holder = _Holder(evidence_fails=True)
    backends = RequestBackends()
    text_ = record_observation(
        holder, holder_pid=HOLDER, backends=backends, waiters={A: [HOLDER]}, label="t"
    )
    assert holder.log == ["savepoint", "rollback"]
    assert "(lock evidence unavailable: RuntimeError('pg_locks read refused'))" in text_
    assert "--- pool checkouts" in text_


def test_a_failing_output_write_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Broken:
        def write(self, _: str) -> int:
            raise OSError("stdout closed")

    monkeypatch.setattr(interleave.sys, "stdout", _Broken())
    holder = _Holder()
    text_ = record_observation(
        holder, holder_pid=HOLDER, backends=RequestBackends(), waiters={A: [HOLDER]}, label="t"
    )
    assert "(test output unavailable: OSError('stdout closed'))" in text_
    assert holder.log == ["savepoint", "release"]  # the evidence itself was read and released


def test_an_unwritable_diagnostics_dir_never_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setattr(interleave, "DIAGNOSTICS_DIR", blocker / "diagnostics")
    text_ = record_observation(
        _Holder(), holder_pid=HOLDER, backends=RequestBackends(), waiters={A: [HOLDER]}, label="t"
    )
    assert "(diagnostics file not written:" in text_


def test_the_formatter_reads_real_rows_without_the_row_tuple_collision() -> None:
    """Codex 2239 ROW-1: SQLAlchemy 2.0.52's ``Row.tuple`` is a METHOD, so a column named
    ``tuple`` is unreachable as ``row.tuple``; the evidence query aliases ``page_no`` /
    ``tuple_no`` and the formatter reads them. Real ``Row`` objects from SQLAlchemy's own result
    machinery (no database — DG-ARC-05 forbids a sqlite engine), not a SimpleNamespace."""
    keys = [
        "pid",
        "locktype",
        "relation",
        "mode",
        "granted",
        "classid",
        "objid",
        "objsubid",
        "transactionid",
        "virtualtransaction",
        "page_no",
        "tuple_no",
        "tuple",
        "state",
        "xact_start",
        "query_start",
        "wait_event_type",
        "wait_event",
        "backend_xid",
        "application_name",
        "blockers",
        "query",
    ]
    values = (
        23878,
        "tuple",
        "erev.combination_group",
        "ExclusiveLock",
        False,
        None,
        None,
        None,
        None,
        "7/1",
        3,
        7,
        "x",
        "active",
        "2026-09-21T12:04:49",
        "2026-09-21T12:04:49",
        "Lock",
        "tuple",
        None,
        "erev-app",
        [10978],
        "SELECT 1",
    )
    rows = IteratorResult(SimpleResultMetaData(keys), iter([values])).all()
    assert type(rows[0]).__name__ == "Row" and callable(rows[0].tuple)  # the collision
    assert rows[0]._mapping["tuple"] == "x"  # the column is reachable only by mapping key
    line = format_lock_rows(rows)
    assert "page/tuple=3/7" in line and "bound method" not in line
    assert line.startswith(
        "pid=23878 tuple rel=erev.combination_group mode=ExclusiveLock granted=False"
    )
    assert "blockers=[10978]" in line


# --- lane FIX-A: the holder's activity snapshot (the cause READ-SIDE-BLOCK-1 left OPEN) -----------

ACTIVITY_READS = (BLOCKED_WAITERS, BLOCKED_BY_HOLDER, LOCKS_OF)
GROUP_ROW = "SELECT … FROM erev.combination_group … FOR UPDATE"


def _unrefreshed(statements: list[object]) -> list[int]:
    """The positions of activity reads NOT immediately preceded by the snapshot discard."""
    return [
        index
        for index, statement in enumerate(statements)
        if statement in ACTIVITY_READS
        and (index == 0 or statements[index - 1] is not CLEAR_SNAPSHOT)
    ]


def test_fresh_activity_discards_the_snapshot_and_then_reads() -> None:
    holder = _Holder()
    rows = fresh_activity(holder, BLOCKED_BY_HOLDER, {"pids": [A], "holder": HOLDER})
    assert holder.statements == [CLEAR_SNAPSHOT, BLOCKED_BY_HOLDER]
    assert [row.pid for row in rows] == [A]
    assert str(CLEAR_SNAPSHOT) == "SELECT pg_stat_clear_snapshot()"


def test_every_activity_read_of_the_waits_and_the_evidence_is_refreshed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """``pg_stat_activity``'s state / query are one copy per transaction and the holder's
    transaction is open for the whole observation: the single wait, the counting wait, the
    population read and the evidence query each discard the snapshot immediately before reading."""
    monkeypatch.setattr(interleave, "DIAGNOSTICS_DIR", tmp_path / "diagnostics")
    backends = RequestBackends()
    backends.pids.update({A, B})
    single = _Holder()
    assert await_lock_wait(
        single, holder_pid=HOLDER, backends=backends, timeout=1.0, expect="combination_group"
    ) == (A, GROUP_ROW)
    counting = _Holder()
    assert await_lock_waits(
        counting, holder_pid=HOLDER, backends=backends, count=1, timeout=1.0
    ) == {A: GROUP_ROW}
    evidence = _Holder()
    assert lock_dump(evidence, pids=[HOLDER, A]).count("pid=") == 2
    for holder in (single, counting, evidence):
        reads = [s for s in holder.statements if s in ACTIVITY_READS]
        assert reads and _unrefreshed(holder.statements) == [], holder.statements
    assert BLOCKED_BY_HOLDER in single.statements and BLOCKED_WAITERS in single.statements
    assert LOCKS_OF in single.statements and LOCKS_OF in counting.statements  # the evidence


class _FrozenActivity:
    """PostgreSQL's measured behaviour (17.11, ``stats_fetch_consistency = cache``): a
    transaction's FIRST read of ``pg_stat_activity`` fixes every backend's statement text until
    ``pg_stat_clear_snapshot()``; the Lock wait and ``pg_blocking_pids`` are live. The request
    backend A executes ``statements`` in turn — one per read of the clock the helper takes through
    this stand-in — and is blocked by the holder in the last one."""

    def __init__(self, statements: list[str]) -> None:
        self.ahead = list(statements)
        self.current = self.ahead.pop(0)
        self.snapshot: str | None = None
        self.log: list[str] = []

    def begin_nested(self) -> _Nested:
        return _Nested(self.log)

    def _advance(self) -> None:
        if self.ahead:
            self.current = self.ahead.pop(0)

    def execute(self, statement: object, params: dict[str, object] | None = None) -> object:
        if statement is CLEAR_SNAPSHOT:
            self.snapshot = None
            return None
        if self.snapshot is None:
            self.snapshot = self.current  # the per-transaction copy of the status array
        blocked = not self.ahead  # live: A waits for the holder once it is in its last statement
        row = SimpleNamespace(pid=A, wait_event="transactionid", query=self.snapshot)
        self._advance()
        if statement is BLOCKED_BY_HOLDER:
            return [row] if blocked else []
        if statement is BLOCKED_WAITERS:
            row.blockers = [HOLDER]
            return _Rows([row] if blocked else [])
        if statement is LOCKS_OF:
            return SimpleNamespace(all=lambda: [])
        raise AssertionError(f"unexpected statement {statement!r}")


REQUEST_PATH = [
    "INSERT INTO erev.idempotency_record …",
    "SELECT … approval_delegation …",
    GROUP_ROW,
]


def test_the_wait_names_the_statement_the_backend_is_blocked_in_not_the_first_one_seen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The b9 node ``test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append``: the
    holder's first read came while the approval was still in its idempotency INSERT; the approval
    then blocked on the group row, and every later poll paired that LIVE wait with the INSERT's
    text — "none of the request's backends was blocked … in a statement mentioning
    'combination_group'" after 20 s, with pg_locks showing the wait on the holder. Refreshed, the
    wait returns the group-row statement."""
    monkeypatch.setattr(interleave, "DIAGNOSTICS_DIR", tmp_path / "diagnostics")
    backends = RequestBackends()
    backends.pids.add(A)
    holder = _FrozenActivity(REQUEST_PATH)
    assert await_lock_wait(
        holder, holder_pid=HOLDER, backends=backends, timeout=2.0, expect="combination_group"
    ) == (A, GROUP_ROW)
    counted = await_lock_waits(
        _FrozenActivity(REQUEST_PATH),
        holder_pid=HOLDER,
        backends=backends,
        count=1,
        timeout=2.0,
        expect="combination_group",
    )
    assert counted == {A: GROUP_ROW}


def test_the_stand_in_reproduces_the_stale_statement_without_the_discard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The negative control of the witness above: with the discard removed the same stand-in
    answers the FIRST statement for the blocked backend on every poll, and the wait times out —
    the defect, reproduced on CPU."""
    monkeypatch.setattr(interleave, "DIAGNOSTICS_DIR", tmp_path / "diagnostics")
    monkeypatch.setattr(
        interleave,
        "fresh_activity",
        lambda holder, statement, params: holder.execute(statement, params),
    )
    backends = RequestBackends()
    backends.pids.add(A)
    with pytest.raises(AssertionError) as refused:
        await_lock_wait(
            _FrozenActivity(REQUEST_PATH),
            holder_pid=HOLDER,
            backends=backends,
            timeout=0.4,
            expect="combination_group",
        )
    assert "blocked statements seen: {" + str(A) + ": 'INSERT INTO erev.idempotency_record" in str(
        refused.value
    )


def test_the_watch_ends_with_the_requests_answer_and_not_with_the_clock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """``while_running`` (item FILE-SHRED-DURABLE-ORDER-1; ``support.shred_in_flight``): a request
    that has answered can no longer come to wait, so the watch ends at its answer — after one
    look, far from the timeout — and says so. A request that still runs is watched on until it
    is blocked, as without the argument; and without the argument the clock ends the watch, as
    before. So a caller may give a loaded machine minutes without paying them when the request
    runs past the holder."""
    monkeypatch.setattr(interleave, "DIAGNOSTICS_DIR", tmp_path / "diagnostics")
    backends = RequestBackends()
    backends.pids.add(A)
    never_blocked = ["SELECT 1"] * 1000
    looks: list[bool] = []

    def has_answered() -> bool:
        looks.append(False)
        return False

    started = time.monotonic()
    with pytest.raises(AssertionError) as refused:
        await_lock_wait(
            _FrozenActivity(never_blocked),
            holder_pid=HOLDER,
            backends=backends,
            timeout=600.0,
            expect="combination_group",
            while_running=has_answered,
        )
    assert looks == [False] and time.monotonic() - started < 60.0
    assert "before the request had answered" in str(refused.value)
    assert "within 600.0s" not in str(refused.value)

    assert await_lock_wait(
        _FrozenActivity(REQUEST_PATH),
        holder_pid=HOLDER,
        backends=backends,
        timeout=2.0,
        expect="combination_group",
        while_running=lambda: True,
    ) == (A, GROUP_ROW)

    with pytest.raises(AssertionError) as timed:
        await_lock_wait(
            _FrozenActivity(never_blocked),
            holder_pid=HOLDER,
            backends=backends,
            timeout=0.3,
            expect="combination_group",
        )
    assert "within 0.3s" in str(timed.value)
    assert "before the request had answered" not in str(timed.value)
