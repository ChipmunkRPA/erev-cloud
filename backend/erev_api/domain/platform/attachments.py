"""Files and attachments: commands and queries (04 T-PLT-29, T-PLT-30, API-R-12, DB-11; 05 UPL-10;
03 REQ-PLT-012, REQ-PLT-015, REQ-PLT-035, REQ-SEC-012; BUILD_SPEC PLF-8).

API-R-12 authorises "per subject", which one route permission cannot express, so the handlers
authorise (SPEC-Q-157):

- an upload needs a permission of its purpose: ``import.upload``, ``migration.run``,
  ``ssp.create``, or for ``ATTACHMENT`` any permission that may attach to some subject;
- attaching needs a write permission of the subject type held for the subject's legal entity, and
  a file the caller may read; voiding needs the write permission and is the uploader's own action
  (REQ-PLT-035);
- reading attachments needs a read permission of the subject type held for the subject's entity;
- a file is read through a record that owns it, by that record's read permission for its entity,
  or by its uploader — never by ``audit.read`` as such (``file_access``, the file-read registry).

A denial writes one ``DENIED`` audit event and returns 403, with the ``mfa-required`` variant when
every held code of the set needs MFA and the session is not verified (DG-KRN-AUTH-05). A subject
the caller does not see — an unknown id, or one outside the entity scope of the permission —
answers 404 on attach and an empty list on read, the two alike (REQ-PLT-012).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, BinaryIO, Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.auth import mfa
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import spec
from erev_api.auth.principal import RequestContext
from erev_api.db import new_id, transitions
from erev_api.db.errors import erev_code
from erev_api.db.session import tenant_session
from erev_api.db.tables import approval_request, file_attachment, file_object
from erev_api.domain.platform import file_access
from erev_api.domain.platform.file_access import (
    ATTACH_PERMISSIONS,
    ATTACHMENT_SUBJECTS,
    UPLOAD_ACTION,
)
from erev_api.enums import ApprovalRequestStatus, FilePurpose
from erev_api.files import policy
from erev_api.files.store import FileStore, lock_readable, open_file, put_file
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

ATTACH_ACTION: Final = "file_attachment.create"
VOID_ACTION: Final = "file_attachment.void"
# 04 T-PLT-29 "Content reads are audited" (rev 1.189): the event of GET /files/{id}/content.
DOWNLOAD_ACTION: Final = "file.download"
NOT_READABLE: Final = "not-readable"
# PRD ERR-05.
FIELD_DETAIL: Final = "1 field needs attention."
PURPOSE_MESSAGE: Final = "Choose IMPORT_SOURCE, ATTACHMENT, SSP_STUDY or LEGACY_DATABASE."
FILE_MESSAGE: Final = "Choose a file to upload."
MISSING_FILE_MESSAGE: Final = "Upload the file first. No file with this id exists."
NOT_ATTACHABLE_MESSAGE: Final = "Only attachments and SSP studies can be attached to a record."
APPROVED_SUBJECT_MESSAGE: Final = (
    "An approved request relies on this record, so its attachment cannot be voided."
)
# REQ-PLT-015: the approver sees what is approved.
PREVIEW_RULE: Final = "REQ-PLT-015"
PREVIEW_UNREADABLE: Final = (
    "The impact preview of this request cannot be read, so the request cannot be approved."
)
ATTACHABLE_PURPOSES: Final = frozenset({FilePurpose.ATTACHMENT, FilePurpose.SSP_STUDY})
UPLOAD_PERMISSIONS: Final[Mapping[FilePurpose, frozenset[str]]] = MappingProxyType(
    {
        FilePurpose.IMPORT_SOURCE: frozenset({"import.upload"}),
        FilePurpose.LEGACY_DATABASE: frozenset({"migration.run"}),
        FilePurpose.SSP_STUDY: frozenset({"ssp.create"}),
        FilePurpose.ATTACHMENT: ATTACH_PERMISSIONS,
    }
)


ANY_UPLOAD_PERMISSION: Final = frozenset().union(*UPLOAD_PERMISSIONS.values())


@dataclass(frozen=True, slots=True)
class UploadCeiling:
    """The largest upload a caller could store: the T-PLT-29 limit of ``purpose``."""

    purpose: FilePurpose
    limit: int


def upload_ceiling(ctx: RequestContext) -> UploadCeiling | None:
    """The largest T-PLT-29 limit among the purposes the caller may upload, with its purpose;
    None when the caller may upload for none (04 API-C-17 rev 1.189; ruling R-111 (8)).

    ``POST /files`` asks before it reads the body, so that a caller sends no more than it could
    store. A purpose counts when the caller holds one of its ``UPLOAD_PERMISSIONS``; an
    attachment counts as well for the requester of a pending approval request, who uploads the
    evidence of that request (T-PLT-30 Subjects; ruling R-100 (b)). The handler still authorises
    the purpose the form names."""
    principal = ctx.principal
    purposes = {
        purpose for purpose, codes in UPLOAD_PERMISSIONS.items() if codes & principal.permissions
    }
    if not purposes:
        with tenant_session(principal.db_context, read_only=True) as session:
            if file_access.has_pending_request(session, principal):
                purposes.add(FilePurpose.ATTACHMENT)
    if not purposes:
        return None
    largest = max(purposes, key=lambda purpose: (policy.UPLOAD_LIMITS[purpose], purpose.value))
    return UploadCeiling(purpose=largest, limit=policy.UPLOAD_LIMITS[largest])


def refuse_upload(ctx: RequestContext, *, keyring: KeyRing) -> Problem:
    """The 403 of a caller who may upload for no purpose, its ``DENIED`` event written: the body
    is not read, so the event names every upload permission and not that of one purpose."""
    codes = sorted(ANY_UPLOAD_PERMISSION)
    audit_writer.record_denied(
        ctx,
        action=UPLOAD_ACTION,
        object_type=file_access.FILE_OBJECT,
        object_id=None,
        permission="|".join(codes),
        detail={"permissions": codes},
        keyring=keyring,
    )
    return Problem("forbidden")


def _field_problem(field: str, message: str) -> Problem:
    return Problem(
        "validation-failed", FIELD_DETAIL, errors=[ProblemError(field=field, message=message)]
    )


def authorize(
    ctx: RequestContext,
    codes: frozenset[str],
    *,
    keyring: KeyRing,
    action: str,
    object_type: str,
    object_id: UUID | None,
) -> None:
    """Pass when the principal holds one of ``codes``; otherwise audit the denial and raise 403."""
    principal = ctx.principal
    held = codes & principal.permissions

    def deny(**detail: str) -> None:
        audit_writer.record_denied(
            ctx,
            action=action,
            object_type=object_type,
            object_id=object_id,
            permission="|".join(sorted(codes)),
            detail={"permissions": sorted(codes), **detail},
            keyring=keyring,
        )

    if not held:
        deny()
        raise Problem("forbidden")
    if principal.mfa_verified_at is None and all(spec(code).requires_mfa for code in held):
        enrolled = principal.id is not None and mfa.has_confirmed_factor(
            principal.id, request_id=ctx.request_id
        )
        deny(reason="mfa-required")
        raise Problem(
            "mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED
        )


def parse_upload_purpose(value: str | None) -> FilePurpose:
    """One of the four uploadable purposes, else 422 ``validation-failed`` on ``purpose``."""
    for purpose in policy.UPLOADABLE_PURPOSES:
        if purpose.value == value:
            return purpose
    raise _field_problem("purpose", PURPOSE_MESSAGE)


def upload_file(
    uow: UnitOfWork,
    *,
    purpose: str | None,
    stream: BinaryIO | None,
    original_filename: str | None,
    media_type: str,
) -> Mapping[str, Any]:
    """``POST /files``: store an upload; identical content of the same purpose returns its row.

    Each principal's first upload of the bytes writes its row of T-PLT-49 ``file_upload`` —
    which is what makes it an uploader of the stored row (``file_access.uploaded_by``), so it can
    attach and read what it uploaded — and is audited once. The answer carries the stored id and
    content facts with the CALLER's own file name, time and identity, never the first
    uploader's (04 T-PLT-29 "Uploads of the same bytes"; ruling R-111 (5))."""
    parsed = parse_upload_purpose(purpose)
    if stream is None:
        raise _field_problem("file", FILE_MESSAGE)
    # The requester of a pending approval request uploads the evidence it attaches to it,
    # whatever permission it holds (04 T-PLT-30 Subjects rev 1.151; ruling R-100 (b)).
    if not (
        parsed is FilePurpose.ATTACHMENT
        and file_access.has_pending_request(uow.session, uow.principal)
    ):
        authorize(
            uow.ctx,
            UPLOAD_PERMISSIONS[parsed],
            keyring=uow.keyring,
            action=UPLOAD_ACTION,
            object_type="file_object",
            object_id=None,
        )
    stored = put_file(
        uow,
        purpose=parsed,
        stream=stream,
        original_filename=original_filename,
        media_type=media_type,
    )
    first = file_access.record_upload(
        uow.session, uow.principal, stored.row, original_filename=original_filename, at=uow.now
    )
    if first:
        audit_writer.record_facts(
            uow,
            action=UPLOAD_ACTION,
            object_type=file_access.FILE_OBJECT,
            ids=[UUID(str(stored.row["id"]))],
            detail={"purpose": parsed.value}
            if stored.created
            else {"purpose": parsed.value, "deduplicated": True},
        )
    return file_access.uploader_view(uow.session, uow.principal, stored.row)


def _attachment_row(session: Session, attachment_id: UUID, *, lock: bool = False) -> Any:
    statement = (
        select(
            file_attachment,
            file_object.c.original_filename,
            file_object.c.media_type,
            file_object.c.size_bytes,
            file_object.c.sha256,
        )
        .join(
            file_object,
            sa.and_(
                file_object.c.tenant_id == file_attachment.c.tenant_id,
                file_object.c.id == file_attachment.c.file_object_id,
            ),
        )
        .where(file_attachment.c.id == attachment_id)
    )
    if lock:
        statement = statement.with_for_update(of=file_attachment)
    return session.execute(statement).mappings().one_or_none()


def attach(
    uow: UnitOfWork,
    *,
    file_object_id: UUID,
    subject_type: str,
    subject_id: UUID,
    description: str | None,
) -> Mapping[str, Any]:
    """``POST /attachments``: link a stored attachment or SSP study to a subject record.

    The caller holds a write permission of the subject type (403 with its ``DENIED`` event
    otherwise), may read the file — its own upload, or one a record it reads already owns; a file
    it may not read is answered like a missing one — and holds the write permission for the
    subject's legal entity; a subject it does not see is 404, unknown and out of scope alike
    (REQ-PLT-012). The requester of an approval request attaches to it while it is pending,
    whatever it holds (``file_access.own_pending_request``; ruling R-100 (b))."""
    subject = ATTACHMENT_SUBJECTS[subject_type]
    own = subject.own is not None and subject.own(uow.session, uow.principal, subject_id)
    if not own:
        authorize(
            uow.ctx,
            subject.write,
            keyring=uow.keyring,
            action=ATTACH_ACTION,
            object_type=subject_type,
            object_id=subject_id,
        )
    stored = file_access.bound(uow.session, uow.ctx, file_object_id)
    # The shred state is read under the file row's lock, held to the commit: an attachment can
    # make its record hold the file, so this command and a shred of the file see each other (04
    # T-PLT-29 "A document a rule asks for").
    if stored is None or not lock_readable(uow.session, [file_object_id]):
        raise _field_problem("file_object_id", MISSING_FILE_MESSAGE)
    if FilePurpose(stored["purpose"]) not in ATTACHABLE_PURPOSES:
        raise _field_problem("file_object_id", NOT_ATTACHABLE_MESSAGE)
    if not (own or subject.writable(uow.session, uow.ctx, subject_id)):
        raise Problem("not-found")
    principal = uow.principal
    attachment_id = new_id()
    values = {
        "file_object_id": file_object_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "description": description,
    }
    uow.session.execute(
        insert(file_attachment).values(
            tenant_id=principal.tenant_id,
            id=attachment_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **values,
        )
    )
    uow.audit(
        action=ATTACH_ACTION,
        object_type="file_attachment",
        object_id=attachment_id,
        after={**values, "file_object_id": str(file_object_id), "subject_id": str(subject_id)},
    )
    return MappingProxyType(dict(_attachment_row(uow.session, attachment_id)))


def readable_evidence(
    session: Session, subject_type: str, subject_id: UUID
) -> tuple[tuple[UUID, ...], bool]:
    """The files of the subject's live attachments that can still be read, each once and in the
    order they were attached, and whether EVERY live attachment's file can (04 T-PLT-29 "A
    document a rule asks for", rev 1.268). The files' rows are locked to the end of the caller's
    transaction (``files.store.lock_readable``), so the command that counts them and a shred of
    one see each other. An attachment row outlives the shred of its file and is the evidence of
    nothing then: the caller decides what a shredded file means for its record."""
    file_ids = [
        UUID(str(value))
        for value in session.scalars(
            select(file_attachment.c.file_object_id)
            .where(
                file_attachment.c.subject_type == subject_type,
                file_attachment.c.subject_id == subject_id,
                file_attachment.c.voided_at.is_(None),
            )
            .order_by(file_attachment.c.created_at, file_attachment.c.id)
        )
    ]
    readable = lock_readable(session, file_ids)
    unique = tuple(dict.fromkeys(file_ids))
    return tuple(value for value in unique if value in readable), all(
        value in readable for value in unique
    )


def attach_evidence(
    uow: UnitOfWork,
    *,
    file_object_id: UUID,
    subject_type: str,
    subject_ids: Sequence[UUID],
    contract_id: UUID | None = None,
    approval_request_id: UUID | None = None,
) -> list[UUID]:
    """Attach one stored file to each of ``subject_ids`` as their evidence, for a command that has
    authorised its caller for the subjects and for the file already (04 T-PLT-30 Subjects rev
    1.268; item EVT-EVIDENCE-1). Two commands do: the events route, which attaches the files a
    caller sent with a record to the events it appends — the caller holds ``event.record`` for the
    contract's entity and may read each file — and the approval of an event submission, which
    attaches the evidence of the request to the events it appends as the SYSTEM principal acting
    for the preparer. That write lies below the permission check of ``POST /attachments``: the
    approver need not hold ``event.record``, and an attachment the SYSTEM principal wrote is
    voided by no person (the void is its uploader's own act).

    The file must be an attachment or an SSP study whose content can still be read, under its
    row's lock (``lock_readable``): 422 on ``file_object_id`` otherwise, as ``attach`` answers.
    One AUD-FACT event names the attachments written, the file and, when given, the request
    whose approval wrote them; it carries the principal the unit of work acts for. Returns the
    attachment ids, in the order of ``subject_ids``."""
    session = uow.session
    purpose = session.execute(
        select(file_object.c.purpose).where(file_object.c.id == file_object_id)
    ).scalar_one_or_none()
    if purpose is None or not lock_readable(session, [file_object_id]):
        raise _field_problem("file_object_id", MISSING_FILE_MESSAGE)
    if FilePurpose(str(getattr(purpose, "value", purpose))) not in ATTACHABLE_PURPOSES:
        raise _field_problem("file_object_id", NOT_ATTACHABLE_MESSAGE)
    if not subject_ids:
        return []
    principal = uow.principal
    ids = [new_id() for _ in subject_ids]
    session.execute(
        insert(file_attachment),
        [
            {
                "tenant_id": principal.tenant_id,
                "id": attachment_id,
                "file_object_id": file_object_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "description": None,
                "created_at": uow.now,
                "created_by": principal.id,
                "created_by_kind": principal.kind.value,
            }
            for attachment_id, subject_id in zip(ids, subject_ids, strict=True)
        ],
    )
    detail: dict[str, Any] = {"file_object_id": str(file_object_id), "subject_type": subject_type}
    if approval_request_id is not None:
        detail["approval_request_id"] = str(approval_request_id)
    audit_writer.record_facts(
        uow,
        action=ATTACH_ACTION,
        object_type="file_attachment",
        ids=ids,
        detail=detail,
        contract_id=contract_id,
    )
    return ids


def void_attachment(uow: UnitOfWork, attachment_id: UUID, *, reason: str) -> Mapping[str, Any]:
    """``POST /attachments/{id}/void``: the person who attached the file voids the attachment
    (REQ-PLT-035; DB-11; 04 T-PLT-30 Subjects rev 1.189).

    An attachment the caller did not attach answers 404 ``not-found``, as an id that names none
    does, whatever the caller holds (ruling R-111 (5)); the attempt is kept as a ``DENIED`` audit
    event. The uploader voids with a write permission of the subject held for the subject's legal
    entity — 403 without the permission, 404 once the subject is outside its scope — or, on an
    approval request, as its requester while it is pending (ruling R-100 (b))."""
    current = _attachment_row(uow.session, attachment_id, lock=True)
    if current is None:
        raise Problem("not-found")
    principal = uow.principal
    if (
        current["created_by"] is None
        or current["created_by"] != principal.id
        or str(current["created_by_kind"]) != principal.kind.value
    ):
        audit_writer.record_denied(
            uow.ctx,
            action=VOID_ACTION,
            object_type="file_attachment",
            object_id=attachment_id,
            permission=VOID_ACTION,
            detail={"reason": "not-uploader"},
            keyring=uow.keyring,
        )
        raise Problem("not-found")
    subject = ATTACHMENT_SUBJECTS[str(current["subject_type"])]
    subject_id = UUID(str(current["subject_id"]))
    own = subject.own is not None and subject.own(uow.session, principal, subject_id)
    if not own:
        authorize(
            uow.ctx,
            subject.write,
            keyring=uow.keyring,
            action=VOID_ACTION,
            object_type="file_attachment",
            object_id=attachment_id,
        )
        if not subject.writable(uow.session, uow.ctx, subject_id):
            raise Problem("not-found")
    try:
        transitions.apply(
            uow.session,
            "file_attachment",
            attachment_id,
            to_status=None,
            set_values={
                "voided_at": uow.now,
                "voided_by": principal.id,
                "voided_by_kind": principal.kind.value,
                "void_reason": reason,
            },
        )
    except DBAPIError as error:
        # 04 §15.2 names no slug for EREV-ATT-001; a refused void is an unavailable action.
        if erev_code(error) != "EREV-ATT-001":
            raise
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(rule_id="DB-11", message=APPROVED_SUBJECT_MESSAGE)],
        ) from error
    uow.audit(
        action=VOID_ACTION,
        object_type="file_attachment",
        object_id=attachment_id,
        before={"voided_at": None, "void_reason": None},
        after={"voided_at": uow.now.isoformat(), "void_reason": reason},
        comment=reason,
    )
    return MappingProxyType(dict(_attachment_row(uow.session, attachment_id)))


def get_file(ctx: RequestContext, file_id: UUID) -> Mapping[str, Any]:
    """``GET /files/{id}``: a file the principal may read, as the principal may see it
    (``file_access.shown``: an uploader of the same bytes is shown its own file name, time and
    identity), else 404 — unknown, out of scope and not the caller's to read alike (REQ-PLT-012)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = (
            session.execute(select(file_object).where(file_object.c.id == file_id))
            .mappings()
            .one_or_none()
        )
        seen = None if row is None else file_access.shown(session, ctx, row)
        if seen is None:
            raise Problem("not-found")
        return seen


def file_content(
    ctx: RequestContext, file_id: UUID, *, files: FileStore, keyring: KeyRing
) -> tuple[Mapping[str, Any], bytes]:
    """``GET /files/{id}/content``: the plaintext of a readable file (UPL-10), with the row as
    the caller may see it — the download is named as the caller's own upload was.

    The read is audited, served or refused (04 T-PLT-29 "Content reads are audited"; ruling
    R-111 (6)): one ``file.download`` event in a transaction of its own before the answer —
    ``SUCCESS`` before the bytes, ``DENIED`` before the 404 of a file of the workspace the caller
    may not read. An id that names no file writes nothing: nothing was refused."""
    refused: str | None = None
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = (
            session.execute(select(file_object).where(file_object.c.id == file_id))
            .mappings()
            .one_or_none()
        )
        seen = None if row is None else file_access.shown(session, ctx, row)
        if seen is None:
            if row is None:
                raise Problem("not-found")
            refused = str(row["purpose"])
        else:
            _, stream = open_file(session, file_id, files=files, keyring=keyring)
    if seen is None:
        audit_writer.record_denied(
            ctx,
            action=DOWNLOAD_ACTION,
            object_type=file_access.FILE_OBJECT,
            object_id=file_id,
            permission="",
            detail={"reason": NOT_READABLE, "purpose": refused},
            keyring=keyring,
        )
        raise Problem("not-found")
    with stream:
        content = stream.read()
    audit_writer.record_now(
        ctx,
        action=DOWNLOAD_ACTION,
        object_type=file_access.FILE_OBJECT,
        object_id=file_id,
        detail={"purpose": str(seen["purpose"]), "sha256": str(seen["sha256"])},
        keyring=keyring,
    )
    return seen, content


def list_attachments[PageT](
    ctx: RequestContext,
    *,
    subject_type: str,
    subject_id: UUID,
    keyring: KeyRing,
    page: Callable[[Session, sa.Select[Any]], PageT],
) -> PageT:
    """``GET /attachments``: authorise the subject type, then ``page`` the attachments of the
    subject the caller reads. A subject the caller does not see — unknown, or outside the entity
    scope of the read permission — lists nothing (REQ-PLT-012).

    The route supplies ``page`` (the DG-LST ``paginate`` with its list specification), because list
    mechanics belong to the api layer (DG-LAY-03).
    """
    subject = ATTACHMENT_SUBJECTS[subject_type]
    if subject.read is not None:
        authorize(
            ctx,
            subject.read,
            keyring=keyring,
            action="file_attachment.read",
            object_type=subject_type,
            object_id=None,
        )
    statement = select(
        file_attachment,
        file_object.c.original_filename,
        file_object.c.media_type,
        file_object.c.size_bytes,
        file_object.c.sha256,
    ).join(
        file_object,
        sa.and_(
            file_object.c.tenant_id == file_attachment.c.tenant_id,
            file_object.c.id == file_attachment.c.file_object_id,
        ),
    )
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        if not subject.readable(session, ctx, subject_id):
            statement = statement.where(sa.false())
        return page(
            session,
            statement.where(
                file_attachment.c.subject_type == subject_type,
                file_attachment.c.subject_id == subject_id,
            ),
        )


@dataclass(frozen=True, slots=True)
class PreviewRefusal:
    """An approval refused because its impact preview cannot be read: the problem, and the
    request's status, which the refusal leaves as it is."""

    status: ApprovalRequestStatus
    problem: Problem


def preview_refusal(uow: UnitOfWork, approval_request_id: UUID) -> PreviewRefusal | None:
    """REQ-PLT-015: a request is approved only by someone who can read its impact preview.

    None when the request has no stored preview or the caller can read it; otherwise the 409
    ``invalid-transition`` that refuses the approval before any decision is written — the stored
    preview was shredded or is gone. A request whose content is not the caller's to read —
    unknown, out of scope, no step of theirs, or one of which they cover only some entities
    (``file_access.request_content_visible``; 04 §16.10 rev 1.208) — is left to the decision,
    which refuses it with its own answer: such a caller cannot decide it."""
    session = uow.session
    request = session.execute(
        select(approval_request.c.impact_preview_file_id, approval_request.c.status).where(
            approval_request.c.id == approval_request_id
        )
    ).one_or_none()
    if request is None or request.impact_preview_file_id is None:
        return None
    row = (
        session.execute(
            select(file_object).where(file_object.c.id == request.impact_preview_file_id)
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is not None
        and row["shredded_at"] is None
        and file_access.readable(session, uow.ctx, row)
    ):
        return None
    if not file_access.request_content_visible(session, uow.ctx, approval_request_id):
        return None
    return PreviewRefusal(
        status=ApprovalRequestStatus(request.status),
        problem=Problem(
            "invalid-transition",
            PREVIEW_UNREADABLE,
            errors=[ProblemError(rule_id=PREVIEW_RULE, message=PREVIEW_UNREADABLE)],
        ),
    )


def require_preview_readable(uow: UnitOfWork, approval_request_id: UUID) -> None:
    """Raise the problem of ``preview_refusal`` when there is one (``POST
    /approvals/{id}/approve``)."""
    refusal = preview_refusal(uow, approval_request_id)
    if refusal is not None:
        raise refusal.problem
