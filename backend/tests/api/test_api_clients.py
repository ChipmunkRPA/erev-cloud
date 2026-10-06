"""API-R-02 OAuth token and API-R-08 API clients (04 §15.3 API-R-02, API-R-08, T-PLT-15, T-PLT-16,
DB-12; dev-guide DG-KRN-AUTH-01, DG-KRN-AUTH-02, DG-KRN-APR-04; 05 SAR-28, THR-04; PRD ERR-24,
BR-PLT-06; BUILD_SPEC PLF-25).

Tomas is a Tenant Admin enrolled in MFA, so ``api_client.manage`` passes and his enrolment counts as
a fresh step-up until the clock moves five minutes on. API clients call the API with bearer tokens
and no cookie.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth import passwords
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    api_token,
    approval_decision,
    approval_request,
    audit_event,
    idempotency_record,
    webhook_endpoint,
)
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import exc, func, insert, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    Actor,
    colleague,
    cookie_headers,
    enrolled,
    member,
    sign_in,
    step_up,
    workspace,
)
from support.rows import (
    PROBE_CONTENT_SHA256,
    api_client_values,
    insert_approval_request,
    insert_approval_step,
    insert_role_assignment,
)

CLIENTS = "/api/v1/api-clients"
TOKEN_PATH = "/api/v1/oauth/token"
AUDIT = "/api/v1/audit-events"
PROBLEM_BASE = "https://erev.dev/problems/"
CLIENT_ID = re.compile(r"^erevc_[0-9a-f]{32}_[A-Za-z0-9_-]{22}$")
ACCESS_TOKEN = re.compile(r"^erevt_[0-9a-f]{32}_[A-Za-z0-9_-]{43}$")
CLIENT_KEYS = {
    "id",
    "name",
    "client_id",
    "scopes",
    "is_all_entities",
    "entity_ids",
    "status",
    "expires_at",
    "rate_limit_per_minute",
    "last_used_at",
    "secret_rotated_at",
    "has_secret",
    "approval_request_id",
    "created_at",
    "updated_at",
    "row_version",
}
REASON = "Integration retired in September"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def tomas(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    someone = member(keyring, clock)
    with tenant_session(_db(someone.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code="tenant_admin",
        )
    return enrolled(app, clock, someone)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def post(app: FastAPI, path: str, actor: Actor, json: dict[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def create(app: FastAPI, actor: Actor, name: str, scopes: list[str]) -> dict[str, Any]:
    created = post(app, CLIENTS, actor, {"name": name, "scopes": scopes})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def basic(client_id: str, client_secret: str) -> str:
    credentials = f"{client_id}:{client_secret}".encode("ascii")
    return "Basic " + base64.b64encode(credentials).decode("ascii")


def request_token(
    app: FastAPI, client: dict[str, Any], client_secret: str | None = None, **form: str
) -> HttpResponse:
    return call(
        app,
        "POST",
        TOKEN_PATH,
        data={"grant_type": "client_credentials", **form},
        headers={
            "Authorization": basic(client["client_id"], client_secret or client["client_secret"])
        },
    )


def access_token(app: FastAPI, client: dict[str, Any], **form: str) -> str:
    issued = request_token(app, client, **form)
    assert issued.status_code == 200, issued.text
    return str(issued.json()["access_token"])


def bearer(access: str, *, key: bool = False, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access}", **extra}
    if key:
        headers["Idempotency-Key"] = f"k-{uuid4()}"
    return headers


@pytest.mark.control("CTL-037")
def test_ctl_037_approval_scope_rejected(app: FastAPI, tomas: Actor) -> None:
    refused = post(
        app,
        CLIENTS,
        tomas,
        {"name": "svc-salesforce", "scopes": ["contract.read", "contract.approve"]},
    )
    assert (refused.status_code, slug(refused)) == (422, "scope-not-allowed"), refused.text
    assert refused.json()["detail"] == "API clients cannot hold approval permissions."
    assert fields(refused) == [("scopes[1]", "DB-12")]

    tenant_id = tomas.member.tenant_id
    with tenant_session(_db(tenant_id)) as session:
        assert session.execute(select(func.count()).select_from(api_client)).scalar_one() == 0
        # DB-12 refuses the row itself.
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(
                insert(api_client).values(
                    **api_client_values(tenant_id, scopes=["contract.approve"])
                )
            )
        savepoint.rollback()
    orig = excinfo.value.orig
    assert getattr(orig, "sqlstate", None) == "P0001"
    message = str(getattr(getattr(orig, "diag", None), "message_primary", ""))
    assert message.startswith("EREV-REF-002: scopes contract.approve of erev.api_client")


def test_create_client_secret_shown_once(app: FastAPI, clock: FrozenClock, tomas: Actor) -> None:
    tenant_id = tomas.member.tenant_id
    body = {
        "name": "svc-salesforce",
        "scopes": ["masterdata.maintain", "contract.read", "import.upload", "contract.create"],
    }
    clock.advance(timedelta(minutes=6))
    stale = post(app, CLIENTS, tomas, body)
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text

    admin = step_up(app, clock, tomas)
    invalid = post(
        app,
        CLIENTS,
        admin,
        {
            "name": " ",
            "scopes": ["contract.explode"],
            "is_all_entities": False,
            "rate_limit_per_minute": 0,
        },
    )
    assert (invalid.status_code, slug(invalid), fields(invalid)) == (
        422,
        "validation-failed",
        [
            ("name", "T-PLT-15"),
            ("scopes[0]", "DB-12"),
            ("entity_codes", "T-PLT-15"),
            ("rate_limit_per_minute", "T-PLT-15"),
        ],
    ), invalid.text

    created = post(app, CLIENTS, admin, body)
    assert created.status_code == 201, created.text
    client = created.json()
    assert set(client) == CLIENT_KEYS | {"client_secret"}
    assert CLIENT_ID.fullmatch(client["client_id"]), client["client_id"]
    assert client["client_id"].startswith(f"erevc_{tenant_id.hex}_")
    client_secret = client["client_secret"]
    assert isinstance(client_secret, str) and len(client_secret) == 43
    created_at = datetime.fromisoformat(client["created_at"])
    assert created_at == clock.now()
    assert datetime.fromisoformat(client["expires_at"]) == created_at + timedelta(days=365)
    assert (
        client["scopes"],
        client["status"],
        client["rate_limit_per_minute"],
        client["is_all_entities"],
        client["entity_ids"],
        client["secret_rotated_at"],
        client["has_secret"],
    ) == (
        ["contract.create", "contract.read", "import.upload", "masterdata.maintain"],
        "ACTIVE",
        600,
        True,
        [],
        # Supervisor ruling R-38 (iii) (04 T-PLT-15 rev 1.168): the bootstrap Tenant Admin's
        # request is approved at once by rule AUTO-BOOTSTRAP, so the secret is issued at creation
        # and ``secret_rotated_at`` is that instant — it was null, when the column meant a
        # rotation only.
        client["created_at"],
        True,
    )
    assert client["approval_request_id"] is not None
    location = f"{CLIENTS}/{client['id']}"
    # Written pending, activated by the approval and stamped with the secret's issue: version 3
    # (it was 1 when the row was written ACTIVE in one statement).
    assert (created.headers["Location"], created.headers["ETag"]) == (location, '"r3"')

    read = get(app, location, admin)
    assert read.status_code == 200, read.text
    assert set(read.json()) == CLIENT_KEYS
    assert read.headers["ETag"] == '"r3"'
    listed = get(app, CLIENTS, admin, status="ACTIVE")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [client["id"]]
    assert get(app, CLIENTS, admin, status="REVOKED").json()["items"] == []
    assert client_secret not in read.text + listed.text

    with tenant_session(_db(tenant_id)) as session:
        stored_hash = session.execute(
            select(api_client.c.secret_hash).where(api_client.c.id == UUID(client["id"]))
        ).scalar_one()
    assert stored_hash.startswith("$argon2id$")
    assert passwords.verify_password(stored_hash, client_secret)

    audit = get(app, AUDIT, admin, object_id=client["id"])
    assert audit.status_code == 200, audit.text
    assert [item["action"] for item in audit.json()["items"]] == [
        "api_client.activate",
        "api_client.create",
    ]
    assert client_secret not in audit.text

    victor = colleague(tenant_id, "victor")
    with tenant_session(_db(tenant_id)) as session:
        insert_role_assignment(
            session, tenant_id=tenant_id, membership_id=victor.membership_id, role_code="viewer"
        )
    viewer = workspace(app, victor, sign_in(app, victor.email))
    hidden = get(app, CLIENTS, viewer)
    assert (hidden.status_code, slug(hidden)) == (403, "forbidden"), hidden.text


def stored_response(tenant_id: UUID, key: str) -> Mapping[str, Any]:
    """The state and stored body of the ``idempotency_record`` of ``key`` (T-PLT-28)."""
    with tenant_session(_db(tenant_id)) as session:
        return dict(
            session.execute(
                select(idempotency_record.c.state, idempotency_record.c.response_body).where(
                    idempotency_record.c.idempotency_key == key
                )
            )
            .mappings()
            .one()
        )


def keyed(actor: Actor, key: str) -> dict[str, str]:
    return cookie_headers(actor.token, actor.csrf_token, key=False, **{"Idempotency-Key": key})


def test_client_secret_not_kept_for_replay(app: FastAPI, tomas: Actor) -> None:
    """PR-A-02 (D-80): the review probe saw the plaintext kept for 7 days and returned on replay."""
    tenant_id = tomas.member.tenant_id
    body = {"name": "svc-probe", "scopes": ["audit.read"]}
    create_key = "k-sup-plf-2-api-client-0001"
    created = call(app, "POST", CLIENTS, json=body, headers=keyed(tomas, create_key))
    assert created.status_code == 201, created.text
    client = created.json()
    client_secret = client["client_secret"]
    assert isinstance(client_secret, str) and len(client_secret) == 43
    record = stored_response(tenant_id, create_key)
    assert (record["state"], record["response_body"]["client_secret"]) == ("COMPLETED", None)
    assert record["response_body"]["id"] == client["id"]
    assert client_secret not in json.dumps(record["response_body"])
    with tenant_session(_db(tenant_id)) as session:
        stored_hash = session.execute(
            select(api_client.c.secret_hash).where(api_client.c.id == UUID(client["id"]))
        ).scalar_one()
    assert stored_hash.startswith("$argon2id$")

    replay = call(app, "POST", CLIENTS, json=body, headers=keyed(tomas, create_key))
    assert (replay.status_code, replay.headers["Idempotent-Replay"]) == (201, "true"), replay.text
    assert (replay.json()["id"], replay.json()["client_secret"]) == (client["id"], None)

    rotate = f"{CLIENTS}/{client['id']}/rotate-secret"
    rotate_key = "k-sup-plf-2-api-client-0002"
    rotated = call(app, "POST", rotate, json={}, headers=keyed(tomas, rotate_key))
    assert rotated.status_code == 200, rotated.text
    renewed_secret = rotated.json()["client_secret"]
    assert isinstance(renewed_secret, str) and len(renewed_secret) == 43
    assert renewed_secret != client_secret
    record = stored_response(tenant_id, rotate_key)
    assert (record["state"], record["response_body"]["client_secret"]) == ("COMPLETED", None)
    assert renewed_secret not in json.dumps(record["response_body"])
    replayed = call(app, "POST", rotate, json={}, headers=keyed(tomas, rotate_key))
    assert (replayed.status_code, replayed.headers["Idempotent-Replay"]) == (200, "true")
    assert replayed.json()["client_secret"] is None
    issued = request_token(app, client, renewed_secret)
    assert issued.status_code == 200, issued.text


def test_client_credentials_token(app: FastAPI, clock: FrozenClock, tomas: Actor) -> None:
    tenant_id = tomas.member.tenant_id
    auditor = create(app, tomas, "svc-audit", ["audit.read", "contract.read"])
    reader = create(app, tomas, "svc-reader", ["contract.read"])

    issued = request_token(app, auditor)
    assert issued.status_code == 200, issued.text
    token = issued.json()
    assert set(token) == {"access_token", "token_type", "expires_in", "scope"}
    assert ACCESS_TOKEN.fullmatch(token["access_token"]), token["access_token"]
    assert token["access_token"].startswith(f"erevt_{tenant_id.hex}_")
    assert (token["token_type"], token["expires_in"], token["scope"]) == (
        "Bearer",
        3600,
        "audit.read contract.read",
    )
    assert issued.headers["Cache-Control"] == "no-store"

    read = call(app, "GET", AUDIT, headers=bearer(token["access_token"]))
    assert read.status_code == 200, read.text
    assert read.headers["X-Erev-Tenant-Kind"] == "production"
    refused = call(app, "GET", AUDIT, headers=bearer(access_token(app, reader)))
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    narrowed = request_token(app, auditor, scope="contract.read")
    assert narrowed.json()["scope"] == "contract.read"
    assert slug(call(app, "GET", AUDIT, headers=bearer(narrowed.json()["access_token"]))) == (
        "forbidden"
    )

    digest = hashlib.sha256(token["access_token"].encode("ascii")).hexdigest()
    with tenant_session(_db(tenant_id)) as session:
        stored = session.execute(
            select(api_token.c.scopes, api_token.c.issued_at, api_token.c.expires_at).where(
                api_token.c.token_sha256 == digest
            )
        ).one()
        last_used_at = session.execute(
            select(api_client.c.last_used_at).where(api_client.c.id == UUID(auditor["id"]))
        ).scalar_one()
    assert (list(stored.scopes), stored.issued_at, stored.expires_at) == (
        ["audit.read", "contract.read"],
        clock.now(),
        clock.now() + timedelta(minutes=60),
    )
    assert last_used_at == clock.now()

    beyond = request_token(app, reader, scope="audit.read")
    assert (beyond.status_code, slug(beyond), fields(beyond)) == (
        422,
        "validation-failed",
        [("scope", "API-R-02")],
    ), beyond.text
    grant = request_token(app, auditor, grant_type="password")
    assert (grant.status_code, slug(grant), fields(grant)) == (
        422,
        "validation-failed",
        [("grant_type", "API-R-02")],
    ), grant.text
    wrong = request_token(app, auditor, "not-the-client-secret")
    assert (wrong.status_code, slug(wrong)) == (401, "unauthenticated"), wrong.text
    assert wrong.headers["WWW-Authenticate"] == 'Basic realm="erev"'
    anonymous = call(app, "POST", TOKEN_PATH, data={"grant_type": "client_credentials"})
    assert (anonymous.status_code, slug(anonymous)) == (401, "unauthenticated")
    forged = call(app, "GET", AUDIT, headers=bearer(f"erevt_{tenant_id.hex}_{'A' * 43}"))
    assert (forged.status_code, slug(forged)) == (401, "unauthenticated")
    assert forged.headers["WWW-Authenticate"] == 'Bearer realm="erev", error="invalid_token"'
    # Session routes take cookies only.
    session_route = call(
        app,
        "POST",
        "/api/v1/session/tenant",
        json={"tenant_id": str(tenant_id)},
        headers=bearer(token["access_token"], key=True),
    )
    assert (session_route.status_code, slug(session_route)) == (401, "unauthenticated")


def test_token_expiry_revocation_and_rotation(
    app: FastAPI, clock: FrozenClock, tomas: Actor
) -> None:
    client = create(app, tomas, "svc-netsuite", ["audit.read"])
    first = access_token(app, client)
    assert call(app, "GET", AUDIT, headers=bearer(first)).status_code == 200

    rotated = post(app, f"{CLIENTS}/{client['id']}/rotate-secret", tomas, {})
    assert rotated.status_code == 200, rotated.text
    renewed = rotated.json()
    assert set(renewed) == CLIENT_KEYS | {"client_secret"}
    assert renewed["client_secret"] != client["client_secret"]
    assert datetime.fromisoformat(renewed["secret_rotated_at"]) == clock.now()
    old = request_token(app, client)
    assert (old.status_code, slug(old)) == (401, "unauthenticated"), old.text
    assert call(app, "GET", AUDIT, headers=bearer(first)).status_code == 401
    second = access_token(app, renewed)
    assert call(app, "GET", AUDIT, headers=bearer(second)).status_code == 200

    revoke = f"{CLIENTS}/{client['id']}/revoke"
    short = post(app, revoke, tomas, {"reason": "retired"})
    assert (short.status_code, slug(short), fields(short)) == (
        422,
        "validation-failed",
        [("reason", "BR-PLT-08")],
    ), short.text
    revoked = post(app, revoke, tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text
    assert set(revoked.json()) == CLIENT_KEYS
    assert revoked.json()["status"] == "REVOKED"
    gone = call(app, "GET", AUDIT, headers=bearer(second))
    assert (gone.status_code, slug(gone)) == (401, "unauthenticated"), gone.text
    assert request_token(app, renewed).status_code == 401
    again = post(app, f"{CLIENTS}/{client['id']}/rotate-secret", tomas, {})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    audit = get(app, AUDIT, tomas, object_id=client["id"])
    assert audit.status_code == 200, audit.text
    assert [(item["action"], item["comment"]) for item in audit.json()["items"]] == [
        ("api_client.revoke", REASON),
        ("api_client.rotate_secret", None),
        ("api_client.activate", None),  # the approval of its scopes (ruling R-38 (iii))
        ("api_client.create", None),
    ]
    assert renewed["client_secret"] not in audit.text

    lasting = create(app, tomas, "svc-metering", ["audit.read"])
    token = access_token(app, lasting)
    clock.advance(timedelta(minutes=59))
    assert call(app, "GET", AUDIT, headers=bearer(token)).status_code == 200
    clock.advance(timedelta(minutes=2))
    expired = call(app, "GET", AUDIT, headers=bearer(token))
    assert (expired.status_code, slug(expired)) == (401, "unauthenticated"), expired.text
    assert expired.headers["WWW-Authenticate"] == 'Bearer realm="erev", error="invalid_token"'


def test_krn_apr_04_api_client_cannot_decide(app: FastAPI, tomas: Actor) -> None:
    tenant_id = tomas.member.tenant_id
    with tenant_session(_db(tenant_id)) as session:
        request_id = insert_approval_request(session, tenant_id=tenant_id)
        insert_approval_step(session, tenant_id=tenant_id, approval_request_id=request_id)
    client = create(app, tomas, "svc-salesforce", ["contract.read", "contract.create"])
    token = access_token(app, client)

    decided = call(
        app,
        "POST",
        f"/api/v1/approvals/{request_id}/approve",
        json={"subject_content_sha256": PROBE_CONTENT_SHA256},
        headers=bearer(token, key=True),
    )
    assert (decided.status_code, slug(decided)) == (403, "forbidden"), decided.text
    assert decided.json()["detail"] == "Only a signed-in person can approve or reject an item."
    with tenant_session(_db(tenant_id)) as session:
        decisions = session.execute(
            select(func.count())
            .select_from(approval_decision)
            .where(approval_decision.c.approval_request_id == request_id)
        ).scalar_one()
        status = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one()
    assert (decisions, status) == (0, "PENDING")


def test_bearer_requests_skip_csrf(app: FastAPI, tomas: Actor) -> None:
    tenant_id = tomas.member.tenant_id
    client = create(app, tomas, "svc-hooks", ["webhook.manage"])
    token = access_token(app, client)
    body = {"url": "https://hooks.example/erev", "event_kinds": ["period.locked"]}

    created = call(
        app,
        "POST",
        "/api/v1/webhook-endpoints",
        json=body,
        headers=bearer(token, key=True, Origin="https://integrations.example"),
    )
    assert created.status_code == 201, created.text
    endpoint_id = UUID(created.json()["id"])
    client_id = UUID(client["id"])
    with tenant_session(_db(tenant_id)) as session:
        stamps = session.execute(
            select(webhook_endpoint.c.created_by, webhook_endpoint.c.created_by_kind).where(
                webhook_endpoint.c.id == endpoint_id
            )
        ).one()
        actor = session.execute(
            select(
                audit_event.c.actor_kind,
                audit_event.c.actor_id,
                audit_event.c.api_client_id,
                audit_event.c.auth_method,
            ).where(audit_event.c.object_id == endpoint_id)
        ).one()
    assert tuple(stamps) == (client_id, "API_CLIENT")
    assert tuple(actor) == ("API_CLIENT", client_id, client_id, "client_credentials")

    # A cookie request without the synchronizer token is refused at the same step.
    cookie = call(
        app, "POST", "/api/v1/webhook-endpoints", json=body, headers=cookie_headers(tomas.token)
    )
    assert (cookie.status_code, slug(cookie), fields(cookie)) == (
        403,
        "forbidden",
        [("X-CSRF-Token", "API-C-02")],
    ), cookie.text
