"""Visible exceptional opening bases from retained POB evidence, never live contract reads."""

from typing import Any

from . import tie_outs
from .builders import ReportParams

KEY = "opening_relief_explanation_v1"
SOURCES = (
    "opening_relief_pob_v1",
    "opening_relief_functional_pob_v1",
    "opening_relief_reporting_pob_v1",
)
BASES = {"ZERO_GROUP_OPENING", "ZERO_CONSUMPTION", "CREATED_AFTER_OPENING"}


def controls(params: ReportParams) -> dict[str, Any]:
    if params.binding is not None:
        if KEY not in params.binding.evidence:
            return {}
        evidence = params.binding.evidence
    elif params.sources is not None:
        evidence = params.sources.evidence
    else:
        return {}
    items = []
    membership = evidence.get("opening_relief_groups_v1", {})
    for source_key in SOURCES:
        for group_key, group in sorted(evidence.get(source_key, {}).items()):
            members = group.get("members")
            if members is None:
                ids = membership.get(group_key, [])
                members = {ids[0] if len(ids) == 1 else "": group}
            for contract_id, member in sorted(members.items()):
                for subject, obligation in sorted(member.get("obligations", {}).items()):
                    absence = obligation.get("opening_absence", {})
                    basis = absence.get("basis", member.get("basis"))
                    if basis not in BASES:
                        continue
                    items.append(
                        {
                            "subject": subject,
                            "contract_id": contract_id,
                            "basis": basis,
                            "event_id": absence.get("event_id", ""),
                            "effective_date": absence.get("effective_date", ""),
                        }
                    )
    tie_outs.record_evidence(params, KEY, True)
    return {"opening_attribution_explanation": {"items": items}}
