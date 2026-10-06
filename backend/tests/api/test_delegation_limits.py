"""Approval delegations: who may hold one, how long it lasts, when it ends and who ends it (04
T-PLT-21, API-R-09; PRD BR-PLT-06, BR-PLT-07 rev 1.118; 03 REQ-PLT-005, REQ-PLT-010; SCREENS
§15.7 rev 1.27; independent review of the platform security merge, findings 2, 6 and 8;
supervisor ruling R-111 (2), (4), (6) and (9)).

The world: Tomas and Grace administer access (Tenant Admin, enrolled); Rhea is a Revenue Reviewer
(enrolled) and gives delegations; Vic is a Viewer with an authenticator app, to whom she
delegates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import delegations
from erev_api.approvals.engine import in_force_delegations
from erev_api.auth import mfa
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_delegation, audit_event, role, role_assignment
from erev_api.domain.platform import approval_delegations
from erev_api.enums import GrantStatus, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.operators import approve as approve_grant
from support.operators import create_operator, operator_services, operator_signed_in
from support.principals import (
    Actor,
    Member,
    authenticator,
    colleague,
    cookie_headers,
    cookie_of,
    enrolled,
    member,
    select_tenant,
    sign_in,
    step_up,
    workspace,
)
from support.rows import (
    insert_approval_delegation,
    insert_contract_rows,
    insert_custom_role,
    insert_role_assignment,
    insert_sod_exception,
)

DELEGATIONS = "/api/v1/approval-delegations"
ASSIGNMENTS = "/api/v1/role-assignments"
ROLES = "/api/v1/roles"
USERS = "/api/v1/users"
APPROVALS = "/api/v1/approvals"
GRANTS = "/api/v1/support-grants"
ENROLL = "/api/v1/me/mfa/enroll"
PROBLEM_BASE = "https://erev.dev/problems/"
REASON = "Cover while I am away"
SOD_3 = (
    "Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets one "
    "person create and approve the same contract or modification."
)


@dataclass(frozen=True, slots=True)
class World:
    tomas: Actor
    grace: Actor
    rhea: Actor
    vic: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.tomas.member.tenant_id


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def assign(someone: Member, role_code: str, *, entity_ids: tuple[UUID, ...] = ()) -> UUID:
    with tenant_session(_all_entities(someone.tenant_id)) as session:
        return insert_role_assignment(
            session,
            tenant_id=someone.tenant_id,
            membership_id=someone.membership_id,
            role_code=role_code,
            entity_ids=entity_ids,
        )


def with_factor(app: FastAPI, someone: Member) -> Actor:
    """The member has an authenticator app, and a session that answered its challenge."""
    authenticator(app, someone)
    return workspace(app, someone, sign_in(app, someone.email))


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    tomas = member(keyring, clock)
    grace = colleague(tomas.tenant_id, "grace")
    rhea = colleague(tomas.tenant_id, "rhea")
    vic = colleague(tomas.tenant_id, "vic")
    assign(tomas, "tenant_admin")
    assign(grace, "tenant_admin")
    assign(rhea, "revenue_reviewer")
    assign(vic, "viewer")
    return World(
        tomas=enrolled(app, clock, tomas),
        grace=enrolled(app, clock, grace),
        rhea=enrolled(app, clock, rhea),
        vic=with_factor(app, vic),
    )


def get(app: FastAPI, path: str, actor: Actor, **params: str) -> HttpResponse:
    return call(app, "GET", path, params=params, headers=cookie_headers(actor.token, key=False))


def post(
    app: FastAPI, path: str, actor: Actor, json: Mapping[str, Any], **headers: str
) -> HttpResponse:
    return call(
        app,
        "POST",
        path,
        json=json,
        headers=cookie_headers(actor.token, actor.csrf_token, **headers),
    )


def slug(response: HttpResponse) -> str:
    return str(response.json()["type"]).removeprefix(PROBLEM_BASE)


def fields(response: HttpResponse) -> list[tuple[str | None, str | None, str]]:
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def body(
    delegate: Member,
    *permissions: str,
    start: datetime,
    end: datetime,
    reason: str = REASON,
) -> dict[str, Any]:
    return {
        "delegate_membership_id": str(delegate.membership_id),
        "permissions": list(permissions or ("contract.approve",)),
        "valid_from": start.isoformat(),
        "valid_to": end.isoformat(),
        "reason": reason,
    }


def stored(tenant_id: UUID) -> list[dict[str, Any]]:
    """The delegations of the workspace as stored, oldest first."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(approval_delegation).order_by(approval_delegation.c.created_at)
        ).mappings()
        return [dict(row) for row in rows]


def row_of(tenant_id: UUID, delegation_id: Any) -> dict[str, Any]:
    [found] = [row for row in stored(tenant_id) if row["id"] == UUID(str(delegation_id))]
    return found


def events(tenant_id: UUID) -> list[tuple[str, str, UUID | None, dict[str, Any]]]:
    """(action, outcome, actor, detail) of the audit events of delegations, in chain order."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.outcome,
                audit_event.c.actor_id,
                audit_event.c.detail,
            )
            .where(audit_event.c.object_type == approval_delegations.OBJECT_TYPE)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(action), str(getattr(outcome, "value", outcome)), actor_id, dict(detail or {}))
        for action, outcome, actor_id, detail in rows
    ]


def in_force(tenant_id: UUID, delegate: Member, at: datetime) -> list[UUID]:
    """The delegations the approval engine would honour for the delegate at ``at``."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        return [item.id for item in in_force_delegations(session, delegate.membership_id, at=at)]


def context(principal: Principal, clock: FrozenClock) -> RequestContext:
    """The request context of a principal built by the test: a command called without a route."""
    return RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-delegation-command",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


def given(app: FastAPI, world: World, clock: FrozenClock, *permissions: str) -> str:
    """Rhea delegates ``permissions`` (``contract.approve`` by default) to Vic for 30 days."""
    now = clock.now()
    created = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(world.vic.member, *permissions, start=now, end=now + timedelta(days=30)),
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


# --- R-111 (2): a delegation never turns a password-only account into an approver ----------------


def test_r_111_2_a_delegation_goes_only_to_a_member_with_a_confirmed_second_factor(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Independent review of the platform security merge, finding 2 (HOLE). A member with no
    approval role and no factor, given a delegation of an approval permission, became an approver
    by enrolling an authenticator with the password alone. A delegation is created only to a
    member whose second factor is confirmed, and is refused by name on the Delegate field
    otherwise; a factor that was started and never confirmed is none."""
    now = clock.now()
    pia_member = colleague(world.tenant_id, "pia")
    assign(pia_member, "viewer")
    signed = sign_in(app, pia_member.email)
    assert (signed.body["mfa_required"], signed.body["mfa_enrolment_required"]) == (False, False)
    pia = workspace(app, pia_member, signed)
    wanted = body(pia_member, start=now, end=now + timedelta(days=30))

    refused = post(app, DELEGATIONS, world.rhea, wanted)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [
        (
            "delegate_membership_id",
            "BR-PLT-07",
            "Choose a member who has set up multi-factor authentication.",
        )
    ]
    # She starts the enrolment and does not confirm it: still no factor.
    started = post(app, ENROLL, pia, {})
    assert started.status_code == 200, started.text
    again = post(app, DELEGATIONS, world.rhea, wanted)
    assert (again.status_code, fields(again)) == (422, fields(refused)), again.text
    assert stored(world.tenant_id) == []

    # Positive control: Vic has an authenticator app.
    created = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(world.vic.member, start=now, end=now + timedelta(days=30)),
    )
    assert created.status_code == 201, created.text
    assert [row["delegate_membership_id"] for row in stored(world.tenant_id)] == [
        world.vic.member.membership_id
    ]


# --- R-111 (4): the limits of a delegation -------------------------------------------------------


def test_r_111_4_a_delegation_ends_within_90_days_of_the_command(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Review finding 6: the 90 days ran from a ``valid_from`` of any date and rows could follow
    one another, so one step-up created delegations that covered years. A delegation ends no
    later than 90 days after the command that creates it, whatever day it starts."""
    now = clock.now()
    vic = world.vic.member

    later = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(vic, start=now + timedelta(days=30), end=now + timedelta(days=100)),
    )
    assert (later.status_code, slug(later)) == (422, "validation-failed"), later.text
    assert fields(later) == [
        ("valid_to", "BR-PLT-07", "A delegation ends within 90 days of today.")
    ]
    # The row's own length is still bounded, and says so in its own words.
    long = post(
        app, DELEGATIONS, world.rhea, body(vic, start=now, end=now + timedelta(days=90, seconds=1))
    )
    assert fields(long) == [("valid_to", "BR-PLT-07", "A delegation lasts at most 90 days.")]
    assert stored(world.tenant_id) == []

    # Positive control: the last instant the command admits.
    first = post(app, DELEGATIONS, world.rhea, body(vic, start=now, end=now + timedelta(days=90)))
    assert first.status_code == 201, first.text
    # Rows do not follow one another beyond it: the next 90 days cannot be given today.
    following = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(vic, start=now + timedelta(days=90), end=now + timedelta(days=150)),
    )
    assert fields(following) == [
        ("valid_to", "BR-PLT-07", "A delegation ends within 90 days of today.")
    ]
    assert len(stored(world.tenant_id)) == 1


@pytest.mark.control("CTL-034")
def test_r_111_4_a_delegation_is_checked_for_separation_of_duties(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Review finding 6: the command ran no separation-of-duties check, so a preparer was handed
    the approval of what they prepare. It runs the check a role assignment runs — the delegate's
    grants with the delegated permissions — and names the permission; an approved exception
    covers the conflict, and a delegate whose grants no rule sets against it is accepted."""
    now = clock.now()
    maya_member = colleague(world.tenant_id, "maya")
    assign(maya_member, "revenue_accountant")
    with_factor(app, maya_member)
    wanted = body(
        maya_member,
        "import.approve",
        "contract.approve",
        start=now,
        end=now + timedelta(days=30),
    )

    refused = post(app, DELEGATIONS, world.rhea, wanted)
    assert (refused.status_code, slug(refused)) == (409, "sod-conflict"), refused.text
    assert fields(refused) == [("permissions[0]", "SoD-3", SOD_3)]
    assert stored(world.tenant_id) == []

    with tenant_session(_all_entities(world.tenant_id)) as session:
        insert_sod_exception(
            session,
            tenant_id=world.tenant_id,
            membership_id=maya_member.membership_id,
            status=GrantStatus.APPROVED,
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=60),
        )
    covered = post(app, DELEGATIONS, world.rhea, wanted)
    assert covered.status_code == 201, covered.text
    # Positive control: nothing a Viewer holds is set against an approval.
    plain = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(world.vic.member, start=now, end=now + timedelta(days=30)),
    )
    assert plain.status_code == 201, plain.text


def role_id_of(tenant_id: UUID, code: str) -> str:
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        return str(session.execute(select(role.c.id).where(role.c.code == code)).scalar_one())


@pytest.mark.control("CTL-034")
def test_r_111_4_a_role_is_checked_against_a_delegation_that_has_not_started(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """A delegation given today for next week comes into force without a further command, so a
    command counts it as held from the moment it is given. Counted only once it had started, the
    preparing role was granted in between and the delegate held both sides of SoD-3 from the
    delegation's first day, with no command left to refuse it. The role is refused while the
    delegation is to come, and accepted once it is revoked (positive control)."""
    tenant_id = world.tenant_id
    now = clock.now()
    vic = world.vic.member
    scheduled = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(vic, start=now + timedelta(days=5), end=now + timedelta(days=30)),
    )
    assert scheduled.status_code == 201, scheduled.text
    assert in_force(tenant_id, vic, now) == []  # it has not started

    wanted = {
        "membership_id": str(vic.membership_id),
        "role_id": role_id_of(tenant_id, "revenue_accountant"),
    }
    refused = post(app, ASSIGNMENTS, world.tomas, wanted)
    assert refused.status_code == 409, refused.text
    assert (slug(refused), fields(refused)) == ("sod-conflict", [("role_id", "SoD-3", SOD_3)])

    revoked = post(
        app,
        f"{DELEGATIONS}/{scheduled.json()['id']}/revoke",
        world.rhea,
        {"reason": "The leave is cancelled"},
    )
    assert revoked.status_code == 200, revoked.text
    accepted = post(app, ASSIGNMENTS, world.tomas, wanted)
    assert accepted.status_code == 201, accepted.text


@pytest.mark.control("CTL-034")
def test_r_111_4_a_delegation_is_checked_against_one_that_has_not_started(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """The same between two delegations: access administration given for next week (SoD-1
    function A) and a transaction approval asked for today (function B). The second is refused by
    name; a member who was given nothing takes it (positive control)."""
    now = clock.now()
    wes_member = colleague(world.tenant_id, "wes")
    assign(wes_member, "viewer")
    with_factor(app, wes_member)
    scheduled = post(
        app,
        DELEGATIONS,
        world.tomas,
        body(
            wes_member,
            "access.approve",
            start=now + timedelta(days=5),
            end=now + timedelta(days=30),
        ),
    )
    assert scheduled.status_code == 201, scheduled.text

    month = {"start": now, "end": now + timedelta(days=30)}
    refused = post(app, DELEGATIONS, world.rhea, body(wes_member, **month))
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "sod-conflict"
    assert fields(refused) == [
        (
            "permissions[0]",
            "SoD-1",
            "Separation of duties conflict SoD-1: user administration with transaction or "
            "approval permissions.",
        )
    ]
    assert [row["id"] for row in stored(world.tenant_id)] == [UUID(scheduled.json()["id"])]

    plain = post(app, DELEGATIONS, world.rhea, body(world.vic.member, **month))
    assert plain.status_code == 201, plain.text


def test_r_111_4_a_delegation_ends_when_its_delegator_loses_the_permission_or_the_membership(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Review finding 6: a delegation whose delegator lost the role lay dormant and came back to
    life when the role returned. It ends with the loss — stamped, audited with its cause — and
    stays ended when the access returns: by a revoked role assignment, by a suspended membership
    and by a changed role. A delegation whose delegator keeps everything stands (positive
    control), and one that has not started yet ends like one that has."""
    tenant_id = world.tenant_id
    vic = world.vic.member
    now = clock.now()
    # Ravi keeps his access throughout; Rio will be suspended; Remy holds a custom role.
    ravi_member = colleague(tenant_id, "ravi")
    rio_member = colleague(tenant_id, "rio")
    remy_member = colleague(tenant_id, "remy")
    assign(ravi_member, "revenue_reviewer")
    assign(rio_member, "revenue_reviewer")
    with tenant_session(_all_entities(tenant_id)) as session:
        desk = insert_custom_role(
            session,
            tenant_id=tenant_id,
            code="deal_desk_approver",
            permissions=["contract.read", "contract.approve", "event.approve"],
        )
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=remy_member.membership_id,
            role_code="deal_desk_approver",
        )
    ravi = enrolled(app, clock, ravi_member)
    rio = enrolled(app, clock, rio_member)
    remy = enrolled(app, clock, remy_member)
    month = {"start": now, "end": now + timedelta(days=30)}

    rhea_assignment = stored_assignment(tenant_id, world.rhea.member)
    lost = given(app, world, clock)
    not_started = post(
        app,
        DELEGATIONS,
        world.rhea,
        body(vic, "event.approve", start=now + timedelta(days=5), end=now + timedelta(days=30)),
    )
    kept = post(app, DELEGATIONS, ravi, body(vic, **month))
    suspended = post(app, DELEGATIONS, rio, body(vic, **month))
    changed = post(app, DELEGATIONS, remy, body(vic, "contract.approve", "event.approve", **month))
    for created in (not_started, kept, suspended, changed):
        assert created.status_code == 201, created.text
    assert set(in_force(tenant_id, vic, now)) == {
        UUID(lost),
        UUID(kept.json()["id"]),
        UUID(suspended.json()["id"]),
        UUID(changed.json()["id"]),
    }

    # 1. Rhea's role assignment is revoked: both of her delegations end, at once.
    revoked = post(
        app,
        f"{ASSIGNMENTS}/{rhea_assignment}/revoke",
        world.tomas,
        {"reason": "Rhea moved to another team"},
    )
    assert revoked.status_code == 200, revoked.text
    for delegation_id in (lost, not_started.json()["id"]):
        ended = row_of(tenant_id, delegation_id)
        assert (ended["revoked_at"], ended["revoked_by"]) == (
            clock.now(),
            world.tomas.member.user_id,
        )
    # ... and the role returning gives nothing back.
    assign(world.rhea.member, "revenue_reviewer")
    assert UUID(lost) not in in_force(tenant_id, vic, clock.now())
    assert row_of(tenant_id, lost)["revoked_at"] is not None

    # 2. Rio is suspended, then reactivated.
    path = f"{USERS}/{rio_member.membership_id}"
    assert (
        post(
            app, f"{path}/suspend", world.tomas, {"reason": "Rio is on extended leave"}
        ).status_code
        == 200
    )
    assert row_of(tenant_id, suspended.json()["id"])["revoked_at"] == clock.now()
    assert (
        post(app, f"{path}/reactivate", world.tomas, {"reason": "Rio is back"}).status_code == 200
    )
    assert UUID(suspended.json()["id"]) not in in_force(tenant_id, vic, clock.now())

    # 3. Remy's role loses one of the two permissions he delegated: the delegation ends whole.
    detail = get(app, f"{ROLES}/{desk}", world.tomas)
    assert detail.status_code == 200, detail.text
    proposed = post(
        app,
        f"{ROLES}/{desk}/propose-change",
        world.tomas,
        {
            "permissions": ["contract.read", "contract.approve"],
            "comment": "The desk approves no events",
        },
        **{"If-Match": detail.headers["ETag"]},
    )
    assert proposed.status_code == 200, proposed.text
    change_id = str(proposed.json()["pending_approval_request_id"])
    assert approve(app, change_id, world.grace).status_code == 200
    assert row_of(tenant_id, changed.json()["id"])["revoked_by"] == world.grace.member.user_id

    # Positive control: Ravi lost nothing, and his delegation stands.
    assert in_force(tenant_id, vic, clock.now()) == [UUID(kept.json()["id"])]
    assert row_of(tenant_id, kept.json()["id"])["revoked_at"] is None

    ends = [
        (actor, detail) for action, _, actor, detail in events(tenant_id) if action.endswith(".end")
    ]
    assert ends == [
        (
            world.tomas.member.user_id,
            {
                "cause": "role-assignment-revoked",
                "delegator_status": "ACTIVE",
                "lost_permissions": ["contract.approve"],
            },
        ),
        (
            world.tomas.member.user_id,
            {
                "cause": "role-assignment-revoked",
                "delegator_status": "ACTIVE",
                "lost_permissions": ["event.approve"],
            },
        ),
        (
            world.tomas.member.user_id,
            {
                "cause": "membership-status",
                "delegator_status": "SUSPENDED",
                "lost_permissions": [],
            },
        ),
        (
            world.grace.member.user_id,
            {
                "cause": "role-changed",
                "delegator_status": "ACTIVE",
                "lost_permissions": ["event.approve"],
            },
        ),
    ]
    assert remy and rio  # their sessions gave the delegations above


def stored_assignment(tenant_id: UUID, someone: Member) -> UUID:
    """The id of the member's one unrevoked role assignment."""
    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        return UUID(
            str(
                session.execute(
                    select(role_assignment.c.id).where(
                        role_assignment.c.membership_id == someone.membership_id,
                        role_assignment.c.revoked_at.is_(None),
                    )
                ).scalar_one()
            )
        )


def approve(app: FastAPI, request_id: str, approver: Actor) -> HttpResponse:
    detail = get(app, f"{APPROVALS}/{request_id}", approver)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is True, detail.text
    shown = detail.json()
    answer: dict[str, Any] = {
        "subject_content_sha256": shown["subject"]["content_sha256"],
        "comment": "Reviewed the change",
    }
    if shown["impact_preview"] is not None:
        answer["impact_preview_sha256"] = shown["impact_preview"]["sha256"]
    return post(app, f"{APPROVALS}/{request_id}/approve", approver, answer)


def test_r_111_4_a_grant_revives_no_delegation(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Ruling R-111 (4), the other direction. A delegation that lost its support by a path no
    command saw — here a role assignment that ran out — is ended before a command gives its
    delegator the permission back through another role, so that the grant revives nothing."""
    tenant_id = world.tenant_id
    now = clock.now()
    lena = colleague(tenant_id, "lena")
    with tenant_session(_all_entities(tenant_id)) as session:
        insert_custom_role(
            session,
            tenant_id=tenant_id,
            code="interim_approver",
            permissions=["contract.read", "contract.approve"],
        )
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=lena.membership_id,
            role_code="interim_approver",
            valid_to=now - timedelta(days=1),  # ran out yesterday
        )
        dormant = insert_approval_delegation(
            session,
            tenant_id=tenant_id,
            delegator_membership_id=lena.membership_id,
            delegate_membership_id=world.vic.member.membership_id,
            valid_from=now - timedelta(days=10),
            valid_to=now + timedelta(days=20),
        )
    # Nobody may decide with it, and it is not ended either: the state the review found.
    assert in_force(tenant_id, world.vic.member, now) == [dormant]
    assert row_of(tenant_id, dormant)["revoked_at"] is None

    with tenant_session(_all_entities(tenant_id), read_only=True) as session:
        reviewer = session.execute(
            select(role.c.id).where(role.c.code == "revenue_reviewer")
        ).scalar_one()
    granted = post(
        app,
        ASSIGNMENTS,
        world.tomas,
        {"membership_id": str(lena.membership_id), "role_id": str(reviewer)},
    )
    assert granted.status_code == 201, granted.text
    granting = world.tomas  # a setup grant is applied at once, in the requester's command
    if granted.json()["status"] == "REQUESTED":
        granting = world.grace
        assert approve(app, str(granted.json()["approval_request_id"]), granting).status_code == 200
    ended = row_of(tenant_id, dormant)
    assert (ended["revoked_at"], ended["revoked_by"]) == (clock.now(), granting.member.user_id)
    assert in_force(tenant_id, world.vic.member, clock.now()) == []
    assert [
        detail for action, _, _, detail in events(tenant_id) if action == delegations.END_ACTION
    ] == [
        {
            "cause": "role-assignment-granted",
            "delegator_status": "ACTIVE",
            "lost_permissions": ["contract.approve"],
        }
    ]


def test_r_111_4_an_access_administrator_ends_any_delegation(
    app: FastAPI,
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
    app_settings: Settings,
) -> None:
    """Review finding 6: only the delegator ended a delegation; an access administrator could
    not. A holder of ``role.manage`` lists the delegations they may end — every one for an
    administrator of all entities — and ends any whose delegator's access lies within their own,
    with the step-up; a refusal for want of the step-up or of the scope is audited (R-111 (6)).
    A member who is no party to the delegation is answered as for an id that names none, and
    its delegate is told who may end it."""
    tenant_id = world.tenant_id
    now = clock.now()
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id).entity_id
    # Sven administers access for one entity; Nora approves for that entity alone.
    sven_member = colleague(tenant_id, "sven")
    nora_member = colleague(tenant_id, "nora")
    otto_member = colleague(tenant_id, "otto")  # a member without a role
    assign(sven_member, "tenant_admin", entity_ids=(north,))
    assign(nora_member, "revenue_reviewer", entity_ids=(north,))
    sven = enrolled(app, clock, sven_member)
    nora = enrolled(app, clock, nora_member)
    otto = workspace(app, otto_member, sign_in(app, otto_member.email))

    wide = given(app, world, clock)  # Rhea approves for all entities
    narrow = post(
        app,
        DELEGATIONS,
        nora,
        body(world.vic.member, start=now, end=now + timedelta(days=30)),
    )
    assert narrow.status_code == 201, narrow.text
    narrow_id = str(narrow.json()["id"])

    # The administrator of every entity sees every delegation; Sven, who administers one
    # entity, the one he may end (item DELEG-LIST-SCOPE-1); the delegate what she received;
    # Otto none.
    listed = get(app, DELEGATIONS, world.tomas)
    assert {item["id"] for item in listed.json()["items"]} == {wide, narrow_id}, listed.text
    listed = get(app, DELEGATIONS, sven)
    assert {item["id"] for item in listed.json()["items"]} == {narrow_id}, listed.text
    assert {item["id"] for item in get(app, DELEGATIONS, world.vic).json()["items"]} == {
        wide,
        narrow_id,
    }
    assert get(app, DELEGATIONS, otto).json()["items"] == []

    # No party and no administrator: as an id that names no delegation. The delegate: 403.
    unknown = post(app, f"{DELEGATIONS}/{uuid4()}/revoke", otto, {"reason": "Not mine to end"})
    stranger = post(app, f"{DELEGATIONS}/{wide}/revoke", otto, {"reason": "Not mine to end"})
    for answer in (unknown, stranger):
        assert (answer.status_code, slug(answer)) == (404, "not-found"), answer.text
    assert {**stranger.json(), "instance": None} == {**unknown.json(), "instance": None}
    by_delegate = post(
        app, f"{DELEGATIONS}/{wide}/revoke", world.vic, {"reason": "No longer needed"}
    )
    assert (by_delegate.status_code, slug(by_delegate)) == (403, "forbidden"), by_delegate.text
    assert by_delegate.json()["detail"] == (
        "Only the delegator or an access administrator can end this delegation."
    )

    # Sven's access covers Nora's and not Rhea's.
    beyond = post(app, f"{DELEGATIONS}/{wide}/revoke", sven, {"reason": "Rhea is on leave"})
    assert (beyond.status_code, slug(beyond)) == (403, "forbidden"), beyond.text
    assert [error["rule_id"] for error in beyond.json()["errors"]] == ["T-PLT-10"]
    assert row_of(tenant_id, wide)["revoked_at"] is None
    within = post(app, f"{DELEGATIONS}/{narrow_id}/revoke", sven, {"reason": "Nora is back"})
    assert within.status_code == 200, within.text
    assert within.json()["revoked_by"]["id"] == str(sven_member.user_id)

    # Tomas administers every entity. Without a fresh step-up he is refused, and it is on record.
    clock.advance(timedelta(minutes=6))
    stale = post(app, f"{DELEGATIONS}/{wide}/revoke", world.tomas, {"reason": "Rhea is on leave"})
    assert (stale.status_code, slug(stale)) == (403, "mfa-step-up-required"), stale.text
    tomas = step_up(app, clock, world.tomas)
    ended = post(app, f"{DELEGATIONS}/{wide}/revoke", tomas, {"reason": "Rhea is on leave"})
    assert ended.status_code == 200, ended.text
    assert ended.json()["revoked_by"]["id"] == str(tomas.member.user_id)
    again = post(app, f"{DELEGATIONS}/{wide}/revoke", tomas, {"reason": "Rhea is on leave"})
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    recorded = [
        (action, outcome, actor, detail.get("reason") or detail.get("rule_id"))
        for action, outcome, actor, detail in events(tenant_id)
        if action.endswith(".revoke")
    ]
    assert recorded == [
        ("approval_delegation.revoke", "DENIED", sven_member.user_id, "T-PLT-10"),
        ("approval_delegation.revoke", "SUCCESS", sven_member.user_id, None),
        ("approval_delegation.revoke", "DENIED", tomas.member.user_id, "mfa-step-up-required"),
        ("approval_delegation.revoke", "SUCCESS", tomas.member.user_id, None),
    ]

    # Who is no member administers nothing (the scope of a grant is read for members only): an
    # API client, the SYSTEM principal and an operator under a support grant.
    fresh = post(
        app,
        DELEGATIONS,
        step_up_now(app, clock, world.rhea),
        body(world.vic.member, start=clock.now(), end=clock.now() + timedelta(days=30)),
    )
    assert fresh.status_code == 201, fresh.text
    target = f"{DELEGATIONS}/{fresh.json()['id']}/revoke"
    files = LocalFileStore(app_settings.file_root)
    no_members = (
        system_principal(tenant_id, on_behalf_of_id=None),
        Principal(
            kind=PrincipalKind.API_CLIENT,
            id=uuid4(),
            tenant_id=tenant_id,
            membership_id=None,
            display_name="svc-access",
            roles=(),
            permissions=frozenset({approval_delegations.ADMINISTER}),
            permission_scopes=MappingProxyType({approval_delegations.ADMINISTER: "*"}),
            entity_scope="*",
            auth_method="client_credentials",
            mfa_verified_at=None,
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
        ),
    )
    for principal in no_members:
        with (
            pytest.raises(Problem) as refused,
            unit_of_work(
                context(principal, clock), clock=clock, keyring=keyring, files=files
            ) as uow,
        ):
            approval_delegations.revoke_delegation(
                uow, UUID(str(fresh.json()["id"])), reason="Ended by an integration"
            )
        assert (refused.value.slug, refused.value.status) == ("forbidden", 403), principal.kind

    services = operator_services(keyring, clock, app_settings.file_root)
    operator = create_operator(services)
    grant = post(
        app,
        GRANTS,
        tomas,
        {
            "operator_email": operator["email"],
            "reason": "Investigate export failure",
            "ticket_ref": "SUP-2291",
            "valid_from": (clock.now() - timedelta(hours=1)).isoformat(),
            "valid_to": (clock.now() + timedelta(hours=7)).isoformat(),
        },
    )
    assert grant.status_code == 201, grant.text
    grace = step_up(app, clock, world.grace)
    assert approve_grant(app, grant.json()["approval_request_id"], grace).status_code == 200
    selected = select_tenant(app, operator_signed_in(app, clock, operator["email"]), tenant_id)
    assert selected.status_code == 200, selected.text
    by_operator = call(
        app,
        "POST",
        target,
        json={"reason": "Ended by support"},
        headers=cookie_headers(cookie_of(selected), selected.json()["csrf_token"]),
    )
    assert (by_operator.status_code, slug(by_operator)) == (403, "forbidden"), by_operator.text
    assert row_of(tenant_id, fresh.json()["id"])["revoked_at"] is None


def step_up_now(app: FastAPI, clock: FrozenClock, someone: Actor) -> Actor:
    """A fresh verification at a TOTP step the member has not used."""
    clock.advance(timedelta(seconds=31))
    return step_up(app, clock, someone)


def test_r_111_4_the_end_is_stamped_by_whoever_runs_the_sweep(
    app: FastAPI, world: World, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    """``approvals.delegations.end_unsupported`` under the SYSTEM principal — a job, the erasure
    of an identity in another workspace: the end carries the SYSTEM kind and no person."""
    tenant_id = world.tenant_id
    now = clock.now()
    gone = colleague(tenant_id, "gwen")  # holds no role: what she "delegated" has no support
    with tenant_session(_all_entities(tenant_id)) as session:
        dormant = insert_approval_delegation(
            session,
            tenant_id=tenant_id,
            delegator_membership_id=gone.membership_id,
            delegate_membership_id=world.vic.member.membership_id,
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=20),
        )
    standing = given(app, world, clock)
    ctx = context(system_principal(tenant_id, on_behalf_of_id=None), clock)
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        ended = delegations.end_unsupported(uow, cause="tests-sweep")
        uow.commit()
    assert ended == [dormant]
    stamped = row_of(tenant_id, dormant)
    assert (stamped["revoked_by"], str(stamped["revoked_by_kind"])) == (None, "SYSTEM")
    assert row_of(tenant_id, standing)["revoked_at"] is None  # supported: left alone


# --- R-111 (9): the findings of the command -------------------------------------------------------


def test_r_111_9_the_findings_of_a_delegation(
    app: FastAPI, world: World, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    """The review's untested branches of rule 2: every finding of the command, collected in one
    answer where they can stand together; a member who is not active or of another workspace;
    a permission held only through a delegation; and an end asked for by an unverified
    principal."""
    tenant_id = world.tenant_id
    now = clock.now()
    rhea = world.rhea

    everything = post(
        app,
        DELEGATIONS,
        rhea,
        {
            "delegate_membership_id": str(rhea.member.membership_id),  # herself
            "permissions": [
                "contract.approve",
                "contract.approve",  # twice
                "contract.read",  # no approval permission
                "access.approve",  # an approval permission she does not hold
            ],
            "valid_from": now.isoformat(),
            "valid_to": (now - timedelta(days=1)).isoformat(),  # ends before it starts
            "reason": "Leave",  # shorter than 10 characters
        },
    )
    assert (everything.status_code, slug(everything)) == (422, "validation-failed"), everything.text
    assert fields(everything) == [
        ("permissions[1]", "T-PLT-21", "Send each permission once."),
        ("permissions[2]", "T-PLT-21", "Choose approval permissions only."),
        ("permissions[3]", "T-PLT-21", "You can delegate only approval permissions you hold."),
        ("delegate_membership_id", "T-PLT-21", "Choose another member as the delegate."),
        ("valid_to", "T-PLT-21", "The end must be after the start."),
        ("reason", "T-PLT-21", "Enter a reason of at least 10 characters."),
    ]

    # A member who is not active, and a membership of another workspace.
    idle_member = colleague(tenant_id, "ida")
    with_factor(app, idle_member)
    suspended = post(
        app,
        f"{USERS}/{idle_member.membership_id}/suspend",
        world.tomas,
        {"reason": "Ida is on extended leave"},
    )
    assert suspended.status_code == 200, suspended.text
    elsewhere = member(keyring, clock)  # the administrator of another workspace
    for delegate in (idle_member, elsewhere):
        refused = post(
            app, DELEGATIONS, rhea, body(delegate, start=now, end=now + timedelta(days=30))
        )
        assert fields(refused) == [
            ("delegate_membership_id", "T-PLT-21", "Choose an active member of this workspace.")
        ], refused.text

    # What Vic holds through Rhea's delegation is not his to delegate.
    given(app, world, clock)
    vic = step_up_now(app, clock, world.vic)
    passed_on = post(
        app,
        DELEGATIONS,
        vic,
        body(world.grace.member, start=clock.now(), end=clock.now() + timedelta(days=30)),
    )
    assert fields(passed_on) == [
        ("permissions[0]", "T-PLT-21", "You can delegate only approval permissions you hold.")
    ], passed_on.text
    assert len(stored(tenant_id)) == 1

    # An end asked for by a principal whose session never passed the second factor.
    [delegation] = stored(tenant_id)
    someone = rhea.member
    principal = Principal(
        kind=PrincipalKind.USER,
        id=someone.user_id,
        tenant_id=tenant_id,
        membership_id=someone.membership_id,
        display_name="Rhea",
        roles=("revenue_reviewer",),
        permissions=frozenset({"contract.approve"}),
        permission_scopes=MappingProxyType({"contract.approve": "*"}),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    files = LocalFileStore(app_settings.file_root)
    with (
        pytest.raises(Problem) as unverified,
        unit_of_work(context(principal, clock), clock=clock, keyring=keyring, files=files) as uow,
    ):
        approval_delegations.revoke_delegation(uow, delegation["id"], reason="Back from leave")
    assert (unverified.value.slug, unverified.value.status) == ("mfa-required", 403)
    assert unverified.value.detail == mfa.VERIFICATION_REQUIRED
    assert row_of(tenant_id, delegation["id"])["revoked_at"] is None
    assert [
        (action, outcome, detail)
        for action, outcome, _, detail in events(tenant_id)
        if outcome == "DENIED"
    ] == [("approval_delegation.revoke", "DENIED", {"reason": "mfa-required", "permission": ""})]


def test_deleg_list_scope_1_an_administrator_of_named_entities_lists_what_they_may_end(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Item DELEG-LIST-SCOPE-1 (the supervisor's ruling on the list clause of the R-111 slice;
    ruling R-28): a holder of ``role.manage`` for named entities is answered the delegations
    they may end — those whose delegator's role assignments name no entity beyond theirs — and
    those they are a party to, nothing else. Ada administers North and Ben South. Each lists
    the delegation of the reviewer of their entity; neither lists the one of a member with a
    role in each entity, nor the one of a reviewer of all entities; and the delegation that
    South's reviewer gave to Ada is listed by both — by Ben, who may end it, and by Ada as its
    delegate, who may not. The administrator of every entity lists them all. What an
    administrator may end follows the delegator's access as it stands: once the role beyond her
    entities is revoked, she lists that delegation and ends it."""
    tenant_id = world.tenant_id
    now = clock.now()
    with tenant_session(_all_entities(tenant_id)) as session:
        north = insert_contract_rows(session, tenant_id).entity_id
        south = insert_contract_rows(session, tenant_id).entity_id
    ada_member = colleague(tenant_id, "ada")
    ben_member = colleague(tenant_id, "ben")
    nora = colleague(tenant_id, "nora")  # reviews for North
    sam = colleague(tenant_id, "sam")  # reviews for South
    drew = colleague(tenant_id, "drew")  # a role in each entity
    assign(ada_member, "tenant_admin", entity_ids=(north,))
    assign(ben_member, "tenant_admin", entity_ids=(south,))
    assign(nora, "revenue_reviewer", entity_ids=(north,))
    assign(sam, "revenue_reviewer", entity_ids=(south,))
    assign(drew, "revenue_reviewer", entity_ids=(north,))
    drew_in_south = assign(drew, "viewer", entity_ids=(south,))
    ada = enrolled(app, clock, ada_member)
    ben = enrolled(app, clock, ben_member)

    def given_by(delegator: Member, to: Member) -> str:
        with tenant_session(_all_entities(tenant_id)) as session:
            return str(
                insert_approval_delegation(
                    session,
                    tenant_id=tenant_id,
                    delegator_membership_id=delegator.membership_id,
                    delegate_membership_id=to.membership_id,
                    valid_from=now,
                    valid_to=now + timedelta(days=30),
                )
            )

    vic = world.vic.member
    of_north = given_by(nora, vic)
    of_south = given_by(sam, vic)
    of_both = given_by(drew, vic)
    of_all = given_by(world.rhea.member, vic)  # Rhea reviews for all entities
    to_ada = given_by(sam, ada_member)

    def listed(actor: Actor) -> set[str]:
        answer = get(app, DELEGATIONS, actor, limit="200")
        assert answer.status_code == 200, answer.text
        return {str(item["id"]) for item in answer.json()["items"]}

    assert {name: listed(actor) for name, actor in (("ada", ada), ("ben", ben))} == {
        "ada": {of_north, to_ada},
        "ben": {of_south, to_ada},
    }
    # Positive controls: the administrator of every entity lists them all, the delegate what
    # she received; and what an administrator lists and did not receive, they may end.
    assert listed(world.tomas) == {of_north, of_south, of_both, of_all, to_ada}
    assert listed(world.vic) == {of_north, of_south, of_both, of_all}
    ended = post(app, f"{DELEGATIONS}/{of_north}/revoke", ada, {"reason": "Nora is back"})
    assert ended.status_code == 200, ended.text
    assert listed(ada) == {of_north, to_ada}  # an ended delegation stays in the list
    # The one she received is not hers to end: its delegator's access lies beyond hers.
    as_delegate = post(app, f"{DELEGATIONS}/{to_ada}/revoke", ada, {"reason": "Not needed"})
    assert (as_delegate.status_code, slug(as_delegate)) == (403, "forbidden"), as_delegate.text
    assert [error["rule_id"] for error in as_delegate.json()["errors"]] == ["T-PLT-10"]
    # The list follows the delegator's access as it stands: Drew's role in South is revoked, and
    # his delegation lies within Ada's entities — she lists it and ends it; Ben does not.
    left = post(
        app, f"{ASSIGNMENTS}/{drew_in_south}/revoke", world.tomas, {"reason": "Drew left South"}
    )
    assert left.status_code == 200, left.text
    assert {name: listed(actor) for name, actor in (("ada", ada), ("ben", ben))} == {
        "ada": {of_north, to_ada, of_both},
        "ben": {of_south, to_ada},
    }
    freed = post(app, f"{DELEGATIONS}/{of_both}/revoke", ada, {"reason": "Drew is back"})
    assert freed.status_code == 200, freed.text
