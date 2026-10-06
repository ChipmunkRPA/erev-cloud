"""PROP:P12 FX layers (dev-guide §9.7; ENGINE_SPEC_B §12.3; D-25, D-25b; REQ-FX-002, REQ-FX-003).

Over generated rate paths and billing, revenue, credit-memo, refund-liability, deposit,
consideration-payable and ``ENGINE`` mode receivable paths, in the ASC606 and IFRS15 books:
contract-liability layer functional amounts never change after creation and consumed layers end at
0 (S12-INV-01); remeasurement never targets revenue (S12-INV-02); contract assets, receivables,
refund liabilities, deposit liabilities and consideration payable carry transaction × closing rate
at every period end and move at spot at settlement (S12-INV-04, S12-INV-08), with every difference
in the net FX gain or loss. The stage 09 to 11 flows are generated directly (D-81 integration after
merge; L2-5-Q-10). Every trace re-evaluates node for node.

A release to the control role (JET-04b release, JET-01b at criteria met) ties per source: the
monetary portions consumed at spot equal the contract-asset settlements plus the contract-liability
layer it creates. That layer takes the release carrying (D-87 L6-5-Q-26), and when the asset
settlements absorb the whole release the residue folds into the last settlement (D-88 L7-6-Q-2);
each such amount stays within one minor unit per portion of transaction × spot (D-89b).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import FxRateInput
from erev_engine.dates import month_end
from erev_engine.money import round_half_up, to_fraction
from erev_engine.stages import s12_fx_entities
from erev_engine.stages.s12_fx_entities import (
    ControlFlow,
    FxFlows,
    FxState,
    LayerMovement,
    MonetaryFlow,
    ReceivableFlow,
)
from erev_engine.stages.state import AllocatedState, PolicyResolver, RateIndex
from erev_engine.trace import TraceBuilder, reevaluate
from hypothesis import given
from hypothesis import strategies as st
from support import bundles
from support.recognition import allocated_state, book_context
from support.strategies import fx_rate_paths

pytestmark = pytest.mark.property

ENTITY = bundles.ENTITY_CODE
CONTRACT = f"K-01@{ENTITY}"
OBLIGATION = "K-01/POB-1"
RETURNS = f"{OBLIGATION}#RETURN"
DEPOSIT = f"{CONTRACT}#DEPOSIT"
ASSET_ROLES = frozenset({"CONTRACT_ASSET", "ACCOUNTS_RECEIVABLE"})
CONTRACT_ASSET = frozenset({"CONTRACT_ASSET"})
CONTRACT_LIABILITY = frozenset({"CONTRACT_LIABILITY"})
MONETARY_ROLES = frozenset({"REFUND_LIABILITY", "DEPOSIT_LIABILITY", "CONSIDERATION_PAYABLE"})
ASSET_PARTS = frozenset({"JET-10a", "JET-10a′"})
LIABILITY_PARTS = frozenset({"JET-10b", "JET-10c", "JET-10d"})


@dataclass(frozen=True, slots=True)
class _Costs:
    allocated: AllocatedState
    fx_flows: FxFlows


@dataclass(frozen=True, slots=True)
class FxCase:
    book: str
    months: int
    policies: tuple[tuple[str, str], ...]
    rates: tuple[FxRateInput, ...]
    flows: FxFlows
    spot: tuple[Fraction, ...]  # per period, dated the period start
    closing: tuple[Fraction, ...]


def _rate(kind: str, index: int, value: Decimal) -> FxRateInput:
    start = date(2026, index + 1, 1)
    period = f"FY2026-P{index + 1:02d}"
    if kind == "spot":
        return FxRateInput(f"SPOT-{period}", "FX@v1", kind, "EUR", "USD", start, None, value)
    end = month_end(start)
    return FxRateInput(f"{kind.upper()}-{period}", "FX@v1", kind, "EUR", "USD", end, period, value)


@st.composite
def fx_cases(draw: st.DrawFn) -> FxCase:
    months = draw(st.integers(1, 6))
    book = draw(st.sampled_from(("ASC606", "IFRS15")))
    consumption = draw(st.sampled_from(("FIFO", "PRO_RATA")))
    remainder = draw(st.sampled_from(("PERIOD_AVERAGE", "TRANSACTION_DATE_SPOT")))
    policies = (
        ("fx.cl_layer_consumption", consumption),
        ("fx.unbilled_revenue_rate", remainder),
    )
    paths = {
        kind: draw(fx_rate_paths(max_periods=months)) for kind in ("spot", "average", "closing")
    }
    rows: list[FxRateInput] = []
    spot: list[Fraction] = []
    closing: list[Fraction] = []
    for index in range(months):
        values = {kind: path[index % len(path)] for kind, path in paths.items()}
        rows += [_rate(kind, index, value) for kind, value in values.items()]
        spot.append(to_fraction(values["spot"]))
        closing.append(to_fraction(values["closing"]))

    control: list[ControlFlow] = []
    monetary: list[MonetaryFlow] = []
    receivables: list[ReceivableFlow] = []
    counter = [0]

    def event() -> tuple[int, str]:
        counter[0] += 1
        return counter[0], f"K-01/EV-{counter[0]:06d}"

    refund_open = deposit_open = 0
    for index in range(months):
        start = date(2026, index + 1, 1)
        middle = date(2026, index + 1, 15)
        end = month_end(start)
        period = f"FY2026-P{index + 1:02d}"
        billed = draw(st.integers(0, 10**6))
        if billed:
            seq, key = event()
            control.append(ControlFlow("BILLING", ENTITY, CONTRACT, key, start, seq, billed, start))
            invoiced = draw(st.integers(0, billed))
            if invoiced:
                receivables.append(
                    ReceivableFlow("INVOICE", ENTITY, CONTRACT, key, key, start, seq, invoiced)
                )
                paid = draw(st.integers(0, invoiced))
                if paid:
                    seq, payment = event()
                    receivables.append(
                        ReceivableFlow(
                            "REDUCTION", ENTITY, CONTRACT, key, payment, middle, seq, paid
                        )
                    )
        memo = draw(st.integers(0, 10**5))
        if memo:
            seq, key = event()
            control.append(ControlFlow("CREDIT_MEMO", ENTITY, CONTRACT, key, middle, seq, memo))
        increase = draw(st.integers(0, 10**5))
        if increase:
            seq, key = event()
            monetary.append(
                MonetaryFlow(
                    "REFUND_LIABILITY", "INCREASE", ENTITY, OBLIGATION, RETURNS, key, middle, seq,
                    increase, "ESTIMATE", "DEBIT",
                )
            )  # fmt: skip
            refund_open += increase
        decrease = draw(st.integers(0, refund_open))
        if decrease:
            seq, key = event()
            monetary.append(
                MonetaryFlow(
                    "REFUND_LIABILITY", "DECREASE", ENTITY, OBLIGATION, RETURNS, key, middle, seq,
                    decrease, "RETURN", "CREDIT",
                )
            )  # fmt: skip
            refund_open -= decrease
        received = draw(st.integers(0, 10**5))
        if received:
            seq, key = event()
            monetary.append(
                MonetaryFlow(
                    "DEPOSIT_LIABILITY", "INCREASE", ENTITY, CONTRACT, DEPOSIT, key, start, seq,
                    received, "RECEIPT",
                )
            )  # fmt: skip
            deposit_open += received
        transferred = draw(st.integers(0, deposit_open))
        if transferred:
            seq, key = event()
            monetary.append(
                MonetaryFlow(
                    "DEPOSIT_LIABILITY", "DECREASE", ENTITY, CONTRACT, DEPOSIT, key, middle, seq,
                    transferred, "CRITERIA_MET", "CREDIT",
                )
            )  # fmt: skip
            deposit_open -= transferred
        promised = draw(st.integers(0, 10**5))
        if promised:
            seq, key = event()
            monetary.append(
                MonetaryFlow(
                    "CONSIDERATION_PAYABLE", "INCREASE", ENTITY, CONTRACT, f"{CONTRACT}#P-{seq}",
                    key, middle, seq, promised, "PROMISE",
                )
            )  # fmt: skip
        revenue = draw(st.integers(0, 10**6))
        if revenue:
            source = f"{OBLIGATION}@{period}"
            control.append(ControlFlow("REVENUE", ENTITY, OBLIGATION, source, end, None, revenue))
    flows = FxFlows(tuple(control), monetary=tuple(monetary), receivables=tuple(receivables))
    return FxCase(book, months, policies, tuple(rows), flows, tuple(spot), tuple(closing))


def _run(case: FxCase) -> FxState:
    calendar = bundles.entity(months=case.months, books=(case.book,))
    ctx = book_context(calendar, book_code=case.book, currency="EUR")
    chosen = dict(case.policies)
    resolved = tuple(
        dataclasses.replace(policy, value=chosen[policy.code]) if policy.code in chosen else policy
        for policy in ctx.policies.all()
    )
    ctx = dataclasses.replace(
        ctx, currencies=bundles.currencies("EUR", "USD"), policies=PolicyResolver(resolved)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    costs = _Costs(allocated_state([]), case.flows)
    state = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(case.rates))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state


def _at(amount: int, rate: Fraction) -> int:
    return round_half_up(Fraction(amount, 100) * rate, 2)


@given(case=fx_cases())
def test_p12_fx_layers(case: FxCase) -> None:
    state = _run(case)
    assert state.findings == ()
    moves = state.layer_movements
    closing = {f"FY2026-P{index + 1:02d}": rate for index, rate in enumerate(case.closing)}

    def spot(on: date) -> Fraction:
        return case.spot[on.month - 1]

    # The releases to the control role: refund or deposit decreases that credit it (S12-R-20).
    releases = {
        flow.source_key
        for flow in case.flows.monetary
        if flow.direction == "DECREASE" and flow.control == "CREDIT"
    }

    def of_source(key: str, kind: str, roles: frozenset[str]) -> list[LayerMovement]:
        return [
            m
            for m in moves
            if m.source_key == key and m.movement_kind == kind and m.balance_role in roles
        ]

    def release_portions(key: str) -> tuple[list[LayerMovement], list[LayerMovement]]:
        consumed = of_source(key, "LIABILITY_LAYER_CONSUMED", MONETARY_ROLES)
        settled = of_source(key, "ASSET_LAYER_SETTLED", CONTRACT_ASSET)
        return consumed, settled

    # Contract-liability layers: created at spot, or at the release carrying, never remeasured, and
    # a consumed layer ends at 0.
    for created in moves:
        if created.movement_kind != "LIABILITY_LAYER_CREATED":
            continue
        if created.balance_role != "CONTRACT_LIABILITY":
            continue
        at_spot = _at(created.amount_txn, spot(created.effective_date))
        if created.source_key in releases:
            # D-87 L6-5-Q-26: the portions consumed at spot less the asset layers settled first.
            portions, settlements = release_portions(created.source_key)
            expected = sum(m.amount_functional for m in portions) - sum(
                m.amount_functional for m in settlements
            )
            assert abs(expected - at_spot) <= len(portions) + len(settlements)
        else:
            expected = at_spot
        assert created.amount_functional == expected
        of_layer = [m for m in moves if m.layer_key == created.layer_key]
        assert {m.movement_kind for m in of_layer} <= {
            "LIABILITY_LAYER_CREATED",
            "LIABILITY_LAYER_CONSUMED",
        }
        consumed = [m for m in of_layer if m.movement_kind == "LIABILITY_LAYER_CONSUMED"]
        if sum(m.amount_txn for m in consumed) == created.amount_txn:
            assert sum(m.amount_functional for m in consumed) == created.amount_functional

    # Remeasurement never targets revenue.
    assert all(m.balance_role != "REVENUE" for m in moves)
    for target in state.remeasurement_targets:
        assert target.part in ASSET_PARTS | LIABILITY_PARTS
        assert target.balance_role not in (None, "REVENUE")

    # Period end: assets, receivables and monetary liabilities carry transaction × closing.
    for balance in state.layer_balances:
        if balance.balance_role in ASSET_ROLES | MONETARY_ROLES:
            assert balance.fn_carrying == _at(balance.txn_open, closing[balance.period_key])
        else:
            assert balance.balance_role == "CONTRACT_LIABILITY"

    # Settlement: the settled portion moves at spot; receivable reductions relieve carrying only.
    for move in moves:
        settled_asset = (
            move.movement_kind == "ASSET_LAYER_SETTLED" and move.balance_role == "CONTRACT_ASSET"
        )
        settled_liability = (
            move.movement_kind == "LIABILITY_LAYER_CONSUMED" and move.balance_role in MONETARY_ROLES
        )
        at_spot = _at(move.amount_txn, spot(move.effective_date))
        if settled_asset and move.source_key in releases:
            # D-88 L7-6-Q-2: the last settlement of a release may take its residue.
            portions, settlements = release_portions(move.source_key)
            assert abs(move.amount_functional - at_spot) <= len(portions) + len(settlements)
        elif settled_asset or settled_liability:
            assert move.amount_functional == at_spot

    # A release ties per source: consumed == settled + created (D-87 L6-5-Q-26; D-88 L7-6-Q-2).
    for key in releases:
        portions, settlements = release_portions(key)
        created_layers = of_source(key, "LIABILITY_LAYER_CREATED", CONTRACT_LIABILITY)
        assert sum(m.amount_functional for m in portions) == sum(
            m.amount_functional for m in settlements
        ) + sum(m.amount_functional for m in created_layers)

    # A fully settled asset, receivable or monetary layer ends at functional 0.
    for key in {m.layer_key for m in moves if m.balance_role in ASSET_ROLES | MONETARY_ROLES}:
        of_layer = [m for m in moves if m.layer_key == key]
        created = next(m for m in of_layer if m.movement_kind.endswith("_CREATED"))
        out = [
            m
            for m in of_layer
            if m.movement_kind in ("ASSET_LAYER_SETTLED", "LIABILITY_LAYER_CONSUMED")
        ]
        if sum(m.amount_txn for m in out) == created.amount_txn:
            remeasured = sum(
                m.amount_functional for m in of_layer if m.movement_kind.endswith("_REMEASURED")
            )
            assert created.amount_functional + remeasured == sum(m.amount_functional for m in out)

    # Every difference lands in the net FX gain: asset parts less liability parts.
    horizon = f"FY2026-P{case.months:02d}"
    final = [t for t in state.remeasurement_targets if t.period_key == horizon]
    gain = [t.amount_functional for t in state.gain_loss_targets if t.period_key == horizon]
    expected = sum(t.amount_functional * (1 if t.part in ASSET_PARTS else -1) for t in final)
    assert gain == ([expected] if final else [])
