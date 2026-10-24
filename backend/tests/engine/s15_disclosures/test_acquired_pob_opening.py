"""Acquisition baselines enter POB eligibility after cutover, not as current billing."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import erev_engine
import pytest
from support import onboarding_worlds as w
from support import bundles


@pytest.mark.parametrize("at", [date(2025, 12, 31), date(2026, 1, 31), date(2026, 2, 28)])
@pytest.mark.parametrize("pre_invoice", [False, True])
def test_acquired_pob_opening_preserves_baseline_and_journals(at, pre_invoice):
    extra = (
        []
        if at.year == 2025
        else [
            bundles.event(
                w.CONTRACT,
                5,
                "BILLING_RECORDED",
                at,
                {
                    "invoice_number": "POST-ACQ",
                    "line_external_id": "POST-ACQ-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("100.00"),
                    "issue_date": at,
                },
                obligation_keys=[w.OBLIGATION],
            )
        ]
    )
    if pre_invoice:
        extra.append(
            bundles.event(
                w.CONTRACT,
                4,
                "BILLING_RECORDED",
                date(2025, 6, 1),
                {
                    "invoice_number": "PRE-ACQ",
                    "line_external_id": "PRE-ACQ-1",
                    "obligation_key": w.OBLIGATION,
                    "amount": Decimal("240000.00"),
                    "issue_date": date(2025, 6, 1),
                },
                obligation_keys=[w.OBLIGATION],
            )
        )
    value = w.chk_121(
        as_of=at,
        extra=extra,
        states={"FY2025-P12": "open"},
        policies={
            "onboarding.method": "OPENING_BALANCES_AT_CUTOVER",
            "rollforward.opening_liability_consumption": "FIFO_WITHIN_POB",
        },
    )
    old = erev_engine.compute(replace(value, evidence_revision=13))
    new = erev_engine.compute(replace(value, evidence_revision=14))
    for prior, book in zip(old.books, new.books, strict=True):
        assert book.posting_intents == prior.posting_intents
        assert prior.disclosure_rollforwards[0].obligation_closing == {
            "status": "UNAVAILABLE",
            "reason": "Original principal, same-entity sources are required.",
        }
        assert book.disclosure_rollforwards
        row = next(row for row in book.disclosure_rollforwards if row.view == "TRANSACTION")
        assert row.obligation_closing["status"] == "AVAILABLE"
        item = row.obligation_closing["obligations"][w.SUBJECT]
        original = 12000000 if book.book_code == "ASC606" else 9000000
        monthly = 1000000 if book.book_code == "ASC606" else 750000
        elapsed = 0 if at.year == 2025 else at.month
        assert item["liability"] == original - elapsed * monthly + (10000 if at.year == 2026 else 0)
        assert any(source.startswith("opening_revenue_cum@") for source in item["sources"])
        values = row.lines["CONTRACT_LIABILITY"]
        assert values["CLOSING"] == item["liability"]
        if elapsed:
            assert values["REVENUE_FROM_OPENING_BALANCE"] == -monthly
            assert values["REVENUE_FROM_OTHER_INCREASES"] == 0
        else:
            assert values["OPENING"] == 0
            assert values["BUSINESS_COMBINATIONS"] == original


def test_acquired_baseline_does_not_override_authenticated_frozen_opening():
    from types import SimpleNamespace as NS
    from erev_engine.errors import EngineError
    from erev_engine.stages.s15_disclosures.rollforward import _within_obligations

    records = NS(acquired_pob_opening=True, flows=())
    own = [NS(subject_key="C/P", opening=None)]
    lines = {
        "CONTRACT_LIABILITY": {
            "OPENING": 100,
            "REVENUE_FROM_OPENING_BALANCE": 0,
            "REVENUE_FROM_OTHER_INCREASES": 0,
        }
    }
    with pytest.raises(EngineError, match="complete original cutover baselines"):
        _within_obligations(
            records, own, "US", date(2026, 1, 1), date(2026, 1, 31), date(2025, 12, 31), lines
        )
    _within_obligations(
        records,
        own,
        "US",
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2025, 12, 31),
        lines,
        opening_obligations={"C/P": 100},
    )
    assert lines["CONTRACT_LIABILITY"]["REVENUE_FROM_OPENING_BALANCE"] == 0
