"""Ordinary activity must not become a residual at another member's acquisition date."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support import onboarding_worlds as w

from erev_engine import compute


@pytest.mark.parametrize("invoice_day", [date(2025, 12, 30), w.CUTOVER])
@pytest.mark.parametrize("billed", ["240000", "0"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"])
def test_mixed_acquisition_keeps_activity_and_dates_netting(invoice_day, billed, consumption):
    value = w.two_contracts(as_of=date(2026, 1, 31))
    ordinary = w.COLLIDING[0]
    events = [
        replace(e, payload=w.opening_payload(billed_cum=billed))
        if e.event_type == "OPENING_BALANCE_ESTABLISHED"
        else e
        for e in value.events
        if not (e.contract_key == ordinary and e.event_type == "OPENING_BALANCE_ESTABLISHED")
    ]
    events.append(
        bundles.event(
            ordinary,
            4,
            "BILLING_RECORDED",
            invoice_day,
            {
                "invoice_number": "ORDINARY",
                "line_external_id": "ORDINARY-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("240000"),
                "issue_date": invoice_day,
            },
            obligation_keys=[w.OBLIGATION],
        )
    )
    value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(p, value=consumption)
                    if p.code == "rollforward.opening_liability_consumption"
                    else p
                    for p in book.policies
                ),
            )
            for book in value.books
        ),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
    )
    prior = compute(replace(value, evidence_revision=24)).books[0]
    current = compute(replace(value, evidence_revision=25)).books[0]
    assert current.posting_intents == prior.posting_intents
    assert current.fx_layer_movements == prior.fx_layer_movements
    row = next(r for r in current.disclosure_rollforwards if r.view == "TRANSACTION")
    assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == (24000000 if billed == "240000" else 0)
    for role, amounts in row.lines.items():
        assert amounts["OTHER"] == 0, (role, dict(amounts))
        assert amounts["CLOSING"] == sum(v for k, v in amounts.items() if k != "CLOSING")
    if invoice_day < w.CUTOVER:
        assert row.lines["CONTRACT_LIABILITY"]["INCREASES_BILLING"] == 24000000
        assert row.lines["CONTRACT_LIABILITY"]["BUSINESS_COMBINATIONS"] == (
            12000000 if billed == "240000" else -12000000
        )
    elif billed == "240000":
        # Ordinary revenue comes first; acquisition settles its asset before billing.
        assert row.lines["CONTRACT_ASSET"]["BUSINESS_COMBINATIONS"] == -12000000
        assert row.lines["CONTRACT_LIABILITY"]["BUSINESS_COMBINATIONS"] == 0
    if consumption == "FIFO_WITHIN_POB" and invoice_day < w.CUTOVER and billed == "240000":
        later = bundles.event(
            ordinary,
            5,
            "BILLING_RECORDED",
            date(2026, 1, 1),
            {
                "invoice_number": "LATER",
                "line_external_id": "LATER-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("100"),
                "issue_date": date(2026, 1, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        subsequent = compute(replace(value, evidence_revision=25, events=(*value.events, later)))
        period = next(
            r
            for r in subsequent.books[0].disclosure_rollforwards
            if r.period_key == "FY2026-P01" and r.view == "TRANSACTION"
        )
        liability = period.lines["CONTRACT_LIABILITY"]
        assert liability["OPENING"] == 24000000
        assert liability["CLOSING"] == 22010000
        assert liability["REVENUE_FROM_OPENING_BALANCE"] == -2000000
        assert liability["OTHER"] == 0
