"""Install prospective allocation segments for a reviewed contract split boundary.

The caller retains the complete original state and separately persists effective membership.
This kernel changes future allocations only; it does not perform database membership changes.
"""

from dataclasses import replace
from fractions import Fraction

from erev_engine.combination_membership import membership_at, validate_partition
from erev_engine.combination_split import SplitBasis
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import boundary_state, pool, segments, weights
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    Finding,
)
from erev_engine.trace import TraceBuilder


def install(
    ctx: BookContext,
    state: AllocatedState,
    event: EventView,
    plan: SplitBasis,
    identified: IdentifiedState,
    trace: TraceBuilder,
) -> AllocatedState:
    """Recheck native boundary measurements and dated weights before installing a plan.

    Keep every earlier segment, original quantity, price, billing plan and recognition ledger.
    The new segment starts at original posted revenue and recognizes only the assigned
    remainder over the remaining service. Redistribution is not a price concession/refund.
    """
    if (plan.book_code, plan.currency, plan.effective_date) != (
        ctx.book_code,
        ctx.txn_currency,
        event.effective_date,
    ):
        raise ValueError("Split plan differs from the calculation boundary")
    if plan.boundary_event_key is not None and plan.boundary_event_key != event.event_key:
        raise ValueError("Split plan names a different original boundary event")
    destinations = {member.contract_key: member.destination for member in plan.members}
    if len(destinations) != len(plan.members):
        raise ValueError("Split plan repeats an original member")
    current = membership_at(
        state.group_code,
        (c.header.external_id for c in state.contracts),
        state.events,
        before_event=event.order_key,
    )
    source_group = validate_partition(current, destinations)
    if event.contract_key not in destinations:
        raise ValueError("A split event must belong to the group being split")
    originals = {
        obligation_subject_key(member.contract_key, row.obligation_key): row
        for member in plan.members
        for row in member.original
    }
    if len(originals) != sum(len(m.original) for m in plan.members) or set(originals) != {
        o.subject_key for o in state.obligations if o.contract_key in destinations
    }:
        raise ValueError("Split plan must retain every original obligation exactly once")
    if any(
        segment.event_key == event.event_key for ob in state.obligations for segment in ob.segments
    ):
        raise ValueError("The split allocation boundary is already installed")
    if len({m.destination for m in plan.members}) < 2:
        raise ValueError("A split requires at least two destinations")
    befores = {}
    selected = {}
    for ob in state.obligations:
        if ob.contract_key not in destinations:
            continue
        if ob.scope_flag != "IN_SCOPE_606" or (
            not ctx.specialist_split_continuation
            and (
                ob.principal_agent != "PRINCIPAL"
                or ob.performing_entity != ob.contracting_entity
                or ob.opening is not None
                or ob.combined_component_keys
                or ob.material_right is not None
                or ob.is_vc_line
                or ob.recognition_method not in {"TIME_ELAPSED", "UNITS_DELIVERED"}
            )
        ):
            raise ValueError(
                "Split application needs a supported original fixed-service obligation"
            )
        row = originals[ob.subject_key]
        segment = segments.in_force(state, ob, event)
        if segment is None or (
            not ctx.specialist_split_continuation
            and any(s.component != "FIXED" for s in ob.segments)
        ):
            raise ValueError("Split allocation requires a complete fixed-service basis")
        from erev_engine.separation import measure, remaining_weight

        before = (
            measure(ctx, state, ob, segment, event)
            if ctx.specialist_split_continuation
            else segments.measure(ctx, state, ob, segment, event)
        )
        if (
            segment.a_posted,
            before.posted,
            before.remaining_quantity,
            segment.x_exact,
            before.exact,
        ) != (
            row.allocation_minor,
            row.recognized_minor,
            row.remaining_quantity,
            row.allocation_exact,
            row.recognized_exact,
        ):
            raise ValueError("Split source measurement changed; rebuild its allocation")
        findings: list[Finding] = []
        weight = (
            None
            if before.progress == 1
            else remaining_weight(ctx, state, identified, ob, before, event, findings)
            if ctx.specialist_split_continuation
            else weights.existing(
                ctx, identified, ob, before, (), event, None, findings, state=state
            )
        )
        if before.progress != 1 and (
            weight is None or any(f.severity == "ERROR" for f in findings)
        ):
            raise ValueError("Split remaining SSP cannot be resolved")
        value = Fraction(0) if weight is None else weight.value
        if (
            value != row.remaining_ssp
            or (() if weight is None else weight.sources) != row.remaining_ssp_sources
        ):
            raise ValueError("Split remaining SSP changed; rebuild its allocation")
        befores[ob.subject_key], selected[ob.subject_key] = before, value
    mu = segments.minor_unit(ctx)
    group_pool = pool.Pool(
        source_group,
        tuple(
            pool.Member(key, before.segment.a_posted - originals[key].retained_minor, before.posted)
            for key, before in sorted(befores.items())
        ),
        0,
        0,
        0,
    )
    if group_pool.posted + sum(
        row.retained_minor for row in originals.values()
    ) != plan.unrecognized_minor or sum(b.posted for b in befores.values()) != sum(
        row.recognized_minor for row in originals.values()
    ):
        raise ValueError("Split totals differ from the original boundary")
    member_weights = [
        (
            m.contract_key,
            sum(
                (
                    selected[obligation_subject_key(m.contract_key, r.obligation_key)]
                    for r in m.original
                ),
                Fraction(0),
            ),
        )
        for m in plan.members
    ]
    expected = pool.preview(group_pool, member_weights, mu)
    if group_pool.posted and not sum((w for _, w in member_weights), Fraction(0)):
        raise ValueError("Nonzero split consideration requires remaining SSP")
    for member in plan.members:
        if (
            expected[member.contract_key][0] + sum(r.retained_minor for r in member.original)
            != member.remaining_after_minor
        ):
            raise ValueError("Split member allocation differs from remaining SSP")
    # The group pool is preserved; member adjustments below are internal allocation transfers.
    # Group and contract natural keys can coincide. Reserve a distinct group-pool
    # measure namespace instead of treating a contract key as an obligation subject.
    pool.emit(
        ctx,
        trace,
        replace(event, event_key=f"{event.event_key}~split-group"),
        group_pool,
        mu,
        {"basis": "PROSPECTIVE_COMBINATION_SPLIT", "source_event": event.event_key},
    )
    changed = {}
    for member in plan.members:
        keys = sorted(
            obligation_subject_key(member.contract_key, r.obligation_key) for r in member.original
        )
        old_remaining = sum(
            befores[key].segment.a_posted - befores[key].posted - originals[key].retained_minor
            for key in keys
        )
        member_pool = pool.Pool(
            member.contract_key,
            tuple(
                pool.Member(
                    key,
                    befores[key].segment.a_posted - originals[key].retained_minor,
                    befores[key].posted,
                )
                for key in keys
            ),
            expected[member.contract_key][0] - old_remaining,
            0,
            0,
        )
        ordered = [(key, selected[key]) for key in keys]
        shares_before = pool.preview(member_pool, ordered, mu)
        if {
            r.obligation_key: shares_before[
                obligation_subject_key(member.contract_key, r.obligation_key)
            ][0]
            + r.retained_minor
            for r in member.original
        } != dict(member.obligation_shares):
            raise ValueError("Split obligation allocation differs from remaining SSP")
        node = pool.emit(ctx, trace, event, member_pool, mu, {"basis": "SPLIT_ALLOCATION_TRANSFER"})
        shares = pool.apportion(ctx, trace, event, member_pool, node, ordered, mu)
        for ob in state.obligations:
            if ob.subject_key not in shares:
                continue
            before, share = befores[ob.subject_key], shares[ob.subject_key]
            reserve = originals[ob.subject_key].retained_minor
            if reserve and before.progress == 1 and share.posted == 0:
                continue
            boundary = segments.prospective(
                ctx,
                event,
                before=before,
                x_exact=Fraction(before.posted + reserve, 10**mu) + share.exact,
                a_posted=before.posted + reserve + share.posted,
                totals=replace(before.segment.totals, quantity=before.remaining_quantity),
                progress_measure=before.segment.progress_measure,
                weight=selected[ob.subject_key],
                billing_plan=before.segment.remaining_billing_plan,
                boundary_no=before.segment.modification_boundary_no + 1,
            )
            from erev_engine.stages.s09_recognition.breakage import applies

            if ctx.specialist_split_continuation and (
                ob.subject_key in state.return_paths or applies(ob)
            ):
                boundary = replace(
                    boundary,
                    separation_source_index=next(
                        i for i, s in enumerate(ob.segments) if s is before.segment
                    ),
                    separation_event_key=event.event_key,
                    totals=before.segment.totals,
                )
            changed[ob.subject_key] = replace(ob, segments=(*ob.segments, boundary))
    result = replace(
        state, obligations=tuple(changed.get(ob.subject_key, ob) for ob in state.obligations)
    )
    for ob in result.obligations:
        if ob.subject_key not in changed:
            continue
        before = befores[ob.subject_key]
        after = (
            measure(ctx, result, ob, ob.segments[-1], event)
            if ctx.specialist_split_continuation
            else segments.measure(ctx, result, ob, ob.segments[-1], event)
        )
        if after.posted != before.posted:
            raise ValueError("A prospective split cannot change previously recognized revenue")
        segments.emit_catch_up(
            ctx,
            trace,
            event,
            ob.subject_key,
            before=before,
            after=after,
            share_node=f"mod_share@{event.event_key}:{ob.subject_key}:-",
            base=before.posted + originals[ob.subject_key].retained_minor,
            extra={"retained_historical_amount": str(originals[ob.subject_key].retained_minor)},
        )
    boundary_state.emit(ctx, trace, state, result, event)
    return result
