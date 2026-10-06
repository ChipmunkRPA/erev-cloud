"""CLO-QUARANTINE-READ-1: ``GET /exceptions?blocking=<period id>`` lists the items the close gates
count, an item states the code of the contract group it names, and ONE attribution says whose
an item is — for the gates, the cockpit's counts, the list's ``entity`` filter and the home
page's figure: the item of an import is of the entities its upload names, the item of a sync
run of the entities its connection serves, and a failed import holds the interface gate the
same way (04 §15.3 API-R-44, §16.14 "Exception items — what blocks a period", T-IMP-05 "An
item that names no entity", §16.8 ``blockers``, §16.13 API-S-DashboardHome, rev 1.206;
supervisor ruling R-121 (i); 05 RCP-20; SCREENS_B §1.1 BLK-02, §1.2; BUILD_SPEC CLO-19).

World: ``support.close_world.close_world`` — Maya and AVM-US with FY2026-P01 to P09 open — and a
second entity, AVM-UK, created and opened through the product. The exception items are rows: each
case of the gates' scope rule ([J] D-88 L7-2-Q-1, ``close.gates``) once for each entity, a contract
group that holds a contract of each entity, and the items the gates do not count. The quarantine a
close run raises for a group of several contracts is witnessed through the product in
``tests/domain/close/test_close_runs.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.engine import OUTSIDE_SCOPE_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    approval_request,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    customer,
    exception_item,
    file_object,
    import_upload,
    integration_connection,
    legal_entity,
    notification,
    sync_run,
)
from erev_api.domain.imports import exceptions as exception_queue
from erev_api.domain.imports.exceptions import OWNER_CANNOT_READ
from erev_api.enums import ApprovalRequestStatus, FilePurpose, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.close_world import CloseWorld, close_world, contract_of, system_session
from support.db import TestDatabase
from support.factories import open_periods
from support.principals import Actor, colleague
from support.reference import assign, entity, fields, get, holding, periods, post, slug
from support.rows import (
    approval_request_values,
    combination_group_member_values,
    combination_group_values,
    contract_event_values,
    contract_values,
    customer_values,
    exception_item_values,
    file_object_values,
    import_upload_values,
    integration_connection_values,
)

PERIODS = "/api/v1/periods"
HOME = "/api/v1/dashboard/home"
EXCEPTIONS = "/api/v1/exceptions"
TOTAL_COUNT = "X-Erev-Total-Count"
AVM_US = "AVM-US"
AVM_UK = "AVM-UK"
AUGUST = "FY2026-P08"
SEPTEMBER = "FY2026-P09"
OPEN = ("OPEN", "IN_PROGRESS")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


@dataclass(frozen=True, slots=True)
class Queue:
    """The two entities' period states and the exception items, by the name of their case."""

    uk: UUID
    states: Mapping[tuple[str, str], str]  # (entity code, period key) -> API-S-Period id
    items: Mapping[str, UUID]
    group_codes: Mapping[str, str]  # item name -> the code of the group it names

    def ids(self, *names: str) -> set[str]:
        return {str(self.items[name]) for name in names}


# What ``blockers.exceptions_open`` counts for September, by entity; "mixed" and the tenant-wide
# items count for both.
US_SEPTEMBER = (
    "us entity",
    "us contract",
    "us group",
    "mixed group",
    "nothing named",
    "unmapped product",
    "us in progress",
    "us september",
    "us import warning",
    "us data quality blocking",
)
UK_SEPTEMBER = (
    "uk entity",
    "uk contract",
    "uk group",
    "mixed group",
    "nothing named",
    "unmapped product",
)


def _queue(world: CloseWorld) -> Queue:
    app, maya, tenant_id = world.app, world.maya, world.tenant_id
    us = world.entity_id
    with system_session(world) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == us)
        ).scalar_one()
    uk = UUID(str(entity(app, maya, code=AVM_UK, calendar_id=str(calendar_id))["id"]))
    # a period opens after its predecessor (DB-07): the nine of AVM-US
    open_periods(
        app, maya, entity_code=AVM_UK, keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    states = {
        (code, str(item["period"]["period_key"])): str(item["id"])
        for code in (AVM_US, AVM_UK)
        for item in periods(app, maya, entity=code)
    }
    august = UUID(
        next(
            str(item["period"]["id"])
            for item in periods(app, maya, entity=AVM_US)
            if item["period"]["period_key"] == AUGUST
        )
    )
    items: dict[str, UUID] = {}
    group_codes: dict[str, str] = {}
    with system_session(world) as session:
        us_contract, us_event, us_group = contract_of(session, world)
        uk_contract, uk_event, uk_group = contract_of(session, world, uk)
        # one group with a contract of each entity: the item of its quarantine names no entity
        mixed_uk, mixed_uk_event, mixed_group = contract_of(session, world, uk)
        buyer = customer_values(tenant_id)
        session.execute(insert(customer).values(**buyer))
        mixed_us = contract_values(
            tenant_id,
            customer_id=buyer["id"],
            contracting_entity_id=us,
            combination_group_id=mixed_group,
            head_stream_version=1,
        )
        session.execute(insert(contract).values(**mixed_us))
        mixed_us_event = contract_event_values(
            tenant_id, contract_id=mixed_us["id"], contracting_entity_id=us, stream_version=1
        )
        session.execute(insert(contract_event).values(**mixed_us_event))
        # T-CON-04: every product path writes a contract's membership with its group, and the
        # reading rule of an item that names a group reads its members there (EXC-IMPORT-SCOPE-1)
        for group_id, contract_id, event_id in (
            (us_group, us_contract, us_event),
            (uk_group, uk_contract, uk_event),
            (mixed_group, mixed_uk, mixed_uk_event),
            (mixed_group, mixed_us["id"], mixed_us_event["id"]),
        ):
            session.execute(
                insert(combination_group_member).values(
                    **combination_group_member_values(
                        tenant_id,
                        combination_group_id=group_id,
                        contract_id=contract_id,
                        join_event_id=event_id,
                    )
                )
            )
        cases: dict[str, dict[str, Any]] = {
            "us entity": {"entity_id": us},  # (a)
            "us contract": {"contract_id": us_contract},  # (b)
            "us group": {"combination_group_id": us_group},  # (b2)
            "uk entity": {"entity_id": uk},
            "uk contract": {"contract_id": uk_contract},
            "uk group": {"combination_group_id": uk_group},
            "mixed group": {"combination_group_id": mixed_group},
            "nothing named": {},  # (c)
            "unmapped product": {"code": "PRODUCT_UNMAPPED"},
            "us in progress": {"entity_id": us, "status": "IN_PROGRESS"},
            "us september": {"entity_id": us, "period_id": world.period_id},
            "us august": {"entity_id": us, "period_id": august},
            "us import warning": {
                "entity_id": us,
                "source": "IMPORT",
                "code": "STALE_SOURCE_VERSION",
                "severity": "WARNING",
            },
            "us data quality blocking": {
                "entity_id": us,
                "period_id": world.period_id,
                "source": "DATA_QUALITY",
                "code": "DQ_DUPLICATE_INVOICE",
            },
            "us data quality warning": {
                "entity_id": us,
                "period_id": world.period_id,
                "source": "DATA_QUALITY",
                "code": "DQ_INACTIVE_CONTRACT",
                "severity": "WARNING",
            },
            "us control totals": {"entity_id": us, "code": "CONTROL_TOTALS_MISMATCH"},
            "us info": {"entity_id": us, "severity": "INFO"},
            "us resolved": {"entity_id": us, "status": "RESOLVED", "resolution": "Corrected."},
            "us waived": {"entity_id": us, "status": "WAIVED", "resolution": "Accepted."},
            "us dismissed": {"entity_id": us, "status": "DISMISSED", "resolution": "Superseded."},
        }
        for name, values in cases.items():
            row = exception_item_values(tenant_id, **values)
            if values.get("status") == "WAIVED":  # ck_exception_item__waiver: its request
                waiver = approval_request_values(
                    tenant_id,
                    status=ApprovalRequestStatus.APPROVED,
                    subject_type="EXCEPTION_WAIVER",
                    subject_id=row["id"],
                    entity_id=us,
                )
                session.execute(insert(approval_request).values(**waiver))
                row["waiver_approval_request_id"] = waiver["id"]
            session.execute(insert(exception_item).values(**row))
            items[name] = UUID(str(row["id"]))
        for name in ("us group", "uk group", "mixed group"):
            group_codes[name] = str(
                session.execute(
                    select(combination_group.c.code).where(
                        combination_group.c.id == cases[name]["combination_group_id"]
                    )
                ).scalar_one()
            )
    return Queue(uk=uk, states=states, items=items, group_codes=group_codes)


def _import_items(world: CloseWorld, queue: Queue) -> dict[str, str]:
    """One upload for each thing an upload can name (T-IMP-02 ``named_entity_ids``) — AVM-US,
    AVM-UK, both, no entity (tenant-level data), and a set that is not resolved — each with one
    open finding that names the upload and no entity, contract or group, as the import pipeline
    raises it. Returns the item ids by the name of their upload."""
    tenant_id, us, uk = world.tenant_id, world.entity_id, queue.uk
    named: dict[str, list[UUID] | None] = {
        "import of us": [us],
        "import of uk": [uk],
        "import of both": [us, uk],
        "tenant-level import": [],
        "unresolved import": None,
    }
    found: dict[str, str] = {}
    with system_session(world) as session:
        for name, entities in named.items():
            stored = file_object_values(tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
            session.execute(insert(file_object).values(**stored))
            upload = import_upload_values(
                tenant_id, file_object_id=stored["id"], status="INVALID", named_entity_ids=entities
            )
            session.execute(insert(import_upload).values(**upload))
            row = exception_item_values(
                tenant_id,
                source="IMPORT",
                code="PROGRESS_OVER_DELIVERY",
                title="Delivery exceeds the contracted quantity",
                import_upload_id=upload["id"],
            )
            session.execute(insert(exception_item).values(**row))
            found[name] = str(row["id"])
    return found


def _sync_items(world: CloseWorld, queue: Queue) -> dict[str, str]:
    """One connection for each set of entities a connection can serve (T-INT-01 ``entity_ids``)
    — AVM-US, AVM-UK, both, and every entity (the empty set) — each with a succeeded sync run
    and one open finding that names the run and no entity, contract or group. Returns the item
    ids by the name of their connection."""
    tenant_id, us, uk = world.tenant_id, world.entity_id, queue.uk
    served: dict[str, list[UUID]] = {
        "connection of us": [us],
        "connection of uk": [uk],
        "connection of both": [us, uk],
        "connection of every entity": [],
    }
    found: dict[str, str] = {}
    with system_session(world) as session:
        for name, entities in served.items():
            connection = integration_connection_values(tenant_id, entity_ids=entities)
            session.execute(insert(integration_connection).values(**connection))
            run_id = new_id()
            session.execute(
                insert(sync_run).values(
                    tenant_id=tenant_id,
                    id=run_id,
                    integration_connection_id=connection["id"],
                    kind="INBOUND_POLL",
                    status="SUCCEEDED",
                    checkpoint_before={},
                    created_by_kind="SYSTEM",
                    updated_by_kind="SYSTEM",
                )
            )
            row = exception_item_values(
                tenant_id,
                source="SYNC",
                code="CUSTOMER_NOT_FOUND",
                title="Customer not found",
                sync_run_id=run_id,
            )
            session.execute(insert(exception_item).values(**row))
            found[name] = str(row["id"])
    return found


def _failed_imports(world: CloseWorld, queue: Queue) -> None:
    """Four uploads that failed their control totals, each with its open
    ``CONTROL_TOTALS_MISMATCH`` item: one names AVM-US, one AVM-UK, one no entity, and one is
    not resolved."""
    tenant_id = world.tenant_id
    named: tuple[list[UUID] | None, ...] = ([world.entity_id], [queue.uk], [], None)
    with system_session(world) as session:
        for entities in named:
            stored = file_object_values(tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
            session.execute(insert(file_object).values(**stored))
            upload = import_upload_values(
                tenant_id, file_object_id=stored["id"], status="FAILED", named_entity_ids=entities
            )
            session.execute(insert(import_upload).values(**upload))
            row = exception_item_values(
                tenant_id,
                source="IMPORT",
                code="CONTROL_TOTALS_MISMATCH",
                title="Control totals do not match",
                import_upload_id=upload["id"],
            )
            session.execute(insert(exception_item).values(**row))


def _blockers(app: FastAPI, actor: Actor, state_id: str) -> dict[str, int]:
    shown = get(app, f"{PERIODS}/{state_id}", actor)
    assert shown.status_code == 200, shown.text
    return dict(shown.json()["blockers"])


def _listed(app: FastAPI, actor: Actor, **params: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Every item of ``GET /exceptions`` under ``params`` and the total the server counted."""
    found = get(app, EXCEPTIONS, actor, {"limit": 200, "count": "true", **params})
    assert found.status_code == 200, found.text
    return list(found.json()["items"]), found.headers.get(TOTAL_COUNT)


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {str(item["id"]) for item in items}


def _open_count(app: FastAPI, actor: Actor, state_id: str) -> int:
    shown = get(app, f"{PERIODS}/{state_id}", actor)
    assert shown.status_code == 200, shown.text
    return int(shown.json()["blockers"]["exceptions_open"])


def test_the_blocking_list_names_the_items_the_gates_count(world: CloseWorld) -> None:
    """04 §16.14 rev 1.206: the list under ``blocking`` is what ``blockers.exceptions_open``
    counts — the same predicate. For September of each entity it names the items of that entity by
    every case of the scope rule: the item names the entity; it names no entity and a contract of
    the entity; it names no entity or contract and a group that holds a contract of the entity — a
    group with a contract of each entity counts for both; it names none of the three. It names the
    items of the period and those that name no period, and leaves out August's item, the resolved,
    waived and dismissed ones, an ``INFO`` item, a ``WARNING`` finding of the monitors and a
    control-totals mismatch. ``entity`` lists the entity's items by the same attribution without
    the gate's conditions (supervisor ruling R-121 (i)): with the open statuses, the ten that
    hold September and the four open items no gate of September counts. Until that ruling it
    compared the item's own column and found five of the ten."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    us_state = queue.states[(AVM_US, SEPTEMBER)]
    uk_state = queue.states[(AVM_UK, SEPTEMBER)]

    us_items, us_total = _listed(app, maya, blocking=us_state)
    assert _ids(us_items) == queue.ids(*US_SEPTEMBER)
    assert us_total == str(len(US_SEPTEMBER)) == str(_open_count(app, maya, us_state))
    uk_items, uk_total = _listed(app, maya, blocking=uk_state)
    assert _ids(uk_items) == queue.ids(*UK_SEPTEMBER)
    assert uk_total == str(len(UK_SEPTEMBER)) == str(_open_count(app, maya, uk_state))

    # August of AVM-US: its own item in place of September's two
    august_items, _ = _listed(app, maya, blocking=queue.states[(AVM_US, AUGUST)])
    assert _ids(august_items) == (
        queue.ids(*US_SEPTEMBER, "us august")
        - queue.ids("us september", "us data quality blocking")
    )

    # the filter combines with every other one
    engine, _ = _listed(app, maya, blocking=us_state, source="ENGINE", severity="BLOCKING")
    assert _ids(engine) == (
        queue.ids(*US_SEPTEMBER) - queue.ids("us import warning", "us data quality blocking")
    )
    unmapped, total = _listed(app, maya, blocking=us_state, code="PRODUCT_UNMAPPED")
    assert (_ids(unmapped), total) == (queue.ids("unmapped product"), "1")
    in_progress, _ = _listed(app, maya, blocking=us_state, status="IN_PROGRESS")
    assert _ids(in_progress) == queue.ids("us in progress")
    none, total = _listed(app, maya, blocking=us_state, status="RESOLVED")
    assert (none, total) == ([], "0")

    # ``entity``: the same attribution, without the gate's severity, code and period conditions
    by_entity, total = _listed(app, maya, entity=AVM_US, status=list(OPEN))
    assert _ids(by_entity) == queue.ids(
        *US_SEPTEMBER,
        "us august",
        "us control totals",
        "us data quality warning",
        "us info",
    )
    assert total == "14"
    assert _ids(us_items) < _ids(by_entity)
    # by id as by code; closed items are the entity's too; an entity nobody knows lists nothing
    by_id, _ = _listed(app, maya, entity=str(world.entity_id), status=list(OPEN))
    assert _ids(by_id) == _ids(by_entity)
    closed, _ = _listed(app, maya, entity=AVM_US, status=["RESOLVED", "WAIVED", "DISMISSED"])
    assert _ids(closed) == queue.ids("us resolved", "us waived", "us dismissed")
    assert _listed(app, maya, entity="AVM-XX") == ([], "0")
    of_uk, _ = _listed(app, maya, entity=AVM_UK, status=list(OPEN))
    assert _ids(of_uk) == queue.ids(*UK_SEPTEMBER)
    both, _ = _listed(app, maya, entity=[AVM_US, AVM_UK], status=list(OPEN))
    assert _ids(both) == _ids(by_entity) | _ids(of_uk)


def test_an_item_states_the_code_of_the_group_it_names(world: CloseWorld) -> None:
    """04 §16.14 rev 1.206: ``combination_group_code`` is the code of the contract group an item
    names and null for an item that names none — in the list and for the single item. The item of a
    group names no contract; the code is what a screen shows in its place."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    items, _ = _listed(app, maya, blocking=queue.states[(AVM_US, SEPTEMBER)])
    by_id = {str(item["id"]): item for item in items}
    for name in ("us group", "mixed group"):
        item = by_id[str(queue.items[name])]
        assert (
            item["combination_group_code"],
            item["contract_id"],
            item["contract_external_id"],
            item["entity_id"],
        ) == (queue.group_codes[name], None, None, None)
        single = get(app, f"{EXCEPTIONS}/{item['id']}", maya)
        assert single.status_code == 200, single.text
        assert single.json()["combination_group_code"] == queue.group_codes[name]
    for name in ("us entity", "us contract", "nothing named"):
        item = by_id[str(queue.items[name])]
        assert (item["combination_group_id"], item["combination_group_code"]) == (None, None)


def test_the_blocking_list_is_the_same_for_a_reader_of_one_entity(world: CloseWorld) -> None:
    """Supervisor ruling R-42 (d) — a control's result must not depend on who reads it: a Revenue
    Accountant whose role names AVM-US alone reads for AVM-US's September the count the
    tenant-wide accountant reads, and the list he reads in his order — less the one item she may
    not read: the quarantine of the group with a contract of each entity names both contracts,
    and is shown to a reader of every member's entity (04 T-IMP-05 "An item that names no entity:
    who reads it", rev 1.218; item EXC-IMPORT-SCOPE-1). She is told that it holds the period and
    is not shown it. AVM-UK's period is no period she can read: its list is empty, as for an id
    nobody knows. A reader of AVM-UK alone reads that period's count and list the same way.
    Until rev 1.218 the item was shown to both: it names no entity."""
    app, maya, tenant_id = world.app, world.maya, world.tenant_id
    queue = _queue(world)
    us_state = queue.states[(AVM_US, SEPTEMBER)]
    uk_state = queue.states[(AVM_UK, SEPTEMBER)]
    rita = holding(
        app, colleague(tenant_id, "rita"), "revenue_accountant", entity_ids=[world.entity_id]
    )
    uma = holding(app, colleague(tenant_id, "uma"), "revenue_accountant", entity_ids=[queue.uk])

    not_shown = queue.ids("mixed group")
    mine, total = _listed(app, rita, blocking=us_state)
    assert _ids(mine) == queue.ids(*US_SEPTEMBER) - not_shown
    assert _open_count(app, rita, us_state) == len(US_SEPTEMBER) == int(str(total)) + 1
    assert [str(item["id"]) for item in mine] == [
        str(item["id"])
        for item in _listed(app, maya, blocking=us_state)[0]
        if str(item["id"]) not in not_shown
    ]

    hidden = get(app, f"{PERIODS}/{uk_state}", rita)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text
    assert _listed(app, rita, blocking=uk_state) == ([], "0")

    theirs, total = _listed(app, uma, blocking=uk_state)
    assert _ids(theirs) == queue.ids(*UK_SEPTEMBER) - not_shown
    assert _open_count(app, uma, uk_state) == len(UK_SEPTEMBER) == int(str(total)) + 1
    assert _listed(app, uma, blocking=us_state) == ([], "0")


def test_the_item_of_an_import_holds_the_entities_its_upload_names(world: CloseWorld) -> None:
    """04 T-IMP-05 "An item that names no entity" (rev 1.206; the supervisor's ruling of 2026-10-01
    on a measurement by lane WEB-QA: two findings of an AVM-US import held AVM-DE's January). The
    finding of an import names its upload and no entity, contract or group. It holds the close of
    the entities the upload names: the import of AVM-US holds AVM-US and not AVM-UK, the import of
    both holds each, and an upload that names no entity — tenant-level data — or is not resolved
    holds every entity, as an item of no import does. The count of the cockpit and the list under
    ``blocking`` read that one rule."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    imports = _import_items(world, queue)
    every = {imports["tenant-level import"], imports["unresolved import"]}
    expected = {
        AVM_US: queue.ids(*US_SEPTEMBER)
        | every
        | {imports["import of us"], imports["import of both"]},
        AVM_UK: queue.ids(*UK_SEPTEMBER)
        | every
        | {imports["import of uk"], imports["import of both"]},
    }
    assert (len(expected[AVM_US]), len(expected[AVM_UK])) == (14, 10)
    for code, items in expected.items():
        state_id = queue.states[(code, SEPTEMBER)]
        listed, total = _listed(app, maya, blocking=state_id)
        assert _ids(listed) == items
        assert total == str(len(items)) == str(_open_count(app, maya, state_id))
        of_imports, _ = _listed(app, maya, blocking=state_id, source="IMPORT", severity="BLOCKING")
        assert _ids(of_imports) == items & set(imports.values())


def test_the_item_of_a_sync_run_holds_the_entities_its_connection_serves(world: CloseWorld) -> None:
    """Supervisor ruling R-121 (i) (04 T-IMP-05 "An item that names no entity", rev 1.206): the
    finding of a sync run names its run and no entity, contract or group. It is of the entities
    the run's connection serves — the run itself holds the interface gate for exactly those
    (``gates.uncleared_sync_runs``): the connection of AVM-US holds AVM-US and not AVM-UK, the
    connection of both holds each, and a connection that serves every entity holds every entity.
    Until this ruling each of the four items held the close of both entities."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    runs = _sync_items(world, queue)
    every = {runs["connection of every entity"], runs["connection of both"]}
    expected = {
        AVM_US: queue.ids(*US_SEPTEMBER) | every | {runs["connection of us"]},
        AVM_UK: queue.ids(*UK_SEPTEMBER) | every | {runs["connection of uk"]},
    }
    assert (len(expected[AVM_US]), len(expected[AVM_UK])) == (13, 9)
    for code, items in expected.items():
        state_id = queue.states[(code, SEPTEMBER)]
        listed, total = _listed(app, maya, blocking=state_id)
        assert _ids(listed) == items
        assert total == str(len(items)) == str(_open_count(app, maya, state_id))
        of_runs, _ = _listed(app, maya, entity=code, source="SYNC")
        assert _ids(of_runs) == items & set(runs.values())


def test_a_failed_import_holds_the_interface_gate_of_the_entities_it_names(
    world: CloseWorld,
) -> None:
    """Supervisor ruling R-121 (i) (04 §16.8 "``blockers.interface_failures`` and the
    ``INTERFACES_COMPLETE`` gate", rev 1.206): an upload that failed its control totals, its
    ``CONTROL_TOTALS_MISMATCH`` item open, holds the interface gate of the entities it names —
    and of every entity while it names none or is not resolved. Of the four failed uploads three
    hold AVM-US and three AVM-UK; until this ruling all four held both."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    before = {
        code: _blockers(app, maya, queue.states[(code, SEPTEMBER)]) for code in (AVM_US, AVM_UK)
    }
    assert {code: counts["interface_failures"] for code, counts in before.items()} == {
        AVM_US: 0,
        AVM_UK: 0,
    }
    _failed_imports(world, queue)
    for code in (AVM_US, AVM_UK):
        counts = _blockers(app, maya, queue.states[(code, SEPTEMBER)])
        assert counts["interface_failures"] == 3
        # the mismatch items count here and nowhere else
        assert counts["exceptions_open"] == before[code]["exceptions_open"]


def test_the_home_figure_is_the_entitys_list_and_covers_the_close_row(world: CloseWorld) -> None:
    """Supervisor ruling R-121 (i) (04 §16.13 API-S-DashboardHome ``open_exceptions``, rev 1.206):
    the home page's figure and its close row state two things by definition — every open item of
    the entity, and the items that hold this period's lock — and agree on whose an item is. For
    each entity the figure equals the list behind its link (``GET /exceptions`` with ``entity``
    and the open statuses), its ``blocking``, ``warning`` and ``info`` are that list by severity,
    and every item of the close row (``close.blockers.exceptions_open``, the list under
    ``blocking`` with ``close.id``) is in it. Until that ruling the figure took the item's own
    column — measured on this world before the change: AVM-US's figure 9 beside a close row of
    18, AVM-UK's 1 beside 14."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    _import_items(world, queue)
    _sync_items(world, queue)
    for code, held in ((AVM_US, 17), (AVM_UK, 13)):
        shown = get(app, HOME, maya, {"entity": code, "period": SEPTEMBER})
        assert shown.status_code == 200, shown.text
        figure = shown.json()["open_exceptions"]
        behind, total = _listed(app, maya, entity=code, status=list(OPEN))
        assert str(figure["total"]) == total
        by_severity = {"BLOCKING": 0, "WARNING": 0, "INFO": 0}
        for item in behind:
            by_severity[item["severity"]] += 1
        assert (figure["blocking"], figure["warning"], figure["info"]) == (
            by_severity["BLOCKING"],
            by_severity["WARNING"],
            by_severity["INFO"],
        )
        close = shown.json()["close"]
        # the row's link: ``close.id`` is the API-S-Period id the list takes as ``blocking``
        assert close["id"] == queue.states[(code, SEPTEMBER)]
        close_row = close["blockers"]["exceptions_open"]
        holding, _ = _listed(app, maya, blocking=close["id"])
        assert close_row == len(holding) == held
        assert _ids(holding) <= _ids(behind)
        assert figure["total"] >= close_row


def test_a_reader_of_one_entity_is_told_the_count_of_every_item_that_holds_the_period(
    world: CloseWorld,
) -> None:
    """Supervisor rulings R-42 (d) and R-121 (i): the count of what holds a period does not
    depend on its reader, and a reader is not shown an item he may not read (04 T-IMP-05 "An item
    that names no entity", rev 1.206 and 1.218). A Revenue Accountant of AVM-US alone is told the
    same ``blockers.exceptions_open`` as the tenant-wide accountant, 14 — the import that names
    AVM-US and AVM-UK, the unresolved one and the group with a contract of each entity counted.
    Her list under ``blocking`` holds the 11 she may read — the items about her entity alone,
    the uploads whose every named entity her ``contract.read`` covers, and the tenant-level one —
    and none of the three she may not; the home page's figure, the count of her list under
    ``entity``, leaves them out as well. Before item EXC-IMPORT-SCOPE-1 an item without an entity
    was hidden from nobody: she was shown all 14."""
    app, maya, tenant_id = world.app, world.maya, world.tenant_id
    queue = _queue(world)
    imports = _import_items(world, queue)
    state_id = queue.states[(AVM_US, SEPTEMBER)]
    rita = holding(
        app, colleague(tenant_id, "rita"), "revenue_accountant", entity_ids=[world.entity_id]
    )
    everything, _ = _listed(app, maya, blocking=state_id)
    assert (
        len(everything)
        == 14
        == _open_count(app, maya, state_id)
        == _open_count(app, rita, state_id)
    )

    not_hers = {imports["import of both"], imports["unresolved import"]} | queue.ids("mixed group")
    may_read = (queue.ids(*US_SEPTEMBER) - queue.ids("mixed group")) | {
        imports["import of us"],
        imports["tenant-level import"],
    }
    hers, total = _listed(app, rita, blocking=state_id)
    assert _ids(hers) == may_read == _ids(everything) - not_hers
    assert total == "11"
    by_entity, figure = _listed(app, rita, entity=AVM_US, status=list(OPEN))
    assert not _ids(by_entity) & not_hers
    shown = get(app, HOME, rita, {"entity": AVM_US, "period": SEPTEMBER})
    assert shown.status_code == 200, shown.text
    assert str(shown.json()["open_exceptions"]["total"]) == figure
    assert shown.json()["close"]["blockers"]["exceptions_open"] == 14


def test_blocking_takes_one_period_id(world: CloseWorld) -> None:
    """04 §16.14 rev 1.206: an id that names no period lists nothing, as an unknown ``contract``
    id does; a value that is no id, and the parameter sent twice, are 422 ``validation-failed``
    on ``blocking``. The filter binds the cursor as every filter does (API-C-09): a page follows
    under the same period only."""
    app, maya = world.app, world.maya
    queue = _queue(world)
    us_state = queue.states[(AVM_US, SEPTEMBER)]
    uk_state = queue.states[(AVM_UK, SEPTEMBER)]

    unknown = "018f0000-0000-7000-8000-000000000000"
    assert _listed(app, maya, blocking=unknown) == ([], "0")
    assert _listed(app, maya, contract=unknown) == ([], "0")
    # the id of the calendar period is not the id of an API-S-Period
    assert _listed(app, maya, blocking=str(world.period_id)) == ([], "0")

    for params in ({"blocking": "FY2026-P09"}, {"blocking": [us_state, uk_state]}):
        refused = get(app, EXCEPTIONS, maya, params)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("blocking", "API-C-09")]

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(len(US_SEPTEMBER)):
        params: dict[str, Any] = {"blocking": us_state, "limit": 4}
        if cursor is not None:
            params["cursor"] = cursor
        page = get(app, EXCEPTIONS, maya, params)
        assert page.status_code == 200, page.text
        seen += [str(item["id"]) for item in page.json()["items"]]
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break
        foreign = get(app, EXCEPTIONS, maya, {"blocking": uk_state, "limit": 4, "cursor": cursor})
        assert (foreign.status_code, slug(foreign)) == (422, "validation-failed"), foreign.text
    assert len(seen) == len(set(seen)) == len(US_SEPTEMBER)
    assert set(seen) == queue.ids(*US_SEPTEMBER)


# --- EXC-IMPORT-SCOPE-1: who reads, and who acts on, an item that names no entity ----------------
#
# 04 T-IMP-05 "An item that names no entity: who reads it", §15.3 API-R-44, §16.10 (rev 1.218);
# the supervisor's rulings of 2026-10-01. An item that names an entity is the row policy's. An
# item that names none passed the policy for every member and was read, assigned, waived and
# dismissed by every member: the finding of an import the member could not open, the quarantine
# of a group that holds another entity's contract, a suggestion to combine a contract with
# another entity's, the finding of a sync run of another entity's connection.

EVERYONE = frozenset({"maya", "rita", "uma", "bo", "vic"})
US_READERS = frozenset({"maya", "rita", "bo", "vic"})  # contract.read names AVM-US
UK_READERS = frozenset({"maya", "uma", "bo", "vic"})
BOTH_READERS = frozenset({"maya", "bo", "vic"})
US_RESOLVERS = US_READERS  # exception.resolve names AVM-US
UK_RESOLVERS = frozenset({"maya", "uma", "bo"})  # Vic reads AVM-UK and resolves nothing there
BOTH_RESOLVERS = frozenset({"maya", "bo"})
ALL_ENTITIES_ONLY = frozenset({"maya"})
# item -> (who reads it, who acts on it)
LEFT_AT = datetime(2026, 2, 1, tzinfo=UTC)
RULE: Mapping[str, tuple[frozenset[str], frozenset[str]]] = {
    "us entity": (US_READERS, US_RESOLVERS),
    "uk entity": (UK_READERS, UK_RESOLVERS),
    "us contract": (US_READERS, US_RESOLVERS),
    "uk contract": (UK_READERS, UK_RESOLVERS),
    "us group": (US_READERS, US_RESOLVERS),
    "uk group": (UK_READERS, UK_RESOLVERS),
    "us pair": (US_READERS, US_RESOLVERS),  # a group of two contracts of ONE entity
    "mixed group": (BOTH_READERS, BOTH_RESOLVERS),
    "suggestion": (BOTH_READERS, BOTH_RESOLVERS),
    # a payload that names a contract which is no row: what cannot be named is not shown
    "suggestion of an unknown contract": (ALL_ENTITIES_ONLY, ALL_ENTITIES_ONLY),
    # a group no membership names (every product path writes one with the group)
    "empty group": (ALL_ENTITIES_ONLY, ALL_ENTITIES_ONLY),
    # a group of AVM-US's contract that a contract of AVM-UK has left: the open memberships
    "us group, former uk member": (US_READERS, US_RESOLVERS),
    "nothing named": (EVERYONE, EVERYONE),  # about the workspace: every holder, as before
    "import of us": (US_READERS, US_RESOLVERS),
    "import of uk": (UK_READERS, UK_RESOLVERS),
    "import of both": (BOTH_READERS, BOTH_RESOLVERS),
    "tenant-level import": (EVERYONE, ALL_ENTITIES_ONLY),
    "unresolved import": (ALL_ENTITIES_ONLY, ALL_ENTITIES_ONLY),
    "connection of us": (US_READERS, US_RESOLVERS),
    "connection of uk": (UK_READERS, UK_RESOLVERS),
    "connection of both": (BOTH_READERS, BOTH_RESOLVERS),
    "connection of every entity": (ALL_ENTITIES_ONLY, ALL_ENTITIES_ONLY),
}


@dataclass(frozen=True, slots=True)
class Scoped:
    """The world of ``_queue`` with one item of every kind that names no entity, and five people:
    Maya (every entity), Rita and Uma (Revenue Accountants of AVM-US and of AVM-UK), Bo (Revenue
    Accountant of both by name) and Vic (Viewer of both, Revenue Accountant of AVM-US: he reads
    two entities and acts in one)."""

    queue: Queue
    items: Mapping[str, str]
    people: Mapping[str, Actor]


def _scoped(world: CloseWorld) -> Scoped:
    app, tenant_id, us = world.app, world.tenant_id, world.entity_id
    queue = _queue(world)
    uk = queue.uk
    items = {name: str(queue.items[name]) for name in RULE if name in queue.items}
    items |= _import_items(world, queue) | _sync_items(world, queue)
    with system_session(world) as session:
        named = {
            case: session.execute(
                select(exception_item.c.contract_id).where(exception_item.c.id == queue.items[case])
            ).scalar_one()
            for case in ("us contract", "uk contract")
        }
        # a suggestion to combine a contract of each entity: it names the booked contract and no
        # entity, and its message and payload name both (``combination.raise_suggestions``)
        suggestion = exception_item_values(
            tenant_id,
            code="COMBINATION_SUGGESTED",
            severity="WARNING",
            title="Contracts may need to be combined",
            contract_id=named["us contract"],
            source_payload={
                "contract_ids": sorted(str(value) for value in named.values()),
                "contract_external_ids": ["US-1", "UK-1"],
            },
        )
        session.execute(insert(exception_item).values(**suggestion))
        items["suggestion"] = str(suggestion["id"])
        # a group of two contracts of AVM-US: its quarantine names no contract and no entity
        first, first_event, pair = contract_of(session, world)
        buyer = customer_values(tenant_id)
        session.execute(insert(customer).values(**buyer))
        second = contract_values(
            tenant_id,
            customer_id=buyer["id"],
            contracting_entity_id=us,
            combination_group_id=pair,
            head_stream_version=1,
        )
        session.execute(insert(contract).values(**second))
        second_event = contract_event_values(
            tenant_id, contract_id=second["id"], contracting_entity_id=us, stream_version=1
        )
        session.execute(insert(contract_event).values(**second_event))
        for contract_id, event_id in ((first, first_event), (second["id"], second_event["id"])):
            session.execute(
                insert(combination_group_member).values(
                    **combination_group_member_values(
                        tenant_id,
                        combination_group_id=pair,
                        contract_id=contract_id,
                        join_event_id=event_id,
                    )
                )
            )
        of_pair = exception_item_values(tenant_id, combination_group_id=pair)
        session.execute(insert(exception_item).values(**of_pair))
        items["us pair"] = str(of_pair["id"])
        # a suggestion whose payload names, beside AVM-US's contract, an id that is no contract
        unknown = exception_item_values(
            tenant_id,
            code="COMBINATION_SUGGESTED",
            severity="WARNING",
            title="Contracts may need to be combined",
            contract_id=named["us contract"],
            source_payload={
                "contract_ids": sorted([str(named["us contract"]), str(new_id())]),
                "contract_external_ids": ["US-1", "GONE-1"],
            },
        )
        session.execute(insert(exception_item).values(**unknown))
        items["suggestion of an unknown contract"] = str(unknown["id"])
        # a group without a membership
        empty = combination_group_values(tenant_id)
        session.execute(insert(combination_group).values(**empty))
        of_empty = exception_item_values(tenant_id, combination_group_id=empty["id"])
        session.execute(insert(exception_item).values(**of_empty))
        items["empty group"] = str(of_empty["id"])
        # a group of a contract of AVM-US, which a contract of AVM-UK joined and has left: that
        # contract's open membership is in its own group, its closed one in this group
        stays, stays_event, left_group = contract_of(session, world)
        leaver, leaver_event, leaver_group = contract_of(session, world, uk)
        memberships: tuple[tuple[UUID, UUID, UUID, dict[str, Any]], ...] = (
            (left_group, stays, stays_event, {}),
            (leaver_group, leaver, leaver_event, {}),
            (
                left_group,
                leaver,
                leaver_event,
                {"valid_to_known_at": LEFT_AT, "leave_event_id": leaver_event},
            ),
        )
        for group_id, contract_id, event_id, ended in memberships:
            session.execute(
                insert(combination_group_member).values(
                    **combination_group_member_values(
                        tenant_id,
                        combination_group_id=group_id,
                        contract_id=contract_id,
                        join_event_id=event_id,
                        **ended,
                    )
                )
            )
        of_left = exception_item_values(tenant_id, combination_group_id=left_group)
        session.execute(insert(exception_item).values(**of_left))
        items["us group, former uk member"] = str(of_left["id"])
    assert set(items) == set(RULE)
    vic = colleague(tenant_id, "vic")
    assign(vic, "viewer", entity_ids=[us, uk])
    people = {
        "maya": world.maya,
        "rita": holding(app, colleague(tenant_id, "rita"), "revenue_accountant", entity_ids=[us]),
        "uma": holding(app, colleague(tenant_id, "uma"), "revenue_accountant", entity_ids=[uk]),
        "bo": holding(app, colleague(tenant_id, "bo"), "revenue_accountant", entity_ids=[us, uk]),
        "vic": holding(app, vic, "revenue_accountant", entity_ids=[us]),
    }
    return Scoped(queue=queue, items=items, people=people)


def _who(found: Mapping[str, set[str]]) -> dict[str, frozenset[str]]:
    return {name: frozenset(people) for name, people in found.items()}


def test_exc_scope_an_item_that_names_no_entity_is_read_by_the_readers_of_what_it_is_about(
    world: CloseWorld,
) -> None:
    """04 T-IMP-05 "An item that names no entity: who reads it" (rev 1.218). For one item of every
    kind and five people: the list shows an item to exactly the people ``RULE`` names — whose
    ``contract.read`` covers the entity of the contract it names, of every member of its group,
    of both contracts of a suggestion, every entity its upload names or its connection serves —
    and its id answers 404, as an unknown one, to everyone else. An item about the workspace and
    the finding of a tenant-level upload are every holder's; the finding of an unresolved upload,
    and of a connection that serves every entity, an all-entities holder's alone. Before the
    change every one of the twenty-two was listed and read by all five."""
    app = world.app
    scoped = _scoped(world)
    shown = {who: _ids(_listed(app, actor)[0]) for who, actor in scoped.people.items()}
    listed = {
        name: {who for who in scoped.people if item_id in shown[who]}
        for name, item_id in scoped.items.items()
    }
    assert _who(listed) == {name: readers for name, (readers, _) in RULE.items()}

    unknown = get(app, f"{EXCEPTIONS}/{new_id()}", scoped.people["rita"])
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    read: dict[str, set[str]] = {name: set() for name in scoped.items}
    for name, item_id in scoped.items.items():
        for who, actor in scoped.people.items():
            answer = get(app, f"{EXCEPTIONS}/{item_id}", actor)
            if answer.status_code == 200:
                read[name].add(who)
                continue
            assert (answer.status_code, slug(answer)) == (404, "not-found"), answer.text
            assert {key: answer.json()[key] for key in ("title", "detail", "errors")} == {
                key: unknown.json()[key] for key in ("title", "detail", "errors")
            }
    assert _who(read) == {name: readers for name, (readers, _) in RULE.items()}
    # the suggestions' own list follows the same rule (04 API-R-28)
    suggested = {
        who: {
            str(item["id"])
            for item in get(app, "/api/v1/combination-suggestions", actor).json()["items"]
        }
        for who, actor in scoped.people.items()
    }
    assert {who for who, ids in suggested.items() if scoped.items["suggestion"] in ids} == set(
        RULE["suggestion"][0]
    )


def test_exc_scope_acting_asks_exception_resolve_for_everything_the_item_is_about(
    world: CloseWorld,
) -> None:
    """04 API-R-44 (rev 1.218): ``available_actions`` is empty, and each command answers 404,
    for a member who does not hold ``exception.resolve`` for every entity the item is about —
    also when he reads it. Vic reads AVM-UK's items and the finding of the two-entity import and
    acts on none of them; the finding of a tenant-level upload is read by every holder and acted
    on by Maya alone. Before the change a holder of the permission for ANY entity acted on every
    item that named none."""
    app = world.app
    scoped = _scoped(world)
    offered: dict[str, set[str]] = {name: set() for name in scoped.items}
    for who, actor in scoped.people.items():
        by_id = {str(item["id"]): item for item in _listed(app, actor)[0]}
        for name, item_id in scoped.items.items():
            if "ASSIGN" in by_id.get(item_id, {}).get("available_actions", ()):
                offered[name].add(who)
    assert _who(offered) == {name: actors for name, (_, actors) in RULE.items()}

    acted: dict[str, set[str]] = {name: set() for name in scoped.items}
    for name, item_id in scoped.items.items():
        for who, actor in scoped.people.items():
            answer = post(
                app,
                f"{EXCEPTIONS}/{item_id}/assign",
                actor,
                {"owner_membership_id": str(actor.member.membership_id)},
            )
            if answer.status_code == 200:
                acted[name].add(who)
                continue
            assert (answer.status_code, slug(answer)) == (404, "not-found"), (name, who)
            dismissed = post(
                app, f"{EXCEPTIONS}/{item_id}/dismiss", actor, {"comment": "Not ours to keep."}
            )
            assert (dismissed.status_code, slug(dismissed)) == (404, "not-found"), (name, who)
    assert _who(acted) == {name: actors for name, (_, actors) in RULE.items()}


def test_exc_scope_an_item_is_assigned_to_someone_who_reads_it(world: CloseWorld) -> None:
    """04 API-R-44 ``assign`` (rev 1.218): the owner of an item is told of it (NTF-11) and opens
    it from that message, so an owner is a member who reads the item. Maya assigns each of the
    twenty-two items to each of the five people: the command succeeds exactly when that person's
    own ``GET /exceptions/{id}`` answers 200, and otherwise answers 422 on
    ``owner_membership_id`` with the reason as the problem's detail — the screen prints the
    detail — and nobody is notified. Before the change any active member was made the owner."""
    app, maya = world.app, world.maya
    scoped = _scoped(world)
    assigned: dict[str, set[str]] = {name: set() for name in scoped.items}
    reads: dict[str, set[str]] = {name: set() for name in scoped.items}
    for name, item_id in scoped.items.items():
        for who, actor in scoped.people.items():
            if get(app, f"{EXCEPTIONS}/{item_id}", actor).status_code == 200:
                reads[name].add(who)
            answer = post(
                app,
                f"{EXCEPTIONS}/{item_id}/assign",
                maya,
                {"owner_membership_id": str(actor.member.membership_id)},
            )
            if answer.status_code == 200:
                assert answer.json()["owner_membership_id"] == str(actor.member.membership_id)
                assigned[name].add(who)
                continue
            assert (answer.status_code, slug(answer)) == (422, "validation-failed"), (name, who)
            assert fields(answer) == [("owner_membership_id", "T-IMP-05")]
            assert answer.json()["detail"] == OWNER_CANNOT_READ
    assert _who(assigned) == _who(reads) == {name: readers for name, (readers, _) in RULE.items()}
    # a member without any role reads nothing — not even an item about the workspace, which
    # every holder of ``contract.read`` reads — and owns nothing
    nora = colleague(world.tenant_id, "nora")
    refused = post(
        app,
        f"{EXCEPTIONS}/{scoped.items['nothing named']}/assign",
        maya,
        {"owner_membership_id": str(nora.membership_id)},
    )
    assert refused.status_code == 422, refused.text
    assert slug(refused) == "validation-failed"
    assert fields(refused) == [("owner_membership_id", "T-IMP-05")]
    assert refused.json()["detail"] == OWNER_CANNOT_READ
    with system_session(world) as session:
        told = session.execute(
            select(notification.c.subject_id, notification.c.recipient_membership_id).where(
                notification.c.kind == "EXCEPTION_ASSIGNED"
            )
        ).all()
    by_member = {str(actor.member.membership_id): who for who, actor in scoped.people.items()}
    by_item = {item_id: name for name, item_id in scoped.items.items()}
    notified: dict[str, set[str]] = {name: set() for name in scoped.items}
    for subject_id, membership_id in told:
        notified[by_item[str(subject_id)]].add(by_member[str(membership_id)])
    assert _who(notified) == _who(assigned)


def test_exc_scope_a_waiver_names_the_entities_whose_close_the_item_holds(
    world: CloseWorld,
) -> None:
    """04 §16.10 (rev 1.218; the supervisor's ruling of 2026-10-01): an ``EXCEPTION_WAIVER``
    request names the entities the one attribution gives its item (``gates.item_of_entity``) —
    the members' entities of a group, the entities an upload names or a connection serves, and
    EVERY entity where the attribution says every entity: a tenant-level or unresolved upload, a
    connection that names none, an item about the workspace. While it is pending it is a pending
    approval of each of those entities' period (``blockers.approvals_pending``). Before the
    change the waiver of an item that named no entity and no contract was a tenant-level
    request — any holder of ``exception.waive`` decided it — and counted in nobody's
    ``approvals_pending``."""
    app, maya, us = world.app, world.maya, world.entity_id
    scoped = _scoped(world)
    uk = scoped.queue.uk
    both = sorted([us, uk], key=str)
    states = {code: scoped.queue.states[(code, SEPTEMBER)] for code in (AVM_US, AVM_UK)}

    def pending() -> dict[str, int]:
        return {
            code: _blockers(app, maya, state)["approvals_pending"] for code, state in states.items()
        }

    expected: Mapping[str, tuple[Any, list[UUID], bool, tuple[int, int]]] = {
        # item -> (entity_id, entity_ids, is_all_entities, what it adds for (AVM-US, AVM-UK))
        "us contract": (us, [], False, (1, 0)),
        "us pair": (us, [], False, (1, 0)),
        "mixed group": (None, both, False, (1, 1)),
        "suggestion": (None, both, False, (1, 1)),
        # an id that is no contract: every entity rather than an entity dropped; the item
        # names AVM-US's contract, whose close it holds
        "suggestion of an unknown contract": (None, [], True, (1, 0)),
        # a group no membership names: every entity; it holds nobody's close
        "empty group": (None, [], True, (0, 0)),
        "us group, former uk member": (us, [], False, (1, 0)),
        "nothing named": (None, [], True, (1, 1)),
        "import of uk": (uk, [], False, (0, 1)),
        "import of both": (None, both, False, (1, 1)),
        "tenant-level import": (None, [], True, (1, 1)),
        "unresolved import": (None, [], True, (1, 1)),
        "connection of uk": (uk, [], False, (0, 1)),
        "connection of every entity": (None, [], True, (1, 1)),
    }
    found: dict[str, tuple[Any, list[UUID], bool, tuple[int, int]]] = {}
    for name in expected:
        before = pending()
        asked = post(
            app,
            f"{EXCEPTIONS}/{scoped.items[name]}/request-waiver",
            maya,
            {"comment": "Accepted for this period; corrected at the source."},
        )
        assert asked.status_code == 200, (name, asked.text)
        with system_session(world) as session:
            row = session.execute(
                select(
                    approval_request.c.entity_id,
                    approval_request.c.entity_ids,
                    approval_request.c.is_all_entities,
                ).where(approval_request.c.id == UUID(str(asked.json()["approval_request_id"])))
            ).one()
        after = pending()
        found[name] = (
            row.entity_id,
            sorted(row.entity_ids or (), key=str),
            bool(row.is_all_entities),
            (after[AVM_US] - before[AVM_US], after[AVM_UK] - before[AVM_UK]),
        )
    assert found == expected


def test_exc_scope_a_suggestion_across_two_entities_is_dismissed_by_a_holder_for_both(
    world: CloseWorld,
) -> None:
    """04 API-R-28 (rev 1.218): ``POST /combination-suggestions/{id}/dismiss`` answers 404, as
    for an unknown id, to a member who does not read the suggestion, and asks ``contract.create``
    for the entity of EACH contract a suggestion names when it names no entity of its own. Uma
    and Rita each read one of the two contracts; Vic reads both and creates contracts for AVM-US
    alone; Bo holds the permission for both and dismisses it. Before the change a holder of
    ``contract.create`` for ANY entity dismissed a suggestion that named no entity."""
    app = world.app
    scoped = _scoped(world)
    path = f"/api/v1/combination-suggestions/{scoped.items['suggestion']}/dismiss"
    body = {"rationale": "Negotiated separately; the prices do not depend on each other."}
    answers = {who: post(app, path, scoped.people[who], body) for who in ("uma", "rita", "vic")}
    assert {who: answer.status_code for who, answer in answers.items()} == dict.fromkeys(
        ("uma", "rita", "vic"), 404
    )
    assert {slug(answer) for answer in answers.values()} == {"not-found"}
    with system_session(world) as session:
        kept = session.execute(
            select(exception_item.c.status).where(
                exception_item.c.id == UUID(scoped.items["suggestion"])
            )
        ).scalar_one()
    assert str(getattr(kept, "value", kept)) == "OPEN"
    dismissed = post(app, path, scoped.people["bo"], body)
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["status"] == "DISMISSED"


def test_exc_scope_a_waiver_is_offered_to_the_members_the_kernel_takes_it_from(
    world: CloseWorld,
) -> None:
    """04 §16.14 ``REQUEST_WAIVER`` (rev 1.218): the action is offered exactly to the members
    whose request the approvals kernel takes — who act on the item AND whose own entities cover
    the entities the waiver names (§16.10; supervisor ruling R-64 (6): a preparer submits nothing
    for an entity outside his roles). A member who acts on an item covers everything it is
    about, so the two agree for every item but one about the workspace: it is taken in hand by a
    holder for any entity and its waiver spans every entity, so only Maya is offered it and the
    command of anyone else who acts on the item is the kernel's 403 by name. For one item of
    every kind and five people the offer and the command's answer are held together; each
    request that is taken is withdrawn by its preparer, so the next person meets the item as the
    first did. Before the change every one of the five was offered, and asked, the waiver of
    every item that named no entity."""
    app = world.app
    scoped = _scoped(world)
    offered: dict[str, set[str]] = {name: set() for name in scoped.items}
    taken: dict[str, set[str]] = {name: set() for name in scoped.items}
    outside: dict[str, set[str]] = {name: set() for name in scoped.items}
    for name, item_id in scoped.items.items():
        for who, actor in scoped.people.items():
            shown = get(app, f"{EXCEPTIONS}/{item_id}", actor)
            if shown.status_code == 200 and "REQUEST_WAIVER" in shown.json()["available_actions"]:
                offered[name].add(who)
            asked = post(
                app,
                f"{EXCEPTIONS}/{item_id}/request-waiver",
                actor,
                {"comment": "Accepted for this period; corrected at the source."},
            )
            if asked.status_code == 200:
                taken[name].add(who)
                request_id = asked.json()["approval_request_id"]
                withdrawn = post(app, f"/api/v1/approvals/{request_id}/withdraw", actor, {})
                assert withdrawn.status_code == 200, (name, who, withdrawn.text)
            elif asked.status_code == 403:
                assert slug(asked) == "forbidden", (name, who, asked.text)
                assert asked.json()["detail"] == OUTSIDE_SCOPE_DETAIL
                outside[name].add(who)
            else:
                assert (asked.status_code, slug(asked)) == (404, "not-found"), (name, who)
    asks = {
        name: ALL_ENTITIES_ONLY if name == "nothing named" else actors
        for name, (_, actors) in RULE.items()
    }
    assert _who(taken) == asks
    assert _who(offered) == _who(taken)
    assert {name: people for name, people in _who(outside).items() if people} == {
        "nothing named": EVERYONE - ALL_ENTITIES_ONLY
    }


def test_exc_scope_a_member_acts_on_an_item_he_reads_whatever_his_roles(world: CloseWorld) -> None:
    """04 T-IMP-05 "Who acts on it" (rev 1.218): an item's id answers 404 on every command to a
    member who does not read it. Every default role that holds ``exception.resolve`` holds
    ``contract.read`` for the same entities, so the five people of ``_scoped`` cannot show it; a
    role defined in the workspace need not. For a principal who holds ``exception.resolve`` for
    AVM-US and AVM-UK and ``contract.read`` for AVM-US alone, ``acting`` names exactly the items
    he both reads and holds the permission for: the items about AVM-UK that the permission alone
    would admit — the two-entity group's, the two-entity import's, the suggestion — are not his
    to act on."""
    scoped = _scoped(world)
    us, uk = world.entity_id, scoped.queue.uk
    scopes = {"contract.read": frozenset({us}), "exception.resolve": frozenset({us, uk})}
    resolver = Principal(
        kind=PrincipalKind.USER,
        id=new_id(),
        tenant_id=world.tenant_id,
        membership_id=new_id(),
        display_name="Resolver of both, reader of one",
        roles=(),
        permissions=frozenset(scopes),
        permission_scopes=scopes,
        entity_scope=tuple(sorted((us, uk), key=str)),
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    names = {UUID(item_id): name for name, item_id in scoped.items.items()}
    item = exception_item.c
    listed = item.id.in_(list(names))
    with tenant_session(resolver.db_context, read_only=True) as session:
        rows = [
            dict(row) for row in session.execute(select(exception_item).where(listed)).mappings()
        ]
        reads = set(
            session.scalars(select(item.id).where(listed, exception_queue.readable(resolver)))
        )
        holds = set(
            session.scalars(select(item.id).where(listed, exception_queue.actable(resolver)))
        )
        acts = exception_queue.acting(session, resolver, rows)
    assert len(rows) == len(names)
    assert {names[item_id] for item_id in acts} == {names[item_id] for item_id in reads & holds}
    assert {names[item_id] for item_id in holds - reads} == {
        "uk contract",
        "uk group",
        "mixed group",
        "suggestion",
        "import of uk",
        "import of both",
        "connection of uk",
        "connection of both",
    }
