"""Describe dated fixed-allocation evidence for historical RPO."""

from erev_api.db import migration_ops as ops

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('dated fixed-allocation evidence reconciles to version remainders and excludes future estimate changes from earlier RPO; same-version estimate movements require complete original shares matching the dated allocation difference'::text)) "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'dated fixed-allocation evidence reconciles to version remainders and excludes future estimate changes from earlier RPO; same-version estimate movements require complete original shares matching the dated allocation difference'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'dated fixed-allocation evidence reconciles to version remainders and excludes future estimate changes from earlier RPO; same-version estimate movements require complete original shares matching the dated allocation difference') "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
