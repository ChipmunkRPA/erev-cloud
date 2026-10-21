"""Document realized-fee attribution through cancelled version chains."""

from erev_api.db import migration_ops as ops

revision = "0246"
down_revision = "0245"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancelled_usage_v3 carries realized-fee "
        "attribution through subsequent versions only when every retained obligation stays "
        "cancelled and has dated realization evidence; final realized fees and recognized "
        "revenue use the final retained source, while original fixed changes retain their "
        "termination bridge; earlier v1 and v2 bindings preserve their classification'::text)) "
        "WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancelled_usage_v3 carries realized-fee attribution "
        "through subsequent versions only when every retained obligation stays cancelled and "
        "has dated realization evidence; final realized fees and recognized revenue use the "
        "final retained source, while original fixed changes retain their termination bridge; "
        "earlier v1 and v2 bindings preserve their classification') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
