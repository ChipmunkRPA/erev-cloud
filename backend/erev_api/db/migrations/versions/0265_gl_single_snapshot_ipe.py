"""Read GL identities and captured states in one snapshot."""

from erev_api.db import migration_ops as ops

revision = "0265"
down_revision = "0264"
branch_labels = None
depends_on = None

NOTE = (
    "GL bridge v6 selects source identities and their latest captured states from "
    "immutable revisions in one database statement for all requested entities; a "
    "concurrent source change cannot mix identity and review snapshots; timestamp "
    "cutoffs still do not reconstruct arbitrary historical commit visibility; "
    "retained v1-v5 comparisons use their bound evidence unchanged"
)


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') || to_jsonb('" + NOTE + "'::text)) "
        "WHERE code IN ('contract_balances','contract_balance_rollforward') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 — static release note
        "(ipe_logic->'filters') - '" + NOTE + "') "
        "WHERE code IN ('contract_balances','contract_balance_rollforward') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
