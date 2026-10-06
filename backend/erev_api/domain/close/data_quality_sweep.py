"""SCH-10 ``data_quality_monitors`` (05 §SCH; REQ-CLS-019).

Daily at 04:00 UTC the worker evaluates the published ``DATA_QUALITY`` rule sets of every ACTIVE
tenant: for each period state in an evaluated state (``open``, ``closing``, ``reopened``) it runs
the CLO-5 monitors (``close.monitors.run_monitors`` — the evaluator of the tenant's PUBLISHED
``DATA_QUALITY`` rules: ``overrides_of`` reads their ``outputs.severity`` by monitor code), which
raises one exception item per finding by ``dedupe_key`` (a re-run counts the open item again),
notifies the entity's Revenue Accountants of new items (NTF-11) and settles the open items of the
entity and period that no evaluated book of the entity finds any more (05 SCH-10 rev 1.124; 04
T-IMP-05 "A monitor finding that is gone"). One SYSTEM unit of work per
period, so one refusal never blocks the others; refusals are logged by name and counted, never
raised into the periodic. Periods in other states are not evaluated (they keep their items).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import system_principal
from erev_api.db.session import tenant_session
from erev_api.db.tables import legal_entity, period, period_state
from erev_api.domain.close import gates, monitors
from erev_api.domain.platform.tenant_directory import active_tenants
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem

REQUEST_ID: Final = "sch10-data-quality-monitors"

_LOGGER: Final = "erev_api.domain.close.data_quality_sweep"
register_logger_fields(
    _LOGGER,
    (
        "tenants",
        "periods",
        "evaluated",
        "created",
        "seen_again",
        "settled",
        "severity_changed",
        "open_blocking",
        "failed",
        "tenant_id",
        "state_id",
        "entity",
        "book",
        "period_key",
        "slug",
        "rule_id",
    ),
)


@dataclass(frozen=True, slots=True)
class EvaluatedPeriod:
    state_id: UUID
    entity_id: UUID
    entity_code: str
    book_code: str
    period_id: UUID
    period_key: str


@dataclass(frozen=True, slots=True)
class SweepReport:
    tenants: int = 0
    periods: int = 0
    evaluated: int = 0
    created: int = 0
    seen_again: int = 0
    severity_changed: int = 0
    failed: int = 0
    settled: int = 0  # open items whose finding is gone (05 SCH-10 rev 1.124)


def evaluated_periods(session: Session) -> list[EvaluatedPeriod]:
    """The period states in ``gates.EVALUATED_STATES`` visible to ``session`` (RLS tenant scope),
    in entity, period, book order."""
    rows = session.execute(
        select(
            period_state.c.id,
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            legal_entity.c.code,
            period.c.period_key,
        )
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            ).join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
        )
        .where(period_state.c.state.in_(sorted(gates.EVALUATED_STATES)))
        .order_by(legal_entity.c.code, period.c.start_date, period_state.c.book_code)
    ).all()
    return [
        EvaluatedPeriod(
            state_id=UUID(str(row.id)),
            entity_id=UUID(str(row.entity_id)),
            entity_code=str(row.code),
            book_code=str(row.book_code),
            period_id=UUID(str(row.period_id)),
            period_key=str(row.period_key),
        )
        for row in rows
    ]


def run(
    runtime: JobRuntime,
    *,
    request_id: str = REQUEST_ID,
    only_tenants: Sequence[UUID] | None = None,
) -> SweepReport:
    """SCH-10 over every ACTIVE tenant; returns the counts it also logs."""
    logger = get_logger(_LOGGER)
    tenant_ids = active_tenants(runtime, request_id=request_id, only=only_tenants)
    periods = evaluated = created = seen_again = severity_changed = settled = failed = 0
    for tenant_id in tenant_ids:
        principal = system_principal(tenant_id)
        with tenant_session(principal.db_context, read_only=True) as db:
            found = evaluated_periods(db)
        periods += len(found)
        for item in found:
            with system_unit_of_work(runtime, principal, request_id=request_id) as uow:
                try:
                    result = monitors.run_monitors(
                        uow, item.entity_id, item.book_code, item.period_id
                    )
                except Problem as problem:  # the state moved between the read and the run
                    failed += 1
                    logger.warning(
                        "data_quality_monitors.refused",
                        tenant_id=str(tenant_id),
                        state_id=str(item.state_id),
                        entity=item.entity_code,
                        book=item.book_code,
                        period_key=item.period_key,
                        slug=problem.slug,
                        rule_id=problem.errors[0].rule_id if problem.errors else None,
                    )
                    continue  # the unit of work is discarded on exit, nothing committed
                uow.commit()
            evaluated += 1
            created += result.created
            seen_again += result.seen_again
            severity_changed += result.severity_changed
            settled += len(result.settled)
            logger.info(
                "data_quality_monitors.evaluated",
                tenant_id=str(tenant_id),
                state_id=str(item.state_id),
                entity=item.entity_code,
                book=item.book_code,
                period_key=item.period_key,
                created=result.created,
                seen_again=result.seen_again,
                severity_changed=result.severity_changed,
                settled=len(result.settled),
                open_blocking=result.open_blocking,
            )
    report = SweepReport(
        tenants=len(tenant_ids),
        periods=periods,
        evaluated=evaluated,
        created=created,
        seen_again=seen_again,
        severity_changed=severity_changed,
        settled=settled,
        failed=failed,
    )
    logger.info(
        "data_quality_monitors.completed",
        tenants=report.tenants,
        periods=report.periods,
        evaluated=report.evaluated,
        created=report.created,
        seen_again=report.seen_again,
        severity_changed=report.severity_changed,
        settled=report.settled,
        failed=report.failed,
    )
    return report
