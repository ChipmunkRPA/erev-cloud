"""``PERIOD_OPEN_REDIRTY`` — the re-marking of a period the lock decision opened (04 E-14, T-PLT-27
and §14.1 DB-07 note rev 1.164; 05 SCH-06 and §5.6 rev 1.79; PRD BR-CLS-03; supervisor rulings
R-101 (a) and R-106 (a) of 2026-09-30; item CLO-LOCK-OPEN-REDIRTY-1).

BR-CLS-03: the lock decision of a period opens the next one when it is ``future``. 05 SCH-06
re-marks dirty the clean combination groups with an effect in an opened period; the manual route
and the scheduled opening do so in the opening's own transaction
(``commands.open_future_period``). The lock decision cannot: it holds the closing period's state
row, the re-marking takes ``combination_group`` rows, and a posting holds such a row while it waits
for that state row (04 DB-07). So the decision DEFERS the re-marking — this job — and the handler
marks the groups as SYSTEM in a transaction of its own, which takes no period state row.

The job's subject is the period state it re-marks (T-PLT-27 ``subject_type`` ``period_state``):
``job.start`` names the period, and every read below finds the jobs of a period state by subject.
``params.period_state_id`` names the same state for the handler.

Until a job of the opened period state has succeeded nothing tells a recompute which groups the
opening reaches. The window is enforced and visible, never silent:

- ``remark_pending``: the period's ``NO_DIRTY_GROUPS`` gate fails by name while the newest job of
  the period state has not succeeded — queued, running, failed or cancelled alike — and is not
  waivable for that reason (``close.gates``, ``close.commands.waive_checklist_item``);
- ``of_state``: the period's "Failed jobs" blocker counts the job once the newest one ended
  ``FAILED`` (``gates.blocker_statement``, by the rule of every subject:
  ``platform.jobs.newest_of_subject``) — a waiting job is not a failed one, the gate names it;
- ``failed_states`` / ``defer_single``: a job that ended ``FAILED`` or ``CANCELLED`` is deferred
  again by the scheduler's period tick (SCH-05), once per tick and period state; one function
  makes every deferral and keeps at most one live job per period state.

A period opened by ``POST /periods/{id}/open`` or by the schedule has no such job and none of the
above applies to it: those paths re-mark in their own transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import job, period, period_state
from erev_api.domain.imports.job_items import failed_item
from erev_api.domain.platform import jobs as platform_jobs
from erev_api.domain.reference import period_redirty
from erev_api.enums import ExceptionSource, JobKind, JobState
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import FailedSubject, JobOutcome, RetryPolicy, task
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# ``platform.jobs`` is imported as a module and read at call time: it reaches this module again
# (``approval_queries``, ``close.gates``), so a name bound from it at import time fails whenever
# ``platform.jobs`` is the first of the three to be imported.
JOB: Final = JobKind.PERIOD_OPEN_REDIRTY  # 04 E-14 rev 1.164; 05 §5.6 queue ``close``
SUBJECT_TYPE: Final = "period_state"  # 04 T-PLT-27 rev 1.164: the job's subject
STATE_PARAM: Final = "period_state_id"  # the same period state, for the handler
RETRY: Final = RetryPolicy(max_attempts=3)  # 05 §5.6: 3 attempts
HREF: Final = "/api/v1/periods/{state_id}"
LIVE: Final = (JobState.QUEUED.value, JobState.RUNNING.value)
SUCCEEDED: Final = (JobState.SUCCEEDED.value, JobState.SUCCEEDED_WITH_EXCEPTIONS.value)
# ended without success: the scheduler's tick defers the re-marking again
ENDED_UNSUCCESSFUL: Final = (JobState.FAILED.value, JobState.CANCELLED.value)
LOCK_KEY: Final = "period-open-redirty:{state_id}"

_OF_KIND: Final = and_(job.c.kind == JOB.value, job.c.subject_type == SUBJECT_TYPE)


def of_state(state_id: UUID) -> ColumnElement[bool]:
    """A predicate over ``job``: the jobs of this kind that work on the period state. With
    ``platform.jobs.newest_of_subject`` and state ``FAILED`` it is what the period's "Failed
    jobs" blocker counts (SCREENS_B BLK-08) until the scheduler's tick has deferred the
    re-marking again."""
    return and_(_OF_KIND, job.c.subject_id == state_id)


def unsucceeded(state_id: UUID) -> ColumnElement[bool]:
    """A predicate over ``job``: the NEWEST job of the period state — at most one row — when it
    has not succeeded: queued, running, failed or cancelled alike. A job that a later job of the
    same period state follows is history: once a later one succeeds the period is re-marked,
    whatever the earlier ones did."""
    return and_(
        of_state(state_id),
        platform_jobs.newest_of_subject(),
        job.c.state.not_in(SUCCEEDED),
    )


def remark_pending(session: Session, state_id: UUID) -> bool:
    """True while the period state has a job of this kind and its newest one has not succeeded:
    the groups with an effect in the opened period are not known to be marked (R-106 (a))."""
    newest = select(job.c.id).where(unsucceeded(state_id)).exists()
    return bool(session.execute(select(newest)).scalar_one())


def failed_states(session: Session) -> list[tuple[UUID, int]]:
    """The period states whose newest job of this kind ended ``FAILED`` or ``CANCELLED``, with the
    number of jobs of the period state that ended so — what the scheduler's tick defers again."""
    newest = session.execute(
        select(job.c.subject_id, job.c.state)
        .where(_OF_KIND)
        .distinct(job.c.subject_id)
        .order_by(job.c.subject_id, job.c.created_at.desc(), job.c.id.desc())
    ).all()
    wanted = [UUID(str(state_id)) for state_id, state in newest if str(state) in ENDED_UNSUCCESSFUL]
    if not wanted:
        return []
    counts: dict[UUID, int] = {
        UUID(str(state_id)): int(ended)
        for state_id, ended in session.execute(
            select(job.c.subject_id, func.count())
            .where(
                _OF_KIND,
                job.c.subject_id.in_(wanted),
                job.c.state.in_(ENDED_UNSUCCESSFUL),
            )
            .group_by(job.c.subject_id)
        )
    }
    return [(state_id, counts.get(state_id, 0)) for state_id in sorted(wanted, key=str)]


def defer_single(uow: UnitOfWork, *, state_id: UUID) -> Mapping[str, Any] | None:
    """Defer the re-marking of the period state in ``uow``'s transaction unless a job of it is
    ``QUEUED`` or ``RUNNING``; returns the job row, or None when one is live.

    Every deferral goes through here — the lock decision that opens the period and the scheduler's
    tick — under a transaction advisory lock keyed by the period state, so two deferrals of one
    period state never leave two live jobs."""
    session = uow.session
    key = LOCK_KEY.format(state_id=state_id)
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
    live = session.execute(
        select(job.c.id).where(of_state(state_id), job.c.state.in_(LIVE)).limit(1)
    ).first()
    if live is not None:
        return None
    return uow.defer(
        JOB, {STATE_PARAM: str(state_id)}, subject_type=SUBJECT_TYPE, subject_id=state_id
    )


def remark(uow: UnitOfWork, *, state_id: UUID) -> int:
    """SCH-06 for a period state that is open already: mark dirty the clean combination groups the
    opening reaches (``period_redirty``); returns the number marked. The state row is read without
    a lock — no ``combination_group`` lock follows a period state row here (04 DB-07) — and only
    clean groups are stamped, so a second run marks nothing twice."""
    session = uow.session
    found = session.execute(
        select(
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            period.c.start_date,
            period.c.end_date,
        )
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(period_state.c.id == state_id)
    ).one_or_none()
    if found is None:
        raise Problem("not-found")
    entity_id = UUID(str(found.entity_id))
    book_code = str(found.book_code)
    gap = period_redirty.deferred_gap(
        period_redirty.period_states_of(session, entity_id=entity_id, book_code=book_code),
        opened_start=found.start_date,
    )
    return period_redirty.redirty_groups(
        uow,
        entity_id=entity_id,
        book_code=book_code,
        period_id=UUID(str(found.period_id)),
        start_date=found.start_date,
        end_date=found.end_date,
        gap_period_ids=gap,
    )


def failed_remark(
    session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
) -> FailedSubject | None:
    """05 JOB-07 rev 1.165: what the exception item of a failed re-marking names — the entity and
    the period of the period state the job re-marks (04 T-PLT-27 ``subject_type``
    ``period_state``). The cockpit counts the failed job itself (BLK-08); the item tells the
    entity's readers of the queue."""
    found = session.execute(
        select(period_state.c.entity_id, period_state.c.period_id).where(
            period_state.c.id == subject_id
        )
    ).one_or_none()
    if found is None:
        return None
    return FailedSubject(entity_id=UUID(str(found[0])), period_id=UUID(str(found[1])))


@task(JOB, retry=RETRY, failed_item=failed_item(ExceptionSource.CLOSE, failed_remark))
def run_remark(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``PERIOD_OPEN_REDIRTY`` (05 §5.6 queue ``close``): one transaction as SYSTEM. A retried
    attempt whose marking is stored finds the groups dirty and marks nothing more."""
    state_id = UUID(str(params[STATE_PARAM]))
    with jc.unit_of_work() as uow:
        marked = remark(uow, state_id=state_id)
        uow.commit()
    return JobOutcome(
        state="SUCCEEDED",
        result={"href": HREF.format(state_id=state_id), "counts": {"redirtied": marked}},
    )


__all__ = [
    "JOB",
    "STATE_PARAM",
    "SUBJECT_TYPE",
    "defer_single",
    "failed_states",
    "of_state",
    "remark",
    "remark_pending",
    "run_remark",
    "unsucceeded",
]
