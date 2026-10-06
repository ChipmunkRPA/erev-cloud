"""D-98 candidate 29 (POS-CHK-010; ENC-6): the realised right to invoice enters the transaction
price once and is never allocated a second time to the fixed-price obligations.

The POS-CHK-010 shape: a time-and-materials rate line (P1-TM, quantity 1, ``total_price`` 0.00,
``unit_price`` 25.00, ``RIGHT_TO_INVOICE``) beside two fixed-price lines (10,000.00 and 2,000.00);
120 hours delivered in January → the version price is 15,000.00 = fixed 12,000.00 + realised
3,000.00 (ENGINE_SPEC S04-R-02, S04-R-06 rev 1.12; 04 DB-17 V1), P1-TM's allocation is the realised
3,000.00 (S09-R-01 ``PERIOD_VC``) and P2 / P3 keep 10,000.00 / 2,000.00 (the relative-SSP
allocation of the fixed consideration alone). Whole engine (``compute``); no database (DG-TST-18).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from erev_engine import compute
from support import bundles
from test_compute import INCEPTION, entry, event, template, world

RTI_TEMPLATE = template(
    "TPL-RTI",
    satisfaction_pattern="OVER_TIME",
    over_time_criterion="OT_A",
    recognition_method="RIGHT_TO_INVOICE",
)


def _line(key: str, product: str, total: str, **members: object) -> dict[str, object]:
    line = bundles.booking_line(
        key,
        product_code=product,
        quantity="1",
        total_price=total,
        start=INCEPTION,
        end=date(2026, 12, 31),
    )
    return {**line, **members}


def test_d98_29_realised_right_to_invoice_is_priced_once_and_stays_with_its_line() -> None:
    lines = [
        _line("P1-TM", "TM-HOURS", "0.00", unit_price=Decimal("25.00")),
        _line("P2-MILESTONE", "PHASE-1", "10000.00"),
        _line("P3-BUILD", "PHASE-2", "2000.00"),
    ]
    keys = [str(line["obligation_key"]) for line in lines]
    events = [
        event(1, "CONTRACT_BOOKED", INCEPTION, {"lines": lines}, keys),
        event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        event(
            3,
            "DELIVERY_RECORDED",
            date(2026, 1, 15),
            {"obligation_key": "P1-TM", "quantity": Decimal("120"), "trigger": "DELIVERY"},
            ["P1-TM"],
        ),
    ]
    bundle = world(
        events,
        products=[
            ("TM-HOURS", "TPL-RTI", "PRINCIPAL"),
            ("PHASE-1", "TPL-PIT", "PRINCIPAL"),
            ("PHASE-2", "TPL-PIT", "PRINCIPAL"),
        ],
        entries=[
            entry("TM-HOURS", point="0"),
            entry("PHASE-1", point="10000"),
            entry("PHASE-2", point="2000"),
        ],
        templates=(RTI_TEMPLATE,),
    )
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    assert book.contract_version is not None
    assert book.contract_version.columns["transaction_price"] == 1_500_000  # 15,000.00
    allocated = {
        row.subject_key.rsplit("/", 1)[1]: row.columns["allocated_amount"]
        for row in book.obligation_versions
    }
    # The realised 3,000.00 is P1-TM's alone; the fixed 12,000.00 is allocated by relative SSP to
    # P2 and P3 exactly as without the rate line — nothing is allocated twice.
    assert allocated == {"P1-TM": 300_000, "P2-MILESTONE": 1_000_000, "P3-BUILD": 200_000}
    revenue = {
        row.subject_key.rsplit("/", 1)[1]: row.columns["revenue_cum"]
        for row in book.obligation_versions
    }
    assert revenue["P1-TM"] == 300_000  # 120 h × 25.00, the right to invoice (S09-R-18)
