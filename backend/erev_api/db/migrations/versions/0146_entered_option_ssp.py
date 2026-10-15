"""Preserve a total entered SSP on immutable material-right terms."""

from erev_api.db import migration_ops as ops

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.material_right ADD COLUMN entered_ssp_amount erev.money")
    ops.execute(
        "ALTER TABLE erev.material_right ADD CONSTRAINT ck_material_right__entered_ssp "
        "CHECK (entered_ssp_amount IS NULL OR "
        "(ssp_method = 'ENTERED_AMOUNT' AND entered_ssp_amount >= 0))"
    )


def downgrade() -> None:
    # Do not silently lose amounts or reprice existing contracts during downgrade.
    ops.execute(
        "ALTER TABLE erev.material_right ADD CONSTRAINT "
        "ck_material_right__entered_ssp_downgrade CHECK (entered_ssp_amount IS NULL)"
    )
    ops.execute("ALTER TABLE erev.material_right DROP COLUMN entered_ssp_amount")
