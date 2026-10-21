"""Retain evidenced inception estimates in same-day entry movements."""

from erev_api.db import migration_ops as ops

revision = "0262"
down_revision = "0261"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_same_day_entry_estimates_v1 retains original inception estimates in new- "
    "contract amounts when activation and termination share a day; every estimate "
    "requires an original INCEPTION pin and an admission-date event; amendments "
    "remain separately classified from original boundaries; missing evidence and "
    "older bindings retain their previous eligibility"
)


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') || to_jsonb('" + NOTE + "'::text)) "
        "WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') - '" + NOTE + "') "
        "WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
