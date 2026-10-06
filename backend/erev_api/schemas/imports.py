"""API-R-43 import schemas (04 §15.3 API-R-43, §16.6 API-S-ImportTemplate, API-S-ImportCreate,
API-S-Import, API-S-ImportRow; T-IMP-01 to T-IMP-04; BUILD_SPEC DIN-1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from erev_api.enums import (
    ConfigStatus,
    HeaderMatchKind,
    ImportDiffChange,
    ImportRowStatus,
    ImportStatus,
)
from erev_api.schemas.common import ActorOut

__all__ = [
    "FindingCountOut",
    "HeaderMatchOut",
    "ImportCountsOut",
    "ImportCreateIn",
    "ImportDiffCountsOut",
    "ImportDiffItemOut",
    "ImportDiffOut",
    "ImportFileOut",
    "ImportOut",
    "ImportRowLineageOut",
    "ImportRowMessageOut",
    "ImportRowOut",
    "ImportSubmitIn",
    "ImportTemplateHeaderOut",
    "ImportTemplateOut",
    "ImportTemplateParameterOut",
    "ImportTemplateRefOut",
    "MappingProfileIn",
    "MappingProfileMappingsIn",
    "MappingProfileMappingsOut",
    "MappingProfileOut",
    "MappingProfileSubmitIn",
    "MappingProfileUpdateIn",
]

FindingSeverity = Literal["ERROR", "WARNING", "INFO"]
TemplateCode = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ImportTemplateHeaderOut(BaseModel):
    """A template column: ``{name, type, required, rule_ids}`` (T-IMP-01 ``headers``)."""

    name: str
    type: str
    required: bool
    rule_ids: list[str]


class ImportTemplateParameterOut(BaseModel):
    """A parameter the upload must carry (T-IMP-01 ``required_parameters``)."""

    name: str
    type: str
    allowed_values: list[str] | None


class ImportTemplateOut(BaseModel):
    """API-S-ImportTemplate (``GET /import-templates``)."""

    code: str
    version: int
    name: str
    family: Literal["LEGACY_V1", "CSV_V2"]
    file_format: Literal["XLSX", "CSV"]
    headers: list[ImportTemplateHeaderOut]
    required_parameters: list[ImportTemplateParameterOut]
    download_href: str = Field(
        description="Blank template with example rows and column definitions (REQ-DAT-016)"
    )


class ImportCreateIn(BaseModel):
    """API-S-ImportCreate (``POST /imports``): the file is uploaded first with ``POST /files``,
    purpose ``IMPORT_SOURCE``."""

    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID
    template_code: TemplateCode
    template_version: int | None = Field(default=None, ge=1, description="Default current")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "effective_date for the progress and modification templates; mode (prospective, "
            "retrospective, pob_price_change) for the modification template"
        ),
    )
    mapping_profile_id: uuid.UUID | None = Field(default=None, description="CSV_V2 only")
    forecast_event_set_id: uuid.UUID | None = Field(
        default=None, description="Scenario tenants only"
    )


class ImportTemplateRefOut(BaseModel):
    code: str
    version: int
    name: str


class ImportFileOut(BaseModel):
    id: uuid.UUID
    original_filename: str | None
    sha256: str
    size_bytes: int


class ImportCountsOut(BaseModel):
    """Data rows by status; null before validation."""

    rows: int | None
    valid: int | None
    warnings: int | None
    errors: int | None
    aggregated: int
    blank: int


class FindingCountOut(BaseModel):
    """Row messages grouped by §15.4 code and finding severity, with the number of distinct rows."""

    code: str
    severity: FindingSeverity
    rows: int


class HeaderMatchOut(BaseModel):
    source_column: str
    samples: list[str]
    template_field: str | None
    match: HeaderMatchKind
    alias_profile_code: str | None


class ImportOut(BaseModel):
    """API-S-Import (``GET /imports/{id}``)."""

    id: uuid.UUID
    import_no: str
    template: ImportTemplateRefOut
    file: ImportFileOut
    parameters: dict[str, Any]
    status: ImportStatus
    counts: ImportCountsOut
    is_quarantine_mode: bool
    control_totals: dict[str, Any] | None
    finding_counts: list[FindingCountOut]
    header_match: list[HeaderMatchOut]
    diff_summary: dict[str, Any] | None
    approval_request_id: uuid.UUID | None
    committed_at: datetime | None
    exceptions_href: str
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime


class ImportRowMessageOut(BaseModel):
    """A row message from an exception item of the row; ``severity`` is the finding severity."""

    rule_id: str
    severity: FindingSeverity
    field: str | None
    message: str


class ImportRowLineageOut(BaseModel):
    target_type: str
    target_id: uuid.UUID


class ImportRowOut(BaseModel):
    """API-S-ImportRow (``GET /imports/{id}/rows``)."""

    id: uuid.UUID
    sheet_name: str
    row_number: int
    status: ImportRowStatus
    business_key: str | None
    raw: dict[str, Any]
    normalized: dict[str, Any] | None
    messages: list[ImportRowMessageOut]
    aggregated_into_row_id: uuid.UUID | None
    lineage: list[ImportRowLineageOut]


class ImportSubmitIn(BaseModel):
    """``POST /imports/{id}/submit`` (04 §16.6 import commands)."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=2000)


class ImportDiffCountsOut(BaseModel):
    contracts_added: int
    contracts_changed: int
    obligations_added: int
    obligations_changed: int


class ImportDiffItemOut(BaseModel):
    """One change of the dry run; values are strings (API-C-06)."""

    change: ImportDiffChange
    contract_external_id: str
    obligation_key: str | None
    measure: str
    before: str | None
    after: str | None


class ImportDiffOut(BaseModel):
    """API-S-ImportDiff (``GET /imports/{id}/diff``)."""

    summary_counts: ImportDiffCountsOut
    items: list[ImportDiffItemOut]
    next_cursor: str | None


# --- mapping profiles (04 T-IMP-06; BUILD_SPEC DIN-10) -------------------------------------------

ColumnName = Annotated[str, StringConstraints(min_length=1, max_length=200)]
ConstantValue = str | int | float | bool


class MappingProfileMappingsIn(BaseModel):
    """T-IMP-06 ``mappings``: ``{aliases: {source column → template column}, constants: {template
    column → value}, custom_attributes: [source columns]}``."""

    model_config = ConfigDict(extra="forbid")

    aliases: dict[ColumnName, ColumnName] = Field(default_factory=dict, max_length=200)
    constants: dict[ColumnName, ConstantValue] = Field(default_factory=dict, max_length=200)
    custom_attributes: list[ColumnName] = Field(default_factory=list, max_length=50)


class MappingProfileIn(BaseModel):
    """``POST /import-mapping-profiles``: the next version of a profile code, as DRAFT."""

    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,63}$")]
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    template_code: TemplateCode
    mappings: MappingProfileMappingsIn
    effective_from: AwareDatetime | None = None


class MappingProfileUpdateIn(BaseModel):
    """``PATCH /import-mapping-profiles/{id}`` with ``If-Match`` while DRAFT or TESTED."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    mappings: MappingProfileMappingsIn | None = None
    effective_from: AwareDatetime | None = None


class MappingProfileSubmitIn(BaseModel):
    """``POST /import-mapping-profiles/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=2000)


class MappingProfileMappingsOut(BaseModel):
    aliases: dict[str, str]
    constants: dict[str, Any]
    custom_attributes: list[str]


class MappingProfileOut(BaseModel):
    """One mapping profile version: the T-IMP-06 columns and the SC-V lifecycle members."""

    id: uuid.UUID
    code: str
    name: str
    template_code: str
    mappings: MappingProfileMappingsOut
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    effective_to: datetime | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    published_at: datetime | None
    published_by: uuid.UUID | None
    supersedes_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    row_version: int
