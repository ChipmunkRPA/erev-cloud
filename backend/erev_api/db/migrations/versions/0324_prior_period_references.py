"""Retain prior-period revenue reference population."""

import json

from erev_api.db import migration_ops as ops

revision = "0324"
down_revision = "0323"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["schedule_line", "obligation_version", '
    '"contract", "product", "legal_entity", "period", "lock_snapshot", '
    '"subledger_posting_commit", "historical_source_commit"], "joins": '
    '["schedule_line.subject_id = obligation_version.obligation_id and '
    'schedule_line.contract_version_id = obligation_version.contract_version_id", '
    '"schedule_line.contract_id = contract.id", "obligation_version.product_id = product.id",'
    ' "schedule_line.entity_id = legal_entity.id", "schedule_line.period_id = period.id"], '
    '"filters": ["entity code in entity_codes and within the caller\'s entity scope", '
    '"book_code = book", "period_key from from_period_key to to_period_key", "catch-up '
    'schedule lines of obligations satisfied before from_period_key", "cause: transaction '
    'price change, estimate change or modification (POL-204)", "with period_lock_id, the '
    'values frozen at that lock (lock_snapshot kind PRIOR_PERIOD_POB_REVENUE)", '
    '"subledger_commit_visibility_v1 requires original PostgreSQL posting commit time at or '
    "before the historical cutoff; retained commit evidence is immutable; older bindings "
    'preserve their original seal-time interpretation", "historical_source_commit_v1 retains '
    "original event and contract-version transaction commits; new event/version extracts and "
    "BBR event sources use commit cutoffs; historical version populations exclude later "
    'commits before latest selection; bound inputs keep their original interpretation"], '
    '"parameters": ["entity_codes", "book", "period_lock_id", "from_period_key", '
    '"to_period_key", "currency_view", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["schedule_line", "obligation_version", '
    '"contract", "product", "legal_entity", "period", "lock_snapshot", '
    '"subledger_posting_commit", "historical_source_commit"], "joins": '
    '["schedule_line.subject_id = obligation_version.obligation_id and '
    'schedule_line.contract_version_id = obligation_version.contract_version_id", '
    '"schedule_line.contract_id = contract.id", "obligation_version.product_id = product.id",'
    ' "schedule_line.entity_id = legal_entity.id", "schedule_line.period_id = period.id"], '
    '"filters": ["same-source runs retain the original entity/period revenue-line version '
    "references; version selection and trace attribution do not rediscover current ledger "
    'references", "entity code in entity_codes and within the caller\'s entity scope", '
    '"book_code = book", "period_key from from_period_key to to_period_key", "catch-up '
    'schedule lines of obligations satisfied before from_period_key", "cause: transaction '
    'price change, estimate change or modification (POL-204)", "with period_lock_id, the '
    'values frozen at that lock (lock_snapshot kind PRIOR_PERIOD_POB_REVENUE)", '
    '"subledger_commit_visibility_v1 requires original PostgreSQL posting commit time at or '
    "before the historical cutoff; retained commit evidence is immutable; older bindings "
    'preserve their original seal-time interpretation", "historical_source_commit_v1 retains '
    "original event and contract-version transaction commits; new event/version extracts and "
    "BBR event sources use commit cutoffs; historical version populations exclude later "
    'commits before latest selection; bound inputs keep their original interpretation"], '
    '"parameters": ["entity_codes", "book", "period_lock_id", "from_period_key", '
    '"to_period_key", "currency_view", "known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='revenue_from_prior_period_obligations' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
