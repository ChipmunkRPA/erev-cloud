from decimal import Decimal as D
from fractions import Fraction
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.domain.reports import opening_intercompany as ic
from erev_api.domain.reports.builders import SourceCollector
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
from erev_api.problems import Problem


def fixture(monkeypatch):
    owner, entity, performer, version, line, due = (UUID(int=i) for i in range(1, 7))
    row = NS(contract_id=owner, entity_id=entity, version_id=version, external_id="C")
    obligations = [
        {"obligation_key": "S", "performing_entity_id": performer, "principal_agent": "PRINCIPAL"}
    ]
    control = {
        "contract_id": owner,
        "entity_id": entity,
        "entry_kind": "INTERCOMPANY",
        "account_role": "CONTRACT_LIABILITY",
        "subject_key": "C/S",
    }
    session = NS(
        execute=lambda *a: NS(mappings=lambda: NS(one=lambda: control)), scalars=lambda *a: [owner]
    )
    proof = NS(
        components=(),
        verified_source_owners=(),
        delta=NS(
            amount=Fraction(-40), source_ids=(UUID(int=8),), movements=(NS(contract_id=owner),)
        ),
        paid_line_ids=(UUID(int=9),),
        evidence=((version, "digest"),),
    )
    monkeypatch.setattr(ic.revenue_attribution, "for_control", lambda *a, **k: (due, proof))
    entry = Entry(order=(1,), flow=Flow(D(40), True), subject_key="C/S", line_id=line)
    return NS(session=session), row, obligations, entry, control, proof


def test_original_due_to_identity_sources_and_replay_are_retained(monkeypatch):
    uow, row, obligations, entry, _, _ = fixture(monkeypatch)
    sources = SourceCollector()
    reader = ic.Reader(uow, NS(binding=None, sources=sources), "functional")
    facts = reader.read(row, obligations, [entry])
    assert facts["C/S"]["performing_entity_id"] == str(UUID(int=3))
    assert facts["C/S"]["lines"][0]["control_relief"] == "40"
    assert facts["C/S"]["lines"][0]["sources"] == [str(UUID(int=8))]
    assert reader.paid == {UUID(int=i) for i in (5, 6, 9)}
    reader.retain()
    assert sources.evidence[ic.KEY] == reader.evidence
    old = ic.Reader(uow, NS(binding=NS(evidence={}), sources=None), "functional")
    assert old.read(row, obligations, [entry]) == {}
    old.retain()


@pytest.mark.parametrize("mismatch", ["entity", "role", "amount", "agent", "owner"])
def test_other_entities_roles_amounts_and_agent_splits_are_not_admitted(monkeypatch, mismatch):
    uow, row, obligations, entry, control, proof = fixture(monkeypatch)
    if mismatch == "entity":
        control["entity_id"] = UUID(int=99)
    elif mismatch == "role":
        control["entry_kind"] = "REVENUE_RECOGNITION"
    elif mismatch == "amount":
        proof.delta.amount = Fraction(-39)
    elif mismatch == "owner":
        proof.delta.movements[0].contract_id = UUID(int=99)
    else:
        obligations[0]["principal_agent"] = "AGENT"
    reader = ic.Reader(uow, NS(binding=None, sources=None), "transaction")
    if mismatch == "agent":
        assert reader.read(row, obligations, [entry]) == {}
    else:
        with pytest.raises(Problem):
            reader.read(row, obligations, [entry])


def test_verified_historical_intercompany_owner_is_retained(monkeypatch):
    from erev_api.domain.reports import opening_source_membership

    uow, row, obligations, entry, _, proof = fixture(monkeypatch)
    former = UUID(int=99)
    proof.delta.movements[0].contract_id = former
    proof.verified_source_owners = (former,)
    sources = SourceCollector()
    reader = ic.Reader(uow, NS(binding=None, sources=sources), "functional")
    facts = reader.read(row, obligations, [entry])
    assert facts["C/S"]["lines"][0]["historical_source_owners"] == [str(former)]
    assert facts["C/S"]["lines"][0]["control_relief"] == "40"
    reader.retain()
    assert opening_source_membership.KEY in sources.evidence
    replay = ic.Reader(uow, NS(binding=NS(evidence=sources.evidence), sources=None), "functional")
    assert replay.read(row, obligations, [entry]) == facts
    old = ic.Reader(uow, NS(binding=NS(evidence={ic.KEY: facts}), sources=None), "functional")
    with pytest.raises(Problem):
        old.read(row, obligations, [entry])
