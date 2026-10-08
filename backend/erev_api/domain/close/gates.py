"""Close blockers and gate evaluation (04 §16.8 API-S-Period ``blockers``, API-S-PeriodCockpit
``derived_blockers``; T-CLS-02, T-CLS-03; E-60, E-122; PRD §5.3 BR-CLS-01; SCREENS_B §1.1 BLK-01 to
BLK-16 and the gate label table; 03 REQ-CLS-008, REQ-CLS-009; BUILD_SPEC CLO-4, CLO-GATE-RUN-1,
header XR-12).

``blocker_counts`` answers the twelve API-S-Period counts of one entity, book and period in one
statement; ``derived_counts`` the two E-122 derived blockers. ``signals`` gathers what the fourteen
gates read, ``gate_results`` maps it to one ``GateResult`` per gate check code, and
``evaluate_gates`` stores the results on the period's checklist items, creating the items of every
active template first.

[J] L7-2-Q-1 to Q-6 (docs/reviews/loop/sprint/L7-2.md):

- Exceptions count while ``OPEN`` or ``IN_PROGRESS`` with severity ``BLOCKING`` or ``WARNING`` —
  an item of source ``DATA_QUALITY`` only when ``BLOCKING`` (supervisor ruling R-57; 04 Table
  15.4-E rev 1.106: a WARNING finding of the monitors holds no lock) — for
  the period (``period_id`` null or the period) and the entity ([J] D-88 L7-2-Q-1): (a) the item
  names the entity; (b) it names no entity and a contract of the entity; (b2) it names no entity
  or contract and a combination group holding a contract of the entity; (c) it names no entity,
  contract or group (import-, file- and tenant-level items), counted for every entity under XR-12
  — except the item of an import, which holds the entities its upload names, and the item of a
  sync run, which holds the entities its connection serves (supervisor ruling R-121 (i), item
  CLO-QUARANTINE-READ-1; ``_of_no_named_entity``). ``item_of_entity`` is that attribution
  without the gate's status, severity and period conditions: the one the exception list's
  ``entity`` filter and the home page's figure read too.
  ``INFO`` items do not block a close. ``CONTROL_TOTALS_MISMATCH`` counts only in
  ``interface_failures``; ``unmapped_products`` uses the same clause as ``exceptions_open``.
  An item ``FX_RATE_CHANGED_AFTER_LOCK`` (source ``CLOSE``, ``WARNING``) names a closed period
  and is an item of the period its difference posts to (``close.rate_changes``; 04 T-REF-11 "A
  rate changed after a lock", rev 1.291): it counts there, and holds that period's lock until
  it is waived or the closed period is reopened — no exemption of the monitors' kind.
  An import that failed before its commit holds no lock (04 T-IMP-05 rev 1.270; the
  supervisor's ruling of 2026-10-02): the ``IMPORT_PROCESSING_FAILED`` item of an upload that
  ended ``INVALID`` — its validation or its dry run failed, nothing was written — is not
  counted (``_failed_before_commit``); the item of a failed commit is, as before.
- Pending approvals count for the entity when the request names it, or when it names no entity and
  its subject resolves to the entity: a contract, an event submission, an obligation, a policy
  override, an estimate version, a judgement record, a journal run, a manual adjustment, a
  checklist item or an exception item of the entity (``item_of_entity``).
- The period's own lock request is no pending approval of its period (item
  CLO-LOCK-REQUEST-OWN-GATE-1; 04 §16.8 ``blockers`` rev 1.311; PRD BR-CLS-01 rev 1.205; the
  supervisor's ruling of 2026-10-02): ``approvals_pending`` leaves out the ``PENDING``
  ``PERIOD_LOCK`` request whose subject is the period state asked — the lock request of a period
  in soft close and the permanent-lock request of a closed one (``own_lock_request``). One
  statement counts for every reader, so the cockpit, the period read, the home's close panel and
  every evaluation of ``APPROVALS_CLEARED`` say the same. Counted as before: a request of another
  period state of the entity — another period's or another book's — and every ``PERIOD_REOPEN``
  request, the period's own included: while a reopen request waits for its approvers no
  ``closing`` period of the entity moves to ``closed`` (04 §14.1 "A decision's basis under the
  row lock"). Until then the request counted itself: between "Submit for lock" and the decision
  the gate read ``FAILED`` "Pending approvals: 1", the cockpit's read stored that without an
  audit event and the screen called the lock unavailable, while the decision — its request
  ``APPROVED`` before its hook reads the gates — counted none and locked.
- Nor is the request that asks to waive this very count (item
  CLO-APPROVALS-WAIVER-OWN-REQUEST-1; 04 §16.8 ``blockers`` rev 1.318; PRD BR-CLS-01 rev 1.206;
  the supervisor's ruling of 2026-10-03): ``approvals_pending`` leaves out the ``PENDING``
  ``EXCEPTION_WAIVER`` request whose subject is the period's own ``APPROVALS_CLEARED`` item
  (``own_gate_waiver_request``) — by the type, the subject and the item's gate, so the waiver
  request of another gate's item, and of another period's item, counts as before. A waiver
  covers the count it was approved for and its request states that count (04 T-CLS-03 rev
  1.305), and this gate's waiver changed its own count by being asked: the first read of the
  cockpit stored one more, and the approval then answered 409 ``stale-approval`` and voided the
  request — a waiver the product offers that nobody could approve once anybody had looked.
- Interface failures (CTL-002; BR-INT-03; 04 §16.8 rev 1.106; supervisor ruling R-45 (d)): the
  failed imports whose ``CONTROL_TOTALS_MISMATCH`` item is still open, for every period and for
  the entities the upload names — every entity while it names none or is not resolved (04 rev
  1.206, ruling R-121 (i); before, every failed import held every entity) — plus the sync runs
  (T-INT-02) of the entity's connections that ended ``FAILED`` or ``CONTROL_TOTAL_MISMATCH`` and
  are not cleared (``uncleared_sync_runs``).
- Failed jobs (BLK-08): a close run or journal run of the period counts once, when its newest job
  is ``FAILED`` — a run resumed to success shows none (supervisor ruling R-103 (a), item
  CLO-BLK08-NEWEST-1).
- A journal run is required (E-122 ``JOURNAL_RUN_NOT_CALCULATED``), so ``JE_BALANCED`` and
  ``BATCHES_ACKNOWLEDGED`` fail with a count of 1 and the detail "Journal run not calculated"
  while no non-cancelled run exists.
- ``JE_COMPLETE`` (CLO-10) is the completeness assertion of the period's non-cancelled runs
  (``journals.completeness``): uncovered activity, account differences and JE sequence gaps,
  each named; without a run it fails "Journal run not calculated" like ``JE_BALANCED``.
  exception items of the entity and period (``data_quality_blocking``, ``data_quality_gate``; the
  monitors of ``close/monitors.py`` raise them); ``CONTROLLER_CERTIFIED`` fails with "Awaiting
  Controller certification at lock" until CLO-6 certifies at lock.
- ``BATCHES_ACKNOWLEDGED`` (CLO-14; REQ-JE-016; CTL-021) counts the batches of the period's
  non-cancelled runs that are neither ``acknowledged`` nor ``cancelled``: a batch still to be
  sent, an ``exported`` batch whose ERP reference nobody recorded and a ``failed`` batch each
  hold the lock, until ``POST /journal-batches/{id}/acknowledge`` or a retry moves them. A
  ``failed`` batch also leaves by the cancel of its run, once its ledger holds none of it, and
  by its hand-over, which makes it an ``exported`` batch to acknowledge (04 T-SL-07 "The ways
  out of ``failed``", rev 1.159).
- ``MANUAL_ADJUSTMENTS_CLEARED`` (CLO-12; REQ-JE-019; 04 T-SL-05 ``is_deferred_past_lock``)
  counts the ``DRAFT`` and ``SUBMITTED`` adjustments of the period that are not deferred past
  lock: an approved deferral leaves the adjustment ``SUBMITTED`` without a pending request, so it
  holds neither this gate nor ``APPROVALS_CLEARED``.
- An automatic item is written only when its status, count or detail changes, so
  ``result.evaluated_at`` is the time the stored result was established; ``WAIVED`` and
  ``NOT_APPLICABLE`` items are never evaluated again.
- Reconciliations count through their current row — the latest generated of a kind, entity, book
  and period (``superseded``; CLO-16; 04 T-CLS-06 rev 1.121; supervisor ruling R-54 (b)): a
  required kind counts while its current reconciliation is missing, or not ``REVIEWED``,
  ``AUTO_CERTIFIED`` or ``CERTIFIED``. A reviewed or auto-certified one that the period has
  overtaken does not count as reviewed (``overtaken``; supervisor ruling R-58 (e)): the gate
  names it out of date, and the unsigned count and cockpit KPI read it the same way. Ledger
  seals and document counts establish freshness, with timestamps for pre-0121 records. The
  GL kind watches posting history through period end; other kinds watch that period's lines.
- ``CLOSE_RUN_COMPLETED`` (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and R-116 (e)): the
  latest close run of the entity, book and period ended ``SUCCEEDED``, and no computed contract
  group holds a period end of the period, or of an earlier one, still to post (04 T-CON-03;
  ``contracts.period_ends``). Without a run it fails "Close run not completed"; a latest run in
  another status is named with that status; a run the contracts have overtaken is "out of date"
  with the count of those groups. Never waivable: a period end that was not posted is not a risk
  a signature accepts.
- What ``CLOSE_RUN_COMPLETED`` counts (item CLO-GATE-RUN-2; 04 §16.8 rev 1.228; review findings
  F3 and F8 of 2026-10-01): a computed group that holds a contract and either holds a
  ``period_ends_open`` entry of the entity and book on or before the period's last day — dirty or
  not: becoming dirty posts nothing — or holds no such entry and has a contract of the entity:
  nothing recorded says that its period ends are posted. A dirty group is ``NO_DIRTY_GROUPS``'s
  as well; the one whose quarantine stands waived is that gate's alone
  (``quarantines.standing_waived``), since no run can pass it. Not counted: a group that holds no
  contract, and a group without an entry that only performs for the entity ([J] whether it has
  lines of the entity is not asked on every read of the gate; a run marks it when it passes it).
- What a run read (item CLO-RATE-AFTER-RUN-1; 04 T-CLS-01 "What a run read" and §16.8 rev 1.291;
  the supervisor's ruling of 2026-10-02 08:56): a succeeded run whose first period-end step
  recorded what its passes could read of the tenant's reference data — the exchange rates in
  force through the period's last day and the period-pinned policy values, as two digests
  (``close.run_inputs``) — is out of date while the same read differs now, and the gate fails by
  name: the remedy is another run, which posts the difference or nothing. Never a time: a
  version's ``published_at`` is the start of its approval's unit of work, so the gate reads the
  rates in force whenever their version was published (``run_inputs.standing``) — a lock
  decision that waited for an approval began before that approval's instant. A run without the
  two digests (started before revision 0127) is read as before.
- Gate results are stored only under the period's state row (item CLO-GATE-RUN-2; 04 T-CLS-03
  rev 1.228; review finding F6): ``evaluate_gates`` pins it ``FOR SHARE`` itself — the lock
  decision holds it ``FOR UPDATE`` — and ``materialise_for_view`` pins it once it has found
  something to store, then stores nothing for a period that is no longer evaluated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Date,
    Select,
    Uuid,
    and_,
    any_,
    cast,
    column,
    exists,
    func,
    literal,
    not_,
    or_,
    select,
    true,
    tuple_,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from erev_api.approvals.subjects import CHECKLIST_WAIVER_BASIS
from erev_api.db import new_id, transitions
from erev_api.db.session import every_entity_scope
from erev_api.db.tables import (
    approval_request,
    close_checklist_item,
    close_checklist_template,
    close_run,
    combination_group,
    contract,
    contract_event,
    contract_hold,
    contract_version,
    estimate,
    estimate_version,
    event_submission,
    exception_item,
    import_upload,
    integration_connection,
    job,
    journal_batch,
    journal_run,
    judgement_record,
    legal_entity,
    manual_adjustment,
    obligation,
    period,
    period_state,
    policy_override,
    reconciliation,
    source_invoice,
    subledger_line,
    subledger_posting_seal,
    sync_run,
)
from erev_api.domain.close import quarantines, run_inputs
from erev_api.domain.contracts import period_ends
from erev_api.domain.journals import completeness as completeness_rules
from erev_api.domain.platform import jobs as platform_jobs
from erev_api.domain.reference import period_redirty_job
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ChecklistGateKind,
    ChecklistStatus,
    CloseRunStatus,
    ContractEventType,
    DerivedBlockerCode,
    ExceptionSeverity,
    ExceptionSource,
    ExceptionStatus,
    ImportStatus,
    JobState,
    JournalState,
    JudgementStatus,
    ManualAdjustmentStatus,
    ReconciliationKind,
    ReconciliationStatus,
    SyncRunStatus,
)
from erev_api.problems import Problem
from erev_api.registry.resolve import resolve

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "close_checklist_item"
CREATE_ACTION: Final = "close_checklist_item.create"
EVALUATE_ACTION: Final = "close_checklist_item.evaluate"
REQUIRE_RECONCILIATIONS: Final = "close.require_reconciliations_for_lock"  # T-PLT-31

# 04 T-CLS-02 ``gate_check_code`` in system sequence (REQ-CLS-008, -009).
INTERFACES_COMPLETE: Final = "INTERFACES_COMPLETE"
JE_BALANCED: Final = "JE_BALANCED"
JE_COMPLETE: Final = "JE_COMPLETE"
APPROVALS_CLEARED: Final = "APPROVALS_CLEARED"
EXCEPTIONS_CLEARED: Final = "EXCEPTIONS_CLEARED"
HOLDS_REVIEWED: Final = "HOLDS_REVIEWED"
BATCHES_ACKNOWLEDGED: Final = "BATCHES_ACKNOWLEDGED"
RECONCILIATIONS_GENERATED: Final = "RECONCILIATIONS_GENERATED"
JUDGEMENTS_REVIEWED: Final = "JUDGEMENTS_REVIEWED"
DATA_QUALITY_CLEAR: Final = "DATA_QUALITY_CLEAR"
NO_DIRTY_GROUPS: Final = "NO_DIRTY_GROUPS"
MANUAL_ADJUSTMENTS_CLEARED: Final = "MANUAL_ADJUSTMENTS_CLEARED"
CLOSE_RUN_COMPLETED: Final = "CLOSE_RUN_COMPLETED"
CONTROLLER_CERTIFIED: Final = "CONTROLLER_CERTIFIED"
GATE_CHECK_CODES: Final = (
    INTERFACES_COMPLETE,
    JE_BALANCED,
    JE_COMPLETE,
    APPROVALS_CLEARED,
    EXCEPTIONS_CLEARED,
    HOLDS_REVIEWED,
    BATCHES_ACKNOWLEDGED,
    RECONCILIATIONS_GENERATED,
    JUDGEMENTS_REVIEWED,
    DATA_QUALITY_CLEAR,
    NO_DIRTY_GROUPS,
    MANUAL_ADJUSTMENTS_CLEARED,
    CLOSE_RUN_COMPLETED,
    CONTROLLER_CERTIFIED,
)

# SCREENS_B §1.1 gate label table: failure details (row caption and ERR-14 gate list item).
NOT_EVALUATED: Final = "not evaluated"  # XR-12: the producer is not built yet
IMPORT_CONNECTION: Final = "File imports"
# CLO-GATE-SYNC-1 (supervisor ruling R-45 (d)): the T-INT-02 runs that hold the interface gate.
FAILED_SYNC_STATUSES: Final = (
    SyncRunStatus.FAILED.value,
    SyncRunStatus.CONTROL_TOTAL_MISMATCH.value,
)
PROBE_KIND: Final = "TEST_CONNECTION"  # a probe moves no batch and records no control totals
# R-56 (a), "a later run over the same window" per run kind; every other kind (WEBHOOK_BATCH,
# JOURNAL_EXPORT, TRIAL_BALANCE_PULL) has no window in sync_run and clears through its items only.
CHECKPOINT_KINDS: Final = ("INBOUND_POLL",)  # the later run started from the same checkpoint
WHOLE_SET_KINDS: Final = ("RECONCILIATION_SWEEP", "COA_SYNC")  # each run reads the whole set
INTERFACE_DETAIL: Final = "Interface batch not complete: {connection} ({n} runs)"
UNBALANCED_DETAIL: Final = "Journal batch does not balance: {currency}"
RUN_NOT_CALCULATED: Final = "Journal run not calculated"
APPROVALS_DETAIL: Final = "Pending approvals: {n}"
EXCEPTIONS_DETAIL: Final = "Open exceptions: {n}"
HOLDS_DETAIL: Final = "Open holds: {n}"
UNACKNOWLEDGED_DETAIL: Final = "Unacknowledged batches: {n}"
NOT_GENERATED_DETAIL: Final = "Reconciliation not generated: {kind}"
NOT_REVIEWED_DETAIL: Final = "Reconciliation not reviewed: {kind}"
# Supervisor ruling R-58 (e); SCREENS_B §1.1 gate label table (rev 1.27).
OUT_OF_DATE_DETAIL: Final = "Reconciliation out of date, generate it again: {kind}"
JUDGEMENTS_DETAIL: Final = "Judgements not reviewed: {n}"
DIRTY_DETAIL: Final = "Contracts changed since the last close run: {n}"
# Supervisor ruling R-106 (a); SCREENS_B §1.1 gate label table (rev 1.38): the period was opened
# by a lock decision and its PERIOD_OPEN_REDIRTY job has not succeeded.
REMARK_PENDING_DETAIL: Final = "Contracts not re-marked since the period was opened"
ADJUSTMENTS_DETAIL: Final = "Manual adjustments pending: {n}"
# Item CLO-GATE-RUN-1 (supervisor rulings R-114 (b), R-116 (e)); SCREENS_B §1.1 gate label table
# (rev 1.50): no close run of the period; its latest run in another status than SUCCEEDED, named
# as §0.4 labels E-62; a succeeded run the contracts have overtaken.
CLOSE_RUN_MISSING_DETAIL: Final = "Close run not completed"
CLOSE_RUN_STATUS_DETAIL: Final = "Close run {no} is {status}"
CLOSE_RUN_STALE_DETAIL: Final = "Close run out of date, run it again: {n} contracts"
# 04 §16.8 rev 1.291 (item CLO-RATE-AFTER-RUN-1): what the run read is no longer what is in force.
# ``{what}`` is "exchange rates", "policies" or "exchange rates and policies"
# (``run_inputs.RATES``, ``run_inputs.POLICIES``). The second sentence is the price of a read
# that is the tenant's and not the entity's.
CLOSE_RUN_INPUTS_DETAIL: Final = (
    "Close run out of date, run it again: {what} changed since it ran. "
    "A run posts nothing where the change moves nothing for this entity."
)
CLOSE_RUN_STATUS_LABELS: Final[Mapping[str, str]] = {
    CloseRunStatus.PENDING.value: "Queued",
    CloseRunStatus.RUNNING.value: "Running",
    CloseRunStatus.BLOCKED.value: "Blocked",
    CloseRunStatus.SUCCEEDED.value: "Succeeded",
    CloseRunStatus.FAILED.value: "Failed",
    CloseRunStatus.CANCELLED.value: "Cancelled",
}
CERTIFICATION_DETAIL: Final = "Awaiting Controller certification at lock"
DATA_QUALITY_DETAIL: Final = "Data-quality errors: {n}"  # SCREENS_B §1.1 :368 (CLO-5)
# E-58 labels (SCREENS_B §1.1).
RECONCILIATION_LABELS: Final[Mapping[str, str]] = {
    ReconciliationKind.BILLING_TO_SUBLEDGER.value: "Billing to subledger",
    ReconciliationKind.SUBLEDGER_TO_GL.value: "Subledger to GL",
    ReconciliationKind.CONTRACT_BALANCE_ROLLFORWARD.value: "Contract balance rollforward",
    ReconciliationKind.RPO_ROLLFORWARD.value: "RPO rollforward",
    ReconciliationKind.MIGRATION_OPENING_BALANCE.value: "Migration opening balances",
}
REQUIRED_KINDS: Final = (
    ReconciliationKind.BILLING_TO_SUBLEDGER.value,
    ReconciliationKind.SUBLEDGER_TO_GL.value,
)
REVIEWED_RECONCILIATIONS: Final = frozenset(
    {
        ReconciliationStatus.REVIEWED.value,
        ReconciliationStatus.AUTO_CERTIFIED.value,
        ReconciliationStatus.CERTIFIED.value,
    }
)
# R-58 (e): the reviewed statuses a later posting overtakes; a CERTIFIED row is its lock's.
OVERTAKEN_STATUSES: Final = (
    ReconciliationStatus.REVIEWED.value,
    ReconciliationStatus.AUTO_CERTIFIED.value,
)
# 04 E-03: the billing events a billing-to-subledger reconciliation compares, and the events of a
# contract's stream that decide which of their lines are kept (the voids).
BILLING_EVENT_TYPES: Final = (
    ContractEventType.BILLING_RECORDED.value,
    ContractEventType.CREDIT_MEMO_RECORDED.value,
)
VOID_EVENT_TYPES: Final = (
    ContractEventType.EVENT_VOIDED.value,
    ContractEventType.CONTRACT_VOIDED.value,
)
BILLING_STREAM_TYPES: Final = (*BILLING_EVENT_TYPES, *VOID_EVENT_TYPES)
OPEN_EXCEPTIONS: Final = (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
BLOCKING_SEVERITIES: Final = (ExceptionSeverity.BLOCKING.value, ExceptionSeverity.WARNING.value)
PRODUCT_UNMAPPED: Final = "PRODUCT_UNMAPPED"
CONTROL_TOTALS_MISMATCH: Final = "CONTROL_TOTALS_MISMATCH"
IMPORT_PROCESSING_FAILED: Final = "IMPORT_PROCESSING_FAILED"
# E-60: an item in these statuses is not evaluated again.
FINAL_STATUSES: Final = frozenset(
    {ChecklistStatus.WAIVED.value, ChecklistStatus.NOT_APPLICABLE.value}
)
# Item CLO-WAIVER-COVERS-LATER-1 (04 T-CLS-03 rev 1.305; PRD BR-CLS-01 rev 1.202): a waiver covers
# the count it was approved for. A gate that counts more fails again and says so after its own
# sentence; the stored result keeps the waiver's request number and count under ``OUTGROWN``.
WAIVER_COVERED: Final = "The waiver {request_no} covered {count}."
OUTGROWN: Final = "waiver_outgrown"
WAIVER_REQUEST_NO: Final = "waiver_request_no"
# the number of the request an item's waiver names, read with the item (one key lookup)
_WAIVER_REQUEST_NO: Final = (
    select(approval_request.c.request_no)
    .where(
        approval_request.c.tenant_id == close_checklist_item.c.tenant_id,
        approval_request.c.id == close_checklist_item.c.waiver_approval_request_id,
    )
    .scalar_subquery()
    .label(WAIVER_REQUEST_NO)
)
# SC-N4 (supervisor rulings R-54 (h), R-55; D-88 L7-2-Q-16; 04 §16.8 rev 1.106): the statuses that
# clear a gating checklist item, and the gates no waiver clears — the ledger's identities against
# its journals, which a journal run can always restore, the close run that posts the period end
# (rev 1.172; R-114 (b)), which can always be run again, and the certification itself.
CLEARED_STATUSES: Final = frozenset(
    {ChecklistStatus.PASSED, ChecklistStatus.WAIVED, ChecklistStatus.NOT_APPLICABLE}
)
NEVER_WAIVABLE: Final = frozenset(
    {JE_BALANCED, JE_COMPLETE, CLOSE_RUN_COMPLETED, CONTROLLER_CERTIFIED}
)
TASK_NOT_SIGNED: Final = "Close task not signed: {name}"  # R-55 (a): the ERR-14 entry of a task
# E-04 states whose checklist is evaluated; a future period has no checklist, and a closed one
# keeps the results certified at lock (CLO-6).
EVALUATED_STATES: Final = frozenset({"open", "closing", "reopened"})
WEEKDAYS: Final = 5


@dataclass(frozen=True, slots=True)
class PeriodScope:
    """One period state with its entity and period (API-S-Period identity)."""

    state_id: UUID
    entity_id: UUID
    entity_code: str
    functional_currency: str
    book_code: str
    period_id: UUID
    period_key: str
    period_name: str
    start_date: date
    end_date: date
    state: str
    current_lock_id: UUID | None
    row_version: int


@dataclass(frozen=True, slots=True)
class GateResult:
    """The evaluation of one gate check code (T-CLS-03 ``result``)."""

    gate_check_code: str
    status: ChecklistStatus
    count: int | None
    detail: str | None
    evaluated_at: datetime
    # R-55 (b): a gate whose checklist item an approved EXCEPTION_WAIVER waived is ``WAIVED`` here,
    # with the request and the item's stored count when the waiver was approved; ``count`` and
    # ``detail`` stay what the gate computes now.
    waiver_approval_request_id: UUID | None = None
    waived_count: int | None = None
    # CLO-GATE-RUN-1 (R-116 (e)): the result is the one the source lock certified, laid over the
    # sandbox's own evaluation by the replay of that lock (``platform.sandbox_periods``).
    replayed: bool = False
    # CLO-WAIVER-COVERS-LATER-1 (04 T-CLS-03 rev 1.305): the waiver this failing gate outgrew —
    # the number of its request and the count it was approved for (``outgrown``).
    waiver_outgrown: Mapping[str, Any] | None = None

    members: tuple[str, ...] | None = None

    def result(self) -> dict[str, Any]:
        """Stored count, detail, evaluation time and optional member identities; for a gate that
        failed over a waiver it outgrew, ``waiver_outgrown`` (``{request_no, count}``; item
        CLO-WAIVER-COVERS-LATER-1), so that every later evaluation states the same sentence."""
        stored: dict[str, Any] = {
            "count": self.count,
            "detail": self.detail,
            "evaluated_at": self.evaluated_at.isoformat(),
        }
        if self.members is not None:
            stored["members"] = list(self.members)
        if self.waiver_outgrown is not None:
            stored[OUTGROWN] = dict(self.waiver_outgrown)
        return stored


@dataclass(frozen=True, slots=True)
class BlockingTask:
    """A tenant close task that holds the lock (R-55 (a); PRD BR-CLS-01 "custom close tasks
    signed"): the item of an active ``MANUAL`` template with ``is_blocking = true`` that is not
    ``PASSED``, ``WAIVED`` or ``NOT_APPLICABLE``. ``code`` is the template code (T-CLS-02, unique
    per tenant) — the ``rule_id`` of the task's ``close-gates-failed`` entry."""

    code: str
    name: str
    status: ChecklistStatus

    @property
    def message(self) -> str:
        return TASK_NOT_SIGNED.format(name=self.name)


class GateResults(tuple[GateResult, ...]):
    """The evaluated system gates of a period, in T-CLS-02 order, with the tenant close tasks that
    hold its lock beside them (``blocking_tasks``). ``evaluate_gates`` returns it, so every lock
    decision that receives the gate results receives the tasks with them (``certification``)."""

    blocking_tasks: tuple[BlockingTask, ...]

    def __new__(
        cls, results: Iterable[GateResult], blocking_tasks: Iterable[BlockingTask] = ()
    ) -> GateResults:
        made = super().__new__(cls, results)
        made.blocking_tasks = tuple(blocking_tasks)
        return made


@dataclass(frozen=True, slots=True)
class CloseRunFacts:
    """The latest close run of an entity, book and period (item CLO-GATE-RUN-1): its number, its
    E-62 status and, when it ``SUCCEEDED``, the computed contract groups that hold a period end
    of the period or an earlier one still to post (``out_of_date``; ``close_run_facts``) and
    what of the reference data its passes read has changed since (``inputs_changed``; item
    CLO-RATE-AFTER-RUN-1) — empty for a run that recorded nothing of it."""

    number: str
    status: str
    out_of_date: int = 0
    inputs_changed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CloseSignals:
    """What the fourteen gates read for one entity, book and period."""

    blockers: Mapping[str, int]
    derived: Mapping[str, int]
    unbalanced_currencies: tuple[str, ...]
    unacknowledged_batches: int
    missing_kinds: tuple[str, ...]
    unreviewed_kinds: tuple[str, ...]
    data_quality_blocking: int = 0  # CLO-5: open BLOCKING DATA_QUALITY items of the period
    # CLO-10: the JE_COMPLETE signal of the period's non-cancelled runs; None without a run.
    completeness: completeness_rules.CompletenessResult | None = None
    # R-58 (e): required kinds whose reviewed reconciliation the period has overtaken.
    outdated_kinds: tuple[str, ...] = ()
    # CLO-GATE-SYNC-1: the connections named in the INTERFACES_COMPLETE failure detail — those
    # with an uncleared sync run, then "File imports" when a failed import counts as well.
    failing_interfaces: tuple[str, ...] = ()
    # R-106 (a): a lock decision opened the period and its re-marking job has not succeeded.
    remark_pending: bool = False
    # CLO-GATE-RUN-1: the latest close run of the period; None without one.
    close_run: CloseRunFacts | None = None
    members: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


SCOPE_COLUMNS: Final = (
    period_state.c.id,
    period_state.c.entity_id,
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.functional_currency,
    period_state.c.book_code,
    period_state.c.period_id,
    period.c.period_key,
    period.c.name.label("period_name"),
    period.c.start_date,
    period.c.end_date,
    period_state.c.state,
    period_state.c.current_lock_id,
    period_state.c.row_version,
)


def scope_select() -> Select[Any]:
    """Period states joined to their entity and period."""
    joined = period_state.join(
        period,
        and_(
            period.c.tenant_id == period_state.c.tenant_id, period.c.id == period_state.c.period_id
        ),
    ).join(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == period_state.c.tenant_id,
            legal_entity.c.id == period_state.c.entity_id,
        ),
    )
    return select(*SCOPE_COLUMNS).select_from(joined)


def scope_of(row: Mapping[Any, Any]) -> PeriodScope:
    return PeriodScope(
        state_id=UUID(str(row["id"])),
        entity_id=UUID(str(row["entity_id"])),
        entity_code=str(row["entity_code"]),
        functional_currency=str(row["functional_currency"]),
        book_code=_text(row["book_code"]),
        period_id=UUID(str(row["period_id"])),
        period_key=str(row["period_key"]),
        period_name=str(row["period_name"]),
        start_date=row["start_date"],
        end_date=row["end_date"],
        state=str(row["state"]),
        current_lock_id=None
        if row["current_lock_id"] is None
        else UUID(str(row["current_lock_id"])),
        row_version=int(row["row_version"]),
    )


def period_scope(
    session: Session, state_id: UUID, *, lock: bool = False, share: bool = False
) -> PeriodScope | None:
    """The scope of a visible period state, or None; ``lock`` locks the state row ``FOR UPDATE``,
    ``share`` pins it ``FOR SHARE`` to the end of the transaction (item CLO-GATE-RUN-2: whoever
    stores gate results holds the row and has read the state under it)."""
    statement = scope_select().where(period_state.c.id == state_id)
    if lock:
        statement = statement.with_for_update(of=period_state)
    elif share:
        statement = statement.with_for_update(read=True, of=period_state)
    row = session.execute(statement).mappings().first()
    return None if row is None else scope_of(row)


def scope_of_period(
    session: Session, entity_id: UUID, book_code: str, period_id: UUID, *, share: bool = False
) -> PeriodScope | None:
    """The scope of the period state of an entity, book and period, or None; ``share`` pins the
    state row ``FOR SHARE`` to the end of the transaction."""
    statement = scope_select().where(
        period_state.c.entity_id == entity_id,
        period_state.c.book_code == book_code,
        period_state.c.period_id == period_id,
    )
    if share:
        statement = statement.with_for_update(read=True, of=period_state)
    row = session.execute(statement).mappings().first()
    return None if row is None else scope_of(row)


# --- blocker counts ------------------------------------------------------------------------------


def _count(table: Any, *conditions: ColumnElement[bool]) -> Any:
    return select(func.count()).select_from(table).where(*conditions).scalar_subquery()


def _population(table: Any, *conditions: ColumnElement[bool]) -> Select[Any]:
    return select(table.c.id).select_from(table).where(*conditions)


def _population_members(session: Session, scope: PeriodScope) -> dict[str, tuple[str, ...]]:
    populations = _blocker_populations(scope)
    populations["data_quality_blocking"] = _population(exception_item, *_quality_conditions(scope))
    row = (
        session.execute(
            select(
                *(
                    query.with_only_columns(func.array_agg(query.selected_columns[0]))
                    .scalar_subquery()
                    .label(key)
                    for key, query in populations.items()
                )
            )
        )
        .mappings()
        .one()
    )
    # Typed identifiers distinguish two different source populations with the same UUID.
    return {
        key: tuple(sorted(f"{key}:{identifier}" for identifier in (row[key] or ())))
        for key in populations
    }


def _entity_contracts(entity_id: UUID) -> Select[Any]:
    return select(contract.c.id).where(contract.c.contracting_entity_id == entity_id)


def _entity_groups(entity_id: UUID) -> Select[Any]:
    return select(contract.c.combination_group_id).where(
        contract.c.contracting_entity_id == entity_id,
        contract.c.combination_group_id.is_not(None),
    )


def _upload_names(entity_id: UUID) -> ColumnElement[bool]:
    """An upload whose findings and whose failure hold the close of ``entity_id`` (T-IMP-02
    ``named_entity_ids``): its rows name the entity, or it names no entity (tenant-level data),
    or it is not resolved — the last two hold every entity, as the ``INTERFACE_COMPLETENESS``
    count reads an upload (supervisor ruling R-103 (a))."""
    names = import_upload.c.named_entity_ids
    return or_(names.is_(None), func.cardinality(names) == 0, names.contains([entity_id]))


def _of_no_named_entity(entity_id: UUID) -> ColumnElement[bool]:
    """Whose an item is that names no entity, contract or group (04 T-IMP-05 "An item that names
    no entity", rev 1.206; the supervisor's rulings of 2026-10-01 on item CLO-QUARANTINE-READ-1,
    R-121 (i)). The item of an import is of the entities its upload names (``_upload_names``); the
    item of a sync run is of the entities its connection serves (T-INT-01 ``entity_ids``, empty =
    every entity), as the run itself holds the interface gate (``uncleared_sync_runs``); an item
    of neither is of every entity, as before (XR-12). Until these rulings the finding of an
    import or of a connection of one entity held the close of every other entity too."""
    item = exception_item.c
    run = sync_run.alias("item_run")
    connection = integration_connection.alias("item_connection")
    of_upload = exists().where(
        import_upload.c.tenant_id == item.tenant_id,
        import_upload.c.id == item.import_upload_id,
        _upload_names(entity_id),
    )
    of_connection = exists().where(
        run.c.tenant_id == item.tenant_id,
        run.c.id == item.sync_run_id,
        connection.c.tenant_id == run.c.tenant_id,
        connection.c.id == run.c.integration_connection_id,
        or_(
            func.cardinality(connection.c.entity_ids) == 0,
            connection.c.entity_ids.contains([entity_id]),
        ),
    )
    return and_(
        or_(item.import_upload_id.is_(None), of_upload),
        or_(item.sync_run_id.is_(None), of_connection),
    )


def item_of_entity(entity_id: UUID) -> ColumnElement[bool]:
    """Whose an exception item is — ONE attribution for the close gates, the count of the cockpit,
    ``GET /exceptions`` ``entity`` and ``blocking``, and the home page's figure (04 T-IMP-05 "An
    item that names no entity", §16.14, rev 1.206; supervisor ruling R-121 (i); [J] D-88
    L7-2-Q-1): the item names the entity; or names no entity and a contract of the entity; or
    names no entity or contract and a contract group that holds a contract of the entity; or names
    none of the three and is of the entity by its import or its connection, or of every entity
    (``_of_no_named_entity``). No status, severity or period condition: those are the gate's."""
    item = exception_item.c
    no_entity = item.entity_id.is_(None)
    no_contract = item.contract_id.is_(None)
    return or_(
        item.entity_id == entity_id,
        and_(no_entity, item.contract_id.in_(_entity_contracts(entity_id))),
        and_(no_entity, no_contract, item.combination_group_id.in_(_entity_groups(entity_id))),
        and_(
            no_entity,
            no_contract,
            item.combination_group_id.is_(None),
            _of_no_named_entity(entity_id),
        ),
    )


def _failed_before_commit() -> ColumnElement[bool]:
    """The ``IMPORT_PROCESSING_FAILED`` item of an import that failed before its commit (04
    T-IMP-05 "An item that names no entity: whose close it holds" and §16.14, rev 1.270; 05 §5.6
    rev 1.185; the supervisor's ruling of 2026-10-02). The validation or the dry run of the upload
    failed — by the handler's own ending or by the job's failure hook — so the upload ended
    ``INVALID``: nothing was written and nothing is owed to any period. The item stays in the
    queue for the upload's readers, who open and dismiss it, and holds no lock. The item of a
    failed commit does — its upload is ``FAILED`` — and so does the finding of a plan a dry run
    refused, whose upload goes on."""
    item = exception_item.c
    upload = import_upload.alias("failed_import")
    return and_(
        item.code == IMPORT_PROCESSING_FAILED,
        exists().where(
            upload.c.tenant_id == item.tenant_id,
            upload.c.id == item.import_upload_id,
            upload.c.status == ImportStatus.INVALID.value,
        ),
    )


def _open_exceptions(scope: PeriodScope) -> ColumnElement[bool]:
    """Open blocking or warning items of the entity and period, cases (a) to (c) of the module
    docstring ([J] D-88 L7-2-Q-1). A data-quality finding counts only when it is BLOCKING (04
    Table 15.4-E rev 1.106: "`ERROR` results block lock"; supervisor ruling R-57): a WARNING
    finding of the monitors stays in the queue with its notification and holds no lock. Nor
    does the processing failure of an import that never reached its commit
    (``_failed_before_commit``)."""
    item = exception_item.c
    return and_(
        item.status.in_(OPEN_EXCEPTIONS),
        item.severity.in_(BLOCKING_SEVERITIES),
        or_(
            item.source != ExceptionSource.DATA_QUALITY.value,
            item.severity == ExceptionSeverity.BLOCKING.value,
        ),
        item.code != CONTROL_TOTALS_MISMATCH,
        not_(_failed_before_commit()),
        or_(item.period_id.is_(None), item.period_id == scope.period_id),
        item_of_entity(scope.entity_id),
    )


def blocking_exceptions(scope: PeriodScope) -> ColumnElement[bool]:
    """The exception items ``blockers.exceptions_open`` and the gate ``EXCEPTIONS_CLEARED`` count
    for ``scope``, as a condition on ``exception_item``: the predicate of the count itself, for the
    list that names those items (04 API-R-44 ``blocking``, §16.14 rev 1.206; item
    CLO-QUARANTINE-READ-1). One definition, so the count and the list behind it cannot part."""
    return _open_exceptions(scope)


def request_of_entity(entity_id: UUID) -> ColumnElement[bool]:
    """An approval request of the entity: it names the entity — alone (``entity_id``) or among
    several (``entity_ids``; 04 T-PLT-17 rev 1.104) — or names none and its subject belongs to the
    entity (L7-2-Q-2; BLK-01 and the home ``pending_approvals``, RPS-17)."""
    return or_(
        approval_request.c.entity_id == entity_id,
        literal(entity_id, Uuid()) == any_(approval_request.c.entity_ids),
        and_(approval_request.c.entity_id.is_(None), _subject_of_entity(entity_id)),
    )


def _subject_of_entity(entity_id: UUID) -> ColumnElement[bool]:
    """A pending request without an entity whose subject belongs to the entity (L7-2-Q-2)."""
    contracts = _entity_contracts(entity_id)
    subject = approval_request.c.subject_id
    return or_(
        subject.in_(contracts),
        exists().where(
            event_submission.c.id == subject, event_submission.c.contract_id.in_(contracts)
        ),
        exists().where(obligation.c.id == subject, obligation.c.contract_id.in_(contracts)),
        exists().where(
            policy_override.c.id == subject, policy_override.c.contract_id.in_(contracts)
        ),
        exists().where(
            estimate_version.c.id == subject,
            estimate_version.c.estimate_id == estimate.c.id,
            estimate.c.contract_id.in_(contracts),
        ),
        exists().where(
            judgement_record.c.id == subject, judgement_record.c.contract_id.in_(contracts)
        ),
        exists().where(journal_run.c.id == subject, journal_run.c.entity_id == entity_id),
        exists().where(
            manual_adjustment.c.id == subject, manual_adjustment.c.entity_id == entity_id
        ),
        exists().where(
            close_checklist_item.c.id == subject,
            close_checklist_item.c.entity_id == entity_id,
        ),
        # the waiver of an exception item is a pending approval of the entities the item is —
        # the one attribution (R-121 (i); item EXC-IMPORT-SCOPE-1): before, only an item that
        # named the entity or a contract of it, so the pending waiver of a group's, an import's
        # or a workspace-level item held nobody's APPROVALS_CLEARED
        exists().where(exception_item.c.id == subject, item_of_entity(entity_id)),
    )


def own_lock_request(scope: PeriodScope) -> ColumnElement[bool]:
    """The request that asks for the lock of the period itself: ``PERIOD_LOCK`` on the period's
    state — the lock request of a period in soft close and the permanent-lock request of a closed
    one, which are one subject type on one subject (``approvals.subjects.LOCK_FROM_STATE``).

    It is no pending approval of its own period (04 §16.8 ``blockers`` rev 1.311; PRD BR-CLS-01
    rev 1.205; item CLO-LOCK-REQUEST-OWN-GATE-1): ``blocker_statement`` leaves it out of
    ``approvals_pending``. By the type AND the subject: a ``PERIOD_LOCK`` request of another
    period state of the entity is a pending approval of this period as before, and so is a
    ``PERIOD_REOPEN`` request of any period state, this one's included (04 §14.1)."""
    return and_(
        approval_request.c.subject_type == ApprovalSubjectType.PERIOD_LOCK.value,
        approval_request.c.subject_id == scope.state_id,
    )


def own_gate_waiver_request(scope: PeriodScope) -> ColumnElement[bool]:
    """The request that asks to waive the period's own ``APPROVALS_CLEARED`` gate:
    ``EXCEPTION_WAIVER`` on that checklist item (``commands.waive_checklist_item``).

    It is no pending approval of its own period (04 §16.8 ``blockers`` rev 1.318; PRD BR-CLS-01
    rev 1.206; item CLO-APPROVALS-WAIVER-OWN-REQUEST-1): the request that asks to waive the
    count is no part of the count, so ``blocker_statement`` leaves it out of
    ``approvals_pending``. The count a waiver of this gate states and covers (04 T-CLS-03 rev
    1.305) is then the other requests alone, before and after it is asked; counted, the request
    raised the count it stated, and its approval answered 409 ``stale-approval``. By the type,
    the subject AND the item's gate: the waiver request of another gate's item of the period,
    and of another period's ``APPROVALS_CLEARED`` item, is a pending approval of this period as
    before."""
    own_item = (
        select(close_checklist_item.c.id)
        .join(
            close_checklist_template,
            and_(
                close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            ),
        )
        .where(
            _of_period(close_checklist_item, scope),
            close_checklist_template.c.gate_check_code == APPROVALS_CLEARED,
        )
    )
    return and_(
        approval_request.c.subject_type == ApprovalSubjectType.EXCEPTION_WAIVER.value,
        approval_request.c.subject_id.in_(own_item),
    )


# D-90a QA-L9-7 (L8-C-Q-2): the request types SCREENS_B §1.1 BLK-06 and BLK-15 subtract, in the
# fixed order of 04 API-S-PeriodCockpit ``pending_requests`` (rev 1.8).
BLOCKER_REQUEST_TYPES: Final = (
    ApprovalSubjectType.JUDGEMENT_RECORD,
    ApprovalSubjectType.MANUAL_ADJUSTMENT,
)


def pending_request_counts(session: Session, scope: PeriodScope) -> dict[str, int]:
    """The ``PENDING`` requests of the entity per ``BLOCKER_REQUEST_TYPES`` type, both keys
    always present in that order (04 API-S-PeriodCockpit ``pending_requests``; D-90a QA-L9-7).

    The population is the one ``blockers.approvals_pending`` counts (``request_of_entity``; the
    requests it leaves out, ``own_lock_request`` and ``own_gate_waiver_request``, are of neither
    type):
    entity-only, not filtered by book, counts only, and independent of API-R-09 request
    visibility, so every reader of the period reads the same counts."""
    counts = {subject_type.value: 0 for subject_type in BLOCKER_REQUEST_TYPES}
    rows = session.execute(
        select(approval_request.c.subject_type, func.count())
        .where(
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
            approval_request.c.subject_type.in_(list(counts)),
            request_of_entity(scope.entity_id),
        )
        .group_by(approval_request.c.subject_type)
    ).all()
    for subject_type, count in rows:
        counts[str(subject_type)] = int(count)
    return counts


def _of_period(table: Any, scope: PeriodScope) -> ColumnElement[bool]:
    return and_(
        table.c.entity_id == scope.entity_id,
        table.c.book_code == scope.book_code,
        table.c.period_id == scope.period_id,
    )


def _live_runs(scope: PeriodScope) -> Select[Any]:
    return select(journal_run.c.id).where(
        _of_period(journal_run, scope), journal_run.c.state != JournalState.CANCELLED.value
    )


def uncleared_sync_runs(scope: PeriodScope) -> ColumnElement[bool]:
    """The sync runs (T-INT-02) that hold the interface gate of the scope's entity (CTL-002;
    BR-INT-03; supervisor rulings R-45 (d) and R-56 (a), item CLO-GATE-SYNC-1): a run of a
    connection whose ``entity_ids`` is empty (all entities) or names the entity, that ended
    ``FAILED`` or ``CONTROL_TOTAL_MISMATCH``, until it is cleared. A run is cleared when

    - a later run of the same connection and kind ``SUCCEEDED`` over the same window:
      an ``INBOUND_POLL`` that started from the same ``checkpoint_before`` (the failed run did not
      move the replay position, so the later one read the same changes); a
      ``RECONCILIATION_SWEEP`` or a ``COA_SYNC`` that ran to completion (each reads the whole
      set). A ``WEBHOOK_BATCH``, a ``JOURNAL_EXPORT`` and a ``TRIAL_BALANCE_PULL`` have no window
      of their own in ``sync_run`` and are never cleared this way; or
    - it has failure items in the exception queue (``exception_item.sync_run_id``) and none of them
      is still ``OPEN`` or ``IN_PROGRESS`` (resolved, waived or dismissed: PRD BR-CLS-01). A run
      without any item is not cleared by this limb.

    A run carries the documents of any period, so the run's own date does not limit the periods it
    holds (fail closed). A ``TEST_CONNECTION`` probe is no interface batch (REQ-DAT-010: a batch
    records control totals) and is not counted. A run neither limb can clear — a poll that failed
    on objects recorded in ``problem.failures`` only while its checkpoint advanced — holds the gate
    until the gate itself is waived (item SYNC-RUN-CLEAR-1)."""
    later = sync_run.alias("later_run")
    same_window = or_(
        and_(
            sync_run.c.kind.in_(CHECKPOINT_KINDS),
            later.c.checkpoint_before == sync_run.c.checkpoint_before,
        ),
        sync_run.c.kind.in_(WHOLE_SET_KINDS),
    )
    recovered = exists().where(
        later.c.tenant_id == sync_run.c.tenant_id,
        later.c.integration_connection_id == sync_run.c.integration_connection_id,
        later.c.kind == sync_run.c.kind,
        later.c.status == SyncRunStatus.SUCCEEDED.value,
        tuple_(later.c.created_at, later.c.id) > tuple_(sync_run.c.created_at, sync_run.c.id),
        same_window,
    )
    item = exception_item.alias("run_item")
    of_run = and_(item.c.tenant_id == sync_run.c.tenant_id, item.c.sync_run_id == sync_run.c.id)
    settled = and_(
        exists().where(of_run), ~exists().where(of_run, item.c.status.in_(OPEN_EXCEPTIONS))
    )
    connection = integration_connection.alias("run_connection")
    of_entity = exists().where(
        connection.c.tenant_id == sync_run.c.tenant_id,
        connection.c.id == sync_run.c.integration_connection_id,
        or_(
            func.cardinality(connection.c.entity_ids) == 0,
            connection.c.entity_ids.contains([scope.entity_id]),
        ),
    )
    return and_(
        sync_run.c.status.in_(FAILED_SYNC_STATUSES),
        sync_run.c.kind != PROBE_KIND,
        of_entity,
        ~recovered,
        ~settled,
    )


def failing_connections(session: Session, scope: PeriodScope) -> tuple[str, ...]:
    """The names of the connections with a sync run that holds the interface gate, in name order
    (the ``<connection name>`` of the SCREENS_B §1.1 failure detail)."""
    names = session.execute(
        select(integration_connection.c.name)
        .where(
            exists().where(
                sync_run.c.tenant_id == integration_connection.c.tenant_id,
                sync_run.c.integration_connection_id == integration_connection.c.id,
                uncleared_sync_runs(scope),
            )
        )
        .order_by(integration_connection.c.name, integration_connection.c.id)
    ).scalars()
    return tuple(str(name) for name in names)


def _blocker_populations(scope: PeriodScope) -> dict[str, Select[Any]]:
    """Shared populations for cockpit counts and identity-bound gate waivers."""
    runs = select(journal_run.c.id).where(_of_period(journal_run, scope))
    close_jobs = or_(
        and_(job.c.subject_type == "journal_run", job.c.subject_id.in_(runs)),
        and_(job.c.subject_type == "close_run", job.c.subject_id.in_(_close_runs(scope))),
        # R-106 (a), R-110 (c): the re-marking job of a period a lock opened; its subject is the
        # period state (04 T-PLT-27 rev 1.164)
        period_redirty_job.of_state(scope.state_id),
    )
    # BLK-08 counts the newest job of a subject: a run resumed to success shows no failed job
    # (supervisor ruling R-103 (a), item CLO-BLK08-NEWEST-1), nor does a period state whose
    # re-marking the scheduler's tick has deferred again (R-106 (a)).
    newest_job = platform_jobs.newest_of_subject()
    mismatch_open = exists().where(
        exception_item.c.import_upload_id == import_upload.c.id,
        exception_item.c.code == CONTROL_TOTALS_MISMATCH,
        exception_item.c.status.in_(OPEN_EXCEPTIONS),
    )
    # R-121 (i): a failed import holds the interface gate of the entities its upload names
    # (every entity while it names none or is not resolved), as its findings hold the
    # exceptions gate; before, it held the gate of every entity.
    imports_failed = _population(
        import_upload,
        import_upload.c.status == ImportStatus.FAILED.value,
        mismatch_open,
        _upload_names(scope.entity_id),
    )
    dirty_group = and_(
        combination_group.c.dirty_since.is_not(None),
        exists().where(
            contract.c.combination_group_id == combination_group.c.id,
            contract.c.contracting_entity_id == scope.entity_id,
        ),
    )
    return {
        "exceptions_open": _population(exception_item, _open_exceptions(scope)),
        "holds_open": _population(
            contract_hold,
            contract_hold.c.released_at.is_(None),
            contract_hold.c.contract_id.in_(_entity_contracts(scope.entity_id)),
        ),
        "unmapped_products": _population(
            exception_item, _open_exceptions(scope), exception_item.c.code == PRODUCT_UNMAPPED
        ),
        "judgements_unreviewed": _population(
            judgement_record,
            judgement_record.c.status == JudgementStatus.SUBMITTED.value,
            judgement_record.c.contract_id.in_(_entity_contracts(scope.entity_id)),
            or_(
                judgement_record.c.book_code.is_(None),
                judgement_record.c.book_code == scope.book_code,
            ),
        ),
        "approvals_pending": _population(
            approval_request,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
            request_of_entity(scope.entity_id),
            # rev 1.311: the period's own lock request is no pending approval of its period
            ~own_lock_request(scope),
            # rev 1.318: nor is the request that asks to waive this very count
            ~own_gate_waiver_request(scope),
        ),
        "sync_failed": _population(sync_run, uncleared_sync_runs(scope)),
        "imports_failed": imports_failed,
        "jobs_failed": _population(
            job, job.c.state == JobState.FAILED.value, close_jobs, newest_job
        ),
        "groups_dirty": _population(combination_group, dirty_group),
        "batches_unexported": _population(
            journal_batch,
            _of_period(journal_batch, scope),
            journal_batch.c.state == JournalState.APPROVED.value,
        ),
        "batches_unacknowledged": _population(
            journal_batch,
            _of_period(journal_batch, scope),
            journal_batch.c.state.in_((JournalState.EXPORTED.value, JournalState.FAILED.value)),
        ),
        "reconciliations_unsigned": _population(
            reconciliation,
            _of_period(reconciliation, scope),
            or_(
                reconciliation.c.status.not_in(sorted(REVIEWED_RECONCILIATIONS)),
                overtaken(scope),
            ),
            ~superseded(),
        ),
        "manual_adjustments_pending": _population(
            manual_adjustment,
            _of_period(manual_adjustment, scope),
            manual_adjustment.c.status.in_(
                (ManualAdjustmentStatus.DRAFT.value, ManualAdjustmentStatus.SUBMITTED.value)
            ),
            # CLO-12 (REQ-JE-019): an adjustment deferred past lock with approval does not count.
            manual_adjustment.c.is_deferred_past_lock.is_(False),
        ),
        "runs_live": _population(journal_run, journal_run.c.id.in_(_live_runs(scope))),
        "batches_not_acknowledged": _population(
            journal_batch,
            journal_batch.c.journal_run_id.in_(_live_runs(scope)),
            journal_batch.c.state.not_in(
                (JournalState.ACKNOWLEDGED.value, JournalState.CANCELLED.value)
            ),
        ),
    }


def blocker_statement(scope: PeriodScope) -> Select[Any]:
    """One row of cockpit and gate-only counts, using the same predicates as members."""
    counts: dict[str, ColumnElement[Any]] = {
        key: query.with_only_columns(func.count()).scalar_subquery()
        for key, query in _blocker_populations(scope).items()
    }
    counts["interface_failures"] = counts["imports_failed"] + counts.pop("sync_failed")
    return select(*(value.label(key) for key, value in counts.items()))


def _close_runs(scope: PeriodScope) -> Select[Any]:
    return select(close_run.c.id).where(_of_period(close_run, scope))


BLOCKER_KEYS: Final = (
    "exceptions_open",
    "holds_open",
    "unmapped_products",
    "judgements_unreviewed",
    "approvals_pending",
    "interface_failures",
    "jobs_failed",
    "groups_dirty",
    "batches_unexported",
    "batches_unacknowledged",
    "reconciliations_unsigned",
    "manual_adjustments_pending",
)


def _counts_row(session: Session, scope: PeriodScope) -> Mapping[Any, Any]:
    return session.execute(blocker_statement(scope)).mappings().one()


def blocker_counts(session: Session, scope: PeriodScope) -> dict[str, int]:
    """API-S-Period ``blockers`` of one period state (04 §16.8; REQ-CLS-008)."""
    row = _counts_row(session, scope)
    return {key: int(row[key]) for key in BLOCKER_KEYS}


def required_kinds(session: Session, scope: PeriodScope, *, known_at: datetime) -> tuple[str, ...]:
    """``BILLING_TO_SUBLEDGER`` and ``SUBLEDGER_TO_GL`` when
    ``close.require_reconciliations_for_lock = true`` (T-PLT-31), otherwise none."""
    resolved = resolve(
        session,
        REQUIRE_RECONCILIATIONS,
        book_code=BookCode(scope.book_code),
        entity_id=scope.entity_id,
        known_at=known_at,
    )
    return REQUIRED_KINDS if resolved.value is True else ()


def reconciliations_reviewed(
    session: Session, scope: PeriodScope, *, known_at: datetime
) -> dict[str, int]:
    """API-S-PeriodCockpit ``kpis.reconciliations_reviewed``: the required kinds with a reviewed,
    auto-certified or certified reconciliation of the period, over the required kinds."""
    kinds = required_kinds(session, scope, known_at=known_at)
    generated = _reconciliation_statuses(session, scope)
    outdated = _overtaken_kinds(session, scope)
    reviewed = sum(
        1
        for kind in kinds
        if generated.get(kind, set()) & REVIEWED_RECONCILIATIONS and kind not in outdated
    )
    return {"reviewed": reviewed, "required": len(kinds)}


def superseded(target: Any = reconciliation) -> ColumnElement[bool]:
    """A later reconciliation of the same kind, entity, book and period exists. Every generation
    inserts a new row and the latest generated — the greatest ``as_of_known_at``, then id — is the
    current reconciliation: the gate, the unsigned count, the cockpit and the lock's certification
    read current rows only (04 T-CLS-06 rev 1.121; supervisor ruling R-54 (b), extending D-98 79).
    """
    later = reconciliation.alias("later_reconciliation")
    return (
        exists()
        .where(
            later.c.tenant_id == target.c.tenant_id,
            later.c.entity_id == target.c.entity_id,
            later.c.book_code == target.c.book_code,
            later.c.period_id == target.c.period_id,
            later.c.kind == target.c.kind,
            or_(
                later.c.as_of_known_at > target.c.as_of_known_at,
                and_(
                    later.c.as_of_known_at == target.c.as_of_known_at,
                    later.c.id > target.c.id,
                ),
            ),
        )
        .correlate(target)
    )


def later_than(row: Mapping[str, Any]) -> ColumnElement[bool]:
    """The reconciliations generated after ``row`` (the order of ``superseded``)."""
    return or_(
        reconciliation.c.as_of_known_at > row["as_of_known_at"],
        and_(
            reconciliation.c.as_of_known_at == row["as_of_known_at"],
            reconciliation.c.id > row["id"],
        ),
    )


# --- what a reconciliation read (item REC-GEN-LOCK-1) --------------------------------------------
# The populations a generation reads beside the ledger, as conditions: the generation reads its
# rows under them and stores how many there were (04 T-CLS-06 ``source_documents_read``,
# ``subledger_documents_read``), and ``overtaken`` counts under the same conditions — so a count
# the gate takes is a count of exactly what a generation would read now. Each population is
# append-only (T-SRC-04 and T-CON-05 are IM-A): a count that differs is a row the reconciliation
# did not read.


def source_invoices_of(scope: PeriodScope) -> tuple[ColumnElement[bool], ...]:
    """The billing system's documents of the entity issued in the period — every stored version
    (the billing-to-subledger reconciliation compares the newest of each)."""
    return (
        source_invoice.c.legal_entity_code == scope.entity_code,
        source_invoice.c.issue_date >= scope.start_date,
        source_invoice.c.issue_date <= scope.end_date,
    )


def billed_contracts_of(scope: PeriodScope) -> Select[tuple[UUID]]:
    """The contracts of the entity that hold a billing event dated in the period."""
    return (
        select(contract_event.c.contract_id)
        .where(
            contract_event.c.contracting_entity_id == scope.entity_id,
            contract_event.c.event_type.in_(BILLING_EVENT_TYPES),
            contract_event.c.effective_date >= scope.start_date,
            contract_event.c.effective_date <= scope.end_date,
        )
        .distinct()
    )


def billing_streams_of(scope: PeriodScope) -> tuple[ColumnElement[bool], ...]:
    """The stream events a billing-to-subledger reconciliation depends on, of the contracts that
    hold a billing event dated in the period: their billing events dated on or before the
    period's last day, and their voids of any date.

    The identity of a billed line is fixed over the contract's stream in the order of effective
    date (ENGINE_SPEC_B S10-R-07: the first-seen event of an identity is the line, a repeat is a
    status update), so a billing event dated AFTER the period cannot change which events of the
    period are lines — it is not read, and a later month's invoice does not put this period's
    reconciliation out of date. An event dated earlier and recorded late can, and so can a void
    whenever it is dated: both are read."""
    return (
        contract_event.c.contract_id.in_(billed_contracts_of(scope)),
        or_(
            and_(
                contract_event.c.event_type.in_(BILLING_EVENT_TYPES),
                contract_event.c.effective_date <= scope.end_date,
            ),
            contract_event.c.event_type.in_(VOID_EVENT_TYPES),
        ),
    )


def events_through(scope: PeriodScope) -> tuple[ColumnElement[bool], ...]:
    """The contract events of the entity's contracts dated on or before the period's last day, of
    any type: what the stored closing contract balances of the period depend on beside the
    ledger (04 T-CLS-06 "Role basis"). An event dated in a later period is not among them, so a
    later period's bookings do not put this period's reconciliation out of date; an event of the
    period recorded late does."""
    return (
        contract_event.c.contracting_entity_id == scope.entity_id,
        contract_event.c.effective_date <= scope.end_date,
    )


def _number_of(table: Any, conditions: tuple[ColumnElement[bool], ...]) -> Any:
    """How many rows of ``table`` meet ``conditions`` now, as a scalar subquery."""
    return select(func.count()).select_from(table).where(*conditions).scalar_subquery()


def _inclusions(scope: PeriodScope, as_of: datetime | None = None) -> Any:
    """How many times a contract version of the run's book includes an event of
    ``events_through`` (04 T-CON-08 ``cause_event_ids``), as a scalar subquery — with ``as_of``,
    of the versions known at or before it.

    A version names the events it was the first to include: those beyond the stream heads of
    the group's last ``SUCCEEDED`` computation (``contracts.computation._cause_event_ids``). So
    an event is included when it is first COMPUTED into the book — once per group that computes
    it: again by the first version of a group its contract moves into. Versions are append-only
    (IM-A): the number never falls."""
    included = (
        func.unnest(contract_version.c.cause_event_ids)
        .table_valued(column("event_id", Uuid()))
        .render_derived(name="included")
    )
    return (
        select(func.count())
        .select_from(
            contract_version.join(included, true()).join(
                contract_event,
                and_(
                    contract_event.c.tenant_id == contract_version.c.tenant_id,
                    contract_event.c.id == included.c.event_id,
                ),
            )
        )
        .where(
            contract_version.c.book_code == scope.book_code,
            *events_through(scope),
            *(() if as_of is None else (contract_version.c.known_at <= as_of,)),
        )
        .scalar_subquery()
    )


def ledger_documents(scope: PeriodScope, as_of: datetime | None = None) -> Any:
    """What a subledger-to-GL reconciliation depends on beside the ledger, as ONE number (04
    T-CLS-06 ``subledger_documents_read``; item REC-GEN-LOCK-1, the supervisor's ruling of
    2026-10-02 01:41): the contract events of the entity's contracts dated on or before the
    period's last day (``events_through``) PLUS the inclusions of those events in a contract
    version of the book (``_inclusions``).

    On the role basis the subledger side of the three contract balance roles is the stored
    closing balance of the contract versions known at the reconciliation's ``as_of_known_at``,
    and a version is "known" at the record time of its newest event — not when it was computed.
    The first term moves when such an event is RECORDED; the second when it is first COMPUTED
    into the book. Without the second, an event recorded before a generation and computed after
    the review moved the stored balance behind a reconciliation that had counted it (measured:
    V5). Neither term moves for a later period's event, nor for a computation that includes no
    new event — a close-run pass, a replay.

    Both populations are append-only, so the sum differs exactly when one of them grew.
    ``overtaken`` counts every row there is now. A GENERATION counts the rows it will be able to
    read (``as_of``, its ``as_of_known_at``): the events recorded, and the inclusions in
    versions known, at or before it. The attach reads the contract versions known at or before
    that instant, so a row beyond it is one the reconciliation does not hold — even when it was
    committed while the generation ran, after the generation's instant was fixed and before its
    count. Left unbounded, the generation would count such a row as read and the gate would find
    nothing new (measured: V6)."""
    events = (
        events_through(scope)
        if as_of is None
        else (*events_through(scope), contract_event.c.recorded_at <= as_of)
    )
    return _number_of(contract_event, events) + _inclusions(scope, as_of)


def overtaken(scope: PeriodScope) -> ColumnElement[bool]:
    """A reviewed or auto-certified reconciliation of ``scope`` that the period has overtaken
    (supervisor ruling R-58 (e); item REC-GEN-LOCK-1, the supervisor's rulings of 2026-10-01
    21:41 and 22:52 and of 2026-10-02 00:09 and 01:41; 04 T-CLS-06 rev 1.259). Such a row does
    not count as reviewed; generating the reconciliation again gives the current one.

    A reconciliation records what it READ, as a position and a count, not as a time. A line's
    ``recorded_at`` — like a source invoice's ``created_at`` and an event's ``recorded_at`` — is
    the START of its unit of work, so "recorded after" is not "committed after": a posting that
    began before a generation and committed after it is older than the reconciliation by every
    clock stored, and no time test sees it. What orders commits is the book's ledger chain: a
    seal takes the chain head's row lock and holds it to commit, so ``chain_seq`` is the commit
    order of the book's postings.

    - Any kind: a subledger line of the entity and book whose posting was sealed after
      the chain position the generation read (``ledger_chain_seq``). For subledger to GL,
      the population includes every period through the reconciled period end, matching
      the attach's ledger history; other kinds retain the reconciled period alone.
    - Billing to subledger: or the number of source invoices of the period, or of the billing
      events through the period's last day and the voids of the contracts billed in it, differs
      from what the generation read. Under ``billing.posting = ERP`` a billing event writes no
      subledger line, so the position alone does not see it.
    - Subledger to GL: or the number of contract events of the entity dated through the period's
      last day, plus their inclusions in a contract version of the book, differs
      (``ledger_documents``). On the role basis the subledger side of the three contract balance
      roles is the stored closing balance, which such an event moves without a line — when it
      is computed, which may be after the review of a reconciliation that already counted it.

    A row generated before revision 0121 holds neither position nor counts and keeps the test it
    was generated under: a line recorded after its ``as_of_known_at`` and, for billing to
    subledger, a source invoice created after it."""
    row = reconciliation.c
    of_period = (
        subledger_line.c.tenant_id == row.tenant_id,
        subledger_line.c.entity_id == scope.entity_id,
        subledger_line.c.book_code == scope.book_code,
        # The GL attach reads all history through period end (including account/role
        # discovery), while the billing comparison reads postings of this period only.
        or_(
            and_(
                row.kind == ReconciliationKind.SUBLEDGER_TO_GL.value,
                subledger_line.c.period_end_date <= scope.end_date,
            ),
            and_(
                row.kind != ReconciliationKind.SUBLEDGER_TO_GL.value,
                subledger_line.c.period_end_date == scope.end_date,
                subledger_line.c.period_id == scope.period_id,
            ),
        ),
    )
    later_seal = (
        exists()
        .where(
            *of_period,
            subledger_posting_seal.c.tenant_id == subledger_line.c.tenant_id,
            subledger_posting_seal.c.subledger_posting_id == subledger_line.c.subledger_posting_id,
            subledger_posting_seal.c.chain_seq > row.ledger_chain_seq,
        )
        .correlate(reconciliation)
    )
    line_recorded_later = (
        exists().where(*of_period, subledger_line.c.recorded_at > row.as_of_known_at)
    ).correlate(reconciliation)
    invoice_created_later = (
        exists()
        .where(
            source_invoice.c.tenant_id == row.tenant_id,
            *source_invoices_of(scope),
            source_invoice.c.created_at > row.as_of_known_at,
        )
        .correlate(reconciliation)
    )
    billing = row.kind == ReconciliationKind.BILLING_TO_SUBLEDGER.value
    ledger = row.kind == ReconciliationKind.SUBLEDGER_TO_GL.value
    later_line = or_(
        and_(row.ledger_chain_seq.is_not(None), later_seal),
        and_(row.ledger_chain_seq.is_(None), line_recorded_later),
    )
    source_moved = and_(
        billing,
        or_(
            and_(
                row.source_documents_read.is_not(None),
                row.source_documents_read != _number_of(source_invoice, source_invoices_of(scope)),
            ),
            and_(row.source_documents_read.is_(None), invoice_created_later),
        ),
    )
    subledger_moved = and_(
        row.subledger_documents_read.is_not(None),
        or_(
            and_(
                billing,
                row.subledger_documents_read
                != _number_of(contract_event, billing_streams_of(scope)),
            ),
            and_(ledger, row.subledger_documents_read != ledger_documents(scope)),
        ),
    )
    return and_(row.status.in_(OVERTAKEN_STATUSES), or_(later_line, source_moved, subledger_moved))


def _overtaken_kinds(session: Session, scope: PeriodScope) -> frozenset[str]:
    """The kinds whose current reconciliation of the period is ``overtaken``."""
    return frozenset(
        _text(kind)
        for kind in session.execute(
            select(reconciliation.c.kind).where(
                _of_period(reconciliation, scope), ~superseded(), overtaken(scope)
            )
        ).scalars()
    )


def _reconciliation_statuses(session: Session, scope: PeriodScope) -> dict[str, set[str]]:
    """The status of the current reconciliation of each kind of the period (``superseded``)."""
    rows = session.execute(
        select(reconciliation.c.kind, reconciliation.c.status).where(
            _of_period(reconciliation, scope), ~superseded()
        )
    ).tuples()
    found: dict[str, set[str]] = {}
    for kind, status in rows:
        found.setdefault(_text(kind), set()).add(_text(status))
    return found


def _reconciliation_members(
    identifiers: Mapping[str, UUID],
    missing: tuple[str, ...],
    unreviewed: tuple[str, ...],
    outdated: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            [f"reconciliation:{kind}:missing" for kind in missing]
            + [f"reconciliation:{kind}:{identifiers.get(kind)}:unreviewed" for kind in unreviewed]
            + [f"reconciliation:{kind}:{identifiers.get(kind)}:outdated" for kind in outdated]
        )
    )


def derived_counts(
    session: Session,
    scope: PeriodScope,
    *,
    known_at: datetime,
    runs_live: int | None = None,
) -> dict[str, int]:
    """E-122 derived blockers, both codes present (04 API-S-PeriodCockpit ``derived_blockers``)."""
    if runs_live is None:
        runs_live = int(
            session.execute(
                select(func.count()).select_from(_live_runs(scope).subquery())
            ).scalar_one()
        )
    generated = _reconciliation_statuses(session, scope)
    missing = [
        kind for kind in required_kinds(session, scope, known_at=known_at) if kind not in generated
    ]
    return {
        DerivedBlockerCode.JOURNAL_RUN_NOT_CALCULATED.value: 0 if runs_live else 1,
        DerivedBlockerCode.RECONCILIATIONS_NOT_GENERATED.value: len(missing),
    }


def _quality_conditions(scope: PeriodScope) -> tuple[ColumnElement[bool], ...]:
    return (
        exception_item.c.source == ExceptionSource.DATA_QUALITY.value,
        exception_item.c.severity == ExceptionSeverity.BLOCKING.value,
        exception_item.c.status.in_(OPEN_EXCEPTIONS),
        exception_item.c.entity_id == scope.entity_id,
        exception_item.c.period_id == scope.period_id,
    )


def data_quality_blocking(session: Session, scope: PeriodScope) -> int:
    """Open blocking data-quality findings of this entity and period."""
    return int(
        session.execute(select(_count(exception_item, *_quality_conditions(scope)))).scalar_one()
    )


def close_run_facts(
    session: Session, scope: PeriodScope, *, known_at: datetime
) -> CloseRunFacts | None:
    """The latest close run of the period — the newest by ``created_at``, then id, the order
    ``close_runs.lock_marked`` reads — with the groups that hold the gate when it ``SUCCEEDED``
    (module docstring, "What ``CLOSE_RUN_COMPLETED`` counts"): a computed group that holds a
    contract and whose ``period_ends_open`` entry of the entity and book lies on or before the
    period's last day, or is absent for a group of the entity — less the dirty groups whose
    quarantine stands waived. And, for a run that recorded what it read (module docstring, "What
    a run read"), what of it differs from the same read at ``known_at``. None when the period
    has no run."""
    row = session.execute(
        select(
            close_run.c.close_run_no,
            close_run.c.status,
            close_run.c.rates_read,
            close_run.c.registry_read,
        )
        .where(_of_period(close_run, scope))
        .order_by(close_run.c.created_at.desc(), close_run.c.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    number, status = str(row[0]), _text(row[1])
    if status != CloseRunStatus.SUCCEEDED.value:
        return CloseRunFacts(number, status)
    entry = combination_group.c.period_ends_open[
        period_ends.scope_key(scope.entity_code, scope.book_code)
    ].astext
    member = and_(
        contract.c.tenant_id == combination_group.c.tenant_id,
        contract.c.combination_group_id == combination_group.c.id,
    )
    held = session.execute(
        select(combination_group.c.id, combination_group.c.dirty_since).where(
            combination_group.c.head_computation_id.is_not(None),
            exists().where(member),
            or_(
                cast(entry, Date) <= scope.end_date,
                and_(
                    entry.is_(None),
                    exists().where(member, contract.c.contracting_entity_id == scope.entity_id),
                ),
            ),
        )
    ).all()
    dirty = [UUID(str(group_id)) for group_id, dirty_since in held if dirty_since is not None]
    waived = quarantines.standing_waived(session, dirty)
    changed: tuple[str, ...] = ()
    if row[2] is not None and row[3] is not None:
        recorded = run_inputs.RunInputs(rates=str(row[2]), registry=str(row[3]))
        changed = run_inputs.changed(recorded, run_inputs.standing(session, scope, known_at))
    return CloseRunFacts(number, status, len(held) - len(waived), changed)


def signals(
    session: Session,
    scope: PeriodScope,
    *,
    known_at: datetime,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> CloseSignals:
    """Everything the gates read, in a few statements. ``files`` / ``keyring`` let the completeness
    assertion read a run's held detail file when its audit event predates
    ``held_subledger_line_ids`` (CLO-10; Codex 1317 R5-ORDER-1)."""
    members = _population_members(session, scope)
    row = {key: len(values) for key, values in members.items()}
    row["interface_failures"] = row["imports_failed"] + row["sync_failed"]
    runs_live = int(row["runs_live"])
    imports_failed = int(row["imports_failed"])
    interfaces = (
        failing_connections(session, scope)
        if int(row["interface_failures"]) > imports_failed
        else ()
    )
    if imports_failed:
        interfaces = (*interfaces, IMPORT_CONNECTION)
    unbalanced = session.execute(
        select(journal_batch.c.txn_currency)
        .where(
            journal_batch.c.journal_run_id.in_(_live_runs(scope)),
            or_(
                journal_batch.c.total_debit_txn != journal_batch.c.total_credit_txn,
                journal_batch.c.total_debit_functional != journal_batch.c.total_credit_functional,
            ),
        )
        .distinct()
        .order_by(journal_batch.c.txn_currency)
    ).scalars()
    kinds = required_kinds(session, scope, known_at=known_at)
    reconciliation_rows = session.execute(
        select(
            reconciliation.c.kind,
            reconciliation.c.status,
            reconciliation.c.id,
            overtaken(scope).label("overtaken"),
        ).where(_of_period(reconciliation, scope), ~superseded())
    ).all()
    generated = {_text(found.kind): {_text(found.status)} for found in reconciliation_rows}
    identifiers = {_text(found.kind): UUID(str(found.id)) for found in reconciliation_rows}
    missing = tuple(kind for kind in kinds if kind not in generated)
    unreviewed = tuple(
        kind
        for kind in kinds
        if kind in generated and not generated[kind] & REVIEWED_RECONCILIATIONS
    )
    overtaken_kinds = {_text(found.kind) for found in reconciliation_rows if found.overtaken}
    outdated = tuple(kind for kind in kinds if kind in overtaken_kinds)
    return CloseSignals(
        blockers={key: int(row[key]) for key in BLOCKER_KEYS},
        derived={
            DerivedBlockerCode.JOURNAL_RUN_NOT_CALCULATED.value: 0 if runs_live else 1,
            DerivedBlockerCode.RECONCILIATIONS_NOT_GENERATED.value: len(missing),
        },
        unbalanced_currencies=tuple(str(value) for value in unbalanced),
        unacknowledged_batches=int(row["batches_not_acknowledged"]),
        missing_kinds=missing,
        unreviewed_kinds=unreviewed,
        outdated_kinds=outdated,
        remark_pending=period_redirty_job.remark_pending(session, scope.state_id),
        close_run=close_run_facts(session, scope, known_at=known_at),
        data_quality_blocking=row["data_quality_blocking"],
        members={
            INTERFACES_COMPLETE: tuple(sorted(members["imports_failed"] + members["sync_failed"])),
            APPROVALS_CLEARED: members["approvals_pending"],
            EXCEPTIONS_CLEARED: members["exceptions_open"],
            HOLDS_REVIEWED: members["holds_open"],
            BATCHES_ACKNOWLEDGED: members["batches_not_acknowledged"]
            + (() if runs_live else ("journal_run:missing",)),
            RECONCILIATIONS_GENERATED: _reconciliation_members(
                identifiers, missing, unreviewed, outdated
            ),
            JUDGEMENTS_REVIEWED: members["judgements_unreviewed"],
            DATA_QUALITY_CLEAR: members["data_quality_blocking"],
            NO_DIRTY_GROUPS: members["groups_dirty"],
            MANUAL_ADJUSTMENTS_CLEARED: members["manual_adjustments_pending"],
        },
        failing_interfaces=interfaces,
        completeness=(
            completeness_rules.completeness_of(
                session,
                entity_id=scope.entity_id,
                book_code=scope.book_code,
                period_id=scope.period_id,
                files=files,
                keyring=keyring,
            )
            if runs_live
            else None
        ),
    )


# --- gate results --------------------------------------------------------------------------------


def _counted(code: str, count: int, detail: str, at: datetime) -> GateResult:
    if count == 0:
        return GateResult(code, ChecklistStatus.PASSED, 0, None, at)
    return GateResult(code, ChecklistStatus.FAILED, count, detail.format(n=count), at)


def _dirty_groups(facts: CloseSignals, *, at: datetime) -> GateResult:
    """``NO_DIRTY_GROUPS``: the count of dirty groups — unless a lock decision opened the period
    and its re-marking job has not succeeded (supervisor ruling R-106 (a)). Until then nothing has
    marked the groups with an effect in the period, so the count proves nothing: the gate fails by
    name with no count, and is not waivable for that reason (``commands.waive_checklist_item``)."""
    if facts.remark_pending:
        return GateResult(NO_DIRTY_GROUPS, ChecklistStatus.FAILED, None, REMARK_PENDING_DETAIL, at)
    return _counted(NO_DIRTY_GROUPS, facts.blockers["groups_dirty"], DIRTY_DETAIL, at)


def data_quality_gate(open_blocking: int, *, at: datetime) -> GateResult:
    """The ``DATA_QUALITY_CLEAR`` gate from the count of open ``BLOCKING`` ``DATA_QUALITY`` items of
    the period: ``PASSED`` (count 0) or ``FAILED`` with the count (CLO-5; SCREENS_B :368)."""
    if open_blocking < 0:
        raise ValueError("a count of open items is not negative")
    return _counted(DATA_QUALITY_CLEAR, open_blocking, DATA_QUALITY_DETAIL, at)


def _completeness_result(facts: CloseSignals, *, run_missing: bool, at: datetime) -> GateResult:
    """CLO-10 (REQ-JE-005): ``JE_COMPLETE`` from the period's completeness assertion — FAILED
    "Journal run not calculated" without a run (as JE_BALANCED), the assertion's count and named
    detail with one; ``NOT_EVALUATED`` only when the signal was not collected at all."""
    if run_missing:
        return GateResult(JE_COMPLETE, ChecklistStatus.FAILED, 1, RUN_NOT_CALCULATED, at)
    outcome = facts.completeness
    if outcome is None:
        return GateResult(JE_COMPLETE, ChecklistStatus.FAILED, None, NOT_EVALUATED, at)
    return GateResult(JE_COMPLETE, outcome.status, outcome.count, outcome.detail, at)


def _close_run_result(facts: CloseSignals, *, at: datetime) -> GateResult:
    """``CLOSE_RUN_COMPLETED`` (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and R-116 (e)):
    ``PASSED`` when the period's latest close run ``SUCCEEDED``, no contract group overtook it
    and what it read is still what is in force; otherwise ``FAILED`` by name — no run (count 1),
    the latest run in another status (count 1, the run's number and the E-62 label of its
    status), the count of the groups that hold a period end still to post ("out of date"), or,
    with no such group, what of the rates and the policies the run read has changed since
    (count 1; item CLO-RATE-AFTER-RUN-1)."""
    run = facts.close_run
    if run is None:
        return GateResult(
            CLOSE_RUN_COMPLETED, ChecklistStatus.FAILED, 1, CLOSE_RUN_MISSING_DETAIL, at
        )
    if run.status != CloseRunStatus.SUCCEEDED.value:
        detail = CLOSE_RUN_STATUS_DETAIL.format(
            no=run.number, status=CLOSE_RUN_STATUS_LABELS[run.status]
        )
        return GateResult(CLOSE_RUN_COMPLETED, ChecklistStatus.FAILED, 1, detail, at)
    if run.out_of_date == 0 and run.inputs_changed:
        detail = CLOSE_RUN_INPUTS_DETAIL.format(what=" and ".join(run.inputs_changed))
        return GateResult(CLOSE_RUN_COMPLETED, ChecklistStatus.FAILED, 1, detail, at)
    return _counted(CLOSE_RUN_COMPLETED, run.out_of_date, CLOSE_RUN_STALE_DETAIL, at)


def gate_results(facts: CloseSignals, *, at: datetime) -> tuple[GateResult, ...]:
    """One result per gate check code in T-CLS-02 order (BR-CLS-01; SCREENS_B §1.1)."""
    blockers = facts.blockers
    run_missing = facts.derived[DerivedBlockerCode.JOURNAL_RUN_NOT_CALCULATED.value]
    interfaces = blockers["interface_failures"]
    # SCREENS_B §1.1: "Interface batch not complete: <connection name> (<n> runs)" — the failing
    # connections by name, and the total of their runs.
    named = ", ".join(facts.failing_interfaces) or IMPORT_CONNECTION
    interface = _counted(
        INTERFACES_COMPLETE,
        interfaces,
        INTERFACE_DETAIL.format(connection=named, n="{n}"),
        at,
    )
    if run_missing:
        balanced = GateResult(JE_BALANCED, ChecklistStatus.FAILED, 1, RUN_NOT_CALCULATED, at)
        acknowledged = GateResult(
            BATCHES_ACKNOWLEDGED,
            ChecklistStatus.FAILED,
            facts.unacknowledged_batches + 1,
            RUN_NOT_CALCULATED,
            at,
        )
    else:
        unbalanced = facts.unbalanced_currencies
        balanced = (
            GateResult(
                JE_BALANCED,
                ChecklistStatus.FAILED,
                len(unbalanced),
                "; ".join(UNBALANCED_DETAIL.format(currency=currency) for currency in unbalanced),
                at,
            )
            if unbalanced
            else GateResult(JE_BALANCED, ChecklistStatus.PASSED, 0, None, at)
        )
        acknowledged = _counted(
            BATCHES_ACKNOWLEDGED, facts.unacknowledged_batches, UNACKNOWLEDGED_DETAIL, at
        )
    problems = [
        NOT_GENERATED_DETAIL.format(kind=RECONCILIATION_LABELS[kind])
        for kind in facts.missing_kinds
    ] + [
        NOT_REVIEWED_DETAIL.format(kind=RECONCILIATION_LABELS[kind])
        for kind in facts.unreviewed_kinds
    ]
    problems += [
        OUT_OF_DATE_DETAIL.format(kind=RECONCILIATION_LABELS[kind]) for kind in facts.outdated_kinds
    ]
    reconciliations = (
        GateResult(
            RECONCILIATIONS_GENERATED,
            ChecklistStatus.FAILED,
            len(problems),
            "; ".join(problems),
            at,
        )
        if problems
        else GateResult(RECONCILIATIONS_GENERATED, ChecklistStatus.PASSED, 0, None, at)
    )
    results = (
        interface,
        balanced,
        _completeness_result(facts, run_missing=bool(run_missing), at=at),
        _counted(APPROVALS_CLEARED, blockers["approvals_pending"], APPROVALS_DETAIL, at),
        _counted(EXCEPTIONS_CLEARED, blockers["exceptions_open"], EXCEPTIONS_DETAIL, at),
        _counted(HOLDS_REVIEWED, blockers["holds_open"], HOLDS_DETAIL, at),
        acknowledged,
        reconciliations,
        _counted(JUDGEMENTS_REVIEWED, blockers["judgements_unreviewed"], JUDGEMENTS_DETAIL, at),
        data_quality_gate(facts.data_quality_blocking, at=at),
        _dirty_groups(facts, at=at),
        _counted(
            MANUAL_ADJUSTMENTS_CLEARED,
            blockers["manual_adjustments_pending"],
            ADJUSTMENTS_DETAIL,
            at,
        ),
        _close_run_result(facts, at=at),
        GateResult(CONTROLLER_CERTIFIED, ChecklistStatus.FAILED, None, CERTIFICATION_DETAIL, at),
    )
    return tuple(
        replace(result, members=facts.members.get(result.gate_check_code)) for result in results
    )


# --- checklist items -----------------------------------------------------------------------------


def business_days_after(end: date, days: int) -> date:
    """T-CLS-02 ``due_offset_days``: the date ``days`` business days (Monday to Friday) after
    ``end`` (L7-2-Q-6: no holiday calendar exists)."""
    current = end
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.isoweekday() <= WEEKDAYS:
            remaining -= 1
    return current


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def ensure_items(uow: UnitOfWork, scope: PeriodScope, *, audited: bool = True) -> list[UUID]:
    """Create the missing item of every active template for the period; the ids created. A command
    audits each creation; the materialisation for a reader (``materialise_for_view``) passes
    ``audited=False`` — a read never appends an audit event (04 T-CLS-03 rev 1.106)."""
    templates = uow.session.execute(
        select(close_checklist_template.c.id, close_checklist_template.c.due_offset_days)
        .where(close_checklist_template.c.is_active.is_(True))
        .order_by(close_checklist_template.c.sequence, close_checklist_template.c.id)
    ).tuples()
    principal = uow.principal
    created: list[UUID] = []
    for template_id, offset in templates:
        due = None if offset is None else business_days_after(scope.end_date, int(offset))
        statement = (
            pg_insert(close_checklist_item)
            .values(
                tenant_id=principal.tenant_id,
                id=new_id(),
                close_checklist_template_id=template_id,
                entity_id=scope.entity_id,
                book_code=scope.book_code,
                period_id=scope.period_id,
                status=ChecklistStatus.NOT_STARTED.value,
                due_date=due,
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
                **_stamps(uow),
            )
            .on_conflict_do_nothing(
                index_elements=[
                    "tenant_id",
                    "close_checklist_template_id",
                    "entity_id",
                    "book_code",
                    "period_id",
                ]
            )
            .returning(close_checklist_item.c.id)
        )
        found = uow.session.execute(statement).scalar_one_or_none()
        if found is None:
            continue
        item_id = UUID(str(found))
        created.append(item_id)
        if not audited:
            continue
        uow.audit(
            action=CREATE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=item_id,
            object_version="1",
            after={
                "status": ChecklistStatus.NOT_STARTED.value,
                "close_checklist_template_id": str(template_id),
                "entity_id": str(scope.entity_id),
                "book_code": scope.book_code,
                "period_id": str(scope.period_id),
                "due_date": None if due is None else due.isoformat(),
            },
        )
    return created


def store_results(uow: UnitOfWork, results: Sequence[GateResult], scope: PeriodScope) -> None:
    """Store gate results on the period's items (CLO-6: the certified results at lock)."""
    _store(uow, results, scope)


def _automatic_items(scope: PeriodScope, *, lock: bool) -> Select[Any]:
    """The period's items of automatic gates with their gate codes, in id order; ``lock`` locks the
    item rows."""
    statement = (
        select(
            close_checklist_item.c.id,
            close_checklist_item.c.status,
            close_checklist_item.c.result,
            close_checklist_item.c.row_version,
            close_checklist_item.c.waiver_approval_request_id,
            close_checklist_template.c.gate_check_code,
            _WAIVER_REQUEST_NO,
        )
        .join(
            close_checklist_template,
            and_(
                close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            ),
        )
        .where(
            _of_period(close_checklist_item, scope),
            close_checklist_template.c.gate_kind == ChecklistGateKind.AUTOMATIC.value,
        )
        .order_by(close_checklist_item.c.id)
    )
    return statement.with_for_update(of=close_checklist_item) if lock else statement


def outgrown(row: Mapping[Any, Any], result: GateResult) -> GateResult:
    """A waiver only covers its recorded member identities; a spent waiver never revives.

    Legacy count-only waivers fail closed when blockers remain. A shrinking covered set is
    permitted, but a new member lapses the waiver even when the count is unchanged.
    """
    stored = row["result"] or {}
    spent = stored.get(OUTGROWN)
    if _text(row["status"]) == ChecklistStatus.WAIVED.value:
        waived = stored.get("count")
        covered = stored.get("members")
        if result.status is ChecklistStatus.PASSED:
            return result
        if (
            covered is not None
            and result.members is not None
            and set(result.members).issubset(covered)
            and waived is not None
            and result.count is not None
            and result.count <= int(waived)
        ):
            return result
        spent = {"request_no": row[WAIVER_REQUEST_NO], "count": waived}
        if covered is None or result.members is None:
            spent["reason"] = "unbound"
        elif result.count is not None and waived is not None and result.count <= int(waived):
            spent["reason"] = "new_members"
    if spent is None or result.status is not ChecklistStatus.FAILED:
        return result
    sentence = waiver_lapse_detail(spent)
    detail = sentence if result.detail is None else f"{result.detail} {sentence}"
    return replace(result, status=ChecklistStatus.FAILED, detail=detail, waiver_outgrown=spent)


def waiver_lapse_detail(spent: Mapping[str, Any]) -> str:
    if spent.get("reason") == "unbound":
        return "This waiver has no recorded item identities. Request a new waiver."
    sentence = WAIVER_COVERED.format(request_no=spent["request_no"], count=spent["count"])
    if spent.get("reason") == "new_members":
        sentence += " New items require a new waiver."
    return sentence


def renewed_waiver_result(stored: Mapping[str, Any]) -> dict[str, Any]:
    """A fresh approval ends the prior lapse annotation, retaining its approved population."""
    result = dict(stored)
    result.pop(CHECKLIST_WAIVER_BASIS, None)
    spent = result.pop(OUTGROWN, None)
    if spent is not None and result.get("detail") is not None:
        sentence = waiver_lapse_detail(spent)
        detail = str(result["detail"])
        result["detail"] = None if detail == sentence else detail.removesuffix(f" {sentence}")
    return result


def _to_store(row: Mapping[Any, Any], by_code: Mapping[str, GateResult]) -> GateResult | None:
    """The result to store on an automatic item, or None when the item keeps what it holds: a
    final item (not applicable, whatever its stored result remembers; waived, while the gate
    contains only members the waiver covered — ``outgrown``), a gate without a result, or an
    unchanged status, count, detail and members (``evaluated_at`` alone is no change)."""
    computed = by_code.get(str(row["gate_check_code"]))
    status = _text(row["status"])
    if computed is None or status == ChecklistStatus.NOT_APPLICABLE.value:
        return None
    result = outgrown(row, computed)
    if status == ChecklistStatus.WAIVED.value and result.waiver_outgrown is None:
        return None
    stored = row["result"] or {}
    unchanged = (
        status == result.status.value
        and stored.get("count") == result.count
        and stored.get("detail") == result.detail
        and stored.get("members") == (None if result.members is None else list(result.members))
    )
    return None if unchanged else result


def _store(
    uow: UnitOfWork, results: Sequence[GateResult], scope: PeriodScope, *, audited: bool = True
) -> int:
    """Store each automatic gate's result on its item when the status, count or detail changed;
    the number of items written. ``audited=False`` writes the rows without an audit event (the
    materialisation for a reader, ``materialise_for_view``) — but for one move: an item that
    leaves ``WAIVED`` because its gate contains members the waiver did not cover. A waiver's
    lapse is a change of a control's state and is on the trail whoever stores it, a reader's
    materialisation included, as SYSTEM (item CLO-WAIVER-COVERS-LATER-1; the supervisor's ruling
    of 2026-10-02 20:22; 04 T-CLS-03 rev 1.305; dev guide DG-CMD-13). It is bounded: once per
    approved waiver — the item then names no request, and a second lapse needs a second
    approval. The event names the request that lapsed and is linked to it."""
    by_code = {result.gate_check_code: result for result in results}
    rows = uow.session.execute(_automatic_items(scope, lock=True)).mappings()
    written = 0
    for row in list(rows):
        result = _to_store(row, by_code)
        if result is None:
            continue
        status = _text(row["status"])
        stored = row["result"] or {}
        item_id = UUID(str(row["id"]))
        moved = status != result.status.value
        lapsed = moved and status == ChecklistStatus.WAIVED.value
        stored_result = result.result()
        if row["waiver_approval_request_id"] is not None and CHECKLIST_WAIVER_BASIS in stored:
            stored_result[CHECKLIST_WAIVER_BASIS] = stored[CHECKLIST_WAIVER_BASIS]
        values: dict[str, Any] = {"result": stored_result, **_stamps(uow)}
        if lapsed:
            # the waiver is spent: the item names no request until another is asked for; its
            # number and count stay in the stored result and in the sentence
            values["waiver_approval_request_id"] = None
        transitions.apply(
            uow.session,
            OBJECT_TYPE,
            item_id,
            to_status=result.status.value if moved else None,
            expected_status=status if moved else None,
            set_values=values,
        )
        written += 1
        if not audited and not lapsed:
            continue
        before = {"status": status, "count": stored.get("count"), "detail": stored.get("detail")}
        after: dict[str, Any] = {
            "status": result.status.value,
            "count": result.count,
            "detail": result.detail,
        }
        waiver = row["waiver_approval_request_id"] if lapsed else None
        if lapsed:
            before["members"] = stored.get("members")
            after["members"] = None if result.members is None else list(result.members)
            before["waiver_approval_request_id"] = None if waiver is None else str(waiver)
            after["waiver_approval_request_id"] = None
        uow.audit(
            action=EVALUATE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=item_id,
            object_version=str(int(row["row_version"]) + 1),
            before=before,
            after=after,
            approval_request_id=None if waiver is None else UUID(str(waiver)),
        )
    return written


def _view_is_stale(session: Session, scope: PeriodScope, results: Sequence[GateResult]) -> bool:
    """Whether the stored checklist differs from what a reader must see: an active template
    without its item for the period, or an automatic item whose stored status, count or detail is
    not the evaluated one. Plain reads: no row is locked and nothing is written."""
    missing = session.execute(
        select(func.count())
        .select_from(close_checklist_template)
        .where(
            close_checklist_template.c.is_active.is_(True),
            ~select(close_checklist_item.c.id)
            .where(
                close_checklist_item.c.tenant_id == close_checklist_template.c.tenant_id,
                close_checklist_item.c.close_checklist_template_id == close_checklist_template.c.id,
                _of_period(close_checklist_item, scope),
            )
            .exists(),
        )
    ).scalar_one()
    if int(missing):
        return True
    by_code = {result.gate_check_code: result for result in results}
    rows = session.execute(_automatic_items(scope, lock=False)).mappings()
    return any(_to_store(row, by_code) is not None for row in rows)


def materialise_for_view(uow: UnitOfWork, state_id: UUID) -> bool:
    """Bring the stored checklist of a period up to what its readers must see, for
    ``GET /periods/{id}/cockpit`` and ``GET /periods/{id}/checklist`` (security finding SC-8;
    supervisor ruling R-32; 04 T-CLS-03 rev 1.106): True when a row was written, so the caller
    commits only then.

    A read appends no audit event — but for one, the lapse of a waiver its gate has outgrown
    (``_store``; the supervisor's ruling of 2026-10-02 20:22) — and writes nothing when nothing
    changed. While the period
    is ``open``, ``closing`` or ``reopened`` the fourteen gates are evaluated; only when an active
    template has no item for the period, or an automatic item's stored status, count or detail is
    not the evaluated one, are the missing items created and the changed results stored — without
    audit events. The data-quality monitors do not run here: the scheduled sweep (05 SCH-10) and
    the period commands run them (``commands.run_period_monitors``). The commands that evaluate
    gates (sign, waive, request-lock, the lock decision) keep auditing what they create and
    change, and the results certified at lock are the ones the lock stores (CLO-6). 404
    ``not-found`` for an unknown period state.

    What a reader stores, it stores under the state row (item CLO-GATE-RUN-2; review finding F6):
    once something is to be stored the row is pinned ``FOR SHARE`` and the state read again — a
    lock decision in flight is waited for, and a period it closed keeps the checklist it
    certified. Before, a cockpit read that met the decision stored its evaluation from before
    the lock on the closed period, without an audit event. [J] A reader that still finds the
    period evaluated stores the evaluation it made before it waited; the next read corrects it."""
    scope = period_scope(uow.session, state_id)
    if scope is None:
        raise Problem("not-found")
    if scope.state not in EVALUATED_STATES:
        return False
    results = gate_results(
        signals(uow.session, scope, known_at=uow.now, files=uow.files, keyring=uow.keyring),
        at=uow.now,
    )
    if not _view_is_stale(uow.session, scope, results):
        return False
    pinned = period_scope(uow.session, state_id, share=True)
    if pinned is None or pinned.state not in EVALUATED_STATES:
        return False
    created = ensure_items(uow, scope, audited=False)
    written = _store(uow, results, scope, audited=False)
    return bool(created) or written > 0


def remark_pending(session: Session, scope: PeriodScope) -> bool:
    """True while a lock decision opened the period and its ``PERIOD_OPEN_REDIRTY`` job has not
    succeeded (supervisor ruling R-106 (a); ``reference.period_redirty_job``)."""
    return period_redirty_job.remark_pending(session, scope.state_id)


def waivable(gate_check_code: str | None, *, remark_pending: bool) -> bool:
    """Whether an approved waiver clears the item of ``gate_check_code`` (None: a tenant task).
    R-55 (c): journal balancing, journal completeness and the controller certification never;
    R-114 (b): nor the close run that posts the period end.
    R-106 (a), R-112 (j): nor ``NO_DIRTY_GROUPS`` while ``remark_pending`` — the gate then fails
    because nothing has marked the period's contracts yet, which no waiver can vouch for. Every
    other gate and task is waivable."""
    if gate_check_code in NEVER_WAIVABLE:
        return False
    return not (remark_pending and gate_check_code == NO_DIRTY_GROUPS)


def with_final_items(
    session: Session, scope: PeriodScope, results: Sequence[GateResult]
) -> tuple[GateResult, ...]:
    """The results with the FINAL state of their checklist items laid over them (R-55 (b)): a gate
    whose item an approved ``EXCEPTION_WAIVER`` waived is ``WAIVED`` with the request and the count
    the item held when the waiver was approved (a waived item is not stored over while its gate
    counts no more than that, so its stored result is that count); a ``NOT_APPLICABLE`` item
    gives ``NOT_APPLICABLE``. A gate that counts MORE than its waiver covered is laid ``FAILED``
    with its sentence, whether the evaluation has stored the move or not, and so is a failing
    item that remembers a spent waiver (``outgrown``; 04 T-CLS-03 rev 1.305). ``count``,
    ``detail`` and ``evaluated_at`` stay the gate's computed ones. A pending, rejected or voided
    waiver leaves the item's status alone and changes nothing here; a gate that is never waivable
    keeps its computed status whatever its item says — and so does ``NO_DIRTY_GROUPS`` while the
    period's re-marking has not succeeded (``waivable``; R-106 (a), R-112 (j))."""
    pending = remark_pending(session, scope)
    rows = session.execute(
        select(
            close_checklist_template.c.gate_check_code,
            close_checklist_item.c.status,
            close_checklist_item.c.result,
            close_checklist_item.c.waiver_approval_request_id,
            _WAIVER_REQUEST_NO,
        )
        .join(
            close_checklist_template,
            and_(
                close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            ),
        )
        .where(
            _of_period(close_checklist_item, scope),
            close_checklist_template.c.gate_kind == ChecklistGateKind.AUTOMATIC.value,
            or_(
                close_checklist_item.c.status.in_(sorted(FINAL_STATUSES)),
                close_checklist_item.c.result.has_key(OUTGROWN),
            ),
        )
    ).mappings()
    final = {str(row["gate_check_code"]): row for row in rows}
    laid: list[GateResult] = []
    for result in results:
        row = final.get(result.gate_check_code)
        if row is None or not waivable(result.gate_check_code, remark_pending=pending):
            laid.append(result)
            continue
        status = ChecklistStatus(_text(row["status"]))
        if status.value not in FINAL_STATUSES:
            # a failing item that remembers a waiver it outgrew: the sentence with the gate's own
            laid.append(outgrown(row, result))
            continue
        if status is not ChecklistStatus.WAIVED:
            laid.append(replace(result, status=status))
            continue
        spent = outgrown(row, result)
        if spent.waiver_outgrown is not None:
            # rev 1.305: the gate counts more than the waiver was approved for — it fails
            laid.append(spent)
            continue
        request_id = row["waiver_approval_request_id"]
        stored = row["result"] or {}
        laid.append(
            replace(
                result,
                status=status,
                waiver_approval_request_id=None if request_id is None else UUID(str(request_id)),
                waived_count=stored.get("count"),
            )
        )
    return tuple(laid)


def unsigned_blocking_tasks(session: Session, scope: PeriodScope) -> tuple[BlockingTask, ...]:
    """The tenant close tasks that hold the lock of the period (R-55 (a)), in template sequence:
    items of active ``MANUAL`` templates with ``is_blocking = true`` whose status is not
    ``PASSED``, ``WAIVED`` or ``NOT_APPLICABLE`` (the SCREENS_B BLK-16 population). A task with
    ``is_blocking = false`` never holds a lock."""
    rows = session.execute(
        select(
            close_checklist_template.c.code,
            close_checklist_template.c.name,
            close_checklist_item.c.status,
        )
        .join(
            close_checklist_template,
            and_(
                close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            ),
        )
        .where(
            _of_period(close_checklist_item, scope),
            close_checklist_template.c.is_active.is_(True),
            close_checklist_template.c.gate_kind == ChecklistGateKind.MANUAL.value,
            close_checklist_template.c.is_blocking.is_(True),
            close_checklist_item.c.status.not_in(
                sorted(status.value for status in CLEARED_STATUSES)
            ),
        )
        .order_by(close_checklist_template.c.sequence, close_checklist_template.c.id)
    ).all()
    return tuple(
        BlockingTask(code=str(code), name=str(name), status=ChecklistStatus(_text(status)))
        for code, name, status in rows
    )


def evaluate_gates(
    uow: UnitOfWork, entity_id: UUID, book_code: str, period_id: UUID
) -> GateResults:
    """Evaluate the fourteen gates of a period (REQ-CLS-009). While the period is ``open``,
    ``closing`` or ``reopened``, every active template gets its item and each automatic item stores
    its result; the results are returned in either case. 404 ``not-found`` for an unknown period
    state.

    What a lock decision needs comes back in one value (SC-N4; supervisor ruling R-55): the
    results carry the final state of their checklist items — a gate waived through an approved
    waiver is ``WAIVED`` (``with_final_items``) — and ``blocking_tasks`` holds the tenant close
    tasks that still hold the lock (``unsigned_blocking_tasks``).

    The gates read under the tenant's every-entity row scope, whatever the caller's roles
    (supervisor ruling R-42 (d), item CLO-GATE-SCOPE-1; ``db.session.every_entity_scope``): a
    gate's result must not depend on who evaluates it, and the rows a gate counts can carry
    another entity than the period's. The caller has authorised the principal for the period's
    entity before it calls (``commands._pinned_scope``).

    The state row is pinned ``FOR SHARE`` here, for every caller (item CLO-GATE-RUN-2; 04
    T-CLS-03 rev 1.228): the results are stored for the state read under that lock. The commands
    hold the row already; the close run's ``EXCEPTION_CHECK`` step held nothing."""
    with every_entity_scope(uow.session, uow.principal.db_context):
        scope = scope_of_period(uow.session, entity_id, _text(book_code), period_id, share=True)
        if scope is None:
            raise Problem("not-found")
        results = gate_results(
            signals(uow.session, scope, known_at=uow.now, files=uow.files, keyring=uow.keyring),
            at=uow.now,
        )
        tasks: tuple[BlockingTask, ...] = ()
        if scope.state in EVALUATED_STATES:
            ensure_items(uow, scope)
            _store(uow, results, scope)
            tasks = unsigned_blocking_tasks(uow.session, scope)
        laid = with_final_items(uow.session, scope, results)
    return GateResults(laid, tasks)
