"""Caller-authorized close-pack header and verified, audited download (API-R-42)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, false, select

from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import Principal
from erev_api.db.tables import evidence_pack, legal_entity, period
from erev_api.domain.reports import evidence_sources, evidence_storage
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackOut, ClosePackSummaryOut
from erev_api.uow import UnitOfWork

READ_PERMISSIONS = frozenset({"report.run", "audit.read", "contract.read"})


def require_permissions(uow: UnitOfWork, pack_id: UUID | None, required: frozenset[str]) -> None:
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
    require_permissions(uow, pack_id, READ_PERMISSIONS)
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
    require_permissions(
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


def list_statement(principal: Principal) -> Select[Any]:
    """Apply every source permission's scope before pagination and counting."""
    statement = (
        select(evidence_pack)
        .join(
            legal_entity,
            (legal_entity.c.tenant_id == evidence_pack.c.tenant_id)
            & (legal_entity.c.id == evidence_pack.c.entity_id),
        )
        .join(
            period,
            (period.c.tenant_id == evidence_pack.c.tenant_id)
            & (period.c.id == evidence_pack.c.period_id),
        )
        .where(
            evidence_pack.c.tenant_id == principal.tenant_id,
            evidence_pack.c.kind == "CLOSE",
            evidence_pack.c.source_binding.is_not(None),
        )
    )
    for permission in READ_PERMISSIONS:
        scope = principal.permission_scopes.get(permission, frozenset())
        if permission not in principal.permissions:
            return statement.where(false())
        if scope != "*":
            statement = statement.where(evidence_pack.c.entity_id.in_(scope))
    return statement


def summary(row: Mapping[str, Any]) -> ClosePackSummaryOut:
    """Validate record/binding identity without opening files or asserting source integrity."""
    bound = evidence_sources.checked_row(row)
    return ClosePackSummaryOut(
        id=row["id"],
        pack_no=row["pack_no"],
        kind="CLOSE",
        status=row["status"],
        entity_id=bound.entity_id,
        book=bound.request.book,
        period_id=bound.period_id,
        period_lock_id=bound.request.period_lock_id,
        job_id=row["job_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
