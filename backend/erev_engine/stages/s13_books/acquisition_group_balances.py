"""Original nonposting member observations; shared FX layers stay at group scope."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

from erev_engine.bundle import PeriodInput
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s12_fx_entities.current_layers import classify
from erev_engine.stages.state import BookContext, CanonicalBundle, billing_mode_at
from erev_engine.trace import TraceBuilder


def capture_members(
    ctx: BookContext,
    cb: CanonicalBundle,
    measured: Mapping[str, object],
    evidence: TraceBuilder,
    destination: TraceBuilder,
    entity: str,
    period: PeriodInput,
    cutover: date,
) -> tuple[Mapping[str, object], ...]:
    from erev_engine import _balances, _functional_balances

    from .acquisition_balances import MEASURES

    balances, costs = measured["10"], measured["11"]
    assert isinstance(balances, BalanceState) and isinstance(costs, CostLossState)
    fx = measured.get("12")
    foreign = ctx.entities[entity].functional_currency != ctx.txn_currency
    if foreign:
        assert isinstance(fx, FxState)
        _functional_balances(cb.bundle, balances.allocated, fx, _balances(cb.bundle, balances))
    targets = (*balances.member_balances, *balances.member_sums, *costs.member_sums)
    members = sorted(c.header.external_id for c in balances.allocated.contracts)
    result: list[dict[str, Any]] = []
    shared = []
    for member in members:
        subject = contract_entity_subject_key(member, entity)
        amounts, links, unmeasured = {}, {}, {}
        for name in MEASURES:
            found = [
                t
                for t in targets
                if (t.subject_key, t.entity, t.period_key, t.measure)
                == (subject, entity, period.period_key, name)
            ]
            if (
                not found
                and name == "accounts_receivable"
                and billing_mode_at(ctx.policies, ctx.entities[entity], cutover) == "ERP"
            ):
                amounts[name] = 0
                unmeasured[name] = "ERP_MODE_EXTERNAL_BALANCE"
            elif len(found) != 1:
                return ()
            else:
                amounts[name], links[name] = found[0].value, found[0].node_id
        snapshot: dict[str, Any] = {
            "basis": "ORIGINAL_NONPOSTING_CUTOVER_EVALUATION",
            "member": member,
            "members": members,
            "entity": entity,
            "period_key": period.period_key,
            "as_of": cutover.isoformat(),
            "currency": ctx.txn_currency,
            "minor_unit": ctx.currencies[ctx.txn_currency].minor_unit,
            "amounts": amounts,
            "nodes": links,
            "unmeasured": unmeasured,
        }
        if foreign:
            assert isinstance(fx, FxState)
            own = [
                t
                for t in fx.functional_member_balances
                if (t.subject_key, t.entity, t.period_key) == (subject, entity, period.period_key)
            ]
            fn_amounts = {t.measure.removesuffix("_functional"): t.value for t in own}
            fn_nodes = {t.measure.removesuffix("_functional"): t.node_id for t in own}
            if (
                len(fn_amounts) != len(own)
                or not {
                    "contract_liability",
                    "contract_liability_current",
                    "contract_asset",
                    "contract_asset_current",
                    "unbilled_receivable",
                }
                <= fn_amounts.keys()
            ):
                return ()
            currency = ctx.entities[entity].functional_currency
            snapshot["functional"] = {
                "currency": currency,
                "minor_unit": ctx.currencies[currency].minor_unit,
                "amounts": fn_amounts,
                "nodes": fn_nodes,
            }
            shared.append(
                {
                    "member": member,
                    "amounts": {
                        name: amounts[name]
                        for name in ("contract_liability", "contract_liability_current")
                    },
                    "nodes": {
                        name: links[name]
                        for name in ("contract_liability", "contract_liability_current")
                    },
                    "functional_amounts": {
                        name: fn_amounts[name]
                        for name in ("contract_liability", "contract_liability_current")
                    },
                    "functional_nodes": {
                        name: fn_nodes[name]
                        for name in ("contract_liability", "contract_liability_current")
                    },
                }
            )
        result.append(snapshot)
    if foreign:
        assert isinstance(fx, FxState)
        layers = [
            {
                "layer_key": layer.layer_key,
                "txn_open": layer.txn_open,
                "functional_carrying": layer.fn_carrying,
                "movements": [
                    {
                        **(
                            {"owner_contract": move.contract_key}
                            if (cb.bundle.evidence_revision or 0) >= 63
                            else {}
                        ),
                        "kind": move.movement_kind,
                        "effective_date": move.effective_date.isoformat(),
                        "amount_txn": move.amount_txn,
                        "amount_functional": move.amount_functional,
                        "rate_key": move.rate_key,
                        "version_key": move.version_key,
                        "rate": str(move.rate),
                        "source_key": move.source_key,
                        "node": move.trace_node_id,
                    }
                    for move in fx.layer_movements
                    if move.entity == entity
                    and move.layer_key == layer.layer_key
                    and move.balance_role == "CONTRACT_LIABILITY"
                    and move.effective_date <= cutover
                ],
            }
            for layer in fx.layer_balances
            if (layer.entity, layer.period_key, layer.balance_role)
            == (entity, period.period_key, "CONTRACT_LIABILITY")
        ]
        policy = str(
            ctx.policies.value("fx.cl_layer_consumption", entity=entity, period=period.period_key)
        )
        monetary = (
            str(ctx.framework) == "ASC606"
            and ctx.policies.value(
                "fx.cl_historical_layering",
                contract=members[0],
                entity=entity,
                period=period.period_key,
            )
            == "DISABLED_REMEASURE_AS_MONETARY"
        )
        parts = classify(
            layers,
            sum(s["amounts"]["contract_liability_current"] for s in result),
            policy=policy,
            minor_unit=ctx.currencies[currency].minor_unit,
            monetary=monetary,
        )
        for snapshot in result:
            snapshot["functional"].update(
                {
                    "liability_layers": layers,
                    "shared_liability_members": shared,
                    "liability_current": {
                        "policy": policy,
                        "monetary": monetary,
                        "allocations": list(parts),
                    },
                }
            )
    trace = evidence.build(root_measures={})
    prefix = f"acquisition-cutover/{period.period_key}/"
    names = {
        n.id: n.id.split(":", 1)[0] + ":" + prefix + n.id.split(":", 1)[1] for n in trace.nodes
    }
    destination.merge_evidence(
        replace(
            trace,
            nodes=tuple(
                replace(
                    n,
                    id=names[n.id],
                    params={k: names.get(v, v) for k, v in n.params.items()},
                    inputs=tuple(names[i] if isinstance(i, str) else i for i in n.inputs),
                )
                for n in trace.nodes
            ),
        )
    )

    def remap(value: Any) -> Any:
        if isinstance(value, str):
            return names.get(value, value)
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}
        if isinstance(value, list):
            return [remap(v) for v in value]
        return value

    return tuple(remap(snapshot) for snapshot in result)
