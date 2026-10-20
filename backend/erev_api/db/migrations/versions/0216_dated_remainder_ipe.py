"""Describe dated recognition-hold remainder evidence."""

from erev_api.db import migration_ops as ops

revision = "0216"
down_revision = "0215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('scheduled and awaiting remainders use original period-level recognition-hold and pattern evidence reconciled to the version state; future holds do not alter earlier time-based projections'::text)) "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'scheduled and awaiting remainders use original period-level recognition-hold and pattern evidence reconciled to the version state; future holds do not alter earlier time-based projections'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'scheduled and awaiting remainders use original period-level recognition-hold and pattern evidence reconciled to the version state; future holds do not alter earlier time-based projections') "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
