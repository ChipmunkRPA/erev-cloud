"""API-R-54 Operator tenant provisioning (04 §15.3 API-R-54, §14.3; dev-guide DG-KRN-TEN-05,
DG-KRN-TEN-06, DG-KRN-IDEM-01; 03 REQ-PLT-038; BUILD_SPEC PLF-29).

Operators are created with ``erev operator create`` and verify TOTP before provisioning. Tomas is a
Tenant Admin whose API client calls the route with a bearer token.
"""

from __future__ import annotations

import base64
import json
import secrets
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.cli import CliServices
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.registry import REPOSITORY_ROOT
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import audit_event, idempotency_record, security_event, tenant_membership
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.operators import create_operator, operator_services, operator_signed_in
from support.principals import Signed, cookie_headers, enrolled, member, sign_in
from support.rows import insert_role_assignment

TENANTS = "/api/v1/operator/tenants"
PROBLEM_BASE = "https://erev.dev/problems/"
TAG = "API-R-54 Operator tenant provisioning"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def services(keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> CliServices:
    return operator_services(keyring, clock, app_settings.file_root)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def request_body(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "display_name": "Harbour Test",
        "reporting_currency": "USD",
        "is_demo": False,
        "admin_email": f"tomas@{code}.test",
    }


def provision(
    app: FastAPI, signed: Signed, body: dict[str, Any], *, key: bool = True
) -> HttpResponse:
    return call(
        app,
        "POST",
        TENANTS,
        json=body,
        headers=cookie_headers(signed.token, signed.csrf_token, key=key),
    )


def test_non_operator_forbidden(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    someone = member(keyring, clock)
    refused = provision(app, sign_in(app, someone.email), request_body(f"t-{secrets.token_hex(6)}"))
    assert (refused.status_code, slug(refused)) == (403, "forbidden")


def test_operator_without_mfa(app: FastAPI, services: CliServices) -> None:
    operator = create_operator(services)
    refused = provision(
        app, sign_in(app, operator["email"]), request_body(f"t-{secrets.token_hex(6)}")
    )
    assert (refused.status_code, slug(refused)) == (403, "mfa-required")


def test_bearer_token_forbidden(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    someone = member(keyring, clock)
    with tenant_session(
        DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    ) as db:
        insert_role_assignment(
            db,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code="tenant_admin",
        )
    tomas = enrolled(app, clock, someone)
    created = call(
        app,
        "POST",
        "/api/v1/api-clients",
        json={"name": "svc-provisioning", "scopes": ["contract.read"]},
        headers=cookie_headers(tomas.token, tomas.csrf_token),
    )
    assert created.status_code == 201, created.text
    client = created.json()
    credentials = f"{client['client_id']}:{client['client_secret']}".encode("ascii")
    issued = call(
        app,
        "POST",
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": "Basic " + base64.b64encode(credentials).decode("ascii")},
    )
    assert issued.status_code == 200, issued.text
    refused = call(
        app,
        "POST",
        TENANTS,
        json=request_body(f"t-{secrets.token_hex(6)}"),
        headers={
            "Authorization": f"Bearer {issued.json()['access_token']}",
            "Idempotency-Key": f"k-{uuid4()}",
        },
    )
    assert (refused.status_code, slug(refused)) == (403, "forbidden")


def test_created_body_shape(app: FastAPI, clock: FrozenClock, services: CliServices) -> None:
    operator = create_operator(services)
    signed = operator_signed_in(app, clock, operator["email"])

    unkeyed = provision(app, signed, request_body("harbour-test"), key=False)
    assert (unkeyed.status_code, slug(unkeyed)) == (422, "validation-failed")
    assert [error["rule_id"] for error in unkeyed.json()["errors"]] == ["API-C-04"]

    created = provision(app, signed, request_body("harbour-test"))
    assert created.status_code == 201, created.text
    assert "location" not in created.headers
    body = created.json()
    assert set(body) == {"tenant", "admin_membership_id", "invitation_expires_at"}
    tenant_id = UUID(body["tenant"]["id"])
    assert body["tenant"] == {
        "id": str(tenant_id),
        "code": "harbour-test",
        "kind": "production",
        "display_name": "Harbour Test",
        "reporting_currency": "USD",
        "is_demo": False,
    }
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
        membership = db.execute(select(tenant_membership)).mappings().one()
        records = db.execute(select(func.count()).select_from(idempotency_record)).scalar_one()
        first = db.execute(select(audit_event).where(audit_event.c.chain_seq == 1)).mappings().one()
    assert (str(membership["id"]), membership["status"]) == (body["admin_membership_id"], "INVITED")
    assert body["invitation_expires_at"] == membership["invitation_expires_at"].isoformat().replace(
        "+00:00", "Z"
    )
    assert records == 0
    assert (first["action"], first["actor_kind"], first["actor_id"], first["detail"]) == (
        "tenant.provision",
        "OPERATOR",
        UUID(operator["id"]),
        {"channel": "API", "operator_user_id": operator["id"]},
    )
    with identity_session(request_id="tests-operator-tenants") as db:
        events = db.execute(
            select(security_event.c.kind, security_event.c.user_id).where(
                security_event.c.tenant_id == tenant_id
            )
        ).all()
    assert [tuple(event) for event in events] == [("PLATFORM_SCOPE_USED", UUID(operator["id"]))]


def test_duplicate_code(app: FastAPI, clock: FrozenClock, services: CliServices) -> None:
    operator = create_operator(services)
    signed = operator_signed_in(app, clock, operator["email"])
    body = request_body(f"t-{secrets.token_hex(6)}")
    assert provision(app, signed, body).status_code == 201
    repeated = provision(app, signed, body)
    assert (repeated.status_code, slug(repeated)) == (422, "validation-failed")
    assert [(error["field"], error["rule_id"]) for error in repeated.json()["errors"]][0] == (
        "code",
        "TENANT_CODE_EXISTS",
    )


def test_krn_ten_06_openapi_tag_and_extension() -> None:
    committed = json.loads((REPOSITORY_ROOT / "docs" / "api" / "openapi.json").read_text("utf-8"))
    operation = committed["paths"][TENANTS]["post"]
    assert operation["operationId"] == "operator_tenants_create"
    assert operation["tags"] == [TAG]
    assert operation["x-erev-operator"] is True
    assert "x-erev-permission" not in operation
