"""Recorded release provenance for CHANGE packs; no host files or remote URLs are read.

The registry retains the manifest facts admitted at process startup, not the original
build-manifest bytes. Preserve that distinction and never turn missing gates into passes.
Capture once with the request; later collection serializes the immutable source binding.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Literal, Self
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator
from sqlalchemy import select

from erev_api.db.tables import engine_release
from erev_api.domain.reports import framework
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ChangePackCreateIn
from erev_api.uow import UnitOfWork


class ReleaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    engine_version: str
    build_sha: str
    schema_revision: str
    deployed_at: AwareDatetime
    validation_level: str
    control_impact_tags: tuple[str, ...]
    gate_results: dict[str, Any]


class ReleaseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["erev.registered-release-evidence.v1"] = "erev.registered-release-evidence.v1"
    from_date: date
    to_date: date
    known_at: AwareDatetime
    requesting_release: ReleaseRecord
    registered_in_range: tuple[ReleaseRecord, ...]

    @model_validator(mode="after")
    def valid_population(self) -> Self:
        if (
            self.to_date < self.from_date
            or self.to_date > self.known_at.astimezone(UTC).date()
            or self.requesting_release.deployed_at > self.known_at
            or len({row.id for row in self.registered_in_range}) != len(self.registered_in_range)
            or any(
                row.deployed_at > self.known_at
                or not self.from_date <= row.deployed_at.astimezone(UTC).date() <= self.to_date
                or (row.id == self.requesting_release.id and row != self.requesting_release)
                for row in self.registered_in_range
            )
        ):
            raise ValueError("Release evidence differs from its date/cutoff population.")
        return self


def capture(uow: UnitOfWork, request: ChangePackCreateIn) -> ReleaseEvidence:
    if "audit.read" not in uow.principal.permissions:
        raise Problem("forbidden")
    columns = [engine_release.c[name] for name in ReleaseRecord.model_fields]
    requesting_release_id = framework._release_id(uow.session)
    requesting_release = (
        uow.session.execute(select(*columns).where(engine_release.c.id == requesting_release_id))
        .mappings()
        .one_or_none()
    )
    if requesting_release is None:
        raise Problem(
            "validation-failed", "The requesting process release has no retained registration."
        )
    # This is the shared platform registry, exactly as exposed by the audit-only release API.
    # Preserve only registry manifest fields; free-form release notes are not evidence inputs.
    rows = (
        uow.session.execute(
            select(*columns)
            .where(
                engine_release.c.deployed_at
                >= datetime.combine(request.from_date, time.min, tzinfo=UTC),
                engine_release.c.deployed_at
                <= datetime.combine(request.to_date, time.max, tzinfo=UTC),
                engine_release.c.deployed_at <= uow.now,
            )
            .order_by(engine_release.c.deployed_at, engine_release.c.id)
            .limit(10001)
        )
        .mappings()
        .all()
    )
    if len(rows) > 10000:
        raise Problem(
            "validation-failed",
            "Release evidence exceeds 10,000 registrations; narrow the date range.",
        )
    try:
        return ReleaseEvidence(
            from_date=request.from_date,
            to_date=request.to_date,
            known_at=uow.now,
            requesting_release=ReleaseRecord.model_validate(dict(requesting_release)),
            registered_in_range=tuple(ReleaseRecord.model_validate(dict(row)) for row in rows),
        )
    except ValueError as error:
        raise Problem(
            "validation-failed", "The release registry cannot establish this evidence cutoff."
        ) from error


def files(source: ReleaseEvidence) -> tuple[PackFile, ...]:
    return (
        PackFile(
            "release/registered_manifest.json",
            canonical_bytes(
                {
                    "basis": (
                        "Manifest facts retained in the release registry; "
                        "not original build-manifest bytes."
                    ),
                    "gate_basis": (
                        "Recorded gate declarations only; absent gates are not passes "
                        "or independent sign-off."
                    ),
                    "source": source.model_dump(mode="json"),
                }
            ),
        ),
    )
