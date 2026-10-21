"""Describe retained TIME deltas for mixed recognition periods."""

from erev_api.db import migration_ops as ops

revision = "0224"
down_revision = "0223"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('mixed recognition periods may use retained transaction and functional TIME target deltas only with one original provenance per mixed period; totals must reconcile in both currencies and ambiguous within-period owners remain unavailable'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'mixed recognition periods may use retained transaction and functional TIME target deltas only with one original provenance per mixed period; totals must reconcile in both currencies and ambiguous within-period owners remain unavailable'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'mixed recognition periods may use retained transaction and functional TIME target deltas only with one original provenance per mixed period; totals must reconcile in both currencies and ambiguous within-period owners remain unavailable') "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
