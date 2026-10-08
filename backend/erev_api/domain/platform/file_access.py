"""The file-read registry: who may read a stored file (04 T-PLT-29 "Read access", T-PLT-30; 03
REQ-PLT-012, REQ-PLT-015, REQ-PLT-035, REQ-PLT-036; supervisor rulings R-28, R-48 (c)).

A file has no readers of its own. It is read through a record that owns it, by the people who
read that record: the holders of the record's read permission (04 §15.3) or of a permission that
prepares or approves it, for the record's legal entity (DG-KRN-AUTH-04). ``FILE_READ_ACCESS``
names, for every E-68 purpose, the owners of a file of that purpose — the table and column that
reference it — each with those permissions and the entity the owner names; an owner whose rule is
its own (an approval request, an attachment, a calculator pool, the impact preview a modification
or a manual adjustment retains) states it as a ``grant``. A record
that names no entity while its file shows entity financial data is read with the permission for
all entities (R-28), until the record carries the entity; a record that names a list of entities
(an import upload, ``named_entity_ids``) is read with the permission for every one of them — an
empty list is a tenant-level record, a list not set yet asks for all entities (R-86 (f)). The
files of an import are read by the upload's own uploader and by the holders of ``contract.read``
or ``import.approve`` for those entities, not by ``import.upload`` alone (R-98). The
uploader of an upload reads it back,
which is how an upload is used before anything owns it; whoever uploads the same bytes again is an
uploader too (``uploaded_by``), because identical content is one stored row.

A command that takes a file id from its caller — to parse the file, to make it a record's
source or evidence, to attach it — binds it through ``bound``, which answers the row only for a
file the caller may read; a missing file and one the caller may not read are one answer, given
before any property of the file is looked at. ``FILE_BINDINGS`` names every request member that
names a file with the function that binds it (04 T-PLT-29 "Binding"; ruling R-111 (1)).

Nothing else reads a file: ``audit.read`` opens the audit artefacts it owns and no more, and a
platform operator's support grant (scope ``READ_ONLY``) names no file purpose, so an operator
reads no file. An owner whose record has a download route of its own — one that audits each export
or checks the record's state — is read there and not through the file routes (``route``).

``ATTACHMENT_SUBJECTS`` is the other half of the table: the records a file attaches to (T-PLT-30
``subject_type``), with the permissions that attach to and read each and the entity it names.

This is the READ registry. What keeps a file from being destroyed — the evidence references of
the shred rule (05 PRV-07 b; ``domain/platform/privacy.py``) — is another question with a registry
of its own. One question about destruction is answered here, because this registry knows every
record that references a file and the entity each names: ``referencing_scopes`` — the entities a
command that destroys the file is bound to (04 T-PLT-29 "Shred scope"; item FILE-SHRED-SCOPE-1).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import SubjectNotVisible
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    access_review_campaign,
    account_mapping_version,
    approval_request,
    audit_chain_verification,
    contract,
    contract_event,
    control_execution,
    estimate,
    estimate_version,
    event_submission,
    evidence_pack,
    exception_item,
    file_attachment,
    file_object,
    file_upload,
    idempotency_record,
    import_upload,
    journal_batch,
    judgement_record,
    lock_snapshot,
    manual_adjustment,
    migration_batch,
    modification,
    period_lock,
    posting_ack,
    reconciliation,
    registry_version,
    report_run,
    rule_set_version,
    sod_exception,
    ssp_book,
    ssp_book_version,
    ssp_calculator_run,
    tenant_snapshot,
)
from erev_api.domain.platform import approval_queries
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType, FilePurpose, PrincipalKind
from erev_api.problems import Problem

AUDIT_READ: Final = "audit.read"
# The "Read by" words of an owner whose own uploader reads its files (04 T-PLT-29).
UPLOADER_READS: Final = "the upload's own uploader"
# The "Attach with" words of a subject its requester attaches to (04 T-PLT-30).
REQUESTER_ATTACHES: Final = "its requester while it is PENDING"
# The audit fact of an upload (AUD-FACT: ``detail.ids`` names the stored row).
UPLOAD_ACTION: Final = "file.upload"
# The column behind every "uploader" row of 04 T-PLT-29 Read access: T-PLT-49 names the uploaders
# of a file. It holds a file id and owns no file, so it is no owner of the registry.
UPLOAD_REF: Final = "file_upload.file_object_id"
FILE_OBJECT: Final = "file_object"
# What a row names as its legal entity: every entity it concerns. Empty for a tenant-level row.
Entities = frozenset[UUID]
TENANT_LEVEL: Final[Entities] = frozenset()
# R-28: a row without an entity whose file shows entity financial data asks for the permission at
# scope ``*``.
ALL_ENTITIES: Final = "*"
# (session, request context, file id) → whether the owner lets the caller read the file.
Grant = Callable[[Session, RequestContext, UUID], bool]
# (session, file id) → the entities of each record that references the file through an owner
# whose rule is its own; None for a record that names none or that the lookup cannot place.
Referenced = Callable[[Session, UUID], list["Entities | Literal['*'] | None"]]
# The scope of one record that references a file, as ``auth.entity_scope.covers`` reads it:
# (all entities, the entities named).
ReferenceScope = tuple[bool, tuple[UUID, ...]]
EVERY_ENTITY: Final[ReferenceScope] = (True, ())
# (session, subject id) → the entities of the subject row the session sees, or None without one.
SubjectEntities = Callable[[Session, UUID], Entities | Literal["*"] | None]


def holds(
    principal: Principal, permissions: Iterable[str], entities: Entities | Literal["*"]
) -> bool:
    """Whether the principal holds one of ``permissions`` for every one of ``entities``; a
    tenant-level row (no entity) asks only that the permission be held, and ``ALL_ENTITIES`` that
    it be held for all entities (DG-KRN-AUTH-04; R-28)."""
    for code in permissions:
        scope = principal.permission_scopes.get(code)
        if scope is None:
            continue
        if scope == "*" or (entities != ALL_ENTITIES and entities <= scope):
            return True
    return False


def _entities(value: Any) -> Entities:
    if value is None:
        return TENANT_LEVEL
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(UUID(str(item)) for item in value)
    return frozenset({UUID(str(value))})


def _bound_scope(found: Entities | Literal["*"] | None) -> ReferenceScope:
    """What a destructive command is bound to by one record that references the file: the
    entities the record names, and every entity for a record that names none — a tenant-level
    row, a list not set or empty, a row whose owner states no entity (item FILE-SHRED-SCOPE-1,
    B3: "all entities where a referencing record has none"). Reading asks less of such a row;
    destroying its document asks for the whole workspace."""
    if found is None or found == ALL_ENTITIES or not found:
        return EVERY_ENTITY
    return (False, tuple(sorted(found, key=str)))


@dataclass(frozen=True, slots=True)
class FileOwner:
    """One way a record owns a file: ``table.column`` holds the file id.

    The caller reads the file through ``GET /files/{id}`` and ``GET /files/{id}/content`` when it
    holds one of ``permissions`` for the entity of an owning row the session sees (``entity``: a
    ``uuid`` or ``uuid[]`` expression over ``table`` and ``joins``), or, for an owner with a rule
    of its own, when ``grant`` says so. A row that names no entity (NULL) is tenant-level, unless
    its file shows entity financial data (``financial``): then the permission is needed for all
    entities (R-28). A list names every entity the permission is needed for; an empty list is a
    row that states it concerns no entity, and is tenant-level. An owner with a ``route`` is not
    read through the file routes at all: its
    record serves the bytes itself, under the rule and the audit of that route, or keeps them for
    the component that wrote them.
    """

    table: sa.Table
    column: str
    permissions: frozenset[str] = frozenset()
    entity: sa.ColumnElement[Any] | None = None
    # The file shows entity financial data, so a row without an entity is not tenant-level.
    financial: bool = False
    joins: tuple[tuple[sa.Table, sa.ColumnElement[bool]], ...] = ()
    grant: Grant | None = None
    # The name 04 T-PLT-29 gives the owner's own rule (``grant``).
    rule: str | None = None
    route: str | None = None
    # The column that names the principal who uploaded the owning record (an import upload's
    # ``created_by``): that principal reads the record's files whatever it holds (R-98).
    uploader: sa.ColumnElement[Any] | None = None
    # The records that reference a file through an owner whose rule is its own (``grant``), with
    # the entities each names: such an owner finds its records its own way (``references``).
    referenced: Referenced | None = None

    def __post_init__(self) -> None:
        rules = (bool(self.permissions), self.grant is not None, self.route is not None)
        if sum(rules) != 1:
            raise ValueError(f"{self.ref}: exactly one of permissions, grant and route")
        if (self.grant is None) != (self.rule is None):
            raise ValueError(f"{self.ref}: a grant has a rule name, and only a grant")
        if (self.grant is None) != (self.referenced is None):
            raise ValueError(f"{self.ref}: a grant finds its own records, and only a grant")
        if self.uploader is not None and not self.permissions:
            raise ValueError(f"{self.ref}: the record's uploader reads beside permissions")

    @property
    def ref(self) -> str:
        """``<table>.<column>``, as 04 T-PLT-29 lists the owner."""
        return f"{self.table.name}.{self.column}"

    @property
    def read_by(self) -> str:
        """The "Read by" cell of the owner's 04 T-PLT-29 row: the permissions in code order, the
        name of the owner's own rule, or the route that serves the file instead."""
        if self.route is not None:
            return f"route: {self.route}"
        if self.rule is not None:
            return f"rule: {self.rule}"
        held = ", ".join(sorted(self.permissions))
        return held if self.uploader is None else f"{held}; {UPLOADER_READS}"

    @property
    def entity_of(self) -> str:
        """The "Entity" cell of the owner's row: the column that names the owner's legal entity
        (with what a row without one asks), ``tenant`` for a tenant-level owner, ``all entities``
        for one without an entity whose file shows entity financial data, and a dash where the
        owner's rule or route decides."""
        if self.route is not None or self.grant is not None:
            return "-"
        if self.entity is None:
            return "all entities" if self.financial else "tenant"
        column = self.entity
        named = f"{column.table.name}.{column.name}"
        return f"{named}; all entities without one" if self.financial else named

    def allows(self, session: Session, ctx: RequestContext, file_id: UUID) -> bool:
        if self.route is not None:
            return False
        if self.grant is not None:
            return self.grant(session, ctx, file_id)
        source: sa.FromClause = self.table
        for other, on in self.joins:
            source = source.join(other, on)
        entity = sa.null() if self.entity is None else self.entity
        uploader = sa.null() if self.uploader is None else self.uploader
        rows = session.execute(
            select(entity.label("entity"), uploader.label("uploader"))
            .select_from(source)
            .where(self.table.c[self.column] == file_id)
        )
        principal = ctx.principal
        return any(
            (row.uploader is not None and row.uploader == principal.id)
            or holds(principal, self.permissions, self._needed(row.entity))
            for row in rows
        )

    def _needed(self, value: Any) -> Entities | Literal["*"]:
        if value is None and self.financial:
            return ALL_ENTITIES
        return _entities(value)

    def references(self, session: Session, file_id: UUID) -> list[ReferenceScope]:
        """The scope of every row that references ``file_id`` through this owner, among the rows
        ``session`` reads (``_bound_scope``): the row's entity where the owner states one, every
        entity where it states none — an owner read by a route included."""
        if self.referenced is not None:
            return [_bound_scope(found) for found in self.referenced(session, file_id)]
        source: sa.FromClause = self.table
        for other, on in self.joins:
            source = source.join(other, on)
        entity = sa.null() if self.entity is None else self.entity
        rows = session.execute(
            select(entity.label("entity"))
            .select_from(source)
            .where(self.table.c[self.column] == file_id)
        )
        return [_bound_scope(None if row.entity is None else _entities(row.entity)) for row in rows]


@dataclass(frozen=True, slots=True)
class PurposeAccess:
    """Who reads a file of one purpose: its owners, and the uploader when the purpose is uploaded
    through ``POST /files`` (an upload is read back by the person who uploaded it)."""

    owners: tuple[FileOwner, ...] = ()
    uploader: bool = False


# --- attachment subjects (T-PLT-30) ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AttachmentSubject:
    """A record type a file attaches to: who attaches (``write``), who reads (``read``), and the
    entities of one such record (``entities``; None when the session sees no such row, which is an
    unknown id and an id outside the entity scope alike, REQ-PLT-012). ``visible`` is a rule of
    the subject's own, which both reading and attaching must also pass; a subject read by that
    rule alone names no read permission."""

    write: frozenset[str]
    read: frozenset[str] | None
    entities: SubjectEntities
    # The "Entity" cell of the subject's 04 T-PLT-30 row.
    entity_of: str
    visible: Callable[[Session, RequestContext, UUID], bool] | None = None
    # What the 04 T-PLT-30 row calls the people ``visible`` admits.
    visible_of: str | None = None
    # A rule under which a principal attaches whatever it holds: the requester of an approval
    # request, while the request is pending (``own_pending_request``; R-100 (b)).
    own: Callable[[Session, Principal, UUID], bool] | None = None

    def readable(self, session: Session, ctx: RequestContext, subject_id: UUID) -> bool:
        return self._allowed(session, ctx, subject_id, self.read)

    def writable(self, session: Session, ctx: RequestContext, subject_id: UUID) -> bool:
        return self._allowed(session, ctx, subject_id, self.write)

    def _allowed(
        self,
        session: Session,
        ctx: RequestContext,
        subject_id: UUID,
        permissions: frozenset[str] | None,
    ) -> bool:
        entities = self.entities(session, subject_id)
        if entities is None:
            return False
        if permissions is not None and not holds(ctx.principal, permissions, entities):
            return False
        return self.visible is None or self.visible(session, ctx, subject_id)


def _request_entities(session: Session, subject_id: UUID) -> Entities | Literal["*"] | None:
    """The legal entities an approval request names (04 T-PLT-17 rev 1.104): the one of
    ``entity_id``, the several of ``entity_ids``, every entity for ``is_all_entities``
    (``ALL_ENTITIES``), none for a tenant-level request; None when the session sees no such
    request. A permission is needed for all of them at once (``holds``), as a decision needs one
    authority that covers them (item ATT-MULTI-ENTITY-1)."""
    row = session.execute(
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
        ).where(approval_request.c.id == subject_id)
    ).one_or_none()
    if row is None:
        return None
    if row.is_all_entities:
        return ALL_ENTITIES
    if row.entity_id is not None:
        return _entities(row.entity_id)
    return frozenset(UUID(str(value)) for value in row.entity_ids or ())


def _own_entity(table: sa.Table, column: str | None) -> SubjectEntities:
    """The subject row's own entity column (NULL names no entity), or a tenant-level subject."""

    def entities(session: Session, subject_id: UUID) -> Entities | None:
        value = sa.null() if column is None else table.c[column]
        row = session.execute(
            select(table.c.id, value.label("entity")).where(table.c.id == subject_id)
        ).one_or_none()
        return None if row is None else _entities(row.entity)

    return entities


def _through_contract(
    table: sa.Table, contract_id: sa.ColumnElement[Any], *joins: tuple[sa.Table, Any]
) -> SubjectEntities:
    """A subject that belongs to a contract, when it names one: the contract's contracting entity.
    A contract the session does not see (RLS-TE) hides the subject with it; a subject that names
    no contract is tenant-level."""

    def entities(session: Session, subject_id: UUID) -> Entities | None:
        source: sa.FromClause = table
        for other, on in joins:
            source = source.join(other, on)
        source = source.outerjoin(
            contract,
            sa.and_(contract.c.tenant_id == table.c.tenant_id, contract.c.id == contract_id),
        )
        row = session.execute(
            select(contract_id.label("contract_id"), contract.c.contracting_entity_id)
            .select_from(source)
            .where(table.c.id == subject_id)
        ).one_or_none()
        if row is None:
            return None
        if row.contract_id is None:
            return TENANT_LEVEL
        return None if row.contracting_entity_id is None else _entities(row.contracting_entity_id)

    return entities


def _ssp_book_entity(session: Session, subject_id: UUID) -> Entities | None:
    row = session.execute(
        select(ssp_book_version.c.id, ssp_book.c.entity_id)
        .select_from(
            ssp_book_version.join(
                ssp_book,
                sa.and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(ssp_book_version.c.id == subject_id)
    ).one_or_none()
    return None if row is None else _entities(row.entity_id)


def _own_pending(principal: Principal) -> sa.ColumnElement[bool]:
    """The approval requests the principal submitted that are still pending."""
    return sa.and_(
        approval_request.c.preparer_id == principal.id,
        approval_request.c.preparer_kind == principal.kind.value,
        approval_request.c.status == ApprovalRequestStatus.PENDING.value,
    )


def own_pending_request(session: Session, principal: Principal, approval_request_id: UUID) -> bool:
    """Whether the principal submitted this approval request and it is still ``PENDING``: its
    requester attaches evidence to it whatever permission it holds — the permission to make the
    request is what brought it there (04 T-PLT-30 Subjects rev 1.151; ruling R-100 (b), item
    ATT-REQUESTER-1). A decided, withdrawn or voided request gives its requester nothing."""
    if principal.id is None:
        return False
    return (
        session.execute(
            select(approval_request.c.id)
            .where(approval_request.c.id == approval_request_id, _own_pending(principal))
            .limit(1)
        ).first()
        is not None
    )


def has_pending_request(session: Session, principal: Principal) -> bool:
    """Whether the principal has a pending approval request of its own: it may upload the
    evidence it then attaches to it (``POST /files``, purpose ``ATTACHMENT``)."""
    if principal.id is None:
        return False
    return (
        session.execute(
            select(approval_request.c.id).where(_own_pending(principal)).limit(1)
        ).first()
        is not None
    )


def exception_item_readable(session: Session, ctx: RequestContext, item_id: UUID) -> bool:
    """The item is one the caller reads (``imports.exceptions.readable``; 04 T-PLT-30 Subjects
    rev 1.218, item EXC-IMPORT-SCOPE-1): the attachments of an exception item are read, and
    added, by the people who read the item. An item that names no entity is, by its own column, a
    tenant-level record, which any holder of a read permission would open — the finding of an
    import he cannot read, the quarantine of a group of another entity's contracts. An item the
    row policy hides was not found before this rule is asked."""
    # imported here: the imports domain stores its files through this module's readers
    from erev_api.domain.imports import exceptions

    return (
        session.execute(
            select(exception_item.c.id)
            .where(exception_item.c.id == item_id, exceptions.readable(ctx.principal))
            .limit(1)
        ).first()
        is not None
    )


def request_content_visible(
    session: Session, ctx: RequestContext, approval_request_id: UUID
) -> bool:
    """The request is one whose CONTENT the caller reads: the caller holds the permission of one
    of its steps for every entity of it in her own right, or reads its subject in full — one
    permission that reads it, for every entity (rev 1.319; until then: every entity in her own
    entity scope) — and prepared it, decided it, or holds such a permission through one
    delegation in force (API-R-09; 04 §16.10 "Entity scope of a request" rev 1.208:
    ``approval_queries.content_visible`` over the caller's decision authorities; item
    APR-CONTENT-SCOPE-1). A reader who covers only some of
    the request's entities lists the request and reads its header; its preview file and its
    attachments are content, and such a reader is answered as for a file that does not exist."""
    principal = ctx.principal
    authorities = approval_queries.decision_authorities(session, principal, at=ctx.now)
    return bool(
        approval_queries.content_readable(session, principal, authorities, [approval_request_id])
    )


_SUBJECT_WRITE: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "contract": frozenset({"contract.create"}),
        "modification": frozenset({"modification.create"}),
        "estimate_version": frozenset({"estimate.create"}),
        "ssp_book_version": frozenset({"ssp.create"}),
        "judgement_record": frozenset({"judgement.create"}),
        "manual_adjustment": frozenset({"adjustment.create"}),
        "reconciliation": frozenset({"recon.prepare"}),
        "sod_exception": frozenset({"user.manage", "access.approve"}),
        "exception_item": frozenset({"exception.resolve"}),
        "contract_event": frozenset({"event.record"}),
        "event_submission": frozenset({"event.record"}),
    }
)
# Any holder of a subject write permission may upload an attachment and attach it to an approval
# request they see.
ATTACH_PERMISSIONS: Final = frozenset().union(*_SUBJECT_WRITE.values())
# The people who read each record: the holders of its read permission (04 §15.3 — API-R-07,
# API-R-33, API-R-37, API-R-40, API-R-44 for the five below the SSP row) or of a permission that
# prepares or approves it. ``audit.read`` reads no record's attachments as such.
_CONTRACT_READ: Final = frozenset({"contract.read"})
ADJUSTMENT_READERS: Final = frozenset(
    {"contract.read", "adjustment.create", "adjustment.approve", "report.run"}
)
RECONCILIATION_READERS: Final = frozenset({"contract.read", "recon.prepare", "recon.signoff"})
_SUBJECT_READ: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "contract": _CONTRACT_READ,
        "modification": _CONTRACT_READ,
        "estimate_version": _CONTRACT_READ,
        "contract_event": _CONTRACT_READ,
        "event_submission": _CONTRACT_READ,
        "ssp_book_version": frozenset({"ssp.read"}),
        "judgement_record": frozenset({"contract.read", "config.read"}),
        "manual_adjustment": ADJUSTMENT_READERS,
        "reconciliation": RECONCILIATION_READERS,
        "sod_exception": frozenset({"role.manage", "user.manage", "access.approve"}),
        "exception_item": frozenset({"contract.read", "exception.resolve", "exception.waive"}),
    }
)

_ESTIMATE_OF_VERSION: Final = (
    estimate,
    sa.and_(
        estimate.c.tenant_id == estimate_version.c.tenant_id,
        estimate.c.id == estimate_version.c.estimate_id,
    ),
)
CONTRACT_ENTITY: Final = (
    "contract.contracting_entity_id of the contract the record names; tenant without one"
)
REQUEST_READERS: Final = "the readers of the request's content (API-R-09)"
ITEM_READERS: Final = "the readers of the item (API-R-44)"
# subject type → (the subject's own rule, which reading and attaching must also pass; what its
# 04 T-PLT-30 row calls the people the rule admits)
_SUBJECT_VISIBLE: Final[
    Mapping[str, tuple[Callable[[Session, RequestContext, UUID], bool], str]]
] = MappingProxyType({"exception_item": (exception_item_readable, ITEM_READERS)})
# subject type → (how the subject's entities are read, the "Entity" cell of its 04 T-PLT-30 row)
_SUBJECT_ENTITIES: Final[Mapping[str, tuple[SubjectEntities, str]]] = MappingProxyType(
    {
        "contract": (
            _own_entity(contract, "contracting_entity_id"),
            "contract.contracting_entity_id",
        ),
        "modification": (
            _own_entity(modification, "contracting_entity_id"),
            "modification.contracting_entity_id",
        ),
        "estimate_version": (
            _through_contract(estimate_version, estimate.c.contract_id, _ESTIMATE_OF_VERSION),
            CONTRACT_ENTITY,
        ),
        "ssp_book_version": (_ssp_book_entity, "ssp_book.entity_id"),
        "judgement_record": (
            _through_contract(judgement_record, judgement_record.c.contract_id),
            CONTRACT_ENTITY,
        ),
        "manual_adjustment": (
            _own_entity(manual_adjustment, "entity_id"),
            "manual_adjustment.entity_id",
        ),
        "reconciliation": (_own_entity(reconciliation, "entity_id"), "reconciliation.entity_id"),
        "sod_exception": (_own_entity(sod_exception, None), "tenant"),
        "exception_item": (_own_entity(exception_item, "entity_id"), "exception_item.entity_id"),
        "contract_event": (
            _own_entity(contract_event, "contracting_entity_id"),
            "contract_event.contracting_entity_id",
        ),
        "event_submission": (
            _own_entity(event_submission, "contracting_entity_id"),
            "event_submission.contracting_entity_id",
        ),
    }
)
# 04 T-PLT-30 "Subjects": every ``subject_type`` of ``ck_file_attachment__subject_type``.
ATTACHMENT_SUBJECTS: Final[Mapping[str, AttachmentSubject]] = MappingProxyType(
    {
        **{
            subject: AttachmentSubject(
                write=_SUBJECT_WRITE[subject],
                read=_SUBJECT_READ[subject],
                entities=entities,
                entity_of=entity_of,
                visible=_SUBJECT_VISIBLE[subject][0] if subject in _SUBJECT_VISIBLE else None,
                visible_of=_SUBJECT_VISIBLE[subject][1] if subject in _SUBJECT_VISIBLE else None,
            )
            for subject, (entities, entity_of) in _SUBJECT_ENTITIES.items()
        },
        "approval_request": AttachmentSubject(
            write=ATTACH_PERMISSIONS,
            # Read by whoever reads the request's content (``request_content_visible``): its
            # preparer, its deciders and the holders of a step's permission, whatever that
            # permission is — for every entity of the request (rev 1.208). An attachment is
            # evidence about the record, so a reader of the header alone neither lists it nor
            # attaches one; the requester attaches while the request is pending (``own``).
            read=None,
            entities=_request_entities,
            entity_of=("approval_request.entity_id, entity_ids; all entities with is_all_entities"),
            visible=request_content_visible,
            visible_of=REQUEST_READERS,
            own=own_pending_request,
        ),
    }
)


def attachment_subject_rows() -> list[tuple[str, str, str, str]]:
    """The registry as 04 T-PLT-30 tables it: (subject type, attach with, read with, entity). An
    approval request is read and attached to by its readers, whatever permission makes them one;
    an exception item by the holders of its permissions who also read the item (rev 1.218)."""
    rows: list[tuple[str, str, str, str]] = []
    for name, subject in ATTACHMENT_SUBJECTS.items():
        own_rule = "" if subject.visible_of is None else f"; {subject.visible_of}"
        rows.append(
            (
                name,
                ", ".join(sorted(subject.write))
                + own_rule
                + ("" if subject.own is None else f"; {REQUESTER_ATTACHES}"),
                (subject.visible_of or "")
                if subject.read is None
                else ", ".join(sorted(subject.read)) + own_rule,
                subject.entity_of,
            )
        )
    return rows


# --- owners with a rule of their own --------------------------------------------------------------


def _through_attachment(session: Session, ctx: RequestContext, file_id: UUID) -> bool:
    """A live attachment to a record the caller reads (REQ-PLT-035)."""
    attached = session.execute(
        select(file_attachment.c.subject_type, file_attachment.c.subject_id)
        .where(file_attachment.c.file_object_id == file_id, file_attachment.c.voided_at.is_(None))
        .distinct()
    ).all()
    return any(
        ATTACHMENT_SUBJECTS[str(subject_type)].readable(session, ctx, UUID(str(subject_id)))
        for subject_type, subject_id in attached
    )


def _through_request(session: Session, ctx: RequestContext, file_id: UUID) -> bool:
    """The impact preview of an approval request whose content the caller reads: its preparer
    and deciders, and the holders of a step's approval permission, for every entity of the
    request (REQ-PLT-015: the approver sees what is approved; rev 1.208: a reader who covers
    only some of the request's entities does not)."""
    ids = session.scalars(
        select(approval_request.c.id).where(approval_request.c.impact_preview_file_id == file_id)
    ).all()
    return any(request_content_visible(session, ctx, UUID(str(request_id))) for request_id in ids)


def _pool_of_run(session: Session, ctx: RequestContext, file_id: UUID) -> bool:
    """The transaction pool of an SSP calculator run (``parameters.pool_file_id``), read with the
    run (``ssp.read``). A run names no entity yet and its pool is transaction data, so the
    permission is needed for all entities (R-28)."""
    if not holds(ctx.principal, {"ssp.read"}, ALL_ENTITIES):
        return False
    return (
        session.execute(
            select(ssp_calculator_run.c.id)
            .where(ssp_calculator_run.c.parameters["pool_file_id"].astext == str(file_id))
            .limit(1)
        ).first()
        is not None
    )


def _attached_to(session: Session, file_id: UUID) -> list[Entities | Literal["*"] | None]:
    """The entities of the subject of every attachment of the file, voided or not: a voided
    attachment gives nobody the file to read, and the document was that record's all the same."""
    attached = session.execute(
        select(file_attachment.c.subject_type, file_attachment.c.subject_id)
        .where(file_attachment.c.file_object_id == file_id)
        .distinct()
    ).all()
    return [
        ATTACHMENT_SUBJECTS[str(subject_type)].entities(session, UUID(str(subject_id)))
        for subject_type, subject_id in attached
    ]


def _previewed_by(session: Session, file_id: UUID) -> list[Entities | Literal["*"] | None]:
    """The entities of every approval request whose impact preview the file is."""
    ids = session.scalars(
        select(approval_request.c.id).where(approval_request.c.impact_preview_file_id == file_id)
    ).all()
    return [_request_entities(session, UUID(str(request_id))) for request_id in ids]


def _pooled_by(session: Session, file_id: UUID) -> list[Entities | Literal["*"] | None]:
    """One entry per SSP calculator run that names the file as its pool: a run names no entity."""
    runs = session.scalars(
        select(ssp_calculator_run.c.id).where(
            ssp_calculator_run.c.parameters["pool_file_id"].astext == str(file_id)
        )
    ).all()
    return [None for _ in runs]


# --- stored impact previews (04 §16.10 "Who reads a stored preview", rev 1.300) -----------------

# The read permissions of each subject that retains the document of its dry run: those the
# owner's row of 04 T-PLT-29 named for the row's own entity until rev 1.300, asked since then
# for every entity the subject is bound to.
STORED_PREVIEW_READERS: Final[Mapping[ApprovalSubjectType, frozenset[str]]] = MappingProxyType(
    {
        ApprovalSubjectType.MODIFICATION: _CONTRACT_READ,
        ApprovalSubjectType.MANUAL_ADJUSTMENT: ADJUSTMENT_READERS,
    }
)


def stored_preview_entities(
    session: Session, subject_type: ApprovalSubjectType, subject_id: UUID
) -> Entities | Literal["*"]:
    """The entities the stored impact preview of a subject is bound to: those a request of the
    subject names — the contracting entities of every current member of its contract's
    combination group (R-87 (1)) — read by the kernel under the tenant's SYSTEM scope
    (``approvals.preparer_scope``; R-64 (1)), so that an entity the caller cannot read is
    named and not guessed. ``ALL_ENTITIES`` for a subject that spans every entity."""
    found = approvals.preparer_scope(session, subject_type, subject_id)
    return ALL_ENTITIES if found.all_entities else found.ids


def stored_preview_readable(
    session: Session, principal: Principal, subject_type: ApprovalSubjectType, subject_id: UUID
) -> bool:
    """Whether ``principal`` is answered the impact preview a modification or a manual adjustment
    retains (04 §16.10 "Who reads a stored preview", rev 1.300; item MOD-PREVIEW-READ-SCOPE-1):
    it holds one read permission of the subject for EVERY entity the subject is bound to. The
    document is the dry run of the whole combination group — the group's figures, the journal
    lines of every entity — so the entity of the row alone does not decide. It is a read, asked
    by permission; the own-entity-scope question of a preview request and of a submission is
    the kernel's (``approvals.refuse_outside_scope``) and is not this one.

    ONE function for the doors of a stored preview: the read of a modification, the read of a
    manual adjustment, the file's own routes through both owners below — and, since rev 1.314,
    the summary of the same dry run in the answer of its job (``preview_summary_readable``)."""
    permissions = STORED_PREVIEW_READERS[ApprovalSubjectType(subject_type)]
    if holds(principal, permissions, ALL_ENTITIES):
        return True  # whatever the subject is bound to: nothing is read for the answer
    return holds(principal, permissions, stored_preview_entities(session, subject_type, subject_id))


# --- the summary of a dry run in its job's answer (04 API-S-Job, rev 1.314) ----------------------

# The subject of a preview of pending events: they are stored nowhere and take the set of their
# contract (``approvals.contract_scope``).
PENDING_EVENTS: Final = approvals.CONTRACT_SUBJECT
# A dry run that retains no document — the preview of an estimate version, and of the pending
# events of a contract — answers its summary in the result of its job alone. It is read with the
# contract's read permission, which the routes of both subjects ask (04 §15.3).
UNSTORED_PREVIEW_READERS: Final = _CONTRACT_READ


def preview_summary_readable(
    session: Session, principal: Principal, subject_type: str, subject_id: UUID
) -> bool:
    """Whether ``principal`` is answered the summary of a dry run of the subject where the job
    that ran it answers one (04 API-S-Job and §16.10 "Who reads a stored preview", rev 1.314;
    item PREVIEW-JOB-RESULT-SCOPE-1): it holds one read permission of the subject for EVERY
    entity the subject is bound to — the question of ``stored_preview_readable``, for each of the
    four subjects a dry run has.

    For a modification and a manual adjustment it IS that function: both retain the document of
    a dry run, and the summary in a job's result is a dry run of the same subject — the very
    summary a modification then retains — so the job's answer is a fourth door of the stored
    preview. An estimate version and the pending events of a contract
    (``PENDING_EVENTS``) retain no document, so the job's answer is the only door of their
    summary: ``UNSTORED_PREVIEW_READERS`` for the entities the preview route asks its caller
    about (``approvals.preparer_scope``, ``approvals.contract_scope``).

    False for a subject that is gone, which names no entity any more — unless the permission is
    held for all entities, where nothing is read for the answer."""
    kind = None if subject_type == PENDING_EVENTS else ApprovalSubjectType(subject_type)
    try:
        if kind is not None and kind in STORED_PREVIEW_READERS:
            return stored_preview_readable(session, principal, kind, subject_id)
        if holds(principal, UNSTORED_PREVIEW_READERS, ALL_ENTITIES):
            return True
        found = (
            approvals.contract_scope(session, subject_id)
            if kind is None
            else approvals.preparer_scope(session, kind, subject_id)
        )
    except SubjectNotVisible:
        return False
    except Problem as refused:
        if refused.slug != "not-found":
            raise
        return False
    entities: Entities | Literal["*"] = ALL_ENTITIES if found.all_entities else found.ids
    return holds(principal, UNSTORED_PREVIEW_READERS, entities)


def _retaining(session: Session, table: sa.Table, file_id: UUID) -> list[UUID]:
    """The rows of ``table`` the session sees whose retained impact preview the file is."""
    found = session.scalars(select(table.c.id).where(table.c.impact_preview_file_id == file_id))
    return [UUID(str(value)) for value in found]


def _through_modification(session: Session, ctx: RequestContext, file_id: UUID) -> bool:
    """The stored preview of a modification the caller reads, for a caller who is answered it
    (``stored_preview_readable``)."""
    return any(
        stored_preview_readable(
            session, ctx.principal, ApprovalSubjectType.MODIFICATION, modification_id
        )
        for modification_id in _retaining(session, modification, file_id)
    )


def _through_adjustment(session: Session, ctx: RequestContext, file_id: UUID) -> bool:
    """The stored preview of a manual adjustment the caller reads, likewise."""
    return any(
        stored_preview_readable(
            session, ctx.principal, ApprovalSubjectType.MANUAL_ADJUSTMENT, adjustment_id
        )
        for adjustment_id in _retaining(session, manual_adjustment, file_id)
    )


def _modification_previews(session: Session, file_id: UUID) -> list[Entities | Literal["*"] | None]:
    """The entities of every modification whose stored preview the file is: those the subject
    is bound to, which a command that destroys the document is bound to as well."""
    return [
        stored_preview_entities(session, ApprovalSubjectType.MODIFICATION, modification_id)
        for modification_id in _retaining(session, modification, file_id)
    ]


def _adjustment_previews(session: Session, file_id: UUID) -> list[Entities | Literal["*"] | None]:
    """The entities of every manual adjustment whose stored preview the file is, likewise."""
    return [
        stored_preview_entities(session, ApprovalSubjectType.MANUAL_ADJUSTMENT, adjustment_id)
        for adjustment_id in _retaining(session, manual_adjustment, file_id)
    ]


def _preview_rule(subject_type: ApprovalSubjectType, subject: str) -> str:
    """The name 04 T-PLT-29 gives the rule of a stored preview's owner: its read permissions in
    code order — one of them — for every entity of the subject."""
    codes = sorted(STORED_PREVIEW_READERS[subject_type])
    held = codes[0] if len(codes) == 1 else f"{', '.join(codes[:-1])} or {codes[-1]}"
    return f"{held} for every entity the {subject} is bound to (§16.10)"


MODIFICATION_PREVIEW_RULE: Final = _preview_rule(ApprovalSubjectType.MODIFICATION, "modification")
ADJUSTMENT_PREVIEW_RULE: Final = _preview_rule(ApprovalSubjectType.MANUAL_ADJUSTMENT, "adjustment")
_LOCK_OF_SNAPSHOT: Final = (
    period_lock,
    sa.and_(
        period_lock.c.tenant_id == lock_snapshot.c.tenant_id,
        period_lock.c.id == lock_snapshot.c.period_lock_id,
    ),
)
ATTACHMENT_RULE: Final = "the subject of a live attachment (T-PLT-30)"
REQUEST_RULE: Final = "the readers of the request's content (API-R-09)"
POOL_RULE: Final = "ssp.read for all entities, for the pool a run names in parameters.pool_file_id"
_ATTACHED: Final = FileOwner(
    file_attachment,
    "file_object_id",
    grant=_through_attachment,
    rule=ATTACHMENT_RULE,
    referenced=_attached_to,
)
_CONFIG_READ: Final = frozenset({"config.read"})
# The source and the diff of an import are read by the readers of the import (API-R-43,
# ``contract.read``) and by its approvers, for every entity the upload names
# (``named_entity_ids``; R-86 (f)), and by the upload's own uploader. ``import.upload`` brings
# data in and reads nothing another member brought (R-98).
IMPORT_READERS: Final = frozenset({"contract.read", "import.approve"})
EVIDENCE_DOWNLOAD_ROUTE: Final = "GET /evidence-packs/{id}/download"
REPORT_OUTPUT_ROUTE: Final = "GET /report-runs/{id}/output"
JOURNAL_DOWNLOAD_ROUTE: Final = "GET /journal-batches/{id}/download"
SNAPSHOT_MANIFEST_ROUTE: Final = "GET /tenant/snapshots/{id}/manifest"
# Read only by the component that wrote it; no route serves the bytes.
INTERNAL: Final = "internal"

# 04 T-PLT-29 "Read access": every E-68 purpose, its owners and the permission that reads each.
FILE_READ_ACCESS: Final[Mapping[FilePurpose, PurposeAccess]] = MappingProxyType(
    {
        FilePurpose.IMPORT_SOURCE: PurposeAccess(
            uploader=True,
            owners=(
                FileOwner(
                    import_upload,
                    "file_object_id",
                    IMPORT_READERS,
                    import_upload.c.named_entity_ids,
                    financial=True,
                    uploader=import_upload.c.created_by,
                ),
                FileOwner(
                    ssp_calculator_run,
                    "parameters",
                    grant=_pool_of_run,
                    rule=POOL_RULE,
                    referenced=_pooled_by,
                ),
                FileOwner(
                    reconciliation,
                    "source_file_id",
                    RECONCILIATION_READERS,
                    reconciliation.c.entity_id,
                ),
            ),
        ),
        FilePurpose.ATTACHMENT: PurposeAccess(uploader=True, owners=(_ATTACHED,)),
        FilePurpose.SSP_STUDY: PurposeAccess(uploader=True, owners=(_ATTACHED,)),
        FilePurpose.LEGACY_DATABASE: PurposeAccess(
            uploader=True,
            owners=(
                FileOwner(
                    migration_batch,
                    "source_file_id",
                    frozenset({"migration.run", "migration.approve"}),
                    financial=True,
                ),
            ),
        ),
        FilePurpose.REPORT_OUTPUT: PurposeAccess(
            owners=(
                FileOwner(report_run, "output_file_id", route=REPORT_OUTPUT_ROUTE),
                FileOwner(report_run, "manifest_file_id", route=REPORT_OUTPUT_ROUTE),
                FileOwner(
                    registry_version,
                    "impact_simulation_file_id",
                    _CONFIG_READ,
                    registry_version.c.entity_id,
                    financial=True,
                ),
                FileOwner(
                    rule_set_version, "impact_simulation_file_id", _CONFIG_READ, financial=True
                ),
                FileOwner(
                    account_mapping_version,
                    "impact_simulation_file_id",
                    _CONFIG_READ,
                    financial=True,
                ),
                FileOwner(
                    ssp_calculator_run,
                    "result_file_id",
                    frozenset({"ssp.read"}),
                    financial=True,
                ),
                FileOwner(
                    period_lock, "diff_report_file_id", _CONFIG_READ, period_lock.c.entity_id
                ),
                FileOwner(
                    access_review_campaign, "snapshot_file_id", frozenset({"access.approve"})
                ),
                FileOwner(
                    control_execution,
                    "exceptions_file_id",
                    frozenset({AUDIT_READ}),
                    control_execution.c.entity_id,
                    financial=True,
                ),
                FileOwner(idempotency_record, "response_file_id", route=INTERNAL),
            ),
        ),
        FilePurpose.EVIDENCE_PACK: PurposeAccess(
            owners=(
                FileOwner(
                    evidence_pack,
                    "file_id",
                    entity=evidence_pack.c.entity_id,
                    route=EVIDENCE_DOWNLOAD_ROUTE,
                ),
            ),
        ),
        FilePurpose.JOURNAL_EXPORT: PurposeAccess(
            owners=(
                FileOwner(journal_batch, "export_file_id", route=JOURNAL_DOWNLOAD_ROUTE),
                FileOwner(journal_batch, "detail_file_id", route=INTERNAL),
            ),
        ),
        FilePurpose.SNAPSHOT_DATASET: PurposeAccess(
            owners=(
                FileOwner(
                    lock_snapshot,
                    "file_id",
                    frozenset({"report.run"}),
                    period_lock.c.entity_id,
                    joins=(_LOCK_OF_SNAPSHOT,),
                ),
                FileOwner(tenant_snapshot, "manifest_file_id", route=SNAPSHOT_MANIFEST_ROUTE),
            ),
        ),
        FilePurpose.IMPACT_PREVIEW: PurposeAccess(
            owners=(
                FileOwner(
                    approval_request,
                    "impact_preview_file_id",
                    grant=_through_request,
                    rule=REQUEST_RULE,
                    referenced=_previewed_by,
                ),
                FileOwner(
                    modification,
                    "impact_preview_file_id",
                    grant=_through_modification,
                    rule=MODIFICATION_PREVIEW_RULE,
                    referenced=_modification_previews,
                ),
                FileOwner(
                    manual_adjustment,
                    "impact_preview_file_id",
                    grant=_through_adjustment,
                    rule=ADJUSTMENT_PREVIEW_RULE,
                    referenced=_adjustment_previews,
                ),
                FileOwner(
                    import_upload,
                    "diff_file_id",
                    IMPORT_READERS,
                    import_upload.c.named_entity_ids,
                    financial=True,
                    uploader=import_upload.c.created_by,
                ),
            ),
        ),
        FilePurpose.AUDIT_DIGEST: PurposeAccess(
            owners=(
                FileOwner(audit_chain_verification, "digest_file_id", frozenset({AUDIT_READ})),
            ),
        ),
        FilePurpose.POSTING_RESPONSE: PurposeAccess(
            owners=(FileOwner(posting_ack, "response_file_id", route=INTERNAL),),
        ),
        # Written by features that are not built (AI assistance): no record owns such a file yet,
        # so nobody reads one. The feature that writes the first names its owner here.
        FilePurpose.AI_PROMPT_LOG: PurposeAccess(),
        FilePurpose.AI_DOCUMENT_TEXT: PurposeAccess(),
    }
)


def every_owner() -> tuple[FileOwner, ...]:
    """Each owner of the registry once, whatever the purposes it owns files of (an attachment
    owns files of two)."""
    found: dict[str, FileOwner] = {}
    for access in FILE_READ_ACCESS.values():
        for owner in access.owners:
            found.setdefault(owner.ref, owner)
    return tuple(found.values())


def referencing_scopes(tenant_id: UUID, file_id: UUID) -> list[ReferenceScope]:
    """What a command that destroys the file is bound to (04 T-PLT-29 "Shred scope", rev 1.225;
    item FILE-SHRED-SCOPE-1, B3): the scope of every record that references the file — through
    any owner of the registry, whatever the file's purpose, as the evidence lookup asks every
    reference; an attachment through its subject, voided or not — read over every entity of the
    tenant in a read-only session of its own: a record of an entity outside the caller's scope
    references its file too, and is exactly the one that matters. A file that no record
    references is bound to every entity: nothing ties it to the entities of whoever asks. The
    upload record of a file (T-PLT-49) names who brought the bytes and is no such record."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        found = [scope for owner in every_owner() for scope in owner.references(session, file_id)]
    return found or [EVERY_ENTITY]


def file_owners() -> frozenset[str]:
    """``<table>.<column>`` of every owner the registry names (the architecture test compares it
    with the columns of the schema that hold a file id)."""
    return frozenset(owner.ref for access in FILE_READ_ACCESS.values() for owner in access.owners)


def read_access_rows() -> list[tuple[str, str, str, str]]:
    """The registry as 04 T-PLT-29 tables it: (purpose, owner, read by, entity) per owner, a
    purpose's uploader first, and one row for a purpose nothing owns yet."""
    rows: list[tuple[str, str, str, str]] = []
    for purpose, access in FILE_READ_ACCESS.items():
        if access.uploader:
            rows.append((purpose.value, "uploader", "the principal that uploaded the file", "-"))
        rows.extend(
            (purpose.value, owner.ref, owner.read_by, owner.entity_of) for owner in access.owners
        )
        if not access.uploader and not access.owners:
            rows.append((purpose.value, "none", "nobody", "-"))
    return rows


def _stored_by(principal: Principal, row: Mapping[Any, Any]) -> bool:
    """Whether the principal stored the row: the first uploader, whose facts the row carries."""
    return (
        principal.id is not None
        and row["created_by"] == principal.id
        and str(row["created_by_kind"]) == principal.kind.value
    )


def _upload_of(session: Session, principal: Principal, file_id: UUID) -> Mapping[str, Any] | None:
    """The principal's own upload of the file (T-PLT-49): its file name and time."""
    if principal.id is None:
        return None
    found = (
        session.execute(
            select(file_upload.c.original_filename, file_upload.c.uploaded_at).where(
                file_upload.c.file_object_id == file_id,
                file_upload.c.uploaded_by == principal.id,
                file_upload.c.uploaded_by_kind == principal.kind.value,
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if found is None else dict(found)


def uploaded_by(session: Session, principal: Principal, row: Mapping[Any, Any]) -> bool:
    """Whether the principal uploaded the file: it stored the row, or it uploaded the same bytes
    again. Identical content of one purpose is one row (content identity, T-PLT-29), so a second
    uploader gets the stored row's id and ``created_by`` names only the first; the row of
    T-PLT-49 ``file_upload`` that ``record_upload`` writes for each uploader is the record of
    it (04 rev 1.189; until then the ``file.upload`` audit fact was read for it)."""
    return (
        _stored_by(principal, row)
        or _upload_of(session, principal, UUID(str(row["id"]))) is not None
    )


def record_upload(
    session: Session,
    principal: Principal,
    row: Mapping[Any, Any],
    *,
    original_filename: str | None,
    at: datetime,
) -> bool:
    """Record that the principal uploaded the file's bytes (T-PLT-49), with its own file name
    and time; True when this is its first upload of them — a later one adds no row and keeps
    the first name and time. ``POST /files`` calls it for the principal that stores a file and
    for each other principal that uploads the same bytes."""
    written = session.execute(
        pg_insert(file_upload)
        .values(
            tenant_id=principal.tenant_id,
            file_object_id=row["id"],
            uploaded_by=principal.id,
            uploaded_by_kind=principal.kind.value,
            original_filename=original_filename,
            uploaded_at=at,
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "file_object_id", "uploaded_by", "uploaded_by_kind"]
        )
        .returning(file_upload.c.file_object_id)
    ).first()
    return written is not None


def _as_uploaded(
    row: Mapping[Any, Any], principal: Principal, upload: Mapping[str, Any]
) -> Mapping[str, Any]:
    """The stored id and content facts with the uploader's own file name, time and identity."""
    return MappingProxyType(
        {
            **row,
            "original_filename": upload["original_filename"],
            "created_at": upload["uploaded_at"],
            "created_by": principal.id,
            "created_by_kind": principal.kind.value,
        }
    )


def uploader_view(
    session: Session, principal: Principal, row: Mapping[Any, Any]
) -> Mapping[str, Any]:
    """The file as ``POST /files`` answers it to the principal that just uploaded its bytes:
    the stored id and content facts with the CALLER's file name, time and identity — never the
    first uploader's (04 T-PLT-29 "Uploads of the same bytes"; ruling R-111 (5))."""
    if _stored_by(principal, row):
        return MappingProxyType(dict(row))
    upload = _upload_of(session, principal, UUID(str(row["id"])))
    return MappingProxyType(dict(row)) if upload is None else _as_uploaded(row, principal, upload)


def shown(
    session: Session, ctx: RequestContext, row: Mapping[Any, Any]
) -> Mapping[str, Any] | None:
    """The ``file_object`` row as the caller may see it, or None when the caller may not read the
    file: the stored row for the principal that stored it and for a caller who reads a record
    that owns the file (``FILE_READ_ACCESS``); for a caller who reads it only as an uploader of
    the same bytes, the stored id and content facts with that caller's own file name, time and
    identity (04 T-PLT-29 "Uploads of the same bytes"). An operator never may: a support grant's
    scope names no file purpose (T-PLT-33 ``READ_ONLY``; REQ-PLT-036)."""
    principal = ctx.principal
    if principal.kind is PrincipalKind.OPERATOR:
        return None
    access = FILE_READ_ACCESS[FilePurpose(row["purpose"])]
    if access.uploader and _stored_by(principal, row):
        return MappingProxyType(dict(row))
    file_id = UUID(str(row["id"]))
    if any(owner.allows(session, ctx, file_id) for owner in access.owners):
        return MappingProxyType(dict(row))
    upload = _upload_of(session, principal, file_id) if access.uploader else None
    return None if upload is None else _as_uploaded(row, principal, upload)


def readable(session: Session, ctx: RequestContext, row: Mapping[Any, Any]) -> bool:
    """Whether the caller may read the ``file_object`` row: as an uploader of an upload, or
    through a record that owns the file (``shown``)."""
    return shown(session, ctx, row) is not None


def bound(session: Session, ctx: RequestContext, file_id: UUID) -> Mapping[str, Any] | None:
    """The ``file_object`` row a command binds for its caller: the row of ``file_id`` when the
    id names a file the session sees that the caller may read (``readable``), else None. An id
    that names no file and a file the caller may not read are one answer, so the command answers
    both as it answers a missing file — before it looks at the row's purpose, media type, shred
    state, name or content (04 T-PLT-29 "Binding"; ruling R-111 (1), item FILE-BIND-READABLE-1).
    Every request member that names a file is bound here (``FILE_BINDINGS``)."""
    row = (
        session.execute(select(file_object).where(file_object.c.id == file_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else shown(session, ctx, row)


@dataclass(frozen=True, slots=True)
class FileBinding:
    """A request member that names a file (04 T-PLT-29 "Binding"): the route that takes it, the
    function that binds it through ``bound`` — ``<module>:<function>``, None while no command
    uses the member — and what a missing or unreadable file is answered, in the words of the
    member's 04 row."""

    route: str
    binder: str | None
    answer: str


# Why ``ReplayPlanItemIn.file_id`` has no binder: the command refuses REPLAY bodies whole.
REPLAY_NOT_BUILT: Final = "refused before any use: mode REPLAY is not built"
FILE_BINDINGS: Final[Mapping[str, FileBinding]] = MappingProxyType(
    {
        "AttachmentCreateIn.file_object_id": FileBinding(
            "POST /attachments",
            "erev_api.domain.platform.attachments:attach",
            "422 validation-failed on file_object_id",
        ),
        "EventAppendIn.evidence_file_ids": FileBinding(
            "POST /contracts/{id}/events",
            "erev_api.domain.contracts.events:evidence_errors",
            "422 validation-failed on evidence_file_ids[i], rule T-PLT-29",
        ),
        "ImportCreateIn.file_id": FileBinding(
            "POST /imports",
            "erev_api.domain.imports.upload:_file",
            "422 validation-failed on file_id, rule API-R-43",
        ),
        "MigrationCreateIn.source_file_id": FileBinding(
            "POST /migrations",
            "erev_api.domain.migration.commands:recognise_stored_source",
            "404 not-found",
        ),
        "ReconciliationAttachIn.file_id": FileBinding(
            "POST /reconciliations/{id}/attach-trial-balance",
            "erev_api.domain.close.reconciliations:request_trial_balance",
            "422 validation-failed on file_id, rule REQ-CLS-016",
        ),
        "ReplayPlanItemIn.file_id": FileBinding(
            "POST /migrations/{id}/import", None, REPLAY_NOT_BUILT
        ),
        "SspCalculatorParametersIn.pool_file_id": FileBinding(
            "POST /ssp-calculator-runs",
            "erev_api.domain.ssp.calculator:_pool_errors",
            "422 validation-failed on parameters.pool_file_id, rule BR-SSP-04",
        ),
    }
)


def binding_rows() -> list[tuple[str, str, str]]:
    """The registry as 04 T-PLT-29 "Binding" tables it: (request member, route, the answer of a
    file that is missing or that the caller may not read), by request member."""
    return [
        (member, binding.route, binding.answer) for member, binding in sorted(FILE_BINDINGS.items())
    ]
