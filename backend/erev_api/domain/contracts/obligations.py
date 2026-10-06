"""API-R-29 obligation reads (04 §15.3 API-R-29, §16.2 API-S-Obligation, API-S-ScheduleLine, §16.3
API-S-Event; API-C-09 to API-C-11; BUILD_SPEC CTR-15).

An obligation is visible when its contract is (RLS-TE on the contracting entity), otherwise 404
``not-found``. ``obligation_out`` answers the obligation's version in the group's latest version of
the book recorded by ``known_at`` (``queries.version_at``), 404 while none exists; its to-date
members, and those of ``contract_obligations``, are served at the cut of ``as_of`` (04 API-C-10 rev
1.132; ``queries.obligations_at``). ``versions_statement`` lists every obligation version of the
book, one per contract version, each in the context of its own version and as stored.
``schedule_statement`` keeps the contract's schedule lines at the version in context whose subject
is the obligation. ``events_statement`` lists the stream events whose ``obligation_ids`` or payload
``obligation_key`` name the obligation, recorded by ``known_at``. [J] L4-2-Q-7: an event appended
without ``obligation_keys`` names its obligation only in the payload (``DELIVERY_RECORDED``), so
both count; obligation keys inside payload arrays (billing lines) are not searched.

``event_items`` answers each of them as API-S-Event WHOLE (04 rev 1.273; the supervisor's ruling of
2026-10-02): the events resource's model, built by its builder (``events.event_outs``). Until then
this module built a model of its own, which had fallen behind — measured on the route the Events
panel reads: an applied manual event named neither its preparer nor its approver (PRD J-08-AC-3;
control CTL-009), and an imported event never its source row.

[J] L4-2-Q-7: ``material_right_out`` answers 404, because T-CON-14 ``material_right`` moved
post-rc with CTR-14 (R-RC-1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from erev_api.clock import to_entity_date
from erev_api.db.tables import (
    contract_event,
    legal_entity,
    obligation,
    obligation_version,
    schedule_line,
)
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.contracts import queries, repo, to_date
from erev_api.enums import BookCode
from erev_api.problems import Problem
from erev_api.schemas.common import ContextOut
from erev_api.schemas.contracts import ObligationOut
from erev_api.schemas.events import EventOut
from erev_api.schemas.obligations import MaterialRightOut

SUBJECT_TYPE: Final = "obligation"  # schedule_line.subject_type of an obligation's lines
NO_VERSION: Final = "The obligation has no computed version in this book yet."
NO_MATERIAL_RIGHT: Final = "The obligation has no material right."


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _literal(value: Any) -> str:
    return str(getattr(value, "value", value))


def obligation_row(session: Session, obligation_id: UUID) -> dict[str, Any]:
    """The obligation with its visible contract (member ``contract``); 404 ``not-found``."""
    found = (
        session.execute(select(obligation).where(obligation.c.id == obligation_id))
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    return {**dict(found), "contract": repo.get_contract(session, _uuid(found["contract_id"]))}


def _context(
    session: Session,
    contract_row: Mapping[str, Any],
    version: Mapping[str, Any],
    *,
    params: queries.ReadParams,
    now: datetime,
) -> ContextOut:
    zone = session.execute(
        select(legal_entity.c.time_zone).where(
            legal_entity.c.id == contract_row["contracting_entity_id"]
        )
    ).scalar_one()
    return ContextOut(
        book=BookCode(_literal(version["book_code"])),
        as_of=params.as_of or to_entity_date(now, str(zone)),
        known_at=params.known_at or now,
        contract_version_id=version["id"],
        version_no=version["version_no"],
        computed_at=version["computed_at"],
    )


def _version(
    session: Session, contract_row: Mapping[str, Any], params: queries.ReadParams
) -> dict[str, Any] | None:
    return queries.version_at(
        session,
        contract_row,
        book_code=params.book or queries.primary_book(session),
        known_at=params.known_at,
    )


def obligation_out(
    session: Session, obligation_id: UUID, *, params: queries.ReadParams, now: datetime
) -> ObligationOut:
    """API-S-Obligation at the version in context, its to-date members at the cut of ``as_of``;
    404 while the book has no version."""
    contract_row, version, row = _at_version(session, obligation_id, params)
    context = _context(session, contract_row, version, params=params, now=now)
    at = queries.obligations_at(session, contract_row, version, [row], as_of=context.as_of)
    (out,) = queries.obligation_outs(session, version, [row], context=context, at=at)
    return out


def _at_version(
    session: Session, obligation_id: UUID, params: queries.ReadParams
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The obligation's visible contract, the version in context and the obligation's version in
    it; 404 while the book has no version."""
    contract_row = obligation_row(session, obligation_id)["contract"]
    version = _version(session, contract_row, params)
    row = None
    if version is not None:
        row = (
            session.execute(
                select(obligation_version).where(
                    obligation_version.c.contract_version_id == version["id"],
                    obligation_version.c.obligation_id == obligation_id,
                )
            )
            .mappings()
            .one_or_none()
        )
    if version is None or row is None:
        raise Problem("not-found", NO_VERSION)
    return contract_row, version, dict(row)


def measured_period(
    session: Session,
    obligation_id: UUID,
    measure: str,
    *,
    params: queries.ReadParams,
    now: datetime,
) -> to_date.Measured | None:
    """The period whose node holds the obligation's to-date ``measure`` (``revenue_cum``,
    ``billed_cum`` or ``progress_ratio``) at the cut of ``as_of`` in the version in context — what
    ``obligation_out`` serves, so an Explain of the figure names the same node (04 §16.11 rev
    1.132). None before the first period the version measures; 404 while the book has no version."""
    contract_row, version, row = _at_version(session, obligation_id, params)
    context = _context(session, contract_row, version, params=params, now=now)
    at = queries.obligations_at(session, contract_row, version, [row], as_of=context.as_of)
    found = at[_uuid(row["id"])]
    return found.billed_measured if measure == to_date.BILLED else found.measured


def contract_obligations(
    session: Session, contract_id: UUID, *, params: queries.ReadParams, now: datetime
) -> list[ObligationOut]:
    """API-S-Obligation of every obligation of the contract at the version in context, in line
    order, their to-date members at the cut of ``as_of``; empty while the book has no version."""
    contract_row = repo.get_contract(session, contract_id)
    version = _version(session, contract_row, params)
    if version is None:
        return []
    statement = (
        select(obligation_version)
        .select_from(
            obligation_version.join(
                obligation,
                and_(
                    obligation.c.tenant_id == obligation_version.c.tenant_id,
                    obligation.c.id == obligation_version.c.obligation_id,
                ),
            )
        )
        .where(
            obligation_version.c.contract_version_id == version["id"],
            obligation_version.c.contract_id == contract_id,
        )
        .order_by(obligation.c.line_sequence, obligation_version.c.obligation_key)
    )
    rows = [dict(row) for row in session.execute(statement).mappings()]
    context = _context(session, contract_row, version, params=params, now=now)
    at = queries.obligations_at(session, contract_row, version, rows, as_of=context.as_of)
    return queries.obligation_outs(session, version, rows, context=context, at=at)


def versions_statement(session: Session, obligation_id: UUID, *, book: str | None) -> Select[Any]:
    """The obligation versions of the book (default the primary book), one per contract version."""
    obligation_row(session, obligation_id)
    return select(obligation_version).where(
        obligation_version.c.obligation_id == obligation_id,
        obligation_version.c.book_code == (book or queries.primary_book(session)),
    )


def version_items(
    session: Session, obligation_id: UUID, rows: Sequence[Mapping[str, Any]], *, now: datetime
) -> list[ObligationOut]:
    """API-S-Obligation of each row in the context of its own contract version (its ``known_at``;
    ``as_of`` today in the contracting entity's time zone), as the version stores it (04 API-C-10
    rev 1.132: the version reads are not moved to a cut)."""
    if not rows:
        return []
    contract_row = obligation_row(session, obligation_id)["contract"]
    versions = queries.versions_by_id(session, (row["contract_version_id"] for row in rows))
    items: list[ObligationOut] = []
    for row in rows:
        version = versions[_uuid(row["contract_version_id"])]
        params = queries.ReadParams(
            book=_literal(version["book_code"]), known_at=version["known_at"]
        )
        context = _context(session, contract_row, version, params=params, now=now)
        items.extend(queries.obligation_outs(session, version, [dict(row)], context=context))
    return items


def schedule_statement(
    session: Session, obligation_id: UUID, *, params: queries.ReadParams
) -> Select[Any]:
    """API-S-ScheduleLine rows of the obligation at the version in context (``queries``)."""
    found = obligation_row(session, obligation_id)
    return queries.schedule_statement(session, _uuid(found["contract_id"]), params=params).where(
        schedule_line.c.subject_type == SUBJECT_TYPE, schedule_line.c.subject_id == obligation_id
    )


def events_statement(
    session: Session, obligation_id: UUID, *, known_at: datetime | None
) -> Select[Any]:
    """The contract's stream events naming the obligation, recorded by ``known_at``."""
    found = obligation_row(session, obligation_id)
    statement = select(contract_event).where(
        contract_event.c.contract_id == found["contract_id"],
        or_(
            contract_event.c.obligation_ids.contains([obligation_id]),
            contract_event.c.payload["obligation_key"].astext == str(found["obligation_key"]),
        ),
    )
    if known_at is not None:
        statement = statement.where(contract_event.c.recorded_at <= known_at)
    return statement


def _named_keys(row: Mapping[str, Any], keys: Mapping[UUID, str]) -> list[str]:
    """The obligation keys an event names: its ``obligation_ids``, then the payload's key."""
    named = [keys[_uuid(value)] for value in row["obligation_ids"] or () if _uuid(value) in keys]
    payload = row["payload"]
    key = payload.get("obligation_key") if isinstance(payload, Mapping) else None
    if isinstance(key, str) and key in keys.values() and key not in named:
        named.append(key)
    return named


def event_items(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[EventOut]:
    """API-S-Event of each stream row, as every read of an event answers it: the events
    resource's model, built by its builder (``events.event_outs``; 04 API-S-Event rev 1.273) —
    the people of the request the event names, its source row, the computation that first
    included it and ``void_refusal``; a member API-S-Event gains is answered here with it.

    One member keeps this route's own rule: ``obligation_keys`` also holds the key an event names
    only in its payload, by which ``events_statement`` found it ([J] L4-2-Q-7), so that every
    listed event names the obligation it is listed under."""
    if not rows:
        return []
    contract_ids = sorted({_uuid(row["contract_id"]) for row in rows})
    keys = {
        _uuid(found.id): str(found.obligation_key)
        for found in session.execute(
            select(obligation.c.id, obligation.c.obligation_key).where(
                obligation.c.contract_id.in_(contract_ids)
            )
        )
    }
    return [
        item.model_copy(update={"obligation_keys": _named_keys(row, keys)})
        for item, row in zip(contract_events.event_outs(session, rows), rows, strict=True)
    ]


def material_right_out(session: Session, obligation_id: UUID) -> MaterialRightOut:
    """The obligation's material right; 404 while T-CON-14 does not exist (L4-2-Q-7)."""
    obligation_row(session, obligation_id)
    raise Problem("not-found", NO_MATERIAL_RIGHT)
