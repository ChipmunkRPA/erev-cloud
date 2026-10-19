"""Retain immutable production journal actuals alongside scenario snapshots."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_tenant_table(
        "forecast_actuals_capture",
        sa.Column("tenant_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_file_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_sha256", sa.CHAR(64), nullable=False),
        sa.Column("entity_ids", JSONB(), nullable=False),
        standard_sets=["SC-C"],
        unique=[
            ("ux_forecast_actuals_capture__snapshot", ["tenant_id", "tenant_snapshot_id"], None)
        ],
        checks=[("ck_forecast_actuals_capture__entities", "jsonb_typeof(entity_ids) = 'array'")],
    )
    ops.add_tenant_fk("forecast_actuals_capture", "tenant_snapshot_id", "tenant_snapshot")
    ops.add_tenant_fk("forecast_actuals_capture", "dataset_file_id", "file_object")
    ops.apply_class("forecast_actuals_capture", "IM-A")
    ops.enable_rls("forecast_actuals_capture", "RLS-T")


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.forecast_actuals_capture) THEN
        RAISE EXCEPTION 'Forecast actuals evidence exists; downgrade refused';
      END IF;
    END $$""")
    ops.drop_tenant_table("forecast_actuals_capture")
