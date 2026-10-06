"""API-C-02 ``X-Erev-Tenant-Kind`` (04 §15.1; 03 REQ-PLT-003; 05 SBX-08; BUILD_SPEC SNP-4): every
answer given inside a workspace says whether the workspace is a production tenant or a sandbox —
successes, refusals and problems alike — and an answer given outside any workspace says neither.

The sandbox is ``support.snapshots.seeded_sandbox`` (a tenant row of kind ``sandbox`` with its
roles and chain head); the production tenant is provisioned. The same member role and the same
requests are used in both, so the header is the only thing the kind changes in this module.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.http import call
from support.principals import Actor, colleague, enrolled, member
from support.reference import assign, get, post, slug
from support.snapshots import seeded_sandbox

API = "/api/v1"
HEADER = "X-Erev-Tenant-Kind"
ENDPOINTS = f"{API}/webhook-endpoints"
ENDPOINT_BODY = {"url": "https://hooks.example/erev", "event_kinds": ["period.locked"]}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _integration_admin(app: FastAPI, clock: FrozenClock, tenant_id: UUID) -> Actor:
    someone = colleague(tenant_id, "nikhil")
    assign(someone, "integration_admin")
    return enrolled(app, clock, someone)


def test_tenant_kind_header(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    production = member(keyring, clock).tenant_id
    sandbox = seeded_sandbox(keyring, clock)
    statuses = {}
    for kind, tenant_id in (("production", production), ("sandbox", sandbox)):
        actor = _integration_admin(app, clock, tenant_id)
        answers = {
            "a list": get(app, ENDPOINTS, actor),
            "the session": get(app, f"{API}/session", actor),
            "a command": post(app, ENDPOINTS, actor, ENDPOINT_BODY),
            "an invalid command": post(app, ENDPOINTS, actor, {"url": "", "event_kinds": []}),
            "a missing resource": get(app, f"{ENDPOINTS}/{new_id()}", actor),
            "a permission refusal": get(app, f"{API}/tenant", actor),  # settings.manage not held
        }
        for name, answer in answers.items():
            assert answer.headers[HEADER] == kind, (kind, name, answer.status_code)
        statuses[kind] = {name: answer.status_code for name, answer in answers.items()}
        assert slug(answers["a permission refusal"]) == "forbidden"
    # The requests were real ones: the same six answers in both kinds, except that a sandbox
    # refuses the endpoint commands before it validates them (05 SBX-08).
    assert statuses["production"] == {
        "a list": 200,
        "the session": 200,
        "a command": 201,
        "an invalid command": 422,
        "a missing resource": 404,
        "a permission refusal": 403,
    }
    assert statuses["sandbox"] == {
        **statuses["production"],
        "a command": 403,
        "an invalid command": 403,
    }

    # Outside a workspace there is no kind to name: no session, and a session before a workspace
    # is opened.
    assert HEADER not in call(app, "GET", f"{API}/session").headers
    assert HEADER not in call(app, "GET", f"{API}/health").headers
