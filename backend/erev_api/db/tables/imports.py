"""Import and exception tables (04 §11: T-IMP-01 to T-IMP-06; BUILD_SPEC CTR-5, DIN-1, DIN-10,
BS3-D-02).

Revision 0041 creates ``exception_item``, the shared exception queue, before the other T-IMP tables;
revision 0044 (DIN-1) creates the template registry, uploads, rows and row lineage, and the foreign
keys that name them (DG-MIG-03); revision 0052 (DIN-10) creates the mapping profiles and the foreign
key ``import_upload.mapping_profile_id``.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import CHAR, Boolean, Column, Integer, SmallInteger, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c_sc_m, _sc_v, _timestamp, principal_kind
from erev_api.enums import (
    ExceptionDisposition,
    ExceptionSeverity,
    ExceptionSource,
    ExceptionStatus,
    ImportRowStatus,
    ImportStatus,
)

# Created by revision 0041 (CTR-5): E-42, E-43, E-44, E-106.
exception_source: Final = _enum(ExceptionSource, "exception_source")
exception_severity: Final = _enum(ExceptionSeverity, "exception_severity")
exception_status: Final = _enum(ExceptionStatus, "exception_status")
exception_disposition: Final = _enum(ExceptionDisposition, "exception_disposition")
# Created by revision 0044 (DIN-1): E-40, E-41.
import_status: Final = _enum(ImportStatus, "import_status")
import_row_status: Final = _enum(ImportRowStatus, "import_row_status")

# T-IMP-01: the global template registry (IM-A, RLS-NONE-G), seeded by revision 0044.
import_template: Final = Table(
    "import_template",
    metadata,
    Column("code", Text(), primary_key=True),
    Column("version", Integer(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("family", Text(), nullable=False),
    Column("target_object", Text(), nullable=False),
    Column("file_format", Text(), nullable=False),
    Column("sheet_rule", Text(), nullable=False, server_default=text("'FIRST_SHEET'")),
    Column("header_match", Text(), nullable=False),
    Column("headers", JSONB(none_as_null=True), nullable=False),
    Column("required_parameters", JSONB(none_as_null=True), nullable=False, server_default="[]"),
    Column("row_model", Text(), nullable=False),
    Column("aggregation_rule", Text(), nullable=True),
    Column("is_current", Boolean(), nullable=False, server_default=text("true")),
)

# T-IMP-02: one uploaded file along E-40 (IM-S, RLS-T); DB-03 trigger of revision 0044, replaced
# by revision 0087 (``named_entity_ids``); revision 0102 adds ``uploader_scopes``.
import_upload: Final = Table(
    "import_upload",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("import_no", Text(), nullable=False),
    Column("template_code", Text(), nullable=False),
    Column("template_version", Integer(), nullable=False),
    Column("file_object_id", Uuid(), nullable=False),
    Column("file_sha256", CHAR(64), nullable=False),
    Column("parameters", JSONB(none_as_null=True), nullable=False, server_default="{}"),
    Column("mapping_profile_id", Uuid(), nullable=True),
    Column("status", import_status, nullable=False, server_default=text("'UPLOADED'")),
    Column("row_count", Integer(), nullable=True),
    Column("valid_row_count", Integer(), nullable=True),
    Column("warning_count", Integer(), nullable=True),
    Column("error_count", Integer(), nullable=True),
    Column("is_quarantine_mode", Boolean(), nullable=False, server_default=text("false")),
    Column("control_totals", JSONB(none_as_null=True), nullable=True),
    Column("diff_summary", JSONB(none_as_null=True), nullable=True),
    Column("diff_file_id", Uuid(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    _timestamp("committed_at"),
    Column("job_id", Uuid(), nullable=True),
    # 04 rev 1.107 (R-29; revision 0087): the legal entities the rows name, set once by the
    # validation job; NULL = unresolved (every entity), empty = a tenant-level upload.
    Column("named_entity_ids", ARRAY(Uuid()), nullable=True),
    # 04 rev 1.147 (rulings R-98, R-109 (a); revision 0102): the permission codes the access
    # token of an API client carried when it created the upload, written at INSERT and never
    # again; NULL for a person's upload.
    Column("uploader_scopes", ARRAY(Text()), nullable=True),
    *_sc_c_sc_m(),
)

# T-IMP-03: each data row as read and validated (IM-A, RLS-T).
import_row: Final = Table(
    "import_row",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("import_upload_id", Uuid(), nullable=False),
    Column("sheet_name", Text(), nullable=False),
    Column("row_number", Integer(), nullable=False),
    Column("raw", JSONB(none_as_null=True), nullable=False),
    Column("normalized", JSONB(none_as_null=True), nullable=True),
    Column("row_sha256", CHAR(64), nullable=False),
    Column("status", import_row_status, nullable=False),
    Column("business_key", Text(), nullable=True),
    Column("aggregated_into_row_id", Uuid(), nullable=True),
    _timestamp("created_at", nullable=False, now_default=True),
    Column("created_by", Uuid(), nullable=True),
    Column("created_by_kind", principal_kind, nullable=False),
)

# T-IMP-04: row-level lineage from a row to every object it emitted (IM-A, RLS-T).
import_row_lineage: Final = Table(
    "import_row_lineage",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("import_row_id", Uuid(), nullable=False),
    Column("import_upload_id", Uuid(), nullable=False),
    Column("target_type", Text(), nullable=False),
    Column("target_id", Uuid(), nullable=False),
    _timestamp("created_at", nullable=False, now_default=True),
    Column("created_by", Uuid(), nullable=True),
    Column("created_by_kind", principal_kind, nullable=False),
)

# T-IMP-05: the shared exception queue (IM-M, RLS-T plus the restrictive nullable entity policy).
exception_item: Final = Table(
    "exception_item",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("exception_no", Text(), nullable=False),
    Column("source", exception_source, nullable=False),
    Column("code", Text(), nullable=False),
    Column("severity", exception_severity, nullable=False),
    Column(
        "disposition", exception_disposition, nullable=False, server_default=text("'remediable'")
    ),
    Column("status", exception_status, nullable=False, server_default=text("'OPEN'")),
    Column("priority", SmallInteger(), nullable=False, server_default=text("3")),
    Column("title", Text(), nullable=False),
    Column("message", Text(), nullable=False),
    Column("suggestion", Text(), nullable=True),
    Column("field", Text(), nullable=True),
    Column("business_key", Text(), nullable=True),
    Column("source_payload", JSONB(none_as_null=True), nullable=True),
    Column("import_upload_id", Uuid(), nullable=True),
    Column("import_row_id", Uuid(), nullable=True),
    Column("sync_run_id", Uuid(), nullable=True),
    Column("source_record_id", Uuid(), nullable=True),
    Column("contract_id", Uuid(), nullable=True),
    Column("obligation_id", Uuid(), nullable=True),
    Column("combination_group_id", Uuid(), nullable=True),
    Column("entity_id", Uuid(), nullable=True),
    Column("period_id", Uuid(), nullable=True),
    Column("close_run_id", Uuid(), nullable=True),
    Column("journal_run_id", Uuid(), nullable=True),
    Column("owner_membership_id", Uuid(), nullable=True),
    Column("dedupe_key", Text(), nullable=False),
    Column("occurrence_count", Integer(), nullable=False, server_default=text("1")),
    _timestamp("last_seen_at", nullable=False, now_default=True),
    Column("resolution", Text(), nullable=True),
    _timestamp("resolved_at"),
    Column("resolved_by", Uuid(), nullable=True),
    Column("resolved_by_kind", principal_kind, nullable=True),
    Column("waiver_approval_request_id", Uuid(), nullable=True),
    _timestamp("reprocessed_at"),
    *_sc_c_sc_m(),
)

# T-IMP-06: versioned column mappings of CSV v2 imports (IM-P, SC-V, RLS-T); DB-04 trigger of
# revision 0052 (BUILD_SPEC DIN-10).
import_mapping_profile: Final = Table(
    "import_mapping_profile",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("template_code", Text(), nullable=False),
    Column("mappings", JSONB(none_as_null=True), nullable=False),
    *_sc_c_sc_m(),
    *_sc_v(),
)
