"""Stage 08 estimate reassessment: pins, measure-only and reallocating kinds, 32-45 routing.

ENGINE_SPEC §8.2, §8.3 S08-R-01 to S08-R-07, §8.6 S08-INV-01, S08-INV-02 and §8.7 EX-08-B, EX-08-C,
EX-08-E; POLICIES ALG-10 §2.11.1, §2.11.2 (CHK-100, CHK-101) and POL-106. Stages 04 to 06 are built
in another lane, so the tests build ``AllocatedState`` against ENGINE_SPEC §0.11 and bind a fake
``price_at`` that follows the §4.2 contract (D-81 integration after merge). Stage 09 then runs over
the resulting state with the same trace and cites the ``catch_up@`` nodes stage 08 publishes.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import BookOutput, EstimateVersionInput, InputBundle
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages import s04_transaction_price, s08_estimates_late_events
from erev_engine.stages.s08_estimates_late_events import routing
from erev_engine.stages.s09_recognition import RecognitionState, run
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EstimatePin,
    EstimatePins,
    EventView,
    Quota,
    Quota1,
    ReturnPath,
    ReturnPin,
    SegmentCause,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support import allocation_worlds as worlds
from support import bundles
from support.bundles import entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    estimate_version,
    event_view,
    obligation,
    segment,
    targets_by_period,
    usd,
)

PriceAt = s08_estimates_late_events.PriceAt
RETURNS_POLICY = {
    "returns.model": "EXPECTED_RETURNS",
    "returns.returned_units_scope": "REDUCE_CONTRACT_QUANTITY",
    "returns.reversal_rate": "AVERAGE_CARRYING_RATE",
}


def _version(
    element: str,
    kind: str,
    version_no: int,
    effective: date,
    *,
    amount: str | None = None,
    total: str | None = None,
    quantity: str | None = None,
    target: str = "CONTRACT",
    targets: Sequence[str] = (),
    obligation_key: str | None = None,
) -> EstimateVersionInput:
    """An APPROVED T-CON-13 version of ``kind`` (E-09) of element ``K-01/<element>``."""
    base = estimate_version(
        f"{CONTRACT_KEY}/{element}", kind, version_no, effective, obligation_key=obligation_key
    )
    return dataclasses.replace(
        base,
        allocation_target=target,
        target_obligation_keys=tuple(targets),
        constrained_amount=None if amount is None else Decimal(amount),
        expected_total_amount=None if total is None else Decimal(total),
        expected_quantity=None if quantity is None else Decimal(quantity),
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
    stream_version: int,
    effective: date,
    obligation_key: str,
    quantity: str = "1",
    trigger: str = "CONTROL_TRANSFER",
) -> EventView:
    payload = {"obligation_key": obligation_key, "quantity": Decimal(quantity), "trigger": trigger}
    return event_view(
        CONTRACT_KEY,
        stream_version,
        "DELIVERY_RECORDED",
        effective,
        payload,
        obligation_keys=[obligation_key],
    )


def _pins(*applied: tuple[EstimateVersionInput, EventView]) -> EstimatePins:
    """The S01-R-18 index of the versions the given events apply."""
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
    """A fake stage 04 ``price_at`` (ENGINE_SPEC §4.2; D-81), minor units.

    The allocation basis is the fixed consideration at ``at`` plus the amount of every version
    pinned at ``at`` among the events before the position (S04-R-01).
    """

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


def _recognise(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder
) -> tuple[RecognitionState, Trace]:
    """Run stage 09 over the folded state and check that the trace reproduces every node."""
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _causes(state: RecognitionState, subject_key: str, period_key: str) -> dict[str, int]:
    return {
        target.cause or "": target.value
        for target in state.revenue_by_cause
        if target.subject_key == subject_key and target.period_key == period_key
    }


def test_chk_100_bonus_catch_up() -> None:
    ctx = book_context(entity(months=36))
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
    absorbed = s08_estimates_late_events.apply(ctx, st, first, tb, price_at=price_at)
    assert absorbed is st  # version 1 at inception belongs to the inception price (§4.2)
    after = s08_estimates_late_events.apply(ctx, absorbed, second, tb, price_at=price_at)
    changed = after.obligations[0].segments[-1]
    assert (changed.cause, changed.basis, changed.effective_date, changed.event_key) == (
        SegmentCause.TP_CHANGE,
        "INCEPTION",
        date(2027, 1, 1),
        second.event_key,
    )
    assert changed.estimate_pair == (v1.version_key, v2.version_key)
    assert (changed.x_exact, changed.a_posted) == (2655000, usd("2655000.00"))  # x′
    # S08-INV-01: Σ a_posted = allocation_basis.posted after the version.
    assert after.tp_history[-1].allocation_basis.posted == changed.a_posted

    state, trace = _recognise(ctx, after, tb)
    subject = f"{CONTRACT_KEY}/L1-ASSET"
    delta = _node(trace, f"tp_delta@{second.event_key}:CG-1:-")
    assert (delta.value, delta.params["v_old"], delta.params["v_new"]) == (
        "150000.00",
        v1.version_key,
        v2.version_key,
    )
    catch_up = _node(trace, f"catch_up@{second.event_key}:{subject}:-")
    assert (catch_up.formula_id, catch_up.value, catch_up.params["progress"]) == (
        "estimate.catch_up.v1",
        "60000.00",
        "2/5",
    )
    targets = targets_by_period(state, subject)
    assert (targets["FY2026-P12"], targets["FY2027-P01"], targets["FY2027-P12"]) == (
        usd("1002000.00"),
        usd("1062000.00"),
        usd("2124000.00"),
    )
    assert targets["FY2027-P12"] - targets["FY2027-P01"] == usd("1062000.00")  # f 0.40 to 0.80
    assert targets["FY2027-P12"] - targets["FY2026-P12"] == usd("1122000.00")  # Year 2
    assert _causes(state, subject, "FY2027-P01") == {"TP_CHANGE": usd("60000.00")}


def test_l9_run_q8_element_contract_resolves_the_encoded_estimate_head() -> None:
    """D-90d L9-RUN-Q-8: the estimate key head is the CV-21 encoded contract id, so a contract id
    with a delimiter (``K/01``, head ``K%2F01``) keeps its element's obligations and the CHK-100
    figures; before the fix ``element_obligations`` returned nothing and stage 08 raised
    ``ENGINE_INVARIANT_VIOLATED`` "no obligation receives the transaction price change"."""
    contract, encoded = "K/01", "K%2F01"
    ctx = book_context(entity(months=36))
    asset = segment(
        Fraction(2505000), usd("2505000.00"), start=date(2026, 1, 1), end=date(2028, 12, 31)
    )
    ob = dataclasses.replace(
        obligation(
            "L1-ASSET", [asset], method="OUTPUT_PERCENT", convention=None, contract_key=contract
        ),
        subject_key=f"{encoded}/L1-ASSET",
    )

    def version(no: int, effective: date, amount: str) -> EstimateVersionInput:
        base = estimate_version(f"{encoded}/VC-BONUS", "VARIABLE_CONSIDERATION", no, effective)
        return dataclasses.replace(
            base, allocation_target="CONTRACT", constrained_amount=Decimal(amount)
        )

    def event(
        stream: int, event_type: str, effective: date, payload: dict[str, object]
    ) -> EventView:
        raw = event_view(contract, stream, event_type, effective, payload)
        return dataclasses.replace(
            raw,
            event_key=f"{encoded}/EV-{stream:06d}",
            obligation_subject_keys=(
                (f"{encoded}/L1-ASSET",) if event_type == "PROGRESS_RECORDED" else ()
            ),
        )

    def progress(stream: int, effective: date, ratio: str) -> EventView:
        payload = {
            "obligation_key": "L1-ASSET",
            "cumulative_progress_ratio": Decimal(ratio),
            "measure": "OUTPUT_PERCENT",
        }
        return event(stream, "PROGRESS_RECORDED", effective, payload)

    v1 = version(1, date(2026, 1, 1), "0.00")
    v2 = version(2, date(2027, 1, 1), "150000.00")
    first = event(3, "ESTIMATE_CHANGED", v1.effective_date, {"estimate_version_id": v1.version_key})
    second = event(
        8, "ESTIMATE_CHANGED", v2.effective_date, {"estimate_version_id": v2.version_key}
    )
    events = [
        first,
        progress(6, date(2026, 12, 31), "0.40"),
        second,
        progress(9, date(2027, 12, 31), "0.80"),
    ]
    st = allocated_state([ob], events=events, estimates=_pins((v1, first), (v2, second)))
    assert routing.element_obligations(st, second, v2) == (ob,)
    # A portfolio element still applies to the event's contract.
    portfolio = dataclasses.replace(v2, estimate_key="PORTFOLIO:P-1/VC-BONUS")
    assert routing.element_obligations(st, second, portfolio) == (ob,)
    price_at = _price_at(lambda at: usd("2505000.00"), {v2.version_key: usd("150000.00")})
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    absorbed = s08_estimates_late_events.apply(ctx, st, first, tb, price_at=price_at)
    after = s08_estimates_late_events.apply(ctx, absorbed, second, tb, price_at=price_at)
    changed = after.obligations[0].segments[-1]
    assert (changed.cause, changed.a_posted) == (SegmentCause.TP_CHANGE, usd("2655000.00"))
    state, trace = _recognise(ctx, after, tb)
    subject = f"{encoded}/L1-ASSET"
    catch_up = _node(trace, f"catch_up@{second.event_key}:{subject}:-")
    assert (catch_up.value, catch_up.params["progress"]) == ("60000.00", "2/5")
    targets = targets_by_period(state, subject)
    assert (targets["FY2026-P12"], targets["FY2027-P01"]) == (
        usd("1002000.00"),
        usd("1062000.00"),
    )


def test_chk_101_concession_resolved_after_satisfaction() -> None:
    december, resolved = date(2026, 12, 1), date(2027, 2, 15)
    ctx = book_context(entity(start=december, months=3))
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
    delivered = _delivery(4, december, "L1-PROD", "1000", "DELIVERY")
    st = allocated_state(
        [ob],
        events=[first, delivered, second],
        inception=december,
        estimates=_pins((v1, first), (v2, second)),
    )
    # 1,000 products at 100.00 less the constrained concession.
    amounts = {v1.version_key: usd("-50000.00"), v2.version_key: usd("-45000.00")}
    price_at = _price_at(lambda at: usd("100000.00"), amounts)

    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    absorbed = s08_estimates_late_events.apply(ctx, st, first, tb, price_at=price_at)
    after = s08_estimates_late_events.apply(ctx, absorbed, second, tb, price_at=price_at)
    changed = after.obligations[0].segments[-1]
    assert (changed.cause, changed.x_exact, changed.a_posted) == (
        SegmentCause.TP_CHANGE,
        55000,
        usd("55000.00"),
    )

    state, trace = _recognise(ctx, after, tb)
    subject = f"{CONTRACT_KEY}/L1-PROD"
    assert _node(trace, f"tp_delta@{second.event_key}:CG-1:-").value == "5000.00"
    catch_up = _node(trace, f"catch_up@{second.event_key}:{subject}:-")
    assert (catch_up.value, catch_up.params["complete_before"], catch_up.params["progress"]) == (
        "5000.00",
        "true",
        "1",
    )
    targets = targets_by_period(state, subject)
    assert (targets["FY2026-P12"], targets["FY2027-P01"], targets["FY2027-P02"]) == (
        usd("50000.00"),
        usd("50000.00"),
        usd("55000.00"),
    )
    assert _causes(state, subject, "FY2027-P02") == {"TP_CHANGE": usd("5000.00")}


def _modification_catch_ups(
    tb: TraceBuilder, ctx: BookContext, st: AllocatedState, ev: EventView
) -> None:
    """Fake stage 06 ``catch_up@`` nodes of a 25-13(a) boundary: E starts at R_p (S06-INV-02)."""
    for ob in st.obligations:
        if any(seg.event_key == ev.event_key for seg in ob.segments):
            detail = {"member": "catch_up", "value": "0.00"}
            tb.node(
                measure=f"catch_up@{ev.event_key}",
                subject_key=ob.subject_key,
                period_key=None,
                value=0,
                currency=ctx.txn_currency,
                minor_unit=2,
                formula_id="rec.catch_up.sum.v1",
                inputs=[SourceRef("contract_event", ev.event_key, detail)],
                narrative_key="rec.catch_up.sum",
            )


def test_ex_08_e_32_45_routing() -> None:
    inception, modified, revised = date(2026, 7, 1), date(2026, 11, 30), date(2026, 12, 31)
    ctx = book_context(entity(start=inception, months=12))
    assert ctx.policies.value("mod.post_modification_vc_routing", contract=CONTRACT_KEY) == (
        "ASC_606_10_32_45"
    )
    amended = event_view(
        CONTRACT_KEY,
        5,
        "CONTRACT_AMENDED",
        modified,
        {"modification_id": "MOD-Z"},
        obligation_keys=["L2-Y", "L3-Z"],
    )
    lineage = (f"{CONTRACT_KEY}/L1-X", f"{CONTRACT_KEY}/L2-Y")

    def transferred(x_exact: str) -> AllocationSegment:
        return segment(
            Fraction(x_exact), usd(x_exact), start=inception, end=inception, measure="POINT_IN_TIME"
        )

    def remaining(x_exact: str) -> AllocationSegment:
        # A class D segment of the 25-13(a) boundary with its recorded weight (S06-R-11, S06-R-14).
        seg = segment(
            Fraction(x_exact),
            usd(x_exact),
            start=modified,
            end=modified,
            basis="PROSPECTIVE",
            cause=SegmentCause.MODIFICATION,
            event_key=amended.event_key,
            measure="POINT_IN_TIME",
        )
        return dataclasses.replace(seg, remaining_ssp=Fraction(500))

    x = obligation("L1-X", [transferred("600.00")], method="POINT_IN_TIME", convention=None)
    y = dataclasses.replace(
        obligation(
            "L2-Y",
            [transferred("600.00"), remaining("450.00")],
            method="POINT_IN_TIME",
            convention=None,
        ),
        lineage_pre_modification=lineage,
    )
    z = dataclasses.replace(
        obligation("L3-Z", [remaining("450.00")], method="POINT_IN_TIME", convention=None),
        lineage_pre_modification=lineage,
    )
    v1 = _version("VC-EX6", "VARIABLE_CONSIDERATION", 1, inception, amount="200.00")
    v2 = _version("VC-EX6", "VARIABLE_CONSIDERATION", 2, revised, amount="240.00")
    first, second = _estimate(3, v1), _estimate(6, v2)
    events = [
        first,
        _delivery(4, inception, "L1-X"),
        amended,
        second,
        _delivery(7, date(2027, 3, 31), "L2-Y"),
        _delivery(8, date(2027, 6, 30), "L3-Z"),
    ]
    st = allocated_state(
        [x, y, z], events=events, inception=inception, estimates=_pins((v1, first), (v2, second))
    )
    price_at = _price_at(
        lambda at: usd("1300.00") if at >= modified else usd("1000.00"),
        {v1.version_key: usd("200.00"), v2.version_key: usd("240.00")},
    )

    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    folded = s08_estimates_late_events.apply(ctx, st, first, tb, price_at=price_at)
    after = s08_estimates_late_events.apply(ctx, folded, second, tb, price_at=price_at)
    final = {ob.obligation_key: ob.segments[-1] for ob in after.obligations}
    assert {key: (seg.x_exact, seg.a_posted) for key, seg in final.items()} == {
        "L1-X": (620, usd("620.00")),
        "L2-Y": (460, usd("460.00")),
        "L3-Z": (460, usd("460.00")),
    }
    assert {seg.cause for seg in final.values()} == {SegmentCause.TP_CHANGE}

    _modification_catch_ups(tb, ctx, after, amended)
    state, trace = _recognise(ctx, after, tb)
    keys = ("L1-X", "L2-Y", "L3-Z")
    shares = {
        key: _node(trace, f"tp_share@{second.event_key}:{CONTRACT_KEY}/{key}:-") for key in keys
    }
    assert {key: node.value for key, node in shares.items()} == {
        "L1-X": "20.00",
        "L2-Y": "10.00",
        "L3-Z": "10.00",
    }
    assert shares["L1-X"].formula_id == "estimate.route.32_45.v1"
    assert (shares["L1-X"].params["satisfied_1"], shares["L2-Y"].params["post_keys_1"]) == (
        f"{CONTRACT_KEY}/L1-X",
        f"{CONTRACT_KEY}/L2-Y|{CONTRACT_KEY}/L3-Z",
    )
    catch_ups = {
        key: _node(trace, f"catch_up@{second.event_key}:{CONTRACT_KEY}/{key}:-").value
        for key in keys
    }
    assert catch_ups == {"L1-X": "20.00", "L2-Y": "0.00", "L3-Z": "0.00"}  # X +20.00 at once
    x_targets = targets_by_period(state, f"{CONTRACT_KEY}/L1-X")
    assert (x_targets["FY2026-P11"], x_targets["FY2026-P12"]) == (usd("600.00"), usd("620.00"))
    total = sum(targets_by_period(state, f"{CONTRACT_KEY}/{key}")["FY2027-P06"] for key in keys)
    assert total == usd("1540.00")


def test_s08_r02_measure_only_kinds() -> None:
    def unbound(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        raise AssertionError("a measure-only version never reads the transaction price")

    # EAC: progress totals are read at each date by stages 09 to 11 (S08-R-02).
    ctx = book_context()
    asset = segment(Fraction(1000), usd("1000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31))
    ob = obligation("L1-ASSET", [asset], method="OUTPUT_PERCENT", convention=None)
    eac_1 = _version(
        "EAC-ASSET", "EAC", 1, date(2026, 1, 1), total="800.00", obligation_key="L1-ASSET"
    )
    eac_2 = _version(
        "EAC-ASSET", "EAC", 2, date(2026, 6, 30), total="900.00", obligation_key="L1-ASSET"
    )
    first, second = _estimate(3, eac_1), _estimate(4, eac_2)
    st = allocated_state(
        [ob], events=[first, second], estimates=_pins((eac_1, first), (eac_2, second))
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    assert s08_estimates_late_events.apply(ctx, st, second, tb, price_at=unbound) is st
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert [node.id for node in trace.nodes] == [
        f"estimate_pin@{second.event_key}:{CONTRACT_KEY}/EAC-ASSET:-"
    ]
    pin = trace.nodes[0]
    assert Fraction(Decimal(pin.value)) == 900
    assert (pin.params["v_old"], pin.params["v_new"]) == (eac_1.version_key, eac_2.version_key)

    # RETURN_RATE: the expected returns are re-measured at the pin, with Σ a_posted unchanged.
    transfer, revision = date(2026, 1, 10), date(2026, 1, 20)
    ctx = book_context(entity(months=3))
    goods = segment(
        Fraction(10000), usd("10000.00"), start=transfer, end=transfer, quantity=Fraction(100)
    )
    product = obligation(
        "L1-PROD", [goods], method="UNITS_DELIVERED", convention=None, quantity=Fraction(100)
    )
    rate_1 = _version("RET-JAN", "RETURN_RATE", 1, transfer, quantity="3", obligation_key="L1-PROD")
    rate_2 = _version("RET-JAN", "RETURN_RATE", 2, revision, quantity="4", obligation_key="L1-PROD")
    applied_1, delivered, applied_2 = (
        _estimate(3, rate_1),
        _delivery(4, transfer, "L1-PROD", "100", "DELIVERY"),
        _estimate(5, rate_2),
    )
    subject = f"{CONTRACT_KEY}/L1-PROD"

    def returns_state(pins: Sequence[tuple[EstimateVersionInput, EventView]]) -> AllocatedState:
        path_pins = tuple(
            ReturnPin(
                version.effective_date,
                version.version_key,
                Fraction(Decimal(str(version.expected_quantity))),
                Fraction(60),
                Fraction(0),
                date(2026, 3, 15),
            )
            for version, _ in pins
        )
        path = ReturnPath(
            f"{CONTRACT_KEY}/RET-JAN",
            path_pins,
            ((transfer, Fraction(100)),),
            Fraction(100),
            RETURNS_POLICY,
        )
        base = allocated_state(
            [product],
            events=[delivered, *(ev for _, ev in pins)],
            inception=transfer,
            estimates=_pins(*pins),
        )
        return dataclasses.replace(base, return_paths={subject: path})

    original = returns_state([(rate_1, applied_1)])
    revised = returns_state([(rate_1, applied_1), (rate_2, applied_2)])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    assert s08_estimates_late_events.apply(ctx, revised, applied_2, tb, price_at=unbound) is revised
    state, trace = _recognise(ctx, revised, tb)
    assert not [
        node.id
        for node in trace.nodes
        if node.id.startswith(("tp_delta@", "tp_share@", "catch_up@"))
    ]
    original_state, _ = _recognise(ctx, original, TraceBuilder(engine_version=ENGINE_VERSION))
    assert targets_by_period(original_state, subject)["FY2026-P01"] == usd("9700.00")
    assert targets_by_period(state, subject)["FY2026-P01"] == usd("9600.00")


def test_s08_inv_02_shares_sum_to_delta() -> None:
    ctx = book_context()
    start, end, revised = date(2026, 1, 1), date(2026, 12, 31), date(2026, 7, 1)
    allocations = {"POB-01": "100.00", "POB-02": "200.00", "POB-03": "400.00"}
    obligations = [
        obligation(
            key, [segment(Fraction(Decimal(x)), usd(x), start=start, end=end)], convention="DAILY"
        )
        for key, x in allocations.items()
    ]

    def routed(
        target: str, targets: Sequence[str], change: str
    ) -> tuple[AllocatedState, AllocatedState, list[TraceNode]]:
        v1 = _version(
            "VC-VOL",
            "VARIABLE_CONSIDERATION",
            1,
            start,
            amount="0.00",
            target=target,
            targets=targets,
        )
        v2 = _version(
            "VC-VOL",
            "VARIABLE_CONSIDERATION",
            2,
            revised,
            amount=change,
            target=target,
            targets=targets,
        )
        first, second = _estimate(3, v1), _estimate(4, v2)
        st = allocated_state(
            obligations, events=[first, second], estimates=_pins((v1, first), (v2, second))
        )
        price_at = _price_at(lambda at: usd("700.00"), {v2.version_key: usd(change)})
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        after = s08_estimates_late_events.apply(ctx, st, second, tb, price_at=price_at)
        trace = tb.build(root_measures={})
        assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
        shares = [
            node for node in trace.nodes if node.id.startswith(f"tp_share@{second.event_key}:")
        ]
        return st, after, shares

    def moved(st: AllocatedState, after: AllocatedState) -> tuple[list[int], Fraction]:
        pairs = list(zip(st.obligations, after.obligations, strict=True))
        posted = [new.segments[-1].a_posted - old.segments[-1].a_posted for old, new in pairs]
        exact = sum(
            (new.segments[-1].x_exact - old.segments[-1].x_exact for old, new in pairs), Fraction(0)
        )
        return posted, exact

    # Targeted with 32-40 evidence: incremental shares by relative SSP within the targets.
    st, after, shares = routed("OBLIGATIONS", list(allocations), "1.00")
    assert [node.value for node in shares] == ["0.14", "0.29", "0.57"]
    assert {node.params["mode"] for node in shares} == {"incremental"}
    assert {node.formula_id for node in shares} == {"estimate.route.inception.v2"}
    assert {node.params["ssp_weights"] for node in shares} == {"100|200|400"}
    assert moved(st, after) == ([14, 29, 57], Fraction(1))  # Σ Δ_p = ΔTP, Σ δ_p exact

    # Not targeted and every obligation on its inception segment: re-apportioned (S08-R-07); the
    # v2 params carry the exact quotas after the change and the S08-R-04 weights (D-91).
    st, after, shares = routed("CONTRACT", (), "1.01")
    assert [node.value for node in shares] == ["0.14", "0.29", "0.58"]
    assert {node.params["mode"] for node in shares} == {"reapportion"}
    assert {node.formula_id for node in shares} == {"estimate.route.inception.v2"}
    assert {node.params["ssp_weights"] for node in shares} == {"100|200|400"}
    assert {node.params["quotas_after"] for node in shares} == {"70101/700|70101/350|70101/175"}
    assert {node.params["basis_after"] for node in shares} == {"70101"}
    assert [node.params["a_before"] for node in shares] == ["10000", "20000", "40000"]
    assert [ob.segments[-1].x_exact for ob in after.obligations] == [
        Fraction(70101, 700),
        Fraction(70101, 350),
        Fraction(70101, 175),
    ]
    assert [ob.segments[-1].a_posted for ob in after.obligations] == [10014, 20029, 40058]
    assert moved(st, after) == ([14, 29, 58], Fraction(101, 100))

    # A share turning an allocation below 0 raises VC_ALLOCATION_NEGATIVE and adds no segment.
    st, after, _ = routed("OBLIGATIONS", ["POB-01"], "-150.00")
    assert [
        (item.code, item.severity, item.subject_key, item.stage) for item in after.findings
    ] == [("VC_ALLOCATION_NEGATIVE", "ERROR", f"{CONTRACT_KEY}/POB-01", 8)]
    assert after.obligations == st.obligations


def test_l8_d_contract_royalty_accrual_reallocates() -> None:
    """D-88 L7-5-Q-8: a new ``ROYALTY_ACCRUAL`` version with allocation_target CONTRACT, on a
    contract none of whose obligations has component ROYALTY or PERIOD_VC, is a reallocating kind
    (S08-R-03): ΔTP 200.00 routes on the inception basis over every obligation, so L1-X 133.33 and
    L2-Y 166.67 become 222.22 and 277.78 (ALC-S4-EX35-CASEB january-royalty). A royalty-component
    obligation keeps the measure-only S08-R-02."""
    ctx = book_context()
    start, january = date(2026, 1, 1), date(2026, 1, 31)
    licences = [
        obligation(
            key,
            [segment(Fraction(x, 3), usd(posted), start=start, end=start)],
            method="POINT_IN_TIME",
            convention=None,
        )
        for key, x, posted in (("L1-X", 400, "133.33"), ("L2-Y", 500, "166.67"))
    ]
    accrual = dataclasses.replace(
        _version("ROY-2026-01", "ROYALTY_ACCRUAL", 1, january, total="200.00"),
        parameters={"usage_period_start_date": "2026-01-01", "usage_period_end_date": "2026-01-31"},
    )
    applied = _estimate(3, accrual)
    st = allocated_state(licences, events=[applied], estimates=_pins((accrual, applied)))
    price_at = _price_at(lambda at: usd("300.00"), {accrual.version_key: usd("200.00")})
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s08_estimates_late_events.apply(ctx, st, applied, tb, price_at=price_at)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    changed = {ob.obligation_key: ob.segments[-1] for ob in after.obligations}
    assert {key: (seg.cause, seg.a_posted) for key, seg in changed.items()} == {
        "L1-X": (SegmentCause.TP_CHANGE, usd("222.22")),
        "L2-Y": (SegmentCause.TP_CHANGE, usd("277.78")),
    }
    assert after.tp_history[-1].allocation_basis.posted == usd("500.00")

    def unbound(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        raise AssertionError("a measure-only version never reads the transaction price")

    royalty = obligation(
        "L3-ROY",
        [segment(Fraction(0), 0, start=start, end=start, component="ROYALTY")],
        method="POINT_IN_TIME",
        convention=None,
    )
    measured = allocated_state(
        [*licences, royalty], events=[applied], estimates=_pins((accrual, applied))
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    assert s08_estimates_late_events.apply(ctx, measured, applied, tb, price_at=unbound) is measured


def test_l8_d_targeted_concession_on_a_satisfied_obligation_adds_a_refund_quota() -> None:
    """D-88 L7-5-Q-4 (iii) on the VC-CHK-113 world: a DISCOUNT element targeting POB #2, with no
    refund_liability_target, turns negative (−60.00) after the obligation is satisfied (f = 1 at
    d), so stage 08 adds refund_components[POB #2] = Quota(60, 6000), the CONCESSION quota stage 10
    consumes with the ESTIMATE_CHANGED event key. An unsatisfied receiver or a version naming a
    refund_liability_target adds none."""
    ctx = book_context(entity(start=date(2023, 1, 1), months=12))
    start, delivered_on, conceded = date(2023, 1, 1), date(2023, 10, 31), date(2023, 11, 15)
    software = segment(
        Fraction(400), usd("400.00"), start=start, end=start, measure="POINT_IN_TIME"
    )
    pob = obligation("POB-2", [software], method="POINT_IN_TIME", convention=None)
    subject = f"{CONTRACT_KEY}/POB-2"

    def world(*, delivered: bool, parameters: Mapping[str, object] | None = None) -> AllocatedState:
        v1 = _version(
            "VC-CONC-2",
            "VARIABLE_CONSIDERATION",
            1,
            start,
            amount="0.00",
            target="OBLIGATIONS",
            targets=["POB-2"],
        )
        v2 = dataclasses.replace(
            _version(
                "VC-CONC-2",
                "VARIABLE_CONSIDERATION",
                2,
                conceded,
                amount="-60.00",
                target="OBLIGATIONS",
                targets=["POB-2"],
            ),
            vc_element_type="DISCOUNT",
            parameters=parameters or {},
        )
        first, second = _estimate(3, v1), _estimate(8, v2)
        events = [first, second]
        if delivered:
            events.append(_delivery(5, delivered_on, "POB-2"))
        return allocated_state(
            [pob],
            events=events,
            inception=start,
            statuses=((start, "ACTIVE"),),
            estimates=_pins((v1, first), (v2, second)),
        )

    price_at = _price_at(lambda at: usd("400.00"), {f"{CONTRACT_KEY}/VC-CONC-2@v2": usd("-60.00")})

    def fold(st: AllocatedState) -> AllocatedState:
        second = next(ev for ev in st.events if ev.effective_date == conceded)
        return s08_estimates_late_events.apply(
            ctx, st, second, TraceBuilder(engine_version=ENGINE_VERSION), price_at=price_at
        )

    after = fold(world(delivered=True))
    quota = after.refund_components[subject]
    assert (quota.x_exact, quota.a_posted) == (60, usd("60.00"))
    assert after.obligations[0].segments[-1].a_posted == usd("340.00")
    assert dict(fold(world(delivered=False)).refund_components) == {}
    targeted = fold(world(delivered=True, parameters={"refund_liability_target": "60.00"}))
    assert dict(targeted.refund_components) == {}


# --- D-91 C606-02: S08-R-07 rev 1.6, the S08-R-06 transition predicate, the S08-R-04 guards -------
#
# Every expected figure below is derived from POLICIES §2.1.2 and ENGINE_SPEC S08-R-07 (rev 1.6) by
# the test-local oracle ``_lr`` / ``_carried`` (the lane derivation ``.run/l9/d91-c606-02/
# derive_b2.py``), never from engine output. Public-compute worlds come from
# ``support.allocation_worlds``; helper-level worlds bind a fake ``price_at`` (§4.2; D-81).


def _lr(total: int, weights: Sequence[Fraction], keys: Sequence[str]) -> list[int]:
    """POLICIES §2.1.2 largest remainder with the (fraction, weight, key) tie order; test-local."""
    assert all(weight >= 0 for weight in weights) and sum(weights, Fraction(0)) > 0
    sign, magnitude = (-1 if total < 0 else 1), abs(total)
    exact = [magnitude * weight / sum(weights, Fraction(0)) for weight in weights]
    base = [share.numerator // share.denominator for share in exact]
    order = sorted(range(len(keys)), key=lambda i: (-(exact[i] - base[i]), -weights[i], keys[i]))
    for i in order[: magnitude - sum(base)]:
        base[i] += 1
    return [sign * share for share in base]


def _carried(
    quotas: Mapping[str, tuple[Fraction, int]],
    weights: Mapping[str, Fraction],
    delta: int,
    mu: int = 2,
) -> tuple[dict[str, tuple[Fraction, int]], str]:
    """S08-R-07 (rev 1.6) by hand: x′ = x + ΔTP × w ÷ Σw; a′ = LR(basis after, [x′]) when every
    x′ ≥ 0 (0 on a zero basis), else a + LR(ΔTP, w). Returns the quotas after and the mode."""
    keys = sorted(quotas)
    weight_sum = sum((weights[key] for key in keys), Fraction(0))
    after = {
        key: quotas[key][0] + Fraction(delta, 10**mu) * weights[key] / weight_sum for key in keys
    }
    basis = sum(quotas[key][1] for key in keys) + delta
    assert sum(after.values(), Fraction(0)) * 10**mu == basis
    if any(value < 0 for value in after.values()):
        shares = _lr(delta, [weights[key] for key in keys], keys)
        return {
            k: (after[k], quotas[k][1] + s) for k, s in zip(keys, shares, strict=True)
        }, "incremental"
    if basis == 0:
        return {key: (after[key], 0) for key in keys}, "reapportion"
    shares = _lr(basis, [after[key] for key in keys], keys)
    return {k: (after[k], s) for k, s in zip(keys, shares, strict=True)}, "reapportion"


def _allocations(book: BookOutput) -> dict[str, tuple[int, int]]:
    """(allocated_amount, revenue_cum) per obligation key of a computed book."""
    found: dict[str, tuple[int, int]] = {}
    for version in book.obligation_versions:
        allocated, revenue = version.columns["allocated_amount"], version.columns["revenue_cum"]
        assert isinstance(allocated, int) and isinstance(revenue, int)
        found[version.subject_key.rsplit("/", 1)[-1]] = (allocated, revenue)
    return found


def _revenue_postings(book: BookOutput) -> dict[str, int]:
    """Σ ``REVENUE`` posting-intent lines per posting period, credit positive."""
    found: dict[str, int] = {}
    for intent in book.posting_intents:
        for line in intent.lines:
            if line.account_role == "REVENUE":
                signed = line.amount_txn if line.side == "C" else -line.amount_txn
                found[intent.posting_period_key] = found.get(intent.posting_period_key, 0) + signed
    return {period: amount for period, amount in sorted(found.items()) if amount}


def _column(book: BookOutput, name: str) -> int:
    assert book.contract_version is not None
    value = book.contract_version.columns[name]
    assert isinstance(value, int)
    return value


def _reevaluates(trace: Trace) -> None:
    """PROP:P14 inline: every posted node reproduces exactly, every exact node within 1e-12 (the
    stage 05 exact inputs, L2-2-Q-40); every ``tp_share`` and ``catch_up`` node exactly."""
    recomputed = reevaluate(trace)
    for node in trace.nodes:
        if node.rounding_residue is not None or node.measure.startswith(("tp_share@", "catch_up@")):
            assert recomputed[node.id] == node.value, node.id
        else:
            gap = abs(Fraction(Decimal(recomputed[node.id])) - Fraction(Decimal(node.value)))
            assert gap <= Fraction(1, 10**12), node.id


def _event_key(trace: Trace, version_key: str) -> str:
    """The ESTIMATE_CHANGED event that applied ``version_key``, from its ``tp_delta`` node."""
    return next(
        node.id.split("@", 1)[1].split(":", 1)[0]
        for node in trace.nodes
        if node.id.startswith("tp_delta@") and node.params["v_new"] == version_key
    )


def _shares(trace: Trace, event_key: str) -> dict[str, TraceNode]:
    return {
        node.id.split(":")[1].rsplit("/", 1)[-1]: node
        for node in trace.nodes
        if node.id.startswith(f"tp_share@{event_key}:")
    }


def _steps(
    value: InputBundle, changes: Sequence[EstimateVersionInput], **kwargs: object
) -> list[tuple[EstimateVersionInput, BookOutput]]:
    """Public ``compute`` of ``value`` known after each change in turn: (version, ASC606 book)."""
    found: list[tuple[EstimateVersionInput, BookOutput]] = []
    for count in range(1, len(changes) + 1):
        bundle = worlds.with_changes(value, changes[:count], **kwargs)  # type: ignore[arg-type]
        (book,) = compute(bundle).books
        found.append((changes[count - 1], book))
    return found


def _review_world(
    untargeted: Sequence[tuple[date, str]],
) -> tuple[InputBundle, list[EstimateVersionInput]]:
    """The C606-02 review fixture: A/B SSP 100/100, fixed 50/50, evidenced targeted VC 100 → A and
    a contract-wide element BASE at 0, whose later versions follow ``untargeted`` (date, amount)."""
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(estimates=[worlds.element("100", keys=["A"]), base])
    changes = [
        worlds.later_version(base, number, on, amount)
        for number, (on, amount) in enumerate(untargeted, start=2)
    ]
    return value, changes


def _apply_all(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder, price_at: PriceAt
) -> tuple[AllocatedState, list[AllocatedState]]:
    """``s08.apply`` over every ESTIMATE_CHANGED after inception, in ENG-06 order; the states after
    each applied event."""
    states: list[AllocatedState] = []
    for ev in st.events:
        if ev.event_type == "ESTIMATE_CHANGED" and ev.effective_date > st.inception_date:
            st = s08_estimates_late_events.apply(ctx, st, ev, tb, price_at=price_at)
            states.append(st)
    return st, states


def _fold_apply(
    value: InputBundle,
) -> tuple[BookContext, AllocatedState, list[AllocatedState], Trace]:
    """Stages 01 to 05 over ``value``, then ``s08.apply`` with the real stage 04 price function."""
    ctx, priced, allocated, _ = worlds.fold(value)

    def price_at(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        return s04_transaction_price.price_at(ctx, priced.pob, at, None, before=before)

    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    final, states = _apply_all(ctx, allocated, tb, price_at)
    return ctx, final, states, tb.build(root_measures={})


def _carried_state(
    quotas: Mapping[str, tuple[Fraction, int]],
    weights: Mapping[str, Fraction],
    amounts: Sequence[tuple[date, int]],
    *,
    mu: int = 2,
    currency: str = "USD",
    inception: date = date(2026, 1, 1),
) -> tuple[BookContext, AllocatedState, PriceAt]:
    """A helper-level pure-inception state: point-in-time obligations carrying ``quotas`` (x, a)
    with inception weights ``weights``, and a contract-wide element BASE at 0 whose later versions
    take ``amounts`` (date, cumulative minor units). ``price_at`` = Σ a + the pinned amount."""
    ctx = book_context(entity(start=inception, months=12), currency=currency)
    obligations = [
        obligation(
            key,
            [segment(x, a, start=inception, end=inception, measure="POINT_IN_TIME")],
            method="POINT_IN_TIME",
            convention=None,
            inception_weight=weights[key],
        )
        for key, (x, a) in sorted(quotas.items())
    ]
    versions = [
        dataclasses.replace(
            estimate_version(f"{CONTRACT_KEY}/BASE", "VARIABLE_CONSIDERATION", 1, inception),
            allocation_target="CONTRACT",
            target_obligation_keys=(),
            constrained_amount=Decimal(0),
        )
    ]
    for number, (on, amount) in enumerate(amounts, start=2):
        versions.append(
            dataclasses.replace(
                versions[0],
                version_no=number,
                version_key=f"{CONTRACT_KEY}/BASE@v{number}",
                effective_date=on,
                constrained_amount=Decimal(amount) / 10**mu,
                supersedes_version_key=f"{CONTRACT_KEY}/BASE@v{number - 1}",
            )
        )
    events = [_estimate(10 + number, version) for number, version in enumerate(versions, start=1)]
    st = allocated_state(
        obligations,
        events=events,
        inception=inception,
        estimates=_pins(*zip(versions, events, strict=True)),
    )
    minor = {
        version.version_key: amount
        for version, (_, amount) in zip(versions[1:], amounts, strict=True)
    }
    basis = sum(a for _, a in quotas.values())

    def price_at(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        total = basis
        for estimate_key in sorted(st.estimates.pins):
            version = st.estimates.pin(estimate_key, at, before)
            if version is not None:
                total += minor.get(version.version_key, 0)
        quota = Quota1(Fraction(total, 10**mu), total)
        zero = Quota1(Fraction(0), 0)
        key = None if before is None else before.event_key
        return TpBuildUp(at, key, quota, *(zero,) * 8, quota, quota, ())

    return ctx, st, price_at


def _quotas(st: AllocatedState) -> dict[str, tuple[Fraction, int]]:
    return {
        ob.obligation_key: (ob.segments[-1].x_exact, ob.segments[-1].a_posted)
        for ob in st.obligations
    }


def test_s08_r07_targeted_pool_survives_untargeted_change() -> None:
    """The D-91 measured defect through the public ``compute``: A/B SSP 100/100, fixed 50/50,
    evidenced targeted VC 100 → A, A satisfied 10 January, untargeted 0 → 100 (1 Feb) → 0 (1 Mar)
    → 100 (1 Apr), POL-200 DO_NOT_APPLY. The targeted pool is carried: x_A = 150 + U/2, x_B = 50 +
    U/2 (main re-derived 150/150, 100/100, 150/150 from raw SSP with no February catch-up)."""
    value, changes = _review_world(
        [(date(2026, 2, 1), "100"), (date(2026, 3, 1), "0"), (date(2026, 4, 1), "100")]
    )
    expected = {
        "FY2026-P02": ({"A": (20000, 20000), "B": (10000, 0)}, 30000, 10000),
        "FY2026-P03": ({"A": (15000, 15000), "B": (5000, 0)}, 20000, 5000),
        "FY2026-P04": ({"A": (20000, 20000), "B": (10000, 0)}, 30000, 10000),
    }
    postings = {"FY2026-P01": 15000, "FY2026-P02": 5000, "FY2026-P03": -5000, "FY2026-P04": 5000}
    quotas: dict[str, tuple[Fraction, int]] = {
        "A": (Fraction(150), 15000),
        "B": (Fraction(50), 5000),
    }
    weights = {"A": Fraction(100), "B": Fraction(100)}
    level = 0
    for version, book in _steps(value, changes, deliveries=[(date(2026, 1, 10), "A")]):
        period = f"FY2026-P{version.effective_date.month:02d}"
        allocations, price, rpo = expected[period]
        amount = int(version.constrained_amount or 0) * 100
        quotas, mode = _carried(quotas, weights, amount - level)
        level = amount
        assert mode == "reapportion"
        assert {key: a for key, (_, a) in quotas.items()} == {
            k: v[0] for k, v in allocations.items()
        }
        assert _allocations(book) == allocations
        assert (_column(book, "transaction_price"), _column(book, "rpo_amount")) == (price, rpo)
        months = [f"FY2026-P{month:02d}" for month in range(1, version.effective_date.month + 1)]
        assert _revenue_postings(book) == {month: postings[month] for month in months}
        _reevaluates(book.trace)
        shares = _shares(book.trace, _event_key(book.trace, version.version_key))
        assert {key: node.formula_id for key, node in shares.items()} == {
            "A": "estimate.route.inception.v2",
            "B": "estimate.route.inception.v2",
        }
        assert {key: node.params["mode"] for key, node in shares.items()} == {
            "A": "reapportion",
            "B": "reapportion",
        }
        assert shares["A"].params["ssp_weights"] == "100|100"
        assert shares["A"].params["quotas_after"] == "|".join(
            rational_param(quotas[key][0]) for key in ("A", "B")
        )


@pytest.mark.parametrize(
    ("deltas", "posted"),
    [
        (
            (1, 1, 1, 1),
            [(15001, 5000), (15001, 5001), (15002, 5001), (15002, 5002)],
        ),
        (
            (1, -2, 3, -2, 3),  # cumulative +0.01, −0.01, +0.02, 0, +0.03
            [(15001, 5000), (15000, 4999), (15001, 5001), (15000, 5000), (15002, 5001)],
        ),
    ],
)
def test_s08_r07_cumulative_rounding_per_pool(
    deltas: Sequence[int], posted: Sequence[tuple[int, int]]
) -> None:
    """One apportionment of the posted price over the exact quotas after every change (S08-R-07
    (b)): Σa = basis and |x × 100 − a| < 1 at every step, a = LR(basis, [x]) by the §2.1.2 oracle,
    and the zero-net cycle restores the carried state (150.00/50.00 at cumulative 0). The naive
    incremental posting of four +0.01 changes gives 150.04/50.00."""
    quotas: dict[str, tuple[Fraction, int]] = {
        "A": (Fraction(150), 15000),
        "B": (Fraction(50), 5000),
    }
    weights = {"A": Fraction(100), "B": Fraction(100)}
    levels, level = [], 0
    for delta in deltas:
        level += delta
        levels.append((date(2026, 1 + len(levels) + 1, 1), level))
    ctx, st, price_at = _carried_state(quotas, weights, levels)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    _, states = _apply_all(ctx, st, tb, price_at)
    expected = quotas
    for delta, state, want in zip(deltas, states, posted, strict=True):
        expected, mode = _carried(expected, weights, delta)
        assert mode == "reapportion"
        got = _quotas(state)
        assert got == expected
        assert (got["A"][1], got["B"][1]) == want
        basis = state.tp_history[-1].allocation_basis.posted
        assert sum(a for _, a in got.values()) == basis  # PROP:P1
        assert all(abs(x * 100 - a) < 1 for x, a in got.values())  # PROP:P2
        assert [got[key][1] for key in sorted(got)] == _lr(
            basis, [got[key][0] for key in sorted(got)], sorted(got)
        )
    naive = {"A": 15000, "B": 5000}
    for _ in range(4):
        shares = _lr(1, [weights["A"], weights["B"]], ["A", "B"])
        naive = {"A": naive["A"] + shares[0], "B": naive["B"] + shares[1]}
    assert naive == {"A": 15004, "B": 5000}
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}


def test_s08_r07_q5_interaction_restores_quotas_not_stage05_cent() -> None:
    """Fixed 100.01, K 33.33 → [A, B], SSP 100/100: stage 05 rounds each pool (relative 50.01/50.00
    plus targeted 16.67/16.66) and posts 66.68/66.66 for exact 66.67/66.67 (L9-C606-02-Q5). The
    first untargeted change re-rounds that cent inside its Δ_p: +0.01 → 66.68/66.67; −0.01 →
    66.67/66.67. The exact quotas are restored; the posted amounts differ from inception by design,
    and the v2 params show it."""
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(
        lines=(("A", "PROD-A", "100.01"), ("B", "PROD-B", "0.00")),
        estimates=[worlds.element("33.33", keys=["A", "B"]), base],
    )
    changes = [
        worlds.later_version(base, 2, date(2026, 2, 1), "0.01"),
        worlds.later_version(base, 3, date(2026, 3, 1), "0"),
    ]
    inception = _allocations(compute(value).books[0])
    assert inception == {"A": (6668, 0), "B": (6666, 0)}
    steps = _steps(value, changes)
    assert [_allocations(book) for _, book in steps] == [
        {"A": (6668, 0), "B": (6667, 0)},
        {"A": (6667, 0), "B": (6667, 0)},
    ]
    exact = {"A": Fraction(6667, 100), "B": Fraction(6667, 100)}
    after_plus, _ = _carried(
        {k: (exact[k], inception[k][0]) for k in exact}, {"A": Fraction(100), "B": Fraction(100)}, 1
    )
    assert {k: a for k, (_, a) in after_plus.items()} == {"A": 6668, "B": 6667}
    after_minus, _ = _carried(after_plus, {"A": Fraction(100), "B": Fraction(100)}, -1)
    assert after_minus == {"A": (exact["A"], 6667), "B": (exact["B"], 6667)}
    for (version, book), quotas in zip(steps, (after_plus, after_minus), strict=True):
        shares = _shares(book.trace, _event_key(book.trace, version.version_key))
        assert shares["A"].params["mode"] == "reapportion"
        assert shares["A"].params["quotas_after"] == "|".join(
            rational_param(quotas[k][0]) for k in ("A", "B")
        )
        assert (shares["A"].params["a_before"], shares["B"].params["a_before"]) == tuple(
            str(inception[k][0] if version.version_no == 2 else after_plus[k][1])
            for k in ("A", "B")
        )
        _reevaluates(book.trace)


def test_s08_r07_two_targeted_elements_subset_targets() -> None:
    """A/B/C SSP 100/200/300, fixed 300 (50/100/150), K1 60 → [A, B] (20/40), K2 30 → C, untargeted
    0 → 60 (Feb) → 33.33 (Mar): every pool is carried and the change spreads by 1:2:3."""
    base = worlds.untargeted_element("0")
    k1 = worlds.element("60", keys=["A", "B"])
    k2 = dataclasses.replace(
        worlds.element("30", keys=["C"]),
        estimate_key="K-01/VC-2",
        element_code="VC-2",
        version_key="K-01/VC-2@v1",
    )
    value = worlds.targeted_world(
        lines=(("A", "PROD-A", "50"), ("B", "PROD-B", "100"), ("C", "PROD-C", "150")),
        ssp={"PROD-A": "100", "PROD-B": "200", "PROD-C": "300"},
        estimates=[k1, k2, base],
    )
    changes = [
        worlds.later_version(base, 2, date(2026, 2, 1), "60"),
        worlds.later_version(base, 3, date(2026, 3, 1), "33.33"),
    ]
    quotas: dict[str, tuple[Fraction, int]] = {
        "A": (Fraction(70), 7000),
        "B": (Fraction(140), 14000),
        "C": (Fraction(180), 18000),
    }
    weights = {"A": Fraction(100), "B": Fraction(200), "C": Fraction(300)}
    assert _allocations(compute(value).books[0]) == {k: (a, 0) for k, (_, a) in quotas.items()}
    steps = _steps(value, changes)
    assert [_allocations(book) for _, book in steps] == [
        {"A": (8000, 0), "B": (16000, 0), "C": (21000, 0)},
        {"A": (7555, 0), "B": (15111, 0), "C": (19667, 0)},
    ]
    for delta, (_, book) in zip((6000, 3333 - 6000), steps, strict=True):
        quotas, mode = _carried(quotas, weights, delta)
        assert mode == "reapportion"
        assert _allocations(book) == {k: (a, 0) for k, (_, a) in quotas.items()}
        _reevaluates(book.trace)


def test_s08_r07_untargeted_decrease_negative_total_quota_fails_closed() -> None:
    """U = −150 on the review fixture: x_A 150 − 75 = 75, x_B 50 − 75 = −25 → one
    ``VC_ALLOCATION_NEGATIVE`` (ERROR) on K-01/B at stage 8 under S08-R-06, no segment, the price
    appended to ``tp_history`` (main silently posted 25/25 by re-weighting the targeted pool)."""
    value, changes = _review_world([(date(2026, 2, 1), "-150")])
    ctx, final, states, trace = _fold_apply(worlds.with_changes(value, changes))
    (after,) = states
    assert [
        (f.code, f.severity, f.subject_key, f.stage, f.detail["rule"], f.detail["allocated_exact"])
        for f in after.findings
    ] == [("VC_ALLOCATION_NEGATIVE", "ERROR", "K-01/B", 8, "S08-R-06", "-25")]
    assert after.findings[0].detail["a_posted"] == "-2500"
    assert _quotas(after) == {"A": (Fraction(150), 15000), "B": (Fraction(50), 5000)}
    assert all(len(ob.segments) == 1 for ob in after.obligations)
    assert [tp.allocation_basis.posted for tp in after.tp_history] == [20000, 5000]
    shares = _shares(trace, "K-01/EV-000005")
    assert {key: (node.params["mode"], node.value) for key, node in shares.items()} == {
        "A": ("incremental", "-75.00"),
        "B": ("incremental", "-75.00"),
    }
    assert shares["B"].params["quotas_after"] == "75|-25"


def test_s08_r07_targeted_to_each_obligation_decrease_within_totals_does_not_raise() -> None:
    """The predicate is on each obligation's total exact quota, not an untargeted-pool budget:
    fixed 50/50, targeted 100 → A and 100 → B, U = −150 gives 75/75 and no finding."""
    base = worlds.untargeted_element("0")
    to_a = worlds.element("100", keys=["A"])
    to_b = dataclasses.replace(
        worlds.element("100", keys=["B"]),
        estimate_key="K-01/VC-2",
        element_code="VC-2",
        version_key="K-01/VC-2@v1",
    )
    value = worlds.targeted_world(estimates=[to_a, to_b, base])
    changes = [worlds.later_version(base, 2, date(2026, 2, 1), "-150")]
    _, final, _, trace = _fold_apply(worlds.with_changes(value, changes))
    assert final.findings == ()
    assert _quotas(final) == {"A": (Fraction(75), 7500), "B": (Fraction(75), 7500)}
    assert {key: node.params["mode"] for key, node in _shares(trace, "K-01/EV-000006").items()} == {
        "A": "reapportion",
        "B": "reapportion",
    }
    (book,) = compute(worlds.with_changes(value, changes)).books
    assert _allocations(book) == {"A": (7500, 0), "B": (7500, 0)}


def test_s08_r06_negative_exact_quota_below_one_minor_unit() -> None:
    """A newly negative exact quota below one minor unit raises even with both postings 0: SSP
    10/90, fixed 0.01, targeted 5.00 → B, U −0.02 gives x′_A = −1/1000 (posted 0 → 0; the
    prototype posted A 0 / B 4.99 with no finding, main 0.50/4.49); on the review fixture U −100.01
    gives x′_B = −1/200 → finding on B."""
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(
        lines=(("A", "PROD-A", "0.01"), ("B", "PROD-B", "0.00")),
        ssp={"PROD-A": "10", "PROD-B": "90"},
        estimates=[worlds.element("5.00", keys=["B"]), base],
    )
    ctx, final, states, _ = _fold_apply(
        worlds.with_changes(value, [worlds.later_version(base, 2, date(2026, 2, 1), "-0.02")])
    )
    (after,) = states
    assert _quotas(after) == {"A": (Fraction(1, 1000), 0), "B": (Fraction(5009, 1000), 501)}
    assert [
        (f.code, f.subject_key, f.detail["allocated_exact"], f.detail["a_posted"])
        for f in after.findings
    ] == [("VC_ALLOCATION_NEGATIVE", "K-01/A", "-0.001", "0")]
    assert all(len(ob.segments) == 1 for ob in after.obligations)
    review, changes = _review_world([(date(2026, 2, 1), "-100.01")])
    _, _, (after,), _ = _fold_apply(worlds.with_changes(review, changes))
    assert [(f.code, f.subject_key, f.detail["allocated_exact"]) for f in after.findings] == [
        ("VC_ALLOCATION_NEGATIVE", "K-01/B", "-0.005")
    ]


def test_s08_r06_inception_negative_exact_quota_does_not_fire() -> None:
    """S05-R-10 symmetric negative T (PROP:P3): A x −0.004 posted 0, B x −0.996 posted −1.00; a
    later −0.01 leaves both exact quotas negative, so nothing raises even though A's posted amount
    moves from 0 to −0.01 (the posting follows the exact quota); main fired on the posted sign."""
    quotas = {"A": (Fraction(-4, 1000), 0), "B": (Fraction(-996, 1000), -100)}
    weights = {"A": Fraction(100), "B": Fraction(100)}
    ctx, st, price_at = _carried_state(quotas, weights, [(date(2026, 2, 1), -1)])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    final, (after,) = _apply_all(ctx, st, tb, price_at)
    assert after.findings == ()
    expected, mode = _carried(quotas, weights, -1)
    assert mode == "incremental"
    assert (
        _quotas(after)
        == expected
        == {"A": (Fraction(-9, 1000), -1), "B": (Fraction(-1001, 1000), -100)}
    )
    assert all(len(ob.segments) == 2 for ob in after.obligations)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert {k: n.params["mode"] for k, n in _shares(trace, "K-01/EV-000012").items()} == {
        "A": "incremental",
        "B": "incremental",
    }


@pytest.mark.parametrize(("currency", "mu"), [("JPY", 0), ("BHD", 3)])
def test_s08_r07_minor_unit_currencies(currency: str, mu: int) -> None:
    """0- and 3-decimal currencies at the helper level: SSP 100/100, fixed 101, targeted 100 on
    POB-01, untargeted levels 0, 1, 2, 3, 4, 3, −1, 7, 0 (minor units). At every step Σa = basis
    (P1), |x × 10^μ − a| < 1 (P2) and a = LR(basis, [x]); the posted pairs are the ruled ones."""
    weights = {"POB-01": Fraction(100), "POB-02": Fraction(100)}
    x0 = {
        key: Fraction(101, 10**mu) * weights[key] / 200
        + (Fraction(100, 10**mu) if key == "POB-01" else 0)
        for key in weights
    }
    a0 = dict(
        zip(
            sorted(weights),
            _lr(201, [x0[key] for key in sorted(weights)], sorted(weights)),
            strict=True,
        )
    )
    assert a0 == {"POB-01": 151, "POB-02": 50}
    quotas = {key: (x0[key], a0[key]) for key in weights}
    levels = [1, 2, 3, 4, 3, -1, 7, 0]
    amounts = [(date(2026, 2 + index, 1), level) for index, level in enumerate(levels)]
    ctx, st, price_at = _carried_state(quotas, weights, amounts, mu=mu, currency=currency)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    _, states = _apply_all(ctx, st, tb, price_at)
    expected_posted = [
        (151, 51),
        (152, 51),
        (152, 52),
        (153, 52),
        (152, 52),
        (150, 50),
        (154, 54),
        (151, 50),
    ]
    previous = 0
    for level, state, want in zip(levels, states, expected_posted, strict=True):
        quotas, mode = _carried(quotas, weights, level - previous, mu)
        previous = level
        assert mode == "reapportion"
        got = _quotas(state)
        assert got == quotas
        assert (got["POB-01"][1], got["POB-02"][1]) == want
        basis = state.tp_history[-1].allocation_basis.posted
        assert basis == 201 + level and sum(a for _, a in got.values()) == basis
        assert all(abs(x * 10**mu - a) < 1 for x, a in got.values())
        assert [got[key][1] for key in sorted(got)] == _lr(
            basis, [got[key][0] for key in sorted(got)], sorted(got)
        )
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}


def test_s08_r07_minor_unit_public_compute() -> None:
    """One public-compute 0-decimal case: a JPY contract, A/B SSP 100/100, fixed 51/50, targeted
    100 → A, untargeted 0 → 1 → 3: 151/51 then 152/52 (P1, P2 in whole yen)."""
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(
        lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")),
        estimates=[worlds.element("100", keys=["A"]), base],
    )
    value = _in_currency(value, "JPY")
    changes = [
        worlds.later_version(base, 2, date(2026, 2, 1), "1"),
        worlds.later_version(base, 3, date(2026, 3, 1), "3"),
    ]
    assert _allocations(compute(value).books[0]) == {"A": (151, 0), "B": (50, 0)}
    quotas: dict[str, tuple[Fraction, int]] = {
        "A": (Fraction(301, 2), 151),
        "B": (Fraction(101, 2), 50),
    }
    weights = {"A": Fraction(100), "B": Fraction(100)}
    for delta, (_, book) in zip((1, 2), _steps(value, changes), strict=True):
        quotas, _mode = _carried(quotas, weights, delta, 0)
        assert _allocations(book) == {k: (a, 0) for k, (_, a) in quotas.items()}
        assert _column(book, "transaction_price") == sum(a for _, a in quotas.values())
        _reevaluates(book.trace)
    assert {k: a for k, (_, a) in quotas.items()} == {"A": 152, "B": 52}


def _in_currency(value: InputBundle, currency: str) -> InputBundle:
    """``value`` re-denominated in ``currency``: entity, contract, group, SSP entries, estimates."""
    entities = tuple(
        dataclasses.replace(item, functional_currency=currency) for item in value.entities
    )
    contracts = tuple(
        dataclasses.replace(item, transaction_currency=currency) for item in value.contracts
    )
    ssp = tuple(
        dataclasses.replace(
            version,
            entries=tuple(
                dataclasses.replace(
                    item,
                    entry_key=item.entry_key.replace("/USD", f"/{currency}"),
                    currency=currency,
                )
                for item in version.entries
            ),
        )
        for version in value.ssp_versions
    )
    return dataclasses.replace(
        value,
        currencies=bundles.currencies(currency),
        entities=entities,
        contracts=contracts,
        group=dataclasses.replace(value.group, transaction_currency=currency),
        ssp_versions=ssp,
        estimate_versions=tuple(
            dataclasses.replace(item, currency=currency) for item in value.estimate_versions
        ),
    )


def test_s08_r07_discount_exception_and_residual_pools_survive_change() -> None:
    """Exception pools are carried and the increment spreads by the S08-R-04 weights (D-91 reading
    (i) and (iii)). FASB Example 34 Case A (discount exception 40/33/27) + 14.00 → 44.00 / 38.50 /
    31.50 (main 32.57 / 44.79 / 36.64); Case B (residual D = 30) + 13.00 with weights 40/55/45/30
    (D at its inception residual R) → 43.06 / 37.21 / 30.44 / 32.29 (main 40.86 / 56.18 / 45.96 /
    0.00; the prototype's weight 0 gave 43.71 / 38.11 / 31.18 / 30.00)."""
    base = worlds.untargeted_element("0", code="VC-U")
    case_a = worlds.ex_34(
        "40.00", "30.00", "30.00", judgements=[worlds.approval()], activated=True, estimates=[base]
    )
    bundle_a = worlds.with_changes(
        case_a, [worlds.later_version(base, 2, date(2026, 2, 1), "14.00")]
    )
    (book,) = compute(bundle_a).books
    assert _allocations(book) == {"L1-A": (4400, 0), "L2-B": (3850, 0), "L3-C": (3150, 0)}
    quotas, mode = _carried(
        {"L1-A": (Fraction(40), 4000), "L2-B": (Fraction(33), 3300), "L3-C": (Fraction(27), 2700)},
        {"L1-A": Fraction(40), "L2-B": Fraction(55), "L3-C": Fraction(45)},
        1400,
    )
    assert (mode, {k: a for k, (_, a) in quotas.items()}) == (
        "reapportion",
        {"L1-A": 4400, "L2-B": 3850, "L3-C": 3150},
    )
    _reevaluates(book.trace)
    (share,) = [
        n for n in book.trace.nodes if n.id.startswith("tp_share@") and n.id.endswith("/L1-A:-")
    ]
    assert share.params["ssp_weights"] == "40|55|45"

    case_b = worlds.ex_34(
        "40.00",
        "30.00",
        "30.00",
        "30.00",
        residual=worlds.RESIDUAL_D,
        judgements=[worlds.approval()],
        activated=True,
        estimates=[base],
    )
    bundle_b = worlds.with_changes(
        case_b, [worlds.later_version(base, 2, date(2026, 2, 1), "13.00")]
    )
    (book,) = compute(bundle_b).books
    assert _allocations(book) == {
        "L1-A": (4306, 0),
        "L2-B": (3721, 0),
        "L3-C": (3044, 0),
        "L4-D": (3229, 0),
    }
    quotas, mode = _carried(
        {
            "L1-A": (Fraction(40), 4000),
            "L2-B": (Fraction(33), 3300),
            "L3-C": (Fraction(27), 2700),
            "L4-D": (Fraction(30), 3000),
        },
        {"L1-A": Fraction(40), "L2-B": Fraction(55), "L3-C": Fraction(45), "L4-D": Fraction(30)},
        1300,
    )
    assert {k: a for k, (_, a) in quotas.items()} == {
        "L1-A": 4306,
        "L2-B": 3721,
        "L3-C": 3044,
        "L4-D": 3229,
    }
    _reevaluates(book.trace)
    (share,) = [
        n for n in book.trace.nodes if n.id.startswith("tp_share@") and n.id.endswith("/L4-D:-")
    ]
    assert share.params["ssp_weights"] == "40|55|45|30"
    # The weight of the residual candidate is its inception R, recorded by stage 05 (S08-R-04).
    _, _, allocated, _ = worlds.fold(case_b)
    weights = {ob.obligation_key: ob.inception_weight for ob in allocated.obligations}
    assert weights == {
        "L1-A": 40,
        "L2-B": 55,
        "L3-C": 45,
        "L4-D": 30,
    }


def test_s08_r07_total_weight_zero() -> None:
    """Σw = 0 raises ``TOTAL_WEIGHT_ZERO`` before any division (S08-R-07 (a); CV-32); a version
    that leaves the price unchanged never reaches routing, so zero weights raise nothing there."""
    quotas = {"A": (Fraction(150), 15000), "B": (Fraction(50), 5000)}
    zero = {"A": Fraction(0), "B": Fraction(0)}
    ctx, st, price_at = _carried_state(quotas, zero, [(date(2026, 2, 1), 100)])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    with pytest.raises(EngineError) as raised:
        _apply_all(ctx, st, tb, price_at)
    assert (raised.value.code, raised.value.detail["rule"]) == ("TOTAL_WEIGHT_ZERO", "S08-R-07")
    ctx, st, price_at = _carried_state(quotas, zero, [(date(2026, 2, 1), 0)])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    final, (after,) = _apply_all(ctx, st, tb, price_at)
    assert [tp.allocation_basis.posted for tp in after.tp_history] == [20000]
    assert _quotas(after) == quotas and after.findings == ()
    assert not [n.id for n in tb.build(root_measures={}).nodes if n.id.startswith("tp_share@")]


def _guarded(
    first: EstimateVersionInput, second: EstimateVersionInput
) -> tuple[BookContext, AllocatedState, TraceBuilder, PriceAt]:
    """Two point-in-time obligations of 100.00 each with the element versions ``first`` (inception)
    and ``second`` (1 Feb) pinned; ``price_at`` = 200.00 plus the pinned amount."""
    ctx = book_context()
    start = date(2026, 1, 1)
    obligations = [
        obligation(
            key,
            [segment(Fraction(100), 10000, start=start, end=start, measure="POINT_IN_TIME")],
            method="POINT_IN_TIME",
            convention=None,
        )
        for key in ("POB-01", "POB-02")
    ]
    events = [_estimate(3, first), _estimate(4, second)]
    st = allocated_state(
        obligations, events=events, estimates=_pins((first, events[0]), (second, events[1]))
    )
    amounts = {
        first.version_key: int((first.constrained_amount or 0) * 100),
        second.version_key: int((second.constrained_amount or 0) * 100),
    }
    return (
        ctx,
        st,
        TraceBuilder(engine_version=ENGINE_VERSION),
        _price_at(lambda at: usd("200.00"), amounts),
    )


def _targeted_version(
    version_no: int, effective: date, amount: str, targets: Sequence[str], evidence: str | None
) -> EstimateVersionInput:
    version = _version(
        "VC-T",
        "VARIABLE_CONSIDERATION",
        version_no,
        effective,
        amount=amount,
        target="OBLIGATIONS",
        targets=targets,
    )
    parameters = {} if evidence is None else {"allocation_criteria_evidence": evidence}
    return dataclasses.replace(version, parameters=parameters)


@pytest.mark.parametrize("amount", ["150.00", "100.00"], ids=["price-changes", "same-price"])
def test_s08_r04_target_set_change_fails_closed(amount: str) -> None:
    """A version whose target set differs from the element's version 1 is refused in
    ``estimates.apply`` before the zero-delta early return (S08-R-04; CV-45): nothing moves and no
    node is added, whether or not the price changes."""
    first = _targeted_version(1, date(2026, 1, 1), "100.00", ["POB-01"], "attested")
    second = _targeted_version(2, date(2026, 2, 1), amount, ["POB-02"], "attested")
    ctx, st, tb, price_at = _guarded(first, second)
    with pytest.raises(EngineError) as raised:
        s08_estimates_late_events.apply(ctx, st, st.events[1], tb, price_at=price_at)
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert (raised.value.detail["rule"], raised.value.detail["reason"]) == (
        "S08-R-04",
        "target_set_changed",
    )
    assert (raised.value.detail["v_first"], raised.value.detail["v_new"]) == (
        first.version_key,
        second.version_key,
    )
    assert not [
        n.id
        for n in tb.build(root_measures={}).nodes
        if n.id.startswith(("tp_share@", "tp_delta@"))
    ]


@pytest.mark.parametrize(
    ("before", "after"),
    [(None, "attested"), ("", "attested"), ("attested", "")],
    ids=["null-to-non-empty", "empty-string-to-non-empty", "non-empty-to-empty-string"],
)
@pytest.mark.parametrize("amount", ["150.00", "100.00"], ids=["price-changes", "same-price"])
def test_s08_r04_evidence_state_change_fails_closed(
    before: str | None, after: str, amount: str
) -> None:
    """A version whose 32-40 evidence state differs from version 1 in either direction is refused
    before the zero-delta return; the predicate is the shared stage 05 ``targeted.evidenced``
    (present and non-empty), not a null-only check. Before the fix an evidence-at-v2 version
    recorded a Δ-only quota silently and a same-price version returned early unguarded."""
    first = _targeted_version(1, date(2026, 1, 1), "100.00", ["POB-01"], before)
    second = _targeted_version(2, date(2026, 2, 1), amount, ["POB-01"], after)
    ctx, st, tb, price_at = _guarded(first, second)
    with pytest.raises(EngineError) as raised:
        s08_estimates_late_events.apply(ctx, st, st.events[1], tb, price_at=price_at)
    assert (raised.value.code, raised.value.detail["rule"], raised.value.detail["reason"]) == (
        "ENGINE_INVARIANT_VIOLATED",
        "S08-R-04",
        "evidence_changed",
    )
    assert not [
        n.id
        for n in tb.build(root_measures={}).nodes
        if n.id.startswith(("tp_share@", "tp_delta@"))
    ]
    # The same states on both versions pass the guard.
    same = _targeted_version(2, date(2026, 2, 1), amount, ["POB-01"], before)
    ctx, st, tb, price_at = _guarded(first, same)
    result = s08_estimates_late_events.apply(ctx, st, st.events[1], tb, price_at=price_at)
    assert result.findings == ()


def test_s08_r07_dated_targeted_quota_history() -> None:
    """S05-R-14 (rev 1.6): stage 05 seeds ``targeted_vc_quota_history`` with the inception quota and
    stage 08 appends (effective date, quota after the change) after every reallocating version of
    an evidenced ``OBLIGATIONS`` element whose segments were added; ``targeted_vc_quotas`` holds the
    latest quota; an untargeted change and a blocked change append nothing."""
    targeted = worlds.element("100", keys=["A"])
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(estimates=[targeted, base])
    ctx, priced, allocated, _ = worlds.fold(value)
    assert dict(allocated.targeted_vc_quota_history["K-01/VC-1"]) == {
        "K-01/A": ((date(2026, 1, 1), Quota(Fraction(100), 10000)),)
    }
    changes = [
        worlds.later_version(targeted, 2, date(2026, 2, 1), "200"),
        worlds.later_version(base, 2, date(2026, 3, 1), "100"),
        worlds.later_version(targeted, 3, date(2026, 4, 1), "-50"),
    ]
    _, final, states, _ = _fold_apply(worlds.with_changes(value, changes))
    assert [dict(s.targeted_vc_quota_history["K-01/VC-1"])["K-01/A"] for s in states] == [
        (
            (date(2026, 1, 1), Quota(Fraction(100), 10000)),
            (date(2026, 2, 1), Quota(Fraction(200), 20000)),
        ),
        (
            (date(2026, 1, 1), Quota(Fraction(100), 10000)),
            (date(2026, 2, 1), Quota(Fraction(200), 20000)),
        ),
        (
            (date(2026, 1, 1), Quota(Fraction(100), 10000)),
            (date(2026, 2, 1), Quota(Fraction(200), 20000)),
            (date(2026, 4, 1), Quota(Fraction(-50), -5000)),
        ),
    ]
    assert final.targeted_vc_quotas["K-01/VC-1"]["K-01/A"] == Quota(Fraction(-50), -5000)
    assert final.findings == ()  # x_A 250 → 300 → 50: never negative
    assert _quotas(final) == {"A": (Fraction(50), 5000), "B": (Fraction(100), 10000)}
    # A blocked change (x_B → −25) appends nothing.
    blocked, blocked_changes = _review_world([(date(2026, 2, 1), "-150")])
    _, after, _, _ = _fold_apply(worlds.with_changes(blocked, blocked_changes))
    assert after.findings and dict(after.targeted_vc_quota_history["K-01/VC-1"]) == {
        "K-01/A": ((date(2026, 1, 1), Quota(Fraction(100), 10000)),)
    }
