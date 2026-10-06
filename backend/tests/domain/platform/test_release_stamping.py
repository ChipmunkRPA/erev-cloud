"""Release identity of deferred jobs (05 REL-05; 04 §15.2 `release-mismatch`; D-80; dev-guide
DG-KRN-JOB-02, DG-KRN-JOB-03, DG-KRN-JOB-13; BUILD_SPEC SOP-2).

`insert_job` records the enqueuing process's stamped release as `params.engine_release_id` on every
enqueue path (callers cannot supply the reserved key); a worker whose stamped release differs
re-defers the job for 30 seconds up to 10 times, then fails it with `release-mismatch` (503). A job
without a pin (queued before REL-05) follows the same bounded path and fails closed; a malformed pin
fails at once with `validation-failed`; only a runtime without a stamped release (tests,
`run_inline`) compares nothing, and says so in its log. Re-dispatches are fenced on the observed
task (D-80) and the deferral budget survives slot contention and recovery. Handlers never see the
reserved key.

CTL-032 (03 REQ-CTL-003; 05 REL-03; BUILD_SPEC SOP-2): `test_ctl_032_runs_stamped_with_release` is
the control's witness — the run records one working day leaves through the product name the
release this process stamped at its start, and none of them can be written without one.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls import release
from erev_api.controls.release import EngineRelease
from erev_api.db import new_id
from erev_api.db.migration_ops import code_head
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_computation,
    control_execution,
    engine_release,
    job,
    journal_batch,
    metadata,
    report_run,
)
from erev_api.db.transitions import apply
from erev_api.domain.contracts import compute_job
from erev_api.enums import JobKind, JobState, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import HandlerSpec, JobOutcome, RetryPolicy, job_slot, run_job
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import Table, exc, insert, select, text
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import RELEASE_BUILD, tenant_factory, tenant_id_of
from support.reference import post
from support.rows import engine_release_values
from support.worlds import AVM_US, K01, journal_run, k01_pellworth
from support.worlds import report_run as report_run_through_the_route

_TASK = text(
    "SELECT task_name, queue_name, queueing_lock, args, status, scheduled_at, attempts "
    "FROM procrastinate_jobs WHERE id = :id"
)
_TASKS_WITH_LOCK = text("SELECT count(*) FROM procrastinate_jobs WHERE queueing_lock = :lock")
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
_TASK_FAILED = text("UPDATE procrastinate_jobs SET status = 'failed' WHERE id = :id")
RELEASE_MISMATCH_TYPE = "https://erev.dev/problems/release-mismatch"
VALIDATION_FAILED_TYPE = "https://erev.dev/problems/validation-failed"
THIRTY_SECONDS = timedelta(seconds=30)


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring))


def _release(build: str) -> EngineRelease:
    return EngineRelease(
        id=uuid4(),
        engine_version=ENGINE_VERSION,
        build_sha=build,
        schema_revision=code_head(),
        deployed_at=FROZEN_AT,
    )


def _runtime(
    app_settings: Settings, keyring: KeyRing, clock: FrozenClock, stamped: EngineRelease | None
) -> JobRuntime:
    return JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
        engine_release=stamped,
    )


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@contextmanager
def _uow(tenant_id: UUID, runtime: JobRuntime, clock: FrozenClock) -> Iterator[Any]:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-release-stamping",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    assert runtime.keyring is not None and runtime.files is not None
    with unit_of_work(ctx, clock=clock, keyring=runtime.keyring, files=runtime.files) as uow:
        yield uow


def _defer(
    tenant_id: UUID,
    runtime: JobRuntime,
    clock: FrozenClock,
    params: Mapping[str, Any],
    *,
    enqueuer: EngineRelease | None,
) -> UUID:
    """Defer as a process that stamped ``enqueuer`` (None: a process that stamped nothing)."""
    release.remember_release(enqueuer)
    try:
        with _uow(tenant_id, runtime, clock) as uow:
            row = uow.defer(JobKind.REPORT_RUN, params)
            uow.commit()
    finally:
        release.remember_release(None)
    return UUID(str(row["id"]))


def _insert_raw(tenant_id: UUID, clock: FrozenClock, params: Mapping[str, Any]) -> UUID:
    """A QUEUED job row with exactly ``params`` (legacy or malformed pins bypass ``insert_job``)."""
    job_id = new_id()
    with tenant_session(_db(tenant_id)) as session:
        session.execute(
            insert(job).values(
                tenant_id=tenant_id,
                id=job_id,
                kind=JobKind.REPORT_RUN.value,
                state=JobState.QUEUED.value,
                params=dict(params),
                queue=registry.JOB_QUEUE[JobKind.REPORT_RUN],
                priority=0,
                created_at=clock.now(),
                created_by=None,
                created_by_kind=PrincipalKind.SYSTEM.value,
                updated_at=clock.now(),
                updated_by=None,
                updated_by_kind=PrincipalKind.SYSTEM.value,
            )
        )
        registry.dispatch(
            session,
            job_id=job_id,
            tenant_id=tenant_id,
            queue=registry.JOB_QUEUE[JobKind.REPORT_RUN],
            now=clock.now(),
        )
    return job_id


def _job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _task(tenant_id: UUID, procrastinate_job_id: int) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(_TASK, {"id": procrastinate_job_id}).mappings().one()


def _tasks_of(tenant_id: UUID, job_id: UUID) -> int:
    with tenant_session(_db(tenant_id)) as session:
        return int(session.execute(_TASKS_WITH_LOCK, {"lock": str(job_id)}).scalar_one())


def _fetch(tenant_id: UUID, job_id: UUID) -> int:
    """The worker takes the job's current task: its Procrastinate row becomes ``doing``."""
    procrastinate_job_id = int(_job(tenant_id, job_id)["procrastinate_job_id"])
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    return procrastinate_job_id


def _recording(seen: list[dict[str, Any]], *, max_attempts: int = 1) -> HandlerSpec:
    def handler(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        seen.append(dict(params))
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 0}})

    return HandlerSpec(handler=handler, retry=RetryPolicy(max_attempts=max_attempts))


def _assert_deferred(
    tenant_id: UUID, job_id: UUID, *, previous_task: int, deferrals: int, delay: timedelta
) -> int:
    """The job is still QUEUED under a new task scheduled after ``delay`` carrying ``deferrals``."""
    waiting = _job(tenant_id, job_id)
    assert (waiting["state"], waiting["started_at"]) == ("QUEUED", None)
    assert waiting["procrastinate_job_id"] != previous_task
    task = _task(tenant_id, waiting["procrastinate_job_id"])
    assert task["scheduled_at"] == FROZEN_AT + delay
    assert (task["status"], task["queueing_lock"], task["args"]["attempt"]) == (
        "todo",
        str(job_id),
        1,
    )
    assert task["args"].get("release_mismatch_deferrals", 0) == deferrals
    return int(waiting["procrastinate_job_id"])


def _assert_failed_release_mismatch(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    failed = _job(tenant_id, job_id)
    assert failed["state"] == "FAILED"
    assert (failed["started_at"], failed["finished_at"]) == (FROZEN_AT, FROZEN_AT)
    assert failed["problem"]["type"] == RELEASE_MISMATCH_TYPE
    assert failed["problem"]["status"] == 503
    assert failed["problem"]["instance"] == f"/api/v1/jobs/{job_id}"
    return failed


def test_rel_05_release_mismatch_redefers_then_fails(
    tenant_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, _recording(seen))
    mine, other = _release("w" * 40), _release("o" * 40)
    worker = _runtime(app_settings, keyring, clock, mine)

    # Enqueued by another release: ten 30-second re-deferrals that never run the handler …
    foreign = _defer(tenant_id, worker, clock, {"probe": True}, enqueuer=other)
    assert _job(tenant_id, foreign)["params"]["engine_release_id"] == str(other.id)
    task = _fetch(tenant_id, foreign)
    for deferrals in range(registry.RELEASE_MISMATCH_MAX_DEFERRALS):
        run_job(foreign, tenant_id, attempt=1, runtime=worker, release_mismatch_deferrals=deferrals)
        task = _assert_deferred(
            tenant_id,
            foreign,
            previous_task=task,
            deferrals=deferrals + 1,
            delay=THIRTY_SECONDS,
        )
        _fetch(tenant_id, foreign)
    assert seen == []

    # … then the eleventh delivery fails the job with release-mismatch (503) without running it.
    run_job(
        foreign,
        tenant_id,
        attempt=1,
        runtime=worker,
        release_mismatch_deferrals=registry.RELEASE_MISMATCH_MAX_DEFERRALS,
    )
    failed = _assert_failed_release_mismatch(tenant_id, foreign)
    assert str(other.id) in failed["problem"]["detail"]
    assert seen == []
    # A duplicate delivery of the failed job does nothing.
    run_job(foreign, tenant_id, attempt=1, runtime=worker, release_mismatch_deferrals=3)
    assert _job(tenant_id, foreign)["state"] == "FAILED"

    # The worker's own release runs at once; the handler never sees the key.
    same = _defer(tenant_id, worker, clock, {"probe": True}, enqueuer=mine)
    _fetch(tenant_id, same)
    run_job(same, tenant_id, attempt=1, runtime=worker)
    assert _job(tenant_id, same)["state"] == "SUCCEEDED"
    assert seen == [{"probe": True}]


def test_rel_05_enqueue_stamps_the_actual_release(
    tenant_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mine = _release("e" * 40)
    runtime = _runtime(app_settings, keyring, clock, mine)

    # A process that stamped nothing (tests, CLI) leaves the params as the caller gave them.
    plain = _defer(tenant_id, runtime, clock, {"probe": True}, enqueuer=None)
    assert _job(tenant_id, plain)["params"] == {"probe": True}

    # A stamped process records its release on every enqueue …
    recorded = _defer(tenant_id, runtime, clock, {"probe": True}, enqueuer=mine)
    assert _job(tenant_id, recorded)["params"] == {
        "probe": True,
        "engine_release_id": str(mine.id),
    }
    # … and callers cannot supply the reserved key, stamped or not, whatever the value.
    for value in (str(uuid4()), str(mine.id), None, "", 42):
        for enqueuer in (mine, None):
            with pytest.raises(ValueError, match="engine_release_id"):
                _defer(
                    tenant_id,
                    runtime,
                    clock,
                    {"probe": True, "engine_release_id": value},
                    enqueuer=enqueuer,
                )

    # A child a handler defers carries the worker process's release, not the parent's pin.
    children: list[UUID] = []

    def parent_handler(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        assert params == {"probe": True}, "the handler never sees the reserved key"
        with context.unit_of_work() as uow:
            child = uow.defer(JobKind.REPORT_RUN, {"child": True})
            uow.commit()
        children.append(UUID(str(child["id"])))
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 0}})

    monkeypatch.setitem(
        registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(parent_handler, RetryPolicy())
    )
    release.remember_release(mine)
    try:
        _fetch(tenant_id, recorded)
        run_job(recorded, tenant_id, attempt=1, runtime=runtime)
    finally:
        release.remember_release(None)
    assert _job(tenant_id, recorded)["state"] == "SUCCEEDED"
    (child_id,) = children
    assert _job(tenant_id, child_id)["params"] == {
        "child": True,
        "engine_release_id": str(mine.id),
    }
    assert registry.handler_params({"a": 1, "engine_release_id": "r"}) == {"a": 1}


def test_rel_05_legacy_and_malformed_pins_fail_closed(
    tenant_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, _recording(seen))
    mine = _release("w" * 40)
    worker = _runtime(app_settings, keyring, clock, mine)

    # A job queued before REL-05 records no enqueuing release: a stamped worker never claims
    # compatibility. It waits the same bounded 30-second cycle (an older worker may still take it
    # during the roll-out) and then fails closed with release-mismatch; the work is not deleted.
    legacy = _insert_raw(tenant_id, clock, {"probe": True})
    task = _fetch(tenant_id, legacy)
    for deferrals in range(registry.RELEASE_MISMATCH_MAX_DEFERRALS):
        run_job(legacy, tenant_id, attempt=1, runtime=worker, release_mismatch_deferrals=deferrals)
        task = _assert_deferred(
            tenant_id, legacy, previous_task=task, deferrals=deferrals + 1, delay=THIRTY_SECONDS
        )
        _fetch(tenant_id, legacy)
    run_job(
        legacy,
        tenant_id,
        attempt=1,
        runtime=worker,
        release_mismatch_deferrals=registry.RELEASE_MISMATCH_MAX_DEFERRALS,
    )
    failed = _assert_failed_release_mismatch(tenant_id, legacy)
    assert "no enqueuing release" in failed["problem"]["detail"]
    assert seen == []

    # A malformed pin cannot become valid by waiting: the job fails at once with validation-failed
    # naming the field, without a new task and without running.
    for value in (None, "", 42, "not-a-uuid", ["x"]):
        malformed = _insert_raw(tenant_id, clock, {"probe": True, "engine_release_id": value})
        _fetch(tenant_id, malformed)
        tasks_before = _tasks_of(tenant_id, malformed)
        run_job(malformed, tenant_id, attempt=1, runtime=worker)
        row = _job(tenant_id, malformed)
        assert row["state"] == "FAILED", repr(value)
        assert (row["started_at"], row["finished_at"]) == (FROZEN_AT, FROZEN_AT)
        assert row["problem"]["type"] == VALIDATION_FAILED_TYPE
        assert row["problem"]["status"] == 422
        assert row["problem"]["errors"][0]["field"] == "params.engine_release_id"
        assert row["problem"]["errors"][0]["rule_id"] == "REL-05"
        assert _tasks_of(tenant_id, malformed) == tasks_before, "no re-dispatch"
    assert seen == []

    # Only a runtime without a stamped release (tests, run_inline) compares nothing: a foreign pin
    # and a legacy job both run there. Production workers always stamp (worker.main).
    naive = _runtime(app_settings, keyring, clock, None)
    other = _release("o" * 40)
    foreign = _defer(tenant_id, naive, clock, {"probe": True}, enqueuer=other)
    _fetch(tenant_id, foreign)
    run_job(foreign, tenant_id, attempt=1, runtime=naive)
    unpinned = _insert_raw(tenant_id, clock, {"probe": True})
    _fetch(tenant_id, unpinned)
    run_job(unpinned, tenant_id, attempt=1, runtime=naive)
    assert _job(tenant_id, foreign)["state"] == "SUCCEEDED"
    assert _job(tenant_id, unpinned)["state"] == "SUCCEEDED"
    assert seen == [{"probe": True}, {"probe": True}]


def test_rel_05_stale_delivery_never_redispatches(
    tenant_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # D-80 fence: the mismatch re-dispatch happens only while the row is still QUEUED under the
    # task the delivery observed. A stale delivery (a successor task exists, runs, finished or the
    # job was cancelled) never creates a task or replaces the pointer of its successor.
    seen: list[dict[str, Any]] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, _recording(seen))
    mine, other = _release("w" * 40), _release("o" * 40)
    worker = _runtime(app_settings, keyring, clock, mine)
    compatible = _runtime(app_settings, keyring, clock, other)

    def stale_delivery(job_id: UUID, stale_task: int, *, deferrals: int) -> None:
        with tenant_session(_db(tenant_id)) as session:
            current = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        registry._settle_release_mismatch(
            job_id,
            tenant_id,
            current=current,
            queue=str(current["queue"]),
            task_id=stale_task,
            attempt=1,
            deferrals=deferrals,
            pin=registry.classify_release_pin(current["params"], mine.id),
            runtime=worker,
        )

    # Successor dispatched (still QUEUED under task B): the stale delivery of task A is a no-op.
    job_id = _defer(tenant_id, worker, clock, {"probe": True}, enqueuer=other)
    task_a = _fetch(tenant_id, job_id)
    with tenant_session(_db(tenant_id)) as session:
        task_b = registry.dispatch(
            session,
            job_id=job_id,
            tenant_id=tenant_id,
            queue=str(_job(tenant_id, job_id)["queue"]),
            now=clock.now(),
        )
    assert _tasks_of(tenant_id, job_id) == 2
    for deferrals in (0, 5, registry.RELEASE_MISMATCH_MAX_DEFERRALS):
        stale_delivery(job_id, task_a, deferrals=deferrals)
        row = _job(tenant_id, job_id)
        assert (row["state"], row["procrastinate_job_id"]) == ("QUEUED", task_b)
        assert _tasks_of(tenant_id, job_id) == 2

    # Successor RUNNING under task B, then SUCCEEDED: the stale delivery changes nothing.
    _fetch(tenant_id, job_id)
    run_job(job_id, tenant_id, attempt=1, runtime=compatible)  # the compatible worker runs it
    assert _job(tenant_id, job_id)["state"] == "SUCCEEDED"
    assert seen == [{"probe": True}]
    for deferrals in (0, registry.RELEASE_MISMATCH_MAX_DEFERRALS):
        stale_delivery(job_id, task_a, deferrals=deferrals)
        row = _job(tenant_id, job_id)
        assert (row["state"], row["procrastinate_job_id"]) == ("SUCCEEDED", task_b)
        assert _tasks_of(tenant_id, job_id) == 2

    # RUNNING successor: the stale terminal delivery must not move it to FAILED either. The
    # successor is taken (`doing`) before the job runs, as a real worker leaves it.
    running = _defer(tenant_id, worker, clock, {"probe": True}, enqueuer=other)
    stale = _fetch(tenant_id, running)
    with tenant_session(_db(tenant_id)) as session:
        successor = registry.dispatch(
            session,
            job_id=running,
            tenant_id=tenant_id,
            queue=str(_job(tenant_id, running)["queue"]),
            now=clock.now(),
        )
    _fetch(tenant_id, running)
    with tenant_session(_db(tenant_id)) as session:
        apply(
            session,
            "job",
            running,
            to_status="RUNNING",
            set_values={"started_at": FROZEN_AT},
            expected_status="QUEUED",
        )
    for deferrals in (0, registry.RELEASE_MISMATCH_MAX_DEFERRALS):
        stale_delivery(running, stale, deferrals=deferrals)
        row = _job(tenant_id, running)
        assert (row["state"], row["procrastinate_job_id"]) == ("RUNNING", successor)
        assert row["problem"] is None
        assert _tasks_of(tenant_id, running) == 2
    # Finish it, so no stale RUNNING job is left to another test's sweeper (DG-KRN-JOB-06).
    with tenant_session(_db(tenant_id)) as session:
        apply(
            session,
            "job",
            running,
            to_status="SUCCEEDED",
            set_values={"finished_at": FROZEN_AT, "result": {"counts": {"rows": 0}}},
            expected_status="RUNNING",
        )
    assert _job(tenant_id, running)["state"] == "SUCCEEDED"

    # CANCELLED job: no needless task, pointer untouched.
    cancelled = _defer(tenant_id, worker, clock, {"probe": True}, enqueuer=other)
    task_c = _fetch(tenant_id, cancelled)
    with tenant_session(_db(tenant_id)) as session:
        apply(
            session,
            "job",
            cancelled,
            to_status="CANCELLED",
            set_values={"finished_at": FROZEN_AT},
            expected_status="QUEUED",
        )
    stale_delivery(cancelled, task_c, deferrals=0)
    row = _job(tenant_id, cancelled)
    assert (row["state"], row["procrastinate_job_id"]) == ("CANCELLED", task_c)
    assert _tasks_of(tenant_id, cancelled) == 1

    # Duplicate mismatch deliveries of one task: the first re-dispatches, the second is stale.
    twice = _defer(tenant_id, worker, clock, {"probe": True}, enqueuer=other)
    first = _fetch(tenant_id, twice)
    run_job(twice, tenant_id, attempt=1, runtime=worker)
    replaced = _assert_deferred(
        tenant_id, twice, previous_task=first, deferrals=1, delay=THIRTY_SECONDS
    )
    stale_delivery(twice, first, deferrals=0)
    row = _job(tenant_id, twice)
    assert (row["state"], row["procrastinate_job_id"]) == ("QUEUED", replaced)
    assert _tasks_of(tenant_id, twice) == 2
    assert seen == [{"probe": True}]


def test_rel_05_budget_survives_slot_contention_and_recovery(
    tenant_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # REL-05 allows up to ten deferrals for the job. A compatible worker without a free slot, and
    # the sweeper's recovery of a stranded task, re-dispatch without executing and must carry the
    # count; alternating wrong and busy workers therefore reaches the same terminal failure.
    seen: list[dict[str, Any]] = []
    # Three attempts, so the sweeper's recovery may replace a failed task (attempt 1 → 2) and
    # retry a stalled one (attempt 2 < 3) instead of ending the job.
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, _recording(seen, max_attempts=3))
    mine, other = _release("w" * 40), _release("o" * 40)
    wrong = _runtime(app_settings, keyring, clock, mine)
    busy = _runtime(app_settings, keyring, clock, other)  # compatible, but its slots are full

    job_id = _defer(tenant_id, wrong, clock, {"probe": True}, enqueuer=other)
    task = _fetch(tenant_id, job_id)
    run_job(job_id, tenant_id, attempt=1, runtime=wrong)
    task = _assert_deferred(
        tenant_id, job_id, previous_task=task, deferrals=1, delay=THIRTY_SECONDS
    )

    with ExitStack() as stack:
        held = [stack.enter_context(job_slot(tenant_id, 4)) for _ in range(4)]
        assert held == [0, 1, 2, 3]
        _fetch(tenant_id, job_id)
        run_job(job_id, tenant_id, attempt=1, runtime=busy, release_mismatch_deferrals=1)
        # Slot contention: 5-second re-dispatch that keeps the count at 1.
        task = _assert_deferred(
            tenant_id, job_id, previous_task=task, deferrals=1, delay=timedelta(seconds=5)
        )
    assert seen == []

    _fetch(tenant_id, job_id)
    run_job(job_id, tenant_id, attempt=1, runtime=wrong, release_mismatch_deferrals=1)
    task = _assert_deferred(
        tenant_id, job_id, previous_task=task, deferrals=2, delay=THIRTY_SECONDS
    )

    # Recovery of a failed task (sweeper, D-80): the replacement carries the count.
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_TASK_FAILED, {"id": task})
    state = registry.retry_stranded(
        job_id,
        tenant_id,
        task_id=task,
        attempt=1,
        stalled=False,
        error=RuntimeError("stranded"),
        runtime=busy,
    )
    assert state == JobState.QUEUED
    waiting = _job(tenant_id, job_id)
    replacement = _task(tenant_id, waiting["procrastinate_job_id"])
    assert waiting["procrastinate_job_id"] != task
    assert (replacement["args"]["attempt"], replacement["args"]["release_mismatch_deferrals"]) == (
        2,
        2,
    )
    task = int(waiting["procrastinate_job_id"])

    # Recovery of a stalled task retries it in place: the arguments (and the count) stay.
    _fetch(tenant_id, job_id)
    state = registry.retry_stranded(
        job_id,
        tenant_id,
        task_id=task,
        attempt=2,
        stalled=True,
        error=RuntimeError("stalled"),
        runtime=busy,
    )
    assert state == JobState.QUEUED
    assert _job(tenant_id, job_id)["procrastinate_job_id"] == task
    assert _task(tenant_id, task)["args"]["release_mismatch_deferrals"] == 2

    # The wrong worker exhausts the remaining budget: eight more deferrals, then one failure.
    for deferrals in range(2, registry.RELEASE_MISMATCH_MAX_DEFERRALS):
        _fetch(tenant_id, job_id)
        run_job(job_id, tenant_id, attempt=2, runtime=wrong, release_mismatch_deferrals=deferrals)
        waiting = _job(tenant_id, job_id)
        assert waiting["state"] == "QUEUED"
        assert _task(tenant_id, waiting["procrastinate_job_id"])["args"] == {
            "job_id": str(job_id),
            "tenant_id": str(tenant_id),
            "attempt": 2,
            "release_mismatch_deferrals": deferrals + 1,
        }
    _fetch(tenant_id, job_id)
    run_job(
        job_id,
        tenant_id,
        attempt=2,
        runtime=wrong,
        release_mismatch_deferrals=registry.RELEASE_MISMATCH_MAX_DEFERRALS,
    )
    _assert_failed_release_mismatch(tenant_id, job_id)
    assert seen == []
    # No second terminal failure: a later delivery of any kind is a no-op.
    run_job(job_id, tenant_id, attempt=2, runtime=busy)
    assert _job(tenant_id, job_id)["state"] == "FAILED"
    assert seen == []


def test_rel_05_worker_entry_fences_the_delivered_task(
    tenant_id: UUID,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The worker passes the Procrastinate task it is delivering (`context.job.id`); the registry
    # compares it with the locked row's pointer at entry. A delivery of task A that arrives after
    # a successor B replaced the pointer is stale: no handler, no transition, no task, no pointer
    # or count change, whatever the worker's release and whatever B's status.
    seen: list[dict[str, Any]] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, _recording(seen))
    mine, other = _release("w" * 40), _release("o" * 40)
    wrong = _runtime(app_settings, keyring, clock, mine)
    right = _runtime(app_settings, keyring, clock, other)

    def successor(job_id: UUID, *, deferrals: int) -> int:
        with tenant_session(_db(tenant_id)) as session:
            return registry.dispatch(
                session,
                job_id=job_id,
                tenant_id=tenant_id,
                queue=str(_job(tenant_id, job_id)["queue"]),
                now=clock.now(),
                release_mismatch_deferrals=deferrals,
            )

    # (a) Matching release, B todo: stale A claims nothing; the legitimate B delivery then runs.
    job_a = _defer(tenant_id, right, clock, {"probe": True}, enqueuer=other)
    task_a = _fetch(tenant_id, job_a)
    task_b = successor(job_a, deferrals=1)
    run_job(job_a, tenant_id, attempt=1, runtime=right, delivered_task_id=task_a)
    row = _job(tenant_id, job_a)
    assert (row["state"], row["started_at"], row["procrastinate_job_id"]) == (
        "QUEUED",
        None,
        task_b,
    )
    assert _tasks_of(tenant_id, job_a) == 2
    assert _task(tenant_id, task_b)["args"]["release_mismatch_deferrals"] == 1
    assert seen == []
    _fetch(tenant_id, job_a)
    run_job(
        job_a,
        tenant_id,
        attempt=1,
        runtime=right,
        delivered_task_id=task_b,
        release_mismatch_deferrals=1,
    )
    assert _job(tenant_id, job_a)["state"] == "SUCCEEDED"
    assert seen == [{"probe": True}]

    # (b) Mismatch, B doing, row QUEUED: stale A inserts no C and changes no count; the legitimate
    # B delivery advances 1 → 2.
    job_b = _defer(tenant_id, wrong, clock, {"probe": True}, enqueuer=other)
    task_a = _fetch(tenant_id, job_b)
    task_b = successor(job_b, deferrals=1)
    _fetch(tenant_id, job_b)  # B doing
    run_job(job_b, tenant_id, attempt=1, runtime=wrong, delivered_task_id=task_a)
    row = _job(tenant_id, job_b)
    assert (row["state"], row["procrastinate_job_id"]) == ("QUEUED", task_b)
    assert _tasks_of(tenant_id, job_b) == 2
    assert _task(tenant_id, task_b)["args"]["release_mismatch_deferrals"] == 1
    run_job(
        job_b,
        tenant_id,
        attempt=1,
        runtime=wrong,
        delivered_task_id=task_b,
        release_mismatch_deferrals=1,
    )
    task_c = _assert_deferred(
        tenant_id, job_b, previous_task=task_b, deferrals=2, delay=THIRTY_SECONDS
    )
    assert _tasks_of(tenant_id, job_b) == 3

    # (c) Mismatch, B todo: stale A returns harmlessly, never reaching a queueing-lock conflict.
    job_c = _defer(tenant_id, wrong, clock, {"probe": True}, enqueuer=other)
    task_a = _fetch(tenant_id, job_c)
    task_b = successor(job_c, deferrals=1)
    run_job(job_c, tenant_id, attempt=1, runtime=wrong, delivered_task_id=task_a)
    row = _job(tenant_id, job_c)
    assert (row["state"], row["procrastinate_job_id"]) == ("QUEUED", task_b)
    assert _tasks_of(tenant_id, job_c) == 2
    assert _task(tenant_id, task_b)["args"]["release_mismatch_deferrals"] == 1
    # (d) Ordinary control: the delivered task is the pointer, so B advances its own counter.
    _fetch(tenant_id, job_c)
    run_job(
        job_c,
        tenant_id,
        attempt=1,
        runtime=wrong,
        delivered_task_id=task_b,
        release_mismatch_deferrals=1,
    )
    _assert_deferred(tenant_id, job_c, previous_task=task_b, deferrals=2, delay=THIRTY_SECONDS)
    assert seen == [{"probe": True}]
    assert task_c != task_b


# --- CTL-032: the run records name the running release ----------------------------------------

NOT_NULL_VIOLATION = "23502"
JANUARY = "FY2026-P01"
# WLD-K-01's second invoice (PRD §2.7): a fact a person records and the route appends at once.
INVOICE_OF_FEBRUARY = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-02-27",
    "payload": {
        "invoice_number": "INV-US-1044",
        "line_external_id": "INV-US-1044-1",
        "obligation_key": "O2",
        "amount": {"amount": "15000.00", "currency": "USD"},
        "issue_date": "2026-02-27",
    },
}
# The run records that carry `engine_release_id` (04 T-CON-07, T-SL-08, T-RPT-02, T-PLT-39), each
# written at a call site of its own: `computation.persist` and `compute_job._refused`,
# `journals.summarise`, `reports.framework`, `controls.evidence`.
RUN_RECORDS: tuple[Table, ...] = (
    contract_computation,
    journal_batch,
    report_run,
    control_execution,
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _refusing(bundle: InputBundle) -> OutputBundle:
    """An engine that refuses the group: the product stores the refusal as a computation."""
    raise EngineError("ENGINE_INVARIANT_VIOLATED", "allocation does not sum", detail={})


@pytest.mark.control("CTL-032")
def test_ctl_032_runs_stamped_with_release(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """CTL-032 (03 REQ-CTL-003: "every calculation run and report run stamps the engine
    release"; 05 REL-03; BUILD_SPEC SOP-2). One process stamps its release at its start, as the
    api and the worker do, and does a day's work through the product: computations by the
    booking world's commands and by the events route, a computation the engine refuses, a
    journal run and a report run through their routes and the worker's job, and the control
    executions those producers record. Every run record of the tenant names THAT release — also
    after another build of the same engine version was deployed into the same database, which a
    "latest row of the version" would name instead. And none of the four can be written with no
    release at all: the column refuses a null (04 NOT NULL).

    Not witnessed here, by name. The acceptance's fifth record, a deal preview (04 T-FC-04), is
    not built: the last line fails when that table arrives, so that it is added. The control's
    other half, the release manifest with its gate evidence, is witnessed in
    tests/unit/test_release_manifest.py and tests/pg/test_engine_release.py. That a process
    which stamped NO release is refused outside dev and test is witnessed in
    tests/unit/test_consumer_release_identity.py and tests/unit/test_evidence_release_identity.py.
    The other stamp of the control's title, the report definition a run names
    (`report_run.report_code` and `report_version`), is asserted by CTL-029's witness,
    tests/domain/reports/test_framework.py::test_ctl_029_run_record_and_rerun; every definition
    is version 1 today, so no run can yet tell that stamp from a constant.
    """
    world = k01_pellworth(
        app, keyring, clock, LocalFileStore(app_settings.file_root), through=date(2026, 1, 31)
    )
    running = release.current_release()
    assert running is not None
    assert (running.engine_version, running.build_sha) == (ENGINE_VERSION, RELEASE_BUILD)
    tenant = _db(world.tenant_id)

    def rows(table: Table) -> list[dict[str, Any]]:
        with tenant_session(tenant, read_only=True) as session:
            return [dict(row) for row in session.execute(select(table)).mappings()]

    before = len(rows(contract_computation))
    assert before >= 1  # the booking world computed once, under the same stamp

    # Another process deploys a later build of the same engine version: from here on it is the
    # latest `engine_release` row of the running version, and not this process's.
    later = engine_release_values()
    with tenant_session(tenant) as session:
        session.execute(insert(engine_release).values(**later))
        latest = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == ENGINE_VERSION)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one()
    assert latest == later["id"] != running.id

    # The day's work, through the product.
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    billed = post(
        app,
        f"/api/v1/contracts/{contract_id}/events",
        world.maya,
        {"events": [INVOICE_OF_FEBRUARY]},
        if_match=f'"s{int(head)}"',
    )
    assert billed.status_code == 201, billed.text
    assert billed.json()["computation"]["status"] == "SUCCEEDED", billed.text
    with world.place.uow() as uow:
        refused = compute_job.compute_group(uow, group_id, engine=_refusing)
        uow.commit()
    assert refused.status is not None and refused.status.value == "QUARANTINED"
    journal = journal_run(world, period_key=JANUARY)
    report, _ = report_run_through_the_route(
        world,
        "contract_balances",
        {"entity_codes": [AVM_US], "book": "ASC606", "period_key": JANUARY},
    )
    assert report["engine_release"] == {
        "engine_version": running.engine_version,
        "build_sha": running.build_sha,
    }

    # Every run record of the tenant names the release this process stamped.
    found = {table.name: rows(table) for table in RUN_RECORDS}
    computations = found[contract_computation.name]
    assert len(computations) == before + 2
    assert {str(row["status"]) for row in computations} == {"SUCCEEDED", "QUARANTINED"}
    assert {row["journal_run_id"] for row in found[journal_batch.name]} == {
        UUID(str(journal["id"]))
    }
    assert [row["id"] for row in found[report_run.name]] == [UUID(str(report["id"]))]
    assert {str(row["run_ref_type"]) for row in found[control_execution.name]} >= {
        "CONTRACT_COMPUTATION",
        "JOURNAL_BATCH",
        "REPORT_RUN",
    }
    for name, stored in found.items():
        assert stored, name
        assert {row["engine_release_id"] for row in stored} == {running.id}, name

    # None of them can be written without a release: the same row again, with none.
    for table in RUN_RECORDS:
        unstamped = {**found[table.name][0], "id": new_id(), "engine_release_id": None}
        with pytest.raises(exc.IntegrityError) as null_refused, tenant_session(tenant) as session:
            session.execute(insert(table).values(**unstamped))
        assert null_refused.value.orig.sqlstate == NOT_NULL_VIOLATION, table.name  # type: ignore[union-attr]
        assert null_refused.value.orig.diag.column_name == "engine_release_id", table.name  # type: ignore[union-attr]
        assert len(rows(table)) == len(found[table.name]), table.name

    # The acceptance's fifth record. T-FC-04 `deal_preview` is not built; when it is, its
    # `engine_release_id` belongs in RUN_RECORDS and a preview in the day's work above.
    assert "deal_preview" not in {table.name for table in metadata.tables.values()}
