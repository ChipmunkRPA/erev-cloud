"""Document estimate reporting equivalents and their effective-period rate basis."""

import json

from erev_api.db import migration_ops as ops

revision = "0308"
down_revision = "0307"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["estimate_version", "estimate", '
    '"contract", "obligation", "approval_request", "approval_decision", "file_attachment", '
    '"historical_source_commit"], "joins": ["estimate_version.estimate_id = estimate.id", '
    '"estimate.contract_id = contract.id", "estimate.obligation_id = obligation.id", '
    '"estimate_version.supersedes_version_id = estimate_version.id (predecessor)", '
    '"estimate_version.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id"], "filters": ["entity code'
    ' in entity_codes and within the caller\'s entity scope", "approved versions with '
    'effective_date from from_date to to_date inclusive", "estimate kind in estimate_kind '
    'when given", "historical_source_commit_v1 retains original event and contract-version '
    "transaction commits; new event/version extracts and BBR event sources use commit "
    "cutoffs; historical version populations exclude later commits before latest selection; "
    'bound inputs keep their original interpretation"], "parameters": ["entity_codes", '
    '"book", "from_date", "to_date", "estimate_kind", "currency_view", "known_at", '
    '"known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["estimate_version", "estimate", '
    '"contract", "obligation", "approval_request", "approval_decision", "file_attachment", '
    '"legal_entity", "tenant", "period", "fx_rate", "fx_rate_set", "fx_rate_set_version", '
    '"historical_source_commit"], "joins": ["estimate_version.estimate_id = estimate.id", '
    '"estimate.contract_id = contract.id", "estimate.obligation_id = obligation.id", '
    '"estimate_version.supersedes_version_id = estimate_version.id (predecessor)", '
    '"estimate_version.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id"], "filters": ["reporting '
    "preserves original measures and adds analytical monetary equivalents at the estimate "
    "effective-period average; before/after use the same rate, ratios stay dimensionless, "
    'missing effects stay empty; these are not posted FX amounts", "entity code in '
    'entity_codes and within the caller\'s entity scope", "approved versions with '
    'effective_date from from_date to to_date inclusive", "estimate kind in estimate_kind '
    'when given", "historical_source_commit_v1 retains original event and contract-version '
    "transaction commits; new event/version extracts and BBR event sources use commit "
    "cutoffs; historical version populations exclude later commits before latest selection; "
    'bound inputs keep their original interpretation"], "parameters": ["entity_codes", '
    '"book", "from_date", "to_date", "estimate_kind", "currency_view", "known_at", '
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
            + "'::jsonb WHERE code='estimate_change_listing' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
