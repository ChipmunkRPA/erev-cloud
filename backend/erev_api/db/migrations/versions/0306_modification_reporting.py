"""Document reporting equivalents and their effective-period rate basis."""

import json

from erev_api.db import migration_ops as ops

revision = "0306"
down_revision = "0305"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", '
    '"approval_request", "approval_decision", "judgement_record", "contract_version", '
    '"lock_snapshot", "historical_source_commit"], "joins": ["modification.contract_id = '
    'contract.id", "modification.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"modification.judgement_record_id = judgement_record.id"], "filters": ["entity code in '
    'entity_codes and within the caller\'s entity scope", "book_code = book", '
    '"modification.effective_date from from_date to to_date inclusive", "modification.status in'
    ' status", "contract.external_id = contract_external_id when given", "with period_lock_id, '
    'the values frozen at that lock (lock_snapshot kind MODIFICATION_REGISTER)", '
    '"historical_source_commit_v1 retains original event and contract-version transaction '
    "commits; new event/version extracts and BBR event sources use commit cutoffs; historical "
    "version populations exclude later commits before latest selection; bound inputs keep their"
    ' original interpretation"], "parameters": ["entity_codes", "book", "from_date", "to_date",'
    ' "status", "contract_external_id", "period_lock_id", "currency_view", "known_at", '
    '"known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["modification", "contract", '
    '"approval_request", "approval_decision", "judgement_record", "contract_version", '
    '"lock_snapshot", "legal_entity", "period", "tenant", "fx_rate", "fx_rate_set", '
    '"fx_rate_set_version", "historical_source_commit"], "joins": ["modification.contract_id = '
    'contract.id", "modification.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"modification.judgement_record_id = judgement_record.id"], "filters": '
    '["functional/reporting require contract currency to equal entity functional currency; '
    "reporting preserves original amounts and adds equivalents using the approved average of "
    "the modification effective period; these are analytical equivalents, not posted FX "
    'amounts; unknown measures stay empty and TP totals count each modification once", "entity '
    'code in entity_codes and within the caller\'s entity scope", "book_code = book", '
    '"modification.effective_date from from_date to to_date inclusive", "modification.status in'
    ' status", "contract.external_id = contract_external_id when given", "with period_lock_id, '
    'the values frozen at that lock (lock_snapshot kind MODIFICATION_REGISTER)", '
    '"historical_source_commit_v1 retains original event and contract-version transaction '
    "commits; new event/version extracts and BBR event sources use commit cutoffs; historical "
    "version populations exclude later commits before latest selection; bound inputs keep their"
    ' original interpretation"], "parameters": ["entity_codes", "book", "from_date", "to_date",'
    ' "status", "contract_external_id", "period_lock_id", "currency_view", "known_at", '
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
