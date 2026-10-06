"""The session cookie's ``Secure`` attribute (05 SAR-09 rev 1.53; DG-KRN-AUTH-07; R-34 SD-2;
supervisor ruling R-53 (1)).

``Secure`` follows ``EREV_PUBLIC_ORIGIN`` and fails closed: it is set unless the configured origin
is an http origin on a loopback host. The security review found it derived from the request's
``Host`` header, which the client chooses, so ``Host: 127.0.0.1`` obtained a cookie without
``Secure`` from an https deployment.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from erev_api.api.deps import cookie_secure
from erev_api.auth import oidc, sessions
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.main import create_app
from starlette.requests import Request

API = Path(__file__).resolve().parents[2] / "erev_api" / "api"
# What a client can put in Host: the public name, loopback in every spelling, and a stranger.
HOSTS = (
    "erev.example.com",
    "127.0.0.1",
    "127.0.0.1:8195",
    "localhost",
    "[::1]:8195",
    "attacker.example",
)


def _request(app: Any, host: str, *, scheme: str) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "scheme": scheme,
        "path": "/api/v1/session/login",
        "raw_path": b"/api/v1/session/login",
        "query_string": b"",
        "headers": [(b"host", host.encode("latin-1"))],
        "client": ("169.254.1.1", 40000),
        "server": ("10.8.0.2", 8080),
        "app": app,
    }
    return Request(scope)


def _production(app_settings: Settings, origin: str) -> Settings:
    return app_settings.model_copy(update={"env": Environment.PRODUCTION, "public_origin": origin})


@pytest.mark.parametrize("host", HOSTS)
def test_sar_09_secure_follows_the_public_origin_never_the_host_header(
    host: str, app_settings: Settings, clock: FrozenClock
) -> None:
    hosted = create_app(_production(app_settings, "https://erev.example.com"), clock=clock)
    compose = create_app(_production(app_settings, "http://127.0.0.1:8195"), clock=clock)
    local = create_app(app_settings, clock=clock)  # the test environment: an http loopback origin
    for scheme in ("http", "https"):  # the scheme a proxy hands on decides nothing either
        # The exploit of the review: an https deployment asked with a loopback Host.
        assert cookie_secure(_request(hosted, host, scheme=scheme)) is True
        # Controls: a browser never returns a Secure cookie to an http origin, so the compose
        # verification stack and the local environments set none, whatever Host says.
        assert cookie_secure(_request(compose, host, scheme=scheme)) is False
        assert cookie_secure(_request(local, host, scheme=scheme)) is False


@pytest.mark.parametrize(
    ("origin", "secure"),
    [
        # https, whatever the host: Secure.
        ("https://erev.example.com", True),
        ("https://127.0.0.1:8443", True),
        ("https://localhost", True),
        # http on a loopback host — the local environments and the compose stack: none, because
        # a browser would not return a Secure cookie to it.
        ("http://127.0.0.1:8195", False),
        ("http://localhost:5270", False),
        ("http://[::1]:8195", False),
        # http on any other host fails closed (R-53 (1)): the cookie stays Secure, a browser does
        # not return it over http, and the deployment holds no session in clear.
        ("http://erev.example.com", True),
        ("http://10.0.0.5:8195", True),
        ("http://127.0.0.1.erev.example.com", True),
        ("http://localhost.erev.example.com", True),
    ],
)
def test_sar_09_secure_unless_an_http_loopback_origin(
    origin: str, secure: bool, app_settings: Settings, clock: FrozenClock
) -> None:
    app = create_app(_production(app_settings, origin), clock=clock)
    for host in HOSTS:
        for scheme in ("http", "https"):
            assert cookie_secure(_request(app, host, scheme=scheme)) is secure, (origin, host)


def test_cookie_headers_carry_secure_only_when_asked() -> None:
    assert sessions.cookie_header("t", secure=True) == (
        "erev_session=t; HttpOnly; Path=/; SameSite=Lax; Secure"
    )
    assert sessions.cookie_header("t", secure=False) == (
        "erev_session=t; HttpOnly; Path=/; SameSite=Lax"
    )
    assert sessions.cleared_cookie_header(secure=True).endswith("; Secure; Max-Age=0")
    assert "; Secure" in oidc.flow_cookie_header("t", secure=True)
    assert "; Secure" not in oidc.flow_cookie_header("t", secure=False)
    assert "; Secure" in oidc.cleared_flow_cookie_header(secure=True)


def test_every_cookie_the_api_sets_asks_cookie_secure() -> None:
    """The family: every ``Set-Cookie`` of the api takes its ``Secure`` flag from
    ``cookie_secure(request)`` — directly, or through a local named ``secure`` assigned from it
    in the same module — so no route decides the attribute on its own."""
    builders = re.compile(
        r"\b(?:cookie_header|cleared_cookie_header|flow_cookie_header|cleared_flow_cookie_header)"
        r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
    )
    found = 0
    for path in sorted(API.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for match in builders.finditer(source):
            found += 1
            arguments = match.group(1)
            assert re.search(r"\bsecure=(cookie_secure\(request\)|secure)\s*$", arguments), (
                path.name,
                match.group(0),
            )
            if arguments.rstrip().endswith("secure=secure"):
                assert "secure = cookie_secure(request)" in source, path.name
    assert found == 10, "two in me.py and eight in session.py"
    assert "request.url.hostname" not in (API / "deps.py").read_text(encoding="utf-8")
