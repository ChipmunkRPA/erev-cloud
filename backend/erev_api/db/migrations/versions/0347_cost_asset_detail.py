"""Expose original cost-asset rollforward grouping."""

from erev_api.db import migration_ops as ops

revision = "0347"
down_revision = "0346"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute("""
        UPDATE erev.report_definition
        SET parameters_schema = jsonb_set(parameters_schema, '{properties,granularity}',
            '{"type":"string","enum":["category","asset"],"default":"category"}'::jsonb),
            ipe_logic = jsonb_set(ipe_logic, '{parameters}',
                (ipe_logic->'parameters') || '["granularity"]'::jsonb)
        WHERE code = 'contract_cost_rollforward' AND version = 1
    """)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute("""
        UPDATE erev.report_definition
        SET parameters_schema = parameters_schema #- '{properties,granularity}',
            ipe_logic = jsonb_set(ipe_logic, '{parameters}',
                (ipe_logic->'parameters') - 'granularity')
        WHERE code = 'contract_cost_rollforward' AND version = 1
    """)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
