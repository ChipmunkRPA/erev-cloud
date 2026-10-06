"""Stage 11 contract costs: capitalisation, amortisation segments, impairment and reversal (ENC-15).

ENGINE_SPEC_B §11.2.1 to §11.2.5 (S11-R-01 to S11-R-11b), §11.3 S11-INV-01 to S11-INV-04, §11.4
and §11.7 EX-11-A (floor row, rev 1.3); POLICIES JET-09a to JET-09d (CHK-131). Stages 09 and 10 run
over an ``AllocatedState`` built against the documented contract (support.recognition; D-81
integration after merge). Stage 04 publishes no unconstrained transaction price in this lane
(ENA-7), so the remaining consideration is the related obligations' exact allocation unless a test
supplies a ``TpBuildUp`` (L2-4-Q-34). The CHK-131 worlds keep one accounting period per year, so
each year of the check is one period-end test.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput, EstimateVersionInput, JudgementInput, PeriodInput
from erev_engine.stages import s09_recognition, s10_billing_balances, s11_costs_loss
from erev_engine.stages.s11_costs_loss import CostAssetMeasures, CostLossState, CostSegment
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    Quota1,
    TpBuildUp,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import INCEPTION, entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    contract_view,
    emit_catch_up_nodes,
    estimate_version,
    event_view,
    obligation,
    segment,
    usd,
)

CTX = book_context(entity(months=24))
MONTHLY_EVEN = ("recognition.time_convention", "ENTITY", "US01", "MONTHLY_EVEN")
PROPORTIONAL = ("costs.amortisation_pattern", "ENTITY", "US01", "PROPORTIONAL_TO_RELATED_REVENUE")
GROUP = f"{CONTRACT_KEY}/P1"  # the related set of every test asset


def _identity(m: CostAssetMeasures) -> int:
    """capitalized − amortized − impaired + reversed − clawback − accelerated (S11-INV-01)."""
    return (
        m.capitalized_cum
        - m.amortized_cum
        - m.impaired_cum
        + m.impairment_reversed_cum
        - m.clawback_cum
        - m.accelerated_cum
    )


def _run(ctx: BookContext, st: AllocatedState) -> tuple[CostLossState, Trace]:
    """Stages 09 to 11 over one book; the trace re-evaluates node for node and every asset satisfies
    S11-INV-01 at every period end."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    balances = s10_billing_balances.run(ctx, recognition, tb)
    state = s11_costs_loss.run(ctx, balances, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    for measures in state.cost_asset_measures.values():
        assert measures.carrying_amount == _identity(measures) >= 0
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _measures(state: CostLossState, asset: str, period_key: str) -> CostAssetMeasures:
    return state.cost_asset_measures[(asset, period_key)]


def _line(state: CostLossState, asset: str, period_key: str) -> int:
    """The ``COST_AMORTIZATION`` amount of a period, 0 without a line."""
    return sum(
        line.amount
        for line in state.schedule_lines
        if (line.subject_key, line.period_key) == (asset, period_key)
    )


def _cost(version: int, when: date, purpose: str, amount: str, **members: object) -> EventView:
    payload: dict[str, object] = {"purpose": purpose, "amount": Decimal(amount), **members}
    named = members.get("obligation_key")
    keys = [] if named is None else [str(named)]
    return event_view(CONTRACT_KEY, version, "COST_INCURRED", when, payload, obligation_keys=keys)


def _services(amount: str, start: date, end: date, *, convention: str = "DAILY") -> ObligationState:
    services = segment(Fraction(Decimal(amount)), usd(amount), start=start, end=end)
    return obligation("P1", [services], convention=convention)


def _pins(*items: tuple[EstimateVersionInput, int]) -> EstimatePins:
    """APPROVED versions applied by the events of the given stream versions (S01-R-18)."""
    grouped: dict[str, list[EstimatePin]] = {}
    for version, seq in items:
        order_key = (version.effective_date, seq, f"{CONTRACT_KEY}/EV-{seq:06d}")
        grouped.setdefault(version.estimate_key, []).append(EstimatePin(version, order_key))
    return EstimatePins({key: tuple(pins) for key, pins in grouped.items()})


def _renewal(
    version_no: int, effective: date, months: int, expected: str | None = None
) -> EstimateVersionInput:
    version = estimate_version(
        f"{CONTRACT_KEY}/AMORT", "RENEWAL_EXPECTATION", version_no, effective
    )
    amount = None if expected is None else Decimal(expected)
    return dataclasses.replace(version, amortization_months=months, expected_total_amount=amount)


def _eac(version_no: int, effective: date, expected: str) -> EstimateVersionInput:
    version = estimate_version(f"{CONTRACT_KEY}/EAC", "EAC", version_no, effective)
    return dataclasses.replace(version, expected_total_amount=Decimal(expected))


def _annual(years: int = 4) -> EntityInput:
    """One period per calendar year from 2026, open in both books."""
    periods = tuple(
        PeriodInput(
            f"FY{year}-P01",
            year,
            1,
            date(year, 1, 1),
            date(year, 12, 31),
            (("ASC606", "open"), ("IFRS15", "open")),
        )
        for year in range(2026, 2026 + years)
    )
    return EntityInput("US01", "USD", "America/New_York", "MONTHLY", periods)


def test_ex_11_a_k09_daily_amortisation() -> None:
    ctx = book_context(entity(months=48), horizon="FY2026-P12")
    ob = _services("100000", date(2026, 9, 1), date(2029, 8, 31))
    events = [
        _cost(
            2,
            date(2026, 9, 1),
            "COST_TO_OBTAIN",
            "6480.00",
            plan_code="COMM-K09",
            is_incremental=True,
        )
    ]
    state, trace = _run(ctx, allocated_state([ob], events=events))
    asset = f"{CONTRACT_KEY}/EV-000002"
    (spec,) = state.cost_asset_specs
    assert (
        spec.asset_key,
        spec.cost_kind,
        spec.amortization_start_date,
        spec.amortization_months,
        spec.amortization_end_date,
        spec.time_convention,
    ) == (asset, "OBTAIN", date(2026, 9, 1), 36, date(2029, 8, 31), "DAILY")
    # round(6,480.00 × 30 ÷ 1,096) = 177.37 in September 2026.
    assert _line(state, asset, "FY2026-P09") == usd("177.37")
    assert _measures(state, asset, "FY2026-P09").carrying_amount == usd("6302.63")
    node = _node(trace, f"cost_amortised_cum:{asset}:FY2026-P09")
    assert (node.formula_id, node.value, node.params["segments"]) == (
        "cost.amortise.straight_line.v1",
        "177.37",
        "2026-09-01/2029-08-31/648000",
    )


def test_ex_11_a_k02_daily_amortisation() -> None:
    ob = _services("100000", INCEPTION, date(2027, 12, 31))
    events = [
        _cost(2, INCEPTION, "COST_TO_OBTAIN", "12000.00", plan_code="COMM-K02", is_incremental=True)
    ]
    state, _ = _run(CTX, allocated_state([ob], events=events))
    asset = f"{CONTRACT_KEY}/EV-000002"
    august = _measures(state, asset, "FY2026-P08")
    september = _measures(state, asset, "FY2026-P09")
    assert august.amortized_cum == usd("3994.52")  # round(12,000.00 × 243 ÷ 730)
    assert _line(state, asset, "FY2026-P09") == usd("493.15")
    assert (august.carrying_amount, september.carrying_amount) == (
        usd("8005.48"),
        usd("7512.33"),
    )


def _chk_131(book_code: str) -> tuple[CostLossState, Trace]:
    """CHK-131: 40,000.00 over 48 months; remaining consideration 100,000.00 at the end of Year 1
    (75,000.00 of the contract and 25,000.00 of anticipated renewals); remaining costs 85,000.00."""
    ctx = book_context(_annual(), book_code=book_code, overrides=[MONTHLY_EVEN])
    ob = _services("150000", INCEPTION, date(2027, 12, 31), convention="MONTHLY_EVEN")
    pins = _pins(
        (_renewal(1, INCEPTION, 48, "25000.00"), 2),
        (_eac(1, date(2026, 12, 31), "170000.00"), 5),
    )
    events = [
        _cost(
            3, INCEPTION, "COST_TO_OBTAIN", "40000.00", plan_code="COMM-131", is_incremental=True
        ),
        _cost(4, date(2026, 12, 31), "PROGRESS_INPUT", "85000.00", obligation_key="P1"),
        _cost(6, date(2027, 12, 31), "PROGRESS_INPUT", "85000.00", obligation_key="P1"),
    ]
    view = contract_view(statuses=((INCEPTION, "ACTIVE"),), book_code=book_code)
    return _run(ctx, allocated_state([ob], contracts=[view], events=events, estimates=pins))


def test_chk_131_impairment_and_ifrs_reversal() -> None:
    asset = f"{CONTRACT_KEY}/EV-000003"
    us, us_trace = _chk_131("ASC606")
    ifrs, ifrs_trace = _chk_131("IFRS15")
    year_1 = _measures(us, asset, "FY2026-P01")
    assert year_1.amortized_cum == usd("10000.00")
    recoverable = _node(us_trace, f"cost_recoverable:{GROUP}:FY2026-P01")
    # 150,000.00 − 75,000.00 + 25,000.00 − (170,000.00 − 85,000.00) = 15,000.00.
    assert (
        recoverable.value,
        recoverable.params["consideration"],
        recoverable.params["renewal"],
        recoverable.params["eac"],
        recoverable.params["costs"],
    ) == ("15000.00", "15000000", "2500000", "17000000", "8500000")
    impaired = _node(us_trace, f"cost_impaired_cum:{asset}:FY2026-P01")
    assert impaired.params["carrying"] == "3000000"  # carrying 30,000.00 before the test
    assert (year_1.impaired_cum, year_1.carrying_amount) == (usd("15000.00"), usd("15000.00"))
    assert year_1.segments[-1] == CostSegment(
        date(2027, 1, 1), date(2029, 12, 31), usd("15000.00"), "IMPAIRMENT"
    )
    # Year 2, ASC606: segment 2 progress 12/36 gives 5,000.00 and carrying 10,000.00.
    year_2 = _measures(us, asset, "FY2027-P01")
    assert (year_2.amortized_cum - year_1.amortized_cum, year_2.carrying_amount) == (
        usd("5000.00"),
        usd("10000.00"),
    )
    assert {m.impairment_reversed_cum for m in us.cost_asset_measures.values()} == {0}  # S11-INV-03
    # Year 2, IFRS15: min(25,000.00, 20,000.00) − 10,000.00 = 10,000.00; carrying 20,000.00.
    reversal = _node(ifrs_trace, f"cost_impairment_reversed_cum:{asset}:FY2027-P01")
    assert (reversal.params["unimpaired"], reversal.params["carrying"], reversal.value) == (
        "2000000",
        "1000000",
        "10000.00",
    )
    ifrs_2 = _measures(ifrs, asset, "FY2027-P01")
    assert (ifrs_2.impairment_reversed_cum, ifrs_2.carrying_amount) == (
        usd("10000.00"),
        usd("20000.00"),
    )
    assert ifrs_2.segments[-1] == CostSegment(
        date(2028, 1, 1), date(2029, 12, 31), usd("20000.00"), "REVERSAL"
    )
    # Year 3, IFRS15: segment 3 progress 12/24 gives 10,000.00.
    assert _line(ifrs, asset, "FY2028-P01") == usd("10000.00")
    # S11-INV-04: reversals never exceed impairments.
    assert all(
        m.impairment_reversed_cum <= m.impaired_cum for m in ifrs.cost_asset_measures.values()
    )


def test_ex_11_a_impairment_floor() -> None:
    ctx = book_context(_annual(), overrides=[MONTHLY_EVEN])
    ob = _services("400000", INCEPTION, date(2029, 12, 31), convention="MONTHLY_EVEN")
    pins = _pins(
        (_renewal(1, INCEPTION, 48), 2),
        (_eac(1, date(2026, 12, 31), "380000.00"), 5),
        (_eac(2, date(2028, 12, 31), "500000.00"), 9),
    )
    events = [
        _cost(
            3,
            date(2026, 1, 2),
            "COST_TO_OBTAIN",
            "40000.00",
            plan_code="COMM-2026",
            is_incremental=True,
        ),
        _cost(4, date(2026, 12, 31), "PROGRESS_INPUT", "95000.00", obligation_key="P1"),
        _cost(6, date(2027, 12, 31), "PROGRESS_INPUT", "95000.00", obligation_key="P1"),
        _cost(8, date(2028, 12, 31), "PROGRESS_INPUT", "95000.00", obligation_key="P1"),
    ]
    state, trace = _run(ctx, allocated_state([ob], events=events, estimates=pins))
    asset = f"{CONTRACT_KEY}/EV-000003"
    before = _measures(state, asset, "FY2027-P01")
    after = _measures(state, asset, "FY2028-P01")
    assert (before.impaired_cum, before.carrying_amount) == (usd("15000.00"), usd("10000.00"))
    # 400,000.00 − 300,000.00 − (500,000.00 − 285,000.00) = −115,000.00.
    assert _node(trace, f"cost_recoverable:{GROUP}:FY2028-P01").value == "-115000.00"
    impaired = _node(trace, f"cost_impaired_cum:{asset}:FY2028-P01")
    assert impaired.params["carrying"] == "500000"  # carrying 5,000.00 before the test
    # min(5,000.00, max(0, 5,000.00 − (−115,000.00))) = 5,000.00, not 120,000.00.
    assert after.impaired_cum - before.impaired_cum == usd("5000.00")
    assert after.carrying_amount == 0


def test_chk_131_one_year_expedient() -> None:
    ob = _services("12000", INCEPTION, date(2026, 12, 31))
    events = [
        _cost(2, INCEPTION, "COST_TO_OBTAIN", "1200.00", plan_code="COMM-EXP", is_incremental=True)
    ]
    state, trace = _run(CTX, allocated_state([ob], events=events))
    assert not state.cost_asset_specs and not state.cost_assets
    (expensed,) = state.expensed_costs
    assert (expensed.reason, expensed.amount) == ("EXPEDIENT_ONE_YEAR", usd("1200.00"))
    node = _node(trace, expensed.node_id)
    assert (node.id, node.formula_id, node.params["reason"], node.params["months"]) == (
        f"cost_expensed:{CONTRACT_KEY}/EV-000002:FY2026-P01",
        "cost.expense_reason.v1",
        "EXPEDIENT_ONE_YEAR",
        "12",
    )


def test_s11_r01_capitalised_on_activation() -> None:
    march = date(2026, 3, 1)
    ob = _services("100000", INCEPTION, date(2027, 12, 31))
    events = [
        _cost(
            2,
            date(2026, 1, 15),
            "COST_TO_OBTAIN",
            "12000.00",
            plan_code="COMM-ACT",
            is_incremental=True,
        )
    ]
    statuses = ((INCEPTION, "NOT_A_CONTRACT"), (march, "ACTIVE"))
    state, trace = _run(CTX, allocated_state([ob], events=events, statuses=statuses))
    (spec,) = state.cost_asset_specs
    assert spec.capitalization_date == march
    assert _node(trace, f"cost_capitalised:{spec.asset_key}:FY2026-P03").value == "12000.00"
    assert (spec.asset_key, "FY2026-P02") not in state.cost_asset_measures
    assert _measures(state, spec.asset_key, "FY2026-P03").capitalized_cum == usd("12000.00")
    # A contract never active in the book expenses the cost.
    never = allocated_state([ob], events=events, statuses=((INCEPTION, "NOT_A_CONTRACT"),))
    expensed, _ = _run(CTX, never)
    assert [item.reason for item in expensed.expensed_costs] == ["CONTRACT_NOT_ACTIVE"]


def test_s11_r02_fulfilment_cost_requires_judgement() -> None:
    ob = _services("100000", INCEPTION, date(2027, 12, 31))
    events = [
        _cost(
            2, date(2026, 1, 20), "COST_TO_FULFILL", "40000.00", payee="DESIGN", plan_code="FUL-1"
        )
    ]
    state, _ = _run(CTX, allocated_state([ob], events=events))
    assert [(item.reason, item.purpose) for item in state.expensed_costs] == [
        ("FULFILMENT_NOT_ATTESTED", "COST_TO_FULFILL")
    ]
    assert not state.cost_asset_specs
    attestation = JudgementInput("JDG-FUL-1", "OTHER", "FUL-1", None, {"fulfilment_25_5": "true"})
    attested, _ = _run(CTX, allocated_state([ob], events=events, judgements=[attestation]))
    (spec,) = attested.cost_asset_specs
    assert (spec.cost_kind, spec.amount_capitalized) == ("FULFILL", usd("40000.00"))
    assert not attested.expensed_costs


def test_s11_r05_renewal_expectation_prospective() -> None:
    ctx = book_context(entity(months=36), horizon="FY2026-P12", overrides=[MONTHLY_EVEN])
    ob = _services("100000", INCEPTION, date(2027, 12, 31))
    # D-89 L7-6-Q-7 (a): version 2 is effective 30 June; its segment starts the next day.
    first, second = _renewal(1, INCEPTION, 24), _renewal(2, date(2026, 6, 30), 36)
    events = [
        _cost(3, INCEPTION, "COST_TO_OBTAIN", "12000.00", plan_code="COMM-R05", is_incremental=True)
    ]
    st = allocated_state([ob], events=events, estimates=_pins((first, 2), (second, 4)))
    state, _ = _run(ctx, st)
    asset = f"{CONTRACT_KEY}/EV-000003"
    june, july, december = (
        _measures(state, asset, period_key)
        for period_key in ("FY2026-P06", "FY2026-P07", "FY2026-P12")
    )
    assert june.amortized_cum == usd("3000.00")  # 12,000.00 × 6/24, not restated
    assert july.segments[-1] == CostSegment(
        date(2026, 7, 1), date(2028, 12, 31), usd("9000.00"), "PERIOD_CHANGE"
    )
    assert _line(state, asset, "FY2026-P07") == usd("300.00")  # 9,000.00 over the 30 months left
    assert (december.amortized_cum, december.carrying_amount, december.remaining_months) == (
        usd("4800.00"),
        usd("7200.00"),
        24,
    )
    # Version 2 is in force from its effective date, 30 June, before its segment starts.
    may = _measures(state, asset, "FY2026-P05")
    assert (may.renewal_version_key, june.renewal_version_key, december.renewal_version_key) == (
        first.version_key,
        second.version_key,
        second.version_key,
    )


def test_l8_e_renewal_fall_runs_off_the_remaining_costs() -> None:
    """D-89 L7-6-Q-7 (COST-CAP; EX-11-A rows): commission 30,000.00 over 36 months under
    ``MONTHLY_EVEN``; ``RENEWAL_EXPECTATION`` version 2 (12 months) and EAC 55,000.00 both effective
    30 June; no ``PROGRESS_INPUT`` cost. June amortises at the old rate (833.33; carrying
    25,000.00), recoverable (120,000.00 − 60,000.00) − 55,000.00 = 5,000.00 and the impairment is
    20,000.00. From July the remaining costs run off with revenue progress since 30 June, so the
    recoverable amount equals the carrying amount at every period end P07 to P11 and nothing more is
    impaired; P12 ends at 0.00. With a ``PROGRESS_INPUT`` cost on or before t the progress costs
    stand."""
    ctx = book_context(entity(months=36), horizon="FY2026-P12", overrides=[MONTHLY_EVEN])
    ob = _services("120000", INCEPTION, date(2026, 12, 31), convention="MONTHLY_EVEN")
    june_30 = date(2026, 6, 30)
    pins = _pins(
        (_renewal(1, INCEPTION, 36), 2),
        (_renewal(2, june_30, 12), 6),
        (_eac(1, june_30, "55000.00"), 7),
    )
    commission = _cost(
        5, date(2026, 1, 10), "COST_TO_OBTAIN", "30000.00", plan_code="AE-2026", is_incremental=True
    )
    state, trace = _run(ctx, allocated_state([ob], events=[commission], estimates=pins))
    asset = f"{CONTRACT_KEY}/EV-000005"

    june = _measures(state, asset, "FY2026-P06")
    assert _line(state, asset, "FY2026-P06") == usd("833.33")
    assert (june.impaired_cum, june.carrying_amount) == (usd("20000.00"), usd("5000.00"))
    assert june.segments[1] == CostSegment(
        date(2026, 7, 1), date(2026, 12, 31), usd("25000.00"), "PERIOD_CHANGE"
    )
    node = _node(trace, f"cost_recoverable:{GROUP}:FY2026-P06")
    assert (node.value, node.params["costs"], node.params["costs_basis"]) == (
        "5000.00",
        "0",
        "run_off",
    )
    # P07 to P11: recoverable = carrying and no further impairment (exact ties).
    for month in range(7, 12):
        period_key = f"FY2026-P{month:02d}"
        measures = _measures(state, asset, period_key)
        recoverable = _node(trace, f"cost_recoverable:{GROUP}:{period_key}")
        assert usd(recoverable.value) == measures.carrying_amount, period_key
        assert measures.impaired_cum == usd("20000.00"), period_key
    july = _node(trace, f"cost_recoverable:{GROUP}:FY2026-P07")
    # round(55,000.00 × 10,000.00 ÷ 60,000.00) = 9,166.67; (120,000.00 − 70,000.00) − 45,833.33.
    assert (july.value, july.params["costs"], july.params["progress"]) == (
        "4166.67",
        "916667",
        "1/6",
    )
    december = _measures(state, asset, "FY2026-P12")
    assert (december.amortized_cum, december.impaired_cum, december.carrying_amount) == (
        usd("10000.00"),
        usd("20000.00"),
        0,
    )
    assert _node(trace, f"cost_recoverable:{GROUP}:FY2026-P12").value == "0.00"

    # A PROGRESS_INPUT cost of the related obligation effective by t: the progress costs stand.
    progress = _cost(8, date(2026, 7, 31), "PROGRESS_INPUT", "9000.00", obligation_key="P1")
    events = [commission, progress]
    _, with_costs = _run(ctx, allocated_state([ob], events=events, estimates=pins))
    node = _node(with_costs, f"cost_recoverable:{GROUP}:FY2026-P07")
    assert (node.params["costs"], node.params["costs_basis"]) == ("900000", "progress")


def test_s11_r09_impairment_includes_anticipated_renewals() -> None:
    ctx = book_context(entity(months=36), horizon="FY2026-P06", overrides=[MONTHLY_EVEN])
    ob = _services("120000", INCEPTION, date(2026, 12, 31), convention="MONTHLY_EVEN")
    zero, total = Quota1(Fraction(0), 0), Quota1(Fraction(120000), usd("120000"))
    build = TpBuildUp(
        at=INCEPTION,
        before_event_key=None,
        fixed=total,
        vc_constrained=zero,
        vc_excluded=zero,
        expected_returns=zero,
        consideration_payable=zero,
        financing_adjustment=zero,
        noncash=zero,
        sales_tax_excluded=zero,
        out_of_scope=zero,
        total=total,
        allocation_basis=total,
        elements=(),
    )
    events = [
        _cost(
            3, INCEPTION, "COST_TO_OBTAIN", "30000.00", plan_code="COMM-R09", is_incremental=True
        ),
        _cost(4, date(2026, 6, 30), "PROGRESS_INPUT", "50000.00", obligation_key="P1"),
    ]
    asset = f"{CONTRACT_KEY}/EV-000003"

    def world(renewals: str | None) -> tuple[CostLossState, Trace]:
        pins = _pins(
            (_renewal(1, INCEPTION, 36, renewals), 2), (_eac(1, date(2026, 6, 30), "300000.00"), 5)
        )
        st = allocated_state([ob], events=events, estimates=pins)
        return _run(ctx, dataclasses.replace(st, tp_unconstrained={CONTRACT_KEY: (build,)}))

    anticipated, trace = world("240000.00")
    node = _node(trace, f"cost_recoverable:{GROUP}:FY2026-P06")
    # 120,000.00 − 60,000.00 + 240,000.00 − (300,000.00 − 50,000.00) = 50,000.00 ≥ 25,000.00.
    assert (node.value, node.params["renewal"], node.params["consideration_source"]) == (
        "50000.00",
        "24000000",
        "tp_unconstrained",
    )
    june = _measures(anticipated, asset, "FY2026-P06")
    assert (june.impaired_cum, june.carrying_amount) == (0, usd("25000.00"))
    # Without anticipated renewals the recoverable amount is −190,000.00: the asset is impaired.
    none_anticipated, _ = world(None)
    june_none = _measures(none_anticipated, asset, "FY2026-P06")
    assert (june_none.impaired_cum, june_none.carrying_amount) == (usd("25000.00"), 0)


def test_cost_findings() -> None:
    ob = _services("100000", INCEPTION, date(2027, 12, 31))
    missing = [
        _cost(
            2,
            INCEPTION,
            "COST_TO_OBTAIN",
            "5000.00",
            obligation_key="P9",
            plan_code="COMM-X",
            is_incremental=True,
        )
    ]
    state, _ = _run(CTX, allocated_state([ob], events=missing))
    assert [(f.code, f.severity, f.subject_key) for f in state.findings] == [
        ("COST_RELATED_POB_MISSING", "ERROR", f"{CONTRACT_KEY}/EV-000002")
    ]
    assert not state.cost_asset_specs
    proportional = book_context(entity(months=24), overrides=[PROPORTIONAL])
    events = [
        _cost(3, INCEPTION, "COST_TO_OBTAIN", "12000.00", plan_code="COMM-P", is_incremental=True)
    ]
    renewals = _pins((_renewal(1, INCEPTION, 36), 2))
    invalid, _ = _run(proportional, allocated_state([ob], events=events, estimates=renewals))
    assert [(f.code, f.severity) for f in invalid.findings] == [("COST_PATTERN_INVALID", "ERROR")]
    assert not invalid.cost_asset_specs
    # With the contract term as the period the pattern is valid; the test without an EAC version
    # raises COST_NO_EAC once per asset over the 24 period ends.
    valid, trace = _run(proportional, allocated_state([ob], events=events))
    asset = f"{CONTRACT_KEY}/EV-000003"
    assert [(f.code, f.severity, f.subject_key) for f in valid.findings] == [
        ("COST_NO_EAC", "INFO", asset)
    ]
    # Half the related revenue (50,000.00 of 100,000.00) amortises half the asset.
    assert _measures(valid, asset, "FY2026-P12").amortized_cum == usd("6000.00")
    node = _node(trace, f"cost_amortised_cum:{asset}:FY2026-P12")
    assert (node.formula_id, node.params["segments"]) == (
        "cost.amortise.proportional.v1",
        "1200000/1/2",
    )


def test_s11_inv_01_carrying_identity() -> None:
    checked = 0
    for book_code in ("ASC606", "IFRS15"):
        state, _ = _chk_131(book_code)
        for measures in state.cost_asset_measures.values():
            assert measures.carrying_amount == _identity(measures) >= 0
            checked += 1
    assert checked == 2 * 4
