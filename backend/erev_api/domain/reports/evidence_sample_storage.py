"""Atomic completion and verified retained reads for contract sample evidence packs.

The job owns commit/cancellation fencing. A succeeded pack is read as stored and never
rendered again; its source archive and original documents still require current access.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import evidence_pack
from erev_api.db.transitions import apply
from erev_api.domain.reports import (
    evidence_archive,
    evidence_sample_rendering,
    evidence_sample_sources,
)
from erev_api.domain.reports.evidence_archive import Archive
from erev_api.domain.reports.evidence_storage import StoredClose
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file, store_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

OUTPUTS = frozenset({"reports/contract_sample.pdf", "reports/contract_sample.xlsx"})


def _row(uow: UnitOfWork, pack_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    query = select(evidence_pack).where(
        evidence_pack.c.tenant_id == uow.principal.tenant_id,
        evidence_pack.c.id == pack_id,
        evidence_pack.c.kind == "CONTRACT_SAMPLE",
    )
    if lock:
        query = query.with_for_update()
    row = uow.session.execute(query).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _stored(uow: UnitOfWork, row: Mapping[str, Any], source: Archive) -> StoredClose:
    if row["file_id"] is None or row["manifest"] is None or row["manifest_sha256"] is None:
        raise Problem("validation-failed", "The completed sample has no retained output.")
    metadata, stream = open_file(uow.session, row["file_id"], files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read(512 * 1024 * 1024 + 1)
    if (
        metadata["tenant_id"] != uow.principal.tenant_id
        or metadata["purpose"] != FilePurpose.SNAPSHOT_DATASET
        or metadata["media_type"] != "application/zip"
        or metadata["size_bytes"] != len(content)
        or metadata["sha256"] != hashlib.sha256(content).hexdigest()
    ):
        raise Problem("validation-failed", "The retained sample output failed verification.")
    try:
        evidence_archive.verify(content, expected_manifest_sha256=row["manifest_sha256"])
        with (
            zipfile.ZipFile(io.BytesIO(content)) as exported,
            zipfile.ZipFile(io.BytesIO(source.content)) as original,
        ):
            manifest = exported.read("manifest.json")
            document = json.loads(manifest)
            if document != row["manifest"]:
                raise ValueError("manifest binding")
            sources = {entry["path"] for entry in source.manifest_document()["files"]}
            if {entry["path"] for entry in document["files"]} != sources | OUTPUTS:
                raise ValueError("source population")
            if any(exported.read(path) != original.read(path) for path in sources):
                raise ValueError("source content")
            if not exported.read("reports/contract_sample.pdf").startswith(b"%PDF-"):
                raise ValueError("PDF")
            with zipfile.ZipFile(io.BytesIO(exported.read("reports/contract_sample.xlsx"))) as book:
                if "xl/workbook.xml" not in book.namelist():
                    raise ValueError("XLSX")
    except (evidence_archive.InvalidArchive, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise Problem("validation-failed", "The retained sample archive is invalid.") from error
    return StoredClose(row["file_id"], Archive(content, manifest, row["manifest_sha256"]))


def read(uow: UnitOfWork, pack_id: UUID) -> StoredClose:
    bound = evidence_sample_sources.load(uow, pack_id)
    row = _row(uow, pack_id)
    if row["status"] != "SUCCEEDED":
        raise Problem("invalid-transition", "The contract sample has not completed.")
    return _stored(uow, row, evidence_sample_sources.read(uow, bound))


def finish(uow: UnitOfWork, pack_id: UUID) -> StoredClose:
    """Authorize before locking, render once, publish output and transition atomically."""
    bound = evidence_sample_sources.load(uow, pack_id)
    row = _row(uow, pack_id, lock=True)
    if row["status"] == "SUCCEEDED":
        return _stored(uow, row, evidence_sample_sources.read(uow, bound))
    if row["status"] != "RUNNING":
        raise Problem("invalid-transition", "Only a running contract sample can finish.")
    if any(row[key] is not None for key in ("file_id", "manifest", "manifest_sha256")):
        raise Problem("validation-failed", "The running sample already contains output.")
    stamp = bound.render_stamp
    if stamp is None or stamp.report_run_no != row["pack_no"] or stamp.run_at != row["created_at"]:
        raise Problem("validation-failed", "The sample has no matching retained render stamp.")
    archive = evidence_sample_rendering.assemble(uow, pack_id, stamp)
    # The final archive contains the same sensitive originals as its encrypted source snapshot.
    # SNAPSHOT_DATASET keeps per-file encryption without changing legacy cleartext CLOSE files.
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
        contract_ids=row["contract_ids"],
        before={"status": "RUNNING"},
        after={
            "status": "SUCCEEDED",
            "file_id": stored["id"],
            "manifest_sha256": archive.manifest_sha256,
        },
    )
    return StoredClose(stored["id"], archive)
