"""BUILD_SPEC item RFD-12: SSP books, versions and entries.

04 ids created: E-47 ``ssp_method`` and E-49 ``ssp_value_basis`` (04 §3.4 order); T-REF-28
``ssp_book`` (IM-M, RLS-T) with ``ux_ssp_book__code``, the 04 column check named
``ck_ssp_book__resolution_mode`` (NC-16) and the foreign keys ``fk_ssp_book__entity`` →
``legal_entity`` and ``fk_ssp_book__currency`` → ``currency``, which 04 does not name
(L2-1-Q-23); T-REF-29 ``ssp_book_version`` (IM-P, SC-V, RLS-T) with ``ux_ssp_book_version__no``,
``ux_ssp_book_version__label``, the 04 checks named ``ck_ssp_book_version__sc_v_dates_unused`` and
``ck_ssp_book_version__effective_dates``, ``ck_ssp_book_version__entry_count``, the foreign key to
``ssp_book`` and the DB-04 trigger ``tg_ssp_book_version__config_version`` (scope key
``ssp_book_id``; an SSP version is never PUBLISHED, so the PUBLISHED overlap check never applies);
T-REF-30 ``ssp_entry`` (IM-P child, RLS-T) with ``ux_ssp_entry__key``, the 04 column checks named
``ck_ssp_entry__legacy_range``, ``ck_ssp_entry__midpoint_discount_ratio``,
``ck_ssp_entry__range_ratio`` and ``ck_ssp_entry__observable_point``, the foreign keys to
``ssp_book_version``, ``product``, ``gl_account`` (``revenue_gl_account_id``) and ``currency``, and
the DB-04 trigger ``tg_ssp_entry__config_child``; T-REF-31 ``ssp_range`` (IM-P child, RLS-T) with
the 04 key ``ux_ssp_range`` named ``ux_ssp_range__band`` (NC-16), the 04 column checks named
``ck_ssp_range__band_dimension``, ``ck_ssp_range__ordered`` and ``ck_ssp_range__value``, the foreign
key to ``ssp_entry`` and the DB-04 trigger ``tg_ssp_range__config_child``. The parent version of a
range is two rows away, which ``erev.tg_config_child()`` cannot follow, so this revision adds the
function ``erev.tg_ssp_range__config_child()`` with the same rule (L2-1-Q-24). The foreign keys
``ssp_book_version.import_upload_id`` and ``ssp_book_version.ssp_calculator_run_id`` belong to
DIN-1 and RFD-15 (DG-MIG-03). The DB-04 overlap check among APPROVED versions and the DB-05 freeze
of the ``ssp_book`` scope belong to RFD-13.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

# 04 §3.4 E-47 and E-49 (DG-MIG-06).
SSP_METHOD = (
    "observable",
    "adjusted_market",
    "cost_plus_margin",
    "residual",
    "legacy_range",
    "formula",
)
SSP_VALUE_BASIS = ("AMOUNT", "PERCENT_OF_LIST")
# 04 T-REF-30 ``ux_ssp_entry__key``: absent dimension keys equal blank ones (legacy 01 M-04).
ENTRY_KEY = (
    "tenant_id, ssp_book_version_id, product_id, stratification, coalesce(region, ''), "
    "coalesce(channel, ''), coalesce(segment, ''), coalesce(deal_size_band, ''), "
    "coalesce(term_band, ''), currency"
)
# DB-04 for T-REF-31: a range changes only while the version of its entry is DRAFT or TESTED. As
# ``erev.tg_config_child()``: provisioning may insert the rows of the versions it seeds; a row of
# another tenant is left to row-level security, which checks after BEFORE triggers; an invisible
# entry fails closed.
SSP_RANGE_CONFIG_CHILD_BODY = """
DECLARE
  targets jsonb[];
  target jsonb;
  version_id uuid;
  version_status text;
BEGIN
  IF TG_OP = 'INSERT' AND current_setting('app.platform_scope', true) = 'provisioning' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN
    targets := ARRAY[to_jsonb(NEW)];
  ELSIF TG_OP = 'UPDATE' THEN
    targets := ARRAY[to_jsonb(OLD), to_jsonb(NEW)];
  ELSE
    targets := ARRAY[to_jsonb(OLD)];
  END IF;
  FOREACH target IN ARRAY targets LOOP
    IF (target ->> 'tenant_id')::uuid IS DISTINCT FROM erev.current_tenant_id() THEN
      CONTINUE;
    END IF;
    version_id := NULL;
    version_status := NULL;
    SELECT v.id, v.status::text INTO version_id, version_status
      FROM erev.ssp_entry e
      JOIN erev.ssp_book_version v ON v.tenant_id = e.tenant_id AND v.id = e.ssp_book_version_id
     WHERE e.tenant_id = (target ->> 'tenant_id')::uuid
       AND e.id = (target ->> 'ssp_entry_id')::uuid;
    IF version_status IS NULL OR version_status <> ALL (ARRAY['DRAFT', 'TESTED']::text[]) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-CFG-002: rows of %I.%I cannot change while %s is %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME,
                         CASE WHEN version_id IS NULL
                              THEN 'ssp_entry ' || (target ->> 'ssp_entry_id')
                              ELSE 'ssp_book_version ' || version_id::text END,
                         coalesce(version_status, 'not visible'));
    END IF;
  END LOOP;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
"""


def _exact(name: str) -> sa.Column[Any]:
    return sa.Column(name, ops.NamedType("erev.exact"), nullable=True)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("ssp_method", SSP_METHOD)
    ops.create_enum("ssp_value_basis", SSP_VALUE_BASIS)

    ops.create_tenant_table(
        "ssp_book",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("description", ops.NamedType("erev.memo"), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("currency", ops.NamedType("erev.currency_code"), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("segment", sa.Text(), nullable=True),
        sa.Column(
            "resolution_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'EFFECTIVE_DATE'"),
        ),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_ssp_book__resolution_mode",
                "resolution_mode IN ('EFFECTIVE_DATE', 'BY_LABEL')",
            )
        ],
        unique=[("ux_ssp_book__code", ["tenant_id", "code"], None)],
    )
    # [J] Scope columns name existing rows, as T-REF-15 entity_id (revision 0032; L2-1-Q-23).
    ops.add_tenant_fk("ssp_book", "entity_id", "legal_entity")
    ops.add_global_fk("ssp_book", "currency", "currency", target_column="code")
    ops.apply_class("ssp_book", "IM-M")
    ops.enable_rls("ssp_book", "RLS-T")

    ops.create_tenant_table(
        "ssp_book_version",
        sa.Column("ssp_book_id", sa.Uuid(), nullable=False),
        sa.Column("legacy_version_label", sa.Text(), nullable=True),
        sa.Column("effective_from_date", sa.Date(), nullable=True),
        sa.Column("effective_to_date", sa.Date(), nullable=True),
        sa.Column("methodology_label", ops.NamedType("erev.label"), nullable=False),
        sa.Column(
            "is_methodology_change", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("diff_summary", ops.NamedType("jsonb"), nullable=True),
        sa.Column("ssp_calculator_run_id", sa.Uuid(), nullable=True),
        sa.Column("import_upload_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        checks=[
            (
                "ck_ssp_book_version__sc_v_dates_unused",
                "effective_from IS NULL AND effective_to IS NULL",
            ),
            (
                "ck_ssp_book_version__effective_dates",
                "effective_to_date IS NULL OR effective_to_date >= effective_from_date",
            ),
            # [J] As fx_rate_set_version.rate_count (revision 0030; L2-1-Q-23).
            ("ck_ssp_book_version__entry_count", "entry_count >= 0"),
        ],
        unique=[
            ("ux_ssp_book_version__no", ["tenant_id", "ssp_book_id", "version_no"], None),
            (
                "ux_ssp_book_version__label",
                ["tenant_id", "ssp_book_id", "legacy_version_label"],
                "legacy_version_label IS NOT NULL",
            ),
        ],
    )
    ops.add_tenant_fk("ssp_book_version", "ssp_book_id", "ssp_book")
    ops.apply_class("ssp_book_version", "IM-P")
    ops.enable_rls("ssp_book_version", "RLS-T")
    ops.add_config_version_trigger("ssp_book_version", scope_columns=["ssp_book_id"])

    ops.create_tenant_table(
        "ssp_entry",
        sa.Column("ssp_book_version_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("stratification", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("segment", sa.Text(), nullable=True),
        sa.Column("deal_size_band", sa.Text(), nullable=True),
        sa.Column("term_band", sa.Text(), nullable=True),
        sa.Column("currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("method", ops.NamedType("erev.ssp_method"), nullable=False),
        sa.Column(
            "value_basis",
            ops.NamedType("erev.ssp_value_basis"),
            nullable=False,
            server_default=sa.text("'AMOUNT'"),
        ),
        _exact("unit_list_price"),
        _exact("midpoint_discount_ratio"),
        _exact("range_ratio"),
        _exact("cost_basis"),
        _exact("margin_ratio"),
        _exact("observable_point"),
        sa.Column("revenue_gl_account_id", sa.Uuid(), nullable=True),
        sa.Column("distinctness", ops.NamedType("erev.distinctness"), nullable=False),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_ssp_entry__legacy_range",
                "method <> 'legacy_range' OR (unit_list_price IS NOT NULL "
                "AND midpoint_discount_ratio IS NOT NULL AND range_ratio IS NOT NULL)",
            ),
            (
                "ck_ssp_entry__midpoint_discount_ratio",
                "midpoint_discount_ratio IS NULL "
                "OR (midpoint_discount_ratio >= 0 AND midpoint_discount_ratio < 1)",
            ),
            ("ck_ssp_entry__range_ratio", "range_ratio IS NULL OR range_ratio >= 0"),
            (
                "ck_ssp_entry__observable_point",
                "observable_point IS NULL OR observable_point >= 0",
            ),
        ],
    )
    ops.execute(f"CREATE UNIQUE INDEX ux_ssp_entry__key ON erev.ssp_entry ({ENTRY_KEY})")
    ops.add_tenant_fk("ssp_entry", "ssp_book_version_id", "ssp_book_version")
    ops.add_tenant_fk("ssp_entry", "product_id", "product")
    ops.add_tenant_fk("ssp_entry", "revenue_gl_account_id", "gl_account")
    ops.add_global_fk("ssp_entry", "currency", "currency", target_column="code")
    ops.apply_class("ssp_entry", "IM-P", without_sc_m=True)
    ops.enable_rls("ssp_entry", "RLS-T")
    ops.add_config_child_trigger(
        "ssp_entry", parent_table="ssp_book_version", parent_column="ssp_book_version_id"
    )

    ops.create_tenant_table(
        "ssp_range",
        sa.Column("ssp_entry_id", sa.Uuid(), nullable=False),
        sa.Column("band_dimension", sa.Text(), nullable=False, server_default=sa.text("'NONE'")),
        _exact("band_from"),
        _exact("band_to"),
        _exact("point_value"),
        _exact("low_value"),
        _exact("mid_value"),
        _exact("high_value"),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_ssp_range__band_dimension",
                "band_dimension IN ('NONE', 'QUANTITY', 'DEAL_SIZE', 'TERM_MONTHS')",
            ),
            (
                "ck_ssp_range__ordered",
                "low_value IS NULL OR mid_value IS NULL OR high_value IS NULL "
                "OR (low_value <= mid_value AND mid_value <= high_value)",
            ),
            ("ck_ssp_range__value", "point_value IS NOT NULL OR mid_value IS NOT NULL"),
        ],
    )
    ops.execute(
        "CREATE UNIQUE INDEX ux_ssp_range__band ON erev.ssp_range "
        "(tenant_id, ssp_entry_id, band_dimension, coalesce(band_from, -1))"
    )
    ops.add_tenant_fk("ssp_range", "ssp_entry_id", "ssp_entry")
    ops.apply_class("ssp_range", "IM-P", without_sc_m=True)
    ops.enable_rls("ssp_range", "RLS-T")
    ops.create_trigger(
        "ssp_range",
        "config_child",
        SSP_RANGE_CONFIG_CHILD_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OR DELETE",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("ssp_range")
    ops.drop_tenant_table("ssp_entry")
    ops.drop_tenant_table("ssp_book_version")
    ops.drop_tenant_table("ssp_book")
    ops.drop_enum("ssp_value_basis")
    ops.drop_enum("ssp_method")
