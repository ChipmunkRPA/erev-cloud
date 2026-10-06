"""Stage 09 components, FIXED targets over segments, time elapsed and status guards (ENC-1).

ENGINE_SPEC_B §9.2.1 to §9.2.3 and §9.3; ENGINE_SPEC CV-60 to CV-63, S02-R-03, EX-02-A, EX-06-J,
EX-07-B. The ``AllocatedState`` is built against the documented contract (support.recognition).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.errors import EngineError
from erev_engine.money import cumulative_posted, largest_remainder
from erev_engine.stages.s09_recognition import RecognitionState, components, run
from erev_engine.stages.state import AllocatedState, BookContext, SegmentCause
from erev_engine.trace import TraceBuilder, reevaluate
from support.bundles import entity
from support.recognition import (
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


def _run(ctx: BookContext, st: AllocatedState) -> RecognitionState:
    """Run stage 09 and check that the trace reproduces every node (DG-ENG-04)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)  # the stage 06 and stage 08 nodes stage 09 cites
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert state.allocated is st
    return state


def test_ex_09_a_time_elapsed_with_boundary() -> None:
    ctx = book_context()
    o1_inception = segment(
        Fraction(240000), usd("240000.00"), start=date(2026, 1, 1), end=date(2027, 12, 31)
    )
    before = allocated_state([obligation("POB-01", [o1_inception])])
    o1_before = before.obligations[0]
    assert components.target_at(ctx, before, o1_before, date(2026, 8, 31)).value == usd("79890.41")
    r_k = components.target_at(ctx, before, o1_before, date(2026, 9, 15)).value
    assert r_k == usd("84821.92")

    # ALG-04 §2.5.5: pool (240,000.00 − 84,821.92) + 60,000.00 over mod-date SSP 155,000 : 77,500.
    pool = usd("240000.00") - r_k + usd("60000.00")
    assert pool == usd("215178.08")
    shares = largest_remainder(pool, [Fraction(155000), Fraction(77500)], ["POB-01", "POB-02"])
    assert shares == [usd("143452.05"), usd("71726.03")]
    o1_share = Fraction(pool, 100) * 155000 / 232500
    o2_share = Fraction(pool, 100) * 77500 / 232500
    boundary = f"{CONTRACT_KEY}/EV-000002"
    remaining = {"start": date(2026, 9, 16), "end": date(2027, 12, 31)}
    o1_prospective = segment(
        Fraction(r_k, 100) + o1_share,
        r_k + shares[0],
        basis="PROSPECTIVE",
        cause=SegmentCause.MODIFICATION,
        event_key=boundary,
        base_revenue_posted=r_k,
        base_revenue_exact=Fraction(r_k, 100),
        **remaining,  # type: ignore[arg-type]
    )
    assert o1_prospective.a_posted == usd("228273.97")
    o2_segment = segment(
        o2_share,
        shares[1],
        basis="PROSPECTIVE",
        cause=SegmentCause.MODIFICATION,
        event_key=boundary,
        **remaining,  # type: ignore[arg-type]
    )
    amended = event_view(
        CONTRACT_KEY,
        2,
        "CONTRACT_AMENDED",
        date(2026, 9, 16),
        {"modification_id": "MOD-1"},
        obligation_keys=["POB-01", "POB-02"],
    )
    after = allocated_state(
        [
            obligation("POB-01", [o1_inception, o1_prospective], start=date(2026, 1, 1)),
            obligation("POB-02", [o2_segment]),
        ],
        events=[amended],
    )
    state = _run(ctx, after)
    o1 = period_amounts(targets_by_period(state, O1))
    o2 = period_amounts(targets_by_period(state, O2))
    assert o1["FY2026-P09"] == usd("9490.37")
    assert o2["FY2026-P09"] == usd("2279.43")
    assert o1["FY2026-P09"] + o2["FY2026-P09"] == usd("11769.80")
    assert o1["FY2026-P10"] + o2["FY2026-P10"] == usd("14132.46")
    assert sum(o2[key] for key in o2 if key < "FY2026-P09") == 0

    # S09-INV-09: at the boundary position both segments give R_k, so no catch-up arises.
    contract = after.contracts[0]
    o1_after = after.obligations[0]
    old = components.segment_target(ctx, after, contract, o1_after, o1_inception, date(2026, 9, 15))
    new = components.segment_target(
        ctx, after, contract, o1_after, o1_prospective, date(2026, 9, 15)
    )
    assert old.posted == new.posted == r_k
    assert new.progress.value == 0
    assert targets_by_period(state, O1)["FY2027-P12"] == usd("228273.97")
    assert targets_by_period(state, O2)["FY2027-P12"] == usd("71726.03")


def test_s09_r02_period_vc_realised_component() -> None:
    ctx = book_context()
    fixed = segment(Fraction(1200), usd("1200.00"), start=date(2026, 1, 1), end=date(2026, 12, 31))
    usage_fees = segment(
        Fraction(0), 0, start=date(2026, 1, 1), end=date(2026, 12, 31), component="PERIOD_VC"
    )
    ob = obligation("POB-01", [fixed, usage_fees], convention="MONTHLY_EVEN")

    def usage(version: int, effective: date, period_end: date, rated: str | None) -> object:
        payload: dict[str, object] = {
            "obligation_key": "POB-01",
            "usage_period_start": period_end.replace(day=1),
            "usage_period_end": period_end,
            "metric": "API_CALLS",
            "quantity": Decimal("1000"),
        }
        if rated is not None:
            payload["rated_amount"] = Decimal(rated)
        return event_view(
            CONTRACT_KEY, version, "USAGE_REPORTED", effective, payload, obligation_keys=["POB-01"]
        )

    events = [
        usage(2, date(2026, 2, 3), date(2026, 1, 31), "150.00"),
        usage(3, date(2026, 3, 2), date(2026, 2, 28), "200.00"),
        usage(4, date(2026, 3, 5), date(2026, 3, 31), "75.00"),
    ]
    st = allocated_state([ob], events=events)  # type: ignore[arg-type]
    feb = components.target_at(ctx, st, st.obligations[0], date(2026, 2, 28))
    assert [(item.event_key, item.amount) for item in feb.realised] == [("K-01/EV-000002", 15000)]
    # X = A = the realised cumulative amount and f = 1: ALG-01 §2.1.3 returns the amount itself.
    assert cumulative_posted(Fraction(15000, 100), 15000, Fraction(1), 2) == 15000
    assert feb.fixed is not None and feb.fixed.posted == usd("200.00")
    assert feb.value == feb.fixed.posted + sum(item.amount for item in feb.realised)

    targets = targets_by_period(_run(ctx, st), O1)
    assert targets["FY2026-P01"] == usd("100.00")  # the January usage is reported on 3 February
    assert targets["FY2026-P02"] == usd("200.00") + usd("150.00")
    assert targets["FY2026-P03"] == usd("300.00") + usd("150.00") + usd("200.00") + usd("75.00")

    missing = allocated_state([ob], events=[usage(2, date(2026, 2, 3), date(2026, 1, 31), None)])  # type: ignore[list-item]
    state = _run(ctx, missing)
    assert [(f.code, f.severity, f.event_key) for f in state.findings] == [
        ("NON_FINITE_AMOUNT", "ERROR", "K-01/EV-000002")
    ]
    assert targets_by_period(state, O1)["FY2026-P02"] == usd("200.00")


def test_s02_r03_revenue_guard_and_transition() -> None:
    calendar = entity(months=36)
    ctx = book_context(calendar)
    service = segment(Fraction(720), usd("720.00"), start=date(2026, 1, 1), end=date(2028, 12, 31))
    ob = obligation("POB-01", [service], convention="MONTHLY_EVEN")

    # EX-02-A: NOT_A_CONTRACT from activation; criteria met at the end of month 6.
    ex_02_a = (
        (date(2026, 1, 1), "DRAFT"),
        (date(2026, 1, 1), "NOT_A_CONTRACT"),
        (date(2026, 6, 30), "ACTIVE"),
    )
    targets = targets_by_period(_run(ctx, allocated_state([ob], statuses=ex_02_a)), O1)
    assert [targets[f"FY2026-P0{month}"] for month in range(1, 6)] == [0, 0, 0, 0, 0]
    assert targets["FY2026-P06"] == cumulative_posted(Fraction(720), 72000, Fraction(6, 36), 2)
    assert targets["FY2026-P06"] == usd("120.00")
    assert targets["FY2026-P07"] == usd("140.00")

    for statuses in (
        ((date(2026, 1, 1), "DRAFT"),),
        ((date(2026, 1, 1), "NOT_A_CONTRACT"),),
        ((date(2026, 1, 1), "PENDING_REVIEW"),),
    ):
        guarded = targets_by_period(_run(ctx, allocated_state([ob], statuses=statuses)), O1)
        assert set(guarded.values()) == {0}

    voided = ((date(2026, 1, 1), "ACTIVE"), (date(2026, 3, 15), "VOIDED"))
    targets = targets_by_period(_run(ctx, allocated_state([ob], statuses=voided)), O1)
    assert (targets["FY2026-P01"], targets["FY2026-P02"]) == (usd("20.00"), usd("40.00"))
    assert {targets[key] for key in targets if key >= "FY2026-P03"} == {0}

    # S02-R-05: a prospective failure freezes the targets at C of the transition date.
    failed = ((date(2026, 1, 1), "ACTIVE"), (date(2026, 3, 15), "NOT_A_CONTRACT"))
    targets = targets_by_period(_run(ctx, allocated_state([ob], statuses=failed)), O1)
    # MONTHLY_EVEN steps on the last day of a whole period (ALG-11 rule 2): f(15 March) = 2/36.
    frozen = cumulative_posted(Fraction(720), 72000, Fraction(2, 36), 2)
    assert frozen == usd("40.00")
    assert {targets[key] for key in targets if key >= "FY2026-P03"} == {frozen}


def test_s09_inv_06_before_recognition_start() -> None:
    ctx = book_context()
    licence = segment(
        Fraction(12000), usd("12000.00"), start=date(2026, 1, 1), end=date(2027, 12, 31)
    )
    ob = obligation("POB-01", [licence], recognition_start=date(2027, 1, 1))
    targets = targets_by_period(_run(ctx, allocated_state([ob])), O1)
    assert [targets[f"FY2026-P{month:02d}"] for month in range(1, 13)] == [0] * 12
    assert targets["FY2027-P01"] == cumulative_posted(
        Fraction(12000), 1200000, Fraction(31, 365), 2
    )
    assert targets["FY2027-P01"] == usd("1019.18")
    assert targets["FY2027-P12"] == usd("12000.00")
    assert components.target_at(ctx, allocated_state([ob]), ob, date(2026, 12, 31)).guard == "V5"


def test_s09_r06_termination_segment() -> None:
    # EX-06-J: a two-year subscription billed 120,000.00 a year, terminated at month 18.
    ctx = book_context()
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=date(2026, 1, 1), end=date(2027, 12, 31)
    )
    termination = segment(
        Fraction(180000),
        usd("180000.00"),
        start=date(2026, 1, 1),
        end=date(2027, 6, 30),
        effective=date(2027, 6, 30),
        cause=SegmentCause.TERMINATION,
        event_key=f"{CONTRACT_KEY}/EV-000005",
    )
    ob = obligation("POB-01", [subscription, termination], convention="MONTHLY_EVEN")
    terminated = event_view(
        CONTRACT_KEY,
        5,
        "CONTRACT_TERMINATED",
        date(2027, 6, 30),
        {"modification_id": "MOD-T", "termination_kind": "FULL"},
        obligation_keys=["POB-01"],
    )
    st = allocated_state([ob], events=[terminated])
    targets = targets_by_period(_run(ctx, st), O1)
    assert targets["FY2027-P05"] == usd("170000.00")
    assert targets["FY2027-P06"] == usd("180000.00")
    assert {targets[f"FY2027-P{month:02d}"] for month in range(6, 13)} == {usd("180000.00")}
    for d in (date(2027, 6, 30), date(2027, 7, 15), date(2027, 12, 31)):
        at = components.target_at(ctx, st, st.obligations[0], d)
        assert at.fixed is not None and at.fixed.progress.value == 1
        assert at.value == usd("180000.00")


def test_ex_07_b_january_revenue() -> None:
    calendar = entity(start=date(2025, 11, 1), months=13)
    ctx = book_context(calendar)
    support = segment(
        Fraction(12000), usd("12000.00"), start=date(2025, 11, 10), end=date(2026, 11, 9)
    )
    st = allocated_state(
        [obligation("POB-01", [support])],
        inception=date(2025, 11, 10),
        statuses=((date(2025, 11, 10), "ACTIVE"),),
    )
    targets = targets_by_period(_run(ctx, st), O1)
    assert targets["FY2025-P12"] == cumulative_posted(
        Fraction(12000), 1200000, Fraction(52, 365), 2
    )
    assert targets["FY2025-P12"] == usd("1709.59")
    assert targets["FY2026-P01"] == usd("2728.77")
    assert targets["FY2026-P01"] - targets["FY2025-P12"] == usd("1019.18")


def test_s09_r09_custodial_start() -> None:
    ctx = book_context()
    goods = segment(Fraction(10000), usd("10000.00"), start=date(2026, 1, 1), end=date(2026, 1, 1))
    goods_ob = obligation("POB-01", [goods], method="POINT_IN_TIME", convention=None)
    custody = segment(
        Fraction(1000), usd("1000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    custody_ob = obligation("POB-02", [custody], kind="CUSTODIAL")
    bill_and_hold = event_view(
        CONTRACT_KEY,
        2,
        "DELIVERY_RECORDED",
        date(2026, 3, 15),
        {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "BILL_AND_HOLD"},
        obligation_keys=["POB-01"],
    )
    met = allocated_state(
        [goods_ob, custody_ob],
        events=[bill_and_hold],
        judgements=[bill_and_hold_judgement("POB-01")],
    )
    state = _run(ctx, met)
    goods_targets = targets_by_period(state, O1)
    custody_targets = targets_by_period(state, O2)
    assert (goods_targets["FY2026-P02"], goods_targets["FY2026-P03"]) == (0, usd("10000.00"))
    assert (custody_targets["FY2026-P01"], custody_targets["FY2026-P02"]) == (0, 0)
    # DAILY over [2026-03-15, 2026-12-31] (292 days): 17 days by 31 March.
    assert custody_targets["FY2026-P03"] == cumulative_posted(
        Fraction(1000), 100000, Fraction(17, 292), 2
    )
    assert custody_targets["FY2026-P03"] == usd("58.22")
    assert custody_targets["FY2026-P12"] == usd("1000.00")

    # The later of the custodial start and the transfer: a custody term from 1 April.
    late = obligation(
        "POB-02",
        [segment(Fraction(1000), usd("1000.00"), start=date(2026, 4, 1), end=date(2026, 12, 31))],
        kind="CUSTODIAL",
    )
    later = allocated_state(
        [goods_ob, late], events=[bill_and_hold], judgements=[bill_and_hold_judgement("POB-01")]
    )
    late_targets = targets_by_period(_run(ctx, later), O2)
    assert (late_targets["FY2026-P03"], late_targets["FY2026-P04"]) == (0, usd("109.09"))

    # Criteria unmet: no control transfer, so neither the goods nor the custody earn revenue.
    unmet = allocated_state(
        [goods_ob, custody_ob],
        events=[bill_and_hold],
        judgements=[bill_and_hold_judgement("POB-01", unmet=["ready_for_physical_transfer"])],
    )
    state = _run(ctx, unmet)
    assert set(targets_by_period(state, O1).values()) == {0}
    assert set(targets_by_period(state, O2).values()) == {0}


def test_rec_002_over_time_requires_criterion() -> None:
    ctx = book_context()
    service = segment(
        Fraction(12000), usd("12000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    for criterion in ("NOT_APPLICABLE", "OT_D", ""):
        st = allocated_state([obligation("POB-01", [service], criterion=criterion)])
        with pytest.raises(EngineError) as raised:
            run(ctx, st, TraceBuilder(engine_version=ENGINE_VERSION))
        assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
        assert raised.value.detail["rule"] == "REQ-REC-002"

    over_time = targets_by_period(
        _run(ctx, allocated_state([obligation("POB-01", [service], criterion="OT_A")])), O1
    )
    values = [over_time[f"FY2026-P{month:02d}"] for month in range(1, 13)]
    assert values == sorted(values) and 0 < values[0] < values[-1] == usd("12000.00")

    goods = segment(Fraction(5000), usd("5000.00"), start=date(2026, 1, 1), end=date(2026, 1, 1))
    point = obligation("POB-01", [goods], method="POINT_IN_TIME", convention=None)
    with pytest.raises(EngineError, match="ENGINE_INVARIANT_VIOLATED"):
        bad = obligation(
            "POB-01", [goods], method="POINT_IN_TIME", convention=None, criterion="OT_A"
        )
        run(ctx, allocated_state([bad]), TraceBuilder(engine_version=ENGINE_VERSION))
    delivery = event_view(
        CONTRACT_KEY,
        2,
        "DELIVERY_RECORDED",
        date(2026, 5, 10),
        {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "DELIVERY"},
        obligation_keys=["POB-01"],
    )
    awaiting = targets_by_period(_run(ctx, allocated_state([point])), O1)
    assert set(awaiting.values()) == {0}  # the whole allocation awaits the control transfer
    transferred = targets_by_period(_run(ctx, allocated_state([point], events=[delivery])), O1)
    assert transferred["FY2026-P04"] == 0
    assert usd("5000.00") - transferred["FY2026-P04"] == usd("5000.00")  # awaiting trigger
    assert transferred["FY2026-P05"] == usd("5000.00")


def test_s09_inv_01_02_component_bounds() -> None:
    calendar = entity(start=date(2026, 1, 1), months=24)
    ctx = book_context(calendar)
    cases = (
        (Fraction(1000), usd("1000.00"), "DAILY", date(2026, 2, 10), date(2027, 2, 9)),
        (Fraction(-1000), usd("-1000.00"), "DAILY", date(2026, 2, 10), date(2027, 2, 9)),
        (
            Fraction(1300 * 368, 2018),
            usd("237.07"),
            "MONTHLY_EVEN",
            date(2026, 2, 10),
            date(2026, 5, 20),
        ),
        (
            Fraction(-1300 * 368, 2018),
            usd("-237.07"),
            "MONTHLY_EVEN",
            date(2026, 1, 1),
            date(2026, 3, 31),
        ),
        (Fraction(10000, 3), usd("3333.33"), "MID_MONTH", date(2026, 3, 20), date(2026, 10, 10)),
        (Fraction(-500), usd("-500.00"), "MID_MONTH", date(2026, 1, 20), date(2026, 2, 10)),
    )
    for x_exact, a_posted, convention, start, end in cases:
        ob = obligation(
            "POB-01", [segment(x_exact, a_posted, start=start, end=end)], convention=convention
        )
        st = allocated_state([ob])
        state = _run(ctx, st)
        targets = targets_by_period(state, O1)
        for value in targets.values():
            if a_posted >= 0:
                assert 0 <= value <= a_posted
            else:
                assert a_posted <= value <= 0
        last = max(targets)
        assert targets[last] == a_posted
        final = components.target_at(ctx, st, st.obligations[0], calendar.periods[-1].end_date)
        assert final.fixed is not None and final.fixed.progress.value == 1
        assert final.value == a_posted
