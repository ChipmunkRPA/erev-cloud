"""API-R-26 SSP book schemas (04 §15.3 API-R-26, §16.4 API-S-SspBook, API-S-SspBookVersion,
API-S-SspEntry, T-REF-28 to T-REF-31, E-47, E-49, API-C-06; SCREENS §11.4; BUILD_SPEC RFD-12).

The members follow 04 §16.4. A version adds ``created_at`` and ``updated_at``; ``POST
/ssp-book-versions/{id}/entries`` answers with the stored entries in request order, and the diff
follows the §16.4 command responses (L2-1-Q-22). Decimals travel as API-C-06 strings.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import ConfigStatus, Distinctness, SspMethod, SspQuantityUnit, SspValueBasis
from erev_api.money import CurrencyCode, DecimalStr, MoneyOut
from erev_api.schemas.common import ActorOut
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

TEXT_LENGTH: Final = 255
MAX_BANDS: Final = 20  # 04 §16.4 ``ranges``
MAX_ENTRIES: Final = 5000  # 04 §16.4 entries per call
ResolutionMode = Literal["EFFECTIVE_DATE", "BY_LABEL"]
BandDimension = Literal["NONE", "QUANTITY", "DEAL_SIZE", "TERM_MONTHS"]


class SspBookIn(BaseModel):
    """``POST /ssp-books``: a T-REF-28 book and its scope."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)
    entity_code: str | None = Field(
        default=None, max_length=CODE_LENGTH, description="Scope; absent = all entities"
    )
    currency: CurrencyCode | None = Field(default=None, description="Scope; absent = any")
    channel: str | None = Field(default=None, max_length=TEXT_LENGTH)
    segment: str | None = Field(default=None, max_length=TEXT_LENGTH)
    resolution_mode: ResolutionMode = "EFFECTIVE_DATE"


class SspBookUpdateIn(BaseModel):
    """``PATCH /ssp-books/{id}``: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=CODE_LENGTH)
    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)
    entity_code: str | None = Field(default=None, max_length=CODE_LENGTH)
    currency: CurrencyCode | None = None
    channel: str | None = Field(default=None, max_length=TEXT_LENGTH)
    segment: str | None = Field(default=None, max_length=TEXT_LENGTH)
    resolution_mode: ResolutionMode | None = None


class SspCurrentVersionOut(BaseModel):
    """The latest APPROVED version of a book."""

    id: uuid.UUID
    version_no: int
    legacy_version_label: str | None
    effective_from_date: date | None
    effective_to_date: date | None


class SspBookOut(BaseModel):
    """API-S-SspBook."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    entity_code: str | None
    currency: str | None
    channel: str | None
    segment: str | None
    resolution_mode: ResolutionMode
    current_version: SspCurrentVersionOut | None
    draft_version_id: uuid.UUID | None = Field(description="The highest-numbered DRAFT version")
    row_version: int
    created_at: datetime
    updated_at: datetime


class SspBookVersionIn(BaseModel):
    """``POST /ssp-books/{id}/versions``: a DRAFT version, optionally copying another version's
    entries."""

    model_config = ConfigDict(extra="forbid")

    copy_from_version_id: uuid.UUID | None = None
    legacy_version_label: str | None = Field(default=None, max_length=TEXT_LENGTH)
    effective_from_date: date | None = Field(
        default=None, description="Required for EFFECTIVE_DATE books before submission"
    )
    effective_to_date: date | None = None
    methodology_label: str = Field(max_length=LABEL_LENGTH)
    is_methodology_change: bool = False


class SspBookVersionUpdateIn(BaseModel):
    """``PATCH /ssp-book-versions/{id}`` while DRAFT: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    legacy_version_label: str | None = Field(default=None, max_length=TEXT_LENGTH)
    effective_from_date: date | None = None
    effective_to_date: date | None = None
    methodology_label: str | None = Field(default=None, max_length=LABEL_LENGTH)
    is_methodology_change: bool | None = None


class SspBookVersionOut(BaseModel):
    """API-S-SspBookVersion (L2-1-Q-22)."""

    id: uuid.UUID
    ssp_book_id: uuid.UUID
    version_no: int
    status: ConfigStatus
    legacy_version_label: str | None
    effective_from_date: date | None
    effective_to_date: date | None
    methodology_label: str
    is_methodology_change: bool
    entry_count: int
    diff_summary: dict[str, Any] | None
    ssp_calculator_run_id: uuid.UUID | None = Field(
        description="The calculator run the version was created from (T-REF-29; L2-1-Q-58)"
    )
    study_attachment_ids: list[uuid.UUID] = Field(
        description=(
            "Live attachments of purpose SSP_STUDY whose file can still be read, in attachment "
            "order"
        )
    )
    approval_request_id: uuid.UUID | None
    content_sha256: str | None
    published_at: datetime | None = Field(description="Approval time")
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int


class SspBookVersionCommandIn(BaseModel):
    """``POST /ssp-book-versions/{id}/submit`` and ``/withdraw``: an optional comment."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class SspRangeIn(BaseModel):
    """One T-REF-31 band: per-unit values, or ratios of list price under PERCENT_OF_LIST."""

    model_config = ConfigDict(extra="forbid")

    band_dimension: BandDimension = "NONE"
    band_from: DecimalStr | None = Field(default=None, description="Inclusive")
    band_to: DecimalStr | None = Field(default=None, description="Exclusive")
    point_value: DecimalStr | None = None
    low_value: DecimalStr | None = None
    mid_value: DecimalStr | None = None
    high_value: DecimalStr | None = None


class SspRangeOut(BaseModel):
    """A stored T-REF-31 band."""

    band_dimension: BandDimension
    band_from: str | None
    band_to: str | None
    point_value: str | None
    low_value: str | None
    mid_value: str | None
    high_value: str | None


class SspEntryIn(BaseModel):
    """One API-S-SspEntry of ``POST /ssp-book-versions/{id}/entries``."""

    model_config = ConfigDict(extra="forbid")

    product_code: str = Field(max_length=CODE_LENGTH)
    stratification: str = Field(default="", max_length=TEXT_LENGTH)
    region: str | None = Field(default=None, max_length=TEXT_LENGTH)
    channel: str | None = Field(default=None, max_length=TEXT_LENGTH)
    segment: str | None = Field(default=None, max_length=TEXT_LENGTH)
    deal_size_band: str | None = Field(default=None, max_length=TEXT_LENGTH)
    term_band: str | None = Field(default=None, max_length=TEXT_LENGTH)
    currency: CurrencyCode
    method: SspMethod = Field(description="formula is refused")
    value_basis: SspValueBasis | None = Field(
        default=None,
        description=(
            "E-49; AMOUNT when omitted for a non-series product. A series product's entry declares"
            " it explicitly (D-97 (3a))."
        ),
    )
    quantity_unit: SspQuantityUnit | None = Field(
        default=None,
        description=(
            "E-125; what the line's quantity counts for a PER_INCREMENT entry (required then, never"
            " inferred; D-97 (3))."
        ),
    )
    unit_list_price: DecimalStr | None = Field(
        default=None, description="Required for legacy_range"
    )
    midpoint_discount_ratio: DecimalStr | None = Field(default=None, description="0 ≤ d < 1")
    range_ratio: DecimalStr | None = Field(default=None, description="At least 0")
    cost_basis: DecimalStr | None = None
    margin_ratio: DecimalStr | None = None
    observable_point: DecimalStr | None = Field(default=None, description="At least 0; POL-072")
    revenue_account_code: str | None = Field(default=None, max_length=CODE_LENGTH)
    distinctness: Distinctness
    ranges: list[SspRangeIn] | None = Field(
        default=None,
        max_length=MAX_BANDS,
        description="1 to 20 bands; for legacy_range the server derives the NONE band",
    )


class SspEntriesIn(BaseModel):
    """``POST /ssp-book-versions/{id}/entries``: 1 to 5,000 entries upserted by key."""

    model_config = ConfigDict(extra="forbid")

    entries: list[SspEntryIn] = Field(min_length=1, max_length=MAX_ENTRIES)


class SspEntryOut(BaseModel):
    """API-S-SspEntry."""

    id: uuid.UUID
    product_code: str
    stratification: str
    region: str | None
    channel: str | None
    segment: str | None
    deal_size_band: str | None
    term_band: str | None
    currency: str
    method: SspMethod
    value_basis: SspValueBasis
    quantity_unit: SspQuantityUnit | None
    unit_list_price: str | None
    midpoint_discount_ratio: str | None
    range_ratio: str | None
    cost_basis: str | None
    margin_ratio: str | None
    observable_point: str | None
    revenue_account_code: str | None
    distinctness: Distinctness
    ranges: list[SspRangeOut]


class SspEntriesOut(BaseModel):
    """The stored entries of an upsert, in request order."""

    entries: list[SspEntryOut]


class SspEntryKeyOut(BaseModel):
    """The T-REF-30 key of an entry."""

    product_code: str
    stratification: str
    region: str | None
    channel: str | None
    segment: str | None
    deal_size_band: str | None
    term_band: str | None
    currency: str


class SspEntryChangeOut(BaseModel):
    """A changed entry of the diff."""

    key: SspEntryKeyOut
    before: SspEntryOut
    after: SspEntryOut
    mid_change_ratio: str | None = Field(
        description="(after mid − before mid) ÷ before mid of the NONE band"
    )


class SspVersionDiffOut(BaseModel):
    """``GET /ssp-book-versions/{id}/diff?against=<version id>`` (04 §16.4)."""

    added: list[SspEntryOut]
    removed: list[SspEntryOut]
    changed: list[SspEntryChangeOut]


class SspResolutionVersionOut(BaseModel):
    """The version that answered a resolution."""

    id: uuid.UUID
    book_code: str
    version_no: int
    legacy_version_label: str | None


class SspPolicySourceOut(BaseModel):
    """A resolved POL-071 or POL-072 value with its level (T-PLT-32 resolution)."""

    value: Any
    level: str = Field(description="TENANT, ENTITY, BOOK or FRAMEWORK_DEFAULT")
    source_id: uuid.UUID | None


class SspPolicySourcesOut(BaseModel):
    inside_range_point: SspPolicySourceOut
    outside_range_point: SspPolicySourceOut


class SspResolutionOut(BaseModel):
    """API-S-SspResolution (``GET /ssp/resolve``; 04 §16.4): values extended by quantity."""

    ssp_book_version: SspResolutionVersionOut
    ssp_entry_id: uuid.UUID
    method: SspMethod
    low: str | None
    mid: str | None
    high: str | None
    stated_price: MoneyOut | None
    in_range: bool | None
    selected_ssp: str
    policy_sources: SspPolicySourcesOut
