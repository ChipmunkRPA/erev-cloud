"""Original member proof for principal and gross control sources across report groups."""

from uuid import UUID

from . import revenue_attribution, tie_outs
from .builders import ReportParams

KEY = "opening_historical_principal_owners_v1"


def enabled(params: ReportParams) -> bool:
    if params.binding is not None and KEY not in params.binding.evidence:
        return False
    value = {"basis": "ORIGINAL_COMPUTATION_AND_PAID_HISTORY"}
    if params.binding is not None and params.binding.evidence[KEY] != value:
        raise tie_outs.invalid(
            "currency_view", "Historical principal source interpretation differs."
        )
    tie_outs.record_evidence(params, KEY, value)
    return True


def verify(
    proof: revenue_attribution.Attribution, selected: set[UUID], *, historical: bool
) -> list[str]:
    outside = {part.contract_id for part in proof.delta.movements} - selected
    if outside and (not historical or not outside <= set(proof.verified_source_owners)):
        raise ValueError(
            "Control sources outside the selected group lack verified original membership."
        )
    return sorted(map(str, outside))
