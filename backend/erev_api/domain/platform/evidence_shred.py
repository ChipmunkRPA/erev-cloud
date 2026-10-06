"""The approved shred of an evidence file (supervisor rulings R-49 (a) and R-86 (b), (c); security
finding SC-6; 05 rev 1.81 PRV-07 b; 04 rev 1.142 E-08 ``EVIDENCE_SHRED``, §16.10, API-R-12, table
15.4-B ``FILE_SHRED_APPROVAL_REQUIRED``, T-PLT-29 evidence references; runbook RB-14 step 4; PRD
§2.5 rev 1.71, IMP-129; 03 REQ-DAT-001, REQ-PLT-011).

Some uploaded documents are both a record the books rest on and the only place personal data
lives in clear: the source of a committed import, the source file of a signed reconciliation, the
legacy database of a migration whose capture is relied on, the SSP study of a submitted version,
the attachment a manual adjustment at or above its threshold needed. The documents require both
that such a file is kept (REQ-DAT-001) and that it can be erased (05 PRV-06; runbook RB-14), so
the erasure takes a second person:

1. ``request_shred`` — the privacy-side administrator (``settings.manage``, a TOTP step-up at most
   five minutes old, a reason that names the data-subject request) asks for the file to be
   shredded. Nothing about the file changes while the request is pending.
2. The request is an ``EVIDENCE_SHRED`` approval whose subject is the ``file_object`` row and
   whose hashed content is the proposal — the file, its SHA-256, the records that hold it, their
   legal entities, the approval requests pending on those records (the decision of each is
   refused once the file is gone; ruling R-120 (g)) and the reason — with the state of the
   file. The request is bound to those
   entities, or to every entity when one of the records has none (R-25, R-41 (4): the proposal
   states them, ``SubjectSpec.proposal_entities``), and its one step is ``config.approve`` with
   the Controller role (R-49 (a); ``SubjectSpec.step_role``). The approvals kernel holds everyone
   to that set (04 §16.10 "Entity scope of a request"): the requester's own scope covers it, the
   request is listed and read only inside it, and the decider holds the permission and the role
   for every entity of it. The requester never decides it (REQ-PLT-011) and it is never
   auto-approved (R-26).
3. On approval the SYSTEM principal decides the shred on behalf of the requester, in the
   decision's transaction — the row is marked and the ``file_object.shred`` audit event names the
   approval request — and the file's key is destroyed after that transaction commits, by the
   same principal (``privacy.continuation``; 05 PRV-07 b rev 1.171: nothing of the store is
   touched before the decision is durable, so an approval that fails destroys nothing). The
   approval lifts the holds its proposal names and no other: when the records that hold the file,
   or their legal entities, are no longer exactly those, the decision is refused by name and
   nothing is shredded.

A file that a record holds without override (``file_evidence``: lock datasets, journal batch
files, the source of an import before its commit, …) takes no request; neither does a file
nothing holds, which ``file.shred`` erases directly.

A sandbox destroys nothing it shares (05 SBX-08 rev 1.164; item FILE-SHRED-SCOPE-1): a sandbox
copy shares its stored files with its source, so in a sandbox the request for such a file is
refused once the file's row is read, and the approval of such a request — one copied while it
was pending included — is refused before anything is destroyed, each 403 ``sandbox-restricted``
with its ``DENIED`` event (``privacy.refuse_shared_in_sandbox``). Such a request stays PENDING
in the sandbox; rejecting or withdrawing it changes no file. A file the sandbox stored itself
is its own: both ends run for it as in production.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.approvals import engine as approvals
from erev_api.approvals import preview, subjects
from erev_api.auth import mfa
from erev_api.auth.principal import system_principal
from erev_api.db.tables import approval_request, file_object
from erev_api.domain.platform import file_evidence, privacy, users
from erev_api.enums import ApprovalSubjectType
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

__all__ = [
    "HOLDS_CHANGED",
    "NOT_HELD",
    "REQUEST_ACTION",
    "SUBJECT",
    "ShredRequested",
    "request_shred",
]

SUBJECT: Final = ApprovalSubjectType.EVIDENCE_SHRED
REQUEST_ACTION: Final = "file_object.request_shred"
SUMMARY: Final = "Shred a file that is {record}"
SUMMARY_MORE: Final = "Shred a file that is {record} and held by {more} more"
RULE_PROCEDURE: Final = privacy.RULE_ERASURE  # PRV-07, the erasure procedure
NOT_HELD: Final = (
    "No record holds this file as its evidence, so shredding it needs no approval. Shred it "
    "directly."
)
HOLDS_CHANGED: Final = (
    "The records that hold this file are no longer the ones this request names. Reject the "
    "request, or have it withdrawn, and request the shredding again."
)


@dataclass(frozen=True, slots=True)
class ShredRequested:
    """The pending request and the file, which is unchanged until the decision."""

    approval_request_id: UUID
    file: Mapping[str, Any]


def _locked_file(session: Session, file_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(select(file_object).where(file_object.c.id == file_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _invalid(rule_id: str, message: str) -> Problem:
    error = ProblemError(field="status", rule_id=rule_id, message=message)
    return Problem("invalid-transition", errors=[error])


def _refuse_own_state(uow: UnitOfWork, row: Mapping[str, Any]) -> None:
    """The file's own refusals — already shredded, a legal hold or retention. They name no
    record."""
    today = uow.now.date()
    if row["shredded_at"] is not None or privacy.retention_active(row, today):
        refusal = privacy.shred_refusal(row, today)
        assert refusal is not None  # exactly the two states the condition names
        raise refusal


def _standing(uow: UnitOfWork, row: Mapping[str, Any]) -> tuple[file_evidence.Hold, ...]:
    """The records that hold the file now, for the REQUEST: read over every entity of the tenant
    — after the file's own refusals — and refused by name when one of them holds it without
    override. The requester's scope covers every record that references the file
    (``privacy.refuse_beyond_scope`` before this), so the name is the requester's to read."""
    _refuse_own_state(uow, row)
    found = file_evidence.holds(uow.principal.tenant_id, UUID(str(row["id"])))
    blocking = next((hold for hold in found if not hold.reference.approval), None)
    if blocking is not None:
        refusal = privacy.shred_refusal(row, uow.now.date(), held=blocking)
        assert refusal is not None
        raise refusal
    return found


def _described(found: Sequence[file_evidence.Hold]) -> list[dict[str, Any]]:
    """The holds as the proposal names them (``subjects.evidence_shred_proposal``)."""
    return [
        {
            "table": hold.reference.table,
            "column": hold.reference.column,
            "record_id": str(hold.row_id),
            "record": hold.record,
        }
        for hold in found
    ]


def _keys(described: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    return sorted(
        (str(item["table"]), str(item["column"]), str(item["record_id"])) for item in described
    )


def _entities(found: Sequence[file_evidence.Hold]) -> frozenset[UUID] | None:
    """The legal entities of the records in ``found`` (R-25, R-41 (5)) — for an import its
    ``named_entity_ids`` — or None, every entity, when one of them has none: a migration batch,
    a book without an entity, a tenant-level or unresolved import."""
    union: set[UUID] = set()
    for hold in found:
        if hold.entity_ids is None:
            return None
        union |= hold.entity_ids
    return frozenset(union) or None


def _bound(found: Sequence[file_evidence.Hold]) -> subjects.SubjectEntities:
    """The entity set a request that lifts ``found`` is bound to, as the kernel compares it."""
    named = _entities(found)
    return subjects.ALL_ENTITIES if named is None else subjects.SubjectEntities(named)


def _still_named(
    session: Session, found: Sequence[file_evidence.Hold], proposal: Mapping[str, Any]
) -> bool:
    """Whether ``found`` — the records that hold the file now — are exactly the ones the request
    names, bound to the entities it froze. The approval lifts those holds and no other, and the
    approver was checked against that set (``engine.decide``): the same records under other
    entities are not the request's either."""
    same_records = _keys(_described(found)) == _keys(proposal.get("holds") or ())
    return same_records and _bound(found) == subjects.evidence_shred_entities(session, proposal)


def request_shred(uow: UnitOfWork, file_id: UUID, *, reason: str) -> ShredRequested:
    """``POST /files/{id}/request-shred``: open the ``EVIDENCE_SHRED`` approval for a file that a
    record holds as its evidence and an approval may release.

    403 ``mfa-step-up-required`` without a TOTP verification at most five minutes old (so only a
    person asks); 404 for an unknown file; 422 for a reason under ten characters; 409
    ``invalid-transition`` by rule when the file is already shredded, under legal hold or
    retention, held by a record without override (``FILE_EVIDENCE_HELD``), stored in plaintext
    (``PRV-06``) or held by no record (``PRV-07``: shred it directly), and when a request for the
    file is pending; 403 ``forbidden`` when the requester's own entity scope does not cover every
    legal entity of the records that reference the file — those that hold it among them (the
    kernel's rule for a preparer, R-64 (6), asked here before any refusal names a record).
    The step is the kernel's: the published routing raised to the subject's own step with its
    role, and no auto-approval rule is read. Nothing about the file changes here. In a sandbox
    a file it shares with its source is refused once its row is read, 403 ``sandbox-restricted``
    (module docstring)."""
    principal = uow.principal
    if not mfa.step_up_fresh_at(principal.mfa_verified_at, uow.now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
    session = uow.session
    row = _locked_file(session, file_id)
    privacy.refuse_shared_in_sandbox(
        uow, row, action=REQUEST_ACTION, detail={"reason": reason.strip()}
    )
    # Before any refusal that names a record (item FILE-SHRED-SCOPE-1, B5): the requester's scope
    # covers every entity of the records that reference the file, which include the ones that
    # hold it. The answer is the kernel's for a preparer outside the scope of what it submits.
    privacy.refuse_beyond_scope(
        uow,
        row,
        action=REQUEST_ACTION,
        reason=reason,
        refusal=Problem("forbidden", approvals.OUTSIDE_SCOPE_DETAIL),
    )
    comment = users.require_reason(reason)
    found = _standing(uow, row)
    refusal = privacy.shred_refusal(row, uow.now.date())
    if refusal is not None:  # a plaintext purpose: no approval makes it shreddable in 1.0
        raise refusal
    if not found:
        raise _invalid(RULE_PROCEDURE, NOT_HELD)
    proposal = subjects.evidence_shred_proposal(
        row,
        _described(found),
        reason=comment,
        entity_ids=_entities(found),
        pending_requests=file_evidence.pending_on(principal.tenant_id, found),
    )
    summary = (
        SUMMARY.format(record=found[0].record)
        if len(found) == 1
        else SUMMARY_MORE.format(record=found[0].record, more=len(found) - 1)
    )
    request = approvals.submit(
        uow,
        subject_type=SUBJECT,
        subject_id=file_id,
        summary=summary,
        impact_preview=approvals.ImpactPreview(
            before={"file_id": str(file_id), "shredded_at": None}, after=proposal
        ),
        comment=comment,
        auto_approval=False,
    )
    request_id = UUID(str(request["id"]))
    uow.audit(
        action=REQUEST_ACTION,
        object_type=privacy.FILE_OBJECT,
        object_id=file_id,
        after={
            "approval_request_id": str(request_id),
            "sha256": str(row["sha256"]),
            "holds": proposal["holds"],
        },
        comment=comment,
        approval_request_id=request_id,
    )
    return ShredRequested(approval_request_id=request_id, file=row)


# --- the decision ---------------------------------------------------------------------------------


def _approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """The approval decides the shred: SYSTEM on behalf of the requester, in the decision's
    transaction, the audit event naming the approval request; the key is destroyed once that
    transaction has committed (``privacy.continuation``, registered here on the unit of work
    that commits). Who may decide is the kernel's check before this
    hook runs — the step's permission and the Controller role for every entity the request
    froze. Everything is read again under the file's lock — a legal hold or a retention set
    since the request, a record that has come to hold the file or ceased to, records whose legal
    entities are no longer the frozen ones — and each refuses the decision by rule; a record
    that has come to hold the file is not named, with or without override. In a sandbox
    the approval destroys nothing the sandbox shares: for such a file it is refused first, 403
    ``sandbox-restricted``, and the decision rolls back with it (module docstring)."""
    session = uow.session
    row = _locked_file(session, subject_id)
    privacy.refuse_shared_in_sandbox(
        uow,
        row,
        action=privacy.SHRED_ACTION,
        detail={"approval_request_id": str(approval_request_id)},
    )
    _refuse_own_state(uow, row)
    # The decider's scope covers the entities the request froze — not those of a record that has
    # come to hold the file since, which may be another entity's. No such record is named here
    # (item FILE-SHRED-SCOPE-1, finding B5): it is not one of the request's, so the decision is
    # refused because the holds changed, and the next request names it to a requester whose
    # scope covers it. A hold without override is never lifted, whatever the proposal says.
    found = file_evidence.holds(uow.principal.tenant_id, subject_id)
    proposal = preview.request_proposal(uow, approval_request_id)
    if not found:
        raise _invalid(RULE_PROCEDURE, NOT_HELD)
    lifted_by_approval = all(hold.reference.approval for hold in found)
    if not lifted_by_approval or not _still_named(session, found, proposal):
        raise _invalid(RULE_PROCEDURE, HOLDS_CHANGED)
    request = (
        session.execute(
            select(approval_request.c.preparer_id, approval_request.c.comment).where(
                approval_request.c.id == approval_request_id
            )
        )
        .mappings()
        .one()
    )
    unit = UnitOfWork(
        ctx=dataclasses.replace(
            uow.ctx,
            principal=system_principal(
                uow.principal.tenant_id, on_behalf_of_id=request["preparer_id"]
            ),
        ),
        session=session,
        clock=uow.clock,
        keyring=uow.keyring,
        files=uow.files,
    )
    unit.now = uow.now
    privacy.shred_approved(
        unit,
        row,
        reason=str(request["comment"] or ""),
        approval_request_id=approval_request_id,
        lifted=found,
    )
    for event in unit.drain_audit_events():
        uow.buffer_audit_event(event)
    # ``unit`` shares this transaction and is never committed: the completion is the hook of the
    # unit of work that commits the decision, and it writes its event as the principal that
    # decided — SYSTEM on behalf of the requester.
    uow.after_commit(
        privacy.continuation(
            unit.ctx, subject_id, clock=uow.clock, keyring=uow.keyring, files=uow.files
        )
    )


def _closed(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """A rejected or withdrawn request leaves the file as it is; the decision is the record."""
    del uow, subject_id, approval_request_id


subjects.register_lifecycle(
    SUBJECT,
    subjects.SubjectLifecycle(on_approved=_approved, on_rejected=_closed, on_voided=_closed),
)
