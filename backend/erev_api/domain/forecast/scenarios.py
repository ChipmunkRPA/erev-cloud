"""Tenant-scoped scenario catalogue (API-R-46)."""

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import scenario
from erev_api.domain.platform import actors


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
