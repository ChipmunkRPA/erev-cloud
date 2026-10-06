"""Stage 09 royalties: the ``ROYALTY`` recognition component (ENGINE_SPEC_B §9.2.9 S09-R-32 to
S09-R-34, S09-R-01 to S09-R-03; POLICIES POL-056, POL-057; 606-10-55-65 to 55-65B; ENC-8).

Sales- or usage-based royalties of a licence of IP are realised amounts (S09-R-02): X = A = the
realised cumulative amount CR in minor units and f = 1 once the licence is satisfied, so the
component adds CR to the obligation's allocation and to its target. CR is the kernel realisation of
``erev_engine.royalties`` (the latest statement per usage period whose period has ended, plus the
``ROYALTY_ACCRUAL`` version in force for every ended period no statement covers under POL-056
``ACCRUE_ESTIMATE``), the same function stage 04 prices into the transaction price (S04-R-06;
04 DB-17 V1). Under POL-057 ``FIXED_ON_LICENCE_PATTERN`` the stated price of a ``ROYALTY``-method
licence is its minimum guarantee, fixed consideration recognised by the ``FIXED`` component on the
licence pattern, and royalty revenue is max(0, CR − G) (S09-R-33). Realised royalties of a licence
not yet satisfied (no ``FIXED`` progress) stay awaiting trigger (S09-R-45).

The component's node is ``royalty_revenue_cum`` (``royalty.accrual.v1``, or
``royalty.minimum_guarantee.v1`` when a guarantee nets), citing each statement and accrual as a
source reference; a statement emits ``royalty_true_up@<event key>`` (``royalty.report_true_up.v1``,
S09-R-32) once (CV-50): its amount less the prior measurement of its usage period, the accruals
it replaces or, for a corrected statement, the statement it corrects (the latest earlier statement
for the same usage period), so the node explains the event's own movement rather than the
cumulative difference from the original estimate. The coverage-gap facts of S09-R-34 are
published for the close step, which raises ``ROYALTY_ACCRUAL_MISSING``. Private to stage 09.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates, money, royalties
from erev_engine.errors import EngineError
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ACCRUAL_FORMULA",
    "GUARANTEE_FORMULA",
    "ROYALTY_MEASURE",
    "TRUE_UP_FORMULA",
    "CoverageGap",
    "RoyaltyPart",
    "bearing",
    "coverage_gaps",
    "emit",
    "target",
]

ACCRUAL_FORMULA: Final = "royalty.accrual.v1"
TRUE_UP_FORMULA: Final = "royalty.report_true_up.v1"
GUARANTEE_FORMULA: Final = "royalty.minimum_guarantee.v1"
ROYALTY_MEASURE: Final = "royalty_revenue_cum"
TRUE_UP_MEASURE: Final = "royalty_true_up"
COMPONENT: Final = "ROYALTY"
_ONE_DAY: Final = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class RoyaltyPart:
    """The ``ROYALTY`` component at a date and position (S09-R-02, S09-R-33)."""

    realised: int  # max(0, CR − G), minor units: X = A of the component
    recognised: int  # the realised amount once the licence is satisfied, else 0
    satisfied: bool
    guarantee: int  # G, minor units (0 unless POL-057 nets a ROYALTY-method stated price)
    realisation: royalties.Realisation
    formula_id: str
    params: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """A royalty usage period ended by the period end with neither statement nor accrual
    (S09-R-34): the close step raises ``ROYALTY_ACCRUAL_MISSING`` from it."""

    subject_key: str
    contract_key: str
    entity: str  # contracting entity
    period_key: str
    period_end: date
    usage_period_start: date
    usage_period_end: date


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def bearing(ob: ObligationState) -> bool:
    """The obligation carries a ``ROYALTY`` component (a marker segment from stage 05)."""
    return any(seg.component == COMPONENT for seg in ob.segments)


def _accrues(ctx: BookContext, ob: ObligationState, d: date) -> bool:
    """POL-056 ``ACCRUE_ESTIMATE`` at the contracting entity's period of ``d`` (pin P)."""
    entity = ctx.entities.get(ob.contracting_entity)
    if entity is None:
        raise _invariant("the contracting entity has no calendar", ob, rule="CV-12")
    period = dates.period_of(entity, d).period_key
    value = ctx.policies.value(
        royalties.UNREPORTED_SALES_POLICY,
        contract=ob.contract_key,
        obligation=ob.subject_key,
        entity=ob.contracting_entity,
        period=period,
    )
    return value == royalties.ACCRUE_ESTIMATE


def _guarantee(ctx: BookContext, ob: ObligationState, mu: int) -> int:
    """G in minor units: the stated price of a ``ROYALTY``-method licence under POL-057
    ``FIXED_ON_LICENCE_PATTERN`` (S09-R-33; the stage 04 S04-R-06 netting), else 0."""
    if str(ob.recognition_method) != royalties.ROYALTY_METHOD:
        return 0
    policy = ctx.policies.value(royalties.GUARANTEE_POLICY, contract=ob.contract_key)
    if policy != royalties.FIXED_ON_LICENCE_PATTERN:
        return 0
    return money.round_half_up(ob.stated_price, mu)


def _minor(amount: Fraction, mu: int, ob: ObligationState, what: str) -> int:
    scaled = amount * 10**mu
    if scaled.denominator != 1:
        raise _invariant(f"{what} has more places than the currency", ob, rule="CV-45")
    return int(scaled.numerator)


def target(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    d: date,
    *,
    satisfied: bool,
    position: Position | None = None,
    mu: int,
) -> RoyaltyPart:
    """``royalty_target`` of §9.2.9 at ``d`` and ``position``.

    ``satisfied`` is the licence's satisfaction at ``d`` (the ``FIXED`` component has progressed),
    read by the caller from the segment target; realised royalties before it wait (S09-R-45).
    """
    cutoff = None if position is None else position.order_key
    inclusive = True if position is None else position.inclusive
    found = royalties.realised(
        st.measure_events,
        st.estimates,
        ob.contract_key,
        ob.obligation_key,
        ob.subject_key,
        at=d,
        cutoff=cutoff,
        inclusive=inclusive,
        accrue=_accrues(ctx, ob, d),
    )
    guarantee = _guarantee(ctx, ob, mu)
    gross = _minor(found.total, mu, ob, "a realised royalty")
    realised = max(0, gross - guarantee)
    params = {
        "as_of": d.isoformat(),
        "guarantee": rational_param_minor(guarantee, mu),
        "satisfied": "true" if satisfied else "false",
    }
    formula_id = GUARANTEE_FORMULA if guarantee else ACCRUAL_FORMULA
    return RoyaltyPart(
        realised=realised,
        recognised=realised if satisfied else 0,
        satisfied=satisfied,
        guarantee=guarantee,
        realisation=found,
        formula_id=formula_id,
        params=MappingProxyType(dict(sorted(params.items()))),
    )


def rational_param_minor(amount: int, mu: int) -> str:
    """A minor-unit amount as a currency-unit rational param."""
    value = Fraction(amount, 10**mu)
    return (
        str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    )


def _sources(found: royalties.Realisation) -> list[str | SourceRef]:
    sources: list[str | SourceRef] = []
    for item in found.statements:
        sources.append(
            SourceRef(
                "contract_event",
                item.event.event_key,
                {
                    "member": "rated_amount",
                    "usage_period_end": item.end.isoformat(),
                    "usage_period_start": item.start.isoformat(),
                    "value": money.format_exact(item.amount),
                },
            )
        )
    for accrual in found.accruals:
        sources.append(
            SourceRef(
                "estimate_version",
                accrual.version.version_key,
                {
                    "member": accrual.member,
                    "usage_period_end": accrual.end.isoformat(),
                    "usage_period_start": accrual.start.isoformat(),
                    "value": money.format_exact(accrual.amount),
                },
            )
        )
    return sources


def _measured_by(item: royalties.Statement) -> date:
    """The date at which ``item`` and the measurements it replaces are counted: its effective date,
    or its usage period end when the statement precedes it (``statements`` and ``accruals`` count
    ended periods only; the order-key cutoff keeps later events out)."""
    return max(item.event.effective_date, item.end)


def _corrected_statement(
    st: AllocatedState, ob: ObligationState, item: royalties.Statement
) -> royalties.Statement | None:
    """The latest earlier statement for the same usage period as ``item``, which ``item`` corrects
    (S09-R-32: the latest statement per usage period counts), or None."""
    earlier = royalties.statements(
        st.measure_events,
        ob.contract_key,
        ob.obligation_key,
        ob.subject_key,
        at=_measured_by(item),
        cutoff=item.event.order_key,
        inclusive=False,
    )
    for found in earlier:
        if (found.start, found.end) == (item.start, item.end):
            return found
    return None


def _replaced_accruals(
    st: AllocatedState, ob: ObligationState, item: royalties.Statement
) -> tuple[royalties.Accrual, ...]:
    """The accrual versions in force before ``item`` whose usage periods lie within its own
    (S09-R-32), by (start, end)."""
    replaced = royalties.accruals(
        st.estimates,
        ob.contract_key,
        ob.obligation_key,
        at=_measured_by(item),
        cutoff=item.event.order_key,
        inclusive=False,
    )
    return tuple(acc for acc in replaced if item.start <= acc.start and acc.end <= item.end)


def _emit_true_ups(
    tb: TraceBuilder,
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    item: royalties.Statement,
    emitted: set[str],
    *,
    mu: int,
) -> None:
    """``royalty_true_up@<event key>`` for ``item`` and, in turn, for each earlier statement of
    its usage period that it corrects, once per event (CV-50), so that the event nodes foot to
    the period's ``ROYALTY`` movement even when several statements fall in one period.

    A corrected statement cites the statement it corrects (``replaces = statement``); the first
    statement of a usage period cites the accruals it replaces (``replaces = accrual``) and emits
    nothing when there are none. Formula ``royalty.report_true_up.v1`` is unchanged: input 0 less
    the sum of the further inputs (DG-ENG-04; PROP:P14).
    """
    current: royalties.Statement | None = item
    while current is not None:
        node_id = f"{TRUE_UP_MEASURE}@{current.event.event_key}:{ob.subject_key}:-"
        if node_id in emitted:
            return
        prior = _corrected_statement(st, ob, current)
        if prior is not None:
            replaced_amount = prior.amount
            inputs = _sources(royalties.Realisation((current, prior), ()))
            replaces = "statement"
        else:
            accruals = _replaced_accruals(st, ob, current)
            if not accruals:
                return
            replaced_amount = sum((acc.amount for acc in accruals), Fraction(0))
            inputs = _sources(royalties.Realisation((current,), accruals))
            replaces = "accrual"
        tb.node(
            measure=f"{TRUE_UP_MEASURE}@{current.event.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=_minor(current.amount - replaced_amount, mu, ob, "a true-up"),
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=TRUE_UP_FORMULA,
            inputs=inputs,
            params={
                "as_of": current.event.effective_date.isoformat(),
                "replaces": replaces,
                "usage_period_end": current.end.isoformat(),
                "usage_period_start": current.start.isoformat(),
            },
            narrative_key=TRUE_UP_FORMULA.rsplit(".v", 1)[0],
        )
        emitted.add(node_id)
        current = prior


def emit(
    tb: TraceBuilder,
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    period_key: str,
    part: RoyaltyPart,
    emitted: set[str],
    *,
    mu: int,
) -> str:
    """``royalty_revenue_cum:<ob>:<period>`` and the ``royalty_true_up@`` nodes (§9.5; S09-R-32).

    The component node cites every statement and accrual counted. Each statement counted emits
    its true-up once (CV-50): input 0 is the statement and the further inputs the prior
    measurement of its usage period it replaces, the accruals admitted before it (param
    ``replaces = accrual``) or the statement it corrects (``replaces = statement``); the value is
    the statement less that prior measurement. A statement that replaces nothing has no node.
    """
    for item in part.realisation.statements:
        _emit_true_ups(tb, ctx, st, ob, item, emitted, mu=mu)
    return tb.node(
        measure=ROYALTY_MEASURE,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=part.recognised,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=part.formula_id,
        inputs=_sources(part.realisation),
        params=part.params,
        narrative_key=part.formula_id.rsplit(".v", 1)[0],
    )


def _whole_months(start: date, end: date) -> int | None:
    """The length in months of a usage period spanning whole calendar months, else None."""
    if start.day != 1 or end != dates.month_end(end) or end < start:
        return None
    return (end.year - start.year) * 12 + end.month - start.month + 1


def coverage_gaps(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    d: date,
    period_key: str,
    *,
    satisfied: bool,
) -> tuple[CoverageGap, ...]:
    """S09-R-34 at the period end ``d``: with the licence satisfied and POL-056 ``ACCRUE_ESTIMATE``,
    the next expected usage period after the latest covered one (statement or accrual in force at
    ``d``) that ended by ``d`` with neither, as one fact. Before the first covered period no fact is
    emitted, and a cadence that is not whole months is left to the preparer [J]."""
    if not satisfied or not _accrues(ctx, ob, d):
        return ()
    found = royalties.realised(
        st.measure_events,
        st.estimates,
        ob.contract_key,
        ob.obligation_key,
        ob.subject_key,
        at=d,
        accrue=True,
    )
    covered = [(item.start, item.end) for item in found.statements]
    covered.extend((accrual.start, accrual.end) for accrual in found.accruals)
    if not covered:
        return ()
    start, end = max(covered, key=lambda item: (item[1], item[0]))
    length = _whole_months(start, end)
    if length is None:
        return ()
    next_start = end + _ONE_DAY
    next_end = dates.add_months(end, length)
    if next_end > d:
        return ()
    if any(s <= next_start and next_end <= e for s, e in covered):
        return ()
    return (
        CoverageGap(
            ob.subject_key,
            ob.contract_key,
            ob.contracting_entity,
            period_key,
            d,
            next_start,
            next_end,
        ),
    )
