"""Contract headers, combination groups and event streams (04 T-CON-01, T-CON-03 to T-CON-05,
T-CON-10, §16.3, DB-08; dev-guide §5.11 DG-KRN-EVT-01; 05 RCP-17, RCP-22; 03 REQ-CON-001; BUILD_SPEC
CTR-1).

Maya holds Revenue Accountant (``contract.create``, ``masterdata.maintain``) in a fresh workspace.
The world is created through the reference commands: a monthly calendar with fiscal year 2026, the
entity AVM-US (USD, America/New_York), the customer C-01 (PRD WLD-C-01) and the products
AVM-PLAT-ENT and AVM-IMPL-STD. The booking is PRD WLD-K-01 ``SF-ORD-10001``. The frozen clock reads
2026-09-12T12:00:00Z; database timestamps (``recorded_at``) are asserted by order and presence only
(DG-KRN-TIME-06).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, timedelta
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    customer,
    obligation,
)
from erev_api.domain.contracts.commands import BookedContract, book_contract
from erev_api.domain.reference.commands import (
    create_calendar,
    create_customer,
    create_entity,
    create_product,
    generate_year,
)
from erev_api.enums import ContractEventType, PrincipalKind, TenantKind
from erev_api.events.payloads import (
    ContractActivatedV1,
    ContractBookedV1,
    DeliveryRecordedV1,
    SignificantChangeFlaggedV1,
)
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.schemas.calendars import CalendarIn, GenerateYearIn
from erev_api.schemas.customers import CustomerIn
from erev_api.schemas.entities import EntityIn
from erev_api.schemas.products import ProductIn
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, select
from support.db import TestDatabase
from support.principals import Member, member

REQUEST_ID = "tests-contract-streams"
PLATFORM = "AVM-PLAT-ENT"
IMPLEMENTATION = "AVM-IMPL-STD"


def maya_principal(someone: Member) -> Principal:
    """Maya with the Revenue Accountant permissions for every entity (PRD §5.6)."""
    permissions = DEFAULT_ROLES["revenue_accountant"]
    scopes: dict[str, Literal["*"] | frozenset[UUID]] = {code: "*" for code in permissions}
    return Principal(
        kind=PrincipalKind.USER,
        id=someone.user_id,
        tenant_id=someone.tenant_id,
        membership_id=someone.membership_id,
        display_name="Maya Okafor",
        roles=("revenue_accountant",),
        permissions=permissions,
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


@dataclass(frozen=True, slots=True)
class World:
    maya: Principal
    clock: FrozenClock
    keyring: KeyRing
    files: LocalFileStore
    entity_id: UUID = UUID(int=0)
    customer_id: UUID = UUID(int=0)
    products: Mapping[str, UUID] = MappingProxyType({})

    @property
    def tenant_id(self) -> UUID:
        return self.maya.tenant_id

    @contextmanager
    def uow(self, principal: Principal | None = None) -> Iterator[UnitOfWork]:
        ctx = RequestContext(
            principal=principal or self.maya,
            tenant_kind=TenantKind.PRODUCTION,
            request_id=REQUEST_ID,
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=self.clock.now(),
            format_locale="en-US",
        )
        with unit_of_work(ctx, clock=self.clock, keyring=self.keyring, files=self.files) as uow:
            yield uow

    def rows(self, statement: Select[Any]) -> list[dict[str, Any]]:
        context = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    def scalar(self, statement: Select[Any]) -> Any:
        context = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            return session.execute(statement).scalar_one()


@pytest.fixture
def world(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> World:
    base = World(
        maya=maya_principal(member(keyring, clock)),
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
    )
    with base.uow() as uow:
        calendar = create_calendar(
            uow, body=CalendarIn(code="GREGORIAN", name="Gregorian calendar")
        )
        generate_year(uow, calendar_id=calendar.id, body=GenerateYearIn(fiscal_year=2026))
        entity = create_entity(
            uow,
            body=EntityIn(
                code="AVM-US",
                name="Avenmoor Software Inc. (Demo)",
                functional_currency="USD",
                time_zone="America/New_York",
                calendar_id=calendar.id,
            ),
        )
        buyer = create_customer(
            uow, body=CustomerIn(code="C-01", name="Pellworth Logistics Inc. (Demo)")
        )
        products = {
            code: create_product(uow, body=ProductIn(code=code, name=name)).id
            for code, name in (
                (PLATFORM, "Platform, enterprise tier, 12 months"),
                (IMPLEMENTATION, "Implementation, standard"),
            )
        }
        uow.commit()
    return replace(
        base, entity_id=entity.id, customer_id=buyer.id, products=MappingProxyType(products)
    )


def booking_data(world: World, **extra: Any) -> dict[str, Any]:
    """PRD WLD-K-01: SF-ORD-10001 for C-01, AVM-US, USD, inception 2026-01-01."""
    return {
        "external_id": "SF-ORD-10001",
        "customer_id": str(world.customer_id),
        "contracting_entity_code": "AVM-US",
        "transaction_currency": "USD",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PLATFORM,
                "quantity": "1",
                "total_price": {"amount": "120000.00", "currency": "USD"},
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
            {
                "obligation_key": "O2",
                "product_code": IMPLEMENTATION,
                "quantity": "1",
                "total_price": {"amount": "15000.00", "currency": "USD"},
            },
        ],
        **extra,
    }


def booking(world: World, **extra: Any) -> ContractBookedV1:
    return ContractBookedV1.model_validate(booking_data(world, **extra))


def book(world: World) -> BookedContract:
    with world.uow() as uow:
        booked = book_contract(uow, body=booking(world))
        uow.commit()
    return booked


def change(description: str = "Customer asked for a scope review") -> EventIn:
    return EventIn(
        event_type=ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
        effective_date=date(2026, 2, 1),
        payload=SignificantChangeFlaggedV1(description=description),
    )


def delivery(key: str | None = None, obligation_key: str = "O1") -> EventIn:
    return EventIn(
        event_type=ContractEventType.DELIVERY_RECORDED,
        effective_date=date(2026, 2, 15),
        payload=DeliveryRecordedV1(obligation_key=obligation_key, quantity="1", trigger="DELIVERY"),
        obligation_keys=(obligation_key,),
        idempotency_key=key,
    )


def stream_of(world: World, contract_id: UUID) -> list[dict[str, Any]]:
    return world.rows(
        select(contract_event)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )


def head_of(world: World, contract_id: UUID) -> int:
    return int(
        world.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    )


def test_book_contract_creates_draft_group_and_obligations(world: World) -> None:
    booked = book(world)
    header = booked.contract
    contract_id = header["id"]
    stored = world.rows(select(contract))
    assert [row["id"] for row in stored] == [contract_id]
    assert (
        header["contract_no"],
        header["external_id"],
        header["status"],
        header["head_stream_version"],
        header["customer_id"],
        header["contracting_entity_id"],
        header["transaction_currency"],
        header["inception_date"],
        header["source_system"],
    ) == (
        "CON-000001",
        "SF-ORD-10001",
        "DRAFT",
        1,
        world.customer_id,
        world.entity_id,
        "USD",
        date(2026, 1, 1),
        "MANUAL_UI",
    )

    groups = world.rows(select(combination_group))
    assert [
        (group["id"], group["code"], group["is_singleton"], group["status"])
        + (group["transaction_currency"], group["inception_date"], group["criterion"])
        for group in groups
    ] == [
        (
            header["combination_group_id"],
            "CG-CON-000001",
            True,
            "APPLIED",
            "USD",
            date(2026, 1, 1),
            None,
        )
    ]

    events = stream_of(world, contract_id)
    assert len(events) == 1
    event = events[0]
    assert (
        event["stream_version"],
        event["event_type"],
        event["schema_version"],
        event["effective_date"],
        event["origin"],
        event["is_manual"],
        event["request_id"],
        event["contracting_entity_id"],
        event["idempotency_key"],
    ) == (
        1,
        "CONTRACT_BOOKED",
        1,
        date(2026, 1, 1),
        "API",
        False,
        REQUEST_ID,
        world.entity_id,
        None,
    )
    assert event["recorded_at"] is not None and event["record_seq"] > 0
    assert event == dict(booked.event)
    assert event["payload_sha256"] == sha256_hex(event["payload"])
    payload = event["payload"]
    assert (payload["external_id"], payload["customer_id"], payload["customer"]) == (
        "SF-ORD-10001",
        str(world.customer_id),
        None,
    )
    assert [line["obligation_key"] for line in payload["lines"]] == ["O1", "O2"]
    assert payload["lines"][0]["total_price"] == {"amount": "120000.00", "currency": "USD"}

    members = world.rows(select(combination_group_member))
    assert [
        (row["combination_group_id"], row["contract_id"], row["join_event_id"])
        + (row["valid_to_known_at"], row["leave_event_id"])
        for row in members
    ] == [(header["combination_group_id"], contract_id, event["id"], None, None)]
    assert members[0]["valid_from_known_at"] == event["recorded_at"]

    lines = world.rows(select(obligation).order_by(obligation.c.line_sequence))
    assert [
        (row["obligation_key"], row["product_id"], row["legacy_record_key"])
        + (row["created_by_event_id"], row["line_sequence"], row["parent_obligation_id"])
        for row in lines
    ] == [
        ("O1", world.products[PLATFORM], "SF-ORD-10001 O1 AVM-PLAT-ENT", event["id"], 1, None),
        (
            "O2",
            world.products[IMPLEMENTATION],
            "SF-ORD-10001 O2 AVM-IMPL-STD",
            event["id"],
            2,
            None,
        ),
    ]
    assert event["obligation_ids"] == [row["id"] for row in lines]
    assert [row["id"] for row in booked.obligations] == [row["id"] for row in lines]
    # The append marked the new group dirty (05 RCP-17).
    assert groups[0]["dirty_since"] == world.clock.now()

    # AUD-FACT summaries of the event, contract, membership and obligations; AUD-CMD of the group.
    audited = world.rows(
        select(audit_event.c.action, audit_event.c.object_type, audit_event.c.detail)
        .where(audit_event.c.request_id == REQUEST_ID, audit_event.c.object_type != "calendar")
        .order_by(audit_event.c.chain_seq)
    )
    actions = [(row["action"], row["object_type"]) for row in audited]
    assert actions[-5:] == [
        ("combination_group.create", "combination_group"),
        ("contract_event.append", "contract_event"),
        ("contract.book", "contract"),
        ("combination_group_member.create", "combination_group_member"),
        ("obligation.create", "obligation"),
    ]
    assert audited[-4]["detail"]["ids"] == [str(event["id"])]
    assert sorted(audited[-1]["detail"]["ids"]) == sorted(str(row["id"]) for row in lines)


def test_append_consecutive_stream_versions(world: World) -> None:
    booked = book(world)
    contract_id = booked.contract["id"]
    with world.uow() as uow:
        appended = append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=1,
            events=[change(), delivery()],
            origin="API",
        )
        uow.commit()
    assert [row["stream_version"] for row in appended] == [2, 3]
    o1 = booked.obligations[0]["id"]
    assert (appended[0]["obligation_ids"], appended[1]["obligation_ids"]) == ([], [o1])
    events = stream_of(world, contract_id)
    assert [(row["stream_version"], row["event_type"]) for row in events] == [
        (1, "CONTRACT_BOOKED"),
        (2, "SIGNIFICANT_CHANGE_FLAGGED"),
        (3, "DELIVERY_RECORDED"),
    ]
    # Server recorded_at: one transaction shares it, later than the booking's; record_seq rises.
    assert events[1]["recorded_at"] == events[2]["recorded_at"] >= events[0]["recorded_at"]
    assert events[0]["record_seq"] < events[1]["record_seq"] < events[2]["record_seq"]
    assert head_of(world, contract_id) == 3

    # A stale expected_stream_version (DB-08; API-C-08).
    with world.uow() as uow, pytest.raises(Problem) as excinfo:
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=1,
            events=[change("Stale")],
            origin="API",
        )
    problem = excinfo.value
    assert (problem.status, problem.slug, problem.code) == (
        412,
        "precondition-failed",
        "EREV-EVT-001",
    )
    assert [(error.field, error.rule_id) for error in problem.errors] == [
        ("If-Match", "EREV-EVT-001")
    ]
    assert len(stream_of(world, contract_id)) == 3
    assert head_of(world, contract_id) == 3
    # An invisible contract is not found.
    with world.uow() as uow, pytest.raises(Problem) as excinfo:
        append_events(
            uow, contract_id=new_id(), expected_stream_version=0, events=[change()], origin="API"
        )
    assert excinfo.value.slug == "not-found"


def test_idempotency_key_replay_creates_no_event(world: World) -> None:
    booked = book(world)
    contract_id = booked.contract["id"]
    shipment = delivery(key="SALESFORCE:SHIP-5001:1")
    with world.uow() as uow:
        (first,) = append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=1,
            events=[shipment],
            origin="ADAPTER",
        )
        uow.commit()
    assert first["stream_version"] == 2
    # A second append with the same key creates no row, whatever version it expects.
    for expected in (1, 2):
        with world.uow() as uow:
            (replayed,) = append_events(
                uow,
                contract_id=contract_id,
                expected_stream_version=expected,
                events=[shipment],
                origin="ADAPTER",
            )
            uow.commit()
        assert (replayed["id"], replayed["stream_version"]) == (first["id"], 2)
    assert [row["idempotency_key"] for row in stream_of(world, contract_id)] == [
        None,
        "SALESFORCE:SHIP-5001:1",
    ]
    assert head_of(world, contract_id) == 2
    # A batch mixing the replay with a new key appends only the new event.
    with world.uow() as uow:
        replayed, second = append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=2,
            events=[shipment, delivery(key="SALESFORCE:SHIP-5002:1")],
            origin="ADAPTER",
        )
        uow.commit()
    assert (replayed["id"], second["stream_version"]) == (first["id"], 3)
    assert head_of(world, contract_id) == 3
    # Keys repeated within one append are a programming error.
    with world.uow() as uow, pytest.raises(ValueError):
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=3,
            events=[delivery(key="K-1"), delivery(key="K-1")],
            origin="ADAPTER",
        )


def test_append_marks_group_dirty(world: World) -> None:
    booked = book(world)
    contract_id, group_id = booked.contract["id"], booked.contract["combination_group_id"]
    booked_at = world.clock.now()
    dirty = select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    assert world.scalar(dirty) == booked_at

    world.clock.advance(timedelta(hours=2))
    later = world.clock.now()
    with world.uow() as uow:
        append_events(
            uow, contract_id=contract_id, expected_stream_version=1, events=[change()], origin="API"
        )
        # In the same transaction as the append …
        assert uow.session.execute(dirty).scalar_one() == later
        # … and invisible to other transactions until it commits.
        assert world.scalar(dirty) == booked_at
        # Left without commit: the unit of work rolls back.
    assert world.scalar(dirty) == booked_at
    assert len(stream_of(world, contract_id)) == 1

    with world.uow() as uow:
        append_events(
            uow, contract_id=contract_id, expected_stream_version=1, events=[change()], origin="API"
        )
        uow.commit()
    assert world.scalar(dirty) == later
    assert head_of(world, contract_id) == 2


def test_book_contract_refusals(world: World) -> None:
    # Every finding is listed (DG-CMD-03), and nothing is written.
    body = booking(
        world,
        customer_id=str(new_id()),
        contracting_entity_code="AVM-XX",
        lines=[
            {
                "obligation_key": "O1",
                "product_code": PLATFORM,
                "quantity": "1",
                "total_price": {"amount": "120000.00", "currency": "EUR"},
            },
            {
                "obligation_key": "O2",
                "product_code": "AVM-UNKNOWN",
                "quantity": "1",
                "total_price": {"amount": "15000.00", "currency": "USD"},
            },
        ],
    )
    with world.uow() as uow, pytest.raises(Problem) as excinfo:
        book_contract(uow, body=body)
    assert excinfo.value.slug == "validation-failed"
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("customer_id", "T-REF-19"),
        ("contracting_entity_code", "T-REF-01"),
        ("lines.1.product_code", "T-REF-20"),
        ("lines.0.total_price", "REQ-CON-019"),
    ]
    with world.uow() as uow, pytest.raises(Problem) as excinfo:
        book_contract(uow, body=booking(world, transaction_currency="EUR"))
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("transaction_currency", "T-REF-09"),
        ("lines.0.total_price", "REQ-CON-019"),
        ("lines.1.total_price", "REQ-CON-019"),
    ]
    assert world.rows(select(contract)) == []

    # The first valid booking still takes CON-000001; a second one with the same external id is
    # refused (REQ-DAT-017).
    assert book(world).contract["contract_no"] == "CON-000001"
    with world.uow() as uow, pytest.raises(Problem) as excinfo:
        book_contract(uow, body=booking(world))
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("external_id", "REQ-DAT-017")
    ]

    # ``customer {code, name}`` creates a customer that does not exist yet.
    named = {"code": "C-09", "name": "Harrowgate Freight Ltd (Demo)"}
    body = booking(world, external_id="SF-ORD-10002", customer_id=None, customer=named)
    with world.uow() as uow:
        booked = book_contract(uow, body=body, origin="IMPORT")
        uow.commit()
    created = world.rows(select(customer.c.id, customer.c.code).where(customer.c.code == "C-09"))
    assert [row["id"] for row in created] == [booked.contract["customer_id"]]
    assert booked.contract["contract_no"] == "CON-000002"
    assert booked.event["origin"] == "IMPORT"

    # A principal without contract.create for the entity does not see it (DG-CMD-01).
    scopes: dict[str, Literal["*"] | frozenset[UUID]] = {"contract.create": frozenset({new_id()})}
    outsider = replace(world.maya, permission_scopes=MappingProxyType(scopes))
    with world.uow(outsider) as uow, pytest.raises(Problem) as excinfo:
        book_contract(uow, body=booking(world, external_id="SF-ORD-10003"))
    assert excinfo.value.slug == "not-found"


def test_append_refuses_unknown_obligation_and_projects_status(world: World) -> None:
    booked = book(world)
    contract_id = booked.contract["id"]
    with world.uow() as uow, pytest.raises(Problem) as excinfo:
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=1,
            events=[change(), delivery(obligation_key="O9")],
            origin="API",
        )
    assert [(error.field, error.rule_id) for error in excinfo.value.errors] == [
        ("events.1.obligation_keys", "T-CON-10")
    ]
    assert head_of(world, contract_id) == 1

    # CONTRACT_ACTIVATED projects ACTIVE in the statement that raises the head (DB-18; L3-1-Q-17).
    activated = EventIn(
        event_type=ContractEventType.CONTRACT_ACTIVATED,
        effective_date=date(2026, 1, 1),
        payload=ContractActivatedV1.model_validate(
            {"checklist": [{"code": "SOURCE_REFERENCE", "passed": True}]}
        ),
    )
    with world.uow() as uow:
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=1,
            events=[activated],
            origin="SYSTEM",
        )
        uow.commit()
    header = world.rows(select(contract).where(contract.c.id == contract_id))[0]
    assert (header["status"], header["activated_at"], header["head_stream_version"]) == (
        "ACTIVE",
        world.clock.now(),
        2,
    )
    # A payload of another model is a programming error.
    with world.uow() as uow, pytest.raises(TypeError):
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=2,
            events=[replace(activated, payload=SignificantChangeFlaggedV1(description="x"))],
            origin="API",
        )
