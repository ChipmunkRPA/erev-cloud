"""API-R-35 schedule lines (04 §15.3 API-R-35, §16.2 API-S-ScheduleLine, API-C-10; PRD WLD-X-05;
BUILD_SPEC CTR-5).

World: ``support.factories.seat_world`` (PRD §2.6 for K-02): ``SF-ORD-10002`` O1 AVM-SEAT-MO,
240,000.00 USD from 01 Jan 2026 to 31 Dec 2027 (730 days, TPL-SUB-DAILY), booked, activated as the
SYSTEM principal and computed. Maya reads with ``contract.read``.
"""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    activated_contract,
    booked_contract,
    computed,
    k02_body,
    k09_body,
    seat_world,
)
from support.reference import fields, get

LINES = "/api/v1/schedule-lines"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> SeatWorld:
    return seat_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def test_schedule_lines_k02(world: SeatWorld) -> None:
    k02 = activated_contract(
        world.place, booked_contract(world.place, k02_body(world.customers["C-02"]), activate=False)
    )
    computed(world.place, k02.combination_group["id"])
    k09 = activated_contract(
        world.place, booked_contract(world.place, k09_body(world.customers["C-09"]), activate=False)
    )
    computed(world.place, k09.combination_group["id"])
    response = get(
        world.app,
        LINES,
        world.place.author,
        {
            "contract": str(k02.contract["id"]),
            "schedule_kind": "REVENUE",
            "from_period": "FY2026-P09",
            "to_period": "FY2026-P10",
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [
        (
            item["period"]["period_key"],
            item["obligation_key"],
            item["schedule_kind"],
            item["amount"],
            item["entity"]["code"],
        )
        for item in items
    ] == [
        ("FY2026-P09", "O1", "REVENUE", {"amount": "9863.01", "currency": "USD"}, "AVM-US"),
        ("FY2026-P10", "O1", "REVENUE", {"amount": "10191.79", "currency": "USD"}, "AVM-US"),
    ]

    # Without a contract, both contracts' September lines; the entity code filter matches them.
    both = get(
        world.app,
        LINES,
        world.place.author,
        {
            "schedule_kind": "REVENUE",
            "entity": "AVM-US",
            "from_period": "FY2026-P09",
            "to_period": "FY2026-P09",
            "obligation": "O1",
        },
    )
    assert both.status_code == 200, both.text
    assert sorted(item["amount"]["amount"] for item in both.json()["items"]) == [
        "2956.20",
        "9863.01",
    ]
    unknown = get(world.app, LINES, world.place.author, {"known_at": "2026-09-12T12:00:00"})
    assert unknown.status_code == 422, unknown.text
    assert fields(unknown) == [("known_at", "API-C-09")]
