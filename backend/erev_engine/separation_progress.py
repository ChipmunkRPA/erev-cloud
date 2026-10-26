"""Remaining-service progress for retained specialist recognition layers."""

import json
from collections.abc import Mapping, Sequence
from fractions import Fraction


def fraction(inputs: Sequence[Fraction], params: Mapping[str, str]) -> Fraction:
    if params["mode"] == "RATIO":
        if len(inputs) != 1:
            raise ValueError("Separation progress lacks its original measurement")
        base = Fraction(params["base"])
        return (
            min(Fraction(1), max(Fraction(0), (inputs[0] - base) / (1 - base)))
            if base < 1
            else Fraction(0)
        )
    events = json.loads(params["events"])
    has_expected = params["expected_input"] == "true"
    if len(inputs) != len(events) + int(has_expected):
        raise ValueError("Separation unit sources are incomplete")
    layers: list[list[Fraction | bool]] = []
    lost = Fraction(0)
    for quantity, (kind, new) in zip(inputs[: len(events)], events, strict=True):
        if quantity < 0:
            raise ValueError("Separation unit quantity must be nonnegative")
        if kind == "DELIVERY_RECORDED":
            layers.append([quantity, new])
            continue
        before = sum((Fraction(q) for q, new in layers if new), Fraction(0))
        consume(layers, quantity, params["policy"])
        lost += before - sum((Fraction(q) for q, new in layers if new), Fraction(0))
    if has_expected:
        before = sum((Fraction(q) for q, new in layers if new), Fraction(0))
        consume(layers, inputs[-1], params["policy"])
        lost += before - sum((Fraction(q) for q, new in layers if new), Fraction(0))
    remaining = Fraction(params["remaining_quantity"])
    current = (
        lost
        if params.get("metric") == "LOST"
        else sum((Fraction(qty) for qty, new in layers if new), Fraction(0))
    )
    return min(Fraction(1), current / remaining) if remaining else Fraction(0)


def consume(layers: list[list[Fraction | bool]], quantity: Fraction, policy: str) -> None:
    total = sum((Fraction(layer[0]) for layer in layers), Fraction(0))
    if not 0 <= quantity <= total:
        raise ValueError("Return quantities exceed retained delivery layers")
    if policy == "PRO_RATA":
        for layer in layers:
            layer[0] = Fraction(layer[0]) * (1 - quantity / total) if total else Fraction(0)
    elif policy == "FIFO":
        left = quantity
        for layer in layers:
            take = min(left, Fraction(layer[0]))
            layer[0] = Fraction(layer[0]) - take
            left -= take
    else:
        raise ValueError("Unknown original release policy")
