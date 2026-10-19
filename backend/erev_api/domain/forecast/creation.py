"""Scenario snapshot requests and completion registration (BR-FC-01, SBX-09)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert, select

from erev_api.auth.principal import system_principal
from erev_api.db import new_id
from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import scenario, tenant_snapshot
from erev_api.domain.platform import sandboxes, snapshots
from erev_api.enums import PrincipalKind
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut
from erev_api.uow import UnitOfWork


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    name: str = Field(min_length=1, max_length=400)
    purpose: str | None = Field(default=None, max_length=4000)
    requested_by: UUID


def request(
    uow: UnitOfWork, *, name: str, purpose: str | None, known_at: datetime
) -> tuple[UUID, UUID, JobOut]:
    if uow.principal.kind is not PrincipalKind.USER or uow.principal.id is None:
        raise Problem("forbidden", "A workspace member must request a scenario.")
    if not name.strip():
        raise Problem("validation-failed", "A scenario needs a name.")
    requested = ScenarioRequest(
        id=new_id(), name=name.strip(), purpose=purpose, requested_by=uow.principal.id
    )
    row, job = snapshots.request_scenario_snapshot(
        uow,
        known_at=known_at,
        name=requested.name,
        scenario_request=requested.model_dump(mode="json"),
    )
    uow.audit(
        action="scenario.request",
        object_type="scenario",
        object_id=requested.id,
        after={"name": requested.name, "tenant_snapshot_id": str(row["id"]), "job_id": str(job.id)},
    )
    return requested.id, UUID(str(row["id"])), job


def register(
    jc: JobContext,
    *,
    requested: ScenarioRequest,
    snapshot_id: UUID,
    target_id: UUID,
    known_at: datetime,
) -> None:
    """Register only the completed copy, with source and sandbox audit records."""
    with system_unit_of_work(
        jc.runtime, system_principal(target_id), request_id=f"job-{jc.job_id}-scenario-audit"
    ) as uow:
        sandboxes.require_point_in_time(uow.session, target_id)
        uow.audit(
            action="scenario.create",
            object_type="scenario",
            object_id=requested.id,
            after={
                "source_tenant_id": str(jc.tenant_id),
                "name": requested.name,
                "tenant_snapshot_id": str(snapshot_id),
            },
        )
        uow.commit()
    with jc.unit_of_work() as uow:
        # The creator's copied membership exposes the target to RLS-TN; no privileged lookup.
        set_tenant_context(
            uow.session,
            DbContext(tenant_id=jc.tenant_id, user_id=requested.requested_by, entity_scope="*"),
        )
        snapshot = (
            uow.session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
            .mappings()
            .one()
        )
        if snapshot["status"] != "SUCCEEDED" or snapshot["target_tenant_id"] != target_id:
            raise Problem("precondition-failed", "The scenario copy is not complete.")
        uow.session.execute(
            insert(scenario).values(
                tenant_id=jc.tenant_id,
                id=requested.id,
                name=requested.name,
                purpose=requested.purpose,
                scenario_tenant_id=target_id,
                tenant_snapshot_id=snapshot_id,
                base_known_at=known_at,
                status="ACTIVE",
                created_at=uow.now,
                created_by=requested.requested_by,
                created_by_kind="USER",
                updated_at=uow.now,
                updated_by_kind="SYSTEM",
            )
        )
        uow.audit(
            action="scenario.create",
            object_type="scenario",
            object_id=requested.id,
            after={
                "name": requested.name,
                "status": "ACTIVE",
                "scenario_tenant_id": str(target_id),
                "tenant_snapshot_id": str(snapshot_id),
            },
            detail={"requested_by": str(requested.requested_by)},
        )
        uow.commit()
