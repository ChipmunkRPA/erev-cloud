"""The integration test world of PRD J-23 (WLD-T-22 preconditions; BUILD_SPEC DIN-13, DIN-14): a
tenant with entity ``QUAY-US`` (USD, America/Chicago) whose FY2026 periods are open, the WLD-F-36
products, and Nikhil, an MFA-enrolled Integration Admin and Revenue Accountant. Connections reach
the in-process mock routers (05 ADP-20) through ``support.http.asgi_client``, registered as the
adapters' HTTP client factory (DG-LAY-03); the ``SYNC_RUN`` and ``OUTBOX_RELAY`` jobs run
in-process under the world's runtime, the way a worker would fetch and run them.

Everything is built through the product's own routes and commands. The inbound adapters are
registered with a backoff that moves the world's frozen clock instead of sleeping (ADP-12), and the
composition root's registrations are put back when the world ends.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final
from uuid import UUID

from erev_api.adapters import mocks
from erev_api.adapters.billing import stripe
from erev_api.adapters.crm import salesforce
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, sync_run
from erev_api.domain.integrations import ports
from erev_api.domain.integrations import sync as sync_module
from erev_api.enums import JobKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from fastapi import FastAPI
from sqlalchemy import select, text
from support.factories import stamp_test_release, world_calendar
from support.http import asgi_client
from support.principals import Actor, enrolled, member
from support.reference import assign, new_product, patch, post

__all__ = [
    "ADMIN",
    "ENTITY",
    "INTEGRATIONS",
    "PRODUCTS",
    "IntegrationWorld",
    "connection",
    "integration_world",
    "queue_fault",
    "relay_outbox",
    "run",
    "sync",
]

INTEGRATIONS: Final = "/api/v1/integrations"
ADMIN: Final = f"{mocks.MOCKS_PREFIX}/__admin"
ENTITY: Final = "QUAY-US"
PRODUCTS: Final = ("QUAY-PLAT", "QUAY-ADDON", "QUAY-SVC")  # WLD-F-36; SF-PROD-X99 is unmapped
ROLES: Final = ("revenue_accountant", "integration_admin")
_TASK_FETCHED: Final = "UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"


@dataclass(frozen=True, slots=True)
class IntegrationWorld:
    app: FastAPI
    nikhil: Actor
    tenant_id: UUID
    entity_id: UUID
    runtime: JobRuntime
    clock: FrozenClock

    @property
    def context(self) -> DbContext:
        return DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")

    def rows(self, statement: Any) -> list[dict[str, Any]]:
        with tenant_session(self.context, read_only=True) as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    def execute(self, statement: Any) -> None:
        with tenant_session(self.context) as session:
            session.execute(statement)


@contextmanager
def integration_world(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    settings: Settings,
    *,
    roles: tuple[str, ...] = ROLES,
    products: tuple[str, ...] = PRODUCTS,
) -> Iterator[IntegrationWorld]:
    """The J-23 world over ``app`` (a ``committed_db`` app); the registrations are restored on
    exit."""
    someone = member(keyring, clock)
    for role in roles:
        assign(someone, role)
    nikhil = enrolled(app, clock, someone)
    _, entity_id = world_calendar(
        app, nikhil, entity_code=ENTITY, functional_currency="USD", time_zone="America/Chicago"
    )
    for code in products:
        new_product(app, nikhil, code=code, name=code.replace("-", " ").title())

    def backoff(seconds: float) -> None:
        # ADP-12: a retry moves the frozen clock by its backoff; no test waits (DG-KRN-TIME-06).
        clock.advance(timedelta(seconds=seconds))

    ports.register_inbound_adapter(
        "SALESFORCE", lambda context: salesforce.SalesforceAdapter(context, sleep=backoff)
    )
    ports.register_inbound_adapter(
        "STRIPE", lambda context: stripe.StripeAdapter(context, sleep=backoff)
    )
    previous = sync_module._HOOKS.get("http")
    sync_module.register_http_client_factory(lambda base_url: asgi_client(app))
    with asgi_client(app) as client:
        assert client.post(f"{ADMIN}/reset").status_code == 204  # the seeded WLD-F-31 state
    stamp_test_release()
    try:
        yield IntegrationWorld(
            app=app,
            nikhil=nikhil,
            tenant_id=someone.tenant_id,
            entity_id=entity_id,
            runtime=JobRuntime(
                clock=clock, keyring=keyring, files=LocalFileStore(settings.file_root)
            ),
            clock=clock,
        )
    finally:
        sync_module.register_http_client_factory(previous)
        salesforce.register()  # the composition root's factories (real sleep) for later modules
        stripe.register()


def connection(world: IntegrationWorld, **body: Any) -> dict[str, Any]:
    """``POST /integrations`` then ``PATCH … {status: ACTIVE}``; the ACTIVE connection. A mock
    connection carries no ``secret_ref`` unless the test gives one (05 KEY-09)."""
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


def queue_fault(world: IntegrationWorld, route: str, kind: str, count: int = 1) -> None:
    """05 ADP-21: the next ``count`` requests matching ``route`` answer the fault."""
    with asgi_client(world.app) as client:
        response = client.post(
            f"{ADMIN}/faults", json={"route": route, "kind": kind, "count": count}
        )
        assert response.status_code == 201, response.text


def run(world: IntegrationWorld, job_id: UUID) -> dict[str, Any]:
    """The worker fetches the job's task and runs it; the finished job row."""
    with tenant_session(world.context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(text(_TASK_FETCHED), {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=1, runtime=world.runtime)
    [row] = world.rows(select(job).where(job.c.id == job_id))
    return row


def sync(
    world: IntegrationWorld, target: dict[str, Any], kind: str = "INBOUND_POLL"
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``POST /integrations/{id}/sync`` then the job; the sync run row and the job row."""
    accepted = post(world.app, f"{INTEGRATIONS}/{target['id']}/sync", world.nikhil, {"kind": kind})
    assert accepted.status_code == 202, accepted.text
    finished = run(world, UUID(accepted.json()["id"]))
    [row] = world.rows(
        select(sync_run).where(sync_run.c.id == UUID(accepted.headers["X-Erev-Sync-Run-Id"]))
    )
    return row, finished


def relay_outbox(world: IntegrationWorld) -> list[dict[str, Any]]:
    """Run every QUEUED ``OUTBOX_RELAY`` job of the tenant (the jobs an ``outbox.enqueue`` defers)
    and answer the finished job rows."""
    queued = world.rows(
        select(job.c.id)
        .where(job.c.kind == JobKind.OUTBOX_RELAY.value, job.c.state == "QUEUED")
        .order_by(job.c.created_at, job.c.id)
    )
    return [run(world, UUID(str(row["id"]))) for row in queued]
