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
