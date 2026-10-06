"""Close runs: the persisted, resumable close state machine (04 T-CLS-01, E-62, §15.3 API-R-39,
§15.4 ``CLOSE_RUN_FAILED``, §16.8 API-S-CloseRunCreate and API-S-CloseRun; 05 RCP-19, RCP-20,
JOB-03, JOB-07, §5.6; 03 REQ-CLS-012, REQ-CLS-013, REQ-OPS-006; PRD SM-14, NFR-14, NTF-05;
SCREENS_B §1.2; dev-guide DG-KRN-JOB-03 to DG-KRN-JOB-05; BUILD_SPEC CLO-19, CLO-20, BS4-D-03,
BS4-D-04; supervisor ruling R-79).

``start`` inserts a ``PENDING`` run with its fourteen ``PENDING`` steps and defers the
``CLOSE_RUN`` job; an entity, book and period with an active run (``PENDING``, ``RUNNING``,
``BLOCKED``) answers that run. A close run is a command of a close, and the LEGACY book has no
close of its own: ``start`` for that book and ``resume`` of a run of it are refused by name before
anything is written (``_refuse_legacy``; PRD ERR-76 rev 1.160; 04 T-REF-06 rev 1.230; item
CLO-RUN-LEGACY-1). The job — ``run_close`` — moves the run to ``RUNNING`` and executes
steps 1 to 13 in ``EXECUTED_STEPS`` order: the array of T-CLS-01 is the display order, and
``FX_REMEASUREMENT`` executes before ``RELEASE_SCHEDULES`` (supervisor ruling R-79 (b); 05 RCP-08
rev 1.9). ``LOCK`` stays ``PENDING`` for the lock job (BS4-D-03). One loop turn is one step:

1. a short transaction locks the run, stops when another job owns it, when it is no longer
   ``RUNNING`` or when a cancellation was requested, and otherwise records the next step that is
   not ``SUCCEEDED`` as ``RUNNING``;
2. the step runs — in one transaction with its own record when its work is one transaction
   (``_Step.once``: the work first, then the run row is locked and the step recorded, so that a
   failure keeps nothing of the step and a request to cancel does not wait for it), else in the
   transactions of its chunks (``_Step.chunked``) — and its status, ``finished_at`` and ``counts``
   are recorded.

A step that ended ``SUCCEEDED`` is never executed again, so a resumed run restarts at the first
step, in execution order, that is not ``SUCCEEDED`` (NFR-14).

A close run and the lock decision (item CLO-RUN-START-PIN-1; 04 §14.1 and §16.8 rev 1.228; 05 §5.6
rev 1.167; dev-guide DG-KRN-DB-08 rev 1.216; review finding F5 of 2026-10-01). ``start`` and
``resume`` take their advisory key and then read the period's state row ``FOR SHARE``, held to
their commit, before they ask whether the period is open: the decision takes that row ``FOR
UPDATE`` before it reads its gates, so a start or a resume that arrives while the lock is decided
waits and is refused once the period is ``closed``, and one that came first is read by the
decision's gates as the period's latest run. Only the period's latest run is resumed: the gate
reads the latest run, and a superseded run resumed beside a succeeded one would execute under a
lock the gate lets through. Measured before the pin: a start between the decision's gates and its
commit answered 202 and left a ``PENDING`` run in a period ``closed`` a moment later; a failed
run resumed before the decision was ``RUNNING`` while the lock was approved, and its job ran its
thirteen steps in the closed period.

Ends. ``BLOCKED``: ``RECOMPUTE_DIRTY`` left a quarantined group (RCP-20), or ``INVARIANTS`` found
the period's ledger out of balance (PRD SM-14 "failed invariant": the step is ``FAILED`` with its
problem and the ``CLOSE_RUN_FAILED`` item is raised). ``FAILED``: a step raised, or the job was
dead-lettered; the kernel ends the job ``FAILED`` and calls ``close_failed`` in the same
transaction, which records the step and the run ``FAILED``, raises the ``CLOSE_RUN_FAILED``
exception item of the entity, book and period and notifies the holders of ``period.lock`` for the
entity (NTF-05 "Controllers of the entity"; the kernel notifies the initiator). ``CANCELLED``: a
cancellation was requested; the step in progress ends first. ``SUCCEEDED``: steps 1 to 13
succeeded; the open ``CLOSE_RUN_FAILED`` item of the period is settled.

``RECOMPUTE_DIRTY`` (RCP-19) selects the dirty groups of the entity, defers one child
``CONTRACT_COMPUTE`` job per chunk of 250 groups with ``parent_job_id`` = this job, and polls the
children every 2 seconds. A child still ``QUEUED`` at the second poll after it was deferred is
cancelled and its chunk computed here, one transaction per group as the child would: close runs
that hold every worker while they wait cannot starve their own children. A dirty group whose
quarantine was waived and whose streams have not moved since is not computed again (T-CLS-01
"Ends of a run").

[J] The children compute at their own record time (``bundles.record_cutoff``), not at the run's
``cutoff_known_at``: a computation at an earlier cutoff would post the reversal of what a later
command posted, and a contract version's ``known_at`` would stop being monotonic per group.

[J] ``INTERFACE_COMPLETENESS`` and ``EXCEPTION_CHECK`` record what the lock's gates decide on and
never stop the run (SM-14 blocks a run only on quarantined contracts or a failed invariant).

The period-end steps (BUILD_SPEC CLO-20). ``FX_REMEASUREMENT``, ``RELEASE_SCHEDULES`` and
``NETTING_RECLASS`` each run one engine pass over the entity's groups and seal what it posts
(``period_end.post_pass``; R-79 (a), (c) to (e)). A pass seals the amounts of the run's own period
and is refused by name over an earlier period end no close run has posted (supervisor ruling
R-112: periods close in order): the run ends ``FAILED`` at that step and is resumed after the
earlier period's own run. ``INVARIANTS`` checks that the period's ledger
balances per currency. ``JOURNAL_SUMMARIZATION`` calculates a ``draft`` journal run under the run
(``summarise.calculate_run``, the ``JOURNAL_RUN_CALCULATE`` handler) when the period has no run yet
or holds a sealed posting no run covers. ``EXPORT``, ``ACKNOWLEDGEMENT_WAIT`` and ``GL_TIE_OUT``
record what they observe — the batches exported and acknowledged, the difference of the current
subledger-to-GL reconciliation or that no trial balance is attached — and never export,
acknowledge or reconcile (BS4-D-03). ``DATASET_FREEZE`` writes the twelve E-64 datasets as
``SNAPSHOT_DATASET`` files at ONE instant — the later of the step's application instant and its
transaction timestamp, the lock's own rule (ENGINE_SPEC_B S15-R-18, S15-R-18c) — and records
their hashes; the lock decision freezes again at its own cutoff and the file store's
deduplication makes an unchanged dataset the same file (BS4-D-04). ``lock_marked`` is called by
the lock decision, in its transaction: the ``LOCK`` step of the latest ``SUCCEEDED`` run of the
period becomes ``SUCCEEDED`` with the lock and the user who decided it.

[J] The ledger invariant is the one 04 DB-06 enforces at every seal, read again for the period as
a whole: per transaction currency the lines' transaction amounts sum to zero, and their functional
amounts sum to zero. The close-gate facts of 05 (``VC_REASSESSMENT_MISSING``,
``ROYALTY_ACCRUAL_MISSING``) join the step with BUILD_SPEC CLO-18, when the engine states them
(item ENG-S10-GATE-FACTS-1).

[J] A journal run is not calculated when the period has one and nothing new to journalise: an
empty ``draft`` run per close run would only ask for approvals of nothing.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, and_, any_, func, insert, or_, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api import numbering
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db import new_id, transitions
from erev_api.db.session import of_session_tenant, tenant_session
from erev_api.db.tables import (
    close_run,
    combination_group,
    contract,
    exception_item,
    import_upload,
    integration_connection,
    job,
    journal_batch,
    journal_run,
    ledger_chain_head,
    legal_entity,
    period,
    period_lock,
    reconciliation,
    subledger_line,
    sync_run,
    tenant_membership,
)
from erev_api.domain.close import (
    dependencies,
    freeze,
    gates,
    monitors,
    period_end,
    quarantines,
    reconciliations,
    snapshots,
)
from erev_api.domain.contracts import compute_job
from erev_api.domain.contracts.queries import primary_book
from erev_api.domain.imports import exceptions
from erev_api.domain.journals import commands as journal_commands
from erev_api.domain.journals import completeness, summarise
from erev_api.domain.platform import approval_queries
from erev_api.domain.platform.jobs import job_out_of
from erev_api.enums import (
    BookCode,
    CloseRunStatus,
    ComputationStatus,
    ComputationTrigger,
    ExceptionSeverity,
    ExceptionSource,
    ExceptionStatus,
    ImportStatus,
    JobKind,
    JobState,
    JournalRunGrain,
    JournalRunMode,
    JournalState,
    LockKind,
    NotificationKind,
    PrincipalKind,
    ReconciliationKind,
    SyncRunStatus,
)
from erev_api.events import notifications
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JOB_FAILED_TITLE, JOB_LABELS, JobOutcome, job_failed_body, task
from erev_api.periods import period_by_key
from erev_api.problems import Problem, ProblemError, from_db_error
from erev_api.registry.resolve import resolve
from erev_api.schemas.close_runs import CloseRunCancelIn, CloseRunCreateIn, CloseRunOut
from erev_api.schemas.common import JobOut

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "CHUNK_SIZE",
    "CLOSE_PERMISSION",
    "EXECUTED_STEPS",
    "READ_PERMISSION",
    "STEP_CODES",
    "StepResult",
    "cancel",
    "chunks",
    "close_failed",
    "get",
    "lock_marked",
    "outs",
    "read",
    "resume",
    "run_close",
    "start",
    "statement",
]

READ_PERMISSION: Final = "contract.read"  # 04 API-R-39
CLOSE_PERMISSION: Final = "period.close"  # SCREENS_B §1.2: run, resume and cancel
CONTROLLER_PERMISSION: Final = "period.lock"  # PRD NTF-05 "Controllers of the entity"
OBJECT_TYPE: Final = "close_run"
SERIES: Final = "CLOSE_RUN"
JOB: Final = JobKind.CLOSE_RUN
CREATE_ACTION: Final = "close_run.create"
RESUME_ACTION: Final = "close_run.resume"
CANCEL_ACTION: Final = "close_run.cancel"
STATUS_ACTION: Final = "close_run.status"
RULE_STATES: Final = "E-62"
RULE_ROW: Final = "T-CLS-01"
RUN_HREF: Final = "/api/v1/close-runs/{run_id}"
RUN_LINK: Final = "/close/{entity}/{book}/{period}/close-run"  # SCREENS_B §1.2 route

# 04 T-CLS-01 ``steps``, in its fixed order (REQ-CLS-012).
CUTOFF: Final = "CUTOFF"
INTERFACE_COMPLETENESS: Final = "INTERFACE_COMPLETENESS"
EXCEPTION_CHECK: Final = "EXCEPTION_CHECK"
RECOMPUTE_DIRTY: Final = "RECOMPUTE_DIRTY"
RELEASE_SCHEDULES: Final = "RELEASE_SCHEDULES"
FX_REMEASUREMENT: Final = "FX_REMEASUREMENT"
NETTING_RECLASS: Final = "NETTING_RECLASS"
INVARIANTS: Final = "INVARIANTS"
JOURNAL_SUMMARIZATION: Final = "JOURNAL_SUMMARIZATION"
EXPORT: Final = "EXPORT"
ACKNOWLEDGEMENT_WAIT: Final = "ACKNOWLEDGEMENT_WAIT"
GL_TIE_OUT: Final = "GL_TIE_OUT"
DATASET_FREEZE: Final = "DATASET_FREEZE"
LOCK: Final = "LOCK"
STEP_CODES: Final = (
    CUTOFF,
    INTERFACE_COMPLETENESS,
    EXCEPTION_CHECK,
    RECOMPUTE_DIRTY,
    RELEASE_SCHEDULES,
    FX_REMEASUREMENT,
    NETTING_RECLASS,
    INVARIANTS,
    JOURNAL_SUMMARIZATION,
    EXPORT,
    ACKNOWLEDGEMENT_WAIT,
    GL_TIE_OUT,
    DATASET_FREEZE,
    LOCK,
)
# The order the job executes steps 1 to 13 in (supervisor ruling R-79 (b); 05 RCP-08 rev 1.9):
# the FX pass, then the release pass, then the netting reclass, each reading the earlier ones
# as posted; every other step in the order of the array. The lock job completes LOCK
# (BS4-D-03).
EXECUTED_STEPS: Final = (
    CUTOFF,
    INTERFACE_COMPLETENESS,
    EXCEPTION_CHECK,
    RECOMPUTE_DIRTY,
    FX_REMEASUREMENT,
    RELEASE_SCHEDULES,
    NETTING_RECLASS,
    INVARIANTS,
    JOURNAL_SUMMARIZATION,
    EXPORT,
    ACKNOWLEDGEMENT_WAIT,
    GL_TIE_OUT,
    DATASET_FREEZE,
)
# SCREENS_B §1.2 step labels, for the NTF-05 body "<job label> failed at <step>".
STEP_LABELS: Final[Mapping[str, str]] = {
    CUTOFF: "Cut-off known at",
    INTERFACE_COMPLETENESS: "Interface completeness",
    EXCEPTION_CHECK: "Exception check",
    RECOMPUTE_DIRTY: "Recompute changed contracts",
    RELEASE_SCHEDULES: "Release schedules",
    FX_REMEASUREMENT: "FX remeasurement",
    NETTING_RECLASS: "Contract balance reclassification",
    INVARIANTS: "Invariant checks",
    JOURNAL_SUMMARIZATION: "Journal summarization",
    EXPORT: "Export",
    ACKNOWLEDGEMENT_WAIT: "Acknowledgement wait",
    GL_TIE_OUT: "Subledger to GL tie-out",
    DATASET_FREEZE: "Dataset freeze",
    LOCK: "Lock",
}

PENDING: Final = CloseRunStatus.PENDING.value
RUNNING: Final = CloseRunStatus.RUNNING.value
BLOCKED: Final = CloseRunStatus.BLOCKED.value
SUCCEEDED: Final = CloseRunStatus.SUCCEEDED.value
FAILED: Final = CloseRunStatus.FAILED.value
CANCELLED: Final = CloseRunStatus.CANCELLED.value
# ``ux_close_run__active``: one such run per entity, book and period.
ACTIVE_STATUSES: Final = (PENDING, RUNNING, BLOCKED)
RESUMABLE_STATUSES: Final = (FAILED, BLOCKED)

CHUNK_SIZE: Final = 250  # 05 RCP-19: groups per child CONTRACT_COMPUTE job
POLL_SECONDS: Final = 2.0  # 05 RCP-19: the close-run job polls its children every 2 seconds
LIVE_JOBS: Final = (JobState.QUEUED.value, JobState.RUNNING.value)
COMPUTED_JOBS: Final = (JobState.SUCCEEDED.value, JobState.SUCCEEDED_WITH_EXCEPTIONS.value)
FAILED_CODE: Final = "CLOSE_RUN_FAILED"  # 04 §15.4
# RFC 9457 base members a reader of the run sees of a failed step (04 §16.8).
PROBLEM_MEMBERS: Final = ("type", "title", "status", "detail")

UNKNOWN_ENTITY: Final = "Choose an entity of this workspace."
UNKNOWN_PERIOD: Final = "Choose a period of the entity's calendar."
BOOK_NOT_KEPT: Final = "{entity} keeps no {book} book for {period_key}."
PERIOD_NOT_OPEN: Final = (
    "{period_key} of {entity} in book {book} is {state}. A close run needs an open period, a "
    "period in soft close or a reopened one."
)
NOT_RESUMABLE: Final = "{no} is {status}. Only a failed or blocked close run is resumed."
# 04 §16.8 rev 1.259: the last sentence takes the words of the button that starts a run (SCREENS_B
# §1.1 "Run close"; the supervisor's word of 2026-10-02 02:51 on lane F-CLO-WEB's O1).
SUPERSEDED: Final = "{no} is not the latest close run of this period. Run close again."
OTHER_ACTIVE: Final = "{other} is already running for this period. {no} cannot be resumed."
NOT_CANCELLABLE: Final = "{no} is {status}. Only a close run that has not ended is cancelled."
UNBALANCED: Final = (
    "{count} of {checked} ledger invariants failed for {period_key} of {entity} in book {book}: "
    "{first}"
)
UNBALANCED_TXN: Final = "the {currency} lines sum to {amount} {currency}, not to zero"
UNBALANCED_FUNCTIONAL: Final = (
    "the lines sum to {amount} {currency} in the functional currency, not to zero"
)
DATASET_REFUSED: Final = "The {kind} dataset of {period_key} cannot be frozen ({reason})."
DATASETS_REFUSED: Final = "The datasets of {period_key} cannot be frozen ({reason})."
# The steps that seal postings, and the run counts they add up to (04 T-CLS-01 ``counts``).
PASS_STEPS: Final = (FX_REMEASUREMENT, RELEASE_SCHEDULES, NETTING_RECLASS)
PASS_COUNTS: Final = ("postings", "lines")
# A long step marks its job alive (05 JOB-06: a job silent for 10 minutes is stalled).
BEAT_INTERVAL: Final = timedelta(seconds=30)
EXPORTED_STATES: Final = (JournalState.EXPORTED.value, JournalState.ACKNOWLEDGED.value)
CHILD_FAILED: Final = (
    "A recalculation job of {no} ended {state}; the contracts it had not reached are unchanged."
)
# PRD IMP-132, word for word (tests/architecture/test_copy_catalogue_drift.py binds the two).
FAILED_MESSAGE: Final = (
    "Close run {close_run_no} for {entity_code} {period_label} failed at {step_label}: {reason}. "
    "Nothing was committed for that step. Resume the close run once the cause is fixed."
)
SETTLED: Final = "Close run {no} succeeded."


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _refused(message: str, *, field: str = "status", rule_id: str = RULE_STATES) -> Problem:
    error = ProblemError(field=field, rule_id=rule_id, message=message)
    return Problem("invalid-transition", message, errors=[error])


def _invalid(field: str, message: str) -> Problem:
    error = ProblemError(field=field, rule_id=RULE_ROW, message=message)
    return Problem("validation-failed", "1 field needs attention.", errors=[error])


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def chunks(ids: Sequence[UUID], size: int = CHUNK_SIZE) -> list[list[UUID]]:
    """``ids`` in consecutive chunks of at most ``size`` (05 RCP-19: 250 groups per child job)."""
    if size < 1:
        raise ValueError("a chunk holds at least one group")
    return [list(ids[start : start + size]) for start in range(0, len(ids), size)]


# --- the run row ---------------------------------------------------------------------------------


def _new_steps() -> list[dict[str, Any]]:
    return [
        {
            "step_code": code,
            "status": PENDING,
            "started_at": None,
            "finished_at": None,
            "counts": {},
            "problem": None,
        }
        for code in STEP_CODES
    ]


def _no_beat() -> None:
    """A step that runs outside a job has no heartbeat."""


@dataclass(frozen=True, slots=True)
class _Run:
    """A close run with the period it closes; ``beat`` is the heartbeat of the job that runs it
    (05 JOB-06), called by a step between two pieces of long work."""

    row: Mapping[str, Any]
    scope: gates.PeriodScope
    beat: Callable[[], None] = _no_beat

    @property
    def id(self) -> UUID:
        return UUID(str(self.row["id"]))

    @property
    def number(self) -> str:
        return str(self.row["close_run_no"])

    @property
    def status(self) -> str:
        return _text(self.row["status"])

    @property
    def steps(self) -> list[dict[str, Any]]:
        return [dict(step) for step in self.row["steps"]]

    def step(self, code: str) -> dict[str, Any]:
        return next(step for step in self.steps if step["step_code"] == code)


def _scope(session: Session, row: Mapping[str, Any]) -> gates.PeriodScope:
    scope = gates.scope_of_period(
        session,
        UUID(str(row["entity_id"])),
        _text(row["book_code"]),
        UUID(str(row["period_id"])),
    )
    if scope is None:
        raise Problem("not-found")
    return scope


def _locked(session: Session, run_id: UUID) -> _Run:
    """The run under ``FOR UPDATE`` with its period; 404 ``not-found`` for an unknown id."""
    row = (
        session.execute(select(close_run).where(close_run.c.id == run_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return _Run(row=dict(row), scope=_scope(session, dict(row)))


def _move(uow: UnitOfWork, run: _Run, to_status: str | None, values: Mapping[str, Any]) -> _Run:
    """One DB-03 change of the run (a status move, or its steps and counts), audited when the
    status changes."""
    row_version = int(run.row["row_version"])
    updated = transitions.apply(
        uow.session,
        OBJECT_TYPE,
        run.id,
        to_status=to_status,
        set_values={**values, "row_version": row_version + 1, **_stamps(uow)},
        expected_status=None if to_status is None else run.status,
        expected_row_version=row_version,
    )
    if to_status is not None:
        uow.audit(
            action=STATUS_ACTION,
            object_type=OBJECT_TYPE,
            object_id=run.id,
            object_version=str(row_version + 1),
            before={"status": run.status},
            after={
                "status": to_status,
                "current_step_code": updated["current_step_code"],
                "counts": updated["counts"],
            },
        )
    return _Run(row=dict(updated), scope=run.scope)


def _with_step(run: _Run, code: str, **values: Any) -> list[dict[str, Any]]:
    steps = run.steps
    for step in steps:
        if step["step_code"] == code:
            step.update(values)
    return steps


def _instant(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _newest_job(session: Session, run_id: UUID) -> Mapping[str, Any] | None:
    """The newest ``CLOSE_RUN`` job of the run: the one that owns it."""
    found = (
        session.execute(
            select(job.c.id, job.c.state, job.c.progress_done, job.c.progress_total)
            .where(
                job.c.kind == JOB.value,
                job.c.subject_type == OBJECT_TYPE,
                job.c.subject_id == run_id,
            )
            .order_by(job.c.created_at.desc(), job.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return None if found is None else dict(found)


def _serialise(uow: UnitOfWork, scope: gates.PeriodScope) -> None:
    """One start or resume at a time per entity, book and period (05 §5.6 lock
    ``close:<entity>:<book>:<period>``), so that "the active run" is one row."""
    key = (
        f"erev.close:{uow.principal.tenant_id}:{scope.entity_id}:{scope.book_code}:"
        f"{scope.period_id}"
    )
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


def _pinned(session: Session, scope: gates.PeriodScope) -> gates.PeriodScope:
    """``scope`` read again with its state row ``FOR SHARE``, held to the end of the transaction
    (item CLO-RUN-START-PIN-1; 04 DB-07; dev-guide DG-KRN-DB-08 (1a)): a lock decision takes the
    row ``FOR UPDATE`` before it reads its gates, so a start or a resume that arrives while the
    lock is decided waits and then reads the state the decision committed, and one that came
    first is read by the decision's gates as the period's latest run."""
    pinned = gates.scope_of_period(
        session, scope.entity_id, scope.book_code, scope.period_id, share=True
    )
    if pinned is None:
        raise Problem("not-found")
    return pinned


def _latest(session: Session, scope: gates.PeriodScope) -> Mapping[str, Any] | None:
    """The period's latest close run — the newest by ``created_at``, then id: the one the gate
    ``CLOSE_RUN_COMPLETED`` reads (``gates.close_run_facts``)."""
    found = (
        session.execute(
            select(close_run.c.id, close_run.c.close_run_no)
            .where(
                close_run.c.entity_id == scope.entity_id,
                close_run.c.book_code == scope.book_code,
                close_run.c.period_id == scope.period_id,
            )
            .order_by(close_run.c.created_at.desc(), close_run.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return None if found is None else dict(found)


def _require_open(scope: gates.PeriodScope) -> None:
    if scope.state in gates.EVALUATED_STATES:
        return
    message = PERIOD_NOT_OPEN.format(
        period_key=scope.period_key,
        state=scope.state,
        entity=scope.entity_code,
        book=scope.book_code,
    )
    raise _refused(message, field="period_key")


def _active(session: Session, scope: gates.PeriodScope) -> Mapping[str, Any] | None:
    found = (
        session.execute(
            select(close_run.c.id, close_run.c.close_run_no).where(
                close_run.c.entity_id == scope.entity_id,
                close_run.c.book_code == scope.book_code,
                close_run.c.period_id == scope.period_id,
                close_run.c.status.in_(ACTIVE_STATUSES),
            )
        )
        .mappings()
        .first()
    )
    return None if found is None else dict(found)


# --- commands ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Started:
    """``POST /close-runs``: the run, and the job when the command started it."""

    run_id: UUID
    job: JobOut | None


def _refuse_legacy(session: Session, book_code: str) -> None:
    """PRD ERR-76 for a close run (rev 1.160; 04 T-REF-06 "The LEGACY book's rows" and §16.8 rev
    1.230; the supervisor's ruling of 2026-10-01; item CLO-RUN-LEGACY-1). A close run is a command
    of a close; the LEGACY book has none of its own and follows the close of the primary book — no
    journal run exists for it (04 T-SL-06), so its run stopped at ``JOURNAL_SUMMARIZATION`` on an
    unhandled error, after its period-end steps had made the LEGACY period a row of a window. The
    answer is the one the four period commands give (``commands._refuse_legacy_book``): 409
    ``invalid-transition`` under rule ``LEGACY_FOLLOWS_PRIMARY``, with the primary book's label.
    Asked after the permission check — a caller who may not close the entity is answered as for
    any book — and before anything is read for the run or written: no run row, no job, no
    close-run number, no audit event."""
    from erev_api.domain.close import commands  # ``commands`` imports this module

    commands._refuse_legacy_book(session, book_code)


def start(uow: UnitOfWork, body: CloseRunCreateIn) -> Started:
    """Start the close run of an entity, book and period, or answer the run that is active for
    them (SCREENS_B §1.2: "Starting a run while one is active returns the active run"). The
    period's state row is pinned ``FOR SHARE`` before the period is asked for (module docstring,
    "A close run and the lock decision")."""
    session = uow.session
    found = session.execute(
        select(legal_entity.c.id, legal_entity.c.calendar_id).where(
            legal_entity.c.code == body.entity_code
        )
    ).one_or_none()
    if found is None:
        raise _invalid("entity_code", UNKNOWN_ENTITY)
    entity_id, calendar_id = UUID(str(found[0])), UUID(str(found[1]))
    require_for_entity(uow.ctx, CLOSE_PERMISSION, entity_id)
    book = body.book if body.book is not None else BookCode(primary_book(session))
    _refuse_legacy(session, book.value)
    try:
        at = period_by_key(session, calendar_id=calendar_id, period_key=body.period_key)
    except LookupError:
        raise _invalid("period_key", UNKNOWN_PERIOD) from None
    scope = gates.scope_of_period(session, entity_id, book.value, at.id)
    if scope is None:
        message = BOOK_NOT_KEPT.format(
            entity=body.entity_code, book=book.value, period_key=body.period_key
        )
        raise _invalid("book", message)
    _serialise(uow, scope)
    scope = _pinned(session, scope)
    active = _active(session, scope)
    if active is not None:
        return Started(run_id=UUID(str(active["id"])), job=None)
    _require_open(scope)
    run_id = new_id()
    job_row = uow.defer(
        JOB, {"close_run_id": str(run_id)}, subject_type=OBJECT_TYPE, subject_id=run_id
    )
    principal = uow.principal
    number = numbering.next_number(uow, SERIES)
    cutoff = freeze.freeze_cutoff(session, uow.now)
    session.execute(
        insert(close_run).values(
            tenant_id=principal.tenant_id,
            id=run_id,
            close_run_no=number,
            entity_id=entity_id,
            book_code=book.value,
            period_id=at.id,
            status=PENDING,
            cutoff_known_at=cutoff,
            current_step_code=None,
            steps=_new_steps(),
            counts={},
            job_id=job_row["id"],
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            row_version=1,
            **_stamps(uow),
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        object_version="1",
        after={
            "close_run_no": number,
            "entity_id": str(entity_id),
            "book_code": book.value,
            "period_id": str(at.id),
            "period_key": body.period_key,
            "cutoff_known_at": cutoff.isoformat(),
            "job_id": str(job_row["id"]),
        },
    )
    return Started(run_id=run_id, job=job_out_of(session, UUID(str(job_row["id"]))))


def resume(uow: UnitOfWork, run_id: UUID) -> JobOut:
    """``POST /close-runs/{id}/resume``: a ``FAILED`` or ``BLOCKED`` run goes back to ``RUNNING``
    under a further ``CLOSE_RUN`` job, which continues at the first step that is not ``SUCCEEDED``
    (NFR-14). Only the period's latest run is resumed (item CLO-RUN-START-PIN-1; 04 §16.8 rev
    1.228): the gate ``CLOSE_RUN_COMPLETED`` reads the latest run, so a run that a newer one has
    superseded would execute beside a succeeded run the lock is decided on — measured: resumed
    before a lock decision it was ``RUNNING`` while the gate passed, and its job ran its thirteen
    steps in the closed period."""
    session = uow.session
    seen = (
        session.execute(
            select(close_run.c.entity_id, close_run.c.book_code, close_run.c.period_id).where(
                close_run.c.id == run_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if seen is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, CLOSE_PERMISSION, UUID(str(seen["entity_id"])))
    _refuse_legacy(session, _text(seen["book_code"]))
    # dev-guide DG-KRN-DB-08 rev 1.216: the advisory key, the state row, then the run row — the
    # lock decision takes the state row before the row of a close run as well
    unpinned = _scope(session, dict(seen))
    _serialise(uow, unpinned)
    scope = _pinned(session, unpinned)
    run = _locked(session, run_id)
    if run.status not in RESUMABLE_STATUSES:
        raise _refused(NOT_RESUMABLE.format(no=run.number, status=run.status))
    other = _active(session, scope)
    if other is not None and UUID(str(other["id"])) != run.id:
        raise _refused(OTHER_ACTIVE.format(other=other["close_run_no"], no=run.number))
    latest = _latest(session, scope)
    if latest is not None and UUID(str(latest["id"])) != run.id:
        raise _refused(SUPERSEDED.format(no=run.number))
    _require_open(scope)
    job_row = uow.defer(
        JOB, {"close_run_id": str(run.id)}, subject_type=OBJECT_TYPE, subject_id=run.id
    )
    _move(uow, run, RUNNING, {"finished_at": None})
    uow.audit(
        action=RESUME_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run.id,
        object_version=str(int(run.row["row_version"]) + 1),
        before={"status": run.status, "current_step_code": run.row["current_step_code"]},
        after={"status": RUNNING, "job_id": str(job_row["id"])},
    )
    return job_out_of(session, UUID(str(job_row["id"])))


def cancel(uow: UnitOfWork, run_id: UUID, body: CloseRunCancelIn) -> CloseRunOut:
    """``POST /close-runs/{id}/cancel``: a run whose job is running records the request and ends
    ``CANCELLED`` after its current step; a run whose job has not started, and a ``BLOCKED`` run,
    is ``CANCELLED`` at once. The reason is kept in the audit event."""
    session = uow.session
    seen = session.execute(
        select(close_run.c.entity_id).where(close_run.c.id == run_id)
    ).scalar_one_or_none()
    if seen is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, CLOSE_PERMISSION, UUID(str(seen)))
    run = _locked(session, run_id)
    if run.status not in ACTIVE_STATUSES:
        raise _refused(NOT_CANCELLABLE.format(no=run.number, status=run.status))
    owner = (
        session.execute(
            select(job.c.id, job.c.state)
            .where(
                job.c.kind == JOB.value,
                job.c.subject_type == OBJECT_TYPE,
                job.c.subject_id == run.id,
                job.c.state.in_(LIVE_JOBS),
            )
            .order_by(job.c.created_at.desc(), job.c.id.desc())
            .limit(1)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    requested = False
    if owner is not None and _text(owner["state"]) == JobState.RUNNING.value:
        # The job ends the run after its current step (05 JOB-05).
        session.execute(
            update(job)
            .where(job.c.id == owner["id"], job.c.cancel_requested_at.is_(None))
            .values(cancel_requested_at=uow.now, **_stamps(uow))
        )
        requested = True
    else:
        if owner is not None:
            transitions.apply(
                session,
                "job",
                UUID(str(owner["id"])),
                to_status=JobState.CANCELLED.value,
                set_values={
                    "cancel_requested_at": uow.now,
                    "finished_at": uow.now,
                    **_stamps(uow),
                },
                expected_status=JobState.QUEUED.value,
            )
        _cancelled(uow, run)
    uow.audit(
        action=CANCEL_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run.id,
        before={"status": run.status, "current_step_code": run.row["current_step_code"]},
        after={"status": run.status if requested else CANCELLED, "reason": body.reason},
    )
    return get(session, uow.principal, run.id)


def _cancelled(uow: UnitOfWork, run: _Run) -> _Run:
    """End ``run`` ``CANCELLED`` along DB-03 (E-62 knows ``RUNNING`` → ``CANCELLED`` only, so a
    run that is not running passes through ``RUNNING`` in the same transaction)."""
    if run.status != RUNNING:
        values: dict[str, Any] = {"finished_at": None}
        if run.row["started_at"] is None:
            values["started_at"] = uow.now
        run = _move(uow, run, RUNNING, values)
    steps = run.steps
    for step in steps:
        if step["status"] in (RUNNING, BLOCKED):
            step.update(status=CANCELLED, finished_at=_instant(uow.now))
    return _move(
        uow, run, CANCELLED, {"steps": steps, "current_step_code": None, "finished_at": uow.now}
    )


# --- steps ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StepResult:
    """How a step ended: its status — ``SUCCEEDED``; ``BLOCKED``, which stops the run; or
    ``FAILED`` with its ``problem``, a failed invariant, which also stops the run ``BLOCKED`` (PRD
    SM-14) — the ``counts`` of its ``steps`` element, what it sets in the run's ``counts``, and
    the columns of the run it writes with its end (``run_values``: what the first period-end
    step read, T-CLS-01 ``rates_read`` and ``registry_read``)."""

    status: str = SUCCEEDED
    counts: Mapping[str, Any] = field(default_factory=dict)
    run_counts: Mapping[str, Any] = field(default_factory=dict)
    problem: Mapping[str, Any] | None = None
    run_values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Step:
    """How a step executes: ``once`` in the transaction that records it, so that a failure keeps
    nothing of it, or ``chunked`` over transactions of its own."""

    once: Callable[[UnitOfWork, _Run], StepResult] | None = None
    chunked: Callable[[JobContext, _Run], StepResult] | None = None


def _cutoff(uow: UnitOfWork, run: _Run) -> StepResult:
    """``CUTOFF``: the knowledge cutoff was fixed when the run was started (T-CLS-01)."""
    del uow, run
    return StepResult()


def _previous_lock_at(session: Session, scope: gates.PeriodScope) -> datetime | None:
    """When the entity last locked an earlier period of the book: the start of "this close"."""
    found = session.execute(
        select(func.max(period_lock.c.created_at))
        .select_from(
            period_lock.join(
                period,
                and_(
                    period.c.tenant_id == period_lock.c.tenant_id,
                    period.c.id == period_lock.c.period_id,
                ),
            )
        )
        .where(
            period_lock.c.entity_id == scope.entity_id,
            period_lock.c.book_code == scope.book_code,
            period_lock.c.kind == LockKind.LOCK.value,
            period.c.end_date < scope.start_date,
        )
    ).scalar_one_or_none()
    return found if isinstance(found, datetime) else None


def _interface_completeness(uow: UnitOfWork, run: _Run) -> StepResult:
    """``INTERFACE_COMPLETENESS``: the imports committed and the sync runs that succeeded since
    the latest lock of an earlier period, and the failures the ``INTERFACES_COMPLETE`` gate counts.
    An import counts when its rows name the run's entity or it names none (T-IMP-02
    ``named_entity_ids``: a workspace-level upload, or one whose entities are not resolved); a
    sync run when its connection serves the entity (T-INT-01 ``entity_ids``, empty = every
    entity): a figure of one entity's close is not drawn from another entity's interfaces
    (supervisor ruling R-103 (a))."""
    session = uow.session
    entity_id = run.scope.entity_id
    since = _previous_lock_at(session, run.scope)
    names = import_upload.c.named_entity_ids
    imports = (
        select(func.count())
        .select_from(import_upload)
        .where(
            import_upload.c.status == ImportStatus.COMMITTED.value,
            or_(names.is_(None), func.cardinality(names) == 0, any_(names) == entity_id),
        )
    )
    served = integration_connection.c.entity_ids
    syncs = (
        select(func.count())
        .select_from(
            sync_run.join(
                integration_connection,
                and_(
                    integration_connection.c.tenant_id == sync_run.c.tenant_id,
                    integration_connection.c.id == sync_run.c.integration_connection_id,
                ),
            )
        )
        .where(
            sync_run.c.status == SyncRunStatus.SUCCEEDED.value,
            or_(func.cardinality(served) == 0, any_(served) == entity_id),
        )
    )
    if since is not None:
        imports = imports.where(import_upload.c.created_at > since)
        syncs = syncs.where(sync_run.c.created_at > since)
    complete = int(session.execute(imports).scalar_one()) + int(session.execute(syncs).scalar_one())
    failures = gates.blocker_counts(session, run.scope)["interface_failures"]
    return StepResult(counts={"interface_runs_complete": complete, "interface_failures": failures})


def _exception_check(uow: UnitOfWork, run: _Run) -> StepResult:
    """``EXCEPTION_CHECK``: the data-quality monitors run for the period (REQ-CLS-019), the gates
    are evaluated and stored, and the open exceptions that block the lock are counted. The step
    writes findings and gate results, so it pins the period's state row first and is refused by
    name for a period that is no longer open (item CLO-GATE-RUN-2; 04 T-CLS-03 rev 1.228)."""
    scope = _pinned(uow.session, run.scope)
    _require_open(scope)
    monitors.run_monitors(uow, scope.entity_id, scope.book_code, scope.period_id)
    gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id)
    open_items = gates.blocker_counts(uow.session, scope)["exceptions_open"]
    return StepResult(counts={"blocking_exceptions": open_items})


def _dirty_groups(session: Session, entity_id: UUID) -> list[UUID]:
    """The dirty combination groups with a contract of the entity, in id order (05 RCP-19;
    ``ix_combination_group__dirty``) — the groups the ``NO_DIRTY_GROUPS`` gate counts."""
    statement = (
        select(combination_group.c.id)
        .where(
            combination_group.c.dirty_since.is_not(None),
            select(contract.c.id)
            .where(
                contract.c.combination_group_id == combination_group.c.id,
                contract.c.contracting_entity_id == entity_id,
            )
            .exists(),
        )
        .order_by(combination_group.c.id)
    )
    return [UUID(str(value)) for value in session.scalars(statement)]


def _waived_quarantines(session: Session, group_ids: Sequence[UUID]) -> set[UUID]:
    """``quarantines.standing_waived``: the groups whose quarantine was waived and still stands."""
    return quarantines.standing_waived(session, group_ids)


def _pause(seconds: float) -> None:
    """Between two polls of the children (05 RCP-19)."""
    time.sleep(seconds)


def _compute_chunk(jc: JobContext, group_ids: Sequence[UUID]) -> dict[str, int]:
    """A chunk computed by this job, as a child ``CONTRACT_COMPUTE`` job computes it: group by
    group, one transaction per group (05 RCP-19; 04 §6.0)."""
    counts = {"groups": len(group_ids), "succeeded": 0, "quarantined": 0, "failed": 0}
    for group_id in group_ids:
        with jc.unit_of_work() as uow:
            outcome = compute_job.compute_group(
                uow, group_id, trigger=ComputationTrigger.COMMAND, job_id=jc.job_id
            )
            uow.commit()
        status = outcome.status or ComputationStatus.FAILED
        counts[status.value.lower()] += 1
        jc.heartbeat()
    return counts


def _take_over(jc: JobContext, child_id: UUID) -> bool:
    """Cancel a child no worker has started; False when a worker took it meanwhile."""
    with jc.unit_of_work() as uow:
        try:
            transitions.apply(
                uow.session,
                "job",
                child_id,
                to_status=JobState.CANCELLED.value,
                set_values={
                    "cancel_requested_at": uow.now,
                    "finished_at": uow.now,
                    **_stamps(uow),
                },
                expected_status=JobState.QUEUED.value,
            )
        except Problem as problem:
            if problem.slug != "invalid-transition":
                raise
            return False
        uow.commit()
    return True


def _await_children(
    jc: JobContext, run: _Run, children: Mapping[UUID, Sequence[UUID]]
) -> list[Mapping[str, Any]]:
    """Poll the child jobs until each has ended and answer their ``counts`` (05 RCP-19). A child
    seen ``QUEUED`` at two polls running is taken over: cancelled and computed here. A child that
    ended ``FAILED`` or was cancelled by someone else fails the step, by name."""
    total = sum(len(group_ids) for group_ids in children.values())
    waiting = dict(children)
    found: list[Mapping[str, Any]] = []
    queued_before: set[UUID] = set()
    while waiting:
        with jc.read_session() as session:
            rows = {
                UUID(str(row["id"])): row
                for row in session.execute(
                    select(job.c.id, job.c.state, job.c.result, job.c.progress_done).where(
                        job.c.id.in_(sorted(waiting, key=str))
                    )
                ).mappings()
            }
        queued: list[UUID] = []
        running = 0
        for child_id in sorted(waiting, key=str):
            row = rows[child_id]
            state = _text(row["state"])
            if state in COMPUTED_JOBS:
                found.append(dict((row["result"] or {}).get("counts") or {}))
                del waiting[child_id]
            elif state == JobState.QUEUED.value:
                queued.append(child_id)
            elif state == JobState.RUNNING.value:
                running += int(row["progress_done"] or 0)
            else:
                raise Problem("invalid-transition", CHILD_FAILED.format(no=run.number, state=state))
        done = sum(int(counts.get("groups", 0)) for counts in found) + running
        jc.progress(done, total)
        jc.heartbeat()
        stale = next((child_id for child_id in queued if child_id in queued_before), None)
        queued_before = set(queued)
        if stale is not None and _take_over(jc, stale):
            found.append(_compute_chunk(jc, waiting.pop(stale)))
            continue
        if waiting:
            _pause(POLL_SECONDS)
    jc.progress(total, total)
    return found


def _recompute_dirty(jc: JobContext, run: _Run) -> StepResult:
    """``RECOMPUTE_DIRTY`` (05 RCP-19, RCP-20; REQ-CLS-013): the module docstring."""
    with jc.read_session() as session:
        dirty = _dirty_groups(session, run.scope.entity_id)
        waived = _waived_quarantines(session, dirty)
    todo = [group_id for group_id in dirty if group_id not in waived]
    children: dict[UUID, list[UUID]] = {}
    if todo:
        with jc.unit_of_work() as uow:
            for chunk in chunks(todo):
                child = uow.defer(
                    JobKind.CONTRACT_COMPUTE,
                    {
                        "combination_group_ids": [str(group_id) for group_id in chunk],
                        "trigger": ComputationTrigger.COMMAND.value,
                    },
                    parent_job_id=jc.job_id,
                )
                children[UUID(str(child["id"]))] = chunk
            uow.commit()
    found = _await_children(jc, run, children)
    recomputed = sum(int(counts.get("succeeded", 0)) for counts in found)
    quarantined = sum(
        int(counts.get("quarantined", 0)) + int(counts.get("failed", 0)) for counts in found
    )
    counts = {
        "groups_recomputed": recomputed,
        "groups_quarantined": quarantined,
        "groups_waived": len(waived),
    }
    return StepResult(
        status=BLOCKED if quarantined else SUCCEEDED,
        counts=counts,
        run_counts={
            "groups_recomputed": recomputed,
            "groups_quarantined": quarantined,
        },
    )


# --- the period-end steps (BUILD_SPEC CLO-20) -----------------------------------------------------


def _pass(pass_name: str) -> Callable[[UnitOfWork, _Run], StepResult]:
    """The step of one engine pass over the entity's groups (``period_end.post_pass``): what it
    sealed, the groups it ran over and the dirty groups it left out."""

    def run_pass(uow: UnitOfWork, run: _Run) -> StepResult:
        found = period_end.post_pass(
            uow,
            close_run_id=run.id,
            close_run_no=run.number,
            scope=run.scope,
            pass_name=pass_name,
            beat=run.beat,
        )
        return StepResult(
            counts={
                "postings": found.postings,
                "lines": found.lines,
                "groups": found.groups,
                "groups_skipped": found.groups_skipped,
            },
            # 04 T-CLS-01 rev 1.291: what the first period-end step read, stored with its end
            run_values=(
                {}
                if found.inputs is None
                else {"rates_read": found.inputs.rates, "registry_read": found.inputs.registry}
            ),
        )

    return run_pass


@dataclass(frozen=True, slots=True)
class LedgerSums:
    """The sums of a period's subledger lines of one entity and book, debit positive: the
    transaction amounts per transaction currency, the functional amounts as one figure, and the
    number of lines."""

    txn: Mapping[str, Decimal]
    functional: Decimal
    lines: int


def _ledger_sums(session: Session, scope: gates.PeriodScope) -> LedgerSums:
    rows = session.execute(
        select(
            subledger_line.c.txn_currency,
            func.coalesce(func.sum(subledger_line.c.amount_txn), Decimal(0)),
            func.coalesce(func.sum(subledger_line.c.amount_functional), Decimal(0)),
            func.count(),
        )
        .where(
            subledger_line.c.period_end_date == scope.end_date,
            subledger_line.c.entity_id == scope.entity_id,
            subledger_line.c.book_code == scope.book_code,
            subledger_line.c.period_id == scope.period_id,
        )
        .group_by(subledger_line.c.txn_currency)
        .order_by(subledger_line.c.txn_currency)
    ).all()
    return LedgerSums(
        txn={str(currency).strip(): Decimal(txn) for currency, txn, _, _ in rows},
        functional=sum((Decimal(functional) for _, _, functional, _ in rows), Decimal(0)),
        lines=sum(int(count) for _, _, _, count in rows),
    )


def _shown(problem: Problem) -> dict[str, Any]:
    """The four base members of a problem, as a step keeps them (04 §16.8)."""
    body = problem.to_json(instance="")
    return {name: body.get(name) for name in PROBLEM_MEMBERS}


def _invariants(uow: UnitOfWork, run: _Run) -> StepResult:
    """``INVARIANTS``: debits equal credits for the entity, book and period — per transaction
    currency in transaction amounts, and in functional amounts (04 DB-06, read for the period as
    a whole). A failure ends the step ``FAILED`` with its problem and the run ``BLOCKED``."""
    scope = run.scope
    found = _ledger_sums(uow.session, scope)
    functional = scope.functional_currency.strip()
    failures = [
        UNBALANCED_TXN.format(
            currency=currency, amount=reconciliations.amount_text(amount, currency)
        )
        for currency, amount in sorted(found.txn.items())
        if amount != 0
    ]
    if found.functional != 0:
        failures.append(
            UNBALANCED_FUNCTIONAL.format(
                amount=reconciliations.amount_text(found.functional, functional),
                currency=functional,
            )
        )
    counts = {
        "invariants_checked": len(found.txn) + 1,
        "invariant_failures": len(failures),
        "lines_checked": found.lines,
    }
    if not failures:
        return StepResult(counts=counts)
    detail = UNBALANCED.format(
        count=len(failures),
        checked=counts["invariants_checked"],
        period_key=scope.period_key,
        entity=scope.entity_code,
        book=scope.book_code,
        first=failures[0],
    )
    return StepResult(
        status=FAILED, counts=counts, problem=_shown(Problem("ledger-unbalanced", detail))
    )


def _journal_pending(uow: UnitOfWork, scope: gates.PeriodScope) -> bool:
    """Whether a journal run calculated now would be the period's first or may hold a posting:
    the period has no run that is not cancelled (``JE_COMPLETE`` fails closed without one), or a
    sealed posting of the period is journalised by no run and its contract is under no
    ``journal_export`` hold now (``completeness``: the uncovered postings; the held ones are not
    among them). Such a posting lies beyond what the runs cover, or a run left it out under a
    hold released since — the period's next run takes that one over (ENGINE_SPEC_B S14-R-17 rev
    1.164; 04 DB-16 rev 1.267; item JRN-HELD-AFTER-EXPORT-1). Until that revision only a posting
    beyond the runs counted, and a step beside a released posting calculated nothing. The
    calculation decides what it would hold: where that is nothing — a posting inside the range of
    a run whose held detail cannot be verified — it makes no run and the step succeeds."""
    found = completeness.assert_completeness(uow, scope.entity_id, scope.book_code, scope.period_id)
    return found.run_count == 0 or bool(found.uncovered_postings)


def _journal_counts(session: Session, journal_run_id: UUID | None) -> dict[str, int]:
    """``{batches, journal_lines}`` of the journal run the step calculated; zero without one."""
    if journal_run_id is None:
        return {"batches": 0, "journal_lines": 0}
    batches = session.execute(
        select(func.count())
        .select_from(journal_batch)
        .where(journal_batch.c.journal_run_id == journal_run_id)
    ).scalar_one()
    lines = session.execute(
        select(journal_run.c.line_count).where(journal_run.c.id == journal_run_id)
    ).scalar_one()
    return {"batches": int(batches), "journal_lines": int(lines)}


def _journal_summarization(jc: JobContext, run: _Run) -> StepResult:
    """``JOURNAL_SUMMARIZATION``: the ``JOURNAL_RUN_CALCULATE`` handler calculates one ``draft``
    journal run under the close run, at the mode and grain the policies resolve (POL-005,
    POL-006), in its own transaction; a line that fails validation fails the step with the
    finding's problem (CLO-10). A run that already has its journal run does not calculate again."""
    scope = run.scope
    params: dict[str, Any] | None = None
    with jc.unit_of_work() as uow:  # reads only: nothing is committed here
        session = uow.session
        if _journal_runs(session, [run.id]).get(run.id) is None and _journal_pending(uow, scope):
            book = BookCode(scope.book_code)

            def resolved(key: str, *, at: datetime = uow.now) -> str:
                found = resolve(
                    session, key, book_code=book, entity_id=scope.entity_id, known_at=at
                )
                return str(found.value)

            params = {
                "journal_run_id": str(new_id()),
                "entity_id": str(scope.entity_id),
                "book_code": scope.book_code,
                "period_id": str(scope.period_id),
                "mode": JournalRunMode(resolved(journal_commands.POSTING_MODE)).value,
                "grain": JournalRunGrain(resolved(journal_commands.SUMMARIZATION)).value,
                "cutoff_known_at": uow.now.isoformat(),
                "close_run_id": str(run.id),
            }
    if params is not None:
        summarise.calculate_run(jc, params)
    with jc.read_session() as session:
        counts = _journal_counts(session, _journal_runs(session, [run.id]).get(run.id))
    return StepResult(counts=counts, run_counts={"batches": counts["batches"]})


def _batch_states(session: Session, scope: gates.PeriodScope) -> dict[str, int]:
    """The journal batches of the period's journal runs, by state; cancelled runs and batches
    are left out."""
    cancelled = JournalState.CANCELLED.value
    live = select(journal_run.c.id).where(
        journal_run.c.entity_id == scope.entity_id,
        journal_run.c.book_code == scope.book_code,
        journal_run.c.period_id == scope.period_id,
        journal_run.c.state != cancelled,
    )
    return {
        _text(state): int(count)
        for state, count in session.execute(
            select(journal_batch.c.state, func.count())
            .where(journal_batch.c.journal_run_id.in_(live), journal_batch.c.state != cancelled)
            .group_by(journal_batch.c.state)
        )
    }


def _export(uow: UnitOfWork, run: _Run) -> StepResult:
    """``EXPORT`` observes: the period's batches and those exported. It exports nothing and
    writes no outbox message, in a sandbox as elsewhere (BS4-D-03; 05 SBX-08)."""
    found = _batch_states(uow.session, run.scope)
    exported = sum(found.get(state, 0) for state in EXPORTED_STATES)
    return StepResult(counts={"batches": sum(found.values()), "batches_exported": exported})


def _acknowledgement_wait(uow: UnitOfWork, run: _Run) -> StepResult:
    """``ACKNOWLEDGEMENT_WAIT`` observes: the period's batches and those the GL acknowledged. It
    waits for nothing (BS4-D-03)."""
    found = _batch_states(uow.session, run.scope)
    acknowledged = found.get(JournalState.ACKNOWLEDGED.value, 0)
    return StepResult(counts={"batches": sum(found.values()), "batches_acknowledged": acknowledged})


def _gl_tie_out(uow: UnitOfWork, run: _Run) -> StepResult:
    """``GL_TIE_OUT`` observes the current subledger-to-GL reconciliation of the period: the
    difference its summary states and its variances, or that no trial balance is attached. It
    generates and attaches nothing (BS4-D-03)."""
    scope = run.scope
    row = (
        uow.session.execute(
            select(
                reconciliation.c.id,
                reconciliation.c.totals,
                reconciliation.c.variance_count,
                reconciliation.c.source_file_id,
                reconciliation.c.sync_run_id,
            ).where(
                reconciliation.c.entity_id == scope.entity_id,
                reconciliation.c.book_code == scope.book_code,
                reconciliation.c.period_id == scope.period_id,
                reconciliation.c.kind == ReconciliationKind.SUBLEDGER_TO_GL.value,
                ~gates.superseded(),
            )
        )
        .mappings()
        .first()
    )
    if row is None or (row["source_file_id"] is None and row["sync_run_id"] is None):
        return StepResult(counts={"trial_balance_attached": False})
    functional = scope.functional_currency.strip()
    stated = {
        str(item["currency"]).strip(): item["difference"]
        for item in reconciliations.summary_of(row["totals"] or [])
    }
    difference = stated.get(functional)
    return StepResult(
        counts={
            "trial_balance_attached": True,
            "reconciliation_id": str(row["id"]),
            "currency": functional,
            "difference": reconciliations.amount_text(Decimal(0), functional)
            if difference is None
            else difference.amount,
            "variance_count": int(row["variance_count"]),
        }
    )


def _dataset_freeze(uow: UnitOfWork, run: _Run) -> StepResult:
    """``DATASET_FREEZE``: the twelve E-64 datasets of the period as ``SNAPSHOT_DATASET`` files,
    all at one instant — the later of the step's application instant and its transaction
    timestamp (``freeze.freeze_cutoff``; ENGINE_SPEC_B S15-R-18, S15-R-18c), so that they hold
    what the run itself posted — with their hashes, that instant and the book's chain position.
    A dataset the registry refuses fails the step by name (S15-R-18b)."""
    scope = run.scope
    session = uow.session
    cutoff = freeze.freeze_cutoff(session, uow.now)
    # 05 TXN-03 rev 1.121 (supervisor ruling R-119 (d)): the step's transaction is idle while the
    # freeze's SYSTEM reader produces a dataset; the connection default of 60 s ended the step.
    freeze.allow_idle(session)
    registry = dependencies.snapshot_registry()
    try:
        datasets = snapshots.freeze_datasets(
            uow,
            scope.entity_id,
            scope.book_code,
            scope.period_id,
            cutoff,
            frozen_at=cutoff,
            registry=registry.datasets,
            scope_type=registry.scope,
        )
    except registry.refusal as refused:
        message = DATASET_REFUSED.format(
            kind=str(getattr(refused, "kind", "")),
            period_key=scope.period_key,
            reason=str(getattr(refused, "reason", refused)),
        )
        raise _refused(message, field="datasets", rule_id=freeze.RULE_FREEZE) from refused
    except snapshots.MachineArtefactRefused as refused:
        message = DATASETS_REFUSED.format(period_key=scope.period_key, reason=str(refused))
        raise _refused(message, field="datasets", rule_id=freeze.RULE_FREEZE) from refused
    hashes = {item.kind: item.file_sha256 for item in datasets}
    head = session.execute(
        select(ledger_chain_head.c.last_chain_seq).where(
            ledger_chain_head.c.book_code == scope.book_code
        )
    ).scalar_one_or_none()
    return StepResult(
        counts={
            "datasets": hashes,
            "datasets_frozen": len(hashes),
            "frozen_known_at": cutoff.isoformat(),
            "ledger_chain_seq": 0 if head is None else int(head),
        },
        run_counts={"datasets": hashes},
    )


STEPS: Final[dict[str, _Step]] = {
    CUTOFF: _Step(once=_cutoff),
    INTERFACE_COMPLETENESS: _Step(once=_interface_completeness),
    EXCEPTION_CHECK: _Step(once=_exception_check),
    RECOMPUTE_DIRTY: _Step(chunked=_recompute_dirty),
    FX_REMEASUREMENT: _Step(once=_pass(period_end.FX_REMEASUREMENT)),
    RELEASE_SCHEDULES: _Step(once=_pass(period_end.CLOSE_RELEASE)),
    NETTING_RECLASS: _Step(once=_pass(period_end.NETTING_RECLASS)),
    INVARIANTS: _Step(once=_invariants),
    JOURNAL_SUMMARIZATION: _Step(chunked=_journal_summarization),
    EXPORT: _Step(once=_export),
    ACKNOWLEDGEMENT_WAIT: _Step(once=_acknowledgement_wait),
    GL_TIE_OUT: _Step(once=_gl_tie_out),
    DATASET_FREEZE: _Step(once=_dataset_freeze),
}


# --- the job -------------------------------------------------------------------------------------


def _owns(session: Session, run_id: UUID, job_id: UUID) -> bool:
    newest = _newest_job(session, run_id)
    return newest is not None and UUID(str(newest["id"])) == job_id


def _next_step(jc: JobContext, run_id: UUID) -> str | None:
    """Record the next step ``RUNNING`` and answer its code; None when the job is done with the
    run: another job owns it, it is no longer running, it was cancelled, or every executed step
    has succeeded (the run then ends ``SUCCEEDED``)."""
    cancel_requested = jc.cancel_requested()
    with jc.unit_of_work() as uow:
        run = _locked(uow.session, run_id)
        if not _owns(uow.session, run_id, jc.job_id):
            return None
        if run.status == PENDING:
            run = _move(uow, run, RUNNING, {"started_at": uow.now})
        if run.status != RUNNING:
            return None
        if cancel_requested:
            _cancelled(uow, run)
            uow.commit()
            return None
        pending = next(
            (code for code in EXECUTED_STEPS if run.step(code)["status"] != SUCCEEDED), None
        )
        if pending is None:
            _move(uow, run, SUCCEEDED, {"current_step_code": None, "finished_at": uow.now})
            _settle_failure(uow, run)
            uow.commit()
            return None
        steps = _with_step(
            run,
            pending,
            status=RUNNING,
            started_at=_instant(uow.now),
            finished_at=None,
            counts={},
            problem=None,
        )
        _move(uow, run, None, {"steps": steps, "current_step_code": pending})
        uow.commit()
    return pending


def _record(uow: UnitOfWork, run: _Run, code: str, result: StepResult) -> str:
    """The end of a step: its status, ``finished_at``, ``counts`` and problem, the run's
    ``counts``, and the run ``BLOCKED`` when the step blocks it or fails an invariant — the
    latter with the ``CLOSE_RUN_FAILED`` item of the period. Answers how the run goes on:
    ``SUCCEEDED`` or ``BLOCKED``."""
    values: dict[str, Any] = {
        "status": result.status,
        "finished_at": _instant(uow.now),
        "counts": dict(result.counts),
    }
    if result.problem is not None:
        values["problem"] = {name: result.problem.get(name) for name in PROBLEM_MEMBERS}
    steps = _with_step(run, code, **values)
    counts = {**dict(run.row["counts"] or {}), **dict(result.run_counts)}
    if code in PASS_STEPS:
        for name in PASS_COUNTS:
            counts[name] = sum(
                int(step["counts"].get(name, 0))
                for step in steps
                if step["step_code"] in PASS_STEPS
            )
    changed: dict[str, Any] = {"steps": steps, "counts": counts}
    if result.status == SUCCEEDED:
        # written once, with the step that read them (DB-03 refuses a second write)
        changed.update(result.run_values)
        _move(uow, run, None, changed)
        return SUCCEEDED
    run = _move(uow, run, BLOCKED, {**changed, "finished_at": uow.now})
    if result.status == FAILED:
        newest = _newest_job(uow.session, run.id)
        _failed_item(
            uow,
            run,
            code,
            dict(values.get("problem") or {}),
            job_id=None if newest is None else UUID(str(newest["id"])),
        )
    return BLOCKED


def _seen(session: Session, run_id: UUID, beat: Callable[[], None] = _no_beat) -> _Run:
    """The run as it is committed, without a lock."""
    row = session.execute(select(close_run).where(close_run.c.id == run_id)).mappings().one()
    return _Run(row=dict(row), scope=_scope(session, dict(row)), beat=beat)


def _beat(jc: JobContext) -> Callable[[], None]:
    """The job's heartbeat, at most once in ``BEAT_INTERVAL`` of the job's clock."""
    last = [jc.clock.now()]

    def beat() -> None:
        now = jc.clock.now()
        if now - last[0] >= BEAT_INTERVAL:
            last[0] = now
            jc.heartbeat()

    return beat


def _execute(jc: JobContext, run_id: UUID, code: str) -> str:
    """Run one step and record its end; how the run goes on (``SUCCEEDED``, ``BLOCKED``, or
    ``CANCELLED`` for a job that no longer owns the run). A ``once`` step works first and locks
    the run row only to record itself, in the same transaction: a failure keeps nothing of it, a
    job that lost the run rolls its work back, and a request to cancel or resume does not wait
    for the step. A ``chunked`` step keeps what its own transactions committed."""
    spec = STEPS[code]
    if spec.once is not None:
        with jc.unit_of_work() as uow:
            seen = _seen(uow.session, run_id, _beat(jc))
            if seen.status != RUNNING or not _owns(uow.session, run_id, jc.job_id):
                return CANCELLED
            result = spec.once(uow, seen)
            run = _locked(uow.session, run_id)
            if run.status != RUNNING or not _owns(uow.session, run_id, jc.job_id):
                return CANCELLED
            ended = _record(uow, run, code, result)
            uow.commit()
        return ended
    assert spec.chunked is not None
    with jc.read_session() as session:
        seen = _seen(session, run_id, _beat(jc))
    result = spec.chunked(jc, seen)
    with jc.unit_of_work() as uow:
        run = _locked(uow.session, run_id)
        if run.status != RUNNING or not _owns(uow.session, run_id, jc.job_id):
            return CANCELLED
        ended = _record(uow, run, code, result)
        uow.commit()
    return ended


def _result(run_id: UUID, session: Session) -> dict[str, Any]:
    counts = session.execute(
        select(close_run.c.counts).where(close_run.c.id == run_id)
    ).scalar_one_or_none()
    return {"href": RUN_HREF.format(run_id=run_id), "counts": dict(counts or {})}


def _failed_item(
    uow: UnitOfWork, run: _Run, code: Any, shown: Mapping[str, Any], *, job_id: UUID | None
) -> tuple[str, str]:
    """Raise the ``CLOSE_RUN_FAILED`` item of the run's entity, book and period (04 §15.4; PRD
    IMP-132) for the step ``code`` and its problem; (step label, reason) as the item states
    them."""
    scope = run.scope
    label = "the start" if code is None else STEP_LABELS[str(code)]
    reason = str(shown.get("detail") or shown.get("title") or "").rstrip(".")
    exceptions.raise_exception_item(
        uow,
        source=ExceptionSource.CLOSE,
        code=FAILED_CODE,
        severity=ExceptionSeverity.BLOCKING,
        message=FAILED_MESSAGE.format(
            close_run_no=run.number,
            entity_code=scope.entity_code,
            period_label=scope.period_name,
            step_label=label,
            reason=reason,
        ),
        dedupe=exceptions.dedupe_key(ExceptionSource.CLOSE, FAILED_CODE, scope.state_id),
        entity_id=scope.entity_id,
        period_id=scope.period_id,
        close_run_id=run.id,
        source_payload={
            "close_run_id": str(run.id),
            "close_run_no": run.number,
            "step_code": code,
            "job_id": None if job_id is None else str(job_id),
            "problem": dict(shown),
        },
    )
    return label, reason


def close_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The ``CLOSE_RUN`` job's terminal hook (05 JOB-07; DG-KRN-JOB-05), in the transaction that
    ends the job ``FAILED``: the step in progress and the run are recorded ``FAILED`` with the
    job's problem, the ``CLOSE_RUN_FAILED`` item of the entity, book and period is raised, and the
    holders of ``period.lock`` for the entity are notified (the kernel notifies the initiator). A
    run that a newer job owns, or that has already ended, is left as it is."""
    session = uow.session
    run_id = UUID(str(params["close_run_id"]))
    try:
        run = _locked(session, run_id)
    except Problem:
        return
    newest = _newest_job(session, run_id)
    if newest is None or _text(newest["state"]) != JobState.FAILED.value:
        return
    if run.status == PENDING:
        run = _move(uow, run, RUNNING, {"started_at": uow.now})
    if run.status != RUNNING:
        return
    code = run.row["current_step_code"]
    shown = {name: problem.get(name) for name in PROBLEM_MEMBERS}
    steps = run.steps
    for step in steps:
        if step["status"] == RUNNING:
            step.update(status=FAILED, finished_at=_instant(uow.now), problem=shown)
    run = _move(uow, run, FAILED, {"steps": steps, "finished_at": uow.now})
    scope = run.scope
    label, reason = _failed_item(uow, run, code, shown, job_id=UUID(str(newest["id"])))
    initiator = run.row["created_by"]
    own = (
        []
        if initiator is None
        else [
            UUID(str(value))
            for value in session.scalars(
                select(tenant_membership.c.id).where(
                    of_session_tenant(tenant_membership), tenant_membership.c.user_id == initiator
                )
            )
        ]
    )
    job_label = JOB_LABELS[JOB]
    notifications.notify_permission_holders(
        uow,
        permission=CONTROLLER_PERMISSION,
        entity_id=scope.entity_id,
        kind=NotificationKind.JOB_FAILED,
        title=JOB_FAILED_TITLE.format(label=job_label),
        body=job_failed_body(label=job_label, step=label, reason=reason, problem=problem),
        link_path=RUN_LINK.format(
            entity=scope.entity_code, book=scope.book_code, period=scope.period_key
        ),
        subject_type=OBJECT_TYPE,
        subject_id=run.id,
        exclude_membership_ids=own,
    )


def _settle_failure(uow: UnitOfWork, run: _Run) -> None:
    """A run that succeeded settles the open ``CLOSE_RUN_FAILED`` item of its period."""
    scope = run.scope
    key = exceptions.dedupe_key(ExceptionSource.CLOSE, FAILED_CODE, scope.state_id)
    open_ids = uow.session.scalars(
        select(exception_item.c.id).where(
            exception_item.c.dedupe_key == key,
            exception_item.c.status.in_(
                (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
            ),
        )
    ).all()
    for item_id in open_ids:
        exceptions.settle_record_reprocess(
            uow, UUID(str(item_id)), resolved=True, resolution=SETTLED.format(no=run.number)
        )


@task(JOB, on_failure=close_failed)
def run_close(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``CLOSE_RUN`` (05 §5.6 queue ``close``; no automatic retry — ``resume`` restarts at the
    failed step): the module docstring."""
    run_id = UUID(str(params["close_run_id"]))
    ended = SUCCEEDED
    while True:
        code = _next_step(jc, run_id)
        if code is None:
            break
        try:
            ended = _execute(jc, run_id, code)
        except DBAPIError as error:
            # a refusal of the database the catalogue names (the period was closed meanwhile, a
            # lock wait ran out, an entry does not balance) is the step's problem, not an
            # unexpected error (DG-KRN-ERR-02)
            named = from_db_error(error)
            if named is None:
                raise
            raise named from error
        if ended != SUCCEEDED:
            break
        jc.heartbeat()
    with jc.read_session() as session:
        result = _result(run_id, session)
    return JobOutcome(
        state="SUCCEEDED_WITH_EXCEPTIONS" if ended == BLOCKED else "SUCCEEDED", result=result
    )


# --- the lock's mark (BS4-D-03) ------------------------------------------------------------------


def lock_marked(uow: UnitOfWork, scope: gates.PeriodScope, lock_id: UUID) -> UUID | None:
    """The ``LOCK`` step of the latest ``SUCCEEDED`` close run of the entity, book and period
    becomes ``SUCCEEDED`` with the lock and the user who decided it; the id of that run, or None
    when the period has no succeeded run — the gate ``CLOSE_RUN_COMPLETED`` lets no lock be
    requested or decided without one (item CLO-GATE-RUN-1), so only a lock replayed into a
    sandbox, which runs no close run of the source's, has none. The lock decision calls it in its
    own transaction after the lock is written, so a decision that is refused, or answered 409
    ``lock-conflict`` and decided again, leaves the step ``PENDING``. No running job holds the
    row of a ``SUCCEEDED`` run, so the decision does not wait here (04 DB-07 order)."""
    session = uow.session
    found = session.execute(
        select(close_run.c.id)
        .where(
            close_run.c.entity_id == scope.entity_id,
            close_run.c.book_code == scope.book_code,
            close_run.c.period_id == scope.period_id,
            close_run.c.status == SUCCEEDED,
        )
        .order_by(close_run.c.created_at.desc(), close_run.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if found is None:
        return None
    run = _locked(session, UUID(str(found)))
    at = _instant(uow.now)
    steps = _with_step(
        run,
        LOCK,
        status=SUCCEEDED,
        started_at=at,
        finished_at=at,
        counts={"period_lock_id": str(lock_id), "locked_by_id": str(uow.principal.id)},
        problem=None,
    )
    _move(uow, run, None, {"steps": steps})
    return run.id


# --- reads ---------------------------------------------------------------------------------------

ROW_COLUMNS: Final = (
    *close_run.c,
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.name.label("entity_name"),
    period.c.period_key,
    period.c.name.label("period_name"),
    period.c.start_date,
    period.c.end_date,
)


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller (DG-CMD-13)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


def statement(principal: Principal) -> Select[Any]:
    """API-S-CloseRun rows inside the principal's ``contract.read`` scope (REQ-PLT-012)."""
    row = close_run.c
    joined = close_run.join(
        legal_entity,
        and_(legal_entity.c.tenant_id == row.tenant_id, legal_entity.c.id == row.entity_id),
    ).join(period, and_(period.c.tenant_id == row.tenant_id, period.c.id == row.period_id))
    found = select(*ROW_COLUMNS).select_from(joined)
    scope = principal.permission_scopes.get(READ_PERMISSION)
    if isinstance(scope, frozenset):
        found = found.where(close_run.c.entity_id.in_(sorted(scope, key=str)))
    return found


def _jobs(session: Session, ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    """The newest ``CLOSE_RUN`` job of each run."""
    found: dict[UUID, dict[str, Any]] = {}
    if not ids:
        return found
    for row in session.execute(
        select(job.c.id, job.c.state, job.c.progress_done, job.c.progress_total, job.c.subject_id)
        .where(
            job.c.kind == JOB.value, job.c.subject_type == OBJECT_TYPE, job.c.subject_id.in_(ids)
        )
        .order_by(job.c.created_at, job.c.id)
    ).mappings():
        found[UUID(str(row["subject_id"]))] = {
            "id": row["id"],
            "state": _text(row["state"]),
            "progress": {"done": int(row["progress_done"] or 0), "total": row["progress_total"]},
        }
    return found


def _journal_runs(session: Session, ids: Sequence[UUID]) -> dict[UUID, UUID]:
    """The journal run each run's ``JOURNAL_SUMMARIZATION`` calculated (T-SL-06 ``close_run_id``);
    a cancelled one is not named."""
    found: dict[UUID, UUID] = {}
    if not ids:
        return found
    for run_id, journal_run_id in session.execute(
        select(journal_run.c.close_run_id, journal_run.c.id)
        .where(
            journal_run.c.close_run_id.in_(ids),
            journal_run.c.state != JournalState.CANCELLED.value,
        )
        .order_by(journal_run.c.created_at, journal_run.c.id)
    ):
        found[UUID(str(run_id))] = UUID(str(journal_run_id))
    return found


def _locker(step: Mapping[str, Any]) -> UUID | None:
    """The user a ``LOCK`` step names (``lock_marked``)."""
    found = (step.get("counts") or {}).get("locked_by_id")
    return None if found is None else UUID(str(found))


def _step_out(step: Mapping[str, Any], names: Mapping[UUID, str]) -> dict[str, Any]:
    """A ``steps`` element as API-S-CloseRun serves it; the ``LOCK`` step's ``locked_by`` is the
    API-S-Actor of the user who decided the lock, named as that user is named now."""
    problem = step.get("problem")
    counts = dict(step.get("counts") or {})
    locker = _locker(step)
    if locker is not None:
        del counts["locked_by_id"]
        counts["locked_by"] = approval_queries.actor(locker, PrincipalKind.USER.value, names)
    return {
        "step_code": step["step_code"],
        "status": step["status"],
        "started_at": step.get("started_at"),
        "finished_at": step.get("finished_at"),
        "counts": counts,
        "problem": None if not problem else {name: problem.get(name) for name in PROBLEM_MEMBERS},
    }


def outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[CloseRunOut]:
    """API-S-CloseRun of each ``statement`` row with its newest job and its journal run."""
    ids = [UUID(str(row["id"])) for row in rows]
    jobs = _jobs(session, ids)
    journals = _journal_runs(session, ids)
    lockers = [_locker(step) for row in rows for step in row["steps"]]
    names = approval_queries.display_names(
        session, [*(row["created_by"] for row in rows), *lockers]
    )
    found: list[CloseRunOut] = []
    for row in rows:
        run_id = UUID(str(row["id"]))
        found.append(
            CloseRunOut.model_validate(
                {
                    "id": run_id,
                    "close_run_no": row["close_run_no"],
                    "entity": {
                        "id": row["entity_id"],
                        "code": row["entity_code"],
                        "name": row["entity_name"],
                    },
                    "book": _text(row["book_code"]),
                    "period": {
                        "id": row["period_id"],
                        "period_key": row["period_key"],
                        "name": row["period_name"],
                        "start_date": row["start_date"],
                        "end_date": row["end_date"],
                    },
                    "status": _text(row["status"]),
                    "cutoff_known_at": row["cutoff_known_at"],
                    "current_step_code": row["current_step_code"],
                    "steps": [_step_out(step, names) for step in row["steps"]],
                    "counts": dict(row["counts"] or {}),
                    "job": jobs.get(run_id),
                    "journal_run_id": journals.get(run_id),
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "created_by": approval_queries.actor(
                        row["created_by"], _text(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "row_version": row["row_version"],
                }
            )
        )
    return found


def get(session: Session, principal: Principal, run_id: UUID) -> CloseRunOut:
    """``GET /close-runs/{id}``; 404 ``not-found`` outside the caller's entities."""
    row = session.execute(statement(principal).where(close_run.c.id == run_id)).mappings().first()
    if row is None:
        raise Problem("not-found")
    return outs(session, [dict(row)])[0]
