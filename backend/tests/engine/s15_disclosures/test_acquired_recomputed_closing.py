"""Recomputed acquisition eligibility reads original cumulative targets, not ERP imports."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support import onboarding_worlds as w

import erev_engine


@pytest.mark.parametrize("engine_invoice", [False, True])
@pytest.mark.parametrize("imported", ["100000", "120000", "140000"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_POB", "FIFO_WITHIN_CONTRACT"])
def test_recomputed_acquisition_uses_native_revenue_and_preserves_journals(
    imported, consumption, engine_invoice
):
    value = w.chk_121(
        as_of=date(2026, 1, 31),
        states={"FY2025-P12": "open"},
        payload=w.opening_payload(
            revenue_cum=imported,
            remaining_allocation=str(Decimal("240000") - Decimal(imported)),
        ),
        extra=[
            bundles.event(
                w.CONTRACT,
                5,
                "BILLING_RECORDED",
                date(2026, 1, 31),
                {
                    "invoice_number": "POST-ACQ",
                    "line_external_id": "POST-ACQ-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("100"),
                    "issue_date": date(2026, 1, 31),
                },
                obligation_keys=[w.OBLIGATION],
            ),
        ],
        policies={
            "onboarding.method": "RECOMPUTE_FROM_INCEPTION",
            "billing.posting": "ENGINE" if engine_invoice else "ERP",
            "rollforward.opening_liability_consumption": consumption,
        },
    )
    if engine_invoice:
        invoice = bundles.event(
            w.CONTRACT,
            4,
            "BILLING_RECORDED",
            date(2025, 6, 1),
            {
                "invoice_number": "ORIGINAL",
                "line_external_id": "ORIGINAL-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("200000"),
                "issue_date": date(2025, 6, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        value = replace(
            value,
            events=tuple(
                sorted(
                    (*value.events, invoice),
                    key=lambda e: (e.effective_date, e.record_seq, e.event_key),
                )
            ),
        )
    previous = erev_engine.compute(replace(value, evidence_revision=13))
    current = erev_engine.compute(replace(value, evidence_revision=38))
    for old, book in zip(previous.books, current.books, strict=True):
        assert book.posting_intents == old.posting_intents
        for row in book.disclosure_rollforwards:
            assert row.obligation_closing["status"] == "AVAILABLE"
            item = row.obligation_closing["obligations"][w.SUBJECT]
            expected = (
                (20010000 if engine_invoice else 24010000, 13000000)
                if book.book_code == "ASC606"
                else (9010000, 750000)
            )
            assert (item["billed"], item["revenue"]) == expected
            assert item["liability"] == expected[0] - expected[1]
            assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == item["liability"]
            assert row.lines["CONTRACT_LIABILITY"]["REVENUE_FROM_OTHER_INCREASES"] == 0
            assert row.lines["CONTRACT_LIABILITY"]["OTHER"] == 0
            if book.book_code == "ASC606":
                nodes = {n.id for n in book.trace.nodes}
                assert set(item["sources"]) <= nodes
                assert any(s.startswith("billed_cum:") for s in item["sources"])
                assert any(s.startswith("revenue_cum:") for s in item["sources"])


def test_closed_recomputed_cutover_does_not_substitute_imported_balances():
    value = w.chk_121(
        as_of=date(2025, 12, 31),
        policies={"onboarding.method": "RECOMPUTE_FROM_INCEPTION"},
    )
    output = erev_engine.compute(replace(value, evidence_revision=38))
    asc = next(b for b in output.books if b.book_code == "ASC606")
    assert all(r.obligation_closing["status"] == "UNAVAILABLE" for r in asc.disclosure_rollforwards)
