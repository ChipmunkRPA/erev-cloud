"""Salesforce canonical ingestion over a database (05 §5.1 ADP-01 to ADP-05, ADP-12, ADP-16; 04
T-INT-01, T-INT-02, T-INT-04, T-SRC-01 to T-SRC-03; 03 REQ-INT-001, REQ-INT-004; PRD WLD-F-31,
J-23.4, BR-INT-02, BR-INT-03; ENGINE_SPEC S01-R-01 to S01-R-03, S02-R-13; BUILD_SPEC DIN-12 named
cases ``test_quayside_scenario_ingestion``, ``test_canonical_flow_order``,
``test_webhook_is_notification_only``, ``test_checkpoint_older_than_72_hours_triggers_sweep``,
``test_order_amendment_becomes_draft_modification``).

DB-bound: every test needs the test database. World (PRD J-23 preconditions): a tenant with entity
``QUAY-US`` (USD, America/Chicago) whose FY2026 periods are open, products ``QUAY-PLAT``,
``QUAY-ADDON`` and ``QUAY-SVC`` (WLD-F-36; ``SF-PROD-X99`` deliberately absent), no customers (the
sync creates them from the source account ids, pending team-lead's Q-C), and Nikhil, an Integration
Admin (MFA-enrolled). The connection reaches the in-process Salesforce mock (WLD-F-31) through
``support.http.asgi_client``, registered as the adapters' HTTP client factory; the ``SYNC_RUN`` job
runs in-process under the world's runtime the way ``support.factories.run_import_job`` runs import
jobs. The amendment case (ADP-05) exercises the non-ACTIVE-parent branch of D-98 146 A1 Q-B: the
candidate rows are recorded, ``MODIFICATION_CANDIDATE_UNAPPLIED`` is raised, no ``CONTRACT_AMENDED``
is appended; the ACTIVE-parent DRAFT modification (provisional kind) needs an activated parent,
which this world does not provision (follow-up).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.crm import salesforce
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_event,
    customer,
    exception_item,
    external_id_map,
    integration_connection,
    job,
    modification,
    obligation,
    product,
    source_order,
    source_order_line,
    source_record,
    sync_run,
)
from erev_api.domain.integrations import commands, grouping, ports
from erev_api.domain.integrations import sync as sync_module
from erev_api.domain.integrations.normalise import SourceIdentity, store_source_record
from erev_api.enums import SourceObjectType, SourceSystem
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, text, update
from support.adapter_secrets import serve_adapter_secrets, tenant_ref
from support.db import TestDatabase
from support.factories import stamp_test_release, world_calendar
from support.http import asgi_client, call
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, get, new_product, patch, post

INTEGRATIONS = "/api/v1/integrations"
MOCK_BASE = f"{mocks.MOCKS_PREFIX}{sf_mock.PREFIX}"
ADMIN = f"{mocks.MOCKS_PREFIX}/__admin"
# The workspace's Salesforce secret: its reference lies in the workspace's own namespace of the
# secret store (``tenant_ref``; 05 KEY-09 rev 1.47).
SECRET_NAME = "sf-client-secret"
PRODUCTS = ("QUAY-PLAT", "QUAY-ADDON", "QUAY-SVC")  # WLD-F-36; SF-PROD-X99 is unmapped
_TASK_FETCHED = "UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"


@dataclass(frozen=True, slots=True)
class World:
    app: FastAPI
    nikhil: Actor
    tenant_id: UUID
    runtime: JobRuntime
    clock: FrozenClock

    def rows(self, statement: Any) -> list[dict[str, Any]]:
        context = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    def execute(self, statement: Any) -> None:
        context = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            session.execute(statement)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> Iterator[World]:
    someone = member(keyring, clock)
    for role in ("revenue_accountant", "integration_admin"):
        assign(someone, role)
    nikhil = enrolled(app, clock, someone)
    world_calendar(
        app, nikhil, entity_code="QUAY-US", functional_currency="USD", time_zone="America/Chicago"
    )
    for code in PRODUCTS:
        new_product(app, nikhil, code=code, name=code.replace("-", " ").title())
    # ADP-14: the connection's ``secret_ref`` resolves through the app's key ring; locally
    # ``EnvSecretStore`` serves the master keys only (05 KEY-09), so the fixture secret is served
    # by a SecretStore (``support.adapter_secrets``), never read from the environment.
    serve_adapter_secrets(app, {tenant_ref(someone.tenant_id, SECRET_NAME): sf_mock.SHARED_SECRET})

    def backoff(seconds: float) -> None:
        # ADP-12: the adapter's backoff sleep is injectable so that tests never wait
        # (adapters/crm/salesforce.py); here a retried 429 moves the world's frozen clock by the
        # backoff instead of the wall clock, so the run it delays has a duration (DG-KRN-TIME-06).
        clock.advance(timedelta(seconds=seconds))

    ports.register_inbound_adapter(
        "SALESFORCE", lambda context: salesforce.SalesforceAdapter(context, sleep=backoff)
    )
    previous = sync_module._HOOKS.get("http")
    sync_module.register_http_client_factory(lambda base_url: asgi_client(app))
    with asgi_client(app) as client:
        assert client.post(f"{ADMIN}/reset").status_code == 204  # the seeded WLD-F-31 state
    stamp_test_release()
    try:
        yield World(
            app=app,
            nikhil=nikhil,
            tenant_id=someone.tenant_id,
            runtime=JobRuntime(
                clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root)
            ),
            clock=clock,
        )
    finally:
        sync_module.register_http_client_factory(previous)
        salesforce.register()  # the composition root's factory (real sleep) for later modules


def _connection(world: World, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "sf-quayside",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "base_url": MOCK_BASE,
        "config": {"default_performing_entity": "QUAY-US"},
        "secret_ref": tenant_ref(world.tenant_id, SECRET_NAME),
    }
    body.update(over)
    created = post(world.app, INTEGRATIONS, world.nikhil, body)
    assert created.status_code == 201, created.text
    activated = patch(
        world.app,
        f"{INTEGRATIONS}/{created.json()['id']}",
        world.nikhil,
        {"status": "ACTIVE"},
        if_match='"r1"',
    )
    assert activated.status_code == 200, activated.text
    result: dict[str, Any] = activated.json()
    return result


def _queue_fault(world: World, route: str, kind: str, count: int = 1) -> None:
    with asgi_client(world.app) as client:
        response = client.post(
            f"{ADMIN}/faults", json={"route": route, "kind": kind, "count": count}
        )
        assert response.status_code == 201, response.text


def _run(world: World, job_id: UUID) -> dict[str, Any]:
    """The worker fetches the job's task and runs it; the finished job row."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(text(_TASK_FETCHED), {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=1, runtime=world.runtime)
    [row] = world.rows(select(job).where(job.c.id == job_id))
    return row


def _sync(
    world: World, connection: dict[str, Any], kind: str = "INBOUND_POLL"
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``POST /integrations/{id}/sync`` then the job; the sync run row and the job row."""
    accepted = post(
        world.app, f"{INTEGRATIONS}/{connection['id']}/sync", world.nikhil, {"kind": kind}
    )
    assert accepted.status_code == 202, accepted.text
    finished = _run(world, UUID(accepted.json()["id"]))
    [run] = world.rows(
        select(sync_run).where(sync_run.c.id == UUID(accepted.headers["X-Erev-Sync-Run-Id"]))
    )
    return run, finished


def test_quayside_scenario_ingestion(world: World) -> None:
    """BUILD_SPEC DIN-12 / PRD J-23.4: a sync over WLD-F-31 ingests 3 orders — the duplicate
    webhook is recorded once, the out-of-order version raises ``STALE_SOURCE_VERSION``, the 429 is
    retried, product ``SF-PROD-X99`` raises ``PRODUCT_UNMAPPED`` (remediable); the control totals
    match and the run SUCCEEDED."""
    connection = _connection(world)
    _queue_fault(world, f"{sf_mock.PREFIX}/sobjects/Order", "RATE_LIMIT")  # the scenario's one 429
    run, finished = _sync(world, connection)

    assert run["status"] == "SUCCEEDED", run["problem"]
    assert run["record_count"] == 3  # unique source records
    assert run["exception_count"] == 2  # one stale version, one unmapped product
    assert run["source_totals"]["count"] == 3
    assert run["source_totals"]["amount_by_currency"] == {"USD": "190000.00"}
    assert run["loaded_totals"]["count"] == 3
    assert run["loaded_totals"]["amount_by_currency"] == {"USD": "190000.00"}
    assert run["checkpoint_after"]["replay_id"] == 5 and run["started_at"] < run["finished_at"]
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    counts = finished["result"]["counts"]
    assert counts["notifications"] == 5 and counts["duplicates"] == 1  # NTF-Q-0001 twice
    assert counts["fetched"] == 3 and counts["stale"] == 1 and counts["unmapped_products"] == 1
    assert counts["contracts_booked"] == 3 and counts["customers_created"] == 3

    [after] = world.rows(
        select(integration_connection).where(integration_connection.c.id == UUID(connection["id"]))
    )
    assert after["checkpoint"]["replay_id"] == 5  # persisted replay-id checkpoint (ADP-16)

    records = world.rows(
        select(source_record).order_by(
            source_record.c.external_id, source_record.c.external_version
        )
    )
    assert [(r["external_id"], r["external_version"]) for r in records] == [
        ("SF-ORD-Q-001", "1"),
        ("SF-ORD-Q-002", "2"),
        ("SF-ORD-Q-003", "1"),
    ]
    assert all(r["sync_run_id"] == run["id"] and len(r["payload_sha256"]) == 64 for r in records)

    items = world.rows(select(exception_item).order_by(exception_item.c.code))
    by_code = {item["code"]: item for item in items}
    assert set(by_code) == {"PRODUCT_UNMAPPED", "STALE_SOURCE_VERSION"}
    unmapped = by_code["PRODUCT_UNMAPPED"]
    assert unmapped["disposition"] == "remediable" and unmapped["source"] == "SYNC"
    assert unmapped["message"] == (  # PRD IMP-41, as J-23.4 quotes it
        "Order SF-ORD-Q-003, line 2: product SF-PROD-X99 has no approved product record."
    )
    assert unmapped["business_key"] == "SF-ORD-Q-003"
    assert unmapped["sync_run_id"] == run["id"] and unmapped["status"] == "OPEN"
    stale = by_code["STALE_SOURCE_VERSION"]
    assert stale["severity"] == "WARNING" and stale["business_key"] == "SF-ORD-Q-002"

    # 04 §16.14 rev 1.81 (partial booking): SF-ORD-Q-003 is a DRAFT from its mapped line QUAY-PLAT;
    # its PRODUCT_UNMAPPED item names that contract, so activation stays blocked (J-23.4).
    contracts = world.rows(select(contract).order_by(contract.c.external_id))
    assert [(c["external_id"], c["status"], c["source_system"]) for c in contracts] == [
        ("Q-001", "DRAFT", "SALESFORCE"),
        ("Q-002", "DRAFT", "SALESFORCE"),
        ("Q-003", "DRAFT", "SALESFORCE"),
    ]
    # 05 ADP-16 rev 1.204 (item ACT-FLAGS-1): the two terms each order states reach its contract
    # — the scenario's orders state both false.
    assert [(c["acceptance_clause"], c["side_letter"]) for c in contracts] == [(False, False)] * 3
    [q003] = [c for c in contracts if c["external_id"] == "Q-003"]
    assert unmapped["contract_id"] == q003["id"]
    assert unmapped["source_payload"]["detail"] == {
        "product_code": "SF-PROD-X99",
        "line_external_ids": ["SF-OI-Q-003-2"],
    }
    customers = world.rows(select(customer).order_by(customer.c.code))
    assert [(c["code"], c["external_id"], c["source_system"]) for c in customers] == [
        ("ACC-QUAY-1001", "ACC-QUAY-1001", "SALESFORCE"),
        ("ACC-QUAY-1002", "ACC-QUAY-1002", "SALESFORCE"),
        ("ACC-QUAY-1003", "ACC-QUAY-1003", "SALESFORCE"),
    ]
    links = world.rows(select(external_id_map).where(external_id_map.c.valid_to.is_(None)))
    assert sorted((link["object_type"], link["external_id"]) for link in links) == [
        ("contract", "SF-ORD-Q-001"),
        ("contract", "SF-ORD-Q-002"),
        ("contract", "SF-ORD-Q-003"),
        ("customer", "ACC-QUAY-1001"),
        ("customer", "ACC-QUAY-1002"),
        ("customer", "ACC-QUAY-1003"),
    ]
    with asgi_client(world.app) as client:
        state = client.get(f"{ADMIN}/state").json()
    assert state["faults"] == []  # the queued 429 was consumed by the retried fetch

    listed = get(world.app, f"/api/v1/sync-runs/{run['id']}", world.nikhil)
    assert listed.status_code == 200 and listed.json()["duration_seconds"] is not None
    shown = get(world.app, f"{INTEGRATIONS}/{connection['id']}", world.nikhil)
    assert shown.json()["last_sync_run"]["result"] == {"record_count": 3, "exception_count": 2}

    again, again_job = _sync(world, connection)  # idempotent: nothing new after replay id 5
    assert again["status"] == "SUCCEEDED" and again["record_count"] == 0
    assert again_job["result"]["counts"]["notifications"] == 0


def test_canonical_flow_order(world: World) -> None:
    """05 §5.1; S01-R-03: receive → ``source_record`` with ``payload_sha256`` → dedupe →
    normalisation into ``source_order`` and lines → validation → matching by grouping →
    ``CONTRACT_BOOKED`` with key ``src:<hex>``, origin ADAPTER, ``source_record_id`` and
    ``sync_run_id``."""
    connection = _connection(world)
    run, _ = _sync(world, connection)
    [record] = world.rows(
        select(source_record).where(source_record.c.external_id == "SF-ORD-Q-001")
    )
    assert record["source_system"] == "SALESFORCE" and record["object_type"] == "ORDER"
    assert record["version_order"] == 1 and len(record["payload_sha256"]) == 64
    assert record["payload"]["Id"] == "SF-ORD-Q-001"
    [order] = world.rows(
        select(source_order).where(source_order.c.source_record_id == record["id"])
    )
    assert order["order_number"] == "Q-001" and order["customer_external_id"] == "ACC-QUAY-1001"
    assert order["customer_id"] is not None and order["legal_entity_code"] == "QUAY-US"
    assert order["grouping_values"]  # the T-PLT-31 fields of the tenant
    lines = world.rows(
        select(source_order_line)
        .where(source_order_line.c.source_order_id == order["id"])
        .order_by(source_order_line.c.line_no)
    )
    assert [(line["product_code"], str(line["total_price"])) for line in lines] == [
        ("QUAY-PLAT", "100000.0000"),
        ("QUAY-SVC", "20000.0000"),
    ]
    assert all(line["product_id"] is not None for line in lines)
    [booked] = world.rows(select(contract).where(contract.c.external_id == "Q-001"))
    [event] = world.rows(select(contract_event).where(contract_event.c.contract_id == booked["id"]))
    assert event["event_type"] == "CONTRACT_BOOKED" and event["origin"] == "ADAPTER"
    assert event["idempotency_key"].startswith("src:") and len(event["idempotency_key"]) == 4 + 64
    assert event["source_record_id"] == record["id"] and event["sync_run_id"] == run["id"]
    # 04 T-PLT-19 rev 1.154: the append's audit event names the contract and the sync run, so the
    # contract's trail names the run that booked it (the run's own events name no contract).
    [append] = world.rows(
        select(audit_event.c.detail).where(
            audit_event.c.action == "contract_event.append",
            audit_event.c.detail["contract_id"].astext == str(booked["id"]),
        )
    )
    assert append["detail"]["sync_run_id"] == str(run["id"])
    assert append["detail"]["ids"] == [str(event["id"])]
    assert sum(Decimal(str(line["total_price"])) for line in lines) == Decimal("120000.00")
    assert run["record_count"] == 3


def test_sync_run_etag_follows_every_move_of_the_run(world: World) -> None:
    """04 API-C-08 / SC-M: ``GET /sync-runs/{id}`` answers ``ETag "r<row_version>"``, and an IM-S
    row has no touch trigger, so every move of a run raises ``row_version`` itself: QUEUED is r1,
    RUNNING r2 and the finished run r3 — whether it finished itself or its job's failure hook
    ended it. One ETag for every status would let a client keep a stale representation."""
    connection = _connection(world)
    accepted = post(world.app, f"{INTEGRATIONS}/{connection['id']}/sync", world.nikhil, {})
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.headers["X-Erev-Sync-Run-Id"]
    queued = get(world.app, f"/api/v1/sync-runs/{run_id}", world.nikhil)
    assert (queued.json()["status"], queued.headers["ETag"]) == ("QUEUED", '"r1"')
    _run(world, UUID(accepted.json()["id"]))
    done = get(world.app, f"/api/v1/sync-runs/{run_id}", world.nikhil)
    assert (done.json()["status"], done.headers["ETag"]) == ("SUCCEEDED", '"r3"')
    assert done.json()["row_version"] == 3

    # The job's failure hook moves the run too: with no HTTP client the job fails after the start.
    refused = post(world.app, f"{INTEGRATIONS}/{connection['id']}/sync", world.nikhil, {})
    assert refused.status_code == 202, refused.text
    failed_id = refused.headers["X-Erev-Sync-Run-Id"]
    serving = sync_module._HOOKS.get("http")
    sync_module.register_http_client_factory(None)
    try:
        finished = _run(world, UUID(refused.json()["id"]))
    finally:
        sync_module.register_http_client_factory(serving)
    assert finished["state"] == "FAILED"
    failed = get(world.app, f"/api/v1/sync-runs/{failed_id}", world.nikhil)
    assert (failed.json()["status"], failed.headers["ETag"]) == ("FAILED", '"r3"')


def test_webhook_is_notification_only(world: World) -> None:
    """BUILD_SPEC DIN-12 / 05 ADP-01: ``POST /webhooks/SALESFORCE/{id}`` with a valid signature
    answers 2xx, stores only a ``sync_run`` of kind ``WEBHOOK_BATCH`` and defers ``SYNC_RUN``, which
    fetches each object from the source before acting."""
    connection = _connection(world)
    receiver = commands.receiver_id(world.tenant_id, UUID(connection["id"]))
    event = '{"notificationId": "NTF-Q-0001", "orderId": "SF-ORD-Q-001", "version": "1"'
    body = f'{{"events": [{event}, "replayId": 1}}, {event}, "replayId": 5}}]}}'.encode()
    with asgi_client(world.app) as client:
        signed = client.post(f"{MOCK_BASE}/webhooks/sign", content=body).json()
    accepted = call(
        world.app,
        "POST",
        f"/api/v1/webhooks/SALESFORCE/{receiver}",
        content=body,
        headers={signed["header"]: signed["signature"]},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["notifications"] == 2
    run_id = UUID(accepted.json()["sync_run_id"])
    [run] = world.rows(select(sync_run).where(sync_run.c.id == run_id))
    assert run["kind"] == "WEBHOOK_BATCH" and run["status"] == "QUEUED"
    assert world.rows(select(source_record)) == []  # nothing but the run and the job
    assert world.rows(select(contract)) == []
    with asgi_client(world.app) as client:
        before = client.get(f"{ADMIN}/state").json()
    finished = _run(world, UUID(accepted.json()["job_id"]))
    assert finished["state"] == "SUCCEEDED"
    [done] = world.rows(select(sync_run).where(sync_run.c.id == run_id))
    assert done["status"] == "SUCCEEDED" and done["record_count"] == 1
    assert done["checkpoint_after"] == done["checkpoint_before"]  # a batch moves no checkpoint
    assert finished["result"]["counts"] == {
        **finished["result"]["counts"],
        "notifications": 2,
        "duplicates": 1,
        "fetched": 1,
        "records": 1,
        "contracts_booked": 1,
    }
    records = world.rows(select(source_record))
    assert [(r["external_id"], r["external_version"]) for r in records] == [("SF-ORD-Q-001", "1")]
    with asgi_client(world.app) as client:
        after = client.get(f"{ADMIN}/state").json()
    assert (
        after["adapters"]["salesforce"]["served"] == before["adapters"]["salesforce"]["served"] + 1
    )


def _aged(world: World, connection: dict[str, Any], *, hours: int) -> None:
    """The connection's replay-id checkpoint as its last poll left it ``hours`` ago."""
    aged = ports.Checkpoint(
        replay_id=5,
        replay_at=world.clock.now() - timedelta(hours=hours),
        last_modified_watermark=None,
    )
    world.execute(
        update(integration_connection)
        .where(integration_connection.c.id == UUID(connection["id"]))
        .values(checkpoint=aged.as_json())
    )


def test_checkpoint_older_than_72_hours_triggers_sweep(world: World) -> None:
    """05 ADP-16 / REQ-INT-004: a replay-id checkpoint older than 72 hours makes the next poll run a
    ``RECONCILIATION_SWEEP`` by last-modified time; the watermark advances. The 72 hours are
    measured on the application clock — the job's (DG-KRN-TIME-06) — so a checkpoint 71 hours old
    polls and one 73 hours old sweeps, whatever the wall clock reads."""
    young = _connection(world, code="sf-71h")
    _aged(world, young, hours=71)
    polled, polled_job = _sync(world, young)
    assert polled_job["result"]["swept"] is False  # inside the 72 hours: a poll after replay id 5
    assert polled["status"] == "SUCCEEDED" and polled["record_count"] == 0
    after_poll = ports.Checkpoint.from_json(polled["checkpoint_after"])
    assert after_poll.replay_id == 5 and after_poll.last_modified_watermark is None
    assert after_poll.replay_at == world.clock.now()  # stamped on the application clock

    connection = _connection(world)
    _aged(world, connection, hours=73)
    run, finished = _sync(world, connection)  # INBOUND_POLL, yet the adapter sweeps
    assert finished["result"]["swept"] is True
    assert run["status"] == "SUCCEEDED" and run["record_count"] == 3  # every order swept once
    after = ports.Checkpoint.from_json(run["checkpoint_after"])
    assert after.last_modified_watermark is not None and after.sweep_cursor is None
    assert after.replay_id == 5
    assert after.replay_at == world.clock.now()  # the completed sweep re-baselines the cadence
    [row] = world.rows(
        select(integration_connection).where(integration_connection.c.id == UUID(connection["id"]))
    )
    assert row["checkpoint"] == run["checkpoint_after"]

    fresh = _connection(world, code="sf-fresh")
    explicit, explicit_job = _sync(world, fresh, kind="RECONCILIATION_SWEEP")
    assert explicit_job["result"]["swept"] is True and explicit["kind"] == "RECONCILIATION_SWEEP"


def test_unmapped_order_is_booked_from_its_mapped_lines(world: World) -> None:
    """04 §16.14 rev 1.81 (BUILD_SPEC fragment 13 rev 1.2): SF-ORD-Q-003 becomes a DRAFT from its
    mapped line QUAY-PLAT only; the unmapped line stays a candidate row (``product_id`` null); the
    ``PRODUCT_UNMAPPED`` item names the contract; the activation checklist fails
    ``PRODUCT_TEMPLATE_SSP``."""
    connection = _connection(world)
    _sync(world, connection)
    [q003] = world.rows(select(contract).where(contract.c.external_id == "Q-003"))
    keys = world.rows(
        select(obligation.c.obligation_key).where(obligation.c.contract_id == q003["id"])
    )
    assert [row["obligation_key"] for row in keys] == ["SF-OI-Q-003-1"]  # the mapped line only
    [order] = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-003")
    )
    lines = world.rows(
        select(source_order_line)
        .where(source_order_line.c.source_order_id == order["id"])
        .order_by(source_order_line.c.line_no)
    )
    assert [(line["product_code"], line["product_id"] is None) for line in lines] == [
        ("QUAY-PLAT", False),
        ("SF-PROD-X99", True),  # the candidate row of the unmapped line
    ]
    [item] = world.rows(select(exception_item).where(exception_item.c.code == "PRODUCT_UNMAPPED"))
    assert item["contract_id"] == q003["id"] and item["status"] == "OPEN"
    checklist = get(world.app, f"/api/v1/contracts/{q003['id']}/activation-checklist", world.nikhil)
    assert checklist.status_code == 200, checklist.text
    [ssp] = [i for i in checklist.json()["items"] if i["code"] == "PRODUCT_TEMPLATE_SSP"]
    assert ssp["passed"] is False and "SF-PROD-X99" in (ssp["detail"] or "")


def test_reprocess_maps_the_unmapped_line_and_resolves_the_item(world: World) -> None:
    """04 §16.14 rev 1.81 (BUILD_SPEC fragment 13 rev 1.2; PRD J-23.5): after the J-23.4 run,
    ``POST /external-ids`` links ``SF-PROD-X99`` to ``QUAY-ADDON`` under the connection; then
    ``POST /exceptions/{id}/reprocess`` (202) queues an ``INBOUND_POLL`` run over the STORED record
    and its job re-books the DRAFT through the DRAFT-replacement path with the line mapped to
    ``QUAY-ADDON`` (the earlier booking voided; no duplicate ``CONTRACT_BOOKED``), resolves the
    SAME item ("Input processed") and unblocks ``PRODUCT_TEMPLATE_SSP`` for that line."""
    connection = _connection(world)
    _sync(world, connection)
    [item] = world.rows(select(exception_item).where(exception_item.c.code == "PRODUCT_UNMAPPED"))
    [q003] = world.rows(select(contract).where(contract.c.external_id == "Q-003"))
    assert item["contract_id"] == q003["id"] and item["status"] == "OPEN"
    [addon] = world.rows(select(product.c.id).where(product.c.code == "QUAY-ADDON"))
    linked = post(
        world.app,
        "/api/v1/external-ids",
        world.nikhil,
        {
            "integration_connection_id": connection["id"],
            "object_type": "product",
            "internal_id": str(addon["id"]),
            "external_id": "SF-PROD-X99",
        },
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["object_type"] == "product" and linked.json()["valid_to"] is None
    shown = get(world.app, f"/api/v1/exceptions/{item['id']}", world.nikhil)
    assert shown.status_code == 200, shown.text
    assert "REPROCESS" in shown.json()["available_actions"]
    reprocess = post(world.app, f"/api/v1/exceptions/{item['id']}/reprocess", world.nikhil, {})
    assert reprocess.status_code == 202, reprocess.text
    job_id = UUID(reprocess.json()["id"])
    [run] = world.rows(select(sync_run).where(sync_run.c.job_id == job_id))
    assert run["kind"] == "INBOUND_POLL" and run["status"] == "QUEUED"
    [queued] = world.rows(select(job.c.params).where(job.c.id == job_id))
    assert queued["params"][sync_module.REPROCESS_PARAM] == [str(item["source_record_id"])]
    assert queued["params"][sync_module.REPROCESS_ITEM_PARAM] == str(item["id"])
    finished = _run(world, job_id)
    assert finished["state"] == "SUCCEEDED", finished["result"]
    counts = finished["result"]["counts"]
    assert counts["reprocessed"] == 1 and counts["rebooked"] == 1 and counts["fetched"] == 0
    events = world.rows(
        select(contract_event.c.event_type, contract_event.c.supersedes_event_id)
        .where(contract_event.c.contract_id == q003["id"])
        .order_by(contract_event.c.stream_version)
    )
    assert [e["event_type"] for e in events] == [
        "CONTRACT_BOOKED",
        "EVENT_VOIDED",
        "CONTRACT_BOOKED",
    ]
    assert events[1]["supersedes_event_id"] is not None  # the earlier booking voided; no duplicate
    keys = world.rows(
        select(obligation.c.obligation_key, product.c.code)
        .join(product, product.c.id == obligation.c.product_id)
        .where(obligation.c.contract_id == q003["id"])
        .order_by(obligation.c.obligation_key)
    )
    assert [(k["obligation_key"], k["code"]) for k in keys] == [
        ("SF-OI-Q-003-1", "QUAY-PLAT"),
        ("SF-OI-Q-003-2", "QUAY-ADDON"),  # the line now maps to QUAY-ADDON (J-23.5)
    ]
    [settled] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert settled["status"] == "RESOLVED" and settled["resolution"] == "Input processed"
    assert settled["reprocessed_at"] is not None
    [after] = world.rows(select(sync_run).where(sync_run.c.id == run["id"]))
    assert after["status"] == "SUCCEEDED" and after["record_count"] == 1
    assert (
        after["checkpoint_after"] == after["checkpoint_before"]
    )  # a reprocess moves no checkpoint
    # 04 §16.14 reuse rule (Codex 0606 witness (1)): the retained identity is unchanged — the same
    # record and digest — and its source_order rows are reused, never stored again: one row per
    # (order, version), the candidate line IM-A (SOURCE code, product_id null); only the booking
    # product changed.
    orders = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-003")
    )
    assert len(orders) == 1 and orders[0]["source_record_id"] == item["source_record_id"]
    stored_lines = world.rows(
        select(source_order_line)
        .where(source_order_line.c.source_order_id == orders[0]["id"])
        .order_by(source_order_line.c.line_no)
    )
    assert [(line["product_code"], line["product_id"] is None) for line in stored_lines] == [
        ("QUAY-PLAT", False),
        ("SF-PROD-X99", True),
    ]
    checklist = get(world.app, f"/api/v1/contracts/{q003['id']}/activation-checklist", world.nikhil)
    assert checklist.status_code == 200, checklist.text
    [ssp] = [i for i in checklist.json()["items"] if i["code"] == "PRODUCT_TEMPLATE_SSP"]
    assert "SF-PROD-X99" not in (ssp["detail"] or "")


def _apply_one(
    world: World,
    connection: dict[str, Any],
    run_id: UUID,
    obj: ports.SourceObject,
    *,
    stored_id: UUID | None = None,
) -> Any:
    """``apply_object`` under the sync principal in one committed unit of work; ``stored_id``
    applies an already-stored record again (the reprocess path, 04 §16.14 rev 1.81)."""
    principal = sync_module.sync_principal(world.tenant_id)
    with system_unit_of_work(
        world.runtime, principal, request_id=f"tests-{obj.external_id}"
    ) as uow:
        [row] = world.rows(
            select(integration_connection).where(
                integration_connection.c.id == UUID(connection["id"])
            )
        )
        adapter = sync_module.adapter_for(
            row, tenant_code="quayside", client=asgi_client(world.app)
        )
        counts = sync_module.Counts()
        assert sync_module.apply_object(
            uow,
            adapter,
            row,
            obj,
            notified_versions=("1",),
            sync_run_id=run_id,
            counts=counts,
            loaded=[],
            stored_id=stored_id,
        )  # True = counted in the control totals, whatever the ingestion outcome
        uow.commit()
    return counts


def _order_object(
    external_id: str, *, product: str, quantity: str, total: str
) -> ports.SourceObject:
    return ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id=external_id,
        external_version="1",
        version_order=1,
        payload={
            "Id": external_id,
            "OrderNumber": external_id.removeprefix("SF-ORD-"),
            "Status": "Activated",
            "EffectiveDate": "2026-09-18",
            "AccountId": "ACC-QUAY-1001",
            "CurrencyIsoCode": "USD",
            "OrderItems": {
                "records": [
                    {
                        "Id": f"{external_id.replace('SF-ORD-', 'SF-OI-')}-1",
                        "ProductCode": product,
                        "Quantity": quantity,
                        "TotalPrice": total,
                    }
                ]
            },
        },
    )


def _alias(world: World, connection: dict[str, Any], external: str, code: str) -> None:
    [target] = world.rows(select(product.c.id).where(product.c.code == code))
    linked = post(
        world.app,
        "/api/v1/external-ids",
        world.nikhil,
        {
            "integration_connection_id": connection["id"],
            "object_type": "product",
            "internal_id": str(target["id"]),
            "external_id": external,
        },
    )
    assert linked.status_code == 201, linked.text


def _reprocessed(world: World, item: dict[str, Any]) -> dict[str, Any]:
    reprocess = post(world.app, f"/api/v1/exceptions/{item['id']}/reprocess", world.nikhil, {})
    assert reprocess.status_code == 202, reprocess.text
    return _run(world, UUID(reprocess.json()["id"]))


def test_all_unmapped_order_is_booked_on_reprocess_from_its_reused_rows(world: World) -> None:
    """04 §16.14 rev 1.81 (Codex 0606 witness (2)): an order whose only line is unmapped books no
    contract and its ``PRODUCT_UNMAPPED`` item names none; after ``POST /external-ids`` and
    ``POST /exceptions/{id}/reprocess`` the job books the contract through ``ingest_order`` on the
    REUSED ``source_order`` rows (one row per (order, version) — the same row, the same record; the
    candidate line's ``product_id`` still null, IM-A), one ``CONTRACT_BOOKED``; the item
    RESOLVED."""
    connection = _connection(world)
    run, _ = _sync(world, connection)  # the Quayside scenario; a run row for the applied object
    counts = _apply_one(
        world,
        connection,
        UUID(str(run["id"])),
        _order_object("SF-ORD-Q-010", product="SF-PROD-X99", quantity="1", total="5000.00"),
    )
    assert counts.candidates == 1 and counts.contracts_booked == 0 and counts.failures == []
    assert counts.unmapped_products == 1
    assert world.rows(select(contract).where(contract.c.external_id == "Q-010")) == []
    [stored] = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-010")
    )
    [item] = world.rows(
        select(exception_item).where(exception_item.c.business_key == "SF-ORD-Q-010")
    )
    assert item["code"] == "PRODUCT_UNMAPPED" and item["contract_id"] is None
    _alias(world, connection, "SF-PROD-X99", "QUAY-ADDON")
    finished = _reprocessed(world, item)
    assert finished["state"] == "SUCCEEDED", finished["result"]
    assert finished["result"]["counts"]["contracts_booked"] == 1
    [booked] = world.rows(select(contract).where(contract.c.external_id == "Q-010"))
    events = world.rows(
        select(contract_event.c.event_type).where(contract_event.c.contract_id == booked["id"])
    )
    assert [event["event_type"] for event in events] == ["CONTRACT_BOOKED"]  # once
    orders = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-010")
    )
    assert [order["id"] for order in orders] == [stored["id"]]  # the reused identity: the same row
    assert orders[0]["source_record_id"] == stored["source_record_id"]
    [line] = world.rows(
        select(source_order_line).where(source_order_line.c.source_order_id == stored["id"])
    )
    assert line["product_code"] == "SF-PROD-X99" and line["product_id"] is None  # IM-A
    [settled] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert settled["status"] == "RESOLVED" and settled["resolution"] == "Input processed"
    [link] = world.rows(
        select(external_id_map).where(
            external_id_map.c.external_id == "SF-ORD-Q-010", external_id_map.c.valid_to.is_(None)
        )
    )
    assert link["internal_id"] == booked["id"]


def test_source_content_conflict_is_refused_by_name_with_no_partial_writes(world: World) -> None:
    """04 §16.14 rev 1.81 (Codex 0606 witness (5), the source-authored conflict). DELIBERATELY
    INCONSISTENT, SCHEMA-ADMITTED SEAM WITNESS, NOT A NORMAL-WRITER TRAJECTORY (Codex 0652 §1): a
    same-identity ``source_order`` row of ANOTHER record is planted directly — the public store
    never yields two records of one identity (``normalise.store_source_record``,
    ``ux_source_record__identity``); the planted row is a NEW ``ux_source_order`` identity (no
    unique constraint violated, 0049_din_2_source_store.py:194–199), references an existing
    ``source_record`` (the FK holds), updates nothing (IM-A, 04 T-SRC-02) and disables nothing. It
    witnesses the pre-write refusal ONLY: the first application of ``SF-ORD-Q-030`` refuses by name
    (``SOURCE_ORDER_CONTENT_MISMATCH``, the differing members named) with NO partial writes — no
    contract, no event, no new ``source_order`` row, no customer, no exception item; the planted
    rows byte-identical; the object still counted in the control totals."""
    connection = _connection(world)
    run, _ = _sync(world, connection)
    [q001] = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-001")
    )
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    planted_id = UUID(int=0x30)
    with tenant_session(context) as session:
        session.execute(
            source_order.insert().values(
                tenant_id=world.tenant_id,
                id=planted_id,
                source_record_id=q001["source_record_id"],  # another record: a different digest
                source_system="SALESFORCE",
                external_order_id="SF-ORD-Q-030",
                external_version="1",
                order_number="Q-030-PLANTED",
                order_date=date(2026, 1, 1),
                customer_external_id="ACC-QUAY-1001",
                customer_id=q001["customer_id"],
                legal_entity_code="QUAY-US",
                transaction_currency="USD",
                grouping_values={},
                custom_attributes={"mapping_version": salesforce.MAPPING_VERSION},
                created_at=world.clock.now(),
                created_by=None,
                created_by_kind="SYSTEM",
            )
        )
    before = world.rows(select(source_order).where(source_order.c.id == planted_id))
    counts = _apply_one(
        world,
        connection,
        UUID(str(run["id"])),
        _order_object("SF-ORD-Q-030", product="QUAY-PLAT", quantity="2", total="200.00"),
    )
    [failure] = counts.failures
    assert failure["step"] == "reuse" and failure["rule_id"] == "SOURCE_ORDER_CONTENT_MISMATCH"
    assert failure["external_id"] == "SF-ORD-Q-030" and failure["external_version"] == "1"
    assert {"payload_sha256", "order_number", "order_date", "lines"} <= set(
        failure["detail"]["members"]
    )
    assert failure["detail"]["stored_record"] == str(q001["source_record_id"])
    assert counts.candidates == 0 and counts.contracts_booked == 0 and counts.customers_created == 0
    assert counts.records == 1  # stored and counted in the totals, whatever the ingestion outcome
    assert world.rows(select(contract).where(contract.c.external_id == "Q-030")) == []
    assert (
        world.rows(select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-030"))
        == before
    )
    assert (
        world.rows(select(exception_item).where(exception_item.c.business_key == "SF-ORD-Q-030"))
        == []
    )


def _amendment_object(external_id: str, parent: str) -> ports.SourceObject:
    return ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id=external_id,
        external_version="1",
        version_order=1,
        payload={
            "Id": external_id,
            "OrderNumber": external_id.removeprefix("SF-ORD-"),
            "Status": "Activated",
            "EffectiveDate": "2026-09-18",
            "AccountId": "ACC-QUAY-1001",
            "CurrencyIsoCode": "USD",
            "Parent_Order__c": parent,
            "Amendment_Reason__c": "Upsell",
            "OrderItems": {
                "records": [
                    {
                        "Id": f"{external_id.replace('SF-ORD-', 'SF-OI-')}-1",
                        "ProductCode": "QUAY-PLAT",
                        "Quantity": "1",
                        "TotalPrice": "1.00",
                    }
                ]
            },
        },
    )


def test_unchanged_unknown_parent_amendment_reprocess_keeps_the_item_open(world: World) -> None:
    """04 §16.14 rev 1.81 (Codex 0606 witness (3)): an amendment of an UNKNOWN parent raises
    ``MODIFICATION_CANDIDATE_UNAPPLIED``; reprocessing its unchanged stored record raises the SAME
    item again (its dedupe key in this run's ``raised_keys``), so the item stays OPEN with its
    occurrence increased and ``reprocessed_at`` set — never resolved by a re-run that did not clear
    its cause; its candidate rows reused, never stored again (R1)."""
    connection = _connection(world)
    run, _ = _sync(world, connection)
    counts = _apply_one(
        world,
        connection,
        UUID(str(run["id"])),
        _amendment_object("SF-ORD-Q-020-A1", parent="SF-ORD-Q-020"),  # never synced
    )
    assert counts.candidates == 1 and counts.exceptions == 1 and counts.failures == []
    [item] = world.rows(
        select(exception_item).where(exception_item.c.business_key == "SF-ORD-Q-020-A1")
    )
    assert item["code"] == "MODIFICATION_CANDIDATE_UNAPPLIED" and item["occurrence_count"] == 1
    assert item["reprocessed_at"] is None
    finished = _reprocessed(world, item)
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS", finished["result"]
    assert finished["result"]["counts"]["reprocessed"] == 1
    [again] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert again["status"] == "OPEN" and again["occurrence_count"] == 2  # raised again, same item
    assert again["reprocessed_at"] is not None and again["resolution"] is None
    candidates = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-020-A1")
    )
    assert len(candidates) == 1  # the candidate rows reused, never stored again (R1)


def test_failed_rebook_keeps_the_item_open(world: World) -> None:
    """04 §16.14 rev 1.81 (Codex 0606 witness (4)): after the alias repair, the DRAFT is VOIDED
    through the real ``POST /contracts/{id}/request-void`` + approval before the reprocess, so the
    DRAFT replacement is refused ("Only a draft contract can be replaced.") and recorded as the
    object's failure; the item stays OPEN with ``reprocessed_at`` set; the run is FAILED (its job
    outcome SUCCEEDED_WITH_EXCEPTIONS carries that status) — a failed re-application settles
    nothing."""
    connection = _connection(world)
    _sync(world, connection)
    [item] = world.rows(select(exception_item).where(exception_item.c.code == "PRODUCT_UNMAPPED"))
    [q003] = world.rows(select(contract).where(contract.c.external_id == "Q-003"))
    _alias(world, connection, "SF-PROD-X99", "QUAY-ADDON")
    reviewer = colleague(world.tenant_id, "priya")
    assign(reviewer, "revenue_reviewer")  # contract.approve
    priya = enrolled(world.app, world.clock, reviewer)
    requested = post(
        world.app,
        f"/api/v1/contracts/{q003['id']}/request-void",
        world.nikhil,
        {"reason_code": "CREATED_IN_ERROR", "comment": "Void the DRAFT before the reprocess."},
        if_match=f'"s{q003["head_stream_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    decided = approve(world.app, str(requested.json()["approval_request_id"]), priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    [voided] = world.rows(select(contract).where(contract.c.id == q003["id"]))
    assert voided["status"] == "VOIDED"
    finished = _reprocessed(world, item)
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS", finished["result"]
    assert finished["result"]["status"] == "FAILED"
    [run] = world.rows(select(sync_run).where(sync_run.c.job_id == finished["id"]))
    assert run["status"] == "FAILED"
    # SYNC-PROBLEM-SHAPE-1: the T-PLT-27 envelope; the records verbatim under ``failures``
    assert run["problem"]["type"].endswith("/sync-objects-not-applied")
    assert run["problem"]["status"] == 422 and run["problem"]["errors"] == []
    assert run["problem"]["instance"] == f"/api/v1/sync-runs/{run['id']}"
    [failure] = run["problem"]["failures"]
    assert failure["step"] == "rebook" and failure["external_id"] == "SF-ORD-Q-003"
    assert "Only a draft contract can be replaced." in failure["error"]
    [still] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert still["status"] == "OPEN" and still["resolution"] is None
    assert still["reprocessed_at"] is not None and still["occurrence_count"] == 1


def test_derivation_change_is_refused_by_name_with_no_partial_writes(world: World) -> None:
    """04 §16.14 rev 1.81 (Codex 0606 witness (5), class C): the connection's default performing
    entity changes after the first ingestion; the reprocess of the unchanged stored record is
    refused by name (``SOURCE_ORDER_DERIVATION_CHANGED``, the members named) BEFORE any write — no
    new contract, event, modification or ``source_order`` row; the stored rows byte-identical; the
    item unchanged apart from ``reprocessed_at`` (the reprocess ran over its record); the run
    FAILED. Class C guards the entity only "when the source names no entity (the connection's
    default)", and WLD-F-31's orders all name ``QUAY-US``; so the source order of this witness is
    served without ``Performing_Entity__c`` and its first ingestion stores the DEFAULT entity."""
    connection = _connection(world)
    # The mock's in-memory scenario (05 ADP-22; reset by the fixture): this source order names no
    # performing entity, so ``default_performing_entity`` derives it (PRD J-23.2).
    served = world.app.state.mocks.adapters[sf_mock.CODE].scenario.orders["SF-ORD-Q-003"]
    named = served.header.pop("Performing_Entity__c")
    assert named == "QUAY-US"  # what WLD-F-31 serves for every order
    _sync(world, connection)
    [stored] = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-003")
    )
    assert stored["legal_entity_code"] == "QUAY-US"  # derived from the connection's default
    [item] = world.rows(select(exception_item).where(exception_item.c.code == "PRODUCT_UNMAPPED"))
    _alias(world, connection, "SF-PROD-X99", "QUAY-ADDON")
    rows_before = {
        "contracts": world.rows(select(contract.c.id).order_by(contract.c.id)),
        "events": world.rows(select(contract_event.c.id).order_by(contract_event.c.id)),
        "orders": world.rows(select(source_order).order_by(source_order.c.id)),
        "lines": world.rows(select(source_order_line).order_by(source_order_line.c.id)),
    }
    shown = get(world.app, f"{INTEGRATIONS}/{connection['id']}", world.nikhil)
    changed = patch(
        world.app,
        f"{INTEGRATIONS}/{connection['id']}",
        world.nikhil,
        {"config": {"default_performing_entity": "QUAY-EU"}},
        if_match=shown.headers["ETag"],
    )
    assert changed.status_code == 200, changed.text
    finished = _reprocessed(world, item)
    assert finished["state"] == "SUCCEEDED_WITH_EXCEPTIONS", finished["result"]
    assert finished["result"]["status"] == "FAILED"
    [run] = world.rows(select(sync_run).where(sync_run.c.job_id == finished["id"]))
    assert run["problem"]["title"] == "Some source objects were not applied"  # the envelope
    assert run["problem"]["detail"].startswith("1 of 1 source objects were not applied.")
    [failure] = run["problem"]["failures"]
    assert failure["step"] == "reuse" and failure["rule_id"] == "SOURCE_ORDER_DERIVATION_CHANGED"
    assert failure["external_id"] == "SF-ORD-Q-003"
    assert "legal_entity_code" in failure["detail"]["members"]
    assert {
        "contracts": world.rows(select(contract.c.id).order_by(contract.c.id)),
        "events": world.rows(select(contract_event.c.id).order_by(contract_event.c.id)),
        "orders": world.rows(select(source_order).order_by(source_order.c.id)),
        "lines": world.rows(select(source_order_line).order_by(source_order_line.c.id)),
    } == rows_before  # no partial writes; the stored rows byte-identical
    assert world.rows(select(modification).where(modification.c.contract_id.isnot(None))) == []
    [still] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert still["status"] == "OPEN" and still["occurrence_count"] == 1
    assert still["reprocessed_at"] is not None and still["resolution"] is None


def _two_line_object(external_id: str, first: str, second: str) -> ports.SourceObject:
    key = external_id.replace("SF-ORD-", "SF-OI-")
    return ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id=external_id,
        external_version="1",
        version_order=1,
        payload={
            "Id": external_id,
            "OrderNumber": external_id.removeprefix("SF-ORD-"),
            "Status": "Activated",
            "EffectiveDate": "2026-09-18",
            "AccountId": "ACC-QUAY-1001",
            "CurrencyIsoCode": "USD",
            "OrderItems": {
                "records": [
                    {
                        "Id": f"{key}-1",
                        "ProductCode": first,
                        "Quantity": "1",
                        "TotalPrice": "100000.00",
                    },
                    {
                        "Id": f"{key}-2",
                        "ProductCode": second,
                        "Quantity": "1",
                        "TotalPrice": "5000.00",
                    },
                ]
            },
        },
    )


def test_partial_booking_with_an_aliased_first_line_reprocesses_on_the_same_record(
    world: World,
) -> None:
    """Codex 0652 §1 (the R1 residual; 04 rev 1.81 §16.14 / T-SRC-03 in place): alias SF-PROD-PLAT
    → QUAY-PLAT BEFORE the first ingestion of a two-line order (SF-PROD-PLAT / SF-PROD-X99) → a
    partial DRAFT from line 1 whose stored row keeps the SOURCE code with the resolved
    ``product_id``; alias SF-PROD-X99 → QUAY-ADDON; the same-record reprocess passes the class-A
    check (the source codes equal) and re-books BOTH lines; one ``source_order`` row, the lines and
    the record digest unchanged; the item RESOLVED."""
    connection = _connection(world)
    run, _ = _sync(world, connection)
    _alias(world, connection, "SF-PROD-PLAT", "QUAY-PLAT")  # the first line aliased up front
    counts = _apply_one(
        world,
        connection,
        UUID(str(run["id"])),
        _two_line_object("SF-ORD-Q-040", "SF-PROD-PLAT", "SF-PROD-X99"),
    )
    assert counts.contracts_booked == 1 and counts.unmapped_products == 1 and counts.failures == []
    [q040] = world.rows(select(contract).where(contract.c.external_id == "Q-040"))
    keys = world.rows(
        select(obligation.c.obligation_key, product.c.code)
        .join(product, product.c.id == obligation.c.product_id)
        .where(obligation.c.contract_id == q040["id"])
    )
    assert [(k["obligation_key"], k["code"]) for k in keys] == [("SF-OI-Q-040-1", "QUAY-PLAT")]
    [stored] = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-040")
    )
    [plat] = world.rows(select(product.c.id).where(product.c.code == "QUAY-PLAT"))
    stored_lines = world.rows(
        select(source_order_line)
        .where(source_order_line.c.source_order_id == stored["id"])
        .order_by(source_order_line.c.line_no)
    )
    assert [(line["product_code"], line["product_id"]) for line in stored_lines] == [
        ("SF-PROD-PLAT", plat["id"]),  # the SOURCE code and its resolution, two columns
        ("SF-PROD-X99", None),
    ]
    [item] = world.rows(
        select(exception_item).where(exception_item.c.business_key == "SF-ORD-Q-040")
    )
    assert item["code"] == "PRODUCT_UNMAPPED" and item["contract_id"] == q040["id"]
    [record] = world.rows(
        select(source_record).where(source_record.c.id == item["source_record_id"])
    )
    _alias(world, connection, "SF-PROD-X99", "QUAY-ADDON")
    finished = _reprocessed(world, item)
    assert finished["state"] == "SUCCEEDED", finished["result"]  # no false content mismatch
    assert finished["result"]["counts"]["rebooked"] == 1
    keys = world.rows(
        select(obligation.c.obligation_key, product.c.code)
        .join(product, product.c.id == obligation.c.product_id)
        .where(obligation.c.contract_id == q040["id"])
        .order_by(obligation.c.obligation_key)
    )
    assert [(k["obligation_key"], k["code"]) for k in keys] == [
        ("SF-OI-Q-040-1", "QUAY-PLAT"),
        ("SF-OI-Q-040-2", "QUAY-ADDON"),
    ]
    assert world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-040")
    ) == [stored]
    assert (
        world.rows(
            select(source_order_line)
            .where(source_order_line.c.source_order_id == stored["id"])
            .order_by(source_order_line.c.line_no)
        )
        == stored_lines
    )  # IM-A: the rows unchanged
    [same] = world.rows(select(source_record).where(source_record.c.id == item["source_record_id"]))
    assert same["payload_sha256"] == record["payload_sha256"]  # the retained identity unchanged
    [settled] = world.rows(select(exception_item).where(exception_item.c.id == item["id"]))
    assert settled["status"] == "RESOLVED" and settled["resolution"] == "Input processed"


def test_same_id_amendment_basis_is_the_booked_order_not_the_candidate(world: World) -> None:
    """Codex 0339 §1 DIN12-AMENDMENT-BASIS-1 (database witness): after Q-001 is booked, the parent
    basis read for the (never computed) DRAFT is its CONTRACT_BOOKED payload (L1 100000, L2
    20000); a recorded same-id candidate (Q-001 version 2 with an Amendment_Reason) never becomes
    the basis, and its mechanical diff carries the +30000 delta on L1 (PRICE_CHANGE)."""
    connection = _connection(world)
    _sync(world, connection)
    [parent] = world.rows(select(contract).where(contract.c.external_id == "Q-001"))
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        found = sync_module._parent_basis(session, parent)
    assert found.unkeyed == () and found.refused is None
    before = dict(found.lines)
    # The booked payload's money is API-S-Money (04 API-C-06: "exactly the currency's minor-unit
    # decimals", two for USD) — not the NUMERIC(…,4) text of a ``source_order_line`` row; the +30000
    # delta below is "30000.00" for the same reason.
    assert {key: str(line["total_price"]) for key, line in before.items()} == {
        "SF-OI-Q-001-1": "100000.00",
        "SF-OI-Q-001-2": "20000.00",
    }
    candidate = ports.NormalisedOrderDraft(
        source_system=SourceSystem.SALESFORCE,
        external_order_id="SF-ORD-Q-001",
        external_version="2",
        order_number="Q-001",
        order_date=date(2026, 9, 20),
        customer_external_id="ACC-QUAY-1001",
        legal_entity_code="QUAY-US",
        transaction_currency="USD",
        lines=(
            ports.NormalisedLine("SF-OI-Q-001-1", "QUAY-PLAT", Decimal(1), Decimal("130000.00")),
            ports.NormalisedLine("SF-OI-Q-001-2", "QUAY-SVC", Decimal(40), Decimal("20000.00")),
        ),
        amendment_reason="Upsell",
    )
    principal = sync_module.sync_principal(world.tenant_id)
    with system_unit_of_work(world.runtime, principal, request_id="tests-basis") as uow:
        [record] = world.rows(
            select(source_record).where(source_record.c.external_id == "SF-ORD-Q-001")
        )
        order = sync_module._normalised_order(
            candidate, source_record_id=record["id"], customer_id=parent["customer_id"]
        )
        grouping.record_candidate(uow, order)  # the candidate rows exist before the basis is read
        uow.commit()
    with tenant_session(context, read_only=True) as session:
        after = dict(sync_module._parent_basis(session, parent).lines)
    assert after == before  # the candidate never enters the basis
    lines, kind = sync_module.amendment_lines(candidate, after)
    assert [
        (line["obligation_key"], line["action"], line["consideration_delta"]["amount"])
        for line in lines
    ] == [("SF-OI-Q-001-1", "CHANGE", "30000.00")]
    assert kind.value == "PRICE_CHANGE"


def test_order_amendment_becomes_draft_modification(world: World) -> None:
    """05 ADP-05: an amended order (``Parent_Order__c``) creates a DRAFT modification requiring
    classification and appends no ``CONTRACT_AMENDED``. On the lane the parent booked by this sync
    is still DRAFT, so the non-ACTIVE branch of D-98 146 A1 Q-B is exercised: the candidate's
    ``source_order`` rows are recorded, ``MODIFICATION_CANDIDATE_UNAPPLIED`` is raised (remediable,
    naming the parent) and no event is appended; the ACTIVE-parent DRAFT modification with its
    provisional kind is a follow-up on an activated world."""
    connection = _connection(world)
    _sync(world, connection)  # books Q-001 (the parent) as a DRAFT contract
    [parent] = world.rows(select(contract).where(contract.c.external_id == "Q-001"))
    amendment = ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id="SF-ORD-Q-001-A1",
        external_version="1",
        version_order=1,
        payload={
            "Id": "SF-ORD-Q-001-A1",
            "OrderNumber": "Q-001-A1",
            "Status": "Activated",
            "EffectiveDate": "2026-09-15",
            "AccountId": "ACC-QUAY-1001",
            "CurrencyIsoCode": "USD",
            "Performing_Entity__c": "QUAY-US",
            "Parent_Order__c": "SF-ORD-Q-001",
            "Amendment_Reason__c": "Upsell",
            "OrderItems": {
                "records": [
                    {
                        "Id": "SF-OI-Q-001-1",
                        "ProductCode": "QUAY-PLAT",
                        "Quantity": "1",
                        "TotalPrice": "130000.00",
                    },
                    {
                        "Id": "SF-OI-Q-001-3",
                        "ProductCode": "QUAY-ADDON",
                        "Quantity": "5",
                        "TotalPrice": "6000.00",
                    },
                ]
            },
        },
    )
    principal = sync_module.sync_principal(world.tenant_id)
    with system_unit_of_work(world.runtime, principal, request_id="tests-amendment") as uow:
        [row] = world.rows(
            select(integration_connection).where(
                integration_connection.c.id == UUID(connection["id"])
            )
        )
        adapter = sync_module.adapter_for(
            row, tenant_code="quayside", client=asgi_client(world.app)
        )
        counts = sync_module.Counts()
        loaded: list[tuple[str, str, str, Decimal]] = []
        run_id = UUID(str(world.rows(select(sync_run.c.id))[0]["id"]))
        applied = sync_module.apply_object(
            uow,
            adapter,
            row,
            amendment,
            notified_versions=("1",),
            sync_run_id=run_id,
            counts=counts,
            loaded=loaded,
        )
        uow.commit()
    assert applied is True and counts.candidates == 1 and counts.modifications_drafted == 0
    assert counts.failures == [] and counts.exceptions == 1
    [item] = world.rows(
        select(exception_item).where(exception_item.c.code == "MODIFICATION_CANDIDATE_UNAPPLIED")
    )
    assert item["source"] == "SYNC" and item["disposition"] == "remediable"
    assert item["contract_id"] == parent["id"] and item["business_key"] == "SF-ORD-Q-001-A1"
    assert "is DRAFT and not ACTIVE" in item["message"]  # PRD IMP-123 copy
    [candidate] = world.rows(
        select(source_order).where(source_order.c.external_order_id == "SF-ORD-Q-001-A1")
    )
    assert candidate["parent_order_external_id"] == "SF-ORD-Q-001"
    events = world.rows(
        select(contract_event.c.event_type).where(contract_event.c.contract_id == parent["id"])
    )
    assert [event["event_type"] for event in events] == ["CONTRACT_BOOKED"]  # no CONTRACT_AMENDED
    assert (
        world.rows(select(contract).where(contract.c.external_id == "Q-001-A1")) == []
    )  # no new contract


def _seed_pre_rule_order(
    world: World, connection: dict[str, Any], run_id: UUID, obj: ports.SourceObject, *, target: str
) -> tuple[UUID, UUID]:
    """Positive-path seeding through internal writers with a constructed pre-1.81 input, under
    supervisor exception DIN-SEED-EXC-1 (form (a); a direct INSERT is refused). The T-SRC tables are
    IM-A and no current command writes the alias target into ``product_code``, so pre-rule history
    cannot be produced by any command: the record is stored by the real ``store_source_record``
    (the real tokenised payload and digest), the order by the real ``record_candidate`` →
    ``_store_order`` (the real rows, resolution and ``source_order.create`` audit anchor), fed the
    value the pre-1.81 normaliser passed — the first line's ``product_code`` = the alias TARGET
    (``target``), no booking code. Everything else is the adapter's own draft. Returns (record,
    order)."""
    principal = sync_module.sync_principal(world.tenant_id)
    with system_unit_of_work(
        world.runtime, principal, request_id=f"tests-seed-{obj.external_id}"
    ) as uow:
        [row] = world.rows(
            select(integration_connection).where(
                integration_connection.c.id == UUID(connection["id"])
            )
        )
        adapter = sync_module.adapter_for(
            row, tenant_code="quayside", client=asgi_client(world.app)
        )
        [draft] = adapter.normalise(obj, sync_module.mapping_version_of(row)).orders
        stored = store_source_record(
            uow,
            identity=SourceIdentity(
                obj.source_system, obj.object_type, obj.external_id, obj.external_version
            ),
            version_order=obj.version_order,
            payload=obj.payload,
            sync_run_id=run_id,
        )
        customer_id = sync_module.lookup_customer(uow.session, UUID(connection["id"]), draft)
        assert customer_id is not None
        order = sync_module._normalised_order(
            draft, source_record_id=stored.id, customer_id=customer_id
        )
        first, *rest = order.lines
        pre_rule = dataclasses.replace(
            order,
            lines=(
                dataclasses.replace(first, product_code=target, booking_product_code=None),
                *rest,
            ),
        )
        order_id = grouping.record_candidate(uow, pre_rule)
        uow.commit()
    return stored.id, order_id


def _rename(world: World, product_id: UUID, changes: dict[str, Any]) -> None:
    """The LAWFUL product change: ``PATCH /products/{id}`` under maintain with If-Match."""
    [current] = world.rows(select(product.c.row_version).where(product.c.id == product_id))
    done = patch(
        world.app,
        f"/api/v1/products/{product_id}",
        world.nikhil,
        changes,
        if_match=f'"r{current["row_version"]}"',
    )
    assert done.status_code == 200, done.text


def test_a_lawful_product_rename_does_not_refuse_the_unchanged_pre_rule_source(
    world: World,
) -> None:
    """04 §16.14 rev 1.91 (Codex production-20260922-1442 §1 and 1508 §1, DIN-HISTORICAL-ALIAS-
    RENAME-1) — the discriminating trajectory public PATCH → retained receipt → reprocess, by CHAIN
    POSITION at ONE clock instant, BRACKETING the receipt (Codex 1508 §1's table: rename A→B, the
    receipt storing B, rename B→C — all at one instant): WITHOUT advancing the frozen clock, the
    LAWFUL rename of P from QUAY-EDGE (A) to QUAY-EDGE-B (B) through ``PATCH /products/{id}``; a
    pre-1.81 row carrying the alias TARGET at receipt (P, QUAY-EDGE-B) — seeded under
    DIN-SEED-EXC-1, see ``_seed_pre_rule_order``; a name-only PATCH (no code on either side:
    excluded); the LAWFUL
    rename of P to QUAY-EDGE2 (C); a rename of an unrelated product — every audit row with the
    receipt's ``occurred_at``; then the unchanged source applied again over its stored rows: NOT
    refused — the receipt anchor and the chain walk-back give B, neither A (the pre-receipt code the
    ``>=`` clock predicate would pick) nor C (the current code the strict ``>`` predicate would
    keep), the two lines book on the CURRENT products, the seeded rows and digest unchanged (IM-A).
    Beside
    it the altered-content refusal
    still IS refused: a second seeded row whose stored code (QUAY-OTHER) was never P's is named by
    ``SOURCE_ORDER_CONTENT_MISMATCH`` with ``history`` receipt-anchored and no writes (the :669
    refusal witness stays as well). No per-reprocess chain verification is run; a KRN-AUD FAIL
    result is not consulted.

    The world (04 §14.1 DB-05 rev 1.160, item PRODUCT-CODE-FREEZE-1; supervisor ruling R-112 (i)):
    a rename is lawful only while no contract line, SSP entry or account mapping rule references
    the product, so P and the unrelated product are two that the orders of the first sync do not
    name (QUAY-EDGE and QUAY-SPARE); until the reprocess books Q-043 nothing references P."""
    connection = _connection(world)
    run, _ = _sync(world, connection)
    for code in ("QUAY-EDGE", "QUAY-SPARE"):  # in use by nothing: their codes may change
        new_product(world.app, world.nikhil, code=code, name=code.replace("-", " ").title())
    _alias(world, connection, "SF-PROD-PLAT", "QUAY-EDGE")  # in force at the receipts below
    [plat] = world.rows(select(product.c.id).where(product.c.code == "QUAY-EDGE"))
    [svc] = world.rows(select(product.c.id).where(product.c.code == "QUAY-SPARE"))
    plat_id, svc_id = UUID(str(plat["id"])), UUID(str(svc["id"]))
    # the same clock instant for everything that follows: only the chain separates the events
    _rename(world, plat_id, {"code": "QUAY-EDGE-B"})  # A→B, BEFORE the receipt
    unchanged = _two_line_object("SF-ORD-Q-043", "SF-PROD-PLAT", "SF-PROD-X99")
    record_043, order_043 = _seed_pre_rule_order(  # the receipt: the target as it stood, B
        world, connection, UUID(str(run["id"])), unchanged, target="QUAY-EDGE-B"
    )
    altered = _two_line_object("SF-ORD-Q-044", "SF-PROD-PLAT", "SF-PROD-X99")
    record_044, _order_044 = _seed_pre_rule_order(
        world, connection, UUID(str(run["id"])), altered, target="QUAY-OTHER"
    )
    seeded_lines = world.rows(
        select(source_order_line)
        .where(source_order_line.c.source_order_id == order_043)
        .order_by(source_order_line.c.line_no)
    )
    assert [(line["product_code"], line["product_id"]) for line in seeded_lines] == [
        ("QUAY-EDGE-B", plat_id),  # the pre-1.81 shape: the alias target AT RECEIPT as the code
        ("SF-PROD-X99", None),
    ]
    [anchor] = world.rows(
        select(audit_event.c.chain_seq, audit_event.c.object_id, audit_event.c.detail).where(
            audit_event.c.action == "source_order.create",
            audit_event.c.detail["ids"].contains([str(order_043)]),
        )
    )
    assert anchor["object_id"] is None and anchor["detail"]["ids"] == [str(order_043)]
    [before_digest] = world.rows(
        select(source_record.c.payload_sha256).where(source_record.c.id == record_043)
    )
    _rename(world, plat_id, {"name": "Quayside Edge (renamed label)"})  # non-code: no code
    _rename(world, plat_id, {"code": "QUAY-EDGE2"})  # B→C, AFTER the receipt: the LAWFUL rename
    _rename(world, svc_id, {"code": "QUAY-SPARE2"})  # an unrelated product: never selected
    events = world.rows(
        select(
            audit_event.c.chain_seq,
            audit_event.c.occurred_at,
            audit_event.c.before,
            audit_event.c.after,
        )
        .where(audit_event.c.action == "product.update", audit_event.c.object_id == plat_id)
        .order_by(audit_event.c.chain_seq)
    )
    assert [(e["before"], e["after"]) for e in events] == [
        ({"code": "QUAY-EDGE"}, {"code": "QUAY-EDGE-B"}),  # A→B
        ({"name": "Quay Edge"}, {"name": "Quayside Edge (renamed label)"}),  # no code
        ({"code": "QUAY-EDGE-B"}, {"code": "QUAY-EDGE2"}),  # B→C
    ]  # the writer audits only the CHANGED members (condition 2)
    before_receipt, _label, after_receipt = events
    assert before_receipt["chain_seq"] < anchor["chain_seq"] < after_receipt["chain_seq"]
    [receipt] = world.rows(select(source_order.c.created_at).where(source_order.c.id == order_043))
    assert {e["occurred_at"] for e in events} == {receipt["created_at"]}  # ONE instant: the clock
    # cannot separate A→B, the receipt and B→C; only the chain position does (Codex 1508 §1)
    _alias(world, connection, "SF-PROD-X99", "QUAY-ADDON")
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        lineage = grouping.alias_lineage_at(
            session,
            UUID(connection["id"]),
            {"SF-PROD-PLAT"},
            receipt["created_at"],
            tenant_id=world.tenant_id,
            order_id=order_043,
        )
    assert lineage.targets == {"SF-PROD-PLAT": (plat_id, "QUAY-EDGE-B")}  # B: the code AT receipt
    assert lineage.evidence == {"SF-PROD-PLAT": grouping.HistoryState.RECEIPT_ANCHORED}
    assert lineage.renames == {"SF-PROD-PLAT": 1}  # only B→C walked back; A→B is before the anchor
    [_pid, compared] = lineage.targets["SF-PROD-PLAT"]
    assert compared not in (
        "QUAY-EDGE",
        "QUAY-EDGE2",
    )  # neither the pre-receipt nor the current code
    counts = _apply_one(world, connection, UUID(str(run["id"])), unchanged, stored_id=record_043)
    assert counts.failures == [], counts.failures  # NOT refused: the compatibility path admits
    assert counts.reprocessed == 1 and counts.contracts_booked == 1
    assert counts.unmapped_products == 0
    [q043] = world.rows(select(contract).where(contract.c.external_id == "Q-043"))
    keys = world.rows(
        select(obligation.c.obligation_key, product.c.code)
        .join(product, product.c.id == obligation.c.product_id)
        .where(obligation.c.contract_id == q043["id"])
        .order_by(obligation.c.obligation_key)
    )
    assert [(k["obligation_key"], k["code"]) for k in keys] == [
        ("SF-OI-Q-043-1", "QUAY-EDGE2"),  # booked on the CURRENT product; the stored row untouched
        ("SF-OI-Q-043-2", "QUAY-ADDON"),
    ]
    assert (
        world.rows(
            select(source_order_line)
            .where(source_order_line.c.source_order_id == order_043)
            .order_by(source_order_line.c.line_no)
        )
        == seeded_lines
    )  # IM-A: the seeded rows unchanged
    [after_digest] = world.rows(
        select(source_record.c.payload_sha256).where(source_record.c.id == record_043)
    )
    assert after_digest == before_digest  # the retained identity unchanged
    # beside it: altered content is STILL refused by name, its history anchored, with no writes
    counts = _apply_one(world, connection, UUID(str(run["id"])), altered, stored_id=record_044)
    [failure] = counts.failures
    assert failure["step"] == "reuse" and failure["rule_id"] == "SOURCE_ORDER_CONTENT_MISMATCH"
    assert failure["detail"]["members"] == ["lines.SF-OI-Q-044-1.product_code"]
    assert failure["detail"]["history"]["SF-PROD-PLAT"]["evidence"] == "receipt-anchored"
    assert "conservative refusal" not in failure["error"]
    assert counts.contracts_booked == 0 and counts.candidates == 0
    assert world.rows(select(contract).where(contract.c.external_id == "Q-044")) == []
