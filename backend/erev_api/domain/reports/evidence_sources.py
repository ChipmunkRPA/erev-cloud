"""Durable CLOSE source selection for pack creation and retries (RPS-16).

Prepare once in the transaction that inserts the pack; persist pack_values() with
its normal identity/stamps/job. Retry readers load that immutable binding instead
of selecting newer runs or digests. This is not the pack command, job or API.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import evidence_pack, report_run
from erev_api.domain.reports import evidence_audit, evidence_close, evidence_report_plan
from erev_api.domain.reports.evidence_reports import PATHS, ReportSource
from erev_api.domain.reports.evidence_selection import SOURCE_PERMISSIONS, resolve
from erev_api.enums import JobKind
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import ClosePackCreateIn
from erev_api.uow import UnitOfWork

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BoundReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    report_code: str
    parameters_sha256: Sha256
    entity_ids: tuple[UUID, ...]
    book_code: str | None
    as_of_date: date | None
    known_at: AwareDatetime
    job_id: UUID

    def source(self) -> ReportSource:
        return ReportSource(**self.model_dump(exclude={"job_id"}))


class _CloseSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: UUID
    request: ClosePackCreateIn
    requested_at: AwareDatetime
    entity_id: UUID
    period_id: UUID
    cutoff_known_at: AwareDatetime
    snapshot_manifest_sha256: Sha256
    frozen_report_run_ids: tuple[UUID, ...]
    supporting_reports: tuple[BoundReport, ...]

    @model_validator(mode="after")
    def complete_sources(self) -> Self:
        reports = self.supporting_reports
        if (
            self.cutoff_known_at > self.requested_at
            or len(reports) != len(PATHS)
            or {report.report_code for report in reports} != set(PATHS)
            or len({report.run_id for report in reports}) != len(reports)
            or len({report.job_id for report in reports}) != len(reports)
            or len(set(self.frozen_report_run_ids)) != len(self.frozen_report_run_ids)
            or set(self.frozen_report_run_ids) & {report.run_id for report in reports}
            or any(
                report.entity_ids != (self.entity_id,) or report.known_at != self.cutoff_known_at
                for report in reports
            )
        ):
            raise ValueError("The CLOSE binding has incomplete or inconsistent sources.")
        return self

    def pack_values(self) -> dict[str, Any]:
        """Selectors and source evidence for a new row; caller supplies identity, job and stamps."""
        return {
            "kind": "CLOSE",
            "entity_id": self.entity_id,
            "book_code": self.request.book.value,
            "period_id": self.period_id,
            "period_lock_id": self.request.period_lock_id,
            "contract_ids": [],
            "as_of_date": None,
            "from_date": None,
            "to_date": None,
            "report_run_ids": sorted(
                {
                    *self.frozen_report_run_ids,
                    *(report.run_id for report in self.supporting_reports),
                }
            ),
            "source_binding": self.model_dump(mode="json"),
        }


class CloseSources(_CloseSources):
    """Original binding: its completed verification ID and serialization stay unchanged."""

    format: Literal["erev.close-evidence.sources.v1"]
    audit_verification_id: UUID


class QueuedCloseSources(_CloseSources):
    """A dedicated verification job; the exact result is resolved only after success."""

    format: Literal["erev.close-evidence.sources.v2"]
    audit_verification_job_id: UUID
    pack_id: UUID

    @model_validator(mode="after")
    def distinct_audit_job(self) -> Self:
        if self.audit_verification_job_id in {item.job_id for item in self.supporting_reports}:
            raise ValueError("The audit verification must have its own job.")
        return self


type CloseBinding = CloseSources | QueuedCloseSources
_BINDING: TypeAdapter[CloseBinding] = TypeAdapter(
    Annotated[CloseBinding, Field(discriminator="format")]
)


def _prepared(uow: UnitOfWork, request: ClosePackCreateIn) -> dict[str, Any]:
    selection = resolve(uow, request)
    frozen = evidence_close.read_locked(uow, selection)
    queued = evidence_report_plan.queue(uow, selection)
    return dict(
        tenant_id=selection.tenant_id,
        request=request,
        requested_at=selection.known_at,
        entity_id=frozen.scope.entity_id,
        period_id=frozen.scope.period_id,
        cutoff_known_at=frozen.record["cutoff_known_at"],
        snapshot_manifest_sha256=frozen.record["snapshot_manifest_sha256"],
        frozen_report_run_ids=tuple(
            sorted(
                {
                    report.report_run_id
                    for report in frozen.reports
                    if report.report_run_id is not None
                }
            )
        ),
        supporting_reports=tuple(
            BoundReport(**asdict(item.source), job_id=item.job_id) for item in queued
        ),
    )


def prepare_close(
    uow: UnitOfWork, request: ClosePackCreateIn, *, verification_id: UUID
) -> CloseSources:
    """Retain the original explicit-completed-verification path for v1 callers."""
    evidence_audit.collect(uow, resolve(uow, request), verification_id=verification_id)
    return CloseSources(
        **_prepared(uow, request),
        format="erev.close-evidence.sources.v1",
        audit_verification_id=verification_id,
    )


def prepare_queued_close(
    uow: UnitOfWork, request: ClosePackCreateIn, *, pack_id: UUID
) -> QueuedCloseSources:
    """Queue a fresh verification and five reports atomically with the caller's pack."""
    # Never reuse a pending tenant verification: it may have read a prefix before this lock.
    verification_job = uow.defer(
        JobKind.AUDIT_CHAIN_VERIFY,
        {"trigger": "ON_DEMAND", "period_lock_id": str(request.period_lock_id)},
        subject_type="evidence_pack",
        subject_id=pack_id,
    )
    return QueuedCloseSources(
        **_prepared(uow, request),
        format="erev.close-evidence.sources.v2",
        audit_verification_job_id=verification_job["id"],
        pack_id=pack_id,
    )


def checked_row(row: Mapping[str, Any]) -> CloseBinding:
    try:
        bound = _BINDING.validate_python(row["source_binding"])
    except (KeyError, ValidationError) as error:
        raise Problem(
            "validation-failed", "This pack has no valid retained CLOSE sources."
        ) from error
    if isinstance(bound, QueuedCloseSources) and row.get("id") != bound.pack_id:
        raise Problem("validation-failed", "The queued sources belong to a different pack.")
    expected = bound.pack_values()
    if (
        row["tenant_id"] != bound.tenant_id
        or row["created_at"] != bound.requested_at
        or any(
            row[key] != value
            for key, value in expected.items()
            if key not in {"source_binding", "report_run_ids"}
        )
        or len(row["report_run_ids"]) != len(expected["report_run_ids"])
        or set(row["report_run_ids"]) != set(expected["report_run_ids"])
    ):
        raise Problem("validation-failed", "The pack record differs from its retained sources.")
    return bound


def load_close(uow: UnitOfWork, pack_id: UUID) -> CloseBinding:
    """Read exact saved sources under current caller scope; never enqueue or select latest."""
    if any(permission not in uow.principal.permissions for permission in SOURCE_PERMISSIONS):
        raise Problem("forbidden")
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
                evidence_pack.c.kind == "CLOSE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    for permission in SOURCE_PERMISSIONS:
        require_for_entity(uow.ctx, permission, row["entity_id"])
    bound = checked_row(dict(row))
    selected = resolve(uow, bound.request)
    frozen = evidence_close.read_locked(uow, selected)
    if (
        frozen.scope.entity_id != bound.entity_id
        or frozen.scope.period_id != bound.period_id
        or frozen.record["cutoff_known_at"] != bound.cutoff_known_at
        or frozen.record["snapshot_manifest_sha256"] != bound.snapshot_manifest_sha256
        or {report.report_run_id for report in frozen.reports if report.report_run_id is not None}
        != set(bound.frozen_report_run_ids)
    ):
        raise Problem("validation-failed", "The frozen close differs from its retained sources.")
    # Job/run association is fixed at creation and needed by retry orchestration. Success,
    # selectors, file hashes and export permission are verified by evidence_reports.collect.
    jobs = {
        run_id: job_id
        for run_id, job_id in uow.session.execute(
            select(report_run.c.id, report_run.c.job_id).where(
                report_run.c.tenant_id == bound.tenant_id,
                report_run.c.id.in_([report.run_id for report in bound.supporting_reports]),
            )
        ).all()
    }
    if jobs != {report.run_id: report.job_id for report in bound.supporting_reports}:
        raise Problem("validation-failed", "A retained supporting report has no matching job.")
    return bound
