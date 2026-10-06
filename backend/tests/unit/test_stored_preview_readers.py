"""Who reads a stored preview (04 §16.10 rev 1.300 "Who reads a stored preview"; T-PLT-29 "Read
access"; item MOD-PREVIEW-READ-SCOPE-1): ``file_access.stored_preview_readable`` — ONE read
permission of the subject for EVERY entity the subject is bound to. CPU (DG-TST-18): the rule over
principals built here, with a stand-in for the kernel's read of the subject's entities. The three
doors that ask the function — the read of a modification, the read of a manual adjustment, the
file's own routes — are witnessed on the database in
``tests/domain/contracts/test_reader_independence.py``."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

import pytest
from erev_api.approvals.subjects import ALL_ENTITIES, SubjectEntities
from erev_api.auth.principal import Principal
from erev_api.domain.platform import file_access
from erev_api.enums import ApprovalSubjectType, FilePurpose, PrincipalKind

TENANT = UUID("0a1b2c3d-0000-4000-8000-0000000000aa")
UK = UUID("0a1b2c3d-0000-4000-8000-0000000000d2")
US = UUID("0a1b2c3d-0000-4000-8000-0000000000d3")
SUBJECT = UUID("0a1b2c3d-0000-4000-8000-0000000000f1")
FILE = UUID("0a1b2c3d-0000-4000-8000-0000000000f2")
MODIFICATION = ApprovalSubjectType.MODIFICATION
ADJUSTMENT = ApprovalSubjectType.MANUAL_ADJUSTMENT
NO_SESSION: Any = None  # the stand-in below reads nothing
Held = Literal["*"] | frozenset[UUID]
Read = list[tuple[ApprovalSubjectType, UUID]]


def _reader(scopes: dict[str, Held]) -> Principal:
    """A member who holds each permission of ``scopes`` for its entities."""
    return Principal(
        kind=PrincipalKind.USER,
        id=UUID(int=7),
        tenant_id=TENANT,
        membership_id=UUID(int=8),
        display_name="Una",
        roles=("revenue_accountant",),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


@pytest.fixture
def bound_to(monkeypatch: pytest.MonkeyPatch) -> Callable[[SubjectEntities], Read]:
    """The kernel's read of the entities a subject is bound to answers ``entities``; the list
    returned holds every subject it was asked about."""

    def install(entities: SubjectEntities) -> Read:
        asked: Read = []

        def preparer_scope(
            session: Any, subject_type: ApprovalSubjectType, subject_id: UUID
        ) -> SubjectEntities:
            asked.append((subject_type, subject_id))
            return entities

        monkeypatch.setattr(file_access.approvals, "preparer_scope", preparer_scope)
        return asked

    return install


def _answered(reader: Principal, subject_type: ApprovalSubjectType = MODIFICATION) -> bool:
    return file_access.stored_preview_readable(NO_SESSION, reader, subject_type, SUBJECT)


def test_a_stored_preview_is_answered_to_a_reader_of_every_entity_of_its_subject(
    bound_to: Callable[[SubjectEntities], Read],
) -> None:
    of_uk = _reader({"contract.read": frozenset({UK})})
    of_both = _reader({"contract.read": frozenset({UK, US})})
    # a contract alone in its group: the entity that contracts
    asked = bound_to(SubjectEntities(frozenset({UK})))
    assert _answered(of_uk) is True
    assert asked == [(MODIFICATION, SUBJECT)]
    # a group of two contracting entities: a reader of one of them is not answered
    bound_to(SubjectEntities(frozenset({UK, US})))
    assert _answered(of_uk) is False
    assert _answered(of_both) is True
    # without the permission nothing is answered, whatever the roles reach
    assert _answered(_reader({"event.record": "*"})) is False


def test_one_permission_covers_every_entity_and_scopes_are_never_added_up(
    bound_to: Callable[[SubjectEntities], Read],
) -> None:
    bound_to(SubjectEntities(frozenset({UK, US})))
    split = _reader({"contract.read": frozenset({UK}), "report.run": frozenset({US})})
    assert _answered(split, ADJUSTMENT) is False
    one = _reader({"contract.read": frozenset({UK}), "report.run": frozenset({UK, US})})
    assert _answered(one, ADJUSTMENT) is True


def test_the_permissions_are_the_read_permissions_of_the_subject(
    bound_to: Callable[[SubjectEntities], Read],
) -> None:
    bound_to(SubjectEntities(frozenset({UK})))
    assert dict(file_access.STORED_PREVIEW_READERS) == {
        MODIFICATION: frozenset({"contract.read"}),
        ADJUSTMENT: frozenset(
            {"adjustment.approve", "adjustment.create", "contract.read", "report.run"}
        ),
    }
    for code in ("adjustment.approve", "adjustment.create", "report.run"):
        holder = _reader({code: frozenset({UK})})
        assert (_answered(holder, ADJUSTMENT), _answered(holder, MODIFICATION)) == (True, False)


def test_a_subject_that_spans_every_entity_asks_for_all_entities(
    bound_to: Callable[[SubjectEntities], Read],
) -> None:
    """A member the kernel cannot name makes the subject span every entity (it fails closed): the
    preview is then answered only with the permission for all entities."""
    bound_to(ALL_ENTITIES)
    assert _answered(_reader({"contract.read": frozenset({UK, US})})) is False
    assert _answered(_reader({"contract.read": "*"})) is True


def test_a_reader_of_all_entities_is_answered_without_a_read_of_the_subject(
    bound_to: Callable[[SubjectEntities], Read],
) -> None:
    asked = bound_to(SubjectEntities(frozenset({UK, US})))
    assert _answered(_reader({"contract.read": "*"})) is True
    assert asked == []


def test_the_two_owners_state_the_rule_by_name() -> None:
    """04 T-PLT-29 "Read access": the owners' cells are the rule's words, held equal to the table
    by ``tests/architecture/test_file_access.py``; the words name the permissions of the rule."""
    owners = {
        owner.ref: owner
        for owner in file_access.FILE_READ_ACCESS[FilePurpose.IMPACT_PREVIEW].owners
    }
    stated = {
        ref: (owners[ref].read_by, owners[ref].entity_of)
        for ref in (
            "modification.impact_preview_file_id",
            "manual_adjustment.impact_preview_file_id",
        )
    }
    assert stated == {
        "modification.impact_preview_file_id": (
            "rule: contract.read for every entity the modification is bound to (§16.10)",
            "-",
        ),
        "manual_adjustment.impact_preview_file_id": (
            "rule: adjustment.approve, adjustment.create, contract.read or report.run for every "
            "entity the adjustment is bound to (§16.10)",
            "-",
        ),
    }


def test_a_command_that_destroys_the_document_is_bound_to_every_entity_of_the_subject(
    bound_to: Callable[[SubjectEntities], Read], monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-PLT-29 "Shred scope" (rev 1.300): the record of a stored preview names every entity
    its subject is bound to — until then the entity of the row alone — and a subject that spans
    every entity binds the command to all of them."""
    owners = {
        owner.ref: owner
        for owner in file_access.FILE_READ_ACCESS[FilePurpose.IMPACT_PREVIEW].owners
    }
    held = {
        "modification.impact_preview_file_id": MODIFICATION,
        "manual_adjustment.impact_preview_file_id": ADJUSTMENT,
    }
    monkeypatch.setattr(file_access, "_retaining", lambda session, table, file_id: [SUBJECT])
    for ref, subject_type in held.items():
        asked = bound_to(SubjectEntities(frozenset({UK, US})))
        assert owners[ref].references(NO_SESSION, FILE) == [(False, (UK, US))]
        assert asked == [(subject_type, SUBJECT)]
        bound_to(ALL_ENTITIES)
        assert owners[ref].references(NO_SESSION, FILE) == [file_access.EVERY_ENTITY]
