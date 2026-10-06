"""API-R-05 users and memberships (04 §15.3 API-R-05, T-PLT-07, T-PLT-10, SMAP-14, §14.3 item 3;
PRD SM-13, BR-PLT-02, BR-PLT-06; SCREENS_B §9.10, SB-R-05; BUILD_SPEC PLF-17, BS1-D-06, BS1-D-24).

Tomas is the bootstrap Tenant Admin of a provisioned workspace and Grace a colleague without a
role, both enrolled in MFA. Setup is incomplete unless a test completes it and nobody else can
approve access, so rule AUTO-BOOTSTRAP approves Tomas's role requests (04 §14.3 item 3). A test
that needs another approver makes Grace a second Tenant Admin (``second_admin``); from then on
Tomas's requests wait for her, whatever the setup state (supervisor ruling R-38 (iv) addendum).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import routing
from erev_api.approvals.engine import in_force_delegations
from erev_api.auth import invitations, sessions, totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    api_client,
    api_token,
    app_user,
    approval_decision,
    approval_delegation,
    approval_request,
    approval_step,
    audit_event,
    outbox_message,
    password_reset_token,
    role,
    role_assignment,
    rule_set,
    rule_set_version,
    security_event,
    tenant,
    tenant_membership,
    user_mfa_factor,
    user_session,
)
from erev_api.domain.platform.privacy import erased_display_name
from erev_api.enums import MembershipStatus
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import Select, insert, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.links import emailed_token
from support.operators import create_operator, operator_services, operator_signed_in
from support.plans import sent
from support.principals import (
    PASSWORD,
    Actor,
    Member,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    refreshed,
    select_tenant,
    sign_in,
    step_up,
    workspace,
)
from support.rows import RowContext, api_client_values, insert_role_assignment, membership_row

USERS = "/api/v1/users"
SESSION_MFA = "/api/v1/session/mfa"
APPROVALS = "/api/v1/approvals"
ACCEPT = "/api/v1/session/accept-invitation"
PASSWORD_PATH = "/api/v1/me/password"
CHANGED_PASSWORD = "Oskar!Ledger2027"
PROBLEM_BASE = "https://erev.dev/problems/"
REASON = "Left the revenue team in September"
ROLE_ASSIGNMENT = "ROLE_ASSIGNMENT"


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor

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
        insert_role_assignment(
            session,
            tenant_id=tomas.tenant_id,
            membership_id=tomas.membership_id,
            role_code="tenant_admin",
        )
    return World(tomas=enrolled(app, clock, tomas), grace=enrolled(app, clock, grace))


def second_admin(world: World) -> None:
    """Grace becomes a second Tenant Admin: another active member who holds ``access.approve``."""
    with tenant_session(_context(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=world.grace.member.membership_id,
            role_code="tenant_admin",
        )


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any]) -> HttpResponse:
    return call(app, "POST", path, json=json, headers=cookie_headers(actor.token, actor.csrf_token))


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


def invitation(
    world: World,
    email: str,
    codes: Sequence[str],
    *,
    display_name: str = "Lena Fischer",
    entity_codes: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "email": email,
        "display_name": display_name,
        "roles": [
            {
                "role_id": role_id(world.tenant_id, code),
                "is_all_entities": not entity_codes,
                "entity_codes": list(entity_codes),
            }
            for code in codes
        ],
    }


def unique_email() -> str:
    return f"lena-{secrets.token_hex(4)}@acme.test"


def role_requests(world: World) -> list[Mapping[str, Any]]:
    return rows(
        world.tenant_id,
        select(approval_request)
        .where(
            approval_request.c.subject_type == ROLE_ASSIGNMENT,
            approval_request.c.preparer_id == world.tomas.member.user_id,
        )
        .order_by(approval_request.c.submitted_at, approval_request.c.id),
    )


def assignments_of(world: World, membership_id: str) -> list[Mapping[str, Any]]:
    return rows(
        world.tenant_id,
        select(role_assignment).where(role_assignment.c.membership_id == UUID(membership_id)),
    )


def test_invite_during_setup_auto_approved(app: FastAPI, world: World) -> None:
    response = post(
        app, USERS, world.tomas, invitation(world, "lena@acme.test", ["revenue_reviewer"])
    )
    assert response.status_code == 201, response.text
    body = response.json()
    membership_id = body["id"]
    assert response.headers["Location"] == f"{USERS}/{membership_id}"
    assert response.headers["ETag"] == '"r1"'
    # An INVITED row shows no MFA state of the person and says that it is not shown: null with
    # ``sign_in_withheld``, where it answered false (04 T-PLT-02 rev 1.316).
    assert (body["email"], body["status"], body["mfa_enrolled"]) == (
        "lena@acme.test",
        "INVITED",
        None,
    )
    assert body["sign_in_withheld"] is True

    [request] = role_requests(world)
    assert request["status"] == "APPROVED"
    decisions = rows(
        world.tenant_id,
        select(approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == request["id"]
        ),
    )
    assert [decision["decision"] for decision in decisions] == ["AUTO_APPROVE"]
    [assignment] = assignments_of(world, membership_id)
    assert (assignment["id"], assignment["approval_request_id"]) == (
        request["subject_id"],
        request["id"],
    )
    [granted] = body["roles"]
    assert (
        granted["assignment_id"],
        granted["role"]["code"],
        granted["status"],
        granted["setup_grant"],
        granted["granted_by"]["kind"],
    ) == (str(assignment["id"]), "revenue_reviewer", "ACTIVE", True, "SYSTEM")

    messages = rows(
        world.tenant_id,
        select(outbox_message.c.topic, outbox_message.c.payload).where(
            outbox_message.c.aggregate_id == UUID(membership_id)
        ),
    )
    assert [(message["topic"], message["payload"]["to"]) for message in messages] == [
        ("EMAIL", "lena@acme.test")
    ]
    events = rows(
        world.tenant_id,
        select(audit_event.c.action, audit_event.c.object_id)
        .where(audit_event.c.object_id.in_([UUID(membership_id), assignment["id"]]))
        .order_by(audit_event.c.chain_seq),
    )
    assert [(event["action"], event["object_id"]) for event in events] == [
        ("tenant_membership.invite", UUID(membership_id)),
        ("role_assignment.create", assignment["id"]),
    ]


def test_invite_after_setup_routes_to_second_admin(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    second_admin(world)
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )
    response = post(
        app, USERS, world.tomas, invitation(world, unique_email(), ["revenue_reviewer"])
    )
    assert response.status_code == 201, response.text
    membership_id = response.json()["id"]
    assert [(item["status"], item["assignment_id"]) for item in response.json()["roles"]] == [
        ("REQUESTED", None)
    ]

    [request] = role_requests(world)
    assert request["status"] == "PENDING"
    steps = rows(
        world.tenant_id,
        select(approval_step.c.required_permission, approval_step.c.status).where(
            approval_step.c.approval_request_id == request["id"]
        ),
    )
    assert [(step["required_permission"], step["status"]) for step in steps] == [
        ("access.approve", "ACTIVE")
    ]
    assert assignments_of(world, membership_id) == []

    detail = get(app, f"{APPROVALS}/{request['id']}", world.grace)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    approved = post(
        app,
        f"{APPROVALS}/{request['id']}/approve",
        world.grace,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Reviewer access for the September close",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    [assignment] = assignments_of(world, membership_id)
    assert (assignment["id"], assignment["approval_request_id"]) == (
        request["subject_id"],
        request["id"],
    )

    user = get(app, f"{USERS}/{membership_id}", world.tomas)
    assert user.status_code == 200, user.text
    assert [
        (item["status"], item["granted_by"]["id"], item["setup_grant"])
        for item in user.json()["roles"]
    ] == [("ACTIVE", str(world.grace.member.user_id), False)]


def test_invite_during_setup_waits_for_a_second_admin(app: FastAPI, world: World) -> None:
    """Supervisor ruling R-38 (iv) addendum; PRD BR-PLT-02 "a new tenant has no second approver";
    04 §14.3 item 3: as soon as another active member holds ``access.approve``, the bootstrap
    admin's role requests wait for that person although setup is still incomplete, and the role
    that person grants is no setup grant. ``test_invite_during_setup_auto_approved`` is the other
    side: nobody else can approve, so the seeded rule does."""
    second_admin(world)
    [workspace_row] = rows(
        world.tenant_id, select(tenant.c.setup_completed_at).where(tenant.c.id == world.tenant_id)
    )
    assert workspace_row["setup_completed_at"] is None

    response = post(
        app, USERS, world.tomas, invitation(world, unique_email(), ["revenue_reviewer"])
    )
    assert response.status_code == 201, response.text
    membership_id = response.json()["id"]
    assert [(item["status"], item["assignment_id"]) for item in response.json()["roles"]] == [
        ("REQUESTED", None)
    ]
    [request] = role_requests(world)
    assert (request["status"], request["routing_rule_id"]) == ("PENDING", None)
    decisions = rows(
        world.tenant_id,
        select(approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == request["id"]
        ),
    )
    assert decisions == []
    assert assignments_of(world, membership_id) == []

    own = post(
        app,
        f"{APPROVALS}/{request['id']}/approve",
        world.tomas,
        {
            "subject_content_sha256": request["subject_content_sha256"],
            "impact_preview_sha256": request["impact_preview_sha256"],
            "comment": "Reviewer access for the September close",
        },
    )
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    detail = get(app, f"{APPROVALS}/{request['id']}", world.grace)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    approved = post(
        app,
        f"{APPROVALS}/{request['id']}/approve",
        world.grace,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Reviewer access for the September close",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    user = get(app, f"{USERS}/{membership_id}", world.tomas)
    assert user.status_code == 200, user.text
    assert [
        (item["status"], item["granted_by"]["id"], item["setup_grant"])
        for item in user.json()["roles"]
    ] == [("ACTIVE", str(world.grace.member.user_id), False)]


def test_entity_codes_fail_closed(app: FastAPI, world: World) -> None:
    response = post(
        app,
        USERS,
        world.tomas,
        invitation(world, unique_email(), ["revenue_reviewer"], entity_codes=["AVM-DE"]),
    )
    assert (response.status_code, slug(response)) == (422, "validation-failed"), response.text
    assert fields(response) == [("roles[0].entity_codes", "EREV-REF-002")]


def test_assignment_sod_conflict_blocks_invitation(app: FastAPI, world: World) -> None:
    email = unique_email()
    response = post(
        app,
        USERS,
        world.tomas,
        invitation(world, email, ["revenue_accountant", "revenue_reviewer"]),
    )
    assert (response.status_code, slug(response)) == (409, "sod-conflict"), response.text
    assert fields(response) == [("roles", "SoD-3")]

    with identity_session(request_id="tests-users-sod") as session:
        assert session.execute(select(app_user.c.id).where(app_user.c.email == email)).all() == []
    assert (
        rows(
            world.tenant_id,
            select(tenant_membership.c.id).where(tenant_membership.c.status == "INVITED"),
        )
        == []
    )
    assert role_requests(world) == []


def test_suspend_ends_sessions(app: FastAPI, world: World) -> None:
    lena = colleague(world.tenant_id, "lena")
    signed_in = workspace(app, lena, sign_in(app, lena.email))
    assert get(app, APPROVALS, signed_in).status_code == 200
    path = f"{USERS}/{lena.membership_id}/suspend"

    short = post(app, path, world.tomas, {"reason": "Leaving"})
    assert (short.status_code, slug(short)) == (422, "validation-failed"), short.text
    assert fields(short) == [("reason", "BR-PLT-08")]

    suspended = post(app, path, world.tomas, {"reason": REASON})
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    with identity_session(request_id="tests-users-suspend") as session:
        ended = session.execute(
            select(user_session.c.ended_at, user_session.c.end_reason).where(
                user_session.c.user_id == lena.user_id,
                user_session.c.active_tenant_id == world.tenant_id,
            )
        ).all()
    assert ended and all(end_reason == "REVOKED" for _, end_reason in ended)

    refused = get(app, APPROVALS, signed_in)
    assert (refused.status_code, slug(refused)) == (401, "unauthenticated"), refused.text


def test_reset_mfa_step_up_and_sessions(app: FastAPI, world: World, clock: FrozenClock) -> None:
    lena = colleague(world.tenant_id, "lena")
    lena_actor = enrolled(app, clock, lena)
    clock.advance(timedelta(minutes=6))
    path = f"{USERS}/{lena.membership_id}/reset-mfa"

    stale = post(app, path, world.tomas, {"reason": "Lost her phone"})
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text

    tomas = step_up(app, clock, world.tomas)
    reset = post(app, path, tomas, {"reason": "Lost her phone"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["mfa_enrolled"] is False
    with identity_session(request_id="tests-users-reset-mfa") as session:
        disabled = session.execute(
            select(user_mfa_factor.c.disabled_at).where(user_mfa_factor.c.user_id == lena.user_id)
        ).scalars()
        assert list(disabled) == [clock.now()]
        events = session.execute(
            select(security_event.c.tenant_id).where(
                security_event.c.user_id == lena.user_id, security_event.c.kind == "MFA_RESET"
            )
        ).scalars()
        assert list(events) == [world.tenant_id]
        open_sessions = session.execute(
            select(user_session.c.id).where(
                user_session.c.user_id == lena.user_id, user_session.c.ended_at.is_(None)
            )
        ).all()
        assert open_sessions == []
    refused = get(app, APPROVALS, lena_actor)
    assert (refused.status_code, slug(refused)) == (401, "unauthenticated"), refused.text


def open_sessions_of(user_id: UUID) -> list[UUID]:
    with identity_session(request_id="tests-users-open-sessions") as session:
        return list(
            session.execute(
                select(user_session.c.id).where(
                    user_session.c.user_id == user_id, user_session.c.ended_at.is_(None)
                )
            ).scalars()
        )


def test_reset_mfa_is_not_outlived_by_a_rotation_past_its_authentication(
    app: FastAPI, world: World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; BR-PLT-06). An MFA reset ends every session
    of the member, so that she enrols again at the next sign-in. A request of hers that was past
    its authentication when the reset committed went on, rotated its session and left an open
    successor that still counted as verified. The rotation finds its session ended: 401, and no
    session of hers is open after the reset."""
    lena = colleague(world.tenant_id, "lena")
    presented = refreshed(app, enrolled(app, clock, lena).token)
    clock.advance(timedelta(minutes=6))
    tomas = step_up(app, clock, world.tomas)
    path = f"{USERS}/{lena.membership_id}/reset-mfa"
    marked = sessions._mark_opened  # noqa: SLF001 - between the authentication and the rotation
    resets: list[HttpResponse] = []

    def resetting(facts: Any, **arguments: Any) -> None:
        marked(facts, **arguments)
        # The administrator's reset, in her request's own thread, before it rotates her session.
        resets.append(post(app, path, tomas, {"reason": "Lost her phone"}))

    monkeypatch.setattr(sessions, "_mark_opened", resetting)
    refused = select_tenant(app, presented, world.tenant_id)
    (reset,) = resets
    assert reset.status_code == 200, reset.text
    assert refused.status_code == 401, refused.text
    assert slug(refused) == "unauthenticated"
    assert "set-cookie" not in refused.headers
    assert open_sessions_of(lena.user_id) == []


def test_reset_mfa_waits_for_a_rotation_that_holds_the_identity(
    app: FastAPI, world: World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; dev-guide DG-KRN-AUTH-08). A rotation of
    hers has ended the session it was given and has not yet committed the successor when the
    administrator resets her factor. Without her identity's row the reset waited for the ended
    session's row, passed it over as ended and never saw the successor. ``end_user_sessions``
    takes the identity's row before it ends a session, and a rotation holds it: the reset is
    observed waiting for that row, and once the rotation has committed it ends the successor
    with the rest."""
    lena = colleague(world.tenant_id, "lena")
    presented = refreshed(app, enrolled(app, clock, lena).token)
    clock.advance(timedelta(minutes=6))
    tomas = step_up(app, clock, world.tomas)
    path = f"{USERS}/{lena.membership_id}/reset-mfa"
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opened = sessions._open  # noqa: SLF001 - the place between the given session's end and the row

    def held_open(db: Any, **arguments: Any) -> Any:
        seen["holder"] = backend_pid(db)
        holding.set()
        assert release.wait(timeout=30), "the rotation was never let go"
        return opened(db, **arguments)

    def rotating() -> None:
        try:
            seen["rotated"] = select_tenant(app, presented, world.tenant_id)
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["rotated"] = error

    def resetting() -> None:
        try:
            seen["reset"] = post(app, path, tomas, {"reason": "Lost her phone"})
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["reset"] = error

    monkeypatch.setattr(sessions, "_open", held_open)
    rotator = threading.Thread(target=rotating, name="rotation")
    resetter = threading.Thread(target=resetting, name="reset-mfa")
    rotator.start()
    try:
        assert holding.wait(timeout=30), seen
        with (
            identity_session(request_id="tests-users-watch") as watch,
            observing_checkouts() as backends,
        ):
            resetter.start()
            _, waited_in = await_lock_wait(
                watch, holder_pid=seen["holder"], backends=backends, timeout=20
            )
            assert "reset" not in seen  # the reset has not answered: it waits
    finally:
        release.set()
        rotator.join(timeout=60)
        if resetter.ident is not None:
            resetter.join(timeout=60)
    assert not rotator.is_alive() and not resetter.is_alive()

    rotated, reset = seen["rotated"], seen["reset"]
    assert not isinstance(rotated, BaseException), rotated
    assert not isinstance(reset, BaseException), reset
    assert rotated.status_code == 200, rotated.text  # the rotation itself completed
    assert reset.status_code == 200, reset.text
    assert open_sessions_of(lena.user_id) == []
    successor = call(
        app, "GET", APPROVALS, headers={"Cookie": f"erev_session={cookie_of(rotated)}"}
    )
    assert (successor.status_code, slug(successor)) == (401, "unauthenticated"), successor.text
    # What the reset waited for was her identity's row, not a session's.
    assert "erev.app_user" in waited_in and "for no key update" in waited_in.lower()


def first_sent(texts: Sequence[str], *parts: str) -> int:
    """The place of the first statement that holds every one of ``parts``."""
    found = [n for n, text in enumerate(texts) if all(part in text for part in parts)]
    assert found, (parts, texts)
    return found[0]


def test_reset_mfa_takes_the_factor_then_the_identity_then_the_sessions(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; dev-guide DG-KRN-AUTH-08): the lock order
    of an MFA reset, read from the statements the request sent - the membership's row, the
    factor's row, the identity's row, then the sessions. A verification takes the factor before
    the identity as well (``tests/api/test_mfa.py``), so the two wait for each other at the
    factor and never in a ring."""
    lena = colleague(world.tenant_id, "lena")
    enrolled(app, clock, lena)
    clock.advance(timedelta(minutes=6))
    tomas = step_up(app, clock, world.tomas)
    with sent() as statements:
        reset = post(
            app, f"{USERS}/{lena.membership_id}/reset-mfa", tomas, {"reason": "Lost her phone"}
        )
    assert reset.status_code == 200, reset.text
    texts = [statement for statement, _ in statements]
    membership = first_sent(texts, "FROM erev.tenant_membership", "FOR UPDATE")
    factor = first_sent(texts, "FROM erev.user_mfa_factor", "FOR UPDATE")
    identity = first_sent(texts, "FROM erev.app_user", "FOR NO KEY UPDATE")
    ended = first_sent(texts, "UPDATE erev.user_session", "end_reason")
    assert membership < factor < identity < ended, texts


def test_reset_mfa_and_a_verification_under_way_meet_at_the_factor_and_both_complete(
    app: FastAPI, world: World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 SAR-09 rev 1.178 (item SESSION-ROTATION-END-1; dev-guide DG-KRN-AUTH-08): the lock order,
    measured with two connections. A verification holds the member's factor row, her identity's
    row and the session it has ended - its rotation is under way - when the administrator resets
    her factor. Both take the factor before the identity, so the reset is observed waiting for
    the factor's row and for nothing behind it: the verification completes, then the reset
    disables the factor and ends the rotated session. Neither is refused as a deadlock."""
    lena = colleague(world.tenant_id, "lena")
    lena_actor = enrolled(app, clock, lena)
    assert lena_actor.secret is not None
    clock.advance(timedelta(minutes=6))
    tomas = step_up(app, clock, world.tomas)
    path = f"{USERS}/{lena.membership_id}/reset-mfa"
    code = totp.code_at(lena_actor.secret, totp.time_step(clock.now()))
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opened = sessions._open  # noqa: SLF001 - the place between the given session's end and the row

    def held_open(db: Any, **arguments: Any) -> Any:
        seen["holder"] = backend_pid(db)
        holding.set()
        assert release.wait(timeout=30), "the verification was never let go"
        return opened(db, **arguments)

    def verifying() -> None:
        try:
            seen["verified"] = call(
                app,
                "POST",
                SESSION_MFA,
                json={"code": code},
                headers=cookie_headers(lena_actor.token, lena_actor.csrf_token),
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["verified"] = error

    def resetting() -> None:
        try:
            seen["reset"] = post(app, path, tomas, {"reason": "Lost her phone"})
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["reset"] = error

    monkeypatch.setattr(sessions, "_open", held_open)
    verifier = threading.Thread(target=verifying, name="verification")
    resetter = threading.Thread(target=resetting, name="reset-mfa")
    verifier.start()
    try:
        assert holding.wait(timeout=30), seen
        with (
            identity_session(request_id="tests-users-watch") as watch,
            observing_checkouts() as backends,
        ):
            resetter.start()
            _, waited_in = await_lock_wait(
                watch, holder_pid=seen["holder"], backends=backends, timeout=20
            )
            assert "reset" not in seen  # the reset has not answered: it waits
    finally:
        release.set()
        verifier.join(timeout=60)
        if resetter.ident is not None:
            resetter.join(timeout=60)
    assert not verifier.is_alive() and not resetter.is_alive()

    verified, reset = seen["verified"], seen["reset"]
    assert not isinstance(verified, BaseException), verified
    assert not isinstance(reset, BaseException), reset
    assert verified.status_code == 200, verified.text  # the verification itself completed
    assert reset.status_code == 200, reset.text  # and the reset after it: no deadlock, no timeout
    assert reset.json()["mfa_enrolled"] is False
    assert open_sessions_of(lena.user_id) == []
    # What the reset waited for was the factor's row: the first row both of them take.
    assert "erev.user_mfa_factor" in waited_in and "for update" in waited_in.lower()


def viewer_invitation(world: World, email: str) -> dict[str, Any]:
    return {
        "email": email,
        "display_name": "Name typed by A",
        "roles": [
            {
                "role_id": role_id(world.tenant_id, "viewer"),
                "is_all_entities": True,
                "entity_codes": [],
            }
        ],
    }


def admin_of_another_workspace(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """The Tenant Admin of workspace B, enrolled in MFA and signed in to B."""
    admin = member(keyring, clock)
    with tenant_session(_context(admin.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=admin.tenant_id,
            membership_id=admin.membership_id,
            role_code="tenant_admin",
        )
    return enrolled(app, clock, admin)


def invitation_token(tenant_id: UUID, membership_id: UUID) -> str:
    [message] = rows(
        tenant_id,
        select(outbox_message.c.payload).where(outbox_message.c.aggregate_id == membership_id),
    )
    # The message names the token; the link is composed as the email carries it (T-INT-03).
    return emailed_token(message["payload"], prefix="/accept-invitation#token=")


def reset_events(tenant_id: UUID) -> list[Mapping[str, Any]]:
    return rows(
        tenant_id,
        select(audit_event.c.object_id, audit_event.c.detail).where(
            audit_event.c.action == "user_mfa_factor.reset"
        ),
    )


def security_kinds(user_id: UUID, kind: str) -> list[Any]:
    with identity_session(request_id="tests-users-security-events") as session:
        return list(
            session.execute(
                select(security_event.c.tenant_id).where(
                    security_event.c.user_id == user_id, security_event.c.kind == kind
                )
            ).scalars()
        )


def factor_disabled_at(user_id: UUID) -> list[Any]:
    with identity_session(request_id="tests-users-factor") as session:
        return list(
            session.execute(
                select(user_mfa_factor.c.disabled_at).where(user_mfa_factor.c.user_id == user_id)
            ).scalars()
        )


def test_reset_mfa_refused_for_unaccepted_invitation(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    victim = admin_of_another_workspace(app, keyring, clock)
    invited = post(app, USERS, world.tomas, viewer_invitation(world, victim.member.email))
    assert invited.status_code == 201, invited.text
    assert invited.json()["status"] == "INVITED"
    membership_id = UUID(invited.json()["id"])
    path = f"{USERS}/{membership_id}/reset-mfa"

    refused = post(app, path, world.tomas, {"reason": "probe cross tenant reset"})
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["errors"][0]["field"] == "status"
    assert factor_disabled_at(victim.member.user_id) == [None]
    assert get(app, USERS, victim).status_code == 200
    assert security_kinds(victim.member.user_id, "MFA_RESET") == []
    assert reset_events(world.tenant_id) == []
    assert reset_events(victim.member.tenant_id) == []

    token = invitation_token(world.tenant_id, membership_id)
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    reset = post(app, path, world.tomas, {"reason": "probe cross tenant reset"})
    assert reset.status_code == 200, reset.text
    assert factor_disabled_at(victim.member.user_id) == [clock.now()]


def test_operator_identity_not_invitable_or_resettable(
    app: FastAPI,
    world: World,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    committed_db: TestDatabase,
) -> None:
    operator = create_operator(operator_services(keyring, clock, app_settings.file_root))
    operator_id = UUID(operator["id"])
    signed = operator_signed_in(app, clock, operator["email"])

    refused = post(app, USERS, world.tomas, viewer_invitation(world, operator["email"]))
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    first_error = refused.json()["errors"][0]
    assert (first_error["field"], first_error["rule_id"], first_error["message"]) == (
        "email",
        "T-PLT-02",
        "This email cannot be invited to a workspace.",
    )
    of_operator = select(tenant_membership.c.id).where(tenant_membership.c.user_id == operator_id)
    assert rows(world.tenant_id, of_operator) == []

    row = membership_row(RowContext(world.tenant_id, operator_id), status=MembershipStatus.ACTIVE)
    with committed_db.owner_engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE erev.tenant_membership NO FORCE ROW LEVEL SECURITY")
        connection.execute(insert(tenant_membership).values(**row))
        connection.exec_driver_sql("ALTER TABLE erev.tenant_membership FORCE ROW LEVEL SECURITY")
    reset = post(app, f"{USERS}/{row['id']}/reset-mfa", world.tomas, {"reason": "Lost the phone"})
    assert (reset.status_code, slug(reset)) == (404, "not-found"), reset.text
    assert factor_disabled_at(operator_id) == [None]
    assert refreshed(app, signed.token).body["authenticated"] is True
    assert security_kinds(operator_id, "MFA_RESET") == []


def shown_identity(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (item["status"], item["display_name"], item["last_login_at"], item["mfa_enrolled"])


def test_invitation_of_existing_user_discloses_nothing(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """PR-Z-02 (D-80 rule 5): the review probe P-2 saw the real name, last sign-in and MFA state."""
    victim = admin_of_another_workspace(app, keyring, clock)
    email = victim.member.email
    with identity_session(request_id="tests-users-real-name") as session:
        session.execute(
            update(app_user)
            .where(app_user.c.id == victim.member.user_id)
            .values(display_name="b admin real name", updated_by_kind="SYSTEM")
        )
    invited = post(app, USERS, world.tomas, viewer_invitation(world, email))
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    withheld = ("INVITED", email, None, None)
    assert shown_identity(invited.json()) == withheld

    detail = get(app, f"{USERS}/{membership_id}", world.tomas)
    assert detail.status_code == 200, detail.text
    assert shown_identity(detail.json()) == withheld
    listed = get(app, USERS, world.tomas, status="INVITED")
    assert listed.status_code == 200, listed.text
    assert [
        shown_identity(item) for item in listed.json()["items"] if item["id"] == membership_id
    ] == [withheld]
    # Neither search nor sort sees the withheld name.
    probed = get(app, USERS, world.tomas, q="real name")
    assert probed.status_code == 200, probed.text
    assert membership_id not in [item["id"] for item in probed.json()["items"]]

    token = invitation_token(world.tenant_id, UUID(membership_id))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    with identity_session(request_id="tests-users-last-login") as session:
        last_login_at = session.execute(
            select(app_user.c.last_login_at).where(app_user.c.id == victim.member.user_id)
        ).scalar_one()
    assert last_login_at is not None
    after = get(app, f"{USERS}/{membership_id}", world.tomas)
    assert after.status_code == 200, after.text
    body = after.json()
    assert (body["status"], body["display_name"], body["mfa_enrolled"]) == (
        "ACTIVE",
        "b admin real name",
        True,
    )
    assert datetime.fromisoformat(body["last_login_at"]) == last_login_at


def test_a_person_only_invited_is_named_by_no_reader_before_acceptance(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """D-80 rule 5 is one rule for EVERY reader of a membership's person (04 T-PLT-02 rev 1.315;
    item IDENTITY-BEFORE-ACCEPTANCE-READERS-1). Workspace B invites Dana under a name it types;
    she accepts and signs in at B. Workspace A invites her address. Everything goes through the
    routes and nothing is planted. Before she accepts A's invitation, A reads her email where a
    name would stand, and no last sign-in: in API-S-User; in the summary of each request about
    her — the invitation's role, a role asked for later, an SoD exception; in her role
    assignments and in the answer that stands for a pending one; in the SoD exception; in the
    label of her membership's audit events; and in an access review A starts — its items and
    its snapshot file. Once she accepts, the readers that read when they are asked show her
    name; what was written before keeps what it was written with.

    Fail-first (a00425ad0): the summaries, the role assignments, the SoD exception, the audit label
    and the access review named her as B had typed, and the review gave her last sign-in at B;
    API-S-User alone withheld both."""
    assignments, exceptions = "/api/v1/role-assignments", "/api/v1/sod-exceptions"
    reviews, events = "/api/v1/access-reviews", "/api/v1/audit-events"
    b_admin = admin_of_another_workspace(app, keyring, clock)
    b_tenant = b_admin.member.tenant_id
    email, name = f"dana-{secrets.token_hex(4)}@members.test", "Dana Name-typed-by-B"
    viewer = {"is_all_entities": True, "entity_codes": []}
    in_b = post(
        app,
        USERS,
        b_admin,
        {
            "email": email,
            "display_name": name,
            "roles": [{"role_id": role_id(b_tenant, "viewer"), **viewer}],
        },
    )
    assert in_b.status_code == 201, in_b.text
    token = invitation_token(b_tenant, UUID(in_b.json()["id"]))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    clock.advance(timedelta(minutes=3))
    sign_in(app, email)  # her last sign-in, at B
    clock.advance(timedelta(minutes=1))

    invited = post(app, USERS, world.tomas, viewer_invitation(world, email))
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    [granted] = invited.json()["roles"]
    second_admin(world)  # from here Tomas's requests wait for Grace, and she can review access
    asked = post(
        app,
        assignments,
        world.tomas,
        {"membership_id": membership_id, "role_id": role_id(world.tenant_id, "revenue_reviewer")},
    )
    assert (asked.status_code, asked.json()["status"]) == (201, "REQUESTED"), asked.text
    start = clock.now()
    exception = post(
        app,
        exceptions,
        world.tomas,
        {
            "sod_rule_code": "SoD-3",
            "membership_id": membership_id,
            "compensating_control": "The Controller reviews her approvals every month.",
            "valid_from": start.isoformat(),
            "valid_to": (start + timedelta(days=90)).isoformat(),
            "comment": "Small team until a second reviewer joins",
        },
    )
    assert exception.status_code == 201, exception.text
    campaign = post(
        app,
        reviews,
        world.tomas,
        {
            "name": "Access review of the third quarter",
            "as_of": start.isoformat(),
            "reviewer_membership_ids": [str(world.grace.member.membership_id)],
        },
    )
    assert campaign.status_code == 201, campaign.text
    review = f"{reviews}/{campaign.json()['id']}"
    started = post(app, f"{review}/start", world.tomas, {})
    assert started.status_code == 200, started.text
    snapshot = f"/api/v1/files/{started.json()['snapshot_file_id']}/content"

    def answered(path: str, **params: str) -> Any:
        answer = get(app, path, world.tomas, **params)
        assert answer.status_code == 200, answer.text
        return answer

    def summary(request: Mapping[str, Any]) -> tuple[str, str]:
        shown = answered(f"{APPROVALS}/{request['approval_request_id']}").json()
        return shown["summary"], shown["subject"]["display"]

    def hers(items: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        [found] = [item for item in items if item["membership_id"] == membership_id]
        return found

    def read() -> dict[str, Any]:
        """What each reader of workspace A shows of Dana when it is asked."""
        user = answered(f"{USERS}/{membership_id}").json()
        held = answered(assignments, membership_id=membership_id).json()["items"]
        item = hers(answered(f"{review}/items").json()["items"])
        stored = hers(json.loads(answered(snapshot).content)["items"])
        labels = {
            event["object_label"]
            for event in answered(events, object_id=membership_id).json()["items"]
        }
        return {
            "API-S-User": (user["display_name"], user["last_login_at"] is None),
            "the invitation's role request": summary(granted),
            "a role asked for later: its request": summary(asked.json()),
            "the role assignments": [(one["role"]["code"], one["member_name"]) for one in held],
            "the SoD exception": hers(answered(exceptions).json()["items"])["member_name"],
            "the SoD exception's request": summary(exception.json()),
            "the audit events' label": sorted(labels),
            "the access review's item": (item["display_name"], item["last_login_at"]),
            "the access review's snapshot": (stored["display_name"], stored["last_login_at"]),
        }

    def texts(of: str) -> dict[str, tuple[str, str]]:
        """The three summaries, as a request about ``of`` words them."""
        return {
            "the invitation's role request": (f"Grant {granted['role']['name']} to {of}",) * 2,
            "a role asked for later: its request": (
                f"Grant {asked.json()['role']['name']} to {of}",
            )
            * 2,
            "the SoD exception's request": (f"Allow SoD-3 for {of}",) * 2,
        }

    before = {
        **read(),
        "a role asked for later: the answer": asked.json()["member_name"],
        "the SoD exception: the answer": exception.json()["member_name"],
    }
    assert before == {
        "API-S-User": (email, True),
        **texts(email),
        "the role assignments": [("viewer", email)],
        "a role asked for later: the answer": email,
        "the SoD exception": email,
        "the SoD exception: the answer": email,
        "the audit events' label": [email],
        "the access review's item": (email, None),
        "the access review's snapshot": (email, None),
    }

    # She accepts: a reader that reads when it is asked shows her name, and what was written
    # before — a summary, the review's snapshot and the item's last sign-in — keeps its words.
    token = invitation_token(world.tenant_id, UUID(membership_id))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    assert read() == {
        "API-S-User": (name, False),
        **texts(email),
        "the role assignments": [("viewer", name)],
        "the SoD exception": name,
        "the audit events' label": [name],
        "the access review's item": (name, None),
        "the access review's snapshot": (email, None),
    }


def test_who_is_not_a_member_now_is_shown_as_one_only_invited(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """D-80 rule 5 by the membership's status (04 T-PLT-02 rev 1.316; item
    IDENTITY-WITHHELD-BY-STATUS-1). Two people pass through workspace A: Dana, whom workspace B
    named and who signs in there, and Otto, whom A itself names. Each is invited, accepts, is
    removed and — Dana — invited again; everything goes through the routes and nothing is
    planted. While a membership is INVITED or REMOVED the workspace is shown no last sign-in and
    no MFA state of the person, whoever created the identity, and API-S-User says so
    (``sign_in_withheld``); the name is the email unless this membership's invitation created
    the identity. ``activated_at`` plays no part: a member removed after an acceptance is shown
    as one only invited, and a sign-in the person makes elsewhere after the removal reaches no
    reader of A.

    Fail-first (eac214532): the REMOVED row of Dana gave the name B had typed, her MFA state and her
    last sign-in — minute 3, the sign-in she made at B after the removal — and so did the second
    invitation; ``q`` found her by that name; her role assignment, her audit events and the
    ended delegation named her; and API-S-User had no member that tells "not shown" from
    "never"."""
    assignments, events = "/api/v1/role-assignments", "/api/v1/audit-events"
    b_admin = admin_of_another_workspace(app, keyring, clock)
    b_tenant = b_admin.member.tenant_id
    dana_email, dana_name = f"dana-{secrets.token_hex(4)}@members.test", "Dana Name-typed-by-B"
    otto_email, otto_name = f"otto-{secrets.token_hex(4)}@members.test", "Otto Named-by-A"
    viewer = {"role_id": role_id(b_tenant, "viewer"), "is_all_entities": True, "entity_codes": []}
    in_b = post(
        app, USERS, b_admin, {"email": dana_email, "display_name": dana_name, "roles": [viewer]}
    )
    assert in_b.status_code == 201, in_b.text
    token = invitation_token(b_tenant, UUID(in_b.json()["id"]))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text

    began, minute = clock.now(), timedelta(minutes=1)

    def shown(membership_id: str) -> tuple[Any, ...]:
        """(status, name, the last sign-in in minutes after the walk began, MFA, the cells are
        withheld) of API-S-User."""
        answer = get(app, f"{USERS}/{membership_id}", world.tomas)
        assert answer.status_code == 200, answer.text
        user = answer.json()
        last = user["last_login_at"]
        return (
            user["status"],
            user["display_name"],
            None if last is None else (datetime.fromisoformat(last) - began) // minute,
            user["mfa_enrolled"],
            user.get("sign_in_withheld"),
        )

    def invited(email: str, name: str) -> str:
        answer = post(
            app, USERS, world.tomas, {**viewer_invitation(world, email), "display_name": name}
        )
        assert answer.status_code == 201, answer.text
        return str(answer.json()["id"])

    def accept(membership_id: str) -> None:
        token = latest_token(world.tenant_id, UUID(membership_id))
        answer = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
        assert answer.status_code == 200, answer.text

    def removed(membership_id: str) -> None:
        answer = post(app, f"{USERS}/{membership_id}/remove", world.tomas, {"reason": REASON})
        assert (answer.status_code, answer.json()["status"]) == (200, "REMOVED"), answer.text

    def found_by(text: str) -> list[str]:
        answer = get(app, USERS, world.tomas, q=text)
        assert answer.status_code == 200, answer.text
        return [item["id"] for item in answer.json()["items"]]

    seen: dict[str, Any] = {}
    clock.advance(timedelta(minutes=1))
    dana, otto = invited(dana_email, "Name typed by A"), invited(otto_email, otto_name)
    seen["Dana invited"], seen["Otto invited"] = shown(dana), shown(otto)
    accept(dana)
    accept(otto)
    sign_in(app, otto_email)  # a last sign-in the workspace is shown while he is its member
    # Dana sets up MFA: her own factor, and what a delegate must have (BR-PLT-07).
    user_id = get(app, f"{USERS}/{dana}", world.tomas).json()["user_id"]
    enrolled(app, clock, Member(UUID(user_id), dana_email, world.tenant_id, UUID(dana)))
    seen["Dana active"], seen["Otto active"] = shown(dana), shown(otto)
    second_admin(world)  # Grace holds access approval, and gives Dana a delegation of it
    now = clock.now()
    given = post(
        app,
        DELEGATIONS,
        world.grace,
        {
            "delegate_membership_id": dana,
            "permissions": ["access.approve"],
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "reason": "Cover while I am away",
        },
    )
    assert given.status_code == 201, given.text

    def delegate() -> tuple[str, bool]:
        """(the delegate's name, the delegation has ended) of the delegation's row."""
        answer = get(app, DELEGATIONS, world.grace)
        assert answer.status_code == 200, answer.text
        [found] = [item for item in answer.json()["items"] if item["id"] == given.json()["id"]]
        return found["delegate"]["display_name"], found["revoked_at"] is not None

    seen["Dana active: the delegation Grace gave her"] = delegate()
    clock.advance(timedelta(minutes=1))
    removed(dana)
    removed(otto)
    clock.advance(timedelta(minutes=1))
    sign_in(app, dana_email)  # at B, after A removed her
    seen["Dana removed"], seen["Otto removed"] = shown(dana), shown(otto)
    seen["Dana removed: found by her name, by her address"] = (
        dana in found_by("Name-typed-by-B"),
        dana in found_by(dana_email),
    )
    held = get(app, assignments, world.tomas, membership_id=dana)
    assert held.status_code == 200, held.text
    seen["Dana removed: her role assignment"] = [
        (item["role"]["code"], item["status"], item["member_name"]) for item in held.json()["items"]
    ]
    trail = get(app, events, world.tomas, object_id=dana)
    assert trail.status_code == 200, trail.text
    seen["Dana removed: the label of her audit events"] = sorted(
        {event["object_label"] for event in trail.json()["items"]}
    )
    seen["Dana removed: the delegation, ended"] = delegate()
    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, viewer_invitation(world, dana_email))
    assert (again.status_code, again.json()["id"]) == (201, dana), again.text
    seen["Dana invited again"] = shown(dana)

    not_shown = (None, None, True)  # no last sign-in, no MFA state, and the answer says why
    assert seen == {
        "Dana invited": ("INVITED", dana_email, *not_shown),
        "Otto invited": ("INVITED", otto_name, *not_shown),
        # a member: the sign-in of the first minute, when each of them accepted
        "Dana active": ("ACTIVE", dana_name, 1, True, False),
        "Otto active": ("ACTIVE", otto_name, 1, False, False),
        "Dana active: the delegation Grace gave her": (dana_name, False),
        "Dana removed": ("REMOVED", dana_email, *not_shown),
        "Otto removed": ("REMOVED", otto_name, *not_shown),
        "Dana removed: found by her name, by her address": (False, True),
        "Dana removed: her role assignment": [("viewer", "REVOKED", dana_email)],
        "Dana removed: the label of her audit events": [dana_email],
        "Dana removed: the delegation, ended": (dana_email, True),
        "Dana invited again": ("INVITED", dana_email, *not_shown),
    }


def test_an_erased_person_reads_by_the_erasure_label_whoever_created_the_identity(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """05 PRV-07 a beside D-80 rule 5 (04 T-PLT-02 rev 1.316; item IDENTITY-WITHHELD-BY-STATUS-1).
    An erased identity carries the product's own label, ``Erased user <8 hex>``, the same in
    every workspace: no name of a person is left to withhold, so the rule does not put the
    address in its place. Dana, whom workspace B named, is a member of A too, and A erases her —
    through the routes, nothing planted. Both memberships are REMOVED, and each workspace reads
    the label where it read her name, as an actor read by her user id does.

    Fail-first (ed9f21599, the rule by status without this clause): workspace A, which had not
    created the identity, read ``erased+<user id>@invalid.erev`` as her name — on her row, her
    role assignment and her audit events — and the label on an actor read by user id."""
    assignments, events = "/api/v1/role-assignments", "/api/v1/audit-events"
    b_admin = admin_of_another_workspace(app, keyring, clock)
    b_tenant = b_admin.member.tenant_id
    email = f"dana-{secrets.token_hex(4)}@members.test"
    viewer = {"role_id": role_id(b_tenant, "viewer"), "is_all_entities": True, "entity_codes": []}
    in_b = post(
        app, USERS, b_admin, {"email": email, "display_name": "Dana Typed-by-B", "roles": [viewer]}
    )
    assert in_b.status_code == 201, in_b.text
    token = invitation_token(b_tenant, UUID(in_b.json()["id"]))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    in_a = post(app, USERS, world.tomas, viewer_invitation(world, email))
    assert in_a.status_code == 201, in_a.text
    dana = str(in_a.json()["id"])
    token = latest_token(world.tenant_id, UUID(dana))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text

    def row(actor: Actor, membership_id: str) -> tuple[Any, ...]:
        """(status, name, the cells are withheld) of API-S-User as ``actor``'s workspace reads."""
        answer = get(app, f"{USERS}/{membership_id}", actor)
        assert answer.status_code == 200, answer.text
        user = answer.json()
        return user["status"], user["display_name"], user["sign_in_withheld"]

    assert row(world.tomas, dana) == ("ACTIVE", "Dana Typed-by-B", False)
    clock.advance(timedelta(seconds=30))
    tomas = step_up(app, clock, world.tomas)  # his session is a new one from here on
    erased = post(app, f"{USERS}/{dana}/anonymise", tomas, {"reason": REASON})
    assert erased.status_code == 200, erased.text
    label = erased_display_name(UUID(in_a.json()["user_id"]))

    held = get(app, assignments, tomas, membership_id=dana)
    assert held.status_code == 200, held.text
    trail = get(app, events, tomas, object_id=dana)
    assert trail.status_code == 200, trail.text
    assert {
        "A, her row": row(tomas, dana),
        "A, her role assignment": [
            (item["role"]["code"], item["status"], item["member_name"])
            for item in held.json()["items"]
        ],
        "A, the label of her audit events": sorted(
            {event["object_label"] for event in trail.json()["items"]}
        ),
        "B, her row": row(b_admin, str(in_b.json()["id"])),
    } == {
        "A, her row": ("REMOVED", label, True),
        "A, her role assignment": [("viewer", "REVOKED", label)],
        "A, the label of her audit events": [label],
        "B, her row": ("REMOVED", label, True),
    }


def test_rename_only_users_created_by_the_invitation(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """PR-Z-02 (D-80 rule 6): the review probe P-5 saw 200 and the global name changed."""
    code = f"t-{secrets.token_hex(6)}"
    email = f"c-admin@{code}.test"
    tenant_factory(keyring=keyring, clock=clock, code=code, admin_email=email)
    invited = post(app, USERS, world.tomas, viewer_invitation(world, email))
    assert invited.status_code == 201, invited.text
    path = f"{USERS}/{invited.json()['id']}"
    etag = get(app, path, world.tomas).headers["ETag"]
    refused = call(
        app,
        "PATCH",
        path,
        json={"display_name": "Renamed from tenant A"},
        headers=cookie_headers(world.tomas.token, world.tomas.csrf_token, **{"If-Match": etag}),
    )
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["errors"][0]["field"] == "status"
    with identity_session(request_id="tests-users-global-name") as session:
        name = session.execute(
            select(app_user.c.display_name).where(app_user.c.email == email)
        ).scalar_one()
    assert name == email

    own = post(app, USERS, world.tomas, invitation(world, unique_email(), ["viewer"]))
    assert own.status_code == 201, own.text
    own_path = f"{USERS}/{own.json()['id']}"
    own_etag = get(app, own_path, world.tomas).headers["ETag"]
    renamed = call(
        app,
        "PATCH",
        own_path,
        json={"display_name": "Lena Fischer"},
        headers=cookie_headers(world.tomas.token, world.tomas.csrf_token, **{"If-Match": own_etag}),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "Lena Fischer"


def session_id_of(token: str) -> UUID:
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with identity_session(request_id="tests-users-session-id") as session:
        found = session.execute(
            select(user_session.c.id).where(user_session.c.token_sha256 == digest)
        ).scalar_one()
    return UUID(str(found))


def membership_status_of(tenant_id: UUID, membership_id: UUID) -> str:
    [row] = rows(
        tenant_id, select(tenant_membership.c.status).where(tenant_membership.c.id == membership_id)
    )
    return str(row["status"])


def invited_with_a_password(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> tuple[Actor, UUID, str]:
    """A person who has a password and a session - the administrator of another workspace -
    invited to this one: she, the invited membership and the invitation's token."""
    person = admin_of_another_workspace(app, keyring, clock)
    invited = post(app, USERS, world.tomas, viewer_invitation(world, person.member.email))
    assert invited.status_code == 201, invited.text
    membership_id = UUID(invited.json()["id"])
    return person, membership_id, invitation_token(world.tenant_id, membership_id)


def change_of_password(app: FastAPI, person: Actor) -> HttpResponse:
    return call(
        app,
        "POST",
        PASSWORD_PATH,
        json={"current_password": PASSWORD, "new_password": CHANGED_PASSWORD},
        headers=cookie_headers(person.token, person.csrf_token),
    )


def test_an_acceptance_opens_no_session_on_a_password_changed_after_its_check(
    app: FastAPI,
    world: World,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SAR-09 rev 1.201 (item INVITE-ACCEPT-SESSION-1; dev-guide DG-KRN-AUTH-08 rev 1.267). The
    acceptance of an invitation verifies an existing person's password in a transaction of its
    own and opens her session in the next. A password change that committed between the two
    ended her sessions and was followed by a session opened on the old password. The acceptance
    now looks at the password again under the identity's row: 404, no session of hers is open
    but the one that changed the password, nothing of the acceptance is kept, and the invitation
    still stands for the new password."""
    person, membership_id, token = invited_with_a_password(app, world, keyring, clock)
    checked = invitations.check_acceptance_password
    changes: list[HttpResponse] = []

    def changing(invitation: Any, password: str, **arguments: Any) -> None:
        checked(invitation, password, **arguments)
        # Her own signed-in request, after the old password was verified and before the session.
        changes.append(change_of_password(app, person))

    monkeypatch.setattr(invitations, "check_acceptance_password", changing)
    refused = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    (changed,) = changes
    assert (changed.status_code, changed.content) == (204, b""), changed.text
    # Only the session that changed the password is open: the acceptance opened none.
    assert open_sessions_of(person.member.user_id) == [session_id_of(cookie_of(changed))]
    assert refused.status_code == 404, refused.text
    assert slug(refused) == "not-found"
    assert "set-cookie" not in refused.headers
    assert membership_status_of(world.tenant_id, membership_id) == "INVITED"

    monkeypatch.setattr(invitations, "check_acceptance_password", checked)
    stale = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert (stale.status_code, slug(stale)) == (422, "validation-failed"), stale.text
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": CHANGED_PASSWORD})
    assert accepted.status_code == 200, accepted.text
    assert membership_status_of(world.tenant_id, membership_id) == "ACTIVE"


def sent_after(texts: Sequence[str], start: int, *parts: str) -> int:
    """The place of the first statement after ``start`` that holds every one of ``parts``."""
    found = [n for n, text in enumerate(texts) if n > start and all(part in text for part in parts)]
    assert found, (parts, texts[start:])
    return found[0]


def test_an_acceptance_takes_the_membership_then_the_identity_then_the_session(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Dev-guide DG-KRN-AUTH-08 rev 1.267 (item INVITE-ACCEPT-SESSION-1): the lock order of the
    acceptance's transaction, read from the statements the request sent - the membership's row,
    then the identity's, then the session - for a person who has a password (the second look)
    and for one who has none (the first password). The first password was written before the
    membership's row: the reverse of the order every other tenant transaction keeps, so that an
    administrator's act on the same open invitation and the acceptance could wait in a ring."""
    _, _, token = invited_with_a_password(app, world, keyring, clock)
    with sent() as statements:
        accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    texts = [statement for statement, _ in statements]
    membership = first_sent(texts, "UPDATE erev.tenant_membership", "activated_at")
    identity = sent_after(texts, membership, "FROM erev.app_user", "FOR NO KEY UPDATE")
    session = sent_after(texts, membership, "INSERT INTO erev.user_session")
    assert membership < identity < session, texts
    assert "password_hash" in texts[identity]

    own = post(app, USERS, world.tomas, invitation(world, unique_email(), ["viewer"]))
    assert own.status_code == 201, own.text
    first_token = invitation_token(world.tenant_id, UUID(own.json()["id"]))
    with sent() as statements:
        first = call(app, "POST", ACCEPT, json={"token": first_token, "password": PASSWORD})
    assert first.status_code == 200, first.text
    texts = [statement for statement, _ in statements]
    membership = first_sent(texts, "UPDATE erev.tenant_membership", "activated_at")
    password = first_sent(texts, "UPDATE erev.app_user", "password_hash")
    session = first_sent(texts, "INSERT INTO erev.user_session")
    assert membership < password < session, texts


def test_a_password_change_waits_for_an_acceptance_that_holds_the_identity(
    app: FastAPI,
    world: World,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SAR-09 rev 1.201 (item INVITE-ACCEPT-SESSION-1): the other order of the same two. The
    acceptance has looked at the password under the identity's row and has not yet committed
    its session when her password changes. The change is observed waiting for that row; once the
    acceptance has committed it ends the session opened there with her others, so that only the
    session that changed the password is open."""
    person, _, token = invited_with_a_password(app, world, keyring, clock)
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    opening = sessions.open_workspace_session

    def held_open(db: Any, **arguments: Any) -> Any:
        seen["holder"] = backend_pid(db)
        holding.set()
        assert release.wait(timeout=30), "the acceptance was never let go"
        return opening(db, **arguments)

    def accepting() -> None:
        try:
            seen["accepted"] = call(
                app, "POST", ACCEPT, json={"token": token, "password": PASSWORD}
            )
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["accepted"] = error

    def changing() -> None:
        try:
            seen["changed"] = change_of_password(app, person)
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen["changed"] = error

    monkeypatch.setattr(sessions, "open_workspace_session", held_open)
    acceptor = threading.Thread(target=accepting, name="acceptance")
    changer = threading.Thread(target=changing, name="password-change")
    acceptor.start()
    try:
        assert holding.wait(timeout=30), seen
        with (
            identity_session(request_id="tests-users-watch-acceptance") as watch,
            observing_checkouts() as backends,
        ):
            changer.start()
            _, waited_in = await_lock_wait(
                watch, holder_pid=seen["holder"], backends=backends, timeout=20
            )
            assert "changed" not in seen  # the change has not answered: it waits
    finally:
        release.set()
        acceptor.join(timeout=60)
        if changer.ident is not None:
            changer.join(timeout=60)
    assert not acceptor.is_alive() and not changer.is_alive()

    accepted, changed = seen["accepted"], seen["changed"]
    assert not isinstance(accepted, BaseException), accepted
    assert not isinstance(changed, BaseException), changed
    assert accepted.status_code == 200, accepted.text  # the acceptance itself completed
    assert (changed.status_code, changed.content) == (204, b""), changed.text
    assert open_sessions_of(person.member.user_id) == [session_id_of(cookie_of(changed))]
    opened = call(app, "GET", USERS, headers={"Cookie": f"erev_session={cookie_of(accepted)}"})
    assert (opened.status_code, slug(opened)) == (401, "unauthenticated"), opened.text
    # What the change waited for was her identity's row.
    assert "erev.app_user" in waited_in and "for no key update" in waited_in.lower()


def test_the_second_look_answers_for_the_identity_as_it_is_under_its_row(world: World) -> None:
    """``sessions.hold_password`` (item INVITE-ACCEPT-SESSION-1): the identity's row is taken
    without its key and the password verified under it; an identity that is not ACTIVE, or has
    no password, answers no whatever is presented, and nothing is counted."""
    lena = colleague(world.tenant_id, "lena")

    def look(password: str) -> tuple[bool, list[str]]:
        with identity_session(request_id="tests-users-second-look") as db, sent() as statements:
            answer = sessions.hold_password(db, lena.user_id, password)
        return answer, [statement for statement, _ in statements]

    def identity(**values: Any) -> None:
        with identity_session(request_id="tests-users-second-look-set") as db:
            db.execute(
                update(app_user)
                .where(app_user.c.id == lena.user_id)
                .values(updated_by_kind="SYSTEM", **values)
            )

    known, texts = look(PASSWORD)
    assert known is True
    (locking,) = [text for text in texts if "FROM erev.app_user" in text]
    assert "FOR NO KEY UPDATE" in locking and "password_hash" in locking
    assert look(CHANGED_PASSWORD)[0] is False
    with identity_session(request_id="tests-users-second-look-count") as db:
        counted = db.execute(
            select(app_user.c.failed_login_count).where(app_user.c.id == lena.user_id)
        ).scalar_one()
    assert counted == 0  # the verification that counts is the check's
    identity(status="DISABLED")
    assert look(PASSWORD)[0] is False
    identity(status="ACTIVE", password_hash=None)
    assert look(PASSWORD)[0] is False
    with identity_session(request_id="tests-users-second-look-nobody") as db:
        assert sessions.hold_password(db, new_id(), PASSWORD) is False


def test_reset_mfa_audited_in_every_active_workspace(
    app: FastAPI, world: World, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = colleague(world.tenant_id, "lena")
    active_b = other_workspace(keyring, clock, lena.email, activate=True)
    invited_c = other_workspace(keyring, clock, lena.email, activate=False)
    enrolled(app, clock, lena)

    reset = post(app, f"{USERS}/{lena.membership_id}/reset-mfa", world.tomas, {"reason": REASON})
    assert reset.status_code == 200, reset.text

    [in_a] = reset_events(world.tenant_id)
    [in_b] = reset_events(active_b)
    assert reset_events(invited_c) == []
    assert in_a["object_id"] == in_b["object_id"]
    assert in_a["detail"] == {"membership_id": str(lena.membership_id)}
    assert in_b["detail"]["acting_tenant_id"] == str(world.tenant_id)
    assert security_kinds(lena.user_id, "MFA_RESET") == [world.tenant_id]
    with identity_session(request_id="tests-users-reset-sessions") as session:
        ended = session.execute(
            select(user_session.c.ended_at, user_session.c.end_reason).where(
                user_session.c.user_id == lena.user_id
            )
        ).all()
    assert ended
    assert all(ended_at is not None and reason == "REVOKED" for ended_at, reason in ended)


def other_workspace(keyring: KeyRing, clock: FrozenClock, email: str, *, activate: bool) -> UUID:
    """Another provisioned workspace whose admin is the existing user of ``email`` (SPEC-Q-118)."""
    result = tenant_factory(keyring=keyring, clock=clock, admin_email=email)
    tenant_id = tenant_id_of(result)
    if activate:
        with tenant_session(_context(tenant_id)) as session:
            session.execute(
                update(tenant_membership)
                .where(tenant_membership.c.id == result.admin_membership_id)
                .values(
                    status="ACTIVE",
                    invitation_token_sha256=None,
                    invitation_expires_at=None,
                    activated_at=clock.now(),
                    updated_by_kind="SYSTEM",
                )
            )
    return tenant_id


def test_resend_invitation_replaces_token(app: FastAPI, world: World, clock: FrozenClock) -> None:
    invited = post(app, USERS, world.tomas, invitation(world, unique_email(), ["viewer"]))
    assert invited.status_code == 201, invited.text
    membership_id = UUID(invited.json()["id"])
    columns = select(
        tenant_membership.c.invitation_token_sha256, tenant_membership.c.invitation_expires_at
    ).where(tenant_membership.c.id == membership_id)
    [before] = rows(world.tenant_id, columns)

    clock.advance(timedelta(minutes=10))
    resent = post(app, f"{USERS}/{membership_id}/resend-invitation", world.tomas, {})
    assert resent.status_code == 200, resent.text
    [after] = rows(world.tenant_id, columns)
    assert after["invitation_token_sha256"] != before["invitation_token_sha256"]
    assert after["invitation_expires_at"] == clock.now() + timedelta(days=7)
    messages = rows(
        world.tenant_id,
        select(outbox_message.c.id).where(outbox_message.c.aggregate_id == membership_id),
    )
    assert len(messages) == 2


def test_viewer_forbidden_and_denied_audit(app: FastAPI, world: World) -> None:
    vera = colleague(world.tenant_id, "vera")
    with tenant_session(_context(world.tenant_id)) as session:
        insert_role_assignment(
            session, tenant_id=world.tenant_id, membership_id=vera.membership_id, role_code="viewer"
        )
    viewer = workspace(app, vera, sign_in(app, vera.email))

    refused = post(app, USERS, viewer, invitation(world, unique_email(), ["viewer"]))
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    denied = rows(
        world.tenant_id,
        select(audit_event.c.action, audit_event.c.detail).where(audit_event.c.outcome == "DENIED"),
    )
    assert [(event["action"], event["detail"]["permission"]) for event in denied] == [
        ("user.manage", "user.manage")
    ]


def test_list_detail_update_reactivate_remove(app: FastAPI, world: World) -> None:
    email = unique_email()
    invited = post(
        app,
        USERS,
        world.tomas,
        invitation(world, email, ["revenue_reviewer"], display_name="Lena Fisher"),
    )
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    path = f"{USERS}/{membership_id}"

    listed = get(app, USERS, world.tomas, status="INVITED", q=email.split("@")[0], count="true")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [membership_id]
    assert listed.headers["X-Erev-Total-Count"] == "1"
    unknown = get(app, USERS, world.tomas, status="GONE")
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text

    detail = get(app, path, world.tomas)
    assert detail.status_code == 200, detail.text
    etag = detail.headers["ETag"]
    rename = {"display_name": "Lena Fischer"}
    headers = cookie_headers(world.tomas.token, world.tomas.csrf_token)
    missing = call(app, "PATCH", path, json=rename, headers=headers)
    assert (missing.status_code, slug(missing)) == (428, "precondition-required"), missing.text
    renamed = call(
        app,
        "PATCH",
        path,
        json=rename,
        headers=cookie_headers(world.tomas.token, world.tomas.csrf_token, **{"If-Match": etag}),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "Lena Fischer"
    assert renamed.headers["ETag"] != etag

    not_active = post(app, f"{path}/suspend", world.tomas, {"reason": REASON})
    assert (not_active.status_code, slug(not_active)) == (409, "invalid-transition")
    grace = f"{USERS}/{world.grace.member.membership_id}"
    suspended = post(app, f"{grace}/suspend", world.tomas, {"reason": REASON})
    assert suspended.json()["status"] == "SUSPENDED", suspended.text
    reactivated = post(app, f"{grace}/reactivate", world.tomas, {})
    assert reactivated.json()["status"] == "ACTIVE", reactivated.text

    removed = post(app, f"{path}/remove", world.tomas, {"reason": REASON})
    assert removed.status_code == 200, removed.text
    body = removed.json()
    assert (body["status"], body["invitation_expires_at"]) == ("REMOVED", None)
    assert [(item["status"], item["revoked_by"]["id"]) for item in body["roles"]] == [
        ("REVOKED", str(world.tomas.member.user_id))
    ]
    own = post(
        app, f"{USERS}/{world.tomas.member.membership_id}/remove", world.tomas, {"reason": REASON}
    )
    assert (own.status_code, slug(own)) == (403, "forbidden"), own.text


# --- supervisor ruling R-63 (e): a role for named entities (03 REQ-PLT-012; PRD J-22.1, J-22.2) ---


def legal_entities(app: FastAPI, world: World, *codes: str) -> dict[str, str]:
    """Legal entities of the workspace created through the product by a Revenue Accountant, the
    role that holds the reference commands; code → id."""
    from support.reference import calendar, entity, holding

    maya = holding(app, colleague(world.tenant_id, "maya"), "revenue_accountant")
    calendar_id = calendar(app, maya)
    return {
        code: str(entity(app, maya, code=code, calendar_id=calendar_id)["id"]) for code in codes
    }


def setup_completed(world: World, clock: FrozenClock) -> None:
    """After setup rule AUTO-BOOTSTRAP no longer approves Tomas's requests (BR-PLT-02)."""
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.tenant_id)
            .values(setup_completed_at=clock.now())
        )


def shown_roles(response: HttpResponse) -> list[tuple[str, bool, list[str]]]:
    return [
        (item["status"], item["is_all_entities"], [ref["code"] for ref in item["entities"]])
        for item in response.json()["roles"]
    ]


def test_j_22_1_a_role_for_one_entity_is_requested_approved_and_held_for_it(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """PRD J-22.1 and J-22.2: Tomas invites Lena as Revenue Reviewer for AVM-DE only; the request
    names the entity and Tomas has no Approve action on it; Grace approves; the assignment holds
    the entity, every read of it names the entity, and Lena's permissions are held for AVM-DE
    alone. Before: 422 ``EREV-REF-002`` for every entity code (the BS1-D-06 stub)."""
    from erev_api.auth.permissions import effective_grants

    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    second_admin(world)  # Grace approves access: without her role the request is not hers to read
    setup_completed(world, clock)
    response = post(
        app,
        USERS,
        world.tomas,
        invitation(world, unique_email(), ["revenue_reviewer"], entity_codes=["AVM-DE"]),
    )
    assert response.status_code == 201, response.text
    membership_id = response.json()["id"]
    assert shown_roles(response) == [("REQUESTED", False, ["AVM-DE"])]

    [request] = role_requests(world)
    assert request["status"] == "PENDING"
    own = get(app, f"{APPROVALS}/{request['id']}", world.tomas)
    assert own.status_code == 200, own.text
    assert own.json()["summary"] == "Grant Revenue Reviewer to Lena Fischer for AVM-DE"
    assert own.json()["can_decide"] is False  # J-22.1: the preparer has no Approve action
    detail = get(app, f"{APPROVALS}/{request['id']}", world.grace)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    assert assignments_of(world, membership_id) == []
    approved = post(
        app,
        f"{APPROVALS}/{request['id']}/approve",
        world.grace,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Reviewer access for AVM-DE",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    # the row the approval wrote passes the DB-12 trigger with the entity's id
    [assignment] = assignments_of(world, membership_id)
    assert (assignment["is_all_entities"], [str(value) for value in assignment["entity_ids"]]) == (
        False,
        [ids["AVM-DE"]],
    )
    # every read of the grant names the entity
    user = get(app, f"{USERS}/{membership_id}", world.tomas)
    assert user.status_code == 200, user.text
    assert shown_roles(user) == [("ACTIVE", False, ["AVM-DE"])]
    listed = get(app, USERS, world.tomas, limit="200")
    assert listed.status_code == 200, listed.text
    [lena] = [item for item in listed.json()["items"] if item["id"] == membership_id]
    assert [ref["code"] for ref in lena["roles"][0]["entities"]] == ["AVM-DE"]
    # what it gives: every permission of the role for AVM-DE alone
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        grants = effective_grants(session, UUID(membership_id), at=clock.now())
    assert grants.entity_scope == (UUID(ids["AVM-DE"]),)
    assert set(grants.permission_scopes.values()) == {frozenset({UUID(ids["AVM-DE"])})}


def test_the_entity_scope_of_an_invitation_is_refused_by_name(app: FastAPI, world: World) -> None:
    """The three rules of ``erev_api.auth.entity_scope`` at ``POST /users``: one shape (T-PLT-10),
    codes that name legal entities (DB-12 ``EREV-REF-002``; the answer names none of them), and
    nothing is written for a refused invitation."""
    legal_entities(app, world, "AVM-DE")
    cases = [
        ({"is_all_entities": True, "entity_codes": ["AVM-DE"]}, "T-PLT-10"),
        ({"is_all_entities": False, "entity_codes": []}, "T-PLT-10"),
        ({"is_all_entities": False, "entity_codes": ["AVM-FR"]}, "EREV-REF-002"),
        ({"is_all_entities": False, "entity_codes": ["AVM-DE", "AVM-FR"]}, "EREV-REF-002"),
    ]
    for scope, rule in cases:
        body = invitation(world, unique_email(), ["revenue_reviewer"])
        body["roles"][0].update(scope)
        response = post(app, USERS, world.tomas, body)
        assert (response.status_code, slug(response)) == (422, "validation-failed"), response.text
        assert fields(response) == [("roles[0].entity_codes", rule)], scope
    assert role_requests(world) == []
    invited = rows(
        world.tenant_id,
        select(tenant_membership.c.id).where(
            tenant_membership.c.status == MembershipStatus.INVITED.value
        ),
    )
    assert invited == []


def test_an_administrator_of_named_entities_grants_those_and_no_more(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """REQ-PLT-012: nobody grants beyond their own access. Dieter is a Tenant Admin for AVM-DE —
    a grant made through the product: Tomas requests it, Grace approves. He invites for AVM-DE;
    AVM-US answers exactly as a code that names no entity; all entities is refused by name."""
    from support.principals import enrolled as enrolled_member

    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    second_admin(world)  # Grace approves access: without her role the request is not hers to read
    setup_completed(world, clock)
    dieter = colleague(world.tenant_id, "dieter")
    requested = post(
        app,
        "/api/v1/role-assignments",
        world.tomas,
        {
            "membership_id": str(dieter.membership_id),
            "role_id": role_id(world.tenant_id, "tenant_admin"),
            "is_all_entities": False,
            "entity_codes": ["AVM-DE"],
        },
    )
    assert requested.status_code == 201, requested.text
    request_id = requested.json()["approval_request_id"]
    detail = get(app, f"{APPROVALS}/{request_id}", world.grace)
    approved = post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        world.grace,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Administration of AVM-DE",
        },
    )
    assert approved.status_code == 200, approved.text
    admin = enrolled_member(app, clock, dieter)

    inside = post(
        app,
        USERS,
        admin,
        invitation(world, unique_email(), ["viewer"], entity_codes=["AVM-DE"]),
    )
    assert inside.status_code == 201, inside.text
    assert shown_roles(inside) == [("REQUESTED", False, ["AVM-DE"])]

    def refused(entity_codes: list[str]) -> list[tuple[str, str | None]]:
        response = post(
            app,
            USERS,
            admin,
            invitation(world, unique_email(), ["viewer"], entity_codes=entity_codes),
        )
        assert (response.status_code, slug(response)) == (422, "validation-failed"), response.text
        return fields(response)

    # an entity outside his scope and a code that names none answer alike
    assert refused(["AVM-US"]) == refused(["AVM-FR"]) == [("roles[0].entity_codes", "EREV-REF-002")]
    assert refused(["AVM-DE", "AVM-US"]) == [("roles[0].entity_codes", "EREV-REF-002")]
    everything = post(app, USERS, admin, invitation(world, unique_email(), ["viewer"]))
    assert (everything.status_code, slug(everything)) == (422, "validation-failed")
    assert fields(everything) == [("roles[0].is_all_entities", "T-PLT-10")]
    assert everything.json()["errors"][0]["message"] == (
        "Your own access covers named entities only. Choose from those entities, not all entities."
    )
    assert ids["AVM-US"] not in everything.text  # nothing of the other entity is named
    # Each request that reached beyond his own access is the DENIED event of an invitation — a
    # code that names nothing as much as AVM-US: he may read the audit log, and an event for the
    # entity that exists alone would tell him what the answer withholds. No entity is named.
    assert denials(world) == [
        ("tenant_membership.invite", "tenant_membership", None, SCOPE_DENIAL),
        ("tenant_membership.invite", "tenant_membership", None, SCOPE_DENIAL),
        ("tenant_membership.invite", "tenant_membership", None, SCOPE_DENIAL),
        ("tenant_membership.invite", "tenant_membership", None, {**SCOPE_DENIAL, "scope": "*"}),
    ]


def test_a_grant_for_one_entity_is_decided_by_an_approver_of_that_entity(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Supervisor rulings R-25 and R-41 (4) through the product (R-63 (e); 03 REQ-PLT-012, 04
    §16.10): a ``ROLE_ASSIGNMENT`` request is bound to the entities of the grant it proposes, and
    a decision needs ``access.approve`` for every one of them. Dieter approves access for AVM-US
    alone — a grant made through the product. Tomas requests Revenue Reviewer for AVM-DE for
    Lena: Dieter is not waited for, the request answers him as an unknown one (404) and so does
    his approval; Grace, who approves access for all entities, decides it. The request for
    AVM-US is Dieter's: he is waited for and approves it.

    Fail-first (before R-25): the request named no entity, and any holder of ``access.approve``
    — Dieter too — decided a grant for AVM-DE."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    # Dieter's own grant is a setup grant: rule AUTO-BOOTSTRAP approves it while nobody but Tomas
    # has held access.approve. Grace then is the administrator of all entities.
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-US")
    second_admin(world)
    setup_completed(world, clock)
    lena, uma = (colleague(world.tenant_id, name) for name in ("lena", "uma"))

    def requested(who: Member, code: str) -> str:
        response = post(
            app,
            "/api/v1/role-assignments",
            world.tomas,
            {
                "membership_id": str(who.membership_id),
                "role_id": role_id(world.tenant_id, "revenue_reviewer"),
                "is_all_entities": False,
                "entity_codes": [code],
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "REQUESTED", response.text
        return str(response.json()["approval_request_id"])

    def waiting_for(actor: Actor) -> set[str]:
        listed = get(app, APPROVALS, actor, assigned_to_me="true")
        assert listed.status_code == 200, listed.text
        return {str(item["id"]) for item in listed.json()["items"]}

    def approved_by(actor: Actor, request_id: str) -> HttpResponse:
        detail = get(app, f"{APPROVALS}/{request_id}", actor)
        assert detail.status_code == 200, detail.text
        assert detail.json()["can_decide"] is True
        return post(
            app,
            f"{APPROVALS}/{request_id}/approve",
            actor,
            {
                "subject_content_sha256": detail.json()["subject"]["content_sha256"],
                "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
                "comment": "Reviewer access",
            },
        )

    for_de = requested(lena, "AVM-DE")
    for_us = requested(uma, "AVM-US")

    # Dieter approves access for AVM-US alone: the AVM-DE request is not his in any way.
    assert waiting_for(dieter) == {for_us}
    hidden = get(app, f"{APPROVALS}/{for_de}", dieter)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    refused = post(
        app,
        f"{APPROVALS}/{for_de}/approve",
        dieter,
        {"subject_content_sha256": "0" * 64, "impact_preview_sha256": "0" * 64, "comment": "OK"},
    )
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert assignments_of(world, str(lena.membership_id)) == []

    # Grace approves access for all entities: both wait for her, and she decides the first.
    assert waiting_for(world.grace) == {for_de, for_us}
    shown = get(app, f"{APPROVALS}/{for_de}", world.grace)
    assert shown.status_code == 200, shown.text
    assert shown.json()["entity"]["code"] == "AVM-DE"
    decided = approved_by(world.grace, for_de)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    [assignment] = assignments_of(world, str(lena.membership_id))
    assert [str(value) for value in assignment["entity_ids"]] == [ids["AVM-DE"]]

    # Positive control: the grant for AVM-US is Dieter's to decide.
    own = approved_by(dieter, for_us)
    assert own.status_code == 200, own.text
    assert own.json()["status"] == "APPROVED"
    [held] = assignments_of(world, str(uma.membership_id))
    assert [str(value) for value in held["entity_ids"]] == [ids["AVM-US"]]


def _requested(
    app: FastAPI, world: World, who: Member, code: str, *entity_codes: str
) -> dict[str, Any]:
    """``POST /role-assignments`` by Tomas, the bootstrap Tenant Admin; the answer."""
    response = post(
        app,
        "/api/v1/role-assignments",
        world.tomas,
        {
            "membership_id": str(who.membership_id),
            "role_id": role_id(world.tenant_id, code),
            "is_all_entities": not entity_codes,
            "entity_codes": list(entity_codes),
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _outcome(answer: Mapping[str, Any]) -> tuple[str, bool]:
    return str(answer["status"]), bool(answer["setup_grant"])


def test_the_setup_rule_ends_per_request_for_the_entities_another_approver_covers(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The supervisor's ruling of 2026-10-01 on the join with entity-scoped grants (04 §14.3
    item 3 rev 1.197; PRD BR-PLT-02 rev 1.126; rulings R-38 (iv), R-66 (2), R-73): rule
    ``AUTO-BOOTSTRAP`` ends per request — once another person has held ``access.approve`` for
    EVERY entity the request names.

    The order that stranded a workspace: Tomas first makes Dieter Tenant Admin for AVM-DE. A
    grant for all entities and one for AVM-US are still his alone to make — nobody else could
    ever decide them — and the rule approves them, its basis on the audit event; a grant for
    AVM-DE waits for Dieter, who decides it. Erin then approves access for AVM-US: a grant that
    names AVM-DE and AVM-US is covered by neither of them alone and is a setup grant still; a
    grant for AVM-US waits for her.

    Fail-first: any other holder of the permission ended the rule, so after Dieter's grant the
    grant for all entities was REQUESTED — with nobody who could decide it."""
    legal_entities(app, world, "AVM-DE", "AVM-US")
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-DE")
    carla, uma, lena, mio, sam = (
        colleague(world.tenant_id, name) for name in ("carla", "uma", "lena", "mio", "sam")
    )

    everywhere = _requested(app, world, carla, "controller")
    assert _outcome(everywhere) == ("ACTIVE", True)
    assert _outcome(_requested(app, world, uma, "viewer", "AVM-US")) == ("ACTIVE", True)
    # the audit event of the grant states why no person decided it
    [event] = rows(
        world.tenant_id,
        select(audit_event.c.after).where(
            audit_event.c.action == "approval_request.auto_approve",
            audit_event.c.object_id == UUID(str(everywhere["approval_request_id"])),
        ),
    )
    assert event["after"]["basis"] == "NO_OTHER_APPROVER_FOR_ENTITIES"
    assert event["after"]["auto_rule"]["rule_set_code"] == "AUTO-BOOTSTRAP"

    # A grant for AVM-DE is one Dieter can decide: it waits for him.
    for_de = _requested(app, world, lena, "viewer", "AVM-DE")
    assert _outcome(for_de) == ("REQUESTED", False)
    request_id = str(for_de["approval_request_id"])
    detail = get(app, f"{APPROVALS}/{request_id}", dieter)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True
    decided = post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        dieter,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Viewer for AVM-DE",
        },
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"

    # One authority has to cover every entity of the request, as a decision needs: Dieter covers
    # AVM-DE and Erin AVM-US, and neither covers a grant that names both.
    scoped_admin(app, world, clock, "erin", "AVM-US")
    assert _outcome(_requested(app, world, mio, "viewer", "AVM-DE", "AVM-US")) == ("ACTIVE", True)
    assert _outcome(_requested(app, world, sam, "viewer", "AVM-US")) == ("REQUESTED", False)


def test_the_setup_rule_never_returns_once_an_approver_of_all_entities_has_existed(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The end, one way (R-66 (2), R-73; 04 §14.3 item 3 rev 1.197): Tomas makes Grace Tenant
    Admin for all entities — the last grant the rule approves, because nobody else could have
    decided it. From then on nothing is approved by the rule, for any entity: a grant for one
    entity, for two, for all. It stays so after Grace is suspended: a workspace left without a
    second approver is repaired by the operator, never by the exception coming back.

    Fail-first: with the reading "no second approver has ever existed" removed, every grant
    below is a setup grant."""
    legal_entities(app, world, "AVM-DE", "AVM-US")
    assert granted(app, world, world.grace.member, "tenant_admin")  # the rule's last grant
    uma, lena, mio, carla, sam = (
        colleague(world.tenant_id, name) for name in ("uma", "lena", "mio", "carla", "sam")
    )
    assert _outcome(_requested(app, world, uma, "viewer", "AVM-US")) == ("REQUESTED", False)
    assert _outcome(_requested(app, world, lena, "viewer", "AVM-DE")) == ("REQUESTED", False)
    assert _outcome(_requested(app, world, mio, "viewer", "AVM-DE", "AVM-US")) == (
        "REQUESTED",
        False,
    )
    assert _outcome(_requested(app, world, carla, "controller")) == ("REQUESTED", False)

    suspended = post(
        app,
        f"{USERS}/{world.grace.member.membership_id}/suspend",
        world.tomas,
        {"reason": REASON},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    assert _outcome(_requested(app, world, sam, "viewer", "AVM-US")) == ("REQUESTED", False)


def _auto_approval(world: World, answer: Mapping[str, Any]) -> dict[str, Any]:
    """The ``after`` of the one ``approval_request.auto_approve`` event of a grant the rule
    approved."""
    assert _outcome(answer) == ("ACTIVE", True)
    [event] = rows(
        world.tenant_id,
        select(audit_event.c.after).where(
            audit_event.c.action == "approval_request.auto_approve",
            audit_event.c.object_id == UUID(str(answer["approval_request_id"])),
        ),
    )
    return dict(event["after"])


def test_the_basis_of_a_setup_grant_names_the_entities_another_approver_covers(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2 (the supervisor's ruling of 2026-10-01 on the independent review of
    the setup rule; 04 §14.3 item 3 rev 1.224). Rule ``AUTO-BOOTSTRAP`` ends for a request when
    ONE other person covers every entity it names, so a second approver for one entity does not
    constrain a grant that reaches beyond it: Dieter approves access for AVM-DE, and Tomas's grant
    for AVM-DE and AVM-US, or for all entities, is the rule's all the same. That is the accepted
    meaning, and the trail says so: beside its basis the audit event of such a grant states the
    entities of the request that another approver did cover — none before Dieter, AVM-DE with
    him, both once Erin approves access for AVM-US.

    Fail-first: the event stated the basis alone, so its reader could not see that Dieter covered
    AVM-DE when the rule approved a grant that names it."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    uma, mio, carla, lena, sam = (
        colleague(world.tenant_id, name) for name in ("uma", "mio", "carla", "lena", "sam")
    )
    basis = "NO_OTHER_APPROVER_FOR_ENTITIES"
    covered = "entity_ids_with_another_approver"

    # Nobody else approves access: the member is there, and empty.
    alone = _auto_approval(world, _requested(app, world, uma, "viewer", "AVM-DE", "AVM-US"))
    assert (alone["basis"], alone[covered]) == (basis, [])

    scoped_admin(app, world, clock, "dieter", "AVM-DE")
    # The two-entity case: Dieter covers AVM-DE and not the request.
    both = _auto_approval(world, _requested(app, world, mio, "viewer", "AVM-DE", "AVM-US"))
    assert (both["basis"], both[covered]) == (basis, [ids["AVM-DE"]])
    assert both["auto_rule"]["rule_set_code"] == "AUTO-BOOTSTRAP"
    # A grant for all entities names every entity, AVM-DE among them.
    everywhere = _auto_approval(world, _requested(app, world, carla, "controller"))
    assert (everywhere["basis"], everywhere[covered]) == (basis, [ids["AVM-DE"]])
    # A grant for AVM-US names no entity another approver covers.
    elsewhere = _auto_approval(world, _requested(app, world, lena, "viewer", "AVM-US"))
    assert (elsewhere["basis"], elsewhere[covered]) == (basis, [])

    # Erin approves access for AVM-US: each entity of the two-entity grant has an approver, and
    # no one person covers it.
    scoped_admin(app, world, clock, "erin", "AVM-US")
    again = _auto_approval(world, _requested(app, world, sam, "viewer", "AVM-DE", "AVM-US"))
    assert (again["basis"], again[covered]) == (basis, sorted([ids["AVM-DE"], ids["AVM-US"]]))


# --- supervisor ruling R-115 (c): commands on what is already granted ----------------------------

MEMBER_BEYOND_SCOPE = (
    "This member holds access for entities beyond your own. An administrator whose access covers "
    "every entity of the member's roles must make this change."
)
LOST_PHONE = "Lost the phone at the airport"


def granted(app: FastAPI, world: World, who: Member, code: str, *entity_codes: str) -> str:
    """A role granted through the product by Tomas. Setup is incomplete, so rule AUTO-BOOTSTRAP
    approves it and the assignment exists at once; its id."""
    response = post(
        app,
        "/api/v1/role-assignments",
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


def scoped_admin(
    app: FastAPI, world: World, clock: FrozenClock, name: str, *entity_codes: str
) -> Actor:
    """A Tenant Admin for named entities — granted through the product — signed in with a factor."""
    admin = colleague(world.tenant_id, name)
    granted(app, world, admin, "tenant_admin", *entity_codes)
    return enrolled(app, clock, admin)


def beyond_scope(response: HttpResponse) -> None:
    """403 by name: the rule and the sentence, and no entity of the member's roles."""
    assert (response.status_code, slug(response)) == (403, "forbidden"), response.text
    assert [(error["rule_id"], error["message"]) for error in response.json()["errors"]] == [
        ("T-PLT-10", MEMBER_BEYOND_SCOPE)
    ]


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


# what a scope refusal records: the permission and the rule, and no entity
SCOPE_DENIAL: dict[str, Any] = {"permission": "user.manage", "rule_id": "T-PLT-10"}


def membership_status(world: World, who: Member) -> str:
    [found] = rows(
        world.tenant_id,
        select(tenant_membership.c.status).where(tenant_membership.c.id == who.membership_id),
    )
    return str(found["status"])


AdminGrant = tuple[bool, str | None, UUID | None, str | None]


def admin_grants(world: World, who: Member) -> set[AdminGrant]:
    """Each ``tenant_admin`` assignment of the member: whether it is revoked, who prepared the
    request it names — the principal kind and the id — and the rule set of the rule that
    approved that request; none of the three where the assignment names no request."""
    found = rows(
        world.tenant_id,
        select(
            role_assignment.c.revoked_at,
            approval_request.c.preparer_kind,
            approval_request.c.preparer_id,
            rule_set.c.code,
        )
        .select_from(
            role_assignment.join(role, role.c.id == role_assignment.c.role_id)
            .outerjoin(
                approval_request, approval_request.c.id == role_assignment.c.approval_request_id
            )
            .outerjoin(
                approval_decision, approval_decision.c.approval_request_id == approval_request.c.id
            )
            .outerjoin(
                rule_set_version,
                rule_set_version.c.id == approval_decision.c.auto_rule_set_version_id,
            )
            .outerjoin(rule_set, rule_set.c.id == rule_set_version.c.rule_set_id)
        )
        .where(role_assignment.c.membership_id == who.membership_id, role.c.code == "tenant_admin"),
    )
    return {
        (
            row["revoked_at"] is not None,
            None if row["preparer_kind"] is None else str(row["preparer_kind"]),
            row["preparer_id"],
            row["code"],
        )
        for row in found
    }


def test_a_tenant_admin_whose_grant_the_setup_rule_approved_is_not_the_bootstrap_admin(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """04 §14.3 item 2 rev 1.254 (item SBX-EMPTY-BOOTSTRAP-1); supervisor ruling R-38 (iv): no
    command of a member makes a second member the bootstrap Tenant Admin. Tomas makes Dieter a
    Tenant Admin for all entities through the product, during setup, so rule ``AUTO-BOOTSTRAP``
    itself approves the grant: Dieter's assignment names a request, as the seed's does, and the
    same rule approved it. What tells the two apart is the preparer: the engine reads the rule
    for a signed-in member only, so a request the rule approves at a submission carries the
    member who asked, and the seed's has none. Dieter is not the bootstrap admin. Tomas is,
    through the provisioned grant, although this world revoked it
    (``support.principals.member``) and wrote Tomas's own assignment, which names no request."""
    dieter = scoped_admin(app, world, clock, "dieter")
    tomas = world.tomas.member
    assert admin_grants(world, dieter.member) == {(False, "USER", tomas.user_id, "AUTO-BOOTSTRAP")}
    assert admin_grants(world, tomas) == {
        (True, "SYSTEM", None, "AUTO-BOOTSTRAP"),
        (False, None, None, None),
    }
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        assert routing.is_bootstrap_admin(session, tomas.membership_id) is True
        assert routing.is_bootstrap_admin(session, dieter.member.membership_id) is False


def test_an_administrator_of_one_entity_commands_members_who_hold_nothing_beyond_it(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """REQ-PLT-012 on what is already granted: Dieter is Tenant Admin for AVM-DE. Lena holds
    Revenue Reviewer for AVM-DE and Nico holds no role, so every membership command of API-R-05
    answers Dieter as it answers an administrator of all entities — suspend, reactivate, reset a
    factor, remove, and the erasure."""
    legal_entities(app, world, "AVM-DE", "AVM-US")
    lena = colleague(world.tenant_id, "lena")
    granted(app, world, lena, "revenue_reviewer", "AVM-DE")
    # R-38 (iv) with its addendum; R-66 (2), R-73; 04 §14.3 item 3: rule AUTO-BOOTSTRAP approves
    # Tomas's grant for AVM-DE only while nobody else has held access.approve for AVM-DE, so
    # Dieter is granted his role after it.
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-DE")
    nico = colleague(world.tenant_id, "nico")
    for who in (lena, nico):
        enrolled(app, clock, who)  # a factor to reset (409 without one)
        path = f"{USERS}/{who.membership_id}"
        suspended = post(app, f"{path}/suspend", dieter, {"reason": REASON})
        assert suspended.status_code == 200, suspended.text
        assert suspended.json()["status"] == "SUSPENDED"
        reactivated = post(app, f"{path}/reactivate", dieter, {})
        assert reactivated.status_code == 200, reactivated.text
        assert reactivated.json()["status"] == "ACTIVE"
        reset = post(app, f"{path}/reset-mfa", dieter, {"reason": LOST_PHONE})
        assert reset.status_code == 200, reset.text
        removed = post(app, f"{path}/remove", dieter, {"reason": REASON})
        assert removed.status_code == 200, removed.text
        assert removed.json()["status"] == "REMOVED"
    erased = post(app, f"{USERS}/{lena.membership_id}/anonymise", dieter, {"reason": REASON})
    assert erased.status_code == 200, erased.text


def test_an_administrator_of_one_entity_is_refused_a_member_who_holds_more(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The other half: Uma holds Revenue Reviewer for AVM-US, Carla is Controller of all entities
    and Mio holds Viewer for AVM-DE and AVM-US. Each membership command answers Dieter 403 by
    name (rule ``T-PLT-10``) and changes nothing — before, a Tenant Admin of AVM-DE suspended the
    Controller of every entity. The answer names no entity. Tomas, administrator of all
    entities, then runs the same commands."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    # Dieter approves access for AVM-DE alone. The four grants below name AVM-US, every entity,
    # or AVM-DE and AVM-US: nobody but Tomas could ever decide them, so they are setup grants
    # still (04 §14.3 item 3 rev 1.197).
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-DE")
    uma, carla, mio = (colleague(world.tenant_id, name) for name in ("uma", "carla", "mio"))
    granted(app, world, uma, "revenue_reviewer", "AVM-US")
    granted(app, world, carla, "controller")
    granted(app, world, mio, "viewer", "AVM-DE", "AVM-US")
    # Sam was suspended by Tomas: reactivation is a command like any other
    sam = colleague(world.tenant_id, "sam")
    granted(app, world, sam, "viewer", "AVM-US")
    path = f"{USERS}/{sam.membership_id}"
    assert post(app, f"{path}/suspend", world.tomas, {"reason": REASON}).status_code == 200

    for who in (uma, carla, mio):
        path = f"{USERS}/{who.membership_id}"
        for command, body in (
            ("suspend", {"reason": REASON}),
            ("reset-mfa", {"reason": LOST_PHONE}),
            ("remove", {"reason": REASON}),
            ("anonymise", {"reason": REASON}),
        ):
            refused = post(app, f"{path}/{command}", dieter, body)
            beyond_scope(refused)
            assert ids["AVM-US"] not in refused.text and "AVM-US" not in refused.text
        assert membership_status(world, who) == "ACTIVE"
    beyond_scope(post(app, f"{USERS}/{sam.membership_id}/reactivate", dieter, {}))
    assert membership_status(world, sam) == "SUSPENDED"
    # each refusal is the DENIED event of its command on that membership (DG-KRN-AUTH-05)
    assert denials(world) == [
        *(
            (action, "tenant_membership", who.membership_id, SCOPE_DENIAL)
            for who in (uma, carla, mio)
            for action in (
                "tenant_membership.suspend",
                "user_mfa_factor.reset",
                "tenant_membership.remove",
                "app_user.anonymise",
            )
        ),
        ("tenant_membership.reactivate", "tenant_membership", sam.membership_id, SCOPE_DENIAL),
    ]
    # nothing was revoked on the way
    kept = rows(
        world.tenant_id,
        select(role_assignment.c.id).where(
            role_assignment.c.membership_id.in_(
                [who.membership_id for who in (uma, carla, mio, sam)]
            ),
            role_assignment.c.revoked_at.is_(None),
        ),
    )
    assert len(kept) == 4

    # the administrator of all entities: the same commands. A TOTP code is spent within its
    # step (T-PLT-04), so the clock moves on before Tomas verifies again.
    for who in (uma, carla, mio):
        enrolled(app, clock, who)
    clock.advance(timedelta(seconds=30))
    tomas = step_up(app, clock, world.tomas)
    reactivated = post(app, f"{USERS}/{sam.membership_id}/reactivate", tomas, {})
    assert reactivated.status_code == 200, reactivated.text
    for who in (uma, carla, mio):
        path = f"{USERS}/{who.membership_id}"
        suspended = post(app, f"{path}/suspend", tomas, {"reason": REASON})
        assert suspended.status_code == 200, suspended.text
        reactivated = post(app, f"{path}/reactivate", tomas, {})
        assert reactivated.status_code == 200, reactivated.text
        reset = post(app, f"{path}/reset-mfa", tomas, {"reason": LOST_PHONE})
        assert reset.status_code == 200, reset.text
        removed = post(app, f"{path}/remove", tomas, {"reason": REASON})
        assert removed.status_code == 200, removed.text
    erased = post(app, f"{USERS}/{uma.membership_id}/anonymise", tomas, {"reason": REASON})
    assert erased.status_code == 200, erased.text


def test_an_open_invitation_follows_the_scope_of_its_roles(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Rename and resend are membership commands too. An invitation whose role is for AVM-US
    answers Dieter 403 by name; one whose role is for AVM-DE is his to resend and rename."""
    legal_entities(app, world, "AVM-DE", "AVM-US")
    invited = {}
    for code in ("AVM-DE", "AVM-US"):
        response = post(
            app,
            USERS,
            world.tomas,
            invitation(world, unique_email(), ["viewer"], entity_codes=[code]),
        )
        assert response.status_code == 201, response.text
        assert shown_roles(response) == [("ACTIVE", False, [code])]
        invited[code] = response.json()["id"]
    # R-38 (iv) with its addendum; R-66 (2), R-73; 04 §14.3 item 3: rule AUTO-BOOTSTRAP approved
    # the grant for AVM-DE above because nobody else had held access.approve for AVM-DE; Dieter
    # is granted his role after it.
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-DE")

    def rename(membership_id: str, actor: Actor) -> HttpResponse:
        path = f"{USERS}/{membership_id}"
        detail = get(app, path, actor)
        assert detail.status_code == 200, detail.text
        return call(
            app,
            "PATCH",
            path,
            json={"display_name": "Lena Fischer-Braun"},
            headers=cookie_headers(
                actor.token, actor.csrf_token, **{"If-Match": detail.headers["ETag"]}
            ),
        )

    beyond_scope(post(app, f"{USERS}/{invited['AVM-US']}/resend-invitation", dieter, {}))
    beyond_scope(rename(invited["AVM-US"], dieter))
    assert denials(world) == [
        (action, "tenant_membership", UUID(invited["AVM-US"]), SCOPE_DENIAL)
        for action in ("tenant_membership.resend_invitation", "tenant_membership.update")
    ]
    resent = post(app, f"{USERS}/{invited['AVM-DE']}/resend-invitation", dieter, {})
    assert resent.status_code == 200, resent.text
    # the invitation created the identity, so its name is this workspace's to change (D-80 rule 6)
    renamed = rename(invited["AVM-DE"], dieter)
    assert renamed.status_code == 200, renamed.text
    assert rename(invited["AVM-US"], world.tomas).status_code == 200


def test_me_states_the_entities_of_each_permission(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """ME-SCOPE-PER-PERMISSION-1 (04 §16.12 API-S-Me; 03 REQ-PLT-012): ``/me`` states, per held
    permission, the entities it is held for. Mara is Viewer for all entities and Revenue
    Accountant for AVM-DE: the session sees every entity (``entity_scope``), and the accountant's
    permissions reach AVM-DE alone — which ``permissions`` and ``entity_scope`` together cannot
    say. An administrator of all entities reads "*" for each permission."""
    import asyncio

    from erev_api.auth.permissions import DEFAULT_ROLES

    async def started() -> None:  # the startup stamps the release API-S-Me names (REL-03)
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(started())
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    mara_member = colleague(world.tenant_id, "mara")
    granted(app, world, mara_member, "viewer")
    granted(app, world, mara_member, "revenue_accountant", "AVM-DE")
    mara = enrolled(app, clock, mara_member)
    me = get(app, "/api/v1/me", mara)
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["entity_scope"] == "*"
    scopes = body["permission_scopes"]
    assert sorted(scopes) == body["permissions"]
    viewer, accountant = DEFAULT_ROLES["viewer"], DEFAULT_ROLES["revenue_accountant"]
    assert {code: scopes[code] for code in sorted(viewer)} == dict.fromkeys(sorted(viewer), "*")
    only_accountant = sorted(accountant - viewer)
    assert "period.close" in only_accountant
    assert {code: scopes[code] for code in only_accountant} == dict.fromkeys(
        only_accountant, [ids["AVM-DE"]]
    )
    admin = get(app, "/api/v1/me", world.tomas).json()
    assert set(admin["permission_scopes"].values()) == {"*"}
    assert sorted(admin["permission_scopes"]) == admin["permissions"]


def test_a_member_whose_only_role_is_for_one_entity_lands_on_a_home_that_answers(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """SECFIX-SCOPE item 1 (supervisor ruling R-63 (e); 03 REQ-PLT-012): Rosa's only role is Revenue
    Accountant for AVM-DE, granted through the product. She signs in, opens the workspace and
    the reads the home page makes answer her: the context bar's entities and periods show AVM-DE
    alone, ``/me`` states AVM-DE for her session and for each of her permissions, and the home
    counts are those of AVM-DE."""
    import asyncio

    async def started() -> None:  # the startup stamps the release API-S-Me names (REL-03)
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(started())
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    rosa_member = colleague(world.tenant_id, "rosa")
    granted(app, world, rosa_member, "revenue_accountant", "AVM-DE")
    rosa = enrolled(app, clock, rosa_member)

    me = get(app, "/api/v1/me", rosa)
    assert me.status_code == 200, me.text
    assert me.json()["entity_scope"] == [ids["AVM-DE"]]
    assert {tuple(held) for held in me.json()["permission_scopes"].values()} == {(ids["AVM-DE"],)}
    entities = get(app, "/api/v1/entities", rosa, limit="200")
    assert entities.status_code == 200, entities.text
    assert [item["code"] for item in entities.json()["items"]] == ["AVM-DE"]
    periods = get(app, "/api/v1/periods", rosa, limit="200")
    assert periods.status_code == 200, periods.text
    assert {item["entity"]["code"] for item in periods.json()["items"]} == {"AVM-DE"}
    # the home counts are of the earliest open period: Rosa opens January of her entity
    january = periods.json()["items"][0]
    opened = call(
        app,
        "POST",
        f"/api/v1/periods/{january['id']}/open",
        json={},
        headers=cookie_headers(rosa.token, rosa.csrf_token, **{"If-Match": '"r1"'}),
    )
    assert opened.status_code == 200, opened.text
    home = get(app, "/api/v1/dashboard/home", rosa)
    assert home.status_code == 200, home.text
    assert home.json()["context"]["period"]["period_key"] == "FY2026-P01"
    named = get(app, "/api/v1/dashboard/home", rosa, entity="AVM-DE")
    assert named.status_code == 200, named.text
    assert named.json()["context"]["entity"]["code"] == "AVM-DE"
    # the other entity answers exactly as a code that names none
    other, unknown = (
        get(app, "/api/v1/dashboard/home", rosa, entity=code) for code in ("AVM-US", "AVM-FR")
    )
    assert (other.status_code, slug(other)) == (422, "validation-failed"), other.text
    assert fields(other) == fields(unknown) == [("entity", "API-C-11")]
    assert other.json()["errors"] == unknown.json()["errors"]
    # every other read of the home page (frontend/src/routes/home) and of the shell
    answered = {
        path: get(app, f"/api/v1/{path}", rosa).status_code
        for path in (
            "session",
            "books",
            "currencies",
            "approvals",
            "exceptions",
            "me/notifications",
            "contracts",
            "saved-views",
            "policies",
        )
    }
    assert answered == {
        "session": 200,
        "books": 200,
        "currencies": 200,
        "approvals": 200,
        "exceptions": 200,
        "me/notifications": 200,
        "contracts": 200,
        "saved-views": 200,
        "policies": 200,
    }
    # Not pinned here: the two tenant-wide lists of the home page, GET /jobs and GET
    # /audit-events. Ruling R-28 gives them to a holder of the guarding permission for all
    # entities; that rule is built with the sweep that follows this item, and the home page of
    # a member of named entities has to cope with a 403 on either.


# --- item USER-ROLE-ENTITY-COUNT-1 (04 T-PLT-10 rev 1.202): a role row counts its entities --------


def counted(roles: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, bool, list[str], int]]:
    """The role rows of an API-S-User: the role, its status, whether it is for all entities, the
    entities the reader is shown and how many the role names."""
    return [
        (
            item["role"]["code"],
            item["status"],
            item["is_all_entities"],
            [ref["code"] for ref in item["entities"]],
            item["entity_count"],
        )
        for item in roles
    ]


def test_a_role_row_states_how_many_entities_the_role_names(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Lena holds Revenue Reviewer for AVM-DE and AVM-US and Viewer for all entities; a request
    for Nico as Revenue Reviewer of both entities waits for an approver. Tomas, administrator of
    all entities, is shown both entities of each row. Dieter, Tenant Admin for AVM-DE, is shown
    AVM-DE alone and the count 2: the role reaches beyond what he sees, and a command on Lena
    answers him 403 by rule ``T-PLT-10``. Before, his row read as a role for AVM-DE, which he
    covers, and the screen offered the command (found by lane WEB-QA). A role for all entities
    counts 0, as an approval's ``entity_count`` does for a request that spans every entity. The
    count is a number: no entity outside the reader's view is named."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    lena, nico = (colleague(world.tenant_id, name) for name in ("lena", "nico"))
    # granted while nobody else can approve access: rule AUTO-BOOTSTRAP approves each grant
    granted(app, world, lena, "revenue_reviewer", "AVM-DE", "AVM-US")
    granted(app, world, lena, "viewer")
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-DE")
    setup_completed(world, clock)  # from here a request waits for an approver
    requested = post(
        app,
        "/api/v1/role-assignments",
        world.tomas,
        {
            "membership_id": str(nico.membership_id),
            "role_id": role_id(world.tenant_id, "revenue_reviewer"),
            "is_all_entities": False,
            "entity_codes": ["AVM-US", "AVM-DE"],
        },
    )
    assert requested.status_code == 201, requested.text
    assert (requested.json()["status"], requested.json()["entity_count"]) == ("REQUESTED", 2)

    for reader, shown in ((world.tomas, ["AVM-DE", "AVM-US"]), (dieter, ["AVM-DE"])):
        held = [
            ("revenue_reviewer", "ACTIVE", False, shown, 2),
            ("viewer", "ACTIVE", True, [], 0),
        ]
        awaited = [("revenue_reviewer", "REQUESTED", False, shown, 2)]
        for who, expected in ((lena, held), (nico, awaited)):
            user = get(app, f"{USERS}/{who.membership_id}", reader)
            assert user.status_code == 200, user.text
            assert counted(user.json()["roles"]) == expected
        listed = get(app, USERS, reader, limit="200")
        assert listed.status_code == 200, listed.text
        by_id = {item["id"]: item["roles"] for item in listed.json()["items"]}
        assert counted(by_id[str(lena.membership_id)]) == held
        assert counted(by_id[str(nico.membership_id)]) == awaited

    # the count names no entity, and it foretells the refusal: Lena's role reaches beyond Dieter
    seen = get(app, f"{USERS}/{lena.membership_id}", dieter)
    assert ids["AVM-US"] not in seen.text and "AVM-US" not in seen.text
    beyond_scope(post(app, f"{USERS}/{lena.membership_id}/suspend", dieter, {"reason": REASON}))
    assert membership_status(world, lena) == "ACTIVE"


# --- the guards of T-PLT-10 and a principal that is no member: an API client ----------------------


def access_client(world: World, clock: FrozenClock, *scopes: str) -> dict[str, str]:
    """World setup by rows (04 T-PLT-15, T-PLT-16): an ACTIVE API client for all entities that
    holds ``scopes``, with an open access token that carries them; the header of its requests."""
    token = f"erevt_{world.tenant_id.hex}_{secrets.token_urlsafe(32)}"
    row = api_client_values(world.tenant_id, name="svc-access", scopes=sorted(scopes))
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(insert(api_client).values(**row))
        session.execute(
            insert(api_token).values(
                tenant_id=world.tenant_id,
                id=new_id(),
                api_client_id=row["id"],
                token_sha256=hashlib.sha256(token.encode("ascii")).hexdigest(),
                scopes=sorted(scopes),
                issued_at=clock.now(),
                expires_at=clock.now() + timedelta(hours=1),
            )
        )
    return {"Authorization": f"Bearer {token}"}


def test_an_api_client_is_refused_every_access_route_for_want_of_a_second_factor(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """``user.manage`` and ``role.manage`` need a second factor and an API client carries none: a
    client that holds both scopes for all entities is answered 403 ``mfa-required`` on every
    route of API-R-05 and API-R-06 — by the route's guard, before the handler, so the entity
    scope rule of T-PLT-10 is never asked of a client. Each refusal is the guard's ``DENIED``
    event and nothing changes. (The table of principals against the guards, from the repair of
    SECFIX-SCOPE item 1: this cell was stated from the code.)"""
    lena = colleague(world.tenant_id, "lena")
    held = granted(app, world, lena, "viewer")
    viewer = role_id(world.tenant_id, "viewer")
    member_path = f"{USERS}/{lena.membership_id}"
    of_users: list[tuple[str, str, Mapping[str, Any] | None]] = [
        ("GET", USERS, None),
        ("POST", USERS, invitation(world, unique_email(), ["viewer"])),
        ("GET", member_path, None),
        ("PATCH", member_path, {"display_name": "Lena Fischer-Braun"}),
        *(
            ("POST", f"{member_path}/{command}", {"reason": REASON})
            for command in ("suspend", "reactivate", "remove", "reset-mfa", "anonymise")
        ),
        ("POST", f"{member_path}/resend-invitation", {}),
    ]
    of_roles: list[tuple[str, str, Mapping[str, Any] | None]] = [
        ("GET", "/api/v1/roles", None),
        (
            "POST",
            "/api/v1/roles",
            {"code": "deal_desk", "name": "Deal desk", "permissions": ["contract.read"]},
        ),
        ("GET", f"/api/v1/roles/{viewer}", None),
        (
            "POST",
            f"/api/v1/roles/{viewer}/propose-change",
            {"permissions": ["contract.read"], "comment": "Fewer permissions"},
        ),
        ("GET", "/api/v1/role-assignments", None),
        (
            "POST",
            "/api/v1/role-assignments",
            {"membership_id": str(lena.membership_id), "role_id": viewer},
        ),
        ("POST", f"/api/v1/role-assignments/{held}/revoke", {"reason": REASON}),
    ]
    before = denials(world)
    token = access_client(world, clock, "user.manage", "role.manage")
    for method, path, body in (*of_users, *of_roles):
        headers = {**token, "Idempotency-Key": f"k-{secrets.token_hex(8)}", "If-Match": '"r1"'}
        refused = call(app, method, path, json=body, headers=headers)
        assert (refused.status_code, slug(refused)) == (403, "mfa-required"), (method, path)
    assert [
        (action, detail["permission"], detail["reason"])
        for action, _, _, detail in denials(world)[len(before) :]
    ] == [
        *[("user.manage", "user.manage", "mfa-required")] * len(of_users),
        *[("role.manage", "role.manage", "mfa-required")] * len(of_roles),
    ]
    assert membership_status(world, lena) == "ACTIVE"
    assert [
        (str(row["id"]), row["revoked_at"])
        for row in assignments_of(world, str(lena.membership_id))
    ] == [(held, None)]
    assert rows(world.tenant_id, select(role.c.id).where(role.c.code == "deal_desk")) == []


# --- item SBX-COPY-OPEN-INVITATION-1, its second half: a person removed once is invited again
# (PRD SM-13 rev 1.201; 04 T-PLT-07 rev 1.293; the supervisor's ruling of 2026-10-02) ---

LOOKUP = "/api/v1/session/invitations/lookup"


def latest_token(tenant_id: UUID, membership_id: UUID) -> str:
    """The token of the membership's LATEST invitation email: an invitation issued again leaves
    the earlier emails in the outbox."""
    messages = rows(
        tenant_id,
        select(outbox_message.c.payload)
        .where(outbox_message.c.aggregate_id == membership_id)
        .order_by(outbox_message.c.id),
    )
    return emailed_token(messages[-1]["payload"], prefix="/accept-invitation#token=")


def membership_of(world: World, membership_id: str) -> Mapping[str, Any]:
    [row] = rows(
        world.tenant_id,
        select(tenant_membership).where(tenant_membership.c.id == UUID(membership_id)),
    )
    return row


def trail_of(world: World, membership_id: str) -> list[Mapping[str, Any]]:
    """The audit events of the membership, in chain order."""
    return rows(
        world.tenant_id,
        select(audit_event.c.action, audit_event.c.before, audit_event.c.after)
        .where(
            audit_event.c.object_type == "tenant_membership",
            audit_event.c.object_id == UUID(membership_id),
        )
        .order_by(audit_event.c.chain_seq),
    )


def test_a_member_removed_after_acceptance_is_invited_again_on_the_same_membership(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """PRD SM-13 rev 1.201: REMOVED goes back to INVITED on the SAME row, by the command that
    invites. The membership keeps its id, its ``invited_at`` and its first acceptance; the role
    of the first life stays revoked with the stamp of the removal and the new one is a new row;
    the trail is one. A person who is a member is refused as before. And the acceptance of the
    second invitation leaves ``activated_at`` where the first put it.

    Fail-first (the lane's tip before this item): the second ``POST /users`` answered 422 "This
    person is already a member of this workspace." — a person removed once could never return."""
    email = unique_email()
    invited = post(app, USERS, world.tomas, invitation(world, email, ["revenue_reviewer"]))
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    first = membership_of(world, membership_id)
    token = invitation_token(world.tenant_id, UUID(membership_id))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    first_acceptance = clock.now()
    assert membership_of(world, membership_id)["activated_at"] == first_acceptance

    clock.advance(timedelta(minutes=1))
    removed = post(app, f"{USERS}/{membership_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    removed_at = clock.now()

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, invitation(world, email, ["viewer"]))
    assert again.status_code == 201, again.text
    body = again.json()
    assert (body["id"], body["status"], body["email"]) == (membership_id, "INVITED", email)
    assert again.headers["Location"] == f"{USERS}/{membership_id}"
    row = membership_of(world, membership_id)
    assert (row["status"], row["removed_at"], row["activated_at"], row["invited_at"]) == (
        "INVITED",
        None,
        first_acceptance,
        first["invited_at"],
    )
    assert row["invitation_expires_at"] == clock.now() + timedelta(days=7)
    assert row["invitation_token_sha256"] not in (None, first["invitation_token_sha256"])
    assert (row["created_at"], row["created_by"]) == (first["created_at"], first["created_by"])
    # The role of the first life stays revoked, by the removal; the new one is a new row.
    assert sorted((item["role"]["code"], item["status"]) for item in body["roles"]) == [
        ("revenue_reviewer", "REVOKED"),
        ("viewer", "ACTIVE"),
    ]
    old, new = sorted(
        assignments_of(world, membership_id), key=lambda item: item["revoked_at"] is None
    )
    assert (old["revoked_at"], old["revoked_by"]) == (removed_at, world.tomas.member.user_id)
    assert new["revoked_at"] is None and new["id"] != old["id"]
    # One trail: what the first life wrote stands, and the invitation is appended to it.
    events = trail_of(world, membership_id)
    assert [event["action"] for event in events] == [
        "tenant_membership.invite",
        "membership.accept",
        "tenant_membership.remove",
        "tenant_membership.invite",
    ]
    assert (events[0]["before"], events[-1]["before"]["status"]) == (None, "REMOVED")
    assert events[-1]["before"]["removed_at"] == events[2]["after"]["removed_at"]
    assert (events[-1]["after"]["status"], events[-1]["after"]["removed_at"]) == ("INVITED", None)
    emails = rows(
        world.tenant_id,
        select(outbox_message.c.topic).where(outbox_message.c.aggregate_id == UUID(membership_id)),
    )
    assert [message["topic"] for message in emails] == ["EMAIL", "EMAIL"]

    # A person who is a member — invited, here — is refused as before.
    present = post(app, USERS, world.tomas, invitation(world, email, ["viewer"]))
    assert (present.status_code, fields(present)) == (422, [("email", "T-PLT-07")]), present.text
    member_too = post(
        app, USERS, world.tomas, invitation(world, world.grace.member.email, ["viewer"])
    )
    assert (member_too.status_code, fields(member_too)) == (422, [("email", "T-PLT-07")])

    # The first link is dead, the second opens; the second acceptance keeps the first.
    assert call(app, "POST", LOOKUP, json={"token": token}).status_code == 404
    clock.advance(timedelta(minutes=1))
    second = latest_token(world.tenant_id, UUID(membership_id))
    accepted_again = call(app, "POST", ACCEPT, json={"token": second, "password": PASSWORD})
    assert accepted_again.status_code == 200, accepted_again.text
    row = membership_of(world, membership_id)
    assert (row["status"], row["activated_at"]) == ("ACTIVE", first_acceptance)
    last = trail_of(world, membership_id)[-1]
    assert (last["action"], last["after"]["status"]) == ("membership.accept", "ACTIVE")
    assert last["after"]["activated_at"] == events[1]["after"]["activated_at"]


def test_reset_email_open_invitation_1_a_person_invited_again_resets_and_accepts(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Item RESET-EMAIL-OPEN-INVITATION-1 (register index 290; 04 T-PLT-42 rule 1 rev 1.308), a
    release blocker measured on this section's second life (lane F-SNP's review of index 273,
    finding M3): a person who was a member, was removed and is invited again has the first
    life's password and no ACTIVE membership. The link opened and said so, another password was
    refused — and "forgot password" answered 202, wrote its token and NO email (``email`` false
    in the security log): she could neither accept nor reset. Now the email is written in the
    inviting workspace and the invitation is accepted with the new password.

    The controls of the road: a person invited who never accepted has no password, and the reset
    sets none for her — no token, no email; between the removal and the second invitation the
    person gets a token and no email, as before."""
    reset, confirm = "/api/v1/session/password-reset", "/api/v1/session/password-reset/confirm"
    email = unique_email()
    invited = post(app, USERS, world.tomas, invitation(world, email, ["viewer"]))
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    user_id = membership_of(world, membership_id)["user_id"]

    def asked() -> tuple[int, list[Mapping[str, Any]]]:
        """One reset request, always 202 with no body: her tokens so far, and her emails."""
        sent = call(app, "POST", reset, json={"email": email})
        assert (sent.status_code, sent.content) == (202, b""), sent.text
        with identity_session(request_id="tests-users-reset-tokens") as session:
            tokens = session.execute(
                select(password_reset_token.c.id).where(password_reset_token.c.user_id == user_id)
            ).all()
        emails = rows(
            world.tenant_id,
            select(outbox_message.c.payload)
            .where(outbox_message.c.aggregate_type == "password_reset_token")
            .order_by(outbox_message.c.created_at, outbox_message.c.id),
        )
        return len(tokens), emails

    def said() -> tuple[str, Any, Any]:
        """What the security log says of her latest reset request."""
        with identity_session(request_id="tests-users-reset-event") as session:
            event = session.execute(
                select(security_event.c.outcome, security_event.c.detail)
                .where(
                    security_event.c.user_id == user_id,
                    security_event.c.kind == "PASSWORD_RESET_REQUESTED",
                )
                .order_by(security_event.c.chain_seq.desc())
                .limit(1)
            ).one()
        return str(event.outcome), event.detail["email"], event.detail.get("email_tenant_id")

    # Invited, never accepted: no password to reset and none to set without the invitation.
    assert asked() == (0, [])

    first = invitation_token(world.tenant_id, UUID(membership_id))
    accepted = call(app, "POST", ACCEPT, json={"token": first, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    clock.advance(timedelta(minutes=1))
    removed = post(app, f"{USERS}/{membership_id}/remove", world.tomas, {"reason": REASON})
    assert removed.status_code == 200, removed.text
    # Removed and not invited: a token and no email, as before.
    assert (asked(), said()) == ((1, []), ("SUCCESS", False, None))

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, invitation(world, email, ["viewer"]))
    assert again.status_code == 201, again.text
    second = latest_token(world.tenant_id, UUID(membership_id))
    looked = call(app, "POST", LOOKUP, json={"token": second})
    assert (looked.status_code, looked.json()["has_password"]) == (200, True), looked.text
    guess = "Another!Revenue2027"
    forgotten = call(app, "POST", ACCEPT, json={"token": second, "password": guess})
    assert (forgotten.status_code, slug(forgotten)) == (422, "validation-failed"), forgotten.text

    issued, emails = asked()
    assert (issued, said()) == (2, ("SUCCESS", True, str(world.tenant_id)))  # before: no email
    [message] = emails
    assert message["payload"]["to"] == email
    new_password = "Second!Ledger2031"
    confirmed = call(
        app,
        "POST",
        confirm,
        json={
            "token": emailed_token(message["payload"], prefix="/password/reset/confirm#token="),
            "new_password": new_password,
        },
    )
    assert (confirmed.status_code, confirmed.content) == (204, b""), confirmed.text
    # The first life's password went with the reset; the new one accepts the second invitation.
    stale = call(app, "POST", ACCEPT, json={"token": second, "password": PASSWORD})
    assert stale.status_code == 422, stale.text
    accepted_again = call(app, "POST", ACCEPT, json={"token": second, "password": new_password})
    assert accepted_again.status_code == 200, accepted_again.text
    assert membership_of(world, membership_id)["status"] == "ACTIVE"


def test_an_invitation_withdrawn_before_acceptance_is_issued_again(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The same transition for a person who never accepted: the invitation is withdrawn
    (``remove``) and the person is invited again on that membership. ``invited_at`` stays, as a
    re-send leaves it, so the name of a person this workspace added — who never signed in — can
    still be corrected (D-80 rule 6); the acceptance then is the first.

    Fail-first (the lane's tip): 422 "This person is already a member of this workspace."."""
    email = unique_email()
    typed = invitation(world, email, ["revenue_reviewer"], display_name="Lena Fisher")
    invited = post(app, USERS, world.tomas, typed)
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    first = membership_of(world, membership_id)
    withdrawn = invitation_token(world.tenant_id, UUID(membership_id))
    removed = post(app, f"{USERS}/{membership_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, typed)
    assert again.status_code == 201, again.text
    assert (again.json()["id"], again.json()["status"]) == (membership_id, "INVITED")
    row = membership_of(world, membership_id)
    assert (row["status"], row["removed_at"], row["activated_at"], row["invited_at"]) == (
        "INVITED",
        None,
        None,
        first["invited_at"],
    )
    assert call(app, "POST", LOOKUP, json={"token": withdrawn}).status_code == 404
    issued = latest_token(world.tenant_id, UUID(membership_id))
    looked_up = call(app, "POST", LOOKUP, json={"token": issued})
    assert looked_up.status_code == 200, looked_up.text

    path = f"{USERS}/{membership_id}"
    detail = get(app, path, world.tomas)
    assert detail.status_code == 200, detail.text
    renamed = call(
        app,
        "PATCH",
        path,
        json={"display_name": "Lena Fischer"},
        headers=cookie_headers(
            world.tomas.token, world.tomas.csrf_token, **{"If-Match": detail.headers["ETag"]}
        ),
    )
    assert (renamed.status_code, renamed.json()["display_name"]) == (200, "Lena Fischer")

    clock.advance(timedelta(minutes=1))
    accepted = call(app, "POST", ACCEPT, json={"token": issued, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    row = membership_of(world, membership_id)
    assert (row["status"], row["activated_at"]) == ("ACTIVE", clock.now())


def test_the_setup_rule_reads_a_past_approver_the_same_after_that_person_is_invited_again(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """04 T-PLT-07 rev 1.293: ``activated_at`` is the FIRST acceptance. ``routing``'s measure of
    "another approver has existed" (04 §14.3 item 3) reads it "from rows nothing erases: the
    member's acceptance, set once", against the period of the member's assignment — which the
    removal ended. Grace was the second Tenant Admin; she is removed, invited again and accepts:
    the measure answers the same at every step, and the setup rule approves nothing again.

    Fail-first (the acceptance writing ``activated_at`` anew, as it did): after Grace accepted
    the second invitation her past assignment ended before her "acceptance", the measure
    answered False, and rule AUTO-BOOTSTRAP approved Tomas's next grant."""
    assert granted(app, world, world.grace.member, "tenant_admin")  # the rule's last grant
    grace_id = str(world.grace.member.membership_id)

    def another_approver_has_existed() -> bool:
        with tenant_session(_context(world.tenant_id), read_only=True) as session:
            return routing.second_approver_has_existed(
                session,
                bootstrap_membership_id=world.tomas.member.membership_id,
                permission="access.approve",
                at=clock.now(),
            )

    assert another_approver_has_existed() is True
    clock.advance(timedelta(minutes=1))
    removed = post(app, f"{USERS}/{grace_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    assert another_approver_has_existed() is True

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, invitation(world, world.grace.member.email, ["viewer"]))
    assert again.status_code == 201, again.text
    assert (again.json()["id"], again.json()["status"]) == (grace_id, "INVITED")
    # The rule did not approve the role of the second invitation either: it waits for a person.
    assert [(item["role"]["code"], item["status"]) for item in again.json()["roles"]][-1] == (
        "viewer",
        "REQUESTED",
    )
    assert another_approver_has_existed() is True

    clock.advance(timedelta(minutes=1))
    activated_before = membership_of(world, grace_id)["activated_at"]
    token = latest_token(world.tenant_id, UUID(grace_id))
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    assert membership_of(world, grace_id)["status"] == "ACTIVE"
    assert another_approver_has_existed() is True
    uma = colleague(world.tenant_id, "uma")
    assert _outcome(_requested(app, world, uma, "viewer")) == ("REQUESTED", False)
    assert membership_of(world, grace_id)["activated_at"] == activated_before


def test_a_role_asked_for_the_first_life_is_not_decided_for_the_second(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """A role request of an invitation hashes "the membership is not removed" into its content
    (``subjects.role_assignment_content``). Withdrawn while the request waits, it is stale and
    still PENDING — nobody has tried to decide it. Invited again on the same row, its hash would
    match once more: the invitation voids it first (DG-KRN-APR-05), so the approver decides what
    was asked for the second life and nothing else.

    Fail-first (the invitation without that step): the Controller request of the first
    invitation was PENDING again, Grace approved it, and the person invited as a Viewer held
    Controller."""
    second_admin(world)
    setup_completed(world, clock)
    email = unique_email()
    invited = post(app, USERS, world.tomas, invitation(world, email, ["controller"]))
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    [first] = role_requests(world)
    assert first["status"] == "PENDING"
    removed = post(app, f"{USERS}/{membership_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    assert [request["status"] for request in role_requests(world)] == ["PENDING"]

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, invitation(world, email, ["viewer"]))
    assert again.status_code == 201, again.text
    assert again.json()["id"] == membership_id
    assert [(item["role"]["code"], item["status"]) for item in again.json()["roles"]] == [
        ("viewer", "REQUESTED")
    ]
    old, new = role_requests(world)
    assert (old["id"], old["status"], old["void_reason"]) == (
        first["id"],
        "VOIDED",
        "STALE_SUBJECT",
    )
    assert (new["status"], new["void_reason"]) == ("PENDING", None)

    seen = get(app, f"{APPROVALS}/{old['id']}", world.grace)
    assert seen.status_code == 200, seen.text
    assert (seen.json()["status"], seen.json()["can_decide"]) == ("VOIDED", False)
    refused = post(
        app,
        f"{APPROVALS}/{old['id']}/approve",
        world.grace,
        {
            "subject_content_sha256": seen.json()["subject"]["content_sha256"],
            "impact_preview_sha256": seen.json()["impact_preview"]["sha256"],
            "comment": "The Controller role of the first invitation",
        },
    )
    assert refused.status_code == 409, refused.text
    assert assignments_of(world, membership_id) == []

    detail = get(app, f"{APPROVALS}/{new['id']}", world.grace)
    assert detail.status_code == 200, detail.text
    approved = post(
        app,
        f"{APPROVALS}/{new['id']}/approve",
        world.grace,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "Viewer access, as invited again",
        },
    )
    assert approved.status_code == 200, approved.text
    [assignment] = assignments_of(world, membership_id)
    assert str(assignment["role_id"]) == role_id(world.tenant_id, "viewer")


# --- item SBX-COPY-OPEN-INVITATION-1, what the independent review of its head found (PRD SM-13;
# 04 T-PLT-07 "Invited again"; PRD BR-PLT-07): nothing asked or granted for the first life passes
# into the second — whoever invites, and whoever gave it ---

DELEGATIONS = "/api/v1/approval-delegations"


def approved_by(app: FastAPI, actor: Actor, request_id: Any, comment: str) -> HttpResponse:
    """The approver's read of the request and the approval with what it read."""
    detail = get(app, f"{APPROVALS}/{request_id}", actor)
    assert detail.status_code == 200, detail.text
    return post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        actor,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": comment,
        },
    )


def pending_role_requests(world: World) -> list[Mapping[str, Any]]:
    return [request for request in role_requests(world) if request["status"] == "PENDING"]


def test_a_delegation_given_to_the_first_life_does_not_decide_for_the_second(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """PRD BR-PLT-07: a delegation ends, and never returns, when its delegate is removed. Grace,
    who approves access, delegates ``access.approve`` to Vic, a Viewer. Vic is removed: the
    removal ends the delegation, stamped by the remover, with its ``approval_delegation.end``
    event naming the delegate's status. Vic is invited again as a Viewer and accepts: the engine
    honours nothing for the second life, and Tomas's Controller grant for Uma is not Vic's to
    read or to decide.

    Fail-first (16dc7693: the sweep ended what a member GAVE, and the engine asks nothing of the
    delegate): the delegation stood with ``revoked_at`` null — inert while REMOVED was the last
    state — and after the second acceptance Vic, invited as a Viewer, read the Controller request
    with ``can_decide`` true and approved it on Grace's behalf."""
    second_admin(world)
    setup_completed(world, clock)
    vic_member = colleague(world.tenant_id, "vic")
    with tenant_session(_context(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=vic_member.membership_id,
            role_code="viewer",
        )
    vic = enrolled(app, clock, vic_member)
    now = clock.now()
    given = post(
        app,
        DELEGATIONS,
        world.grace,
        {
            "delegate_membership_id": str(vic_member.membership_id),
            "permissions": ["access.approve"],
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "reason": "Cover while I am away",
        },
    )
    assert given.status_code == 201, given.text
    delegation_id = UUID(given.json()["id"])

    def honoured() -> list[UUID]:
        with tenant_session(_context(world.tenant_id), read_only=True) as session:
            found = in_force_delegations(session, vic_member.membership_id, at=clock.now())
        return [item.id for item in found]

    assert honoured() == [delegation_id]

    clock.advance(timedelta(minutes=1))
    vic_id = str(vic_member.membership_id)
    removed = post(app, f"{USERS}/{vic_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    [ended] = rows(
        world.tenant_id,
        select(approval_delegation.c.revoked_at, approval_delegation.c.revoked_by).where(
            approval_delegation.c.id == delegation_id
        ),
    )
    assert (ended["revoked_at"], ended["revoked_by"]) == (clock.now(), world.tomas.member.user_id)
    [event] = rows(
        world.tenant_id,
        select(audit_event.c.detail).where(
            audit_event.c.action == "approval_delegation.end",
            audit_event.c.object_id == delegation_id,
        ),
    )
    assert event["detail"] == {
        "cause": "membership-status",
        "delegator_status": "ACTIVE",
        "lost_permissions": [],
        "delegate_status": "REMOVED",
    }

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, invitation(world, vic_member.email, ["viewer"]))
    assert again.status_code == 201, again.text
    [request] = pending_role_requests(world)
    approved = approved_by(app, world.grace, request["id"], "Viewer, as invited again")
    assert approved.status_code == 200, approved.text
    clock.advance(timedelta(minutes=1))
    token = latest_token(world.tenant_id, vic_member.membership_id)
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    assert membership_of(world, vic_id)["status"] == "ACTIVE"
    assert honoured() == []

    clock.advance(timedelta(minutes=1))
    vic = workspace(app, vic_member, sign_in(app, vic_member.email), vic.secret)
    uma = colleague(world.tenant_id, "uma")
    asked = _requested(app, world, uma, "controller")
    assert _outcome(asked) == ("REQUESTED", False)
    # The Viewer of the second life is no approver: the request answers as one that is not theirs.
    unseen = get(app, f"{APPROVALS}/{asked['approval_request_id']}", vic)
    assert (unseen.status_code, slug(unseen)) == (404, "not-found"), unseen.text
    refused = post(
        app,
        f"{APPROVALS}/{asked['approval_request_id']}/approve",
        vic,
        {"subject_content_sha256": "0" * 64, "impact_preview_sha256": "0" * 64, "comment": "OK"},
    )
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert assignments_of(world, str(uma.membership_id)) == []


def test_an_assignment_left_on_a_removed_row_is_revoked_by_the_invitation(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """04 T-PLT-07 rev 1.306 (item INVITE-ENDS-STANDING-ASSIGNMENTS-1): "none is revived". A
    removal revokes the member's assignments; one that stands on the removed row all the same —
    an approval that passed its check before the removal committed inserts after it — was inert
    while REMOVED was the last state of a membership. The invitation revokes whatever stands on
    the row before the status changes, with its ``role_assignment.revoke`` event, whatever left
    it there; the person holds what the new invitation's roles give, once they are approved, and
    nothing else. The state is written by the test: the race that leaves it is not run.

    Fail-first (317f62a9b): the Controller assignment stayed in force through the invitation —
    the answer listed it ACTIVE — and from the acceptance the person invited as a Viewer held
    Controller: 26 permissions, ``config.approve``, ``period.lock`` and ``journal.approve``
    among them (the probe of the independent review)."""
    second_admin(world)
    setup_completed(world, clock)
    lena = colleague(world.tenant_id, "lena")
    lena_id = str(lena.membership_id)
    removed = post(app, f"{USERS}/{lena_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    with tenant_session(_context(world.tenant_id)) as session:
        insert_role_assignment(
            session,
            tenant_id=world.tenant_id,
            membership_id=lena.membership_id,
            role_code="controller",
        )
    [left] = assignments_of(world, lena_id)
    assert left["revoked_at"] is None

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, world.tomas, invitation(world, lena.email, ["viewer"]))
    assert again.status_code == 201, again.text
    assert sorted((item["role"]["code"], item["status"]) for item in again.json()["roles"]) == [
        ("controller", "REVOKED"),
        ("viewer", "REQUESTED"),
    ]
    [revoked] = assignments_of(world, lena_id)
    assert (revoked["id"], revoked["revoked_at"], revoked["revoked_by"]) == (
        left["id"],
        clock.now(),
        world.tomas.member.user_id,
    )
    events = rows(
        world.tenant_id,
        select(audit_event.c.action, audit_event.c.comment).where(
            audit_event.c.object_type == "role_assignment", audit_event.c.object_id == left["id"]
        ),
    )
    assert [(event["action"], event["comment"]) for event in events] == [
        ("role_assignment.revoke", "The member was removed and is invited again.")
    ]

    # The second life holds the invitation's role, once it is approved, and nothing of before.
    [request] = pending_role_requests(world)
    approved = approved_by(app, world.grace, request["id"], "Viewer, as invited again")
    assert approved.status_code == 200, approved.text
    clock.advance(timedelta(minutes=1))
    token = latest_token(world.tenant_id, lena.membership_id)
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text
    codes = {str(found["id"]): str(found["code"]) for found in rows(world.tenant_id, select(role))}
    assert sorted(
        (codes[str(item["role_id"])], item["revoked_at"] is None)
        for item in assignments_of(world, lena_id)
    ) == [("controller", False), ("viewer", True)]


def test_two_invitations_of_one_removed_person_are_one(
    app: FastAPI, world: World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invitation of a removed person locks the membership's row and reads its status again
    under the lock (04 T-PLT-07 "Invited again"). Tomas and Grace invite the same removed person
    at once: the second is observed waiting for the first at that row, and once the first has
    committed it finds the person a member again — 422, one invitation, one email, one request.

    Test only (the independent review of the item's head: the check had no witness). Fail-first
    (the status not read again under the lock): the second invitation went on over the first —
    201, a second token that kills the first link, a second email and a second request."""
    from erev_api.domain.platform import users as users_domain

    second_admin(world)
    lena = colleague(world.tenant_id, "lena")
    lena_id = str(lena.membership_id)
    removed = post(app, f"{USERS}/{lena_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text
    clock.advance(timedelta(minutes=1))
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, Any] = {}
    end_first_life = users_domain._end_first_life  # noqa: SLF001 - the first step under the lock

    def under_the_lock(uow: Any, membership_id: UUID) -> None:
        # The first invitation's call: the second never comes this far (a request runs in a
        # worker thread, so the caller is told apart by the order, not by a thread's name).
        if not holding.is_set():
            seen["holder"] = backend_pid(uow.session)
            holding.set()
            assert release.wait(timeout=60), "the first invitation was never let go"
        end_first_life(uow, membership_id)

    def inviting(name: str, actor: Actor) -> None:
        try:
            seen[name] = post(app, USERS, actor, invitation(world, lena.email, ["viewer"]))
        except BaseException as error:  # noqa: BLE001 - handed to the asserting thread
            seen[name] = error

    monkeypatch.setattr(users_domain, "_end_first_life", under_the_lock)
    first = threading.Thread(target=inviting, args=("first", world.tomas), name="first")
    second = threading.Thread(target=inviting, args=("second", world.grace), name="second")
    first.start()
    try:
        assert holding.wait(timeout=60), seen
        with (
            identity_session(request_id="tests-users-watch") as watch,
            observing_checkouts() as backends,
        ):
            second.start()
            _, waited_in = await_lock_wait(
                watch,
                holder_pid=seen["holder"],
                backends=backends,
                timeout=40,
                while_running=second.is_alive,
            )
            assert "second" not in seen  # the second has not answered: it waits
    finally:
        release.set()
        first.join(timeout=120)
        if second.ident is not None:
            second.join(timeout=120)
    assert not first.is_alive() and not second.is_alive()
    one, two = seen["first"], seen["second"]
    assert not isinstance(one, BaseException), one
    assert not isinstance(two, BaseException), two
    assert "erev.tenant_membership" in waited_in and "for update" in waited_in.lower()
    assert (one.status_code, one.json()["status"]) == (201, "INVITED"), one.text
    assert two.status_code == 422, two.text
    assert fields(two) == [("email", "T-PLT-07")]
    emails = rows(
        world.tenant_id,
        select(outbox_message.c.id).where(outbox_message.c.aggregate_id == lena.membership_id),
    )
    invitations = [
        event for event in trail_of(world, lena_id) if event["action"] == "tenant_membership.invite"
    ]
    assert (len(emails), len(invitations), len(pending_role_requests(world))) == (1, 1, 1)


def test_what_an_invitation_ends_does_not_depend_on_the_inviters_entities(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """A role request for ONE entity is a row an administrator of another entity does not read
    (RLS-TE on ``approval_request.entity_id``; 04 §16.10). Tomas invites Lena with Controller for
    AVM-US and withdraws the invitation; the request stays PENDING and stale. Dieter, Tenant
    Admin for AVM-DE alone, invites Lena again with Viewer for AVM-DE. The invitation voids the
    AVM-US request all the same — what it ends is the invitation's own control, read under the
    tenant's SYSTEM scope (rulings R-42 (d), R-64 (1)) — and Grace finds nothing of the first
    life to decide. Dieter is answered what he may read: the role he asked for.

    Fail-first (16dc7693, the sweep under the inviter's scope): Dieter's invitation did not see
    the request; it was PENDING with a matching hash again, Grace approved it, and the person
    invited as a Viewer for AVM-DE held Controller for AVM-US."""
    ids = legal_entities(app, world, "AVM-DE", "AVM-US")
    dieter = scoped_admin(app, world, clock, "dieter", "AVM-DE")
    second_admin(world)
    setup_completed(world, clock)
    email = unique_email()
    invited = post(
        app, USERS, world.tomas, invitation(world, email, ["controller"], entity_codes=["AVM-US"])
    )
    assert invited.status_code == 201, invited.text
    membership_id = invited.json()["id"]
    [first] = pending_role_requests(world)
    assert str(first["entity_id"]) == ids["AVM-US"]  # the row-level key of the request
    removed = post(app, f"{USERS}/{membership_id}/remove", world.tomas, {"reason": REASON})
    assert (removed.status_code, removed.json()["status"]) == (200, "REMOVED"), removed.text

    clock.advance(timedelta(minutes=1))
    again = post(app, USERS, dieter, invitation(world, email, ["viewer"], entity_codes=["AVM-DE"]))
    assert again.status_code == 201, again.text
    assert again.json()["id"] == membership_id
    assert shown_roles(again) == [("REQUESTED", False, ["AVM-DE"])]
    [old] = [request for request in role_requests(world) if request["id"] == first["id"]]
    assert (old["status"], old["void_reason"]) == ("VOIDED", "STALE_SUBJECT")

    seen = get(app, f"{APPROVALS}/{first['id']}", world.grace)
    assert seen.status_code == 200, seen.text
    assert (seen.json()["status"], seen.json()["can_decide"]) == ("VOIDED", False)
    refused = post(
        app,
        f"{APPROVALS}/{first['id']}/approve",
        world.grace,
        {
            "subject_content_sha256": seen.json()["subject"]["content_sha256"],
            "impact_preview_sha256": seen.json()["impact_preview"]["sha256"],
            "comment": "The Controller role of the first invitation",
        },
    )
    assert refused.status_code == 409, refused.text
    assert assignments_of(world, membership_id) == []
