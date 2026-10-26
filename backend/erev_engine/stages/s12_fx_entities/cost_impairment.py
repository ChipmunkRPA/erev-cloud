"""Independent functional cost assets, impairment and permitted reversals."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction

from erev_engine import money
from erev_engine.bundle import PeriodInput
from erev_engine.stages.s11_costs_loss import (
    CostAssetSpec,
    CostLossState,
    CostRevenue,
    MonetaryBasis,
    measure_assets,
)
from erev_engine.stages.s12_fx_entities.layers import FxTarget, RateRef
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates, RateView, to_functional
from erev_engine.stages.state import BookContext, EventView, Finding, RateIndex
from erev_engine.trace import SourceRef, TraceBuilder


class FunctionalTrace(TraceBuilder):
    """Reuse registered cost formulas under distinct functional measure identities."""

    def __init__(self, original: TraceBuilder) -> None:
        super().__init__(engine_version=original.build(root_measures={}).engine_version)
        self.original = original

    def node(
        self,
        *,
        measure: str,
        subject_key: str,
        period_key: str | None,
        value: Fraction | Decimal | int,
        currency: str | None,
        minor_unit: int | None,
        formula_id: str,
        inputs: Sequence[str | SourceRef],
        params: Mapping[str, str] | None = None,
        exact: Fraction | None = None,
        narrative_key: str,
    ) -> str:
        return self.original.node(
            measure=measure + "_functional",
            subject_key=subject_key,
            period_key=period_key,
            value=value,
            currency=currency,
            minor_unit=minor_unit,
            formula_id=formula_id,
            inputs=inputs,
            params=params,
            exact=exact,
            narrative_key=narrative_key,
        )


@dataclass
class ConvertedInputs:
    pair: Rates
    currency: str
    mu: int
    source_mu: int
    trace: TraceBuilder
    ctx: BookContext
    basis_rates: dict[str, RateView]
    clawbacks: dict[tuple[str, str], tuple[int, SourceRef, int, int]]
    recovery_rates: dict[str, RateView]

    def recoverable(
        self, group: str, period: PeriodInput, consideration: int, remaining_costs: int
    ) -> tuple[int, str]:
        rate = self.pair.spot(period.end_date)
        self.recovery_rates[period.period_key] = rate
        amount = to_functional(consideration, rate, self.source_mu, self.mu) - to_functional(
            remaining_costs, rate, self.source_mu, self.mu
        )
        node = self.trace.node(
            measure="cost_recoverable_functional",
            subject_key=group,
            period_key=period.period_key,
            value=amount,
            currency=self.currency,
            minor_unit=self.mu,
            formula_id="fx.cost_recoverable.v1",
            inputs=[f"cost_recoverable:{group}:{period.period_key}", *rate.inputs()],
            params={
                "as_of": period.end_date.isoformat(),
                "remaining_consideration": str(consideration),
                "remaining_costs": str(remaining_costs),
                "source_minor_unit": str(self.source_mu),
                "basis": "INDEPENDENT_FUNCTIONAL_RECOVERABILITY",
            },
            narrative_key="fx.cost_recoverable",
        )
        return (amount, node)

    def clawback(self, asset: str, event: EventView) -> tuple[int, str]:
        if (asset, event.event_key) not in self.clawbacks:
            raise ValueError("Original cost clawback allocation is unavailable")
        taken, original_ref, original_carrying, taken_before = self.clawbacks[
            asset, event.event_key
        ]
        original_node = self.trace.node(
            measure="cost_clawback_original_allocation",
            subject_key=f"{asset}@{event.event_key}",
            period_key=None,
            value=taken,
            currency=self.ctx.txn_currency,
            minor_unit=self.source_mu,
            formula_id="cost.clawback.v1",
            inputs=[original_ref],
            params={
                "as_of": event.effective_date.isoformat(),
                "carrying": str(original_carrying),
                "taken_before": str(taken_before),
            },
            narrative_key="cost.clawback",
        )
        rate = self.basis_rates[asset]
        amount = to_functional(taken, rate, self.source_mu, self.mu)
        node = self.trace.node(
            measure="cost_clawback_historical_conversion",
            subject_key=f"{asset}@{event.event_key}",
            period_key=None,
            value=amount,
            currency=self.currency,
            minor_unit=self.mu,
            formula_id="fx.cost_translate.v1",
            inputs=[original_node, *rate.inputs()],
            params={"as_of": event.effective_date.isoformat()},
            narrative_key="fx.cost_translate",
        )
        return (amount, node)


def targets(
    ctx: BookContext,
    costs: CostLossState,
    trace: TraceBuilder,
    rates: RateIndex | None,
) -> tuple[tuple[FxTarget, ...], tuple[Finding, ...]]:
    original_nodes = {n.id: n for n in trace.build(root_measures={}).nodes}
    grouped: dict[tuple[str, str], list[CostAssetSpec]] = defaultdict(list)
    original = {(t.subject_key, t.period_key, t.measure): t for t in costs.cost_assets}
    for spec in costs.cost_asset_specs:
        if ctx.entities[spec.entity].functional_currency != ctx.txn_currency:
            grouped[(spec.contract_key, spec.entity)].append(spec)
    output: list[FxTarget] = []
    findings: list[Finding] = []
    source_mu = ctx.currencies[ctx.txn_currency].minor_unit
    obligations = {ob.subject_key: ob for ob in costs.allocated.obligations}
    revenue = CostRevenue(ctx, costs.balances.recognition.revenue_targets, obligations)
    for (_, entity), specs in sorted(grouped.items()):
        currency = ctx.entities[entity].functional_currency
        mu = ctx.currencies[currency].minor_unit
        pair = Rates(() if rates is None else rates.rates, ctx.txn_currency, currency)
        basis_rates: dict[str, RateView] = {}
        basis_refs = {}
        capital_nodes = {}
        translated = []
        recovery_rates: dict[str, RateView] = {}
        clawbacks: dict[tuple[str, str], tuple[int, SourceRef, int, int]] = {}
        for held in costs.cost_asset_measures.values():
            claw_node = original_nodes[held.trace_nodes["cost_clawback_cum"]]
            carrying = claw_node.params["carrying"].split("|") if claw_node.inputs else []
            before = claw_node.params["taken_before"].split("|") if claw_node.inputs else []
            for ref, carrying_value, prior_taken in zip(
                claw_node.inputs, carrying, before, strict=True
            ):
                if not isinstance(ref, SourceRef):
                    raise ValueError("Original cost clawback source is unavailable")
                amount = money.round_half_up(money.to_fraction(ref.detail["value"]), source_mu)
                clawbacks.setdefault(
                    (held.asset_key, ref.ref_id),
                    (
                        min(max(0, amount - int(prior_taken)), int(carrying_value)),
                        ref,
                        int(carrying_value),
                        int(prior_taken),
                    ),
                )

        try:
            for spec in specs:
                rate = pair.spot(spec.capitalization_date)
                basis_rates[spec.asset_key] = rate
                basis_refs[spec.asset_key] = set(
                    ()
                    if rate.rate_key is None
                    else (RateRef(rate.rate_key, str(rate.version_key)),)
                )
                own = [
                    t
                    for t in costs.cost_assets
                    if t.subject_key == spec.asset_key and t.measure == "cost_capitalised"
                ]
                original_capital = own[0].node_id
                amount = to_functional(spec.amount_capitalized, rate, source_mu, mu)
                capital_nodes[spec.asset_key] = trace.node(
                    measure="cost_capitalisation_basis_functional",
                    subject_key=spec.asset_key,
                    period_key=None,
                    value=amount,
                    currency=currency,
                    minor_unit=mu,
                    formula_id="fx.cost_translate.v1",
                    inputs=[original_capital, *rate.inputs()],
                    params={"capitalization_date": spec.capitalization_date.isoformat()},
                    narrative_key="fx.cost_translate",
                )
                translated.append(replace(spec, amount_capitalized=amount))

            basis = ConvertedInputs(
                pair, currency, mu, source_mu, trace, ctx, basis_rates, clawbacks, recovery_rates
            )

            measured = measure_assets(
                replace(ctx, txn_currency=currency),
                costs.balances,
                translated,
                capital_nodes,
                FunctionalTrace(trace),
                monetary_basis=MonetaryBasis(source_mu, revenue, basis.recoverable, basis.clawback),
            )
            previous: dict[str, tuple[int, int]] = {}
            refs_at = {}
            for key, held in measured.measures.items():
                prior = previous.get(held.asset_key, (0, 0))
                if (held.impaired_cum, held.impairment_reversed_cum) != prior:
                    rate = recovery_rates[held.period_key]
                    if rate.rate_key is not None:
                        basis_refs[held.asset_key].add(
                            RateRef(rate.rate_key, str(rate.version_key))
                        )
                previous[held.asset_key] = (held.impaired_cum, held.impairment_reversed_cum)
                refs_at[key] = tuple(
                    sorted(basis_refs[held.asset_key], key=lambda r: (r.rate_key, r.version_key))
                )
            for target in measured.targets:
                source = original[(target.subject_key, target.period_key, target.measure)]
                node = target.node_id
                expected = f"{target.measure}_functional:{target.subject_key}:{target.period_key}"
                if node != expected:
                    node = trace.node(
                        measure=target.measure + "_functional",
                        subject_key=target.subject_key,
                        period_key=target.period_key,
                        value=target.value,
                        currency=currency,
                        minor_unit=mu,
                        formula_id="rec.activity_sum.v1",
                        inputs=[node],
                        params={"signs": "+"},
                        narrative_key="rec.activity_sum",
                    )
                output.append(
                    FxTarget(
                        ctx.book_code,
                        entity,
                        target.subject_key,
                        target.measure,
                        None,
                        None,
                        target.period_key,
                        ctx.txn_currency,
                        source.value,
                        currency,
                        target.value,
                        refs_at[(target.subject_key, target.period_key)],
                        node,
                    )
                )
        except RateMissing as missing:
            findings.append(
                Finding(
                    "FX_RATE_MISSING",
                    "ERROR",
                    specs[0].asset_key,
                    missing.detail,
                    12,
                    specs[0].asset_key,
                )
            )
    return tuple(output), tuple(findings)
