"""Advance current-release validation through durable replay, report and acceptance stages."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import job, release_validation_attempt, report_run
from erev_api.domain.reports import framework
from erev_api.problems import Problem
from erev_api.schemas.reports import ReportRunCreateIn
from erev_api.uow import UnitOfWork

from . import (
    validation_acceptance,
    validation_aggregation,
    validation_artifacts,
    validation_attempts,
    validation_creation,
    validation_fanout,
    validation_reports,
)


@dataclass(frozen=True)
class Advancement:
    validation_id: UUID
    status: str
    phase: str
    attempt_id: UUID | None = None
    report_id: UUID | None = None
    job_ids: tuple[UUID, ...] = ()


def advance(uow: UnitOfWork, *, retry_report: bool = False) -> Advancement:
    """Perform one durable stage; the caller commits before advancing again.

    Report attachment is a separate stage from final acceptance so no retained-file reads
    happen under the population fence. Repeated calls resume stored work rather than redrawing
    a sample or duplicating child jobs/reports. Failures never silently replace an attempt.
    """
    if (
        "report.run" not in uow.principal.permissions
        or uow.principal.permission_scopes.get("report.run") != "*"
        or uow.principal.db_context.entity_scope != "*"
    ):
        raise Problem("forbidden", "Release validation requires report access for all entities.")
    parent = validation_creation.ensure(uow)
    validation_id = parent["id"]
    status = parent["status"]
    if parent["enabled_at"] is not None:
        return Advancement(validation_id, status, "ENABLED", parent["accepted_attempt_id"])
    if status in {"PENDING_APPROVAL", "FAILED", "REJECTED"}:
        return Advancement(validation_id, status, status)
    if parent["source_engine_release_id"] is None or parent["effective_level"] not in {
        "MINOR",
        "MAJOR",
    }:
        return Advancement(validation_id, status, "PREPARATION_REQUIRED")
    attempt = (
        uow.session.execute(
            select(release_validation_attempt)
            .where(release_validation_attempt.c.release_validation_id == validation_id)
            .order_by(release_validation_attempt.c.attempt_no.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if attempt is None:
        frozen = validation_attempts.freeze(uow, validation_id=validation_id, attempt_no=1)
        fanout = validation_fanout.enqueue(uow, validation_id=validation_id, attempt_id=frozen.id)
        return Advancement(
            validation_id, "RUNNING", "WAITING_REPLAY", frozen.id, job_ids=fanout.job_ids
        )
    attempt_id = attempt["id"]
    if attempt["status"] == "SUPERSEDED" or status == "INCOMPLETE":
        return Advancement(validation_id, status, "RESTART_REQUIRED", attempt_id)
    if attempt["report_run_id"] is not None:
        result = validation_acceptance.finalize(
            uow,
            validation_id=validation_id,
            attempt_id=attempt_id,
            report_id=attempt["report_run_id"],
        )
        return Advancement(
            validation_id,
            result,
            "ENABLED" if result in {"PASSED", "APPROVED"} else result,
            attempt_id,
            attempt["report_run_id"],
        )
    if attempt["status"] == "SELECTED":
        fanout = validation_fanout.enqueue(uow, validation_id=validation_id, attempt_id=attempt_id)
        return Advancement(
            validation_id, "RUNNING", "WAITING_REPLAY", attempt_id, job_ids=fanout.job_ids
        )
    decision = validation_aggregation.assess(
        uow, validation_id=validation_id, attempt_id=attempt_id
    )
    if decision.status is None:
        # Re-enqueue also repairs scheduler deliveries lost after a committed fanout.
        fanout = validation_fanout.enqueue(uow, validation_id=validation_id, attempt_id=attempt_id)
        return Advancement(
            validation_id, status, "WAITING_REPLAY", attempt_id, job_ids=fanout.job_ids
        )
    validation_artifacts.retain(uow, validation_id=validation_id, attempt_id=attempt_id)
    # retain holds the parent/attempt locks; concurrent callers cannot both create the report.
    run = (
        uow.session.execute(
            select(report_run, job.c.state.label("job_state"))
            .join(
                job, (job.c.tenant_id == report_run.c.tenant_id) & (job.c.id == report_run.c.job_id)
            )
            .where(
                report_run.c.report_code == "upgrade_validation",
                report_run.c.output_format == "JSON",
                report_run.c.parameters["release_validation_attempt_id"].astext == str(attempt_id),
            )
            .order_by(report_run.c.created_at.desc(), report_run.c.id.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        report_id, queued = framework.create_run(
            uow,
            ReportRunCreateIn(
                report_code="upgrade_validation",
                output_format="JSON",
                parameters={"release_validation_attempt_id": str(attempt_id)},
            ),
        )
        return Advancement(
            validation_id, status, "WAITING_REPORT", attempt_id, report_id, (queued.id,)
        )
    report_id = run["id"]
    if run["job_state"] in {"FAILED", "CANCELLED"}:
        if retry_report:
            report_id, queued = framework.rerun(uow, report_id)
            return Advancement(
                validation_id, status, "WAITING_REPORT", attempt_id, report_id, (queued.id,)
            )
        return Advancement(validation_id, status, "REPORT_FAILED", attempt_id, report_id)
    if run["status"] != "SUCCEEDED" or run["job_state"] not in {
        "SUCCEEDED",
        "SUCCEEDED_WITH_EXCEPTIONS",
    }:
        return Advancement(
            validation_id, status, "WAITING_REPORT", attempt_id, report_id, (run["job_id"],)
        )
    validation_reports.attach(
        uow, validation_id=validation_id, attempt_id=attempt_id, report_id=report_id
    )
    return Advancement(validation_id, status, "READY_FOR_ACCEPTANCE", attempt_id, report_id)
