"""Retain the actual close-pass input, output and selected ledger entries."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0192"
down_revision = "0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "close_pass_evidence",
        sa.Column("subledger_posting_id", sa.Uuid(), nullable=False),
        sa.Column("combination_group_id", sa.Uuid(), nullable=False),
        sa.Column("pass_name", sa.Text(), nullable=False),
        sa.Column("entry_numbers", JSONB(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("document_sha256", sa.CHAR(64), nullable=False),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_close_pass_evidence__posting_group",
                ["tenant_id", "subledger_posting_id", "combination_group_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("close_pass_evidence", "subledger_posting_id", "subledger_posting")
    ops.add_tenant_fk("close_pass_evidence", "combination_group_id", "combination_group")
    ops.execute(
        "ALTER TABLE erev.close_pass_evidence ADD CONSTRAINT ck_close_pass_evidence__pass "
        "CHECK (pass_name IN ('FX_REMEASUREMENT', 'CLOSE_RELEASE', 'NETTING_RECLASS'))"
    )
    ops.add_tenant_fk("close_pass_evidence", "file_id", "file_object")
    ops.apply_class("close_pass_evidence", "IM-A")
    # Like calc_trace, a group input can contain several member entities. Readers
    # must authorize the entire group before exposing the raw document.
    ops.enable_rls("close_pass_evidence", "RLS-T")


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.close_pass_evidence) THEN
        RAISE EXCEPTION 'Close-pass accounting evidence exists; downgrade refused';
      END IF;
    END $$""")
    ops.drop_tenant_table("close_pass_evidence")
