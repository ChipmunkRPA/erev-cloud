"""Describe the newly enabled loss-provision report's persisted sources."""

from erev_api.db import migration_ops as ops

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None

UPGRADE_SQL = 'UPDATE erev.report_definition SET ipe_logic = \'{"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","contracts in the loss-test scope of the book (POL-151) at the end of period_key","only_with_provision true: a non-zero provision balance"],"joins":["loss_provision_version.contract_version_id = contract_version.id","contract_version.id = the report-bound version read for each contract","loss_provision_version.period_key and as_of = the selected entity period","loss_provision_version.obligation_id = obligation.id","loss_provision_eac.loss_provision_version_id = loss_provision_version.id","loss_provision_eac.estimate_version_id = estimate_version.id","estimate_version.estimate_id = estimate.id"],"parameters":["entity_codes","book","period_lock_id","period_key","only_with_provision","currency_view","known_at","known_at_basis"],"source_tables":["loss_provision_version","loss_provision_eac","calc_trace","contract_version_balance","estimate","legal_entity","period","contract_version","contract","obligation","estimate_version"],"version":1}\'::jsonb WHERE code = \'loss_provision_register\' AND version = 1'  # noqa: E501
DOWNGRADE_SQL = 'UPDATE erev.report_definition SET ipe_logic = \'{"filters":["entity code in entity_codes and within the caller\'\'s entity scope","book_code = book","contracts in the loss-test scope of the book (POL-151) at the end of period_key","only_with_provision true: a non-zero provision balance"],"joins":["loss_provision_version.contract_version_id = contract_version.id","contract_version.id = the latest version of contract","loss_provision_version.obligation_id = obligation.id","loss_provision_version.eac_estimate_version_id = estimate_version.id"],"parameters":["entity_codes","book","period_lock_id","period_key","only_with_provision","currency_view","known_at","known_at_basis"],"source_tables":["loss_provision_version","contract_version","contract","obligation","estimate_version"],"version":1}\'::jsonb WHERE code = \'loss_provision_register\' AND version = 1'  # noqa: E501


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
