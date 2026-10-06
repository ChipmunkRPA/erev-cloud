"""The session is asked before a request body is read, and asked once (item AUTH-BEFORE-BODY-1;
05 §2.5; 04 API-C-17; dev-guide DG-API-12, DG-KRN-AUTH-09).

FastAPI reads and decodes a route's body before it solves the route's dependencies, the guard
among them. Measured before the rule over every operation of the application that changes
something: 227 answered a caller without a session 401 for a body that decodes, and 180 of them
answered the same caller 422 ``validation-failed`` for a body that does not — the body had been
read, decoded and judged before anybody had looked at the session. The one guarded operation
with a body that answered 401 both ways was ``POST /files``, whose route class already asked
first (ruling R-111 (8)).

``GuardedRoute`` now asks its route's session question before the handler that reads the body,
and what the identity store answered is kept for the request, so that FastAPI's later call of
the guard asks the store nothing. The operations are read from the application: one added later
is walked too.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

import pytest
from erev_api.api.deps import PUBLIC_PATHS
from erev_api.auth import sessions
from erev_api.auth.dependencies import (
    authenticate_session,
    forget_session,
    require_authenticated,
    session_questions,
)
from erev_api.auth.keyring import KeyRing
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.release import current_release
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import app_user, file_object, user_session
from erev_api.main import create_app
from fastapi import Depends, FastAPI, Request
from fastapi.routing import APIRoute, iter_route_contexts
from sqlalchemy import Engine, event, func, select
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.http import HttpResponse, call
from support.principals import Actor, cookie_headers, enrolled, member
from support.reference import assign

MOCK_PREFIX = "/api/v1/__mocks__/"
PROBLEM_BASE = "https://erev.dev/problems/"
READS = frozenset({"GET", "HEAD", "OPTIONS"})
PLACEHOLDER = str(UUID(int=0))
UNDECODABLE: dict[str, Any] = {
    "content": b"{not json",
    "headers": {"Content-Type": "application/json"},
}
# What a caller can send where a JSON body is expected: one that decodes, one that does not, one
# of another media type, and nothing.
BODIES: dict[str, dict[str, Any]] = {
    "decodable": {"json": {}},
    "undecodable": UNDECODABLE,
    "another media type": {"content": b"a=1", "headers": {"Content-Type": "text/plain"}},
    "none": {},
}
CONTRACTS = "/api/v1/contracts"
FILES = "/api/v1/files"
ME = "/api/v1/me"
PREFERENCES = "/api/v1/me/preferences"
OPERATOR_PREFIX = "/api/v1/operator/"
PROBE = "/api/v1/__probe__/end-then-ask"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    application = create_app(app_settings, clock=clock)
    stamp_test_release()  # a command names the engine release, as the app's startup stamps it
    application.state.engine_release = current_release()
    return application


def answer(response: HttpResponse) -> str:
    """``<status> <problem slug>`` of a response, for a table of answers a failure can show."""
    try:
        kind = str(response.json().get("type", "")).removeprefix(PROBLEM_BASE)
    except ValueError:
        kind = "no-json"
    return f"{response.status_code} {kind}"


def operations_that_change_something(app: FastAPI) -> Iterator[tuple[str, str, bool]]:
    """(method, path, whether the route asks a session question) of every operation of the
    application that is no read, the mocks apart."""
    for route in iter_route_contexts(app.routes):
        original = route.original_route
        path = route.path or ""
        if not isinstance(original, APIRoute) or path.startswith(MOCK_PREFIX):
            continue
        asks = bool(session_questions(original.dependant))
        for method in sorted(set(route.methods or ()) - READS):
            yield method, path, asks


def url_of(path: str) -> str:
    return re.sub(r"\{[^}]+\}", PLACEHOLDER, path)


def test_auth_before_body_1_a_caller_without_a_session_is_answered_401_whatever_the_body(
    app: FastAPI,
) -> None:
    """Every operation that changes something and asks a session question answers a caller
    without a session 401 — for a body that decodes, one that does not, one of another media
    type and none; and so it answers a cookie that names no session and a bearer token that
    names no client. Before the rule 180 of them answered 422 for the body that does not
    decode."""
    operations = sorted(set(operations_that_change_something(app)))
    guarded = [(method, path) for method, path, asks in operations if asks]
    assert len(guarded) > 200, len(guarded)
    assert ("POST", CONTRACTS) in guarded and ("POST", FILES) in guarded

    other: dict[str, str] = {}
    for method, path in guarded:
        for name, body in BODIES.items():
            got = answer(call(app, method, url_of(path), **body))
            if got != "401 unauthenticated":
                other[f"{method} {path} [{name}]"] = got
    assert other == {}

    # A credential that names nobody is no session either: it is refused before the body, as
    # the guard refuses it — 401, and 403 where a bearer token meets an operator route, which
    # takes a cookie session only (DG-KRN-TEN-05).
    strangers = {
        "a cookie that names no session": {"Cookie": f"{sessions.COOKIE_NAME}=nobody"},
        "a bearer token that names no client": {"Authorization": "Bearer nobody"},
    }
    refused: Counter[str] = Counter()
    forbidden: set[str] = set()
    for method, path in guarded:
        for name, credential in strangers.items():
            headers = {**UNDECODABLE["headers"], **credential}
            got = call(app, method, url_of(path), content=UNDECODABLE["content"], headers=headers)
            refused[f"{name}: {answer(got)}"] += 1
            if got.status_code == 403:
                forbidden.add(f"{name}: {path}")
    assert set(refused) <= {
        "a cookie that names no session: 401 unauthenticated",
        "a bearer token that names no client: 401 unauthenticated",
        "a bearer token that names no client: 403 forbidden",
    }, refused
    assert forbidden and all(
        entry.startswith(f"a bearer token that names no client: {OPERATOR_PREFIX}")
        for entry in forbidden
    ), forbidden


def test_auth_before_body_1_an_operation_without_a_guard_still_reads_its_body(
    app: FastAPI,
) -> None:
    """Positive control: the operations that ask no session question are the API-C-01 routes,
    and the six of the sign-in surface that take a JSON body still judge it — 422 for one that
    does not decode. The rule moved nothing for a route without a guard."""
    unguarded = {
        (method, path) for method, path, asks in operations_that_change_something(app) if not asks
    }
    assert {path for _, path in unguarded} <= PUBLIC_PATHS
    judged = {
        f"{method} {path}": answer(call(app, method, url_of(path), **UNDECODABLE))
        for method, path in sorted(unguarded)
    }
    sign_in_surface = {
        "POST /api/v1/session/login",
        "POST /api/v1/session/invitations/lookup",
        "POST /api/v1/session/accept-invitation",
        "POST /api/v1/session/password-reset",
        "POST /api/v1/session/password-reset/confirm",
        "POST /api/v1/oauth/token",
    }
    assert sign_in_surface <= set(judged)
    assert {judged[operation] for operation in sign_in_surface} == {"422 validation-failed"}


@pytest.fixture
def lena(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """A Revenue Accountant: she may upload an import source."""
    someone = member(keyring, clock)
    assign(someone, "revenue_accountant")
    return enrolled(app, clock, someone)


def test_auth_before_body_1_a_signed_in_callers_body_is_still_judged(
    app: FastAPI, lena: Actor
) -> None:
    """Positive control: the guard in front changes nothing for a caller who has a session — a
    body that does not decode is 422 ``validation-failed``, as before."""
    refused = call(
        app,
        "POST",
        CONTRACTS,
        content=UNDECODABLE["content"],
        headers={**UNDECODABLE["headers"], **cookie_headers(lena.token, lena.csrf_token)},
    )
    assert answer(refused) == "422 validation-failed", refused.text


@contextmanager
def session_lookups() -> Iterator[list[str]]:
    """The statements the process sends, while the block runs, that look a session up by its
    token (``sessions._find``): what a session question costs the identity store."""
    seen: list[str] = []

    def capture(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        text = " ".join(statement.split())
        if text.upper().startswith("SELECT") and "user_session" in text and "token_sha256" in text:
            seen.append(text)

    event.listen(Engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


def test_auth_before_body_1_the_identity_store_is_asked_once_a_request(
    app: FastAPI, lena: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route class asks the session question before the body and FastAPI asks it again when
    it solves the dependencies; the upload route asks a third time, in ``admit_upload``. For a
    request whose body arrives with its headers the store answers once: a JSON command, a read
    and ``POST /files`` each call ``sessions.authenticate`` one time and send one statement
    that looks the session up (``POST /files`` sent two before the rule)."""
    asked: list[str] = []
    real = sessions.authenticate

    def counted(token: str, **kwargs: Any) -> Any:
        asked.append(token)
        return real(token, **kwargs)

    monkeypatch.setattr(sessions, "authenticate", counted)
    headers = cookie_headers(lena.token, lena.csrf_token)

    with session_lookups() as lookups:
        command = call(
            app, "PATCH", PREFERENCES, json={"shortcuts_enabled": False}, headers=headers
        )
    assert command.status_code == 200, command.text
    assert (asked, len(lookups)) == ([lena.token], 1)

    asked.clear()
    with session_lookups() as lookups:
        read = call(app, "GET", ME, headers=cookie_headers(lena.token, key=False))
    assert read.status_code == 200, read.text
    assert (asked, len(lookups)) == ([lena.token], 1)

    asked.clear()
    with session_lookups() as lookups:
        upload = call(
            app,
            "POST",
            FILES,
            data={"purpose": "IMPORT_SOURCE"},
            files={"file": ("orders.csv", b"code,name\nC-1,One\n", "text/csv")},
            headers=cookie_headers(lena.token, lena.csrf_token),
        )
    assert upload.status_code == 201, upload.text
    assert (asked, len(lookups)) == ([lena.token], 1)


# --- a body that takes its time ---------------------------------------------------------------


def slowly(body: bytes, between: Callable[[], None]) -> AsyncIterator[bytes]:
    """``body`` in two parts. ``between`` runs when the application asks for the second part —
    after it has read the first, and so after the session question in front of the body."""

    async def parts() -> AsyncIterator[bytes]:
        half = len(body) // 2
        yield body[:half]
        between()
        yield body[half:]

    return parts()


def signed_in(app: FastAPI, keyring: KeyRing, clock: FrozenClock, name: str) -> Actor:
    someone = member(keyring, clock, name=name)
    assign(someone, "revenue_accountant")
    return enrolled(app, clock, someone)


def ended(actor: Actor, keyring: KeyRing, clock: FrozenClock) -> Callable[[], None]:
    """End the session of ``actor`` in the identity store, as a sign-out elsewhere does."""

    def end() -> None:
        facts = RequestFacts(
            request_id="tests-slow-body", source_ip=None, user_agent=None, now=clock.now()
        )
        auth = sessions.authenticate(actor.token, facts=facts, keyring=keyring, csrf=None)
        sessions.sign_out(auth, keyring=keyring)

    return end


def shortcuts_of(actor: Actor) -> object:
    with identity_session(request_id="tests-slow-body-read") as db:
        preferences = db.execute(
            select(app_user.c.preferences).where(app_user.c.id == actor.member.user_id)
        ).scalar_one()
    return preferences.get("shortcuts_enabled")


def patch_slowly(app: FastAPI, actor: Actor, between: Callable[[], None]) -> HttpResponse:
    body = json.dumps({"shortcuts_enabled": False}).encode()
    headers = {
        **cookie_headers(actor.token, actor.csrf_token),
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    return call(app, "PATCH", PREFERENCES, content=slowly(body, between), headers=headers)


def test_auth_before_body_1_a_kept_answer_does_not_outlive_a_slow_body(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The question moved in front of the body; the check must not move away from the command.
    What the store answered is kept for one second of the application clock (``KEPT_FOR``). A
    body that takes longer is followed by a second question: a session ended while the body
    arrived is refused when the command starts — 401, nothing changed — as it was while the
    guard ran after the body. Positive control: the same slow body with the session alive is
    served, and the store was asked twice. Stated, not closed: within the second a session
    ended beside the request does not stop it — the race between a guard and its handler,
    bounded at a second."""
    second = timedelta(seconds=2)

    # Ended while the body arrived, and the body took its time: refused when the command starts.
    ada = signed_in(app, keyring, clock, "ada")
    end_ada = ended(ada, keyring, clock)

    def ended_and_late() -> None:
        end_ada()
        clock.advance(second)

    refused = patch_slowly(app, ada, ended_and_late)
    assert answer(refused) == "401 unauthenticated", refused.text
    assert shortcuts_of(ada) is None

    # Positive control: alive, and the body took its time — served, and asked twice.
    ben = signed_in(app, keyring, clock, "ben")
    with session_lookups() as lookups:
        served = patch_slowly(app, ben, lambda: clock.advance(second))
    assert served.status_code == 200, served.text
    assert shortcuts_of(ben) is False
    assert len(lookups) == 2

    # Stated: ended within the second — the kept answer serves, the command runs.
    cy = signed_in(app, keyring, clock, "cy")
    within = patch_slowly(app, cy, ended(cy, keyring, clock))
    assert within.status_code == 200, within.text
    assert shortcuts_of(cy) is False


def test_auth_before_body_1_an_upload_whose_session_ended_stores_nothing(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """``POST /files`` asked the session before its body since ruling R-111 (8) and again when
    the command started. The second question is now answered from the first within
    ``KEPT_FOR`` — and asked of the store after it: an upload whose session ended while the
    form arrived stores nothing."""
    dana = signed_in(app, keyring, clock, "dana")
    boundary = "erev-slow-upload"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\n'
        f"IMPORT_SOURCE\r\n"
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="orders.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\ncode,name\nC-1,One\n\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    headers = {
        **cookie_headers(dana.token, dana.csrf_token),
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    end_dana = ended(dana, keyring, clock)

    def ended_and_late() -> None:
        end_dana()
        clock.advance(timedelta(seconds=2))

    refused = call(app, "POST", FILES, content=slowly(body, ended_and_late), headers=headers)
    assert answer(refused) == "401 unauthenticated", refused.text
    ctx = DbContext(tenant_id=dana.member.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        stored = session.execute(select(func.count()).select_from(file_object)).scalar_one()
    assert stored == 0


# --- a handler that ends the session it was called with -----------------------------------------


def test_auth_before_body_1_a_guard_asked_after_the_session_ended_reads_the_stores_refusal(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    """A rotation and the sign-out end the presented session inside the handler, milliseconds
    after the guard answered. Such a handler drops the kept answer (``forget_session``), so a
    guard asked later in the same request asks the identity store and reads its refusal of the
    ended session: 401. No handler of the application asks a guard after it ended its session —
    each answers from the successor the rotation returned, and
    ``tests/architecture/test_routes.py`` holds the five to their forgetting; the probe route
    here does ask, to show what it reads. Its twin does not forget, and is served the answer
    of a session that no longer exists: what the rule is for."""
    application = create_app(app_settings, clock=clock)

    def end_then_ask(*, forget: bool) -> Any:
        def handler(
            request: Request,
            auth: Annotated[AuthenticatedSession, Depends(require_authenticated(tenant=False))],
        ) -> dict[str, str]:
            sessions.sign_out(auth, keyring=request.app.state.keyring)
            if forget:
                forget_session(request)
            asked_again = authenticate_session(request, clock)
            return {"session": str(asked_again.session.id)}

        return handler

    application.post(f"{PROBE}/forgetting")(end_then_ask(forget=True))
    application.post(f"{PROBE}/keeping")(end_then_ask(forget=False))

    def ended_at(actor: Actor) -> object:
        with identity_session(request_id="tests-end-then-ask") as db:
            return db.execute(
                select(user_session.c.ended_at).where(
                    user_session.c.token_sha256 == sessions.sha256_hex(actor.token)
                )
            ).scalar_one()

    ada = signed_in(application, keyring, clock, "ada")
    refused = call(
        application,
        "POST",
        f"{PROBE}/forgetting",
        headers=cookie_headers(ada.token, ada.csrf_token),
    )
    assert answer(refused) == "401 unauthenticated", refused.text
    assert ended_at(ada) is not None

    ben = signed_in(application, keyring, clock, "ben")
    served = call(
        application, "POST", f"{PROBE}/keeping", headers=cookie_headers(ben.token, ben.csrf_token)
    )
    assert served.status_code == 200, served.text
    assert ended_at(ben) is not None  # the session is ended, and its kept answer was served
