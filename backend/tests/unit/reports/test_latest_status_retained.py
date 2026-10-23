"""Original dated contract inputs rebuild figures without a database session."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import RETAINED, ReportParams, SourceBinding
from erev_api.domain.reports.builders import latest_contract_status as latest
from erev_api.problems import Problem


def test_original_cuts_recalculate_and_balances_are_counted_once():
    tenant, entity, version, contract = (UUID(int=i) for i in range(1, 5))
    record = {
        "row": {
            "id": str(UUID(int=5)),
            "contract_version_id": str(version),
            "contract_id": str(contract),
            "contracting_entity_id": str(entity),
            "txn_currency": "USD",
            "contract_external_id": "Original contract",
            "obligation_key": "O1",
            "product_code": "Original product",
            "entity_code": "US",
            "chain_version_no": 2,
            "effective_date": "2026-01-01",
            "remaining_quantity": "2",
            "allocated_amount": "100",
            "remaining_allocation": "80",
        },
        "cut": {
            "revenue": "50",
            "billed": "30",
            "delta": "30",
            "shift": "10",
            "scheduled": "35",
            "awaiting": "5",
            "satisfaction_status": "IN_PROGRESS",
        },
        "balances": ["0", "20"],
    }
    second = deepcopy(record)
    second["row"]["obligation_key"] = "O2"
    retained = {
        "tenant_id": str(tenant),
        "entity_ids": [str(entity)],
        "selection": {"book": None, "as_of": None, "contract_external_id": None},
        "as_of": "2026-06-30",
        "inputs": [record, second],
    }
    at = datetime(2026, 7, 1, tzinfo=UTC)
    params = ReportParams(
        report_code=latest.CODE,
        report_version=1,
        entity_ids=(entity,),
        parameters={},
        known_at=at,
        binding=SourceBinding(
            cutoff=at,
            versions={},
            labels={},
            row_keys=frozenset(),
            strategy=RETAINED,
            evidence={latest.EVIDENCE: retained},
        ),
    )
    uow = SimpleNamespace(principal=SimpleNamespace(tenant_id=tenant))
    data = latest.build(uow, params)
    assert data.columns == latest.COLUMNS
    assert "combined_components" not in data.rows[0]
    assert data.rows[0]["allocated_amount"]["amount"] == "90.00"
    assert data.rows[0]["remaining_allocation"]["amount"] == "40.00"
    assert data.control_totals["contract_asset_and_unbilled"] == {"USD": "20.00"}
    assert data.control_totals["revenue_cum"] == {"USD": "100.00"}
    record["combination"] = {
        "scope_flag": "IN_SCOPE_606",
        "combined_components": "L1; S1",
        "combination_judgements": "JDG-1",
        "combination_rationales": "JDG-1: Original approved rationale",
        "combination_evidence_status": "Retained calculation evidence",
    }
    combined = latest.build(uow, params)
    assert combined.rows[0]["combined_components"] == "L1; S1"
    assert combined.rows[1]["combined_components"] is None
    assert combined.control_totals == data.control_totals
    assert "combination_rationales" in {column.key for column in combined.columns}
    record["cut"]["shift"] = "15"
    assert latest.build(uow, params).rows[0]["remaining_allocation"]["amount"] == "35.00"
    for invalid in (replace(params, entity_ids=()), replace(params, parameters={"book": "IFRS15"})):
        with pytest.raises(Problem):
            latest.build(uow, invalid)
    with pytest.raises(Problem):
        latest.build(SimpleNamespace(principal=SimpleNamespace(tenant_id=entity)), params)
