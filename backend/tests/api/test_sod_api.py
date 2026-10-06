"""API-R-07 SoD rules and exceptions (04 §15.3 API-R-07, T-PLT-13, T-PLT-14; PRD SM-04, SM-13,
ERR-22; SCREENS_B §9.10, §9.12; REQ-PLT-010; BUILD_SPEC PLF-19, BS1-D-24, BS1-D-26, BS1-D-29).

Tomas and Grace are Tenant Admins of a provisioned workspace, both enrolled in MFA; Lena is a member
holding Revenue Reviewer. Tomas requests exceptions and rule versions; Grace approves them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth import sod as sod_kernel
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    role,
    role_assignment,
    sod_exception,
    sod_rule,
    tenant,
)
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import Select, select, update
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, enrolled, member
from support.rows import insert_role_assignment

RULES = "/api/v1/sod-rules"
EXCEPTIONS = "/api/v1/sod-exceptions"
ASSIGNMENTS = "/api/v1/role-assignments"
APPROVALS = "/api/v1/approvals"
PROBLEM_BASE = "https://erev.dev/problems/"
# SCREENS_B §9.10 sample world J-22.7.
CONTROL = "Controller reviews every approval by Lena Fischer monthly using the approvals register."
REASON = "The second reviewer joined the team"
SOD_5_VERSION: Mapping[str, Any] = {
    "name": "authoring and approving the same configuration or SSP book version",
    "function_a_permissions": ["ssp.create", "config.author"],
    "function_b_permissions": ["config.approve", "ssp.approve"],
    "rationale": "SSP book versions are configuration under the same maker-checker rule.",
    "comment": "Extend SoD-5 to SSP books",
}


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor
    lena: Member

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    lena = colleague(tomas.tenant_id, "lena")
    with tenant_session(_context(tomas.tenant_id)) as session:
        for someone, code in ((tomas, "tenant_admin"), (grace, "tenant_admin")):
            insert_role_assignment(
                session,
                tenant_id=tomas.tenant_id,
                membership_id=someone.membership_id,
                role_code=code,
            )
        insert_role_assignment(
            session,
            tenant_id=tomas.tenant_id,
            membership_id=lena.membership_id,
            role_code="revenue_reviewer",
        )
    return World(tomas=enrolled(app, clock, tomas), grace=enrolled(app, clock, grace), lena=lena)


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None]]:
    return [(error["field"], error["rule_id"]) for error in response.json()["errors"]]


def rows(tenant_id: UUID, statement: Select[Any]) -> list[Mapping[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def role_id(tenant_id: UUID, code: str) -> str:
    [found] = rows(tenant_id, select(role.c.id).where(role.c.code == code))
    return str(found["id"])


def approve(app: FastAPI, request_id: str, approver: Actor) -> HttpResponse:
    detail = get(app, f"{APPROVALS}/{request_id}", approver)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    return post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        approver,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Reviewed the compensating control",
        },
    )


def exception_body(
    world: World, clock: FrozenClock, *, code: str = "SoD-3", days: int = 90
) -> dict[str, Any]:
    start = clock.now()
    return {
        "sod_rule_code": code,
        "membership_id": str(world.lena.membership_id),
        "compensating_control": CONTROL,
        "valid_from": start.isoformat(),
        "valid_to": (start + timedelta(days=days)).isoformat(),
        "comment": "Small team until a second reviewer joins",
    }


def approved_exception(
    app: FastAPI, world: World, clock: FrozenClock, *, code: str = "SoD-3"
) -> Mapping[str, Any]:
    """An exception for Lena, requested by Tomas and approved by Grace."""
    created = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock, code=code))
    assert created.status_code == 201, created.text
    approved = approve(app, created.json()["approval_request_id"], world.grace)
    assert approved.status_code == 200, approved.text
    return dict(created.json())


def test_request_and_approve_exception(app: FastAPI, world: World, clock: FrozenClock) -> None:
    too_long = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock, days=367))
    assert (too_long.status_code, slug(too_long)) == (422, "validation-failed"), too_long.text
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in too_long.json()["errors"]
    ] == [("valid_to", "T-PLT-14", "Choose a validity of at most 366 days.")]
    invalid = post(
        app,
        EXCEPTIONS,
        world.tomas,
        {
            **exception_body(world, clock),
            "sod_rule_code": "SoD-9",
            "compensating_control": "Reviewed",
            "comment": " ",
        },
    )
    assert (invalid.status_code, slug(invalid)) == (422, "validation-failed"), invalid.text
    assert fields(invalid) == [
        ("sod_rule_code", "T-PLT-13"),
        ("compensating_control", "BR-PLT-08"),
        ("comment", "T-PLT-14"),
    ]
    assert rows(world.tenant_id, select(sod_exception.c.id)) == []

    created = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock))
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["status"], body["sod_rule_code"], body["compensating_control"]) == (
        "REQUESTED",
        "SoD-3",
        CONTROL,
    )
    assert (body["approved_at"], body["created_by"]["id"]) == (
        None,
        str(world.tomas.member.user_id),
    )
    [request] = rows(
        world.tenant_id,
        select(approval_request).where(approval_request.c.subject_type == "SOD_EXCEPTION"),
    )
    assert (request["status"], request["subject_id"], str(request["id"])) == (
        "PENDING",
        UUID(body["id"]),
        body["approval_request_id"],
    )
    twice = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock))
    assert (twice.status_code, slug(twice)) == (409, "invalid-transition"), twice.text
    assert fields(twice) == [("sod_rule_code", "SM-13")]
    listed = get(app, EXCEPTIONS, world.tomas, status="REQUESTED")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [body["id"]]
    own = get(app, f"{APPROVALS}/{body['approval_request_id']}", world.tomas)
    assert own.json()["can_decide"] is False, own.text

    approved = approve(app, body["approval_request_id"], world.grace)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    [row] = rows(
        world.tenant_id,
        select(
            sod_exception.c.status, sod_exception.c.approved_at, sod_exception.c.approval_request_id
        ).where(sod_exception.c.id == UUID(body["id"])),
    )
    assert (row["status"], row["approved_at"], row["approval_request_id"]) == (
        "APPROVED",
        clock.now(),
        request["id"],
    )
    [event] = rows(
        world.tenant_id,
        select(audit_event.c.approval_request_id).where(
            audit_event.c.action == "sod_exception.approve",
            audit_event.c.object_id == UUID(body["id"]),
        ),
    )
    assert event["approval_request_id"] == request["id"]
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        [conflict] = sod_kernel.conflicts_for(
            session,
            world.lena.membership_id,
            adding_role_ids=[UUID(role_id(world.tenant_id, "revenue_accountant"))],
            at=clock.now(),
        )
    assert (conflict.rule_code, conflict.sod_exception_id) == ("SoD-3", UUID(body["id"]))


def test_revoke_exception(app: FastAPI, world: World, clock: FrozenClock) -> None:
    exception = approved_exception(app, world, clock)
    path = f"{EXCEPTIONS}/{exception['id']}/revoke"
    short = post(app, path, world.tomas, {"reason": "Joined"})
    assert (short.status_code, slug(short)) == (422, "validation-failed"), short.text
    assert fields(short) == [("reason", "BR-PLT-08")]

    revoked = post(app, path, world.tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text
    assert (revoked.json()["status"], revoked.json()["revoked_by"]["id"]) == (
        "REVOKED",
        str(world.tomas.member.user_id),
    )
    [row] = rows(
        world.tenant_id,
        select(
            sod_exception.c.status, sod_exception.c.revoked_at, sod_exception.c.revoked_by_kind
        ).where(sod_exception.c.id == UUID(exception["id"])),
    )
    assert (row["status"], row["revoked_at"], row["revoked_by_kind"]) == (
        "REVOKED",
        clock.now(),
        "USER",
    )
    again = post(app, path, world.tomas, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    assert fields(again) == [("status", "SM-13")]
    missing = post(app, f"{EXCEPTIONS}/{uuid4()}/revoke", world.tomas, {"reason": REASON})
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text

    rejected = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock, code="SoD-1"))
    assert rejected.status_code == 201, rejected.text
    decision = post(
        app,
        f"{APPROVALS}/{rejected.json()['approval_request_id']}/reject",
        world.grace,
        {"comment": "Lena needs no user administration."},
    )
    assert decision.status_code == 200, decision.text
    [closed] = rows(
        world.tenant_id,
        select(sod_exception.c.status).where(sod_exception.c.id == UUID(rejected.json()["id"])),
    )
    assert closed["status"] == "REJECTED"
    refused = post(
        app, f"{EXCEPTIONS}/{rejected.json()['id']}/revoke", world.tomas, {"reason": REASON}
    )
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text


def test_sod_rule_version_lifecycle(app: FastAPI, world: World, clock: FrozenClock) -> None:
    listed = get(app, RULES, world.tomas, status="PUBLISHED", count="true")
    assert listed.status_code == 200, listed.text
    assert listed.headers["X-Erev-Total-Count"] == "7"
    items = listed.json()["items"]
    assert [(item["code"], item["version_no"]) for item in items] == [
        (f"SoD-{number}", 1) for number in range(1, 8)
    ]
    [first] = [item for item in items if item["code"] == "SoD-5"]
    assert (first["function_a_permissions"], first["function_b_permissions"]) == (
        ["config.author"],
        ["config.approve"],
    )

    versions = f"{RULES}/SoD-5/versions"
    unknown = post(app, f"{RULES}/SoD-9/versions", world.tomas, SOD_5_VERSION)
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    invalid = post(
        app,
        versions,
        world.tomas,
        {
            **SOD_5_VERSION,
            "function_a_permissions": ["config.author", "config.fly"],
            "rationale": "",
        },
    )
    assert (invalid.status_code, slug(invalid)) == (422, "validation-failed"), invalid.text
    assert fields(invalid) == [("function_a_permissions[1]", "T-PLT-13"), ("rationale", "T-PLT-13")]
    unchanged = post(
        app,
        versions,
        world.tomas,
        {
            "name": first["name"],
            "function_a_permissions": first["function_a_permissions"],
            "function_b_permissions": first["function_b_permissions"],
            "rationale": first["rationale"],
        },
    )
    assert (unchanged.status_code, fields(unchanged)) == (422, [(None, "SM-04")]), unchanged.text

    created = post(app, versions, world.tomas, SOD_5_VERSION)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["code"], body["version_no"], body["status"], body["supersedes_version_id"]) == (
        "SoD-5",
        2,
        "SUBMITTED",
        first["id"],
    )
    assert body["function_a_permissions"] == ["config.author", "ssp.create"]
    [event] = rows(
        world.tenant_id,
        select(audit_event.c.detail).where(
            audit_event.c.action == "sod_rule.create", audit_event.c.object_id == UUID(body["id"])
        ),
    )
    assert event["detail"] == {"lifecycle": ["DRAFT", "TESTED", "SUBMITTED"]}
    [request] = rows(
        world.tenant_id,
        select(approval_request).where(approval_request.c.subject_type == "ROLE_CHANGE"),
    )
    assert (request["subject_id"], str(request["id"])) == (
        UUID(body["id"]),
        body["pending_approval_request_id"],
    )
    open_version = post(app, versions, world.tomas, SOD_5_VERSION)
    assert (open_version.status_code, slug(open_version)) == (409, "invalid-transition")
    assert fields(open_version) == [("code", "SM-04")]

    # A pending exception of SoD-5 covers the published version, so publishing voids it.
    pending = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock, code="SoD-5"))
    assert pending.status_code == 201, pending.text

    approved = approve(app, str(request["id"]), world.grace)
    assert approved.status_code == 200, approved.text
    stored = rows(
        world.tenant_id,
        select(
            sod_rule.c.version_no,
            sod_rule.c.status,
            sod_rule.c.effective_to,
            sod_rule.c.published_by,
            sod_rule.c.approval_request_id,
        )
        .where(sod_rule.c.code == "SoD-5")
        .order_by(sod_rule.c.version_no),
    )
    assert [tuple(row.values()) for row in stored] == [
        (1, "SUPERSEDED", clock.now(), None, None),
        (2, "PUBLISHED", None, world.grace.member.user_id, request["id"]),
    ]
    current = get(app, RULES, world.tomas, status="PUBLISHED", code="SoD-5")
    assert [
        (item["version_no"], item["function_b_permissions"], item["pending_approval_request_id"])
        for item in current.json()["items"]
    ] == [(2, ["config.approve", "ssp.approve"], None)]
    [voided] = rows(
        world.tenant_id,
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(pending.json()["approval_request_id"])
        ),
    )
    assert (voided["status"], voided["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    [closed] = rows(
        world.tenant_id,
        select(sod_exception.c.status).where(sod_exception.c.id == UUID(pending.json()["id"])),
    )
    assert closed["status"] == "REJECTED"


def test_role_assignment_with_approved_exception(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    accountant = role_id(world.tenant_id, "revenue_accountant")
    request_body = {"membership_id": str(world.lena.membership_id), "role_id": accountant}
    unusable = post(
        app, ASSIGNMENTS, world.tomas, {**request_body, "sod_exception_id": str(uuid4())}
    )
    assert (unusable.status_code, slug(unusable)) == (422, "validation-failed"), unusable.text
    assert fields(unusable) == [("sod_exception_id", "T-PLT-14")]
    blocked = post(app, ASSIGNMENTS, world.tomas, request_body)
    assert (blocked.status_code, fields(blocked)) == (409, [("role_id", "SoD-3")]), blocked.text

    other = approved_exception(app, world, clock, code="SoD-2")
    not_needed = post(
        app, ASSIGNMENTS, world.tomas, {**request_body, "sod_exception_id": other["id"]}
    )
    assert (not_needed.status_code, fields(not_needed)) == (422, [("sod_exception_id", "T-PLT-14")])

    exception = approved_exception(app, world, clock)
    requested = post(
        app, ASSIGNMENTS, world.tomas, {**request_body, "sod_exception_id": exception["id"]}
    )
    assert requested.status_code == 201, requested.text
    body = requested.json()
    assert (body["status"], body["sod_exception_id"], body["role"]["code"]) == (
        "REQUESTED",
        exception["id"],
        "revenue_accountant",
    )
    [request] = rows(
        world.tenant_id,
        select(approval_request.c.subject_type, approval_request.c.status).where(
            approval_request.c.id == UUID(body["approval_request_id"])
        ),
    )
    assert (request["subject_type"], request["status"]) == ("ROLE_ASSIGNMENT", "PENDING")

    approved = approve(app, body["approval_request_id"], world.grace)
    assert approved.status_code == 200, approved.text
    [row] = rows(
        world.tenant_id,
        select(role_assignment.c.id, role_assignment.c.sod_exception_id).where(
            role_assignment.c.membership_id == world.lena.membership_id,
            role_assignment.c.role_id == UUID(accountant),
        ),
    )
    assert (str(row["id"]), row["sod_exception_id"]) == (body["id"], UUID(exception["id"]))


# --- item SBX-COPY-OPEN-INVITATION-1, its second half: a person removed once is invited again
# (PRD SM-13 rev 1.201; 04 T-PLT-14 rev 1.293; the supervisor's ruling of 2026-10-02) ---

USERS = "/api/v1/users"


def test_an_exception_of_the_first_life_does_not_cover_the_member_invited_again(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """An exception was granted to circumstances that ended with the removal. A removal leaves
    an APPROVED one standing, and the SoD check of an invitation takes whatever is in force as
    cover without being named — so the invitation of the removed member ends the membership's
    exceptions first: the one in force is REVOKED by the inviter with its audit event, the one
    still waiting for approval is closed with its request, which has been stale since the
    removal. An invitation that is refused ends nothing.

    Fail-first (the invitation without that step): Lena, removed and invited again as Revenue
    Reviewer and Revenue Accountant together, was invited — SoD-3 covered by the exception of
    her first membership — and both exceptions stood."""
    in_force = approved_exception(app, world, clock)  # SoD-3, approved by Grace, 90 days
    waiting = post(app, EXCEPTIONS, world.tomas, exception_body(world, clock, code="SoD-2"))
    assert waiting.status_code == 201, waiting.text

    def state(exception_id: str) -> tuple[str, Any, Any]:
        [row] = rows(
            world.tenant_id,
            select(
                sod_exception.c.status, sod_exception.c.revoked_at, sod_exception.c.revoked_by
            ).where(sod_exception.c.id == UUID(exception_id)),
        )
        return str(row["status"]), row["revoked_at"], row["revoked_by"]

    def request_status(request_id: str) -> tuple[str, Any]:
        [row] = rows(
            world.tenant_id,
            select(approval_request.c.status, approval_request.c.void_reason).where(
                approval_request.c.id == UUID(request_id)
            ),
        )
        return str(row["status"]), row["void_reason"]

    def invitation(*codes: str) -> dict[str, Any]:
        return {
            "email": world.lena.email,
            "display_name": "Lena Fischer",
            "roles": [
                {
                    "role_id": role_id(world.tenant_id, code),
                    "is_all_entities": True,
                    "entity_codes": [],
                }
                for code in codes
            ],
        }

    lena = f"{USERS}/{world.lena.membership_id}"
    removed = post(app, f"{lena}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    # A removal leaves the exceptions as they are (04 T-PLT-14 rev 1.293 says so).
    assert state(in_force["id"]) == ("APPROVED", None, None)
    assert state(waiting.json()["id"]) == ("REQUESTED", None, None)
    assert request_status(waiting.json()["approval_request_id"]) == ("PENDING", None)

    clock.advance(timedelta(minutes=1))
    both = post(app, USERS, world.tomas, invitation("revenue_reviewer", "revenue_accountant"))
    assert both.status_code == 409, both.text
    assert (slug(both), fields(both)) == ("sod-conflict", [("roles", "SoD-3")])
    # The refusal ended nothing: the member is removed still, and so stand the exceptions.
    assert state(in_force["id"]) == ("APPROVED", None, None)
    assert state(waiting.json()["id"]) == ("REQUESTED", None, None)

    again = post(app, USERS, world.tomas, invitation("revenue_reviewer"))
    assert again.status_code == 201, again.text
    assert (again.json()["id"], again.json()["status"]) == (
        str(world.lena.membership_id),
        "INVITED",
    )
    assert state(in_force["id"]) == ("REVOKED", clock.now(), world.tomas.member.user_id)
    assert state(waiting.json()["id"]) == ("REJECTED", None, None)
    assert request_status(waiting.json()["approval_request_id"]) == ("VOIDED", "STALE_SUBJECT")
    [revocation] = rows(
        world.tenant_id,
        select(audit_event.c.comment, audit_event.c.actor_id).where(
            audit_event.c.action == "sod_exception.revoke",
            audit_event.c.object_id == UUID(in_force["id"]),
        ),
    )
    assert (revocation["comment"], revocation["actor_id"]) == (
        "The member was removed and is invited again.",
        world.tomas.member.user_id,
    )
