"""Bound pending commit recovery scans to unarchived postings."""

from erev_api.db import migration_ops as ops

revision = "0275"
down_revision = "0274"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "CREATE INDEX ix_subledger_posting_commit__pending "
        "ON erev.subledger_posting_commit (tenant_id, subledger_posting_id) "
        "WHERE committed_server_at IS NULL"
    )


def downgrade() -> None:
    ops.execute("DROP INDEX erev.ix_subledger_posting_commit__pending")
