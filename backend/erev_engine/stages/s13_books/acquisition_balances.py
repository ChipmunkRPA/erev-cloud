"""Nonposting complete balance observations for otherwise unmeasured acquisitions."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from erev_engine.errors import EngineError
from erev_engine.stages import StageSpec
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    group_entity_subject_key,
)
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.state import BookContext, CanonicalBundle, billing_mode_at
from erev_engine.trace import TraceBuilder

MEASURES = (
    "contract_liability",
    "contract_liability_current",
    "contract_asset",
    "contract_asset_current",
    "unbilled_receivable",
    "accounts_receivable",
    "refund_liability",
    "return_asset",
    "deposit_liability",
    "customer_incentive_asset",
    "consideration_payable",
    "cost_asset_carrying",
    "loss_provision",
)


def capture(
    ctx: BookContext,
    cb: CanonicalBundle,
    stages: Sequence[StageSpec],
    published: Mapping[str, object],
    tb: TraceBuilder,
) -> tuple[Mapping[str, object], ...]:
    from . import _run_book
    from .memo import Memo

    original = published.get("10")
    if not isinstance(original, BalanceState) or original.member_balances:
        return ()
    own = original.allocated.obligations
    if (
        not own
        or len({ob.contract_key for ob in own}) != 1
        or any(
            ob.principal_agent.value != "PRINCIPAL"
            or ob.performing_entity != ob.contracting_entity
            or ob.opening is None
            or ob.opening.get("reason") != "BUSINESS_COMBINATION"
            for ob in own
        )
    ):
        return ()
    entities = {ob.contracting_entity for ob in own}
    if len(entities) != 1:
        return ()
    entity = next(iter(entities))
    foreign = ctx.entities[entity].functional_currency != ctx.txn_currency
    if foreign and (cb.bundle.evidence_revision or 0) < 45:
        return ()
    baselines = [baseline_of(ob) for ob in own]
    if any(b is None or b.method != "RECOMPUTE_FROM_INCEPTION" for b in baselines):
        return ()
    dates = {b.cutover_date for b in baselines if b is not None}
    if len(dates) != 1:
        return ()
    cutover = next(iter(dates))
    period = next((p for p in ctx.entities[entity].periods if p.end_date == cutover), None)
    if period is None or period.period_key <= ctx.horizon[entity]:
        return ()
    evidence = TraceBuilder(engine_version=cb.bundle.engine_version)
    # Re-evaluate the original financial stages through costs (and original FX
    # for a foreign observation), retaining all
    # specialist inputs. No posting, disclosure, or output assembler runs here.
    # Calendar states, original input and ordinary context are never changed.
    extended = replace(ctx, horizon=MappingProxyType({**ctx.horizon, entity: period.period_key}))
    try:
        _, measured, _ = _run_book(
            extended,
            cb,
            tuple(s for s in stages if s.stage <= ("12" if foreign else "11")),
            evidence,
            Memo(),
        )
    except EngineError:
        return ()
    balances, costs = measured.get("10"), measured.get("11")
    if not isinstance(balances, BalanceState) or not isinstance(costs, CostLossState):
        return ()
    if any(
        f.severity == "ERROR" for state in measured.values() for f in getattr(state, "findings", ())
    ):
        return ()
    member = own[0].contract_key
    subject = contract_entity_subject_key(member, entity)
    group = group_entity_subject_key(original.allocated.group_code, entity)
    targets = (*balances.member_balances, *balances.member_sums, *costs.member_sums)
    amounts: dict[str, int] = {}
    links: dict[str, str] = {}
    unmeasured: dict[str, str] = {}
    for name in MEASURES:
        candidates = balances.current_split if name.endswith("_current") else targets
        key = group if name.endswith("_current") else subject
        found = [
            t
            for t in candidates
            if t.measure == name
            and t.subject_key == key
            and t.entity == entity
            and t.period_key == period.period_key
        ]
        if len(found) != 1:
            if (
                name == "accounts_receivable"
                and not found
                and billing_mode_at(ctx.policies, ctx.entities[entity], cutover) == "ERP"
            ):
                amounts[name] = 0
                unmeasured[name] = "ERP_MODE_EXTERNAL_BALANCE"
                continue
            return ()  # no absent component is silently converted to a zero balance
        amounts[name], links[name] = found[0].value, found[0].node_id
    functional: dict[str, Any] | None = None
    if foreign:
        fx = measured.get("12")
        if not isinstance(fx, FxState):
            return ()
        from erev_engine import _balances, _functional_balances

        try:
            # Use the ordinary assembler's layer-to-target consistency check,
            # without publishing its rows into the ordinary output population.
            _functional_balances(cb.bundle, balances.allocated, fx, _balances(cb.bundle, balances))
        except EngineError:
            return ()
        fn_amounts: dict[str, int] = {}
        fn_nodes: dict[str, str] = {}
        functional_targets = fx.functional_member_balances
        if (cb.bundle.evidence_revision or 0) >= 52:
            from erev_engine.stages.s12_fx_entities.current_assets import measure

            # This capture has already verified a single acquired member and a
            # recomputed inception baseline. Its group current asset is its own.
            currents = tuple(
                replace(target, subject_key=subject)
                for target in balances.current_split
                if target.measure == "contract_asset_current"
            )
            functional_targets = (
                *functional_targets,
                *measure(
                    extended, fx, currents, functional_targets, evidence, acquired_cutover=True
                ),
            )
        for target in functional_targets:
            if (
                target.subject_key != subject
                or target.entity != entity
                or target.period_key != period.period_key
            ):
                continue
            role = target.measure.removesuffix("_functional")
            if role in fn_amounts or not target.measure.endswith("_functional"):
                return ()
            fn_amounts[role], fn_nodes[role] = target.value, target.node_id
        if not {"contract_liability", "contract_asset", "unbilled_receivable"} <= fn_amounts.keys():
            return ()
        currency = ctx.entities[entity].functional_currency
        functional = {
            "currency": currency,
            "minor_unit": ctx.currencies[currency].minor_unit,
            "amounts": fn_amounts,
            "nodes": fn_nodes,
        }
        if (cb.bundle.evidence_revision or 0) >= 46:
            functional["liability_layers"] = [
                {
                    "layer_key": layer.layer_key,
                    "txn_open": layer.txn_open,
                    "functional_carrying": layer.fn_carrying,
                    "movements": [
                        {
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
                if layer.entity == entity
                and layer.period_key == period.period_key
                and layer.balance_role == "CONTRACT_LIABILITY"
            ]
        if (cb.bundle.evidence_revision or 0) >= 47:
            from erev_engine.stages.s12_fx_entities.current_layers import classify

            policy = str(
                ctx.policies.value(
                    "fx.cl_layer_consumption", entity=entity, period=period.period_key
                )
            )
            monetary = (
                str(ctx.framework) == "ASC606"
                and ctx.policies.value(
                    "fx.cl_historical_layering",
                    contract=member,
                    entity=entity,
                    period=period.period_key,
                )
                == "DISABLED_REMEASURE_AS_MONETARY"
            )
            parts = classify(
                functional["liability_layers"],
                amounts["contract_liability_current"],
                policy=policy,
                minor_unit=functional["minor_unit"],
                monetary=monetary,
            )
            value = sum(int(part["current_functional"]) for part in parts)
            functional["liability_current"] = {
                "policy": policy,
                "monetary": monetary,
                "allocations": list(parts),
            }
            name = "contract_liability_current"
            fn_amounts[name] = value
            fn_nodes[name] = evidence.node(
                measure=f"{name}_functional",
                subject_key=subject,
                period_key=period.period_key,
                value=value,
                currency=currency,
                minor_unit=functional["minor_unit"],
                formula_id="fx.functional_member.v1",
                inputs=[
                    links[name],
                    *(
                        move["node"]
                        for layer in functional["liability_layers"]
                        for move in layer["movements"]
                    ),
                ],
                params={
                    "as_of": period.period_key,
                    "value": str(value),
                    "classification_basis": "ORIGINAL_LAYER_RELEASE",
                    "release_policy": policy,
                },
                narrative_key="fx.functional_member",
            )
    trace = evidence.build(root_measures={})
    prefix = f"acquisition-cutover/{period.period_key}/"
    names = {
        n.id: n.id.split(":", 1)[0] + ":" + prefix + n.id.split(":", 1)[1] for n in trace.nodes
    }
    trace = replace(
        trace,
        nodes=tuple(
            replace(
                n,
                id=names[n.id],
                params={key: names.get(value, value) for key, value in n.params.items()},
                inputs=tuple(names[i] if isinstance(i, str) else i for i in n.inputs),
            )
            for n in trace.nodes
        ),
    )
    tb.merge_evidence(trace)
    if functional is not None:
        functional["nodes"] = {name: names[node] for name, node in functional["nodes"].items()}
        for layer in functional.get("liability_layers", ()):
            for move in layer["movements"]:
                move["node"] = names[move["node"]]
    return (
        {
            "basis": "ORIGINAL_NONPOSTING_CUTOVER_EVALUATION",
            "member": member,
            "entity": entity,
            "period_key": period.period_key,
            "as_of": cutover.isoformat(),
            "currency": ctx.txn_currency,
            "minor_unit": ctx.currencies[ctx.txn_currency].minor_unit,
            "amounts": amounts,
            "unmeasured": unmeasured,
            **({"functional": functional} if functional is not None else {}),
            "nodes": {name: names[node] for name, node in links.items()},
        },
    )
