"""Document original cancellation dates in historical RPO reads."""

from erev_api.db import migration_ops as ops

revision = "0242"
down_revision = "0241"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('original cancellation dates preserve "
        "pre-termination historical RPO and variance cuts; a single fixed-only first-entry or "
        "same-version cancellation separates original modifications and estimate changes from "
        "recognized revenue and cancelled remainder; traces without cancellation dates retain "
        "legacy behavior'::text)) WHERE code IN ('rpo','rpo_rollforward') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'original cancellation dates preserve pre-termination "
        "historical RPO and variance cuts; a single fixed-only first-entry or same-version "
        "cancellation separates original modifications and estimate changes from recognized "
        "revenue and cancelled remainder; traces without cancellation dates retain legacy "
        "behavior') WHERE code IN ('rpo','rpo_rollforward') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
