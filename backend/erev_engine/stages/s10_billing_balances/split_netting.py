"""Effective destination netting within the original calculation envelope."""

from collections.abc import Sequence
from dataclasses import fields, replace
from typing import TYPE_CHECKING

from erev_engine.combination_membership import membership_at
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    group_entity_subject_key,
)
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances.billing import Billed
from erev_engine.stages.s10_billing_balances.position import latest_target, series
from erev_engine.stages.state import BookContext, ObligationState, Target
from erev_engine.trace import TraceBuilder

if TYPE_CHECKING:
    from erev_engine.stages.s10_billing_balances.reclass import _Point


def points(
    ctx: BookContext,
    recognition: RecognitionState,
    billed: Billed,
    own: Sequence[ObligationState],
    point: "_Point",
    trace: TraceBuilder,
) -> list[tuple[Sequence[ObligationState], "_Point"]]:
    """Retain pre-split points; partition supported same-currency fixed service thereafter."""
    state = recognition.allocated
    if not ctx.prospective_split_netting or not any(
        e.event_type == "COMBINATION_CHANGED"
        and "prospective_split_destinations" in e.payload
        and e.effective_date <= point.period.end_date
        for e in state.events
    ):
        return [(own, point)]
    if (
        ctx.entities[point.parts.entity].functional_currency != ctx.txn_currency
        or any(
            (
                point.parts.deposit_transferred,
                point.parts.noncash_unconditional,
                point.parts.interest_expense,
                point.parts.interest_income,
                point.parts.receivable_contra,
                point.parts.refund_liability,
            )
        )
        or state.estimates.pins
        or state.return_paths
        or state.refund_components
        or any(getattr(state.specialist_targets, f.name) for f in fields(state.specialist_targets))
        or any(
            ob.opening is not None
            or ob.material_right is not None
            or ob.combined_component_keys
            or ob.principal_agent != "PRINCIPAL"
            or ob.performing_entity != ob.contracting_entity
            or ob.scope_flag != "IN_SCOPE_606"
            or ob.recognition_method not in {"TIME_ELAPSED", "UNITS_DELIVERED"}
            or any(s.component != "FIXED" for s in ob.segments)
            for ob in state.obligations
        )
    ):
        raise ValueError(
            "Split posting requires same-currency fixed-service destination continuation"
        )
    groups = membership_at(
        state.group_code,
        (c.header.external_id for c in state.contracts),
        state.events,
        effective_date=point.period.end_date,
    )
    destinations = sorted({groups[ob.contract_key] for ob in own})
    if len(destinations) == 1:
        return [(own, point)]
    billings = {
        (t.subject_key, t.period_key): t
        for t in billed.targets
        if t.measure == "billed_unconditional_cum"
    }
    revenues = series(ctx, recognition.revenue_targets)
    result: list[tuple[Sequence[ObligationState], _Point]] = []
    for destination in destinations:
        selected = [ob for ob in own if groups[ob.contract_key] == destination]
        inputs, signs = [], []
        b = r = 0
        for member in sorted({ob.contract_key for ob in selected}):
            target = billings.get(
                (contract_entity_subject_key(member, point.parts.entity), point.period.period_key)
            )
            if target is not None:
                b += target.value
                inputs.append(target.node_id)
                signs.append("+")
        for ob in selected:
            target = latest_target(
                revenues.get(("revenue_cum", ob.subject_key), ()), point.period.end_date
            )
            if target is not None:
                r += target.value
                inputs.append(target.node_id)
                signs.append("-")
        subject = group_entity_subject_key(
            f"{state.group_code}/split/{destination}", point.parts.entity
        )
        node = trace.node(
            measure="net_position",
            subject_key=subject,
            period_key=point.period.period_key,
            value=b - r,
            currency=ctx.txn_currency,
            minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
            formula_id="pos.net_position.v1",
            inputs=inputs,
            params={
                "as_of": point.period.end_date.isoformat(),
                "signs": "|".join(signs),
                "destination": destination,
                "members": "|".join(sorted({ob.contract_key for ob in selected})),
            },
            narrative_key="pos.net_position",
        )
        parts = replace(
            point.parts,
            subject_key=subject,
            net_position=b - r,
            billed_unconditional=b,
            revenue_relief=r,
            node_id=node,
        )
        result.append((selected, replace(point, parts=parts)))
    if sum(p.parts.net_position for _, p in result) != point.parts.net_position:
        raise ValueError("Destination net positions do not reconcile with the original envelope")
    return result


def aggregate(
    ctx: BookContext,
    own: Sequence[ObligationState],
    original: "_Point",
    targets: Sequence[Target],
    trace: TraceBuilder,
) -> list[Target]:
    """Envelope totals are sums of independently netted destinations, never renetted."""
    result = []
    for measure in ("contract_liability", "contract_asset", "unbilled_receivable"):
        parts = [t for t in targets if t.measure == measure]
        value = sum(t.value for t in parts)
        subject = original.parts.subject_key
        name = (
            f"group_{measure}"
            if any(
                contract_entity_subject_key(ob.contract_key, original.parts.entity) == subject
                for ob in own
            )
            else measure
        )
        node = trace.node(
            measure=name,
            subject_key=subject,
            period_key=original.period.period_key,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
            formula_id="rec.activity_sum.v1",
            inputs=[t.node_id for t in parts],
            params={"signs": ",".join("+" for _ in parts)},
            narrative_key="rec.activity_sum",
        )
        result.append(replace(parts[0], subject_key=subject, value=value, node_id=node))
    return result
