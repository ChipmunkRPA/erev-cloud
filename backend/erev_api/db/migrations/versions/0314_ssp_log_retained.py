"""Retain SSP lifecycle, approval and study inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0314"
down_revision = "0313"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["ssp_book_version", "ssp_book", '
    '"ssp_entry", "approval_request", "approval_decision", "file_object"], "joins": '
    '["ssp_book_version.ssp_book_id = ssp_book.id", "ssp_entry.ssp_book_version_id = '
    'ssp_book_version.id", "ssp_book_version.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id"], "filters": ["a lifecycle'
    ' transition of the version from from_date to to_date inclusive", "ssp_book.code = '
    'ssp_book_code when given", "books of the entities in entity_codes and tenant-wide '
    'books"], "parameters": ["entity_codes", "from_date", "to_date", "ssp_book_code", '
    '"known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["ssp_book_version", "ssp_book", '
    '"ssp_entry", "approval_request", "approval_decision", "file_object"], "joins": '
    '["ssp_book_version.ssp_book_id = ssp_book.id", "ssp_entry.ssp_book_version_id = '
    'ssp_book_version.id", "ssp_book_version.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id"], "filters": ["same-source'
    " runs retain SSP lifecycle, approval, actor and study inputs; rebuild rows and lifecycle"
    ' date selection without live reads", "a lifecycle transition of the version from '
    'from_date to to_date inclusive", "ssp_book.code = ssp_book_code when given", "books of '
    'the entities in entity_codes and tenant-wide books"], "parameters": ["entity_codes", '
    '"from_date", "to_date", "ssp_book_code", "known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='ssp_change_log' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
