"""Carry original returns and redemption recognition across contract-group separation."""

import json
from dataclasses import replace
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING

from erev_engine import money
from erev_engine.separation import measure
from erev_engine.separation_progress import fraction
from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    EventView,
    ObligationState,
)
from erev_engine.trace import SourceRef

if TYPE_CHECKING:
    from erev_engine.stages.s09_recognition.components import FixedPart


def part(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    day: date,
    position: progress_events.Position | None,
) -> "FixedPart":
    from erev_engine.stages.s09_recognition.components import (
        FixedPart,
        SeparationPart,
        segment_target,
    )

    assert seg.separation_source_index is not None
    index = seg.separation_source_index
    if not 0 <= index < len(ob.segments) or ob.segments[index] is seg:
        raise ValueError("Separation has no earlier original component")
    original = ob.segments[index]
    source_ob = replace(ob, segments=ob.segments[: index + 1])
    source = segment_target(ctx, st, contract, source_ob, original, day, position=position)
    boundary = next(e for e in st.events if e.event_key == seg.separation_event_key)
    before = measure(ctx, st, source_ob, original, boundary)
    events, values, refs = [], [], []
    params = {"mode": "RATIO", "base": str(before.progress), "as_of": day.isoformat()}
    original_part = source
    while original_part.continuation is not None:
        original_part = original_part.continuation.source
    expected = original_part.returns.expected if original_part.returns is not None else None
    if ob.subject_key in st.return_paths:
        option = progress_events.control_trigger_option(ctx, ob)
        outcome = progress_events.repurchase_outcome(ctx, contract, ob)
        for event in st.measure_events:
            if (
                event.event_type not in {"DELIVERY_RECORDED", "RETURN_RECORDED"}
                or not progress_events.admitted(event, day, position)
                or not progress_events.concerns(event, ob)
            ):
                continue
            if (
                event.event_type == "DELIVERY_RECORDED"
                and progress_events.hold_reason(
                    ctx, contract, ob, event, option=option, outcome=outcome
                )
                is not None
            ):
                continue
            qty = progress_events.quantity(event, ob)
            events.append((event.event_type, event.order_key > boundary.order_key))
            values.append(qty)
            refs.append(
                SourceRef(
                    "contract_event",
                    event.event_key,
                    {"member": "quantity", "value": money.format_exact(qty)},
                )
            )
        period = next(
            p.period_key
            for p in ctx.entities[ob.contracting_entity].periods
            if p.start_date <= day <= p.end_date
        )
        params.update(
            mode="UNITS",
            policy=str(
                ctx.policies.value(
                    "fx.cl_layer_consumption", entity=ob.contracting_entity, period=period
                )
            ),
            remaining_quantity=str(before.remaining_quantity),
            events=json.dumps(events),
            expected_input=str(expected is not None).lower(),
        )
        if expected is not None:
            values.append(expected.value)
    else:
        values = [source.progress.value]
    progress = fraction(values, params)
    delta = seg.x_exact - original.x_exact
    exact = source.exact + delta * progress
    if not 0 <= exact <= seg.x_exact:
        raise ValueError("Separation continuation exceeds its remaining allocation")
    mu = ctx.currencies[ctx.txn_currency].minor_unit
    posted = (
        money.cumulative_posted(seg.x_exact, seg.a_posted, exact / seg.x_exact, mu)
        if seg.x_exact
        else 0
    )
    continuation = SeparationPart(source, progress, tuple(refs), params, expected)
    return FixedPart(
        seg,
        source.progress,
        exact,
        posted,
        exact == seg.x_exact,
        findings=source.findings,
        redemption=source.redemption,
        continuation=continuation,
    )


def reduction_exact(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    day: date,
    returned: Fraction,
    expected: Fraction,
    position: progress_events.Position | None = None,
) -> Fraction:
    from erev_engine.stages.s09_recognition import returns

    if seg.separation_source_index is None:
        return returns.unit_rate(
            st.return_paths[ob.subject_key], ob, day, st=st, position=position
        ) * (returned + expected)
    source_ob = replace(ob, segments=ob.segments[: seg.separation_source_index + 1])
    original = source_ob.segments[-1]
    baseline = reduction_exact(
        ctx, st, contract, source_ob, original, day, returned, expected, position
    )
    current = part(ctx, st, contract, ob, seg, day, position)
    assert current.continuation is not None
    held = current.continuation
    values = [Fraction(s.detail["value"]) for s in held.sources]
    params = dict(held.params, metric="LOST", expected_input="true")
    values.append(expected)
    return baseline + (seg.x_exact - original.x_exact) * fraction(values, params)


def future_unit_rate(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    event: "EventView",
) -> Fraction:
    """Keep each separation's future-delivery rate separate from earlier deliveries."""
    from erev_engine.stages.s09_recognition import returns

    if seg.separation_source_index is None:
        return returns.unit_rate(
            st.return_paths[ob.subject_key],
            ob,
            event.effective_date,
            st=st,
            position=progress_events.Position(event.order_key, False),
        )
    source_ob = replace(ob, segments=ob.segments[: seg.separation_source_index + 1])
    original = source_ob.segments[-1]
    boundary = next(e for e in st.events if e.event_key == seg.separation_event_key)
    remaining = measure(ctx, st, source_ob, original, boundary).remaining_quantity
    original_rate = future_unit_rate(ctx, st, source_ob, original, boundary)
    delta = seg.x_exact - original.x_exact
    if remaining == 0:
        if delta:
            raise ValueError(
                "Separation cannot allocate consideration without remaining deliveries"
            )
        return original_rate
    return original_rate + delta / remaining
