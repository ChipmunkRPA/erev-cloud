"""Document retained mixed-role FX attribution in the report IPE catalogue."""

from erev_api.db import migration_ops as ops

revision = "0193"
down_revision = "0192"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["subledger_line","subledger_posting","close_pass_evidence","file_object","contract_version_balance","calc_trace","fx_layer_movement","contract_event","contract","customer","period","lock_snapshot","reconciliation","tenant","fx_rate","fx_rate_set","fx_rate_set_version"],"joins":["subledger_line.subledger_posting_id = subledger_posting.id","close_pass_evidence.subledger_posting_id = subledger_posting.id; retained entry index identifies the source group","close_pass_evidence.file_id = file_object.id; authenticated pass input/output and paid-line history","subledger_line.contract_id = contract.id","subledger_line.period_id = period.id","contract_version_balance.contract_id = contract.id","calc_trace.contract_version_id = contract_version_balance.contract_version_id","contract_event.contract_id = contract.id (billing documents)","contract.customer_id = customer.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","period_key from from_period_key to to_period_key","subledger_line.account_role is a contract balance role","opening: balance at the end of the period before from_period_key; closing: balance at the end of to_period_key","billing that posts no line (billing.posting = ERP): per period the delta of the calc_trace node billed_unconditional_cum less the BILLING and CREDIT_MEMO lines of the role; where not zero and the role holds no such line, the period\'\'s kept BILLING_RECORDED lines and CREDIT_MEMO_RECORDED events, not voided, at their effective dates","functional/reporting close FX uses signed asset/liability source layers, prior targets and recursively retained paid lines","source binding retains posted-history dependencies and evidence hashes; unavailable source attribution refuses","with period_lock_id, the values frozen at that lock (lock_snapshot kind CONTRACT_BALANCE_ROLLFORWARD)"],"parameters":["entity_codes","book","from_period_key","to_period_key","balance_role","period_lock_id","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'contract_balance_rollforward\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["subledger_line","subledger_posting","contract_version_balance","calc_trace","fx_layer_movement","contract_event","contract","customer","period","lock_snapshot","reconciliation","tenant","fx_rate","fx_rate_set","fx_rate_set_version"],"joins":["subledger_line.subledger_posting_id = subledger_posting.id","subledger_line.contract_id = contract.id","subledger_line.period_id = period.id","contract_version_balance.contract_id = contract.id","calc_trace.contract_version_id = contract_version_balance.contract_version_id","contract_event.contract_id = contract.id (billing documents)","contract.customer_id = customer.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","period_key from from_period_key to to_period_key","subledger_line.account_role is a contract balance role","opening: balance at the end of the period before from_period_key; closing: balance at the end of to_period_key","billing that posts no line (billing.posting = ERP): per period the delta of the calc_trace node billed_unconditional_cum less the BILLING and CREDIT_MEMO lines of the role; where not zero and the role holds no such line, the period\'\'s kept BILLING_RECORDED lines and CREDIT_MEMO_RECORDED events, not voided, at their effective dates","with period_lock_id, the values frozen at that lock (lock_snapshot kind CONTRACT_BALANCE_ROLLFORWARD)"],"parameters":["entity_codes","book","from_period_key","to_period_key","balance_role","period_lock_id","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'contract_balance_rollforward\' AND version = 1'  # noqa: E501


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
