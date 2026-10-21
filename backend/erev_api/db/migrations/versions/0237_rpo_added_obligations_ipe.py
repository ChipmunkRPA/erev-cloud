"""Document RPO classification of added obligations on existing contracts."""

from erev_api.db import migration_ops as ops

revision = "0237"
down_revision = "0236"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('new obligations added to an already disclosed "
        "contract follow modification and estimate causes instead of new contracts; first "
        "admission and re-entry keep admission rules; bindings without "
        "rpo_added_obligations_v1 retain their original classification'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'new obligations added to an already disclosed contract "
        "follow modification and estimate causes instead of new contracts; first admission "
        "and re-entry keep admission rules; bindings without rpo_added_obligations_v1 retain "
        "their original classification') WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
