"""Who reads an approval subject in full (04 §16.10 rev 1.319 "Who reads a subject in full";
03 REQ-PLT-012 rev 1.146; dev-guide DG-KRN-APR-06 rev 1.295; item READ-SCOPE-BY-PERMISSION-1,
register index 301).

The kernel asks three people whether they read the WHOLE of what a request puts in force: its
preparer, at a submission and a preview (supervisor ruling R-64 (6): a preparer asks others to
approve only what she can read in full); a delegate, at a decision, in the queue and in a
notification (R-41 (1): a delegation conveys the permission, not the view); and the reader of a
request's content (04 §16.10 rev 1.208). Until rev 1.319 the answer was the person's entity scope
— the union of the entities of every role assignment. A role on an entity is not a read of it.
Measured: a Revenue Accountant of one entity whose second role, for another entity, holds
``import.upload`` alone previewed and submitted a modification of a contract grouped across the
two, and read the content of her request — the group's figures — because her roles' union covered
both. And since rev 1.319 a guarded transaction runs under the scope of the permission that
admitted it (``auth.dependencies.require``), so the union is no longer what a command reads
under.

The question is asked by permission: the person holds, in her own right, ONE permission that
reads the subject for EVERY entity the subject is bound to — the question a stored preview and
the summary of a dry run already ask (04 §16.10 "Who reads a stored preview", rev 1.300 and rev
1.314; ``domain.platform.file_access.stored_preview_readable``). ``READERS`` states those
permissions for each subject type: the permissions the subject's own read routes admit (04
§15.3). Who holds the permission of a step in her own right for every entity is asked nothing
further (REQ-PLT-015: the approver sees what they approve): the question is put to a preparer, to
a delegate and to a reader whom no step's permission of her own covers
(``engine.find_authority``, ``approval_queries.content_visible``).

A subject that no read permission of the catalogue names — an access grant, a provider's support
grant, the shredding of a document — is covered as before: by a permission of the person's own,
whatever it is, for every entity (``ANY_PERMISSION``). A tenant-level subject names no entity and
asks nothing. ``tests/unit/approvals/test_subject_readers.py`` holds the table against the
registry of subjects and against the read registry of files.

Two principals are not asked by this table: they hold no permission by construction and no route
admitted them — SYSTEM, and the provider's operator at the command line, the preparer of a
support grant's request. The kernel asks their entity scope instead
(``engine.asked_by_entity_scope``; 04 §16.10 rev 1.321). Asked by this table, as every principal
but SYSTEM was from rev 1.319, that operator covered nothing and its request was refused.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal
from uuid import UUID

from erev_api.approvals.subjects import SubjectEntities
from erev_api.enums import ApprovalSubjectType

type Scope = Literal["*"] | frozenset[UUID]
type Readers = Literal["*"] | frozenset[str]

# A subject no read permission names: a permission of the person's own for every entity, whatever
# it is — the entities of her roles, as the kernel asked of every subject until rev 1.319.
ANY_PERMISSION: Final = "*"
# The subject of what is asked about a contract before a subject of it is stored: the pending
# events of a preview (``engine.CONTRACT_SUBJECT``).
CONTRACT: Final = "contract"

_CONTRACT_READ: Final = frozenset({"contract.read"})
_CONFIG_READ: Final = frozenset({"config.read"})
_SSP_READ: Final = frozenset({"ssp.read"})
# 04 §16.14 API-R-37: the adjustment's own reads admit the four.
_ADJUSTMENT_READERS: Final = frozenset(
    {"contract.read", "adjustment.create", "adjustment.approve", "report.run"}
)

READERS: Final[Mapping[str, Readers]] = MappingProxyType(
    {
        # access administration and the provider's access: no read permission of the catalogue
        ApprovalSubjectType.ROLE_ASSIGNMENT.value: ANY_PERMISSION,
        ApprovalSubjectType.ROLE_CHANGE.value: ANY_PERMISSION,
        ApprovalSubjectType.SOD_EXCEPTION.value: ANY_PERMISSION,
        ApprovalSubjectType.SUPPORT_GRANT.value: ANY_PERMISSION,
        # a document is read through the record that owns it (04 T-PLT-29), a legacy batch by the
        # migration's own permission for all entities
        ApprovalSubjectType.EVIDENCE_SHRED.value: ANY_PERMISSION,
        ApprovalSubjectType.MIGRATION_SSP_REPLAY.value: ANY_PERMISSION,
        # configuration (04 §15.3: ``config.read``)
        ApprovalSubjectType.FX_RATE_SET_VERSION.value: _CONFIG_READ,
        ApprovalSubjectType.ACCOUNT_MAPPING_VERSION.value: _CONFIG_READ,
        ApprovalSubjectType.RULE_SET_VERSION.value: _CONFIG_READ,
        ApprovalSubjectType.POB_TEMPLATE_VERSION.value: _CONFIG_READ,
        ApprovalSubjectType.REGISTRY_VERSION.value: _CONFIG_READ,
        ApprovalSubjectType.POLICY_OVERRIDE.value: _CONFIG_READ,
        ApprovalSubjectType.PERIOD_LOCK.value: _CONFIG_READ,
        ApprovalSubjectType.PERIOD_REOPEN.value: _CONFIG_READ,
        # SSP books (``ssp.read``)
        ApprovalSubjectType.SSP_BOOK_VERSION.value: _SSP_READ,
        # contracts and what is recorded, computed and posted on them (``contract.read``)
        CONTRACT: _CONTRACT_READ,
        ApprovalSubjectType.CONTRACT_ACTIVATION.value: _CONTRACT_READ,
        ApprovalSubjectType.CONTRACT_VOID.value: _CONTRACT_READ,
        ApprovalSubjectType.COMBINATION_GROUP.value: _CONTRACT_READ,
        ApprovalSubjectType.MODIFICATION.value: _CONTRACT_READ,
        ApprovalSubjectType.MANUAL_EVENT.value: _CONTRACT_READ,
        ApprovalSubjectType.ATTRIBUTE_CHANGE.value: _CONTRACT_READ,
        ApprovalSubjectType.ESTIMATE_VERSION.value: _CONTRACT_READ,
        ApprovalSubjectType.SSP_OVERRIDE.value: _CONTRACT_READ,
        ApprovalSubjectType.JUDGEMENT_RECORD.value: _CONTRACT_READ,
        ApprovalSubjectType.EXCEPTION_WAIVER.value: _CONTRACT_READ,
        ApprovalSubjectType.IMPORT_COMMIT.value: _CONTRACT_READ,
        ApprovalSubjectType.JOURNAL_RUN.value: _CONTRACT_READ,
        ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE.value: _CONTRACT_READ,
        ApprovalSubjectType.MAPPING_PROFILE_VERSION.value: _CONTRACT_READ,
        ApprovalSubjectType.MANUAL_ADJUSTMENT.value: _ADJUSTMENT_READERS,
    }
)


def of(subject_type: ApprovalSubjectType | str) -> Readers:
    """The permissions that read a subject of ``subject_type``; none for a type that states none
    (fail closed: nobody reads in full what the table does not know)."""
    return READERS.get(str(getattr(subject_type, "value", subject_type)), frozenset())


def any_scope(held: Mapping[str, Scope]) -> Scope:
    """Every entity a permission of ``held`` names: all entities when one of them is held for
    all, else the union of what each names."""
    named: set[UUID] = set()
    for scope in held.values():
        if not isinstance(scope, frozenset):
            return "*"
        named |= scope
    return frozenset(named)


def read_in_full(
    held: Mapping[str, Scope], subject_type: ApprovalSubjectType | str, entities: SubjectEntities
) -> bool:
    """Whether ``held`` — a person's own permissions, each with its entities — reads a subject of
    ``subject_type`` bound to ``entities`` in full: ONE permission of ``of(subject_type)`` is held
    for every entity. Scopes of several permissions are never added up. A tenant-level subject
    names no entity: always."""
    if not entities.all_entities and not entities.ids:
        return True
    readers = of(subject_type)
    if not isinstance(readers, frozenset):
        return entities.covered_by(any_scope(held))
    return any(code in held and entities.covered_by(held[code]) for code in sorted(readers))


_REQUEST_TYPES: Final = frozenset(member.value for member in ApprovalSubjectType)


def read_with(code: str) -> tuple[str, ...]:
    """The subject types of a request (E-08) that ``code`` reads, sorted: what a statement over
    ``approval_request`` asks of a permission (``domain.platform.approval_queries``)."""
    return tuple(
        sorted(
            subject_type
            for subject_type, readers in READERS.items()
            if subject_type in _REQUEST_TYPES and isinstance(readers, frozenset) and code in readers
        )
    )


def read_with_any() -> tuple[str, ...]:
    """The subject types of a request (E-08) of ``ANY_PERMISSION``, sorted."""
    return tuple(
        sorted(
            subject_type
            for subject_type, readers in READERS.items()
            if subject_type in _REQUEST_TYPES and not isinstance(readers, frozenset)
        )
    )
