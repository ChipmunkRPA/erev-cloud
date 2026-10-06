"""SAR-42 CSRF rejection and session fixation (04 API-C-02, API-C-03; 05 SAR-09, SAR-11; BUILD_SPEC
SOP-8). Both tests drive the real session flows and need the test database. Tenant-selection
rotation is also covered by ``tests/api/test_session.py``; this file adds login, MFA verification
and password change."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    PASSWORD,
    Actor,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    refreshed,
    sign_in,
)
from support.rows import insert_role_assignment

PROBLEM_BASE = "https://erev.dev/problems/"
NEW_PASSWORD = "Rotated!Password-2026"


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    with tenant_session(_context(tomas.tenant_id)) as session:
        for someone in (tomas, grace):
            insert_role_assignment(
                session,
                tenant_id=tomas.tenant_id,
                membership_id=someone.membership_id,
                role_code="tenant_admin",
            )
    return World(tomas=enrolled(app, clock, tomas), grace=enrolled(app, clock, grace))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def test_sar_42_csrf_rejected(app: FastAPI, world: World) -> None:
    """Each cookie-authenticated command without ``X-CSRF-Token`` returns 403 ``forbidden`` with
    ``rule_id`` ``API-C-02`` and changes nothing."""
    grace = world.grace.member
    commands = (
        (
            "POST",
            f"/api/v1/users/{grace.membership_id}/suspend",
            {"reason": "CSRF probe, ten chars"},
        ),
        (
            "POST",
            "/api/v1/me/password",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        ),
        ("POST", "/api/v1/session/tenant", {"tenant_id": str(world.tenant_id)}),
        ("POST", "/api/v1/session/logout", {}),
    )
    for method, path, body in commands:
        response = call(app, method, path, json=body, headers=cookie_headers(world.tomas.token))
        assert (response.status_code, slug(response)) == (403, "forbidden"), (path, response.text)
        assert response.json()["errors"][0]["rule_id"] == "API-C-02", path
    still_signed_in = call(
        app, "GET", "/api/v1/session", headers=cookie_headers(world.tomas.token, key=False)
    )
    assert still_signed_in.status_code == 200, "a refused command ends nothing"


def test_sar_42_session_token_rotates(app: FastAPI, world: World, clock: FrozenClock) -> None:
    """The cookie value changes at login, MFA verification, password change and tenant selection,
    and each previous value returns 401 ``unauthenticated`` afterwards."""
    lena = colleague(world.tenant_id, "lena")
    actor = enrolled(app, clock, lena)  # login → tenant selection → MFA enrolment, each rotating
    seen: list[str] = []

    def rotated(response: HttpResponse, previous: str) -> str:
        token = cookie_of(response)
        assert token and token != previous and token not in seen, "the cookie value changes"
        # Probed on an authenticated route: ``GET /session`` alone answers a dead cookie with the
        # anonymous 200, capabilities only (04 API-R-01, B3-D15; tests/api/test_session.py).
        stale = call(app, "GET", "/api/v1/me", headers=cookie_headers(previous, key=False))
        assert (stale.status_code, slug(stale)) == (401, "unauthenticated"), "the old value is dead"
        seen.append(previous)
        return token

    # Login issues a token that no earlier cookie shares (no pre-login fixation).
    fresh = sign_in(app, lena.email)
    assert fresh.token not in {actor.token}
    # MFA verification rotates, and comes first: with a factor, the password-only session
    # reaches nothing but the challenge (REQ-PLT-005). The enrolment consumed the current TOTP
    # step (T-PLT-04 ``last_used_step``), so the clock moves one step before a fresh code is
    # presented (Codex production-20260921-2353 P8-SOP8-MFA-1); the anti-replay rule stays in
    # force.
    assert actor.secret is not None
    clock.advance(totp.STEP)
    verified = call(
        app,
        "POST",
        "/api/v1/session/mfa",
        json={"code": totp.code_at(actor.secret, totp.time_step(clock.now()))},
        headers=cookie_headers(fresh.token, fresh.csrf_token),
    )
    assert verified.status_code == 200, verified.text
    token = rotated(verified, fresh.token)
    refreshed_session = refreshed(app, token)
    # Tenant selection rotates.
    selected = call(
        app,
        "POST",
        "/api/v1/session/tenant",
        json={"tenant_id": str(world.tenant_id)},
        headers=cookie_headers(refreshed_session.token, refreshed_session.csrf_token),
    )
    assert selected.status_code == 200, selected.text
    token = rotated(selected, refreshed_session.token)
    refreshed_session = refreshed(app, token)
    # Password change rotates and keeps this session under the new cookie.
    changed = call(
        app,
        "POST",
        "/api/v1/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=cookie_headers(refreshed_session.token, refreshed_session.csrf_token),
    )
    assert changed.status_code == 204, changed.text
    token = rotated(changed, refreshed_session.token)
    alive = call(app, "GET", "/api/v1/session", headers=cookie_headers(token, key=False))
    assert alive.status_code == 200
    # A fresh login with the new password issues yet another distinct token.
    again = sign_in(app, lena.email, NEW_PASSWORD)
    assert again.token not in seen and again.token != token
