"""Document terminal realized-fee RPO attribution."""

from erev_api.db import migration_ops as ops

revision = "0244"
down_revision = "0243"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') || to_jsonb('rpo_cancelled_usage_v1 separates terminal "
        "realized-fee changes from fixed cancellation attribution when opening and terminating "
        "versions both retain dated realization evidence; a single later termination uses its "
        "realized amount, while fixed modifications and estimates still require the original "
        "pre-termination bridge; legacy bindings keep prior classification'::text)) WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
        "(ipe_logic->'filters') - 'rpo_cancelled_usage_v1 separates terminal realized-fee "
        "changes from fixed cancellation attribution when opening and terminating versions both "
        "retain dated realization evidence; a single later termination uses its realized "
        "amount, while fixed modifications and estimates still require the original "
        "pre-termination bridge; legacy bindings keep prior classification') WHERE "
        "code='rpo_rollforward' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
