"""API-R-46 forecast run admission and durable result."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from erev_api.schemas.common import JobOut


class ForecastParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horizon_periods: list[str] = Field(min_length=1)
    entity_ids: list[UUID] = Field(min_length=1)
    book_code: Literal["ASC606", "IFRS15"]
    currency_view: Literal["transaction", "functional"] = "transaction"
    output_formats: list[Literal["JSON", "XLSX", "CSV"]] = Field(default=["JSON"], min_length=1)


class ForecastRunCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forecast_event_set_id: UUID
    parameters: ForecastParameters


class ForecastRunRequestedOut(JobOut):
    forecast_run_id: UUID


class ForecastRunOut(BaseModel):
    id: UUID
    forecast_event_set_id: UUID
    status: str
    parameters: ForecastParameters
    report_run_ids: list[UUID]
    job_id: UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    problem: dict[str, Any] | None
    created_at: datetime
