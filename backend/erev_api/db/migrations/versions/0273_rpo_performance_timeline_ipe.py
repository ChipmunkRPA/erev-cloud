"""Include performance events in original ordered RPO eligibility timelines."""

from erev_api.db import migration_ops as ops

revision = "0273"
down_revision = "0272"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_initial_performance_timeline_v1 includes original delivery, return, billing "
    "and credit events in ordered initial eligibility timelines; net fixed allocation "
    "changes from performance and return-window expiry are VC movements while included; "
    "excluded changes enter with the remaining re-entry balance; exact before-event "
    "amounts separate time-only releases from subsequent monetary causes; required "
    "original positions cannot be replaced by date-only timelines; older bindings "
    "preserve their original interpretation"
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
