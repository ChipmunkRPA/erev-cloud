"""Retain the designated human owner of an integration connection.

Historical connections remain unassigned until an owner is selected. A downgrade cannot
silently discard an assignment, including one outside the migration role's tenant context.
"""

from erev_api.db import migration_ops as ops

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.integration_connection ADD COLUMN owner_membership_id uuid")
    ops.add_tenant_fk("integration_connection", "owner_membership_id", "tenant_membership")


def downgrade() -> None:
    guard = "ck_integration_connection__0140_no_owner"
    ops.execute(
        f"ALTER TABLE erev.integration_connection ADD CONSTRAINT {guard} "
        "CHECK (owner_membership_id IS NULL) NOT VALID"
    )
    ops.execute(f"ALTER TABLE erev.integration_connection VALIDATE CONSTRAINT {guard}")
    ops.execute(f"ALTER TABLE erev.integration_connection DROP CONSTRAINT {guard}")
    ops.execute("ALTER TABLE erev.integration_connection DROP COLUMN owner_membership_id")
