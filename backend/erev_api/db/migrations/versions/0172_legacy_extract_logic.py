"""Document legacy extract inputs, exact trace sources and source cutoff."""

from erev_api.db import migration_ops as ops

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["obligation_version","contract_version","contract","contract_computation","obligation","legal_entity","combination_group_member","calc_trace"],"joins":["obligation_version.contract_version_id = contract_version.id","obligation_version.contract_id = contract.id","contract_version.contract_computation_id = contract_computation.id","previous_obligation_version_id identifies predecessor input","calc_trace.contract_version_id supplies exact source texts"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","ASC606 only","04 \\u00a717.1 rule 1 over all effective dates","known_at source cutoff and row/version created_at cutoff; lock unsupported","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_legacy_contract_live\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["obligation_version","contract_version","contract","migrated_legacy_row"],"joins":["obligation_version.contract_version_id = contract_version.id","obligation_version.contract_id = contract.id","migrated_legacy_row.contract_id = contract.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","04 \\u00a717.1 rule 1 over all dates","source time: the lock of period_lock_id when given, else known_at","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_legacy_contract_live\' AND version = 1'  # noqa: E501


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
