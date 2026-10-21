"""Use original event positions across initial RPO eligibility timelines."""

from erev_api.db import migration_ops as ops

revision = "0272"
down_revision = "0271"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_initial_ordered_timeline_v1 attributes initial eligibility and monetary events "
    "in original date, record sequence and event-key order; original before/after "
    "allocation, realization and revenue evidence separates same-day exits and "
    "re-entries; changes while excluded enter with the remaining re-entry balance; "
    "missing required positions are not replaced with day-end amounts; historical "
    "bindings preserve their original timeline"
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
