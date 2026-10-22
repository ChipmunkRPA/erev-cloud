"""Retain SSP override version and approval inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0315"
down_revision = "0314"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract", '
    '"product", "ssp_book_version", "approval_request", "approval_decision", '
    '"historical_source_commit"], "joins": '
    '["obligation_version.ssp_override_approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"obligation_version.ssp_book_version_id = ssp_book_version.id", '
    '"obligation_version.contract_id = contract.id", "obligation_version.product_id = '
    'product.id"], "filters": ["entity code in entity_codes and within the caller\'s entity '
    'scope", "obligation_version.ssp_override_approval_request_id is not null", "approval '
    'decided from from_date to to_date inclusive", "historical_source_commit_v1 retains '
    "original event and contract-version transaction commits; new event/version extracts and "
    "BBR event sources use commit cutoffs; historical version populations exclude later "
    'commits before latest selection; bound inputs keep their original interpretation"], '
    '"parameters": ["entity_codes", "from_date", "to_date", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["obligation_version", "contract", '
    '"product", "ssp_book_version", "approval_request", "approval_decision", '
    '"historical_source_commit"], "joins": '
    '["obligation_version.ssp_override_approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"obligation_version.ssp_book_version_id = ssp_book_version.id", '
    '"obligation_version.contract_id = contract.id", "obligation_version.product_id = '
    'product.id"], "filters": ["same-source runs retain override/version labels, approval '
    'requests and actor names; rebuild rows and approval-date selection without live reads", '
    '"entity code in entity_codes and within the caller\'s entity scope", '
    '"obligation_version.ssp_override_approval_request_id is not null", "approval decided '
    'from from_date to to_date inclusive", "historical_source_commit_v1 retains original '
    "event and contract-version transaction commits; new event/version extracts and BBR event"
    " sources use commit cutoffs; historical version populations exclude later commits before"
    ' latest selection; bound inputs keep their original interpretation"], "parameters": '
    '["entity_codes", "from_date", "to_date", "known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='ssp_override_listing' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
