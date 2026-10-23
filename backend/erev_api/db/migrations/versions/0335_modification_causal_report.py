"""Expose fixed-basis sequential modification causal analysis."""

import json

from erev_api.db import migration_ops as ops

revision = "0335"
down_revision = "0334"
branch_labels = None
depends_on = None

OLD = json.loads(
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", '
    '"approval_request", "approval_decision", "judgement_record", '
    '"contract_version", "calc_trace", "lock_snapshot", "legal_entity", "period",'
    ' "tenant", "fx_rate", "fx_rate_set", "fx_rate_set_version", '
    '"historical_source_commit"], "joins": ["modification.contract_id = '
    'contract.id", "modification.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"modification.judgement_record_id = judgement_record.id"], "filters": '
    '["Monetary cell explanations rebuild retained modification inputs, identify '
    "the original modification UUID and link saved native trace nodes; analytical"
    " equivalents expose pinned spot/average rate evidence separately; old runs "
    'without source identity refuse the drill and require a new report", '
    '"Original functional catch-up calculation is shown separately when one '
    "modification event exclusively explains its native recognition period and "
    "both currency totals reconcile to retained historical layers; not a journal "
    "delta or spot equivalent; mixed or missing evidence stays empty; bound runs "
    'preserve values and column shape", "currency_basis=spot_equivalent permits '
    "foreign functional/reporting views with approved effective-date spot "
    "equivalents, followed by effective-period average for reporting; original "
    "amounts and pinned rates are retained; equivalents are explicitly "
    'analytical, never actual posted FX attribution", "Native event TP '
    "composition shows fixed, constrained variable, returns, payable, financing, "
    "noncash and posting-rounding contributions in original currency; components "
    "reconcile to event TP change, totals count each modification once, missing "
    "historical evidence remains empty, and retained runs preserve their original"
    ' column shape", "new native traces provide event-position TP changes and '
    "per-obligation catch-ups; verified trace hashes and node identities "
    "distinguish batched modifications; older traces retain version deltas with "
    'exact predecessors and refuse shared catch-ups", "source basis '
    "functional/reporting require contract currency to equal entity functional "
    "currency; reporting preserves original amounts and adds equivalents using "
    "the approved average of the modification effective period; these are "
    "analytical equivalents, not posted FX amounts; unknown measures stay empty "
    'and TP totals count each modification once", "same-source runs retain '
    "modification inputs, applied-version/preview provenance, resolved dates and "
    'reporting rates; reruns rebuild rows and totals without live reads", "entity'
    ' code in entity_codes and within the caller\'s entity scope", "book_code = '
    'book", "modification.effective_date from from_date to to_date inclusive", '
    '"modification.status in status", "contract.external_id = '
    'contract_external_id when given", "with period_lock_id, the values frozen at'
    ' that lock (lock_snapshot kind MODIFICATION_REGISTER)", '
    '"historical_source_commit_v1 retains original event and contract-version '
    "transaction commits; new event/version extracts and BBR event sources use "
    "commit cutoffs; historical version populations exclude later commits before "
    'latest selection; bound inputs keep their original interpretation"], '
    '"parameters": ["entity_codes", "book", "from_date", "to_date", "status", '
    '"contract_external_id", "period_lock_id", "currency_view", "currency_basis",'
    ' "known_at", "known_at_basis"]}, "parameters_schema": {"$schema": '
    '"https://json-schema.org/draft/2020-12/schema", "type": "object", '
    '"additionalProperties": false, "properties": {"entity_codes": {"type": '
    '"array", "items": {"type": "string", "minLength": 1}, "minItems": 1, '
    '"uniqueItems": true}, "book": {"type": "string", "enum": ["ASC606", '
    '"IFRS15", "LEGACY"]}, "from_date": {"type": "string", "format": "date"}, '
    '"to_date": {"type": "string", "format": "date"}, "status": {"type": "array",'
    ' "items": {"type": "string", "enum": ["DRAFT", "SUBMITTED", "APPROVED", '
    '"APPLIED", "REJECTED", "VOIDED"]}, "uniqueItems": true}, '
    '"contract_external_id": {"type": "string", "minLength": 1}, '
    '"period_lock_id": {"type": "string", "format": "uuid"}, "currency_view": '
    '{"type": "string", "enum": ["transaction", "functional", "reporting"]}, '
    '"currency_basis": {"type": "string", "enum": ["source", "spot_equivalent"], '
    '"default": "source", "title": "Currency amount basis"}, "known_at": {"type":'
    ' "string", "format": "date-time"}, "known_at_basis": {"type": "string", '
    '"enum": ["record", "historical"]}}}}'
)
NEW = json.loads(
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", '
    '"approval_request", "approval_decision", "judgement_record", '
    '"contract_version", "contract_computation", "computation_evidence", '
    '"contract_event", "calc_trace", "lock_snapshot", "legal_entity", "period", '
    '"tenant", "fx_rate", "fx_rate_set", "fx_rate_set_version", '
    '"historical_source_commit"], "joins": ["modification.contract_id = '
    'contract.id", "modification.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"modification.judgement_record_id = judgement_record.id"], "filters": '
    '["currency_basis=causal_analysis replays applied modification events in '
    "original order on a fixed retained basis; baseline plus selected and other "
    "event effects reconciles to original period revenue; "
    "transaction/functional/reporting views are causal analysis, not original "
    "journal ownership; engine execution is outside transactions and saved reruns"
    ' and cells consume retained results", "Monetary cell explanations rebuild '
    "retained modification inputs, identify the original modification UUID and "
    "link saved native trace nodes; analytical equivalents expose pinned "
    "spot/average rate evidence separately; old runs without source identity "
    'refuse the drill and require a new report", "Original functional catch-up '
    "calculation is shown separately when one modification event exclusively "
    "explains its native recognition period and both currency totals reconcile to"
    " retained historical layers; not a journal delta or spot equivalent; mixed "
    "or missing evidence stays empty; bound runs preserve values and column "
    'shape", "currency_basis=spot_equivalent permits foreign functional/reporting'
    " views with approved effective-date spot equivalents, followed by "
    "effective-period average for reporting; original amounts and pinned rates "
    "are retained; equivalents are explicitly analytical, never actual posted FX "
    'attribution", "Native event TP composition shows fixed, constrained '
    "variable, returns, payable, financing, noncash and posting-rounding "
    "contributions in original currency; components reconcile to event TP change,"
    " totals count each modification once, missing historical evidence remains "
    'empty, and retained runs preserve their original column shape", "new native '
    "traces provide event-position TP changes and per-obligation catch-ups; "
    "verified trace hashes and node identities distinguish batched modifications;"
    " older traces retain version deltas with exact predecessors and refuse "
    'shared catch-ups", "source basis functional/reporting require contract '
    "currency to equal entity functional currency; reporting preserves original "
    "amounts and adds equivalents using the approved average of the modification "
    "effective period; these are analytical equivalents, not posted FX amounts; "
    'unknown measures stay empty and TP totals count each modification once", '
    '"same-source runs retain modification inputs, applied-version/preview '
    "provenance, resolved dates and reporting rates; reruns rebuild rows and "
    'totals without live reads", "entity code in entity_codes and within the '
    'caller\'s entity scope", "book_code = book", "modification.effective_date '
    'from from_date to to_date inclusive", "modification.status in status", '
    '"contract.external_id = contract_external_id when given", "with '
    "period_lock_id, the values frozen at that lock (lock_snapshot kind "
    'MODIFICATION_REGISTER)", "historical_source_commit_v1 retains original event'
    " and contract-version transaction commits; new event/version extracts and "
    "BBR event sources use commit cutoffs; historical version populations exclude"
    " later commits before latest selection; bound inputs keep their original "
    'interpretation"], "parameters": ["entity_codes", "book", "from_date", '
    '"to_date", "status", "contract_external_id", "period_lock_id", '
    '"currency_view", "currency_basis", "known_at", "known_at_basis"]}, '
    '"parameters_schema": {"$schema": '
    '"https://json-schema.org/draft/2020-12/schema", "type": "object", '
    '"additionalProperties": false, "properties": {"entity_codes": {"type": '
    '"array", "items": {"type": "string", "minLength": 1}, "minItems": 1, '
    '"uniqueItems": true}, "book": {"type": "string", "enum": ["ASC606", '
    '"IFRS15", "LEGACY"]}, "from_date": {"type": "string", "format": "date"}, '
    '"to_date": {"type": "string", "format": "date"}, "status": {"type": "array",'
    ' "items": {"type": "string", "enum": ["DRAFT", "SUBMITTED", "APPROVED", '
    '"APPLIED", "REJECTED", "VOIDED"]}, "uniqueItems": true}, '
    '"contract_external_id": {"type": "string", "minLength": 1}, '
    '"period_lock_id": {"type": "string", "format": "uuid"}, "currency_view": '
    '{"type": "string", "enum": ["transaction", "functional", "reporting"]}, '
    '"currency_basis": {"type": "string", "enum": ["source", "spot_equivalent", '
    '"causal_analysis"], "default": "source", "title": "Currency amount basis"}, '
    '"known_at": {"type": "string", "format": "date-time"}, "known_at_basis": '
    '{"type": "string", "enum": ["record", "historical"]}}}}'
)


def _set(value: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column in ("ipe_logic", "parameters_schema"):
        payload = json.dumps(value[column]).replace("'", "''")
        ops.execute(
            f"UPDATE erev.report_definition SET {column}='{payload}'::jsonb "  # noqa: S608
            "WHERE code='modification_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
