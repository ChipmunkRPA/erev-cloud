"""Freeze original balance aging with all three currency views on new locks."""

from erev_api.db import migration_ops as ops

revision = "0234"
down_revision = "0233"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.add_enum_value("snapshot_kind", "BALANCE_AGING", after="WATERFALL")
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set("
        "jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') || "
        "to_jsonb('lock_snapshot'::text)), '{filters}', (ipe_logic->'filters') || "
        "to_jsonb('with period_lock_id, the values frozen at that lock "
        "(lock_snapshot kind BALANCE_AGING)'::text)) WHERE code='balance_aging' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    # Retained aging snapshots cannot be discarded to make a downgrade succeed.
    ops.remove_enum_value("snapshot_kind", "BALANCE_AGING")
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set("
        "jsonb_set(ipe_logic, '{source_tables}', (ipe_logic->'source_tables') - "
        "'lock_snapshot'), '{filters}', (ipe_logic->'filters') - "
        "'with period_lock_id, the values frozen at that lock (lock_snapshot kind BALANCE_AGING)') "
        "WHERE code='balance_aging' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
