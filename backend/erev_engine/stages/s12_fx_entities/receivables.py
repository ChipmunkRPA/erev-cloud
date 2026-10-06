"""Stage 12 functional amounts of ``ENGINE`` mode billing (ENGINE_SPEC_B §12.1
``functional_targets``; S12-R-02; Table 14-A row JET-03 invoice; POLICIES CHK-083; lane L6-5,
FX-CHK-083).

In ``ENGINE`` billing mode stage 14 posts JET-03 per obligation from the stage 10 cumulative
``billed_unconditional_cum`` and ``sales_tax_billed_cum`` (Dr ``ACCOUNTS_RECEIVABLE`` / Cr
``CONTRACT_LIABILITY`` and ``SALES_TAX_PAYABLE``), and S14-R-01 takes the functional amount of
the part from stage 12. ``remeasure.receivable`` records each unconditional invoice as an
``ACCOUNTS_RECEIVABLE`` item at spot on its date (JET-10a′). ``close_period`` runs for one
(combination group, contracting entity, book) after the period-end steps:

- the functional amount of the receivable items created in the period is the signed sum of their
  T-CON-18 creation nodes;
- it is apportioned by largest remainder over the obligations' period movements of billing plus
  tax (``alloc.largest_remainder.v1``), so the JET-03 amounts of the obligations sum to the
  receivable created; with one invoice date in the period each obligation takes its billing at
  that spot rate;
- a cumulative functional target per obligation, measure ``billed_unconditional_cum``, is
  published at every period end through the horizon.

From a period whose billing movements differ from the receivable created (a credit memo, whose
S12-R-08 settlement difference is not built here, or billing outside the receivable flows) the unit
publishes nothing more, so stage 14 fails closed on the part (S14-R-01). Nothing is published when
the functional currency is the transaction currency: stage 14 then posts the part at rate 1.
Private to stage 12 (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Final

from erev_engine import dates
from erev_engine.money import largest_remainder
from erev_engine.stages.s12_fx_entities.layers import (
    ACCOUNTS_RECEIVABLE,
    LayerMovement,
    Piece,
    RateRef,
    Running,
    UnitBook,
)
from erev_engine.stages.state import Target

__all__ = ["BILLING_MEASURE", "TAX_MEASURE", "Billing", "close_period"]

BILLING_MEASURE: Final = "billed_unconditional_cum"  # Table 14-A JET-03 invoice input (10)
TAX_MEASURE: Final = "sales_tax_billed_cum"
_CREATED: Final = "ASSET_LAYER_CREATED"
_RECEIVABLE_CREATED: Final = "fx_receivable_created"
_MOVEMENT: Final = "fx_billing_movement"
_SHARE: Final = "fx_billing_share"
_CUMULATIVE: Final = "fx_billing_functional"
_SUM: Final = "fx.gain_loss.sum.v1"
_REMAINDER: Final = "alloc.largest_remainder.v1"

Weight = tuple[str, int, list[tuple[str, int]]]  # (obligation, movement, signed input nodes)


@dataclass(slots=True)
class Billing:
    """The running JET-03 functional targets of one unit."""

    running: dict[str, Running] = field(default_factory=dict)  # obligation subject key
    previous: dict[str, list[Target]] = field(default_factory=dict)  # last cumulative inputs
    stopped: bool = False


def close_period(
    book: UnitBook, period: dates.PeriodLike, inputs: Sequence[Target], billing: Billing
) -> None:
    """Publish the cumulative functional JET-03 targets of one period end (S12-R-02)."""
    if book.fn == book.txn or billing.stopped:
        return
    current: dict[str, list[Target]] = {}
    for item in inputs:
        if (
            item.measure in (BILLING_MEASURE, TAX_MEASURE)
            and item.entity == book.entity
            and item.period_key == period.period_key
        ):
            current.setdefault(item.subject_key, []).append(item)
    weights: list[Weight] = []
    for subject in sorted(set(current) | set(billing.previous)):
        before = billing.previous.get(subject, [])
        now = current.get(subject, before)
        movement = sum(item.value for item in now) - sum(item.value for item in before)
        if movement != 0:
            signed = [
                *((item.node_id, 1) for item in now),
                *((item.node_id, -1) for item in before),
            ]
            weights.append((subject, movement, signed))
        billing.previous[subject] = now
    created = [
        movement
        for movement in book.movements
        if movement.balance_role == ACCOUNTS_RECEIVABLE
        and movement.movement_kind == _CREATED
        and book.period(movement.effective_date).period_key == period.period_key
    ]
    total_txn = sum(movement.amount_txn for movement in created)
    if any(movement < 0 for _, movement, _ in weights) or (
        sum(movement for _, movement, _ in weights) != total_txn
    ):
        billing.stopped = True
        return
    if weights:
        pieces = _shares(book, period, created, weights)
        for (subject, movement, _), piece in zip(weights, pieces, strict=True):
            entry = billing.running.setdefault(
                subject, Running(BILLING_MEASURE, subject, None, None)
            )
            entry.amount_txn += movement
            entry.add(piece, 1)
            entry.rates.update(
                RateRef(item.rate_key, item.version_key)
                for item in created
                if item.rate_key is not None and item.version_key is not None
            )
    for subject in sorted(billing.running):
        target = book.publish(billing.running[subject], _CUMULATIVE, _SUM, period)
        book.functional_targets.append(target)


def _shares(
    book: UnitBook,
    period: dates.PeriodLike,
    created: Sequence[LayerMovement],
    weights: Sequence[Weight],
) -> list[Piece]:
    """The receivable created in the period apportioned over the obligations' movements."""
    total = sum(movement.amount_functional for movement in created)
    created_node = book.tb.node(
        measure=_RECEIVABLE_CREATED,
        subject_key=book.unit_key,
        period_key=period.period_key,
        value=total,
        currency=book.fn,
        minor_unit=book.mu_fn,
        formula_id=_SUM,
        inputs=[movement.trace_node_id for movement in created],
        params={"signs": "|".join("1" for _ in created)},
        narrative_key="fx.gain_loss.sum",
    )
    movement_nodes = [
        book.tb.node(
            measure=_MOVEMENT,
            subject_key=subject,
            period_key=period.period_key,
            value=movement,
            currency=book.txn,
            minor_unit=book.mu_txn,
            formula_id=_SUM,
            inputs=[node for node, _ in signed],
            params={"signs": "|".join(str(sign) for _, sign in signed)},
            narrative_key="fx.gain_loss.sum",
        )
        for subject, movement, signed in weights
    ]
    names = [subject for subject, _, _ in weights]
    values = [Fraction(movement) for _, movement, _ in weights]
    shares = largest_remainder(total, values, names)
    total_weight = sum(values, Fraction(0))
    rate = book.rates.spot(created[0].effective_date)
    pieces: list[Piece] = []
    for index, share in enumerate(shares):
        node = book.tb.node(
            measure=_SHARE,
            subject_key=names[index],
            period_key=period.period_key,
            value=share,
            currency=book.fn,
            minor_unit=book.mu_fn,
            formula_id=_REMAINDER,
            inputs=[created_node, *movement_nodes],
            params={"index": str(index), "keys": ",".join(names)},
            exact=Fraction(total, 10**book.mu_fn) * values[index] / total_weight,
            narrative_key="alloc.largest_remainder",
        )
        pieces.append(Piece(node, share, rate, None))
    return pieces
