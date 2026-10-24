from datetime import date
from decimal import Decimal as D
from fractions import Fraction as F
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.domain.reports import opening_agent_contract as contract
from erev_api.domain.reports import opening_agent_sources as agent
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
from erev_api.problems import Problem

A, B, ENTITY, PERIOD = (UUID(int=i) for i in range(1, 5))
START = date(2026, 4, 1)


def row(owner):
    return NS(
        contract_id=owner,
        entity_id=ENTITY,
        version_id=UUID(int=9),
        external_id=str(owner),
        entity_code="US",
        customer_name="Customer",
    )


def entry(owner, amount, index):
    return Entry(
        order=(index,),
        flow=Flow(D(amount), True),
        subject_key=str(owner),
        line_id=UUID(int=10 + index),
        period_id=PERIOD,
    )


def fixture(monkeypatch, net="40", eligible="20"):
    income = entry(A, net, 1)
    opening = entry(A, eligible, 1)
    found = agent.Result(
        (income,), {str(A): D(eligible)}, {str(A): {"lines": []}}, {income.line_id}, (opening,)
    )

    def read(uow, selected, *a, **k):
        assert k["allowed_source_contracts"] == {A, B}
        return found if selected.contract_id == A else None

    monkeypatch.setattr(agent, "read", read)
    return income


def test_contract_fifo_has_one_group_cap_not_per_obligation_caps(monkeypatch):
    income = fixture(monkeypatch)
    principal = entry(B, "120", 2)
    proof = NS(
        components=(),
        delta=NS(
            amount=F(-120),
            source_ids=(UUID(int=8),),
            movements=(
                NS(
                    contract_id=A,
                    layer_key="opening",
                    movement_kind="LIABILITY_LAYER_CONSUMED",
                    amount=F(-120),
                ),
            ),
        ),
        layer_dates=((A, "opening", date(2026, 3, 1)),),
        paid_line_ids=(),
        evidence=(),
    )
    monkeypatch.setattr(
        contract.revenue_attribution, "for_control", lambda *a, **k: (UUID(int=20), proof)
    )
    result = contract.calculate(
        None,
        [row(A), row(B)],
        {(A, ENTITY): [income], (B, ENTITY): [principal]},
        {},
        start=START,
        opening=D(100),
        consumed=D(200),
        view="transaction",
    )
    assert result.recognized == D(160)
    assert result.relief == D(100)
    assert result.evidence["eligible"] == "140"
    shown = contract.row([row(A), row(B)], "group", "USD", D(100), result)
    assert shown["row_key"] == "combined:group"
    assert shown["contract_external_id"] is None
    assert shown["_opening_source"]["contracts"] == sorted([str(A), str(B)])


def test_original_source_total_can_limit_contract_eligibility(monkeypatch):
    income = fixture(monkeypatch)
    result = contract.calculate(
        None,
        [row(A), row(B)],
        {(A, ENTITY): [income]},
        {},
        start=START,
        opening=D(100),
        consumed=D(100),
        view="functional",
    )
    assert result.recognized == D(40)
    assert result.relief == D(20)
    slices, net = contract.period_slices(
        result,
        periods=[NS(id=PERIOD, key="P04")],
        opening=D(100),
        consumption={PERIOD: D(100)},
    )
    assert slices == {PERIOD: D(20)}
    assert net == {PERIOD: D(40)}


def test_unrelated_original_owner_is_rejected(monkeypatch):
    income = fixture(monkeypatch)
    proof = NS(
        components=(),
        delta=NS(
            amount=F(-120),
            source_ids=(),
            movements=(
                NS(
                    contract_id=UUID(int=99),
                    layer_key="x",
                    movement_kind="LIABILITY_LAYER_CONSUMED",
                    amount=F(-120),
                ),
            ),
        ),
        layer_dates=(),
        paid_line_ids=(),
        evidence=(),
    )
    monkeypatch.setattr(contract.revenue_attribution, "for_control", lambda *a, **k: (A, proof))
    with pytest.raises(Problem):
        contract.calculate(
            None,
            [row(A), row(B)],
            {(A, ENTITY): [income], (B, ENTITY): [entry(B, "120", 2)]},
            {},
            start=START,
            opening=D(100),
            consumed=D(200),
            view="transaction",
        )


def test_older_bindings_do_not_gain_contract_fifo_behavior():
    assert not contract.enabled(NS(binding=NS(evidence={agent.KEY: {}})))
    assert contract.enabled(NS(binding=None))
    assert contract.enabled(NS(binding=NS(evidence={contract.KEY: {}})))


def test_reporting_intermediate_consumption_cannot_use_range_zero_shortcut(monkeypatch):
    fixture(monkeypatch)
    old = agent.read
    flags = []

    def read(*a, **k):
        flags.append(k["classify_opening"])
        return old(*a, **k)

    monkeypatch.setattr(agent, "read", read)
    for allowed in (True, False):
        result = contract.calculate(
            None,
            [row(A), row(B)],
            {},
            {},
            start=START,
            opening=D(100),
            consumed=D(-10),
            view="functional",
            allow_zero_consumption=allowed,
        )
        assert result.relief == 0
    assert flags == [False, False, True, True]


def test_cell_explanation_identifies_contract_cap_and_original_principal_sources():
    from erev_api.domain.reports import opening_relief_cells as cells

    source = {
        "contracts": [str(A), str(B)],
        "currency_view": "functional",
        "currency": "GBP",
        "translation_rates": [],
        "values": {key: {"amount": "20", "currency": "GBP"} for key in cells.COLUMNS},
        "pob": {
            "basis": "CONTRACT_FIFO_ORIGINAL_NET_SOURCES",
            "opening_cap": "100",
            "members": {
                str(B): {
                    "principal_sources": {
                        "control": {
                            "net_line": "net",
                            "net_income": "30",
                            "opening_income": "20",
                            "sources": ["original-layer"],
                        }
                    },
                }
            },
        },
    }
    text = "\n".join(cells._details(source))
    assert "Contract FIFO: one group cap" in text
    assert "no per-obligation cap or member allocation" in text
    assert "Principal control line: control; net line: net" in text
    assert "original opening-source income: 20 GBP; sources: original-layer" in text
