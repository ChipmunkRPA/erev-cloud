"""Who is told of a rate changed after a lock is scoped to the finding's entity (item
CLO-RATE-AFTER-RUN-1, second part; the supervisor's word of 2026-10-02 17:32; PRD NTF-11; 04
T-REF-11 "A rate changed after a lock", rev 1.291).

``close.rate_changes.approved`` tells the Revenue Accountants and the Controllers of the closed
period's entity — ``role_holders(..., entity_id=entity_id)``, the ninth call of
``events.notifications.role_holders``, whose scope ``tests/unit/events/test_role_holders_scope.py``
pins by reading the source. This is that call's database witness: a holder of one of the two
roles for ANOTHER entity only is not told, a holder for this entity only is.

DB-bound; the world of ``tests/domain/close/test_rate_changed_after_lock.py``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import exception_item, legal_entity, notification
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support import close_run_worlds, worlds
from support.db import TestDatabase
from support.principals import colleague
from support.reference import assign
from support.rows import legal_entity_values

AUGUST = close_run_worlds.AUGUST
CODE = "FX_RATE_CHANGED_AFTER_LOCK"
CORRECTED = "1.115000"  # the closing rate of August as corrected; it was 1.105000


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _second_entity(world: worlds.ReportWorld) -> UUID:
    """AVM-UK on AVM-US's calendar: an entity of the tenant with no period state."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        ).scalar_one()
        row = legal_entity_values(
            world.tenant_id, calendar_id=calendar_id, code="AVM-UK", time_zone="Europe/London"
        )
        session.execute(insert(legal_entity).values(**row))
    return UUID(str(row["id"]))


def _member_with(world: worlds.ReportWorld, name: str, role: str, entity_id: UUID) -> Any:
    """A member of the tenant who holds ``role`` for ``entity_id`` alone; the membership id."""
    someone = colleague(world.tenant_id, name)
    assign(someone, role, entity_ids=[entity_id])
    return someone.membership_id


def test_a_holder_of_the_roles_for_another_entity_only_is_not_told(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """August is closed for AVM-US on a run that read 1.105000. AVM-UK is a second entity of the
    workspace. Uma is a Controller, and Ugo a Revenue Accountant, of AVM-UK alone; Una is a
    Controller of AVM-US alone. The version that corrects August's closing rate is approved: one
    finding, of AVM-US. Told are Maya and Marcus — who hold the two roles for every entity — and
    Una; Uma and Ugo are not, and neither is Priya, who holds neither role."""
    world, _ = close_run_worlds.august_locked(app, keyring, clock, files, monkeypatch)
    uk = _second_entity(world)
    uma = _member_with(world, "uma", "controller", uk)
    ugo = _member_with(world, "ugo", "revenue_accountant", uk)
    una = _member_with(world, "una", "controller", world.entity_id)

    clock.advance(timedelta(minutes=5))
    world = close_run_worlds.closing_rates(world, clock, {AUGUST: CORRECTED})
    (item,) = close_run_worlds.rows(
        world.tenant_id, select(exception_item).where(exception_item.c.code == CODE)
    )
    assert item["entity_id"] == world.entity_id
    told = {
        row["recipient_membership_id"]
        for row in close_run_worlds.rows(
            world.tenant_id,
            select(notification.c.recipient_membership_id).where(
                notification.c.subject_id == item["id"]
            ),
        )
    }
    assert told == {world.maya.member.membership_id, world.marcus.member.membership_id, una}
    assert not told & {uma, ugo, world.priya.member.membership_id}
