"""Expose functional-currency live disclosure packs; preserve historical locked sources."""

import json
from erev_api.db import migration_ops as ops

revision = "0344"
down_revision = "0343"
branch_labels = None
depends_on = None

OLD = {
    "ipe_logic": {
        "filters": [
            "one entity of entity_codes, book and period_key",
            "section runs of revenue_waterfall, contract_balances, "
            "contract_balance_rollforward, revenue_from_opening_liability, "
            "revenue_from_prior_period_obligations, rpo, rpo_rollforward "
            "and disaggregation (T-RPT-01 rule 2)",
            "a locked period reads the disclosure_snapshot rows frozen at lock",
            "quarter true: the fiscal quarter-to-date column",
        ],
        "joins": [
            "report_run.child_report_run_ids holds the section runs",
            "report_run.disclosure_snapshot_ids holds the snapshots read",
            "disclosure_snapshot.period_lock_id = period_lock.id",
        ],
        "parameters": [
            "entity_codes",
            "book",
            "period_key",
            "period_lock_id",
            "quarter",
            "known_at",
            "known_at_basis",
        ],
        "source_tables": ["report_run", "disclosure_snapshot", "registry_version", "period_lock"],
        "version": 1,
    },
    "parameters_schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "book": {"enum": ["ASC606", "IFRS15", "LEGACY"], "type": "string"},
            "entity_codes": {
                "items": {"minLength": 1, "type": "string"},
                "maxItems": 1,
                "minItems": 1,
                "type": "array",
                "uniqueItems": True,
            },
            "known_at": {"format": "date-time", "type": "string"},
            "known_at_basis": {"enum": ["record", "historical"], "type": "string"},
            "period_key": {"pattern": "^FY[0-9]{4}-P[0-9]{2}$", "type": "string"},
            "period_lock_id": {"format": "uuid", "type": "string"},
            "quarter": {"type": "boolean"},
        },
        "type": "object",
    },
}
NEW = {
    "ipe_logic": {
        "filters": [
            "one entity of entity_codes, book and period_key",
            "live packs propagate transaction (default) or functional "
            "currency to every child; retained reruns preserve that basis; "
            "locked packs retain their frozen currency",
            "section runs of revenue_waterfall, contract_balances, "
            "contract_balance_rollforward, revenue_from_opening_liability, "
            "revenue_from_prior_period_obligations, rpo, rpo_rollforward "
            "and disaggregation (T-RPT-01 rule 2)",
            "a locked period reads the disclosure_snapshot rows frozen at lock",
            "quarter true: the fiscal quarter-to-date column",
        ],
        "joins": [
            "report_run.child_report_run_ids holds the section runs",
            "report_run.disclosure_snapshot_ids holds the snapshots read",
            "disclosure_snapshot.period_lock_id = period_lock.id",
        ],
        "parameters": [
            "entity_codes",
            "book",
            "period_key",
            "period_lock_id",
            "quarter",
            "currency_view",
            "known_at",
            "known_at_basis",
        ],
        "source_tables": ["report_run", "disclosure_snapshot", "registry_version", "period_lock"],
        "version": 1,
    },
    "parameters_schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "book": {"enum": ["ASC606", "IFRS15", "LEGACY"], "type": "string"},
            "currency_view": {"enum": ["transaction", "functional"], "type": "string"},
            "entity_codes": {
                "items": {"minLength": 1, "type": "string"},
                "maxItems": 1,
                "minItems": 1,
                "type": "array",
                "uniqueItems": True,
            },
            "known_at": {"format": "date-time", "type": "string"},
            "known_at_basis": {"enum": ["record", "historical"], "type": "string"},
            "period_key": {"pattern": "^FY[0-9]{4}-P[0-9]{2}$", "type": "string"},
            "period_lock_id": {"format": "uuid", "type": "string"},
            "quarter": {"type": "boolean"},
        },
        "type": "object",
    },
}


def _set(value: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column in ("ipe_logic", "parameters_schema"):
        payload = json.dumps(value[column]).replace("'", "''")
        ops.execute(
            f"UPDATE erev.report_definition SET {column}='{payload}'::jsonb "  # noqa: S608
            "WHERE code='disclosure_pack' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
