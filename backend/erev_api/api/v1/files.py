"""API-R-12 Files and attachments (04 §15.3 API-R-12, T-PLT-29, T-PLT-30; 05 UPL-10; BUILD_SPEC
PLF-8).

Uploads and attachment commands authorise per purpose and per subject inside their handlers
(SPEC-Q-157), so the command routes depend on ``command(per_subject=True)`` and the reads on
``require_authenticated()``. The upload is an ``UploadRoute``: its caller is authenticated, and
the body bounded by what that caller may upload, before the multipart form is read (DG-API-12).
A file is read through a record that owns it, by that record's read permission for its legal
entity (04 T-PLT-29 "Read access"; ``domain.platform.file_access``).
``POST /files/{id}/shred`` (05 PRV-07 b; BUILD_SPEC SOP-5) needs ``settings.manage``, whose MFA
gate applies (API-C-03), and a reason. ``POST /files/{id}/request-shred`` (05 rev 1.81; rulings
R-49 (a), R-86) needs the same permission, a step-up at most five minutes old and a reason of
at least ten characters: it opens the ``EVIDENCE_SHRED`` approval that shreds a file a record
holds as its evidence.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Annotated, Any, Final
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.api.uploads import UploadRoute
from erev_api.auth.dependencies import require_authenticated
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import file_attachment
from erev_api.domain.platform import attachments, evidence_shred, privacy
from erev_api.schemas.common import ListOut
from erev_api.schemas.files import (
    AttachmentCreateIn,
    AttachmentOut,
    AttachmentVoidIn,
    FileOut,
    FileShredIn,
    FileShredRequestOut,
    SubjectType,
    attachment_out,
    file_out,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-12 Files and attachments"
ATTACHMENT_LIST: Final = ListSpec(
    resource="attachments",
    sort_keys={"id": file_attachment.c.id},
    default_sort="-id",
    filters={
        "subject_type": FilterSpec("subject_type", file_attachment.c.subject_type, "exact"),
        "subject_id": FilterSpec("subject_id", file_attachment.c.subject_id, "exact"),
    },
)
# 05 UPL-10: downloads never render inline.
DOWNLOAD_CSP: Final = "sandbox"
OCTET_STREAM: Final = "application/octet-stream"
# 05 PRV-07 b: the shred permission (04 API-R-12); its requires_mfa flag applies (API-C-03).
SHRED_PERMISSION: Final = privacy.SHRED_PERMISSION
_READ_PROBLEMS: Final = (
    "unauthenticated",
    "session-expired",
    "forbidden",
    "mfa-required",
    "not-found",
)
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_UNSAFE_FILENAME: Final = re.compile(r"[\x00-\x1f\x7f\"\\/]")

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def content_disposition(row: Mapping[str, Any]) -> str:
    """``attachment; filename*=UTF-8''<sanitised name>``; the name is metadata only (UPL-11)."""
    name = _UNSAFE_FILENAME.sub("_", str(row["original_filename"] or row["sha256"])).strip() or str(
        row["sha256"]
    )
    return f"attachment; filename*=UTF-8''{quote(name, safe='')}"


def files_upload(
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    purpose: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> Response:
    """Upload a file of purpose IMPORT_SOURCE, ATTACHMENT, SSP_STUDY or LEGACY_DATABASE; identical
    content of the same purpose returns the existing file."""

    def handler(uow: UnitOfWork) -> FileOut:
        row = attachments.upload_file(
            uow,
            purpose=purpose,
            stream=None if file is None else file.file,
            original_filename=None if file is None else file.filename,
            media_type=OCTET_STREAM if file is None else file.content_type or OCTET_STREAM,
        )
        return file_out(row)

    return run_command(
        cmd,
        deps,
        handler,
        status_code=201,
        location=lambda result: f"{API_PREFIX}/files/{result.id}",
    )


# DG-API-12 (04 API-C-17 rev 1.189; ruling R-111 (8)): the one multipart route. ``UploadRoute``
# authenticates the caller and bounds the body before the form is parsed, which the decorator's
# route class cannot do — FastAPI reads a form before it solves a route's dependencies.
router.add_api_route(
    "/files",
    files_upload,
    methods=["POST"],
    status_code=201,
    operation_id="files_upload",
    response_model=FileOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "upload-type-not-allowed"),
    route_class_override=UploadRoute,
)


@router.get(
    "/files/{file_id}",
    operation_id="files_get",
    response_model=FileOut,
    responses=problem_responses(*_READ_PROBLEMS),
)
def files_get(
    file_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
) -> FileOut:
    """File metadata: purpose, type, size and SHA-256 of the plaintext."""
    return file_out(attachments.get_file(ctx, file_id))


@router.get(
    "/files/{file_id}/content",
    operation_id="files_content",
    response_class=Response,
    responses={
        200: {"content": {OCTET_STREAM: {}}, "description": "The file's bytes as a download"},
        **problem_responses(*_READ_PROBLEMS),
    },
)
def files_content(
    file_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Download a file as an attachment with the UPL-10 headers."""
    row, content = attachments.file_content(ctx, file_id, files=deps.files, keyring=deps.keyring)
    return Response(
        content=content,
        media_type=str(row["media_type"]),
        headers={
            "Content-Disposition": content_disposition(row),
            "Content-Security-Policy": DOWNLOAD_CSP,
        },
    )


@router.post(
    "/files/{file_id}/shred",
    operation_id="files_shred",
    response_model=FileOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition", "sandbox-restricted"),
)
def files_shred(
    file_id: uuid.UUID,
    body: FileShredIn,
    cmd: Annotated[CommandContext, Depends(command(SHRED_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Shred the file (05 PRV-07 b): the shred is decided on the row and audited, and the file's
    wrapped data key is destroyed after that commit, so its bytes become unreadable; the row and
    its SHA-256 stay as evidence. The answer is the file as decided; ``shred_completed_at`` is set
    once the key's destruction is recorded — normally before this answer is sent — and
    ``GET /files/{id}`` shows it. Sent again under a new ``Idempotency-Key`` for a file decided
    and not completed, the command completes the shred and answers the completed file (409
    ``lock-conflict`` while a wrapped key is live again in the store). Refused while a legal hold
    or retention applies (``FILE_RETENTION_ACTIVE``), once the shred is completed
    (``FILE_SHREDDED``), while a standing record
    references the file as its evidence (``FILE_EVIDENCE_HELD``, or
    ``FILE_SHRED_APPROVAL_REQUIRED`` where an approved request may release it; rulings R-30,
    R-49, R-86), and for plaintext-stored purposes until their erasure is ruled (``PRV-06``).
    Every refusal is audited as ``DENIED``. 403 for an administrator whose ``settings.manage``
    does not cover every legal entity of the records that reference the file — every entity for
    a file no record references — asked before any refusal names a record (04 T-PLT-29 "Shred
    scope"). In a sandbox a file it shares with the workspace it was copied from answers 403
    ``sandbox-restricted``; a file the sandbox stored itself is its own (05 SBX-08)."""
    return run_command(
        cmd,
        deps,
        lambda uow: file_out(
            privacy.shred_file(uow, file_id, reason=body.reason, files=deps.files)
        ),
    )


@router.post(
    "/files/{file_id}/request-shred",
    operation_id="files_request_shred",
    response_model=FileShredRequestOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "invalid-transition", "mfa-step-up-required", "sandbox-restricted"
    ),
)
def files_request_shred(
    file_id: uuid.UUID,
    body: FileShredIn,
    cmd: Annotated[CommandContext, Depends(command(SHRED_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Ask for a file that a record holds as its evidence to be shredded (05 PRV-07 b; rulings
    R-49 (a), R-86): the source of a committed import, the source file of a signed
    reconciliation, the legacy database of a migration, an SSP study, the attachment of a manual
    adjustment. One person does not shred such a file — this opens an ``EVIDENCE_SHRED`` approval
    bound to the legal entities of those records, which a Controller of all of them decides, and
    the approval shreds. Needs a step-up at most five minutes old and a reason of at least 10
    characters that names the erasure request. Refused for a file no record holds (``PRV-07``:
    shred it directly), for a file a record holds without override (``FILE_EVIDENCE_HELD``), once
    shredded, under a legal hold or retention, and while a request for the file is pending; 403
    for a requester whose ``settings.manage`` does not cover every legal entity of the records
    that reference the file, asked before any refusal names a record (04 T-PLT-29 "Shred scope").
    Nothing changes until the decision. In a sandbox a file it shares with the workspace it was
    copied from answers 403 ``sandbox-restricted``, and the approval of a request for such a
    file is refused there too; a file the sandbox stored itself is its own (05 SBX-08)."""

    def handle(uow: UnitOfWork) -> FileShredRequestOut:
        requested = evidence_shred.request_shred(uow, file_id, reason=body.reason)
        return FileShredRequestOut(
            approval_request_id=requested.approval_request_id, file=file_out(requested.file)
        )

    return run_command(cmd, deps, handle)


@router.get(
    "/attachments",
    operation_id="attachments_list",
    response_model=ListOut[AttachmentOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def attachments_list(
    response: Response,
    subject_type: Annotated[SubjectType, Query()],
    subject_id: Annotated[uuid.UUID, Query()],
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[AttachmentOut]:
    """The attachments of one subject record, newest first (DG-LST)."""
    result = attachments.list_attachments(
        ctx,
        subject_type=subject_type,
        subject_id=subject_id,
        keyring=deps.keyring,
        page=lambda session, statement: paginate(session, statement, ATTACHMENT_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AttachmentOut](
        items=[attachment_out(row) for row in result.items], next_cursor=result.next_cursor
    )


@router.post(
    "/attachments",
    status_code=201,
    operation_id="attachments_create",
    response_model=AttachmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def attachments_create(
    body: AttachmentCreateIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Attach an uploaded attachment or SSP study to a subject record."""

    def handler(uow: UnitOfWork) -> AttachmentOut:
        row = attachments.attach(
            uow,
            file_object_id=body.file_object_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            description=body.description,
        )
        return attachment_out(row)

    return run_command(cmd, deps, handler, status_code=201)


@router.post(
    "/attachments/{attachment_id}/void",
    operation_id="attachments_void",
    response_model=AttachmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def attachments_void(
    attachment_id: uuid.UUID,
    body: AttachmentVoidIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Void an attachment you uploaded, while no approval relies on its subject (DB-11)."""
    return run_command(
        cmd,
        deps,
        lambda uow: attachment_out(
            attachments.void_attachment(uow, attachment_id, reason=body.reason)
        ),
    )
