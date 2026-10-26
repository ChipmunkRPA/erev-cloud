"""Conserved allocation of remaining original FX layers for a prospective split.

This kernel allocates existing carrying only. Newly exposed gross balances require a
separate carry-forward rule; they must never be manufactured from these remaining layers.
"""

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from erev_engine.money import largest_remainder
from erev_engine.stages.s12_fx_entities.rates import RateView


@dataclass(frozen=True, slots=True)
class OpenLayer:
    layer_key: str
    original_contract_key: str | None
    source_key: str
    source_date: date
    created_node: str
    rate: RateView
    txn_open: int
    fn_carrying: int


@dataclass(frozen=True, slots=True)
class LayerShare:
    original: OpenLayer
    destination: str
    txn_open: int
    fn_carrying: int


def allocate(
    layers: Sequence[OpenLayer],
    destination_liabilities: Mapping[str, int],
    *,
    effective_date: date,
) -> tuple[LayerShare, ...]:
    """Preserve every source layer and both currency totals, including minor-unit ties.

    Transaction allocations are controlled rounding of the original layer-by-destination
    proportional matrix. Every cell is a floor or ceiling of its exact quota, with both
    layer totals and destination totals exact. Independently rounding each layer can put
    all small layers in one destination and violate the destination's liability target.
    Functional carrying is apportioned within each original layer over its actual
    transaction portions; a zero-transaction portion cannot hide functional carrying.
    """
    ordered = sorted(layers, key=lambda layer: (layer.source_date, layer.layer_key))
    destinations = sorted(destination_liabilities)
    amounts = [destination_liabilities[key] for key in destinations]
    if (
        len({layer.layer_key for layer in ordered}) != len(ordered)
        or any(type(v) is not int or v < 0 for v in amounts)
        or any(
            type(layer.txn_open) is not int
            or layer.txn_open <= 0
            or type(layer.fn_carrying) is not int
            or layer.fn_carrying < 0
            or layer.source_date > effective_date
            or layer.rate.value <= 0
            or not layer.source_key
            or not layer.created_node
            for layer in ordered
        )
    ):
        raise ValueError(
            "Split layers require unique original sources and valid nonnegative carrying"
        )
    total = sum(layer.txn_open for layer in ordered)
    if sum(amounts) != total:
        raise ValueError("Destination liabilities differ from the original remaining FX layers")
    if not total:
        return ()
    if not destinations:
        raise ValueError("Split layers require destination liabilities")
    if len({(layer.rate.base, layer.rate.quote) for layer in ordered}) != 1:
        raise ValueError("Split layers must use one original transaction/functional currency pair")
    matrix = [[layer.txn_open * amount // total for amount in amounts] for layer in ordered]
    fractions = [[layer.txn_open * amount % total for amount in amounts] for layer in ordered]
    row_need = [layer.txn_open - sum(row) for layer, row in zip(ordered, matrix, strict=True)]
    col_need = [amount - sum(row[col] for row in matrix) for col, amount in enumerate(amounts)]
    rounded: list[set[int]] = [set() for _ in ordered]
    # Deterministic bipartite augmenting paths preserve all floor/ceiling bounds.
    # A full column may move one of its previously rounded cells to another column.
    choices = [
        sorted(
            (col for col, remainder in enumerate(row) if remainder),
            key=lambda col: (-row[col], destinations[col]),
        )
        for row in fractions
    ]
    for root, needed in enumerate(row_need):
        for _ in range(needed):
            queue = deque([root])
            visited_rows = {root}
            parent_col: dict[int, int] = {}
            parent_row: dict[int, int] = {}
            terminal = None
            while queue and terminal is None:
                row = queue.popleft()
                for col in choices[row]:
                    if col in rounded[row] or col in parent_col:
                        continue
                    parent_col[col] = row
                    if col_need[col]:
                        terminal = col
                        break
                    for prior in range(len(ordered)):
                        if col in rounded[prior] and prior not in visited_rows:
                            visited_rows.add(prior)
                            parent_row[prior] = col
                            queue.append(prior)
            if terminal is None:
                raise ValueError(
                    "Split layer rounding cannot reconcile original destination totals"
                )
            col_need[terminal] -= 1
            col = terminal
            while True:
                row = parent_col[col]
                rounded[row].add(col)
                if row == root:
                    break
                previous = parent_row[row]
                rounded[row].remove(previous)
                col = previous
    result = []
    for row, original in enumerate(ordered):
        shares = [matrix[row][col] + int(col in rounded[row]) for col in range(len(destinations))]
        functional = largest_remainder(
            original.fn_carrying, [Fraction(v) for v in shares], destinations
        )
        for destination, txn, fn in zip(destinations, shares, functional, strict=True):
            if txn:
                result.append(LayerShare(original, destination, txn, fn))
            elif fn:
                raise ValueError(
                    "A split FX share cannot carry functional value without transaction quantity"
                )
    return tuple(result)
