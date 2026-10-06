"""Stage 08 prior-period decomposition.

ENGINE_SPEC §8.5 S08-R-14 to S08-R-16 and §8.6 S08-INV-04; ENGINE_SPEC_B §15.2.4 and §15.7 EX-15-C;
POLICIES ALG-10 §2.11.3 (CHK-100, CHK-101), §5.1 PT-01 (CHK-110 prior-period column) and ALG-09
step 7. Stages 02 to 06 are built in other lanes, so the tests build ``AllocatedState`` through
``support/recognition.py`` and bind a fake ``price_at`` that follows the §4.2 contract (D-81
integration after merge). Cost-to-cost progress is ENC-5, deferred post-rc, so EX-15-C is measured
with ``UNITS_DELIVERED`` where the costs incurred are the units and the EAC is the contracted
quantity (L2-5-Q-5). Every trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput, EstimateVersionInput, PeriodInput, PostedAmountInput
from erev_engine.dates import month_end
from erev_engine.errors import EngineError
from erev_engine.money import largest_remainder, round_half_up
from erev_engine.stages import s08_estimates_late_events
from erev_engine.stages.s08_estimates_late_events import decompose_prior_period
from erev_engine.stages.s09_recognition import target_at_position
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    ObligationState,
    PostedIndex,
    Quota1,
    SegmentCause,
    Target,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    estimate_version,
    event_view,
    obligation,
    segment,
    usd,
)

PriceAt = s08_estimates_late_events.PriceAt
ENTITY = bundles.ENTITY_CODE
JANUARY_2023 = date(2023, 1, 1)
GOLDEN_CONTRACT_1 = (  # (POB, quantity, extended SSP); price 1,300.00 (legacy 02 §5.3)
    ("POB #1", "5", 500),
    ("POB #2", "2", 368),
    ("POB #3", "1", 150),
    ("POB #4", "1000", 1000),
)


def _trace(tb: TraceBuilder) -> Trace:
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _parts(node: TraceNode) -> list[tuple[str, str]]:
    return [(ref.ref_id, ref.detail["value"]) for ref in node.inputs if isinstance(ref, SourceRef)]


def _version(
    element: str, kind: str, version_no: int, effective: date, *, amount: str
) -> EstimateVersionInput:
    base = estimate_version(f"{CONTRACT_KEY}/{element}", kind, version_no, effective)
    return dataclasses.replace(
        base, allocation_target="CONTRACT", constrained_amount=Decimal(amount)
    )


def _estimate(stream_version: int, version: EstimateVersionInput) -> EventView:
    payload = {"estimate_version_id": version.version_key}
    return event_view(
        CONTRACT_KEY, stream_version, "ESTIMATE_CHANGED", version.effective_date, payload
    )


def _progress(stream_version: int, effective: date, ratio: str, obligation_key: str) -> EventView:
    payload = {
        "obligation_key": obligation_key,
        "cumulative_progress_ratio": Decimal(ratio),
        "measure": "OUTPUT_PERCENT",
    }
    return event_view(
        CONTRACT_KEY,
        stream_version,
        "PROGRESS_RECORDED",
        effective,
        payload,
        obligation_keys=[obligation_key],
    )


def _delivery(
    contract_key: str,
    stream_version: int,
    effective: date,
    obligation_key: str,
    quantity: str,
    trigger: str = "CONTROL_TRANSFER",
) -> EventView:
    payload = {"obligation_key": obligation_key, "quantity": Decimal(quantity), "trigger": trigger}
    return event_view(
        contract_key,
        stream_version,
        "DELIVERY_RECORDED",
        effective,
        payload,
        obligation_keys=[obligation_key],
    )


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


def _price_at(fixed: Callable[[date], int], amounts: Mapping[str, int]) -> PriceAt:
    """A fake stage 04 ``price_at`` (ENGINE_SPEC §4.2; D-81): fixed plus the pinned versions."""

    def price(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        total = fixed(at)
        for estimate_key in sorted(st.estimates.pins):
            version = st.estimates.pin(estimate_key, at, before)
            if version is not None:
                total += amounts.get(version.version_key, 0)
        quota = Quota1(Fraction(total, 100), total)
        zero = Quota1(Fraction(0), 0)
        key = None if before is None else before.event_key
        return TpBuildUp(at, key, quota, *(zero,) * 8, quota, quota, ())

    return price


def _fold(
    ctx: BookContext,
    st: AllocatedState,
    events: Sequence[EventView],
    price_at: PriceAt,
    tb: TraceBuilder,
) -> AllocatedState:
    for ev in events:
        st = s08_estimates_late_events.apply(ctx, st, ev, tb, price_at=price_at)
    return st


def _single(targets: tuple[Target, ...]) -> Target:
    (target,) = targets
    return target


def test_chk_100_prior_period_portion() -> None:
    ctx = book_context(bundles.entity(months=36))
    asset = segment(
        Fraction(2505000), usd("2505000.00"), start=date(2026, 1, 1), end=date(2028, 12, 31)
    )
    ob = obligation("L1-ASSET", [asset], method="OUTPUT_PERCENT", convention=None)
    v1 = _version("VC-BONUS", "VARIABLE_CONSIDERATION", 1, date(2026, 1, 1), amount="0.00")
    v2 = _version("VC-BONUS", "VARIABLE_CONSIDERATION", 2, date(2027, 1, 1), amount="150000.00")
    first, second = _estimate(3, v1), _estimate(8, v2)
    events = [
        first,
        _progress(6, date(2026, 12, 31), "0.40", "L1-ASSET"),
        second,
        _progress(9, date(2027, 12, 31), "0.80", "L1-ASSET"),
    ]
    st = allocated_state([ob], events=events, estimates=_pins((v1, first), (v2, second)))
    price_at = _price_at(lambda at: usd("2505000.00"), {v2.version_key: usd("150000.00")})
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    folded = _fold(ctx, st, [first, second], price_at, tb)

    year_2 = [
        _single(decompose_prior_period(ctx, folded, f"FY2027-P{month:02d}", tb))
        for month in range(1, 13)
    ]
    assert [target.value for target in year_2] == [usd("60000.00"), *[0] * 11]
    january = year_2[0]
    subject = f"{CONTRACT_KEY}/L1-ASSET"
    assert (january.measure, january.subject_key, january.entity, january.cause) == (
        "revenue_prior_period",
        subject,
        ENTITY,
        None,
    )
    node = _node(_trace(tb), january.node_id)
    assert node.id == f"revenue_prior_period:{subject}:FY2027-P01"
    assert (node.formula_id, node.value, node.params["as_of"]) == (
        "estimate.prior_period.v1",
        "60000.00",
        "2026-12-31",
    )
    # round(150,000.00 × 0.40): x′ × f(s) − x × f(s) with f = 0.40 at the end of Year 1.
    assert (node.params["e_before_1"], node.params["e_after_1"], node.params["rule_1"]) == (
        "1002000",
        "1062000",
        "S08-R-14",
    )
    assert _parts(node) == [(second.event_key, "60000.00")]


def test_chk_101_prior_period_portion() -> None:
    december, resolved = date(2026, 12, 1), date(2027, 2, 15)
    ctx = book_context(bundles.entity(start=december, months=3))
    goods = segment(
        Fraction(50000),
        usd("50000.00"),
        start=december,
        end=december,
        quantity=Fraction(1000),
        measure="POINT_IN_TIME",
    )
    ob = obligation(
        "L1-PROD", [goods], method="POINT_IN_TIME", convention=None, quantity=Fraction(1000)
    )
    v1 = _version("VC-CONCESSION", "IMPLICIT_PRICE_CONCESSION", 1, december, amount="50000.00")
    v2 = _version("VC-CONCESSION", "IMPLICIT_PRICE_CONCESSION", 2, resolved, amount="45000.00")
    first, second = _estimate(3, v1), _estimate(5, v2)
    delivered = _delivery(CONTRACT_KEY, 4, december, "L1-PROD", "1000", "DELIVERY")
    st = allocated_state(
        [ob],
        events=[first, delivered, second],
        inception=december,
        estimates=_pins((v1, first), (v2, second)),
    )
    amounts = {v1.version_key: usd("-50000.00"), v2.version_key: usd("-45000.00")}
    price_at = _price_at(lambda at: usd("100000.00"), amounts)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    folded = _fold(ctx, st, [first, second], price_at, tb)

    portions = {
        key: _single(decompose_prior_period(ctx, folded, key, tb)).value
        for key in ("FY2026-P12", "FY2027-P01", "FY2027-P02")
    }
    # Satisfied in December (f = 1): the February price change is all prior-period revenue.
    assert portions == {"FY2026-P12": 0, "FY2027-P01": 0, "FY2027-P02": usd("5000.00")}
    node = _node(_trace(tb), f"revenue_prior_period:{CONTRACT_KEY}/L1-PROD:FY2027-P02")
    assert _parts(node) == [(second.event_key, "5000.00")]


def test_ex_15_c_portions() -> None:
    ctx = book_context(bundles.entity(months=24))
    k03, start, end = "K-03", date(2026, 1, 1), date(2027, 12, 31)
    to_august = _delivery(k03, 2, date(2026, 8, 31), "O1", "420000")  # costs at s
    amended = event_view(
        k03,
        3,
        "CONTRACT_AMENDED",
        date(2026, 9, 10),
        {"modification_id": "MOD-K03-1"},
        obligation_keys=["O1"],
    )
    september = _delivery(k03, 4, date(2026, 9, 25), "O1", "82000")
    eac = event_view(
        k03, 5, "ESTIMATE_CHANGED", date(2026, 9, 30), {"estimate_version_id": "K-03/EAC@v3"}
    )
    j14 = _delivery(k03, 6, date(2026, 9, 29), "O1", "20500")  # recorded after the EAC change
    inception = segment(
        Fraction(1000000),
        usd("1000000.00"),
        start=start,
        end=end,
        quantity=Fraction(700000),
        measure="UNITS_DELIVERED",
    )
    modified = segment(  # 25-13(b): A′ 1,350,000.00 and EAC 820,000.00 (stage 06 stand-in, D-81)
        Fraction(1350000),
        usd("1350000.00"),
        start=start,
        end=end,
        effective=amended.effective_date,
        cause=SegmentCause.MODIFICATION,
        event_key=amended.event_key,
        quantity=Fraction(820000),
        measure="UNITS_DELIVERED",
    )
    re_estimated = dataclasses.replace(  # EAC version 3 of 850,000.00 (L2-5-Q-5)
        modified,
        effective_date=eac.effective_date,
        event_key=eac.event_key,
        cause=SegmentCause.ESTIMATE_CHANGE,
        totals=dataclasses.replace(modified.totals, quantity=Fraction(850000)),
    )
    ob = obligation(
        "O1",
        [inception, modified, re_estimated],
        contract_key=k03,
        method="UNITS_DELIVERED",
        convention=None,
        start=start,
        quantity=Fraction(850000),
    )
    events = [to_august, amended, september, eac]
    st = allocated_state([ob], events=events)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)

    target = _single(decompose_prior_period(ctx, st, "FY2026-P09", tb))
    assert target.value == usd("67058.82")
    node = _node(_trace(tb), target.node_id)
    assert _parts(node) == [(amended.event_key, "91463.41"), (eac.event_key, "-24404.59")]
    assert [Fraction(node.params[name]) for name in ("e_before_1", "e_after_1", "e_after_2")] == [
        Fraction(600000),
        Fraction(1350000 * 420000, 820000),  # 691,463.414…
        Fraction(1350000 * 420000, 850000),  # 667,058.823…
    ]
    assert node.params["e_before_2"] == node.params["e_after_1"]

    def revenue(state: AllocatedState) -> int:
        september_end = target_at_position(ctx, state, ob, date(2026, 9, 30), adjusted=True)
        august_end = target_at_position(ctx, state, ob, date(2026, 8, 31), adjusted=True)
        return september_end.value - august_end.value

    assert revenue(st) == usd("197294.12")
    assert revenue(st) - target.value == usd("130235.30")  # current-period revenue of Sep 2026

    corrected = allocated_state([ob], events=[*events, j14])
    replayed = _single(
        decompose_prior_period(
            ctx, corrected, "FY2026-P09", TraceBuilder(engine_version=ENGINE_VERSION)
        )
    )
    assert replayed.value == usd("67058.82")  # the cost dated 29 September adds nothing
    assert revenue(corrected) == usd("229852.94")

    # A 25-13(a) treatment of the same amendment, and the EAC change that copies its base, give 0.
    prospective = dataclasses.replace(
        modified,
        basis="PROSPECTIVE",
        base_revenue_posted=usd("600000.00"),
        base_revenue_exact=Fraction(600000),
    )
    copied = dataclasses.replace(
        prospective,
        effective_date=eac.effective_date,
        event_key=eac.event_key,
        cause=SegmentCause.ESTIMATE_CHANGE,
    )
    unrelated = dataclasses.replace(ob, segments=(inception, prospective, copied))
    zero = _single(
        decompose_prior_period(
            ctx,
            allocated_state([unrelated], events=events),
            "FY2026-P09",
            TraceBuilder(engine_version=ENGINE_VERSION),
        )
    )
    assert zero.value == 0


def _quarterly(year: int) -> EntityInput:
    periods = tuple(
        PeriodInput(
            period_key=f"FY{year}-P{quarter:02d}",
            fiscal_year=year,
            period_no=quarter,
            start_date=date(year, 3 * quarter - 2, 1),
            end_date=month_end(date(year, 3 * quarter, 1)),
            states=(("ASC606", "open"),),
        )
        for quarter in range(1, 5)
    )
    # E-50 holds no quarterly pattern; a non-MONTHLY literal makes stage 09 read these periods
    # (ALG-11 rule 3), which are the calendar quarters of the CHK-110 table (L2-5-Q-7).
    return EntityInput(ENTITY, "USD", "America/New_York", "P445", periods)


def test_s08_r14_minimum_commitment_portion() -> None:
    ctx = book_context(_quarterly(2026))
    element = f"{CONTRACT_KEY}/VC-MINIMUM"
    lowered = event_view(
        CONTRACT_KEY,
        3,
        "ESTIMATE_CHANGED",
        date(2026, 6, 30),
        {"estimate_version_id": f"{element}@v2"},
    )
    stand_ready = segment(
        Fraction(140000), usd("140000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    changed = dataclasses.replace(
        stand_ready,
        effective_date=lowered.effective_date,
        event_key=lowered.event_key,
        cause=SegmentCause.TP_CHANGE,
        x_exact=Fraction(120000),
        a_posted=usd("120000.00"),
        estimate_pair=(f"{element}@v1", f"{element}@v2"),
    )
    ob = obligation("STAND-READY", [stand_ready, changed], convention="MONTHLY_EVEN")
    st = allocated_state([ob], events=[lowered])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)

    quarters = {
        key: _single(decompose_prior_period(ctx, st, key, tb)).value
        for key in ("FY2026-P01", "FY2026-P02", "FY2026-P03", "FY2026-P04")
    }
    # round(−20,000.00 × 3/12) for the quarter starting 1 April (CHK-110 prior-period column).
    assert quarters == {
        "FY2026-P01": 0,
        "FY2026-P02": usd("-5000.00"),
        "FY2026-P03": 0,
        "FY2026-P04": 0,
    }
    node = _node(_trace(tb), f"revenue_prior_period:{CONTRACT_KEY}/STAND-READY:FY2026-P02")
    assert (Fraction(node.params["e_before_1"]), Fraction(node.params["e_after_1"])) == (
        Fraction(35000),
        Fraction(30000),
    )
    # The sequential catch-up at 30 June is (10,000.00) (REQ-MOD-015; ENGINE_SPEC_B S09-R-37).
    before = target_at_position(ctx, st, ob, lowered.effective_date, event=lowered, inclusive=False)
    after = target_at_position(ctx, st, ob, lowered.effective_date, event=lowered, inclusive=True)
    assert after.value - before.value == usd("-10000.00")


def test_s08_inv_04_prior_plus_current_equals_catch_up() -> None:
    ctx = book_context(bundles.entity(months=12))
    service = segment(
        Fraction(36500), usd("36500.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    ob = obligation("SVC", [service])  # DAILY over 365 days
    amounts = (  # cumulative VC amount of each version
        (1, date(2026, 1, 1), "0.00"),
        (2, date(2026, 2, 10), "1000.00"),
        (3, date(2026, 3, 1), "270.00"),
        (4, date(2026, 3, 31), "603.33"),
        (5, date(2026, 7, 17), "-1234.56"),
    )
    versions = [
        _version("VC-1", "VARIABLE_CONSIDERATION", no, effective, amount=amount)
        for no, effective, amount in amounts
    ]
    applied = [(version, _estimate(version.version_no + 1, version)) for version in versions]
    st = allocated_state([ob], events=[ev for _, ev in applied], estimates=_pins(*applied))
    price_at = _price_at(
        lambda at: usd("36500.00"),
        {
            version.version_key: usd(amount)
            for version, (_, _, amount) in zip(versions, amounts, strict=True)
        },
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    folded = _fold(ctx, st, [ev for _, ev in applied], price_at, tb)
    (folded_ob,) = folded.obligations
    calendar = ctx.entities[ENTITY].periods
    prior = {
        period.period_key: _single(decompose_prior_period(ctx, folded, period.period_key, tb))
        for period in calendar
    }
    nodes = {node.id: node for node in _trace(tb).nodes}

    checked = 0
    for period in calendar:
        f_start = target_at_position(
            ctx, folded, folded_ob, period.start_date - timedelta(days=1)
        ).progress
        catch_ups = [
            nodes[f"catch_up@{ev.event_key}:{folded_ob.subject_key}:-"]
            for _, ev in applied[1:]
            if period.start_date <= ev.effective_date <= period.end_date
        ]
        node = nodes[prior[period.period_key].node_id]
        assert int(node.params["boundaries"]) == len(catch_ups)
        exact_prior = sum(
            (
                Fraction(node.params[f"e_after_{index}"])
                - Fraction(node.params[f"e_before_{index}"])
                for index in range(1, len(catch_ups) + 1)
            ),
            Fraction(0),
        )
        exact_catch_up = sum(
            (
                Fraction(item.params["exact_after"]) - Fraction(item.params["exact_before"])
                for item in catch_ups
            ),
            Fraction(0),
        )
        exact_current = sum(  # ΔX × (f(d) − f(s)) per boundary (ALG-10 §2.11.3)
            (
                (Fraction(item.params["x_after"]) - Fraction(item.params["x_before"]))
                * (Fraction(item.params["progress"]) - (f_start or Fraction(0)))
                for item in catch_ups
            ),
            Fraction(0),
        )
        assert exact_prior + exact_current == exact_catch_up  # S08-INV-04, exact
        posted_catch_up = sum(usd(item.value) for item in catch_ups)
        current = posted_catch_up - prior[period.period_key].value  # current-period remainder
        assert prior[period.period_key].value + current == posted_catch_up
        assert abs(current - round_half_up(exact_current, 2)) <= len(catch_ups)
        checked += len(catch_ups)
    assert checked == 4
    assert [prior[key].value for key in ("FY2026-P02", "FY2026-P03", "FY2026-P07")] == [
        usd("84.93"),  # round(1,000.00 × 31/365)
        usd("-64.12"),  # round(−730.00 × 59/365) + round(333.33 × 59/365): two boundaries chained
        usd("-911.39"),  # round(−1,837.89 × 181/365)
    ]


def _golden_contract_1() -> list[ObligationState]:
    total = sum(ssp for *_, ssp in GOLDEN_CONTRACT_1)
    posted = largest_remainder(
        1300 * 100,
        [Fraction(ssp) for *_, ssp in GOLDEN_CONTRACT_1],
        [key for key, *_ in GOLDEN_CONTRACT_1],
    )
    return [
        obligation(
            key,
            [
                segment(
                    Fraction(1300 * ssp, total),
                    a_posted,
                    start=JANUARY_2023,
                    end=date(2023, 12, 31),
                    quantity=Fraction(quantity),
                    measure="UNITS_DELIVERED",
                )
            ],
            contract_key="Contract 1",
            method="UNITS_DELIVERED",
            convention=None,
            start=JANUARY_2023,
            quantity=Fraction(quantity),
        )
        for (key, quantity, ssp), a_posted in zip(GOLDEN_CONTRACT_1, posted, strict=True)
    ]


def _revenue_posted(subject_key: str, period_key: str, amount: str) -> PostedAmountInput:
    minor = usd(amount)  # a revenue credit posts negative (debit positive, RCP-05)
    return PostedAmountInput(
        book_code="ASC606",
        entity_code=ENTITY,
        subject_key=subject_key,
        entry_kind="REVENUE_RECOGNITION",
        account_role="REVENUE",
        clearing_purpose=None,
        counterparty_entity_code=None,
        period_key=period_key,
        origin_period_key=None,
        posting_class="EVENT",
        txn_currency="USD",
        functional_currency="USD",
        amount_txn=-minor,
        amount_functional=-minor,
    )


def test_s08_r15_late_event_attribution() -> None:
    ctx = book_context(
        bundles.entity(start=JANUARY_2023, months=12, states={"FY2023-P01": "closed"}),
        preset="LEGACY_PARITY",
    )
    late = [  # effective in the locked January, recorded in February (EX-08-A)
        _delivery("Contract 1", version, date(2023, 1, 31), key, quantity, "DELIVERY")
        for version, key, quantity in ((5, "POB #1", "2"), (6, "POB #2", "1"), (7, "POB #3", "0.5"))
    ]
    st = allocated_state(_golden_contract_1(), events=late, inception=JANUARY_2023)
    posted = PostedIndex(
        (
            _revenue_posted("Contract 1/POB #1", "FY2023-P01", "100.00"),  # posted before the lock
            _revenue_posted("Contract 1/POB #2", "FY2023-P02", "10.00"),  # native February amount
        )
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)

    february = {
        t.subject_key: t for t in decompose_prior_period(ctx, st, "FY2023-P02", tb, posted=posted)
    }
    assert {key: target.value for key, target in february.items()} == {
        "Contract 1/POB #1": usd("28.84"),
        "Contract 1/POB #2": usd("118.53"),
        "Contract 1/POB #3": usd("48.32"),
        "Contract 1/POB #4": 0,
    }
    posted_through_january = {"Contract 1/POB #1": usd("100.00")}
    for ob in st.obligations:  # recomputed target through t − 1 less posted through t − 1
        recomputed = target_at_position(ctx, st, ob, date(2023, 1, 31), adjusted=True).value
        expected = recomputed - posted_through_january.get(ob.subject_key, 0)
        assert february[ob.subject_key].value == expected
    march = decompose_prior_period(ctx, st, "FY2023-P03", tb, posted=posted)
    assert [target.value for target in march] == [0, 0, 0, 0]  # February is open: no carry
    node = _node(_trace(tb), february["Contract 1/POB #1"].node_id)
    assert (
        node.params["carries"],
        node.params["late_origin_1"],
        node.params["late_target_1"],
        node.params["late_posted_1"],
    ) == (
        "1",
        "FY2023-P01",
        "12884",
        "10000",
    )

    with pytest.raises(EngineError) as unbound:
        decompose_prior_period(ctx, st, "FY2023-P02", TraceBuilder(engine_version=ENGINE_VERSION))
    assert unbound.value.detail["rule"] == "S08-R-15"


# --- EX-15-C through the input measure (S08-R-14; D-97 (10)) --------------------------------------

EAC_KEY = f"{CONTRACT_KEY}/EAC-01"


def _eac_version(number: int, effective: date, total: str) -> EstimateVersionInput:
    base = estimate_version(EAC_KEY, "EAC", number, effective, obligation_key="O1")
    return dataclasses.replace(base, expected_total_amount=Decimal(total))


def _cost(stream_version: int, effective: date, amount: str) -> EventView:
    payload = {"obligation_key": "O1", "purpose": "PROGRESS_INPUT", "amount": Decimal(amount)}
    return event_view(
        CONTRACT_KEY, stream_version, "COST_INCURRED", effective, payload, obligation_keys=["O1"]
    )


def _k03_cost_to_cost(
    *, correction: bool = False, prospective: bool = False
) -> tuple[AllocatedState, EventView, EventView]:
    """EX-09-B and EX-15-C measured cost to cost: TP 1,000,000.00, EAC 700,000.00, costs 420,000.00
    at 31 Aug 2026; the 10 Sep amendment (class N, A′ 1,350,000.00) records EAC 820,000.00 after it
    (S06-R-15); +82,000.00 on 25 Sep; EAC 850,000.00 effective 30 Sep, a measure-only version that
    adds no segment (S08-R-02). ``correction`` adds the J-14 cost of 20,500.00 dated 29 Sep;
    ``prospective`` treats the amendment under 25-13(a) (a PROSPECTIVE segment with base revenue
    600,000.00 at 10 Sep; Codex C4-EAC-R1)."""
    start, end, d = date(2026, 1, 1), date(2027, 12, 31), date(2026, 9, 10)
    v1 = _eac_version(1, start, "700000.00")
    v2 = _eac_version(2, d, "820000.00")
    v3 = _eac_version(3, date(2026, 9, 30), "850000.00")
    amend = event_view(
        CONTRACT_KEY,
        5,
        "CONTRACT_AMENDED",
        d,
        {"modification_id": "MOD-K03-1"},
        obligation_keys=["O1"],
    )
    e1, e2, e3 = _estimate(3, v1), _estimate(6, v2), _estimate(8, v3)
    inception = segment(
        Fraction(1000000), usd("1000000.00"), start=start, end=end, measure="COST_TO_COST"
    )
    modified = segment(
        Fraction(1350000),
        usd("1350000.00"),
        start=start,
        end=end,
        effective=d,
        cause=SegmentCause.MODIFICATION,
        event_key=amend.event_key,
        measure="COST_TO_COST",
    )
    if prospective:
        modified = dataclasses.replace(
            modified,
            basis="PROSPECTIVE",
            base_revenue_posted=usd("600000.00"),
            base_revenue_exact=Fraction(600000),
        )
    ob = obligation(
        "O1", [inception, modified], method="COST_TO_COST", convention=None, start=start
    )
    events = [e1, _cost(4, date(2026, 8, 31), "420000.00"), amend, e2]
    events.append(_cost(7, date(2026, 9, 25), "82000.00"))
    events.append(e3)
    if correction:
        events.append(_cost(9, date(2026, 9, 29), "20500.00"))
    st = allocated_state([ob], events=events, estimates=_pins((v1, e1), (v2, e2), (v3, e3)))
    return st, amend, e3


def test_ex_15_c_eac_version_is_its_own_portion() -> None:
    """S08-R-14 (D-97 (10)): a measure-only ``EAC`` version effective in t is a boundary of the
    obligation, measured as E_after(s) − E_before(s) with the costs at s; the class N amendment is
    measured with its S06-R-15 updated EAC. EX-15-C: 91,463.41 and (24,404.59), prior-period
    revenue 67,058.82 of September's 197,294.12."""
    ctx = book_context(bundles.entity(months=24))
    st, amend, eac = _k03_cost_to_cost()
    (ob,) = st.obligations
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    target = _single(decompose_prior_period(ctx, st, "FY2026-P09", tb))
    assert target.value == usd("67058.82")
    node = _node(_trace(tb), target.node_id)
    assert _parts(node) == [(amend.event_key, "91463.41"), (eac.event_key, "-24404.59")]
    assert [Fraction(node.params[name]) for name in ("e_before_1", "e_after_1", "e_after_2")] == [
        Fraction(600000),
        Fraction(1350000 * 420000, 820000),  # 691,463.414…
        Fraction(1350000 * 420000, 850000),  # 667,058.823…
    ]
    assert node.params["e_before_2"] == node.params["e_after_1"]
    assert (node.params["rule_1"], node.params["rule_2"]) == ("S08-R-14", "S08-R-14")
    versions = (node.params["version_1"], node.params["version_2"])
    assert versions == (f"{EAC_KEY}@v2", f"{EAC_KEY}@v3")

    def revenue(state: AllocatedState) -> int:
        september = target_at_position(ctx, state, ob, date(2026, 9, 30), adjusted=True)
        august = target_at_position(ctx, state, ob, date(2026, 8, 31), adjusted=True)
        return september.value - august.value

    assert revenue(st) == usd("197294.12")
    assert revenue(st) - target.value == usd("130235.30")  # current-period revenue of Sep 2026
    corrected, _, _ = _k03_cost_to_cost(correction=True)
    replayed = _single(
        decompose_prior_period(
            ctx, corrected, "FY2026-P09", TraceBuilder(engine_version=ENGINE_VERSION)
        )
    )
    assert replayed.value == usd("67058.82")  # the cost dated 29 September adds nothing
    assert revenue(corrected) == usd("229852.94")


def test_c4_eac_r1_measure_only_versions_after_a_prospective_boundary_add_nothing() -> None:
    """Codex C4-EAC-R1 (review of 32fbcb4 / 7cbad2e): with the same K-03 world and the amendment
    treated under 25-13(a) (PROSPECTIVE, base revenue 600,000.00), the boundary contributes 0
    (CV-63) and the later measure-only EAC versions v2 and v3 contribute 0 too — the basis in force
    starts at the boundary, so nothing of it is measured at s; the stale inception view must not
    be remeasured against 820,000 / 850,000 (which gave (105,882.35)). September revenue is
    143,023.26 either way."""
    ctx = book_context(bundles.entity(months=24))
    st, amend, _eac = _k03_cost_to_cost(prospective=True)
    (ob,) = st.obligations
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    target = _single(decompose_prior_period(ctx, st, "FY2026-P09", tb))
    assert target.value == 0
    node = _node(_trace(tb), target.node_id)
    assert _parts(node) == [(amend.event_key, "0.00")]
    assert node.params["rule_1"] == "CV-63"
    september = target_at_position(ctx, st, ob, date(2026, 9, 30), adjusted=True).value
    august = target_at_position(ctx, st, ob, date(2026, 8, 31), adjusted=True).value
    assert september - august == usd("143023.26")
