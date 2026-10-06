"""Stage 07 onboarding: opening balances, recomputation from inception, business combinations.

ENGINE_SPEC §7.2, §7.3 S07-R-01 to S07-R-08, §7.5 S07-INV-01 to S07-INV-03 and §7.6 EX-07-A to
EX-07-C; POLICIES POL-210, POL-215 to POL-217 and PT-11 (CHK-121). Stages 02 to 05 are built in
another lane, so the tests build ``AllocatedState`` against ENGINE_SPEC §0.11 (D-81 integration
after merge). Every trace built here re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.errors import EngineError
from erev_engine.money import cumulative_posted, largest_remainder, round_half_up
from erev_engine.stages import s07_onboarding
from erev_engine.stages.s09_recognition import components, run
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ContractView,
    EventView,
    ObligationState,
    Quota1,
    SegmentCause,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    contract_view,
    event_view,
    obligation,
    period_amounts,
    segment,
    targets_by_period,
    usd,
)

CONTRACT_1 = "Contract 1"
LEGACY_START = date(2023, 1, 1)
CUTOVER_A = date(2023, 1, 31)
CUTOVER_B = date(2025, 12, 31)
OPENING_MODE = "OPENING_BALANCES_AT_CUTOVER"
# Golden step 04, Contract 1 (docs/legacy/golden/04-delivery-billing-2023-01-31/contract_live.csv):
# POB, extended SSP and quantity (Original columns), then the Current columns Rev Rec - Cumulative,
# Remaining Allocation, Remaining Qty, Remaining SSP, Delivery - Cumulative, Billing - Cumulative,
# Remaining Billing and Pre-ASC606 Revenue - Cumulative, as stored.
GOLDEN_STEP_04 = (
    (
        "POB #1",
        500,
        "5",
        "128.8404360753221",
        "193.26065411298316",
        "3.0",
        "300.0",
        "2.0",
        "100",
        "400",
        "0",
    ),
    (
        "POB #2",
        368,
        "2",
        "118.53320118929634",
        "118.53320118929634",
        "1.0",
        "184.0",
        "1.0",
        "100",
        "300",
        "66",
    ),
    (
        "POB #3",
        150,
        "1",
        "48.31516352824579",
        "48.31516352824579",
        "0.5",
        "75.0",
        "0.5",
        "100",
        "300",
        "88",
    ),
    ("POB #4", 1000, "1000", "0.0", "644.2021803766105", "1000.0", "1000.0", "0.0", "0", "0", "0"),
)


def _decimal(value: str) -> Fraction:
    """A payload decimal as stage 01 converts it (CV-30)."""
    return Fraction(Decimal(value))


def _row(
    obligation_key: str,
    revenue: str,
    remaining: str,
    *,
    quantity: str = "0",
    ssp: str = "0",
    delivered: str = "0",
    billed: str = "0",
    remaining_billing: str = "0",
    pre_standard: str = "0",
) -> dict[str, object]:
    """One ``obligations[]`` member of the payload (04 §16.3)."""
    return {
        "obligation_key": obligation_key,
        "billed_cum": _decimal(billed),
        "catch_up_cum": Fraction(0),
        "delivered_quantity_cum": _decimal(delivered),
        "netting_reclass_amount": Fraction(0),
        "position_obligation": Fraction(0),
        "pre_standard_revenue_cum": _decimal(pre_standard),
        "remaining_allocation": _decimal(remaining),
        "remaining_billing": _decimal(remaining_billing),
        "remaining_quantity": _decimal(quantity),
        "remaining_ssp": _decimal(ssp),
        "revenue_cum": _decimal(revenue),
        "ssp_delivered_cum": Fraction(0),
    }


def _golden_row(
    pob: str,
    *,
    revenue: str | None = None,
    remaining: str | None = None,
    quantity: str | None = None,
) -> dict[str, object]:
    """The golden step 04 row of ``pob``, with members replaced where given."""
    for name, _, _, rev, rem, qty, ssp, delivered, billed, rb, pre in GOLDEN_STEP_04:
        if name == pob:
            return _row(
                name,
                revenue or rev,
                remaining or rem,
                quantity=quantity or qty,
                ssp=ssp,
                delivered=delivered,
                billed=billed,
                remaining_billing=rb,
                pre_standard=pre,
            )
    raise KeyError(pob)


def _golden_rows() -> list[dict[str, object]]:
    return [_golden_row(row[0]) for row in GOLDEN_STEP_04]


def _opening(
    contract_key: str,
    version: int,
    cutover: date,
    reason: str,
    rows: Sequence[Mapping[str, object]],
    **members: object,
) -> EventView:
    """``OPENING_BALANCE_ESTABLISHED`` effective on the cutover (S07-R-01; 04 §16.3)."""
    payload: dict[str, object] = {
        "reason": reason,
        "cutover_date": cutover,
        "migration_batch_id": "MIG-000001",
        "obligations": [dict(row) for row in rows],
        **members,
    }
    return event_view(contract_key, version, "OPENING_BALANCE_ESTABLISHED", cutover, payload)


def _legacy_ctx() -> BookContext:
    return book_context(
        entity(start=LEGACY_START, months=12),
        preset="LEGACY_PARITY",
        overrides=[("onboarding.method", "CONTRACT", CONTRACT_1, OPENING_MODE)],
    )


def _golden_contract_1(events: Sequence[EventView]) -> AllocatedState:
    """Contract 1 booked from its Original columns: X = 1,300 × extended SSP ÷ 2,018 (S07-R-02)."""
    keys = [row[0] for row in GOLDEN_STEP_04]
    posted = largest_remainder(usd("1300.00"), [Fraction(row[1]) for row in GOLDEN_STEP_04], keys)
    obligations = []
    for row, a_posted in zip(GOLDEN_STEP_04, posted, strict=True):
        pob, ssp, quantity = row[0], row[1], Fraction(row[2])
        units = segment(
            Fraction(1300 * ssp, 2018),
            a_posted,
            start=LEGACY_START,
            end=date(2023, 12, 31),
            quantity=quantity,
            measure="UNITS_DELIVERED",
        )
        obligations.append(
            obligation(
                pob,
                [units],
                contract_key=CONTRACT_1,
                method="UNITS_DELIVERED",
                convention=None,
                quantity=quantity,
            )
        )
    return allocated_state(obligations, events=events, inception=LEGACY_START)


def _checked(tb: TraceBuilder) -> Trace:
    """The trace, after checking that it reproduces every node (DG-ENG-04)."""
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def test_ex_07_a_opening_balances_mode_a() -> None:
    ctx = _legacy_ctx()
    ev = _opening(CONTRACT_1, 3, CUTOVER_A, "LEGACY_MIGRATION", _golden_rows())
    st = _golden_contract_1([ev])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, st, ev, tb)
    assert after.findings == ()

    opening = [ob.segments[-1] for ob in after.obligations]
    assert [(seg.cause, seg.basis, seg.effective_date, seg.event_key) for seg in opening] == [
        (SegmentCause.OPENING_BALANCE, "PROSPECTIVE", CUTOVER_A, ev.event_key)
    ] * 4
    # X = revenue_cum + remaining_allocation, legacy full precision (S07-R-03).
    assert [seg.x_exact for seg in opening] == [
        _decimal(row[3]) + _decimal(row[4]) for row in GOLDEN_STEP_04
    ]
    assert [round_half_up(seg.x_exact, 4) for seg in opening] == [3221011, 2370664, 966303, 6442022]
    # A = largest_remainder(130,000, X, keys); C_0 = cumulative_posted(X, A, revenue_cum ÷ X).
    assert [seg.a_posted for seg in opening] == [
        usd("322.10"),
        usd("237.07"),
        usd("96.63"),
        usd("644.20"),
    ]
    assert [seg.base_revenue_posted for seg in opening] == [
        usd("128.84"),
        usd("118.53"),
        usd("48.32"),
        0,
    ]
    assert [seg.base_revenue_exact for seg in opening] == [
        _decimal(row[3]) for row in GOLDEN_STEP_04
    ]
    assert [seg.totals.quantity for seg in opening] == [3, 1, Fraction(1, 2), 1000]
    assert {seg.totals.start_date for seg in opening} == {date(2023, 2, 1)}
    assert {seg.progress_measure for seg in opening} == {"UNITS_SINCE_BOUNDARY"}
    assert (opening[0].unit_ssp, opening[0].remaining_billing_plan) == (100, 400)

    baselines = [s07_onboarding.baseline_of(ob) for ob in after.obligations]
    assert all(
        item is not None and (item.method, item.cutover_date) == (OPENING_MODE, CUTOVER_A)
        for item in baselines
    )
    assert sum(item.revenue_cum for item in baselines if item is not None) == usd("295.69")
    assert sum(item.billed_cum for item in baselines if item is not None) == usd("300.00")

    # S07-INV-01: every revenue target on or before the cutover equals the baseline.
    state = run(ctx, after, tb)
    trace = _checked(tb)
    for ob, item in zip(after.obligations, baselines, strict=True):
        assert item is not None
        assert targets_by_period(state, ob.subject_key)["FY2023-P01"] == item.revenue_cum
        for d in (LEGACY_START, date(2023, 1, 15), CUTOVER_A):
            assert components.target_at(ctx, after, ob, d).value == item.revenue_cum
    node = _node(trace, f"opening_revenue_cum@{ev.event_key}:{CONTRACT_1}/POB #1:-")
    assert (node.formula_id, node.value, node.rounding_residue) == (
        "onb.baseline.v1",
        "128.84",
        "0.0004360753221",
    )
    allocation = _node(trace, f"opening_allocation@{ev.event_key}:{CONTRACT_1}/POB #2:-")
    assert (allocation.formula_id, allocation.value) == ("onb.opening_segment.v1", "237.07")


def test_s07_r03_inconsistent_payload() -> None:
    ctx = _legacy_ctx()

    def checks(rows: Sequence[Mapping[str, object]]) -> list[tuple[str, str]]:
        ev = _opening(CONTRACT_1, 3, CUTOVER_A, "LEGACY_MIGRATION", rows)
        st = _golden_contract_1([ev])
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        after = s07_onboarding.apply(ctx, st, ev, tb)
        assert after.obligations == st.obligations  # no segment is established
        assert tb.build(root_measures={}).nodes == ()
        found = []
        for item in after.findings:
            assert (item.code, item.severity, item.stage, item.event_key) == (
                "OPENING_BALANCE_INCONSISTENT",
                "ERROR",
                7,
                ev.event_key,
            )
            assert item.detail["rule"] == "S07-R-03"
            found.append((item.detail["check"], item.subject_key or ""))
        return sorted(found)

    rows = _golden_rows()
    # POB #1 remaining allocation 0.01 above the golden value: Σ X_i misses TP_c = 1,300.00.
    off = [_golden_row("POB #1", remaining="193.27065411298316"), *rows[1:]]
    assert checks(off) == [("transaction_price", CONTRACT_1)]

    # Within the 1e-4 tolerance the payload is consistent.
    near = [_golden_row("POB #1", remaining="193.26070411298316"), *rows[1:]]
    ev = _opening(CONTRACT_1, 3, CUTOVER_A, "LEGACY_MIGRATION", near)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, _golden_contract_1([ev]), ev, tb)
    assert after.findings == ()
    assert {ob.segments[-1].cause for ob in after.obligations} == {SegmentCause.OPENING_BALANCE}
    _checked(tb)

    # Signs, magnitudes and remaining quantities, with every X_i unchanged.
    wrong = [
        rows[0],
        _golden_row("POB #2", revenue="-1", remaining="238.06640237859268"),
        _golden_row("POB #3", revenue="100", remaining="-3.36967294350842"),
        _golden_row("POB #4", quantity="-1"),
    ]
    assert checks(wrong) == [
        ("magnitude", f"{CONTRACT_1}/POB #3"),
        ("remaining_quantity", f"{CONTRACT_1}/POB #4"),
        ("sign", f"{CONTRACT_1}/POB #2"),
    ]

    # A booked obligation missing from the payload, and a row for an unknown obligation.
    missing = [*rows[1:], _row("POB #9", "0", "0")]
    assert checks(missing) == [
        ("missing_row", f"{CONTRACT_1}/POB #1"),
        ("unknown_obligation", f"{CONTRACT_1}/POB #9"),
    ]


def test_ex_07_b_recompute_from_inception() -> None:
    ctx = book_context(entity(start=date(2025, 11, 1), months=14))
    assert ctx.policies.value("onboarding.method", contract=CONTRACT_KEY) == (
        "RECOMPUTE_FROM_INCEPTION"
    )
    support = segment(
        Fraction(12000), usd("12000.00"), start=date(2025, 11, 10), end=date(2026, 11, 9)
    )
    rows = [_row("POB-01", "2000.00", "10000.00", quantity="1", billed="12000.00")]
    first = _opening(CONTRACT_KEY, 3, CUTOVER_B, "SYSTEM_ONBOARDING", rows)
    second = _opening(CONTRACT_KEY, 4, CUTOVER_B, "SYSTEM_ONBOARDING", rows)
    st = allocated_state(
        [obligation("POB-01", [support], convention="DAILY")],
        events=[first, second],
        inception=date(2025, 11, 10),
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    once = s07_onboarding.apply(ctx, st, first, tb)
    twice = s07_onboarding.apply(ctx, once, second, tb)
    # ONB-DIFF-ROLES: the -290.41 difference is recorded once, by the first event (S07-INV-03), and
    # posted by stage 14 at the cutover (S07-R-07 rev 1.17); stage 07 raises no finding for it.
    assert twice.findings == ()
    ob = twice.obligations[0]
    assert ob.segments == st.obligations[0].segments  # S07-R-06: no segment

    recomputed = cumulative_posted(Fraction(12000), usd("12000.00"), Fraction(52, 365), 2)
    assert recomputed == usd("1709.59")
    (difference,) = s07_onboarding.differences_of(ob)  # S07-INV-03: once per (obligation, role)
    assert (difference.role, difference.cutover_date, difference.event_key) == (
        "REVENUE",
        CUTOVER_B,
        first.event_key,
    )
    assert (difference.recomputed, difference.imported, difference.amount) == (
        recomputed,
        usd("2000.00"),
        usd("-290.41"),
    )
    baseline = s07_onboarding.baseline_of(ob)
    assert baseline is not None
    assert (baseline.revenue_cum, baseline.billed_cum, baseline.method) == (
        usd("2000.00"),
        usd("12000.00"),
        "RECOMPUTE_FROM_INCEPTION",
    )

    state = run(ctx, twice, tb)
    trace = _checked(tb)
    differences = [node for node in trace.nodes if node.id.startswith("onboarding_difference@")]
    assert [node.id for node in differences] == [
        f"onboarding_difference@{first.event_key}:{CONTRACT_KEY}/POB-01:-"
    ]
    assert (
        differences[0].value,
        differences[0].params["role"],
        differences[0].params["imported"],
        differences[0].params["recomputed"],
    ) == ("-290.41", "REVENUE", "200000", "170959")
    targets = targets_by_period(state, f"{CONTRACT_KEY}/POB-01")
    assert targets["FY2025-P12"] == usd("1709.59")
    assert period_amounts(targets)["FY2026-P01"] == usd("1019.18")


def _support_liability(ctx: BookContext) -> int:
    """Support liability at the acquisition of a TP 200,000.00 contract billed upfront (EX-07-C).

    The booking weights stand in for stage 05: acquisition-date SSPs under POL-217 ``APPLY``, the
    inception SSPs otherwise (S05-R-01).
    """
    inception, cutover = date(2025, 1, 1), CUTOVER_B
    applied = ctx.policies.value("bc.expedient_ssp_at_acquisition", contract=CONTRACT_KEY)
    ssp = (
        (Fraction(120000), Fraction(80000))
        if applied == "APPLY"
        else (Fraction(150000), Fraction(50000))
    )
    posted = largest_remainder(usd("200000.00"), list(ssp), ["LIC-01", "SUP-01"])
    exact = [Fraction(200000) * weight / sum(ssp) for weight in ssp]
    licence = obligation(
        "LIC-01",
        [segment(exact[0], posted[0], start=inception, end=inception, measure="POINT_IN_TIME")],
        method="POINT_IN_TIME",
        convention=None,
    )
    support = obligation(
        "SUP-01",
        [segment(exact[1], posted[1], start=inception, end=date(2026, 12, 31))],
        convention="MONTHLY_EVEN",
    )
    rows = [
        _row("LIC-01", str(exact[0]), "0", billed=str(exact[0])),
        _row("SUP-01", str(exact[1] / 2), str(exact[1] / 2), quantity="1", billed=str(exact[1])),
    ]
    ev = _opening(
        CONTRACT_KEY, 3, cutover, "BUSINESS_COMBINATION", rows, acquisition_date=date(2026, 1, 1)
    )
    st = allocated_state([licence, support], events=[ev], inception=inception)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, st, ev, tb)
    _checked(tb)
    assert after.findings == ()
    opening = next(ob for ob in after.obligations if ob.obligation_key == "SUP-01").segments[-1]
    return opening.a_posted - opening.base_revenue_posted


def test_chk_121_business_combination() -> None:
    inception = date(2025, 1, 1)
    calendar = entity(start=inception, months=24, books=("ASC606", "IFRS15"))
    overrides = [("onboarding.method", "CONTRACT", CONTRACT_KEY, OPENING_MODE)]
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=inception, end=date(2026, 12, 31)
    )
    ob = obligation("SUB-01", [subscription], convention="MONTHLY_EVEN")
    rows = [_row("SUB-01", "120000.00", "120000.00", quantity="1", billed="240000.00")]
    ev = _opening(
        CONTRACT_KEY,
        3,
        CUTOVER_B,
        "BUSINESS_COMBINATION",
        rows,
        acquisition_date=date(2026, 1, 1),
        fair_value_contract_liability=Fraction(90000),
    )
    subject = f"{CONTRACT_KEY}/SUB-01"
    months_2025 = [f"FY2025-P{month:02d}" for month in range(1, 13)]
    months_2026 = [f"FY2026-P{month:02d}" for month in range(1, 13)]

    # ASC606 book: computed as if originated; the acquisition-date balances become opening state.
    ctx = book_context(calendar, overrides=overrides)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(
        ctx, allocated_state([ob], events=[ev], inception=inception), ev, tb
    )
    baseline = s07_onboarding.baseline_of(after.obligations[0])
    assert baseline is not None
    assert baseline.billed_cum - baseline.revenue_cum == usd("120000.00")  # contract liability
    targets = targets_by_period(run(ctx, after, tb), subject)
    _checked(tb)
    assert {targets[key] for key in months_2025} == {usd("120000.00")}
    amounts = period_amounts(targets)
    assert [amounts[key] for key in months_2026] == [usd("10000.00")] * 12

    # IFRS15 book: the acquisition-date fair value 90,000.00 is recognised from 0 (S07-R-08).
    ifrs = book_context(calendar, book_code="IFRS15", overrides=overrides)
    assert ifrs.policies.value("bc.acquired_contract_measurement", contract=CONTRACT_KEY) == (
        "FAIR_VALUE_IFRS3"
    )
    contracts = [contract_view(CONTRACT_KEY, statuses=((inception, "ACTIVE"),), book_code="IFRS15")]
    st_ifrs = allocated_state([ob], contracts=contracts, events=[ev], inception=inception)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after_ifrs = s07_onboarding.apply(ifrs, st_ifrs, ev, tb)
    fair = after_ifrs.obligations[0].segments[-1]
    assert (fair.cause, fair.x_exact, fair.a_posted) == (
        SegmentCause.OPENING_BALANCE,
        90000,
        usd("90000.00"),
    )
    assert (fair.base_revenue_exact, fair.base_revenue_posted) == (0, 0)
    fair_baseline = s07_onboarding.baseline_of(after_ifrs.obligations[0])
    assert fair_baseline is not None
    assert (fair_baseline.revenue_cum, fair_baseline.billed_cum) == (0, usd("90000.00"))
    targets = targets_by_period(run(ifrs, after_ifrs, tb), subject)
    _checked(tb)
    assert {targets[key] for key in months_2025} == {0}
    amounts = period_amounts(targets)
    assert [amounts[key] for key in months_2026] == [usd("7500.00")] * 12

    # Expedient (b), POL-217: SSP at the acquisition date gives an opening support liability of
    # 40,000.00, against 25,000.00 as if originated.
    assert ctx.policies.value("bc.expedient_ssp_at_acquisition", contract=CONTRACT_KEY) == "APPLY"
    assert _support_liability(ctx) == usd("40000.00")
    not_applied = book_context(
        calendar,
        overrides=[
            *overrides,
            ("bc.expedient_ssp_at_acquisition", "CONTRACT", CONTRACT_KEY, "DO_NOT_APPLY"),
        ],
    )
    assert _support_liability(not_applied) == usd("25000.00")


def test_l8_d_ifrs_fair_value_appends_the_price_buildup() -> None:
    # D-88 L7-5-Q-9: the IFRS15 acquisition event appends fixed = total = allocation_basis = V.
    inception = date(2025, 1, 1)
    calendar = entity(start=inception, months=24, books=("ASC606", "IFRS15"))
    overrides = [("onboarding.method", "CONTRACT", CONTRACT_KEY, OPENING_MODE)]
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=inception, end=date(2026, 12, 31)
    )
    ob = obligation("SUB-01", [subscription], convention="MONTHLY_EVEN")
    rows = [_row("SUB-01", "120000.00", "120000.00", quantity="1", billed="240000.00")]
    ev = _opening(
        CONTRACT_KEY,
        3,
        CUTOVER_B,
        "BUSINESS_COMBINATION",
        rows,
        acquisition_date=date(2026, 1, 1),
        fair_value_contract_liability=Fraction(90000),
    )
    # ASC606 book: as if originated, no build-up is appended.
    ctx = book_context(calendar, overrides=overrides)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    st = allocated_state([ob], events=[ev], inception=inception)
    assert s07_onboarding.apply(ctx, st, ev, tb).tp_history == ()

    ifrs = book_context(calendar, book_code="IFRS15", overrides=overrides)
    contracts = [contract_view(CONTRACT_KEY, statuses=((inception, "ACTIVE"),), book_code="IFRS15")]
    st_ifrs = allocated_state([ob], contracts=contracts, events=[ev], inception=inception)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ifrs, st_ifrs, ev, tb)
    (buildup,) = after.tp_history
    value = Quota1(Fraction(90000), usd("90000.00"))
    assert (buildup.at, buildup.before_event_key) == (CUTOVER_B, None)
    assert (buildup.fixed, buildup.total, buildup.allocation_basis) == (value, value, value)
    others = (
        buildup.vc_constrained,
        buildup.vc_excluded,
        buildup.expected_returns,
        buildup.consideration_payable,
        buildup.financing_adjustment,
        buildup.noncash,
        buildup.sales_tax_excluded,
        buildup.out_of_scope,
    )
    assert set(others) == {Quota1(Fraction(0), 0)}
    assert buildup.elements == ()
    # S04-R-02: Σ a_posted of the segments in force = allocation_basis.
    assert sum(item.segments[-1].a_posted for item in after.obligations) == value.posted
    trace = _checked(tb)
    group = after.group_code
    basis = _node(trace, f"tp_allocation_basis@{ev.event_key}:{group}:-")
    price = _node(trace, f"transaction_price@{ev.event_key}:{group}:-")
    fixed = _node(trace, f"fixed_consideration@{ev.event_key}:{group}:-")
    assert (basis.value, price.value, fixed.value) == ("90000.00",) * 3
    assert (basis.inputs, price.inputs) == ((price.id,), (fixed.id,))
    (ref,) = fixed.inputs
    assert isinstance(ref, SourceRef)
    assert (ref.ref_id, ref.detail["member"]) == (ev.event_key, "fair_value_contract_liability")


def test_s07_inv_02_allocation_sum() -> None:
    # Golden Contract 1: Σ a_posted = TP_c = 1,300.00.
    ctx = _legacy_ctx()
    ev = _opening(CONTRACT_1, 3, CUTOVER_A, "LEGACY_MIGRATION", _golden_rows())
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, _golden_contract_1([ev]), ev, tb)
    _checked(tb)
    assert sum(ob.segments[-1].a_posted for ob in after.obligations) == usd("1300.00")

    # Three equal quotas without a terminating decimal, in USD (μ = 2) and JPY (μ = 0).
    for currency, total, revenue, remaining in (
        ("USD", 10000, "10.00", "23.3333333333"),
        ("JPY", 10000, "1000", "2333.3333333333"),
    ):
        ctx = book_context(
            entity(),
            currency=currency,
            overrides=[("onboarding.method", "CONTRACT", CONTRACT_KEY, OPENING_MODE)],
        )
        mu = ctx.currencies[currency].minor_unit
        keys = ["POB-01", "POB-02", "POB-03"]
        posted = largest_remainder(total, [Fraction(1)] * 3, keys)
        obligations = [
            obligation(
                key,
                [
                    segment(
                        Fraction(total, 10**mu) / 3,
                        a_posted,
                        start=date(2026, 1, 1),
                        end=date(2026, 12, 31),
                    )
                ],
                convention="DAILY",
            )
            for key, a_posted in zip(keys, posted, strict=True)
        ]
        rows = [_row(key, revenue, remaining, quantity="1") for key in keys]
        ev = _opening(CONTRACT_KEY, 3, date(2026, 3, 31), "SYSTEM_ONBOARDING", rows)
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        after = s07_onboarding.apply(ctx, allocated_state(obligations, events=[ev]), ev, tb)
        _checked(tb)
        assert after.findings == ()
        assert [ob.segments[-1].a_posted for ob in after.obligations] == [3334, 3333, 3333]
        assert sum(ob.segments[-1].a_posted for ob in after.obligations) == total


def test_s07_r07_zero_difference_records_no_finding() -> None:
    """D-97 (11): CHK-121's ASC606 book recomputes from inception under RECOMPUTE_FROM_INCEPTION
    and the imported 120,000.00 equals the recomputed 12 x 10,000.00, so no
    ONBOARDING_DIFFERENCE_UNPOSTED finding is recorded; the difference node reads 0."""
    inception = date(2025, 1, 1)
    ctx = book_context(entity(start=inception, months=24))
    assert ctx.policies.value("onboarding.method", contract=CONTRACT_KEY) == (
        "RECOMPUTE_FROM_INCEPTION"
    )
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=inception, end=date(2026, 12, 31)
    )
    ob = obligation("SUB-01", [subscription], convention="MONTHLY_EVEN")
    rows = [_row("SUB-01", "120000.00", "120000.00", quantity="1", billed="240000.00")]
    ev = _opening(CONTRACT_KEY, 3, CUTOVER_B, "BUSINESS_COMBINATION", rows)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(
        ctx, allocated_state([ob], events=[ev], inception=inception), ev, tb
    )
    assert after.findings == ()
    (difference,) = s07_onboarding.differences_of(after.obligations[0])
    assert (difference.imported, difference.recomputed, difference.amount) == (
        12000000,
        12000000,
        0,
    )


# --- a migrated contract that begins after the cutover (S07-R-01, S07-R-03, S07-R-04) -------------

CONTRACT_3 = "Contract 3"
LATE_START = date(2023, 2, 1)
# Golden step 03, Contract 3 (docs/legacy/golden/03-contract-setup-2023-02-01/contract_live.csv):
# set up on 1 Feb 2023 with Contract 1's lines, so its legacy minimum Current Period is after the
# 31 Jan 2023 cutover. POB, then the Current columns Remaining Allocation, Remaining Qty, Remaining
# SSP and Remaining Billing, as stored; every cumulative column of the four rows is 0.
GOLDEN_STEP_03_CONTRACT_3 = (
    ("POB #1", "322.10109018830525", "5", "500.0", "500"),
    ("POB #2", "237.06640237859267", "2", "368.0", "400"),
    ("POB #3", "96.63032705649158", "1", "150.0", "400"),
    ("POB #4", "644.2021803766105", "1000", "1000.0", "0"),
)


def _late_rows() -> list[dict[str, object]]:
    return [
        _row(pob, "0", remaining, quantity=quantity, ssp=ssp, remaining_billing=billing)
        for pob, remaining, quantity, ssp, billing in GOLDEN_STEP_03_CONTRACT_3
    ]


def _opening_on(
    contract_key: str,
    version: int,
    effective: date,
    cutover: date,
    reason: str,
    rows: Sequence[Mapping[str, object]],
) -> EventView:
    """``OPENING_BALANCE_ESTABLISHED`` naming ``cutover`` and effective on ``effective``."""
    payload: dict[str, object] = {
        "reason": reason,
        "cutover_date": cutover,
        "migration_batch_id": "MIG-000001",
        "obligations": [dict(row) for row in rows],
    }
    return event_view(contract_key, version, "OPENING_BALANCE_ESTABLISHED", effective, payload)


def _booked_on(inception: date, events: Sequence[EventView]) -> AllocatedState:
    """Contract 3 booked on ``inception`` with Contract 1's lines (the golden rows share them), its
    header carrying that inception — the date S01-R-15 and S07-R-01 measure the event against."""
    keys = [row[0] for row in GOLDEN_STEP_04]
    posted = largest_remainder(usd("1300.00"), [Fraction(row[1]) for row in GOLDEN_STEP_04], keys)
    obligations = []
    for row, a_posted in zip(GOLDEN_STEP_04, posted, strict=True):
        pob, ssp, quantity = row[0], row[1], Fraction(row[2])
        units = segment(
            Fraction(1300 * ssp, 2018),
            a_posted,
            start=inception,
            end=date(2023, 12, 31),
            quantity=quantity,
            measure="UNITS_DELIVERED",
        )
        obligations.append(
            obligation(
                pob,
                [units],
                contract_key=CONTRACT_3,
                method="UNITS_DELIVERED",
                convention=None,
                quantity=quantity,
            )
        )
    return allocated_state(
        obligations, contracts=[_header(inception)], events=events, inception=inception
    )


def _header(inception: date, contract_key: str = CONTRACT_3) -> ContractView:
    view = contract_view(contract_key, statuses=((inception, "ACTIVE"),))
    return dataclasses.replace(
        view, header=dataclasses.replace(view.header, inception_date=inception)
    )


def _late_ctx(preset: str = "LEGACY_PARITY") -> BookContext:
    return book_context(
        entity(start=LEGACY_START, months=12),
        preset=preset,
        overrides=[("onboarding.method", "CONTRACT", CONTRACT_3, OPENING_MODE)],
    )


def test_s07_r01_a_migrated_contract_that_begins_after_the_cutover_opens_on_its_inception() -> None:
    """Ruling R-5a (variant E): Contract 3 of WLD-F-15 keeps its inception 1 Feb 2023 and carries
    its one opening event on that date, the payload naming the batch's cutover 31 Jan 2023 and
    nil cumulative members. PRD WLD-X-27: TP of Contract 3 1,300.00."""
    ctx = _late_ctx()
    ev = _opening_on(CONTRACT_3, 3, LATE_START, CUTOVER_A, "LEGACY_MIGRATION", _late_rows())
    st = _booked_on(LATE_START, [ev])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, st, ev, tb)
    assert after.findings == ()

    opening = [ob.segments[-1] for ob in after.obligations]
    assert [(seg.cause, seg.basis, seg.effective_date, seg.event_key) for seg in opening] == [
        (SegmentCause.OPENING_BALANCE, "PROSPECTIVE", LATE_START, ev.event_key)
    ] * 4
    assert [seg.x_exact for seg in opening] == [
        _decimal(row[1]) for row in GOLDEN_STEP_03_CONTRACT_3
    ]
    assert [seg.a_posted for seg in opening] == [
        usd("322.10"),
        usd("237.07"),
        usd("96.63"),
        usd("644.20"),
    ]
    assert sum(seg.a_posted for seg in opening) == usd("1300.00")  # S07-INV-02
    assert {(seg.base_revenue_posted, seg.base_revenue_exact) for seg in opening} == {(0, 0)}
    assert [seg.totals.quantity for seg in opening] == [5, 2, 1, 1000]
    # The imported cumulative amounts cover the cutover date, so the remaining term starts the day
    # after the CUTOVER — here the inception itself, never the day after the event (S07-R-04).
    assert {seg.totals.start_date for seg in opening} == {LATE_START}
    assert {seg.base_progress.boundary_date for seg in opening} == {LATE_START}
    assert {seg.progress_measure for seg in opening} == {"UNITS_SINCE_BOUNDARY"}

    baselines = [s07_onboarding.baseline_of(ob) for ob in after.obligations]
    assert all(item is not None for item in baselines)
    assert [
        (item.method, item.cutover_date, item.revenue_cum, item.billed_cum)
        for item in baselines
        if item is not None
    ] == [(OPENING_MODE, CUTOVER_A, 0, 0)] * 4

    # S07-INV-01: nothing is recognised on or before the cutover, nor before a delivery.
    state = run(ctx, after, tb)
    _checked(tb)
    for ob in after.obligations:
        targets = targets_by_period(state, ob.subject_key)
        assert targets and set(targets.values()) == {0}
        for d in (CUTOVER_A, LATE_START, date(2023, 2, 28)):
            assert components.target_at(ctx, after, ob, d).value == 0


def test_s07_r01_an_event_after_its_cutover_is_admitted_only_on_a_later_inception() -> None:
    """The amended rule is an exception, not a relaxation: the event is effective on its cutover
    date, or on the inception of a contract that begins after it — never a business combination,
    never another date (S07-R-01 rev 1.38)."""
    ctx = _late_ctx()
    rows = _late_rows()

    def refused(inception: date, effective: date, reason: str, cutover: date = CUTOVER_A) -> None:
        ev = _opening_on(CONTRACT_3, 3, effective, cutover, reason, rows)
        st = _booked_on(inception, [ev])
        with pytest.raises(EngineError) as failed:
            s07_onboarding.apply(ctx, st, ev, TraceBuilder(engine_version=ENGINE_VERSION))
        assert (failed.value.code, failed.value.detail["rule"]) == (
            "ENGINE_INVARIANT_VIOLATED",
            "S07-R-01",
        )

    # a business combination never moves off its cutover: a contract that begins after the
    # acquisition date is not an acquired contract (PT-11; S07-R-08 has no fair value for it)
    refused(LATE_START, LATE_START, "BUSINESS_COMBINATION")
    for reason in ("LEGACY_MIGRATION", "SYSTEM_ONBOARDING"):
        # the later date is the inception itself, not a day after it
        refused(LATE_START, date(2023, 2, 2), reason)
        # a contract that existed at the cutover opens on the cutover, whatever later date it offers
        refused(LEGACY_START, LATE_START, reason)
        refused(CUTOVER_A, LATE_START, reason)
        # and never before it
        refused(LEGACY_START, date(2023, 1, 30), reason)

    # the rule reads the dates, not the source: another system's contract that begins after the
    # cutover (S07-R-13) opens on its inception with the same nil opening state
    ev = _opening_on(CONTRACT_3, 3, LATE_START, CUTOVER_A, "SYSTEM_ONBOARDING", rows)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, _booked_on(LATE_START, [ev]), ev, tb)
    assert after.findings == ()
    assert {
        (ob.segments[-1].cause, ob.segments[-1].effective_date, ob.segments[-1].totals.start_date)
        for ob in after.obligations
    } == {(SegmentCause.OPENING_BALANCE, LATE_START, LATE_START)}
    nil = [s07_onboarding.baseline_of(ob) for ob in after.obligations]
    assert [
        (item.cutover_date, item.revenue_cum, item.billed_cum) for item in nil if item is not None
    ] == [(CUTOVER_A, 0, 0)] * 4

    # a contract whose header the state does not carry has no inception to admit the later date
    ev = _opening_on(CONTRACT_3, 3, LATE_START, CUTOVER_A, "LEGACY_MIGRATION", rows)
    st = dataclasses.replace(_booked_on(LATE_START, [ev]), contracts=(_header(LATE_START, "K-9"),))
    with pytest.raises(EngineError) as failed:
        s07_onboarding.apply(ctx, st, ev, TraceBuilder(engine_version=ENGINE_VERSION))
    assert failed.value.detail["rule"] == "S07-R-01"

    # the unchanged case: the same contract booked on or before the cutover opens on the cutover
    for inception in (LEGACY_START, CUTOVER_A):
        ev = _opening_on(CONTRACT_3, 3, CUTOVER_A, CUTOVER_A, "LEGACY_MIGRATION", rows)
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        after = s07_onboarding.apply(ctx, _booked_on(inception, [ev]), ev, tb)
        assert after.findings == ()
        assert {ob.segments[-1].totals.start_date for ob in after.obligations} == {LATE_START}


def test_s07_r03_a_contract_that_begins_after_the_cutover_carries_no_history() -> None:
    """A contract that did not exist at the cutover holds nothing at it: a row with a cumulative
    amount is the legacy database read past the cutover, and fails closed by name."""
    ctx = _late_ctx()
    rows = _late_rows()
    # POB #1 with one unit delivered, 64.42 recognised and 100 billed after the cutover; X_1 and
    # so Σ X_i are unchanged, which is why the transaction-price check alone would not catch it
    progressed = _row(
        "POB #1",
        "64.42021803766105",
        "257.6808721506442",
        quantity="4",
        ssp="400.0",
        delivered="1",
        billed="100",
        remaining_billing="400",
    )
    ev = _opening_on(
        CONTRACT_3, 3, LATE_START, CUTOVER_A, "LEGACY_MIGRATION", [progressed, *rows[1:]]
    )
    st = _booked_on(LATE_START, [ev])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, st, ev, tb)
    assert after.obligations == st.obligations  # no segment is established
    assert tb.build(root_measures={}).nodes == ()
    assert [
        (item.code, item.severity, item.stage, item.event_key, item.subject_key)
        for item in after.findings
    ] == [("OPENING_BALANCE_INCONSISTENT", "ERROR", 7, ev.event_key, f"{CONTRACT_3}/POB #1")] * 3
    assert sorted(
        (item.detail["rule"], item.detail["check"], item.detail["member"])
        for item in after.findings
    ) == [
        ("S07-R-03", "history_before_inception", "billed_cum"),
        ("S07-R-03", "history_before_inception", "delivered_quantity_cum"),
        ("S07-R-03", "history_before_inception", "revenue_cum"),
    ]

    # the same row is consistent history for a contract that existed at the cutover
    ev = _opening_on(
        CONTRACT_3, 3, CUTOVER_A, CUTOVER_A, "LEGACY_MIGRATION", [progressed, *rows[1:]]
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    assert s07_onboarding.apply(ctx, _booked_on(LEGACY_START, [ev]), ev, tb).findings == ()


def test_s07_r04_the_remaining_term_starts_the_day_after_the_cutover_not_after_the_event() -> None:
    """A time-elapsed obligation of a contract that begins after the cutover is recognised as the
    same contract is without an opening event: 334 days at 1.00 a day from 1 Feb 2023. Taking the
    day after the EVENT would drop the inception day (27 days at 334 / 333 in February)."""
    calendar = entity(start=LEGACY_START, months=12)
    ctx = book_context(
        calendar, overrides=[("onboarding.method", "CONTRACT", CONTRACT_3, OPENING_MODE)]
    )
    end = date(2023, 12, 31)
    assert (end - LATE_START).days + 1 == 334
    subject = f"{CONTRACT_3}/SUB-01"

    def subscription() -> list[ObligationState]:
        term = segment(Fraction(334), usd("334.00"), start=LATE_START, end=end)
        return [obligation("SUB-01", [term], contract_key=CONTRACT_3, convention="DAILY")]

    native = allocated_state(
        subscription(), contracts=[_header(LATE_START)], events=[], inception=LATE_START
    )
    expected = targets_by_period(
        run(ctx, native, TraceBuilder(engine_version=ENGINE_VERSION)), subject
    )
    assert (expected["FY2023-P02"], expected["FY2023-P03"], expected["FY2023-P12"]) == (
        usd("28.00"),
        usd("59.00"),
        usd("334.00"),
    )

    ev = _opening_on(
        CONTRACT_3,
        3,
        LATE_START,
        CUTOVER_A,
        "LEGACY_MIGRATION",
        [_row("SUB-01", "0", "334", quantity="1")],
    )
    st = allocated_state(
        subscription(), contracts=[_header(LATE_START)], events=[ev], inception=LATE_START
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s07_onboarding.apply(ctx, st, ev, tb)
    assert after.findings == ()
    opened = after.obligations[0].segments[-1]
    assert (opened.cause, opened.effective_date) == (SegmentCause.OPENING_BALANCE, LATE_START)
    assert (opened.totals.start_date, opened.totals.end_date) == (LATE_START, end)
    targets = targets_by_period(run(ctx, after, tb), subject)
    _checked(tb)
    assert {key: value for key, value in targets.items() if key >= "FY2023-P02"} == {
        key: value for key, value in expected.items() if key >= "FY2023-P02"
    }
    assert targets["FY2023-P02"] == usd("28.00")
