"""The evidence references of ``file_object`` (security finding SC-6; supervisor rulings R-30, R-49
and R-86; 05 PRV-06, PRV-07 b; 04 T-PLT-29, table 15.4-B ``FILE_EVIDENCE_HELD`` and
``FILE_SHRED_APPROVAL_REQUIRED``; runbook RB-14).

A file that is the evidence of a standing record is not shredded by one person: ``file.shred``
refuses BY REFERENCE, whatever the file's retention columns say (no retention date is invented).
This module is the one registry the commands consult.

``EVIDENCE`` names every column that references a file as evidence, how the refusal names the
record and, where only some rows stand, which. There are two kinds of hold:

- no override in 1.0 (R-49 (b)): lock datasets, journal batch files, report outputs of locked
  runs, impact previews, audit digests — and the source of an import that is submitted, approved
  or being committed, whose erasure path is "have it rejected or withdrawn first". The refusal is
  the recorded outcome of the request (``FILE_EVIDENCE_HELD``);
- lifted by an approval (``approval``; R-49 (a), R-86 (b), (c)): an uploaded document that may
  carry personal data AND that a record rests on — the source of a committed import, the source
  file of a reconciliation that has been signed, the legacy database of a migration whose capture
  is relied on, the SSP study of a version that has left DRAFT, the attachment a manual adjustment
  at or above its threshold needed, the evidence of an event submission that is submitted,
  approved or applied, and the evidence of a recorded contract event (item EVT-EVIDENCE-1; 04
  rev 1.268). ``file.shred`` answers ``FILE_SHRED_APPROVAL_REQUIRED``, and
  ``file.request_shred`` opens the ``EVIDENCE_SHRED`` approval a Controller decides
  (``erev_api.domain.platform.evidence_shred``), so that no file is held without a path by which
  a privacy erasure can still be approved.

``NOT_EVIDENCE`` names the foreign keys to ``file_object`` that are not evidence, each with its
reason. ``backend/tests/architecture/test_file_evidence_registry.py`` replays the migration chain
and fails when a foreign key to ``file_object`` is in neither, so a new table that stores a file
reference has to decide.

``holds`` answers under EVERY entity of the tenant: a journal batch or a period lock of an entity
outside the caller's scope holds its file all the same, so the lookup runs in a read-only session
of its own with entity scope ``*`` (the caller has the ``file_object`` row locked; a row that
comes to reference the file later references a shredded file). It returns EVERY standing record,
because an approval lifts the holds it names and no other: a file that a second record holds
without override stays refused, whatever else holds it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Table, Text, and_, cast, exists, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals.subjects import ABOVE_THRESHOLD
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import metadata
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ConfigStatus,
    FilePurpose,
    ImportStatus,
    ManualAdjustmentStatus,
    MigrationStatus,
    ModificationStatus,
    ReconciliationStatus,
)

__all__ = [
    "APPROVAL_MESSAGE",
    "EVIDENCE",
    "HELD_MESSAGE",
    "NOT_EVIDENCE",
    "RULE_APPROVAL_REQUIRED",
    "RULE_EVIDENCE_HELD",
    "EvidenceReference",
    "Hold",
    "first_refusing",
    "held_message",
    "held_rule",
    "holding",
    "holding_in",
    "holds",
    "holds_in",
    "pending_on",
]

RULE_EVIDENCE_HELD: Final = "FILE_EVIDENCE_HELD"  # 04 table 15.4-B (rev 1.107); PRD IMP-128
# 04 table 15.4-B (rev 1.142); PRD IMP-129; rulings R-49 (a) and R-86 (b), (c)
RULE_APPROVAL_REQUIRED: Final = "FILE_SHRED_APPROVAL_REQUIRED"
HELD_MESSAGE: Final = (
    "This file is {record}. It is kept while that record stands and cannot be shredded."
)
APPROVAL_MESSAGE: Final = (
    "This file is {record}. It is kept while that record stands; to erase it, request its "
    "shredding, which a Controller approves."
)
# R-49 (a): the erasure path of an import source before its commit.
WITHDRAW_FIRST: Final = "Have the import rejected, or its approval request withdrawn, first."
# R-30 / R-49 (a): the statuses in which an import holds its source.
IMPORT_PENDING: Final = (
    ImportStatus.SUBMITTED.value,
    ImportStatus.APPROVED.value,
    ImportStatus.COMMITTING.value,
)
# R-86 (b): a reconciliation holds its source file while the row carries a sign-off — every E-59
# status but DRAFT. PREPARED, REVIEWED and CERTIFIED are signed by a person (a row superseded by
# a later generation keeps its status); AUTO_CERTIFIED is certified by rule (REQ-CLS-017);
# REOPENED is reached only from a signed status and keeps its sign-offs and its lock.
RECONCILIATION_SIGNED: Final = (
    ReconciliationStatus.PREPARED.value,
    ReconciliationStatus.AUTO_CERTIFIED.value,
    ReconciliationStatus.REVIEWED.value,
    ReconciliationStatus.CERTIFIED.value,
    ReconciliationStatus.REOPENED.value,
)
# R-86 (b): a migration batch holds its legacy database while its capture is relied on — from the
# import that takes the capture (T-MIG-01 ``capture_operation_id``, written with IMPORTING) to the
# promotion. Before it (UPLOADED, PROFILING, PROFILED) no capture exists; a FAILED or CANCELLED
# batch has released its source (``ux_migration_batch__source`` excludes exactly those two).
MIGRATION_CAPTURED: Final = (
    MigrationStatus.IMPORTING.value,
    MigrationStatus.IMPORTED.value,
    MigrationStatus.RECONCILED.value,
    MigrationStatus.SUBMITTED.value,
    MigrationStatus.PROMOTED.value,
)
# R-86 (c): the SSP study is evidence once its version has left DRAFT and is not rejected or
# withdrawn (E-12; a rejected or withdrawn version returns to DRAFT, PRD SM-04).
SSP_VERSION_NOT_SUBMITTED: Final = (
    ConfigStatus.DRAFT.value,
    ConfigStatus.REJECTED.value,
    ConfigStatus.WITHDRAWN.value,
)
# R-86 (c): the attachment a manual adjustment needed is evidence once the adjustment is submitted
# (E-94; PRD SM-10; BUILD_SPEC CLO-12). SUBMITTED covers a pending request and an adjustment
# deferred past lock; a DRAFT — never submitted, withdrawn, voided as stale, returned for revision
# — and a REJECTED adjustment were never in force.
ADJUSTMENT_SUBMITTED: Final = (
    ManualAdjustmentStatus.SUBMITTED.value,
    ManualAdjustmentStatus.APPROVED.value,
    ManualAdjustmentStatus.POSTED.value,
)
# A VOIDED adjustment holds its attachment only when it was applied (``applied_event_id``): its
# lines and their reversal stand in the ledger. A DRAFT that was discarded is VOIDED too and
# holds nothing.
ADJUSTMENT_VOIDED: Final = ManualAdjustmentStatus.VOIDED.value
SSP_VERSION_SUBJECT: Final = "ssp_book_version"  # T-PLT-30 ``subject_type``
ADJUSTMENT_SUBJECT: Final = "manual_adjustment"
# Item EVT-EVIDENCE-1 (04 T-PLT-29 evidence references rev 1.268; the supervisor's ruling of
# 2026-10-02). The evidence of an event submission is attached to its approval request
# (``contracts.events._submit``); it is evidence while the submission stands — submitted, approved
# or applied. A rejected, withdrawn or voided submission put nothing in force and holds nothing.
REQUEST_SUBJECT: Final = "approval_request"
EVENT_SUBMISSION_SUBJECTS: Final = (
    ApprovalSubjectType.MANUAL_EVENT.value,
    ApprovalSubjectType.STEP1_EVENT.value,
    ApprovalSubjectType.ATTRIBUTE_CHANGE.value,
)
SUBMISSION_STANDING: Final = (
    ModificationStatus.SUBMITTED.value,
    ModificationStatus.APPROVED.value,
    ModificationStatus.APPLIED.value,
)
# A live attachment of a contract event is the evidence of a recorded fact, whichever road wrote
# it — the approval of the request, or the caller of a direct append.
EVENT_SUBJECT: Final = "contract_event"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """One column that references a ``file_object`` row as the evidence of its record."""

    table: str
    column: str
    record: str  # names the record in the refusal; ``{label}`` takes the row's label value
    # the rows whose record stands; None = every row that references the file
    standing: Callable[[Table], ColumnElement[bool]] | None = None
    label: str | None = None  # a column of the row that names it for the person who reads
    advice: str | None = None  # what lifts the hold, where something does
    # R-49 (a), R-86: the hold is lifted by an approved EVIDENCE_SHRED request, never by one person
    approval: bool = False
    # the label read from another table (the subject of an attachment); excludes ``label``
    label_of: Callable[[Table], ColumnElement[Any]] | None = None
    # the legal entity, or the entities, of the record (a uuid or a uuid[] expression); None = the
    # record has no entity, so the approval that lifts its hold covers every entity (R-25, R-41)
    entities: Callable[[Table], ColumnElement[Any]] | None = None


def _table(name: str) -> Table:
    return metadata.tables[f"erev.{name}"]


def _pending(table: Table) -> ColumnElement[bool]:
    found: ColumnElement[bool] = table.c.status.in_(IMPORT_PENDING)
    return found


def _committed(table: Table) -> ColumnElement[bool]:
    found: ColumnElement[bool] = table.c.status == ImportStatus.COMMITTED.value
    return found


def _as_locked(table: Table) -> ColumnElement[bool]:
    found: ColumnElement[bool] = table.c.period_lock_id.is_not(None)
    return found


def _signed(table: Table) -> ColumnElement[bool]:
    found: ColumnElement[bool] = table.c.status.in_(RECONCILIATION_SIGNED)
    return found


def _captured(table: Table) -> ColumnElement[bool]:
    found: ColumnElement[bool] = table.c.status.in_(MIGRATION_CAPTURED)
    return found


def _ssp_study(table: Table) -> ColumnElement[bool]:
    """A live ``SSP_STUDY`` attachment (``ssp.queries.study_attachment_ids``) of a version that
    has left DRAFT and is not rejected or withdrawn."""
    version, stored = _table("ssp_book_version"), _table("file_object")
    return and_(
        table.c.subject_type == SSP_VERSION_SUBJECT,
        table.c.voided_at.is_(None),
        exists().where(
            stored.c.tenant_id == table.c.tenant_id,
            stored.c.id == table.c.file_object_id,
            stored.c.purpose == FilePurpose.SSP_STUDY.value,
        ),
        exists().where(
            version.c.tenant_id == table.c.tenant_id,
            version.c.id == table.c.subject_id,
            version.c.status.not_in(SSP_VERSION_NOT_SUBMITTED),
        ),
    )


def _ssp_version_label(table: Table) -> ColumnElement[Any]:
    version, book = _table("ssp_book_version"), _table("ssp_book")
    return (
        select(book.c.code.concat(" version ").concat(cast(version.c.version_no, Text)))
        .where(
            version.c.tenant_id == table.c.tenant_id,
            version.c.id == table.c.subject_id,
            book.c.tenant_id == version.c.tenant_id,
            book.c.id == version.c.ssp_book_id,
        )
        .scalar_subquery()
    )


def _ssp_book_entity(table: Table) -> ColumnElement[Any]:
    version, book = _table("ssp_book_version"), _table("ssp_book")
    return (
        select(book.c.entity_id)
        .where(
            version.c.tenant_id == table.c.tenant_id,
            version.c.id == table.c.subject_id,
            book.c.tenant_id == version.c.tenant_id,
            book.c.id == version.c.ssp_book_id,
        )
        .scalar_subquery()
    )


def _adjustment_attachment(table: Table) -> ColumnElement[bool]:
    """A live attachment of a manual adjustment that needed one and has been submitted.

    "Needed" is what the product itself decided at the submission: from USD 10,000.00 —
    compared in USD at the spot rate of the effective date, whatever the entity's functional
    currency — the request is refused without an attachment and carries ``ABOVE_THRESHOLD``
    (PRD §2.5; ``journals.adjustments._routing_flags``; a deferral request carries the same
    routing flags). The adjustment's request (T-SL-05 ``approval_request_id``) is the record of
    it: ``amount_functional_abs`` alone is in the functional currency and says it for USD
    entities only."""
    adjustment, request = _table("manual_adjustment"), _table("approval_request")
    return and_(
        table.c.subject_type == ADJUSTMENT_SUBJECT,
        table.c.voided_at.is_(None),
        exists().where(
            adjustment.c.tenant_id == table.c.tenant_id,
            adjustment.c.id == table.c.subject_id,
            or_(
                adjustment.c.status.in_(ADJUSTMENT_SUBMITTED),
                and_(
                    adjustment.c.status == ADJUSTMENT_VOIDED,
                    adjustment.c.applied_event_id.is_not(None),
                ),
            ),
            exists().where(
                request.c.tenant_id == adjustment.c.tenant_id,
                request.c.id == adjustment.c.approval_request_id,
                request.c.flags.any(ABOVE_THRESHOLD),
            ),
        ),
    )


def _adjustment_column(name: str) -> Callable[[Table], ColumnElement[Any]]:
    def read(table: Table) -> ColumnElement[Any]:
        adjustment = _table("manual_adjustment")
        return (
            select(adjustment.c[name])
            .where(
                adjustment.c.tenant_id == table.c.tenant_id, adjustment.c.id == table.c.subject_id
            )
            .scalar_subquery()
        )

    return read


def _event_request_evidence(table: Table) -> ColumnElement[bool]:
    """A live attachment of an approval request whose subject is an event submission —
    ``MANUAL_EVENT``, ``ATTRIBUTE_CHANGE`` or ``STEP1_EVENT`` — that is submitted,
    approved or applied."""
    request, submission = _table("approval_request"), _table("event_submission")
    return and_(
        table.c.subject_type == REQUEST_SUBJECT,
        table.c.voided_at.is_(None),
        exists().where(
            request.c.tenant_id == table.c.tenant_id,
            request.c.id == table.c.subject_id,
            request.c.subject_type.in_(EVENT_SUBMISSION_SUBJECTS),
            exists().where(
                submission.c.tenant_id == request.c.tenant_id,
                submission.c.id == request.c.subject_id,
                submission.c.status.in_(SUBMISSION_STANDING),
            ),
        ),
    )


def _request_no(table: Table) -> ColumnElement[Any]:
    request = _table("approval_request")
    return (
        select(request.c.request_no)
        .where(request.c.tenant_id == table.c.tenant_id, request.c.id == table.c.subject_id)
        .scalar_subquery()
    )


def _event_request_entity(table: Table) -> ColumnElement[Any]:
    """The contracting entity of the contract the submission's events are recorded on."""
    request, submission = _table("approval_request"), _table("event_submission")
    return (
        select(submission.c.contracting_entity_id)
        .where(
            request.c.tenant_id == table.c.tenant_id,
            request.c.id == table.c.subject_id,
            submission.c.tenant_id == request.c.tenant_id,
            submission.c.id == request.c.subject_id,
        )
        .scalar_subquery()
    )


def _event_attachment(table: Table) -> ColumnElement[bool]:
    """A live attachment of a contract event."""
    return and_(table.c.subject_type == EVENT_SUBJECT, table.c.voided_at.is_(None))


def _event_contract(table: Table) -> ColumnElement[Any]:
    event, contract = _table("contract_event"), _table("contract")
    return (
        select(contract.c.external_id)
        .where(
            event.c.tenant_id == table.c.tenant_id,
            event.c.id == table.c.subject_id,
            contract.c.tenant_id == event.c.tenant_id,
            contract.c.id == event.c.contract_id,
        )
        .scalar_subquery()
    )


def _event_entity(table: Table) -> ColumnElement[Any]:
    event = _table("contract_event")
    return (
        select(event.c.contracting_entity_id)
        .where(event.c.tenant_id == table.c.tenant_id, event.c.id == table.c.subject_id)
        .scalar_subquery()
    )


def _own(name: str) -> Callable[[Table], ColumnElement[Any]]:
    def read(table: Table) -> ColumnElement[Any]:
        found: ColumnElement[Any] = table.c[name]
        return found

    return read


_PREVIEW: Final = "the impact preview of {what}"
_SIMULATION: Final = "the impact simulation of a configuration version"
EVIDENCE: Final[tuple[EvidenceReference, ...]] = (
    # --- period locks (04 T-CLS-04, T-CLS-05; REQ-CLS-010): for the life of the lock
    EvidenceReference("lock_snapshot", "file_id", "a frozen dataset of a period lock"),
    EvidenceReference(
        "period_lock", "diff_report_file_id", "the re-lock difference report of a period lock"
    ),
    # --- imports (04 T-IMP-02; REQ-DAT-001 "the original file and its SHA-256 are kept")
    EvidenceReference(
        "import_upload",
        "file_object_id",
        "the source of import {label}, which is submitted for approval or being committed",
        standing=_pending,
        label="import_no",
        advice=WITHDRAW_FIRST,
    ),
    EvidenceReference(
        "import_upload",
        "file_object_id",
        "the source of committed import {label}",
        standing=_committed,
        label="import_no",
        approval=True,
        entities=_own("named_entity_ids"),
    ),
    EvidenceReference(
        "import_upload", "diff_file_id", "the dry-run diff of import {label}", label="import_no"
    ),
    # --- journals (04 T-SL-07, T-SL-09; CTL-021)
    EvidenceReference("journal_batch", "export_file_id", "the export file of a journal batch"),
    EvidenceReference("journal_batch", "detail_file_id", "the detail file of a journal batch"),
    EvidenceReference(
        "posting_ack", "response_file_id", "the response to a general ledger posting"
    ),
    # --- reports and evidence (04 T-RPT-02, T-RPT-04; CTL-029, CTL-041): runs bound to a lock
    EvidenceReference(
        "report_run",
        "output_file_id",
        "the output of a report run as locked",
        standing=_as_locked,
    ),
    EvidenceReference(
        "report_run",
        "manifest_file_id",
        "the manifest of a report run as locked",
        standing=_as_locked,
    ),
    EvidenceReference("evidence_pack", "file_id", "a period evidence pack"),
    # --- approvals: what the approver reviewed (REQ-PLT-015; REQ-POL-006)
    EvidenceReference(
        "approval_request", "impact_preview_file_id", _PREVIEW.format(what="an approval request")
    ),
    EvidenceReference(
        "modification", "impact_preview_file_id", _PREVIEW.format(what="a contract modification")
    ),
    EvidenceReference(
        "manual_adjustment", "impact_preview_file_id", _PREVIEW.format(what="a manual adjustment")
    ),
    EvidenceReference("account_mapping_version", "impact_simulation_file_id", _SIMULATION),
    EvidenceReference("registry_version", "impact_simulation_file_id", _SIMULATION),
    EvidenceReference("rule_set_version", "impact_simulation_file_id", _SIMULATION),
    # --- audit and controls (04 T-PLT-28, T-PLT-39; CTL-039, CTL-042)
    EvidenceReference("audit_chain_verification", "digest_file_id", "an audit chain digest"),
    EvidenceReference(
        "control_execution", "exceptions_file_id", "the exceptions file of a control execution"
    ),
    EvidenceReference(
        "access_review_campaign", "snapshot_file_id", "the snapshot of an access review campaign"
    ),
    EvidenceReference(
        "ssp_calculator_run", "result_file_id", "the result of an SSP calculator run"
    ),
    # --- uploaded documents a record rests on (ruling R-86 (b), (c)): lifted by an approval
    EvidenceReference(
        "reconciliation",
        "source_file_id",
        "the source file of reconciliation {label}, which has been signed",
        standing=_signed,
        label="reconciliation_no",
        approval=True,
        entities=_own("entity_id"),
    ),
    EvidenceReference(
        "migration_batch",
        "source_file_id",
        "the legacy database of migration {label}, whose capture is relied on",
        standing=_captured,
        label="migration_no",
        approval=True,
    ),
    EvidenceReference(
        "file_attachment",
        "file_object_id",
        "the SSP study of SSP book {label}, which has been submitted",
        standing=_ssp_study,
        label_of=_ssp_version_label,
        approval=True,
        entities=_ssp_book_entity,
    ),
    EvidenceReference(
        "file_attachment",
        "file_object_id",
        "the supporting attachment of manual adjustment {label}, which has been submitted",
        standing=_adjustment_attachment,
        label_of=_adjustment_column("adjustment_no"),
        approval=True,
        entities=_adjustment_column("entity_id"),
    ),
    # --- the evidence of recorded events (item EVT-EVIDENCE-1; 04 rev 1.268): lifted by an approval
    EvidenceReference(
        "file_attachment",
        "file_object_id",
        "the evidence of approval request {label}, whose events wait for approval or are recorded",
        standing=_event_request_evidence,
        label_of=_request_no,
        approval=True,
        entities=_event_request_entity,
    ),
    EvidenceReference(
        "file_attachment",
        "file_object_id",
        "the evidence of an event recorded on contract {label}",
        standing=_event_attachment,
        label_of=_event_contract,
        approval=True,
        entities=_event_entity,
    ),
)

# The foreign keys to ``file_object`` that are NOT evidence, each with its reason.
NOT_EVIDENCE: Final[Mapping[tuple[str, str], str]] = MappingProxyType(
    {
        ("file_upload", "file_object_id"): (
            "the record that a principal uploaded the file's bytes (T-PLT-49): it names the file "
            "and holds nothing against a shred; the row and the SHA-256 remain"
        ),
        ("tenant_snapshot", "manifest_file_id"): (
            "the manifest of a sandbox copy or stored backup: a copy, not a record of the books, "
            "kept under the snapshot retention families (04 T-PLT-34; ruling R-86 (c))"
        ),
    }
)


@dataclass(frozen=True, slots=True)
class Hold:
    """The standing record that holds a file."""

    reference: EvidenceReference
    label: str | None
    row_id: UUID | None = None  # the row that references the file
    # the record's legal entities; None = every entity (a record without an entity, a tenant-level
    # import, or an import whose entities are not resolved)
    entity_ids: frozenset[UUID] | None = None

    @property
    def record(self) -> str:
        return self.reference.record.format(label=self.label or "")

    @property
    def held_by(self) -> str:
        return f"{self.reference.table}.{self.reference.column}"


def held_rule(hold: Hold) -> str:
    """The 04 table 15.4-B rule id of the refusal: the approved path for a hold an approval lifts
    (R-49 (a), R-86), no override for every other evidence file."""
    return RULE_APPROVAL_REQUIRED if hold.reference.approval else RULE_EVIDENCE_HELD


def held_message(hold: Hold) -> str:
    """The copy of the refusal (PRD §5.5): the record by name, and what lifts the hold."""
    if hold.reference.approval:
        return APPROVAL_MESSAGE.format(record=hold.record)
    message = HELD_MESSAGE.format(record=hold.record)
    advice = hold.reference.advice
    return message if advice is None else f"{message} {advice}"


def _entity_ids(value: Any) -> frozenset[UUID] | None:
    """The entities of a record from its column value: a uuid, a uuid[] (an empty array is a
    tenant-level import) or NULL — None when the approval has to cover every entity."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        found = frozenset(UUID(str(item)) for item in value)
        return found or None
    return frozenset({UUID(str(value))})


def holds_in(session: Session, file_id: UUID) -> tuple[Hold, ...]:
    """Every standing record of ``EVIDENCE`` that references ``file_id`` among the rows
    ``session`` reads, in registry order."""
    found: list[Hold] = []
    for reference in EVIDENCE:
        table = _table(reference.table)
        label: ColumnElement[Any] | None = (
            table.c[reference.label]
            if reference.label is not None
            else (None if reference.label_of is None else reference.label_of(table))
        )
        entities = None if reference.entities is None else reference.entities(table)
        columns: list[Any] = [table.c.id]
        if label is not None:
            columns.append(label.label("hold_label"))
        if entities is not None:
            columns.append(entities.label("hold_entities"))
        statement = (
            select(*columns).where(table.c[reference.column] == file_id).order_by(table.c.id)
        )
        if reference.standing is not None:
            statement = statement.where(reference.standing(table))
        for row in session.execute(statement).mappings():
            named = row.get("hold_label")
            found.append(
                Hold(
                    reference,
                    None if named is None else str(named).strip(),
                    UUID(str(row["id"])),
                    _entity_ids(row.get("hold_entities")),
                )
            )
    return tuple(found)


def first_refusing(found: Sequence[Hold]) -> Hold | None:
    """The hold a refusal names: a record that holds the file without override before one whose
    hold an approval lifts (the first answers "cannot be shredded", whatever else holds it)."""
    for hold in found:
        if not hold.reference.approval:
            return hold
    return found[0] if found else None


def holding_in(session: Session, file_id: UUID) -> Hold | None:
    """The standing record a refusal of ``file.shred`` names among the rows ``session`` reads;
    None when none holds the file."""
    return first_refusing(holds_in(session, file_id))


def holds(tenant_id: UUID, file_id: UUID) -> tuple[Hold, ...]:
    """``holds_in`` over every entity of the tenant: a read-only session of its own with entity
    scope ``*``, so that a record of an entity outside the caller's scope holds its file too."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return holds_in(session, file_id)


def holding(tenant_id: UUID, file_id: UUID) -> Hold | None:
    """The standing record a refusal names, read over every entity of the tenant."""
    return first_refusing(holds(tenant_id, file_id))


def pending_on(tenant_id: UUID, found: Sequence[Hold]) -> list[dict[str, str]]:
    """The approval requests that are ``PENDING`` on the records that hold a file — for an
    attachment, on its subject — each by its number, its subject type and the record as the
    refusal names it (ruling R-120 (g); 04 T-PLT-29 "A document a rule asks for"). The decision
    of each is refused once the file is shredded — a manual adjustment's as stale, an SSP
    version's by the study rule — so the request to shred names them: its approver sees what the
    shred stops. Read over every entity of the tenant, as the holds are; a request to shred
    evidence is none of them. Where the attachment's subject is itself an approval request — the
    evidence of an event submission (rev 1.268) — that request is the one named, by its own id."""
    attachment, request = _table("file_attachment"), _table("approval_request")
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        attached = [
            hold.row_id
            for hold in found
            if hold.reference.table == attachment.name and hold.row_id is not None
        ]
        subject_of: dict[UUID, UUID] = {}
        if attached:
            subject_of = {
                UUID(str(attachment_id)): UUID(str(subject_id))
                for attachment_id, subject_id in session.execute(
                    select(attachment.c.id, attachment.c.subject_id).where(
                        attachment.c.id.in_(attached)
                    )
                )
            }
        record_of: dict[UUID, str] = {}
        for hold in found:
            if hold.row_id is not None:
                record_of.setdefault(subject_of.get(hold.row_id, hold.row_id), hold.record)
        if not record_of:
            return []
        holders = sorted(record_of, key=str)
        rows = session.execute(
            select(request.c.request_no, request.c.subject_type, request.c.subject_id, request.c.id)
            .where(
                request.c.status == ApprovalRequestStatus.PENDING.value,
                or_(request.c.subject_id.in_(holders), request.c.id.in_(holders)),
                request.c.subject_type != ApprovalSubjectType.EVIDENCE_SHRED.value,
            )
            .order_by(request.c.request_no)
        ).all()
    return [
        {
            "request_no": str(request_no),
            "subject_type": str(getattr(subject_type, "value", subject_type)),
            "record": record_of.get(UUID(str(subject_id))) or record_of[UUID(str(request_id))],
        }
        for request_no, subject_type, subject_id, request_id in rows
    ]
