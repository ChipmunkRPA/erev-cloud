"""Audit log reads and on-demand chain verification (04 §15.3 API-R-10, T-PLT-19, T-PLT-23;
SCREENS_B §6.3 SF-09:audit-log, §6.4 SF-09:verification; REQ-PLT-019, REQ-PLT-020; BUILD_SPEC
PLF-23).

The routes require ``audit.read``. ``request_verification`` defers an ``ON_DEMAND``
``AUDIT_CHAIN_VERIFY`` job and answers API-S-Job. Like every job request it writes no audit event
(T-PLT-27 AUD-OPS); the verification row the job inserts is audited (T-PLT-23 AUD-FACT).

Item AUD-API-GAPS-1 (04 §16.14 "Audit events", rev 1.154; supervisor ruling R-108):

- the events of one contract are read by the contract key of T-PLT-19 — ``detail.contract_id``
  or a member of ``detail.contract_ids`` — through ``audit_event_contract`` (T-PLT-48), which
  holds the key as plain columns: under the table's row-level-security policy an index serves
  only leakproof conditions, and the ``jsonb`` operators are not (``trail_source``);
- a read always has a start (``window_start``), except by contract or by chain sequence, which an
  index answers at any age; and it has an end (``window_end``; rev 1.280, item
  AUDIT-LIST-PLAN-1), so that PostgreSQL plans the months of the range and not every monthly
  partition after its start;
- an event is read with the label of its object (``audit_labels``) and with its actor's membership
  id, in its own statement;
- ``actors_in_range`` answers who acted in a range, so that the log's own readers can filter on a
  person without the workspace's user list.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, case, null, select, true
from sqlalchemy.orm import Session

from erev_api.audit import verify
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    audit_chain_verification,
    audit_event,
    audit_event_contract,
    tenant_membership,
)
from erev_api.domain.platform import actors, audit_labels, jobs
from erev_api.enums import JobKind, MembershipStatus, PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.audit import AuditActorsOut, AuditChainVerificationOut, AuditEventOut
from erev_api.schemas.common import ActorOut, JobOut

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

EVENT_COLUMNS: Final = tuple(column for column in audit_event.c if column.name != "tenant_id")
# The ``actors.named`` values ``event_select`` reads with each event (dev-guide DG-API-11).
ACTOR_NAMED: Final = "actor__named"
ON_BEHALF_OF_NAMED: Final = "on_behalf_of__named"
# Columns an event shows as API-S-Actor members, not as they are stored.
_AS_ACTORS: Final = frozenset(
    {"actor_id", "actor_kind", "on_behalf_of_id", ACTOR_NAMED, ON_BEHALF_OF_NAMED}
)
OBJECT_LABEL: Final = "object_label"
ACTOR_MEMBERSHIP_ID: Final = "actor_membership_id"
# 04 §16.14: a read without ``from`` starts this long before its end.
DEFAULT_WINDOW: Final = timedelta(days=30)
# 04 §16.14 rev 1.280: a read without ``to`` ends this long after the request. An event carries
# the instant of the unit of work that wrote it, and none lies after a reader's request by more
# than the clocks of two processes differ: the day removes no row, and it lets the planner leave
# the months ahead out.
END_MARGIN: Final = timedelta(days=1)
# ``GET /audit-events/actors`` answers at most this many; ``is_truncated`` says there are more.
ACTOR_LIMIT: Final = 100


def window_start(now: datetime, *, since: datetime | None, until: datetime | None) -> datetime:
    """Where a read of the log starts: ``from`` when the caller sent it, else thirty days before
    ``to``, else thirty days before the request."""
    if since is not None:
        return since
    return (now if until is None else until) - DEFAULT_WINDOW


def window_end(now: datetime, *, until: datetime | None) -> datetime:
    """Where a read of the log ends, exclusive: ``to`` when the caller sent it, else one day after
    the request (04 §16.14 rev 1.280; item AUDIT-LIST-PLAN-1). ``audit_event`` is partitioned by
    month on ``occurred_at``; without an end a read planned every partition from its start to the
    last one created - 77 of 181 for the last thirty days, measured on 2026-10-02 - where it now
    plans the months of its range."""
    return now + END_MARGIN if until is None else until


VERIFICATION_COLUMNS: Final = tuple(
    column
    for column in audit_chain_verification.c
    if column.name not in {"tenant_id", "created_at", "created_by", "created_by_kind"}
)


@dataclass(frozen=True, slots=True)
class EventSource:
    """A read of the log before the list parameters: its statement, and for every T-PLT-19 column
    the expression the list kernel sorts and filters by (the route binds its ``ListSpec`` to
    these). For the log as a whole they are the table's columns; for the trail of a contract the
    sequence, the instant and the id are the link's, which the link's key holds in order."""

    statement: Select[Any]
    columns: Mapping[str, ColumnElement[Any]]


def _actor_membership(columns: Mapping[str, ColumnElement[Any]]) -> ColumnElement[Any]:
    """The membership of the person who acted, in the event's workspace: the key of the user
    screen (SCREENS RT-108). Null for an API client, an operator and the system, and for a member
    who has been removed."""
    found = (
        select(tenant_membership.c.id)
        .where(
            tenant_membership.c.tenant_id == columns["tenant_id"],
            tenant_membership.c.user_id == columns["actor_id"],
            tenant_membership.c.status != MembershipStatus.REMOVED.value,
        )
        .correlate_except(tenant_membership)
        .scalar_subquery()
    )
    return case((columns["actor_kind"] == PrincipalKind.USER.value, found), else_=null())


def _select(columns: Mapping[str, ColumnElement[Any]]) -> Select[Any]:
    """The T-PLT-19 rows ``event_outs`` takes, read from ``columns``: every column but
    ``tenant_id``, with who acted and on whose behalf, the actor's membership and the label of the
    object — each a lookup of the same statement."""
    tenant_id = columns["tenant_id"]
    return select(
        *(columns[column.name] for column in EVENT_COLUMNS),
        actors.named(columns["actor_id"], tenant_id=tenant_id).label(ACTOR_NAMED),
        actors.named(columns["on_behalf_of_id"], tenant_id=tenant_id).label(ON_BEHALF_OF_NAMED),
        _actor_membership(columns).label(ACTOR_MEMBERSHIP_ID),
        audit_labels.label(columns["object_type"], columns["object_id"], tenant_id).label(
            OBJECT_LABEL
        ),
    )


# The log as a whole is sorted and filtered by the table's own columns.
_TABLE_COLUMNS: Final[Mapping[str, ColumnElement[Any]]] = MappingProxyType(
    {column.name: column for column in audit_event.c}
)


def event_select() -> Select[Any]:
    """Every event of the log, as ``event_outs`` takes them."""
    return _select(_TABLE_COLUMNS)


def trail_source(contract_id: UUID) -> EventSource:
    """The events that name ``contract_id`` — it is their contract, or one of their contracts —
    read through T-PLT-48: the link's rows of the contract, and for each the one event it names,
    looked up by the event's own key (``LATERAL … LIMIT 1``).

    The shape is deliberate. Every condition compares ``uuid`` or ``timestamptz`` columns, which
    an index may take under the tables' row-level-security policy (a ``jsonb`` operator may not).
    And the lookup is LATERAL with a limit, so the link always drives it: joined plainly, the
    planner prices one probe of ``audit_event`` at a probe of every monthly partition — it cannot
    know that ``occurred_at`` leaves one — and above a few hundred events it would rather read the
    whole log of the tenant (``tests/pg/test_audit_log_plans.py`` reads the plan)."""
    link = audit_event_contract
    event = audit_event.alias("event")
    trail = (
        select(event)
        .where(
            event.c.tenant_id == link.c.tenant_id,
            event.c.occurred_at == link.c.occurred_at,
            event.c.id == link.c.audit_event_id,
        )
        .limit(1)
        .lateral("trail")
    )
    columns: dict[str, ColumnElement[Any]] = {
        column.name: trail.c[column.name] for column in audit_event.c
    }
    # The link holds the sequence, the instant and the id of its event: a cursor, a sort and a
    # range on them are answered before the event is looked up, and the order of a page is the
    # order of the link's key — neither sort column can be NULL, so the key read backwards
    # supplies it and the read stops at the page (DG-LST-08).
    columns["chain_seq"] = link.c.chain_seq
    columns["occurred_at"] = link.c.occurred_at
    columns["id"] = link.c.audit_event_id.label("id")
    statement = (
        _select(columns)
        .select_from(link.join(trail, true()))
        .where(link.c.contract_id == contract_id)
    )
    return EventSource(statement=statement, columns=MappingProxyType(columns))


def event_source(
    now: datetime,
    *,
    contract_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    by_sequence: bool = False,
) -> EventSource:
    """The read of ``GET /audit-events`` under the filters the resource applies itself (04
    §16.14): the contract, and the start and the end of the range where the caller sent none
    (the end since rev 1.280). A read by contract or by chain sequence (``by_sequence``) has no
    start and no end of its own: the trail of a contract is read whole, and a sequence is one
    event of any age; ``from`` and ``to`` still narrow either when sent — the list kernel
    applies those two."""
    if contract_id is not None:
        return trail_source(contract_id)
    statement = event_select()
    if not by_sequence:
        if since is None:
            start = window_start(now, since=since, until=until)
            statement = statement.where(audit_event.c.occurred_at >= start)
        if until is None:
            statement = statement.where(audit_event.c.occurred_at < window_end(now, until=until))
    return EventSource(statement=statement, columns=_TABLE_COLUMNS)


def list_events[T](
    ctx: RequestContext, source: EventSource, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """One page of the tenant's audit events; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, source.statement)


def event_outs(rows: Sequence[Mapping[str, Any]]) -> list[AuditEventOut]:
    """API-S-AuditEvent of each ``event_select`` row. ``on_behalf_of`` is the principal a system
    step acted for (``audit_event.on_behalf_of_id``: the creator of the job, a user or an API
    client), null when the event names none; the column stores no kind, so the Actor's kind is the
    one the identity tables give."""
    return [
        AuditEventOut.model_validate(
            {
                **{name: value for name, value in row.items() if name not in _AS_ACTORS},
                "source_ip": None if row["source_ip"] is None else str(row["source_ip"]),
                "actor": actors.actor(row["actor_id"], row["actor_kind"], row[ACTOR_NAMED]),
                "on_behalf_of": None
                if row["on_behalf_of_id"] is None
                else actors.actor(row["on_behalf_of_id"], None, row[ON_BEHALF_OF_NAMED]),
            }
        )
        for row in rows
    ]


def actors_statement(
    start: datetime, *, until: datetime | None, q: str | None, limit: int
) -> Select[Any]:
    """The principals with an id that acted from ``start`` (to ``until``), by name: ``limit`` rows.

    Who acted is read from ``ix_audit_event__actor`` one actor at a time — the first id of the
    range, then the first id above it, and so on — so the read costs one index probe per actor and
    month, not one per event (PostgreSQL has no skip scan of its own for ``DISTINCT``). The name
    and the kind are what the identity tables say now, as API-S-Actor reads them."""
    first = audit_event.alias("first")

    def in_range(event: Any) -> list[ColumnElement[bool]]:
        bounds = [event.c.occurred_at >= start]
        if until is not None:
            bounds.append(event.c.occurred_at < until)
        return bounds

    seed = (
        select(first.c.tenant_id, first.c.actor_id)
        .where(first.c.actor_id.is_not(None), *in_range(first))
        .order_by(first.c.actor_id)
        .limit(1)
        .subquery("seed")
    )
    found = select(seed.c.tenant_id, seed.c.actor_id).cte("found", recursive=True)
    previous = found.alias("previous")
    following_event = audit_event.alias("following_event")
    following = (
        select(following_event.c.tenant_id, following_event.c.actor_id)
        .where(following_event.c.actor_id > previous.c.actor_id, *in_range(following_event))
        .order_by(following_event.c.actor_id)
        .limit(1)
        .lateral("following")
    )
    found = found.union_all(
        select(following.c.tenant_id, following.c.actor_id).select_from(
            previous.join(following, true())
        )
    )
    listed = select(
        found.c.actor_id.label("id"),
        actors.named(found.c.actor_id, tenant_id=found.c.tenant_id).label("named"),
    ).subquery("listed")
    name = listed.c.named[actors.DISPLAY_NAME].astext
    statement = select(listed.c.id, listed.c.named)
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        statement = statement.where(name.ilike(pattern, escape="\\"))
    return statement.order_by(name.asc().nulls_last(), listed.c.id).limit(limit)


def actors_in_range(
    ctx: RequestContext, *, since: datetime | None, until: datetime | None, q: str | None
) -> AuditActorsOut:
    """``GET /audit-events/actors``: who acted in the range, for the log's actor filter. The range
    starts and ends as a read of the log does (``window_start``, ``window_end``). The system has
    no id and is not answered: ``actor_id`` cannot name it."""
    start = window_start(ctx.now, since=since, until=until)
    end = window_end(ctx.now, until=until)
    statement = actors_statement(start, until=end, q=q, limit=ACTOR_LIMIT + 1)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        rows = session.execute(statement).mappings().all()
    return AuditActorsOut(
        items=[
            ActorOut.model_validate(actors.actor(row["id"], None, row["named"]))
            for row in rows[:ACTOR_LIMIT]
        ],
        is_truncated=len(rows) > ACTOR_LIMIT,
    )


def list_verifications[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the tenant's chain verifications."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*VERIFICATION_COLUMNS))


def verification_outs(rows: Sequence[Mapping[str, Any]]) -> list[AuditChainVerificationOut]:
    return [AuditChainVerificationOut.model_validate(dict(row)) for row in rows]


def get_verification(ctx: RequestContext, verification_id: UUID) -> AuditChainVerificationOut:
    """``GET /audit-events/verifications/{id}``: one chain verification; 404 for another id."""
    statement = select(*VERIFICATION_COLUMNS).where(
        audit_chain_verification.c.id == verification_id
    )
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    (found,) = verification_outs([dict(row)])
    return found


def request_verification(uow: UnitOfWork) -> JobOut:
    """``POST /audit-events/verify``: defer an ON_DEMAND verification of the tenant's chain —
    unless one is pending (scheduled or on demand; QUEUED or RUNNING), in which case the answer is
    that job and nothing is deferred. Any holder of ``audit.read`` may call the route at will, and
    every run reads the whole chain and stores a digest (security finding SC-8; supervisor ruling
    R-32; dev-guide DG-KRN-AUD-07)."""
    job_id, _ = uow.defer_single(JobKind.AUDIT_CHAIN_VERIFY, {"trigger": verify.ON_DEMAND})
    return jobs.job_out_of(uow.session, job_id)
