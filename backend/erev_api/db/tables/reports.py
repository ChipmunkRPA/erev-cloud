"""Report tables (04 §10 T-RPT-01 to T-RPT-04; BUILD_SPEC RPS-1).

The RPS-1 revision creates the global report catalogue, report runs, disclosure snapshots and
evidence packs. The catalogue and snapshots are IM-A (DB-01); runs and packs are IM-S (DB-03,
generated from ``TRANSITIONS``).
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import CHAR, BigInteger, Boolean, Column, Date, Integer, Table, Text, Uuid
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_c_sc_m, _timestamp
from erev_api.enums import BookCode, DisclosureKind, EvidencePackKind, RunStatus

# E-02 and E-67 of earlier revisions, bound here again so that this module does not depend on
# ``tables.reference`` while ``tables/__init__`` is importing.
book_code_type: Final = _enum(BookCode, "book_code")
run_status_type: Final = _enum(RunStatus, "run_status")
# Created by the RPS-1 revision: E-65 and E-66.
disclosure_kind: Final = _enum(DisclosureKind, "disclosure_kind")
evidence_pack_kind: Final = _enum(EvidencePackKind, "evidence_pack_kind")

# T-RPT-01: global, versioned standard report catalogue (IM-A, RLS-NONE-G); seeded by its revision.
report_definition: Final = Table(
    "report_definition",
    metadata,
    Column("code", Text(), primary_key=True),
    Column("version", Integer(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("kind", Text(), nullable=False),
    Column("description", Text(), nullable=False),
    Column("parameters_schema", JSONB(), nullable=False),
    Column("output_formats", ARRAY(Text()), nullable=False),
    Column("ipe_logic", JSONB(), nullable=False),
    Column("tie_outs", ARRAY(Text()), nullable=False, server_default=sql_text("'{}'")),
    Column("is_current", Boolean(), nullable=False, server_default=sql_text("true")),
)

# T-RPT-02: IPE-grade report and export run record (IM-S, RLS-T); DB-03, immutable once finished.
report_run: Final = Table(
    "report_run",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("report_run_no", Text(), nullable=False),
    Column("report_code", Text(), nullable=False),
    Column("report_version", Integer(), nullable=False),
    Column("status", run_status_type, nullable=False, server_default=sql_text("'QUEUED'")),
    Column("parameters", JSONB(), nullable=False),
    Column("entity_ids", ARRAY(Uuid()), nullable=False),
    Column("book_code", book_code_type, nullable=True),
    Column("as_of_date", Date(), nullable=True),
    _timestamp("known_at", nullable=False),
    Column("period_lock_id", Uuid(), nullable=True),
    Column("engine_release_id", Uuid(), nullable=False),
    Column("output_format", Text(), nullable=False),
    Column("output_file_id", Uuid(), nullable=True),
    Column("output_sha256", CHAR(64), nullable=True),
    Column("manifest_file_id", Uuid(), nullable=True),
    Column("row_count", BigInteger(), nullable=True),
    Column("control_totals", JSONB(none_as_null=True), nullable=True),
    Column("tie_out_results", JSONB(none_as_null=True), nullable=True),
    Column("ledger_heads", JSONB(none_as_null=True), nullable=True),
    # frps3b (04 T-RPT-02 rev 1.55; S15-R-24): the sources a live run's build consumed, written
    # once at SUCCEEDED; NULL for an as-locked run and for a run created before the binding.
    Column("source_binding", JSONB(none_as_null=True), nullable=True),
    Column("child_report_run_ids", ARRAY(Uuid()), nullable=False, server_default=sql_text("'{}'")),
    Column(
        "disclosure_snapshot_ids", ARRAY(Uuid()), nullable=False, server_default=sql_text("'{}'")
    ),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    Column("problem", JSONB(none_as_null=True), nullable=True),
    *_sc_c_sc_m(),
)

# T-RPT-03: frozen disclosure dataset per entity, book and period (IM-A, RLS-TE on entity_id).
disclosure_snapshot: Final = Table(
    "disclosure_snapshot",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("disclosure_kind", disclosure_kind, nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("period_lock_id", Uuid(), nullable=True),
    Column("report_run_id", Uuid(), nullable=False),
    Column("data", JSONB(), nullable=False),
    Column("data_sha256", CHAR(64), nullable=False),
    *_sc_c(),
)

# T-RPT-04: period and contract sample evidence packs with manifest (IM-S, RLS-T); DB-03, frozen
# once SUCCEEDED; the four kind checks of rev 1.2.
evidence_pack: Final = Table(
    "evidence_pack",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("pack_no", Text(), nullable=False),
    Column("source_binding", JSONB(none_as_null=True), nullable=True),
    Column("kind", evidence_pack_kind, nullable=False),
    Column("entity_id", Uuid(), nullable=True),
    Column("book_code", book_code_type, nullable=True),
    Column("period_id", Uuid(), nullable=True),
    Column("period_lock_id", Uuid(), nullable=True),
    Column("contract_ids", ARRAY(Uuid()), nullable=False, server_default=sql_text("'{}'")),
    Column("as_of_date", Date(), nullable=True),
    Column("from_date", Date(), nullable=True),
    Column("to_date", Date(), nullable=True),
    Column("status", run_status_type, nullable=False, server_default=sql_text("'QUEUED'")),
    Column("manifest", JSONB(none_as_null=True), nullable=True),
    Column("manifest_sha256", CHAR(64), nullable=True),
    Column("file_id", Uuid(), nullable=True),
    Column("report_run_ids", ARRAY(Uuid()), nullable=False, server_default=sql_text("'{}'")),
    Column("job_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
)
