"""Document original creation evidence for batched RPO additions."""

from erev_api.db import migration_ops as ops

revision = "0239"
down_revision = "0238"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('first-batch added obligations may omit "
        "pre-creation boundaries only with original absent-before creation evidence and "
        "independently retained earlier event order; zero allocation alone never proves "
        "absence and missing post-creation evidence remains unsupported'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'first-batch added obligations may omit pre-creation "
        "boundaries only with original absent-before creation evidence and independently "
        "retained earlier event order; zero allocation alone never proves absence and "
        "missing post-creation evidence remains unsupported') WHERE code='rpo_rollforward' "
        "AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
