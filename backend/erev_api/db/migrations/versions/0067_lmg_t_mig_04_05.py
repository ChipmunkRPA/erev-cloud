"""BUILD_SPEC item LMG-2 (MIGRATION_IMPORT durable capture): T-MIG-04, T-MIG-05 and the T-MIG-01
``capture_operation_id`` column.

Creates ``migration_population_version`` (04 T-MIG-04) and ``migration_population_obligation``
(04 T-MIG-05; both rev 1.60, D-98 candidates 122 and 126; lane F-LMG record
``docs/reviews/loop/prod/F-LMG.md`` §24): the DURABLE capture of the opening-balance import's dry
run — one row per computed contract version (identities as tokens of the rolled-back rows, the
computation's provenance, the cutover and batch id read back from the
``OPENING_BALANCE_ESTABLISHED`` input, the authoritative member contracts, the expected
``obligation_version_ids`` — possibly empty — and the calc-trace mirror) and one row per captured
obligation version (the nine T-MIG-03 measure sources as ``obligation_version`` stores them,
``trace_nodes``, the full row and its hash).

Both tables are IM-A (DB-01) and RLS-T; the foreign keys are the tenant FKs to T-MIG-01
(``migration_batch_id``, ``payload_migration_batch_id``) and, for T-MIG-05, to T-MIG-04 — every
other ``*_id`` column names a row the dry run rolled back and is NOT a reference (D-98 candidate 106
exclusion). T-MIG-01 gains ``capture_operation_id`` (uuid, NULL; the import's durable operation
identity, IM-S updatable): the column joins the ``erev_app`` UPDATE grant and the DB-03 transition
trigger function ``tg_migration_batch__transition()`` is REPLACED with the body that lists it
(``CREATE OR REPLACE`` keeps the trigger and grants — the 0065 precedent); the downgrade restores
the 0056 body. Amended in place before landing (slice LMG-API-1; D-98 candidate 128; 04 rev 1.60
in place): T-MIG-01 ``cutover_date`` becomes SET-ONCE (the opening-balances cutover is captured at
``POST /migrations/{id}/import``, not at creation) — the CHECK ``ck_migration_batch__cutover`` is
REPLACED by ``(mode = 'REPLAY' AND cutover_date IS NULL) OR mode = 'OPENING_BALANCES'``, the column
joins the ``erev_app`` UPDATE grant, and the transition body lists it as updatable and set once;
the downgrade restores the 0056 CHECK and body ONLY when no OPENING_BALANCES row carries a NULL
cutover — otherwise it is refused by name (``EREV-MIG-0067``): no date is synthesized and no row
is deleted (Codex 0727). D-98 128 AMENDMENT 1 (integrated batch #6 ci; dev-guide 1.60 DG-MIG-13):
the refusal is raised from the constraint validation itself inside the restoring ``DO`` block —
the earlier ``IF EXISTS`` predicate ran on the owner connection over a FORCE-RLS table and saw no
rows — and propagates so the whole revision transaction rolls back. Revision number 0067 assigned
by the supervisor on
2026-09-20; ``down_revision`` was ``0065`` while lane F-SNP's 0066 (T-PLT-47) was not on main and
was re-pointed to ``0066`` at the single main merge after F-SNP landed (main fe8e85df,
2026-09-21) — the ENG-C6 0064 precedent, never two heads on main.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

BATCH = "migration_batch"
APP_ROLE = "erev_app"
SIGNATURE = "tg_migration_batch__transition()"
# 04 T-MIG-01 ``cutover_date`` (rev 1.60 in place; D-98 candidate 128) and the 0056 text it
# replaces.
CUTOVER_CHECK = "ck_migration_batch__cutover"
CUTOVER_CHECK_SQL = "(mode = 'REPLAY' AND cutover_date IS NULL) OR mode = 'OPENING_BALANCES'"
CUTOVER_CHECK_SQL_0056 = "(mode = 'OPENING_BALANCES') = (cutover_date IS NOT NULL)"
# A constant statement (no interpolation): the 0056 CHECK is restored INSIDE the block and only
# over rows it admits — the constraint validation itself is the guard (D-98 128 AMENDMENT 1;
# dev-guide 1.60 DG-MIG-13): an EXISTS over erev.migration_batch on the owner connection sees no
# rows (FORCE ROW LEVEL SECURITY, no tenant context) while ADD CONSTRAINT scans every physical row,
# so the earlier predicate was blind and the designed refusal surfaced as a raw CheckViolation
# (integrated batch #6 ci). Only that check_violation is translated into the named refusal; the
# RAISE propagates so the whole revision transaction rolls back (transaction_per_migration) —
# the capture-table drops and the function change above included; compatible data keeps the
# original effect. No date is synthesized, no row deleted, RLS and roles untouched.
DOWNGRADE_RESTORE = """
DO $$
BEGIN
  ALTER TABLE erev.migration_batch DROP CONSTRAINT ck_migration_batch__cutover;
  ALTER TABLE erev.migration_batch ADD CONSTRAINT ck_migration_batch__cutover
    CHECK ((mode = 'OPENING_BALANCES') = (cutover_date IS NOT NULL));
EXCEPTION
  WHEN check_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'EREV-MIG-0067: OPENING_BALANCES migrations without a cutover date exist; the 0056 '
                'CHECK cannot be restored without synthesizing dates or deleting rows';
END
$$;
"""
# The DB-03 body of migration_batch with ``capture_operation_id`` among the updatable columns
# (``transitions.transition_trigger_sql("migration_batch")`` at this revision; DG-MIG-12 literal).
TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'capture_operation_id', 'cutover_date', 'finished_at', 'import_upload_ids', 'job_id', 'problem', 'profile', 'reconciliation_id', 'reconciliation_report_run_id', 'registry_version_id', 'row_version', 'started_at', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.cutover_date IS NOT NULL AND NEW.cutover_date IS DISTINCT FROM OLD.cutover_date THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: cutover_date of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['IMPORTED>CANCELLED', 'IMPORTED>FAILED', 'IMPORTED>RECONCILED', 'IMPORTING>CANCELLED', 'IMPORTING>FAILED', 'IMPORTING>IMPORTED', 'PROFILED>CANCELLED', 'PROFILED>FAILED', 'PROFILED>IMPORTING', 'PROFILING>CANCELLED', 'PROFILING>FAILED', 'PROFILING>PROFILED', 'RECONCILED>CANCELLED', 'RECONCILED>FAILED', 'RECONCILED>SUBMITTED', 'SUBMITTED>CANCELLED', 'SUBMITTED>FAILED', 'SUBMITTED>PROMOTED', 'UPLOADED>CANCELLED', 'UPLOADED>FAILED', 'UPLOADED>PROFILING']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# The 0056 body (without ``capture_operation_id``), restored by ``downgrade``.
TRANSITION_BODY_0056 = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'finished_at', 'import_upload_ids', 'job_id', 'problem', 'profile', 'reconciliation_id', 'reconciliation_report_run_id', 'registry_version_id', 'row_version', 'started_at', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['IMPORTED>CANCELLED', 'IMPORTED>FAILED', 'IMPORTED>RECONCILED', 'IMPORTING>CANCELLED', 'IMPORTING>FAILED', 'IMPORTING>IMPORTED', 'PROFILED>CANCELLED', 'PROFILED>FAILED', 'PROFILED>IMPORTING', 'PROFILING>CANCELLED', 'PROFILING>FAILED', 'PROFILING>PROFILED', 'RECONCILED>CANCELLED', 'RECONCILED>FAILED', 'RECONCILED>SUBMITTED', 'SUBMITTED>CANCELLED', 'SUBMITTED>FAILED', 'SUBMITTED>PROMOTED', 'UPLOADED>CANCELLED', 'UPLOADED>FAILED', 'UPLOADED>PROFILING']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
VERSION = "migration_population_version"
OBLIGATION = "migration_population_obligation"
TABLES = (VERSION, OBLIGATION)
# 04 T-MIG-04 CHECKs: the legacy database's book; the payload's batch is this batch; ≥ 1 member.
VERSION_CHECKS = (
    ("ck_migration_population_version__book", "book_code = 'ASC606'"),
    (
        "ck_migration_population_version__payload_batch",
        "payload_migration_batch_id = migration_batch_id",
    ),
    (
        "ck_migration_population_version__members",
        "jsonb_typeof(members) = 'array' AND jsonb_array_length(members) >= 1",
    ),
)


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=False)


def _named(name: str, type_name: str, *, default: str | None = None) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, ops.NamedType(type_name), nullable=False, server_default=server_default)


def _create_version() -> None:
    ops.create_tenant_table(
        VERSION,
        _uuid("migration_batch_id"),
        _uuid("contract_version_id"),
        sa.Column("version_no", sa.Integer(), nullable=False),
        _named("book_code", "erev.book_code"),
        _uuid("combination_group_id"),
        _text("status_in_book"),
        _uuid("contract_computation_id"),
        _named("input_sha256", "erev.sha256"),
        _named("output_sha256", "erev.sha256"),
        _text("engine_version"),
        _uuid("engine_release_id", nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bundle_known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutover_date", sa.Date(), nullable=False),
        _uuid("payload_migration_batch_id"),
        _uuid("opening_event_id"),
        _text("opening_event_key"),
        _named("opening_event_binding_sha256", "erev.sha256"),
        _named("members", "jsonb"),
        sa.Column("expected_output_captured", sa.Boolean(), nullable=False),
        _named("obligation_version_ids", "uuid[]", default="'{}'::uuid[]"),
        _uuid("capture_operation_id"),
        _uuid("calc_trace_id"),
        sa.Column("format_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("node_count", sa.Integer(), nullable=False),
        _named("root_measures", "jsonb"),
        _named("trace_sha256", "erev.sha256"),
        _named("trace", "jsonb"),
        _named("input_evidence", "jsonb"),
        _named("input_evidence_sha256", "erev.sha256"),
        standard_sets=["SC-C"],
        checks=VERSION_CHECKS,
        unique=[
            (
                "ux_migration_population_version__version",
                ["tenant_id", "migration_batch_id", "contract_version_id"],
                None,
            )
        ],
        indexes=[
            ("ix_migration_population_version__batch", ["tenant_id", "migration_batch_id"], None)
        ],
    )
    ops.add_tenant_fk(VERSION, "migration_batch_id", BATCH)
    ops.add_tenant_fk(VERSION, "payload_migration_batch_id", BATCH)
    ops.apply_class(VERSION, "IM-A")
    ops.enable_rls(VERSION, "RLS-T")


def _create_obligation() -> None:
    ops.create_tenant_table(
        OBLIGATION,
        _uuid("migration_batch_id"),
        _uuid("population_version_id"),
        _uuid("capture_operation_id"),
        _uuid("contract_version_id"),
        _uuid("obligation_version_id"),
        _uuid("contract_id"),
        _text("contract_external_id"),
        _text("obligation_key"),
        _text("obligation_kind"),
        _named("original_allocated_exact", "erev.exact"),
        _named("remaining_quantity", "erev.exact"),
        _named("billed_cum", "erev.money"),
        _named("revenue_cum", "erev.money"),
        _named("remaining_allocation", "erev.money"),
        _named("position_obligation", "erev.money"),
        _named("netting_reclass_amount", "erev.money"),
        _named("trace_nodes", "jsonb"),
        _named("row", "jsonb"),
        _named("row_sha256", "erev.sha256"),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_migration_population_obligation__obligation",
                ["tenant_id", "migration_batch_id", "obligation_version_id"],
                None,
            )
        ],
        indexes=[
            (
                "ix_migration_population_obligation__version",
                ["tenant_id", "population_version_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(OBLIGATION, "migration_batch_id", BATCH)
    ops.add_tenant_fk(OBLIGATION, "population_version_id", VERSION)
    ops.apply_class(OBLIGATION, "IM-A")
    ops.enable_rls(OBLIGATION, "RLS-T")


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{SIGNATURE} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order: the T-MIG-01
    column and its trigger body first (the capture tables reference the batch), then the tables."""
    ops.execute(f"ALTER TABLE erev.{BATCH} ADD COLUMN capture_operation_id uuid NULL")
    ops.execute(
        f"GRANT UPDATE (capture_operation_id, cutover_date) ON TABLE erev.{BATCH} TO {APP_ROLE}"
    )
    # D-98 candidate 128: the cutover is set once at /import — the CHECK no longer demands it at
    # INSERT for OPENING_BALANCES; REPLAY still never carries one.
    ops.execute(f"ALTER TABLE erev.{BATCH} DROP CONSTRAINT {CUTOVER_CHECK}")
    ops.execute(
        f"ALTER TABLE erev.{BATCH} ADD CONSTRAINT {CUTOVER_CHECK} CHECK ({CUTOVER_CHECK_SQL})"
    )
    _replace_function(TRANSITION_BODY)
    _create_version()
    _create_obligation()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table in reversed(TABLES):
        ops.drop_tenant_table(table)
    _replace_function(TRANSITION_BODY_0056)
    # Codex 0727: rows the 1.60 CHECK admits (OPENING_BALANCES without a cutover) would violate
    # the 0056 CHECK — the downgrade is refused by name; no date is synthesized, no row deleted.
    # D-98 128 AMENDMENT 1: the refusal comes from the constraint validation itself
    # (RLS-independent) and propagates, rolling back this whole revision transaction.
    ops.execute(DOWNGRADE_RESTORE)
    ops.execute(f"REVOKE UPDATE (cutover_date) ON TABLE erev.{BATCH} FROM {APP_ROLE}")
    ops.execute(f"REVOKE UPDATE (capture_operation_id) ON TABLE erev.{BATCH} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE erev.{BATCH} DROP COLUMN capture_operation_id")
