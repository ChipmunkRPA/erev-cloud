"""Encrypted, immutable access-review capture and source-file deletion holds.

The legacy-named evidence_sample_file table is a tenant-scoped pack/file dependency
registry with no kind constraint. ACCESS uses it with tenant-wide scope, preserving
the existing internal-file access policy and permanent evidence retention.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from erev_engine.canonical import canonical_bytes
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import insert, select

from erev_api.db.tables import access_review_campaign, evidence_pack, evidence_sample_file
from erev_api.domain.platform import file_access
from erev_api.domain.reports import evidence_access_reviews, evidence_archive
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.enums import FilePurpose
from erev_api.files.store import lock_readable, open_file, store_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SnapshotFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    campaign_id: UUID
    file_id: UUID


class ReviewScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: UUID
    as_of: AwareDatetime
    known_at: AwareDatetime
    campaign_ids: tuple[UUID, ...]
    original_files: tuple[SnapshotFile, ...]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.as_of > self.known_at
            or len(set(self.campaign_ids)) != len(self.campaign_ids)
            or len({item.file_id for item in self.original_files}) != len(self.original_files)
            or len({item.campaign_id for item in self.original_files}) != len(self.original_files)
            or any(item.campaign_id not in self.campaign_ids for item in self.original_files)
        ):
            raise ValueError("Access-review source identities are inconsistent.")
        return self


class ReviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["erev.access-review-snapshot.v1"] = "erev.access-review-snapshot.v1"
    scope: ReviewScope
    file_id: UUID
    sha256: Sha256
    size_bytes: Annotated[int, Field(gt=0, le=512 * 1024 * 1024)]
    manifest_sha256: Sha256

    def dependency_ids(self) -> frozenset[UUID]:
        return frozenset({self.file_id, *(item.file_id for item in self.scope.original_files)})


def authorize(uow: UnitOfWork, scope: ReviewScope) -> None:
    evidence_access_reviews.authorize(uow)
    if scope.tenant_id != uow.principal.tenant_id:
        raise Problem("not-found")
    rows = dict(
        uow.session.execute(
            select(
                access_review_campaign.c.id,
                access_review_campaign.c.snapshot_file_id,
            ).where(
                access_review_campaign.c.tenant_id == scope.tenant_id,
                access_review_campaign.c.id.in_(scope.campaign_ids),
            )
        )
        .tuples()
        .all()
    )
    if set(rows) != set(scope.campaign_ids):
        raise Problem("not-found")
    for original in scope.original_files:
        if (
            rows[original.campaign_id] != original.file_id
            or file_access.bound(uow.session, uow.ctx, original.file_id) is None
        ):
            raise Problem("not-found")
    originals = frozenset(item.file_id for item in scope.original_files)
    if lock_readable(uow.session, originals) != originals:
        raise Problem("validation-failed", "Retained access-review sources are unavailable.")


def capture(uow: UnitOfWork, *, as_of: AwareDatetime) -> ReviewSnapshot:
    captured = evidence_access_reviews.collect(uow, as_of=as_of)
    pairs = uow.session.execute(
        select(
            access_review_campaign.c.id,
            access_review_campaign.c.snapshot_file_id,
        )
        .where(
            access_review_campaign.c.tenant_id == uow.principal.tenant_id,
            access_review_campaign.c.id.in_(captured.campaign_ids),
            access_review_campaign.c.snapshot_file_id.in_(captured.source_file_ids),
        )
        .order_by(access_review_campaign.c.id)
    ).all()
    scope = ReviewScope(
        tenant_id=uow.principal.tenant_id,
        as_of=as_of,
        known_at=uow.now,
        campaign_ids=captured.campaign_ids,
        original_files=tuple(
            SnapshotFile(campaign_id=identity, file_id=file_id) for identity, file_id in pairs
        ),
    )
    if {item.file_id for item in scope.original_files} != set(captured.source_file_ids):
        raise Problem(
            "validation-failed", "Access-review source population changed during capture."
        )
    authorize(uow, scope)
    try:
        archive = evidence_archive.build(
            (
                *captured.files,
                PackFile(
                    "access/reviews/scope.json",
                    canonical_bytes(scope.model_dump(mode="json")),
                ),
            )
        )
    except evidence_archive.InvalidArchive as error:
        raise Problem(
            "validation-failed", f"Access-review sources cannot be archived: {error}"
        ) from error
    if len(archive.content) > 512 * 1024 * 1024:
        raise Problem(
            "validation-failed", "Access-review snapshot exceeds the retained size limit."
        )
    stored = store_file(
        uow,
        purpose=FilePurpose.SNAPSHOT_DATASET,
        stream=io.BytesIO(archive.content),
        original_filename="access-review-sources.zip",
        media_type="application/zip",
    )
    digest = hashlib.sha256(archive.content).hexdigest()
    if stored["sha256"] != digest or stored["size_bytes"] != len(archive.content):
        raise Problem(
            "validation-failed", "Stored access-review metadata differs from captured bytes."
        )
    return ReviewSnapshot(
        scope=scope,
        file_id=stored["id"],
        sha256=digest,
        size_bytes=len(archive.content),
        manifest_sha256=archive.manifest_sha256,
    )


def retain(uow: UnitOfWork, pack_id: UUID, bound: ReviewSnapshot) -> None:
    authorize(uow, bound.scope)
    saved = uow.session.scalar(
        select(evidence_pack.c.source_binding).where(
            evidence_pack.c.tenant_id == bound.scope.tenant_id,
            evidence_pack.c.id == pack_id,
            evidence_pack.c.kind == "ACCESS",
        )
    )
    if not isinstance(saved, dict) or saved.get("access_reviews") != bound.model_dump(mode="json"):
        raise Problem(
            "validation-failed", "The ACCESS pack differs from its retained review snapshot."
        )
    ids = bound.dependency_ids()
    if lock_readable(uow.session, ids) != ids:
        raise Problem("validation-failed", "Access-review dependencies are unavailable.")
    uow.session.execute(
        insert(evidence_sample_file),
        [
            dict(
                tenant_id=bound.scope.tenant_id,
                id=uuid4(),
                evidence_pack_id=pack_id,
                file_id=identity,
                entity_ids=None,
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
            )
            for identity in sorted(ids)
        ],
    )


def verify_links(uow: UnitOfWork, pack_id: UUID, bound: ReviewSnapshot) -> None:
    authorize(uow, bound.scope)
    links = uow.session.execute(
        select(
            evidence_sample_file.c.file_id,
            evidence_sample_file.c.entity_ids,
        ).where(
            evidence_sample_file.c.tenant_id == bound.scope.tenant_id,
            evidence_sample_file.c.evidence_pack_id == pack_id,
        )
    ).all()
    if {row.file_id for row in links} != bound.dependency_ids() or any(
        row.entity_ids is not None for row in links
    ):
        raise Problem("validation-failed", "Access-review dependency retention is incomplete.")


def files(uow: UnitOfWork, bound: ReviewSnapshot) -> tuple[PackFile, ...]:
    authorize(uow, bound.scope)
    metadata, stream = open_file(uow.session, bound.file_id, files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read(bound.size_bytes + 1)
    if (
        metadata["tenant_id"] != bound.scope.tenant_id
        or metadata["purpose"] != FilePurpose.SNAPSHOT_DATASET
        or metadata["media_type"] != "application/zip"
        or len(content) != bound.size_bytes
        or metadata["size_bytes"] != bound.size_bytes
        or metadata["sha256"] != bound.sha256
        or hashlib.sha256(content).hexdigest() != bound.sha256
    ):
        raise Problem("validation-failed", "Retained access-review bytes failed verification.")
    try:
        manifest = evidence_archive.verify(content, expected_manifest_sha256=bound.manifest_sha256)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if archive.read("access/reviews/scope.json") != canonical_bytes(
                bound.scope.model_dump(mode="json")
            ):
                raise ValueError("scope")
            result = tuple(
                PackFile(entry["path"], archive.read(entry["path"])) for entry in manifest["files"]
            )
            return (
                *result,
                PackFile("access/reviews/source_manifest.json", archive.read("manifest.json")),
            )
    except (ValueError, KeyError, zipfile.BadZipFile) as error:
        raise Problem(
            "validation-failed", "The retained access-review archive is inconsistent."
        ) from error
