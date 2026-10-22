"""Retain disclosed call evidence with original requester scope."""

import json

from erev_api.db import migration_ops as ops

revision = "0323"
down_revision = "0322"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["ai_model_log"], "joins": [], "filters": '
    '["Original requester scope and current source/export permissions"], "parameters": []}, '
    '"description": "Current authorized call evidence; reruns are new live evaluations."}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["ai_model_log"], "joins": [], "filters": '
    '["Original requester scope and current source/export permissions", "Same-source runs '
    "retain only disclosed API evidence, rebuild usage totals and recheck the original "
    'requester before reading retained content"], "parameters": []}, "description": '
    '"Authorized call evidence retained for same-source reconstruction with current access '
    'checks."}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column, value in json.loads(encoded).items():
        payload = (value if column == "description" else json.dumps(value)).replace("'", "''")
        cast = "" if column == "description" else "::jsonb"
        ops.execute(
            "UPDATE erev.report_definition SET "  # noqa: S608 — frozen metadata
            + column
            + "='"
            + payload
            + "'"
            + cast
            + " WHERE code='ai_call_log_export' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
