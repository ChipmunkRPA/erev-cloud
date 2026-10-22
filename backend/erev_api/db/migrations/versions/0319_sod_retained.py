"""Retain scoped SoD conflict and exception inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0319"
down_revision = "0318"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["sod_rule", "role_assignment", '
    '"role_permission", "tenant_membership", "app_user", "sod_exception", '
    '"approval_delegation"], "joins": ["role_assignment.membership_id = '
    'tenant_membership.id", "role_permission.role_id = role_assignment.role_id", '
    '"tenant_membership.user_id = app_user.id", "sod_exception.membership_id = '
    'tenant_membership.id", "approval_delegation.delegate_membership_id = '
    'tenant_membership.id", "approval_delegation.delegator_membership_id = '
    'tenant_membership.id"], "filters": ["memberships holding permissions of both functions '
    'of a published sod_rule at as_of", "exception status at as_of", "assignments whose '
    'entity scope includes an entity of entity_codes", "approval delegations standing at '
    "as_of and given by then, for the permissions their delegator holds at as_of through the "
    'assignments in scope"], "parameters": ["entity_codes", "as_of", "known_at", '
    '"known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["sod_rule", "role_assignment", '
    '"role_permission", "tenant_membership", "app_user", "sod_exception", '
    '"approval_delegation"], "joins": ["role_assignment.membership_id = '
    'tenant_membership.id", "role_permission.role_id = role_assignment.role_id", '
    '"tenant_membership.user_id = app_user.id", "sod_exception.membership_id = '
    'tenant_membership.id", "approval_delegation.delegate_membership_id = '
    'tenant_membership.id", "approval_delegation.delegator_membership_id = '
    'tenant_membership.id"], "filters": ["same-source runs retain scoped rule functions, held'
    " permissions, delegations and exception inputs; recalculate conflicts and coverage "
    'without live access reads", "memberships holding permissions of both functions of a '
    'published sod_rule at as_of", "exception status at as_of", "assignments whose entity '
    'scope includes an entity of entity_codes", "approval delegations standing at as_of and '
    "given by then, for the permissions their delegator holds at as_of through the "
    'assignments in scope"], "parameters": ["entity_codes", "as_of", "known_at", '
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
            + "'::jsonb WHERE code='sod_conflict_report' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
