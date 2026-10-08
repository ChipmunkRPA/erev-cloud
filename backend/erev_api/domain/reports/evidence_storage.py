"""Atomic encrypted retention for verified first-close packs (RPS-16).

The caller owns the transaction and job lifecycle. No commit, job creation or
public download occurs here. Repeated completion verifies the retained output;
it never replaces a succeeded pack or silently rebuilds a damaged archive.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import evidence_pack
from erev_api.db.transitions import apply
from erev_api.domain.reports import evidence_assembly
from erev_api.domain.reports.evidence_archive import Archive, InvalidArchive, verify
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file, store_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class StoredClose:
    file_id: UUID
    archive: Archive


def checked_stored(
    row: Mapping[str, Any], metadata: Mapping[str, Any], content: bytes, expected: Archive
) -> None:
    """Bind the stored row, encrypted file and manifest to the reauthorized source bytes."""
    if (
        row["status"] != "SUCCEEDED"
        or row["file_id"] != metadata["id"]
        or row["tenant_id"] != metadata["tenant_id"]
        or metadata["purpose"] != FilePurpose.EVIDENCE_PACK
        or metadata["media_type"] != "application/zip"
        or metadata["size_bytes"] != len(content)
        or metadata["sha256"] != hashlib.sha256(content).hexdigest()
        or row["manifest_sha256"] != expected.manifest_sha256
        or row["manifest"] != expected.manifest_document()
        or content != expected.content
    ):
        raise Problem("validation-failed", "The retained evidence pack failed verification.")
    try:
        verify(content, expected_manifest_sha256=row["manifest_sha256"])
    except InvalidArchive as error:
        raise Problem("validation-failed", "The retained evidence archive is invalid.") from error


def read_close(uow: UnitOfWork, pack_id: UUID) -> StoredClose:
    """Read a completed pack under current source/export scope; never finish pending work."""
    if "evidence.export" not in uow.principal.permissions:
        raise Problem("forbidden")
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
                evidence_pack.c.kind == "CLOSE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, "evidence.export", row["entity_id"])
    if row["status"] != "SUCCEEDED":
        raise Problem("invalid-transition", "The evidence pack has not completed.")
    archive = evidence_assembly.assemble_close(uow, pack_id)
    return _retained(uow, dict(row), archive)


def _retained(uow: UnitOfWork, row: Mapping[str, Any], archive: Archive) -> StoredClose:
    if row["file_id"] is None:
        raise Problem("validation-failed", "The succeeded evidence pack has no file.")
    metadata, stream = open_file(uow.session, row["file_id"], files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read(len(archive.content) + 1)
    checked_stored(row, metadata, content, archive)
    return StoredClose(row["file_id"], archive)


def finish_close(uow: UnitOfWork, pack_id: UUID) -> StoredClose:
    """Finish a RUNNING pack atomically, or verify and reuse an already SUCCEEDED output."""
    if "evidence.export" not in uow.principal.permissions:
        raise Problem("forbidden")
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
                evidence_pack.c.kind == "CLOSE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, "evidence.export", row["entity_id"])
    # Serialize completion/retry after authorization, before inspecting output state.
    row = (
        uow.session.execute(
            select(evidence_pack)
            .where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
            )
            .with_for_update()
        )
        .mappings()
        .one()
    )
    if row["status"] not in {"RUNNING", "SUCCEEDED"}:
        raise Problem("invalid-transition", "Only a running or succeeded close pack can finish.")
    archive = evidence_assembly.assemble_close(uow, pack_id)
    if row["status"] == "SUCCEEDED":
        return _retained(uow, dict(row), archive)
    if any(row[key] is not None for key in ("file_id", "manifest", "manifest_sha256")):
        raise Problem("validation-failed", "The running evidence pack already contains output.")
    stored = store_file(
        uow,
        purpose=FilePurpose.EVIDENCE_PACK,
        stream=io.BytesIO(archive.content),
        original_filename=f"{row['pack_no']}.zip",
        media_type="application/zip",
    )
    apply(
        uow.session,
        "evidence_pack",
        pack_id,
        to_status="SUCCEEDED",
        expected_status="RUNNING",
        set_values={
            "file_id": stored["id"],
            "manifest": archive.manifest_document(),
            "manifest_sha256": archive.manifest_sha256,
            "updated_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": uow.principal.kind.value,
        },
    )
    uow.audit(
        action="evidence.finish",
        object_type="evidence_pack",
        object_id=pack_id,
        contract_ids=row["contract_ids"],
        before={"status": "RUNNING"},
        after={
            "status": "SUCCEEDED",
            "file_id": str(stored["id"]),
            "manifest_sha256": archive.manifest_sha256,
        },
    )
    return StoredClose(UUID(str(stored["id"])), archive)
