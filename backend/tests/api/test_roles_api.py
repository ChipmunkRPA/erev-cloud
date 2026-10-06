"""API-R-06 roles, permissions and role assignments (04 §15.3 API-R-06, T-PLT-09 to T-PLT-12,
SMAP-14; PRD SM-04, SM-13, ERR-22; SCREENS_B §9.11; REQ-PLT-008 to REQ-PLT-010; CTL-034;
BUILD_SPEC PLF-18, BS1-D-24, BS1-D-31).

Tomas and Grace are Tenant Admins of a provisioned workspace, both enrolled in MFA; Lena is a member
without roles. Tomas is the bootstrap Tenant Admin. Role changes always wait for another admin, and
so do the role assignments Tomas requests while Grace holds her role; rule AUTO-BOOTSTRAP approves
them only while setup is incomplete and nobody else can approve access (04 §14.3 item 3;
supervisor ruling R-38 (iv) addendum), the workspace ``without_second_admin`` leaves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import CATALOGUE, DEFAULT_ROLES, effective_grants
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    role,
    role_assignment,
    role_permission,
    tenant,
)
from erev_api.main import create_app
from erev_engine.canonical import sha256_hex
from fastapi import FastAPI
from sqlalchemy import Select, select, update
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, Member, colleague, cookie_headers, enrolled, member
from support.rows import (
    insert_approval_delegation,
    insert_role_assignment,
    revoke_role_assignments,
)

PERMISSIONS = "/api/v1/permissions"
ROLES = "/api/v1/roles"
ASSIGNMENTS = "/api/v1/role-assignments"
APPROVALS = "/api/v1/approvals"
PROBLEM_BASE = "https://erev.dev/problems/"
REASON = "Moved to the deal desk team"
DEAL_DESK: Mapping[str, Any] = {
    "code": "deal_desk_analyst",
    "name": "Deal desk analyst",
    "permissions": ["scenario.use"],
}
# PRD ERR-22 with the BS1-D-26 name of SoD-3.
SOD_3 = (
    "Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets one person "
    "create and approve the same contract or modification."
)


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
    with tenant_session(_context(tomas.tenant_id)) as session:
        for someone in (tomas, grace):
            insert_role_assignment(
                session,
                tenant_id=tomas.tenant_id,
                membership_id=someone.membership_id,
                role_code="tenant_admin",
            )
    return World(
        tomas=enrolled(app, clock, tomas),
        grace=enrolled(app, clock, grace),
        lena=colleague(tomas.tenant_id, "lena"),
    )


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def post_if_match(
    app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any], etag: str
) -> HttpResponse:
    headers = cookie_headers(actor.token, actor.csrf_token, **{"If-Match": etag})
    return call(app, "POST", path, json=json, headers=headers)


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str, str | None]]:
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
            "comment": "Reviewed the permission list",
        },
    )


def created_role(app: FastAPI, world: World) -> Mapping[str, Any]:
    """The deal desk analyst role, created by Tomas and approved by Grace."""
    created = post(app, ROLES, world.tomas, DEAL_DESK)
    assert created.status_code == 201, created.text
    approved = approve(app, created.json()["pending_approval_request_id"], world.grace)
    assert approved.status_code == 200, approved.text
    return dict(created.json())


def without_second_admin(world: World, clock: FrozenClock) -> None:
    """Grace's Tenant Admin role ends, so nobody but Tomas can approve access."""
    with tenant_session(_context(world.tenant_id)) as session:
        revoke_role_assignments(
            session,
            tenant_id=world.tenant_id,
            membership_id=world.grace.member.membership_id,
            at=clock.now(),
        )


def assignment(world: World, code_or_id: str) -> dict[str, str]:
    value = code_or_id if "-" in code_or_id else role_id(world.tenant_id, code_or_id)
    return {"membership_id": str(world.lena.membership_id), "role_id": value}


def test_permissions_catalogue(app: FastAPI, world: World) -> None:
    response = get(app, PERMISSIONS, world.tomas)
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"]
    assert (len(items), body["next_cursor"]) == (52, None)
    assert {tuple(sorted(item)) for item in items} == {
        ("area", "code", "description", "is_access_admin", "is_approval", "requires_mfa")
    }
    assert [item["code"] for item in items] == sorted(spec.code for spec in CATALOGUE)
    [access] = [item for item in items if item["code"] == "access.approve"]
    assert (
        access["area"],
        access["is_approval"],
        access["is_access_admin"],
        access["requires_mfa"],
    ) == ("PLT", True, True, True)


def test_create_custom_role_under_approval(app: FastAPI, world: World) -> None:
    response = post(app, ROLES, world.tomas, DEAL_DESK)
    assert response.status_code == 201, response.text
    body = response.json()
    assert response.headers["Location"] == f"{ROLES}/{body['id']}"
    assert response.headers["ETag"] == '"r1"'
    assert (body["code"], body["is_system"], body["is_active"], body["permissions"]) == (
        "deal_desk_analyst",
        False,
        False,
        [],
    )
    new_role = UUID(body["id"])
    [request] = rows(
        world.tenant_id,
        select(approval_request).where(approval_request.c.subject_type == "ROLE_CHANGE"),
    )
    assert (request["status"], request["subject_id"], str(request["id"])) == (
        "PENDING",
        new_role,
        body["pending_approval_request_id"],
    )
    assert (
        rows(world.tenant_id, select(role_permission).where(role_permission.c.role_id == new_role))
        == []
    )

    approved = approve(app, str(request["id"]), world.grace)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    granted = rows(
        world.tenant_id,
        select(role_permission.c.permission_code).where(role_permission.c.role_id == new_role),
    )
    assert [row["permission_code"] for row in granted] == ["scenario.use"]
    [stored] = rows(
        world.tenant_id,
        select(role.c.is_active, role.c.content_sha256).where(role.c.id == new_role),
    )
    assert stored["is_active"] is True
    assert stored["content_sha256"] == sha256_hex(["scenario.use"])
    [event] = rows(
        world.tenant_id,
        select(audit_event.c.approval_request_id, audit_event.c.diff, audit_event.c.detail).where(
            audit_event.c.action == "role.change", audit_event.c.object_id == new_role
        ),
    )
    assert event["approval_request_id"] == request["id"]
    assert event["detail"] == {"permissions_added": ["scenario.use"], "permissions_removed": []}
    assert {entry["path"] for entry in event["diff"]} == {
        "content_sha256",
        "is_active",
        "permissions",
    }

    detail = get(app, f"{ROLES}/{new_role}", world.tomas)
    assert detail.status_code == 200, detail.text
    assert (
        detail.json()["is_active"],
        detail.json()["permissions"],
        detail.json()["pending_approval_request_id"],
    ) == (True, ["scenario.use"], None)
    assert detail.headers["ETag"] == '"r2"'


def test_system_role_cannot_change(app: FastAPI, world: World) -> None:
    controller = role_id(world.tenant_id, "controller")
    detail = get(app, f"{ROLES}/{controller}", world.tomas)
    assert detail.status_code == 200, detail.text
    assert (detail.json()["is_system"], detail.json()["permissions"]) == (
        True,
        sorted(DEFAULT_ROLES["controller"]),
    )

    response = post_if_match(
        app,
        f"{ROLES}/{controller}/propose-change",
        world.tomas,
        {"permissions": ["contract.read"], "comment": "Narrow the controller role"},
        detail.headers["ETag"],
    )
    assert (response.status_code, slug(response)) == (409, "invalid-transition"), response.text
    assert response.json()["detail"] == "System roles cannot change."
    assert (
        rows(
            world.tenant_id,
            select(approval_request.c.id).where(approval_request.c.subject_type == "ROLE_CHANGE"),
        )
        == []
    )


@pytest.mark.control("CTL-034")
def test_role_assignment_sod_block(app: FastAPI, world: World) -> None:
    with tenant_session(_context(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=world.lena.membership_id,
            role_code="revenue_reviewer",
        )

    response = post(app, ASSIGNMENTS, world.tomas, assignment(world, "revenue_accountant"))
    assert (response.status_code, slug(response)) == (409, "sod-conflict"), response.text
    [error] = response.json()["errors"]
    assert (error["field"], error["rule_id"], error["message"]) == ("role_id", "SoD-3", SOD_3)

    assert (
        rows(
            world.tenant_id,
            select(approval_request.c.id).where(
                approval_request.c.preparer_id == world.tomas.member.user_id
            ),
        )
        == []
    )
    held = rows(
        world.tenant_id,
        select(role_assignment.c.role_id).where(
            role_assignment.c.membership_id == world.lena.membership_id
        ),
    )
    assert [str(row["role_id"]) for row in held] == [role_id(world.tenant_id, "revenue_reviewer")]


@pytest.mark.control("CTL-034")
def test_r_111_4_a_role_assignment_counts_a_delegation_the_member_holds(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 6 (ruling R-111 (4)); 04
    T-PLT-21 rev 1.189. Lena was delegated ``contract.approve``; the request to make her a
    Revenue Accountant assembles SoD-3 in the other order — the approval first, the preparing
    role second — and was accepted, because the check read role grants only. It is refused by
    the rule's name; a delegation that has ended counts for nothing (positive control)."""
    now = clock.now()
    with tenant_session(_context(world.tenant_id)) as session:
        ended = insert_approval_delegation(
            session,
            tenant_id=world.tenant_id,
            delegator_membership_id=world.grace.member.membership_id,
            delegate_membership_id=world.lena.membership_id,
            valid_from=now - timedelta(days=40),
            valid_to=now - timedelta(days=10),
        )
    accepted = post(app, ASSIGNMENTS, world.tomas, assignment(world, "viewer"))
    assert accepted.status_code == 201, accepted.text  # nothing she holds conflicts
    with tenant_session(_context(world.tenant_id)) as session:
        standing = insert_approval_delegation(
            session,
            tenant_id=world.tenant_id,
            delegator_membership_id=world.grace.member.membership_id,
            delegate_membership_id=world.lena.membership_id,
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=30),
        )
    assert ended != standing

    refused = post(app, ASSIGNMENTS, world.tomas, assignment(world, "revenue_accountant"))
    assert (refused.status_code, slug(refused)) == (409, "sod-conflict"), refused.text
    [error] = refused.json()["errors"]
    assert (error["field"], error["rule_id"], error["message"]) == ("role_id", "SoD-3", SOD_3)
    # A role no rule sets against the delegated approval is still requested.
    allowed = post(app, ASSIGNMENTS, world.tomas, assignment(world, "auditor"))
    assert allowed.status_code == 201, allowed.text


@pytest.mark.control("CTL-034")
def test_ctl_034_second_pending_grant_refused_at_approval(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    for code in ("revenue_accountant", "revenue_reviewer"):
        response = post(
            app, ASSIGNMENTS, world.tomas, {**assignment(world, code), "is_all_entities": True}
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "REQUESTED"
    requests = select(approval_request.c.id, approval_request.c.status).where(
        approval_request.c.subject_type == "ROLE_ASSIGNMENT",
        approval_request.c.preparer_id == world.tomas.member.user_id,
    )
    first, second = rows(world.tenant_id, requests.order_by(approval_request.c.request_no))

    approved = approve(app, str(first["id"]), world.grace)
    assert approved.status_code == 200, approved.text
    refused = approve(app, str(second["id"]), world.grace)
    assert (refused.status_code, slug(refused)) == (409, "sod-conflict"), refused.text
    assert [error["rule_id"] for error in refused.json()["errors"]] == ["SoD-3"]

    statuses = rows(world.tenant_id, requests.order_by(approval_request.c.request_no))
    assert [row["status"] for row in statuses] == ["APPROVED", "PENDING"]
    held = rows(
        world.tenant_id,
        select(role_assignment.c.id).where(
            role_assignment.c.membership_id == world.lena.membership_id,
            role_assignment.c.revoked_at.is_(None),
        ),
    )
    assert len(held) == 1


def test_revoke_role_assignment(app: FastAPI, world: World, clock: FrozenClock) -> None:
    without_second_admin(world, clock)
    assigned = post(app, ASSIGNMENTS, world.tomas, assignment(world, "viewer"))
    assert assigned.status_code == 201, assigned.text
    body = assigned.json()
    assert (body["status"], body["setup_grant"], body["role"]["code"]) == ("ACTIVE", True, "viewer")
    assignment_id = body["id"]
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        before = effective_grants(session, world.lena.membership_id, at=clock.now())
    assert before.permissions == DEFAULT_ROLES["viewer"]

    path = f"{ASSIGNMENTS}/{assignment_id}/revoke"
    short = post(app, path, world.tomas, {"reason": "Moved"})
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
            role_assignment.c.revoked_at,
            role_assignment.c.revoked_by,
            role_assignment.c.revoked_by_kind,
        ).where(role_assignment.c.id == UUID(assignment_id)),
    )
    assert (row["revoked_at"], row["revoked_by"], row["revoked_by_kind"]) == (
        clock.now(),
        world.tomas.member.user_id,
        "USER",
    )
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        after = effective_grants(session, world.lena.membership_id, at=clock.now())
    assert (after.roles, after.permissions) == ((), frozenset())

    again = post(app, path, world.tomas, {"reason": REASON})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text
    listed = get(app, ASSIGNMENTS, world.tomas, membership_id=str(world.lena.membership_id))
    assert listed.status_code == 200, listed.text
    assert [(item["id"], item["status"]) for item in listed.json()["items"]] == [
        (assignment_id, "REVOKED")
    ]
    own = [
        item["id"]
        for item in get(
            app, ASSIGNMENTS, world.tomas, membership_id=str(world.tomas.member.membership_id)
        ).json()["items"]
    ]
    refused = post(app, f"{ASSIGNMENTS}/{own[0]}/revoke", world.tomas, {"reason": REASON})
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text


def test_role_change_voids_pending_assignment(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    created = created_role(app, world)
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    requested = post(app, ASSIGNMENTS, world.tomas, assignment(world, str(created["id"])))
    assert requested.status_code == 201, requested.text
    assert (requested.json()["status"], requested.json()["valid_from"]) == ("REQUESTED", None)
    request_id = requested.json()["approval_request_id"]
    twice = post(app, ASSIGNMENTS, world.tomas, assignment(world, str(created["id"])))
    assert (twice.status_code, slug(twice)) == (409, "invalid-transition"), twice.text
    assert fields(twice) == [("role_id", "SM-13")]

    path = f"{ROLES}/{created['id']}"
    etag = get(app, path, world.tomas).headers["ETag"]
    change = {"permissions": ["scenario.use", "ai.use"], "comment": "Deal desk uses AI summaries"}
    missing = post(app, f"{path}/propose-change", world.tomas, change)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    unchanged = post_if_match(
        app, f"{path}/propose-change", world.tomas, {"permissions": ["scenario.use"]}, etag
    )
    assert (unchanged.status_code, slug(unchanged)) == (422, "validation-failed"), unchanged.text
    assert fields(unchanged) == [("permissions", "T-PLT-12")]

    proposed = post_if_match(app, f"{path}/propose-change", world.tomas, change, etag)
    assert proposed.status_code == 200, proposed.text
    change_id = proposed.json()["pending_approval_request_id"]
    assert change_id is not None
    pending = post_if_match(app, f"{path}/propose-change", world.tomas, change, etag)
    assert (pending.status_code, slug(pending)) == (409, "invalid-transition"), pending.text

    approved = approve(app, change_id, world.grace)
    assert approved.status_code == 200, approved.text
    [voided] = rows(
        world.tenant_id,
        select(approval_request.c.status, approval_request.c.void_reason).where(
            approval_request.c.id == UUID(request_id)
        ),
    )
    assert (voided["status"], voided["void_reason"]) == ("VOIDED", "STALE_SUBJECT")
    assert get(app, path, world.tomas).json()["permissions"] == ["ai.use", "scenario.use"]


def test_role_list_validation_and_change_sod_check(app: FastAPI, world: World) -> None:
    listed = get(app, ROLES, world.tomas, count="true")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert listed.headers["X-Erev-Total-Count"] == "10"
    assert {item["code"]: item["permissions"] for item in items} == {
        code: sorted(codes) for code, codes in DEFAULT_ROLES.items()
    }
    assert all(item["is_system"] and item["is_active"] for item in items)
    assert {item["code"]: item["member_count"] for item in items}["tenant_admin"] == 2

    invalid = post(
        app,
        ROLES,
        world.tomas,
        {
            "code": "Deal desk",
            "name": " ",
            "permissions": ["scenario.use", "scenario.fly", "scenario.use"],
        },
    )
    assert (invalid.status_code, slug(invalid)) == (422, "validation-failed"), invalid.text
    assert fields(invalid) == [
        ("code", "T-PLT-09"),
        ("name", "T-PLT-09"),
        ("permissions[1]", "T-PLT-12"),
        ("permissions[2]", "T-PLT-12"),
    ]
    taken = post(app, ROLES, world.tomas, {**DEAL_DESK, "code": "controller"})
    assert (taken.status_code, fields(taken)) == (422, [("code", "T-PLT-09")]), taken.text

    created = created_role(app, world)
    with tenant_session(_context(world.tenant_id)) as session:
        for code in ("revenue_reviewer", "deal_desk_analyst"):
            insert_role_assignment(
                session,
                tenant_id=world.tenant_id,
                membership_id=world.lena.membership_id,
                role_code=code,
            )
    path = f"{ROLES}/{created['id']}"
    detail = get(app, path, world.tomas)
    assert detail.json()["member_count"] == 1, detail.text
    conflict = post_if_match(
        app,
        f"{path}/propose-change",
        world.tomas,
        {"permissions": ["scenario.use", "contract.create"]},
        detail.headers["ETag"],
    )
    assert (conflict.status_code, slug(conflict)) == (409, "sod-conflict"), conflict.text
    assert fields(conflict) == [("permissions", "SoD-3")]


# --- supervisor ruling R-63 (e): a role assignment for named entities (03 REQ-PLT-012) ------------


def denials(world: World) -> list[tuple[str, str, UUID | None, dict[str, Any]]]:
    """The DENIED audit events of the workspace in chain order: the action, the object and the
    detail of each (DG-KRN-AUTH-05)."""
    found = rows(
        world.tenant_id,
        select(
            audit_event.c.action,
            audit_event.c.object_type,
            audit_event.c.object_id,
            audit_event.c.detail,
        )
        .where(audit_event.c.outcome == "DENIED")
        .order_by(audit_event.c.chain_seq),
    )
    return [
        (str(row["action"]), str(row["object_type"]), row["object_id"], dict(row["detail"]))
        for row in found
    ]


def legal_entities(app: FastAPI, world: World, *codes: str) -> dict[str, str]:
    """Legal entities of the workspace created through the product by a Revenue Accountant, the
    role that holds the reference commands; code → id."""
    from support.reference import calendar, entity, holding

    maya = holding(app, colleague(world.tenant_id, "maya"), "revenue_accountant")
    calendar_id = calendar(app, maya)
    return {
        code: str(entity(app, maya, code=code, calendar_id=calendar_id)["id"]) for code in codes
    }


def scoped(world: World, code: str, *entity_codes: str) -> dict[str, Any]:
    return {**assignment(world, code), "is_all_entities": False, "entity_codes": list(entity_codes)}


def test_role_assignment_for_named_entities(app: FastAPI, world: World, clock: FrozenClock) -> None:
    """``POST /role-assignments`` for named entities (T-PLT-10; REQ-PLT-012): the request is
    answered with the entities by code, the row holds their ids (DB-12 validates them), the list
    and the member's grants state the scope, and the assignment is revoked as any other.
    Before: 422 ``EREV-REF-002`` for every entity code, and a list holding such a row — one
    inserted as the security proofs inserted theirs — answered 500."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-UK", "AVM-US")
    without_second_admin(world, clock)  # the setup grant: nobody but Tomas approves access
    assigned = post(app, ASSIGNMENTS, world.tomas, scoped(world, "viewer", "AVM-UK", "AVM-DE"))
    assert assigned.status_code == 201, assigned.text
    body = assigned.json()
    # setup is incomplete: rule AUTO-BOOTSTRAP approved it, and the row exists
    assert (body["status"], body["setup_grant"], body["is_all_entities"]) == ("ACTIVE", True, False)
    assert [ref["code"] for ref in body["entities"]] == ["AVM-DE", "AVM-UK"]
    [row] = rows(
        world.tenant_id,
        select(role_assignment.c.is_all_entities, role_assignment.c.entity_ids).where(
            role_assignment.c.id == UUID(body["id"])
        ),
    )
    assert row["is_all_entities"] is False
    assert sorted(str(value) for value in row["entity_ids"]) == sorted(
        [ids["AVM-DE"], ids["AVM-UK"]]
    )
    listed = get(app, ASSIGNMENTS, world.tomas, membership_id=str(world.lena.membership_id))
    assert listed.status_code == 200, listed.text
    assert [
        (item["status"], item["is_all_entities"], [ref["code"] for ref in item["entities"]])
        for item in listed.json()["items"]
    ] == [("ACTIVE", False, ["AVM-DE", "AVM-UK"])]
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        grants = effective_grants(session, world.lena.membership_id, at=clock.now())
    held = frozenset({UUID(ids["AVM-DE"]), UUID(ids["AVM-UK"])})
    assert grants.permissions == DEFAULT_ROLES["viewer"]
    assert set(grants.permission_scopes.values()) == {held}
    assert set(grants.entity_scope) == set(held)
    revoked = post(app, f"{ASSIGNMENTS}/{body['id']}/revoke", world.tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text
    assert (revoked.json()["status"], [ref["code"] for ref in revoked.json()["entities"]]) == (
        "REVOKED",
        ["AVM-DE", "AVM-UK"],
    )


def test_role_assignment_entity_scope_is_refused_by_name(app: FastAPI, world: World) -> None:
    """One shape, and codes that name legal entities; nothing is requested for a refusal."""
    legal_entities(app, world, "AVM-DE")
    before = rows(world.tenant_id, select(approval_request.c.id))  # the accountant's own role
    cases = [
        ({"is_all_entities": True, "entity_codes": ["AVM-DE"]}, "T-PLT-10"),
        ({"is_all_entities": False, "entity_codes": []}, "T-PLT-10"),
        ({"is_all_entities": False, "entity_codes": ["AVM-FR"]}, "EREV-REF-002"),
        ({"is_all_entities": False, "entity_codes": ["AVM-DE", "AVM-FR"]}, "EREV-REF-002"),
    ]
    for scope, rule in cases:
        response = post(app, ASSIGNMENTS, world.tomas, {**assignment(world, "viewer"), **scope})
        assert (response.status_code, slug(response)) == (422, "validation-failed"), response.text
        assert fields(response) == [("entity_codes", rule)], scope
    assert rows(world.tenant_id, select(approval_request.c.id)) == before
    assert (
        rows(
            world.tenant_id,
            select(role_assignment.c.id).where(
                role_assignment.c.membership_id == world.lena.membership_id
            ),
        )
        == []
    )
    # Tomas grants for all entities: none of these reached beyond his access, so none is a denial
    assert denials(world) == []


def test_pending_request_for_named_entities_names_them(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """After setup the request waits for the second admin: the requested assignment, the pending
    role of the member and the approval's summary name the entities (PRD J-22.1)."""
    legal_entities(app, world, "AVM-DE")
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    requested = post(app, ASSIGNMENTS, world.tomas, scoped(world, "revenue_reviewer", "AVM-DE"))
    assert requested.status_code == 201, requested.text
    body = requested.json()
    assert (body["status"], [ref["code"] for ref in body["entities"]]) == ("REQUESTED", ["AVM-DE"])
    detail = get(app, f"{APPROVALS}/{body['approval_request_id']}", world.grace)
    assert detail.status_code == 200, detail.text
    assert detail.json()["summary"] == "Grant Revenue Reviewer to Lena for AVM-DE"
    approved = approve(app, body["approval_request_id"], world.grace)
    assert approved.status_code == 200, approved.text
    listed = get(app, ASSIGNMENTS, world.tomas, membership_id=str(world.lena.membership_id))
    assert [
        (item["status"], [ref["code"] for ref in item["entities"]])
        for item in listed.json()["items"]
    ] == [("ACTIVE", ["AVM-DE"])]


# --- supervisor ruling R-115 (c): a command on an assignment needs its scope ----------------------

ASSIGNMENT_BEYOND_SCOPE = (
    "This role assignment covers entities beyond your own access. An administrator whose access "
    "covers every entity it names must change it."
)


def test_revoke_needs_the_scope_of_the_assignment(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """REQ-PLT-012 on what is already granted: Dieter is Tenant Admin for AVM-DE, granted through
    the product. He revokes an assignment for AVM-DE. One for AVM-US, one that names AVM-DE and
    AVM-US and one for all entities answer him 403 by name (rule ``T-PLT-10``), name no entity
    and stay as they are — before, he revoked the Controller of every entity. What he reads of
    them is the entities his session sees. Tomas, administrator of all entities, revokes each."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")

    def grant(who: Member, code: str, *entity_codes: str) -> str:
        response = post(
            app,
            ASSIGNMENTS,
            world.tomas,
            {
                "membership_id": str(who.membership_id),
                "role_id": role_id(world.tenant_id, code),
                "is_all_entities": not entity_codes,
                "entity_codes": list(entity_codes),
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "ACTIVE", response.text
        return str(response.json()["id"])

    # R-38 (iv) with its addendum; R-66 (2), R-73; 04 §14.3 item 3: rule AUTO-BOOTSTRAP approves
    # a grant of Tomas's only while nobody else has held access.approve for its entities —
    # Grace's role for all entities ends first, and Dieter is granted his for AVM-DE last.
    without_second_admin(world, clock)
    inside = grant(world.lena, "viewer", "AVM-DE")
    outside = {
        "another entity": grant(colleague(world.tenant_id, "uma"), "viewer", "AVM-US"),
        "one entity beyond": grant(colleague(world.tenant_id, "mio"), "viewer", "AVM-DE", "AVM-US"),
        "all entities": grant(colleague(world.tenant_id, "carla"), "controller"),
    }
    dieter_member = colleague(world.tenant_id, "dieter")
    grant(dieter_member, "tenant_admin", "AVM-DE")
    dieter = enrolled(app, clock, dieter_member)

    listed = get(app, ASSIGNMENTS, dieter, limit="200")
    assert listed.status_code == 200, listed.text
    shown = {
        item["id"]: (item["is_all_entities"], [ref["code"] for ref in item["entities"]])
        for item in listed.json()["items"]
    }
    assert shown[inside] == (False, ["AVM-DE"])
    assert shown[outside["another entity"]] == (False, [])
    assert shown[outside["one entity beyond"]] == (False, ["AVM-DE"])
    assert shown[outside["all entities"]] == (True, [])

    revoked = post(app, f"{ASSIGNMENTS}/{inside}/revoke", dieter, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "REVOKED"
    for case, assignment_id in outside.items():
        refused = post(app, f"{ASSIGNMENTS}/{assignment_id}/revoke", dieter, {"reason": REASON})
        assert (refused.status_code, slug(refused)) == (403, "forbidden"), (case, refused.text)
        assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
            ("T-PLT-10", ASSIGNMENT_BEYOND_SCOPE)
        ], case
        assert "AVM-US" not in refused.text and ids["AVM-US"] not in refused.text, case
    # each refusal is the DENIED event of the revocation it refused (DG-KRN-AUTH-05)
    assert denials(world) == [
        (
            "role_assignment.revoke",
            "role_assignment",
            UUID(assignment_id),
            {"permission": "role.manage", "rule_id": "T-PLT-10"},
        )
        for assignment_id in outside.values()
    ]
    kept = rows(
        world.tenant_id,
        select(role_assignment.c.id).where(
            role_assignment.c.id.in_([UUID(value) for value in outside.values()]),
            role_assignment.c.revoked_at.is_(None),
        ),
    )
    assert len(kept) == 3
    # A request of his that reaches beyond his own access — an entity he does not cover, a code
    # that names nothing, all entities — answers 422 as for anyone and is a DENIED event of the
    # assignment for that member; no entity is named, and the three answers that name codes
    # are one answer.
    reached = [
        post(app, ASSIGNMENTS, dieter, {**assignment(world, "viewer"), **asked})
        for asked in (
            {"is_all_entities": False, "entity_codes": ["AVM-US"]},
            {"is_all_entities": False, "entity_codes": ["AVM-FR"]},
            {"is_all_entities": True, "entity_codes": []},
        )
    ]
    assert [(response.status_code, fields(response)) for response in reached] == [
        (422, [("entity_codes", "EREV-REF-002")]),
        (422, [("entity_codes", "EREV-REF-002")]),
        (422, [("is_all_entities", "T-PLT-10")]),
    ]
    assert reached[0].json()["errors"] == reached[1].json()["errors"]
    for_lena = {"permission": "role.manage", "rule_id": "T-PLT-10"} | {
        "membership_id": str(world.lena.membership_id)
    }
    assert denials(world)[3:] == [
        ("role_assignment.create", "role_assignment", None, for_lena),
        ("role_assignment.create", "role_assignment", None, for_lena),
        ("role_assignment.create", "role_assignment", None, {**for_lena, "scope": "*"}),
    ]

    for case, assignment_id in outside.items():
        done = post(app, f"{ASSIGNMENTS}/{assignment_id}/revoke", world.tomas, {"reason": REASON})
        assert done.status_code == 200, (case, done.text)
        assert done.json()["status"] == "REVOKED"


# --- supervisor ruling R-115 (c): a role's definition is a tenant-wide act ------------------------

DEFINITION_BEYOND_SCOPE = (
    "A role's definition applies to every entity. Your own access covers named entities only; an "
    "administrator of all entities must make this change."
)


def test_a_roles_definition_is_changed_by_an_administrator_of_all_entities(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """A role is held, or may be held, for every entity, so its definition is not an act of one
    entity's administrator: ``POST /roles`` and ``POST /roles/{id}/propose-change`` need
    ``role.manage`` for all entities. Dieter, Tenant Admin for AVM-DE, is refused by name (403,
    rule ``T-PLT-10``) and nothing is requested; Tomas makes both. Before: the commands passed
    for ``role.manage`` held for any entity (DG-KRN-AUTH-04)."""
    legal_entities(app, world, "AVM-DE")
    dieter_member = colleague(world.tenant_id, "dieter")
    granted = post(
        app,
        ASSIGNMENTS,
        world.tomas,
        {
            "membership_id": str(dieter_member.membership_id),
            "role_id": role_id(world.tenant_id, "tenant_admin"),
            "is_all_entities": False,
            "entity_codes": ["AVM-DE"],
        },
    )
    assert granted.status_code == 201, granted.text
    # Grace is the second administrator of this world, so the grant waits for her (R-38 (iv)).
    decided = approve(app, granted.json()["approval_request_id"], world.grace)
    assert decided.status_code == 200, decided.text
    dieter = enrolled(app, clock, dieter_member)

    def by_name(response: HttpResponse) -> None:
        assert (response.status_code, slug(response)) == (403, "forbidden"), response.text
        assert [(error["rule_id"], error["message"]) for error in response.json()["errors"]] == [
            ("T-PLT-10", DEFINITION_BEYOND_SCOPE)
        ]

    requests = select(approval_request.c.id).where(approval_request.c.subject_type == "ROLE_CHANGE")
    by_name(post(app, ROLES, dieter, DEAL_DESK))
    assert rows(world.tenant_id, select(role.c.id).where(role.c.code == DEAL_DESK["code"])) == []
    assert rows(world.tenant_id, requests) == []

    created = created_role(app, world)  # Tomas creates it, Grace approves
    path = f"{ROLES}/{created['id']}"
    shown = get(app, path, dieter)
    assert shown.status_code == 200, shown.text  # the definition is his to read
    change = {"permissions": ["scenario.use", "ai.use"], "comment": "Deal desk uses AI summaries"}
    before = rows(world.tenant_id, requests)
    by_name(post_if_match(app, f"{path}/propose-change", dieter, change, shown.headers["ETag"]))
    assert rows(world.tenant_id, requests) == before
    # both refusals are DENIED events that say the permission is needed for all entities
    for_all = {"permission": "role.manage", "rule_id": "T-PLT-10", "scope": "*"}
    assert denials(world) == [
        ("role.create", "role", None, for_all),
        ("approval_request.submit", "role", UUID(created["id"]), for_all),
    ]
    proposed = post_if_match(
        app,
        f"{path}/propose-change",
        world.tomas,
        change,
        get(app, path, world.tomas).headers["ETag"],
    )
    assert proposed.status_code == 200, proposed.text


# --- item USER-ROLE-ENTITY-COUNT-1 (04 T-PLT-10 rev 1.202): an assignment counts its entities -----


def counted(item: Mapping[str, Any]) -> tuple[str, bool, list[str], int]:
    """An API-S-RoleAssignment: its status, whether it is for all entities, the entities the
    reader is shown and how many it names."""
    return (
        item["status"],
        item["is_all_entities"],
        [ref["code"] for ref in item["entities"]],
        item["entity_count"],
    )


def test_an_assignment_states_how_many_entities_it_names(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Tomas requests Viewer for Lena for AVM-DE and AVM-US; the request waits for Grace, and its
    answer counts 2 already. Once approved, the list answers Tomas both entities, and Dieter —
    Tenant Admin for AVM-DE — AVM-DE alone with the count 2: the assignment reaches beyond what
    he sees, and his revoke answers 403 by rule ``T-PLT-10``. Before, the row read as an
    assignment for AVM-DE, which he covers. The revoked row keeps its count; an assignment for
    all entities counts 0, as an approval's ``entity_count`` does for a request that spans every
    entity."""
    legal_entities(app, world, "AVM-DE", "AVM-US")
    both = ["AVM-DE", "AVM-US"]

    def grant(who: Member, code: str, *entity_codes: str) -> dict[str, Any]:
        """Requested by Tomas and approved by Grace; what the request answered."""
        requested = post(
            app,
            ASSIGNMENTS,
            world.tomas,
            {
                "membership_id": str(who.membership_id),
                "role_id": role_id(world.tenant_id, code),
                "is_all_entities": False,
                "entity_codes": list(entity_codes),
            },
        )
        assert requested.status_code == 201, requested.text
        approved = approve(app, requested.json()["approval_request_id"], world.grace)
        assert approved.status_code == 200, approved.text
        return dict(requested.json())

    dieter_member = colleague(world.tenant_id, "dieter")
    grant(dieter_member, "tenant_admin", "AVM-DE")
    dieter = enrolled(app, clock, dieter_member)
    requested = grant(world.lena, "viewer", "AVM-US", "AVM-DE")
    assert counted(requested) == ("REQUESTED", False, both, 2)

    for reader, shown in ((world.tomas, both), (dieter, ["AVM-DE"])):
        listed = get(app, ASSIGNMENTS, reader, membership_id=str(world.lena.membership_id))
        assert listed.status_code == 200, listed.text
        assert [counted(item) for item in listed.json()["items"]] == [("ACTIVE", False, shown, 2)]
    path = f"{ASSIGNMENTS}/{requested['id']}/revoke"
    refused = post(app, path, dieter, {"reason": REASON})
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
        ("T-PLT-10", ASSIGNMENT_BEYOND_SCOPE)
    ]
    assert "AVM-US" not in refused.text
    revoked = post(app, path, world.tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text
    assert counted(revoked.json()) == ("REVOKED", False, both, 2)
    own = get(app, ASSIGNMENTS, world.tomas, membership_id=str(world.tomas.member.membership_id))
    assert own.status_code == 200, own.text
    held = [counted(item) for item in own.json()["items"]]
    assert ("ACTIVE", True, [], 0) in held
    assert all(row[1:] == (True, [], 0) for row in held)
