"""Retain monthly unexplained differences in transaction-currency RPO reports."""

from erev_api.db import migration_ops as ops

revision = "0255"
down_revision = "0254"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_transaction_monthly_gaps_v1 checks each original "
        "contract/entity/period in transaction currency before range-level netting; any nonzero "
        "source difference fails the rollforward tie-out even when months offset, and "
        "unexplained_details retains the original amount unchanged in report currency for viewer "
        "and exports; period cuts and the rule are retained for reruns; older transaction "
        "bindings keep their previous range-level checks'::text)) WHERE code='rpo_rollforward' "
        "AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_transaction_monthly_gaps_v1 checks each original "
        "contract/entity/period in transaction currency before range-level netting; any nonzero "
        "source difference fails the rollforward tie-out even when months offset, and "
        "unexplained_details retains the original amount unchanged in report currency for viewer "
        "and exports; period cuts and the rule are retained for reruns; older transaction "
        "bindings keep their previous range-level checks') WHERE code='rpo_rollforward' AND "
        "version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
