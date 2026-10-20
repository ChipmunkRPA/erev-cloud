"""Enable retained reporting-currency close variance."""

from erev_api.db import migration_ops as ops

revision = "0191"
down_revision = "0190"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET parameters_schema = \'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"properties":{"entity_codes":{"type":"array","items":{"type":"string","minLength":1},"minItems":1,"uniqueItems":true},"from_period_lock_id":{"type":"string","format":"uuid"},"to_period_lock_id":{"type":"string","format":"uuid"},"currency_view":{"type":"string","enum":["transaction","functional","reporting"]},"known_at":{"type":"string","format":"date-time"},"known_at_basis":{"type":"string","enum":["record","historical"]}}}\'::jsonb WHERE code = \'variance_between_closes\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET parameters_schema = \'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"properties":{"entity_codes":{"type":"array","items":{"type":"string","minLength":1},"minItems":1,"uniqueItems":true},"from_period_lock_id":{"type":"string","format":"uuid"},"to_period_lock_id":{"type":"string","format":"uuid"},"currency_view":{"type":"string","enum":["transaction","functional"]},"known_at":{"type":"string","format":"date-time"},"known_at_basis":{"type":"string","enum":["record","historical"]}}}\'::jsonb WHERE code = \'variance_between_closes\' AND version = 1'  # noqa: E501


def _apply(statement: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(statement)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _apply(UP)


def downgrade() -> None:
    _apply(DOWN)
