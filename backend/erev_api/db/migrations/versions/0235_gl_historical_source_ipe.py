"""State the latest-source historical GL comparison rule."""

from erev_api.db import migration_ops as ops

revision = "0235"
down_revision = "0234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('GL bridge v4 selects the latest source identity "
        "before checking mutable state; a source changed after the report cutoff is unavailable "
        "and never replaced by an older reviewed source; retained v1-v3 bindings remain "
        "unchanged'::text)) WHERE code IN ('contract_balances', 'contract_balance_rollforward') "
        "AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'GL bridge v4 selects the latest source identity "
        "before checking mutable state; a source changed after the report cutoff is unavailable "
        "and never replaced by an older reviewed source; retained v1-v3 bindings remain "
        "unchanged') WHERE code IN ('contract_balances', 'contract_balance_rollforward') "
        "AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
