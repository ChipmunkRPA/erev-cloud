"""API-R-27 SSP calculator schemas (04 §15.3 API-R-27, T-REF-32 to T-REF-34, §16.14, API-C-06,
API-C-12; SCREENS §11.5; BUILD_SPEC RFD-15).

04 names no calculator schema (L2-1-Q-52). A run returns the T-REF-32 columns with ``created_by``
as API-S-Actor. Its parameters are the T-REF-32 members plus ``ssp_book_id`` and ``pool_file_id``
(L2-1-Q-53). A result returns the T-REF-33 columns with the product code; an observation the §16.14
members with ``product_code``; an exclusion the T-REF-34 columns with the order line reference.
Decimals travel as API-C-06 strings.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import RunStatus
from erev_api.money import CurrencyCode, DecimalStr
from erev_api.schemas.common import ActorOut, RefOut
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

TEXT_LENGTH: Final = 255
MAX_PRODUCTS: Final = 100
CalculatorSource = Literal["source_order_lines", "committed_obligations"]


class SspCalculatorParametersIn(BaseModel):
    """T-REF-32 ``parameters`` of a new run."""

    model_config = ConfigDict(extra="forbid")

    source: CalculatorSource = Field(
        description="source_order_lines reads the pool file; committed_obligations the contracts"
    )
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_PRODUCTS)
    dimensions: dict[str, str] = Field(
        default_factory=dict,
        description="Filters: entity, region, channel, segment, deal_size_band, term_band",
    )
    date_from: date
    date_to: date = Field(description="Inclusive")
    band_ratio: DecimalStr = Field(default="0.15", description="Half-width around the median")
    currency: CurrencyCode
    ssp_book_id: uuid.UUID = Field(description="The book a draft version is created in")
    pool_file_id: uuid.UUID | None = Field(
        default=None, description="An IMPORT_SOURCE CSV file; required for source_order_lines"
    )


class SspCalculatorRunIn(BaseModel):
    """``POST /ssp-calculator-runs``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=LABEL_LENGTH)
    parameters: SspCalculatorParametersIn


class SspCalculatorParametersOut(BaseModel):
    """The stored T-REF-32 ``parameters``."""

    source: CalculatorSource
    product_ids: list[uuid.UUID]
    dimensions: dict[str, str]
    date_from: date
    date_to: date
    band_ratio: str
    currency: str
    ssp_book_id: uuid.UUID
    pool_file_id: uuid.UUID | None


class SspCalculatorRunOut(BaseModel):
    """API-S-SspCalculatorRun (L2-1-Q-52)."""

    id: uuid.UUID
    name: str
    parameters: SspCalculatorParametersOut
    status: RunStatus
    observation_count: int | None = Field(description="Non-excluded observations of every result")
    result_file_id: uuid.UUID | None = Field(description="The observations file")
    draft_ssp_book_version_id: uuid.UUID | None
    job_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: ActorOut
    created_at: datetime


class SspCalculatorHistogramBinOut(BaseModel):
    """One ``histogram`` bin: ``from`` inclusive, ``to`` exclusive except for the last bin."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    count: int


class SspCalculatorResultOut(BaseModel):
    """API-S-SspCalculatorResult: T-REF-33 statistics of one product and key."""

    id: uuid.UUID
    ssp_calculator_run_id: uuid.UUID
    product_id: uuid.UUID
    product_code: str
    stratification: str
    dimension_key: dict[str, str]
    currency: str
    observation_count: int = Field(description="Non-excluded observations")
    excluded_count: int
    median_unit_price: str
    mean_unit_price: str
    p10_unit_price: str
    p25_unit_price: str
    p75_unit_price: str
    p90_unit_price: str
    band_ratio: str
    compliance_ratio: str = Field(description="inside_count ÷ observation_count")
    inside_count: int = Field(description="Non-excluded observations inside the proposed band")
    proposed_low: str
    proposed_mid: str
    proposed_high: str
    histogram: list[SspCalculatorHistogramBinOut]


class SspCalculatorObservationOut(BaseModel):
    """One observation of ``GET /ssp-calculator-runs/{id}/observations`` (04 §16.14)."""

    date: date
    source_reference: str = Field(description="Order line external id")
    product_code: str
    customer: RefOut | None
    quantity: str
    unit_price: str
    in_band: bool = Field(description="Inside the proposed band of its product and key")
    exclusion_reason: str | None


class SspCalculatorExclusionIn(BaseModel):
    """``POST /ssp-calculator-runs/{id}/exclusions``: the observation and a reason of at least 10
    characters (SCREENS §11.5 exclude modal)."""

    model_config = ConfigDict(extra="forbid")

    source_reference: str = Field(max_length=TEXT_LENGTH, description="Order line external id")
    reason: str = Field(max_length=MEMO_LENGTH)


class SspCalculatorExclusionOut(BaseModel):
    """API-S-SspCalculatorExclusion: a T-REF-34 row."""

    id: uuid.UUID
    ssp_calculator_run_id: uuid.UUID
    source_ref_type: str
    source_ref_id: uuid.UUID
    source_reference: str
    reason: str
    created_by: ActorOut
    created_at: datetime


class SspCalculatorDraftVersionIn(BaseModel):
    """``POST /ssp-calculator-runs/{id}/create-draft-version`` (SCREENS §11.5 create draft
    modal)."""

    model_config = ConfigDict(extra="forbid")

    version_label: str = Field(max_length=TEXT_LENGTH)
    effective_from_date: date | None = None
    effective_to_date: date | None = None
    methodology_label: str | None = Field(default=None, max_length=LABEL_LENGTH)
