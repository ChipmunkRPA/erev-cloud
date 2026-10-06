"""DB-bound: the ``LedgerResolver`` over a real workspace (record §17). Written for the lane's
``erev_rv_l17_test`` database and recorded **not run — databases not provisioned** (§9.1); it runs
in an admitted database stage only.

The workspace of ``support.worlds.report_world``'s first lines (maya prepares, marcus approves)
stands in for the provisioned tenant: the adapter runs POS-CHK-012's tenant-currency, calendar,
entity and customer steps through the real invoker, and the resolver's ids equal the rows.

Rule ACT-1 (record §22; slices PLAT-ACT-1 / PLAT-ACT-1b, §31–§32): the stand-ins are handed to
``for_database`` as the principal map of ``support.answer_keys.db_personas`` — built from the
members and the T-PLT-09 roles they are assigned here, never defaulted to the workspace's own
principal. The batch ci on main 065e7f65 refused the first step by name ("WORLD tenant
currencies: no principal mapped for actor 'ak-approver'") because no map was passed. Under D-98
candidate 107 (DG-AK-41 rev 1.38) marcus is the approver (controller role) and, holding the
provisioned ``tenant_admin`` grant, stands in for the operator who applies the tenant currencies.
"""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import customer, legal_entity
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.answer_keys.db_personas import (
    LEDGER_RESOLVER_HANDLERS,
    PERSONA_ROLES,
    principal_map,
)
from support.answer_keys.ledger_resolver import LedgerResolver
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, load_platform_key, plan
from support.answer_keys.workspace_adapter import WorkspaceAdapter
from support.db import TestDatabase
from support.factories import workspace
from support.principals import colleague, enrolled, member
from support.reference import assign

POS_012 = PLATFORM_KEY_IDS[0]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_ledger_resolver_ids_equal_rows(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    maya_member = member(keyring, clock)
    for code in PERSONA_ROLES["ak-preparer"]:
        assign(maya_member, code)
    marcus = colleague(maya_member.tenant_id, "marcus")
    for code in PERSONA_ROLES["ak-approver"]:
        assign(marcus, code)
    approver = enrolled(app, clock, marcus)
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), approver)
    loaded = load_platform_key(POS_012)
    # ACT-1: the stand-ins' principals, proven by name; never the workspace's default principal.
    adapter = WorkspaceAdapter.for_database(
        loaded, place, principal_map(maya_member, marcus, verified_at=clock.now())
    )
    for step in plan(loaded).steps:
        if step.handler in LEDGER_RESOLVER_HANDLERS:
            adapter.run(step)
    resolver = LedgerResolver(adapter.ledger)
    entity = loaded.key.world.entities[0]
    row = place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == entity.code))
    assert resolver.entity_id(entity.code) == row
    for item in loaded.key.world.customers:
        row = place.scalar(select(customer.c.id).where(customer.c.code == item.code))
        assert resolver.customer_id(item.code) == row
