"""Historical billing-document routing, shared by reconciliation reads and freshness.

A document received after its origin period closed belongs to the first later period
open at receipt. Later locks/reopens must not move an already received document.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select
from sqlalchemy.sql import ColumnElement

from erev_api.db.tables import period, period_lock, source_invoice

if TYPE_CHECKING:
    from .gates import PeriodScope


def routing(
    scope: "PeriodScope", table: Any, day: ColumnElement[Any], received: ColumnElement[Any]
) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    origin = period.alias("billing_origin")
    candidate = period.alias("billing_destination")
    scope_period = period.alias("billing_scope")
    calendar = (
        select(scope_period.c.calendar_id)
        .where(scope_period.c.id == scope.period_id)
        .scalar_subquery()
    )

    def locked(at: Any) -> ColumnElement[bool]:
        history = period_lock.alias("billing_lock_history")
        last = (
            select(history.c.kind)
            .where(
                history.c.tenant_id == table.c.tenant_id,
                history.c.entity_id == scope.entity_id,
                history.c.book_code == scope.book_code,
                history.c.period_id == at.c.id,
                history.c.created_at < received,
            )
            .order_by(history.c.created_at.desc(), history.c.id.desc())
            .limit(1)
            .correlate(at, table)
            .scalar_subquery()
        )
        return func.coalesce(last.in_(("LOCK", "PERMANENT_LOCK")), False)

    destination = (
        select(candidate.c.id)
        .where(
            candidate.c.tenant_id == table.c.tenant_id,
            candidate.c.calendar_id == origin.c.calendar_id,
            candidate.c.start_date > origin.c.end_date,
            ~locked(candidate),
        )
        .order_by(candidate.c.start_date, candidate.c.id)
        .limit(1)
        .correlate(origin, table)
        .scalar_subquery()
    )
    conditions = (
        origin.c.tenant_id == table.c.tenant_id,
        origin.c.calendar_id == calendar,
        origin.c.start_date <= day,
        origin.c.end_date >= day,
    )
    origin_id = select(origin.c.id).where(*conditions).correlate(table).scalar_subquery()
    target = (
        select(case((locked(origin), destination), else_=origin.c.id))
        .where(*conditions)
        .correlate(table)
        .scalar_subquery()
    )
    return origin_id, target


def source_received() -> ColumnElement[Any]:
    """A status/version refresh does not turn an existing invoice into a new receipt."""
    versions = source_invoice.alias("billing_source_versions")
    return (
        select(func.min(versions.c.created_at))
        .where(
            versions.c.tenant_id == source_invoice.c.tenant_id,
            versions.c.source_system == source_invoice.c.source_system,
            versions.c.external_invoice_id == source_invoice.c.external_invoice_id,
        )
        .correlate(source_invoice)
        .scalar_subquery()
    )
