"""Retain latest contract status calculation inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0320"
down_revision = "0319"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract_version",'
    ' "contract_version_balance", "contract", "product", "legal_entity", '
    '"combination_group_member", "contract_computation", "historical_source_commit"], '
    '"joins": ["obligation_version.contract_version_id = contract_version.id", '
    '"obligation_version.contract_id = contract.id", '
    '"contract_version_balance.contract_version_id = contract_version.id", '
    '"obligation_version.product_id = product.id", "obligation_version.contracting_entity_id '
    '= legal_entity.id", "combination_group_member.contract_id = contract.id", '
    '"contract_version.contract_computation_id = contract_computation.id"], "filters": '
    '["entity code in entity_codes and within the caller\'s entity scope", "book_code = book",'
    ' "per contract, the latest contract version with effective_date on or before as_of among'
    " the versions recorded while the contract was a member of their group "
    '(combination_group_member), tie-broken by record_seq (04 \\u00a717.1 rule 1)", "rows '
    'recorded at or before known_at", "contract.external_id = contract_external_id when '
    'given", "the version number counts the versions computed with the contract among their '
    "members while it was a member of their combination group, along the contract's chain of "
    'groups in record order (combination_group_member, contract_computation)", '
    '"historical_source_commit_v1 retains original event and contract-version transaction '
    "commits; new event/version extracts and BBR event sources use commit cutoffs; historical"
    " version populations exclude later commits before latest selection; bound inputs keep "
    'their original interpretation"], "parameters": ["entity_codes", "book", "as_of", '
    '"contract_external_id", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract_version",'
    ' "contract_version_balance", "contract", "product", "legal_entity", '
    '"combination_group_member", "contract_computation", "historical_source_commit"], '
    '"joins": ["obligation_version.contract_version_id = contract_version.id", '
    '"obligation_version.contract_id = contract.id", '
    '"contract_version_balance.contract_version_id = contract_version.id", '
    '"obligation_version.product_id = product.id", "obligation_version.contracting_entity_id '
    '= legal_entity.id", "combination_group_member.contract_id = contract.id", '
    '"contract_version.contract_computation_id = contract_computation.id"], "filters": '
    '["same-source runs retain selected version values and resolved as-of cuts; rebuild '
    'figures and deduplicated balances without live contract reads", "entity code in '
    'entity_codes and within the caller\'s entity scope", "book_code = book", "per contract, '
    "the latest contract version with effective_date on or before as_of among the versions "
    "recorded while the contract was a member of their group (combination_group_member), tie-"
    'broken by record_seq (04 \\u00a717.1 rule 1)", "rows recorded at or before known_at", '
    '"contract.external_id = contract_external_id when given", "the version number counts the'
    " versions computed with the contract among their members while it was a member of their "
    "combination group, along the contract's chain of groups in record order "
    '(combination_group_member, contract_computation)", "historical_source_commit_v1 retains '
    "original event and contract-version transaction commits; new event/version extracts and "
    "BBR event sources use commit cutoffs; historical version populations exclude later "
    'commits before latest selection; bound inputs keep their original interpretation"], '
    '"parameters": ["entity_codes", "book", "as_of", "contract_external_id", "known_at", '
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
            + "'::jsonb WHERE code='latest_contract_status' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
