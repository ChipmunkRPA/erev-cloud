"""Nonposting current-liability classification using the original layer release policy."""

from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from erev_engine.money import cumulative_posted, largest_remainder, round_half_up


def classify(
    layers: Sequence[Mapping[str, Any]],
    current: int,
    *,
    policy: str,
    minor_unit: int,
    monetary: bool = False,
) -> tuple[dict[str, int | str], ...]:
    """Keep engine insertion order for FIFO and engine key order for PRO_RATA.

    This values a classification of the existing carrying amount; it does not
    forecast new layers, future exchange rates or future postings.
    """
    if policy not in {"FIFO", "PRO_RATA"} or not 0 <= current <= sum(x["txn_open"] for x in layers):
        raise ValueError("Invalid current liability quantity or layer release policy")
    ordered = list(layers) if policy == "FIFO" else sorted(layers, key=lambda x: x["layer_key"])
    if policy == "FIFO":
        takes = []
        left = current
        for layer in ordered:
            take = min(left, layer["txn_open"])
            takes.append(take)
            left -= take
    else:
        takes = (
            largest_remainder(
                current,
                [Fraction(x["txn_open"]) for x in ordered],
                [x["layer_key"] for x in ordered],
            )
            if current
            else [0] * len(ordered)
        )
    result = []
    for layer, take in zip(ordered, takes, strict=True):
        if not take:
            value = 0
        elif take == layer["txn_open"]:
            value = layer["functional_carrying"]
        elif monetary:
            value = min(
                layer["functional_carrying"],
                round_half_up(
                    Fraction(layer["functional_carrying"], 10**minor_unit)
                    * Fraction(take, layer["txn_open"]),
                    minor_unit,
                ),
            )
        else:
            created = [m for m in layer["movements"] if m["kind"] == "LIABILITY_LAYER_CREATED"]
            if len(created) != 1:
                raise ValueError("Original liability creation basis is ambiguous")
            original = created[0]
            quantity, carrying = original["amount_txn"], original["amount_functional"]
            consumed = quantity - layer["txn_open"]
            exact = Fraction(carrying, 10**minor_unit)
            before = cumulative_posted(exact, carrying, Fraction(consumed, quantity), minor_unit)
            if carrying - before != layer["functional_carrying"]:
                raise ValueError("Original historical liability carrying does not reconcile")
            value = (
                cumulative_posted(exact, carrying, Fraction(consumed + take, quantity), minor_unit)
                - before
            )
        result.append(
            {
                "layer_key": layer["layer_key"],
                "current_txn": take,
                "current_functional": value,
                "noncurrent_functional": layer["functional_carrying"] - value,
            }
        )
    return tuple(result)
