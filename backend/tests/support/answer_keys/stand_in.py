"""A platform key's plan against the product over a fixture tenant (DB-bound witnesses of the
answer-key runner; record §31, rule ACT-1).

The witnesses that run a whole key through ``run_platform`` — the close run of a plan
(``tests/domain/answer_keys/test_platform_close_run_db.py``), the journal runs of its journals
blocks (``test_platform_journal_plan_db.py``) — do not run the runner's own phases: the fixture
tenant and the stand-in members take the place of the provisioning and of the personas
(``support.answer_keys.db_personas``). Everything else — the world, the contracts, the timeline,
the close run, the journal runs, the checkpoint reads — goes through the real adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client
from erev_api.files.store import LocalFileStore
from fastapi import FastAPI
from sqlalchemy import insert
from support.answer_keys.db_personas import PERSONA_ROLES, principal_map
from support.answer_keys.loader import LoadedKey
from support.answer_keys.platform_plan import (
    APPROVER,
    INTEGRATION,
    INTEGRATION_SCOPES,
    PREPARER,
    SSP_ANALYST,
    SSP_APPROVER,
    Step,
    plan,
)
from support.answer_keys.platform_runner import DbPlatform
from support.answer_keys.workspace_adapter import WorkspaceAdapter
from support.factories import Workspace, stamp_test_release, workspace
from support.principals import colleague, enrolled, member
from support.reference import assign
from support.rows import api_client_values

__all__ = ["STAND_IN_PHASES", "StandInPlatform", "stand_in_world"]

# The runner's own phases are not run: the fixture tenant and the stand-in members take the place
# of the provisioning and of the personas.
STAND_IN_PHASES: Final = frozenset({"RUNNER", "PROVISION", "PERSONAS"})


class StandInPlatform(DbPlatform):
    """The database platform over a fixture tenant: the runner's own phases run nothing."""

    def execute(self, step: Step) -> datetime | None:
        if step.phase in STAND_IN_PHASES:
            return None
        return super().execute(step)


def stand_in_world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    settings: Settings,
    loaded: LoadedKey,
) -> tuple[WorkspaceAdapter, Workspace]:
    """The fixture tenant with the stand-in personas the plan's steps name (ACT-1, ACT-2), at
    the plan's setup clock, and the world's API client as a row (BUILD_SPEC CTR-6)."""
    provision = next(step for step in plan(loaded).steps if step.phase == "PROVISION")
    assert provision.clock_at is not None
    clock.set(datetime.strptime(provision.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC))
    stamp_test_release()
    maya = member(keyring, clock)
    for code in PERSONA_ROLES[PREPARER]:
        assign(maya, code)
    stand_ins = {}
    for persona, name in ((APPROVER, "marcus"), (SSP_ANALYST, "sasha"), (SSP_APPROVER, "priya")):
        someone = colleague(maya.tenant_id, name)
        for code in PERSONA_ROLES[persona]:
            assign(someone, code)
        stand_ins[persona] = someone
    marcus = stand_ins[APPROVER]
    author = enrolled(app, clock, marcus)
    place = workspace(app, clock, keyring, LocalFileStore(settings.file_root), author)
    client = api_client_values(maya.tenant_id, name=INTEGRATION, scopes=list(INTEGRATION_SCOPES))
    with tenant_session(
        DbContext(tenant_id=maya.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        session.execute(insert(api_client).values(**client))
    principals = principal_map(
        maya,
        marcus,
        ssp_analyst=stand_ins[SSP_ANALYST],
        ssp_approver=stand_ins[SSP_APPROVER],
        integration=UUID(str(client["id"])),
        verified_at=clock.now(),
    )
    return WorkspaceAdapter.for_database(loaded, place, principals), place
