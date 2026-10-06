"""Golden delivery revenue under the units measure (ENC-4; legacy 02 §7.3 TC-delivery-01 to 08, 20).

Contracts 1 to 4 of the legacy UAT (legacy 02 §5.3, §5.7; legacy 07 §4.4) are built as
``AllocatedState`` against the documented contract (D-81 integration after merge): X = contract
price × extended SSP ÷ total SSP, posted allocations by largest remainder (ALG-01 §2.1.2), measure
``UNITS_DELIVERED`` (POL-091 parity value; DEV-082) under the ``LEGACY_PARITY`` preset. Each upload
row becomes ``DELIVERY_RECORDED`` or ``RETURN_RECORDED`` and ``BILLING_RECORDED`` or
``CREDIT_MEMO_RECORDED`` on the upload date (04 LM-TPL-PROG-01 to 09). Revenue exact values are
compared at the six places of the legacy figures; posted values follow ALG-01 §2.1.3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.money import format_exact, largest_remainder
from erev_engine.stages.s09_recognition import (
    RecognitionState,
    components,
    progress_events,
    run,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    EventView,
    ObligationState,
    SegmentCause,
    Target,
)
from erev_engine.trace import TraceBuilder, reevaluate
from support.bundles import entity
from support.recognition import (
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    usd,
)

CTX = book_context(entity(start=date(2023, 1, 1), months=12), preset="LEGACY_PARITY")
STEP_04, STEP_05, STEP_06, STEP_07 = (
    date(2023, 1, 31),
    date(2023, 2, 28),
    date(2023, 3, 31),
    date(2023, 4, 30),
)
STEP_14 = date(2023, 10, 31)
TERM_END = date(2023, 12, 31)
SETUP = {
    "Contract 1": date(2023, 1, 1),
    "Contract 2": date(2023, 1, 1),
    "Contract 3": date(2023, 2, 1),
    "Contract 4": date(2023, 2, 1),
}
# (contract price, ((POB, quantity, extended SSP), ...)): legacy 02 §5.3, §5.7; legacy 07 §4.4.
CONTRACTS: Mapping[str, tuple[int, tuple[tuple[str, str, int], ...]]] = {
    "Contract 1": (
        1300,
        (
            ("POB #1", "5", 500),
            ("POB #2", "2", 368),
            ("POB #3", "1", 150),
            ("POB #4", "1000", 1000),
        ),
    ),
    "Contract 2": (
        900,
        (("POB #1", "8", 612), ("POB #2", "3", 408), ("POB #3", "1", 150), ("VC #1", "1", 0)),
    ),
    "Contract 3": (
        1300,
        (
            ("POB #1", "5", 500),
            ("POB #2", "2", 368),
            ("POB #3", "1", 150),
            ("POB #4", "1000", 1000),
        ),
    ),
    "Contract 4": (
        950,
        (("POB #1", "8", 612), ("POB #2", "4", 544), ("POB #3", "1", 150), ("VC #1", "1", 0)),
    ),
}


@dataclass(frozen=True, slots=True)
class Row:
    """One aggregated upload row: ``Current Delivery`` and ``Current Billing`` of a POB."""

    upload: date
    obligation_key: str
    delivery: str = "0"
    billing: str = "0"


# Golden steps 04 to 07 (docs/legacy/golden/0N-*/contract_live.csv, the rows with activity).
UPLOADS: Mapping[str, tuple[Row, ...]] = {
    "Contract 1": (
        Row(STEP_04, "POB #1", "2", "100"),  # two identical rows summed (REQ-REC-025)
        Row(STEP_04, "POB #2", "1", "100"),
        Row(STEP_04, "POB #3", "0.5", "100"),
        Row(STEP_05, "POB #1", "1", "100"),
        Row(STEP_07, "POB #1", "-3", "-200"),
        Row(STEP_07, "POB #2", "0", "300"),
    ),
    "Contract 2": (
        Row(STEP_04, "POB #1", "1", "0"),
        Row(STEP_06, "POB #3", "0.4", "0"),
        Row(STEP_07, "POB #1", "0", "20"),
    ),
    "Contract 3": (
        Row(STEP_05, "POB #3", "0.5", "200"),
        Row(STEP_06, "POB #2", "1", "200"),
    ),
    "Contract 4": (
        Row(STEP_05, "POB #1", "2", "150"),
        Row(STEP_06, "POB #2", "1", "200"),
        Row(STEP_06, "VC #1", "0.5", "-100"),
    ),
}


def _events(contract_key: str, rows: Sequence[Row]) -> list[EventView]:
    events: list[EventView] = []
    version = 1  # stream version 1 is CONTRACT_BOOKED
    for row in rows:
        key = row.obligation_key
        delivery, billing = Decimal(row.delivery), Decimal(row.billing)
        payloads: list[tuple[str, dict[str, object]]] = []
        if delivery > 0:
            payloads.append(
                (
                    "DELIVERY_RECORDED",
                    {"obligation_key": key, "quantity": delivery, "trigger": "DELIVERY"},
                )
            )
        elif delivery < 0:
            payloads.append(("RETURN_RECORDED", {"obligation_key": key, "quantity": -delivery}))
        if billing > 0:
            invoice = {
                "invoice_number": f"INV-{row.upload.isoformat()}",
                "line_external_id": key,
                "obligation_key": key,
                "amount": billing,
                "issue_date": row.upload,
            }
            payloads.append(("BILLING_RECORDED", invoice))
        elif billing < 0:
            memo = {
                "credit_memo_number": f"CM-{row.upload.isoformat()}",
                "obligation_key": key,
                "amount": -billing,
                "issue_date": row.upload,
            }
            payloads.append(("CREDIT_MEMO_RECORDED", memo))
        for event_type, payload in payloads:
            version += 1
            events.append(
                event_view(
                    contract_key, version, event_type, row.upload, payload, obligation_keys=[key]
                )
            )
    return events


def _inception(contract_key: str) -> list[ObligationState]:
    price, lines = CONTRACTS[contract_key]
    total = sum(ssp for _, _, ssp in lines)
    posted = largest_remainder(
        price * 100, [Fraction(ssp) for _, _, ssp in lines], [key for key, _, _ in lines]
    )
    obligations = []
    for (key, quantity, ssp), a_posted in zip(lines, posted, strict=True):
        seg = segment(
            Fraction(price * ssp, total),
            a_posted,
            start=SETUP[contract_key],
            end=TERM_END,
            quantity=Fraction(quantity),
            measure="UNITS_DELIVERED",
        )
        obligations.append(_units_obligation(contract_key, key, [seg], Fraction(quantity)))
    return obligations


def _units_obligation(
    contract_key: str, key: str, segments: Sequence[AllocationSegment], quantity: Fraction
) -> ObligationState:
    return obligation(
        key,
        segments,
        contract_key=contract_key,
        method="UNITS_DELIVERED",
        convention=None,
        start=SETUP.get(contract_key),
        quantity=quantity,
    )


def _run(
    contract_key: str,
    through: date,
    *,
    rows: Sequence[Row] | None = None,
    obligations: Sequence[ObligationState] | None = None,
) -> tuple[AllocatedState, RecognitionState]:
    """Stage 09 over one contract (its own group) with the uploads through ``through``."""
    uploads = UPLOADS[contract_key] if rows is None else rows
    obligations = _inception(contract_key) if obligations is None else obligations
    # Each boundary event of a segment is in the state (CV-60); stages 06 to 08 are faked here.
    boundaries = {
        seg.event_key: seg.effective_date
        for ob in obligations
        for seg in ob.segments
        if seg.event_key is not None
    }
    amended = [
        event_view(
            contract_key,
            int(key.rsplit("-", 1)[1]),
            "CONTRACT_AMENDED",
            when,
            {"modification_id": f"MOD-{when.isoformat()}"},
        )
        for key, when in sorted(boundaries.items())
    ]
    st = allocated_state(
        obligations,
        events=[
            *_events(contract_key, [row for row in uploads if row.upload <= through]),
            *amended,
        ],
        inception=SETUP[contract_key],
        statuses=((SETUP[contract_key], "ACTIVE"),),
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, CTX, st)  # the stage 06 nodes stage 09 cites
    state = run(CTX, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return st, state


def _target(state: RecognitionState, subject_key: str, period_key: str) -> Target:
    return next(
        target
        for target in state.revenue_targets
        if target.subject_key == subject_key and target.period_key == period_key
    )


def _exact(state: RecognitionState, subject_key: str, period_key: str) -> Fraction:
    exact = _target(state, subject_key, period_key).exact
    assert exact is not None
    return exact


def _six(value: Fraction) -> Decimal:
    """A revenue exact value at the six places of the legacy figures (legacy 02 §3.13)."""
    return Decimal(format_exact(value, 6))


def _revenue(state: RecognitionState, subject_key: str, period: str, previous: str) -> Decimal:
    return _six(_exact(state, subject_key, period) - _exact(state, subject_key, previous))


def _remaining(st: AllocatedState, subject_key: str, d: date) -> Fraction:
    ob = next(item for item in st.obligations if item.subject_key == subject_key)
    seg = components.active_segment(ob, "FIXED", d)
    assert seg is not None
    return progress_events.remaining_quantity(CTX, st, st.contracts[0], ob, seg, d)


def test_tc_delivery_01_contract1_step04() -> None:
    _, state = _run("Contract 1", STEP_04)
    for key, exact, posted in (
        ("POB #1", "128.840436", "128.84"),
        ("POB #2", "118.533201", "118.53"),
        ("POB #3", "48.315164", "48.32"),
    ):
        target = _target(state, f"Contract 1/{key}", "FY2023-P01")
        assert target.exact is not None and _six(target.exact) == Decimal(exact)
        assert target.value == usd(posted)
    assert _target(state, "Contract 1/POB #4", "FY2023-P01").value == 0
    assert state.findings == ()


def test_tc_delivery_02_contract2_delivery_without_billing() -> None:
    _, state = _run("Contract 2", STEP_04)
    assert _six(_exact(state, "Contract 2/POB #1", "FY2023-P01")) == Decimal("58.846154")
    assert _target(state, "Contract 2/POB #1", "FY2023-P01").value == usd("58.85")


def test_tc_delivery_03_step05() -> None:
    _, contract_1 = _run("Contract 1", STEP_05)
    assert _revenue(contract_1, "Contract 1/POB #1", "FY2023-P02", "FY2023-P01") == Decimal(
        "64.420218"
    )
    _, contract_3 = _run("Contract 3", STEP_05)
    assert _six(_exact(contract_3, "Contract 3/POB #3", "FY2023-P02")) == Decimal("48.315164")
    _, contract_4 = _run("Contract 4", STEP_05)
    assert _six(_exact(contract_4, "Contract 4/POB #1", "FY2023-P02")) == Decimal("111.294028")


def test_tc_delivery_04_contract2_fractional() -> None:
    st, state = _run("Contract 2", STEP_06)
    assert _revenue(state, "Contract 2/POB #3", "FY2023-P03", "FY2023-P02") == Decimal("46.153846")
    assert _remaining(st, "Contract 2/POB #3", STEP_06) == Fraction(3, 5)


def test_tc_delivery_05_contract4_vc_line() -> None:
    _, state = _run("Contract 4", STEP_06)
    vc = [target for target in state.revenue_targets if target.subject_key == "Contract 4/VC #1"]
    assert {(target.value, target.exact) for target in vc} == {(0, Fraction(0))}
    assert _revenue(state, "Contract 4/POB #2", "FY2023-P03", "FY2023-P02") == Decimal("98.928025")


def test_tc_delivery_06_contract1_return() -> None:
    st, state = _run("Contract 1", STEP_07)
    assert _revenue(state, "Contract 1/POB #1", "FY2023-P04", "FY2023-P03") == Decimal(
        "-193.260654"
    )
    posted = _target(state, "Contract 1/POB #1", "FY2023-P04").value
    assert posted - _target(state, "Contract 1/POB #1", "FY2023-P03").value == usd("-193.26")
    assert _remaining(st, "Contract 1/POB #1", STEP_07) == 5  # POL-053 RESTORE_REMAINING_QUANTITY
    # Billing 300 with no delivery leaves POB #2 revenue unchanged.
    assert _revenue(state, "Contract 1/POB #2", "FY2023-P04", "FY2023-P03") == 0


# State after golden step 13 (docs/legacy/golden/13-*/contract_live.csv, latest row per POB):
# (POB, remaining quantity RQ_k, delivered N_k, revenue R_k, remaining allocation, step 14
# delivery). Float noise of 2.8e-14 on Contract 1 POB #1 is taken as 0 (DEV-005).
STEP_13: Mapping[str, tuple[date, tuple[tuple[str, str, str, str, str, str], ...]]] = {
    "Contract 1": (
        date(2023, 6, 15),
        (
            ("POB #1", "0", "0", "0", "0", "0"),
            ("POB #2", "1", "1", "118.53320118929634", "92.5336782303195", "1"),
            ("POB #3", "0.5", "0.5", "43.01634770780214", "43.01634770780214", "0.5"),
            ("POB #4", "1000", "0", "0", "502.90042516477985", "1000"),
        ),
    ),
    "Contract 2": (
        date(2023, 5, 31),
        (
            ("POB #1", "9", "1", "53.54090354090354", "519.6617108381814", "9"),
            ("POB #2", "3", "0", "0", "385.1851851851852", "3"),
            ("POB #3", "0.6", "0.4", "56.64488017429194", "84.96732026143789", "0.6"),
            ("VC #1", "1", "0", "0", "0", "1"),
        ),
    ),
    "Contract 3": (
        date(2023, 9, 15),
        (
            ("POB #1", "3", "0", "0", "678.0182497533068", "3"),
            ("POB #2", "1", "1", "153.41323606044816", "311.1106183406695", "1"),
            ("POB #3", "0.5", "0.5", "94.67198119587995", "94.67198119587994", "0.5"),
            ("POB #4", "0", "0", "0", "0", "0"),
            ("POB #5", "5", "0", "0", "1268.113933453816", "5"),
        ),
    ),
    "Contract 4": (
        date(2023, 8, 15),
        (
            ("POB #1", "6", "2", "119.92161985630305", "359.76485956890923", "6"),
            ("POB #2", "3", "1", "106.59699542782496", "319.7909862834749", "3"),
            ("POB #3", "2.5", "0", "0", "293.92553886348793", "2.5"),
            ("VC #1", "0.5", "0.5", "0", "0", "0.5"),
        ),
    ),
}
FINAL_PRICE = {"Contract 1": 800, "Contract 2": 1100, "Contract 3": 2600, "Contract 4": 1200}


def _after_modifications(contract_key: str) -> list[ObligationState]:
    """Step 13 segments: each POB's last boundary is ``PROSPECTIVE`` over the remaining totals.

    x′ = R_k + remaining allocation (CV-62, CV-63 parity base E_before), Q′ = RQ_k and N_k the net
    delivered quantity at the boundary (S06-R-14). Posted allocations apportion the final price
    by largest remainder (the stage 05 and 06 contract, faked here).
    """
    boundary, rows = STEP_13[contract_key]
    exact = [
        Fraction(Decimal(revenue)) + Fraction(Decimal(rest)) for _, _, _, revenue, rest, _ in rows
    ]
    posted = largest_remainder(FINAL_PRICE[contract_key] * 100, exact, [row[0] for row in rows])
    inception = {ob.obligation_key: ob for ob in _inception(contract_key)}
    obligations = []
    for (key, remaining, delivered, revenue, _, _), x_exact, a_posted in zip(
        rows, exact, posted, strict=True
    ):
        base = Fraction(Decimal(revenue))
        prospective = segment(
            x_exact,
            a_posted,
            start=boundary,
            end=TERM_END,
            basis="PROSPECTIVE",
            cause=SegmentCause.MODIFICATION,
            event_key=f"{contract_key}/EV-000099",
            base_revenue_posted=usd(format_exact(base, 2)),
            base_revenue_exact=base,
            quantity=Fraction(Decimal(remaining)),
            base_delivered=Fraction(Decimal(delivered)),
            measure="UNITS_DELIVERED",
        )
        before = inception.get(key)  # Contract 3 POB #5 is created by the 09.15 modification
        segments = [prospective] if before is None else [*before.segments, prospective]
        obligations.append(
            _units_obligation(contract_key, key, segments, prospective.totals.quantity)
        )
    return obligations


def test_tc_delivery_08_full_uat() -> None:
    for contract_key, (_, rows) in STEP_13.items():
        full = [
            *UPLOADS[contract_key],
            *(Row(STEP_14, key, delivery) for key, *_, delivery in rows if delivery != "0"),
        ]
        obligations = _after_modifications(contract_key)
        st, state = _run(contract_key, STEP_14, rows=full, obligations=obligations)
        for key, _, _, revenue, rest, _ in rows:
            subject_key = f"{contract_key}/{key}"
            assert _remaining(st, subject_key, STEP_14) == 0
            # The whole remaining allocation is recognised in October (legacy RR at step 14).
            assert _exact(state, subject_key, "FY2023-P09") == Fraction(Decimal(revenue))
            assert _revenue(state, subject_key, "FY2023-P10", "FY2023-P09") == _six(
                Fraction(Decimal(rest))
            )
        total = sum(
            target.value for target in state.revenue_targets if target.period_key == "FY2023-P10"
        )
        assert total == usd(f"{FINAL_PRICE[contract_key]}.00")

    # CV-62 divisor since a boundary: 3 of Contract 2 POB #1's 9 remaining units earn
    # 3 × remaining allocation ÷ RQ_k, the legacy unit-rate refresh RALLOC ÷ RQ (legacy 02 §3.7).
    partial = [*UPLOADS["Contract 2"], Row(STEP_14, "POB #1", "3")]
    _, state = _run(
        "Contract 2", STEP_14, rows=partial, obligations=_after_modifications("Contract 2")
    )
    earned = _exact(state, "Contract 2/POB #1", "FY2023-P10") - _exact(
        state, "Contract 2/POB #1", "FY2023-P09"
    )
    assert earned == Fraction(Decimal("519.6617108381814")) * 3 / 9


def test_tc_delivery_20_deliver_all_then_return() -> None:
    rows = (Row(STEP_04, "POB #1", "5"), Row(STEP_05, "POB #1", "-1"))
    st, state = _run("Contract 1", STEP_05, rows=rows)
    subject_key = "Contract 1/POB #1"
    assert _six(_exact(state, subject_key, "FY2023-P01")) == Decimal("322.101090")
    assert _target(state, subject_key, "FY2023-P01").value == usd("322.10")  # C = A at f = 1
    assert _revenue(state, subject_key, "FY2023-P02", "FY2023-P01") == Decimal("-64.420218")
    assert _remaining(st, subject_key, STEP_05) == 1


def test_rec_026_progress_edge_cases() -> None:
    # Fractional delivery (0.4 of 1; TC-delivery-04) and delivery without billing (TC-delivery-02).
    _, state = _run("Contract 2", STEP_06)
    assert _six(_exact(state, "Contract 2/POB #3", "FY2023-P03")) == Decimal("46.153846")
    assert _six(_exact(state, "Contract 2/POB #1", "FY2023-P03")) == Decimal("58.846154")
    # Billing with zero delivery (TC-delivery-07): billing 20 leaves every revenue unchanged.
    _, billed = _run("Contract 2", STEP_07)
    for key in ("POB #1", "POB #2", "POB #3", "VC #1"):
        subject_key = f"Contract 2/{key}"
        assert _revenue(billed, subject_key, "FY2023-P04", "FY2023-P03") == 0
    total = sum(
        target.value for target in billed.revenue_targets if target.period_key == "FY2023-P04"
    )
    assert total == usd("105.00")
    assert state.findings == billed.findings == ()
