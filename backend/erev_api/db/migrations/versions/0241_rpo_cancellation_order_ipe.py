"""Document immutable event ordering for same-day RPO cancellation changes."""

from erev_api.db import migration_ops as ops

revision = "0241"
down_revision = "0240"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('mixed cancellation v2 admits same-day estimate "
        "changes only when immutable contract-event record sequence proves they precede the "
        "original termination boundary; later or missing order remains unexplained; retained "
        "v1 keeps its date-only classification'::text)) WHERE code='rpo_rollforward' AND "
        "version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'mixed cancellation v2 admits same-day estimate changes "
        "only when immutable contract-event record sequence proves they precede the original "
        "termination boundary; later or missing order remains unexplained; retained v1 keeps "
        "its date-only classification') WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
