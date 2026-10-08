"""Align persisted out-of-period report metadata with the existing late-event reader."""

import json
from typing import Any

from erev_api.db import migration_ops as ops

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None

BEFORE_DESCRIPTION = (
    "Contract events whose effect posted in a period other than the period of their effective "
    "date, with origin and posting periods (REQ-CLS-006)."
)

AFTER_DESCRIPTION = (
    "Contract events whose effect posted in a period other than the period of their effective "
    "date, plus computed late events with zero postings. Event amounts are separate from posted "
    "effects (REQ-CLS-006; REG-LATE-NOLINE-1)."
)

BEFORE_LOGIC = {
    "filters": [
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "posting period_key from from_period_key to to_period_key",
        "subledger_line.origin_period_id is not null and differs from subledger_line.period_id",
        "origin period = origin_period_key when given",
        "with period_lock_id, the values frozen at that lock (lock_snapshot kind "
        "OUT_OF_PERIOD_REGISTER)",
    ],
    "joins": [
        "subledger_line.contract_event_id = contract_event.id",
        "subledger_line.contract_id = contract.id",
        "subledger_line.period_id = period.id (posting period)",
        "subledger_line.origin_period_id = period.id (origin period)",
        "contract_event.approval_request_id = approval_request.id",
        "contract_event.import_upload_id = import_upload.id (an event written by SYSTEM "
        "for an import: recorded by = the upload's creator)",
        "import_upload.approval_request_id = approval_request.id (the approval of such an event)",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "from_period_key",
        "to_period_key",
        "origin_period_key",
        "period_lock_id",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
    "source_tables": [
        "subledger_line",
        "contract_event",
        "contract",
        "approval_request",
        "import_upload",
        "period",
        "lock_snapshot",
    ],
    "version": 1,
}

AFTER_LOGIC = {
    "filters": [
        "stored LATE_EVENT period/book evidence; known_at excludes later findings",
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "posting period_key from from_period_key to to_period_key",
        "subledger_line.origin_period_id is not null and differs from subledger_line.period_id",
        "origin period = origin_period_key when given",
        "with period_lock_id, the values frozen at that lock (lock_snapshot kind "
        "OUT_OF_PERIOD_REGISTER)",
    ],
    "joins": [
        "ENGINE LATE_EVENT exception dedupe key binds contract_event.id",
        "subledger_line.contract_event_id = contract_event.id",
        "subledger_line.contract_id = contract.id",
        "subledger_line.period_id = period.id (posting period)",
        "subledger_line.origin_period_id = period.id (origin period)",
        "contract_event.approval_request_id = approval_request.id",
        "contract_event.import_upload_id = import_upload.id (an event written by SYSTEM "
        "for an import: recorded by = the upload's creator)",
        "import_upload.approval_request_id = approval_request.id (the approval of such an event)",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "from_period_key",
        "to_period_key",
        "origin_period_key",
        "period_lock_id",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
    "source_tables": [
        "exception_item",
        "subledger_line",
        "contract_event",
        "contract",
        "approval_request",
        "import_upload",
        "period",
        "lock_snapshot",
    ],
    "version": 1,
}


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _replace(description: str, logic: dict[str, Any]) -> None:
    # Metadata repair only; preserve every existing run, output, definition key and version.
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET description = "  # noqa: S608 — escaped frozen constants
        + _literal(description)
        + ", ipe_logic = "
        + _literal(json.dumps(logic, sort_keys=True, separators=(",", ":")))
        + "::jsonb WHERE code = 'out_of_period_register' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _replace(AFTER_DESCRIPTION, AFTER_LOGIC)


def downgrade() -> None:
    _replace(BEFORE_DESCRIPTION, BEFORE_LOGIC)
