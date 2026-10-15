"""API-R-47 number-explanation submission and retained evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import AiProposalStatus
from erev_api.schemas.common import ActorOut
from erev_api.schemas.explain import ExplainObjectType


class AIExplanationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: ExplainObjectType
    id: UUID
    measure: str = Field(min_length=1, max_length=128)
    period: str | None = Field(default=None, min_length=1, max_length=100)


class AIProposalOut(BaseModel):
    """Retained number-explanation evidence authorized through its source trace."""

    id: UUID
    kind: Literal["NUMBER_EXPLANATION"]
    status: AiProposalStatus
    job_id: UUID | None
    subject_type: Literal["calc_trace"]
    subject_id: UUID
    content: dict[str, Any]
    citations: list[dict[str, Any]]
    ai_model_log_id: UUID
    expires_at: datetime
    problem: dict[str, Any] | None
    created_at: datetime
    created_by: ActorOut
    updated_at: datetime
    updated_by: ActorOut
    row_version: int
