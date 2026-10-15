"""Bound SCH-11 expiry scans by tenant and expiry timestamp under RLS."""

from erev_api.db import migration_ops as ops

revision = "0154"
down_revision = "0153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_indexes(
        "ai_proposal",
        [("ix_ai_proposal__expiry", ["tenant_id", "expires_at", "id"], None)],
        unique=False,
    )


def downgrade() -> None:
    ops.execute("DROP INDEX erev.ix_ai_proposal__expiry")
