"""Immediate tenant AI disable: MFA, atomic queue cancellation and repeat semantics."""

from __future__ import annotations

from datetime import timedelta

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, job, tenant
from erev_api.domain.ai.settings import load_settings
from erev_api.enums import RegistryCategory
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.http import call
from support.principals import cookie_headers, enrolled, member
from support.rows import insert_role_assignment, publish_registry_version
from tests.api.test_tenant_api import app as app  # noqa: F401

PATH = "/api/v1/tenant/ai/disable"


def test_disable_cancels_only_queued_ai_and_is_repeatable(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    person = member(keyring, clock)
    other = member(keyring, clock)
    context = DbContext(person.tenant_id, person.user_id, "*")
    identities = [new_id() for _ in range(4)]
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="tenant_admin",
        )
        publish_registry_version(
            session,
            tenant_id=person.tenant_id,
            category=RegistryCategory.AI,
            values={
                "ai.enabled": True,
                "ai.model": "fixture-model",
                "ai.monthly_token_budget": 1000,
                "ai.send_contract_text": False,
                "ai.redact_contact_details": True,
            },
            at=clock.now(),
        )
        assert load_settings(
            session, tenant_id=person.tenant_id, now=clock.now(), platform_kill_switch=False
        ).enabled
        for job_id, kind, queue, state in zip(
            identities[:3],
            ("AI_TASK", "AI_TASK", "REPORT_RUN"),
            ("ai", "ai", "report"),
            ("QUEUED", "RUNNING", "QUEUED"),
            strict=True,
        ):
            session.execute(
                insert(job).values(
                    id=job_id,
                    tenant_id=person.tenant_id,
                    kind=kind,
                    queue=queue,
                    state=state,
                    params={},
                    created_by=person.user_id,
                    created_by_kind="USER",
                    updated_by=person.user_id,
                    updated_by_kind="USER",
                )
            )
    with tenant_session(DbContext(other.tenant_id, other.user_id, "*")) as session:
        session.execute(
            insert(job).values(
                id=identities[3],
                tenant_id=other.tenant_id,
                kind="AI_TASK",
                queue="ai",
                state="QUEUED",
                params={},
                created_by=other.user_id,
                created_by_kind="USER",
                updated_by=other.user_id,
                updated_by_kind="USER",
            )
        )
    actor = enrolled(app, clock, person)
    headers = cookie_headers(actor.token, actor.csrf_token)
    response = call(app, "POST", PATH, json={"comment": "Pause AI for review"}, headers=headers)
    assert response.status_code == 200, response.text
    repeat = call(app, "POST", PATH, json={"comment": "Pause AI for review"}, headers=headers)
    assert repeat.status_code == 200 and repeat.json() == response.json()
    later = call(
        app,
        "POST",
        PATH,
        json={"comment": "Already paused"},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert later.status_code == 200 and later.json() == response.json()
    with tenant_session(context, read_only=True) as session:
        rows = session.execute(select(job).where(job.c.id.in_(identities))).mappings().all()
        by_id = {row["id"]: row for row in rows}
        assert [by_id[item]["state"] for item in identities[:3]] == [
            "CANCELLED",
            "RUNNING",
            "QUEUED",
        ]
        assert by_id[identities[0]]["finished_at"] == clock.now()
        assert by_id[identities[1]]["cancel_requested_at"] is None
        workspace = (
            session.execute(select(tenant).where(tenant.c.id == person.tenant_id)).mappings().one()
        )
        assert workspace["ai_disabled_at"] == clock.now()
        assert workspace["ai_disabled_by"] == person.user_id
        assert not load_settings(
            session, tenant_id=person.tenant_id, now=clock.now(), platform_kill_switch=False
        ).enabled
        events = (
            session.execute(select(audit_event).where(audit_event.c.action == "ai.disabled"))
            .mappings()
            .all()
        )
        assert len(events) == 1 and events[0]["comment"] == "Pause AI for review"
        assert session.scalar(select(audit_event.c.id).where(audit_event.c.action == "job.cancel"))
    with tenant_session(DbContext(other.tenant_id, other.user_id, "*"), read_only=True) as session:
        assert session.scalar(select(job.c.state).where(job.c.id == identities[3])) == "QUEUED"
        assert (
            session.scalar(select(tenant.c.ai_disabled_at).where(tenant.c.id == other.tenant_id))
            is None
        )


def test_disable_requires_permission_fresh_mfa_and_comment(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    person = member(keyring, clock)
    actor = enrolled(app, clock, person)
    response = call(
        app,
        "POST",
        PATH,
        json={"comment": "Stop"},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert response.status_code == 403, response.text
    with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
        insert_role_assignment(
            session,
            tenant_id=person.tenant_id,
            membership_id=person.membership_id,
            role_code="tenant_admin",
        )
    invalid = call(
        app,
        "POST",
        PATH,
        json={"comment": "   "},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert invalid.status_code == 422, invalid.text
    clock.advance(timedelta(minutes=6))
    stale = call(
        app,
        "POST",
        PATH,
        json={"comment": "Stop"},
        headers=cookie_headers(actor.token, actor.csrf_token),
    )
    assert stale.status_code == 403 and stale.json()["type"].endswith("mfa-step-up-required"), (
        stale.text
    )
    with tenant_session(
        DbContext(person.tenant_id, person.user_id, "*"), read_only=True
    ) as session:
        assert (
            session.scalar(select(tenant.c.ai_disabled_at).where(tenant.c.id == person.tenant_id))
            is None
        )
