"""Disclose BBR source-time valuation and retained source reads."""

from erev_api.db import migration_ops as ops

revision = "0175"
down_revision = "0174"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["contract_event","modification","combination_group_member","contract_version","subledger_line","subledger_posting_seal","journal_line","journal_entry","journal_batch","journal_run","audit_event","legal_entity","period","fx_rate","fx_rate_set","fx_rate_set_version"],"joins":["modification applied_event_id binds its original application group and contract_version; predecessor supplies price delta","subledger_line joins its posting seal; journal lines join entries, batches and runs with lifecycle evidence","entity fiscal calendars bucket contributions; historical approved spot rates value non-functional contract and billing amounts"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","period_key from from_period_key to to_period_key","source-time event/version creation and sealed posting cutoffs; retained inputs supply reruns","activated contract stated line values exclude bookings linked to separate-contract modifications","applied modification counted once; missing or shared valuation basis refuses","billing identity, credit and void rules; revenue uses posting period","journal revenue excludes runs cancelled as of source time; unknown historical state refuses","functional contract/billing amounts use unique approved effective-day spot rate; reporting currency and lock datasets unsupported"],"parameters":["entity_codes","book","period_lock_id","from_period_key","to_period_key","granularity","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'bookings_billings_revenue\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["contract_event","modification","subledger_line","journal_line","legal_entity","period"],"joins":["modification.applied_event_id = contract_event.id","subledger_line.contract_event_id = contract_event.id","subledger_line.period_id = period.id","subledger_line.entity_id = legal_entity.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","period_key from from_period_key to to_period_key","booked: activated contracts and applied modifications effective in the range","billings: billing events effective in the range","revenue: subledger_line.account_role = \'\'REVENUE\'\'"],"parameters":["entity_codes","book","period_lock_id","from_period_key","to_period_key","granularity","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'bookings_billings_revenue\' AND version = 1'  # noqa: E501


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
