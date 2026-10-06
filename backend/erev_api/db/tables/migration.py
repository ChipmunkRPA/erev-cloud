"""Legacy migration tables (04 §17 T-MIG-01 to T-MIG-05; BUILD_SPEC LMG-1, LMG-2; D-31; REQ-MIG-001
to REQ-MIG-006).

T-MIG-01 to T-MIG-03 are created by revision ``0056_lmg_t_mig_01_03`` (assigned at merge prep,
2026-09-20; lane record ``docs/reviews/loop/prod/F-LMG.md`` §16, §19) with the E-75 / E-76 types
and the DB-03 trigger of ``migration_batch``. T-MIG-04 ``migration_population_version`` and
T-MIG-05 ``migration_population_obligation`` (04 rev 1.60; D-98 candidates 122 and 126; record §24)
are created by revision ``0067_lmg_t_mig_04_05``: the DURABLE capture of the opening-balance
import's dry run — the dry run's engine rows roll back, so the ``*_id`` columns of the two tables
are identity TOKENS of rows that no longer exist (not references; excluded from the snapshot
copy's element-wise array-reference rule, D-98 candidate 106), and the trace mirror is the
evidence the reconcile rebuilds and hash-checks. DG-ARC-09 compares the column names with the 04
rows; 04 rev 1.35 adds ``ORIGINAL_ALLOCATION`` to the T-MIG-03 ``measure`` CHECK (D-98 candidate
48).
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Column,
    Date,
    Integer,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_c_sc_m, _timestamp
from erev_api.db.types import ExactType, MoneyType
from erev_api.enums import BookCode, MigrationMode, MigrationStatus

__all__ = [
    "LEGACY_ROW_LABEL",
    "MEASURES",
    "POPULATION_BOOK",
    "migrated_legacy_row",
    "migration_batch",
    "migration_mode",
    "migration_population_obligation",
    "migration_population_version",
    "migration_reconciliation_line",
    "migration_status",
]

# Created by revision 0056 (LMG-1): E-75, E-76.
migration_mode: Final = _enum(MigrationMode, "migration_mode")
migration_status: Final = _enum(MigrationStatus, "migration_status")
book_code_type: Final = _enum(BookCode, "book_code")
# 04 T-MIG-03 ``measure`` CHECK (rev 1.35; D-98 candidate 48), in 04 order.
MEASURES: Final = (
    "POB_COUNT",
    "TRANSACTION_PRICE",
    "ORIGINAL_ALLOCATION",
    "ALLOCATION",
    "REVENUE_CUM",
    "BILLED_CUM",
    "NET_POSITION",
    "RECLASS",
    "REMAINING_QTY",
)
LEGACY_ROW_LABEL: Final = "migrated, unattributed"  # 04 T-MIG-02 ``label`` CHECK (D-31 mode a)
POPULATION_BOOK: Final = "ASC606"  # 04 T-MIG-04 ``book_code`` CHECK: the legacy database's book

# T-MIG-01: one legacy database import in opening-balance or replay mode (IM-S, RLS-T; DB-03).
migration_batch: Final = Table(
    "migration_batch",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("migration_no", Text(), nullable=False),
    Column("mode", migration_mode, nullable=False),
    Column("status", migration_status, nullable=False, server_default=text("'UPLOADED'")),
    Column("source_file_id", Uuid(), nullable=False),
    Column("source_sha256", CHAR(64), nullable=False),
    Column("cutover_date", Date(), nullable=True),
    Column("sandbox_tenant_id", Uuid(), nullable=True),
    Column("profile", JSONB(none_as_null=True), nullable=True),
    Column(
        "import_upload_ids",
        ARRAY(Uuid()),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    ),
    Column("registry_version_id", Uuid(), nullable=True),
    Column("reconciliation_id", Uuid(), nullable=True),
    Column("reconciliation_report_run_id", Uuid(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    Column("problem", JSONB(none_as_null=True), nullable=True),
    # rev 1.60 (revision 0067): the import's durable operation identity — a token, not a reference
    Column("capture_operation_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
)

# T-MIG-02: the migrated Contract_Live history, labelled "migrated, unattributed" (IM-A, RLS-T).
migrated_legacy_row: Final = Table(
    "migrated_legacy_row",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("migration_batch_id", Uuid(), nullable=False),
    Column("source_rowid", BigInteger(), nullable=False),
    Column("contract_external_id", Text(), nullable=False),
    Column("obligation_key", Text(), nullable=False),
    Column("product_code", Text(), nullable=False),
    Column("current_period", Date(), nullable=True),
    Column("processing_time_log", Text(), nullable=False),
    Column("record_unique_id", Text(), nullable=False),
    Column("legacy_row", JSONB(none_as_null=True), nullable=False),
    Column("legacy_row_sha256", CHAR(64), nullable=False),
    Column("contract_id", Uuid(), nullable=True),
    Column("obligation_id", Uuid(), nullable=True),
    Column("label", Text(), nullable=False, server_default=text("'migrated, unattributed'")),
    *_sc_c(),
)

# T-MIG-03: one reconciliation line per contract or obligation and measure (IM-A, RLS-T).
migration_reconciliation_line: Final = Table(
    "migration_reconciliation_line",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("migration_batch_id", Uuid(), nullable=False),
    Column("contract_external_id", Text(), nullable=False),
    Column("obligation_key", Text(), nullable=True),
    Column("measure", Text(), nullable=False),
    Column("source_value", ExactType(), nullable=False),
    Column("erev_value", ExactType(), nullable=False),
    Column("difference", ExactType(), nullable=False),
    Column("tolerance", ExactType(), nullable=False, server_default=text("0.0001")),
    Column("is_within_tolerance", Boolean(), nullable=False),
    Column("deviation_ref", Text(), nullable=True),
    Column("exception_item_id", Uuid(), nullable=True),
    *_sc_c(),
)

# T-MIG-04: one captured contract version of the import's dry run (IM-A, RLS-T; rev 1.60). The
# ``*_id`` columns other than ``migration_batch_id`` are identity tokens of rolled-back rows.
migration_population_version: Final = Table(
    "migration_population_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("migration_batch_id", Uuid(), nullable=False),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("version_no", Integer(), nullable=False),
    Column(
        "book_code", book_code_type, nullable=False
    ),  # the erev.book_code ENUM (batch #5 return)
    Column("combination_group_id", Uuid(), nullable=False),
    Column("status_in_book", Text(), nullable=False),
    Column("contract_computation_id", Uuid(), nullable=False),
    Column("input_sha256", CHAR(64), nullable=False),
    Column("output_sha256", CHAR(64), nullable=False),
    Column("engine_version", Text(), nullable=False),
    Column("engine_release_id", Uuid(), nullable=True),
    _timestamp("known_at", nullable=False),
    _timestamp("bundle_known_at", nullable=False),
    Column("cutover_date", Date(), nullable=False),
    Column("payload_migration_batch_id", Uuid(), nullable=False),
    Column("opening_event_id", Uuid(), nullable=False),
    Column("opening_event_key", Text(), nullable=False),
    Column("opening_event_binding_sha256", CHAR(64), nullable=False),
    Column("members", JSONB(), nullable=False),
    Column("expected_output_captured", Boolean(), nullable=False),
    Column(
        "obligation_version_ids",
        ARRAY(Uuid()),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    ),
    Column("capture_operation_id", Uuid(), nullable=False),
    Column("calc_trace_id", Uuid(), nullable=False),
    Column("format_version", SmallInteger(), nullable=False, server_default=text("1")),
    Column("node_count", Integer(), nullable=False),
    Column("root_measures", JSONB(), nullable=False),
    Column("trace_sha256", CHAR(64), nullable=False),
    Column("trace", JSONB(), nullable=False),
    # rev 1.60 (Codex 0515 R1): the producing bundle's T-CON-25 input evidence, recomputable later
    Column("input_evidence", JSONB(), nullable=False),
    Column("input_evidence_sha256", CHAR(64), nullable=False),
    *_sc_c(),
)

# T-MIG-05: one captured obligation version of a T-MIG-04 row (IM-A, RLS-T; rev 1.60): the nine
# T-MIG-03 measure sources as ``obligation_version`` stores them, the trace-node binding, the row.
migration_population_obligation: Final = Table(
    "migration_population_obligation",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("migration_batch_id", Uuid(), nullable=False),
    Column("population_version_id", Uuid(), nullable=False),
    Column("capture_operation_id", Uuid(), nullable=False),
    Column("contract_version_id", Uuid(), nullable=False),
    Column("obligation_version_id", Uuid(), nullable=False),
    Column("contract_id", Uuid(), nullable=False),
    Column("contract_external_id", Text(), nullable=False),
    Column("obligation_key", Text(), nullable=False),
    Column("obligation_kind", Text(), nullable=False),
    Column("original_allocated_exact", ExactType(), nullable=False),
    Column("remaining_quantity", ExactType(), nullable=False),
    Column("billed_cum", MoneyType(), nullable=False),
    Column("revenue_cum", MoneyType(), nullable=False),
    Column("remaining_allocation", MoneyType(), nullable=False),
    Column("position_obligation", MoneyType(), nullable=False),
    Column("netting_reclass_amount", MoneyType(), nullable=False),
    Column("trace_nodes", JSONB(), nullable=False),
    Column("row", JSONB(), nullable=False),
    Column("row_sha256", CHAR(64), nullable=False),
    *_sc_c(),
)
