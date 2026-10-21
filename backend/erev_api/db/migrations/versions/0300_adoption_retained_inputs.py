"""Describe retained adoption inputs for same-source reconstruction."""

import json

from erev_api.db import migration_ops as ops

revision = "0300"
down_revision = "0299"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"adoption_bridge": {"version": 1, "source_tables": ["contract_version", "contract_v'
    'ersion_balance", "obligation_version", "contract", "customer", "subledger_line", "te'
    'nant", "fx_rate", "fx_rate_set", "fx_rate_set_version", "subledger_posting_commit", '
    '"historical_source_commit"], "joins": ["contract_version_balance.contract_version_id'
    ' = contract_version.id", "obligation_version.contract_version_id = contract_version.'
    'id", "contract_version_balance.contract_id = contract.id", "contract.customer_id = c'
    'ustomer.id"], "filters": ["one entity of entity_codes keeping the LEGACY book", "ASC'
    '606 and LEGACY figures at date_of_initial_application", "contract.external_id = cont'
    'ract_external_id when given", "functional view uses posted legacy revenue and reconc'
    "iled dated primary revenue and balances; foreign legacy positions without historical"
    ' carrying evidence are unavailable, including affected aggregate comparisons", "repo'
    "rting view translates each period change in functional cumulative revenue at its ave"
    "rage rate and ending balances independently at the closing rate; legacy-only histori"
    "cal revenue remains in its final endpoint population; nonzero imported opening reven"
    'ue without dated history cannot be translated", "subledger_commit_visibility_v1 requ'
    "ires original PostgreSQL posting commit time at or before the historical cutoff; ret"
    "ained commit evidence is immutable; older bindings preserve their original seal-time"
    ' interpretation", "historical_source_commit_v1 retains original event and contract-v'
    "ersion transaction commits; new event/version extracts and BBR event sources use com"
    "mit cutoffs; historical version populations exclude later commits before latest sele"
    'ction; bound inputs keep their original interpretation"], "parameters": ["entity_cod'
    'es", "date_of_initial_application", "contract_external_id", "currency_view", "known_'
    'at", "known_at_basis"]}}'
)

NEW_IPE = (
    '{"adoption_bridge": {"version": 1, "source_tables": ["contract_version", "contract_v'
    'ersion_balance", "obligation_version", "contract", "customer", "subledger_line", "te'
    'nant", "fx_rate", "fx_rate_set", "fx_rate_set_version", "subledger_posting_commit", '
    '"historical_source_commit"], "joins": ["contract_version_balance.contract_version_id'
    ' = contract_version.id", "obligation_version.contract_version_id = contract_version.'
    'id", "contract_version_balance.contract_id = contract.id", "contract.customer_id = c'
    'ustomer.id"], "filters": ["one entity of entity_codes keeping the LEGACY book", "ASC'
    '606 and LEGACY figures at date_of_initial_application", "same-source reruns reconstr'
    "uct sections, membership counts and totals from retained per-contract adoption input"
    's, date and currency basis without live source or rate reads", "contract.external_id'
    ' = contract_external_id when given", "functional view uses posted legacy revenue and'
    " reconciled dated primary revenue and balances; foreign legacy positions without his"
    'torical carrying evidence are unavailable, including affected aggregate comparisons"'
    ', "reporting view translates each period change in functional cumulative revenue at '
    "its average rate and ending balances independently at the closing rate; legacy-only "
    "historical revenue remains in its final endpoint population; nonzero imported openin"
    'g revenue without dated history cannot be translated", "subledger_commit_visibility_'
    "v1 requires original PostgreSQL posting commit time at or before the historical cuto"
    "ff; retained commit evidence is immutable; older bindings preserve their original se"
    'al-time interpretation", "historical_source_commit_v1 retains original event and con'
    "tract-version transaction commits; new event/version extracts and BBR event sources "
    "use commit cutoffs; historical version populations exclude later commits before late"
    'st selection; bound inputs keep their original interpretation"], "parameters": ["ent'
    'ity_codes", "date_of_initial_application", "contract_external_id", "currency_view", '
    '"known_at", "known_at_basis"]}}'
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
