"""Stage 12 contract-liability and asset layers (ENGINE_SPEC_B §12.2.2; BUILD_SPEC END-1, END-2).

Private to stage 12 (DG-ENG-07). ``UnitBook`` holds the layers of one (combination group,
contracting entity, book) inside one compute call and processes the control-role flows of S12-R-03
(POLICIES ALG-08 §2.9.1):

- a credit first settles open asset layers in creation order, each portion remeasured to spot
  before it is settled (JET-10a settlement), and creates a contract-liability layer at spot on its
  layer date for any remainder (POL-160; S12-R-04);
- a debit relieves open liability layers in POL-161 order, each relief the cumulatively rounded
  share of the layer's historical functional amount (S12-R-05, S12-R-07); any remainder creates an
  asset layer at the POL-162 rate for revenue and at spot for other debits (S12-R-06);
- a credit memo that relieves liability layers publishes the JET-10c difference (S12-R-08);
- under the approved POL-163 override in the ASC606 book a liability layer is monetary: a relief is
  the transaction amount at the debit's rate, and the relief that empties the layer first
  remeasures its carrying amount to that amount (JET-10b; S12-R-10; L2-5-Q-16).

``monetary.py`` adds the monetary-liability layers and ``remeasure.py`` the period-end
remeasurements and ``ENGINE`` mode receivables. ``close_period`` then snapshots the open layers,
checks S12-INV-03 and publishes the cumulative functional, remeasurement and FX gain or loss
targets. Every movement is a T-CON-18 row with a trace node (§12.5). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.enums import BookCode
from erev_engine.formulas import rational_param
from erev_engine.money import cumulative_posted, largest_remainder
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from erev_engine.stages.s12_fx_entities.rates import AVERAGE, Rates, RateView, to_functional
from erev_engine.stages.state import BookContext, Finding
from erev_engine.trace import TraceBuilder

__all__ = [
    "ACCOUNTS_RECEIVABLE",
    "ASSET_ROLES",
    "CONTRACT_ASSET",
    "CONTRACT_LIABILITY",
    "GAIN_SIGNS",
    "MONETARY_ROLES",
    "SIDES",
    "ControlFlow",
    "FxTarget",
    "Layer",
    "LayerBalance",
    "LayerMovement",
    "Piece",
    "RateRef",
    "UnitBook",
    "UnitResult",
]

CONTRACT_LIABILITY: Final = "CONTRACT_LIABILITY"
CONTRACT_ASSET: Final = "CONTRACT_ASSET"  # asset positions; the presentation split belongs to §10
ACCOUNTS_RECEIVABLE: Final = "ACCOUNTS_RECEIVABLE"  # ENGINE billing mode only (JET-10a′)
ASSET_ROLES: Final = frozenset({CONTRACT_ASSET, ACCOUNTS_RECEIVABLE})
MONETARY_ROLES: Final = ("REFUND_LIABILITY", "DEPOSIT_LIABILITY", "CONSIDERATION_PAYABLE")  # D-25b
STAGE: Final = 12

# S12-R-03: the side of each control-role flow kind.
SIDES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "BILLING": "CREDIT",  # unconditional billing or receipt, whichever is earlier (POL-160)
        "DEPOSIT_TRANSFER": "CREDIT",  # JET-01b at criteria met
        "NONCASH": "CREDIT",  # noncash consideration becoming unconditional (JET-17)
        "INTEREST_EXPENSE": "CREDIT",  # advance-payment interest (JET-11b)
        "REFUND_RELEASE": "CREDIT",  # refund-liability release to the control role (JET-04b)
        "NEGATIVE_REVENUE": "CREDIT",
        "REVENUE": "DEBIT",  # revenue relief (JET-02, 04a, 05a, 08, 13 contracting side)
        "REFUND_INCREASE": "DEBIT",  # refund-liability increase (JET-04b)
        "CONTRA_INCREASE": "DEBIT",  # receivable-contra increase (JET-04c)
        "CONTRA_RELEASE": "CREDIT",  # receivable-contra decrease (JET-04c reversal; L4-3-Q-29)
        "INTEREST_INCOME": "DEBIT",  # deferred-payment interest (JET-11a)
        "CREDIT_MEMO": "DEBIT",
    }
)
# The sign of each JET-10 part's difference in the net FX gain: an asset difference is a gain when
# positive, a liability difference a loss (POLICIES JET-10; L2-5-Q-15).
GAIN_SIGNS: Final[Mapping[str, int]] = MappingProxyType(
    {"JET-10a": 1, "JET-10a′": 1, "JET-10b": -1, "JET-10c": -1, "JET-10d": -1}
)
_POL_160: Final = frozenset({"EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE", "INVOICE_ISSUE_DATE"})
_POL_161: Final = frozenset({"FIFO", "PRO_RATA"})
_POL_162: Final = frozenset({"PERIOD_AVERAGE", "TRANSACTION_DATE_SPOT"})
_POL_163: Final = frozenset({"ENABLED", "DISABLED_REMEASURE_AS_MONETARY"})
_REVENUE_SIGNS: Final[Mapping[str, int]] = MappingProxyType({"REVENUE": 1, "NEGATIVE_REVENUE": -1})
_FUNCTIONAL_NODES: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "revenue_cum": ("revenue_functional", "fx.revenue_functional.v1"),
        # JET-14 promised of a foreign-currency payable (S12-R-19, S14-R-01; L6-5).
        "consideration_payable": ("fx_payable_functional", "fx.gain_loss.sum.v1"),
        # JET-04b of a foreign-currency refund-liability component (S12-R-19, S12-R-20; L6-5).
        "refund_liability": ("fx_refund_liability_functional", "fx.gain_loss.sum.v1"),
        # JET-01b receipt, criteria met and refund of a foreign-currency deposit (S12-R-19,
        # S12-R-20; L6-5); the 25-7 recognition is published beside them.
        "deposit_received_cum": ("fx_deposit_received_functional", "fx.gain_loss.sum.v1"),
        "deposit_refunded_cum": ("fx_deposit_refunded_functional", "fx.gain_loss.sum.v1"),
        "deposit_to_contract_liability_cum": (
            "fx_deposit_transferred_functional",
            "fx.gain_loss.sum.v1",
        ),
        "deposit_to_revenue_cum": ("fx_deposit_to_revenue_functional", "fx.gain_loss.sum.v1"),
        # The dated (TIME) 25-7 releases at their own conversion (S12-R-20, S14-R-05; D1-R04).
        "deposit_to_revenue_time_cum": (
            "fx_deposit_to_revenue_time_functional",
            "fx.gain_loss.sum.v1",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ControlFlow:
    """One control-role flow of a contracting entity (ENGINE_SPEC_B §12.1; S12-R-03).

    ``amount`` is positive, in transaction-currency minor units; ``kind`` fixes the side.
    ``source_key`` is the CV-22 global key of the event behind the flow, or
    ``<subject key>@<period key>`` for a time-driven release (``record_seq`` None), which runs
    before the events of its date. A ``BILLING`` flow's ``effective_date`` is the date its line
    enters the position (S10-R-06): the invoice issue date of an ``ERP`` line, the date an
    ``ENGINE`` line became billing, the cutover of an opening baseline. ``unconditional_date`` is
    its POL-160 "unconditional due" (the payload due date of an ``ERP`` line when present, D-87
    L6-5-Q-14) and ``first_receipt_date`` the first receipt naming the invoice (S12-R-04).
    """

    kind: str
    entity: str  # contracting entity
    subject_key: str  # obligation subject key for revenue; contract@entity otherwise
    source_key: str
    effective_date: date
    record_seq: int | None
    amount: int
    unconditional_date: date | None = None
    first_receipt_date: date | None = None

    def __post_init__(self) -> None:
        if self.kind not in SIDES:
            raise ValueError(f"unknown control-role flow kind {self.kind!r} (S12-R-03)")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount <= 0:
            raise ValueError("a control-role flow amount is a positive integer of minor units")

    @property
    def side(self) -> str:
        return SIDES[self.kind]

    @property
    def flow_key(self) -> str:
        """The natural key of the flow inside trace subjects (L2-5-Q-12)."""
        return f"{self.source_key}#{self.kind}@{self.subject_key}"


@dataclass(frozen=True, slots=True)
class RateRef:
    """The natural keys of a pinned rate row (REQ-FX-006)."""

    rate_key: str
    version_key: str


@dataclass(frozen=True, slots=True)
class LayerMovement:
    """A T-CON-18 row without surrogate ids (ENGINE_SPEC_B §12.1 ``layer_movements``).

    Creation, consumption and settlement carry magnitudes; a remeasurement carries the transaction
    amount remeasured and the signed functional difference (positive raises the carrying amount).
    """

    book_code: BookCode
    entity: str
    layer_key: str  # "<balance role>:<global event key>" (CV-22; L2-5-Q-12)
    movement_kind: str  # E-86
    balance_role: str  # E-01
    effective_date: date
    txn_currency: str
    amount_txn: int
    functional_currency: str
    amount_functional: int
    rate_key: str | None  # None only when txn_currency == functional_currency
    version_key: str | None
    rate: Fraction
    source_key: str | None  # None for a period-end remeasurement
    reason: str | None  # remeasurements: SETTLEMENT | PERIOD_END
    trace_node_id: str


@dataclass(frozen=True, slots=True)
class LayerBalance:
    """An open layer at a period end, after its period-end remeasurement (S12-INV-03, 08)."""

    book_code: BookCode
    entity: str
    period_key: str
    layer_key: str
    balance_role: str
    component_key: str | None
    txn_open: int
    fn_carrying: int


@dataclass(frozen=True, slots=True)
class FxTarget:
    """A cumulative stage 12 target in both currencies (REQ-FX-001; L2-5-Q-13).

    ``rates`` are the distinct pinned rates of the movements behind the amount. A remeasurement
    target has ``part`` (JET-10 part), ``balance_role``, ``amount_txn`` 0 and the cumulative signed
    difference of that part; the FX gain or loss target is the cumulative net gain (L2-5-Q-15).
    """

    book_code: BookCode
    entity: str
    subject_key: str
    measure: str
    part: str | None
    balance_role: str | None
    period_key: str
    txn_currency: str
    amount_txn: int
    functional_currency: str
    amount_functional: int
    rates: tuple[RateRef, ...]
    node_id: str


@dataclass(slots=True)
class Layer:
    """Engine-internal mutable layer inside one compute call (ENGINE_SPEC_B §12.2.2)."""

    key: str
    role: str
    component_key: str | None
    txn_original: int
    txn_open: int
    fn_original: int  # historical functional amount (liability) or carrying at creation (asset)
    fn_carrying: int
    rate: RateView
    created_node: str

    @property
    def consumed(self) -> int:
        return self.txn_original - self.txn_open


@dataclass(frozen=True, slots=True)
class Piece:
    """A functional amount a flow moved, with its node, rate and layer."""

    node_id: str
    amount: int
    rate: RateView
    layer_key: str | None = None


@dataclass(slots=True)
class Running:
    """A cumulative target under construction: totals and the nodes of the current period."""

    measure: str
    subject_key: str
    part: str | None
    balance_role: str | None
    amount_txn: int = 0
    amount_functional: int = 0
    rates: set[RateRef] = field(default_factory=set)
    pending: list[tuple[str, int]] = field(default_factory=list)  # (node id, sign)
    node_id: str | None = None

    def add(self, piece: Piece, sign: int) -> None:
        self.amount_functional += sign * piece.amount
        self.pending.append((piece.node_id, sign))
        if piece.rate.rate_key is not None and piece.rate.version_key is not None:
            self.rates.add(RateRef(piece.rate.rate_key, piece.rate.version_key))


@dataclass(frozen=True, slots=True)
class UnitResult:
    movements: tuple[LayerMovement, ...]
    balances: tuple[LayerBalance, ...]
    functional_targets: tuple[FxTarget, ...]
    remeasurement_targets: tuple[FxTarget, ...]
    gain_loss_targets: tuple[FxTarget, ...]
    findings: tuple[Finding, ...]


class UnitBook:
    """The layers of one (group, contracting entity, book) (POLICIES ALG-08 §2.9.1)."""

    def __init__(
        self, ctx: BookContext, rates: Rates, tb: TraceBuilder, *, group: str, entity: str
    ) -> None:
        if entity not in ctx.entities:
            raise ValueError(f"flows name the entity {entity!r}, absent from the book (CV-45)")
        self.ctx = ctx
        self.rates = rates
        self.tb = tb
        self.entity = entity
        self.calendar = ctx.entities[entity]
        self.unit_key = group_entity_subject_key(group, entity)  # CV-21 group and entity
        self.txn = ctx.txn_currency
        self.fn = self.calendar.functional_currency
        self.mu_txn = ctx.currencies[self.txn].minor_unit
        self.mu_fn = ctx.currencies[self.fn].minor_unit
        self.layers: dict[str, Layer] = {}  # creation order
        self.movements: list[LayerMovement] = []
        self.balances: list[LayerBalance] = []
        self.findings: list[Finding] = []
        self.functional: dict[tuple[str, str], Running] = {}
        self.remeasurement: dict[tuple[str, str], Running] = {}
        self.gain_loss = Running("fx_gain_loss", self.unit_key, None, "FX_GAIN_LOSS")
        self.functional_targets: list[FxTarget] = []
        self.remeasurement_targets: list[FxTarget] = []
        self.gain_loss_targets: list[FxTarget] = []

    def result(self) -> UnitResult:
        return UnitResult(
            tuple(self.movements),
            tuple(self.balances),
            tuple(self.functional_targets),
            tuple(self.remeasurement_targets),
            tuple(self.gain_loss_targets),
            tuple(self.findings),
        )

    # --- policies and dates ----------------------------------------------------------------------

    def horizon(self) -> dates.PeriodLike:
        horizon_key = self.ctx.horizon.get(self.entity)
        horizon = next((p for p in self.calendar.periods if p.period_key == horizon_key), None)
        if horizon is None:
            raise ValueError(f"entity {self.entity} has no horizon period (C-05)")
        return horizon

    def period(self, d: date) -> dates.PeriodLike:
        return dates.period_of(self.calendar, d)

    def policy(self, code: str, d: date, allowed: frozenset[str]) -> str:
        """A pin P option at the contracting entity's period of ``d`` (CV-17; L2-4-Q-11)."""
        value = self.ctx.policies.value(code, entity=self.entity, period=self.period(d).period_key)
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"policy {code} holds an unknown option {value!r} (CV-17)")
        return value

    def cl_monetary(self, d: date) -> bool:
        """S12-R-10: the POL-163 contract override, effective in the ASC606 book only (D-25a)."""
        option = self.policy("fx.cl_historical_layering", d, _POL_163)
        return self.ctx.framework == BookCode.ASC606 and option == "DISABLED_REMEASURE_AS_MONETARY"

    def layer_date(self, flow: ControlFlow) -> date | None:
        """S12-R-04: the date of a billing credit; other flows keep their effective date.

        Rev 1.83 (supervisor ruling R-81, amending D-87 L6-5-Q-14): the earlier of "unconditional
        due" and the first receipt may not leave the accounting period in which the line enters
        the position — the flow's effective date, its S10-R-06 date in either billing mode. A
        date in a later period (an invoice neither due nor paid by the end of its issue period)
        gives the end of that period; a date in an earlier period (a receipt naming an invoice
        issued later, or a later line of a paid invoice) gives the effective date; a date inside
        the period is unchanged. The credit is processed on this date, so at every period end the
        layers hold exactly the lines the position counts (S12-INV-03).
        """
        if flow.kind != "BILLING":
            return flow.effective_date
        option = self.policy("fx.cl_layer_date", flow.effective_date, _POL_160)
        if option == "INVOICE_ISSUE_DATE" and self.ctx.framework != BookCode.IFRS15:
            return flow.effective_date
        # IFRS15 forces the earlier of receipt and unconditional due date (IFRIC 22.8, 22.9).
        candidates = [
            d for d in (flow.unconditional_date, flow.first_receipt_date) if d is not None
        ]
        if not candidates:
            return None
        earliest = min(candidates)
        entered = self.period(flow.effective_date)
        if earliest > entered.end_date:
            return entered.end_date
        if earliest < entered.start_date:
            return flow.effective_date
        return earliest

    # --- flows -----------------------------------------------------------------------------------

    def control(
        self, flow: ControlFlow, when: date, released: list[Piece] | None = None
    ) -> list[Piece]:
        """One control-role flow; the functional pieces it moved (S12-R-03). ``released``: the
        monetary portions a release consumed at spot (D-87 L6-5-Q-26)."""
        period = self.period(when)
        if flow.side == "CREDIT":
            pieces = self.credit(flow, when, period, released)
        else:
            pieces = self.debit(flow, when, period)
        sign = _REVENUE_SIGNS.get(flow.kind)
        if sign is not None:
            running = self.functional.setdefault(
                ("revenue_cum", flow.subject_key),
                Running("revenue_cum", flow.subject_key, None, None),
            )
            running.amount_txn += sign * flow.amount
            for piece in pieces:
                running.add(piece, sign)
        return pieces

    def credit(
        self,
        flow: ControlFlow,
        when: date,
        period: dates.PeriodLike,
        released: list[Piece] | None = None,
    ) -> list[Piece]:
        """S12-R-03 credit: settle open asset layers at spot, then a liability layer (ALG-08).

        When the asset settlements absorb a whole release (``released`` given), the last
        settlement takes the residue Σ released − Σ settled at spot (D-88 L7-6-Q-2).
        """
        spot = self.rates.spot(when)
        pieces: list[Piece] = []
        left = flow.amount
        assets = [
            layer
            for layer in self.layers.values()
            if layer.role == CONTRACT_ASSET and layer.txn_open > 0
        ]
        for layer in assets:
            if left == 0:
                break
            take = min(layer.txn_open, left)
            last = released is not None and take == left
            pieces.append(
                self.settle(
                    layer,
                    take,
                    spot,
                    flow.flow_key,
                    flow.source_key,
                    when,
                    period,
                    formula_id="fx.settlement.spot.v1",
                    part="JET-10a",
                    release=(released, tuple(pieces)) if last and released is not None else None,
                )
            )
            left -= take
        if left > 0 and released is not None:
            pieces.append(self.create_released(left, spot, flow, when, period, released, pieces))
            left = 0
        if left > 0:
            pieces.append(
                self.create(
                    CONTRACT_LIABILITY,
                    left,
                    spot,
                    flow.source_key,
                    when,
                    period,
                    formula_id="fx.layer.create.v1",
                    movement_kind="LIABILITY_LAYER_CREATED",
                )
            )
        return pieces

    def create_released(
        self,
        amount: int,
        rate: RateView,
        flow: ControlFlow,
        when: date,
        period: dates.PeriodLike,
        released: list[Piece],
        settled: list[Piece],
    ) -> Piece:
        """The contract-liability layer a release creates (D-87 L6-5-Q-26; S12-R-20, S12-INV-08,
        S14-R-11).

        It takes the carrying of the release: Σ per-layer round(take × spot) of the refund-liability
        or deposit portions consumed, less the asset layers the release settled first at spot. GL
        and layers then tie with no residue and no ROUNDING line.
        """
        key = self.new_key(CONTRACT_LIABILITY, flow.source_key)
        functional = sum(piece.amount for piece in released) - sum(
            piece.amount for piece in settled
        )
        formula_id = "fx.gain_loss.sum.v1"
        signs = ["1"] * len(released) + ["-1"] * len(settled)
        node = self.tb.node(
            measure="fx_layer_created",
            subject_key=key,
            period_key=period.period_key,
            value=functional,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=[*(piece.node_id for piece in released), *(piece.node_id for piece in settled)],
            params={**self.conversion_params(amount, rate, when), "signs": "|".join(signs)},
            exact=Fraction(functional, 10**self.mu_fn),
            narrative_key=_narrative(formula_id),
        )
        self.layers[key] = Layer(
            key, CONTRACT_LIABILITY, None, amount, amount, functional, functional, rate, node
        )
        self.move(
            key,
            CONTRACT_LIABILITY,
            "LIABILITY_LAYER_CREATED",
            when,
            amount,
            functional,
            rate,
            flow.source_key,
            None,
            node,
        )
        return Piece(node, functional, rate, key)

    def debit(self, flow: ControlFlow, when: date, period: dates.PeriodLike) -> list[Piece]:
        """S12-R-03 debit: relieve liability layers (POL-161), then an asset layer (S12-R-06)."""
        option = self.policy("fx.cl_layer_consumption", when, _POL_161)
        open_layers = [
            layer
            for layer in self.layers.values()
            if layer.role == CONTRACT_LIABILITY and layer.txn_open > 0
        ]
        reliefs: list[Piece] = []
        left = flow.amount
        if option == "FIFO":
            for layer in open_layers:
                if left == 0:
                    break
                take = min(layer.txn_open, left)
                params = {"take": str(take)}
                reliefs.append(
                    self.relieve(
                        layer, take, flow, when, period, "fx.layer.consume.fifo.v1", params
                    )
                )
                left -= take
        else:
            total = min(left, sum(layer.txn_open for layer in open_layers))
            if total > 0:
                ordered = sorted(open_layers, key=lambda layer: layer.key)
                weights = [layer.txn_open for layer in ordered]
                shares = largest_remainder(
                    total,
                    [Fraction(weight) for weight in weights],
                    [layer.key for layer in ordered],
                )
                for index, (layer, share) in enumerate(zip(ordered, shares, strict=True)):
                    if share == 0:
                        continue
                    params = {
                        "debit": str(total),
                        "index": str(index),
                        "take": str(share),
                        "weights": "|".join(str(weight) for weight in weights),
                    }
                    reliefs.append(
                        self.relieve(
                            layer, share, flow, when, period, "fx.layer.consume.pro_rata.v1", params
                        )
                    )
                left -= total
        pieces = list(reliefs)
        if left > 0:
            pieces.append(
                self.create(
                    CONTRACT_ASSET,
                    left,
                    self.debit_rate(flow, when, period),
                    flow.source_key,
                    when,
                    period,
                    formula_id="fx.asset_layer.create.v1",
                    movement_kind="ASSET_LAYER_CREATED",
                )
            )
        if flow.kind == "CREDIT_MEMO" and reliefs:
            self.credit_memo_difference(flow, flow.amount - left, reliefs, when, period)
        return pieces

    def debit_rate(self, flow: ControlFlow, when: date, period: dates.PeriodLike) -> RateView:
        """S12-R-06: POL-162 for revenue; spot on the flow date for any other debit (L2-5-Q-14)."""
        if flow.kind != "REVENUE":
            return self.rates.spot(when)
        option = self.policy("fx.unbilled_revenue_rate", when, _POL_162)
        if option == "PERIOD_AVERAGE":
            return self.rates.period_rate(AVERAGE, period)
        return self.rates.spot(when)

    # --- movements -------------------------------------------------------------------------------

    def new_key(self, role: str, source_key: str) -> str:
        """``<balance role>:<source key>``; a later layer of that role and source adds ``#n``."""
        base = f"{role}:{source_key}"
        if base not in self.layers:
            return base
        number = 2
        while f"{base}#{number}" in self.layers:
            number += 1
        return f"{base}#{number}"

    def create(
        self,
        role: str,
        amount: int,
        rate: RateView,
        source_key: str,
        when: date,
        period: dates.PeriodLike,
        *,
        formula_id: str,
        movement_kind: str,
        component_key: str | None = None,
    ) -> Piece:
        key = self.new_key(role, source_key)
        functional = to_functional(amount, rate, self.mu_txn, self.mu_fn)
        node = self.tb.node(
            measure="fx_layer_created",
            subject_key=key,
            period_key=period.period_key,
            value=functional,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=rate.inputs(),
            params=self.conversion_params(amount, rate, when),
            exact=Fraction(amount, 10**self.mu_txn) * rate.value,
            narrative_key=_narrative(formula_id),
        )
        self.layers[key] = Layer(
            key, role, component_key, amount, amount, functional, functional, rate, node
        )
        self.move(key, role, movement_kind, when, amount, functional, rate, source_key, None, node)
        return Piece(node, functional, rate, key)

    def relieve(
        self,
        layer: Layer,
        take: int,
        flow: ControlFlow,
        when: date,
        period: dates.PeriodLike,
        formula_id: str,
        params: Mapping[str, str],
    ) -> Piece:
        """S12-R-05: the cumulatively rounded share of the historical functional amount."""
        if self.cl_monetary(when):
            return self.relieve_at_rate(layer, take, flow, when, period, formula_id, params)
        before = layer.consumed
        exact_original = Fraction(layer.fn_original, 10**self.mu_fn)

        def cumulative(consumed: int) -> int:
            share = Fraction(consumed, layer.txn_original)
            return cumulative_posted(exact_original, layer.fn_original, share, self.mu_fn)

        relief = cumulative(before + take) - cumulative(before)
        node = self.tb.node(
            measure="fx_layer_consumed",
            subject_key=f"{layer.key}@{flow.flow_key}",
            period_key=period.period_key,
            value=relief,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=[layer.created_node],
            params={
                **params,
                "basis": "HISTORICAL",
                "consumed_before": str(before),
                "effective_date": when.isoformat(),
                "txn_original": str(layer.txn_original),
            },
            exact=exact_original * Fraction(take, layer.txn_original),
            narrative_key=_narrative(formula_id),
        )
        layer.txn_open -= take
        layer.fn_carrying -= relief
        self.move(
            layer.key,
            layer.role,
            "LIABILITY_LAYER_CONSUMED",
            when,
            take,
            relief,
            layer.rate,
            flow.source_key,
            None,
            node,
        )
        return Piece(node, relief, layer.rate, layer.key)

    def relieve_at_rate(
        self,
        layer: Layer,
        take: int,
        flow: ControlFlow,
        when: date,
        period: dates.PeriodLike,
        formula_id: str,
        params: Mapping[str, str],
    ) -> Piece:
        """S12-R-10 override (CHK-082): the relief is the transaction amount at the debit's rate.

        The relief that empties the layer first remeasures the carrying amount to that amount
        (JET-10b, reason ``SETTLEMENT``), so a consumed layer ends at 0 (L2-5-Q-16).
        """
        rate = self.debit_rate(flow, when, period)
        if take == layer.txn_open:
            return self.settle(
                layer,
                take,
                rate,
                flow.flow_key,
                flow.source_key,
                when,
                period,
                formula_id="fx.settlement.spot.v1",
                part="JET-10b",
            )
        relief = to_functional(take, rate, self.mu_txn, self.mu_fn)
        node = self.tb.node(
            measure="fx_layer_consumed",
            subject_key=f"{layer.key}@{flow.flow_key}",
            period_key=period.period_key,
            value=relief,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=rate.inputs(),
            params={**params, **self.conversion_params(take, rate, when), "basis": "RATE"},
            exact=Fraction(take, 10**self.mu_txn) * rate.value,
            narrative_key=_narrative(formula_id),
        )
        layer.txn_open -= take
        layer.fn_carrying -= relief
        self.move(
            layer.key,
            layer.role,
            "LIABILITY_LAYER_CONSUMED",
            when,
            take,
            relief,
            rate,
            flow.source_key,
            None,
            node,
        )
        return Piece(node, relief, rate, layer.key)

    def settle(
        self,
        layer: Layer,
        take: int,
        rate: RateView,
        flow_key: str,
        source_key: str,
        when: date,
        period: dates.PeriodLike,
        *,
        formula_id: str,
        part: str,
        release: tuple[Sequence[Piece], Sequence[Piece]] | None = None,
    ) -> Piece:
        """A portion leaving a layer at ``rate`` (S12-R-09, S12-R-10, S12-R-20).

        The settled carrying share is ``cumulative_posted`` over the carrying amount at take ÷ open;
        round(take × rate) − that share is remeasured (reason ``SETTLEMENT``), then the portion is
        settled or consumed at round(take × rate).

        ``release``: the released portions and the asset settlements before this one, when this is
        the last settlement of a release the assets absorb (D-88 L7-6-Q-2). The residue r = Σ
        released − Σ settled amounts, this one included, is added to the remeasurement and to the
        settled amount; the carrying still leaves by its share only, so GL and layers tie with no
        ROUNDING line.
        """
        open_before, carrying = layer.txn_open, layer.fn_carrying
        scale = 10**self.mu_fn
        share = cumulative_posted(
            Fraction(carrying, scale), carrying, Fraction(take, open_before), self.mu_fn
        )
        at_rate = to_functional(take, rate, self.mu_txn, self.mu_fn)
        difference = at_rate - share
        params = {
            **self.conversion_params(take, rate, when),
            "carrying_before": str(carrying),
            "open_before": str(open_before),
        }
        subject = f"{layer.key}@{flow_key}"
        asset = layer.role in ASSET_ROLES
        exact = Fraction(take, 10**self.mu_txn) * rate.value
        amount_node = self.tb.node(
            measure="fx_layer_settled" if asset else "fx_layer_consumed",
            subject_key=subject,
            period_key=period.period_key,
            value=at_rate,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=rate.inputs(),
            params={**params, "output": "AMOUNT"},
            exact=exact,
            narrative_key=_narrative(formula_id),
        )
        difference_node = self.tb.node(
            measure="fx_layer_remeasured",
            subject_key=subject,
            period_key=period.period_key,
            value=difference,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=rate.inputs(),
            params={**params, "output": "DIFFERENCE"},
            exact=exact - Fraction(share, scale),
            narrative_key=_narrative(formula_id),
        )
        remeasured_node, remeasured_amount = difference_node, difference
        settled_node, settled_amount = amount_node, at_rate
        if release is not None:
            released, before = release
            residue = sum(piece.amount for piece in released) - sum(
                piece.amount for piece in before
            )
            residue -= at_rate
            if residue:
                remeasured_amount = difference + residue
                settled_amount = at_rate + residue
                remeasured_node, settled_node = self.release_residue(
                    subject,
                    period,
                    residue,
                    released,
                    before,
                    (amount_node, settled_amount),
                    (difference_node, remeasured_amount),
                )
        if remeasured_amount:
            remeasured = "ASSET_LAYER_REMEASURED" if asset else "LIABILITY_LAYER_REMEASURED"
            self.move(
                layer.key,
                layer.role,
                remeasured,
                when,
                take,
                remeasured_amount,
                rate,
                source_key,
                "SETTLEMENT",
                remeasured_node,
            )
        settled = "ASSET_LAYER_SETTLED" if asset else "LIABILITY_LAYER_CONSUMED"
        self.move(
            layer.key,
            layer.role,
            settled,
            when,
            take,
            settled_amount,
            rate,
            source_key,
            None,
            settled_node,
        )
        layer.txn_open -= take
        layer.fn_carrying = carrying - share
        self.remeasured(
            part, layer.role, Piece(remeasured_node, remeasured_amount, rate, layer.key)
        )
        return Piece(settled_node, settled_amount, rate, layer.key)

    def release_residue(
        self,
        subject: str,
        period: dates.PeriodLike,
        residue: int,
        released: Sequence[Piece],
        before: Sequence[Piece],
        settled: tuple[str, int],
        remeasured: tuple[str, int],
    ) -> tuple[str, str]:
        """D-88 L7-6-Q-2: the residue node over the released portions (+1) and the settled amount
        nodes (−1), this settlement's included; then the ``#release_total`` remeasured and settled
        nodes over this settlement's difference or amount node and the residue node. Returns the
        (remeasured, settled) total node ids. Every node is ``fx.gain_loss.sum.v1``."""
        formula_id = "fx.gain_loss.sum.v1"
        amount_node, settled_total = settled
        difference_node, remeasured_total = remeasured
        settled_inputs = [*(piece.node_id for piece in before), amount_node]
        signs = ["1"] * len(released) + ["-1"] * len(settled_inputs)
        residue_node = self.tb.node(
            measure="fx_layer_remeasured",
            subject_key=f"{subject}#release_residue",
            period_key=period.period_key,
            value=residue,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=[*(piece.node_id for piece in released), *settled_inputs],
            params={"signs": "|".join(signs)},
            narrative_key=_narrative(formula_id),
        )
        totals = []
        for measure, node_id, value in (
            ("fx_layer_remeasured", difference_node, remeasured_total),
            ("fx_layer_settled", amount_node, settled_total),
        ):
            totals.append(
                self.tb.node(
                    measure=measure,
                    subject_key=f"{subject}#release_total",
                    period_key=period.period_key,
                    value=value,
                    currency=self.fn,
                    minor_unit=self.mu_fn,
                    formula_id=formula_id,
                    inputs=[node_id, residue_node],
                    params={"signs": "1|1"},
                    narrative_key=_narrative(formula_id),
                )
            )
        return totals[0], totals[1]

    def credit_memo_difference(
        self,
        flow: ControlFlow,
        taken: int,
        reliefs: Sequence[Piece],
        when: date,
        period: dates.PeriodLike,
    ) -> None:
        """S12-R-08 JET-10c: round(m × spot) − the historical relief of the layers relieved."""
        spot = self.rates.spot(when)
        relieved = sum(piece.amount for piece in reliefs)
        difference = to_functional(taken, spot, self.mu_txn, self.mu_fn) - relieved
        formula_id = "fx.credit_memo_difference.v1"
        params = self.conversion_params(taken, spot, when)
        params["reliefs"] = str(len(reliefs))
        node = self.tb.node(
            measure="fx_credit_memo_difference",
            subject_key=flow.flow_key,
            period_key=period.period_key,
            value=difference,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=[*spot.inputs(), *(piece.node_id for piece in reliefs)],
            params=params,
            exact=Fraction(taken, 10**self.mu_txn) * spot.value
            - Fraction(relieved, 10**self.mu_fn),
            narrative_key=_narrative(formula_id),
        )
        self.remeasured("JET-10c", CONTRACT_LIABILITY, Piece(node, difference, spot))

    def conversion_params(self, amount: int, rate: RateView, when: date) -> dict[str, str]:
        return {
            "amount_txn": str(amount),
            "effective_date": when.isoformat(),
            "rate": rational_param(rate.value),
            "rate_input": "true" if rate.rate_key is not None else "false",
            "rate_type": rate.rate_type,
            "txn_minor_unit": str(self.mu_txn),
        }

    def move(
        self,
        key: str,
        role: str,
        kind: str,
        when: date,
        amount_txn: int,
        amount_functional: int,
        rate: RateView,
        source_key: str | None,
        reason: str | None,
        node: str,
    ) -> None:
        self.movements.append(
            LayerMovement(
                book_code=self.ctx.book_code,
                entity=self.entity,
                layer_key=key,
                movement_kind=kind,
                balance_role=role,
                effective_date=when,
                txn_currency=self.txn,
                amount_txn=amount_txn,
                functional_currency=self.fn,
                amount_functional=amount_functional,
                rate_key=rate.rate_key,
                version_key=rate.version_key,
                rate=rate.value,
                source_key=source_key,
                reason=reason,
                trace_node_id=node,
            )
        )

    def remeasured(self, part: str, role: str, piece: Piece) -> None:
        """Add a JET-10 difference to its part's target and to the net FX gain or loss."""
        running = self.remeasurement.setdefault(
            (part, role),
            Running("fx_remeasurement_cum", f"{self.unit_key}#{part}#{role}", part, role),
        )
        running.add(piece, 1)
        self.gain_loss.add(piece, GAIN_SIGNS[part])

    # --- period end ------------------------------------------------------------------------------

    def close_period(
        self, period: dates.PeriodLike, positions: Mapping[tuple[str, str], int]
    ) -> None:
        """Snapshot open layers, check S12-INV-03 and publish the cumulative targets."""
        net = 0
        for layer in self.layers.values():
            if layer.txn_open == 0:
                continue
            self.balances.append(
                LayerBalance(
                    self.ctx.book_code,
                    self.entity,
                    period.period_key,
                    layer.key,
                    layer.role,
                    layer.component_key,
                    layer.txn_open,
                    layer.fn_carrying,
                )
            )
            if layer.role == CONTRACT_LIABILITY:
                net += layer.txn_open
            elif layer.role == CONTRACT_ASSET:
                net -= layer.txn_open
        expected = positions.get((self.entity, period.period_key))
        if expected is not None and expected != net:
            self.findings.append(
                Finding(
                    "ENGINE_INVARIANT_VIOLATION",
                    "ERROR",
                    self.unit_key,
                    {
                        "layers_net": str(net),
                        "net_position": str(expected),
                        "period_key": period.period_key,
                        "rule": "S12-INV-03",
                    },
                    STAGE,
                    None,
                )
            )
        for (measure, _subject), running in sorted(self.functional.items()):
            node_measure, formula_id = _FUNCTIONAL_NODES[measure]
            target = self.publish(running, node_measure, formula_id, period)
            self.functional_targets.append(target)
        for _key, running in sorted(self.remeasurement.items()):
            target = self.publish(running, "fx_remeasurement_cum", "fx.gain_loss.sum.v1", period)
            self.remeasurement_targets.append(target)
        if self.gain_loss.pending or self.gain_loss.node_id is not None:
            target = self.publish(self.gain_loss, "fx_gain_loss", "fx.gain_loss.sum.v1", period)
            self.gain_loss_targets.append(target)

    def publish(
        self, running: Running, node_measure: str, formula_id: str, period: dates.PeriodLike
    ) -> FxTarget:
        inputs = ([] if running.node_id is None else [(running.node_id, 1)]) + running.pending
        node = self.tb.node(
            measure=node_measure,
            subject_key=running.subject_key,
            period_key=period.period_key,
            value=running.amount_functional,
            currency=self.fn,
            minor_unit=self.mu_fn,
            formula_id=formula_id,
            inputs=[node_id for node_id, _ in inputs],
            params={"signs": "|".join(str(sign) for _, sign in inputs)},
            narrative_key=_narrative(formula_id),
        )
        running.node_id = node
        running.pending.clear()
        return FxTarget(
            book_code=self.ctx.book_code,
            entity=self.entity,
            subject_key=running.subject_key,
            measure=running.measure,
            part=running.part,
            balance_role=running.balance_role,
            period_key=period.period_key,
            txn_currency=self.txn,
            amount_txn=running.amount_txn,
            functional_currency=self.fn,
            amount_functional=running.amount_functional,
            rates=tuple(sorted(running.rates, key=lambda ref: (ref.rate_key, ref.version_key))),
            node_id=node,
        )


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]
