"""Stage 10 current and noncurrent parts of the presented balances (ENGINE_SPEC_B §10.2.8; ENC-14).

POL-124 is read per contracting entity and period. Under ``NONE`` the reporting view is suppressed
and every current part is 0 (T-CON-09 defaults). Under ``EXPECTED_TIMING_12_MONTHS`` the current
part of the contract liability is the revenue relief expected within 12 months after the period
end t, capped at the presented liability: for a deterministic obligation (stage 09
``is_deterministic``; S09-R-45) its projected schedule
target at h12 = t + 12 months less its revenue target at t; for any other obligation ending by h12
or without an end date, the amount awaiting a trigger, its posted allocation less its revenue
target (S10-R-24; L2-4-Q-25). A contract asset attributed to an obligation ending by h12 or without
an end date is current, and every unbilled receivable is current (S10-R-25). Current parts never
exceed their balances (S10-INV-09). The split is a reporting view and posts nothing. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from erev_engine.stages.s09_recognition import RecognitionState, is_deterministic
from erev_engine.stages.s10_billing_balances import billing, classification
from erev_engine.stages.s10_billing_balances.position import latest_target, series
from erev_engine.stages.s10_billing_balances.reclass import Presentation
from erev_engine.stages.state import BookContext, ObligationState, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["CURRENT_FORMULA", "CURRENT_POLICY", "EXPECTED_TIMING", "NONE", "measure"]

CURRENT_FORMULA: Final = "pos.current_split.v1"
CURRENT_POLICY: Final = "balance.current_noncurrent"  # POL-124
EXPECTED_TIMING: Final = "EXPECTED_TIMING_12_MONTHS"
NONE: Final = "NONE"
_BALANCES: Final = (
    ("contract_liability", "contract_liability_current", "cl"),
    ("contract_asset", "contract_asset_current", "ca"),
    ("unbilled_receivable", "unbilled_receivable_current", "ur"),
)


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _relief_12(
    ob: ObligationState,
    t: date,
    h12: date,
    revenue: Mapping[tuple[str, str], Sequence[tuple[date, Target]]],
    projected: Mapping[str, Sequence[tuple[date, int]]],
) -> int | None:
    """Revenue relief of ``ob`` expected in (t, h12], or None when it does not count (S10-R-24)."""
    found = latest_target(revenue.get(("revenue_cum", ob.subject_key), ()), t)
    earned = 0 if found is None else found.value
    if is_deterministic(ob):  # S09-R-45
        lines = projected.get(ob.subject_key, ())
        return sum(amount for end, amount in lines if end <= h12) - earned
    if ob.end_date is None or ob.end_date <= h12:
        return billing.posted_allocation(ob, t) - earned
    return None


def measure(
    ctx: BookContext, recognition: RecognitionState, presentation: Presentation, tb: TraceBuilder
) -> tuple[Target, ...]:
    """The current parts ``contract_liability_current``, ``contract_asset_current`` and
    ``unbilled_receivable_current`` per (group, contracting entity) and period end (§10.2.8;
    §10.5)."""
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    ends = {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    projected: dict[str, list[tuple[date, int]]] = {}
    for line in recognition.schedule_lines:
        if str(line.schedule_kind) != "REVENUE" or line.subject_type != "obligation":
            continue
        end = ends.get((line.entity, line.period_key))
        if end is None:
            raise _invariant(
                "a schedule line names a period absent from its entity's calendar",
                line.subject_key,
                rule="CV-12",
                period_key=line.period_key,
            )
        projected.setdefault(line.subject_key, []).append((end, line.amount))
    revenue = series(ctx, recognition.revenue_targets)
    balances = {
        (target.measure, target.subject_key, target.period_key): target
        for target in presentation.targets
    }
    attributions = {(item.subject_key, item.period_key): item for item in presentation.reclass}
    obligations = sorted(st.obligations, key=lambda ob: ob.subject_key)
    out: list[Target] = []
    for entity in sorted({ob.contracting_entity for ob in obligations}):
        own = [ob for ob in obligations if ob.contracting_entity == entity]
        subject_key = group_entity_subject_key(st.group_code, entity)
        for period in billing.periods(ctx, st, entity):
            t = period.end_date
            balance = {
                name: balances[(name, subject_key, period.period_key)] for name, _, _ in _BALANCES
            }
            option = ctx.policies.value(CURRENT_POLICY, entity=entity, period=period.period_key)
            nodes: dict[str, tuple[int, list[str | SourceRef], dict[str, str]]] = {}
            if option == NONE:
                for _, name, _ in _BALANCES:
                    nodes[name] = (0, [], {"as_of": t.isoformat(), "mode": "none"})
            elif option == EXPECTED_TIMING:
                h12 = dates.add_months(t, 12)
                keys: list[str] = []
                relief: list[int] = []
                for ob in own:
                    amount = _relief_12(ob, t, h12, revenue, projected)
                    if amount is not None:
                        keys.append(ob.subject_key)
                        relief.append(amount)
                liability = balance["contract_liability"]
                nodes["contract_liability_current"] = (
                    min(liability.value, max(0, sum(relief))),
                    [liability.node_id],
                    {
                        "as_of": t.isoformat(),
                        "horizon": h12.isoformat(),
                        "keys": "|".join(keys),
                        "mode": "cl",
                        "relief": "|".join(str(value) for value in relief),
                    },
                )
                current = [
                    attributions[(ob.subject_key, period.period_key)]
                    for ob in own
                    if ob.end_date is None or ob.end_date <= h12
                ]
                asset = balance["contract_asset"]
                parts = [item.asset for item in current]
                nodes["contract_asset_current"] = (
                    min(asset.value, sum(parts)),
                    [asset.node_id, *(item.node_id for item in current)],
                    {
                        "as_of": t.isoformat(),
                        "horizon": h12.isoformat(),
                        "keys": "|".join(item.subject_key for item in current),
                        "mode": "ca",
                        "parts": "|".join(str(value) for value in parts),
                    },
                )
                receivable = balance["unbilled_receivable"]
                nodes["unbilled_receivable_current"] = (
                    receivable.value,
                    [receivable.node_id],
                    {"as_of": t.isoformat(), "mode": "ur"},
                )
            else:
                raise _invariant(
                    "the current and noncurrent option is unknown",
                    subject_key,
                    rule="S10-R-24",
                    value=str(option),
                )
            for name, current_name, _ in _BALANCES:
                value, inputs, params = nodes[current_name]
                if not 0 <= value <= balance[name].value:
                    raise _invariant(
                        "a current part exceeds its balance",
                        subject_key,
                        rule="S10-INV-09",
                        period_key=period.period_key,
                        measure=current_name,
                    )
                node_id = tb.node(
                    measure=current_name,
                    subject_key=subject_key,
                    period_key=period.period_key,
                    value=value,
                    currency=ctx.txn_currency,
                    minor_unit=mu,
                    formula_id=CURRENT_FORMULA,
                    inputs=inputs,
                    params=params,
                    narrative_key=CURRENT_FORMULA.rsplit(".v", 1)[0],
                )
                out.append(
                    Target(
                        ctx.book_code,
                        entity,
                        subject_key,
                        current_name,
                        period.period_key,
                        None,
                        value,
                        None,
                        node_id,
                    )
                )
    return tuple(out)
