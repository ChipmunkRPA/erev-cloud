"""Tenant-scoped scenario catalogue (API-R-46)."""

from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import DbContext, set_tenant_context, tenant_session
from erev_api.db.tables import forecast_event_set, scenario, tenant
from erev_api.domain.platform import actors
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.problems import Problem


def list_scenarios[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """Read the source tenant's scenarios, including archived records."""
    statement = select(
        *scenario.c,
        actors.named(scenario.c.created_by, tenant_id=scenario.c.tenant_id).label("creator_name"),
    ).where(scenario.c.tenant_id == ctx.principal.tenant_id)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, statement)


def scenario_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """Use the common actor representation; tenant/internal actor columns stay private."""
    return {
        **{
            key: value
            for key, value in row.items()
            if key
            not in {"tenant_id", "created_by_kind", "updated_by_kind", "updated_by", "creator_name"}
        },
        "created_by": actors.actor(row["created_by"], row["created_by_kind"], row["creator_name"]),
    }


def published_inputs[T](
    ctx: RequestContext, scenario_id: UUID, *, page: Callable[[Session, Select[Any]], T]
) -> T:
    """Source-authorized metadata from exactly the scenario's current target workspace."""
    actor = ctx.principal
    if (
        ctx.tenant_kind != TenantKind.PRODUCTION
        or actor.kind != PrincipalKind.USER
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    with tenant_session(actor.db_context, read_only=True) as session:
        current = session.execute(
            select(scenario.c.scenario_tenant_id).where(
                scenario.c.id == scenario_id,
                scenario.c.tenant_id == actor.tenant_id,
                scenario.c.status == "ACTIVE",
            )
        ).scalar_one_or_none()
        if current is None:
            raise Problem("not-found")
        try:
            set_tenant_context(
                session, DbContext(tenant_id=current, user_id=actor.id, entity_scope="*")
            )
            valid_target = session.scalar(
                select(tenant.c.id).where(
                    tenant.c.id == current,
                    tenant.c.kind == "sandbox",
                    tenant.c.status == "ACTIVE",
                    tenant.c.source_tenant_id == actor.tenant_id,
                )
            )
            if valid_target is None:
                raise Problem("not-found")
            return page(
                session,
                select(
                    forecast_event_set.c.id,
                    forecast_event_set.c.code,
                    forecast_event_set.c.name,
                    forecast_event_set.c.version_no,
                    forecast_event_set.c.content_sha256,
                    forecast_event_set.c.published_at,
                    forecast_event_set.c.created_at,
                ).where(
                    forecast_event_set.c.tenant_id == current,
                    forecast_event_set.c.production_scenario_id == scenario_id,
                    forecast_event_set.c.status == "PUBLISHED",
                ),
            )
        finally:
            set_tenant_context(session, actor.db_context)
