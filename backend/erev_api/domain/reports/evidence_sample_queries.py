"""Current-source authorization for sample metadata and audited retained downloads."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Select, false, select

from erev_api.auth.principal import Principal
from erev_api.db.tables import evidence_pack
from erev_api.domain.reports import (
    evidence_queries,
    evidence_sample_sources,
    evidence_sample_storage,
)
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ContractSamplePackOut, ContractSamplePackSummaryOut
from erev_api.uow import UnitOfWork


def get(uow: UnitOfWork, pack_id: UUID) -> ContractSamplePackOut:
    evidence_queries.require_permissions(uow, pack_id, PERMISSIONS)
    evidence_sample_sources.load(uow, pack_id)
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
    header = summary(dict(row))
    return ContractSamplePackOut(
        **header.model_dump(),
        manifest=evidence_queries._retained_manifest(row),
        download_href=f"/api/v1/evidence-packs/{pack_id}/download"
        if header.status == "SUCCEEDED"
        else None,
    )


def summary(row: Mapping[str, Any]) -> ContractSamplePackSummaryOut:
    """Metadata only, after the list predicate has authorized the complete binding."""
    bound = evidence_sample_sources.SampleSources.model_validate(row["source_binding"])
    pack_id = row["id"]
    manifest = evidence_queries._retained_manifest(row)
    return ContractSamplePackSummaryOut(
        id=pack_id,
        pack_no=row["pack_no"],
        kind="CONTRACT_SAMPLE",
        status=row["status"],
        contract_ids=list(bound.scope.sampled_contract_ids),
        contract_external_ids=bound.scope.request.contract_external_ids,
        source_entity_ids=list(bound.scope.source_entity_ids),
        all_entities=bound.scope.all_entities,
        as_of=bound.scope.request.as_of,
        known_at=bound.scope.known_at,
        job_id=row["job_id"],
        file_count=None if manifest is None else len(manifest.files),
        manifest_sha256=row["manifest_sha256"] if manifest is not None else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def download(uow: UnitOfWork, pack_id: UUID, *, manifest_only: bool = False) -> tuple[str, bytes]:
    header = get(uow, pack_id)
    retained = evidence_sample_storage.read(uow, pack_id)
    content = retained.archive.manifest_bytes if manifest_only else retained.archive.content
    uow.audit(
        action="evidence.export",
        object_type="evidence_pack",
        object_id=pack_id,
        contract_ids=header.contract_ids,
        detail={
            "file_id": str(retained.file_id),
            "manifest_sha256": retained.archive.manifest_sha256,
            "bytes": len(content),
            "artifact": "manifest" if manifest_only else "archive",
        },
    )
    return header.pack_no + (".manifest.json" if manifest_only else ".zip"), content


def is_sample(uow: UnitOfWork, pack_id: UUID) -> bool:
    return (
        uow.session.execute(
            select(evidence_pack.c.kind).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
            )
        ).scalar_one_or_none()
        == "CONTRACT_SAMPLE"
    )


def list_statement(principal: Principal) -> Select[Any]:
    """Coarse SQL scope filter; composite document permissions still require visible()."""
    scope = evidence_pack.c.source_binding["scope"]
    statement = select(evidence_pack).where(
        evidence_pack.c.tenant_id == principal.tenant_id,
        evidence_pack.c.kind == "CONTRACT_SAMPLE",
        evidence_pack.c.source_binding["render_stamp"].astext.is_not(None),
    )
    if not PERMISSIONS <= principal.permissions:
        return statement.where(false())
    scopes = [
        principal.permission_scopes.get(permission, frozenset()) for permission in PERMISSIONS
    ]
    scopes.append("*" if principal.entity_scope == "*" else frozenset(principal.entity_scope))
    for allowed in scopes:
        if allowed != "*":
            statement = statement.where(
                scope["all_entities"].as_boolean().is_(False),
                scope["source_entity_ids"].contained_by(
                    [str(entity) for entity in sorted(allowed)]
                ),
            )
    return statement


def visible(uow: UnitOfWork, pack_id: UUID) -> bool:
    try:
        evidence_sample_sources.load(uow, pack_id, lock_documents=False)
    except Problem as error:
        if error.status in {403, 404}:
            return False
        raise
    return True
