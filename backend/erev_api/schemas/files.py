"""API-R-12 files and attachments schemas (04 T-PLT-29, T-PLT-30; DG-API-03).

04 §15.3 names no P0 schema for API-R-12, so the responses carry the table columns a client needs:
metadata and hashes, never storage keys.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import FilePurpose, PrincipalKind

# 04 T-PLT-30 ``ck_file_attachment__subject_type``.
SubjectType = Literal[
    "contract",
    "modification",
    "estimate_version",
    "ssp_book_version",
    "judgement_record",
    "manual_adjustment",
    "reconciliation",
    "sod_exception",
    "approval_request",
    "exception_item",
    "contract_event",
    "event_submission",
]


class FileOut(BaseModel):
    """A stored file (T-PLT-29)."""

    id: uuid.UUID
    purpose: FilePurpose
    media_type: str
    original_filename: str | None
    size_bytes: int
    sha256: str
    legal_hold: bool
    retention_until: date | None
    shredded_at: datetime | None
    shred_completed_at: datetime | None = Field(
        description=(
            "When the file's wrapped key was destroyed and that was recorded. Empty for a file "
            "that is not shredded, and for one whose shred is decided (`shredded_at`) and not "
            "yet completed: its content is refused already, and the same command sent again "
            "under a new `Idempotency-Key`, or the platform's sweep, completes it (05 PRV-07 b)."
        ),
    )
    created_at: datetime
    created_by: uuid.UUID | None
    created_by_kind: PrincipalKind


class AttachmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_object_id: uuid.UUID
    subject_type: SubjectType
    subject_id: uuid.UUID
    description: str | None = Field(default=None, min_length=1, max_length=400)


class AttachmentVoidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=4000)


class FileShredIn(BaseModel):
    """``POST /files/{id}/shred`` (05 PRV-07 b): the reason is required and recorded on the row."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=4000)


class FileShredRequestOut(BaseModel):
    """``POST /files/{id}/request-shred`` (05 PRV-07 b rev 1.81; rulings R-49 (a), R-86): the
    pending ``EVIDENCE_SHRED`` approval request, and the file, which is unchanged until it is
    decided."""

    approval_request_id: uuid.UUID
    file: FileOut


class AttachmentOut(BaseModel):
    """A file attached to a subject (T-PLT-30) with the file's name, type, size and hash."""

    id: uuid.UUID
    file_object_id: uuid.UUID
    subject_type: SubjectType
    subject_id: uuid.UUID
    description: str | None
    original_filename: str | None
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    created_by: uuid.UUID | None
    created_by_kind: PrincipalKind
    voided_at: datetime | None
    voided_by: uuid.UUID | None
    voided_by_kind: PrincipalKind | None
    void_reason: str | None


def file_out(row: Mapping[str, Any]) -> FileOut:
    return FileOut(
        id=row["id"],
        purpose=FilePurpose(row["purpose"]),
        media_type=row["media_type"],
        original_filename=row["original_filename"],
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]),
        legal_hold=bool(row["legal_hold"]),
        retention_until=row["retention_until"],
        shredded_at=row["shredded_at"],
        shred_completed_at=row.get("shred_completed_at"),
        created_at=row["created_at"],
        created_by=row["created_by"],
        created_by_kind=PrincipalKind(row["created_by_kind"]),
    )


def attachment_out(row: Mapping[str, Any]) -> AttachmentOut:
    voided_by_kind = row["voided_by_kind"]
    return AttachmentOut(
        id=row["id"],
        file_object_id=row["file_object_id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        description=row["description"],
        original_filename=row["original_filename"],
        media_type=row["media_type"],
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]),
        created_at=row["created_at"],
        created_by=row["created_by"],
        created_by_kind=PrincipalKind(row["created_by_kind"]),
        voided_at=row["voided_at"],
        voided_by=row["voided_by"],
        voided_by_kind=None if voided_by_kind is None else PrincipalKind(voided_by_kind),
        void_reason=row["void_reason"],
    )
