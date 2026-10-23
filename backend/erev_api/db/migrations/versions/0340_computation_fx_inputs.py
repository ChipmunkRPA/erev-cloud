"""Retain original FX inputs for lock-time computation freshness checks."""

from erev_api.db import migration_ops as ops

revision = "0340"
down_revision = "0339"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.computation_evidence ADD COLUMN fx_inputs jsonb")


def downgrade() -> None:
    ops.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM erev.computation_evidence WHERE fx_inputs IS NOT NULL) THEN
            RAISE EXCEPTION 'Cannot remove retained computation FX inputs';
          END IF;
        END $$
    """)
    ops.execute("ALTER TABLE erev.computation_evidence DROP COLUMN fx_inputs")
