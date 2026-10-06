"""API-R-29 Obligations (04 §15.3 API-R-29, §16.2 API-S-Obligation, API-S-ScheduleLine, §16.3
API-S-Event, API-C-10; PRD WLD-K-02, WLD-K-11, WLD-X-22; BUILD_SPEC CTR-15).

Worlds: ``support.factories.k11_world`` (PRD §2.6 for K-11: booked, activated as SYSTEM, 120 O1
units delivered effective 2026-09-12, computed) and ``support.factories.k02_world`` (PRD §2.6 for
K-02: ``SF-ORD-10002``, AVM-SEAT-MO for 240,000.00 USD from 1 Jan 2026 to 31 Dec 2027). Maya
(Revenue Accountant) reads with ``contract.read``. The frozen clock reads 2026-09-12T12:00Z.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_version, obligation
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    K02World,
    K11World,
    activated_contract,
    booked_contract,
    computed,
    delivered_k11,
    k02_seat_month_body,
    k02_world,
    k11_world,
)
from support.reference import get

OBLIGATIONS = "/api/v1/obligations"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _obligation_id(world: K11World | K02World, contract_id: UUID, key: str) -> UUID:
    statement = select(obligation.c.id).where(
        obligation.c.contract_id == contract_id, obligation.c.obligation_key == key
    )
    return UUID(str(world.place.scalar(statement)))


def test_obligation_read_model_k11_o1(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k11_world(app, keyring, clock, files)
    booked = delivered_k11(world)
    computed(world.place, booked.combination_group["id"])
    contract_id = booked.contract["id"]
    o1 = _obligation_id(world, contract_id, "O1")
    maya = world.place.author

    shown = get(app, f"{OBLIGATIONS}/{o1}", maya)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert (body["id"], body["contract_id"], body["obligation_key"]) == (
        str(o1),
        str(contract_id),
        "O1",
    )
    # PRD WLD-X-22: 108,000.00 × 90,000 ÷ 109,000; the range 405 / 450 / 495 per unit × 200 units.
    assert body["current"]["allocated_amount"] == {"amount": "89174.31", "currency": "EUR"}
    original = body["original"]
    assert tuple(Decimal(original[name]) for name in ("ssp_low", "ssp_mid", "ssp_high")) == (
        Decimal("81000"),
        Decimal("90000"),
        Decimal("99000"),
    )
    assert (body["ssp"]["range_position"], body["ssp"]["outside_range_point"]) == ("INSIDE", None)
    assert (body["performing_entity"]["code"], body["performing_entity"]["id"]) == (
        "AVM-DE",
        str(world.entity_id),
    )
    assert body["context"]["book"] == "ASC606"
    assert body["links"]["self"] == f"/api/v1/obligations/{o1}"

    listed = get(app, f"/api/v1/contracts/{contract_id}/obligations", maya)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [
        (item["obligation_key"], item["current"]["allocated_amount"]["amount"]) for item in items
    ] == [("O1", "89174.31"), ("O2", "18825.69")]

    events = get(app, f"{OBLIGATIONS}/{o1}/events", maya)
    assert events.status_code == 200, events.text
    named = events.json()["items"]
    assert named and all("O1" in item["obligation_keys"] for item in named)
    (delivery,) = [item for item in named if item["event_type"] == "DELIVERY_RECORDED"]
    assert Decimal(delivery["payload"]["quantity"]) == Decimal("120")
    assert delivery["created_by"]["kind"] == "USER"
    assert delivery["computation"] is not None
    assert delivery["computation"]["status"] == "SUCCEEDED"

    assert get(app, f"{OBLIGATIONS}/{o1}/material-right", maya).status_code == 404
    assert get(app, f"{OBLIGATIONS}/{uuid4()}", maya).status_code == 404
    assert get(
        app, f"{OBLIGATIONS}/{o1}", maya, {"known_at": "2026-09-12T12:00:00"}
    ).status_code == (422)


def test_obligation_schedule_and_versions(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k02_world(app, keyring, clock, files)
    maya = world.place.author
    booked = booked_contract(world.place, k02_seat_month_body(world.customer_id), activate=False)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)  # the provisional version of the draft
    # CTR-9's factory computes on activation unless told not to (L4-1-Q-21); this test computes
    # the activated version itself, so the group holds exactly two versions.
    booked = activated_contract(world.place, booked, compute=False)
    computed(world.place, group_id)
    o1 = _obligation_id(world, booked.contract["id"], "O1")

    schedule = get(app, f"{OBLIGATIONS}/{o1}/schedule", maya, {"limit": 100})
    assert schedule.status_code == 200, schedule.text
    lines = {item["period"]["period_key"]: item for item in schedule.json()["items"]}
    assert lines and all(item["obligation_key"] == "O1" for item in lines.values())
    september = lines["FY2026-P09"]
    # 240,000.00 × 273 ÷ 730 − 240,000.00 × 243 ÷ 730, cumulatively rounded. 04 API-S-ScheduleLine
    # rev 1.132 (supervisor rulings R-76 (b), R-79 (f)): the activated version's computation posted
    # September, so the ledger holds a REVENUE line of the contract, obligation and period and the
    # line reads RECOGNIZED; October, past the horizon, has none.
    assert (september["amount"], september["state"]) == (
        {"amount": "9863.01", "currency": "USD"},
        "RECOGNIZED",
    )
    assert lines["FY2026-P10"]["state"] == "SCHEDULED"

    versions = get(app, f"{OBLIGATIONS}/{o1}/versions", maya)
    assert versions.status_code == 200, versions.text
    stored = world.place.rows(
        select(contract_version.c.id, contract_version.c.version_no)
        .where(
            contract_version.c.combination_group_id == group_id,
            contract_version.c.book_code == "ASC606",
        )
        .order_by(contract_version.c.version_no.desc())
    )
    assert len(stored) == 2
    assert [
        (
            item["obligation_key"],
            item["context"]["contract_version_id"],
            item["context"]["version_no"],
        )
        for item in versions.json()["items"]
    ] == [("O1", str(row["id"]), row["version_no"]) for row in stored]
