"""BUILD_SPEC item RFD-9: products, bundles and principal-or-agent changes.

04 ids created: E-89 ``principal_agent`` and E-105 ``distinctness`` (04 §3.4 order); T-REF-20
``product`` (IM-M, RLS-T) with ``ux_product__code``, the 04 column check named
``ck_product__assurance_cost_per_unit`` (NC-16) and ``ck_product__disaggregation`` and
``ck_product__policy_values`` (JSON objects); T-REF-21 ``product_bundle_component`` (IM-M with
DELETE, 04 §14.2; RLS-T) with the 04 key ``ux_product_bundle_component`` named
``ux_product_bundle_component__component`` (NC-16 suffix; L2-1-Q-14), the 04 column checks named
``ck_product_bundle_component__distinct_products``, ``__quantity``, ``__split_basis`` and
``__split_ratio``, ``ck_product_bundle_component__split_ratio_required`` and
``ck_product_bundle_component__valid_range``, and its foreign keys to ``product`` (bundle and
component). The foreign key ``account_mapping_rule.product_id`` → ``product`` of T-REF-15 is added
here, because this revision creates ``product`` (DG-MIG-03). ``product.default_pob_template_id`` →
``pob_template`` belongs to RFD-10, which creates ``pob_template``. No function is added.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

# 04 §3.4 E-89 and E-105 (DG-MIG-06).
PRINCIPAL_AGENT = ("PRINCIPAL", "AGENT", "NOT_ASSESSED")
DISTINCTNESS = ("distinct", "nondistinct", "series")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("principal_agent", PRINCIPAL_AGENT)
    ops.create_enum("distinctness", DISTINCTNESS)

    ops.create_tenant_table(
        "product",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("sku_number", sa.Text(), nullable=True),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("product_family", sa.Text(), nullable=True),
        sa.Column("revenue_category", sa.Text(), nullable=True),
        sa.Column("default_pob_template_id", sa.Uuid(), nullable=True),
        sa.Column(
            "disaggregation",
            ops.NamedType("jsonb"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "principal_agent",
            ops.NamedType("erev.principal_agent"),
            nullable=False,
            server_default=sa.text("'NOT_ASSESSED'"),
        ),
        sa.Column(
            "distinctness_default",
            ops.NamedType("erev.distinctness"),
            nullable=False,
            server_default=sa.text("'distinct'"),
        ),
        sa.Column("unit_of_measure", sa.Text(), nullable=False, server_default=sa.text("'EA'")),
        sa.Column("is_bundle", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("assurance_cost_per_unit", ops.NamedType("erev.exact"), nullable=True),
        sa.Column(
            "is_franchisor_preopening_service",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "policy_values",
            ops.NamedType("jsonb"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_product__assurance_cost_per_unit",
                "assurance_cost_per_unit IS NULL OR assurance_cost_per_unit >= 0",
            ),
            # [J] As for account_mapping_rule.default_dimensions (revision 0032; L2-1-Q-14).
            ("ck_product__disaggregation", "jsonb_typeof(disaggregation) = 'object'"),
            ("ck_product__policy_values", "jsonb_typeof(policy_values) = 'object'"),
        ],
        unique=[("ux_product__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("product", "IM-M")
    ops.enable_rls("product", "RLS-T")

    ops.create_tenant_table(
        "product_bundle_component",
        sa.Column("bundle_product_id", sa.Uuid(), nullable=False),
        sa.Column("component_product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "quantity_per_bundle",
            ops.NamedType("erev.exact"),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "split_basis", sa.Text(), nullable=False, server_default=sa.text("'relative_ssp'")
        ),
        sa.Column("split_ratio", ops.NamedType("erev.exact"), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_product_bundle_component__distinct_products",
                "component_product_id <> bundle_product_id",
            ),
            ("ck_product_bundle_component__quantity", "quantity_per_bundle > 0"),
            (
                "ck_product_bundle_component__split_basis",
                "split_basis IN ('relative_ssp', 'fixed_percentage')",
            ),
            (
                "ck_product_bundle_component__split_ratio",
                "split_ratio IS NULL OR (split_ratio > 0 AND split_ratio <= 1)",
            ),
            # [J] 04 "Required for fixed_percentage" and a non-empty validity (L2-1-Q-14).
            (
                "ck_product_bundle_component__split_ratio_required",
                "split_basis <> 'fixed_percentage' OR split_ratio IS NOT NULL",
            ),
            (
                "ck_product_bundle_component__valid_range",
                "valid_to IS NULL OR valid_to > valid_from",
            ),
        ],
        unique=[
            (
                "ux_product_bundle_component__component",
                ["tenant_id", "bundle_product_id", "component_product_id", "valid_from"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("product_bundle_component", "bundle_product_id", "product")
    ops.add_tenant_fk("product_bundle_component", "component_product_id", "product")
    ops.apply_class("product_bundle_component", "IM-M", delete_allowed=True)
    ops.enable_rls("product_bundle_component", "RLS-T")

    ops.add_tenant_fk("account_mapping_rule", "product_id", "product")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(
        "ALTER TABLE erev.account_mapping_rule DROP CONSTRAINT fk_account_mapping_rule__product"
    )
    ops.drop_tenant_table("product_bundle_component")
    ops.drop_tenant_table("product")
    ops.drop_enum("distinctness")
    ops.drop_enum("principal_agent")
