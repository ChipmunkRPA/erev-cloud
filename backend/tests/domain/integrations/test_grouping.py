"""DIN-10 ingestion grouping policy (ENGINE_SPEC §2.4 S02-R-13; 04 T-PLT-31
``integration.grouping_fields``, T-SRC-02 ``grouping_values``, T-CON-02; 05 §5.1 ADP-05; SCREENS_B
§9.6; 03 REQ-CON-011; BUILD_SPEC DIN-10).

Worlds: ``support.factories.j03_world`` (AVM-US, USD, customer C-12, AVM-PLAT-100) for the orders,
normalised as an adapter normalises them after ``store_source_record``; ``import_world`` (a Revenue
Accountant, ``config.author``) for the tenant setting.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_event, contract_source_link, source_order
from erev_api.domain.integrations import grouping
from erev_api.domain.integrations.normalise import SourceIdentity, store_source_record
from erev_api.enums import SourceObjectType, SourceSystem
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import PLATFORM_100, J03World, import_world, j03_world
from support.reference import post, slug

POLICIES = "/api/v1/policies"
SIX_FIELDS = [
    "order_number",
    "customer_external_id",
    "legal_entity_code",
    "transaction_currency",
    "po_number",
    "document_ref",
]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _order(world: J03World, number: str, external_order_id: str) -> grouping.NormalisedOrder:
    """A Salesforce order stored as its source record, then normalised (S01-R-01; T-SRC-02)."""
    identity = SourceIdentity(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id=external_order_id,
        external_version="1",
    )
    with world.place.uow() as uow:
        stored = store_source_record(
            uow,
            identity=identity,
            version_order=1,
            payload={"OrderNumber": number, "Id": external_order_id},
        )
        uow.commit()
    return grouping.NormalisedOrder(
        source_record_id=stored.id,
        source_system=SourceSystem.SALESFORCE,
        external_order_id=external_order_id,
        external_version="1",
        order_number=number,
        order_date=date(2026, 3, 1),
        customer_external_id="C-12",
        customer_id=world.customer_id,
        legal_entity_code="AVM-US",
        transaction_currency="USD",
        lines=(
            grouping.OrderLine(
                line_external_id="O1",
                product_code=PLATFORM_100,
                quantity=Decimal(1),
                total_price=Decimal("100000.00"),
                start_date=date(2026, 3, 1),
                end_date=date(2027, 2, 28),
            ),
        ),
    )


def _ingested(world: J03World, order: grouping.NormalisedOrder) -> grouping.Routed:
    with world.place.uow() as uow:
        routed = grouping.ingest_order(uow, order)
        uow.commit()
    return routed


def _contracts(world: J03World) -> list[dict[str, Any]]:
    return world.place.rows(
        select(
            contract.c.id, contract.c.external_id, contract.c.status, contract.c.head_stream_version
        ).order_by(contract.c.external_id)
    )


def test_same_grouping_key_becomes_candidate_modification(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = j03_world(app, keyring, clock, files)
    first = _ingested(world, _order(world, "SF-ORD-30417", "801A00000000001"))
    assert (first.outcome, first.grouping_key) == (
        grouping.GroupingOutcome.NEW_CONTRACT,
        '["SF-ORD-30417"]',
    )
    (booked,) = _contracts(world)
    # A new order number creates a contract whose external id is the order number (S02-R-13).
    assert (booked["id"], booked["external_id"], str(booked["status"])) == (
        first.contract_id,
        "SF-ORD-30417",
        "DRAFT",
    )
    (event,) = world.place.rows(
        select(contract_event.c.origin, contract_event.c.source_record_id).where(
            contract_event.c.contract_id == first.contract_id
        )
    )
    assert str(event["origin"]) == "ADAPTER"
    (stored,) = world.place.rows(
        select(source_order.c.grouping_values).where(source_order.c.id == first.source_order_id)
    )
    assert stored["grouping_values"] == {"order_number": "SF-ORD-30417"}

    # integration.grouping_fields = ["order_number"] (the T-PLT-31 default): an order with the same
    # number is a candidate modification of that contract (ADP-05) and books nothing.
    second = _ingested(world, _order(world, "SF-ORD-30417", "801A00000000002"))
    assert (second.outcome, second.contract_id, second.event_id) == (
        grouping.GroupingOutcome.CANDIDATE_MODIFICATION,
        first.contract_id,
        None,
    )
    assert _contracts(world) == [booked]
    links = world.place.rows(
        select(func.count())
        .select_from(contract_source_link)
        .where(contract_source_link.c.contract_id == first.contract_id)
    )
    assert links == [{"count_1": 1}]
    # [J] L6-1-Q-6: the DRAFT modification row waits for BUILD_SPEC CTR-17 (T-CON-06).

    third = _ingested(world, _order(world, "SF-ORD-30418", "801A00000000003"))
    assert third.outcome is grouping.GroupingOutcome.NEW_CONTRACT
    assert [row["external_id"] for row in _contracts(world)] == ["SF-ORD-30417", "SF-ORD-30418"]


def test_at_most_five_grouping_fields(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = import_world(app, keyring, clock, files)
    body = {"category": "INTEGRATION", "scope": "TENANT", "values": {grouping.SETTING: SIX_FIELDS}}
    refused = post(app, POLICIES, world.actor, body)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert refused.json()["detail"] == "Choose at most five fields."
    assert [(error["field"], error["rule_id"]) for error in refused.json()["errors"]] == [
        ("values.integration.grouping_fields", "POLICY_VALUE_INVALID")
    ]
    five = {**body, "values": {grouping.SETTING: SIX_FIELDS[:5]}}
    accepted = post(app, POLICIES, world.actor, five)
    assert accepted.status_code == 201, accepted.text
    assert UUID(accepted.json()["id"])
