"""Retain the original S10-R-24/25 inputs for nonposting acquisition cutovers."""

from datetime import date
from typing import Any

from erev_engine import dates
from erev_engine.stages.s09_recognition import RecognitionState, is_deterministic
from erev_engine.stages.s10_billing_balances import billing, current_split
from erev_engine.stages.s10_billing_balances.position import latest_target, series
from erev_engine.stages.state import BookContext


def capture(
    ctx: BookContext,
    recognition: RecognitionState,
    entity: str,
    period_key: str,
    cutover: date,
    subjects: set[str],
) -> dict[str, dict[str, Any]]:
    """Per-POB eligibility, not an allocation of the group's current asset or liability.

    Reuse the original current-split evaluator with the separately retained cutover
    revenue observations. Nothing is appended to posting or schedule targets.
    """
    horizon = dates.add_months(cutover, 12)
    ends = {
        (code, p.period_key): p.end_date
        for code, calendar in ctx.entities.items()
        for p in calendar.periods
    }
    projected: dict[str, list[tuple[date, int]]] = {}
    sources: dict[str, set[str]] = {}
    for line in recognition.schedule_lines:
        if str(line.schedule_kind) != "REVENUE" or line.subject_type != "obligation":
            continue
        end = ends[(line.entity, line.period_key)]
        projected.setdefault(line.subject_key, []).append((end, line.amount))
        if end <= horizon:
            sources.setdefault(line.subject_key, set()).add(line.trace_node_id)
    revenue = series(ctx, (*recognition.revenue_targets, *recognition.disclosure_revenue_targets))
    policy = ctx.policies.value(current_split.CURRENT_POLICY, entity=entity, period=period_key)
    result = {}
    for ob in recognition.allocated.obligations:
        if ob.subject_key not in subjects:
            continue
        observed = latest_target(revenue.get(("revenue_cum", ob.subject_key), ()), cutover)
        if observed is None:
            continue
        deterministic = is_deterministic(ob)
        inputs = sources.get(ob.subject_key, set()) if deterministic else set()
        result[ob.subject_key] = {
            "rule": "S10-R-24/S10-R-25",
            "policy": policy,
            "as_of": cutover.isoformat(),
            "horizon": horizon.isoformat(),
            "deterministic": deterministic,
            "revenue": observed.value,
            "allocation": billing.posted_allocation(ob, cutover),
            "expected_relief": current_split._relief_12(ob, cutover, horizon, revenue, projected),
            "asset_current_eligible": ob.end_date is None or ob.end_date <= horizon,
            "sources": sorted({*inputs, observed.node_id}),
        }
    return result
