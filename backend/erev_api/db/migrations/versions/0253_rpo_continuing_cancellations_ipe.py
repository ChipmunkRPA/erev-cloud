"""Attribute termination cross-effects before surviving obligations cancel."""

from erev_api.db import migration_ops as ops

revision = "0253"
down_revision = "0252"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_continuing_cancellations_v1 separates original "
        "partial-termination allocation changes for obligations still disclosed at the period "
        "end, in first-entry and same-version monthly cuts; every termination must retain "
        "explicit original state and the continuing obligation must not be cancelled within the "
        "cut; monthly fixed movements must reconcile to dated allocations; older bindings retain "
        "prior classification'::text)) WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_continuing_cancellations_v1 separates original "
        "partial-termination allocation changes for obligations still disclosed at the period "
        "end, in first-entry and same-version monthly cuts; every termination must retain "
        "explicit original state and the continuing obligation must not be cancelled within the "
        "cut; monthly fixed movements must reconcile to dated allocations; older bindings retain "
        "prior classification') WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
