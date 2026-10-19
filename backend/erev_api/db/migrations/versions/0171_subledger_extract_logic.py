"""Document sealed subledger extract sources and server cutoffs."""

from erev_api.db import migration_ops as ops

revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["subledger_line","subledger_posting_seal","contract","period","gl_account"],"joins":["subledger_line.contract_id = contract.id","subledger_line.subledger_posting_id = subledger_posting_seal.subledger_posting_id (same tenant/book)","subledger_line.period_id = period.id","subledger_line.origin_period_id = period.id (origin period)","subledger_line.gl_account_id = gl_account.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","subledger_line.recorded_at at or before the source time","source time is known_at; lock datasets unsupported","line recorded_server_at and posting sealed_server_at at or before source time","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_subledger_lines\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["subledger_line","contract","period","gl_account"],"joins":["subledger_line.contract_id = contract.id","subledger_line.period_id = period.id","subledger_line.origin_period_id = period.id (origin period)","subledger_line.gl_account_id = gl_account.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","subledger_line.recorded_at at or before the source time","source time: the lock of period_lock_id when given, else known_at","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_subledger_lines\' AND version = 1'  # noqa: E501


def _apply(statement: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(statement)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _apply(UP)


def downgrade() -> None:
    _apply(DOWN)
