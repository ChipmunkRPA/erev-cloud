"""BUILD_SPEC item RFD-7: account-role mapping versions.

04 ids created: E-01 ``account_role`` (the 33 values of D-14 as amended by D-14a, in 04 §3.1 order);
E-109 ``clearing_purpose``; T-REF-14 ``account_mapping_version`` (IM-P, SC-V, RLS-T) with
``ux_account_mapping_version__no``, the foreign key ``impact_simulation_file_id`` → ``file_object``
and the DB-04 trigger ``tg_account_mapping_version__config_version`` (no scope key: PUBLISHED
ranges of the tenant never overlap); T-REF-15 ``account_mapping_rule`` (IM-P child, RLS-T) with
``ix_account_mapping_rule__role``, ``ck_account_mapping_rule__reserved_role``,
``ck_account_mapping_rule__clearing_purpose``, the 04 column check named
``ck_account_mapping_rule__product_category`` (NC-16),
``ck_account_mapping_rule__default_dimensions``, the generated column ``specificity``, the foreign
keys to ``account_mapping_version``, ``gl_account`` and ``legal_entity`` and the DB-04 trigger
``tg_account_mapping_rule__config_child``.
The foreign key ``product_id`` → ``product`` belongs to RFD-9, which creates ``product``
(DG-MIG-03). The DB-04 functions exist from revisions 0009 and 0014, so this revision adds none.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

# 04 §3.1 E-01: values 1 to 28 in D-14 order, then 29 to 33 in D-14a order (DG-MIG-06).
ACCOUNT_ROLE = (
    "REVENUE",
    "CONTRACT_LIABILITY",
    "CONTRACT_ASSET",
    "UNBILLED_RECEIVABLE",
    "ACCOUNTS_RECEIVABLE",
    "BILLING_CLEARING",
    "REFUND_LIABILITY",
    "RETURN_ASSET",
    "DEPOSIT_LIABILITY",
    "CONSIDERATION_PAYABLE",
    "CUSTOMER_INCENTIVE_ASSET",
    "COST_TO_OBTAIN_ASSET",
    "COST_TO_FULFILL_ASSET",
    "CONTRACT_COST_AMORTIZATION",
    "CONTRACT_COST_IMPAIRMENT",
    "LOSS_PROVISION",
    "LOSS_EXPENSE",
    "WARRANTY_PROVISION",
    "WARRANTY_EXPENSE",
    "INTEREST_INCOME",
    "INTEREST_EXPENSE",
    "FX_GAIN_LOSS",
    "INTERCOMPANY_DUE_TO",
    "INTERCOMPANY_DUE_FROM",
    "NONCASH_CONSIDERATION_ASSET",
    "SALES_TAX_PAYABLE",
    "PRE_STANDARD_REVENUE",
    "ROUNDING",
    "COST_OF_REVENUE",
    "CONTRACT_COST_CLEARING",
    "RECEIVABLE_CONTRA",
    "RETAINED_EARNINGS",
    "FINANCING_OBLIGATION",
)
# 04 §3.4 E-109.
CLEARING_PURPOSE = (
    "BILLING",
    "UNAPPLIED_CASH",
    "AP_SUPPLIER",
    "INVENTORY",
    "EQUITY",
    "INVESTMENTS",
)
# 04 T-REF-15 ``specificity``: entity 8, book 4, product or revenue category 2.
SPECIFICITY = (
    "(CASE WHEN entity_id IS NOT NULL THEN 8 ELSE 0 END) "
    "+ (CASE WHEN book_code IS NOT NULL THEN 4 ELSE 0 END) "
    "+ (CASE WHEN product_id IS NOT NULL OR revenue_category IS NOT NULL THEN 2 ELSE 0 END)"
)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("account_role", ACCOUNT_ROLE)
    ops.create_enum("clearing_purpose", CLEARING_PURPOSE)

    ops.create_tenant_table(
        "account_mapping_version",
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("notes", ops.NamedType("erev.memo"), nullable=True),
        sa.Column("impact_simulation_file_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        unique=[("ux_account_mapping_version__no", ["tenant_id", "version_no"], None)],
    )
    ops.add_tenant_fk("account_mapping_version", "impact_simulation_file_id", "file_object")
    ops.apply_class("account_mapping_version", "IM-P")
    ops.enable_rls("account_mapping_version", "RLS-T")
    ops.add_config_version_trigger("account_mapping_version")

    ops.create_tenant_table(
        "account_mapping_rule",
        sa.Column("account_mapping_version_id", sa.Uuid(), nullable=False),
        sa.Column("account_role", ops.NamedType("erev.account_role"), nullable=False),
        sa.Column("clearing_purpose", ops.NamedType("erev.clearing_purpose"), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("revenue_category", sa.Text(), nullable=True),
        sa.Column("gl_account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "default_dimensions",
            ops.NamedType("jsonb"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "specificity",
            sa.SmallInteger(),
            sa.Computed(SPECIFICITY, persisted=True),
            nullable=False,
        ),
        checks=[
            (
                "ck_account_mapping_rule__reserved_role",
                "account_role NOT IN ('RETAINED_EARNINGS', 'FINANCING_OBLIGATION')",
            ),
            (
                "ck_account_mapping_rule__clearing_purpose",
                "(account_role = 'BILLING_CLEARING') = (clearing_purpose IS NOT NULL)",
            ),
            (
                "ck_account_mapping_rule__product_category",
                "product_id IS NULL OR revenue_category IS NULL",
            ),
            (
                "ck_account_mapping_rule__default_dimensions",
                "jsonb_typeof(default_dimensions) = 'object'",
            ),
        ],
        indexes=[
            (
                "ix_account_mapping_rule__role",
                ["tenant_id", "account_mapping_version_id", "account_role", "clearing_purpose"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(
        "account_mapping_rule", "account_mapping_version_id", "account_mapping_version"
    )
    ops.add_tenant_fk("account_mapping_rule", "gl_account_id", "gl_account")
    ops.add_tenant_fk("account_mapping_rule", "entity_id", "legal_entity")
    ops.apply_class("account_mapping_rule", "IM-P", without_sc_m=True)
    ops.enable_rls("account_mapping_rule", "RLS-T")
    ops.add_config_child_trigger(
        "account_mapping_rule",
        parent_table="account_mapping_version",
        parent_column="account_mapping_version_id",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("account_mapping_rule")
    ops.drop_tenant_table("account_mapping_version")
    ops.drop_enum("clearing_purpose")
    ops.drop_enum("account_role")
