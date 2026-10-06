"""Request rate limits (BUILD_SPEC SOP-4; 05 SAR-13; 04 API-C-16; REQ-PLT-037; DG-API-07).

``test_req_plt_037_api_client_limit`` and ``test_token_endpoint_limit`` need the database (an API
client, its token and authenticated calls). ``test_openapi_publishes_limit`` reads the committed
OpenAPI only.
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.ratelimit import (
    BROWSER_PER_SESSION,
    LOGIN_PER_ADDRESS,
    OPENAPI_RATE_LIMIT_LINE,
    TOKEN_PER_CLIENT_ID,
)
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    SESSION_MFA,
    Actor,
    Signed,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    next_code,
    sign_in,
)
from support.rows import insert_active_membership, insert_role_assignment

ROOT: Final = Path(__file__).resolve().parents[3]
CLIENTS: Final = "/api/v1/api-clients"
TOKEN_PATH: Final = "/api/v1/oauth/token"
CONTRACTS: Final = "/api/v1/contracts"
PROBLEM_BASE: Final = "https://erev.dev/problems/"
CUSTOMERS: Final = "/api/v1/customers"
ME: Final = "/api/v1/me"
ROLES: Final = "/api/v1/roles"
SESSION: Final = "/api/v1/session"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def tomas(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """A tenant admin, MFA-verified, who may create API clients (``api_client.manage``)."""
    someone = member(keyring, clock)
    with tenant_session(
        DbContext(tenant_id=someone.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code="tenant_admin",
        )
    return enrolled(app, clock, someone)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def _client(app: FastAPI, tomas: Actor, **extra: Any) -> dict[str, Any]:
    created = call(
        app,
        "POST",
        CLIENTS,
        json={"name": "svc-metering", "scopes": ["contract.read", "masterdata.maintain"], **extra},
        headers=cookie_headers(tomas.token, tomas.csrf_token),
    )
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def _basic(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("ascii")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _token(app: FastAPI, client: dict[str, Any]) -> HttpResponse:
    return call(
        app,
        "POST",
        TOKEN_PATH,
        data={"grant_type": "client_credentials"},
        headers={"Authorization": _basic(client["client_id"], client["client_secret"])},
    )


def _bearer(access_token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", **extra}


def test_r_111_8_an_upload_counts_once_in_its_client_bucket(app: FastAPI, tomas: Actor) -> None:
    """Ruling R-111 (8): ``POST /files`` resolves its caller before the body is read and again
    when the command starts (dev-guide DG-API-12). The request is one request: an API client is
    counted once in its bucket, as a browser session is — with a limit of two, two uploads are
    answered by the command and the third by the limiter."""
    client = _client(app, tomas, rate_limit_per_minute=2)
    issued = _token(app, client)
    assert issued.status_code == 200, issued.text
    access = str(issued.json()["access_token"])

    def attempt(number: int) -> HttpResponse:
        return call(
            app,
            "POST",
            "/api/v1/files",
            data={"purpose": "IMPORT_SOURCE"},
            files={"file": ("orders.csv", b"code,name\nC-1,One\n", "text/csv")},
            headers=_bearer(access, **{"Idempotency-Key": f"upload-count-{number:04d}"}),
        )

    answers = [attempt(number) for number in range(3)]
    # The client holds no upload permission: the command refuses it, which is beside the point.
    assert [(answer.status_code, slug(answer)) for answer in answers] == [
        (403, "forbidden"),
        (403, "forbidden"),
        (429, "rate-limited"),
    ]


def test_req_plt_037_api_client_limit(app: FastAPI, clock: FrozenClock, tomas: Actor) -> None:
    client = _client(app, tomas, rate_limit_per_minute=5)
    issued = _token(app, client)
    assert issued.status_code == 200, issued.text
    access = str(issued.json()["access_token"])

    statuses = [call(app, "GET", CONTRACTS, headers=_bearer(access)).status_code for _ in range(5)]
    assert statuses == [200] * 5
    sixth = call(app, "GET", CONTRACTS, headers=_bearer(access))
    assert (sixth.status_code, slug(sixth)) == (429, "rate-limited"), sixth.text
    assert sixth.headers["Retry-After"].isdigit() and int(sixth.headers["Retry-After"]) >= 1
    assert sixth.json()["detail"].startswith("Too many requests.")

    # The 429 is never stored as an idempotent response (DG-KRN-IDEM-03). The command is a
    # SCHEMA-VALID `POST /customers` that reaches run_command and succeeds exactly (Codex P4-SOP4
    # C1 / 2359: a schema-invalid body is refused before run_command and never settled, so only a
    # command that runs can prove storage and replay).
    key = f"sop4-{UUID(client['id']).hex}"
    body = {"code": "C-SOP4", "name": "Pellworth (SOP-4 probe)"}
    limited = call(
        app, "POST", CUSTOMERS, json=body, headers=_bearer(access, **{"Idempotency-Key": key})
    )
    assert (limited.status_code, slug(limited)) == (429, "rate-limited"), limited.text
    assert "Idempotent-Replay" not in limited.headers

    clock.advance(timedelta(seconds=60))
    again = call(app, "GET", CONTRACTS, headers=_bearer(access))
    assert again.status_code == 200, again.text
    # First execution under the key after the window: the command runs and creates the customer.
    created = call(
        app, "POST", CUSTOMERS, json=body, headers=_bearer(access, **{"Idempotency-Key": key})
    )
    assert created.status_code == 201, created.text
    assert (created.json()["code"], created.json()["name"]) == (body["code"], body["name"])
    assert "Idempotent-Replay" not in created.headers
    # The 201 is stored: the same key and body replay it — identical body, Idempotent-Replay: true —
    # which also proves the earlier 429 never entered the idempotency store.
    replayed = call(
        app, "POST", CUSTOMERS, json=body, headers=_bearer(access, **{"Idempotency-Key": key})
    )
    assert replayed.status_code == 201, replayed.text
    assert replayed.headers.get("Idempotent-Replay") == "true"
    assert replayed.json() == created.json()


def _get(app: FastAPI, path: str, token: str) -> HttpResponse:
    return call(app, "GET", path, headers=cookie_headers(token, key=False))


async def _start(application: FastAPI) -> None:
    """Run the app's startup and shutdown as uvicorn does; startup stamps the release (REL-03)."""
    async with application.router.lifespan_context(application):
        pass


def test_browser_session_limit_on_every_authenticated_path(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Codex P4-SOP4-BROWSER-1 — the 1,200-per-minute bucket is keyed on the session and entered by
    every authenticated browser path: an active workspace (``GET /roles``), no workspace (a user
    with two memberships whose
    sign-in opens none, ``GET /me``), and the tenant-free ``GET /session``,
    which must answer the 429 rather than an anonymous 200. The boundary is 1,200 / 1,201; the
    window resets after 60 seconds; another session is a separate bucket."""
    # ``GET /me`` answers the release the process stamped when it started serving (05 REL-03).
    asyncio.run(_start(app))
    # Active workspace: a tenant admin whose single membership opens at sign-in (D-83). ``GET
    # /roles`` is under ``role.manage``, an MFA permission, so the admin is enrolled and verified
    # (REQ-PLT-005; otherwise 403 ``mfa-required``). Every rotation opens a new session row, so
    # the session ``enrolled`` returns has made no request yet: its bucket starts empty.
    admin = member(keyring, clock)
    with tenant_session(
        DbContext(tenant_id=admin.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        insert_role_assignment(
            session,
            tenant_id=admin.tenant_id,
            membership_id=admin.membership_id,
            role_code="tenant_admin",
        )
    signed = enrolled(app, clock, admin)
    statuses = {_get(app, ROLES, signed.token).status_code for _ in range(BROWSER_PER_SESSION)}
    assert statuses == {200}
    refused = _get(app, ROLES, signed.token)
    assert (refused.status_code, slug(refused)) == (429, "rate-limited"), refused.text
    assert refused.headers["Retry-After"].isdigit()
    # GET /session shares the session's bucket and does not degrade the refusal to anonymous 200.
    shared = _get(app, SESSION, signed.token)
    assert (shared.status_code, slug(shared)) == (429, "rate-limited"), shared.text
    clock.advance(timedelta(seconds=60))
    assert _get(app, ROLES, signed.token).status_code == 200

    # No workspace: a second membership means sign-in opens none; GET /me is tenant-free.
    other = member(keyring, clock, name="other")
    with tenant_session(
        DbContext(tenant_id=other.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        insert_active_membership(session, tenant_id=other.tenant_id, user_id=admin.user_id)
    assert signed.secret is not None

    def challenged(password_only: Signed) -> str:
        """The cookie of the session after its sign-in challenge; the rotation opens a new
        session row, which has made no request yet."""
        verified = call(
            app,
            "POST",
            SESSION_MFA,
            json={"code": next_code(app, admin.user_id, str(signed.secret))},
            headers=cookie_headers(password_only.token, password_only.csrf_token),
        )
        assert verified.status_code == 200, verified.text
        return cookie_of(verified)

    pending = sign_in(app, admin.email)
    assert pending.body["active_tenant"] is None
    # The admin has a factor, so this password-only session owes the challenge (REQ-PLT-005). Its
    # refused requests enter the session's bucket like any other: the limit comes before the
    # second-factor refusal, so a session that owes a step cannot be driven without bound.
    statuses = {_get(app, ME, pending.token).status_code for _ in range(BROWSER_PER_SESSION)}
    assert statuses == {403}
    assert slug(_get(app, ME, pending.token)) == "rate-limited"
    roaming = challenged(sign_in(app, admin.email))
    assert {_get(app, ME, roaming).status_code for _ in range(BROWSER_PER_SESSION)} == {200}
    limited = _get(app, ME, roaming)
    assert (limited.status_code, slug(limited)) == (429, "rate-limited"), limited.text
    assert limited.headers["Retry-After"].isdigit()
    # A different session of the same user is its own bucket (keyed on the session identity).
    fresh = challenged(sign_in(app, admin.email))
    assert _get(app, ME, fresh).status_code == 200


def test_token_endpoint_limit(app: FastAPI, clock: FrozenClock, tomas: Actor) -> None:
    client = _client(app, tomas)
    statuses = [_token(app, client).status_code for _ in range(TOKEN_PER_CLIENT_ID)]
    assert statuses == [200] * TOKEN_PER_CLIENT_ID
    refused = _token(app, client)
    assert (refused.status_code, slug(refused)) == (429, "rate-limited"), refused.text
    assert refused.headers["Retry-After"].isdigit()
    clock.advance(timedelta(seconds=60))
    assert _token(app, client).status_code == 200


LOOKUP: Final = "/api/v1/session/invitations/lookup"


def _unknown_client(app: FastAPI, number: int) -> HttpResponse:
    """A token request under a client id nobody holds — a different one each time."""
    client = {"client_id": f"erevc_unknown_{number:04d}", "client_secret": "not-a-secret"}
    return _token(app, client)


def _lookup(app: FastAPI, number: int) -> HttpResponse:
    """An invitation lookup with a token no invitation has (not even the right shape, so that
    the refusal needs no walk over the workspaces)."""
    return call(app, "POST", LOOKUP, json={"token": f"guess-{number:04d}"})


def _limited(response: HttpResponse) -> None:
    assert response.status_code == 429, response.text
    assert slug(response) == "rate-limited"
    assert response.headers["Retry-After"] == "60"
    assert response.json()["detail"] == "Too many requests. Try again in 60 seconds."


def test_sar_13_one_address_cannot_try_client_ids_without_limit(
    app: FastAPI, clock: FrozenClock
) -> None:
    """Security review, the lead's finding 5 (ruling R-48 (e); 05 SAR-13 rev 1.90). The token
    endpoint counted per client id only — 30 a minute for EACH id — so one address tried any
    number of client ids. It is counted per address first, whatever client the request names."""
    statuses = [_unknown_client(app, number).status_code for number in range(LOGIN_PER_ADDRESS)]
    assert statuses == [401] * LOGIN_PER_ADDRESS
    _limited(_unknown_client(app, LOGIN_PER_ADDRESS))
    # A request without credentials is counted too: the address is asked before they are read.
    _limited(call(app, "POST", TOKEN_PATH, data={"grant_type": "client_credentials"}))
    clock.advance(timedelta(seconds=60))
    assert _unknown_client(app, LOGIN_PER_ADDRESS + 1).status_code == 401


def test_sar_13_the_invitation_lookup_is_counted_per_address_with_the_sign_in_surface(
    app: FastAPI, clock: FrozenClock
) -> None:
    """The lead's finding 5: ``POST /session/invitations/lookup`` had no limit at all. It takes
    the per-address bucket of the login class, and that bucket is one for every unauthenticated
    route of the sign-in surface: an address that has used it up is refused on each of them."""
    statuses = [_lookup(app, number).status_code for number in range(LOGIN_PER_ADDRESS)]
    assert statuses == [404] * LOGIN_PER_ADDRESS
    _limited(_lookup(app, LOGIN_PER_ADDRESS))

    origin = {"Origin": app.state.settings.public_origin}
    token = "t" * 43
    surface = {
        "oauth/token": _unknown_client(app, 0),
        "accept-invitation": call(
            app,
            "POST",
            "/api/v1/session/accept-invitation",
            json={"token": token, "password": "Correct-Horse-9-Battery"},
            headers=origin,
        ),
        "password-reset/confirm": call(
            app,
            "POST",
            "/api/v1/session/password-reset/confirm",
            json={"token": token, "new_password": "Correct-Horse-9-Battery"},
            headers=origin,
        ),
        "oidc start": call(app, "GET", "/api/v1/session/oidc/mock-oidc/start"),
        "oidc callback": call(
            app,
            "GET",
            "/api/v1/session/oidc/mock-oidc/callback",
            params={"code": "c", "state": "s"},
        ),
    }
    for response in surface.values():
        _limited(response)
    # Sign-in shares the bucket (SAR-13, as before): its own copy names the wait.
    sign_in_refused = call(
        app, "POST", "/api/v1/session/login", json={"email": "a@example.test", "password": "x" * 12}
    )
    assert (sign_in_refused.status_code, slug(sign_in_refused)) == (429, "rate-limited")

    # Positive control: when the window has passed, each route answers for itself again.
    clock.advance(timedelta(seconds=60))
    assert _lookup(app, LOGIN_PER_ADDRESS + 1).status_code == 404
    assert _unknown_client(app, 1).status_code == 401
    unknown_provider = call(app, "GET", "/api/v1/session/oidc/no-such-provider/start")
    assert unknown_provider.status_code == 404, unknown_provider.text


def test_openapi_publishes_limit() -> None:
    committed = json.loads((ROOT / "docs" / "api" / "openapi.json").read_text("utf-8"))
    description = str(committed["info"].get("description", ""))
    assert "600 requests per minute per API client" in description
    assert description == OPENAPI_RATE_LIMIT_LINE
