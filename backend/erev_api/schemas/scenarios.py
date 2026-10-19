"""API-R-46 scenario catalogue and asynchronous creation schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import ScenarioStatus
from erev_api.schemas.common import ActorOut, JobOut


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


class ScenarioCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=400)
    purpose: str | None = Field(default=None, max_length=4000)
    known_at: AwareDatetime | None = None


class ScenarioRequestedOut(JobOut):
    scenario_id: UUID
    tenant_snapshot_id: UUID
