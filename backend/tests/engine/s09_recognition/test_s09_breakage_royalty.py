"""Stage 09 breakage, the unclaimed-property carve-out and royalties (ENC-8).

ENGINE_SPEC_B §9.2.8 S09-R-27 to S09-R-31 and S09-INV-11 (EX-09-D), §9.2.9 S09-R-32 to S09-R-34
(EX-09-F), §9.4 findings, §9.5 nodes; POLICIES POL-055 to POL-057, POL-241. Every expected figure
was re-derived with Fraction arithmetic in ``.run/l3-enc8/derive.py`` before these tests were
written (lane ENG-C3). The ``AllocatedState`` is hand-built against the documented contract
(support.recognition); stage 10 runs on the stage 09 output for the JET-04b carve-out.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.stages import s10_billing_balances
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from erev_engine.stages.s09_recognition import RecognitionState, run
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s15_disclosures.rpo import rollforward
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    Target,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import ENTITY_CODE, entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    estimate_version,
    event_view,
    obligation,
    period_amounts,
    segment,
    targets_by_period,
    usd,
)

pytestmark: list[pytest.MarkDecorator] = []

O_CREDITS = f"{CONTRACT_KEY}/L1"
JAN_1 = date(2026, 1, 1)
P1, P2, P3, P4 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
GROUP_AT_ENTITY = group_entity_subject_key("CG-1", ENTITY_CODE)


def _run(ctx: BookContext, st: AllocatedState) -> tuple[RecognitionState, Trace]:
    """Stage 09, every node re-evaluated (DG-ENG-04; PROP:P14)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _stages(ctx: BookContext, st: AllocatedState) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10, every node re-evaluated."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    recognition = run(ctx, st, tb)
    state = s10_billing_balances.run(ctx, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _pins(*applied: tuple[EstimateVersionInput, EventView]) -> EstimatePins:
    pins: dict[str, list[EstimatePin]] = {}
    for version, ev in applied:
        pins.setdefault(version.estimate_key, []).append(EstimatePin(version, ev.order_key))
    return EstimatePins(
        {
            key: tuple(sorted(items, key=lambda pin: pin.event_order_key))
            for key, items in sorted(pins.items())
        }
    )


def _causes(state: RecognitionState, subject_key: str) -> dict[tuple[str, str], int]:
    """(period key, cause) -> period amount of ``revenue`` targets."""
    return {
        (t.period_key, str(t.cause)): t.value
        for t in state.revenue_by_cause
        if t.subject_key == subject_key
    }


def _target(targets: Sequence[Target], measure: str, subject_key: str, period_key: str) -> int:
    return next(
        t.value
        for t in targets
        if (t.measure, t.subject_key, t.period_key) == (measure, subject_key, period_key)
    )


# --- EX-09-D: prepaid credits with breakage and the unclaimed-property carve-out ------------------


def _breakage_version(
    version_no: int, effective: date, *, rate: str, expected: str
) -> EstimateVersionInput:
    base = estimate_version(f"{CONTRACT_KEY}/BRK-CREDITS", "BREAKAGE", version_no, effective)
    return dataclasses.replace(
        base,
        obligation_key="L1",
        rate=Decimal(rate),
        expected_quantity=Decimal(expected),
        method="RATE",
    )


def _credits(end: date | None = P4) -> ObligationState:
    """EX-09-D: 120,000 credits sold for 120,000.00 (Q = 120,000, X = A = 120,000.00)."""
    seg = segment(
        Fraction(120000),
        usd("120000.00"),
        start=JAN_1,
        end=end,
        quantity=Fraction(120000),
        measure="REDEMPTION_PATTERN",
    )
    return obligation(
        "L1",
        [seg],
        method="REDEMPTION_PATTERN",
        convention=None,
        pattern="OVER_TIME",
        criterion="OT_A",
        quantity=Fraction(120000),
        end=end,
    )


def _ev(version: int, event_type: str, when: date, payload: Mapping[str, object]) -> EventView:
    return event_view(CONTRACT_KEY, version, event_type, when, payload, obligation_keys=["L1"])


def _delivery(version: int, when: date, quantity: str) -> EventView:
    return _ev(
        version,
        "DELIVERY_RECORDED",
        when,
        {"obligation_key": "L1", "quantity": Decimal(quantity), "trigger": "DELIVERY"},
    )


def _estimate(version: int, applied: EstimateVersionInput) -> EventView:
    return _ev(
        version,
        "ESTIMATE_CHANGED",
        applied.effective_date,
        {"estimate_version_id": applied.version_key},
    )


def _ex_09_d_state(
    versions: Sequence[EstimateVersionInput] | None = None,
    deliveries: Sequence[tuple[date, str]] = (
        (P1, "30000"),
        (P2, "45000"),
        (P3, "20000"),
        (P4, "1000"),
    ),
    end: date | None = P4,
) -> AllocatedState:
    if versions is None:
        versions = (
            _breakage_version(1, JAN_1, rate="0.10", expected="100000"),
            _breakage_version(2, P3, rate="0.05", expected="110000"),
        )
    events: list[EventView] = [
        _ev(
            3,
            "BILLING_RECORDED",
            JAN_1,
            {
                "invoice_number": "INV-CREDITS",
                "line_external_id": "INV-CREDITS-1",
                "obligation_key": "L1",
                "amount": Decimal("120000.00"),
                "issue_date": JAN_1,
            },
        )
    ]
    applied: list[tuple[EstimateVersionInput, EventView]] = []
    stream = 4
    for version in versions:
        ev = _estimate(stream, version)
        events.append(ev)
        applied.append((version, ev))
        stream += 1
    for when, quantity in deliveries:
        events.append(_delivery(stream, when, quantity))
        stream += 1
    return allocated_state([_credits(end)], events=events, estimates=_pins(*applied))


CTX_6 = book_context(entity(months=6))


def test_ex_09_d_breakage_and_unclaimed_property() -> None:
    """EX-09-D (S09-R-27, S09-R-28, S09-R-30, S09-INV-11): C_total 33,600.00 / 84,000.00 /
    100,181.82 / 116,000.00; redeemed 30,000.00 / 75,000.00 / 95,000.00 / 96,000.00; breakage
    cumulative 3,600.00 / 9,000.00 / 5,181.82 / 20,000.00; period revenue 33,600.00 / 50,400.00 /
    16,181.82 / 15,818.18; BREAKAGE line 3,600.00 / 5,400.00 / (3,818.18) / 14,818.18. The
    unclaimed-property share u = 1/30 (4,000.00) is never revenue: stage 10 opens the
    UNCLAIMED_PROPERTY refund component and the net position is 0.00 at expiry."""
    state, trace = _stages(CTX_6, _ex_09_d_state())
    recognition = state.recognition
    targets = targets_by_period(recognition, O_CREDITS)
    periods = ("FY2026-P01", "FY2026-P02", "FY2026-P03", "FY2026-P04")
    assert [targets[p] for p in periods] == [
        usd("33600.00"),
        usd("84000.00"),
        usd("100181.82"),
        usd("116000.00"),
    ]
    assert [period_amounts(targets)[p] for p in periods] == [
        usd("33600.00"),
        usd("50400.00"),
        usd("16181.82"),
        usd("15818.18"),
    ]
    causes = _causes(recognition, O_CREDITS)
    assert [causes[(p, "BREAKAGE")] for p in periods] == [
        usd("3600.00"),
        usd("5400.00"),
        -usd("3818.18"),
        usd("14818.18"),
    ]
    assert [causes[(p, "NORMAL")] for p in periods] == [
        usd("30000.00"),
        usd("45000.00"),
        usd("20000.00"),
        usd("1000.00"),
    ]
    breakage = [
        Decimal(_node(trace, f"breakage_revenue_cum:{O_CREDITS}:{p}").value) for p in periods
    ]
    assert breakage == [
        Decimal("3600.00"),
        Decimal("9000.00"),
        Decimal("5181.82"),
        Decimal("20000.00"),
    ]
    # progress_ratio is the entitlement progress E_total ÷ X: 0.30 × 14/15 = 0.28 in P1.
    p1 = _node(trace, f"progress_ratio:{O_CREDITS}:FY2026-P01")
    assert (p1.formula_id, Fraction(Decimal(p1.value))) == (
        "breakage.proportional.v1",
        Fraction(7, 25),
    )
    assert p1.params["expected"] == "100000" and p1.params["rate"] == "1/10"
    p4 = _node(trace, f"progress_ratio:{O_CREDITS}:FY2026-P04")
    assert (p4.formula_id, p4.params["unclaimed_share"]) == ("breakage.expiry.v1", "1/30")
    # The BREAKAGE cause cites the period's and the previous period's breakage nodes.
    line = _node(trace, f"revenue_by_cause:{O_CREDITS}/BREAKAGE:FY2026-P03")
    assert line.params["signs"] == "+,-"
    assert line.inputs == (
        f"breakage_revenue_cum:{O_CREDITS}:FY2026-P03",
        f"breakage_revenue_cum:{O_CREDITS}:FY2026-P02",
    )
    # S09-R-28: A − C_total = 4,000.00 from the expiry on, published for stage 10 per period end.
    assert [(e.period_key, e.expired_on, e.amount) for e in recognition.escheat_components] == [
        (f"FY2026-P0{m}", P4, usd("4000.00")) for m in (4, 5, 6)
    ]
    escheat = recognition.escheat_components[0]
    assert escheat.subject_key == O_CREDITS
    assert Decimal(_node(trace, escheat.node_id).value) == Decimal("4000.00")
    component = f"{GROUP_AT_ENTITY}/UNCLAIMED_PROPERTY/{O_CREDITS}"
    assert _target(state.refund_liabilities, "refund_liability", component, "FY2026-P04") == usd(
        "4000.00"
    )
    assert _target(state.positions, "net_position", GROUP_AT_ENTITY, "FY2026-P03") == usd(
        "19818.18"
    )
    assert _target(state.positions, "net_position", GROUP_AT_ENTITY, "FY2026-P04") == 0
    measures = recognition.obligation_measures[O_CREDITS]
    assert (measures.allocated_amount, measures.revenue_cum, measures.remaining_allocation) == (
        usd("120000.00"),
        usd("116000.00"),
        usd("4000.00"),
    )
    assert str(measures.satisfaction_status) == "PARTIALLY_SATISFIED"


def test_ex_09_d_without_a_version_is_when_remote() -> None:
    """POL-055 default without an approved version: revenue follows redemptions only (S09-R-29),
    and the breakage line is 0."""
    state, trace = _run(CTX_6, _ex_09_d_state(versions=(), end=None))
    targets = targets_by_period(state, O_CREDITS)
    assert [targets[f"FY2026-P0{m}"] for m in (1, 2, 3, 4)] == [
        usd("30000.00"),
        usd("75000.00"),
        usd("95000.00"),
        usd("96000.00"),
    ]
    node = _node(trace, f"progress_ratio:{O_CREDITS}:FY2026-P01")
    assert (node.formula_id, node.params["remote"], node.params["rate"]) == (
        "breakage.remote.v1",
        "false",
        "0",
    )
    assert ("FY2026-P01", "BREAKAGE") not in _causes(state, O_CREDITS)
    assert state.escheat_components == ()


def test_breakage_findings() -> None:
    """§9.4: expected_quantity 0 on a PROPORTIONAL_TO_EXERCISE version → BREAKAGE_EXPECTED_ZERO
    (ERROR); redemptions above R_exp → BREAKAGE_OVER_REDEMPTION (WARNING); ρ > 1 →
    ESTIMATE_CONSTRAINT_RANGE (ERROR)."""
    zero = _ex_09_d_state(
        versions=(_breakage_version(1, JAN_1, rate="0.10", expected="0"),), end=None
    )
    with pytest.raises(EngineError) as raised:
        _run(CTX_6, zero)
    assert raised.value.code == "BREAKAGE_EXPECTED_ZERO"

    over = _ex_09_d_state(
        versions=(_breakage_version(1, JAN_1, rate="0.10", expected="100000"),),
        deliveries=((P1, "30000"), (P2, "75000")),
        end=None,
    )
    state, _ = _run(CTX_6, over)
    assert [(f.code, f.severity, f.subject_key) for f in state.findings] == [
        ("BREAKAGE_OVER_REDEMPTION", "WARNING", O_CREDITS)
    ]
    # R = 105,000 > R_exp: the entitlement is capped at ρ, so C_total = 120,000 × 14/15.
    assert targets_by_period(state, O_CREDITS)["FY2026-P02"] == usd("112000.00")

    out_of_range = _ex_09_d_state(
        versions=(_breakage_version(1, JAN_1, rate="0.20", expected="100000"),), end=None
    )
    with pytest.raises(EngineError) as raised:
        _run(CTX_6, out_of_range)
    assert raised.value.code == "ESTIMATE_CONSTRAINT_RANGE"


# --- EX-09-F: royalties with a guarantee and a late licensee statement (JPY) ----------------------

CTX_JPY = book_context(entity(months=12), currency="JPY")
O_LIC = f"{CONTRACT_KEY}/L1"
APR_15, JUL_20, SEP_30, NOV_15 = (
    date(2026, 4, 15),
    date(2026, 7, 20),
    date(2026, 9, 30),
    date(2026, 11, 15),
)
YEN_50M = 50_000_000


def _licence() -> ObligationState:
    """A functional licence with a 50,000,000 JPY guarantee, method ROYALTY (S09-R-33)."""
    fixed = segment(
        Fraction(YEN_50M),
        YEN_50M,
        start=APR_15,
        end=APR_15,
        quantity=Fraction(1),
        measure="ROYALTY",
    )
    royalty = segment(
        Fraction(0),
        0,
        start=APR_15,
        end=APR_15,
        quantity=Fraction(1),
        component="ROYALTY",
        measure="ROYALTY",
    )
    return obligation(
        "L1",
        [fixed, royalty],
        method="ROYALTY",
        convention=None,
        pattern="POINT_IN_TIME",
        criterion="NOT_APPLICABLE",
        kind="LICENCE",
        quantity=Fraction(1),
    )


def _statement(version: int, when: date, start: date, end: date, amount: int) -> EventView:
    return _ev(
        version,
        "USAGE_REPORTED",
        when,
        {
            "obligation_key": "L1",
            "usage_period_start": start,
            "usage_period_end": end,
            "metric": "LICENSEE_SALES",
            "quantity": Decimal(amount) * 10,
            "rated_amount": Decimal(amount),
            "is_royalty_statement": True,
        },
    )


def _accrual(
    version_no: int, effective: date, start: date, end: date, amount: int
) -> EstimateVersionInput:
    base = estimate_version(f"{CONTRACT_KEY}/ROY-ACCRUAL", "ROYALTY_ACCRUAL", version_no, effective)
    return dataclasses.replace(
        base,
        obligation_key="L1",
        method="ENTERED_AMOUNT",
        expected_total_amount=Decimal(amount),
        currency="JPY",
        parameters={"usage_period_start_date": start, "usage_period_end_date": end},
    )


def _ex_09_f_state(*, accrue: bool = True) -> AllocatedState:
    accrual = _accrual(1, SEP_30, date(2026, 7, 1), SEP_30, 25_000_000)
    events: list[EventView] = [
        _ev(
            3,
            "DELIVERY_RECORDED",
            APR_15,
            {"obligation_key": "L1", "quantity": Decimal(1), "trigger": "CONTROL_TRANSFER"},
        ),
        _statement(4, JUL_20, date(2026, 4, 1), date(2026, 6, 30), 30_000_000),
    ]
    applied: list[tuple[EstimateVersionInput, EventView]] = []
    if accrue:
        ev = _estimate(5, accrual)
        events.append(ev)
        applied.append((accrual, ev))
    events.append(_statement(6, NOV_15, date(2026, 7, 1), SEP_30, 27_000_000))
    return allocated_state([_licence()], events=events, estimates=_pins(*applied))


def test_ex_09_f_royalties_with_guarantee_jpy() -> None:
    """EX-09-F (S09-R-32, S09-R-33; POL-056, POL-057): FIXED 50,000,000 at transfer in April; the
    April to June statement of 30,000,000 (20 July) gives royalty revenue 0 (below the guarantee);
    the July to September accrual of 25,000,000 (30 September) gives ROYALTY 5,000,000 in
    September; the July to September statement of 27,000,000 (15 November) replaces the accrual,
    a November true-up of 2,000,000. No coverage gap at 31 July and 31 August (S09-R-34)."""
    state, trace = _run(CTX_JPY, _ex_09_f_state())
    targets = targets_by_period(state, O_LIC)
    assert [targets[f"FY2026-P{m:02d}"] for m in range(3, 13)] == [
        0,
        YEN_50M,
        YEN_50M,
        YEN_50M,
        YEN_50M,
        YEN_50M,
        55_000_000,
        55_000_000,
        57_000_000,
        57_000_000,
    ]
    causes = _causes(state, O_LIC)
    assert causes[("FY2026-P04", "NORMAL")] == YEN_50M
    assert causes[("FY2026-P09", "ROYALTY")] == 5_000_000
    assert causes[("FY2026-P11", "ROYALTY")] == 2_000_000
    assert ("FY2026-P07", "ROYALTY") not in causes
    september = _node(trace, f"royalty_revenue_cum:{O_LIC}:FY2026-P09")
    assert (september.formula_id, Decimal(september.value)) == (
        "royalty.minimum_guarantee.v1",
        Decimal("5000000"),
    )
    assert september.params["guarantee"] == "50000000" and september.params["satisfied"] == "true"
    assert [ref.ref_id for ref in september.inputs if not isinstance(ref, str)] == [
        f"{CONTRACT_KEY}/EV-000004",
        f"{CONTRACT_KEY}/ROY-ACCRUAL@v1",
    ]
    true_up = _node(trace, f"royalty_true_up@{CONTRACT_KEY}/EV-000006:{O_LIC}:-")
    assert (true_up.formula_id, Decimal(true_up.value)) == (
        "royalty.report_true_up.v1",
        Decimal("2000000"),
    )
    assert [
        (p.period_key)
        for p in state.close_gate_facts
        if p.period_key in ("FY2026-P07", "FY2026-P08")
    ] == []
    measures = state.obligation_measures[O_LIC]
    assert (measures.allocated_amount, measures.revenue_cum, measures.awaiting_trigger_amount) == (
        57_000_000,
        57_000_000,
        0,
    )
    # The revenue_cum node cites the ROYALTY component as a realised amount (S09-R-02).
    revenue = _node(trace, f"revenue_cum:{O_LIC}:FY2026-P11")
    assert f"royalty_revenue_cum:{O_LIC}:FY2026-P11" in revenue.inputs


def test_royalties_before_satisfaction_await_their_trigger() -> None:
    """S09-R-45: a statement on a licence not yet transferred is allocated but not recognised."""
    st = _ex_09_f_state()
    st = dataclasses.replace(st, events=st.events[1:], measure_events=st.measure_events[1:])
    state, _ = _run(CTX_JPY, st)
    assert targets_by_period(state, O_LIC)["FY2026-P12"] == 0
    measures = state.obligation_measures[O_LIC]
    assert (measures.allocated_amount, measures.revenue_cum, measures.awaiting_trigger_amount) == (
        57_000_000,
        0,
        57_000_000,
    )


def test_s09_r34_coverage_gap_fact() -> None:
    """Removing the September accrual makes the 30 September close-gate facts list the licence
    obligation for the uncovered July to September usage period (S09-R-34)."""
    state, _ = _run(CTX_JPY, _ex_09_f_state(accrue=False))
    assert targets_by_period(state, O_LIC)["FY2026-P09"] == YEN_50M
    facts = [f for f in state.close_gate_facts if f.period_key == "FY2026-P09"]
    assert [
        (f.subject_key, f.usage_period_start, f.usage_period_end, f.period_end) for f in facts
    ] == [(O_LIC, date(2026, 7, 1), SEP_30, SEP_30)]
    with_accrual, _ = _run(CTX_JPY, _ex_09_f_state())
    assert [
        f.period_key for f in with_accrual.close_gate_facts if f.period_key == "FY2026-P09"
    ] == []


# --- Corrected statements: the true-up cites the prior measurement of the usage period -----------

CTX_JPY_13 = book_context(entity(months=13), currency="JPY")
DEC_15, JAN_15_2027, NOV_20 = date(2026, 12, 15), date(2027, 1, 15), date(2026, 11, 20)


def _corrected(st: AllocatedState, *corrections: tuple[int, date, int]) -> AllocatedState:
    """EX-09-F with further July to September statements (stream version, date, amount), each
    correcting the last: the latest statement per usage period counts (S09-R-32)."""
    added = [
        _statement(version, when, date(2026, 7, 1), SEP_30, amount)
        for version, when, amount in corrections
    ]
    events = tuple(sorted((*st.events, *added), key=lambda ev: ev.order_key))
    measured = tuple(sorted((*st.measure_events, *added), key=lambda ev: ev.order_key))
    return dataclasses.replace(st, events=events, measure_events=measured)


def _true_up(trace: Trace, version: int) -> TraceNode:
    return _node(trace, f"royalty_true_up@{CONTRACT_KEY}/EV-{version:06d}:{O_LIC}:-")


def _refs(node: TraceNode) -> list[tuple[str, str, str]]:
    """(ref type, ref id, value) of the node's source references, in input order."""
    return [
        (ref.ref_type, ref.ref_id, ref.detail["value"])
        for ref in node.inputs
        if not isinstance(ref, str)
    ]


def _component_refs(trace: Trace, period_key: str) -> list[str]:
    node = _node(trace, f"royalty_revenue_cum:{O_LIC}:{period_key}")
    return [ref.ref_id for ref in node.inputs if not isinstance(ref, str)]


def test_corrected_statement_true_up_cites_the_prior_statement() -> None:
    """A 15 December statement of 28,000,000 corrects the 15 November 27,000,000 for the same July
    to September usage period: cumulative 58,000,000, December ``ROYALTY`` 1,000,000, and the
    ``royalty_true_up@EV-000007`` node explains 1,000,000 against the statement it corrects
    (28,000,000 − 27,000,000), never 3,000,000 against the superseded accrual. The November node
    is unchanged (27,000,000 − 25,000,000 against the accrual). Derived in
    ``.run/l3-trace/derive.py``."""
    state, trace = _run(CTX_JPY, _corrected(_ex_09_f_state(), (7, DEC_15, 28_000_000)))
    targets = targets_by_period(state, O_LIC)
    assert (targets["FY2026-P11"], targets["FY2026-P12"]) == (57_000_000, 58_000_000)
    causes = _causes(state, O_LIC)
    assert (causes[("FY2026-P11", "ROYALTY")], causes[("FY2026-P12", "ROYALTY")]) == (
        2_000_000,
        1_000_000,
    )
    december = _true_up(trace, 7)
    assert (december.formula_id, Decimal(december.value)) == (
        "royalty.report_true_up.v1",
        Decimal("1000000"),
    )
    assert _refs(december) == [
        ("contract_event", f"{CONTRACT_KEY}/EV-000007", "28000000"),
        ("contract_event", f"{CONTRACT_KEY}/EV-000006", "27000000"),
    ]
    assert (december.params["replaces"], december.params["as_of"]) == ("statement", "2026-12-15")
    assert (december.params["usage_period_start"], december.params["usage_period_end"]) == (
        "2026-07-01",
        "2026-09-30",
    )
    november = _true_up(trace, 6)
    assert (november.formula_id, Decimal(november.value), november.params["replaces"]) == (
        "royalty.report_true_up.v1",
        Decimal("2000000"),
        "accrual",
    )
    assert _refs(november) == [
        ("contract_event", f"{CONTRACT_KEY}/EV-000006", "27000000"),
        ("estimate_version", f"{CONTRACT_KEY}/ROY-ACCRUAL@v1", "25000000"),
    ]
    # The component counts the Q2 statement and the latest Q3 statement only (S09-R-32).
    assert _component_refs(trace, "FY2026-P12") == [
        f"{CONTRACT_KEY}/EV-000004",
        f"{CONTRACT_KEY}/EV-000007",
    ]
    assert Decimal(_node(trace, f"royalty_revenue_cum:{O_LIC}:FY2026-P12").value) == Decimal(
        "8000000"
    )
    measures = state.obligation_measures[O_LIC]
    assert (measures.allocated_amount, measures.revenue_cum) == (58_000_000, 58_000_000)


def test_downward_correction_true_up_is_negative_against_the_prior_statement() -> None:
    """A 15 January 2027 statement of 26,000,000 corrects the December 28,000,000 downward:
    cumulative 56,000,000, January ``ROYALTY`` (2,000,000), and ``royalty_true_up@EV-000008``
    explains (2,000,000) against the 28,000,000 statement it corrects; the earlier nodes keep
    1,000,000 and 2,000,000, so the three true-ups foot to the movement since the accrual."""
    st = _corrected(_ex_09_f_state(), (7, DEC_15, 28_000_000), (8, JAN_15_2027, 26_000_000))
    state, trace = _run(CTX_JPY_13, st)
    targets = targets_by_period(state, O_LIC)
    assert (targets["FY2026-P12"], targets["FY2027-P01"]) == (58_000_000, 56_000_000)
    assert period_amounts(targets)["FY2027-P01"] == -2_000_000
    causes = _causes(state, O_LIC)
    assert (causes[("FY2026-P12", "ROYALTY")], causes[("FY2027-P01", "ROYALTY")]) == (
        1_000_000,
        -2_000_000,
    )
    january = _true_up(trace, 8)
    assert (january.formula_id, Decimal(january.value)) == (
        "royalty.report_true_up.v1",
        Decimal("-2000000"),
    )
    assert _refs(january) == [
        ("contract_event", f"{CONTRACT_KEY}/EV-000008", "26000000"),
        ("contract_event", f"{CONTRACT_KEY}/EV-000007", "28000000"),
    ]
    assert january.params["replaces"] == "statement"
    assert [Decimal(_true_up(trace, v).value) for v in (6, 7, 8)] == [
        Decimal("2000000"),
        Decimal("1000000"),
        Decimal("-2000000"),
    ]
    assert _component_refs(trace, "FY2027-P01") == [
        f"{CONTRACT_KEY}/EV-000004",
        f"{CONTRACT_KEY}/EV-000008",
    ]
    measures = state.obligation_measures[O_LIC]
    assert (measures.allocated_amount, measures.revenue_cum) == (56_000_000, 56_000_000)


def test_correction_without_an_accrual_still_cites_the_statement_it_corrects() -> None:
    """Without the September accrual the first statement replaces nothing and has no true-up
    node; the December correction still explains its 1,000,000 against the November statement."""
    st = _corrected(_ex_09_f_state(accrue=False), (7, DEC_15, 28_000_000))
    state, trace = _run(CTX_JPY, st)
    assert targets_by_period(state, O_LIC)["FY2026-P12"] == 58_000_000
    assert f"royalty_true_up@{CONTRACT_KEY}/EV-000006:{O_LIC}:-" not in {n.id for n in trace.nodes}
    december = _true_up(trace, 7)
    assert (Decimal(december.value), december.params["replaces"]) == (
        Decimal("1000000"),
        "statement",
    )
    assert _refs(december) == [
        ("contract_event", f"{CONTRACT_KEY}/EV-000007", "28000000"),
        ("contract_event", f"{CONTRACT_KEY}/EV-000006", "27000000"),
    ]


def test_same_period_correction_emits_both_true_ups() -> None:
    """Two statements in one posting period (27,000,000 on 15 November, 28,000,000 on 20
    November): the period's ``ROYALTY`` cause is 3,000,000 and both event nodes exist once
    (CV-50), 2,000,000 against the accrual and 1,000,000 against the statement corrected, so the
    event chain foots to the period movement."""
    state, trace = _run(CTX_JPY, _corrected(_ex_09_f_state(), (7, NOV_20, 28_000_000)))
    targets = targets_by_period(state, O_LIC)
    assert (targets["FY2026-P11"], targets["FY2026-P12"]) == (58_000_000, 58_000_000)
    assert _causes(state, O_LIC)[("FY2026-P11", "ROYALTY")] == 3_000_000
    assert [Decimal(_true_up(trace, v).value) for v in (6, 7)] == [
        Decimal("2000000"),
        Decimal("1000000"),
    ]
    assert _refs(_true_up(trace, 7))[1] == (
        "contract_event",
        f"{CONTRACT_KEY}/EV-000006",
        "27000000",
    )
    assert _component_refs(trace, "FY2026-P11") == [
        f"{CONTRACT_KEY}/EV-000004",
        f"{CONTRACT_KEY}/EV-000007",
    ]


@pytest.mark.parametrize("satisfied", [False, True])
def test_royalty_rollforward_carries_realized_allocation_before_and_after_satisfaction(
    satisfied: bool,
) -> None:
    st = _ex_09_f_state()
    if not satisfied:
        st = dataclasses.replace(st, events=st.events[1:], measure_events=st.measure_events[1:])
    recognition, _ = _run(CTX_JPY, st)
    september = rollforward(CTX_JPY, st, recognition, ENTITY_CODE, "FY2026-P09")
    assert september.lines["OPENING"] == (0 if satisfied else 50_000_000)
    assert september.lines["CLOSING"] == (0 if satisfied else 55_000_000)
    assert september.lines["VC_ESTIMATE_CHANGES"] == 5_000_000
    assert september.lines["REVENUE"] == (-5_000_000 if satisfied else 0)
    assert september.lines["UNEXPLAINED"] == 0
    november = rollforward(CTX_JPY, st, recognition, ENTITY_CODE, "FY2026-P11")
    assert november.lines["CLOSING"] == (0 if satisfied else 57_000_000)
    assert november.lines["VC_ESTIMATE_CHANGES"] == 2_000_000
    assert november.lines["UNEXPLAINED"] == 0


def test_royalty_rollforward_downward_correction_reverses_realized_additions() -> None:
    st = _corrected(_ex_09_f_state(), (7, DEC_15, 28_000_000), (8, JAN_15_2027, 26_000_000))
    recognition, _ = _run(CTX_JPY_13, st)
    january = rollforward(CTX_JPY_13, st, recognition, ENTITY_CODE, "FY2027-P01")
    assert january.lines["OPENING"] == january.lines["CLOSING"] == 0
    assert january.lines["VC_ESTIMATE_CHANGES"] == -2_000_000
    assert january.lines["REVENUE"] == 2_000_000
    assert january.lines["UNEXPLAINED"] == 0
