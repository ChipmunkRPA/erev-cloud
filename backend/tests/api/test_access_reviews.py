"""API-R-51 Access reviews (04 §15.3 API-R-51, T-PLT-40, T-PLT-41, DB-10, §14.3 item 3; SCREENS_B
§9.13; PRD BR-PLT-02, J-22.11; REQ-CTL-006; BUILD_SPEC PLF-28, BS1-D-28).

Tomas is the bootstrap Tenant Admin and Grace a second Tenant Admin, both enrolled in MFA. Lena is
a member whose Revenue Reviewer role Tomas requested while setup was incomplete and before Grace
held her role — nobody else could approve access — so rule AUTO-BOOTSTRAP approved it (a setup
grant; 04 §14.3 item 3, supervisor ruling R-38 (iv) addendum). The workspace has exactly these
three memberships.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, file_object, role, role_assignment
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled, member
from support.rows import ASSIGNED_FROM, insert_role_assignment

REVIEWS = "/api/v1/access-reviews"
ASSIGNMENTS = "/api/v1/role-assignments"
PROBLEM_BASE = "https://erev.dev/problems/"
NAME = "Q3 2026 access review"
COMMENT = "Left team."  # 10 characters
REASON = "Revocation requested by the access review"
ROLE_KEYS = {"role_code", "is_all_entities", "entity_codes", "granted_at", "granted_by"}


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor
    lena: Actor

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
        insert_role_assignment(
            session,
            tenant_id=tomas.tenant_id,
            membership_id=tomas.membership_id,
            role_code="tenant_admin",
        )
        reviewer_role = session.execute(
            select(role.c.id).where(role.c.code == "revenue_reviewer")
        ).scalar_one()
    actors = World(
        tomas=enrolled(app, clock, tomas),
        grace=enrolled(app, clock, grace),
        lena=enrolled(app, clock, lena),
    )
    granted = post(
        app,
        ASSIGNMENTS,
        actors.tomas,
        {"membership_id": str(lena.membership_id), "role_id": str(reviewer_role)},
    )
    assert granted.status_code == 201, granted.text
    assert (granted.json()["status"], granted.json()["setup_grant"]) == ("ACTIVE", True)
    with tenant_session(_context(tomas.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=tomas.tenant_id,
            membership_id=grace.membership_id,
            role_code="tenant_admin",
        )
    return actors


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(
    app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any] | None = None
) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def started_campaign(
    app: FastAPI, clock: FrozenClock, world: World, reviewers: Sequence[Actor]
) -> tuple[str, dict[str, dict[str, Any]]]:
    """A campaign Tomas creates and starts; returns its id and the items by membership id."""
    created = post(
        app,
        REVIEWS,
        world.tomas,
        {
            "name": NAME,
            "as_of": clock.now().isoformat(),
            "reviewer_membership_ids": [str(someone.member.membership_id) for someone in reviewers],
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    started = post(app, f"{REVIEWS}/{campaign_id}/start", world.tomas)
    assert started.status_code == 200, started.text
    listed = get(app, f"{REVIEWS}/{campaign_id}/items", world.tomas)
    assert listed.status_code == 200, listed.text
    return campaign_id, {item["membership_id"]: item for item in listed.json()["items"]}


def test_start_snapshots_memberships(app: FastAPI, clock: FrozenClock, world: World) -> None:
    created = post(
        app,
        REVIEWS,
        world.tomas,
        {
            "name": NAME,
            "as_of": clock.now().isoformat(),
            "reviewer_membership_ids": [str(world.grace.member.membership_id)],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    campaign_id = body["id"]
    assert created.headers["Location"] == f"{REVIEWS}/{campaign_id}"
    assert (body["status"], body["name"], body["snapshot_file_id"]) == ("DRAFT", NAME, None)
    assert [reviewer["membership_id"] for reviewer in body["reviewers"]] == [
        str(world.grace.member.membership_id)
    ]

    started = post(app, f"{REVIEWS}/{campaign_id}/start", world.tomas)
    assert started.status_code == 200, started.text
    out = started.json()
    assert out["status"] == "IN_REVIEW"
    assert out["started_at"] is not None
    assert out["counts"] == {
        "members": 3,
        "pending": 3,
        "certified": 0,
        "revoke_requested": 0,
        "revoked": 0,
    }
    again = post(app, f"{REVIEWS}/{campaign_id}/start", world.tomas)
    assert (again.status_code, slug(again)) == (409, "invalid-transition")

    listed = get(app, f"{REVIEWS}/{campaign_id}/items", world.tomas)
    assert listed.status_code == 200, listed.text
    items = {item["membership_id"]: item for item in listed.json()["items"]}
    assert set(items) == {
        str(someone.member.membership_id) for someone in (world.tomas, world.grace, world.lena)
    }
    assert all(item["decision"] == "PENDING" for item in items.values())
    assert all(
        set(entry) == ROLE_KEYS for item in items.values() for entry in item["roles_snapshot"]
    )
    tomas = items[str(world.tomas.member.membership_id)]
    assert tomas["user_email_snapshot"] == world.tomas.member.email
    assert tomas["last_login_at"] is not None
    assert [
        (entry["role_code"], entry["is_all_entities"], entry["entity_codes"], entry["granted_by"])
        for entry in tomas["roles_snapshot"]
    ] == [("tenant_admin", True, [], None)]
    assert tomas["roles_snapshot"][0]["granted_at"] == ASSIGNED_FROM.isoformat().replace(
        "+00:00", "Z"
    )
    lena = items[str(world.lena.member.membership_id)]
    assert [(entry["role_code"], entry["granted_by"]) for entry in lena["roles_snapshot"]] == [
        ("revenue_reviewer", "AUTO-BOOTSTRAP")
    ]

    snapshot_file_id = out["snapshot_file_id"]
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        purpose = session.execute(
            select(file_object.c.purpose).where(file_object.c.id == UUID(snapshot_file_id))
        ).scalar_one()
        actions = (
            session.execute(
                select(audit_event.c.action).where(
                    audit_event.c.object_id == UUID(campaign_id),
                )
            )
            .scalars()
            .all()
        )
    assert purpose == "REPORT_OUTPUT"
    assert sorted(actions) == ["access_review_campaign.create", "access_review_campaign.start"]
    content = get(app, f"/api/v1/files/{snapshot_file_id}/content", world.tomas)
    assert content.status_code == 200, content.text
    document = json.loads(content.content)
    assert document["campaign"]["id"] == campaign_id
    assert sorted(item["membership_id"] for item in document["items"]) == sorted(items)


def test_reviewer_cannot_review_own_membership(
    app: FastAPI, clock: FrozenClock, world: World
) -> None:
    campaign_id, items = started_campaign(app, clock, world, [world.grace])
    own = items[str(world.grace.member.membership_id)]
    refused = post(
        app,
        f"{REVIEWS}/{campaign_id}/items/{own['id']}/decide",
        world.grace,
        {"decision": "CERTIFIED"},
    )
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert refused.json()["detail"] == "You cannot review your own access."

    other = items[str(world.tomas.member.membership_id)]
    outsider = post(
        app,
        f"{REVIEWS}/{campaign_id}/items/{other['id']}/decide",
        world.tomas,
        {"decision": "CERTIFIED"},
    )
    assert (outsider.status_code, slug(outsider)) == (403, "forbidden")
    certified = post(
        app,
        f"{REVIEWS}/{campaign_id}/items/{other['id']}/decide",
        world.grace,
        {"decision": "CERTIFIED"},
    )
    assert certified.status_code == 200, certified.text
    assert (certified.json()["decision"], certified.json()["reviewer"]["id"]) == (
        "CERTIFIED",
        str(world.grace.member.user_id),
    )


def test_revocation_requires_comment_and_completion(
    app: FastAPI, clock: FrozenClock, world: World
) -> None:
    campaign_id, items = started_campaign(app, clock, world, [world.grace])
    item_path = f"{REVIEWS}/{campaign_id}/items/{items[str(world.lena.member.membership_id)]['id']}"

    silent = post(app, f"{item_path}/decide", world.grace, {"decision": "REVOKE_REQUESTED"})
    assert (silent.status_code, slug(silent)) == (422, "validation-failed")
    assert [(error["field"], error["rule_id"]) for error in silent.json()["errors"]] == [
        ("comment", "BR-PLT-08")
    ]
    requested = post(
        app,
        f"{item_path}/decide",
        world.grace,
        {"decision": "REVOKE_REQUESTED", "comment": COMMENT},
    )
    assert requested.status_code == 200, requested.text
    assert (requested.json()["decision"], requested.json()["comment"]) == (
        "REVOKE_REQUESTED",
        COMMENT,
    )

    early = post(app, f"{item_path}/confirm-revocation", world.grace)
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text

    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        assignment_id = session.execute(
            select(role_assignment.c.id).where(
                role_assignment.c.membership_id == world.lena.member.membership_id
            )
        ).scalar_one()
    revoked = post(app, f"{ASSIGNMENTS}/{assignment_id}/revoke", world.tomas, {"reason": REASON})
    assert revoked.status_code == 200, revoked.text

    confirmed = post(app, f"{item_path}/confirm-revocation", world.grace)
    assert confirmed.status_code == 200, confirmed.text
    out = confirmed.json()
    assert out["decision"] == "REVOKED"
    assert out["revocation_completed_at"] is not None
    campaign = get(app, f"{REVIEWS}/{campaign_id}", world.tomas)
    assert campaign.status_code == 200, campaign.text
    assert (campaign.json()["counts"]["revoked"], campaign.headers["ETag"]) == (1, '"r2"')


def test_complete_with_pending_items_refused(
    app: FastAPI, clock: FrozenClock, world: World
) -> None:
    campaign_id, items = started_campaign(app, clock, world, [world.grace, world.tomas])
    refused = post(app, f"{REVIEWS}/{campaign_id}/complete", world.tomas)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == "Decide 3 pending items before completing the campaign."

    for someone, reviewer in (
        (world.tomas, world.grace),
        (world.lena, world.grace),
        (world.grace, world.tomas),
    ):
        item_id = items[str(someone.member.membership_id)]["id"]
        decided = post(
            app,
            f"{REVIEWS}/{campaign_id}/items/{item_id}/decide",
            reviewer,
            {"decision": "CERTIFIED"},
        )
        assert decided.status_code == 200, decided.text

    completed = post(app, f"{REVIEWS}/{campaign_id}/complete", world.tomas)
    assert completed.status_code == 200, completed.text
    assert (completed.json()["status"], completed.json()["counts"]["certified"]) == ("COMPLETED", 3)
    listed = get(app, REVIEWS, world.grace, status="COMPLETED")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [campaign_id]
    cancelled = post(app, f"{REVIEWS}/{campaign_id}/cancel", world.tomas)
    assert (cancelled.status_code, slug(cancelled)) == (409, "invalid-transition")


def test_access_approve_required(app: FastAPI, clock: FrozenClock, world: World) -> None:
    listed = get(app, REVIEWS, world.lena)
    assert (listed.status_code, slug(listed)) == (403, "forbidden"), listed.text
    created = post(
        app,
        REVIEWS,
        world.lena,
        {
            "name": NAME,
            "as_of": clock.now().isoformat(),
            "reviewer_membership_ids": [str(world.grace.member.membership_id)],
        },
    )
    assert (created.status_code, slug(created)) == (403, "forbidden"), created.text


def test_the_snapshot_states_the_entities_of_a_role_for_named_entities(
    app: FastAPI, clock: FrozenClock, world: World
) -> None:
    """Supervisor ruling R-63 (e) (03 REQ-PLT-012; 04 T-PLT-10): the campaign's snapshot is
    evidence of who held what for which entity. Uma is Viewer for AVM-DE and AVM-US, granted
    through the product; her snapshot entry states both codes in code order, and Lena's role for
    all entities states none. Before: starting a campaign over a membership with such an
    assignment answered 500 — the reader of the scope was the BS1-D-06 stub."""
    from support.reference import approve, calendar, entity, holding

    maya = holding(app, colleague(world.tenant_id, "maya"), "revenue_accountant")
    calendar_id = calendar(app, maya)
    for code in ("AVM-DE", "AVM-US"):
        entity(app, maya, code=code, calendar_id=calendar_id)
    uma = colleague(world.tenant_id, "uma")
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        viewer = session.execute(select(role.c.id).where(role.c.code == "viewer")).scalar_one()
    granted = post(
        app,
        ASSIGNMENTS,
        world.tomas,
        {
            "membership_id": str(uma.membership_id),
            "role_id": str(viewer),
            "is_all_entities": False,
            "entity_codes": ["AVM-US", "AVM-DE"],
        },
    )
    assert granted.status_code == 201, granted.text
    # Grace is the second administrator of this world, so the grant waits for her (R-38 (iv)).
    decided = approve(app, granted.json()["approval_request_id"], world.grace)
    assert decided.status_code == 200, decided.text

    _, items = started_campaign(app, clock, world, [world.grace])
    [stated] = items[str(uma.membership_id)]["roles_snapshot"]
    assert (stated["role_code"], stated["is_all_entities"], stated["entity_codes"]) == (
        "viewer",
        False,
        ["AVM-DE", "AVM-US"],
    )
    [lena] = items[str(world.lena.member.membership_id)]["roles_snapshot"]
    assert (lena["role_code"], lena["is_all_entities"], lena["entity_codes"]) == (
        "revenue_reviewer",
        True,
        [],
    )
