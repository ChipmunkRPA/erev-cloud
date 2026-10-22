"""Retain original inputs for both legacy contract exports."""

import json

from erev_api.db import migration_ops as ops

revision = "0321"
down_revision = "0320"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"legacy_contract_history_export": {"ipe_logic": {"version": 1, "source_tables": '
    '["obligation_version", "contract_version", "contract", "migrated_legacy_row", '
    '"combination_group_member", "contract_computation"], "joins": '
    '["obligation_version.contract_version_id = contract_version.id", '
    '"obligation_version.contract_id = contract.id", "migrated_legacy_row.contract_id = '
    'contract.id", "combination_group_member.contract_id = contract.id", '
    '"contract_version.contract_computation_id = contract_computation.id"], "filters": '
    '["entity code in entity_codes and within the caller\'s entity scope", "book fixed to '
    'ASC606", "04 \\u00a717.1 rules 1 to 6 over obligation versions effective from from_date '
    'to to_date", "rows before a cutover from migrated_legacy_row.legacy_row unchanged", '
    '"contract.external_id = contract_external_id when given", "the version number counts the'
    " versions computed with the contract among their members while it was a member of their "
    "combination group, along the contract's chain of groups in record order "
    '(combination_group_member, contract_computation)"], "parameters": ["entity_codes", '
    '"book", "from_date", "to_date", "contract_external_id", "known_at", "known_at_basis"]}},'
    ' "legacy_latest_contract_export": {"ipe_logic": {"version": 1, "source_tables": '
    '["obligation_version", "contract_version", "contract", "migrated_legacy_row"], "joins": '
    '["obligation_version.contract_version_id = contract_version.id", '
    '"obligation_version.contract_id = contract.id", "migrated_legacy_row.contract_id = '
    'contract.id"], "filters": ["entity code in entity_codes and within the caller\'s entity '
    'scope", "book fixed to ASC606", "the RPT-11 row rule at as_of", "contract.external_id = '
    'contract_external_id when given"], "parameters": ["entity_codes", "book", "as_of", '
    '"contract_external_id", "known_at", "known_at_basis"]}}}'
)

NEW_METADATA = (
    '{"legacy_contract_history_export": {"ipe_logic": {"version": 1, "source_tables": '
    '["obligation_version", "contract_version", "contract", "migrated_legacy_row", '
    '"combination_group_member", "contract_computation"], "joins": '
    '["obligation_version.contract_version_id = contract_version.id", '
    '"obligation_version.contract_id = contract.id", "migrated_legacy_row.contract_id = '
    'contract.id", "combination_group_member.contract_id = contract.id", '
    '"contract_version.contract_computation_id = contract_computation.id"], "filters": '
    '["same-source runs retain current/predecessor version inputs and verified exact texts; '
    'rebuild the 71 columns without live contract or trace reads", "entity code in '
    'entity_codes and within the caller\'s entity scope", "book fixed to ASC606", "04 '
    '\\u00a717.1 rules 1 to 6 over obligation versions effective from from_date to to_date", '
    '"rows before a cutover from migrated_legacy_row.legacy_row unchanged", '
    '"contract.external_id = contract_external_id when given", "the version number counts the'
    " versions computed with the contract among their members while it was a member of their "
    "combination group, along the contract's chain of groups in record order "
    '(combination_group_member, contract_computation)"], "parameters": ["entity_codes", '
    '"book", "from_date", "to_date", "contract_external_id", "known_at", "known_at_basis"]}},'
    ' "legacy_latest_contract_export": {"ipe_logic": {"version": 1, "source_tables": '
    '["obligation_version", "contract_version", "contract", "migrated_legacy_row"], "joins": '
    '["obligation_version.contract_version_id = contract_version.id", '
    '"obligation_version.contract_id = contract.id", "migrated_legacy_row.contract_id = '
    'contract.id"], "filters": ["same-source runs retain current/predecessor version inputs '
    'and verified exact texts; rebuild the 71 columns without live contract or trace reads", '
    '"entity code in entity_codes and within the caller\'s entity scope", "book fixed to '
    'ASC606", "the RPT-11 row rule at as_of", "contract.external_id = contract_external_id '
    'when given"], "parameters": ["entity_codes", "book", "as_of", "contract_external_id", '
    '"known_at", "known_at_basis"]}}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, metadata in json.loads(encoded).items():
        payload = json.dumps(metadata["ipe_logic"]).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
