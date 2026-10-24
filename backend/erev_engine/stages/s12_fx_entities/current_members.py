"""Current liability carrying from the original open FX layers, never a new FX rate."""

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING

from erev_engine.stages.s12_fx_entities.current_layers import classify
from erev_engine.stages.state import BookContext, Target
from erev_engine.trace import TraceBuilder

if TYPE_CHECKING:
    from erev_engine.stages.s12_fx_entities import FxState


def singleton(
    ctx: BookContext,
    fx: "FxState",
    members: Sequence[Target],
    trace: TraceBuilder,
    *,
    grouped: bool = False,
) -> tuple[Target, ...]:
    from erev_engine.stages.s10_billing_balances.current_members import supported

    if (len(fx.allocated.contracts) != 1 and not grouped) or not supported(ctx, fx.allocated):
        return ()
    contract = fx.allocated.contracts[0].header.external_id
    result: list[Target] = []
    for target in members:
        if target.measure != "contract_liability_current":
            continue
        currency = ctx.entities[target.entity].functional_currency
        if currency == ctx.txn_currency:
            continue
        end = next(
            p.end_date
            for p in ctx.entities[target.entity].periods
            if p.period_key == target.period_key
        )
        layers = []
        inputs = [target.node_id]
        for layer in fx.layer_balances:
            if (layer.entity, layer.period_key, layer.balance_role) != (
                target.entity,
                target.period_key,
                "CONTRACT_LIABILITY",
            ):
                continue
            movements = [
                m
                for m in fx.layer_movements
                if m.entity == layer.entity
                and m.layer_key == layer.layer_key
                and m.balance_role == "CONTRACT_LIABILITY"
                and m.effective_date <= end
            ]
            inputs.extend(m.trace_node_id for m in movements)
            layers.append(
                {
                    "layer_key": layer.layer_key,
                    "txn_open": layer.txn_open,
                    "functional_carrying": layer.fn_carrying,
                    "movements": [
                        {
                            "kind": m.movement_kind,
                            "amount_txn": m.amount_txn,
                            "amount_functional": m.amount_functional,
                        }
                        for m in movements
                    ],
                }
            )
        policy = str(
            ctx.policies.value(
                "fx.cl_layer_consumption", entity=target.entity, period=target.period_key
            )
        )
        if grouped:
            policies = {
                ctx.policies.value(
                    "fx.cl_historical_layering",
                    contract=c.header.external_id,
                    entity=target.entity,
                    period=target.period_key,
                )
                for c in fx.allocated.contracts
                if any(
                    ob.contract_key == c.header.external_id
                    and ob.contracting_entity == target.entity
                    for ob in fx.allocated.obligations
                )
            }
            if len(policies) != 1 and target.value and str(ctx.framework) == "ASC606":
                raise ValueError(
                    "Combined current liability requires a consistent historical-layer policy"
                )
        monetary_policy = (
            next(iter(policies))
            if grouped
            else ctx.policies.value(
                "fx.cl_historical_layering",
                contract=contract,
                entity=target.entity,
                period=target.period_key,
            )
        )
        monetary = (
            str(ctx.framework) == "ASC606" and monetary_policy == "DISABLED_REMEASURE_AS_MONETARY"
        )
        unit = ctx.currencies[currency].minor_unit
        parts = classify(layers, target.value, policy=policy, minor_unit=unit, monetary=monetary)
        value = sum(int(p["current_functional"]) for p in parts)
        name = "contract_liability_current_functional"
        node = trace.node(
            measure=name,
            subject_key=target.subject_key,
            period_key=target.period_key,
            value=value,
            currency=currency,
            minor_unit=unit,
            formula_id="fx.functional_member.v1",
            inputs=inputs,
            params={
                "value": str(value),
                "as_of": end.isoformat(),
                "policy": policy,
                "monetary": str(monetary).lower(),
                "layer_allocations": json.dumps(parts, sort_keys=True, separators=(",", ":")),
            },
            narrative_key="fx.functional_member",
        )
        result.append(
            Target(
                ctx.book_code,
                target.entity,
                target.subject_key,
                name,
                target.period_key,
                None,
                value,
                None,
                node,
            )
        )
    return tuple(result)


def combined(
    ctx: BookContext,
    fx: "FxState",
    current: Sequence[Target],
    totals: Sequence[Target],
    trace: TraceBuilder,
) -> tuple[Target, ...]:
    from dataclasses import replace

    from erev_engine.stages.s01_canonicalize import group_entity_subject_key
    from erev_engine.stages.s10_billing_balances.current_members import apportion, supported

    if not supported(ctx, fx.allocated):
        return ()
    groups = tuple(
        replace(
            t,
            subject_key=group_entity_subject_key(
                fx.allocated.group_code + "/current-liability", t.entity
            ),
        )
        for t in current
        if t.measure == "contract_liability_current"
    )
    measured = singleton(ctx, fx, groups, trace, grouped=True)
    result: list[Target] = []
    for target in measured:
        own = [
            t
            for t in totals
            if t.measure == "contract_liability_functional"
            and (t.entity, t.period_key) == (target.entity, target.period_key)
        ]
        carrying = sum(
            layer.fn_carrying
            for layer in fx.layer_balances
            if (layer.entity, layer.period_key, layer.balance_role)
            == (target.entity, target.period_key, "CONTRACT_LIABILITY")
        )
        if sum(t.value for t in own) != carrying:
            raise ValueError("Member liability carrying does not reconcile with original FX layers")
        result.extend(
            apportion(
                ctx,
                target,
                own,
                trace,
                currency=ctx.entities[target.entity].functional_currency,
                measure="contract_liability_current_functional",
            )
        )
    return tuple(result)
