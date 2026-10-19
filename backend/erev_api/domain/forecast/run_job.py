"""Compute and publish scenario forecast reports in one fenced worker transaction."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from erev_api.db.tables import contract, forecast_run, job
from erev_api.db.transitions import apply
from erev_api.domain.contracts import computation
from erev_api.domain.forecast import runs
from erev_api.domain.platform import sandboxes
from erev_api.domain.reports import forecast_capture, forecast_publication
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.forecast_exports import Identity
from erev_api.enums import JobKind
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.problems import Problem
from erev_api.schemas.forecast_runs import ForecastParameters
from erev_api.uow import UnitOfWork


def failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    identity = UUID(str(params["forecast_run_id"]))
    row = (
        uow.session.execute(
            select(forecast_run).where(forecast_run.c.id == identity).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["status"] in {"SUCCEEDED", "FAILED"}:
        return
    apply(
        uow.session,
        "forecast_run",
        identity,
        to_status="FAILED",
        expected_status=row["status"],
        set_values={"finished_at": uow.now, "problem": dict(problem)},
    )
    uow.audit(
        action="forecast_run.fail",
        object_type="forecast_run",
        object_id=identity,
        after={"status": "FAILED", "problem": dict(problem)},
    )


def cancelled(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    failed(uow, params, {"title": "Forecast run cancelled", "job_id": str(job_id)})


def cancel_guard(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    row = uow.session.execute(
        select(forecast_run.c.status).where(
            forecast_run.c.id == UUID(str(params["forecast_run_id"])),
            forecast_run.c.job_id == job_id,
        )
    ).scalar_one_or_none()
    if row == "SUCCEEDED":
        raise Problem("invalid-transition", "The forecast reports have already been published.")


class Cancelled(Exception):
    pass


def checkpoint(jc: JobContext) -> None:
    jc.heartbeat()
    if jc.cancel_requested():
        raise Cancelled


@task(
    JobKind.FORECAST_RUN,
    retry=RetryPolicy(max_attempts=1),
    on_failure=failed,
    on_cancel=cancelled,
    cancel_guard=cancel_guard,
)
def run_forecast(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    try:
        return execute(jc, params)
    except Cancelled:
        with jc.unit_of_work() as uow:
            cancelled(uow, params, jc.job_id)
            uow.commit()
        return outcome(UUID(str(params["forecast_run_id"])), [])


def execute(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    identity = UUID(str(params["forecast_run_id"]))
    with jc.unit_of_work() as uow:
        row = (
            uow.session.execute(select(forecast_run).where(forecast_run.c.id == identity))
            .mappings()
            .one()
        )
        if row["job_id"] != jc.job_id or row["created_by"] != jc.principal.on_behalf_of_id:
            raise Problem("forbidden")
        actor_id = row["created_by"]
    actor = sandboxes.sandbox_actor(jc.tenant_id, actor_id, at=jc.clock.now())
    with system_unit_of_work(jc.runtime, actor, request_id=f"job-{jc.job_id}-forecast") as uow:
        row = (
            uow.session.execute(
                select(forecast_run).where(forecast_run.c.id == identity).with_for_update()
            )
            .mappings()
            .one()
        )
        values = ForecastParameters.model_validate(row["parameters"])
        runs.validate(uow, values)
        if row["status"] == "SUCCEEDED":
            return outcome(identity, row["report_run_ids"])
        if row["status"] != "QUEUED":
            raise Problem("invalid-transition", "The forecast run cannot start.")
        if runs.state_fingerprint(uow) != params["scenario_state_sha256"]:
            raise Problem(
                "precondition-failed", "Scenario inputs changed; request a new forecast run."
            )
        selected = runs.inputs(uow, row["forecast_event_set_id"])
        if selected["content_sha256"] != params["input_sha256"]:
            raise Problem("precondition-failed", "The requested forecast inputs changed.")
        apply(
            uow.session,
            "forecast_run",
            identity,
            to_status="RUNNING",
            expected_status="QUEUED",
            set_values={"started_at": uow.now},
        )
        uow.audit(
            action="forecast_run.start",
            object_type="forecast_run",
            object_id=identity,
            after={"status": "RUNNING"},
        )
        groups = uow.session.scalars(
            select(contract.c.combination_group_id)
            .where(
                contract.c.contracting_entity_id.in_(values.entity_ids),
                contract.c.activated_at.is_not(None),
            )
            .distinct()
            .order_by(contract.c.combination_group_id)
        ).all()
        for group in groups:
            checkpoint(jc)
            computed = computation.recompute(uow, group, job_id=jc.job_id)
            if computed["status"] != "SUCCEEDED":
                raise Problem(
                    "invalid-transition", "A forecast group did not compute successfully."
                )
        clock_at = uow.session.execute(select(func.clock_timestamp())).scalar_one()
        cutoff = max(uow.now, clock_at)
        source = Identity(
            selected["production_scenario_id"],
            "Scenario",
            selected["id"],
            selected["name"],
            selected["version_no"],
            selected["content_sha256"],
        )
        reports = []
        for format in values.output_formats:
            checkpoint(jc)
            captured = forecast_capture.capture(
                uow,
                ReportParams(
                    report_code="forecast_outputs",
                    report_version=1,
                    parameters={"currency_view": values.currency_view},
                    entity_ids=tuple(values.entity_ids),
                    known_at=cutoff,
                    book_code=values.book_code,
                    output_format=format,
                ),
                horizon=values.horizon_periods,
            )
            reports.append(forecast_publication.publish(uow, identity, captured, source))
        checkpoint(jc)
        # Serialize the final cancellation decision and publication commit on the job row.
        requested = uow.session.execute(
            select(job.c.cancel_requested_at)
            .where(
                job.c.id == jc.job_id,
            )
            .with_for_update()
        ).scalar_one()
        if requested is not None:
            raise Cancelled
        apply(
            uow.session,
            "forecast_run",
            identity,
            to_status="SUCCEEDED",
            expected_status="RUNNING",
            set_values={"finished_at": uow.now},
        )
        uow.audit(
            action="forecast_run.succeed",
            object_type="forecast_run",
            object_id=identity,
            after={"status": "SUCCEEDED", "report_run_ids": [str(r) for r in reports]},
        )
        uow.commit()
    return outcome(identity, reports)


def outcome(identity: UUID, reports: Any) -> JobOutcome:
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "forecast_run_id": str(identity),
            "report_run_ids": [str(r) for r in reports],
            "href": f"/api/v1/forecast-runs/{identity}",
        },
    )
