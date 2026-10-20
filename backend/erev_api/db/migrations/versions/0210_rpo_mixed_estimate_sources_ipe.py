"""Document event-backed mixed RPO allocation attribution."""

from erev_api.db import migration_ops as ops

revision = "0210"
down_revision = "0209"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["tenant","fx_rate","fx_rate_set","fx_rate_set_version","calc_trace","obligation_version","contract_version","contract_computation","computation_evidence","contract_event","contract","period","lock_snapshot","combination_group_member"],"joins":["obligation_version.contract_version_id = contract_version.id","obligation_version.contract_id = contract.id","contract_event.contract_id = contract.id","combination_group_member.contract_id = contract.id","calc_trace.contract_version_id = contract_version.id; estimate-event shares reconcile to original tp_delta nodes"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","opening: RPO at the end of the period before from_period_key; closing: RPO at the end of to_period_key","per contract, the contract_version at the date along the contract\'\'s chain of combination groups: the versions recorded while the contract was a member of their group (combination_group_member)","movements classified by the contract_event that caused each contract version","full RPO exemption eligibility is evaluated per retained version; opening and closing exclusions are separate, with eligibility changes in EXEMPTIONS","terminal cancellations remove only unrecognized allocation; retained cancelled-version revenue separates period recognition and late restatement","cancellation and re-entry histories use separate disclosure segments; re-entry admits remaining RPO and revenue excludes changes while outside disclosure","mixed modification and estimate changes use original event-specific estimate shares reconciled to each price delta; unsupported or incomplete evidence stays unexplained","with period_lock_id, the values frozen at that lock (lock_snapshot kind RPO_ROLLFORWARD)"],"parameters":["entity_codes","book","period_lock_id","from_period_key","to_period_key","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'rpo_rollforward\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["tenant","fx_rate","fx_rate_set","fx_rate_set_version","obligation_version","contract_version","contract_computation","computation_evidence","contract_event","contract","period","lock_snapshot","combination_group_member"],"joins":["obligation_version.contract_version_id = contract_version.id","obligation_version.contract_id = contract.id","contract_event.contract_id = contract.id","combination_group_member.contract_id = contract.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","opening: RPO at the end of the period before from_period_key; closing: RPO at the end of to_period_key","per contract, the contract_version at the date along the contract\'\'s chain of combination groups: the versions recorded while the contract was a member of their group (combination_group_member)","movements classified by the contract_event that caused each contract version","full RPO exemption eligibility is evaluated per retained version; opening and closing exclusions are separate, with eligibility changes in EXEMPTIONS","terminal cancellations remove only unrecognized allocation; retained cancelled-version revenue separates period recognition and late restatement","cancellation and re-entry histories use separate disclosure segments; re-entry admits remaining RPO and revenue excludes changes while outside disclosure","with period_lock_id, the values frozen at that lock (lock_snapshot kind RPO_ROLLFORWARD)"],"parameters":["entity_codes","book","period_lock_id","from_period_key","to_period_key","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'rpo_rollforward\' AND version = 1'  # noqa: E501


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
