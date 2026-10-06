"""Stage 12 period-end remeasurement and receivables (ENGINE_SPEC_B §12.2.3; BUILD_SPEC END-2).

Private to stage 12 (DG-ENG-07). At every period end through the horizon ``period_end`` remeasures
to the closing rate, non-reversing, against ``FX_GAIN_LOSS`` (POL-164
``ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES``):

- open asset layers (JET-10a; S12-R-09, S12-INV-04);
- open receivable items in ``ENGINE`` billing mode (JET-10a′);
- refund-liability, deposit-liability and consideration-payable layers, in every book (JET-10d;
  S12-R-11, S12-INV-08);
- contract-liability layers only under the ASC606 POL-163 override (JET-10b; S12-R-10,
  S12-INV-06).

The closing rate is read only when such a layer is open. Every period through the horizon is
remeasured at the rates of that period, and every flow converts at the rates of its own effective
date and period, so a late event lands in the cumulative targets that stage 14 posts into the first
open period (POL-181; S12-R-13). ``receivable`` keeps the ``ENGINE`` mode receivable items of stage
10 (S10-R-19; L2-5-Q-18). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.money import cumulative_posted
from erev_engine.stages.s12_fx_entities.layers import (
    ACCOUNTS_RECEIVABLE,
    CONTRACT_ASSET,
    CONTRACT_LIABILITY,
    MONETARY_ROLES,
    Layer,
    Piece,
    UnitBook,
)
from erev_engine.stages.s12_fx_entities.rates import CLOSING, to_functional

__all__ = ["RECEIVABLE_KINDS", "ReceivableFlow", "period_end", "receivable"]

RECEIVABLE_KINDS: Final = frozenset({"INVOICE", "REDUCTION"})
_POL_164: Final = frozenset({"ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES"})
_POL_181: Final = frozenset({"EFFECTIVE_DATE_RATES_CUMULATIVE_DIFFERENCE"})
_CLOSING_ASSET: Final = ("fx.remeasure.closing.v1", "ASSET_LAYER_REMEASURED")
_CLOSING_LIABILITY: Final = ("fx.remeasure.closing.v1", "LIABILITY_LAYER_REMEASURED")
_CLOSING_MONETARY: Final = (
    "fx.monetary_liability.remeasure.closing.v1",
    "LIABILITY_LAYER_REMEASURED",
)
# Balance role -> (JET-10 part, formula id, E-86 movement kind).
_PARTS: Final[Mapping[str, tuple[str, str, str]]] = MappingProxyType(
    {
        CONTRACT_ASSET: ("JET-10a", *_CLOSING_ASSET),
        ACCOUNTS_RECEIVABLE: ("JET-10a′", *_CLOSING_ASSET),
        CONTRACT_LIABILITY: ("JET-10b", *_CLOSING_LIABILITY),
        **{role: ("JET-10d", *_CLOSING_MONETARY) for role in MONETARY_ROLES},
    }
)


@dataclass(frozen=True, slots=True)
class ReceivableFlow:
    """An ``ENGINE`` mode receivable movement of one invoice (S10-R-19; JET-10a′; L2-5-Q-18).

    ``INVOICE`` records the unconditional invoice, tax included, at spot on its date. ``REDUCTION``
    is a credit memo or an applied payment; it relieves the cumulatively rounded carrying share of
    the invoice's item, because the realised difference belongs to the ERP cash application.
    """

    kind: str
    entity: str  # contracting entity
    subject_key: str  # contract@entity
    invoice_key: str  # global event key of the invoice
    source_key: str
    effective_date: date
    record_seq: int | None
    amount: int

    def __post_init__(self) -> None:
        if self.kind not in RECEIVABLE_KINDS:
            raise ValueError(f"unknown receivable flow kind {self.kind!r} (S10-R-19)")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount <= 0:
            raise ValueError("a receivable flow amount is a positive integer of minor units")

    @property
    def flow_key(self) -> str:
        return f"{self.source_key}#{self.kind}@{self.invoice_key}"


def receivable(book: UnitBook, flow: ReceivableFlow, when: date) -> None:
    """Record or reduce the receivable item of an invoice (JET-10a′)."""
    period = book.period(when)
    if flow.kind == "INVOICE":
        book.create(
            ACCOUNTS_RECEIVABLE,
            flow.amount,
            book.rates.spot(when),
            flow.source_key,
            when,
            period,
            formula_id="fx.asset_layer.create.v1",
            movement_kind="ASSET_LAYER_CREATED",
            component_key=flow.invoice_key,
        )
        return
    items = [
        layer
        for layer in book.layers.values()
        if layer.role == ACCOUNTS_RECEIVABLE
        and layer.component_key == flow.invoice_key
        and layer.txn_open > 0
    ]
    if sum(layer.txn_open for layer in items) < flow.amount:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a receivable reduction exceeds the open invoice",
            subject_key=book.unit_key,
            detail={"invoice_key": flow.invoice_key, "rule": "S10-R-19"},
        )
    left = flow.amount
    for layer in items:
        if left == 0:
            break
        take = min(layer.txn_open, left)
        _reduce(book, layer, take, flow, when, period)
        left -= take


def _reduce(
    book: UnitBook,
    layer: Layer,
    take: int,
    flow: ReceivableFlow,
    when: date,
    period: dates.PeriodLike,
) -> None:
    carrying, open_before = layer.fn_carrying, layer.txn_open
    scale = 10**book.mu_fn
    share = cumulative_posted(
        Fraction(carrying, scale), carrying, Fraction(take, open_before), book.mu_fn
    )
    formula_id = "fx.settlement.spot.v1"
    node = book.tb.node(
        measure="fx_layer_settled",
        subject_key=f"{layer.key}@{flow.flow_key}",
        period_key=period.period_key,
        value=share,
        currency=book.fn,
        minor_unit=book.mu_fn,
        formula_id=formula_id,
        inputs=[],
        params={
            "amount_txn": str(take),
            "carrying_before": str(carrying),
            "effective_date": when.isoformat(),
            "open_before": str(open_before),
            "output": "SHARE",
            "txn_minor_unit": str(book.mu_txn),
        },
        exact=Fraction(carrying, scale) * Fraction(take, open_before),
        narrative_key="fx.settlement.spot",
    )
    book.move(
        layer.key,
        ACCOUNTS_RECEIVABLE,
        "ASSET_LAYER_SETTLED",
        when,
        take,
        share,
        layer.rate,
        flow.source_key,
        None,
        node,
    )
    layer.txn_open -= take
    layer.fn_carrying = carrying - share


def period_end(book: UnitBook, period: dates.PeriodLike) -> None:
    """Remeasure the open monetary positions of one period end to its closing rate (§12.2.3)."""
    book.policy("fx.monetary_remeasurement", period.end_date, _POL_164)
    book.policy("late_events.fx_rates", period.end_date, _POL_181)
    override = book.cl_monetary(period.end_date)
    layers = [
        layer
        for layer in book.layers.values()
        if layer.txn_open > 0 and (layer.role != CONTRACT_LIABILITY or override)
    ]
    if not layers:
        return
    closing = book.rates.period_rate(CLOSING, period)
    for layer in layers:
        part, formula_id, kind = _PARTS[layer.role]
        target = to_functional(layer.txn_open, closing, book.mu_txn, book.mu_fn)
        difference = target - layer.fn_carrying
        if difference == 0:
            continue
        params = {
            **book.conversion_params(layer.txn_open, closing, period.end_date),
            "carrying_before": str(layer.fn_carrying),
        }
        node = book.tb.node(
            measure="fx_layer_remeasured",
            subject_key=layer.key,
            period_key=period.period_key,
            value=difference,
            currency=book.fn,
            minor_unit=book.mu_fn,
            formula_id=formula_id,
            inputs=closing.inputs(),
            params=params,
            exact=Fraction(layer.txn_open, 10**book.mu_txn) * closing.value
            - Fraction(layer.fn_carrying, 10**book.mu_fn),
            narrative_key=formula_id.rsplit(".v", 1)[0],
        )
        book.move(
            layer.key,
            layer.role,
            kind,
            period.end_date,
            layer.txn_open,
            difference,
            closing,
            None,
            "PERIOD_END",
            node,
        )
        layer.fn_carrying = target
        book.remeasured(part, layer.role, Piece(node, difference, closing, layer.key))
