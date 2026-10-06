"""Stage 09: the deterministic component, ONE predicate (ENC-10; item ENG-USAGE-FIXED-SCHEDULE-1).

ENGINE_SPEC_B S09-R-45, S09-R-49 and S09-R-50 rev 1.126 (supervisor ruling R-116 (a); candidate
AD-61 for the independent accountant): a ``FIXED`` component measured by time elapsed that carries
an allocation is deterministic — a ``TIME_ELAPSED`` obligation as before, the stand-ready fee or
minimum of a ``USAGE`` obligation and the guarantee of a right-to-access ``ROYALTY`` licence; a
``RIGHT_TO_INVOICE`` obligation never. Until that revision the predicate was the method
``TIME_ELAPSED`` alone: the fixed fee of a usage obligation was called awaiting trigger though no
event moves it, and its schedule ended at the evaluation horizon.

The ``AllocatedState`` is built against the documented contract (support.recognition). Every
obligation runs over calendar 2026 under ``MONTHLY_EVEN`` (1,000.00 a month of 12,000.00), with the
horizon at June, so that what is projected lies in July to December.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import MaterialRightInput
from erev_engine.enums import RecognitionMethod
from erev_engine.errors import EngineError
from erev_engine.stages import STAGES
from erev_engine.stages.s09_recognition import (
    RecognitionState,
    components,
    is_deterministic,
    progress_time,
    run,
    schedule,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    EventView,
    MaterialRightTerms,
    ObligationState,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    targets_by_period,
    usd,
)

O1 = f"{CONTRACT_KEY}/POB-01"
START, END = date(2026, 1, 1), date(2026, 12, 31)
MARCH_31 = date(2026, 3, 31)
MONTHLY_EVEN = ("recognition.time_convention", "ENTITY", "US01", "MONTHLY_EVEN")
CTX = book_context(horizon="FY2026-P06", overrides=[MONTHLY_EVEN])
MONTHS = [f"FY2026-P{month:02d}" for month in range(1, 13)]
OPEN = MONTHS[:6]
# The formulas of time-elapsed progress (§9.2.3): what "measured by time elapsed" means in code.
TIME_FORMULAS = {*progress_time.TIME_FORMULAS.values(), progress_time.PROSPECTIVE_FORMULA}


def _run(st: AllocatedState) -> tuple[RecognitionState, Trace]:
    """Stage 09; the trace re-evaluates, every formula is declared and S09-INV-03 holds."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, CTX, st)
    state = run(CTX, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    spec = next(item for item in STAGES if item.stage == "09")
    assert {node.formula_id for node in trace.nodes} <= set(spec.formula_ids)
    for measures in state.obligation_measures.values():
        assert measures.allocated_amount == (
            measures.revenue_cum + measures.scheduled_amount + measures.awaiting_trigger_amount
        )
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _fixed(amount: int, measure: str) -> AllocationSegment:
    return segment(Fraction(amount), usd(f"{amount}.00"), start=START, end=END, measure=measure)


def _marker(component: str, measure: str) -> AllocationSegment:
    return segment(Fraction(0), 0, start=START, end=END, component=component, measure=measure)


def _usage(fee: int = 12000, *, fees: bool = True) -> ObligationState:
    """A usage obligation: a fixed fee of ``fee`` and, with ``fees``, the ``PERIOD_VC`` component
    of POL-240 ``DERIVED`` (without it, the PT-01 shape of S09-R-20: the ``FIXED`` component
    alone)."""
    segments = [_fixed(fee, "USAGE")]
    if fees:
        segments.append(_marker("PERIOD_VC", "USAGE"))
    return obligation("POB-01", segments, method="USAGE", convention=None)


def _royalty(pattern: str) -> ObligationState:
    """A licence of method ``ROYALTY`` with a guarantee of 12,000.00 (S09-R-33): a right to access
    (``OVER_TIME``) or a right to use (``POINT_IN_TIME``)."""
    return obligation(
        "POB-01",
        [_fixed(12000, "ROYALTY"), _marker("ROYALTY", "ROYALTY")],
        method="ROYALTY",
        convention=None,
        pattern=pattern,
        kind="LICENCE",
    )


def _right_to_invoice(stated: int, allocation: int) -> ObligationState:
    """A right-to-invoice line with stated price ``stated`` whose ``FIXED`` segment holds
    ``allocation``: P > 0 (S09-R-18), or a rate line, P = 0."""
    ob = obligation(
        "POB-01",
        [_fixed(allocation, "RIGHT_TO_INVOICE"), _marker("PERIOD_VC", "RIGHT_TO_INVOICE")],
        method="RIGHT_TO_INVOICE",
        convention=None,
    )
    return dataclasses.replace(
        ob, stated_price=Fraction(stated), original_stated_price=Fraction(stated)
    )


def _usage_report(version: int, when: date, start: date, rated: str) -> EventView:
    payload = {
        "obligation_key": "POB-01",
        "usage_period_start": start,
        "usage_period_end": when,
        "metric": "API_CALLS",
        "quantity": Decimal("3000"),
        "rated_amount": Decimal(rated),
    }
    return event_view(
        CONTRACT_KEY, version, "USAGE_REPORTED", when, payload, obligation_keys=["POB-01"]
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


def _split(state: RecognitionState) -> tuple[int, int, int, int]:
    """(allocated, revenue, scheduled, awaiting trigger) of the one obligation at d_v."""
    m = state.obligation_measures[O1]
    return m.allocated_amount, m.revenue_cum, m.scheduled_amount, m.awaiting_trigger_amount


def _pattern(trace: Trace) -> tuple[str, str]:
    node = _node(trace, f"scheduled_amount:{O1}:-")
    return node.params["pattern"], node.params["held"]


def _lines(state: RecognitionState) -> dict[str, tuple[int, bool]]:
    """Period → (amount, ``is_released_at_close``) of the obligation's ``NORMAL`` lines."""
    return {
        line.period_key: (line.amount, line.is_released_at_close)
        for line in state.schedule_lines
        if line.subject_key == O1 and str(line.line_type) == "NORMAL"
    }


def test_s09_r45_the_fixed_fee_of_a_usage_obligation_is_scheduled() -> None:
    # 12,000.00 by time and a usage fee of 150.00 for March, reported on 31 March: the version
    # date. Three months are earned; the nine that remain depend on no event.
    report = _usage_report(2, MARCH_31, date(2026, 3, 1), "150.00")
    state, trace = _run(allocated_state([_usage()], events=[report]))
    assert state.obligation_measures[O1].as_of == MARCH_31
    assert _split(state) == (usd("12150.00"), usd("3150.00"), usd("9000.00"), 0)
    assert _pattern(trace) == ("DETERMINISTIC", "false")
    assert _node(trace, f"scheduled_amount:{O1}:-").value == "9000.00"
    assert _node(trace, f"awaiting_trigger_amount:{O1}:-").value == "0.00"

    # The PT-01 shape (S09-R-20): the FIXED component alone, at the inception.
    state, trace = _run(allocated_state([_usage(fees=False)]))
    assert _split(state) == (usd("12000.00"), 0, usd("12000.00"), 0)
    assert _pattern(trace) == ("DETERMINISTIC", "false")

    # Without an allocation nothing is scheduled and the obligation is event-driven, as before:
    # its fees are realised when they are reported.
    state, trace = _run(allocated_state([_usage(0)], events=[report]))
    assert _split(state) == (usd("150.00"), usd("150.00"), 0, 0)
    assert _pattern(trace) == ("EVENT_DRIVEN", "false")

    # S09-R-44: under a recognition hold the fixed fee awaits its release, as a time-elapsed
    # obligation's does. The hold of 10 April freezes the three months earned before it.
    state, trace = _run(allocated_state([_usage()], events=[_hold(2, date(2026, 4, 10))]))
    assert _split(state) == (usd("12000.00"), usd("3000.00"), 0, usd("9000.00"))
    assert _pattern(trace) == ("DETERMINISTIC", "true")


def test_s09_r45_the_guarantee_of_a_right_to_access_royalty_is_scheduled() -> None:
    state, trace = _run(allocated_state([_royalty("OVER_TIME")]))
    assert _split(state) == (usd("12000.00"), 0, usd("12000.00"), 0)
    assert _pattern(trace) == ("DETERMINISTIC", "false")

    # A right to use transfers at a point in time (POL-024): its guarantee awaits that transfer.
    state, trace = _run(allocated_state([_royalty("POINT_IN_TIME")]))
    assert _split(state) == (usd("12000.00"), 0, 0, usd("12000.00"))
    assert _pattern(trace) == ("EVENT_DRIVEN", "false")


def test_s09_r45_a_right_to_invoice_obligation_is_never_deterministic() -> None:
    # P > 0: the FIXED component is measured by the right to invoice (S09-R-18).
    state, trace = _run(allocated_state([_right_to_invoice(3000, 3000)]))
    assert _split(state) == (usd("3000.00"), 0, 0, usd("3000.00"))
    assert _pattern(trace) == ("EVENT_DRIVEN", "false")

    # A rate line (P = 0) that holds an allocation is measured by the completion signal of its
    # term — time — and stays event-driven all the same (R-116 (a): "not RIGHT_TO_INVOICE"): its
    # schedule ends with the horizon.
    state, trace = _run(allocated_state([_right_to_invoice(0, 600)]))
    assert _split(state) == (usd("600.00"), 0, 0, usd("600.00"))
    assert _pattern(trace) == ("EVENT_DRIVEN", "false")
    assert sorted(_lines(state)) == OPEN
    assert max(targets_by_period(state, O1)) == "FY2026-P06"


def test_s09_r49_the_months_of_a_fixed_fee_are_released_at_close() -> None:
    # The flag marks the NORMAL line of a deterministic component in a period whose realised
    # usage did not move: every month of the fee but March, whose line holds the fee of 150.00.
    report = _usage_report(2, MARCH_31, date(2026, 3, 1), "150.00")
    state, _ = _run(allocated_state([_usage()], events=[report]))
    lines = _lines(state)
    assert sorted(lines) == MONTHS
    assert lines["FY2026-P03"] == (usd("1150.00"), False)
    assert {key: found for key, found in lines.items() if key != "FY2026-P03"} == {
        key: (usd("1000.00"), True) for key in MONTHS if key != "FY2026-P03"
    }
    # A usage obligation without a fixed fee has the line of its fee alone, and it is not flagged.
    state, _ = _run(allocated_state([_usage(0)], events=[report]))
    assert _lines(state) == {"FY2026-P03": (usd("150.00"), False)}


def test_s09_r50_a_deterministic_component_is_projected_to_its_term_end() -> None:
    # The horizon is June. The fixed fee has a line in every month of its term and its target
    # reaches the allocation in December; what lies after June is the fee alone.
    report = _usage_report(2, MARCH_31, date(2026, 3, 1), "150.00")
    state, _ = _run(allocated_state([_usage()], events=[report]))
    targets = targets_by_period(state, O1)
    assert sorted(targets) == MONTHS
    assert (targets["FY2026-P06"], targets["FY2026-P12"]) == (usd("6150.00"), usd("12150.00"))
    assert sum(amount for key, (amount, _) in _lines(state).items() if key > "FY2026-P06") == usd(
        "6000.00"
    )

    # The guarantee of a right to access is projected likewise.
    state, _ = _run(allocated_state([_royalty("OVER_TIME")]))
    assert sorted(_lines(state)) == MONTHS
    assert targets_by_period(state, O1)["FY2026-P12"] == usd("12000.00")

    # Event-driven components end with the horizon: a usage obligation without a fixed fee, the
    # guarantee of a right to use, a right-to-invoice line.
    for ob, events in (
        (_usage(0), [report]),
        (_royalty("POINT_IN_TIME"), []),
        (_right_to_invoice(3000, 3000), []),
    ):
        state, _ = _run(allocated_state([ob], events=events))
        assert sorted(targets_by_period(state, O1)) == OPEN, ob.recognition_method

    # A time-elapsed obligation is deterministic by its method, whatever it holds — as before.
    empty = obligation("POB-01", [_fixed(0, "TIME_ELAPSED")], convention="MONTHLY_EVEN")
    state, trace = _run(allocated_state([empty]))
    assert sorted(targets_by_period(state, O1)) == MONTHS
    assert _pattern(trace) == ("DETERMINISTIC", "false")


# --- the predicate and the dispatch it mirrors ----------------------------------------------------

# (method, satisfaction pattern) of every combination ``components.validate`` accepts and
# ``segment_target`` measures → whether the obligation is deterministic when its FIXED segment
# holds an allocation. A combination that appears here and is not listed, or the reverse, fails
# the walk: a new measure needs its answer.
DETERMINISTIC = {
    ("TIME_ELAPSED", "OVER_TIME"): True,
    ("USAGE", "OVER_TIME"): True,
    ("ROYALTY", "OVER_TIME"): True,
    ("ROYALTY", "POINT_IN_TIME"): False,
    ("RIGHT_TO_INVOICE", "OVER_TIME"): False,
    ("POINT_IN_TIME", "OVER_TIME"): False,
    ("POINT_IN_TIME", "POINT_IN_TIME"): False,
    ("UNITS_DELIVERED", "OVER_TIME"): False,
    ("UNITS_DELIVERED", "POINT_IN_TIME"): False,
    ("OUTPUT_PERCENT", "OVER_TIME"): False,
    ("MILESTONE", "OVER_TIME"): False,
    ("COST_TO_COST", "OVER_TIME"): False,
    ("LABOUR_HOURS", "OVER_TIME"): False,
    ("COST_RECOVERY", "OVER_TIME"): False,
    ("REDEMPTION_PATTERN", "OVER_TIME"): False,
}
LOYALTY_OPTION = MaterialRightTerms(
    terms=MaterialRightInput(
        obligation_key="POB-01",
        option_type="LOYALTY_POINTS",
        incremental_discount_ratio=None,
        is_discount_available_without_contract=False,
        expected_purchase_amount=None,
        currency="USD",
        ssp_method="ENTERED_AMOUNT",
        expiry_date=None,
        likelihood_estimate_key=None,
        is_legacy_quantity_ssp_dollars=False,
    ),
    option_ssp=Fraction(1200),
)


def _measured(
    method: str, pattern: str, *, stated: int = 1200, option: bool = False
) -> tuple[ObligationState, bool] | None:
    """The obligation and whether ``segment_target`` measures its FIXED component by time elapsed;
    None for a combination the engine refuses (T-REF-23) or does not build (S09-R-02)."""
    fixed = _fixed(1200, method)
    ob = obligation(
        "POB-01",
        [fixed],
        method=method,
        convention="MONTHLY_EVEN" if method == "TIME_ELAPSED" else None,
        pattern=pattern,
        criterion="NOT_APPLICABLE" if pattern == "POINT_IN_TIME" else "OT_A",
        kind="LICENCE" if method == "ROYALTY" else "STANDARD",
    )
    ob = dataclasses.replace(ob, stated_price=Fraction(stated))
    if option:
        ob = dataclasses.replace(ob, material_right=LOYALTY_OPTION)
    st = allocated_state([ob])
    try:
        components.validate(ob)
        part = components.segment_target(CTX, st, st.contracts[0], ob, fixed, date(2026, 6, 30))
    except EngineError as error:
        assert dict(error.detail)["rule"] in ("T-REF-23", "S09-R-02"), error.detail
        return None
    return ob, part.progress.formula_id in TIME_FORMULAS


def test_the_predicate_mirrors_the_dispatch_of_segment_target() -> None:
    """S09-R-45 rev 1.126, both ways: with an allocation in its FIXED segment an obligation is
    deterministic exactly when ``segment_target`` measures that segment by time elapsed. Two
    exceptions are named, and no other exists: a right-to-invoice rate line (P = 0), measured by
    the completion signal of its term and never deterministic (R-116 (a)); and a loyalty-points
    option of method ``TIME_ELAPSED``, measured by its redemption pattern and deterministic by its
    method, as before (R-116 (a): "TIME_ELAPSED as today")."""
    assert schedule.is_deterministic is components.is_deterministic is is_deterministic
    walked: dict[tuple[str, str], bool] = {}
    for method in RecognitionMethod:
        for pattern in ("OVER_TIME", "POINT_IN_TIME"):
            found = _measured(method.value, pattern)
            if found is None:
                continue
            ob, by_time = found
            walked[(method.value, pattern)] = is_deterministic(ob)
            if (method.value, pattern) == ("RIGHT_TO_INVOICE", "OVER_TIME"):
                assert not by_time  # P > 0: by the right to invoice
                rate_line, rate_by_time = _measured(method.value, pattern, stated=0) or (ob, False)
                assert (rate_by_time, is_deterministic(rate_line)) == (True, False)
            else:
                assert is_deterministic(ob) == by_time, (method.value, pattern)
    assert walked == DETERMINISTIC

    # "Carries an allocation": without one a usage obligation and a right-to-access royalty are
    # not deterministic; a time-elapsed obligation is, by its method.
    for method, expected in (("USAGE", False), ("ROYALTY", False), ("TIME_ELAPSED", True)):
        ob = obligation(
            "POB-01",
            [_fixed(0, method)],
            method=method,
            convention="MONTHLY_EVEN" if method == "TIME_ELAPSED" else None,
            kind="LICENCE" if method == "ROYALTY" else "STANDARD",
        )
        assert is_deterministic(ob) is expected, method
    # Either half of the allocation is enough: a posted amount alone (what a modification leaves of
    # an allocation it takes away), an exact amount alone (one that rounds to nothing).
    posted_only = dataclasses.replace(_fixed(0, "USAGE"), a_posted=usd("0.01"))
    assert is_deterministic(obligation("POB-01", [posted_only], method="USAGE", convention=None))
    exact_only = dataclasses.replace(_fixed(0, "USAGE"), x_exact=Fraction(1, 300))
    assert is_deterministic(obligation("POB-01", [exact_only], method="USAGE", convention=None))
    # It is the FIXED component's allocation: one of the usage fees alone places nothing by time.
    fees = segment(
        Fraction(500), usd("500.00"), start=START, end=END, component="PERIOD_VC", measure="USAGE"
    )
    fees_only = obligation("POB-01", [_fixed(0, "USAGE"), fees], method="USAGE", convention=None)
    assert not is_deterministic(fees_only)

    # A loyalty-points option is measured by its redemption pattern, whatever its method (§9.2.8).
    for method, expected in (("USAGE", False), ("ROYALTY", False), ("TIME_ELAPSED", True)):
        ob, by_time = _measured(method, "OVER_TIME", option=True) or (None, True)
        assert ob is not None and not by_time, method
        assert is_deterministic(ob) is expected, method
