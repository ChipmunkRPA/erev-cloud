"""Describe retained reporting-currency aging translation."""

from erev_api.db import migration_ops as ops

revision = "0232"
down_revision = "0231"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('Reporting-currency aging translates supported functional age buckets at retained approved closing rates, rounds cumulative buckets to conserve the translated balance; balance tie-outs remain in functional currency; foreign transaction-currency aging without functional layer attribution remains unavailable; legacy bindings retain their original view'::text)) "  # noqa: E501
        "WHERE code = 'balance_aging' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'Reporting-currency aging translates supported functional age buckets at retained approved closing rates, rounds cumulative buckets to conserve the translated balance; balance tie-outs remain in functional currency; foreign transaction-currency aging without functional layer attribution remains unavailable; legacy bindings retain their original view'"  # noqa: E501
    )
    for source in ("tenant", "period", "fx_rate", "fx_rate_set", "fx_rate_set_version"):
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{source_tables}', "  # noqa: S608
            f"(ipe_logic->'source_tables') || to_jsonb('{source}'::text)) "
            "WHERE code = 'balance_aging' AND version = 1 "
            f"AND NOT (ipe_logic->'source_tables') ? '{source}'"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'Reporting-currency aging translates supported functional age buckets at retained approved closing rates, rounds cumulative buckets to conserve the translated balance; balance tie-outs remain in functional currency; foreign transaction-currency aging without functional layer attribution remains unavailable; legacy bindings retain their original view') "  # noqa: E501
        "WHERE code = 'balance_aging' AND version = 1"
    )
    for source in ("tenant", "period", "fx_rate", "fx_rate_set", "fx_rate_set_version"):
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{source_tables}', "  # noqa: S608
            f"(ipe_logic->'source_tables') - '{source}') "
            "WHERE code = 'balance_aging' AND version = 1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
