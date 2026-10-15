"""Admit the engine's point-in-time royalty licence pattern (S09-R-33; POL-024)."""

from erev_api.db import migration_ops as ops

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None

BASE = (
    "satisfaction_pattern <> 'POINT_IN_TIME' "
    "OR recognition_method IN ('POINT_IN_TIME', 'UNITS_DELIVERED', 'MANUAL')"
)


def _replace(expression: str) -> None:
    ops.execute(
        "ALTER TABLE erev.pob_template_version "
        "DROP CONSTRAINT ck_pob_template_version__point_in_time_method"
    )
    ops.execute(
        "ALTER TABLE erev.pob_template_version "
        "ADD CONSTRAINT ck_pob_template_version__point_in_time_method CHECK (" + expression + ")"
    )


def upgrade() -> None:
    _replace(BASE + " OR (obligation_kind = 'LICENCE' AND recognition_method = 'ROYALTY')")


def downgrade() -> None:
    # Existing royalty licences make this fail rather than discard or rewrite their terms.
    _replace(BASE)
