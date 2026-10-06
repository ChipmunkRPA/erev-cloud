"""API-R-25 rule set authorization and concurrency (04 §15.3 API-R-25, API-C-08, API-C-13; PRD §5.6
ACT-22; BUILD_SPEC RFD-4).

Vera is a Viewer (``config.read`` only); Maya holds Revenue Accountant (``config.author``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import rule_set
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
PROBLEM_BASE = "https://erev.dev/problems/"
HOLDS: Mapping[str, Any] = {"code": "HOLDS", "kind": "HOLD", "name": "Contract holds"}


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def actors(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Actor, Actor]:
    """Vera (Viewer) and Maya (Revenue Accountant) of one workspace."""
    maya = member(keyring, clock)
    vera = colleague(maya.tenant_id, "vera")
    with tenant_session(_context(maya.tenant_id)) as session:
        for someone, code in ((vera, "viewer"), (maya, "revenue_accountant")):
            insert_role_assignment(
                session,
                tenant_id=maya.tenant_id,
                membership_id=someone.membership_id,
                role_code=code,
            )
    return (
        workspace(app, vera, sign_in(app, vera.email)),
        workspace(app, maya, sign_in(app, maya.email)),
    )


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def test_authoring_requires_config_author(app: FastAPI, actors: tuple[Actor, Actor]) -> None:
    vera, maya = actors
    refused = post(app, RULE_SETS, vera, HOLDS)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    with tenant_session(_context(maya.member.tenant_id), read_only=True) as session:
        assert session.execute(select(rule_set.c.id).where(rule_set.c.code == "HOLDS")).all() == []
    readable = call(app, "GET", RULE_SETS, headers=cookie_headers(vera.token, key=False))
    assert readable.status_code == 200, readable.text

    created = post(app, RULE_SETS, maya, HOLDS)
    assert created.status_code == 201, created.text
    assert (created.json()["name"], created.headers["ETag"]) == ("Contract holds", '"r1"')
    version = post(app, f"{RULE_SETS}/{created.json()['id']}/versions", vera, {})
    assert (version.status_code, slug(version)) == (403, "forbidden"), version.text


def test_version_update_requires_if_match(app: FastAPI, actors: tuple[Actor, Actor]) -> None:
    _, maya = actors
    created = post(app, RULE_SETS, maya, HOLDS)
    version = post(app, f"{RULE_SETS}/{created.json()['id']}/versions", maya, {})
    assert version.status_code == 201, version.text
    path = f"{VERSIONS}/{version.json()['id']}"
    body = {"effective_from": "2026-10-01T00:00:00Z"}

    missing = call(
        app, "PATCH", path, json=body, headers=cookie_headers(maya.token, maya.csrf_token)
    )
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    stale = call(
        app,
        "PATCH",
        path,
        json=body,
        headers=cookie_headers(maya.token, maya.csrf_token, **{"If-Match": '"r9"'}),
    )
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text

    current = call(app, "GET", path, headers=cookie_headers(maya.token, key=False))
    assert current.headers["ETag"] == '"r1"'
    patched = call(
        app,
        "PATCH",
        path,
        json=body,
        headers=cookie_headers(
            maya.token, maya.csrf_token, **{"If-Match": current.headers["ETag"]}
        ),
    )
    assert patched.status_code == 200, patched.text
    assert (patched.json()["effective_from"], patched.headers["ETag"]) == (
        "2026-10-01T00:00:00Z",
        '"r2"',
    )
