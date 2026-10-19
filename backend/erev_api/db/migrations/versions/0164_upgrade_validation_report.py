"""Register the frozen upgrade-validation report."""

from erev_api.db import migration_ops as ops

revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None

VALIDATION_REPORT_SEED = """
INSERT INTO erev.report_definition (code, version, name, kind, description, parameters_schema, output_formats, ipe_logic, tie_outs, is_current) VALUES
  ('upgrade_validation', 1, 'Upgrade validation', 'REGISTER', 'Frozen release validation outcomes and detailed comparison evidence.', '{"$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"properties":{"entity_codes":{"items":{"minLength":1,"type":"string"},"minItems":1,"type":"array","uniqueItems":true},"known_at":{"format":"date-time","type":"string"},"known_at_basis":{"enum":["record","historical"],"type":"string"},"release_validation_attempt_id":{"format":"uuid","type":"string"}},"required":["release_validation_attempt_id"],"type":"object"}', '{XLSX,CSV,JSON}', '{"filters":["Current report permission for every frozen entity; no partial population"],"joins":["Immutable attempt dataset file and digest"],"parameters":["entity_codes","release_validation_attempt_id","known_at","known_at_basis"],"source_tables":["release_validation_attempt","file_object"],"version":1}', '{}', TRUE)
"""  # noqa: E501


def upgrade() -> None:
    ops.execute(VALIDATION_REPORT_SEED)


def downgrade() -> None:
    # Retained report-run foreign keys refuse removal while evidence still exists.
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute("DELETE FROM erev.report_definition WHERE code = 'upgrade_validation'")
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
