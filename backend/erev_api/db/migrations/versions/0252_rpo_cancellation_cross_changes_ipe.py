"""Attribute original partial-cancellation allocation cross-effects."""

from erev_api.db import migration_ops as ops

revision = "0252"
down_revision = "0251"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancellation_cross_changes_v1 attributes "
        "original fixed-allocation changes from earlier partial terminations to cancellations, "
        "including first-entry and monthly cuts; each termination must have explicit original "
        "state and nonzero cross-effects must precede the unique actual cancellation; the opening "
        "plus modifications, estimates and cross-effects must reproduce its original before "
        "amount for mixed later-version attribution; older bindings retain prior "
        "behavior'::text)) WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancellation_cross_changes_v1 attributes original "
        "fixed-allocation changes from earlier partial terminations to cancellations, including "
        "first-entry and monthly cuts; each termination must have explicit original state and "
        "nonzero cross-effects must precede the unique actual cancellation; the opening plus "
        "modifications, estimates and cross-effects must reproduce its original before amount for "
        "mixed later-version attribution; older bindings retain prior behavior') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
