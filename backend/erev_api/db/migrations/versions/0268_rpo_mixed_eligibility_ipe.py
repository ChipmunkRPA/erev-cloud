"""Separate mixed allocation changes from RPO eligibility exits."""

from erev_api.db import migration_ops as ops

revision = "0268"
down_revision = "0267"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_mixed_eligibility_v1 separates original amendment and estimate allocations "
    "from retained collectibility exits; complete event evidence dated no later than "
    "the exit must reconcile the fixed change; dated realized fees remain VC movements "
    "and the resulting remaining balance leaves through eligibility changes; older "
    "bindings retain their previous classification"
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
