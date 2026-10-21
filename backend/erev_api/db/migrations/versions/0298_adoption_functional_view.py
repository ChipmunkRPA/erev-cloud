"""Expose Adoption Bridge functional currency with explicit unavailable legacy positions."""

import json

from erev_api.db import migration_ops as ops

revision = "0298"
down_revision = "0297"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"parameters_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "t'
    'ype": "object", "additionalProperties": false, "properties": {"entity_codes": {"type'
    '": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems'
    '": true, "maxItems": 1}, "date_of_initial_application": {"type": "string", "format":'
    ' "date"}, "contract_external_id": {"type": "string", "minLength": 1}, "known_at": {"'
    'type": "string", "format": "date-time"}, "known_at_basis": {"type": "string", "enum"'
    ': ["record", "historical"]}}}, "ipe_logic": {"version": 1, "source_tables": ["contra'
    'ct_version", "contract_version_balance", "obligation_version", "contract", "customer'
    '", "subledger_posting_commit", "historical_source_commit"], "joins": ["contract_vers'
    'ion_balance.contract_version_id = contract_version.id", "obligation_version.contract'
    '_version_id = contract_version.id", "contract_version_balance.contract_id = contract'
    '.id", "contract.customer_id = customer.id"], "filters": ["one entity of entity_codes'
    ' keeping the LEGACY book", "ASC606 and LEGACY figures at date_of_initial_application'
    '", "contract.external_id = contract_external_id when given", "subledger_commit_visib'
    "ility_v1 requires original PostgreSQL posting commit time at or before the historica"
    "l cutoff; retained commit evidence is immutable; older bindings preserve their origi"
    'nal seal-time interpretation", "historical_source_commit_v1 retains original event a'
    "nd contract-version transaction commits; new event/version extracts and BBR event so"
    "urces use commit cutoffs; historical version populations exclude later commits befor"
    'e latest selection; bound inputs keep their original interpretation"], "parameters":'
    ' ["entity_codes", "date_of_initial_application", "contract_external_id", "known_at",'
    ' "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"parameters_schema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "t'
    'ype": "object", "additionalProperties": false, "properties": {"entity_codes": {"type'
    '": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems'
    '": true, "maxItems": 1}, "date_of_initial_application": {"type": "string", "format":'
    ' "date"}, "contract_external_id": {"type": "string", "minLength": 1}, "currency_view'
    '": {"type": "string", "enum": ["transaction", "functional"]}, "known_at": {"type": "'
    'string", "format": "date-time"}, "known_at_basis": {"type": "string", "enum": ["reco'
    'rd", "historical"]}}}, "ipe_logic": {"version": 1, "source_tables": ["contract_versi'
    'on", "contract_version_balance", "obligation_version", "contract", "customer", "subl'
    'edger_line", "subledger_posting_commit", "historical_source_commit"], "joins": ["con'
    'tract_version_balance.contract_version_id = contract_version.id", "obligation_versio'
    'n.contract_version_id = contract_version.id", "contract_version_balance.contract_id '
    '= contract.id", "contract.customer_id = customer.id"], "filters": ["one entity of en'
    'tity_codes keeping the LEGACY book", "ASC606 and LEGACY figures at date_of_initial_a'
    'pplication", "contract.external_id = contract_external_id when given", "functional v'
    "iew uses posted legacy revenue and reconciled dated primary revenue and balances; fo"
    "reign legacy positions without historical carrying evidence are unavailable, includi"
    'ng affected aggregate comparisons", "subledger_commit_visibility_v1 requires origina'
    "l PostgreSQL posting commit time at or before the historical cutoff; retained commit"
    " evidence is immutable; older bindings preserve their original seal-time interpretat"
    'ion", "historical_source_commit_v1 retains original event and contract-version trans'
    "action commits; new event/version extracts and BBR event sources use commit cutoffs;"
    " historical version populations exclude later commits before latest selection; bound"
    ' inputs keep their original interpretation"], "parameters": ["entity_codes", "date_o'
    'f_initial_application", "contract_external_id", "currency_view", "known_at", "known_'
    'at_basis"]}}'
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
