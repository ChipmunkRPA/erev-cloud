"""Retain late-entry event, lock and window inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0312"
down_revision = "0311"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["contract_event", "contract", "period", '
    '"period_lock", "approval_request", "import_upload"], "joins": '
    '["contract_event.contract_id = contract.id", "period_lock.period_id = period.id", '
    '"contract_event.approval_request_id = approval_request.id", '
    '"contract_event.import_upload_id = import_upload.id (an event written by SYSTEM for an '
    'import: recorded by = the upload\'s creator)", "import_upload.approval_request_id = '
    'approval_request.id (the approval of such an event)"], "filters": ["entity code in '
    'entity_codes and within the caller\'s entity scope", "book_code = book", "section 1: '
    "contract_event.recorded_at after the first period_lock of period_key, with "
    'effective_date in the period", "section 2: effective_date within window_days of the '
    'period end (close.late_entry_window_days)"], "parameters": ["entity_codes", "book", '
    '"period_key", "window_days", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["contract_event", "contract", "period", '
    '"period_lock", "approval_request", "import_upload"], "joins": '
    '["contract_event.contract_id = contract.id", "period_lock.period_id = period.id", '
    '"contract_event.approval_request_id = approval_request.id", '
    '"contract_event.import_upload_id = import_upload.id (an event written by SYSTEM for an '
    'import: recorded by = the upload\'s creator)", "import_upload.approval_request_id = '
    'approval_request.id (the approval of such an event)"], "filters": ["same-source runs '
    "retain event and actor inputs, resolved period/lock scopes and window; rebuild both "
    'sections and counts without live reads", "entity code in entity_codes and within the '
    'caller\'s entity scope", "book_code = book", "section 1: contract_event.recorded_at after'
    ' the first period_lock of period_key, with effective_date in the period", "section 2: '
    'effective_date within window_days of the period end (close.late_entry_window_days)"], '
    '"parameters": ["entity_codes", "book", "period_key", "window_days", "known_at", '
    '"known_at_basis"]}}'
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
            + "'::jsonb WHERE code='late_entry_report' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
