"""Retention of the global identity rows (04 T-PLT-08, T-PLT-42 IM-E; 05 SCH-08; REQ-PLT-004;
BUILD_SPEC PLF-22).

``user_session`` rows are deleted 30 days after ``ended_at`` and ``password_reset_token`` rows once
``expires_at`` has passed. Both tables are global (RLS-NONE-U), so the deletes run through the
identity session (DG-KRN-DB-02), at most 100 rows per transaction (DG-KRN-JOB-04). Rows another
transaction holds are skipped and deleted by a later sweep.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import delete, select
from sqlalchemy.sql.dml import ReturningDelete

from erev_api.auth.sessions import RETENTION
from erev_api.db.session import identity_session
from erev_api.db.tables.platform import password_reset_token, user_session

CHUNK: Final = 100


def _purge(statement: ReturningDelete[Any], *, request_id: str) -> int:
    total = 0
    while True:
        with identity_session(request_id=request_id) as db:
            deleted = len(db.execute(statement).all())
        total += deleted
        if deleted < CHUNK:
            return total


def purge_ended_sessions(*, now: datetime, request_id: str) -> int:
    """Delete the sessions that ended more than 30 days before ``now``; returns the count."""
    doomed: Any = (
        select(user_session.c.id)
        .where(user_session.c.ended_at.is_not(None), user_session.c.ended_at < now - RETENTION)
        .order_by(user_session.c.ended_at, user_session.c.id)
        .limit(CHUNK)
        .with_for_update(skip_locked=True)
    )
    statement = (
        delete(user_session)
        .where(user_session.c.id.in_(doomed.scalar_subquery()))
        .returning(user_session.c.id)
    )
    return _purge(statement, request_id=request_id)


def purge_expired_reset_tokens(*, now: datetime, request_id: str) -> int:
    """Delete the password reset tokens past ``expires_at``; returns the count."""
    doomed: Any = (
        select(password_reset_token.c.id)
        .where(password_reset_token.c.expires_at < now)
        .order_by(password_reset_token.c.expires_at, password_reset_token.c.id)
        .limit(CHUNK)
        .with_for_update(skip_locked=True)
    )
    statement = (
        delete(password_reset_token)
        .where(password_reset_token.c.id.in_(doomed.scalar_subquery()))
        .returning(password_reset_token.c.id)
    )
    return _purge(statement, request_id=request_id)
