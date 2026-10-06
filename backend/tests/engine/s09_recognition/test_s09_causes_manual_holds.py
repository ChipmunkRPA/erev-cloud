"""Stage 09 cause decomposition, manual release, deferral, schedule overrides and holds (ENC-9).

ENGINE_SPEC_B §9.2.10 to §9.2.12 (S09-R-35 to S09-R-44), §9.3 S09-INV-04 and S09-INV-08, §9.5,
§9.7 EX-09-B, EX-09-E and EX-09-G; ENGINE_SPEC Table 0.9-A. The ``AllocatedState`` and the stage 06
and stage 08 ``catch_up@<event key>`` nodes are built against the documented contract
(support.recognition; D-81 integration after merge).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.money import round_half_up
from erev_engine.stages.s09_recognition import RecognitionState, components, decompose, run
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    SegmentCause,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
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
CTX = book_context()
YEAR_START, YEAR_END = date(2026, 1, 1), date(2026, 12, 31)


def _run(
    ctx: BookContext, st: AllocatedState, catch_ups: Mapping[tuple[str, str], int] | None = None
) -> tuple[RecognitionState, Trace]:
    """Run stage 09 after faking the stage 06 and 08 catch-up nodes; the trace re-evaluates."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st, catch_ups)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _causes(state: RecognitionState, subject_key: str, period_key: str) -> dict[str, int]:
    return {
        str(target.cause): target.value
        for target in state.revenue_by_cause
        if target.subject_key == subject_key and target.period_key == period_key
    }


def _assert_causes_sum(state: RecognitionState, subject_key: str) -> None:
    """S09-INV-04: Σ over line types = target(t) − target(t − 1) for every period."""
    for period_key, amount in period_amounts(targets_by_period(state, subject_key)).items():
        assert sum(_causes(state, subject_key, period_key).values()) == amount


def _ratable(x_exact: int = 12000, key: str = "POB-01") -> ObligationState:
    """EX-09-G: an allocation recognised over calendar 2026 under MONTHLY_EVEN."""
    service = segment(Fraction(x_exact), x_exact * 100, start=YEAR_START, end=YEAR_END)
    return obligation(key, [service], convention="MONTHLY_EVEN")


def _revised(
    x_exact: int, effective: date, event: EventView, cause: SegmentCause
) -> AllocationSegment:
    """An inception-basis segment from a boundary: the updated allocation over the same term."""
    return segment(
        Fraction(x_exact),
        x_exact * 100,
        start=YEAR_START,
        end=YEAR_END,
        effective=effective,
        cause=cause,
        event_key=event.event_key,
    )


def _estimate(version: int, when: date, element: str) -> EventView:
    payload = {"estimate_version_id": f"{CONTRACT_KEY}/{element}@v2"}
    return event_view(CONTRACT_KEY, version, "ESTIMATE_CHANGED", when, payload)


def _pins(*applied: tuple[EventView, str, str]) -> EstimatePins:
    """Estimate versions v2 applied by the given events: (event, element code, E-09 kind)."""
    pins: dict[str, tuple[EstimatePin, ...]] = {}
    for ev, element, kind in applied:
        key = f"{CONTRACT_KEY}/{element}"
        version = estimate_version(key, kind, 2, ev.effective_date)
        pins[key] = (*pins.get(key, ()), EstimatePin(version, ev.order_key))
    return EstimatePins(pins)


def _adjustment(
    version: int, when: date, kind: str, period_key: str, **members: object
) -> EventView:
    payload: dict[str, object] = {
        "manual_adjustment_id": f"MA-{version}",
        "kind": kind,
        "obligation_key": "POB-01",
        "period_key": period_key,
        **members,
    }
    return event_view(
        CONTRACT_KEY,
        version,
        "MANUAL_ADJUSTMENT_APPLIED",
        when,
        payload,
        obligation_keys=["POB-01"],
    )


def _hold(
    version: int, when: date, obligation_key: str | None = "POB-01", hold_type: str = "recognition"
) -> EventView:
    payload: dict[str, object] = {
        "hold_type": hold_type,
        "hold_source": "MANUAL",
        "reason": "Customer acceptance dispute",
    }
    keys: list[str] = []
    if obligation_key is not None:
        payload["obligation_key"] = obligation_key
        keys.append(obligation_key)
    return event_view(CONTRACT_KEY, version, "HOLD_APPLIED", when, payload, obligation_keys=keys)


def _release(version: int, when: date, applied: EventView) -> EventView:
    payload = {"hold_id": applied.event_key, "comment": "Dispute resolved"}
    return event_view(CONTRACT_KEY, version, "HOLD_RELEASED", when, payload)


def _periods(targets: Mapping[str, int], months: tuple[int, ...]) -> list[int]:
    return [targets[f"FY2026-P{month:02d}"] for month in months]


def test_ex_09_b_cause_split() -> None:
    # EX-09-B (CHK-027). Cost-to-cost progress is ENC-5, deferred past 1.0-rc, so the posted
    # targets at each ENG-06 position are computed from the documented figures and the sequential
    # decomposition runs over them (D-81 integration after merge).
    def c(x: int, costs: int, eac: int) -> int:
        return round_half_up(Fraction(x * costs, eac), 2)

    august = c(1_000_000, 420_000, 700_000)
    amended = event_view(CONTRACT_KEY, 5, "CONTRACT_AMENDED", date(2026, 9, 10), {})
    eac = event_view(CONTRACT_KEY, 7, "ESTIMATE_CHANGED", date(2026, 9, 30), {})
    after_amendment = c(1_350_000, 420_000, 820_000)
    after_cost = c(1_350_000, 502_000, 820_000)
    after_eac = c(1_350_000, 502_000, 850_000)
    assert (august, after_amendment, after_cost, after_eac) == (
        usd("600000.00"),
        usd("691463.41"),
        usd("826463.41"),
        usd("797294.12"),
    )
    modification = decompose.CausePoint(
        amended,
        "MODIFICATION",
        after_amendment - august,
        decompose.catch_up_node_id(amended.event_key, O1),
    )
    estimate = decompose.CausePoint(
        eac, "CATCH_UP", after_eac - after_cost, decompose.catch_up_node_id(eac.event_key, O1)
    )
    amounts = decompose.sequential(august, after_eac, [modification, estimate])
    assert amounts == {
        "CATCH_UP": usd("-29169.29"),
        "MODIFICATION": usd("91463.41"),
        "NORMAL": usd("135000.00"),
    }
    assert sum(amounts.values()) == after_eac - august == usd("197294.12")

    # J-14: a cost of 20,500.00 effective 29 September is inserted before the EAC change.
    corrected = c(1_350_000, 522_500, 820_000)
    final = c(1_350_000, 522_500, 850_000)
    catch_up = decompose.CausePoint(eac, "CATCH_UP", final - corrected, None)
    amounts = decompose.sequential(august, final, [modification, catch_up])
    assert amounts["NORMAL"] == usd("135000.00") + usd("33750.00")
    assert amounts["CATCH_UP"] == usd("-30360.47")
    assert sum(amounts.values()) == usd("229852.94")


def test_s09_r37_sequential_catch_up_differs_from_prior_period() -> None:
    # CHK-110 (EX-09-E): TP 140,000.00, and a version effective 30 June sets TP 120,000.00.
    tp_change = _estimate(2, date(2026, 6, 30), "VC-MIN")
    inception = segment(Fraction(140000), usd("140000.00"), start=YEAR_START, end=YEAR_END)
    revised = _revised(120000, date(2026, 6, 30), tp_change, SegmentCause.TP_CHANGE)
    ob = obligation("POB-01", [inception, revised], convention="MONTHLY_EVEN")
    st = allocated_state(
        [ob],
        events=[tp_change],
        estimates=_pins((tp_change, "VC-MIN", "VARIABLE_CONSIDERATION")),
    )
    catch_up_node = decompose.catch_up_node_id(tp_change.event_key, O1)
    state, trace = _run(CTX, st, {(tp_change.event_key, O1): usd("-10000.00")})
    targets = targets_by_period(state, O1)
    assert targets["FY2026-P03"] == usd("35000.00")
    assert targets["FY2026-P06"] - targets["FY2026-P03"] == usd("25000.00")
    normal = sum(_causes(state, O1, f"FY2026-P0{month}")["NORMAL"] for month in (4, 5, 6))
    assert normal == usd("35000.00")
    assert _causes(state, O1, "FY2026-P06")["TP_CHANGE"] == usd("-10000.00")
    _assert_causes_sum(state, O1)
    cause_node = _node(trace, f"revenue_by_cause:{O1}/TP_CHANGE:FY2026-P06")
    assert (cause_node.formula_id, cause_node.inputs) == (
        "rec.decompose.sequential.v1",
        (catch_up_node,),
    )
    cum = _node(trace, f"catch_up_tp_change_cum:{O1}:-")
    assert (cum.value, cum.inputs) == ("-10000.00", (catch_up_node,))

    # The 50-12A prior-period portion evaluates both bases at the start of the period (31 March):
    # round(−20,000 × 3/12) = (5,000.00), not the sequential (10,000.00) (ALG-10 §2.11.3).
    contract = st.contracts[0]
    at_start = date(2026, 3, 31)
    prior_period = (
        components.segment_target(CTX, st, contract, ob, revised, at_start).posted
        - components.segment_target(CTX, st, contract, ob, inception, at_start).posted
    )
    assert prior_period == usd("-5000.00")
    assert prior_period != Fraction(Decimal(cum.value)) * 100


def test_catch_up_cum_by_cause_nodes() -> None:
    amended = event_view(
        CONTRACT_KEY,
        2,
        "CONTRACT_AMENDED",
        date(2026, 3, 31),
        {"modification_id": "MOD-1"},
        obligation_keys=["POB-01"],
    )
    tp_change = _estimate(3, date(2026, 6, 30), "VC-1")
    eac = _estimate(4, date(2026, 9, 30), "EAC-1")
    segments = [
        segment(Fraction(12000), usd("12000.00"), start=YEAR_START, end=YEAR_END),
        _revised(15000, date(2026, 3, 31), amended, SegmentCause.MODIFICATION),
        _revised(14400, date(2026, 6, 30), tp_change, SegmentCause.TP_CHANGE),
        _revised(14000, date(2026, 9, 30), eac, SegmentCause.ESTIMATE_CHANGE),
    ]
    ob = obligation("POB-01", segments, convention="MONTHLY_EVEN")
    st = allocated_state(
        [ob],
        events=[amended, tp_change, eac],
        estimates=_pins((tp_change, "VC-1", "VARIABLE_CONSIDERATION"), (eac, "EAC-1", "EAC")),
    )
    # Stage 06 and stage 08 publish C_after − C_before at each boundary: 3,750.00 − 3,000.00;
    # 7,200.00 − 7,500.00; 10,500.00 − 10,800.00.
    published = {
        (amended.event_key, O1): usd("750.00"),
        (tp_change.event_key, O1): usd("-300.00"),
        (eac.event_key, O1): usd("-300.00"),
    }
    state, trace = _run(CTX, st, published)
    for measure, event, value in (
        ("catch_up_modification_cum", amended, "750.00"),
        ("catch_up_tp_change_cum", tp_change, "-300.00"),
        ("catch_up_estimate_cum", eac, "-300.00"),
    ):
        node = _node(trace, f"{measure}:{O1}:-")
        assert (node.formula_id, node.value) == ("rec.catch_up.sum.v1", value)
        assert node.inputs == (decompose.catch_up_node_id(event.event_key, O1),)
    total = _node(trace, f"catch_up_cum:{O1}:-")
    assert total.value == "150.00"
    assert total.inputs == (
        f"catch_up_modification_cum:{O1}:-",
        f"catch_up_tp_change_cum:{O1}:-",
        f"catch_up_estimate_cum:{O1}:-",
    )
    assert _node(trace, f"catch_up_amount:{O1}:-").value == "150.00"  # every event is new
    assert _causes(state, O1, "FY2026-P03") == {
        "MODIFICATION": usd("750.00"),
        "NORMAL": usd("1000.00"),
    }
    assert _causes(state, O1, "FY2026-P06")["TP_CHANGE"] == usd("-300.00")
    assert _causes(state, O1, "FY2026-P09")["CATCH_UP"] == usd("-300.00")
    _assert_causes_sum(state, O1)


def test_s09_r38_manual_release() -> None:
    release = _adjustment(2, date(2026, 3, 15), "MANUAL_RELEASE", "FY2026-P03", ratio="0.5")
    state, trace = _run(CTX, allocated_state([_ratable()], events=[release]))
    targets = targets_by_period(state, O1)
    # C(P) = 3,000.00 and A = 12,000.00: min(A, max(C(t), 3,000.00 + 0.5 × 9,000.00)).
    assert targets["FY2026-P02"] == usd("2000.00")
    assert _periods(targets, (3, 4, 7, 8, 12)) == [
        usd("7500.00"),
        usd("7500.00"),
        usd("7500.00"),
        usd("8000.00"),
        usd("12000.00"),
    ]
    node = _node(trace, f"manual_adjusted_target@{release.event_key}:{O1}:FY2026-P04")
    assert (node.formula_id, node.inputs) == (
        "sched.manual_release.v1",
        (f"segment_target:{O1}:FY2026-P04",),
    )
    assert _node(trace, f"revenue_cum:{O1}:FY2026-P04").inputs == (node.id,)
    assert _causes(state, O1, "FY2026-P03") == {"NORMAL": usd("5500.00")}
    _assert_causes_sum(state, O1)

    # Mirrored for A < 0: max(A, min(C(t), C(P) + 0.5 × (A − C(P)))).
    state, _ = _run(CTX, allocated_state([_ratable(-12000)], events=[release]))
    targets = targets_by_period(state, O1)
    assert _periods(targets, (2, 3, 8)) == [usd("-2000.00"), usd("-7500.00"), usd("-8000.00")]

    for members, expected in (
        ({"amount": Decimal("1000.00")}, "4000.00"),
        ({"remaining": True}, "12000.00"),
    ):
        adjusted = _adjustment(2, date(2026, 3, 15), "MANUAL_RELEASE", "FY2026-P03", **members)
        state, _ = _run(CTX, allocated_state([_ratable()], events=[adjusted]))
        assert targets_by_period(state, O1)["FY2026-P03"] == usd(expected)
    journal = _adjustment(2, date(2026, 3, 15), "MANUAL_JOURNAL", "FY2026-P03", lines=[])
    state, _ = _run(CTX, allocated_state([_ratable()], events=[journal]))
    assert targets_by_period(state, O1)["FY2026-P03"] == usd("3000.00")  # S09-R-41
    # S09-R-41 (rev 1.63): an adjustment applies in the book it names (04 T-SL-05 ``book_code``);
    # a payload that names no book applies in every book, as the cases above do.
    for book_code, expected in (("IFRS15", "3000.00"), (str(CTX.book_code), "7500.00")):
        named = _adjustment(
            2, date(2026, 3, 15), "MANUAL_RELEASE", "FY2026-P03", ratio="0.5", book_code=book_code
        )
        state, _ = _run(CTX, allocated_state([_ratable()], events=[named]))
        assert targets_by_period(state, O1)["FY2026-P03"] == usd(expected), book_code


def test_s09_r39_manual_defer() -> None:
    defer = _adjustment(2, date(2026, 3, 20), "MANUAL_DEFER", "FY2026-P03", amount="500.00")
    state, trace = _run(CTX, allocated_state([_ratable()], events=[defer]))
    targets = targets_by_period(state, O1)
    amounts = period_amounts(targets)
    assert _periods(targets, (2, 3, 4)) == [usd("2000.00"), usd("2500.00"), usd("4000.00")]
    assert _periods(amounts, (2, 3, 4, 5)) == [
        usd("1000.00"),
        usd("500.00"),
        usd("1500.00"),
        usd("1000.00"),
    ]
    assert _node(trace, f"revenue_cum:{O1}:FY2026-P04").formula_id == "rec.revenue_cum.v1"
    assert f"manual_adjusted_target@{defer.event_key}:{O1}:FY2026-P04" not in {
        node.id for node in trace.nodes
    }
    _assert_causes_sum(state, O1)
    for members, expected in (({"ratio": "0.25"}, "2750.00"), ({"remaining": True}, "2000.00")):
        adjusted = _adjustment(2, date(2026, 3, 20), "MANUAL_DEFER", "FY2026-P03", **members)
        state, _ = _run(CTX, allocated_state([_ratable()], events=[adjusted]))
        targets = targets_by_period(state, O1)
        assert (targets["FY2026-P03"], targets["FY2026-P04"]) == (usd(expected), usd("4000.00"))


def test_s09_r40_schedule_override() -> None:
    override = _adjustment(
        2,
        date(2026, 3, 10),
        "SCHEDULE_OVERRIDE",
        "FY2026-P03",
        periods=[
            {"period_key": "FY2026-P03", "amount": Decimal("1500.00")},
            {"period_key": "FY2026-P04", "amount": Decimal("500.00")},
        ],
    )
    state, trace = _run(CTX, allocated_state([_ratable()], events=[override]))
    targets = targets_by_period(state, O1)
    # T_0 = C(P02) = 2,000.00; T_1 = 3,500.00; T_2 = 4,000.00. After P04: g = (f(t) − 1/3) ÷ (2/3).
    assert _periods(targets, (2, 3, 4, 5, 6, 12)) == [
        usd("2000.00"),
        usd("3500.00"),
        usd("4000.00"),
        usd("5000.00"),
        usd("6000.00"),
        usd("12000.00"),
    ]
    listed = _node(trace, f"manual_adjusted_target@{override.event_key}:{O1}:FY2026-P03")
    respread = _node(trace, f"manual_adjusted_target@{override.event_key}:{O1}:FY2026-P05")
    assert (listed.params["mode"], respread.params["mode"]) == ("listed", "respread")
    assert (respread.params["f_k"], respread.params["f_t"]) == ("1/3", "5/12")

    ahead = _adjustment(
        2,
        date(2026, 3, 10),
        "SCHEDULE_OVERRIDE",
        "FY2026-P03",
        periods=[{"period_key": "FY2026-P03", "amount": Decimal("3000.00")}],
    )
    state, _ = _run(CTX, allocated_state([_ratable()], events=[ahead]))
    targets = targets_by_period(state, O1)
    # T_1 = 5,000.00; April: 5,000.00 + 7,000.00 × (1/12 ÷ 3/4) = 5,777.78; completion at A.
    assert _periods(targets, (3, 4, 12)) == [usd("5000.00"), usd("5777.78"), usd("12000.00")]
    _assert_causes_sum(state, O1)


def test_s09_r41_order_of_application() -> None:
    release = _adjustment(2, date(2026, 6, 15), "MANUAL_RELEASE", "FY2026-P06", ratio="0.5")
    hold = _hold(3, date(2026, 5, 10))
    released = _release(4, date(2026, 8, 20), hold)
    statuses = (
        (YEAR_START, "ACTIVE"),
        (date(2026, 10, 15), "NOT_A_CONTRACT"),
        (date(2026, 11, 1), "VOIDED"),
    )
    st = allocated_state([_ratable()], events=[release, hold, released], statuses=statuses)
    state, trace = _run(CTX, st)
    targets = targets_by_period(state, O1)
    # June: segment 6,000.00 → release max(6,000.00, 6,000.00 + 0.5 × 6,000.00) = 9,000.00 → hold
    # min(9,000.00, L = C(9 May) = 4,000.00) = 4,000.00. Released in August: 9,000.00. The V4 guard
    # comes last: frozen at C(15 October) = 9,000.00, then 0 once VOIDED.
    assert _periods(targets, (4, 5, 6, 7, 8, 9, 10, 11, 12)) == [
        usd("4000.00"),
        usd("4000.00"),
        usd("4000.00"),
        usd("4000.00"),
        usd("9000.00"),
        usd("9000.00"),
        usd("9000.00"),
        0,
        0,
    ]
    chain = [
        f"segment_target:{O1}:FY2026-P06",
        f"manual_adjusted_target@{release.event_key}:{O1}:FY2026-P06",
        f"hold_frozen_target:{O1}:FY2026-P06",
        f"revenue_cum:{O1}:FY2026-P06",
    ]
    for previous, current in zip(chain, chain[1:], strict=False):
        assert _node(trace, current).inputs == (previous,)
    assert [_node(trace, node_id).value for node_id in chain] == [
        "6000.00",
        "9000.00",
        "4000.00",
        "4000.00",
    ]
    assert _node(trace, f"revenue_cum:{O1}:FY2026-P11").params["guard"] == "V4:VOIDED"
    _assert_causes_sum(state, O1)


def test_ex_09_g_recognition_hold() -> None:
    hold = _hold(2, date(2026, 4, 10))
    released = _release(3, date(2026, 6, 20), hold)
    st = allocated_state([_ratable()], events=[hold, released])
    state, trace = _run(CTX, st)
    targets = targets_by_period(state, O1)
    assert _periods(targets, (3, 4, 5, 6)) == [
        usd("3000.00"),
        usd("3000.00"),
        usd("3000.00"),
        usd("6000.00"),
    ]
    amounts = period_amounts(targets)
    assert _periods(amounts, (4, 5, 6)) == [0, 0, usd("3000.00")]
    assert _causes(state, O1, "FY2026-P06") == {"NORMAL": usd("3000.00")}
    frozen = _node(trace, f"hold_frozen_target:{O1}:FY2026-P04")
    assert (frozen.params["level"], frozen.params["applied"]) == ("300000", "2026-04-10")
    _assert_causes_sum(state, O1)

    ob = st.obligations[0]
    for d in (date(2026, 4, 10), date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 19)):
        assert components.target_at(CTX, st, ob, d).value <= usd("3000.00")  # S09-INV-08
    assert components.target_at(CTX, st, ob, date(2026, 6, 20)).value == usd("5000.00")
    # At 31 May the hold is open: the held amount is awaiting trigger 9,000.00 and nothing is
    # scheduled (S09-R-44, S09-R-45; the measures themselves are ENC-10).
    at = components.target_at(CTX, st, ob, date(2026, 5, 31))
    assert at.hold is not None and at.hold.interval.released is None
    assert at.fixed is not None and at.fixed.segment.a_posted - at.value == usd("9000.00")

    # A contract-level hold freezes every obligation of the contract; an export hold none.
    contract_hold = _hold(2, date(2026, 4, 10), obligation_key=None)
    both = [_ratable(), _ratable(key="POB-02")]
    state, _ = _run(CTX, allocated_state(both, events=[contract_hold]))
    for subject_key in (O1, O2):
        assert targets_by_period(state, subject_key)["FY2026-P08"] == usd("3000.00")
    export_hold = _hold(2, date(2026, 4, 10), hold_type="journal_export")
    state, _ = _run(CTX, allocated_state([_ratable()], events=[export_hold]))
    assert targets_by_period(state, O1)["FY2026-P08"] == usd("8000.00")


def test_s09_r43_hold_never_defers_a_reversal() -> None:
    hold = _hold(2, date(2026, 4, 10))
    tp_change = _estimate(3, date(2026, 4, 30), "VC-1")

    def held(x_exact: int, reduced: int | None) -> dict[str, int]:
        segments = [segment(Fraction(x_exact), x_exact * 100, start=YEAR_START, end=YEAR_END)]
        events = [hold]
        pins = None
        if reduced is not None:
            segments.append(_revised(reduced, date(2026, 4, 30), tp_change, SegmentCause.TP_CHANGE))
            events.append(tp_change)
            pins = _pins((tp_change, "VC-1", "VARIABLE_CONSIDERATION"))
        ob = obligation("POB-01", segments, convention="MONTHLY_EVEN")
        state, _ = _run(CTX, allocated_state([ob], events=events, estimates=pins))
        return targets_by_period(state, O1)

    # A ≥ 0: frozen at L = 3,000.00, but a price reduction to 2,400.00 is recognised when it
    # occurs: min(C(t), L) = 800.00 in April.
    assert _periods(held(12000, None), (4, 8)) == [usd("3000.00"), usd("3000.00")]
    assert _periods(held(12000, 2400), (4, 5)) == [usd("800.00"), usd("1000.00")]
    # A < 0: max(C(t), L) holds the target at (3,000.00), and a reduction towards 0 passes.
    assert _periods(held(-12000, None), (4, 8)) == [usd("-3000.00"), usd("-3000.00")]
    assert _periods(held(-12000, -2400), (4, 5)) == [usd("-800.00"), usd("-1000.00")]
