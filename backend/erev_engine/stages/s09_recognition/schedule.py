"""Stage 09 obligation measures, schedules and versioning (ENGINE_SPEC_B §9.2.13, §9.2.14; ENC-10).

``obligation_measures`` gives the T-CON-11 values of one obligation at the version date d_v (§9.1):
allocated = revenue_cum + scheduled + awaiting trigger (S09-R-45; S09-INV-03; 04 DB-17). Scheduled
is what a deterministic component (``is_deterministic``; rev 1.126) still places in later
periods without further events; every other remainder awaits a trigger, and so does a held target
(S09-R-44). ``satisfaction_status`` and ``satisfied_date`` follow S09-R-46 and the legacy
SSP-delivered measures S09-R-47. The activity columns aggregate the effects of the events first
included in the version (ENGINE_SPEC CV-64; DEV-051). ``revenue_schedule`` turns the period amounts
by cause into the ``REVENUE`` lines of one contract version (S09-R-48 to S09-R-50). ``validate`` is
the stage entry assertion of S09-INV-07. Every measure node comes from a registered formula, so the
trace reproduces it (DG-KRN-EXP-04). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.enums import SatisfactionStatus, ScheduleKind, ScheduleLineType
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.money import format_exact, format_money, round_half_up, to_fraction
from erev_engine.stages.s09_recognition import (
    components,
    decompose,
    progress_events,
    progress_inputs,
    returns,
    royalty,
    step1,
)
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    ObligationState,
    ScheduleLineOut,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "AWAITING_FORMULA",
    "DETERMINISTIC",
    "EVENT_DRIVEN",
    "HOLD_TYPES",
    "MEASURE_MARKERS",
    "REMAINING_FORMULA",
    "SCHEDULED_FORMULA",
    "ObligationMeasures",
    "build",
    "is_deterministic",
    "obligation_measures",
    "realised_at",
    "revenue_schedule",
    "unit_ssp",
    "validate",
    "version_date",
]

ALLOCATION_FORMULA: Final = "rec.allocation.v1"
REALISED_FORMULA: Final = "rec.realised_allocation.v1"
FIXED_SCHEDULE_FORMULA: Final = "rec.schedule.fixed.v1"
PERIOD_VC_FORMULA: Final = "rec.period_vc_revenue.v1"
ADJUSTMENT_FORMULA: Final = "rec.allocation_adjustment.v1"
SEGMENT_STATE_FORMULA: Final = "rec.segment_state.v1"
ACTIVITY_FORMULA: Final = "rec.activity_sum.v1"
# POL-053 and the option under which T-CON-11 delivered_quantity_cum is net of returns (L5-3-Q-5).
RETURNED_UNITS_SCOPE: Final = "returns.returned_units_scope"
RESTORE_REMAINING_QUANTITY: Final = "RESTORE_REMAINING_QUANTITY"
REMAINING_FORMULA: Final = "rec.remaining.v1"
SCHEDULED_FORMULA: Final = "rec.scheduled.v1"
AWAITING_FORMULA: Final = "rec.awaiting.v1"
DETERMINISTIC: Final = "DETERMINISTIC"
EVENT_DRIVEN: Final = "EVENT_DRIVEN"
HOLD_TYPES: Final = frozenset({"journal_export", "recognition"})  # 04 E-45 (verbatim)
# Segment measures that restate the obligation's measure since a boundary rather than name a
# second method (ENGINE_SPEC §0.11 AllocationSegment.progress_measure; S06-R-29; S07-R-04).
MEASURE_MARKERS: Final = frozenset({"SSP_DELIVERED", "UNITS_SINCE_BOUNDARY"})
_UNITS_METHODS: Final = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED"})
_QUANTITY_SIGN: Final[Mapping[str, int]] = MappingProxyType(
    {"DELIVERY_RECORDED": 1, "RETURN_RECORDED": -1}
)
_NORMAL: Final = "NORMAL"


@dataclass(frozen=True, slots=True)
class ObligationMeasures:
    """T-CON-11 values of one obligation at the version date (§9.1; S09-R-45 to S09-R-47)."""

    subject_key: str
    as_of: date  # d_v (04 T-CON-11 effective_date)
    allocated_amount: int  # A, minor units; returns-adjusted under REDUCE (S09-R-23)
    progress_ratio: Fraction
    revenue_cum: int
    remaining_allocation: int
    remaining_quantity: Fraction
    scheduled_amount: int
    awaiting_trigger_amount: int
    catch_up_amount: int
    catch_up_cum: int
    catch_up_modification_cum: int
    catch_up_tp_change_cum: int
    catch_up_estimate_cum: int
    satisfaction_status: SatisfactionStatus  # E-22
    satisfied_date: date | None
    hold_types: tuple[str, ...]  # E-45 literals of the holds open at d_v
    delivered_quantity: Fraction  # activity: net units of the new events (CV-64)
    revenue_amount: int  # activity: posted effect of the new events, catch-ups included
    ssp_delivered: Fraction  # activity: net units of the new events × unit SSP
    ssp_delivered_cum: Fraction
    trace_nodes: Mapping[str, str]  # measure -> node id (04 T-CON-11 trace_nodes)
    # Exact revenue at d_v, the posted value plus its rounding residue; None for an adjusted target
    # (L1-3-Q-17). Stage 10 reads it for the exact position_obligation (S10-R-12; ENC-12).
    revenue_cum_exact: Fraction | None = None
    # round(r × (Y + E)) at d_v that ``allocated_amount`` nets under REDUCE with a return path, else
    # None (S09-R-23). The version memo is −Σ of it, so 04 DB-17 V1 holds (S04-R-08; L5-3-Q-1).
    returns_reduction: int | None = None


@dataclass(frozen=True, slots=True)
class _Parts:
    """Values the version-date nodes record beside the measures themselves."""

    allocated_fixed: int  # A of the FIXED component, minor units
    realised_in_target: int  # realised PERIOD_VC amounts inside revenue_cum, minor units
    pattern: str  # DETERMINISTIC | EVENT_DRIVEN
    held: bool
    remaining_exact: Fraction | None  # x_k − E(d_v), currency units (Table 0.9-A)
    total_quantity: Fraction  # Q′ of the segment in force
    # DG-KRN-EXP-01 version-state and activity nodes (lane ENG-T1F; D-97 (8)).
    x_fixed: Fraction = Fraction(0)  # X of the FIXED segment in force, net of the returns reduction
    realised: int = 0  # realised PERIOD_VC amounts in the allocation, minor units
    segment: AllocationSegment | None = None
    quantity_events: tuple[tuple[EventView, Fraction, Fraction], ...] = ()  # (event, units, SSP)
    revenue_effects: tuple[_Effect, ...] = ()  # the admitted new events with BOTH endpoints
    delivered_cum: Fraction = Fraction(0)  # T-CON-11 delivered_quantity_cum under POL-053
    returned_cum: Fraction = Fraction(0)
    events: tuple[EventView, ...] = ()  # the version's events (ENG-06), for the latest-event ids


@dataclass(frozen=True, slots=True)
class _Effect:
    """One admitted event of the version's revenue activity (CV-64): the event and its two ENG-06
    endpoint evaluations, retained WHOLE (value, exact, guard, adjustments, hold, netting, parts) so
    the exact side is classified per endpoint (T1F-89-1; ENGINE_SPEC CV-64 rev 1.30)."""

    event: EventView
    before: components.Evaluation
    after: components.Evaluation

    @property
    def posted(self) -> int:
        """C_after − C_before, minor units — the posted effect (unchanged)."""
        return self.after.value - self.before.value


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def validate(st: AllocatedState) -> None:
    """S09-INV-07 at stage entry: one recognition method per obligation version (REQ-REC-018).

    The ``FIXED`` segments of an obligation name at most one E-11 method. ``UNITS_SINCE_BOUNDARY``
    and ``SSP_DELIVERED`` restate the measure since a boundary and are not a second method
    (L2-4-Q-1).
    """
    for ob in st.obligations:
        methods = sorted(
            {
                seg.progress_measure
                for seg in ob.segments
                if seg.component == "FIXED" and seg.progress_measure not in MEASURE_MARKERS
            }
        )
        if len(methods) > 1:
            raise _invariant(
                "an obligation version carries two recognition methods",
                ob,
                rule="S09-INV-07",
                methods=",".join(methods),
            )


# Time alone places the amounts of a deterministic ``FIXED`` component (S09-R-45, S09-R-49). The
# predicate stands in ``components``, beside the dispatch of ``segment_target`` that it mirrors and
# for ``evaluation_periods``, which reads it too; this is the stage's public name for it.
is_deterministic = components.is_deterministic


def version_date(st: AllocatedState) -> date:
    """d_v: the latest effective date the version includes (04 T-CON-11 ``effective_date``)."""
    latest = max((ev.effective_date for ev in st.events), default=st.inception_date)
    return max(latest, st.inception_date)


def unit_ssp(seg: AllocationSegment | None) -> Fraction:
    """The unit SSP of a segment (ENGINE_SPEC §0.11); 0 without an SSP resolution (L2-4-Q-4)."""
    return Fraction(0) if seg is None or seg.unit_ssp is None else seg.unit_ssp


def _pattern(ob: ObligationState, evaluation: components.Evaluation, v: date) -> str:
    """``DETERMINISTIC`` while time alone moves the obligation's target at ``v`` (S09-R-45)."""
    if not is_deterministic(ob):
        return EVENT_DRIVEN
    if evaluation.guard == "V5":
        return DETERMINISTIC  # the recognition start is a date, not an event (S09-INV-06)
    if evaluation.guard is not None or evaluation.as_of != v:
        return EVENT_DRIVEN  # V4: a status change comes first (S02-R-03, S02-R-05)
    fixed = evaluation.fixed
    if fixed is None or fixed.progress.params.get("pending") == "true":
        return EVENT_DRIVEN  # a custodial term awaits its bill-and-hold transfer (S09-R-09)
    return DETERMINISTIC


def _allocation(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    evaluator: components.Evaluator,
    seg: AllocationSegment | None,
    v: date,
) -> tuple[int, Fraction]:
    """A and X of the ``FIXED`` component at ``v``; less round(r × (Y + E)) under REDUCE (S09-R-23)
    when the obligation has a return path."""
    if seg is None:
        return 0, Fraction(0)
    path = st.return_paths.get(ob.subject_key)
    if path is None or returns.policy(ctx, st, ob, returns.SCOPE_POLICY) != returns.REDUCE:
        return seg.a_posted, seg.x_exact
    state = returns.return_state(ctx, st, evaluator.contract, ob, seg, v)
    exact = returns.unit_rate(path, ob, v) * (state.Y + state.E)
    posted = returns.reduction_from_state(path, ob, state, v, evaluator.mu)  # S09-R-23; D-91
    return seg.a_posted - posted, seg.x_exact - exact


def _returns_reduction(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    evaluator: components.Evaluator,
    seg: AllocationSegment | None,
    v: date,
) -> int | None:
    """round(r × (Y + E)) that ``_allocation`` netted at d_v under REDUCE with a return path, else
    None (S09-R-23): the ``returns.reduction`` composition stage 15 shares (D-91)."""
    if seg is None or ob.subject_key not in st.return_paths:
        return None
    if returns.policy(ctx, st, ob, returns.SCOPE_POLICY) != returns.REDUCE:
        return None
    return returns.reduction(ctx, st, evaluator.contract, ob, seg, v)


def realised_at(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    v: date,
    evaluation: components.Evaluation | None = None,
) -> int:
    """Realised ``PERIOD_VC`` and ``ROYALTY`` amounts at ``v``: X = A = the amount (S09-R-02).

    Realised royalties count whether or not the licence is satisfied: unrecognised, they await
    their trigger (S09-R-45). ``evaluation`` is the posted evaluation at ``v``, whose royalty part
    carries them; a guarded evaluation carries none, so they are measured here.
    """
    total = 0
    if components.active_segment(ob, "PERIOD_VC", v) is not None:
        realised, _ = components.period_vc_realised(ctx, st, ob, v)
        total += sum(item.amount for item in realised)
    if components.active_segment(ob, "ROYALTY", v) is not None:
        if evaluation is not None and evaluation.royalty is not None:
            total += evaluation.royalty.realised
        else:
            mu = components.minor_unit(ctx)
            total += royalty.target(ctx, st, ob, v, satisfied=False, mu=mu).realised
    return total


def _quantity_events(
    st: AllocatedState, ob: ObligationState, v: date
) -> list[tuple[EventView, Fraction]]:
    """Signed units of every delivery and return of ``ob`` effective on or before ``v``."""
    found: list[tuple[EventView, Fraction]] = []
    for ev in st.measure_events:
        sign = _QUANTITY_SIGN.get(ev.event_type)
        if sign is None or ev.effective_date > v or not progress_events.concerns(ev, ob):
            continue
        found.append((ev, sign * progress_events.quantity(ev, ob)))
    return found


def _revenue_effect_items(
    st: AllocatedState, ob: ObligationState, evaluator: components.Evaluator, v: date
) -> list[_Effect]:
    """The admitted events of the version's revenue activity (CV-64) with BOTH ENG-06 endpoint
    evaluations of each: ``revenue_amount`` is Σ (C_after − C_before) and the
    ``rec.activity_sum.v1`` node cites each posted effect; the exact side (rev 1.30) reads the same
    evaluations' exact targets per endpoint — never a period-end snapshot."""
    boundary_keys = {seg.event_key for seg in ob.segments if seg.event_key is not None}
    found: list[_Effect] = []
    for ev in st.events:
        if not ev.is_new or ev.effective_date > v:
            continue
        if ev.contract_key != ob.contract_key and ev.event_key not in boundary_keys:
            continue
        before = evaluator.posted(ev.effective_date, Position(ev.order_key, inclusive=False))
        after = evaluator.posted(ev.effective_date, Position(ev.order_key, inclusive=True))
        found.append(_Effect(ev, before, after))
    return found


def delivered_quantity_cum(ctx: BookContext, st: AllocatedState, ob: ObligationState) -> Fraction:
    """T-CON-11 ``delivered_quantity_cum`` (D-87 L5-3-Q-5; 606-10-55-23, 55-27): delivered less
    returned only when the obligation's resolved POL-053 is ``RESTORE_REMAINING_QUANTITY``, else
    gross delivered. POL-053 is the return path's value, else the book's, as stage 09 reads it
    (S04-R-08b); an obligation with no return needs no resolution. The assembler publishes the
    column from this function and stage 09 emits its node (DG-KRN-EXP-01)."""
    point = st.ledger.at(ob.subject_key)
    if point.returned_cum == 0:
        return point.delivered_cum
    path = st.return_paths.get(ob.subject_key)
    scope: object = None if path is None else path.policy.get(RETURNED_UNITS_SCOPE)
    if scope is None:
        scope = ctx.policies.value(
            RETURNED_UNITS_SCOPE,
            contract=ob.contract_key,
            obligation=ob.subject_key,
            entity=ob.performing_entity,
        )
    if scope == RESTORE_REMAINING_QUANTITY:
        return point.delivered_cum - point.returned_cum
    return point.delivered_cum


def _open_hold_types(st: AllocatedState, ob: ObligationState, v: date) -> tuple[str, ...]:
    """E-45 types of the holds on ``ob`` or its contract open at ``v`` (S09-R-42, S09-R-44)."""
    released = {
        ev.payload.get("hold_id")
        for ev in st.measure_events
        if ev.event_type == "HOLD_RELEASED"
        and ev.effective_date <= v
        and ev.contract_key == ob.contract_key
    }
    found: set[str] = set()
    for ev in st.measure_events:
        if ev.event_type != "HOLD_APPLIED" or ev.effective_date > v:
            continue
        if ev.contract_key != ob.contract_key or ev.event_key in released:
            continue
        if ev.payload.get("obligation_key") not in (None, "", ob.obligation_key):
            continue
        hold_type = ev.payload.get("hold_type")
        if not isinstance(hold_type, str) or hold_type not in HOLD_TYPES:
            raise _invariant(
                "a hold carries an unknown hold type", ob, rule="CV-45", event_key=ev.event_key
            )
        found.add(hold_type)
    return tuple(sorted(found))


def _complete(evaluator: components.Evaluator, d: date) -> bool:
    evaluation = evaluator.segments(d)
    return evaluation.guard is None and evaluation.fixed is not None and evaluation.fixed.complete


def _candidate_dates(
    st: AllocatedState, ob: ObligationState, evaluator: components.Evaluator, v: date
) -> list[date]:
    """Dates on or before ``v`` at which progress can change: events, boundaries, term ends,
    period ends and the day a return window ends (E = 0 from the window end; D-87 L6-5-Q-25)."""
    found = {
        v,
        *(seg.effective_date for seg in ob.segments),
        *(ev.effective_date for ev in st.events),
    }
    found.update(period.end_date for period in evaluator.periods)
    for end in (ob.end_date, *(seg.totals.end_date for seg in ob.segments)):
        if end is not None:
            found.add(end)
    path = st.return_paths.get(ob.subject_key)
    if path is not None:
        found.update(pin.window_end_date for pin in path.pins if pin.window_end_date is not None)
    return sorted(d for d in found if d <= v)


def _satisfaction(
    st: AllocatedState,
    ob: ObligationState,
    evaluator: components.Evaluator,
    seg: AllocationSegment | None,
    revenue: int,
    v: date,
) -> tuple[SatisfactionStatus, date | None, Fraction]:
    """(status, satisfied date, f) at ``v`` (S09-R-46)."""
    evaluation = evaluator.segments(v)
    fixed = None if evaluation.guard is not None else evaluation.fixed
    progress = Fraction(0) if fixed is None else fixed.progress.value
    terminated = ob.terminated_on is not None and ob.terminated_on <= v
    if terminated or (seg is not None and seg.cause == SegmentCause.TERMINATION):
        return SatisfactionStatus.CANCELLED, None, progress  # S06-R-21 removed the remainder
    if fixed is not None and fixed.complete:
        first = v
        for d in reversed(_candidate_dates(st, ob, evaluator, v)):
            if not _complete(evaluator, d):
                break
            first = d
        return SatisfactionStatus.SATISFIED, first, progress
    if revenue == 0 and progress == 0:
        return SatisfactionStatus.UNSATISFIED, None, progress
    return SatisfactionStatus.PARTIALLY_SATISFIED, None, progress


def obligation_measures(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    v: date,
    *,
    evaluator: components.Evaluator | None = None,
    boundaries: Sequence[decompose.CausePoint] | None = None,
    tb: TraceBuilder | None = None,
    emitted: set[str] | None = None,
) -> ObligationMeasures:
    """T-CON-11 measures of ``ob`` at the version date ``v`` (§9.2.13; S09-R-45 to S09-R-47).

    With ``tb`` the version-date nodes are emitted: the ``revenue_cum`` chain at ``-``, then
    ``remaining_allocation``, ``remaining_quantity``, ``scheduled_amount`` and
    ``awaiting_trigger_amount`` (§9.5). ``trace_nodes`` names them with the catch-up nodes that
    stage 09 emits at ``-``. A negative term while A ≥ 0 raises ``ENGINE_INVARIANT_VIOLATED``
    naming S09-INV-03 (DG-ENG-05).
    """
    evaluator = components.Evaluator(ctx, st, ob) if evaluator is None else evaluator
    if boundaries is None:
        boundaries = decompose.boundary_points(
            st,
            ob,
            segments=evaluator.segment_value,
            cited=decompose.cited_posted(tb, evaluator.mu),
            exacts=evaluator.segment_exact,
        )
    evaluation = evaluator.posted(v)
    seg = components.active_segment(ob, "FIXED", v)
    allocated_fixed, x_fixed = _allocation(ctx, st, ob, evaluator, seg, v)
    realised = realised_at(ctx, st, ob, v, evaluation)
    in_target = sum(item.amount for item in evaluation.realised) + (
        0 if evaluation.royalty is None else evaluation.royalty.recognised
    )
    allocated = allocated_fixed + realised
    revenue = evaluation.value
    pattern = _pattern(ob, evaluation, v)
    held = evaluation.hold is not None
    scheduled = 0
    if pattern == DETERMINISTIC and not held:
        scheduled = allocated_fixed - (revenue - in_target)
    remaining = allocated - revenue
    awaiting = remaining - scheduled
    if allocated >= 0 and min(revenue, scheduled, awaiting) < 0:
        raise _invariant(
            "allocated_amount = revenue_cum + scheduled_amount + awaiting_trigger_amount has a "
            "negative term",
            ob,
            rule="S09-INV-03",
            allocated_amount=str(allocated),
            revenue_cum=str(revenue),
            scheduled_amount=str(scheduled),
            awaiting_trigger_amount=str(awaiting),
        )
    remaining_exact: Fraction | None = None
    if not evaluation.adjusted:
        remaining_exact = x_fixed + Fraction(realised, 10**evaluator.mu) - evaluation.exact
    total_quantity = ob.quantity if seg is None else seg.totals.quantity
    remaining_quantity = total_quantity
    if seg is not None:
        remaining_quantity = progress_events.remaining_quantity(
            ctx, st, evaluator.contract, ob, seg, v
        )
    cited = [  # boundary catch-ups and the stage 09 EAC estimate points (S09-R-36)
        point
        for point in boundaries
        if point.cause in decompose.CATCH_UP_MEASURES and point.event.effective_date <= v
    ]
    by_measure = {
        measure: sum(point.delta for point in cited if point.cause == cause)
        for cause, measure in decompose.CATCH_UP_MEASURES.items()
    }
    delivered = ssp_new = ssp_cum = Fraction(0)
    quantity_events: list[tuple[EventView, Fraction, Fraction]] = []
    for ev, quantity in _quantity_events(st, ob, v):
        at = components.active_segment(
            ob, "FIXED", ev.effective_date, st=st, position=Position(ev.order_key, inclusive=True)
        )
        amount = quantity * unit_ssp(at)
        quantity_events.append((ev, quantity, amount))
        ssp_cum += amount
        if ev.is_new:
            delivered += quantity
            ssp_new += amount
    effects = _revenue_effect_items(st, ob, evaluator, v)
    status, satisfied, progress = _satisfaction(st, ob, evaluator, seg, revenue, v)
    measures = ObligationMeasures(
        subject_key=ob.subject_key,
        as_of=v,
        allocated_amount=allocated,
        progress_ratio=progress,
        revenue_cum=revenue,
        remaining_allocation=remaining,
        remaining_quantity=remaining_quantity,
        scheduled_amount=scheduled,
        awaiting_trigger_amount=awaiting,
        catch_up_amount=sum(point.delta for point in cited if point.event.is_new),
        catch_up_cum=sum(by_measure.values()),
        catch_up_modification_cum=by_measure["catch_up_modification_cum"],
        catch_up_tp_change_cum=by_measure["catch_up_tp_change_cum"],
        catch_up_estimate_cum=by_measure["catch_up_estimate_cum"],
        satisfaction_status=status,
        satisfied_date=satisfied,
        hold_types=_open_hold_types(st, ob, v),
        delivered_quantity=delivered,
        revenue_amount=sum(item.posted for item in effects),
        ssp_delivered=ssp_new,
        ssp_delivered_cum=ssp_cum,
        trace_nodes=MappingProxyType({}),
        revenue_cum_exact=None if evaluation.adjusted else evaluation.exact,
        returns_reduction=_returns_reduction(ctx, st, ob, evaluator, seg, v),
    )
    if tb is None:
        return measures
    point = st.ledger.at(ob.subject_key)
    parts = _Parts(
        allocated_fixed,
        in_target,
        pattern,
        held,
        remaining_exact,
        total_quantity,
        x_fixed=x_fixed,
        realised=realised,
        segment=seg,
        quantity_events=tuple(quantity_events),
        revenue_effects=tuple(effects),
        delivered_cum=delivered_quantity_cum(ctx, st, ob),
        returned_cum=point.returned_cum,
        events=tuple(st.events),
    )
    nodes = _emit(
        tb,
        ctx,
        st,
        ob,
        evaluation,
        measures,
        parts,
        set() if emitted is None else emitted,
        evaluator,
    )
    return replace(measures, trace_nodes=nodes)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def _emit(
    tb: TraceBuilder,
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    evaluation: components.Evaluation,
    m: ObligationMeasures,
    parts: _Parts,
    emitted: set[str],
    evaluator: components.Evaluator | None = None,
) -> Mapping[str, str]:
    """Version-date nodes of the obligation measures (§9.5; CV-50)."""
    mu = components.minor_unit(ctx)
    as_of = m.as_of.isoformat()
    if evaluator is not None and evaluator.attribution is not None:
        # The S14-R-25 share nodes at the version date, cited by the netted chain and stage 15.
        step1.emit(tb, ctx, evaluator.attribution, ob, None, m.as_of)
    revenue_node = components.emit_target(tb, ctx, ob, "-", evaluation, emitted, st=st)
    nodes: dict[str, str] = {"revenue_cum": revenue_node}
    # CV-50 rev 1.31 (T1F-LP-PR-1): the version-date progress node always exists — the measured
    # progress of the FIXED component, or the rule-produced unmeasured 0 under a guard / without a
    # FIXED component — and the column links it unconditionally.
    nodes["progress_ratio"] = f"progress_ratio:{ob.subject_key}:-"
    nodes["remaining_allocation"] = tb.node(
        measure="remaining_allocation",
        subject_key=ob.subject_key,
        period_key=None,
        value=m.remaining_allocation,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=REMAINING_FORMULA,
        inputs=[revenue_node],
        params={"allocated": str(m.allocated_amount), "as_of": as_of, "kind": "allocation"},
        exact=parts.remaining_exact,
        narrative_key=_narrative(REMAINING_FORMULA),
    )
    nodes["remaining_quantity"] = tb.node(
        measure="remaining_quantity",
        subject_key=ob.subject_key,
        period_key=None,
        value=m.remaining_quantity,
        currency=None,
        minor_unit=None,
        formula_id=REMAINING_FORMULA,
        inputs=[],
        params={
            "as_of": as_of,
            "consumed": rational_param(parts.total_quantity - m.remaining_quantity),
            "kind": "quantity",
            "quantity": rational_param(parts.total_quantity),
        },
        narrative_key=_narrative(REMAINING_FORMULA),
    )
    nodes["scheduled_amount"] = tb.node(
        measure="scheduled_amount",
        subject_key=ob.subject_key,
        period_key=None,
        value=m.scheduled_amount,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=SCHEDULED_FORMULA,
        inputs=[revenue_node],
        params={
            "allocated": str(parts.allocated_fixed),
            "as_of": as_of,
            "held": "true" if parts.held else "false",
            "pattern": parts.pattern,
            "realised": str(parts.realised_in_target),
        },
        narrative_key=_narrative(SCHEDULED_FORMULA),
    )
    nodes["awaiting_trigger_amount"] = tb.node(
        measure="awaiting_trigger_amount",
        subject_key=ob.subject_key,
        period_key=None,
        value=m.awaiting_trigger_amount,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=AWAITING_FORMULA,
        inputs=[nodes["remaining_allocation"], nodes["scheduled_amount"]],
        params={"as_of": as_of},
        narrative_key=_narrative(AWAITING_FORMULA),
    )
    for measure in (*decompose.CATCH_UP_MEASURES.values(), "catch_up_cum", "catch_up_amount"):
        nodes[measure] = f"{measure}:{ob.subject_key}:-"
    nodes.update(_emit_state_and_activity(tb, ctx, ob, m, parts, mu, as_of))
    return MappingProxyType(dict(sorted(nodes.items())))


def _latest_node(
    tb: TraceBuilder, column: str, ob: ObligationState, events: Sequence[EventView]
) -> str | None:
    """The latest ``<column>@<event>:<ob>:-`` node over the events in ENG-06 order, else the
    inception ``<column>:<ob>:-`` node, else None."""
    for event in sorted(events, key=lambda item: item.order_key, reverse=True):
        for slot in ("returns", "-"):  # the qualified re-measurement before the boundary's own
            node_id = f"{column}@{event.event_key}:{ob.subject_key}:{slot}"
            if tb.value(node_id) is not None:
                return node_id
    inception = f"{column}:{ob.subject_key}:-"
    return inception if tb.value(inception) is not None else None


def _emit_allocation_adjustment(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    m: ObligationMeasures,
    allocation_node: str,
    mu: int,
    as_of: str,
    parts: _Parts,
) -> None:
    """T-CON-11 ``allocation_adjustment`` re-measured at the version date (Codex T1F-R3): when the
    returns-adjusted allocation A (S09-R-23 REDUCE) moves the adjustment away from the latest
    stage 05 / stage 06 node, stage 09 — the stage that computes A — emits
    ``allocation_adjustment@<event>:<ob>:-`` for the latest event the version includes
    (``rec.allocation_adjustment.v1``: the ``allocated_amount`` node less the latest stated-price
    node, or params ``stated_price``); the assembler links the latest node whose value ties. A
    stage 06 node of the same event that already holds the value stands; a differing one (the
    boundary's gross adjustment) makes the netted node take the CV-50 qualifier ``returns`` in the
    period slot (``allocation_adjustment@<event>:<ob>:returns``)."""
    events = parts.events
    stated_posted = round_half_up(ob.stated_price, mu)
    value = m.allocated_amount - stated_posted
    latest = _latest_node(tb, "allocation_adjustment", ob, events)
    if latest is not None:
        held = tb.value(latest)
        if held is not None and to_fraction(held) * 10**mu == value:
            return
    if not events:
        return
    event = max(events, key=lambda item: item.order_key)
    node_id = f"allocation_adjustment@{event.event_key}:{ob.subject_key}:-"
    period_key: str | None = None
    existing = tb.value(node_id)
    if existing is not None:
        # The latest event is itself a boundary whose stage 06 node holds the GROSS adjustment
        # while the returns re-estimate nets the allocation at the version date: the netted node
        # takes the CV-50 qualifier ``returns`` in the period slot (Codex T1F-R3 ruling).
        period_key = "returns"
        if (
            tb.value(f"allocation_adjustment@{event.event_key}:{ob.subject_key}:returns")
            is not None
        ):
            return
    stated_node = _latest_node(tb, "stated_price", ob, events)
    inputs: list[str | SourceRef] = [allocation_node]
    params = {"as_of": as_of, "signs": "+,-"}
    if stated_node is not None:
        inputs.append(stated_node)
    else:
        params = {"as_of": as_of, "signs": "+", "stated_price": str(stated_posted)}
    tb.node(
        measure=f"allocation_adjustment@{event.event_key}",
        subject_key=ob.subject_key,
        period_key=period_key,
        value=value,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=ADJUSTMENT_FORMULA,
        inputs=inputs,
        params={**params, "qualifier": period_key or "-"},
        exact=parts.x_fixed + Fraction(parts.realised, 10**mu) - ob.stated_price,
        narrative_key=_narrative(ADJUSTMENT_FORMULA),
    )


def _segment_lineage(
    tb: TraceBuilder, ob: ObligationState, seg: AllocationSegment | None
) -> list[str]:
    """The allocation node of the segment in force, when one exists: stage 05's
    ``original_allocated_amount`` at inception, else the boundary's ``allocated_amount@<event>``."""
    if seg is None:
        return []
    node_id = (
        f"original_allocated_amount:{ob.subject_key}:-"
        if seg.event_key is None
        else f"allocated_amount@{seg.event_key}:{ob.subject_key}:-"
    )
    return [node_id] if tb.value(node_id) is not None else []


def _emit_state_and_activity(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    m: ObligationMeasures,
    parts: _Parts,
    mu: int,
    as_of: str,
) -> dict[str, str]:
    """Version-state and activity nodes of the T-CON-11 columns stage 09 publishes (DG-KRN-EXP-01;
    ENGINE_SPEC CV-50 links; D-97 (8); lane ENG-T1F): ``allocated_amount`` / ``allocated_exact``
    (``rec.allocation.v1``), ``quantity``, ``unit_ssp`` (absent without one), ``remaining_ssp``
    (``rec.segment_state.v1`` of the FIXED segment in force), ``delivered_quantity``,
    ``delivered_quantity_cum``, ``returned_quantity_cum``, ``ssp_delivered``, ``ssp_delivered_cum``
    and ``revenue_amount`` (``rec.activity_sum.v1`` citing every event with its signed value)."""
    nodes: dict[str, str] = {}
    scale: int = 10**mu
    lineage = _segment_lineage(tb, ob, parts.segment)
    exact = parts.x_fixed + Fraction(parts.realised, scale)
    nodes["allocated_amount"] = tb.node(
        measure="allocated_amount",
        subject_key=ob.subject_key,
        period_key=None,
        value=m.allocated_amount,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=ALLOCATION_FORMULA,
        inputs=lineage,
        params={"allocated": str(m.allocated_amount), "as_of": as_of, "kind": "posted"},
        exact=exact,
        narrative_key=_narrative(ALLOCATION_FORMULA),
    )
    nodes["allocated_exact"] = tb.node(
        measure="allocated_exact",
        subject_key=ob.subject_key,
        period_key=None,
        value=exact,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=ALLOCATION_FORMULA,
        inputs=lineage,
        params={"as_of": as_of, "exact": rational_param(exact), "kind": "exact"},
        narrative_key=_narrative(ALLOCATION_FORMULA),
    )
    _emit_allocation_adjustment(tb, ctx, ob, m, nodes["allocated_amount"], mu, as_of, parts)
    seg = parts.segment
    members: list[tuple[str, Fraction | None]] = [
        ("quantity", ob.quantity),  # T-CON-11: the contracted quantity after modifications
        ("unit_ssp", None if seg is None else seg.unit_ssp),
        ("remaining_ssp", Fraction(0) if seg is None else seg.remaining_ssp),
    ]
    for member, value in members:
        if value is None:
            continue
        nodes[member] = tb.node(
            measure=member,
            subject_key=ob.subject_key,
            period_key=None,
            value=value,
            currency=ctx.txn_currency if member != "quantity" else None,
            minor_unit=None,
            formula_id=SEGMENT_STATE_FORMULA,
            inputs=lineage,
            params={"as_of": as_of, "member": member, "value": rational_param(value)},
            narrative_key=_narrative(SEGMENT_STATE_FORMULA),
        )

    def source(ev: EventView, value: Fraction, role: str) -> SourceRef:
        # ``role`` names the event's contribution (a derived per-event value, not a canonical
        # payload member; ENGINE_SPEC CV-53).
        detail = {"role": role, "value": format_exact(value)}
        return SourceRef("contract_event", ev.event_key, detail)

    def activity(
        measure: str,
        items: Sequence[tuple[EventView, Fraction]],
        role: str,
        *,
        posted: bool,
        exact: Fraction | None = None,
        extra: Mapping[str, str] | None = None,
    ) -> None:
        total = sum((value for _, value in items), Fraction(0))
        nodes[measure] = tb.node(
            measure=measure,
            subject_key=ob.subject_key,
            period_key=None,
            value=(total * scale).numerator if posted else total,
            currency=ctx.txn_currency
            if measure != "delivered_quantity" and "quantity" not in measure
            else None,
            minor_unit=mu if posted else None,
            formula_id=ACTIVITY_FORMULA,
            inputs=[source(ev, value, role) for ev, value in items],
            params={"as_of": as_of, "role": role, **(extra or {})},
            exact=exact if posted else None,
            narrative_key=_narrative(ACTIVITY_FORMULA),
        )

    new_units = [(ev, q) for ev, q, _ in parts.quantity_events if ev.is_new]
    activity("delivered_quantity", new_units, "quantity", posted=False)
    activity(
        "ssp_delivered",
        [(ev, a) for ev, _, a in parts.quantity_events if ev.is_new],
        "ssp_delivered",
        posted=False,
    )
    activity(
        "ssp_delivered_cum",
        [(ev, a) for ev, _, a in parts.quantity_events],
        "ssp_delivered",
        posted=False,
    )
    returned = [(ev, -q) for ev, q, _ in parts.quantity_events if q < 0]
    activity("returned_quantity_cum", returned, "quantity", posted=False)
    gross = [(ev, q) for ev, q, _ in parts.quantity_events if q > 0]
    net_of_returns = parts.delivered_cum != sum((q for _, q in gross), Fraction(0))
    activity(
        "delivered_quantity_cum",
        [(ev, q) for ev, q, _ in parts.quantity_events] if net_of_returns else gross,
        "quantity",
        posted=False,
    )
    # CV-64 rev 1.30 (T1F-89-1): the exact revenue activity — its own endpoint / delta / companion
    # chain — bound as the posted node's exact and named in params; unavailable by name otherwise.
    exact_total, extra = _emit_exact_activity(tb, ctx, ob, as_of, parts.revenue_effects, mu)
    activity(
        "revenue_amount",
        [(item.event, Fraction(item.posted, scale)) for item in parts.revenue_effects],
        "revenue_amount",
        posted=True,
        exact=exact_total,
        extra=extra,
    )
    return nodes


EXACT_ENDPOINT_FORMULA: Final = "rec.exact_endpoint.v1"
EXACT_DIFFERENCE_FORMULA: Final = "rec.exact_difference.v1"
EXACT_ACTIVITY_FORMULA: Final = "rec.exact_activity.v1"


def _endpoint_unavailable(x: components.Evaluation) -> str | None:
    """Why the exact target at one ENG-06 endpoint has no authored exact provenance (CV-64 rev
    1.30): an adjusted target — a manual adjustment, a hold's frozen level, the S02-R-04 netting —
    is defined in posted units and has no exact counterpart (the segment exact is never
    substituted); a returns target or a ROYALTY component has an exact chain this emitter does not
    author. None when the endpoint's exact is the evaluation's own ``exact``."""
    if x.adjustments:
        return "adjusted:manual-adjustment"
    if x.hold is not None:
        return "adjusted:hold"
    if x.netting is not None:
        return "adjusted:netting"
    if x.guard is None:
        if x.fixed is not None and x.fixed.returns is not None:
            return "unauthored:returns-target"
        if x.royalty is not None:
            return "unauthored:royalty-component"
    return None


def _emit_endpoint(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    event_key: str,
    side: str,
    x: components.Evaluation,
    mu: int,
) -> str:
    """The exact endpoint chain of one admitted event's ``side`` (CV-64 rev 1.30), from the retained
    evaluation: a guarded endpoint is the defined 0 with its guard named; otherwise the endpoint
    progress node (the production progress formula and params at that position), the ``FIXED``
    exact endpoint through the production ``rec.target_exact.*`` formula (raw params), the admitted
    realised amounts as money sources, and the endpoint sum — every id qualified by event and side,
    never a fiscal-period label. Returns the endpoint sum node id."""
    as_of = x.as_of.isoformat()
    measure = f"revenue_exact_{side}@{event_key}"
    common = {"as_of": as_of, "event": event_key, "side": side}
    if x.guard is not None:
        return tb.node(
            measure=measure,
            subject_key=ob.subject_key,
            period_key=None,
            value=Fraction(0),
            currency=ctx.txn_currency,
            minor_unit=None,
            formula_id=EXACT_ENDPOINT_FORMULA,
            inputs=[],
            params={**common, "guard": x.guard},
            narrative_key=_narrative(EXACT_ENDPOINT_FORMULA),
        )
    inputs: list[str | SourceRef] = []
    if x.fixed is not None:
        fixed = x.fixed
        seg = fixed.segment
        progress_id = tb.node(
            measure=f"progress_ratio_{side}@{event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=fixed.progress.value,
            currency=None,
            minor_unit=None,
            formula_id=fixed.progress.formula_id,
            inputs=[],
            params=fixed.progress.params,
            narrative_key=fixed.progress.formula_id.rsplit(".v", 1)[0],
        )
        exact_params = {
            "as_of": as_of,
            "progress": rational_param(fixed.progress.value),
            "x_exact": rational_param(seg.x_exact),
        }
        exact_formula = components.INCEPTION_EXACT_FORMULA
        if seg.basis == "PROSPECTIVE":
            exact_formula = components.PROSPECTIVE_EXACT_FORMULA
            exact_params["base_revenue_exact"] = rational_param(seg.base_revenue_exact)
        if fixed.materials is not None:  # S09-R-14 zero-margin materials (D-76)
            exact_formula = progress_inputs.UNINSTALLED_FORMULA
            exact_params.update(fixed.materials.params())
        inputs.append(
            tb.node(
                measure=f"revenue_target_exact_{side}@{event_key}",
                subject_key=f"{ob.subject_key}#FIXED",
                period_key=None,
                value=fixed.exact,
                currency=None,
                minor_unit=None,
                formula_id=exact_formula,
                inputs=[progress_id],
                params=exact_params,
                narrative_key=exact_formula.rsplit(".v", 1)[0],
            )
        )
    for item in x.realised:
        inputs.append(
            SourceRef(
                "contract_event",
                item.event_key,
                {"member": "rated_amount", "value": format_money(item.amount, mu)},
            )
        )
    return tb.node(
        measure=measure,
        subject_key=ob.subject_key,
        period_key=None,
        value=x.exact,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=EXACT_ENDPOINT_FORMULA,
        inputs=inputs,
        params={**common, "exact": rational_param(x.exact)},
        narrative_key=_narrative(EXACT_ENDPOINT_FORMULA),
    )


def _emit_exact_activity(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    as_of: str,
    effects: Sequence[_Effect],
    mu: int,
) -> tuple[Fraction | None, dict[str, str]]:
    """The exact revenue activity of the version (CV-64 rev 1.30; T1F-89-1): BOTH endpoints of EVERY
    admitted event are classified first — one unavailable endpoint (adjusted target; unauthored
    chain) makes the whole activity UNAVAILABLE by name (``exact_basis``; no chain emitted, no
    residue, never posted-as-exact); otherwise the endpoint chains, one ``revenue_exact_delta@``
    per event (after − before, raw operands bound) and the companion ``revenue_amount_exact``
    (Σ deltas, multiplicity preserved; the defined 0 without admitted events) are emitted and
    (A_major, {exact_node}) is returned for the posted node's exact and link."""
    for item in effects:
        for side, x in (("before", item.before), ("after", item.after)):
            reason = _endpoint_unavailable(x)
            if reason is not None:
                return None, {"exact_basis": f"unavailable: {reason} {item.event.event_key} {side}"}
    delta_ids: list[str] = []
    total = Fraction(0)
    for item in effects:
        before_id = _emit_endpoint(tb, ctx, ob, item.event.event_key, "before", item.before, mu)
        after_id = _emit_endpoint(tb, ctx, ob, item.event.event_key, "after", item.after, mu)
        delta = item.after.exact - item.before.exact
        total += delta
        delta_ids.append(
            tb.node(
                measure=f"revenue_exact_delta@{item.event.event_key}",
                subject_key=ob.subject_key,
                period_key=None,
                value=delta,
                currency=ctx.txn_currency,
                minor_unit=None,
                formula_id=EXACT_DIFFERENCE_FORMULA,
                inputs=[after_id, before_id],
                params={
                    "event": item.event.event_key,
                    "after": rational_param(item.after.exact),
                    "before": rational_param(item.before.exact),
                },
                narrative_key=_narrative(EXACT_DIFFERENCE_FORMULA),
            )
        )
    companion = tb.node(
        measure="revenue_amount_exact",
        subject_key=ob.subject_key,
        period_key=None,
        value=total,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=EXACT_ACTIVITY_FORMULA,
        inputs=delta_ids,
        params={"as_of": as_of, "exact": rational_param(total), "events": str(len(effects))},
        narrative_key=_narrative(EXACT_ACTIVITY_FORMULA),
    )
    return total, {"exact_node": companion}


def revenue_schedule(
    st: AllocatedState,
    ob: ObligationState,
    evaluator: components.Evaluator,
    targets: Sequence[Target],
    causes: Sequence[Target],
) -> tuple[ScheduleLineOut, ...]:
    """``build_revenue_schedule`` of §9.2.14: the ``REVENUE`` lines of one obligation (S09-R-48).

    One line per (subject key, schedule kind, line type, period key) with a non-zero amount through
    the last evaluated period: the period containing the term end of a deterministic component, else
    the horizon (S09-R-50). ``cumulative_exact`` is the running amount of a line type other than
    ``NORMAL``; the ``NORMAL`` line takes the exact target less those, so the line types sum to the
    exact target (L2-4-Q-5). ``quantity`` is the net units transferred in the period under a units
    measure. ``is_released_at_close`` marks the ``NORMAL`` line of a deterministic pattern in a
    period whose realised ``PERIOD_VC`` amount did not move (S09-R-49). The lines sum to the last
    target (S09-INV-04).
    """
    scale: int = 10**evaluator.mu
    periods = {period.period_key: period for period in evaluator.periods}
    grouped: dict[str, list[Target]] = {}
    for cause in causes:
        grouped.setdefault(cause.period_key, []).append(cause)
    last_end = max((periods[t.period_key].end_date for t in targets), default=st.inception_date)
    units = str(ob.recognition_method) in _UNITS_METHODS
    events = _quantity_events(st, ob, last_end) if units else []
    cumulative: dict[str, int] = {}
    lines: list[ScheduleLineOut] = []
    previous_realised = 0
    for target in targets:
        period = periods[target.period_key]
        realised = sum(item.amount for item in evaluator.segments(period.end_date).realised)
        realised_moved = realised != previous_realised
        previous_realised = realised
        found = sorted(grouped.get(target.period_key, ()), key=lambda item: str(item.cause))
        for item in found:
            cumulative[str(item.cause)] = cumulative.get(str(item.cause), 0) + item.value
        exact = Fraction(target.value, scale) if target.exact is None else target.exact
        others = sum(amount for line_type, amount in cumulative.items() if line_type != _NORMAL)
        for item in found:
            line_type = str(item.cause)
            if item.value == 0:
                continue
            normal = line_type == _NORMAL
            quantity: Fraction | None = None
            if normal and units:
                quantity = sum(
                    (
                        q
                        for ev, q in events
                        if period.start_date <= ev.effective_date <= period.end_date
                    ),
                    Fraction(0),
                )
            lines.append(
                ScheduleLineOut(
                    schedule_kind=ScheduleKind.REVENUE,
                    subject_type="obligation",
                    subject_key=ob.subject_key,
                    entity=ob.performing_entity,
                    period_key=target.period_key,
                    line_type=ScheduleLineType(line_type),
                    amount=item.value,
                    cumulative_amount=cumulative[line_type],
                    cumulative_exact=(
                        exact - Fraction(others, scale)
                        if normal
                        else Fraction(cumulative[line_type], scale)
                    ),
                    quantity=quantity,
                    is_released_at_close=normal and is_deterministic(ob) and not realised_moved,
                    trace_node_id=item.node_id,
                )
            )
    final = targets[-1].value if targets else 0
    if sum(line.amount for line in lines) != final:
        raise _invariant("the schedule lines do not sum to the last target", ob, rule="S09-INV-04")
    return tuple(lines)


def _emit_fixed_schedule(
    ctx: BookContext,
    tb: TraceBuilder,
    evaluator: components.Evaluator,
    targets: Sequence[Target],
    causes: Sequence[Target],
) -> None:
    """Separate fixed schedule portions using the engine's component/cause evidence.

    Manual adjustments, holds and Step-1 netting do not supply a component attribution;
    omit their projections so a dated reader refuses instead of assigning them by ratio.
    """
    ob = evaluator.ob
    if not any(seg.component in ("PERIOD_VC", "ROYALTY") for seg in ob.segments):
        return
    periods = {period.period_key: period for period in evaluator.periods}
    previous: components.Evaluation | None = None
    previous_usage: str | None = None
    for target in targets:
        ev = evaluator.posted(periods[target.period_key].end_date)
        usage = sum(item.amount for item in ev.realised)
        usage_node = tb.node(
            measure="period_vc_revenue_cum",
            subject_key=ob.subject_key,
            period_key=target.period_key,
            value=usage,
            currency=ctx.txn_currency,
            minor_unit=evaluator.mu,
            formula_id=PERIOD_VC_FORMULA,
            inputs=[
                SourceRef(
                    "contract_event",
                    item.event_key,
                    {"member": "rated_amount", "value": format_money(item.amount, evaluator.mu)},
                )
                for item in ev.realised
            ],
            params={"cause": "PERIOD_VC", "as_of": ev.as_of.isoformat()},
            narrative_key=_narrative(PERIOD_VC_FORMULA),
        )
        readable = (
            ev.guard is None
            and not ev.adjusted
            and (previous is None or (previous.guard is None and not previous.adjusted))
        )
        if readable:
            old_usage = 0 if previous is None else sum(item.amount for item in previous.realised)
            for cause in causes:
                if cause.period_key != target.period_key:
                    continue
                inputs = [cause.node_id]
                signs = ["+"]
                value = cause.value
                if cause.cause == "NORMAL":
                    value -= usage - old_usage
                    inputs.append(usage_node)
                    signs.append("-")
                    if previous_usage is not None:
                        inputs.append(previous_usage)
                        signs.append("+")
                elif cause.cause == "ROYALTY":
                    value = 0
                    inputs.append(cause.node_id)
                    signs.append("-")
                tb.node(
                    measure="scheduled_fixed_amount",
                    subject_key=ob.subject_key,
                    period_key=f"{target.period_key}@{cause.cause}",
                    value=value,
                    currency=ctx.txn_currency,
                    minor_unit=evaluator.mu,
                    formula_id=FIXED_SCHEDULE_FORMULA,
                    inputs=inputs,
                    params={
                        "cause": "FIXED_SCHEDULE",
                        "signs": ",".join(signs),
                        "as_of": ev.as_of.isoformat(),
                        "source_node": cause.node_id,
                    },
                    narrative_key=_narrative(FIXED_SCHEDULE_FORMULA),
                )
        previous, previous_usage = ev, usage_node


def _emit_realised_allocation(
    ctx: BookContext,
    st: AllocatedState,
    tb: TraceBuilder,
    evaluator: components.Evaluator,
    targets: Sequence[Target],
    version_day: date,
) -> None:
    """Persist realization separately from fixed allocation and recognized revenue.

    Revenue cannot stand in for this amount: a royalty or usage fee can remain
    unrecognized under a satisfaction condition or recognition hold. Use the same
    dated realization calculation as the obligation state and disclosure stage.
    Zero period points are retained so earlier report cuts have explicit evidence.
    """
    ob = evaluator.ob
    dated = any(seg.component in ("PERIOD_VC", "ROYALTY") for seg in ob.segments)
    period_ends = {period.period_key: period.end_date for period in evaluator.periods}
    points: list[tuple[str | None, date, tuple[str, ...]]] = [
        (target.period_key, period_ends[target.period_key], (target.node_id,))
        for target in targets
        if dated
    ]
    points.append((None, version_day, tuple(target.node_id for target in targets)))
    for period_key, day, inputs in points:
        value = realised_at(ctx, st, ob, day, evaluator.posted(day))
        tb.node(
            measure="realised_allocation",
            subject_key=ob.subject_key,
            period_key=period_key,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=evaluator.mu,
            formula_id=REALISED_FORMULA,
            inputs=inputs,
            params={
                "allocated": str(value),
                "as_of": day.isoformat(),
                "kind": "posted",
                "realisation_mode": "DATED" if dated else "NONE",
            },
            narrative_key=_narrative(REALISED_FORMULA),
        )


def build(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder, result: components.StageTargets
) -> tuple[tuple[ScheduleLineOut, ...], Mapping[str, ObligationMeasures]]:
    """Schedule lines and obligation measures of every obligation with targets (§9.1)."""
    v = version_date(st)
    emitted = set(result.emitted)
    targets: dict[str, list[Target]] = {}
    for target in result.revenue_targets:
        targets.setdefault(target.subject_key, []).append(target)
    causes: dict[str, list[Target]] = {}
    for cause in result.revenue_by_cause:
        causes.setdefault(cause.subject_key, []).append(cause)
    lines: list[ScheduleLineOut] = []
    measures: dict[str, ObligationMeasures] = {}
    for subject_key in sorted(result.evaluators):
        evaluator = result.evaluators[subject_key]
        ob = evaluator.ob
        _emit_realised_allocation(ctx, st, tb, evaluator, targets.get(subject_key, ()), v)
        _emit_fixed_schedule(
            ctx, tb, evaluator, targets.get(subject_key, ()), causes.get(subject_key, ())
        )
        lines.extend(
            revenue_schedule(
                st, ob, evaluator, targets.get(subject_key, ()), causes.get(subject_key, ())
            )
        )
        boundaries = decompose.boundary_points(
            st, ob, segments=evaluator.segment_value, cited=decompose.cited_posted(tb, evaluator.mu)
        )
        measures[subject_key] = obligation_measures(
            ctx, st, ob, v, evaluator=evaluator, boundaries=boundaries, tb=tb, emitted=emitted
        )
    return tuple(lines), MappingProxyType(measures)
