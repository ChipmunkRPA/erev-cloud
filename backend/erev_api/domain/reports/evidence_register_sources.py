"""Retained report sections for CHANGE/ACCESS evidence packs.

This boundary queues and binds report sources, then collects their original CSV and IPE
manifest bytes under current authorization. It does not claim a complete pack: CHANGE
still needs release evidence; ACCESS still needs its role matrix and access-review evidence.
No parent job, pack completion or public endpoint is enabled here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, time
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import evidence_pack, legal_entity, report_run
from erev_api.domain.reports import evidence_reports, evidence_selection, framework
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_sources import BoundReport
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import AccessPackCreateIn, ChangePackCreateIn
from erev_api.schemas.reports import ReportRunCreateIn
from erev_api.uow import UnitOfWork

PERMISSIONS = frozenset({"report.run", "report.export", "audit.read", "evidence.export"})
REPORTS = {
    "CHANGE": frozenset({"config_change_register", "ssp_change_log"}),
    "ACCESS": frozenset({"user_access_listing", "sod_conflict_report"}),
}
Request = Annotated[ChangePackCreateIn | AccessPackCreateIn, Field(discriminator="kind")]


class RegisterSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["erev.register-evidence.sources.v1"] = "erev.register-evidence.sources.v1"
    tenant_id: UUID
    request: Request
    known_at: AwareDatetime
    entity_ids: tuple[UUID, ...]
    entity_codes: tuple[str, ...]
    reports: tuple[BoundReport, ...]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if (
            not self.entity_ids
            or len(set(self.entity_ids)) != len(self.entity_ids)
            or len(self.entity_ids) != len(self.entity_codes)
            or len(set(self.entity_codes)) != len(self.entity_codes)
            or len(self.reports) != len(REPORTS[self.request.kind])
            or {report.report_code for report in self.reports} != REPORTS[self.request.kind]
            or len({report.run_id for report in self.reports}) != len(self.reports)
            or len({report.job_id for report in self.reports}) != len(self.reports)
            or any(
                set(report.entity_ids) != set(self.entity_ids) or report.known_at != self.known_at
                for report in self.reports
            )
        ):
            raise ValueError("Incomplete or inconsistent register evidence sources.")
        requests(self.request, entity_codes=self.entity_codes, known_at=self.known_at)
        return self

    def pack_values(self) -> dict[str, Any]:
        return {
            "kind": self.request.kind,
            "entity_id": None,
            "book_code": None,
            "period_id": None,
            "period_lock_id": None,
            "contract_ids": [],
            "as_of_date": self.request.as_of
            if isinstance(self.request, AccessPackCreateIn)
            else None,
            "from_date": self.request.from_date
            if isinstance(self.request, ChangePackCreateIn)
            else None,
            "to_date": self.request.to_date
            if isinstance(self.request, ChangePackCreateIn)
            else None,
            "report_run_ids": sorted(report.run_id for report in self.reports),
            "source_binding": self.model_dump(mode="json"),
        }


def requests(
    request: ChangePackCreateIn | AccessPackCreateIn,
    *,
    entity_codes: tuple[str, ...],
    known_at: datetime,
) -> tuple[ReportRunCreateIn, ...]:
    """Inclusive UTC days; today's ACCESS snapshot uses the request instant."""
    if known_at.tzinfo is None or not entity_codes:
        raise Problem("validation-failed", "Register evidence requires a scoped, aware cutoff.")
    cutoff = known_at.astimezone(UTC)
    selected_date = request.to_date if isinstance(request, ChangePackCreateIn) else request.as_of
    if selected_date > cutoff.date():
        raise Problem("validation-failed", "Evidence dates cannot be in the future.")
    common: dict[str, Any] = {"entity_codes": list(entity_codes), "known_at": cutoff.isoformat()}
    if isinstance(request, ChangePackCreateIn):
        selectors = {
            "from_date": request.from_date.isoformat(),
            "to_date": request.to_date.isoformat(),
        }
    else:
        instant = min(datetime.combine(request.as_of, time.max, tzinfo=UTC), cutoff)
        selectors = {"as_of": instant.isoformat()}
    return tuple(
        ReportRunCreateIn(
            report_code=code,
            output_format="CSV",
            parameters={
                **common,
                **selectors,
                **({"include_removed": True} if code == "user_access_listing" else {}),
            },
        )
        for code in sorted(REPORTS[request.kind])
    )


def authorize(uow: UnitOfWork, entity_ids: tuple[UUID, ...]) -> None:
    if not PERMISSIONS <= uow.principal.permissions:
        raise Problem("forbidden")
    if uow.principal.entity_scope != "*" and not set(entity_ids) <= set(uow.principal.entity_scope):
        raise Problem("not-found")
    for entity_id in entity_ids:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity_id)
    found = set(
        uow.session.scalars(
            select(legal_entity.c.id).where(
                legal_entity.c.tenant_id == uow.principal.tenant_id,
                legal_entity.c.id.in_(entity_ids),
            )
        )
    )
    if found != set(entity_ids):
        raise Problem("not-found")


def prepare(uow: UnitOfWork, request: ChangePackCreateIn | AccessPackCreateIn) -> RegisterSources:
    """Caller persists the returned binding and commits all report jobs with its pack."""
    selection = evidence_selection.resolve(uow, request)
    authorize(uow, selection.entity_ids)
    codes = {
        identity: code
        for identity, code in uow.session.execute(
            select(legal_entity.c.id, legal_entity.c.code).where(
                legal_entity.c.tenant_id == selection.tenant_id,
                legal_entity.c.id.in_(selection.entity_ids),
            )
        ).all()
    }
    entity_codes = tuple(codes[identity] for identity in selection.entity_ids)
    reports = []
    for body in requests(request, entity_codes=entity_codes, known_at=selection.known_at):
        run_id, job = framework.create_run(uow, body)
        row = (
            uow.session.execute(
                select(report_run).where(
                    report_run.c.tenant_id == selection.tenant_id, report_run.c.id == run_id
                )
            )
            .mappings()
            .one()
        )
        reports.append(
            BoundReport(
                run_id=run_id,
                job_id=job.id,
                report_code=body.report_code,
                parameters_sha256=sha256_hex(row["parameters"]),
                entity_ids=tuple(row["entity_ids"]),
                book_code=row["book_code"],
                as_of_date=row["as_of_date"],
                known_at=row["known_at"],
            )
        )
    return RegisterSources(
        tenant_id=selection.tenant_id,
        request=request,
        known_at=selection.known_at,
        entity_ids=selection.entity_ids,
        entity_codes=entity_codes,
        reports=tuple(reports),
    )


def checked_row(row: Mapping[str, Any]) -> RegisterSources:
    try:
        bound = RegisterSources.model_validate(row["source_binding"])
    except (KeyError, ValidationError) as error:
        raise Problem("validation-failed", "Invalid retained register evidence sources.") from error
    if (
        row["tenant_id"] != bound.tenant_id
        or row["created_at"] != bound.known_at
        or any(
            row[key] != value
            for key, value in bound.pack_values().items()
            if key not in {"source_binding", "report_run_ids"}
        )
        or sorted(row["report_run_ids"]) != bound.pack_values()["report_run_ids"]
    ):
        raise Problem("validation-failed", "Register evidence differs from its retained selectors.")
    return bound


def load(uow: UnitOfWork, pack_id: UUID) -> RegisterSources:
    row = (
        uow.session.execute(
            select(evidence_pack).where(
                evidence_pack.c.tenant_id == uow.principal.tenant_id,
                evidence_pack.c.id == pack_id,
                evidence_pack.c.kind.in_(REPORTS),
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    bound = checked_row(dict(row))
    authorize(uow, bound.entity_ids)
    jobs = {
        identity: job_id
        for identity, job_id in uow.session.execute(
            select(report_run.c.id, report_run.c.job_id).where(
                report_run.c.tenant_id == bound.tenant_id,
                report_run.c.id.in_([report.run_id for report in bound.reports]),
            )
        ).all()
    }
    if jobs != {report.run_id: report.job_id for report in bound.reports}:
        raise Problem("validation-failed", "A retained register report has no matching job.")
    return bound


def collect(uow: UnitOfWork, pack_id: UUID) -> tuple[PackFile, ...]:
    """Collect saved report sections only; never queue newer reports on retry."""
    bound = load(uow, pack_id)
    files = tuple(
        file for report in bound.reports for file in evidence_reports.collect(uow, report.source())
    )
    return (
        *files,
        PackFile("registers/source_binding.json", canonical_bytes(bound.model_dump(mode="json"))),
    )
