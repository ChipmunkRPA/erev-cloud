"""Bind forecast file imports immutably to their scenario input set."""

from erev_api.db import migration_ops as ops

revision = "0181"
down_revision = "0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.import_upload ADD COLUMN forecast_event_set_id uuid NULL")
    ops.add_tenant_fk("import_upload", "forecast_event_set_id", "forecast_event_set")
    ops.execute("""
        CREATE INDEX ix_import_upload__forecast_event_set
        ON erev.import_upload (tenant_id, forecast_event_set_id)
        WHERE forecast_event_set_id IS NOT NULL
    """)


def downgrade() -> None:
    ops.execute("ALTER TABLE erev.import_upload DROP COLUMN forecast_event_set_id")
