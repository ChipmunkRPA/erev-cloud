"""Require reviewed GL reconciliation sources for new report bindings."""

from erev_api.db import migration_ops as ops

revision = "0230"
down_revision = "0229"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('GL bridge v3 requires the latest retained reconciliation to be reviewed or certified; draft, prepared, reopened or missing status is unavailable; historical v1 and v2 bindings preserve their original arithmetic controls'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balances', 'contract_balance_rollforward') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'GL bridge v3 requires the latest retained reconciliation to be reviewed or certified; draft, prepared, reopened or missing status is unavailable; historical v1 and v2 bindings preserve their original arithmetic controls'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'GL bridge v3 requires the latest retained reconciliation to be reviewed or certified; draft, prepared, reopened or missing status is unavailable; historical v1 and v2 bindings preserve their original arithmetic controls') "  # noqa: E501
        "WHERE code IN ('contract_balances', 'contract_balance_rollforward') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
