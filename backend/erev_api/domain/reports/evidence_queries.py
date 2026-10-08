"""Caller-authorized close-pack header and verified, audited download (API-R-42)."""

from __future__ import annotations

from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import evidence_pack
from erev_api.domain.reports import evidence_sources, evidence_storage
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackOut
from erev_api.uow import UnitOfWork


def _permissions(uow: UnitOfWork, pack_id: UUID, required: frozenset[str]) -> None:
    for permission in sorted(required - uow.principal.permissions):
        audit_writer.record_denied(
            uow.ctx,
            action=permission,
            object_type="evidence_pack",
            object_id=pack_id,
            permission=permission,
            contract_ids=[],
            keyring=uow.keyring,
        )
        raise Problem("forbidden")


def get_close(uow: UnitOfWork, pack_id: UUID) -> ClosePackOut:
    _permissions(uow, pack_id, frozenset({"report.run", "audit.read", "contract.read"}))
    bound = evidence_sources.load_close(uow, pack_id)
    require_for_entity(uow.ctx, "contract.read", bound.entity_id)
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
            )
        )
        .mappings()
        .one()
    )
    succeeded = row["status"] == "SUCCEEDED"
    if succeeded and (
        row["manifest"] is None
        or row["file_id"] is None
        or sha256_hex(row["manifest"]) != row["manifest_sha256"]
    ):
        raise Problem("validation-failed", "The retained evidence manifest is inconsistent.")
    return ClosePackOut(
        id=pack_id,
        pack_no=row["pack_no"],
        kind="CLOSE",
        status=row["status"],
        entity_id=bound.entity_id,
        book=bound.request.book,
        period_id=bound.period_id,
        period_lock_id=bound.request.period_lock_id,
        job_id=row["job_id"],
        report_run_ids=row["report_run_ids"],
        manifest=row["manifest"] if succeeded else None,
        manifest_sha256=row["manifest_sha256"] if succeeded else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        download_href=f"/api/v1/evidence-packs/{pack_id}/download" if succeeded else None,
    )


def download_close(uow: UnitOfWork, pack_id: UUID) -> tuple[str, bytes]:
    _permissions(
        uow,
        pack_id,
        frozenset(
            {"report.run", "report.export", "evidence.export", "audit.read", "contract.read"}
        ),
    )
    header = get_close(uow, pack_id)
    retained = evidence_storage.read_close(uow, pack_id)
    uow.audit(
        action="evidence.export",
        object_type="evidence_pack",
        object_id=pack_id,
        contract_ids=[],
        detail={
            "file_id": str(retained.file_id),
            "manifest_sha256": retained.archive.manifest_sha256,
            "bytes": len(retained.archive.content),
        },
    )
    return f"{header.pack_no}.zip", retained.archive.content
