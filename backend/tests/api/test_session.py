"""API-R-01 Session (04 §16.12; 05 SAR-06, SAR-09 to SAR-11, SAR-13; BUILD_SPEC PLF-2, BS1-D-30)."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

import pytest
from erev_api.auth import passwords, sessions
from erev_api.auth.dependencies import require_authenticated
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import app_user, security_event, tenant_membership, user_session
from erev_api.main import create_app
from fastapi import Depends, FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpResponse, call
from support.plans import sent
from support.principals import (
    LOGIN,
    PASSWORD,
    TENANT,
    Signed,
    cookie_headers,
    cookie_of,
    member,
    select_tenant,
    sign_in,
)
from support.rows import insert_active_membership

WRONG_PASSWORD = "Lena!Revenue2027"
SESSION = "/api/v1/session"
NOTIFICATIONS = "/api/v1/me/notifications"
LOGOUT = "/api/v1/session/logout"
LOCKED_COPY = (
    "Too many failed sign-in attempts. Try again in 15 minutes or ask a workspace administrator."
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def event_kinds(user_id: UUID) -> list[str]:
    with identity_session(request_id="tests-session-events") as db:
        rows = db.execute(
            select(security_event.c.kind)
            .where(security_event.c.user_id == user_id)
            .order_by(security_event.c.chain_seq)
        ).scalars()
        return [str(kind) for kind in rows]


def sessions_of(user_id: UUID) -> list[Mapping[str, Any]]:
    with identity_session(request_id="tests-session-rows") as db:
        return list(
            db.execute(
                select(user_session)
                .where(user_session.c.user_id == user_id)
                .order_by(user_session.c.created_at, user_session.c.id)
            ).mappings()
        )


def session_row(token: str) -> Mapping[str, Any]:
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with identity_session(request_id="tests-session-row") as db:
        return (
            db.execute(select(user_session).where(user_session.c.token_sha256 == digest))
            .mappings()
            .one()
        )


def user_row(user_id: UUID) -> Mapping[str, Any]:
    with identity_session(request_id="tests-session-user") as db:
        return db.execute(select(app_user).where(app_user.c.id == user_id)).mappings().one()


def problem_slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).rsplit("/", 1)[1]


def second_workspace(keyring: KeyRing, clock: FrozenClock, user_id: UUID) -> UUID:
    """A workspace where ``user_id`` holds another ACTIVE membership; sign-in opens none (D-83)."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
        insert_active_membership(db, tenant_id=tenant_id, user_id=user_id)
    return tenant_id


def test_login_sets_cookie_and_returns_csrf(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    response = call(app, "POST", LOGIN, json={"email": lena.email.upper(), "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", body["csrf_token"])
    assert body["mfa_required"] is False
    assert body["mfa_enrolment_required"] is False
    assert body["user"] == {
        "id": str(lena.user_id),
        "email": lena.email,
        "display_name": lena.email,
    }
    # D-83: her only ACTIVE membership opens with the session.
    assert body["active_tenant"]["id"] == str(lena.tenant_id)
    token = cookie_of(response)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    assert response.headers["set-cookie"] == f"erev_session={token}; HttpOnly; Path=/; SameSite=Lax"
    row = session_row(token)
    assert row["token_sha256"] == hashlib.sha256(token.encode("ascii")).hexdigest()
    assert (
        row["csrf_token_sha256"] == hashlib.sha256(body["csrf_token"].encode("ascii")).hexdigest()
    )
    assert row["auth_method"] == "password"
    assert row["idle_expires_at"] == clock.now() + timedelta(minutes=30)
    assert row["absolute_expires_at"] == clock.now() + timedelta(hours=12)
    assert event_kinds(lena.user_id) == ["LOGIN_SUCCEEDED", "TENANT_SELECTED"]
    assert user_row(lena.user_id)["last_login_at"] == clock.now()

    again = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"})
    assert again.status_code == 200
    assert again.json()["csrf_token"] == body["csrf_token"]


def test_d83_sign_in_opens_the_only_active_membership(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    # An INVITED membership of another workspace does not count; only ACTIVE memberships do.
    tenant_factory(keyring=keyring, clock=clock, admin_email=lena.email)
    response = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_tenant"]["id"] == str(lena.tenant_id)
    assert body["active_tenant"]["kind"] == "production"
    assert body["active_tenant"]["code"].startswith("t-")
    assert response.headers["X-Erev-Tenant-Kind"] == "production"

    token = cookie_of(response)
    row = session_row(token)
    assert row["active_tenant_id"] == lena.tenant_id
    assert row["idle_expires_at"] == clock.now() + timedelta(minutes=30)
    assert event_kinds(lena.user_id) == ["LOGIN_SUCCEEDED", "TENANT_SELECTED"]
    with identity_session(request_id="tests-session-d83-open", user_id=lena.user_id) as db:
        selected = db.execute(
            select(security_event.c.tenant_id, security_event.c.session_id).where(
                security_event.c.user_id == lena.user_id,
                security_event.c.kind == "TENANT_SELECTED",
            )
        ).one()
        opened_at = db.execute(
            select(tenant_membership.c.last_opened_at).where(
                tenant_membership.c.id == lena.membership_id
            )
        ).scalar_one()
    assert (selected.tenant_id, selected.session_id) == (lena.tenant_id, row["id"])
    assert opened_at == clock.now()

    # The session acts in the workspace at once, without POST /session/tenant.
    notifications = call(app, "GET", NOTIFICATIONS, headers=cookie_headers(token, key=False))
    assert notifications.status_code == 200, notifications.text
    current = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"}).json()
    assert current["active_tenant"]["id"] == str(lena.tenant_id)


def test_d83_sign_in_with_several_active_memberships_opens_none(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    other = second_workspace(keyring, clock, lena.user_id)
    response = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_tenant"] is None
    assert "X-Erev-Tenant-Kind" not in response.headers

    token = cookie_of(response)
    assert session_row(token)["active_tenant_id"] is None
    assert event_kinds(lena.user_id) == ["LOGIN_SUCCEEDED"]
    with identity_session(request_id="tests-session-d83-none", user_id=lena.user_id) as db:
        opened = list(
            db.execute(
                select(tenant_membership.c.last_opened_at).where(
                    tenant_membership.c.user_id == lena.user_id
                )
            ).scalars()
        )
    assert opened == [None, None]

    # Tenant routes still need a workspace; the client shows workspace selection instead.
    notifications = call(app, "GET", NOTIFICATIONS, headers=cookie_headers(token, key=False))
    assert (notifications.status_code, problem_slug(notifications)) == (401, "unauthenticated")
    signed = Signed(token=token, csrf_token=body["csrf_token"], body=body)
    chosen = select_tenant(app, signed, other)
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["active_tenant"]["id"] == str(other)


@pytest.mark.control("CTL-033")
def test_ctl_033_lockout_after_five_failures(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    statuses = [
        call(app, "POST", LOGIN, json={"email": lena.email, "password": WRONG_PASSWORD}).status_code
        for _ in range(5)
    ]
    assert statuses == [401, 401, 401, 401, 423]
    assert Counter(event_kinds(lena.user_id)) == Counter({"LOGIN_FAILED": 5, "ACCOUNT_LOCKED": 1})

    locked = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert locked.status_code == 423
    assert problem_slug(locked) == "account-locked"
    assert locked.json()["detail"] == LOCKED_COPY
    assert "set-cookie" not in locked.headers
    assert user_row(lena.user_id)["locked_until"] == clock.now() + timedelta(minutes=15)
    assert sessions_of(lena.user_id) == []

    clock.advance(timedelta(minutes=15))
    unlocked = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert unlocked.status_code == 200
    assert user_row(lena.user_id)["failed_login_count"] == 0
    assert user_row(lena.user_id)["locked_until"] is None


def test_req_plt_004_a_lockout_answer_does_not_tell_whether_an_account_exists(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security review, the lead's finding 5 (ruling R-48 (e); 03 REQ-PLT-004 rev 1.66; 05 SAR-06
    rev 1.90). The fifth wrong password answered 423 ``account-locked`` only when the account
    existed; an email without one answered 401 for ever, so five attempts told an outsider which
    addresses have accounts. Both are counted and answered alike, attempt for attempt."""
    lena = member(keyring, clock)
    nobody = f"nobody-{secrets.token_hex(6)}@example.test"
    digest = hashlib.sha256(nobody.encode("ascii")).hexdigest()

    def answer(email: str, password: str = WRONG_PASSWORD) -> tuple[int, str, Any, bool]:
        response = call(app, "POST", LOGIN, json={"email": email, "password": password})
        body = response.json()
        return (
            response.status_code,
            problem_slug(response),
            body["detail"],
            "set-cookie" in response.headers,
        )

    def events_of_nobody() -> list[tuple[str, Any, Mapping[str, Any]]]:
        with identity_session(request_id="tests-session-nobody") as db:
            rows = db.execute(
                select(security_event.c.kind, security_event.c.user_id, security_event.c.detail)
                .where(security_event.c.email_sha256 == digest)
                .order_by(security_event.c.chain_seq)
            ).all()
        return [(str(kind), user_id, dict(detail)) for kind, user_id, detail in rows]

    wrong = (401, "unauthenticated", "The email or password is incorrect.", False)
    locked = (423, "account-locked", LOCKED_COPY, False)
    # Five wrong passwords, then one more attempt while the lock lasts: the same six answers.
    with_account = [answer(lena.email) for _ in range(6)]
    without_account = [answer(nobody) for _ in range(6)]
    assert with_account == [wrong] * 4 + [locked] * 2
    assert without_account == with_account

    # The count of the email without an account lives in the security log: five failures with
    # their running count, then the lock, which names its end; the locked attempt writes nothing.
    until = (clock.now() + timedelta(minutes=15)).isoformat()
    assert events_of_nobody() == [
        *(("LOGIN_FAILED", None, {"failed_login_count": count}) for count in range(1, 6)),
        ("ACCOUNT_LOCKED", None, {"lockout_minutes": 15, "locked_until": until}),
    ]
    assert Counter(event_kinds(lena.user_id)) == Counter({"LOGIN_FAILED": 5, "ACCOUNT_LOCKED": 1})

    # One second before the lock ends both are still locked; when it has ended a new run of
    # failures starts for both (the correct password would sign the account in: not tried here,
    # so that the two stay comparable).
    clock.advance(timedelta(minutes=14, seconds=59))
    assert answer(lena.email) == answer(nobody) == locked
    clock.advance(timedelta(seconds=1))
    assert [answer(lena.email) for _ in range(5)] == [wrong] * 4 + [locked]
    assert [answer(nobody) for _ in range(5)] == [wrong] * 4 + [locked]
    assert [kind for kind, _, _ in events_of_nobody()].count("ACCOUNT_LOCKED") == 2

    # Positive control: the account still signs in once its lock has ended.
    clock.advance(timedelta(minutes=15))
    signed = call(app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD})
    assert signed.status_code == 200, signed.text


@pytest.mark.control("CTL-033")
def test_ctl_033_idle_and_absolute_timeout(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    idle = sign_in(app, lena.email)
    clock.advance(timedelta(minutes=31))
    expired = select_tenant(app, idle, lena.tenant_id)
    assert expired.status_code == 401
    assert problem_slug(expired) == "session-expired"
    assert expired.json()["detail"] == (
        "Your session ended after 30 minutes without activity. Sign in again."
    )
    assert session_row(idle.token)["end_reason"] == "IDLE_TIMEOUT"
    assert event_kinds(lena.user_id).count("SESSION_EXPIRED") == 1

    active = sign_in(app, lena.email)
    started = clock.now()
    for step in range(1, 36):
        clock.set(started + timedelta(minutes=20 * step))
        still = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={active.token}"})
        assert still.json()["authenticated"] is True, step
    clock.set(started + timedelta(hours=12, minutes=1))
    absolute = select_tenant(app, active, lena.tenant_id)
    assert absolute.status_code == 401
    assert problem_slug(absolute) == "session-expired"
    assert session_row(active.token)["end_reason"] == "ABSOLUTE_TIMEOUT"
    assert event_kinds(lena.user_id).count("SESSION_EXPIRED") == 2


def test_logout_invalidates_session_server_side(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    signed = sign_in(app, lena.email)
    response = call(app, "POST", LOGOUT, headers=cookie_headers(signed.token, signed.csrf_token))
    assert response.status_code == 204
    assert response.content == b""
    assert (
        response.headers["set-cookie"] == "erev_session=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"
    )
    row = session_row(signed.token)
    assert row["end_reason"] == "LOGOUT"
    assert row["ended_at"] == clock.now()
    assert row["expires_at"] == clock.now() + timedelta(days=30)
    assert event_kinds(lena.user_id) == ["LOGIN_SUCCEEDED", "TENANT_SELECTED", "LOGOUT"]

    replay = call(app, "POST", LOGOUT, headers=cookie_headers(signed.token, signed.csrf_token))
    assert replay.status_code == 401
    assert problem_slug(replay) == "unauthenticated"
    assert replay.json()["detail"] == "Sign in to continue."
    anonymous = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={signed.token}"})
    assert anonymous.json()["authenticated"] is False


def test_krn_auth_02_csrf_and_origin(
    app: FastAPI, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    signed = sign_in(app, lena.email)
    body = {"tenant_id": str(lena.tenant_id)}
    without_token = call(app, "POST", TENANT, json=body, headers=cookie_headers(signed.token))
    assert without_token.status_code == 403
    assert problem_slug(without_token) == "forbidden"
    assert without_token.json()["errors"][0]["rule_id"] == "API-C-02"

    wrong_origin = call(
        app,
        "POST",
        TENANT,
        json=body,
        headers=cookie_headers(signed.token, signed.csrf_token, Origin="http://127.0.0.1:9999"),
    )
    assert wrong_origin.status_code == 403
    assert wrong_origin.json()["errors"][0]["rule_id"] == "API-C-02"

    forged = call(app, "POST", TENANT, json=body, headers=cookie_headers(signed.token, "x" * 43))
    assert forged.status_code == 403
    assert session_row(signed.token)["ended_at"] is None

    same_origin = call(
        app,
        "POST",
        TENANT,
        json=body,
        headers=cookie_headers(signed.token, signed.csrf_token, Origin=app_settings.public_origin),
    )
    assert same_origin.status_code == 200

    login_elsewhere = call(
        app,
        "POST",
        LOGIN,
        json={"email": lena.email, "password": PASSWORD},
        headers={"Origin": "http://127.0.0.1:9999"},
    )
    assert login_elsewhere.status_code == 403
    assert login_elsewhere.json()["errors"][0]["rule_id"] == "API-C-02"


def test_sar_09_tenant_selection_rotates_token(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    second_workspace(keyring, clock, lena.user_id)
    signed = sign_in(app, lena.email)
    clock.advance(timedelta(minutes=5))
    response = select_tenant(app, signed, lena.tenant_id)
    assert response.status_code == 200
    body = response.json()
    rotated = cookie_of(response)
    assert rotated != signed.token
    assert body["csrf_token"] != signed.csrf_token
    assert body["active_tenant"]["id"] == str(lena.tenant_id)
    assert body["active_tenant"]["kind"] == "production"
    assert response.headers["X-Erev-Tenant-Kind"] == "production"

    previous, current = session_row(signed.token), session_row(rotated)
    assert previous["end_reason"] == "REVOKED"
    assert current["active_tenant_id"] == lena.tenant_id
    assert current["absolute_expires_at"] == previous["absolute_expires_at"]
    assert event_kinds(lena.user_id) == ["LOGIN_SUCCEEDED", "TENANT_SELECTED"]
    with identity_session(request_id="tests-session-selected", user_id=lena.user_id) as db:
        selected_event = db.execute(
            select(security_event.c.tenant_id, security_event.c.session_id).where(
                security_event.c.user_id == lena.user_id,
                security_event.c.kind == "TENANT_SELECTED",
            )
        ).one()
        opened_at = db.execute(
            select(tenant_membership.c.last_opened_at).where(
                tenant_membership.c.id == lena.membership_id
            )
        ).scalar_one()
    assert selected_event.tenant_id == lena.tenant_id
    assert selected_event.session_id == current["id"]
    assert opened_at == clock.now()

    later = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={rotated}"})
    assert later.headers["X-Erev-Tenant-Kind"] == "production"
    assert later.json()["active_tenant"]["code"].startswith("t-")
    old_cookie = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={signed.token}"})
    assert old_cookie.json()["authenticated"] is False
    assert "X-Erev-Tenant-Kind" not in old_cookie.headers

    other = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    current_signed = Signed(token=rotated, csrf_token=body["csrf_token"], body=body)
    not_member = select_tenant(app, current_signed, other)
    assert not_member.status_code == 404
    assert problem_slug(not_member) == "not-found"
    assert session_row(rotated)["ended_at"] is None


def test_sar_09_a_rotation_takes_the_identity_then_ends_the_session_it_was_given(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; dev-guide DG-KRN-AUTH-08): a rotation
    holds the identity's row before it touches a session - the row every act that ends an
    identity's sessions holds - and ends the session it was given before it opens the successor.
    The order is read from the statements the request sent."""
    lena = member(keyring, clock)
    signed = sign_in(app, lena.email)
    with sent() as statements:
        response = select_tenant(app, signed, lena.tenant_id)
    assert response.status_code == 200, response.text
    texts = [statement for statement, _ in statements]
    holds = [
        n
        for n, text in enumerate(texts)
        if "FROM erev.app_user" in text and "FOR NO KEY UPDATE" in text
    ]
    ends = [
        n
        for n, text in enumerate(texts)
        if text.startswith("UPDATE erev.user_session") and "end_reason" in text
    ]
    opens = [n for n, text in enumerate(texts) if text.startswith("INSERT INTO erev.user_session")]
    assert (len(holds), len(ends), len(opens)) == (1, 1, 1), texts
    assert holds[0] < ends[0] < opens[0]


def test_sar_09_a_session_that_ended_after_its_request_was_authenticated_has_no_successor(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1). A request is authenticated in a
    transaction of its own, and a rotation opened the successor of whatever session the request
    had presented: a session that was signed out, or rotated by another request, between the two
    left an open session behind. Here the session ends inside the request, after its
    authentication and before its rotation - once by a sign-out, once by another rotation of the
    same session: the rotation answers 401 and opens nothing."""
    lena = member(keyring, clock)
    marked = sessions._mark_opened  # noqa: SLF001 - between the authentication and the rotation
    between: list[Callable[[], None]] = []

    def then(facts: Any, **arguments: Any) -> None:
        marked(facts, **arguments)
        if between:
            between.pop()()

    monkeypatch.setattr(sessions, "_mark_opened", then)

    signed = sign_in(app, lena.email)

    def signing_out() -> None:
        left = call(app, "POST", LOGOUT, headers=cookie_headers(signed.token, signed.csrf_token))
        assert left.status_code == 204, left.text

    between.append(signing_out)
    refused = select_tenant(app, signed, lena.tenant_id)
    assert refused.status_code == 401, refused.text
    assert problem_slug(refused) == "unauthenticated"
    assert refused.json()["detail"] == "Sign in to continue."
    assert "set-cookie" not in refused.headers
    assert Counter(row["end_reason"] for row in sessions_of(lena.user_id)) == Counter({"LOGOUT": 1})

    # Two requests present one session: the one that rotates it first has the successor.
    again = sign_in(app, lena.email)
    others: list[HttpResponse] = []
    between.append(lambda: others.append(select_tenant(app, again, lena.tenant_id)))
    refused = select_tenant(app, again, lena.tenant_id)
    (first,) = others
    assert first.status_code == 200, first.text
    assert refused.status_code == 401, refused.text
    assert problem_slug(refused) == "unauthenticated"
    assert "set-cookie" not in refused.headers
    assert Counter(row["end_reason"] for row in sessions_of(lena.user_id)) == Counter(
        {"LOGOUT": 1, "REVOKED": 1, None: 1}
    )
    assert session_row(cookie_of(first))["ended_at"] is None


def test_sar_09_a_password_step_holds_the_identity_without_its_key_and_before_the_chain(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 rev 1.178 (item AUTH-LOCK-ORDER-1; dev-guide DG-KRN-AUTH-08).
    A password step locks the identity's row, and it locked it with its key: every event that
    names the member - a sign-out, an expiry, a refused code - then waited for the row at its
    foreign key, holding the security chain's lock the password step asks for next. The row is
    held without its key, before the chain's lock: the order is read from the statements a
    sign-in sent, and a sign-out of the member's other session is answered while a password
    step of hers holds the row."""
    lena = member(keyring, clock)
    other = sign_in(app, lena.email)
    with sent() as statements:
        sign_in(app, lena.email)
    texts = [statement for statement, _ in statements]
    locks = [n for n, text in enumerate(texts) if "FROM erev.app_user" in text and " FOR " in text]
    chain = [n for n, text in enumerate(texts) if "pg_advisory_xact_lock" in text]
    assert len(locks) == 1 and chain, texts
    assert texts[locks[0]].rstrip().endswith("FOR NO KEY UPDATE")
    assert locks[0] < chain[0]

    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opened = sessions._open  # noqa: SLF001 - the place between the identity's lock and the event

    def held_open(db: Any, **arguments: Any) -> Any:
        holding.set()
        assert release.wait(timeout=30), "the password step was never let go"
        return opened(db, **arguments)

    def signing_in() -> None:
        try:
            seen["signed_in"] = call(
                app, "POST", LOGIN, json={"email": lena.email, "password": PASSWORD}
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["signed_in"] = error

    monkeypatch.setattr(sessions, "_open", held_open)
    signer = threading.Thread(target=signing_in, name="password-step")
    signer.start()
    try:
        assert holding.wait(timeout=30), seen
        # Her other session signs out: an event that names her, written by a step that holds no
        # row of hers. It is answered while the password step still holds the identity's row.
        left = call(app, "POST", LOGOUT, headers=cookie_headers(other.token, other.csrf_token))
        assert left.status_code == 204, left.text
        assert "signed_in" not in seen
    finally:
        release.set()
        signer.join(timeout=60)
    assert not signer.is_alive()
    signed_in = seen["signed_in"]
    assert not isinstance(signed_in, BaseException), signed_in
    assert signed_in.status_code == 200, signed_in.text


def test_sar_13_login_rate_limit(app: FastAPI, clock: FrozenClock) -> None:
    email = f"nobody-{secrets.token_hex(6)}@example.test"
    digest = hashlib.sha256(email.encode("ascii")).hexdigest()

    def failures() -> int:
        with identity_session(request_id="tests-session-rate") as db:
            return len(
                db.execute(
                    select(security_event.c.id).where(
                        security_event.c.email_sha256 == digest,
                        security_event.c.kind == "LOGIN_FAILED",
                    )
                ).all()
            )

    attempt = {"email": email, "password": WRONG_PASSWORD}
    # Ten attempts are admitted per minute for one address and email. The email has no account,
    # and it is locked at its fifth failure as an account is (REQ-PLT-004 rev 1.66): the five
    # locked answers are admitted and counted by the limiter like the others, and write no event.
    statuses = [call(app, "POST", LOGIN, json=attempt).status_code for _ in range(10)]
    assert statuses == [401] * 4 + [423] * 6
    assert failures() == 5
    limited = call(app, "POST", LOGIN, json=attempt)
    assert limited.status_code == 429
    assert problem_slug(limited) == "rate-limited"
    assert limited.headers["Retry-After"] == "60"
    assert limited.json()["detail"] == "Too many sign-in attempts. Try again in 60 seconds."
    assert failures() == 5

    other_email = call(app, "POST", LOGIN, json={**attempt, "email": f"x{email}"})
    assert other_email.status_code == 401
    clock.advance(timedelta(seconds=60))
    # The window has passed: the attempt is admitted again — and answered by the lockout, which
    # lasts 15 minutes.
    assert call(app, "POST", LOGIN, json=attempt).status_code == 423
    assert failures() == 5
    clock.advance(timedelta(minutes=15))
    assert call(app, "POST", LOGIN, json=attempt).status_code == 401
    assert failures() == 6


def test_sar_06_unknown_email(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    email = f"Unknown-{secrets.token_hex(6)}@Example.test"
    dummy = passwords.dummy_hash()
    verified: list[str] = []
    original = passwords.verify_password

    def counting(password_hash: str, password: str) -> bool:
        verified.append(password_hash)
        return original(password_hash, password)

    monkeypatch.setattr(passwords, "verify_password", counting)
    response = call(app, "POST", LOGIN, json={"email": email, "password": PASSWORD})
    assert response.status_code == 401
    assert problem_slug(response) == "unauthenticated"
    assert response.json()["detail"] == "The email or password is incorrect."
    assert verified == [dummy]

    digest = hashlib.sha256(email.lower().encode("ascii")).hexdigest()
    with identity_session(request_id="tests-session-unknown") as db:
        event = (
            db.execute(select(security_event).where(security_event.c.email_sha256 == digest))
            .mappings()
            .one()
        )
    assert event["kind"] == "LOGIN_FAILED"
    assert event["user_id"] is None
    assert event["session_id"] is None
    assert email.lower() not in str(event["detail"])


def test_get_session_without_cookie_returns_capabilities(app: FastAPI) -> None:
    response = call(app, "GET", SESSION)
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "capabilities": {"identity_providers": []}}
    assert "X-Erev-Tenant-Kind" not in response.headers


def test_command_requires_idempotency_key(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    signed = sign_in(app, lena.email)
    for headers in (
        cookie_headers(signed.token, signed.csrf_token, key=False),
        {**cookie_headers(signed.token, signed.csrf_token), "Idempotency-Key": "short"},
    ):
        response = call(app, "POST", LOGOUT, headers=headers)
        assert response.status_code == 422
        assert response.json()["errors"][0] == {
            "field": "Idempotency-Key",
            "sheet": None,
            "row": None,
            "rule_id": "API-C-04",
            "message": "Send an Idempotency-Key header with every command.",
        }
    assert session_row(signed.token)["ended_at"] is None


def test_require_authenticated_builds_request_context(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    @app.get("/api/v1/__probe__/context")
    def probe(ctx: Annotated[RequestContext, Depends(require_authenticated())]) -> dict[str, Any]:
        return {
            "tenant_id": str(ctx.principal.tenant_id),
            "membership_id": str(ctx.principal.membership_id),
            "user_id": str(ctx.principal.id),
            "permissions": sorted(ctx.principal.permissions),
            "tenant_kind": ctx.tenant_kind.value,
            "now": ctx.now.isoformat(),
            "format_locale": ctx.format_locale,
        }

    lena = member(keyring, clock)
    second_workspace(keyring, clock, lena.user_id)
    signed = sign_in(app, lena.email)
    without_tenant = call(
        app, "GET", "/api/v1/__probe__/context", headers=cookie_headers(signed.token, key=False)
    )
    assert without_tenant.status_code == 401
    assert problem_slug(without_tenant) == "unauthenticated"
    assert call(app, "GET", "/api/v1/__probe__/context").status_code == 401
    bearer = call(
        app, "GET", "/api/v1/__probe__/context", headers={"Authorization": "Bearer erevt_x"}
    )
    assert bearer.status_code == 401

    rotated = cookie_of(select_tenant(app, signed, lena.tenant_id))
    response = call(
        app, "GET", "/api/v1/__probe__/context", headers=cookie_headers(rotated, key=False)
    )
    assert response.status_code == 200
    assert response.headers["X-Erev-Tenant-Kind"] == "production"
    assert response.json() == {
        "tenant_id": str(lena.tenant_id),
        "membership_id": str(lena.membership_id),
        "user_id": str(lena.user_id),
        "permissions": [],
        "tenant_kind": "production",
        "now": clock.now().isoformat(),
        "format_locale": "en-US",
    }


def test_sar_09_secure_cookie_follows_the_public_origin_not_the_host_header(
    committed_db: TestDatabase, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    """R-34 SD-2 through the sign-in and sign-out routes. An https deployment sets ``Secure``
    whatever ``Host`` the request carries — the review's request named ``127.0.0.1`` and got a
    cookie without it; the compose shape on ``http://127.0.0.1`` sets none, whatever ``Host``
    says, because a browser would never return it."""
    lena = member(keyring, clock)
    credentials = {"email": lena.email, "password": PASSWORD}
    hosted = create_app(
        app_settings.model_copy(
            update={"env": Environment.PRODUCTION, "public_origin": "https://erev.example.com"}
        ),
        clock=clock,
    )
    for host in ("127.0.0.1", "127.0.0.1:8195", "erev.example.com"):
        response = call(hosted, "POST", LOGIN, json=credentials, headers={"Host": host})
        assert response.status_code == 200, response.text
        token = cookie_of(response)
        assert response.headers["set-cookie"] == (
            f"erev_session={token}; HttpOnly; Path=/; SameSite=Lax; Secure"
        ), host
    ended = call(
        hosted,
        "POST",
        LOGOUT,
        headers=cookie_headers(
            token,
            response.json()["csrf_token"],
            Host="127.0.0.1",
            Origin="https://erev.example.com",
        ),
    )
    assert ended.status_code == 204, ended.text
    assert ended.headers["set-cookie"] == (
        "erev_session=; HttpOnly; Path=/; SameSite=Lax; Secure; Max-Age=0"
    )

    compose = create_app(
        app_settings.model_copy(
            update={"env": Environment.PRODUCTION, "public_origin": "http://127.0.0.1:8195"}
        ),
        clock=clock,
    )
    for host in ("erev.example.com", "127.0.0.1:8195"):
        response = call(compose, "POST", LOGIN, json=credentials, headers={"Host": host})
        assert response.status_code == 200, response.text
        assert response.headers["set-cookie"] == (
            f"erev_session={cookie_of(response)}; HttpOnly; Path=/; SameSite=Lax"
        ), host

    # Supervisor ruling R-53 (1): an http origin on any other host fails closed — the cookie stays
    # Secure, whatever Host says, so a browser never sends the session in clear.
    plain = create_app(
        app_settings.model_copy(
            update={"env": Environment.PRODUCTION, "public_origin": "http://erev.example.com"}
        ),
        clock=clock,
    )
    for host in ("erev.example.com", "127.0.0.1"):
        response = call(plain, "POST", LOGIN, json=credentials, headers={"Host": host})
        assert response.status_code == 200, response.text
        assert response.headers["set-cookie"] == (
            f"erev_session={cookie_of(response)}; HttpOnly; Path=/; SameSite=Lax; Secure"
        ), host
