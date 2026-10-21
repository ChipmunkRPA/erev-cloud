"""Describe mixed fixed and realized usage projection."""

from erev_api.db import migration_ops as ops

revision = "0227"
down_revision = "0226"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('manual projection freezes realized usage at the reporting cut and replays fixed plus PERIOD_VC targets without proportional allocation; schedule overrides retain anchor-period realized consideration and recognize subsequent usage immediately; royalty and netted projections remain unavailable'::text)) "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'manual projection freezes realized usage at the reporting cut and replays fixed plus PERIOD_VC targets without proportional allocation; schedule overrides retain anchor-period realized consideration and recognize subsequent usage immediately; royalty and netted projections remain unavailable'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'manual projection freezes realized usage at the reporting cut and replays fixed plus PERIOD_VC targets without proportional allocation; schedule overrides retain anchor-period realized consideration and recognize subsequent usage immediately; royalty and netted projections remain unavailable') "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
