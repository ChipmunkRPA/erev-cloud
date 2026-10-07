"""API-R-03 password change (04 §16.12; 05 SAR-10; SCREENS_B §12.3; BUILD_SPEC PLF-15)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from typing import Any

import pytest
from erev_api.auth import sessions
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import identity_session
from erev_api.db.tables import app_user, security_event, user_session
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    LOGIN,
    PASSWORD,
    cookie_headers,
    cookie_of,
    member,
    select_tenant,
    sign_in,
    workspace,
)

PASSWORD_PATH = "/api/v1/me/password"
ME_PATH = "/api/v1/me"
NEW_PASSWORD_VALUE = "Oskar!Ledger2027"
WRONG_CURRENT = "Lena!Revenue2027"


async def _start(application: FastAPI) -> None:
    async with application.router.lifespan_context(application):
        pass


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    """The app after its lifespan startup, so ``GET /me`` serves the stamped release."""
    application = create_app(app_settings, clock=clock)
    asyncio.run(_start(application))
    return application


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).rsplit("/", 1)[1]


def session_row(token: str) -> Mapping[str, Any]:
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with identity_session(request_id="tests-me-password-session") as db:
        return (
            db.execute(select(user_session).where(user_session.c.token_sha256 == digest))
            .mappings()
            .one()
        )


def test_change_password(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    lena = member(keyring, clock)
    other = sign_in(app, lena.email)
    # The presented session has the workspace open, so GET /me answers for it (API-R-03).
    current = workspace(app, lena, sign_in(app, lena.email))
    headers = cookie_headers(current.token, current.csrf_token)

    wrong = call(
        app,
        "POST",
        PASSWORD_PATH,
        json={"current_password": WRONG_CURRENT, "new_password": NEW_PASSWORD_VALUE},
        headers=headers,
    )
    assert (wrong.status_code, slug(wrong)) == (422, "validation-failed"), wrong.text
    assert wrong.json()["errors"][0]["field"] == "current_password"
    assert wrong.json()["errors"][0]["message"] == "The current password is incorrect."

    weak = call(
        app,
        "POST",
        PASSWORD_PATH,
        json={"current_password": PASSWORD, "new_password": lena.email},
        headers=cookie_headers(current.token, current.csrf_token),
    )
    assert (weak.status_code, slug(weak)) == (422, "password-policy"), weak.text
    assert weak.json()["detail"] == "The password cannot be your email address."

    changed = call(
        app,
        "POST",
        PASSWORD_PATH,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD_VALUE},
        headers=cookie_headers(current.token, current.csrf_token),
    )
    assert (changed.status_code, changed.content) == (204, b""), changed.text
    # D-80 (PR-A-03): the user stays signed in under a rotated token (05 SAR-09).
    rotated = cookie_of(changed)
    assert rotated != current.token
    presented = call(app, "GET", ME_PATH, headers={"Cookie": f"erev_session={current.token}"})
    assert (presented.status_code, slug(presented)) == (401, "unauthenticated"), presented.text
    assert session_row(current.token)["end_reason"] == "REVOKED"
    renewed = call(app, "GET", ME_PATH, headers={"Cookie": f"erev_session={rotated}"})
    assert renewed.status_code == 200, renewed.text
    assert session_row(other.token)["end_reason"] == "PASSWORD_CHANGED"

    with identity_session(request_id="tests-me-password-events") as db:
        events = db.execute(
            select(security_event.c.kind, security_event.c.session_id)
            .where(
                security_event.c.user_id == lena.user_id,
                security_event.c.kind == "PASSWORD_CHANGED",
            )
            .order_by(security_event.c.chain_seq)
        ).all()
        changed_at = db.execute(
            select(app_user.c.password_changed_at).where(app_user.c.id == lena.user_id)
        ).scalar_one()
    assert [tuple(event) for event in events] == [("PASSWORD_CHANGED", session_row(rotated)["id"])]
    assert changed_at == clock.now()
    old = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert old.status_code == 401
    assert sign_in(app, lena.email, NEW_PASSWORD_VALUE).body["authenticated"] is True


def test_sar_10_a_rotation_in_flight_does_not_outlive_a_password_change(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 and SAR-10 rev 1.178 (item SESSION-ROTATION-END-1). A password change ends every
    other session of the identity. A request of one of them that was past its authentication
    when the password changed went on, rotated its session and left an open successor - a
    session the person who changed the password had not ended. The rotation finds its session
    ended: 401, and only the session that changed the password is open afterwards."""
    lena = member(keyring, clock)
    other = sign_in(app, lena.email)
    current = workspace(app, lena, sign_in(app, lena.email))
    marked = sessions._mark_opened  # noqa: SLF001 - between the authentication and the rotation
    changed: list[HttpResponse] = []

    def changing(facts: Any, **arguments: Any) -> None:
        marked(facts, **arguments)
        # The password changes in the other request's own thread, before it rotates its session.
        changed.append(
            call(
                app,
                "POST",
                PASSWORD_PATH,
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD_VALUE},
                headers=cookie_headers(current.token, current.csrf_token),
            )
        )

    monkeypatch.setattr(sessions, "_mark_opened", changing)
    refused = select_tenant(app, other, lena.tenant_id)
    (done,) = changed
    assert (done.status_code, done.content) == (204, b""), done.text
    assert refused.status_code == 401, refused.text
    assert slug(refused) == "unauthenticated"
    assert "set-cookie" not in refused.headers
    assert session_row(other.token)["end_reason"] == "PASSWORD_CHANGED"
    renewed = session_row(cookie_of(done))["id"]
    with identity_session(request_id="tests-me-password-open") as db:
        still_open = list(
            db.execute(
                select(user_session.c.id).where(
                    user_session.c.user_id == lena.user_id, user_session.c.ended_at.is_(None)
                )
            ).scalars()
        )
    assert still_open == [renewed]


def test_wrong_current_password_locks_and_expiry_restarts_count(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    current = workspace(app, lena, sign_in(app, lena.email))

    def change(password: str, new: str = NEW_PASSWORD_VALUE) -> HttpResponse:
        return call(
            app,
            "POST",
            PASSWORD_PATH,
            json={"current_password": password, "new_password": new},
            headers=cookie_headers(current.token, current.csrf_token),
        )

    for expected in (422, 422, 422, 422, 423):
        answer = change(WRONG_CURRENT)
        assert answer.status_code == expected, answer.text
    locked = change(PASSWORD)
    assert (locked.status_code, slug(locked)) == (423, "account-locked")
    with identity_session(request_id="tests-change-lockout") as db:
        row = db.execute(select(app_user).where(app_user.c.id == lena.user_id)).mappings().one()
        assert row["failed_login_count"] == 5
        assert row["locked_until"] == clock.now() + sessions.LOCKOUT
        events = db.execute(
            select(security_event.c.kind, security_event.c.detail)
            .where(
                security_event.c.user_id == lena.user_id,
                security_event.c.kind.in_(["LOGIN_FAILED", "ACCOUNT_LOCKED", "PASSWORD_CHANGED"]),
            )
            .order_by(security_event.c.chain_seq)
        ).all()
    assert [kind for kind, _ in events] == ["LOGIN_FAILED"] * 5 + ["ACCOUNT_LOCKED"]
    assert [detail["failed_login_count"] for kind, detail in events if kind == "LOGIN_FAILED"] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert all(
        detail.get("purpose") == "password_change"
        for kind, detail in events
        if kind == "LOGIN_FAILED"
    )
    clock.advance(sessions.LOCKOUT)
    assert change(WRONG_CURRENT).status_code == 422
    with identity_session(request_id="tests-change-expired-lock") as db:
        assert db.execute(
            select(app_user.c.failed_login_count, app_user.c.locked_until).where(
                app_user.c.id == lena.user_id
            )
        ).one() == (1, None)
    # A correct current password breaks consecutive failures even if the proposed password
    # is rejected by policy. That rejection must not roll back the successful verification.
    assert change(PASSWORD, lena.email).status_code == 422
    with identity_session(request_id="tests-change-correct-check") as db:
        assert (
            db.execute(
                select(app_user.c.failed_login_count).where(app_user.c.id == lena.user_id)
            ).scalar_one()
            == 0
        )
    changed = change(PASSWORD)
    assert changed.status_code == 204, changed.text
    assert sign_in(app, lena.email, NEW_PASSWORD_VALUE).body["authenticated"] is True


def test_concurrent_password_changes_share_the_login_failure_budget(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    lena = member(keyring, clock)
    current = workspace(app, lena, sign_in(app, lena.email))
    for _ in range(3):
        assert (
            call(
                app, "POST", LOGIN, json={"email": lena.email, "password": WRONG_CURRENT}
            ).status_code
            == 401
        )
    ready = Barrier(2)

    def attempt() -> int:
        ready.wait(timeout=10)
        return call(
            app,
            "POST",
            PASSWORD_PATH,
            json={"current_password": WRONG_CURRENT, "new_password": NEW_PASSWORD_VALUE},
            headers=cookie_headers(current.token, current.csrf_token),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(answers) == [422, 423]
    with identity_session(request_id="tests-change-concurrent-budget") as db:
        assert (
            db.execute(
                select(app_user.c.failed_login_count).where(app_user.c.id == lena.user_id)
            ).scalar_one()
            == 5
        )
    assert (
        call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD}).status_code
        == 423
    )
