"""Resolve a saved forecast through the current logical scenario's successful refresh chain.

Archived workspaces are not globally searchable. The current scenario grants access only to
its own proven predecessors, and the requester must still hold the saved run's entity scope.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import forecast_event_set, forecast_run, scenario, scenario_refresh, tenant
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.problems import Problem
from erev_api.schemas.forecast_runs import ForecastParameters
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class SavedForecast:
    scenario_id: UUID
    source_tenant_id: UUID
    forecast_tenant_id: UUID
    actuals_cutoff: datetime
    last_refreshed_at: datetime | None
    actuals_snapshot_id: UUID
    run: Mapping[str, Any]


def predecessors(current: UUID, refreshes: Sequence[Mapping[str, Any]]) -> tuple[UUID, ...]:
    """Follow successful target-to-source edges; failed refresh copies are never ancestors."""
    parents: dict[UUID, UUID] = {}
    for refresh in refreshes:
        if refresh["status"] != "SUCCEEDED":
            continue
        target, source = refresh["target_tenant_id"], refresh["source_tenant_id"]
        if target in parents:
            raise Problem("precondition-failed", "The scenario refresh lineage is ambiguous.")
        parents[target] = source
    chain = [current]
    while chain[-1] in parents:
        parent = parents[chain[-1]]
        if parent in chain:
            raise Problem("precondition-failed", "The scenario refresh lineage contains a cycle.")
        chain.append(parent)
    return tuple(chain)


def resolve(uow: UnitOfWork, run_id: UUID) -> SavedForecast:
    actor = uow.principal
    if (
        uow.ctx.tenant_kind != TenantKind.SANDBOX
        or actor.kind != PrincipalKind.USER
        or "scenario.use" not in actor.permissions
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    original = actor.db_context
    parent = uow.session.execute(
        select(tenant.c.source_tenant_id).where(
            tenant.c.id == actor.tenant_id,
            tenant.c.kind == "sandbox",
            tenant.c.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if parent is None:
        raise Problem("not-found")
    try:
        set_tenant_context(
            uow.session, DbContext(tenant_id=parent, user_id=actor.id, entity_scope="*")
        )
        logical = (
            uow.session.execute(
                select(scenario).where(
                    scenario.c.scenario_tenant_id == actor.tenant_id, scenario.c.status == "ACTIVE"
                )
            )
            .mappings()
            .one_or_none()
        )
        if logical is None:
            raise Problem("not-found")
        lineage = predecessors(
            actor.tenant_id,
            [
                dict(row)
                for row in uow.session.execute(
                    select(scenario_refresh).where(scenario_refresh.c.scenario_id == logical["id"])
                ).mappings()
            ],
        )
        for workspace_id in lineage:
            set_tenant_context(
                uow.session,
                DbContext(
                    tenant_id=workspace_id, user_id=actor.id, entity_scope=original.entity_scope
                ),
            )
            valid_workspace = uow.session.scalar(
                select(tenant.c.id).where(
                    tenant.c.id == workspace_id,
                    tenant.c.kind == "sandbox",
                    tenant.c.source_tenant_id == parent,
                    tenant.c.status.in_(("ACTIVE", "ARCHIVED")),
                )
            )
            if valid_workspace is None:
                raise Problem(
                    "precondition-failed", "The scenario forecast archive is unavailable."
                )
            saved = (
                uow.session.execute(
                    select(forecast_run)
                    .join(
                        forecast_event_set,
                        (forecast_event_set.c.tenant_id == forecast_run.c.tenant_id)
                        & (forecast_event_set.c.id == forecast_run.c.forecast_event_set_id),
                    )
                    .where(
                        forecast_run.c.id == run_id,
                        forecast_event_set.c.production_scenario_id == logical["id"],
                        forecast_event_set.c.status == "PUBLISHED",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if saved is None:
                continue
            parameters = ForecastParameters.model_validate(saved["parameters"])
            for entity_id in parameters.entity_ids:
                require_for_entity(uow.ctx, "report.run", entity_id)
            if saved["status"] != "SUCCEEDED":
                raise Problem("invalid-transition", "Choose a succeeded forecast run.")
            return SavedForecast(
                logical["id"],
                parent,
                workspace_id,
                logical["base_known_at"],
                logical["last_refreshed_at"],
                logical["tenant_snapshot_id"],
                dict(saved),
            )
        raise Problem("not-found")
    finally:
        set_tenant_context(uow.session, original)
