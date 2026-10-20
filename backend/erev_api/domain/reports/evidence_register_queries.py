"""Current-scope CHANGE/ACCESS metadata and verified, audited retained downloads."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select

from erev_api.auth.principal import Principal
from erev_api.db.tables import evidence_pack
from erev_api.domain.reports import (
    evidence_queries,
    evidence_register_sources,
    evidence_register_storage,
)
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import RegisterPackOut, RegisterPackSummaryOut
from erev_api.uow import UnitOfWork


def is_register(uow: UnitOfWork, pack_id: UUID) -> bool:
    return uow.session.scalar(
        select(evidence_pack.c.kind).where(
            evidence_pack.c.tenant_id == uow.principal.tenant_id,
            evidence_pack.c.id == pack_id,
        )
    ) in {"CHANGE", "ACCESS"}


def get(uow: UnitOfWork, pack_id: UUID) -> RegisterPackOut:
    evidence_queries.require_permissions(uow, pack_id, evidence_register_sources.PERMISSIONS)
    bound = evidence_register_sources.load(uow, pack_id)
    evidence_register_storage.complete_binding(bound)
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
    return RegisterPackOut(
        **summary(dict(row)).model_dump(),
        manifest=evidence_queries._retained_manifest(row),
        download_href=f"/api/v1/evidence-packs/{pack_id}/download"
        if row["status"] == "SUCCEEDED"
        else None,
    )


def summary(row: Mapping[str, Any]) -> RegisterPackSummaryOut:
    bound = evidence_register_sources.checked_row(row)
    manifest = evidence_queries._retained_manifest(row)
    return RegisterPackSummaryOut(
        id=row["id"],
        pack_no=row["pack_no"],
        kind=row["kind"],
        status=row["status"],
        entity_ids=list(bound.entity_ids),
        entity_codes=list(bound.entity_codes),
        as_of=row["as_of_date"],
        from_date=row["from_date"],
        to_date=row["to_date"],
        known_at=bound.known_at,
        job_id=row["job_id"],
        report_run_ids=row["report_run_ids"],
        file_count=None if manifest is None else len(manifest.files),
        manifest_sha256=row["manifest_sha256"] if manifest is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_statement(principal: Principal, kind: str) -> Select[Any]:
    return select(evidence_pack).where(
        evidence_pack.c.tenant_id == principal.tenant_id,
        evidence_pack.c.kind == kind,
        evidence_pack.c.source_binding["format"].astext.in_(
            [
                "erev.register-evidence.sources.v2",
                "erev.register-evidence.sources.v4",
            ]
        ),
    )


def visible(uow: UnitOfWork, pack_id: UUID) -> bool:
    try:
        bound = evidence_register_sources.load(uow, pack_id)
        evidence_register_storage.complete_binding(bound)
    except Problem as error:
        if error.status in {403, 404}:
            return False
        raise
    return True


def download(uow: UnitOfWork, pack_id: UUID, *, manifest_only: bool = False) -> tuple[str, bytes]:
    header = get(uow, pack_id)
    retained = evidence_register_storage.read(uow, pack_id)
    content = retained.archive.manifest_bytes if manifest_only else retained.archive.content
    uow.audit(
        action="evidence.export",
        object_type="evidence_pack",
        object_id=pack_id,
        contract_ids=[],
        detail={
            "file_id": retained.file_id,
            "manifest_sha256": retained.archive.manifest_sha256,
            "bytes": len(content),
            "artifact": "manifest" if manifest_only else "archive",
        },
    )
    return header.pack_no + (".manifest.json" if manifest_only else ".zip"), content
