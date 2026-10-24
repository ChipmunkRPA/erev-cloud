"""Current amounts from original maturity inputs, without allocating group asset netting."""

from collections.abc import Mapping
from typing import Any

from erev_engine import dates
from erev_engine.bundle import BookInput, InputBundle
from erev_engine.stages.state import PolicyResolver

from . import tie_outs


def current_parts(
    bundle: InputBundle,
    book: BookInput,
    row: Mapping[str, Any],
    obligations: Mapping[str, Any],
    nodes: Mapping[str, Any],
    period: tie_outs.PeriodRef,
) -> tuple[dict[str, int], dict[str, Any]]:
    policy = PolicyResolver(book.policies).value(
        "balance.current_noncurrent", entity=row["entity"], period=period.key
    )
    parts = {"contract_liability_current": 0, "contract_asset_current": 0}
    if policy == "NONE":
        return parts, {"policy": policy}
    if policy != "EXPECTED_TIMING_12_MONTHS" or (bundle.evidence_revision or 0) < 42:
        raise tie_outs.invalid("currency_view", "Acquisition lacks original maturity evidence.")
    maturity = {}
    relief = 0
    eligible = set()
    for subject, item in obligations.items():
        source = item.get("maturity")
        if (
            not isinstance(source, dict)
            or source.get("policy") != policy
            or source.get("as_of") != period.end.isoformat()
            or source.get("horizon") != dates.add_months(period.end, 12).isoformat()
            or source.get("revenue") != item["revenue"]
            or type(source.get("asset_current_eligible")) is not bool
            or not source.get("sources")
            or any(identity not in nodes for identity in source["sources"])
        ):
            raise tie_outs.invalid("currency_view", "Acquisition maturity source differs.")
        amount = source.get("expected_relief")
        if amount is not None and type(amount) is not int:
            raise tie_outs.invalid("currency_view", "Acquisition maturity amount is invalid.")
        relief += amount or 0
        eligible.add(source["asset_current_eligible"])
        maturity[subject] = source
    liability = row["lines"]["CONTRACT_LIABILITY"]["CLOSING"]
    asset = row["lines"]["CONTRACT_ASSET"]["CLOSING"]
    parts["contract_liability_current"] = min(liability, max(0, relief))
    attribution = row.get("obligation_closing", {}).get("asset_attribution")
    if asset and len(eligible) > 1 and (bundle.evidence_revision or 0) >= 43:
        expected_policy = PolicyResolver(book.policies).value(
            "position.reclass_attribution_key", entity=row["entity"], period=period.key
        )
        if (
            not isinstance(attribution, dict)
            or attribution.get("rule") != "S10-R-22"
            or attribution.get("policy") != expected_policy
            or attribution.get("as_of") != period.end.isoformat()
            or attribution.get("contract_asset") != asset
            or attribution.get("unbilled_receivable")
            != row["lines"]["UNBILLED_RECEIVABLE"]["CLOSING"]
            or not isinstance(attribution.get("parts"), dict)
            or set(attribution["parts"]) != set(obligations)
            or any(not isinstance(part, dict) for part in attribution["parts"].values())
            or attribution.get("sources")
            != sorted({identity for item in obligations.values() for identity in item["sources"]})
            or any(identity not in nodes for identity in attribution["sources"])
        ):
            raise tie_outs.invalid("currency_view", "Acquisition asset attribution source differs.")
        for role in ("contract_asset", "unbilled_receivable"):
            values = [part.get(role) for part in attribution["parts"].values()]
            if (
                any(type(value) is not int or value < 0 for value in values)
                or sum(values) != attribution[role]
            ):
                raise tie_outs.invalid(
                    "currency_view", "Acquisition asset attribution does not reconcile."
                )
        parts["contract_asset_current"] = sum(
            attribution["parts"][subject]["contract_asset"]
            for subject, source in maturity.items()
            if source["asset_current_eligible"]
        )
        return parts, {"policy": policy, "obligations": maturity, "asset_attribution": attribution}
    if asset and len(eligible) > 1:
        raise tie_outs.invalid(
            "currency_view", "Acquisition current asset requires original netting attribution."
        )
    parts["contract_asset_current"] = asset if eligible == {True} else 0
    return parts, {"policy": policy, "obligations": maturity}
