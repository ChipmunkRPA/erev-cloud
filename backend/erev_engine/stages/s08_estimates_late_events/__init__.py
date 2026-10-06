"""Stage 08: estimate reassessment and late events (ENGINE_SPEC §8; BUILD_SPEC ENB-10 to ENB-12).

``apply`` is the Table 0.3-A handler of ``ESTIMATE_CHANGED`` (§8.2; S08-R-01 to S08-R-07). A
measure-only kind pins a version, and a reallocating kind routes the transaction price change and
adds ``TP_CHANGE`` segments with their catch-ups. ``price_at`` is the stage 04 price function bound
over its ``PobState`` (§4.2). ``AllocatedState`` carries no price, so the caller binds it
(L1-3-Q-26), and a reallocating version without it fails closed.

``assign_posting_period`` fixes the posting period of any amount (S08-R-08; called by stage 14).
``late_events`` returns the ``LATE_EVENT`` findings, the out-of-period register facts and the
POL-042 reassessment gate facts of one book (S08-R-10 to S08-R-13); Table 0.2-A names no entry
for them, so the orchestrator calls it once per book (L2-5-Q-1). ``decompose_prior_period``
returns the ``revenue_prior_period`` targets of one period (S08-R-14 to S08-R-16; called by stage
15). Registration in ``STAGES`` and ``BOUNDARY_HANDLERS`` belongs to ENB-13. The submodules follow
the BUILD_SPEC paths (``estimates``, ``routing``, ``assign``, ``late``, ``decompose``) and are
private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from typing import Final

from erev_engine.stages.s08_estimates_late_events import estimates
from erev_engine.stages.s08_estimates_late_events.assign import Assignment, assign_posting_period
from erev_engine.stages.s08_estimates_late_events.decompose import decompose_prior_period
from erev_engine.stages.s08_estimates_late_events.estimates import KIND_EFFECT, PriceAt
from erev_engine.stages.s08_estimates_late_events.late import (
    LateEventFact,
    LateEvents,
    ReassessmentGap,
    late_events,
)
from erev_engine.stages.state import AllocatedState, BookContext, EventView
from erev_engine.trace import TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "KIND_EFFECT",
    "POLICY_KEYS",
    "Assignment",
    "LateEventFact",
    "LateEvents",
    "PriceAt",
    "ReassessmentGap",
    "apply",
    "assign_posting_period",
    "decompose_prior_period",
    "late_events",
]

# ENGINE_SPEC Table 0.10-A row 08 (STAGE_POLICY_KEYS), sorted, with the POL-042 key S08-R-13 reads
# (L2-5-Q-3).
POLICY_KEYS: Final[tuple[str, ...]] = (
    "disclosure.prior_period_pob_revenue_basis",
    "estimates.change_classification",
    "estimates.versioning",
    "late_events.fx_rates",
    "late_events.posting",
    "vc.reassessment_gate",
)
FORMULA_IDS: Final[tuple[str, ...]] = (
    "estimate.catch_up.v1",
    "estimate.pin.v1",
    "estimate.prior_period.v1",
    "estimate.route.32_45.v1",
    "estimate.route.inception.v1",
    "estimate.route.inception.v2",
    "estimate.tp_delta.v1",
    "late.assign.v1",
)


def apply(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    *,
    price_at: PriceAt | None = None,
) -> AllocatedState:
    """The state after one ``ESTIMATE_CHANGED`` event (ENGINE_SPEC §8.2)."""
    return estimates.apply(ctx, st, ev, tb, price_at=price_at)
