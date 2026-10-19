"""Document implemented version extract sources and complete-member scope."""

from erev_api.db import migration_ops as ops

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["contract_version","contract_computation","contract"],"joins":["contract_version.contract_computation_id = contract_computation.id","contract_computation.stream_heads keys = contract.id (original members)"],"filters":["Every original member contracting entity must be in the report scope","book_code = book","version known_at and created_at at or before known_at source time; lock unsupported","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_contract_versions\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["contract_version","combination_group_member","contract"],"joins":["combination_group_member.combination_group_id = contract_version.combination_group_id","combination_group_member.contract_id = contract.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","source time: the lock of period_lock_id when given, else known_at","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_contract_versions\' AND version = 1'  # noqa: E501


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
