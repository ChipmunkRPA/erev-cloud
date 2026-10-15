"""J-19.9 requires administrator-only AI configuration, without accounting privileges.

The strict expected failure records the missing workflow; dual-role policy tests do not
prove that the demo's Tomas/Grace personas can enable AI. Remove it with that implementation.
"""

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from fastapi import FastAPI
from support.http import call
from support.principals import Actor, cookie_headers, enrolled, member
from support.rows import insert_role_assignment
from tests.api.test_tenant_api import app as app  # noqa: F401


class AdminAIWorkflowMissing(AssertionError):
    """Only the confirmed author-permission refusal is an expected failure."""


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


@pytest.mark.xfail(
    strict=True,
    raises=AdminAIWorkflowMissing,
    reason="J-19.9: administrator-only AI policy authoring/approval workflow is missing",
)
def test_admin_can_prepare_ai_enablement_without_accounting_role(
    app: FastAPI, administrator: Actor
) -> None:
    response = call(
        app,
        "POST",
        "/api/v1/policies",
        json={"category": "AI", "scope": "TENANT", "values": {"ai.enabled": True}},
        headers=cookie_headers(administrator.token, administrator.csrf_token),
    )
    if response.status_code == 403 and response.json()["type"].endswith("/forbidden"):
        raise AdminAIWorkflowMissing(response.text)
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
