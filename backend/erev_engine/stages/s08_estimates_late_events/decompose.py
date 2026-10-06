"""Stage 08 prior-period decomposition (ENGINE_SPEC §8.5 S08-R-14 to S08-R-16, §8.6; ENB-12).

``decompose_prior_period`` returns one ``revenue_prior_period`` target per obligation for a period
t starting at s: the revenue of t from performance satisfied before s (POL-204
``ALG10_DECOMPOSITION``; POLICIES ALG-10 §2.11.3; 606-10-50-12A; IFRS 15.116(c)). Stage 15 calls it
with the ``AllocatedState`` stage 09 consumed (ENGINE_SPEC_B §0.4, S15-R-13).

- Boundaries (S08-R-14). E is the exact cumulative revenue of the ``FIXED`` component with the
  measure quantities at the end of the day before s, measured by stage 09 (CV-63; L1-3-Q-30). E_0
  is the value under the state in force then. For each boundary k effective in t that gives the
  obligation a new segment, in ENG-06 order, E_k applies the allocation and progress totals of
  that segment at s, and the part is round(E_k − E_(k−1)). The state immediately before k is the
  state after the previous boundary, so E_(k−1) is E_before,k. An ``INCEPTION``-basis segment is
  measured from inception. A ``PROSPECTIVE`` segment that copies the base of the segment in force
  at s (a price change after an earlier 25-13(a) boundary) is measured from that boundary. A
  25-13(a) boundary in t, and a price change that copies it, contributes 0 (CV-63; S15-R-13), and
  so does a termination (S09-R-06; L2-5-Q-6). A measure-only ``EAC`` version applied in t to an
  input-measured obligation adds no segment (S08-R-02) but changes the progress totals, so it is a
  boundary of its own (D-97 (10)): E_k is the target of the segment in force with the ``EAC``
  version in force after k, and the part is round(E_k − E_(k−1)). Every E_k of an input-measured
  obligation reads the version in force after k (the S06-R-15 updated EAC of a class N
  amendment), dated no later than the day before s so that the costs at s meet the totals after
  k; the node names it as ``version_<k>``. After a 25-13(a) boundary effective in t with a new
  base, no later measure-only version of t contributes: the basis in force starts at that boundary
  and nothing of it is measured at s (CV-63; C4-EAC-R1).
- Late events (S08-R-15; ALG-09 step 7). For each closed or locked period p before t whose carry
  ``assign_posting_period`` posts in t: the period target of p (stage 09 after S09-R-41) less the
  revenue posted with origin p (``InputBundle.posted``; debit positive, so revenue enters negated;
  ENGINE_SPEC_B S14-R-04). ``posted`` is bound by the caller, as ``price_at`` is (L1-3-Q-26), and a
  carry without it fails closed (L2-5-Q-4).
- Output (S08-R-16): node ``revenue_prior_period:<ob>:<period key>`` (``estimate.prior_period.v1``)
  citing each boundary event with its part. Journal lines are not split.

Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from fractions import Fraction
from typing import Final

from erev_engine import dates, money
from erev_engine.bundle import EstimateVersionInput, PeriodInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s08_estimates_late_events import routing
from erev_engine.stages.s08_estimates_late_events.assign import (
    CLOSED_STATES,
    assign_posting_period,
)
from erev_engine.stages.s09_recognition import eac_version_at, measures_eac, target_at_position
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    OrderKey,
    PostedIndex,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["CHANGE_TYPES", "MEASURE", "PRIOR_PERIOD_FORMULA", "decompose_prior_period"]

PRIOR_PERIOD_FORMULA: Final = "estimate.prior_period.v1"
MEASURE: Final = "revenue_prior_period"
REVENUE_ROLE: Final = "REVENUE"  # E-01
FIXED: Final = "FIXED"
PROSPECTIVE: Final = "PROSPECTIVE"
# Table 0.3-A boundaries that change an allocation or progress totals (S08-R-14).
CHANGE_TYPES: Final = frozenset(
    {
        "CONTRACT_AMENDED",
        "CONTRACT_TERMINATED",
        "ESTIMATE_CHANGED",
        "LINE_ATTRIBUTES_CHANGED",
        "MATERIAL_RIGHT_EXERCISED",
        "REGROUPED",
    }
)
RULE_BOUNDARY: Final = "S08-R-14"
RULE_PROSPECTIVE: Final = "CV-63"
RULE_TERMINATION: Final = "S09-R-06"


@dataclass(frozen=True, slots=True)
class _Part:
    """The prior-period part of one boundary: E_before,k(s) and E_after,k(s), currency units."""

    event: EventView
    before: Fraction
    after: Fraction
    rule: str
    version: str | None = None  # the EAC version in force after k of an input-measured obligation


@dataclass(frozen=True, slots=True)
class _Carry:
    """A late carry into t: the period target of a closed period less its posted revenue."""

    origin_period_key: str
    target: int  # minor units
    posted: int  # minor units, credit positive


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def decompose_prior_period(
    ctx: BookContext,
    st: AllocatedState,
    period_key: str,
    tb: TraceBuilder,
    *,
    posted: PostedIndex | None = None,
) -> tuple[Target, ...]:
    """One ``revenue_prior_period`` target per obligation for ``period_key`` (ENGINE_SPEC §8.5)."""
    mu = routing.minor_unit(ctx)
    order_keys = {ev.event_key: ev.order_key for ev in st.events}
    targets: list[Target] = []
    for ob in st.obligations:
        calendar = _calendar(ctx, ob)
        period = next((item for item in calendar if item.period_key == period_key), None)
        if period is None:
            raise _invariant(
                "the period is absent from the owning entity's calendar",
                ob.subject_key,
                rule="CV-12",
                period_key=period_key,
            )
        parts = _parts(ctx, st, ob, period, order_keys)
        carries = _carries(ctx, st, ob, calendar, period, posted)
        targets.append(_emit(ctx, tb, ob, period, parts, carries, mu))
    return tuple(targets)


def _calendar(ctx: BookContext, ob: ObligationState) -> tuple[PeriodInput, ...]:
    entity = ctx.entities.get(ob.performing_entity)
    if entity is None:
        raise _invariant("the owning entity has no calendar", ob.subject_key, rule="CV-12")
    return tuple(sorted(entity.periods, key=lambda item: (item.start_date, item.end_date)))


def _segment_at(
    ob: ObligationState, ev: EventView, order_keys: Mapping[str, OrderKey]
) -> AllocationSegment | None:
    """The ``FIXED`` segment in force immediately after ``ev`` in ENG-06 order (CV-60)."""
    found: AllocationSegment | None = None
    for seg in ob.segments:
        if seg.component != FIXED or seg.effective_date > ev.effective_date:
            continue
        if seg.event_key is not None:
            key = order_keys.get(seg.event_key)
            if key is None:
                raise _invariant(
                    "the boundary event of a segment is absent", ob.subject_key, rule="CV-60"
                )
            if key > ev.order_key:
                continue
        found = seg
    return found


def _base(seg: AllocationSegment) -> tuple[object, ...]:
    return (
        seg.component,
        seg.basis,
        seg.base_revenue_posted,
        seg.base_revenue_exact,
        seg.base_progress,
        seg.totals,
        seg.progress_measure,
    )


def _parts(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    period: PeriodInput,
    order_keys: Mapping[str, OrderKey],
) -> list[_Part]:
    day_before = period.start_date - timedelta(days=1)
    at_start = target_at_position(ctx, st, ob, day_before)
    in_force = at_start.segment
    view = in_force  # the FIXED segment in force at s, as the last boundary left it
    current = at_start.fixed_exact
    parts: list[_Part] = []
    for ev in st.events:
        if ev.event_type not in CHANGE_TYPES:
            continue
        if not period.start_date <= ev.effective_date <= period.end_date:
            continue
        seg = _segment_at(ob, ev, order_keys)
        if seg is None or seg.event_key != ev.event_key:
            # The boundary gives this obligation no new segment; a measure-only EAC version of an
            # input-measured obligation is a boundary of its own (S08-R-14; D-97 (10)).
            if (
                view is not None
                and ev.event_type == "ESTIMATE_CHANGED"
                and measures_eac(st, ob, ev)
            ):
                measured, version = _measure(ctx, st, ob, view, day_before, ev)
                if (
                    measured != current
                ):  # a version the previous boundary already read moves nothing
                    parts.append(_Part(ev, current, measured, RULE_BOUNDARY, version))
                    current = measured
            continue
        if seg.cause == SegmentCause.TERMINATION:
            parts.append(_Part(ev, current, current, RULE_TERMINATION))
            continue
        if seg.basis == PROSPECTIVE:
            if in_force is None or _base(seg) != _base(in_force):
                parts.append(_Part(ev, current, current, RULE_PROSPECTIVE))
                # The basis in force now starts at this boundary, so nothing of it is measured
                # at s: a later measure-only version of t adds nothing (CV-63; Codex C4-EAC-R1).
                view = None
                continue
            view = replace(
                seg, effective_date=in_force.effective_date, event_key=in_force.event_key
            )
        else:
            view = replace(seg, effective_date=min(seg.effective_date, day_before))
        measured, version = _measure(ctx, st, ob, view, day_before, ev)
        parts.append(_Part(ev, current, measured, RULE_BOUNDARY, version))
        current = measured
    return parts


def _measure(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    view: AllocationSegment,
    day_before: date,
    ev: EventView,
) -> tuple[Fraction, str | None]:
    """E_k(s): the exact FIXED target at the end of the day before s under the state immediately
    after k (S08-R-14): the segment ``view`` and, for an input-measured obligation, the ``EAC``
    version in force after k (``eac_version_at`` at k, inclusive; S06-R-15), which stands alone
    for its element in the measured state, dated no later than ``day_before`` so that the measure
    quantities at s meet the totals after k."""
    version = eac_version_at(st, ob, view, ev.effective_date, event=ev, inclusive=True)
    state = st if version is None else _with_version(st, version, day_before)
    measured = target_at_position(
        ctx, state, replace(ob, segments=(view,)), day_before, event=ev, inclusive=True
    )
    return measured.fixed_exact, None if version is None else version.version_key


def _with_version(
    st: AllocatedState, version: EstimateVersionInput, day_before: date
) -> AllocatedState:
    """``st`` with ``version`` as the only pin of its element, effective no later than
    ``day_before`` (its ``ESTIMATE_CHANGED`` position kept), so the input measure reads it then."""
    pins = dict(st.estimates.pins)
    pin = next(
        item
        for item in pins.get(version.estimate_key, ())
        if item.version.version_key == version.version_key
    )
    dated = replace(version, effective_date=min(version.effective_date, day_before))
    pins[version.estimate_key] = (EstimatePin(dated, pin.event_order_key),)
    return replace(st, estimates=EstimatePins(pins))


def _carries(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    calendar: Sequence[PeriodInput],
    period: PeriodInput,
    posted: PostedIndex | None,
) -> list[_Carry]:
    book_code = str(ctx.book_code)
    if dates.period_state(period, book_code) not in dates.POSTABLE_STATES:
        return []  # nothing posts in t
    earlier = [item for item in calendar if item.end_date < period.start_date]
    carried = {
        item.period_key
        for item in earlier
        if dates.period_state(item, book_code) in CLOSED_STATES
        and assign_posting_period(ctx, ob.performing_entity, item.end_date).posting_period_key
        == period.period_key
    }
    if not carried:
        return []
    if posted is None:
        raise _invariant(
            "the posted amounts of a late carry are not bound",
            ob.subject_key,
            rule="S08-R-15",
            period_key=period.period_key,
        )
    carries: list[_Carry] = []
    previous = 0
    for item in earlier:
        cumulative = target_at_position(ctx, st, ob, item.end_date, adjusted=True).value
        target, previous = cumulative - previous, cumulative
        if item.period_key not in carried:
            continue
        by_origin = _posted_revenue(ctx, posted, ob, item.period_key)
        if target != by_origin:
            carries.append(_Carry(item.period_key, target, by_origin))
    return carries


def _posted_revenue(
    ctx: BookContext, posted: PostedIndex, ob: ObligationState, origin_period_key: str
) -> int:
    """Revenue posted with origin ``origin_period_key``, minor units, credit positive (S14-R-04)."""
    wanted = (
        str(ctx.book_code),
        ob.performing_entity,
        ob.subject_key,
        REVENUE_ROLE,
        ctx.txn_currency,
        origin_period_key,
    )
    total = 0
    for amount in posted.amounts:
        origin = amount.origin_period_key or amount.period_key
        key = (
            amount.book_code,
            amount.entity_code,
            amount.subject_key,
            amount.account_role,
            amount.txn_currency,
            origin,
        )
        if key == wanted:
            total -= amount.amount_txn
    return total


def _emit(
    ctx: BookContext,
    tb: TraceBuilder,
    ob: ObligationState,
    period: PeriodInput,
    parts: Sequence[_Part],
    carries: Sequence[_Carry],
    mu: int,
) -> Target:
    """``revenue_prior_period:<ob>:<period key>`` and its target (S08-R-16)."""
    params = {
        "as_of": (period.start_date - timedelta(days=1)).isoformat(),
        "boundaries": str(len(parts)),
        "carries": str(len(carries)),
        "period_start": period.start_date.isoformat(),
    }
    inputs: list[str | SourceRef] = []
    value = 0
    exact = Fraction(0)
    for index, part in enumerate(parts, start=1):
        amount = money.round_half_up(part.after - part.before, mu)
        params[f"e_after_{index}"] = rational_param(part.after)
        params[f"e_before_{index}"] = rational_param(part.before)
        params[f"rule_{index}"] = part.rule
        if part.version is not None:
            params[f"version_{index}"] = part.version
        detail = {"member": "prior_period_part", "value": money.format_money(amount, mu)}
        inputs.append(SourceRef("contract_event", part.event.event_key, detail))
        value += amount
        exact += part.after - part.before
    for index, carry in enumerate(carries, start=1):
        params[f"late_origin_{index}"] = carry.origin_period_key
        params[f"late_posted_{index}"] = str(carry.posted)
        params[f"late_target_{index}"] = str(carry.target)
        value += carry.target - carry.posted
        exact += Fraction(carry.target - carry.posted, 10**mu)
    node_id = tb.node(
        measure=MEASURE,
        subject_key=ob.subject_key,
        period_key=period.period_key,
        value=value,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=PRIOR_PERIOD_FORMULA,
        inputs=inputs,
        params=params,
        exact=exact,
        narrative_key=PRIOR_PERIOD_FORMULA.rsplit(".v", 1)[0],
    )
    return Target(
        book_code=ctx.book_code,
        entity=ob.performing_entity,
        subject_key=ob.subject_key,
        measure=MEASURE,
        period_key=period.period_key,
        cause=None,
        value=value,
        exact=exact,
        node_id=node_id,
    )
