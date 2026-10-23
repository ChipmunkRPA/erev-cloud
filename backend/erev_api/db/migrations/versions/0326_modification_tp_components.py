"""Document original event price composition in the modification register."""

import json

from erev_api.db import migration_ops as ops

revision = "0326"
down_revision = "0325"
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
    "new native traces provide event-position TP changes and per-obligation catch-u"
    "ps; verified trace hashes and node identities distinguish batched modification"
    "s; older traces retain version deltas with exact predecessors and refuse share"
    'd catch-ups", "functional/reporting require contract currency to equal entity '
    "functional currency; reporting preserves original amounts and adds equivalents"
    " using the approved average of the modification effective period; these are an"
    "alytical equivalents, not posted FX amounts; unknown measures stay empty and T"
    'P totals count each modification once", "same-source runs retain modification '
    "inputs, applied-version/preview provenance, resolved dates and reporting rates"
    '; reruns rebuild rows and totals without live reads", "entity code in entity_c'
    'odes and within the caller\'s entity scope", "book_code = book", "modification.'
    'effective_date from from_date to to_date inclusive", "modification.status in s'
    'tatus", "contract.external_id = contract_external_id when given", "with period'
    "_lock_id, the values frozen at that lock (lock_snapshot kind MODIFICATION_REGI"
    'STER)", "historical_source_commit_v1 retains original event and contract-versi'
    "on transaction commits; new event/version extracts and BBR event sources use c"
    "ommit cutoffs; historical version populations exclude later commits before lat"
    'est selection; bound inputs keep their original interpretation"], "parameters"'
    ': ["entity_codes", "book", "from_date", "to_date", "status", "contract_externa'
    'l_id", "period_lock_id", "currency_view", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
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
            + "'::jsonb WHERE code='modification_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
