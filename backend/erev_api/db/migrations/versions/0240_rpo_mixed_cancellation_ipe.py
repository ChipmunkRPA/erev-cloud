"""Document source-reconciled mixed RPO cancellations."""

from erev_api.db import migration_ops as ops

revision = "0240"
down_revision = "0239"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('mixed terminal cancellations separate original "
        "modification and estimate deltas only when they reconcile from opening fixed "
        "allocation to the retained pre-termination amount; missing or ambiguous event order "
        "remains unexplained and legacy bindings keep original classification'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'mixed terminal cancellations separate original "
        "modification and estimate deltas only when they reconcile from opening fixed "
        "allocation to the retained pre-termination amount; missing or ambiguous event order "
        "remains unexplained and legacy bindings keep original classification') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
