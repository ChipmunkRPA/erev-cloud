"""API-R-18 period schemas: API-S-Period and the ``open`` command (04 §16.8, T-REF-05 to T-REF-07;
BUILD_SPEC RFD-2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import (
    BookCode,
    ChecklistStatus,
    LockKind,
    PeriodState,
    ReasonCode,
    SnapshotKind,
)
from erev_api.schemas.calendars import CalendarPeriodOut
from erev_api.schemas.common import ActorOut, RefOut

MEMO_LENGTH: Final = 4000  # TY erev.memo


class PeriodLockOut(BaseModel):
    """API-S-Period ``current_lock`` and ``dataset_lock``: one T-CLS-04 record of the period."""

    id: uuid.UUID
    kind: str
    created_at: datetime
    created_by: ActorOut
    ledger_head_chain_seq: int | None
    snapshot_manifest_sha256: str | None


class CloseRunRefOut(BaseModel):
    """API-S-Period ``close_run``; null until CLO creates close runs."""

    id: uuid.UUID
    status: str
    current_step_code: str | None


class PeriodBlockersOut(BaseModel):
    """Counts by gate check code (REQ-CLS-008); 0 until CLO registers the sources."""

    exceptions_open: int
    holds_open: int
    unmapped_products: int
    judgements_unreviewed: int
    approvals_pending: int
    interface_failures: int
    jobs_failed: int
    groups_dirty: int
    batches_unexported: int
    batches_unacknowledged: int
    reconciliations_unsigned: int
    manual_adjustments_pending: int


class PeriodFollowsOut(BaseModel):
    """API-S-Period ``follows`` (04 §16.8 rev 1.155; supervisor rulings R-112 (e) and R-114 (d)):
    the book whose close a period of the LEGACY book follows — the tenant's primary book — and
    the state of that book's period for the same entity; ``state`` is null where the entity keeps
    no period of that book there."""

    book_code: BookCode
    state: PeriodState | None


class PeriodOut(BaseModel):
    """API-S-Period: one row per entity, book and period; ``id`` is ``period_state.id``."""

    id: uuid.UUID
    entity: RefOut
    book: BookCode
    period: CalendarPeriodOut
    state: PeriodState
    state_changed_at: datetime
    is_first_open: bool
    current_lock: PeriodLockOut | None
    # the ``LOCK`` record whose datasets stand (04 §16.8 rev 1.301): ``current_lock`` while it
    # is a ``LOCK``, the lock a ``PERMANENT_LOCK`` record follows, null otherwise — the record a
    # report run "as locked" names
    dataset_lock: PeriodLockOut | None = None
    # null in a row of ``GET /periods`` alone (04 §16.8 rev 1.199): the single read, the
    # cockpit and the commands' answers always carry the counts
    blockers: PeriodBlockersOut | None
    close_run: CloseRunRefOut | None
    row_version: int
    # null for a period of a posting book; the row's own ``state`` is never rewritten
    follows: PeriodFollowsOut | None = None


class PeriodOpenIn(BaseModel):
    """``POST /periods/{id}/open``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PeriodStartCloseIn(BaseModel):
    """``POST /periods/{id}/start-close`` (BUILD_SPEC CLO-3)."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PeriodCancelCloseIn(BaseModel):
    """``POST /periods/{id}/cancel-close``: ``reason_code`` of the table 3.4-R subset
    ``CLOSE_RESTARTED``, ``DATA_CORRECTION_PENDING``, ``OTHER`` (BUILD_SPEC CLO-3)."""

    model_config = ConfigDict(extra="forbid")

    reason_code: ReasonCode
    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PeriodTransitionOut(BaseModel):
    """One ``period_state_transition`` of ``GET /periods/{id}/transitions`` (T-REF-07).
    ``approval_request_no`` is the number of the request ``approval_request_id`` names, null for
    a transition no request decided (04 §16.8, rev 1.207; item CLO-LOCKS-READ-1)."""

    id: uuid.UUID
    period_state_id: uuid.UUID
    from_state: PeriodState | None
    to_state: PeriodState
    reason_code: ReasonCode | None
    comment: str | None
    approval_request_id: uuid.UUID | None
    approval_request_no: str | None
    period_lock_id: uuid.UUID | None
    close_run_id: uuid.UUID | None
    created_by: ActorOut
    created_at: datetime


class PeriodGateResultOut(BaseModel):
    """One gate result of ``POST /periods/{id}/request-lock`` (T-CLS-03 ``result`` with its
    code). A gate waived through an approved waiver is ``WAIVED`` and names the request and the
    count its item held when the waiver was approved, beside the count the gate computes now
    (supervisor ruling R-55 (b): the two counts on the lock request)."""

    gate_check_code: str
    status: ChecklistStatus
    count: int | None
    detail: str | None
    evaluated_at: datetime
    waiver_approval_request_id: uuid.UUID | None = None
    waived_count: int | None = None


class PeriodLockRequestIn(BaseModel):
    """``POST /periods/{id}/request-lock`` (04 §16.8; BUILD_SPEC CLO-6): the certification comment,
    at least 10 characters (BR-PLT-08)."""

    model_config = ConfigDict(extra="forbid")

    certification_comment: str = Field(min_length=1, max_length=MEMO_LENGTH)


class PeriodLockRequestOut(BaseModel):
    """``{approval_request_id, gate_results}`` (04 §16.8 ``request-lock``)."""

    approval_request_id: uuid.UUID
    gate_results: list[PeriodGateResultOut]


class PeriodReopenRequestIn(BaseModel):
    """``POST /periods/{id}/request-reopen`` (04 §16.8; BUILD_SPEC CLO-7): a reason of the
    request-reopen subset of E-110 (``ERROR_CORRECTION``, ``LATE_SOURCE_DATA``,
    ``AUDIT_ADJUSTMENT``, ``OTHER``; any other literal is 422 ``REASON_CODE_NOT_ALLOWED``) and a
    comment of at least 10 characters (BR-PLT-08)."""

    model_config = ConfigDict(extra="forbid")

    reason_code: ReasonCode
    comment: str = Field(min_length=1, max_length=MEMO_LENGTH)


class PeriodReopenRequestOut(BaseModel):
    """``{approval_request_id}``: a ``PERIOD_REOPEN`` request two approvers other than the
    requester decide, at least one a Controller (REQ-CLS-011)."""

    approval_request_id: uuid.UUID


class PeriodPermanentLockRequestIn(BaseModel):
    """``POST /periods/{id}/request-permanent-lock``: a comment of at least 10 characters."""

    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=1, max_length=MEMO_LENGTH)


class PeriodPermanentLockRequestOut(BaseModel):
    approval_request_id: uuid.UUID


class PeriodLockGateOut(BaseModel):
    """One gate result of a lock record's ``certification`` (04 T-CLS-04; API-S-PeriodLock, rev
    1.207): the stored row. The three waiver members are null except on a ``WAIVED`` gate
    (supervisor ruling R-55 (b)), which names its waiver request and that request's number;
    ``replayed`` is true only on the result the replay of a source lock laid over a sandbox's
    own evaluation (ruling R-116 (e))."""

    gate_check_code: str
    status: ChecklistStatus
    count: int | None
    evaluated_at: datetime
    waiver_approval_request_id: uuid.UUID | None = None
    waiver_approval_request_no: str | None = None
    waived_count: int | None = None
    replayed: bool = False


class PeriodLockSnapshotOut(BaseModel):
    """One dataset a ``LOCK`` record froze (04 T-CLS-05): its kind, row count and file hash. The
    file and its control totals stay with the reads of the dataset itself."""

    snapshot_kind: SnapshotKind
    row_count: int
    file_sha256: str


class PeriodLockRowOut(BaseModel):
    """One T-CLS-04 row of ``GET /periods/{id}/locks`` (04 §16.8 API-S-PeriodLock, rev 1.140).
    ``cutoff_known_at`` is the instant a ``LOCK`` froze its datasets at (supervisor ruling R-94
    (d); ENGINE_SPEC_B S15-R-18c): null for another kind and for a lock older than revision
    0084. Rev 1.207 (item CLO-LOCKS-READ-1): the record's ``certification``, its
    ``ledger_head_sha256``, the datasets it froze (``snapshots``, E-64 order) and the number of
    its request, ``approval_request_no`` — null only for a request outside the reader's row
    scope. ``audit_head_hmac`` is not stated."""

    id: uuid.UUID
    kind: LockKind
    created_at: datetime
    created_by: ActorOut
    approval_request_id: uuid.UUID
    approval_request_no: str | None
    reason_code: ReasonCode | None
    comment: str | None
    certification: list[PeriodLockGateOut]
    ledger_head_chain_seq: int
    ledger_head_sha256: str | None
    audit_head_chain_seq: int
    snapshot_manifest_sha256: str | None
    previous_lock_id: uuid.UUID | None
    diff_report_file_id: uuid.UUID | None
    cutoff_known_at: datetime | None
    snapshots: list[PeriodLockSnapshotOut]
