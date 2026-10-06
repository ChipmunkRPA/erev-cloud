"""Stage 09 point-in-time, output and units measures (ENC-3, ENC-4).

ENGINE_SPEC_B §9.2.4 S09-R-10 to S09-R-13, §9.4, §9.5; ENGINE_SPEC Table 0.4-A and EX-06-C;
POLICIES POL-094, POL-095, POL-233 and ALG-01 §2.1.4 CHK-007. The ``AllocatedState`` is built
against the documented contract (support.recognition; D-81 integration after merge).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import JudgementInput
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up
from erev_engine.stages.s09_recognition import RecognitionState, components, run
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    ReturnPath,
    ReturnPin,
    SegmentCause,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import entity
from support.recognition import (
    BILL_AND_HOLD_MEMBERS,
    CONTRACT_KEY,
    allocated_state,
    bill_and_hold_judgement,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    period_amounts,
    segment,
    targets_by_period,
    usd,
)

O1 = f"{CONTRACT_KEY}/POB-01"
O2 = f"{CONTRACT_KEY}/POB-02"


def _run(ctx: BookContext, st: AllocatedState) -> tuple[RecognitionState, Trace]:
    """Run stage 09 and check that the trace reproduces every node (DG-ENG-04)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)  # the stage 06 and stage 08 nodes stage 09 cites
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert state.allocated is st
    return state, trace


def _node(trace: Trace, measure: str, subject_key: str, period_key: str) -> TraceNode:
    node_id = f"{measure}:{subject_key}:{period_key}"
    return next(node for node in trace.nodes if node.id == node_id)


def _goods(
    *, quantity: int = 1, scope: str = "IN_SCOPE_606", method: str = "POINT_IN_TIME"
) -> ObligationState:
    """A point-in-time product sold for 5,000.00 (T-REF-23: pattern POINT_IN_TIME)."""
    goods = segment(
        Fraction(5000),
        usd("5000.00"),
        start=date(2026, 1, 1),
        end=date(2026, 1, 1),
        quantity=Fraction(quantity),
    )
    return obligation(
        "POB-01", [goods], method=method, convention=None, quantity=Fraction(quantity), scope=scope
    )


def _delivery(version: int, effective: date, trigger: str, quantity: str = "1") -> EventView:
    payload = {"obligation_key": "POB-01", "quantity": Decimal(quantity), "trigger": trigger}
    return event_view(
        CONTRACT_KEY, version, "DELIVERY_RECORDED", effective, payload, obligation_keys=["POB-01"]
    )


def _return(version: int, effective: date, quantity: str) -> EventView:
    payload = {"obligation_key": "POB-01", "quantity": Decimal(quantity)}
    return event_view(
        CONTRACT_KEY, version, "RETURN_RECORDED", effective, payload, obligation_keys=["POB-01"]
    )


def _option(value: str) -> tuple[tuple[str, str, str, str], ...]:
    """An obligation-level POL-095 option (levels P, O)."""
    return (("recognition.control_trigger", "OBLIGATION", O1, value),)


def _repurchase(outcome: str) -> JudgementInput:
    """A REVIEWED ``REPURCHASE_CLASSIFICATION`` record (ENGINE_SPEC Table 0.4-A)."""
    return JudgementInput(
        judgement_key="JDG-RP-POB-01",
        topic="REPURCHASE_CLASSIFICATION",
        subject_key=O1,
        book_code=None,
        outcome={"obligation_key": "POB-01", "outcome": outcome},
    )


def _values(state: RecognitionState, subject_key: str = O1) -> set[int]:
    return set(targets_by_period(state, subject_key).values())


def test_s09_r11_control_transfer_triggers() -> None:
    ctx = book_context()
    goods = _goods()
    for version, trigger in enumerate(
        ("DELIVERY", "ACCEPTANCE", "SELL_THROUGH", "CONTROL_TRANSFER"), start=2
    ):
        st = allocated_state([goods], events=[_delivery(version, date(2026, 5, 10), trigger)])
        state, trace = _run(ctx, st)
        targets = targets_by_period(state, O1)
        assert (targets["FY2026-P04"], targets["FY2026-P05"]) == (0, usd("5000.00"))
        params = _node(trace, "progress_ratio", O1, "FY2026-P05").params
        assert (params["transferred"], "reason" in params) == ("1", False)
        assert state.findings == ()

    # REQ-REC-013: a consignment shipment is not a transfer; the sell-through report is.
    consignment = book_context(overrides=_option("SELL_THROUGH_ONLY"))
    shipment = _delivery(2, date(2026, 3, 10), "DELIVERY")
    st = allocated_state([goods], events=[shipment])
    state, trace = _run(consignment, st)
    assert _values(state) == {0}
    params = _node(trace, "progress_ratio", O1, "FY2026-P03").params
    assert (params["reason"], params["transferred"]) == ("TRIGGER_NOT_PERMITTED", "0")
    assert state.findings == ()  # S09-R-11: no finding for a non-permitted trigger
    at = components.target_at(consignment, st, st.obligations[0], date(2026, 12, 31))
    assert usd("5000.00") - at.value == usd("5000.00")  # the allocation awaits the trigger
    sold = allocated_state(
        [goods], events=[shipment, _delivery(3, date(2026, 6, 20), "SELL_THROUGH")]
    )
    targets = targets_by_period(_run(consignment, sold)[0], O1)
    assert (targets["FY2026-P05"], targets["FY2026-P06"]) == (0, usd("5000.00"))

    # REQ-REC-014: under a subjective acceptance clause only ACCEPTANCE, or a trial lapse recorded
    # as CONTROL_TRANSFER, transfers control.
    acceptance = book_context(overrides=_option("ACCEPTANCE_ONLY"))
    delivered = _delivery(2, date(2026, 2, 15), "DELIVERY")
    for trigger in ("ACCEPTANCE", "CONTROL_TRANSFER"):
        st = allocated_state([goods], events=[delivered, _delivery(3, date(2026, 4, 2), trigger)])
        targets = targets_by_period(_run(acceptance, st)[0], O1)
        assert (targets["FY2026-P03"], targets["FY2026-P04"]) == (0, usd("5000.00"))
    held = allocated_state(
        [goods],
        events=[_delivery(2, date(2026, 2, 15), "BILL_AND_HOLD")],
        judgements=[bill_and_hold_judgement("POB-01")],
    )
    state, trace = _run(acceptance, held)
    assert _values(state) == {0}
    assert state.findings == ()
    assert _node(trace, "progress_ratio", O1, "FY2026-P02").params["reason"] == (
        "TRIGGER_NOT_PERMITTED"
    )

    # Acceptance that is objectively determinable (606-10-55-86) is recorded as the delivery.
    targets = targets_by_period(_run(ctx, allocated_state([goods], events=[delivered]))[0], O1)
    assert (targets["FY2026-P01"], targets["FY2026-P02"]) == (0, usd("5000.00"))

    with pytest.raises(EngineError) as raised:
        bad = allocated_state([goods], events=[_delivery(2, date(2026, 2, 15), "SHIPPED")])
        run(ctx, bad, TraceBuilder(engine_version=ENGINE_VERSION))
    assert (raised.value.code, raised.value.detail["rule"]) == (
        "ENGINE_INVARIANT_VIOLATED",
        "CV-45",
    )


def test_s09_r12_bill_and_hold() -> None:
    ctx = book_context()
    goods = _goods()
    held = [_delivery(2, date(2026, 3, 15), "BILL_AND_HOLD")]
    met = allocated_state([goods], events=held, judgements=[bill_and_hold_judgement("POB-01")])
    state, _ = _run(ctx, met)
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P02"], targets["FY2026-P03"]) == (0, usd("5000.00"))
    assert state.findings == ()

    for member in BILL_AND_HOLD_MEMBERS:  # each of 606-10-55-83(a) to (d) is necessary
        judgement = bill_and_hold_judgement("POB-01", unmet=[member])
        state, trace = _run(ctx, allocated_state([goods], events=held, judgements=[judgement]))
        assert _values(state) == {0}
        # Evaluated at twelve period ends, the finding is still raised once per event.
        assert [
            (f.code, f.severity, f.subject_key, f.event_key, dict(f.detail)) for f in state.findings
        ] == [
            (
                "BILL_AND_HOLD_CRITERIA_UNMET",
                "WARNING",
                O1,
                f"{CONTRACT_KEY}/EV-000002",
                {"rule": "S09-R-12", "unmet": member},
            )
        ]
        assert _node(trace, "progress_ratio", O1, "FY2026-P12").params["reason"] == (
            "BILL_AND_HOLD_CRITERIA_UNMET"
        )

    # No judgement, or one for another book: one finding per obligation and event.
    twice = [*held, _delivery(3, date(2026, 7, 1), "BILL_AND_HOLD")]
    other_book = bill_and_hold_judgement("POB-01", book_code="IFRS15")
    judgement_sets: Sequence[Sequence[JudgementInput]] = ((), (other_book,))
    for judgements in judgement_sets:
        st = allocated_state([goods], events=twice, judgements=judgements)
        state, _ = _run(ctx, st)
        assert _values(state) == {0}
        assert [(f.event_key, f.detail["unmet"]) for f in state.findings] == [
            (f"{CONTRACT_KEY}/EV-000002", "NO_JUDGEMENT"),
            (f"{CONTRACT_KEY}/EV-000003", "NO_JUDGEMENT"),
        ]

    # The physical delivery that follows transfers control; the held event keeps its finding.
    shipped = allocated_state([goods], events=[*held, _delivery(3, date(2026, 8, 3), "DELIVERY")])
    state, _ = _run(ctx, shipped)
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P07"], targets["FY2026-P08"]) == (0, usd("5000.00"))
    assert [f.event_key for f in state.findings] == [f"{CONTRACT_KEY}/EV-000002"]


def test_s09_r13_repurchase_outcomes() -> None:
    ctx = book_context()
    goods = _goods()
    shipped = _delivery(2, date(2026, 3, 10), "DELIVERY")

    def classified(
        outcome: str, events: Sequence[EventView], ob: ObligationState = goods
    ) -> AllocatedState:
        return allocated_state([ob], events=events, judgements=[_repurchase(outcome)])

    targets = targets_by_period(_run(ctx, classified("SALE", [shipped]))[0], O1)
    assert (targets["FY2026-P02"], targets["FY2026-P03"]) == (0, usd("5000.00"))

    # FINANCING: no delivery transfers control while the option is open; the lapse does.
    state, trace = _run(ctx, classified("FINANCING", [shipped]))
    assert _values(state) == {0}
    params = _node(trace, "progress_ratio", O1, "FY2026-P06").params
    assert (params["reason"], params["repurchase"]) == ("REPURCHASE_OPTION_OPEN", "FINANCING")
    lapse = _delivery(3, date(2026, 9, 30), "CONTROL_TRANSFER")
    targets = targets_by_period(_run(ctx, classified("FINANCING", [shipped, lapse]))[0], O1)
    assert (targets["FY2026-P08"], targets["FY2026-P09"]) == (0, usd("5000.00"))

    # LEASE: stage 03 routes the obligation to Topic 842 (S03-R-12); stage 09 emits nothing.
    for ob in (_goods(scope="LEASE_842"), goods):
        state, trace = _run(ctx, classified("LEASE", [shipped], ob))
        assert targets_by_period(state, O1) == {}
        assert trace.nodes == ()
    st = classified("LEASE", [shipped])
    assert components.target_at(ctx, st, goods, date(2026, 12, 31)).guard == "S09-R-13:LEASE"

    # RIGHT_OF_RETURN: returned units leave the count (§9.2.7; ALG-06 step 2 with E = 0).
    batch = _goods(quantity=10)
    events = [_delivery(2, date(2026, 3, 10), "DELIVERY", "10"), _return(3, date(2026, 4, 15), "2")]
    st = classified("RIGHT_OF_RETURN", events, batch)
    state, trace = _run(ctx, st)
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P03"], targets["FY2026-P04"]) == (usd("5000.00"), usd("4000.00"))
    params = _node(trace, "progress_ratio", O1, "FY2026-P04").params
    assert (params["transferred"], params["returned"], params["repurchase"]) == (
        "10",
        "2",
        "RIGHT_OF_RETURN",
    )
    # With a return path the target is ALG-06 step 2 (ENC-7): C = r × (N − Y − E), where E = 1 at
    # transfer and falls to 0 once 2 units come back (S09-R-23).
    pin = ReturnPin(date(2026, 3, 1), "EST-RR@v1", Fraction(1), None, None, None)
    path = ReturnPath("EST-RR", (pin,), ((date(2026, 1, 1), Fraction(500)),), Fraction(500), {})
    expected = dataclasses.replace(st, return_paths={O1: path})
    state, trace = _run(ctx, expected)
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P03"], targets["FY2026-P04"]) == (usd("4500.00"), usd("4000.00"))
    assert [
        Fraction(Decimal(_node(trace, "return_expected_units", O1, period).value))
        for period in ("FY2026-P03", "FY2026-P04")
    ] == [1, 0]

    with pytest.raises(EngineError) as raised:
        run(ctx, classified("BUYBACK", [shipped]), TraceBuilder(engine_version=ENGINE_VERSION))
    assert (raised.value.code, raised.value.detail["rule"]) == (
        "ENGINE_INVARIANT_VIOLATED",
        "S09-R-13",
    )


def test_milestones_and_percent_complete() -> None:
    ctx = book_context()
    design = segment(
        Fraction(10000), usd("10000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )

    def achieved(version: int, effective: date, weight: str) -> EventView:
        payload = {
            "obligation_key": "POB-01",
            "milestone_code": f"M{version}",
            "cumulative_weight": Decimal(weight),
        }
        return event_view(
            CONTRACT_KEY,
            version,
            "MILESTONE_ACHIEVED",
            effective,
            payload,
            obligation_keys=["POB-01"],
        )

    milestone_ob = obligation("POB-01", [design], method="MILESTONE", convention=None)
    first = achieved(2, date(2026, 3, 20), "0.25")
    st = allocated_state([milestone_ob], events=[first])
    state, trace = _run(ctx, st)
    at = components.target_at(ctx, st, milestone_ob, date(2026, 3, 31))
    assert at.fixed is not None and at.fixed.progress.value == Fraction(1, 4)
    node = _node(trace, "progress_ratio", O1, "FY2026-P03")
    assert (node.formula_id, node.params["weight"], node.params["base"]) == (
        "rec.progress.milestone.v1",
        "1/4",
        "0",
    )
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P02"], targets["FY2026-P03"], targets["FY2026-P12"]) == (
        0,
        usd("2500.00"),
        usd("2500.00"),
    )

    def recorded(version: int, effective: date, ratio: str, measure: str) -> EventView:
        payload = {
            "obligation_key": "POB-01",
            "cumulative_progress_ratio": Decimal(ratio),
            "measure": measure,
        }
        return event_view(
            CONTRACT_KEY,
            version,
            "PROGRESS_RECORDED",
            effective,
            payload,
            obligation_keys=["POB-01"],
        )

    output_ob = obligation("POB-01", [design], method="OUTPUT_PERCENT", convention=None)
    events = [
        recorded(2, date(2026, 4, 30), "0.40", "OUTPUT_PERCENT"),
        recorded(3, date(2026, 5, 31), "0.90", "LABOUR_HOURS"),  # another measure: not read
        recorded(4, date(2026, 8, 31), "1", "OUTPUT_PERCENT"),
    ]
    st = allocated_state([output_ob], events=events)
    state, trace = _run(ctx, st)
    at = components.target_at(ctx, st, output_ob, date(2026, 4, 30))
    assert at.fixed is not None and at.fixed.progress.value == Fraction(2, 5)
    node = _node(trace, "progress_ratio", O1, "FY2026-P05")
    assert (node.formula_id, node.params["ratio"]) == ("rec.progress.output_percent.v1", "2/5")
    targets = targets_by_period(state, O1)
    assert [targets[f"FY2026-P{month:02d}"] for month in (3, 4, 5, 8)] == [
        0,
        usd("4000.00"),
        usd("4000.00"),
        usd("10000.00"),
    ]

    # Since a boundary: g = (w(d) − w_k) ÷ (1 − w_k), with w_k read before the boundary event.
    boundary = event_view(
        CONTRACT_KEY,
        3,
        "CONTRACT_AMENDED",
        date(2026, 6, 1),
        {"modification_id": "MOD-1"},
        obligation_keys=["POB-01"],
    )
    extended = segment(
        Fraction(12000),
        usd("12000.00"),
        start=date(2026, 6, 1),
        end=date(2026, 12, 31),
        basis="PROSPECTIVE",
        cause=SegmentCause.MODIFICATION,
        event_key=boundary.event_key,
        base_revenue_posted=usd("2500.00"),
        base_revenue_exact=Fraction(2500),
    )
    ob = obligation(
        "POB-01", [design, extended], method="MILESTONE", convention=None, start=date(2026, 1, 1)
    )
    st = allocated_state([ob], events=[first, boundary, achieved(4, date(2026, 7, 15), "0.625")])
    state, trace = _run(ctx, st)
    targets = targets_by_period(state, O1)
    assert targets["FY2026-P06"] == usd("2500.00")  # g = 0 at the boundary (S09-INV-09)
    assert targets["FY2026-P07"] == usd("7250.00")  # 2,500 + 9,500 × (0.625 − 0.25) ÷ 0.75
    assert _node(trace, "progress_ratio", O1, "FY2026-P07").params["base"] == "1/4"


def test_chk_007_units_schedule() -> None:
    calendar = entity(start=date(2023, 1, 1), months=12)
    ctx = book_context(calendar, preset="LEGACY_PARITY")
    x_exact = Fraction(1300 * 368, 2018)  # golden Contract 1 POB #2: 237.066402…
    software = segment(
        x_exact, usd("237.07"), start=date(2023, 1, 1), end=date(2023, 12, 31), quantity=Fraction(2)
    )
    ob = obligation(
        "POB-02", [software], method="UNITS_DELIVERED", convention=None, quantity=Fraction(2)
    )

    def delivered(version: int, effective: date) -> EventView:
        payload = {"obligation_key": "POB-02", "quantity": Decimal("1"), "trigger": "DELIVERY"}
        return event_view(
            CONTRACT_KEY,
            version,
            "DELIVERY_RECORDED",
            effective,
            payload,
            obligation_keys=["POB-02"],
        )

    st = allocated_state(
        [ob],
        events=[delivered(2, date(2023, 1, 31)), delivered(3, date(2023, 2, 28))],
        inception=date(2023, 1, 1),
    )
    state, trace = _run(ctx, st)
    amounts = period_amounts(targets_by_period(state, O2))
    assert (amounts["FY2023-P01"], amounts["FY2023-P02"]) == (usd("118.53"), usd("118.54"))
    assert format_exact(x_exact / 2, 6) == "118.533201"
    assert round_half_up(Fraction(usd("237.07"), 200), 2) == usd("118.54")  # forbidden A × f
    node = _node(trace, "progress_ratio", O2, "FY2023-P01")
    assert (node.formula_id, node.params["delivered"], node.params["quantity"]) == (
        "rec.progress.units.v1",
        "1",
        "2",
    )


def test_ex_06_c_total_revenue() -> None:
    # EX-06-C: 120 products at 100.00; after 60 transferred, 30 more at 95.00 as a separate
    # contract (proposal SEPARATE_CONTRACT), so each contract is its own group.
    ctx = book_context()

    def units_contract(contract_key: str, price: int, quantity: int) -> ObligationState:
        seg = segment(
            Fraction(price * quantity),
            usd(f"{price * quantity}.00"),
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
            quantity=Fraction(quantity),
        )
        return obligation(
            "POB-01",
            [seg],
            contract_key=contract_key,
            method="UNITS_DELIVERED",
            convention=None,
            quantity=Fraction(quantity),
        )

    def shipped(contract_key: str, version: int, effective: date, quantity: int) -> EventView:
        payload = {"obligation_key": "POB-01", "quantity": Decimal(quantity), "trigger": "DELIVERY"}
        return event_view(
            contract_key,
            version,
            "DELIVERY_RECORDED",
            effective,
            payload,
            obligation_keys=["POB-01"],
        )

    original = allocated_state(
        [units_contract("K-01", 100, 120)],
        events=[
            shipped("K-01", 2, date(2026, 2, 15), 60),
            shipped("K-01", 3, date(2026, 5, 20), 60),
        ],
    )
    separate = allocated_state(
        [units_contract("K-02", 95, 30)], events=[shipped("K-02", 2, date(2026, 6, 10), 30)]
    )
    k01 = targets_by_period(_run(ctx, original)[0], "K-01/POB-01")
    k02 = targets_by_period(_run(ctx, separate)[0], "K-02/POB-01")
    assert (k01["FY2026-P02"], k02["FY2026-P02"]) == (usd("6000.00"), 0)
    assert k01["FY2026-P12"] + k02["FY2026-P12"] == usd("14850.00")
