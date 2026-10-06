"""Stripe ingestion over a database (05 §5.1 canonical ingestion, ADP-01 to ADP-03, ADP-17; 04
T-SRC-01, T-SRC-04, T-SRC-05, T-INT-02, T-INT-04, §16.3 ``BILLING_RECORDED`` and
``CREDIT_MEMO_RECORDED``; 03 REQ-INT-005; PRD WLD-F-31, J-23.6; BUILD_SPEC DIN-13 named case
``test_subscription_and_invoices``).

DB-bound: every test needs the test database. World: ``support.integrations`` — the J-23 tenant
with ``QUAY-US`` and the WLD-F-36 products — and an ACTIVE Stripe connection over the in-process
mock (WLD-F-31: subscription ``sub_DEMO0001`` of 1,200.00 per year on ``QUAY-PLAT``, invoice
``in_DEMO0001`` in two versions, credit note ``cn_DEMO0001`` of 100.00, a five-event feed with a
repeated event id and an out-of-order invoice version). The connection carries no ``secret_ref``:
a mock connection sends no credential (05 KEY-09).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.mocks import stripe as st_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    contract,
    contract_event,
    contract_source_link,
    customer,
    exception_item,
    external_id_map,
    integration_connection,
    obligation,
    source_invoice,
    source_invoice_line,
    source_order,
    source_order_line,
    source_record,
    sync_run,
)
from erev_api.domain.integrations import commands
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support.adapter_secrets import serve_adapter_secrets, tenant_ref
from support.db import TestDatabase
from support.http import asgi_client, call
from support.integrations import (
    INTEGRATIONS,
    IntegrationWorld,
    connection,
    integration_world,
    run,
    sync,
)
from support.reference import post

MOCK_BASE = f"{mocks.MOCKS_PREFIX}{st_mock.PREFIX}"
MONEY_1200 = {"amount": "1200.00", "currency": "USD"}
MONEY_100 = {"amount": "100.00", "currency": "USD"}
# A secret the test's store serves; the reference is its name in the workspace's own namespace
# (``tenant_ref``; 05 KEY-09 rev 1.47).
WEBHOOK_SECRET_NAME = "stripe-webhook-secret"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Iterator[IntegrationWorld]:
    with integration_world(app, keyring, clock, app_settings) as built:
        yield built


def _stripe(world: IntegrationWorld, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "stripe-quayside",
        "name": "Stripe (mock)",
        "adapter": "STRIPE",
        "direction": "INBOUND",
        "base_url": MOCK_BASE,
        "config": {"default_legal_entity": "QUAY-US"},
    }
    body.update(over)
    return connection(world, **body)


def _mock(world: IntegrationWorld) -> st_mock.StripeMock:
    adapter = world.app.state.mocks.adapters[st_mock.CODE]
    assert isinstance(adapter, st_mock.StripeMock)
    return adapter


def _events(world: IntegrationWorld, contract_id: UUID) -> list[dict[str, Any]]:
    return world.rows(
        select(contract_event)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )


def _stated(payload: dict[str, Any]) -> dict[str, Any]:
    """The members a stored payload states: the model's absent optional members are null."""
    return {name: value for name, value in payload.items() if value is not None}


def test_subscription_and_invoices(world: IntegrationWorld) -> None:
    """BUILD_SPEC DIN-13 / PRD J-23.6 / 05 ADP-17: subscription ``sub_DEMO0001`` (1,200.00 per
    year) creates a DRAFT contract with its item as the line; invoice ``in_DEMO0001`` creates a
    ``BILLING_RECORDED`` with the service period 01 Sep 2026 – 31 Aug 2027 and credit note
    ``cn_DEMO0001`` a ``CREDIT_MEMO_RECORDED`` naming the invoice; the repeated event id creates
    nothing; each object is fetched once, before it is applied."""
    target = _stripe(world)
    # J-23.6 "tests": a mock connection carries no credential reference (05 KEY-09) and its probe
    # — one page of the feed, a single attempt — succeeds
    assert target["secret_ref"] is None
    tested = post(world.app, f"{INTEGRATIONS}/{target['id']}/test", world.nikhil, {})
    assert tested.status_code == 200, tested.text
    assert tested.json()["last_test_result"] == "SUCCESS"
    _mock(world).served.clear()  # the probe's request is not part of the sync below

    row, finished = sync(world, target)

    assert row["status"] == "SUCCEEDED", row["problem"]
    assert row["record_count"] == 3 and row["exception_count"] == 1  # the out-of-order version
    totals = {"count": 3, "amount_by_currency": {"USD": "2300.00"}}  # 1200 + 1200 - 100
    for side in ("source_totals", "loaded_totals"):
        assert {key: row[side][key] for key in totals} == totals, side
    assert row["source_totals"]["sha256"] == row["loaded_totals"]["sha256"]
    counts = finished["result"]["counts"]
    assert counts["notifications"] == 5 and counts["duplicates"] == 1  # evt_DEMO0002 twice
    assert counts["fetched"] == 3 and counts["records"] == 3 and counts["stale"] == 1
    assert counts["contracts_booked"] == 1 and counts["customers_created"] == 1
    assert (counts["documents"], counts["billing_events"], counts["credit_memo_events"]) == (
        2,
        1,
        1,
    )
    assert counts["failures"] == 0 and counts["gaps"] == 0

    # each object is fetched before it is applied, once: the feed, then the three objects — the
    # invoice at its current version 2; the notified version 1 is never fetched (ADP-01, ADP-17)
    assert _mock(world).served == [
        "events:0",
        "subscription:sub_DEMO0001",
        "invoice:in_DEMO0001:2",
        "credit_note:cn_DEMO0001",
    ]
    records = world.rows(select(source_record))
    assert sorted((r["object_type"], r["external_id"], r["external_version"]) for r in records) == [
        ("CREDIT_MEMO", "cn_DEMO0001", "1"),
        ("INVOICE", "in_DEMO0001", "2"),
        ("ORDER", "sub_DEMO0001", "1"),
    ]
    assert all(r["sync_run_id"] == row["id"] and r["source_system"] == "STRIPE" for r in records)
    by_type = {r["object_type"]: r for r in records}

    # the subscription is the contract source: a DRAFT with its item as the line
    [booked] = world.rows(select(contract))
    assert (booked["external_id"], booked["status"], booked["source_system"]) == (
        "sub_DEMO0001",
        "DRAFT",
        "STRIPE",
    )
    # 05 ADP-17 rev 1.204 (item ACT-FLAGS-1): the two terms the subscription's metadata states
    # reach its contract — the scenario states both false.
    assert (booked["acceptance_clause"], booked["side_letter"]) == (False, False)
    [order] = world.rows(select(source_order))
    assert (order["external_order_id"], order["transaction_currency"]) == ("sub_DEMO0001", "USD")
    [item] = world.rows(
        select(source_order_line).where(source_order_line.c.source_order_id == order["id"])
    )
    assert (item["line_external_id"], item["product_code"]) == ("si_DEMO0001", "QUAY-PLAT")
    assert item["quantity"] == Decimal(1) and item["total_price"] == Decimal("1200.00")
    keys = world.rows(
        select(obligation.c.obligation_key).where(obligation.c.contract_id == booked["id"])
    )
    assert [key["obligation_key"] for key in keys] == ["si_DEMO0001"]
    [buyer] = world.rows(select(customer))
    assert (buyer["external_id"], buyer["source_system"]) == ("cus_DEMO0001", "STRIPE")
    assert booked["customer_id"] == buyer["id"]
    links = world.rows(select(external_id_map).where(external_id_map.c.valid_to.is_(None)))
    assert sorted((link["object_type"], link["external_id"]) for link in links) == [
        ("contract", "sub_DEMO0001"),
        ("customer", "cus_DEMO0001"),
    ]

    # the documents as the source states them (T-SRC-04 / T-SRC-05), signed, with their periods
    stored = {
        doc["external_invoice_id"]: doc
        for doc in world.rows(select(source_invoice).order_by(source_invoice.c.document_kind))
    }
    assert sorted(stored) == ["cn_DEMO0001", "in_DEMO0001"]
    invoice, note = stored["in_DEMO0001"], stored["cn_DEMO0001"]
    assert (
        invoice["document_kind"],
        invoice["invoice_number"],
        invoice["external_version"],
        str(invoice["issue_date"]),
        str(invoice["due_date"]),
        invoice["total_amount"],
        invoice["currency"],
        invoice["legal_entity_code"],
    ) == (
        "INVOICE",
        "QUAY-0001",
        "2",
        "2026-09-01",
        "2026-10-01",
        Decimal("1200.00"),
        "USD",
        "QUAY-US",
    )
    assert (
        note["document_kind"],
        note["invoice_number"],
        str(note["issue_date"]),
        note["total_amount"],
        note["credited_invoice_external_id"],
    ) == ("CREDIT_MEMO", "QUAY-CN-0001", "2026-09-06", Decimal("-100.00"), "in_DEMO0001")
    assert invoice["source_record_id"] == by_type["INVOICE"]["id"]
    assert note["source_record_id"] == by_type["CREDIT_MEMO"]["id"]
    assert invoice["customer_id"] == buyer["id"] == note["customer_id"]
    [invoice_line] = world.rows(
        select(source_invoice_line).where(source_invoice_line.c.source_invoice_id == invoice["id"])
    )
    assert (
        invoice_line["line_external_id"],
        invoice_line["contract_ref"],
        invoice_line["product_code"],
        invoice_line["amount"],
        str(invoice_line["service_period_start"]),
        str(invoice_line["service_period_end"]),
    ) == (
        "il_DEMO0001",
        "sub_DEMO0001",
        "QUAY-PLAT",
        Decimal("1200.00"),
        "2026-09-01",
        "2027-08-31",
    )
    [note_line] = world.rows(
        select(source_invoice_line).where(source_invoice_line.c.source_invoice_id == note["id"])
    )
    assert (
        note_line["line_external_id"],
        note_line["amount"],
        str(note_line["service_period_start"]),
        str(note_line["service_period_end"]),
    ) == ("cnli_DEMO0001", Decimal("-100.00"), "2026-09-01", "2026-09-06")

    # the events: the booking, then the billing with its service-period hint, then the credit
    events = _events(world, booked["id"])
    assert [(e["stream_version"], e["event_type"], e["origin"]) for e in events] == [
        (1, "CONTRACT_BOOKED", "ADAPTER"),
        (2, "BILLING_RECORDED", "ADAPTER"),
        (3, "CREDIT_MEMO_RECORDED", "ADAPTER"),
    ]
    assert all(e["sync_run_id"] == row["id"] and e["is_manual"] is False for e in events)
    assert all(str(e["idempotency_key"]).startswith("src:") for e in events)  # ADP-03
    _, billing, credit = events
    assert _stated(billing["payload"]) == {
        "invoice_number": "QUAY-0001",
        "line_external_id": "il_DEMO0001",
        "amount": MONEY_1200,
        "issue_date": "2026-09-01",
        "due_date": "2026-10-01",
        "service_period_start": "2026-09-01",
        "service_period_end": "2027-08-31",
        "source_invoice_id": str(invoice["id"]),
    }
    assert str(billing["effective_date"]) == "2026-09-01"
    assert billing["source_record_id"] == by_type["INVOICE"]["id"]
    assert _stated(credit["payload"]) == {
        "credit_memo_number": "QUAY-CN-0001",
        "credited_invoice_number": "QUAY-0001",
        "amount": MONEY_100,
        "issue_date": "2026-09-06",
    }
    assert str(credit["effective_date"]) == "2026-09-06"
    assert credit["source_record_id"] == by_type["CREDIT_MEMO"]["id"]
    document_links = world.rows(
        select(contract_source_link).where(contract_source_link.c.link_role == "INVOICE")
    )
    assert sorted(
        (link["source_record_id"], link["contract_event_id"]) for link in document_links
    ) == sorted(
        [(by_type["INVOICE"]["id"], billing["id"]), (by_type["CREDIT_MEMO"]["id"], credit["id"])]
    )

    # the out-of-order invoice version is recorded and not applied (ADP-02; PRD IMP-44)
    [stale] = world.rows(select(exception_item))
    assert (stale["code"], stale["severity"], stale["business_key"]) == (
        "STALE_SOURCE_VERSION",
        "WARNING",
        "in_DEMO0001",
    )

    # a repeated Stripe event id creates nothing: the whole feed delivered again — every event id
    # a repeat — fetches the three objects, finds each version stored, and appends nothing
    world.execute(
        update(integration_connection)
        .where(integration_connection.c.id == UUID(target["id"]))
        .values(checkpoint={})
    )
    again, again_job = sync(world, target)
    assert again["status"] == "SUCCEEDED" and again["record_count"] == 0
    replay = again_job["result"]["counts"]
    assert replay["notifications"] == 5 and replay["fetched"] == 3
    assert replay["duplicates"] == 1 + 3  # the repeated id, and the three stored versions
    assert (replay["records"], replay["documents"], replay["billing_events"]) == (0, 0, 0)
    assert replay["contracts_booked"] == 0 and replay["credit_memo_events"] == 0
    assert [e["id"] for e in _events(world, booked["id"])] == [e["id"] for e in events]
    assert len(world.rows(select(source_invoice))) == 2
    assert len(world.rows(select(source_record))) == 3
    assert len(world.rows(select(contract))) == 1


def test_document_without_its_contract_is_remediable(world: IntegrationWorld) -> None:
    """05 §5.1 (referential validation → exception item; PRD IMP-20): an invoice whose
    subscription is linked to no contract raises ``CONTRACT_NOT_FOUND`` — remediable, naming the
    stored record — and stores no document; once the subscription is ingested, reprocessing the
    item applies the stored invoice and resolves it."""
    target = _stripe(world)
    mock = _mock(world)
    full = mock.scenario
    # the feed delivers the paid invoice first: the subscription's event has not arrived
    paid = next(event for event in full.events if event["ordinal"] == 2)
    mock.scenario = dataclasses.replace(full, events=(paid,))
    row, finished = sync(world, target)
    assert row["status"] == "SUCCEEDED" and row["record_count"] == 1
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    [item] = world.rows(select(exception_item))
    assert (item["code"], item["severity"], item["disposition"], item["status"]) == (
        "CONTRACT_NOT_FOUND",
        "BLOCKING",
        "remediable",
        "OPEN",
    )
    assert item["message"] == "Contract sub_DEMO0001 does not exist in this workspace."
    assert item["business_key"] == "QUAY-0001" and item["sync_run_id"] == row["id"]
    [record] = world.rows(select(source_record))
    assert item["source_record_id"] == record["id"]
    assert world.rows(select(source_invoice)) == [] and world.rows(select(contract)) == []

    # the subscription's event arrives with the next poll, which books the contract and leaves
    # the stored invoice alone: the item is what brings the invoice back
    late = {
        "ordinal": 3,
        "id": "evt_DEMO_LATE",
        "type": "customer.subscription.created",
        "object": "subscription",
        "object_id": "sub_DEMO0001",
        "version": "1",
    }
    mock.scenario = dataclasses.replace(full, events=(paid, late))
    later, later_job = sync(world, target)
    assert later["status"] == "SUCCEEDED" and later_job["result"]["counts"]["notifications"] == 1
    [booked] = world.rows(select(contract))
    assert [e["event_type"] for e in _events(world, booked["id"])] == ["CONTRACT_BOOKED"]

    reprocess = post(world.app, f"/api/v1/exceptions/{item['id']}/reprocess", world.nikhil, {})
    assert reprocess.status_code == 202, reprocess.text
    done = run(world, UUID(reprocess.json()["id"]))
    counts = done["result"]["counts"]
    assert counts["reprocessed"] == 1 and counts["billing_events"] == 1 and counts["fetched"] == 0
    [settled] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert settled["status"] == "RESOLVED" and settled["reprocessed_at"] is not None
    assert [e["event_type"] for e in _events(world, booked["id"])] == [
        "CONTRACT_BOOKED",
        "BILLING_RECORDED",
    ]
    [invoice] = world.rows(select(source_invoice))
    assert invoice["source_record_id"] == record["id"]


def test_refused_document_is_a_failure_record_and_stores_nothing(world: IntegrationWorld) -> None:
    """04 T-INT-02 ``problem`` (step ``bill``, rev 1.103) and 05 §3.9: a credit note above the
    billing it credits is refused by the bound the route applies (``REFUND_EXCEEDS_BILLED``); the
    run ends FAILED naming the object, the step and the rule, nothing of the credit note is stored
    or appended, and what the run ingested before it stays committed."""
    target = _stripe(world)
    # the source states a credit of 2,000.00 against an invoice of 1,200.00
    _mock(world).scenario.credit_notes["cn_DEMO0001"]["lines"]["data"][0]["amount"] = 200000
    row, finished = sync(world, target)

    assert row["status"] == "FAILED" and finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    problem = row["problem"]
    assert problem["type"].endswith("/sync-objects-not-applied") and problem["status"] == 422
    [failure] = problem["failures"]
    assert (failure["step"], failure["object_type"], failure["external_id"]) == (
        "bill",
        "CREDIT_MEMO",
        "cn_DEMO0001",
    )
    assert [error["rule_id"] for error in failure["errors"]] == ["REFUND_EXCEEDS_BILLED"]
    counts = finished["result"]["counts"]
    assert (counts["documents"], counts["billing_events"], counts["credit_memo_events"]) == (
        1,
        1,
        0,
    )
    assert counts["failures"] == 1 and counts["records"] == 3  # the raw record is kept (S01-R-01)
    [invoice] = world.rows(select(source_invoice))
    assert invoice["external_invoice_id"] == "in_DEMO0001"  # the credit note left no document
    [booked] = world.rows(select(contract))
    assert [e["event_type"] for e in _events(world, booked["id"])] == [
        "CONTRACT_BOOKED",
        "BILLING_RECORDED",
    ]
    links = world.rows(
        select(contract_source_link).where(contract_source_link.c.link_role == "INVOICE")
    )
    assert len(links) == 1


def test_stripe_webhook_is_a_notification_and_the_job_fetches_what_it_names(
    world: IntegrationWorld,
) -> None:
    """05 ADP-01, ADP-14, ADP-17: a Stripe webhook with a valid ``Stripe-Signature`` stores nothing
    but a ``WEBHOOK_BATCH`` run naming its events; the job fetches the subscription, the invoice
    and the credit note before applying them, the repeated event id creates nothing, and the
    connection's poll cursor does not move. The webhook secret is served by a secret-store double
    (05 KEY-09: the local provider serves no adapter credential).

    Rev 1.47 (security review P3-23, the lead's finding 4; ruling R-48 (f)): the signature's
    timestamp lies within 300 seconds of the application clock — a notification captured and sent
    again later is refused with the same 401, however valid its signature."""
    secret_ref = tenant_ref(world.tenant_id, WEBHOOK_SECRET_NAME)
    serve_adapter_secrets(world.app, {secret_ref: st_mock.SHARED_SECRET})
    target = _stripe(world, secret_ref=secret_ref)
    receiver = commands.receiver_id(world.tenant_id, UUID(target["id"]))
    now = int(world.clock.now().timestamp())
    with asgi_client(world.app) as client:
        feed = client.get(f"{MOCK_BASE}/v1/events?starting_after=0&limit=5").json()
        body = json.dumps(feed).encode()
        signed = client.post(f"{MOCK_BASE}/webhooks/sign?t={now}", content=body).json()
        # 05 ADP-01: "more than 300 seconds from the application clock, in either direction".
        replayed = client.post(f"{MOCK_BASE}/webhooks/sign?t={now - 301}", content=body).json()
        early = client.post(f"{MOCK_BASE}/webhooks/sign?t={now + 301}", content=body).json()
    assert signed["header"] == "Stripe-Signature"
    forged = call(
        world.app,
        "POST",
        f"/api/v1/webhooks/STRIPE/{receiver}",
        content=body,
        headers={signed["header"]: "t=1,v1=" + "00" * 32},
    )
    assert forged.status_code == 401 and world.rows(select(sync_run)) == []
    # A valid signature of another time: the same body signed 301 seconds before the clock (a
    # captured notification sent again) and 301 seconds after it.
    for stale in (replayed, early):
        refused = call(
            world.app,
            "POST",
            f"/api/v1/webhooks/STRIPE/{receiver}",
            content=body,
            headers={signed["header"]: stale["signature"]},
        )
        assert refused.status_code == 401, refused.text
        assert refused.json()["type"].endswith("/unauthenticated")
    assert world.rows(select(sync_run)) == []
    _mock(world).served.clear()

    accepted = call(
        world.app,
        "POST",
        f"/api/v1/webhooks/STRIPE/{receiver}",
        content=body,
        headers={signed["header"]: signed["signature"]},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["notifications"] == 5
    [queued] = world.rows(select(sync_run))
    assert (queued["kind"], queued["status"]) == ("WEBHOOK_BATCH", "QUEUED")
    assert world.rows(select(source_record)) == [] and _mock(world).served == []  # a notification

    finished = run(world, UUID(accepted.json()["job_id"]))
    [done] = world.rows(select(sync_run))
    assert done["status"] == "SUCCEEDED", done["problem"]
    assert done["record_count"] == 3 and done["checkpoint_after"] == done["checkpoint_before"]
    counts = finished["result"]["counts"]
    assert (counts["notifications"], counts["duplicates"], counts["fetched"]) == (5, 1, 3)
    assert (counts["contracts_booked"], counts["billing_events"], counts["credit_memo_events"]) == (
        1,
        1,
        1,
    )
    assert _mock(world).served == [  # the truth is fetched, once per object, never the feed
        "subscription:sub_DEMO0001",
        "invoice:in_DEMO0001:2",
        "credit_note:cn_DEMO0001",
    ]
    [booked] = world.rows(select(contract))
    assert [e["event_type"] for e in _events(world, booked["id"])] == [
        "CONTRACT_BOOKED",
        "BILLING_RECORDED",
        "CREDIT_MEMO_RECORDED",
    ]
