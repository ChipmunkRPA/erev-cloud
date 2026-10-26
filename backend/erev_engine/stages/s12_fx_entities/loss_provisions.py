"""Loss tests in functional currency from historical actuals and dated forecasts."""

from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING

from erev_engine import money
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s11_costs_loss import LossMeasures, capitalise
from erev_engine.stages.s12_fx_entities.layers import FxTarget, RateRef
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates, RateView, to_functional
from erev_engine.stages.state import BookContext, Finding, RateIndex
from erev_engine.trace import SourceRef, TraceBuilder

if TYPE_CHECKING:
    from . import FxSource, FxState


def measure(
    ctx: BookContext,
    source: "FxSource",
    fx: "FxState",
    trace: TraceBuilder,
    *,
    rates: RateIndex | None,
) -> "FxState":
    costs = getattr(source, "costs", source)
    held_measures = getattr(costs, "loss_measures", {})
    functional = list(fx.functional_targets)
    findings = list(fx.findings)
    grouped = defaultdict(list)
    failed_entities: set[str] = set()
    originals = {n.id: n for n in trace.build(root_measures={}).nodes}
    previous: dict[str, tuple[int, str]] = {}
    for (_, _), held in sorted(held_measures.items()):
        currency = ctx.entities[held.entity].functional_currency
        if currency == ctx.txn_currency:
            continue
        pair = Rates(() if rates is None else rates.rates, ctx.txn_currency, currency)
        mu = ctx.currencies[currency].minor_unit
        source_mu = ctx.currencies[ctx.txn_currency].minor_unit
        own = [
            ob
            for ob in fx.allocated.obligations
            if ob.contract_key == held.contract_key
            and (held.obligation_key is None or ob.obligation_key == held.obligation_key)
        ]
        member_subjects = {ob.subject_key for ob in own}
        refs = set()

        def summed(
            name: str,
            amount: int,
            inputs: list[str],
            *,
            held: LossMeasures = held,
            currency: str = currency,
            mu: int = mu,
        ) -> str:
            return trace.node(
                measure=name,
                subject_key=held.unit_key,
                period_key=held.period_key,
                value=amount,
                currency=currency,
                minor_unit=mu,
                formula_id="rec.activity_sum.v1",
                inputs=inputs,
                params={"signs": ",".join("+" for _ in inputs)},
                narrative_key="rec.activity_sum",
            )

        try:
            actuals = []
            txn_cost_inputs = []
            txn_cost = 0
            for event in fx.allocated.measure_events:
                if (
                    event.event_type != "COST_INCURRED"
                    or event.contract_key != held.contract_key
                    or event.effective_date > held.as_of
                    or event.payload.get("purpose") != "PROGRESS_INPUT"
                ):
                    continue
                key = event.payload.get("obligation_key")
                if held.obligation_key is not None and not (
                    key == held.obligation_key
                    or (
                        key is None
                        and len(
                            [
                                ob
                                for ob in fx.allocated.obligations
                                if ob.contract_key == held.contract_key
                            ]
                        )
                        == 1
                    )
                    or (
                        fx.allocated.eac_scope_required
                        and any(key in ob.combined_component_keys for ob in own)
                    )
                ):
                    continue
                amount = capitalise.amount_of(event, source_mu)
                txn_cost += amount
                raw = SourceRef(
                    "contract_event",
                    event.event_key,
                    detail={"member": "amount", "value": money.format_money(amount, source_mu)},
                )
                txn_cost_inputs.append(raw)
                rate = pair.spot(event.effective_date)
                if rate.rate_key is not None:
                    refs.add(RateRef(rate.rate_key, str(rate.version_key)))
                converted = to_functional(amount, rate, source_mu, mu)
                node = trace.node(
                    measure="loss_actual_cost_functional",
                    subject_key=held.unit_key + "@" + event.event_key,
                    period_key=held.period_key,
                    value=converted,
                    currency=currency,
                    minor_unit=mu,
                    formula_id="fx.cost_translate.v1",
                    inputs=[raw, *rate.inputs()],
                    params={"as_of": event.effective_date.isoformat()},
                    narrative_key="fx.cost_translate",
                )
                actuals.append((converted, node))
            if txn_cost != held.costs_to_date:
                raise ValueError("Functional loss actual costs differ from the original unit scope")
            cost_txn_node = trace.node(
                measure="loss_original_costs",
                subject_key=held.unit_key,
                period_key=held.period_key,
                value=txn_cost,
                currency=ctx.txn_currency,
                minor_unit=source_mu,
                formula_id="rec.activity_sum.v1",
                inputs=txn_cost_inputs,
                params={"signs": ",".join("+" for _ in txn_cost_inputs)},
                narrative_key="rec.activity_sum",
            )
            cost_fn = sum(amount for amount, _ in actuals)
            cost_node = summed(
                "loss_costs_to_date_functional", cost_fn, [node for _, node in actuals]
            )
            earned = []
            for subject in sorted(member_subjects):
                choices = [
                    target
                    for target in fx.functional_targets
                    if target.entity == held.entity
                    and target.subject_key == subject
                    and target.measure == "revenue_cum"
                    and next(
                        p.end_date
                        for p in ctx.entities[held.entity].periods
                        if p.period_key == target.period_key
                    )
                    <= held.as_of
                ]
                if choices:
                    earned.append(
                        max(
                            choices,
                            key=lambda t: next(
                                p.end_date
                                for p in ctx.entities[held.entity].periods
                                if p.period_key == t.period_key
                            ),
                        )
                    )
            if sum(t.amount_txn for t in earned) != held.revenue_to_date:
                raise ValueError("Functional loss revenue differs from the original unit scope")
            revenue_fn = sum(t.amount_functional for t in earned)
            revenue_node = summed(
                "loss_revenue_to_date_functional", revenue_fn, [t.node_id for t in earned]
            )
            original_required = originals[held.trace_nodes["loss_provision_required"]]
            revenue_txn_node = trace.node(
                measure="loss_original_revenue",
                subject_key=held.unit_key,
                period_key=held.period_key,
                value=held.revenue_to_date,
                currency=ctx.txn_currency,
                minor_unit=source_mu,
                formula_id="rec.activity_sum.v1",
                inputs=list(original_required.inputs[1:]),
                params={"signs": ",".join("+" for _ in original_required.inputs[1:])},
                narrative_key="rec.activity_sum",
            )
            rate = pair.spot(held.as_of)
            if rate.rate_key is not None:
                refs.add(RateRef(rate.rate_key, str(rate.version_key)))

            def forecast(
                name: str,
                original_amount: int,
                original_node: str,
                actual_txn: int,
                actual_node: str,
                actual_fn: int,
                actual_fn_node: str,
                *,
                rate: RateView = rate,
                source_mu: int = source_mu,
                mu: int = mu,
                held: LossMeasures = held,
                currency: str = currency,
            ) -> tuple[int, str]:
                amount = actual_fn + to_functional(
                    original_amount - actual_txn, rate, source_mu, mu
                )
                node = trace.node(
                    measure=name,
                    subject_key=held.unit_key,
                    period_key=held.period_key,
                    value=amount,
                    currency=currency,
                    minor_unit=mu,
                    formula_id="fx.loss_forecast.v1",
                    inputs=[original_node, actual_node, actual_fn_node, *rate.inputs()],
                    params={
                        "as_of": held.as_of.isoformat(),
                        "basis": "HISTORICAL_ACTUALS_DATED_FORECASTS",
                    },
                    narrative_key="fx.loss_forecast",
                )
                return amount, node

            consideration, consideration_node = forecast(
                "loss_expected_consideration_functional",
                held.expected_consideration,
                held.trace_nodes["tp_unconstrained_credit_adjusted"],
                held.revenue_to_date,
                revenue_txn_node,
                revenue_fn,
                revenue_node,
            )
            expected_costs = 0
            if held.eac_version_keys:
                versions = [
                    v
                    for v in {
                        pin.version.version_key: pin.version
                        for pins in fx.allocated.estimates.pins.values()
                        for pin in pins
                    }.values()
                    if v.version_key in held.eac_version_keys
                ]
                # The original unit test is the authoritative sum and contributor set.
                if len(versions) != len(held.eac_version_keys):
                    raise ValueError("Original loss EAC contributors are unavailable")
                eac_inputs = [
                    SourceRef(
                        "estimate_version",
                        v.version_key,
                        detail={
                            "member": "expected_total_amount",
                            "value": str(v.expected_total_amount),
                        },
                    )
                    for v in versions
                ]
                original_eac = trace.node(
                    measure="loss_original_eac",
                    subject_key=held.unit_key,
                    period_key=held.period_key,
                    value=held.expected_total_costs,
                    currency=ctx.txn_currency,
                    minor_unit=source_mu,
                    formula_id="rec.activity_sum.v1",
                    inputs=eac_inputs,
                    params={"signs": ",".join("+" for _ in eac_inputs)},
                    narrative_key="rec.activity_sum",
                )
                expected_costs, expected_costs_node = forecast(
                    "loss_expected_total_costs_functional",
                    held.expected_total_costs,
                    original_eac,
                    held.costs_to_date,
                    cost_txn_node,
                    cost_fn,
                    cost_node,
                )
            else:
                expected_costs_node = summed("loss_expected_total_costs_functional", 0, [])
            margin = consideration - expected_costs
            margin_node = trace.node(
                measure="expected_margin_functional",
                subject_key=held.unit_key,
                period_key=held.period_key,
                value=margin,
                currency=currency,
                minor_unit=mu,
                formula_id="rec.activity_sum.v1",
                inputs=[consideration_node, expected_costs_node],
                params={"signs": "+,-"},
                narrative_key="rec.activity_sum",
            )
            required = (
                max(0, max(0, expected_costs - consideration) - max(0, cost_fn - revenue_fn))
                if held.eac_version_keys
                else 0
            )
            required_node = trace.node(
                measure="loss_provision_required_functional",
                subject_key=held.unit_key,
                period_key=held.period_key,
                value=required,
                currency=currency,
                minor_unit=mu,
                formula_id="loss.required_provision.v1",
                inputs=[consideration_node, revenue_node],
                params={
                    "as_of": held.as_of.isoformat(),
                    "costs": str(cost_fn),
                    "eac": str(expected_costs) if held.eac_version_keys else "none",
                },
                narrative_key="loss.required_provision",
            )
            prior, prior_node = previous.get(held.unit_key, (0, None))
            movement = required - prior
            movement_node = trace.node(
                measure="provision_movement_functional",
                subject_key=held.unit_key,
                period_key=held.period_key,
                value=movement,
                currency=currency,
                minor_unit=mu,
                formula_id="loss.movement.v1",
                inputs=[required_node] if prior_node is None else [required_node, prior_node],
                params={"as_of": held.as_of.isoformat()},
                narrative_key="loss.movement",
            )
            previous[held.unit_key] = (required, required_node)
            values = {
                "loss_provision_required": (held.provision_balance, required, required_node),
                "provision_movement": (held.provision_movement, movement, movement_node),
                "loss_expected_consideration": (
                    held.expected_consideration,
                    consideration,
                    consideration_node,
                ),
                "loss_expected_total_costs": (
                    held.expected_total_costs,
                    expected_costs,
                    expected_costs_node,
                ),
                "loss_costs_to_date": (held.costs_to_date, cost_fn, cost_node),
                "loss_revenue_to_date": (held.revenue_to_date, revenue_fn, revenue_node),
                "expected_margin": (held.expected_margin, margin, margin_node),
            }
            for name, (txn, amount, node) in values.items():
                target = FxTarget(
                    ctx.book_code,
                    held.entity,
                    held.unit_key,
                    name,
                    None,
                    None,
                    held.period_key,
                    ctx.txn_currency,
                    txn,
                    currency,
                    amount,
                    tuple(sorted(refs, key=lambda r: (r.rate_key, r.version_key))),
                    node,
                )
                functional.append(target)
                if name == "loss_provision_required":
                    grouped[
                        (
                            held.entity,
                            contract_entity_subject_key(held.contract_key, held.entity),
                            held.period_key,
                        )
                    ].append(target)
        except RateMissing as missing:
            failed_entities.add(held.entity)
            findings.append(
                Finding("FX_RATE_MISSING", "ERROR", held.unit_key, missing.detail, 12, None)
            )
    members = list(fx.functional_member_balances)
    for target in getattr(costs, "member_sums", ()):
        if (
            target.measure != "loss_provision"
            or ctx.entities[target.entity].functional_currency == ctx.txn_currency
        ):
            continue
        if target.entity in failed_entities:
            continue
        parts = grouped[(target.entity, target.subject_key, target.period_key)]
        if sum(t.amount_txn for t in parts) != target.value:
            raise ValueError("Functional loss member sum lacks complete original units")
        amount = sum(t.amount_functional for t in parts)
        currency = ctx.entities[target.entity].functional_currency
        node = trace.node(
            measure="loss_provision_functional",
            subject_key=target.subject_key,
            period_key=target.period_key,
            value=amount,
            currency=currency,
            minor_unit=ctx.currencies[currency].minor_unit,
            formula_id="rec.activity_sum.v1",
            inputs=[t.node_id for t in parts],
            params={"signs": ",".join("+" for _ in parts)},
            narrative_key="rec.activity_sum",
        )
        members.append(
            replace(target, measure="loss_provision_functional", value=amount, node_id=node)
        )
    return replace(
        fx,
        functional_targets=tuple(functional),
        functional_member_balances=tuple(members),
        findings=tuple(sorted(findings, key=lambda f: f.sort_key())),
    )
