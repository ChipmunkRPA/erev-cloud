"""A calculator run reads within its requester's entities and is read within its own (item
SSP-ENTITY-SCOPE-1; supervisor ruling R-28, row N-29; 04 T-REF-32 and API-R-27 rev 1.277; 03
REQ-PLT-012).

What a run shows is contract data — the order, its unit price, its customer — and its job runs as
SYSTEM. Measured before (lane F-RPS-REG's row 4): an SSP Analyst of AVM-DE alone listed and read
the run, the results and the observations of an order of AVM-US that ``GET /contracts`` answers
her 404 for; her own run read that order; and she created a draft version from the other run.

The world is the calculator world of ``test_calculator.py`` — Maya, the approvers, US-LIST with
2026-H1 — with the entities AVM-US and AVM-DE on one calendar and one ACTIVE single-obligation
contract of each: SF-ORD-20101 of AVM-US at 96,000.00 and SF-ORD-30101 of AVM-DE at 50,000.00,
both for AVM-PLAT-100, booked on 2026-03-01. Ann is SSP Analyst of AVM-DE alone; Uma of AVM-US
alone. Two members tell the run's permission from the route's, each through roles of one
permission: Cleo holds ``ssp.read`` and ``ssp.create`` for every entity and ``contract.read``
for AVM-DE alone; Rolf is SSP Analyst of AVM-DE and holds ``contract.read`` for every entity;
Nora holds ``ssp.read`` and ``ssp.create`` for every entity and reads no contract.
The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, ssp_calculator_run
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    TPL_SUB_DAILY,
    booked_contract,
    computed,
    customer_id,
    fake_compute,
    open_periods,
    published_template,
    set_default_template,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled
from support.reference import assign, entity, fields, get, post, slug
from support.rows import insert_custom_role
from tests.domain.ssp.test_calculator import (
    PLATFORM,
    RUN_ID_HEADER,
    RUNS,
    SSP_BOOKS,
    built_world,
    run_body,
    work,
)
from tests.domain.ssp.test_calculator import World as CalculatorWorld

NOBODY = "00000000-0000-0000-0000-000000000000"
US_ORDER = ("SF-ORD-20101 O1", "96000")
DE_ORDER = ("SF-ORD-30101 O1", "50000")


@dataclass(frozen=True, slots=True)
class World:
    app: FastAPI
    base: CalculatorWorld
    runtime: JobRuntime
    maya: Actor
    ann: Actor  # SSP Analyst of AVM-DE alone
    uma: Actor  # SSP Analyst of AVM-US alone
    cleo: Actor  # ssp.read and ssp.create for every entity; contract.read for AVM-DE alone
    rolf: Actor  # SSP Analyst of AVM-DE; contract.read for every entity
    nora: Actor  # ssp.read and ssp.create for every entity; no contract.read
    entities: dict[str, UUID]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def built(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> World:
    """The world of the module docstring, through the product's commands."""
    base = built_world(app, keyring, clock)
    maya = base.maya
    files = LocalFileStore(app_settings.file_root)
    someone = colleague(base.tenant_id, "carmen")
    assign(someone, "controller")
    carmen = enrolled(app, clock, someone)
    calendar_id, us_id = world_calendar(app, maya)
    made = entity(
        app,
        maya,
        code="AVM-DE",
        calendar_id=calendar_id,
        functional_currency="USD",
        time_zone="Europe/Berlin",
    )
    open_periods(
        app, maya, entity_code="AVM-DE", keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    entities = {"AVM-US": us_id, "AVM-DE": UUID(str(made["id"]))}
    buyer = customer_id(app, maya, code="C-12", name="Kinsley Marrow Foods Inc. (Demo)")
    line = {
        "obligation_key": "POB-01",
        "product_code": PLATFORM,
        "quantity": "1",
        "total_price": "96000.00",
        "start_date": "2026-03-01",
        "end_date": "2027-02-28",
    }
    template = published_template(
        app, maya, carmen, code="TPL-SUB-DAILY", outputs=TPL_SUB_DAILY, case_line=line
    )
    set_default_template(app, maya, base.platform_id, template["template_id"])
    stamp_test_release()
    place = workspace(app, clock, keyring, files, maya)
    for external_id, entity_code, price in (
        ("SF-ORD-20101", "AVM-US", "96000.00"),
        ("SF-ORD-30101", "AVM-DE", "50000.00"),
    ):
        booked = booked_contract(
            place,
            {
                "external_id": external_id,
                "customer_id": str(buyer),
                "contracting_entity_code": entity_code,
                "transaction_currency": "USD",
                "inception_date": "2026-03-01",
                "lines": [
                    {
                        "obligation_key": "O1",
                        "product_code": PLATFORM,
                        "quantity": "1",
                        "total_price": {"amount": price, "currency": "USD"},
                        "start_date": "2026-03-01",
                        "end_date": "2027-02-28",
                    }
                ],
            },
            activate=True,
        )
        computed(place, booked.combination_group["id"], run=fake_compute)

    def analyst(name: str, entity_code: str) -> Actor:
        found = colleague(base.tenant_id, name)
        assign(found, "ssp_analyst", entity_ids=[entities[entity_code]])
        return enrolled(app, clock, found)

    everyone = DbContext(tenant_id=base.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(everyone) as session:
        for code, permissions in (
            ("only_ssp", ["ssp.read", "ssp.create"]),
            ("only_contracts", ["contract.read"]),
        ):
            insert_custom_role(
                session, tenant_id=base.tenant_id, code=code, permissions=permissions
            )
    cleo_member = colleague(base.tenant_id, "cleo")
    assign(cleo_member, "only_ssp")
    assign(cleo_member, "only_contracts", entity_ids=[entities["AVM-DE"]])
    rolf_member = colleague(base.tenant_id, "rolf")
    assign(rolf_member, "ssp_analyst", entity_ids=[entities["AVM-DE"]])
    assign(rolf_member, "only_contracts")
    nora_member = colleague(base.tenant_id, "nora")
    assign(nora_member, "only_ssp")

    return World(
        app=app,
        base=base,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        maya=maya,
        ann=analyst("ann", "AVM-DE"),
        uma=analyst("uma", "AVM-US"),
        cleo=enrolled(app, clock, cleo_member),
        rolf=enrolled(app, clock, rolf_member),
        nora=enrolled(app, clock, nora_member),
        entities=entities,
    )


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> World:
    return built(app, keyring, clock, app_settings)


def told(response: HttpResponse) -> tuple[int, dict[str, Any]]:
    """What an answer tells its caller: the status and the body without the request's own id."""
    return response.status_code, {**response.json(), "instance": None}


def run_of(world: World, actor: Actor, **dimensions: str) -> str:
    """A ``committed_obligations`` run of ``actor`` with the entity filter given, worked; its id."""
    body = run_body(world.base, None, source="committed_obligations", dimensions=dimensions)
    started = post(world.app, RUNS, actor, body)
    assert started.status_code == 202, started.text
    work(world.base, UUID(started.json()["id"]), world.runtime)
    return str(started.headers[RUN_ID_HEADER])


def observations(world: World, actor: Actor, run_id: str) -> list[tuple[str, str]]:
    """(source reference, unit price as a whole number) of the run's observations, as read."""
    found = get(world.app, f"{RUNS}/{run_id}/observations", actor, {"limit": "50"})
    assert found.status_code == 200, found.text
    return [
        (str(item["source_reference"]), str(item["unit_price"]).split(".")[0])
        for item in found.json()["items"]
    ]


def stored_scope(world: World, run_id: str) -> list[UUID] | None:
    """entity_ids of the run as stored: None for a run of every entity."""
    ctx = DbContext(tenant_id=world.base.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        stored = session.execute(
            select(ssp_calculator_run.c.entity_ids).where(ssp_calculator_run.c.id == UUID(run_id))
        ).scalar_one()
    return None if stored is None else [UUID(str(value)) for value in stored]


def run_denials(world: World) -> list[tuple[str, UUID | None, dict[str, Any]]]:
    """(action, actor, detail) of the ``DENIED`` audit events of calculator runs, in order."""
    ctx = DbContext(tenant_id=world.base.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        rows = session.execute(
            select(audit_event.c.action, audit_event.c.actor_id, audit_event.c.detail)
            .where(
                audit_event.c.object_type == "ssp_calculator_run",
                audit_event.c.outcome == "DENIED",
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [(str(action), actor_id, dict(detail)) for action, actor_id, detail in rows]


def runs_listed(world: World, actor: Actor) -> set[str]:
    found = get(world.app, RUNS, actor, {"limit": "50"})
    assert found.status_code == 200, found.text
    return {str(item["id"]) for item in found.json()["items"]}


def test_ssp_entity_scope_1_a_run_reads_within_its_requesters_entities(world: World) -> None:
    """The provider. Ann's run over committed contract lines reads the order of AVM-DE and not
    the order of AVM-US — with no entity filter, and with the filter AVM-US, which is no entity
    of hers and matches nothing, as a code nobody knows does. Her run stores her scope. Maya,
    who reads every entity, reads both orders and stores a run of all entities; her run with the
    filter AVM-DE stores that entity alone. The scope is the requester's ``contract.read`` and
    not the route's permission (Cleo, Rolf), a requester who reads no contract starts no run
    (Nora: 403, recorded), and a run names a book its requester may prepare: the book of AVM-US
    answers Ann as a book that does not exist.

    Fail-first: Ann's run, with and without the filter, read SF-ORD-20101 of AVM-US."""
    app = world.app
    de, us = world.entities["AVM-DE"], world.entities["AVM-US"]
    hers = run_of(world, world.ann)
    assert observations(world, world.ann, hers) == [DE_ORDER]
    assert stored_scope(world, hers) == [de]
    filtered = run_of(world, world.ann, entity="AVM-US")
    assert observations(world, world.ann, filtered) == []
    assert stored_scope(world, filtered) == [de]
    unknown = run_of(world, world.ann, entity="AVM-XX")
    assert (observations(world, world.ann, unknown), stored_scope(world, unknown)) == ([], [de])

    # Positive controls: the member of every entity, and the narrowing to one named entity.
    everything = run_of(world, world.maya)
    assert sorted(observations(world, world.maya, everything)) == sorted([US_ORDER, DE_ORDER])
    assert stored_scope(world, everything) is None
    german = run_of(world, world.maya, entity="AVM-DE")
    assert observations(world, world.maya, german) == [DE_ORDER]
    assert stored_scope(world, german) == [de]
    american = run_of(world, world.uma)
    assert observations(world, world.uma, american) == [US_ORDER]
    assert stored_scope(world, american) == [us]
    # The scope is the requester's ``contract.read``, not the route's permission: Cleo's
    # ``ssp.create`` covers every entity and her run reads AVM-DE; Rolf's covers AVM-DE and his
    # run, with ``contract.read`` for every entity, reads both orders.
    cleos = run_of(world, world.cleo)
    assert (observations(world, world.cleo, cleos), stored_scope(world, cleos)) == (
        [DE_ORDER],
        [de],
    )
    rolfs = run_of(world, world.rolf)
    assert sorted(observations(world, world.rolf, rolfs)) == sorted([US_ORDER, DE_ORDER])
    assert stored_scope(world, rolfs) is None
    # The narrowing asks the permission too: Cleo's session reads AVM-US and her
    # ``contract.read`` does not cover it, so the filter narrows nothing and matches nothing.
    cleo_us = run_of(world, world.cleo, entity="AVM-US")
    assert (observations(world, world.cleo, cleo_us), stored_scope(world, cleo_us)) == ([], [de])
    # A requester who reads no contract starts no run, and the refusal is recorded.
    assert run_denials(world) == []
    body = run_body(world.base, None, source="committed_obligations")
    refused = post(app, RUNS, world.nora, body)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert run_denials(world) == [
        ("ssp_calculator_run.create", world.nora.member.user_id, {"permission": "contract.read"})
    ]

    # The run's book: one its requester may prepare a version of.
    only = post(
        app,
        SSP_BOOKS,
        world.maya,
        {"code": "A-US-ONLY", "name": "US only", "currency": "USD", "entity_code": "AVM-US"},
    )
    assert only.status_code == 201, only.text
    for book_id in (str(only.json()["id"]), NOBODY):
        body = run_body(world.base, None, source="committed_obligations", ssp_book_id=book_id)
        refused = post(app, RUNS, world.ann, body)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("parameters.ssp_book_id", "T-REF-32")]
    named = post(
        app,
        RUNS,
        world.uma,
        run_body(
            world.base, None, source="committed_obligations", ssp_book_id=str(only.json()["id"])
        ),
    )
    assert named.status_code == 202, named.text
    # The draft version needs the run AND its book. Rolf reads Uma's run — his
    # ``contract.read`` covers every entity — and the book of AVM-US is not his to prepare:
    # his command answers what it answers for an id that names no run. Uma's reaches the
    # command itself, which answers by the study: the book of AVM-US has no approved entry
    # that states the series product's value basis.
    work(world.base, UUID(named.json()["id"]), world.runtime)
    us_run = str(named.headers[RUN_ID_HEADER])
    assert observations(world, world.rolf, us_run) == [US_ORDER]
    draft = {"version_label": "2026-H2", "effective_from_date": "2026-10-01"}
    refused = post(app, f"{RUNS}/{us_run}/create-draft-version", world.rolf, draft)
    nobody = post(app, f"{RUNS}/{NOBODY}/create-draft-version", world.rolf, draft)
    assert (nobody.status_code, slug(nobody)) == (404, "not-found"), nobody.text
    assert told(refused) == told(nobody), refused.text
    made = post(app, f"{RUNS}/{us_run}/create-draft-version", world.uma, draft)
    assert (made.status_code, slug(made)) == (422, "validation-failed"), made.text
    assert made.json()["detail"].startswith("No draft version was created."), made.text


def test_ssp_entity_scope_1_a_run_is_read_and_commanded_within_its_scope(world: World) -> None:
    """The reads and the commands. Maya's run over AVM-US and her run of all entities are
    absent for Ann: neither is listed, and the run, its results, its observations, an exclusion
    and the draft version answer her 404, exactly as an id that names none. Uma, whose
    ``contract.read`` covers AVM-US, reads the run of AVM-US and makes the draft version from
    it; the run of all entities is absent for her too. Maya reads both. A run of AVM-DE alone —
    Maya's, narrowed by its filter — is read by Ann.

    Fail-first: Ann read Maya's run, its results and the order of AVM-US, and created a draft
    version from it."""
    app = world.app
    american = run_of(world, world.maya, entity="AVM-US")
    everything = run_of(world, world.maya)
    german = run_of(world, world.maya, entity="AVM-DE")
    assert runs_listed(world, world.ann) == {german}
    draft = {"version_label": "2026-H2", "effective_from_date": "2026-10-01"}

    def asked(actor: Actor, run_id: str) -> dict[str, HttpResponse]:
        return {
            "the run": get(app, f"{RUNS}/{run_id}", actor),
            "its results": get(app, f"{RUNS}/{run_id}/results", actor),
            "its observations": get(app, f"{RUNS}/{run_id}/observations", actor),
            "an exclusion": post(
                app,
                f"{RUNS}/{run_id}/exclusions",
                actor,
                {"source_reference": US_ORDER[0], "reason": "Not a standalone sale at all"},
            ),
            "the draft version": post(app, f"{RUNS}/{run_id}/create-draft-version", actor, draft),
        }

    unknown = asked(world.ann, NOBODY)
    for what, answer in unknown.items():
        assert (answer.status_code, slug(answer)) == (404, "not-found"), (what, answer.text)
    for run_id in (american, everything):
        for what, answer in asked(world.ann, run_id).items():
            assert told(answer) == told(unknown[what]), (what, answer.text)
    # Nothing moved: the run of AVM-US has its observation, no exclusion and no draft version.
    shown = get(app, f"{RUNS}/{american}", world.maya).json()
    assert (shown["observation_count"], shown["draft_ssp_book_version_id"]) == (1, None)
    assert observations(world, world.maya, american) == [US_ORDER]

    # Positive controls. The run of her own entity is hers to read ...
    assert observations(world, world.ann, german) == [DE_ORDER]
    # ... the member of AVM-US reads the run of AVM-US and prepares the draft version from it,
    # and the run of all entities is as absent for her as for Ann ...
    assert runs_listed(world, world.uma) == {american}
    assert observations(world, world.uma, american) == [US_ORDER]
    assert told(get(app, f"{RUNS}/{everything}", world.uma)) == told(unknown["the run"])
    created = post(app, f"{RUNS}/{american}/create-draft-version", world.uma, draft)
    assert created.status_code == 201, created.text
    # ... and the member of every entity reads all three.
    assert runs_listed(world, world.maya) == {american, everything, german}
    # The reader is held to ``contract.read``, under the route's ``ssp.read``. Cleo's
    # ``ssp.read`` covers every entity and her ``contract.read`` AVM-DE: the runs over AVM-US
    # and over every entity are absent for her. Rolf's ``ssp.read`` covers AVM-DE and his
    # ``contract.read`` every entity: he reads all three.
    assert runs_listed(world, world.cleo) == {german}
    for run_id in (american, everything):
        assert told(get(app, f"{RUNS}/{run_id}", world.cleo)) == told(
            get(app, f"{RUNS}/{NOBODY}", world.cleo)
        )
    assert observations(world, world.cleo, german) == [DE_ORDER]
    assert runs_listed(world, world.rolf) == {american, everything, german}
    assert sorted(observations(world, world.rolf, everything)) == sorted([US_ORDER, DE_ORDER])
