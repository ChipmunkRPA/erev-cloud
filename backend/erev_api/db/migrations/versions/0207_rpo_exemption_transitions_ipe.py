"""Describe endpoint-specific full RPO exemption attribution."""

from erev_api.db import migration_ops as ops

revision = "0207"
down_revision = "0206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('full RPO exemption eligibility is evaluated per retained version; opening and closing exclusions are separate, with eligibility changes in EXEMPTIONS'::text)) "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'full RPO exemption eligibility is evaluated per retained version; opening and closing exclusions are separate, with eligibility changes in EXEMPTIONS'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'full RPO exemption eligibility is evaluated per retained version; opening and closing exclusions are separate, with eligibility changes in EXEMPTIONS') "  # noqa: E501
        "WHERE code = 'rpo_rollforward' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
