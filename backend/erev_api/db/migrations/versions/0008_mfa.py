"""BUILD_SPEC item PLF-5: TOTP multi-factor authentication, recovery codes and step-up.

04 ids created: T-PLT-04 ``user_mfa_factor`` (IM-M, RLS-NONE-U; §14.2 ``SELECT, INSERT, UPDATE``);
T-PLT-05 ``user_recovery_code`` (IM-S, RLS-NONE-U; UPDATE of ``used_at`` only, from NULL to a
value) with the DB-03 trigger ``tg_user_recovery_code__transition``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# 04 T-PLT-05: the column erev_app may update.
RECOVERY_CODE_UPDATE_COLUMNS = ("used_at",)
# DB-03: erev_api.db.transitions.transition_trigger_sql("user_recovery_code") at PLF-5; DG-ARC-07
# compares the installed function with a fresh rendering.
RECOVERY_CODE_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['used_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.used_at IS NOT NULL AND NEW.used_at IS DISTINCT FROM OLD.used_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: used_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_global_table(
        "user_mfa_factor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("factor_kind", sa.Text(), nullable=False, server_default=sa.text("'TOTP'")),
        sa.Column("secret_ciphertext", ops.NamedType("bytea"), nullable=False),
        sa.Column("secret_key_id", sa.Text(), nullable=False),
        _timestamp("confirmed_at"),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        _timestamp("disabled_at"),
        primary_key=["id"],
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_user_mfa_factor__factor_kind", "factor_kind = 'TOTP'")],
        unique=[("ux_user_mfa_factor__active", ["user_id"], "disabled_at IS NULL")],
    )
    ops.add_global_fk("user_mfa_factor", "user_id", "app_user")
    ops.apply_class("user_mfa_factor", "IM-M")

    ops.create_global_table(
        "user_recovery_code",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        _timestamp("used_at"),
        _timestamp("created_at", nullable=False, now_default=True),
        primary_key=["id"],
        indexes=[("ix_user_recovery_code__user_batch", ["user_id", "batch_id"], None)],
    )
    ops.add_global_fk("user_recovery_code", "user_id", "app_user")
    ops.apply_class("user_recovery_code", "IM-S", update_columns=RECOVERY_CODE_UPDATE_COLUMNS)
    ops.create_trigger(
        "user_recovery_code",
        "transition",
        RECOVERY_CODE_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("user_recovery_code")
    ops.drop_global_table("user_mfa_factor")
