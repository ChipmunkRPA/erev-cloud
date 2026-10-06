"""Stage 09 sequential cause decomposition of a period amount (ENGINE_SPEC_B §9.2.10; ENC-9).

A period amount C_t − C_(t−1) is split by E-28 line type over the events effective within the
period in ENG-06 order (S09-R-35). A boundary event that creates a segment of the obligation
contributes C_after(d) − C_before(d) of the segment targets at its position, which is the stage 06
or stage 08 node ``catch_up@<event key>:<ob>:-`` (S06-R-17; CV-50): that node is cited, and the
cause node sums the nodes it cites (S09-R-36). ``RETURN_RECORDED`` and a ``RETURN_RATE`` version
applied to a returnable obligation contribute the posted target after the event less before it,
carried by a source reference. An ``ESTIMATE_CHANGED`` that applies an ``EAC`` version to an
input-measured obligation adds no segment (S08-R-02), so stage 09 measures its own delta at the
event position, cause ``CATCH_UP``, carried by a source reference (S09-R-16, S09-R-36; ENC-5).
Every other effect, including time, progress, manual adjustments, holds and window expiry, is
``NORMAL``, which is the remainder, so the decomposition sums exactly to the period amount
(S09-INV-04). The catch-up disclosure measures of REQ-MOD-015 sum the boundary and estimate
catch-ups by cause (Table 0.9-A). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput, PeriodInput
from erev_engine.errors import EngineError
from erev_engine.stages.s09_recognition import progress_events, progress_inputs
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "BOUNDARY_TYPES",
    "CATCH_UP_FORMULA",
    "CATCH_UP_MEASURES",
    "CAUSE_OF_ESTIMATE_KIND",
    "CAUSE_OF_EVENT",
    "CausePoint",
    "ComponentCause",
    "DECOMPOSE_FORMULA",
    "boundary_points",
    "catch_up_node_id",
    "emit",
    "emit_catch_up_measures",
    "estimate_points",
    "event_cause",
    "measures_eac",
    "points",
    "sequential",
]

DECOMPOSE_FORMULA: Final = "rec.decompose.sequential.v1"
CATCH_UP_FORMULA: Final = "rec.catch_up.sum.v1"
NORMAL: Final = "NORMAL"
CAUSE_OF_EVENT: Final[Mapping[str, str]] = MappingProxyType(
    {  # E-03 literal -> E-28 line type (§9.2.10)
        "DELIVERY_RECORDED": "NORMAL",
        "PROGRESS_RECORDED": "NORMAL",
        "MILESTONE_ACHIEVED": "NORMAL",
        "COST_INCURRED": "NORMAL",
        "USAGE_REPORTED": "NORMAL",
        "HOLD_RELEASED": "NORMAL",
        "HOLD_APPLIED": "NORMAL",
        "MANUAL_ADJUSTMENT_APPLIED": "NORMAL",
        "MATERIAL_RIGHT_EXPIRED": "NORMAL",
        "BILLING_RECORDED": "NORMAL",
        "CREDIT_MEMO_RECORDED": "NORMAL",
        "CONTRACT_CRITERIA_MET": "NORMAL",
        "CONTRACT_AMENDED": "MODIFICATION",
        "CONTRACT_TERMINATED": "MODIFICATION",
        "REGROUPED": "MODIFICATION",
        "COMBINATION_CHANGED": "MODIFICATION",
        "MATERIAL_RIGHT_EXERCISED": "MODIFICATION",
        "RETURN_RECORDED": "RETURN",
        "OPENING_BALANCE_ESTABLISHED": "OPENING_BALANCE",
    }
)
CAUSE_OF_ESTIMATE_KIND: Final[Mapping[str, str]] = MappingProxyType(
    {  # ESTIMATE_CHANGED by E-09 kind (§9.2.10)
        "VARIABLE_CONSIDERATION": "TP_CHANGE",
        "IMPLICIT_PRICE_CONCESSION": "TP_CHANGE",
        "EXPECTED_PURCHASES": "TP_CHANGE",
        "EXERCISE_LIKELIHOOD": "TP_CHANGE",
        "RETURN_RATE": "RETURN",
        "EAC": "CATCH_UP",
        "BREAKAGE": "BREAKAGE",
        "ROYALTY_ACCRUAL": "ROYALTY",
        "RENEWAL_EXPECTATION": "CATCH_UP",
    }
)
# Table 0.3-A boundaries whose handlers publish catch_up@<event key> nodes (stages 06 and 08).
CATCH_UP_HANDLER_TYPES: Final = frozenset(
    {
        "CONTRACT_AMENDED",
        "CONTRACT_TERMINATED",
        "REGROUPED",
        "LINE_ATTRIBUTES_CHANGED",
        "MATERIAL_RIGHT_EXERCISED",
        "ESTIMATE_CHANGED",
    }
)
BOUNDARY_TYPES: Final = CATCH_UP_HANDLER_TYPES | {
    "COLLECTIBILITY_ASSESSED",
    "CONTRACT_CRITERIA_MET",
    "SIGNIFICANT_CHANGE_FLAGGED",
    "OPENING_BALANCE_ESTABLISHED",
    "CONTRACT_BOOKED",
}
CATCH_UP_MEASURES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "MODIFICATION": "catch_up_modification_cum",
        "TP_CHANGE": "catch_up_tp_change_cum",
        "CATCH_UP": "catch_up_estimate_cum",
    }
)

Target_fn = Callable[[date, Position], int]
Exact_fn = Callable[[date, Position], Fraction]  # the exact segment target, currency units
# The posted value, minor units, of a catch_up@ node the builder holds, else None (S09-R-36).
Cited_fn = Callable[[str], int | None]


def cited_posted(tb: TraceBuilder | None, mu: int) -> Cited_fn:
    """The reader of the posted ``catch_up@<event key>`` values the stage 06 and stage 08 handlers
    published in ``tb``. S09-R-36: a boundary's delta is that node, cited and never recomputed, so
    the cause and catch-up nodes reproduce under ``reevaluate`` even where stage 06 measures time
    on the close of d − 1 (EX-09-A) and stage 09's target at d does not move (D-88 L7-5-Q-13)."""

    def read(node_id: str) -> int | None:
        encoded = None if tb is None else tb.value(node_id)
        if encoded is None:
            return None
        scale: int = 10**mu
        scaled = money.to_fraction(encoded) * scale
        if scaled.denominator != 1:
            raise ValueError(f"catch-up node {node_id} is not posted at minor unit {mu}")
        numerator: int = scaled.numerator
        return numerator

    return read


@dataclass(frozen=True, slots=True)
class CausePoint:
    """The effect of one event on the obligation's target (§9.2.10 ``decompose``)."""

    event: EventView
    cause: str  # E-28 line type
    delta: int  # minor units
    catch_up_node: str | None  # the stage 06 or stage 08 node cited, if any
    exact: Fraction | None = None  # E_after − E_before of a stage 09 estimate point (S09-R-36)


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def catch_up_node_id(event_key: str, subject_key: str) -> str:
    """``catch_up@<event key>:<obligation>:-`` of stages 06 and 08 (CV-50)."""
    return f"catch_up@{event_key}:{subject_key}:-"


def _estimate_version(
    st: AllocatedState, ob: ObligationState, ev: EventView
) -> EstimateVersionInput:
    for pins in st.estimates.pins.values():
        for pin in pins:
            if pin.event_order_key == ev.order_key:
                return pin.version
    raise _invariant(
        "the estimate version of an estimate change is absent",
        ob,
        rule="S09-R-35",
        event_key=ev.event_key,
    )


def _estimate_kind(st: AllocatedState, ob: ObligationState, ev: EventView) -> str:
    return _estimate_version(st, ob, ev).estimate_kind


def measures_eac(st: AllocatedState, ob: ObligationState, ev: EventView) -> bool:
    """The event applies an ``EAC`` version of the element measuring an input-measured obligation
    (S09-R-14 to S09-R-16): a measure-only kind, so no segment marks it (S08-R-02)."""
    if str(ob.recognition_method) not in progress_inputs.INPUT_METHODS:
        return False
    version = _estimate_version(st, ob, ev)
    if version.estimate_kind != "EAC":
        return False
    return version.estimate_key in progress_inputs.eac_keys(st, ob)


def estimate_points(
    st: AllocatedState,
    ob: ObligationState,
    *,
    segments: Target_fn,
    exacts: Exact_fn | None = None,
) -> tuple[CausePoint, ...]:
    """Every ``EAC`` estimate change of an input-measured obligation with a non-zero effect, in
    ENG-06 order: cause ``CATCH_UP``, delta C_after(d) − C_before(d) of the segment targets at the
    event position, no cited node (S08-R-02; S09-R-16; S09-R-36)."""
    boundaries = {seg.event_key for seg in ob.segments if seg.event_key is not None}
    found: list[CausePoint] = []
    for ev in st.events:
        if ev.event_type != "ESTIMATE_CHANGED" or ev.event_key in boundaries:
            continue
        if not measures_eac(st, ob, ev):
            continue
        before_position = Position(ev.order_key, inclusive=False)
        after_position = Position(ev.order_key, inclusive=True)
        before = segments(ev.effective_date, before_position)
        after = segments(ev.effective_date, after_position)
        if after == before:
            continue
        exact: Fraction | None = None
        if exacts is not None:
            exact = exacts(ev.effective_date, after_position) - exacts(
                ev.effective_date, before_position
            )
        found.append(CausePoint(ev, "CATCH_UP", after - before, None, exact))
    return tuple(found)


def event_cause(st: AllocatedState, ob: ObligationState, ev: EventView) -> str:
    """``component_cause`` of S09-R-35 for the segment and measure components built in 1.0-rc.

    A ``LINE_ATTRIBUTES_CHANGED`` boundary, handled by stage 06 and absent from the table, is a
    ``MODIFICATION`` (L1-3-Q-16).
    """
    if ev.event_type == "ESTIMATE_CHANGED":
        kind = _estimate_kind(st, ob, ev)
        cause = CAUSE_OF_ESTIMATE_KIND.get(kind)
        if cause is None:
            raise _invariant("an estimate kind has no cause", ob, rule="S09-R-35", kind=kind)
        return cause
    if ev.event_type == "LINE_ATTRIBUTES_CHANGED":
        return "MODIFICATION"
    return CAUSE_OF_EVENT.get(ev.event_type, NORMAL)


def _boundary_events(st: AllocatedState, ob: ObligationState) -> list[EventView]:
    keys = {seg.event_key for seg in ob.segments if seg.event_key is not None}
    found = [ev for ev in st.events if ev.event_key in keys]
    if len(found) != len(keys):
        raise _invariant("the boundary event of a segment is absent", ob, rule="CV-60")
    return found


def _segment_point(
    st: AllocatedState,
    ob: ObligationState,
    ev: EventView,
    segments: Target_fn,
    cited: Cited_fn | None = None,
) -> CausePoint | None:
    cause = event_cause(st, ob, ev)
    if cause == NORMAL:
        return None
    node = catch_up_node_id(ev.event_key, ob.subject_key)
    handled = ev.event_type in CATCH_UP_HANDLER_TYPES
    published = cited(node) if handled and cited is not None else None
    if published is not None:
        return CausePoint(ev, cause, published, node)  # S09-R-36: cited, never recomputed
    before = segments(ev.effective_date, Position(ev.order_key, inclusive=False))
    after = segments(ev.effective_date, Position(ev.order_key, inclusive=True))
    return CausePoint(ev, cause, after - before, node if handled else None)


def boundary_points(
    st: AllocatedState,
    ob: ObligationState,
    *,
    segments: Target_fn,
    cited: Cited_fn | None = None,
    exacts: Exact_fn | None = None,
) -> tuple[CausePoint, ...]:
    """Every boundary of the obligation with a cause other than ``NORMAL`` and every ``EAC``
    estimate point (``estimate_points``), ENG-06 order.

    With ``cited`` a boundary whose ``catch_up@`` node the builder holds takes that node's posted
    value as its delta (S09-R-36); otherwise C_after(d) − C_before(d) of the segment targets."""
    found = [_segment_point(st, ob, ev, segments, cited) for ev in _boundary_events(st, ob)]
    found.extend(estimate_points(st, ob, segments=segments, exacts=exacts))
    return tuple(
        sorted(
            (point for point in found if point is not None), key=lambda point: point.event.order_key
        )
    )


def points(
    st: AllocatedState,
    ob: ObligationState,
    period: PeriodInput,
    *,
    posted: Target_fn,
    segments: Target_fn,
    cited: Cited_fn | None = None,
) -> tuple[CausePoint, ...]:
    """The events of ``period`` whose effect is not ``NORMAL``, in ENG-06 order (S09-R-35); a
    boundary takes its cited catch-up node's posted value when ``cited`` holds it (S09-R-36)."""
    boundaries = {ev.event_key for ev in _boundary_events(st, ob)}
    path = st.return_paths.get(ob.subject_key)
    return_versions = (
        set()
        if path is None
        else {pin.event_order_key for pin in st.estimates.pins.get(path.estimate_key, ())}
    )
    found: list[CausePoint] = []
    for ev in st.events:
        if not period.start_date <= ev.effective_date <= period.end_date:
            continue
        if ev.event_key in boundaries:
            point = _segment_point(st, ob, ev, segments, cited)
            if point is not None:
                found.append(point)
            continue
        if ev.event_type == "ESTIMATE_CHANGED" and ev.order_key in return_versions:
            cause = "RETURN"
        elif ev.event_type == "ESTIMATE_CHANGED" and measures_eac(st, ob, ev):
            before = segments(ev.effective_date, Position(ev.order_key, inclusive=False))
            after = segments(ev.effective_date, Position(ev.order_key, inclusive=True))
            if after != before:  # S09-R-16: the EAC change posts as a CATCH_UP
                found.append(CausePoint(ev, "CATCH_UP", after - before, None))
            continue
        elif ev.event_type not in BOUNDARY_TYPES and progress_events.concerns(ev, ob):
            cause = CAUSE_OF_EVENT.get(ev.event_type, NORMAL)
            if cause == NORMAL:
                continue
        else:
            continue
        before = posted(ev.effective_date, Position(ev.order_key, inclusive=False))
        after = posted(ev.effective_date, Position(ev.order_key, inclusive=True))
        found.append(CausePoint(ev, cause, after - before, None))
    return tuple(found)


@dataclass(frozen=True, slots=True)
class ComponentCause:
    """A cause carried by a recognition component rather than by events (S09-R-35): the
    ``BREAKAGE`` part of a redemption obligation or the ``ROYALTY`` component. Its period amount
    is the difference of the component's cumulative nodes, which the cause node cites."""

    cause: str  # BREAKAGE | ROYALTY
    delta: int  # minor units
    nodes: tuple[str, ...]  # the component node of the period and, when one exists, the previous


def sequential(
    previous: int,
    current: int,
    found: Sequence[CausePoint],
    components: Sequence[ComponentCause] = (),
) -> dict[str, int]:
    """The period amount by line type, non-zero amounts only (§9.2.10 ``decompose``).

    Σ over line types = ``current`` − ``previous`` exactly (S09-INV-04; PRD J-16-AC-1). A cause
    named by ``components`` takes the component's own delta, whatever the event (S09-R-35), and
    event points of that cause are not counted again.
    """
    carried = {item.cause for item in components}
    out: dict[str, int] = {}
    for point in found:
        if point.cause != NORMAL and point.cause not in carried:
            out[point.cause] = out.get(point.cause, 0) + point.delta
    for item in components:
        out[item.cause] = out.get(item.cause, 0) + item.delta
    out[NORMAL] = current - previous - sum(out.values())
    return {cause: out[cause] for cause in sorted(out) if out[cause] != 0}


def _delta_ref(point: CausePoint, mu: int) -> str | SourceRef:
    if point.catch_up_node is not None:
        return point.catch_up_node
    value = money.format_money(point.delta, mu)
    return SourceRef(
        "contract_event", point.event.event_key, {"member": "revenue_delta", "value": value}
    )


def emit(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    period_key: str,
    *,
    as_of: date,
    mu: int,
    current_node: str,
    previous_node: str | None,
    found: Sequence[CausePoint],
    amounts: Mapping[str, int],
    components: Sequence[ComponentCause] = (),
) -> tuple[Target, ...]:
    """``revenue_by_cause:<ob>/<line type>:<period>`` nodes and ``revenue`` targets (§9.5).

    A component cause cites the component's cumulative nodes instead of event deltas (S09-R-35).
    """
    carried = {item.cause: item for item in components}
    targets: list[Target] = []
    cause_nodes: list[str] = []
    for cause in sorted(amounts):
        if cause == NORMAL:
            continue
        inputs: list[str | SourceRef]
        signs: str | None = None
        if cause in carried:
            # The period's component node less the previous period's (S09-R-35).
            inputs = list(carried[cause].nodes)
            signs = ",".join(["+", *("-" for _ in inputs[1:])])
        else:
            inputs = [_delta_ref(point, mu) for point in found if point.cause == cause]
        cause_nodes.append(
            _node(tb, ctx, ob, period_key, cause, amounts[cause], inputs, as_of, mu, signs=signs)
        )
    if NORMAL in amounts:
        normal_inputs: list[str | SourceRef] = [current_node]
        params_previous = "false"
        if previous_node is not None:
            normal_inputs.append(previous_node)
            params_previous = "true"
        normal_inputs.extend(cause_nodes)
        node_id = _node(
            tb,
            ctx,
            ob,
            period_key,
            NORMAL,
            amounts[NORMAL],
            normal_inputs,
            as_of,
            mu,
            params_previous,
        )
        cause_nodes.append(node_id)
    for node_id in sorted(cause_nodes):
        cause = node_id.split(":", 2)[1].rsplit("/", 1)[1]
        targets.append(
            Target(
                book_code=ctx.book_code,
                entity=ob.performing_entity,
                subject_key=ob.subject_key,
                measure="revenue",
                period_key=period_key,
                cause=cause,
                value=amounts[cause],
                exact=None,
                node_id=node_id,
            )
        )
    return tuple(targets)


def _node(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    period_key: str,
    cause: str,
    amount: int,
    inputs: Sequence[str | SourceRef],
    as_of: date,
    mu: int,
    previous: str | None = None,
    signs: str | None = None,
) -> str:
    params = {"as_of": as_of.isoformat(), "cause": cause}
    if previous is not None:
        params["previous"] = previous
    if signs is not None:
        params["signs"] = signs
    return tb.node(
        measure="revenue_by_cause",
        subject_key=f"{ob.subject_key}/{cause}",
        period_key=period_key,
        value=amount,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=DECOMPOSE_FORMULA,
        inputs=inputs,
        params=params,
        narrative_key=DECOMPOSE_FORMULA.rsplit(".v", 1)[0],
    )


def emit_catch_up_measures(
    tb: TraceBuilder,
    ctx: BookContext,
    ob: ObligationState,
    boundaries: Sequence[CausePoint],
    *,
    as_of: date,
    mu: int,
) -> Mapping[str, str]:
    """``catch_up_*_cum``, ``catch_up_cum`` and ``catch_up_amount`` version-state nodes (S09-R-36).

    Each sums the ``catch_up@`` nodes of the boundaries effective on or before ``as_of`` with its
    cause, and the ``EAC`` estimate points of stage 09 by source reference (``estimate_points``);
    ``catch_up_amount`` sums those of the events first included in the version
    (``EventView.is_new``; Table 0.9-A). The posted value is Σ CU_posted, and the exact value is Σ
    CU_exact, the exact values of the cited nodes or of the estimate points (Table 0.9-A;
    S09-R-36; DG-OQ-05). A cited node that this builder does not hold contributes its posted
    amount.
    """
    cited = [
        point
        for point in boundaries
        if point.cause in CATCH_UP_MEASURES and point.event.effective_date <= as_of
    ]
    ids: dict[str, str] = {}
    amounts: dict[str, int] = {}
    exacts: dict[str, Fraction] = {}

    def cited_exact(point: CausePoint) -> Fraction:
        if point.catch_up_node is None:
            return Fraction(point.delta, 10**mu) if point.exact is None else point.exact
        found = tb.exact(point.catch_up_node)
        return Fraction(point.delta, 10**mu) if found is None else found

    def sum_node(measure: str, items: Sequence[CausePoint], nodes: Sequence[str] = ()) -> str:
        inputs: list[str | SourceRef] = [_delta_ref(point, mu) for point in items]
        exact = sum((cited_exact(point) for point in items), Fraction(0))
        exact += sum((exacts[node] for node in nodes), Fraction(0))
        inputs.extend(nodes)
        value = sum(point.delta for point in items) + sum(amounts[node] for node in nodes)
        node_id = tb.node(
            measure=measure,
            subject_key=ob.subject_key,
            period_key=None,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=CATCH_UP_FORMULA,
            inputs=inputs,
            params={"as_of": as_of.isoformat()},
            exact=exact,
            narrative_key=CATCH_UP_FORMULA.rsplit(".v", 1)[0],
        )
        amounts[node_id] = value
        exacts[node_id] = exact
        return node_id

    for cause, measure in CATCH_UP_MEASURES.items():
        ids[measure] = sum_node(measure, [point for point in cited if point.cause == cause])
    ids["catch_up_cum"] = sum_node(
        "catch_up_cum", (), [ids[measure] for measure in CATCH_UP_MEASURES.values()]
    )
    ids["catch_up_amount"] = sum_node(
        "catch_up_amount", [point for point in cited if point.event.is_new]
    )
    return MappingProxyType(ids)
