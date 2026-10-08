"""Jobs KRN-JOB (dev-guide §5.12 DG-KRN-JOB-01 to 03, 05, 06; 05 JOB-02, JOB-03; BUILD_SPEC PLF-9).

The tests play the worker: after a dispatch they mark the Procrastinate row ``doing`` (the worker
fetched it) and call ``run_job`` as the task body would. The last three tests are the witnesses of
the registry's audit events (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a)).
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.audit.verify import verify_tenant_chain
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, job
from erev_api.db.transitions import apply
from erev_api.enums import ControlResult, JobKind, TenantKind
from erev_api.events import outbox, webhooks
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry, sweeper
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import HandlerSpec, JobOutcome, RetryPolicy, job_slot, run_job
from erev_api.jobs.sweeper import requeue_undispatched
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_sandbox_tenant

_TASK = text(
    "SELECT task_name, queue_name, queueing_lock, args, status, scheduled_at, attempts "
    "FROM procrastinate_jobs WHERE id = :id"
)
_TASKS_WITH_LOCK = text("SELECT count(*) FROM procrastinate_jobs WHERE queueing_lock = :lock")
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
_TASK_FAILED = text("UPDATE procrastinate_jobs SET status = 'failed' WHERE id = :id")
_REGISTER_WORKER = text("SELECT worker_id FROM procrastinate_register_worker_v1()")
_SILENT_WORKER = text(
    "UPDATE procrastinate_workers SET last_heartbeat = now() - interval '31 seconds' "
    "WHERE id = :worker"
)
_TAKEN_BY = text(
    "UPDATE procrastinate_jobs SET status = 'doing', worker_id = :worker WHERE id = :id"
)
_UNREGISTER_WORKER = text("SELECT procrastinate_unregister_worker_v1(:worker)")
STALLED_TYPE = "https://erev.dev/problems/job-stalled"


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring))


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@contextmanager
def _uow(tenant_id: UUID, runtime: JobRuntime, clock: FrozenClock) -> Iterator[Any]:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-jobs",
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
    kind: JobKind,
    *,
    clock: FrozenClock | None = None,
    **kwargs: Any,
) -> UUID:
    with _uow(tenant_id, runtime, clock or frozen_clock()) as uow:
        row = uow.defer(kind, {"probe": True}, **kwargs)
        uow.commit()
    return UUID(str(row["id"]))


def _job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _task(tenant_id: UUID, procrastinate_job_id: int) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(_TASK, {"id": procrastinate_job_id}).mappings().one()


def _fetch(tenant_id: UUID, job_id: UUID) -> int:
    """The worker takes the job's current task: its Procrastinate row becomes ``doing``."""
    procrastinate_job_id = int(_job(tenant_id, job_id)["procrastinate_job_id"])
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    return procrastinate_job_id


def _succeeding(ran: list[UUID]) -> HandlerSpec:
    def handler(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        assert dict(params) == {"probe": True}
        ran.append(context.job_id)
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 0}})

    return HandlerSpec(handler=handler, retry=RetryPolicy())


def test_krn_job_02_defer_after_commit(tenant_id: UUID, runtime: JobRuntime) -> None:
    with _uow(tenant_id, runtime, frozen_clock()) as uow:
        row = uow.defer(JobKind.AUDIT_CHAIN_VERIFY, {})
        before_commit = uow.session.execute(
            select(job.c.state, job.c.queue, job.c.procrastinate_job_id).where(
                job.c.id == row["id"]
            )
        ).one()
        assert tuple(before_commit) == ("QUEUED", "maintenance", None)
        uow.commit()

    stored = _job(tenant_id, row["id"])
    assert stored["created_by_kind"] == "SYSTEM"
    assert stored["procrastinate_job_id"] is not None
    task = _task(tenant_id, stored["procrastinate_job_id"])
    assert (task["task_name"], task["queue_name"], task["queueing_lock"], task["status"]) == (
        "erev.run_job",
        "maintenance",
        str(row["id"]),
        "todo",
    )
    assert task["args"] == {"job_id": str(row["id"]), "tenant_id": str(tenant_id), "attempt": 1}

    with _uow(tenant_id, runtime, frozen_clock()) as uow:
        discarded = uow.defer(JobKind.AUDIT_CHAIN_VERIFY, {})
        # Left without commit: the job row and its hook are discarded.
    with tenant_session(_db(tenant_id)) as session:
        rows = select(func.count()).select_from(job).where(job.c.id == discarded["id"])
        assert session.execute(rows).scalar_one() == 0
        assert session.execute(_TASKS_WITH_LOCK, {"lock": str(discarded["id"])}).scalar_one() == 0


def test_krn_job_03_per_tenant_slots(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[UUID] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.CONTRACT_COMPUTE, _succeeding(ran))
    fifth = _defer(tenant_id, runtime, JobKind.CONTRACT_COMPUTE)
    first_task = _fetch(tenant_id, fifth)

    with ExitStack() as stack:
        # Four RUNNING jobs of the tenant hold the four slots of platform.job_concurrency 4.
        with tenant_session(_db(tenant_id)) as session:
            assert registry.job_concurrency(session, known_at=FROZEN_AT) == 4
        held = [stack.enter_context(job_slot(tenant_id, 4)) for _ in range(4)]
        assert held == [0, 1, 2, 3]

        run_job(fifth, tenant_id, attempt=1, runtime=runtime)
        waiting = _job(tenant_id, fifth)
        assert (waiting["state"], waiting["started_at"]) == ("QUEUED", None)
        assert waiting["procrastinate_job_id"] != first_task
        again = _task(tenant_id, waiting["procrastinate_job_id"])
        assert again["scheduled_at"] == FROZEN_AT + timedelta(seconds=5)
        assert (again["queueing_lock"], again["status"], again["args"]["attempt"]) == (
            str(fifth),
            "todo",
            1,
        )
        assert ran == []

        # A child of a RUNNING CLOSE_RUN runs without a slot (05 JOB-03).
        parent = _defer(tenant_id, runtime, JobKind.CLOSE_RUN)
        with tenant_session(_db(tenant_id)) as session:
            apply(
                session,
                "job",
                parent,
                to_status="RUNNING",
                set_values={"started_at": FROZEN_AT},
                expected_status="QUEUED",
            )
        child = _defer(tenant_id, runtime, JobKind.CONTRACT_COMPUTE, parent_job_id=parent)
        _fetch(tenant_id, child)
        run_job(child, tenant_id, attempt=1, runtime=runtime)
        finished = _job(tenant_id, child)
        assert (finished["state"], finished["result"]) == ("SUCCEEDED", {"counts": {"rows": 0}})
        assert (finished["started_at"], finished["finished_at"]) == (FROZEN_AT, FROZEN_AT)
        assert ran == [child]

    # The slots are free again, so the fifth job runs on its next delivery.
    _fetch(tenant_id, fifth)
    run_job(fifth, tenant_id, attempt=1, runtime=runtime)
    assert _job(tenant_id, fifth)["state"] == "SUCCEEDED"
    assert ran == [child, fifth]
    # A duplicate delivery of a finished job does nothing (05 JOB-02).
    run_job(fifth, tenant_id, attempt=1, runtime=runtime)
    assert ran == [child, fifth]


def test_krn_job_05_retry_then_failure(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        raise RuntimeError("customer detail that must not reach the job row")

    policy = RetryPolicy(max_attempts=2)
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(failing, policy))
    job_id = _defer(tenant_id, runtime, JobKind.REPORT_RUN)
    _fetch(tenant_id, job_id)

    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    retried = _job(tenant_id, job_id)
    assert retried["state"] == "QUEUED"
    task = _task(tenant_id, retried["procrastinate_job_id"])
    assert task["scheduled_at"] == FROZEN_AT + timedelta(seconds=30)
    assert task["args"]["attempt"] == 2

    _fetch(tenant_id, job_id)
    run_job(job_id, tenant_id, attempt=2, runtime=runtime)
    failed = _job(tenant_id, job_id)
    assert (failed["state"], failed["finished_at"]) == ("FAILED", FROZEN_AT)
    assert failed["problem"] == {
        "type": "about:blank",
        "title": "Job failed",
        "status": 500,
        "detail": "The job stopped with an unexpected error.",
        "instance": f"/api/v1/jobs/{job_id}",
        "code": None,
        "errors": [],
    }


def test_krn_job_01_unregistered_kind_fails_closed(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The kind has no handler for this test, whatever the process imported: a module collected
    # beside this one may import ``erev_api.worker``, which registers every handler (register
    # index 249: the assertion that it was absent failed in such a process and passed alone).
    monkeypatch.delitem(registry.HANDLERS, JobKind.SANDBOX_RESET, raising=False)
    job_id = _defer(tenant_id, runtime, JobKind.SANDBOX_RESET)
    _fetch(tenant_id, job_id)
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    failed = _job(tenant_id, job_id)
    assert (failed["state"], failed["problem"]["title"]) == ("FAILED", "Job failed")


def _jobs_of(tenant_id: UUID, kind: JobKind) -> list[Mapping[str, Any]]:
    with tenant_session(_db(tenant_id)) as session:
        return list(session.execute(select(job).where(job.c.kind == kind.value)).mappings())


def _task_failed(tenant_id: UUID, procrastinate_job_id: int) -> None:
    """The worker records the task as failed after ``run_job`` raised."""
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_TASK_FAILED, {"id": procrastinate_job_id})


@pytest.mark.control("CTL-040")
def test_krn_job_06_stranded_tasks_redispatched(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR-R-04 (D-80): a QUEUED job whose Procrastinate task failed, or stalled on a worker that
    stopped heartbeating, is dispatched again within its retry policy, and periodic deferrals no
    longer count it as pending."""
    relay = _defer(tenant_id, runtime, JobKind.OUTBOX_RELAY)
    stranded_task = _fetch(tenant_id, relay)

    def unavailable(session: Session, *, known_at: datetime) -> int:
        raise OperationalError("SELECT platform.job_concurrency", {}, ConnectionError("probe"))

    monkeypatch.setattr(registry, "job_concurrency", unavailable)
    with pytest.raises(OperationalError):
        run_job(relay, tenant_id, attempt=1, runtime=runtime)
    monkeypatch.undo()
    _task_failed(tenant_id, stranded_task)
    assert _job(tenant_id, relay)["state"] == "QUEUED"

    # Two days later SCH-03 still defers a relay while the provisioned invitation is due, and the
    # daily fan-outs defer again although stranded jobs of their kinds exist.
    later = frozen_clock(FROZEN_AT + timedelta(days=2))
    outbox.sweep(later)
    relays = _jobs_of(tenant_id, JobKind.OUTBOX_RELAY)
    assert sorted(row["state"] for row in relays) == ["QUEUED", "QUEUED"]
    for kind in (JobKind.AUDIT_CHAIN_VERIFY, JobKind.RETENTION_SWEEP):
        _task_failed(tenant_id, _fetch(tenant_id, _defer(tenant_id, runtime, kind)))
    registry.defer_for_active_tenants(
        JobKind.AUDIT_CHAIN_VERIFY, {"trigger": "SCHEDULED"}, clock=later, request_id="tests-jobs"
    )
    registry.defer_for_active_tenants(
        JobKind.RETENTION_SWEEP, {}, clock=later, request_id="tests-jobs"
    )
    for kind in (JobKind.AUDIT_CHAIN_VERIFY, JobKind.RETENTION_SWEEP):
        assert len(_jobs_of(tenant_id, kind)) == 2

    # A kind without attempts left ends FAILED instead (no handler yet: one attempt).
    assert JobKind.DEAL_PREVIEW not in registry.HANDLERS
    doomed = _defer(tenant_id, runtime, JobKind.DEAL_PREVIEW)
    _task_failed(tenant_id, _fetch(tenant_id, doomed))

    sweeper.sweep(runtime)
    redispatched = _job(tenant_id, relay)
    assert redispatched["state"] == "QUEUED"
    assert redispatched["procrastinate_job_id"] != stranded_task
    task = _task(tenant_id, redispatched["procrastinate_job_id"])
    assert (task["status"], task["queueing_lock"], task["args"]["attempt"]) == (
        "todo",
        str(relay),
        2,
    )
    assert task["scheduled_at"] == FROZEN_AT + timedelta(seconds=30)
    _fetch(tenant_id, relay)
    run_job(relay, tenant_id, attempt=2, runtime=runtime)
    assert _job(tenant_id, relay)["state"] == "SUCCEEDED"
    failed = _job(tenant_id, doomed)
    assert (failed["state"], failed["problem"]["type"], failed["problem"]["detail"]) == (
        "FAILED",
        STALLED_TYPE,
        "the worker task stopped before the job started",
    )

    # A WEBHOOK_DELIVERY task stalled in doing on a worker silent for 31 seconds is retried in
    # place through JobManager.retry_job_by_id, and the job then runs.
    ran: list[UUID] = []
    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.WEBHOOK_DELIVERY,
        HandlerSpec(handler=_succeeding(ran).handler, retry=webhooks.DELIVERY_RETRY),
    )
    delivery = _defer(tenant_id, runtime, JobKind.WEBHOOK_DELIVERY)
    delivery_task = int(_job(tenant_id, delivery)["procrastinate_job_id"])
    with tenant_session(_db(tenant_id)) as session:
        worker = session.execute(_REGISTER_WORKER).scalar_one()
        session.execute(_SILENT_WORKER, {"worker": worker})
        session.execute(_TAKEN_BY, {"worker": worker, "id": delivery_task})
    try:
        sweeper.sweep(runtime)
        retried = _task(tenant_id, delivery_task)
        assert (retried["status"], retried["attempts"]) == ("todo", 1)
        assert _job(tenant_id, delivery)["procrastinate_job_id"] == delivery_task
        _fetch(tenant_id, delivery)
        run_job(delivery, tenant_id, attempt=1, runtime=runtime)
        assert (_job(tenant_id, delivery)["state"], ran) == ("SUCCEEDED", [delivery])
    finally:
        with tenant_session(_db(tenant_id)) as session:
            session.execute(_UNREGISTER_WORKER, {"worker": worker})


def test_krn_job_06_sweeper_requeues_undispatched_jobs(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lost(**_: object) -> None:
        raise ConnectionError("dispatch lost")

    # The after-commit dispatch fails; the commit stands (DG-KRN-UOW-02).
    monkeypatch.setattr(registry, "_dispatch_hook", lost)
    stale = _defer(
        tenant_id,
        runtime,
        JobKind.AUDIT_CHAIN_VERIFY,
        clock=frozen_clock(FROZEN_AT - timedelta(seconds=61)),
    )
    recent = _defer(
        tenant_id,
        runtime,
        JobKind.AUDIT_CHAIN_VERIFY,
        clock=frozen_clock(FROZEN_AT - timedelta(seconds=30)),
    )
    monkeypatch.undo()
    assert _job(tenant_id, stale)["procrastinate_job_id"] is None

    assert requeue_undispatched(frozen_clock()) >= 1
    swept = _job(tenant_id, stale)
    assert swept["state"] == "QUEUED"
    assert swept["procrastinate_job_id"] is not None
    task = _task(tenant_id, swept["procrastinate_job_id"])
    assert (task["queueing_lock"], task["queue_name"]) == (str(stale), "maintenance")
    assert _job(tenant_id, recent)["procrastinate_job_id"] is None


def _job_events(tenant_id: UUID, job_id: UUID) -> list[tuple[str, str, str, Any]]:
    """``(action, actor kind, request id, after)`` of a job's audit events, in chain order."""
    with tenant_session(_db(tenant_id)) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.actor_kind,
                audit_event.c.request_id,
                audit_event.c.after,
            )
            .where(audit_event.c.object_type == "job", audit_event.c.object_id == job_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [(str(action), str(kind), str(request), after) for action, kind, request, after in rows]


def _chain_passes(tenant_id: UUID, runtime: JobRuntime) -> bool:
    """The tenant's audit chain verifies to its head: the appends outside a unit of work chained
    their events as ``UnitOfWork.commit`` does."""
    assert runtime.keyring is not None
    with tenant_session(_db(tenant_id)) as session:
        result = verify_tenant_chain(session, tenant_id=tenant_id, keyring=runtime.keyring)
    return result.result is ControlResult.PASS


def test_r_50_a_defer_writes_job_start_in_the_deferring_transaction(
    tenant_id: UUID, runtime: JobRuntime
) -> None:
    """04 T-PLT-27 rev 1.106 (supervisor ruling R-50 (a); dev-guide DG-KRN-JOB-02): ``defer``
    buffers ``job.start`` on the unit of work that inserts the row — its principal, its request
    id, the job's facts and never its params — so the event commits or is discarded with the job.
    A transport kind of the outbox writes none (04 T-INT-03: the originating command is audited).
    Until this ruling no deferral left an audit event."""
    subject = new_id()
    with _uow(tenant_id, runtime, frozen_clock()) as uow:
        row = uow.defer(
            JobKind.REPORT_RUN,
            {"probe": True, "note": "never audited"},
            priority=3,
            subject_type="report_run",
            subject_id=subject,
        )
        relay = uow.defer(JobKind.OUTBOX_RELAY, {})
        assert [event["action"] for event in uow.audit_events] == ["job.start"]
        assert _job_events(tenant_id, row["id"]) == []  # nothing before the commit
        uow.commit()
    assert _job_events(tenant_id, row["id"]) == [
        (
            "job.start",
            "SYSTEM",
            "tests-jobs",
            {
                "kind": "REPORT_RUN",
                "state": "QUEUED",
                "queue": "reports",
                "priority": 3,
                "parent_job_id": None,
                "subject_type": "report_run",
                "subject_id": str(subject),
            },
        )
    ]
    assert _job(tenant_id, relay["id"])["state"] == "QUEUED"
    assert _job_events(tenant_id, relay["id"]) == []

    # A deferral left without commit leaves neither the job nor its event.
    with _uow(tenant_id, runtime, frozen_clock()) as uow:
        discarded = uow.defer(JobKind.REPORT_RUN, {})
    assert _job_events(tenant_id, discarded["id"]) == []
    assert _chain_passes(tenant_id, runtime)


def test_r_50_a_the_terminal_state_writes_job_finish(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-PLT-27 rev 1.106 (R-50 (a); dev-guide DG-KRN-JOB-05): the transaction that records a
    terminal state writes ``job.finish`` as SYSTEM under ``job-<id>`` with the state and the slug
    of the problem. A retry, a duplicate delivery and a transport kind write nothing."""
    ran: list[UUID] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.CONTRACT_COMPUTE, _succeeding(ran))
    done = _defer(tenant_id, runtime, JobKind.CONTRACT_COMPUTE)
    _fetch(tenant_id, done)
    run_job(done, tenant_id, attempt=1, runtime=runtime)
    assert [
        (action, kind, request) for action, kind, request, _ in _job_events(tenant_id, done)
    ] == [
        ("job.start", "SYSTEM", "tests-jobs"),
        ("job.finish", "SYSTEM", f"job-{done}"),
    ]
    finish = _job_events(tenant_id, done)[-1][3]
    assert finish == {"kind": "CONTRACT_COMPUTE", "state": "SUCCEEDED", "problem": None}
    run_job(done, tenant_id, attempt=1, runtime=runtime)  # duplicate delivery (05 JOB-02)
    assert len(_job_events(tenant_id, done)) == 2

    # An unexpected error: the first attempt returns the job to QUEUED and writes nothing; the
    # last one ends it FAILED, and the event names the problem as the job row does.
    def failing(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        raise RuntimeError("customer detail that must not reach the audit event")

    monkeypatch.setitem(
        registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(failing, RetryPolicy(max_attempts=2))
    )
    retried = _defer(tenant_id, runtime, JobKind.REPORT_RUN)
    _fetch(tenant_id, retried)
    run_job(retried, tenant_id, attempt=1, runtime=runtime)
    assert _job(tenant_id, retried)["state"] == "QUEUED"
    assert [action for action, *_ in _job_events(tenant_id, retried)] == ["job.start"]
    _fetch(tenant_id, retried)
    run_job(retried, tenant_id, attempt=2, runtime=runtime)
    assert _job_events(tenant_id, retried)[-1] == (
        "job.finish",
        "SYSTEM",
        f"job-{retried}",
        {"kind": "REPORT_RUN", "state": "FAILED", "problem": "about:blank"},
    )

    # A catalogued problem is named by its slug.
    def refusing(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        raise Problem("not-found")

    monkeypatch.setitem(
        registry.HANDLERS, JobKind.EVIDENCE_PACK, HandlerSpec(refusing, RetryPolicy())
    )
    refused = _defer(tenant_id, runtime, JobKind.EVIDENCE_PACK)
    _fetch(tenant_id, refused)
    run_job(refused, tenant_id, attempt=1, runtime=runtime)
    assert _job_events(tenant_id, refused)[-1][3] == {
        "kind": "EVIDENCE_PACK",
        "state": "FAILED",
        "problem": "not-found",
    }

    # Positive control for the exception: a relay runs to SUCCEEDED and writes neither event.
    monkeypatch.setitem(registry.HANDLERS, JobKind.OUTBOX_RELAY, _succeeding(ran))
    relay = _defer(tenant_id, runtime, JobKind.OUTBOX_RELAY)
    _fetch(tenant_id, relay)
    run_job(relay, tenant_id, attempt=1, runtime=runtime)
    assert _job(tenant_id, relay)["state"] == "SUCCEEDED"
    assert _job_events(tenant_id, relay) == []
    assert _chain_passes(tenant_id, runtime)


def test_r_50_a_the_scheduler_fan_out_writes_job_start_as_system(
    tenant_id: UUID, runtime: JobRuntime
) -> None:
    """04 T-PLT-27 rev 1.106 (R-50 (a)): a job the scheduler defers has no command and no unit of
    work; its ``job.start`` is appended as SYSTEM under the sweep's request id in the transaction
    that inserts and dispatches it, and the chain still verifies. A second fan-out while the job
    is pending defers nothing and writes nothing."""
    before = {row["id"] for row in _jobs_of(tenant_id, JobKind.RETENTION_SWEEP)}
    registry.defer_for_active_tenants(
        JobKind.RETENTION_SWEEP, {}, clock=frozen_clock(), request_id="tests-sweep"
    )
    (swept,) = [
        row for row in _jobs_of(tenant_id, JobKind.RETENTION_SWEEP) if row["id"] not in before
    ]
    assert (swept["state"], swept["created_by_kind"]) == ("QUEUED", "SYSTEM")
    assert swept["procrastinate_job_id"] is not None
    expected = (
        "job.start",
        "SYSTEM",
        "tests-sweep",
        {
            "kind": "RETENTION_SWEEP",
            "state": "QUEUED",
            "queue": "maintenance",
            "priority": 0,
            "parent_job_id": None,
            "subject_type": None,
            "subject_id": None,
        },
    )
    assert _job_events(tenant_id, swept["id"]) == [expected]
    registry.defer_for_active_tenants(
        JobKind.RETENTION_SWEEP, {}, clock=frozen_clock(), request_id="tests-sweep"
    )
    assert {row["id"] for row in _jobs_of(tenant_id, JobKind.RETENTION_SWEEP)} == {
        *before,
        swept["id"],
    }
    assert _job_events(tenant_id, swept["id"]) == [expected]
    assert _chain_passes(tenant_id, runtime)


def _isolated_failure(log_stream: io.StringIO, event: str, tenant_id: UUID) -> dict[str, Any]:
    """The one ``event`` the isolation logged for ``tenant_id`` (dev-guide DG-KRN-JOB-06 rev
    1.183): error level, the exception's class, and the place it was raised - a module of this
    code base and a line, never its message. Only the lines of the test's own tenant are counted:
    the database is shared (DG-TST-13), and a tenant that another test left without a chain head
    fails the same fan-out or sweep with a line of its own."""
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    (failure,) = [
        line for line in lines if line["event"] == event and line["tenant_id"] == str(tenant_id)
    ]
    assert failure["level"] == "error" and failure["error_class"]
    module, _, line = str(failure["error_at"]).rpartition(":")
    assert module.split(".")[0] == "erev_api" and line.isdigit(), failure["error_at"]
    return failure


def test_r_50_a_a_tenant_that_cannot_be_audited_never_stops_the_fan_out(
    tenant_id: UUID, runtime: JobRuntime, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """dev-guide DG-KRN-JOB-02 rev 1.89: the scheduler's ``job.start`` is written in the tenant
    transaction that inserts and dispatches the job, so a tenant whose audit chain cannot take the
    event (no chain head: DB-09 fails closed) gets no job — and the tenants after it are served.
    Without the isolation the first such tenant ended the fan-out for every later one."""
    broken = insert_sandbox_tenant(keyring)  # ACTIVE, without the chain head provisioning writes
    later = tenant_id_of(tenant_factory(keyring=keyring))
    assert str(tenant_id) < str(broken) < str(later)  # the fan-out serves tenants in id order
    registry.defer_for_active_tenants(
        JobKind.RETENTION_SWEEP, {}, clock=frozen_clock(), request_id="tests-isolation"
    )
    assert _jobs_of(broken, JobKind.RETENTION_SWEEP) == []
    failure = _isolated_failure(log_stream, "job.fan_out_failed", broken)
    assert failure["job_kind"] == "RETENTION_SWEEP"
    for served in (tenant_id, later):
        (swept,) = _jobs_of(served, JobKind.RETENTION_SWEEP)
        assert (swept["state"], swept["procrastinate_job_id"] is not None) == ("QUEUED", True)
        assert [
            (action, request) for action, _, request, _ in _job_events(served, swept["id"])
        ] == [("job.start", "tests-isolation")]
        assert _chain_passes(served, runtime)


def test_dependencies_wait_without_spending_attempts_or_taking_a_slot(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real queued child gates a real queued parent across repeated/stale deliveries."""
    ran: list[UUID] = []
    checks: list[UUID] = []
    monkeypatch.setitem(registry.HANDLERS, JobKind.AUDIT_CHAIN_VERIFY, _succeeding(ran))
    dependency = _defer(tenant_id, runtime, JobKind.AUDIT_CHAIN_VERIFY)

    def ready(session: Session, job_id: UUID, params: Mapping[str, Any]) -> bool:
        assert params == {"probe": True}
        checks.append(job_id)
        return session.scalar(select(job.c.state).where(job.c.id == dependency)) == "SUCCEEDED"

    success = _succeeding(ran)
    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.EVIDENCE_PACK,
        HandlerSpec(handler=success.handler, retry=RetryPolicy(max_attempts=1), ready=ready),
    )
    parent = _defer(tenant_id, runtime, JobKind.EVIDENCE_PACK)
    first_task = _fetch(tenant_id, parent)
    real_slot = registry.job_slot

    def forbidden_slot(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a dependency wait must not acquire a tenant slot")

    monkeypatch.setattr(registry, "job_slot", forbidden_slot)
    for index in range(7):
        delivery = first_task if index == 0 else _fetch(tenant_id, parent)
        run_job(parent, tenant_id, attempt=1, runtime=runtime, delivered_task_id=delivery)
        waiting = _job(tenant_id, parent)
        assert (waiting["state"], waiting["started_at"], waiting["problem"]) == (
            "QUEUED",
            None,
            None,
        )
        assert waiting["procrastinate_job_id"] != delivery
        task = _task(tenant_id, waiting["procrastinate_job_id"])
        assert task["args"]["attempt"] == 1
        assert task["scheduled_at"] == runtime.clock.now() + timedelta(seconds=30)
    assert ran == [] and checks == [parent] * 7
    # An old delivery neither rechecks dependencies nor supersedes the current task.
    latest = _job(tenant_id, parent)["procrastinate_job_id"]
    run_job(parent, tenant_id, attempt=1, runtime=runtime, delivered_task_id=first_task)
    assert len(checks) == 7
    assert _job(tenant_id, parent)["procrastinate_job_id"] == latest
    monkeypatch.setattr(registry, "job_slot", real_slot)
    child_task = _fetch(tenant_id, dependency)
    run_job(dependency, tenant_id, attempt=1, runtime=runtime, delivered_task_id=child_task)
    delivery = _fetch(tenant_id, parent)
    run_job(parent, tenant_id, attempt=1, runtime=runtime, delivered_task_id=delivery)
    assert ran == [dependency, parent]
    assert _job(tenant_id, parent)["state"] == "SUCCEEDED"
    with tenant_session(_db(tenant_id), read_only=True) as session:
        events = (
            session.execute(select(audit_event.c.action).where(audit_event.c.object_id == parent))
            .scalars()
            .all()
        )
    assert sorted(events) == ["job.finish", "job.start"]


def test_failed_dependency_settles_parent_and_its_failure_hook_without_handler(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[UUID] = []
    failures: list[str] = []

    def ready(session: Session, job_id: UUID, params: Mapping[str, Any]) -> bool:
        raise Problem("validation-failed", "A retained source report failed.")

    def failed(uow: Any, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
        failures.append(str(problem["detail"]))

    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.EVIDENCE_PACK,
        HandlerSpec(
            handler=_succeeding(ran).handler,
            retry=RetryPolicy(max_attempts=3),
            ready=ready,
            on_failure=failed,
            failure_hook_required=True,
        ),
    )
    parent = _defer(tenant_id, runtime, JobKind.EVIDENCE_PACK)
    delivery = _fetch(tenant_id, parent)
    run_job(parent, tenant_id, attempt=1, runtime=runtime, delivered_task_id=delivery)
    stored = _job(tenant_id, parent)
    assert stored["state"] == "FAILED"
    assert stored["problem"]["detail"] == "A retained source report failed."
    assert ran == [] and failures == ["A retained source report failed."]
    run_job(parent, tenant_id, attempt=1, runtime=runtime, delivered_task_id=delivery)
    assert failures == ["A retained source report failed."]


@pytest.mark.parametrize("broken", ["exception", "not-bool"])
def test_broken_readiness_keeps_queued_job_for_existing_stranded_recovery(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    ran: list[UUID] = []

    def ready(session: Session, job_id: UUID, params: Mapping[str, Any]) -> bool:
        if broken == "exception":
            raise RuntimeError("dependency reader unavailable")
        return None  # type: ignore[return-value] - exercise an invalid hook at runtime

    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.EVIDENCE_PACK,
        HandlerSpec(handler=_succeeding(ran).handler, retry=RetryPolicy(), ready=ready),
    )
    parent = _defer(tenant_id, runtime, JobKind.EVIDENCE_PACK)
    delivery = _fetch(tenant_id, parent)
    with pytest.raises(RuntimeError if broken == "exception" else TypeError):
        run_job(parent, tenant_id, attempt=1, runtime=runtime, delivered_task_id=delivery)
    stored = _job(tenant_id, parent)
    assert (stored["state"], stored["procrastinate_job_id"], stored["started_at"]) == (
        "QUEUED",
        delivery,
        None,
    )
    assert ran == []
