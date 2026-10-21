"""Describe source-backed member refund presentation."""

from erev_api.db import migration_ops as ops

revision = "0226"
down_revision = "0225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('combined-member refunds classify billing from retained asset and liability sources even when asset consumption is zero; full-return recipients replay original negative postings when latest targets no longer retain prior consumed layers'::text)) "  # noqa: E501
        "WHERE code = 'contract_balance_rollforward' "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'combined-member refunds classify billing from retained asset and liability sources even when asset consumption is zero; full-return recipients replay original negative postings when latest targets no longer retain prior consumed layers'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'combined-member refunds classify billing from retained asset and liability sources even when asset consumption is zero; full-return recipients replay original negative postings when latest targets no longer retain prior consumed layers') "  # noqa: E501
        "WHERE code = 'contract_balance_rollforward' "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
