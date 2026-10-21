"""Add sourced legacy functional carrying positions to the Adoption Bridge."""

import json

from erev_api.db import migration_ops as ops

revision = "0301"
down_revision = "0300"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"parameters_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": '
    '"object", "additionalProperties": false, "properties": {"entity_codes": {"type": "array", '
    '"items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": true, '
    '"maxItems": 1}, "date_of_initial_application": {"type": "string", "format": "date"}, '
    '"contract_external_id": {"type": "string", "minLength": 1}, "currency_view": {"type": '
    '"string", "enum": ["transaction", "functional", "reporting"]}, "known_at": {"type": '
    '"string", "format": "date-time"}, "known_at_basis": {"type": "string", "enum": ["record", '
    '"historical"]}}}, "ipe_logic": {"version": 1, "source_tables": ["contract_version", '
    '"contract_version_balance", "obligation_version", "contract", "customer", '
    '"subledger_line", "tenant", "fx_rate", "fx_rate_set", "fx_rate_set_version", '
    '"subledger_posting_commit", "historical_source_commit"], "joins": '
    '["contract_version_balance.contract_version_id = contract_version.id", '
    '"obligation_version.contract_version_id = contract_version.id", '
    '"contract_version_balance.contract_id = contract.id", "contract.customer_id = '
    'customer.id"], "filters": ["one entity of entity_codes keeping the LEGACY book", "ASC606 '
    'and LEGACY figures at date_of_initial_application", "same-source reruns reconstruct '
    "sections, membership counts and totals from retained per-contract adoption inputs, date "
    'and currency basis without live source or rate reads", "contract.external_id = '
    'contract_external_id when given", "functional view uses posted legacy revenue and '
    "reconciled dated primary revenue and balances; foreign legacy positions without historical"
    ' carrying evidence are unavailable, including affected aggregate comparisons", "reporting '
    "view translates each period change in functional cumulative revenue at its average rate "
    "and ending balances independently at the closing rate; legacy-only historical revenue "
    "remains in its final endpoint population; nonzero imported opening revenue without dated "
    'history cannot be translated", "subledger_commit_visibility_v1 requires original '
    "PostgreSQL posting commit time at or before the historical cutoff; retained commit "
    'evidence is immutable; older bindings preserve their original seal-time interpretation", '
    '"historical_source_commit_v1 retains original event and contract-version transaction '
    "commits; new event/version extracts and BBR event sources use commit cutoffs; historical "
    "version populations exclude later commits before latest selection; bound inputs keep their"
    ' original interpretation"], "parameters": ["entity_codes", "date_of_initial_application", '
    '"contract_external_id", "currency_view", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"parameters_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": '
    '"object", "additionalProperties": false, "properties": {"entity_codes": {"type": "array", '
    '"items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": true, '
    '"maxItems": 1}, "date_of_initial_application": {"type": "string", "format": "date"}, '
    '"contract_external_id": {"type": "string", "minLength": 1}, "currency_view": {"type": '
    '"string", "enum": ["transaction", "functional", "reporting"]}, '
    '"legacy_functional_positions": {"type": "array", "maxItems": 500, "items": {"type": '
    '"object", "additionalProperties": false, "required": ["contract_external_id", "as_of", '
    '"currency", "contract_liability", "unbilled_receivable", "source_reference"], '
    '"properties": {"contract_external_id": {"type": "string", "minLength": 1}, "as_of": '
    '{"type": "string", "format": "date"}, "currency": {"type": "string", "pattern": '
    '"^[A-Z]{3}$"}, "contract_liability": {"type": "string", "pattern": '
    '"^[0-9]{1,18}(?:\\\\.[0-9]{1,8})?$"}, "unbilled_receivable": {"type": "string", "pattern": '
    '"^[0-9]{1,18}(?:\\\\.[0-9]{1,8})?$"}, "source_reference": {"type": "string", "minLength": 1,'
    ' "maxLength": 500}}}}, "known_at": {"type": "string", "format": "date-time"}, '
    '"known_at_basis": {"type": "string", "enum": ["record", "historical"]}}}, "ipe_logic": '
    '{"version": 1, "source_tables": ["contract_version", "contract_version_balance", '
    '"obligation_version", "contract", "customer", "subledger_line", "tenant", "fx_rate", '
    '"fx_rate_set", "fx_rate_set_version", "subledger_posting_commit", '
    '"historical_source_commit"], "joins": ["contract_version_balance.contract_version_id = '
    'contract_version.id", "obligation_version.contract_version_id = contract_version.id", '
    '"contract_version_balance.contract_id = contract.id", "contract.customer_id = '
    'customer.id"], "filters": ["one entity of entity_codes keeping the LEGACY book", "ASC606 '
    'and LEGACY figures at date_of_initial_application", "same-source reruns reconstruct '
    "sections, membership counts and totals from retained per-contract adoption inputs, date "
    'and currency basis without live source or rate reads", "contract.external_id = '
    'contract_external_id when given", "optional supplied legacy functional carrying balances '
    "require an in-scope contract, prior period end, entity functional currency and source "
    "reference; they are retained report inputs, not ledger postings; reporting translates them"
    ' at the closing rate", "functional view uses posted legacy revenue and reconciled dated '
    "primary revenue and balances; foreign legacy positions without historical carrying "
    'evidence are unavailable, including affected aggregate comparisons", "reporting view '
    "translates each period change in functional cumulative revenue at its average rate and "
    "ending balances independently at the closing rate; legacy-only historical revenue remains "
    "in its final endpoint population; nonzero imported opening revenue without dated history "
    'cannot be translated", "subledger_commit_visibility_v1 requires original PostgreSQL '
    "posting commit time at or before the historical cutoff; retained commit evidence is "
    'immutable; older bindings preserve their original seal-time interpretation", '
    '"historical_source_commit_v1 retains original event and contract-version transaction '
    "commits; new event/version extracts and BBR event sources use commit cutoffs; historical "
    "version populations exclude later commits before latest selection; bound inputs keep their"
    ' original interpretation"], "parameters": ["entity_codes", "date_of_initial_application", '
    '"contract_external_id", "currency_view", "legacy_functional_positions", "known_at", '
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
            + "'::jsonb WHERE code='adoption_bridge' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
