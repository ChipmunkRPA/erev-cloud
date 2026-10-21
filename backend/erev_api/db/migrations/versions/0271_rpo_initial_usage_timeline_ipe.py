"""Use original event-date realization across initial RPO eligibility timelines."""

from erev_api.db import migration_ops as ops

revision = "0271"
down_revision = "0270"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_initial_usage_timeline_v1 assigns initial usage events to eligibility "
    "segments using original event-date realized allocations; fees realized before "
    "exit are VC movements and fees realized while excluded enter with the remaining "
    "re-entry balance; original date evidence is required and missing values are not "
    "replaced by month-end amounts; same-day ordered limitations remain; older "
    "bindings keep their prior timeline"
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
