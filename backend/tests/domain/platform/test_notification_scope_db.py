"""Who is told of an event by role (item NOTIFY-ROLE-HOLDERS-SCOPE-1; the supervisor's ruling of
2026-10-01; PRD §5.4 NTF-06, NTF-07, NTF-09, NTF-11, NTF-12; 05 NTR-02; 03 REQ-PLT-012).

A notification addressed by role goes to the holders whose role assignments cover the event: for
an event of one entity — a period's lock and reopen, a data-quality item of its close — an
assignment for all entities or one that names the entity; for an event of the whole workspace —
an operator's request for access, the audit chain's failed verification — an assignment for all
entities alone. ``events.notifications.role_holders`` took no scope.

Measured before the item, in the world of the first test: the Tenant Admin of AVM-DE alone was
told that an operator asked for access; the Controller, the Revenue Reviewer and the Auditor of
AVM-DE alone were told "AVM-US FY2026-P01 locked" and "AVM-US FY2026-P01 reopened" — against PRD
NTF-06 and NTF-07, which name the holders "with the entity in scope"; and the Controller and the
Tenant Admin of AVM-DE alone were told that the chain's verification had failed.

Worlds. The first test: WLD-K-01 through January 2026 (``worlds.k01_pellworth``; AVM-US) and a
second entity, AVM-DE, made through the product; every scoped role is granted through the
product (``POST /role-assignments``, requested by Marcus, approved by Grace). The second:
``support.close_world`` (AVM-US, FY2026-P09) with a second entity as a row.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import exception_item, notification, role
from erev_api.domain.close import monitors
from erev_api.domain.platform import audit_jobs  # noqa: F401 - registers the verification's handler
from erev_api.enums import NotificationKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.close_world import BOOK, close_world, identity_duplicates, other_entity, system_session
from support.db import TestDatabase
from support.operators import create_operator, operator_services
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, entity, get, post
from support.rows import tamper_audit_event
from support.worlds import AVM_US, JANUARY_2026
from tests.domain.reports.test_entity_scoped_runs_db import ASSIGNMENTS, scoped, second_admin

API: Final = "/api/v1"
OTHER: Final = "AVM-DE"
ONE_ROLE: Final = (
    "controller",
    "revenue_reviewer",
    "auditor",
    "revenue_accountant",
    "tenant_admin",
)
# the four kinds the first test raises: each is addressed by role
BY_ROLE: Final = (
    NotificationKind.SUPPORT_GRANT_REQUESTED,
    NotificationKind.PERIOD_LOCKED,
    NotificationKind.PERIOD_REOPENED,
    NotificationKind.CHAIN_VERIFICATION_FAILED,
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def told(world: worlds.ReportWorld, people: dict[str, Actor], kind: NotificationKind) -> set[str]:
    """Those of ``people`` who hold a notification of ``kind``."""
    recipients = {
        UUID(str(row["recipient_membership_id"]))
        for row in world.place.rows(
            select(notification.c.recipient_membership_id).where(notification.c.kind == kind.value)
        )
    }
    return {name for name, actor in people.items() if actor.member.membership_id in recipients}


def titles(world: worlds.ReportWorld, kind: NotificationKind) -> set[str]:
    rows = world.place.rows(select(notification.c.title).where(notification.c.kind == kind.value))
    return {str(row["title"]) for row in rows}


def granted(
    world: worlds.ReportWorld,
    clock: FrozenClock,
    approver: Actor,
    name: str,
    role_code: str,
    *entity_codes: str,
) -> Actor:
    """A member holding ``role_code`` through ONE assignment that names ``entity_codes``."""
    someone = colleague(world.tenant_id, name)
    role_id = world.place.scalar(select(role.c.id).where(role.c.code == role_code))
    asked = post(
        world.app,
        ASSIGNMENTS,
        world.marcus,
        {
            "membership_id": str(someone.membership_id),
            "role_id": str(role_id),
            "is_all_entities": False,
            "entity_codes": list(entity_codes),
        },
    )
    assert asked.status_code == 201, asked.text
    approved = approve(world.app, asked.json()["approval_request_id"], approver)
    assert approved.status_code == 200, approved.text
    return enrolled(world.app, clock, someone)


@pytest.mark.slow
def test_an_event_is_told_to_the_holders_whose_role_covers_it(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    app_settings: Settings,
    committed_db: TestDatabase,
) -> None:
    """Four events, two of the workspace and two of AVM-US. An operator's request for access is
    told to the Tenant Admins of all entities, the requester apart; the lock and the reopen of
    AVM-US January to the Controllers, Revenue Reviewers and Auditors whose role covers AVM-US —
    a Controller of AVM-US alone and an Auditor of AVM-US and AVM-DE among them; the chain's
    failed verification to the Tenant Admins and Controllers of all entities. The five members
    who hold one role each for AVM-DE alone are told of none of the four, and a Controller of
    AVM-US alone is not told of the workspace's. Before: every holder of a role was told,
    whatever entities the role named."""
    world = worlds.k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 1))
    assign(world.priya.member, "revenue_reviewer")  # PRD 2.5: the journal run is hers to approve
    world = worlds.on_record_clock(world, clock)
    calendars = get(app, f"{API}/calendars", world.maya, {"limit": "50"}).json()["items"]
    entity(
        app,
        world.maya,
        code=OTHER,
        calendar_id=str(calendars[0]["id"]),
        functional_currency="USD",
        time_zone="America/New_York",
    )
    grace = second_admin(world, clock)
    people: dict[str, Actor] = {
        f"{code} of {OTHER}": scoped(world, clock, grace, f"de{index}", (code, OTHER))
        for index, code in enumerate(ONE_ROLE)
    }
    people[f"controller of {AVM_US}"] = scoped(world, clock, grace, "us0", ("controller", AVM_US))
    people["auditor of both"] = granted(world, clock, grace, "both", "auditor", AVM_US, OTHER)
    people |= {"maya": world.maya, "priya": world.priya, "marcus": world.marcus, "grace": grace}
    for kind in BY_ROLE:
        assert told(world, people, kind) == set(), kind  # the grants themselves told nobody

    # 1. the workspace's: an operator asks for access (Grace records the request)
    operator = create_operator(operator_services(keyring, clock, app_settings.file_root))
    now = clock.now()
    asked = post(
        app,
        f"{API}/support-grants",
        grace,
        {
            "operator_email": operator["email"],
            "reason": "Investigate the export failure of ticket SUP-2291",
            "ticket_ref": "SUP-2291",
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert asked.status_code == 201, asked.text
    assert told(world, people, NotificationKind.SUPPORT_GRANT_REQUESTED) == {"marcus"}

    # 2. AVM-US's: January is closed and locked through the product
    covers_us = {"priya", "marcus", f"controller of {AVM_US}", "auditor of both"}
    _, world = worlds.period_locked(world, clock, entity_code=AVM_US, period_key=JANUARY_2026)
    assert titles(world, NotificationKind.PERIOD_LOCKED) == {f"{AVM_US} {JANUARY_2026} locked"}
    assert told(world, people, NotificationKind.PERIOD_LOCKED) == covers_us

    # 3. AVM-US's: January is reopened
    world = worlds.period_reopened(
        world,
        clock,
        entity_code=AVM_US,
        period_key=JANUARY_2026,
        comment="An error correction of January",
    )
    assert titles(world, NotificationKind.PERIOD_REOPENED) == {f"{AVM_US} {JANUARY_2026} reopened"}
    assert told(world, people, NotificationKind.PERIOD_REOPENED) == covers_us

    # 4. the workspace's: the chain's verification fails (one tampered event; DG-TST-22)
    tamper_audit_event(committed_db.owner_engine, tenant_id=world.tenant_id, chain_seq=2)
    requested = post(app, f"{API}/audit-events/verify", world.maya, {})
    assert requested.status_code == 202, requested.text
    finished = worlds.run_now(world, UUID(str(requested.json()["id"])))
    assert finished["result"]["counts"]["failures"] == 1, finished
    assert told(world, people, NotificationKind.CHAIN_VERIFICATION_FAILED) == {"marcus", "grace"}

    # the events of AVM-US and of the workspace told the members of AVM-DE alone nothing at all
    for kind in BY_ROLE:
        assert not {name for name in told(world, people, kind) if name.endswith(f"of {OTHER}")}


def test_a_monitors_item_is_told_to_the_revenue_accountants_of_its_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD NTF-11 for an item a data-quality monitor creates in the close of AVM-US September: no
    owner is set at creation, so the Revenue Accountants are told — Maya, of all entities, and a
    Revenue Accountant of AVM-US alone; a Revenue Accountant of AVM-UK alone is not. Before: all
    three."""
    world = close_world(app, keyring, clock, files)
    with system_session(world) as session:
        other_id = other_entity(session, world)
        identity_duplicates(session, world, issue_date=date(2026, 9, 3))
    here = colleague(world.tenant_id, "here")
    assign(here, "revenue_accountant", entity_ids=[world.entity_id])
    elsewhere = colleague(world.tenant_id, "elsewhere")
    assign(elsewhere, "revenue_accountant", entity_ids=[other_id])

    with world.place.uow() as uow:
        run = monitors.run_monitors(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    assert run.created == 1

    with system_session(world) as session:
        (item_id,) = session.execute(
            select(exception_item.c.id).where(exception_item.c.code == "DQ_DUPLICATE_INVOICE")
        ).scalars()
        recipients = set(
            session.execute(
                select(notification.c.recipient_membership_id).where(
                    notification.c.kind == NotificationKind.EXCEPTION_ASSIGNED.value,
                    notification.c.subject_id == item_id,
                )
            ).scalars()
        )
    assert recipients == {world.maya.member.membership_id, here.membership_id}
    assert elsewhere.membership_id not in recipients
