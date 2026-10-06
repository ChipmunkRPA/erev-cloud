"""Stage 07: onboarding and migration (ENGINE_SPEC §7; BUILD_SPEC ENB-9).

``apply`` is the Table 0.3-A handler of ``OPENING_BALANCE_ESTABLISHED`` (S07-R-01). It checks the
payload (S07-R-03) and then establishes cutover state. A business combination in the IFRS15 book
apportions the acquisition-date fair value of the contract liability (S07-R-08). Otherwise POL-210
decides: ``OPENING_BALANCES_AT_CUTOVER`` gives each obligation a ``PROSPECTIVE`` segment with cause
``OPENING_BALANCE`` and an opening baseline (S07-R-04, S07-R-05); ``RECOMPUTE_FROM_INCEPTION``
creates no segment and measures the revenue ``ONBOARDING_DIFFERENCE`` once per obligation
(S07-R-06, S07-R-07; S07-INV-03). An inconsistent payload returns the state with its
``OPENING_BALANCE_INCONSISTENT`` findings and no segment, and the findings block the computation
(CV-15, CV-42). ``baseline_of`` and ``differences_of`` read what stage 14 posts against.

The submodules follow the BUILD_SPEC ENB-9 paths (``opening``, ``difference``,
``business_combination``) rather than the module list of ENGINE_SPEC §7.1, and are private
(DG-ENG-07). Registration in ``STAGES`` and ``BOUNDARY_HANDLERS`` belongs to ENB-13. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.stages.s07_onboarding import business_combination, difference, opening
from erev_engine.stages.s07_onboarding.opening import (
    OnboardingDifference,
    OpeningBaseline,
    baseline_of,
    differences_of,
)
from erev_engine.stages.state import AllocatedState, BookContext, EventView
from erev_engine.trace import TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "POLICY_KEYS",
    "OnboardingDifference",
    "OpeningBaseline",
    "apply",
    "baseline_of",
    "differences_of",
]

# ENGINE_SPEC Table 0.10-A row 07 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "bc.acquired_contract_measurement",
    "bc.expedient_modification_aggregation",
    "bc.expedient_ssp_at_acquisition",
    "migration.material_right_convention",
    "onboarding.method",
)
FORMULA_IDS: Final[tuple[str, ...]] = (
    "onb.baseline.v1",
    "onb.difference.v1",
    "onb.ifrs_fair_value_split.v1",
    "onb.opening_segment.v1",
)


def apply(ctx: BookContext, st: AllocatedState, ev: EventView, tb: TraceBuilder) -> AllocatedState:
    """The state after ``OPENING_BALANCE_ESTABLISHED`` (ENGINE_SPEC §7.2)."""
    inception = next(
        (
            view.header.inception_date
            for view in st.contracts
            if view.header.external_id == ev.contract_key
        ),
        None,
    )
    payload = opening.parse(ev, inception=inception)
    method = ctx.policies.value("onboarding.method", contract=ev.contract_key)
    if method not in (opening.OPENING_BALANCES, opening.RECOMPUTE):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the onboarding method is unknown",
            subject_key=ev.contract_key,
            detail={"event_key": ev.event_key, "rule": "POL-210"},
        )
    findings = opening.consistency(ctx, st, ev, payload)
    if findings:
        return replace(st, findings=(*st.findings, *findings))
    if payload.reason == opening.BUSINESS_COMBINATION and ctx.framework == "IFRS15":
        measurement = ctx.policies.value(
            "bc.acquired_contract_measurement", contract=ev.contract_key
        )
        if measurement != business_combination.FAIR_VALUE_IFRS3:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "an IFRS15 book measures acquired contracts at fair value",
                subject_key=ev.contract_key,
                detail={"event_key": ev.event_key, "rule": "POL-215"},
            )
        return business_combination.ifrs_fair_value(ctx, st, ev, payload, tb)
    if method == opening.OPENING_BALANCES:
        return opening.establish(ctx, st, ev, payload, tb)
    return difference.baseline(ctx, st, ev, payload, tb)
