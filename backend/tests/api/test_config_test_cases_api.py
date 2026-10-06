"""API-R-57 configuration test cases (04 §15.3 API-R-57, T-REF-27, §14.1 DB-04, API-C-08;
BUILD_SPEC RFD-5).

Maya holds Revenue Accountant (``config.author``).
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import rule_set_version, rule_test_case
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, cookie_headers, member, sign_in, workspace
from support.rows import insert_role_assignment

RULE_SETS = "/api/v1/rule-sets"
CONFIG_TEST_CASES = "/api/v1/config-test-cases"
PROBLEM_BASE = "https://erev.dev/problems/"


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def maya(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    someone = member(keyring, clock)
    with tenant_session(_context(someone.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code="revenue_accountant",
        )
    return workspace(app, someone, sign_in(app, someone.email))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def test_config_test_cases_follow_subject_status(app: FastAPI, maya: Actor) -> None:
    created_set = post(
        app, RULE_SETS, maya, {"code": "APPROVAL_ROUTING", "kind": "APPROVAL_ROUTING"}
    )
    version = post(app, f"{RULE_SETS}/{created_set.json()['id']}/versions", maya, {})
    assert version.status_code == 201, version.text
    version_id = str(version.json()["id"])
    body = {
        "subject_type": "rule_set_version",
        "subject_id": version_id,
        "name": "Contract activation",
        "input": {"subject.type": "CONTRACT_ACTIVATION"},
        "expected_output": {"matched": False},
    }

    created = post(app, CONFIG_TEST_CASES, maya, body)
    assert created.status_code == 201, created.text
    assert (created.json()["subject_type"], created.json()["subject_id"]) == (
        "rule_set_version",
        version_id,
    )
    assert created.headers["ETag"] == '"r1"'
    listed = call(
        app,
        "GET",
        CONFIG_TEST_CASES,
        params={"subject_type": "rule_set_version", "subject_id": version_id},
        headers=cookie_headers(maya.token, key=False),
    )
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
    unsupported = post(
        app, CONFIG_TEST_CASES, maya, {**body, "subject_type": "account_mapping_version"}
    )
    assert (unsupported.status_code, fields(unsupported)) == (
        422,
        [("subject_type", "T-REF-27")],
    ), unsupported.text
    missing = post(app, CONFIG_TEST_CASES, maya, {**body, "subject_id": str(uuid4())})
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text

    with tenant_session(_context(maya.member.tenant_id)) as session:
        where = rule_set_version.c.id == UUID(version_id)
        session.execute(
            update(rule_set_version)
            .where(where)
            .values(status="TESTED", content_sha256=secrets.token_hex(32))
        )
        session.execute(update(rule_set_version).where(where).values(status="SUBMITTED"))

    frozen = post(app, CONFIG_TEST_CASES, maya, body)
    assert (frozen.status_code, slug(frozen)) == (409, "configuration-frozen"), frozen.text
    assert fields(frozen) == [("status", "DB-04")]
    path = f"{CONFIG_TEST_CASES}/{created.json()['id']}"
    headers = cookie_headers(maya.token, maya.csrf_token, **{"If-Match": created.headers["ETag"]})
    patched = call(app, "PATCH", path, json={"name": "Renamed"}, headers=headers)
    assert (patched.status_code, slug(patched)) == (409, "configuration-frozen"), patched.text
    removed = call(
        app,
        "DELETE",
        path,
        headers=cookie_headers(
            maya.token, maya.csrf_token, **{"If-Match": created.headers["ETag"]}
        ),
    )
    assert (removed.status_code, slug(removed)) == (409, "configuration-frozen"), removed.text
    with tenant_session(_context(maya.member.tenant_id), read_only=True) as session:
        names = session.execute(
            select(rule_test_case.c.name).where(rule_test_case.c.subject_id == UUID(version_id))
        ).scalars()
        assert list(names) == ["Contract activation"]
