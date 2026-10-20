"""Immutable source/output adapter for catalogue evidence reports (RPT-54/55).

The report lifecycle must persist this binding before dispatch. Bind an explicitly selected
pack, never the latest matching pack; subsequent reads reauthorize and use original bytes.
This adapter owns neither report/job creation nor transaction commit.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zipfile import ZipFile

from erev_engine.canonical import canonical_bytes, sha256_hex
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import evidence_pack, job
from erev_api.domain.reports import (
    evidence_archive,
    evidence_commands,
    evidence_queries,
    evidence_sample_queries,
    evidence_sample_sources,
    evidence_sources,
)
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn, ContractSamplePackCreateIn
from erev_api.uow import UnitOfWork

Request = Annotated[ClosePackCreateIn | ContractSamplePackCreateIn, Field(discriminator="kind")]


class CatalogueEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["erev.catalogue-evidence.v1"] = "erev.catalogue-evidence.v1"
    tenant_id: UUID
    pack_id: UUID
    job_id: UUID
    report_code: Literal["period_evidence_pack", "contract_sample_pack"]
    output_format: Literal["ZIP", "PDF", "XLSX"]
    request: Request
    entity_ids: tuple[UUID, ...]
    known_at: datetime
    source_binding_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def consistent(self) -> CatalogueEvidence:
        if (
            self.known_at.tzinfo is None
            or not self.entity_ids
            or len(set(self.entity_ids)) != len(self.entity_ids)
        ):
            raise ValueError("Evidence requires an aware cutoff and unique nonempty entity scope.")
        close = self.report_code == "period_evidence_pack"
        if close != isinstance(self.request, ClosePackCreateIn):
            raise ValueError("Evidence kind differs from its catalogue report.")
        if close and (self.output_format != "ZIP" or len(self.entity_ids) != 1):
            raise ValueError("Period evidence is a single-entity ZIP.")
        return self


def bind(
    uow: UnitOfWork,
    pack_id: UUID,
    *,
    request: ClosePackCreateIn | ContractSamplePackCreateIn,
    entity_ids: tuple[UUID, ...],
    known_at: datetime,
    output_format: Literal["ZIP", "PDF", "XLSX"],
) -> CatalogueEvidence:
    """Bind the requested selectors and report scope to an existing, explicit source pack."""
    evidence_queries.require_permissions(uow, pack_id, evidence_commands.PERMISSIONS)
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if row["kind"] != request.kind or row["job_id"] is None:
        raise Problem("validation-failed", "The catalogue source has a different kind or no job.")
    parent = uow.session.execute(
        select(job.c.kind, job.c.subject_type, job.c.subject_id, job.c.params).where(
            job.c.tenant_id == uow.principal.tenant_id,
            job.c.id == row["job_id"],
        )
    ).one_or_none()
    if parent is None or (
        (parent.kind, parent.subject_type, parent.subject_id)
        != ("EVIDENCE_PACK", "evidence_pack", pack_id)
        or parent.params.get("evidence_pack_id") != str(pack_id)
    ):
        raise Problem("validation-failed", "The source evidence job does not match its pack.")
    if row["status"] not in {"QUEUED", "RUNNING", "SUCCEEDED"}:
        raise Problem("invalid-transition", "The source evidence pack failed.")
    selected_request: ClosePackCreateIn | ContractSamplePackCreateIn
    source_entities: tuple[UUID, ...]
    if isinstance(request, ClosePackCreateIn):
        close = evidence_sources.load_close(uow, pack_id)
        evidence_queries.get_close(uow, pack_id)
        selected_request = close.request
        source_entities = (close.entity_id,)
        cutoff = close.cutoff_known_at
    else:
        sample = evidence_sample_sources.load(uow, pack_id)
        if sample.render_stamp is None:
            raise Problem("validation-failed", "The source sample has no rendering stamp.")
        selected_request = sample.scope.request
        source_entities = sample.scope.source_entity_ids
        cutoff = sample.scope.known_at
    if selected_request != request or known_at != cutoff or set(entity_ids) != set(source_entities):
        raise Problem("validation-failed", "Catalogue selectors differ from the retained evidence.")
    for entity_id in source_entities:
        for permission in evidence_commands.PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity_id)
    try:
        return CatalogueEvidence(
            tenant_id=uow.principal.tenant_id,
            pack_id=pack_id,
            job_id=row["job_id"],
            report_code="period_evidence_pack"
            if request.kind == "CLOSE"
            else "contract_sample_pack",
            output_format=output_format,
            request=request,
            entity_ids=entity_ids,
            known_at=known_at,
            source_binding_sha256=sha256_hex(row["source_binding"]),
        )
    except ValueError as error:
        raise Problem(
            "validation-failed", "Invalid catalogue evidence source or format."
        ) from error


def authorize(uow: UnitOfWork, bound: CatalogueEvidence) -> None:
    if bound.tenant_id != uow.principal.tenant_id:
        raise Problem("not-found")
    current = bind(
        uow,
        bound.pack_id,
        request=bound.request,
        entity_ids=bound.entity_ids,
        known_at=bound.known_at,
        output_format=bound.output_format,
    )
    if current != bound:
        raise Problem("validation-failed", "The bound catalogue evidence source has changed.")


@dataclass(frozen=True)
class EvidenceOutput:
    content: bytes
    extension: str
    media_type: str
    sha256: str
    manifest: bytes


def select_output(bound: CatalogueEvidence, content: bytes, manifest_sha256: str) -> EvidenceOutput:
    """Extract only a declared, hash-verified original artifact; never re-render a sample."""
    try:
        manifest = evidence_archive.verify(content, expected_manifest_sha256=manifest_sha256)
        path = (
            None
            if bound.output_format == "ZIP"
            else f"reports/contract_sample.{bound.output_format.lower()}"
        )
        if path is None:
            payload = content
        else:
            entry = next((item for item in manifest["files"] if item["path"] == path), None)
            if entry is None:
                raise ValueError("The selected sample artifact is missing.")
            with ZipFile(io.BytesIO(content)) as archive:
                payload = archive.read(path)
        digest = hashlib.sha256(payload).hexdigest()
        provenance = canonical_bytes(
            {
                "format": "erev.catalogue-evidence.output.v1",
                "source": bound.model_dump(mode="json"),
                "pack_manifest_sha256": manifest_sha256,
                "path": path,
                "bytes": len(payload),
                "sha256": digest,
            }
        )
    except (ValueError, KeyError) as error:
        raise Problem(
            "validation-failed", "The retained catalogue artifact failed verification."
        ) from error
    media_types = {
        "ZIP": "application/zip",
        "PDF": "application/pdf",
        "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return EvidenceOutput(
        payload, bound.output_format.lower(), media_types[bound.output_format], digest, provenance
    )


def read(uow: UnitOfWork, bound: CatalogueEvidence) -> EvidenceOutput:
    """Reauthorize all source permissions and audit the original pack export in this transaction."""
    authorize(uow, bound)
    if bound.report_code == "period_evidence_pack":
        digest = evidence_queries.get_close(uow, bound.pack_id).manifest_sha256
        _, archive = evidence_queries.download_close(uow, bound.pack_id)
    else:
        digest = evidence_sample_queries.get(uow, bound.pack_id).manifest_sha256
        _, archive = evidence_sample_queries.download(uow, bound.pack_id)
    if digest is None:
        raise Problem("invalid-transition", "The source evidence pack has not completed.")
    return select_output(bound, archive, digest)
