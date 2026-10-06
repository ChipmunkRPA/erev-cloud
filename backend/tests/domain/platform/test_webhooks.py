"""Outbound webhooks (dev-guide §5.11 DG-KRN-EVT-07; 04 T-PLT-35, T-PLT-36; 05 NTR-10 to NTR-13,
SAR-15, SCH-12; BUILD_SPEC PLF-24, BS1-D-08).

The tests play the worker: deliveries go through ``WebhookClient`` over an in-process mock transport
with a fixed resolver, so no request leaves the process.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.email import build_email_sender
from erev_api.adapters.http import guard
from erev_api.adapters.http.guard import DestinationRefused, check_destination
from erev_api.adapters.http.webhook_client import WebhookClient
from erev_api.audit.verify import rfc3339
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, outbox_message, tenant, webhook_delivery
from erev_api.domain.platform.webhook_endpoints import (
    CreatedEndpoint,
    create_endpoint,
    update_endpoint,
)
from erev_api.enums import JobKind, JobState, OutboxTopic, PrincipalKind, TenantKind
from erev_api.events import webhooks
from erev_api.events.outbox import RelayStats, relay
from erev_api.events.webhooks import DeliveryStats, deliver, emit_webhook, signature_header
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import select, text
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.http import HttpRequest, mock_transport

PUBLIC_ADDRESS = "93.184.216.34"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def _public(host: str, port: int) -> list[str]:
    return [PUBLIC_ADDRESS]


def _resolving_to(address: str) -> Callable[[str, int], list[str]]:
    return lambda host, port: [address]


class Receiver:
    """A mock endpoint answering every request with ``status`` and keeping the requests."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest) -> int:
        self.requests.append(request)
        return self.status


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring, clock=clock))


def _runtime(
    settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    receiver: Receiver,
    *,
    env: Environment = Environment.TEST,
) -> JobRuntime:
    return JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(settings.file_root),
        email=build_email_sender(settings, clock),
        public_origin=settings.public_origin,
        webhooks=WebhookClient(env=env, transport=mock_transport(receiver), resolve=_public),
    )


@pytest.fixture
def run_settings(app_settings: Settings, tmp_path: Path) -> Settings:
    return app_settings.model_copy(update={"run_dir": tmp_path / ".run"})


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@contextmanager
def _uow(tenant_id: UUID, runtime: JobRuntime) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-webhooks",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=runtime.clock.now(),
        format_locale="en-US",
    )
    assert runtime.keyring is not None and runtime.files is not None
    with unit_of_work(
        ctx, clock=runtime.clock, keyring=runtime.keyring, files=runtime.files
    ) as uow:
        yield uow


def _endpoint(
    tenant_id: UUID, runtime: JobRuntime, url: str, kinds: Sequence[str]
) -> CreatedEndpoint:
    with _uow(tenant_id, runtime) as uow:
        created = create_endpoint(uow, url=url, description=None, event_kinds=kinds)
        uow.commit()
    return created


def _deactivate(tenant_id: UUID, runtime: JobRuntime, endpoint_id: UUID) -> None:
    with _uow(tenant_id, runtime) as uow:
        update_endpoint(uow, endpoint_id, {"is_active": False}, check_version=lambda _: None)
        uow.commit()


def _emit(tenant_id: UUID, runtime: JobRuntime, **data: Any) -> int:
    with _uow(tenant_id, runtime) as uow:
        count = emit_webhook(uow, event_kind="period.locked", payload=data)
        uow.commit()
    return count


def _worker(tenant_id: UUID, runtime: JobRuntime, kind: JobKind) -> JobContext:
    return JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=kind,
        principal=system_principal(tenant_id),
        runtime=runtime,
        persisted=False,
    )


def _deliveries(tenant_id: UUID) -> list[Mapping[str, Any]]:
    statement = select(webhook_delivery).order_by(webhook_delivery.c.webhook_endpoint_id)
    with tenant_session(_db(tenant_id)) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _id(created: CreatedEndpoint) -> UUID:
    value = created.endpoint["id"]
    assert isinstance(value, UUID)
    return value


def test_krn_evt_07_signature_header() -> None:
    secret = b"probe-signing-key-for-krn-evt-07"
    body = b'{"id":"x"}'
    expected = hmac.new(secret, b"1757678400." + body, "sha256").hexdigest()
    assert signature_header(secret, 1757678400, body) == f"t=1757678400,v1={expected}"
    assert webhooks.SIGNATURE_HEADER == "X-Erev-Signature"


def test_emit_one_delivery_per_subscribed_active_endpoint(
    tenant_id: UUID, run_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    runtime = _runtime(run_settings, keyring, clock, Receiver(204))
    first = _endpoint(tenant_id, runtime, "https://hooks.example/a", ["period.locked"])
    second = _endpoint(
        tenant_id, runtime, "https://hooks.example/b", ["run.completed", "period.locked"]
    )
    inactive = _endpoint(tenant_id, runtime, "https://hooks.example/off", ["period.locked"])
    _endpoint(tenant_id, runtime, "https://hooks.example/imports", ["import.committed"])
    _deactivate(tenant_id, runtime, _id(inactive))

    period_id = new_id()
    assert _emit(tenant_id, runtime, period_id=period_id, href=f"/api/v1/periods/{period_id}") == 2

    rows = _deliveries(tenant_id)
    assert sorted(row["webhook_endpoint_id"] for row in rows) == sorted([_id(first), _id(second)])
    now = clock.now()
    for row in rows:
        assert (row["event_kind"], row["status"], row["attempt_count"]) == (
            "period.locked",
            "PENDING",
            0,
        )
        assert (row["next_attempt_at"], row["abandon_at"]) == (now, now + timedelta(hours=24))
        assert row["payload_sha256"] == sha256_hex(row["payload"])
    # One envelope for the event, one WEBHOOK message per delivery.
    assert rows[0]["payload"] == rows[1]["payload"]
    with tenant_session(_db(tenant_id)) as session:
        messages = session.execute(
            select(outbox_message).where(outbox_message.c.topic == OutboxTopic.WEBHOOK.value)
        ).mappings()
        by_delivery = {row["aggregate_id"]: dict(row) for row in messages}
    assert set(by_delivery) == {row["id"] for row in rows}
    for delivery_id, message in by_delivery.items():
        assert (message["aggregate_type"], message["dedupe_key"], message["payload"]) == (
            "webhook_delivery",
            f"webhook:{delivery_id}",
            {"webhook_delivery_id": str(delivery_id)},
        )

    with _uow(tenant_id, runtime) as uow, pytest.raises(ValueError, match="event kind"):
        emit_webhook(uow, event_kind="contract.created", payload={})


def test_ntr_10_payload_ids_only(
    tenant_id: UUID, run_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    receiver = Receiver(204)
    runtime = _runtime(run_settings, keyring, clock, receiver)
    created = _endpoint(tenant_id, runtime, "https://hooks.example/erev", ["period.locked"])
    period_id = new_id()
    _emit(tenant_id, runtime, period_id=period_id, href=f"/api/v1/periods/{period_id}")

    # The relay dispatches the provisioned invitation and the WEBHOOK message, whose handler
    # makes the first attempt.
    assert relay(_worker(tenant_id, runtime, JobKind.OUTBOX_RELAY)) == RelayStats(
        claimed=2, dispatched=2, failed=0, dead=0
    )
    [request] = receiver.requests
    body = json.loads(request.content)
    with tenant_session(_db(tenant_id)) as session:
        code = session.execute(select(tenant.c.code).where(tenant.c.id == tenant_id)).scalar_one()
    assert body == {
        "id": body["id"],
        "kind": "period.locked",
        "tenant_code": code,
        "occurred_at": rfc3339(clock.now()),
        "data": {"href": f"/api/v1/periods/{period_id}", "period_id": str(period_id)},
    }
    assert UUID(body["id"])
    # NTR-11 over the raw body with the secret shown at creation; SAR-15 connects to the checked
    # address with the host in Host and SNI.
    secret = created.signing_secret.encode("ascii")
    assert request.headers["X-Erev-Signature"] == signature_header(
        secret, int(clock.now().timestamp()), request.content
    )
    assert (request.method, request.url.host, request.url.path) == ("POST", PUBLIC_ADDRESS, "/erev")
    assert request.headers["Host"] == "hooks.example"
    assert request.headers["Content-Type"] == "application/json"
    assert request.extensions["sni_hostname"] == "hooks.example"

    [row] = _deliveries(tenant_id)
    assert (row["status"], row["attempt_count"], row["last_response_status"]) == (
        "SUCCEEDED",
        1,
        204,
    )
    assert (row["succeeded_at"], row["next_attempt_at"], row["last_error"]) == (
        clock.now(),
        None,
        None,
    )

    for data in ({"amount": "1200.00"}, {"period_id": "P-2026-09"}, {"href": "https://x.test/"}):
        with _uow(tenant_id, runtime) as uow, pytest.raises(ValueError):
            emit_webhook(uow, event_kind="period.locked", payload=data)


def test_retry_backoff_and_abandon(
    tenant_id: UUID, run_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    receiver = Receiver(500)
    runtime = _runtime(run_settings, keyring, clock, receiver)
    _endpoint(tenant_id, runtime, "https://hooks.example/erev", ["period.locked"])
    _emit(tenant_id, runtime, period_id=new_id())
    worker = _worker(tenant_id, runtime, JobKind.WEBHOOK_DELIVERY)
    created_at = clock.now()

    assert deliver(worker) == DeliveryStats(claimed=1, succeeded=0, failed=1, abandoned=0)
    [row] = _deliveries(tenant_id)
    assert (
        row["status"],
        row["attempt_count"],
        row["last_response_status"],
        row["last_error"],
    ) == (
        "FAILED",
        1,
        500,
        "HTTP 500",
    )
    assert row["next_attempt_at"] == created_at + timedelta(seconds=30)
    clock.advance(timedelta(seconds=29))
    assert deliver(worker).claimed == 0

    # SCH-12: the minute sweep defers one WEBHOOK_DELIVERY job for the tenant once it is due.
    clock.set(row["next_attempt_at"])
    webhooks.sweep(clock)
    webhooks.sweep(clock)
    with tenant_session(_db(tenant_id)) as session:
        jobs = session.execute(
            select(job.c.state, job.c.queue).where(job.c.kind == JobKind.WEBHOOK_DELIVERY.value)
        ).all()
    assert [(state, queue) for state, queue in jobs] == [(JobState.QUEUED.value, "outbox")]

    waits: dict[int, timedelta] = {}
    for attempt in range(2, 10):
        clock.set(row["next_attempt_at"])
        assert webhooks.delivery_job(worker, {}).result == {
            "counts": {"claimed": 1, "succeeded": 0, "failed": 1, "abandoned": 0}
        }
        [row] = _deliveries(tenant_id)
        assert (row["status"], row["attempt_count"]) == ("FAILED", attempt)
        waits[attempt] = row["next_attempt_at"] - clock.now()
    assert waits[2] == timedelta(seconds=60)
    assert waits[7] == timedelta(seconds=1920)
    # The eighth failure reaches the one-hour cap.
    assert waits[8] == waits[9] == timedelta(seconds=3600)

    abandon_at = created_at + timedelta(hours=24)
    assert row["abandon_at"] == abandon_at
    while row["status"] == "FAILED":
        assert row["next_attempt_at"] <= abandon_at
        clock.set(row["next_attempt_at"])
        deliver(worker)
        [row] = _deliveries(tenant_id)
    assert (row["status"], row["next_attempt_at"], row["last_error"]) == (
        "ABANDONED",
        None,
        "HTTP 500",
    )
    assert clock.now() == abandon_at
    assert row["attempt_count"] == len(receiver.requests)
    clock.advance(timedelta(days=1))
    assert deliver(worker).claimed == 0


def _run_delivery_job(tenant_id: UUID, runtime: JobRuntime) -> UUID:
    """A second WEBHOOK_DELIVERY job, fetched and run to completion as another worker would."""
    now = runtime.clock.now()
    with tenant_session(_db(tenant_id)) as session:
        row = registry.insert_job(
            session,
            JobKind.WEBHOOK_DELIVERY,
            {},
            tenant_id=tenant_id,
            now=now,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        )
        task_id = registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=now
        )
        session.execute(_FETCHED, {"id": task_id})
    job_id = UUID(str(row["id"]))
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    return job_id


def test_ntr_12_one_post_per_attempt_when_the_lease_lapses(
    tenant_id: UUID, run_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    """PR-R-01 (D-80): deliveries are claimed one at a time just before their POST, and a claim
    whose two-minute lease lapses during its POST is not posted again by a second deliverer."""
    second: list[UUID] = []

    class LapsingReceiver(Receiver):
        def __call__(self, request: HttpRequest) -> int:
            self.requests.append(request)
            if len(self.requests) == 1:
                clock.advance(timedelta(seconds=121))
                second.append(_run_delivery_job(tenant_id, runtime))
            return self.status

    receiver = LapsingReceiver(204)
    runtime = _runtime(run_settings, keyring, clock, receiver)
    _endpoint(tenant_id, runtime, "https://hooks.example/erev", ["period.locked"])
    for _ in range(3):
        _emit(tenant_id, runtime, period_id=new_id())

    # SCH-12 defers the tenant's delivery job, which a worker fetches and runs.
    webhooks.sweep(clock)
    with tenant_session(_db(tenant_id)) as session:
        first, task_id = session.execute(
            select(job.c.id, job.c.procrastinate_job_id).where(
                job.c.kind == JobKind.WEBHOOK_DELIVERY.value
            )
        ).one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(first, tenant_id, attempt=1, runtime=runtime)

    rows = _deliveries(tenant_id)
    posted = [json.loads(request.content)["id"] for request in receiver.requests]
    assert len(posted) == len(set(posted)) == 3
    assert sorted(posted) == sorted(row["payload"]["id"] for row in rows)
    assert [(row["status"], row["attempt_count"]) for row in rows] == [("SUCCEEDED", 1)] * 3
    with tenant_session(_db(tenant_id)) as session:
        finished = {
            row.id: (row.state, row.result["counts"])
            for row in session.execute(
                select(job.c.id, job.c.state, job.c.result).where(job.c.id.in_([first, *second]))
            )
        }
    assert finished == {
        first: ("SUCCEEDED", {"claimed": 1, "succeeded": 1, "failed": 0, "abandoned": 0}),
        second[0]: ("SUCCEEDED", {"claimed": 2, "succeeded": 2, "failed": 0, "abandoned": 0}),
    }


def test_inactive_endpoint_abandons_delivery(
    tenant_id: UUID, run_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    receiver = Receiver(204)
    runtime = _runtime(run_settings, keyring, clock, receiver)
    created = _endpoint(tenant_id, runtime, "https://hooks.example/erev", ["period.locked"])
    _emit(tenant_id, runtime, period_id=new_id())
    _deactivate(tenant_id, runtime, _id(created))

    worker = _worker(tenant_id, runtime, JobKind.WEBHOOK_DELIVERY)
    assert deliver(worker) == DeliveryStats(claimed=1, succeeded=0, failed=0, abandoned=1)
    [row] = _deliveries(tenant_id)
    assert (row["status"], row["attempt_count"], row["last_error"]) == (
        "ABANDONED",
        0,
        "The endpoint is inactive.",
    )
    assert receiver.requests == []


def test_sar_15_destination_guard(
    tenant_id: UUID, run_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    production = Environment.PRODUCTION
    for url in (
        "https://10.0.0.5/hook",
        "https://169.254.169.254/",
        "https://127.0.0.1/hook",
        "https://100.64.0.9/hook",
        "https://[::1]/hook",
        "https://[fe80::1]/hook",
        "https://[::ffff:192.168.1.4]/hook",
        "http://hooks.example/erev",
        "https://user:pw@hooks.example/erev",
    ):
        with pytest.raises(DestinationRefused):
            check_destination(url, env=production, resolve=_public)
    # D-80 (PR-R-08): only global unicast addresses pass. NAT64, IPv4-compatible and 6to4 addresses
    # are judged by their embedded IPv4 address; site-local, multicast, broadcast, reserved,
    # benchmarking and IETF protocol assignment addresses are refused. The SAR-15 ranges stay
    # refused, as a literal host and as a resolved address.
    for address in (
        "64:ff9b::a9fe:a9fe",
        "64:ff9b::7f00:1",
        "::a9fe:a9fe",
        "::7f00:1",
        "2002:a9fe:a9fe::1",
        "2002:0a00:0005::1",
        "fec0::1",
        "ff02::1",
        "224.0.0.1",
        "255.255.255.255",
        "240.0.0.1",
        "198.18.0.1",
        "192.0.0.170",
        "0.0.0.0",
        "10.0.0.5",
        "100.64.0.9",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "192.168.1.4",
        "::",
        "::1",
        "fc00::1",
        "fe80::1",
    ):
        literal = f"[{address}]" if ":" in address else address
        with pytest.raises(DestinationRefused, match="loopback, private, link-local"):
            check_destination(f"https://{literal}/hook", env=production)
        with pytest.raises(DestinationRefused, match="loopback, private, link-local"):
            check_destination(
                "https://hooks.example/erev", env=production, resolve=_resolving_to(address)
            )
    assert check_destination(f"https://{PUBLIC_ADDRESS}/hook", env=production).address == (
        PUBLIC_ADDRESS
    )
    # A host is refused when any address it resolves to is refused.
    with pytest.raises(DestinationRefused, match="loopback, private, link-local"):
        check_destination(
            "https://hooks.example/erev",
            env=production,
            resolve=lambda host, port: [PUBLIC_ADDRESS, "10.1.2.3"],
        )
    checked = check_destination("https://hooks.example:8443/erev", env=production, resolve=_public)
    assert (checked.scheme, checked.host, checked.netloc, checked.address) == (
        "https",
        "hooks.example",
        "hooks.example:8443",
        PUBLIC_ADDRESS,
    )

    # dev, test and e2e reach the in-process mock routers over loopback http, nothing else.
    local = check_destination(
        "http://127.0.0.1:8190/api/v1/__mocks__/__admin/state", env=Environment.TEST
    )
    assert (local.address, local.netloc) == ("127.0.0.1", "127.0.0.1:8190")
    with pytest.raises(DestinationRefused):
        check_destination("https://10.0.0.5/hook", env=Environment.TEST)

    # A refused destination fails the delivery without sending anything.
    receiver = Receiver(204)
    runtime = _runtime(run_settings, keyring, clock, receiver, env=production)
    _endpoint(tenant_id, runtime, "https://10.0.0.5/hook", ["period.locked"])
    _emit(tenant_id, runtime, period_id=new_id())
    deliver(_worker(tenant_id, runtime, JobKind.WEBHOOK_DELIVERY))
    [row] = _deliveries(tenant_id)
    assert (row["status"], row["last_response_status"], row["last_error"]) == (
        "FAILED",
        None,
        guard.ADDRESS_REFUSED,
    )
    assert receiver.requests == []
