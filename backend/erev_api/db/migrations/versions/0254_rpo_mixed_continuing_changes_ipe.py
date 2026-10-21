"""Attribute mixed causes while an obligation remains disclosed."""

from erev_api.db import migration_ops as ops

revision = "0254"
down_revision = "0253"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_mixed_continuing_changes_v1 separates original "
        "modification, estimate and partial-termination effects in a later retained version while "
        "the obligation remains disclosed; original event coverage and dates are required and "
        "their fixed amounts must sum to the actual version change; missing evidence or "
        "mismatched amounts remain unexplained; older bindings retain prior attribution'::text)) "
        "WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_mixed_continuing_changes_v1 separates original "
        "modification, estimate and partial-termination effects in a later retained version while "
        "the obligation remains disclosed; original event coverage and dates are required and "
        "their fixed amounts must sum to the actual version change; missing evidence or "
        "mismatched amounts remain unexplained; older bindings retain prior attribution') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
