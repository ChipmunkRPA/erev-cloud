"""Preserve source aging with separate combined-member allocation adjustments."""

from erev_api.db import migration_ops as ops

revision = "0260"
down_revision = "0259"
branch_labels = None
depends_on = None

NOTE = (
    "aging_member_adjustments_v1 preserves original receiving-contract liability ages "
    "and shows member allocation adjustments separately without an age; complete "
    "retained engine member populations and conservation of original layers are "
    "required; totals include the adjustment and original zero-net owners remain "
    "visible; older bindings retain their previous schema and treatment"
)


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') || to_jsonb('" + NOTE + "'::text)) "
        "WHERE code='balance_aging' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') - '" + NOTE + "') "
        "WHERE code='balance_aging' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
