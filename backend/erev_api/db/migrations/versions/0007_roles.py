"""BUILD_SPEC item PLF-4: roles, grants, entity scope and status transitions.

04 ids created: T-PLT-09 ``role`` (IM-M, RLS-T); T-PLT-10 ``role_assignment`` (IM-S, RLS-T) with the
DB-03 trigger ``tg_role_assignment__transition`` and the DB-12 trigger
``tg_role_assignment__entity_ids``, which rejects every non-empty ``entity_ids`` until
``legal_entity`` exists (BUILD_SPEC BS1-D-06); T-PLT-12 ``role_permission`` (IM-M with DELETE, DB-01
blocks UPDATE). The foreign keys ``approval_request_id`` and ``sod_exception_id`` belong to the
revisions that create their targets (DG-MIG-03).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# 04 T-PLT-10: the columns erev_app may update.
ROLE_ASSIGNMENT_UPDATE_COLUMNS = ("revoked_at", "revoked_by", "revoked_by_kind", "valid_to")
# DB-03: erev_api.db.transitions.transition_trigger_sql("role_assignment") at PLF-4; DG-ARC-07
# compares the installed function with a fresh rendering.
ROLE_ASSIGNMENT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['revoked_at', 'revoked_by', 'revoked_by_kind', 'valid_to']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""
# DB-12 fail closed (BS1-D-06): no entity id can be validated before legal_entity exists.
ENTITY_IDS_BODY = """
BEGIN
  IF cardinality(NEW.entity_ids) > 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: entity_ids of %I.%I name no existing legal entity',
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
    ops.create_tenant_table(
        "role",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("description", ops.NamedType("erev.memo"), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("content_sha256", ops.NamedType("erev.sha256"), nullable=False),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_role__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("role", "IM-M")
    ops.enable_rls("role", "RLS-T")

    ops.create_tenant_table(
        "role_assignment",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("is_all_entities", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "entity_ids",
            ops.NamedType("uuid[]"),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        _timestamp("valid_from", nullable=False, now_default=True),
        _timestamp("valid_to"),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("sod_exception_id", sa.Uuid(), nullable=True),
        _timestamp("revoked_at"),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_by_kind", ops.NamedType("erev.principal_kind"), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            ("ck_role_assignment__entity_ids", "is_all_entities = (cardinality(entity_ids) = 0)")
        ],
        unique=[
            (
                "ux_role_assignment__active",
                ["tenant_id", "membership_id", "role_id"],
                "revoked_at IS NULL",
            )
        ],
        indexes=[("ix_role_assignment__membership", ["tenant_id", "membership_id"], None)],
    )
    ops.add_tenant_fk("role_assignment", "membership_id", "tenant_membership")
    ops.add_tenant_fk("role_assignment", "role_id", "role")
    ops.apply_class("role_assignment", "IM-S", update_columns=ROLE_ASSIGNMENT_UPDATE_COLUMNS)
    ops.enable_rls("role_assignment", "RLS-T")
    ops.create_trigger(
        "role_assignment",
        "transition",
        ROLE_ASSIGNMENT_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.create_trigger(
        "role_assignment",
        "entity_ids",
        ENTITY_IDS_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OF entity_ids",
    )

    ops.create_tenant_table(
        "role_permission",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.Text(), nullable=False),
        include_id=False,
        primary_key=["tenant_id", "role_id", "permission_code"],
        standard_sets=["SC-C"],
    )
    ops.add_tenant_fk("role_permission", "role_id", "role")
    ops.add_global_fk("role_permission", "permission_code", "permission", target_column="code")
    ops.apply_class("role_permission", "IM-M", delete_allowed=True, update_forbidden=True)
    ops.enable_rls("role_permission", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("role_permission")
    ops.drop_tenant_table("role_assignment")
    ops.drop_tenant_table("role")
