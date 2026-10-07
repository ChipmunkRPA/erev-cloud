"""Stage 12 period-end remeasurement, monetary liabilities and late-event rates.

ENGINE_SPEC_B §12.2.2 S12-R-19 to S12-R-21, §12.2.3 S12-R-09 to S12-R-12, §12.2.4 S12-R-13, §12.3
S12-INV-02, S12-INV-04, S12-INV-06, S12-INV-08 and §12.7 EX-12-B; POLICIES ALG-08 §2.9.1 to §2.9.3
(CHK-081 to CHK-084), POL-163, POL-164, POL-181 and JET-10a to JET-10d. The consumed state is a fake
that carries ``FxFlows`` (D-81 integration after merge; L2-5-Q-10). Every trace re-evaluates node
for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import FxRateInput
from erev_engine.dates import month_end
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.money import round_half_up
from erev_engine.stages import s12_fx_entities
from erev_engine.stages.s12_fx_entities import (
    ControlFlow,
    FxFlows,
    FxState,
    FxTarget,
    MonetaryFlow,
    ReceivableFlow,
)
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    PolicyResolver,
    RateIndex,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import CONTRACT_KEY, allocated_state, book_context, period_amounts, usd

ENTITY = bundles.ENTITY_CODE
GROUP = "CG-1"
UNIT = f"{GROUP}@{ENTITY}"
CONTRACT = f"{CONTRACT_KEY}@{ENTITY}"
SERVICES = f"{CONTRACT_KEY}/S"
LICENCE = f"{CONTRACT_KEY}/L"
PRODUCT = f"{CONTRACT_KEY}/P"
RETURNS = f"{PRODUCT}#RETURN"
DEPOSIT = f"{CONTRACT}#DEPOSIT"
PROMISE = f"{CONTRACT}#PROMISE-1"
RATE_SET = "EURUSD-PUBLISHED@v1"
PARTS = frozenset({"JET-10a", "JET-10a′", "JET-10b", "JET-10c", "JET-10d"})
MONETARY_ROLES = ("REFUND_LIABILITY", "DEPOSIT_LIABILITY", "CONSIDERATION_PAYABLE")
BALANCE_ROLES = frozenset(
    {"CONTRACT_ASSET", "CONTRACT_LIABILITY", "ACCOUNTS_RECEIVABLE", *MONETARY_ROLES}
)
OVERRIDE = {"fx.cl_historical_layering": "DISABLED_REMEASURE_AS_MONETARY"}
PAYABLE_MEASURE = "consideration_payable"  # the JET-14 promised functional target (L6-5)
REFUND_MEASURE = "refund_liability"  # the JET-04b functional target per component (L6-5)


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stage 12 reads it (L2-5-Q-10)."""

    allocated: AllocatedState
    fx_flows: FxFlows


@dataclass(frozen=True, slots=True)
class _PartCosts:
    """The fake stage 11 output with the stage 10 reclass attributions (S12-R-09)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


@dataclass(frozen=True, slots=True)
class _Case:
    state: FxState
    trace: Trace
    monetary: tuple[MonetaryFlow, ...]
    closing: Mapping[str, Fraction]


def _context(
    *, book: str = "ASC606", months: int, policies: Mapping[str, str] | None = None
) -> BookContext:
    calendar = bundles.entity(months=months, books=(book,))
    ctx = book_context(calendar, book_code=book, currency="EUR")
    ctx = dataclasses.replace(ctx, currencies=bundles.currencies("EUR", "USD"))
    for code, value in (policies or {}).items():
        resolved = tuple(
            dataclasses.replace(policy, value=value, level="C", source_ref="OVR-TEST")
            if policy.code == code
            else policy
            for policy in ctx.policies.all()
        )
        ctx = dataclasses.replace(ctx, policies=PolicyResolver(resolved))
    return ctx


def _spot(on: date, rate: str) -> FxRateInput:
    key = f"EURUSD-SPOT-{on.isoformat()}"
    return FxRateInput(key, RATE_SET, "spot", "EUR", "USD", on, None, Decimal(rate))


def _period_rate(kind: str, month: int, rate: str) -> FxRateInput:
    start = date(2026, month, 1)
    period_key = f"FY2026-P{month:02d}"
    key = f"EURUSD-{kind.upper()}-{period_key}"
    end = month_end(start)
    return FxRateInput(key, RATE_SET, kind, "EUR", "USD", end, period_key, Decimal(rate))


def _event(stream_version: int) -> str:
    return f"{CONTRACT_KEY}/EV-{stream_version:06d}"


def _invoice(stream_version: int, issued: date, amount: str) -> ControlFlow:
    source = _event(stream_version)
    return ControlFlow(
        "BILLING", ENTITY, CONTRACT, source, issued, stream_version, usd(amount), issued
    )


def _release(subject: str, on: date, amount: str) -> ControlFlow:
    """A time-driven revenue release at a period end (``record_seq`` None)."""
    source = f"{subject}@FY{on.year}-P{on.month:02d}"
    return ControlFlow("REVENUE", ENTITY, subject, source, on, None, usd(amount))


def _on_event(
    kind: str, stream_version: int, on: date, amount: str, subject: str = CONTRACT
) -> ControlFlow:
    source = _event(stream_version)
    return ControlFlow(kind, ENTITY, subject, source, on, stream_version, usd(amount))


def _monetary(
    role: str,
    direction: str,
    component: str,
    source: str,
    on: date,
    stream_version: int | None,
    amount: str,
    reason: str,
    *,
    control: str | None = None,
    subject: str = CONTRACT,
) -> MonetaryFlow:
    return MonetaryFlow(
        role,
        direction,
        ENTITY,
        subject,
        component,
        source,
        on,
        stream_version,
        usd(amount),
        reason,
        control,
    )


def _run(
    ctx: BookContext,
    rates: Iterable[FxRateInput],
    *,
    control: Iterable[ControlFlow] = (),
    monetary: Iterable[MonetaryFlow] = (),
    receivables: Iterable[ReceivableFlow] = (),
) -> _Case:
    pinned = tuple(rates)
    flows = FxFlows(tuple(control), monetary=tuple(monetary), receivables=tuple(receivables))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = s12_fx_entities.run(
        ctx, _Costs(allocated_state([]), flows), tb, rates=RateIndex(pinned)
    )
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    closing = {
        row.period_key: Fraction(row.rate)
        for row in pinned
        if row.rate_type == "closing" and row.period_key is not None
    }
    return _Case(state, trace, flows.monetary, closing)


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _moves(state: FxState, kind: str, role: str | None = None) -> list[tuple[object, ...]]:
    return [
        (move.layer_key, move.effective_date, move.amount_txn, move.amount_functional, move.reason)
        for move in state.layer_movements
        if move.movement_kind == kind and (role is None or move.balance_role == role)
    ]


def _targets(targets: Iterable[FxTarget], subject: str) -> dict[str, int]:
    return {t.period_key: t.amount_functional for t in targets if t.subject_key == subject}


def _remeasured(state: FxState, part: str, role: str) -> dict[str, int]:
    return _targets(state.remeasurement_targets, f"{UNIT}#{part}#{role}")


def _gain(state: FxState) -> dict[str, int]:
    return _targets(state.gain_loss_targets, UNIT)


def _open(state: FxState, period: str) -> list[tuple[str, int, int]]:
    return [
        (balance.layer_key, balance.txn_open, balance.fn_carrying)
        for balance in state.layer_balances
        if balance.period_key == period
    ]


def _chk_081() -> _Case:
    control = [
        _release(SERVICES, date(2026, 1, 31), "1000.00"),
        _release(SERVICES, date(2026, 2, 28), "1000.00"),
        _release(SERVICES, date(2026, 3, 31), "1000.00"),
        _invoice(4, date(2026, 3, 31), "3000.00"),
    ]
    rates = [
        _period_rate("average", 1, "1.1100"),
        _period_rate("average", 2, "1.1300"),
        _period_rate("average", 3, "1.1500"),
        _period_rate("closing", 1, "1.1200"),
        _period_rate("closing", 2, "1.1400"),
        _spot(date(2026, 3, 31), "1.1600"),
    ]
    return _run(_context(months=3), rates, control=control)


def _chk_082(book: str) -> _Case:
    control = [
        _invoice(2, date(2026, 1, 1), "12000.00"),
        _release(SERVICES, date(2026, 1, 31), "1000.00"),
    ]
    rates = [
        _spot(date(2026, 1, 1), "1.1000"),
        _period_rate("average", 1, "1.1100"),
        _period_rate("closing", 1, "1.1200"),
    ]
    return _run(_context(book=book, months=1, policies=OVERRIDE), rates, control=control)


def _chk_083() -> _Case:
    invoice = _event(2)
    receivables = [
        ReceivableFlow(
            "INVOICE", ENTITY, CONTRACT, invoice, invoice, date(2026, 1, 1), 2, usd("12000.00")
        ),
        ReceivableFlow(
            "REDUCTION", ENTITY, CONTRACT, invoice, _event(3), date(2026, 2, 10), 3, usd("3000.00")
        ),
    ]
    rates = [
        _spot(date(2026, 1, 1), "1.1000"),
        _period_rate("closing", 1, "1.1200"),
        _period_rate("closing", 2, "1.1500"),
    ]
    return _run(_context(months=2), rates, receivables=receivables)


def _chk_084_a() -> _Case:
    control = [
        _invoice(2, date(2026, 3, 1), "10000.00"),  # received the same day
        _on_event("REVENUE", 3, date(2026, 3, 1), "9700.00", PRODUCT),
        _on_event("CREDIT_MEMO", 5, date(2026, 4, 15), "200.00"),
        _release(PRODUCT, date(2026, 5, 31), "100.00"),  # JET-04a at window expiry
    ]
    refund = "REFUND_LIABILITY"
    expiry = f"{RETURNS}@FY2026-P05"
    monetary = [
        _monetary(
            refund, "INCREASE", RETURNS, _event(3), date(2026, 3, 1), 3, "300.00", "ESTIMATE",
            control="DEBIT", subject=PRODUCT,
        ),
        _monetary(
            refund, "DECREASE", RETURNS, _event(4), date(2026, 4, 15), 4, "200.00", "RETURN",
            control="CREDIT", subject=PRODUCT,
        ),
        _monetary(
            refund, "DECREASE", RETURNS, expiry, date(2026, 5, 31), None, "100.00", "WINDOW_EXPIRY",
            control="CREDIT", subject=PRODUCT,
        ),
    ]  # fmt: skip
    rates = [
        _spot(date(2026, 3, 1), "1.1000"),
        _spot(date(2026, 4, 15), "1.1500"),
        _spot(date(2026, 5, 31), "1.1000"),
        _period_rate("closing", 3, "1.1200"),
        _period_rate("closing", 4, "1.0800"),
        _period_rate("closing", 5, "1.1000"),
        _period_rate("average", 5, "1.1000"),
    ]
    return _run(_context(months=5), rates, control=control, monetary=monetary)


def _chk_084_b() -> _Case:
    deposit = "DEPOSIT_LIABILITY"
    received, transferred = date(2026, 1, 10), date(2026, 2, 15)
    monetary = [
        _monetary(deposit, "INCREASE", DEPOSIT, _event(2), received, 2, "1000.00", "RECEIPT"),
        _monetary(
            deposit, "DECREASE", DEPOSIT, _event(3), transferred, 3, "1000.00", "CRITERIA_MET",
            control="CREDIT",
        ),
    ]  # fmt: skip
    rates = [
        _spot(date(2026, 1, 10), "1.1000"),
        _spot(date(2026, 2, 15), "1.1300"),
        _period_rate("closing", 1, "1.1200"),
    ]
    return _run(_context(months=2), rates, monetary=monetary)


def _chk_084_c() -> _Case:
    monetary = [
        _monetary(
            "CONSIDERATION_PAYABLE", "INCREASE", PROMISE, _event(2), date(2026, 6, 1), 2,
            "50000.00", "PROMISE",
        )
    ]  # fmt: skip
    rates = [_spot(date(2026, 6, 1), "1.1000"), _period_rate("closing", 6, "1.0900")]
    return _run(_context(months=6), rates, monetary=monetary)


def test_chk_081_contract_asset_remeasured() -> None:
    case = _chk_081()
    state, trace = case.state, case.trace

    assets = [f"CONTRACT_ASSET:{SERVICES}@FY2026-P0{month}" for month in (1, 2, 3)]
    assert period_amounts(_targets(state.functional_targets, SERVICES)) == {
        "FY2026-P01": 111000,
        "FY2026-P02": 113000,
        "FY2026-P03": 115000,
    }
    assert period_amounts(_gain(state)) == {
        "FY2026-P01": 1000,
        "FY2026-P02": 3000,
        "FY2026-P03": 5000,
    }
    assert _remeasured(state, "JET-10a", "CONTRACT_ASSET") == {
        "FY2026-P01": 1000,
        "FY2026-P02": 4000,
        "FY2026-P03": 9000,
    }
    # Contract asset presented 1,120.00 at 31 January and 2,280.00 at 28 February (S12-INV-04).
    assert _open(state, "FY2026-P01") == [(assets[0], 100000, 112000)]
    assert _open(state, "FY2026-P02") == [(assets[0], 100000, 114000), (assets[1], 100000, 114000)]
    assert _open(state, "FY2026-P03") == []
    for period in ("FY2026-P01", "FY2026-P02"):
        for _key, txn_open, carrying in _open(state, period):
            assert carrying == round_half_up(Fraction(txn_open, 100) * case.closing[period], 2)
    assert _moves(state, "ASSET_LAYER_REMEASURED") == [
        (assets[0], date(2026, 1, 31), 100000, 1000, "PERIOD_END"),
        (assets[0], date(2026, 2, 28), 100000, 2000, "PERIOD_END"),
        (assets[1], date(2026, 2, 28), 100000, 1000, "PERIOD_END"),
        (assets[0], date(2026, 3, 31), 100000, 2000, "SETTLEMENT"),
        (assets[1], date(2026, 3, 31), 100000, 2000, "SETTLEMENT"),
        (assets[2], date(2026, 3, 31), 100000, 1000, "SETTLEMENT"),
    ]
    # Receivable at invoice 3,480.00: the invoice settles the three asset layers at spot 1.1600.
    settled = _moves(state, "ASSET_LAYER_SETTLED")
    assert settled == [(asset, date(2026, 3, 31), 100000, 116000, None) for asset in assets]
    assert sum(move[3] for move in settled) == 348000  # type: ignore[misc]
    assert _moves(state, "LIABILITY_LAYER_CREATED") == []

    settlement = _node(
        trace, f"fx_layer_remeasured:{assets[0]}@{_event(4)}#BILLING@{CONTRACT}:FY2026-P03"
    )
    assert (settlement.formula_id, settlement.value, settlement.params["carrying_before"]) == (
        "fx.settlement.spot.v1",
        "20.00",
        "114000",
    )
    assert _node(trace, f"fx_gain_loss:{UNIT}:FY2026-P03").value == "90.00"


def test_chk_082_refundable_advance_override() -> None:
    layer = f"CONTRACT_LIABILITY:{_event(2)}"
    case = _chk_082("ASC606")
    state, trace = case.state, case.trace

    assert _targets(state.functional_targets, SERVICES) == {"FY2026-P01": 111000}
    consumed = [m for m in state.layer_movements if m.movement_kind == "LIABILITY_LAYER_CONSUMED"]
    assert [(m.amount_txn, m.amount_functional, m.rate_key) for m in consumed] == [
        (100000, 111000, "EURUSD-AVERAGE-FY2026-P01")
    ]
    assert _moves(state, "LIABILITY_LAYER_REMEASURED") == [
        (layer, date(2026, 1, 31), 1100000, 23000, "PERIOD_END")
    ]
    # Carrying 12,090.00; EUR 11,000.00 remeasured at 1.1200 to 12,320.00 (JET-10b 230.00).
    remeasured = _node(trace, f"fx_layer_remeasured:{layer}:FY2026-P01")
    assert (remeasured.formula_id, remeasured.params["carrying_before"], remeasured.value) == (
        "fx.remeasure.closing.v1",
        "1209000",
        "230.00",
    )
    assert _open(state, "FY2026-P01") == [(layer, 1100000, 1232000)]
    assert _remeasured(state, "JET-10b", "CONTRACT_LIABILITY") == {"FY2026-P01": 23000}
    assert _gain(state) == {"FY2026-P01": -23000}

    # IFRS15 remeasures no contract-liability layer, whatever the registry value (S12-INV-06).
    ifrs = _chk_082("IFRS15").state
    assert _targets(ifrs.functional_targets, SERVICES) == {"FY2026-P01": 110000}
    assert _moves(ifrs, "LIABILITY_LAYER_REMEASURED") == []
    assert (ifrs.remeasurement_targets, ifrs.gain_loss_targets) == ((), ())
    assert _open(ifrs, "FY2026-P01") == [(layer, 1100000, 1210000)]

    # The relief that empties an overridden layer first remeasures its carrying amount (L2-5-Q-16).
    control = [
        _invoice(2, date(2026, 1, 1), "2000.00"),
        _release(SERVICES, date(2026, 1, 31), "1000.00"),
        _release(SERVICES, date(2026, 2, 28), "1000.00"),
    ]
    rates = [
        _spot(date(2026, 1, 1), "1.1000"),
        _period_rate("average", 1, "1.1100"),
        _period_rate("average", 2, "1.1300"),
        _period_rate("closing", 1, "1.1200"),
    ]
    emptied = _run(_context(months=2, policies=OVERRIDE), rates, control=control).state
    assert _targets(emptied.functional_targets, SERVICES) == {
        "FY2026-P01": 111000,
        "FY2026-P02": 224000,
    }
    assert _moves(emptied, "LIABILITY_LAYER_REMEASURED") == [
        (layer, date(2026, 1, 31), 100000, 3000, "PERIOD_END"),
        (layer, date(2026, 2, 28), 100000, 1000, "SETTLEMENT"),
    ]
    assert _remeasured(emptied, "JET-10b", "CONTRACT_LIABILITY") == {
        "FY2026-P01": 3000,
        "FY2026-P02": 4000,
    }
    assert _open(emptied, "FY2026-P02") == []


def test_chk_083_engine_receivable_remeasurement() -> None:
    state = _chk_083().state
    item = f"ACCOUNTS_RECEIVABLE:{_event(2)}"

    assert _moves(state, "ASSET_LAYER_CREATED") == [
        (item, date(2026, 1, 1), 1200000, 1320000, None)
    ]
    assert _open(state, "FY2026-P01") == [(item, 1200000, 1344000)]
    assert _remeasured(state, "JET-10a′", "ACCOUNTS_RECEIVABLE") == {
        "FY2026-P01": 24000,
        "FY2026-P02": 51000,
    }
    assert _gain(state) == {"FY2026-P01": 24000, "FY2026-P02": 51000}
    # An applied payment relieves the carrying share 13,440.00 × 3,000 ÷ 12,000 = 3,360.00; the
    # remaining EUR 9,000.00 is remeasured at 1.1500 (L2-5-Q-18).
    assert _moves(state, "ASSET_LAYER_SETTLED") == [(item, date(2026, 2, 10), 300000, 336000, None)]
    assert _moves(state, "ASSET_LAYER_REMEASURED") == [
        (item, date(2026, 1, 31), 1200000, 24000, "PERIOD_END"),
        (item, date(2026, 2, 28), 900000, 27000, "PERIOD_END"),
    ]
    assert _open(state, "FY2026-P02") == [(item, 900000, 1035000)]


def test_chk_084_a_refund_liability_remeasured() -> None:
    case = _chk_084_a()
    state, trace = case.state, case.trace
    layer = f"REFUND_LIABILITY:{_event(3)}"

    assert _moves(state, "LIABILITY_LAYER_CREATED", "REFUND_LIABILITY") == [
        (layer, date(2026, 3, 1), 30000, 33000, None)
    ]
    assert _moves(state, "LIABILITY_LAYER_REMEASURED", "REFUND_LIABILITY") == [
        (layer, date(2026, 3, 31), 30000, 600, "PERIOD_END"),
        (layer, date(2026, 4, 15), 20000, 600, "SETTLEMENT"),
        (layer, date(2026, 4, 30), 10000, -400, "PERIOD_END"),
        (layer, date(2026, 5, 31), 10000, 200, "SETTLEMENT"),
    ]
    assert _moves(state, "LIABILITY_LAYER_CONSUMED", "REFUND_LIABILITY") == [
        (layer, date(2026, 4, 15), 20000, 23000, None),
        (layer, date(2026, 5, 31), 10000, 11000, None),
    ]
    settled = _node(trace, f"fx_layer_remeasured:{layer}@{_event(4)}#DECREASE@{RETURNS}:FY2026-P04")
    # cumulative_posted(336.00, 33,600, 2/3) = 224.00, remeasured to 230.00.
    assert (
        settled.formula_id,
        settled.params["carrying_before"],
        settled.params["open_before"],
        settled.value,
    ) == ("fx.monetary_liability.settle.v1", "33600", "30000", "6.00")
    recognition = _node(
        trace, f"fx_layer_remeasured:{layer}@{_event(3)}#INCREASE@{RETURNS}:FY2026-P03"
    )
    assert (recognition.formula_id, recognition.value) == (
        "fx.monetary_liability.recognition_difference.v1",
        "0.00",
    )
    # The JET-04b releases credit the contract liability at spot (230.00, 110.00).
    assert _moves(state, "LIABILITY_LAYER_CREATED", "CONTRACT_LIABILITY") == [
        (f"CONTRACT_LIABILITY:{_event(2)}", date(2026, 3, 1), 1000000, 1100000, None),
        (f"CONTRACT_LIABILITY:{_event(4)}", date(2026, 4, 15), 20000, 23000, None),
        (f"CONTRACT_LIABILITY:{RETURNS}@FY2026-P05", date(2026, 5, 31), 10000, 11000, None),
    ]
    memo = _node(trace, f"fx_credit_memo_difference:{_event(5)}#CREDIT_MEMO@{CONTRACT}:FY2026-P04")
    assert memo.value == "0.00"
    assert _remeasured(state, "JET-10d", "REFUND_LIABILITY") == {
        "FY2026-P03": 600,
        "FY2026-P04": 800,
        "FY2026-P05": 1000,
    }
    revenue = _targets(state.functional_targets, PRODUCT)
    assert revenue == {"FY2026-P03": 1067000, "FY2026-P04": 1067000, "FY2026-P05": 1078000}
    assert _gain(state)["FY2026-P05"] == -1000
    assert _open(state, "FY2026-P05") == []
    # Revenue less the FX loss (10,770.00) equals 11,000.00 received less 230.00 refunded.
    assert revenue["FY2026-P05"] + _gain(state)["FY2026-P05"] == 1100000 - 23000


def test_chk_084_b_deposit_liability_remeasured() -> None:
    state = _chk_084_b().state
    layer = f"DEPOSIT_LIABILITY:{_event(2)}"
    transferred = f"CONTRACT_LIABILITY:{_event(3)}"

    assert _moves(state, "LIABILITY_LAYER_CREATED", "DEPOSIT_LIABILITY") == [
        (layer, date(2026, 1, 10), 100000, 110000, None)
    ]
    assert _moves(state, "LIABILITY_LAYER_REMEASURED", "DEPOSIT_LIABILITY") == [
        (layer, date(2026, 1, 31), 100000, 2000, "PERIOD_END"),
        (layer, date(2026, 2, 15), 100000, 1000, "SETTLEMENT"),
    ]
    assert _moves(state, "LIABILITY_LAYER_CONSUMED", "DEPOSIT_LIABILITY") == [
        (layer, date(2026, 2, 15), 100000, 113000, None)
    ]
    created = [
        (
            move.layer_key,
            move.movement_kind,
            move.effective_date,
            move.amount_functional,
            move.rate_key,
        )
        for move in state.layer_movements
        if move.balance_role == "CONTRACT_LIABILITY"
    ]
    assert created == [
        (
            transferred,
            "LIABILITY_LAYER_CREATED",
            date(2026, 2, 15),
            113000,
            "EURUSD-SPOT-2026-02-15",
        )
    ]
    assert _remeasured(state, "JET-10d", "DEPOSIT_LIABILITY") == {
        "FY2026-P01": 2000,
        "FY2026-P02": 3000,
    }
    assert _open(state, "FY2026-P02") == [(transferred, 100000, 113000)]


def test_chk_084_c_consideration_payable_remeasured() -> None:
    case = _chk_084_c()
    state, trace = case.state, case.trace
    layer = f"CONSIDERATION_PAYABLE:{_event(2)}"

    assert _moves(state, "LIABILITY_LAYER_CREATED") == [
        (layer, date(2026, 6, 1), 5000000, 5500000, None)
    ]
    assert _moves(state, "LIABILITY_LAYER_REMEASURED") == [
        (layer, date(2026, 6, 30), 5000000, -50000, "PERIOD_END")
    ]
    assert _remeasured(state, "JET-10d", "CONSIDERATION_PAYABLE") == {"FY2026-P06": -50000}
    assert _gain(state) == {"FY2026-P06": 50000}
    assert _open(state, "FY2026-P06") == [(layer, 5000000, 5450000)]
    # The customer incentive asset is nonmonetary: it has no layer and keeps 55,000.00 (POL-164).
    assert {move.balance_role for move in state.layer_movements} == {"CONSIDERATION_PAYABLE"}
    assert _node(trace, f"fx_layer_created:{layer}:FY2026-P06").value == "55000.00"
    with pytest.raises(ValueError, match="S12-R-21"):
        _monetary(
            "CONSIDERATION_PAYABLE", "DECREASE", PROMISE, _event(3), date(2026, 6, 20), 3,
            "100.00", "SETTLEMENT",
        )  # fmt: skip


def test_l6_5_consideration_payable_publishes_the_jet_14_functional_amount() -> None:
    """S14-R-01 (L6-5): the promised payable's functional amount is the layer created at spot, a
    cumulative target per ``<contract>@<entity>`` at every period end; the remeasurement does not
    change it. A same-currency unit publishes none, so stage 14 posts the part at rate 1."""
    state = _chk_084_c().state
    payables = [target for target in state.functional_targets if target.measure == PAYABLE_MEASURE]
    assert [(t.subject_key, t.period_key, t.amount_txn, t.amount_functional) for t in payables] == [
        (CONTRACT, "FY2026-P06", 5000000, 5500000)
    ]
    assert [(ref.rate_key, ref.version_key) for ref in payables[0].rates] == [
        ("EURUSD-SPOT-2026-06-01", RATE_SET)
    ]
    calendar = bundles.entity(months=6, books=("ASC606",))
    same = book_context(calendar, book_code="ASC606", currency="USD")
    promise = _monetary(
        "CONSIDERATION_PAYABLE", "INCREASE", PROMISE, _event(2), date(2026, 6, 1), 2,
        "50000.00", "PROMISE",
    )  # fmt: skip
    assert _run(same, [], monetary=[promise]).state.functional_targets == ()


def test_l6_5_refund_liability_publishes_the_jet_04b_functional_amount() -> None:
    """S14-R-01 (L6-5): per refund-liability component, the JET-04b functional amount is the
    contract-liability relief an increase debits (330.00 at the historical 1.1000) less each release
    consumed at spot (230.00 on 15 April, 110.00 at the 31 May expiry). With the JET-10d differences
    it gives the layers' carrying (336.00, 108.00, 0.00). A same-currency unit publishes none."""
    state = _chk_084_a().state
    refunds = {
        t.period_key: (t.amount_txn, t.amount_functional)
        for t in state.functional_targets
        if t.measure == REFUND_MEASURE and t.subject_key == RETURNS
    }
    assert refunds == {
        "FY2026-P03": (30000, 33000),
        "FY2026-P04": (10000, 10000),
        "FY2026-P05": (0, -1000),
    }
    remeasured = _remeasured(state, "JET-10d", "REFUND_LIABILITY")
    carrying = {period: refunds[period][1] + remeasured[period] for period in refunds}
    assert carrying == {"FY2026-P03": 33600, "FY2026-P04": 10800, "FY2026-P05": 0}
    calendar = bundles.entity(months=3, books=("ASC606",))
    same = book_context(calendar, book_code="ASC606", currency="USD")
    increase = _monetary(
        "REFUND_LIABILITY", "INCREASE", RETURNS, _event(3), date(2026, 3, 1), 3, "300.00",
        "ESTIMATE", control="DEBIT", subject=PRODUCT,
    )  # fmt: skip
    measures = {t.measure for t in _run(same, [], monetary=[increase]).state.functional_targets}
    assert REFUND_MEASURE not in measures


def test_l6_5_deposit_publishes_the_jet_01b_functional_amounts() -> None:
    """S14-R-01 (L6-5): per ``<contract>@<entity>``, the JET-01b receipt's functional amount is the
    deposit layer created at spot (1,100.00 at 1.1000) and the criteria-met transfer's the portion
    consumed at spot (1,130.00 at 1.1300), cumulative at every period end. A same-currency unit
    publishes none, and a deposit flow without an EMOD-12 reason is refused."""
    state = _chk_084_b().state
    deposits = {
        (t.measure, t.period_key): (t.amount_txn, t.amount_functional)
        for t in state.functional_targets
        if t.measure.startswith("deposit_") and t.subject_key == CONTRACT
    }
    assert deposits == {
        ("deposit_received_cum", "FY2026-P01"): (100000, 110000),
        ("deposit_received_cum", "FY2026-P02"): (100000, 110000),
        ("deposit_to_contract_liability_cum", "FY2026-P02"): (100000, 113000),
    }
    calendar = bundles.entity(months=2, books=("ASC606",))
    same = book_context(calendar, book_code="ASC606", currency="USD")
    receipt = _monetary(
        "DEPOSIT_LIABILITY", "INCREASE", DEPOSIT, _event(2), date(2026, 1, 10), 2, "1000.00",
        "RECEIPT",
    )  # fmt: skip
    assert _run(same, [], monetary=[receipt]).state.functional_targets == ()
    unknown = dataclasses.replace(receipt, reason="PROMISE")
    with pytest.raises(ValueError, match="S02-R-08"):
        _run(same, [], monetary=[unknown])


def test_l7_6_release_over_several_layers_creates_the_liability_at_their_sum() -> None:
    """D-87 L6-5-Q-26 (S12-R-20, S12-INV-08, S14-R-11): a JET-04b release that consumes several
    refund-liability layers takes Σ per-layer round(take × spot) as its functional amount, and the
    contract-liability layer the release creates takes the same carrying, so GL and layers tie with
    no residue. Layers of EUR 100.05 and 200.05 released on 15 April at 1.1000 consume 110.06 and
    220.06 (330.12), where round(300.10 × 1.1000) is 330.11."""
    refund = "REFUND_LIABILITY"
    control = [_invoice(2, date(2026, 3, 1), "10000.00")]
    monetary = [
        _monetary(
            refund, "INCREASE", RETURNS, _event(3), date(2026, 3, 1), 3, "100.05", "ESTIMATE",
            control="DEBIT", subject=PRODUCT,
        ),
        _monetary(
            refund, "INCREASE", RETURNS, _event(4), date(2026, 3, 10), 4, "200.05", "ESTIMATE",
            control="DEBIT", subject=PRODUCT,
        ),
        _monetary(
            refund, "DECREASE", RETURNS, _event(5), date(2026, 4, 15), 5, "300.10", "RETURN",
            control="CREDIT", subject=PRODUCT,
        ),
    ]  # fmt: skip
    rates = [
        _spot(date(2026, 3, 1), "1.1000"),
        _spot(date(2026, 3, 10), "1.1200"),
        _spot(date(2026, 4, 15), "1.1000"),
        _period_rate("closing", 3, "1.1200"),
        _period_rate("closing", 4, "1.1000"),
    ]
    case = _run(_context(months=4), rates, control=control, monetary=monetary)
    state, trace = case.state, case.trace
    released = f"CONTRACT_LIABILITY:{_event(5)}"

    assert _moves(state, "LIABILITY_LAYER_CONSUMED", refund) == [
        (f"{refund}:{_event(3)}", date(2026, 4, 15), 10005, 11006, None),
        (f"{refund}:{_event(4)}", date(2026, 4, 15), 20005, 22006, None),
    ]
    created = [
        move
        for move in _moves(state, "LIABILITY_LAYER_CREATED", "CONTRACT_LIABILITY")
        if move[0] == released
    ]
    assert created == [(released, date(2026, 4, 15), 30010, 33012, None)]
    node = _node(trace, f"fx_layer_created:{released}:FY2026-P04")
    assert (node.formula_id, node.value) == ("fx.gain_loss.sum.v1", "330.12")
    refunds = {
        t.period_key: t.amount_functional
        for t in state.functional_targets
        if t.measure == REFUND_MEASURE and t.subject_key == RETURNS
    }
    # The JET-04b release moves the functional target by the same 330.12.
    assert refunds["FY2026-P03"] - refunds["FY2026-P04"] == 33012
    assert [row for row in _open(state, "FY2026-P04") if row[0] == released] == [
        (released, 30010, 33012)
    ]
    assert [row for row in _open(state, "FY2026-P04") if row[0].startswith(refund)] == []


def _released_into_assets(asset: str, months: int) -> tuple[FxState, Trace]:
    """A contract asset of ``asset`` (the March average 1.0800) absorbs a JET-04b release of EUR
    300.10 on 15 April at spot 1.1000 that consumes refund-liability layers of EUR 100.05 and 200.05
    at 110.06 and 220.06 (330.12), where round(300.10 × 1.1000) is 330.11. A five-month world adds
    a May reclass attribution of the open asset."""
    refund = "REFUND_LIABILITY"
    control = [_release(SERVICES, date(2026, 3, 31), asset)]
    monetary = [
        _monetary(
            refund, "INCREASE", RETURNS, _event(3), date(2026, 3, 1), 3, "100.05", "ESTIMATE",
            subject=PRODUCT,
        ),
        _monetary(
            refund, "INCREASE", RETURNS, _event(4), date(2026, 3, 10), 4, "200.05", "ESTIMATE",
            subject=PRODUCT,
        ),
        _monetary(
            refund, "DECREASE", RETURNS, _event(5), date(2026, 4, 15), 5, "300.10", "RETURN",
            control="CREDIT", subject=PRODUCT,
        ),
    ]  # fmt: skip
    rates = [
        _spot(date(2026, 3, 1), "1.1000"),
        _spot(date(2026, 3, 10), "1.1200"),
        _spot(date(2026, 4, 15), "1.1000"),
        _period_rate("average", 3, "1.0800"),
        *(_period_rate("closing", month, "1.0800") for month in range(3, months + 1)),
    ]
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    reclass: tuple[Target, ...] = ()
    if months == 5:
        node = tb.node(
            measure="netting_reclass_amount",
            subject_key=SERVICES,
            period_key="FY2026-P05",
            value=usd("199.90"),
            currency="EUR",
            minor_unit=2,
            formula_id="fx.gain_loss.sum.v1",
            inputs=[SourceRef("source_record", f"{SERVICES}@FY2026-P05", {"value": "199.90"})],
            params={"signs": "1"},
            narrative_key="fx.gain_loss.sum",
        )
        reclass = (
            Target(
                BookCode.ASC606, ENTITY, SERVICES, "netting_reclass_amount", "FY2026-P05",
                "CONTRACT_ASSET", usd("199.90"), None, node,
            ),
        )  # fmt: skip
    flows = FxFlows(tuple(control), monetary=tuple(monetary))
    costs = _PartCosts(allocated_state([]), flows, PartInputs(reclass=reclass))
    state = s12_fx_entities.run(_context(months=months), costs, tb, rates=RateIndex(rates))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _control_gl(state: FxState, period: str) -> int:
    """The functional control-role GL (asset positive): the revenue relief, the JET-04b release
    credited at the portions consumed, and the JET-10a differences."""
    revenue = _targets(state.functional_targets, SERVICES)[period]
    released = _targets(state.functional_targets, RETURNS)[period]
    return revenue + released + _remeasured(state, "JET-10a", "CONTRACT_ASSET")[period]


def test_l8_e_release_residue_folds_into_the_last_asset_settlement() -> None:
    """D-88 L7-6-Q-2 (a): a release absorbed by the contract assets it settles creates no
    contract-liability layer, so the residue r = 330.12 − 330.11 = 0.01 folds into the last asset
    settlement: remeasured 6.00 + 0.01 = 6.01 (JET-10a) and settled 330.11 + 0.01 = 330.12. The
    control-role GL ties to the layers, with no ROUNDING line."""
    state, trace = _released_into_assets("300.10", 4)
    asset = f"CONTRACT_ASSET:{SERVICES}@FY2026-P03"
    subject = f"{asset}@{_event(5)}#REFUND_RELEASE@{PRODUCT}"

    assert _moves(state, "ASSET_LAYER_CREATED") == [(asset, date(2026, 3, 31), 30010, 32411, None)]
    assert _moves(state, "ASSET_LAYER_REMEASURED") == [
        (asset, date(2026, 4, 15), 30010, 601, "SETTLEMENT")
    ]
    assert _moves(state, "ASSET_LAYER_SETTLED") == [(asset, date(2026, 4, 15), 30010, 33012, None)]
    assert _moves(state, "LIABILITY_LAYER_CREATED", "CONTRACT_LIABILITY") == []
    residue = _node(trace, f"fx_layer_remeasured:{subject}#release_residue:FY2026-P04")
    assert (residue.formula_id, residue.params["signs"], residue.value) == (
        "fx.gain_loss.sum.v1",
        "1|1|-1",
        "0.01",
    )
    remeasured = f"fx_layer_remeasured:{subject}#release_total:FY2026-P04"
    settled = f"fx_layer_settled:{subject}#release_total:FY2026-P04"
    assert (_node(trace, remeasured).value, _node(trace, settled).value) == ("6.01", "330.12")
    assert {
        move.movement_kind: move.trace_node_id
        for move in state.layer_movements
        if move.balance_role == "CONTRACT_ASSET" and move.source_key == _event(5)
    } == {"ASSET_LAYER_REMEASURED": remeasured, "ASSET_LAYER_SETTLED": settled}
    assert _remeasured(state, "JET-10a", "CONTRACT_ASSET")["FY2026-P04"] == 601
    assert _open(state, "FY2026-P04") == []
    assert _control_gl(state, "FY2026-P04") == 0


def test_l8_e_partial_take_folds_the_residue_and_keeps_the_carrying() -> None:
    """D-88 L7-6-Q-2 (b): a release of EUR 300.10 from a contract-asset layer of EUR 500.00 at
    540.00 remeasures 330.11 − 324.11 + 0.01 = 6.01 and settles 330.12. The carrying keeps
    540.00 − 324.11 = 215.89, which is the control-role GL, and the May reclass apportions it from
    the layer movements (``reclass._shares``)."""
    state, _trace = _released_into_assets("500.00", 5)
    asset = f"CONTRACT_ASSET:{SERVICES}@FY2026-P03"

    assert _moves(state, "ASSET_LAYER_REMEASURED") == [
        (asset, date(2026, 4, 15), 30010, 601, "SETTLEMENT")
    ]
    assert _moves(state, "ASSET_LAYER_SETTLED") == [(asset, date(2026, 4, 15), 30010, 33012, None)]
    assert _open(state, "FY2026-P04") == [(asset, 19990, 21589)]
    assert _control_gl(state, "FY2026-P04") == 21589
    reclass = [
        (t.subject_key, t.period_key, t.amount_txn, t.amount_functional)
        for t in state.functional_targets
        if t.measure == "netting_reclass_amount"
    ]
    assert reclass == [(f"{SERVICES}#CONTRACT_ASSET", "FY2026-P05", 19990, 21589)]


def _late(late: int, march: int) -> _Case:
    control = [
        _invoice(2, date(2026, 1, 1), "1000.00"),
        _on_event("REVENUE", late, date(2026, 2, 15), "1500.00", SERVICES),
        _on_event("REVENUE", march, date(2026, 3, 15), "100.00", LICENCE),
    ]
    rates = [
        _spot(date(2026, 1, 1), "1.1000"),
        _spot(date(2026, 3, 10), "1.2000"),
        _period_rate("average", 2, "1.1300"),
        _period_rate("average", 3, "1.1500"),
        _period_rate("closing", 2, "1.1400"),
        _period_rate("closing", 3, "1.1600"),
    ]
    return _run(_context(months=3), rates, control=control)


def test_s12_r13_late_event_rates() -> None:
    # The February delivery is recorded in March, after the March event (record_seq 9 > 5).
    case = _late(late=9, march=5)
    state, trace = case.state, case.trace

    created = [
        (move.layer_key, move.effective_date, move.amount_functional, move.rate_key)
        for move in state.layer_movements
        if move.movement_kind == "ASSET_LAYER_CREATED"
    ]
    assert created == [
        (f"CONTRACT_ASSET:{_event(9)}", date(2026, 2, 15), 56500, "EURUSD-AVERAGE-FY2026-P02"),
        (f"CONTRACT_ASSET:{_event(5)}", date(2026, 3, 15), 11500, "EURUSD-AVERAGE-FY2026-P03"),
    ]
    assert _targets(state.functional_targets, SERVICES) == {
        "FY2026-P02": 166500,
        "FY2026-P03": 166500,
    }
    # Every period end is evaluated at its own closing rate through the horizon (S12-R-13).
    assert _remeasured(state, "JET-10a", "CONTRACT_ASSET") == {
        "FY2026-P02": 500,
        "FY2026-P03": 1600,
    }
    february = _node(trace, f"fx_layer_remeasured:CONTRACT_ASSET:{_event(9)}:FY2026-P02")
    assert [ref.ref_id for ref in february.inputs if isinstance(ref, SourceRef)] == [
        "EURUSD-CLOSING-FY2026-P02"
    ]

    def amounts(fx: FxState) -> list[tuple[object, ...]]:
        return [
            (
                m.movement_kind,
                m.effective_date,
                m.amount_txn,
                m.amount_functional,
                m.rate_key,
                m.reason,
            )
            for m in fx.layer_movements
        ]

    # The recording order changes no amount: the replay converts by effective date (POL-181).
    assert amounts(_late(late=5, march=9).state) == amounts(state)


def test_s12_inv_02_no_remeasurement_to_revenue() -> None:
    cases = [_chk_081(), _chk_082("ASC606"), _chk_083(), _chk_084_a(), _chk_084_b(), _chk_084_c()]
    for case in cases:
        assert case.state.remeasurement_targets
        for target in case.state.remeasurement_targets:
            assert target.part in PARTS
            assert target.balance_role in BALANCE_ROLES
            assert target.amount_txn == 0
        assert {move.balance_role for move in case.state.layer_movements} <= BALANCE_ROLES
        for node in case.trace.nodes:
            if node.measure == "revenue_functional":
                assert not any(
                    isinstance(item, str) and item.startswith("fx_layer_remeasured:")
                    for item in node.inputs
                )


def test_s12_inv_08_monetary_layers_equal_balances() -> None:
    for case, months in ((_chk_084_a(), 5), (_chk_084_b(), 2), (_chk_084_c(), 6)):
        state = case.state
        for month in range(1, months + 1):
            period = f"FY2026-P{month:02d}"
            end = month_end(date(2026, month, 1))
            for role in MONETARY_ROLES:
                balance = sum(
                    flow.amount if flow.direction == "INCREASE" else -flow.amount
                    for flow in case.monetary
                    if flow.role == role and flow.effective_date <= end
                )
                layers = [
                    b
                    for b in state.layer_balances
                    if b.period_key == period and b.balance_role == role
                ]
                assert sum(b.txn_open for b in layers) == balance, (period, role)
                for b in layers:
                    closing = case.closing[period]
                    assert b.fn_carrying == round_half_up(Fraction(b.txn_open, 100) * closing, 2)
        # A fully consumed monetary layer ends at functional 0.
        for created in state.layer_movements:
            if created.movement_kind != "LIABILITY_LAYER_CREATED":
                continue
            if created.balance_role not in MONETARY_ROLES:
                continue
            of_layer = [m for m in state.layer_movements if m.layer_key == created.layer_key]
            consumed = [m for m in of_layer if m.movement_kind == "LIABILITY_LAYER_CONSUMED"]
            if sum(m.amount_txn for m in consumed) != created.amount_txn:
                continue
            remeasured = sum(
                m.amount_functional
                for m in of_layer
                if m.movement_kind == "LIABILITY_LAYER_REMEASURED"
            )
            out = sum(m.amount_functional for m in consumed)
            assert created.amount_functional + remeasured - out == 0


def _contract_period_policy(ctx: BookContext, contract: str, period: str) -> BookContext:
    from erev_engine.bundle import ResolvedPolicyInput, contract_period_key

    exception = ResolvedPolicyInput(
        "fx.cl_historical_layering",
        "CONTRACT_PERIOD",
        contract_period_key(contract, ENTITY, period),
        "DISABLED_REMEASURE_AS_MONETARY",
        "C",
        "OVR-MEMBER",
        "P",
    )
    return dataclasses.replace(
        ctx,
        policies=PolicyResolver(
            tuple(
                sorted(
                    (*ctx.policies.all(), exception),
                    key=lambda p: (p.code, p.scope, p.subject_key),
                )
            )
        ),
    )


@pytest.mark.parametrize(
    "book,monetary_member,revenue,fx",
    [
        ("ASC606", "first", 111000, 23000),
        ("ASC606", "second", 110000, 24000),
        ("IFRS15", "first", 110000, 0),
        ("IFRS15", "second", 110000, 0),
    ],
)
@pytest.mark.parametrize("first", ["A", "A/part@entity#item:%2F"])
def test_member_exception_follows_originating_layer_not_revenue_member(
    book: str,
    monetary_member: str,
    revenue: int,
    fx: int,
    first: str,
) -> None:
    from erev_engine.stages.s01_canonicalize import contract_entity_subject_key, encode_key

    second = "B"
    chosen = first if monetary_member == "first" else second
    ctx = _contract_period_policy(_context(book=book, months=1), chosen, "FY2026-P01")
    first_event, second_event = f"{encode_key(first)}/EV-2", f"{encode_key(second)}/EV-3"
    subject = f"{encode_key(second)}/S"
    control = [
        dataclasses.replace(
            _invoice(2, date(2026, 1, 1), "12000.00"),
            subject_key=contract_entity_subject_key(first, ENTITY),
            source_key=first_event,
        ),
        dataclasses.replace(
            _invoice(3, date(2026, 1, 1), "12000.00"),
            subject_key=contract_entity_subject_key(second, ENTITY),
            source_key=second_event,
        ),
        _release(subject, date(2026, 1, 31), "1000.00"),
    ]
    case = _run(
        ctx,
        [
            _spot(date(2026, 1, 1), "1.1000"),
            _period_rate("average", 1, "1.1100"),
            _period_rate("closing", 1, "1.1200"),
        ],
        control=control,
    )
    state = case.state
    assert _targets(state.functional_targets, subject) == {"FY2026-P01": revenue}
    assert _remeasured(state, "JET-10b", "CONTRACT_LIABILITY").get("FY2026-P01", 0) == fx
    first_carrying = 1232000 if book == "ASC606" and monetary_member == "first" else 1210000
    second_carrying = 1344000 if book == "ASC606" and monetary_member == "second" else 1320000
    assert _open(state, "FY2026-P01") == [
        (f"CONTRACT_LIABILITY:{first_event}", 1100000, first_carrying),
        (f"CONTRACT_LIABILITY:{second_event}", 1200000, second_carrying),
    ]
    assert revenue + first_carrying + second_carrying - fx == 2640000
    # Cross-member consumption retains the layer owner's identity in persistence output.
    assert {
        movement.contract_key
        for movement in state.layer_movements
        if movement.layer_key == f"CONTRACT_LIABILITY:{first_event}"
    } == {first}


def test_later_period_exception_does_not_remeasure_prior_period_layer_balance() -> None:
    ctx = _contract_period_policy(_context(months=2), CONTRACT_KEY, "FY2026-P02")
    state = _run(
        ctx,
        [
            _spot(date(2026, 1, 1), "1.1000"),
            _period_rate("closing", 1, "1.1200"),
            _period_rate("closing", 2, "1.1500"),
        ],
        control=[_invoice(2, date(2026, 1, 1), "12000.00")],
    ).state
    layer = f"CONTRACT_LIABILITY:{_event(2)}"
    assert _open(state, "FY2026-P01") == [(layer, 1200000, 1320000)]
    assert _open(state, "FY2026-P02") == [(layer, 1200000, 1380000)]
    assert _remeasured(state, "JET-10b", "CONTRACT_LIABILITY") == {"FY2026-P02": 60000}


@pytest.mark.parametrize("released", ["0.00", "6000.00", "12000.00"])
@pytest.mark.parametrize("closing", ["1.1200", "1.0800"])
def test_return_to_historical_basis_cannot_hide_a_carrying_residue(
    released: str, closing: str
) -> None:
    ctx = _contract_period_policy(_context(months=2), CONTRACT_KEY, "FY2026-P01")
    control = [_invoice(2, date(2026, 1, 1), "12000.00")]
    if released != "0.00":
        control.append(_release(SERVICES, date(2026, 2, 28), released))
    with pytest.raises(EngineError) as refused:
        _run(
            ctx,
            [
                _spot(date(2026, 1, 1), "1.1000"),
                _period_rate("closing", 1, closing),
                _period_rate("average", 2, "1.1500"),
            ],
            control=control,
        )
    error = refused.value
    expected = 1320000 - usd(released) * 11 // 10
    residue = 24000 if closing == "1.1200" else -24000
    assert error.code == "ENGINE_INVARIANT_VIOLATED"
    assert error.subject_key == f"CONTRACT_LIABILITY:{_event(2)}"
    assert error.detail == {
        "rule": "S12-INV-01" if released == "12000.00" else "S12-R-05",
        "period_key": "FY2026-P02",
        "txn_open": str(1200000 - usd(released)),
        "carrying": str(expected + residue),
        "expected_carrying": str(expected),
    }
