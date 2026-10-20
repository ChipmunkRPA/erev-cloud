"""Describe manual schedule projection at the reporting cut."""

from erev_api.db import migration_ops as ops

revision = "0217"
down_revision = "0216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('fixed-only manual releases, deferrals and schedule overrides replay only events effective at the reporting cut; unsupported component mixtures or unreproducible snapshots retain explicit projection errors'::text)) "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'fixed-only manual releases, deferrals and schedule overrides replay only events effective at the reporting cut; unsupported component mixtures or unreproducible snapshots retain explicit projection errors'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'fixed-only manual releases, deferrals and schedule overrides replay only events effective at the reporting cut; unsupported component mixtures or unreproducible snapshots retain explicit projection errors') "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
