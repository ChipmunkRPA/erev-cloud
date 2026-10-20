"""Deal-desk request contracts; compute/save orchestration is implemented separately."""

from datetime import date, datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from erev_api.enums import SspRangePosition
from erev_api.events.payloads import NonNegativeMoney, PositiveDecimal
from erev_api.money import MoneyOut
from erev_api.schemas.common import JobOut


class DealLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_code: str = Field(min_length=1, max_length=128)
    quantity: PositiveDecimal
    term_months: int | None = Field(default=None, strict=True, ge=1, le=1200)
    price: NonNegativeMoney
    performing_entity_code: str | None = Field(default=None, min_length=1, max_length=128)


class DealInputIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: UUID | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    entity_code: str = Field(min_length=1, max_length=128)
    start_date: date
    lines: list[DealLineIn] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def one_customer(self) -> Self:
        if (self.customer_id is None) == (self.customer_name is None):
            raise ValueError("Choose one customer ID or proposed customer name.")
        currencies = {line.price.currency for line in self.lines}
        if len(currencies) != 1:
            raise ValueError("All deal lines must use one transaction currency.")
        return self

    @field_validator("start_date", mode="before")
    @classmethod
    def calendar_date(cls, value: object) -> object:
        if not isinstance(value, str | date):
            raise ValueError("Provide a calendar date, not a numeric timestamp.")
        return value


class DealPreviewCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: DealInputIn


class DealPreviewSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    contract_external_id: str = Field(min_length=1, max_length=128)


class DealPreviewRequestedOut(JobOut):
    preview_id: UUID


class DealPreviewSummaryOut(BaseModel):
    id: UUID
    proposal: DealInputIn
    input_sha256: str
    result_sha256: str
    engine_release_id: UUID
    saved_contract_id: UUID | None
    created_at: datetime


class DealAllocationOut(BaseModel):
    subject_key: str
    obligation_key: str
    product_code: str
    stated_price: MoneyOut
    ssp_low: str | None
    ssp_mid: str | None
    ssp_high: str | None
    range_position: SspRangePosition | None
    selected_ssp: str | None
    allocation_weight: str | None
    allocated_amount: MoneyOut
    allocation_adjustment: MoneyOut


class DealRevenueOut(BaseModel):
    entity_code: str
    period_key: str
    subject_key: str
    product_code: str | None
    amount: MoneyOut


class DealBookOut(BaseModel):
    book_code: str
    transaction_price: MoneyOut
    total_allocated: MoneyOut
    scheduled: MoneyOut
    awaiting_trigger: MoneyOut
    has_material_right: bool
    has_variable_consideration: bool
    allocations: list[DealAllocationOut]
    revenue_by_period: list[DealRevenueOut]


class DealPreviewOut(DealPreviewSummaryOut):
    presentation: list[DealBookOut]
    result: dict[str, Any]
    pinned_refs: dict[str, Any]
