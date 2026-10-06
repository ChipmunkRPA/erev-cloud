"""Contract time-travel reads (04 §15.1 API-C-09, API-C-10, §16.1 API-S-ContractVersion,
API-S-ContractBalance, §16.2 API-S-ScheduleLine; 03 REQ-PLT-030, REQ-CON-014; PRD WLD-X-23;
BUILD_SPEC CTR-4).

The world is ``support.factories.j03_world``; ``SF-ORD-20417`` is created and its draft replaced
through the routes, computing through ``support.factories.engine()`` (V-C). ``known_at`` is a record
instant: versions carry the ``recorded_at`` of their events, which the database stamps (DB-08), so
the instant between the two commands is read from the database clock.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.contracts import computation
from erev_api.enums import ContractEventType
from erev_api.events.payloads import ChecklistItemV1, ContractActivatedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import J03World, computed, engine, j03_world, sf_ord_20417_body
from support.reference import fields, get, post, slug

CONTRACTS = "/api/v1/contracts"


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> J03World:
    monkeypatch.setattr(computation, "default_engine", engine)
    return j03_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def booked_and_replaced(world: J03World) -> tuple[dict[str, Any], str, str]:
    """(the created contract, an instant before its booking, an instant between the booking and
    its replacement)."""
    before = world.place.scalar(select(func.now())).isoformat()
    created = post(world.app, CONTRACTS, world.place.author, sf_ord_20417_body(world.customer_id))
    assert created.status_code == 201, created.text
    between = world.place.scalar(select(func.now())).isoformat()
    body = created.json()
    changed = post(
        world.app,
        f"{CONTRACTS}/{body['id']}/replace-draft",
        world.place.author,
        sf_ord_20417_body(world.customer_id, implementation_price="26000.00"),
        if_match='"s1"',
    )
    assert changed.status_code == 200, changed.text
    return body, before, between


def scheduled_contract(world: J03World) -> dict[str, Any]:
    """SF-ORD-20422: O1 of SF-ORD-20417 alone (AVM-PLAT-100 96,000.00 from 01 Sep 2026 to 31 Aug
    2027), booked through the route, activated as the SYSTEM principal (BS3-D-19) and computed
    through ``support.factories.computed``. The TPL-SVC-HOURS line is left out: an active
    ``LABOUR_HOURS`` obligation needs a measure of progress the rc engine does not build
    (L3-1-Q-45)."""
    body = sf_ord_20417_body(world.customer_id, external_id="SF-ORD-20422")
    body["lines"] = body["lines"][:1]
    created = post(world.app, CONTRACTS, world.place.author, body)
    assert created.status_code == 201, created.text
    booked: dict[str, Any] = created.json()
    with world.place.uow(system_principal(world.place.tenant_id)) as uow:
        append_events(
            uow,
            contract_id=UUID(booked["id"]),
            expected_stream_version=1,
            events=[
                EventIn(
                    event_type=ContractEventType.CONTRACT_ACTIVATED,
                    effective_date=date(2026, 9, 1),
                    payload=ContractActivatedV1(
                        checklist=(ChecklistItemV1(code="SOURCE_REFERENCE", passed=True),)
                    ),
                )
            ],
            origin="SYSTEM",
        )
        uow.commit()
    computed(world.place, UUID(booked["combination_group"]["id"]))
    return booked


def test_known_at_returns_earlier_version(world: J03World) -> None:
    maya = world.place.author
    booked, before, between = booked_and_replaced(world)
    path = f"{CONTRACTS}/{booked['id']}"
    earlier = get(world.app, path, maya, {"known_at": between})
    assert earlier.status_code == 200, earlier.text
    assert (
        earlier.json()["context"]["version_no"],
        earlier.json()["kpis"]["transaction_price"],
    ) == (
        1,
        usd("120000.00"),
    )
    latest = get(world.app, path, maya)
    assert (latest.json()["context"]["version_no"], latest.json()["kpis"]["transaction_price"]) == (
        2,
        usd("122000.00"),
    )
    # API-C-08: the ETag names the current head whatever the record cut-off.
    assert earlier.headers["ETag"] == latest.headers["ETag"] == '"s3"'
    none_yet = get(world.app, path, maya, {"known_at": before}).json()
    assert (none_yet["context"], none_yet["kpis"]) == (None, None)
    assert [step["state"] for step in none_yet["steps"]] == [
        "COMPLETE",
        "NOT_STARTED",
        "NOT_STARTED",
        "NOT_STARTED",
        "NOT_STARTED",
    ]
    naive = get(world.app, path, maya, {"known_at": "2026-09-12T12:00:00"})
    assert (naive.status_code, fields(naive)) == (422, [("known_at", "API-C-09")]), naive.text
    # API-C-10: as_of bounds the schedule at the period that contains it. Schedules exist once the
    # contract is active (REQ-CON-002), so the figures are read from an activated contract.
    active = scheduled_contract(world)
    schedule_path = f"{CONTRACTS}/{active['id']}/schedule"
    unbounded = get(world.app, schedule_path, maya, {"limit": "500"})
    assert unbounded.status_code == 200, unbounded.text
    o1 = [item for item in unbounded.json()["items"] if item["obligation_key"] == "O1"]
    assert (len(o1), o1[0]["period"]["period_key"], o1[-1]["period"]["period_key"]) == (
        12,
        "FY2026-P09",
        "FY2027-P08",
    )
    assert o1[-1]["cumulative_amount"] == usd("96000.00")
    bounded = get(world.app, schedule_path, maya, {"as_of": "2026-09-15", "limit": "500"})
    assert bounded.status_code == 200, bounded.text
    items = bounded.json()["items"]
    assert {item["period"]["period_key"] for item in items} == {"FY2026-P09"}
    (september,) = [item for item in items if item["obligation_key"] == "O1"]
    assert (
        september["amount"],
        september["cumulative_amount"],
        september["period"]["end_date"],
        september["state"],
        september["schedule_kind"],
        september["entity"]["code"],
    ) == (usd("7890.41"), usd("7890.41"), "2026-09-30", "RECOGNIZED", "REVENUE", "AVM-US")
    # 04 API-S-ScheduleLine rev 1.132 (supervisor rulings R-76 (b), R-79 (f)): the state is read
    # from the ledger line of the contract, obligation, period and REVENUE role. The activation's
    # computation posted September, the open period; the ledger holds nothing of a later one.
    assert [item["state"] for item in o1] == ["RECOGNIZED", *["SCHEDULED"] * 11]
    # Before activation the provisional version holds no schedule (REQ-CON-002).
    draft = get(world.app, f"{path}/schedule", maya, {"known_at": between})
    assert (draft.status_code, draft.json()["items"]) == (200, []), draft.text


def test_versions_versions_detail_and_balances(world: J03World) -> None:
    maya = world.place.author
    booked, _, _ = booked_and_replaced(world)
    path = f"{CONTRACTS}/{booked['id']}"
    listed = get(world.app, f"{path}/versions", maya)
    assert listed.status_code == 200, listed.text
    assert [
        (item["version_no"], item["transaction_price_buildup"]["total"])
        for item in listed.json()["items"]
    ] == [(2, usd("122000.00")), (1, usd("120000.00"))]
    first = get(world.app, f"{path}/versions/1", maya)
    assert first.status_code == 200, first.text
    version = first.json()
    assert (
        version["book"],
        version["status_in_book"],
        version["total_ssp"],
        version["transaction_price_buildup"]["fixed"],
        version["transaction_price_buildup"]["out_of_scope"],
        [event["event_type"] for event in version["cause_events"]],
    ) == ("ASC606", "DRAFT", "118000", usd("120000.00"), usd("0.00"), ["CONTRACT_BOOKED"])
    assert len(version["input_sha256"]) == len(version["output_sha256"]) == 64
    obligations = {item["obligation_key"]: item for item in version["obligations"]}
    assert (
        obligations["O1"]["current"]["allocated_amount"],
        obligations["O2"]["current"]["allocated_amount"],
        obligations["O2"]["ssp"]["range_position"],
        obligations["O2"]["ssp"]["outside_range_point"],
        obligations["O1"]["pob_template_version"]["template_code"],
        obligations["O1"]["context"]["version_no"],
    ) == (
        usd("97627.12"),
        usd("22372.88"),
        "ABOVE",
        "NEAREST_BOUND",
        "TPL-SUB-DAILY",
        1,
    )
    second = get(world.app, f"{path}/versions/2", maya).json()
    assert [event["event_type"] for event in second["cause_events"]] == [
        "EVENT_VOIDED",
        "CONTRACT_BOOKED",
    ]
    missing = get(world.app, f"{path}/versions/3", maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text
    balances = get(world.app, f"{path}/balances", maya)
    assert balances.status_code == 200, balances.text
    assert balances.json()["next_cursor"] is None
    for item in balances.json()["items"]:
        assert (item["contract_id"], item["book"]) == (booked["id"], "ASC606")
