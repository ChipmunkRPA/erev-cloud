"""05 ADP-21, ADP-22 and ADP-24: mock fault injection, reset and the OIDC mock (dev-guide DG-API-09;
D-72; BUILD_SPEC PLF-27)."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

from authlib.oauth2.rfc7636 import create_s256_code_challenge
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import FastAPI
from joserfc import jwt
from joserfc.jwk import KeySet
from support.http import HttpResponse, call

MOCKS = "/api/v1/__mocks__"
ADMIN = f"{MOCKS}/__admin"
OIDC = f"{MOCKS}/oidc"
CLIENT_ID = "erev-local"
REDIRECT_URI = "http://127.0.0.1:5270/api/v1/session/oidc/mock-oidc/callback"
VERIFIER = "pkce-verifier-" + "7" * 43


def issue_code(app: FastAPI) -> str:
    response = call(
        app,
        "GET",
        f"{OIDC}/authorize",
        params={
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": "openid email",
            "state": "state-1",
            "nonce": "nonce-1",
            "code_challenge": create_s256_code_challenge(VERIFIER),
            "code_challenge_method": "S256",
        },
    )
    assert response.status_code == 302, response.text
    query = dict(parse_qsl(urlsplit(response.headers["location"]).query))
    assert query["state"] == "state-1"
    return query["code"]


def redeem(app: FastAPI, code: str, verifier: str = VERIFIER) -> HttpResponse:
    return call(
        app,
        "POST",
        f"{OIDC}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": verifier,
        },
    )


def test_adp_21_faults_apply_to_next_requests(app_settings: Settings, clock: FrozenClock) -> None:
    app = create_app(app_settings, clock=clock)
    seeded = call(app, "GET", f"{ADMIN}/state")
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["faults"] == []
    code = issue_code(app)

    queued = call(
        app,
        "POST",
        f"{ADMIN}/faults",
        json={"route": "/oidc/token", "kind": "SERVER_ERROR", "count": 1},
    )
    assert queued.status_code == 201, queued.text
    assert queued.json()["faults"] == [
        {"route": "/oidc/token", "kind": "SERVER_ERROR", "remaining": 1}
    ]
    assert redeem(app, code).status_code == 500
    succeeded = redeem(app, code)
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["token_type"] == "Bearer"
    keys = KeySet.import_key_set(call(app, "GET", f"{OIDC}/jwks").json())
    claims = jwt.decode(succeeded.json()["id_token"], keys, algorithms=["RS256"]).claims
    assert (claims["aud"], claims["nonce"], claims["email"], claims["email_verified"]) == (
        CLIENT_ID,
        "nonce-1",
        "maya@acme.test",
        True,
    )
    assert claims["iat"] == int(clock.now().timestamp())
    # Codes are single-use and bound to the PKCE challenge.
    assert redeem(app, code).status_code == 400
    assert redeem(app, issue_code(app), verifier="another-" + VERIFIER).status_code == 400

    limited = call(
        app,
        "POST",
        f"{ADMIN}/faults",
        json={"route": "/oidc/jwks", "kind": "RATE_LIMIT", "count": 2},
    )
    assert limited.status_code == 201, limited.text
    throttled = call(app, "GET", f"{OIDC}/jwks")
    assert (throttled.status_code, throttled.headers["retry-after"]) == (429, "1")
    issue_code(app)
    assert call(app, "GET", f"{ADMIN}/state").json() != seeded.json()

    reset = call(app, "POST", f"{ADMIN}/reset")
    assert reset.status_code == 204, reset.text
    assert call(app, "GET", f"{ADMIN}/state").json() == seeded.json()
    assert call(app, "GET", f"{OIDC}/jwks").status_code == 200
