"""Retain allocation segment lineage for same-source reconstruction."""

import json

from erev_api.db import migration_ops as ops

revision = "0316"
down_revision = "0315"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract_version",'
    ' "contract", "product", "ssp_book_version", "ssp_entry", "ssp_range", '
    '"historical_source_commit"], "joins": ["obligation_version.contract_version_id = '
    'contract_version.id", "obligation_version.contract_id = contract.id", '
    '"obligation_version.product_id = product.id", "obligation_version.ssp_book_version_id = '
    'ssp_book_version.id", "obligation_version.ssp_entry_id = ssp_entry.id", '
    '"obligation_version.ssp_range_id = ssp_range.id"], "filters": ["entity code in '
    'entity_codes and within the caller\'s entity scope", "book_code = book", "obligation '
    'versions of an allocation event effective from from_date to to_date", '
    '"obligation_version.ssp_book_version_id = ssp_book_version_id when given", '
    '"historical_source_commit_v1 retains original event and contract-version transaction '
    "commits; new event/version extracts and BBR event sources use commit cutoffs; historical"
    " version populations exclude later commits before latest selection; bound inputs keep "
    'their original interpretation"], "parameters": ["entity_codes", "book", '
    '"ssp_book_version_id", "from_date", "to_date", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract_version",'
    ' "contract", "product", "ssp_book_version", "ssp_entry", "ssp_range", '
    '"historical_source_commit"], "joins": ["obligation_version.contract_version_id = '
    'contract_version.id", "obligation_version.contract_id = contract.id", '
    '"obligation_version.product_id = product.id", "obligation_version.ssp_book_version_id = '
    'ssp_book_version.id", "obligation_version.ssp_entry_id = ssp_entry.id", '
    '"obligation_version.ssp_range_id = ssp_range.id"], "filters": ["same-source runs retain '
    "allocation segment versions, cause dates and chain numbers; rebuild lineage amounts, "
    'range checks and totals without live reads", "entity code in entity_codes and within the'
    ' caller\'s entity scope", "book_code = book", "obligation versions of an allocation event'
    ' effective from from_date to to_date", "obligation_version.ssp_book_version_id = '
    'ssp_book_version_id when given", "historical_source_commit_v1 retains original event and'
    " contract-version transaction commits; new event/version extracts and BBR event sources "
    "use commit cutoffs; historical version populations exclude later commits before latest "
    'selection; bound inputs keep their original interpretation"], "parameters": '
    '["entity_codes", "book", "ssp_book_version_id", "from_date", "to_date", "known_at", '
    '"known_at_basis"]}}'
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
            + "'::jsonb WHERE code='allocations_by_ssp_version' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
