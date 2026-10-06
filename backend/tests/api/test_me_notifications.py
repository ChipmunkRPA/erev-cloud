"""API-R-03 me notifications and notification preferences (04 §15.3 API-R-03, §16.12, T-PLT-24,
T-PLT-25; PRD §5.4 NTF-R2; SCREENS SCR-IA-06 bindings; BUILD_SPEC PLF-14).

Each test signs in a member of a fresh tenant; notifications are written through ``notify`` by the
SYSTEM principal, as their causes will.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.enums import NotificationKind, TenantKind
from erev_api.events.notifications import EMAIL_DEFAULTS, notify
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Member, cookie_headers, cookie_of, member, select_tenant, sign_in

NOTIFICATIONS = "/api/v1/me/notifications"
READ_ALL = f"{NOTIFICATIONS}/read-all"
PREFERENCES = "/api/v1/me/notification-preferences"
SESSION = "/api/v1/session"
PROBLEM_BASE = "https://erev.dev/problems/"
MANDATORY = "Audit chain failures are always sent in the app and by email."


@dataclass(frozen=True, slots=True)
class Actor:
    member: Member
    token: str
    csrf_token: str


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def actor(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    lena = member(keyring, clock)
    token = cookie_of(select_tenant(app, sign_in(app, lena.email), lena.tenant_id))
    session = call(app, "GET", SESSION, headers={"Cookie": f"erev_session={token}"})
    return Actor(member=lena, token=token, csrf_token=session.json()["csrf_token"])


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def _notify(
    lena: Member, subject_id: UUID, *, clock: FrozenClock, keyring: KeyRing, settings: Settings
) -> None:
    ctx = RequestContext(
        principal=system_principal(lena.tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-me-notifications",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        notify(
            uow,
            recipient_membership_ids=[lena.membership_id],
            kind=NotificationKind.ITEM_APPROVED,
            title="Approved: Change the access approver role",
            subject_type="ROLE_CHANGE",
            subject_id=subject_id,
        )
        uow.commit()


def test_read_all_before(
    app: FastAPI, actor: Actor, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    moments = []
    for _ in range(3):
        clock.advance(timedelta(minutes=1))
        moments.append(clock.now())
        _notify(actor.member, new_id(), clock=clock, keyring=keyring, settings=app_settings)

    listed = call(app, "GET", NOTIFICATIONS, headers=cookie_headers(actor.token, key=False))
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [item["kind"] for item in items] == ["ITEM_APPROVED"] * 3
    assert [item["read_at"] for item in items] == [None, None, None]

    marked = call(
        app,
        "POST",
        READ_ALL,
        json={"before": moments[1].isoformat()},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert (marked.status_code, marked.json()) == (200, {"marked": 2}), marked.text

    unread = call(
        app,
        "GET",
        f"{NOTIFICATIONS}?unread=true&count=true",
        headers=cookie_headers(actor.token, key=False),
    )
    assert unread.status_code == 200, unread.text
    assert unread.headers["X-Erev-Total-Count"] == "1"
    [remaining] = unread.json()["items"]
    assert remaining["id"] == items[0]["id"]

    read = call(
        app,
        "POST",
        f"{NOTIFICATIONS}/{remaining['id']}/read",
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert read.status_code == 200, read.text
    assert read.json()["read_at"] is not None
    missing = call(
        app,
        "POST",
        f"{NOTIFICATIONS}/{new_id()}/read",
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert (missing.status_code, slug(missing)) == (404, "not-found")


def test_notification_preferences_put_and_mandatory_kind(app: FastAPI, actor: Actor) -> None:
    kinds = [kind.value for kind in NotificationKind]
    defaults = call(app, "GET", PREFERENCES, headers=cookie_headers(actor.token, key=False))
    assert defaults.status_code == 200, defaults.text
    assert [item["kind"] for item in defaults.json()["items"]] == kinds
    assert {item["kind"]: item["email"] for item in defaults.json()["items"]} == {
        kind.value: EMAIL_DEFAULTS[kind] for kind in NotificationKind
    }

    entries = [
        {
            "kind": kind.value,
            "in_app": True,
            "email": kind is NotificationKind.ITEM_APPROVED or EMAIL_DEFAULTS[kind],
        }
        for kind in NotificationKind
    ]
    assert len(entries) == 12
    put = call(
        app,
        "PUT",
        PREFERENCES,
        json={"items": entries},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert put.status_code == 200, put.text
    assert put.json()["items"] == entries
    stored = call(app, "GET", PREFERENCES, headers=cookie_headers(actor.token, key=False))
    assert stored.json()["items"] == entries

    refused = call(
        app,
        "PUT",
        PREFERENCES,
        json={"items": [{"kind": "CHAIN_VERIFICATION_FAILED", "in_app": True, "email": False}]},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    [error] = refused.json()["errors"]
    assert (error["field"], error["rule_id"], error["message"]) == (
        "items[0].email",
        "NTF-R2",
        MANDATORY,
    )
    unchanged = call(app, "GET", PREFERENCES, headers=cookie_headers(actor.token, key=False))
    assert unchanged.json()["items"] == entries
