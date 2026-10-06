"""Transactional outbox and the fake email adapter (dev-guide §5.11 DG-KRN-EVT-04,
DG-KRN-EVT-05; 04 T-INT-03, §14.3 item 2; 05 ADP-31, NTR-05; BUILD_SPEC PLF-14).

The tests play the relay job: they build a ``JobContext`` whose runtime carries the fake email
sender, writing under the test's own ``.run`` directory, and call ``relay`` as the handler does.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import timedelta
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.email import build_email_sender
from erev_api.adapters.email.smtp import SmtpEmailSender
from erev_api.adapters.http.guard import DestinationRefused
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Environment, Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, outbox_message, tenant_membership
from erev_api.domain.platform.provisioning import TenantProvisionResult
from erev_api.enums import JobKind, OutboxTopic, PrincipalKind, TenantKind
from erev_api.events import outbox
from erev_api.events.outbox import DispatchResult, RelayStats, enqueue, relay
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.problems import LOCK_CONFLICT_DETAIL, Problem
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import func, select, text
from support import network
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of

_TASK = text("SELECT task_name, queue_name, status FROM procrastinate_jobs WHERE id = :id")
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring, clock=clock))


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / ".run"


@pytest.fixture
def runtime(
    app_settings: Settings, keyring: KeyRing, clock: FrozenClock, run_dir: Path
) -> JobRuntime:
    settings = app_settings.model_copy(update={"run_dir": run_dir})
    return JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(settings.file_root),
        email=build_email_sender(settings, clock),
        public_origin=settings.public_origin,
    )


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@contextmanager
def _uow(tenant_id: UUID, runtime: JobRuntime) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-outbox",
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


def _relayer(tenant_id: UUID, runtime: JobRuntime) -> JobContext:
    return JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=JobKind.OUTBOX_RELAY,
        principal=system_principal(tenant_id),
        runtime=runtime,
        persisted=False,
    )


def _messages(tenant_id: UUID, **where: Any) -> list[Mapping[str, Any]]:
    statement = select(outbox_message).order_by(outbox_message.c.created_at, outbox_message.c.id)
    for name, value in where.items():
        statement = statement.where(outbox_message.c[name] == value)
    with tenant_session(_db(tenant_id)) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _relay_jobs(tenant_id: UUID) -> list[Mapping[str, Any]]:
    with tenant_session(_db(tenant_id)) as session:
        return [
            dict(row)
            for row in session.execute(
                select(job.c.state, job.c.queue, job.c.procrastinate_job_id).where(
                    job.c.kind == JobKind.OUTBOX_RELAY.value
                )
            ).mappings()
        ]


def _probe(
    uow: UnitOfWork,
    dedupe_key: str,
    payload: Mapping[str, Any],
    *,
    topic: OutboxTopic = OutboxTopic.EMAIL,
) -> Mapping[str, Any]:
    return enqueue(
        uow,
        topic=topic,
        aggregate_type="probe",
        aggregate_id=new_id(),
        dedupe_key=dedupe_key,
        payload=payload,
    )


def test_krn_evt_04_enqueue_dedupe_and_after_commit(tenant_id: UUID, runtime: JobRuntime) -> None:
    with _uow(tenant_id, runtime) as uow:
        first = _probe(uow, "probe:1", {"n": 1})
        second = _probe(uow, "probe:1", {"n": 2})
        assert second["id"] == first["id"]
        pending = uow.session.execute(
            select(job.c.procrastinate_job_id).where(job.c.kind == JobKind.OUTBOX_RELAY.value)
        ).all()
        assert [row.procrastinate_job_id for row in pending] == [None]
        uow.commit()

    probes = _messages(tenant_id, aggregate_type="probe")
    assert [
        (row["dedupe_key"], row["payload"], row["status"], row["attempt_count"]) for row in probes
    ] == [("probe:1", {"n": 1}, "PENDING", 0)]
    assert probes[0]["next_attempt_at"] == runtime.clock.now()
    # After commit one relay job is deferred on the outbox queue.
    [relay_job] = _relay_jobs(tenant_id)
    assert (relay_job["state"], relay_job["queue"]) == ("QUEUED", "outbox")
    assert relay_job["procrastinate_job_id"] is not None
    with tenant_session(_db(tenant_id)) as session:
        task = session.execute(_TASK, {"id": relay_job["procrastinate_job_id"]}).mappings().one()
    assert (task["task_name"], task["queue_name"], task["status"]) == (
        "erev.run_job",
        "outbox",
        "todo",
    )

    # A unit of work that rolls back inserts nothing and defers nothing.
    with _uow(tenant_id, runtime) as uow:
        _probe(uow, "probe:2", {"n": 3})
    assert len(_messages(tenant_id, aggregate_type="probe")) == 1
    assert len(_relay_jobs(tenant_id)) == 1
    with tenant_session(_db(tenant_id)) as session:
        tasks = session.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE queue_name = 'outbox' AND args ->> 'tenant_id' = :t"
            ),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert tasks == 1


def test_krn_evt_05_relay_backoff_and_dead_letter(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = runtime.clock
    assert isinstance(clock, FrozenClock)
    relayer = _relayer(tenant_id, runtime)
    # The provisioned invitation is due first and dispatches through the fake sender.
    assert relay(relayer) == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    [invitation] = _messages(tenant_id, aggregate_type="tenant_membership")
    assert (invitation["status"], invitation["attempt_count"], invitation["dispatched_at"]) == (
        "DISPATCHED",
        0,
        clock.now(),
    )

    calls: list[Mapping[str, Any]] = []

    def refusing(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        calls.append(payload)
        raise RuntimeError("probe endpoint refused the delivery")

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, refusing)
    with _uow(tenant_id, runtime) as uow:
        message_id = _probe(uow, "probe:retry", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"]
        uow.commit()

    def current() -> Mapping[str, Any]:
        [row] = _messages(tenant_id, id=message_id)
        return row

    start = clock.now()
    assert relay(relayer) == RelayStats(claimed=1, dispatched=0, failed=1, dead=0)
    row = current()
    assert (row["status"], row["attempt_count"], row["next_attempt_at"], row["last_error"]) == (
        "FAILED",
        1,
        start + timedelta(seconds=60),
        "RuntimeError",
    )
    # Not due before its backoff has passed.
    clock.advance(timedelta(seconds=59))
    assert relay(relayer).claimed == 0

    waits: dict[int, timedelta] = {}
    for attempt in range(2, 10):
        clock.set(row["next_attempt_at"])
        assert relay(relayer) == RelayStats(claimed=1, dispatched=0, failed=1, dead=0)
        row = current()
        assert (row["status"], row["attempt_count"]) == ("FAILED", attempt)
        waits[attempt] = row["next_attempt_at"] - clock.now()
    assert waits[2] == timedelta(seconds=120)
    assert waits[6] == timedelta(seconds=1920)
    # The seventh failure reaches the one-hour cap.
    assert waits[7] == waits[9] == timedelta(seconds=3600)

    clock.set(row["next_attempt_at"])
    assert relay(relayer) == RelayStats(claimed=1, dispatched=0, failed=0, dead=1)
    row = current()
    assert (row["status"], row["attempt_count"], row["dispatched_at"]) == ("DEAD", 10, None)
    clock.advance(timedelta(days=1))
    assert relay(relayer).claimed == 0
    assert len(calls) == 10


def test_a_delivered_message_keeps_no_last_error(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supervisor ruling R-108 (b) (5) (04 T-INT-03 rev 1.144; dev-guide DG-KRN-EVT-05 rev 1.127):
    a message that failed and is then delivered ends DISPATCHED with ``last_error`` null - the
    class of an earlier failed attempt is not the state of a delivered row, and ``attempt_count``
    keeps the history. Measured on the verification stack by lane OPS: an invitation the relay had
    refused once read ``DISPATCHED | 1 | DestinationRefused`` after its delivery. Fail-first here:
    ``DISPATCHED | 1 | RuntimeError``."""
    clock = runtime.clock
    assert isinstance(clock, FrozenClock)
    relayer = _relayer(tenant_id, runtime)
    assert relay(relayer).dispatched == 1  # the provisioned invitation
    answers: list[Exception | None] = [RuntimeError("the endpoint refused the delivery"), None]

    def flaky(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        answer = answers.pop(0)
        if answer is not None:
            raise answer
        return DispatchResult(reference="probe-delivered")

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, flaky)
    with _uow(tenant_id, runtime) as uow:
        message_id = _probe(uow, "probe:recovers", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"]
        uow.commit()

    def current() -> Mapping[str, Any]:
        [row] = _messages(tenant_id, id=message_id)
        return row

    assert relay(relayer) == RelayStats(claimed=1, dispatched=0, failed=1, dead=0)
    failed = current()
    assert (failed["status"], failed["attempt_count"], failed["last_error"]) == (
        "FAILED",
        1,
        "RuntimeError",
    )
    clock.set(failed["next_attempt_at"])
    assert relay(relayer) == RelayStats(claimed=1, dispatched=1, failed=0, dead=0)
    delivered = current()
    assert (
        delivered["status"],
        delivered["attempt_count"],
        delivered["last_error"],
        delivered["dispatched_at"],
    ) == ("DISPATCHED", 1, None, clock.now())
    assert answers == []


def test_a_failed_message_names_the_problem_not_its_class(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item JRN-DISPATCH-DEAD-1 (supervisor rulings R-118 (k) and R-119 (c); 04 T-INT-03 rev
    1.159; dev-guide DG-KRN-EVT-05 rev 1.142): a database error the unit of work mapped at its
    commit reaches the relay as a ``Problem`` — ``lock-conflict``, ``statement-timeout`` — and
    the class of every problem is the same word. ``last_error`` keeps the slug, which names what
    happened; any other error keeps its class, as before. Fail-first here:
    ``FAILED | 1 | Problem``."""
    relayer = _relayer(tenant_id, runtime)
    assert relay(relayer).dispatched == 1  # the provisioned invitation
    answers: list[Exception] = [
        Problem("lock-conflict", LOCK_CONFLICT_DETAIL),
        RuntimeError("the endpoint refused the delivery"),
    ]

    def failing(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        raise answers[int(payload["n"])]

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, failing)
    with _uow(tenant_id, runtime) as uow:
        mapped = _probe(uow, "probe:mapped", {"n": 0}, topic=OutboxTopic.WEBHOOK)["id"]
        other = _probe(uow, "probe:other", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"]
        uow.commit()
    assert relay(relayer) == RelayStats(claimed=2, dispatched=0, failed=2, dead=0)
    found = {
        row["id"]: (row["status"], row["attempt_count"], row["last_error"])
        for row in _messages(tenant_id, topic=OutboxTopic.WEBHOOK.value)
    }
    assert found == {mapped: ("FAILED", 1, "lock-conflict"), other: ("FAILED", 1, "RuntimeError")}
    assert outbox.error_name(answers[0]) == "lock-conflict"
    assert outbox.error_name(answers[1]) == "RuntimeError"


def test_a_message_does_not_die_before_its_topic_has_recorded_it(
    tenant_id: UUID, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item JRN-DISPATCH-DEAD-1 (05 ADP-31 and ADP-32 rev 1.98): a topic may say what the death of
    one of its messages means for the record that waits for the delivery (``DEAD_HOOKS``; a
    journal batch becomes ``failed``). The relay calls the hook before it records ``DEAD`` and
    only for a message that dies; when the hook cannot do its work the message is not settled —
    it stays claimed, the failed attempt uncounted — and the relay that takes it again after 15
    minutes dispatches it as the last attempt once more. ``DEAD`` and the hook's record are
    therefore written both or neither."""
    clock = runtime.clock
    assert isinstance(clock, FrozenClock)
    relayer = _relayer(tenant_id, runtime)
    assert relay(relayer).dispatched == 1  # the provisioned invitation
    dispatched: list[Mapping[str, Any]] = []

    def refusing(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        dispatched.append(payload)
        if payload["n"] == 1:
            raise outbox.Undeliverable("the endpoint is gone")
        raise RuntimeError("the endpoint timed out")

    with _uow(tenant_id, runtime) as uow:
        dying = _probe(uow, "probe:dies", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"]
        retried = _probe(uow, "probe:retried", {"n": 2}, topic=OutboxTopic.WEBHOOK)["id"]
        uow.commit()

    def current(message_id: UUID) -> tuple[Any, ...]:
        [row] = _messages(tenant_id, id=message_id)
        return (row["status"], row["attempt_count"], row["last_error"])

    hooked: list[tuple[Any, str, tuple[Any, ...]]] = []
    outcomes: list[Exception | None] = [RuntimeError("the record cannot be written"), None]

    def hook(jc: JobContext, payload: Mapping[str, Any], error: Exception) -> None:
        # the message is still claimed while the topic records what its death means
        hooked.append((payload["n"], outbox.error_name(error), current(dying)))
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, refusing)
    monkeypatch.setitem(outbox.DEAD_HOOKS, OutboxTopic.WEBHOOK, hook)
    # the dying message's hook fails: nothing of it is settled; the other message only failed
    # and is no business of the hook
    assert relay(relayer) == RelayStats(claimed=2, dispatched=0, failed=1, dead=0)
    assert hooked == [(1, "Undeliverable", ("DISPATCHING", 0, None))]
    assert current(dying) == ("DISPATCHING", 0, None)
    assert current(retried) == ("FAILED", 1, "RuntimeError")
    assert relay(relayer).claimed == 0  # the claim stands until it is 15 minutes old
    clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
    again = relay(relayer)
    assert (again.dead, len(hooked)) == (1, 2)
    assert hooked[1] == (1, "Undeliverable", ("DISPATCHING", 0, None))
    assert current(dying) == ("DEAD", 1, "Undeliverable")
    assert [payload["n"] for payload in dispatched].count(1) == 2 and outcomes == []


class _LapsingEmail:
    """The fake email adapter; after its first send the clock moves 15 minutes and ``meanwhile``
    runs before the send returns."""

    def __init__(self, inner: outbox.EmailSender, clock: FrozenClock) -> None:
        self._inner = inner
        self._clock = clock
        self.meanwhile: Callable[[], None] | None = None

    def send(self, message: outbox.EmailMessage) -> str:
        reference = self._inner.send(message)
        meanwhile, self.meanwhile = self.meanwhile, None
        if meanwhile is not None:
            self._clock.advance(timedelta(minutes=15))
            meanwhile()
        return reference


class _Stopped(BaseException):
    """The relay's process stops: no handler below the worker catches it."""


def _email_payload(n: int) -> dict[str, str]:
    return {
        "to": f"probe{n}@acme.test",
        "subject": "Probe",
        "text": "Probe message.",
        "reference": str(new_id()),
    }


def _run_relay_job(tenant_id: UUID, runtime: JobRuntime) -> UUID:
    """An OUTBOX_RELAY job, fetched and run to completion as a worker would."""
    now = runtime.clock.now()
    with tenant_session(_db(tenant_id)) as session:
        row = registry.insert_job(
            session,
            JobKind.OUTBOX_RELAY,
            {},
            tenant_id=tenant_id,
            now=now,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        )
        task_id = registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=now
        )
        session.execute(_FETCHED, {"id": task_id})
    job_id = UUID(str(row["id"]))
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    return job_id


def test_adp_32_live_relay_not_reclaimed(
    tenant_id: UUID,
    runtime: JobRuntime,
    app_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-R-02 (D-80): a relay claims one message at a time just before dispatching it, and the
    ADP-32 re-claim takes only messages whose own claim is more than 15 minutes old."""
    clock = runtime.clock
    assert isinstance(clock, FrozenClock)
    # The provisioned invitation goes out first, to the fixture's mail directory.
    assert relay(_relayer(tenant_id, runtime)).dispatched == 1

    relay_dir = tmp_path / "relays"
    settings = app_settings.model_copy(update={"run_dir": relay_dir})
    email = _LapsingEmail(build_email_sender(settings, clock), clock)
    relays = JobRuntime(
        clock=clock,
        keyring=runtime.keyring,
        files=runtime.files,
        email=email,
        public_origin=settings.public_origin,
    )
    with _uow(tenant_id, runtime) as uow:
        for n in range(3):
            _probe(uow, f"probe:mail:{n}", _email_payload(n))
        uow.commit()

    # Relay 1 sends the first message; relay 2 then runs to completion 15 minutes later.
    second: list[UUID] = []
    email.meanwhile = lambda: second.append(_run_relay_job(tenant_id, relays))
    first = _run_relay_job(tenant_id, relays)

    assert len(list((relay_dir / "mail").rglob("*.eml"))) == 3
    probes = _messages(tenant_id, aggregate_type="probe")
    assert [row["status"] for row in probes] == ["DISPATCHED"] * 3
    with tenant_session(_db(tenant_id)) as session:
        finished = {
            row.id: (row.state, row.result["counts"])
            for row in session.execute(
                select(job.c.id, job.c.state, job.c.result).where(job.c.id.in_([first, *second]))
            )
        }
    assert finished == {
        first: ("SUCCEEDED", {"claimed": 1, "dispatched": 1, "failed": 0, "dead": 0}),
        second[0]: ("SUCCEEDED", {"claimed": 2, "dispatched": 2, "failed": 0, "dead": 0}),
    }

    # A message left DISPATCHING by a relay that stopped is re-claimed once its claim is more than
    # 15 minutes old, and sent once.
    with _uow(tenant_id, runtime) as uow:
        stopped = _probe(uow, "probe:mail:stopped", _email_payload(3))["id"]
        uow.commit()

    def stopping(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        raise _Stopped

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.EMAIL, stopping)
    with pytest.raises(_Stopped):
        relay(_relayer(tenant_id, relays))
    monkeypatch.undo()
    [left] = _messages(tenant_id, id=stopped)
    assert left["status"] == "DISPATCHING"
    clock.advance(timedelta(minutes=15))
    assert relay(_relayer(tenant_id, relays)).claimed == 0
    clock.advance(timedelta(seconds=1))
    assert relay(_relayer(tenant_id, relays)) == RelayStats(
        claimed=1, dispatched=1, failed=0, dead=0
    )
    [sent] = _messages(tenant_id, id=stopped)
    assert (sent["status"], sent["dispatched_at"]) == ("DISPATCHED", clock.now())
    assert len(list((relay_dir / "mail").rglob("*.eml"))) == 4


def test_ntr_05_fake_email_file(
    acme: TenantProvisionResult, runtime: JobRuntime, run_dir: Path
) -> None:
    tenant_id = acme.tenant["id"]
    assert isinstance(tenant_id, UUID)
    assert relay(_relayer(tenant_id, runtime)) == RelayStats(
        claimed=1, dispatched=1, failed=0, dead=0
    )

    files = sorted((run_dir / "mail" / "acme-test").iterdir())
    assert [path.name for path in files] == [
        f"20260912T120000000000Z-{acme.admin_membership_id}.eml"
    ]
    raw = files[0].read_bytes()
    message = message_from_bytes(raw, policy=default)
    assert isinstance(message, EmailMessage)
    assert (message["To"], message["Subject"]) == (
        "admin@acme.test",
        "You are invited to Acme Test on eRev",
    )
    body = message.get_content()
    # The link starts with the configured EREV_PUBLIC_ORIGIN, which review worktrees change (D-70).
    link = re.search(
        rf"^{re.escape(runtime.public_origin)}/accept-invitation#token=([A-Za-z0-9_-]{{43}})\r?$",
        body,
        re.MULTILINE,
    )
    assert link is not None, body
    with tenant_session(_db(tenant_id)) as session:
        token_sha256 = session.execute(
            select(tenant_membership.c.invitation_token_sha256).where(
                tenant_membership.c.id == acme.admin_membership_id
            )
        ).scalar_one()
        dispatched = session.execute(
            select(func.count()).where(outbox_message.c.status == "DISPATCHED")
        ).scalar_one()
    assert hashlib.sha256(link.group(1).encode("ascii")).hexdigest() == token_sha256
    assert dispatched == 1
    # PRD NTF-R3: no amount leaves in an email.
    assert re.search(r"\d\.\d{2}\b", raw.decode("utf-8")) is None


def test_sar_15_smtp_host_guarded(clock: FrozenClock, monkeypatch: pytest.MonkeyPatch) -> None:
    """PR-R-08 (D-80): EREV_SMTP_HOST passes the SAR-15 guard before any socket connects."""
    attempts = network.record_connections(monkeypatch)
    message = outbox.EmailMessage(
        tenant_code="acme-test",
        reference=new_id(),
        to="admin@acme.test",
        subject="Probe",
        text="Probe",
    )

    def sender(env: Environment, address: str, port: int = 587) -> SmtpEmailSender:
        return SmtpEmailSender(
            host="smtp.acme.example",
            port=port,
            username=None,
            password=None,
            sender="erev@acme.test",
            clock=clock,
            env=env,
            resolve=lambda host, port: [address],
        )

    with pytest.raises(DestinationRefused):
        sender(Environment.PRODUCTION, "10.0.0.5").send(message)
    assert attempts == []

    # The client connects to the checked address: loopback is allowed under test, and nothing
    # listens on the port.
    port = network.unused_loopback_port()
    with pytest.raises(ConnectionRefusedError):
        sender(Environment.TEST, "127.0.0.1", port).send(message)
    assert attempts
    assert {tuple(attempt) for attempt in attempts} == {("127.0.0.1", port)}


def test_deploy_alert_names_1_the_relays_line_says_what_it_recorded(
    tenant_id: UUID,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """Item DEPLOY-ALERT-NAMES-1 (dev-guide DG-KRN-EVT-05 rev 1.206; 05 DPL-37 rev 1.162): the
    relay's line ``outbox.dispatch_failed`` carries ``outcome`` - what this relay recorded for
    the message - and is written once that is known. A failed attempt with attempts left reads
    ``FAILED``. The last attempt reads ``DEAD`` only when the message was recorded so: a message
    whose dead hook raised is not dead - it stays ``DISPATCHING`` - and reads ``UNSETTLED``,
    behind the hook's own line. The hosted SLO-05 alert matches ``outcome`` ``DEAD``, so it fires
    once for a message that died and not for an attempt that will be made again."""
    clock = runtime.clock
    assert isinstance(clock, FrozenClock)
    relayer = _relayer(tenant_id, runtime)
    assert relay(relayer).dispatched == 1  # the provisioned invitation

    def refusing(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        if payload["n"] == 1:
            raise outbox.Undeliverable("the endpoint is gone")
        raise RuntimeError("the endpoint timed out")

    with _uow(tenant_id, runtime) as uow:
        dying = str(_probe(uow, "probe:dies", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"])
        retried = str(_probe(uow, "probe:retried", {"n": 2}, topic=OutboxTopic.WEBHOOK)["id"])
        uow.commit()
    hook_raises = [True, False]

    def hook(jc: JobContext, payload: Mapping[str, Any], error: Exception) -> None:
        if hook_raises.pop(0):
            raise RuntimeError("the record cannot be written")

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, refusing)
    monkeypatch.setitem(outbox.DEAD_HOOKS, OutboxTopic.WEBHOOK, hook)

    def lines(message_id: str) -> list[tuple[Any, ...]]:
        """(event, level, attempt, error class, outcome) of the relay's lines on one message."""
        records = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
        return [
            (
                record["event"],
                record["level"],
                record["attempt"],
                record["error_class"],
                record.get("outcome"),
            )
            for record in records
            if record.get("outbox_message_id") == message_id
        ]

    # The dying message's hook raises: nothing of it is recorded, and the line does not say DEAD.
    assert relay(relayer) == RelayStats(claimed=2, dispatched=0, failed=1, dead=0)
    unsettled = [
        ("outbox.dead_hook_failed", "error", 1, "RuntimeError", None),
        ("outbox.dispatch_failed", "warning", 1, "Undeliverable", outbox.UNSETTLED),
    ]
    assert lines(dying) == unsettled
    assert [row["status"] for row in _messages(tenant_id, id=UUID(dying))] == ["DISPATCHING"]
    failed = ("outbox.dispatch_failed", "warning", 1, "RuntimeError", "FAILED")
    assert lines(retried) == [failed]

    # The relay that takes the message again records it DEAD: one line says so.
    clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
    assert relay(relayer).dead == 1
    assert lines(dying) == [
        *unsettled,
        ("outbox.dispatch_failed", "warning", 1, "Undeliverable", "DEAD"),
    ]
    assert [row["status"] for row in _messages(tenant_id, id=UUID(dying))] == ["DEAD"]
    # The other message was due again and failed again: a second attempt, still not dead.
    assert lines(retried) == [
        failed,
        ("outbox.dispatch_failed", "warning", 2, "RuntimeError", "FAILED"),
    ]
    # What the hosted filter matches - the event with outcome DEAD - is one line: the dead
    # message's.
    matched = [
        record["outbox_message_id"]
        for record in (json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip())
        if record.get("event") == "outbox.dispatch_failed" and record.get("outcome") == "DEAD"
    ]
    assert matched == [dying]


def test_deploy_alert_names_1_the_line_is_written_when_the_recording_fails(
    tenant_id: UUID,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """Item DEPLOY-ALERT-NAMES-1: the relay's line is written after the settlement, and a
    settlement that itself raises does not lose it - the line says ``UNSETTLED``, the error goes
    on to the job, and the message stays claimed for the relay that takes it again."""
    relayer = _relayer(tenant_id, runtime)
    assert relay(relayer).dispatched == 1  # the provisioned invitation

    def refusing(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        raise RuntimeError("the endpoint timed out")

    def unrecorded(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("the database went away")

    with _uow(tenant_id, runtime) as uow:
        message_id = _probe(uow, "probe:unrecorded", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"]
        uow.commit()
    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, refusing)
    monkeypatch.setattr(outbox, "_record", unrecorded)
    with pytest.raises(ConnectionError):
        relay(relayer)
    records = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    assert [
        (record["event"], record["attempt"], record["error_class"], record["outcome"])
        for record in records
        if record.get("outbox_message_id") == str(message_id)
    ] == [("outbox.dispatch_failed", 1, "RuntimeError", outbox.UNSETTLED)]
    assert [row["status"] for row in _messages(tenant_id, id=message_id)] == ["DISPATCHING"]


def test_deploy_alert_names_1_a_relay_that_lost_its_claim_records_nothing(
    tenant_id: UUID,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """Item DEPLOY-ALERT-NAMES-1 (dev-guide DG-KRN-EVT-05 rev 1.206; 05 ADP-32): a relay whose
    claim a later relay has taken records nothing, and its line says so - ``UNSETTLED`` - while
    the later relay's line states what the message was recorded as. One failed attempt is
    counted, by the relay that held the claim."""
    clock = runtime.clock
    assert isinstance(clock, FrozenClock)
    relayer = _relayer(tenant_id, runtime)
    assert relay(relayer).dispatched == 1  # the provisioned invitation
    with _uow(tenant_id, runtime) as uow:
        message_id = _probe(uow, "probe:retaken", {"n": 1}, topic=OutboxTopic.WEBHOOK)["id"]
        uow.commit()
    later: list[RelayStats] = []
    lapsed: list[bool] = []

    def slow_and_refusing(jc: JobContext, payload: Mapping[str, Any]) -> DispatchResult:
        if not lapsed:
            # The first relay's dispatch outlasts its claim: fifteen minutes on, a later relay
            # takes the message, fails too and records the attempt.
            lapsed.append(True)
            clock.advance(outbox.STRANDED_AFTER + timedelta(seconds=1))
            later.append(relay(_relayer(tenant_id, runtime)))
        raise RuntimeError("the endpoint timed out")

    monkeypatch.setitem(outbox.HANDLERS, OutboxTopic.WEBHOOK, slow_and_refusing)
    assert relay(relayer) == RelayStats(claimed=1, dispatched=0, failed=0, dead=0)
    assert later == [RelayStats(claimed=1, dispatched=0, failed=1, dead=0)]
    records = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    assert [
        (record["event"], record["attempt"], record["error_class"], record["outcome"])
        for record in records
        if record.get("outbox_message_id") == str(message_id)
    ] == [
        ("outbox.dispatch_failed", 1, "RuntimeError", "FAILED"),
        ("outbox.dispatch_failed", 1, "RuntimeError", outbox.UNSETTLED),
    ]
    [row] = _messages(tenant_id, id=message_id)
    assert (row["status"], row["attempt_count"]) == ("FAILED", 1)
