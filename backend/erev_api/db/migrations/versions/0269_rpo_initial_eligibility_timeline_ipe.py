"""Retain initial RPO eligibility timelines and pre-exit projections."""

from erev_api.db import migration_ops as ops

revision = "0269"
down_revision = "0268"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_initial_eligibility_timeline_v1 reads original Step 1 status nodes and their "
    "dated source events for eligibility-only initial computations; retained source "
    "identity and amounts are preserved across entry, exit and re-entry slices; "
    "pre-exit deterministic schedules retain original-cut projections; monetary event "
    "batches and unavailable original evidence retain their previous behavior; older "
    "bindings retain their original version timeline"
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
