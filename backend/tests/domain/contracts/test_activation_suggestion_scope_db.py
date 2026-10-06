"""What the activation checklist tells the reader of ONE contract of an open combination
suggestion (item ACT-CHECKLIST-SUGGESTION-SCOPE-1; the supervisor's rulings of 2026-10-02 on
finding C-1 of lane F-RPS-REG; 03 REQ-PLT-012, REQ-CON-010; 04 table 15.4-I
``COMBINATION_SUGGESTIONS``, §16.1 ``submit-activation``; PRD BR-CON-03, BR-DAT-06, IMP-103,
ERR-31).

A suggestion to combine contracts of two contracting entities is stored without an entity, so its
item is in the session of every reader of either contract. Who lists it and who ends it is a
member who reads every contract it names (item EXC-IMPORT-SCOPE-1). The checklist of each
contract still counts it — one line for each open suggestion — and that line named the other
contract by its external id to every reader.

- Read by a session — the checklist's read and the 409 of ``submit-activation`` — the line names
  the other contract to a session that reads it and says "a contract outside your entities" to
  any other.
- Stored — a Contract Setup commit whose activation checklist fails keeps the lines as the
  message of an exception item of the contract's entity — the line has readers, not a session:
  it names the other contract only when that contract is of the contract's own contracting
  entity and says "a contract of another entity" otherwise.

Measured before the item. In the first world: Dee, whose ``GET`` of the Austrian order answers
404, read "Combination suggestion with NS-SO-AT-5001 is open." in the checklist of the German
order and in the 409 of its ``submit-activation``; Ana read "... with NS-SO-DE-5004 is open." of
the Austrian order in both. In the second: Olga, Revenue Accountant of Mock Entity 1 alone, read
the external id of an order of Mock Entity 2 in the message of the commit's item.

Worlds.
- ``pair``: ``support.factories.k11_world`` (AVM-DE, EUR) with the related-party group
  HOLLENBRAND of ``test_combination`` and two more entities on the same calendar, AVM-AT and
  AVM-CH. K-11 ``NS-SO-DE-5004`` (2026-09-01) is booked for AVM-DE and left DRAFT;
  ``NS-SO-AT-5001`` (2026-09-03) is created for AVM-AT through ``POST /contracts``, which raises
  the suggestion. Maya is Revenue Accountant of all entities, Dee of AVM-DE alone, Ana of AVM-AT
  alone, Bea of AVM-DE and AVM-AT.
- The stored line: ``support.legacy_replay.legacy_world`` without the legacy preset (under it no
  suggestion is raised). The first two rows of "Contract 1" are committed with
  ``activate_on_approval`` false: a DRAFT of Mock Entity 1. Maya books two more orders of the same
  customer through ``POST /contracts``, one for Mock Entity 2 and one for Mock Entity 1; the
  remaining rows of "Contract 1" are then committed with activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_event, exception_item, legal_entity
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    K11World,
    booked_contract,
    k11_body,
    k11_world,
    open_periods,
    workbook_bytes,
)
from support.legacy_replay import SETUP_2023, SKU_SSP, committed, legacy_world, workbook_rows
from support.principals import Actor, colleague, enrolled
from support.reference import assign, entity, get, holding, post
from tests.domain.contracts.test_combination import _hollenbrand, _k05

SUGGESTIONS: Final = "/api/v1/combination-suggestions"
CONTRACTS: Final = "/api/v1/contracts"
EXCEPTIONS: Final = "/api/v1/exceptions"
CODE: Final = "COMBINATION_SUGGESTIONS"
DE_ORDER: Final = "NS-SO-DE-5004"  # K-11, AVM-DE, inception 2026-09-01
AT_ORDER: Final = "NS-SO-AT-5001"  # AVM-AT, inception 2026-09-03
OUTSIDE: Final = "Combination suggestion with a contract outside your entities is open."
ANOTHER: Final = "Combination suggestion with a contract of another entity is open."
PERIODS: Final = [f"FY2026-P{month:02d}" for month in range(1, 10)]
SETUP_ORDER: Final = "Contract 1"  # Mock Entity 1 in the setup file
OTHER_ENTITY_ORDER: Final = "Contract 1 - order of the other entity"
SAME_ENTITY_ORDER: Final = "Contract 1 - order of the same entity"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@dataclass(frozen=True, slots=True)
class Pair:
    """The open suggestion of ``DE_ORDER`` and ``AT_ORDER`` with the readers of the tests."""

    world: K11World
    de_contract: UUID
    at_contract: UUID
    maya: Actor  # all entities
    dee: Actor  # AVM-DE
    ana: Actor  # AVM-AT
    bea: Actor  # AVM-DE and AVM-AT

    @property
    def app(self) -> FastAPI:
        return self.world.app


@pytest.fixture
def pair(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Pair:
    world = k11_world(app, keyring, clock, files)
    maya = world.place.author
    buyer = _hollenbrand(world)
    calendar_id = str(
        world.place.scalar(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
    )
    ids = {"AVM-DE": world.entity_id}
    for code, zone in (("AVM-AT", "Europe/Vienna"), ("AVM-CH", "Europe/Zurich")):
        created = entity(
            app, maya, code=code, calendar_id=calendar_id, functional_currency="EUR", time_zone=zone
        )
        ids[code] = UUID(str(created["id"]))
    open_periods(app, maya, entity_code="AVM-AT", keys=PERIODS)

    german = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    austrian = post(
        app,
        CONTRACTS,
        maya,
        {**_k05(buyer), "external_id": AT_ORDER, "contracting_entity_code": "AVM-AT"},
    )
    assert austrian.status_code == 201, austrian.text
    (item,) = world.place.rows(
        select(exception_item).where(exception_item.c.code == "COMBINATION_SUGGESTED")
    )
    assert item["entity_id"] is None  # a pair of two contracting entities carries none

    def member(name: str, *codes: str) -> Actor:
        someone = colleague(world.place.tenant_id, name)
        return holding(app, someone, "revenue_accountant", entity_ids=[ids[code] for code in codes])

    return Pair(
        world=world,
        de_contract=UUID(str(german.contract["id"])),
        at_contract=UUID(str(austrian.json()["id"])),
        maya=maya,
        dee=member("dee", "AVM-DE"),
        ana=member("ana", "AVM-AT"),
        bea=member("bea", "AVM-DE", "AVM-AT"),
    )


def naming(external_id: str) -> str:
    return f"Combination suggestion with {external_id} is open."


def checklist_line(app: FastAPI, actor: Actor, contract_id: UUID) -> tuple[bool, str | None]:
    """The ``COMBINATION_SUGGESTIONS`` item of ``GET /contracts/{id}/activation-checklist``."""
    shown = get(app, f"{CONTRACTS}/{contract_id}/activation-checklist", actor)
    assert shown.status_code == 200, shown.text
    (item,) = [found for found in shown.json()["items"] if found["code"] == CODE]
    return item["passed"], item["detail"]


def refused_line(pair: Pair, actor: Actor, contract_id: UUID) -> str:
    """The message of ``COMBINATION_SUGGESTIONS`` in the 409 of ``submit-activation``."""
    shown = get(pair.app, f"{CONTRACTS}/{contract_id}", actor)
    assert shown.status_code == 200, shown.text
    head = shown.json()["head_stream_version"]
    refused = post(
        pair.app, f"{CONTRACTS}/{contract_id}/submit-activation", actor, {}, if_match=f'"s{head}"'
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["type"].endswith("/activation-checklist-failed"), body
    assert CODE in body["detail"], body["detail"]  # ERR-31 counts the item among those failed
    (message,) = [error["message"] for error in body["errors"] if error["rule_id"] == CODE]
    return str(message)


def unread(pair: Pair, actor: Actor, contract_id: UUID) -> None:
    """The precondition of each case: the other contract is not ``actor``'s to read, and the
    suggestion is not listed for her — she can neither accept nor dismiss it."""
    assert get(pair.app, f"{CONTRACTS}/{contract_id}", actor).status_code == 404
    listed = get(pair.app, SUGGESTIONS, actor)
    assert listed.status_code == 200 and listed.json()["items"] == [], listed.text


@pytest.mark.slow
def test_the_checklist_names_the_other_contract_of_a_suggestion_to_a_session_that_reads_it(
    pair: Pair,
) -> None:
    """``GET /contracts/{id}/activation-checklist``. Dee reads the German order and not the
    Austrian one: the item fails with one line, and the line says "a contract outside your
    entities" where the external id stood; Ana, on the Austrian order, the mirror. Bea, who holds
    her role for both entities, and Maya, who holds it for all, are told the id as before.
    Before: "Combination suggestion with NS-SO-AT-5001 is open." for Dee."""
    unread(pair, pair.dee, pair.at_contract)
    unread(pair, pair.ana, pair.de_contract)

    assert checklist_line(pair.app, pair.dee, pair.de_contract) == (False, OUTSIDE)
    assert checklist_line(pair.app, pair.ana, pair.at_contract) == (False, OUTSIDE)
    assert checklist_line(pair.app, pair.bea, pair.de_contract) == (False, naming(AT_ORDER))
    assert checklist_line(pair.app, pair.bea, pair.at_contract) == (False, naming(DE_ORDER))
    assert checklist_line(pair.app, pair.maya, pair.de_contract) == (False, naming(AT_ORDER))
    assert checklist_line(pair.app, pair.maya, pair.at_contract) == (False, naming(DE_ORDER))

    # nothing of the other order in the whole answer of either reader of one
    whole = get(pair.app, f"{CONTRACTS}/{pair.de_contract}/activation-checklist", pair.dee).text
    assert AT_ORDER not in whole and str(pair.at_contract) not in whole
    whole = get(pair.app, f"{CONTRACTS}/{pair.at_contract}/activation-checklist", pair.ana).text
    assert DE_ORDER not in whole and str(pair.de_contract) not in whole


@pytest.mark.slow
def test_the_409_of_submit_activation_names_the_other_contract_to_a_session_that_reads_it(
    pair: Pair,
) -> None:
    """``POST /contracts/{id}/submit-activation`` answers 409 ``activation-checklist-failed`` while
    the suggestion is open, and its ``errors[]`` carry the checklist's line under ``rule_id``
    ``COMBINATION_SUGGESTIONS``: "a contract outside your entities" for Dee and for Ana, the
    external id for Bea and Maya. Nothing is submitted: both orders stay DRAFT. Before:
    "Combination suggestion with NS-SO-AT-5001 is open." in Dee's 409."""
    unread(pair, pair.dee, pair.at_contract)
    unread(pair, pair.ana, pair.de_contract)

    assert refused_line(pair, pair.dee, pair.de_contract) == OUTSIDE
    assert refused_line(pair, pair.ana, pair.at_contract) == OUTSIDE
    assert refused_line(pair, pair.bea, pair.de_contract) == naming(AT_ORDER)
    assert refused_line(pair, pair.bea, pair.at_contract) == naming(DE_ORDER)
    assert refused_line(pair, pair.maya, pair.de_contract) == naming(AT_ORDER)
    assert refused_line(pair, pair.maya, pair.at_contract) == naming(DE_ORDER)

    statuses = {
        str(row["external_id"]): str(row["status"])
        for row in pair.world.place.rows(select(contract.c.external_id, contract.c.status))
    }
    assert statuses == {DE_ORDER: "DRAFT", AT_ORDER: "DRAFT"}


@pytest.mark.slow
def test_a_stored_line_names_the_other_contract_only_inside_the_contracts_own_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A Contract Setup commit whose activation checklist fails keeps the contract DRAFT and
    stores the failed lines as the message of an exception item of the contract's entity
    (BR-DAT-06). The commit runs as SYSTEM, which reads every contract, and the message is read
    by the members of that entity: the line of the suggestion with the order of Mock Entity 2
    says "a contract of another entity", the line of the suggestion with the order of Mock
    Entity 1 names it. Olga, of Mock Entity 1 alone, and Maya, of all entities, read the same
    stored message; Maya finds the other entity's order on the checklist itself, Olga does not.
    Before: the message named "Contract 1 - order of the other entity" to Olga, whose ``GET`` of
    that order answers 404."""
    legacy = legacy_world(app, keyring, clock, files, preset=False)
    maya = legacy.maya
    rows_of = legacy.imports.rows
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    headers, rows = workbook_rows(SETUP_2023)
    lines = [row for row in rows if row[0] == SETUP_ORDER]
    committed(
        legacy,
        "Contract 1 part 1.xlsx",
        workbook_bytes("Sheet1", headers, lines[:2]),
        "legacy_contract_setup",
        {"activate_on_approval": False},
    )
    (draft,) = rows_of(select(contract).where(contract.c.external_id == SETUP_ORDER))
    assert str(draft["status"]) == "DRAFT"
    entities = {
        UUID(str(row["id"])): str(row["code"])
        for row in rows_of(select(legal_entity.c.id, legal_entity.c.code))
    }
    own_id = UUID(str(draft["contracting_entity_id"]))
    (other_code,) = [code for found, code in entities.items() if found != own_id]
    (booking,) = rows_of(
        select(contract_event.c.payload)
        .where(
            contract_event.c.contract_id == draft["id"],
            contract_event.c.event_type == "CONTRACT_BOOKED",
        )
        .order_by(contract_event.c.stream_version.desc())
        .limit(1)
    )
    booked: dict[str, Any] = {
        key: value for key, value in dict(booking["payload"]).items() if key != "document_ref"
    }
    sisters: dict[str, UUID] = {}
    for external_id, entity_code in (
        (OTHER_ENTITY_ORDER, other_code),
        (SAME_ENTITY_ORDER, entities[own_id]),
    ):
        created = post(
            app,
            CONTRACTS,
            maya,
            {**booked, "external_id": external_id, "contracting_entity_code": entity_code},
        )
        assert created.status_code == 201, created.text
        sisters[external_id] = UUID(str(created.json()["id"]))

    done = committed(
        legacy,
        "Contract 1 part 2.xlsx",
        workbook_bytes("Sheet1", headers, lines[2:]),
        "legacy_contract_setup",
    )
    (after,) = rows_of(select(contract.c.status).where(contract.c.external_id == SETUP_ORDER))
    assert str(after["status"]) == "DRAFT"  # the checklist failed: nothing was activated
    (item,) = rows_of(
        select(exception_item).where(exception_item.c.import_upload_id == UUID(str(done["id"])))
    )
    assert (item["contract_id"], item["entity_id"]) == (draft["id"], own_id)
    stored = str(item["message"])
    assert stored.endswith(f"{ANOTHER} {naming(SAME_ENTITY_ORDER)}"), stored
    assert OTHER_ENTITY_ORDER not in stored

    someone = colleague(legacy.tenant_id, "olga")
    assign(someone, "revenue_accountant", entity_ids=[own_id])
    olga = enrolled(app, clock, someone)
    assert get(app, f"{CONTRACTS}/{sisters[OTHER_ENTITY_ORDER]}", olga).status_code == 404
    assert get(app, f"{CONTRACTS}/{sisters[SAME_ENTITY_ORDER]}", olga).status_code == 200
    for reader in (olga, maya):
        read = get(app, f"{EXCEPTIONS}/{item['id']}", reader)
        assert read.status_code == 200, read.text
        assert read.json()["message"] == stored
    listed = get(app, EXCEPTIONS, olga, {"limit": "200"})
    assert listed.status_code == 200, listed.text
    assert OTHER_ENTITY_ORDER not in listed.text

    # the checklist itself, read by a session: the id for the member who reads both contracts
    contract_id = UUID(str(draft["id"]))
    assert checklist_line(app, maya, contract_id) == (
        False,
        f"{naming(OTHER_ENTITY_ORDER)} {naming(SAME_ENTITY_ORDER)}",
    )
    assert checklist_line(app, olga, contract_id) == (
        False,
        f"{OUTSIDE} {naming(SAME_ENTITY_ORDER)}",
    )
