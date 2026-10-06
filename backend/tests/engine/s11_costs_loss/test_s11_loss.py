"""Stage 11 clawbacks, termination acceleration and loss provisions (ENC-16).

ENGINE_SPEC_B §11.2.6 (S11-R-12, S11-R-13), §11.2.7 (S11-R-14 to S11-R-17), §11.3 S11-INV-05 and
S11-INV-06, §11.4 and §11.7 EX-11-B; POLICIES POL-145, POL-150 to POL-153, JET-09e, JET-09f, JET-12
(CHK-132), §5.3 PT-03 (CHK-112) and §6.2 row 11. Stages 09 and 10 run over an ``AllocatedState``
built against the documented contract (support.recognition; D-81 integration after merge): the
stage 06 termination segments, the stage 04 unconstrained build-up and the ``scope_605_35`` flag
are built in the tests. Stage 09 does not build the cost-to-cost measure (ENC-6 is post-rc), so the
loss worlds recognise revenue through a units stand-in with the same progress, and stage 11 reads
those obligations as ``COST_TO_COST``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput, EstimateVersionInput, PeriodInput
from erev_engine.enums import RecognitionMethod, SatisfactionPattern
from erev_engine.stages import s09_recognition, s10_billing_balances, s11_costs_loss
from erev_engine.stages.s11_costs_loss import (
    CostAssetMeasures,
    CostLossState,
    CostSegment,
    LossMeasures,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    PolicyResolver,
    Quota1,
    SegmentCause,
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

MONTHLY_EVEN = ("recognition.time_convention", "ENTITY", "US01", "MONTHLY_EVEN")
YEAR_ENDS = (date(2026, 12, 31), date(2027, 12, 31), date(2028, 12, 31))
YEARS = ("FY2026-P01", "FY2027-P01", "FY2028-P01")
K02 = "K-02"
ASSET_3 = f"{CONTRACT_KEY}/EV-000003"
RELEASE = "LOSS_PROVISION_RELEASE"


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


def _cost_to_cost(st: AllocatedState) -> AllocatedState:
    """The units stand-ins as stage 11 reads them: measured on costs (ENC-6 is post-rc)."""
    obligations = tuple(
        dataclasses.replace(
            ob,
            recognition_method=RecognitionMethod.COST_TO_COST,
            satisfaction_pattern=SatisfactionPattern.OVER_TIME,
            over_time_criterion="OT_A",
        )
        if ob.recognition_method == RecognitionMethod.UNITS_DELIVERED
        else ob
        for ob in st.obligations
    )
    return dataclasses.replace(st, obligations=obligations)


def _run(
    ctx: BookContext, st: AllocatedState, *, cost_to_cost: bool = False
) -> tuple[CostLossState, Trace]:
    """Stages 09 to 11 over one book; the trace re-evaluates node for node, every asset satisfies
    S11-INV-01 and every loss unit S11-INV-05."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    balances = s10_billing_balances.run(ctx, recognition, tb)
    if cost_to_cost:
        balances = dataclasses.replace(balances, allocated=_cost_to_cost(balances.allocated))
    state = s11_costs_loss.run(ctx, balances, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    for measures in state.cost_asset_measures.values():
        assert measures.carrying_amount == _identity(measures) >= 0
    for loss in state.loss_measures.values():
        total_loss = max(0, loss.expected_total_costs - loss.expected_consideration)
        assert 0 <= loss.provision_balance <= (total_loss if loss.eac_version_keys else 0)
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _measures(state: CostLossState, asset: str, period_key: str) -> CostAssetMeasures:
    return state.cost_asset_measures[(asset, period_key)]


def _loss(state: CostLossState, unit_key: str, period_key: str) -> LossMeasures:
    return state.loss_measures[(unit_key, period_key)]


def _line(state: CostLossState, subject_key: str, period_key: str) -> int:
    """The ``COST_AMORTIZATION`` amount of a period, 0 without a line."""
    return sum(
        line.amount
        for line in state.schedule_lines
        if line.schedule_kind == "COST_AMORTIZATION"
        and (line.subject_key, line.period_key) == (subject_key, period_key)
    )


def _cost(
    version: int,
    when: date,
    purpose: str,
    amount: str,
    *,
    contract_key: str = CONTRACT_KEY,
    **members: object,
) -> EventView:
    payload: dict[str, object] = {"purpose": purpose, "amount": Decimal(amount), **members}
    named = members.get("obligation_key")
    keys = [] if named is None else [str(named)]
    return event_view(contract_key, version, "COST_INCURRED", when, payload, obligation_keys=keys)


def _delivery(
    version: int, when: date, quantity: str, key: str, *, contract_key: str = CONTRACT_KEY
) -> EventView:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return event_view(
        contract_key, version, "DELIVERY_RECORDED", when, payload, obligation_keys=[key]
    )


def _units(
    key: str,
    amount: str,
    *,
    contract_key: str = CONTRACT_KEY,
    extra: Sequence[AllocationSegment] = (),
) -> ObligationState:
    """100 units over 2026 to 2028: the stand-in of an obligation measured on costs."""
    goods = segment(
        Fraction(Decimal(amount)),
        usd(amount),
        start=INCEPTION,
        end=YEAR_ENDS[2],
        quantity=Fraction(100),
        measure="UNITS_DELIVERED",
    )
    return obligation(
        key,
        [goods, *extra],
        contract_key=contract_key,
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(100),
    )


def _ratable(key: str, amount: str, end: date) -> ObligationState:
    services = segment(Fraction(Decimal(amount)), usd(amount), start=INCEPTION, end=end)
    return obligation(key, [services], convention="MONTHLY_EVEN")


def _pins(*items: tuple[EstimateVersionInput, int]) -> EstimatePins:
    """APPROVED versions applied by the events of the given stream versions (S01-R-18)."""
    grouped: dict[str, list[EstimatePin]] = {}
    for version, seq in items:
        contract_key = version.estimate_key.split("/", 1)[0]
        order_key = (version.effective_date, seq, f"{contract_key}/EV-{seq:06d}")
        grouped.setdefault(version.estimate_key, []).append(EstimatePin(version, order_key))
    return EstimatePins({key: tuple(pins) for key, pins in grouped.items()})


def _eac(
    element: str,
    version_no: int,
    effective: date,
    expected: str,
    *,
    contract_key: str = CONTRACT_KEY,
    obligation_key: str | None = None,
) -> EstimateVersionInput:
    version = estimate_version(
        f"{contract_key}/{element}", "EAC", version_no, effective, obligation_key=obligation_key
    )
    return dataclasses.replace(version, expected_total_amount=Decimal(expected))


def _renewal(
    version_no: int, effective: date, months: int, expected: str | None = None
) -> EstimateVersionInput:
    version = estimate_version(
        f"{CONTRACT_KEY}/AMORT", "RENEWAL_EXPECTATION", version_no, effective
    )
    amount = None if expected is None else Decimal(expected)
    return dataclasses.replace(version, amortization_months=months, expected_total_amount=amount)


def _scoped(
    external_id: str = CONTRACT_KEY, *, flag: bool = True, book_code: str = "ASC606"
) -> ContractView:
    """A member contract whose T-CON-01 ``scope_605_35`` is ``flag``."""
    view = contract_view(external_id, book_code=book_code)
    return dataclasses.replace(view, header=dataclasses.replace(view.header, scope_605_35=flag))


def _annual(years: int = 3) -> EntityInput:
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


def _build(fixed: str, bonus: str) -> TpBuildUp:
    """A stage 04 unconstrained build-up: fixed consideration plus the unconstrained bonus."""
    zero = Quota1(Fraction(0), 0)
    base = Quota1(Fraction(Decimal(fixed)), usd(fixed))
    vc = Quota1(Fraction(Decimal(bonus)), usd(bonus))
    total = Quota1(base.exact + vc.exact, base.posted + vc.posted)
    return TpBuildUp(
        at=INCEPTION,
        before_event_key=None,
        fixed=base,
        vc_constrained=vc,
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


def _period_policy(ctx: BookContext, code: str, value: str) -> BookContext:
    """The book context with every value of ``code`` replaced (pin P policies such as POL-145)."""
    policies = tuple(
        dataclasses.replace(policy, value=value) if policy.code == code else policy
        for policy in ctx.policies.all()
    )
    return dataclasses.replace(ctx, policies=PolicyResolver(policies))


def _chk_132(*, bonus: bool = False, horizon: str | None = None) -> tuple[CostLossState, Trace]:
    """EX-11-B: fixed price 1,000,000.00 measured on costs; EAC 900,000.00 in Year 1, then
    1,100,000.00; costs 450,000.00, 770,000.00 and 1,100,000.00 cumulative. The units stand-in
    delivers 50, 20 and 30 of 100 units at the year ends (progress 50%, 70% and 100%)."""
    ctx = book_context(_annual(), horizon=horizon)
    events = [
        _delivery(2, YEAR_ENDS[0], "50", "P1"),
        _cost(3, YEAR_ENDS[0], "PROGRESS_INPUT", "450000.00", obligation_key="P1"),
        _delivery(5, YEAR_ENDS[1], "20", "P1"),
        _cost(6, YEAR_ENDS[1], "PROGRESS_INPUT", "320000.00", obligation_key="P1"),
        _delivery(8, YEAR_ENDS[2], "30", "P1"),
        _cost(9, YEAR_ENDS[2], "PROGRESS_INPUT", "330000.00", obligation_key="P1"),
    ]
    versions = [
        (_eac("EAC", 1, YEAR_ENDS[0], "900000.00"), 4),
        (_eac("EAC", 2, YEAR_ENDS[1], "1100000.00"), 7),
    ]
    extra: list[AllocationSegment] = []
    if bonus:
        # The bonus of 20,000.00 is earned in Year 3: the constrained allocation rises then.
        earned = f"{CONTRACT_KEY}/EV-000010"
        extra.append(
            segment(
                Fraction(1020000),
                usd("1020000.00"),
                start=INCEPTION,
                end=YEAR_ENDS[2],
                effective=YEAR_ENDS[2],
                cause=SegmentCause.TP_CHANGE,
                event_key=earned,
                quantity=Fraction(100),
                measure="UNITS_DELIVERED",
            )
        )
        bonus_version = estimate_version(
            f"{CONTRACT_KEY}/BONUS", "VARIABLE_CONSIDERATION", 1, YEAR_ENDS[2]
        )
        versions.append((bonus_version, 10))
        payload = {"estimate_key": f"{CONTRACT_KEY}/BONUS"}
        events.append(event_view(CONTRACT_KEY, 10, "ESTIMATE_CHANGED", YEAR_ENDS[2], payload))
    pins = _pins(*versions)
    ob = _units("P1", "1000000.00", extra=extra)
    st = allocated_state([ob], contracts=[_scoped()], events=events, estimates=pins)
    if bonus:
        build = _build("1000000.00", "20000.00")
        st = dataclasses.replace(st, tp_unconstrained={CONTRACT_KEY: (build,)})
    return _run(ctx, st, cost_to_cost=True)


def test_chk_132_loss_provision() -> None:
    state, trace = _chk_132()
    rows = [_loss(state, CONTRACT_KEY, period_key) for period_key in YEARS]
    assert [(m.revenue_to_date, m.costs_to_date, m.expected_total_costs) for m in rows] == [
        (usd("500000.00"), usd("450000.00"), usd("900000.00")),
        (usd("700000.00"), usd("770000.00"), usd("1100000.00")),
        (usd("1000000.00"), usd("1100000.00"), usd("1100000.00")),
    ]
    assert {m.expected_consideration for m in rows} == {usd("1000000.00")}
    # Total expected loss 0.00 / 100,000.00 / 100,000.00; margin loss 0.00 / 70,000.00 / 100,000.00.
    assert [max(0, m.expected_total_costs - m.expected_consideration) for m in rows] == [
        0,
        usd("100000.00"),
        usd("100000.00"),
    ]
    assert [max(0, m.costs_to_date - m.revenue_to_date) for m in rows] == [
        0,
        usd("70000.00"),
        usd("100000.00"),
    ]
    assert [m.provision_balance for m in rows] == [0, usd("30000.00"), 0]
    assert [m.provision_movement for m in rows] == [0, usd("30000.00"), -usd("30000.00")]
    assert [m.expected_margin for m in rows] == [
        usd("100000.00"),
        -usd("100000.00"),
        -usd("100000.00"),
    ]
    assert {(m.unit, m.obligation_key, m.measurement_basis) for m in rows} == {
        ("CONTRACT", None, "ASC_605_35")
    }
    # S11-INV-05 at completion: costs = EAC and revenue = TP_u, so nothing is required.
    assert (rows[2].costs_to_date, rows[2].revenue_to_date) == (
        rows[2].expected_total_costs,
        rows[2].expected_consideration,
    )
    node = _node(trace, f"loss_provision_required:{CONTRACT_KEY}:FY2027-P01")
    assert (
        node.formula_id,
        node.value,
        node.params["eac"],
        node.params["costs"],
        node.params["eac_versions"],
        node.inputs[0],
    ) == (
        "loss.required_provision.v1",
        "30000.00",
        "110000000",
        "77000000",
        f"{CONTRACT_KEY}/EAC@v2",
        f"tp_unconstrained_credit_adjusted:{CONTRACT_KEY}:FY2027-P01",
    )
    tp = _node(trace, f"tp_unconstrained_credit_adjusted:{CONTRACT_KEY}:FY2027-P01")
    assert (tp.formula_id, tp.value, tp.params["source"]) == (
        "loss.tp_unconstrained.v1",
        "1000000.00",
        "allocation",
    )
    movement = _node(trace, f"provision_movement:{CONTRACT_KEY}:FY2028-P01")
    assert (movement.formula_id, movement.value, movement.inputs) == (
        "loss.movement.v1",
        "-30000.00",
        (
            f"loss_provision_required:{CONTRACT_KEY}:FY2028-P01",
            f"loss_provision_required:{CONTRACT_KEY}:FY2027-P01",
        ),
    )
    targets = {(t.measure, t.period_key): t.value for t in state.loss_provisions}
    assert targets[("provision_movement", "FY2027-P01")] == usd("30000.00")
    assert {t.measure for t in state.loss_provisions} == {
        "tp_unconstrained_credit_adjusted",
        "expected_margin",
        "loss_provision_required",
        "provision_movement",
    }
    assert not [f for f in state.findings if f.code == "LOSS_EAC_MISSING"]


def test_ex_11_b_constrained_bonus_variant() -> None:
    state, trace = _chk_132(bonus=True)
    rows = [_loss(state, CONTRACT_KEY, period_key) for period_key in YEARS]
    # TP_u is unconstrained: 1,020,000.00 in every year, while revenue waits for the bonus.
    assert {m.expected_consideration for m in rows} == {usd("1020000.00")}
    assert [max(0, m.expected_total_costs - m.expected_consideration) for m in rows] == [
        0,
        usd("80000.00"),
        usd("80000.00"),
    ]
    assert [m.revenue_to_date for m in rows] == [
        usd("500000.00"),
        usd("700000.00"),
        usd("1020000.00"),
    ]
    assert rows[2].revenue_to_date - rows[1].revenue_to_date == usd("320000.00")
    assert [m.provision_balance for m in rows] == [0, usd("10000.00"), 0]
    # JET-12: Year 2 Dr LOSS_EXPENSE 10,000.00; Year 3 release 10,000.00.
    assert [m.provision_movement for m in rows] == [0, usd("10000.00"), -usd("10000.00")]
    tp = _node(trace, f"tp_unconstrained_credit_adjusted:{CONTRACT_KEY}:FY2027-P01")
    assert (tp.value, tp.params["source"], tp.params["total"]) == (
        "1020000.00",
        "tp_unconstrained",
        "1020000",
    )


# The calendar covers the 36-month amortisation period; the horizon is the end of 2027.
CHK_112_CTX = book_context(entity(months=36), horizon="FY2027-P12", overrides=[MONTHLY_EVEN])


def _chk_112(ctx: BookContext) -> tuple[CostLossState, Trace]:
    """PT-03 CHK-112: 240,000.00 over 2026 and 2027; a commission of 36,000.00 amortised over 36
    months (renewal commissions not commensurate, POL-141); a full termination at month 18 with a
    refund of 60,000.00. The stage 06 ``TERMINATION`` segment gives f = 1 from 30 June 2027 at the
    revenue recognised through that date (EX-06-J)."""
    terminated_on = date(2027, 6, 30)
    subscription = segment(
        Fraction(240000), usd("240000.00"), start=INCEPTION, end=date(2027, 12, 31)
    )
    ended = segment(
        Fraction(180000),
        usd("180000.00"),
        start=INCEPTION,
        end=terminated_on,
        effective=terminated_on,
        cause=SegmentCause.TERMINATION,
        event_key=f"{CONTRACT_KEY}/EV-000004",
    )
    ob = dataclasses.replace(
        obligation("P1", [subscription, ended], convention="MONTHLY_EVEN"),
        terminated_on=terminated_on,
    )
    termination = {
        "modification_id": "MOD-T",
        "termination_kind": "FULL",
        "refund_amount": Decimal("60000.00"),
    }
    events = [
        _cost(
            3,
            INCEPTION,
            "COST_TO_OBTAIN",
            "36000.00",
            payee="REP-7",
            plan_code="COMM-112",
            is_incremental=True,
        ),
        event_view(
            CONTRACT_KEY,
            4,
            "CONTRACT_TERMINATED",
            terminated_on,
            termination,
            obligation_keys=["P1"],
        ),
    ]
    st = allocated_state([ob], events=events, estimates=_pins((_renewal(1, INCEPTION, 36), 2)))
    return _run(ctx, st)


def test_chk_112_termination_acceleration() -> None:
    ctx = CHK_112_CTX
    state, trace = _chk_112(ctx)
    (spec,) = state.cost_asset_specs
    assert (spec.amortization_months, spec.amortization_end_date) == (36, date(2028, 12, 31))
    may, june, july = (
        _measures(state, ASSET_3, period_key)
        for period_key in ("FY2027-P05", "FY2027-P06", "FY2027-P07")
    )
    assert (may.amortized_cum, may.accelerated_cum, may.carrying_amount) == (
        usd("17000.00"),
        0,
        usd("19000.00"),
    )
    # JET-09e: 36,000.00 − 18 × 1,000.00 = 18,000.00 accelerated; the cost asset is 0.00.
    assert (june.amortized_cum, june.accelerated_cum, june.carrying_amount) == (
        usd("18000.00"),
        usd("18000.00"),
        0,
    )
    assert june.segments[-1] == CostSegment(date(2027, 7, 1), date(2027, 7, 1), 0, "ACCELERATION")
    assert (july.amortized_cum, july.carrying_amount, july.remaining_months) == (
        usd("18000.00"),
        0,
        0,
    )
    assert (_line(state, ASSET_3, "FY2027-P06"), _line(state, ASSET_3, "FY2027-P07")) == (
        usd("1000.00"),
        0,
    )
    node = _node(trace, f"cost_accelerated_cum:{ASSET_3}:FY2027-P06")
    assert (
        node.formula_id,
        node.value,
        node.params["policy"],
        node.params["carrying"],
        node.params["before"],
        node.params["after"],
        node.params["all_ended"],
    ) == (
        "cost.accelerate.v1",
        "18000.00",
        "ACCELERATE_TO_REMAINING_BENEFIT",
        "1800000",
        "6000000",
        "0",
        "true",
    )
    assert _node(trace, f"carrying_amount:{ASSET_3}:FY2027-P06").params["signs"] == "+|-|-|+|-|-"
    # Under POL-145 CONTINUE nothing accelerates; with nothing left to recognise, the period-end
    # test finds a recoverable amount of 0.00 and impairs the 18,000.00 instead (JET-09c).
    continued, continued_trace = _chk_112(
        _period_policy(ctx, "costs.termination_acceleration", "CONTINUE")
    )
    kept = _measures(continued, ASSET_3, "FY2027-P06")
    assert (kept.accelerated_cum, kept.impaired_cum, kept.carrying_amount) == (
        0,
        usd("18000.00"),
        0,
    )
    continue_node = _node(continued_trace, f"cost_accelerated_cum:{ASSET_3}:FY2027-P06")
    assert (continue_node.value, continue_node.params["policy"]) == ("0.00", "CONTINUE")


def test_s11_r13_partial_termination() -> None:
    """Additional: a termination of one of two related obligations accelerates by 1 − ρ."""
    ctx = book_context(entity(months=24), overrides=[MONTHLY_EVEN])
    terminated_on, end = date(2026, 12, 31), date(2027, 12, 31)
    kept = _ratable("P1", "120000.00", end)
    ended = segment(
        Fraction(60000),
        usd("60000.00"),
        start=INCEPTION,
        end=terminated_on,
        effective=terminated_on,
        cause=SegmentCause.TERMINATION,
        event_key=f"{CONTRACT_KEY}/EV-000003",
    )
    services = segment(Fraction(120000), usd("120000.00"), start=INCEPTION, end=end)
    removed = dataclasses.replace(
        obligation("P2", [services, ended], convention="MONTHLY_EVEN"),
        terminated_on=terminated_on,
    )
    payload = {"modification_id": "MOD-P", "termination_kind": "PARTIAL", "obligation_keys": ["P2"]}
    events = [
        _cost(
            2,
            INCEPTION,
            "COST_TO_OBTAIN",
            "24000.00",
            payee="REP-1",
            plan_code="COMM-P",
            is_incremental=True,
        ),
        event_view(
            CONTRACT_KEY, 3, "CONTRACT_TERMINATED", terminated_on, payload, obligation_keys=["P2"]
        ),
    ]
    state, trace = _run(ctx, allocated_state([kept, removed], events=events))
    asset = f"{CONTRACT_KEY}/EV-000002"
    december = _measures(state, asset, "FY2026-P12")
    # ρ = 60,000.00 remaining on P1 ÷ (60,000.00 on P1 + 60,000.00 on P2) = 1/2 of 12,000.00.
    assert (december.amortized_cum, december.accelerated_cum, december.carrying_amount) == (
        usd("12000.00"),
        usd("6000.00"),
        usd("6000.00"),
    )
    assert december.segments[-1] == CostSegment(
        date(2027, 1, 1), end, usd("6000.00"), "ACCELERATION"
    )
    node = _node(trace, f"cost_accelerated_cum:{asset}:FY2026-P12")
    assert (node.params["before"], node.params["after"], node.params["all_ended"]) == (
        "12000000",
        "6000000",
        "false",
    )
    assert _line(state, asset, "FY2027-P01") == usd("500.00")
    assert _measures(state, asset, "FY2027-P12").carrying_amount == 0


def test_s11_r12_clawback() -> None:
    ctx = book_context(entity(months=24), overrides=[MONTHLY_EVEN])
    ob = _ratable("P1", "100000.00", date(2027, 12, 31))
    commission: dict[str, object] = {"payee": "REP-1", "plan_code": "COMM-CB"}
    events = [
        _cost(2, INCEPTION, "COST_TO_OBTAIN", "2400.00", is_incremental=True, **commission),
        _cost(3, date(2026, 3, 1), "COST_TO_OBTAIN", "12000.00", is_incremental=True, **commission),
        _cost(
            4,
            INCEPTION,
            "COST_TO_OBTAIN",
            "6000.00",
            payee="REP-2",
            plan_code="COMM-CB",
            is_incremental=True,
        ),
        _cost(
            5,
            date(2026, 6, 30),
            "COST_TO_OBTAIN",
            "3000.00",
            cost_adjustment="CLAWBACK",
            **commission,
        ),
        _cost(
            6,
            date(2026, 9, 30),
            "COST_TO_OBTAIN",
            "20000.00",
            cost_adjustment="CLAWBACK",
            **commission,
        ),
    ]
    state, trace = _run(ctx, allocated_state([ob], events=events))
    older, newer, other = (f"{CONTRACT_KEY}/EV-00000{n}" for n in (2, 3, 4))
    assert [spec.asset_key for spec in state.cost_asset_specs] == [older, newer, other]
    assert not state.expensed_costs  # a clawback is neither capitalised nor expensed
    # 30 June: 3,000.00 takes the older asset's carrying 1,800.00, then 1,200.00 of 9,000.00.
    june = [_measures(state, asset, "FY2026-P06") for asset in (older, newer, other)]
    assert [(m.clawback_cum, m.carrying_amount) for m in june] == [
        (usd("1800.00"), 0),
        (usd("1200.00"), usd("7800.00")),
        (0, usd("4500.00")),
    ]
    assert june[1].segments[-1] == CostSegment(
        date(2026, 7, 1), date(2027, 12, 31), usd("7800.00"), "CLAWBACK"
    )
    assert _line(state, newer, "FY2026-P07") == usd("433.33")  # 7,800.00 over 18 months
    node = _node(trace, f"cost_clawback_cum:{newer}:FY2026-P06")
    assert (node.formula_id, node.value, node.params["carrying"], node.params["taken_before"]) == (
        "cost.clawback.v1",
        "1200.00",
        "900000",
        "180000",
    )
    # 30 September: 20,000.00 finds a carrying amount of 6,500.00; the excess stays in the ERP.
    september = _measures(state, newer, "FY2026-P09")
    assert (september.amortized_cum, september.clawback_cum, september.carrying_amount) == (
        usd("4300.00"),
        usd("7700.00"),
        0,
    )
    later = _node(trace, f"cost_clawback_cum:{newer}:FY2026-P09")
    assert (later.params["carrying"], later.params["taken_before"]) == ("900000|650000", "180000|0")
    assert _measures(state, older, "FY2026-P09").clawback_cum == usd("1800.00")


def _scope_world(
    book_code: str, overrides: Iterable[tuple[str, str, str, str]] = ()
) -> tuple[CostLossState, Trace]:
    """K-01 (``scope_605_35`` true; P1 600,000.00 and P2 400,000.00) and K-02 (flag false; Q1
    500,000.00), each half delivered at the end of 2026."""
    ctx = book_context(_annual(), book_code=book_code, overrides=overrides)
    y1 = YEAR_ENDS[0]
    obligations = [
        _units("P1", "600000.00"),
        _units("P2", "400000.00"),
        _units("Q1", "500000.00", contract_key=K02),
    ]
    events = [
        _delivery(2, y1, "50", "P1"),
        _delivery(3, y1, "50", "P2"),
        _cost(4, y1, "PROGRESS_INPUT", "350000.00", obligation_key="P1"),
        _cost(5, y1, "PROGRESS_INPUT", "190000.00", obligation_key="P2"),
        _delivery(2, y1, "50", "Q1", contract_key=K02),
        _cost(3, y1, "PROGRESS_INPUT", "280000.00", contract_key=K02),
    ]
    pins = _pins(
        (_eac("EAC-P1", 1, y1, "700000.00", obligation_key="P1"), 6),
        (_eac("EAC-P2", 1, y1, "380000.00", obligation_key="P2"), 7),
        (_eac("EAC", 1, y1, "600000.00", contract_key=K02), 4),
        (_eac("EAC_IAS37", 1, y1, "550000.00", contract_key=K02), 5),
    )
    contracts = [_scoped(book_code=book_code), _scoped(K02, flag=False, book_code=book_code)]
    st = allocated_state(obligations, contracts=contracts, events=events, estimates=pins)
    return _run(ctx, st, cost_to_cost=True)


def test_s11_r15_books_scope() -> None:
    year_1 = YEARS[0]
    us, _ = _scope_world("ASC606", overrides=[("loss.unit", "ENTITY", "US01", "POB")])
    assert sorted(us.loss_measures) == [
        (f"{CONTRACT_KEY}/{key}", period_key) for key in ("P1", "P2") for period_key in YEARS
    ]
    p1, p2 = (_loss(us, f"{CONTRACT_KEY}/{key}", year_1) for key in ("P1", "P2"))
    # P1: 700,000.00 − 600,000.00 = 100,000.00 less the margin loss 350,000.00 − 300,000.00.
    assert (
        p1.unit,
        p1.obligation_key,
        p1.expected_consideration,
        p1.expected_total_costs,
        p1.costs_to_date,
        p1.revenue_to_date,
        p1.provision_balance,
        p1.measurement_basis,
    ) == (
        "POB",
        "P1",
        usd("600000.00"),
        usd("700000.00"),
        usd("350000.00"),
        usd("300000.00"),
        usd("50000.00"),
        "ASC_605_35",
    )
    assert (p2.expected_total_costs, p2.provision_balance) == (usd("380000.00"), 0)
    assert not [t for t in us.loss_provisions if t.subject_key.startswith(K02)]
    # IFRS15 tests every contract with an EAC version, at contract level.
    ifrs, _ = _scope_world("IFRS15")
    assert sorted({unit_key for unit_key, _ in ifrs.loss_measures}) == [CONTRACT_KEY, K02]
    k01, k02 = _loss(ifrs, CONTRACT_KEY, year_1), _loss(ifrs, K02, year_1)
    # K-01: 1,080,000.00 − 1,000,000.00 = 80,000.00 less the margin loss 540,000.00 − 500,000.00.
    assert (k01.unit, k01.measurement_basis, k01.expected_total_costs, k01.provision_balance) == (
        "CONTRACT",
        "IAS_37",
        usd("1080000.00"),
        usd("40000.00"),
    )
    # K-02 uses the IAS 37.68A costs of EAC_IAS37: 50,000.00 less the margin loss 30,000.00.
    assert (k02.eac_version_keys, k02.expected_total_costs, k02.provision_balance) == (
        (f"{K02}/EAC_IAS37@v1",),
        usd("550000.00"),
        usd("20000.00"),
    )


def test_s11_r14_loss_eac_missing() -> None:
    ctx = book_context(_annual())
    y1 = YEAR_ENDS[0]
    obligations = [_units("P1", "1000000.00"), _units("Q1", "500000.00", contract_key=K02)]
    events = [
        _delivery(2, y1, "30", "P1"),
        _cost(3, y1, "PROGRESS_INPUT", "300000.00", obligation_key="P1"),
        _delivery(2, y1, "30", "Q1", contract_key=K02),
        _cost(3, y1, "PROGRESS_INPUT", "150000.00", contract_key=K02),
    ]
    pins = _pins((_eac("EAC", 1, YEAR_ENDS[1], "900000.00"), 4))
    contracts = [_scoped(), _scoped(K02, flag=False)]
    st = allocated_state(obligations, contracts=contracts, events=events, estimates=pins)
    state, trace = _run(ctx, st, cost_to_cost=True)
    missing = [
        (f.code, f.severity, f.subject_key, f.detail["period_key"])
        for f in state.findings
        if f.code == "LOSS_EAC_MISSING"
    ]
    # The scoped contract has no approved EAC version at the end of 2026; K-02 is outside the scope.
    assert missing == [("LOSS_EAC_MISSING", "WARNING", CONTRACT_KEY, "FY2026-P01")]
    first = _loss(state, CONTRACT_KEY, YEARS[0])
    assert (first.provision_balance, first.expected_total_costs, first.eac_version_keys) == (
        0,
        0,
        (),
    )
    assert _node(trace, f"loss_provision_required:{CONTRACT_KEY}:FY2026-P01").params["eac"] == (
        "none"
    )
    # The same unit measured on units rather than costs raises nothing.
    units, _ = _run(ctx, st)
    assert not [f for f in units.findings if f.code == "LOSS_EAC_MISSING"]


def test_s11_r17_release_schedule_informational() -> None:
    # CHK-132 at the end of Year 2: the unit is not deterministic, so the provision of 30,000.00 is
    # one line in the period of the latest unit end date.
    state, _ = _chk_132(horizon="FY2027-P01")
    lines = [line for line in state.schedule_lines if line.schedule_kind == RELEASE]
    assert [
        (line.subject_type, line.subject_key, line.period_key, line.amount, line.trace_node_id)
        for line in lines
    ] == [
        (
            "contract",
            CONTRACT_KEY,
            "FY2028-P01",
            usd("30000.00"),
            f"loss_provision_required:{CONTRACT_KEY}:FY2027-P01",
        )
    ]
    # A time-elapsed unit releases in proportion to its remaining deterministic revenue.
    ctx = book_context(entity(months=24), horizon="FY2026-P06")
    ob = _ratable("P1", "120000.00", date(2027, 12, 31))
    pins = _pins((_eac("EAC", 1, INCEPTION, "150000.00"), 2))
    ratable, _ = _run(ctx, allocated_state([ob], contracts=[_scoped()], estimates=pins))
    june = _loss(ratable, CONTRACT_KEY, "FY2026-P06")
    assert (june.revenue_to_date, june.provision_balance) == (usd("30000.00"), usd("30000.00"))
    released = [line for line in ratable.schedule_lines if line.schedule_kind == RELEASE]
    assert [line.period_key for line in released] == [
        f"FY{year}-P{month:02d}"
        for year, months in ((2026, range(7, 13)), (2027, range(1, 13)))
        for month in months
    ]
    assert (released[0].amount, sum(line.amount for line in released)) == (
        usd("1666.67"),
        usd("30000.00"),
    )
    assert {line.is_released_at_close for line in [*lines, *released]} == {False}


def test_s11_r17_a_usage_unit_with_a_fixed_fee_is_released_at_its_end_date() -> None:
    """S11-R-17 asks the method of every unit obligation, not the predicate of S09-R-45 (rev 1.126;
    item ENG-USAGE-FIXED-SCHEDULE-1; supervisor ruling R-116 (a)): the time-elapsed case above with
    the obligation measured by usage. Stage 09 calls its fixed fee deterministic and schedules it to
    the term end, but the fee's lines are not the whole of the unit's remaining revenue — its usage
    fees stand on no schedule — so the provision is not released over them: it stays one line in the
    period of the unit's end date."""
    ctx = book_context(entity(months=24), horizon="FY2026-P06", overrides=[MONTHLY_EVEN])
    end = date(2027, 12, 31)
    fee = segment(Fraction(120000), usd("120000.00"), start=INCEPTION, end=end, measure="USAGE")
    fees = segment(Fraction(0), 0, start=INCEPTION, end=end, component="PERIOD_VC", measure="USAGE")
    pins = _pins((_eac("EAC", 1, INCEPTION, "150000.00"), 2))
    ob = obligation("P1", [fee, fees], method="USAGE", convention=None)
    assert s09_recognition.is_deterministic(ob)
    state, _ = _run(ctx, allocated_state([ob], contracts=[_scoped()], estimates=pins))
    june = _loss(state, CONTRACT_KEY, "FY2026-P06")
    assert (june.revenue_to_date, june.provision_balance) == (usd("30000.00"), usd("30000.00"))
    # The fee is on the schedule to its term end: eighteen months of 5,000.00 after June 2026.
    after_june = [
        line.amount
        for line in state.balances.recognition.schedule_lines
        if line.schedule_kind == "REVENUE" and line.period_key > "FY2026-P06"
    ]
    assert after_june == [usd("5000.00")] * 18
    released = [line for line in state.schedule_lines if line.schedule_kind == RELEASE]
    assert [(line.period_key, line.amount, line.is_released_at_close) for line in released] == [
        ("FY2027-P12", usd("30000.00"), False)
    ]


def _chk_131(book_code: str) -> tuple[CostLossState, Trace]:
    """CHK-131 (ENC-15): 40,000.00 over 48 months; recoverable 15,000.00 at the end of Year 1."""
    ctx = book_context(_annual(4), book_code=book_code, overrides=[MONTHLY_EVEN])
    ob = _ratable("P1", "150000.00", date(2027, 12, 31))
    pins = _pins(
        (_renewal(1, INCEPTION, 48, "25000.00"), 2),
        (_eac("EAC", 1, YEAR_ENDS[0], "170000.00"), 5),
    )
    events = [
        _cost(
            3, INCEPTION, "COST_TO_OBTAIN", "40000.00", plan_code="COMM-131", is_incremental=True
        ),
        _cost(4, YEAR_ENDS[0], "PROGRESS_INPUT", "85000.00", obligation_key="P1"),
        _cost(6, YEAR_ENDS[1], "PROGRESS_INPUT", "85000.00", obligation_key="P1"),
    ]
    view = contract_view(statuses=((INCEPTION, "ACTIVE"),), book_code=book_code)
    return _run(ctx, allocated_state([ob], contracts=[view], events=events, estimates=pins))


def _rollforward(state: CostLossState) -> int:
    """opening + additions − amortisation − impairment + reversal − clawback − acceleration =
    closing per asset and period (S11-INV-06); returns the number of periods checked."""
    checked = 0
    previous: dict[str, CostAssetMeasures] = {}
    ordered = sorted(state.cost_asset_measures.values(), key=lambda m: (m.asset_key, m.as_of))
    for m in ordered:
        before = previous.get(m.asset_key)
        points = (
            (0, 0, 0, 0, 0, 0, 0)
            if before is None
            else (
                before.carrying_amount,
                before.capitalized_cum,
                before.amortized_cum,
                before.impaired_cum,
                before.impairment_reversed_cum,
                before.clawback_cum,
                before.accelerated_cum,
            )
        )
        opening, capitalised, amortised, impaired, reversed_, clawback, accelerated = points
        closing = (
            opening
            + (m.capitalized_cum - capitalised)
            - (m.amortized_cum - amortised)
            - (m.impaired_cum - impaired)
            + (m.impairment_reversed_cum - reversed_)
            - (m.clawback_cum - clawback)
            - (m.accelerated_cum - accelerated)
        )
        assert closing == m.carrying_amount, (m.asset_key, m.period_key)
        previous[m.asset_key] = m
        checked += 1
    return checked


def test_s11_inv_06_cost_rollforward_identity() -> None:
    assert sum(_rollforward(_chk_131(book_code)[0]) for book_code in ("ASC606", "IFRS15")) == 8
    chk_112, _ = _chk_112(CHK_112_CTX)
    assert _rollforward(chk_112) == 24
    june = _measures(chk_112, ASSET_3, "FY2027-P06")
    may = _measures(chk_112, ASSET_3, "FY2027-P05")
    # June: opening 19,000.00 − amortisation 1,000.00 − acceleration 18,000.00 = closing 0.00.
    assert (
        may.carrying_amount,
        june.amortized_cum - may.amortized_cum,
        june.accelerated_cum - may.accelerated_cum,
        june.carrying_amount,
    ) == (usd("19000.00"), usd("1000.00"), usd("18000.00"), 0)
