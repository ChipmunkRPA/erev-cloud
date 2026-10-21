"""Document independent per-obligation cancellation attribution."""

from erev_api.db import migration_ops as ops

revision = "0251"
down_revision = "0250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_separate_cancellations_v1 permits multiple "
        "contract termination causes only when original per-obligation metadata identifies one "
        "actual cancellation and every other termination has an explicitly retained zero "
        "fixed-allocation change for that obligation; incomplete or nonzero cross-effects "
        "remain unexplained; older bindings keep prior classification'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_separate_cancellations_v1 permits multiple contract "
        "termination causes only when original per-obligation metadata identifies one actual "
        "cancellation and every other termination has an explicitly retained zero "
        "fixed-allocation change for that obligation; incomplete or nonzero cross-effects "
        "remain unexplained; older bindings keep prior classification') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
