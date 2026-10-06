"""The OIDC mock identity provider (05 ADP-20, ADP-22, ADP-24; dev-guide DG-API-09; D-72;
BUILD_SPEC PLF-27).

The authorization code flow with PKCE S256, ``state`` and ``nonce`` over the users of
``fixtures/oidc/users.json``: discovery, authorize, token and JWKS routes under
``/api/v1/__mocks__/oidc``. ID tokens are RS256-signed with a key the process generates on first
use. The mock has no sign-in page: ``authorize`` signs in the fixture user named by ``login_hint``,
else the first fixture user, and redirects straight back to the client.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

from authlib.oauth2.rfc7636 import create_s256_code_challenge
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import RSAKey

from erev_api.adapters.mocks.admin import fault_response, world_of
from erev_api.clock import Clock
from erev_api.config import Environment, Settings

CODE: Final = "oidc"
PREFIX: Final = "/oidc"
USERS_FIXTURE: Final = Path(__file__).parent / "fixtures" / "oidc" / "users.json"
KEY_ID: Final = "mock-oidc-1"
SIGNING_ALGORITHM: Final = "RS256"
RSA_KEY_BITS: Final = 2048
ID_TOKEN_LIFETIME_SECONDS: Final = 300
CODE_BYTES: Final = 24


@dataclass(frozen=True, slots=True)
class MockUser:
    sub: str
    email: str
    email_verified: bool
    name: str


@dataclass(frozen=True, slots=True)
class IssuedCode:
    client_id: str
    redirect_uri: str
    code_challenge: str
    nonce: str
    user: MockUser


def issuer_for(settings: Settings) -> str:
    """DG-API-09: clients reach the mock on 127.0.0.1 at the api port of the environment."""
    port = settings.e2e_api_port if settings.env is Environment.E2E else settings.api_port
    return f"http://127.0.0.1:{port}/api/v1/__mocks__/{CODE}"


def load_users(path: Path = USERS_FIXTURE) -> tuple[MockUser, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        MockUser(
            sub=str(user["sub"]),
            email=str(user["email"]),
            email_verified=bool(user["email_verified"]),
            name=str(user["name"]),
        )
        for user in raw["users"]
    )


@lru_cache(maxsize=1)
def signing_key() -> RSAKey:
    """The RSA key of the process, generated on first use (ADP-24)."""
    return RSAKey.generate_key(
        RSA_KEY_BITS,
        parameters={"kid": KEY_ID, "use": "sig", "alg": SIGNING_ALGORITHM},
        private=True,
    )


class OidcMock:
    """ADP-24 state: the fixture users and the authorization codes not yet redeemed."""

    def __init__(self, *, issuer: str, users_path: Path = USERS_FIXTURE) -> None:
        self.issuer = issuer
        self._users_path = users_path
        self._lock = threading.Lock()
        self._users: tuple[MockUser, ...] = ()
        self._codes: dict[str, IssuedCode] = {}
        self.reset()

    def reset(self) -> None:
        users = load_users(self._users_path)
        with self._lock:
            self._users = users
            self._codes = {}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "issuer": self.issuer,
                "users": [user.sub for user in self._users],
                "open_codes": len(self._codes),
            }

    def discovery(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "jwks_uri": f"{self.issuer}/jwks",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [SIGNING_ALGORITHM],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": ["openid", "email", "profile"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "claims_supported": ["sub", "email", "email_verified", "name", "nonce"],
        }

    def authorize(self, params: Mapping[str, str]) -> tuple[str, str] | None:
        """The code and redirect URI of a valid authorization request, or None."""
        required = ("client_id", "redirect_uri", "state", "nonce", "code_challenge")
        if (
            params.get("response_type") != "code"
            or params.get("code_challenge_method") != "S256"
            or "openid" not in params.get("scope", "").split()
            or any(not params.get(name) for name in required)
        ):
            return None
        with self._lock:
            hint = params.get("login_hint")
            matching = [user for user in self._users if hint is None or user.email == hint]
            if not matching:
                return None
            code = secrets.token_urlsafe(CODE_BYTES)
            self._codes[code] = IssuedCode(
                client_id=params["client_id"],
                redirect_uri=params["redirect_uri"],
                code_challenge=params["code_challenge"],
                nonce=params["nonce"],
                user=matching[0],
            )
        return code, params["redirect_uri"]

    def redeem(self, form: Mapping[str, str], *, now: int) -> dict[str, Any] | None:
        """The token response for a one-time code with the matching client, redirect URI and PKCE
        verifier, or None."""
        if form.get("grant_type") != "authorization_code":
            return None
        with self._lock:
            issued = self._codes.pop(form.get("code", ""), None)
        if (
            issued is None
            or form.get("client_id") != issued.client_id
            or form.get("redirect_uri") != issued.redirect_uri
            or not hmac.compare_digest(
                create_s256_code_challenge(form.get("code_verifier", "")), issued.code_challenge
            )
        ):
            return None
        claims = {
            "iss": self.issuer,
            "sub": issued.user.sub,
            "aud": issued.client_id,
            "iat": now,
            "exp": now + ID_TOKEN_LIFETIME_SECONDS,
            "nonce": issued.nonce,
            "email": issued.user.email,
            "email_verified": issued.user.email_verified,
            "name": issued.user.name,
        }
        id_token = jwt.encode({"alg": SIGNING_ALGORITHM, "kid": KEY_ID}, claims, signing_key())
        return {
            "access_token": secrets.token_urlsafe(CODE_BYTES),
            "token_type": "Bearer",
            "expires_in": ID_TOKEN_LIFETIME_SECONDS,
            "id_token": id_token,
        }


def mock_of(request: Request) -> OidcMock:
    adapter = world_of(request).adapters[CODE]
    assert isinstance(adapter, OidcMock)
    return adapter


router = APIRouter(prefix=PREFIX)


@router.get("/.well-known/openid-configuration")
def discovery(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/.well-known/openid-configuration")
    return fault or JSONResponse(mock_of(request).discovery())


@router.get("/authorize")
def authorize(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/authorize")
    if fault is not None:
        return fault
    params = dict(request.query_params)
    issued = mock_of(request).authorize(params)
    if issued is None:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    code, redirect_uri = issued
    separator = "&" if "?" in redirect_uri else "?"
    query = urlencode({"code": code, "state": params["state"]})
    return RedirectResponse(f"{redirect_uri}{separator}{query}", status_code=302)


@router.post("/token")
async def token(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/token")
    if fault is not None:
        return fault
    form = {name: str(value) for name, value in (await request.form()).items()}
    clock: Clock = request.app.state.clock
    body = mock_of(request).redeem(form, now=int(clock.now().timestamp()))
    if body is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/jwks")
def jwks(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/jwks")
    return fault or JSONResponse({"keys": [signing_key().as_dict(private=False)]})
