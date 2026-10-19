"""Child dataset admission preserves typed values and rejects inconsistent sources."""

import hashlib
from datetime import date
from uuid import UUID

import pytest
from erev_api.domain.reports.disclosure_plan import ChildSource
from erev_api.domain.reports.disclosure_results import decode
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.outputs.manifest import dataset_bytes
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex


def test_child_json_rebuilds_dates_and_exact_money_and_binds_parameters() -> None:
    data = ReportData(
        (Column("end", "Period end", "date"), Column("amount", "Amount", "money")),
        (
            {
                "row_key": "a",
                "end": date(2026, 9, 30),
                "amount": {"amount": "123.45", "currency": "USD"},
            },
        ),
        {"total": "123.45"},
        ({"code": "TO_TEST", "result": "PASS"},),
    )
    parameters = {"entity_codes": ["US"], "period_key": "FY2026-P09"}
    report = {"code": "contract_balances", "version": 1, "name": "Contract balances"}
    content = dataset_bytes(report, parameters, data)
    row = {
        "report_code": report["code"],
        "report_version": 1,
        "parameters": parameters,
        "row_count": 1,
        "control_totals": data.control_totals,
        "tie_out_results": list(data.tie_out_results),
        "output_sha256": hashlib.sha256(content).hexdigest(),
    }
    source = ChildSource(
        "contract_balances:PERIOD", (2,), "PERIOD", UUID(int=1), UUID(int=2), sha256_hex(parameters)
    )
    assert decode(content, row, source) == data
    with pytest.raises(Problem, match="digest differs"):
        decode(content + b" ", row, source)
    with pytest.raises(Problem, match="inconsistent"):
        decode(content, {**row, "row_count": 2}, source)
    with pytest.raises(Problem, match="digest differs"):
        decode(content, {**row, "parameters": {"entity_codes": ["OTHER"]}}, source)
