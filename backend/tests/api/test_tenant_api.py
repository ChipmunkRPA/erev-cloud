"""API-R-04 tenant settings (04 §15.3 API-R-04, T-PLT-01, DB-05, API-C-08; PRD ERR-26, ERR-39;
SCREENS_B SF-23 data bindings; BUILD_SPEC PLF-21).

Tomas holds the Tenant Admin role of a provisioned workspace and is enrolled in MFA, because
``settings.manage`` needs a verified session; Vera is a member without roles.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    Actor,
    colleague,
    cookie_headers,
    enrolled,
    member,
    sign_in,
    workspace,
)
from support.rows import insert_role_assignment

TENANT = "/api/v1/tenant"
PROBLEM_BASE = "https://erev.dev/problems/"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def patch(app: FastAPI, actor: Actor, json: dict[str, Any], **headers: str) -> HttpResponse:
    return call(
        app,
        "PATCH",
        TENANT,
        json=json,
        headers=cookie_headers(actor.token, actor.csrf_token, **headers),
    )


def test_patch_tenant_with_if_match(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    tomas = member(keyring, clock)
    code = tomas.email.split("@", 1)[1].removesuffix(".test")
    with tenant_session(_context(tomas.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=tomas.tenant_id,
            membership_id=tomas.membership_id,
            role_code="tenant_admin",
        )
    admin = enrolled(app, clock, tomas)

    current = call(app, "GET", TENANT, headers=cookie_headers(admin.token, key=False))
    assert current.status_code == 200, current.text
    assert current.headers["ETag"] == '"r1"'
    body = current.json()
    assert (body["id"], body["code"], body["kind"], body["display_name"]) == (
        str(tomas.tenant_id),
        code,
        "production",
        f"Tenant {code}",
    )
    assert "audit_hmac_key_id" not in body

    rename = {"display_name": "Acme Holdings"}
    missing = patch(app, admin, rename)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    renamed = patch(app, admin, rename, **{"If-Match": '"r1"'})
    assert renamed.status_code == 200, renamed.text
    assert renamed.headers["ETag"] == '"r2"'
    assert (renamed.json()["display_name"], renamed.json()["row_version"]) == ("Acme Holdings", 2)

    stale = patch(app, admin, {"display_name": "Acme Group"}, **{"If-Match": '"r1"'})
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text

    kind = patch(app, admin, {"kind": "sandbox"}, **{"If-Match": '"r2"'})
    assert (kind.status_code, slug(kind)) == (409, "tenant-kind-immutable"), kind.text
    assert kind.json()["detail"] == "A workspace's type is fixed when it is created."

    locale = patch(app, admin, {"default_locale": "not a locale"}, **{"If-Match": '"r2"'})
    assert (locale.status_code, slug(locale)) == (422, "validation-failed"), locale.text
    assert [(error["field"], error["rule_id"]) for error in locale.json()["errors"]] == [
        ("default_locale", "T-PLT-01")
    ]

    with tenant_session(_context(tomas.tenant_id), read_only=True) as session:
        events = session.execute(
            select(audit_event.c.action, audit_event.c.object_id).where(
                audit_event.c.object_type == "tenant", audit_event.c.action == "tenant.update"
            )
        ).all()
    assert [(action, object_id) for action, object_id in events] == [
        ("tenant.update", tomas.tenant_id)
    ]

    vera = colleague(tomas.tenant_id, "vera")
    viewer = workspace(app, vera, sign_in(app, vera.email))
    refused = patch(app, viewer, {"display_name": "Vera Holdings"}, **{"If-Match": '"r2"'})
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    unchanged = call(app, "GET", TENANT, headers=cookie_headers(admin.token, key=False))
    assert (unchanged.json()["display_name"], unchanged.headers["ETag"]) == (
        "Acme Holdings",
        '"r2"',
    )
