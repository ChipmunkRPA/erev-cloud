"""RPT-17 ``late_entry_report`` Late-entry report (SCREENS_B §5.6.3 RPT-17 rev 1.25; 04 T-CON-05,
T-CLS-04, T-PLT-31 ``close.late_entry_window_days``; 03 REQ-CLS-007; research 07 PC-03, A-11;
BUILD_SPEC RPS-8).

The cutoff register of a period: the contract events (T-CON-05) of the contracts whose contracting
entity is an entity of the run, recorded by the run's cutoff, against the period ``period_key`` of
each entity's calendar (default: the period that holds the run's as-of date) and the run's book.

- Section 1 "Entered after lock": an event whose effective date lies in the period and whose
  ``recorded_at`` is after ``lock_recorded_at`` — the ``created_at`` of the earliest ``LOCK``
  record (T-CLS-04) of the entity, book and period by the cutoff. An entity whose period has no
  lock by then has no section 1 row.
- Section 2 "Near period end": an event whose effective date lies from ``window_days`` days
  before the period end to ``window_days`` days after it, both inclusive.

``days_from_period_end`` is the effective date less the period end date in days: negative before
the period end, 0 on it, positive after it. One dataset holds both sections; a row fills
``lock_recorded_at`` in section 1 only. An event that meets both rules has a row in each section
under the same ``row_key`` (``event:<external id>:<stream version>``, the external id CV-21
encoded as RPT-16's ``event_key``), so ``section`` and ``row_key`` together identify a row. Rows
are ordered by section, entity code, effective date, ``recorded_at``, contract and stream version.

``event_type`` is the E-03 code and ``event_type_label`` its label; ``origin``, ``recorded_by``
and ``approval_request_no`` are the event's own, read as RPT-16 reads them (``recorded_by`` names
the user or the API client that appended the event). An event an import commit wrote as the
``SYSTEM`` principal names its upload's uploader and the upload's approval request instead
(``event_provenance``; supervisor ruling R-63 (c)). ``window_days`` is the run's parameter, else
the registry value ``close.late_entry_window_days`` in force at the run's ``known_at``; a value
outside 0 to 31 is refused with the SCREENS_B copy. Control totals ``section_1_count``,
``section_2_count`` and the ``window_days`` applied. Tie-out: none.

T-CON-05 and T-CLS-04 are append-only, so the state at a cutoff is the rows recorded by it: an
explicit historical run never refuses. ``dataset_rows`` is pure over ``Event`` and ``Scope``
records; ``build`` reads them through the unit of work.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    api_client,
    app_user,
    approval_request,
    contract,
    contract_event,
    period_lock,
)
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, event_provenance
from erev_api.domain.reports.builders.out_of_period_register import event_key, event_type_label
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef
from erev_api.enums import LockKind, PrincipalKind
from erev_api.registry.resolve import setting
from erev_api.uow import UnitOfWork

CODE: Final = "late_entry_report"
WINDOW_DAYS: Final = "window_days"
WINDOW_SETTING: Final = "close.late_entry_window_days"  # T-PLT-31 (REQ-CLS-007)
WINDOW_RANGE: Final = (0, 31)
WINDOW_COPY: Final = "Enter a number of days from 0 to 31."  # SCREENS_B RPT-17
ENTERED_AFTER_LOCK: Final = 1
NEAR_PERIOD_END: Final = 2
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    Column("entity_code", "Entity", "code"),
    Column("event_key", "Event key", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("event_type", "Event", "code"),
    Column("effective_date", "Effective date", "date"),
    Column("recorded_at", "Recorded", "timestamp"),
    Column("days_from_period_end", "Days from period end", "integer"),
    Column("lock_recorded_at", "Lock recorded", "timestamp"),
    Column("origin", "Origin", "code"),
    Column("recorded_by", "Recorded by", "actor"),
    Column("approval_request_no", "Approval", "code"),
    Column("event_type_label", "Event label", "text"),
)


@dataclass(frozen=True, slots=True)
class Scope:
    """The period of one run entity and its first lock by the cutoff (None: not locked)."""

    entity_code: str
    period_start: date
    period_end: date
    lock_recorded_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Event:
    """One contract event of a run entity — the input of ``dataset_rows``."""

    entity_code: str
    contract_external_id: str
    stream_version: int
    event_type: str
    effective_date: date
    recorded_at: datetime
    origin: str
    recorded_by: Mapping[str, Any]
    approval_request_no: str | None = None


def window_days(value: object) -> int:
    """The window as an integer of 0 to 31 days, else 422 with the SCREENS_B copy. Pure."""
    low, high = WINDOW_RANGE
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise tie_outs.invalid(WINDOW_DAYS, WINDOW_COPY)
    return value


def entered_after_lock(event: Event, scope: Scope) -> bool:
    """Section 1: effective in the period and recorded after the period's first lock. Pure."""
    return (
        scope.lock_recorded_at is not None
        and scope.period_start <= event.effective_date <= scope.period_end
        and event.recorded_at > scope.lock_recorded_at
    )


def near_period_end(event: Event, scope: Scope, days: int) -> bool:
    """Section 2: effective within ``days`` days of the period end, either side. Pure."""
    return abs((event.effective_date - scope.period_end).days) <= days


def _row(event: Event, scope: Scope, section: int) -> dict[str, Any]:
    key = event_key(event.contract_external_id, event.stream_version)
    return {
        "row_key": key,
        "section": section,
        "entity_code": event.entity_code,
        "event_key": key,
        "contract_external_id": event.contract_external_id,
        "event_type": event.event_type,
        "effective_date": event.effective_date,
        "recorded_at": event.recorded_at,
        "days_from_period_end": (event.effective_date - scope.period_end).days,
        "lock_recorded_at": scope.lock_recorded_at if section == ENTERED_AFTER_LOCK else None,
        "origin": event.origin,
        "recorded_by": dict(event.recorded_by),
        "approval_request_no": event.approval_request_no,
        "event_type_label": event_type_label(event.event_type),
    }


def dataset_rows(
    events: Iterable[Event], scopes: Mapping[str, Scope], *, days: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows of sections 1 and 2, control totals) of ``events`` against the period of each
    event's entity (``scopes`` by entity code); an event of an entity without a scope is outside
    the run and is not listed. Pure."""
    ordered = sorted(
        events,
        key=lambda item: (
            item.entity_code,
            item.effective_date,
            item.recorded_at,
            item.contract_external_id,
            item.stream_version,
        ),
    )
    late: list[dict[str, Any]] = []
    near: list[dict[str, Any]] = []
    for event in ordered:
        scope = scopes.get(event.entity_code)
        if scope is None:
            continue
        if entered_after_lock(event, scope):
            late.append(_row(event, scope, ENTERED_AFTER_LOCK))
        if near_period_end(event, scope, days):
            near.append(_row(event, scope, NEAR_PERIOD_END))
    totals = {"section_1_count": len(late), "section_2_count": len(near), WINDOW_DAYS: days}
    return late + near, totals


def window_of(session: Session, params: ReportParams) -> int:
    """``window_days`` of the run, else the registry value in force at the run's ``known_at``
    (SCREENS_B RPT-17 default)."""
    given = params.parameters.get(WINDOW_DAYS)
    if given is None:
        given = setting(session, WINDOW_SETTING, known_at=params.known_at)
    return window_days(given)


def first_locks(
    session: Session,
    *,
    book_code: str,
    periods: Mapping[UUID, PeriodRef],
    cutoff: datetime,
) -> dict[UUID, datetime]:
    """Per entity: the ``created_at`` of the earliest ``LOCK`` record of its period and the run's
    book by the cutoff; an entity whose period holds none is absent."""
    pairs = [
        and_(period_lock.c.entity_id == entity_id, period_lock.c.period_id == item.id)
        for entity_id, item in sorted(periods.items(), key=lambda pair: str(pair[0]))
    ]
    if not pairs:
        return {}
    rows = session.execute(
        select(period_lock.c.entity_id, func.min(period_lock.c.created_at).label("locked_at"))
        .where(
            period_lock.c.kind == LockKind.LOCK.value,
            period_lock.c.book_code == book_code,
            period_lock.c.created_at <= cutoff,
            or_(*pairs),
        )
        .group_by(period_lock.c.entity_id)
    ).mappings()
    return {UUID(str(row["entity_id"])): row["locked_at"] for row in rows}


def _names(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[UUID, str]:
    """The names of the principals that appended ``rows``: an API client's name, else the
    person's display name."""
    clients: set[UUID] = set()
    people: set[UUID] = set()
    for row in rows:
        if row["created_by"] is None:
            continue
        kind = str(getattr(row["created_by_kind"], "value", row["created_by_kind"]))
        (clients if kind == PrincipalKind.API_CLIENT.value else people).add(
            UUID(str(row["created_by"]))
        )
    names: dict[UUID, str] = {}
    if people:
        found = session.execute(
            select(app_user.c.id, app_user.c.display_name).where(app_user.c.id.in_(sorted(people)))
        ).tuples()
        names |= {UUID(str(user_id)): str(name) for user_id, name in found}
    if clients:
        found = session.execute(
            select(api_client.c.id, api_client.c.name).where(api_client.c.id.in_(sorted(clients)))
        ).tuples()
        names |= {UUID(str(client_id)): str(name) for client_id, name in found}
    return names


def sources(
    session: Session,
    *,
    entities: Sequence[EntityRef],
    periods: Mapping[UUID, PeriodRef],
    days: int,
    cutoff: datetime,
) -> list[Event]:
    """The events of the run's entities recorded by the cutoff whose effective date lies in the
    entity's period or within ``days`` days of its end — the population either section draws on.
    An event belongs to the entity of its contract (T-CON-05 ``contracting_entity_id``)."""
    codes = {entity.id: entity.code for entity in entities}
    ranges = [
        and_(
            contract_event.c.contracting_entity_id == entity_id,
            contract_event.c.effective_date >= min(item.start, item.end - timedelta(days=days)),
            contract_event.c.effective_date <= item.end + timedelta(days=days),
        )
        for entity_id, item in sorted(periods.items(), key=lambda pair: str(pair[0]))
    ]
    tenant_id = contract_event.c.tenant_id
    statement = (
        select(
            contract_event.c.contracting_entity_id,
            contract.c.external_id,
            contract_event.c.stream_version,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.recorded_at,
            contract_event.c.origin,
            contract_event.c.created_by,
            contract_event.c.created_by_kind,
            contract_event.c.import_upload_id,
            approval_request.c.request_no.label(event_provenance.APPROVAL),
        )
        .select_from(
            contract_event.join(
                contract,
                and_(
                    contract.c.tenant_id == tenant_id, contract.c.id == contract_event.c.contract_id
                ),
            ).outerjoin(
                approval_request,
                and_(
                    approval_request.c.tenant_id == tenant_id,
                    approval_request.c.id == contract_event.c.approval_request_id,
                ),
            )
        )
        .where(contract_event.c.recorded_at <= cutoff, or_(*ranges) if ranges else false())
        .order_by(contract_event.c.contract_id, contract_event.c.stream_version)
    )
    # R-63 (c): an event an import commit wrote names its upload's uploader and approval
    rows = event_provenance.attributed(
        session, [dict(row) for row in session.execute(statement).mappings()]
    )
    names = _names(session, rows)
    return [
        Event(
            entity_code=codes[UUID(str(row["contracting_entity_id"]))],
            contract_external_id=str(row["external_id"]),
            stream_version=int(row["stream_version"]),
            event_type=str(getattr(row["event_type"], "value", row["event_type"])),
            effective_date=row["effective_date"],
            recorded_at=row["recorded_at"],
            origin=str(row["origin"]),
            recorded_by=approval_queries.actor(
                None if row["created_by"] is None else UUID(str(row["created_by"])),
                str(getattr(row["created_by_kind"], "value", row["created_by_kind"])),
                names,
            ),
            approval_request_no=(
                None
                if row[event_provenance.APPROVAL] is None
                else str(row[event_provenance.APPROVAL])
            ),
        )
        for row in rows
    ]


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    days = window_of(session, params)
    found = tie_outs.entities(session, params.entity_ids)
    calendars = tie_outs.calendars(session, found)
    periods = {
        entity.id: tie_outs.period_of(params, calendars[entity.id], entity) for entity in found
    }
    cutoff = tie_outs.cutoff_for(session, params)
    locks = first_locks(session, book_code=book_code, periods=periods, cutoff=cutoff)
    scopes = {
        entity.code: Scope(
            entity_code=entity.code,
            period_start=periods[entity.id].start,
            period_end=periods[entity.id].end,
            lock_recorded_at=locks.get(entity.id),
        )
        for entity in found
    }
    events = sources(session, entities=found, periods=periods, days=days, cutoff=cutoff)
    rows, totals = dataset_rows(events, scopes, days=days)
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "WINDOW_COPY",
    "WINDOW_SETTING",
    "Event",
    "Scope",
    "build",
    "dataset_rows",
    "entered_after_lock",
    "first_locks",
    "near_period_end",
    "sources",
    "window_days",
    "window_of",
]
