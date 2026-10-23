"""Opening-consumption uses each POB's range-net revenue, never another POB's billing."""

from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.domain.reports import opening_relief_pob as pob
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
from erev_api.problems import Problem


def fixture(monkeypatch):
    entity = UUID(int=1)
    obligations = [
        {"obligation_key": key, "performing_entity_id": entity, "principal_agent": "PRINCIPAL"}
        for key in ("S", "D")
    ]
    session = NS(execute=lambda *a: NS(mappings=lambda: NS(all=lambda: obligations)))
    row = NS(
        version_id=UUID(int=2),
        contract_id=UUID(int=3),
        entity_id=entity,
        external_id="C",
        currency="USD",
    )
    nodes = [
        NS(id=f"{measure}:C/{subject}:P03", value=value, currency="USD")
        for subject, billed, revenue in (("S", "20000", "15000"), ("D", "0", "0"))
        for measure, value in (("billed_cum", billed), ("revenue_cum", revenue))
    ]
    monkeypatch.setattr(pob.store, "load_trace", lambda *a: NS(nodes=nodes))
    return session, row, nodes


def entry(index, subject, amount):
    return Entry(
        order=(index,),
        flow=Flow(D(amount), True),
        subject_key=f"C/{subject}",
        line_id=UUID(int=10 + index),
    )


@pytest.mark.parametrize("cap,expected", [("5000", "800"), ("200", "200"), ("0", "0")])
def test_unbilled_delivery_cannot_consume_service_opening(monkeypatch, cap, expected):
    session, row, _ = fixture(monkeypatch)
    entries = [entry(1, "D", "8000"), entry(2, "S", "200"), entry(3, "S", "600")]
    amount, facts = pob.calculate(session, row, NS(key="P03"), entries, D(cap), D("5800"))
    assert amount == D(expected)
    assert facts["obligations"]["C/D"]["eligible_relief"] == "0"
    assert D(facts["obligations"]["C/S"]["eligible_relief"]) == D("800")


def test_range_nets_corrections_before_applying_opening_cap(monkeypatch):
    session, row, nodes = fixture(monkeypatch)
    entries = [entry(1, "S", "6000"), entry(2, "S", "-5500")]
    amount, _ = pob.calculate(session, row, NS(key="P03"), entries, D("5000"), D("500"))
    assert amount == D("500")
    # Missing original opening evidence must not be replaced with current/latest balances.
    nodes.pop()
    with pytest.raises(Problem):
        pob.calculate(session, row, NS(key="P03"), entries, D("5000"), D("500"))
