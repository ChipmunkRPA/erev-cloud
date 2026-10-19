"""Capture and retain one contract sample source snapshot for subsequent rendering.

The caller must persist pack_values() and call retain() in the same transaction. Retries
load the immutable binding; they never recollect live facts. No public command, job
completion or final PDF/XLSX publication is implemented by this module.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid4

from erev_engine.canonical import canonical_bytes
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import insert, select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import contract, evidence_pack, evidence_sample_file
from erev_api.domain.platform import file_access
from erev_api.domain.reports import (
    evidence_archive,
    evidence_sample_computations,
    evidence_sample_decisions,
    evidence_sample_documents,
    evidence_sample_events,
    evidence_sample_journals,
)
from erev_api.domain.reports.evidence_archive import Archive, PackFile
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.outputs import RunStamp
from erev_api.enums import FilePurpose
from erev_api.files.store import lock_readable, open_file, store_file
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ContractSamplePackCreateIn
from erev_api.uow import UnitOfWork

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DocumentGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject_type: str
    subject_id: UUID
    file_id: UUID


class SampleScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: UUID
    request: ContractSamplePackCreateIn
    known_at: AwareDatetime
    sampled_contract_ids: tuple[UUID, ...]
    source_contract_ids: tuple[UUID, ...]
    source_entity_ids: tuple[UUID, ...]
    all_entities: bool
    version_ids: tuple[UUID, ...]
    event_ids: tuple[UUID, ...]
    approval_request_ids: tuple[UUID, ...]
    document_grants: tuple[DocumentGrant, ...]

    @model_validator(mode="after")
    def complete_scope(self) -> Self:
        if (
            not self.source_entity_ids
            or not self.sampled_contract_ids
            or len(self.sampled_contract_ids) != len(self.request.contract_external_ids)
            or not set(self.sampled_contract_ids) <= set(self.source_contract_ids)
            or self.request.as_of > self.known_at.date()
        ):
            raise ValueError("Incomplete sample source scope")
        for values in (
            self.sampled_contract_ids,
            self.source_contract_ids,
            self.source_entity_ids,
            self.version_ids,
            self.event_ids,
            self.approval_request_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate sample source identity")
        return self


class SampleSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["erev.contract-sample.sources.v1"] = "erev.contract-sample.sources.v1"
    scope: SampleScope
    source_file_id: UUID
    source_file_sha256: Sha256
    source_file_bytes: Annotated[int, Field(gt=0, le=512 * 1024 * 1024)]
    manifest_sha256: Sha256
    render_stamp: RunStamp | None = None

    def pack_values(self) -> dict[str, Any]:
        return {
            "kind": "CONTRACT_SAMPLE",
            "entity_id": None,
            "book_code": None,
            "period_id": None,
            "period_lock_id": None,
            "from_date": None,
            "to_date": None,
            "contract_ids": list(self.scope.sampled_contract_ids),
            "as_of_date": self.scope.request.as_of,
            "report_run_ids": [],
            "source_binding": self.model_dump(mode="json"),
        }


def authorize(uow: UnitOfWork, scope: SampleScope) -> None:
    if scope.tenant_id != uow.principal.tenant_id or not PERMISSIONS <= uow.principal.permissions:
        raise Problem("forbidden")
    for permission in PERMISSIONS:
        if scope.all_entities and uow.principal.permission_scopes.get(permission) != "*":
            raise Problem("not-found")
        for entity in scope.source_entity_ids:
            require_for_entity(uow.ctx, permission, entity)
    if uow.principal.entity_scope != "*" and (
        scope.all_entities or not set(scope.source_entity_ids) <= set(uow.principal.entity_scope)
    ):
        raise Problem("not-found")
    contracts = uow.session.execute(
        select(contract.c.id, contract.c.contracting_entity_id).where(
            contract.c.tenant_id == scope.tenant_id,
            contract.c.id.in_(scope.source_contract_ids),
        )
    ).all()
    if {row.id for row in contracts} != set(scope.source_contract_ids) or not {
        row.contracting_entity_id for row in contracts
    } <= set(scope.source_entity_ids):
        raise Problem("not-found")
    for grant in scope.document_grants:
        subject = file_access.ATTACHMENT_SUBJECTS.get(grant.subject_type)
        if (
            subject is None
            or not subject.readable(uow.session, uow.ctx, grant.subject_id)
            or file_access.bound(uow.session, uow.ctx, grant.file_id) is None
        ):
            raise Problem("not-found")
    files = frozenset(grant.file_id for grant in scope.document_grants)
    if lock_readable(uow.session, files) != files:
        raise Problem(
            "validation-failed", "Retained sample source documents are no longer available."
        )


def prepare(uow: UnitOfWork, request: ContractSamplePackCreateIn) -> SampleSources:
    events = evidence_sample_events.collect(uow, request)
    computations = evidence_sample_computations.collect(uow, events.selection, as_of=request.as_of)
    journals = evidence_sample_journals.collect(uow, events.selection, as_of=request.as_of)
    expanded = replace(
        events.selection,
        contract_ids=tuple(sorted(set(computations.contract_ids) | set(journals.contract_ids))),
        entity_ids=tuple(sorted(set(computations.entity_ids) | set(journals.entity_ids))),
    )
    decisions = evidence_sample_decisions.collect(
        uow,
        expanded,
        approval_request_ids=tuple(
            sorted(
                set(events.approval_request_ids)
                | set(computations.approval_request_ids)
                | set(journals.approval_request_ids)
            )
        ),
    )
    documents = evidence_sample_documents.collect(
        uow,
        expanded,
        as_of=request.as_of,
        event_ids=events.event_ids,
        approval_request_ids=decisions.approval_request_ids,
    )
    document_index = json.loads(
        next(file.content for file in documents.files if file.path == "sample/documents.json")
    )
    scope = SampleScope(
        tenant_id=events.selection.tenant_id,
        request=request,
        known_at=events.selection.known_at,
        sampled_contract_ids=events.selection.contract_ids,
        source_contract_ids=decisions.contract_ids,
        source_entity_ids=decisions.entity_ids,
        all_entities=decisions.all_entities,
        version_ids=computations.version_ids,
        event_ids=events.event_ids,
        approval_request_ids=decisions.approval_request_ids,
        document_grants=tuple(
            DocumentGrant(
                subject_type=row["subject_type"],
                subject_id=row["subject_id"],
                file_id=row["file_id"],
            )
            for row in document_index["attachments"]
        ),
    )
    authorize(uow, scope)
    archive = evidence_archive.build(
        (
            *events.files,
            *computations.files,
            *journals.files,
            *decisions.files,
            *documents.files,
            PackFile("sample/scope.json", canonical_bytes(scope.model_dump(mode="json"))),
        )
    )
    stored = store_file(
        uow,
        purpose=FilePurpose.SNAPSHOT_DATASET,
        stream=io.BytesIO(archive.content),
        original_filename="contract-sample-sources.zip",
        media_type="application/zip",
    )
    digest = hashlib.sha256(archive.content).hexdigest()
    if stored["sha256"] != digest or stored["size_bytes"] != len(archive.content):
        raise Problem(
            "validation-failed", "Stored sample source metadata differs from captured bytes."
        )
    return SampleSources(
        scope=scope,
        source_file_id=stored["id"],
        source_file_sha256=digest,
        source_file_bytes=len(archive.content),
        manifest_sha256=archive.manifest_sha256,
    )


def read(uow: UnitOfWork, bound: SampleSources) -> Archive:
    """Reauthorize the retained population, then verify stored bytes without live recollection."""
    authorize(uow, bound.scope)
    metadata, stream = open_file(
        uow.session, bound.source_file_id, files=uow.files, keyring=uow.keyring
    )
    with stream:
        content = stream.read(bound.source_file_bytes + 1)
    if (
        metadata["tenant_id"] != bound.scope.tenant_id
        or metadata["purpose"] != FilePurpose.SNAPSHOT_DATASET
        or metadata["media_type"] != "application/zip"
        or len(content) != bound.source_file_bytes
        or metadata["size_bytes"] != len(content)
        or metadata["sha256"] != bound.source_file_sha256
        or hashlib.sha256(content).hexdigest() != bound.source_file_sha256
    ):
        raise Problem(
            "validation-failed", "The retained sample source archive failed verification."
        )
    try:
        evidence_archive.verify(content, expected_manifest_sha256=bound.manifest_sha256)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            scope_bytes = archive.read("sample/scope.json")
            manifest = archive.read("manifest.json")
        if scope_bytes != canonical_bytes(bound.scope.model_dump(mode="json")):
            raise ValueError("scope")
    except (evidence_archive.InvalidArchive, KeyError, ValueError, zipfile.BadZipFile) as error:
        raise Problem(
            "validation-failed", "The retained sample source binding is invalid."
        ) from error
    return Archive(content, manifest, bound.manifest_sha256)


def retain(uow: UnitOfWork, pack_id: UUID, bound: SampleSources) -> None:
    """Bind deletion holds in the pack creation transaction, without granting file access."""
    authorize(uow, bound.scope)
    row = uow.session.execute(
        select(evidence_pack.c.source_binding).where(
            evidence_pack.c.tenant_id == uow.principal.tenant_id,
            evidence_pack.c.id == pack_id,
            evidence_pack.c.kind == "CONTRACT_SAMPLE",
        )
    ).scalar_one_or_none()
    if row != bound.model_dump(mode="json"):
        raise Problem("validation-failed", "Sample dependency binding differs from its pack.")
    files = frozenset({bound.source_file_id, *(g.file_id for g in bound.scope.document_grants)})
    if lock_readable(uow.session, files) != files:
        raise Problem("validation-failed", "Sample dependency files are no longer available.")
    uow.session.execute(
        insert(evidence_sample_file),
        [
            dict(
                tenant_id=uow.principal.tenant_id,
                id=uuid4(),
                evidence_pack_id=pack_id,
                file_id=file_id,
                entity_ids=None
                if bound.scope.all_entities
                else list(bound.scope.source_entity_ids),
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
            )
            for file_id in sorted(files)
        ],
    )


def load(uow: UnitOfWork, pack_id: UUID) -> SampleSources:
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
                evidence_pack.c.kind == "CONTRACT_SAMPLE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    try:
        bound = SampleSources.model_validate(row["source_binding"])
        if any(
            row[key] != value
            for key, value in bound.pack_values().items()
            if key != "source_binding"
        ):
            raise ValueError("selection")
    except ValueError as error:
        raise Problem(
            "validation-failed", "The contract sample has no valid retained sources."
        ) from error
    authorize(uow, bound.scope)
    references = uow.session.execute(
        select(evidence_sample_file.c.file_id, evidence_sample_file.c.entity_ids).where(
            evidence_sample_file.c.tenant_id == uow.principal.tenant_id,
            evidence_sample_file.c.evidence_pack_id == pack_id,
        )
    ).all()
    expected = {bound.source_file_id, *(g.file_id for g in bound.scope.document_grants)}
    entities = None if bound.scope.all_entities else list(bound.scope.source_entity_ids)
    if {row.file_id for row in references} != expected or any(
        row.entity_ids != entities for row in references
    ):
        raise Problem("validation-failed", "The sample dependency retention is incomplete.")
    return bound
