"""Read the engine's period-end presentation shares, retaining their revenue dates.

The trace is immutable and belongs to the exact contract version selected by the report.
Amounts are attributed by the engine, never reconstructed from close-run ledger postings.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from erev_engine.trace import Trace

from erev_api.domain.reports import tie_outs


def attributions(
    trace: Trace | None,
    *,
    contract: str,
    entity: str,
    currency: str,
    end: date,
    functional_currency: str | None = None,
) -> list[tuple[date, str, Decimal]]:
    """Latest measured period at/before ``end`` for each obligation of the member.

    Older traces without the explicit aging payload refuse. Reading the latest attribution
    per obligation also carries the final measured balance forward after the calendar ends.
    """
    if trace is None:
        raise tie_outs.invalid("period_key", "The selected version has no aging trace.")
    latest: dict[str, tuple[date, date, Decimal, Decimal]] = {}
    nodes = {node.id: node for node in trace.nodes}
    if functional_currency not in (None, currency) and len(nodes) != len(trace.nodes):
        raise tie_outs.invalid("period_key", "The aging trace repeats a node identity.")
    for node in trace.nodes:
        if node.measure != "netting_reclass_amount" or node.id.endswith(":-"):
            continue
        params = node.params
        # All period nodes in a new trace carry this payload, including zero attributions.
        if "aging_contract" not in params:
            raise tie_outs.invalid(
                "period_key", "The selected version predates aging attribution support."
            )
        if params["aging_contract"] != contract or params.get("aging_entity") != entity:
            continue
        try:
            as_of = date.fromisoformat(params["as_of"])
            if as_of > end:
                continue
            revenue_on = date.fromisoformat(params["aging_revenue_date"])
            receivable = Decimal(params["aging_receivable"])
            asset = Decimal(params["aging_asset"])
            key = params["key"]
            if (
                node.currency != currency
                or revenue_on > as_of
                or not receivable.is_finite()
                or not asset.is_finite()
                or receivable < 0
                or asset < 0
                or receivable + asset != Decimal(node.value)
            ):
                raise ValueError("Inconsistent attribution")
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise tie_outs.invalid(
                "period_key", "The selected version has invalid aging data."
            ) from exc
        if functional_currency is not None and functional_currency != currency:
            amounts = []
            period_key = node.id.rsplit(":", 1)[-1]
            for role, amount in (("UNBILLED_RECEIVABLE", receivable), ("CONTRACT_ASSET", asset)):
                if amount == 0:
                    amounts.append(Decimal(0))
                    continue
                share = nodes.get(f"fx_reclass_share:{key}#{role}:{period_key}")
                if (
                    share is None
                    or share.measure != "fx_reclass_share"
                    or share.currency != functional_currency
                    or share.formula_id != "alloc.largest_remainder.v1"
                    or node.id not in share.inputs
                ):
                    raise tie_outs.invalid(
                        "currency_view", "Functional aging share is unavailable."
                    )
                try:
                    value = Decimal(share.value)
                except InvalidOperation as exc:
                    raise tie_outs.invalid(
                        "currency_view", "Functional aging share is invalid."
                    ) from exc
                if not value.is_finite() or value < 0:
                    raise tie_outs.invalid("currency_view", "Functional aging share is invalid.")
                amounts.append(value)
            receivable, asset = amounts
        previous = latest.get(key)
        if previous is None or previous[0] < as_of:
            latest[key] = (as_of, revenue_on, receivable, asset)
    return [
        (revenue_on, role, amount)
        for _, revenue_on, receivable, asset in latest.values()
        for role, amount in (("UNBILLED_RECEIVABLE", receivable), ("CONTRACT_ASSET", asset))
        if amount != 0
    ]
