"""The exception item of a failed job (05 JOB-07 rev 1.165; 04 §15.4 ``JOB_FAILED`` rev 1.226,
T-IMP-05 ``dedupe_key``, §16.14; PRD IMP-137, BR-DAT-04; dev-guide DG-KRN-JOB-05 rev 1.212; 03
REQ-OPS-006 rev 1.135; CTL-040; item JOB-FAILED-ITEM-1; BUILD_SPEC PLF-22, BS1-D-13).

World: ``support.factories.k11_world`` — contract K-11 of entity AVM-DE, and Maya (Revenue
Accountant), who holds ``exception.resolve``. The tests play the worker as
``test_job_monitoring.py`` does: a job's task is fetched and its attempt started, and the sweeper
run ten minutes later ends the one-attempt job FAILED through the registry's own settlement
(``fail_stalled`` → ``fail_attempt`` → ``_fail_job``), the path a handler's exception at its last
attempt takes too. The sweeper serves every tenant of the shared database, so each test reads the
rows and the log lines of its own tenant and job (DG-TST-13).
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, contract, exception_item, job, period_state
from erev_api.db.transitions import apply
from erev_api.domain.close import gates
from erev_api.domain.contracts import compute_job
from erev_api.domain.imports import job_items
from erev_api.domain.imports.exceptions import raise_exception_item
from erev_api.enums import ExceptionSeverity, ExceptionSource, JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import FailedJob, FailedSubject, JobOutcome
from erev_api.jobs.sweeper import fail_stalled
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import K11World, booked_contract, k11_body, k11_world
from support.reference import get, post

EXCEPTIONS = "/api/v1/exceptions"
STALL = timedelta(minutes=10, seconds=1)
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
LABEL = "Contract computation"
REASON = "no heartbeat for 10 minutes"
DISMISSAL = "The contract was computed afterwards by its own command; no job will follow."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    return k11_world(app, keyring, clock, files)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _runtime(world: K11World, at: datetime) -> JobRuntime:
    return JobRuntime(clock=frozen_clock(at), keyring=world.place.keyring, files=world.place.files)


def _start(
    world: K11World,
    params: Mapping[str, Any],
    *,
    subject_type: str | None,
    subject_id: UUID | None,
    kind: JobKind = JobKind.CONTRACT_COMPUTE,
) -> UUID:
    """Maya starts a job of ``kind``; its first task is deferred."""
    tenant_id = world.place.tenant_id
    with tenant_session(_db(tenant_id)) as session:
        row = registry.insert_job(
            session,
            kind,
            params,
            tenant_id=tenant_id,
            now=FROZEN_AT,
            created_by=world.place.principal.id,
            created_by_kind=PrincipalKind.USER,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=FROZEN_AT
        )
    return UUID(str(row["id"]))


def _fetch(world: K11World, job_id: UUID) -> None:
    """A worker takes the job's task."""
    with tenant_session(_db(world.place.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})


def _fail(world: K11World, job_id: UUID) -> Mapping[str, Any]:
    """The worker starts the attempt and dies; the sweeper ends the job FAILED ten minutes on."""
    _fetch(world, job_id)
    with tenant_session(_db(world.place.tenant_id)) as session:
        apply(
            session,
            "job",
            job_id,
            to_status="RUNNING",
            set_values={
                "started_at": FROZEN_AT,
                "updated_at": FROZEN_AT,
                "updated_by": None,
                "updated_by_kind": PrincipalKind.SYSTEM.value,
            },
            expected_status="QUEUED",
        )
    fail_stalled(_runtime(world, FROZEN_AT + STALL))
    (row,) = world.place.rows(select(job).where(job.c.id == job_id))
    assert (row["state"], row["problem"]["detail"]) == ("FAILED", REASON), row
    return row


def _succeed(world: K11World, job_id: UUID, monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker runs the job with a handler that completes; the kind keeps its ``FailedItem``."""

    def completes(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        return JobOutcome(state="SUCCEEDED", result={"href": "/api/v1/contracts", "counts": {}})

    kind = JobKind(world.place.scalar(select(job.c.kind).where(job.c.id == job_id)))
    with monkeypatch.context() as patch:
        patch.setitem(registry.HANDLERS, kind, replace(registry.HANDLERS[kind], handler=completes))
        _fetch(world, job_id)
        registry.run_job(
            job_id, world.place.tenant_id, attempt=1, runtime=_runtime(world, FROZEN_AT + STALL)
        )
    assert world.place.scalar(select(job.c.state).where(job.c.id == job_id)) == "SUCCEEDED"


def _items(world: K11World) -> list[dict[str, Any]]:
    return world.place.rows(
        select(exception_item)
        .where(exception_item.c.code == "JOB_FAILED")
        .order_by(exception_item.c.exception_no)
    )


def _events(world: K11World, job_id: UUID) -> list[str]:
    """The audit actions written under the request id of the job's settlement."""
    rows = world.place.rows(
        select(audit_event.c.action)
        .where(audit_event.c.request_id == f"job-{job_id}")
        .order_by(audit_event.c.chain_seq)
    )
    return [str(row["action"]) for row in rows]


def _computing(world: K11World) -> tuple[UUID, dict[str, Any]]:
    """K-11 booked: its id and the params of a computation job for it."""
    booked = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    contract_id = UUID(str(booked.contract["id"]))
    group_id = world.place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    params = {
        "combination_group_ids": [str(group_id)],
        "trigger": "COMMAND",
        "contract_id": str(contract_id),
    }
    return contract_id, params


def _lines(log_stream: io.StringIO, event: str, job_id: UUID) -> list[dict[str, Any]]:
    records = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    return [
        record
        for record in records
        if record.get("event") == event and record.get("job_id") == str(job_id)
    ]


def test_job_failed_item_1_a_failed_job_of_an_entity_leaves_its_item(
    world: K11World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed computation of a contract leaves one open ``INFO`` item of source ``ENGINE`` for
    the contract's entity, written in the transaction that ends the job; a second failure counts
    it again; a later job of the kind and record that runs to its end resolves it as the system;
    a failure after that raises a new item. A preview and a job without a subject raise none."""
    contract_id, params = _computing(world)
    subject: dict[str, Any] = {"subject_type": "contract", "subject_id": contract_id}
    assert _items(world) == []

    first = _start(world, params, **subject)
    _fail(world, first)
    (item,) = _items(world)
    key = f"ENGINE:JOB_FAILED:CONTRACT_COMPUTE:{contract_id}"
    assert (
        job_items.item_key(ExceptionSource.ENGINE, JobKind.CONTRACT_COMPUTE, str(contract_id))
        == key
    )
    assert {
        name: item[name]
        for name in (
            "source", "code", "severity", "status", "entity_id", "period_id", "contract_id",
            "dedupe_key", "occurrence_count", "title", "message", "source_payload",
        )
    } == {
        "source": "ENGINE",
        "code": "JOB_FAILED",
        "severity": "INFO",
        "status": "OPEN",
        "entity_id": world.entity_id,
        "period_id": None,
        "contract_id": contract_id,
        "dedupe_key": key,
        "occurrence_count": 1,
        "title": f"Job failed: {LABEL}",
        "message": job_items.MESSAGE.format(
            label=LABEL, attempt=1, reason=REASON, job_id=first
        ),
        "source_payload": {
            "job_id": str(first),
            "job_kind": "CONTRACT_COMPUTE",
            "attempt": 1,
            "problem": "job-stalled",
        },
    }  # fmt: skip
    # One transaction ends the job and writes the item: both events under the settlement's id.
    assert sorted(_events(world, first)) == ["exception_item.create", "job.finish"]

    second = _start(world, params, **subject)
    _fail(world, second)
    (again,) = _items(world)
    assert (again["id"], again["occurrence_count"], again["status"]) == (item["id"], 2, "OPEN")
    assert _events(world, second) == ["job.finish"]  # counted again: AUD-OPS, no second create

    # A preview keeps nothing and tells the person who asked; a job without a subject names no
    # record. Neither raises an item nor counts the open one.
    preview = _start(world, {**params, "mode": compute_job.PREVIEW_MODE}, **subject)
    _fail(world, preview)
    unnamed = _start(world, params, subject_type=None, subject_id=None)
    _fail(world, unnamed)
    assert [(row["id"], row["occurrence_count"]) for row in _items(world)] == [(item["id"], 2)]

    third = _start(world, params, **subject)
    _succeed(world, third, monkeypatch)
    (settled,) = _items(world)
    assert (
        settled["status"],
        settled["resolved_by"],
        settled["resolved_by_kind"],
        settled["resolution"],
    ) == ("RESOLVED", None, "SYSTEM", job_items.RESOLUTION.format(job_id=third))
    assert "exception_item.resolve" in _events(world, third)

    fourth = _start(world, params, **subject)
    _fail(world, fourth)
    earlier, later = _items(world)
    assert (earlier["id"], earlier["status"]) == (item["id"], "RESOLVED")
    assert (later["status"], later["occurrence_count"], later["dedupe_key"]) == ("OPEN", 1, key)
    assert later["exception_no"] > earlier["exception_no"]


def test_job_failed_item_1_a_record_that_each_job_creates_anew_is_one_record(
    world: K11World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal run calculation creates its run under a new id, so the job's subject id names
    nothing a later job works on again: the record is the entity, the book and the period of
    the job's params. Two failed calculations under two run ids are one open item, counted
    twice, and a third run of the same entity, book and period that completes resolves it; a
    calculation of another period is another record."""
    # Imported here: the module registers the handler and its reader when it is imported.
    from erev_api.domain.journals import summarise

    assert registry.HANDLERS[JobKind.JOURNAL_RUN_CALCULATE].failed_item is not None
    with tenant_session(_db(world.place.tenant_id), read_only=True) as session:
        states = session.execute(
            select(period_state.c.book_code, period_state.c.period_id)
            .where(period_state.c.entity_id == world.entity_id)
            .order_by(period_state.c.period_end_date)
            .limit(2)
        ).all()
    (book, september), (_, other_period) = (
        (str(getattr(state[0], "value", state[0])), state[1]) for state in states
    )

    def calculation(period_id: UUID) -> tuple[UUID, dict[str, Any]]:
        run_id = new_id()
        return run_id, {
            "journal_run_id": str(run_id),
            "entity_id": str(world.entity_id),
            "book_code": book,
            "period_id": str(period_id),
        }

    def started(period_id: UUID) -> UUID:
        run_id, params = calculation(period_id)
        return _start(
            world,
            params,
            subject_type=summarise.OBJECT_TYPE,
            subject_id=run_id,
            kind=JobKind.JOURNAL_RUN_CALCULATE,
        )

    _fail(world, started(september))
    _fail(world, started(september))
    (item,) = _items(world)
    record = f"{world.entity_id}:{book}:{september}"
    assert (
        item["source"],
        item["dedupe_key"],
        item["occurrence_count"],
        item["entity_id"],
        item["period_id"],
        item["status"],
    ) == (
        "JOURNAL",
        f"JOURNAL:JOB_FAILED:JOURNAL_RUN_CALCULATE:{record}",
        2,
        world.entity_id,
        september,
        "OPEN",
    )
    _fail(world, started(other_period))
    assert [row["period_id"] for row in _items(world)] == [september, other_period]

    _succeed(world, started(september), monkeypatch)
    first, second = _items(world)
    assert (first["status"], first["resolved_by_kind"]) == ("RESOLVED", "SYSTEM")
    assert (second["period_id"], second["status"]) == (other_period, "OPEN")


def test_job_failed_item_1_the_item_holds_no_close_and_is_dismissed_with_a_comment(
    world: K11World,
) -> None:
    """The item is information: the count behind ``blockers.exceptions_open`` and the gate
    ``EXCEPTIONS_CLEARED`` leaves it out, where it counts a ``WARNING`` item of the same entity
    that names no period. A holder of ``exception.resolve`` dismisses it with a comment — its
    source is ``ENGINE``, whose items are otherwise closed by a waiver alone (PRD BR-DAT-04)."""
    contract_id, params = _computing(world)
    _fail(world, _start(world, params, subject_type="contract", subject_id=contract_id))
    (item,) = _items(world)
    maya = world.place.author

    with tenant_session(_db(world.place.tenant_id), read_only=True) as session:
        state = session.execute(
            select(period_state.c.book_code, period_state.c.period_id)
            .where(period_state.c.entity_id == world.entity_id)
            .limit(1)
        ).one()
        scope = gates.scope_of_period(
            session, world.entity_id, str(getattr(state[0], "value", state[0])), state[1]
        )
    assert scope is not None

    def counted() -> int:
        return int(
            world.place.scalar(
                select(func.count())
                .select_from(exception_item)
                .where(gates.blocking_exceptions(scope))
            )
        )

    assert counted() == 0
    # Control: a WARNING item of the entity without a period is counted for the period.
    with world.place.uow() as uow:
        raise_exception_item(
            uow,
            source=ExceptionSource.ENGINE,
            code="OBSERVABLE_POINT_MISSING",
            severity=ExceptionSeverity.WARNING,
            message="Price outside the range and no observable point; the range bound is used.",
            dedupe=f"ENGINE:OBSERVABLE_POINT_MISSING:{contract_id}",
            entity_id=world.entity_id,
            contract_id=contract_id,
        )
        uow.commit()
    assert counted() == 1

    shown = get(world.app, f"{EXCEPTIONS}/{item['id']}", maya)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert (body["code"], body["severity"], body["source"], body["status"]) == (
        "JOB_FAILED",
        "INFO",
        "ENGINE",
        "OPEN",
    )
    assert (body["available_actions"], body["dismiss_blocked_reason"]) == (
        ["ASSIGN", "DISMISS"],
        None,
    )
    dismissed = post(world.app, f"{EXCEPTIONS}/{item['id']}/dismiss", maya, {"comment": DISMISSAL})
    assert dismissed.status_code == 200, dismissed.text
    closed = dismissed.json()
    assert (closed["status"], closed["resolution"], closed["resolved_by"]["kind"]) == (
        "DISMISSED",
        DISMISSAL,
        "USER",
    )
    assert (closed["available_actions"], closed["dismiss_blocked_reason"]) == ([], None)
    assert counted() == 1  # the control item is untouched


def test_job_failed_item_1_an_item_that_cannot_be_raised_leaves_the_job_failed(
    world: K11World, monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    """The item is raised in a savepoint of the unit of work. A reader that raises, and a writer
    that raises after it wrote the item and buffered its audit event, are logged with their class
    and place; the job ends FAILED with its ``job.finish``, and nothing of the item stays — no
    row, and no audit event of a row that was rolled back."""
    contract_id, params = _computing(world)
    subject: dict[str, Any] = {"subject_type": "contract", "subject_id": contract_id}
    spec = registry.HANDLERS[JobKind.CONTRACT_COMPUTE]
    assert spec.failed_item is not None

    def unreadable(
        session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
    ) -> FailedSubject | None:
        raise LookupError("the record cannot be read")

    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.CONTRACT_COMPUTE,
        replace(spec, failed_item=replace(spec.failed_item, subject=unreadable)),
    )
    first = _start(world, params, **subject)
    _fail(world, first)
    assert _items(world) == [] and _events(world, first) == ["job.finish"]
    (line,) = _lines(log_stream, "job.failed_item_failed", first)
    assert (line["level"], line["job_kind"], line["error_class"]) == (
        "error",
        "CONTRACT_COMPUTE",
        "LookupError",
    )

    def written_then_refused(uow: Any, failed: FailedJob) -> None:
        spec.failed_item.raise_item(uow, failed)
        raise RuntimeError("the queue refused the item after writing it")

    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.CONTRACT_COMPUTE,
        replace(spec, failed_item=replace(spec.failed_item, raise_item=written_then_refused)),
    )
    second = _start(world, params, **subject)
    _fail(world, second)
    assert _items(world) == []
    assert _events(world, second) == ["job.finish"]  # no exception_item.create of a row undone
    (line,) = _lines(log_stream, "job.failed_item_failed", second)
    assert line["error_class"] == "RuntimeError"
    assert str(line["error_at"]).startswith("tests.") is False  # a place of the code base, or none


def test_job_failed_item_1_a_failure_hook_that_fails_leaves_nothing_behind(
    world: K11World, monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    """The kind's failure hook runs in a savepoint of the unit of work, not of the session: a
    hook that buffered an audit event and then failed leaves no event of what was rolled back
    (before, the session's savepoint undid the rows and the unit of work still wrote the
    event)."""
    contract_id, params = _computing(world)
    spec = registry.HANDLERS[JobKind.CONTRACT_COMPUTE]

    probes: list[UUID] = []

    def hook(uow: Any, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
        probes.append(UUID(str(problem["instance"]).rsplit("/", 1)[-1]))
        uow.audit(
            action="job.hook_probe",
            object_type="job",
            object_id=probes[-1],
            after={"probe": "written by a hook that then failed"},
        )
        raise RuntimeError("the record could not be ended")

    monkeypatch.setitem(registry.HANDLERS, JobKind.CONTRACT_COMPUTE, replace(spec, on_failure=hook))
    job_id = _start(world, params, subject_type="contract", subject_id=contract_id)
    _fail(world, job_id)
    assert probes == [job_id]  # the hook ran, for this job
    assert [
        line["error_class"] for line in _lines(log_stream, "job.failure_hook_failed", job_id)
    ] == ["RuntimeError"]
    # The job is FAILED, the item of the failed job is raised, and the hook's event is not there.
    assert sorted(_events(world, job_id)) == ["exception_item.create", "job.finish"]
    assert [row["occurrence_count"] for row in _items(world)] == [1]
