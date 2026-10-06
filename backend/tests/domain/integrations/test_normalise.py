"""DIN-2 raw source store and canonical normalisation (ENGINE_SPEC §1.3 S01-R-01 to S01-R-03; 05
ADP-02 to ADP-04, PRV-05; 04 T-SRC-01, table 15.4-B; PRD IMP-44; 03 REQ-DAT-011; control CTL-001;
BUILD_SPEC DIN-2).

World: a provisioned tenant and Maya (Revenue Accountant); records are stored in her units of work.
The CTL-001 world books PRD WLD-K-01 ``SF-ORD-10001`` through the domain commands, as
``test_streams`` does, and ingests a Stripe invoice as ``BILLING_RECORDED``.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_event,
    exception_item,
    file_object,
    import_upload,
    source_record,
    tenant,
)
from erev_api.domain.contracts.commands import book_contract
from erev_api.domain.integrations import normalise
from erev_api.domain.integrations.normalise import SourceIdentity, StoredRecord, StoreOutcome
from erev_api.domain.integrations.tokenise import tokenise
from erev_api.domain.reference.commands import (
    create_calendar,
    create_customer,
    create_entity,
    create_product,
    generate_year,
)
from erev_api.enums import (
    ContractEventType,
    FilePurpose,
    SourceObjectType,
    SourceSystem,
    TenantKind,
)
from erev_api.events.payloads import BillingRecordedV1, ContractBookedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import LocalFileStore
from erev_api.redaction import CONTACT_FIELDS
from erev_api.schemas.calendars import CalendarIn, GenerateYearIn
from erev_api.schemas.customers import CustomerIn
from erev_api.schemas.entities import EntityIn
from erev_api.schemas.products import ProductIn
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, exc, func, insert, select
from support.db import TestDatabase
from support.factories import maya_principal
from support.principals import member
from support.rows import file_object_values, import_upload_values, source_record_values

REQUEST_ID = "tests-source-records"


@dataclass(frozen=True, slots=True)
class Place:
    maya: Principal
    clock: FrozenClock
    keyring: KeyRing
    files: LocalFileStore

    @property
    def tenant_id(self) -> UUID:
        return self.maya.tenant_id

    @contextmanager
    def uow(self) -> Iterator[UnitOfWork]:
        ctx = RequestContext(
            principal=self.maya,
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
def place(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Place:
    return Place(
        maya=maya_principal(member(keyring, clock)),
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
    )


def _store(
    place: Place,
    identity: SourceIdentity,
    *,
    version_order: int,
    payload: Mapping[str, Any],
    **extra: Any,
) -> StoredRecord:
    with place.uow() as uow:
        stored = normalise.store_source_record(
            uow, identity=identity, version_order=version_order, payload=payload, **extra
        )
        uow.commit()
    return stored


def _records(place: Place, identity: SourceIdentity) -> list[dict[str, Any]]:
    return place.rows(
        select(source_record)
        .where(
            source_record.c.source_system == identity.source_system.value,
            source_record.c.object_type == identity.object_type.value,
            source_record.c.external_id == identity.external_id,
        )
        .order_by(source_record.c.version_order)
    )


def _log_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_identity_dedupe(place: Place, log_stream: io.StringIO) -> None:
    identity = SourceIdentity(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id="SF-ORD-30001",
        external_version="2026-09-01T10:00:00.000Z",
    )
    payload = {"OrderNumber": "SF-ORD-30001", "TotalAmount": "120000.00"}
    first = _store(place, identity, version_order=1788256800000, payload=payload)
    second = _store(place, identity, version_order=1788256800000, payload=payload)

    assert (first.outcome, second.outcome) == (StoreOutcome.STORED, StoreOutcome.DUPLICATE)
    assert (first.applies, second.applies) == (True, False)
    assert (second.id, second.payload_sha256) == (first.id, first.payload_sha256)
    assert [row["id"] for row in _records(place, identity)] == [first.id]
    skipped = [
        line
        for line in _log_lines(log_stream)
        if line["event"] == "source_record.duplicate_skipped"
    ]
    assert [
        (line["source_record_id"], line["source_system"], line["object_type"]) for line in skipped
    ] == [(str(first.id), "SALESFORCE", "ORDER")]
    assert skipped[0]["external_version"] == "2026-09-01T10:00:00.000Z"
    assert skipped[0]["level"] == "info"

    # The identity key refuses a direct second insert as well (ux_source_record__identity).
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session, pytest.raises(exc.IntegrityError) as excinfo:
        session.execute(
            insert(source_record).values(
                **source_record_values(
                    place.tenant_id,
                    source_system="SALESFORCE",
                    object_type="ORDER",
                    external_id="SF-ORD-30001",
                    external_version="2026-09-01T10:00:00.000Z",
                )
            )
        )
    diag = getattr(excinfo.value.orig, "diag", None)
    assert getattr(diag, "constraint_name", None) == "ux_source_record__identity"
    assert len(_records(place, identity)) == 1


def test_version_order_not_arrival(place: Place) -> None:
    version_2 = SourceIdentity(SourceSystem.SALESFORCE, SourceObjectType.ORDER, "SO-1", "2")
    version_1 = SourceIdentity(SourceSystem.SALESFORCE, SourceObjectType.ORDER, "SO-1", "1")
    newer = _store(place, version_2, version_order=2, payload={"Stage": "Closed Won"})
    older = _store(place, version_1, version_order=1, payload={"Stage": "Proposal"})

    assert (newer.outcome, older.outcome) == (StoreOutcome.STORED, StoreOutcome.STALE)
    assert older.applies is False
    # Both versions are stored; processing order is version_order, not arrival.
    assert [
        (row["external_version"], row["version_order"]) for row in _records(place, version_2)
    ] == [("1", 1), ("2", 2)]
    (item,) = place.rows(
        select(exception_item).where(exception_item.c.source_record_id == older.id)
    )
    assert (item["id"], item["code"], item["severity"], item["source"], item["status"]) == (
        older.exception_item_id,
        "STALE_SOURCE_VERSION",
        "WARNING",
        "INTEGRATION",
        "OPEN",
    )
    assert item["message"] == (
        "SALESFORCE ORDER SO-1 version 1 is older than the processed version 2. "
        "It was recorded and not applied."
    )
    assert (item["title"], item["business_key"]) == ("Stale source version", "SO-1")
    assert str(item["exception_no"]).startswith("EXC-")
    assert (
        place.rows(select(exception_item).where(exception_item.c.source_record_id == newer.id))
        == []
    )

    # A later version above the highest stored one applies again.
    latest = SourceIdentity(SourceSystem.SALESFORCE, SourceObjectType.ORDER, "SO-1", "3")
    assert _store(place, latest, version_order=3, payload={"Stage": "Amended"}).applies


def test_file_row_identity(place: Place) -> None:
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    stored_file = file_object_values(place.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
    upload = import_upload_values(place.tenant_id, file_object_id=stored_file["id"])
    with tenant_session(context) as session:
        session.execute(insert(file_object).values(**stored_file))
        session.execute(insert(import_upload).values(**upload))
    upload_id = UUID(str(upload["id"]))

    identity = normalise.file_row_identity(
        source_system=SourceSystem.LEGACY_TEMPLATE_V1,
        object_type=SourceObjectType.SSP_ROW,
        import_upload_id=upload_id,
        sheet_name="SKU Setup",
        row_number=2,
    )
    assert (identity.external_id, identity.external_version) == (f"{upload_id}:SKU Setup:2", "1")
    stored = _store(
        place,
        identity,
        version_order=1,
        payload={"SKU Name": "Hardware 1", "SKU Unit List Price": "100"},
        import_upload_id=upload_id,
    )
    (row,) = _records(place, identity)
    assert (
        row["id"],
        row["source_system"],
        row["object_type"],
        row["external_id"],
        row["external_version"],
        row["import_upload_id"],
        row["idempotency_key"],
    ) == (
        stored.id,
        "LEGACY_TEMPLATE_V1",
        "SSP_ROW",
        f"{upload_id}:SKU Setup:2",
        "1",
        upload_id,
        None,
    )
    assert (
        place.scalar(
            select(func.count())
            .select_from(source_record)
            .where(source_record.c.import_upload_id == upload_id)
        )
        == 1
    )
    with pytest.raises(ValueError):
        normalise.file_row_external_id(upload_id, "SKU Setup", 0)


def test_import_event_idempotency_key() -> None:
    file_sha256 = hashlib.sha256(b"Contract Progress Tracking, September 2026").hexdigest()
    business_key = "Contract 1 / POB #1 / Hardware 1"
    key = normalise.import_event_key(
        file_sha256=file_sha256,
        template_code="legacy_progress_tracking",
        template_version=1,
        business_key=business_key,
        ordinal=1,
    )
    expected = hashlib.sha256(
        f"{file_sha256}:legacy_progress_tracking:1:{business_key}:1".encode()
    ).hexdigest()
    assert key == "imp:" + expected
    assert len(key) == 68
    second = normalise.import_event_key(
        file_sha256=file_sha256,
        template_code="legacy_progress_tracking",
        template_version=1,
        business_key=business_key,
        ordinal=2,
    )
    assert second != key and second.startswith("imp:")
    # Adapter and API keys (S01-R-03; ADP-03).
    identity = SourceIdentity(SourceSystem.STRIPE, SourceObjectType.INVOICE, "in_1PZ001", "evt_7")
    assert (
        normalise.adapter_event_key(identity, 1)
        == "src:" + hashlib.sha256(b"STRIPE:INVOICE:in_1PZ001:evt_7:1").hexdigest()
    )
    assert normalise.api_event_key("0f8e2c1a-5d7b-4e3f-9a61-2c4d8b7e1f30", 2) == (
        "0f8e2c1a-5d7b-4e3f-9a61-2c4d8b7e1f30:2"
    )
    with pytest.raises(ValueError):
        normalise.adapter_event_key(identity, 0)


def test_payload_tokenised_before_store(place: Place) -> None:
    identity = SourceIdentity(SourceSystem.STRIPE, SourceObjectType.CUSTOMER, "cus_Q1", "evt_1")
    payload: dict[str, Any] = {name: f"{name} value" for name in sorted(CONTACT_FIELDS)}
    payload |= {
        "id": "cus_Q1",
        "balance": "0.00",
        "customer_address": {"line1": "12 Harbour Row", "city": "Portland", "postal_code": None},
    }
    stored = _store(place, identity, version_order=1, payload=payload)

    (row,) = _records(place, identity)
    key_id = place.scalar(select(tenant.c.audit_hmac_key_id).where(tenant.c.id == place.tenant_id))
    key = place.keyring.tenant_audit_key(str(key_id))

    def token(text: str) -> dict[str, str]:
        return {"$pii": "hmac:" + hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()}

    kept = row["payload"]
    for name in sorted(CONTACT_FIELDS - {"customer_address"}):
        assert kept[name] == token(f"{name} value"), name
    assert kept["customer_address"] == {
        "line1": token("12 Harbour Row"),
        "city": token("Portland"),
        "postal_code": None,
    }
    assert (kept["id"], kept["balance"]) == ("cus_Q1", "0.00")
    text = json.dumps(kept)
    assert "12 Harbour Row" not in text
    assert all(f"{name} value" not in text for name in CONTACT_FIELDS)
    # payload_sha256 is taken over the stored canonical (tokenised) payload.
    assert str(row["payload_sha256"]).strip() == sha256_hex(kept) == stored.payload_sha256
    assert stored.payload_sha256 != sha256_hex(payload)
    assert tokenise(key, kept) == kept


@dataclass(frozen=True, slots=True)
class Booked:
    place: Place
    contract_id: UUID


@pytest.fixture
def booked(place: Place) -> Booked:
    with place.uow() as uow:
        calendar = create_calendar(
            uow, body=CalendarIn(code="GREGORIAN", name="Gregorian calendar")
        )
        generate_year(uow, calendar_id=calendar.id, body=GenerateYearIn(fiscal_year=2026))
        create_entity(
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
        create_product(
            uow, body=ProductIn(code="AVM-PLAT-ENT", name="Platform, enterprise tier, 12 months")
        )
        booking = book_contract(
            uow,
            body=ContractBookedV1.model_validate(
                {
                    "external_id": "SF-ORD-10001",
                    "customer_id": str(buyer.id),
                    "contracting_entity_code": "AVM-US",
                    "transaction_currency": "USD",
                    "inception_date": "2026-01-01",
                    "lines": [
                        {
                            "obligation_key": "O1",
                            "product_code": "AVM-PLAT-ENT",
                            "quantity": "1",
                            "total_price": {"amount": "120000.00", "currency": "USD"},
                            "start_date": "2026-01-01",
                            "end_date": "2026-12-31",
                        }
                    ],
                }
            ),
        )
        uow.commit()
    return Booked(place=place, contract_id=UUID(str(booking.contract["id"])))


@pytest.mark.control("CTL-001")
def test_ctl_001_duplicate_source_version_creates_no_event(booked: Booked) -> None:
    place = booked.place
    identity = SourceIdentity(
        SourceSystem.STRIPE, SourceObjectType.INVOICE, "in_1PZ001", "evt_1PZ001"
    )
    payload = {
        "id": "in_1PZ001",
        "number": "INV-US-5001",
        "amount_due": "10000.00",
        "currency": "usd",
        "customer_email": "ap@pellworth.example",
    }
    event_key = normalise.adapter_event_key(identity, 1)

    def ingest() -> tuple[StoredRecord, Mapping[str, Any]]:
        with place.uow() as uow:
            stored = normalise.store_source_record(
                uow, identity=identity, version_order=1767225600, payload=payload
            )
            (row,) = append_events(
                uow,
                contract_id=booked.contract_id,
                expected_stream_version=1,
                events=[
                    EventIn(
                        event_type=ContractEventType.BILLING_RECORDED,
                        effective_date=date(2026, 2, 1),
                        payload=BillingRecordedV1.model_validate(
                            {
                                "invoice_number": "INV-US-5001",
                                "line_external_id": "INV-US-5001-1",
                                "amount": {"amount": "10000.00", "currency": "USD"},
                                "issue_date": "2026-02-01",
                            }
                        ),
                        idempotency_key=event_key,
                        source_record_id=stored.id,
                    )
                ],
                origin="ADAPTER",
            )
            uow.commit()
        return stored, row

    first, first_event = ingest()
    second, replayed = ingest()

    assert (first.outcome, second.outcome) == (StoreOutcome.STORED, StoreOutcome.DUPLICATE)
    assert second.id == first.id
    assert (replayed["id"], replayed["stream_version"]) == (first_event["id"], 2)
    assert [row["id"] for row in _records(place, identity)] == [first.id]
    events = place.rows(
        select(contract_event).where(contract_event.c.contract_id == booked.contract_id)
    )
    assert sorted((row["stream_version"], row["event_type"]) for row in events) == [
        (1, "CONTRACT_BOOKED"),
        (2, "BILLING_RECORDED"),
    ]
    (billing,) = [row for row in events if row["idempotency_key"] == event_key]
    assert (billing["origin"], billing["source_record_id"]) == ("ADAPTER", first.id)
    assert (
        place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == booked.contract_id)
        )
        == 2
    )
    # The index itself refuses a second event with the key (ux_contract_event__idempotency).
    context = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    duplicate = {**billing, "id": new_id(), "stream_version": 3}
    duplicate.pop("recorded_at", None)
    duplicate.pop("record_seq", None)
    with tenant_session(context) as session, pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(insert(contract_event).values(**duplicate))
    assert getattr(getattr(excinfo.value.orig, "diag", None), "constraint_name", None) in (
        "ux_contract_event__idempotency",
        None,
    )
