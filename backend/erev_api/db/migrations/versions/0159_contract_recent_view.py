"""Private caller history for the most recently opened contracts."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0159"
down_revision = "0158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "contract_recent_view",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("actor_kind", ops.NamedType("erev.principal_kind"), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_contract_recent_view__actor_kind", "actor_kind IN ('USER', 'API_CLIENT')")],
        unique=[
            (
                "ux_contract_recent_view__actor_contract",
                ["tenant_id", "actor_id", "actor_kind", "contract_id"],
                None,
            )
        ],
        indexes=[
            (
                "ix_contract_recent_view__recent",
                ["tenant_id", "actor_id", "actor_kind", "viewed_at", "contract_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("contract_recent_view", "contract_id", "contract")
    ops.apply_class("contract_recent_view", "IM-M", delete_allowed=True)
    ops.enable_rls("contract_recent_view", "RLS-T")
    ops.execute("""
        CREATE POLICY pl_contract_recent_view__owner ON erev.contract_recent_view
        AS RESTRICTIVE FOR ALL TO erev_app
        USING (actor_id = (SELECT erev.current_user_id()))
        WITH CHECK (actor_id = (SELECT erev.current_user_id()))
    """)


def downgrade() -> None:
    ops.drop_tenant_table("contract_recent_view")
