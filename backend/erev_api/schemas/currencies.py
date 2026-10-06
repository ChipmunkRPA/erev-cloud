"""API-R-19 currency and FX schemas (04 §15.3 API-R-19, T-REF-08 to T-REF-12, E-12, E-51, API-C-06;
BUILD_SPEC RFD-3).

04 §16 defines no currency or FX schema. The members follow the table columns plus ``created_at``,
``updated_at`` and ``row_version``, as the calendar, account and entity schemas do (L1-1-Q-26).
Rates arrive as API-C-06 rate strings and leave as their stored ``NUMERIC(28,12)`` string with
twelve places, which the RFD-3 acceptance names (``"1.105000000000"``; L1-1-Q-27).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import ConfigStatus, RateType
from erev_api.money import CurrencyCode, RateStr
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

PERIOD_KEY_LENGTH: Final = 16
# [J] One version holds at most this many entered rates; a 1 MiB body holds about 8,000 (API-C-17).
MAX_RATES: Final = 5000
MAX_TENANT_CURRENCIES: Final = 200


class CurrencyOut(BaseModel):
    """A T-REF-08 ISO 4217 currency."""

    code: str
    numeric_code: str
    name: str
    minor_unit: int
    is_active: bool


class TenantCurrencyOut(BaseModel):
    """A T-REF-09 row with its currency's name and minor unit."""

    currency_code: str
    name: str
    minor_unit: int
    is_enabled: bool
    is_reporting_currency: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class TenantCurrenciesIn(BaseModel):
    """``PUT /tenant-currencies``: the currencies enabled from now on; every other tenant currency
    is disabled, and the reporting currency stays enabled (T-REF-09)."""

    model_config = ConfigDict(extra="forbid")

    currency_codes: list[CurrencyCode] = Field(min_length=1, max_length=MAX_TENANT_CURRENCIES)


class FxRateSetIn(BaseModel):
    """``POST /fx-rate-sets``: a T-REF-10 rate series."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    rate_type: RateType
    source: str = Field(
        default="MANUAL",
        max_length=CODE_LENGTH,
        description="MANUAL, CSV_IMPORT or a provider code",
    )


class FxRateSetOut(BaseModel):
    """A T-REF-10 rate set."""

    id: uuid.UUID
    code: str
    name: str
    rate_type: RateType
    source: str
    created_at: datetime
    updated_at: datetime
    row_version: int


class FxRateIn(BaseModel):
    """One entered rate: 1 ``base_currency`` = ``rate`` ``quote_currency`` (T-REF-12). A spot rate
    names its day; a closing or average rate names its period, whose end date is the effective
    date."""

    model_config = ConfigDict(extra="forbid")

    base_currency: CurrencyCode
    quote_currency: CurrencyCode
    rate: RateStr
    effective_date: date | None = Field(default=None, description="Spot: the day of the rate")
    period_key: str | None = Field(
        default=None, max_length=PERIOD_KEY_LENGTH, description="Closing and average: the period"
    )


class FxRateSetVersionIn(BaseModel):
    """``POST /fx-rate-sets/{id}/versions``: a DRAFT version and its entered rates."""

    model_config = ConfigDict(extra="forbid")

    coverage_from: date
    coverage_to: date
    rates: list[FxRateIn] = Field(default_factory=list, max_length=MAX_RATES)


class FxRateSetVersionUpdateIn(BaseModel):
    """``PATCH /fx-rate-set-versions/{id}``: the members sent replace the stored values; ``rates``
    replaces every entered rate of the DRAFT version."""

    model_config = ConfigDict(extra="forbid")

    coverage_from: date | None = None
    coverage_to: date | None = None
    rates: list[FxRateIn] | None = Field(default=None, max_length=MAX_RATES)


class FxRateSetVersionCommandIn(BaseModel):
    """``POST /fx-rate-set-versions/{id}/submit`` and ``/withdraw``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class FxRateOut(BaseModel):
    """A T-REF-12 rate of a version."""

    id: uuid.UUID
    rate_type: RateType
    base_currency: str
    quote_currency: str
    effective_date: date
    period_id: uuid.UUID | None
    period_key: str | None
    rate: str = Field(description="NUMERIC(28,12) string with twelve places")
    is_derived: bool


class FxRateSetVersionOut(BaseModel):
    """A T-REF-11 version with its pending approval request."""

    id: uuid.UUID
    fx_rate_set_id: uuid.UUID
    fx_rate_set_code: str
    rate_type: RateType
    version_no: int
    status: ConfigStatus
    coverage_from: date
    coverage_to: date
    rate_count: int
    import_upload_id: uuid.UUID | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    pending_approval_request_id: uuid.UUID | None
    published_at: datetime | None
    published_by: uuid.UUID | None
    created_at: datetime
    created_by: uuid.UUID | None
    updated_at: datetime
    row_version: int


class FxRateSetVersionDetailOut(FxRateSetVersionOut):
    """A version with every rate it holds, derived inverses included."""

    rates: list[FxRateOut]


class EffectiveFxRateOut(BaseModel):
    """``GET /fx-rates``: a rate in force, from the highest APPROVED version of its set whose
    coverage contains the date (T-REF-11)."""

    id: uuid.UUID
    rate_type: RateType
    base_currency: str
    quote_currency: str
    effective_date: date
    period_id: uuid.UUID | None
    period_key: str | None
    rate: str = Field(description="NUMERIC(28,12) string with twelve places")
    is_derived: bool
    fx_rate_set_id: uuid.UUID
    fx_rate_set_code: str
    fx_rate_set_version_id: uuid.UUID
    version_no: int
    published_at: datetime | None
