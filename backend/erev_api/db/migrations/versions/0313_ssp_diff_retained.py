"""Retain SSP comparison versions and entry/range inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0313"
down_revision = "0312"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["ssp_entry", "ssp_range", '
    '"ssp_book_version", "product"], "joins": ["ssp_entry.ssp_book_version_id = '
    'ssp_book_version.id", "ssp_entry.product_id = product.id", "ssp_range of each ssp_entry '
    '(T-REF-31)"], "filters": ["entry keys present in either version", "against_version_id: a'
    ' version of the same book, by default the prior approved version", "only_changes true: '
    'added, removed and changed entries only"], "parameters": ["entity_codes", '
    '"ssp_book_version_id", "against_version_id", "only_changes", "known_at", '
    '"known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["ssp_entry", "ssp_range", '
    '"ssp_book_version", "product"], "joins": ["ssp_entry.ssp_book_version_id = '
    'ssp_book_version.id", "ssp_entry.product_id = product.id", "ssp_range of each ssp_entry '
    '(T-REF-31)"], "filters": ["same-source runs retain selected comparison version IDs and '
    'complete entry/range inputs; recalculate changes and ratios without live reads", "entry '
    'keys present in either version", "against_version_id: a version of the same book, by '
    'default the prior approved version", "only_changes true: added, removed and changed '
    'entries only"], "parameters": ["entity_codes", "ssp_book_version_id", '
    '"against_version_id", "only_changes", "known_at", "known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column, value in json.loads(encoded).items():
        payload = json.dumps(value).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET "  # noqa: S608 — frozen metadata
            + column
            + "='"
            + payload
            + "'::jsonb WHERE code='ssp_version_diff' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
