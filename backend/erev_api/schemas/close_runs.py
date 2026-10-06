"""API-R-39 close run schemas (04 §15.3 API-R-39, §16.8 API-S-CloseRunCreate, API-S-CloseRun,
"Close run commands"; T-CLS-01; E-62; SCREENS_B §1.2; BUILD_SPEC CLO-19).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import BookCode, CloseRunStatus, JobState
from erev_api.schemas.common import ActorOut, JobProgressOut, RefOut
from erev_api.schemas.periods import MEMO_LENGTH

CODE_LENGTH: Final = 64
PERIOD_KEY_LENGTH: Final = 16
# SCREENS_B SB-R-05: a high-risk confirmation carries a reason of at least 10 characters.
REASON_MIN_LENGTH: Final = 10


class CloseRunCreateIn(BaseModel):
    """API-S-CloseRunCreate: ``POST /close-runs`` answers 202 API-S-Job, or 200 API-S-CloseRun of
    the run that is already active for the entity, book and period."""

    model_config = ConfigDict(extra="forbid")

    entity_code: str = Field(min_length=1, max_length=CODE_LENGTH)
    book: BookCode | None = Field(default=None, description="Default the primary book")
    period_key: str = Field(min_length=1, max_length=PERIOD_KEY_LENGTH)


class CloseRunCancelIn(BaseModel):
    """``POST /close-runs/{id}/cancel``."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=REASON_MIN_LENGTH, max_length=MEMO_LENGTH)


class CloseRunPeriodOut(BaseModel):
    id: uuid.UUID
    period_key: str
    name: str
    start_date: date
    end_date: date


class CloseRunProblemOut(BaseModel):
    """The four base members of the problem a step failed with; the job's own problem is read
    through ``GET /jobs/{id}`` by its initiator and holders of ``audit.read`` (04 API-R-11)."""

    type: str
    title: str
    status: int
    detail: str | None


class CloseRunStepOut(BaseModel):
    """One T-CLS-01 ``steps`` element; ``counts`` holds what the step's summary states."""

    step_code: str
    status: CloseRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    counts: dict[str, Any]
    problem: CloseRunProblemOut | None


class CloseRunJobOut(BaseModel):
    """The newest ``CLOSE_RUN`` job of the run, as every reader of the run sees it."""

    id: uuid.UUID
    state: JobState
    progress: JobProgressOut


class CloseRunOut(BaseModel):
    """API-S-CloseRun: a T-CLS-01 row with its entity, period, steps and newest job."""

    id: uuid.UUID
    close_run_no: str
    entity: RefOut
    book: BookCode
    period: CloseRunPeriodOut
    status: CloseRunStatus
    cutoff_known_at: datetime
    current_step_code: str | None
    steps: list[CloseRunStepOut]
    counts: dict[str, Any]
    job: CloseRunJobOut | None
    journal_run_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int
