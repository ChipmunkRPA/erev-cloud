"""Item JRN-COMPLETENESS-TRANSIENT-1 (the supervisor's ruling of 2026-10-01; dev-guide DG-CMD-09
rev 1.234): what the guard around the read of a run's held detail file answers.

``completeness._held_ids_from_file`` answers ``None`` — the run is "unverifiable", covers nothing
and is a named finding of ``JE_COMPLETE`` — when the file cannot be read. That is a statement
about the file. Until rev 1.234 the guard caught every exception, so a lock timeout, a cancelled
statement or a lost connection read as "unverifiable" too, and the caught database error left the
transaction aborted for the statements after it. Now a failure that says nothing about the file
is re-raised by the table the computation reads (``db.errors``), and the read runs in a
savepoint. CPU-only: a session that raises what a driver would.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
import sqlalchemy as sa
from erev_api.domain.journals import completeness
from erev_api.problems import Problem
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
AFTER: Final = {
    "held_detail_file_id": "00000000-0000-4000-8000-00000000f001",
    "held_detail_sha256": "0" * 64,
}


class _Orig(Exception):
    """A driver error as psycopg raises it: a SQLSTATE and a primary message."""

    def __init__(self, sqlstate: str | None, message: str) -> None:
        super().__init__(message)
        if sqlstate is not None:
            self.sqlstate = sqlstate


def _db_error(sqlstate: str, message: str = "from the server") -> DBAPIError:
    return DBAPIError("SELECT … FROM erev.file_object", {}, _Orig(sqlstate, message))


def _lost_connection() -> OperationalError:
    return OperationalError("SELECT … FROM erev.file_object", {}, _Orig(None, "connection lost"))


class _Rows:
    def mappings(self) -> _Rows:
        return self

    def one_or_none(self) -> None:
        return None  # no visible ``file_object`` row


class _Session:
    """A session whose one statement — the read of the file's row — raises ``error`` or finds no
    row; it records that the read ran inside a savepoint."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.savepoints = 0
        self.statements_in_savepoint = 0
        self._inside = False

    @contextmanager
    def begin_nested(self) -> Iterator[None]:
        self.savepoints += 1
        self._inside = True
        try:
            yield
        finally:
            self._inside = False

    def execute(self, statement: Any) -> _Rows:
        assert isinstance(statement, sa.sql.Select)
        self.statements_in_savepoint += self._inside
        if self.error is not None:
            raise self.error
        return _Rows()


def _read(session: _Session) -> frozenset[UUID] | None:
    return completeness._held_ids_from_file(
        session,  # type: ignore[arg-type]
        AFTER,
        files=None,  # type: ignore[arg-type]
        keyring=None,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "error",
    [
        _db_error("55P03", "canceling statement due to lock timeout"),
        _db_error("57014", "canceling statement due to statement timeout"),
        _db_error("40P01", "deadlock detected"),
        _db_error("53300", "too many connections"),
        _db_error("25P02", "current transaction is aborted"),
        _lost_connection(),
        PoolTimeoutError("QueuePool limit of size 5 overflow 10 reached"),
    ],
    ids=["lock-timeout", "cancelled", "deadlock", "resources", "aborted", "lost", "pool-timeout"],
)
def test_a_failure_that_says_nothing_about_the_file_is_re_raised(error: BaseException) -> None:
    """A transient database error, an unavailable server and a pool timeout are not an answer
    about the file: the guard re-raises them and the caller's command answers as for any such
    error. Before the item each read as "unverifiable"."""
    assert completeness.not_about_the_file(error)
    session = _Session(error)
    with pytest.raises(type(error)) as raised:
        _read(session)
    assert raised.value is error
    assert (session.savepoints, session.statements_in_savepoint) == (1, 1)


def test_the_failure_is_found_behind_the_exception_that_wraps_it() -> None:
    """``db.errors.database_error_in`` walks causes and contexts: an error of the file store
    raised FROM a lost connection is still the lost connection."""
    try:
        try:
            raise _lost_connection()
        except OperationalError as lost:
            raise RuntimeError("the row could not be read") from lost
    except RuntimeError as wrapped:
        assert completeness.not_about_the_file(wrapped)


@pytest.mark.parametrize(
    "error",
    [
        None,  # no visible row: ``open_file`` answers not-found
        Problem("not-found"),
        FileNotFoundError("the object is gone"),
        ValueError("the key does not open the object"),
        _db_error("42501", "permission denied for table file_object"),
        _db_error("22P02", "invalid input syntax"),
    ],
    ids=["no-row", "not-found", "missing-object", "wrong-key", "privilege", "data"],
)
def test_a_failure_of_the_file_is_unverifiable(error: BaseException | None) -> None:
    """Everything else stays what it was: no row, a shredded or missing object, a key that does
    not open it — and a deterministic database error, which the savepoint rolls back — answer
    ``None``, and the run is a named finding."""
    if error is not None:
        assert not completeness.not_about_the_file(error)
    session = _Session(error)
    assert _read(session) is None
    assert (session.savepoints, session.statements_in_savepoint) == (1, 1)


def test_an_event_that_names_no_file_reads_nothing() -> None:
    session = _Session(_lost_connection())
    assert (
        completeness._held_ids_from_file(
            session,  # type: ignore[arg-type]
            {"held_detail_file_id": None, "held_detail_sha256": None},
            files=None,  # type: ignore[arg-type]
            keyring=None,  # type: ignore[arg-type]
        )
        is None
    )
    assert session.savepoints == 0


def test_the_guard_reads_the_computations_table_and_the_guide_says_so() -> None:
    """The guard's rule is ``db.errors`` — the server unavailable, a pool timeout, a transient
    error — and nothing of its own; dev-guide DG-CMD-09 rev 1.234 states it in one sentence."""
    rule = inspect.getsource(completeness.not_about_the_file)
    assert "db_errors.server_unavailable_in(error) or db_errors.pool_timeout_in(error)" in rule
    assert "db_errors.is_transient(raised)" in rule
    guard = inspect.getsource(completeness._held_ids_from_file)
    assert "with session.begin_nested():" in guard
    assert "if not_about_the_file(error):\n            raise" in guard
    [row] = [
        line
        for line in (DOCS / "dev-guide.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| DG-CMD-09 |")
    ]
    assert "Rev 1.234 (item JRN-COMPLETENESS-TRANSIENT-1;" in row
    assert "(`journals.completeness._held_ids_from_file`) decides by the same table" in row
    assert 'answers "unverifiable", inside a savepoint' in row
