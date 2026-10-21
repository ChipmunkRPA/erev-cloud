"""Document realized-fee attribution within a cancellation computation."""

from erev_api.db import migration_ops as ops

revision = "0245"
down_revision = "0244"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancelled_usage_v2 also separates dated "
        "realized fees in a single first-entry cancellation computation or an "
        "opening-to-closing cancellation within one retained version; realized changes are VC "
        "movements and cancellation removes fixed plus realized remainder net of recognized "
        "revenue; retained v1 keeps its later-version-only behavior'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancelled_usage_v2 also separates dated realized fees in "
        "a single first-entry cancellation computation or an opening-to-closing cancellation "
        "within one retained version; realized changes are VC movements and cancellation "
        "removes fixed plus realized remainder net of recognized revenue; retained v1 keeps its "
        "later-version-only behavior') WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
