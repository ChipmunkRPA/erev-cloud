"""Retention sweep ``RETENTION_SWEEP`` (04 T-PLT-08, T-PLT-16, T-PLT-28, T-PLT-42 IM-E; 05 §5.6,
SCH-07, SCH-08; dev-guide DG-KRN-JOB-04, DG-KRN-JOB-07; REQ-PLT-026, REQ-OPS-006; BUILD_SPEC PLF-22,
PLF-25).

A sweep deletes the tenant's ``idempotency_record`` rows past ``expires_at`` and its ``api_token``
rows more than 7 days past ``expires_at``, then the global ``user_session`` rows that ended more
than 30 days ago and ``password_reset_token`` rows past ``expires_at``. Each chunk of at most 100
rows is its own transaction; the job heartbeats after each chunk and stops between chunks when
cancelled. ``result.counts`` names the four tables.

The periodic task ``idempotency_purge`` (03:00 UTC) defers one sweep per ACTIVE tenant that has no
sweep QUEUED or RUNNING. ``session_purge`` (03:10 UTC) purges the global rows directly, so they
expire even while no tenant is ACTIVE. The deletes are AUD-OPS: no audit event.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from sqlalchemy import delete, select, tuple_
from sqlalchemy.sql.dml import ReturningDelete

from erev_api.auth import api_clients
from erev_api.auth import retention as identity_retention
from erev_api.clock import Clock
from erev_api.db.tables.platform import api_token, idempotency_record
from erev_api.enums import JobKind
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task

CHUNK: Final = 100
# 05 §5.6 execution profile: 5 attempts, exponential wait 30 s.
RETENTION_RETRY: Final = RetryPolicy(max_attempts=5, backoff_seconds=(30, 60, 120, 240))
TABLES: Final = ("idempotency_record", "api_token", "user_session", "password_reset_token")


def _purge_chunks(jc: JobContext, statement: ReturningDelete[Any]) -> int:
    """Run a chunked delete until a chunk is short or the job is cancelled; returns the total."""
    total = 0
    while True:
        with jc.unit_of_work() as uow:
            deleted = len(uow.session.execute(statement).all())
            uow.commit()
        total += deleted
        jc.heartbeat()
        if deleted < CHUNK or jc.cancel_requested():
            return total


def _idempotency_records(jc: JobContext, now: datetime) -> ReturningDelete[Any]:
    doomed = (
        select(idempotency_record.c.principal_id, idempotency_record.c.idempotency_key)
        .where(
            idempotency_record.c.tenant_id == jc.tenant_id,
            idempotency_record.c.expires_at < now,
        )
        .order_by(idempotency_record.c.expires_at)
        .limit(CHUNK)
        .with_for_update(skip_locked=True)
    )
    return (
        delete(idempotency_record)
        .where(
            idempotency_record.c.tenant_id == jc.tenant_id,
            tuple_(idempotency_record.c.principal_id, idempotency_record.c.idempotency_key).in_(
                doomed
            ),
        )
        .returning(idempotency_record.c.idempotency_key)
    )


def _api_tokens(jc: JobContext, now: datetime) -> ReturningDelete[Any]:
    doomed = (
        select(api_token.c.id)
        .where(
            api_token.c.tenant_id == jc.tenant_id,
            api_token.c.expires_at < now - api_clients.TOKEN_RETENTION,
        )
        .order_by(api_token.c.expires_at)
        .limit(CHUNK)
        .with_for_update(skip_locked=True)
    )
    return (
        delete(api_token)
        .where(api_token.c.tenant_id == jc.tenant_id, api_token.c.id.in_(doomed))
        .returning(api_token.c.id)
    )


@task(JobKind.RETENTION_SWEEP, retry=RETENTION_RETRY)
def retention_sweep(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``RETENTION_SWEEP``: delete the rows past their retention (IM-E)."""
    now = jc.clock.now()
    counts = dict.fromkeys(TABLES, 0)
    counts["idempotency_record"] = _purge_chunks(jc, _idempotency_records(jc, now))
    if not jc.cancel_requested():
        counts["api_token"] = _purge_chunks(jc, _api_tokens(jc, now))
    if not jc.cancel_requested():
        request_id = f"job-{jc.job_id}"
        counts["user_session"] = identity_retention.purge_ended_sessions(
            now=now, request_id=request_id
        )
        counts["password_reset_token"] = identity_retention.purge_expired_reset_tokens(
            now=now, request_id=request_id
        )
    return JobOutcome(
        state="SUCCEEDED", result={"href": f"/api/v1/jobs/{jc.job_id}", "counts": counts}
    )


def defer_sweeps(clock: Clock, *, request_id: str = "idempotency-purge") -> int:
    """SCH-07: defer one ``RETENTION_SWEEP`` per ACTIVE tenant without a sweep QUEUED or RUNNING;
    returns the number deferred."""
    return registry.defer_for_active_tenants(
        JobKind.RETENTION_SWEEP, {}, clock=clock, request_id=request_id
    )


def purge_global(clock: Clock, *, request_id: str = "session-purge") -> dict[str, int]:
    """SCH-08: delete the expired global session and reset token rows; returns the counts."""
    now = clock.now()
    return {
        "user_session": identity_retention.purge_ended_sessions(now=now, request_id=request_id),
        "password_reset_token": identity_retention.purge_expired_reset_tokens(
            now=now, request_id=request_id
        ),
    }
