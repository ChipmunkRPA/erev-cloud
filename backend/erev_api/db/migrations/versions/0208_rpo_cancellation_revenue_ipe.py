"""Describe terminal cancellation RPO and retained revenue attribution."""

from erev_api.db import migration_ops as ops

revision = "0208"
down_revision = "0207"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('terminal cancellations remove only unrecognized allocation; retained cancelled-version revenue separates period recognition and late restatement'::text)) "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'terminal cancellations remove only unrecognized allocation; retained cancelled-version revenue separates period recognition and late restatement'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'terminal cancellations remove only unrecognized allocation; retained cancelled-version revenue separates period recognition and late restatement') "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
