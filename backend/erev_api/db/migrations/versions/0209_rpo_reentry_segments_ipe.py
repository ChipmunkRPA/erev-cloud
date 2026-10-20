"""Describe segmented cancellation and re-entry RPO attribution."""

from erev_api.db import migration_ops as ops

revision = "0209"
down_revision = "0208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('cancellation and re-entry histories use separate disclosure segments; re-entry admits remaining RPO and revenue excludes changes while outside disclosure'::text)) "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'cancellation and re-entry histories use separate disclosure segments; re-entry admits remaining RPO and revenue excludes changes while outside disclosure'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'cancellation and re-entry histories use separate disclosure segments; re-entry admits remaining RPO and revenue excludes changes while outside disclosure') "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
