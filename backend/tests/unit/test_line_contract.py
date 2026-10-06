"""The contract a ledger line is listed under, without a database (item BILLING-GROUP-SUBJECT-1;
the supervisor's ruling of 2026-10-02; 04 T-SL-04 ``contract_id`` rev 1.303; dev-guide DG-CMD-10
rev 1.284; ENGINE_SPEC_B S14-R-13 and Table 14-A).

A ledger line needs one contract. An entry names it by its obligation, by the ``contract_key``
dimension the engine gives a line whose subject has ONE member contract, by being of a group of
one contract, or by a ``<contract>@<entity>`` subject. Every JET-10 part — the remeasurement of a
foreign-currency balance and the difference at its settlement — is one entry per group and entity,
``<group>@<entity>``: in a group of several contracts it names none, and before the item the
computation that met it ended FAILED (``ValueError: subject … names no member contract``).

The rule: such an entry's lines are listed under the member contract FIRST BY EXTERNAL ID among
the members the entry's entity posts for — as their contracting entity, or as the performing
entity of one of their obligations. The entry itself still belongs to no member
(``computation._line_contract`` without ``listed``), which is what the void's attribution reads.
The database witnesses are ``tests/domain/contracts/test_group_subject_lines.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.contracts import computation
from erev_engine.stages.s01_canonicalize import group_entity_subject_key

UK, US = UUID(int=1), UUID(int=2)
GROUP = "CG-CON-000003"
A, B, C = "NS-SO-UK-7001", "NS-SO-UK-7002", "NS-SO-UK-7000"
IDS = {A: UUID(int=11), B: UUID(int=12), C: UUID(int=10)}


def _found(*members: tuple[str, UUID], group: str = GROUP, **obligations: Any) -> Any:
    """A bundle index of the members given as (external id, contracting entity), in that order."""
    return SimpleNamespace(
        group={"code": group},
        contracts={
            external_id: {
                "id": IDS[external_id],
                "external_id": external_id,
                "contracting_entity_id": entity_id,
            }
            for external_id, entity_id in members
        },
        entities={"AVM-UK": {"id": UK}, "AVM-US": {"id": US}},
        obligations=dict(obligations),
    )


def _intent(subject_key: str, *, entity: str = "AVM-UK", contract_key: str | None = None) -> Any:
    dimensions = {"contract": GROUP} | (
        {} if contract_key is None else {"contract_key": contract_key}
    )
    line = SimpleNamespace(dimensions=dimensions)
    return SimpleNamespace(subject_key=subject_key, entity=entity, lines=(line, line))


def _own(entity: str = "AVM-UK", group: str = GROUP) -> str:
    return group_entity_subject_key(group, entity)


def _listed(found: Any, intent: Any, **performed: set[UUID]) -> str:
    return str(computation._line_contract(found, intent, None, performed)["external_id"])


# --- the four answers an entry gives itself -------------------------------------------------------


def test_an_entry_of_an_obligation_is_its_obligations_contract() -> None:
    """The obligation's row answers first, whatever the subject spells: here a subject that
    alone names nobody."""
    found = _found((A, UK), (B, UK))
    row = {"id": UUID(int=99), "contract_id": IDS[B]}
    assert computation._line_contract(found, _intent("O1"), row)["external_id"] == B


def test_an_entry_with_one_contract_key_dimension_is_that_contracts() -> None:
    """The engine names the owner of a component under the group's subject from the component's
    source (``assign.subject_contracts``) and gives its lines the dimension: that member, with
    or without a listing, although the listing's first member is another."""
    found = _found((A, UK), (B, UK))
    intent = _intent(f"{_own()}/RETURN/{B}/O1", contract_key=B)
    assert computation._line_contract(found, intent, None)["external_id"] == B
    assert _listed(found, intent) == B


def test_an_entry_of_a_group_of_one_contract_is_its_only_members() -> None:
    """The group's own subject in a group of one: the only member, with or without a listing."""
    found = _found((A, UK))
    assert computation._line_contract(found, _intent(_own()), None)["external_id"] == A
    assert _listed(found, _intent(_own())) == A


def test_an_entry_of_a_contract_subject_is_that_contracts() -> None:
    found = _found((A, UK), (B, UK))
    assert computation._line_contract(found, _intent(f"{B}@AVM-UK"), None)["external_id"] == B
    assert computation._line_contract(found, _intent(f"{B}/COST/1"), None)["external_id"] == B


# --- the fifth: the group's own subject in a group of several -------------------------------------


def test_the_groups_own_entry_belongs_to_no_member() -> None:
    """Without a listing the entry names nobody — the answer the void's attribution reads, and
    before the item the only one: the computation that posted such an entry ended FAILED."""
    found = _found((A, UK), (B, UK))
    with pytest.raises(ValueError, match="names no member contract"):
        computation._line_contract(found, _intent(_own()), None)
    assert computation._intent_contract(found, _intent(_own())) is None


def test_its_lines_are_listed_under_the_first_member_by_external_id() -> None:
    """Two members of the entry's entity, given in the other order: the one whose external id
    sorts first, whichever holds the balance."""
    found = _found((B, UK), (A, UK), (C, UK))
    assert list(found.contracts) == [B, A, C]
    assert _listed(found, _intent(_own())) == C
    assert _listed(_found((B, UK), (A, UK)), _intent(_own())) == A


def test_only_among_the_members_the_entrys_entity_posts_for() -> None:
    """A line's entity and its contract's never part: a member contracted by another entity is
    passed over, although its external id sorts first."""
    found = _found((C, US), (A, UK), (B, UK))
    assert _listed(found, _intent(_own("AVM-UK"))) == A
    assert _listed(found, _intent(_own("AVM-US"), entity="AVM-US")) == C


def test_a_member_whose_obligation_the_entity_performs_counts() -> None:
    """The performing entity of an obligation posts for its contract (05 RCP-04): the member is
    among those the entry's entity posts for, and first by external id it is the one listed."""
    found = _found((C, US), (A, UK))
    assert _listed(found, _intent(_own("AVM-UK"))) == A
    assert _listed(found, _intent(_own("AVM-UK")), **{"AVM-UK": {IDS[C]}}) == C


def test_a_component_under_the_groups_subject_is_listed_the_same_way() -> None:
    found = _found((B, UK), (A, UK))
    assert _listed(found, _intent(f"{_own()}/RETURN/unresolved")) == A


def test_the_groups_subject_is_the_engines_own_spelling() -> None:
    """``group_entity_subject_key`` encodes each component (CV-21): a group code with a
    delimiter is met in its encoded form, and its plain form names nothing."""
    found = _found((B, UK), (A, UK), group="CG/1")
    assert _listed(found, _intent(_own(group="CG/1"))) == A
    with pytest.raises(ValueError, match="names no member contract"):
        _listed(found, _intent("CG/1@AVM-UK"))


def test_an_entity_that_posts_for_no_member_is_refused() -> None:
    found = _found((A, US), (B, US))
    with pytest.raises(ValueError, match="posts for no member contract"):
        _listed(found, _intent(_own("AVM-UK")))


def test_a_subject_that_names_nothing_is_still_refused() -> None:
    found = _found((A, UK), (B, UK))
    with pytest.raises(ValueError, match="names no member contract"):
        _listed(found, _intent("SOMETHING-ELSE@AVM-UK"))
    with pytest.raises(ValueError, match="names no member contract"):
        _listed(found, _intent(_own("AVM-US")))  # another entity's unit under this entry's entity


# --- who performs for whom ------------------------------------------------------------------------


def test_the_performing_entities_are_read_from_the_books_obligation_versions() -> None:
    found = _found(
        (A, UK),
        (C, US),
        **{f"{A}/O1": {"contract_id": IDS[A]}, f"{C}/O1": {"contract_id": IDS[C]}},
    )
    book_output = SimpleNamespace(
        obligation_versions=(
            SimpleNamespace(subject_key=f"{A}/O1", columns={"performing_entity_code": "AVM-UK"}),
            SimpleNamespace(subject_key=f"{C}/O1", columns={"performing_entity_code": "AVM-UK"}),
            SimpleNamespace(subject_key="GONE/O1", columns={"performing_entity_code": "AVM-US"}),
        )
    )
    assert computation._performed_by(found, book_output) == {"AVM-UK": {IDS[A], IDS[C]}}
