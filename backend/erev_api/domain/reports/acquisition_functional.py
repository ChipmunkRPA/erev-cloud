"""Project requested totals from the authenticated original cutover observation."""

from collections.abc import Sequence
from decimal import Decimal

from . import acquisition_balances, tie_outs
from .builders import ReportParams


def project(
    params: ReportParams,
    row: tie_outs.BalanceRow,
    at: tie_outs.PeriodRef,
    *,
    currency: str,
    measures: Sequence[str],
) -> dict[str, Decimal] | None:
    # balances_at has already authenticated the original files and checked the
    # snapshot against original nodes before retaining this exact endpoint.
    evidence = (
        params.binding.evidence
        if params.binding is not None
        else params.sources.evidence
        if params.sources is not None
        else {}
    )
    identity = (
        f"{acquisition_balances.KEY}:{row.version_id}:{row.contract_id}:{row.entity_id}:{at.key}"
    )
    original = evidence.get(identity)
    if original is None:
        return None
    snapshot = original["snapshot"]
    functional = snapshot.get("functional")
    if functional is None:
        return None
    if (
        functional["currency"] != currency
        or snapshot["currency"] != row.currency
        or original["requested_period_key"] != at.key
        or any(Decimal(value) != row.value(role) for role, value in original["amounts"].items())
    ):
        raise tie_outs.invalid("currency_view", "Original acquisition functional endpoint differs.")
    missing = set(measures) - functional["amounts"].keys()
    if missing:
        raise tie_outs.invalid(
            "currency_view",
            "Original acquisition functional measures are unavailable: "
            + ", ".join(sorted(missing)),
        )
    scale = Decimal(10) ** -functional["minor_unit"]
    return {role: Decimal(functional["amounts"][role]) * scale for role in measures}


def liability_carrying(
    params: ReportParams, row: tie_outs.BalanceRow, at: tie_outs.PeriodRef
) -> Decimal | None:
    """Original open layers supply a singleton's source side of the member bridge."""
    evidence = (
        params.binding.evidence
        if params.binding is not None
        else params.sources.evidence
        if params.sources is not None
        else {}
    )
    identity = (
        f"{acquisition_balances.KEY}:{row.version_id}:{row.contract_id}:{row.entity_id}:{at.key}"
    )
    original = evidence.get(identity)
    if original is None:
        return None
    functional = original["snapshot"].get("functional", {})
    if "liability_layers" not in functional:
        return None
    if functional["currency"] != row.currency:
        raise tie_outs.invalid("currency_view", "Original liability layer currency differs.")
    scale = Decimal(10) ** -functional["minor_unit"]
    return sum(
        (Decimal(layer["functional_carrying"]) * scale for layer in functional["liability_layers"]),
        Decimal(0),
    )
