"""Contract-group separation uses native component measurements, not obligation transfer guards."""

from dataclasses import replace
from datetime import timedelta

from erev_engine import money
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import segments, weights
from erev_engine.stages.s09_recognition import components, progress_events
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    Finding,
    ObligationState,
)


def measure(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    segment: AllocationSegment,
    event: EventView,
) -> segments.Measured:
    when = (
        event.effective_date - timedelta(days=1)
        if segment.progress_measure == "TIME_ELAPSED"
        or (
            ob.recognition_method in {"USAGE", "ROYALTY"} and ob.satisfaction_pattern == "OVER_TIME"
        )
        else event.effective_date
    )
    position = progress_events.Position(event.order_key, False)
    contract = next(c for c in st.contracts if c.header.external_id == ob.contract_key)
    part = components.segment_target(ctx, st, contract, ob, segment, when, position=position)
    if any(f.severity == "ERROR" for f in part.findings):
        raise ValueError("Separation requires a complete original component measurement")
    point = st.ledger.at(ob.subject_key, before=event)
    counts = progress_events.tally(ctx, st, contract, ob, event.effective_date, position)
    delivered = counts.counted - counts.returned
    remaining = segment.totals.quantity
    if segment.progress_measure in segments.UNIT_MEASURES:
        remaining -= delivered - (
            segment.base_progress.delivered_cum if segment.basis == "PROSPECTIVE" else 0
        )
    if ob.subject_key in st.return_paths:
        path = st.return_paths[ob.subject_key]
        completed = (
            counts.counted
            if path.policy.get("returns.returned_units_scope") == "REDUCE_CONTRACT_QUANTITY"
            else delivered
        )
        remaining = ob.quantity - completed
    if remaining < 0:
        raise ValueError("Separation has delivery quantities beyond the retained service")
    point = replace(point, delivered_cum=counts.counted, returned_cum=counts.returned)
    return segments.Measured(
        segment,
        point,
        part.progress.value,
        part.exact,
        part.posted,
        part.complete,
        delivered,
        remaining,
    )


def retained(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    before: segments.Measured,
    event: EventView,
) -> int:
    remaining = before.segment.a_posted - before.posted
    if remaining < 0:
        raise ValueError("Separation cannot allocate negative unrecognized consideration")
    if ob.is_vc_line:
        return remaining
    if ob.subject_key in st.return_paths:
        # Historical expected-return entitlement belongs to its original delivery;
        # only consideration for remaining service joins the SSP redistribution.
        from erev_engine.separation_recognition import future_unit_rate

        capacity = money.round_half_up(
            future_unit_rate(ctx, st, ob, before.segment, event) * before.remaining_quantity,
            segments.minor_unit(ctx),
        )
        return remaining - min(remaining, max(0, capacity))
    return remaining if before.progress == 1 else 0


def remaining_weight(
    ctx: BookContext,
    st: AllocatedState,
    identified: IdentifiedState,
    ob: ObligationState,
    before: segments.Measured,
    event: EventView,
    findings: list[Finding],
) -> weights.Weight | None:
    """Price remaining service, using native measured progress for non-unit methods."""
    from erev_engine.stages.s09_recognition.breakage import applies

    value = weights.existing(ctx, identified, ob, before, (), event, None, findings, state=st)
    if value is None:
        return None
    # Time and delivery methods already price only their remaining term/units. Cost
    # recovery without a reliable EAC supplies no separate performance percentage.
    if before.segment.progress_measure in {
        "COST_TO_COST",
        "LABOUR_HOURS",
        "OUTPUT_PERCENT",
        "MILESTONE",
    } or applies(ob):
        factor = 1 - before.progress
        return replace(
            value,
            value=value.value * factor,
            params={**value.params, "separation_remaining_progress": str(factor)},
        )
    return value
