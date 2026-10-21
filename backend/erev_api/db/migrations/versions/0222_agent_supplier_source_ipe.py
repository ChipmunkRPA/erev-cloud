"""Describe retained agent gross/net supplier source attribution."""

from erev_api.db import migration_ops as ops

revision = "0222"
down_revision = "0221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('agent gross control relief is reconciled to separately retained net revenue and AP_SUPPLIER components in both currencies; split targets require unique original source ownership and supplier history capability, otherwise attribution is unavailable'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'agent gross control relief is reconciled to separately retained net revenue and AP_SUPPLIER components in both currencies; split targets require unique original source ownership and supplier history capability, otherwise attribution is unavailable'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'agent gross control relief is reconciled to separately retained net revenue and AP_SUPPLIER components in both currencies; split targets require unique original source ownership and supplier history capability, otherwise attribution is unavailable') "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
