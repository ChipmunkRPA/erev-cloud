"""API-R-18 calendar schemas (04 §15.3 API-R-18, T-REF-04, T-REF-05; BUILD_SPEC RFD-1).

04 §16 defines no calendar schema. The members follow the T-REF-04 columns, and a generated period
carries the member set of API-S-Period ``period`` (§16.8) (L1-1-Q-1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import CalendarPattern
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH

YearEndAnchor = Literal["LAST_WEEKDAY_OF_MONTH", "NEAREST_WEEKDAY_TO_MONTH_END"]
# [J] Plausible fiscal years; the bounds keep every generated date inside the date range.
FISCAL_YEAR_MIN: Final = 1900
FISCAL_YEAR_MAX: Final = 2999


class CalendarIn(BaseModel):
    """``POST /calendars``: a fiscal calendar definition (T-REF-04)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    pattern: CalendarPattern = CalendarPattern.MONTHLY
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    week_end_day: int | None = Field(
        default=None,
        ge=1,
        le=7,
        description="ISO weekday on which weeks end (1 Monday to 7 Sunday); week-based patterns",
    )
    year_end_anchor: YearEndAnchor | None = Field(
        default=None, description="Week-based patterns only (BUILD_SPEC BS3-D-16)"
    )


class CalendarOut(BaseModel):
    """A T-REF-04 calendar (L1-1-Q-1)."""

    id: uuid.UUID
    code: str
    name: str
    pattern: CalendarPattern
    fiscal_year_start_month: int
    week_end_day: int | None
    year_end_anchor: YearEndAnchor | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class GenerateYearIn(BaseModel):
    """``POST /calendars/{id}/generate-year``."""

    model_config = ConfigDict(extra="forbid")

    fiscal_year: int = Field(
        ge=FISCAL_YEAR_MIN,
        le=FISCAL_YEAR_MAX,
        description="The calendar year in which the fiscal year ends (T-REF-05)",
    )


class CalendarPeriodOut(BaseModel):
    """A T-REF-05 period: the members of API-S-Period ``period`` (§16.8)."""

    id: uuid.UUID
    period_key: str
    name: str
    fiscal_year: int
    period_no: int
    quarter_no: int
    start_date: date
    end_date: date


class GenerateYearOut(BaseModel):
    """Every period of the fiscal year in period order, how many the command inserted, and how
    many period states it wrote for the books kept on the calendar."""

    calendar_id: uuid.UUID
    fiscal_year: int
    inserted_count: int
    inserted_state_count: int = Field(
        description=(
            "Period states written: one for each period of the calendar and each book an entity "
            "on it keeps that had none, of every entity"
        )
    )
    periods: list[CalendarPeriodOut]
