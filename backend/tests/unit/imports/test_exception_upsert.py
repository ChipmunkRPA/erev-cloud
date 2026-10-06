"""The exception-item upsert infers the partial unique index with a LITERAL predicate (batch #5 on
main 020e5fd3, ``test_same_scope_open_repeat_keeps_blocking``: "there is no unique or exclusion
constraint matching the ON CONFLICT specification").

``ux_exception_item__open`` is ``UNIQUE (tenant_id, dedupe_key) WHERE status IN ('OPEN',
'IN_PROGRESS')`` (0041). Postgres infers it for ``INSERT … ON CONFLICT (tenant_id, dedupe_key) WHERE
<predicate>`` only while it can prove the statement's predicate implies the index predicate.
SQLAlchemy renders ``index_where`` with bound parameters, so the proof held only under a custom
plan with the parameter values in hand; once psycopg had prepared the statement
(``prepare_threshold`` 5) and the
planner switched to a generic plan the parameters were unknown and inference failed — the sixth and
later raises on a warmed connection. The predicate is therefore rendered as a literal, which no plan
mode can lose. CPU-only: the compiled SQL is inspected, nothing is executed."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from erev_api.domain.imports import exceptions
from sqlalchemy.dialects import postgresql

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


def _values() -> dict[str, object]:
    return {
        "tenant_id": UUID(int=1),
        "id": UUID(int=2),
        "exception_no": "EXC-000001",
        "source": "JOURNAL",
        "code": "FX_RATE_MISSING",
        "severity": "BLOCKING",
        "disposition": "REMEDIABLE",
        "status": "OPEN",
        "priority": 3,
        "title": "t",
        "message": "m",
        "dedupe_key": "probe",
        "occurrence_count": 1,
        "last_seen_at": NOW,
        "created_at": NOW,
        "created_by": None,
        "created_by_kind": "SYSTEM",
        "updated_at": NOW,
        "updated_by": None,
        "updated_by_kind": "SYSTEM",
    }


def _conflict_clause() -> str:
    statement = exceptions.open_item_upsert(_values(), NOW)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in sql and "DO UPDATE SET" in sql, sql
    return sql.split("ON CONFLICT", 1)[1].split("DO UPDATE SET", 1)[0]


def test_the_inference_predicate_is_the_index_predicate_verbatim() -> None:
    clause = _conflict_clause()
    assert clause.strip() == "(tenant_id, dedupe_key) WHERE status IN ('OPEN', 'IN_PROGRESS')", (
        clause
    )


def test_the_inference_predicate_carries_no_bind_parameter() -> None:
    clause = _conflict_clause()
    assert "%(" not in clause and "POSTCOMPILE" not in clause and ":status" not in clause, clause


def test_the_literal_predicate_follows_the_open_statuses() -> None:
    assert exceptions.OPEN_PREDICATE == "status IN ('OPEN', 'IN_PROGRESS')"
    assert tuple(exceptions.OPEN_STATUSES) == ("OPEN", "IN_PROGRESS")
