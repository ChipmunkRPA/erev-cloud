"""Register the exact-cutoff engine true-up report."""

from erev_api.db import migration_ops as ops

revision = "0180"
down_revision = "0179"
branch_labels = None
depends_on = None

TRUEUP_REPORT_SEED = """
INSERT INTO erev.report_definition (code, version, name, kind, description, parameters_schema, output_formats, ipe_logic, tie_outs, is_current) VALUES
  ('engine_trueup_register', 1, 'Engine true-up register', 'REGISTER', 'Upgrade processing states and attributed ledger amounts at the record cutoff.', '{"$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"properties":{"entity_codes":{"items":{"minLength":1,"type":"string"},"minItems":1,"type":"array","uniqueItems":true},"known_at":{"format":"date-time","type":"string"},"known_at_basis":{"enum":["record","historical"],"type":"string"},"release_validation_id":{"format":"uuid","type":"string"}},"required":["release_validation_id"],"type":"object"}', '{XLSX,CSV,JSON}', '{"filters":["Exact known_at; authorized entities; whole-group terminal hidden for partial scope"],"joins":["Processing portion to attributed sealed posting lines by entity and book"],"parameters":["entity_codes","release_validation_id","known_at","known_at_basis"],"source_tables":["release_group_processing","posting_attribution","subledger_posting","subledger_posting_seal","subledger_line","release_validation_group","legal_entity","period"],"version":1}', '{}', TRUE)
"""  # noqa: E501


def upgrade() -> None:
    ops.execute(TRUEUP_REPORT_SEED)


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute("DELETE FROM erev.report_definition WHERE code = 'engine_trueup_register'")
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
