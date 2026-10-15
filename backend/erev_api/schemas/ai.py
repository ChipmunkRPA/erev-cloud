"""API-R-47 AI submission and retained evidence."""

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


class AIContractExtractionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: UUID


class AIProposalEvidenceOut(BaseModel):
    """Common retained proposal metadata."""

    id: UUID
    status: AiProposalStatus
    job_id: UUID | None
    citations: list[dict[str, Any]]
    ai_model_log_id: UUID
    expires_at: datetime
    problem: dict[str, Any] | None
    created_at: datetime
    created_by: ActorOut
    updated_at: datetime
    updated_by: ActorOut
    row_version: int
    rejected_by: ActorOut | None
    rejected_at: datetime | None
    rejection_reason: str | None


class AIProposalOut(AIProposalEvidenceOut):
    """Retained number-explanation evidence authorized through its source trace."""

    kind: Literal["NUMBER_EXPLANATION"]
    subject_type: Literal["calc_trace"]
    subject_id: UUID
    content: dict[str, Any]


class AIExtractionProposalOut(AIProposalEvidenceOut):
    """Extraction suggestions remain review evidence, never accepted contract values."""

    kind: Literal["CONTRACT_EXTRACTION"]
    file_object_id: UUID
    document_text_file_id: UUID
    content: list[dict[str, Any]]


class AIProposalRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=4000)
