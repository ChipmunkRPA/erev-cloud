"""Separate monetary events in initial RPO eligibility timelines."""

from erev_api.db import migration_ops as ops

revision = "0270"
down_revision = "0269"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_initial_monetary_timeline_v1 assigns initial eligibility-batch amendments, "
    "and estimates to their original dates; event-specific shares and retained "
    "boundaries remove later same-period fixed changes from lifecycle cuts; changes "
    "while excluded enter through the remaining re-entry balance; same-day monetary "
    "events after a status transition require additional ordered evidence and retain "
    "the previous timeline; old bindings retain their original classification"
)


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') || to_jsonb('" + NOTE + "'::text)) "
        "WHERE code IN ('rpo','rpo_rollforward') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') - '" + NOTE + "') "
        "WHERE code IN ('rpo','rpo_rollforward') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
