"""AI enablement publishes under independent administrator approval, never on replay."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals
from erev_api.db.session import tenant_session
from erev_api.db.tables import approval_decision, audit_event, tenant
from sqlalchemy import func, select
from support.principals import enrolled
from support.reference import assign
from tests.domain.policies.test_registry_versions import (
    POLICIES,
    World,
    context,
    created,
    pass_tests,
    shown,
    submitted,
)
from tests.domain.policies.test_registry_versions import world as world  # noqa: F401


def test_independent_admin_publication_clears_switch_but_replay_does_not(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    policies = world.policies
    assign(policies.maya.member, "tenant_admin")
    admin = enrolled(policies.app, policies.clock, policies.maya.member)
    policies = replace(policies, maya=admin)
    world = replace(world, policies=policies)

    def disable() -> str:
        response = policies.post("/api/v1/tenant/ai/disable", {"comment": "Pause AI"}, admin)
        assert response.status_code == 200, response.text
        return str(response.json()["ai_disabled_at"])

    def switch() -> Any:
        with tenant_session(context(world.tenant_id), read_only=True) as session:
            return session.scalar(
                select(tenant.c.ai_disabled_at).where(tenant.c.id == world.tenant_id)
            )

    auto_flags: list[bool] = []
    real_submit = approvals.submit

    def observed_submit(*args: Any, **kwargs: Any) -> Any:
        auto_flags.append(kwargs["auto_approval"])
        return real_submit(*args, **kwargs)

    monkeypatch.setattr(approvals, "submit", observed_submit)
    disable()
    first = created(world, category="AI", scope="TENANT", values={"ai.enabled": True})
    pass_tests(world, first["id"])
    request_id = str(submitted(world, first["id"])["approval_request_id"])
    assert auto_flags == [False]
    refused = policies.get(f"/api/v1/approvals/{request_id}", policies.marcus)
    assert refused.status_code == 404, refused.text
    assert shown(world, first["id"])["status"] == "SUBMITTED"
    assert switch() is not None
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(approval_decision)
                .where(approval_decision.c.approval_request_id == UUID(request_id))
            )
            == 0
        )
    assign(policies.marcus.member, "tenant_admin")
    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    assert shown(world, first["id"])["status"] == "PUBLISHED"
    assert switch() is None

    policies.clock.advance(timedelta(seconds=1))
    disabled = disable()
    replay = policies.post(f"{POLICIES}/{first['id']}/publish", {})
    assert replay.status_code == 200, replay.text
    assert switch().isoformat().replace("+00:00", "Z") == disabled

    # ai.enabled is carried from the predecessor, not named in this draft. It
    # still needs a human decision before it may clear a later emergency stop.
    second = created(world, category="AI", scope="TENANT", values={"ai.monthly_token_budget": 5000})
    pass_tests(world, second["id"])
    second_request = str(submitted(world, second["id"])["approval_request_id"])
    assert auto_flags == [False, False]
    assert switch() is not None
    approved = policies.approve(second_request)
    assert approved.status_code == 200, approved.text
    assert switch() is None
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        events = (
            session.execute(select(audit_event).where(audit_event.c.action == "ai.enabled"))
            .mappings()
            .all()
        )
        assert len(events) == 2
        assert {row["approval_request_id"] for row in events} == {
            UUID(request_id),
            UUID(second_request),
        }
        workspace = (
            session.execute(select(tenant).where(tenant.c.id == world.tenant_id)).mappings().one()
        )
        assert workspace["ai_disabled_by"] is None and workspace["ai_disabled_by_kind"] is None

    # A budget-only change while AI remains enabled keeps normal approval routing.
    policies.clock.advance(timedelta(seconds=1))
    budget = created(world, category="AI", scope="TENANT", values={"ai.monthly_token_budget": 6000})
    pass_tests(world, budget["id"])
    budget_request = str(submitted(world, budget["id"])["approval_request_id"])
    assert auto_flags == [False, False, True]
    approved = policies.approve(budget_request)
    assert approved.status_code == 200, approved.text
    assert switch() is None

    # A new policy that keeps AI disabled does not clear an emergency switch.
    policies.clock.advance(timedelta(seconds=1))
    disable()
    stopped_at = switch()
    third = created(world, category="AI", scope="TENANT", values={"ai.enabled": False})
    pass_tests(world, third["id"])
    third_request = str(submitted(world, third["id"])["approval_request_id"])
    approved = policies.approve(third_request)
    assert approved.status_code == 200, approved.text
    assert switch() == stopped_at


@pytest.mark.parametrize(
    "baseline,changes,unset,review",
    [
        ({"ai.enabled": False}, {"ai.model": "fixture-new-model"}, [], True),
        ({"ai.enabled": False, "ai.model": "fixture-old-model"}, {}, ["ai.model"], True),
        ({"ai.enabled": False}, {"ai.send_contract_text": True}, [], True),
        (
            {"ai.enabled": False, "ai.send_contract_text": True},
            {"ai.send_contract_text": False},
            [],
            False,
        ),
    ],
)
def test_ai_setting_review_preserves_emergency_disable(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    baseline: dict[str, Any],
    changes: dict[str, Any],
    unset: list[str],
    review: bool,
) -> None:
    from erev_api.domain.ai.settings import load_settings
    from erev_api.enums import RegistryCategory
    from erev_api.registry.platform import PLATFORM_PARAMETERS
    from support.rows import publish_registry_version

    policies = world.policies
    assign(policies.maya.member, "tenant_admin")
    author = enrolled(policies.app, policies.clock, policies.maya.member)
    policies = replace(policies, maya=author)
    world = replace(world, policies=policies)
    with tenant_session(context(world.tenant_id)) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.AI,
            values=baseline,
            at=policies.clock.now() - timedelta(seconds=1),
        )
    disabled = policies.post("/api/v1/tenant/ai/disable", {"comment": "Keep AI paused"})
    assert disabled.status_code == 200, disabled.text
    auto_flags: list[bool] = []
    real_submit = approvals.submit

    def observed_submit(*args: Any, **kwargs: Any) -> Any:
        auto_flags.append(kwargs["auto_approval"])
        return real_submit(*args, **kwargs)

    monkeypatch.setattr(approvals, "submit", observed_submit)
    version = created(world, category="AI", scope="TENANT", values=changes, unset=unset)
    pass_tests(world, version["id"])
    request_id = str(submitted(world, version["id"])["approval_request_id"])
    assert auto_flags == [not review]
    hidden = policies.get(f"/api/v1/approvals/{request_id}", policies.marcus)
    assert hidden.status_code == 404, hidden.text
    assert shown(world, version["id"])["status"] == "SUBMITTED"
    assign(policies.marcus.member, "tenant_admin")
    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    assert shown(world, version["id"])["status"] == "PUBLISHED"
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        stamp = session.scalar(
            select(tenant.c.ai_disabled_at).where(tenant.c.id == world.tenant_id)
        )
        assert stamp is not None
        assert stamp.isoformat().replace("+00:00", "Z") == disabled.json()["ai_disabled_at"]
        effective = load_settings(
            session, tenant_id=world.tenant_id, now=policies.clock.now(), platform_kill_switch=False
        )
        expected = {**baseline, **changes}
        for code in unset:
            expected.pop(code, None)
        assert effective.model == expected.get(
            "ai.model", PLATFORM_PARAMETERS["ai.model"].default_asc606
        )
        assert effective.send_contract_text is expected.get("ai.send_contract_text", False)
        assert effective.enabled is False
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == "ai.enabled")
            )
            == 0
        )
