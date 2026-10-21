"""Retain explicit scope and refund terms for approved terminations."""

from erev_api.db import migration_ops as ops

revision = "0264"
down_revision = "0263"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.modification ADD COLUMN termination jsonb")


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.modification WHERE termination IS NOT NULL) THEN
        RAISE EXCEPTION 'Retained termination terms prevent downgrade';
      END IF;
    END $$""")
    ops.execute("ALTER TABLE erev.modification DROP COLUMN termination")
