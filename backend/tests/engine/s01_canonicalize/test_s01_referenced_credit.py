"""Stage 01 ``REFUND_EXCEEDS_BILLED`` for a referenced credit memo over unreferenced billing
(ENGINE_SPEC S01-R-16, S01-INV-03; D-87 L6-5-Q-15, overruling the second sentence of the L4-3-Q-11
decision).

A referenced credit draws first on its obligation's referenced billing, then on the contract-level
unreferenced billing not yet drawn by unreferenced credits. ``REFUND_EXCEEDS_BILLED`` raises on the
obligation only when both are exhausted. Unreferenced credits keep the stream check. Before the fix
``FX-CHK-084-A`` stopped at stage 01: its invoice is unreferenced, and the credit memo names
``L1-GADGET``, whose referenced billing is 0.

Bundles come from ``support.bundles`` (DG-ENG-11); no database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EventInput, InputBundle
from erev_engine.stages import s01_canonicalize
from erev_engine.stages.state import CanonicalBundle
from erev_engine.trace import TraceBuilder
from support import bundles

CONTRACT = "Contract 1"
INCEPTION = date(2026, 3, 1)
LINE_END = date(2026, 12, 31)
LINES = (("POB #1", "Hardware 1", "5", "300.00"), ("POB #2", "Software 1", "5", "300.00"))
POB_1 = "Contract 1/POB %231"
POB_2 = "Contract 1/POB %232"


def booking() -> EventInput:
    lines = [
        bundles.booking_line(
            key,
            product_code=product,
            quantity=quantity,
            total_price=price,
            start=INCEPTION,
            end=LINE_END,
        )
        for key, product, quantity, price in LINES
    ]
    return bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=[key for key, *_ in LINES],
    )


def billing(stream: int, obligation: str | None, amount: str) -> EventInput:
    payload: dict[str, object] = {
        "invoice_number": f"INV-{stream}",
        "line_external_id": f"INV-{stream}",
        "amount": Decimal(amount),
        "issue_date": INCEPTION,
    }
    if obligation is not None:
        payload["obligation_key"] = obligation
    keys = [] if obligation is None else [obligation]
    return bundles.event(
        CONTRACT, stream, "BILLING_RECORDED", INCEPTION, payload, obligation_keys=keys
    )


def credit(stream: int, obligation: str | None, amount: str) -> EventInput:
    payload: dict[str, object] = {
        "credit_memo_number": f"CM-{stream}",
        "amount": Decimal(amount),
        "issue_date": INCEPTION,
    }
    if obligation is not None:
        payload["obligation_key"] = obligation
    keys = [] if obligation is None else [obligation]
    return bundles.event(
        CONTRACT, stream, "CREDIT_MEMO_RECORDED", INCEPTION, payload, obligation_keys=keys
    )


def run(*events: EventInput) -> CanonicalBundle:
    calendar = bundles.entity(start=date(2026, 1, 1), months=24)
    headers = (bundles.contract(CONTRACT, inception=INCEPTION),)
    products = [bundles.product(product) for _, product, *_ in LINES]
    value = InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
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
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )
    return s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))


def _findings(cb: CanonicalBundle) -> list[tuple[str, str, str | None, dict[str, str]]]:
    return [(f.code, f.subject_key, f.event_key, dict(f.detail)) for f in cb.findings]


def test_l7_5_referenced_credit_draws_on_unreferenced_billing() -> None:
    # FX-CHK-084-A shape: the invoice names no obligation, the credit memo names POB #1.
    cb = run(booking(), billing(2, None, "300.00"), credit(3, "POB #1", "200.00"))
    assert _findings(cb) == []
    point = cb.ledger.at(POB_1)
    assert (point.billed_cum, point.credited_cum) == (0, 200)
    # Referenced billing first, then the unreferenced remainder: 80.00 + 20.00 covers 100.00.
    covered = run(
        booking(),
        billing(2, "POB #1", "80.00"),
        billing(3, None, "20.00"),
        credit(4, "POB #1", "100.00"),
    )
    assert _findings(covered) == []


def test_l7_5_referenced_credit_raises_when_both_are_exhausted() -> None:
    exceeding = run(
        booking(),
        billing(2, "POB #1", "80.00"),
        billing(3, None, "20.00"),
        credit(4, "POB #1", "100.01"),
    )
    assert _findings(exceeding) == [
        (
            "REFUND_EXCEEDS_BILLED",
            POB_1,
            "Contract 1/EV-000004",
            {"billed": "100", "credited": "100.01", "event_key": "Contract 1/EV-000004"},
        )
    ]
    # Unreferenced credits draw on the unreferenced billing first: 300.00 − 250.00 leaves 50.00.
    drawn = run(
        booking(),
        billing(2, None, "300.00"),
        credit(3, None, "250.00"),
        credit(4, "POB #1", "100.00"),
    )
    assert _findings(drawn) == [
        (
            "REFUND_EXCEEDS_BILLED",
            POB_1,
            "Contract 1/EV-000004",
            {"billed": "50", "credited": "100", "event_key": "Contract 1/EV-000004"},
        )
    ]
    # Referenced credits of several obligations draw on the same unreferenced billing.
    shared = run(
        booking(),
        billing(2, None, "300.00"),
        credit(3, "POB #1", "200.00"),
        credit(4, "POB #2", "150.00"),
    )
    assert _findings(shared) == [
        (
            "REFUND_EXCEEDS_BILLED",
            POB_2,
            "Contract 1/EV-000004",
            {"billed": "100", "credited": "150", "event_key": "Contract 1/EV-000004"},
        )
    ]
    # No unreferenced billing: the obligation check as before (L4-3-Q-11 first sentence).
    alone = run(booking(), billing(2, "POB #2", "100.00"), credit(3, "POB #2", "150.00"))
    assert [code for code, *_ in _findings(alone)] == ["REFUND_EXCEEDS_BILLED"]


def test_l7_5_unreferenced_credit_keeps_the_stream_check() -> None:
    # 300.00 billed on POB #1 covers an unreferenced credit of 300.00, not 300.01.
    covered = run(booking(), billing(2, "POB #1", "300.00"), credit(3, None, "300.00"))
    assert _findings(covered) == []
    exceeding = run(booking(), billing(2, "POB #1", "300.00"), credit(3, None, "300.01"))
    assert [(code, subject) for code, subject, *_ in _findings(exceeding)] == [
        ("REFUND_EXCEEDS_BILLED", CONTRACT)
    ]
