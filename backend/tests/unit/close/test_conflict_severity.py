"""D-98 69 (Codex CLO-5 conflict review R5): when the existing-item read of ``raise_exception_item``
finds no open row but the insert's ``ON CONFLICT`` lands on one (a concurrent first creation of the
same open ``(tenant_id, dedupe_key)``), the winning row is reconciled in the same transaction before
the caller reads any gate — exactly one occurrence increment, the current effective severity when
it differs, one audited ``exception_item.severity_changed`` event with the actual prior and current
severities and the row version written; scope and status untouched.

Codex's three projections over an inert session (no database): the initial SELECT observes no row;
at the INSERT boundary the session supplies the same-scope OPEN winner and applies exactly the
emitted ``ON CONFLICT`` SET and RETURNING columns; a later UPDATE applies only when its WHERE names
the winner's id and the row version the insert returned. The gate is composed as ``monitors.py``
does: the open BLOCKING rows of the scope → ``gates.data_quality_gate``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.close import gates, monitors
from erev_api.domain.imports import exceptions
from erev_api.enums import ChecklistStatus, ExceptionSeverity, ExceptionSource
from sqlalchemy.sql import Select
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.elements import BinaryExpression, BindParameter

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
TENANT = UUID("00000000-0000-0000-0000-00000000aa01")
ENTITY = UUID("00000000-0000-0000-0000-0000000000e1")
PERIOD = UUID("00000000-0000-0000-0000-000000000f09")
CONTRACT = UUID("00000000-0000-0000-0000-00000000c001")
WINNER = UUID("00000000-0000-0000-0000-00000000e0a1")
ACTOR = UUID("00000000-0000-0000-0000-0000000000a7")
CODE = "DQ_INACTIVE_CONTRACT"
KEY = f"DATA_QUALITY:{CODE}:{ENTITY}:{PERIOD}:{CONTRACT}"
NUMBER = "EXC-000777"


def _literal(value: Any) -> Any:
    return value.value if isinstance(value, BindParameter) else value


def _apply(current: Any, value: Any) -> Any:
    """The effect of one SET expression on a stored value: ``col + n`` or a literal."""
    if isinstance(value, BinaryExpression):
        return int(current) + int(_literal(value.right))
    return _literal(value)


def _where(statement: Update) -> dict[str, Any]:
    clause = statement.whereclause
    parts = list(getattr(clause, "clauses", [clause]))
    return {part.left.name: _literal(part.right) for part in parts}


def _winner(severity: str) -> dict[str, Any]:
    """Codex's supplied conflict winner: the native candidate's scope with an explicit prior id,
    number, severity, occurrence count and row version; OPEN."""
    return {
        "id": WINNER,
        "exception_no": "EXC-000041",
        "source": ExceptionSource.DATA_QUALITY.value,
        "code": CODE,
        "severity": severity,
        "status": "OPEN",
        "dedupe_key": KEY,
        "entity_id": ENTITY,
        "period_id": PERIOD,
        "contract_id": CONTRACT,
        # T-IMP-05: the two other columns the audit event's contract key is read from
        "combination_group_id": None,
        "source_payload": None,
        "occurrence_count": 1,
        "row_version": 1,
    }


@dataclass
class _Result:
    rows: list[Any]

    def one_or_none(self) -> Any:
        return self.rows[0] if self.rows else None

    def one(self) -> Any:
        (row,) = self.rows
        return row


@dataclass
class _Session:
    """Inert: the SELECT sees no row; the INSERT lands on ``winner`` when given (applying only the
    emitted SET / RETURNING); an UPDATE applies only where its WHERE names the stored id and row
    version. ``row`` is the stored state after the call."""

    winner: dict[str, Any] | None
    row: dict[str, Any] | None = None
    statements: list[Any] = field(default_factory=list)

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.statements.append(statement)
        if isinstance(statement, Select):
            return _Result([])
        if isinstance(statement, Insert):
            if self.winner is None:
                self.row = {
                    **{str(k): _literal(v) for k, v in statement._values.items()},
                    "row_version": 1,
                }
            else:
                self.row = dict(self.winner)
                for key, value in statement._post_values_clause.update_values_to_set:
                    self.row[str(key)] = _apply(self.row.get(key), value)
            return self._returning(statement)
        if isinstance(statement, Update):
            assert self.row is not None
            where = _where(statement)
            if (
                where.get("id") != self.row["id"]
                or where.get("row_version", self.row["row_version"]) != self.row["row_version"]
            ):
                return _Result([])
            for column, value in statement._values.items():
                name = getattr(column, "name", column)
                self.row[str(name)] = _apply(self.row.get(str(name)), value)
            return self._returning(statement)
        raise AssertionError(f"unexpected statement {type(statement).__name__}")

    def _returning(self, statement: Any) -> _Result:
        assert self.row is not None
        names = [column.name for column in statement._returning]
        return _Result([SimpleNamespace(**{name: self.row[name] for name in names})])


@dataclass
class _Uow:
    session: _Session
    now: datetime = NOW
    principal: Any = field(
        default_factory=lambda: SimpleNamespace(
            tenant_id=TENANT, id=ACTOR, kind=SimpleNamespace(value="USER")
        )
    )
    audits: list[dict[str, Any]] = field(default_factory=list)

    def audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)


def _raise(uow: _Uow) -> exceptions.RaisedItem:
    """The ``monitors.run_monitors`` composition for one current ERROR finding of the contract."""
    return exceptions.raise_exception_item(
        uow,  # type: ignore[arg-type]
        source=ExceptionSource.DATA_QUALITY,
        code=CODE,
        severity=ExceptionSeverity.BLOCKING,
        message="No event on the contract for 120 days",
        dedupe=KEY,
        severity_cause=monitors.SEVERITY_CAUSE,
        business_key=str(CONTRACT),
        contract_id=CONTRACT,
        entity_id=ENTITY,
        period_id=PERIOD,
    )


def _gate(session: _Session) -> gates.GateResult:
    """``gates.data_quality_blocking`` over the stored row, then ``data_quality_gate``."""
    row = session.row
    blocking = int(
        row is not None
        and row["status"] in exceptions.OPEN_STATUSES
        and row["severity"] == ExceptionSeverity.BLOCKING.value
        and (row["entity_id"], row["period_id"]) == (ENTITY, PERIOD)
    )
    return gates.data_quality_gate(blocking, at=NOW)


@pytest.fixture(autouse=True)
def _numbering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exceptions.numbering, "next_number", lambda uow, series: NUMBER)


def test_same_scope_open_warning_winner_takes_the_current_error() -> None:
    session = _Session(winner=_winner("WARNING"))
    uow = _Uow(session)
    raised = _raise(uow)
    row = session.row
    assert row is not None
    # The winner's identity, scope and status are untouched; exactly one occurrence increment.
    assert (row["id"], row["status"], row["dedupe_key"]) == (WINNER, "OPEN", KEY)
    assert (row["entity_id"], row["period_id"], row["contract_id"]) == (ENTITY, PERIOD, CONTRACT)
    assert row["occurrence_count"] == 2
    # The current effective severity is stored in the same transaction with one history event.
    assert row["severity"] == "BLOCKING"
    assert (raised.id, raised.created, raised.occurrence_count) == (WINNER, False, 2)
    assert (raised.severity_changed, raised.previous_severity) == (True, "WARNING")
    history = [entry for entry in uow.audits if entry["action"] == exceptions.SEVERITY_ACTION]
    assert len(history) == 1
    (event,) = history
    assert (event["object_type"], event["object_id"]) == (exceptions.OBJECT_TYPE, WINNER)
    assert event["before"] == {"severity": "WARNING"}
    assert event["after"] == {
        "severity": "BLOCKING",
        "from": "WARNING",
        "to": "BLOCKING",
        "evaluated_at": NOW.isoformat(),
        "cause": monitors.SEVERITY_CAUSE,
    }
    assert event["object_version"] == str(row["row_version"]) == "3"
    assert event["contract_ids"] == [CONTRACT]  # the item's contract (04 T-PLT-19 contract key)
    assert not [entry for entry in uow.audits if entry["action"] == exceptions.CREATE_ACTION]
    # Statement shape: one SELECT, one INSERT (the single increment), one UPDATE; no helper retry.
    kinds = [type(statement).__name__ for statement in session.statements]
    assert kinds == ["Select", "Insert", "Update"]
    # The gate the caller reads in this invocation.
    gate = _gate(session)
    assert (gate.status, gate.count) == (ChecklistStatus.FAILED, 1)


def test_same_scope_open_blocking_winner_needs_no_history() -> None:
    session = _Session(winner=_winner("BLOCKING"))
    uow = _Uow(session)
    raised = _raise(uow)
    row = session.row
    assert row is not None
    assert (row["severity"], row["occurrence_count"], row["row_version"]) == ("BLOCKING", 2, 2)
    assert (raised.created, raised.severity_changed, raised.previous_severity) == (
        False,
        False,
        None,
    )
    assert raised.occurrence_count == 2 and uow.audits == []
    assert [type(statement).__name__ for statement in session.statements] == ["Select", "Insert"]
    gate = _gate(session)
    assert (gate.status, gate.count) == (ChecklistStatus.FAILED, 1)


def test_new_error_without_conflict_is_created() -> None:
    session = _Session(winner=None)
    uow = _Uow(session)
    raised = _raise(uow)
    row = session.row
    assert row is not None
    assert (row["severity"], row["occurrence_count"], row["status"]) == ("BLOCKING", 1, "OPEN")
    assert (raised.created, raised.occurrence_count, raised.severity_changed) == (True, 1, False)
    assert raised.exception_no == NUMBER
    assert [entry["action"] for entry in uow.audits] == [exceptions.CREATE_ACTION]
    assert [type(statement).__name__ for statement in session.statements] == ["Select", "Insert"]
    gate = _gate(session)
    assert (gate.status, gate.count) == (ChecklistStatus.FAILED, 1)
