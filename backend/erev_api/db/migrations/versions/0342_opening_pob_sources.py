"""Describe original obligation and locked disclosure sources in the opening report IPE."""

import json

from erev_api.db import migration_ops as ops

revision = "0342"
down_revision = "0341"
branch_labels = None
depends_on = None

ADDITIONS = {
    "source_tables": ["obligation_version", "report_run", "disclosure_snapshot"],
    "joins": [
        "POB subject keys join selected obligation versions to original "
        "billing/revenue trace nodes",
        "locked POB openings use the authenticated disclosure pack balance report source binding",
    ],
    "filters": [
        "New transaction and functional FIFO_WITHIN_POB runs use original obligation openings "
        "and range-net posted control revenue; group caps do not establish member ownership",
        "Functional POB billing requires complete original document coverage, including "
        "cancelling invoices and credits; revenue quantities reconcile to original transaction "
        "nodes; incomplete sources refuse and older bindings retain their original method",
    ],
}


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for key, values in ADDITIONS.items():
        literal = json.dumps(values).replace("'", "''")
        ops.execute(
            f"UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{{{key}}}', "  # noqa: S608
            f"(ipe_logic->'{key}') || '{literal}'::jsonb) "
            "WHERE code = 'revenue_from_opening_liability' AND version = 1"
        )

    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for key, values in ADDITIONS.items():
        literals = ",".join("'" + value.replace("'", "''") + "'" for value in values)
        ops.execute(
            f"UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{{{key}}}', "  # noqa: S608
            f"(ipe_logic->'{key}') - ARRAY[{literals}]::text[]) "
            "WHERE code = 'revenue_from_opening_liability' AND version = 1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
