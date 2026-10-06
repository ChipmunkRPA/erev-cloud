"""BUILD_SPEC item PLF-21: me, tenant settings and saved views API.

04 ids created: T-PLT-37 ``saved_view`` (IM-M with DELETE, RLS-T; §14.2 grants ``SELECT, INSERT,
UPDATE, DELETE`` to ``erev_app``) with ``ux_saved_view__name (tenant_id, membership_id, screen_code,
name)``, its composite foreign key to ``tenant_membership`` and the DB-02 touch trigger
``tg_saved_view__touch``.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        "saved_view",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("screen_code", sa.Text(), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("config", ops.NamedType("jsonb"), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_favourite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        standard_sets=["SC-C", "SC-M"],
        unique=[
            (
                "ux_saved_view__name",
                ["tenant_id", "membership_id", "screen_code", "name"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("saved_view", "membership_id", "tenant_membership")
    ops.apply_class("saved_view", "IM-M", delete_allowed=True)
    ops.enable_rls("saved_view", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("saved_view")
