"""Freeze date-aligned disaggregation columns for new report bindings."""

import json

from erev_api.db import migration_ops as ops

revision = "0339"
down_revision = "0338"
branch_labels = None
depends_on = None

OLD = {
    "filters": [
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "period_key from from_period_key to to_period_key",
        "subledger_line.account_role = 'REVENUE'; independent tie-out uses journal runs "
        "not cancelled",
        "functional reads posted amounts; reporting translates posted functional lines "
        "at their period average rates, retained for reruns",
        "grouped by dimension_code and, with include_timing, the timing of transfer",
        "with period_lock_id, the values frozen at that lock (lock_snapshot kind DISAGGREGATION)",
        "subledger_commit_visibility_v1 requires original PostgreSQL posting commit time "
        "at or before the historical cutoff; retained commit evidence is immutable; "
        "older bindings preserve their original seal-time interpretation",
        "Historical journal populations use original line commits and the latest "
        "committed journal-run/batch source revision at known_at. New journal "
        "incremental extracts use line commits in (known_since, known_at]; retained "
        "legacy bindings keep their original basis.",
    ],
    "joins": [
        "subledger_line.obligation_id = obligation_version.obligation_id and "
        "subledger_line.contract_version_id = obligation_version.contract_version_id",
        "obligation_version.product_id = product.id",
        "subledger_line.period_id = period.id",
        "journal_line.journal_batch_id = journal_batch.id for the independent journal tie-out",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "period_lock_id",
        "from_period_key",
        "to_period_key",
        "dimension_code",
        "include_timing",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
    "source_tables": [
        "subledger_line",
        "tenant",
        "fx_rate",
        "fx_rate_set",
        "fx_rate_set_version",
        "journal_line",
        "journal_batch",
        "journal_run",
        "obligation_version",
        "product",
        "dimension_value",
        "period",
        "lock_snapshot",
        "subledger_posting_commit",
        "report_source_revision",
        "historical_source_commit",
    ],
    "version": 1,
}
NEW = {
    "filters": [
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "period_key from from_period_key to to_period_key",
        "subledger_line.account_role = 'REVENUE'; independent tie-out uses journal runs "
        "not cancelled",
        "functional reads posted amounts; reporting translates posted functional lines "
        "at their period average rates, retained for reruns",
        "grouped by dimension_code and, with include_timing, the timing of transfer",
        "with period_lock_id, the values frozen at that lock (lock_snapshot kind DISAGGREGATION)",
        "New runs align complete selected periods by start/end dates across entity "
        "calendars; identical intervals combine, different or partially overlapping "
        "intervals stay separate; retained legacy runs preserve fiscal-key columns",
        "subledger_commit_visibility_v1 requires original PostgreSQL posting commit time "
        "at or before the historical cutoff; retained commit evidence is immutable; "
        "older bindings preserve their original seal-time interpretation",
        "Historical journal populations use original line commits and the latest "
        "committed journal-run/batch source revision at known_at. New journal "
        "incremental extracts use line commits in (known_since, known_at]; retained "
        "legacy bindings keep their original basis.",
    ],
    "joins": [
        "subledger_line.obligation_id = obligation_version.obligation_id and "
        "subledger_line.contract_version_id = obligation_version.contract_version_id",
        "obligation_version.product_id = product.id",
        "subledger_line.period_id = period.id",
        "journal_line.journal_batch_id = journal_batch.id for the independent journal tie-out",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "period_lock_id",
        "from_period_key",
        "to_period_key",
        "dimension_code",
        "include_timing",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
    "source_tables": [
        "subledger_line",
        "tenant",
        "fx_rate",
        "fx_rate_set",
        "fx_rate_set_version",
        "journal_line",
        "journal_batch",
        "journal_run",
        "obligation_version",
        "product",
        "dimension_value",
        "period",
        "lock_snapshot",
        "subledger_posting_commit",
        "report_source_revision",
        "historical_source_commit",
    ],
    "version": 1,
}


def _set(value: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    payload = json.dumps(value).replace("'", "''")
    ops.execute(
        f"UPDATE erev.report_definition SET ipe_logic='{payload}'::jsonb "  # noqa: S608
        "WHERE code='disaggregation' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
