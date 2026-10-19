"""Retain the files on which a captured contract sample depends."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "evidence_sample_file",
        sa.Column("evidence_pack_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("entity_ids", ARRAY(sa.Uuid()), nullable=True),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_evidence_sample_file__pack_file",
                ["tenant_id", "evidence_pack_id", "file_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("evidence_sample_file", "evidence_pack_id", "evidence_pack")
    ops.add_tenant_fk("evidence_sample_file", "file_id", "file_object")
    ops.apply_class("evidence_sample_file", "IM-A")
    ops.enable_rls("evidence_sample_file", "RLS-T")


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.evidence_sample_file) THEN
        RAISE EXCEPTION 'Contract sample evidence exists; downgrade refused';
      END IF;
    END $$""")
    ops.drop_tenant_table("evidence_sample_file")
