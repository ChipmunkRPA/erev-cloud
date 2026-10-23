"""Add opt-in event-level close variance replay."""

import json

from erev_api.db import migration_ops as ops

revision = "0331"
down_revision = "0330"
branch_labels = None
depends_on = None

OLD_METADATA = {
    "ipe_logic": {
        "version": 1,
        "source_tables": ["period_lock", "lock_snapshot", "disclosure_snapshot", "contract"],
        "joins": [
            "lock_snapshot.period_lock_id = period_lock.id",
            "disclosure_snapshot.period_lock_id = period_lock.id",
        ],
        "filters": [
            "POL-199 excludes original realized royalty awaiting recognition, "
            "retaining fixed minimum guarantees; POL-200 then applies to "
            "remaining eligible targeted VC; separate exemption rows and "
            "translated amounts reconcile to the combined cap; new retained "
            "RPO runs preserve this interpretation and old bindings keep their "
            "prior cap",
            "two locks of one entity, book and period; the later recorded after the earlier",
            "locks of an entity in entity_codes",
            "changes attributed to drivers",
            "Net-zero contract and driver rows remain visible when nonzero "
            "replay effects offset; contributor details retain signed effect "
            "amounts and event keys; unchanged replays remain empty; older "
            "bound runs preserve their original row population",
        ],
        "parameters": [
            "entity_codes",
            "from_period_lock_id",
            "to_period_lock_id",
            "currency_view",
            "known_at",
            "known_at_basis",
        ],
    },
    "parameters_schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entity_codes": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
            "from_period_lock_id": {"type": "string", "format": "uuid"},
            "to_period_lock_id": {"type": "string", "format": "uuid"},
            "currency_view": {"type": "string", "enum": ["transaction", "functional", "reporting"]},
            "known_at": {"type": "string", "format": "date-time"},
            "known_at_basis": {"type": "string", "enum": ["record", "historical"]},
        },
    },
}

NEW_METADATA = {
    "ipe_logic": {
        "version": 1,
        "source_tables": ["period_lock", "lock_snapshot", "disclosure_snapshot", "contract"],
        "joins": [
            "lock_snapshot.period_lock_id = period_lock.id",
            "disclosure_snapshot.period_lock_id = period_lock.id",
        ],
        "filters": [
            "POL-199 excludes original realized royalty awaiting recognition, "
            "retaining fixed minimum guarantees; POL-200 then applies to "
            "remaining eligible targeted VC; separate exemption rows and "
            "translated amounts reconcile to the combined cap; new retained "
            "RPO runs preserve this interpretation and old bindings keep their "
            "prior cap",
            "two locks of one entity, book and period; the later recorded after the earlier",
            "locks of an entity in entity_codes",
            "changes attributed to drivers",
            "attribution_detail=event evaluates each business event in ENG-06 "
            "order and retains signed intermediate differences; driver totals "
            "and frozen endpoints reconcile exactly; structural "
            "membership/reference/population phases remain explicit grouped "
            "effects; default driver detail and older bound runs retain "
            "grouped replay",
            "Net-zero contract and driver rows remain visible when nonzero "
            "replay effects offset; contributor details retain signed effect "
            "amounts and event keys; unchanged replays remain empty; older "
            "bound runs preserve their original row population",
        ],
        "parameters": [
            "entity_codes",
            "from_period_lock_id",
            "to_period_lock_id",
            "currency_view",
            "attribution_detail",
            "known_at",
            "known_at_basis",
        ],
    },
    "parameters_schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entity_codes": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
            "from_period_lock_id": {"type": "string", "format": "uuid"},
            "to_period_lock_id": {"type": "string", "format": "uuid"},
            "currency_view": {"type": "string", "enum": ["transaction", "functional", "reporting"]},
            "attribution_detail": {
                "type": "string",
                "enum": ["driver", "event"],
                "default": "driver",
            },
            "known_at": {"type": "string", "format": "date-time"},
            "known_at_basis": {"type": "string", "enum": ["record", "historical"]},
        },
    },
}


def _set(metadata: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column, value in metadata.items():
        payload = json.dumps(value).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET "  # noqa: S608 — frozen metadata
            + column
            + "='"
            + payload
            + "'::jsonb WHERE code='variance_between_closes' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW_METADATA)


def downgrade() -> None:
    _set(OLD_METADATA)
