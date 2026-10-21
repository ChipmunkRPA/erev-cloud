"""Document realized-fee attribution across disclosure re-entry."""

from erev_api.db import migration_ops as ops

revision = "0247"
down_revision = "0246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancelled_usage_v4 reads realized fees for "
        "each retained cancellation segment through the next re-entry cut; re-entry admits its "
        "fixed plus realized allocation net of prior revenue and removes pre-entry realized "
        "fees from in-scope VC changes; retained v1-v3 bindings preserve prior "
        "classification'::text)) WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancelled_usage_v4 reads realized fees for each retained "
        "cancellation segment through the next re-entry cut; re-entry admits its fixed plus "
        "realized allocation net of prior revenue and removes pre-entry realized fees from "
        "in-scope VC changes; retained v1-v3 bindings preserve prior classification') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
