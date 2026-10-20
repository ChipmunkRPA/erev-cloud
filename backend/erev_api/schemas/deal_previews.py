"""Deal-desk request contracts; compute/save orchestration is implemented separately."""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from erev_api.events.payloads import NonNegativeMoney, PositiveDecimal


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
