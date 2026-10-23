"""Document original event amounts in the modification register."""

import json

from erev_api.db import migration_ops as ops

revision = "0325"
down_revision = "0324"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", "ap'
    'proval_request", "approval_decision", "judgement_record", "contract_version", '
    '"lock_snapshot", "legal_entity", "period", "tenant", "fx_rate", "fx_rate_set",'
    ' "fx_rate_set_version", "historical_source_commit"], "joins": ["modification.c'
    'ontract_id = contract.id", "modification.approval_request_id = approval_reques'
    't.id", "approval_decision.approval_request_id = approval_request.id", "modific'
    'ation.judgement_record_id = judgement_record.id"], "filters": ["functional/rep'
    'orting require contract currency to equal entity functional currency; reportin'
    'g preserves original amounts and adds equivalents using the approved average o'
    'f the modification effective period; these are analytical equivalents, not pos'
    'ted FX amounts; unknown measures stay empty and TP totals count each modificat'
    'ion once", "same-source runs retain modification inputs, applied-version/previ'
    'ew provenance, resolved dates and reporting rates; reruns rebuild rows and tot'
    'als without live reads", "entity code in entity_codes and within the caller\'s '
    'entity scope", "book_code = book", "modification.effective_date from from_date'
    ' to to_date inclusive", "modification.status in status", "contract.external_id'
    ' = contract_external_id when given", "with period_lock_id, the values frozen a'
    't that lock (lock_snapshot kind MODIFICATION_REGISTER)", "historical_source_co'
    'mmit_v1 retains original event and contract-version transaction commits; new e'
    'vent/version extracts and BBR event sources use commit cutoffs; historical ver'
    'sion populations exclude later commits before latest selection; bound inputs k'
    'eep their original interpretation"], "parameters": ["entity_codes", "book", "f'
    'rom_date", "to_date", "status", "contract_external_id", "period_lock_id", "cur'
    'rency_view", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", "ap'
    'proval_request", "approval_decision", "judgement_record", "contract_version", '
    '"calc_trace", "lock_snapshot", "legal_entity", "period", "tenant", "fx_rate", '
    '"fx_rate_set", "fx_rate_set_version", "historical_source_commit"], "joins": ["'
    'modification.contract_id = contract.id", "modification.approval_request_id = a'
    'pproval_request.id", "approval_decision.approval_request_id = approval_request'
    '.id", "modification.judgement_record_id = judgement_record.id"], "filters": ["'
    'new native traces provide event-position TP changes and per-obligation catch-u'
    'ps; verified trace hashes and node identities distinguish batched modification'
    's; older traces retain version deltas with exact predecessors and refuse share'
    'd catch-ups", "functional/reporting require contract currency to equal entity '
    'functional currency; reporting preserves original amounts and adds equivalents'
    ' using the approved average of the modification effective period; these are an'
    'alytical equivalents, not posted FX amounts; unknown measures stay empty and T'
    'P totals count each modification once", "same-source runs retain modification '
    'inputs, applied-version/preview provenance, resolved dates and reporting rates'
    '; reruns rebuild rows and totals without live reads", "entity code in entity_c'
    'odes and within the caller\'s entity scope", "book_code = book", "modification.'
    'effective_date from from_date to to_date inclusive", "modification.status in s'
    'tatus", "contract.external_id = contract_external_id when given", "with period'
    '_lock_id, the values frozen at that lock (lock_snapshot kind MODIFICATION_REGI'
    'STER)", "historical_source_commit_v1 retains original event and contract-versi'
    'on transaction commits; new event/version extracts and BBR event sources use c'
    'ommit cutoffs; historical version populations exclude later commits before lat'
    'est selection; bound inputs keep their original interpretation"], "parameters"'
    ': ["entity_codes", "book", "from_date", "to_date", "status", "contract_externa'
    'l_id", "period_lock_id", "currency_view", "known_at", "known_at_basis"]}}'
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
