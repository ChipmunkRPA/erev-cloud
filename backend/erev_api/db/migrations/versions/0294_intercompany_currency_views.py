"""Describe posted functional and common reporting currency intercompany activity."""

import json

from erev_api.db import migration_ops as ops

revision = "0294"
down_revision = "0293"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"intercompany_pairs": {"version": 1, "source_tables": ["subledger_line", "obligation'
    '_version", "contract", "legal_entity", "period", "subledger_posting_commit"], "joins"'
    ': ["subledger_line.counterparty_entity_id = legal_entity.id", "subledger_line.obligat'
    'ion_id = obligation_version.obligation_id", "subledger_line.contract_id = contract.id'
    '", "subledger_line.period_id = period.id"], "filters": ["entity code in entity_codes '
    'and within the caller\'s entity scope", "book_code = book", "period_key from from_peri'
    'od_key to to_period_key", "subledger_line.counterparty_entity_id is not null: an obli'
    'gation performed by an entity other than the contracting entity", "subledger_commit_v'
    "isibility_v1 requires original PostgreSQL posting commit time at or before the histor"
    "ical cutoff; retained commit evidence is immutable; older bindings preserve their ori"
    'ginal seal-time interpretation"], "parameters": ["entity_codes", "book", "period_lock'
    '_id", "from_period_key", "to_period_key", "currency_view", "known_at", "known_at_basi'
    's"]}}'
)

NEW_IPE = (
    '{"intercompany_pairs": {"version": 1, "source_tables": ["subledger_line", "obligation'
    '_version", "contract", "legal_entity", "period", "tenant", "fx_rate", "fx_rate_set", '
    '"fx_rate_set_version", "subledger_posting_commit"], "joins": ["subledger_line.counter'
    'party_entity_id = legal_entity.id", "subledger_line.obligation_id = obligation_versio'
    'n.obligation_id", "subledger_line.contract_id = contract.id", "subledger_line.period_'
    'id = period.id"], "filters": ["entity code in entity_codes and within the caller\'s en'
    'tity scope", "book_code = book", "period_key from from_period_key to to_period_key", '
    '"functional view reads posted functional activity; different functional currencies re'
    'main separate with incomparable sides empty", "reporting view translates posted funct'
    "ional period activity at approved period-average rates to one reporting currency; unm"
    'atched translation residuals remain visible", "subledger_line.counterparty_entity_id '
    'is not null: an obligation performed by an entity other than the contracting entity",'
    ' "subledger_commit_visibility_v1 requires original PostgreSQL posting commit time at '
    "or before the historical cutoff; retained commit evidence is immutable; older binding"
    's preserve their original seal-time interpretation"], "parameters": ["entity_codes", '
    '"book", "period_lock_id", "from_period_key", "to_period_key", "currency_view", "known'
    '_at", "known_at_basis"]}}'
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
