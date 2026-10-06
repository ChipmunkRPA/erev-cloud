"""API-R-55 ``GET /search`` (04 §15.3 API-R-55, §16.13 API-S-SearchResult rev 1.195; dev-guide
DG-LST-11; SCREENS R-01, §1.4; BUILD_SPEC CTR-28; supervisor ruling R-116 (f)).

The world is the seat world (AVM-US, the monthly seat product, customers C-02 and C-09) with
Pellworth as C-01, a second entity AVM-DE, contracts booked through the contract command, a
computed version where an obligation's status is read, invoices as an adapter stores them (rows
of ``source_record``, ``source_invoice`` and its lines) and a journal run of the close world.

What is held: the five scopes in E-120 order; the word rule — a term begins a word, every term
must match, compared case-folded — and the order of the items; the bounds of ``q`` and ``limit``;
the cursor of a scope; and that a record the caller could not open is not answered, whichever
table its entity is read from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    source_invoice,
    source_invoice_line,
    source_record,
)
from erev_api.domain.contracts.commands import BookedContract
from erev_api.enums import SearchScope
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert
from support.close_world import acknowledged_run_for
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    booked_contract,
    computed,
    customer_id,
    seat_body,
    seat_line,
    seat_world,
)
from support.http import HttpResponse
from support.plans import sent
from support.principals import Actor, colleague
from support.reference import CALENDARS, entity, fields, get, holding, periods, slug
from support.rows import approval_request_values, source_invoice_values, source_record_values

SEARCH = "/api/v1/search"
SCOPES = ["contracts", "customers", "invoices", "obligations", "journals"]
PELLWORTH = "Pellworth Logistics Inc. (Demo)"
SEAT = "Platform seat, monthly"
BETWEEN = " \N{MIDDLE DOT} "


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def _search(world: SeatWorld, actor: Actor | None = None, **params: Any) -> HttpResponse:
    return get(world.app, SEARCH, world.place.author if actor is None else actor, params)


def _items(
    world: SeatWorld, scope: str, q: str, actor: Actor | None = None
) -> list[dict[str, Any]]:
    found = _search(world, actor, q=q, scope=scope, limit=50)
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["scope"] == scope
    return list(body["items"])


def _primaries(world: SeatWorld, scope: str, q: str, actor: Actor | None = None) -> list[str]:
    return [item["primary"] for item in _items(world, scope, q, actor)]


def _booked(
    world: SeatWorld,
    external_id: str,
    *,
    customer: UUID,
    entity_code: str = "AVM-US",
    activate: bool = False,
) -> BookedContract:
    line = seat_line("O1", seats="10", price="24000.00", start="2026-01-01", end="2026-12-31")
    body = seat_body(customer, external_id=external_id, inception="2026-01-01", lines=[line])
    return booked_contract(
        world.place, {**body, "contracting_entity_code": entity_code}, activate=activate
    )


def _pellworth(world: SeatWorld) -> UUID:
    return customer_id(world.app, world.place.author, code="C-01", name=PELLWORTH)


def _invoice(
    world: SeatWorld,
    number: str,
    *,
    contracts: tuple[str, ...],
    external_id: str | None = None,
    version: int = 1,
    minutes: int = 0,
) -> UUID:
    """One stored version of an invoice whose lines name ``contracts`` by external id."""
    tenant_id = world.place.tenant_id
    external = external_id or f"ext-{number}"
    record = source_record_values(
        tenant_id,
        object_type="INVOICE",
        external_id=external,
        external_version=str(version),
        version_order=version,
    )
    invoice = source_invoice_values(
        tenant_id,
        source_record_id=record["id"],
        external_invoice_id=external,
        external_version=str(version),
        invoice_number=number,
        created_at=world.place.clock.now() + timedelta(minutes=minutes),
    )
    lines = [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "source_invoice_id": invoice["id"],
            "line_external_id": str(position),
            "contract_ref": reference,
            "amount": Decimal("100.00"),
            "created_by_kind": "SYSTEM",
        }
        for position, reference in enumerate(contracts, start=1)
    ]
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(source_record).values(**record))
        session.execute(insert(source_invoice).values(**invoice))
        if lines:
            session.execute(insert(source_invoice_line), lines)
    return UUID(str(invoice["id"]))


@dataclass(frozen=True, slots=True)
class TwoEntities:
    """AVM-US with ``SF-ORD-10001`` and AVM-DE with ``NS-SO-DE-5004``, and Dana, a Revenue
    Accountant for AVM-DE alone."""

    us: BookedContract
    de: BookedContract
    dana: Actor


def _two_entities(world: SeatWorld) -> TwoEntities:
    maya = world.place.author
    listed = get(world.app, CALENDARS, maya)
    assert listed.status_code == 200, listed.text
    calendar_id = str(listed.json()["items"][0]["id"])
    germany = entity(world.app, maya, code="AVM-DE", calendar_id=calendar_id)
    pellworth = _pellworth(world)
    us = _booked(world, "SF-ORD-10001", customer=pellworth, activate=True)
    de = _booked(world, "NS-SO-DE-5004", customer=world.customers["C-09"], entity_code="AVM-DE")
    dana = holding(
        world.app,
        colleague(world.place.tenant_id, "dana"),
        "revenue_accountant",
        entity_ids=[UUID(str(germany["id"]))],
    )
    return TwoEntities(us=us, de=de, dana=dana)


def test_search_without_scope_groups_results(world: SeatWorld) -> None:
    """CTR-28: ``GET /search?q=SF-ORD`` answers one entry per E-120 scope in E-120 order; the
    contracts hold ``SF-ORD-10001`` with its customer as ``secondary`` and the status the contract
    reads show."""
    booked = _booked(world, "SF-ORD-10001", customer=_pellworth(world), activate=True)
    found = _search(world, q="SF-ORD")
    assert found.status_code == 200, found.text
    results = found.json()["results"]
    assert [entry["scope"] for entry in results] == SCOPES == [scope.value for scope in SearchScope]
    contracts = results[0]
    assert contracts["items"] == [
        {
            "id": str(booked.contract["id"]),
            "primary": "SF-ORD-10001",
            "secondary": PELLWORTH,
            "status": "ACTIVE",
            "href": f"/api/v1/contracts/{booked.contract['id']}",
        }
    ]
    assert contracts["next_cursor"] is None
    # ... its obligation is found by the contract's external id in its primary; no customer, no
    # invoice and no journal run has a word that begins with both terms
    (obligation,) = results[3]["items"]
    assert obligation["primary"] == f"SF-ORD-10001{BETWEEN}O1"
    assert [entry["items"] for entry in (results[1], results[2], results[4])] == [[], [], []]


def test_query_length_bounds(world: SeatWorld) -> None:
    """CTR-28: ``q`` holds 2 to 200 characters after trimming and a letter or digit; ``limit`` is
    1 to 50; ``cursor`` comes with ``scope``. Each refusal is 422 ``validation-failed`` on the
    parameter."""
    for q, message in (
        ("S", "Type at least 2 characters to search."),
        ("  S  ", "Type at least 2 characters to search."),
        ("x" * 201, "Search for at most 200 characters."),
        ("--", "Type a letter or a digit to search."),
    ):
        refused = _search(world, q=q)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("q", "API-R-55")], refused.text
        assert refused.json()["errors"][0]["message"] == message
    for params in (
        {"q": "SF", "limit": 51},
        {"q": "SF", "limit": 0},
        {},
        {"q": "SF", "scope": "x"},
    ):
        refused = get(world.app, SEARCH, world.place.author, params)
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    # 200 characters are a query, and so are two after trimming
    assert _search(world, q="x" * 200).status_code == 200
    assert _search(world, q="  x1  ").status_code == 200
    # a cursor belongs to a scope
    refused = _search(world, q="SF", cursor="abc")
    assert (refused.status_code, fields(refused)) == (422, [("cursor", "API-R-55")]), refused.text


def test_results_filtered_by_entity_scope(world: SeatWorld) -> None:
    """CTR-28: a principal whose role names AVM-DE finds ``NS-SO-DE-5004`` and not
    ``SF-ORD-10001``; a principal for every entity finds both."""
    two = _two_entities(world)
    assert _primaries(world, "contracts", "SF-ORD") == ["SF-ORD-10001"]
    assert _primaries(world, "contracts", "NS-SO") == ["NS-SO-DE-5004"]
    assert _primaries(world, "contracts", "SF-ORD", two.dana) == []
    assert _primaries(world, "contracts", "NS-SO", two.dana) == ["NS-SO-DE-5004"]
    everything = _search(world, two.dana, q="demo")  # the customers' names end in "(Demo)"
    assert everything.status_code == 200, everything.text
    by_scope = {entry["scope"]: entry["items"] for entry in everything.json()["results"]}
    assert [item["primary"] for item in by_scope["contracts"]] == ["NS-SO-DE-5004"]


def test_a_record_the_caller_could_not_open_is_not_answered(
    world: SeatWorld, clock: FrozenClock
) -> None:
    """``obligation`` and ``source_invoice`` are tenant-level in the row policy: the search reads
    them through their contract, so the obligations and the invoices of AVM-US are not answered
    to a principal for AVM-DE, an invoice whose lines name contracts of both entities names hers,
    and a journal run of AVM-US is not hers. Customers are tenant master data and are answered to
    every holder of ``contract.read``."""
    two = _two_entities(world)
    maya = world.place.author
    _invoice(world, "INV-7001", contracts=("SF-ORD-10001",))
    _invoice(world, "INV-7002", contracts=("NS-SO-DE-5004",))
    _invoice(world, "INV-7003", contracts=("SF-ORD-10001", "NS-SO-DE-5004"))
    _invoice(world, "INV-7004", contracts=("NO-SUCH-CONTRACT",))
    _invoice(world, "INV-7005", contracts=())
    september = next(
        row
        for row in periods(world.app, maya, entity="AVM-US")
        if row["period"]["period_key"] == "FY2026-P09"
    )
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        run = acknowledged_run_for(
            session,
            tenant_id=world.place.tenant_id,
            entity_id=world.entity_id,
            period_id=UUID(str(september["period"]["id"])),
            now=clock.now(),
        ).run

    # Maya, for every entity: each invoice once, through the first contract its lines name
    invoices = {item["primary"]: item for item in _items(world, "invoices", "INV")}
    assert sorted(invoices) == ["INV-7001", "INV-7002", "INV-7003"]  # no contract, no item
    assert invoices["INV-7003"]["secondary"] == "NS-SO-DE-5004"  # the first by external id
    assert invoices["INV-7001"]["href"] == f"/api/v1/contracts/{two.us.contract['id']}"
    assert {item["status"] for item in invoices.values()} == {None}
    assert _primaries(world, "obligations", "O1") == [
        f"NS-SO-DE-5004{BETWEEN}O1",
        f"SF-ORD-10001{BETWEEN}O1",
    ]
    assert [
        (item["primary"], item["secondary"], item["status"])
        for item in _items(world, "journals", str(run["run_no"]))
    ] == [(run["run_no"], f"FY2026-P09{BETWEEN}AVM-US", "acknowledged")]

    # Dana, for AVM-DE: what names her contract, and nothing else
    hers = {item["primary"]: item for item in _items(world, "invoices", "INV", two.dana)}
    assert sorted(hers) == ["INV-7002", "INV-7003"]
    assert {item["secondary"] for item in hers.values()} == {"NS-SO-DE-5004"}
    assert {item["href"] for item in hers.values()} == {
        f"/api/v1/contracts/{two.de.contract['id']}"
    }
    assert _primaries(world, "obligations", "O1", two.dana) == [f"NS-SO-DE-5004{BETWEEN}O1"]
    assert _items(world, "journals", str(run["run_no"]), two.dana) == []
    # ... and each link she is given opens for her, while the other contract's does not
    assert get(world.app, hers["INV-7003"]["href"], two.dana).status_code == 200
    assert get(world.app, invoices["INV-7001"]["href"], two.dana).status_code == 404
    # customers have no entity
    assert _primaries(world, "customers", "pellworth", two.dana) == ["C-01"]


def test_scope_cursor_paging(world: SeatWorld) -> None:
    """CTR-28: ``GET /search?q=BG-AVM&scope=contracts&limit=25`` answers 25 items and a
    ``next_cursor``; the cursor continues the scope without a gap or a repeat, and belongs to its
    ``q`` and its scope."""
    customer = world.customers["C-02"]
    for number in range(1, 28):
        _booked(world, f"BG-AVM-{number:04d}", customer=customer)
    first = _search(world, q="BG-AVM", scope="contracts", limit=25)
    assert first.status_code == 200, first.text
    page = first.json()
    assert (page["scope"], len(page["items"])) == ("contracts", 25)
    assert isinstance(page["next_cursor"], str)
    rest = _search(world, q="BG-AVM", scope="contracts", limit=25, cursor=page["next_cursor"])
    assert rest.status_code == 200, rest.text
    assert (len(rest.json()["items"]), rest.json()["next_cursor"]) == (2, None)
    seen = [item["primary"] for item in (*page["items"], *rest.json()["items"])]
    assert sorted(seen) == [f"BG-AVM-{number:04d}" for number in range(1, 28)]
    # without a scope every entry carries the cursor of its own scope, which continues it
    grouped = _search(world, q="BG-AVM", limit=25)
    assert grouped.status_code == 200, grouped.text
    contracts = grouped.json()["results"][0]
    assert [item["id"] for item in contracts["items"]] == [item["id"] for item in page["items"]]
    again = _search(world, q="BG-AVM", scope="contracts", limit=25, cursor=contracts["next_cursor"])
    assert again.json()["items"] == rest.json()["items"]
    # a cursor of another query, of another scope, or no cursor at all is refused
    for params in (
        {"q": "BG", "scope": "contracts"},
        {"q": "BG-AVM", "scope": "obligations"},
        {"q": "BG-AVM", "scope": "contracts", "cursor": "not-a-cursor"},
    ):
        cursor = params.get("cursor", page["next_cursor"])
        refused = _search(world, **{**params, "cursor": cursor})
        assert (refused.status_code, fields(refused)) == (422, [("cursor", "API-C-09")]), (
            refused.text
        )


def test_dg_lst_11_a_term_begins_a_word_and_every_term_must_match(world: SeatWorld) -> None:
    """The word rule (04 §16.13 "Matching and order"): a term matches where it BEGINS a word of
    ``primary`` or ``secondary`` — never inside one —, words are compared case-folded, a
    separator is whatever is no letter or digit, and every term of ``q`` must match."""
    _booked(world, "SF-ORD-10002", customer=world.customers["C-02"])  # Marrowby Health Partners
    _booked(world, "SF-ORD-20417", customer=world.customers["C-09"])  # Orrin Vale Architects
    for q, expected in (
        ("10002", ["SF-ORD-10002"]),  # a word of the identifier
        ("0002", []),  # ... not its inside
        ("sf-ord", ["SF-ORD-20417", "SF-ORD-10002"]),  # case-folded; the newer first
        ("ord sf", ["SF-ORD-20417", "SF-ORD-10002"]),  # the terms in any order
        ("marrow", ["SF-ORD-10002"]),  # the beginning of a word of the customer's name
        ("rrow", []),
        ("MARROWBY health", ["SF-ORD-10002"]),
        ("sf marrow", ["SF-ORD-10002"]),  # one term in each text
        ("sf marrow vale", []),  # every term must match
        ("orrin_vale", ["SF-ORD-20417"]),  # an underscore separates words like a space
        ("s 1", ["SF-ORD-10002"]),  # a term of one character inside a longer query
    ):
        assert _primaries(world, "contracts", q) == expected, q
    assert _primaries(world, "customers", "c 02") == ["C-02"]
    assert _primaries(world, "customers", "architects llp") == ["C-09"]


def test_items_order_by_exact_primary_then_primary_then_newest(world: SeatWorld) -> None:
    """04 §16.13: an exact ``primary`` first; then the items whose ``primary`` alone matches every
    term; then the rest; within each the row written last, then ``id`` descending."""
    maya = world.place.author
    for code, name in (
        ("ACME", "Zephyr Holdings (Demo)"),  # exact for "acme"
        ("ACME-EAST", "Borealis Ltd (Demo)"),  # by primary
        ("B-200", "Acme Tools (Demo)"),  # by secondary alone
        ("ACME-WEST", "Cirrus Ltd (Demo)"),  # by primary, written last
    ):
        customer_id(world.app, maya, code=code, name=name)
    assert _primaries(world, "customers", "acme") == ["ACME", "ACME-WEST", "ACME-EAST", "B-200"]
    assert _primaries(world, "customers", "ACME") == ["ACME", "ACME-WEST", "ACME-EAST", "B-200"]
    # a page of two and its cursor walk the same order across the three steps
    walked: list[str] = []
    cursor: str | None = None
    while True:
        params = {"q": "acme", "scope": "customers", "limit": 2}
        found = _search(world, **(params if cursor is None else {**params, "cursor": cursor}))
        assert found.status_code == 200, found.text
        walked += [item["primary"] for item in found.json()["items"]]
        cursor = found.json()["next_cursor"]
        if cursor is None:
            break
    assert walked == ["ACME", "ACME-WEST", "ACME-EAST", "B-200"]


def test_status_is_what_the_single_read_shows(world: SeatWorld) -> None:
    """04 §16.13 "What is answered": the ``status`` of an obligation is the E-22 literal ``GET
    /obligations/{id}`` answers without parameters (the search reads it with the single read's
    own function, ``to_date.version_at``, at the cut of today), and null while the primary book
    has no version of its contract; a page of obligations costs the same number of statements
    whatever its size."""
    maya = world.place.author
    first = _booked(world, "SF-ORD-10002", customer=world.customers["C-02"], activate=True)
    second = _booked(world, "SF-ORD-10003", customer=world.customers["C-02"], activate=True)
    draft = _booked(world, "SF-ORD-10004", customer=world.customers["C-02"])
    for booked in (first, second):
        computed(world.place, UUID(str(booked.combination_group["id"])))
    found = {item["primary"]: item for item in _items(world, "obligations", "sf ord o1")}
    assert sorted(found) == [f"SF-ORD-1000{n}{BETWEEN}O1" for n in (2, 3, 4)]
    for booked in (first, second):
        (obligation,) = booked.obligations
        item = found[f"{booked.contract['external_id']}{BETWEEN}O1"]
        shown = get(world.app, f"/api/v1/obligations/{obligation['id']}", maya)
        assert shown.status_code == 200, shown.text
        assert item == {
            "id": str(obligation["id"]),
            "primary": f"{booked.contract['external_id']}{BETWEEN}O1",
            "secondary": SEAT,
            "status": shown.json()["satisfaction_status"],
            "href": f"/api/v1/obligations/{obligation['id']}",
        }
        # a year of seats from January, read in September: neither end of E-22
        assert item["status"] == "PARTIALLY_SATISFIED"
    assert found[f"{draft.contract['external_id']}{BETWEEN}O1"]["status"] is None

    def statements(limit: int) -> int:
        with sent() as seen:
            answered = _search(world, q="sf ord o1", scope="obligations", limit=limit)
        assert answered.status_code == 200, answered.text
        assert len(answered.json()["items"]) == min(limit, 3)
        return len(seen)

    assert statements(2) == statements(50)

    # A contract whose activation awaits its decision is stored DRAFT and reads PENDING_REVIEW
    # (T-CON-01): the search answers what GET /contracts/{id} answers.
    request = approval_request_values(
        world.place.tenant_id,
        entity_id=world.entity_id,
        subject_type="CONTRACT_ACTIVATION",
        subject_id=draft.contract["id"],
        summary="Activate SF-ORD-10004",
    )
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(approval_request).values(**request))
    single = get(world.app, f"/api/v1/contracts/{draft.contract['id']}", maya)
    assert single.status_code == 200, single.text
    assert single.json()["status"] == "PENDING_REVIEW"
    (in_review,) = _items(world, "contracts", "SF-ORD-10004")
    assert (in_review["primary"], in_review["status"]) == ("SF-ORD-10004", "PENDING_REVIEW")


def test_an_invoice_is_answered_once_in_its_newest_version(world: SeatWorld) -> None:
    """04 §16.13: a source sends an invoice again in a later version; the search answers the
    newest stored version alone — by ``source_record.version_order``, not by arrival."""
    booked = _booked(world, "SF-ORD-10002", customer=world.customers["C-02"])
    _invoice(world, "INV-8001", contracts=("SF-ORD-10002",), external_id="stripe-in-1", version=2)
    older = _invoice(
        world,
        "INV-8001-DRAFT",
        contracts=("SF-ORD-10002",),
        external_id="stripe-in-1",
        version=1,
        minutes=5,  # stored later, and still the older version
    )
    other = _invoice(world, "INV-8002", contracts=("SF-ORD-10002",))
    items = _items(world, "invoices", "inv")
    assert [item["primary"] for item in items] == ["INV-8002", "INV-8001"]
    assert str(older) not in {item["id"] for item in items}
    assert items[0] == {
        "id": str(other),
        "primary": "INV-8002",
        "secondary": "SF-ORD-10002",
        "status": None,
        "href": f"/api/v1/contracts/{booked.contract['id']}",
    }
    assert _primaries(world, "invoices", "draft") == []
