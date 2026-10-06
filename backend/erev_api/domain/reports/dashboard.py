"""API-R-50 home dashboard read model (04 §16.13 API-S-DashboardHome, API-C-11; SCREENS R-02, §2.5,
§2.6; 03 REQ-RPT-016; BUILD_SPEC RPS-17).

``home(uow, entity_ids, book_code, period_id)`` answers API-S-DashboardHome for a context: the named
entities (none: every entity in scope), one book and one period. It reads the datasets the drilled
screens read, so each figure equals its report:

- ``revenue`` and ``revenue_chart`` (``revenue_panel``): the RPT-01 population
  (``revenue_waterfall.population``) of each entity over its calendar's context period − 5 to + 6,
  as of the context period end. ``current`` is the recognized revenue of the context period (the
  SF-04 waterfall total of a one-period run; J-16.1), ``prior`` that of the period before (null
  when the calendar has none), ``trend`` the six periods ending with the context period; the chart
  gives recognized and scheduled revenue per period, the awaiting-trigger amount and the number of
  obligations with a non-zero awaiting amount;
- ``contract_liability``: the RPT-03 presented balance (``tie_outs.balances_at``) at the end of the
  context period and at the end of the period before;
- ``rpo``: section 1 of RPT-06 (``rpo.rows_at``, exempt obligations left out) at the context period
  end; ``within_12_months`` is each obligation's ``current`` part, bounded at 12 months whatever
  POL-201 holds;
- ``pending_approvals``: the requests of SF-12 "Waiting for me" (``assigned_to_me=true``) that the
  caller can decide (``engine.can_decide`` for a registered subject), of the named entities by the
  L7-2-Q-2 rule (``gates.request_of_entity``);
- ``open_exceptions``: ``OPEN`` and ``IN_PROGRESS`` items, of the named entities when entities are
  named — by the one attribution of an item to an entity (``gates.item_of_entity``; 04 rev 1.206,
  supervisor ruling R-121 (i)), which the SF-11 ``entity`` filter reads too: the figure equals
  the list behind its link and covers every item ``close.blockers.exceptions_open`` counts;
- ``close`` (``close_panel``): API-S-Period ``id``, ``state``, ``blockers`` and ``close_run`` of the
  one named entity; null for several entities (SCREENS §2.6 "Select an entity to see its close
  status").

The three figure panels — revenue, contract liability, RPO — are read inside
``every_entity_scope``, as the jobs of the reports they equal read their datasets, so a context's
figures are the same for a reader of one entity and a reader of every entity (SCREENS §2.5 rev
1.41; dev-guide DG-CMD-13 rev 1.195). The lists of the caller — pending approvals, open
exceptions, the close panel — stay under the caller's scope.

[J] L7-2-Q-17: ``context.entity`` is the entity when exactly one is named, else null. ``currency``
is that entity's functional currency, else the tenant reporting currency. Amounts are not converted:
a context holding an obligation or a balance in another currency answers 422 ``validation-failed``
on ``entity``, as the reports fail closed on ``currency_view`` (D-87 L6-3-Q-20). Period keys align
across entities: each context entity's calendar must hold the context period key, and the trend and
chart periods are the first entity's (code order).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Final
from uuid import UUID

from erev_engine.money import format_exact
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.session import every_entity_scope, tenant_session
from erev_api.db.tables import (
    exception_item,
    legal_entity,
    period,
    period_state,
    tenant,
)
from erev_api.domain.close import gates
from erev_api.domain.close import queries as close_queries
from erev_api.domain.imports import exceptions as exception_queue
from erev_api.domain.platform import approval_queries
from erev_api.domain.reference import queries as reference_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, revenue_waterfall, rpo
from erev_api.domain.reports.tie_outs import ZERO, Calendar, EntityRef, PeriodRef, add
from erev_api.enums import ExceptionSeverity, PeriodState
from erev_api.money import MoneyOut
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.dashboard import (
    DashboardCloseOut,
    DashboardContextOut,
    DashboardContractLiabilityOut,
    DashboardHomeOut,
    DashboardOpenExceptionsOut,
    DashboardPendingApprovalsOut,
    DashboardPeriodOut,
    DashboardRevenueOut,
    DashboardRpoOut,
    RevenueChartOut,
    RevenueChartPeriodOut,
    RevenueChartTotalsOut,
    RevenueTrendOut,
)
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.clock import Clock
    from erev_api.files.store import FileStore

READ_PERMISSION: Final = "contract.read"
RULE_ID: Final = "API-C-11"
TREND_PERIODS: Final = 6
CHART_BEFORE: Final = 5
CHART_AFTER: Final = 6
LIABILITY: Final = "contract_liability"
UNKNOWN_ENTITY: Final = "Choose entities that exist in this workspace."
NO_ENTITY: Final = "No entity is in your scope."
UNKNOWN_PERIOD: Final = "Choose a period of the entity's calendar."
NO_OPEN_PERIOD: Final = "Choose a period. No period of these entities is open."
UNCONVERTED: Final = (
    "Key figures show amounts in {currency} only. Contracts in other currencies are not converted."
)


@dataclass(frozen=True, slots=True)
class HomeContext:
    """The resolved context of one home read."""

    named_ids: tuple[UUID, ...]
    named: EntityRef | None
    entities: tuple[EntityRef, ...]
    calendars: Mapping[UUID, Calendar]
    positions: Mapping[UUID, int]  # entity → index of the context period in its calendar
    book_code: str
    currency: str
    known_at: datetime

    def at(self, entity_id: UUID) -> PeriodRef:
        return self.calendars[entity_id].periods[self.positions[entity_id]]

    def window(self, entity_id: UUID, before: int, after: int) -> tuple[PeriodRef, ...]:
        index = self.positions[entity_id]
        return self.calendars[entity_id].periods[max(0, index - before) : index + after + 1]


def _invalid(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field=field, rule_id=RULE_ID, message=message)],
    )


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _money(amount: Decimal, currency: str) -> MoneyOut:
    return MoneyOut(**tie_outs.money(amount, currency))


def _in_scope(session: Session, principal: Principal) -> dict[str, UUID]:
    """The entities the principal reads, by code in code order."""
    scope = principal.permission_scopes.get(READ_PERMISSION)
    allowed = None if scope is None or scope == "*" else frozenset(scope)
    rows = session.execute(
        select(legal_entity.c.id, legal_entity.c.code).order_by(legal_entity.c.code)
    ).tuples()
    return {
        str(code): UUID(str(entity_id))
        for entity_id, code in rows
        if allowed is None or UUID(str(entity_id)) in allowed
    }


def resolve(
    session: Session,
    principal: Principal,
    *,
    entities: Sequence[str],
    book: str | None,
    period_value: str | None,
) -> tuple[tuple[UUID, ...], str, UUID]:
    """API-C-11 context parameters as ids: the named entities (codes or ids), the book (default the
    primary book) and the period (a key or id of the first context entity's calendar; default the
    earliest ``open`` period of the context entities)."""
    in_scope = _in_scope(session, principal)
    named: list[UUID] = []
    for value in entities:
        found = in_scope.get(value)
        if found is None:
            given = _uuid(value)
            found = given if given in in_scope.values() else None
        if found is None:
            raise _invalid("entity", UNKNOWN_ENTITY)
        if found not in named:
            named.append(found)
    context_ids = tuple(named) or tuple(in_scope.values())
    if not context_ids:
        raise _invalid("entity", NO_ENTITY)
    book_code = book or reference_queries.primary_book_code(session)
    if period_value is None:
        earliest = session.execute(
            select(period_state.c.period_id)
            .where(
                period_state.c.entity_id.in_(list(context_ids)),
                period_state.c.book_code == book_code,
                period_state.c.state == PeriodState.OPEN.value,
            )
            .order_by(period_state.c.period_end_date, period_state.c.period_id)
            .limit(1)
        ).scalar()
        if earliest is None:
            raise _invalid("period", NO_OPEN_PERIOD)
        return tuple(named), book_code, UUID(str(earliest))
    first = min(context_ids, key=lambda entity_id: _code_of(in_scope, entity_id))
    statement = (
        select(period.c.id)
        .select_from(
            period.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period.c.tenant_id,
                    legal_entity.c.calendar_id == period.c.calendar_id,
                ),
            )
        )
        .where(legal_entity.c.id == first)
    )
    given = _uuid(period_value)
    statement = statement.where(
        period.c.period_key == period_value if given is None else period.c.id == given
    )
    found_period = session.execute(statement).scalar()
    if found_period is None:
        raise _invalid("period", UNKNOWN_PERIOD)
    return tuple(named), book_code, UUID(str(found_period))


def _code_of(in_scope: Mapping[str, UUID], entity_id: UUID) -> str:
    return next(code for code, found in in_scope.items() if found == entity_id)


def _context(
    uow: UnitOfWork, entity_ids: Sequence[UUID], book_code: str, period_id: UUID
) -> HomeContext:
    session = uow.session
    named_ids = tuple(entity_ids)
    ids = named_ids or tuple(_in_scope(session, uow.principal).values())
    found = tie_outs.entities(session, ids)
    if not found:
        raise _invalid("entity", NO_ENTITY)
    key = session.execute(
        select(period.c.period_key).where(period.c.id == period_id)
    ).scalar_one_or_none()
    if key is None:
        raise _invalid("period", UNKNOWN_PERIOD)
    calendars = tie_outs.calendars(session, found)
    positions: dict[UUID, int] = {}
    for item in found:
        index = next(
            (
                position
                for position, candidate in enumerate(calendars[item.id].periods)
                if candidate.key == str(key)
            ),
            None,
        )
        if index is None:
            raise _invalid("period", UNKNOWN_PERIOD)
        positions[item.id] = index
    named = found[0] if len(named_ids) == 1 else None
    if named is not None:
        currency = named.functional_currency
    else:
        currency = str(
            session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == uow.principal.tenant_id)
            ).scalar_one()
        ).strip()
    return HomeContext(
        named_ids=named_ids,
        named=named,
        entities=found,
        calendars=calendars,
        positions=positions,
        book_code=book_code,
        currency=currency,
        known_at=uow.now,
    )


def _require_currency(context: HomeContext, currency: str) -> None:
    if currency != context.currency:
        raise _invalid("entity", UNCONVERTED.format(currency=context.currency))


# --- panels ---------------------------------------------------------------------------------------


def revenue_panel(
    session: Session, context: HomeContext
) -> tuple[DashboardRevenueOut, RevenueChartOut]:
    """``revenue`` and ``revenue_chart`` from the RPT-01 population (module docstring)."""
    recognized: dict[str, Decimal] = {}
    scheduled: dict[str, Decimal] = {}
    awaiting = ZERO
    pending = 0
    for item in context.entities:
        window = context.window(item.id, CHART_BEFORE, CHART_AFTER)
        params = ReportParams(
            report_code=revenue_waterfall.CODE,
            report_version=1,
            parameters={"from_period_key": window[0].key, "to_period_key": window[-1].key},
            entity_ids=(item.id,),
            known_at=context.known_at,
            book_code=context.book_code,
            as_of_date=context.at(item.id).end,
        )
        for ob in revenue_waterfall.population(session, params).obligations:
            _require_currency(context, ob.currency)
            for key, amount in ob.recognized.items():
                add(recognized, key, amount)
            for key, amount in ob.scheduled.items():
                add(scheduled, key, amount)
            awaiting += ob.awaiting
            pending += 1 if ob.awaiting != 0 else 0
    first = context.entities[0].id
    at = context.at(first)
    index = context.positions[first]
    current = recognized.get(at.key, ZERO)
    prior: Decimal | None = None
    if index > 0:
        prior = recognized.get(context.calendars[first].periods[index - 1].key, ZERO)
    change_ratio = None
    if prior is not None and prior != 0:
        change_ratio = format_exact((Fraction(current) - Fraction(prior)) / abs(Fraction(prior)))
    currency = context.currency
    revenue = DashboardRevenueOut(
        current=_money(current, currency),
        prior=None if prior is None else _money(prior, currency),
        change_ratio=change_ratio,
        trend=[
            RevenueTrendOut(
                period_key=found.key, recognized=_money(recognized.get(found.key, ZERO), currency)
            )
            for found in context.window(first, TREND_PERIODS - 1, 0)
        ],
    )
    window = context.window(first, CHART_BEFORE, CHART_AFTER)
    chart_recognized = sum((recognized.get(found.key, ZERO) for found in window), ZERO)
    chart_scheduled = sum((scheduled.get(found.key, ZERO) for found in window), ZERO)
    chart = RevenueChartOut(
        periods=[
            RevenueChartPeriodOut(
                period_key=found.key,
                recognized=_money(recognized.get(found.key, ZERO), currency),
                scheduled=_money(scheduled.get(found.key, ZERO), currency),
                total=_money(
                    recognized.get(found.key, ZERO) + scheduled.get(found.key, ZERO), currency
                ),
            )
            for found in window
        ],
        awaiting_trigger=_money(awaiting, currency),
        pending_trigger_count=pending,
        totals=RevenueChartTotalsOut(
            recognized=_money(chart_recognized, currency),
            scheduled=_money(chart_scheduled, currency),
            awaiting_trigger=_money(awaiting, currency),
            total=_money(chart_recognized + chart_scheduled + awaiting, currency),
        ),
    )
    return revenue, chart


def _liability(session: Session, context: HomeContext) -> DashboardContractLiabilityOut:
    cutoff = tie_outs.version_cutoff(session, context.known_at)
    ids = tuple(item.id for item in context.entities)
    ends: dict[str, Mapping[UUID, PeriodRef | None]] = {
        "closing": {item.id: context.at(item.id) for item in context.entities},
        "opening": {
            item.id: context.calendars[item.id].before(context.at(item.id))
            for item in context.entities
        },
    }
    totals: dict[str, Decimal] = {}
    for name, period_keys in ends.items():
        totals[name] = ZERO
        for row in tie_outs.balances_at(
            session,
            entity_ids=ids,
            book_code=context.book_code,
            period_keys=period_keys,
            cutoff=cutoff,
        ):
            _require_currency(context, row.currency)
            totals[name] += row.value(LIABILITY)
    return DashboardContractLiabilityOut(
        closing=_money(totals["closing"], context.currency),
        opening=_money(totals["opening"], context.currency),
    )


def _rpo(session: Session, context: HomeContext) -> DashboardRpoOut:
    cutoff = tie_outs.version_cutoff(session, context.known_at)
    store = rpo.load(
        session,
        entity_ids=[item.id for item in context.entities],
        book_code=context.book_code,
        cutoff=cutoff,
    )
    applied = rpo.applied_expedients(
        session, context.entities, book_code=context.book_code, known_at=context.known_at
    )
    as_of = {item.id: context.at(item.id).end for item in context.entities}
    rpo.measure(session, store, {entity_id: (day,) for entity_id, day in as_of.items()})
    found = rpo.rows_at(store, as_of=as_of, bands=rpo.DEFAULT_BANDS, applied=applied)
    total = within = ZERO
    for item in found:
        _require_currency(context, item.ob.currency)
        if item.exemption is None:
            total += item.total
            within += item.current
    return DashboardRpoOut(
        total=_money(total, context.currency), within_12_months=_money(within, context.currency)
    )


def _pending_approvals(
    session: Session, principal: Principal, context: HomeContext
) -> DashboardPendingApprovalsOut:
    authorities = approval_queries.decision_authorities(session, principal, at=context.known_at)
    named = (
        [or_(*(gates.request_of_entity(entity_id) for entity_id in context.named_ids))]
        if context.named_ids
        else []
    )
    # "Waiting for me" is ``can_decide`` (R-64 (4)): the inbox list and this count read one set.
    decidable = approval_queries.decidable(
        session, principal, authorities, at=context.known_at, extra=named
    )
    return DashboardPendingApprovalsOut(
        count=len(decidable),
        oldest_submitted_at=decidable[0]["submitted_at"] if decidable else None,
    )


def _open_exceptions(
    session: Session, principal: Principal, context: HomeContext
) -> DashboardOpenExceptionsOut:
    """The open items the caller may read (``exceptions.readable``; 04 T-IMP-05 rev 1.218), of
    the named entities by the one attribution: the count of the list behind the figure's
    link, by severity."""
    statement = select(exception_item.c.severity, func.count()).where(
        exception_item.c.status.in_(gates.OPEN_EXCEPTIONS),
        exception_queue.readable(principal),
    )
    if context.named_ids:
        statement = statement.where(
            or_(*(gates.item_of_entity(entity_id) for entity_id in context.named_ids))
        )
    counts = {
        str(getattr(severity, "value", severity)): int(count)
        for severity, count in session.execute(
            statement.group_by(exception_item.c.severity)
        ).tuples()
    }
    return DashboardOpenExceptionsOut(
        total=sum(counts.values()),
        blocking=counts.get(ExceptionSeverity.BLOCKING.value, 0),
        warning=counts.get(ExceptionSeverity.WARNING.value, 0),
        info=counts.get(ExceptionSeverity.INFO.value, 0),
    )


def close_panel(session: Session, context: HomeContext) -> DashboardCloseOut | None:
    """API-S-Period ``id``, ``state``, ``blockers`` and ``close_run`` of the named entity's period
    state; null for several entities or a period without a state in the book."""
    if context.named is None:
        return None
    state_id = session.execute(
        select(period_state.c.id).where(
            period_state.c.entity_id == context.named.id,
            period_state.c.book_code == context.book_code,
            period_state.c.period_id == context.at(context.named.id).id,
        )
    ).scalar_one_or_none()
    shown = None if state_id is None else close_queries.period_view(session, UUID(str(state_id)))
    if shown is None:
        return None
    return DashboardCloseOut.model_validate(
        {
            "id": shown["id"],
            "state": shown["state"],
            "blockers": shown["blockers"],
            "close_run": shown["close_run"],
        }
    )


# --- the read model -------------------------------------------------------------------------------


def home(
    uow: UnitOfWork, entity_ids: Sequence[UUID], book_code: str, period_id: UUID
) -> DashboardHomeOut:
    """API-S-DashboardHome of the context (module docstring); never writes (DG-CMD-13)."""
    session = uow.session
    context = _context(uow, entity_ids, book_code, period_id)
    # The three figures that come from report datasets are read as the reports' jobs read them
    # (SCREENS §2.5 rev 1.41; dev-guide DG-CMD-13 rev 1.195; the supervisor's ruling of
    # 2026-10-01): an obligation of the context's entities can be performed by, or belong to a
    # contract of, another entity, whose rows a reader of one entity does not see. Under the
    # caller's scope the Home left such revenue out for one reader and was refused whole for
    # another (rule S15-R-01 over schedule lines the scope hid) where a reader of every entity
    # got the figures. The context's entities are the caller's own (``resolve``); the panels
    # return sums and no row.
    #
    # The count of the requests waiting for the caller is read in the same block (04 §16.13 rev
    # 1.319; supervisor ruling R-64 (4): the inbox list, its total and this count hold exactly
    # the requests the caller can decide now). The Home is a transaction of ``contract.read``
    # (04 API-C-03), and a request of one entity is under the entity policy: under the route's
    # scope the count missed the request of an entity the caller approves for and does not read
    # contracts of, which the inbox — a route without a permission guard — lists. The count asks
    # the inbox's own statement (``approval_queries.decidable``), which names the caller's
    # permissions; whatever it selects lies within the entities of the caller's roles, so under
    # the tenant's scope it holds the rows it holds under the inbox's.
    with every_entity_scope(session, uow.principal.db_context):
        revenue, chart = revenue_panel(session, context)
        liability = _liability(session, context)
        remaining = _rpo(session, context)
        waiting = _pending_approvals(session, uow.principal, context)
    at = context.at(context.entities[0].id)
    return DashboardHomeOut(
        context=DashboardContextOut(
            entity=None
            if context.named is None
            else {
                "id": context.named.id,
                "code": context.named.code,
                "name": _entity_name(session, context.named.id),
            },
            book=context.book_code,
            period=DashboardPeriodOut(period_key=at.key, name=at.name, end_date=at.end),
            currency=context.currency,
            known_at=context.known_at,
        ),
        revenue=revenue,
        contract_liability=liability,
        rpo=remaining,
        pending_approvals=waiting,
        open_exceptions=_open_exceptions(session, uow.principal, context),
        close=close_panel(session, context),
        revenue_chart=chart,
    )


def _entity_name(session: Session, entity_id: UUID) -> str:
    return str(
        session.execute(
            select(legal_entity.c.name).where(legal_entity.c.id == entity_id)
        ).scalar_one()
    )


def read_home(
    ctx: RequestContext,
    *,
    clock: Clock,
    keyring: KeyRing,
    files: FileStore,
    entities: Sequence[str],
    book: str | None,
    period_value: str | None,
) -> DashboardHomeOut:
    """``GET /dashboard/home``: resolve the context parameters and read the home model in one
    read-only transaction (DG-CMD-13); the unit of work is discarded, never committed."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        uow = UnitOfWork(ctx=ctx, session=session, clock=clock, keyring=keyring, files=files)
        try:
            entity_ids, book_code, period_id = resolve(
                session, ctx.principal, entities=entities, book=book, period_value=period_value
            )
            return home(uow, entity_ids, book_code, period_id)
        finally:
            uow.discard()
