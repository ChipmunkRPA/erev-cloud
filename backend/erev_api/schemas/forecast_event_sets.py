"""Versioned forecast input set requests and responses (API-R-46)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from erev_api.enums import ConfigStatus


class EventSetCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}$")
    name: str = Field(min_length=1, max_length=400)
    effective_from: AwareDatetime | None = None
    effective_to: AwareDatetime | None = None

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A name is required.")
        return value.strip()


class EventSetUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=400)
    effective_from: AwareDatetime | None = None
    effective_to: AwareDatetime | None = None

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("A name cannot be null.")
        return EventSetCreateIn.nonblank(value)


class EventSetOut(BaseModel):
    id: UUID
    code: str
    name: str
    production_scenario_id: UUID
    import_upload_ids: list[UUID]
    api_commands: list[dict[str, Any]]
    input_sequence: list[dict[str, Any]] | None = None
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    effective_to: datetime | None
    content_sha256: str | None
    published_at: datetime | None
    published_by: UUID | None
    supersedes_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    row_version: int
