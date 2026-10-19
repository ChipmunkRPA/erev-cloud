"""Scenario catalogue authorization, filtering and tenant isolation."""

from uuid import uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import (
    DbContext,
    name_platform_tenant,
    platform_session,
    set_tenant_context,
    tenant_session,
)
from erev_api.db.tables import scenario, tenant, tenant_snapshot
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert
from support.db import TestDatabase
from support.http import call
from support.principals import cookie_headers, enrolled, member, sign_in, workspace
from support.rows import insert_active_membership, insert_role_assignment, tenant_snapshot_values


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_scenario_catalogue(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    source = member(keyring, clock)
    denied = enrolled(app, clock, source)
    response = call(
        app, "GET", "/api/v1/scenarios", headers=cookie_headers(denied.token, key=False)
    )
    assert response.status_code == 403, response.text
    with tenant_session(
        DbContext(tenant_id=source.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        insert_role_assignment(
            session,
            tenant_id=source.tenant_id,
            membership_id=source.membership_id,
            role_code="controller",
        )
    allowed = workspace(app, source, sign_in(app, source.email), denied.secret)
    other = member(keyring, clock)
    for owner, name, status in (
        (source, "Base", "ACTIVE"),
        (source, "Old", "ARCHIVED"),
        (other, "Private", "ACTIVE"),
    ):
        target = uuid4()
        with platform_session(
            "provisioning", actor_user_id=None, request_id="scenario-list-fixture", keyring=keyring
        ) as session:
            session.execute(
                insert(tenant).values(
                    id=target,
                    code=f"fc-{target.hex[:12]}",
                    kind="sandbox",
                    status="ACTIVE",
                    display_name=name,
                    reporting_currency="USD",
                    source_tenant_id=owner.tenant_id,
                    audit_hmac_key_id=keyring.new_tenant_audit_key_id(target),
                    created_by_kind="SYSTEM",
                    updated_by_kind="SYSTEM",
                )
            )
            name_platform_tenant(session, target)
            set_tenant_context(
                session, DbContext(tenant_id=target, user_id=owner.user_id, entity_scope="*")
            )
            insert_active_membership(session, tenant_id=target, user_id=owner.user_id)
            set_tenant_context(
                session,
                DbContext(tenant_id=owner.tenant_id, user_id=owner.user_id, entity_scope="*"),
            )
            snapshot = tenant_snapshot_values(owner.tenant_id)
            session.execute(insert(tenant_snapshot).values(**snapshot))
            session.execute(
                insert(scenario).values(
                    tenant_id=owner.tenant_id,
                    id=uuid4(),
                    name=name,
                    status=status,
                    scenario_tenant_id=target,
                    tenant_snapshot_id=snapshot["id"],
                    base_known_at=clock.now(),
                    created_by=owner.user_id,
                    created_by_kind="USER",
                    updated_by_kind="SYSTEM",
                )
            )
    headers = cookie_headers(allowed.token, key=False)
    listed = call(app, "GET", "/api/v1/scenarios", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["name"] for row in listed.json()["items"]] == ["Base", "Old"]
    assert "tenant_id" not in listed.json()["items"][0]
    filtered = call(app, "GET", "/api/v1/scenarios", params={"status": "ARCHIVED"}, headers=headers)
    assert filtered.status_code == 200, filtered.text
    assert [row["name"] for row in filtered.json()["items"]] == ["Old"]
