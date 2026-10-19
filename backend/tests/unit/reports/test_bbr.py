"""BBR fiscal aggregation, signed movements and period attribution."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import bookings_billings_revenue as bbr
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef
from erev_api.problems import Problem

ENTITY = EntityRef(UUID(int=1), "US:1", UUID(int=2), "USD", "UTC")
PERIODS = (
    PeriodRef(UUID(int=3), "P01", "July", 2027, 1, 1, date(2026, 7, 1), date(2026, 7, 31)),
    PeriodRef(UUID(int=4), "P02", "August", 2027, 2, 1, date(2026, 8, 1), date(2026, 8, 31)),
)


def contribution(amount: str, day: date) -> Contribution:
    return Contribution(
        "contract_event",
        UUID(int=5),
        UUID(int=6),
        ENTITY.id,
        day,
        "USD",
        Decimal(amount),
    )


def test_fiscal_quarter_signed_totals_and_posting_period() -> None:
    booked = contribution("100", date(2026, 7, 4))
    modification = contribution("-20", date(2026, 8, 4))
    invoice = contribution("80", date(2026, 7, 15))
    credit = contribution("-10", date(2026, 8, 4))
    # A June-effective late-event carry belongs to August's journal, not June.
    revenue = replace(contribution("35", date(2026, 6, 4)), period_id=PERIODS[1].id)
    sources = {
        "booked_new": [booked],
        "booked_modifications": [modification],
        "billings": [invoice, credit],
        "revenue": [revenue],
    }
    args: dict[str, Any] = dict(
        entities=(ENTITY,),
        periods={ENTITY.id: PERIODS},
        currency_view="transaction",
        journal_revenue={"USD": Decimal("35")},
    )
    quarter = bbr.dataset(sources, granularity="QUARTER", **args)
    assert len(quarter.rows) == 1
    row = quarter.rows[0]
    assert row["row_key"] == "period:FY2027-Q1:US%3A1"
    assert [row[m]["amount"] for m in bbr.MEASURES] == ["100.00", "-20.00", "70.00", "35.00"]
    assert quarter.tie_out_results[0]["result"] == "PASS"
    months = bbr.dataset(sources, granularity="MONTH", **args)
    assert [r["revenue"]["amount"] for r in months.rows] == ["0.00", "35.00"]


def test_currency_split_and_missing_valuation_refuse() -> None:
    usd = contribution("100", date(2026, 7, 4))
    eur = replace(usd, source_id=UUID(int=7), currency="EUR", amount=Decimal("60"))
    sources = {"booked_new": [usd, eur], "booked_modifications": [], "billings": [], "revenue": []}
    args: dict[str, Any] = dict(
        entities=(ENTITY,), periods={ENTITY.id: PERIODS}, granularity="MONTH", journal_revenue={}
    )
    result = bbr.dataset(sources, currency_view="transaction", **args)
    assert {r["row_key"] for r in result.rows} == {"period:P01:US%3A1:USD", "period:P01:US%3A1:EUR"}
    with pytest.raises(Problem, match="FX valuation"):
        bbr.dataset(sources, currency_view="functional", **args)
    with pytest.raises(Problem, match="all four"):
        bbr.dataset({"billings": []}, currency_view="transaction", **args)
