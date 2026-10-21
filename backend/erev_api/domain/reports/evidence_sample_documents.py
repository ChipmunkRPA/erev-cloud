"""Retained attachment bytes for a contract sample, using current file-read grants.

Only stored attachments are collected. Document references are never fetched as URLs,
and shared raw import uploads are not substituted for missing attachments. A historical
attachment with unavailable or no-longer-readable bytes refuses the collection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import and_, func, or_, select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import (
    approval_request,
    contract_event,
    file_attachment,
    report_source_revision,
)
from erev_api.domain.platform import file_access
from erev_api.domain.platform.attachments import ATTACHABLE_PURPOSES
from erev_api.domain.reports.evidence_archive import MAX_FILES, MAX_PAYLOAD_BYTES, PackFile
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.enums import FilePurpose
from erev_api.files.store import lock_readable, open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class SampleDocuments:
    files: tuple[PackFile, ...]
    attachment_ids: tuple[UUID, ...]
    file_ids: tuple[UUID, ...]


def collect(
    uow: UnitOfWork,
    selected: SourceSelection,
    *,
    as_of: date,
    event_ids: tuple[UUID, ...],
    approval_request_ids: tuple[UUID, ...],
) -> SampleDocuments:
    if (
        selected.tenant_id != uow.principal.tenant_id
        or not selected.contract_ids
        or selected.known_at.tzinfo is None
        or selected.known_at > uow.now
        or not PERMISSIONS <= uow.principal.permissions
    ):
        raise Problem("forbidden")
    for entity in selected.entity_ids:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity)
    for contract_id in selected.contract_ids:
        if not file_access.ATTACHMENT_SUBJECTS["contract"].readable(
            uow.session, uow.ctx, contract_id
        ):
            raise Problem("not-found")
    tenant = selected.tenant_id
    cutoff = selected.known_at
    subjects: set[tuple[str, UUID]] = {("contract", key) for key in selected.contract_ids}
    events = (
        uow.session.execute(
            select(contract_event).where(
                contract_event.c.tenant_id == tenant,
                contract_event.c.id.in_(event_ids),
                contract_event.c.contract_id.in_(selected.contract_ids),
                contract_event.c.recorded_at <= cutoff,
                func.erev.source_commit_time("contract_event", contract_event.c.id) <= cutoff,
                contract_event.c.effective_date <= as_of,
            )
        )
        .mappings()
        .all()
        if event_ids
        else []
    )
    if {row["id"] for row in events} != set(event_ids):
        raise Problem(
            "validation-failed", "Sample document event references differ from the selection."
        )
    for event in events:
        subjects.add(("contract_event", event["id"]))
        for kind in ("modification", "estimate_version", "manual_adjustment"):
            if event[f"{kind}_id"] is not None:
                subjects.add((kind, event[f"{kind}_id"]))
    requests = (
        uow.session.execute(
            select(
                approval_request.c.id,
                approval_request.c.subject_type,
                approval_request.c.subject_id,
            ).where(
                approval_request.c.tenant_id == tenant,
                approval_request.c.id.in_(approval_request_ids),
                approval_request.c.submitted_at <= cutoff,
            )
        ).all()
        if approval_request_ids
        else []
    )
    if {row.id for row in requests} != set(approval_request_ids):
        raise Problem("validation-failed", "Sample document approval references are unavailable.")
    for request in requests:
        subjects.add(("approval_request", request.id))
        kind = str(request.subject_type).lower()
        if kind in file_access.ATTACHMENT_SUBJECTS:
            subjects.add((kind, request.subject_id))
    candidates = (
        uow.session.execute(
            select(file_attachment)
            .where(
                file_attachment.c.tenant_id == tenant,
                file_attachment.c.created_at <= cutoff,
                or_(
                    *(
                        and_(
                            file_attachment.c.subject_type == kind,
                            file_attachment.c.subject_id == key,
                        )
                        for kind, key in sorted(subjects)
                    )
                ),
            )
            .order_by(
                file_attachment.c.subject_type,
                file_attachment.c.subject_id,
                file_attachment.c.created_at,
                file_attachment.c.id,
            )
        )
        .mappings()
        .all()
    )
    # Subject and file identity are immutable; revisions decide creation/void visibility.
    revision = report_source_revision
    revisions = uow.session.execute(
        select(
            revision.c.source_id,
            revision.c.id,
            revision.c.document,
            func.erev.source_commit_time("report_source_revision", revision.c.id).label(
                "committed_at"
            ),
        )
        .where(
            revision.c.tenant_id == tenant,
            revision.c.source_kind == "file_attachment",
            revision.c.source_id.in_([row["id"] for row in candidates]),
            revision.c.recorded_at <= cutoff,
            func.erev.source_commit_time("report_source_revision", revision.c.id) <= cutoff,
        )
        .distinct(revision.c.source_id)
        .order_by(revision.c.source_id, revision.c.revision_no.desc())
    ).mappings()
    visible = {}
    for captured in revisions:
        document = captured["document"]
        if document["voided_at"] is not None:
            continue
        restored = dict(document)
        for key in ("id", "file_object_id", "subject_id"):
            restored[key] = UUID(restored[key])
        restored["created_at"] = datetime.fromisoformat(restored["created_at"])
        restored["source_revision_id"] = captured["id"]
        restored["committed_at"] = captured["committed_at"]
        visible[restored["id"]] = restored
    attachments = [visible[row["id"]] for row in candidates if row["id"] in visible]
    # Authorize the owning subject as well as the file. Being its uploader must not bypass
    # permission to read the sample's contract or approval evidence.
    for attachment in attachments:
        subject = file_access.ATTACHMENT_SUBJECTS[attachment["subject_type"]]
        if not subject.readable(uow.session, uow.ctx, attachment["subject_id"]):
            raise Problem("not-found")
    ids = tuple(sorted({row["file_object_id"] for row in attachments}))
    if len(ids) + 1 > MAX_FILES:
        raise Problem("validation-failed", "Sample attachments exceed the archive file limit.")
    metadata = {}
    for file_id in ids:
        row = file_access.bound(uow.session, uow.ctx, file_id)
        if row is None:
            raise Problem("not-found")
        if row["created_at"] > cutoff or FilePurpose(row["purpose"]) not in ATTACHABLE_PURPOSES:
            raise Problem(
                "validation-failed", "A sample attachment has inconsistent file metadata."
            )
        metadata[file_id] = row
    if sum(row["size_bytes"] for row in metadata.values()) > MAX_PAYLOAD_BYTES:
        raise Problem(
            "validation-failed", "Sample attachments exceed the evidence archive size limit."
        )
    if lock_readable(uow.session, ids) != frozenset(ids):
        raise Problem("validation-failed", "A sample attachment is no longer available.")
    files = []
    for file_id in ids:
        expected = metadata[file_id]
        try:
            stored, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
            with stream:
                content = stream.read(expected["size_bytes"] + 1)
        except FileNotFoundError as error:
            raise Problem(
                "validation-failed", "A sample attachment's stored bytes are missing."
            ) from error
        if (
            len(content) != expected["size_bytes"]
            or stored["sha256"] != expected["sha256"]
            or hashlib.sha256(content).hexdigest() != expected["sha256"]
        ):
            raise Problem("validation-failed", "A sample attachment failed its integrity check.")
        # Untrusted names are display metadata only; identifiers determine archive paths.
        files.append(PackFile(f"documents/{file_id}/content", content))
    index = [
        {
            "attachment_id": row["id"],
            "subject_type": row["subject_type"],
            "subject_id": row["subject_id"],
            "file_id": row["file_object_id"],
            "attached_at": row["created_at"],
            "source_revision_id": row["source_revision_id"],
            "committed_at": row["committed_at"],
            "description": row["description"],
            "path": f"documents/{row['file_object_id']}/content",
            "original_filename": metadata[row["file_object_id"]]["original_filename"],
            "media_type": metadata[row["file_object_id"]]["media_type"],
            "bytes": metadata[row["file_object_id"]]["size_bytes"],
            "sha256": metadata[row["file_object_id"]]["sha256"],
        }
        for row in attachments
    ]
    files.insert(
        0,
        PackFile(
            "sample/documents.json",
            canonical_bytes(
                {
                    "schema_version": 2,
                    "as_of": as_of,
                    "known_at": cutoff,
                    "attachments": index,
                    "basis": "Committed attachment revisions at cutoff; current file grants "
                    "and integrity checks required; no external references fetched.",
                }
            ),
        ),
    )
    return SampleDocuments(tuple(files), tuple(row["id"] for row in attachments), ids)
