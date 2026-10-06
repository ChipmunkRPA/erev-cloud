"""API-R-39 close runs at the API (BUILD_SPEC CLO-19 acceptance; 04 §15.3 API-R-39, §16.8
API-S-CloseRunCreate, API-S-CloseRun and the close run commands; SCREENS_B §1.2; 03 REQ-PLT-012;
supervisor ruling R-79 (h)).

World: ``support.factories.seat_world`` — AVM-US with FY2026-P01 to P09 open; Maya (Revenue
Accountant) and Marcus (Controller) hold ``period.close``; Priya (SSP Approver) reads contracts and
closes nothing.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import close_run, job, legal_entity
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import close_runs as runs
from support.db import TestDatabase
from support.factories import SeatWorld, seat_world
from support.principals import colleague
from support.reference import entity, fields, get, holding, post, slug

AVM_US = "AVM-US"
AUGUST = "FY2026-P08"
SEPTEMBER = "FY2026-P09"
OCTOBER = "FY2026-P10"
REASON = "Restarting after the correction."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


def _count(world: SeatWorld, table: object, *conditions: object) -> int:
    statement = select(func.count()).select_from(table).where(*conditions)  # type: ignore[arg-type]
    return int(world.place.scalar(statement))


def test_start_returns_active_run(app: FastAPI, world: SeatWorld) -> None:
    """BUILD_SPEC CLO-19: ``POST /close-runs`` for an (entity, book, period) with an active run
    returns that run instead of a second one; a new run returns 202 with a ``CLOSE_RUN`` job."""
    maya = world.place.author
    first = runs.start(app, maya, entity_code=AVM_US, period_key=SEPTEMBER)
    assert first.status_code == 202, first.text
    queued = first.json()
    assert (queued["kind"], queued["state"]) == ("CLOSE_RUN", "QUEUED")
    assert first.headers["Location"] == f"/api/v1/jobs/{queued['id']}"
    run_id = first.headers[runs.ID_HEADER]

    # The run is active (PENDING): starting again answers it, for its starter and for a colleague.
    for actor in (maya, world.marcus):
        again = runs.start(app, actor, entity_code=AVM_US, period_key=SEPTEMBER)
        assert again.status_code == 200, again.text
        assert "Location" not in again.headers and again.headers[runs.ID_HEADER] == run_id
        active = again.json()
        assert (active["id"], active["status"], active["job"]["id"]) == (
            run_id,
            "PENDING",
            queued["id"],
        )
        assert active["created_by"]["id"] == str(maya.member.user_id)
    assert _count(world, close_run) == 1
    assert _count(world, job, job.c.kind == "CLOSE_RUN") == 1

    # Another period of the entity has its own run.
    other = runs.start(app, maya, entity_code=AVM_US, period_key=AUGUST)
    assert other.status_code == 202, other.text
    august = other.headers[runs.ID_HEADER]
    assert august != run_id

    shown = get(app, f"{runs.CLOSE_RUNS}/{run_id}", maya)
    assert shown.status_code == 200, shown.text
    assert shown.headers["ETag"] == f'"r{shown.json()["row_version"]}"'
    # The list of SCREENS_B §1.2: by entity, book and period; and by status.
    assert [item["id"] for item in runs.listed(app, maya, entity=AVM_US, period=SEPTEMBER)] == [
        run_id
    ]
    assert [item["id"] for item in runs.listed(app, maya, entity=AVM_US, book="ASC606")] == [
        run_id,
        august,
    ]
    assert [item["id"] for item in runs.listed(app, maya, status="PENDING")] == [run_id, august]
    assert runs.listed(app, maya, status="SUCCEEDED") == []
    assert runs.listed(app, maya, entity=AVM_US, book="IFRS15") == []
    newest = get(app, runs.CLOSE_RUNS, maya, {"entity": AVM_US})
    assert [item["id"] for item in newest.json()["items"]] == [august, run_id]  # newest first

    # Once the run has ended, a start is a new run.
    cancelled = runs.cancel(app, maya, run_id, REASON)
    assert (cancelled.status_code, cancelled.json()["status"]) == (200, "CANCELLED"), cancelled.text
    assert cancelled.headers["ETag"] == f'"r{cancelled.json()["row_version"]}"'
    third = runs.start(app, maya, entity_code=AVM_US, period_key=SEPTEMBER)
    assert third.status_code == 202, third.text
    assert third.headers[runs.ID_HEADER] not in (run_id, august)
    assert [item["status"] for item in runs.listed(app, maya, entity=AVM_US, period=SEPTEMBER)] == [
        "CANCELLED",
        "PENDING",
    ]


def test_close_run_commands_are_guarded(app: FastAPI, world: SeatWorld) -> None:
    """04 §16.8: the commands need ``period.close`` for the run's entity; a period that is not
    open, in soft close or reopened takes no run; reads answer the caller's entities only."""
    maya = world.place.author

    def refused(response: object, status: int, problem: str) -> dict[str, object]:
        assert (response.status_code, slug(response)) == (status, problem), response.text  # type: ignore[attr-defined]
        return dict(response.json())  # type: ignore[attr-defined]

    # What is asked for must exist and be open.
    unknown = runs.start(app, maya, entity_code="AVM-XX", period_key=SEPTEMBER)
    refused(unknown, 422, "validation-failed")
    assert fields(unknown) == [("entity_code", "T-CLS-01")]
    no_period = runs.start(app, maya, entity_code=AVM_US, period_key="FY2040-P01")
    refused(no_period, 422, "validation-failed")
    assert fields(no_period) == [("period_key", "T-CLS-01")]
    no_book = runs.start(app, maya, entity_code=AVM_US, period_key=SEPTEMBER, book="IFRS15")
    refused(no_book, 422, "validation-failed")
    assert fields(no_book) == [("book", "T-CLS-01")]
    future = refused(
        runs.start(app, maya, entity_code=AVM_US, period_key=OCTOBER), 409, "invalid-transition"
    )
    assert future["detail"] == (
        "FY2026-P10 of AVM-US in book ASC606 is future. A close run needs an open period, a "
        "period in soft close or a reopened one."
    )
    assert _count(world, close_run) == 0

    run_id, _ = runs.started(app, maya, entity_code=AVM_US, period_key=SEPTEMBER)
    # Priya reads contracts and closes nothing: she sees the run and may not act on it.
    assert get(app, f"{runs.CLOSE_RUNS}/{run_id}", world.priya).status_code == 200
    for response in (
        runs.start(app, world.priya, entity_code=AVM_US, period_key=AUGUST),
        runs.resume(app, world.priya, run_id),
        runs.cancel(app, world.priya, run_id, REASON),
    ):
        refused(response, 403, "forbidden")

    # A Revenue Accountant of another entity: the run is not found, for reads and commands alike
    # (REQ-PLT-012), and AVM-US is not hers to close.
    calendar_id = world.place.scalar(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
    )
    other = entity(app, maya, code="AVM-UK", calendar_id=str(calendar_id))
    elsewhere = colleague(world.place.tenant_id, "erin")
    erin = holding(app, elsewhere, "revenue_accountant", entity_ids=[UUID(str(other["id"]))])
    refused(get(app, f"{runs.CLOSE_RUNS}/{run_id}", erin), 404, "not-found")
    assert runs.listed(app, erin) == []
    for response in (runs.resume(app, erin, run_id), runs.cancel(app, erin, run_id, REASON)):
        refused(response, 404, "not-found")
    # AVM-US is outside her entities: a start for it answers as for a code that does not exist.
    hidden = runs.start(app, erin, entity_code=AVM_US, period_key=SEPTEMBER)
    refused(hidden, 422, "validation-failed")
    assert hidden.json()["errors"] == unknown.json()["errors"]
    # An id that names no run.
    missing = str(new_id())
    refused(get(app, f"{runs.CLOSE_RUNS}/{missing}", maya), 404, "not-found")
    refused(runs.resume(app, maya, missing), 404, "not-found")
    refused(runs.cancel(app, maya, missing, REASON), 404, "not-found")

    # A pending run is not resumed; a cancellation takes a reason of at least ten characters.
    refused(runs.resume(app, maya, run_id), 409, "invalid-transition")
    short = runs.cancel(app, maya, run_id, "Too short")
    refused(short, 422, "validation-failed")
    no_reason = post(app, f"{runs.CLOSE_RUNS}/{run_id}/cancel", maya, {})
    refused(no_reason, 422, "validation-failed")
    still = get(app, f"{runs.CLOSE_RUNS}/{run_id}", maya).json()
    assert (still["status"], UUID(still["id"])) == ("PENDING", UUID(run_id))
