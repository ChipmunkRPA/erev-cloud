"""Preserve original same-day RPO entry/cancellation across retained versions."""

from erev_api.db import migration_ops as ops

revision = "0258"
down_revision = "0257"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_same_day_entry_chains_v1 preserves original same-day activation and "
    "cancellation gross movements when subsequent retained versions exist; subsequent "
    "disclosure re-entry admits only its remaining balance, without duplicating pre- "
    "entry revenue; original termination boundaries and dated realization remain "
    "required; older bindings retain their single-version eligibility"
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
