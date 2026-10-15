"""Let proposal date ranges bound scans under tenant row-level security (NC-20)."""

from erev_api.db import migration_ops as ops

revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enum comparisons stay after the policy. A timestamp ahead of those keys can bound the
    # tenant's scan; leaving it behind kind/status makes the index scan the whole tenant.
    ops.execute("DROP INDEX erev.ix_ai_proposal__status")
    ops.create_indexes(
        "ai_proposal",
        [("ix_ai_proposal__status", ["tenant_id", "created_at", "kind", "status"], None)],
        unique=False,
    )


def downgrade() -> None:
    ops.execute("DROP INDEX erev.ix_ai_proposal__status")
    ops.create_indexes(
        "ai_proposal",
        [("ix_ai_proposal__status", ["tenant_id", "kind", "status", "created_at"], None)],
        unique=False,
    )
