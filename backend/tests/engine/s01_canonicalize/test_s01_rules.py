"""Stage 01 engine canonicalisation (ENGINE_SPEC §1.5 S01-R-11 to S01-R-20; §1.6; BUILD_SPEC ENA-1).

Bundles come from ``support.bundles`` (DG-ENG-11); no database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import ContractInput, EstimateVersionInput, EventInput, InputBundle
from erev_engine.errors import EngineError
from erev_engine.stages import s01_canonicalize
from erev_engine.stages.state import CanonicalBundle
from erev_engine.trace import SourceRef, TraceBuilder, TraceNode
from support import bundles

CONTRACT = "Contract 1"
INCEPTION = date(2023, 1, 1)
LINE_END = date(2023, 12, 31)
# Contract 1 of the golden contract setup (POB #1 to POB #3).
LINES = (
    ("POB #1", "Hardware 1", "5", "500.00"),
    ("POB #2", "Software 1", "2", "400.00"),
    ("POB #3", "Consulting 1", "1", "400.00"),
)
POB_1 = "Contract 1/POB %231"
POB_2 = "Contract 1/POB %232"


def booking(contract: str = CONTRACT, stream: int = 1, **header: object) -> EventInput:
    lines = [
        bundles.booking_line(
            key,
            product_code=product,
            quantity=qty,
            total_price=price,
            start=INCEPTION,
            end=LINE_END,
        )
        for key, product, qty, price in LINES
    ]
    return bundles.event(
        contract,
        stream,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines, **header},
        obligation_keys=[key for key, *_ in LINES],
    )


def event(
    stream: int,
    event_type: str,
    effective: date,
    payload: Mapping[str, object],
    *,
    contract: str = CONTRACT,
) -> EventInput:
    obligation = payload.get("obligation_key")
    keys = [obligation] if isinstance(obligation, str) else []
    return bundles.event(contract, stream, event_type, effective, payload, obligation_keys=keys)


def delivery(stream: int, effective: date, obligation: str, quantity: str) -> EventInput:
    payload = {"obligation_key": obligation, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return event(stream, "DELIVERY_RECORDED", effective, payload)


def bundle(
    *events: EventInput,
    contracts: Iterable[ContractInput] | None = None,
    estimates: Iterable[EstimateVersionInput] = (),
    known_at: datetime = datetime(2024, 12, 31, 23, tzinfo=UTC),
) -> InputBundle:
    calendar = bundles.entity(start=date(2023, 1, 1), months=24)
    headers = tuple(contracts or (bundles.contract(CONTRACT, inception=INCEPTION),))
    products = [bundles.product(product) for _, product, *_ in LINES]
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=known_at,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(bundles.book(entity=calendar),),
        entities=(calendar,),
        group=dataclasses.replace(
            bundles.group(headers, products=products), transaction_currency="USD"
        ),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=tuple(estimates),
        fx_rates=(),
        posted=(),
    )


def run(value: InputBundle) -> tuple[CanonicalBundle, dict[str, TraceNode]]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(value, tb)
    return cb, {node.id: node for node in tb.build(root_measures={}).nodes}


def estimate(version_no: int, effective: date, status: str = "APPROVED") -> EstimateVersionInput:
    key = f"{CONTRACT}/VC-1"
    return EstimateVersionInput(
        estimate_key=key,
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code="VC-1",
        method="MOST_LIKELY_AMOUNT",
        vc_element_type=None,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=None,
        version_key=f"{key}@v{version_no}",
        version_no=version_no,
        status=status,
        effective_date=effective,
        scenarios=(),
        parameters={},
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=Decimal("100.00"),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=bundles.ZERO_SHA256,
    )


def estimate_changed(stream: int, effective: date, version_key: str) -> EventInput:
    payload = {"estimate_version_id": version_key}
    return dataclasses.replace(
        event(stream, "ESTIMATE_CHANGED", effective, payload), estimate_version_key=version_key
    )


def voided(stream: int, effective: date, target: str, *, contract: str = CONTRACT) -> EventInput:
    payload = {"reason_code": "DATA_CORRECTION", "comment": "entered twice"}
    raw = event(stream, "EVENT_VOIDED", effective, payload, contract=contract)
    return dataclasses.replace(raw, supersedes_event_key=target)


def test_s01_r11_decimal_conversion() -> None:
    billing = event(
        2,
        "BILLING_RECORDED",
        date(2023, 1, 31),
        {
            "invoice_number": "INV-1",
            "line_external_id": "INV-1:1",
            "obligation_key": "POB #1",
            "amount": Decimal("300.00"),
            "issue_date": date(2023, 1, 31),
        },
    )
    cb, _ = run(bundle(booking(), billing))
    amount = cb.events[1].payload["amount"]
    assert isinstance(amount, Fraction) and amount == Fraction(300)
    lines = cb.contracts[CONTRACT].booking["lines"]
    assert isinstance(lines, tuple) and isinstance(lines[0], Mapping)
    assert lines[0]["total_price"] == Fraction(500) and isinstance(lines[0]["quantity"], Fraction)
    with pytest.raises(TypeError):
        cb.events[1].payload["amount"] = Fraction(1)  # type: ignore[index]

    exponent = dataclasses.replace(estimate(1, INCEPTION), constrained_amount=Decimal("1E+2"))
    with pytest.raises(ValueError, match="exponent form"):
        run(bundle(booking(), estimates=[exponent]))
    base = bundle(booking())
    product = dataclasses.replace(base.group.products[0], assurance_cost_per_unit=Decimal("NaN"))
    products = (product, *base.group.products[1:])
    infinite = dataclasses.replace(base, group=dataclasses.replace(base.group, products=products))
    with pytest.raises(ValueError, match="non-finite"):
        run(infinite)
    unknown = dataclasses.replace(booking(), event_type="CONTRACT_SIGNED")
    with pytest.raises(ValueError, match="unknown literal"):
        run(bundle(unknown))


def test_s01_r12_void_removes_target_and_void() -> None:
    events = (
        booking(),
        event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        delivery(3, date(2023, 1, 15), "POB #1", "1"),
        delivery(4, date(2023, 1, 20), "POB #1", "1"),
        voided(5, date(2023, 1, 25), "Contract 1/EV-000004"),
    )
    cb, _ = run(bundle(*events))
    keys = [view.event_key for view in cb.events]
    assert keys == ["Contract 1/EV-000001", "Contract 1/EV-000002", "Contract 1/EV-000003"]
    orders = [view.order_key for view in cb.events]
    assert all(previous < current for previous, current in zip(orders, orders[1:], strict=False))
    assert "EVENT_VOIDED" not in {view.event_type for view in cb.events}
    assert cb.ledger.at(POB_1).delivered_cum == 1

    for bad, message in (
        (voided(6, date(2023, 1, 26), "Contract 1/EV-000005"), "void of a void"),
        (voided(6, date(2023, 1, 26), "Contract 1/EV-000099"), "absent"),
        (voided(6, date(2023, 1, 26), "Contract 1/EV-000004"), "voided twice"),
    ):
        with pytest.raises(ValueError, match=message):
            run(bundle(*events, bad))
    other = bundles.contract("Contract 2", inception=INCEPTION)
    headers = (bundles.contract(CONTRACT, inception=INCEPTION), other)
    cross = voided(2, date(2023, 1, 26), "Contract 1/EV-000003", contract="Contract 2")
    with pytest.raises(ValueError, match="another contract"):
        run(bundle(*events[:3], booking("Contract 2"), cross, contracts=headers))


def test_s01_r13_contract_void() -> None:
    headers = (
        bundles.contract(CONTRACT, inception=INCEPTION),
        bundles.contract("Contract 2", inception=INCEPTION),
    )
    events = (
        booking(),
        booking("Contract 2"),
        event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        delivery(3, date(2023, 1, 15), "POB #1", "2"),
        bundles.event(
            "Contract 2",
            2,
            "DELIVERY_RECORDED",
            date(2023, 1, 16),
            {"obligation_key": "POB #2", "quantity": Decimal("1"), "trigger": "DELIVERY"},
            obligation_keys=["POB #2"],
        ),
        event(4, "CONTRACT_VOIDED", date(2023, 2, 1), {"reason_code": "DUPLICATE", "comment": "x"}),
    )
    cb, nodes = run(bundle(*events, contracts=headers))
    assert [(v.contract_key, v.event_type) for v in cb.events if v.contract_key == CONTRACT] == [
        (CONTRACT, "CONTRACT_VOIDED")
    ]
    assert cb.contracts[CONTRACT].booking == {}
    assert CONTRACT not in cb.ledger.steps and POB_1 not in cb.ledger.steps
    assert not any(node_id.endswith(f"{POB_1}:-") for node_id in nodes)
    assert cb.ledger.at("Contract 2/POB %232").delivered_cum == 1
    assert {v.event_type for v in cb.events if v.contract_key == "Contract 2"} == {
        "CONTRACT_BOOKED",
        "DELIVERY_RECORDED",
    }


def test_s01_r14_classification() -> None:
    events = (
        booking(),
        event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        event(
            3,
            "CONTRACT_AMENDED",
            date(2023, 2, 1),
            {"modification_id": "MOD-1", "treatments": {}, "lines": [], "ssp_basis": {}},
        ),
        event(
            4,
            "OPENING_BALANCE_ESTABLISHED",
            date(2023, 2, 2),
            {"reason": "SYSTEM_ONBOARDING", "cutover_date": date(2023, 2, 2), "obligations": []},
        ),
        estimate_changed(5, date(2023, 2, 3), f"{CONTRACT}/VC-1@v1"),
        delivery(6, date(2023, 2, 4), "POB #1", "1"),
        event(
            7,
            "BILLING_RECORDED",
            date(2023, 2, 5),
            {"invoice_number": "INV-7", "line_external_id": "1", "amount": Decimal("10.00")},
        ),
        event(8, "HOLD_APPLIED", date(2023, 2, 6), {"hold_type": "RECOGNITION", "reason": "x"}),
    )
    cb, _ = run(bundle(*events, estimates=[estimate(1, date(2023, 2, 3))]))
    boundary = {view.event_type for view in cb.boundary_events}
    measure = {view.event_type for view in cb.measure_events}
    assert boundary == {"CONTRACT_AMENDED", "OPENING_BALANCE_ESTABLISHED", "ESTIMATE_CHANGED"}
    assert {"DELIVERY_RECORDED", "BILLING_RECORDED", "HOLD_APPLIED"} <= measure
    assert "CONTRACT_BOOKED" not in boundary | measure
    first_booking = [view for view in cb.events if view.event_type == "CONTRACT_BOOKED"]
    parts = [*cb.boundary_events, *cb.measure_events, *first_booking]
    assert sorted(v.event_key for v in parts) == sorted(v.event_key for v in cb.events)
    assert len({v.event_key for v in parts}) == len(parts) == len(cb.events)

    second = dataclasses.replace(booking(stream=9), effective_date=date(2023, 3, 1), record_seq=9)
    with pytest.raises(ValueError, match="one booking"):
        run(bundle(*events, second, estimates=[estimate(1, date(2023, 2, 3))]))


def test_s01_r15_event_before_inception() -> None:
    early = delivery(2, date(2022, 12, 31), "POB #1", "1")
    cb, _ = run(bundle(booking(), early))
    assert [(f.code, f.severity, f.event_key) for f in cb.findings] == [
        ("EVENT_BEFORE_INCEPTION", "ERROR", "Contract 1/EV-000002")
    ]
    assert cb.findings[0].subject_key == CONTRACT and cb.findings[0].stage == 1


def test_s01_r16_returns_and_credits_exceeding() -> None:
    events = (
        booking(),
        delivery(2, date(2023, 1, 10), "POB #1", "2"),
        event(
            3,
            "RETURN_RECORDED",
            date(2023, 1, 11),
            {"obligation_key": "POB #1", "quantity": Decimal("3")},
        ),
        event(
            4,
            "BILLING_RECORDED",
            date(2023, 1, 12),
            {
                "invoice_number": "INV-4",
                "line_external_id": "1",
                "obligation_key": "POB #2",
                "amount": Decimal("100.00"),
            },
        ),
        event(
            5,
            "CREDIT_MEMO_RECORDED",
            date(2023, 1, 13),
            {"credit_memo_number": "CM-5", "obligation_key": "POB #2", "amount": Decimal("150.00")},
        ),
    )
    cb, _ = run(bundle(*events))
    assert [(f.code, f.subject_key, f.event_key) for f in cb.findings] == [
        ("REFUND_EXCEEDS_BILLED", POB_2, "Contract 1/EV-000005"),
        ("RETURN_EXCEEDS_DELIVERED", POB_1, "Contract 1/EV-000003"),
    ]
    assert cb.findings == tuple(sorted(cb.findings, key=lambda f: f.sort_key()))
    assert cb.findings[0].detail == {
        "billed": "100",
        "credited": "150",
        "event_key": "Contract 1/EV-000005",
    }


def test_s01_r17_over_delivery() -> None:
    events = (
        booking(),
        delivery(2, date(2023, 1, 10), "POB #1", "3"),
        delivery(3, date(2023, 1, 20), "POB #1", "3"),
    )
    cb, _ = run(bundle(*events))
    assert [(f.code, f.severity, f.subject_key) for f in cb.findings] == [
        ("PROGRESS_OVER_DELIVERY", "ERROR", POB_1)
    ]
    assert cb.findings[0].detail["booked"] == "5" and cb.findings[0].detail["delivered"] == "6"
    amended = event(
        4,
        "CONTRACT_AMENDED",
        date(2023, 1, 15),
        {
            "modification_id": "MOD-1",
            "treatments": {"POB #1": "PROSPECTIVE"},
            "lines": [{"obligation_key": "POB #1", "quantity_delta": Decimal("2")}],
            "ssp_basis": {},
        },
    )
    changed, _ = run(bundle(*events, amended))
    assert changed.findings == ()


def test_s01_r18_estimate_pins() -> None:
    versions = [estimate(1, date(2023, 1, 1)), estimate(2, date(2023, 3, 1))]
    events = (
        booking(),
        estimate_changed(2, date(2023, 1, 1), f"{CONTRACT}/VC-1@v1"),
        estimate_changed(3, date(2023, 3, 1), f"{CONTRACT}/VC-1@v2"),
        estimate_changed(4, date(2023, 4, 1), f"{CONTRACT}/VC-1@v9"),
    )
    cb, _ = run(bundle(*events, estimates=versions))
    assert [(f.code, f.detail["estimate_version_key"]) for f in cb.findings] == [
        ("ESTIMATE_VERSION_NOT_APPROVED", f"{CONTRACT}/VC-1@v9")
    ]
    key = f"{CONTRACT}/VC-1"
    second = next(view for view in cb.events if view.event_key == "Contract 1/EV-000003")
    assert cb.estimates.pin(key, date(2022, 12, 31)) is None
    first = cb.estimates.pin(key, date(2023, 2, 15))
    assert first is not None and first.version_no == 1
    latest = cb.estimates.pin(key, date(2023, 3, 15))
    assert latest is not None and latest.version_no == 2
    before = cb.estimates.pin(key, date(2023, 3, 15), before=second)
    assert before is not None and before.version_no == 1
    assert cb.estimates.pin(key, date(2023, 3, 15)) == latest  # S01-INV-04

    draft = [versions[0], estimate(2, date(2023, 3, 1), status="REJECTED")]
    rejected, _ = run(bundle(*events[:3], estimates=draft))
    assert [f.event_key for f in rejected.findings] == ["Contract 1/EV-000003"]
    pinned = rejected.estimates.pin(key, date(2023, 3, 15))
    assert pinned is not None and pinned.version_no == 1


def test_s01_r18_a_version_in_force_at_inception_applies_before_every_position() -> None:
    """S01-R-18, S04-R-01 (item ENG-INCEPTION-ESTIMATE-1). An ``ESTIMATE_CHANGED`` effective on or
    before the group inception applies a version in force at inception: its pin is marked and
    ``pin`` admits it before every position — a boundary event of the inception date recorded
    before the estimate change does not keep the version out of the inception price. A later
    version applies at its own event, as before. ``replaced_by`` reads what each event replaced
    with every version counted from its own event, so the first version of an element replaces
    none and the second version of the inception date replaces the first."""
    key = f"{CONTRACT}/VC-1"
    later = date(2023, 3, 1)
    versions = [estimate(1, INCEPTION), estimate(2, INCEPTION), estimate(3, later)]
    events = (
        booking(),
        event(2, "SIGNIFICANT_CHANGE_FLAGGED", INCEPTION, {"description": "A flag at inception."}),
        estimate_changed(3, INCEPTION, f"{key}@v1"),
        estimate_changed(4, INCEPTION, f"{key}@v2"),
        estimate_changed(5, later, f"{key}@v3"),
    )
    cb, _ = run(bundle(*events, estimates=versions))
    assert cb.findings == ()
    assert [(pin.version.version_no, pin.at_inception) for pin in cb.estimates.pins[key]] == [
        (1, True),
        (2, True),
        (3, False),
    ]
    views = {view.event_key: view for view in cb.events}
    flag, first, second, third = (views[f"{CONTRACT}/EV-00000{n}"] for n in (2, 3, 4, 5))

    def number(found: EstimateVersionInput | None) -> int | None:
        return None if found is None else found.version_no

    # before the flag, before either estimate change and at the end of the inception date
    assert number(cb.estimates.pin(key, INCEPTION, before=flag)) == 2
    assert number(cb.estimates.pin(key, INCEPTION, before=first)) == 2
    assert number(cb.estimates.pin(key, INCEPTION, before=second)) == 2
    assert number(cb.estimates.pin(key, INCEPTION)) == 2
    # a version effective after the inception applies at its own event
    assert number(cb.estimates.pin(key, later, before=third)) == 2
    assert number(cb.estimates.pin(key, later)) == 3
    # nothing is in force before the inception date
    assert cb.estimates.pin(key, date(2022, 12, 31), before=flag) is None
    # what each event replaced
    assert cb.estimates.replaced_by(key, first) is None
    assert number(cb.estimates.replaced_by(key, second)) == 1
    assert number(cb.estimates.replaced_by(key, third)) == 2


def test_s01_r19_ledger_trace_nodes() -> None:
    events = (
        booking(),
        delivery(2, date(2023, 1, 10), "POB #1", "1"),
        delivery(3, date(2023, 1, 20), "POB #1", "1"),
    )
    _, nodes = run(bundle(*events))
    node = nodes["delivered_quantity_cum:Contract 1/POB %231:-"]
    assert node.value == "2"
    assert node.formula_id == "ingest.ledger_sum.v1" and node.narrative_key == "ingest.ledger_sum"
    assert node.rounding_residue is None and node.currency is None
    assert all(isinstance(item, SourceRef) for item in node.inputs)
    refs = [item for item in node.inputs if isinstance(item, SourceRef)]
    assert [(ref.ref_type, ref.ref_id, ref.detail["value"]) for ref in refs] == [
        ("contract_event", "Contract 1/EV-000002", "1"),
        ("contract_event", "Contract 1/EV-000003", "1"),
    ]
    returned = nodes["returned_quantity_cum:Contract 1/POB %231:-"]
    assert returned.value == "0" and returned.inputs == ()
    # Every booked obligation carries both measures, delivered or not (S01-R-19).
    assert nodes["delivered_quantity_cum:Contract 1/POB %233:-"].value == "0"

    with_return = (
        *events,
        event(
            4,
            "RETURN_RECORDED",
            date(2023, 1, 25),
            {"obligation_key": "POB #1", "quantity": Decimal("1")},
        ),
    )
    _, netted = run(bundle(*with_return))
    assert netted["delivered_quantity_cum:Contract 1/POB %231:-"].value == "1"
    values = [
        ref.detail["value"]
        for ref in netted["delivered_quantity_cum:Contract 1/POB %231:-"].inputs
        if isinstance(ref, SourceRef)
    ]
    assert values == ["1", "1", "-1"]
    assert netted["returned_quantity_cum:Contract 1/POB %231:-"].value == "1"


def test_s01_r20_booking_payload_is_authoritative() -> None:
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION, currency="EUR"),
        scope_605_35=True,
        termination_party="NONE",
    )
    booked = booking(
        transaction_currency="USD",
        scope_605_35=False,
        termination={"party": "CUSTOMER", "has_penalty": False, "notice_days": 30},
        payment_schedule=[{"date": date(2023, 2, 1), "amount": Decimal("100.00")}],
    )
    amended = event(
        2,
        "CONTRACT_AMENDED",
        date(2023, 6, 1),
        {
            "modification_id": "MOD-1",
            "treatments": {},
            "lines": [],
            "ssp_basis": {},
            "scope_605_35": True,
        },
    )
    cb, _ = run(bundle(booked, amended, contracts=[header]))
    canonical = cb.contracts[CONTRACT].header
    assert canonical.transaction_currency == "USD"
    assert (canonical.termination_party, canonical.termination_notice_days) == ("CUSTOMER", 30)
    assert canonical.termination_has_penalty is False and canonical.scope_605_35 is False
    assert s01_canonicalize.scope_605_35_at(cb, CONTRACT, date(2023, 5, 31)) is False
    assert s01_canonicalize.scope_605_35_at(cb, CONTRACT, date(2023, 6, 1)) is True
    schedule = s01_canonicalize.member_in_force(cb.events, CONTRACT, "payment_schedule", LINE_END)
    assert isinstance(schedule, tuple) and schedule[0]["amount"] == Fraction(100)
    # Without a payload member the header projection serves (S01-R-20).
    plain, _ = run(bundle(booking(), contracts=[header]))
    assert plain.contracts[CONTRACT].header.transaction_currency == "EUR"
    assert s01_canonicalize.scope_605_35_at(plain, CONTRACT, LINE_END) is True


def test_s01_subject_keys_encode_cv_21() -> None:
    assert s01_canonicalize.encode_key("K/01@X#1:%") == "K%2F01%40X%231%3A%25"
    assert s01_canonicalize.obligation_subject_key("Contract 1", "POB #1") == POB_1
    assert s01_canonicalize.contract_entity_subject_key("A@B", "US01") == "A%40B@US01"
    with pytest.raises(ValueError):
        s01_canonicalize.encode_key("")


def test_s01_ledger_measures_and_stream_heads() -> None:
    events = (
        booking(),
        event(
            2,
            "COST_INCURRED",
            date(2023, 1, 5),
            {"purpose": "PROGRESS_INPUT", "obligation_key": "POB #3", "amount": Decimal("40")},
        ),
        event(
            3,
            "COST_INCURRED",
            date(2023, 1, 6),
            {"purpose": "COST_TO_OBTAIN", "amount": Decimal("99")},
        ),
        event(
            4,
            "PROGRESS_RECORDED",
            date(2023, 1, 7),
            {
                "obligation_key": "POB #3",
                "cumulative_progress_ratio": Decimal("0.25"),
                "measure": "LABOUR_HOURS",
                "hours_to_date": Decimal("12"),
            },
        ),
        event(
            5,
            "MILESTONE_ACHIEVED",
            date(2023, 1, 8),
            {
                "obligation_key": "POB #2",
                "milestone_code": "M1",
                "cumulative_weight": Decimal("0.5"),
            },
        ),
        event(
            6,
            "USAGE_REPORTED",
            date(2023, 1, 9),
            {
                "obligation_key": "POB #2",
                "usage_period_start": date(2023, 1, 1),
                "usage_period_end": date(2023, 1, 31),
                "metric": "API",
                "quantity": Decimal("7"),
            },
        ),
        event(
            7,
            "BILLING_RECORDED",
            date(2023, 1, 10),
            {"invoice_number": "INV-7", "line_external_id": "1", "amount": Decimal("80.00")},
        ),
        event(
            8,
            "PAYMENT_RECEIVED",
            date(2023, 1, 11),
            {
                "receipt_reference": "R-8",
                "amount": Decimal("80.00"),
                "receipt_date": date(2023, 1, 11),
            },
        ),
    )
    value = bundle(*events)
    heads = dataclasses.replace(value.group, previous_stream_heads=((CONTRACT, 4),))
    cb, _ = run(dataclasses.replace(value, group=heads))
    pob_3 = cb.ledger.at("Contract 1/POB %233")
    assert (pob_3.costs_cum, pob_3.output_ratio, pob_3.hours_cum) == (40, Fraction(1, 4), 12)
    pob_2 = cb.ledger.at(POB_2)
    assert (pob_2.milestone_weight_cum, pob_2.usage_quantity_cum) == (Fraction(1, 2), 7)
    contract = cb.ledger.at(CONTRACT)
    assert (contract.billed_cum, contract.paid_cum, contract.costs_cum) == (80, 80, 0)
    assert contract.last_event_key == "Contract 1/EV-000008"
    before = cb.ledger.at(CONTRACT, before=cb.events[-1])
    assert before.paid_cum == 0 and before.billed_cum == 80
    assert [view.is_new for view in cb.events] == [False] * 4 + [True] * 4


def test_s01_bundle_programming_errors() -> None:
    events = (booking(), delivery(2, date(2023, 1, 10), "POB #1", "1"))
    value = bundle(*events)
    with pytest.raises(ValueError, match="not sorted"):
        run(dataclasses.replace(value, events=tuple(reversed(value.events))))
    with pytest.raises(ValueError, match="after known_at"):
        run(dataclasses.replace(value, known_at=datetime(2023, 1, 5, tzinfo=UTC)))
    stranger = dataclasses.replace(events[1], contract_key="Contract 9")
    with pytest.raises(ValueError, match="non-member"):
        run(dataclasses.replace(value, events=(events[0], stranger)))
    with pytest.raises(ValueError, match="names no obligation"):
        run(bundle(booking(), event(2, "DELIVERY_RECORDED", INCEPTION, {"quantity": Decimal("1")})))


def test_s01_inv_03_fails_closed() -> None:
    negative = delivery(2, date(2023, 1, 10), "POB #1", "-1")
    with pytest.raises(EngineError) as raised:
        run(bundle(booking(), negative))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail == {"invariant": "S01-INV-03", "subject_key": POB_1}


def test_enc_vc_direction_versions_of_one_element_agree() -> None:
    """04 B3-D16: the sign belongs to the element. Versions of one element that resolve to
    different directions (an explicit INCREASE beside the type's DECREASE default, or two explicit
    values) are malformed input and fail closed in the pin index (CV-45); agreeing explicit and
    derived values pass."""
    events = (
        booking(),
        estimate_changed(2, date(2023, 1, 1), f"{CONTRACT}/VC-1@v1"),
        estimate_changed(3, date(2023, 3, 1), f"{CONTRACT}/VC-1@v2"),
    )
    first = dataclasses.replace(estimate(1, date(2023, 1, 1)), vc_element_type="VOLUME_TIER")
    second = dataclasses.replace(estimate(2, date(2023, 3, 1)), vc_element_type="VOLUME_TIER")
    cb, _ = run(bundle(*events, estimates=[first, second]))
    assert cb.findings == ()
    explicit_both = [
        dataclasses.replace(first, direction="INCREASE"),
        dataclasses.replace(second, direction="INCREASE"),
    ]
    cb, _ = run(bundle(*events, estimates=explicit_both))
    pinned = cb.estimates.pin(f"{CONTRACT}/VC-1", date(2023, 3, 15))
    assert pinned is not None and pinned.resolved_direction() == "INCREASE"
    agreeing = [dataclasses.replace(first, direction="DECREASE"), second]  # explicit = default
    cb, _ = run(bundle(*events, estimates=agreeing))
    assert cb.findings == ()
    for mixed in (
        [dataclasses.replace(first, direction="INCREASE"), second],
        [
            dataclasses.replace(first, direction="INCREASE"),
            dataclasses.replace(second, direction="DECREASE"),
        ],
    ):
        with pytest.raises(ValueError, match="disagree on direction"):
            run(bundle(*events, estimates=mixed))


def test_s01_r15a_billing_identity_missing() -> None:
    """D-97 (28), S01-R-15a: a ``BILLING_RECORDED`` lacking ``line_external_id`` raises
    ``BILLING_IDENTITY_MISSING`` (ERROR, stage 1, detail ``missing``); one lacking both members
    names both; a complete identity raises nothing. Before D-97 (28) a bare identity passed stage
    01 silently and could never be matched to a status update. Detail carries ``rule`` =
    ``S01-R-15a`` as 04 table 15.4-B requires (Codex C6-D97-R1; the de399a0 engine omitted it)."""
    bare_line = event(
        2,
        "BILLING_RECORDED",
        date(2023, 1, 12),
        {"invoice_number": "INV-4", "obligation_key": "POB #1", "amount": Decimal("100.00")},
    )
    bare_both = event(
        3,
        "BILLING_RECORDED",
        date(2023, 1, 13),
        {"obligation_key": "POB #1", "amount": Decimal("100.00")},
    )
    complete = event(
        4,
        "BILLING_RECORDED",
        date(2023, 1, 14),
        {
            "invoice_number": "INV-5",
            "line_external_id": "1",
            "obligation_key": "POB #1",
            "amount": Decimal("100.00"),
        },
    )
    cb, _ = run(bundle(booking(), bare_line, bare_both, complete))
    assert [(f.code, f.severity, f.stage, f.event_key, dict(f.detail)) for f in cb.findings] == [
        (
            "BILLING_IDENTITY_MISSING",
            "ERROR",
            1,
            "Contract 1/EV-000002",
            {
                "event_key": "Contract 1/EV-000002",
                "missing": "line_external_id",
                "rule": "S01-R-15a",
            },
        ),
        (
            "BILLING_IDENTITY_MISSING",
            "ERROR",
            1,
            "Contract 1/EV-000003",
            {
                "event_key": "Contract 1/EV-000003",
                "missing": "invoice_number|line_external_id",
                "rule": "S01-R-15a",
            },
        ),
    ]
    assert all(f.subject_key == CONTRACT for f in cb.findings)
    clean, _ = run(bundle(booking(), complete))
    assert clean.findings == ()
