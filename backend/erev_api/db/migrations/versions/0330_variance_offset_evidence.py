"""Retain offsetting close-variance contributions at zero net change."""

import json

from erev_api.db import migration_ops as ops

revision = "0330"
down_revision = "0329"
branch_labels = None
depends_on = None

OLD_IPE = {
    "version": 1,
    "source_tables": ["period_lock", "lock_snapshot", "disclosure_snapshot", "contract"],
    "joins": [
        "lock_snapshot.period_lock_id = period_lock.id",
        "disclosure_snapshot.period_lock_id = period_lock.id",
    ],
    "filters": [
        "POL-199 excludes original realized royalty awaiting recognition, retaining "
        "fixed minimum guarantees; POL-200 then applies to remaining eligible targeted "
        "VC; separate exemption rows and translated amounts reconcile to the combined "
        "cap; new retained RPO runs preserve this interpretation and old bindings keep "
        "their prior cap",
        "two locks of one entity, book and period; the later recorded after the earlier",
        "locks of an entity in entity_codes",
        "changes attributed to drivers",
    ],
    "parameters": [
        "entity_codes",
        "from_period_lock_id",
        "to_period_lock_id",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
}

NEW_IPE = {
    "version": 1,
    "source_tables": ["period_lock", "lock_snapshot", "disclosure_snapshot", "contract"],
    "joins": [
        "lock_snapshot.period_lock_id = period_lock.id",
        "disclosure_snapshot.period_lock_id = period_lock.id",
    ],
    "filters": [
        "POL-199 excludes original realized royalty awaiting recognition, retaining "
        "fixed minimum guarantees; POL-200 then applies to remaining eligible targeted "
        "VC; separate exemption rows and translated amounts reconcile to the combined "
        "cap; new retained RPO runs preserve this interpretation and old bindings keep "
        "their prior cap",
        "two locks of one entity, book and period; the later recorded after the earlier",
        "locks of an entity in entity_codes",
        "changes attributed to drivers",
        "Net-zero contract and driver rows remain visible when nonzero replay effects "
        "offset; contributor details retain signed effect amounts and event keys; "
        "unchanged replays remain empty; older bound runs preserve their original row "
        "population",
    ],
    "parameters": [
        "entity_codes",
        "from_period_lock_id",
        "to_period_lock_id",
        "currency_view",
        "known_at",
        "known_at_basis",
    ],
}


def _set(value: dict) -> None:
    payload = json.dumps(value).replace("'", "''")
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
        + payload
        + "'::jsonb WHERE code='variance_between_closes' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW_IPE)


def downgrade() -> None:
    _set(OLD_IPE)
