"""Describe obligation-level exemption change details."""

from erev_api.db import migration_ops as ops

revision = "0221"
down_revision = "0220"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('exemption details retain obligation-level opening and closing exclusions, policy codes and transaction-currency movement; translated views label this original basis and legacy bindings retain their existing output shape'::text)) "  # noqa: E501
        "WHERE code = 'rpo_rollforward' "
        "AND version = 1 "
        "AND NOT (ipe_logic->'filters') ? 'exemption details retain obligation-level opening and closing exclusions, policy codes and transaction-currency movement; translated views label this original basis and legacy bindings retain their existing output shape'"  # noqa: E501
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'exemption details retain obligation-level opening and closing exclusions, policy codes and transaction-currency movement; translated views label this original basis and legacy bindings retain their existing output shape') "  # noqa: E501
        "WHERE code = 'rpo_rollforward' "
        "AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
