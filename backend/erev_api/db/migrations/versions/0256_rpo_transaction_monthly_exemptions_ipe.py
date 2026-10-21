"""Retain intermediate monthly transaction-currency RPO exemption movements."""

from erev_api.db import migration_ops as ops

revision = "0256"
down_revision = "0255"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_transaction_monthly_exemptions_v1 retains "
        "nonzero original contract/entity/period exemption movements in transaction-currency "
        "reports, including intermediate entry and exit hidden by range endpoint disclosures; "
        "exemption_translation holds unchanged original and report amounts for the shared detail "
        "schema, labelled as monthly movements without claiming FX translation or equality to the "
        "range endpoint-based Exemptions line; older transaction bindings retain their prior "
        "detail population'::text)) WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_transaction_monthly_exemptions_v1 retains nonzero original "
        "contract/entity/period exemption movements in transaction-currency reports, including "
        "intermediate entry and exit hidden by range endpoint disclosures; exemption_translation "
        "holds unchanged original and report amounts for the shared detail schema, labelled as "
        "monthly movements without claiming FX translation or equality to the range "
        "endpoint-based Exemptions line; older transaction bindings retain their prior detail "
        "population') WHERE code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
