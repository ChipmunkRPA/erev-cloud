"""SOP-4 browser-session admission is wired at the common authentication point (Codex
P4-SOP4-BROWSER-1; 05 SAR-13 "authenticated browser traffic 1,200 per minute per session";
API-C-16).

CPU witnesses over the dependency functions with a faked ``sessions.authenticate``: the app builds
without a database, the limiter is the app's own ``request_rate_limiter`` and the requests are
Starlette ``Request`` objects. Every authenticated-session path — active workspace, no workspace
(``get_optional_request_context``), tenant-free (``require_authenticated(tenant=False)``) and
operator (``require_operator``) — enters the same per-session bucket exactly once per request;
the 1,200 /
1,201 boundary refuses with 429 ``rate-limited`` and ``Retry-After``; the window resets; and
``GET /session`` raises the 429 instead of answering an anonymous 200.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.api.v1 import session as session_routes
from erev_api.auth import dependencies, sessions
from erev_api.auth.ratelimit import BROWSER_PER_SESSION
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from starlette.requests import Request

NOW: Final = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
# The session cookie the faked requests present; its value is a synthetic probe, not a credential.
COOKIE: Final = "erev_session=probe-session-cookie"


def _request(app: FastAPI, method: str = "GET", path: str = "/api/v1/me") -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "scheme": "http",
        "server": ("127.0.0.1", 80),
        "client": ("127.0.0.1", 40000),
        "headers": [(b"cookie", COOKIE.encode("ascii")), (b"host", b"127.0.0.1")],
        "query_string": b"",
        "app": app,
        "state": {"request_id": f"wiring-{uuid4().hex[:8]}"},
    }
    return Request(scope)


def _fake_auth(
    session_id: UUID, facts: RequestFacts, *, operator: bool = False
) -> AuthenticatedSession:
    """The authenticated session ``sessions.authenticate`` would return, carrying the REAL request
    facts (their ``now`` is the clock's, which is what the admission counts against)."""
    session = SimpleNamespace(id=session_id, mfa_verified_at=NOW, user_id=uuid4())
    user = SimpleNamespace(
        id=uuid4(),
        email="probe@members.test",
        display_name="Probe",
        is_operator=operator,
        preferences={},
    )
    return AuthenticatedSession(
        session=session,  # type: ignore[arg-type]
        token=COOKIE.partition("=")[2],
        user=user,  # type: ignore[arg-type]
        active_tenant=None,
        facts=facts,
    )


@pytest.fixture
def wired(
    app_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> tuple[FastAPI, FrozenClock, UUID]:
    clock = FrozenClock(NOW)
    app = create_app(app_settings, clock=clock)
    session_id = uuid4()
    monkeypatch.setattr(
        sessions,
        "authenticate",
        lambda token, **kwargs: _fake_auth(session_id, kwargs["facts"], operator=True),
    )
    return app, clock, session_id


def _fill(app: FastAPI, clock: FrozenClock, count: int) -> None:
    for _ in range(count):
        dependencies.authenticate_session(_request(app), clock)


def _refused(problem: Problem) -> None:
    assert problem.slug == "rate-limited"
    assert problem.headers["Retry-After"].isdigit() and int(problem.headers["Retry-After"]) >= 1
    assert problem.detail is not None and problem.detail.startswith("Too many requests.")


def test_browser_bucket_boundary_and_reset(wired: tuple[FastAPI, FrozenClock, UUID]) -> None:
    """1,200 authenticated requests of one session pass; the 1,201st is 429 with Retry-After; after
    the window the session is admitted again."""
    app, clock, _ = wired
    _fill(app, clock, BROWSER_PER_SESSION)
    with pytest.raises(Problem) as refused:
        dependencies.authenticate_session(_request(app), clock)
    _refused(refused.value)
    clock.advance(timedelta(seconds=60))
    assert dependencies.authenticate_session(_request(app), clock).token == COOKIE.partition("=")[2]


def test_every_session_path_is_admitted_once_per_request(
    wired: tuple[FastAPI, FrozenClock, UUID],
) -> None:
    """No workspace (optional context), tenant-free and operator guards all count — and a request
    that resolves several of them counts ONCE (no double counting)."""
    app, clock, _ = wired
    _fill(app, clock, BROWSER_PER_SESSION - 1)  # one admission left in the window
    request = _request(app)
    # Three dependencies on one request: only the first admission counts.
    assert isinstance(
        dependencies.get_optional_request_context(request, clock), AuthenticatedSession
    )
    assert (
        dependencies.require_authenticated(tenant=False)(request, clock).token
        == COOKIE.partition("=")[2]
    )
    assert dependencies.require_operator()(request, clock).session_id is not None
    # The window is now full: the next REQUEST of the session is refused on every path.
    for dependency in (
        lambda r: dependencies.get_optional_request_context(r, clock),
        lambda r: dependencies.require_authenticated(tenant=False)(r, clock),
        lambda r: dependencies.require_operator()(r, clock),
    ):
        with pytest.raises(Problem) as refused:
            dependency(_request(app))
        _refused(refused.value)


def test_session_get_raises_the_429_instead_of_anonymous_200(
    wired: tuple[FastAPI, FrozenClock, UUID],
) -> None:
    """``GET /session`` swallows sign-in problems into an anonymous answer — never a rate limit."""
    app, clock, _ = wired
    _fill(app, clock, BROWSER_PER_SESSION)
    with pytest.raises(Problem) as refused:
        session_routes.session_get(_request(app, path="/api/v1/session"), clock)
    _refused(refused.value)


def test_sessions_are_separate_buckets(wired: tuple[FastAPI, FrozenClock, UUID]) -> None:
    """The bucket is keyed on the real session identity: another session is not affected."""
    app, clock, _ = wired
    _fill(app, clock, BROWSER_PER_SESSION)
    other = uuid4()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            sessions, "authenticate", lambda token, **kwargs: _fake_auth(other, kwargs["facts"])
        )
        assert (
            dependencies.authenticate_session(_request(app), clock).token
            == COOKIE.partition("=")[2]
        )
