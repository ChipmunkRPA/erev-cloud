"""Support grants and operator access (04 T-PLT-33, T-PLT-08 ``operator_support_grant_id``; 05
SAR-29, TB-7, THR-20, SCH-15; PRD NTF-12, §2.5 routing row ``SUPPORT_GRANT``; REQ-PLT-036; CTL-035;
BUILD_SPEC PLF-26, BS1-D-27).

Tomas and Grace are Tenant Admins of a provisioned workspace; Tomas is enrolled in MFA. The
operator is created and requests access through the ``erev`` CLI, and Tomas approves.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth import sessions
from erev_api.auth.keyring import KeyRing
from erev_api.cli import CliServices
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    approval_request,
    approval_step,
    audit_event,
    notification,
    support_grant,
    user_session,
)
from erev_api.domain.platform import support_grants
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import Select, select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.operators import (
    approve,
    create_operator,
    operator_services,
    operator_signed_in,
    request_grant,
    tenant_code,
)
from support.principals import (
    Actor,
    Member,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    select_tenant,
    sign_in,
)
from support.rows import insert_role_assignment

AUDIT = "/api/v1/audit-events"
LOGOUT = "/api/v1/session/logout"
PROBLEM_BASE = "https://erev.dev/problems/"


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Member
    code: str

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def services(keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> CliServices:
    # The CLI stores the impact preview the approval inbox reads, so both share one file store.
    return operator_services(keyring, clock, app_settings.file_root)


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
    return World(tomas=enrolled(app, clock, tomas), grace=grace, code=tenant_code(tomas.tenant_id))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def rows(tenant_id: UUID, statement: Select[Any]) -> list[Mapping[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def approved_grant(
    app: FastAPI, clock: FrozenClock, services: CliServices, world: World, email: str
) -> UUID:
    """A grant in force from an hour ago for eight hours, requested by the operator and approved
    by Tomas."""
    now = clock.now()
    requested = request_grant(
        services,
        tenant_code=world.code,
        operator_email=email,
        valid_from=(now - timedelta(hours=1)).isoformat(),
        valid_to=(now + timedelta(hours=7)).isoformat(),
    )
    assert requested.exit_code == 0, requested.output
    grant = json.loads(requested.stdout)
    approved = approve(app, str(grant["approval_request_id"]), world.tomas)
    assert approved.status_code == 200, approved.text
    return UUID(grant["id"])


def grant_sessions(grant_id: UUID) -> list[Mapping[str, Any]]:
    with identity_session(request_id="tests-support-grant-sessions") as db:
        return [
            dict(row)
            for row in db.execute(
                select(user_session.c.end_reason, user_session.c.ended_at).where(
                    user_session.c.operator_support_grant_id == grant_id
                )
            ).mappings()
        ]


@pytest.mark.control("CTL-035")
def test_ctl_035_operator_requires_approved_grant(
    app: FastAPI, clock: FrozenClock, services: CliServices, world: World
) -> None:
    operator = create_operator(services)
    signed = operator_signed_in(app, clock, operator["email"])
    # Without a grant the workspace does not exist for the operator.
    refused = select_tenant(app, signed, world.tenant_id)
    assert (refused.status_code, slug(refused)) == (404, "not-found")

    now = clock.now()
    requested = request_grant(
        services,
        tenant_code=world.code,
        operator_email=operator["email"],
        valid_from=(now - timedelta(hours=1)).isoformat(),
        valid_to=(now + timedelta(hours=7)).isoformat(),
    )
    assert requested.exit_code == 0, requested.output
    grant = json.loads(requested.stdout)
    grant_id = UUID(grant["id"])
    # A requested grant opens nothing until a Tenant Admin approves it.
    pending = select_tenant(app, signed, world.tenant_id)
    assert (pending.status_code, slug(pending)) == (404, "not-found")
    approved = approve(app, str(grant["approval_request_id"]), world.tomas)
    assert approved.status_code == 200, approved.text

    # An operator session without MFA verification is refused.
    unverified = select_tenant(app, sign_in(app, operator["email"]), world.tenant_id)
    assert (unverified.status_code, slug(unverified)) == (403, "mfa-required")

    selected = select_tenant(app, signed, world.tenant_id)
    assert selected.status_code == 200, selected.text
    assert selected.json()["active_tenant"]["id"] == str(world.tenant_id)
    token, csrf_token = cookie_of(selected), selected.json()["csrf_token"]
    with identity_session(request_id="tests-ctl-035") as db:
        found = db.execute(
            select(user_session.c.operator_support_grant_id).where(
                user_session.c.token_sha256 == sessions.sha256_hex(token)
            )
        ).scalar_one()
    assert found == grant_id

    listed = call(app, "GET", AUDIT, headers=cookie_headers(token, key=False))
    assert listed.status_code == 200, listed.text
    invited = call(
        app,
        "POST",
        "/api/v1/users",
        json={"email": "new@members.test", "display_name": "New", "roles": []},
        headers=cookie_headers(token, csrf_token),
    )
    assert (invited.status_code, slug(invited)) == (403, "forbidden")
    # A command guarded by a permission the operator holds is refused too: access is read-only.
    verify = call(app, "POST", f"{AUDIT}/verify", headers=cookie_headers(token, csrf_token))
    assert (verify.status_code, slug(verify)) == (403, "forbidden")

    events = rows(
        world.tenant_id,
        select(
            audit_event.c.action,
            audit_event.c.actor_kind,
            audit_event.c.actor_id,
            audit_event.c.outcome,
            audit_event.c.detail,
        )
        .where(audit_event.c.support_grant_id == grant_id)
        .order_by(audit_event.c.chain_seq),
    )
    assert [
        (event["action"], event["outcome"], event["detail"].get("path")) for event in events
    ] == [
        ("support_grant.open_session", "SUCCESS", None),
        ("support_grant.access", "SUCCESS", "/api/v1/audit-events"),
        ("support_grant.access", "SUCCESS", "/api/v1/users"),
        ("user.manage", "DENIED", "/api/v1/users"),
        ("support_grant.access", "SUCCESS", "/api/v1/audit-events/verify"),
        ("support_grant.command", "DENIED", "/api/v1/audit-events/verify"),
    ]
    assert {(event["actor_kind"], event["actor_id"]) for event in events} == {
        ("OPERATOR", UUID(operator["id"]))
    }


def test_sar_09_an_operators_support_session_has_no_successor_once_it_ended(
    app: FastAPI,
    clock: FrozenClock,
    services: CliServices,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; SAR-29): an operator's workspace is opened
    by the same rotation as a member's (``operators.select_support_tenant`` calls
    ``sessions.reissue``), under the same rule. The operator's session is signed out here after
    the request was authenticated and its grant was read, before the rotation: the request is
    answered 401, no session stands under the grant and the workspace's log holds no opening."""
    operator = create_operator(services)
    signed = operator_signed_in(app, clock, operator["email"])
    grant_id = approved_grant(app, clock, services, world, operator["email"])
    read = sessions.support_tenant

    def then(facts: Any, **arguments: Any) -> Any:
        found = read(facts, **arguments)
        left = call(app, "POST", LOGOUT, headers=cookie_headers(signed.token, signed.csrf_token))
        assert left.status_code == 204, left.text
        return found

    monkeypatch.setattr(sessions, "support_tenant", then)
    refused = select_tenant(app, signed, world.tenant_id)
    assert refused.status_code == 401, refused.text
    assert slug(refused) == "unauthenticated"
    assert refused.json()["detail"] == "Sign in to continue."
    assert "set-cookie" not in refused.headers
    assert grant_sessions(grant_id) == []
    opened = rows(
        world.tenant_id,
        select(audit_event.c.action).where(audit_event.c.support_grant_id == grant_id),
    )
    assert opened == []


def test_request_notifies_tenant_admins(services: CliServices, world: World) -> None:
    operator = create_operator(services)
    result = request_grant(
        services,
        tenant_code=world.code,
        operator_email=operator["email"],
        valid_from="2026-09-13T09:00:00Z",
        valid_to="2026-09-13T17:00:00Z",
    )
    assert result.exit_code == 0, result.output
    grant = json.loads(result.stdout)
    assert (
        grant["status"],
        grant["scope"],
        grant["ticket_ref"],
        grant["operator"],
        grant["created_by"]["kind"],
    ) == (
        "REQUESTED",
        "READ_ONLY",
        "SUP-2291",
        {"id": operator["id"], "kind": "OPERATOR", "display_name": "Ops Tester"},
        "OPERATOR",
    )
    grant_id = UUID(grant["id"])
    [request] = rows(
        world.tenant_id,
        select(approval_request).where(approval_request.c.subject_id == grant_id),
    )
    assert (
        request["subject_type"],
        request["status"],
        request["preparer_kind"],
        request["preparer_id"],
        request["id"],
    ) == (
        "SUPPORT_GRANT",
        "PENDING",
        "OPERATOR",
        UUID(operator["id"]),
        UUID(grant["approval_request_id"]),
    )
    steps = rows(
        world.tenant_id,
        select(approval_step.c.required_permission).where(
            approval_step.c.approval_request_id == request["id"]
        ),
    )
    assert steps == [{"required_permission": "support_grant.approve"}]
    notified = rows(
        world.tenant_id,
        select(
            notification.c.recipient_membership_id,
            notification.c.title,
            notification.c.body,
            notification.c.link_path,
        ).where(
            notification.c.kind == "SUPPORT_GRANT_REQUESTED",
            notification.c.subject_id == grant_id,
        ),
    )
    body = "Ops Tester requests read-only access from 13 Sep 2026 09:00 to 13 Sep 2026 17:00 UTC."
    assert sorted(notified, key=lambda row: str(row["recipient_membership_id"])) == sorted(
        (
            {
                "recipient_membership_id": admin,
                "title": "Support access requested",
                "body": body,
                "link_path": "/settings/support-access",
            }
            for admin in (world.tomas.member.membership_id, world.grace.membership_id)
        ),
        key=lambda row: str(row["recipient_membership_id"]),
    )
    [audited] = rows(
        world.tenant_id,
        select(audit_event.c.actor_kind, audit_event.c.approval_request_id).where(
            audit_event.c.action == "support_grant.request",
            audit_event.c.object_id == grant_id,
        ),
    )
    assert audited == {"actor_kind": "OPERATOR", "approval_request_id": request["id"]}


def test_grant_duration_limit(services: CliServices, world: World) -> None:
    operator = create_operator(services)
    result = request_grant(
        services,
        tenant_code=world.code,
        operator_email=operator["email"],
        valid_from="2026-09-13T09:00:00Z",
        valid_to="2026-09-16T10:00:00Z",
    )
    assert result.exit_code == 1, result.output
    problem = json.loads(result.stderr)
    assert problem["type"] == PROBLEM_BASE + "validation-failed"
    assert [(error["field"], error["rule_id"]) for error in problem["errors"]] == [
        ("valid_to", "T-PLT-33")
    ]
    assert result.stdout == ""
    assert rows(world.tenant_id, select(support_grant.c.id)) == []
    assert (
        rows(
            world.tenant_id,
            select(approval_request.c.id).where(approval_request.c.subject_type == "SUPPORT_GRANT"),
        )
        == []
    )
    # Exactly 72 hours is allowed.
    limit = request_grant(
        services,
        tenant_code=world.code,
        operator_email=operator["email"],
        valid_from="2026-09-13T09:00:00Z",
        valid_to="2026-09-16T09:00:00Z",
    )
    assert limit.exit_code == 0, limit.output


def test_expiry_ends_operator_sessions(
    app: FastAPI,
    clock: FrozenClock,
    keyring: KeyRing,
    services: CliServices,
    world: World,
    tmp_path: Path,
) -> None:
    operator = create_operator(services)
    signed = operator_signed_in(app, clock, operator["email"])
    grant_id = approved_grant(app, clock, services, world, operator["email"])
    selected = select_tenant(app, signed, world.tenant_id)
    assert selected.status_code == 200, selected.text
    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(tmp_path / "expiry"))

    # While the grant is in force nothing expires.
    support_grants.expire_due(runtime)
    assert rows(
        world.tenant_id, select(support_grant.c.status).where(support_grant.c.id == grant_id)
    ) == [{"status": "APPROVED"}]
    assert [row["end_reason"] for row in grant_sessions(grant_id)] == [None]

    clock.advance(timedelta(hours=7, minutes=1))
    assert support_grants.expire_due(runtime) >= 1
    assert rows(
        world.tenant_id, select(support_grant.c.status).where(support_grant.c.id == grant_id)
    ) == [{"status": "EXPIRED"}]
    assert [row["end_reason"] for row in grant_sessions(grant_id)] == ["REVOKED"]
    [expired] = rows(
        world.tenant_id,
        select(audit_event.c.actor_kind, audit_event.c.before, audit_event.c.after).where(
            audit_event.c.action == "support_grant.expire", audit_event.c.object_id == grant_id
        ),
    )
    assert expired == {
        "actor_kind": "SYSTEM",
        "before": {"status": "APPROVED"},
        "after": {"status": "EXPIRED"},
    }
