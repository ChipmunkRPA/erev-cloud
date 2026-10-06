"""ENC-6: right to invoice and usage (ENGINE_SPEC_B §9.2.6 S09-R-18, S09-R-19; S09-R-01
``PERIOD_VC``; POLICIES ALG-03 CHK-014; D-87 L6-5-Q-16).

The obligation is built as stage 05 opens it: a ``FIXED`` segment (the stand-ready fee or
minimum, 0 here) and a ``PERIOD_VC`` marker segment; stage 09 realises the right-to-invoice amounts
from the events (S09-R-18 source order: ``USAGE_REPORTED.rated_amount``, else ``DELIVERY_RECORDED``
quantity × the booking line's ``unit_price`` — D-87 L6-5-Q-16 — else invoiced amounts net of credit
memos) and DERIVED usage fees at the end of their usage period (S09-R-19). Every trace re-evaluates
node for node (DG-ENG-04) and every formula id is declared by ``STAGES``. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.stages import STAGES
from erev_engine.stages.s09_recognition import RecognitionState, run
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ContractView,
    EstimatePin,
    EstimatePins,
    ObligationState,
)
from erev_engine.trace import Trace, TraceBuilder, reevaluate
from support.recognition import (
    CONTRACT_KEY,
    INCEPTION,
    allocated_state,
    book_context,
    contract,
    emit_catch_up_nodes,
    estimate_version,
    event_view,
    obligation,
    period_amounts,
    segment,
    targets_by_period,
    usd,
)

CTX = book_context()
DEC_1, DEC_31 = date(2026, 12, 1), date(2026, 12, 31)
JAN_1, JAN_31, FEB_28, DEC_END = (
    date(2026, 1, 1),
    date(2026, 1, 31),
    date(2026, 2, 28),
    date(2026, 12, 31),
)
RTI, USAGE = "RIGHT_TO_INVOICE", "USAGE"


def _run(ctx: BookContext, st: AllocatedState) -> tuple[RecognitionState, Trace]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    state = run(ctx, st, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    spec = next(item for item in STAGES if item.stage == "09")
    assert {node.formula_id for node in trace.nodes} <= set(spec.formula_ids)
    return state, trace


def _realised_obligation(
    key: str, method: str, start: date, end: date, fixed: str = "0"
) -> ObligationState:
    """A ``FIXED`` segment (X = the stand-ready fee, 0 in the corpus keys) and the ``PERIOD_VC``
    marker segment stage 05 opens for a right-to-invoice or DERIVED-usage obligation."""
    parts = [
        segment(Fraction(fixed), usd(f"{fixed}.00"), start=start, end=end, measure=method),
        segment(0, 0, start=start, end=end, component="PERIOD_VC", measure=method),
    ]
    return obligation(key, parts, method=method, convention=None, start=start, end=end)


def _usage(
    version: int,
    key: str,
    when: date,
    period: tuple[date, date] | None,
    quantity: str,
    rated: str | None,
) -> object:
    payload: dict[str, object] = {
        "obligation_key": key,
        "metric": "HOURS",
        "quantity": Decimal(quantity),
    }
    if period is not None:
        payload["usage_period_start"], payload["usage_period_end"] = period
    if rated is not None:
        payload["rated_amount"] = Decimal(rated)
    return event_view(CONTRACT_KEY, version, "USAGE_REPORTED", when, payload, obligation_keys=[key])


def _delivery(version: int, key: str, when: date, quantity: str) -> object:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return event_view(
        CONTRACT_KEY, version, "DELIVERY_RECORDED", when, payload, obligation_keys=[key]
    )


def _booked(key: str, *, quantity: str, total_price: str, unit_price: str | None) -> ContractView:
    """The contract view stage 02 builds: the ``CONTRACT_BOOKED`` payload with decimals as
    Fractions (CV-30), which carries the line's ``unit_price``."""
    line: dict[str, object] = {
        "obligation_key": key,
        "product_code": "SKU-1",
        "quantity": Fraction(quantity),
        "total_price": Fraction(total_price),
        "start_date": DEC_1,
        "end_date": DEC_31,
    }
    if unit_price is not None:
        line["unit_price"] = Fraction(unit_price)
    header = dataclasses.replace(contract(CONTRACT_KEY), inception_date=INCEPTION)
    return ContractView(
        header=header,
        booking={"lines": (line,)},
        status_in_book={"ASC606": ((INCEPTION, "ACTIVE"),)},
    )


def test_chk_014_right_to_invoice_revenue() -> None:
    # CHK-014 (ALG-03 2.4-A; POS-CHK-014): 120 hours × 25.00 performed in December, reported as
    # USAGE_REPORTED with rated_amount 3,000.00 for the usage period 1–31 Dec → December revenue
    # 3,000.00 with a booking of 120 × 25.00 = 3,000.00 (X = 0 on the FIXED component: the right to
    # invoice IS the revenue, S09-R-18).
    ob = _realised_obligation("POB-RTI", RTI, DEC_1, DEC_31)
    reported = _usage(3, "POB-RTI", DEC_31, (DEC_1, DEC_31), "120", "3000.00")
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-RTI", quantity="120", total_price="3000.00", unit_price="25")],
        events=[reported],
        inception=INCEPTION,
    )
    state, _ = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert by_period.get("FY2026-P12") == usd("3000.00")
    assert sum(by_period.values()) == usd("3000.00")


def test_d87_delivered_quantity_times_unit_price_is_the_right_to_invoice() -> None:
    # D-87 L6-5-Q-16 (REC-CHK-014, POS-CHK-010): a right-to-invoice line booked with quantity 1,
    # total_price 0.00 and unit_price 25.00; a DELIVERY_RECORDED of 120 hours in December and no
    # USAGE_REPORTED → 120 × 25.00 = 3,000.00 in December (S01-R-17 over-delivery does not apply —
    # tested at stage 01).
    ob = _realised_obligation("POB-TM", RTI, DEC_1, DEC_31)
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-TM", quantity="1", total_price="0.00", unit_price="25.00")],
        events=[_delivery(3, "POB-TM", date(2026, 12, 15), "120")],
        inception=INCEPTION,
    )
    state, _ = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert by_period.get("FY2026-P12") == usd("3000.00")
    assert sum(by_period.values()) == usd("3000.00")


def test_s09_r18_rated_usage_precedes_deliveries_and_invoices() -> None:
    # Source order: the rated USAGE_REPORTED amount is the right to invoice; a delivery of the same
    # hours does not double it, and a later invoice of the same amount adds nothing (invoices
    # without performance create no revenue).
    ob = _realised_obligation("POB-RTI", RTI, DEC_1, DEC_31)
    events = [
        _usage(3, "POB-RTI", DEC_31, (DEC_1, DEC_31), "120", "3000.00"),
        _delivery(4, "POB-RTI", DEC_31, "120"),
        event_view(
            CONTRACT_KEY,
            5,
            "BILLING_RECORDED",
            date(2027, 1, 5),
            {
                "obligation_key": "POB-RTI",
                "invoice_number": "INV-1",
                "amount": Decimal("3000.00"),
                "issue_date": date(2027, 1, 5),
            },
            obligation_keys=["POB-RTI"],
        ),
    ]
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-RTI", quantity="120", total_price="3000.00", unit_price="25")],
        events=events,
        inception=INCEPTION,
    )
    state, _ = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert by_period.get("FY2026-P12") == usd("3000.00")
    assert sum(by_period.values()) == usd("3000.00")


def test_s09_r19_usage_derived_fees_count_at_the_end_of_their_usage_period() -> None:
    # EX-12A (POB-S2-EX12A-OWNVOLUMES): the 1 % management fee is a DERIVED usage fee reported at
    # each month end; January's 20,000.00 belongs to January, February's 15,000.00 to February
    # (a fee reported after the period end counts when reported — test_s09_r49_release_flags).
    ob = _realised_obligation("POB-MGMT", USAGE, JAN_1, DEC_END)
    events = [
        _usage(3, "POB-MGMT", JAN_31, (JAN_1, JAN_31), "2000000", "20000.00"),
        _usage(4, "POB-MGMT", FEB_28, (date(2026, 2, 1), FEB_28), "1500000", "15000.00"),
    ]
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-MGMT", quantity="1", total_price="0.00", unit_price="0.01")],
        events=events,
        inception=INCEPTION,
    )
    state, _ = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert (by_period.get("FY2026-P01"), by_period.get("FY2026-P02")) == (
        usd("20000.00"),
        usd("15000.00"),
    )
    assert sum(by_period.values()) == usd("35000.00")


# --- D-98 candidate 28 (ENGINE_SPEC_B S09-R-18 rev 1.20; §9.2.4 RIGHT_TO_INVOICE row) ---------

RTI_FORMULA = "rec.progress.right_to_invoice.v1"


def _rti_with_stated_price(key: str, stated: str, start: date, end: date) -> ObligationState:
    """The stage 05 shape when the line books a total: FIXED X = P (the stated price) beside the
    PERIOD_VC marker; ``support.recognition.obligation`` sets ``stated_price`` to the first
    segment's exact allocation."""
    parts = [
        segment(Fraction(stated), usd(f"{stated}.00"), start=start, end=end, measure=RTI),
        segment(0, 0, start=start, end=end, component="PERIOD_VC", measure=RTI),
    ]
    return obligation(key, parts, method=RTI, convention=None, start=start, end=end)


def _progress_nodes(trace: Trace, subject_key: str) -> dict[str, object]:
    return {
        node.id: node
        for node in trace.nodes
        if node.id.startswith(f"progress_ratio:{subject_key}:")
    }


def test_d98_28_pos_chk_014_stated_price_recognised_by_the_right_to_invoice() -> None:
    # POS-CHK-014: the line books 120 × 25 = 3,000.00 (P = X = 3,000) and December's rated usage is
    # 3,000.00 — revenue 3,000.00, not 6,000.00: the right to invoice is the FIXED component's
    # measure of progress (f = R ÷ P = 1) and nothing exceeds P for PERIOD_VC.
    ob = _rti_with_stated_price("POB-RTI", "3000", DEC_1, DEC_31)
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-RTI", quantity="120", total_price="3000.00", unit_price="25")],
        events=[_usage(3, "POB-RTI", DEC_31, (DEC_1, DEC_31), "120", "3000.00")],
        inception=INCEPTION,
    )
    state, trace = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert by_period.get("FY2026-P12") == usd("3000.00")
    assert sum(by_period.values()) == usd("3000.00")
    ratio = _progress_nodes(trace, ob.subject_key)[f"progress_ratio:{ob.subject_key}:FY2026-P12"]
    assert (ratio.formula_id, ratio.value) == (RTI_FORMULA, "1")
    assert (ratio.params["realised"], ratio.params["stated"]) == ("3000", "3000")


def test_d98_28_disc_s10_partial_right_to_invoice_leaves_the_remainder_unrecognised() -> None:
    # DISC-S10 EX-42: 480 expected hours booked at 25.00 (P = 12,000.00) over two years; 120 hours
    # rated 3,000.00 by December → revenue 3,000.00 (f = 1/4), 9,000.00 of the FIXED allocation
    # remains (the S15-R-08 RPO basis), nothing on PERIOD_VC.
    start, end = date(2026, 7, 1), date(2028, 6, 30)
    ob = _rti_with_stated_price("POB-CLEAN", "12000", start, end)
    events = [
        _usage(3 + i, "POB-CLEAN", date(2026, 7 + i, 28), None, "20", "500.00") for i in range(6)
    ]
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-CLEAN", quantity="480", total_price="12000.00", unit_price="25")],
        events=events,
        inception=INCEPTION,
    )
    state, trace = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert sum(by_period.values()) == usd("3000.00")
    assert by_period.get("FY2026-P12") == usd("500.00")
    ratio = _progress_nodes(trace, ob.subject_key)[f"progress_ratio:{ob.subject_key}:FY2026-P12"]
    assert (ratio.formula_id, ratio.value) == (RTI_FORMULA, "0.25")


def test_d98_28_right_to_invoice_above_the_stated_price_rides_period_vc() -> None:
    # P = 1,000.00 booked, 3,000.00 rated: the FIXED component is complete (f = 1, 1,000.00) and
    # the 2,000.00 above P is the PERIOD_VC realised amount (S04-R-06 rev 1.12) — revenue 3,000.00.
    ob = _rti_with_stated_price("POB-RTI", "1000", DEC_1, DEC_31)
    st = allocated_state(
        [ob],
        contracts=[_booked("POB-RTI", quantity="40", total_price="1000.00", unit_price="25")],
        events=[_usage(3, "POB-RTI", DEC_31, (DEC_1, DEC_31), "120", "3000.00")],
        inception=INCEPTION,
    )
    state, trace = _run(CTX, st)
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert sum(by_period.values()) == usd("3000.00")
    nodes = {node.id: node for node in trace.nodes}
    fixed = nodes[f"revenue_target_exact:{ob.subject_key}#FIXED:FY2026-P12"]
    ratio = nodes[f"progress_ratio:{ob.subject_key}:FY2026-P12"]
    # The FIXED component is complete at P (f = 1 → 1,000.00); the other 2,000.00 of the 3,000.00
    # period revenue is the PERIOD_VC realised amount above P.
    assert (fixed.value, ratio.formula_id, ratio.value) == ("1000", RTI_FORMULA, "1")
    assert ratio.params["realised"] == "3000" and ratio.params["stated"] == "1000"


# --- D-98 candidate 37: the POL-092 right-to-invoice guard (S09-R-18 rev 1.21) --------------------

GUARD = "RTI_EXPEDIENT_NOT_APPLICABLE"


def _element(element_type: str, *, key: str = "POB-RTI", code: str = "VC-1") -> EstimatePins:
    """One VARIABLE_CONSIDERATION element of ``element_type`` targeting ``key``, pinned by a
    stage-08 event of version 2."""
    version = dataclasses.replace(
        estimate_version(
            f"{CONTRACT_KEY}/{code}", "VARIABLE_CONSIDERATION", 1, DEC_1, obligation_key=key
        ),
        vc_element_type=element_type,
    )
    pin_event = event_view(CONTRACT_KEY, 2, "ESTIMATE_CHANGED", DEC_1, {"estimate": code})
    return EstimatePins({version.estimate_key: (EstimatePin(version, pin_event.order_key),)})


def _guarded(
    *,
    total_price: str = "3000.00",
    quantity: str = "120",
    unit_price: str | None = "25",
    estimates: EstimatePins | None = None,
    ctx: BookContext = CTX,
) -> tuple[RecognitionState, ObligationState]:
    ob = _realised_obligation("POB-RTI", RTI, DEC_1, DEC_31)
    st = allocated_state(
        [ob],
        contracts=[
            _booked("POB-RTI", quantity=quantity, total_price=total_price, unit_price=unit_price)
        ],
        events=[_usage(3, "POB-RTI", DEC_31, (DEC_1, DEC_31), "120", "3000.00")],
        inception=INCEPTION,
        estimates=estimates,
    )
    state, _ = _run(ctx, st)
    return state, ob


def _guard_findings(state: RecognitionState) -> list[tuple[str, str, str]]:
    return [
        (f.severity, f.detail["policy"], f.detail["reasons"])
        for f in state.findings
        if f.code == GUARD
    ]


def test_d98_37_linear_rate_line_passes_the_guard() -> None:
    # POS-CHK-014: 120 × 25 = 3,000 — the invoice corresponds directly to performance.
    state, _ = _guarded()
    assert _guard_findings(state) == []


def test_d98_37_rate_line_with_total_zero_passes_the_guard() -> None:
    # REC-FS-08 / REC-CHK-014 / POS-CHK-010: quantity 1, total 0.00, unit price 25 (D-87 rate line).
    state, _ = _guarded(total_price="0.00", quantity="1")
    assert _guard_findings(state) == []


def test_d98_37_upfront_fee_beside_the_rate_blocks_the_expedient() -> None:
    # total 3,500 ≠ 120 × 25: a fixed component (or a non-constant rate) beside the rate → ERROR.
    state, _ = _guarded(total_price="3500.00")
    assert _guard_findings(state) == [
        ("ERROR", "BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT", "NONLINEAR_PRICE:3500≠120×25")
    ]


def test_d98_37_tier_rebate_and_minimum_elements_block_the_expedient() -> None:
    for element_type in ("VOLUME_TIER", "REBATE", "PRICE_PROTECTION", "USAGE"):
        state, _ = _guarded(estimates=_element(element_type))
        assert _guard_findings(state) == [
            ("ERROR", "BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT", f"ELEMENT:{element_type}:K-01/VC-1")
        ], element_type


def test_d98_37_element_targeting_another_obligation_does_not_block() -> None:
    state, _ = _guarded(estimates=_element("VOLUME_TIER", key="POB-OTHER"))
    assert _guard_findings(state) == []


def test_d98_37_allow_bypasses_the_guard_and_records_the_policy_reason() -> None:
    allowing = book_context(
        overrides=(
            (
                "recognition.right_to_invoice_guard",
                "OBLIGATION",
                f"{CONTRACT_KEY}/POB-RTI",
                "ALLOW",
            ),
        )
    )
    state, ob = _guarded(total_price="3500.00", ctx=allowing)
    assert _guard_findings(state) == [("WARNING", "ALLOW", "NONLINEAR_PRICE:3500≠120×25")]
    # The bypass leaves the recognition itself untouched: the right to invoice is recognised.
    by_period = period_amounts(targets_by_period(state, ob.subject_key))
    assert sum(by_period.values()) == usd("3000.00")
