"""Principals and request context (dev-guide §5.3; BUILD_SPEC FND-11)."""

from __future__ import annotations

from uuid import UUID

from erev_api.auth.principal import Principal, system_principal
from erev_api.enums import PrincipalKind

TENANT = UUID("00000000-0000-4000-8000-0000000000a1")
E1 = UUID("00000000-0000-4000-8000-0000000000e1")
E2 = UUID("00000000-0000-4000-8000-0000000000e2")
USER = UUID("00000000-0000-4000-8000-0000000000b1")


def test_system_principal_fields() -> None:
    principal = system_principal(TENANT)

    assert principal.kind is PrincipalKind.SYSTEM
    assert principal.id is None
    assert principal.tenant_id == TENANT
    assert principal.permissions == frozenset()
    assert dict(principal.permission_scopes) == {}
    assert principal.auth_method == "system"
    assert principal.on_behalf_of_id is None
    assert principal.db_context.entity_scope == "*"
    assert principal.db_context.tenant_id == TENANT
    assert principal.db_context.user_id is None

    on_behalf = system_principal(TENANT, on_behalf_of_id=USER)
    assert on_behalf.on_behalf_of_id == USER
    assert on_behalf.db_context.user_id is None


def test_db_context_entity_scope_sorted() -> None:
    principal = Principal(
        kind=PrincipalKind.USER,
        id=USER,
        tenant_id=TENANT,
        membership_id=None,
        display_name="Preparer",
        roles=("REVENUE_ACCOUNTANT",),
        permissions=frozenset({"contract.read"}),
        permission_scopes={"contract.read": frozenset({E1, E2})},
        entity_scope=(E2, E1),
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )

    ctx = principal.db_context
    assert ctx.entity_scope == (E1, E2)
    assert ctx.user_id == USER
    assert ctx.scope_setting() == f"{E1},{E2}"
