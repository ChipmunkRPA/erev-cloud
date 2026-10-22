"""Gross/delta calculations rebuild from saved book amounts without a live session."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import RETAINED, ReportParams, SourceBinding
from erev_api.domain.reports.builders import legacy_je_summary as report
from erev_api.problems import Problem


@pytest.mark.parametrize("mode", ["GROSS", "DELTA"])
def test_rebuild_original_book_amounts_and_currency_totals(mode):
    tenant, entity = UUID(int=1), UUID(int=2)
    rows = []
    for code, currency, gross, legacy in (
        ("A", "USD", "100", "-30"),
        ("B", "USD", "50", "-10"),
        ("C", "EUR", "20", "-5"),
    ):
        for book, amount in (("ASC606", gross), ("LEGACY", legacy)):
            if book == "LEGACY" and mode == "GROSS":
                continue
            rows.append(
                {
                    "book_code": book,
                    "entity_code": code,
                    "legacy_key": "same",
                    "account": "1000",
                    "txn_currency": currency,
                    "amount": amount,
                }
            )
    retained = {
        "tenant_id": str(tenant),
        "entity_ids": [str(entity)],
        "selection": {"book": None, "mode": mode, "from_date": None, "to_date": None},
        "entity_codes": ["A", "B", "C"],
        "book": "ASC606",
        "mode": mode,
        "from_date": "2026-01-01",
        "to_date": "2026-01-31",
        "inputs": rows,
    }
    at = datetime(2026, 2, 1, tzinfo=UTC)
    params = ReportParams(
        report_code=report.CODE,
        report_version=1,
        entity_ids=(entity,),
        parameters={"mode": mode},
        known_at=at,
        binding=SourceBinding(
            cutoff=at,
            versions={},
            labels={},
            row_keys=frozenset(),
            strategy=RETAINED,
            evidence={report.EVIDENCE: retained},
        ),
    )
    uow = SimpleNamespace(principal=SimpleNamespace(tenant_id=tenant))
    data = report.build(uow, params)
    assert data.control_totals["total_debit"] == (
        {"USD": "150.00", "EUR": "20.00"} if mode == "GROSS" else {"USD": "110.00", "EUR": "15.00"}
    )
    keys = [row["row_key"] for row in data.rows]
    assert "item:same:1000:USD:A" in keys and "item:same:1000:USD:B" in keys
    assert len(keys) == len(set(keys))
    rows[0]["amount"] = "-100"
    changed = report.build(uow, params)
    assert changed.control_totals["total_credit"]["USD"] == (
        "100.00" if mode == "GROSS" else "130.00"
    )
    assert changed.control_totals["total_debit"]["USD"] == ("50.00" if mode == "GROSS" else "40.00")
    for invalid in (replace(params, entity_ids=()), replace(params, parameters={"mode": "other"})):
        with pytest.raises(Problem):
            report.build(uow, invalid)
    with pytest.raises(Problem):
        report.build(SimpleNamespace(principal=SimpleNamespace(tenant_id=entity)), params)
