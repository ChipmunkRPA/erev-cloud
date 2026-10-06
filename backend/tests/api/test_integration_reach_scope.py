"""The reach of an integration connection under a role held for named entities (item
SCOPE-WORKSPACE-LISTS-1, part (c2); supervisor rulings R-28 and R-115 (c) and the supervisor's
ruling of 2026-10-01, answer Q1; 03 REQ-PLT-012; 04 API-C-03, API-R-45, T-INT-01, T-INT-02,
T-INT-04).

A connection serves the entities it names, and every entity when it names none. The three tables
are RLS-T: no row policy knows a connection's entities, so the readers of API-R-45 decide. A
principal reaches a connection when its scope of the route's permission covers EVERY entity the
connection serves — a connection that serves every entity only when the permission is held for
all entities. Out of reach, the connection, its sync runs and the external ids kept under it are
absent from the lists and 404 by id, to a read and to a command alike; and nobody makes a
connection serve an entity outside their own scope.

WLD-K-04 (``worlds.k04_saltmarsh``; AVM-UK and AVM-US). Every role is granted through the product
(``POST /role-assignments``, requested by Marcus, approved by Grace): Ines is Integration Admin
of all entities, Ivo of AVM-US alone, Mira Revenue Accountant of AVM-US alone. Ines creates four
connections — for AVM-UK, for AVM-US, for both, and for every entity — and queues a sync run of
the first two; Maya, Revenue Accountant of all entities, links an external id under each.

Measured before the item, with the same grants: Ivo listed and read all four connections, the
sync run of AVM-UK's and all four external ids; renamed, tested and synced every connection;
re-pointed AVM-UK's connection to AVM-US; and created a connection that serves every entity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.entity_scope import BEYOND_OWN_SCOPE
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, integration_connection, sync_run
from erev_api.enums import AuditOutcome
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor
from support.reference import get, patch, post
from support.worlds import AVM_US
from tests.api.test_tenant_wide_acts_scope import for_all_entities, slug
from tests.domain.reports.test_entity_scoped_runs_db import scoped, second_admin

API: Final = "/api/v1"
INTEGRATIONS: Final = f"{API}/integrations"
SYNC_RUNS: Final = f"{API}/sync-runs"
EXTERNAL_IDS: Final = f"{API}/external-ids"
MOCK_BASE: Final = "/api/v1/__mocks__/salesforce"
LABELS: Final = ("uk", "us", "both", "every")
OUT_OF_REACH: Final = ("uk", "both", "every")  # of an Integration Admin of AVM-US alone
CREATE: Final = "integration_connection.create"
UPDATE: Final = "integration_connection.update"
ENTITY_UNKNOWN: Final = "entity_ids name no legal entity of this workspace: {ids}."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@dataclass(frozen=True, slots=True)
class Saltmarsh:
    """WLD-K-04 with its four connections, the two sync runs and the four external ids."""

    k04: worlds.K04World
    grace: Actor  # Tenant Admin, all entities: approves the access requests
    ines: Actor  # Integration Admin, all entities
    ivo: Actor  # Integration Admin, AVM-US
    connections: dict[str, str]  # label → connection id
    runs: dict[str, str]  # label → sync run id ("uk", "us")
    links: dict[str, str]  # label → external id map id

    @property
    def world(self) -> worlds.ReportWorld:
        return self.k04.report

    @property
    def app(self) -> FastAPI:
        return self.k04.app

    def path(self, label: str) -> str:
        return f"{INTEGRATIONS}/{self.connections[label]}"


def connection_body(code: str, entity_ids: list[UUID]) -> dict[str, Any]:
    return {
        "code": code,
        "name": f"Salesforce ({code})",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "entity_ids": [str(value) for value in entity_ids],
        "base_url": MOCK_BASE,
        "config": {},
        "secret_ref": None,
    }


def saltmarsh(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> Saltmarsh:
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    grace = second_admin(world, clock)
    ines = for_all_entities(world, clock, grace, "ines", "integration_admin")
    ivo = scoped(world, clock, grace, "ivo", ("integration_admin", AVM_US))
    served = {
        "uk": [k04.uk_entity_id],
        "us": [k04.us_entity_id],
        "both": [k04.uk_entity_id, k04.us_entity_id],
        "every": [],
    }
    connections: dict[str, str] = {}
    links: dict[str, str] = {}
    for label in LABELS:
        created = post(app, INTEGRATIONS, ines, connection_body(f"sf-{label}", served[label]))
        assert created.status_code == 201, created.text
        connection_id = str(created.json()["id"])
        active = patch(
            app,
            f"{INTEGRATIONS}/{connection_id}",
            ines,
            {"status": "ACTIVE"},
            if_match=created.headers["ETag"],
        )
        assert active.status_code == 200, active.text
        connections[label] = connection_id
        linked = post(
            app,
            EXTERNAL_IDS,
            world.maya,
            {
                "integration_connection_id": connection_id,
                "object_type": "contract",
                "internal_id": str(k04.contract_id),
                "external_id": f"ORD-{label}",
            },
        )
        assert linked.status_code == 201, linked.text
        links[label] = str(linked.json()["id"])
    runs: dict[str, str] = {}
    for label in ("uk", "us"):
        queued = post(
            app, f"{INTEGRATIONS}/{connections[label]}/sync", ines, {"kind": "INBOUND_POLL"}
        )
        assert queued.status_code == 202, queued.text
        runs[label] = queued.headers["X-Erev-Sync-Run-Id"]
    return Saltmarsh(k04, grace, ines, ivo, connections, runs, links)


def listed(place: Saltmarsh, path: str, actor: Actor, **params: str) -> set[str]:
    """The ids a list answers ``actor``."""
    answered = get(place.app, path, actor, {"limit": "200", **params})
    assert answered.status_code == 200, answered.text
    return {str(item["id"]) for item in answered.json()["items"]}


def stored(place: Saltmarsh, label: str) -> dict[str, Any]:
    (row,) = place.world.place.rows(
        select(integration_connection).where(
            integration_connection.c.id == UUID(place.connections[label])
        )
    )
    return row


def runs_of(place: Saltmarsh, label: str) -> int:
    return len(
        place.world.place.rows(
            select(sync_run.c.id).where(
                sync_run.c.integration_connection_id == UUID(place.connections[label])
            )
        )
    )


def denials(place: Saltmarsh, action: str) -> list[tuple[str | None, dict[str, Any]]]:
    """(object id, detail) of the DENIED events of a command, oldest first."""
    rows = place.world.place.rows(
        select(audit_event.c.object_id, audit_event.c.detail)
        .where(audit_event.c.action == action, audit_event.c.outcome == AuditOutcome.DENIED.value)
        .order_by(audit_event.c.chain_seq)
    )
    return [
        (None if row["object_id"] is None else str(row["object_id"]), dict(row["detail"]))
        for row in rows
    ]


@pytest.mark.slow
def test_a_connection_is_reached_by_a_scope_that_covers_every_entity_it_serves(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ivo, Integration Admin of AVM-US alone, is listed and answered the connection of AVM-US,
    its sync run and its external id, and runs its commands. The connection of AVM-UK, the one
    of both entities and the one that serves every entity are absent from his lists and 404 by
    id — to the read, to a rename, to the probe and to a sync — and stay as they were; Mira links
    an external id under the connection of her entity and under no other. Ines, of all entities,
    reaches all four. Before: Ivo read and commanded every one of them."""
    place = saltmarsh(app, keyring, clock, files)
    ines, ivo = place.ines, place.ivo
    every_connection = set(place.connections.values())

    assert listed(place, INTEGRATIONS, ines) == every_connection
    assert listed(place, SYNC_RUNS, ines) >= set(place.runs.values())
    assert listed(place, EXTERNAL_IDS, ines) == set(place.links.values())

    assert listed(place, INTEGRATIONS, ivo) == {place.connections["us"]}
    assert listed(place, SYNC_RUNS, ivo) == {place.runs["us"]}
    assert listed(place, EXTERNAL_IDS, ivo) == {place.links["us"]}
    # the list's own filter answers nothing about a connection out of reach
    assert listed(place, SYNC_RUNS, ivo, connection=place.connections["uk"]) == set()
    assert listed(place, EXTERNAL_IDS, ivo, connection=place.connections["uk"]) == set()
    assert get(app, f"{SYNC_RUNS}/{place.runs['us']}", ivo).status_code == 200
    absent = get(app, f"{SYNC_RUNS}/{place.runs['uk']}", ivo)
    assert (absent.status_code, slug(absent)) == (404, "not-found"), absent.text

    before = {label: (stored(place, label), runs_of(place, label)) for label in LABELS}
    for label in OUT_OF_REACH:
        path = place.path(label)
        etag = get(app, path, ines).headers["ETag"]
        answers = {
            "read": get(app, path, ivo),
            "rename": patch(app, path, ivo, {"name": "Renamed by Ivo"}, if_match=etag),
            "test": post(app, f"{path}/test", ivo, {}),
            "sync": post(app, f"{path}/sync", ivo, {"kind": "INBOUND_POLL"}),
        }
        assert {name: (r.status_code, slug(r)) for name, r in answers.items()} == dict.fromkeys(
            answers, (404, "not-found")
        ), label
        assert (stored(place, label), runs_of(place, label)) == before[label], label

    # the connection of his own entity: every read and command answers
    own = place.path("us")
    shown = get(app, own, ivo)
    assert shown.status_code == 200, shown.text
    renamed = patch(app, own, ivo, {"name": "Salesforce (US)"}, if_match=shown.headers["ETag"])
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Salesforce (US)"), renamed.text
    assert post(app, f"{own}/test", ivo, {}).status_code == 200
    assert post(app, f"{own}/sync", ivo, {"kind": "INBOUND_POLL"}).status_code == 202
    assert runs_of(place, "us") == before["us"][1] + 2  # the probe's run and the sync's

    # an external id is linked under a connection in reach (``masterdata.maintain``)
    mira = scoped(place.world, clock, place.grace, "mira", ("revenue_accountant", AVM_US))
    link = {
        "object_type": "legal_entity",
        "internal_id": str(place.k04.us_entity_id),
        "external_id": "SUBSIDIARY-US",
    }
    for label in OUT_OF_REACH:
        refused = post(
            app, EXTERNAL_IDS, mira, {**link, "integration_connection_id": place.connections[label]}
        )
        assert (refused.status_code, slug(refused)) == (404, "not-found"), (label, refused.text)
    linked = post(
        app, EXTERNAL_IDS, mira, {**link, "integration_connection_id": place.connections["us"]}
    )
    assert linked.status_code == 201, linked.text
    # (the list is read with ``integration.manage``, which Mira does not hold)
    assert listed(place, EXTERNAL_IDS, ines) == {*place.links.values(), str(linked.json()["id"])}
    assert listed(place, EXTERNAL_IDS, ivo) == {place.links["us"], str(linked.json()["id"])}
    # a row out of reach is absent: no refusal is recorded for it
    assert denials(place, CREATE) == [] and denials(place, UPDATE) == []


@pytest.mark.slow
def test_a_connection_serves_no_entity_outside_its_administrators_scope(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The take-over measured before the item — Ivo, Integration Admin of AVM-US alone, moved
    AVM-UK's connection to AVM-US with one ``PATCH`` and it answered 200 — now answers 404 and
    the connection serves AVM-UK as before. On a connection of his own he names AVM-US only: an
    entity outside his scope is refused as an id that names none, and the empty list — every
    entity — by name, each 422 on ``entity_ids`` after a DENIED event of the command. The same
    holds at creation. Ines, of all entities, moves a connection and creates one for every
    entity."""
    place = saltmarsh(app, keyring, clock, files)
    ines, ivo = place.ines, place.ivo
    uk, us = place.k04.uk_entity_id, place.k04.us_entity_id
    unknown = ENTITY_UNKNOWN.format(ids=uk)

    # the take-over
    path = place.path("uk")
    etag = get(app, path, ines).headers["ETag"]
    taken = patch(app, path, ivo, {"entity_ids": [str(us)]}, if_match=etag)
    assert (taken.status_code, slug(taken)) == (404, "not-found"), taken.text
    assert stored(place, "uk")["entity_ids"] == [uk]

    def finding(response: Any) -> tuple[int, str, list[tuple[str, str, str]]]:
        body = response.json()
        errors = [(e["field"], e["rule_id"], e["message"]) for e in body.get("errors", ())]
        return response.status_code, slug(response), errors

    beyond = (422, "validation-failed", [("entity_ids", "T-INT-01", unknown)])
    every = (422, "validation-failed", [("entity_ids", "T-INT-01", BEYOND_OWN_SCOPE)])

    # creation
    assert finding(post(app, INTEGRATIONS, ivo, connection_body("ivo-uk", [uk]))) == beyond
    assert finding(post(app, INTEGRATIONS, ivo, connection_body("ivo-both", [us, uk]))) == beyond
    assert finding(post(app, INTEGRATIONS, ivo, connection_body("ivo-every", []))) == every
    created = post(app, INTEGRATIONS, ivo, connection_body("ivo-us", [us]))
    assert created.status_code == 201, created.text
    own = f"{INTEGRATIONS}/{created.json()['id']}"
    own_id = str(created.json()["id"])
    etag = created.headers["ETag"]

    # a change of the entities of his own connection
    assert finding(patch(app, own, ivo, {"entity_ids": [str(uk)]}, if_match=etag)) == beyond
    wider = patch(app, own, ivo, {"entity_ids": [str(us), str(uk)]}, if_match=etag)
    assert finding(wider) == beyond
    assert finding(patch(app, own, ivo, {"entity_ids": []}, if_match=etag)) == every
    assert finding(patch(app, own, ivo, {"entity_ids": None}, if_match=etag)) == every
    kept = patch(app, own, ivo, {"entity_ids": [str(us)], "name": "Ivo (US)"}, if_match=etag)
    assert kept.status_code == 200, kept.text
    assert kept.json()["entity_ids"] == [str(us)]

    named = {"rule_id": "T-INT-01", "permission": "integration.manage"}
    asked_all = {**named, "scope": "*"}
    assert denials(place, CREATE) == [(None, named), (None, named), (None, asked_all)]
    assert denials(place, UPDATE) == [
        (own_id, named),
        (own_id, named),
        (own_id, asked_all),
        (own_id, asked_all),
    ]
    assert listed(place, INTEGRATIONS, ivo) == {place.connections["us"], own_id}

    # the administrator of all entities
    etag = get(app, path, ines).headers["ETag"]
    moved = patch(app, path, ines, {"entity_ids": [str(us)]}, if_match=etag)
    assert moved.status_code == 200, moved.text
    assert stored(place, "uk")["entity_ids"] == [us]
    assert post(app, INTEGRATIONS, ines, connection_body("ines-every", [])).status_code == 201
    assert len(denials(place, CREATE)) == 3 and len(denials(place, UPDATE)) == 4
