"""BUILD_SPEC item RFD-8: customers and related-party groups.

04 ids created: T-REF-18 ``related_party_group`` (IM-M, RLS-T) with
``ux_related_party_group__code``; T-REF-19 ``customer`` (IM-M, RLS-T) with ``ux_customer__code``,
the partial ``ux_customer__external (tenant_id, source_system, external_id) WHERE external_id IS
NOT NULL`` (REQ-REF-010), ``ck_customer__country_code`` and its composite foreign keys to
``related_party_group`` and to itself (``parent_customer_id``). E-38 ``source_system`` exists since
revision 0028 (DG-MIG-06), so this revision creates no enum, and it adds no function.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        "related_party_group",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("description", ops.NamedType("erev.memo"), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_related_party_group__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("related_party_group", "IM-M")
    ops.enable_rls("related_party_group", "RLS-T")

    ops.create_tenant_table(
        "customer",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("related_party_group_id", sa.Uuid(), nullable=True),
        sa.Column("parent_customer_id", sa.Uuid(), nullable=True),
        sa.Column("credit_grade", sa.Text(), nullable=True),
        sa.Column("segment", sa.Text(), nullable=True),
        sa.Column("country_code", sa.CHAR(2), nullable=True),
        sa.Column(
            "source_system",
            ops.NamedType("erev.source_system"),
            nullable=False,
            server_default=sa.text("'MANUAL_UI'"),
        ),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        # [J] As for legal_entity (revision 0029): ISO 3166-1 alpha-2 in capitals (L1-1-Q-24).
        checks=[("ck_customer__country_code", "country_code ~ '^[A-Z]{2}$'")],
        unique=[
            ("ux_customer__code", ["tenant_id", "code"], None),
            (
                "ux_customer__external",
                ["tenant_id", "source_system", "external_id"],
                "external_id IS NOT NULL",
            ),
        ],
    )
    ops.add_tenant_fk("customer", "related_party_group_id", "related_party_group")
    ops.add_tenant_fk("customer", "parent_customer_id", "customer")
    ops.apply_class("customer", "IM-M")
    ops.enable_rls("customer", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("customer")
    ops.drop_tenant_table("related_party_group")
