"""Expose unresolved opening attribution without inventing zero or a complete total."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from . import tie_outs
from .builders import ReportParams

KEY = "opening_attribution_availability_v1"
NOTE = "Opening attribution unavailable: mixed original sources; net revenue is complete."


def enabled(params: ReportParams) -> bool:
    return params.binding is None or KEY in params.binding.evidence


def unresolved(facts: Mapping[str, Any]) -> list[str]:
    subjects = set(facts.get("unresolved_subjects", []))
    for member in facts.get("members", {}).values():
        subjects.update(unresolved(member))
    return sorted(subjects)


def mask_facts(facts: dict[str, Any]) -> None:
    subjects = unresolved(facts)
    if subjects:
        facts["unresolved_subjects"] = subjects
        if "relief" in facts:
            facts["relief"] = None
        if "eligible_relief_capped_by_group" in facts:
            facts["eligible_relief_capped_by_group"] = None


def apply(params: ReportParams, rows: list[dict[str, Any]]) -> tuple[set[str], dict[str, Any]]:
    if not enabled(params):
        return set(), {}
    unavailable = []
    known: dict[str, Decimal] = {}
    for row in rows:
        subjects = row.pop("_opening_unavailable", [])
        if subjects:
            row["revenue_from_opening"] = None
            row["summary"] = ((row.get("summary") or "") + " " + NOTE).strip()
            unavailable.append(
                {
                    "row_key": row["row_key"],
                    "currency": row["currency"],
                    "subjects": subjects,
                }
            )
        else:
            value = row["revenue_from_opening"]
            known[row["currency"]] = known.get(row["currency"], Decimal(0)) + Decimal(
                value["amount"]
            )
    evidence = {
        "status": "INCOMPLETE" if unavailable else "COMPLETE",
        "unavailable_rows": sorted(unavailable, key=lambda item: item["row_key"]),
        "known_subtotals": tie_outs.by_currency(known),
    }
    if params.binding is not None and params.binding.evidence[KEY] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Opening attribution availability differs from retained evidence."
        )
    tie_outs.record_evidence(params, KEY, evidence)
    return {item["currency"] for item in unavailable}, {
        "opening_attribution_availability": evidence
    }
