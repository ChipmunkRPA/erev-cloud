from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.forecast.history import SavedForecast
from erev_api.domain.reports.forecast_actuals_saved import selected_rows

SAVED = SavedForecast(
    UUID(int=1),
    UUID(int=2),
    UUID(int=3),
    datetime(2026, 10, 19, tzinfo=UTC),
    datetime(2026, 10, 20, tzinfo=UTC),
    UUID(int=4),
    {"parameters": {"book_code": "ASC606", "entity_ids": ["one"], "horizon_periods": ["P10"]}},
)


def document():
    rows = [
        {
            "id": str(i),
            "entity_id": entity,
            "period_key": period,
            "book_code": "ASC606",
            "created_at": "2026-10-18T00:00:00+00:00",
            "acknowledged_at": "2026-10-19T00:00:00+00:00",
            "run_state_at_cutoff": "acknowledged",
            "credit_txn": "100.00",
        }
        for i, (entity, period) in enumerate([("one", "P10"), ("two", "P10"), ("one", "P11")])
    ]
    return {
        "schema_version": 1,
        "tenant_snapshot_id": str(SAVED.actuals_snapshot_id),
        "books": {
            "ASC606": {
                "schema_version": 1,
                "source_tenant_id": str(SAVED.source_tenant_id),
                "known_at": SAVED.actuals_cutoff.isoformat(),
                "book_code": "ASC606",
                "entity_ids": ["one", "two"],
                "rows": rows,
            },
            "IFRS15": {"rows": [{"private": "other-book"}]},
        },
    }


def test_only_selected_book_entities_and_horizon_leave_capture():
    rows = selected_rows(document(), SAVED, ["one", "two"])
    assert len(rows) == 1
    assert rows[0]["id"] == "0"
    assert rows[0]["credit_txn"] == "100.00"


@pytest.mark.parametrize(
    "field,value",
    [
        ("entity_id", "unknown"),
        ("book_code", "IFRS15"),
        ("acknowledged_at", "2026-10-20T00:00:00+00:00"),
        ("run_state_at_cutoff", "cancelled"),
    ],
)
def test_invalid_rows_in_retained_population_are_refused(field, value):
    data = document()
    data["books"]["ASC606"]["rows"][1][field] = value
    with pytest.raises(ValueError):
        selected_rows(data, SAVED, ["one", "two"])


def test_wrong_snapshot_duplicate_lines_and_missing_scope_are_refused():
    data = document()
    data["tenant_snapshot_id"] = str(UUID(int=99))
    with pytest.raises(ValueError):
        selected_rows(data, SAVED, ["one", "two"])
    data = document()
    data["books"]["ASC606"]["rows"].append(deepcopy(data["books"]["ASC606"]["rows"][0]))
    with pytest.raises(ValueError):
        selected_rows(data, SAVED, ["one", "two"])
    with pytest.raises(ValueError):
        selected_rows(document(), SAVED, ["two"])
