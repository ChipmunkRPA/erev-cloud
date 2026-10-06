"""The contract compute job and quarantine (dev-guide DG-CMD-09, §5.12; 05 RCP-18 to RCP-20, §3.9,
§5.6; 04 T-CON-07, T-IMP-05; 03 REQ-CLS-013; BUILD_SPEC CTR-5).

World: ``support.factories.seat_world`` (AVM-US, AVM-SEAT-MO in US-LIST 2026-H1, and an unpriced
product for the quarantine). Contracts are booked as DRAFT through ``book_contract``; Maya records
``BILLING_RECORDED`` through ``POST /contracts/{id}/events``. Tests act as the worker (Procrastinate
row ``doing``, then ``run_job``).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls import release
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_computation,
    exception_item,
    job,
)
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, text
from support.db import TestDatabase
from support.factories import SeatWorld, booked_contract, seat_body, seat_line, seat_world
from support.reference import get, post

EVENTS = "/api/v1/contracts/{contract_id}/events"
UNPRICED = "AVM-SEAT-NOSSP"
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
BILLING = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-4001",
        "line_external_id": "INV-US-4001-1",
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
    return seat_world(app, keyring, clock, files, unpriced=(UNPRICED,))


@pytest.fixture
def runtime(keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


def _work(world: SeatWorld, job_id: UUID, runtime: JobRuntime) -> None:
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, world.place.tenant_id, attempt=1, runtime=runtime)


def test_large_group_defers_compute_job(world: SeatWorld, runtime: JobRuntime) -> None:
    lines = [
        seat_line(f"O{index:03d}", seats="1", price="2400.00", start="2026-09-01", end="2027-08-31")
        for index in range(1, 202)
    ]
    body = seat_body(
        world.customers["C-09"], external_id="SF-ORD-10500", inception="2026-09-01", lines=lines
    )
    booked = booked_contract(world.place, body, activate=False)
    assert len(booked.obligations) == 201
    contract_id = booked.contract["id"]
    group_id = booked.combination_group["id"]
    response = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": [BILLING]},
        if_match='"s1"',
    )
    assert response.status_code == 202, response.text
    queued = response.json()
    assert (queued["kind"], queued["state"]) == ("CONTRACT_COMPUTE", "QUEUED")
    assert response.headers["Location"] == f"/api/v1/jobs/{queued['id']}"
    job_id = UUID(queued["id"])
    (row,) = world.place.rows(select(job.c.queue, job.c.params).where(job.c.id == job_id))
    assert row["queue"] == "compute"
    # 05 REL-05: the enqueuing process records its stamped release (here the one the world
    # factory stamped, support.factories); a worker of another release re-defers the job
    # (test_release_stamping). The handler receives the caller's params only.
    stamped = release.current_release()
    assert stamped is not None
    assert row["params"] == {
        "combination_group_ids": [str(group_id)],
        "trigger": "COMMAND",
        "contract_id": str(contract_id),
        "engine_release_id": str(stamped.id),
    }
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    assert head == 2
    dirty = world.place.scalar(
        select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    )
    assert dirty is not None
    assert world.place.rows(select(contract_computation.c.id)) == []

    _work(world, job_id, runtime)
    finished = get(world.app, f"/api/v1/jobs/{job_id}", world.place.author).json()
    assert finished["state"] == "SUCCEEDED", finished
    assert finished["result"] == {
        "href": f"/api/v1/contracts/{contract_id}",
        "counts": {"groups": 1, "succeeded": 1, "quarantined": 0, "failed": 0},
    }
    computations = world.place.rows(
        select(contract_computation.c.status, contract_computation.c.job_id)
    )
    assert [(str(item["status"]), item["job_id"]) for item in computations] == [
        ("SUCCEEDED", job_id)
    ]
    cleared = world.place.scalar(
        select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    )
    assert cleared is None


def test_quarantine_raises_exception_item(world: SeatWorld) -> None:
    line = seat_line(
        "O1",
        seats="10",
        price="24000.00",
        start="2026-09-01",
        end="2027-08-31",
        product_code=UNPRICED,
    )
    body = seat_body(
        world.customers["C-09"], external_id="SF-ORD-10600", inception="2026-09-01", lines=[line]
    )
    booked = booked_contract(world.place, body, activate=False)
    contract_id = booked.contract["id"]
    group_id = booked.combination_group["id"]
    response = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {"events": [BILLING]},
        if_match='"s1"',
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["computation"]["status"] == "QUARANTINED"
    assert result["computation"]["contract_version_ids"] == {}
    (computed,) = world.place.rows(
        select(
            contract_computation.c.id, contract_computation.c.status, contract_computation.c.problem
        )
    )
    assert (str(computed["status"]), str(computed["id"])) == (
        "QUARANTINED",
        result["computation"]["id"],
    )
    assert computed["problem"]["code"] == "SSP_KEY_NOT_FOUND"
    items = world.place.rows(
        select(
            exception_item.c.source,
            exception_item.c.code,
            exception_item.c.severity,
            exception_item.c.status,
            exception_item.c.dedupe_key,
            exception_item.c.contract_id,
            exception_item.c.combination_group_id,
            exception_item.c.exception_no,
            exception_item.c.title,
        )
    )
    assert [
        (
            str(item["source"]),
            item["code"],
            str(item["severity"]),
            str(item["status"]),
            item["dedupe_key"],
            item["contract_id"],
            item["combination_group_id"],
        )
        for item in items
    ] == [
        (
            "ENGINE",
            "SSP_KEY_NOT_FOUND",
            "BLOCKING",
            "OPEN",
            f"ENGINE:SSP_KEY_NOT_FOUND:{group_id}",
            contract_id,
            group_id,
        )
    ]
    assert items[0]["exception_no"].startswith("EXC-")
    assert items[0]["title"] == "SSP key not found"
    dirty = world.place.scalar(
        select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    )
    assert dirty is not None
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    assert head == 2

    # The same finding again counts on the open item instead of raising another.
    again = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        world.place.author,
        {
            "events": [
                {
                    **BILLING,
                    "payload": {
                        **BILLING["payload"],
                        "invoice_number": "INV-US-4002",
                        "line_external_id": "INV-US-4002-1",
                    },
                }
            ]
        },  # type: ignore[dict-item]
        if_match='"s2"',
    )
    assert again.status_code == 201, again.text
    counts = world.place.rows(select(exception_item.c.occurrence_count))
    assert [row["occurrence_count"] for row in counts] == [2]
