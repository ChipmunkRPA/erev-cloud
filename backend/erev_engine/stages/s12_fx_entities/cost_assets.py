"""Historical carrying for ordinary capitalised contract costs and their amortisation."""

from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

from erev_engine.money import round_half_up
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s12_fx_entities.layers import FxTarget, RateRef
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates, to_functional
from erev_engine.stages.state import BookContext, Finding, RateIndex, Target
from erev_engine.trace import TraceBuilder

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
    specs = getattr(costs, "cost_asset_specs", ())
    targets = getattr(costs, "cost_assets", ())
    functional = list(fx.functional_targets)
    findings = list(fx.findings)
    carrying: dict[tuple[str, str, str], list[FxTarget]] = defaultdict(list)
    for spec in specs:
        currency = ctx.entities[spec.entity].functional_currency
        if currency == ctx.txn_currency:
            continue
        own = [t for t in targets if t.subject_key == spec.asset_key]
        # Recoverability and reimbursement need their own functional measurement.
        supported = {"cost_capitalised", "cost_amortised_cum", "carrying_amount"}
        if ctx.historical_cost_acceleration:
            supported.add("cost_accelerated_cum")
        if any(t.value and t.measure not in supported for t in own):
            continue
        event = next(e for e in fx.allocated.events if e.event_key == spec.asset_key)
        if event.effective_date != spec.capitalization_date and not ctx.historical_cost_deferred:
            continue
        pair = Rates(() if rates is None else rates.rates, ctx.txn_currency, currency)
        try:
            rate = pair.spot(spec.capitalization_date)
        except RateMissing as missing:
            findings.append(
                Finding(
                    "FX_RATE_MISSING", "ERROR", spec.asset_key, missing.detail, 12, spec.asset_key
                )
            )
            continue
        mu = ctx.currencies[currency].minor_unit
        original = to_functional(
            spec.amount_capitalized, rate, ctx.currencies[ctx.txn_currency].minor_unit, mu
        )
        refs = () if rate.rate_key is None else (RateRef(rate.rate_key, str(rate.version_key)),)
        by_period: dict[str, dict[str, Target]] = defaultdict(dict)
        for target in own:
            by_period[target.period_key][target.measure] = target
        for period, measures in sorted(by_period.items()):
            capital = measures["cost_capitalised"]
            amort = measures["cost_amortised_cum"]
            held = measures["carrying_amount"]
            accelerated = measures["cost_accelerated_cum"]
            total_released = amort.value + accelerated.value
            if (
                capital.value != spec.amount_capitalized
                or held.value != capital.value - total_released
            ):
                raise ValueError("Ordinary cost carrying does not reconcile")
            if not 0 <= amort.value <= total_released <= capital.value:
                raise ValueError("Ordinary cost amortisation exceeds capitalised cost")
            released = (
                round_half_up(Fraction(original * amort.value, capital.value), 0)
                if capital.value
                else 0
            )
            consumed = (
                round_half_up(Fraction(original * total_released, capital.value), 0)
                if capital.value
                else 0
            )
            values = {
                "cost_capitalised": original,
                "cost_amortised_cum": released,
                "carrying_amount": original - consumed,
            }
            if ctx.historical_cost_acceleration:
                values["cost_accelerated_cum"] = consumed - released
            for name, amount in values.items():
                target = measures[name]
                node = trace.node(
                    measure=f"{name}_functional",
                    subject_key=spec.asset_key,
                    period_key=period,
                    value=amount,
                    currency=currency,
                    minor_unit=mu,
                    formula_id="fx.functional_member.v1",
                    inputs=[
                        capital.node_id,
                        amort.node_id,
                        held.node_id,
                        *rate.inputs(),
                        *([accelerated.node_id] if ctx.historical_cost_acceleration else []),
                    ],
                    params={
                        "value": str(amount),
                        "basis": "HISTORICAL_COST",
                        "capitalization_date": spec.capitalization_date.isoformat(),
                        "capitalised_txn": str(capital.value),
                        "capitalised_functional": str(original),
                        "amortised_txn": str(amort.value),
                        **(
                            {"accelerated_txn": str(accelerated.value)}
                            if ctx.historical_cost_acceleration
                            else {}
                        ),
                    },
                    narrative_key="fx.functional_member",
                )
                converted = FxTarget(
                    ctx.book_code,
                    spec.entity,
                    spec.asset_key,
                    name,
                    None,
                    None,
                    period,
                    ctx.txn_currency,
                    target.value,
                    currency,
                    amount,
                    refs,
                    node,
                )
                functional.append(converted)
                if name == "carrying_amount":
                    member = contract_entity_subject_key(spec.contract_key, spec.entity)
                    carrying[(spec.entity, member, period)].append(converted)
    members = list(fx.functional_member_balances)
    for target in getattr(costs, "member_sums", ()):
        if target.measure != "cost_asset_carrying":
            continue
        currency = ctx.entities[target.entity].functional_currency
        if currency == ctx.txn_currency:
            continue
        parts = carrying.get((target.entity, target.subject_key, target.period_key), [])
        if sum(p.amount_txn for p in parts) != target.value:
            continue  # Never publish a partial member balance.
        amount = sum(p.amount_functional for p in parts)
        name = "cost_asset_carrying_functional"
        node = trace.node(
            measure=name,
            subject_key=target.subject_key,
            period_key=target.period_key,
            value=amount,
            currency=currency,
            minor_unit=ctx.currencies[currency].minor_unit,
            formula_id="rec.activity_sum.v1",
            inputs=[p.node_id for p in parts],
            params={"signs": ",".join("+" for _ in parts)},
            narrative_key="rec.activity_sum",
        )
        members.append(replace(target, measure=name, value=amount, node_id=node))
    return replace(
        fx,
        functional_targets=tuple(functional),
        functional_member_balances=tuple(members),
        findings=tuple(sorted(findings, key=lambda finding: finding.sort_key())),
    )
