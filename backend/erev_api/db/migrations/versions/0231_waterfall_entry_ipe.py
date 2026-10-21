"""Describe the dated waterfall population and retained entry sources."""

from erev_api.db import migration_ops as ops

revision = "0231"
down_revision = "0230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('Waterfall entry dates come from the first included contract version on its membership chain and its book-specific entry event; contracts entering after the performing entity as-of period are excluded; retained entry bindings and legacy populations remain unchanged on rerun'::text)) "  # noqa: E501
        "WHERE code = 'revenue_waterfall' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'Waterfall entry dates come from the first included contract version on its membership chain and its book-specific entry event; contracts entering after the performing entity as-of period are excluded; retained entry bindings and legacy populations remain unchanged on rerun'"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{source_tables}', "
        "(ipe_logic->'source_tables') || to_jsonb('contract_event'::text)) "
        "WHERE code = 'revenue_waterfall' AND version = 1 "
        "AND NOT (ipe_logic->'source_tables') ? 'contract_event'"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'Waterfall entry dates come from the first included contract version on its membership chain and its book-specific entry event; contracts entering after the performing entity as-of period are excluded; retained entry bindings and legacy populations remain unchanged on rerun') "  # noqa: E501
        "WHERE code = 'revenue_waterfall' AND version = 1"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{source_tables}', "
        "(ipe_logic->'source_tables') - 'contract_event') "
        "WHERE code = 'revenue_waterfall' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
