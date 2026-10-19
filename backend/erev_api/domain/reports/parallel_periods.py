"""RPT-42 period defaults: first after cutover through the latest open period."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Row

from erev_api.db.tables import period_state_transition
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.parallel_comparison import Period
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def select_periods(
    calendar: tie_outs.Calendar,
    *,
    entity_code: str,
    currency: str,
    cutover: date,
    open_period_ids: frozenset[UUID],
    first_key: str | None,
    last_key: str | None,
) -> tuple[Period, ...]:
    eligible = tuple(item for item in calendar.periods if item.start > cutover)
    first = (
        calendar.named(first_key, "from_period_key")
        if first_key is not None
        else (eligible[0] if eligible else None)
    )
    opened = tuple(item for item in eligible if item.id in open_period_ids)
    last = (
        calendar.named(last_key, "to_period_key")
        if last_key is not None
        else (opened[-1] if opened else None)
    )
    if any(item is not None and item.start <= cutover for item in (first, last)):
        raise Problem("validation-failed", "Choose comparison periods after the migration cutover.")
    if first is None or last is None:
        return ()
    if first.start > last.start:
        raise Problem("validation-failed", "The comparison start period is after the end period.")
    return tuple(
        Period(entity_code, "ASC606", currency, item.key, item.start, item.end)
        for item in calendar.between(first, last)
    )


def resolve(
    uow: UnitOfWork, params: ReportParams, *, migration_evidence: dict[str, Any]
) -> tuple[Period, ...]:
    """Called only after authorized source admission; current config is retained by capture."""
    try:
        cutover = date.fromisoformat(migration_evidence["cutover_date"])
        currency = str(migration_evidence["reporting_currency"])
    except (KeyError, TypeError, ValueError) as error:
        raise Problem(
            "validation-failed", "The migration has no bound cutover and currency."
        ) from error
    entities = tie_outs.entities(uow.session, params.entity_ids)
    calendars = tie_outs.calendars(uow.session, entities)
    t = period_state_transition.c
    states = uow.session.execute(
        select(t.entity_id, t.period_id, t.to_state, t.created_at, t.created_txid)
        .where(
            t.entity_id.in_(params.entity_ids),
            t.book_code == "ASC606",
            t.created_at <= params.known_at,
        )
        .order_by(t.entity_id, t.period_id, t.created_at.desc(), t.created_txid.desc(), t.id)
    ).all()
    latest: dict[tuple[UUID, UUID], Row[Any]] = {}
    for row in states:
        key = row.entity_id, row.period_id
        previous = latest.get(key)
        if (
            previous is not None
            and (previous.created_at, previous.created_txid) == (row.created_at, row.created_txid)
            and previous.to_state != row.to_state
        ):
            raise Problem("validation-failed", "Period state ordering is ambiguous at this cutoff.")
        if previous is None:
            latest[key] = row
    result: list[Period] = []
    for entity in entities:
        result.extend(
            select_periods(
                calendars[entity.id],
                entity_code=entity.code,
                currency=currency,
                cutover=cutover,
                open_period_ids=frozenset(
                    period_id
                    for (entity_id, period_id), state in latest.items()
                    if entity_id == entity.id and state.to_state == "open"
                ),
                first_key=params.parameters.get("from_period_key"),
                last_key=params.parameters.get("to_period_key"),
            )
        )
    return tuple(result)
