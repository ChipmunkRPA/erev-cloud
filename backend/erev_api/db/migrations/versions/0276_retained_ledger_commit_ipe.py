"""Retain posting commit cutoffs for subledger extracts and BBR revenue sources."""

import json

from erev_api.db import migration_ops as ops

revision = "0276"
down_revision = "0275"
branch_labels = None
depends_on = None

OLD = (
    '{"extract_subledger_lines":{"joins":["subledger_line.contract_id = '
    'contract.id","subledger_line.subledger_posting_id = '
    "subledger_posting_seal.subledger_posting_id (same "
    'tenant/book)","subledger_line.period_id = '
    'period.id","subledger_line.origin_period_id = period.id (origin '
    'period)","subledger_line.gl_account_id = gl_account.id"],"filters":["entity '
    'code in entity_codes and within the caller\'s entity scope","book_code = '
    'book","subledger_line.recorded_at at or before the source time","source time '
    'is known_at; lock datasets unsupported","line recorded_server_at and posting '
    'sealed_server_at at or before source time","mode INCREMENTAL: rows created '
    "(recorded for events and subledger lines) after known_since and at or before "
    'the source time"],"version":1,"parameters":["mode","entity_codes","book","peri'
    'od_lock_id","known_at","known_since","known_at_basis"],"source_tables":["suble'
    'dger_line","subledger_posting_seal","contract","period","gl_account"]},"bookin'
    'gs_billings_revenue":{"joins":["modification applied_event_id binds its '
    "original application group and contract_version; predecessor supplies price "
    'delta","subledger_line joins its posting seal; journal lines join entries, '
    'batches and runs with lifecycle evidence","entity fiscal calendars bucket '
    "contributions; historical approved spot rates value non-functional contract "
    'and billing amounts"],"filters":["entity code in entity_codes and within the '
    'caller\'s entity scope","book_code = book","period_key from from_period_key to '
    'to_period_key","source-time event/version creation and sealed posting cutoffs;'
    ' retained inputs supply reruns","activated contract stated line values exclude'
    ' bookings linked to separate-contract modifications","applied modification '
    'counted once; missing or shared valuation basis refuses","billing identity, '
    'credit and void rules; revenue uses posting period","journal revenue excludes '
    "runs cancelled as of source time; unknown historical state "
    'refuses","functional contract/billing amounts use unique approved '
    'effective-day spot rate; reporting currency and lock datasets unsupported"],"v'
    'ersion":1,"parameters":["entity_codes","book","period_lock_id","from_period_ke'
    'y","to_period_key","granularity","currency_view","known_at","known_at_basis"],'
    '"source_tables":["contract_event","modification","combination_group_member","c'
    'ontract_version","subledger_line","subledger_posting_seal","journal_line","jou'
    'rnal_entry","journal_batch","journal_run","audit_event","legal_entity","period'
    '","fx_rate","fx_rate_set","fx_rate_set_version"]}}'
)

NEW = (
    '{"extract_subledger_lines":{"version":1,"source_tables":["subledger_line","sub'
    'ledger_posting_seal","contract","period","gl_account","subledger_posting_commi'
    't"],"joins":["subledger_line.contract_id = '
    'contract.id","subledger_line.subledger_posting_id = '
    "subledger_posting_seal.subledger_posting_id (same "
    'tenant/book)","subledger_line.period_id = '
    'period.id","subledger_line.origin_period_id = period.id (origin '
    'period)","subledger_line.gl_account_id = gl_account.id"],"filters":["entity '
    'code in entity_codes and within the caller\'s entity scope","book_code = '
    'book","subledger_line.recorded_at at or before the source time","source time '
    'is known_at; lock datasets unsupported","line recorded_server_at and posting '
    'sealed_server_at at or before source time","mode INCREMENTAL: original posting'
    " committed after known_since and at or before known_at; "
    "extract_subledger_commit_visibility_v1 retains this basis; older bound "
    'extracts preserve the recorded_at basis","new retained ledger sources require '
    "actual posting commit time at or before known_at; commit timestamps are "
    "retained with source rows; older bound datasets keep their original inputs and"
    ' interpretation"],"parameters":["mode","entity_codes","book","period_lock_id",'
    '"known_at","known_since","known_at_basis"]},"bookings_billings_revenue":{"vers'
    'ion":1,"source_tables":["contract_event","modification","combination_group_mem'
    'ber","contract_version","subledger_line","subledger_posting_seal","journal_lin'
    'e","journal_entry","journal_batch","journal_run","audit_event","legal_entity",'
    '"period","fx_rate","fx_rate_set","fx_rate_set_version","subledger_posting_comm'
    'it"],"joins":["modification applied_event_id binds its original application '
    'group and contract_version; predecessor supplies price delta","subledger_line '
    "joins its posting seal; journal lines join entries, batches and runs with "
    'lifecycle evidence","entity fiscal calendars bucket contributions; historical '
    "approved spot rates value non-functional contract and billing "
    'amounts"],"filters":["entity code in entity_codes and within the caller\'s '
    'entity scope","book_code = book","period_key from from_period_key to '
    'to_period_key","source-time event/version creation and sealed posting cutoffs;'
    ' retained inputs supply reruns","activated contract stated line values exclude'
    ' bookings linked to separate-contract modifications","applied modification '
    'counted once; missing or shared valuation basis refuses","billing identity, '
    'credit and void rules; revenue uses posting period","journal revenue excludes '
    "runs cancelled as of source time; unknown historical state "
    'refuses","functional contract/billing amounts use unique approved '
    "effective-day spot rate; reporting currency and lock datasets "
    'unsupported","new retained ledger sources require actual posting commit time '
    "at or before known_at; commit timestamps are retained with source rows; older "
    'bound datasets keep their original inputs and interpretation"],"parameters":["'
    'entity_codes","book","period_lock_id","from_period_key","to_period_key","granu'
    'larity","currency_view","known_at","known_at_basis"]}}'
)


def _apply(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, ipe in json.loads(encoded).items():
        payload = json.dumps(ipe).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic = '"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _apply(NEW)


def downgrade() -> None:
    _apply(OLD)
