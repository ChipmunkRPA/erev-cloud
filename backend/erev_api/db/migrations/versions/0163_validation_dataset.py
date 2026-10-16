"""Add the encrypted frozen validation dataset file purpose (D-96, PRV-06)."""

from erev_api.db import migration_ops as ops

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.add_enum_value("file_purpose", "VALIDATION_DATASET")


def downgrade() -> None:
    # remove_enum_value refuses while retained file rows still use the purpose.
    ops.remove_enum_value("file_purpose", "VALIDATION_DATASET")
