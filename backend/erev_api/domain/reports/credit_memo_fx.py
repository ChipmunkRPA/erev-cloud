"""Explain retained credit-memo FX using the original ordered liability reliefs.

Spot conversion is cumulatively rounded in trace input order. This conserves the
engine's once-rounded memo total without allocating by historical carrying value
or assigning an unexplained rounding remainder to an arbitrary owner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from erev_engine.formulas import FORMULAS
from erev_engine.money import round_half_up
from erev_engine.trace import SourceRef, Trace


@dataclass(frozen=True, slots=True)
class MemoPart:
    node_id: str
    relief_node_id: str
    movement: Mapping[str, Any]
    difference_minor: int
    spot_minor: int


def parts(trace: Trace, movements: Sequence[Mapping[str, Any]]) -> tuple[MemoPart, ...]:
    """Read one entity's original output movements, whose amounts are minor units.

    Every relief is matched to its immutable output and trace. Cross-entity nodes
    are skipped only when none of their reliefs belongs to this output population.
    """
    nodes = {node.id: node for node in trace.nodes}
    held = {str(item["trace_node_id"]): item for item in movements}
    if len(held) != len(movements) or len(nodes) != len(trace.nodes):
        raise ValueError("Duplicate credit-memo source identity.")
    result = []
    for node in trace.nodes:
        if node.formula_id != "fx.credit_memo_difference.v1":
            continue
        relief_ids = [item for item in node.inputs if isinstance(item, str)]
        if not any(identity in held for identity in relief_ids):
            continue
        inputs = []
        for source in node.inputs:
            if isinstance(source, SourceRef):
                if source.ref_type != "fx_rate" or source.detail.get("quote") != node.currency:
                    raise ValueError("Credit-memo rate evidence differs from its currency.")
                inputs.append(Fraction(source.detail["value"]))
            else:
                relief = nodes.get(source)
                movement = held.get(source)
                if (
                    relief is None
                    or movement is None
                    or relief.currency != node.currency
                    or movement["movement_kind"] != "LIABILITY_LAYER_CONSUMED"
                    or movement["balance_role"] != "CONTRACT_LIABILITY"
                    or movement["functional_currency"] != node.currency
                    or Fraction(relief.value)
                    != Fraction(
                        int(movement["amount_functional"]), 10 ** int(node.params["minor_unit"])
                    )
                    or movement["effective_date"] != node.params["effective_date"]
                ):
                    raise ValueError("Credit-memo relief differs from its retained movement.")
                inputs.append(Fraction(relief.value))
        expected = FORMULAS[node.formula_id](inputs, node.params)
        if expected != Fraction(node.value):
            raise ValueError("Credit-memo difference fails original formula verification.")
        if len(set(relief_ids)) != len(relief_ids) or len(relief_ids) != int(
            node.params["reliefs"]
        ):
            raise ValueError("Credit-memo relief population is ambiguous.")
        mu, txn_mu = int(node.params["minor_unit"]), int(node.params["txn_minor_unit"])
        rate = Fraction(node.params["rate"])
        quantity = previous = difference = 0
        for identity in relief_ids:
            movement = held[identity]
            take = int(movement["amount_txn"])
            if take <= 0 or not movement.get("source_key") or not movement.get("contract_key"):
                raise ValueError("Credit-memo relief lacks positive dated ownership.")
            quantity += take
            converted = round_half_up(Fraction(quantity, 10**txn_mu) * rate, mu)
            spot = converted - previous
            delta = spot - int(movement["amount_functional"])
            result.append(MemoPart(node.id, identity, movement, delta, spot))
            previous = converted
            difference += delta
        if quantity != int(node.params["amount_txn"]) or Fraction(difference, 10**mu) != expected:
            raise ValueError("Credit-memo source quantities do not reproduce the difference.")
    return tuple(result)
