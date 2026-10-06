"""Stage 09 obligation measures, schedules and versioning (ENC-10).

ENGINE_SPEC_B §9.2.13 and §9.2.14 (S09-R-45 to S09-R-50), §9.3 S09-INV-03, S09-INV-04 and
S09-INV-07, §9.5; ENGINE_SPEC Table 0.9-A and CV-64; 04 T-CON-11, T-ENG-01, T-ENG-02 and DB-17;
DEV-051. The ``AllocatedState`` and the stage 06 and stage 08 ``catch_up@<event key>`` nodes are
built against the documented contract (support.recognition; D-81 integration after merge).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.enums import SatisfactionStatus, ScheduleKind
from erev_engine.errors import EngineError
from erev_engine.money import largest_remainder
from erev_engine.stages import STAGES
from erev_engine.stages.s09_recognition import RecognitionState, run, schedule
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    SegmentCause,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import entity
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

O1 = f"{CONTRACT_KEY}/POB-01"
O2 = f"{CONTRACT_KEY}/POB-02"
O3 = f"{CONTRACT_KEY}/POB-03"
CTX = book_context()
YEAR_START, YEAR_END = date(2026, 1, 1), date(2026, 12, 31)
LINE_KEY_FIELDS = ("subject_key", "schedule_kind", "line_type", "period_key")


def _run(ctx: BookContext, st: AllocatedState) -> tuple[RecognitionState, Trace]:
    """Run stage 09; the trace re-evaluates and every node formula is declared by ``STAGES``."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)  # the stage 06 and stage 08 nodes stage 09 cites
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    spec = next(item for item in STAGES if item.stage == "09")
    assert {node.formula_id for node in trace.nodes} <= set(spec.formula_ids)
    ids = {node.id for node in trace.nodes}
    for measures in state.obligation_measures.values():  # S09-INV-03; 04 DB-17
        assert measures.allocated_amount == (
            measures.revenue_cum + measures.scheduled_amount + measures.awaiting_trigger_amount
        )
        assert set(measures.trace_nodes.values()) <= ids
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _ratable(
    key: str = "POB-01", *, end: date = YEAR_END, convention: str = "MONTHLY_EVEN"
) -> ObligationState:
    service = segment(Fraction(12000), usd("12000.00"), start=YEAR_START, end=end)
    return obligation(key, [service], convention=convention)


def _units(key: str = "POB-02", quantity: int = 10, amount: int = 10000) -> ObligationState:
    goods = segment(
        Fraction(amount),
        amount * 100,
        start=YEAR_START,
        end=YEAR_END,
        quantity=Fraction(quantity),
        measure="UNITS_DELIVERED",
    )
    return obligation(
        key, [goods], method="UNITS_DELIVERED", convention=None, quantity=Fraction(quantity)
    )


def _delivery(
    version: int, when: date, quantity: str, key: str = "POB-02", contract_key: str = CONTRACT_KEY
) -> EventView:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return event_view(
        contract_key, version, "DELIVERY_RECORDED", when, payload, obligation_keys=[key]
    )


def _invoice(
    version: int,
    when: date,
    amount: str,
    key: str = "POB-01",
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload = {
        "invoice_number": f"INV-{version}",
        "line_external_id": key,
        "obligation_key": key,
        "amount": Decimal(amount),
        "issue_date": when,
    }
    return event_view(
        contract_key, version, "BILLING_RECORDED", when, payload, obligation_keys=[key]
    )


def _hold(version: int, when: date) -> EventView:
    payload = {
        "hold_type": "recognition",
        "hold_source": "MANUAL",
        "reason": "Customer acceptance dispute",
        "obligation_key": "POB-01",
    }
    return event_view(
        CONTRACT_KEY, version, "HOLD_APPLIED", when, payload, obligation_keys=["POB-01"]
    )


def _release(version: int, when: date, applied: EventView) -> EventView:
    payload = {"hold_id": applied.event_key, "comment": "Dispute resolved"}
    return event_view(CONTRACT_KEY, version, "HOLD_RELEASED", when, payload)


def _tp_change_state(*, with_change: bool) -> AllocatedState:
    """CHK-110: TP 140,000.00 over 2026 (MONTHLY_EVEN); a version effective 30 June sets
    120,000.00."""
    inception = segment(Fraction(140000), usd("140000.00"), start=YEAR_START, end=YEAR_END)
    if not with_change:
        return allocated_state([obligation("POB-01", [inception], convention="MONTHLY_EVEN")])
    change = event_view(
        CONTRACT_KEY, 2, "ESTIMATE_CHANGED", date(2026, 6, 30), {"estimate_version_id": "VC@v2"}
    )
    revised = segment(
        Fraction(120000),
        usd("120000.00"),
        start=YEAR_START,
        end=YEAR_END,
        effective=date(2026, 6, 30),
        cause=SegmentCause.TP_CHANGE,
        event_key=change.event_key,
    )
    key = f"{CONTRACT_KEY}/VC-MIN"
    version = estimate_version(key, "VARIABLE_CONSIDERATION", 2, change.effective_date)
    pins = EstimatePins({key: (EstimatePin(version, change.order_key),)})
    ob = obligation("POB-01", [inception, revised], convention="MONTHLY_EVEN")
    return allocated_state([ob], events=[change], estimates=pins)


def test_s09_r45_scheduled_and_awaiting_trigger() -> None:
    # A TIME_ELAPSED obligation of 12,000.00 and a units obligation at the version date 31 March.
    events = [_delivery(2, date(2026, 2, 15), "4"), _invoice(3, date(2026, 3, 31), "12000.00")]
    state, trace = _run(CTX, allocated_state([_ratable(), _units()], events=events))
    ratable = state.obligation_measures[O1]
    assert ratable.as_of == date(2026, 3, 31)
    assert (
        ratable.allocated_amount,
        ratable.revenue_cum,
        ratable.scheduled_amount,
        ratable.awaiting_trigger_amount,
        ratable.remaining_allocation,
    ) == (usd("12000.00"), usd("3000.00"), usd("9000.00"), 0, usd("9000.00"))
    scheduled = _node(trace, f"scheduled_amount:{O1}:-")
    assert (scheduled.formula_id, scheduled.value, scheduled.inputs) == (
        "rec.scheduled.v1",
        "9000.00",
        (f"revenue_cum:{O1}:-",),
    )
    assert scheduled.params["pattern"] == "DETERMINISTIC"
    awaiting = _node(trace, f"awaiting_trigger_amount:{O1}:-")
    assert (awaiting.value, awaiting.inputs) == (
        "0.00",
        (f"remaining_allocation:{O1}:-", f"scheduled_amount:{O1}:-"),
    )
    assert _node(trace, f"revenue_cum:{O1}:-").value == "3000.00"
    assert ratable.trace_nodes["progress_ratio"] == f"progress_ratio:{O1}:-"
    assert _node(trace, f"progress_ratio:{O1}:-").value == "0.25"

    # The undelivered allocation of a units obligation awaits a trigger.
    units = state.obligation_measures[O2]
    assert (
        units.revenue_cum,
        units.scheduled_amount,
        units.awaiting_trigger_amount,
        units.remaining_quantity,
        units.progress_ratio,
    ) == (usd("4000.00"), 0, usd("6000.00"), Fraction(6), Fraction(2, 5))
    assert _node(trace, f"scheduled_amount:{O2}:-").params["pattern"] == "EVENT_DRIVEN"
    assert _node(trace, f"remaining_quantity:{O2}:-").value == "6"

    # EX-09-G at 31 May: the hold applied on 10 April is open, so nothing is scheduled.
    hold = _hold(2, date(2026, 4, 10))
    open_hold = allocated_state([_ratable()], events=[hold, _invoice(3, date(2026, 5, 31), "1.00")])
    state, trace = _run(CTX, open_hold)
    held = state.obligation_measures[O1]
    assert (held.as_of, held.revenue_cum, held.scheduled_amount, held.awaiting_trigger_amount) == (
        date(2026, 5, 31),
        usd("3000.00"),
        0,
        usd("9000.00"),
    )
    assert held.hold_types == ("recognition",)
    assert _node(trace, f"scheduled_amount:{O1}:-").params["held"] == "true"
    assert _node(trace, f"revenue_cum:{O1}:-").inputs == (f"hold_frozen_target:{O1}:-",)

    released = allocated_state([_ratable()], events=[hold, _release(3, date(2026, 6, 20), hold)])
    ob = released.obligations[0]
    at_may = schedule.obligation_measures(CTX, released, ob, date(2026, 5, 31))
    assert (at_may.scheduled_amount, at_may.awaiting_trigger_amount) == (0, usd("9000.00"))
    state, _ = _run(CTX, released)
    after = state.obligation_measures[O1]  # version date 20 June: f = 5/12, the hold is closed
    assert (after.revenue_cum, after.scheduled_amount, after.awaiting_trigger_amount) == (
        usd("5000.00"),
        usd("7000.00"),
        0,
    )
    assert after.hold_types == ()

    # V4: while NOT_A_CONTRACT the remainder needs a status change, so it awaits a trigger; V5:
    # before the recognition start, time alone places it.
    not_a_contract = allocated_state([_ratable()], statuses=((YEAR_START, "NOT_A_CONTRACT"),))
    guarded = schedule.obligation_measures(
        CTX, not_a_contract, not_a_contract.obligations[0], date(2026, 3, 31)
    )
    assert (guarded.revenue_cum, guarded.scheduled_amount, guarded.awaiting_trigger_amount) == (
        0,
        0,
        usd("12000.00"),
    )
    later = obligation(
        "POB-01",
        [segment(Fraction(12000), usd("12000.00"), start=YEAR_START, end=YEAR_END)],
        convention="MONTHLY_EVEN",
        recognition_start=date(2026, 7, 1),
    )
    v5 = allocated_state([later])
    assert schedule.obligation_measures(CTX, v5, later, date(2026, 3, 31)).scheduled_amount == usd(
        "12000.00"
    )


def test_s09_r46_satisfaction_status() -> None:
    nothing = allocated_state([_units()])
    unsatisfied = schedule.obligation_measures(
        CTX, nothing, nothing.obligations[0], date(2026, 3, 31)
    )
    assert (
        unsatisfied.satisfaction_status,
        unsatisfied.satisfied_date,
        unsatisfied.revenue_cum,
        unsatisfied.progress_ratio,
    ) == (SatisfactionStatus.UNSATISFIED, None, 0, 0)

    events = [_delivery(2, date(2026, 2, 15), "4"), _delivery(3, date(2026, 5, 10), "6")]
    delivered = allocated_state([_units()], events=events)
    ob = delivered.obligations[0]
    partial = schedule.obligation_measures(CTX, delivered, ob, date(2026, 3, 31))
    assert (partial.satisfaction_status, partial.satisfied_date) == (
        SatisfactionStatus.PARTIALLY_SATISFIED,
        None,
    )
    complete = schedule.obligation_measures(CTX, delivered, ob, date(2026, 6, 30))
    assert (complete.satisfaction_status, complete.satisfied_date, complete.progress_ratio) == (
        SatisfactionStatus.SATISFIED,
        date(2026, 5, 10),
        1,
    )
    state, _ = _run(CTX, delivered)
    assert state.obligation_measures[O2].satisfied_date == date(2026, 5, 10)

    # DAILY over 1 January to 30 June 2026: f reaches 1 on the term end.
    short = allocated_state([_ratable(end=date(2026, 6, 30), convention="DAILY")])
    at_september = schedule.obligation_measures(CTX, short, short.obligations[0], date(2026, 9, 30))
    assert (at_september.satisfaction_status, at_september.satisfied_date) == (
        SatisfactionStatus.SATISFIED,
        date(2026, 6, 30),
    )

    # EX-06-J: the termination at month 18 removes the remaining allocation.
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=YEAR_START, end=date(2027, 12, 31)
    )
    termination = segment(
        Fraction(180000),
        usd("180000.00"),
        start=YEAR_START,
        end=date(2027, 6, 30),
        effective=date(2027, 6, 30),
        cause=SegmentCause.TERMINATION,
        event_key=f"{CONTRACT_KEY}/EV-000005",
    )
    terminated = event_view(
        CONTRACT_KEY,
        5,
        "CONTRACT_TERMINATED",
        date(2027, 6, 30),
        {"modification_id": "MOD-T", "termination_kind": "FULL"},
        obligation_keys=["POB-01"],
    )
    ob = obligation("POB-01", [subscription, termination], convention="MONTHLY_EVEN")
    st = allocated_state([ob], events=[terminated])
    before = schedule.obligation_measures(CTX, st, ob, date(2027, 5, 31))
    assert before.satisfaction_status == SatisfactionStatus.PARTIALLY_SATISFIED
    state, _ = _run(CTX, st)
    cancelled = state.obligation_measures[O1]
    assert (
        cancelled.satisfaction_status,
        cancelled.satisfied_date,
        cancelled.revenue_cum,
        cancelled.remaining_allocation,
        cancelled.awaiting_trigger_amount,
    ) == (SatisfactionStatus.CANCELLED, None, usd("180000.00"), 0, 0)


# Golden Contract 2 (legacy 02 §5.3; legacy 07 §4.4): price 900, (POB, quantity, extended SSP).
CONTRACT_2 = "Contract 2"
CONTRACT_2_LINES = (("POB #1", 8, 612), ("POB #2", 3, 408), ("POB #3", 1, 150), ("VC #1", 1, 0))
PARITY = book_context(entity(start=date(2023, 1, 1), months=12), preset="LEGACY_PARITY")


def _contract_2() -> list[ObligationState]:
    """Inception segments under the units measure with the stage 05 unit SSP = SSP ÷ Q."""
    total = sum(ssp for _, _, ssp in CONTRACT_2_LINES)
    posted = largest_remainder(
        900 * 100,
        [Fraction(ssp) for _, _, ssp in CONTRACT_2_LINES],
        [key for key, _, _ in CONTRACT_2_LINES],
    )
    obligations = []
    for (key, quantity, ssp), a_posted in zip(CONTRACT_2_LINES, posted, strict=True):
        seg = segment(
            Fraction(900 * ssp, total),
            a_posted,
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            quantity=Fraction(quantity),
            measure="UNITS_DELIVERED",
        )
        seg = dataclasses.replace(seg, unit_ssp=Fraction(ssp, quantity))
        obligations.append(
            obligation(
                key,
                [seg],
                contract_key=CONTRACT_2,
                method="UNITS_DELIVERED",
                convention=None,
                quantity=Fraction(quantity),
            )
        )
    return obligations


def _version(events: Sequence[EventView], new: Sequence[EventView]) -> RecognitionState:
    """A contract version whose stream includes ``events``; only ``new`` are first included."""
    stream = [dataclasses.replace(ev, is_new=ev in new) for ev in events]
    st = allocated_state(
        _contract_2(),
        events=stream,
        inception=date(2023, 1, 1),
        statuses=((date(2023, 1, 1), "ACTIVE"),),
    )
    state, _ = _run(PARITY, st)
    return state


def test_s09_r47_legacy_measures() -> None:
    step_04 = _delivery(2, date(2023, 1, 31), "1", "POB #1", CONTRACT_2)
    step_06 = _delivery(3, date(2023, 3, 31), "0.4", "POB #3", CONTRACT_2)
    step_07 = _invoice(4, date(2023, 4, 30), "20", "POB #1", CONTRACT_2)
    pob_1, pob_3 = f"{CONTRACT_2}/POB #1", f"{CONTRACT_2}/POB #3"

    delivery = _version([step_04], new=[step_04]).obligation_measures[pob_1]
    assert (delivery.as_of, delivery.delivered_quantity) == (date(2023, 1, 31), 1)
    assert delivery.ssp_delivered == delivery.ssp_delivered_cum == Fraction("76.5")
    assert delivery.revenue_amount == usd("58.85")

    # Step 06 delivers 0.4 of POB #3 (SSP delivered 60, EX-06-F state); POB #1 has no new event.
    state = _version([step_04, step_06], new=[step_06])
    assert (
        state.obligation_measures[pob_3].ssp_delivered,
        state.obligation_measures[pob_3].ssp_delivered_cum,
        state.obligation_measures[pob_3].delivered_quantity,
    ) == (Fraction(60), Fraction(60), Fraction(2, 5))
    idle = state.obligation_measures[pob_1]
    assert (idle.delivered_quantity, idle.ssp_delivered, idle.revenue_amount) == (0, 0, 0)
    assert idle.ssp_delivered_cum == Fraction("76.5")

    # Step 07 bills 20 on POB #1 without a delivery: every period measure is 0 (DEV-051).
    state = _version([step_04, step_06, step_07], new=[step_07])
    for subject_key in (pob_1, pob_3):
        measures = state.obligation_measures[subject_key]
        assert (measures.delivered_quantity, measures.ssp_delivered, measures.revenue_amount) == (
            0,
            0,
            0,
        )
    assert state.obligation_measures[pob_1].ssp_delivered_cum == Fraction("76.5")
    assert state.obligation_measures[pob_1].revenue_cum == usd("58.85")


def test_s09_r48_schedule_lines_versioned() -> None:
    first, _ = _run(CTX, _tp_change_state(with_change=False))
    kept = tuple(first.schedule_lines)
    second, trace = _run(CTX, _tp_change_state(with_change=True))

    for state in (first, second):
        keys = [
            tuple(getattr(line, name) for name in LINE_KEY_FIELDS) for line in state.schedule_lines
        ]
        assert len(keys) == len(set(keys))  # (subject key, schedule kind, line type, period)
        assert all(line.amount != 0 for line in state.schedule_lines)
        assert {line.schedule_kind for line in state.schedule_lines} == {ScheduleKind.REVENUE}
        assert {line.subject_type for line in state.schedule_lines} == {"obligation"}
        targets = targets_by_period(state, O1)
        assert sum(line.amount for line in state.schedule_lines) == targets[max(targets)]
    ids = {node.id for node in trace.nodes}
    assert {line.trace_node_id for line in second.schedule_lines} <= ids  # one computation

    lines = {(line.line_type, line.period_key): line for line in second.schedule_lines}
    change = lines[("TP_CHANGE", "FY2026-P06")]
    assert (change.amount, change.cumulative_amount, change.is_released_at_close) == (
        usd("-10000.00"),
        usd("-10000.00"),
        False,
    )
    assert change.trace_node_id == f"revenue_by_cause:{O1}/TP_CHANGE:FY2026-P06"
    normal = lines[("NORMAL", "FY2026-P06")]
    targets = targets_by_period(second, O1)
    assert normal.cumulative_amount + change.cumulative_amount == targets["FY2026-P06"]
    exact_target = next(
        target.exact for target in second.revenue_targets if target.period_key == "FY2026-P06"
    )
    assert normal.cumulative_exact + Fraction(change.cumulative_amount, 100) == exact_target

    # The recomputation is a complete new set: the first version's lines are never updated.
    assert first.schedule_lines == kept
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.schedule_lines[0].amount = 0  # type: ignore[misc]
    amounts = {(line.line_type, line.period_key): line.amount for line in first.schedule_lines}
    assert amounts[("NORMAL", "FY2026-P05")] == lines[("NORMAL", "FY2026-P05")].amount
    assert ("TP_CHANGE", "FY2026-P06") not in amounts
    assert period_amounts(targets_by_period(first, O1))["FY2026-P06"] == usd("11666.67")


def test_s09_r49_release_flags() -> None:
    usage_fees = segment(Fraction(0), 0, start=YEAR_START, end=YEAR_END, component="PERIOD_VC")
    with_usage = obligation(
        "POB-03",
        [segment(Fraction(1200), usd("1200.00"), start=YEAR_START, end=YEAR_END), usage_fees],
        convention="MONTHLY_EVEN",
    )
    usage = event_view(
        CONTRACT_KEY,
        4,
        "USAGE_REPORTED",
        date(2026, 2, 3),
        {
            "obligation_key": "POB-03",
            "usage_period_start": date(2026, 1, 1),
            "usage_period_end": date(2026, 1, 31),
            "metric": "API_CALLS",
            "quantity": Decimal("1000"),
            "rated_amount": Decimal("150.00"),
        },
        obligation_keys=["POB-03"],
    )
    st = _tp_change_state(with_change=True)
    events = [*st.events, _delivery(3, date(2026, 3, 10), "4"), usage]
    both = allocated_state(
        [*st.obligations, _units(), with_usage], events=events, estimates=st.estimates
    )
    state, _ = _run(CTX, both)
    flags = {
        (line.subject_key, str(line.line_type), line.period_key): line.is_released_at_close
        for line in state.schedule_lines
    }
    ratable_normal = [
        value for (key, kind, _), value in flags.items() if key == O1 and kind == "NORMAL"
    ]
    assert ratable_normal and all(ratable_normal)
    assert flags[(O1, "TP_CHANGE", "FY2026-P06")] is False
    assert flags[(O2, "NORMAL", "FY2026-P03")] is False  # units measure: event-driven
    assert (flags[(O3, "NORMAL", "FY2026-P01")], flags[(O3, "NORMAL", "FY2026-P02")]) == (
        True,
        False,  # the realised usage fee of January arrives in February
    )
    units_line = next(
        line
        for line in state.schedule_lines
        if line.subject_key == O2 and line.period_key == "FY2026-P03"
    )
    assert units_line.quantity == 4


def test_s09_r50_projection_horizon() -> None:
    ctx = book_context(horizon="FY2026-P06")
    events = [_delivery(2, date(2026, 3, 15), "4"), _delivery(3, date(2026, 9, 15), "6")]
    state, _ = _run(ctx, allocated_state([_ratable(), _units()], events=events))
    ratable = sorted(line.period_key for line in state.schedule_lines if line.subject_key == O1)
    assert (ratable[0], ratable[-1], len(ratable)) == ("FY2026-P01", "FY2026-P12", 12)
    assert targets_by_period(state, O1)["FY2026-P12"] == usd("12000.00")
    units = sorted(line.period_key for line in state.schedule_lines if line.subject_key == O2)
    assert units == ["FY2026-P03"]
    assert max(targets_by_period(state, O2)) == "FY2026-P06"


def test_s09_inv_07_one_measure_per_version() -> None:
    amended = event_view(
        CONTRACT_KEY,
        2,
        "CONTRACT_AMENDED",
        date(2026, 6, 30),
        {"modification_id": "MOD-1"},
        obligation_keys=["POB-01"],
    )
    time_elapsed = segment(Fraction(12000), usd("12000.00"), start=YEAR_START, end=YEAR_END)
    units = segment(
        Fraction(12000),
        usd("12000.00"),
        start=YEAR_START,
        end=YEAR_END,
        effective=date(2026, 6, 30),
        cause=SegmentCause.MODIFICATION,
        event_key=amended.event_key,
        measure="UNITS_DELIVERED",
    )
    ob = obligation("POB-01", [time_elapsed, units], convention="MONTHLY_EVEN")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    with pytest.raises(EngineError) as raised:
        run(CTX, allocated_state([ob], events=[amended]), tb)
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert (raised.value.subject_key, dict(raised.value.detail)) == (
        O1,
        {"methods": "TIME_ELAPSED,UNITS_DELIVERED", "rule": "S09-INV-07"},
    )
    assert tb.build(root_measures={}).nodes == ()  # asserted at stage entry

    # The parity marker since a boundary restates the units measure; it is not a second method.
    since_boundary = dataclasses.replace(
        units, basis="PROSPECTIVE", progress_measure="UNITS_SINCE_BOUNDARY"
    )
    goods = dataclasses.replace(time_elapsed, progress_measure="UNITS_DELIVERED")
    parity = obligation(
        "POB-01", [goods, since_boundary], method="UNITS_DELIVERED", convention=None
    )
    schedule.validate(allocated_state([parity], events=[amended]))
