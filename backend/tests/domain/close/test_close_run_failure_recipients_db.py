"""Who is told of a failed close run among the holders of the Controllers' permission and their
delegates (item NOTIFY-DELEGATE-SCOPE-1; the supervisor's ruling of 2026-10-02 on findings N-1 and
N-2 of lane F-RPS-REG; PRD §5.4 NTF-05, §2.5 delegations; 05 NTR-02; 04 T-PLT-21; supervisor
ruling R-41 (1); BUILD_SPEC CLO-19).

``events.notifications.permission_holders`` answers the holders of a permission for an entity and
adds the delegates of those holders. A delegation conveys the permission, not the view: the
approvals' reader (``permission_holders_covering``) tells a delegate only of what the delegate's
own entity scope covers. This reader told every delegate, whatever the delegate read — a delegate
without the run's entity read "Job failed: Close run" of a close it cannot open — and, asked
without an entity, it answered every holder, whatever entities the role named; no caller asks
that today, and the shape is closed with the rule of ``role_holders``: a subject of the whole
workspace is covered by an assignment for all entities alone.

World: ``support.factories.seat_world`` (AVM-US; Maya, Priya, Marcus) with a second entity AVM-DE
on the same calendar. Marcus is Controller of all entities and holds ``period.lock``; Cora is
Controller of AVM-DE alone. Marcus delegates ``period.lock`` to three members who hold Viewer:
Del for AVM-US alone, Dag for AVM-DE alone, Dan for all entities.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_delegation, legal_entity, notification
from erev_api.events import notifications
from erev_api.jobs.context import JobRuntime
from fastapi import FastAPI
from sqlalchemy import insert, select
from support import close_runs as runs
from support.factories import SeatWorld
from support.principals import Member, colleague
from support.reference import assign, entity
from support.rows import approval_delegation_values
from tests.domain.close.test_close_runs import (  # noqa: F401 - fixtures
    _billed,
    _breaking,
    _contract,
    _started,
    app,
    files,
    runtime,
    world,
)

PERMISSION: Final = "period.lock"  # ``close_runs.CONTROLLER_PERMISSION`` (PRD NTF-05)
OTHER: Final = "AVM-DE"


@dataclass(frozen=True, slots=True)
class Cast:
    us_id: UUID
    de_id: UUID
    names: dict[UUID, str]  # membership id → the name the assertions use

    def named(self, membership_ids: Iterable[Any]) -> set[str]:
        return {self.names.get(UUID(str(value)), str(value)) for value in membership_ids}


def cast_of(app: FastAPI, clock: FrozenClock, world: SeatWorld) -> Cast:  # noqa: F811
    """AVM-DE, Cora and the three delegates of Marcus (module docstring). The members are rows:
    nobody but Maya signs in."""
    maya = world.place.author
    calendar_id = str(
        world.place.scalar(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
    )
    created = entity(
        app,
        maya,
        code=OTHER,
        calendar_id=calendar_id,
        functional_currency="USD",
        time_zone="Europe/Berlin",
    )
    de_id = UUID(str(created["id"]))
    tenant_id = world.place.tenant_id

    def member(name: str, role_code: str, *entity_ids: UUID) -> Member:
        someone = colleague(tenant_id, name)
        assign(someone, role_code, entity_ids=list(entity_ids))
        return someone

    cora = member("cora", "controller", de_id)
    delegates = {
        "del": member("del", "viewer", world.entity_id),
        "dag": member("dag", "viewer", de_id),
        "dan": member("dan", "viewer"),
    }
    marcus = world.marcus.member.membership_id
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        for someone in delegates.values():
            values = approval_delegation_values(
                tenant_id,
                delegator_membership_id=marcus,
                delegate_membership_id=someone.membership_id,
                valid_from=clock.now() - timedelta(days=1),
                valid_to=clock.now() + timedelta(days=29),
            )
            values["permissions"] = [PERMISSION]
            session.execute(insert(approval_delegation).values(**values))
    names = {
        maya.member.membership_id: "maya",
        world.priya.member.membership_id: "priya",
        marcus: "marcus",
        cora.membership_id: "cora",
        **{someone.membership_id: name for name, someone in delegates.items()},
    }
    return Cast(us_id=world.entity_id, de_id=de_id, names=names)


def test_a_failed_close_run_is_told_to_the_delegates_whose_own_scope_covers_its_entity(
    app: FastAPI,  # noqa: F811
    clock: FrozenClock,
    world: SeatWorld,  # noqa: F811
    runtime: JobRuntime,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NTF-05 for the close run of AVM-US September: the initiator (by the job kernel), Marcus,
    who holds ``period.lock`` for all entities, and those of Marcus's delegates whose own entity
    scope covers AVM-US — Del, of AVM-US alone, and Dan, of all entities. Dag, whose scope is
    AVM-DE, is not told; nor is Cora, who holds the permission for AVM-DE alone. Before: Dag was
    told "Job failed: Close run" of AVM-US, with a link to a close run of an entity the session
    does not read."""
    cast = cast_of(app, clock, world)
    booked = _contract(world, "SF-ORD-10781")
    _billed(world, booked, "INV-US-7801")
    _breaking(monkeypatch, times=2)
    runs.unattended(monkeypatch)
    _, job_id = _started(world)
    assert str(runs.work(world.place.tenant_id, runtime, job_id)["state"]) == "FAILED"

    sent = world.place.rows(select(notification).where(notification.c.kind == "JOB_FAILED"))
    assert {str(row["title"]) for row in sent} == {"Job failed: Close run"}
    assert cast.named(row["recipient_membership_id"] for row in sent) == {
        "maya",
        "marcus",
        "del",
        "dan",
    }


def test_the_permissions_reader_answers_by_the_scope_of_the_subject(
    app: FastAPI,  # noqa: F811
    clock: FrozenClock,
    world: SeatWorld,  # noqa: F811
) -> None:
    """``permission_holders`` for ``period.lock`` in the same cast. For AVM-US: Marcus, and the
    delegates Del and Dan. For AVM-DE: Marcus and Cora, and the delegates Dag and Dan. For a
    subject of the whole workspace — no entity — the holders for all entities and the delegates
    whose own scope is all entities: Marcus and Dan. Before: every delegate in each of the
    three, and with no entity Cora too, who holds the permission for AVM-DE alone."""
    cast = cast_of(app, clock, world)
    tenant_id = world.place.tenant_id

    def holders(entity_id: UUID | None) -> set[str]:
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            return cast.named(
                notifications.permission_holders(
                    session, permission=PERMISSION, entity_id=entity_id, at=clock.now()
                )
            )

    assert holders(cast.us_id) == {"marcus", "del", "dan"}
    assert holders(cast.de_id) == {"marcus", "cora", "dag", "dan"}
    assert holders(None) == {"marcus", "dan"}
