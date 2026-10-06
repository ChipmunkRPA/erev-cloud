"""Stage 08 late events, replay and posting-period assignment.

ENGINE_SPEC §8.4 S08-R-08 to S08-R-13, §8.6 S08-INV-03 and §8.7 EX-08-A, EX-08-D; POLICIES ALG-09
(CHK-090, CHK-091), POL-042 and POL-180; legacy 03 §7.3 TC-15 and legacy 04 §7.3 TC-RM-13. Stages 02
to 06 are built in other lanes, so the tests build ``AllocatedState`` against ENGINE_SPEC §0.11
through ``support/recognition.py``, and the TC-15 post-modification segment stands in for stage 06
(D-81 integration after merge). Stage 01 orders the CHK-091 stream, and stage 09 measures the
replayed state. Every trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EstimateVersionInput, EventInput, InputBundle
from erev_engine.money import largest_remainder
from erev_engine.stages import s01_canonicalize
from erev_engine.stages.s08_estimates_late_events import (
    Assignment,
    LateEventFact,
    ReassessmentGap,
    assign_posting_period,
    late_events,
)
from erev_engine.stages.s09_recognition import run, target_at_position
from erev_engine.stages.state import (
    EstimatePin,
    EstimatePins,
    EventView,
    Finding,
    ObligationState,
    SegmentCause,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    estimate_version,
    event_view,
    obligation,
    segment,
    targets_by_period,
    usd,
)

ENTITY = bundles.ENTITY_CODE
JANUARY_2023 = date(2023, 1, 1)
YEAR_END_2023 = date(2023, 12, 31)
POSTABLE = ("open", "closing", "reopened")
UNAVAILABLE = ("closed", "permanently_locked", "future")
# Golden Contract 1 (legacy 02 §5.3; legacy 07 §4.4): price 1,300.00; (POB, quantity, extended SSP).
GOLDEN_CONTRACT_1 = (
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


def _recorded(ev: EventView, when: datetime, *, is_new: bool = True) -> EventView:
    """``ev`` recorded at ``when``; ``is_new`` is false for events of an earlier computation."""
    return dataclasses.replace(ev, recorded_at=when, is_new=is_new)


def _findings(findings: tuple[Finding, ...]) -> list[tuple[str, str, str | None, dict[str, str]]]:
    return [(item.code, item.severity, item.subject_key, dict(item.detail)) for item in findings]


def _detail(ev: EventView, origin: str, posting: str, reason: str) -> dict[str, str]:
    return {
        "event_key": ev.event_key,
        "origin_period_key": origin,
        "posting_period_key": posting,
        "reason": reason,
        "rule": "S08-R-10",
    }


def _units_delivery(
    contract_key: str, stream_version: int, effective: date, obligation_key: str, quantity: str
) -> EventView:
    payload = {
        "obligation_key": obligation_key,
        "quantity": Decimal(quantity),
        "trigger": "CONTROL_TRANSFER",
    }
    return event_view(
        contract_key,
        stream_version,
        "DELIVERY_RECORDED",
        effective,
        payload,
        obligation_keys=[obligation_key],
    )


def _units_obligation(quantity: str = "5", price: str = "500.00") -> ObligationState:
    seg = segment(
        Fraction(Decimal(price)),
        usd(price),
        start=JANUARY_2023,
        end=YEAR_END_2023,
        quantity=Fraction(quantity),
        measure="UNITS_DELIVERED",
    )
    return obligation(
        "POB-01",
        [seg],
        method="UNITS_DELIVERED",
        convention=None,
        start=JANUARY_2023,
        quantity=Fraction(quantity),
    )


def _golden_contract_1() -> list[ObligationState]:
    """Inception segments: X = 1,300 × extended SSP ÷ 2,018, A by largest remainder (ALG-01)."""
    total = sum(ssp for *_, ssp in GOLDEN_CONTRACT_1)
    posted = largest_remainder(
        1300 * 100,
        [Fraction(ssp) for *_, ssp in GOLDEN_CONTRACT_1],
        [key for key, *_ in GOLDEN_CONTRACT_1],
    )
    obligations = []
    for (key, quantity, ssp), a_posted in zip(GOLDEN_CONTRACT_1, posted, strict=True):
        seg = segment(
            Fraction(1300 * ssp, total),
            a_posted,
            start=JANUARY_2023,
            end=YEAR_END_2023,
            quantity=Fraction(quantity),
            measure="UNITS_DELIVERED",
        )
        obligations.append(
            obligation(
                key,
                [seg],
                contract_key="Contract 1",
                method="UNITS_DELIVERED",
                convention=None,
                start=JANUARY_2023,
                quantity=Fraction(quantity),
            )
        )
    return obligations


def test_chk_090_late_delivery_assignment() -> None:
    ctx = book_context(
        bundles.entity(start=JANUARY_2023, months=12, states={"FY2023-P01": "closed"}),
        preset="LEGACY_PARITY",
    )
    assert assign_posting_period(ctx, ENTITY, date(2023, 1, 31)) == Assignment(
        "FY2023-P02", "FY2023-P01", "LATE_EVENT"
    )
    committed = [  # invoiced on 31 January, before the lock of 3 February
        _recorded(
            event_view(
                "Contract 1",
                version,
                "BILLING_RECORDED",
                date(2023, 1, 31),
                {
                    "invoice_number": f"INV-C1-01{version}",
                    "line_external_id": f"INV-C1-01{version}-1",
                    "obligation_key": key,
                    "amount": Decimal("100.00"),
                    "issue_date": date(2023, 1, 31),
                },
                obligation_keys=[key],
            ),
            datetime(2023, 1, 31, 17, version, tzinfo=UTC),
            is_new=False,
        )
        for version, key in ((2, "POB #1"), (3, "POB #2"), (4, "POB #3"))
    ]
    late = [  # delivered on 31 January, recorded on 5 February
        _recorded(
            event_view(
                "Contract 1",
                version,
                "DELIVERY_RECORDED",
                date(2023, 1, 31),
                {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"},
                obligation_keys=[key],
            ),
            datetime(2023, 2, 5, 15, version, tzinfo=UTC),
        )
        for version, key, quantity in ((5, "POB #1", "2"), (6, "POB #2", "1"), (7, "POB #3", "0.5"))
    ]
    st = allocated_state(_golden_contract_1(), events=[*committed, *late], inception=JANUARY_2023)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)

    out = late_events(ctx, st, tb)
    assert _findings(out.findings) == [
        (
            "LATE_EVENT",
            "WARNING",
            f"Contract 1/{key}",
            _detail(ev, "FY2023-P01", "FY2023-P02", "CLOSED_PERIOD"),
        )
        for ev, key in zip(late, ("POB #1", "POB #2", "POB #3"), strict=True)
    ]
    assert out.register == tuple(
        LateEventFact(ev.event_key, "Contract 1", "FY2023-P01", "FY2023-P02", "DELIVERY_RECORDED")
        for ev in late
    )
    assert out.close_gate_facts == ()

    # S08-R-09: the replay measures January with the late deliveries at their effective position.
    state = run(ctx, st, tb)
    trace = _trace(tb)
    january = {
        key: targets_by_period(state, f"Contract 1/{key}")["FY2023-P01"]
        for key in ("POB #1", "POB #2", "POB #3")
    }
    assert january == {"POB #1": usd("128.84"), "POB #2": usd("118.53"), "POB #3": usd("48.32")}
    assert sum(january.values()) == usd("295.69")
    carried = _node(trace, f"late_assign@{late[0].event_key}:Contract 1:-")
    assert (carried.formula_id, carried.value, carried.params["states"]) == (
        "late.assign.v1",
        "1",
        "closed|open",
    )
    assert (carried.params["origin_period_key"], carried.params["posting_period_key"]) == (
        "FY2023-P01",
        "FY2023-P02",
    )


def _contract_2_bundle(events: list[EventInput]) -> InputBundle:
    calendar = bundles.entity(start=JANUARY_2023, months=12)
    header = bundles.contract("Contract 2", inception=JANUARY_2023)
    products = [bundles.product(code) for code in ("Consulting 1", "Hardware 1", "Software 1")]
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2023, 4, 2, 16, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(bundles.book(entity=calendar),),
        entities=(calendar,),
        group=bundles.group([header], products=products),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_chk_091_effective_date_order() -> None:
    contract = "Contract 2"
    lines = [
        bundles.booking_line(
            key,
            product_code=product,
            quantity=qty,
            total_price=price,
            start=JANUARY_2023,
            end=YEAR_END_2023,
        )
        for key, product, qty, price in (
            ("POB #1", "Hardware 1", "8", "600.00"),
            ("POB #2", "Software 1", "3", "200.00"),
            ("POB #3", "Consulting 1", "1", "100.00"),
        )
    ]
    booked = bundles.event(
        contract,
        1,
        "CONTRACT_BOOKED",
        JANUARY_2023,
        {"lines": lines},
        obligation_keys=["POB #1", "POB #2", "POB #3"],
    )
    hardware = bundles.event(
        contract,
        2,
        "DELIVERY_RECORDED",
        date(2023, 1, 31),
        {"obligation_key": "POB #1", "quantity": Decimal("1"), "trigger": "DELIVERY"},
        obligation_keys=["POB #1"],
    )
    software = dataclasses.replace(  # dated 31 March, recorded first
        bundles.event(
            contract,
            3,
            "DELIVERY_RECORDED",
            date(2023, 3, 31),
            {"obligation_key": "POB #2", "quantity": Decimal("1"), "trigger": "DELIVERY"},
            obligation_keys=["POB #2"],
        ),
        recorded_at=datetime(2023, 4, 2, 15, tzinfo=UTC),
    )
    billing = dataclasses.replace(  # dated 28 February, recorded second
        bundles.event(
            contract,
            4,
            "BILLING_RECORDED",
            date(2023, 2, 28),
            {
                "invoice_number": "INV-C2-0201",
                "line_external_id": "INV-C2-0201-1",
                "obligation_key": "POB #1",
                "amount": Decimal("500.00"),
                "issue_date": date(2023, 2, 28),
            },
            obligation_keys=["POB #1"],
        ),
        recorded_at=datetime(2023, 4, 2, 15, 10, tzinfo=UTC),
    )
    # The stage 01 ingest formulas are registered by ENA-13 (lane L2-2), so its nodes stay in their
    # own builder and only the stage 08 trace is re-evaluated here.
    ingest = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(_contract_2_bundle([booked, hardware, software, billing]), ingest)
    assert [ev.event_key for ev in cb.events] == [
        booked.event_key,
        hardware.event_key,
        billing.event_key,
        software.event_key,
    ]
    assert billing.record_seq > software.record_seq  # recorded later, folded earlier (ENG-06)

    ctx = book_context(bundles.entity(start=JANUARY_2023, months=12))
    st = allocated_state(
        [], contracts=list(cb.contracts.values()), events=cb.events, inception=JANUARY_2023
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    out = late_events(ctx, st, tb)
    assert _findings(out.findings) == [
        (
            "LATE_EVENT",
            "WARNING",
            "Contract 2/POB %231",
            _detail(cb.events[2], "-", "FY2023-P02", "OUT_OF_ORDER"),
        )
    ]
    assert out.register == ()  # every period is open: nothing carries an origin
    trace = _trace(tb)
    assert not [node for node in trace.nodes if node.measure.startswith("late_assign@")]


def test_ex_08_d_origin_carry() -> None:
    ctx = book_context(
        bundles.entity(
            start=date(2026, 1, 1),
            months=24,
            states={"FY2026-P12": "permanently_locked", "FY2027-P01": "closed"},
        )
    )
    assert assign_posting_period(ctx, ENTITY, date(2026, 12, 31)) == Assignment(
        "FY2027-P02", "FY2026-P12", "LATE_EVENT"
    )
    changed = _recorded(
        event_view(
            CONTRACT_KEY,
            5,
            "ESTIMATE_CHANGED",
            date(2026, 12, 31),
            {"estimate_version_id": f"{CONTRACT_KEY}/VC-CONCESSION@v2"},
        ),
        datetime(2027, 2, 10, 9, tzinfo=UTC),
    )
    goods = segment(
        Fraction(50000), usd("50000.00"), start=date(2026, 12, 1), end=date(2026, 12, 1)
    )
    ob = obligation("L1-PROD", [goods], method="POINT_IN_TIME", convention=None)
    st = allocated_state([ob], events=[changed], inception=date(2026, 12, 1))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)

    out = late_events(ctx, st, tb)
    assert _findings(out.findings) == [
        (
            "LATE_EVENT",
            "WARNING",
            CONTRACT_KEY,
            _detail(changed, "FY2026-P12", "FY2027-P02", "CLOSED_PERIOD"),
        )
    ]
    assert out.register == (
        LateEventFact(
            changed.event_key, CONTRACT_KEY, "FY2026-P12", "FY2027-P02", "ESTIMATE_CHANGED"
        ),
    )
    carried = _node(_trace(tb), f"late_assign@{changed.event_key}:{CONTRACT_KEY}:-")
    assert (carried.value, carried.params["states"], carried.params["reason_code"]) == (
        "2",
        "permanently_locked|closed|open",
        "LATE_EVENT",
    )


def test_tc_prospective_15_backdated_modification_resequenced() -> None:
    ctx = book_context(bundles.entity(start=JANUARY_2023, months=12))
    delivery = _recorded(
        _units_delivery(CONTRACT_KEY, 2, date(2023, 1, 31), "POB-01", "2"),
        datetime(2023, 1, 31, 17, tzinfo=UTC),
    )
    amended = _recorded(  # dated 15 January, recorded after the 31 January delivery
        event_view(
            CONTRACT_KEY,
            3,
            "CONTRACT_AMENDED",
            date(2023, 1, 15),
            {"modification_id": "MOD-TC-15"},
            obligation_keys=["POB-01"],
        ),
        datetime(2023, 2, 2, 9, tzinfo=UTC),
    )
    inception = _units_obligation().segments[0]
    # Stage 06 stand-in (D-81): the 25-13(a) segment at the amendment position, one unit added for
    # 150.00, with nothing delivered before the boundary.
    modified = segment(
        Fraction(650),
        usd("650.00"),
        start=JANUARY_2023,
        end=YEAR_END_2023,
        effective=date(2023, 1, 15),
        basis="PROSPECTIVE",
        cause=SegmentCause.MODIFICATION,
        event_key=amended.event_key,
        quantity=Fraction(6),
        measure="UNITS_DELIVERED",
    )
    ob = dataclasses.replace(
        _units_obligation(), segments=(inception, modified), quantity=Fraction(6)
    )
    st = allocated_state([ob], events=[delivery, amended], inception=JANUARY_2023)
    # ENG-06 folds the amendment at its effective position, before the delivery recorded earlier.
    assert amended.record_seq > delivery.record_seq and amended.order_key < delivery.order_key
    assert [ev.event_key for ev in st.events] == [amended.event_key, delivery.event_key]

    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    out = late_events(ctx, st, tb)
    assert _findings(out.findings) == [
        (
            "LATE_EVENT",
            "WARNING",
            f"{CONTRACT_KEY}/POB-01",
            _detail(amended, "-", "FY2023-P01", "OUT_OF_ORDER"),
        )
    ]
    assert out.register == ()

    before = target_at_position(ctx, st, ob, date(2023, 1, 31), event=delivery, inclusive=False)
    after = target_at_position(ctx, st, ob, date(2023, 1, 31), event=delivery, inclusive=True)
    assert before.segment == modified and after.segment == modified
    assert (before.value, after.value) == (0, usd("216.67"))  # 650 × 2/6 since the boundary
    unmodified = dataclasses.replace(ob, segments=(inception,), quantity=Fraction(5))
    assert target_at_position(ctx, st, unmodified, date(2023, 1, 31)).value == usd("200.00")

    emit_catch_up_nodes(tb, ctx, st)  # the stage 06 node stage 09 cites (D-81)
    state = run(ctx, st, tb)
    _trace(tb)
    assert targets_by_period(state, f"{CONTRACT_KEY}/POB-01")["FY2023-P01"] == usd("216.67")


def test_tc_rm_13_backdated_retro_modification_in_closed_period() -> None:
    closed = {f"FY2023-P0{month}": "closed" for month in range(1, 5)}
    ctx = book_context(
        bundles.entity(start=JANUARY_2023, months=12, states=closed), preset="LEGACY_PARITY"
    )
    assert assign_posting_period(ctx, ENTITY, date(2023, 1, 15)) == Assignment(
        "FY2023-P05", "FY2023-P01", "LATE_EVENT"
    )
    delivered = _recorded(
        _units_delivery(CONTRACT_KEY, 2, date(2023, 4, 30), "POB-01", "1"),
        datetime(2023, 4, 30, 17, tzinfo=UTC),
        is_new=False,
    )
    retro = _recorded(
        event_view(
            CONTRACT_KEY,
            3,
            "CONTRACT_AMENDED",
            date(2023, 1, 15),
            {"modification_id": "MOD-TC-RM-13", "template_mode": "retrospective"},
            obligation_keys=["POB-01"],
        ),
        datetime(2023, 5, 10, 9, tzinfo=UTC),
    )
    st = allocated_state([_units_obligation()], events=[delivered, retro], inception=JANUARY_2023)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)

    out = late_events(ctx, st, tb)
    assert _findings(out.findings) == [
        (
            "LATE_EVENT",
            "WARNING",
            f"{CONTRACT_KEY}/POB-01",
            _detail(retro, "FY2023-P01", "FY2023-P05", "CLOSED_PERIOD,OUT_OF_ORDER"),
        )
    ]
    assert out.register == (
        LateEventFact(
            retro.event_key, CONTRACT_KEY, "FY2023-P01", "FY2023-P05", "CONTRACT_AMENDED"
        ),
    )
    carried = _node(_trace(tb), f"late_assign@{retro.event_key}:{CONTRACT_KEY}:-")
    assert (carried.value, carried.params["states"]) == ("4", "closed|closed|closed|closed|open")


def test_s08_inv_03_never_returns_unavailable_period() -> None:
    keys = [f"FY2023-P0{month}" for month in range(1, 5)]
    ctx = book_context(bundles.entity(start=JANUARY_2023, months=4))
    for states in itertools.product((*POSTABLE, *UNAVAILABLE), repeat=len(keys)):
        state_of = dict(zip(keys, states, strict=True))
        calendar = bundles.entity(start=JANUARY_2023, months=len(keys), states=state_of)
        view = dataclasses.replace(ctx, entities={ENTITY: calendar})
        for index, period in enumerate(calendar.periods):
            state = state_of[period.period_key]
            later = next((key for key in keys[index + 1 :] if state_of[key] in POSTABLE), None)
            if state in POSTABLE:
                expected = Assignment(period.period_key, None, None)
            elif state == "future":
                expected = Assignment(None, None, None)
            else:
                expected = Assignment(later, period.period_key, "LATE_EVENT")
            for day in (period.start_date, period.end_date):
                got = assign_posting_period(view, ENTITY, day)
                assert got == expected
                if got.posting_period_key is not None:  # PROP:P11 engine contract
                    assert state_of[got.posting_period_key] in POSTABLE
                if state in UNAVAILABLE:
                    assert got.posting_period_key != period.period_key


def _pins(applied: Mapping[str, tuple[EstimateVersionInput, EventView]]) -> EstimatePins:
    pins: dict[str, list[EstimatePin]] = {}
    for version, ev in applied.values():
        pins.setdefault(version.estimate_key, []).append(EstimatePin(version, ev.order_key))
    return EstimatePins(
        {
            key: tuple(sorted(items, key=lambda pin: pin.event_order_key))
            for key, items in sorted(pins.items())
        }
    )


def test_s08_r13_reassessment_gate_facts() -> None:
    calendar = bundles.entity(start=JANUARY_2023, months=12)
    ctx = book_context(calendar, horizon="FY2023-P03")
    ob = obligation(
        "POB-01", [segment(Fraction(1200), usd("1200.00"), start=JANUARY_2023, end=YEAR_END_2023)]
    )
    bonus = f"{CONTRACT_KEY}/VC-BONUS"
    versions = [
        (  # the January reassessment, effective at the period end
            dataclasses.replace(
                estimate_version(bonus, "VARIABLE_CONSIDERATION", 1, date(2023, 1, 31)),
                allocation_target="CONTRACT",
                constrained_amount=Decimal("100.00"),
            ),
            3,
        ),
        (  # no version effective 28 February; a no-change attestation for March
            dataclasses.replace(
                estimate_version(bonus, "VARIABLE_CONSIDERATION", 2, date(2023, 3, 31)),
                allocation_target="CONTRACT",
                constrained_amount=Decimal("100.00"),
                parameters={"no_change_attestation": True},
            ),
            5,
        ),
        (  # a measure-only kind is not a VC element
            dataclasses.replace(
                estimate_version(f"{CONTRACT_KEY}/EAC", "EAC", 1, date(2023, 1, 31)),
                expected_total_amount=Decimal("800.00"),
            ),
            4,
        ),
        (  # realised increments carry no estimate to reassess (S08-R-04)
            dataclasses.replace(
                estimate_version(
                    f"{CONTRACT_KEY}/VC-USAGE", "VARIABLE_CONSIDERATION", 1, date(2023, 1, 15)
                ),
                allocation_target="INCREMENTS",
            ),
            2,
        ),
    ]
    applied = {
        version.version_key: (
            version,
            event_view(
                CONTRACT_KEY,
                seq,
                "ESTIMATE_CHANGED",
                version.effective_date,
                {"estimate_version_id": version.version_key},
            ),
        )
        for version, seq in versions
    }
    st = allocated_state(
        [ob],
        events=[ev for _, ev in applied.values()],
        estimates=_pins(applied),
        inception=JANUARY_2023,
    )

    out = late_events(ctx, st, TraceBuilder(engine_version=ENGINE_VERSION))
    assert out.close_gate_facts == (
        ReassessmentGap(
            "VC_REASSESSMENT_MISSING", bonus, CONTRACT_KEY, ENTITY, "FY2023-P02", f"{bonus}@v1"
        ),
    )
    assert out.findings == () and out.register == ()
    parity = book_context(calendar, horizon="FY2023-P03", preset="LEGACY_PARITY")
    assert (
        late_events(parity, st, TraceBuilder(engine_version=ENGINE_VERSION)).close_gate_facts == ()
    )
