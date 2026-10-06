"""Stage 07 recomputation from inception (ENGINE_SPEC §7.3 S07-R-06, S07-R-07, §7.5; ENB-9).

Under POL-210 ``RECOMPUTE_FROM_INCEPTION`` the contract replays from inception with its full event
history, so ``OPENING_BALANCE_ESTABLISHED`` creates no segment. For each obligation it records the
imported cumulative revenue as the opening baseline and measures ``ONBOARDING_DIFFERENCE`` =
recomputed posted target at the cutover − imported cumulative, once per obligation and role
(S07-INV-03). The recomputed target is the stage 09 target at the event's ENG-06 position, after
manual adjustments and holds (CV-63; S09-R-41). This item measures the revenue relief role; billing
in ``ENGINE`` mode, deposits, refund liabilities and return assets are targets of stages 04 and 10,
which are not built in this lane (L1-3-Q-27). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from erev_engine import money
from erev_engine.stages.s07_onboarding import opening
from erev_engine.stages.s09_recognition import target_at_position
from erev_engine.stages.state import AllocatedState, BookContext, EventView, ObligationState
from erev_engine.trace import TraceBuilder

__all__ = ["DIFFERENCE_FORMULA", "REVENUE_ROLE", "UNPOSTED_CODE", "baseline"]

DIFFERENCE_FORMULA: Final = "onb.difference.v1"
REVENUE_ROLE: Final = "REVENUE"
# D-97 (11), narrowed by ONB-DIFF-ROLES: raised by stage 14 for a role key its template cannot map.
UNPOSTED_CODE: Final = "ONBOARDING_DIFFERENCE_UNPOSTED"


def baseline(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    payload: opening.Payload,
    tb: TraceBuilder,
) -> AllocatedState:
    """S07-R-06 and S07-R-07: baselines and revenue onboarding differences, no segment.

    Stage 14 posts each difference once at the cutover (S07-R-07 rev 1.17; ENGINE_SPEC_B
    S14-R-26); a role key its template cannot map fails closed there with
    ``ONBOARDING_DIFFERENCE_UNPOSTED`` (D-97 (11), narrowed by ONB-DIFF-ROLES).
    """
    mu = opening.minor_unit(ctx)
    cutover = payload.cutover_date.isoformat()
    replaced: dict[str, ObligationState] = {}
    for ob in opening.contract_obligations(st, ev):
        existing = opening.differences_of(ob)
        if any(item.role == REVENUE_ROLE for item in existing):
            continue  # S07-INV-03: posted at most once per (obligation, role)
        row = payload.rows[ob.obligation_key]
        revenue = row.value("revenue_cum")
        imported = money.round_half_up(revenue, mu)
        base_node = tb.node(
            measure=f"opening_revenue_cum@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=imported,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=opening.BASELINE_FORMULA,
            inputs=[opening.payload_ref(ev, ob.obligation_key, "revenue_cum", revenue)],
            params={"cutover_date": cutover, "mode": "imported"},
            exact=revenue,
            narrative_key=opening.BASELINE_FORMULA.rsplit(".v", 1)[0],
        )
        target = target_at_position(ctx, st, ob, payload.cutover_date, event=ev, adjusted=True)
        amount = target.value - imported
        node_id = tb.node(
            measure=f"onboarding_difference@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=amount,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=DIFFERENCE_FORMULA,
            inputs=[base_node],
            params={
                "cutover_date": cutover,
                "imported": str(imported),
                "recomputed": str(target.value),
                "role": REVENUE_ROLE,
            },
            narrative_key=DIFFERENCE_FORMULA.rsplit(".v", 1)[0],
        )
        difference = opening.OnboardingDifference(
            subject_key=ob.subject_key,
            role=REVENUE_ROLE,
            cutover_date=payload.cutover_date,
            event_key=ev.event_key,
            imported=imported,
            recomputed=target.value,
            amount=amount,
            node_id=node_id,
        )
        record = opening.OpeningBaseline(
            subject_key=ob.subject_key,
            cutover_date=payload.cutover_date,
            revenue_cum=imported,
            billed_cum=money.round_half_up(row.value("billed_cum"), mu),
            deposit_liability=row.optional("deposit_liability", mu),
            pre_standard_revenue_cum=money.round_half_up(row.value("pre_standard_revenue_cum"), mu),
            method=opening.RECOMPUTE,
            node_id=base_node,
            absent_members=row.absent(opening.OPTIONAL_MEMBERS),
        )
        replaced[ob.subject_key] = replace(
            ob, opening=opening.view(row, payload, ev, record, (*existing, difference))
        )
    return replace(st, obligations=tuple(replaced.get(ob.subject_key, ob) for ob in st.obligations))
