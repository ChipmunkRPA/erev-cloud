"""Comparison rows use semantic identity across changing populations and currency suffixes."""

from dataclasses import replace

import pytest
from erev_api.domain.reports.disclosure_comparison import compare
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem

COLUMNS = (
    Column("section", "Section", "integer"),
    Column("line_code", "Line code", "code"),
    Column("line_label", "Line", "text"),
    Column("contract_external_id", "Contract", "code"),
    Column("currency", "Currency", "code"),
    Column("rpo", "RPO", "money"),
)


def row(key: str, currency: str, amount: str) -> dict:
    return {
        "row_key": key,
        "section": 1,
        "line_code": "OPENING",
        "line_label": "Opening",
        "contract_external_id": None,
        "currency": currency,
        "rpo": {"amount": amount, "currency": currency},
    }


def test_currency_population_drift_and_missing_rows_never_become_zero() -> None:
    period = ReportData(COLUMNS, (row("OPENING", "USD", "10.00"),), {})
    quarter = ReportData(
        COLUMNS, (row("OPENING:EUR", "EUR", "5.00"), row("OPENING:USD", "USD", "30.00")), {}
    )
    result = compare("rpo_rollforward", period, quarter)
    usd, eur = result.rows
    assert usd["period:rpo"]["amount"] == "10.00"
    assert usd["quarter:rpo"]["amount"] == "30.00"
    assert eur["period:rpo"] is None and eur["period_present"] is False
    assert eur["quarter:rpo"] == {"amount": "5.00", "currency": "EUR"}
    assert len({item["row_key"] for item in result.rows}) == 2
    with pytest.raises(Problem, match="duplicated"):
        compare("rpo_rollforward", replace(period, rows=period.rows * 2), quarter)


def test_disaggregation_uses_range_total_and_retains_different_labels() -> None:
    base = tuple(
        Column(key, key, "code")
        for key in ("dimension_code", "dimension_value", "timing_code", "currency")
    ) + (Column("label", "Label", "text"), Column("total", "Total", "money"))
    dimensions = {
        "row_key": "product",
        "dimension_code": "product",
        "dimension_value": "A",
        "timing_code": "OVER_TIME",
        "currency": "USD",
    }

    def money(value: str) -> dict[str, str]:
        return {"amount": value, "currency": "USD"}

    period = ReportData(
        (*base, Column("period:P02", "February", "money")),
        (
            {
                **dimensions,
                "label": "Period label",
                "total": money("10.00"),
                "period:P02": money("10.00"),
            },
        ),
        {},
    )
    quarter = ReportData(
        (
            *base,
            Column("period:P01", "January", "money"),
            Column("period:P02", "February", "money"),
        ),
        (
            {
                **dimensions,
                "label": "Quarter label",
                "total": money("30.00"),
                "period:P01": money("20.00"),
                "period:P02": money("10.00"),
            },
        ),
        {},
    )
    result = compare("disaggregation", period, quarter)
    assert result.rows[0]["period:total"] == money("10.00")
    assert result.rows[0]["quarter:total"] == money("30.00")
    assert result.rows[0]["period:label"] == "Period label"
    assert not any("P01" in column.key or "P02" in column.key for column in result.columns)
