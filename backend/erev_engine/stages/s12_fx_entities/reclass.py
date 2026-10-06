"""Stage 12 functional amounts of the netting reclass (ENGINE_SPEC_B §12.2.3 S12-R-09; Table 14-A
row JET-06, "functional (12)"; lane L5-5, LATE-POL-181).

``close_period`` runs for one (combination group, contracting entity, book) after the period-end
remeasurement and ``UnitBook.close_period``:

- the remeasured functional carrying of the open contract-asset layers is the signed sum of their
  T-CON-18 movement nodes (created and remeasured add, settled subtracts) and must equal the layer
  carrying (fail closed otherwise);
- that carrying is apportioned over the stage 10 reclass attributions of the period (§10.2.7,
  ``netting_reclass_amount`` per obligation with the reclass role as ``cause``) by largest remainder
  (``alloc.largest_remainder.v1``);
- a cumulative functional target per obligation and role is published at every period end through
  the horizon, as stage 14 accumulates the attributions into the JET-06 part target. Its subject
  key is ``<obligation subject key>#<role>``, and ``balance_role`` names the role.

Nothing is published when the functional currency is the transaction currency: stage 14 then
posts the part amount at rate 1. Private to stage 12 (DG-ENG-07). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.money import largest_remainder
from erev_engine.stages.s12_fx_entities.layers import CONTRACT_ASSET, Piece, Running, UnitBook
from erev_engine.stages.s12_fx_entities.rates import CLOSING
from erev_engine.stages.state import Target

__all__ = ["MEASURE", "close_period"]

MEASURE: Final = "netting_reclass_amount"  # §10.2.7 attribution measure and the target measure
_CARRYING: Final = "fx_asset_carrying"
_SHARE: Final = "fx_reclass_share"
_CUMULATIVE: Final = "fx_reclass_functional"
_SUM: Final = "fx.gain_loss.sum.v1"
_REMAINDER: Final = "alloc.largest_remainder.v1"
# The sign of each contract-asset movement kind in the layer carrying amount (E-86).
_SIGNS: Final[Mapping[str, int]] = MappingProxyType(
    {"ASSET_LAYER_CREATED": 1, "ASSET_LAYER_REMEASURED": 1, "ASSET_LAYER_SETTLED": -1}
)

RunningKey = tuple[str, str]  # (obligation subject key, reclass role)


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=subject_key,
        detail={**detail, "rule": "S12-R-09"},
    )


def close_period(
    book: UnitBook,
    period: dates.PeriodLike,
    attributions: Sequence[Target],
    running: MutableMapping[RunningKey, Running],
) -> None:
    """Publish the cumulative functional reclass targets of one period end (S12-R-09)."""
    if book.fn == book.txn:
        return
    found = sorted(
        (
            item
            for item in attributions
            if item.measure == MEASURE
            and item.entity == book.entity
            and item.period_key == period.period_key
            and item.cause is not None
            and item.value != 0
        ),
        key=lambda item: (item.subject_key, str(item.cause)),
    )
    if found:
        for item, piece in zip(found, _shares(book, period, found), strict=True):
            role = str(item.cause)
            key = (item.subject_key, role)
            entry = running.setdefault(
                key, Running(MEASURE, f"{item.subject_key}#{role}", None, role)
            )
            entry.amount_txn += item.value
            entry.add(piece, 1)
    for key in sorted(running):
        target = book.publish(running[key], _CUMULATIVE, _SUM, period)
        book.functional_targets.append(target)


def _shares(book: UnitBook, period: dates.PeriodLike, found: Sequence[Target]) -> list[Piece]:
    """The carrying of the open contract-asset layers apportioned over the attributions."""
    open_layers = {
        layer.key: layer
        for layer in book.layers.values()
        if layer.role == CONTRACT_ASSET and layer.txn_open > 0
    }
    if not open_layers:
        raise _invariant(
            "a netting reclass names no open contract-asset layer",
            book.unit_key,
            period_key=period.period_key,
        )
    inputs: list[str] = []
    signs: list[int] = []
    total = 0
    for movement in book.movements:
        if movement.layer_key not in open_layers:
            continue
        sign = _SIGNS.get(movement.movement_kind)
        if sign is None:
            raise _invariant(
                "a contract-asset movement has no sign in the carrying amount",
                book.unit_key,
                movement_kind=movement.movement_kind,
            )
        inputs.append(movement.trace_node_id)
        signs.append(sign)
        total += sign * movement.amount_functional
    carrying = sum(layer.fn_carrying for layer in open_layers.values())
    if total != carrying:
        raise _invariant(
            "the contract-asset movements disagree with the layer carrying",
            book.unit_key,
            carrying=str(carrying),
            movements=str(total),
            period_key=period.period_key,
        )
    carrying_node = book.tb.node(
        measure=_CARRYING,
        subject_key=book.unit_key,
        period_key=period.period_key,
        value=carrying,
        currency=book.fn,
        minor_unit=book.mu_fn,
        formula_id=_SUM,
        inputs=inputs,
        params={"signs": "|".join(str(sign) for sign in signs)},
        narrative_key="fx.gain_loss.sum",
    )
    closing = book.rates.period_rate(CLOSING, period)
    names = [f"{item.subject_key}#{item.cause}" for item in found]
    weights = [Fraction(item.value) for item in found]
    shares = largest_remainder(carrying, weights, names)
    total_weight = sum(weights, Fraction(0))
    pieces: list[Piece] = []
    for index, (share, weight) in enumerate(zip(shares, weights, strict=True)):
        node = book.tb.node(
            measure=_SHARE,
            subject_key=names[index],
            period_key=period.period_key,
            value=share,
            currency=book.fn,
            minor_unit=book.mu_fn,
            formula_id=_REMAINDER,
            inputs=[carrying_node, *(other.node_id for other in found)],
            params={"index": str(index), "keys": ",".join(names)},
            exact=Fraction(carrying, 10**book.mu_fn) * weight / total_weight,
            narrative_key="alloc.largest_remainder",
        )
        pieces.append(Piece(node, share, closing, None))
    return pieces
