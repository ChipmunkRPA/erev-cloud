"""Shared approval basis retains membership and the computation used for SSP allocation."""

from datetime import UTC, datetime
from types import SimpleNamespace as NS
from uuid import UUID

import pytest
from erev_api.approvals import subjects

NOW = datetime(2026, 10, 23, tzinfo=UTC)
P, A, B, C = (UUID(int=i) for i in range(1, 5))


def basis(monkeypatch, *, closed=False, computation=9, hidden=False, revision=1):
    memberships = [
        dict(
            id=UUID(int=10),
            contract_id=A,
            valid_from_known_at=NOW,
            valid_to_known_at=NOW if closed else None,
        )
    ]
    affected = [A, B]
    calls = iter(
        [
            NS(one_or_none=lambda: NS(row_version=revision)),
            NS(mappings=lambda: NS(all=lambda: memberships)),
            [NS(id=c, latest_computation_id=UUID(int=computation)) for c in affected],
        ]
    )
    session = NS(execute=lambda *args: next(calls))
    monkeypatch.setattr(subjects, "_group_member_ids", lambda session, contract: [A, B])

    def states(session, ids):
        assert ids == affected
        return [
            dict(
                contract_id=str(c),
                combination_group_id=str(C),
                head_stream_version=None if hidden else 7,
            )
            for c in ids
        ]

    monkeypatch.setattr(subjects, "_member_states", states)
    return subjects._portfolio_estimate_basis(session, P)


def test_population_and_ssp_computation_are_bound(monkeypatch):
    initial = basis(monkeypatch)
    facts = initial["portfolio_basis"]
    assert [m["contract_id"] for m in facts["members"]] == [str(A), str(B)]
    assert facts["precedence"] == "SHARED_OVERRIDES_LOCAL"
    assert facts["breakage_allocation"] == "TOTAL_BY_SSP"
    assert basis(monkeypatch) == initial
    assert basis(monkeypatch, computation=11) != initial
    assert basis(monkeypatch, revision=2) != initial
    ended = basis(monkeypatch, closed=True)
    assert ended != initial
    assert ended["portfolio_basis"]["memberships"][0]["contract_id"] == str(A)
    assert len(ended["portfolio_basis"]["members"]) == 2
    assert basis(monkeypatch, closed=True, computation=12) != ended


def test_hidden_member_is_not_silently_dropped(monkeypatch):
    with pytest.raises(subjects.SubjectNotVisible):
        basis(monkeypatch, hidden=True)


def test_shared_approval_names_affected_entities_not_whole_tenant(monkeypatch):
    from unittest.mock import Mock

    session = Mock()
    session.execute.side_effect = [
        NS(one_or_none=lambda: NS(contract_id=None, portfolio_id=P)),
        NS(all=lambda: [NS(id=A, contracting_entity_id=A), NS(id=B, contracting_entity_id=B)]),
    ]
    monkeypatch.setattr(
        subjects,
        "_portfolio_estimate_basis",
        lambda *_: {
            "portfolio_basis": {"members": [{"contract_id": str(A)}, {"contract_id": str(B)}]}
        },
    )
    entities = subjects.estimate_version_entities(session, C)
    assert entities.ids == frozenset({A, B})
    assert entities.covered_by(frozenset({A, B}))
    assert not entities.covered_by(frozenset({A}))
    assert not entities.touched_by(frozenset({C}))


@pytest.mark.parametrize("empty", [True, False])
def test_shared_approval_never_drops_unreadable_population(monkeypatch, empty):
    from unittest.mock import Mock

    session = Mock()
    session.execute.side_effect = [
        NS(one_or_none=lambda: NS(contract_id=None, portfolio_id=P)),
        NS(all=lambda: []),
    ]
    monkeypatch.setattr(
        subjects,
        "_portfolio_estimate_basis",
        lambda *_: {"portfolio_basis": {"members": [] if empty else [{"contract_id": str(A)}]}},
    )
    if empty:
        assert subjects.estimate_version_entities(session, C) == subjects.ALL_ENTITIES
    else:
        with pytest.raises(subjects.SubjectNotVisible):
            subjects.estimate_version_entities(session, C)
