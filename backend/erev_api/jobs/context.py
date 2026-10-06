"""Job context KRN-JOB (dev-guide §5.12 DG-KRN-JOB-04; DG-KRN-UOW-04; 05 JOB-04, JOB-05, JOB-06).

A handler reaches the database only through its ``JobContext``: chunked units of work as the
SYSTEM principal on behalf of the job's creator, read-only sessions, throttled progress, heartbeats
and the cancellation flag. ``run_inline`` builds a context without a job row, whose progress,
heartbeat and cancellation calls do nothing (DG-KRN-JOB-09).

An attempt keeps nothing once it has lost its job (05 JOB-06 rev 1.200; item
JOB-STALL-COMMIT-RACE-1). The sweeper settles a RUNNING job that was silent for ten minutes, and a
handler's work and its job's end are separate transactions: a worker that was alive and silent
committed its work under a job the sweeper had ended FAILED. Three statements of this module and
of the registry close that for every handler's units of work, with no handler changed:

- a heartbeat or a progress write applies to the attempt's RUNNING job alone and raises
  ``JobLost`` when it finds none (``JobAttempt.beat``);
- a unit of work of the attempt takes the job's advisory lock, shared, when it begins, and is
  refused there when the job is no longer the attempt's; at its commit it writes its heartbeat
  on the job's row under the same condition, as its last statement before the audit chain's
  lock - no row, no commit (``JobAttempt.enter``);
- the sweeper settles a RUNNING job only when it holds that lock exclusively, so never while a
  transaction of the job is open (``registry.fail_attempt``).

The attempt travels in the runtime the registry hands the handler (``JobRuntime.attempt``), so
every unit of work the handler opens with it - ``JobContext.unit_of_work()``, or
``system_unit_of_work`` with another principal - passes the same door. A transaction a handler
opens beside its units of work - a platform scope's, a copy step's - passes it by calling
``JobContext.enlist`` first; ``tests/unit/test_job_unit_doors.py`` holds the list of those that
do and of those that rest on a claim of their own instead (DG-KRN-JOB-04).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select, update
from sqlalchemy.orm import Session

from erev_api.audit.digests import DigestExporter
from erev_api.auth.keyring import KeyRing, TenantKeyProvisioner
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import Clock
from erev_api.controls.operator_alerts import AlertRaiser
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables.platform import job, tenant
from erev_api.enums import JobKind, JobState, TenantKind
from erev_api.files.store import FileStore
from erev_api.uow import UnitOfWork, unit_of_work

if TYPE_CHECKING:
    from erev_api.controls.release import EngineRelease
    from erev_api.events.outbox import EmailSender
    from erev_api.events.webhooks import WebhookSender

PROGRESS_INTERVAL: Final = timedelta(seconds=2)  # JOB-04


def unit_lock_key(job_id: UUID) -> str:
    """``'erev-job-unit:' || job_id`` of DG-KRN-DB-08 (rev 1.266): the advisory key of a job's
    transactions, a class of its own beside the job slots' ``erev-job:<tenant>:<k>``."""
    return f"erev-job-unit:{job_id}"


def _unit_lock(job_id: UUID, *, shared: bool) -> Select[Any]:
    """The job's advisory lock, transaction-level on both sides: shared and waiting for a
    transaction of the job, exclusive and without waiting for the settlement of a stalled job.
    A SELECT of the ORM, not a textual statement: a copy step of a sandbox load takes it under
    its statement guard, which admits reads (``sandboxes.check_copy_statement``)."""
    key = func.hashtextextended(unit_lock_key(job_id), 0)
    if shared:
        return select(func.pg_advisory_xact_lock_shared(key))
    return select(func.pg_try_advisory_xact_lock(key))


def try_unit_lock(session: Session, job_id: UUID) -> bool:
    """Take the job's advisory lock exclusively for ``session``'s transaction without waiting;
    False while a transaction of the job holds it (05 JOB-06 rev 1.200)."""
    return bool(session.execute(_unit_lock(job_id, shared=False)).scalar_one())


class JobLost(Exception):
    """The job is no longer this attempt's RUNNING job: the sweeper settled it, or a later attempt
    runs it. Raised by a heartbeat or progress write, at the beginning of a unit of work and at
    its commit; from then on the attempt keeps nothing (05 JOB-06 rev 1.200)."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"job {job_id} is no longer this attempt's running job")
        self.job_id = job_id


@dataclass(frozen=True, slots=True)
class JobAttempt:
    """One attempt of a persisted job: the job, its workspace and the Procrastinate task the
    attempt runs under - None where the caller named none and the attempt stands for the row's
    current task (tests, inline callers; ``registry.run_job``)."""

    job_id: UUID
    tenant_id: UUID
    task_id: int | None

    def _mine(self) -> list[ColumnElement[bool]]:
        """The job while it is this attempt's: RUNNING, under this attempt's task."""
        conditions: list[ColumnElement[bool]] = [
            job.c.tenant_id == self.tenant_id,
            job.c.id == self.job_id,
            job.c.state == JobState.RUNNING.value,
        ]
        if self.task_id is not None:
            conditions.append(job.c.procrastinate_job_id == self.task_id)
        return conditions

    def hold(self, session: Session) -> None:
        """The job's advisory lock, shared, to the end of ``session``'s transaction: while it is
        held the sweeper passes the job over. It waits for a settlement under way."""
        session.execute(_unit_lock(self.job_id, shared=True))

    def require(self, session: Session) -> None:
        """Refuse when the job is no longer this attempt's; ``session`` is of the job's
        workspace."""
        found = session.execute(select(job.c.id).where(*self._mine())).scalar_one_or_none()
        if found is None:
            raise JobLost(self.job_id)

    def beat(self, session: Session, *, now: datetime, **values: object) -> None:
        """Write the heartbeat (and ``values``) on the job's row while it is this attempt's, a
        plain update of non-key columns - a row that refers to the job is inserted beside it
        without waiting; raise ``JobLost`` when no row took it."""
        written = session.execute(
            update(job).where(*self._mine()).values(updated_at=now, **values).returning(job.c.id)
        ).scalar_one_or_none()
        if written is None:
            raise JobLost(self.job_id)

    def enlist(self, session: Session, clock: Clock) -> None:
        """The door of a transaction of this attempt that cannot read or write the job's row - a
        unit of work in another workspace, a platform scope's transaction, a copy step of a
        sandbox load. The lock first, so that no settlement begins while the transaction is
        open and a settlement under way is waited for; then a heartbeat in the job's workspace,
        in a transaction of its own, which refuses the transaction of a lost job before it
        does anything. Such a transaction rests on the lock from there: nothing settles its
        job as stalled before it ends."""
        self.hold(session)
        own = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(own) as other:
            self.beat(other, now=clock.now())

    def enter(self, uow: UnitOfWork, clock: Clock) -> None:
        """The door of a unit of work of this attempt. In the job's own workspace: the lock, the
        read that refuses a unit of a lost job at its beginning, and the heartbeat its commit
        writes on the job's row - the guarantee at the commit, whatever moved the job meanwhile.
        In another workspace - a sandbox a load fills - ``enlist``."""
        if uow.principal.tenant_id != self.tenant_id:
            self.enlist(uow.session, clock)
            return
        self.hold(uow.session)
        self.require(uow.session)
        uow.before_commit(lambda: self.beat(uow.session, now=clock.now()))


@dataclass(frozen=True, slots=True)
class JobRuntime:
    """What a worker process hands every job: its clock, key ring and file store, the email
    sender and public origin the outbox relay needs (05 NTR-04, NTR-05), and the webhook sender of
    webhook deliveries (NTR-12)."""

    clock: Clock
    keyring: KeyRing | None
    files: FileStore | None
    email: EmailSender | None = None
    public_origin: str | None = None  # EREV_PUBLIC_ORIGIN (CFG-09)
    webhooks: WebhookSender | None = None
    digests: DigestExporter | None = None  # SAR-31 hosted digest copy; None keeps the file only
    # 05 REL-05: the release the worker stamped at startup; jobs another release enqueued are
    # re-deferred and then failed with `release-mismatch`. None (tests, run_inline) compares
    # nothing.
    engine_release: EngineRelease | None = None
    # 05 OPR-24: the operator-alert sinks of the worker (None in tests and run_inline: no alert
    # is raised, nothing is silently swallowed either — the callers log as before).
    alerts: AlertRaiser | None = None
    # 05 KEY-05 / DG-KRN-KEY-06: the provisioning authority a job that CREATES a tenant uses
    # for its audit key — a sandbox load, an empty sandbox (05 SBX-02, SBX-07). Hosted, it is
    # the Secret Manager provisioner; None derives the key locally, as `tenant.provision` does.
    key_provisioner: TenantKeyProvisioner | None = None
    # 05 JOB-06 rev 1.200: the attempt a handler runs as. The registry sets it on the runtime it
    # hands the handler, and every unit of work opened with that runtime passes the attempt's
    # door (``JobAttempt.enter``). None for the worker's own runtime - the sweeper, the periodic
    # tasks, a failure hook's unit of work - and for ``run_inline`` outside a job.
    attempt: JobAttempt | None = None


@contextmanager
def system_unit_of_work(
    runtime: JobRuntime, principal: Principal, *, request_id: str, clock: Clock | None = None
) -> Iterator[UnitOfWork]:
    """A unit of work of a worker principal, with the tenant kind read first (DG-KRN-UOW-04).
    With an attempt's runtime it is a unit of work of that attempt and passes its door, whatever
    the principal (05 JOB-06 rev 1.200)."""
    keyring, files = runtime.keyring, runtime.files
    if keyring is None or files is None:
        raise RuntimeError("this job runtime has no key ring or file store")
    clock = runtime.clock if clock is None else clock
    with tenant_session(principal.db_context, read_only=True) as session:
        kind = session.execute(
            select(tenant.c.kind).where(tenant.c.id == principal.tenant_id)
        ).scalar_one()
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind(kind),
        request_id=request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        if runtime.attempt is not None:
            runtime.attempt.enter(uow, clock)
        yield uow


class JobContext:
    job_id: UUID
    tenant_id: UUID
    kind: JobKind
    principal: Principal
    clock: Clock

    def __init__(
        self,
        *,
        job_id: UUID,
        tenant_id: UUID,
        kind: JobKind,
        principal: Principal,
        runtime: JobRuntime,
        clock: Clock | None = None,
        persisted: bool = True,
    ) -> None:
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.kind = kind
        self.principal = principal
        self.clock = runtime.clock if clock is None else clock
        self._runtime = runtime
        # A context with a job row is the registry's alone and runs as an attempt of its job:
        # its heartbeat and progress writes are that attempt's (05 JOB-04 rev 1.200). A context
        # without one - ``run_inline``, the source context of a sandbox reset, a test's - writes
        # neither, whatever its runtime carries.
        if persisted and runtime.attempt is None:
            raise RuntimeError("a job context with a job row runs as an attempt (registry.run_job)")
        self._attempt = runtime.attempt if persisted else None
        self._last_progress: datetime | None = None

    @property
    def runtime(self) -> JobRuntime:
        """The worker services handed to this job (email sender, public origin, key ring, files)."""
        return self._runtime

    def unit_of_work(self) -> AbstractContextManager[UnitOfWork]:
        """One chunk's unit of work as the job's principal (DG-KRN-JOB-04, DG-KRN-UOW-04)."""
        return system_unit_of_work(
            self._runtime, self.principal, request_id=f"job-{self.job_id}", clock=self.clock
        )

    def read_session(self) -> AbstractContextManager[Session]:
        return tenant_session(self.principal.db_context, read_only=True)

    def enlist(self, session: Session) -> None:
        """The door of a transaction this job opens beside its units of work (05 JOB-06 rev
        1.200; DG-KRN-JOB-04): called as the transaction's first statement, it takes the job's
        lock on ``session`` and beats in the job's workspace, and raises ``JobLost`` when the
        job is no longer this attempt's (``JobAttempt.enlist``). Nothing where no attempt runs:
        ``run_inline``, a context a test built."""
        attempt = self._runtime.attempt
        if attempt is not None:
            attempt.enlist(session, self.clock)

    def _touch(self, attempt: JobAttempt, **values: Any) -> None:
        """Move the job's ``updated_at`` (and ``values``) in a short transaction of its own. The
        write applies to the attempt's RUNNING job alone and raises ``JobLost`` otherwise (05
        JOB-04 rev 1.200): a handler that beats between its chunks stops at the first beat
        after it lost its job."""
        with tenant_session(self.principal.db_context) as session:
            attempt.beat(session, now=self.clock.now(), **values)

    def progress(self, done: int, total: int | None) -> None:
        """Record progress at most every 2 seconds, in its own short transaction (JOB-04)."""
        now = self.clock.now()
        attempt = self._attempt
        if attempt is None or (
            self._last_progress is not None and now - self._last_progress < PROGRESS_INTERVAL
        ):
            return
        self._last_progress = now
        self._touch(attempt, progress_done=done, progress_total=total)

    def heartbeat(self) -> None:
        """Mark the job alive; the sweeper fails RUNNING jobs silent for 10 minutes outside a
        transaction (JOB-06)."""
        if self._attempt is not None:
            self._touch(self._attempt)

    def cancel_requested(self) -> bool:
        """Whether ``POST /jobs/{id}/cancel`` asked this job to stop (JOB-05)."""
        if self._attempt is None:
            return False
        with self.read_session() as session:
            requested = session.execute(
                select(job.c.cancel_requested_at).where(
                    job.c.tenant_id == self.tenant_id, job.c.id == self.job_id
                )
            ).scalar_one_or_none()
        return requested is not None
