"""Destination presentation uses original allocations without cross-group netting."""

from dataclasses import replace
from datetime import date
from fractions import Fraction

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.combination_split_balances import calculate
from erev_engine.trace import reevaluate
from tests.engine.test_combination_split import successive_split_bundle


def billed_split():
    value, first, _ = successive_split_bundle()
    billed = bundles.event(
        first.contract_key,
        4,
        "BILLING_RECORDED",
        date(2026, 10, 1),
        {
            "invoice_number": "SPLIT-INVOICE",
            "line_external_id": "1",
            "obligation_key": "POB-01",
            "amount": "400000",
            "issue_date": "2026-10-01",
            "is_cancellable": False,
        },
        obligation_keys=["POB-01"],
        record_seq=102,
    )
    return replace(
        value,
        events=tuple(
            sorted(
                (*value.events, billed), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
            )
        ),
    )


def test_destination_balances_do_not_offset_separated_members():
    value = billed_split()
    digest = value.sha256()
    result = calculate(value, book_code="ASC606", as_of=date(2026, 10, 31))
    assert [r.destination for r in result] == ["LEFT", "NEW", "REST"]
    measures = {r.destination: {t.measure: t.value for t in r.presentation} for r in result}
    assert measures["LEFT"]["contract_liability"] > 0
    assert measures["LEFT"]["contract_asset"] == 0
    assert measures["NEW"]["contract_asset"] > 0
    assert measures["REST"]["contract_asset"] > 0
    assert measures["NEW"]["contract_liability"] == measures["REST"]["contract_liability"] == 0
    original = compute(value).books[0]
    original_rows = [r for r in original.balances if r.period_key == "FY2026-P10"]

    def net(m):
        return m["contract_liability"] - m["contract_asset"] - m["unbilled_receivable"]

    assert sum(net(m) for m in measures.values()) == sum(
        r.columns["contract_liability_txn"]
        - r.columns["contract_asset_txn"]
        - r.columns["unbilled_receivable_txn"]
        for r in original_rows
    )
    assert sum(m["contract_liability"] for m in measures.values()) > sum(
        r.columns["contract_liability_txn"] for r in original_rows
    )
    for group in result:
        nodes = {n.id: n for n in group.trace.nodes}
        assert reevaluate(group.trace) == {n.id: n.value for n in group.trace.nodes}
        for target in group.presentation:
            assert Fraction(nodes[target.node_id].value) * 100 == target.value
            assert target.value == sum(
                t.value
                for t in group.member_balances
                if t.measure == target.measure and t.entity == target.entity
            )
    assert value.sha256() == digest
    assert calculate(value, book_code="ASC606", as_of=date(2026, 10, 31)) == result


def test_destination_balance_date_precedes_later_split():
    value = billed_split()
    before = calculate(value, book_code="ASC606", as_of=date(2026, 9, 30))
    assert [r.destination for r in before] == ["LEFT", "REST"]
    assert before[1].member_contract_keys == ("SPLIT-B", "SPLIT-C")
    assert all(
        t.value == 0 for r in before for t in r.presentation if t.measure == "contract_liability"
    )


@pytest.mark.parametrize(
    "day, message",
    [
        (date(2026, 8, 31), "effective retained split"),
        (date(2026, 10, 16), "common contracting-period end"),
    ],
)
def test_destination_balance_requires_dated_scope(day, message):
    with pytest.raises(ValueError, match=message):
        calculate(billed_split(), book_code="ASC606", as_of=day)
