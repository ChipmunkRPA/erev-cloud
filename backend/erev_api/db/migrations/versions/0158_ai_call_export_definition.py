"""Register the live, requester-bound AI call-log export."""

from erev_api.db import migration_ops as ops

revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None

CALL_EXPORT_SEED = """
INSERT INTO erev.report_definition (
    code, version, name, kind, description, parameters_schema,
    output_formats, ipe_logic, tie_outs, is_current
) VALUES (
    'ai_call_log_export', 1, 'AI call log export', 'EXTRACT',
    'Current authorized call evidence; reruns are new live evaluations.',
    '{"additionalProperties":false,"properties":{},"type":"object"}',
    '{CSV,XLSX}',
    '{"filters":["Original requester scope and current source/export permissions"],
      "joins":[],"parameters":[],"source_tables":["ai_model_log"],"version":1}',
    '{}', TRUE
)
"""


def upgrade() -> None:
    ops.execute(CALL_EXPORT_SEED)


def downgrade() -> None:
    # The existing report-run foreign key refuses removal while any retained run exists.
    # PostgreSQL rolls back both the deletion and trigger change on that refusal.
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute("DELETE FROM erev.report_definition WHERE code = 'ai_call_log_export'")
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
