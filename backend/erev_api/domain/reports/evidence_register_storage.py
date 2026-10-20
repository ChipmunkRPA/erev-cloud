"""Encrypted CHANGE/ACCESS archive completion; retained reads never rebuild reports."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.db.tables import evidence_pack
from erev_api.db.transitions import apply
from erev_api.domain.reports import evidence_archive
from erev_api.domain.reports import evidence_register_sources as sources
from erev_api.domain.reports.evidence_archive import Archive, PackFile
from erev_api.domain.reports.evidence_storage import StoredClose
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file, store_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def complete_binding(bound: sources.RegisterBinding) -> None:
    if not isinstance(bound, (sources.ChangeSources, sources.CompleteAccessSources)):
        raise Problem("validation-failed", "This pack has incomplete legacy register sources.")


def _row(uow: UnitOfWork, pack_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    query = select(evidence_pack).where(
        evidence_pack.c.tenant_id == uow.principal.tenant_id,
        evidence_pack.c.id == pack_id,
        evidence_pack.c.kind.in_(("CHANGE", "ACCESS")),
    )
    if lock:
        query = query.with_for_update()
    row = uow.session.execute(query).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def payloads(uow: UnitOfWork, row: Mapping[str, Any]) -> tuple[PackFile, ...]:
    bound = sources.load(uow, row["id"])
    complete_binding(bound)
    result = sources.collect(uow, row["id"])
    runs = {file.report_run_id for file in result if file.report_run_id is not None}
    if runs != set(row["report_run_ids"]):
        raise Problem("validation-failed", "Pack report population differs from retained sources.")
    return (
        *result,
        PackFile(
            "pack.json",
            canonical_bytes(
                {
                    "id": row["id"],
                    "pack_no": row["pack_no"],
                    "kind": row["kind"],
                    "created_at": row["created_at"],
                    "created_by": row["created_by"],
                    "request": bound.request.model_dump(mode="json"),
                    "known_at": bound.known_at,
                    "entity_ids": bound.entity_ids,
                    "entity_codes": bound.entity_codes,
                    "report_run_ids": row["report_run_ids"],
                }
            ),
        ),
    )


def _stored(uow: UnitOfWork, row: Mapping[str, Any], expected: tuple[PackFile, ...]) -> StoredClose:
    if row["file_id"] is None or row["manifest"] is None or row["manifest_sha256"] is None:
        raise Problem("validation-failed", "The completed pack has no retained output.")
    metadata, stream = open_file(uow.session, row["file_id"], files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read(512 * 1024 * 1024 + 1)
    if (
        metadata["tenant_id"] != uow.principal.tenant_id
        or metadata["purpose"] != FilePurpose.SNAPSHOT_DATASET
        or metadata["media_type"] != "application/zip"
        or len(content) > 512 * 1024 * 1024
        or metadata["size_bytes"] != len(content)
        or metadata["sha256"] != hashlib.sha256(content).hexdigest()
    ):
        raise Problem("validation-failed", "The retained pack output failed verification.")
    try:
        manifest = evidence_archive.verify(content, expected_manifest_sha256=row["manifest_sha256"])
        if manifest != row["manifest"]:
            raise ValueError("manifest")
        if {entry["path"]: entry["report_run_id"] for entry in manifest["files"]} != {
            file.path: str(file.report_run_id) if file.report_run_id is not None else None
            for file in expected
        }:
            raise ValueError("population")
        with zipfile.ZipFile(io.BytesIO(content)) as exported:
            if any(exported.read(file.path) != file.content for file in expected):
                raise ValueError("retained source bytes")
            manifest_bytes = exported.read("manifest.json")
    except (ValueError, KeyError, zipfile.BadZipFile) as error:
        raise Problem(
            "validation-failed", "The retained pack archive differs from its sources."
        ) from error
    return StoredClose(row["file_id"], Archive(content, manifest_bytes, row["manifest_sha256"]))


def read(uow: UnitOfWork, pack_id: UUID) -> StoredClose:
    bound = sources.load(uow, pack_id)
    complete_binding(bound)
    row = _row(uow, pack_id)
    if row["status"] != "SUCCEEDED":
        raise Problem("invalid-transition", "The evidence pack has not completed.")
    return _stored(uow, row, payloads(uow, row))


def finish(uow: UnitOfWork, pack_id: UUID) -> StoredClose:
    bound = sources.load(uow, pack_id)
    complete_binding(bound)
    row = _row(uow, pack_id, lock=True)
    if row["status"] == "SUCCEEDED":
        return _stored(uow, row, payloads(uow, row))
    if row["status"] != "RUNNING":
        raise Problem("invalid-transition", "Only a running evidence pack can finish.")
    if any(row[key] is not None for key in ("file_id", "manifest", "manifest_sha256")):
        raise Problem("validation-failed", "The running pack already contains output.")
    try:
        archive = evidence_archive.build(payloads(uow, row))
    except evidence_archive.InvalidArchive as error:
        raise Problem("validation-failed", f"The pack cannot be assembled: {error}") from error
    if len(archive.content) > 512 * 1024 * 1024:
        raise Problem("validation-failed", "The evidence pack exceeds the retained size limit.")
    stored = store_file(
        uow,
        purpose=FilePurpose.SNAPSHOT_DATASET,
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
        contract_ids=[],
        before={"status": "RUNNING"},
        after={
            "status": "SUCCEEDED",
            "file_id": stored["id"],
            "manifest_sha256": archive.manifest_sha256,
        },
    )
    return StoredClose(stored["id"], archive)
