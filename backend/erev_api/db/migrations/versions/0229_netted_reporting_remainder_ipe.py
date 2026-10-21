"""Describe source-backed Step-1 netted reporting forecasts."""

from erev_api.db import migration_ops as ops

revision = "0229"
down_revision = "0228"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('Step-1 netted forecasts freeze original deposit recognitions and cite their attributed shares; a separate dated reporting remainder excludes already-recognized deposit revenue while preserving contract measurement balances; projected future periods must reconcile to that net remainder'::text)) "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'Step-1 netted forecasts freeze original deposit recognitions and cite their attributed shares; a separate dated reporting remainder excludes already-recognized deposit revenue while preserving contract measurement balances; projected future periods must reconcile to that net remainder'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'Step-1 netted forecasts freeze original deposit recognitions and cite their attributed shares; a separate dated reporting remainder excludes already-recognized deposit revenue while preserving contract measurement balances; projected future periods must reconcile to that net remainder') "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
