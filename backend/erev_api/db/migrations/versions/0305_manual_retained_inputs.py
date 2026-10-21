"""Describe retained adjustment, approval display and rate inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0305"
down_revision = "0304"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["manual_adjustment", "contract", '
    '"obligation", "legal_entity", "period", "approval_request", "approval_decision", '
    '"file_attachment", "lock_snapshot", "tenant", "fx_rate", "fx_rate_set", '
    '"fx_rate_set_version"], "joins": ["manual_adjustment.contract_id = contract.id", '
    '"manual_adjustment.obligation_id = obligation.id", "manual_adjustment.entity_id = '
    'legal_entity.id", "manual_adjustment.period_id = period.id", '
    '"manual_adjustment.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id"], "filters": ["reporting '
    "view preserves original functional amounts and adds reporting amounts at each posting "
    "period's approved average rate; total impact includes all statuses while the posted footer"
    ' includes only POSTED adjustments; transaction view is unavailable", "entity code in '
    'entity_codes and within the caller\'s entity scope", "book_code = book", "period_key from '
    'from_period_key to to_period_key", "status and kind when given", "with period_lock_id, the'
    ' values frozen at that lock (lock_snapshot kind MANUAL_ADJUSTMENT_REGISTER)"], '
    '"parameters": ["entity_codes", "book", "from_period_key", "to_period_key", "status", '
    '"kind", "period_lock_id", "currency_view", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["manual_adjustment", "contract", '
    '"obligation", "legal_entity", "period", "approval_request", "approval_decision", '
    '"file_attachment", "lock_snapshot", "tenant", "fx_rate", "fx_rate_set", '
    '"fx_rate_set_version"], "joins": ["manual_adjustment.contract_id = contract.id", '
    '"manual_adjustment.obligation_id = obligation.id", "manual_adjustment.entity_id = '
    'legal_entity.id", "manual_adjustment.period_id = period.id", '
    '"manual_adjustment.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id"], "filters": ["reporting '
    "view preserves original functional amounts and adds reporting amounts at each posting "
    "period's approved average rate; total impact includes all statuses while the posted footer"
    ' includes only POSTED adjustments; transaction view is unavailable", "same-source runs '
    "retain adjustment inputs, approval/actor displays, attachment counts and per-period rate "
    'evidence; reruns rebuild rows and totals without live source reads", "entity code in '
    'entity_codes and within the caller\'s entity scope", "book_code = book", "period_key from '
    'from_period_key to to_period_key", "status and kind when given", "with period_lock_id, the'
    ' values frozen at that lock (lock_snapshot kind MANUAL_ADJUSTMENT_REGISTER)"], '
    '"parameters": ["entity_codes", "book", "from_period_key", "to_period_key", "status", '
    '"kind", "period_lock_id", "currency_view", "known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='manual_adjustment_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
