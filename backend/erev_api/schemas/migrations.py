"""API-R-48 migration schemas (04 §15.3 API-R-48; T-MIG-01 to T-MIG-03; E-75, E-76; SCREENS_B
§10.1 to §10.3; PRD J-20, J-21; BUILD_SPEC LMG-1 to LMG-4; lane record §25).

04 lists the API-R-48 routes and defines no API-S-Migration schema, so these models are the
F-LMG contract of the routes (lane record §2): ``MigrationCreateIn`` (``POST /migrations``),
``MigrationOut`` (T-MIG-01 columns, ``profile`` as ``MigrationProfileOut``),
``MigrationImportIn`` (``POST /migrations/{id}/import``: ``OpeningBalancesImportIn`` with the
cutover date, entity mapping and batch parameters, or ``ReplayImportIn`` with the ordered plan —
discriminated on ``mode``), ``MigrationReconciliationLineOut`` (T-MIG-03; ``GET
/migrations/{id}/reconciliation-lines``), ``MigratedLegacyRowOut`` (T-MIG-02; ``GET
/migrations/{id}/legacy-rows``) and ``MigrationSubmitIn`` (``POST
/migrations/{id}/submit-promotion``). Amounts are exact decimal strings (erev.exact); the legacy
row keeps its 71 legacy column names (D-33).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from erev_api.enums import MigrationMode, MigrationStatus
from erev_api.schemas.common import ActorOut, ProblemOut

__all__ = [
    "EntityDefaultsIn",
    "EntityMappingIn",
    "EntityMappingOut",
    "FieldMappingOut",
    "FieldMappingRowOut",
    "MigratedLegacyRowOut",
    "MigrationCreateIn",
    "MigrationImportIn",
    "MigrationOut",
    "MigrationProfileOut",
    "MigrationReconciliationLineOut",
    "MigrationSubmitIn",
    "OpeningBalancesImportIn",
    "ReplayImportIn",
    "ReplayPlanItemIn",
]

ExactText = Annotated[str, StringConstraints(pattern=r"^-?[0-9]+(\.[0-9]+)?$")]
Measure = Literal[
    "POB_COUNT",
    "TRANSACTION_PRICE",
    "ORIGINAL_ALLOCATION",
    "ALLOCATION",
    "REVENUE_CUM",
    "BILLED_CUM",
    "NET_POSITION",
    "RECLASS",
    "REMAINING_QTY",
]
TemplateCode = Literal[
    "legacy_sku_ssp",
    "legacy_contract_setup",
    "legacy_progress_tracking",
    "legacy_contract_modification",
]
TemplateMode = Literal["prospective", "retrospective", "pob_price_change"]


class FieldMappingRowOut(BaseModel):
    """One 04 §17.2 row as data (D-98 133 AMENDMENT 1 (b); 04 rev 1.66 API-R-48): the LM-CL id, the
    exact legacy column name, the eRev target text and the transformation rule — what SCREENS_B
    §10.3's read-only "Field mapping" table renders verbatim."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="LM-CL-nn (04 §17.2)")
    legacy_column: str = Field(description="The exact legacy Contract_Live column name")
    target: str = Field(description="The 04 §17.2 target (table.column) text")
    rule: str = Field(description="The 04 §17.2 transformation / export rule")


class FieldMappingOut(BaseModel):
    """``GET /migrations/field-mapping``: the 71 rows in legacy order (static content, tenant-scoped
    like the resource under ``migration.run``; no database row)."""

    model_config = ConfigDict(frozen=True)

    rows: list[FieldMappingRowOut]


class MigrationCreateIn(BaseModel):
    """``POST /migrations`` ``{mode, source_file_id}`` (SCREENS_B §10.2; T-PLT-29
    ``LEGACY_DATABASE``).
    """

    model_config = ConfigDict(extra="forbid")

    mode: MigrationMode
    source_file_id: uuid.UUID


class MigrationProfileOut(BaseModel):
    """T-MIG-01 ``profile`` (PRD J-20.1; SCREENS_B §10.3 "Key figures")."""

    source_sha256: str
    tables: dict[str, int]
    contract_live_rows: int
    contracts: int
    legacy_pob_rows: int
    sku_ssp_rows: int
    ssp_versions: list[str]
    selling_entities: list[str]
    latest_current_period: date | None
    version_tokens: list[str]


class MigrationOut(BaseModel):
    """API-S-Migration: the T-MIG-01 row (``GET /migrations/{id}``)."""

    id: uuid.UUID
    migration_no: str
    mode: MigrationMode
    status: MigrationStatus
    source_file_id: uuid.UUID
    source_sha256: str
    cutover_date: date | None
    sandbox_tenant_id: uuid.UUID | None
    profile: MigrationProfileOut | None
    import_upload_ids: list[uuid.UUID]
    registry_version_id: uuid.UUID | None
    reconciliation_report_run_id: uuid.UUID | None
    approval_request_id: uuid.UUID | None
    job_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    problem: ProblemOut | None
    # SCREENS_B §10.1 "Unexplained differences": T-MIG-03 lines outside tolerance without a
    # deviation reference (an exception link explains nothing; BR-MIG-02); None before a
    # reconciliation exists
    unexplained_count: int | None = None
    row_version: int  # API-C-08: the ETag is "r<row_version>" (IM-S, SC-M)
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime


class EntityMappingIn(BaseModel):
    """One "Entity mapping" row the user confirms (LM-CL-09): legacy text → entity code; for a
    "Will be created" row the inputs the mapping does not carry (04 §17.2 rev 1.64, D-98
    candidate 133): the fiscal calendar (else ``entity_defaults.calendar_id``, else the tenant's
    only calendar) and the IANA time zone (else ``entity_defaults.time_zone``). The functional
    currency is always the tenant reporting currency."""

    model_config = ConfigDict(extra="forbid")

    legacy_name: str
    entity_code: str
    calendar_id: uuid.UUID | None = None
    time_zone: str | None = Field(default=None, max_length=64)


class EntityDefaultsIn(BaseModel):
    """``entity_defaults`` of ``/import``: applied to every "Will be created" row without its own
    value (the row's own value wins)."""

    model_config = ConfigDict(extra="forbid")

    calendar_id: uuid.UUID | None = None
    time_zone: str | None = Field(default=None, max_length=64)


class EntityMappingOut(EntityMappingIn):
    status: Literal["Matched", "Will be created"]


class OpeningBalancesImportIn(BaseModel):
    """``/import`` for D-31 mode (a) (LMG-2; SCREENS_B §10.3 "Confirm mapping", "Run import")."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["OPENING_BALANCES"] = "OPENING_BALANCES"
    cutover_date: date
    entity_mapping: list[EntityMappingIn] = Field(default_factory=list)
    entity_defaults: EntityDefaultsIn | None = None  # 04 LM-CL-09 rev 1.64
    batch_parameters: dict[str, str] = Field(default_factory=dict)
    create_missing_entities: bool = True  # LM-CL-09 default for legacy templates
    create_missing_products: bool = True  # LM-CL-03 rev 1.64 (mirrors LM-SSP-02)


class ReplayPlanItemIn(BaseModel):
    """One replay plan row (LMG-4; SCREENS_B §10.3 "Replay plan")."""

    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID
    file_name: str
    template_code: TemplateCode
    mode: TemplateMode | None = None
    effective_date: date | None = None


class ReplayImportIn(BaseModel):
    """``/import`` for D-31 mode (b): the ordered plan (LMG-4; PRD J-21.1)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["REPLAY"] = "REPLAY"
    plan: list[ReplayPlanItemIn]


MigrationImportIn = Annotated[OpeningBalancesImportIn | ReplayImportIn, Field(discriminator="mode")]


class MigrationSubmitIn(BaseModel):
    """``POST /migrations/{id}/submit-promotion`` ``{comment}`` (``MIGRATION_PROMOTION``)."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = None


class MigrationReconciliationLineOut(BaseModel):
    """T-MIG-03 line (``GET /migrations/{id}/reconciliation-lines``; RPT-41 columns)."""

    id: uuid.UUID | None = None
    contract_external_id: str
    obligation_key: str | None
    measure: Measure
    source_value: ExactText
    erev_value: ExactText
    difference: ExactText
    tolerance: ExactText = "0.0001"
    is_within_tolerance: bool
    deviation_ref: str | None = None
    exception_item_id: uuid.UUID | None = None
    exception_no: str | None = None  # RPT-41 "Exception" column (SCREENS_B §5.6.7)


class MigratedLegacyRowOut(BaseModel):
    """T-MIG-02 row (``GET /migrations/{id}/legacy-rows``): the 71 legacy columns as stored."""

    id: uuid.UUID | None = None
    source_rowid: int
    contract_external_id: str
    obligation_key: str
    product_code: str
    current_period: date | None
    processing_time_log: str
    record_unique_id: str
    legacy_row: dict[str, Any]
    legacy_row_sha256: str
    contract_id: uuid.UUID | None = None
    obligation_id: uuid.UUID | None = None
    label: Literal["migrated, unattributed"] = "migrated, unattributed"
