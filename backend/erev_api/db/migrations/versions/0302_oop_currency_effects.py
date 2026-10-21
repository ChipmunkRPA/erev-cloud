"""Document posted currency bases for the out-of-period register."""

import json

from erev_api.db import migration_ops as ops

revision = "0302"
down_revision = "0301"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["exception_item", "subledger_line", '
    '"contract_event", "contract", "approval_request", "import_upload", "period", '
    '"lock_snapshot", "subledger_posting_commit"], "joins": ["ENGINE LATE_EVENT exception '
    'dedupe key binds contract_event.id", "subledger_line.contract_event_id = '
    'contract_event.id", "subledger_line.contract_id = contract.id", "subledger_line.period_id '
    '= period.id (posting period)", "subledger_line.origin_period_id = period.id (origin '
    'period)", "contract_event.approval_request_id = approval_request.id", '
    '"contract_event.import_upload_id = import_upload.id (an event written by SYSTEM for an '
    'import: recorded by = the upload\'s creator)", "import_upload.approval_request_id = '
    'approval_request.id (the approval of such an event)"], "filters": ["stored LATE_EVENT '
    'period/book evidence; known_at excludes later findings", "entity code in entity_codes and '
    'within the caller\'s entity scope", "book_code = book", "posting period_key from '
    'from_period_key to to_period_key", "subledger_line.origin_period_id is not null and '
    'differs from subledger_line.period_id", "origin period = origin_period_key when given", '
    '"with period_lock_id, the values frozen at that lock (lock_snapshot kind '
    'OUT_OF_PERIOD_REGISTER)", "subledger_commit_visibility_v1 requires original PostgreSQL '
    "posting commit time at or before the historical cutoff; retained commit evidence is "
    'immutable; older bindings preserve their original seal-time interpretation"], '
    '"parameters": ["entity_codes", "book", "from_period_key", "to_period_key", '
    '"origin_period_key", "period_lock_id", "currency_view", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["exception_item", "subledger_line", '
    '"contract_event", "contract", "approval_request", "import_upload", "period", '
    '"lock_snapshot", "legal_entity", "tenant", "fx_rate", "fx_rate_set", '
    '"fx_rate_set_version", "subledger_posting_commit"], "joins": ["ENGINE LATE_EVENT exception'
    ' dedupe key binds contract_event.id", "subledger_line.contract_event_id = '
    'contract_event.id", "subledger_line.contract_id = contract.id", "subledger_line.period_id '
    '= period.id (posting period)", "subledger_line.origin_period_id = period.id (origin '
    'period)", "contract_event.approval_request_id = approval_request.id", '
    '"contract_event.import_upload_id = import_upload.id (an event written by SYSTEM for an '
    'import: recorded by = the upload\'s creator)", "import_upload.approval_request_id = '
    'approval_request.id (the approval of such an event)"], "filters": ["stored LATE_EVENT '
    'period/book evidence; known_at excludes later findings", "functional effects use posted '
    "functional amounts; reporting effects translate each posting period's functional activity "
    "at its approved average rate; original event amounts retain transaction currency; distinct"
    ' effect currencies never aggregate", "entity code in entity_codes and within the caller\'s '
    'entity scope", "book_code = book", "posting period_key from from_period_key to '
    'to_period_key", "subledger_line.origin_period_id is not null and differs from '
    'subledger_line.period_id", "origin period = origin_period_key when given", "with '
    "period_lock_id, the values frozen at that lock (lock_snapshot kind "
    'OUT_OF_PERIOD_REGISTER)", "subledger_commit_visibility_v1 requires original PostgreSQL '
    "posting commit time at or before the historical cutoff; retained commit evidence is "
    'immutable; older bindings preserve their original seal-time interpretation"], '
    '"parameters": ["entity_codes", "book", "from_period_key", "to_period_key", '
    '"origin_period_key", "period_lock_id", "currency_view", "known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='out_of_period_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
