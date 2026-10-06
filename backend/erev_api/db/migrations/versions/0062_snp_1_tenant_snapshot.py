"""BUILD_SPEC item SNP-1: tenant snapshot (T-PLT-34).

Revision 0062 on P2's 0061 (``0061_security_event_key_attribution``), assigned by the supervisor at
merge prep 2026-09-20 (the lane branch carried it as provisional 0099 on 0054 before; lane record
docs/reviews/loop/prod/F-SNP-prep.md §13.1, §13.4.9).

04 ids created: T-PLT-34 ``tenant_snapshot`` (IM-S, RLS-T; SC-C), its DB-03 transition function and
the DB-15 target trigger.

- T-PLT-34 ``tenant_snapshot``: primary key ``(tenant_id, id)``; ``ck_tenant_snapshot__purpose``
  (``SANDBOX_COPY``, ``STORED_BACKUP``, ``SANDBOX_SEED``); ``ix_tenant_snapshot__status``; foreign
  keys ``target_tenant_id → tenant (id)`` (global), ``manifest_file_id → file_object``,
  ``job_id → job``. IM-S: UPDATE of ``target_tenant_id``, ``manifest_file_id``, ``manifest_sha256``,
  ``row_counts``, ``started_at``, ``finished_at`` and ``status`` along E-67 (DB-03
  ``tg_tenant_snapshot__transition``, rendered by ``erev_api.db.transitions``; DG-ARC-07 compares).
- DB-15 ``tg_tenant_snapshot__target`` (BEFORE INSERT OR UPDATE): a non-NULL ``target_tenant_id``
  names a tenant of kind ``sandbox`` visible to the invoker, else ``EREV-SBX-001``; a target hidden
  by RLS-TN is refused too (trigger functions are SECURITY INVOKER). The SNP-2 load sets the target
  as an actor holding an ACTIVE membership of the sandbox — RLS-TN reveals the row to members;
  provisioning scope reveals nothing (04 rev 1.56; docstring corrected after the batch on 0cb36c14).

Two functions are added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

TABLE = "tenant_snapshot"
PURPOSES = ("SANDBOX_COPY", "STORED_BACKUP", "SANDBOX_SEED")
CHECKS = (
    (
        "ck_tenant_snapshot__purpose",
        "purpose IN (" + ", ".join(f"'{value}'" for value in PURPOSES) + ")",
    ),
)
# 04 T-PLT-34 class IM-S: the columns granted for UPDATE (the DB-03 trigger narrows them).
UPDATE_COLUMNS = (
    "status",
    "target_tenant_id",
    "manifest_file_id",
    "manifest_sha256",
    "row_counts",
    "started_at",
    "finished_at",
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("tenant_snapshot") at SNP-1; DG-ARC-07
# compares the installed function with a fresh rendering.
TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['finished_at', 'manifest_file_id', 'manifest_sha256', 'row_counts', 'started_at', 'status', 'target_tenant_id']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.finished_at IS NOT NULL AND NEW.finished_at IS DISTINCT FROM OLD.finished_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: finished_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.manifest_file_id IS NOT NULL AND NEW.manifest_file_id IS DISTINCT FROM OLD.manifest_file_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: manifest_file_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.manifest_sha256 IS NOT NULL AND NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: manifest_sha256 of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['QUEUED>FAILED', 'QUEUED>RUNNING', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# DB-15: target_tenant_id must be a sandbox (04 §14.1; 05 SBX-02; REQ-PLT-024; CTL-043).
TARGET_BODY = """
DECLARE
  target_kind text;
BEGIN
  IF NEW.target_tenant_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.target_tenant_id IS NOT DISTINCT FROM OLD.target_tenant_id THEN
    RETURN NEW;
  END IF;
  SELECT t.kind::text INTO target_kind FROM erev.tenant t WHERE t.id = NEW.target_tenant_id;
  IF target_kind IS DISTINCT FROM 'sandbox' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-SBX-001: snapshot %s targets tenant %s of kind %s; a snapshot '
                       'restores only into a sandbox tenant',
                       NEW.id, NEW.target_tenant_id, coalesce(target_kind, 'unknown or hidden'));
  END IF;
  RETURN NEW;
END
"""


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        TABLE,
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        _named("status", "erev.run_status", nullable=False, default="'QUEUED'"),
        _uuid("target_tenant_id"),
        _uuid("manifest_file_id"),
        _named("manifest_sha256", "erev.sha256", nullable=True),
        _named("row_counts", "jsonb", nullable=True),
        _uuid("job_id"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        standard_sets=["SC-C"],
        checks=CHECKS,
        indexes=[("ix_tenant_snapshot__status", ["tenant_id", "status"], None)],
    )
    ops.add_global_fk(TABLE, "target_tenant_id", "tenant")
    ops.add_tenant_fk(TABLE, "manifest_file_id", "file_object")
    ops.add_tenant_fk(TABLE, "job_id", "job")
    # IM-S: DB-01 DELETE / TRUNCATE triggers + a column-listed UPDATE grant; no SC-M, no touch.
    ops.apply_class(TABLE, "IM-S", update_columns=UPDATE_COLUMNS)
    ops.enable_rls(TABLE, "RLS-T")
    ops.create_trigger(TABLE, "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE")
    ops.create_trigger(TABLE, "target", TARGET_BODY, timing="BEFORE", events="INSERT OR UPDATE")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
