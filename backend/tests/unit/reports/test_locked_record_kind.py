"""The record a report run "as locked" names is a ``LOCK`` (ENGINE_SPEC_B S15-R-19 rev 1.167; 04
§16.9 rev 1.301; item PERMLOCK-DATASETS-1, the supervisor's ruling of 2026-10-02 16:16) — without
a database: the refusal's sentence as a rule, the two reads behind it and its place among the
refusals of ``framework._resolve``. The database witnesses are
``tests/domain/close/test_dataset_lock.py``.

- A ``LOCK`` record is never refused, and costs no read.
- A ``REOPEN`` and a ``PERMANENT_LOCK`` record froze nothing: the sentence names the record, what
  it is and its period, then the ``LOCK`` whose datasets stand for the period — or says that none
  stands and what the caller can do instead.
- The kind is read with the lock's scope, in that statement; the lock that stands by the rule of
  ``close.lock_records``, in one statement, only for a record that is refused.
- The refusal is made where the run is created, after the report's own (a report without a lock
  dataset is refused first: no lock would serve it).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.domain.close import lock_records
from erev_api.domain.reports import framework, locked
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.enums import LockKind
from sqlalchemy.dialects import postgresql

LOCK: Final = UUID("00000000-0000-4000-8000-000000000c10")
PERMANENT: Final = UUID("00000000-0000-4000-8000-000000000c20")
REOPEN: Final = UUID("00000000-0000-4000-8000-000000000c30")
ENTITY: Final = UUID("00000000-0000-4000-8000-00000000000a")
PERIOD: Final = UUID("00000000-0000-4000-8000-000000000808")
KEY: Final = "FY2026-P08"
CODE: Final = "contract_balances"
NOW: Final = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
LOCKED: Final = locked.LockScope(
    lock_id=LOCK,
    entity_id=ENTITY,
    entity_code="AVM-US",
    book_code="ASC606",
    period_id=PERIOD,
    period_key=KEY,
    kind=LockKind.LOCK.value,
)
PERMANENTLY: Final = dataclasses.replace(
    LOCKED, lock_id=PERMANENT, kind=LockKind.PERMANENT_LOCK.value
)
REOPENED: Final = dataclasses.replace(LOCKED, lock_id=REOPEN, kind=LockKind.REOPEN.value)
PASS: Final = f"The datasets of {KEY} are those of lock {LOCK}; pass that lock."
NONE_STANDS: Final = (
    f"No lock's datasets stand for {KEY}: run the report current (known_at) instead, or pass a "
    "LOCK record of the period (GET /periods/{id}/locks)."
)
IS_PERMANENT: Final = (
    f"Lock {PERMANENT} is the permanent lock of {KEY}: it froze no dataset (E-63 PERMANENT_LOCK)."
)
IS_REOPEN: Final = f"Lock {REOPEN} is a reopen record of {KEY}: it froze no dataset (E-63 REOPEN)."


def _sql(statement: Any) -> str:
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


class _Session:
    """Answers each statement with the next value and keeps the statements."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Any:
        self.statements.append(_sql(statement))
        answer = self.answers.pop(0)
        return SimpleNamespace(
            scalar_one_or_none=lambda: answer,
            mappings=lambda: SimpleNamespace(one_or_none=lambda: answer),
        )


# --- the sentence ---------------------------------------------------------------------------------


def test_a_lock_record_is_never_refused() -> None:
    assert locked.not_a_lock(LOCKED, None) is None
    assert locked.not_a_lock(LOCKED, LOCK) is None
    assert (
        locked.LockScope(
            lock_id=LOCK,
            entity_id=ENTITY,
            entity_code="AVM-US",
            book_code="ASC606",
            period_id=PERIOD,
            period_key=KEY,
        ).kind
        == LockKind.LOCK.value
    )  # what a scope written without its kind describes


def test_the_sentence_names_the_record_its_kind_and_the_lock_to_pass() -> None:
    """The permanent lock of a period that is final, and a reopen record of a period locked
    again since: the record, what it is, its period, then the ``LOCK`` whose datasets stand."""
    assert locked.not_a_lock(PERMANENTLY, LOCK) == f"{IS_PERMANENT} {PASS}"
    assert locked.not_a_lock(REOPENED, LOCK) == f"{IS_REOPEN} {PASS}"


def test_where_no_locks_datasets_stand_the_sentence_says_so_and_what_to_do() -> None:
    """A reopen record of a period that is not locked now, and a permanent lock that follows no
    ``LOCK`` (no writer of the product leaves one): nothing is named that does not stand."""
    assert locked.not_a_lock(REOPENED, None) == f"{IS_REOPEN} {NONE_STANDS}"
    assert locked.not_a_lock(PERMANENTLY, None) == f"{IS_PERMANENT} {NONE_STANDS}"


def test_every_kind_that_freezes_nothing_has_its_words() -> None:
    """E-63 less ``LOCK``: a kind added to the enumeration without its words fails here."""
    assert set(locked.RECORD_WORDS) == {kind.value for kind in LockKind} - {LockKind.LOCK.value}


# --- the two reads --------------------------------------------------------------------------------


def test_the_kind_is_read_with_the_locks_scope() -> None:
    """``lock_scope``: one statement, as before, with the record's kind among its columns — the
    enumeration value or its text, as the driver returns it."""
    row = {
        "id": PERMANENT,
        "kind": LockKind.PERMANENT_LOCK,
        "entity_id": ENTITY,
        "book_code": "ASC606",
        "period_id": PERIOD,
        "entity_code": "AVM-US",
        "period_key": KEY,
    }
    session = _Session(row, {**row, "kind": "PERMANENT_LOCK"}, None)
    assert locked.lock_scope(session, PERMANENT) == PERMANENTLY  # type: ignore[arg-type]
    assert locked.lock_scope(session, PERMANENT) == PERMANENTLY  # type: ignore[arg-type]
    assert locked.lock_scope(session, PERMANENT) is None  # type: ignore[arg-type]
    assert len(session.statements) == 3
    assert session.statements[0].startswith(
        "SELECT erev.period_lock.id, erev.period_lock.kind, erev.period_lock.entity_id, "
    )


def test_the_lock_that_stands_is_read_only_for_a_record_that_is_refused() -> None:
    """``froze_nothing``: no statement for a ``LOCK``; for another record ONE statement — the
    rule of ``close.lock_records`` for the record's entity, book and period."""
    untouched = _Session()
    assert locked.froze_nothing(untouched, LOCKED) is None  # type: ignore[arg-type]
    assert untouched.statements == []

    session = _Session(LOCK, None, str(LOCK))
    assert locked.froze_nothing(session, PERMANENTLY) == f"{IS_PERMANENT} {PASS}"  # type: ignore[arg-type]
    assert locked.froze_nothing(session, REOPENED) == f"{IS_REOPEN} {NONE_STANDS}"  # type: ignore[arg-type]
    assert locked.froze_nothing(session, REOPENED) == f"{IS_REOPEN} {PASS}"  # type: ignore[arg-type]
    rule = _sql(
        lock_records.dataset_lock_of(entity_id=ENTITY, book_code="ASC606", period_id=PERIOD)
    )
    assert session.statements == [rule, rule, rule]


# --- where the run is created ---------------------------------------------------------------------


def _resolve(
    monkeypatch: pytest.MonkeyPatch, scope: locked.LockScope, session: Any, code: str = CODE
) -> Any:
    """``framework._resolve`` of ``code`` with ``scope``'s record as its lock; the caller's entity
    scope and the lock's scope stand in, the read of the lock that stands goes to ``session``."""
    monkeypatch.setattr(
        framework, "_in_scope_entities", lambda session, principal, permission: {"AVM-US": ENTITY}
    )
    monkeypatch.setattr(framework.locked, "lock_scope", lambda session, lock_id: scope)
    uow = SimpleNamespace(session=session, principal=None, now=NOW)
    schema = DEFINITIONS_BY_CODE[code].parameters_schema
    return framework._resolve(uow, schema, {"period_lock_id": str(scope.lock_id)}, code=code)


def test_a_run_that_names_a_record_which_froze_nothing_is_refused_at_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One finding on ``parameters.period_lock_id`` under S15-R-19 with the sentence; the lock
    that stands is read once."""
    for scope, standing, sentence in (
        (PERMANENTLY, LOCK, f"{IS_PERMANENT} {PASS}"),
        (REOPENED, None, f"{IS_REOPEN} {NONE_STANDS}"),
    ):
        session = _Session(standing)
        _, errors = _resolve(monkeypatch, scope, session)
        (error,) = errors
        assert (error.field, error.rule_id) == ("parameters.period_lock_id", locked.RULE)
        assert error.message == sentence
        assert len(session.statements) == 1


def test_a_run_that_names_a_lock_is_resolved_as_before_and_reads_nothing_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    resolved, errors = _resolve(monkeypatch, LOCKED, session)
    assert errors == [] and resolved.period_lock_id == LOCK
    assert resolved.parameters["period_key"] == KEY
    assert session.statements == []


def test_a_report_without_a_lock_dataset_is_refused_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """No lock serves such a report, so its own refusal is the one stated, and the lock that
    stands is not read."""
    code = "revenue_from_opening_liability"
    assert locked.snapshot_kind_of(code) is None
    session = _Session()
    _, errors = _resolve(monkeypatch, PERMANENTLY, session, code=code)
    (error,) = errors
    assert error.message == locked.NO_DATASET.format(code=code)
    assert session.statements == []
