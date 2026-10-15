"""AI-scoped authoring must not grant administrators accounting configuration powers."""

from datetime import timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.domain.ai.settings import load_settings
from erev_api.domain.policies import registry_versions
from erev_api.enums import RegistryCategory
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from fastapi import FastAPI
from support.http import call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.reference import approve
from support.rows import (
    insert_custom_role,
    insert_registry_version,
    insert_role_assignment,
    publish_registry_version,
)
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


@pytest.mark.parametrize("legacy", [False, True])
def test_independent_admin_approves_ai_without_accounting_role(
    app: FastAPI,
    administrator: Actor,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
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
    if legacy:
        monkeypatch.setattr(registry_versions, "AI_KIND", registry_versions.KIND)
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
        if legacy:
            insert_role_assignment(
                session,
                tenant_id=reviewer.tenant_id,
                membership_id=reviewer.membership_id,
                role_code="controller",
            )
    actor = enrolled(app, clock, reviewer)
    request_id = submitted.json()["approval_request_id"]
    response = call(
        app,
        "GET",
        f"/api/v1/approvals/{request_id}",
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["subject"]["type"] == (
        "REGISTRY_VERSION" if legacy else "AI_SETTINGS_VERSION"
    )
    self_decision = approve(app, request_id, administrator)
    assert self_decision.status_code == 403 and self_decision.json()["type"].endswith(
        "/forbidden" if legacy else "/self-approval"
    ), self_decision.text
    decision = approve(app, request_id, actor)
    assert decision.status_code == 200, decision.text
    published = call(app, "GET", path, headers=cookie_headers(actor.token, actor.csrf_token))
    assert published.status_code == 200 and published.json()["status"] == "PUBLISHED", (
        published.text
    )
    with tenant_session(
        DbContext(administrator.member.tenant_id, None, "*"), read_only=True
    ) as session:
        assert load_settings(
            session,
            tenant_id=administrator.member.tenant_id,
            now=clock.now(),
            platform_kill_switch=False,
        ).enabled


def test_admin_discovers_only_tenant_ai_versions(
    app: FastAPI, administrator: Actor, keyring: KeyRing, clock: FrozenClock
) -> None:
    own = administrator.member
    other = member(keyring, clock)
    headers = cookie_headers(administrator.token, administrator.csrf_token)
    path = "/api/v1/ai/settings/versions"
    initial = call(app, "GET", path, headers=headers)
    assert initial.status_code == 200, initial.text
    assert len(initial.json()["items"]) == 1  # Provisioning publishes default tenant settings.
    initial_id = initial.json()["items"][0]["id"]
    with tenant_session(DbContext(own.tenant_id, own.user_id, "*")) as session:
        published_id = publish_registry_version(
            session,
            tenant_id=own.tenant_id,
            category=RegistryCategory.AI,
            values={"ai.enabled": False},
        )
        insert_registry_version(
            session,
            tenant_id=own.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
        )
    with tenant_session(DbContext(other.tenant_id, other.user_id, "*")) as session:
        insert_registry_version(session, tenant_id=other.tenant_id, category=RegistryCategory.AI)
    headers = cookie_headers(administrator.token, administrator.csrf_token)
    path = "/api/v1/ai/settings/versions"
    created = call(app, "POST", path, json={"values": {"ai.enabled": True}}, headers=headers)
    assert created.status_code == 201, created.text
    draft_id = created.json()["id"]
    first = call(app, "GET", path, params={"limit": 1, "count": "true"}, headers=headers)
    assert first.status_code == 200, first.text
    assert first.headers["X-Erev-Total-Count"] == "3"
    assert [item["id"] for item in first.json()["items"]] == [draft_id]
    cursor = first.json()["next_cursor"]
    assert cursor
    second = call(app, "GET", path, params={"limit": 1, "cursor": cursor}, headers=headers)
    assert second.status_code == 200, second.text
    assert [item["id"] for item in second.json()["items"]] == [str(published_id)]
    third = call(
        app,
        "GET",
        path,
        params={"limit": 1, "cursor": second.json()["next_cursor"]},
        headers=headers,
    )
    assert third.status_code == 200, third.text
    assert [item["id"] for item in third.json()["items"]] == [initial_id]
    assert third.json()["next_cursor"] is None
    filtered = call(app, "GET", path, params={"status": "PUBLISHED"}, headers=headers)
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()["items"]] == [str(published_id)]
    rebound = call(
        app,
        "GET",
        path,
        params={"cursor": cursor, "status": "DRAFT"},
        headers=headers,
    )
    assert rebound.status_code == 422, rebound.text
    # Tenant Admin already has config.read; its broader read remains unchanged.
    general = call(app, "GET", "/api/v1/policies", headers=headers)
    assert general.status_code == 200, general.text
    assert any(item["category"] == "ACCOUNTING_POLICY" for item in general.json()["items"])


@pytest.mark.parametrize("query", ["category=ACCOUNTING_POLICY", "scope=ENTITY", "status=INVALID"])
def test_ai_version_list_refuses_scope_changes_and_invalid_filters(
    app: FastAPI, administrator: Actor, query: str
) -> None:
    response = call(
        app,
        "GET",
        f"/api/v1/ai/settings/versions?{query}",
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert response.status_code == 422, response.text


def test_ai_version_list_requires_administrator(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    ordinary = enrolled(app, clock, member(keyring, clock))
    response = call(
        app,
        "GET",
        "/api/v1/ai/settings/versions",
        headers=cookie_headers(ordinary.token, ordinary.csrf_token),
    )
    assert response.status_code == 403, response.text


def test_admin_ai_status_distinguishes_published_setting_from_emergency_disable(
    app: FastAPI,
    administrator: Actor,
    clock: FrozenClock,
) -> None:
    headers = cookie_headers(administrator.token, administrator.csrf_token)
    path = "/api/v1/ai/settings"
    before = call(app, "GET", path, headers=headers)
    assert before.status_code == 200, before.text
    assert not before.json()["enabled"] and not before.json()["registry_enabled"]
    created = call(
        app,
        "POST",
        path + "/versions",
        json={"values": {"ai.enabled": True}},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert call(app, "GET", path, headers=headers).json() == before.json()
    # Publish a separate retained version as the fixture's reviewed baseline.
    own = administrator.member
    with tenant_session(DbContext(own.tenant_id, own.user_id, "*")) as session:
        publish_registry_version(
            session,
            tenant_id=own.tenant_id,
            category=RegistryCategory.AI,
            at=clock.now(),
            values={
                "ai.enabled": True,
                "ai.model": "reviewed-model",
                "ai.monthly_token_budget": 42,
            },
        )
    active = call(app, "GET", path, headers=headers)
    assert active.status_code == 200, active.text
    assert active.json() == {
        "provider": "fake",
        "enabled": True,
        "registry_enabled": True,
        "tenant_disabled_at": None,
        "platform_disabled": False,
        "workspace_active": True,
        "model": "reviewed-model",
        "monthly_token_budget": 42,
        "send_contract_text": False,
        "redact_contact_details": True,
    }
    disabled = call(
        app,
        "POST",
        "/api/v1/tenant/ai/disable",
        json={"comment": "Pause AI for review"},
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert disabled.status_code == 200, disabled.text
    after = call(app, "GET", path, headers=headers)
    assert after.status_code == 200, after.text
    assert after.json()["registry_enabled"] and not after.json()["enabled"]
    assert after.json()["tenant_disabled_at"] == disabled.json()["ai_disabled_at"]
    assert after.json()["model"] == "reviewed-model"


def test_admin_ai_status_reports_platform_switch_without_changing_policy(
    app: FastAPI,
    administrator: Actor,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = administrator.member
    with tenant_session(DbContext(own.tenant_id, own.user_id, "*")) as session:
        publish_registry_version(
            session,
            tenant_id=own.tenant_id,
            category=RegistryCategory.AI,
            at=clock.now(),
            values={"ai.enabled": True},
        )
    monkeypatch.setattr(
        app.state,
        "settings",
        app.state.settings.model_copy(update={"ai_kill_switch": True}),
    )
    response = call(
        app,
        "GET",
        "/api/v1/ai/settings",
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["registry_enabled"] and response.json()["platform_disabled"]
    assert not response.json()["enabled"]
    assert response.json()["tenant_disabled_at"] is None


def test_ai_status_requires_administrator_and_is_tenant_scoped(
    app: FastAPI,
    administrator: Actor,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    other = member(keyring, clock)
    with tenant_session(DbContext(other.tenant_id, other.user_id, "*")) as session:
        publish_registry_version(
            session,
            tenant_id=other.tenant_id,
            category=RegistryCategory.AI,
            at=clock.now(),
            values={"ai.enabled": True, "ai.model": "other-tenant-model"},
        )
    response = call(
        app,
        "GET",
        "/api/v1/ai/settings",
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    assert response.status_code == 200, response.text
    assert not response.json()["enabled"]
    assert response.json()["model"] != "other-tenant-model"
    ordinary = enrolled(app, clock, other)
    refused = call(
        app,
        "GET",
        "/api/v1/ai/settings",
        headers=cookie_headers(ordinary.token, ordinary.csrf_token),
    )
    assert refused.status_code == 403, refused.text


def test_ai_form_values_need_only_settings_manage(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
) -> None:
    person = member(keyring, clock)
    other = member(keyring, clock)
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        insert_custom_role(
            session, tenant_id=person.tenant_id, code="ai_admin", permissions=["settings.manage"]
        )
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="ai_admin",
        )
        publish_registry_version(
            session,
            tenant_id=person.tenant_id,
            category=RegistryCategory.AI,
            values={"ai.model": "reviewed-model", "ai.anomaly.revenue_change_ratio": "0.25"},
            at=clock.now(),
        )
    with tenant_session(DbContext(other.tenant_id, other.user_id, "*")) as session:
        publish_registry_version(
            session,
            tenant_id=other.tenant_id,
            category=RegistryCategory.AI,
            values={"ai.model": "other-model"},
            at=clock.now(),
        )
    actor = enrolled(app, clock, person)
    headers = cookie_headers(actor.token, actor.csrf_token)
    clock.advance(timedelta(seconds=1))
    created = call(
        app,
        "POST",
        "/api/v1/ai/settings/versions",
        json={"values": {"ai.enabled": True, "ai.model": "unpublished-model"}},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert created.status_code == 201, created.text
    draft_id = UUID(created.json()["id"])
    response = call(app, "GET", "/api/v1/ai/settings/values", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        set(body["values"])
        == set(body["defaults"])
        == {
            "ai.enabled",
            "ai.send_contract_text",
            "ai.model",
            "ai.monthly_token_budget",
            "ai.redact_contact_details",
            "ai.anomaly.revenue_change_ratio",
            "ai.anomaly.revenue_ahead_of_billing_days",
            "ai.anomaly.allocation_adjustment_ratio",
        }
    )
    assert body["values"]["ai.model"] == "reviewed-model"
    assert body["defaults"]["ai.model"] == "claude-opus-5"
    assert body["values"]["ai.anomaly.revenue_change_ratio"] == "0.25"
    assert body["values"]["ai.enabled"] is False
    for path in (
        "/api/v1/policies",
        "/api/v1/registry/parameters",
        "/api/v1/policies/resolve?key=billing.posting",
    ):
        denied = call(app, "GET", path, headers=headers)
        assert denied.status_code == 403, denied.text
    # The page must also be able to follow validation and independently approve
    # with this exact custom permission, not just with the bundled Tenant Admin role.
    path = f"/api/v1/ai/settings/versions/{draft_id}"
    tested = call(app, "POST", path + "/test", json={"run_simulation": True}, headers=headers)
    assert tested.status_code == 202, tested.text
    job_id = UUID(tested.json()["id"])
    run_job(
        job_id,
        person.tenant_id,
        attempt=1,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=app.state.file_store),
    )
    job_read = call(app, "GET", f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_read.status_code == 200 and job_read.json()["state"] == "SUCCEEDED", job_read.text
    submitted = call(
        app,
        "POST",
        path + "/submit",
        json={"comment": "Reviewed administrator settings"},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert submitted.status_code == 200, submitted.text
    reviewer = colleague(person.tenant_id, "independent-ai-admin")
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=reviewer.membership_id,
            role_code="ai_admin",
        )
    reviewer_actor = enrolled(app, clock, reviewer)
    decision = approve(app, submitted.json()["approval_request_id"], reviewer_actor)
    assert decision.status_code == 200, decision.text
    active = call(app, "GET", "/api/v1/ai/settings", headers=headers)
    assert active.status_code == 200 and active.json()["enabled"], active.text
    ordinary = enrolled(app, clock, other)
    denied = call(
        app,
        "GET",
        "/api/v1/ai/settings/values",
        headers=cookie_headers(ordinary.token, ordinary.csrf_token),
    )
    assert denied.status_code == 403, denied.text
