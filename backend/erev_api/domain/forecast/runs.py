"""Forecast run admission and scope validation; execution is imported only by the worker."""

from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id
from erev_api.db.tables import contract, forecast_run
from erev_api.domain.forecast import event_sets, input_order
from erev_api.domain.reports import forecast_sections, framework, requester, tie_outs
from erev_api.enums import JobKind, PrincipalKind, TenantKind
from erev_api.problems import Problem
from erev_api.schemas.forecast_runs import (
    ForecastParameters,
    ForecastRunCreateIn,
    ForecastRunRequestedOut,
)
from erev_api.uow import UnitOfWork


def validate(uow: UnitOfWork, values: ForecastParameters) -> None:
    if uow.ctx.tenant_kind != TenantKind.SANDBOX:
        raise Problem("invalid-transition", "Forecast runs belong to a scenario tenant.")
    if (
        uow.principal.kind != PrincipalKind.USER
        or uow.principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    if (
        len(set(values.entity_ids)) != len(values.entity_ids)
        or len(set(values.horizon_periods)) != len(values.horizon_periods)
        or len(set(values.output_formats)) != len(values.output_formats)
    ):
        raise Problem("validation-failed", "Forecast entities, periods and formats must be unique.")
    for entity_id in values.entity_ids:
        require_for_entity(uow.ctx, "report.run", entity_id)
    for format in values.output_formats:
        requester.require_export(uow.principal, format, values.entity_ids)
    entities = tie_outs.entities(uow.session, values.entity_ids)
    if {e.id for e in entities} != set(values.entity_ids):
        raise Problem("not-found")
    calendars = tie_outs.calendars(uow.session, entities)
    for entity in entities:
        calendar = calendars[entity.id]
        periods = tuple(calendar.named(key, "horizon_periods") for key in values.horizon_periods)
        forecast_sections._horizon(periods)
        if calendar.between(periods[0], periods[-1]) != periods:
            raise Problem("validation-failed", "Choose consecutive forecast periods.")


def inputs(uow: UnitOfWork, identity: UUID) -> dict[str, Any]:
    scenario_id = event_sets._scenario(uow.session, uow.principal.db_context)
    selected = event_sets._row(uow.session, identity, lock=True)
    if selected["status"] != "PUBLISHED" or selected["production_scenario_id"] != scenario_id:
        raise Problem("invalid-transition", "Choose a published input set of this scenario.")
    if sha256_hex(input_order.content(selected)) != selected["content_sha256"]:
        raise Problem("precondition-failed", "The forecast input publication hash differs.")
    input_order.sequence(selected)
    return selected


def state_fingerprint(uow: UnitOfWork) -> str:
    """Detect scenario contract edits while a requested forecast waits in the queue."""
    rows = uow.session.execute(
        select(
            contract.c.id,
            contract.c.combination_group_id,
            contract.c.head_stream_version,
        ).order_by(contract.c.id)
    ).mappings()
    return sha256_hex([dict(row) for row in rows])


def request(uow: UnitOfWork, body: ForecastRunCreateIn) -> ForecastRunRequestedOut:
    validate(uow, body.parameters)
    selected = inputs(uow, body.forecast_event_set_id)
    identity = new_id()
    pending = uow.defer(
        JobKind.FORECAST_RUN,
        {
            "forecast_run_id": str(identity),
            "input_sha256": selected["content_sha256"],
            "scenario_state_sha256": state_fingerprint(uow),
        },
        subject_type="forecast_run",
        subject_id=identity,
    )
    parameters = body.parameters.model_dump(mode="json")
    uow.session.execute(
        insert(forecast_run).values(
            tenant_id=uow.principal.tenant_id,
            id=identity,
            forecast_event_set_id=selected["id"],
            status="QUEUED",
            parameters=parameters,
            job_id=pending["id"],
            **framework._stamp(uow),
        )
    )
    uow.audit(
        action="forecast_run.create",
        object_type="forecast_run",
        object_id=identity,
        after={
            "forecast_event_set_id": str(selected["id"]),
            "parameters": parameters,
            "job_id": str(pending["id"]),
            "input_sha256": selected["content_sha256"],
            "scenario_state_sha256": state_fingerprint(uow),
        },
    )
    return ForecastRunRequestedOut(
        **framework._job_out(uow.session, pending["id"]).model_dump(), forecast_run_id=identity
    )
