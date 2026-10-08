"""Reconciliation sweeps and control totals over a database (05 §5.1 canonical ingestion
"reconcile", ADP-16, ADP-17, §5.7 SCH-09; 04 T-INT-02, T-INT-03 ``SYNC_REQUEST``, E-72, table
15.4-B ``SOURCE_VERSION_GAP`` and ``CONTROL_TOTALS_MISMATCH``; 03 REQ-INT-007, REQ-DAT-010; PRD
BR-INT-03, IMP-126; BUILD_SPEC DIN-13 named cases ``test_sweep_raises_gap_exceptions`` and
``test_control_totals_on_sync_run``).

DB-bound: every test needs the test database. World: ``support.integrations`` — the J-23 tenant —
with connections over the in-process Salesforce and Stripe mocks (WLD-F-31). A "missed" object is
one the test adds to a mock's state without a notification in its feed: the source holds it, the
feed never delivers it, and only a sweep can find it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.crm import salesforce
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.adapters.mocks import stripe as st_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    contract,
    contract_event,
    exception_item,
    integration_connection,
    job,
    notification,
    outbox_message,
    period,
    period_state,
    role_assignment,
    source_record,
    sync_run,
    tenant_membership,
)
from erev_api.domain.close import gates
from erev_api.domain.integrations import ports, sweeps
from erev_api.domain.integrations import sync as sync_module
from erev_api.domain.integrations.outbox import sync_request_key
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support.db import TestDatabase
from support.integrations import (
    INTEGRATIONS,
    IntegrationWorld,
    connection,
    integration_world,
    relay_outbox,
    run,
    sync,
)
from support.reference import get, post

SF_BASE = f"{mocks.MOCKS_PREFIX}{sf_mock.PREFIX}"
ST_BASE = f"{mocks.MOCKS_PREFIX}{st_mock.PREFIX}"
SWEEP = "RECONCILIATION_SWEEP"
GAP = "SOURCE_VERSION_GAP"
SALESFORCE_BODY: dict[str, Any] = {
    "code": "sf-quayside",
    "name": "Salesforce (mock)",
    "adapter": "SALESFORCE",
    "direction": "INBOUND",
    "base_url": SF_BASE,
    "config": {"default_performing_entity": "QUAY-US"},
}
STRIPE_BODY: dict[str, Any] = {
    "code": "stripe-quayside",
    "name": "Stripe (mock)",
    "adapter": "STRIPE",
    "direction": "INBOUND",
    "base_url": ST_BASE,
    "config": {"default_legal_entity": "QUAY-US"},
}
# An order the source holds and its feed never announced: one line of QUAY-ADDON, 30,000.00.
MISSED_ORDER = sf_mock.MockOrder(
    order_id="SF-ORD-Q-004",
    header={
        "Id": "SF-ORD-Q-004",
        "OrderNumber": "Q-004",
        "SystemModstamp": "2026-09-10T08:00:00Z",
        "EffectiveDate": "2026-09-10",
        "Status": "Activated",
        "AccountId": "ACC-QUAY-1001",
        "CurrencyIsoCode": "USD",
        "Performing_Entity__c": "QUAY-US",
    },
    versions={
        "1": [
            {
                "Id": "SF-OI-Q-004-1",
                "ProductCode": "QUAY-ADDON",
                "Quantity": "1",
                "TotalPrice": "30000.00",
                "ServiceDate": "2026-09-10",
                "EndDate": "2027-09-09",
            }
        ]
    },
)
# A credit note of 50.00 on in_DEMO0001, created 10 Sep 2026, with no event in the feed.
MISSED_CREDIT_NOTE: dict[str, Any] = {
    "id": "cn_DEMO0002",
    "object": "credit_note",
    "version": "1",
    "customer": "cus_DEMO0001",
    "invoice": "in_DEMO0001",
    "number": "QUAY-CN-0002",
    "currency": "usd",
    "created": 1788998400,
    "metadata": {"legal_entity": "QUAY-US"},
    "lines": {
        "data": [
            {
                "id": "cnli_DEMO0002",
                "object": "credit_note_line_item",
                "amount": 5000,
                "quantity": 1,
                "period": {"start": 1788220800, "end": 1788998400},
                "price": {
                    "id": "price_DEMO_PLAT_Y",
                    "metadata": {"erev_product_code": "QUAY-PLAT"},
                },
            }
        ]
    },
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Iterator[IntegrationWorld]:
    with integration_world(app, keyring, clock, app_settings) as built:
        yield built


def _requests(world: IntegrationWorld) -> list[dict[str, Any]]:
    return world.rows(
        select(outbox_message)
        .where(outbox_message.c.topic == "SYNC_REQUEST")
        .order_by(outbox_message.c.created_at, outbox_message.c.dedupe_key)
    )


def _queued_sweeps(world: IntegrationWorld) -> list[dict[str, Any]]:
    return world.rows(
        select(sync_run)
        .where(sync_run.c.kind == SWEEP, sync_run.c.status == "QUEUED")
        .order_by(sync_run.c.created_at, sync_run.c.id)
    )


def _swept(
    world: IntegrationWorld, queued: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the ``SYNC_RUN`` job of a QUEUED sweep; the finished run row and the job row."""
    finished = run(world, UUID(str(queued["job_id"])))
    [row] = world.rows(select(sync_run).where(sync_run.c.id == queued["id"]))
    return row, finished


def _gaps(world: IntegrationWorld) -> dict[str, dict[str, Any]]:
    return {
        str(item["business_key"]): item
        for item in world.rows(select(exception_item).where(exception_item.c.code == GAP))
    }


def _sweep_all(world: IntegrationWorld) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """Relay the pending sync requests and run every QUEUED sweep; (run row, job row) by
    connection id."""
    relayed = relay_outbox(world)
    assert relayed and all(row["state"] == "SUCCEEDED" for row in relayed)
    return {
        str(queued["integration_connection_id"]): _swept(world, queued)
        for queued in _queued_sweeps(world)
    }


def _checkpoint(world: IntegrationWorld, target: dict[str, Any]) -> ports.Checkpoint:
    [row] = world.rows(
        select(integration_connection.c.checkpoint).where(
            integration_connection.c.id == UUID(target["id"])
        )
    )
    return ports.Checkpoint.from_json(row["checkpoint"])


def _close_blockers(world: IntegrationWorld) -> dict[str, int]:
    """API-S-Period ``blockers`` of QUAY-US for September 2026, the period of the world's clock
    (04 §16.8; ``gates.blocker_counts``, the statement the cockpit and the gates read)."""
    with tenant_session(world.context, read_only=True) as session:
        [state] = (
            session.execute(
                gates.scope_select().where(
                    period_state.c.entity_id == world.entity_id,
                    period.c.period_key == "FY2026-P09",
                )
            )
            .mappings()
            .all()
        )
        return gates.blocker_counts(session, gates.scope_of(state))


def test_sweep_raises_gap_exceptions(world: IntegrationWorld) -> None:
    """BUILD_SPEC DIN-13 / 05 SCH-09 / 03 REQ-INT-007: SCH-09 defers one ``SYNC_RUN`` of kind
    ``RECONCILIATION_SWEEP`` per ACTIVE inbound connection — once per six-hour bucket — and, on a
    connection whose first sweep has run to completion (the baseline load, which raises nothing),
    a source object version absent from ``source_record`` raises an exception item
    ``SOURCE_VERSION_GAP`` (INFO) naming the object and the version; the sweep processes the
    version in the same run, and the item — which names no entity, contract or period — counts in
    no period's open-exception blocker (04 table 15.4-B rev 1.115; ruling R-45 (a))."""
    crm = connection(world, **SALESFORCE_BODY)
    billing = connection(world, **STRIPE_BODY)
    disabled = post(world.app, INTEGRATIONS, world.nikhil, {**SALESFORCE_BODY, "code": "sf-off"})
    assert disabled.status_code == 201 and disabled.json()["status"] == "DISABLED"
    # the feeds deliver everything they announce: both connections have polled, nothing is missed
    for target in (crm, billing):
        polled, _ = sync(world, target)
        assert polled["status"] == "SUCCEEDED" and polled["record_count"] == 3
        assert _checkpoint(world, target).swept_at is None
    assert len(world.rows(select(source_record))) == 6

    # SCH-09: one request per ACTIVE inbound connection, once per bucket
    bucket = sweeps.bucket_of(world.clock.now())
    report = sweeps.run(world.runtime, only_tenants=[world.tenant_id])
    assert report == sweeps.SweepReport(tenants=1, connections=2, requested=2)
    expected_keys = sorted(
        sync_request_key(UUID(target["id"]), SWEEP, bucket) for target in (crm, billing)
    )
    assert sorted(message["dedupe_key"] for message in _requests(world)) == expected_keys
    again = sweeps.run(world.runtime, only_tenants=[world.tenant_id])
    assert again == sweeps.SweepReport(tenants=1, connections=2, repeated=2)
    assert len(_requests(world)) == 2  # the periodic fired twice for the bucket: asked once

    # the relay turns each request into a QUEUED run of kind RECONCILIATION_SWEEP and its job
    assert _queued_sweeps(world) == []
    relayed = relay_outbox(world)
    assert relayed and all(row["state"] == "SUCCEEDED" for row in relayed)
    queued = _queued_sweeps(world)
    assert sorted(str(row["integration_connection_id"]) for row in queued) == sorted(
        [crm["id"], billing["id"]]
    )
    jobs = world.rows(select(job).where(job.c.id.in_([row["job_id"] for row in queued])))
    assert [(row["kind"], row["state"]) for row in jobs] == [("SYNC_RUN", "QUEUED")] * 2

    # the first sweep of each connection compares the source with source_record and finds every
    # version ingested: nothing stored, nothing raised; it is the connection's baseline
    for row in queued:
        first, first_job = _swept(world, row)
        assert first["status"] == "SUCCEEDED", first["problem"]
        assert first_job["result"]["swept"] is True and first["record_count"] == 0
        assert first_job["result"]["counts"]["gaps"] == 0
    assert _gaps(world) == {}
    for target in (crm, billing):
        assert _checkpoint(world, target).swept_at == world.clock.now()

    # what holds the period before any gap exists: the two stale notifications of the WLD-F-31
    # feeds (WARNING) and the order with an unmapped product (BLOCKING) — tenant-level items, which
    # count for every entity and period (XR-12)
    counted = sorted(
        (item["code"], str(item["severity"]))
        for item in world.rows(select(exception_item).where(exception_item.c.status == "OPEN"))
    )
    assert counted == [
        ("PRODUCT_UNMAPPED", "BLOCKING"),
        ("STALE_SOURCE_VERSION", "WARNING"),
        ("STALE_SOURCE_VERSION", "WARNING"),
    ]
    blockers = _close_blockers(world)
    assert (blockers["exceptions_open"], blockers["unmapped_products"]) == (3, 1)

    # ... then each source holds one object its feed never announces
    crm_mock = world.app.state.mocks.adapters[sf_mock.CODE]
    crm_mock.scenario.orders[MISSED_ORDER.order_id] = MISSED_ORDER
    billing_mock = world.app.state.mocks.adapters[st_mock.CODE]
    billing_mock.scenario.credit_notes[MISSED_CREDIT_NOTE["id"]] = dict(MISSED_CREDIT_NOTE)
    world.clock.advance(timedelta(hours=sweeps.BUCKET_HOURS))
    second = sweeps.run(world.runtime, only_tenants=[world.tenant_id])
    assert second == sweeps.SweepReport(tenants=1, connections=2, requested=2)
    found = _sweep_all(world)

    # the Salesforce sweep: the version the feed never delivered is named, recorded and processed
    swept, swept_job = found[crm["id"]]
    assert swept["status"] == "SUCCEEDED", swept["problem"]
    crm_counts = swept_job["result"]["counts"]
    assert (crm_counts["gaps"], crm_counts["records"]) == (1, 1)
    assert crm_counts["contracts_booked"] == 1 and swept["exception_count"] == 1
    assert swept["source_totals"]["amount_by_currency"] == {"USD": "30000.00"}
    assert swept["loaded_totals"]["amount_by_currency"] == {"USD": "30000.00"}
    [missed] = world.rows(select(source_record).where(source_record.c.sync_run_id == swept["id"]))
    assert (missed["external_id"], missed["external_version"]) == ("SF-ORD-Q-004", "1")
    gap = _gaps(world)["SF-ORD-Q-004"]
    assert gap["message"] == (
        "SALESFORCE ORDER SF-ORD-Q-004 version 1 had not been received when the reconciliation"
        " sweep found it. The sweep recorded it and processed it as a delivered version."
    )
    assert (gap["source"], gap["severity"], gap["status"]) == ("SYNC", "INFO", "OPEN")
    assert gap["sync_run_id"] == swept["id"] and gap["source_record_id"] is None
    assert (gap["entity_id"], gap["contract_id"], gap["period_id"]) == (None, None, None)
    assert gap["source_payload"]["detail"] == {
        "source_system": "SALESFORCE",
        "object_type": "ORDER",
        "external_id": "SF-ORD-Q-004",
        "external_version": "1",
        "source_record_id": str(missed["id"]),
    }
    [recovered] = world.rows(select(contract).where(contract.c.external_id == "Q-004"))
    assert recovered["status"] == "DRAFT"  # the sweep processed what it found

    # the Stripe sweep: the missed credit note is named, recorded and applied
    billed, billed_job = found[billing["id"]]
    assert billed["status"] == "SUCCEEDED", billed["problem"]
    billing_counts = billed_job["result"]["counts"]
    assert (billing_counts["gaps"], billing_counts["records"]) == (1, 1)
    assert (billing_counts["documents"], billing_counts["credit_memo_events"]) == (1, 1)
    note = _gaps(world)["cn_DEMO0002"]
    assert note["message"] == (
        "STRIPE CREDIT_MEMO cn_DEMO0002 version 1 had not been received when the reconciliation"
        " sweep found it. The sweep recorded it and processed it as a delivered version."
    )
    assert note["sync_run_id"] == billed["id"]
    [subscription] = world.rows(select(contract).where(contract.c.external_id == "sub_DEMO0001"))
    credits = world.rows(
        select(contract_event)
        .where(
            contract_event.c.contract_id == subscription["id"],
            contract_event.c.event_type == "CREDIT_MEMO_RECORDED",
        )
        .order_by(contract_event.c.stream_version)
    )
    assert [event["payload"]["credit_memo_number"] for event in credits] == [
        "QUAY-CN-0001",
        "QUAY-CN-0002",
    ]
    assert credits[1]["payload"]["amount"] == {"amount": "50.00", "currency": "USD"}
    assert credits[1]["sync_run_id"] == billed["id"]
    assert sorted(_gaps(world)) == ["SF-ORD-Q-004", "cn_DEMO0002"]  # one item per missed version
    # Two OPEN gap items, and the close reads what it read before them: an INFO item holds no
    # period (as a WARNING naming no entity it counted for every entity and period, XR-12).
    assert {item["severity"] for item in _gaps(world).values()} == {"INFO"}
    after = _close_blockers(world)
    assert (after["exceptions_open"], after["unmapped_products"]) == (3, 1)
    assert after["groups_dirty"] == blockers["groups_dirty"] + 1  # the recovered order's contract

    # the next sweep finds nothing new: a gap is raised once, when the version is first stored
    world.clock.advance(timedelta(hours=sweeps.BUCKET_HOURS))
    third = sweeps.run(world.runtime, only_tenants=[world.tenant_id])
    assert third == sweeps.SweepReport(tenants=1, connections=2, requested=2)
    for done, done_job in _sweep_all(world).values():
        assert done["status"] == "SUCCEEDED" and done["record_count"] == 0
        assert done_job["result"]["counts"]["gaps"] == 0
    assert sorted(_gaps(world)) == ["SF-ORD-Q-004", "cn_DEMO0002"]
    assert all(item["occurrence_count"] == 1 for item in _gaps(world).values())


def test_first_completed_sweep_is_the_baseline_not_a_gap(world: IntegrationWorld) -> None:
    """04 table 15.4-B ``SOURCE_VERSION_GAP`` and T-INT-01 ``checkpoint.swept_at`` (rev 1.103): the
    first sweep a connection completes ingests what the source held before the feed was read —
    which no feed promised — and raises nothing, even after a poll; from then on a version a sweep
    stores is a gap."""
    crm = connection(world, **SALESFORCE_BODY)
    polled, _ = sync(world, crm)
    assert polled["record_count"] == 3 and _checkpoint(world, crm).replay_id == 5
    crm_mock = world.app.state.mocks.adapters[sf_mock.CODE]
    crm_mock.scenario.orders[MISSED_ORDER.order_id] = MISSED_ORDER  # held, never announced

    baseline, baseline_job = sync(world, crm, kind=SWEEP)
    assert baseline_job["result"]["swept"] is True
    assert baseline["status"] == "SUCCEEDED" and baseline["record_count"] == 1
    assert baseline_job["result"]["counts"]["gaps"] == 0 and _gaps(world) == {}
    assert _checkpoint(world, crm).swept_at == world.clock.now()
    [recovered] = world.rows(select(contract).where(contract.c.external_id == "Q-004"))
    assert recovered["status"] == "DRAFT"

    later = dataclasses.replace(
        MISSED_ORDER,
        order_id="SF-ORD-Q-005",
        header={
            **MISSED_ORDER.header,
            "Id": "SF-ORD-Q-005",
            "OrderNumber": "Q-005",
            "SystemModstamp": "2026-09-11T08:00:00Z",
        },
        versions={"1": [{**MISSED_ORDER.versions["1"][0], "Id": "SF-OI-Q-005-1"}]},
    )
    crm_mock.scenario.orders[later.order_id] = later
    swept, swept_job = sync(world, crm, kind=SWEEP)
    assert swept["status"] == "SUCCEEDED" and swept_job["result"]["counts"]["gaps"] == 1
    assert sorted(_gaps(world)) == ["SF-ORD-Q-005"]


class _OverstatedSource(salesforce.SalesforceAdapter):
    """A source whose control totals state one object more than it delivers: the fetched set plus
    an order of USD 1,000.00 that no notification names and no fetch returns."""

    def control_totals(self, objects: Sequence[ports.SourceObject]) -> ports.ControlTotals:
        items = [
            (obj.external_id, obj.external_version, order.transaction_currency, order.total)
            for obj in objects
            for order in self.normalise(obj, salesforce.MAPPING_VERSION).orders
        ]
        return ports.ControlTotals.of([*items, ("SF-ORD-Q-999", "1", "USD", Decimal("1000.00"))])


def test_control_totals_on_sync_run(world: IntegrationWorld) -> None:
    """BUILD_SPEC DIN-13 / 03 REQ-DAT-010 / PRD BR-INT-03: a sync run whose loaded totals differ
    from the source totals ends ``CONTROL_TOTAL_MISMATCH`` (E-72) and raises the blocking
    ``CONTROL_TOTALS_MISMATCH`` exception; both totals are on the run (CTL-002), and what was
    ingested stays committed."""
    ports.register_inbound_adapter("SALESFORCE", _OverstatedSource)
    crm = connection(world, **SALESFORCE_BODY)
    row, finished = sync(world, crm)

    assert row["status"] == "CONTROL_TOTAL_MISMATCH" and row["problem"] is None
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    assert finished["result"]["status"] == "CONTROL_TOTAL_MISMATCH"
    source, loaded = row["source_totals"], row["loaded_totals"]
    assert (source["count"], source["amount_by_currency"]) == (4, {"USD": "191000.00"})
    assert (loaded["count"], loaded["amount_by_currency"]) == (3, {"USD": "190000.00"})
    assert source["sha256"] != loaded["sha256"] and len(source["sha256"]) == 64
    assert row["record_count"] == 3

    [mismatch] = world.rows(
        select(exception_item).where(exception_item.c.code == "CONTROL_TOTALS_MISMATCH")
    )
    assert (mismatch["source"], mismatch["severity"], mismatch["status"]) == (
        "SYNC",
        "BLOCKING",
        "OPEN",
    )
    assert mismatch["sync_run_id"] == row["id"] and mismatch["business_key"] == str(row["id"])
    assert "191000.00" in mismatch["message"] and "190000.00" in mismatch["message"]
    assert str(row["id"]) in mismatch["message"]
    assert mismatch["owner_membership_id"] == world.nikhil.member.membership_id
    notes = world.rows(select(notification).where(notification.c.subject_id == mismatch["id"]))
    assert len(notes) == 1
    assert notes[0]["recipient_membership_id"] == world.nikhil.member.membership_id
    assert notes[0]["kind"] == "EXCEPTION_ASSIGNED"
    assert notes[0]["link_path"] == f"/data/exceptions/{mismatch['id']}"
    # the run's exception count: the out-of-order version, the unmapped product, the mismatch
    assert row["exception_count"] == 3

    # the API shows the ledger of the run: both totals and the status (PRD J-23-AC-3; CTL-002)
    shown = get(world.app, f"/api/v1/sync-runs/{row['id']}", world.nikhil)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body["status"] == "CONTROL_TOTAL_MISMATCH" and body["exception_count"] == 3
    assert body["source_totals"]["amount_by_currency"] == {"USD": "191000.00"}
    assert body["loaded_totals"]["amount_by_currency"] == {"USD": "190000.00"}
    assert len(world.rows(select(contract))) == 3  # the ingestion stands; the mismatch is flagged


@pytest.mark.parametrize("owner_state", ["suspended", "revoked", "scoped"])
def test_mismatch_does_not_notify_an_ineligible_owner(
    world: IntegrationWorld, monkeypatch: pytest.MonkeyPatch, owner_state: str
) -> None:
    """Authority is checked when the mismatch occurs, after a run was authorized."""
    ports.register_inbound_adapter("SALESFORCE", _OverstatedSource)
    crm = connection(world, **SALESFORCE_BODY)
    original = sync_module._totals_mismatch

    def lose_access(uow: Any, **kwargs: Any) -> None:
        if owner_state == "suspended":
            uow.session.execute(
                update(tenant_membership)
                .where(tenant_membership.c.id == world.nikhil.member.membership_id)
                .values(status="SUSPENDED")
            )
        else:
            uow.session.execute(
                update(role_assignment)
                .where(
                    role_assignment.c.membership_id == world.nikhil.member.membership_id,
                    role_assignment.c.is_all_entities.is_(True),
                )
                .values(revoked_at=uow.now)
            )
        if owner_state == "scoped":
            from support.rows import insert_role_assignment

            insert_role_assignment(
                uow.session,
                tenant_id=world.tenant_id,
                membership_id=world.nikhil.member.membership_id,
                role_code="integration_admin",
                entity_ids=[world.entity_id],
            )
        original(uow, **kwargs)

    monkeypatch.setattr(sync_module, "_totals_mismatch", lose_access)
    row, _ = sync(world, crm)
    assert row["status"] == "CONTROL_TOTAL_MISMATCH"
    [item] = world.rows(
        select(exception_item).where(exception_item.c.code == "CONTROL_TOTALS_MISMATCH")
    )
    assert item["owner_membership_id"] is None
    assert item["status"] == "OPEN" and item["severity"] == "BLOCKING"
    assert world.rows(select(notification).where(notification.c.subject_id == item["id"])) == []


def test_mismatch_retry_does_not_repeat_owner_notification(
    world: IntegrationWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    ports.register_inbound_adapter("SALESFORCE", _OverstatedSource)
    crm = connection(world, **SALESFORCE_BODY)
    original = sync_module._totals_mismatch
    send = sync_module.notify
    deliveries: list[dict[str, Any]] = []

    def track_delivery(uow: Any, **kwargs: Any) -> Any:
        deliveries.append(kwargs)
        return send(uow, **kwargs)

    monkeypatch.setattr(sync_module, "notify", track_delivery)

    def repeat(uow: Any, **kwargs: Any) -> None:
        original(uow, **kwargs)
        original(uow, **{**kwargs, "counts": sync_module.Counts()})

    monkeypatch.setattr(sync_module, "_totals_mismatch", repeat)
    sync(world, crm)
    [item] = world.rows(
        select(exception_item).where(exception_item.c.code == "CONTROL_TOTALS_MISMATCH")
    )
    assert item["owner_membership_id"] == world.nikhil.member.membership_id
    notes = world.rows(select(notification).where(notification.c.subject_id == item["id"]))
    assert len(notes) == 1
    assert len(deliveries) == 1  # Does not rely on the generic ten-minute notification merge.


def test_owner_scope_must_cover_expanded_connection(world: IntegrationWorld) -> None:
    from support.principals import colleague
    from support.reference import assign, fields, patch

    scoped = colleague(world.tenant_id, "scoped-integration-owner")
    assign(scoped, "integration_admin", entity_ids=[world.entity_id])
    crm = connection(
        world,
        **{
            **SALESFORCE_BODY,
            "entity_ids": [str(world.entity_id)],
            "owner_membership_id": str(scoped.membership_id),
        },
    )
    before = world.rows(select(integration_connection))[0]
    response = patch(
        world.app,
        f"{INTEGRATIONS}/{crm['id']}",
        world.nikhil,
        {"entity_ids": []},
        if_match=f'"r{before["row_version"]}"',
    )
    assert response.status_code == 422, response.text
    assert fields(response) == [("owner_membership_id", "INTEGRATION_OWNER_SCOPE")]
    after = world.rows(select(integration_connection))[0]
    assert after["entity_ids"] == before["entity_ids"]
    assert after["row_version"] == before["row_version"]
    changed = patch(
        world.app,
        f"{INTEGRATIONS}/{crm['id']}",
        world.nikhil,
        {"entity_ids": [], "owner_membership_id": str(world.nikhil.member.membership_id)},
        if_match=f'"r{before["row_version"]}"',
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["entity_ids"] == []


@pytest.mark.parametrize("owner_state", ["unassigned", "suspended", "revoked", "eligible"])
def test_mismatch_falls_back_to_eligible_connection_creator(
    world: IntegrationWorld, monkeypatch: pytest.MonkeyPatch, owner_state: str
) -> None:
    from support.principals import colleague
    from support.reference import assign

    other = colleague(world.tenant_id, "configured-owner")
    assign(other, "integration_admin")
    ports.register_inbound_adapter("SALESFORCE", _OverstatedSource)
    crm = connection(world, **{**SALESFORCE_BODY, "owner_membership_id": str(other.membership_id)})
    original = sync_module._totals_mismatch

    def change_owner(uow: Any, **kwargs: Any) -> None:
        if owner_state == "unassigned":
            uow.session.execute(update(integration_connection).values(owner_membership_id=None))
        elif owner_state == "suspended":
            uow.session.execute(
                update(tenant_membership)
                .where(tenant_membership.c.id == other.membership_id)
                .values(status="SUSPENDED")
            )
        elif owner_state == "revoked":
            uow.session.execute(
                update(role_assignment)
                .where(role_assignment.c.membership_id == other.membership_id)
                .values(revoked_at=uow.now)
            )
        original(uow, **kwargs)
        original(uow, **{**kwargs, "counts": sync_module.Counts()})

    monkeypatch.setattr(sync_module, "_totals_mismatch", change_owner)
    row, _ = sync(world, crm)
    assert row["status"] == "CONTROL_TOTAL_MISMATCH"
    [item] = world.rows(
        select(exception_item).where(exception_item.c.code == "CONTROL_TOTALS_MISMATCH")
    )
    recipient = (
        other.membership_id if owner_state == "eligible" else world.nikhil.member.membership_id
    )
    assert item["owner_membership_id"] == recipient
    notes = world.rows(select(notification).where(notification.c.subject_id == item["id"]))
    assert len(notes) == 1
    assert notes[0]["recipient_membership_id"] == recipient
    [stored] = world.rows(select(integration_connection))
    assert stored["owner_membership_id"] == (
        None if owner_state == "unassigned" else other.membership_id
    )
