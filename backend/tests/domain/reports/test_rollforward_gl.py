"""Role-by-role GL matching must not hide offsetting discrepancies."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.reports import rollforward_gl
from erev_api.domain.reports.builders import ReportParams, SourceBinding
from erev_api.domain.reports.builders.contract_balance_rollforward import ContractRollforward
from erev_api.domain.reports.tie_outs import EntityRef


def test_gl_role_comparison_and_incomplete_sources() -> None:
    entity = EntityRef(uuid4(), "US", uuid4(), "USD", "UTC")
    item = ContractRollforward(
        uuid4(),
        "K1",
        None,
        entity.id,
        entity.code,
        "USD",
        {
            "CLOSING": {
                "contract_liability": Decimal(100),
                "contract_asset": Decimal(20),
                "unbilled_receivable": Decimal(0),
            },
        },
    )
    rows = [
        {
            "account_role": role,
            "currency": "USD",
            "source_amount": amount,
            "subledger_amount": amount,
        }
        for role, amount in (
            ("CONTRACT_LIABILITY", "-100"),
            ("CONTRACT_ASSET", "20"),
            ("UNBILLED_RECEIVABLE", "0"),
        )
    ]
    sources = {
        str(entity.id): {
            "id": str(uuid4()),
            "totals": rows,
            "book_code": "ASC606",
            "period_key": "FY2026-P08",
        }
    }
    assert rollforward_gl.compare([entity], [item], sources)["result"] == "PASS"
    # Equal GL/report balances must not mask opposite bridge differences.
    rows[0]["subledger_amount"] = "-90"
    offset = rollforward_gl.compare([entity], [item], sources)
    assert offset["result"] == "FAIL"
    detail = offset["details"][0]
    assert detail["difference"] == "0"
    assert detail["source_subledger"] == "90"
    assert detail["subledger_gl_difference"] == "-10"
    assert detail["report_subledger_difference"] == "10"
    assert detail["bridge_result"] == "FAIL"
    del rows[0]["subledger_amount"]
    missing_bridge = rollforward_gl.compare([entity], [item], sources)
    assert missing_bridge["result"] == "NOT_APPLICABLE"
    detail = missing_bridge["details"][0]
    assert "source_subledger" not in detail
    assert detail["bridge_reason"] == "The GL source has no retained subledger amount."
    rows[0]["subledger_amount"] = "-100"
    rows[0]["source_amount"] = "-110"
    rows[1]["source_amount"] = "10"
    failed = rollforward_gl.compare([entity], [item], sources)
    assert failed["result"] == "FAIL"
    assert failed["details"][0]["period_key"] == "FY2026-P08"
    assert failed["details"][0]["reconciliation_id"] == sources[str(entity.id)]["id"]
    assert failed["expected"] == failed["actual"]  # aggregate alone would falsely pass
    assert [row["difference"] for row in failed["details"]] == ["-10", "10", "0"]
    assert rollforward_gl.compare([entity], [item], {})["result"] == "NOT_APPLICABLE"
    assert (
        rollforward_gl.compare([entity], [replace(item, currency="EUR")], sources)["result"]
        == "NOT_APPLICABLE"
    )

    # Missing GL evidence stays traceable and never becomes a zero balance.
    rows[0]["source_amount"] = "-100"
    rows[1]["source_amount"] = "20"
    rows.pop(0)
    missing = rollforward_gl.compare([entity], [item], sources)
    assert missing["result"] == "NOT_APPLICABLE"
    detail = missing["details"][0]
    assert detail["reconciliation_id"] == sources[str(entity.id)]["id"]
    assert detail["rollforward"] == "100"
    assert "gl" not in detail and "difference" not in detail
    assert detail["reason"] == "The GL source has no total for this role."
    rows[0]["currency"] = "EUR"
    mismatch = rollforward_gl.compare([entity], [item], sources)["details"][1]
    assert mismatch["period_key"] == "FY2026-P08"
    assert mismatch["reason"] == (
        "The GL source currency differs from the entity functional currency."
    )


@pytest.mark.parametrize("legacy", [True, False])
def test_retained_gl_rebuild_never_reads_current_reconciliation(legacy: bool) -> None:
    from typing import cast

    from sqlalchemy.orm import Session

    now = datetime(2026, 10, 20, tzinfo=UTC)
    entity = EntityRef(uuid4(), "US", uuid4(), "USD", "UTC")
    sources = {
        str(entity.id): {
            "id": str(uuid4()),
            "totals": [
                {
                    "account_role": role,
                    "currency": "USD",
                    "source_amount": "0",
                    **({} if legacy else {"subledger_amount": "0"}),
                }
                for role in rollforward_gl.ROLES
            ],
        }
    }
    params = ReportParams(
        "contract_balance_rollforward",
        1,
        {},
        (entity.id,),
        now,
        binding=SourceBinding(
            now,
            {},
            {},
            frozenset(),
            evidence={
                (rollforward_gl.LEGACY_EVIDENCE if legacy else rollforward_gl.EVIDENCE): sources
            },
        ),
    )

    class NoReads:
        def execute(self, *args: object) -> None:
            raise AssertionError("retained rebuild must not read live GL sources")

    result = rollforward_gl.build(
        cast(Session, NoReads()),
        params,
        entities=[entity],
        periods={},
        items=[],
        book_code="ASC606",
        contract_id=None,
    )
    assert result["result"] == "PASS"

    assert ("source_subledger" in result["details"][0]) is not legacy
