"""Current contract assets retain each member's original reclassification shares."""

from collections.abc import Sequence
from dataclasses import replace

from erev_engine import dates
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s10_billing_balances.current_split import CURRENT_POLICY, NONE
from erev_engine.stages.s10_billing_balances.reclass import Presentation
from erev_engine.stages.state import AllocatedState, BookContext, Target
from erev_engine.trace import TraceBuilder


def measure(
    ctx: BookContext,
    state: AllocatedState,
    presentation: Presentation,
    current: Sequence[Target],
    trace: TraceBuilder,
) -> tuple[Target, ...]:
    result = []
    for group in current:
        if group.measure != "contract_asset_current":
            continue
        end = next(
            p.end_date
            for p in ctx.entities[group.entity].periods
            if p.period_key == group.period_key
        )
        horizon = dates.add_months(end, 12)
        enabled = (
            ctx.policies.value(CURRENT_POLICY, entity=group.entity, period=group.period_key) != NONE
        )
        eligible = (
            {
                ob.subject_key
                for ob in state.obligations
                if ob.contracting_entity == group.entity
                and (ob.end_date is None or ob.end_date <= horizon)
            }
            if enabled
            else set()
        )
        group_sum = 0
        for total in presentation.members:
            if (total.entity, total.period_key, total.measure) != (
                group.entity,
                group.period_key,
                "contract_asset",
            ):
                continue
            parts = [
                p
                for p in presentation.reclass
                if p.subject_key in eligible
                and p.period_key == group.period_key
                and contract_entity_subject_key(p.contract_key, p.entity) == total.subject_key
            ]
            value = sum(p.asset for p in parts)
            if not 0 <= value <= total.value:
                raise ValueError("Member current asset does not reconcile with its total asset")
            node = trace.node(
                measure=group.measure,
                subject_key=total.subject_key,
                period_key=total.period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
                formula_id="pos.current_split.v1",
                inputs=[total.node_id, *(p.node_id for p in parts)],
                params={
                    "mode": "ca",
                    "as_of": end.isoformat(),
                    "horizon": horizon.isoformat(),
                    "keys": "|".join(p.subject_key for p in parts),
                    "parts": "|".join(str(p.asset) for p in parts),
                },
                narrative_key="pos.current_split",
            )
            result.append(replace(total, measure=group.measure, value=value, node_id=node))
            group_sum += value
        if group_sum != group.value:
            raise ValueError("Member current assets do not reconcile with the group current asset")
    return tuple(result)
