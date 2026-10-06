"""BUILD_SPEC item PLF-6: separation-of-duties rules and exceptions.

04 ids created: E-12 ``config_status``; E-96 ``grant_status``; the DB-04 function
``erev.tg_config_version()``; T-PLT-13 ``sod_rule`` (IM-P, SC-V, RLS-T) with the DB-04 trigger
``tg_sod_rule__config_version`` (scope key ``code``), the DB-02 touch trigger and the DB-12 trigger
``tg_sod_rule__permission_codes``; T-PLT-14 ``sod_exception`` (IM-S, RLS-T) with the DB-03 trigger
``tg_sod_exception__transition``; the foreign key ``role_assignment.sod_exception_id``. The foreign
keys to ``approval_request`` belong to the revision that creates it (DG-MIG-03).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# 04 §3.4 E-12 and E-96.
CONFIG_STATUS = (
    "DRAFT",
    "TESTED",
    "SUBMITTED",
    "APPROVED",
    "PUBLISHED",
    "SUPERSEDED",
    "REJECTED",
    "WITHDRAWN",
)
GRANT_STATUS = ("REQUESTED", "APPROVED", "REJECTED", "REVOKED", "EXPIRED")
# 04 T-PLT-14: the columns erev_app may update.
SOD_EXCEPTION_UPDATE_COLUMNS = (
    "status",
    "approved_at",
    "revoked_at",
    "revoked_by",
    "revoked_by_kind",
)
# DB-03: erev_api.db.transitions.transition_trigger_sql("sod_exception") at PLF-6; DG-ARC-07
# compares the installed function with a fresh rendering.
SOD_EXCEPTION_TRANSITION_BODY = """
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
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>EXPIRED', 'APPROVED>REVOKED', 'REQUESTED>APPROVED', 'REQUESTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# DB-12: every permission code of a rule exists in the catalogue.
PERMISSION_CODES_BODY = """
DECLARE
  unknown text;
BEGIN
  SELECT string_agg(u.code, ', ' ORDER BY u.code) INTO unknown
    FROM unnest(NEW.function_a_permissions || NEW.function_b_permissions) AS u(code)
   WHERE NOT EXISTS (SELECT 1 FROM erev.permission p WHERE p.code = u.code);
  IF unknown IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: permission codes %s of %I.%I do not exist',
                       unknown, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""


def _timestamp(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("config_status", CONFIG_STATUS)
    ops.create_enum("grant_status", GRANT_STATUS)
    ops.create_config_version_function()

    ops.create_tenant_table(
        "sod_rule",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("function_a_permissions", ops.NamedType("text[]"), nullable=False),
        sa.Column("function_b_permissions", ops.NamedType("text[]"), nullable=False),
        sa.Column("rationale", ops.NamedType("erev.memo"), nullable=False),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        approval_request_fk=False,
        checks=[
            ("ck_sod_rule__function_a_permissions", "cardinality(function_a_permissions) > 0"),
            ("ck_sod_rule__function_b_permissions", "cardinality(function_b_permissions) > 0"),
        ],
        unique=[
            ("ux_sod_rule__code_version", ["tenant_id", "code", "version_no"], None),
            ("ux_sod_rule__published", ["tenant_id", "code"], "status = 'PUBLISHED'"),
        ],
    )
    ops.apply_class("sod_rule", "IM-P")
    ops.enable_rls("sod_rule", "RLS-T")
    ops.add_config_version_trigger("sod_rule", scope_columns=["code"])
    ops.create_trigger(
        "sod_rule",
        "permission_codes",
        PERMISSION_CODES_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OF function_a_permissions, function_b_permissions",
    )

    ops.create_tenant_table(
        "sod_exception",
        sa.Column("sod_rule_code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("compensating_control", ops.NamedType("erev.memo"), nullable=False),
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
            (
                "ck_sod_exception__validity",
                "valid_to > valid_from AND valid_to <= valid_from + interval '366 days'",
            )
        ],
        indexes=[("ix_sod_exception__membership", ["tenant_id", "membership_id", "status"], None)],
    )
    ops.add_tenant_fk("sod_exception", "membership_id", "tenant_membership")
    ops.apply_class("sod_exception", "IM-S", update_columns=SOD_EXCEPTION_UPDATE_COLUMNS)
    ops.enable_rls("sod_exception", "RLS-T")
    ops.create_trigger(
        "sod_exception",
        "transition",
        SOD_EXCEPTION_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.add_tenant_fk("role_assignment", "sod_exception_id", "sod_exception")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(
        "ALTER TABLE erev.role_assignment DROP CONSTRAINT fk_role_assignment__sod_exception"
    )
    ops.drop_tenant_table("sod_exception")
    ops.drop_tenant_table("sod_rule")
    ops.drop_config_version_function()
    ops.drop_enum("grant_status")
    ops.drop_enum("config_status")
