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
        stream_version=1, event_type="BILLING_RECORDED",
        payload={"amount": {"amount": "100", "currency": "EUR"}},
        effect_currency="USD", effect_amount=Decimal("-120"),
    )
    (row,) = oop.aggregate([record]).rows
    assert row["event_amount"] == {"amount": "100.00", "currency": "EUR"}
    assert row["revenue_effect"] == {"amount": "120.00", "currency": "USD"}
