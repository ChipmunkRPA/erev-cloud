"""Stage 12 monetary-liability layers (ENGINE_SPEC_B S12-R-19 to S12-R-21; BUILD_SPEC END-2).

Private to stage 12 (DG-ENG-07). Refund liabilities, deposit liabilities and consideration payable
to a customer denominated in a currency other than the contracting entity's functional currency are
monetary items in every book (D-25b; POL-164; POLICIES ALG-08 §2.9.1):

- an increase creates a layer ``<balance role>:<global event key>`` at spot on its recognition date
  (``LIABILITY_LAYER_CREATED``). When the recognition debits the control role (JET-04b) the
  contract liability is relieved by a stage 12 debit, and round(amount × spot) − that functional
  debit posts by JET-10d on the recognition date (S12-R-19);
- a decrease, a settlement or an estimate-driven decrease, remeasures the cumulatively rounded
  carrying share of each open layer of its component to spot and consumes it at spot (JET-10d;
  S12-R-20). A release to the control role then enters S12-R-03 as a credit at spot, so a deposit
  transferred at criteria met creates a contract-liability layer dated the transfer date
  (IFRIC 22.8);
- a consideration-payable promise has no recorded settlement and stays open (S12-R-21).

When the functional currency differs from the transaction currency the unit also publishes the
cumulative functional amount of the JET-14 promised part per ``<contract>@<entity>`` (measure
``consideration_payable``, the layers created at spot), and of the JET-04b part per refund-liability
component (measure ``refund_liability``: the contract-liability relief an increase debits, less the
portion a release consumes at spot), which stage 14 takes by S14-R-01 (L6-5). A deposit flow adds
to the target of its EMOD-12 measure per ``<contract>@<entity>`` (``deposit_received_cum`` at the
layer created at spot; ``deposit_to_contract_liability_cum``, ``deposit_refunded_cum`` and
``deposit_to_revenue_cum`` at the portions consumed at spot), which JET-01b takes (L6-5).

Customer incentive assets, return assets and noncash consideration assets are nonmonetary and have
no layer (POL-164). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.stages.s12_fx_entities.layers import (
    MONETARY_ROLES,
    ControlFlow,
    Piece,
    Running,
    UnitBook,
)

__all__ = ["DIRECTIONS", "MonetaryFlow", "apply"]

DIRECTIONS: Final = frozenset({"INCREASE", "DECREASE"})
# The functional targets of the monetary parts stage 14 posts (S14-R-01; L6-5): role -> measure.
_FUNCTIONAL_MEASURES: Final[Mapping[str, str]] = MappingProxyType(
    {"CONSIDERATION_PAYABLE": "consideration_payable", "REFUND_LIABILITY": "refund_liability"}
)
# The control-role credit of a release (JET-04b release; JET-01b at criteria met).
_RELEASE_KINDS: Final[Mapping[str, str]] = MappingProxyType(
    {"REFUND_LIABILITY": "REFUND_RELEASE", "DEPOSIT_LIABILITY": "DEPOSIT_TRANSFER"}
)
# The EMOD-12 measure of each deposit flow reason, whose functional target stage 14 takes for the
# JET-01b receipt, criteria-met and refund parts (S02-R-08, S14-R-01; L6-5).
_DEPOSIT_MEASURES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "RECEIPT": "deposit_received_cum",
        "REFUND": "deposit_refunded_cum",
        "EVENT_25_7": "deposit_to_revenue_cum",
        "CRITERIA_MET": "deposit_to_contract_liability_cum",
    }
)
# The sixth EMOD-12 measure: the 25-7 recognitions at dated points (S02-R-07 (a) at T, (c) at
# ``event_c_met_on``), whose functional amount stage 14 posts as the ``TIME`` share of the
# ``CLOSE_RELEASE`` pass at their own conversion (S12-R-20, S14-R-05; D1-R04).
_DEPOSIT_TIME_MEASURE: Final = "deposit_to_revenue_time_cum"


@dataclass(frozen=True, slots=True)
class MonetaryFlow:
    """One monetary-liability flow of a contracting entity (ENGINE_SPEC_B §12.1; S12-R-19, 20).

    ``component_key`` names the balance a decrease relieves: a refund-liability component, the
    deposit or the promise. ``control`` is ``DEBIT`` when a refund-liability increase debits the
    control role (JET-04b recognition) and ``CREDIT`` when a decrease releases to it (JET-04b
    release, JET-01b at criteria met). The control side is never published again as a
    ``ControlFlow`` (L2-5-Q-10). ``reason`` records the upstream cause, for example ``ESTIMATE``,
    ``RETURN``, ``WINDOW_EXPIRY``, ``CRITERIA_MET``, ``RECEIPT`` or ``PROMISE``.
    """

    role: str
    direction: str
    entity: str  # contracting entity
    subject_key: str  # obligation or contract@entity
    component_key: str
    source_key: str
    effective_date: date
    record_seq: int | None
    amount: int
    reason: str
    control: str | None = None
    timed: bool = False  # a 25-7 recognition at a dated point (no event; D-91 (iii); D1-R04)

    def __post_init__(self) -> None:
        if self.timed and (self.reason != "EVENT_25_7" or self.role != "DEPOSIT_LIABILITY"):
            raise ValueError("only a 25-7 deposit recognition is a dated (timed) flow")
        if self.role not in MONETARY_ROLES:
            raise ValueError(f"{self.role!r} is not a monetary-liability role (POL-164)")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"unknown monetary flow direction {self.direction!r}")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount <= 0:
            raise ValueError("a monetary flow amount is a positive integer of minor units")
        if self.role == "CONSIDERATION_PAYABLE" and self.direction == "DECREASE":
            raise ValueError("consideration payable records no settlement (S12-R-21)")
        if self.control not in (None, "DEBIT", "CREDIT"):
            raise ValueError(f"unknown control side {self.control!r}")
        if self.control == "DEBIT" and (
            self.direction != "INCREASE" or self.role != "REFUND_LIABILITY"
        ):
            raise ValueError("only a refund-liability increase debits the control role (JET-04b)")
        if self.control == "CREDIT" and (
            self.direction != "DECREASE" or self.role not in _RELEASE_KINDS
        ):
            raise ValueError("only a refund or deposit decrease releases to the control role")

    @property
    def flow_key(self) -> str:
        return f"{self.source_key}#{self.direction}@{self.component_key}"


def apply(book: UnitBook, flow: MonetaryFlow, when: date) -> None:
    """One monetary-liability flow (S12-R-19, S12-R-20)."""
    if flow.direction == "INCREASE":
        _increase(book, flow, when)
    else:
        _decrease(book, flow, when)


def _increase(book: UnitBook, flow: MonetaryFlow, when: date) -> None:
    period = book.period(when)
    spot = book.rates.spot(when)
    debit: list[Piece] = []
    if flow.control == "DEBIT":
        control = ControlFlow(
            "REFUND_INCREASE",
            flow.entity,
            flow.subject_key,
            flow.source_key,
            flow.effective_date,
            flow.record_seq,
            flow.amount,
        )
        debit = book.control(control, when)
    created = book.create(
        flow.role,
        flow.amount,
        spot,
        flow.source_key,
        when,
        period,
        formula_id="fx.monetary_liability.create.v1",
        movement_kind="LIABILITY_LAYER_CREATED",
        component_key=flow.component_key,
    )
    if flow.role == "CONSIDERATION_PAYABLE":
        _functional(book, flow, flow.subject_key, 1, [created])  # JET-14 promised at spot
    if flow.role == "DEPOSIT_LIABILITY":
        _deposit_functional(book, flow, [created])  # JET-01b receipt at spot
    if flow.control != "DEBIT":
        return
    _functional(book, flow, flow.component_key, 1, debit)  # JET-04b at the historical relief
    debited = sum(piece.amount for piece in debit)
    difference = created.amount - debited
    formula_id = "fx.monetary_liability.recognition_difference.v1"
    params = {**book.conversion_params(flow.amount, spot, when), "reliefs": str(len(debit))}
    node = book.tb.node(
        measure="fx_layer_remeasured",
        subject_key=f"{created.layer_key}@{flow.flow_key}",
        period_key=period.period_key,
        value=difference,
        currency=book.fn,
        minor_unit=book.mu_fn,
        formula_id=formula_id,
        inputs=[*spot.inputs(), *(piece.node_id for piece in debit)],
        params=params,
        exact=Fraction(flow.amount, 10**book.mu_txn) * spot.value
        - Fraction(debited, 10**book.mu_fn),
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )
    book.remeasured("JET-10d", flow.role, Piece(node, difference, spot, created.layer_key))


def _decrease(book: UnitBook, flow: MonetaryFlow, when: date) -> None:
    period = book.period(when)
    spot = book.rates.spot(when)
    layers = [
        layer
        for layer in book.layers.values()
        if layer.role == flow.role
        and layer.component_key == flow.component_key
        and layer.txn_open > 0
    ]
    if sum(layer.txn_open for layer in layers) < flow.amount:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a monetary-liability decrease exceeds the open layers of its component",
            subject_key=book.unit_key,
            detail={
                "component_key": flow.component_key,
                "rule": "S12-INV-08",
                "source_key": flow.source_key,
            },
        )
    left = flow.amount
    consumed: list[Piece] = []
    for layer in layers:
        if left == 0:
            break
        take = min(layer.txn_open, left)
        consumed.append(
            book.settle(
                layer,
                take,
                spot,
                flow.flow_key,
                flow.source_key,
                when,
                period,
                formula_id="fx.monetary_liability.settle.v1",
                part="JET-10d",
            )
        )
        left -= take
    if flow.role == "DEPOSIT_LIABILITY":
        _deposit_functional(book, flow, consumed)  # JET-01b transfer, refund or 25-7 at spot
    if flow.control == "CREDIT":
        _functional(book, flow, flow.component_key, -1, consumed)  # JET-04b release at spot
        release = ControlFlow(
            _RELEASE_KINDS[flow.role],
            flow.entity,
            flow.subject_key,
            flow.source_key,
            flow.effective_date,
            flow.record_seq,
            flow.amount,
        )
        book.control(release, when, consumed)  # the release's layer at their carrying (L6-5-Q-26)


def _functional(
    book: UnitBook, flow: MonetaryFlow, subject_key: str, sign: int, pieces: list[Piece]
) -> None:
    """Add a flow to the cumulative functional target of its part (S14-R-01; L6-5).

    Nothing is published when the functional currency is the transaction currency: stage 14 then
    posts the part at rate 1.
    """
    measure = _FUNCTIONAL_MEASURES.get(flow.role)
    if measure is None or book.fn == book.txn:
        return
    running = book.functional.setdefault(
        (measure, subject_key), Running(measure, subject_key, None, None)
    )
    running.amount_txn += sign * flow.amount
    for piece in pieces:
        running.add(piece, sign)


def _deposit_functional(book: UnitBook, flow: MonetaryFlow, pieces: list[Piece]) -> None:
    """Add a deposit flow to the cumulative functional target of its EMOD-12 measure per
    ``<contract>@<entity>``: a receipt at the layer created at spot, a transfer, refund or 25-7
    recognition at the portions consumed at spot (S12-R-19, S12-R-20, S14-R-01; L6-5).

    Nothing is published when the functional currency is the transaction currency.
    """
    measure = _DEPOSIT_MEASURES.get(flow.reason)
    if measure is None:
        raise ValueError(f"a deposit flow names no EMOD-12 measure: {flow.reason!r} (S02-R-08)")
    if book.fn == book.txn:
        return
    running = book.functional.setdefault(
        (measure, flow.subject_key), Running(measure, flow.subject_key, None, None)
    )
    running.amount_txn += flow.amount
    for piece in pieces:
        running.add(piece, 1)
    if flow.timed:
        # D1-R04: the dated releases' own conversion, beside the cumulative recognition, so stage
        # 14 posts the TIME share at the settlement spot of its date (S12-R-20), not a proportion.
        timed = book.functional.setdefault(
            (_DEPOSIT_TIME_MEASURE, flow.subject_key),
            Running(_DEPOSIT_TIME_MEASURE, flow.subject_key, None, None),
        )
        timed.amount_txn += flow.amount
        for piece in pieces:
            timed.add(piece, 1)
