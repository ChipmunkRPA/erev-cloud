from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.reports.forecast_comparison_inputs import rebuild
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex


def test_rebuild_recalculates_facts_and_rejects_changed_binding_scope():
    selection = {"row_dimension": "CONTRACT", "from_period_key": None, "to_period_key": None}
    row = {
        "entity_id": str(UUID(int=3)),
        "contract_external_id": "C1",
        "revenue_category": "Service",
        "period_key": "P10",
        "currency": "USD",
        "amount": "100.00",
    }
    facts = {
        "schema_version": 1,
        "tenant_id": str(UUID(int=1)),
        "forecast_run_id": str(UUID(int=2)),
        "entity_ids": [str(UUID(int=3))],
        "book_code": "ASC606",
        "currency_view": "transaction",
        "actuals_cutoff": "2026-10-19T00:00:00+00:00",
        "horizon_periods": ["P10"],
        "selection": selection,
        "forecast_rows": [row],
        "actual_rows": [dict(row, amount="80.00")],
    }
    args = dict(
        expected_sha256=sha256_hex(facts),
        tenant_id=UUID(int=1),
        forecast_run_id=UUID(int=2),
        entity_ids=(UUID(int=3),),
        book_code="ASC606",
        currency_view="transaction",
        selection=selection,
        known_at=datetime(2026, 10, 20, tzinfo=UTC),
    )
    data = rebuild(facts, **args)
    assert data.rows[0]["variance"]["amount"] == "-20.00"
    assert data.rows[0]["variance_percent"] == "-20.00"
    with pytest.raises(Problem):
        rebuild(facts, **dict(args, tenant_id=UUID(int=4)))
    with pytest.raises(Problem):
        rebuild(facts, **dict(args, currency_view="functional"))
    facts["actual_rows"][0]["amount"] = "90.00"
    with pytest.raises(Problem):
        rebuild(facts, **args)
