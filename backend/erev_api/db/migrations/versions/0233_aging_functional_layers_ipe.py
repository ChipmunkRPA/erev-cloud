"""Describe original functional-layer aging evidence."""

from erev_api.db import migration_ops as ops

revision = "0233"
down_revision = "0232"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', ((ipe_logic->'filters') - 'Reporting-currency aging translates supported functional age buckets at retained approved closing rates, rounds cumulative buckets to conserve the translated balance; balance tie-outs remain in functional currency; foreign transaction-currency aging without functional layer attribution remains unavailable; legacy bindings retain their original view') || to_jsonb('Functional aging uses retained original reclass shares for assets and unbilled receivables and signed functional liability-layer movements with original dates; each member and role must reconcile to dated functional balances; reporting view uses retained closing rates and cumulative bucket rounding; legacy bindings retain original behavior'::text)) WHERE code='balance_aging' AND version=1"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') || to_jsonb('contract_version'::text)) WHERE code='balance_aging' AND version=1 AND NOT (ipe_logic->'source_tables') ? 'contract_version'"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') || to_jsonb('contract_computation'::text)) WHERE code='balance_aging' AND version=1 AND NOT (ipe_logic->'source_tables') ? 'contract_computation'"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') || to_jsonb('combination_group_member'::text)) WHERE code='balance_aging' AND version=1 AND NOT (ipe_logic->'source_tables') ? 'combination_group_member'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', ((ipe_logic->'filters') - 'Functional aging uses retained original reclass shares for assets and unbilled receivables and signed functional liability-layer movements with original dates; each member and role must reconcile to dated functional balances; reporting view uses retained closing rates and cumulative bucket rounding; legacy bindings retain original behavior') || to_jsonb('Reporting-currency aging translates supported functional age buckets at retained approved closing rates, rounds cumulative buckets to conserve the translated balance; balance tie-outs remain in functional currency; foreign transaction-currency aging without functional layer attribution remains unavailable; legacy bindings retain their original view'::text)) WHERE code='balance_aging' AND version=1"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') - 'contract_version') WHERE code='balance_aging' AND version=1"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') - 'contract_computation') WHERE code='balance_aging' AND version=1"  # noqa: E501
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') - 'combination_group_member') WHERE code='balance_aging' AND version=1"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
