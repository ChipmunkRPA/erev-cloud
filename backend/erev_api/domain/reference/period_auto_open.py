"""SCH-05 ``period_auto_open`` and SCH-06 ``period_open_redirty`` (05 §SCH; REQ-CLS-001, -004).

Every 15 minutes the worker opens, as SYSTEM, every ``future`` period state of an enabled entity
book whose period ``start_date`` the entity's local date has reached (TZ-06: ``entity_today`` in
``legal_entity.time_zone``), for every ACTIVE tenant whose setup is complete (BR-PLT-02 keeps the
first open period a setup step of the tenant's own people). Each opening is the transition body of
``POST /periods/{id}/open`` (``commands.open_future_period``: one T-REF-07 row, ``reason_code``
null, the fixed comment below) and, in the SAME transaction (SCH-06), every combination group of
the entity with a contract event whose ``effective_date`` falls in the period and that is not
already dirty is marked ``dirty_since = now`` (RCP-04: nothing was posted while the period was
``future``; RCP-17 column set) — since Codex production-20260922-0349 the marking lives in the
shared opening core (``period_redirty``), so the manual ``POST /periods/{id}/open`` marks the same
groups. One SYSTEM unit of work per period state, so one refusal never blocks the others; a
refusal is logged by name and counted, never raised into the periodic.

Rev 1.83 (supervisor ruling R-97 (6)): an opening that could not be done at that moment is
isolated in the same way. When another transaction holds a row the opening needs beyond the lock
timeout (SQLSTATE 55P03), the two deadlock (40P01) or fail to serialize (40001), or PostgreSQL
cancels a statement of the opening at the statement timeout (57014), nothing of that period is
saved, the event is logged by its name and counted, and the tick goes on with the periods and
tenants after it; the next tick finds the period still due. The later due periods of the same
entity and book wait with it - a period opens only after the one before it (PRD SM-07), so each is
refused by name - and the next tick opens them in order.

Rev 1.106 (supervisor ruling R-118 (k); as R-50 (a) for the scheduler fan-out and the sweeper):
every other exception of an opening is isolated as well - a defect, a database error the kernel
has no answer for, a problem the commit raised. It is logged at error level with its class and
never its message (``period_auto_open.failed``), the period is counted as failed, and the tick
goes on. Only the server's own state ends the tick (``ends_the_tick``): the slug-less 503 set of
``db.errors.server_unavailable`` and the pool timeout say that nothing can be served, which is no
period's own and no reason to go on.

The same tick defers again the ``PERIOD_OPEN_REDIRTY`` job of a period state whose newest job
ended ``FAILED`` or ``CANCELLED`` (05 SCH-06 rev 1.79; supervisor ruling R-106 (a)): a period the
LOCK decision opened is re-marked by that job, not in the decision, and the job has no other way
back. Once per tick and period state, through ``period_redirty_job.defer_single``, which leaves a
period state with a live job alone — so a re-marking that cannot succeed runs its attempts once a
tick, never in a loop. A deferral that could not be made at that moment - the lock decision that
opens the period still holds the deferral's advisory lock, or a statement was cancelled - is
isolated as an opening is (rev 1.83): logged by its name, left for the next tick, and the period
states and tenants after it are served. Every other exception of a deferral is isolated as well
(rev 1.106: ``period_open_redirty.failed`` at error level, with its class), the server's own state
excepted.

Rev 1.139 (supervisor ruling of 2026-10-01 on R-118 (k)): the two reads per tenant are isolated by
the same rule. A tenant's due periods and its failed re-marking jobs are each read in a session of
their own; a read that raises anything but the server's own state is logged at error level with the
tenant (``period_auto_open.read_failed``, ``period_open_redirty.read_failed``), the step behind it
is skipped for that tenant - its other step still runs - and the tick goes on with the next tenant;
the report counts the tenants with a skipped step. The tenant list itself has nobody to go on with:
an exception there ends the tick. Every error event of the tick names the place the exception was
raised (``error_at``: module and line of the last frame of this code base, as ``logging.raised_at``
reads it), never its message.

Rev 1.163 (item DEMO-CLOCK-1; supervisor ruling R-116 (k)): the clock opens no period of a demo
tenant (``tenant.is_demo``). Its world keeps the month its seed states - PRD WLD-P-02 has Oct 2026
to Dec 2027 ``future`` - whatever the day a stack runs. Such a tenant is still listed and counted
and has no due period; its failed re-marking jobs are deferred again as any tenant's, and its
periods open by hand (``POST /periods/{id}/open``) or by the lock of the period before.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import Clock, entity_today
from erev_api.db import errors as db_errors
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    entity_book,
    legal_entity,
    period,
    period_state,
    tenant,
)
from erev_api.domain.platform.tenant_directory import active_tenants
from erev_api.domain.reference import period_redirty_job
from erev_api.domain.reference.commands import open_future_period
from erev_api.enums import PeriodState
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.logging import get_logger, raised_at, register_logger_fields
from erev_api.problems import Problem, from_db_error

AUTO_OPEN_COMMENT: Final = "Opened automatically on the period start date"  # 05 SCH-05 literal
REQUEST_ID: Final = "sch05-period-auto-open"
# 05 SCH-05 rev 1.83: the kernel's two answers that say "this transaction, not now" while the
# server is serving (04 §15.2: `lock-conflict` is SQLSTATE 40P01, 55P03 and 40001;
# `statement-timeout` is 57014), and the event the tick logs for each before it goes on.
NOT_NOW_EVENTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "lock-conflict": "period_auto_open.lock_conflict",
        "statement-timeout": "period_auto_open.statement_timeout",
    }
)
# The same two answers at the tick's other unit of work per period state, the re-deferral of a
# failed ``PERIOD_OPEN_REDIRTY`` job (05 SCH-06 rev 1.79), under that step's own events.
REDEFER_NOT_NOW_EVENTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "lock-conflict": "period_open_redirty.lock_conflict",
        "statement-timeout": "period_open_redirty.statement_timeout",
    }
)

# 05 SCH-05 rev 1.106 (supervisor ruling R-118 (k)): the event of an opening, and of a
# re-deferral, that failed for any other reason than the two answers above and the server's own
# state. Error level, with the exception's class and never its message (as ``job.fan_out_failed``
# and ``job.sweep_failed`` of the fan-out and the sweeper, DG-KRN-JOB-06).
FAILED_EVENT: Final = "period_auto_open.failed"
REDEFER_FAILED_EVENT: Final = "period_open_redirty.failed"
# 05 SCH-05 rev 1.139 (supervisor ruling of 2026-10-01 on R-118 (k)): the event of a tenant's
# read that failed - its due periods, its failed re-marking jobs - for any reason but the
# server's own state. Error level; the step behind the read is skipped for that tenant.
READ_FAILED_EVENT: Final = "period_auto_open.read_failed"
REDEFER_READ_FAILED_EVENT: Final = "period_open_redirty.read_failed"

_LOGGER: Final = "erev_api.domain.reference.period_auto_open"
register_logger_fields(
    _LOGGER,
    (
        "tenants",
        "tenants_skipped",
        "candidates",
        "opened",
        "redirtied",
        "failed",
        "redeferred",
        "failed_jobs",
        "tenant_id",
        "state_id",
        "entity",
        "book",
        "period_key",
        "slug",
        "rule_id",
        "sqlstate",
        "error_class",
        "error_at",
    ),
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """A ``future`` period state whose start date the entity's local date has reached."""

    state_id: UUID
    entity_id: UUID
    entity_code: str
    time_zone: str
    book_code: str
    period_id: UUID
    period_key: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class AutoOpenReport:
    tenants: int = 0
    candidates: int = 0
    opened: int = 0
    redirtied: int = 0
    failed: int = 0
    redeferred: int = 0  # PERIOD_OPEN_REDIRTY jobs deferred again after a failure (SCH-06)
    tenants_skipped: int = 0  # tenants with a step whose read failed (rev 1.139)


def due(start_date: date, today: date) -> bool:
    """SCH-05: a period is due on and after its start date in the entity's local calendar."""
    return start_date <= today


def candidates(session: Session, *, clock: Clock) -> list[Candidate]:
    """The due ``future`` period states of enabled entity books visible to ``session`` (RLS
    tenant scope), in entity, period, book order; none for a demo tenant (rev 1.163)."""
    rows = session.execute(
        select(
            period_state.c.id,
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            legal_entity.c.code,
            legal_entity.c.time_zone,
            period.c.period_key,
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
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
            .join(
                entity_book,
                and_(
                    entity_book.c.tenant_id == period_state.c.tenant_id,
                    entity_book.c.entity_id == period_state.c.entity_id,
                    entity_book.c.book_code == period_state.c.book_code,
                ),
            )
            .join(tenant, tenant.c.id == period_state.c.tenant_id)
        )
        .where(
            period_state.c.state == PeriodState.FUTURE.value,
            entity_book.c.is_enabled.is_(True),
            # 05 SCH-05 rev 1.163: the clock opens no period of a demo tenant (PRD WLD-P-02).
            tenant.c.is_demo.is_(False),
        )
        .order_by(legal_entity.c.code, period.c.start_date, period_state.c.book_code)
    ).all()
    found: list[Candidate] = []
    for row in rows:
        if not due(row.start_date, entity_today(clock, str(row.time_zone))):
            continue
        found.append(
            Candidate(
                state_id=UUID(str(row.id)),
                entity_id=UUID(str(row.entity_id)),
                entity_code=str(row.code),
                time_zone=str(row.time_zone),
                book_code=str(row.book_code),
                period_id=UUID(str(row.period_id)),
                period_key=str(row.period_key),
                start_date=row.start_date,
                end_date=row.end_date,
            )
        )
    return found


def not_now(error: BaseException) -> tuple[str | None, str | None]:
    """The slug of ``NOT_NOW_EVENTS`` that ``error`` is - the problem itself (the commit's mapper,
    or an ``except DBAPIError`` around a statement, raises it from the database error) or a
    database error ``from_db_error`` names so - else None; and the SQLSTATE of the database error
    behind it, when there is one. Any other exception is neither answer, whatever it was raised
    from."""
    found = db_errors.database_error_in(error)
    slug: str | None = None
    if isinstance(error, Problem):
        slug = error.slug
    elif isinstance(error, DBAPIError):
        mapped = from_db_error(error)
        slug = None if mapped is None else mapped.slug
    return (
        slug if slug in NOT_NOW_EVENTS else None,
        None if found is None else db_errors.sqlstate(found),
    )


def ends_the_tick(error: BaseException) -> bool:
    """05 SCH-05 rev 1.106 (supervisor ruling R-118 (k)): True when ``error`` is, or was raised
    from, an error that says the server cannot serve - the slug-less 503 set of 04 API-C-05
    (``db.errors.server_unavailable``: class 53, the connection codes, a server shutting down or
    starting, a connection lost without a SQLSTATE) or the application's own pool timeout. That is
    no period's own: the tick ends and the periodic fails, to be run again 15 minutes later. Every
    other exception is isolated to its period or its re-deferral."""
    return db_errors.server_unavailable_in(error) or db_errors.pool_timeout_in(error)


def eligible_tenants(
    runtime: JobRuntime, *, request_id: str, only: Sequence[UUID] | None = None
) -> list[UUID]:
    """ACTIVE tenants whose setup is complete, in id order; ``only`` narrows the run."""
    return active_tenants(runtime, request_id=request_id, setup_complete=True, only=only)


def _read[T](principal: Principal, event: str, read: Callable[[Session], T]) -> T | None:
    """One read of one tenant in a read-only session of its own (05 SCH-05 rev 1.139;
    supervisor ruling of 2026-10-01 on R-118 (k)). The server's own state ends the tick. Any
    other exception is logged at error level as ``event`` with the tenant, its class and the
    place it was raised, and None tells the caller to skip the step behind this read for this
    tenant."""
    try:
        with tenant_session(principal.db_context, read_only=True) as db:
            return read(db)
    except Exception as error:
        if ends_the_tick(error):
            raise
        get_logger(_LOGGER).error(
            event,
            tenant_id=str(principal.tenant_id),
            error_class=type(error).__name__,
            error_at=raised_at(error),
            sqlstate=not_now(error)[1],
        )
        return None


def redefer_failed_remarks(
    runtime: JobRuntime, principal: Principal, *, request_id: str
) -> int | None:
    """SCH-06 (05 rev 1.79; supervisor ruling R-106 (a)): defer again the ``PERIOD_OPEN_REDIRTY``
    job of every period state of the tenant whose newest job ended ``FAILED`` or ``CANCELLED``;
    returns the number deferred, or None when the tenant's failed jobs could not be read and the
    step was skipped (rev 1.139). One SYSTEM unit of work per period state; a period state with
    a ``QUEUED`` or ``RUNNING`` job is left alone (``defer_single``).

    05 SCH-05 rev 1.83 (supervisor ruling R-97 (6)): the tick isolates each period state here as
    it isolates an opening. ``defer_single`` waits for the deferral's advisory lock, which the
    lock decision that opens the period holds until it ends, and its commit takes the audit chain
    head: a wait beyond the lock timeout, a deadlock or a cancelled statement defers nothing for
    that period state, is logged by its name and leaves the newest job as it ended, so the next
    tick finds it again. Rev 1.106 (supervisor ruling R-118 (k)): any other exception is isolated
    too, logged at error level with its class; the server's own state alone ends the tick, as for
    an opening."""
    logger = get_logger(_LOGGER)
    failed = _read(principal, REDEFER_READ_FAILED_EVENT, period_redirty_job.failed_states)
    if failed is None:
        return None
    deferred = 0
    for state_id, failed_jobs in failed:
        try:
            with system_unit_of_work(runtime, principal, request_id=request_id) as uow:
                row = period_redirty_job.defer_single(uow, state_id=state_id)
                uow.commit()
        except Exception as error:
            if ends_the_tick(error):
                raise
            slug, sqlstate = not_now(error)
            if slug is None:
                logger.error(
                    REDEFER_FAILED_EVENT,
                    tenant_id=str(principal.tenant_id),
                    state_id=str(state_id),
                    failed_jobs=failed_jobs,
                    error_class=type(error).__name__,
                    error_at=raised_at(error),
                    slug=error.slug if isinstance(error, Problem) else None,
                    sqlstate=sqlstate,
                )
                continue
            logger.warning(
                REDEFER_NOT_NOW_EVENTS[slug],
                tenant_id=str(principal.tenant_id),
                state_id=str(state_id),
                failed_jobs=failed_jobs,
                sqlstate=sqlstate,
            )
            continue
        if row is None:
            continue
        deferred += 1
        logger.warning(
            "period_open_redirty.redeferred",
            tenant_id=str(principal.tenant_id),
            state_id=str(state_id),
            failed_jobs=failed_jobs,
        )
    return deferred


def open_due_period(
    runtime: JobRuntime, principal: Principal, item: Candidate, *, request_id: str
) -> int | None:
    """Open one due period in a SYSTEM unit of work of its own; returns the number of groups
    SCH-06 re-marked, or None when the period was not opened - refused by its own rules, left
    for the next tick, or failed - which this function has logged. The caller counts a None once
    (rev 1.139: a refusal whose unit of work then failed to discard was counted twice)."""
    logger = get_logger(_LOGGER)
    tenant_id = str(principal.tenant_id)
    marked: int | None = None
    try:
        with system_unit_of_work(runtime, principal, request_id=request_id) as uow:
            try:
                opening = open_future_period(uow, state_id=item.state_id, comment=AUTO_OPEN_COMMENT)
            except Problem as problem:  # the state moved or the book was disabled meanwhile
                if problem.slug in NOT_NOW_EVENTS:
                    raise  # not a refusal of this period: settled below, like the raw error
                logger.warning(
                    "period_auto_open.refused",
                    tenant_id=tenant_id,
                    state_id=str(item.state_id),
                    entity=item.entity_code,
                    book=item.book_code,
                    period_key=item.period_key,
                    slug=problem.slug,
                    rule_id=problem.errors[0].rule_id if problem.errors else None,
                )
                # The unit of work is discarded on exit, nothing committed.
            else:
                uow.commit()
                marked = opening.redirtied  # SCH-06 ran inside the shared core
    except Exception as error:
        # 05 SCH-05 rev 1.83 (ruling R-97 (6)): the tick isolates each period. Another
        # transaction held a row this opening needs - the period's state row, or a group row
        # SCH-06 marks - beyond the lock timeout, the two deadlocked, or a statement ran into the
        # statement timeout: nothing of this period was saved, the next tick finds it still due,
        # and the periods and tenants after it are opened now. Rev 1.106 (ruling R-118 (k)): so
        # is every other exception, at error level with its class; only the server's own state
        # ends the tick.
        if ends_the_tick(error):
            raise
        slug, sqlstate = not_now(error)
        if slug is None:
            logger.error(
                FAILED_EVENT,
                tenant_id=tenant_id,
                state_id=str(item.state_id),
                entity=item.entity_code,
                book=item.book_code,
                period_key=item.period_key,
                error_class=type(error).__name__,
                error_at=raised_at(error),
                slug=error.slug if isinstance(error, Problem) else None,
                sqlstate=sqlstate,
            )
        else:
            logger.warning(
                NOT_NOW_EVENTS[slug],
                tenant_id=tenant_id,
                state_id=str(item.state_id),
                entity=item.entity_code,
                book=item.book_code,
                period_key=item.period_key,
                sqlstate=sqlstate,
            )
        return None
    if marked is None:
        return None
    logger.info(
        "period_auto_open.opened",
        tenant_id=tenant_id,
        state_id=str(item.state_id),
        entity=item.entity_code,
        book=item.book_code,
        period_key=item.period_key,
        redirtied=marked,
    )
    return marked


def run(
    runtime: JobRuntime,
    *,
    request_id: str = REQUEST_ID,
    only_tenants: Sequence[UUID] | None = None,
) -> AutoOpenReport:
    """SCH-05 + SCH-06 over every eligible tenant; returns the counts it also logs."""
    logger = get_logger(_LOGGER)
    tenant_ids = eligible_tenants(runtime, request_id=request_id, only=only_tenants)
    found_total = opened = redirtied = failed = redeferred = tenants_skipped = 0
    for tenant_id in tenant_ids:
        principal = system_principal(tenant_id)
        # The tenant's two steps, each behind a read of its own: a step whose read failed is
        # skipped, the other one still runs (rev 1.139).
        found = _read(principal, READ_FAILED_EVENT, lambda db: candidates(db, clock=runtime.clock))
        for item in found or ():
            marked = open_due_period(runtime, principal, item, request_id=request_id)
            if marked is None:
                failed += 1
                continue
            opened += 1
            redirtied += marked
        found_total += len(found or ())
        again = redefer_failed_remarks(runtime, principal, request_id=request_id)
        redeferred += again or 0
        if found is None or again is None:
            tenants_skipped += 1
    report = AutoOpenReport(
        tenants=len(tenant_ids),
        candidates=found_total,
        opened=opened,
        redirtied=redirtied,
        failed=failed,
        redeferred=redeferred,
        tenants_skipped=tenants_skipped,
    )
    logger.info(
        "period_auto_open.completed",
        tenants=report.tenants,
        tenants_skipped=report.tenants_skipped,
        candidates=report.candidates,
        opened=report.opened,
        redirtied=report.redirtied,
        failed=report.failed,
        redeferred=report.redeferred,
    )
    return report
