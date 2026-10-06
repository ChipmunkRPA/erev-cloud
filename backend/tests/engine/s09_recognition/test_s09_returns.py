"""Stage 09 returns within the units measures (ENC-7).

ENGINE_SPEC_B §9.2.7 S09-R-23 to S09-R-26 and §9.5; POLICIES ALG-06 §2.7.2 and §2.7.3 (CHK-029,
CHK-060, CHK-061), POL-051 to POL-053; legacy 07 §7 GT-08. The ``AllocatedState``, including the
stage 04 return path (ENGINE_SPEC S04-R-08b), is built against the documented contract
(support.recognition; D-81 integration after merge).
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import cast

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.enums import SubledgerPostingKind
from erev_engine.formulas import FORMULAS
from erev_engine.money import format_exact, largest_remainder, round_half_up
from erev_engine.stages import s10_billing_balances
from erev_engine.stages.s09_recognition import (
    RecognitionState,
    components,
    progress_events,
    returns,
    run,
    schedule,
)
from erev_engine.stages.s10_billing_balances import BalanceState, classification
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    PolicyResolver,
    ReturnPath,
    ReturnPin,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import ENTITY_CODE, entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    estimate_version,
    event_view,
    obligation,
    period_amounts,
    segment,
    targets_by_period,
    usd,
)

pytestmark: list[pytest.MarkDecorator] = []

C_RET = "C-RET"
O_RET = f"{C_RET}/L1-PROD"
TRANSFER = date(2026, 1, 10)
RETURNED = date(2026, 2, 10)
WINDOW_END = date(2026, 3, 15)
CTX = book_context(entity(months=3))
REDUCE_PRESET = {
    "returns.model": "EXPECTED_RETURNS",
    "returns.returned_units_scope": "REDUCE_CONTRACT_QUANTITY",
    "returns.reversal_rate": "AVERAGE_CARRYING_RATE",
}


def _run(ctx: BookContext, st: AllocatedState) -> tuple[RecognitionState, Trace]:
    """Run stage 09 and check that the trace reproduces every node (DG-ENG-04)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _product() -> ObligationState:
    """RET-CHK-029-S3-EX22: 100 products sold for 10,000.00 (TPL-UNITS, UNITS_DELIVERED)."""
    goods = segment(
        Fraction(10000), usd("10000.00"), start=TRANSFER, end=TRANSFER, quantity=Fraction(100)
    )
    return obligation(
        "L1-PROD",
        [goods],
        contract_key=C_RET,
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(100),
    )


def _pin(version_no: int, effective: date, expected: int) -> ReturnPin:
    """A RETURN_RATE version: k = 60.00, recovery costs 0, window ending 15 March 2026."""
    key = f"{C_RET}/RET-JAN@v{version_no}"
    return ReturnPin(effective, key, Fraction(expected), Fraction(60), Fraction(0), WINDOW_END)


def _chk_029_events(*revisions: tuple[int, date]) -> list[EventView]:
    def ev(version: int, event_type: str, when: date, payload: dict[str, object]) -> EventView:
        return event_view(C_RET, version, event_type, when, payload, obligation_keys=["L1-PROD"])

    events = [
        ev(3, "ESTIMATE_CHANGED", TRANSFER, {"estimate_version_id": f"{C_RET}/RET-JAN@v1"}),
        ev(
            4,
            "DELIVERY_RECORDED",
            TRANSFER,
            {"obligation_key": "L1-PROD", "quantity": Decimal("100"), "trigger": "DELIVERY"},
        ),
        ev(
            5,
            "BILLING_RECORDED",
            TRANSFER,
            {
                "invoice_number": "INV-RET-1",
                "line_external_id": "INV-RET-1-1",
                "obligation_key": "L1-PROD",
                "amount": Decimal("10000.00"),
                "issue_date": TRANSFER,
            },
        ),
        ev(
            6,
            "RETURN_RECORDED",
            RETURNED,
            {
                "obligation_key": "L1-PROD",
                "quantity": Decimal("2"),
                "refund_amount": Decimal("200"),
            },
        ),
        ev(
            7,
            "CREDIT_MEMO_RECORDED",
            RETURNED,
            {
                "credit_memo_number": "CM-RET-1",
                "credited_invoice_number": "INV-RET-1",
                "obligation_key": "L1-PROD",
                "amount": Decimal("200.00"),
                "issue_date": RETURNED,
            },
        ),
    ]
    for version, (version_no, when) in enumerate(revisions, start=8):
        payload = {"estimate_version_id": f"{C_RET}/RET-JAN@v{version_no}"}
        events.append(ev(version, "ESTIMATE_CHANGED", when, payload))
    return events


def _chk_029_state(
    pins: Sequence[ReturnPin], revisions: Sequence[tuple[int, date]] = ()
) -> AllocatedState:
    st = allocated_state(
        [_product()],
        events=_chk_029_events(*revisions),
        inception=TRANSFER,
        statuses=((TRANSFER, "ACTIVE"),),
    )
    path = ReturnPath(
        f"{C_RET}/RET-JAN", tuple(pins), ((TRANSFER, Fraction(100)),), Fraction(100), REDUCE_PRESET
    )
    return dataclasses.replace(st, return_paths={O_RET: path})


def _liabilities(state: returns.ReturnState) -> tuple[int, int]:
    """(refund liability, return asset) of ALG-06 steps 3 and 4 from the state, minor units."""
    return (
        round_half_up(state.p_ref * state.E_b, 2),
        round_half_up(max(Fraction(0), state.k - state.c_rec) * state.E, 2),
    )


def test_chk_029_revenue_path() -> None:
    st = _chk_029_state([_pin(1, TRANSFER, 3)])
    state, trace = _run(CTX, st)
    targets = targets_by_period(state, O_RET)
    # ALG-06 step 2: round(100 × (100 − 0 − 3)), round(100 × (100 − 2 − 1)), round(100 × 98).
    assert [targets[f"FY2026-P0{month}"] for month in (1, 2, 3)] == [
        usd("9700.00"),
        usd("9700.00"),
        usd("9800.00"),
    ]
    january, february, march = (state.return_states[(O_RET, f"FY2026-P0{m}")] for m in (1, 2, 3))
    assert (january.N, january.Y, january.E, january.E_b) == (100, 0, 3, 3)
    assert _liabilities(january) == (usd("300.00"), usd("180.00"))
    assert (february.Y, february.E, february.E_b, february.returned_before_E) == (2, 1, 1, 2)
    assert _liabilities(february) == (usd("100.00"), usd("60.00"))
    assert (march.E, march.expired, _liabilities(march)) == (0, True, (0, 0))
    assert january.version_key == f"{C_RET}/RET-JAN@v1"

    node = _node(trace, f"return_expected_units:{O_RET}:FY2026-P02")
    assert (node.formula_id, Fraction(Decimal(node.value))) == ("returns.expected_units.v1", 1)
    assert [ref.ref_id for ref in node.inputs if not isinstance(ref, str)] == [
        f"{C_RET}/RET-JAN@v1"
    ]
    exact = _node(trace, f"revenue_target_exact:{O_RET}#FIXED:FY2026-P02")
    assert exact.formula_id == "returns.revenue_target.v1"
    assert exact.inputs == (node.id,)


def test_chk_060_revised_estimate_revenue_path() -> None:
    # E revised to 4 at the first period end, before any return.
    revised = date(2026, 1, 31)
    st = _chk_029_state([_pin(1, TRANSFER, 3), _pin(2, revised, 4)], revisions=[(2, revised)])
    state, _ = _run(CTX, st)
    targets = targets_by_period(state, O_RET)
    assert [targets[f"FY2026-P0{month}"] for month in (1, 2, 3)] == [
        usd("9600.00"),
        usd("9600.00"),
        usd("9800.00"),
    ]
    assert period_amounts(targets)["FY2026-P03"] == usd("200.00")
    february = state.return_states[(O_RET, "FY2026-P02")]
    assert (february.E, february.version_key) == (2, f"{C_RET}/RET-JAN@v2")
    assert _liabilities(february) == (usd("200.00"), usd("120.00"))
    march = state.return_states[(O_RET, "FY2026-P03")]
    assert (march.E, march.expiry_effect) == (0, usd("200.00"))


def test_chk_060_measures_publish_the_returns_reduction() -> None:
    """S09-R-23 at d_v: ``allocated_amount`` = a_posted − round(r × (Y + E)), and the measures
    publish that reduction, so the version memo moves with a RETURN_RATE revision and with each
    return, not with a boundary (S04-R-08, S08-R-02; EX-04-G2; L5-3-Q-1)."""
    revised = date(2026, 1, 31)
    st = _chk_029_state([_pin(1, TRANSFER, 3), _pin(2, revised, 4)], revisions=[(2, revised)])
    ob = st.obligations[0]
    before = schedule.obligation_measures(CTX, st, ob, TRANSFER)
    after_revision = schedule.obligation_measures(CTX, st, ob, revised)
    after_returns = schedule.obligation_measures(CTX, st, ob, RETURNED)
    expired = schedule.obligation_measures(CTX, st, ob, date(2026, 3, 31))
    assert [m.returns_reduction for m in (before, after_revision, after_returns, expired)] == [
        usd("300.00"),  # Y 0, E 3
        usd("400.00"),  # Y 0, E 4
        usd("400.00"),  # Y 2, E 2
        usd("200.00"),  # Y 2, E 0 after the window
    ]
    for m in (before, after_revision, after_returns, expired):
        assert m.allocated_amount == usd("10000.00") - cast(int, m.returns_reduction)
    unreturnable = dataclasses.replace(st, return_paths={})
    assert schedule.obligation_measures(CTX, unreturnable, ob, RETURNED).returns_reduction is None


def test_pt_06_portfolio_rate_pin_expects_rate_times_units_transferred() -> None:
    """A portfolio RETURN_RATE version states only the rate: E = rate × units transferred, as the
    stage 04 memo measures it (S04-R-08; POLICIES PT-06, CHK-116; L5-3-Q-3). Before, the path pin
    carried expected_quantity 0, so stage 09 recognised the whole consideration."""
    rate_pin = dataclasses.replace(_pin(1, TRANSFER, 0), rate=Fraction(3, 100))
    st = _chk_029_state([rate_pin])
    state, trace = _run(CTX, st)
    targets = targets_by_period(state, O_RET)
    # E = 0.03 × 100 = 3; then Y 2 and E 1; then 0 after the window: the CHK-029 revenue path.
    assert [targets[f"FY2026-P0{month}"] for month in (1, 2, 3)] == [
        usd("9700.00"),
        usd("9700.00"),
        usd("9800.00"),
    ]
    january = state.return_states[(O_RET, "FY2026-P01")]
    assert (january.E, _liabilities(january)) == (3, (usd("300.00"), usd("180.00")))
    february = state.return_states[(O_RET, "FY2026-P02")]
    assert (february.Y, february.E) == (2, 1)
    node = _node(trace, f"return_expected_units:{O_RET}:FY2026-P01")
    (source,) = [ref for ref in node.inputs if not isinstance(ref, str)]
    assert (source.detail["member"], source.detail["rate"], source.detail["value"]) == (
        "rate",
        "0.03",
        "3",
    )


def _golden_contract_1(rows: Sequence[tuple[date, str, str]]) -> AllocatedState:
    """Golden Contract 1 POB #1: 5 hardware units, X = 1,300 × 500 ÷ 2,018 (legacy 02 §5.3)."""
    posted = largest_remainder(
        130000, [Fraction(500), Fraction(368), Fraction(150), Fraction(1000)], ["1", "2", "3", "4"]
    )
    hardware = segment(
        Fraction(1300 * 500, 2018),
        posted[0],
        start=date(2023, 1, 1),
        end=date(2023, 12, 31),
        quantity=Fraction(5),
        measure="UNITS_DELIVERED",
    )
    ob = obligation(
        "POB #1",
        [hardware],
        contract_key="Contract 1",
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(5),
    )
    events = []
    for version, (when, event_type, quantity) in enumerate(rows, start=2):
        payload: dict[str, object] = {"obligation_key": "POB #1", "quantity": Decimal(quantity)}
        if event_type == "DELIVERY_RECORDED":
            payload["trigger"] = "DELIVERY"
        events.append(
            event_view("Contract 1", version, event_type, when, payload, obligation_keys=["POB #1"])
        )
    return allocated_state(
        [ob], events=events, inception=date(2023, 1, 1), statuses=((date(2023, 1, 1), "ACTIVE"),)
    )


def test_chk_061_golden_return() -> None:
    calendar = entity(start=date(2023, 1, 1), months=12)
    ctx = book_context(calendar, preset="LEGACY_PARITY")  # POL-052 CURRENT, POL-053 RESTORE
    rows = [
        (date(2023, 1, 31), "DELIVERY_RECORDED", "2"),
        (date(2023, 2, 28), "DELIVERY_RECORDED", "1"),
        (date(2023, 4, 30), "RETURN_RECORDED", "3"),
    ]
    st = _golden_contract_1(rows)
    state, trace = _run(ctx, st)
    subject = "Contract 1/POB #1"
    by_period = {t.period_key: t for t in state.revenue_targets if t.subject_key == subject}
    assert (by_period["FY2023-P02"].value, by_period["FY2023-P03"].value) == (
        usd("193.26"),
        usd("193.26"),
    )
    assert by_period["FY2023-P04"].value - by_period["FY2023-P03"].value == usd("-193.26")
    april, march = by_period["FY2023-P04"].exact, by_period["FY2023-P03"].exact
    assert april is not None and march is not None
    assert format_exact(april - march, 6) == "-193.260654"
    ob = st.obligations[0]
    hardware = ob.segments[0]
    assert (
        progress_events.remaining_quantity(
            ctx, st, st.contracts[0], ob, hardware, date(2023, 4, 30)
        )
        == 5
    )
    assert format_exact(hardware.x_exact - april, 4) == "322.1011"  # remaining allocation
    reversal = _node(trace, f"return_reversal@Contract 1/EV-000004:{subject}:-")
    assert (reversal.formula_id, reversal.params["rate"]) == (
        "returns.excess_reversal.v1",
        "CURRENT_REMAINING_RATE",
    )
    assert Fraction(Decimal(reversal.value)) == 0
    assert state.return_states == {}  # no return path: POL-051 ACTUAL_RETURNS_ONLY


def test_s09_r25_excess_reversal_rates() -> None:
    calendar = entity(start=date(2023, 1, 1), months=12)
    rows = [
        (date(2023, 1, 31), "DELIVERY_RECORDED", "3"),
        (date(2023, 2, 28), "RETURN_RECORDED", "1"),
        (date(2023, 3, 31), "DELIVERY_RECORDED", "1"),
        (date(2023, 4, 30), "DELIVERY_RECORDED", "2"),
    ]
    x_exact = Fraction(1300 * 500, 2018)
    subject = "Contract 1/POB #1"

    current = book_context(calendar, preset="LEGACY_PARITY")
    state, _ = _run(current, _golden_contract_1(rows))
    exact = {t.period_key: t.exact for t in state.revenue_targets if t.subject_key == subject}
    # CURRENT_REMAINING_RATE: (X − X × 3/5) ÷ 2 = X ÷ 5 per unit, the units measure over net units.
    assert exact["FY2023-P02"] == x_exact * 2 / 5
    assert exact["FY2023-P03"] == x_exact * 3 / 5

    average = book_context(
        calendar,
        preset="LEGACY_PARITY",
        overrides=[("returns.reversal_rate", "ENTITY", ENTITY_CODE, "AVERAGE_CARRYING_RATE")],
    )
    state, trace = _run(average, _golden_contract_1(rows))
    by_period = {t.period_key: t for t in state.revenue_targets if t.subject_key == subject}
    # AVERAGE_CARRYING_RATE: posted 193.26 ÷ 3 units kept = 64.42 per returned unit.
    after_return = x_exact * 3 / 5 - Fraction(19326, 100) / 3
    assert by_period["FY2023-P02"].exact == after_return
    assert by_period["FY2023-P02"].value == usd("128.84")
    # A later delivery earns the refreshed unit rate (X − e) ÷ remaining quantity (2 of 5 kept).
    assert by_period["FY2023-P03"].exact == x_exact - (x_exact - after_return) * 2 / 3
    assert by_period["FY2023-P04"].exact == x_exact
    assert by_period["FY2023-P04"].value == usd("322.10")  # C = A at completion
    node = _node(trace, f"return_reversal@Contract 1/EV-000003:{subject}:-")
    assert (node.params["rate"], node.params["a_posted"]) == ("AVERAGE_CARRYING_RATE", "32210")


def _batch(
    ctx: BookContext, events: Sequence[EventView]
) -> tuple[AllocatedState, RecognitionState]:
    batch = segment(
        Fraction(1000),
        usd("1000.00"),
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        quantity=Fraction(10),
    )
    ob = obligation(
        "POB-01", [batch], method="UNITS_DELIVERED", convention=None, quantity=Fraction(10)
    )
    st = allocated_state([ob], events=events)
    return st, _run(ctx, st)[0]


def _units_event(version: int, when: date, event_type: str, quantity: str) -> EventView:
    payload: dict[str, object] = {"obligation_key": "POB-01", "quantity": Decimal(quantity)}
    if event_type == "DELIVERY_RECORDED":
        payload["trigger"] = "DELIVERY"
    return event_view(CONTRACT_KEY, version, event_type, when, payload, obligation_keys=["POB-01"])


def test_s09_r24_returned_units_scope() -> None:
    o1 = f"{CONTRACT_KEY}/POB-01"
    shipped = _units_event(2, date(2026, 3, 10), "DELIVERY_RECORDED", "6")
    back = _units_event(3, date(2026, 4, 15), "RETURN_RECORDED", "2")
    april = date(2026, 4, 30)

    # REDUCE_CONTRACT_QUANTITY (default): the returned units leave the contract; Q − N unchanged.
    reduce_ctx = book_context()
    st, state = _batch(reduce_ctx, [shipped, back])
    ob, seg = st.obligations[0], st.obligations[0].segments[0]
    assert progress_events.remaining_quantity(reduce_ctx, st, st.contracts[0], ob, seg, april) == 4
    assert targets_by_period(state, o1)["FY2026-P04"] == usd("400.00")
    rest = _units_event(4, date(2026, 5, 20), "DELIVERY_RECORDED", "4")
    st, state = _batch(reduce_ctx, [shipped, back, rest])
    ob = st.obligations[0]
    may = date(2026, 5, 31)
    assert progress_events.remaining_quantity(reduce_ctx, st, st.contracts[0], ob, seg, may) == 0
    assert targets_by_period(state, o1)["FY2026-P05"] == usd("800.00")  # r × (10 − 2)

    # RESTORE_REMAINING_QUANTITY: the returned units are deliverable again.
    restore_ctx = book_context(
        overrides=[("returns.returned_units_scope", "OBLIGATION", o1, "RESTORE_REMAINING_QUANTITY")]
    )
    st, state = _batch(restore_ctx, [shipped, back])
    ob = st.obligations[0]
    assert progress_events.remaining_quantity(restore_ctx, st, st.contracts[0], ob, seg, april) == 6
    assert targets_by_period(state, o1)["FY2026-P04"] == usd("400.00")
    again = _units_event(4, date(2026, 5, 20), "DELIVERY_RECORDED", "6")
    st, state = _batch(restore_ctx, [shipped, back, again])
    ob = st.obligations[0]
    assert progress_events.remaining_quantity(restore_ctx, st, st.contracts[0], ob, seg, may) == 0
    assert targets_by_period(state, o1)["FY2026-P05"] == usd("1000.00")

    # Since a boundary under REDUCE: N counts the deliveries after it (7 remaining, 4 delivered).
    inception = segment(
        Fraction(1000),
        usd("1000.00"),
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        quantity=Fraction(10),
    )
    boundary = event_view(
        CONTRACT_KEY, 4, "CONTRACT_AMENDED", date(2026, 3, 1), {"modification_id": "MOD-1"}
    )
    prospective = segment(
        Fraction(1000),
        usd("1000.00"),
        start=date(2026, 3, 1),
        end=date(2026, 12, 31),
        basis="PROSPECTIVE",
        cause=SegmentCause.MODIFICATION,
        event_key=boundary.event_key,
        base_revenue_posted=usd("200.00"),
        base_revenue_exact=Fraction(200),
        quantity=Fraction(7),
        base_delivered=Fraction(2),
    )
    ob = obligation(
        "POB-01",
        [inception, prospective],
        method="UNITS_DELIVERED",
        convention=None,
        start=date(2026, 1, 1),
        quantity=Fraction(10),
    )
    events = [
        _units_event(2, date(2026, 1, 15), "DELIVERY_RECORDED", "3"),
        _units_event(3, date(2026, 2, 10), "RETURN_RECORDED", "1"),
        boundary,
        _units_event(5, date(2026, 4, 10), "DELIVERY_RECORDED", "4"),
        _units_event(6, date(2026, 5, 5), "RETURN_RECORDED", "1"),
    ]
    st = allocated_state([ob], events=events)
    remaining = progress_events.remaining_quantity(
        reduce_ctx, st, st.contracts[0], st.obligations[0], prospective, may
    )
    assert remaining == 3


def test_s09_r26_window_expiry_time_driven() -> None:
    """D-87 L6-5-Q-25: the right expires at the end of ``window_end_date``. A measurement dated on
    or after the window end has E = 0; the day before keeps E."""
    st = _chk_029_state([_pin(1, TRANSFER, 3)])
    ob = st.obligations[0]
    contract = st.contracts[0]
    seg = ob.segments[0]
    day_before = returns.return_state(CTX, st, contract, ob, seg, date(2026, 3, 14))
    assert (day_before.E, day_before.expired, day_before.expiry_effect) == (1, False, 0)
    assert components.target_at(CTX, st, ob, date(2026, 3, 14)).value == usd("9700.00")
    expired = returns.return_state(CTX, st, contract, ob, seg, WINDOW_END)
    assert (expired.E, expired.expired, expired.expiry_effect) == (0, True, usd("100.00"))
    assert components.target_at(CTX, st, ob, WINDOW_END).value == usd("9800.00")
    # RCP-07 and RCP-08: the expiry effect is time-driven and posts in mode CLOSE_RELEASE.
    assert returns.EXPIRY_AMOUNT_CLASS == "TIME"
    assert returns.EXPIRY_POSTING_PASS == SubledgerPostingKind.CLOSE_RELEASE
    state, trace = _run(CTX, st)
    march = state.return_states[(O_RET, "FY2026-P03")]
    assert (march.expired, march.expiry_effect) == (True, usd("100.00"))
    node = _node(trace, f"return_expected_units:{O_RET}:FY2026-P03")
    assert (node.params["window_end"], Fraction(Decimal(node.value))) == ("2026-03-15", 0)


def test_l7_5_return_on_the_window_end_date_still_counts() -> None:
    """D-87 L6-5-Q-25: the expiry sorts after the events of the window end date. The 10 February
    return takes 2 of E = 3, and a unit returned on 15 March is measured against the unexpired E = 1
    before it (JET-07d quantity 1, not 0); the period end of that day holds E = 0. A measurement
    positioned among the day's events carries param ``expiry_pending`` and keeps E; the formula
    re-evaluates both measurements."""
    last_day_return = event_view(
        C_RET,
        8,
        "RETURN_RECORDED",
        WINDOW_END,
        {"obligation_key": "L1-PROD", "quantity": Decimal("1"), "refund_amount": Decimal("100")},
        obligation_keys=["L1-PROD"],
    )
    base = allocated_state(
        [_product()],
        events=[*_chk_029_events(), last_day_return],
        inception=TRANSFER,
        statuses=((TRANSFER, "ACTIVE"),),
    )
    path = ReturnPath(
        f"{C_RET}/RET-JAN",
        (_pin(1, TRANSFER, 3),),
        ((TRANSFER, Fraction(100)),),
        Fraction(100),
        REDUCE_PRESET,
    )
    st = dataclasses.replace(base, return_paths={O_RET: path})
    ob, contract = st.obligations[0], st.contracts[0]
    state = returns.return_state(CTX, st, contract, ob, ob.segments[0], WINDOW_END)
    assert (state.Y, state.E, state.expired) == (3, 0, True)
    assert [quantity for _, quantity in state.returns_before_E] == [2, 1]

    position = progress_events.Position(last_day_return.order_key, inclusive=False)
    pending = returns.expected_units(
        CTX, st, ob, WINDOW_END, kept=Fraction(98), position=position, transferred=Fraction(100)
    )
    assert (pending.value, pending.params["expiry_pending"]) == (1, "true")
    closed = returns.expected_units(CTX, st, ob, WINDOW_END, kept=Fraction(97))
    assert (closed.value, "expiry_pending" in closed.params) == (0, False)
    for expected in (pending, closed):
        assert FORMULAS[returns.EXPECTED_FORMULA]((expected.base,), expected.params) == (
            expected.value
        )


def test_l8_d_unit_rate_from_the_fixed_segment_in_force() -> None:
    """D-88 L7-5-Q-1 on the RET-BR-03 arms world: r = x_exact ÷ Q of the latest ``FIXED`` segment
    in force at d, the selection and divisor of stage 13 ``_rates`` (S04-R-08a/b; S09-R-23 [J]).
    1,000 arms for 200,000.00 transfer on 1 March; the 15 May price-protection version (TP_CHANGE,
    x_exact 188,000.00) gives r 188, so the target is 188,000.00 = X and the invariant clears.
    ``ReturnPath.r`` stays the inception publication and is the fallback only when no ``FIXED``
    segment is in force or Q = 0."""
    arms, shipped, protected = "BR-03-ARMS", date(2026, 3, 1), date(2026, 5, 15)
    subject = f"{arms}/L1-ARMS"
    ctx = book_context(entity(start=shipped, months=4))

    def ev(version: int, event_type: str, when: date, payload: dict[str, object]) -> EventView:
        return event_view(arms, version, event_type, when, payload, obligation_keys=["L1-ARMS"])

    delivery = ev(
        4,
        "DELIVERY_RECORDED",
        shipped,
        {"obligation_key": "L1-ARMS", "quantity": Decimal("1000"), "trigger": "DELIVERY"},
    )
    invoice = ev(
        5,
        "BILLING_RECORDED",
        shipped,
        {
            "invoice_number": "INV-BR03-A01",
            "line_external_id": "INV-BR03-A01-1",
            "obligation_key": "L1-ARMS",
            "amount": Decimal("200000.00"),
            "issue_date": shipped,
        },
    )
    tp_change = ev(11, "ESTIMATE_CHANGED", protected, {"estimate_version_id": f"{arms}/PP@v2"})
    inception = segment(
        Fraction(200000),
        usd("200000.00"),
        start=shipped,
        end=shipped,
        quantity=Fraction(1000),
        measure="POINT_IN_TIME",
    )
    revised = segment(
        Fraction(188000),
        usd("188000.00"),
        start=shipped,
        end=shipped,
        effective=protected,
        cause=SegmentCause.TP_CHANGE,
        event_key=tp_change.event_key,
        quantity=Fraction(1000),
        measure="POINT_IN_TIME",
    )
    ob = obligation(
        "L1-ARMS",
        [inception, revised],
        contract_key=arms,
        method="POINT_IN_TIME",
        convention=None,
        quantity=Fraction(1000),
    )
    pins = EstimatePins(
        {
            f"{arms}/PP": (
                EstimatePin(
                    estimate_version(f"{arms}/PP", "VARIABLE_CONSIDERATION", 2, protected),
                    tp_change.order_key,
                ),
            )
        }
    )
    base = allocated_state(
        [ob],
        events=[delivery, invoice, tp_change],
        inception=shipped,
        statuses=((shipped, "ACTIVE"),),
        estimates=pins,
    )
    path = ReturnPath(f"{arms}/RET", (), ((shipped, Fraction(200)),), Fraction(200), REDUCE_PRESET)
    st = dataclasses.replace(base, return_paths={subject: path})
    ob = st.obligations[0]

    assert returns.unit_rate(path, ob, date(2026, 3, 31)) == 200
    assert returns.unit_rate(path, ob, date(2026, 5, 31)) == 188
    assert path.r == ((shipped, Fraction(200)),)  # the inception publication is unchanged
    # Fallbacks: Q = 0, and a date with no FIXED segment in force, read path.r.
    assert returns.unit_rate(path, dataclasses.replace(ob, quantity=Fraction(0)), protected) == 200
    early = dataclasses.replace(path, r=((date(2026, 2, 1), Fraction(150)),))
    assert returns.unit_rate(early, ob, date(2026, 2, 15)) == 150

    assert components.target_at(ctx, st, ob, date(2026, 3, 31)).value == usd("200000.00")
    assert components.target_at(ctx, st, ob, date(2026, 5, 31)).value == usd("188000.00")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    targets = targets_by_period(state, subject)
    assert [targets[f"FY2026-P0{month}"] for month in (3, 5, 6)] == [
        usd("200000.00"),
        usd("188000.00"),
        usd("188000.00"),
    ]
    exact = _node(trace, f"revenue_target_exact:{subject}#FIXED:FY2026-P05")
    assert exact.params["unit_rate"] == "188"


def test_l8_d_billed_counts_the_share_of_an_unreferenced_invoice() -> None:
    """D-88 L7-5-Q-3 on the FX-CHK-084-A world: the invoice line names no obligation, so E_b counts
    L1-GADGET's S10-R-01 share of the document (the whole 10,000.00 over one obligation); before
    the rule E_b was 0 and no refund liability arose. 100 gadgets for 10,000.00 on 1 March, E 3,
    two returned on 15 April, window end 31 May (p_ref 100.00)."""
    contract, shipped, returned, window_end = (
        "C-FX-084-A",
        date(2026, 3, 1),
        date(2026, 4, 15),
        date(2026, 5, 31),
    )
    subject = f"{contract}/L1-GADGET"

    def ev(
        version: int,
        event_type: str,
        when: date,
        payload: dict[str, object],
        keys: Sequence[str] = ("L1-GADGET",),
    ) -> EventView:
        return event_view(contract, version, event_type, when, payload, obligation_keys=keys)

    invoice = {
        "invoice_number": "INV-084A-1",
        "line_external_id": "INV-084A-1-1",
        "amount": Decimal("10000.00"),
        "issue_date": shipped,
    }
    events = [
        ev(3, "BILLING_RECORDED", shipped, invoice, keys=()),
        ev(5, "ESTIMATE_CHANGED", shipped, {"estimate_version_id": f"{contract}/RET-084@v1"}),
        ev(
            6,
            "DELIVERY_RECORDED",
            shipped,
            {"obligation_key": "L1-GADGET", "quantity": Decimal("100"), "trigger": "DELIVERY"},
        ),
        ev(
            7,
            "RETURN_RECORDED",
            returned,
            {
                "obligation_key": "L1-GADGET",
                "quantity": Decimal("2"),
                "refund_amount": Decimal("200"),
            },
        ),
    ]
    goods = segment(
        Fraction(10000), usd("10000.00"), start=shipped, end=shipped, quantity=Fraction(100)
    )
    gadget = obligation(
        "L1-GADGET",
        [goods],
        contract_key=contract,
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(100),
    )
    base = allocated_state(
        [gadget], events=events, inception=shipped, statuses=((shipped, "ACTIVE"),)
    )
    pin = ReturnPin(
        shipped, f"{contract}/RET-084@v1", Fraction(3), Fraction(60), Fraction(60), window_end
    )
    path = ReturnPath(
        f"{contract}/RET-084", (pin,), ((shipped, Fraction(100)),), Fraction(100), REDUCE_PRESET
    )
    st = dataclasses.replace(base, return_paths={subject: path})
    state, _ = _run(book_context(entity(start=date(2026, 1, 1), months=6)), st)
    march, april, may = (state.return_states[(subject, f"FY2026-P0{m}")] for m in (3, 4, 5))
    assert (march.N, march.Y, march.E, march.E_b) == (100, 0, 3, 3)
    assert round_half_up(march.p_ref * march.E_b, 2) == usd("300.00")
    assert (april.Y, april.E, april.E_b) == (2, 1, 1)
    assert round_half_up(april.p_ref * april.E_b, 2) == usd("100.00")
    assert (may.E, may.E_b, may.expired) == (0, 0, True)
    targets = targets_by_period(state, subject)
    assert [targets[f"FY2026-P0{month}"] for month in (3, 5)] == [usd("9700.00"), usd("9800.00")]


# --- D-91 C606-01: refund billing identity and the E_b basis (World W1) ---------------------------
#
# Expected figures derived independently in .run/l9/d91-c606-01/derive.py from ALG-06 §2.7.2 steps
# 1 to 4 as amended (POLICIES rev 1.7), ENGINE_SPEC_B S09-R-23a, S10-R-06 and S10-R-07: 100 units at
# 100.00 transferred 10 Jan 2026, RETURN_RATE E 20 (rate 0.20, k 60.00, window 15 Mar), INV-1 /
# INV-1-1 1,000.00 cancellable 10 Jan. U_b = counted amount ÷ 100; E_b = max(0, min(E, U_b − Y));
# RL = round(100 × E_b); revenue = round(100 × (100 − Y − E)) = 8,000.00; position = billed −
# revenue − RL. On main (cdd84a4) a same-amount noncancellable repeat of a direct line doubled U_b
# (E_b 20,
# RL 2,000.00, position −9,000.00) and an ENGINE-mode memo-only line grossed up a liability.

C606 = "C-606-01"
W1_SHIPPED, W1_UPDATED, W1_PAID = date(2026, 1, 10), date(2026, 1, 20), date(2026, 1, 25)
W1_JAN, W1_FEB, W1_MAR = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)
W1_RETURNED = date(2026, 2, 10)
W1_INVOICE: Mapping[str, object] = {
    "invoice_number": "INV-1",
    "line_external_id": "INV-1-1",
    "amount": Decimal("1000.00"),
    "issue_date": W1_SHIPPED,
    "is_cancellable": True,
}
W1_GROUP_AT_ENTITY = f"CG-1@{ENTITY_CODE}"


def _w1_obligation(key: str) -> ObligationState:
    goods = segment(
        Fraction(10000), usd("10000.00"), start=W1_SHIPPED, end=W1_SHIPPED, quantity=Fraction(100)
    )
    return obligation(
        key,
        [goods],
        contract_key=C606,
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(100),
    )


def _w1_path(key: str) -> ReturnPath:
    pin = ReturnPin(
        W1_SHIPPED, f"{C606}/RET-{key}@v1", Fraction(20), Fraction(60), Fraction(0), WINDOW_END
    )
    return ReturnPath(
        f"{C606}/RET-{key}", (pin,), ((W1_SHIPPED, Fraction(100)),), Fraction(100), REDUCE_PRESET
    )


def _w1_billing(
    version: int,
    when: date = W1_SHIPPED,
    *,
    key: str | None = "L1",
    cancellable: object = True,
    absent: bool = False,
    amount: str = "1000.00",
    line: str = "INV-1-1",
    number: str = "INV-1",
) -> EventView:
    payload: dict[str, object] = {
        **W1_INVOICE,
        "invoice_number": number,
        "line_external_id": line,
        "amount": Decimal(amount),
    }
    if absent:
        del payload["is_cancellable"]
    else:
        payload["is_cancellable"] = cancellable
    if key is None:
        payload.pop("obligation_key", None)
    else:
        payload["obligation_key"] = key
    return event_view(
        C606, version, "BILLING_RECORDED", when, payload, obligation_keys=[key] if key else []
    )


def _w1_update(version: int = 21, when: date = W1_UPDATED, **changes: object) -> EventView:
    """A same-identity, same-amount noncancellable repeat naming L1 (the S10-R-07 status update)."""
    return _w1_billing(version, when, cancellable=False, **changes)  # type: ignore[arg-type]


def _w1_payment(
    version: int, when: date, amount: str = "1000.00", applied: Sequence[str] = ("INV-1",)
) -> EventView:
    payload: dict[str, object] = {
        "receipt_reference": f"RCPT-{version}",
        "amount": Decimal(amount),
        "receipt_date": when,
        "applied_invoice_numbers": list(applied),
    }
    return event_view(C606, version, "PAYMENT_RECEIVED", when, payload)


def _w1_return_and_memo(key: str = "L1") -> list[EventView]:
    """RETURN_RECORDED 2 units on 10 Feb with its 200.00 credit memo (RET-CHK-029 shape)."""
    returned = event_view(
        C606,
        30,
        "RETURN_RECORDED",
        W1_RETURNED,
        {"obligation_key": key, "quantity": Decimal("2"), "refund_amount": Decimal("200")},
        obligation_keys=[key],
    )
    memo = event_view(
        C606,
        31,
        "CREDIT_MEMO_RECORDED",
        W1_RETURNED,
        {
            "credit_memo_number": "CM-1",
            "credited_invoice_number": "INV-1",
            "obligation_key": key,
            "amount": Decimal("200.00"),
            "issue_date": W1_RETURNED,
        },
        obligation_keys=[key],
    )
    return [returned, memo]


def _w1_state(events: Sequence[EventView], keys: Sequence[str] = ("L1",)) -> AllocatedState:
    deliveries = [
        event_view(
            C606,
            10 + index,
            "DELIVERY_RECORDED",
            W1_SHIPPED,
            {"obligation_key": key, "quantity": Decimal("100"), "trigger": "DELIVERY"},
            obligation_keys=[key],
        )
        for index, key in enumerate(keys)
    ]
    st = allocated_state(
        [_w1_obligation(key) for key in keys],
        events=[*deliveries, *events],
        inception=W1_SHIPPED,
        statuses=((W1_SHIPPED, "ACTIVE"),),
    )
    return dataclasses.replace(st, return_paths={f"{C606}/{key}": _w1_path(key) for key in keys})


def _w1_ctx(mode: str = "ERP") -> BookContext:
    """POL-004 ``mode`` in every period; POL-123 follows when the preset carries it (pin P)."""
    ctx = book_context(entity(start=date(2026, 1, 1), months=3))
    basis = "UNCONDITIONAL_INVOICES_ONLY" if mode == "ENGINE" else "ERP_POSTED_INVOICES"
    rows = []
    for policy in ctx.policies.all():
        if policy.code == "billing.posting":
            policy = dataclasses.replace(policy, value=mode)
        elif policy.code == "balance.position_invoice_basis":
            policy = dataclasses.replace(policy, value=basis)
        rows.append(policy)
    return dataclasses.replace(ctx, policies=PolicyResolver(tuple(rows)))


def _w1_return_state(
    ctx: BookContext, st: AllocatedState, key: str, d: date
) -> returns.ReturnState:
    ob = next(o for o in st.obligations if o.obligation_key == key)
    return returns.return_state(ctx, st, st.contracts[0], ob, None, d)


def _e_b(ctx: BookContext, st: AllocatedState, key: str = "L1", d: date = W1_JAN) -> Fraction:
    return _w1_return_state(ctx, st, key, d).E_b


def _w1_stages(ctx: BookContext, st: AllocatedState) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one book; every node re-evaluates (DG-ENG-04; PROP:P14)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = run(ctx, st, tb)
    state = s10_billing_balances.run(ctx, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _w1_target(targets: Sequence[Target], measure: str, subject_key: str, period_key: str) -> int:
    return next(
        t.value
        for t in targets
        if (t.measure, t.subject_key, t.period_key) == (measure, subject_key, period_key)
    )


def _rl(state: BalanceState, key: str = "L1", period_key: str = "FY2026-P01") -> int:
    component = f"{W1_GROUP_AT_ENTITY}/RETURN/{C606}/{key}"
    return _w1_target(state.refund_liabilities, "refund_liability", component, period_key)


def _position(state: BalanceState, period_key: str = "FY2026-P01") -> int:
    return _w1_target(state.positions, "net_position", W1_GROUP_AT_ENTITY, period_key)


def _billed_cum(state: BalanceState, key: str = "L1", period_key: str = "FY2026-P01") -> int:
    return _w1_target(state.billing, "billed_cum", f"{C606}/{key}", period_key)


def _revenue(state: BalanceState, key: str = "L1", period_key: str = "FY2026-P01") -> int:
    return _w1_target(state.recognition.revenue_targets, "revenue_cum", f"{C606}/{key}", period_key)


@pytest.mark.parametrize("direct", [True, False], ids=["direct", "unreferenced"])
def test_d91_status_update_adds_no_billing_to_e_b(direct: bool) -> None:
    """S10-R-07 before either attribution branch (D-91 C606-01 (1)): U_b 10 of E 20, so E_b =
    min(20, 10 − 0) = 10 with or without the 20 Jan same-amount noncancellable update; RL 1,000.00.
    On main the direct line was accumulated before the ``seen`` check (E_b 20, RL 2,000.00); the
    unreferenced branch already deduplicated (guard)."""
    key = "L1" if direct else None
    line = _w1_billing(20, key=key)
    update = _w1_update(key=key)
    ctx = _w1_ctx()
    for events in ([line], [line, update]):
        st = _w1_state(events)
        state = _w1_return_state(ctx, st, "L1", W1_JAN)
        assert (state.units_billed, state.E, state.E_b) == (10, 20, 10)
        balances, _ = _w1_stages(ctx, st)
        assert (_rl(balances), _revenue(balances), _billed_cum(balances)) == (
            usd("1000.00"),
            usd("8000.00"),
            usd("1000.00"),
        )
        assert _position(balances) == usd("-8000.00")


@pytest.mark.parametrize("mode", ["ERP", "ENGINE"])
@pytest.mark.parametrize("flag", ["false", "absent"])
def test_d91_erp_resend_noncancellable_repeat_counts_once(flag: str, mode: str) -> None:
    """The ERP re-send shape (L2-4-Q-8): a noncancellable original (``is_cancellable`` false or
    absent) and an identical repeat is one line in both modes: E_b 10 (main: 20 in all four)."""
    kwargs: dict[str, object] = {"absent": True} if flag == "absent" else {"cancellable": False}
    line = _w1_billing(20, **kwargs)  # type: ignore[arg-type]
    resend = _w1_billing(21, W1_UPDATED, **kwargs)  # type: ignore[arg-type]
    ctx = _w1_ctx(mode)
    state = _w1_return_state(ctx, _w1_state([line, resend]), "L1", W1_JAN)
    assert (state.units_billed, state.E_b, state.status_updates_skipped) == (10, 10, 1)
    balances, _ = _w1_stages(ctx, _w1_state([line, resend]))
    assert (_rl(balances), _billed_cum(balances)) == (usd("1000.00"), usd("1000.00"))


@pytest.mark.parametrize("case", ["a_to_b", "x11", "null_to_key"])
def test_d91_status_update_never_reattributes(case: str) -> None:
    """D-91 C606-01 (3): a status update never changes the first line's attribution. ``a_to_b``: the
    update naming L2 is a status update of L1's line, stage 10 keeps one 1,000.00 line on L1 and
    raises ``INVOICE_STATUS_UPDATE_MISMATCH`` (member ``obligation_key``); E_b (L1, L2) = (10, 0),
    never (10, 10). ``x11``: a direct line then an unreferenced same-amount update: accepted, (10,
    0), never (15, 5). ``null_to_key``: a two-obligation unreferenced control (equal posted weights)
    apportions INV-1 500.00/500.00, U_b/E_b (5, 5) at p_ref 100.00, and a later update naming L1
    changes nothing: no finding, 500.00/500.00, (5, 5)."""
    ctx = _w1_ctx()
    keys = ("L1", "L2")
    if case == "a_to_b":
        events = [_w1_billing(20, key="L1"), _w1_update(key="L2")]
        expected, lines_on, finding_members = (10, 0), {"L1": usd("1000.00")}, ["obligation_key"]
    elif case == "x11":
        events = [_w1_billing(20, key="L1"), _w1_update(key=None)]
        expected, lines_on, finding_members = (10, 0), {"L1": usd("1000.00")}, []
    else:
        control = _w1_state([_w1_billing(20, key=None)], keys)
        before = [_w1_return_state(ctx, control, key, W1_JAN) for key in keys]
        assert [(s.units_billed, s.E_b) for s in before] == [(5, 5), (5, 5)]
        assert [s.billed_lines[0].contribution for s in before] == [500, 500]
        events = [_w1_billing(20, key=None), _w1_update(key="L1")]
        expected, lines_on, finding_members = (5, 5), {None: usd("1000.00")}, []
    st = _w1_state(events, keys)
    classified = classification.classify(ctx, st)
    assert {
        line.obligation_key: line.amount for doc in classified.documents for line in doc.lines
    } == lines_on
    assert [(f.code, f.detail.get("member")) for f in classified.findings] == [
        ("INVOICE_STATUS_UPDATE_MISMATCH", member) for member in finding_members
    ]
    states = [_w1_return_state(ctx, st, key, W1_JAN) for key in keys]
    assert tuple(s.E_b for s in states) == expected
    if case == "null_to_key":
        assert [s.billed_lines[0].contribution for s in states] == [500, 500]  # the split stands


@pytest.mark.parametrize("case", ["direct", "unreferenced", "noncancellable_then_cancellable"])
def test_d91_repeated_cancellable_identity_is_a_new_line(case: str) -> None:
    """D-91 C606-01 (2): a repeat flagged cancellable is another line in both stages: two 1,000.00
    lines, U_b 20, E_b 20, RL 2,000.00 (ERP). Main misapplied the status-update rule to unreferenced
    repeats (10); direct repeats already counted (guard)."""
    key = None if case == "unreferenced" else "L1"
    first_cancellable = case != "noncancellable_then_cancellable"
    line = _w1_billing(20, key=key, cancellable=first_cancellable)
    repeat = _w1_billing(21, W1_UPDATED, key=key, cancellable=True)
    ctx = _w1_ctx()
    st = _w1_state([line, repeat])
    classified = classification.classify(ctx, st)
    assert [line.amount for doc in classified.documents for line in doc.lines] == [
        usd("1000.00")
    ] * 2
    state = _w1_return_state(ctx, st, "L1", W1_JAN)
    assert (state.units_billed, state.E_b, len(state.billed_lines)) == (20, 20, 2)
    balances, _ = _w1_stages(ctx, st)
    assert (_rl(balances), _billed_cum(balances), _position(balances)) == (
        usd("2000.00"),
        usd("2000.00"),
        usd("-8000.00"),
    )


def test_d91_engine_memo_only_line_is_outside_e_b() -> None:
    """D-91 C606-01 (5) under POL-004 ``ENGINE``: a cancellable line counts from its S10-R-06
    unconditional date. (i) unpaid, no update: E_b 0 at 31 Jan (main 10); (ii) + update 20 Jan: 10;
    (iii) + PAYMENT_RECEIVED 1,000.00 applied 25 Jan: 0 at 20 Jan (main 10), 10 at 31 Jan; (iv)
    payment 5 Jan before the line: 0 at 9 Jan, 10 at 31 Jan (line-date floor); (v) a partial 400.00
    receipt applied 25 Jan dates the whole line: 10; (vi) + a 1,100.00 noncancellable repeat: the
    line stays memo-only at the helper level (E_b 0; main 10) and stage 10 raises the mismatch;
    (vii) ERP control 10."""
    engine, erp = _w1_ctx("ENGINE"), _w1_ctx()
    line = _w1_billing(20)
    memo_only = _w1_state([line])
    state = _w1_return_state(engine, memo_only, "L1", W1_JAN)
    assert (state.units_billed, state.E_b, state.memo_only_lines, state.billing_mode) == (
        0,
        0,
        1,
        "ENGINE",
    )
    balances, trace = _w1_stages(engine, memo_only)
    assert (_rl(balances), _billed_cum(balances), _position(balances)) == (0, 0, usd("-8000.00"))
    units = _node(trace, f"return_units_billed:{C606}/L1:FY2026-P01")
    assert (units.value, units.inputs, units.params["memo_only_lines"]) == ("0", (), "1")
    # (ii) the same-amount noncancellable update is the unconditional date (D-89 L7-6-Q-9).
    updated = _w1_state([line, _w1_update()])
    assert _e_b(engine, updated) == 10
    assert _e_b(engine, updated, d=date(2026, 1, 19)) == 0
    balances, _ = _w1_stages(engine, updated)
    assert (_rl(balances), _billed_cum(balances), _position(balances)) == (
        usd("1000.00"),
        usd("1000.00"),
        usd("-8000.00"),
    )
    # (iii) a payment applied to the invoice dates the line from the receipt.
    paid = _w1_state([line, _w1_payment(22, W1_PAID)])
    assert (_e_b(engine, paid, d=W1_UPDATED), _e_b(engine, paid)) == (0, 10)
    cited = _w1_return_state(engine, paid, "L1", W1_JAN).billed_lines[0]
    assert cited.detail["unconditional_source"] == f"{C606}/EV-000022"
    # (iv) a receipt before the line: the line date is the floor (L2-4-Q-11).
    early = _w1_state([_w1_payment(9, date(2026, 1, 5)), line])
    assert (_e_b(engine, early, d=date(2026, 1, 9)), _e_b(engine, early)) == (0, 10)
    assert (
        "unconditional_source"
        not in _w1_return_state(engine, early, "L1", W1_JAN).billed_lines[0].detail
    )
    # (v) a partial receipt dates the whole line (inherited S10-R-06 semantics).
    partial = _w1_state([line, _w1_payment(22, W1_PAID, "400.00")])
    assert _e_b(engine, partial) == 10
    # (vi) a changed-amount repeat is no unconditional source; stage 10 owns the finding.
    mismatched = _w1_state([line, _w1_update(amount="1100.00")])
    assert _e_b(engine, mismatched) == 0
    assert [f.code for f in classification.classify(engine, mismatched).findings] == [
        "INVOICE_STATUS_UPDATE_MISMATCH"
    ]
    # (vii) ERP counts the line on its effective date whatever the flag.
    assert _e_b(erp, memo_only) == 10


def test_d91_february_return_keeps_the_cumulative_refund_liability() -> None:
    """D-91 C606-01 (6): credit memos never enter U_b; returned units leave through Y. RETURN 2
    units on 10 Feb with a 200.00 credit memo: E 18, U_b 10, E_b = min(18, 10 − 2) = 8, RL 800.00 at
    28 Feb, P02 movement −200.00, position 800 − 8,000 − 800 = −8,000.00, with the status update in
    the stream (main: E_b 18, RL 1,800.00). A credit-memo-reduced base (U_b 8, E_b 6, 600.00) is
    refused."""
    ctx = _w1_ctx()
    st = _w1_state([_w1_billing(20), _w1_update(), *_w1_return_and_memo()])
    february = _w1_return_state(ctx, st, "L1", W1_FEB)
    assert (february.E, february.Y, february.units_billed, february.E_b) == (18, 2, 10, 8)
    assert february.E_b != 6
    balances, _ = _w1_stages(ctx, st)
    assert (_rl(balances), _rl(balances, period_key="FY2026-P02")) == (
        usd("1000.00"),
        usd("800.00"),
    )
    assert _rl(balances, period_key="FY2026-P02") - _rl(balances) == usd("-200.00")
    assert (
        _billed_cum(balances, period_key="FY2026-P02"),
        _revenue(balances, period_key="FY2026-P02"),
    ) == (
        usd("800.00"),
        usd("8000.00"),
    )
    assert _position(balances, "FY2026-P02") == usd("-8000.00")


def test_d91_non_integer_units_and_multiline_invoice() -> None:
    """(a) one 1,050.50 line with its update: U_b 2101/200 (a Fraction, never rounded), RL 1,050.50
    (main 2,000.00: 21.01 units billed capped at E 20); (b) INV-1 lines 600.00 and 400.00, each
    updated: U_b 10, RL 1,000.00 (main: the update on the 600 line double-counted, E_b 16,
    1,600.00)."""
    ctx = _w1_ctx()
    single = _w1_state([_w1_billing(20, amount="1050.50"), _w1_update(amount="1050.50")])
    state = _w1_return_state(ctx, single, "L1", W1_JAN)
    assert (state.units_billed, state.E_b) == (Fraction(2101, 200), Fraction(2101, 200))
    balances, trace = _w1_stages(ctx, single)
    assert _rl(balances) == usd("1050.50")
    assert _node(trace, f"return_units_billed:{C606}/L1:FY2026-P01").value == "10.505"
    lines = [
        _w1_billing(20, amount="600.00", line="INV-1-1"),
        _w1_billing(21, amount="400.00", line="INV-1-2"),
        _w1_update(22, amount="600.00", line="INV-1-1"),
        _w1_update(23, amount="400.00", line="INV-1-2"),
    ]
    multi = _w1_state(lines)
    state = _w1_return_state(ctx, multi, "L1", W1_JAN)
    assert (state.units_billed, state.E_b, state.status_updates_skipped) == (10, 10, 2)
    balances, _ = _w1_stages(ctx, multi)
    assert _rl(balances) == usd("1000.00")


def _with_source_value(trace: Trace, node_id: str, value: str, *, index: int = 0) -> Trace:
    """A trace copy whose ``node_id``'s ``index``-th SourceRef cites ``value`` instead."""
    nodes = []
    for node in trace.nodes:
        if node.id == node_id:
            inputs = list(node.inputs)
            ref = inputs[index]
            assert isinstance(ref, SourceRef)
            inputs[index] = SourceRef(ref.ref_type, ref.ref_id, {**ref.detail, "value": value})
            node = dataclasses.replace(node, inputs=tuple(inputs))
        nodes.append(node)
    return dataclasses.replace(trace, nodes=tuple(nodes))


def test_d91_units_billed_and_e_b_trace_nodes_reevaluate() -> None:
    """D-91 C606-01 (7): ``return_units_billed`` (value 10; one SourceRef to the kept line, none to
    the update) and ``return_refundable_units`` (value 10; inputs the expected-units and units-
    billed nodes) exist and ``reevaluate`` reproduces every node; a copy citing 2,000.00 for the
    direct line re-evaluates U_b 20 and E_b 20; an unreferenced-document copy with the cited total
    1,000.00 → 2,000.00 re-evaluates the S10-R-01 share (L1 of two equal obligations: 500.00 →
    1,000.00)."""
    ctx = _w1_ctx()
    line, update = _w1_billing(20), _w1_update()
    _, trace = _w1_stages(ctx, _w1_state([line, update]))
    units_id = f"return_units_billed:{C606}/L1:FY2026-P01"
    e_b_id = f"return_refundable_units:{C606}/L1:FY2026-P01"
    units = _node(trace, units_id)
    assert (units.formula_id, units.value) == ("returns.units_billed.v1", "10")
    assert [ref.ref_id for ref in units.inputs if isinstance(ref, SourceRef)] == [line.event_key]
    assert (
        units.params["p_ref"],
        units.params["mode"],
        units.params["status_updates_skipped"],
    ) == (
        "100",
        "ERP",
        "1",
    )
    e_b = _node(trace, e_b_id)
    assert (e_b.formula_id, e_b.value, e_b.params["returned_units"]) == (
        "returns.refundable_units.v1",
        "10",
        "0",
    )
    assert e_b.inputs == (f"return_expected_units:{C606}/L1:FY2026-P01", units_id)
    liability = _node(trace, f"refund_liability:{W1_GROUP_AT_ENTITY}/RETURN/{C606}/L1:FY2026-P01")
    assert (liability.formula_id, liability.inputs, liability.value) == (
        "rl.return.v2",
        (e_b_id,),
        "1000.00",
    )
    doubled = reevaluate(_with_source_value(trace, units_id, "2000"))
    assert (doubled[units_id], doubled[e_b_id], doubled[liability.id]) == ("20", "20", "2000.00")
    # An unreferenced document over two equal obligations: the cited total is apportioned again.
    _, shared = _w1_stages(
        ctx, _w1_state([_w1_billing(20, key=None), _w1_update(key=None)], ("L1", "L2"))
    )
    node = _node(shared, units_id)
    assert (node.value, node.params["apportioned"], node.params["key"]) == ("5", "0", f"{C606}/L1")
    assert node.params["keys_0"] == f"{C606}/L1|{C606}/L2"
    assert node.params["weights_0"] == "1000000|1000000"  # a_posted, minor units
    doubled = reevaluate(_with_source_value(shared, units_id, "2000"))
    assert (doubled[units_id], doubled[e_b_id]) == ("10", "10")


def _worlds() -> list[tuple[str, BookContext, AllocatedState, tuple[str, ...]]]:
    line, update = _w1_billing(20), _w1_update()
    unreferenced = _w1_billing(20, key=None)
    found = []
    for mode in ("ERP", "ENGINE"):
        ctx = _w1_ctx(mode)
        found.extend(
            [
                (f"{mode}: line", ctx, _w1_state([line]), ("L1",)),
                (f"{mode}: line + update", ctx, _w1_state([line, update]), ("L1",)),
                (
                    f"{mode}: unreferenced + update",
                    ctx,
                    _w1_state([unreferenced, _w1_update(key=None)]),
                    ("L1",),
                ),
                (f"{mode}: paid 25 Jan", ctx, _w1_state([line, _w1_payment(22, W1_PAID)]), ("L1",)),
                (
                    f"{mode}: repeated cancellable",
                    ctx,
                    _w1_state([line, _w1_billing(21, W1_UPDATED)]),
                    ("L1",),
                ),
                (
                    f"{mode}: February return",
                    ctx,
                    _w1_state([line, update, *_w1_return_and_memo()]),
                    ("L1",),
                ),
                (
                    f"{mode}: two obligations, unreferenced control",
                    ctx,
                    _w1_state([unreferenced, _w1_update(key="L1")], ("L1", "L2")),
                    ("L1", "L2"),
                ),
                (
                    f"{mode}: two lines 600 + 400",
                    ctx,
                    _w1_state(
                        [
                            _w1_billing(20, amount="600.00"),
                            _w1_billing(21, amount="400.00", line="INV-1-2"),
                            _w1_update(22, amount="600.00"),
                            _w1_update(23, amount="400.00", line="INV-1-2"),
                        ]
                    ),
                    ("L1",),
                ),
            ]
        )
    return found


def test_d91_stage09_units_billed_matches_stage10_attributed_invoices() -> None:
    """Stage 09 units billed × p_ref equals stage 10's attribution of the eligible INVOICE lines
    (kind INVOICE only, excluding CREDIT_MEMO; unconditional date ≤ d) in every world above, ERP and
    ENGINE, at every period end, computed by stage 09 from its own state without importing stage 10
    helpers. Separately, stage 10's net ``billed_cum`` is 800.00 in February (gross 1,000 ÷ 100 →
    U_b 10, E_b 8, RL 800.00; the net 800 ÷ 100 → 8 → E_b 6 → 600.00 outcome is the rejected
    one)."""
    source = inspect.getsource(returns)
    assert "s10_billing_balances" not in source and "classification" not in source
    ends = {"FY2026-P01": W1_JAN, "FY2026-P02": W1_FEB, "FY2026-P03": W1_MAR}
    for label, ctx, st, keys in _worlds():
        balances, _ = _w1_stages(ctx, st)
        for key in keys:
            subject = f"{C606}/{key}"
            for period_key, end in ends.items():
                state = balances.recognition.return_states[(subject, period_key)]
                eligible = 0
                for document in balances.documents:
                    if document.kind != classification.INVOICE:
                        continue
                    dated = [line.unconditional_date for line in document.lines]
                    if all(d is not None and d <= end for d in dated):
                        eligible += document.attribution.get(subject, 0)
                    else:
                        assert all(d is None or d > end for d in dated), (label, period_key)
                assert round_half_up(state.units_billed * state.p_ref, 2) == eligible, (
                    label,
                    key,
                    period_key,
                )
    ctx = _w1_ctx()
    february, _ = _w1_stages(
        ctx, _w1_state([_w1_billing(20), _w1_update(), *_w1_return_and_memo()])
    )
    assert _billed_cum(february, period_key="FY2026-P02") == usd("800.00")
    state = february.recognition.return_states[(f"{C606}/L1", "FY2026-P02")]
    assert (state.units_billed, state.E_b, _rl(february, period_key="FY2026-P02")) == (
        10,
        8,
        usd("800.00"),
    )
