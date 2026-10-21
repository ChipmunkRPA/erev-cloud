"""Describe zero-net agent supplier attribution."""

from erev_api.db import migration_ops as ops

revision = "0223"
down_revision = "0222"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('zero-net agent control relief uses its sole retained AP_SUPPLIER counterpart, with no synthetic revenue line; supplier amounts and original signed sources must reconcile in both currencies'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'zero-net agent control relief uses its sole retained AP_SUPPLIER counterpart, with no synthetic revenue line; supplier amounts and original signed sources must reconcile in both currencies'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'zero-net agent control relief uses its sole retained AP_SUPPLIER counterpart, with no synthetic revenue line; supplier amounts and original signed sources must reconcile in both currencies') "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
