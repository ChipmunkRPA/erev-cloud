"""Who is told that a journal export failed (item NOTIFY-ROLE-HOLDERS-SCOPE-1; the supervisor's
ruling of 2026-10-01, answer Q2; PRD §5.4 NTF-10 rev 1.175; 05 NTR-02 rev 1.180).

``EXPORT_FAILED`` goes to the run's exporter and to the Controllers whose role covers the
batch's entity. ``events.notifications.role_holders`` took no scope, so a Controller of another
entity alone was told of this entity's failed batch, with the run's number and the ledger's
reason.

World: that of ``test_failed_run_exit`` — February 2023 of Mock Entity 1, an Integration Admin's
NetSuite connection and the app's own NetSuite mock, whose ``PERMANENT_ERROR`` fault refuses the
one chunk. Two more members hold the Controller role as rows of the test world: one for Mock
Entity 1 alone, one for Mock Entity 2 alone.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.clock import FrozenClock
from erev_api.db.tables import notification
from erev_api.enums import NotificationKind
from sqlalchemy import select
from support.principals import colleague
from support.reference import assign
from support.worlds import ENTITY_1, ENTITY_2, JournalWorld
from test_chunking import _rows
from test_failed_run_exit import _failed_run, app, files, world  # noqa: F401 - fixtures


def test_a_failed_export_is_told_to_the_controllers_of_the_batchs_entity(
    world: JournalWorld,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    clock: FrozenClock,
) -> None:
    """The ledger refuses the one batch of Mock Entity 1's February run. Told: Maya, who exported
    it; Marcus, Controller of all entities; and the Controller of Mock Entity 1 alone. The
    Controller of Mock Entity 2 alone is not. Before: he was."""
    tenant_id = world.legacy.tenant_id
    here = colleague(tenant_id, "here")
    assign(here, "controller", entity_ids=[world.entities[ENTITY_1]])
    elsewhere = colleague(tenant_id, "elsewhere")
    assign(elsewhere, "controller", entity_ids=[world.entities[ENTITY_2]])

    _mock, run, (batch,) = _failed_run(world, monkeypatch, clock)

    told = _rows(
        world,
        select(notification.c.recipient_membership_id, notification.c.title).where(
            notification.c.kind == NotificationKind.EXPORT_FAILED.value,
            notification.c.subject_id == UUID(str(batch["id"])),
        ),
    )
    assert {str(row["title"]) for row in told} == {f"Journal export failed: {run['run_no']}"}
    names = {
        world.legacy.maya.member.membership_id: "maya, the exporter",
        world.legacy.marcus.member.membership_id: "marcus, Controller of all entities",
        here.membership_id: "the Controller of Mock Entity 1",
        elsewhere.membership_id: "the Controller of Mock Entity 2",
    }
    recipients = {UUID(str(row["recipient_membership_id"])) for row in told}
    assert {names.get(value, str(value)) for value in recipients} == {
        "maya, the exporter",
        "marcus, Controller of all entities",
        "the Controller of Mock Entity 1",
    }
