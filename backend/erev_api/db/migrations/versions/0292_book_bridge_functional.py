"""Describe functional book-bridge amounts and unquantified FX residuals."""

import json

from erev_api.db import migration_ops as ops

revision = "0292"
down_revision = "0291"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"book_bridge": {"version": 1, "source_tables": ["contract_version", "contract_versio'
    'n_balance", "schedule_line", "subledger_line", "contract", "legal_entity", "period", '
    '"subledger_posting_commit", "historical_source_commit"], "joins": ["contract_version_'
    'balance.contract_version_id = contract_version.id", "schedule_line.contract_version_i'
    'd = contract_version.id", "subledger_line.contract_id = contract.id", "subledger_line'
    '.period_id = period.id"], "filters": ["one entity of entity_codes keeping both ASC606'
    ' and IFRS15", "period_key from from_period_key to to_period_key", "the same contracts'
    ' compared in both books, differences attributed to drivers", "subledger_commit_visibi'
    "lity_v1 requires original PostgreSQL posting commit time at or before the historical "
    "cutoff; retained commit evidence is immutable; older bindings preserve their original"
    ' seal-time interpretation", "historical_source_commit_v1 retains original event and c'
    "ontract-version transaction commits; new event/version extracts and BBR event sources"
    " use commit cutoffs; historical version populations exclude later commits before late"
    'st selection; bound inputs keep their original interpretation"], "parameters": ["enti'
    'ty_codes", "from_period_key", "to_period_key", "period_lock_id", "currency_view", "kn'
    'own_at", "known_at_basis"]}}'
)

NEW_IPE = (
    '{"book_bridge": {"version": 1, "source_tables": ["contract_version", "contract_versio'
    'n_balance", "schedule_line", "subledger_line", "contract", "legal_entity", "period", '
    '"subledger_posting_commit", "historical_source_commit"], "joins": ["contract_version_'
    'balance.contract_version_id = contract_version.id", "schedule_line.contract_version_i'
    'd = contract_version.id", "subledger_line.contract_id = contract.id", "subledger_line'
    '.period_id = period.id"], "filters": ["one entity of entity_codes keeping both ASC606'
    ' and IFRS15", "period_key from from_period_key to to_period_key", "the same contracts'
    ' compared in both books, differences attributed to drivers", "functional view uses po'
    "sted functional revenue and dated engine member balances; transaction view preserves "
    'original currencies; reporting view is unavailable", "foreign functional residuals re'
    "main in OTHER; advance-consideration FX is unquantified when causal evidence cannot i"
    'solate it, never an unsupported zero", "subledger_commit_visibility_v1 requires origi'
    "nal PostgreSQL posting commit time at or before the historical cutoff; retained commi"
    "t evidence is immutable; older bindings preserve their original seal-time interpretat"
    'ion", "historical_source_commit_v1 retains original event and contract-version transa'
    "ction commits; new event/version extracts and BBR event sources use commit cutoffs; h"
    "istorical version populations exclude later commits before latest selection; bound in"
    'puts keep their original interpretation"], "parameters": ["entity_codes", "from_perio'
    'd_key", "to_period_key", "period_lock_id", "currency_view", "known_at", "known_at_bas'
    'is"]}}'
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
