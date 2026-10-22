"""Retain user-access membership and grant inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0318"
down_revision = "0317"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["tenant_membership", "app_user", '
    '"role_assignment", "role", "sod_exception", "user_mfa_factor", "approval_request", '
    '"audit_event"], "joins": ["role_assignment.membership_id = tenant_membership.id", '
    '"role_assignment.role_id = role.id", "tenant_membership.user_id = app_user.id", '
    '"role_assignment.sod_exception_id = sod_exception.id", '
    '"role_assignment.approval_request_id = approval_request.id", "audit_event.object_id = '
    'tenant_membership.id (action tenant_membership.invite)"], "filters": ["role assignments '
    'active at as_of", "memberships removed at as_of are left out: REMOVED with removed_at by'
    " then, or as_of inside a removal that a later invitation ended (the invitation's audit "
    'event states the removal\'s instant)", "include_removed: removed memberships too", '
    '"assignments whose entity scope includes an entity of entity_codes"], "parameters": '
    '["entity_codes", "as_of", "include_removed", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["tenant_membership", "app_user", '
    '"role_assignment", "role", "sod_exception", "user_mfa_factor", "approval_request", '
    '"audit_event"], "joins": ["role_assignment.membership_id = tenant_membership.id", '
    '"role_assignment.role_id = role.id", "tenant_membership.user_id = app_user.id", '
    '"role_assignment.sod_exception_id = sod_exception.id", '
    '"role_assignment.approval_request_id = approval_request.id", "audit_event.object_id = '
    'tenant_membership.id (action tenant_membership.invite)"], "filters": ["same-source runs '
    "retain member/grant inputs, MFA state and original names; rebuild rows and counts "
    'without live reads", "role assignments active at as_of", "memberships removed at as_of '
    "are left out: REMOVED with removed_at by then, or as_of inside a removal that a later "
    "invitation ended (the invitation's audit event states the removal's instant)\", "
    '"include_removed: removed memberships too", "assignments whose entity scope includes an '
    'entity of entity_codes"], "parameters": ["entity_codes", "as_of", "include_removed", '
    '"known_at", "known_at_basis"]}}'
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
            + "'::jsonb WHERE code='user_access_listing' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
