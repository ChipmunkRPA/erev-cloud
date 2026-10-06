"""API-R-24 obligation template schemas (04 §15.3 API-R-24, T-REF-22, T-REF-23, §16.2
API-S-VersionSummary, §16.14 list additions; SCREENS §11.2 template version editor; BUILD_SPEC
RFD-10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import (
    ConfigStatus,
    Distinctness,
    LicenceNature,
    ObligationKind,
    OverTimeCriterion,
    PrincipalAgent,
    RatableConvention,
    RecognitionMethod,
    SatisfactionPattern,
    WarrantyType,
)
from erev_api.schemas.rule_sets import CODE_LENGTH, CODE_PATTERN, CaseEvidenceOut, VersionSummaryOut
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

INTEGER_MAX: Final = 2_147_483_647  # T-REF-23 `term_months integer`

# 04 T-REF-23 checks.
SeriesIncrementUnit = Literal["day", "month", "transaction", "unit"]
StartDateRule = Literal[
    "LINE_START", "BOOKING_DATE", "CONTROL_TRANSFER", "FIRST_USAGE", "LICENCE_START_OR_AVAILABLE"
]
EndDateRule = Literal["LINE_END", "START_PLUS_TERM", "NONE"]


class PobTemplateIn(BaseModel):
    """``POST /pob-templates``: the identity of an obligation template (T-REF-22)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH, pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PobTemplateOut(BaseModel):
    """API-S-PobTemplate: the T-REF-22 columns with ``current_version`` (the latest PUBLISHED
    version) and ``latest_version`` (the highest ``version_no``)."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    current_version: VersionSummaryOut | None
    latest_version: VersionSummaryOut | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class PobTemplateOutputsIn(BaseModel):
    """The T-REF-23 outputs a request sets; members left out keep their value (the column default,
    the copied version's value or the stored value)."""

    model_config = ConfigDict(extra="forbid")

    obligation_kind: ObligationKind | None = None
    distinctness: Distinctness | None = None
    series_increment_unit: SeriesIncrementUnit | None = None
    satisfaction_pattern: SatisfactionPattern | None = None
    over_time_criterion: OverTimeCriterion | None = None
    recognition_method: RecognitionMethod | None = None
    ratable_convention: RatableConvention | None = None
    start_date_rule: StartDateRule | None = None
    end_date_rule: EndDateRule | None = None
    term_months: int | None = Field(default=None, ge=-INTEGER_MAX, le=INTEGER_MAX)
    principal_agent: PrincipalAgent | None = None
    warranty_type: WarrantyType | None = None
    licence_nature: LicenceNature | None = None
    sfc_assessment_required: bool | None = None
    revenue_category: str | None = Field(default=None, max_length=CODE_LENGTH)
    disaggregation: dict[str, Any] | None = None
    account_role_overrides: dict[str, uuid.UUID] | None = None
    stratification_label: str | None = Field(default=None, max_length=LABEL_LENGTH)
    is_excluded_from_netting_attribution: bool | None = None
    policy_values: dict[str, Any] | None = None


class PobTemplateVersionIn(PobTemplateOutputsIn):
    """``POST /pob-templates/{id}/versions``: the next version as DRAFT; ``source_version_id``
    copies the outputs and example cases of that version of the template."""

    effective_from: AwareDatetime | None = None
    source_version_id: uuid.UUID | None = None


class PobTemplateVersionUpdateIn(PobTemplateOutputsIn):
    """``PATCH /pob-template-versions/{id}`` with ``If-Match`` while the version is DRAFT or
    TESTED."""

    effective_from: AwareDatetime | None = None


class PobTemplateVersionSubmitIn(BaseModel):
    """``POST /pob-template-versions/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PobTemplateVersionOut(BaseModel):
    """API-S-PobTemplateVersion: the T-REF-23 and SC-V columns with the template's code, the test
    evidence of its example cases and its pending approval request (L2-1-Q-43)."""

    id: uuid.UUID
    pob_template_id: uuid.UUID
    template_code: str
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    effective_to: datetime | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    pending_approval_request_id: uuid.UUID | None
    published_at: datetime | None
    published_by: uuid.UUID | None
    supersedes_version_id: uuid.UUID | None
    obligation_kind: ObligationKind
    distinctness: Distinctness
    series_increment_unit: SeriesIncrementUnit | None
    satisfaction_pattern: SatisfactionPattern
    over_time_criterion: OverTimeCriterion
    recognition_method: RecognitionMethod
    ratable_convention: RatableConvention | None
    start_date_rule: StartDateRule
    end_date_rule: EndDateRule
    term_months: int | None
    principal_agent: PrincipalAgent
    warranty_type: WarrantyType
    licence_nature: LicenceNature
    sfc_assessment_required: bool
    revenue_category: str | None
    disaggregation: dict[str, Any]
    account_role_overrides: dict[str, uuid.UUID]
    stratification_label: str | None
    is_excluded_from_netting_attribution: bool
    policy_values: dict[str, Any]
    test_evidence: CaseEvidenceOut
    created_at: datetime
    created_by: uuid.UUID | None
    updated_at: datetime
    row_version: int
