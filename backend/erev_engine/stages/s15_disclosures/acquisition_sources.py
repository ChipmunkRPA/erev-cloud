"""Admission of original contracting-entity acquisition control sources."""

from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.state import ObligationState


def intercompany_enabled(records: object, ob: ObligationState) -> bool:
    if not getattr(records, "acquisition_intercompany_sources", False):
        return False
    baseline = baseline_of(ob)
    return bool(
        ob.principal_agent.value == "PRINCIPAL"
        and ob.opening is not None
        and ob.opening.get("reason") == "BUSINESS_COMBINATION"
        and baseline is not None
        and (
            baseline.method == "OPENING_BALANCES_AT_CUTOVER"
            or (
                baseline.method == "RECOMPUTE_FROM_INCEPTION"
                and (ob.subject_key, baseline.cutover_date)
                in getattr(records, "recomputed_acquisition_closings", {})
            )
        )
    )
