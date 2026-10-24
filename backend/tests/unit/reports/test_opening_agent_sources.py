"""Agent disclosures retain net amounts and source sets, never proportional source shares."""

from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from fractions import Fraction as F
import json
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.domain.reports import opening_agent_sources as agent
from erev_api.domain.reports.revenue_attribution import AmountProof, SourceIdentity
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
from erev_api.problems import Problem

START = date(2026, 4, 1)
OWNER = UUID(int=1)


def proof(*dates, amount=-20):
    return AmountProof(
        F(amount),
        (UUID(int=90),),
        ((UUID(int=91), "digest"),),
        "transaction",
        tuple(
            SourceIdentity(UUID(int=10 + i), OWNER, str(i), "LIABILITY_LAYER_CONSUMED", START, None)
            for i, _ in enumerate(dates)
        ),
        tuple((OWNER, str(i), d) for i, d in enumerate(dates)),
    )


@pytest.mark.parametrize(
    "dates,expected",
    [
        ((date(2026, 3, 1), date(2026, 3, 31)), "OPENING"),
        ((START, date(2026, 4, 2)), "NON_OPENING"),
    ],
)
def test_bucket_uses_original_creation_date_not_consumption_date(dates, expected):
    assert agent.bucket(proof(*dates), START) == expected


def test_mixed_or_missing_dates_never_imply_a_net_allocation():
    mixed = proof(date(2026, 3, 31), START)
    with pytest.raises(ValueError, match="mixes"):
        agent.bucket(mixed, START)
    with pytest.raises(ValueError, match="creation dates"):
        agent.bucket(replace(mixed, layer_dates=()), START)
    assert agent.bucket(replace(mixed, amount=F(0)), START) == "ZERO_NET"


def setup(monkeypatch, source):
    uow = NS(session=NS(scalars=lambda *a: ["S"]))
    row = NS(version_id=UUID(int=2), contract_id=OWNER, entity_id=UUID(int=3), external_id="C")
    entry = Entry(order=(1,), flow=Flow(D(100), True), subject_key="C/S", line_id=UUID(int=4))
    gross = NS(
        delta=NS(amount=F(-100)),
        paid_line_ids=(),
        components=(
            (UUID(int=5), "REVENUE", "-20", "-25"),
            (UUID(int=6), "SUPPLIER_PAYABLE", "-80", "-100"),
        ),
    )
    monkeypatch.setattr(
        agent.revenue_attribution, "for_control", lambda *a, **k: (UUID(int=5), gross)
    )
    monkeypatch.setattr(agent.revenue_attribution, "verify_component", lambda *a, **k: source)
    return uow, row, entry, gross


def test_gross_control_becomes_verified_net_income_with_replayable_source_set(monkeypatch):
    uow, row, entry, _ = setup(monkeypatch, proof(date(2026, 3, 1), date(2026, 3, 2)))
    result = agent.read(uow, row, [entry], START, D(100))
    assert result.entries[0].flow.amount == D(20)
    assert result.eligible == {"C/S": D(20)}
    assert {UUID(int=i) for i in (4, 5, 6, 90)} <= result.paid_lines
    facts = result.evidence["C/S"]["lines"][0]
    assert facts["gross_relief"] == "100"
    assert facts["net_income"] == "20"
    assert len(facts["source_sets"][0]["sources"]) == 2
    assert all("amount" not in source for source in facts["source_sets"][0]["sources"])
    assert json.loads(json.dumps(result.evidence)) == result.evidence


def test_current_sources_cannot_consume_opening_and_mixed_sources_need_a_rule(monkeypatch):
    uow, row, entry, _ = setup(monkeypatch, proof(START))
    assert agent.read(uow, row, [entry], START, D(100)).eligible == {"C/S": D(0)}
    monkeypatch.setattr(
        agent.revenue_attribution,
        "verify_component",
        lambda *a, **k: proof(date(2026, 3, 31), START),
    )
    with pytest.raises(Problem):
        agent.read(uow, row, [entry], START, D(100))
    assert agent.read(uow, row, [entry], START, D(0)).entries[0].flow.amount == D(20)


def test_wrong_gross_sign_or_net_posting_is_rejected(monkeypatch):
    uow, row, entry, gross = setup(monkeypatch, proof(date(2026, 3, 1)))
    gross.delta.amount = F(100)
    with pytest.raises(Problem):
        agent.read(uow, row, [entry], START, D(100))
    gross.delta.amount = F(-100)
    monkeypatch.setattr(
        agent.revenue_attribution,
        "verify_component",
        lambda *a, **k: proof(date(2026, 3, 1), amount=-21),
    )
    with pytest.raises(Problem):
        agent.read(uow, row, [entry], START, D(100))


def test_old_asset_sources_are_not_opening_contract_liability():
    original = proof(date(2026, 3, 1))
    source = replace(original.sources[0], movement_kind="ASSET_LAYER_CREATED")
    assert agent.bucket(replace(original, sources=(source,)), START) == "NON_OPENING"


def test_report_cell_distinguishes_gross_opening_and_net_source_set(monkeypatch):
    from erev_api.domain.reports import opening_relief_cells as cells

    uow, row, entry, _ = setup(monkeypatch, proof(date(2026, 3, 1)))
    result = agent.read(uow, row, [entry], START, D(100))
    source = {
        "contracts": [str(OWNER)],
        "currency_view": "transaction",
        "currency": "USD",
        "translation_rates": [],
        "values": {key: {"amount": "20", "currency": "USD"} for key in cells.COLUMNS},
        "pob": {
            "obligations": {
                "C/S": {
                    "opening_revenue": "80",
                    "agent_net_sources": result.evidence["C/S"],
                }
            }
        },
    }
    detail = "\n".join(cells._details(source))
    assert "Opening gross control relief (includes supplier payable): 80 USD" in detail
    assert "Agent net income: 20 USD; gross control relief: 100 USD" in detail
    assert "complete source set (no per-source amounts)" in detail
    assert str(OWNER) + "/0 LIABILITY_LAYER_CONSUMED" in detail


def test_other_member_source_requires_separate_ownership_support(monkeypatch):
    original = proof(date(2026, 3, 1))
    foreign = replace(original, sources=(replace(original.sources[0], contract_id=UUID(int=99)),))
    uow, row, entry, _ = setup(monkeypatch, foreign)
    with pytest.raises(Problem):
        agent.read(uow, row, [entry], START, D(100))


def test_functional_income_uses_original_net_leg_not_gross_exchange_ratio(monkeypatch):
    original = replace(proof(date(2026, 3, 1), amount=-27), view="functional")
    uow, row, entry, gross = setup(monkeypatch, original)
    gross.delta.amount = F(-125)
    gross.components = (
        (UUID(int=5), "REVENUE", "-20", "-27"),
        (UUID(int=6), "SUPPLIER_PAYABLE", "-80", "-98"),
    )
    entry = replace(entry, flow=replace(entry.flow, amount=D(125)), period_id=UUID(int=8))
    result = agent.read(uow, row, [entry], START, D(125), view="functional")
    assert result.entries[0].flow.amount == D(27)
    assert result.eligible == {"C/S": D(27)}
    assert result.opening_entries[0].period_id == UUID(int=8)
    assert result.opening_entries[0].flow.amount == D(27)


def test_net_supplier_reallocation_is_included_once_without_gross_control(monkeypatch):
    from erev_api.domain.reports import opening_agent_postings

    uow, row, entry, _ = setup(monkeypatch, proof(date(2026, 3, 1)))
    original_net = replace(entry, line_id=UUID(int=5), flow=replace(entry.flow, amount=D(20)))
    extra_net = replace(entry, line_id=UUID(int=7), flow=replace(entry.flow, amount=D(10)))
    pair = [
        {
            "id": UUID(int=7),
            "account_role": "REVENUE",
            "amount_txn": D(-10),
            "amount_functional": D(-12),
        },
        {
            "id": UUID(int=8),
            "account_role": "BILLING_CLEARING",
            "amount_txn": D(10),
            "amount_functional": D(12),
        },
    ]
    monkeypatch.setattr(
        opening_agent_postings,
        "supplier_pair",
        lambda *a, **k: (pair, proof(date(2026, 3, 1), amount=10)),
    )
    monkeypatch.setattr(
        agent.revenue_attribution,
        "verify_component",
        lambda uow, identity, **k: proof(
            date(2026, 3, 1), amount=-10 if identity == UUID(int=7) else -20
        ),
    )
    result = agent.read(
        uow,
        row,
        [entry],
        START,
        D(100),
        net_entries=[original_net, extra_net],
    )
    assert sum(e.flow.amount for e in result.entries) == D(30)
    assert result.eligible == {"C/S": D(30)}
    assert len(result.evidence["C/S"]["lines"]) == 2
    assert result.evidence["C/S"]["lines"][1]["gross_relief"] == "0"
    assert {UUID(int=7), UUID(int=8)} <= result.paid_lines


def test_control_counterpart_must_belong_to_captured_net_population(monkeypatch):
    uow, row, entry, _ = setup(monkeypatch, proof(date(2026, 3, 1)))
    with pytest.raises(Problem):
        agent.read(uow, row, [entry], START, D(100), net_entries=[])
