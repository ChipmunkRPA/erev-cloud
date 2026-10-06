"""Which lock a close command takes on the period's state row (04 DB-07 rev 1.113; dev-guide
DG-KRN-DB-08 (1a); supervisor rulings R-31 and R-40 (b) of 2026-09-30). No database: the emitted
statements of ``erev_api.domain.close.commands`` over an inert statement-capturing session,
compiled for PostgreSQL.

The DB-07 guards hold the state row ``FOR SHARE`` for every line a posting inserts. A change of
the state takes the row ``FOR UPDATE``; a command that leaves the state as it is pins it ``FOR
SHARE`` — it neither waits for the postings in flight nor makes one wait — and a request for a
lock, a permanent lock or a reopen first takes an advisory lock on the period state; the lock
decision takes the next period's row only when that period is ``future`` — directly after the
closing period's row, before its gates and its freeze (04 DB-07 rev 1.182; supervisor ruling
R-116 (h)) — and defers the SCH-06 re-marking of the period it opens instead of taking
``combination_group`` rows (supervisor ruling R-101 (a); ``reference.period_redirty_job``). A lock
decision of a period of the primary book takes the LEGACY book's row of that next period by the
same rule and opens it as well (04 DB-07 rev 1.214; PRD BR-CLS-03 rev 1.143; item
PER-LEGACY-POSTING-PERIOD-1). The locking read of either row runs inside a savepoint, and a row
that is no longer ``future`` under the lock is given back with it (04 DB-07 rev 1.229; dev-guide
DG-KRN-DB-08 (1a) rev 1.218; finding F11 of the independent review of 2026-10-01).
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.close import commands, gates
from erev_api.enums import JobKind, PeriodState
from erev_api.problems import Problem
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.dml import Insert, Update

NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
TENANT = UUID("00000000-0000-0000-0000-00000000aa01")
STATE = UUID("00000000-0000-0000-0000-00000000cc01")
NEXT_STATE = UUID("00000000-0000-0000-0000-00000000cc02")
ENTITY = UUID("00000000-0000-0000-0000-0000000000e1")
PERIOD = UUID("00000000-0000-0000-0000-000000000f09")
NEXT_PERIOD = UUID("00000000-0000-0000-0000-000000000f10")
LEGACY_NEXT_STATE = UUID("00000000-0000-0000-0000-00000000cc03")
ACTOR = UUID("00000000-0000-0000-0000-0000000000a2")


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


class _Result:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return self.row

    def scalar(self) -> Any:
        return self.row

    def scalar_one_or_none(self) -> Any:
        return self.row


@dataclass
class _Session:
    """Captures every statement in emission order; a SELECT answers the next row of ``rows``."""

    rows: list[Any] = field(default_factory=list)
    statements: list[Any] = field(default_factory=list)
    savepoints: list[str] = field(default_factory=list)

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.statements.append(statement)
        if isinstance(statement, Insert | Update):
            return _Result(None)
        return _Result(self.rows.pop(0) if self.rows else None)

    @contextmanager
    def begin_nested(self) -> Iterator[None]:
        """A savepoint: released when its block ends, rolled back when the block raises — and
        with it, in PostgreSQL, every row lock taken inside it."""
        self.savepoints.append("begun")
        try:
            yield
        except BaseException:
            self.savepoints.append("rolled back")
            raise
        self.savepoints.append("released")


@dataclass
class _Uow:
    session: _Session
    now: datetime = NOW
    principal: Any = field(
        default_factory=lambda: SimpleNamespace(
            tenant_id=TENANT, id=ACTOR, kind=SimpleNamespace(value="USER")
        )
    )
    ctx: Any = None
    audits: list[dict[str, Any]] = field(default_factory=list)
    deferred: list[tuple[JobKind, dict[str, Any]]] = field(default_factory=list)
    subjects: list[tuple[Any, Any]] = field(default_factory=list)

    def audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)

    def defer(self, kind: JobKind, params: Mapping[str, Any], **kwargs: Any) -> Mapping[str, Any]:
        self.deferred.append((kind, dict(params)))
        self.subjects.append((kwargs.get("subject_type"), kwargs.get("subject_id")))
        return {"kind": kind.value, "params": dict(params)}


def _scope() -> gates.PeriodScope:
    return gates.PeriodScope(
        state_id=STATE,
        entity_id=ENTITY,
        entity_code="AVM-US",
        functional_currency="USD",
        book_code="ASC606",
        period_id=PERIOD,
        period_key="FY2026-P09",
        period_name="September 2026",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        state=PeriodState.CLOSING.value,
        current_lock_id=None,
        row_version=4,
    )


def _next(state: PeriodState) -> dict[str, Any]:
    return {
        "id": NEXT_STATE,
        "entity_id": ENTITY,
        "book_code": "ASC606",
        "period_id": NEXT_PERIOD,
        "state": state.value,
        "row_version": 1,
        "period_name": "October 2026",
    }


def _selects(session: _Session) -> list[str]:
    return [_sql(s) for s in session.statements if not isinstance(s, Insert | Update)]


def test_a_change_of_the_state_takes_the_row_for_update() -> None:
    """The lock, permanent-lock and reopen decisions read the period through
    ``gates.period_scope(lock=True)``: ``FOR UPDATE`` of the state row, so they wait for the
    postings in flight, whose lines hold it ``FOR SHARE``."""
    session = _Session()
    assert gates.period_scope(session, STATE, lock=True) is None  # type: ignore[arg-type]
    (locked,) = _selects(session)
    assert locked.endswith("FOR UPDATE OF period_state")
    plain = _Session()
    assert gates.period_scope(plain, STATE) is None  # type: ignore[arg-type]
    assert "FOR " not in _selects(plain)[0]


@pytest.mark.parametrize("one_request", [False, True])
def test_a_command_that_leaves_the_state_as_it_is_pins_the_row_for_share(
    one_request: bool,
) -> None:
    """``_pinned_scope`` (the checklist sign-off and waiver, the three requests): the state row
    ``FOR SHARE`` — compatible with the guards' row lock — and, for a request, the advisory lock
    on the period state FIRST. Fail-first: the row was taken ``FOR UPDATE``, so each of these
    commands waited for the postings in flight, and a request took its ``APPROVAL`` number after
    the row while an auto-approved submission holds the number before its first line."""
    uow = _Uow(_Session())
    with pytest.raises(Problem) as missing:
        commands._pinned_scope(uow, STATE, one_request=one_request)  # type: ignore[arg-type]
    assert missing.value.slug == "not-found"  # the inert session answers no row
    statements = _selects(uow.session)
    pinned = statements[-1]
    assert pinned.endswith("FOR SHARE OF period_state")
    if one_request:
        advisory, _ = statements
        assert "pg_advisory_xact_lock(hashtextextended(" in advisory
        key = uow.session.statements[0].compile(dialect=postgresql.dialect()).params
        assert f"erev:period-request:{STATE}" in key.values()
    else:
        assert len(statements) == 1


def test_the_lock_decision_reads_an_open_next_period_without_a_lock() -> None:
    """BR-CLS-03 under DB-07's lock order: a next period that is already open is read once,
    without a lock, and nothing is written. Fail-first: the row was taken ``FOR UPDATE`` whatever
    its state, which waits for every posting in flight into the open period.

    Since 04 DB-07 rev 1.182 the read is ``_hold_future_next_period``'s, at the decision's start;
    ``_open_next_period`` is handed what that read held — here nothing — and reads no row."""
    uow = _Uow(_Session(rows=[_next(PeriodState.OPEN)]))
    assert commands._hold_future_next_period(uow.session, _scope()) is None  # type: ignore[arg-type]
    (read,) = _selects(uow.session)
    assert "FOR UPDATE" not in read and "FOR SHARE" not in read
    assert uow.session.savepoints == []  # nothing is locked, so no savepoint is opened
    assert commands._open_next_period(uow, _scope(), None) is None  # type: ignore[arg-type]
    assert len(_selects(uow.session)) == 1  # the opening reads nothing more
    assert [s for s in uow.session.statements if isinstance(s, Insert | Update)] == []
    assert uow.deferred == []  # nothing is opened, so nothing is re-marked


def test_the_lock_decision_locks_a_future_next_period_before_it_opens_it() -> None:
    """A ``future`` next period is read without a lock, read again ``FOR UPDATE NOWAIT`` — the
    decision holds the closing period's row and does not wait for another period's — and opened by
    its transition; when it is no longer ``future`` under the lock, nothing is written. Fail-first:
    the second read was ``FOR UPDATE``, a wait that an opening of that period in flight and a
    posting can close into a cycle.

    R-101 (a): the opening then DEFERS the SCH-06 re-marking — one ``PERIOD_OPEN_REDIRTY`` job
    for the opened period state, behind an advisory lock on that state and unless a job of it is
    live — and reads or locks no ``combination_group`` row. Fail-first: no job was deferred.

    Since 04 DB-07 rev 1.182 the two reads are ``_hold_future_next_period``'s and the transition
    and the deferral ``_open_next_period``'s, on the row the first one returned; the statements
    are the ones asserted before the split, in the same order.

    Finding F11 of the independent review of 2026-10-01 (04 DB-07 rev 1.229; dev-guide
    DG-KRN-DB-08 (1a) rev 1.218): the locking read runs inside a savepoint. A row that is
    ``future`` under the lock leaves it released — the lock is the decision's to its commit. A row
    an opening moved between the two reads leaves it rolled back, which gives the row back at
    once. Fail-first: no savepoint; that row stayed locked to the decision's end."""
    uow = _Uow(_Session(rows=[_next(PeriodState.FUTURE), _next(PeriodState.FUTURE)]))
    held = commands._hold_future_next_period(uow.session, _scope())  # type: ignore[arg-type]
    assert held is not None and held["id"] == NEXT_STATE
    assert len(uow.session.statements) == 2  # the two reads; nothing is written yet
    assert uow.session.savepoints == ["begun", "released"]  # the lock passes to the decision
    assert commands._open_next_period(uow, _scope(), held) == NEXT_STATE  # type: ignore[arg-type]
    first, second, advisory, live = _selects(uow.session)
    assert "FOR UPDATE" not in first
    assert second.endswith("FOR UPDATE OF period_state NOWAIT")
    assert "pg_advisory_xact_lock(hashtextextended(" in advisory
    key = uow.session.statements[-2].compile(dialect=postgresql.dialect()).params
    assert f"period-open-redirty:{NEXT_STATE}" in key.values()
    assert "FROM erev.job" in live and "FOR UPDATE" not in live and "FOR SHARE" not in live
    assert uow.deferred == [(JobKind.PERIOD_OPEN_REDIRTY, {"period_state_id": str(NEXT_STATE)})]
    # 04 T-PLT-27 rev 1.164: the job's subject is the period state it re-marks
    assert uow.subjects == [("period_state", NEXT_STATE)]
    assert not any("combination_group" in text for text in _selects(uow.session))
    writes = [
        ("INSERT" if isinstance(s, Insert) else "UPDATE", s.table.name)
        for s in uow.session.statements
        if isinstance(s, Insert | Update)
    ]
    assert writes == [("INSERT", "period_state_transition"), ("UPDATE", "period_state")]

    raced = _Uow(_Session(rows=[_next(PeriodState.FUTURE), _next(PeriodState.OPEN)]))
    lost = commands._hold_future_next_period(raced.session, _scope())  # type: ignore[arg-type]
    assert lost is None
    assert raced.session.savepoints == ["begun", "rolled back"]  # F11: the row is given back
    assert commands._open_next_period(raced, _scope(), lost) is None  # type: ignore[arg-type]
    assert [s for s in raced.session.statements if isinstance(s, Insert | Update)] == []
    assert raced.deferred == []


class _Held(_Session):
    """A session whose locked read of the next period finds the row held: the second statement
    raises what PostgreSQL answers ``FOR UPDATE NOWAIT`` with."""

    sqlstate = "55P03"

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if len(self.statements) == 1:
            self.statements.append(statement)
            cause = SimpleNamespace(sqlstate=self.sqlstate)
            raise OperationalError("SELECT … FOR UPDATE NOWAIT", {}, cause)  # type: ignore[arg-type]
        return super().execute(statement, *args, **kwargs)


def test_f8_a_held_next_period_row_is_refused_by_name() -> None:
    """04 DB-07 rev 1.182 (supervisor ruling R-116 (h); review finding F8 (c)): the ``future``
    next period's row is held by another transaction — SQLSTATE 55P03 on the ``NOWAIT`` read. The
    decision is refused 409 ``lock-conflict`` under a rule and a detail of its own (PRD ERR-78),
    naming both periods: nothing was waited for, so the copy of a lock wait is wrong here. Any
    other database error of that statement propagates as it is. Fail-first: the raw 55P03 left
    ``_open_next_period`` and the request was answered with ``LOCK_TIMEOUT``'s copy."""
    session = _Held(rows=[_next(PeriodState.FUTURE)])
    with pytest.raises(Problem) as refused:
        commands._hold_future_next_period(session, _scope())  # type: ignore[arg-type]
    detail = (
        "October 2026 is in use by another request, so September 2026 was not locked. "
        "Nothing was saved. Decide again."
    )
    assert (refused.value.slug, refused.value.detail) == ("lock-conflict", detail)
    assert [(error.rule_id, error.message) for error in refused.value.errors] == [
        ("NEXT_PERIOD_HELD", detail)
    ]
    first, second = _selects(session)
    assert "FOR UPDATE" not in first and second.endswith("FOR UPDATE OF period_state NOWAIT")
    assert session.savepoints == ["begun", "rolled back"]

    class _Deadlocked(_Held):
        sqlstate = "40P01"

    with pytest.raises(OperationalError):
        commands._hold_future_next_period(  # type: ignore[arg-type]
            _Deadlocked(rows=[_next(PeriodState.FUTURE)]), _scope()
        )


def _legacy_next(state: PeriodState) -> dict[str, Any]:
    return {**_next(state), "id": LEGACY_NEXT_STATE, "book_code": "LEGACY"}


def _legacy_reads(*, primary: Any = "ASC606", kept: Any = True, own: Any = "open") -> list[Any]:
    """What the three reads before the LEGACY row answer: the tenant's primary book, whether the
    entity keeps the LEGACY book, and the LEGACY state of the period being locked."""
    return [primary, kept, own]


def test_br_cls_03_the_legacy_books_future_next_row_is_taken_as_the_primarys_is() -> None:
    """04 DB-07 rev 1.214 (PRD BR-CLS-03 rev 1.143; supervisor ruling of 2026-10-01 on item
    PER-LEGACY-POSTING-PERIOD-1): for a period of the primary book, the LEGACY book's row of the
    next period — read without a lock, then ``FOR UPDATE NOWAIT`` — after three reads that take
    no lock: the tenant's primary book, the entity's LEGACY book and the LEGACY state of the
    period being locked. ``_open_legacy_period`` then writes on the held row what
    ``_open_next_period`` writes on the primary's: the transition, the state and one
    ``PERIOD_OPEN_REDIRTY`` job whose subject is the LEGACY period state.

    Fail-first: the decision took no LEGACY row; the LEGACY book's next period stayed ``future``
    after the lock, and a legacy amount dated in the locked period had no period postable in
    both books."""
    rows = [*_legacy_reads(), _legacy_next(PeriodState.FUTURE), _legacy_next(PeriodState.FUTURE)]
    uow = _Uow(_Session(rows=rows))
    held = commands._hold_future_legacy_period(uow.session, _scope())  # type: ignore[arg-type]
    assert held is not None and held["id"] == LEGACY_NEXT_STATE
    assert uow.session.savepoints == ["begun", "released"]  # F11: as the primary's row
    primary, kept, own, first, second = _selects(uow.session)
    assert "FROM erev.book" in primary and "is_primary" in primary
    assert "FROM erev.entity_book" in kept and "is_enabled" in kept
    assert "FROM erev.period_state" in own
    assert not any(" FOR " in text for text in (primary, kept, own, first))
    assert second.endswith("FOR UPDATE OF period_state NOWAIT")
    for statement in uow.session.statements[1:]:  # every read after the first names the book
        assert "LEGACY" in statement.compile(dialect=postgresql.dialect()).params.values()
    assert commands._open_legacy_period(uow, _scope(), held) == LEGACY_NEXT_STATE  # type: ignore[arg-type]
    assert uow.deferred == [
        (JobKind.PERIOD_OPEN_REDIRTY, {"period_state_id": str(LEGACY_NEXT_STATE)})
    ]
    assert uow.subjects == [("period_state", LEGACY_NEXT_STATE)]
    writes = [
        ("INSERT" if isinstance(s, Insert) else "UPDATE", s.table.name)
        for s in uow.session.statements
        if isinstance(s, Insert | Update)
    ]
    assert writes == [("INSERT", "period_state_transition"), ("UPDATE", "period_state")]
    (transition,) = [s for s in uow.session.statements if isinstance(s, Insert)]
    assert transition.compile(dialect=postgresql.dialect()).params["book_code"] == "LEGACY"
    assert not any("combination_group" in text for text in _selects(uow.session))

    nothing = _Uow(_Session())
    assert commands._open_legacy_period(nothing, _scope(), None) is None  # type: ignore[arg-type]
    assert nothing.session.statements == [] and nothing.deferred == []


@pytest.mark.parametrize(
    ("rows", "statements"),
    [
        # the period locked is not of the book the LEGACY book follows: a second posting book
        ([*_legacy_reads(primary="IFRS15")], 1),
        # no book for the LEGACY book to follow: no primary, or the LEGACY book is the primary
        ([*_legacy_reads(primary=None)], 1),
        ([*_legacy_reads(primary="LEGACY")], 1),
        # the entity does not keep the LEGACY book: never kept, or kept no longer
        ([*_legacy_reads(kept=None)], 2),
        ([*_legacy_reads(kept=False)], 2),
        # the LEGACY book has no state for the period being locked, or it was never opened: the
        # periods of a book open in order (PRD SM-07)
        ([*_legacy_reads(own=None)], 3),
        ([*_legacy_reads(own="future")], 3),
        # the LEGACY book's next period is open already, or the calendar ends
        ([*_legacy_reads(), _legacy_next(PeriodState.OPEN)], 4),
        ([*_legacy_reads(), None], 4),
    ],
)
def test_br_cls_03_no_legacy_row_is_taken_unless_the_book_follows_and_its_next_is_future(
    rows: list[Any], statements: int
) -> None:
    """Each condition of ``_hold_future_legacy_period`` ends it without a lock and without a
    further read: nothing is held, so nothing is opened."""
    session = _Session(rows=list(rows))
    assert commands._hold_future_legacy_period(session, _scope()) is None  # type: ignore[arg-type]
    read = _selects(session)
    assert len(read) == statements
    assert not any(" FOR " in text for text in read)
    assert session.savepoints == []  # no lock is asked for, so no savepoint is opened

    raced = _Session(
        rows=[*_legacy_reads(), _legacy_next(PeriodState.FUTURE), _legacy_next(PeriodState.OPEN)]
    )
    # opened between the two reads: nothing is opened, and the row is given back with the
    # savepoint of the locking read (finding F11) — until then it stayed locked to the
    # decision's end
    assert commands._hold_future_legacy_period(raced, _scope()) is None  # type: ignore[arg-type]
    assert raced.savepoints == ["begun", "rolled back"]


class _LegacyHeld(_Session):
    """A session whose locked read of the LEGACY row — its fifth statement — finds it held."""

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if len(self.statements) == 4:
            self.statements.append(statement)
            cause = SimpleNamespace(sqlstate="55P03")
            raise OperationalError("SELECT … FOR UPDATE NOWAIT", {}, cause)  # type: ignore[arg-type]
        return super().execute(statement, *args, **kwargs)


def test_err_78_a_held_legacy_next_row_is_refused_by_the_same_name() -> None:
    """PRD ERR-78 covers the row of the book that follows: a LEGACY row another transaction holds
    is 409 ``lock-conflict`` under rule ``NEXT_PERIOD_HELD`` with the sentence of the primary's
    row — it names the period, which the two rows share."""
    session = _LegacyHeld(rows=[*_legacy_reads(), _legacy_next(PeriodState.FUTURE)])
    with pytest.raises(Problem) as refused:
        commands._hold_future_legacy_period(session, _scope())  # type: ignore[arg-type]
    detail = (
        "October 2026 is in use by another request, so September 2026 was not locked. "
        "Nothing was saved. Decide again."
    )
    assert (refused.value.slug, refused.value.detail) == ("lock-conflict", detail)
    assert [(error.rule_id, error.message) for error in refused.value.errors] == [
        ("NEXT_PERIOD_HELD", detail)
    ]
    assert _selects(session)[-1].endswith("FOR UPDATE OF period_state NOWAIT")
    assert session.savepoints == ["begun", "rolled back"]


def _called(function: Any) -> list[str]:
    """The dotted names ``function`` calls, in source order."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    found: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts: list[str] = []
        target: Any = node.func
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
            found.append((node.lineno, node.col_offset, ".".join(reversed(parts))))
    return [name for _, _, name in sorted(found)]


def test_the_lock_decision_takes_its_locks_and_its_reader_in_the_ruled_order() -> None:
    """04 §14.1 rev 1.182 and 05 TXN-03 rev 1.121 (supervisor ruling R-116 (h); review findings
    F7 (c), F8 and gap G3), read from the source of the hook: the period's state row first; the
    approved basis compared under it; the ``future`` next period's row BEFORE the gates, the read
    of the earlier periods and the freeze; the idle timeout set for the decision's transaction
    and for its reader's before the first dataset; ONE SYSTEM reader, and both coverage reads and
    the producers handed it; the opening on the row already held. Fail-first: the next period's
    row was the last lock (inside ``_open_next_period``, after the lock writes), the basis was
    not compared, and no reader was opened here — each read opened its own."""
    names = _called(commands._period_lock_approved)

    def at(name: str) -> int:
        assert names.count(name) == 1, (name, names.count(name))
        return names.index(name)

    row, basis = at("gates.period_scope"), at("approvals.assert_own_fresh_basis")
    next_row, gate = at("_hold_future_next_period"), at("gates.evaluate_gates")
    earlier, cutoff = at("_earlier_postable"), at("freeze.freeze_cutoff")
    reader, datasets = at("freeze.system_unit"), at("snapshots.freeze_datasets")
    assert row < basis < next_row < gate < earlier < cutoff < reader < datasets
    # 04 DB-07 rev 1.214: the LEGACY book's row directly after the next period's, before the
    # gates; its opening beside the primary's, on the row already held
    assert next_row < at("_hold_future_legacy_period") < gate
    assert at("_open_next_period") < at("_open_legacy_period") < at("evidence.record_execution")
    idle = [index for index, name in enumerate(names) if name == "freeze.allow_idle"]
    assert len(idle) == 2 and cutoff < idle[0] < reader < idle[1] < datasets
    assert at("freeze.held") > reader and at("_open_next_period") > datasets
    covered = [index for index, name in enumerate(names) if name == "freeze.assert_covered"]
    assert len(covered) == 2 and datasets < covered[0] < at("_persist_lock") < covered[1]
    # the reopen hook compares its basis under the row as well
    reopen = _called(commands._period_reopen_approved)
    assert reopen.index("gates.period_scope") < reopen.index("approvals.assert_own_fresh_basis")
    assert reopen.index("approvals.assert_own_fresh_basis") < reopen.index("_later_closed")


class _Rows:
    def __init__(self, rows: list[tuple[str, str, UUID]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[str, str, UUID]]:
        return list(self.rows)


class _Earlier:
    """The session ``_earlier_postable`` sees: its statements in emission order, its savepoints,
    and — when ``held`` names periods — a first read that PostgreSQL refuses (``sqlstate``) and a
    ``SKIP LOCKED`` read that leaves those periods out."""

    def __init__(
        self,
        rows: list[tuple[str, str, UUID]],
        *,
        held: frozenset[str] = frozenset(),
        sqlstate: str = "55P03",
        let_go: bool = False,
    ) -> None:
        self.rows, self.held, self.sqlstate, self.let_go = rows, held, sqlstate, let_go
        self.statements: list[str] = []
        self.savepoints: list[str] = []

    @contextmanager
    def begin_nested(self) -> Iterator[None]:
        self.savepoints.append("begun")
        try:
            yield
        except BaseException:
            self.savepoints.append("rolled back")
            raise
        self.savepoints.append("released")

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Rows:
        sql = _sql(statement)
        self.statements.append(sql)
        if sql.endswith("NOWAIT") and self.held:
            cause = SimpleNamespace(sqlstate=self.sqlstate)
            raise OperationalError("SELECT … FOR SHARE NOWAIT", {}, cause)  # type: ignore[arg-type]
        if sql.endswith("SKIP LOCKED") and not self.let_go:
            return _Rows([row for row in self.rows if row[0] not in self.held])
        return _Rows(self.rows)


def _earlier(*states: str) -> list[tuple[str, str, UUID]]:
    """The earlier periods' rows, January first: (name, state, state id)."""
    names = ("Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026", "Jul 2026")
    return [(names[index], state, UUID(int=index + 1)) for index, state in enumerate(states)]


def test_br_cls_08_the_earlier_rows_are_shared_without_waiting_inside_a_savepoint() -> None:
    """PRD BR-CLS-08 (04 DB-07 rev 1.182; supervisor ruling R-119 (d)): one read of every earlier
    state row ``FOR SHARE NOWAIT``, inside a savepoint, and the earliest postable period is the
    answer — None when every earlier period is closed, permanently locked or ``future``."""
    closed = _Earlier(_earlier("permanently_locked", "closed", "closed", "future"))
    assert commands._earlier_postable(closed, _scope()) is None  # type: ignore[arg-type]
    (read,) = closed.statements
    assert read.endswith("FOR SHARE OF period_state NOWAIT")
    assert closed.savepoints == ["begun", "released"]
    postable = _Earlier(_earlier("closed", "reopened", "closing", "open"))
    assert commands._earlier_postable(postable, _scope()) == "Feb 2026"  # type: ignore[arg-type]


def test_br_cls_08_a_held_earlier_period_row_is_refused_by_name() -> None:
    """Supervisor ruling R-119 (d) (PRD ERR-85; 04 DB-07 rev 1.182): another transaction holds the
    rows of May and July for a change. The ``NOWAIT`` read fails with 55P03; the savepoint is
    rolled back, every earlier row is read without a lock and again ``FOR SHARE SKIP LOCKED``,
    and the EARLIEST row the second read leaves out is named: 409 ``lock-conflict`` under rule
    ``EARLIER_PERIOD_HELD``. Fail-first: the raw 55P03 left the function and the request was
    answered with ``LOCK_TIMEOUT``'s copy — "held … for longer than the platform waits" — though
    nothing was waited for."""
    rows = _earlier("closed", "closed", "closed", "closed", "closed", "closed", "closed")
    session = _Earlier(rows, held=frozenset({"May 2026", "Jul 2026"}))
    with pytest.raises(Problem) as refused:
        commands._earlier_postable(session, _scope())  # type: ignore[arg-type]
    detail = (
        "May 2026 is in use by another request, so September 2026 was not locked. "
        "Nothing was saved. Decide again."
    )
    assert (refused.value.slug, refused.value.detail) == ("lock-conflict", detail)
    assert [(error.rule_id, error.message) for error in refused.value.errors] == [
        ("EARLIER_PERIOD_HELD", detail)
    ]
    assert isinstance(refused.value.__cause__, OperationalError)
    first, plain, skipping = session.statements
    assert first.endswith("FOR SHARE OF period_state NOWAIT")
    assert " FOR " not in plain
    assert skipping.endswith("FOR SHARE OF period_state SKIP LOCKED")
    assert session.savepoints == ["begun", "rolled back"]


def test_br_cls_08_a_holder_that_has_ended_since_leaves_the_rule_to_be_judged() -> None:
    """The holder ends between the refused read and the two that look for it: the ``SKIP LOCKED``
    read then shares EVERY earlier row — what the first read wanted — and the rule is judged on
    them, here an earlier period in soft close (``earlier-period-open`` is the caller's refusal)."""
    rows = _earlier("closed", "closed", "closing")
    session = _Earlier(rows, held=frozenset({"Mar 2026"}), let_go=True)
    assert commands._earlier_postable(session, _scope()) == "Mar 2026"  # type: ignore[arg-type]
    assert len(session.statements) == 3


def test_br_cls_08_another_database_error_of_the_read_is_not_renamed() -> None:
    """Only 55P03 is the held row. A deadlock (40P01) of the same statement leaves the function
    as it is, for the kernel's mapping, and no further statement is sent."""
    session = _Earlier(_earlier("closed"), held=frozenset({"Jan 2026"}), sqlstate="40P01")
    with pytest.raises(OperationalError):
        commands._earlier_postable(session, _scope())  # type: ignore[arg-type]
    assert len(session.statements) == 1 and session.savepoints == ["begun", "rolled back"]
