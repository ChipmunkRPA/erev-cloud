"""Grants, permission guards and entity scope (dev-guide §5.3 DG-KRN-AUTH-03 to DG-KRN-AUTH-05,
§5.4 ``effective_grants``, ``api_client_grants``; 04 T-PLT-09, T-PLT-10, T-PLT-12, T-PLT-15;
BUILD_SPEC PLF-4, PLF-25)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Annotated, Any
from uuid import UUID

import pytest
from erev_api.auth.dependencies import require, require_for_entity
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES, api_client_grants, effective_grants
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import Depends
from fastapi.routing import APIRoute
from sqlalchemy import select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.http import call
from support.principals import cookie_headers, cookie_of, member, select_tenant, sign_in
from support.rows import insert_api_client, insert_role_assignment, revoke_role_assignments

E1 = UUID("0191e0a0-0000-7000-8000-00000000e001")
E2 = UUID("0191e0a0-0000-7000-8000-00000000e002")
MANAGE_ROLES = "/api/v1/__probe__/role-manage"
RUN_REPORTS = "/api/v1/__probe__/report-run"


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def test_effective_grants_union(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    result = tenant_factory(keyring=keyring, clock=clock)
    tenant_id, membership_id = tenant_id_of(result), result.admin_membership_id
    with tenant_session(_all_entities(tenant_id)) as session:
        # Start without roles: revoke the provisioned tenant_admin grant (04 §14.3 item 2).
        revoke_role_assignments(
            session, tenant_id=tenant_id, membership_id=membership_id, at=clock.now()
        )
        for code in ("viewer", "ssp_analyst"):
            insert_role_assignment(
                session, tenant_id=tenant_id, membership_id=membership_id, role_code=code
            )
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            role_code="controller",
            revoked_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            role_code="auditor",
            valid_to=datetime(2026, 6, 30, tzinfo=UTC),
        )
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        grants = effective_grants(session, membership_id, at=clock.now())
        before = effective_grants(session, membership_id, at=datetime(2025, 12, 31, tzinfo=UTC))

    union = DEFAULT_ROLES["viewer"] | DEFAULT_ROLES["ssp_analyst"]
    # PRD §5.6: viewer holds 6 codes and ssp_analyst 5, four of them shared (SPEC-Q-139).
    assert len(union) == 7
    assert grants.permissions == union
    assert grants.roles == ("ssp_analyst", "viewer")
    assert grants.permission_scopes["ssp.create"] == "*"
    assert dict(grants.permission_scopes) == {code: "*" for code in union}
    assert grants.entity_scope == "*"
    # The revoked controller and the lapsed auditor contribute nothing.
    assert not {"period.lock", "evidence.export"} & grants.permissions
    # On 2025-12-31 no assignment is valid yet.
    assert (before.roles, before.permissions, dict(before.permission_scopes)) == (
        (),
        frozenset(),
        {},
    )
    assert before.entity_scope == ()


def test_krn_auth_03_require_permission(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    app = create_app(app_settings, clock=clock)

    @app.get(MANAGE_ROLES)
    def manage_roles(
        ctx: Annotated[RequestContext, Depends(require("role.manage"))],
    ) -> dict[str, Any]:
        return {"roles": list(ctx.principal.roles)}

    @app.get(RUN_REPORTS)
    def run_reports(
        ctx: Annotated[RequestContext, Depends(require("report.run"))],
    ) -> dict[str, Any]:
        return {"roles": list(ctx.principal.roles), "entity_scope": ctx.principal.entity_scope}

    viewer = member(keyring, clock)
    with tenant_session(_all_entities(viewer.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=viewer.tenant_id,
            membership_id=viewer.membership_id,
            role_code="viewer",
        )
    signed = sign_in(app, viewer.email)
    headers = cookie_headers(cookie_of(select_tenant(app, signed, viewer.tenant_id)), key=False)

    denied = call(app, "GET", MANAGE_ROLES, headers=headers)
    assert denied.status_code == 403
    assert denied.json()["type"] == "https://erev.dev/problems/forbidden"
    allowed = call(app, "GET", RUN_REPORTS, headers=headers)
    assert allowed.status_code == 200
    assert allowed.json() == {"roles": ["viewer"], "entity_scope": "*"}

    with tenant_session(_all_entities(viewer.tenant_id)) as session:
        events = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.object_type,
                audit_event.c.actor_id,
                audit_event.c.actor_roles,
                audit_event.c.detail,
            ).where(audit_event.c.outcome == "DENIED")
        ).all()
    assert [tuple(event) for event in events] == [
        (
            "role.manage",
            "route",
            viewer.user_id,
            ["viewer"],
            {"method": "GET", "path": MANAGE_ROLES, "permission": "role.manage"},
        )
    ]

    routes = {route.path: route for route in app.router.routes if isinstance(route, APIRoute)}
    assert routes[MANAGE_ROLES].openapi_extra == {"x-erev-permission": "role.manage"}
    assert app.openapi()["paths"][MANAGE_ROLES]["get"]["x-erev-permission"] == "role.manage"
    with pytest.raises(KeyError):
        require("role.explode")


def _context(scopes: dict[str, Any]) -> RequestContext:
    principal = Principal(
        kind=PrincipalKind.USER,
        id=UUID("0191e0a0-0000-7000-8000-00000000a001"),
        tenant_id=UUID("0191e0a0-0000-7000-8000-00000000a002"),
        membership_id=UUID("0191e0a0-0000-7000-8000-00000000a003"),
        display_name="Probe user",
        roles=("viewer",),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope=(E1,),
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    return RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-krn-auth-04",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=frozen_clock().now(),
        format_locale="en-US",
    )


def test_krn_auth_04_require_for_entity() -> None:
    ctx = _context({"contract.read": frozenset({E1}), "report.run": "*"})
    with pytest.raises(Problem) as excinfo:
        require_for_entity(ctx, "contract.read", E2)
    assert (excinfo.value.slug, excinfo.value.status) == ("not-found", 404)
    require_for_entity(ctx, "contract.read", None)
    require_for_entity(ctx, "contract.read", E1)
    require_for_entity(ctx, "report.run", E2)
    with pytest.raises(Problem) as missing:
        require_for_entity(ctx, "ssp.read", None)
    assert missing.value.slug == "not-found"


def test_dg_krn_perm_04_api_client_grants(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    now = clock.now()
    with tenant_session(_all_entities(tenant_id)) as session:
        client_id = insert_api_client(
            session,
            tenant_id=tenant_id,
            scopes=["audit.read", "contract.read"],
            expires_at=now + timedelta(days=1),
        )
        expired = insert_api_client(session, tenant_id=tenant_id, expires_at=now)
        revoked = insert_api_client(
            session, tenant_id=tenant_id, status="REVOKED", expires_at=now + timedelta(days=1)
        )
        # A token carrying an approval code, or a code the client lacks, holds neither.
        grants = api_client_grants(
            session,
            client_id,
            token_scopes=["contract.read", "contract.approve", "report.run"],
            at=now,
        )
        refused = [
            api_client_grants(session, other, token_scopes=["contract.read"], at=now)
            for other in (expired, revoked)
        ]
    assert grants.permissions == frozenset({"contract.read"})
    assert dict(grants.permission_scopes) == {"contract.read": "*"}
    assert (grants.roles, grants.entity_scope) == ((), "*")
    assert [(other.permissions, other.entity_scope) for other in refused] == [
        (frozenset(), ()),
        (frozenset(), ()),
    ]
