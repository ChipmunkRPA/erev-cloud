"""Document journal extract source-time lifecycle evidence."""

from erev_api.db import migration_ops as ops

revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["journal_line","journal_entry","journal_batch","journal_run","period","audit_event"],"joins":["journal_line.journal_entry_id = journal_entry.id","journal_line.journal_batch_id = journal_batch.id","journal_batch.journal_run_id = journal_run.id","journal_line.period_id = period.id","audit_event run and batch lifecycle transitions resolve run state at source time"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","runs not cancelled as of known_at; unknown historical state refuses","line/entry/batch/run created by known_at; lock datasets unsupported","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_journal_lines\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["journal_line","journal_entry","journal_batch","journal_run","period"],"joins":["journal_line.journal_entry_id = journal_entry.id","journal_line.journal_batch_id = journal_batch.id","journal_batch.journal_run_id = journal_run.id","journal_line.period_id = period.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","runs not cancelled","source time: the lock of period_lock_id when given, else known_at","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_journal_lines\' AND version = 1'  # noqa: E501


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
