"""Retain shared estimate member bindings under the version's existing immutable-state guard."""

from erev_api.db import migration_ops as ops

revision = "0343"
down_revision = "0342"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.estimate_version ADD COLUMN portfolio_application_basis jsonb")
    ops.execute(
        "ALTER TABLE erev.estimate_version ADD CONSTRAINT ck_estimate_version__portfolio_basis "
        "CHECK (portfolio_application_basis IS NULL OR "
        "jsonb_typeof(portfolio_application_basis) = 'object')"
    )
    ops.execute(
        "GRANT UPDATE (portfolio_application_basis) ON TABLE erev.estimate_version TO erev_app"
    )


def downgrade() -> None:
    ops.execute("ALTER TABLE erev.estimate_version DROP COLUMN portfolio_application_basis")
