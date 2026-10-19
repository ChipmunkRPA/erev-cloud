"""Forecast sections preserve billing signs, period-end stocks and journal currencies."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.reports import forecast_sections as sections
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.outputs import ReportData
from erev_api.domain.reports.tie_outs import PeriodRef
from erev_api.problems import Problem


def periods() -> tuple[PeriodRef, ...]:
    return (
        PeriodRef(
            uuid4(), "FY2026-P10", "Oct 2026", 2026, 10, 4, date(2026, 10, 1), date(2026, 10, 31)
        ),
        PeriodRef(
            uuid4(), "FY2026-P11", "Nov 2026", 2026, 11, 4, date(2026, 11, 1), date(2026, 11, 30)
        ),
    )


def test_billing_net_credits_and_currency_totals() -> None:
    horizon = periods()
    contract, entity = uuid4(), uuid4()
    rows = tuple(
        Contribution("contract_event", uuid4(), contract, entity, day, currency, Decimal(amount))
        for day, currency, amount in (
            (date(2026, 10, 2), "USD", "120.25"),
            (date(2026, 10, 4), "USD", "-20.10"),
            (date(2026, 11, 4), "USD", "30.00"),
            (date(2026, 10, 4), "JPY", "500"),
            (date(2026, 12, 4), "USD", "999"),
        )
    )
    result = sections.billing(rows, periods=horizon, contract_labels={contract: "C:ONE"})
    usd = next(r for r in result.rows if r["row_key"] == "TOTAL:USD")
    assert usd["period:FY2026-P10"] == {"amount": "100.15", "currency": "USD"}
    assert usd["total"] == {"amount": "130.15", "currency": "USD"}
    assert next(r for r in result.rows if r["row_key"] == "TOTAL:JPY")["total"] == {
        "amount": "500",
        "currency": "JPY",
    }
    assert len(result.rows) == 4 and not result.tie_out_results
    with pytest.raises(Problem, match="retained label"):
        sections.billing(rows, periods=horizon, contract_labels={})


def test_balances_keep_each_period_stock_and_skip_input_totals() -> None:
    def dataset(amount: str) -> ReportData:
        money = {"amount": amount, "currency": "USD"}
        row = {
            "row_key": "contract:C1:E1",
            "entity_code": "E1",
            "currency": "USD",
            **{key: money for key in sections.BALANCES},
        }
        return ReportData(
            columns=(), rows=(row, {**row, "row_key": "TOTAL:USD"}), control_totals={}
        )

    result = sections.balances(
        ((date(2026, 10, 31), dataset("100.00")), (date(2026, 11, 30), dataset("70.00")))
    )
    assert len(result.rows) == 4
    totals = result.control_totals["balances_by_period_currency"]
    assert totals["2026-10-31:USD"]["contract_liability"]["amount"] == "100.00"
    assert totals["2026-11-30:USD"]["contract_liability"]["amount"] == "70.00"
    with pytest.raises(Problem, match="supplied twice"):
        sections.balances(
            ((date(2026, 10, 31), dataset("100")), (date(2026, 10, 31), dataset("70")))
        )


def test_journal_preview_preserves_debits_credits_and_stored_fx_basis() -> None:
    data = ReportData(
        columns=(),
        rows=tuple(
            {
                "row_key": str(i),
                "period_key": period,
                "account_role": role,
                "txn_currency": "EUR",
                "amount_txn": amount,
                "functional_currency": "USD",
                "amount_functional": functional,
            }
            for i, (period, role, amount, functional) in enumerate(
                (
                    ("FY2026-P10", "CONTRACT_ASSET", "100.00", "110.00"),
                    ("FY2026-P10", "REVENUE", "-100.00", "-110.00"),
                    ("FY2026-P10", "REVENUE", "10.00", "11.00"),
                    ("FY2026-P10", "CONTRACT_ASSET", "-10.00", "-11.00"),
                    ("FY2026-P12", "REVENUE", "-999.00", "-999.00"),
                )
            )
        ),
        control_totals={},
    )
    result = sections.journals(data, periods=periods(), currency_view="functional")
    total = result.rows[-1]
    assert total["debit"] == total["credit"] == {"amount": "121.00", "currency": "USD"}
    revenue = next(r for r in result.rows if r["account_role"] == "REVENUE")
    assert revenue["debit"]["amount"] == "11.00" and revenue["credit"]["amount"] == "110.00"
    with pytest.raises(Problem, match="stored currency basis"):
        sections.journals(data, periods=periods(), currency_view="reporting")
