"""Document reviewable monthly unexplained RPO differences."""

from erev_api.db import migration_ops as ops

revision = "0249"
down_revision = "0248"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('new converted runs retain unexplained_details by "
        "source contract, entity, period and currency with original and already-translated "
        "differences; nonzero source differences remain reviewable even when they offset or "
        "round to zero; earlier bindings keep their existing control totals'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'new converted runs retain unexplained_details by source "
        "contract, entity, period and currency with original and already-translated "
        "differences; nonzero source differences remain reviewable even when they offset or "
        "round to zero; earlier bindings keep their existing control totals') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
