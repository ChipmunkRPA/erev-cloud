"""Retain scope-exclusion inputs and document reporting equivalents."""

import json

from erev_api.db import migration_ops as ops

revision = "0310"
down_revision = "0309"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract_version",'
    ' "contract", "product", "judgement_record", "combination_group_member", '
    '"historical_source_commit"], "joins": ["obligation_version.contract_version_id = '
    'contract_version.id", "obligation_version.contract_id = contract.id", '
    '"obligation_version.product_id = product.id", "judgement_record.contract_id = '
    'contract.id", "combination_group_member.contract_id = contract.id"], "filters": ["entity'
    ' code in entity_codes and within the caller\'s entity scope", "book_code = book", "per '
    "contract, the contract_version at the date along the contract's chain of combination "
    "groups: the versions recorded while the contract was a member of their group "
    '(combination_group_member)", "obligation versions at the end of period_key with '
    'scope_flag other than IN_SCOPE_606", "historical_source_commit_v1 retains original event'
    " and contract-version transaction commits; new event/version extracts and BBR event "
    "sources use commit cutoffs; historical version populations exclude later commits before "
    'latest selection; bound inputs keep their original interpretation"], "parameters": '
    '["entity_codes", "book", "period_lock_id", "period_key", "currency_view", "known_at", '
    '"known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract_version",'
    ' "contract", "product", "judgement_record", "combination_group_member", "legal_entity", '
    '"tenant", "period", "fx_rate", "fx_rate_set", "fx_rate_set_version", '
    '"historical_source_commit"], "joins": ["obligation_version.contract_version_id = '
    'contract_version.id", "obligation_version.contract_id = contract.id", '
    '"obligation_version.product_id = product.id", "judgement_record.contract_id = '
    'contract.id", "combination_group_member.contract_id = contract.id"], "filters": ["same-'
    "source runs retain scope amounts, judgement values and reporting rates; rebuild without "
    "live reads; reporting retains original amounts and adds analytical equivalents at the "
    'report-period closing rate, not carrying balances; missing amounts stay empty", "entity '
    'code in entity_codes and within the caller\'s entity scope", "book_code = book", "per '
    "contract, the contract_version at the date along the contract's chain of combination "
    "groups: the versions recorded while the contract was a member of their group "
    '(combination_group_member)", "obligation versions at the end of period_key with '
    'scope_flag other than IN_SCOPE_606", "historical_source_commit_v1 retains original event'
    " and contract-version transaction commits; new event/version extracts and BBR event "
    "sources use commit cutoffs; historical version populations exclude later commits before "
    'latest selection; bound inputs keep their original interpretation"], "parameters": '
    '["entity_codes", "book", "period_lock_id", "period_key", "currency_view", "known_at", '
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
            + "'::jsonb WHERE code='scope_exclusion_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
