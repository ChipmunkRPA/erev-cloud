"""Describe historical time-based schedule projections."""

from erev_api.db import migration_ops as ops

revision = "0214"
down_revision = "0213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('historical time-based schedules freeze the original allocation segment at the reporting cut; dated projections reconcile to the remainder and retain cut-specific drill-through'::text)) "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'historical time-based schedules freeze the original allocation segment at the reporting cut; dated projections reconcile to the remainder and retain cut-specific drill-through'"  # noqa: E501
    )
    ops.execute(
        'UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, \'{source_tables}\', \'["tenant", "fx_rate", "fx_rate_set", "fx_rate_set_version", "obligation_version", "schedule_line", "contract_version", "contract_computation", "computation_evidence", "contract", "customer", "product", "legal_entity", "period", "registry_version", "lock_snapshot", "combination_group_member"]\'::jsonb) WHERE code = \'rpo\' AND version = 1'  # noqa: E501
    )  # noqa: E501
    ops.execute(
        'UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, \'{source_tables}\', \'["schedule_line", "subledger_line", "tenant", "fx_rate", "fx_rate_set", "fx_rate_set_version", "contract_version", "obligation_version", "contract", "customer", "legal_entity", "product", "period", "journal_line", "lock_snapshot", "combination_group_member", "contract_computation"]\'::jsonb) WHERE code = \'revenue_waterfall\' AND version = 1'  # noqa: E501
    )  # noqa: E501
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'historical time-based schedules freeze the original allocation segment at the reporting cut; dated projections reconcile to the remainder and retain cut-specific drill-through') "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1"
    )
    ops.execute(
        'UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, \'{source_tables}\', \'["obligation_version", "schedule_line", "contract_version", "contract", "customer", "product", "legal_entity", "period", "registry_version", "lock_snapshot", "combination_group_member"]\'::jsonb) WHERE code = \'rpo\' AND version = 1'  # noqa: E501
    )  # noqa: E501
    ops.execute(
        'UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, \'{source_tables}\', \'["schedule_line", "contract_version", "obligation_version", "contract", "customer", "legal_entity", "product", "period", "journal_line", "lock_snapshot", "combination_group_member", "contract_computation"]\'::jsonb) WHERE code = \'revenue_waterfall\' AND version = 1'  # noqa: E501
    )  # noqa: E501
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
