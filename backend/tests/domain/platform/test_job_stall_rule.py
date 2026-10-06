"""An attempt keeps nothing once it has lost its job (05 JOB-04, JOB-06 rev 1.200; dev-guide
DG-KRN-JOB-04, DG-KRN-JOB-06, DG-KRN-DB-08, DG-KRN-UOW-02 rev 1.266; PRD NTF-05 rev 1.191;
BUILD_SPEC PLF-22; item JOB-STALL-COMMIT-RACE-1).

The sweeper stops a RUNNING job that was silent for ten minutes. A handler's work and its job's
end are separate transactions, so a worker that was alive and silent - one long transaction -
had its job ended FAILED beside it and committed its work under that job: measured on
2026-10-02 with the commit of an import. Three statements of the kernel close it for every
handler: a beat is its attempt's, a unit of work holds the job's lock and writes its heartbeat
at its commit, and the sweeper stops a job only while it holds that lock.

The tests play the worker as ``test_job_monitoring`` does. A handler of the test stands for the
product's: the rule is the kernel's and holds whatever a handler does inside its unit of work.
"""

from __future__ import annotations

import io
import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, notification, outbox_message
from erev_api.db.transitions import apply
from erev_api.enums import JobKind, OutboxTopic, PrincipalKind
from erev_api.events import outbox
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import (
    PROGRESS_INTERVAL,
    JobAttempt,
    JobContext,
    JobLost,
    JobRuntime,
    system_unit_of_work,
)
from erev_api.jobs.registry import HandlerSpec, JobOutcome, RetryPolicy
from erev_api.jobs.sweeper import fail_stalled
from erev_api.uow import UnitOfWork
from sqlalchemy import select, text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.plans import sent
from support.principals import Member, member

STALL = timedelta(minutes=10, seconds=1)
KIND = JobKind.REPORT_RUN  # a kind a member starts; the test's handler takes its place
STOPPED = (
    "Report run failed at attempt 1: no heartbeat for 10 minutes. The job was stopped; what it "
    "had not committed by then is not kept."
)
# The tables whose rows refer to a job by foreign key, as the catalogue names them.
REFERRING = (
    "audit_chain_verification",
    "close_run",
    "contract_computation",
    "evidence_pack",
    "import_upload",
    "job",
    "journal_run",
    "migration_batch",
    "report_run",
    "ssp_calculator_run",
    "tenant_snapshot",
)
_REFERRING = text(
    "SELECT DISTINCT r.relname::text FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid "
    "WHERE c.contype = 'f' AND c.confrelid = 'erev.job'::regclass AND NOT r.relispartition "
    "ORDER BY 1"
)
# The lock a row that refers to a job takes on the job's row when it is inserted.
_KEY_SHARE = text(
    "SELECT 1 FROM erev.job WHERE tenant_id = :tenant_id AND id = :job_id FOR KEY SHARE NOWAIT"
)
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
_TASKS = text("SELECT count(*) FROM procrastinate_jobs WHERE args ->> 'job_id' = :job_id")
RUNBOOK = Path(__file__).resolve().parents[4] / "docs" / "guides" / "runbook.md"
# The statement RB-07 gives an operator to find the transaction of a job that is passed over.
_HOLDERS = re.compile(r"`(select l\.pid, a\.xact_start[^`]+)`")


@pytest.fixture
def lena(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> Member:
    return member(keyring, clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _start(someone: Member, kind: JobKind = KIND, params: Mapping[str, Any] | None = None) -> UUID:
    """The member starts a job of ``kind``; its first task is deferred."""
    with tenant_session(_db(someone.tenant_id)) as session:
        row = registry.insert_job(
            session,
            kind,
            dict(params or {}),
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
        )
        registry.dispatch(
            session,
            job_id=row["id"],
            tenant_id=someone.tenant_id,
            queue=str(row["queue"]),
            now=FROZEN_AT,
        )
    return UUID(str(row["id"]))


def _job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _fetch(tenant_id: UUID, job_id: UUID) -> int:
    """A worker takes the job's current task: its Procrastinate row becomes ``doing``."""
    task_id = int(_job(tenant_id, job_id)["procrastinate_job_id"])
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_FETCHED, {"id": task_id})
    return task_id


def _begin(tenant_id: UUID, job_id: UUID, *, heartbeat: datetime) -> int:
    """A worker takes the current task and starts the attempt, last heartbeat ``heartbeat``."""
    task_id = _fetch(tenant_id, job_id)
    with tenant_session(_db(tenant_id)) as session:
        apply(
            session,
            "job",
            job_id,
            to_status="RUNNING",
            set_values={
                "started_at": heartbeat,
                "updated_at": heartbeat,
                "updated_by": None,
                "updated_by_kind": PrincipalKind.SYSTEM.value,
            },
            expected_status="QUEUED",
        )
    return task_id


def _work(uow: UnitOfWork, job_id: UUID | None = None) -> None:
    """What a handler writes in its unit of work, as far as the kernel is concerned: a row - a
    job of its own, deferred with ``job.start`` in the unit's audit buffer."""
    uow.defer(JobKind.RETENTION_SWEEP, {}, parent_job_id=job_id)


def _kept(tenant_id: UUID, parent: UUID | None = None) -> list[str]:
    """The states of the rows ``_work`` left in the workspace (under ``parent``)."""
    statement = select(job.c.state).where(job.c.kind == JobKind.RETENTION_SWEEP.value)
    if parent is not None:
        statement = statement.where(job.c.parent_job_id == parent)
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return [str(state) for state in session.scalars(statement)]


def _tasks(tenant_id: UUID, job_id: UUID) -> int:
    """The Procrastinate tasks ever dispatched for the job: one an attempt."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        return int(session.execute(_TASKS, {"job_id": str(job_id)}).scalar_one())


def _notifications(someone: Member) -> list[tuple[Any, ...]]:
    with tenant_session(_db(someone.tenant_id), read_only=True) as session:
        rows = session.execute(
            select(
                notification.c.title,
                notification.c.body,
                notification.c.subject_type,
                notification.c.subject_id,
            )
            .where(
                notification.c.recipient_membership_id == someone.membership_id,
                notification.c.kind == "JOB_FAILED",
            )
            .order_by(notification.c.created_at)
        ).all()
    return [tuple(row) for row in rows]


def _lines(log_stream: io.StringIO, event: str, job_id: UUID) -> list[dict[str, Any]]:
    lines = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    return [line for line in lines if line["event"] == event and line.get("job_id") == str(job_id)]


def _never_runs(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    raise AssertionError("the sweeper settles attempts without running the handler")


def _first(statements: list[str], fragment: str, start: int = 0) -> int:
    """The index of the first statement from ``start`` on that contains ``fragment``."""
    for index in range(start, len(statements)):
        if fragment in statements[index]:
            return index
    raise AssertionError(f"no statement from {start} on contains {fragment!r}: {statements}")


@pytest.mark.parametrize(
    ("max_attempts", "names_the_job"),
    [(1, False), (3, False), (1, True)],
    ids=["last-attempt", "attempts-left", "holds-the-row-too"],
)
def test_job_06_a_job_with_a_transaction_open_is_passed_over_and_ends_well(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
    max_attempts: int,
    names_the_job: bool,
) -> None:
    """The measured case, turned round. A handler is ten minutes and a second inside ONE
    transaction, without a beat. The sweeper passes the job over at every pass and says so in the
    log - job, kind, attempt and how long the job has been silent; with attempts left it
    dispatches no second attempt beside the first. The work commits, the job ends SUCCEEDED
    under the task that started it, and nobody is told of a failure. Before, the first pass
    ended the job FAILED - or handed it to a second attempt - and the commit went through.

    In the third case the unit of work holds the job's ROW as well: a row it inserted refers
    to the job. Such a job was skipped before, without a word; the pass is told all the same,
    because the sweeper asks for the lock before the row."""
    clock = frozen_clock(FROZEN_AT)
    runtime = _runtime(app_settings, keyring, clock)
    during: list[tuple[str, int]] = []

    def handler(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        with jc.unit_of_work() as uow:
            _work(uow, jc.job_id if names_the_job else None)
            for silent in (STALL, timedelta(minutes=1)):
                clock.advance(silent)
                fail_stalled(runtime)
                row = _job(jc.tenant_id, jc.job_id)
                during.append((str(row["state"]), int(row["procrastinate_job_id"])))
            uow.commit()
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 1}})

    monkeypatch.setitem(
        registry.HANDLERS, KIND, HandlerSpec(handler, RetryPolicy(max_attempts=max_attempts))
    )
    job_id = _start(lena)
    task_id = _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    assert during == [("RUNNING", task_id)] * 2
    done = _job(lena.tenant_id, job_id)
    assert (done["state"], done["procrastinate_job_id"], done["problem"], done["result"]) == (
        "SUCCEEDED",
        task_id,
        None,
        {"counts": {"rows": 1}},
    )
    assert _tasks(lena.tenant_id, job_id) == 1
    assert _kept(lena.tenant_id, job_id if names_the_job else None) == ["QUEUED"]
    assert _notifications(lena) == []
    passes = _lines(log_stream, "job.sweep_passed_over", job_id)
    assert [
        (line["level"], line["job_kind"], line["attempt"], line["silent_seconds"])
        for line in passes
    ] == [("info", "REPORT_RUN", 1, 601), ("info", "REPORT_RUN", 1, 661)]
    assert _lines(log_stream, "job.failed", job_id) == []


def test_job_06_a_unit_of_work_of_a_stopped_job_is_refused_at_its_beginning(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """Silent for ten minutes OUTSIDE a transaction, a job is stopped although its worker lives.
    The unit of work its handler opens next is refused where it begins - not after its work, at
    the commit -, the kernel records nothing for the attempt on a row that is no longer its
    own, and the member reads what the sweeper can know: the job was stopped, and what it had
    not committed by then is not kept."""
    clock = frozen_clock(FROZEN_AT)
    runtime = _runtime(app_settings, keyring, clock)
    reached: list[str] = []

    def handler(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        clock.advance(STALL)
        fail_stalled(runtime)
        reached.append(str(_job(jc.tenant_id, jc.job_id)["state"]))
        with jc.unit_of_work() as uow:
            reached.append("inside the unit of work")
            _work(uow, jc.job_id)
            uow.commit()
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 1}})

    monkeypatch.setitem(registry.HANDLERS, KIND, HandlerSpec(handler, RetryPolicy(max_attempts=1)))
    job_id = _start(lena)
    _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    assert reached == ["FAILED"]
    failed = _job(lena.tenant_id, job_id)
    assert (failed["state"], failed["finished_at"], failed["result"]) == (
        "FAILED",
        FROZEN_AT + STALL,
        None,
    )
    assert failed["problem"]["detail"] == "no heartbeat for 10 minutes"
    assert _kept(lena.tenant_id) == []
    (lost,) = _lines(log_stream, "job.attempt_lost", job_id)
    assert (lost["level"], lost["job_kind"], lost["attempt"]) == ("warning", "REPORT_RUN", 1)
    assert _notifications(lena) == [("Job failed: Report run", STOPPED, "job", job_id)]


def test_job_06_a_commit_under_a_job_that_was_moved_keeps_nothing(
    lena: Member, app_settings: Settings, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guarantee at the commit. Nothing of the product moves a RUNNING job while a unit of
    work of it is open - the sweeper passes such a job over -, and the commit does not rest on
    that: it writes its heartbeat on the job's row while the job is the attempt's, and with no
    row there is no commit. A handler that takes the refusal and leaves its block normally
    commits nothing by that either: the transaction ended where the commit failed."""
    clock = frozen_clock(FROZEN_AT)
    runtime = _runtime(app_settings, keyring, clock)
    reached: list[str] = []

    def handler(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        with jc.unit_of_work() as uow:
            _work(uow)
            with tenant_session(_db(jc.tenant_id)) as session:
                apply(
                    session,
                    "job",
                    jc.job_id,
                    to_status="CANCELLED",
                    set_values={"finished_at": FROZEN_AT},
                    expected_status="RUNNING",
                )
            with pytest.raises(JobLost) as refused:
                uow.commit()
            assert refused.value.job_id == jc.job_id
        reached.append("left the block")
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 1}})

    monkeypatch.setitem(registry.HANDLERS, KIND, HandlerSpec(handler, RetryPolicy(max_attempts=1)))
    job_id = _start(lena)
    _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    assert reached == ["left the block"]
    moved = _job(lena.tenant_id, job_id)
    assert (moved["state"], moved["result"]) == ("CANCELLED", None)
    assert _kept(lena.tenant_id) == []


def test_job_04_a_beat_of_a_lost_attempt_is_refused_and_leaves_its_successors_row(
    lena: Member, app_settings: Settings, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A heartbeat and a progress write are their attempt's. After the sweeper handed the job
    to a second attempt, the first attempt's beat finds no row, raises, and leaves the row the
    second attempt runs under as it is; the first attempt's end records nothing either. Before,
    a beat moved the row's heartbeat and progress whatever its state and whichever attempt
    called - a stopped attempt kept its successor from ever being judged silent."""
    clock = frozen_clock(FROZEN_AT)
    runtime = _runtime(app_settings, keyring, clock)
    second_started = FROZEN_AT + timedelta(minutes=20)
    seen: list[Any] = []

    def handler(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        clock.advance(timedelta(minutes=1))
        jc.heartbeat()  # the attempt's own job: taken
        seen.append(_job(jc.tenant_id, jc.job_id)["updated_at"])
        clock.advance(STALL)
        fail_stalled(runtime)  # QUEUED again, a second attempt dispatched ...
        seen.append(_begin(jc.tenant_id, jc.job_id, heartbeat=second_started))  # ... and started
        with pytest.raises(JobLost):
            jc.heartbeat()
        clock.advance(PROGRESS_INTERVAL)
        with pytest.raises(JobLost):
            jc.progress(7, 9)
        return JobOutcome(state="SUCCEEDED", result={"counts": {"attempt": 1}})

    monkeypatch.setitem(registry.HANDLERS, KIND, HandlerSpec(handler, RetryPolicy(max_attempts=2)))
    job_id = _start(lena)
    first_task = _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    heartbeat, second_task = seen
    assert heartbeat == FROZEN_AT + timedelta(minutes=1)
    assert second_task != first_task
    row = _job(lena.tenant_id, job_id)
    assert (
        row["state"],
        row["procrastinate_job_id"],
        row["updated_at"],
        row["progress_done"],
        row["progress_total"],
        row["result"],
    ) == ("RUNNING", second_task, second_started, 0, None, None)


def test_job_06_a_unit_that_begins_during_a_settlement_waits_and_is_refused(
    lena: Member, app_settings: Settings, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The settlement holds the job's lock, exclusive, to its own commit. A unit of work of the
    attempt that begins meanwhile - the worker was alive between two transactions - waits for
    it at the lock, in its first statement, and is refused when the settlement has committed:
    it never read the job as RUNNING, and its work never began. The settlement is held open
    here in its failure hook; the wait is read from ``pg_stat_activity`` by both backends."""
    job_id = _start(lena)
    task_id = _begin(lena.tenant_id, job_id, heartbeat=FROZEN_AT)
    worker = replace(
        _runtime(app_settings, keyring, frozen_clock(FROZEN_AT)),
        attempt=JobAttempt(job_id=job_id, tenant_id=lena.tenant_id, task_id=task_id),
    )
    outcome: list[str] = []
    waited: list[str] = []
    failures: list[BaseException] = []

    def a_unit_of_work() -> None:
        try:
            with system_unit_of_work(
                worker, system_principal(lena.tenant_id), request_id=f"job-{job_id}"
            ) as uow:
                outcome.append("began")
                _work(uow, job_id)
                uow.commit()
        except JobLost:
            outcome.append("refused")
        except BaseException as error:
            failures.append(error)

    unit = threading.Thread(target=a_unit_of_work, name="attempt-1")

    def hook(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
        # The settlement is in flight: it holds the job's row and the job's lock.
        try:
            with observing_checkouts() as backends:
                unit.start()
                _, statement = await_lock_wait(
                    uow.session,
                    holder_pid=backend_pid(uow.session),
                    backends=backends,
                    timeout=20.0,
                    expect="pg_advisory_xact_lock_shared",
                )
            waited.append(statement)
        except BaseException as error:
            failures.append(error)

    monkeypatch.setitem(
        registry.HANDLERS,
        KIND,
        HandlerSpec(_never_runs, RetryPolicy(max_attempts=1), on_failure=hook),
    )
    fail_stalled(_runtime(app_settings, keyring, frozen_clock(FROZEN_AT + STALL)))
    unit.join(timeout=30)

    assert failures == []
    assert not unit.is_alive()
    assert len(waited) == 1 and "pg_advisory_xact_lock_shared" in waited[0]
    assert outcome == ["refused"]
    assert _job(lena.tenant_id, job_id)["state"] == "FAILED"
    assert _kept(lena.tenant_id) == []


def test_dg_krn_db_08_a_jobs_unit_of_work_takes_its_locks_in_one_order(
    lena: Member, app_settings: Settings, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read from the statements the engine sent: the job's lock is the first statement of a
    job's unit of work and the read of the job's row the second; the heartbeat on the job's
    row is the last statement before the audit chain's head is locked, and the chain's events
    follow. Job row, then chain head: the order in which the settlement of a job takes them."""
    statements: list[str] = []

    def handler(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        with sent() as seen, jc.unit_of_work() as uow:
            _work(uow, jc.job_id)
            uow.commit()
        statements.extend(statement for statement, _ in seen)
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 1}})

    monkeypatch.setitem(registry.HANDLERS, KIND, HandlerSpec(handler, RetryPolicy(max_attempts=1)))
    job_id = _start(lena)
    _fetch(lena.tenant_id, job_id)
    runtime = _runtime(app_settings, keyring, frozen_clock(FROZEN_AT))
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    assert _job(lena.tenant_id, job_id)["state"] == "SUCCEEDED"
    lock = _first(statements, "pg_advisory_xact_lock_shared")
    read = _first(statements, "FROM erev.job", lock)
    work = _first(statements, "INSERT INTO erev.job", read)
    beat = _first(statements, "UPDATE erev.job SET updated_at=", work)
    head = _first(statements, "FROM erev.audit_chain_head", beat)
    event = _first(statements, "INSERT INTO erev.audit_event", head)
    assert (read, head) == (lock + 1, beat + 1)
    assert lock < work < beat < event
    assert "FOR UPDATE" in statements[head]
    # A plain update: it names no lock of its own and returns the row it wrote.
    assert "FOR " not in statements[beat] and "RETURNING erev.job.id" in statements[beat]
    # Nothing of the unit of work was sent before its lock but the transaction's own set-up.
    assert not [s for s in statements[:lock] if "INSERT" in s or "UPDATE" in s]


def test_job_06_a_transaction_in_another_workspace_holds_the_lock_and_beats_first(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """A load fills a sandbox: its units of work run in a workspace where the job's row can be
    neither read nor written, so the heartbeat at the commit does not reach them. Such a unit
    takes the job's lock and then beats in the job's own workspace before it does anything:
    while it is open the sweeper passes the job over, and once the job is stopped the next
    such unit - and a transaction that enlists by itself, as a copy step does - is refused
    before its first statement of work."""
    other = member(keyring, frozen_clock(FROZEN_AT))
    monkeypatch.setitem(
        registry.HANDLERS, KIND, HandlerSpec(_never_runs, RetryPolicy(max_attempts=1))
    )
    job_id = _start(lena)
    task_id = _begin(lena.tenant_id, job_id, heartbeat=FROZEN_AT)
    clock = frozen_clock(FROZEN_AT + timedelta(minutes=3))
    runtime = _runtime(app_settings, keyring, clock)
    worker = replace(
        runtime, attempt=JobAttempt(job_id=job_id, tenant_id=lena.tenant_id, task_id=task_id)
    )
    sandbox = system_principal(other.tenant_id)

    with (
        sent() as seen,
        system_unit_of_work(worker, sandbox, request_id=f"job-{job_id}-recompute") as uow,
    ):
        opening = [statement for statement, _ in seen]
        assert _job(lena.tenant_id, job_id)["updated_at"] == FROZEN_AT + timedelta(minutes=3)
        clock.advance(STALL)
        fail_stalled(runtime)
        assert _job(lena.tenant_id, job_id)["state"] == "RUNNING"
        _work(uow)
        uow.commit()
    lock = _first(opening, "pg_advisory_xact_lock_shared")
    assert _first(opening, "UPDATE erev.job SET updated_at=", lock) > lock
    assert not [s for s in opening[:lock] if "INSERT" in s or "UPDATE" in s]
    (passed,) = _lines(log_stream, "job.sweep_passed_over", job_id)
    assert (passed["job_kind"], passed["attempt"], passed["silent_seconds"]) == (
        "REPORT_RUN",
        1,
        601,
    )
    assert _kept(other.tenant_id) == ["QUEUED"]

    # No transaction of the job is open any more: the next pass stops it.
    fail_stalled(runtime)
    assert _job(lena.tenant_id, job_id)["state"] == "FAILED"
    with (
        pytest.raises(JobLost),
        system_unit_of_work(worker, sandbox, request_id=f"job-{job_id}-report"),
    ):
        raise AssertionError("a unit of work of a stopped job began")
    context = JobContext(
        job_id=job_id,
        tenant_id=lena.tenant_id,
        kind=KIND,
        principal=system_principal(lena.tenant_id),
        runtime=worker,
    )
    with pytest.raises(JobLost), tenant_session(_db(other.tenant_id)) as session:
        context.enlist(session)
        raise AssertionError("a transaction of a stopped job began")
    assert _kept(other.tenant_id) == ["QUEUED"]


def test_job_06_the_heartbeat_takes_no_key_of_the_job_row(lena: Member) -> None:
    """Every row that refers to a job takes KEY SHARE on the job's row when it is inserted.
    The heartbeat a commit writes is a plain update of columns that no key holds, so such an
    insert passes beside it without waiting - a keyed lock on the row would make it wait, and
    with the audit chain's head behind it would close a ring. Shown for the lock each of the
    referring tables takes, read without waiting, and for one of them inserted: a job under
    its parent. The list is the catalogue's; a table that joins it is weighed here."""
    job_id = _start(lena)
    task_id = _begin(lena.tenant_id, job_id, heartbeat=FROZEN_AT)
    attempt = JobAttempt(job_id=job_id, tenant_id=lena.tenant_id, task_id=task_id)
    with tenant_session(_db(lena.tenant_id)) as writer:
        attempt.beat(writer, now=FROZEN_AT + timedelta(minutes=1))  # written, not yet committed
        with tenant_session(_db(lena.tenant_id)) as other:
            assert tuple(other.scalars(_REFERRING)) == REFERRING
            key = {"tenant_id": lena.tenant_id, "job_id": job_id}
            assert other.execute(_KEY_SHARE, key).scalar_one() == 1
            registry.insert_job(
                other,
                JobKind.RETENTION_SWEEP,
                {},
                tenant_id=lena.tenant_id,
                now=FROZEN_AT,
                created_by=None,
                created_by_kind=PrincipalKind.SYSTEM,
                parent_job_id=job_id,
            )
        # The insert is committed while the heartbeat's transaction is still open.
        assert _kept(lena.tenant_id, job_id) == ["QUEUED"]
        assert _job(lena.tenant_id, job_id)["updated_at"] == FROZEN_AT
    assert _job(lena.tenant_id, job_id)["updated_at"] == FROZEN_AT + timedelta(minutes=1)


class _SlowSender:
    """An e-mail adapter whose send takes ten minutes and a second of the clock; the sweeper
    passes before it returns."""

    def __init__(self, clock: FrozenClock) -> None:
        self._clock = clock
        self.sweep: Callable[[], object] = lambda: None
        self.sent: list[str] = []

    def send(self, message: outbox.EmailMessage) -> str:
        self.sent.append(message.subject)
        self._clock.advance(STALL)
        self.sweep()
        return f"sent-{len(self.sent)}"


def test_job_06_a_transport_job_rests_on_its_messages_claim(
    lena: Member, app_settings: Settings, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """The transport kinds pass no door: their transactions are the claim of a message and the
    record of its outcome, and the message's own claim stamp fences them (05 ADP-32). The send
    of an e-mail delivery takes ten minutes here - a handler alive outside a transaction - so
    the sweeper hands the job to a second attempt beside it. The outcome of the send is recorded
    all the same, under the claim: the message is sent and recorded once. The first attempt
    then stops at its beat and records nothing on the job; the second finds nothing due. The
    registered handler of ``EMAIL_DELIVERY`` runs through the worker here."""
    clock = frozen_clock(FROZEN_AT)
    sender = _SlowSender(clock)
    runtime = JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
        email=sender,
        public_origin=app_settings.public_origin,
    )
    sender.sweep = lambda: fail_stalled(runtime)
    with system_unit_of_work(
        runtime, system_principal(lena.tenant_id), request_id="tests-job-stall-rule"
    ) as uow:
        message = outbox.enqueue(
            uow,
            topic=OutboxTopic.EMAIL,
            aggregate_type="probe",
            aggregate_id=new_id(),
            dedupe_key="probe:1",
            payload={
                "to": "probe@acme.test",
                "subject": "Probe",
                "text": "Probe message.",
                "reference": str(new_id()),
            },
        )
        uow.commit()
    message_id = UUID(str(message["id"]))

    def status() -> str:
        with tenant_session(_db(lena.tenant_id), read_only=True) as session:
            return str(
                session.execute(
                    select(outbox_message.c.status).where(outbox_message.c.id == message_id)
                ).scalar_one()
            )

    job_id = _start(lena, JobKind.EMAIL_DELIVERY, {"outbox_message_id": str(message_id)})
    first = _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    assert sender.sent == ["Probe"]
    assert status() == "DISPATCHED"
    handed_on = _job(lena.tenant_id, job_id)
    assert (handed_on["state"], handed_on["result"]) == ("QUEUED", None)
    assert handed_on["procrastinate_job_id"] != first
    (lost,) = _lines(log_stream, "job.attempt_lost", job_id)
    assert (lost["job_kind"], lost["attempt"]) == ("EMAIL_DELIVERY", 1)

    _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=2, runtime=runtime)
    done = _job(lena.tenant_id, job_id)
    assert (done["state"], done["result"]["counts"]["claimed"]) == ("SUCCEEDED", 0)
    assert sender.sent == ["Probe"] and status() == "DISPATCHED"


def test_rb_07_an_operator_ends_the_transaction_of_a_job_that_is_passed_over(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """Nothing ends a transaction that keeps sending statements, so the runbook gives the
    operator the way: the statement that finds the transaction by the job's lock, and
    ``pg_terminate_backend``. Followed here as it is written in RB-07. The statement names the
    backend of the job's open unit of work and no other; once that backend is ended, nothing of
    the transaction is kept, and the worker settles the attempt as a failed one - the job ends
    FAILED with the problem of an unexpected error, and its member is told so."""
    (written,) = _HOLDERS.findall(RUNBOOK.read_text(encoding="utf-8"))
    clock = frozen_clock(FROZEN_AT)
    runtime = _runtime(app_settings, keyring, clock)
    found: list[tuple[list[int], int]] = []

    def handler(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        with jc.unit_of_work() as uow:
            _work(uow)
            clock.advance(STALL)
            fail_stalled(runtime)
            statement = text(written.replace("<job id>", str(jc.job_id)))
            with tenant_session(_db(jc.tenant_id)) as operator:
                pids = [int(row.pid) for row in operator.execute(statement)]
                found.append((pids, backend_pid(uow.session)))
                for pid in pids:
                    operator.execute(text("select pg_terminate_backend(:pid)"), {"pid": pid})
            _work(uow)  # the handler goes on, and its connection is gone
            uow.commit()
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 2}})

    monkeypatch.setitem(registry.HANDLERS, KIND, HandlerSpec(handler, RetryPolicy(max_attempts=1)))
    job_id = _start(lena)
    _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)

    ((pids, unit_pid),) = found
    assert pids == [unit_pid]
    assert len(_lines(log_stream, "job.sweep_passed_over", job_id)) == 1
    failed = _job(lena.tenant_id, job_id)
    assert (failed["state"], failed["problem"]["title"], failed["result"]) == (
        "FAILED",
        "Job failed",
        None,
    )
    assert _kept(lena.tenant_id) == []
    assert _notifications(lena) == [
        (
            "Job failed: Report run",
            "Report run failed at attempt 1: The job stopped with an unexpected error. Nothing "
            "was committed.",
            "job",
            job_id,
        )
    ]
