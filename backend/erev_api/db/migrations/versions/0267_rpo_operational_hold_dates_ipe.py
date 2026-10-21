"""Preserve RPO business dates across operational review holds."""

from erev_api.db import migration_ops as ops

revision = "0267"
down_revision = "0266"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_operational_hold_dates_v1 dates retained RPO versions by business events; "
    "HOLD_APPLIED and HOLD_RELEASED do not move a business change into the "
    "operational review month; hold-only computations keep the prior business date "
    "and original dated projection evidence; older bindings retain their original "
    "version dates; database trace reads preserve projection cut, period_key and "
    "refusal reason"
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
