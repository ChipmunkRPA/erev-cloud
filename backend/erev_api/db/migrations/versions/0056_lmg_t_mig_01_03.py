"""BUILD_SPEC item LMG-1: legacy migration tables (T-MIG-01 to T-MIG-03).

Revision ``0056`` on ``0055`` (P5 ``engine_release_validation_level``), assigned by the
supervisor at merge prep on 2026-09-20 (drafted in lane F-LMG, sprint/l24-flmg, as provisional
0098 on 0054; lane record docs/reviews/loop/prod/F-LMG.md §16, §19).

04 ids created: E-75 ``migration_mode``, E-76 ``migration_status``; T-MIG-01 ``migration_batch``
(IM-S, RLS-T; SC-C, SC-M), its DB-03 transition function; T-MIG-02 ``migrated_legacy_row`` (IM-A,
RLS-T; SC-C); T-MIG-03 ``migration_reconciliation_line`` (IM-A, RLS-T; SC-C). 04 rev 1.35 (D-98
candidate 48): the T-MIG-03 ``measure`` CHECK includes ``ORIGINAL_ALLOCATION``.

- T-MIG-01: ``ck_migration_batch__cutover`` (``(mode = 'OPENING_BALANCES') = (cutover_date IS NOT
  NULL)``); ``ux_migration_batch__no``; the partial ``ux_migration_batch__source (tenant_id,
  source_sha256, mode) WHERE status NOT IN ('FAILED', 'CANCELLED')`` (REQ-MIG-004; BR-MIG-01);
  foreign keys ``source_file_id → file_object``, ``sandbox_tenant_id → tenant (id)`` (global),
  ``registry_version_id → registry_version``, ``reconciliation_id → reconciliation``,
  ``reconciliation_report_run_id → report_run``, ``approval_request_id → approval_request``,
  ``job_id → job``. IM-S: UPDATE of the table-header columns along E-76 (DB-03
  ``tg_migration_batch__transition``, rendered by ``erev_api.db.transitions``; DG-ARC-07 compares).
- T-MIG-02: ``ck_migrated_legacy_row__label``; ``ux_migrated_legacy_row__source`` (04 names it
  ``ux_migrated_legacy_row``; NC-16 requires the ``ux_<table>__<rule>`` shape, as 0049 did for
  ``ux_source_order__external``); ``ix_migrated_legacy_row__contract``; foreign keys
  ``migration_batch_id → migration_batch``, ``contract_id → contract``, ``obligation_id →
  obligation``.
- T-MIG-03: ``ck_migration_reconciliation_line__measure`` (nine measures);
  ``ck_migration_reconciliation_line__exception`` (an unexplained difference carries its exception
  item; 04 rev 1.36); ``ix_migration_reconciliation_line__batch``; foreign keys
  ``migration_batch_id → migration_batch``, ``exception_item_id → exception_item``.

One function is added (``tg_migration_batch__transition``).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

# 04 §3.4 E-75, E-76 (DG-MIG-06).
MIGRATION_MODE = (
    "OPENING_BALANCES",
    "REPLAY",
)
MIGRATION_STATUS = (
    "UPLOADED",
    "PROFILING",
    "PROFILED",
    "IMPORTING",
    "IMPORTED",
    "RECONCILED",
    "SUBMITTED",
    "PROMOTED",
    "FAILED",
    "CANCELLED",
)
# 04 T-MIG-03 ``measure`` (rev 1.35).
MEASURES = (
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
LEGACY_ROW_LABEL = "migrated, unattributed"  # 04 T-MIG-02 ``label`` (D-31 mode a)
BATCH = "migration_batch"
LEGACY_ROW = "migrated_legacy_row"
LINE = "migration_reconciliation_line"
TABLES = (BATCH, LEGACY_ROW, LINE)  # 04 §18 dependency order


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


BATCH_CHECKS = (
    ("ck_migration_batch__cutover", "(mode = 'OPENING_BALANCES') = (cutover_date IS NOT NULL)"),
)
LEGACY_ROW_CHECKS = (("ck_migrated_legacy_row__label", f"label = '{LEGACY_ROW_LABEL}'"),)
LINE_CHECKS = (
    ("ck_migration_reconciliation_line__measure", f"measure IN ({_in(MEASURES)})"),
    # 04 rev 1.36 (D-98 candidate 52): an unexplained difference carries its exception item.
    (
        "ck_migration_reconciliation_line__exception",
        "is_within_tolerance OR deviation_ref IS NOT NULL OR exception_item_id IS NOT NULL",
    ),
)
# 04 T-MIG-01 class IM-S: the columns granted for UPDATE (the DB-03 trigger narrows them).
BATCH_UPDATE_COLUMNS = (
    "status",
    "approval_request_id",
    "finished_at",
    "import_upload_ids",
    "job_id",
    "problem",
    "profile",
    "reconciliation_id",
    "reconciliation_report_run_id",
    "registry_version_id",
    "row_version",
    "started_at",
    "updated_at",
    "updated_by",
    "updated_by_kind",
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("migration_batch") at LMG-1; DG-ARC-07
# compares the installed function with a fresh rendering.
TRANSITION_BODY = """
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


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _create_batch() -> None:
    ops.create_tenant_table(
        BATCH,
        _text("migration_no"),
        _named("mode", "erev.migration_mode", nullable=False),
        _named("status", "erev.migration_status", nullable=False, default="'UPLOADED'"),
        _uuid("source_file_id", nullable=False),
        _named("source_sha256", "erev.sha256", nullable=False),
        sa.Column("cutover_date", sa.Date(), nullable=True),
        _uuid("sandbox_tenant_id"),
        _named("profile", "jsonb", nullable=True),
        sa.Column(
            "import_upload_ids",
            ops.NamedType("uuid[]"),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        _uuid("registry_version_id"),
        _uuid("reconciliation_id"),
        _uuid("reconciliation_report_run_id"),
        _uuid("approval_request_id"),
        _uuid("job_id"),
        _timestamp("started_at"),
        _timestamp("finished_at"),
        _named("problem", "jsonb", nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=BATCH_CHECKS,
        unique=[
            ("ux_migration_batch__no", ["tenant_id", "migration_no"], None),
            (
                "ux_migration_batch__source",
                ["tenant_id", "source_sha256", "mode"],
                "status NOT IN ('FAILED', 'CANCELLED')",
            ),
        ],
    )
    ops.add_tenant_fk(BATCH, "source_file_id", "file_object")
    ops.add_global_fk(BATCH, "sandbox_tenant_id", "tenant")
    ops.add_tenant_fk(BATCH, "registry_version_id", "registry_version")
    ops.add_tenant_fk(BATCH, "reconciliation_id", "reconciliation")
    ops.add_tenant_fk(BATCH, "reconciliation_report_run_id", "report_run")
    ops.add_tenant_fk(BATCH, "approval_request_id", "approval_request")
    ops.add_tenant_fk(BATCH, "job_id", "job")
    ops.apply_class(BATCH, "IM-S", update_columns=BATCH_UPDATE_COLUMNS)
    ops.enable_rls(BATCH, "RLS-T")
    ops.create_trigger(BATCH, "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE")


def _create_legacy_row() -> None:
    ops.create_tenant_table(
        LEGACY_ROW,
        _uuid("migration_batch_id", nullable=False),
        sa.Column("source_rowid", sa.BigInteger(), nullable=False),
        _text("contract_external_id"),
        _text("obligation_key"),
        _text("product_code"),
        sa.Column("current_period", sa.Date(), nullable=True),
        _text("processing_time_log"),
        _text("record_unique_id"),
        _named("legacy_row", "jsonb", nullable=False),
        _named("legacy_row_sha256", "erev.sha256", nullable=False),
        _uuid("contract_id"),
        _uuid("obligation_id"),
        sa.Column(
            "label", sa.Text(), nullable=False, server_default=sa.text("'migrated, unattributed'")
        ),
        standard_sets=["SC-C"],
        checks=LEGACY_ROW_CHECKS,
        unique=[
            (
                "ux_migrated_legacy_row__source",
                ["tenant_id", "migration_batch_id", "source_rowid"],
                None,
            )
        ],
        indexes=[("ix_migrated_legacy_row__contract", ["tenant_id", "contract_id"], None)],
    )
    ops.add_tenant_fk(LEGACY_ROW, "migration_batch_id", BATCH)
    ops.add_tenant_fk(LEGACY_ROW, "contract_id", "contract")
    ops.add_tenant_fk(LEGACY_ROW, "obligation_id", "obligation")
    ops.apply_class(LEGACY_ROW, "IM-A")
    ops.enable_rls(LEGACY_ROW, "RLS-T")


def _create_line() -> None:
    ops.create_tenant_table(
        LINE,
        _uuid("migration_batch_id", nullable=False),
        _text("contract_external_id"),
        _text("obligation_key", nullable=True),
        _text("measure"),
        _named("source_value", "erev.exact", nullable=False),
        _named("erev_value", "erev.exact", nullable=False),
        _named("difference", "erev.exact", nullable=False),
        _named("tolerance", "erev.exact", nullable=False, default="0.0001"),
        sa.Column("is_within_tolerance", sa.Boolean(), nullable=False),
        _text("deviation_ref", nullable=True),
        _uuid("exception_item_id"),
        standard_sets=["SC-C"],
        checks=LINE_CHECKS,
        indexes=[
            ("ix_migration_reconciliation_line__batch", ["tenant_id", "migration_batch_id"], None)
        ],
    )
    ops.add_tenant_fk(LINE, "migration_batch_id", BATCH)
    ops.add_tenant_fk(LINE, "exception_item_id", "exception_item")
    ops.apply_class(LINE, "IM-A")
    ops.enable_rls(LINE, "RLS-T")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("migration_mode", MIGRATION_MODE)
    ops.create_enum("migration_status", MIGRATION_STATUS)
    _create_batch()
    _create_legacy_row()
    _create_line()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table in reversed(TABLES):
        ops.drop_tenant_table(table)
    ops.drop_enum("migration_status")
    ops.drop_enum("migration_mode")
