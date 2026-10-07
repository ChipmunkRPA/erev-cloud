"""Describe the newly enabled balance-aging report's persisted sources."""

from erev_api.db import migration_ops as ops

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None

UPGRADE_SQL = 'UPDATE erev.report_definition SET ipe_logic = \'{"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","non-zero balances at the end of period_key","liability age: layer creation date to period end","asset/unbilled age: engine attribution revenue date to period end","balance_role when not ALL"],"joins":["fx_layer_movement.contract_version_id = contract_version_balance.contract_version_id","fx_layer_movement.contract_id = contract.id","contract.customer_id = customer.id","fx_layer_movement.entity_id = legal_entity.id"],"parameters":["entity_codes","book","period_lock_id","period_key","balance_role","currency_view","known_at","known_at_basis"],"source_tables":["fx_layer_movement","calc_trace","contract_version_balance","contract","customer","legal_entity"],"version":1}\'::jsonb WHERE code = \'balance_aging\' AND version = 1'  # noqa: E501
DOWNGRADE_SQL = 'UPDATE erev.report_definition SET ipe_logic = \'{"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","non-zero balances at the end of period_key","age: days from fx_layer_movement.effective_date to the end of period_key","balance_role when not ALL"],"joins":["fx_layer_movement.contract_version_id = contract_version_balance.contract_version_id","fx_layer_movement.contract_id = contract.id","contract.customer_id = customer.id","fx_layer_movement.entity_id = legal_entity.id"],"parameters":["entity_codes","book","period_lock_id","period_key","balance_role","currency_view","known_at","known_at_basis"],"source_tables":["fx_layer_movement","contract_version_balance","contract","customer","legal_entity"],"version":1}\'::jsonb WHERE code = \'balance_aging\' AND version = 1'  # noqa: E501


def _replace_metadata(statement: str) -> None:
    # Schema-owner migration only. The report has not previously been enabled; preserve its
    # version/key and every run, correcting the declared sources before first availability.
    # PostgreSQL rolls back both DDL and data if the transaction fails.
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(statement)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _replace_metadata(UPGRADE_SQL)


def downgrade() -> None:
    _replace_metadata(DOWNGRADE_SQL)
