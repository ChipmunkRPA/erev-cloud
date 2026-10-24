"""Apply retained signed acquisition changes without reclassifying them as revenue."""

from collections.abc import MutableMapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from . import tie_outs

if TYPE_CHECKING:
    from .builders.contract_balance_rollforward import Flow


def apply(
    flow: "Flow",
    layers: list[list[Any]],
    assets: MutableMapping[str, Decimal],
    line: MutableMapping[str, Decimal],
) -> None:
    liability = "contract_liability"
    amounts = dict(flow.acquisition_changes)
    if (
        flow.acquisition_balances
        or flow.amount != 0
        or flow.is_revenue
        or flow.asset_fx
        or flow.liability_fx
        or len(flow.acquisition_changes) != len(amounts)
        or set(amounts) != set(tie_outs.ROLLFORWARD_BALANCES)
        or any(not value.is_finite() for value in amounts.values())
    ):
        raise tie_outs.invalid("currency_view", "Invalid original signed acquisition changes.")
    for role, held in assets.items():
        if held + amounts[role] < 0:
            raise tie_outs.invalid(
                "currency_view", "Acquisition exceeds its original asset balance."
            )
    change = amounts[liability]
    selected = (
        layers
        if flow.layer_key is None
        else [layer for layer in layers if layer[2] == flow.layer_key]
    )
    if change < 0:
        if flow.layer_key is not None and len(selected) != 1:
            raise tie_outs.invalid("currency_view", "Acquisition liability source is ambiguous.")
        if sum((layer[1] for layer in selected), Decimal(0)) < -change:
            raise tie_outs.invalid("currency_view", "Acquisition exceeds its original liability.")
        need = -change
        for layer in selected:
            take = min(layer[1], need)
            layer[1] -= take
            need -= take
            if need == 0:
                break
    elif change > 0:
        if flow.layer_key is not None and selected:
            raise tie_outs.invalid("currency_view", "Acquisition liability layer already exists.")
        layers.append(["NEW", change, flow.layer_key])
    for role in assets:
        assets[role] += amounts[role]
    for role, amount in amounts.items():
        line[role] += amount
