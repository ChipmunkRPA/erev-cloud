"""Posted effects preserve their accounting basis and original lineage."""

from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import out_of_period_register as oop
from erev_api.problems import Problem


def line(**changes):
    return {
        "line_id": UUID(int=1),
        "origin_period_key": "FY2026-P01",
        "posting_period_key": "FY2026-P02",
        "txn_currency": "USD",
        "amount_txn": "0",
        "functional_currency": "EUR",
        "amount_functional": "-12.34",
        "trigger": "FX_REPUBLISH",
        "computation_id": UUID(int=2),
        "cause_event_count": 0,
        "account_role": "REVENUE",
        "contract_external_id": "C",
        **changes,
    }


def test_functional_only_republication_retains_zero_transaction_proof():
    raw = line()
    effect = oop.functional_amount(raw, "EUR")
    record = {**raw, "effect_amount": effect, "effect_currency": "EUR"}
    (row,) = oop.aggregate([record]).rows
    assert row["attribution_kind"] == "TRIGGER"
    assert row["revenue_effect"] == {"amount": "12.34", "currency": "EUR"}
    assert oop.aggregate([raw]).rows[0]["revenue_effect"]["amount"] == "0.00"
    with pytest.raises(Problem):
        oop.aggregate([{**record, "amount_txn": "1"}])


def test_same_attribution_in_different_functional_currencies_never_combines():
    result = oop.aggregate(
        [
            line(effect_currency="EUR", effect_amount=Decimal("-12.34")),
            line(effect_currency="GBP", effect_amount=Decimal("-20.00")),
        ]
    )
    assert result.line_count == 2
    assert len({row["row_key"] for row in result.rows}) == 2
    assert {row["currency"]: row["revenue_effect"]["amount"] for row in result.rows} == {
        "EUR": "12.34",
        "GBP": "20.00",
    }


@pytest.mark.parametrize("changes", [{"functional_currency": "GBP"}, {"amount_functional": None}])
def test_posted_functional_evidence_is_required(changes):
    with pytest.raises(Problem):
        oop.functional_amount(line(**changes), "EUR")


def test_converted_effect_keeps_original_event_amount():
    record = line(
        stream_version=1,
        event_type="BILLING_RECORDED",
        payload={"amount": {"amount": "100", "currency": "EUR"}},
        effect_currency="USD",
        effect_amount=Decimal("-120"),
    )
    (row,) = oop.aggregate([record]).rows
    assert row["event_amount"] == {"amount": "100.00", "currency": "EUR"}
    assert row["revenue_effect"] == {"amount": "120.00", "currency": "USD"}


@pytest.mark.parametrize("view", ["transaction", "functional", "reporting"])
def test_retained_oop_rebuilds_lineage_and_zero_posting_membership_without_database(view):
    import json
    from dataclasses import replace
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from erev_api.domain.reports.builders import RETAINED, ReportParams, SourceBinding
    from erev_engine.canonical import canonical_bytes

    tenant, entity = UUID(int=20), UUID(int=21)
    event = line(
        stream_version=1,
        event_type="BILLING_RECORDED",
        amount_txn="-50",
        effect_amount="-50",
        effect_currency="USD",
        payload={"amount": {"amount": "100", "currency": "EUR"}},
    )
    fact = {**event, "effect_currency": "USD"}
    selection = {
        key: None for key in ("book", "from_period_key", "to_period_key", "origin_period_key")
    }
    retained = json.loads(
        canonical_bytes(
            {
                "tenant_id": tenant,
                "entity_ids": [entity],
                "currency_view": view,
                "selection": selection,
                "book": "ASC606",
                "records": [event],
                "late_facts": [fact],
            }
        )
    )
    at = datetime(2026, 9, 30, tzinfo=UTC)
    params = ReportParams(
        report_code=oop.CODE,
        report_version=1,
        entity_ids=(entity,),
        parameters={"currency_view": view},
        known_at=at,
        binding=SourceBinding(
            cutoff=at,
            versions={},
            labels={},
            row_keys=frozenset(),
            strategy=RETAINED,
            evidence={oop.EVIDENCE: retained},
        ),
    )
    uow = SimpleNamespace(principal=SimpleNamespace(tenant_id=tenant))
    data = oop.build(uow, params)  # no session: must rebuild from inputs only
    assert len(data.rows) == 1
    assert data.control_totals["revenue_effect_total"] == {"USD": "50.00"}
    retained["records"][0]["effect_amount"] = "-20"
    assert oop.build(uow, params).control_totals["revenue_effect_total"] == {"USD": "20.00"}
    retained["records"] = []
    rebuilt = oop.build(uow, params)
    assert len(rebuilt.rows) == 1  # selected event now contributes its zero-posting row
    assert rebuilt.rows[0]["event_amount"] == {"amount": "100.00", "currency": "EUR"}
    assert rebuilt.control_totals["line_count"] == 0
    assert rebuilt.control_totals["revenue_effect_total"] == {"USD": "0.00"}
    for changed in (
        replace(params, entity_ids=(UUID(int=22),)),
        replace(params, parameters={"currency_view": "invalid"}),
        replace(params, parameters={"currency_view": view, "book": "IFRS15"}),
        replace(params, parameters={"currency_view": view, "origin_period_key": "FY2026-P03"}),
    ):
        with pytest.raises(Problem):
            oop.build(uow, changed)
    with pytest.raises(Problem):
        oop.build(SimpleNamespace(principal=SimpleNamespace(tenant_id=UUID(int=22))), params)
