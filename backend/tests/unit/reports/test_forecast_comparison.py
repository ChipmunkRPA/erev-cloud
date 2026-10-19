from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.reports.forecast_comparison import Revenue, compare
from erev_api.problems import Problem

ENTITY = UUID(int=1)
NOW = datetime(2026, 10, 19, tzinfo=UTC)


def revenue(contract: str, amount: str, currency: str = "USD", period: str = "P10") -> Revenue:
    return Revenue(ENTITY, contract, "Services", period, currency, Decimal(amount))


def report(forecast: list[Revenue], actual: list[Revenue], **kwargs):
    return compare(
        forecast,
        actual,
        horizon=["P9", "P10", "P11"],
        entity_ids=[ENTITY],
        actuals_known_at=NOW,
        **kwargs,
    )


def test_union_sign_zero_base_and_currency_totals():
    data = report(
        [revenue("C1", "100"), revenue("C1", "10", "EUR"), revenue("C2", "30")],
        [revenue("C1", "80"), revenue("C1", "5", "EUR"), revenue("C3", "40")],
    )
    rows = {r["row_key"]: r for r in data.rows}
    assert rows["contract:C1:P10:USD"]["variance"]["amount"] == "-20.00"
    assert rows["contract:C1:P10:EUR"]["variance_percent"] == "-50.00"
    assert rows["contract:C2:P10"]["actual_revenue"]["amount"] == "0.00"
    assert rows["contract:C3:P10"]["variance_percent"] is None
    assert rows["TOTAL:USD"]["variance"]["amount"] == "-10.00"
    assert rows["TOTAL:USD"]["variance_percent"] == "-7.69"


def test_empty_actuals_and_zero_net_postings_are_different():
    empty = report([revenue("C1", "100")], [])
    assert not empty.rows
    assert empty.control_totals["empty_title"] == "No actuals yet for the forecast horizon"
    posted = report([revenue("C1", "100")], [revenue("C1", "20"), revenue("C1", "-20")])
    assert posted.rows[0]["variance"]["amount"] == "-100.00"
    assert posted.control_totals["actuals_known_at"] == NOW.isoformat()


def test_selected_horizon_scopes_and_category_aggregation():
    data = report(
        [revenue("C1", "100"), revenue("C2", "25"), revenue("C1", "500", period="P9")],
        [
            revenue("C1", "80"),
            revenue("C2", "50"),
            Revenue(UUID(int=2), "C1", "Services", "P10", "USD", Decimal("999")),
        ],
        row_dimension="REVENUE_CATEGORY",
        from_period_key="P10",
        to_period_key="P10",
    )
    assert data.rows[0]["row_key"] == "revenue_category:Services:P10"
    assert data.rows[0]["variance"]["amount"] == "5.00"
    assert data.rows[0]["variance_percent"] == "4.00"
    for first, last in [("P8", "P10"), ("P11", "P9")]:
        with pytest.raises(Problem, match="Choose periods inside"):
            report([], [], from_period_key=first, to_period_key=last)


def test_nonfinite_values_are_refused():
    with pytest.raises(Problem, match="Incomplete forecast comparison source"):
        report([revenue("C1", "NaN")], [revenue("C1", "10")])


def test_unassigned_category_does_not_merge_with_named_category():
    data = report(
        [
            Revenue(ENTITY, "C1", None, "P10", "USD", Decimal("100")),
            Revenue(ENTITY, "C2", "Unassigned", "P10", "USD", Decimal("50")),
        ],
        [Revenue(ENTITY, "C1", None, "P10", "USD", Decimal("80"))],
        row_dimension="REVENUE_CATEGORY",
    )
    rows = {r["row_key"]: r for r in data.rows}
    assert rows["revenue_category::P10"]["variance"]["amount"] == "-20.00"
    assert rows["revenue_category:Unassigned:P10"]["forecast_revenue"]["amount"] == "50.00"
