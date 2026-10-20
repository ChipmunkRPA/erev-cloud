"""Describe first-entry batch estimate attribution."""

from erev_api.db import migration_ops as ops

revision = "0212"
down_revision = "0211"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('first-entry batches separate later estimate-event shares from new contracts when all changes fall within the range and no modification or cancellation competes'::text)) "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'first-entry batches separate later estimate-event shares from new contracts when all changes fall within the range and no modification or cancellation competes'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'first-entry batches separate later estimate-event shares from new contracts when all changes fall within the range and no modification or cancellation competes') "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
