"""Describe the retained three-way GL reconciliation bridge."""

from erev_api.db import migration_ops as ops

revision = "0219"
down_revision = "0218"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('GL bridge v2 compares report, retained reconciliation subledger and GL per entity and role in functional currency; either nonzero leg fails even when net differences cancel; missing subledger evidence is unavailable and v1 bindings retain two-way semantics'::text)) "  # noqa: E501
        "WHERE code IN ('contract_balances', 'contract_balance_rollforward') "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'GL bridge v2 compares report, retained reconciliation subledger and GL per entity and role in functional currency; either nonzero leg fails even when net differences cancel; missing subledger evidence is unavailable and v1 bindings retain two-way semantics'"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{source_tables}', "
        '(ipe_logic->\'source_tables\') || \'["tenant", "fx_rate", "fx_rate_set", "fx_rate_set_version"]\'::jsonb) '  # noqa: E501
        "WHERE code = 'contract_balances' AND version = 1 "
        "AND NOT (ipe_logic->'source_tables') ? 'tenant'"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'GL bridge v2 compares report, retained reconciliation subledger and GL per entity and role in functional currency; either nonzero leg fails even when net differences cancel; missing subledger evidence is unavailable and v1 bindings retain two-way semantics') "  # noqa: E501
        "WHERE code IN ('contract_balances', 'contract_balance_rollforward') "
        "AND version = 1"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{source_tables}', "
        "(ipe_logic->'source_tables') - 'tenant' - 'fx_rate' - 'fx_rate_set' - 'fx_rate_set_version') "  # noqa: E501
        "WHERE code = 'contract_balances' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
