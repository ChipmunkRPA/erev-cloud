"""SAR-42 security headers on API error responses and file downloads (05 SAR-20, UPL-10; BUILD_SPEC
SOP-8). ``test_sar_20_headers_on_error_responses`` builds the app without a database (the app
factory connects only at startup) and runs on the CPU; the spec-named
``test_sar_42_headers_on_api_errors_and_files`` also downloads a stored file and needs the test
database — recorded NOT RUN by lane P8 until a database is provisioned."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from erev_api.api.middleware import SECURITY_HEADERS
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.enums import FilePurpose
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.rows import insert_role_assignment
from support.upload_fixtures import PDF

PROBLEM_BASE = "https://erev.dev/problems/"
FILES = "/api/v1/files"


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def assert_sar_20_headers(response: HttpResponse, *, cache: str = "no-store") -> None:
    for name, value in SECURITY_HEADERS.items():
        expected = cache if name == "Cache-Control" else value
        assert response.headers.get(name) == expected, (name, response.headers.get(name))
    assert response.headers.get("X-Request-Id"), "every response names its request"


def test_sar_20_headers_on_error_responses(app_settings: Settings, clock: FrozenClock) -> None:
    """A 401, a 404 and a 422 from the api carry every SAR-20 header and ``Cache-Control:
    no-store``; the app is built without a database (error paths stop before any query)."""
    app = create_app(app_settings, clock=clock)
    unauthenticated = call(app, "GET", "/api/v1/users")
    assert (unauthenticated.status_code, slug(unauthenticated)) == (401, "unauthenticated")
    assert_sar_20_headers(unauthenticated)
    missing = call(app, "GET", "/api/v1/no-such-resource")
    assert missing.status_code == 404 and slug(missing) == "not-found"
    assert_sar_20_headers(missing)
    malformed = call(app, "POST", "/api/v1/session/login", json={"email": 12})
    assert (malformed.status_code, slug(malformed)) == (422, "validation-failed"), malformed.text
    assert_sar_20_headers(malformed)
    assert SECURITY_HEADERS["Content-Security-Policy"].startswith("default-src 'self'")
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"


# ---- with a stored file (needs the test database; NOT RUN until provisioned)


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    with tenant_session(DbContext(tenant_id=tomas.tenant_id, user_id=None, entity_scope="*")) as s:
        for someone in (tomas, grace):
            insert_role_assignment(
                s,
                tenant_id=tomas.tenant_id,
                membership_id=someone.membership_id,
                role_code="tenant_admin",
            )
    return World(tomas=enrolled(app, clock, tomas))


def test_sar_42_headers_on_api_errors_and_files(app: FastAPI, world: World) -> None:
    """BUILD_SPEC SOP-8: a 401, a 404, a 422 and a file download all carry the SAR-20 headers; the
    file download also carries ``Content-Security-Policy: sandbox`` (UPL-10) and
    ``Content-Disposition: attachment``."""
    for response in (
        call(app, "GET", "/api/v1/users"),
        call(
            app,
            "GET",
            f"/api/v1/users/{UUID(int=9)}",
            headers=cookie_headers(world.tomas.token, key=False),
        ),
        call(app, "POST", "/api/v1/session/login", json={"email": 12}),
    ):
        assert response.status_code in (401, 404, 422), response.text
        assert_sar_20_headers(response)
    uploaded = call(
        app,
        "POST",
        FILES,
        data={"purpose": FilePurpose.ATTACHMENT.value},
        files={"file": ("terms.pdf", PDF, "application/pdf")},
        headers=cookie_headers(world.tomas.token, world.tomas.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    download = call(
        app,
        "GET",
        f"{FILES}/{uploaded.json()['id']}/content",
        headers=cookie_headers(world.tomas.token, key=False),
    )
    assert download.status_code == 200
    assert download.headers["Content-Security-Policy"] == "sandbox"
    assert download.headers["Content-Disposition"].startswith("attachment;")
    assert download.headers["X-Content-Type-Options"] == "nosniff"
    for name, value in SECURITY_HEADERS.items():
        if name != "Content-Security-Policy":
            assert download.headers.get(name) == value, name
