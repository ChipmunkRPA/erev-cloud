"""An import that failed before its commit holds no lock (04 T-IMP-05 "An item that names no
entity: whose close it holds" and §16.14, rev 1.270; 05 §5.6 rev 1.185; the supervisor's ruling of
2026-10-02 on lane OPS's reading of the gates).

The failure hooks of the validation and the dry run end an upload ``INVALID`` with one
``IMPORT_PROCESSING_FAILED`` item — ``BLOCKING``, as table 15.4-A gives the code, because it is
the import's own ``ERROR`` finding. That item names no period and no entity, so the close gates
took it as every other import finding: for every period of the entities the upload names, and of
EVERY entity while the upload names none or is not resolved — which is what an upload still
``VALIDATING`` is. A dry run or a validation that failed wrote nothing and owes nothing to any
period: ``close.gates._open_exceptions`` leaves the item out, and with it the count
``blockers.exceptions_open``, the gate ``EXCEPTIONS_CLEARED`` and the list under ``blocking``,
which are one predicate. The queue keeps the item for the upload's readers.

Counted as before: the item of a failed commit (the upload is ``FAILED``) and the finding of a
plan a dry run refused, whose upload goes on.

World: ``support.close_world`` with a second entity on the same calendar; September of both in
soft close. The uploads and their jobs are rows, as a dead worker leaves them, and the sweeper
settles them (``test_commit_job_failed``, ``test_diff_job_failed``, ``test_validate_job_failed``).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import exception_item, file_object, import_upload, legal_entity
from erev_api.domain.close import gates
from erev_api.enums import FilePurpose
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.close_world import BOOK, CloseWorld, close_world, system_session
from support.db import TestDatabase
from support.factories import open_periods
from support.reference import entity, get, periods, post
from support.rows import exception_item_values, file_object_values, import_upload_values
from test_commit_job_failed import _committing, _state, _sweep
from test_diff_job_failed import _diffing
from test_validate_job_failed import _validating

PERIODS = "/api/v1/periods"
EXCEPTIONS = "/api/v1/exceptions"
SEPTEMBER = "FY2026-P09"
FAILED_CODE = "IMPORT_PROCESSING_FAILED"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _second_entity(world: CloseWorld) -> UUID:
    """AVM-UK on AVM-US's calendar, its nine periods open as AVM-US's are."""
    with system_session(world) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        ).scalar_one()
    uk = entity(world.app, world.maya, code="AVM-UK", calendar_id=str(calendar_id))
    open_periods(
        world.app,
        world.maya,
        entity_code="AVM-UK",
        keys=[f"FY2026-P{month:02d}" for month in range(1, 10)],
    )
    return UUID(str(uk["id"]))


def _soft_closed(world: CloseWorld, entity_code: str) -> str:
    """September of the entity in soft close (E-04 ``closing``); its API-S-Period id."""
    (state,) = [
        item
        for item in periods(world.app, world.maya, entity=entity_code)
        if item["period"]["period_key"] == SEPTEMBER
    ]
    started = post(
        world.app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "closing", started.text
    return str(state["id"])


def _held(
    world: CloseWorld, entity_id: UUID, state_id: str
) -> tuple[str, int | None, int, set[str]]:
    """What the lock of the entity's September reads of the exception items: the gate
    ``EXCEPTIONS_CLEARED`` (status, count), ``blockers.exceptions_open``, and the ids the list
    under ``blocking`` names."""
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, entity_id, BOOK, world.period_id)
        uow.commit()
    (gate,) = [result for result in results if result.gate_check_code == "EXCEPTIONS_CLEARED"]
    shown = get(world.app, f"{PERIODS}/{state_id}", world.maya)
    assert shown.status_code == 200, shown.text
    listed = get(
        world.app, EXCEPTIONS, world.maya, {"blocking": state_id, "limit": 200, "count": "true"}
    )
    assert listed.status_code == 200, listed.text
    return (
        gate.status.value,
        gate.count,
        int(shown.json()["blockers"]["exceptions_open"]),
        {str(item["id"]) for item in listed.json()["items"]},
    )


def _item_ids(world: CloseWorld, upload_id: UUID) -> list[str]:
    with system_session(world) as session:
        return [
            str(value)
            for value in session.execute(
                select(exception_item.c.id).where(exception_item.c.import_upload_id == upload_id)
            ).scalars()
        ]


def _upload_with_item(
    world: CloseWorld, status: str, named: list[UUID], code: str = FAILED_CODE
) -> tuple[UUID, str]:
    """An upload in ``status`` that names ``named``, with one open ``BLOCKING`` item of ``code``
    as the handler itself stores a file-level finding; (upload id, item id)."""
    with system_session(world) as session:
        stored = file_object_values(world.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
        session.execute(insert(file_object).values(**stored))
        upload = import_upload_values(
            world.tenant_id, file_object_id=stored["id"], status=status, named_entity_ids=named
        )
        session.execute(insert(import_upload).values(**upload))
        row = exception_item_values(
            world.tenant_id,
            source="IMPORT",
            code=code,
            title="Import finding",
            import_upload_id=upload["id"],
        )
        session.execute(insert(exception_item).values(**row))
    return UUID(str(upload["id"])), str(row["id"])


def test_an_import_that_failed_before_its_commit_holds_no_lock(
    world: CloseWorld, app_settings: Settings, keyring: KeyRing
) -> None:
    """September of AVM-US and of AVM-UK is in soft close and nothing holds either lock. Then:

    1. Three jobs fail and their hooks end the uploads ``INVALID`` with the finding — a
       validation (the upload is not resolved: every entity's, by the attribution), a dry run of
       an upload that names AVM-US and a dry run of one that names AVM-UK. Neither lock moves:
       ``EXCEPTIONS_CLEARED`` passes with 0, ``blockers.exceptions_open`` is 0 and the list under
       ``blocking`` is empty, for the entity an upload names and for the one it does not. Before
       the ruling each September counted two — the validation's item and its own dry run's.
    2. The handler's own stored failure is the same finding on the same kind of upload, and holds
       no lock either.
    3. The clause is the code AND the upload's state. Another finding of a rejected file — an
       ``INVALID`` upload with ``IMPORT_NO_DATA_ROWS`` — is counted as before, and so is the
       same code on an upload that goes on: a plan a dry run refused, the upload ``DIFF_READY``.
       Both for the entity the upload names, not for the other.
    4. A commit that fails (here before it began; the upload is not resolved, so it is every
       entity's) ends the upload ``FAILED``, and that item holds both locks, as before."""
    us = world.entity_id
    uk = _second_entity(world)
    us_state, uk_state = _soft_closed(world, "AVM-US"), _soft_closed(world, "AVM-UK")
    nothing = ("PASSED", 0, 0, set())
    assert _held(world, us, us_state) == nothing and _held(world, uk, uk_state) == nothing

    # 1. the three failed jobs
    maya = world.maya.member
    unresolved, validation_job = _validating(maya, "VALIDATING", attempt=2)
    of_us, us_job = _diffing(maya, "DIFFING", named=[us])
    of_uk, uk_job = _diffing(maya, "VALIDATED", named=[uk])
    _sweep(app_settings, keyring)
    failed: list[str] = []
    for upload_id, job_id in ((unresolved, validation_job), (of_us, us_job), (of_uk, uk_job)):
        status, state, items = _state(world.tenant_id, upload_id, job_id)
        assert (status, state) == ("INVALID", "FAILED")
        assert [(item["code"], item["severity"]) for item in items] == [(FAILED_CODE, "BLOCKING")]
        failed += _item_ids(world, upload_id)
    assert len(failed) == 3
    assert _held(world, us, us_state) == nothing and _held(world, uk, uk_state) == nothing
    # ... and the queue still holds the three, open, for whoever reads the imports
    queue = get(world.app, EXCEPTIONS, world.maya, {"code": FAILED_CODE, "limit": 200})
    assert queue.status_code == 200, queue.text
    assert {str(item["id"]) for item in queue.json()["items"]} == set(failed)
    assert {item["status"] for item in queue.json()["items"]} == {"OPEN"}

    # 2. the handler's own stored failure: an INVALID upload that names AVM-US
    _upload_with_item(world, "INVALID", [us])
    assert _held(world, us, us_state) == nothing and _held(world, uk, uk_state) == nothing

    # 3. the two boundaries: a rejected file's other finding, and a plan a dry run refused
    _, rejected = _upload_with_item(world, "INVALID", [us], code="IMPORT_NO_DATA_ROWS")
    assert _held(world, us, us_state) == ("FAILED", 1, 1, {rejected})
    _, refused = _upload_with_item(world, "DIFF_READY", [us])
    assert _held(world, us, us_state) == ("FAILED", 2, 2, {rejected, refused})
    assert _held(world, uk, uk_state) == nothing

    # 4. a failed commit holds, as before; this upload is not resolved, so it holds both
    approved, commit_job = _committing(maya, "APPROVED")
    _sweep(app_settings, keyring)
    status, state, _ = _state(world.tenant_id, approved, commit_job)
    assert (status, state) == ("FAILED", "FAILED")
    (not_committed,) = _item_ids(world, approved)
    assert _held(world, us, us_state) == ("FAILED", 3, 3, {rejected, refused, not_committed})
    assert _held(world, uk, uk_state) == ("FAILED", 1, 1, {not_committed})
