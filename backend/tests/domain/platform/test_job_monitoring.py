"""Stalled and failed jobs (dev-guide DG-KRN-JOB-05, DG-KRN-JOB-06; 05 JOB-06, JOB-07, SCH-04; PRD
NTF-05, NFR-13; 03 REQ-OPS-006, CTL-040; BUILD_SPEC PLF-22).

The tests play the worker: they take the job's current Procrastinate task, start the attempt with
its last heartbeat at a chosen instant, and run the sweeper with a clock 10 minutes later.
"""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.adapters.email import build_email_sender
from erev_api.adapters.http.webhook_client import WebhookClient
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.controls.operator_alert_sinks import AlertSinks
from erev_api.controls.operator_alerts import LogSink, OperatorAlert
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, job, notification, outbox_message
from erev_api.db.transitions import apply
from erev_api.domain.platform import audit_jobs
from erev_api.domain.platform.webhook_endpoints import create_endpoint
from erev_api.enums import JobKind, OutboxTopic, PrincipalKind, TenantKind
from erev_api.events import outbox, webhooks
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.jobs.registry import HandlerSpec, JobOutcome, RetryPolicy
from erev_api.jobs.sweeper import fail_stalled
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import select, text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.http import HttpRequest, mock_transport
from support.principals import Member, member
from support.rows import insert_audited_tenant, insert_sandbox_tenant

PUBLIC_ADDRESS = "93.184.216.34"
STALL = timedelta(minutes=10, seconds=1)
QUIET = timedelta(minutes=9, seconds=59)
STALLED_TYPE = "https://erev.dev/problems/job-stalled"
_TASK = text("SELECT args, scheduled_at FROM procrastinate_jobs WHERE id = :id")
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def lena(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> Member:
    return member(keyring, clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _runtime(app_settings: Settings, keyring: KeyRing, at: datetime) -> JobRuntime:
    return JobRuntime(
        clock=frozen_clock(at), keyring=keyring, files=LocalFileStore(app_settings.file_root)
    )


def _start(someone: Member, kind: JobKind) -> UUID:
    """The member starts a job; its first task is deferred."""
    with tenant_session(_db(someone.tenant_id)) as session:
        row = registry.insert_job(
            session,
            kind,
            {},
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
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(select(job).where(job.c.id == job_id)).mappings().one()


def _task(tenant_id: UUID, procrastinate_job_id: int) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return session.execute(_TASK, {"id": procrastinate_job_id}).mappings().one()


def _begin(tenant_id: UUID, job_id: UUID, *, heartbeat: datetime) -> None:
    """A worker takes the current task and starts the attempt, last heartbeat ``heartbeat``."""
    with tenant_session(_db(tenant_id)) as session:
        procrastinate_job_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": procrastinate_job_id})
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


def _notifications(someone: Member) -> list[tuple[Any, ...]]:
    with tenant_session(_db(someone.tenant_id)) as session:
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


def _fetch(tenant_id: UUID, job_id: UUID) -> int:
    """A worker takes the job's current task: its Procrastinate row becomes ``doing``."""
    procrastinate_job_id = int(_job(tenant_id, job_id)["procrastinate_job_id"])
    with tenant_session(_db(tenant_id)) as session:
        session.execute(_FETCHED, {"id": procrastinate_job_id})
    return procrastinate_job_id


@contextmanager
def _uow(tenant_id: UUID, runtime: JobRuntime) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-job-monitoring",
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


def _never_runs(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    raise AssertionError("the sweeper settles attempts without running the handler")


@pytest.mark.control("CTL-040")
def test_ctl_040_stalled_job_failed_and_notified(
    lena: Member, app_settings: Settings, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = RetryPolicy(max_attempts=3)
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(_never_runs, policy))
    job_id = _start(lena, JobKind.REPORT_RUN)

    heartbeat = FROZEN_AT
    for attempt in (1, 2):
        _begin(lena.tenant_id, job_id, heartbeat=heartbeat)
        # 9 minutes 59 seconds without a heartbeat is not a stall.
        fail_stalled(_runtime(app_settings, keyring, heartbeat + QUIET))
        assert _job(lena.tenant_id, job_id)["state"] == "RUNNING"

        swept_at = heartbeat + STALL
        fail_stalled(_runtime(app_settings, keyring, swept_at))
        requeued = _job(lena.tenant_id, job_id)
        assert (requeued["state"], requeued["problem"], requeued["finished_at"]) == (
            "QUEUED",
            None,
            None,
        )
        task = _task(lena.tenant_id, requeued["procrastinate_job_id"])
        assert task["args"]["attempt"] == attempt + 1
        assert task["scheduled_at"] == swept_at + registry.backoff_delay(policy, attempt)
        assert _notifications(lena) == []
        heartbeat = swept_at + timedelta(minutes=5)

    _begin(lena.tenant_id, job_id, heartbeat=heartbeat)
    swept_at = heartbeat + STALL
    fail_stalled(_runtime(app_settings, keyring, swept_at))
    failed = _job(lena.tenant_id, job_id)
    assert (failed["state"], failed["finished_at"]) == ("FAILED", swept_at)
    assert (failed["problem"]["type"], failed["problem"]["detail"]) == (
        STALLED_TYPE,
        "no heartbeat for 10 minutes",
    )
    assert _notifications(lena) == [
        (
            "Job failed: Report run",
            # PRD NTF-05 rev 1.191 (item JOB-STALL-COMMIT-RACE-1): the body of a job stopped as
            # stalled says what was not kept - the sweeper cannot say that nothing was committed.
            "Report run failed at attempt 3: no heartbeat for 10 minutes. The job was stopped; "
            "what it had not committed by then is not kept.",
            "job",
            job_id,
        )
    ]
    with tenant_session(_db(lena.tenant_id)) as session:
        emails = session.scalars(
            select(outbox_message.c.payload).where(
                outbox_message.c.aggregate_type == "notification"
            )
        ).all()
    assert [payload["subject"] for payload in emails] == ["Job failed: Report run"]

    # A FAILED job is final: a later sweep changes nothing and notifies no one again.
    fail_stalled(_runtime(app_settings, keyring, swept_at + timedelta(hours=1)))
    assert _job(lena.tenant_id, job_id)["state"] == "FAILED"
    assert len(_notifications(lena)) == 1


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


def test_r_50_a_a_job_that_cannot_be_settled_never_stops_the_sweep(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    clock: FrozenClock,
    log_stream: io.StringIO,
) -> None:
    """dev-guide DG-KRN-JOB-06 rev 1.89 (04 T-PLT-27; supervisor ruling R-50 (a)): ending a job
    FAILED writes ``job.finish`` to its tenant's audit chain, so the sweeper settles each job in
    isolation. A stalled job of a tenant whose chain cannot take the event (no chain head: DB-09
    fails closed) stays as it is, and the stalled job of the tenant after it is still swept — FAILED
    with its ``job.finish``. Without the isolation the first failure raised out of the sweep."""
    assert JobKind.DEAL_PREVIEW not in registry.HANDLERS  # no handler: one attempt, then FAILED
    broken = insert_sandbox_tenant(keyring)  # ACTIVE, without the chain head provisioning writes
    later = member(keyring, clock)
    assert str(lena.tenant_id) < str(broken) < str(later.tenant_id)  # the sweep's tenant order

    def stalled_job(tenant_id: UUID) -> UUID:
        with tenant_session(_db(tenant_id)) as session:
            row = registry.insert_job(
                session,
                JobKind.DEAL_PREVIEW,
                {},
                tenant_id=tenant_id,
                now=FROZEN_AT,
                created_by=None,
                created_by_kind=PrincipalKind.SYSTEM,
            )
            registry.dispatch(
                session,
                job_id=row["id"],
                tenant_id=tenant_id,
                queue=str(row["queue"]),
                now=FROZEN_AT,
            )
        job_id = UUID(str(row["id"]))
        _begin(tenant_id, job_id, heartbeat=FROZEN_AT)
        return job_id

    stuck, swept = stalled_job(broken), stalled_job(later.tenant_id)
    swept_at = FROZEN_AT + STALL
    settled = fail_stalled(_runtime(app_settings, keyring, swept_at))
    assert settled >= 1
    assert _job(broken, stuck)["state"] == "RUNNING"  # nothing of the failed settlement is kept
    failure = _isolated_failure(log_stream, "job.sweep_failed", broken)
    assert failure["job_id"] == str(stuck)
    failed = _job(later.tenant_id, swept)
    assert (failed["state"], failed["finished_at"], failed["problem"]["type"]) == (
        "FAILED",
        swept_at,
        STALLED_TYPE,
    )
    with tenant_session(_db(later.tenant_id)) as session:
        events = session.execute(
            select(audit_event.c.action, audit_event.c.actor_kind, audit_event.c.after).where(
                audit_event.c.object_type == "job", audit_event.c.object_id == swept
            )
        ).all()
    assert [tuple(event) for event in events] == [
        (
            "job.finish",
            "SYSTEM",
            {"kind": "DEAL_PREVIEW", "state": "FAILED", "problem": "job-stalled"},
        )
    ]


class _SlowEmail:
    """The fake email adapter; every send takes 10 s of the clock, and every sixth send runs the
    stall sweeper."""

    def __init__(self, inner: outbox.EmailSender, clock: FrozenClock) -> None:
        self._inner = inner
        self._clock = clock
        self.sends = 0
        self.runtime: JobRuntime | None = None
        self.job: tuple[UUID, UUID] | None = None
        self.states: list[str] = []

    def send(self, message: outbox.EmailMessage) -> str:
        reference = self._inner.send(message)
        self.sends += 1
        self._clock.advance(timedelta(seconds=10))
        if self.sends % 6 == 0 and self.runtime is not None and self.job is not None:
            fail_stalled(self.runtime)
            self.states.append(str(_job(*self.job)["state"]))
        return reference


def test_krn_job_04_heartbeat_keeps_long_handlers_running(
    lena: Member, app_settings: Settings, keyring: KeyRing, tmp_path: Path
) -> None:
    """PR-R-03 (D-80): delivery and relay jobs heartbeat after each delivery or message, so a run
    longer than 10 minutes is never taken for stalled."""
    files = LocalFileStore(app_settings.file_root)
    clock = frozen_clock(FROZEN_AT)
    posts: list[HttpRequest] = []
    states: list[str] = []
    delivery_job: UUID | None = None

    def respond(request: HttpRequest) -> int:
        posts.append(request)
        clock.advance(timedelta(seconds=10))
        if len(posts) % 6 == 0 and delivery_job is not None:
            fail_stalled(deliveries)
            states.append(str(_job(lena.tenant_id, delivery_job)["state"]))
        return 204

    deliveries = JobRuntime(
        clock=clock,
        keyring=keyring,
        files=files,
        webhooks=WebhookClient(
            env=Environment.TEST,
            transport=mock_transport(respond),
            resolve=lambda host, port: [PUBLIC_ADDRESS],
        ),
    )
    with _uow(lena.tenant_id, deliveries) as uow:
        for n in range(7):
            create_endpoint(
                uow,
                url=f"https://hooks.example/erev/{n}",
                description=None,
                event_kinds=["period.locked"],
            )
        uow.commit()
    with _uow(lena.tenant_id, deliveries) as uow:
        for _ in range(10):
            webhooks.emit_webhook(uow, event_kind="period.locked", payload={"period_id": new_id()})
        uow.commit()

    delivery_job = _start(lena, JobKind.WEBHOOK_DELIVERY)
    delivery_task = _fetch(lena.tenant_id, delivery_job)
    registry.run_job(delivery_job, lena.tenant_id, attempt=1, runtime=deliveries)
    delivered = _job(lena.tenant_id, delivery_job)
    assert len(posts) == 70
    assert states == ["RUNNING"] * 11
    assert (delivered["state"], delivered["procrastinate_job_id"]) == ("SUCCEEDED", delivery_task)
    assert delivered["result"]["counts"] == {
        "claimed": 70,
        "succeeded": 70,
        "failed": 0,
        "abandoned": 0,
    }

    # A user's relay over 70 messages with the same clock pattern.
    ines = member(keyring, frozen_clock(FROZEN_AT))
    relay_clock = frozen_clock(FROZEN_AT)
    settings = app_settings.model_copy(update={"run_dir": tmp_path / ".run"})
    email = _SlowEmail(build_email_sender(settings, relay_clock), relay_clock)
    relays = JobRuntime(
        clock=relay_clock,
        keyring=keyring,
        files=files,
        email=email,
        public_origin=settings.public_origin,
    )
    with _uow(ines.tenant_id, relays) as uow:
        for n in range(70):
            outbox.enqueue(
                uow,
                topic=OutboxTopic.EMAIL,
                aggregate_type="probe",
                aggregate_id=new_id(),
                dedupe_key=f"probe:{n}",
                payload={
                    "to": f"probe{n}@acme.test",
                    "subject": "Probe",
                    "text": "Probe message.",
                    "reference": str(new_id()),
                },
            )
        uow.commit()
    relay_job = _start(ines, JobKind.OUTBOX_RELAY)
    relay_task = _fetch(ines.tenant_id, relay_job)
    email.runtime, email.job = relays, (ines.tenant_id, relay_job)
    registry.run_job(relay_job, ines.tenant_id, attempt=1, runtime=relays)
    relayed = _job(ines.tenant_id, relay_job)
    # The 70 messages and the provisioned invitation.
    assert email.sends == 71
    assert email.states == ["RUNNING"] * 11
    assert (relayed["state"], relayed["procrastinate_job_id"]) == ("SUCCEEDED", relay_task)
    assert _notifications(ines) == []


def test_run_job_records_only_its_own_attempt(
    lena: Member, app_settings: Settings, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR-R-03 (D-80): an attempt that the sweeper replaced records nothing on its successor's
    row."""
    clock = frozen_clock(FROZEN_AT)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))
    job_id = _start(lena, JobKind.WEBHOOK_DELIVERY)
    started, release = threading.Event(), threading.Event()
    observed: list[tuple[str, Any]] = []
    failures: list[BaseException] = []

    def attempt_two() -> None:
        try:
            _fetch(lena.tenant_id, job_id)
            registry.run_job(job_id, lena.tenant_id, attempt=2, runtime=runtime)
        except BaseException as error:
            failures.append(error)
            started.set()

    worker = threading.Thread(target=attempt_two, name="attempt-2")

    def handler(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        if not observed:
            # Attempt 1 goes quiet for 10 minutes 1 second; the sweeper re-queues the job, and
            # attempt 2 moves it to RUNNING before attempt 1 returns.
            clock.advance(STALL)
            fail_stalled(runtime)
            requeued = _job(lena.tenant_id, job_id)
            observed.append(("requeued", (requeued["state"], _task_attempt(lena, job_id))))
            worker.start()
            started.wait(timeout=30)
            observed.append(("attempt 2 started", _job(lena.tenant_id, job_id)["state"]))
            return JobOutcome(state="SUCCEEDED", result={"counts": {"attempt": 1}})
        started.set()
        release.wait(timeout=30)
        return JobOutcome(state="SUCCEEDED", result={"counts": {"attempt": 2}})

    monkeypatch.setitem(
        registry.HANDLERS, JobKind.WEBHOOK_DELIVERY, HandlerSpec(handler, webhooks.DELIVERY_RETRY)
    )
    _fetch(lena.tenant_id, job_id)
    registry.run_job(job_id, lena.tenant_id, attempt=1, runtime=runtime)
    after_first = _job(lena.tenant_id, job_id)
    release.set()
    worker.join(timeout=30)

    assert failures == []
    assert observed == [("requeued", ("QUEUED", 2)), ("attempt 2 started", "RUNNING")]
    assert (after_first["state"], after_first["result"], after_first["finished_at"]) == (
        "RUNNING",
        None,
        None,
    )
    finished = _job(lena.tenant_id, job_id)
    assert (finished["state"], finished["result"]) == ("SUCCEEDED", {"counts": {"attempt": 2}})


def _task_attempt(someone: Member, job_id: UUID) -> Any:
    return _task(someone.tenant_id, _job(someone.tenant_id, job_id)["procrastinate_job_id"])[
        "args"
    ]["attempt"]


def test_krn_job_04_chain_verification_heartbeats(
    committed_db: TestDatabase,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-80: AUDIT_CHAIN_VERIFY heartbeats after every 1,000 verified events, or once 30 seconds
    have passed since its last heartbeat."""
    beats: list[UUID] = []

    def recording(self: JobContext) -> None:
        beats.append(self.job_id)

    monkeypatch.setattr(JobContext, "heartbeat", recording)
    monkeypatch.setattr(audit_jobs, "HEARTBEAT_EVENTS", 2)
    tenant_id = insert_audited_tenant(keyring, events=5, at=FROZEN_AT)
    # 05 REL-03 (rev 1.15; D-98 60): the verification (AUDIT_CHAIN_VERIFY) runs in THIS process and
    # its CTL-039 evidence producer stamps the process release — a process that never stamped fails
    # closed (release-mismatch) whatever rows the table holds, so the job runtime stamps through the
    # shared support exactly as the world factories do (P5-DOCTOR-R1).
    stamp_test_release()
    runtime = _runtime(app_settings, keyring, FROZEN_AT)
    with tenant_session(_db(tenant_id)) as session:
        row = registry.insert_job(
            session,
            JobKind.AUDIT_CHAIN_VERIFY,
            {"trigger": "SCHEDULED"},
            tenant_id=tenant_id,
            now=FROZEN_AT,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        )
        registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=FROZEN_AT
        )
    job_id = UUID(str(row["id"]))
    _fetch(tenant_id, job_id)
    # The bare tenant publishes no registry values, so the worker is given its slot count.
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime, concurrency=1)
    assert _job(tenant_id, job_id)["state"] == "SUCCEEDED"
    # After events 2 and 4 of the 5.
    assert beats == [job_id, job_id]

    clock = frozen_clock(FROZEN_AT)
    context = JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.AUDIT_CHAIN_VERIFY,
        principal=system_principal(tenant_id),
        runtime=runtime,
        clock=clock,
        persisted=False,
    )
    beat = audit_jobs.ChainHeartbeat(context)
    beat(1)
    clock.advance(timedelta(seconds=29))
    beat(1)
    assert beats == [job_id, job_id]
    clock.advance(timedelta(seconds=1))
    beat(1)
    assert beats == [job_id, job_id, context.job_id]


def test_krn_job_05_last_attempt_problem_stored(
    lena: Member, app_settings: Settings, keyring: KeyRing
) -> None:
    # No handler yet, so the default policy of one attempt applies.
    assert JobKind.DEAL_PREVIEW not in registry.HANDLERS
    job_id = _start(lena, JobKind.DEAL_PREVIEW)
    _begin(lena.tenant_id, job_id, heartbeat=FROZEN_AT)
    fail_stalled(_runtime(app_settings, keyring, FROZEN_AT + STALL))
    failed = _job(lena.tenant_id, job_id)
    assert failed["state"] == "FAILED"
    assert failed["problem"] == {
        "type": STALLED_TYPE,
        "title": "Job stopped responding",
        "status": 500,
        "detail": "no heartbeat for 10 minutes",
        "instance": f"/api/v1/jobs/{job_id}",
        "code": None,
        "errors": [],
    }


def _started_by(someone: Member, kind: JobKind, by: PrincipalKind) -> UUID:
    """A job of ``kind`` in ``someone``'s workspace, started by the scheduler (no user), by an API
    client, or by the member."""
    created_by = {
        PrincipalKind.SYSTEM: None,
        PrincipalKind.API_CLIENT: uuid4(),
        PrincipalKind.USER: someone.user_id,
    }[by]
    with tenant_session(_db(someone.tenant_id)) as session:
        row = registry.insert_job(
            session,
            kind,
            {},
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=created_by,
            created_by_kind=by,
        )
        registry.dispatch(
            session,
            job_id=row["id"],
            tenant_id=someone.tenant_id,
            queue=str(row["queue"]),
            now=FROZEN_AT,
        )
    return UUID(str(row["id"]))


def _alert_lines(log_stream: io.StringIO, job_id: UUID) -> list[dict[str, Any]]:
    """The ``operator_alert.raised`` lines whose alert names ``job_id``: the sweeper serves every
    tenant of the shared database, so only the lines of the test's own job are read."""
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    return [
        line
        for line in lines
        if line["event"] == "operator_alert.raised"
        and (line.get("alert_fields") or {}).get("job_id") == str(job_id)
    ]


@pytest.mark.parametrize(
    ("by", "alerted"),
    [
        (PrincipalKind.SYSTEM, True),
        (PrincipalKind.API_CLIENT, True),
        (PrincipalKind.USER, False),
    ],
)
def test_job_failed_item_1_who_learns_of_a_failed_job(
    by: PrincipalKind,
    alerted: bool,
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """05 JOB-07 rev 1.165, OPR-24 (item JOB-FAILED-ITEM-1; CTL-040): the same failure of a job
    the scheduler started, an API client started and a user started. The first two told nobody
    before: now the registry raises the operator alert ``JOB_FAILED`` after the commit — through
    the log sink the line ``operator_alert.raised`` at warning level, with values-free fields
    that name the tenant, the job, its kind, its queue, the attempt, the slug of its problem and
    the kind of its initiator, which is what the hosted alert policy matches. A user's job
    notifies its initiator and raises no alert. All three leave ``job.finish``."""
    policy = RetryPolicy(max_attempts=1)
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(_never_runs, policy))
    job_id = _started_by(lena, JobKind.REPORT_RUN, by)
    _begin(lena.tenant_id, job_id, heartbeat=FROZEN_AT)
    runtime = JobRuntime(
        clock=frozen_clock(FROZEN_AT + STALL),
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
        alerts=AlertSinks((LogSink(),)),
    )
    fail_stalled(runtime)
    failed = _job(lena.tenant_id, job_id)
    assert (failed["state"], failed["created_by_kind"]) == ("FAILED", by.value)
    with tenant_session(_db(lena.tenant_id)) as session:
        finished = session.execute(
            select(audit_event.c.action, audit_event.c.actor_kind).where(
                audit_event.c.object_type == "job", audit_event.c.object_id == job_id
            )
        ).all()
    assert [tuple(event) for event in finished] == [("job.finish", "SYSTEM")]

    alerts = _alert_lines(log_stream, job_id)
    if not alerted:
        assert alerts == []
        assert [row[0] for row in _notifications(lena)] == ["Job failed: Report run"]
        return
    assert _notifications(lena) == []
    (alert,) = alerts
    assert (alert["level"], alert["kind"], alert["severity"], alert["runbook"]) == (
        "warning",
        "JOB_FAILED",
        "WARNING",
        "RB-07",
    )
    assert alert["alert_fields"] == {
        "tenant_id": str(lena.tenant_id),
        "job_id": str(job_id),
        "job_kind": "REPORT_RUN",
        "queue": "reports",
        "attempt": 1,
        "problem": "job-stalled",
        "initiator": by.value,
    }


def test_job_failed_item_1_an_alert_that_cannot_be_raised_changes_nothing(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """The alert follows the commit: a raiser that fails is logged ``job.failed_alert_failed``
    with its class, and the job stays FAILED with its ``job.finish``."""

    class Unreachable:
        def raise_alert(self, alert: OperatorAlert) -> tuple[str, ...]:
            raise ConnectionError("the alert channel is down")

    policy = RetryPolicy(max_attempts=1)
    monkeypatch.setitem(registry.HANDLERS, JobKind.REPORT_RUN, HandlerSpec(_never_runs, policy))
    job_id = _started_by(lena, JobKind.REPORT_RUN, PrincipalKind.SYSTEM)
    _begin(lena.tenant_id, job_id, heartbeat=FROZEN_AT)
    runtime = JobRuntime(
        clock=frozen_clock(FROZEN_AT + STALL),
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
        alerts=Unreachable(),
    )
    fail_stalled(runtime)
    assert _job(lena.tenant_id, job_id)["state"] == "FAILED"
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    assert [
        (line["event"], line["level"], line["error_class"])
        for line in lines
        if line["event"] == "job.failed_alert_failed" and line.get("job_id") == str(job_id)
    ] == [("job.failed_alert_failed", "error", "ConnectionError")]
