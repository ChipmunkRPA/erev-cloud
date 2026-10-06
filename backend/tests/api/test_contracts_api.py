"""API-R-28 Contracts: creation, drafts and reads (04 §15.3 API-R-28, §16.1, §16.14; API-C-06,
API-C-08, API-C-09; 03 REQ-CON-001, REQ-CON-002, REQ-CON-014, REQ-CON-016, REQ-CON-017, REQ-ALC-009,
REQ-PLT-012, REQ-PLT-031; PRD WLD-C-12, WLD-F-20, WLD-X-23; D-12; BUILD_SPEC CTR-4).

The world is ``support.factories.j03_world`` (PRD §2.6): Maya (Revenue Accountant, SSP Analyst)
books through the routes; AVM-US and AVM-UK keep FY2026-P01 to P09 open; customer C-12; AVM-PLAT-100
(TPL-SUB-DAILY; observable 85,000.00 / 100,000.00 / 115,000.00 USD) and AVM-IMPL-PLUS
(TPL-SVC-HOURS; cost plus margin 18,000.00 / 20,000.00 / 22,000.00 USD) in US-LIST 2026-H1;
AVM-MAP-2026-01. The routes compute through ``computation.default_engine``, which the fixture points
at ``support.factories.engine()``: the ENGINE_SPEC §0.5 fake until END-9 lands, the real engine in
the L3 merge gate (V-C). The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_event, contract_version, subledger_line
from erev_api.domain.contracts import computation
from erev_api.domain.contracts.commands import book_contract
from erev_api.enums import ContractEventType, SourceSystem
from erev_api.events.payloads import ChecklistItemV1, ContractActivatedV1, ContractBookedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import J03World, computed, engine, j03_world, sf_ord_20417_body
from support.legacy_replay import SETUP_2023, SKU_SSP, LegacyWorld, committed, legacy_world
from support.principals import colleague
from support.reference import entity, fields, get, holding, post, slug

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


def created(world: J03World, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    response = post(
        world.app, CONTRACTS, world.place.author, body or sf_ord_20417_body(world.customer_id)
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def replaced(world: J03World, contract_id: str, *, price: str, if_match: str) -> Any:
    body = sf_ord_20417_body(world.customer_id, implementation_price=price)
    return post(
        world.app,
        f"{CONTRACTS}/{contract_id}/replace-draft",
        world.place.author,
        body,
        if_match=if_match,
    )


def activate(world: J03World, contract_id: str, head: int) -> None:
    """BS3-D-19: ``CONTRACT_ACTIVATED`` as the SYSTEM principal until CTR-9 builds activation."""
    with world.place.uow(system_principal(world.place.tenant_id)) as uow:
        append_events(
            uow,
            contract_id=UUID(contract_id),
            expected_stream_version=head,
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


def test_create_draft_computes_provisional_version(world: J03World) -> None:
    maya = world.place.author
    response = post(world.app, CONTRACTS, maya, sf_ord_20417_body(world.customer_id))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["head_stream_version"], body["kpis"]["transaction_price"]) == (
        "DRAFT",
        1,
        usd("120000.00"),
    )
    assert (response.headers["Location"], response.headers["ETag"]) == (
        f"{CONTRACTS}/{body['id']}",
        '"s1"',
    )
    assert (
        body["external_id"],
        body["document_ref"],
        body["customer"]["code"],
        body["contracting_entity"]["code"],
        body["transaction_currency"],
        body["inception_date"],
        body["source_system"],
        body["status_reason"] is None or isinstance(body["status_reason"], str),
    ) == ("SF-ORD-20417", "SF-ORD-20417", "C-12", "AVM-US", "USD", "2026-09-01", "MANUAL_UI", True)
    assert (body["context"]["book"], body["context"]["version_no"], body["context"]["as_of"]) == (
        "ASC606",
        1,
        "2026-09-12",
    )
    assert body["combination_group"]["member_contract_ids"] == [body["id"]]
    assert [(step["step"], step["state"]) for step in body["steps"]] == [
        ("CONTRACT", "COMPLETE"),
        ("OBLIGATIONS", "COMPLETE"),
        ("TRANSACTION_PRICE", "COMPLETE"),
        ("ALLOCATION", "COMPLETE"),
        ("RECOGNITION", "COMPLETE"),
    ]
    assert body["links"]["self"] == f"{CONTRACTS}/{body['id']}"
    # REQ-CON-002, S02-R-02: a DRAFT computation posts nothing.
    lines = get(world.app, f"{CONTRACTS}/{body['id']}/subledger-lines", maya)
    assert (lines.status_code, lines.json()["items"]) == (200, []), lines.text
    stored = world.place.scalar(
        select(func.count())
        .select_from(subledger_line)
        .where(subledger_line.c.contract_id == UUID(body["id"]))
    )
    assert stored == 0
    shown = get(world.app, f"{CONTRACTS}/{body['id']}", maya)
    assert (shown.status_code, shown.headers["ETag"]) == (200, '"s1"'), shown.text
    assert (shown.json()["kpis"], shown.json()["status"]) == (body["kpis"], "DRAFT")
    versions = world.place.rows(
        select(contract_version.c.version_no, contract_version.c.status_in_book).where(
            contract_version.c.combination_group_id == UUID(body["combination_group"]["id"])
        )
    )
    assert [(row["version_no"], str(row["status_in_book"])) for row in versions] == [(1, "DRAFT")]


def test_allocation_walk_sf_ord_20417(world: J03World) -> None:
    booked = created(world)
    walk = get(world.app, f"{CONTRACTS}/{booked['id']}/allocation", world.place.author)
    assert walk.status_code == 200, walk.text
    body = walk.json()
    lines = {line["obligation_key"]: line for line in body["lines"]}

    def figures(line: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            line["low"],
            line["mid"],
            line["high"],
            line["stated_price"],
            line["range_position"],
            line["outside_range_point"],
            line["selected_ssp"],
            line["allocated"],
            line["allocation_adjustment"],
        )

    assert figures(lines["O1"]) == (
        "85000",
        "100000",
        "115000",
        usd("96000.00"),
        "INSIDE",
        None,
        "96000",
        usd("97627.12"),
        usd("1627.12"),
    )
    assert figures(lines["O2"]) == (
        "18000",
        "20000",
        "22000",
        usd("24000.00"),
        "ABOVE",
        "NEAREST_BOUND",
        "22000",
        usd("22372.88"),
        usd("-1627.12"),
    )
    assert (lines["O1"]["in_range"], lines["O2"]["in_range"]) == (True, False)
    assert (lines["O1"]["product"]["code"], lines["O2"]["product"]["code"]) == (
        "AVM-PLAT-100",
        "AVM-IMPL-PLUS",
    )
    assert (lines["O1"]["ssp_method"], lines["O2"]["ssp_method"]) == (
        "observable",
        "cost_plus_margin",
    )
    assert lines["O1"]["ssp_book_version"] == {"id": world.version_id, "label": "2026-H1"}
    assert body["totals"] == {
        "allocated": usd("120000.00"),
        "allocation_adjustment": usd("0.00"),
    }
    assert (body["transaction_price"], body["total_ssp"], body["context"]["version_no"]) == (
        usd("120000.00"),
        "118000",
        1,
    )
    # REQ-ALC-009: exact quota less the allocated amount is the rounding residue.
    for line in lines.values():
        exact = line["exact_quota"]
        allocated = line["allocated"]["amount"]
        assert abs(float(exact) - float(allocated)) < 0.01
        assert line["rounding_residue"] != ""
    missing = get(world.app, f"{CONTRACTS}/{UUID(int=7)}/allocation", world.place.author)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text


def test_money_number_rejected(world: J03World) -> None:
    maya = world.place.author
    body = sf_ord_20417_body(world.customer_id)
    body["lines"][0]["total_price"] = 96000.00
    refused = post(world.app, CONTRACTS, maya, body)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert ("lines.0.total_price", "API-C-06") in fields(refused)
    body["lines"][0]["total_price"] = {"amount": 96000.00, "currency": "USD"}
    again = post(world.app, CONTRACTS, maya, body)
    assert (again.status_code, slug(again)) == (422, "validation-failed"), again.text
    assert ("lines.0.total_price.amount", "API-C-06") in fields(again)
    listed = get(world.app, CONTRACTS, maya)
    assert (listed.status_code, listed.json()["items"]) == (200, []), listed.text


def test_replace_draft(world: J03World) -> None:
    maya = world.place.author
    booked = created(world)
    contract_id = booked["id"]
    changed = replaced(world, contract_id, price="26000.00", if_match='"s1"')
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["status"], body["head_stream_version"], changed.headers["ETag"]) == (
        "DRAFT",
        3,
        '"s3"',
    )
    assert (body["kpis"]["transaction_price"], body["context"]["version_no"]) == (
        usd("122000.00"),
        2,
    )
    events = world.place.rows(
        select(
            contract_event.c.id,
            contract_event.c.stream_version,
            contract_event.c.event_type,
            contract_event.c.created_by_kind,
            contract_event.c.supersedes_event_id,
            contract_event.c.payload,
        )
        .where(contract_event.c.contract_id == UUID(contract_id))
        .order_by(contract_event.c.stream_version)
    )
    assert [
        (row["stream_version"], str(row["event_type"]), str(row["created_by_kind"]))
        for row in events
    ] == [
        (1, "CONTRACT_BOOKED", "USER"),
        (2, "EVENT_VOIDED", "SYSTEM"),
        (3, "CONTRACT_BOOKED", "USER"),
    ]
    assert events[1]["supersedes_event_id"] == events[0]["id"]
    assert events[1]["payload"]["reason_code"] == "DATA_CORRECTION"
    assert events[2]["payload"]["lines"][1]["total_price"] == usd("26000.00")
    versions = world.place.rows(
        select(contract_version.c.version_no, contract_version.c.transaction_price)
        .where(contract_version.c.combination_group_id == UUID(booked["combination_group"]["id"]))
        .order_by(contract_version.c.version_no)
    )
    assert [(row["version_no"], format(row["transaction_price"], ".2f")) for row in versions] == [
        (1, "120000.00"),
        (2, "122000.00"),
    ]
    # API-C-08: a stale or missing precondition is refused before any change.
    stale = replaced(world, contract_id, price="27000.00", if_match='"s1"')
    assert (stale.status_code, slug(stale)) == (412, "precondition-failed"), stale.text
    unconditional = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/replace-draft",
        maya,
        sf_ord_20417_body(world.customer_id),
    )
    assert (unconditional.status_code, slug(unconditional)) == (428, "precondition-required")
    renamed = sf_ord_20417_body(world.customer_id, external_id="SF-ORD-99999")
    refused = post(
        world.app, f"{CONTRACTS}/{contract_id}/replace-draft", maya, renamed, if_match='"s3"'
    )
    assert (refused.status_code, fields(refused)) == (422, [("external_id", "T-CON-01")])
    # 04 §16.1: only a DRAFT contract is replaced.
    active = created(world, sf_ord_20417_body(world.customer_id, external_id="SF-ORD-20418"))
    activate(world, active["id"], 1)
    body = sf_ord_20417_body(world.customer_id, external_id="SF-ORD-20418")
    body["lines"][1]["total_price"] = usd("26000.00")
    blocked = post(
        world.app, f"{CONTRACTS}/{active['id']}/replace-draft", maya, body, if_match='"s2"'
    )
    assert (blocked.status_code, slug(blocked)) == (409, "invalid-transition"), blocked.text
    heads = world.place.rows(
        select(func.max(contract_event.c.stream_version)).where(
            contract_event.c.contract_id == UUID(active["id"])
        )
    )
    assert list(heads[0].values()) == [2]


def test_versions_compare_field_by_field(world: J03World) -> None:
    booked = created(world)
    changed = replaced(world, booked["id"], price="26000.00", if_match='"s1"')
    assert changed.status_code == 200, changed.text
    compared = get(
        world.app,
        f"{CONTRACTS}/{booked['id']}/versions/compare",
        world.place.author,
        {"from": "1", "to": "2"},
    )
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert (body["book"], body["from_version"]["version_no"], body["to_version"]["version_no"]) == (
        "ASC606",
        1,
        2,
    )
    changes = {
        (change["field"], change["obligation_key"]): (change["before"], change["after"])
        for change in body["changes"]
    }
    assert changes[("transaction_price", None)] == ("120000.00", "122000.00")
    assert changes[("allocated_amount", "O2")] == ("22372.88", "22745.76")
    assert changes[("stated_price", "O2")] == ("24000.00", "26000.00")
    assert changes[("allocated_amount", "O1")] == ("97627.12", "99254.24")
    assert ("total_ssp", None) not in changes
    unknown = get(
        world.app,
        f"{CONTRACTS}/{booked['id']}/versions/compare",
        world.place.author,
        {"from": "1", "to": "9"},
    )
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text


def flagged(world: J03World, external_id: str, scope_flag: str) -> dict[str, Any]:
    """O1 of SF-ORD-20417 plus an O3 AVM-PLAT-100 line of 10,000.00 flagged ``scope_flag``: booked,
    activated as SYSTEM (BS3-D-19) and computed, so version 2 is ACTIVE and holds schedules
    (REQ-CON-002). The LABOUR_HOURS line is left out (L3-1-Q-45)."""
    body = sf_ord_20417_body(world.customer_id, external_id=external_id)
    body["lines"] = body["lines"][:1]
    body["lines"].append(
        {
            "obligation_key": "O3",
            "product_code": "AVM-PLAT-100",
            "quantity": "1",
            "total_price": usd("10000.00"),
            "start_date": "2026-09-01",
            "end_date": "2027-08-31",
            "scope_flag": scope_flag,
            "out_of_scope_amount": usd("10000.00"),
        }
    )
    booked = created(world, body)
    activate(world, booked["id"], 1)
    computed(world.place, UUID(booked["combination_group"]["id"]))
    return booked


def removed_from_price(world: J03World, booked: Mapping[str, Any]) -> tuple[Any, set[Any]]:
    """(the build-up of the active version 2, the obligation keys of its unbounded schedule)."""
    maya = world.place.author
    version = get(world.app, f"{CONTRACTS}/{booked['id']}/versions/2", maya)
    assert version.status_code == 200, version.text
    schedule = get(world.app, f"{CONTRACTS}/{booked['id']}/schedule", maya, {"limit": "500"})
    assert schedule.status_code == 200, schedule.text
    keys = {item["obligation_key"] for item in schedule.json()["items"]}
    return version.json()["transaction_price_buildup"], keys


def test_out_of_scope_line_removed_from_price(world: J03World) -> None:
    # S03-R-11 and S04-R-03 for a flag excluded from obligations: the amount leaves the price.
    guarantee, keys = removed_from_price(world, flagged(world, "SF-ORD-20421", "GUARANTEE_460"))
    assert (guarantee["out_of_scope"], guarantee["total"]) == (usd("10000.00"), usd("96000.00"))
    assert "O1" in keys and "O3" not in keys
    # The named case: a LEASE_842 line (PT-09 allocation target, routed out; L3-1-Q-44).
    leased = flagged(world, "SF-ORD-20419", "LEASE_842")
    lease, keys = removed_from_price(world, leased)
    assert lease["out_of_scope"] == usd("10000.00")
    assert "O1" in keys
    assert "O3" not in keys
    # 04 API-C-10 rev 1.132: the engine takes no revenue measure per period for the routed-out
    # line (ENGINE_SPEC_B S09-INV-05), so its trace holds no period node of it. Its to-date
    # figures stay the version's, 0, no period is named for it, and the reads answer.
    maya = world.place.author
    shown = get(world.app, f"{CONTRACTS}/{leased['id']}", maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["kpis"] is not None
    listed = get(world.app, f"{CONTRACTS}/{leased['id']}/obligations", maya)
    assert listed.status_code == 200, listed.text
    items = {item["obligation_key"]: item for item in listed.json()["items"]}
    assert (items["O3"]["to_date"]["revenue"], items["O3"]["context"]["measured_period"]) == (
        usd("0.00"),
        None,
    )
    assert items["O1"]["context"]["measured_period"] == {
        "period_key": "FY2026-P09",
        "end_date": "2026-09-30",
    }


def test_list_quick_lists_and_filters(world: J03World) -> None:
    maya = world.place.author
    largest = created(world)
    smaller = created(
        world,
        {
            **sf_ord_20417_body(world.customer_id, external_id="SF-ORD-20420"),
            "lines": [sf_ord_20417_body(world.customer_id)["lines"][0]],
        },
    )
    with world.place.uow() as uow:
        body = sf_ord_20417_body(world.customer_id, external_id="SF-ORD-SYNC-1")
        book_contract(
            uow,
            body=ContractBookedV1.model_validate(body),
            origin="ADAPTER",
            source_system=SourceSystem.SALESFORCE,
        )
        uow.commit()

    def external_ids(params: Mapping[str, Any]) -> list[str]:
        listed = get(world.app, CONTRACTS, maya, params)
        assert listed.status_code == 200, listed.text
        return [item["external_id"] for item in listed.json()["items"]]

    assert sorted(external_ids({"quick_list": "CREATED_MANUALLY"})) == [
        "SF-ORD-20417",
        "SF-ORD-20420",
    ]
    assert external_ids({"quick_list": "LARGEST_VALUE"}) == [
        "SF-ORD-20417",
        "SF-ORD-20420",
        "SF-ORD-SYNC-1",
    ]
    assert sorted(external_ids({"status": "DRAFT", "entity": "AVM-US"})) == [
        "SF-ORD-20417",
        "SF-ORD-20420",
        "SF-ORD-SYNC-1",
    ]
    activate(world, smaller["id"], 1)
    assert sorted(external_ids({"status": "DRAFT", "entity": "AVM-US"})) == [
        "SF-ORD-20417",
        "SF-ORD-SYNC-1",
    ]
    assert external_ids({"status": "ACTIVE", "entity": str(world.entity_id)}) == ["SF-ORD-20420"]
    assert external_ids({"entity": "AVM-UK"}) == []
    assert external_ids({"value_min": "115000.00"}) == ["SF-ORD-20417"]
    assert external_ids({"q": "20420"}) == ["SF-ORD-20420"]
    assert external_ids(
        {"customer": "C-12", "quick_list": "CREATED_FROM_INTEGRATIONS_THIS_PERIOD"}
    ) == ["SF-ORD-SYNC-1"]
    counted = get(world.app, CONTRACTS, maya, {"count": "true", "status": "DRAFT"})
    assert counted.headers["X-Erev-Total-Count"] == "2"
    item = get(world.app, CONTRACTS, maya, {"quick_list": "LARGEST_VALUE", "limit": "1"}).json()
    (first,) = item["items"]
    assert (first["external_id"], first["kpis"]["transaction_price"]) == (
        largest["external_id"],
        usd("120000.00"),
    )
    assert "links" not in first and "balances" not in first["kpis"]
    for params in ({"quick_list": "NEWEST"}, {"status": "OPEN"}, {"value_min": "a lot"}):
        refused = get(world.app, CONTRACTS, maya, params)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text


def test_contract_out_of_scope_returns_404(world: J03World) -> None:
    booked = created(world)
    germany = entity(
        world.app,
        world.place.author,
        code="AVM-DE",
        calendar_id=world.calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )
    someone = colleague(world.place.tenant_id, "dieter")
    scoped = holding(world.app, someone, "revenue_accountant", entity_ids=[UUID(germany["id"])])
    for path in ("", "/allocation", "/versions/1", "/history", "/schedule"):
        refused = get(world.app, f"{CONTRACTS}/{booked['id']}{path}", scoped)
        assert (refused.status_code, slug(refused)) == (404, "not-found"), (path, refused.text)
    listed = get(world.app, CONTRACTS, scoped)
    assert (listed.status_code, listed.json()["items"]) == (200, []), listed.text
    shown = get(world.app, f"{CONTRACTS}/{booked['id']}", world.place.author)
    assert shown.status_code == 200, shown.text


def test_history_items_newest_first(world: J03World) -> None:
    maya = world.place.author
    booked = created(world)
    path = f"{CONTRACTS}/{booked['id']}/history"
    first = get(world.app, path, maya)
    assert first.status_code == 200, first.text
    # 05 RCP-18 and TXN-10 rev 1.82, 04 API-S-ContractHistoryItem rev 1.143 (supervisor rulings
    # R-95 and R-103 (b)): a computation is SYSTEM's, on behalf of the person whose command asked
    # for it, as a deferred one always was. The default view lists what people did; the
    # calculations appear with ``include_system``.
    assert [item["kind"] for item in first.json()["items"]] == ["EVENT"]
    world.place.clock.advance(timedelta(minutes=10))  # within the 30-minute idle timeout
    changed = replaced(world, booked["id"], price="26000.00", if_match='"s1"')
    assert changed.status_code == 200, changed.text
    items = get(world.app, path, maya).json()["items"]
    assert [(item["kind"], item["summary_key"]) for item in items] == [
        ("EVENT", "contract_event.CONTRACT_BOOKED"),
        ("EVENT", "contract_event.CONTRACT_BOOKED"),
    ]
    occurred = [item["occurred_at"] for item in items]
    assert occurred == sorted(occurred, reverse=True)
    assert (items[0]["occurred_at"], items[-1]["occurred_at"]) == (
        "2026-09-12T12:10:00Z",
        "2026-09-12T12:00:00Z",
    )
    assert (items[0]["actor"]["kind"], items[0]["actor"]["id"]) == (
        "USER",
        str(maya.member.user_id),
    )
    assert items[0]["params"]["stream_version"] == 3
    assert items[0]["links"]["event"].startswith(f"{CONTRACTS}/{booked['id']}/events/")
    with_system = get(world.app, path, maya, {"include_system": "true"}).json()["items"]
    assert [(item["kind"], item["summary_key"], item["actor"]["kind"]) for item in with_system] == [
        ("CALCULATION", "contract_computation.SUCCEEDED", "SYSTEM"),
        ("EVENT", "contract_event.CONTRACT_BOOKED", "USER"),
        ("EVENT", "contract_event.EVENT_VOIDED", "SYSTEM"),
        ("CALCULATION", "contract_computation.SUCCEEDED", "SYSTEM"),
        ("EVENT", "contract_event.CONTRACT_BOOKED", "USER"),
    ]
    assert with_system[0]["actor"]["display_name"] == "System"
    assert (with_system[2]["summary_key"], with_system[2]["actor"]["display_name"]) == (
        "contract_event.EVENT_VOIDED",
        "System",
    )
    events_only = get(world.app, path, maya, {"kind": "EVENT"}).json()["items"]
    assert {item["kind"] for item in events_only} == {"EVENT"}
    paged = get(world.app, path, maya, {"limit": "1"}).json()
    assert paged["next_cursor"] is not None
    rest = get(world.app, path, maya, {"limit": "3", "cursor": paged["next_cursor"]}).json()
    assert [item["kind"] for item in paged["items"] + rest["items"]] == [
        item["kind"] for item in items
    ]


def test_signed_position_never_in_contract_kpis(world: J03World) -> None:
    booked = created(world)
    shown = get(world.app, f"{CONTRACTS}/{booked['id']}", world.place.author)
    assert shown.status_code == 200, shown.text
    kpis = shown.json()["kpis"]
    assert set(kpis) == {
        "transaction_price",
        "revenue_to_date",
        "billed_to_date",
        "scheduled",
        "awaiting_trigger",
        "rpo",
        "balances",
    }
    assert "net_position" not in kpis
    for balance in kpis["balances"]:
        assert "net_position" not in balance
    listed = get(world.app, CONTRACTS, world.place.author).json()["items"]
    assert all("net_position" not in item["kpis"] for item in listed)
    schemas = world.app.openapi()["components"]["schemas"]
    for name in ("ContractKpisOut", "ContractDetailKpisOut", "EntityBalanceKpiOut"):
        assert "net_position" not in schemas[name]["properties"], name


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def test_contract_sources_route(legacy: LegacyWorld) -> None:
    # BUILD_SPEC DIN-4, BS3-D-04: API-R-28 GET /contracts/{id}/sources over T-CON-02.
    committed(legacy, "SKU SSP Template.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp")
    done = committed(
        legacy,
        "Contract Setup Template 1.1.2023.xlsx",
        SETUP_2023.read_bytes(),
        "legacy_contract_setup",
    )
    listed = get(legacy.app, CONTRACTS, legacy.maya, {"q": "Contract 1"}).json()["items"]
    (contract_1,) = [item for item in listed if item["external_id"] == "Contract 1"]
    response = get(legacy.app, f"{CONTRACTS}/{contract_1['id']}/sources", legacy.maya)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next_cursor"] is None
    items = body["items"]
    assert [(item["sheet_name"], item["row_number"]) for item in items] == [
        ("Sheet1", number) for number in (2, 3, 4, 5)
    ]
    (booking,) = legacy.imports.rows(
        select(contract_event.c.id).where(
            contract_event.c.contract_id == UUID(contract_1["id"]),
            contract_event.c.event_type == ContractEventType.CONTRACT_BOOKED.value,
        )
    )
    for item in items:
        assert (
            item["link_role"],
            item["source_system"],
            item["object_type"],
            item["import_upload_id"],
            item["contract_event_id"],
        ) == (
            "BOOKING",
            "LEGACY_TEMPLATE_V1",
            "CONTRACT_SETUP_ROW",
            done["id"],
            str(booking["id"]),
        )
        assert item["external_id"] == f"{done['id']}:Sheet1:{item['row_number']}"
        record = get(legacy.app, f"/api/v1/source-records/{item['source_record_id']}", legacy.maya)
        assert record.status_code == 200, record.text
        assert record.json()["import_row_id"] == item["import_row_id"]
    missing = get(legacy.app, f"{CONTRACTS}/{UUID(int=7)}/sources", legacy.maya)
    assert missing.status_code == 404, missing.text
