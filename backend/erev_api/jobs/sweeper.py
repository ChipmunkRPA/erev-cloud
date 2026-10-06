"""Job sweeper KRN-JOB (dev-guide DG-KRN-JOB-06; 05 §5.7 SCH-04, JOB-06; D-80; REQ-OPS-006,
CTL-040).

Every minute the worker's periodic task reads the tenant directory once, together with the
``erev.run_job`` tasks stalled in ``doing`` whose worker stopped heartbeating
(``JobManager.get_stalled_jobs``), and, per tenant:

- defers again every QUEUED job without ``procrastinate_job_id`` older than 60 seconds, which an
  after-commit dispatch that failed leaves behind (DG-KRN-UOW-02);
- recovers every QUEUED job whose Procrastinate task can no longer run it: a ``failed``,
  ``cancelled`` or ``aborted`` task is replaced by a new dispatch, and a stalled task is retried in
  place, while the kind's retry policy allows another attempt; after the last attempt the job is
  FAILED with problem ``job-stalled`` (``jobs.registry.retry_stranded``; SPEC-Q-187 (b) overruled).
  The attempt number is the task's ``attempt`` argument plus its in-place retries;
- settles every RUNNING job whose ``updated_at`` is older than 10 minutes as a failed attempt with
  problem ``job-stalled`` and detail "no heartbeat for 10 minutes": the job is re-queued while its
  retry policy allows another attempt, otherwise it is FAILED and its initiator is notified
  (``jobs.registry.fail_attempt``). The attempt number is the ``attempt`` argument of the job's
  current Procrastinate task. A job with a transaction open is passed over and the pass is
  logged ``job.sweep_passed_over`` (05 JOB-06 rev 1.200): its worker is alive, and a job is not
  settled beside the transaction that would then commit under it.

Each job is settled in isolation (DG-KRN-JOB-06 rev 1.89): ending a job FAILED writes
``job.finish`` to its tenant's audit chain (04 T-PLT-27), so a job whose settlement fails — its
tenant's chain cannot take the event, for example — is logged ``job.sweep_failed`` and the sweep
continues with the next job and the next tenant.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from erev_api.clock import Clock
from erev_api.db.session import DbContext, platform_session, tenant_session
from erev_api.db.tables.platform import job, tenant
from erev_api.enums import JobState
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import (
    REDISPATCHED_STATUSES,
    STALL_DETAIL,
    STALL_SLUG,
    dispatch,
    fail_attempt,
    isolated,
    retry_stranded,
    stalled_task_ids,
)
from erev_api.problems import Problem

UNDISPATCHED_AGE: Final = timedelta(seconds=60)
STALL_AGE: Final = timedelta(minutes=10)
STRANDED_DETAIL: Final = "the worker task stopped before the job started"  # SPEC-Q-220
SWEEP_FAILED: Final = "job.sweep_failed"  # DG-KRN-JOB-06 rev 1.89: one job never stops the sweep
_TASK_ARGS: Final = text("SELECT args FROM procrastinate_jobs WHERE id = :id")
_TASKS: Final = text(
    "SELECT id, status, args, attempts FROM procrastinate_jobs WHERE id = ANY(:ids)"
)


def _directory_tenant_ids(session: Session) -> list[UUID]:
    return [
        UUID(str(value)) for value in session.scalars(select(tenant.c.id).order_by(tenant.c.id))
    ]


def _tenant_ids(request_id: str) -> list[UUID]:
    with platform_session("tenant_directory", actor_user_id=None, request_id=request_id) as session:
        return _directory_tenant_ids(session)


def _directory(request_id: str) -> tuple[list[UUID], frozenset[int]]:
    """The tenant ids and the stalled ``erev.run_job`` task ids, over one directory read."""
    with platform_session("tenant_directory", actor_user_id=None, request_id=request_id) as session:
        return _directory_tenant_ids(session), stalled_task_ids(session)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _requeue(tenant_id: UUID, now: datetime) -> int:
    requeued = 0
    with tenant_session(_context(tenant_id)) as session:
        rows = session.execute(
            select(job.c.id, job.c.queue)
            .where(
                job.c.state == JobState.QUEUED.value,
                job.c.procrastinate_job_id.is_(None),
                job.c.created_at < now - UNDISPATCHED_AGE,
            )
            .order_by(job.c.created_at, job.c.id)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            dispatch(
                session,
                job_id=UUID(str(row.id)),
                tenant_id=tenant_id,
                queue=str(row.queue),
                now=now,
            )
            requeued += 1
    return requeued


def _attempt(args: object) -> int:
    if isinstance(args, dict) and isinstance(args.get("attempt"), int):
        return int(args["attempt"])
    return 1


def _redispatch_stranded(tenant_id: UUID, runtime: JobRuntime, stalled: frozenset[int]) -> int:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(job.c.id, job.c.procrastinate_job_id)
            .where(job.c.state == JobState.QUEUED.value, job.c.procrastinate_job_id.is_not(None))
            .order_by(job.c.created_at, job.c.id)
        ).all()
        if not rows:
            return 0
        ids = [int(row.procrastinate_job_id) for row in rows]
        tasks = {int(task.id): task for task in session.execute(_TASKS, {"ids": ids})}
    settled = 0
    for row in rows:
        task_id = int(row.procrastinate_job_id)
        task = tasks.get(task_id)
        if task is None:
            continue
        in_doing = task.status == "doing" and task_id in stalled
        if not in_doing and task.status not in REDISPATCHED_STATUSES:
            continue
        with isolated(SWEEP_FAILED, tenant_id=str(tenant_id), job_id=str(row.id)):
            state = retry_stranded(
                UUID(str(row.id)),
                tenant_id,
                task_id=task_id,
                attempt=_attempt(task.args) + int(task.attempts),
                stalled=in_doing,
                error=Problem(STALL_SLUG, STRANDED_DETAIL),
                runtime=runtime,
            )
            if state is not None:
                settled += 1
    return settled


def _fail_stalled(tenant_id: UUID, runtime: JobRuntime) -> int:
    cutoff = runtime.clock.now() - STALL_AGE
    with tenant_session(_context(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(job.c.id, job.c.procrastinate_job_id)
            .where(job.c.state == JobState.RUNNING.value, job.c.updated_at < cutoff)
            .order_by(job.c.updated_at, job.c.id)
        ).all()
        attempts = {
            UUID(str(row.id)): (
                1
                if row.procrastinate_job_id is None
                else _attempt(
                    session.execute(
                        _TASK_ARGS, {"id": row.procrastinate_job_id}
                    ).scalar_one_or_none()
                )
            )
            for row in rows
        }
    settled = 0
    for job_id, attempt in attempts.items():
        with isolated(SWEEP_FAILED, tenant_id=str(tenant_id), job_id=str(job_id)):
            state = fail_attempt(
                job_id,
                tenant_id,
                attempt=attempt,
                error=Problem(STALL_SLUG, STALL_DETAIL),
                runtime=runtime,
                stalled_before=cutoff,
            )
            if state is not None:
                settled += 1
    return settled


def requeue_undispatched(clock: Clock, *, request_id: str = "job-sweeper") -> int:
    """Defer again every QUEUED job whose dispatch never recorded an id; returns the count."""
    now = clock.now()
    return sum(_requeue(tenant_id, now) for tenant_id in _tenant_ids(request_id))


def redispatch_stranded(runtime: JobRuntime, *, request_id: str = "job-sweeper") -> int:
    """Recover every QUEUED job whose Procrastinate task failed, was cancelled or aborted, or
    stalled with a dead worker; returns the number settled."""
    tenant_ids, stalled = _directory(request_id)
    return sum(_redispatch_stranded(tenant_id, runtime, stalled) for tenant_id in tenant_ids)


def fail_stalled(runtime: JobRuntime, *, request_id: str = "job-sweeper") -> int:
    """Settle every RUNNING job silent for 10 minutes as a stalled attempt; returns the count."""
    return sum(_fail_stalled(tenant_id, runtime) for tenant_id in _tenant_ids(request_id))


def sweep(runtime: JobRuntime, *, request_id: str = "job-sweeper") -> tuple[int, int]:
    """SCH-04: the three sweeps over one tenant directory read; returns (requeued, stalled), where
    requeued counts undispatched and stranded jobs deferred again or settled."""
    now = runtime.clock.now()
    tenant_ids, stalled_tasks = _directory(request_id)
    requeued = stalled = 0
    for tenant_id in tenant_ids:
        requeued += _requeue(tenant_id, now)
        requeued += _redispatch_stranded(tenant_id, runtime, stalled_tasks)
        stalled += _fail_stalled(tenant_id, runtime)
    return requeued, stalled
