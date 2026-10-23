"""Document optional analytical currency equivalents in the modification register."""

import json

from erev_api.db import migration_ops as ops

revision = "0327"
down_revision = "0326"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", "ap'
    'proval_request", "approval_decision", "judgement_record", "contract_version", '
    '"calc_trace", "lock_snapshot", "legal_entity", "period", "tenant", "fx_rate", '
    '"fx_rate_set", "fx_rate_set_version", "historical_source_commit"], "joins": ["'
    'modification.contract_id = contract.id", "modification.approval_request_id = a'
    'pproval_request.id", "approval_decision.approval_request_id = approval_request'
    '.id", "modification.judgement_record_id = judgement_record.id"], "filters": ["'
    "Native event TP composition shows fixed, constrained variable, returns, payabl"
    "e, financing, noncash and posting-rounding contributions in original currency;"
    " components reconcile to event TP change, totals count each modification once,"
    " missing historical evidence remains empty, and retained runs preserve their o"
    'riginal column shape", "new native traces provide event-position TP changes an'
    "d per-obligation catch-ups; verified trace hashes and node identities distingu"
    "ish batched modifications; older traces retain version deltas with exact prede"
    'cessors and refuse shared catch-ups", "functional/reporting require contract c'
    "urrency to equal entity functional currency; reporting preserves original amou"
    "nts and adds equivalents using the approved average of the modification effect"
    "ive period; these are analytical equivalents, not posted FX amounts; unknown m"
    'easures stay empty and TP totals count each modification once", "same-source r'
    "uns retain modification inputs, applied-version/preview provenance, resolved d"
    'ates and reporting rates; reruns rebuild rows and totals without live reads", '
    '"entity code in entity_codes and within the caller\'s entity scope", "book_code'
    ' = book", "modification.effective_date from from_date to to_date inclusive", "'
    'modification.status in status", "contract.external_id = contract_external_id w'
    'hen given", "with period_lock_id, the values frozen at that lock (lock_snapsho'
    't kind MODIFICATION_REGISTER)", "historical_source_commit_v1 retains original '
    "event and contract-version transaction commits; new event/version extracts and"
    " BBR event sources use commit cutoffs; historical version populations exclude "
    "later commits before latest selection; bound inputs keep their original interp"
    'retation"], "parameters": ["entity_codes", "book", "from_date", "to_date", "st'
    'atus", "contract_external_id", "period_lock_id", "currency_view", "known_at", '
    '"known_at_basis"]}, "parameters_schema": {"$schema": "https://json-schema.org/'
    'draft/2020-12/schema", "type": "object", "additionalProperties": false, "prope'
    'rties": {"entity_codes": {"type": "array", "items": {"type": "string", "minLen'
    'gth": 1}, "minItems": 1, "uniqueItems": true}, "book": {"type": "string", "enu'
    'm": ["ASC606", "IFRS15", "LEGACY"]}, "from_date": {"type": "string", "format":'
    ' "date"}, "to_date": {"type": "string", "format": "date"}, "status": {"type": '
    '"array", "items": {"type": "string", "enum": ["DRAFT", "SUBMITTED", "APPROVED"'
    ', "APPLIED", "REJECTED", "VOIDED"]}, "uniqueItems": true}, "contract_external_'
    'id": {"type": "string", "minLength": 1}, "period_lock_id": {"type": "string", '
    '"format": "uuid"}, "currency_view": {"type": "string", "enum": ["transaction",'
    ' "functional", "reporting"]}, "known_at": {"type": "string", "format": "date-t'
    'ime"}, "known_at_basis": {"type": "string", "enum": ["record", "historical"]}}'
    "}}"
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", "ap'
    'proval_request", "approval_decision", "judgement_record", "contract_version", '
    '"calc_trace", "lock_snapshot", "legal_entity", "period", "tenant", "fx_rate", '
    '"fx_rate_set", "fx_rate_set_version", "historical_source_commit"], "joins": ["'
    'modification.contract_id = contract.id", "modification.approval_request_id = a'
    'pproval_request.id", "approval_decision.approval_request_id = approval_request'
    '.id", "modification.judgement_record_id = judgement_record.id"], "filters": ["'
    "currency_basis=spot_equivalent permits foreign functional/reporting views with"
    " approved effective-date spot equivalents, followed by effective-period averag"
    "e for reporting; original amounts and pinned rates are retained; equivalents a"
    're explicitly analytical, never actual posted FX attribution", "Native event T'
    "P composition shows fixed, constrained variable, returns, payable, financing, "
    "noncash and posting-rounding contributions in original currency; components re"
    "concile to event TP change, totals count each modification once, missing histo"
    "rical evidence remains empty, and retained runs preserve their original column"
    ' shape", "new native traces provide event-position TP changes and per-obligati'
    "on catch-ups; verified trace hashes and node identities distinguish batched mo"
    "difications; older traces retain version deltas with exact predecessors and re"
    'fuse shared catch-ups", "source basis functional/reporting require contract cu'
    "rrency to equal entity functional currency; reporting preserves original amoun"
    "ts and adds equivalents using the approved average of the modification effecti"
    "ve period; these are analytical equivalents, not posted FX amounts; unknown me"
    'asures stay empty and TP totals count each modification once", "same-source ru'
    "ns retain modification inputs, applied-version/preview provenance, resolved da"
    'tes and reporting rates; reruns rebuild rows and totals without live reads", "'
    'entity code in entity_codes and within the caller\'s entity scope", "book_code '
    '= book", "modification.effective_date from from_date to to_date inclusive", "m'
    'odification.status in status", "contract.external_id = contract_external_id wh'
    'en given", "with period_lock_id, the values frozen at that lock (lock_snapshot'
    ' kind MODIFICATION_REGISTER)", "historical_source_commit_v1 retains original e'
    "vent and contract-version transaction commits; new event/version extracts and "
    "BBR event sources use commit cutoffs; historical version populations exclude l"
    "ater commits before latest selection; bound inputs keep their original interpr"
    'etation"], "parameters": ["entity_codes", "book", "from_date", "to_date", "sta'
    'tus", "contract_external_id", "period_lock_id", "currency_view", "currency_bas'
    'is", "known_at", "known_at_basis"]}, "parameters_schema": {"$schema": "https:/'
    '/json-schema.org/draft/2020-12/schema", "type": "object", "additionalPropertie'
    's": false, "properties": {"entity_codes": {"type": "array", "items": {"type": '
    '"string", "minLength": 1}, "minItems": 1, "uniqueItems": true}, "book": {"type'
    '": "string", "enum": ["ASC606", "IFRS15", "LEGACY"]}, "from_date": {"type": "s'
    'tring", "format": "date"}, "to_date": {"type": "string", "format": "date"}, "s'
    'tatus": {"type": "array", "items": {"type": "string", "enum": ["DRAFT", "SUBMI'
    'TTED", "APPROVED", "APPLIED", "REJECTED", "VOIDED"]}, "uniqueItems": true}, "c'
    'ontract_external_id": {"type": "string", "minLength": 1}, "period_lock_id": {"'
    'type": "string", "format": "uuid"}, "currency_view": {"type": "string", "enum"'
    ': ["transaction", "functional", "reporting"]}, "currency_basis": {"type": "str'
    'ing", "enum": ["source", "spot_equivalent"], "default": "source", "title": "Cu'
    'rrency amount basis"}, "known_at": {"type": "string", "format": "date-time"}, '
    '"known_at_basis": {"type": "string", "enum": ["record", "historical"]}}}}'
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
            + "'::jsonb WHERE code='modification_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
