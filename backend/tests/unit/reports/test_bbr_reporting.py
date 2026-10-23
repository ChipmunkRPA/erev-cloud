"""Reporting translation preserves signed source sums and journal aggregation basis."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.reports import reporting_currency
from erev_api.domain.reports.builders import bbr_reporting
from erev_api.domain.reports.builders import bookings_billings_revenue as bbr
from tests.unit.reports.test_bbr import ENTITY, PERIODS, contribution


@pytest.mark.parametrize(
    "amounts", [("0.01", "0.01"), ("-0.01", "-0.01"), ("0.01", "-0.01"), ("100.03", "-25.01")]
)
def test_signed_rounding_matches_period_journal_and_stable_source_order(amounts):
    sources = {name: () for name in bbr.MEASURES}
    sources["revenue"] = tuple(
        replace(
            contribution(amount, date(2026, 6, 1)),
            source_id=UUID(int=i + 10),
            period_id=PERIODS[0].id,
        )
        for i, amount in enumerate(amounts)
    )
    rate = reporting_currency.Translation(
        "GBP", {ENTITY.id: {"base_currency": "USD", "rate": "0.5"}}
    )
    rates = {(ENTITY.id, PERIODS[0].id): rate}
    periods = {ENTITY.id: PERIODS}
    translated = bbr_reporting.translate(sources, (ENTITY,), periods, rates)
    reverse = bbr_reporting.translate(
        {**sources, "revenue": tuple(reversed(sources["revenue"]))}, (ENTITY,), periods, rates
    )
    assert translated == reverse
    original = sum(map(Decimal, amounts))
    expected = rate.amount(ENTITY.id, original)
    assert sum(s.amount for s in translated["revenue"]) == expected
    assert [s.functional_amount for s in translated["revenue"]] == list(map(Decimal, amounts))
    # A grouped journal line must tie to several source lines even at half-penny boundaries.
    journal = [
        {
            "entity_id": str(ENTITY.id),
            "period_id": str(PERIODS[0].id),
            "functional_currency": "USD",
            "credit_functional": str(original),
            "debit_functional": "0",
        }
    ]
    totals = bbr_reporting.journal_totals(journal, rates)
    result = bbr.dataset(
        translated,
        entities=(ENTITY,),
        periods=periods,
        granularity="QUARTER",
        currency_view="reporting",
        journal_revenue=totals,
    )
    assert result.tie_out_results[0]["result"] == "PASS"
    assert result.rows[0]["revenue"] == {"amount": f"{expected:.2f}", "currency": "GBP"}


def test_reporting_values_each_period_before_quarter_aggregation():
    sources = {name: () for name in bbr.MEASURES}
    sources["booked_new"] = (
        contribution("100", date(2026, 7, 1)),
        replace(contribution("100", date(2026, 8, 1)), source_id=UUID(int=8)),
    )
    rates = {
        (ENTITY.id, p.id): reporting_currency.Translation(
            "GBP", {ENTITY.id: {"base_currency": "USD", "rate": value}}
        )
        for p, value in zip(PERIODS, ("0.8", "0.9"), strict=True)
    }
    translated = bbr_reporting.translate(sources, (ENTITY,), {ENTITY.id: PERIODS}, rates)
    result = bbr.dataset(
        translated,
        entities=(ENTITY,),
        periods={ENTITY.id: PERIODS},
        granularity="QUARTER",
        currency_view="reporting",
        journal_revenue={},
    )
    assert result.rows[0]["booked_new"] == {"amount": "170.00", "currency": "GBP"}
