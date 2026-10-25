"""Original transaction targets for acquired contracts recomputed from inception."""

from dataclasses import dataclass
from datetime import date

from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.state import BookContext, Target


@dataclass(frozen=True)
class Closing:
    billed: int
    revenue: int
    sources: tuple[str, ...]


def capture(ctx: BookContext, balances: BalanceState) -> dict[tuple[str, date], Closing]:
    """Use actual cumulative targets, including native billing and onboarding differences.

    Imported ERP balances are not substitutes for missing recomputed targets. Separate
    disclosure-only observations may cover a closed cutover without extending posting targets;
    periods missing both ordinary and disclosure observations remain unavailable.
    """
    indexes: list[dict[tuple[str, str, str], list[Target]]] = []
    for targets, measure in (
        ((*balances.billing, *balances.disclosure_billing), "billed_cum"),
        (
            (
                *balances.recognition.revenue_targets,
                *balances.recognition.disclosure_revenue_targets,
            ),
            "revenue_cum",
        ),
    ):
        index: dict[tuple[str, str, str], list[Target]] = {}
        for target in targets:
            if target.measure == measure and target.book_code == ctx.book_code:
                key = (target.subject_key, target.entity, target.period_key)
                index.setdefault(key, []).append(target)
        indexes.append(index)
    result = {}
    for ob in balances.allocated.obligations:
        baseline = baseline_of(ob)
        if (
            baseline is None
            or baseline.method != "RECOMPUTE_FROM_INCEPTION"
            or ob.opening is None
            or ob.opening.get("reason") != "BUSINESS_COMBINATION"
            or ob.principal_agent.value != "PRINCIPAL"
            or (
                ob.performing_entity != ob.contracting_entity
                and not ctx.acquired_cross_entity_observation
            )
        ):
            continue
        for period in ctx.entities[ob.contracting_entity].periods:
            if period.end_date < baseline.cutover_date:
                continue
            selected = []
            for position, index in enumerate(indexes):
                entity = ob.contracting_entity if position == 0 else ob.performing_entity
                aligned = next(
                    (p for p in ctx.entities[entity].periods if p.end_date == period.end_date), None
                )
                if aligned is None:
                    break
                rows = index.get((ob.subject_key, entity, aligned.period_key), [])
                if len(rows) != 1:
                    break
                selected.append(rows[0])
            if len(selected) == 2:
                billed, revenue = selected
                result[ob.subject_key, period.end_date] = Closing(
                    billed.value, revenue.value, (billed.node_id, revenue.node_id, baseline.node_id)
                )
    return result
