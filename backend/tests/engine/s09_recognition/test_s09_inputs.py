"""Stage 09 input measures: cost to cost with EAC, uninstalled materials, waste, labour hours and
cost recovery (ENC-5).

ENGINE_SPEC_B §9.2.5 (S09-R-14 to S09-R-17), §9.2.10 (S09-R-35, S09-R-36), §9.3 S09-INV-10, §9.4
``NON_FINITE_AMOUNT``, §9.5, §9.7 EX-09-B and EX-09-C; ENGINE_SPEC S06-R-15 (the updated EAC of a
class N segment), S08-R-02 (a measure-only ``EAC`` version adds no segment); POLICIES POL-091; 04
T-CON-13 ``uninstalled_materials_cost``; D-76 (revenue equal to cost, no ``COST_OF_REVENUE`` line);
03 REQ-REC-007, REQ-REC-008. The ``AllocatedState`` and the stage 06 ``catch_up@<event key>`` node
are built against the documented contract (support.recognition). Every trace re-evaluates node for
node (DG-ENG-04). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EstimateVersionInput
from erev_engine.formulas import FORMULAS
from erev_engine.money import format_exact
from erev_engine.stages import STAGES
from erev_engine.stages.s09_recognition import RecognitionState, eac_version_at, input_progress, run
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
EAC_KEY = f"{CONTRACT_KEY}/EAC-01"
CTX = book_context()
START, END = date(2026, 1, 1), date(2027, 12, 31)
COST_TO_COST = "rec.progress.cost_to_cost.v1"
LABOUR_HOURS = "rec.progress.labour_hours.v1"
COST_RECOVERY = "rec.progress.cost_recovery.v1"
UNINSTALLED = "rec.uninstalled_materials.v1"


def _run(ctx: BookContext, st: AllocatedState) -> tuple[RecognitionState, Trace]:
    """Run stage 09; the trace re-evaluates and every node formula is declared by ``STAGES``."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)  # the stage 06 nodes stage 09 cites (S09-R-36)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    spec = next(item for item in STAGES if item.stage == "09")
    assert {node.formula_id for node in trace.nodes} <= set(spec.formula_ids)
    for measures in state.obligation_measures.values():  # S09-INV-03; 04 DB-17
        assert measures.allocated_amount == (
            measures.revenue_cum + measures.scheduled_amount + measures.awaiting_trigger_amount
        )
    return state, trace


def _node(trace: Trace, measure: str, subject: str, period: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == f"{measure}:{subject}:{period}")


def _causes(state: RecognitionState, subject: str, period: str) -> dict[str, int]:
    return {
        target.cause: target.value
        for target in state.revenue_by_cause
        if target.subject_key == subject and target.period_key == period and target.cause
    }


def _c2c(
    x: str,
    *,
    method: str = "COST_TO_COST",
    segments: Sequence[object] | None = None,
) -> ObligationState:
    first = segment(Fraction(x), usd(f"{x}.00"), start=START, end=END, measure=method)
    return obligation("POB-01", [first, *(segments or ())], method=method, convention=None)


def _eac(
    number: int,
    effective: date,
    *,
    total: str | None = None,
    hours: str | None = None,
    parameters: Mapping[str, object] | None = None,
) -> EstimateVersionInput:
    version = estimate_version(EAC_KEY, "EAC", number, effective, obligation_key="POB-01")
    return dataclasses.replace(
        version,
        expected_total_amount=None if total is None else Decimal(total),
        expected_quantity=None if hours is None else Decimal(hours),
        parameters={} if parameters is None else dict(parameters),
    )


def _estimate_event(stream: int, version: EstimateVersionInput) -> EventView:
    payload = {"estimate_version_id": version.version_key}
    return event_view(CONTRACT_KEY, stream, "ESTIMATE_CHANGED", version.effective_date, payload)


def _cost(stream: int, when: date, amount: str, **flags: bool) -> EventView:
    payload: dict[str, object] = {
        "obligation_key": "POB-01",
        "purpose": "PROGRESS_INPUT",
        "amount": Decimal(amount),
        **flags,
    }
    return event_view(
        CONTRACT_KEY, stream, "COST_INCURRED", when, payload, obligation_keys=["POB-01"]
    )


def _hours(stream: int, when: date, hours: str, ratio: str) -> EventView:
    payload = {
        "obligation_key": "POB-01",
        "measure": "LABOUR_HOURS",
        "cumulative_progress_ratio": Decimal(ratio),
        "hours_to_date": Decimal(hours),
    }
    return event_view(
        CONTRACT_KEY, stream, "PROGRESS_RECORDED", when, payload, obligation_keys=["POB-01"]
    )


def _pins(*pairs: tuple[EstimateVersionInput, EventView]) -> EstimatePins:
    return EstimatePins({EAC_KEY: tuple(EstimatePin(v, ev.order_key) for v, ev in pairs)})


# --- EX-09-B: cost to cost with a modification, progress and an EAC change (CHK-027) -------------


def _ex_09_b(*, correction: bool = False) -> AllocatedState:
    """TP 1,000,000.00, EAC 700,000.00, costs 420,000.00 at 31 Aug 2026; the 10 Sep amendment
    (class N, A′ 1,350,000.00) records EAC 820,000.00 after it; +82,000.00 on 25 Sep; EAC 850,000.00
    effective 30 Sep. ``correction`` adds the J-14 cost of 20,500.00 effective 29 Sep."""
    d = date(2026, 9, 10)
    v1 = _eac(1, START, total="700000.00")
    v2 = _eac(2, d, total="820000.00")
    v3 = _eac(3, date(2026, 9, 30), total="850000.00")
    amend = event_view(CONTRACT_KEY, 5, "CONTRACT_AMENDED", d, {})
    e1, e2, e3 = _estimate_event(3, v1), _estimate_event(6, v2), _estimate_event(8, v3)
    modified = segment(
        Fraction(1350000),
        usd("1350000.00"),
        start=START,
        end=END,
        effective=d,
        basis="INCEPTION",
        cause=SegmentCause.MODIFICATION,
        event_key=amend.event_key,
        measure="COST_TO_COST",
    )
    ob = _c2c("1000000", segments=[modified])
    events = [e1, _cost(4, date(2026, 8, 31), "420000.00"), amend, e2]
    events.append(_cost(7, date(2026, 9, 25), "82000.00"))
    events.append(e3)
    if correction:
        events.append(_cost(9, date(2026, 9, 29), "20500.00"))
    return allocated_state([ob], events=events, estimates=_pins((v1, e1), (v2, e2), (v3, e3)))


def test_ex_09_b_cost_to_cost_modification_and_eac_change() -> None:
    state, trace = _run(CTX, _ex_09_b())
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P08"], targets["FY2026-P09"]) == (usd("600000.00"), usd("797294.12"))
    assert period_amounts(targets)["FY2026-P09"] == usd("197294.12")
    # S09-R-35, S09-R-36: the class N segment reads the updated EAC (S06-R-15), so the amendment's
    # cited node carries 91,463.41; the +82,000.00 is NORMAL 135,000.00; EAC v3 is a CATCH_UP;
    # the v2 version recorded after the amendment moves nothing.
    assert _causes(state, O1, "FY2026-P09") == {
        "MODIFICATION": usd("91463.41"),
        "NORMAL": usd("135000.00"),
        "CATCH_UP": usd("-29169.29"),
    }
    exact = next(
        t.exact
        for t in state.revenue_targets
        if t.subject_key == O1 and t.period_key == "FY2026-P09"
    )
    assert exact == Fraction(1350000 * 502000, 850000)
    assert format_exact(exact, 6) == "797294.117647"
    measures = state.obligation_measures[O1]
    assert measures.catch_up_modification_cum == usd("91463.41")
    assert measures.catch_up_estimate_cum == usd("-29169.29")
    assert measures.catch_up_cum == usd("62294.12")
    assert measures.progress_ratio == Fraction(502000, 850000)
    node = _node(trace, "progress_ratio", O1, "FY2026-P09")
    assert node.formula_id == COST_TO_COST
    assert (node.params["costs"], node.params["eac"], node.params["uninstalled_expected"]) == (
        "502000",
        "850000",
        "0",
    )
    assert node.params["eac_version"] == f"{EAC_KEY}@v3"
    cause = _node(trace, "revenue_by_cause", f"{O1}/CATCH_UP", "FY2026-P09")
    assert cause.value == "-29169.29"
    # S09-R-36: the exact catch-up is E_after(d) − E_before(d) and the residue exact − posted.
    catch_up = Fraction(1350000 * 502000, 850000) - Fraction(1350000 * 502000, 820000)
    estimate_cum = _node(trace, "catch_up_estimate_cum", O1, "-")
    assert estimate_cum.value == "-29169.29"
    assert estimate_cum.rounding_residue == format_exact(catch_up + Fraction(2916929, 100), 18)


def test_ex_09_b_j14_correction_replay() -> None:
    state, _ = _run(CTX, _ex_09_b(correction=True))
    targets = targets_by_period(state, O1)
    assert targets["FY2026-P09"] == usd("829852.94")
    assert period_amounts(targets)["FY2026-P09"] == usd("229852.94")
    # The replay inserts the 29 Sep cost before the 30 Sep EAC change: NORMAL +33,750.00
    # (C 860,213.41) then CATCH_UP (30,360.47) (C 829,852.94).
    assert _causes(state, O1, "FY2026-P09") == {
        "MODIFICATION": usd("91463.41"),
        "NORMAL": usd("168750.00"),
        "CATCH_UP": usd("-30360.47"),
    }
    assert state.obligation_measures[O1].catch_up_estimate_cum == usd("-30360.47")


def test_s06_r15_updated_eac_read_from_the_class_n_boundary() -> None:
    """The version effective at the modification date counts from the boundary on, whatever the
    position of its ``ESTIMATE_CHANGED`` event; before the boundary the pin before it applies."""
    st = _ex_09_b()
    ob = st.obligations[0]
    amend = next(ev for ev in st.events if ev.event_type == "CONTRACT_AMENDED")
    before, after = ob.segments
    pinned_before = eac_version_at(st, ob, before, amend.effective_date, event=amend)
    pinned_after = eac_version_at(st, ob, after, amend.effective_date, event=amend, inclusive=True)
    assert (pinned_before.version_no, pinned_after.version_no) == (1, 2)
    assert input_progress(st, ob, before, amend.effective_date, event=amend) == Fraction(420, 700)
    assert input_progress(
        st, ob, after, amend.effective_date, event=amend, inclusive=True
    ) == Fraction(420, 820)


# --- EX-09-C: uninstalled materials and waste (S5-EX19, S5-PROGRESS-VARIANTS; D-76) --------------


def _ex_09_c(*, parameter: bool) -> AllocatedState:
    """X 5,000,000.00; EAC 4,000,000.00 including elevators of 1,500,000.00; other costs 500,000.00
    on 30 Nov; the elevators arrive, controlled by the customer, on 15 Dec."""
    parameters = {"uninstalled_materials_cost": "1500000.00"} if parameter else None
    v1 = _eac(1, START, total="4000000.00", parameters=parameters)
    e1 = _estimate_event(3, v1)
    events = [
        e1,
        _cost(4, date(2026, 11, 30), "500000.00"),
        _cost(5, date(2026, 12, 15), "1500000.00", is_uninstalled_material=True),
    ]
    return allocated_state([_c2c("5000000")], events=events, estimates=_pins((v1, e1)))


def test_ex_09_c_uninstalled_materials() -> None:
    state, trace = _run(CTX, _ex_09_c(parameter=True))
    targets = targets_by_period(state, O1)
    # f = 500,000 ÷ 2,500,000 = 1/5; E = 1/5 × 3,500,000 + 1,500,000; 700,000.00 before the
    # elevators arrive.
    assert (targets["FY2026-P11"], targets["FY2026-P12"]) == (usd("700000.00"), usd("2200000.00"))
    for period in ("FY2026-P11", "FY2026-P12"):
        ratio = _node(trace, "progress_ratio", O1, period)
        assert (ratio.formula_id, ratio.value) == (COST_TO_COST, "0.2")
        assert (ratio.params["costs"], ratio.params["uninstalled_expected"]) == (
            "500000",
            "1500000",
        )
    exact = _node(trace, "revenue_target_exact", f"{O1}#FIXED", "FY2026-P12")
    assert (exact.formula_id, exact.value) == (UNINSTALLED, "2200000")
    assert (exact.params["uninstalled_incurred"], exact.params["x_exact"]) == ("1500000", "5000000")
    measures = state.obligation_measures[O1]
    assert measures.progress_ratio == Fraction(1, 5)  # T-CON-11 holds the margin-bearing progress
    assert measures.remaining_allocation == usd("2800000.00")
    # D-76: revenue equal to cost and nothing else; stage 09 produces no COST_OF_REVENUE target.
    assert {target.measure for target in state.revenue_targets} == {"revenue_cum"}
    assert {str(line.schedule_kind) for line in state.schedule_lines} == {"REVENUE"}
    assert state.findings == ()


def test_ex_09_c_uninstalled_materials_without_the_parameter() -> None:
    # S09-R-14: absent the EAC parameter, the expected materials are those incurred to date, so the
    # November denominator is the whole EAC (f = 1/8) and December agrees with EX-09-C.
    state, _ = _run(CTX, _ex_09_c(parameter=False))
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P11"], targets["FY2026-P12"]) == (usd("625000.00"), usd("2200000.00"))


def test_ex_09_c_waste() -> None:
    v1 = _eac(1, START, total="800000.00")
    e1 = _estimate_event(3, v1)
    events = [
        e1,
        _cost(4, date(2026, 6, 30), "300000.00"),
        _cost(5, date(2026, 6, 30), "50000.00", is_wasted=True),
    ]
    state, trace = _run(
        CTX, allocated_state([_c2c("1000000")], events=events, estimates=_pins((v1, e1)))
    )
    assert targets_by_period(state, O1)["FY2026-P06"] == usd("375000.00")
    node = _node(trace, "progress_ratio", O1, "FY2026-P06")
    assert (node.value, node.params["costs"], node.params["wasted"]) == ("0.375", "300000", "50000")
    assert state.obligation_measures[O1].progress_ratio == Fraction(3, 8)


# --- S09-R-15: labour hours (REQ-REC-008) --------------------------------------------------------


def test_s09_r15_labour_hours() -> None:
    v1, v2 = _eac(1, START, hours="600"), _eac(2, date(2026, 2, 28), hours="650")
    e1, e2 = _estimate_event(3, v1), _estimate_event(5, v2)
    events = [e1, _hours(4, date(2026, 1, 31), "150", "0.25"), e2]
    events.append(_hours(6, date(2026, 2, 28), "450", "0.692307692307692308"))
    ob = _c2c("120000", method="LABOUR_HOURS")
    state, trace = _run(
        CTX, allocated_state([ob], events=events, estimates=_pins((v1, e1), (v2, e2)))
    )
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P01"], targets["FY2026-P02"]) == (usd("30000.00"), usd("83076.92"))
    node = _node(trace, "progress_ratio", O1, "FY2026-P01")
    assert (node.formula_id, node.params["hours"], node.params["expected_hours"]) == (
        LABOUR_HOURS,
        "150",
        "600",
    )
    # The 28 Feb version precedes the 28 Feb hours in ENG-06 order: CATCH_UP 150 ÷ 650 − 150 ÷ 600.
    assert _causes(state, O1, "FY2026-P02") == {
        "CATCH_UP": usd("-2307.69"),
        "NORMAL": usd("55384.61"),
    }
    assert state.obligation_measures[O1].progress_ratio == Fraction(450, 650)


def test_s09_r15_hours_without_expected_hours_are_non_finite() -> None:
    v1 = _eac(1, START)  # a pin without expected_quantity
    e1 = _estimate_event(3, v1)
    ob = _c2c("120000", method="LABOUR_HOURS")
    events = [e1, _hours(4, date(2026, 1, 31), "150", "0.25")]
    state, trace = _run(CTX, allocated_state([ob], events=events, estimates=_pins((v1, e1))))
    assert targets_by_period(state, O1)["FY2026-P01"] == 0
    codes = {(f.code, f.severity, f.detail["reason"], f.detail["rule"]) for f in state.findings}
    assert codes == {("NON_FINITE_AMOUNT", "ERROR", "EXPECTED_HOURS_MISSING", "S09-R-15")}
    node = _node(trace, "progress_ratio", O1, "FY2026-P01")
    assert (node.value, node.params["reason"]) == ("0", "EXPECTED_HOURS_MISSING")


# --- S09-R-16: cost recovery until the first EAC pin (606-10-25-37) ------------------------------


def test_s09_r16_cost_recovery_until_eac() -> None:
    v1 = _eac(1, date(2026, 9, 30), total="400000.00")
    e1 = _estimate_event(4, v1)
    ob = _c2c("600000", method="COST_RECOVERY")
    events = [_cost(3, date(2026, 6, 30), "100000.00"), e1]
    state, trace = _run(CTX, allocated_state([ob], events=events, estimates=_pins((v1, e1))))
    targets = targets_by_period(state, O1)
    # Until the pin: E = min(X, costs) = 100,000.00; from 30 Sep: cost to cost 600,000 × 100 ÷ 400.
    assert (targets["FY2026-P06"], targets["FY2026-P08"], targets["FY2026-P09"]) == (
        usd("100000.00"),
        usd("100000.00"),
        usd("150000.00"),
    )
    june = _node(trace, "progress_ratio", O1, "FY2026-P06")
    assert (june.formula_id, june.value, june.params["costs"], june.params["x_exact"]) == (
        COST_RECOVERY,
        "0.166666666666666667",
        "100000",
        "600000",
    )
    september = _node(trace, "progress_ratio", O1, "FY2026-P09")
    assert (september.formula_id, september.params["measure"]) == (COST_TO_COST, "COST_RECOVERY")
    assert _causes(state, O1, "FY2026-P09") == {"CATCH_UP": usd("50000.00")}
    assert state.obligation_measures[O1].catch_up_estimate_cum == usd("50000.00")


def test_s09_r16_cost_recovery_never_exceeds_the_allocation() -> None:
    ob = _c2c("600000", method="COST_RECOVERY")
    state, _ = _run(CTX, allocated_state([ob], events=[_cost(3, date(2026, 6, 30), "700000.00")]))
    assert targets_by_period(state, O1)["FY2026-P06"] == usd("600000.00")
    assert state.obligation_measures[O1].progress_ratio == 1


def test_s09_r16_costs_wait_without_a_pin() -> None:
    # A cost-to-cost obligation with costs and no approved EAC gives f = 0 and no stage 09 finding
    # (stage 11 raises LOSS_EAC_MISSING in 605-35 scope).
    state, trace = _run(
        CTX, allocated_state([_c2c("1000000")], events=[_cost(3, date(2026, 6, 30), "100000.00")])
    )
    assert targets_by_period(state, O1)["FY2026-P06"] == 0
    assert state.findings == ()
    node = _node(trace, "progress_ratio", O1, "FY2026-P06")
    assert (node.value, node.params["reason"]) == ("0", "EAC_PIN_MISSING")


# --- S09-INV-10 and S09-R-17: progress stays within [0, 1] ---------------------------------------


def test_s09_inv_10_progress_bounded() -> None:
    v1 = _eac(1, START, total="800000.00")
    e1 = _estimate_event(3, v1)
    events = [e1, _cost(4, date(2026, 6, 30), "900000.00")]  # costs exceed the EAC (S09-R-17)
    state, trace = _run(
        CTX, allocated_state([_c2c("1000000")], events=events, estimates=_pins((v1, e1)))
    )
    assert targets_by_period(state, O1)["FY2026-P06"] == usd("1000000.00")
    node = _node(trace, "progress_ratio", O1, "FY2026-P06")
    assert node.value == "1"
    measures = state.obligation_measures[O1]
    assert (measures.progress_ratio, str(measures.satisfaction_status)) == (1, "SATISFIED")
    assert state.findings == ()


def test_s09_r14_eac_net_of_materials_not_positive_is_non_finite() -> None:
    parameters = {"uninstalled_materials_cost": "800000.00"}  # the whole EAC is materials
    v1 = _eac(1, START, total="800000.00", parameters=parameters)
    e1 = _estimate_event(3, v1)
    events = [e1, _cost(4, date(2026, 6, 30), "100000.00")]
    state, trace = _run(
        CTX, allocated_state([_c2c("1000000")], events=events, estimates=_pins((v1, e1)))
    )
    assert targets_by_period(state, O1)["FY2026-P06"] == 0
    codes = {(f.code, f.severity, f.detail["reason"]) for f in state.findings}
    assert codes == {("NON_FINITE_AMOUNT", "ERROR", "EAC_NET_OF_MATERIALS_NOT_POSITIVE")}
    node = _node(trace, "progress_ratio", O1, "FY2026-P06")
    assert (node.value, node.params["reason"]) == ("0", "EAC_NET_OF_MATERIALS_NOT_POSITIVE")


# --- Registered formulas (DG-KRN-EXP-04) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("formula_id", "params", "expected"),
    [
        (
            COST_TO_COST,
            {"costs": "502000", "eac": "850000", "uninstalled_expected": "0"},
            Fraction(502, 850),
        ),
        (
            COST_TO_COST,
            {"costs": "900000", "eac": "800000", "uninstalled_expected": "0"},
            Fraction(1),
        ),
        (
            COST_TO_COST,
            {
                "costs": "700000",
                "eac": "1000000",
                "uninstalled_expected": "100000",
                "base_costs": "400000",
            },
            Fraction(3, 5),
        ),
        (COST_TO_COST, {"as_of": "2026-06-30", "rule": "S09-R-06"}, Fraction(1)),
        (LABOUR_HOURS, {"hours": "450", "expected_hours": "650"}, Fraction(450, 650)),
        (LABOUR_HOURS, {"hours": "700", "expected_hours": "650"}, Fraction(1)),
        (
            LABOUR_HOURS,
            {"hours": "0", "expected_hours": "0", "reason": "EAC_PIN_MISSING"},
            Fraction(0),
        ),
        (COST_RECOVERY, {"costs": "100000", "x_exact": "600000"}, Fraction(1, 6)),
        (COST_RECOVERY, {"costs": "700000", "x_exact": "600000"}, Fraction(1)),
        (COST_RECOVERY, {"costs": "100000", "x_exact": "0"}, Fraction(0)),
    ],
)
def test_input_formulas(formula_id: str, params: dict[str, str], expected: Fraction) -> None:
    assert FORMULAS[formula_id]((), params) == expected


def test_uninstalled_materials_formula() -> None:
    inception = {
        "progress": "1/5",
        "x_exact": "5000000",
        "uninstalled_expected": "1500000",
        "uninstalled_incurred": "1500000",
    }
    assert FORMULAS[UNINSTALLED]((Fraction(1, 5),), inception) == Fraction(2200000)
    prospective = {
        **inception,
        "progress": "1/2",
        "base_revenue_exact": "2200000",
        "base_uninstalled": "1500000",
    }
    # E = b_k + g × (X − b_k − (UM_exp − UM_k)) + (UM_inc − UM_k) = 2,200,000 + 1/2 × 2,800,000
    assert FORMULAS[UNINSTALLED]((Fraction(1, 2),), prospective) == Fraction(3600000)
    with pytest.raises(ValueError, match="EAC net of materials"):
        FORMULAS[COST_TO_COST]((), {"costs": "1", "eac": "10", "uninstalled_expected": "10"})
    with pytest.raises(ValueError, match="disagrees"):
        FORMULAS[UNINSTALLED]((Fraction(1, 4),), inception)


# --- Independent review findings (PRODUCTION-C1-INDEPENDENT-REVIEW-20260919): boundaries ---------


def _amendment(stream: int, when: date) -> EventView:
    return event_view(CONTRACT_KEY, stream, "CONTRACT_AMENDED", when, {})


def test_s06_boundary_measure_carries_the_uninstalled_materials() -> None:
    """Finding (1): stage 06 measures a cost-to-cost boundary with the full recognition target of
    S09-R-14 (margin progress × (X − UM_exp) + UM_inc), not X × f, so a later class D base or pool
    starts from the revenue stage 09 recognised (S06-R-17; S06-INV-02)."""
    from erev_engine.stages.s06_modifications import segments as s06_segments
    from erev_engine.stages.s09_recognition import target_at_position

    st = _ex_09_c(parameter=True)
    amend = _amendment(6, date(2026, 12, 31))
    st = dataclasses.replace(st, events=(*st.events, amend))
    ob = st.obligations[0]
    seg = ob.segments[0]
    measured = s06_segments.measure(CTX, st, ob, seg, amend)
    before = target_at_position(CTX, st, ob, amend.effective_date, event=amend, inclusive=False)
    assert measured.progress == Fraction(1, 5)  # the S09-R-14 margin-bearing definition of f
    assert (measured.exact, measured.posted, measured.complete) == (
        Fraction(2200000),
        usd("2200000.00"),
        False,
    )
    assert (before.fixed_exact, before.fixed_posted) == (measured.exact, measured.posted)


def _opening(method: str, *, pin: bool) -> AllocatedState:
    """X 1,000.00 with an imported baseline of 200.00 at the 30 Jun 2026 cutover (S09-R-07); a
    pre-cutover cost of 200.00 on 31 Mar stays in the stream; a new cost of 100.00 on 30 Sep."""
    cutover = date(2026, 6, 30)
    opening = event_view(CONTRACT_KEY, 5, "OPENING_BALANCE_ESTABLISHED", cutover, {})
    imported = segment(
        Fraction(1000),
        usd("1000.00"),
        start=cutover + timedelta(days=1),
        end=END,
        effective=cutover,
        basis="PROSPECTIVE",
        cause=SegmentCause.OPENING_BALANCE,
        event_key=opening.event_key,
        base_revenue_posted=usd("200.00"),
        base_revenue_exact=Fraction(200),
        measure=method,
    )
    ob = _c2c("1000", method=method, segments=[imported])
    events = [_cost(4, date(2026, 3, 31), "200.00"), opening, _cost(6, date(2026, 9, 30), "100.00")]
    estimates = None
    if pin:
        v1 = _eac(1, START, total="800.00")
        e1 = _estimate_event(3, v1)
        events.insert(0, e1)
        estimates = _pins((v1, e1))
    return allocated_state([ob], events=events, estimates=estimates)


def test_s09_r07_opening_balance_cost_to_cost_keeps_the_baseline_before_the_cutover() -> None:
    """Finding (2): before the cutover the opening segment applies with progress 0, so every target
    equals the imported baseline even where the pre-cutover costs in the stream exceed the costs
    at an earlier date (no NON_FINITE_AMOUNT); after it g = (K − K_k) ÷ (EAC − UM_exp − K_k) over
    the remaining allocation (CV-62; §9.2.5)."""
    state, trace = _run(CTX, _opening("COST_TO_COST", pin=True))
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P02"], targets["FY2026-P03"], targets["FY2026-P06"]) == (
        usd("200.00"),
        usd("200.00"),
        usd("200.00"),
    )
    # 200.00 + 800.00 × (300 − 200) ÷ (800 − 200) = 333.33
    assert targets["FY2026-P09"] == usd("333.33")
    assert state.findings == ()
    september = _node(trace, "progress_ratio", O1, "FY2026-P09")
    assert (september.params["costs"], september.params["base_costs"], september.value) == (
        "300",
        "200",
        "0.166666666666666667",
    )
    assert _node(trace, "progress_ratio", O1, "FY2026-P02").value == "0"


def test_s09_r16_cost_recovery_since_an_opening_balance() -> None:
    """Finding (3): cost recovery since a boundary recognises the costs incurred since it over the
    remaining allocation, so the imported baseline is not counted twice: 200.00 at the cutover and
    300.00 after a further 100.00 of cost (606-10-25-37; S09-R-16; CV-62)."""
    state, trace = _run(CTX, _opening("COST_RECOVERY", pin=False))
    targets = targets_by_period(state, O1)
    assert (targets["FY2026-P02"], targets["FY2026-P06"], targets["FY2026-P09"]) == (
        usd("200.00"),
        usd("200.00"),
        usd("300.00"),
    )
    september = _node(trace, "progress_ratio", O1, "FY2026-P09")
    assert (september.formula_id, september.value) == (COST_RECOVERY, "0.125")
    assert (september.params["costs"], september.params["base_costs"]) == ("300", "200")
    assert _causes(state, O1, "FY2026-P09") == {"NORMAL": usd("100.00")}
