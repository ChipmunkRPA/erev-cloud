"""A database that could not do it now is not a computation result (item RES-53-COMPUTE-1 with
supervisor ruling R-53 (5); 05 RCP-20 rev 1.53; 04 API-C-05 rev 1.114; dev-guide DG-CMD-09 and
DG-KRN-ERR-03 rev 1.97).

Before, ``compute_group``'s catch-all stored a FAILED computation with a BLOCKING exception item
for any exception, so a full lock table (SQLSTATE 53200, measured in the deployment lane) became
a permanent-looking finding that held the period's ``EXCEPTIONS_CLEARED`` gate, and the API
answered 201 — or, outside a computation, 500.

The fault is injected at the session level: the first bundle read of the computation makes the
server itself raise the SQLSTATE through the computation's own session, inside its savepoint, so
the driver error, SQLAlchemy's wrapping and the transaction state are the real ones. World:
``support.factories.seat_world``, as ``test_compute_job``.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_computation,
    contract_event,
    exception_item,
    job,
)
from erev_api.domain.contracts import bundles
from erev_api.enums import JobKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import RetryPolicy, run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import SeatWorld, booked_contract, seat_body, seat_line, seat_world
from support.http import call
from support.principals import cookie_headers
from support.reference import get, post

EVENTS = "/api/v1/contracts/{contract_id}/events"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
# The server raises the code itself, as it does when the lock table is full.
_OUT_OF_SHARED_MEMORY = text(
    "DO $fault$ BEGIN RAISE EXCEPTION 'out of shared memory' USING ERRCODE = '53200', "
    "HINT = 'You might need to increase max_locks_per_transaction.'; END $fault$"
)
BILLING = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-5301",
        "line_external_id": "INV-US-5301-1",
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


@pytest.fixture
def runtime(keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


@pytest.fixture
def fault(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable[[Session], None]], list[int]]:
    """Arm one failure of the next bundle read; the list counts the bundle reads since."""

    def arm(fail: Callable[[Session], None]) -> list[int]:
        calls: list[int] = []
        real = bundles.build

        def build(session: Session, *args: Any, **kwargs: Any) -> Any:
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                fail(session)
            return real(session, *args, **kwargs)

        monkeypatch.setattr(bundles, "build", build)
        return calls

    return arm


def _lock_table_full(session: Session) -> None:
    session.execute(_OUT_OF_SHARED_MEMORY)


def _defect(session: Session) -> None:
    raise RuntimeError("a programming error inside the computation")


def _booked(world: SeatWorld, external_id: str, lines: int = 1) -> tuple[UUID, UUID]:
    body = seat_body(
        world.customers["C-09"],
        external_id=external_id,
        inception="2026-09-01",
        lines=[
            seat_line(
                f"O{index:03d}", seats="1", price="2400.00", start="2026-09-01", end="2027-08-31"
            )
            for index in range(1, lines + 1)
        ],
    )
    booked = booked_contract(world.place, body, activate=False)
    return UUID(str(booked.contract["id"])), UUID(str(booked.combination_group["id"]))


def _computations(world: SeatWorld) -> list[str]:
    rows = world.place.rows(
        select(contract_computation.c.status).order_by(contract_computation.c.created_at)
    )
    return [str(row["status"]) for row in rows]


def _events(world: SeatWorld, contract_id: UUID) -> list[str]:
    rows = world.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == contract_id)
        .order_by(contract_event.c.stream_version)
    )
    return [str(row["event_type"]) for row in rows]


def _head(world: SeatWorld, contract_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )


def _log(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.startswith("{")]


def test_a_full_lock_table_inside_a_command_answers_503_and_stores_nothing(
    world: SeatWorld,
    fault: Callable[[Callable[[Session], None]], list[int]],
    log_stream: io.StringIO,
) -> None:
    """The request answers 503 with ``Retry-After``; no computation, no exception item and no event
    is stored; the same request under the same ``Idempotency-Key`` then runs and succeeds."""
    contract_id, group_id = _booked(world, "SF-ORD-53200")
    events_before, head_before = _events(world, contract_id), _head(world, contract_id)
    headers = cookie_headers(world.place.author.token, world.place.author.csrf_token, key=True)
    headers["If-Match"] = f'"s{head_before}"'
    path = EVENTS.format(contract_id=contract_id)

    reads = fault(_lock_table_full)
    refused = call(world.app, "POST", path, json={"events": [BILLING]}, headers=headers)
    assert refused.status_code == 503, refused.text
    assert refused.headers["retry-after"] == "5"
    assert (refused.json()["type"], refused.json()["title"]) == (
        "about:blank",
        "Service Unavailable",
    )
    assert reads == [1], "the computation was reached once and its first read failed"
    # FAILED computation count stays 0 - nothing at all was stored, the events included.
    assert _computations(world) == []
    assert world.place.rows(select(exception_item.c.id)) == []
    assert _events(world, contract_id) == events_before
    assert _head(world, contract_id) == head_before
    logged = _log(log_stream)
    assert [line["sqlstate"] for line in logged if line["event"] == "http.server_unavailable"] == [
        "53200"
    ]
    assert not [line for line in logged if line["event"] == "contract.computation_failed"]
    assert not [line for line in logged if line["event"] == "http.unhandled_error"]

    # The attempt was abandoned, not stored: the same key runs the command again.
    again = call(world.app, "POST", path, json={"events": [BILLING]}, headers=headers)
    assert again.status_code == 201, again.text
    assert "idempotent-replay" not in again.headers
    assert again.json()["computation"]["status"] == "SUCCEEDED"
    assert _computations(world) == ["SUCCEEDED"]
    assert _events(world, contract_id) == [*events_before, "BILLING_RECORDED"]
    assert world.place.rows(select(exception_item.c.id)) == []
    assert (
        world.place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is None
    )


def _deferred(world: SeatWorld, external_id: str) -> tuple[UUID, UUID, UUID]:
    """A group large enough for the command to defer ``CONTRACT_COMPUTE``: contract, group, job."""
    contract_id, group_id = _booked(world, external_id, lines=201)
    response = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": [BILLING]},
        if_match='"s1"',
    )
    assert response.status_code == 202, response.text
    return contract_id, group_id, UUID(response.json()["id"])


def _work(world: SeatWorld, job_id: UUID, runtime: JobRuntime, *, attempt: int) -> int:
    """Act as the worker for the job's current task; returns that task's id."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = int(
            session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
        )
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, world.place.tenant_id, attempt=attempt, runtime=runtime)
    return task_id


def _dirty(world: SeatWorld, group_id: UUID) -> bool:
    since = world.place.scalar(
        select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    )
    return since is not None


def test_a_full_lock_table_inside_the_compute_job_fails_the_attempt_and_stores_nothing(
    world: SeatWorld,
    runtime: JobRuntime,
    fault: Callable[[Callable[[Session], None]], list[int]],
    log_stream: io.StringIO,
) -> None:
    """A deferred ``CONTRACT_COMPUTE`` under the policy the kind is REGISTERED with: the attempt
    that meets the fault stores no computation and no exception item of the computation, and is
    settled by the job's retry policy — re-queued while attempts remain, FAILED otherwise. The
    group stays dirty, so the facts the command committed are computed by the next computation of
    the group. A job that ends FAILED is told to the readers of the contract's entity by the INFO
    item of the job (05 JOB-07 rev 1.165; item JOB-FAILED-ITEM-1) — the one item in the queue; an
    attempt that is retried leaves none."""
    contract_id, group_id, job_id = _deferred(world, "SF-ORD-53201")
    policy = registry.HANDLERS[JobKind.CONTRACT_COMPUTE].retry
    reads = fault(_lock_table_full)
    _work(world, job_id, runtime, attempt=1)
    assert reads == [1]
    assert _computations(world) == [], "no FAILED computation: the fault was the server's"
    assert _dirty(world, group_id) and _head(world, contract_id) == 2
    settled = get(world.app, f"/api/v1/jobs/{job_id}", world.place.author).json()
    settling = ("job.retry_scheduled", "job.failed")
    events = [line for line in _log(log_stream) if line["event"] in settling]
    outcome = [(line["event"], line["attempt"], line["error_class"]) for line in events]
    items = [
        (
            str(row["code"]),
            str(row["severity"]),
            str(row["source"]),
            row["contract_id"],
            row["combination_group_id"],
            str(row["status"]),
        )
        for row in world.place.rows(
            select(
                exception_item.c.code,
                exception_item.c.severity,
                exception_item.c.source,
                exception_item.c.contract_id,
                exception_item.c.combination_group_id,
                exception_item.c.status,
            )
        )
    ]
    if policy.max_attempts > 1:
        assert settled["state"] == "QUEUED", settled
        assert outcome == [("job.retry_scheduled", 1, "OperationalError")]
        assert items == []
    else:
        assert settled["state"] == "FAILED", settled
        assert outcome == [("job.failed", 1, "OperationalError")]
        assert items == [("JOB_FAILED", "INFO", "ENGINE", contract_id, None, "OPEN")]
    assert not [line for line in _log(log_stream) if line["event"] == "contract.computation_failed"]


def test_with_the_profile_of_the_architecture_the_attempt_is_retried_and_succeeds(
    world: SeatWorld,
    runtime: JobRuntime,
    fault: Callable[[Callable[[Session], None]], list[int]],
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """05 §5.6 gives ``CONTRACT_COMPUTE`` three attempts with an exponential wait of 5 s. Under that
    profile — set here on the registered handler, whatever the code registers — the attempt that
    meets the fault is re-queued under a new task and the next attempt computes the group."""
    contract_id, group_id, job_id = _deferred(world, "SF-ORD-53203")
    spec = registry.HANDLERS[JobKind.CONTRACT_COMPUTE]
    profile = RetryPolicy(max_attempts=3, backoff_seconds=(5, 10))
    monkeypatch.setitem(registry.HANDLERS, JobKind.CONTRACT_COMPUTE, replace(spec, retry=profile))

    fault(_lock_table_full)
    first_task = _work(world, job_id, runtime, attempt=1)
    queued = get(world.app, f"/api/v1/jobs/{job_id}", world.place.author).json()
    assert queued["state"] == "QUEUED", queued
    assert _computations(world) == [] and _dirty(world, group_id)
    retried = [line for line in _log(log_stream) if line["event"] == "job.retry_scheduled"]
    assert [(line["job_id"], line["attempt"], line["error_class"]) for line in retried] == [
        (str(job_id), 1, "OperationalError")
    ]

    second_task = _work(world, job_id, runtime, attempt=2)
    assert second_task != first_task, "the retry is a new task"
    finished = get(world.app, f"/api/v1/jobs/{job_id}", world.place.author).json()
    assert finished["state"] == "SUCCEEDED", finished
    assert finished["result"]["counts"] == {
        "groups": 1,
        "succeeded": 1,
        "quarantined": 0,
        "failed": 0,
    }
    assert _computations(world) == ["SUCCEEDED"]
    assert not _dirty(world, group_id) and _head(world, contract_id) == 2


def test_any_other_exception_is_still_recorded_as_a_failed_computation(
    world: SeatWorld,
    fault: Callable[[Callable[[Session], None]], list[int]],
    log_stream: io.StringIO,
) -> None:
    """The boundary: a defect inside the computation keeps the documented behaviour of DG-CMD-09 —
    201, a FAILED computation, a BLOCKING exception item, the events saved, the group dirty."""
    contract_id, group_id = _booked(world, "SF-ORD-53202")
    fault(_defect)
    response = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": [BILLING]},
        if_match='"s1"',
    )
    assert response.status_code == 201, response.text
    assert response.json()["computation"]["status"] == "FAILED"
    assert _computations(world) == ["FAILED"]
    items = world.place.rows(
        select(exception_item.c.source, exception_item.c.code, exception_item.c.severity)
    )
    assert [(str(i["source"]), i["code"], str(i["severity"])) for i in items] == [
        ("ENGINE", "ENGINE_INVARIANT_VIOLATION", "BLOCKING")
    ]
    assert _events(world, contract_id)[-1] == "BILLING_RECORDED"
    assert (
        world.place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is not None
    )
    assert [
        line["event"] for line in _log(log_stream) if line["event"].startswith("contract.")
    ] == ["contract.computation_failed"]
