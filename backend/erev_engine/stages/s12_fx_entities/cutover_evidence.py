"""Original FX evidence at a closed acquisition cutover, separate from posting targets."""

from dataclasses import replace
from types import MappingProxyType

from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.state import BookContext, RateIndex
from erev_engine.trace import TraceBuilder

from . import FxSource, FxState, run


def capture(
    ctx: BookContext, source: FxSource, tb: TraceBuilder, *, rates: RateIndex | None
) -> FxState | None:
    horizon = dict(ctx.horizon)
    for entity, view in ctx.entities.items():
        if view.functional_currency == ctx.txn_currency:
            continue
        own = [ob for ob in source.allocated.obligations if ob.contracting_entity == entity]
        if not own or any(
            ob.performing_entity != entity
            or ob.principal_agent.value != "PRINCIPAL"
            or ob.opening is None
            or ob.opening.get("reason") != "BUSINESS_COMBINATION"
            for ob in own
        ):
            continue
        baselines = [baseline_of(ob) for ob in own]
        if any(b is None or b.method != "OPENING_BALANCES_AT_CUTOVER" for b in baselines):
            continue
        dates = {b.cutover_date for b in baselines if b is not None}
        if len(dates) != 1:
            continue
        cutover = next(iter(dates))
        current = next((p for p in view.periods if p.period_key == horizon.get(entity)), None)
        closing = next((p for p in view.periods if p.end_date == cutover), None)
        if (
            current is not None
            and closing is not None
            and dict(closing.states).get(ctx.book_code) in {"closed", "locked"}
            and current.end_date < cutover
        ):
            horizon[entity] = closing.period_key
    if horizon == dict(ctx.horizon):
        return None
    original = tb.build(root_measures={})
    evidence = TraceBuilder(engine_version=original.engine_version)
    calculated = run(
        replace(ctx, horizon=MappingProxyType(horizon)),
        source,
        evidence,
        rates=rates,
        capture_opening_attribution=True,
    )
    # Missing original rates or invalid evidence must never fabricate functional sources.
    # Financial output of the ordinary run remains authoritative; readers refuse gaps.
    if any(f.severity == "ERROR" for f in calculated.findings):
        return None
    tb.merge_evidence(evidence.build(root_measures={}))
    return calculated
