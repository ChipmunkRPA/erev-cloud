from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.forecast.history import SavedForecast
from erev_api.domain.reports.forecast_dimensions import forecast_rows
from erev_api.domain.reports.forecast_saved import SavedRevenue
from erev_api.problems import Problem


def saved(category=True):
    forecast = SavedForecast(
        UUID(int=1),
        UUID(int=2),
        UUID(int=3),
        datetime(2026, 10, 19, tzinfo=UTC),
        None,
        UUID(int=4),
        {"parameters": {"entity_ids": [str(UUID(int=5))], "horizon_periods": ["P10", "P11"]}},
    )
    row = {
        "row_key": "obligation:C1:O1",
        "contract_external_id": "C1",
        "entity_code": "US",
        "period:P10": {"amount": "100.00", "currency": "USD"},
        "period:P11": {"amount": "-20.00", "currency": "USD"},
        **({"revenue_category": None} if category else {}),
    }
    return SavedRevenue(
        forecast,
        UUID(int=6),
        "a" * 64,
        {"rows": [row, {"row_key": "TOTAL:USD"}]},
        {"US": UUID(int=5)},
    )


def test_saved_entities_periods_and_credit_signs_without_total_duplication():
    result = forecast_rows(saved(), require_category=True)
    assert len(result) == 2
    assert [r.amount for r in result] == [Decimal("100.00"), Decimal("-20.00")]
    assert all(r.entity_id == UUID(int=5) and r.revenue_category is None for r in result)


def test_legacy_missing_category_is_explicit_and_contract_view_still_works():
    assert len(forecast_rows(saved(False), require_category=False)) == 2
    with pytest.raises(Problem):
        forecast_rows(saved(False), require_category=True)


@pytest.mark.parametrize("bad", ["entity", "duplicate", "money"])
def test_incomplete_or_ambiguous_forecast_rows_are_refused(bad):
    source = saved()
    if bad == "entity":
        source.revenue["rows"][0]["entity_code"] = "unknown"
    elif bad == "duplicate":
        source.revenue["rows"].append(source.revenue["rows"][0])
    else:
        source.revenue["rows"][0]["period:P10"]["amount"] = "NaN"
    with pytest.raises(Problem):
        forecast_rows(source, require_category=False)


def actual(category=True):
    from erev_api.domain.reports.forecast_actuals_saved import Actuals

    parent = saved().forecast
    row = {
        "id": "line",
        "entity_id": str(UUID(int=5)),
        "period_key": "P10",
        "contract_label_known": True,
        "contract_external_id": "C1",
        "revenue_category_known": category,
        "revenue_category": None,
        "txn_currency": "USD",
        "debit_txn": "20.00",
        "credit_txn": "100.00",
        "functional_currency": "EUR",
        "debit_functional": "18.00",
        "credit_functional": "90.00",
    }
    return Actuals(parent, UUID(int=7), "b" * 64, (row,))


def test_actual_signed_amounts_use_saved_currency_basis():
    from erev_api.domain.reports.forecast_dimensions import actual_rows

    source = actual()
    assert actual_rows(source, require_category=True)[0].amount == Decimal("80.00")
    source.forecast.run["parameters"]["currency_view"] = "functional"
    result = actual_rows(source, require_category=True)[0]
    assert result.amount == Decimal("72.00")
    assert result.currency == "EUR"


def test_unknown_actual_category_cannot_be_treated_as_unassigned():
    from erev_api.domain.reports.forecast_dimensions import actual_rows

    source = actual(False)
    assert actual_rows(source, require_category=False)[0].contract_external_id == "C1"
    with pytest.raises(Problem):
        actual_rows(source, require_category=True)
    source.rows[0]["contract_label_known"] = False
    with pytest.raises(Problem):
        actual_rows(source, require_category=False)
