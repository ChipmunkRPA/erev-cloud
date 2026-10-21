"""Describe retained intercompany line reconstruction."""

import json

from erev_api.db import migration_ops as ops

revision = "0297"
down_revision = "0296"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"intercompany_pairs": {"version": 1, "source_tables": ["subledger_line", "obligatio'
    'n_version", "contract", "legal_entity", "period", "tenant", "fx_rate", "fx_rate_set"'
    ', "fx_rate_set_version", "subledger_posting_commit"], "joins": ["subledger_line.coun'
    'terparty_entity_id = legal_entity.id", "subledger_line.obligation_id = obligation_ve'
    'rsion.obligation_id", "subledger_line.contract_id = contract.id", "subledger_line.pe'
    'riod_id = period.id"], "filters": ["entity code in entity_codes and within the calle'
    'r\'s entity scope", "book_code = book", "period_key from from_period_key to to_period'
    '_key", "functional view reads posted functional activity; different functional curre'
    'ncies remain separate with incomparable sides empty", "reporting view translates pos'
    "ted functional period activity at approved period-average rates to one reporting cur"
    'rency; unmatched translation residuals remain visible", "subledger_line.counterparty'
    "_entity_id is not null: an obligation performed by an entity other than the contract"
    'ing entity", "subledger_commit_visibility_v1 requires original PostgreSQL posting co'
    "mmit time at or before the historical cutoff; retained commit evidence is immutable;"
    ' older bindings preserve their original seal-time interpretation"], "parameters": ["'
    'entity_codes", "book", "period_lock_id", "from_period_key", "to_period_key", "curren'
    'cy_view", "known_at", "known_at_basis"]}}'
)

NEW_IPE = (
    '{"intercompany_pairs": {"version": 1, "source_tables": ["subledger_line", "obligatio'
    'n_version", "contract", "legal_entity", "period", "tenant", "fx_rate", "fx_rate_set"'
    ', "fx_rate_set_version", "subledger_posting_commit"], "joins": ["subledger_line.coun'
    'terparty_entity_id = legal_entity.id", "subledger_line.obligation_id = obligation_ve'
    'rsion.obligation_id", "subledger_line.contract_id = contract.id", "subledger_line.pe'
    'riod_id = period.id"], "filters": ["entity code in entity_codes and within the calle'
    'r\'s entity scope", "book_code = book", "period_key from from_period_key to to_period'
    '_key", "functional view reads posted functional activity; different functional curre'
    'ncies remain separate with incomparable sides empty", "reporting view translates pos'
    "ted functional period activity at approved period-average rates to one reporting cur"
    'rency; unmatched translation residuals remain visible", "same-source reruns reconstr'
    "uct pairs from retained per-line amounts and entity/currency scope without reading l"
    'ive ledger lines, labels or FX rates", "subledger_line.counterparty_entity_id is not'
    ' null: an obligation performed by an entity other than the contracting entity", "sub'
    "ledger_commit_visibility_v1 requires original PostgreSQL posting commit time at or b"
    "efore the historical cutoff; retained commit evidence is immutable; older bindings p"
    'reserve their original seal-time interpretation"], "parameters": ["entity_codes", "b'
    'ook", "period_lock_id", "from_period_key", "to_period_key", "currency_view", "known_'
    'at", "known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, ipe in json.loads(encoded).items():
        payload = json.dumps(ipe).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_IPE)


def downgrade() -> None:
    _metadata(OLD_IPE)
