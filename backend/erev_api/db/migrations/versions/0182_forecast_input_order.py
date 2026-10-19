"""Retain the application order across API and file forecast inputs."""

from erev_api.db import migration_ops as ops

revision = "0182"
down_revision = "0181"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means historical order was not recorded; never invent an order for existing inputs.
    ops.execute("ALTER TABLE erev.forecast_event_set ADD COLUMN input_sequence jsonb NULL")
    ops.execute("""
        ALTER TABLE erev.forecast_event_set ADD CONSTRAINT ck_forecast_event_set__input_sequence
        CHECK (input_sequence IS NULL OR jsonb_typeof(input_sequence) = 'array')
    """)


def downgrade() -> None:
    ops.execute("ALTER TABLE erev.forecast_event_set DROP COLUMN input_sequence")
