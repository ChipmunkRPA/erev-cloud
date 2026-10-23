"""Enable retained reporting-currency BBR valuation and journal reconciliation."""

import json

from erev_api.db import migration_ops as ops

revision = "0334"
down_revision = "0333"
branch_labels = None
depends_on = None

OLD_IPE = {
    "version": 1,
    "source_tables": [
        "contract_event",
        "modification",
        "combination_group_member",
        "contract_version",
        "subledger_line",
        "subledger_posting_seal",
        "journal_line",
        "journal_entry",
        "journal_batch",
        "journal_run",
        "audit_event",
        "legal_entity",
        "period",
        "fx_rate",
        "fx_rate_set",
        "fx_rate_set_version",
        "subledger_posting_commit",
        "historical_source_commit",
        "report_source_revision",
    ],
    "joins": [
        "modification applied_event_id binds its original application group and "
        "contract_version; predecessor supplies price delta",
        "subledger_line joins its posting seal; journal lines join entries, batches "
        "and runs with lifecycle evidence",
        "entity fiscal calendars bucket contributions; historical approved spot "
        "rates value non-functional contract and billing amounts",
    ],
    "filters": [
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "period_key from from_period_key to to_period_key",
        "source-time event/version creation and sealed posting cutoffs; retained "
        "inputs supply reruns",
        "activated contract stated line values exclude bookings linked to "
        "separate-contract modifications",
        "applied modification counted once; missing or shared valuation basis refuses",
        "billing identity, credit and void rules; revenue uses posting period",
        "journal revenue excludes runs cancelled as of source time; unknown "
        "historical state refuses",
        "functional contract/billing amounts use unique approved effective-day "
        "spot rate; reporting currency and lock datasets unsupported",
        "new retained ledger sources require actual posting commit time at or "
        "before known_at; commit timestamps are retained with source rows; older "
        "bound datasets keep their original inputs and interpretation",
        "historical_source_commit_v1 retains original event and contract-version "
        "transaction commits; new event/version extracts and BBR event sources "
        "use commit cutoffs; historical version populations exclude later commits "
        "before latest selection; bound inputs keep their original interpretation",
        "Historical journal populations use original line commits and the latest "
        "committed journal-run/batch source revision at known_at. New journal "
        "incremental extracts use line commits in (known_since, known_at]; "
        "retained legacy bindings keep their original basis.",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "period_lock_id",
        "from_period_key",
        "to_period_key",
        "granularity",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
}

NEW_IPE = {
    "version": 1,
    "source_tables": [
        "contract_event",
        "modification",
        "combination_group_member",
        "contract_version",
        "subledger_line",
        "subledger_posting_seal",
        "journal_line",
        "journal_entry",
        "journal_batch",
        "journal_run",
        "audit_event",
        "legal_entity",
        "tenant",
        "period",
        "fx_rate",
        "fx_rate_set",
        "fx_rate_set_version",
        "subledger_posting_commit",
        "historical_source_commit",
        "report_source_revision",
    ],
    "joins": [
        "modification applied_event_id binds its original application group and "
        "contract_version; predecessor supplies price delta",
        "subledger_line joins its posting seal; journal lines join entries, batches "
        "and runs with lifecycle evidence",
        "entity fiscal calendars bucket contributions; historical approved spot "
        "rates value non-functional contract and billing amounts",
    ],
    "filters": [
        "Reporting currency translates original functional amounts with retained "
        "approved entity-period average rates, rounds once per "
        "entity/period/measure and distributes source pennies by signed largest "
        "remainder in stable source order; revenue journal totals use the same "
        "period basis; cells expose retained rates and original functional "
        "amounts; quarters and years sum translated periods",
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "period_key from from_period_key to to_period_key",
        "source-time event/version creation and sealed posting cutoffs; retained "
        "inputs supply reruns",
        "activated contract stated line values exclude bookings linked to "
        "separate-contract modifications",
        "applied modification counted once; missing or shared valuation basis refuses",
        "billing identity, credit and void rules; revenue uses posting period",
        "journal revenue excludes runs cancelled as of source time; unknown "
        "historical state refuses",
        "functional contract/billing amounts use unique approved effective-day "
        "spot rate; lock datasets unsupported",
        "new retained ledger sources require actual posting commit time at or "
        "before known_at; commit timestamps are retained with source rows; older "
        "bound datasets keep their original inputs and interpretation",
        "historical_source_commit_v1 retains original event and contract-version "
        "transaction commits; new event/version extracts and BBR event sources "
        "use commit cutoffs; historical version populations exclude later commits "
        "before latest selection; bound inputs keep their original interpretation",
        "Historical journal populations use original line commits and the latest "
        "committed journal-run/batch source revision at known_at. New journal "
        "incremental extracts use line commits in (known_since, known_at]; "
        "retained legacy bindings keep their original basis.",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "period_lock_id",
        "from_period_key",
        "to_period_key",
        "granularity",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
}


def _set(value: dict) -> None:
    payload = json.dumps(value).replace("'", "''")
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
        + payload
        + "'::jsonb WHERE code='bookings_billings_revenue' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW_IPE)


def downgrade() -> None:
    _set(OLD_IPE)
