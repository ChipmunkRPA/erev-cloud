"""API-R-46 scenario catalogue response."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from erev_api.enums import ScenarioStatus
from erev_api.schemas.common import ActorOut


class ScenarioOut(BaseModel):
    id: UUID
    name: str
    purpose: str | None
    scenario_tenant_id: UUID
    tenant_snapshot_id: UUID
    base_known_at: datetime
    status: ScenarioStatus
    last_refreshed_at: datetime | None
    created_at: datetime
    created_by: ActorOut
    updated_at: datetime
    row_version: int
