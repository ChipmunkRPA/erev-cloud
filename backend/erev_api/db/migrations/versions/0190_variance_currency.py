"""Enable retained functional-currency close variance."""

from erev_api.db import migration_ops as ops

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None

UP = 'UPDATE erev.report_definition SET parameters_schema = \'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"properties":{"entity_codes":{"type":"array","items":{"type":"string","minLength":1},"minItems":1,"uniqueItems":true},"from_period_lock_id":{"type":"string","format":"uuid"},"to_period_lock_id":{"type":"string","format":"uuid"},"currency_view":{"type":"string","enum":["transaction","functional"]},"known_at":{"type":"string","format":"date-time"},"known_at_basis":{"type":"string","enum":["record","historical"]}}}\'::jsonb, ipe_logic = \'{"version":1,"source_tables":["period_lock","lock_snapshot","disclosure_snapshot","contract"],"joins":["lock_snapshot.period_lock_id = period_lock.id","disclosure_snapshot.period_lock_id = period_lock.id"],"filters":["two locks of one entity, book and period; the later recorded after the earlier","locks of an entity in entity_codes","changes attributed to drivers"],"parameters":["entity_codes","from_period_lock_id","to_period_lock_id","currency_view","known_at","known_at_basis"]}\'::jsonb WHERE code = \'variance_between_closes\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET parameters_schema = \'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","additionalProperties":false,"properties":{"entity_codes":{"type":"array","items":{"type":"string","minLength":1},"minItems":1,"uniqueItems":true},"from_period_lock_id":{"type":"string","format":"uuid"},"to_period_lock_id":{"type":"string","format":"uuid"},"known_at":{"type":"string","format":"date-time"},"known_at_basis":{"type":"string","enum":["record","historical"]}}}\'::jsonb, ipe_logic = \'{"version":1,"source_tables":["period_lock","lock_snapshot","disclosure_snapshot","contract"],"joins":["lock_snapshot.period_lock_id = period_lock.id","disclosure_snapshot.period_lock_id = period_lock.id"],"filters":["two locks of one entity, book and period; the later recorded after the earlier","locks of an entity in entity_codes","changes attributed to drivers"],"parameters":["entity_codes","from_period_lock_id","to_period_lock_id","known_at","known_at_basis"]}\'::jsonb WHERE code = \'variance_between_closes\' AND version = 1'  # noqa: E501


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
