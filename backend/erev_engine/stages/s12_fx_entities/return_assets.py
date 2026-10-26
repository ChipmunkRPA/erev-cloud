"""Return assets retain original delivery costs/rates and dated recovery estimates."""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING

from erev_engine import dates, money
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s09_recognition import progress_events, returns
from erev_engine.stages.s12_fx_entities.layers import FxTarget, RateRef
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates, RateView
from erev_engine.stages.state import (
    BookContext,
    EventView,
    Finding,
    ObligationState,
    RateIndex,
    ReturnPin,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

if TYPE_CHECKING:
    from . import FxSource, FxState


@dataclass
class DeliveryLayer:
    event: EventView
    remaining: Fraction
    cost: Fraction
    pin: ReturnPin | None
    rate: RateView


def take(
    layers: list[DeliveryLayer], quantity: Fraction, option: str
) -> list[tuple[DeliveryLayer, Fraction]]:
    available = sum((layer.remaining for layer in layers), Fraction(0))
    if quantity < 0 or quantity > available:
        raise ValueError("Return asset quantity exceeds original delivered units")
    result = []
    left = quantity
    for layer in layers:
        amount = (
            quantity * layer.remaining / available
            if option == "PRO_RATA" and available
            else min(left, layer.remaining)
        )
        if amount:
            result.append((layer, amount))
            left -= amount
    if left:
        raise ValueError("Return asset delivery-layer allocation does not reconcile")
    return result


def measure(
    ctx: BookContext,
    source: "FxSource",
    fx: "FxState",
    trace: TraceBuilder,
    *,
    rates: RateIndex | None,
) -> "FxState":
    costs = getattr(source, "costs", source)
    balances = getattr(costs, "balances", getattr(source, "balances", None))
    if balances is None:
        return fx
    original = {(t.subject_key, t.period_key, t.measure): t for t in balances.return_assets}
    obligations = {ob.subject_key: ob for ob in fx.allocated.obligations}
    functional = list(fx.functional_targets)
    findings = list(fx.findings)
    member_parts = defaultdict(list)
    failed_entities: set[str] = set()
    for (subject, period), held in sorted(balances.recognition.return_states.items()):
        ob = obligations[subject]
        currency = ctx.entities[ob.contracting_entity].functional_currency
        if currency == ctx.txn_currency:
            continue
        pair = Rates(() if rates is None else rates.rates, ctx.txn_currency, currency)
        mu = ctx.currencies[currency].minor_unit
        path = fx.allocated.return_paths[subject]
        contract = next(
            c for c in fx.allocated.contracts if c.header.external_id == ob.contract_key
        )
        end = held.as_of
        if end is None:
            raise ValueError("Foreign return asset requires an original measurement date")
        layers: list[DeliveryLayer] = []
        returned = Fraction(0)
        delivered = Fraction(0)
        derecognised = []
        refs: set[RateRef] = set()
        eligible = dict(held.returns_before_E)
        option_trigger = progress_events.control_trigger_option(ctx, ob)
        outcome = progress_events.repurchase_outcome(ctx, contract, ob)

        def policy(on: date, *, ob: ObligationState = ob) -> str:
            key = dates.period_of(ctx.entities[ob.contracting_entity], on).period_key
            return str(
                ctx.policies.value(
                    "fx.cl_layer_consumption", entity=ob.contracting_entity, period=key
                )
            )

        def emit(
            name: str,
            selected: list[tuple[DeliveryLayer, Fraction]],
            recovery: ReturnPin | None,
            when: date,
            raw: Target,
            *,
            subject: str = subject,
            period: str = period,
            currency: str = currency,
            mu: int = mu,
            pair: Rates = pair,
            refs: set[RateRef] = refs,
            ob: ObligationState = ob,
        ) -> tuple[int, str]:
            # Missing unit-cost estimates imply zero carrying under the original
            # return model. Do not manufacture an estimate-version reference.
            selected = [(layer, amount) for layer, amount in selected if layer.cost > 0]
            if not selected:
                node = trace.node(
                    measure=name,
                    subject_key=subject + ("@" + raw.cause if raw.cause else ""),
                    period_key=period,
                    value=0,
                    currency=currency,
                    minor_unit=mu,
                    formula_id="rec.activity_sum.v1",
                    inputs=[],
                    params={"signs": ""},
                    narrative_key="rec.activity_sum",
                )
                return 0, node
            if recovery is None or any(layer.pin is None for layer, _ in selected):
                raise ValueError("Return asset cost/recovery source is unavailable")
            recovery_rate = pair.spot(when)
            if recovery_rate.rate_key is not None:
                refs.add(RateRef(recovery_rate.rate_key, str(recovery_rate.version_key)))
            recovery_value = (
                Fraction(0)
                if recovery is None or recovery.recovery_cost_per_unit is None
                else recovery.recovery_cost_per_unit
            )
            inputs = [
                SourceRef(
                    "estimate_version",
                    "NO_RETURN_RECOVERY_ESTIMATE" if recovery is None else recovery.version_key,
                    detail={
                        "member": "recovery_cost_per_unit",
                        "value": money.format_exact(recovery_value),
                    },
                ),
                *recovery_rate.inputs(),
            ]
            quantities = []
            exact = Fraction(0)
            for layer, taken in selected:
                if layer.rate.rate_key is not None:
                    refs.add(RateRef(layer.rate.rate_key, str(layer.rate.version_key)))
                cost_ref = SourceRef(
                    "rule" if layer.pin is None else "estimate_version",
                    "NO_RETURN_COST_ESTIMATE" if layer.pin is None else layer.pin.version_key,
                    detail={
                        "member": "carrying_cost_per_unit",
                        "value": money.format_exact(layer.cost),
                    },
                )
                delivery_ref = SourceRef(
                    "contract_event",
                    layer.event.event_key,
                    detail={
                        "member": "quantity",
                        "value": money.format_exact(progress_events.quantity(layer.event, ob)),
                    },
                )
                inputs.extend([cost_ref, *layer.rate.inputs(), delivery_ref])
                quantities.append(rational_param(taken))
                exact += (
                    max(
                        Fraction(0),
                        layer.cost * layer.rate.value - recovery_value * recovery_rate.value,
                    )
                    * taken
                )
            inputs.append(raw.node_id)
            value_minor = money.round_half_up(exact, mu)
            node = trace.node(
                measure=name,
                subject_key=subject + ("@" + raw.cause if raw.cause else ""),
                period_key=period,
                value=value_minor,
                currency=currency,
                minor_unit=mu,
                formula_id="fx.return_asset.v1",
                inputs=inputs,
                params={
                    "as_of": when.isoformat(),
                    "quantities": "|".join(quantities),
                    "basis": "HISTORICAL_DELIVERY_COST_DATED_RECOVERY",
                },
                narrative_key="fx.return_asset",
            )
            return value_minor, node

        try:
            for event in fx.allocated.measure_events:
                if event.effective_date > end or not progress_events.concerns(event, ob):
                    continue
                if event.event_type == "DELIVERY_RECORDED":
                    if (
                        progress_events.hold_reason(
                            ctx, contract, ob, event, option=option_trigger, outcome=outcome
                        )
                        is not None
                    ):
                        continue
                    quantity = progress_events.quantity(event, ob)
                    pin = returns.pin_at(
                        path,
                        event.effective_date,
                        progress_events.Position(event.order_key, inclusive=True),
                    )
                    if pin is None or pin.carrying_cost_per_unit is None:
                        known = [
                            p
                            for p in path.pins
                            if p.effective_date <= end
                            and p.carrying_cost_per_unit is not None
                            and p.applies_to_member
                        ]
                        prior = [p for p in known if p.effective_date <= event.effective_date]
                        pin = prior[-1] if prior else (known[0] if known else None)
                    cost = (
                        Fraction(0)
                        if pin is None or pin.carrying_cost_per_unit is None
                        else pin.carrying_cost_per_unit
                    )
                    layers.append(
                        DeliveryLayer(event, quantity, cost, pin, pair.spot(event.effective_date))
                    )
                    delivered += quantity
                elif event.event_type == "RETURN_RECORDED":
                    quantity = progress_events.quantity(event, ob)
                    selected = take(layers, quantity, policy(event.effective_date))
                    expected = eligible.get(event.event_key, Fraction(0))
                    selected_expected = (
                        [(layer, amount * expected / quantity) for layer, amount in selected]
                        if policy(event.effective_date) == "PRO_RATA"
                        else take(layers, expected, "FIFO")
                    )
                    before = returns.pin_at(
                        path,
                        event.effective_date,
                        progress_events.Position(event.order_key, inclusive=False),
                    )
                    raw = original[(subject, period, "return_asset_derecognised_cum")]
                    event_raw = replace(raw, cause=event.event_key)
                    derecognised.append(
                        emit(
                            "return_asset_release_functional",
                            selected_expected,
                            before,
                            event.effective_date,
                            event_raw,
                        )
                    )
                    for layer, taken in selected:
                        layer.remaining -= taken
                    returned += quantity
            if delivered != held.N or returned != held.Y:
                raise ValueError(
                    "Foreign return asset lacks complete original delivery/return history"
                )
            current = returns.pin_at(path, end)
            raw_balance = original[(subject, period, "return_asset")]
            asset_minor, node = emit(
                "return_asset_functional",
                take(layers, held.E, policy(end)),
                current,
                end,
                raw_balance,
            )
            release = sum(value for value, _ in derecognised)
            release_node = trace.node(
                measure="return_asset_derecognised_cum_functional",
                subject_key=subject,
                period_key=period,
                value=release,
                currency=currency,
                minor_unit=mu,
                formula_id="rec.activity_sum.v1",
                inputs=[n for _, n in derecognised],
                params={"signs": ",".join("+" for _ in derecognised)},
                narrative_key="rec.activity_sum",
            )
            established_node = trace.node(
                measure="return_asset_established_cum_functional",
                subject_key=subject,
                period_key=period,
                value=asset_minor + release,
                currency=currency,
                minor_unit=mu,
                formula_id="rec.activity_sum.v1",
                inputs=[node, release_node],
                params={"signs": "+,+"},
                narrative_key="rec.activity_sum",
            )
            functional.append(
                FxTarget(
                    ctx.book_code,
                    ob.contracting_entity,
                    subject,
                    "return_asset_established_cum",
                    None,
                    None,
                    period,
                    ctx.txn_currency,
                    raw_balance.value
                    + original[(subject, period, "return_asset_derecognised_cum")].value,
                    currency,
                    asset_minor + release,
                    tuple(sorted(refs, key=lambda r: (r.rate_key, r.version_key))),
                    established_node,
                )
            )
            for name, value, identity in (
                ("return_asset", asset_minor, node),
                ("return_asset_derecognised_cum", release, release_node),
            ):
                raw = original[(subject, period, name)]
                target = FxTarget(
                    ctx.book_code,
                    ob.contracting_entity,
                    subject,
                    name,
                    None,
                    None,
                    period,
                    ctx.txn_currency,
                    raw.value,
                    currency,
                    value,
                    tuple(sorted(refs, key=lambda r: (r.rate_key, r.version_key))),
                    identity,
                )
                functional.append(target)
                if name == "return_asset":
                    member_parts[
                        (
                            target.entity,
                            contract_entity_subject_key(ob.contract_key, target.entity),
                            period,
                        )
                    ].append(target)
        except RateMissing as missing:
            failed_entities.add(ob.contracting_entity)
            findings.append(Finding("FX_RATE_MISSING", "ERROR", subject, missing.detail, 12, None))
    members = list(fx.functional_member_balances)
    for raw in balances.member_sums:
        if (
            raw.measure != "return_asset"
            or ctx.entities[raw.entity].functional_currency == ctx.txn_currency
        ):
            continue
        if raw.entity in failed_entities:
            continue
        parts = member_parts[(raw.entity, raw.subject_key, raw.period_key)]
        if sum(p.amount_txn for p in parts) != raw.value:
            raise ValueError("Functional return asset member sum is incomplete")
        value = sum(p.amount_functional for p in parts)
        currency = ctx.entities[raw.entity].functional_currency
        node = trace.node(
            measure="return_asset_functional",
            subject_key=raw.subject_key,
            period_key=raw.period_key,
            value=value,
            currency=currency,
            minor_unit=ctx.currencies[currency].minor_unit,
            formula_id="rec.activity_sum.v1",
            inputs=[p.node_id for p in parts],
            params={"signs": ",".join("+" for _ in parts)},
            narrative_key="rec.activity_sum",
        )
        members.append(replace(raw, measure="return_asset_functional", value=value, node_id=node))
    return replace(
        fx,
        functional_targets=tuple(functional),
        functional_member_balances=tuple(members),
        findings=tuple(sorted(findings, key=lambda f: f.sort_key())),
    )
