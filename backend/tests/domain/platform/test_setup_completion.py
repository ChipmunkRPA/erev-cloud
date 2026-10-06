"""Setup completion (PRD BR-PLT-02; 04 T-PLT-01 ``setup_completed_at``, §14.3 rules 1 to 3;
BUILD_SPEC RFD-19).

Lena holds Tenant Admin in a fresh tenant: ``settings.manage`` creates entities and, while setup is
incomplete, opens periods (API-R-18), and rule ``AUTO-BOOTSTRAP`` approves the role assignments she
requests. Maya receives Revenue Accountant (``contract.create``) and Priya Revenue Reviewer
(``contract.approve``) (docs/02-PRD.md §5.6).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import routing
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, outbox_message, tenant
from erev_api.domain.platform import setup
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.http import call
from support.links import emailed_token
from support.principals import PASSWORD, Actor, Member, colleague, enrolled, member
from support.reference import PERIODS, assign, calendar, entity, get, periods, post, slug

ROLES = "/api/v1/roles"
ROLE_ASSIGNMENTS = "/api/v1/role-assignments"
USERS = "/api/v1/users"
ACCEPT = "/api/v1/session/accept-invitation"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _completed_at(tenant_id: UUID) -> datetime | None:
    with tenant_session(_context(tenant_id)) as session:
        value: datetime | None = session.execute(
            select(tenant.c.setup_completed_at).where(tenant.c.id == tenant_id)
        ).scalar_one()
    return value


def _completion_events(tenant_id: UUID) -> list[tuple[UUID | None, Any, Any]]:
    with tenant_session(_context(tenant_id)) as session:
        rows = session.execute(
            select(audit_event.c.object_id, audit_event.c.before, audit_event.c.after).where(
                audit_event.c.action == setup.COMPLETED_ACTION
            )
        ).all()
    return [(row.object_id, row.before, row.after) for row in rows]


def _grant(app: FastAPI, admin: Actor, someone: Member, role_code: str) -> dict[str, Any]:
    """``POST /role-assignments`` for all entities; returns API-S-RoleAssignment."""
    listed = get(app, ROLES, admin, {"limit": 200})
    assert listed.status_code == 200, listed.text
    role_id = next(item["id"] for item in listed.json()["items"] if item["code"] == role_code)
    body = {
        "membership_id": str(someone.membership_id),
        "role_id": role_id,
        "is_all_entities": True,
    }
    granted = post(app, ROLE_ASSIGNMENTS, admin, body)
    assert granted.status_code == 201, granted.text
    result: dict[str, Any] = granted.json()
    return result


def _open_first_period(app: FastAPI, admin: Actor, entity_code: str) -> None:
    first = periods(app, admin, entity=entity_code)[0]
    opened = post(app, f"{PERIODS}/{first['id']}/open", admin, {}, if_match='"r1"')
    assert opened.status_code == 200, opened.text


def _admin(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> Actor:
    """Lena, the bootstrap Tenant Admin of a fresh workspace, signed in with a second factor."""
    lena = member(keyring, clock)
    assign(lena, "tenant_admin")
    return enrolled(app, clock, lena)


def _invite(
    app: FastAPI, admin: Actor, name: str, role_code: str, *entity_codes: str
) -> dict[str, Any]:
    """``POST /users``: an invitation with one role, for all entities or for ``entity_codes``;
    returns API-S-User. The role is granted by rule ``AUTO-BOOTSTRAP`` while setup is incomplete,
    and the membership is INVITED until the person accepts."""
    listed = get(app, ROLES, admin, {"limit": 200})
    assert listed.status_code == 200, listed.text
    role_id = next(item["id"] for item in listed.json()["items"] if item["code"] == role_code)
    body = {
        "email": f"{name}-{secrets.token_hex(4)}@acme.test",
        "display_name": name.title(),
        "roles": [
            {
                "role_id": role_id,
                "is_all_entities": not entity_codes,
                "entity_codes": list(entity_codes),
            }
        ],
    }
    invited = post(app, USERS, admin, body)
    assert invited.status_code == 201, invited.text
    result: dict[str, Any] = invited.json()
    assert result["status"] == "INVITED"
    assert [(item["status"], item["setup_grant"]) for item in result["roles"]] == [("ACTIVE", True)]
    return result


def _accept(app: FastAPI, tenant_id: UUID, membership_id: str) -> None:
    """The invited person accepts through the product: the token the invitation email carries,
    then ``POST /session/accept-invitation``."""
    with tenant_session(_context(tenant_id)) as session:
        payload = session.execute(
            select(outbox_message.c.payload).where(
                outbox_message.c.aggregate_id == UUID(membership_id)
            )
        ).scalar_one()
    token = emailed_token(payload, prefix="/accept-invitation#token=")
    accepted = call(app, "POST", ACCEPT, json={"token": token, "password": PASSWORD})
    assert accepted.status_code == 200, accepted.text


def _completed_by(tenant_id: UUID) -> list[UUID | None]:
    """The actor of each ``tenant.setup_completed`` event."""
    with tenant_session(_context(tenant_id)) as session:
        return list(
            session.execute(
                select(audit_event.c.actor_id).where(audit_event.c.action == setup.COMPLETED_ACTION)
            ).scalars()
        )


def test_setup_completes_with_open_period_and_two_people(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    tenant_id = lena_member.tenant_id
    calendar_id = calendar(app, lena)

    entity(app, lena, code="AVM-US", calendar_id=calendar_id)
    assert _completed_at(tenant_id) is None
    _open_first_period(app, lena, "AVM-US")
    assert _completed_at(tenant_id) is None, "an open period without two people is not setup"

    maya = colleague(tenant_id, "maya")
    priya = colleague(tenant_id, "priya")
    preparer = _grant(app, lena, maya, "revenue_accountant")
    assert (preparer["status"], preparer["setup_grant"]) == ("ACTIVE", True)
    assert _completed_at(tenant_id) is None, "contract.create alone is not setup"

    approver = _grant(app, lena, priya, "revenue_reviewer")
    assert (approver["status"], approver["setup_grant"]) == ("ACTIVE", True)
    completed = _completed_at(tenant_id)
    assert completed == clock.now()
    stamp = clock.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # 04 §1.7 audit timestamp members
    assert _completion_events(tenant_id) == [
        (tenant_id, {"setup_completed_at": None}, {"setup_completed_at": stamp})
    ]

    # Set once: later commands that meet the conditions again change nothing (T-PLT-01).
    clock.advance(timedelta(seconds=60))
    entity(app, lena, code="AVM-UK", calendar_id=calendar_id)
    colleague_omar = colleague(tenant_id, "omar")
    later = _grant(app, lena, colleague_omar, "viewer")
    assert _completed_at(tenant_id) == completed
    assert len(_completion_events(tenant_id)) == 1

    # 04 §14.3 rule 3: AUTO-BOOTSTRAP stops matching, so the grant waits for approval.
    assert (later["status"], later["setup_grant"]) == ("REQUESTED", False)
    with tenant_session(_context(tenant_id)) as session:
        assert routing.setup_completed(session, tenant_id) is True


def test_setup_completes_when_the_period_opens_last(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    tenant_id = lena_member.tenant_id

    _grant(app, lena, colleague(tenant_id, "maya"), "revenue_accountant")
    _grant(app, lena, colleague(tenant_id, "priya"), "controller")
    assert _completed_at(tenant_id) is None, "two people without an entity is not setup"

    calendar_id = calendar(app, lena)
    entity(app, lena, code="AVM-DE", calendar_id=calendar_id, functional_currency="EUR")
    assert _completed_at(tenant_id) is None, "an entity without an open period is not setup"

    _open_first_period(app, lena, "AVM-DE")
    assert _completed_at(tenant_id) == clock.now()
    assert len(_completion_events(tenant_id)) == 1


def test_setup_open_period_binding_pages_one_row(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """SCREENS_B §11.1 item 2 reads ``GET /periods?state=open&limit=1``; a full page carries the
    keyset cursor of the ``period_end_date`` sort (API-C-09)."""
    lena_member = member(keyring, clock)
    assign(lena_member, "tenant_admin")
    lena = enrolled(app, clock, lena_member)
    calendar_id = calendar(app, lena)
    entity(app, lena, code="AVM-US", calendar_id=calendar_id)
    january, february = periods(app, lena, entity="AVM-US")[:2]
    for state in (january, february):
        opened = post(app, f"{PERIODS}/{state['id']}/open", lena, {}, if_match='"r1"')
        assert opened.status_code == 200, opened.text

    first = get(app, PERIODS, lena, {"state": "open", "limit": 1})
    assert first.status_code == 200, first.text
    body = first.json()
    assert [item["period"]["period_key"] for item in body["items"]] == ["FY2026-P01"]
    assert body["next_cursor"] is not None
    rest = get(app, PERIODS, lena, {"state": "open", "limit": 1, "cursor": body["next_cursor"]})
    assert rest.status_code == 200, rest.text
    assert [item["period"]["period_key"] for item in rest.json()["items"]] == ["FY2026-P02"]


def test_setup_completes_when_the_second_person_accepts_the_invitation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2 (the supervisor's ruling of 2026-10-01 on the independent review of
    the setup rule; 04 T-PLT-01 rev 1.224; PRD BR-PLT-02 "Completion ends the rule"): setup
    completes with the command that makes its conditions true, and the acceptance of an
    invitation is one.

    A period is open and Maya prepares contracts. Lena invites Priya as Revenue Reviewer — a
    setup grant to a membership that is INVITED, so the two people are not there yet. Priya
    accepts: now they are, and her acceptance stamps the completion. Lena's next grant waits for
    a person.

    Fail-first: nothing evaluated setup when a membership became ACTIVE. The workspace stayed in
    setup after Priya's acceptance, rule AUTO-BOOTSTRAP approved Lena's next grant, and the
    completion was stamped after it."""
    lena = _admin(app, keyring, clock)
    tenant_id = lena.member.tenant_id
    entity(app, lena, code="AVM-US", calendar_id=calendar(app, lena))
    _open_first_period(app, lena, "AVM-US")
    preparer = _grant(app, lena, colleague(tenant_id, "maya"), "revenue_accountant")
    assert (preparer["status"], preparer["setup_grant"]) == ("ACTIVE", True)
    priya = _invite(app, lena, "priya", "revenue_reviewer")
    assert _completed_at(tenant_id) is None, "an invited reviewer is not the second person yet"

    clock.advance(timedelta(seconds=60))
    accepted_at = clock.now()
    _accept(app, tenant_id, priya["id"])
    assert _completed_at(tenant_id) == accepted_at
    assert _completed_by(tenant_id) == [UUID(priya["user_id"])]

    # Positive control of the rule's end: the grant that follows is no setup grant.
    clock.advance(timedelta(seconds=60))
    later = _grant(app, lena, colleague(tenant_id, "omar"), "viewer")
    assert (later["status"], later["setup_grant"]) == ("REQUESTED", False)
    assert _completed_at(tenant_id) == accepted_at
    assert len(_completion_events(tenant_id)) == 1


def test_setup_completes_when_the_second_person_is_reactivated(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2: a reactivation makes a membership ACTIVE too.

    Maya, the only preparer, is suspended when Priya receives the approving role, so the two
    people are not there. Lena reactivates Maya: that command stamps the completion.

    Fail-first: the reactivation evaluated nothing, setup stayed incomplete and the next grant
    was a setup grant."""
    lena = _admin(app, keyring, clock)
    tenant_id = lena.member.tenant_id
    entity(app, lena, code="AVM-US", calendar_id=calendar(app, lena))
    _open_first_period(app, lena, "AVM-US")
    maya = colleague(tenant_id, "maya")
    _grant(app, lena, maya, "revenue_accountant")
    suspended = post(
        app, f"{USERS}/{maya.membership_id}/suspend", lena, {"reason": "On leave until October"}
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    approver = _grant(app, lena, colleague(tenant_id, "priya"), "revenue_reviewer")
    assert (approver["status"], approver["setup_grant"]) == ("ACTIVE", True)
    assert _completed_at(tenant_id) is None, "a suspended preparer is not one of the two people"

    clock.advance(timedelta(seconds=60))
    reactivated = post(app, f"{USERS}/{maya.membership_id}/reactivate", lena, {})
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "ACTIVE"
    assert _completed_at(tenant_id) == clock.now()
    assert _completed_by(tenant_id) == [lena.member.user_id]

    later = _grant(app, lena, colleague(tenant_id, "omar"), "viewer")
    assert (later["status"], later["setup_grant"]) == ("REQUESTED", False)
    assert len(_completion_events(tenant_id)) == 1


def test_a_role_request_reads_the_conditions_before_it_is_routed(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2: the rule ends when the conditions hold, whatever made them true.

    The conditions can hold in a workspace whose stamp is not set: two commands that each make
    one of them true and commit beside each other evaluate on what each of them sees, and rows
    can be written by no command of the list. Here Priya's approving role is written as a seed
    would write it. Lena's next role request reads the conditions before it is routed: it waits
    for a person, and the command sets the stamp.

    Fail-first: the request was routed on the stamp alone and setup was evaluated after it, so
    rule AUTO-BOOTSTRAP approved one more grant in a workspace that met BR-PLT-02."""
    lena = _admin(app, keyring, clock)
    tenant_id = lena.member.tenant_id
    entity(app, lena, code="AVM-US", calendar_id=calendar(app, lena))
    _open_first_period(app, lena, "AVM-US")
    _grant(app, lena, colleague(tenant_id, "maya"), "revenue_accountant")
    assign(colleague(tenant_id, "priya"), "revenue_reviewer")
    assert _completed_at(tenant_id) is None, "no command has evaluated setup since"

    clock.advance(timedelta(seconds=60))
    later = _grant(app, lena, colleague(tenant_id, "omar"), "viewer")
    assert (later["status"], later["setup_grant"]) == ("REQUESTED", False)
    assert _completed_at(tenant_id) == clock.now()
    assert _completed_by(tenant_id) == [lena.member.user_id]


def test_setup_completes_whoever_evaluates_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2; supervisor ruling R-42 (d) (a control's result does not depend on
    who asks): BR-PLT-02's open period is the TENANT's.

    The only open period is AVM-DE's. Priya is invited as Revenue Reviewer for AVM-US alone, so
    the session of her acceptance reads no row of AVM-DE. The two people are there with her
    acceptance, and it stamps the completion all the same.

    Fail-first: the open period was read under the scope of whoever's command evaluated setup,
    so Priya's acceptance found none and the workspace stayed in setup."""
    lena = _admin(app, keyring, clock)
    tenant_id = lena.member.tenant_id
    calendar_id = calendar(app, lena)
    entity(app, lena, code="AVM-DE", calendar_id=calendar_id, functional_currency="EUR")
    entity(app, lena, code="AVM-US", calendar_id=calendar_id)
    _open_first_period(app, lena, "AVM-DE")
    _grant(app, lena, colleague(tenant_id, "maya"), "revenue_accountant")
    priya = _invite(app, lena, "priya", "revenue_reviewer", "AVM-US")
    assert [
        (item["is_all_entities"], [ref["code"] for ref in item["entities"]])
        for item in priya["roles"]
    ] == [(False, ["AVM-US"])]
    assert _completed_at(tenant_id) is None

    clock.advance(timedelta(seconds=60))
    _accept(app, tenant_id, priya["id"])
    assert _completed_at(tenant_id) == clock.now()
    assert _completed_by(tenant_id) == [UUID(priya["user_id"])]


def test_a_period_is_not_opened_on_settings_manage_once_the_conditions_hold(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Item APR-SETUP-RULE-2, the supervisor's word of 2026-10-01 on its report (04 API-R-18,
    T-PLT-01): ``POST /periods/{id}/open`` takes ``settings.manage`` only while setup is
    incomplete, and asks the conditions where it asked the stamp.

    Lena, a Tenant Admin without ``period.close``, opens the first period: setup is incomplete.
    Then the two people of BR-PLT-02 are there and the stamp is not set — their roles written as
    a seed would write them, the state two commands leave that each make one condition true and
    commit beside each other. Lena's next period is refused. Marcus, a Controller, opens it, and
    his command sets the stamp.

    Fail-first: the command read the stamp alone, and Lena opened one more period on
    ``settings.manage`` in a workspace that met BR-PLT-02."""
    lena = _admin(app, keyring, clock)
    tenant_id = lena.member.tenant_id
    entity(app, lena, code="AVM-US", calendar_id=calendar(app, lena))
    january, february = periods(app, lena, entity="AVM-US")[:2]
    opened = post(app, f"{PERIODS}/{january['id']}/open", lena, {}, if_match='"r1"')
    assert opened.status_code == 200, opened.text
    assign(colleague(tenant_id, "maya"), "revenue_accountant")
    assign(colleague(tenant_id, "priya"), "revenue_reviewer")
    assert _completed_at(tenant_id) is None, "no command has evaluated setup since"

    refused = post(app, f"{PERIODS}/{february['id']}/open", lena, {}, if_match='"r1"')
    assert refused.status_code == 403, refused.text
    assert slug(refused) == "forbidden"
    assert [item["id"] for item in periods(app, lena, entity="AVM-US", state="open")] == [
        january["id"]
    ]

    # Positive control: a holder of period.close opens it, and that command sets the stamp.
    marcus_member = colleague(tenant_id, "marcus")
    assign(marcus_member, "controller")
    marcus = enrolled(app, clock, marcus_member)
    clock.advance(timedelta(seconds=60))
    later = post(app, f"{PERIODS}/{february['id']}/open", marcus, {}, if_match='"r1"')
    assert later.status_code == 200, later.text
    assert _completed_at(tenant_id) == clock.now()
    assert _completed_by(tenant_id) == [marcus.member.user_id]


def test_two_people_means_two_different_memberships() -> None:
    maya, priya = uuid4(), uuid4()
    assert setup.held_by_two_people(frozenset({maya}), frozenset({priya})) is True
    assert setup.held_by_two_people(frozenset({maya}), frozenset({maya})) is False
    assert setup.held_by_two_people(frozenset({maya, priya}), frozenset({maya})) is True
    assert setup.held_by_two_people(frozenset(), frozenset({priya})) is False
