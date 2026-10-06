"""BUILD_SPEC item PLF-26: support grants and operator access.

04 ids created: T-PLT-33 ``support_grant`` (IM-S, RLS-T) with ``ck_support_grant__scope``,
``ck_support_grant__validity`` (at most 72 hours), ``ix_support_grant__operator``, the foreign keys
``operator_user_id`` to ``app_user`` and ``approval_request_id`` to ``approval_request``, and the
DB-03 trigger ``tg_support_grant__transition``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

# 04 T-PLT-33: the columns erev_app may update.
SUPPORT_GRANT_UPDATE_COLUMNS = (
    "status",
    "approved_at",
    "revoked_at",
    "revoked_by",
    "revoked_by_kind",
)
# DB-03: erev_api.db.transitions.transition_trigger_sql("support_grant") at PLF-26; DG-ARC-07
# compares the installed function with a fresh rendering.
SUPPORT_GRANT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approved_at', 'revoked_at', 'revoked_by', 'revoked_by_kind', 'status']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revoked_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revoked_by IS NOT NULL AND NEW.revoked_by IS DISTINCT FROM OLD.revoked_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revoked_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revoked_by_kind IS NOT NULL AND NEW.revoked_by_kind IS DISTINCT FROM OLD.revoked_by_kind THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revoked_by_kind of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>EXPIRED', 'APPROVED>REVOKED', 'REQUESTED>APPROVED', 'REQUESTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _timestamp(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        "support_grant",
        sa.Column("operator_user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default=sa.text("'READ_ONLY'")),
        sa.Column("reason", ops.NamedType("erev.memo"), nullable=False),
        sa.Column("ticket_ref", sa.Text(), nullable=True),
        sa.Column(
            "status",
            ops.NamedType("erev.grant_status"),
            nullable=False,
            server_default=sa.text("'REQUESTED'"),
        ),
        _timestamp("valid_from", nullable=False),
        _timestamp("valid_to", nullable=False),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        _timestamp("approved_at"),
        _timestamp("revoked_at"),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_by_kind", ops.NamedType("erev.principal_kind"), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            ("ck_support_grant__scope", "scope = 'READ_ONLY'"),
            (
                "ck_support_grant__validity",
                "valid_to > valid_from AND valid_to <= valid_from + interval '72 hours'",
            ),
        ],
        indexes=[
            (
                "ix_support_grant__operator",
                ["tenant_id", "operator_user_id", "valid_to"],
                None,
            )
        ],
    )
    ops.add_global_fk("support_grant", "operator_user_id", "app_user")
    ops.add_tenant_fk("support_grant", "approval_request_id", "approval_request")
    ops.apply_class("support_grant", "IM-S", update_columns=SUPPORT_GRANT_UPDATE_COLUMNS)
    ops.enable_rls("support_grant", "RLS-T")
    ops.create_trigger(
        "support_grant",
        "transition",
        SUPPORT_GRANT_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("support_grant")
