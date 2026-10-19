"""Describe the retained forecast/actual source contract in report IPE metadata."""

from erev_api.db import migration_ops as ops

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["forecast_run","report_run","scenario","tenant_snapshot","forecast_actuals_capture","file_object"],"joins":["scenario.tenant_snapshot_id binds the current production actuals capture","successful refresh lineage binds archived forecast reports to the logical scenario"],"filters":["periods inside the saved forecast horizon","current scenario and report entity permissions; exact forecast currency basis","acknowledged production revenue at snapshot cutoff; retained inputs only for same-source rebuild"],"parameters":["entity_codes","forecast_run_id","row_dimension","from_period_key","to_period_key","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'actual_vs_forecast\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["forecast_run","scenario","journal_line","period"],"joins":["journal_line.period_id = period.id"],"filters":["periods inside the horizon of forecast_run_id","actual revenue posted in the scenario tenant as of its latest refresh","entities in entity_codes"],"parameters":["entity_codes","forecast_run_id","row_dimension","from_period_key","to_period_key","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'actual_vs_forecast\' AND version = 1'  # noqa: E501


def _apply(statement: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(statement)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _apply(UP)


def downgrade() -> None:
    _apply(DOWN)
