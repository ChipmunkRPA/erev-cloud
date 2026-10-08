"""Job registry KRN-JOB (dev-guide §5.12 DG-KRN-JOB-01 to 05, 09, 10; 05 §5.6 JOB-01 to JOB-03).

A long operation is a ``job`` row (T-PLT-27) wrapping the Procrastinate task ``erev.run_job``.
``defer`` writes the row in the business transaction and registers an after-commit hook that
defers the task with ``queueing_lock = str(job id)`` and records ``procrastinate_job_id`` in one
short tenant transaction (DG-KRN-JOB-02). ``run_job`` is the task body: the state check, a
per-tenant slot (DG-KRN-JOB-03), the handler, retries (DG-KRN-JOB-05) and the final state, which is
``CANCELLED`` when ``POST /jobs/{id}/cancel`` asked the handler to stop (05 JOB-05).
``fail_attempt`` settles a failed or stalled attempt: it re-queues the job while attempts remain;
after the last attempt the job is FAILED with its problem and the initiator receives ``JOB_FAILED``
in the same transaction (05 JOB-06, JOB-07; PRD NTF-05). Only the attempt whose Procrastinate task
the row names records its completion or failure (D-80). ``retry_stranded`` recovers a QUEUED job
whose task failed, was cancelled or aborted, or stalled with a dead worker, within the same retry
policy (05 SCH-04).

Whom a failed job is told to (05 JOB-07 rev 1.165; item JOB-FAILED-ITEM-1; BUILD_SPEC BS1-D-13
had deferred the exception item): every end of a job as FAILED passes ``_fail_job``, which in its
transaction notifies a user initiator, runs the kind's failure hook and, for a kind that
registered a ``FailedItem`` with its handler, raises the exception item ``JOB_FAILED`` of the one
legal entity the job's record names — the hook and the item each in a savepoint of the unit of
work, so that a failure of either leaves nothing behind and the job still ends FAILED. After the
commit it raises the operator alert ``JOB_FAILED`` for a job that no user started. A later job of
the kind and record that runs to its end settles the open item (``_settle_failed_item``). The
exception queue is a domain module, which this module cannot import (DG-ARC-01): its functions
come inside the ``FailedItem`` that ``domain.imports.job_items.failed_item`` builds.

Audit (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a)): the registry writes ``job.start`` in the
transaction that inserts the row — ``defer`` through the unit of work (the deferring principal,
under its request id), the scheduler fan-out as SYSTEM under the sweep's request id — and
``job.finish`` as SYSTEM in the transaction that records a terminal state (``after`` holds the
state and the slug of the problem); ``domain.platform.jobs.cancel_job`` writes ``job.cancel``.
The transport kinds of the outbox (``TRANSPORT_KINDS``) write neither ``job.start`` nor
``job.finish``: 04 T-INT-03 audits the originating command.
Handlers register through ``task`` in the modules the worker imports; the DG-ARC-08 test names the
kinds later phases build in ``PENDING_JOB_HANDLERS`` (BS-D-07).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import lru_cache, partial
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, LiteralString
from uuid import UUID

from procrastinate import manager as procrastinate_manager
from procrastinate import tasks as procrastinate_tasks
from procrastinate.connector import BaseConnector
from procrastinate.sync_psycopg_connector import SyncPsycopgConnector
from psycopg.rows import dict_row
from sqlalchemy import Select, and_, func, insert, or_, select, text, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from erev_api.audit.chain import append_events
from erev_api.audit.writer import build_event, principal_actor
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import Clock
from erev_api.controls.operator_alerts import AlertRaiser, job_failed_alert
from erev_api.controls.release import current_release
from erev_api.db import new_id
from erev_api.db.session import (
    DbContext,
    lock_connection,
    of_session_tenant,
    platform_session,
    process_keyring,
    tenant_session,
)
from erev_api.db.tables.platform import job, tenant, tenant_membership
from erev_api.db.transitions import apply
from erev_api.enums import (
    ExceptionSource,
    JobKind,
    JobState,
    NotificationKind,
    PrincipalKind,
    TenantStatus,
)
from erev_api.jobs.context import (
    JobAttempt,
    JobContext,
    JobLost,
    JobRuntime,
    system_unit_of_work,
    try_unit_lock,
)
from erev_api.logging import get_logger, raised_at, register_logger_fields
from erev_api.problems import TYPE_BASE, Problem, ProblemError
from erev_api.registry.resolve import setting

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: tuple[int, ...] = (30, 120, 600)


@dataclass(frozen=True, slots=True)
class JobOutcome:
    state: Literal["SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"]
    result: Mapping[str, Any]  # {"href": "/api/v1/…", "counts": {…}}


Handler = Callable[[JobContext, Mapping[str, Any]], JobOutcome]
# The record a job works on ends with the job: called with the unit of work that ends the job
# FAILED, the job's params and its problem, after the last attempt (BUILD_SPEC RPS-2; RV-14).
type FailureHook = Callable[[UnitOfWork, Mapping[str, Any], Mapping[str, Any]], None]
type CancellationHook = Callable[[UnitOfWork, Mapping[str, Any], UUID], None]
# Read-only dependency check while QUEUED: False defers without using a handler attempt.
# A domain Problem is terminal (missing/failed dependency); infrastructure errors propagate
# to the existing stranded-task recovery rather than being mistaken for readiness.
type ReadyHook = Callable[[Session, UUID, Mapping[str, Any]], bool]


@dataclass(frozen=True, slots=True)
class FailedSubject:
    """What the exception item of a failed job names (05 JOB-07 rev 1.165; 04 §15.4
    ``JOB_FAILED``): the one legal entity of the record the job works on, the period where the
    record has one, and the record itself where the queue links an item to it. ``key`` is the
    record's business key where the job's subject id is not what a later job of the kind works
    on again — a journal run or a reconciliation that the job itself creates under a new id, a
    sync run of a connection; without it the record is the subject id."""

    entity_id: UUID
    period_id: UUID | None = None
    key: str | None = None
    contract_id: UUID | None = None
    combination_group_id: UUID | None = None
    import_upload_id: UUID | None = None
    sync_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class FailedJob:
    """A job that ended FAILED and whose record names one legal entity, as the exception queue
    receives it."""

    job_id: UUID
    kind: JobKind
    label: str  # JOB_LABELS[kind]
    attempt: int
    problem: Mapping[str, Any]  # the stored RFC 9457 object
    record: str  # the subject's business key, or the job's subject id
    subject: FailedSubject


# Reads the record a failed job works on, in the transaction that ends the job: the session, the
# job's ``subject_type`` and ``subject_id`` and its params. None when the record names no legal
# entity or several; then no item is raised, because an item without an entity is read by every
# scope.
type SubjectReader = Callable[[Session, str | None, UUID, Mapping[str, Any]], FailedSubject | None]


@dataclass(frozen=True, slots=True)
class FailedItem:
    """A kind whose failed job leaves the exception item ``JOB_FAILED`` (05 JOB-07 rev 1.165):
    the E-42 source of the item, the reader of the job's subject, and the exception queue's three
    functions for the kind and record — raise the item, say whether one is open, settle it. Built
    by ``domain.imports.job_items.failed_item``: this module imports no domain module
    (DG-ARC-01), so the queue's functions come with the registration, and a kind that has a
    reader has them."""

    source: ExceptionSource
    subject: SubjectReader
    raise_item: Callable[[UnitOfWork, FailedJob], None]
    is_open: Callable[[Session, JobKind, str], bool]
    settle: Callable[[UnitOfWork, JobKind, str, UUID], None]  # …, the record, the job that ran


QueueName = Literal[
    "compute", "imports", "close", "outbox", "reports", "maintenance", "integrations", "ai"
]
QUEUES: Final[tuple[QueueName, ...]] = (
    "compute",
    "imports",
    "close",
    "outbox",
    "reports",
    "maintenance",
    "integrations",
    "ai",
)
# DG-KRN-JOB-10: the 05 §5.6 execution profile table.
JOB_QUEUE: Final[Mapping[JobKind, QueueName]] = MappingProxyType(
    {
        JobKind.CONTRACT_COMPUTE: "compute",
        JobKind.REPLAY_VERIFY: "compute",
        JobKind.POLICY_SIMULATION: "compute",
        JobKind.IMPORT_VALIDATE: "imports",
        JobKind.IMPORT_DIFF: "imports",
        JobKind.IMPORT_COMMIT: "imports",
        JobKind.MIGRATION_IMPORT: "imports",
        JobKind.MIGRATION_RECONCILE: "imports",
        JobKind.CLOSE_RUN: "close",
        JobKind.JOURNAL_RUN_CALCULATE: "close",
        JobKind.RECONCILIATION_GENERATE: "close",
        JobKind.PERIOD_OPEN_REDIRTY: "close",
        JobKind.JOURNAL_EXPORT: "outbox",
        JobKind.OUTBOX_RELAY: "outbox",
        JobKind.WEBHOOK_DELIVERY: "outbox",
        JobKind.EMAIL_DELIVERY: "outbox",
        JobKind.REPORT_RUN: "reports",
        JobKind.EVIDENCE_PACK: "reports",
        JobKind.FORECAST_RUN: "reports",
        JobKind.DEAL_PREVIEW: "reports",
        JobKind.SSP_CALCULATOR: "reports",
        JobKind.AUDIT_CHAIN_VERIFY: "maintenance",
        JobKind.TENANT_SNAPSHOT: "maintenance",
        JobKind.SANDBOX_RESET: "maintenance",
        JobKind.RETENTION_SWEEP: "maintenance",
        JobKind.SYNC_RUN: "integrations",
        JobKind.AI_TASK: "ai",
    }
)
# The "<job label>" of PRD NTF-05, ERR-49 and SCREENS SCR-ST-12, one per E-14 kind.
JOB_LABELS: Final[Mapping[JobKind, str]] = MappingProxyType(
    {
        JobKind.CONTRACT_COMPUTE: "Contract computation",
        JobKind.REPLAY_VERIFY: "Replay verification",
        JobKind.POLICY_SIMULATION: "Policy simulation",
        JobKind.IMPORT_VALIDATE: "Import validation",
        JobKind.IMPORT_DIFF: "Import dry run",
        JobKind.IMPORT_COMMIT: "Import commit",
        JobKind.MIGRATION_IMPORT: "Legacy database import",
        JobKind.MIGRATION_RECONCILE: "Migration reconciliation",
        JobKind.CLOSE_RUN: "Close run",
        JobKind.JOURNAL_RUN_CALCULATE: "Journal run calculation",
        JobKind.RECONCILIATION_GENERATE: "Reconciliation generation",
        JobKind.PERIOD_OPEN_REDIRTY: "Contract re-marking",
        JobKind.JOURNAL_EXPORT: "Journal export",
        JobKind.OUTBOX_RELAY: "Outbox relay",
        JobKind.WEBHOOK_DELIVERY: "Webhook delivery",
        JobKind.EMAIL_DELIVERY: "Email delivery",
        JobKind.REPORT_RUN: "Report run",
        JobKind.EVIDENCE_PACK: "Evidence pack",
        JobKind.FORECAST_RUN: "Forecast run",
        JobKind.DEAL_PREVIEW: "Deal preview",
        JobKind.SSP_CALCULATOR: "SSP calculator",
        JobKind.AUDIT_CHAIN_VERIFY: "Audit chain verification",
        JobKind.TENANT_SNAPSHOT: "Workspace snapshot",
        JobKind.SANDBOX_RESET: "Sandbox reset",
        JobKind.RETENTION_SWEEP: "Retention sweep",
        JobKind.SYNC_RUN: "Integration sync",
        JobKind.AI_TASK: "AI task",
    }
)
JOB_FAILED_TITLE: Final = "Job failed: {label}"  # PRD NTF-05
JOB_FAILED_BODY: Final = "{label} failed at {step}: {reason}. Nothing was committed."
# The problem of a RUNNING job the sweeper stopped after ten minutes without a heartbeat (05
# JOB-06; dev-guide DG-KRN-JOB-06). The slug is also that of a job whose task never started it
# (``sweeper.STRANDED_DETAIL``); the detail tells the two apart.
STALL_SLUG: Final = "job-stalled"
STALL_DETAIL: Final = "no heartbeat for 10 minutes"
# PRD NTF-05 rev 1.191 (item JOB-STALL-COMMIT-RACE-1): the body for a job stopped as stalled. What
# its attempt had committed by then - the earlier chunks of a chunked job - stays; nothing of it
# is committed afterwards (05 JOB-06 rev 1.200), which is all the sweeper can say.
JOB_STALLED_BODY: Final = (
    "{label} failed at {step}: {reason}. The job was stopped; what it had not committed by then "
    "is not kept."
)
JOB_SUBJECT: Final = "job"
# 04 T-PLT-27 (rev 1.106; supervisor rulings R-50 (a), R-62 (a)): the audit actions of a job. A
# job of a transport kind writes neither START_ACTION nor FINISH_ACTION — it delivers what an
# audited command wrote (04 T-INT-03 "the originating command is audited"; T-PLT-36). Every E-14
# kind is in exactly one of the two sets (tests/unit/test_jobs_registry.py), so a new kind cannot
# fall outside both.
START_ACTION: Final = "job.start"
FINISH_ACTION: Final = "job.finish"
CANCEL_ACTION: Final = "job.cancel"
TRANSPORT_KINDS: Final = frozenset(
    {JobKind.OUTBOX_RELAY, JobKind.EMAIL_DELIVERY, JobKind.WEBHOOK_DELIVERY}
)
AUDITED_KINDS: Final = frozenset(
    {
        JobKind.CONTRACT_COMPUTE,
        JobKind.REPLAY_VERIFY,
        JobKind.POLICY_SIMULATION,
        JobKind.IMPORT_VALIDATE,
        JobKind.IMPORT_DIFF,
        JobKind.IMPORT_COMMIT,
        JobKind.MIGRATION_IMPORT,
        JobKind.MIGRATION_RECONCILE,
        JobKind.CLOSE_RUN,
        JobKind.JOURNAL_RUN_CALCULATE,
        JobKind.JOURNAL_EXPORT,
        JobKind.REPORT_RUN,
        JobKind.EVIDENCE_PACK,
        JobKind.FORECAST_RUN,
        JobKind.DEAL_PREVIEW,
        JobKind.SSP_CALCULATOR,
        JobKind.AUDIT_CHAIN_VERIFY,
        JobKind.TENANT_SNAPSHOT,
        JobKind.SANDBOX_RESET,
        JobKind.RETENTION_SWEEP,
        JobKind.SYNC_RUN,
        JobKind.AI_TASK,
        JobKind.RECONCILIATION_GENERATE,
        JobKind.PERIOD_OPEN_REDIRTY,
    }
)
RUN_JOB_TASK: Final = "erev.run_job"
SLOT_RETRY_DELAY: Final = timedelta(seconds=5)
DEFAULT_RETRY: Final = RetryPolicy()
STALLED_HEARTBEAT_SECONDS: Final = 30  # 05 JOB-06: a worker silent for 30 seconds has stalled
# D-80: Procrastinate task statuses that leave a QUEUED job without a task that can run it.
REDISPATCHED_STATUSES: Final = frozenset({"failed", "cancelled", "aborted"})
_LOGGER: Final = "erev_api.jobs"
# What ``_fail_job`` reads of the job it ends: its initiator, its params for the failure hook and
# its subject for the exception item (05 JOB-07 rev 1.165).
_FAILING: Final = (
    job.c.kind,
    job.c.queue,
    job.c.created_by,
    job.c.created_by_kind,
    job.c.params,
    job.c.subject_type,
    job.c.subject_id,
)
# The states of a job that ran to its end: they settle the open ``JOB_FAILED`` item of the job's
# kind and record (05 JOB-07 rev 1.165). A cancelled job did not.
_RAN_TO_ITS_END: Final = frozenset({JobState.SUCCEEDED, JobState.SUCCEEDED_WITH_EXCEPTIONS})
# 05 REL-05: the enqueuing process's release travels in job.params; a worker of another release
# re-defers the job for 30 seconds up to 10 times, then fails it with `release-mismatch` (503).
RELEASE_PARAM: Final = "engine_release_id"
RELEASE_MISMATCH_DELAY: Final = timedelta(seconds=30)
RELEASE_MISMATCH_MAX_DEFERRALS: Final = 10
_RESERVED_PARAMS: Final = frozenset({RELEASE_PARAM})

register_logger_fields(
    _LOGGER,
    (
        "job_id",
        "job_kind",
        "attempt",
        "error_class",
        "error_at",
        "enqueuer_release_id",
        "worker_release_id",
        "release_mismatch_deferrals",
        "delivered_task_id",
        "current_task_id",
        "tenant_id",
        "silent_seconds",
    ),
)


def handler_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """The caller's params without the registry's reserved keys (REL-05 `engine_release_id`)."""
    return {key: value for key, value in params.items() if key not in _RESERVED_PARAMS}


PIN_UNVERIFIED: Final = "unverified"  # the runtime stamped no release (tests, run_inline)
PIN_MATCH: Final = "match"
PIN_MISMATCH: Final = "mismatch"
PIN_UNPINNED: Final = "unpinned"  # no key: queued before REL-05 or by an unstamped process
PIN_MALFORMED: Final = "malformed"  # a key that is not a release id


@dataclass(frozen=True, slots=True)
class ReleasePin:
    """How a job's recorded enqueuing release relates to the worker's (05 REL-05)."""

    kind: str
    enqueuer: str | None  # the recorded value as text, when it can be shown


def classify_release_pin(params: Mapping[str, Any], worker_release_id: UUID | None) -> ReleasePin:
    """Classify ``params.engine_release_id`` against the worker's stamped release.

    ``unverified`` (no worker release) compares nothing; ``match`` runs; ``mismatch`` and
    ``unpinned`` follow the bounded REL-05 deferral and then fail closed; ``malformed`` fails at
    once. A legacy job is never assumed compatible.
    """
    value = params.get(RELEASE_PARAM)
    shown = None if value is None and RELEASE_PARAM not in params else repr(value)[:64]
    if worker_release_id is None:
        return ReleasePin(PIN_UNVERIFIED, shown)
    if RELEASE_PARAM not in params:
        return ReleasePin(PIN_UNPINNED, None)
    pinned: UUID | None = None
    if isinstance(value, str):
        try:
            pinned = UUID(value)
        except ValueError:
            pinned = None
    if pinned is None:
        return ReleasePin(PIN_MALFORMED, shown)
    return ReleasePin(PIN_MATCH if pinned == worker_release_id else PIN_MISMATCH, str(pinned))


_TASK_ARGS = text("SELECT args FROM procrastinate_jobs WHERE id = :id")


def _task_release_deferrals(session: Session, task_id: int | None) -> int:
    """The REL-05 deferral count a Procrastinate task carries (0 when absent)."""
    if task_id is None:
        return 0
    args = session.execute(_TASK_ARGS, {"id": task_id}).scalar_one_or_none()
    value = args.get("release_mismatch_deferrals") if isinstance(args, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


@dataclass(frozen=True, slots=True)
class HandlerSpec:
    handler: Handler
    retry: RetryPolicy
    on_failure: FailureHook | None = None
    failed_item: FailedItem | None = None
    on_cancel: CancellationHook | None = None
    failure_hook_required: bool = False
    ready: ReadyHook | None = None
    cancel_guard: CancellationHook | None = None


# One handler per E-14 kind (DG-KRN-JOB-01), filled by ``task`` when handler modules are imported.
HANDLERS: Final[dict[JobKind, HandlerSpec]] = {}


def task(
    kind: JobKind,
    *,
    retry: RetryPolicy = DEFAULT_RETRY,
    on_failure: FailureHook | None = None,
    failed_item: FailedItem | None = None,
    on_cancel: CancellationHook | None = None,
    failure_hook_required: bool = False,
    ready: ReadyHook | None = None,
    cancel_guard: CancellationHook | None = None,
) -> Callable[[Handler], Handler]:
    """Register the handler of ``kind``; its queue is ``JOB_QUEUE[kind]``. ``on_failure`` runs in
    the transaction that ends the job FAILED after its last attempt (BUILD_SPEC RPS-2).
    ``failure_hook_required`` rolls back settlement if subject cleanup fails, so the sweeper
    can retry instead of leaving a terminal job with an unfinished subject.
    ``on_cancel`` settles the subject when a queued job is cancelled, atomically with the job.
    A hook error aborts cancellation rather than stranding the subject.
    ``cancel_guard`` checks the subject under the job row lock before either queued or running
    cancellation; it can reject a cancellation after an atomic subject completion.
    ``ready`` reads retained dependencies before a slot/attempt is taken. False keeps the job
    QUEUED and schedules another delivery without spending retry budget; a Problem settles
    the job through its failure hook. It must not mutate business state.
    ``failed_item`` makes such a job leave the exception item ``JOB_FAILED`` when its record
    names one legal entity (05 JOB-07 rev 1.165); a kind whose failure hook raises an item of
    its own registers none."""

    def register(handler: Handler) -> Handler:
        if kind in HANDLERS:
            raise ValueError(f"job kind {kind.value} already has a handler (DG-KRN-JOB-01)")
        HANDLERS[kind] = HandlerSpec(
            handler=handler,
            retry=retry,
            on_failure=on_failure,
            failed_item=failed_item,
            on_cancel=on_cancel,
            failure_hook_required=failure_hook_required,
            ready=ready,
            cancel_guard=cancel_guard,
        )
        return handler

    return register


def backoff_delay(retry: RetryPolicy, attempt: int) -> timedelta:
    """The wait before the attempt after ``attempt``; the last step repeats (DG-KRN-JOB-05)."""
    steps = retry.backoff_seconds
    return timedelta(seconds=steps[min(max(attempt, 1), len(steps)) - 1])


CONCURRENCY_KEY: Final = "platform.job_concurrency"  # T-PLT-31; REQ-PLT-029


def job_concurrency(session: Session, *, known_at: datetime) -> int:
    """The session tenant's ``platform.job_concurrency`` at ``known_at`` (DG-KRN-JOB-03)."""
    return int(setting(session, CONCURRENCY_KEY, known_at=known_at))


def _system_context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _system_stamp(now: datetime) -> dict[str, Any]:
    return {"updated_at": now, "updated_by": None, "updated_by_kind": PrincipalKind.SYSTEM.value}


def start_is_audited(kind: JobKind) -> bool:
    """Whether a job of ``kind`` writes ``job.start`` and ``job.finish`` (04 T-PLT-27): every kind
    but the transport kinds of the outbox. A kind in neither set would be audited; the unit test
    that compares ``AUDITED_KINDS`` and ``TRANSPORT_KINDS`` with E-14 keeps that case from
    existing."""
    return kind not in TRANSPORT_KINDS


def start_facts(row: Mapping[str, Any]) -> dict[str, Any]:
    """The ``after`` of ``job.start``: what the job is and what it works on, never its params."""
    return {
        "kind": str(row["kind"]),
        "state": str(row["state"]),
        "queue": str(row["queue"]),
        "priority": row["priority"],
        "parent_job_id": row["parent_job_id"],
        "subject_type": row["subject_type"],
        "subject_id": row["subject_id"],
    }


def problem_slug(problem: Mapping[str, Any] | None) -> str | None:
    """The slug of a stored RFC 9457 object: its ``type`` without the catalogue base, so an
    unexpected error reads ``about:blank`` (``failure_problem``); None without a problem."""
    if problem is None:
        return None
    return str(problem["type"]).removeprefix(TYPE_BASE)


def stopped_as_stalled(problem: Mapping[str, Any]) -> bool:
    """Whether ``problem`` is that of a RUNNING job the sweeper stopped after ten minutes without
    a heartbeat - not that of a job whose task never started it, which shares the slug."""
    return problem_slug(problem) == STALL_SLUG and problem.get("detail") == STALL_DETAIL


def job_failed_body(*, label: str, step: str, reason: str, problem: Mapping[str, Any]) -> str:
    """The body of NTF-05 for a job that ended FAILED with ``problem`` (PRD NTF-05 rev 1.191): a
    job stopped as stalled is told what was not kept, every other one that nothing was
    committed. The kernel's notice to the initiator and a kind's own notice share it."""
    body = JOB_STALLED_BODY if stopped_as_stalled(problem) else JOB_FAILED_BODY
    return body.format(label=label, step=step, reason=reason)


def finish_facts(
    kind: JobKind, state: JobState, problem: Mapping[str, Any] | None
) -> dict[str, Any]:
    """The ``after`` of ``job.finish``: the terminal state and the slug of the problem."""
    return {"kind": kind.value, "state": state.value, "problem": problem_slug(problem)}


def _append_job_event(
    session: Session,
    *,
    principal: Principal,
    request_id: str,
    now: datetime,
    action: str,
    job_id: UUID,
    after: Mapping[str, Any],
    keyring: KeyRing | None,
) -> None:
    """Append one job event to the tenant chain in ``session``'s transaction, for the writers that
    hold no unit of work (the scheduler fan-out and the handler's final transition). The chain
    head is the last lock of the transaction (DG-KRN-DB-08): nothing is locked after this call."""
    append_events(
        session,
        tenant_id=principal.tenant_id,
        keyring=process_keyring() if keyring is None else keyring,
        events=[
            build_event(
                tenant_id=principal.tenant_id,
                actor=principal_actor(principal, request_id=request_id),
                occurred_at=now,
                action=action,
                object_type=JOB_SUBJECT,
                object_id=job_id,
                after=after,
            )
        ],
    )


@lru_cache(maxsize=1)
def _job_manager() -> procrastinate_manager.JobManager:
    """A Procrastinate job manager that runs its queries on a borrowed connection only."""
    return procrastinate_manager.JobManager(connector=SyncPsycopgConnector())


class _SessionConnector(BaseConnector):
    """A Procrastinate connector whose queries run on a SQLAlchemy session's psycopg connection,
    inside that session's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_sync_connector(self) -> BaseConnector:
        return self

    def _cursor(self) -> Any:
        driver = self._session.connection().connection.driver_connection
        if driver is None:
            raise RuntimeError("the session has no psycopg connection")
        return driver.cursor(row_factory=dict_row)

    def execute_query(self, query: LiteralString, **arguments: Any) -> None:
        with self._cursor() as cursor:
            cursor.execute(query, arguments)

    def execute_query_all(self, query: LiteralString, **arguments: Any) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute(query, arguments)
            return list(cursor.fetchall())

    async def execute_query_all_async(
        self, query: LiteralString, **arguments: Any
    ) -> list[dict[str, Any]]:
        return self.execute_query_all(query, **arguments)


def stalled_task_ids(session: Session) -> frozenset[int]:
    """The ``erev.run_job`` tasks in ``doing`` whose worker stopped heartbeating 30 seconds ago,
    through ``JobManager.get_stalled_jobs`` (05 JOB-06; D-80)."""
    manager = procrastinate_manager.JobManager(connector=_SessionConnector(session))
    stalled = asyncio.run(
        manager.get_stalled_jobs(
            task_name=RUN_JOB_TASK, seconds_since_heartbeat=STALLED_HEARTBEAT_SECONDS
        )
    )
    return frozenset(int(task.id) for task in stalled if task.id is not None)


def dispatch(
    session: Session,
    *,
    job_id: UUID,
    tenant_id: UUID,
    queue: str,
    now: datetime,
    attempt: int = 1,
    delay: timedelta | None = None,
    release_mismatch_deferrals: int = 0,
) -> int:
    """Defer ``erev.run_job`` in ``session``'s transaction and record its id (DG-KRN-JOB-02).

    The Procrastinate row is written on the session's own connection, so the task and
    ``procrastinate_job_id`` commit together or not at all. ``release_mismatch_deferrals`` (REL-05)
    rides in the task's arguments, because ``job.params`` never changes after insert.
    """
    deferrer = procrastinate_tasks.configure_task(
        name=RUN_JOB_TASK,
        job_manager=_job_manager(),
        queue=queue,
        queueing_lock=str(job_id),
        schedule_at=None if delay is None else now + delay,
        connection=session.connection().connection.driver_connection,
    )
    task_args: dict[str, Any] = {
        "job_id": str(job_id),
        "tenant_id": str(tenant_id),
        "attempt": attempt,
    }
    if release_mismatch_deferrals:
        task_args["release_mismatch_deferrals"] = release_mismatch_deferrals
    procrastinate_job_id = deferrer.defer(**task_args)
    session.execute(
        update(job)
        .where(job.c.tenant_id == tenant_id, job.c.id == job_id)
        .values(procrastinate_job_id=procrastinate_job_id, **_system_stamp(now))
    )
    return procrastinate_job_id


def _dispatch_hook(*, tenant_id: UUID, job_id: UUID, queue: str, clock: Clock) -> None:
    with tenant_session(_system_context(tenant_id)) as session:
        dispatch(session, job_id=job_id, tenant_id=tenant_id, queue=queue, now=clock.now())


def insert_job(
    session: Session,
    kind: JobKind,
    params: Mapping[str, Any],
    *,
    tenant_id: UUID,
    now: datetime,
    created_by: UUID | None,
    created_by_kind: PrincipalKind,
    priority: int = 0,
    parent_job_id: UUID | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
) -> Mapping[str, Any]:
    """Insert one QUEUED job row in ``session``'s transaction; the caller dispatches it.

    05 REL-05: the process's stamped release is recorded as ``params.engine_release_id`` on every
    enqueue; the key is reserved, so no caller can name another enqueuer (tests stamp through
    ``erev_api.controls.release.remember_release``).
    """
    if RELEASE_PARAM in params:
        raise ValueError(f"params.{RELEASE_PARAM} is reserved for the enqueuing release (REL-05)")
    stored = dict(params)
    stamped = current_release()
    if stamped is not None:
        stored[RELEASE_PARAM] = str(stamped.id)
    row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "kind": kind.value,
        "state": JobState.QUEUED.value,
        "params": stored,
        "queue": JOB_QUEUE[kind],
        "priority": priority,
        "parent_job_id": parent_job_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "created_at": now,
        "created_by": created_by,
        "created_by_kind": created_by_kind.value,
        "updated_at": now,
        "updated_by": created_by,
        "updated_by_kind": created_by_kind.value,
    }
    session.execute(insert(job).values(**row))
    return MappingProxyType(row)


def defer(
    uow: UnitOfWork,
    kind: JobKind,
    params: Mapping[str, Any],
    *,
    priority: int = 0,
    parent_job_id: UUID | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
) -> Mapping[str, Any]:
    """Insert a QUEUED job in the business transaction; dispatch after commit (DG-KRN-JOB-02).

    The unit of work's principal starts the job: ``job.start`` joins the events of the same
    transaction under its request id (04 T-PLT-27), but for a transport kind.
    """
    principal = uow.principal
    row = insert_job(
        uow.session,
        kind,
        params,
        tenant_id=principal.tenant_id,
        now=uow.now,
        created_by=principal.id,
        created_by_kind=principal.kind,
        priority=priority,
        parent_job_id=parent_job_id,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    if start_is_audited(kind):
        uow.audit(
            action=START_ACTION,
            object_type=JOB_SUBJECT,
            object_id=row["id"],
            after=start_facts(row),
        )
    uow.after_commit(
        partial(
            _dispatch_hook,
            tenant_id=principal.tenant_id,
            job_id=row["id"],
            queue=row["queue"],
            clock=uow.clock,
        )
    )
    return MappingProxyType(row)


def pending_job_id(session: Session, kind: JobKind) -> UUID | None:
    """The tenant's oldest job of ``kind`` that has still to finish, or None: RUNNING, or QUEUED
    and either not yet dispatched (the after-commit hook or the sweeper dispatches it) or with a
    Procrastinate task that can still run it (``todo`` or ``doing``; D-80). A QUEUED job whose task
    is gone is stranded, not pending: the sweeper settles it."""
    found = session.execute(
        select(job.c.id)
        .where(
            job.c.kind == kind.value,
            or_(
                job.c.state == JobState.RUNNING.value,
                and_(
                    job.c.state == JobState.QUEUED.value,
                    or_(job.c.procrastinate_job_id.is_(None), _LIVE_TASK),
                ),
            ),
        )
        .order_by(job.c.created_at, job.c.id)
        .limit(1)
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def defer_single(
    uow: UnitOfWork, kind: JobKind, params: Mapping[str, Any], **kwargs: Any
) -> tuple[UUID, bool]:
    """Defer a job of ``kind`` unless the tenant has one pending (``pending_job_id``): the id of
    the pending job and False, or the id of the job deferred now and True. For a command any
    holder of its permission may repeat at will — the on-demand audit chain verification
    (security finding SC-8; dev-guide DG-KRN-AUD-07 rev 1.89) — so that requests cannot queue
    more than one run. The check and the insert are serialised by a transaction-level advisory
    lock on tenant and kind: concurrent requests defer one job."""
    key = f"erev.job.single:{uow.principal.tenant_id}:{kind.value}"
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
    pending = pending_job_id(uow.session, kind)
    if pending is not None:
        return pending, False
    row = defer(uow, kind, params, **kwargs)
    return UUID(str(row["id"])), True


def defer_for_active_tenants(
    kind: JobKind, params: Mapping[str, Any], *, clock: Clock, request_id: str
) -> int:
    """The periodic fan-out (DG-KRN-JOB-07; 05 SCH-01, SCH-07): one SYSTEM job of ``kind`` per
    ACTIVE tenant that has none QUEUED or RUNNING, over one ``platform_session("tenant_directory")``
    read; returns the number deferred."""
    now = clock.now()
    with platform_session("tenant_directory", actor_user_id=None, request_id=request_id) as session:
        tenant_ids = [
            UUID(str(value))
            for value in session.scalars(
                select(tenant.c.id)
                .where(tenant.c.status == TenantStatus.ACTIVE.value)
                .order_by(tenant.c.id)
            )
        ]
    deferred = 0
    for tenant_id in tenant_ids:
        with _one_tenant(tenant_id, kind), tenant_session(_system_context(tenant_id)) as session:
            deferred += _defer_unless_pending(
                session, kind, params, tenant_id=tenant_id, now=now, request_id=request_id
            )
    return deferred


@contextmanager
def isolated(event: str, **fields: str) -> Iterator[None]:
    """One tenant or job never stops a fan-out or a sweep (DG-KRN-JOB-02, DG-KRN-JOB-06 rev
    1.89): a failure inside the block — a tenant whose audit chain cannot take ``job.start`` or
    ``job.finish``, for example — is logged as ``event`` at error level with its class and the
    place it was raised (``error_at``, rev 1.183: ``logging.raised_at``; never its message),
    and the caller goes on with the next tenant or job. What the block wrote rolls back with its
    own transaction."""
    try:
        yield
    except Exception as error:
        get_logger(_LOGGER).error(
            event, error_class=type(error).__name__, error_at=raised_at(error), **fields
        )


def _one_tenant(tenant_id: UUID, kind: JobKind) -> AbstractContextManager[None]:
    """A fan-out's tenant in isolation: it gets no job when its transaction fails (the insert and
    the dispatch roll back with the event), and the next tenant is served."""
    return isolated("job.fan_out_failed", tenant_id=str(tenant_id), job_kind=kind.value)


def defer_for_due_tenants(
    kind: JobKind,
    params: Mapping[str, Any],
    *,
    due: Callable[[datetime], Select[Any]],
    clock: Clock,
    request_id: str,
) -> int:
    """The minute sweeps (05 SCH-03, SCH-12; ADP-32): one SYSTEM job of ``kind`` per tenant for
    which ``due(now)`` selects a row and that has none QUEUED or RUNNING; returns the number
    deferred."""
    now = clock.now()
    with platform_session("tenant_directory", actor_user_id=None, request_id=request_id) as session:
        tenant_ids = [
            UUID(str(value)) for value in session.scalars(select(tenant.c.id).order_by(tenant.c.id))
        ]
    deferred = 0
    for tenant_id in tenant_ids:
        with _one_tenant(tenant_id, kind), tenant_session(_system_context(tenant_id)) as session:
            if not session.execute(select(due(now).exists())).scalar_one():
                continue
            deferred += _defer_unless_pending(
                session, kind, params, tenant_id=tenant_id, now=now, request_id=request_id
            )
    return deferred


def _defer_unless_pending(
    session: Session,
    kind: JobKind,
    params: Mapping[str, Any],
    *,
    tenant_id: UUID,
    now: datetime,
    request_id: str,
) -> int:
    """Insert and dispatch one SYSTEM job of ``kind`` unless one is RUNNING, or QUEUED with a
    Procrastinate task that can still run it (``todo`` or ``doing``; D-80); 1 or 0. The job's
    ``job.start`` is appended last, as SYSTEM under the sweep's ``request_id`` (04 T-PLT-27)."""
    pending = (
        select(job.c.id)
        .where(
            job.c.kind == kind.value,
            or_(
                job.c.state == JobState.RUNNING.value,
                and_(job.c.state == JobState.QUEUED.value, _LIVE_TASK),
            ),
        )
        .exists()
    )
    if session.execute(select(pending)).scalar_one():
        return 0
    row = insert_job(
        session,
        kind,
        params,
        tenant_id=tenant_id,
        now=now,
        created_by=None,
        created_by_kind=PrincipalKind.SYSTEM,
    )
    dispatch(session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=now)
    if start_is_audited(kind):
        _append_job_event(
            session,
            principal=system_principal(tenant_id),
            request_id=request_id,
            now=now,
            action=START_ACTION,
            job_id=row["id"],
            after=start_facts(row),
            keyring=None,
        )
    return 1


_LIVE_TASK = text(
    "EXISTS (SELECT 1 FROM procrastinate_jobs AS task "
    "WHERE task.id = erev.job.procrastinate_job_id AND task.status IN ('todo', 'doing'))"
)
_TASK_STATUS = text("SELECT status FROM procrastinate_jobs WHERE id = :id FOR UPDATE")
_TRY_SLOT = text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))")
_RELEASE_SLOT = text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))")


def slot_key(tenant_id: UUID, k: int) -> str:
    """``'erev-job:' || tenant_id || ':' || k`` of DG-KRN-JOB-03."""
    return f"erev-job:{tenant_id}:{k}"


@contextmanager
def job_slot(tenant_id: UUID, concurrency: int) -> Iterator[int | None]:
    """One of ``concurrency`` per-tenant advisory slots, held while the block runs; None when every
    slot is taken (DG-KRN-JOB-03)."""
    with lock_connection(_system_context(tenant_id)) as connection:
        held: int | None = None
        for k in range(concurrency):
            if connection.execute(_TRY_SLOT, {"key": slot_key(tenant_id, k)}).scalar_one():
                held = k
                break
        try:
            yield held
        finally:
            if held is not None:
                connection.execute(_RELEASE_SLOT, {"key": slot_key(tenant_id, held)})


def _runs_under_close_run(session: Session, parent_job_id: object) -> bool:
    """05 JOB-03: a child of a RUNNING ``CLOSE_RUN`` takes no slot, because its parent holds one."""
    if parent_job_id is None:
        return False
    parent = session.execute(
        select(job.c.kind, job.c.state).where(job.c.id == parent_job_id)
    ).one_or_none()
    return (
        parent is not None
        and parent.kind == JobKind.CLOSE_RUN.value
        and parent.state == JobState.RUNNING.value
    )


def _move(
    session: Session,
    job_id: UUID,
    source: JobState,
    target: JobState,
    *,
    now: datetime,
    task_id: int | None = None,
    **values: Any,
) -> bool:
    """Change the job's state along DB-03; False when another process changed it first.

    With ``task_id`` the change applies only while the row still names that Procrastinate task:
    a stalled attempt that the sweeper replaced records nothing on its successor's row (D-80).
    A task carries one attempt number, so the task id identifies the attempt.
    """
    if task_id is not None:
        owner = session.execute(
            select(job.c.procrastinate_job_id)
            .where(job.c.id == job_id, job.c.state == source.value)
            .with_for_update()
        ).scalar_one_or_none()
        if owner != task_id:
            return False
    try:
        apply(
            session,
            "job",
            job_id,
            to_status=target.value,
            set_values={**values, **_system_stamp(now)},
            expected_status=source.value,
        )
    except Problem as problem:
        if problem.slug != "invalid-transition":
            raise
        return False
    return True


def failure_problem(error: Exception, job_id: UUID) -> dict[str, Any]:
    """The RFC 9457 object stored in ``job.problem``; unexpected errors reveal only their class in
    the logs, never their message (DG-KRN-JOB-05; DG-LOG-03)."""
    instance = f"/api/v1/jobs/{job_id}"
    if isinstance(error, Problem):
        return error.to_json(instance=instance)
    return {
        "type": "about:blank",
        "title": "Job failed",
        "status": 500,
        "detail": "The job stopped with an unexpected error.",
        "instance": instance,
        "code": None,
        "errors": [],
    }


def run_job(
    job_id: UUID,
    tenant_id: UUID,
    *,
    attempt: int,
    runtime: JobRuntime,
    concurrency: int | None = None,
    release_mismatch_deferrals: int = 0,
    delivered_task_id: int | None = None,
) -> None:
    """The body of ``erev.run_job`` (DG-KRN-JOB-03; 05 JOB-01 to JOB-03, REL-05; D-80).

    ``delivered_task_id`` is the Procrastinate task this delivery stands for (the worker passes
    ``context.job.id``). A delivery whose task is no longer the job's pointer is stale: it returns
    before any slot, transition, dispatch or handler, whatever the worker's release. Only tests and
    inline callers omit it and stand for the row's current task. A job that is no longer QUEUED is
    left alone (duplicate delivery). A job another release enqueued is re-deferred for 30 seconds
    while ``release_mismatch_deferrals`` is below 10, and fails with ``release-mismatch`` on the
    eleventh delivery (REL-05). The slot is taken before the QUEUED → RUNNING change, so a job
    without a free slot simply stays QUEUED and is deferred again after 5 seconds (SPEC-Q-162).
    The attempt runs under the delivered task, and records its outcome only while the row still
    names it (D-80).
    """
    context = _system_context(tenant_id)
    with tenant_session(context) as session:
        current = (
            session.execute(
                select(
                    job.c.kind,
                    job.c.state,
                    job.c.queue,
                    job.c.params,
                    job.c.parent_job_id,
                    job.c.created_by,
                    job.c.procrastinate_job_id,
                    job.c.subject_type,
                    job.c.subject_id,
                )
                .where(job.c.tenant_id == tenant_id, job.c.id == job_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if current is None or current["state"] != JobState.QUEUED.value:
            return
        if delivered_task_id is not None and current["procrastinate_job_id"] != delivered_task_id:
            # D-80: a successor task owns the job; this delivery is stale and does nothing.
            get_logger(_LOGGER).warning(
                "job.stale_delivery",
                job_id=str(job_id),
                job_kind=str(current["kind"]),
                attempt=attempt,
                delivered_task_id=delivered_task_id,
                current_task_id=current["procrastinate_job_id"],
                release_mismatch_deferrals=release_mismatch_deferrals,
            )
            return
        exempt = _runs_under_close_run(session, current["parent_job_id"])
        limit = (
            job_concurrency(session, known_at=runtime.clock.now())
            if concurrency is None
            else concurrency
        )
    queue = str(current["queue"])
    # The delivered task is the identity of this attempt; tests and inline callers, which pass
    # none, stand for the row's current task (the two are equal after the check above).
    task_id = (
        delivered_task_id if delivered_task_id is not None else current["procrastinate_job_id"]
    )
    worker_release = runtime.engine_release
    pin = classify_release_pin(
        current["params"], None if worker_release is None else worker_release.id
    )
    if pin.kind in (PIN_MISMATCH, PIN_UNPINNED, PIN_MALFORMED):
        _settle_release_mismatch(
            job_id,
            tenant_id,
            current=current,
            queue=queue,
            task_id=task_id,
            attempt=attempt,
            deferrals=release_mismatch_deferrals,
            pin=pin,
            runtime=runtime,
        )
        return
    if pin.kind == PIN_UNVERIFIED and pin.enqueuer is not None:
        # An unstamped runtime (tests, run_inline) runs pinned work without comparing; say so.
        get_logger(_LOGGER).info(
            "job.release_unverified",
            job_id=str(job_id),
            job_kind=str(current["kind"]),
            attempt=attempt,
            enqueuer_release_id=pin.enqueuer,
        )
    if _defer_until_ready(
        job_id,
        tenant_id,
        current=current,
        task_id=task_id,
        attempt=attempt,
        release_mismatch_deferrals=release_mismatch_deferrals,
        runtime=runtime,
    ):
        return
    with ExitStack() as stack:
        if not exempt:
            if stack.enter_context(job_slot(tenant_id, limit)) is None:
                # SPEC-Q-162 re-dispatch, fenced on the observed task (D-80) and keeping the REL-05
                # count: no handler ran, so the budget is not spent by capacity alone.
                with tenant_session(context) as session:
                    _redispatch_if_owner(
                        session,
                        job_id,
                        tenant_id,
                        task_id=task_id,
                        queue=queue,
                        now=runtime.clock.now(),
                        attempt=attempt,
                        delay=SLOT_RETRY_DELAY,
                        release_mismatch_deferrals=release_mismatch_deferrals,
                    )
                return
        with tenant_session(context) as session:
            now = runtime.clock.now()
            if not _move(
                session,
                job_id,
                JobState.QUEUED,
                JobState.RUNNING,
                now=now,
                task_id=task_id,
                started_at=now,
            ):
                return
        _execute(
            job_id=job_id,
            tenant_id=tenant_id,
            kind=JobKind(current["kind"]),
            params=handler_params(current["params"]),
            principal=system_principal(tenant_id, on_behalf_of_id=current["created_by"]),
            attempt=attempt,
            task_id=task_id,
            runtime=runtime,
            current=current,
        )


DEPENDENCY_RETRY_DELAY: Final = timedelta(seconds=30)


def _defer_until_ready(
    job_id: UUID,
    tenant_id: UUID,
    *,
    current: RowMapping,
    task_id: int | None,
    attempt: int,
    release_mismatch_deferrals: int,
    runtime: JobRuntime,
) -> bool:
    """True when this delivery was deferred, superseded, cancelled or failed by readiness."""
    spec = HANDLERS.get(JobKind(current["kind"]))
    if spec is None or spec.ready is None:
        return False
    try:
        with tenant_session(_system_context(tenant_id)) as session:
            owner = session.execute(
                select(job.c.procrastinate_job_id)
                .where(
                    job.c.tenant_id == tenant_id,
                    job.c.id == job_id,
                    job.c.state == JobState.QUEUED.value,
                )
                .with_for_update()
            ).one_or_none()
            if owner is None or owner[0] != task_id:
                return True
            ready = spec.ready(session, job_id, handler_params(current["params"]))
            if not isinstance(ready, bool):
                raise TypeError("A job readiness hook must return bool.")
            if ready:
                return False
            _redispatch_if_owner(
                session,
                job_id,
                tenant_id,
                task_id=task_id,
                queue=str(current["queue"]),
                now=runtime.clock.now(),
                attempt=attempt,
                delay=DEPENDENCY_RETRY_DELAY,
                release_mismatch_deferrals=release_mismatch_deferrals,
            )
        return True
    except Problem as error:
        _fail_queued(
            job_id,
            tenant_id,
            task_id=task_id,
            attempt=attempt,
            error=error,
            runtime=runtime,
            created_by=current["created_by"],
        )
        return True


def _redispatch_if_owner(
    session: Session,
    job_id: UUID,
    tenant_id: UUID,
    *,
    task_id: int | None,
    queue: str,
    now: datetime,
    attempt: int,
    delay: timedelta,
    release_mismatch_deferrals: int,
) -> bool:
    """Dispatch a replacement task only while the row is still QUEUED under ``task_id`` (D-80).

    A stale delivery (a successor task already replaced the pointer, or the job ran, finished or
    was cancelled) creates no task and touches no pointer; the caller treats False as a no-op.
    """
    owner = session.execute(
        select(job.c.procrastinate_job_id)
        .where(
            job.c.tenant_id == tenant_id,
            job.c.id == job_id,
            job.c.state == JobState.QUEUED.value,
        )
        .with_for_update()
    ).one_or_none()
    if owner is None or owner[0] != task_id:
        return False
    dispatch(
        session,
        job_id=job_id,
        tenant_id=tenant_id,
        queue=queue,
        now=now,
        attempt=attempt,
        delay=delay,
        release_mismatch_deferrals=release_mismatch_deferrals,
    )
    return True


def _fail_queued(
    job_id: UUID,
    tenant_id: UUID,
    *,
    task_id: int | None,
    attempt: int,
    error: Exception,
    runtime: JobRuntime,
    created_by: Any,
) -> bool:
    """End a QUEUED job FAILED without running it: QUEUED → RUNNING → FAILED in one transaction
    (DB-03 has no QUEUED → FAILED pair), only while the row still names ``task_id`` (D-80)."""
    principal = system_principal(tenant_id, on_behalf_of_id=created_by)
    with system_unit_of_work(runtime, principal, request_id=f"job-{job_id}") as uow:
        now = uow.now
        if not _move(
            uow.session,
            job_id,
            JobState.QUEUED,
            JobState.RUNNING,
            now=now,
            task_id=task_id,
            started_at=now,
        ):
            return False
        row = uow.session.execute(
            select(*_FAILING).where(job.c.tenant_id == tenant_id, job.c.id == job_id)
        ).one()
        _fail_job(
            uow,
            job_id,
            row,
            kind=JobKind(row.kind),
            attempt=attempt,
            error=error,
            alerts=runtime.alerts,
        )
    return True


def _settle_release_mismatch(
    job_id: UUID,
    tenant_id: UUID,
    *,
    current: RowMapping,
    queue: str,
    task_id: int | None,
    attempt: int,
    deferrals: int,
    pin: ReleasePin,
    runtime: JobRuntime,
) -> None:
    """05 REL-05 for a job this worker must not run.

    ``mismatch`` and ``unpinned`` (a legacy job with no recorded enqueuer is never assumed
    compatible) are re-deferred for 30 seconds while ``deferrals`` is below 10, fenced on the
    observed task; the eleventh delivery fails the job with ``release-mismatch`` (503). A
    ``malformed`` pin cannot become valid by waiting and fails at once with ``validation-failed``
    (422) naming the field. Nothing runs, and a stale delivery changes nothing.
    """
    assert runtime.engine_release is not None
    logger = get_logger(_LOGGER)
    kind = JobKind(current["kind"])
    worker_release_id = str(runtime.engine_release.id)
    common = {
        "job_id": str(job_id),
        "job_kind": kind.value,
        "attempt": attempt,
        "enqueuer_release_id": pin.enqueuer if pin.enqueuer is not None else "<unpinned>",
        "worker_release_id": worker_release_id,
    }
    if pin.kind == PIN_MALFORMED:
        error: Exception = Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field=f"params.{RELEASE_PARAM}",
                    rule_id="REL-05",
                    message="The job's enqueuing release is not a release id.",
                )
            ],
        )
        if _fail_queued(
            job_id,
            tenant_id,
            task_id=task_id,
            attempt=attempt,
            error=error,
            runtime=runtime,
            created_by=current["created_by"],
        ):
            logger.error("job.release_pin_malformed", **common)
        return
    if deferrals < RELEASE_MISMATCH_MAX_DEFERRALS:
        with tenant_session(_system_context(tenant_id)) as session:
            redispatched = _redispatch_if_owner(
                session,
                job_id,
                tenant_id,
                task_id=task_id,
                queue=queue,
                now=runtime.clock.now(),
                attempt=attempt,
                delay=RELEASE_MISMATCH_DELAY,
                release_mismatch_deferrals=deferrals + 1,
            )
        if redispatched:
            logger.warning(
                "job.release_mismatch_deferred", release_mismatch_deferrals=deferrals + 1, **common
            )
        return
    if pin.kind == PIN_UNPINNED:
        detail = (
            "the job records no enqueuing release (queued before REL-05); "
            "re-submit it under the current release"
        )
    else:
        detail = f"enqueued by release {pin.enqueuer}; this worker runs release {worker_release_id}"
    if _fail_queued(
        job_id,
        tenant_id,
        task_id=task_id,
        attempt=attempt,
        error=Problem("release-mismatch", detail),
        runtime=runtime,
        created_by=current["created_by"],
    ):
        logger.error("job.release_mismatch", release_mismatch_deferrals=deferrals, **common)


def _execute(
    *,
    job_id: UUID,
    tenant_id: UUID,
    kind: JobKind,
    params: Mapping[str, Any],
    principal: Principal,
    attempt: int,
    task_id: int | None,
    runtime: JobRuntime,
    current: RowMapping | None = None,
) -> None:
    spec = HANDLERS.get(kind)
    # The handler's runtime names the attempt, so that every unit of work it opens passes the
    # attempt's door (05 JOB-06 rev 1.200). The settlement below keeps the worker's own runtime:
    # the unit of work that ends a job is not one of the attempt's.
    job_context = JobContext(
        job_id=job_id,
        tenant_id=tenant_id,
        kind=kind,
        principal=principal,
        runtime=replace(
            runtime, attempt=JobAttempt(job_id=job_id, tenant_id=tenant_id, task_id=task_id)
        ),
    )
    try:
        if spec is None:
            raise LookupError(f"no handler is registered for job kind {kind.value}")
        outcome = spec.handler(job_context, params)
    except JobLost:
        # The job is the sweeper's or a later attempt's by now: this attempt was refused at a
        # beat, at the beginning of a unit of work or at its commit, kept nothing from there,
        # and records nothing on a row that is no longer its own.
        get_logger(_LOGGER).warning(
            "job.attempt_lost", job_id=str(job_id), job_kind=kind.value, attempt=attempt
        )
        return
    except Exception as error:
        fail_attempt(
            job_id, tenant_id, attempt=attempt, error=error, runtime=runtime, task_id=task_id
        )
        return
    with tenant_session(_system_context(tenant_id)) as session:
        now = runtime.clock.now()
        cancel_requested_at = session.execute(
            select(job.c.cancel_requested_at)
            .where(job.c.tenant_id == tenant_id, job.c.id == job_id)
            .with_for_update()
        ).scalar_one()
        # 05 JOB-05: a handler that stopped after a cancellation request ends CANCELLED.
        target = JobState.CANCELLED if cancel_requested_at is not None else JobState(outcome.state)
        finished = _move(
            session,
            job_id,
            JobState.RUNNING,
            target,
            now=now,
            task_id=task_id,
            finished_at=now,
            result=dict(outcome.result),
        )
        if finished and start_is_audited(kind):
            _append_job_event(
                session,
                principal=principal,
                request_id=f"job-{job_id}",
                now=now,
                action=FINISH_ACTION,
                job_id=job_id,
                after=finish_facts(kind, target, None),
                keyring=runtime.keyring,
            )
    if finished and target in _RAN_TO_ITS_END and current is not None:
        _settle_failed_item(job_id, tenant_id, kind, current, runtime)


def fail_attempt(
    job_id: UUID,
    tenant_id: UUID,
    *,
    attempt: int,
    error: Exception,
    runtime: JobRuntime,
    stalled_before: datetime | None = None,
    task_id: int | None = None,
) -> JobState | None:
    """Settle one failed attempt of a RUNNING job (DG-KRN-JOB-05, DG-KRN-JOB-06; 05 JOB-06, JOB-07).

    While attempts remain, the job returns to QUEUED and is deferred again after its backoff.
    After the last attempt it is FAILED with its problem, and its initiator is notified in the same
    transaction. With ``stalled_before`` the job is settled only while it is still RUNNING without
    an update since then, a job with a transaction open is passed over (05 JOB-06 rev 1.200),
    and a job whose row another process holds is skipped. With ``task_id`` it is settled only
    while the row still names that Procrastinate task (D-80). Returns the new state, or None
    when nothing was settled.
    """
    principal = system_principal(tenant_id)
    with system_unit_of_work(runtime, principal, request_id=f"job-{job_id}") as uow:
        failing = [
            job.c.tenant_id == tenant_id,
            job.c.id == job_id,
            job.c.state == JobState.RUNNING.value,
        ]
        if stalled_before is not None:
            failing.append(job.c.updated_at < stalled_before)
        if task_id is not None:
            failing.append(job.c.procrastinate_job_id == task_id)
        logger = get_logger(_LOGGER)
        if stalled_before is not None and not try_unit_lock(uow.session, job_id):
            # 05 JOB-06 rev 1.200: a transaction of the job is open, so its worker is alive and
            # the job is not settled beside it. The lock is asked for before the row: a unit of
            # work may hold the row as well - a row it inserted refers to the job - and the pass
            # is told whichever it holds. Said at every pass, for the operator who reads how
            # long a job has been silent (runbook RB-07). Once taken, the lock is held to this
            # settlement's commit: a unit of work that begins meanwhile waits for it and is then
            # refused at its beginning.
            silent = uow.session.execute(
                select(job.c.kind, job.c.updated_at).where(*failing)
            ).one_or_none()
            if silent is not None:
                logger.info(
                    "job.sweep_passed_over",
                    job_id=str(job_id),
                    job_kind=str(silent.kind),
                    attempt=attempt,
                    silent_seconds=int((uow.now - silent.updated_at).total_seconds()),
                )
            return None
        current = uow.session.execute(
            select(*_FAILING)
            .where(*failing)
            .with_for_update(skip_locked=stalled_before is not None)
        ).one_or_none()
        if current is None:
            return None
        kind = JobKind(current.kind)
        spec = HANDLERS.get(kind)
        retry = DEFAULT_RETRY if spec is None else spec.retry
        now = uow.now
        if attempt < retry.max_attempts:
            _move(uow.session, job_id, JobState.RUNNING, JobState.QUEUED, now=now)
            dispatch(
                uow.session,
                job_id=job_id,
                tenant_id=tenant_id,
                queue=str(current.queue),
                now=now,
                attempt=attempt + 1,
                delay=backoff_delay(retry, attempt),
            )
            uow.commit()
            logger.warning(
                "job.retry_scheduled",
                job_id=str(job_id),
                job_kind=kind.value,
                attempt=attempt,
                error_class=type(error).__name__,
            )
            return JobState.QUEUED
        _fail_job(
            uow, job_id, current, kind=kind, attempt=attempt, error=error, alerts=runtime.alerts
        )
        return JobState.FAILED


def retry_stranded(
    job_id: UUID,
    tenant_id: UUID,
    *,
    task_id: int,
    attempt: int,
    stalled: bool,
    error: Exception,
    runtime: JobRuntime,
) -> JobState | None:
    """Recover a QUEUED job whose Procrastinate task can no longer run it (05 JOB-06, SCH-04; D-80).

    ``attempt`` is the attempt the task stands for. While the kind's retry policy allows another
    attempt, a ``failed``, ``cancelled`` or ``aborted`` task is replaced by a new dispatch of
    attempt + 1 after the backoff, and a task stalled in ``doing`` (``stalled``) is retried in place
    through ``JobManager.retry_job_by_id``. After the last attempt the job is FAILED with ``error``
    and its initiator is notified. The job is settled only while it is still QUEUED under
    ``task_id`` and the task still has that status. Returns the new state, or None.
    """
    principal = system_principal(tenant_id)
    with system_unit_of_work(runtime, principal, request_id=f"job-{job_id}") as uow:
        current = uow.session.execute(
            select(*_FAILING)
            .where(
                job.c.tenant_id == tenant_id,
                job.c.id == job_id,
                job.c.state == JobState.QUEUED.value,
                job.c.procrastinate_job_id == task_id,
            )
            .with_for_update(skip_locked=True)
        ).one_or_none()
        if current is None:
            return None
        status = uow.session.execute(_TASK_STATUS, {"id": task_id}).scalar_one_or_none()
        still_stranded = status == "doing" if stalled else status in REDISPATCHED_STATUSES
        if not still_stranded:
            return None
        kind = JobKind(current.kind)
        spec = HANDLERS.get(kind)
        retry = DEFAULT_RETRY if spec is None else spec.retry
        now = uow.now
        if attempt < retry.max_attempts:
            delay = backoff_delay(retry, attempt)
            if stalled:
                manager = procrastinate_manager.JobManager(connector=_SessionConnector(uow.session))
                manager.retry_job_by_id(task_id, retry_at=now + delay)
            else:
                dispatch(
                    uow.session,
                    job_id=job_id,
                    tenant_id=tenant_id,
                    queue=str(current.queue),
                    now=now,
                    attempt=attempt + 1,
                    delay=delay,
                    # REL-05: recovery executes nothing, so the deferral budget carries over.
                    release_mismatch_deferrals=_task_release_deferrals(uow.session, task_id),
                )
            uow.commit()
            get_logger(_LOGGER).warning(
                "job.retry_scheduled",
                job_id=str(job_id),
                job_kind=kind.value,
                attempt=attempt,
                error_class=type(error).__name__,
            )
            return JobState.QUEUED
        # DB-03 has no QUEUED → FAILED pair: the job passes through RUNNING in the same transaction.
        _move(uow.session, job_id, JobState.QUEUED, JobState.RUNNING, now=now)
        _fail_job(
            uow, job_id, current, kind=kind, attempt=attempt, error=error, alerts=runtime.alerts
        )
        return JobState.FAILED


def _fail_job(
    uow: UnitOfWork,
    job_id: UUID,
    current: Any,
    *,
    kind: JobKind,
    attempt: int,
    error: Exception,
    alerts: AlertRaiser | None,
) -> None:
    """End a RUNNING job FAILED with its problem, tell of it and commit (DG-KRN-JOB-05; 05
    JOB-07 rev 1.165). ``job.finish`` with the state and the problem's slug joins the same commit
    (04 T-PLT-27). A user who started the job is notified - of a job the sweeper stopped as
    stalled with the sentence PRD NTF-05 rev 1.191 gives that case; the kind's failure hook
    ends the record the job works on; a kind with a ``FailedItem`` leaves the exception item
    ``JOB_FAILED`` of the entity its record names. After the commit a job that no user started
    raises the operator alert ``JOB_FAILED`` through ``alerts`` (None in tests and
    ``run_inline``: no alert)."""
    problem = failure_problem(error, job_id)
    now = uow.now
    failed = _move(
        uow.session,
        job_id,
        JobState.RUNNING,
        JobState.FAILED,
        now=now,
        finished_at=now,
        problem=problem,
    )
    if failed and start_is_audited(kind):
        uow.audit(
            action=FINISH_ACTION,
            object_type=JOB_SUBJECT,
            object_id=job_id,
            after=finish_facts(kind, JobState.FAILED, problem),
        )
    by_user = current.created_by is not None and current.created_by_kind == PrincipalKind.USER.value
    if by_user:
        notify_job_failed(
            uow,
            job_id=job_id,
            kind=kind,
            user_id=UUID(str(current.created_by)),
            attempt=attempt,
            problem=problem,
        )
    spec = HANDLERS.get(kind)
    if spec is not None and spec.on_failure is not None:
        try:
            # A failing hook leaves its record unchanged, and nothing it buffered in the unit of
            # work - an audit event, a notification's dispatch - outlives its rows: the savepoint
            # is the unit of work's (DG-KRN-UOW-03), not the session's. Optional hooks allow
            # FAILED; required hooks abort settlement so the sweeper can retry cleanup.
            with uow.savepoint():
                spec.on_failure(uow, handler_params(current.params or {}), problem)
        except Exception as hook_error:
            get_logger(_LOGGER).error(
                "job.failure_hook_failed",
                job_id=str(job_id),
                job_kind=kind.value,
                attempt=attempt,
                error_class=type(hook_error).__name__,
            )
            if spec.failure_hook_required:
                raise
    if failed:
        _raise_failed_item(uow, job_id, current, kind=kind, attempt=attempt, problem=problem)
    uow.commit()
    get_logger(_LOGGER).error(
        "job.failed",
        job_id=str(job_id),
        job_kind=kind.value,
        attempt=attempt,
        error_class=type(error).__name__,
    )
    if failed and not by_user:
        _alert_job_failed(
            alerts,
            tenant_id=uow.principal.tenant_id,
            job_id=job_id,
            current=current,
            kind=kind,
            attempt=attempt,
            problem=problem,
            now=now,
        )


def _raise_failed_item(
    uow: UnitOfWork,
    job_id: UUID,
    current: Any,
    *,
    kind: JobKind,
    attempt: int,
    problem: Mapping[str, Any],
) -> None:
    """05 JOB-07 rev 1.165: the exception item ``JOB_FAILED`` of a failed job whose record names
    one legal entity, in the transaction that ends the job and inside a savepoint of the unit of
    work — a reader or a writer that fails is logged with its class and place, leaves nothing
    behind, and the job still ends FAILED. A kind without a ``FailedItem``, a job without a
    subject and a record of no entity or of several raise nothing."""
    spec = HANDLERS.get(kind)
    if spec is None or spec.failed_item is None or current.subject_id is None:
        return
    item = spec.failed_item
    subject_id = UUID(str(current.subject_id))
    try:
        with uow.savepoint():
            subject = item.subject(
                uow.session,
                None if current.subject_type is None else str(current.subject_type),
                subject_id,
                handler_params(current.params or {}),
            )
            if subject is not None:
                item.raise_item(
                    uow,
                    FailedJob(
                        job_id=job_id,
                        kind=kind,
                        label=JOB_LABELS[kind],
                        attempt=attempt,
                        problem=problem,
                        record=subject.key or str(subject_id),
                        subject=subject,
                    ),
                )
    except Exception as item_error:
        get_logger(_LOGGER).error(
            "job.failed_item_failed",
            job_id=str(job_id),
            job_kind=kind.value,
            attempt=attempt,
            error_class=type(item_error).__name__,
            error_at=raised_at(item_error),
        )


def _alert_job_failed(
    alerts: AlertRaiser | None,
    *,
    tenant_id: UUID,
    job_id: UUID,
    current: Any,
    kind: JobKind,
    attempt: int,
    problem: Mapping[str, Any],
    now: datetime,
) -> None:
    """05 OPR-24 ``JOB_FAILED`` (JOB-07 rev 1.165): a job that no user started ended FAILED — a
    periodic job of the scheduler, a job of an API client — and nobody is notified of it. Raised
    after the commit, so that an alert names a job that is FAILED; a failure to raise is logged
    and changes nothing."""
    if alerts is None:
        return
    try:
        alerts.raise_alert(
            job_failed_alert(
                tenant_id=tenant_id,
                job_id=job_id,
                job_kind=kind.value,
                queue=str(current.queue),
                attempt=attempt,
                problem=problem_slug(problem),
                initiator=str(current.created_by_kind),
                raised_at=now,
            )
        )
    except Exception as alert_error:
        get_logger(_LOGGER).error(
            "job.failed_alert_failed",
            job_id=str(job_id),
            job_kind=kind.value,
            attempt=attempt,
            error_class=type(alert_error).__name__,
        )


def _settle_failed_item(
    job_id: UUID, tenant_id: UUID, kind: JobKind, current: RowMapping, runtime: JobRuntime
) -> None:
    """05 JOB-07 rev 1.165: a job that ran to its end settles the open ``JOB_FAILED`` item of its
    kind and record — after the transaction that recorded the terminal state, and in a unit of
    work of its own only when the read of the open items finds one, so that a kind's ordinary
    success costs its reader and one indexed read. A settlement that fails is logged; the job
    keeps its state, and the next success of the kind and record settles the item. ``current``
    holds the job's ``subject_type``, ``subject_id`` and ``params``."""
    spec = HANDLERS.get(kind)
    if spec is None or spec.failed_item is None or current["subject_id"] is None:
        return
    if runtime.keyring is None or runtime.files is None:
        return  # a runtime without a key ring writes no audit event (tests, run_inline)
    item = spec.failed_item
    subject_id = UUID(str(current["subject_id"]))
    try:
        with tenant_session(_system_context(tenant_id), read_only=True) as session:
            subject = item.subject(
                session,
                None if current["subject_type"] is None else str(current["subject_type"]),
                subject_id,
                handler_params(current["params"] or {}),
            )
            if subject is None:
                return
            record = subject.key or str(subject_id)
            if not item.is_open(session, kind, record):
                return
        with system_unit_of_work(
            runtime, system_principal(tenant_id), request_id=f"job-{job_id}"
        ) as uow:
            item.settle(uow, kind, record, job_id)
            uow.commit()
    except Exception as settle_error:
        get_logger(_LOGGER).error(
            "job.failed_item_unsettled",
            job_id=str(job_id),
            job_kind=kind.value,
            error_class=type(settle_error).__name__,
            error_at=raised_at(settle_error),
        )


def notify_job_failed(
    uow: UnitOfWork,
    *,
    job_id: UUID,
    kind: JobKind,
    user_id: UUID,
    attempt: int,
    problem: Mapping[str, Any],
) -> None:
    """NTF-05 ``JOB_FAILED`` to the initiator's membership (05 JOB-07). The Controllers of the
    entity join for close runs, which CLO builds. The body is ``job_failed_body``'s."""
    # Imported here: notifications enqueue outbox messages, whose relay registers job handlers.
    from erev_api.events import notifications

    membership_ids = [
        UUID(str(value))
        for value in uow.session.scalars(
            select(tenant_membership.c.id).where(
                of_session_tenant(tenant_membership), tenant_membership.c.user_id == user_id
            )
        )
    ]
    label = JOB_LABELS[kind]
    reason = str(problem.get("detail") or problem["title"]).rstrip(".")
    notifications.notify(
        uow,
        recipient_membership_ids=membership_ids,
        kind=NotificationKind.JOB_FAILED,
        title=JOB_FAILED_TITLE.format(label=label),
        body=job_failed_body(
            label=label, step=f"attempt {attempt}", reason=reason, problem=problem
        ),
        subject_type=JOB_SUBJECT,
        subject_id=job_id,
    )


def run_inline(
    kind: JobKind,
    params: Mapping[str, Any],
    *,
    tenant_id: UUID,
    principal: Principal,
    clock: Clock,
    runtime: JobRuntime | None = None,
) -> JobOutcome:
    """Run a handler synchronously with a context that has no job row (DG-KRN-JOB-09).

    ``runtime`` supplies the key ring and file store the context's units of work need; without it
    the handler may use read sessions only (SPEC-Q-164).
    """
    spec = HANDLERS.get(kind)
    if spec is None:
        raise LookupError(f"no handler is registered for job kind {kind.value}")
    context = JobContext(
        job_id=new_id(),
        tenant_id=tenant_id,
        kind=kind,
        principal=principal,
        runtime=runtime or JobRuntime(clock=clock, keyring=None, files=None),
        clock=clock,
        persisted=False,
    )
    return spec.handler(context, params)
