"""Describe original-cut royalty manual projection."""

from erev_api.db import migration_ops as ops

revision = "0228"
down_revision = "0227"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('royalty manual projections freeze original statements and effective estimate pins at the reporting cut; minimum guarantees and recognized royalty sources must remain stable over the frozen horizon; schedule overrides retain anchor royalties and subsequent signed royalty changes separately'::text)) "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'royalty manual projections freeze original statements and effective estimate pins at the reporting cut; minimum guarantees and recognized royalty sources must remain stable over the frozen horizon; schedule overrides retain anchor royalties and subsequent signed royalty changes separately'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'royalty manual projections freeze original statements and effective estimate pins at the reporting cut; minimum guarantees and recognized royalty sources must remain stable over the frozen horizon; schedule overrides retain anchor royalties and subsequent signed royalty changes separately') "  # noqa: E501
        "WHERE code IN ('rpo', 'rpo_rollforward', 'revenue_waterfall') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
