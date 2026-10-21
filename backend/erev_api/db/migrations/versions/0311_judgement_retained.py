"""Retain judgement-register inputs and withheld population counts."""

import json

from erev_api.db import migration_ops as ops

revision = "0311"
down_revision = "0310"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["judgement_record", "contract", '
    '"app_user"], "joins": ["judgement_record.contract_id = contract.id", '
    '"judgement_record.reviewer_id = app_user.id", "judgement_record.supersedes_id = '
    'judgement_record.id"], "filters": ["entity code in entity_codes and within the caller\'s '
    'entity scope", "recorded from from_date to to_date inclusive", "topic and status when '
    'given"], "parameters": ["entity_codes", "book", "from_date", "to_date", "topic", '
    '"status", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["judgement_record", "contract", '
    '"app_user"], "joins": ["judgement_record.contract_id = contract.id", '
    '"judgement_record.reviewer_id = app_user.id", "judgement_record.supersedes_id = '
    'judgement_record.id"], "filters": ["same-source runs retain judgement inputs, '
    "subject/actor labels, resolved dates and withheld count; rebuild rows and totals without"
    ' live reads", "entity code in entity_codes and within the caller\'s entity scope", '
    '"recorded from from_date to to_date inclusive", "topic and status when given"], '
    '"parameters": ["entity_codes", "book", "from_date", "to_date", "topic", "status", '
    '"known_at", "known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column, value in json.loads(encoded).items():
        payload = json.dumps(value).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET "  # noqa: S608 — frozen metadata
            + column
            + "='"
            + payload
            + "'::jsonb WHERE code='judgement_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
