"""AI-scoped authoring must not grant administrators accounting configuration powers."""

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.domain.ai.settings import load_settings
from erev_api.enums import RegistryCategory
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from fastapi import FastAPI
from support.http import call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.rows import insert_registry_version, insert_role_assignment
from tests.api.test_tenant_api import app as app  # noqa: F401


@pytest.fixture
def administrator(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    person = member(keyring, clock)
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="tenant_admin",
        )
    return enrolled(app, clock, person)


def test_admin_can_prepare_ai_enablement_without_accounting_role(
    app: FastAPI, administrator: Actor
) -> None:
    response = call(
        app,
        "POST",
        "/api/v1/ai/settings/versions",
        json={"values": {"ai.enabled": True}},
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "DRAFT"


def test_admin_still_cannot_author_accounting_policy(app: FastAPI, administrator: Actor) -> None:
    response = call(
        app,
        "POST",
        "/api/v1/policies",
        json={
            "category": "ACCOUNTING_POLICY",
            "scope": "TENANT",
            "values": {"billing.posting": "ERP"},
        },
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert response.status_code == 403, response.text
    assert response.json()["type"].endswith("/forbidden")


def test_admin_ai_version_edit_test_submit_and_withdraw(
    app: FastAPI, administrator: Actor, keyring: KeyRing, clock: FrozenClock
) -> None:
    def headers() -> dict[str, str]:
        return cookie_headers(administrator.token, administrator.csrf_token)

    created = call(
        app,
        "POST",
        "/api/v1/ai/settings/versions",
        json={"values": {"ai.enabled": True}},
        headers=headers(),
    )
    assert created.status_code == 201, created.text
    path = created.headers["Location"]
    read = call(app, "GET", path, headers=headers())
    assert read.status_code == 200, read.text
    assert read.headers["ETag"] == created.headers["ETag"]
    changed = call(
        app,
        "PATCH",
        path,
        json={"values": {"ai.enabled": True, "ai.monthly_token_budget": 10000}},
        headers=headers() | {"If-Match": read.headers["ETag"]},
    )
    assert changed.status_code == 200, changed.text
    stale = call(
        app,
        "PATCH",
        path,
        json={"values": {"ai.enabled": False}},
        headers=headers() | {"If-Match": read.headers["ETag"]},
    )
    assert stale.status_code == 412, stale.text
    queued = call(app, "POST", path + "/test", json={"run_simulation": True}, headers=headers())
    assert queued.status_code == 202, queued.text
    run_job(
        UUID(queued.json()["id"]),
        administrator.member.tenant_id,
        attempt=1,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=app.state.file_store),
    )
    tested = call(app, "GET", path, headers=headers())
    assert tested.status_code == 200 and tested.json()["status"] == "TESTED", tested.text
    submitted = call(app, "POST", path + "/submit", json={}, headers=headers())
    assert submitted.status_code == 200 and submitted.json()["status"] == "SUBMITTED", (
        submitted.text
    )
    with tenant_session(
        DbContext(administrator.member.tenant_id, None, "*"), read_only=True
    ) as session:
        assert not load_settings(
            session,
            tenant_id=administrator.member.tenant_id,
            now=clock.now(),
            platform_kill_switch=False,
        ).enabled
    withdrawn = call(app, "POST", path + "/withdraw", json={}, headers=headers())
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "DRAFT", withdrawn.text


@pytest.mark.parametrize(
    "body",
    [
        {"values": {"billing.posting": "ERP"}},
        {"category": "ACCOUNTING_POLICY", "values": {"ai.enabled": True}},
        {"scope": "ENTITY", "entity_code": "AVM-US", "values": {"ai.enabled": True}},
    ],
)
def test_ai_authoring_rejects_accounting_values_and_scope_changes(
    app: FastAPI, administrator: Actor, body: dict[str, object]
) -> None:
    response = call(
        app,
        "POST",
        "/api/v1/ai/settings/versions",
        json=body,
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert response.status_code == 422, response.text


def test_ai_version_routes_hide_other_categories_and_tenants(
    app: FastAPI, administrator: Actor, keyring: KeyRing, clock: FrozenClock
) -> None:
    own = administrator.member
    other = member(keyring, clock)
    ids = []
    for person, category in (
        (own, RegistryCategory.ACCOUNTING_POLICY),
        (other, RegistryCategory.AI),
    ):
        with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
            ids.append(
                insert_registry_version(session, tenant_id=person.tenant_id, category=category)
            )
    for version_id in ids:
        path = f"/api/v1/ai/settings/versions/{version_id}"
        for method, suffix, body in (
            ("GET", "", None),
            ("PATCH", "", {"values": {"ai.enabled": True}}),
            ("POST", "/test", {}),
            ("POST", "/submit", {}),
            ("POST", "/withdraw", {}),
        ):
            headers = cookie_headers(administrator.token, administrator.csrf_token)
            if method == "PATCH":
                headers["If-Match"] = '"r1"'
            response = call(app, method, path + suffix, json=body, headers=headers)
            assert response.status_code == 404, response.text


def test_ai_authoring_requires_workspace_admin_permission(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    ordinary = enrolled(app, clock, member(keyring, clock))
    response = call(
        app,
        "POST",
        "/api/v1/ai/settings/versions",
        json={"values": {"ai.enabled": True}},
        headers=cookie_headers(ordinary.token, ordinary.csrf_token),
    )
    assert response.status_code == 403, response.text


class AdminAIApprovalMissing(AssertionError):
    """The general registry approval still requires accounting configuration rights."""


@pytest.mark.xfail(
    strict=True,
    raises=AdminAIApprovalMissing,
    reason="J-19.9: independent administrator AI approval routing remains unfinished",
)
def test_independent_admin_can_read_ai_request_for_approval(
    app: FastAPI, administrator: Actor, keyring: KeyRing, clock: FrozenClock
) -> None:
    headers = cookie_headers(administrator.token, administrator.csrf_token)
    created = call(
        app,
        "POST",
        "/api/v1/ai/settings/versions",
        json={"values": {"ai.enabled": True}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    path = created.headers["Location"]
    queued = call(
        app,
        "POST",
        path + "/test",
        json={},
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert queued.status_code == 202, queued.text
    run_job(
        UUID(queued.json()["id"]),
        administrator.member.tenant_id,
        attempt=1,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=app.state.file_store),
    )
    submitted = call(
        app,
        "POST",
        path + "/submit",
        json={},
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert submitted.status_code == 200, submitted.text
    reviewer = colleague(administrator.member.tenant_id, "independent_ai_admin")
    with tenant_session(DbContext(reviewer.tenant_id, reviewer.user_id, "*")) as session:
        insert_role_assignment(
            session,
            tenant_id=reviewer.tenant_id,
            membership_id=reviewer.membership_id,
            role_code="tenant_admin",
        )
    actor = enrolled(app, clock, reviewer)
    request_id = submitted.json()["approval_request_id"]
    response = call(
        app,
        "GET",
        f"/api/v1/approvals/{request_id}",
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    if response.status_code in (403, 404):
        raise AdminAIApprovalMissing(response.text)
    assert response.status_code == 200, response.text
