"""BUILD_SPEC item RFD-6: chart of accounts and dimensions.

04 ids created: E-52 ``account_type`` and E-38 ``source_system`` (first used here, DG-MIG-06);
T-REF-13 ``gl_account`` (IM-M, RLS-T) with ``ux_gl_account__code`` and
``ck_gl_account__normal_balance``; T-REF-16 ``dimension_definition`` (IM-M, RLS-T) with
``ux_dimension_definition__code`` and ``ck_dimension_definition__code``; T-REF-17
``dimension_value`` (IM-M, RLS-T) with ``ux_dimension_value__code`` and its composite foreign keys
to ``dimension_definition`` and to itself (``parent_value_id``); DB-12
``tg_dimension_definition__custom_limit``: at most five non-built-in ``dimension_definition`` rows
per tenant (``EREV-REF-002``). The built-in rows are tenant data, written by provisioning (04 §14.3;
DG-MIG-07).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

# 04 §3.4 E-52 and E-38.
ACCOUNT_TYPE = ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE")
SOURCE_SYSTEM = (
    "LEGACY_TEMPLATE_V1",
    "CSV_V2",
    "API",
    "MANUAL_UI",
    "SALESFORCE",
    "STRIPE",
    "NETSUITE",
    "QUICKBOOKS_ONLINE",
    "LEGACY_DB",
)

# DB-12: at most five non-built-in dimension definitions per tenant. The transaction-level advisory
# lock on the tenant serialises the writers of custom dimensions, so each sees the rows the others
# committed; a built-in row, or a custom row that stays custom, needs no count.
CUSTOM_LIMIT_BODY = """
DECLARE
  custom_count integer;
BEGIN
  IF NEW.is_builtin THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NOT OLD.is_builtin THEN
    RETURN NEW;
  END IF;
  PERFORM pg_advisory_xact_lock(
    hashtextextended('erev.dimension_definition:' || NEW.tenant_id::text, 0));
  SELECT count(*) INTO custom_count FROM erev.dimension_definition d
   WHERE d.tenant_id = NEW.tenant_id AND NOT d.is_builtin AND d.id <> NEW.id;
  IF custom_count >= 5 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: %I.%I allows at most five non-built-in dimensions per tenant',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("account_type", ACCOUNT_TYPE)
    ops.create_enum("source_system", SOURCE_SYSTEM)

    ops.create_tenant_table(
        "gl_account",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("account_type", ops.NamedType("erev.account_type"), nullable=False),
        sa.Column("normal_balance", sa.CHAR(1), nullable=False),
        sa.Column(
            "entity_ids",
            ops.NamedType("uuid[]"),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "required_dimensions",
            ops.NamedType("text[]"),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "source_system",
            ops.NamedType("erev.source_system"),
            nullable=False,
            server_default=sa.text("'MANUAL_UI'"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_gl_account__normal_balance", "normal_balance IN ('D', 'C')")],
        unique=[("ux_gl_account__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("gl_account", "IM-M")
    ops.enable_rls("gl_account", "RLS-T")

    ops.create_tenant_table(
        "dimension_definition",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_dimension_definition__code", "code ~ '^[a-z][a-z0-9_]{1,31}$'")],
        unique=[("ux_dimension_definition__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("dimension_definition", "IM-M")
    ops.enable_rls("dimension_definition", "RLS-T")
    ops.create_trigger(
        "dimension_definition",
        "custom_limit",
        CUSTOM_LIMIT_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OF is_builtin",
    )

    ops.create_tenant_table(
        "dimension_value",
        sa.Column("dimension_definition_id", sa.Uuid(), nullable=False),
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("parent_value_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        unique=[
            (
                "ux_dimension_value__code",
                ["tenant_id", "dimension_definition_id", "code"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("dimension_value", "dimension_definition_id", "dimension_definition")
    ops.add_tenant_fk("dimension_value", "parent_value_id", "dimension_value")
    ops.apply_class("dimension_value", "IM-M")
    ops.enable_rls("dimension_value", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("dimension_value")
    ops.drop_tenant_table("dimension_definition")
    ops.drop_tenant_table("gl_account")
    ops.drop_enum("source_system")
    ops.drop_enum("account_type")
