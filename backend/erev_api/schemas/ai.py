"""API-R-47 number-explanation submission."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from erev_api.schemas.explain import ExplainObjectType


class AIExplanationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: ExplainObjectType
    id: UUID
    measure: str = Field(min_length=1, max_length=128)
    period: str | None = Field(default=None, min_length=1, max_length=100)
