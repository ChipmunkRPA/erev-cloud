"""Retain original mapping content for forecast replay without publishing configuration."""

from erev_api.db import migration_ops as ops

revision = "0183"
down_revision = "0182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.import_upload ADD COLUMN forecast_mapping_snapshot jsonb NULL")
    ops.execute("""
        ALTER TABLE erev.import_upload ADD CONSTRAINT ck_import_upload__forecast_mapping
        CHECK (forecast_mapping_snapshot IS NULL OR (
            forecast_event_set_id IS NOT NULL AND mapping_profile_id IS NULL
            AND jsonb_typeof(forecast_mapping_snapshot) = 'object'
        ))
    """)


def downgrade() -> None:
    ops.execute("ALTER TABLE erev.import_upload DROP COLUMN forecast_mapping_snapshot")
