"""Document same-day fixed entry and cancellation RPO movements."""

from erev_api.db import migration_ops as ops

revision = "0250"
down_revision = "0249"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_same_day_entry_cancel_v1 preserves "
        "new-contract, recognized-revenue and cancellation movements for a single first "
        "fixed-only computation with same-day activation and original termination evidence; "
        "closing RPO remains zero and full exemptions still apply; other event mixtures and "
        "legacy bindings retain prior behavior'::text)) WHERE code='rpo_rollforward' AND "
        "version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_same_day_entry_cancel_v1 preserves new-contract, "
        "recognized-revenue and cancellation movements for a single first fixed-only "
        "computation with same-day activation and original termination evidence; closing RPO "
        "remains zero and full exemptions still apply; other event mixtures and legacy bindings "
        "retain prior behavior') WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
