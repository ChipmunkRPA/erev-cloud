"""Named shared-estimate populations and record-time membership commands."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import EstimateMethod
from erev_api.money import CurrencyCode
from erev_api.schemas.estimates import Code, EstimateVersionCreateIn
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH


class PortfolioIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=CODE_LENGTH)
    name: str = Field(min_length=1, max_length=LABEL_LENGTH)
    product_group: str | None = Field(default=None, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PortfolioOut(PortfolioIn):
    id: UUID
    row_version: int
    created_at: datetime
    updated_at: datetime


class PortfolioMemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    contract_id: UUID
    rationale: str = Field(min_length=1, max_length=MEMO_LENGTH)


class PortfolioMemberCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    rationale: str = Field(min_length=1, max_length=MEMO_LENGTH)


class PortfolioMemberOut(BaseModel):
    id: UUID
    portfolio_id: UUID
    contract_id: UUID
    contracting_entity_id: UUID
    contract_external_id: str
    valid_from_known_at: datetime
    valid_to_known_at: datetime | None
    portfolio_row_version: int


class PortfolioEstimateIn(BaseModel):
    """A shared-estimate definition, without contract-specific allocation targets."""

    model_config = ConfigDict(extra="forbid")
    element_code: Code
    estimate_kind: Literal["RETURN_RATE", "BREAKAGE"]
    method: EstimateMethod


class PortfolioEstimateVersionIn(EstimateVersionCreateIn):
    """Full draft values with an explicit currency; no member-specific links."""

    currency: CurrencyCode
    modification_id: None = None
    judgement_record_id: None = None


class PortfolioBreakageShareOut(BaseModel):
    contract_id: UUID
    contract_external_id: str
    contract_version_id: UUID
    obligation_id: UUID
    obligation_key: str
    ssp: str
    entitlement_quantity: str
    breakage_quantity: str


class PortfolioBreakagePreviewOut(BaseModel):
    basis: Literal["CURRENT_COMPUTED_SSP_PREVIEW"] = "CURRENT_COMPUTED_SSP_PREVIEW"
    portfolio_id: UUID
    version_id: UUID
    book_code: str
    currency: str
    total_breakage_quantity: str
    allocated_total: str
    shares: list[PortfolioBreakageShareOut]
