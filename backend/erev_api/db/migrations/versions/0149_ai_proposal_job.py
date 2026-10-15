"""Bind completed AI proposals to their job and immutable request identity."""

from erev_api.db import migration_ops as ops

revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.ai_proposal ADD COLUMN job_id uuid, ADD COLUMN job_source_sha256 char(64)"
    )
    ops.execute(
        "ALTER TABLE erev.ai_proposal ADD CONSTRAINT ck_ai_proposal__job_binding "
        "CHECK ((job_id IS NULL AND job_source_sha256 IS NULL) OR "
        "(job_id IS NOT NULL AND job_source_sha256 IS NOT NULL "
        "AND job_source_sha256 ~ '^[0-9a-f]{64}$'))"
    )
    ops.add_tenant_fk("ai_proposal", "job_id", "job")
    ops.create_indexes(
        "ai_proposal",
        [("ux_ai_proposal__job", ["tenant_id", "job_id"], "job_id IS NOT NULL")],
        unique=True,
    )


def downgrade() -> None:
    # A populated job binding is completion evidence; never silently erase it.
    ops.execute(
        "ALTER TABLE erev.ai_proposal ADD CONSTRAINT ck_ai_proposal__0149_empty "
        "CHECK (job_id IS NULL) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.ai_proposal VALIDATE CONSTRAINT ck_ai_proposal__0149_empty")
    ops.execute("ALTER TABLE erev.ai_proposal DROP CONSTRAINT ck_ai_proposal__0149_empty")
    ops.execute("ALTER TABLE erev.ai_proposal DROP COLUMN job_id, DROP COLUMN job_source_sha256")
