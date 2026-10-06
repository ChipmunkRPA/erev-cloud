"""The session question of a route and the answer kept for the request (dev-guide
DG-KRN-AUTH-09; 05 §2.5; item AUTH-BEFORE-BODY-1).

CPU witnesses with a faked ``sessions.authenticate``, as ``test_rate_limit_wiring.py`` has them:
the app builds without a database and the requests go through the real route class.

- ``session_questions`` finds the one marked function in the dependency tree of every kind of
  guard, and none in a route without a guard;
- ``GuardedRoute`` asks it before FastAPI reads the body: a caller without a session is answered
  401 for a body that does not decode, a caller with one 422;
- the identity store is asked once a request, however often the question is asked — and an
  answer kept without the synchronizer check does not serve a call that needs it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated, Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.api.deps import GuardedRoute, command
from erev_api.auth import dependencies, sessions
from erev_api.auth.principal import OperatorContext
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from starlette.requests import Request
from support.http import call

NOW: Final = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
# The session cookie the requests present; its value is a synthetic probe, not a credential.
TOKEN: Final = "probe-session-cookie"
COOKIE: Final = {"Cookie": f"{sessions.COOKIE_NAME}={TOKEN}"}
PROBE: Final = "/api/v1/__probe__/note"
PROBLEM_BASE: Final = "https://erev.dev/problems/"
UNDECODABLE: Final = b"{not json"
JSON: Final = {"Content-Type": "application/json"}


class Note(BaseModel):
    text: str


def _fake_auth(session_id: UUID, facts: RequestFacts) -> AuthenticatedSession:
    """The session ``sessions.authenticate`` would return for a verified operator without a
    workspace, carrying the real request facts."""
    session = SimpleNamespace(id=session_id, mfa_verified_at=NOW, user_id=uuid4())
    user = SimpleNamespace(
        id=uuid4(),
        email="probe@members.test",
        display_name="Probe",
        is_operator=True,
        preferences={},
    )
    return AuthenticatedSession(
        session=session,  # type: ignore[arg-type]
        token=TOKEN,
        user=user,  # type: ignore[arg-type]
        active_tenant=None,
        facts=facts,
    )


class Store:
    """``sessions.authenticate`` in a test: it answers one session and records every question,
    with whether the synchronizer evidence came with it."""

    def __init__(self) -> None:
        self.session_id = uuid4()
        self.asked: list[bool] = []

    def __call__(self, token: str, **kwargs: Any) -> AuthenticatedSession:
        assert token == TOKEN
        self.asked.append(kwargs["csrf"] is not None)
        return _fake_auth(self.session_id, kwargs["facts"])


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    fake = Store()
    monkeypatch.setattr(sessions, "authenticate", fake)
    return fake


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture
def app(app_settings: Settings, clock: FrozenClock) -> FastAPI:
    """The application with one more route: a session command with a JSON body, guarded as the
    session routes are (``require_authenticated(tenant=False)``), so no database is asked."""
    application = create_app(app_settings, clock=clock)

    @application.post(PROBE)
    def note(
        body: Note,
        auth: Annotated[
            AuthenticatedSession, Depends(dependencies.require_authenticated(tenant=False))
        ],
    ) -> dict[str, str]:
        return {"text": body.text, "session": str(auth.session.id)}

    return application


def _request(app: FastAPI, method: str = "GET", *, cookie: bool = True) -> Request:
    headers = [(b"host", b"127.0.0.1")]
    if cookie:
        headers.append((b"cookie", COOKIE["Cookie"].encode("ascii")))
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": "/api/v1/me",
        "root_path": "",
        "scheme": "http",
        "server": ("127.0.0.1", 80),
        "client": ("127.0.0.1", 40000),
        "headers": headers,
        "query_string": b"",
        "app": app,
        "state": {"request_id": f"questions-{uuid4().hex[-8:]}"},
    }
    return Request(scope)


def _answer(response: Any) -> str:
    kind = str(response.json().get("type", "")).removeprefix(PROBLEM_BASE)
    return f"{response.status_code} {kind}"


# --- the question of a route ----------------------------------------------------------------------


def _questions_of(guard: Any) -> tuple[Any, ...]:
    synthetic = FastAPI()
    synthetic.router.route_class = GuardedRoute

    @synthetic.post("/probe")
    def probe(
        answer: Any = Depends(guard),  # noqa: B008 - the guard is local to this helper
    ) -> dict[str, str]:
        return {}

    (route,) = [route for route in synthetic.routes if getattr(route, "path", "") == "/probe"]
    return dependencies.session_questions(route.dependant)  # type: ignore[attr-defined]


def test_dg_krn_auth_09_every_guard_ends_in_one_session_question() -> None:
    """Each guard factory puts exactly one marked function of ``(request, clock)`` into the
    tree of its route: ``get_request_context`` under ``require``, ``require_all_entities`` and
    ``command``; the factory's own question for ``require_authenticated`` (each of its three
    forms), ``require_step_up`` and ``require_operator``."""
    tenant_question = (dependencies.get_request_context,)
    assert _questions_of(dependencies.require("contract.read")) == tenant_question
    assert _questions_of(dependencies.require_all_entities("audit.read")) == tenant_question
    assert _questions_of(command("contract.approve")) == tenant_question
    for guard in (
        dependencies.require_authenticated(),
        dependencies.require_authenticated(tenant="optional"),
        dependencies.require_authenticated(tenant=False),
        dependencies.require_operator(),
        command(per_subject=True),
        dependencies.require_step_up(),
    ):
        questions = _questions_of(guard)
        assert len(questions) == 1, guard
        assert getattr(questions[0], "__module__", "") == dependencies.__name__


def test_dg_krn_auth_09_a_route_without_a_guard_has_no_session_question() -> None:
    """The key of a session command (``command()`` without a permission) is no session question,
    and neither is any dependency that is no guard: such a route is not wrapped."""

    def plain() -> str:
        return "no guard"

    assert _questions_of(plain) == ()
    assert _questions_of(command()) == ()


# --- before the body ------------------------------------------------------------------------------


def test_auth_before_body_1_the_session_is_asked_before_the_body_is_read(
    app: FastAPI, store: Store
) -> None:
    """A caller without a session is answered 401 for a body that does not decode — the store
    is not even asked — and a caller with one is answered 422 for it: the body is judged after
    the session, as 05 §2.5 orders the steps."""
    anonymous = call(app, "POST", PROBE, content=UNDECODABLE, headers=JSON)
    assert _answer(anonymous) == "401 unauthenticated", anonymous.text
    assert store.asked == []

    signed_in = call(app, "POST", PROBE, content=UNDECODABLE, headers={**JSON, **COOKIE})
    assert _answer(signed_in) == "422 validation-failed", signed_in.text
    assert store.asked == [True]  # asked once, with the synchronizer evidence of a POST


def test_auth_before_body_1_the_store_is_asked_once_a_request(app: FastAPI, store: Store) -> None:
    """The route class asks the question before the body and FastAPI asks it again when it
    solves the route's dependencies; the store answers once, and the handler receives that
    answer."""
    served = call(app, "POST", PROBE, json={"text": "kept"}, headers=COOKIE)
    assert served.status_code == 200, served.text
    assert served.json() == {"text": "kept", "session": str(store.session_id)}
    assert store.asked == [True]

    again = call(app, "POST", PROBE, json={"text": "kept"}, headers=COOKIE)
    assert again.status_code == 200, again.text
    assert store.asked == [True, True]  # kept for a request, never beyond it


def test_dg_krn_auth_09_several_questions_of_one_request_ask_the_store_once(
    app: FastAPI, store: Store, clock: FrozenClock
) -> None:
    """The four kinds of question on one request: one statement to the store."""
    request = _request(app)
    assert isinstance(
        dependencies.get_optional_request_context(request, clock), AuthenticatedSession
    )
    assert dependencies.require_authenticated(tenant=False)(request, clock).token == TOKEN
    operator = dependencies.require_operator()(request, clock)
    assert isinstance(operator, OperatorContext) and operator.session_id == store.session_id
    assert dependencies.authenticate_session(request, clock).session.id == store.session_id
    assert store.asked == [False]  # a GET: no synchronizer evidence

    dependencies.authenticate_session(_request(app), clock)
    assert store.asked == [False, False]


def test_dg_krn_auth_09_an_answer_kept_without_the_csrf_check_does_not_serve_a_call_with_it(
    app: FastAPI, store: Store, clock: FrozenClock
) -> None:
    """``GET /session`` reads the session without the synchronizer check; a command needs it.
    On a request that changes something, an answer kept from a question without the check is
    not handed to a question with it — the store is asked again, with the evidence — while
    the checked answer then serves both."""
    request = _request(app, "POST")
    dependencies.authenticate_session(request, clock, enforce_csrf=False)
    assert store.asked == [False]
    dependencies.authenticate_session(request, clock)
    assert store.asked == [False, True]
    dependencies.authenticate_session(request, clock)
    dependencies.authenticate_session(request, clock, enforce_csrf=False)
    assert store.asked == [False, True]


def test_dg_krn_auth_09_an_answer_below_zero_or_above_one_second_is_asked_again(
    app: FastAPI, store: Store, clock: FrozenClock
) -> None:
    """A body that takes its time must not carry an answer past it: a session ended while the
    body arrived is refused when the command starts, as it was while the guard ran after the
    body. A question asked within one second of the store's answer — one second of the
    APPLICATION clock, the one the tests move — is served from it. One asked later asks the
    store again, and so does one asked "before" the answer: a clock that steps back keeps no
    answer alive. A guard asked late merely asks twice. The second is the rule's own figure
    (05 §2.5) and is written out here, not read from the constant."""
    assert dependencies.KEPT_FOR == timedelta(seconds=1)
    request = _request(app)
    first = dependencies.authenticate_session(request, clock)
    answered_at = first.facts.now
    clock.advance(timedelta(seconds=1))
    assert dependencies.authenticate_session(request, clock) is first
    assert store.asked == [False]

    # Above one second: asked again, and the later answer is the kept one from then on.
    clock.advance(timedelta(milliseconds=1))
    later = dependencies.authenticate_session(request, clock)
    assert store.asked == [False, False]
    assert later is not first
    assert later.facts.now == answered_at + timedelta(seconds=1, milliseconds=1)
    assert dependencies.authenticate_session(request, clock) is later
    assert store.asked == [False, False]

    # Below zero: the clock stepped back behind the answer.
    clock.set(later.facts.now - timedelta(milliseconds=1))
    stepped_back = dependencies.authenticate_session(request, clock)
    assert store.asked == [False, False, False]
    assert stepped_back is not later


def test_dg_krn_auth_09_a_handler_that_ended_the_session_forgets_its_answer(
    app: FastAPI, store: Store, clock: FrozenClock
) -> None:
    """A rotation or a sign-out ends the presented session inside the handler, milliseconds
    after the guard: ``forget_session`` drops the kept answer, so a guard asked afterwards in
    the same request asks the store — and reads what the store says of the ended session."""
    request = _request(app)
    dependencies.authenticate_session(request, clock)
    dependencies.forget_session(request)
    assert not hasattr(request.state, "authenticated_session")
    dependencies.authenticate_session(request, clock)
    assert store.asked == [False, False]
    dependencies.forget_session(_request(app))  # nothing kept: nothing to forget, no error


def test_dg_krn_auth_09_a_refusal_is_not_kept(app: FastAPI, clock: FrozenClock) -> None:
    """A request without a cookie is refused at every question, and nothing is kept for it."""
    from erev_api.problems import Problem

    request = _request(app, cookie=False)
    for _ in range(2):
        with pytest.raises(Problem) as refused:
            dependencies.get_request_context(request, clock)
        assert refused.value.slug == "unauthenticated"
    assert not hasattr(request.state, "authenticated_session")


def test_dg_krn_auth_09_the_tenant_question_needs_a_workspace(
    app: FastAPI, store: Store, clock: FrozenClock
) -> None:
    """Positive control of the fake: a session without a workspace is no request context."""
    from erev_api.problems import Problem

    with pytest.raises(Problem) as refused:
        dependencies.get_request_context(_request(app), clock)
    assert refused.value.slug == "unauthenticated"
    assert store.asked == [False]
