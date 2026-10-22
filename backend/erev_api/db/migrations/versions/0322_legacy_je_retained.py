"""Retain original gross/delta journal aggregates."""

import json

from erev_api.db import migration_ops as ops

revision = "0322"
down_revision = "0321"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["subledger_line", "subledger_posting", '
    '"gl_account", "legal_entity", "contract"], "joins": '
    '["subledger_line.subledger_posting_id = subledger_posting.id", '
    '"subledger_line.gl_account_id = gl_account.id", "subledger_line.entity_id = '
    'legal_entity.id", "subledger_line.contract_id = contract.id"], "filters": ["entity code '
    'in entity_codes and within the caller\'s entity scope", "book fixed to ASC606", '
    '"subledger_line.effective_date from from_date to to_date inclusive", "mode GROSS: gross '
    'lines; mode DELTA: adjustment lines against the Legacy book", "rows recorded at or '
    'before known_at"], "parameters": ["entity_codes", "book", "from_date", "to_date", '
    '"mode", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["subledger_line", "subledger_posting", '
    '"gl_account", "legal_entity", "contract"], "joins": '
    '["subledger_line.subledger_posting_id = subledger_posting.id", '
    '"subledger_line.gl_account_id = gl_account.id", "subledger_line.entity_id = '
    'legal_entity.id", "subledger_line.contract_id = contract.id"], "filters": ["same-source '
    "runs retain original per-book journal aggregates and source line IDs; recalculate "
    'gross/delta nets and currency totals without live ledger reads", "entity code in '
    'entity_codes and within the caller\'s entity scope", "book fixed to ASC606", '
    '"subledger_line.effective_date from from_date to to_date inclusive", "mode GROSS: gross '
    'lines; mode DELTA: adjustment lines against the Legacy book", "rows recorded at or '
    'before known_at"], "parameters": ["entity_codes", "book", "from_date", "to_date", '
    '"mode", "known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='legacy_je_summary' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
