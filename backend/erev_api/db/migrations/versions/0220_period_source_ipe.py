"""Describe retained recognition-period source attribution."""

from erev_api.db import migration_ops as ops

revision = "0220"
down_revision = "0219"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('mixed revenue inputs spanning original sources use retained recognition-period classes only when every source period is uniform TIME or EVENT and both currency TIME totals reconcile; mixed periods and unmatched functional allocation remain unavailable'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'mixed revenue inputs spanning original sources use retained recognition-period classes only when every source period is uniform TIME or EVENT and both currency TIME totals reconcile; mixed periods and unmatched functional allocation remain unavailable'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'mixed revenue inputs spanning original sources use retained recognition-period classes only when every source period is uniform TIME or EVENT and both currency TIME totals reconcile; mixed periods and unmatched functional allocation remain unavailable') "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
