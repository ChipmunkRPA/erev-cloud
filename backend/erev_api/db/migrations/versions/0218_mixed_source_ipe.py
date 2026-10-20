"""Describe exact mixed-input TIME attribution with unique original provenance."""

from erev_api.db import migration_ops as ops

revision = "0218"
down_revision = "0217"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('mixed revenue inputs use retained per-input TIME amounts in both currencies only when original sources have one contract, layer, movement kind, date and source identity; ambiguous ownership is not proportionally assigned'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'mixed revenue inputs use retained per-input TIME amounts in both currencies only when original sources have one contract, layer, movement kind, date and source identity; ambiguous ownership is not proportionally assigned'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'mixed revenue inputs use retained per-input TIME amounts in both currencies only when original sources have one contract, layer, movement kind, date and source identity; ambiguous ownership is not proportionally assigned') "  # noqa: E501
        "WHERE code IN ('contract_balance_rollforward', 'revenue_from_opening_liability') "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
