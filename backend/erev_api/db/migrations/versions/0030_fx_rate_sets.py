"""BUILD_SPEC item RFD-3: currencies and FX rate sets.

04 ids created: E-51 ``rate_type``; T-REF-09 ``tenant_currency`` (IM-M, RLS-T; primary key
``(tenant_id, currency_code)`` and its foreign key to ``currency``); T-REF-10 ``fx_rate_set``
(IM-M, RLS-T) with ``ux_fx_rate_set__code``; T-REF-11 ``fx_rate_set_version`` (IM-P, SC-V, RLS-T)
with ``ux_fx_rate_set_version__no``, ``ck_fx_rate_set_version__coverage`` and the DB-04 trigger
``tg_fx_rate_set_version__config_version`` (scope key ``fx_rate_set_id``; no version is ever
PUBLISHED, so the PUBLISHED overlap check never applies and the highest APPROVED version wins,
L1-1-Q-28); T-REF-12 ``fx_rate`` (IM-P child, RLS-T) with ``ux_fx_rate__pair`` (04 names the key
``ux_fx_rate``; NC-16 name, as L1-1-Q-19), ``ix_fx_rate__lookup``, the checks of its column notes,
``rate`` of the TY-03 domain renamed ``erev.fx_rate_value`` (the table's row type takes the name
``erev.fx_rate``, L1-1-Q-32),
its foreign keys to ``fx_rate_set_version``, ``period`` and ``currency``, and the DB-04 trigger
``tg_fx_rate__config_child``. The foreign key ``fx_rate_set_version.import_upload_id`` belongs to
the revision that creates ``import_upload`` (DG-MIG-03). The DB-04 functions exist from revisions
0009 and 0014, so this revision adds no function.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

# 04 §3.4 E-51.
RATE_TYPE = ("spot", "closing", "average")
# TY-03: table T-REF-12 creates the row type erev.fx_rate, and PostgreSQL refuses a second type of
# that name, so the TY-03 domain of revision 0001 takes this name first (L1-1-Q-32).
RATE_DOMAIN = "fx_rate_value"


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.execute(f"ALTER DOMAIN erev.fx_rate RENAME TO {RATE_DOMAIN}")
    ops.create_enum("rate_type", RATE_TYPE)

    ops.create_tenant_table(
        "tenant_currency",
        sa.Column("currency_code", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        primary_key=["tenant_id", "currency_code"],
        include_id=False,
    )
    ops.add_global_fk("tenant_currency", "currency_code", "currency", target_column="code")
    ops.apply_class("tenant_currency", "IM-M")
    ops.enable_rls("tenant_currency", "RLS-T")

    ops.create_tenant_table(
        "fx_rate_set",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("rate_type", ops.NamedType("erev.rate_type"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_fx_rate_set__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("fx_rate_set", "IM-M")
    ops.enable_rls("fx_rate_set", "RLS-T")

    ops.create_tenant_table(
        "fx_rate_set_version",
        sa.Column("fx_rate_set_id", sa.Uuid(), nullable=False),
        sa.Column("coverage_from", sa.Date(), nullable=False),
        sa.Column("coverage_to", sa.Date(), nullable=False),
        sa.Column("rate_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("import_upload_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        checks=[
            ("ck_fx_rate_set_version__coverage", "coverage_to >= coverage_from"),
            ("ck_fx_rate_set_version__rate_count", "rate_count >= 0"),
        ],
        unique=[
            (
                "ux_fx_rate_set_version__no",
                ["tenant_id", "fx_rate_set_id", "version_no"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("fx_rate_set_version", "fx_rate_set_id", "fx_rate_set")
    ops.apply_class("fx_rate_set_version", "IM-P")
    ops.enable_rls("fx_rate_set_version", "RLS-T")
    ops.add_config_version_trigger("fx_rate_set_version", scope_columns=["fx_rate_set_id"])

    ops.create_tenant_table(
        "fx_rate",
        sa.Column("fx_rate_set_version_id", sa.Uuid(), nullable=False),
        sa.Column("rate_type", ops.NamedType("erev.rate_type"), nullable=False),
        sa.Column("base_currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("quote_currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=True),
        sa.Column("rate", ops.NamedType(f"erev.{RATE_DOMAIN}"), nullable=False),
        sa.Column("is_derived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        checks=[
            ("ck_fx_rate__currencies", "base_currency <> quote_currency"),
            ("ck_fx_rate__period", "rate_type = 'spot' OR period_id IS NOT NULL"),
        ],
        unique=[
            (
                "ux_fx_rate__pair",
                [
                    "tenant_id",
                    "fx_rate_set_version_id",
                    "base_currency",
                    "quote_currency",
                    "effective_date",
                ],
                None,
            )
        ],
        indexes=[
            (
                "ix_fx_rate__lookup",
                ["tenant_id", "rate_type", "base_currency", "quote_currency", "effective_date"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("fx_rate", "fx_rate_set_version_id", "fx_rate_set_version")
    ops.add_tenant_fk("fx_rate", "period_id", "period")
    ops.add_global_fk("fx_rate", "base_currency", "currency", target_column="code")
    ops.add_global_fk("fx_rate", "quote_currency", "currency", target_column="code")
    ops.apply_class("fx_rate", "IM-P", without_sc_m=True)
    ops.enable_rls("fx_rate", "RLS-T")
    ops.add_config_child_trigger(
        "fx_rate", parent_table="fx_rate_set_version", parent_column="fx_rate_set_version_id"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("fx_rate")
    ops.drop_tenant_table("fx_rate_set_version")
    ops.drop_tenant_table("fx_rate_set")
    ops.drop_tenant_table("tenant_currency")
    ops.drop_enum("rate_type")
    ops.execute(f"ALTER DOMAIN erev.{RATE_DOMAIN} RENAME TO fx_rate")
