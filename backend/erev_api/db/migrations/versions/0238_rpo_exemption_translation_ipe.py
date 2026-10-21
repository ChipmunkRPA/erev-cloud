"""Document monthly translated RPO exemption movements."""

from erev_api.db import migration_ops as ops

revision = "0238"
down_revision = "0237"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('translated RPO exemption details retain each "
        "contract-period original movement and its monthly-average translated amount; "
        "details sum by report currency to EXEMPTIONS even when original range endpoints "
        "cancel; older bindings keep their existing controls'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'translated RPO exemption details retain each "
        "contract-period original movement and its monthly-average translated amount; "
        "details sum by report currency to EXEMPTIONS even when original range endpoints "
        "cancel; older bindings keep their existing controls') WHERE code='rpo_rollforward' "
        "AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
