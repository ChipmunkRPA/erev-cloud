"""Carry original pending RPO cancellation across intervening versions."""

from erev_api.db import migration_ops as ops

revision = "0259"
down_revision = "0258"
branch_labels = None
depends_on = None

NOTE = (
    "rpo_pretermination_versions_v1 carries original pre-termination fixed balances "
    "across intervening retained versions instead of settling a future cancellation "
    "early; the superseding computation determines the pending termination and "
    "version deltas retain their own cause attribution; original boundary and dated "
    "realization guards remain required; older bindings retain prior treatment"
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
