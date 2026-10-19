"""Current-release validation orchestration requests and durable phase responses."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from erev_api.enums import ReleaseValidationStatus


class ReleaseValidationAdvanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retry_report: bool = False


class ReleaseValidationAdvanceOut(BaseModel):
    validation_id: UUID
    status: ReleaseValidationStatus
    phase: Literal[
        "ENABLED",
        "PREPARATION_REQUIRED",
        "WAITING_REPLAY",
        "WAITING_REPORT",
        "REPORT_FAILED",
        "READY_FOR_ACCEPTANCE",
        "PENDING_APPROVAL",
        "FAILED",
        "REJECTED",
        "INCOMPLETE",
        "RESTART_REQUIRED",
    ]
    attempt_id: UUID | None
    report_id: UUID | None
    job_ids: list[UUID]
