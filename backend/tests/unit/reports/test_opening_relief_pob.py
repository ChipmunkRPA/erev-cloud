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


def test_frozen_opening_never_uses_current_trace(monkeypatch):
    session, row, nodes = fixture(monkeypatch)
    original = NS(**{**vars(row), "version_id": UUID(int=99)})

    def frozen_only(session, version):
        assert version == original.version_id
        return NS(nodes=nodes)

    monkeypatch.setattr(pob.store, "load_trace", frozen_only)
    amount, facts = pob.calculate(
        session,
        row,
        NS(key="P03"),
        [entry(1, "S", "800")],
        D("5000"),
        D("800"),
        opening_row=original,
    )
    assert amount == D("800")
    assert facts["obligations"]["C/S"]["opening_billing"] == "20000"


def test_contract_absent_from_frozen_population_has_no_opening(monkeypatch):
    session, row, _ = fixture(monkeypatch)
    amount, facts = pob.calculate(
        session, row, NS(key="P03"), [entry(1, "S", "800")], D("0"), D("800"), opening_absent=True
    )
    assert amount == 0
    assert facts["obligations"]["C/S"]["opening_nodes"] == []


def test_frozen_sources_are_cached_and_must_tie_to_lock(monkeypatch):
    from erev_api.domain.reports import opening_relief_frozen as frozen

    entity, contract, lock = UUID(int=1), UUID(int=2), UUID(int=3)
    row = NS(contract_id=contract, entity_id=entity, external_id="C")
    original = NS(
        version_id=UUID(int=4),
        currency="USD",
        value=lambda name: D("500") if name == "contract_liability" else D(0),
    )
    held = NS(currency="USD", values={"contract_liability": D("500")})
    locked = NS(lock_id=lock, rows={"C": held})
    calls = []

    def sources(*args, **kwargs):
        calls.append(1)
        return frozen.FrozenSources({contract: original}, {"lock_id": str(lock)})

    monkeypatch.setattr(frozen, "_sources", sources)
    reader = frozen.Reader(None)
    assert reader.read(row=row, previous=None, locked=locked, book="ASC606")[0] is original
    assert reader.read(row=row, previous=None, locked=locked, book="ASC606")[0] is original
    assert calls == [1]
    held.values["contract_liability"] = D("501")
    with pytest.raises(Problem):
        reader.read(row=row, previous=None, locked=locked, book="ASC606")


def test_combination_cap_is_applied_once_after_member_eligibility(monkeypatch):
    session, row, _ = fixture(monkeypatch)
    # Two members independently qualify for 800; a group-level 1,000 cap cannot
    # establish whether either member owns 200, 500, or 800 of the final amount.
    candidate, _ = pob.calculate(
        session, row, NS(key="P03"), [entry(1, "S", "800")], D("1000"), D("1600")
    )
    assert candidate == D("800")
    assert pob.group_total([candidate, candidate], opening=D("1000"), consumed=D("1600")) == D(
        "1000"
    )
    assert pob.group_total([candidate, candidate], opening=D("2000"), consumed=D("900")) == D("900")


@pytest.mark.parametrize("role,performer", [("AGENT", UUID(int=1)), ("PRINCIPAL", UUID(int=9))])
def test_zero_functional_opening_keeps_special_contract_revenue_without_invented_sources(
    monkeypatch, role, performer
):
    session, row, _ = fixture(monkeypatch)
    obligations = [
        {"obligation_key": "S", "performing_entity_id": performer, "principal_agent": role}
    ]
    session.execute = lambda *a: NS(mappings=lambda: NS(all=lambda: obligations))
    monkeypatch.setattr(
        pob.store, "load_trace", lambda *a: pytest.fail("Zero cap needs no opening trace")
    )
    amount, facts = pob.calculate(
        session,
        row,
        NS(key="P03"),
        [entry(1, "S", "50"), entry(2, "S", "-10")],
        D(0),
        D(40),
        functional_currency="USD",
    )
    assert amount == 0
    assert facts["basis"] == "ZERO_GROUP_OPENING"
    assert facts["obligations"] == {"C/S": {"posted_revenue": "40"}}
    assert len(facts["posted_lines"]) == 2
    # Positive openings still need the unresolved special attribution; this is no FIFO fallback.
    with pytest.raises(Problem):
        pob.calculate(
            session,
            row,
            NS(key="P03"),
            [entry(1, "S", "40")],
            D(1),
            D(40),
            functional_currency="USD",
        )
    # A zero cap does not bypass posted-source membership validation.
    with pytest.raises(Problem):
        pob.calculate(
            session,
            row,
            NS(key="P03"),
            [entry(1, "UNKNOWN", "40")],
            D(0),
            D(40),
            functional_currency="USD",
        )
