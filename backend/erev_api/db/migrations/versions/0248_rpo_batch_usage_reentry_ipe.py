"""Document first-batch realized-fee cancellation followed by re-entry."""

from erev_api.db import migration_ops as ops

revision = "0248"
down_revision = "0247"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancelled_usage_v5 settles original "
        "first-batch and opening-version realized-fee cancellation at the next retained "
        "re-entry cut, including intervening cancelled corrections, before admitting the new "
        "remaining allocation; retained v1-v4 preserve their classification'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancelled_usage_v5 settles original first-batch and "
        "opening-version realized-fee cancellation at the next retained re-entry cut, including "
        "intervening cancelled corrections, before admitting the new remaining allocation; "
        "retained v1-v4 preserve their classification') WHERE code='rpo_rollforward' AND "
        "version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
