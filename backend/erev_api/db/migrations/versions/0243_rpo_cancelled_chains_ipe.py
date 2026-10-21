"""Document cancellation attribution through retained version chains."""

from erev_api.db import migration_ops as ops

revision = "0243"
down_revision = "0242"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancelled_chains_v1 settles original "
        "first-batch and opening-version cancellations before later retained versions; "
        "subsequent cancelled versions carry current retained revenue and re-entry admits only "
        "its remaining allocation; legacy bindings retain prior classification'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancelled_chains_v1 settles original first-batch and "
        "opening-version cancellations before later retained versions; subsequent cancelled "
        "versions carry current retained revenue and re-entry admits only its remaining "
        "allocation; legacy bindings retain prior classification') WHERE code='rpo_rollforward' "
        "AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
