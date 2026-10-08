"""Notify access administrators when an approval has no independent active-step decider."""

from erev_api.db import migration_ops as ops

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.add_enum_value("notification_kind", "APPROVAL_UNASSIGNED")


def downgrade() -> None:
    # Refuses downgrade while retained notifications/preferences still use the new kind.
    ops.remove_enum_value("notification_kind", "APPROVAL_UNASSIGNED")
