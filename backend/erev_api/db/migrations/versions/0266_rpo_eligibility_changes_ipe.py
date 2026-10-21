"""Separate RPO eligibility exits and criteria-met re-entry."""

from erev_api.db import migration_ops as ops

revision = "0266"
down_revision = "0265"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_eligibility_changes_v1 separately reports retained collectibility exits and "
    "criteria-met re-entry as contract eligibility changes; unchanged fixed "
    "allocation and dated realized evidence are required at exit; re-entry includes "
    "only the remaining balance and excludes prior-segment revenue; old bindings "
    "retain their original classification and report columns"
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
