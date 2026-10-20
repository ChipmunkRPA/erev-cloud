"""Signed revenue sources from retained S12 cumulative calculation traces.

These are cumulative sources, not posted movements. A caller must reconcile the
original target, prior target and paid history before presenting posting deltas.
The source owner is independent of the obligation that recognizes the revenue.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.trace import Trace


class InvalidRevenueTrace(ValueError):
    """Revenue cannot be reproduced from its retained signed sources."""


@dataclass(frozen=True, slots=True)
class RevenueSource:
    movement_id: UUID
    contract_id: UUID
    layer_key: str
    movement_kind: str
    amount: Fraction


_ALLOWED = {
    ("CONTRACT_LIABILITY", "LIABILITY_LAYER_CONSUMED"): {
        "fx.layer.consume.fifo.v1",
        "fx.layer.consume.pro_rata.v1",
        "fx.settlement.spot.v1",
    },
    ("CONTRACT_LIABILITY", "LIABILITY_LAYER_CREATED"): {"fx.layer.create.v1"},
    ("CONTRACT_ASSET", "ASSET_LAYER_CREATED"): {"fx.asset_layer.create.v1"},
    ("CONTRACT_ASSET", "ASSET_LAYER_SETTLED"): {"fx.settlement.spot.v1"},
}


def project(
    trace: Trace,
    node_id: str,
    movements: Sequence[Mapping[Any, Any]],
    *,
    currency: str,
) -> tuple[RevenueSource, ...]:
    """Expand positive relief/asset creation and negative settlement/creation.

    Only signed revenue cumulative nodes may combine leaves. Every intermediate
    sum must reproduce its own value, including zero totals with opposing owners.
    Scope and immutable computation provenance are checked by the caller.
    """
    nodes = {node.id: node for node in trace.nodes}
    if len(nodes) != len(trace.nodes):
        raise InvalidRevenueTrace("Duplicate revenue trace node.")
    leaves: dict[str, Mapping[Any, Any]] = {}
    identities: set[UUID] = set()
    for row in movements:
        if (row["balance_role"], row["movement_kind"]) not in _ALLOWED:
            continue
        key = str(row["trace_node_id"])
        if key in leaves or row["id"] in identities:
            raise InvalidRevenueTrace("Duplicate revenue movement identity.")
        leaves[key] = row
        identities.add(row["id"])
    root = nodes.get(node_id)
    if root is None or root.formula_id != "fx.revenue_functional.v1":
        raise InvalidRevenueTrace("Original revenue cumulative target is unavailable.")
    active: set[str] = set()
    cache: dict[str, dict[str, Fraction]] = {}

    def visit(key: str) -> dict[str, Fraction]:
        if key in active:
            raise InvalidRevenueTrace("Cyclic revenue calculation source.")
        if key in cache:
            return cache[key]
        node = nodes.get(key)
        if node is None or node.currency != currency:
            raise InvalidRevenueTrace("Missing revenue source or mismatched currency.")
        amount = Fraction(node.value)
        if key in leaves:
            row = leaves[key]
            if (
                node.formula_id not in _ALLOWED[(row["balance_role"], row["movement_kind"])]
                or str(row["functional_currency"]).strip() != currency
                or Fraction(row["amount_functional"]) != amount
                or amount < 0
            ):
                raise InvalidRevenueTrace("Revenue movement differs from its retained trace.")
            values = {key: amount}
        else:
            if (
                node.formula_id != "fx.revenue_functional.v1"
                or "signs" not in node.params
                or set(node.params) - {"signs", "minor_unit"}
            ):
                raise InvalidRevenueTrace("Revenue has an unattributed calculation source.")
            signs = node.params["signs"].split("|") if node.inputs else []
            if len(signs) != len(node.inputs) or any(sign not in {"1", "-1"} for sign in signs):
                raise InvalidRevenueTrace("Invalid revenue input signs.")
            active.add(key)
            values = {}
            for child, sign in zip(node.inputs, signs, strict=True):
                if not isinstance(child, str):
                    raise InvalidRevenueTrace("Revenue source must name a retained node.")
                for leaf, value in visit(child).items():
                    values[leaf] = values.get(leaf, Fraction(0)) + int(sign) * value
            active.remove(key)
        if sum(values.values(), Fraction(0)) != amount:
            raise InvalidRevenueTrace("Signed revenue sources do not reproduce the target.")
        cache[key] = values
        return values

    return tuple(
        RevenueSource(
            movement_id=UUID(str(leaves[key]["id"])),
            contract_id=UUID(str(leaves[key]["contract_id"])),
            layer_key=str(leaves[key]["layer_key"]),
            movement_kind=str(leaves[key]["movement_kind"]),
            amount=amount,
        )
        for key, amount in sorted(visit(node_id).items())
    )
