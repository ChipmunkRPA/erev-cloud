"""Reporting-currency cost rollforwards and disclosure packs."""

import json
from erev_api.db import migration_ops as ops

revision = "0345"
down_revision = "0344"
branch_labels = None
depends_on = None

OLD = {
    "contract_cost_rollforward": {
        "ipe_logic": {
            "filters": [
                "entity code in entity_codes and within the caller's entity scope",
                "book_code = book",
                "period_key from from_period_key to to_period_key",
                "schedule_line.subject_type = 'contract_cost_asset'",
                "with period_lock_id, the values "
                "frozen at that lock "
                "(lock_snapshot kind "
                "COST_ROLLFORWARD)",
                "subledger_commit_visibility_v1 "
                "requires original PostgreSQL "
                "posting commit time at or before "
                "the historical cutoff; retained "
                "commit evidence is immutable; "
                "older bindings preserve their "
                "original seal-time "
                "interpretation",
                "historical_source_commit_v1 "
                "retains original event and "
                "contract-version transaction "
                "commits; new event/version "
                "extracts and BBR event sources "
                "use commit cutoffs; historical "
                "version populations exclude "
                "later commits before latest "
                "selection; bound inputs keep "
                "their original interpretation",
            ],
            "joins": [
                "cost_asset_version.contract_cost_asset_id = contract_cost_asset.id",
                "contract_cost_asset.contract_id = contract.id",
                "subledger_line.contract_cost_asset_id = contract_cost_asset.id",
                "schedule_line.subject_id = contract_cost_asset.id",
            ],
            "parameters": [
                "entity_codes",
                "book",
                "period_lock_id",
                "from_period_key",
                "to_period_key",
                "currency_view",
                "known_at",
                "known_at_basis",
            ],
            "source_tables": [
                "contract_cost_asset",
                "cost_asset_version",
                "schedule_line",
                "subledger_line",
                "contract",
                "period",
                "lock_snapshot",
                "subledger_posting_commit",
                "historical_source_commit",
            ],
            "version": 1,
        },
        "parameters_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "book": {"enum": ["ASC606", "IFRS15", "LEGACY"], "type": "string"},
                "currency_view": {
                    "enum": ["transaction", "functional", "reporting"],
                    "type": "string",
                },
                "entity_codes": {
                    "items": {"minLength": 1, "type": "string"},
                    "minItems": 1,
                    "type": "array",
                    "uniqueItems": True,
                },
                "from_period_key": {"pattern": "^FY[0-9]{4}-P[0-9]{2}$", "type": "string"},
                "known_at": {"format": "date-time", "type": "string"},
                "known_at_basis": {"enum": ["record", "historical"], "type": "string"},
                "period_lock_id": {"format": "uuid", "type": "string"},
                "to_period_key": {"pattern": "^FY[0-9]{4}-P[0-9]{2}$", "type": "string"},
            },
            "type": "object",
        },
    },
    "disclosure_pack": {
        "ipe_logic": {
            "filters": [
                "one entity of entity_codes, book and period_key",
                "live packs propagate transaction (default) "
                "or functional currency to every child; "
                "retained reruns preserve that basis; "
                "locked packs retain their frozen currency",
                "section runs of revenue_waterfall, "
                "contract_balances, "
                "contract_balance_rollforward, "
                "revenue_from_opening_liability, "
                "revenue_from_prior_period_obligations, "
                "rpo, rpo_rollforward and disaggregation "
                "(T-RPT-01 rule 2)",
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
            "source_tables": [
                "report_run",
                "disclosure_snapshot",
                "registry_version",
                "period_lock",
            ],
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
    },
}
NEW = {
    "contract_cost_rollforward": {
        "ipe_logic": {
            "filters": [
                "Reporting currency translates "
                "original functional cost "
                "movements monthly at average "
                "rates and endpoints at closing "
                "rates; FX and rounding are "
                "separate; source carrying "
                "tie-outs remain mandatory; "
                "original rate identities are "
                "retained for reruns and old "
                "saved reporting views preserve "
                "their prior shape",
                "entity code in entity_codes and within the caller's entity scope",
                "book_code = book",
                "period_key from from_period_key to to_period_key",
                "schedule_line.subject_type = 'contract_cost_asset'",
                "with period_lock_id, the values "
                "frozen at that lock "
                "(lock_snapshot kind "
                "COST_ROLLFORWARD)",
                "subledger_commit_visibility_v1 "
                "requires original PostgreSQL "
                "posting commit time at or before "
                "the historical cutoff; retained "
                "commit evidence is immutable; "
                "older bindings preserve their "
                "original seal-time "
                "interpretation",
                "historical_source_commit_v1 "
                "retains original event and "
                "contract-version transaction "
                "commits; new event/version "
                "extracts and BBR event sources "
                "use commit cutoffs; historical "
                "version populations exclude "
                "later commits before latest "
                "selection; bound inputs keep "
                "their original interpretation",
            ],
            "joins": [
                "cost_asset_version.contract_cost_asset_id = contract_cost_asset.id",
                "contract_cost_asset.contract_id = contract.id",
                "subledger_line.contract_cost_asset_id = contract_cost_asset.id",
                "schedule_line.subject_id = contract_cost_asset.id",
            ],
            "parameters": [
                "entity_codes",
                "book",
                "period_lock_id",
                "from_period_key",
                "to_period_key",
                "currency_view",
                "known_at",
                "known_at_basis",
            ],
            "source_tables": [
                "contract_cost_asset",
                "cost_asset_version",
                "schedule_line",
                "subledger_line",
                "contract",
                "period",
                "lock_snapshot",
                "tenant",
                "fx_rate",
                "fx_rate_set",
                "fx_rate_set_version",
                "subledger_posting_commit",
                "historical_source_commit",
            ],
            "version": 1,
        },
        "parameters_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "book": {"enum": ["ASC606", "IFRS15", "LEGACY"], "type": "string"},
                "currency_view": {
                    "enum": ["transaction", "functional", "reporting"],
                    "type": "string",
                },
                "entity_codes": {
                    "items": {"minLength": 1, "type": "string"},
                    "minItems": 1,
                    "type": "array",
                    "uniqueItems": True,
                },
                "from_period_key": {"pattern": "^FY[0-9]{4}-P[0-9]{2}$", "type": "string"},
                "known_at": {"format": "date-time", "type": "string"},
                "known_at_basis": {"enum": ["record", "historical"], "type": "string"},
                "period_lock_id": {"format": "uuid", "type": "string"},
                "to_period_key": {"pattern": "^FY[0-9]{4}-P[0-9]{2}$", "type": "string"},
            },
            "type": "object",
        },
    },
    "disclosure_pack": {
        "ipe_logic": {
            "filters": [
                "one entity of entity_codes, book and period_key",
                "live packs propagate transaction "
                "(default), functional or reporting "
                "currency to every child; retained reruns "
                "preserve that basis; locked packs retain "
                "their frozen currency",
                "section runs of revenue_waterfall, "
                "contract_balances, "
                "contract_balance_rollforward, "
                "revenue_from_opening_liability, "
                "revenue_from_prior_period_obligations, "
                "rpo, rpo_rollforward and disaggregation "
                "(T-RPT-01 rule 2)",
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
            "source_tables": [
                "report_run",
                "disclosure_snapshot",
                "registry_version",
                "period_lock",
            ],
            "version": 1,
        },
        "parameters_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "additionalProperties": False,
            "properties": {
                "book": {"enum": ["ASC606", "IFRS15", "LEGACY"], "type": "string"},
                "currency_view": {
                    "enum": ["transaction", "functional", "reporting"],
                    "type": "string",
                },
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
    },
}


def _set(definitions: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, value in definitions.items():
        for column in ("ipe_logic", "parameters_schema"):
            payload = json.dumps(value[column]).replace("'", "''")
            ops.execute(
                f"UPDATE erev.report_definition SET {column}='{payload}'::jsonb "  # noqa: S608
                f"WHERE code='{code}' AND version=1"
            )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
