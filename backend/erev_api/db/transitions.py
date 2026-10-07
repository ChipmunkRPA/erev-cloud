"""Status transitions DB-03 (dev-guide §6.2 SM; 04 §1.5 IM-S, §14.1 DB-03).

``TRANSITIONS`` is the single source of the column allow-lists and status pairs of IM-S tables
(DG-SM-01). ``apply`` checks a change in Python before any SQL and then issues the conditional
UPDATE (DG-SM-02). ``transition_trigger_sql`` renders the body of ``erev.tg_<table>__transition()``,
which enforces the same rule in the database with ``EREV-TRN-001``. A revision embeds the rendered
body as a literal, and DG-ARC-07 compares every installed function with a fresh rendering. Items add
their IM-S tables here in the item that creates the table.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.db.tables import metadata
from erev_api.problems import Problem, ProblemError, from_db_error

RULE_ID: Final = "DB-03"
_COLUMN: Final = re.compile(r"^[a-z][a-z0-9_]{0,47}$")  # NC-02
_STATUS: Final = re.compile(r"^[A-Za-z0-9_]{1,63}$")


@dataclass(frozen=True, slots=True)
class FrozenElement:
    """The elements of the jsonb array ``column`` whose member ``key`` equals ``value``. While the
    row is frozen they may change; the other elements, their order and their count may not
    (BS4-D-03)."""

    column: str
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class ParentStatus:
    """The parent row of ``table`` named by the child's ``column``. While its ``status_column``
    holds one of ``statuses``, or the parent is not visible, nothing of the child changes (04
    T-CLS-07)."""

    table: str
    column: str
    status_column: str
    statuses: frozenset[str]


@dataclass(frozen=True, slots=True)
class TableTransitions:
    table: str
    status_column: str | None  # None when only a column allow-list applies
    updatable_columns: frozenset[str]  # the IM-S column list of the 04 table header
    pairs: frozenset[tuple[str, str]]  # allowed (from, to) status pairs
    editable_while: frozenset[str] = frozenset()  # statuses in which every column may change
    set_once: frozenset[str] = frozenset()  # updatable columns that change only from NULL
    # Statuses in which only the status, SC-M and the ``frozen_element`` column change (CLO-2).
    frozen_while: frozenset[str] = frozenset()
    frozen_element: FrozenElement | None = None
    parent: ParentStatus | None = None  # a parent status that freezes the whole row (CLO-2)

    def __post_init__(self) -> None:
        if not self.set_once <= self.updatable_columns:
            raise ValueError(f"{self.table!r} set-once columns must be updatable columns")
        names = {self.table, *self.updatable_columns}
        if self.status_column is not None:
            names.add(self.status_column)
        if self.frozen_element is not None:
            names |= {self.frozen_element.column, self.frozen_element.key}
        if self.parent is not None:
            names |= {self.parent.table, self.parent.column, self.parent.status_column}
        if not all(_COLUMN.fullmatch(name) for name in names):
            raise ValueError(f"invalid table or column name in {self.table!r} (NC-02)")
        statuses = (
            {status for pair in self.pairs for status in pair}
            | self.editable_while
            | self.frozen_while
        )
        literals = set(statuses)
        if self.frozen_element is not None:
            literals.add(self.frozen_element.value)
        if self.parent is not None:
            literals |= self.parent.statuses
        if not all(_STATUS.fullmatch(status) for status in literals):
            raise ValueError(f"invalid status literal in {self.table!r}")
        if self.status_column is None and statuses:
            raise ValueError(f"{self.table!r} has status pairs but no status column")
        if self.status_column in self.updatable_columns:
            raise ValueError(f"{self.table!r} lists its status column among updatable columns")
        if self.frozen_while & self.editable_while:
            raise ValueError(f"{self.table!r} cannot be editable and frozen in one status")
        if self.frozen_element is not None and (
            not self.frozen_while or self.frozen_element.column not in self.updatable_columns
        ):
            raise ValueError(f"{self.table!r} frozen element needs frozen statuses and its column")


_SC_M: Final = frozenset({"row_version", "updated_at", "updated_by", "updated_by_kind"})
# 04 E-34 (CLO-1): draft → approved → exported → acknowledged or failed; failed → exported (retry,
# or the manual hand-over); draft or approved → cancelled; failed → cancelled (rev 1.159, item
# JRN-FAILED-CANCEL-1: the cancel of a failed run after its ledger was asked; Alembic revision
# 0108). Shared by journal runs and journal batches.
_JOURNAL_STATE_PAIRS: Final = frozenset(
    {
        ("draft", "approved"),
        ("approved", "exported"),
        ("exported", "acknowledged"),
        ("exported", "failed"),
        ("failed", "exported"),
        ("draft", "cancelled"),
        ("approved", "cancelled"),
        ("failed", "cancelled"),
    }
)
# 04 E-67 (RPS-1): QUEUED → RUNNING → SUCCEEDED or FAILED; QUEUED → FAILED when the job fails
# before the run starts. Shared by report runs and evidence packs.
_RUN_STATUS_PAIRS: Final = frozenset(
    {
        ("QUEUED", "RUNNING"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED"),
        ("QUEUED", "FAILED"),
    }
)

# 04 E-76 (LMG-1; PRD SM-12, D-31): UPLOADED → PROFILING → PROFILED → IMPORTING → IMPORTED →
# RECONCILED → SUBMITTED → PROMOTED; every non-terminal status → FAILED and → CANCELLED; PROMOTED,
# FAILED and CANCELLED are terminal.
_MIGRATION_CHAIN: Final = (
    "UPLOADED",
    "PROFILING",
    "PROFILED",
    "IMPORTING",
    "IMPORTED",
    "RECONCILED",
    "SUBMITTED",
    "PROMOTED",
)
_MIGRATION_STATUS_PAIRS: Final = frozenset(
    {*zip(_MIGRATION_CHAIN, _MIGRATION_CHAIN[1:], strict=False)}
    | {(status, "FAILED") for status in _MIGRATION_CHAIN[:-1]}
    | {(status, "CANCELLED") for status in _MIGRATION_CHAIN[:-1]}
)

TRANSITIONS: Final[Mapping[str, TableTransitions]] = MappingProxyType(
    {
        # 04 T-PLT-40 and E-107: DRAFT → IN_REVIEW → COMPLETED; DRAFT or IN_REVIEW → CANCELLED
        # (SPEC-Q-193). The start and completion columns are set once.
        "access_review_campaign": TableTransitions(
            table="access_review_campaign",
            status_column="status",
            updatable_columns=frozenset({"completed_at", "snapshot_file_id", "started_at"}) | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "IN_REVIEW"),
                    ("IN_REVIEW", "COMPLETED"),
                    ("DRAFT", "CANCELLED"),
                    ("IN_REVIEW", "CANCELLED"),
                }
            ),
            set_once=frozenset({"completed_at", "snapshot_file_id", "started_at"}),
        ),
        # 04 T-PLT-41 and E-108: a PENDING item is CERTIFIED or REVOKE_REQUESTED once; a requested
        # revocation becomes REVOKED when its completion is confirmed (SPEC-Q-193).
        "access_review_item": TableTransitions(
            table="access_review_item",
            status_column="decision",
            updatable_columns=frozenset(
                {"comment", "decided_at", "reviewer_id", "revocation_completed_at"}
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("PENDING", "CERTIFIED"),
                    ("PENDING", "REVOKE_REQUESTED"),
                    ("REVOKE_REQUESTED", "REVOKED"),
                }
            ),
            set_once=frozenset({"comment", "decided_at", "reviewer_id", "revocation_completed_at"}),
        ),
        # 04 T-PLT-21: a revocation sets the three revocation columns once.
        "approval_delegation": TableTransitions(
            table="approval_delegation",
            status_column=None,
            updatable_columns=frozenset({"revoked_at", "revoked_by", "revoked_by_kind"}),
            pairs=frozenset(),
            set_once=frozenset({"revoked_at", "revoked_by", "revoked_by_kind"}),
        ),
        # 04 T-PLT-17 and PRD SM-01: PENDING → APPROVED, REJECTED, VOIDED or WITHDRAWN (E-05); the
        # step pointer moves while PENDING.
        "approval_request": TableTransitions(
            table="approval_request",
            status_column="status",
            updatable_columns=frozenset(
                {"current_step_no", "decided_at", "void_reason", "voided_at"}
            ),
            pairs=frozenset(
                {
                    ("PENDING", "APPROVED"),
                    ("PENDING", "REJECTED"),
                    ("PENDING", "VOIDED"),
                    ("PENDING", "WITHDRAWN"),
                }
            ),
            set_once=frozenset({"decided_at", "void_reason", "voided_at"}),
        ),
        # 04 T-PLT-18 and PRD SM-01: steps activate in order; an active step is approved, rejected
        # or voided, and a waiting step is skipped or voided (E-06).
        "approval_step": TableTransitions(
            table="approval_step",
            status_column="status",
            updatable_columns=frozenset({"activated_at", "completed_at"}),
            pairs=frozenset(
                {
                    ("WAITING", "ACTIVE"),
                    ("ACTIVE", "APPROVED"),
                    ("ACTIVE", "REJECTED"),
                    ("ACTIVE", "VOIDED"),
                    ("WAITING", "SKIPPED"),
                    ("WAITING", "VOIDED"),
                }
            ),
            set_once=frozenset({"activated_at", "completed_at"}),
        ),
        # 04 T-CLS-03 and E-60 (CLO-2): IM-M with a DB-03 allow-list; the template, entity, book and
        # period are the item's identity. A gate is evaluated again until lock, so PASSED and FAILED
        # alternate; a manual task is signed PASSED; an approved waiver or NOT_APPLICABLE ends the
        # item (L4-2-Q-21). A waiver ends with what it covered (rev 1.305, revision 0130; item
        # CLO-WAIVER-COVERS-LATER-1): WAIVED → FAILED when the gate counts more than the waiver
        # was approved for, WAIVED → NOT_STARTED when the period is reopened.
        "close_checklist_item": TableTransitions(
            table="close_checklist_item",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "comment",
                    "control_execution_id",
                    "due_date",
                    "owner_membership_id",
                    "result",
                    "signoff_id",
                    "waiver_approval_request_id",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("NOT_STARTED", "IN_PROGRESS"),
                    ("NOT_STARTED", "PASSED"),
                    ("NOT_STARTED", "FAILED"),
                    ("NOT_STARTED", "WAIVED"),
                    ("NOT_STARTED", "NOT_APPLICABLE"),
                    ("IN_PROGRESS", "PASSED"),
                    ("IN_PROGRESS", "FAILED"),
                    ("IN_PROGRESS", "WAIVED"),
                    ("IN_PROGRESS", "NOT_APPLICABLE"),
                    ("FAILED", "IN_PROGRESS"),
                    ("FAILED", "PASSED"),
                    ("FAILED", "WAIVED"),
                    ("PASSED", "FAILED"),
                    ("PASSED", "NOT_STARTED"),
                    ("WAIVED", "FAILED"),
                    ("WAIVED", "NOT_STARTED"),
                }
            ),
        ),
        # 04 T-CLS-01, E-62 and PRD SM-14 (CLO-2): PENDING → RUNNING → SUCCEEDED; RUNNING → BLOCKED
        # → RUNNING; RUNNING → FAILED → RUNNING (resume); RUNNING → CANCELLED. A SUCCEEDED run is
        # frozen except the LOCK element of ``steps``, which the lock job completes (BS4-D-03).
        # ``rates_read`` and ``registry_read`` (rev 1.291, revision 0127; item
        # CLO-RATE-AFTER-RUN-1) are what the run's first period-end step read: written once, by
        # that step.
        "close_run": TableTransitions(
            table="close_run",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "counts",
                    "current_step_code",
                    "finished_at",
                    "rates_read",
                    "registry_read",
                    "started_at",
                    "steps",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("PENDING", "RUNNING"),
                    ("RUNNING", "SUCCEEDED"),
                    ("RUNNING", "BLOCKED"),
                    ("BLOCKED", "RUNNING"),
                    ("RUNNING", "FAILED"),
                    ("FAILED", "RUNNING"),
                    ("RUNNING", "CANCELLED"),
                }
            ),
            set_once=frozenset({"rates_read", "registry_read", "started_at"}),
            frozen_while=frozenset({"SUCCEEDED"}),
            frozen_element=FrozenElement(column="steps", key="step_code", value="LOCK"),
        ),
        # 04 T-CON-03 and E-95 (CTR-1): a proposed group is submitted, then approved and applied, or
        # rejected, or discarded before its submission (rev 1.289, item
        # COMBINATION-PROPOSAL-DISCARD-1); singletons are created APPLIED. Dirty marking — the
        # stamp and the trigger a mark carries (rev 1.297, item FX-REPUBLISH-DIRTY-1) — the head
        # computation, the group inception and the mark of its period ends (rev 1.172, item
        # CLO-GATE-RUN-1) change in any status (05 RCP-17; L3-1-Q-14).
        "combination_group": TableTransitions(
            table="combination_group",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "approval_request_id",
                    "criterion",
                    "dirty_since",
                    "dirty_trigger",
                    "head_computation_id",
                    "inception_date",
                    "judgement_record_id",
                    "period_ends_open",
                    "rationale",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("PROPOSED", "SUBMITTED"),
                    ("PROPOSED", "VOIDED"),
                    ("SUBMITTED", "APPROVED"),
                    ("APPROVED", "APPLIED"),
                    ("SUBMITTED", "REJECTED"),
                }
            ),
        ),
        # 04 T-CON-01, E-17 and PRD SM-02 (CTR-7): DRAFT → PENDING_REVIEW → ACTIVE or back to
        # DRAFT; DRAFT → NOT_A_CONTRACT → PENDING_REVIEW; ACTIVE ↔ COMPLETED; ACTIVE → TERMINATED;
        # any status except VOIDED → VOIDED. The header is a projection of events (DB-18).
        # [J] L4-1-Q-11: a DRAFT header changes freely (replace-draft replaces the booking members,
        # and the approved / SYSTEM activation moves the stored DRAFT to ACTIVE — a listed
        # pair since D-98 candidate 143 AMENDMENT 1, not the editable early-return's
        # silence); afterwards only
        # the columns later events project change.
        "contract": TableTransitions(
            table="contract",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "activated_at",
                    "activation_checklist",
                    "combination_group_id",
                    "completed_at",
                    "custom_attributes",
                    "head_stream_version",
                    "latest_computation_id",
                    "memo_1",
                    "memo_2",
                    "memo_3",
                    "scope_605_35",
                    "terminated_at",
                    "voided_at",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "PENDING_REVIEW"),
                    # D-98 candidate 143 AMENDMENT 1: the STORED move of the approved SM-02 and the
                    # SYSTEM activation — the submit appends no event (L4-1-Q-18), so the row is
                    # DRAFT when ``activate`` writes ACTIVE (events/stream._next_status projects
                    # CONTRACT_ACTIVATED from DRAFT or PENDING_REVIEW).
                    ("DRAFT", "ACTIVE"),
                    ("PENDING_REVIEW", "ACTIVE"),
                    ("PENDING_REVIEW", "DRAFT"),
                    ("DRAFT", "NOT_A_CONTRACT"),
                    ("NOT_A_CONTRACT", "PENDING_REVIEW"),
                    ("ACTIVE", "COMPLETED"),
                    ("COMPLETED", "ACTIVE"),
                    ("ACTIVE", "TERMINATED"),
                    ("DRAFT", "VOIDED"),
                    ("PENDING_REVIEW", "VOIDED"),
                    ("NOT_A_CONTRACT", "VOIDED"),
                    ("ACTIVE", "VOIDED"),
                    ("COMPLETED", "VOIDED"),
                    ("TERMINATED", "VOIDED"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
        ),
        # 04 T-CON-04 (CTR-1): a membership ends once, with the leave event.
        "combination_group_member": TableTransitions(
            table="combination_group_member",
            status_column=None,
            updatable_columns=frozenset({"leave_event_id", "valid_to_known_at"}),
            pairs=frozenset(),
            set_once=frozenset({"leave_event_id", "valid_to_known_at"}),
        ),
        # 04 T-CON-13, E-12 and PRD SM-04 (CTR-12): editable while DRAFT; afterwards the status, the
        # request, the applied events and SC-M change only. DRAFT → SUBMITTED → APPROVED →
        # SUPERSEDED; SUBMITTED → REJECTED → DRAFT or SUBMITTED → WITHDRAWN → DRAFT; DRAFT →
        # VOIDED (discard; 04 rev 1.210, revision 0114).
        "estimate_version": TableTransitions(
            table="estimate_version",
            status_column="status",
            updatable_columns=frozenset({"applied_event_ids", "approval_request_id"}) | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "SUBMITTED"),
                    ("SUBMITTED", "APPROVED"),
                    ("SUBMITTED", "REJECTED"),
                    ("SUBMITTED", "WITHDRAWN"),
                    ("APPROVED", "SUPERSEDED"),
                    ("REJECTED", "DRAFT"),
                    ("WITHDRAWN", "DRAFT"),
                    ("DRAFT", "VOIDED"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
        ),
        # 04 T-CON-06 and PRD SM-03 (CTR-17; D-98 140): editable while DRAFT; afterwards the status,
        # the request, the applied event and SC-M change only. DRAFT → SUBMITTED → APPROVED →
        # APPLIED; SUBMITTED → DRAFT (withdraw / edit) or REJECTED → DRAFT (revise); DRAFT → VOIDED
        # (discard); APPLIED → VOIDED (the amendment's approved EVENT_VOIDED).
        "modification": TableTransitions(
            table="modification",
            status_column="status",
            updatable_columns=frozenset({"applied_event_id", "approval_request_id"}) | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "SUBMITTED"),
                    ("SUBMITTED", "DRAFT"),
                    ("SUBMITTED", "APPROVED"),
                    ("SUBMITTED", "REJECTED"),
                    ("REJECTED", "DRAFT"),
                    ("APPROVED", "APPLIED"),
                    ("DRAFT", "VOIDED"),
                    ("APPLIED", "VOIDED"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
        ),
        # 04 T-CON-24 (CTR-1): editable while DRAFT; DRAFT → SUBMITTED → APPROVED → APPLIED;
        # SUBMITTED → REJECTED; DRAFT or SUBMITTED → VOIDED (withdrawn).
        "event_submission": TableTransitions(
            table="event_submission",
            status_column="status",
            updatable_columns=frozenset({"applied_event_ids", "approval_request_id"}) | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "SUBMITTED"),
                    ("SUBMITTED", "APPROVED"),
                    ("APPROVED", "APPLIED"),
                    ("SUBMITTED", "REJECTED"),
                    ("DRAFT", "VOIDED"),
                    ("SUBMITTED", "VOIDED"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
        ),
        # 04 T-PLT-30: a void sets the four void columns once; nothing else changes.
        "file_attachment": TableTransitions(
            table="file_attachment",
            status_column=None,
            updatable_columns=frozenset(
                {"voided_at", "voided_by", "voided_by_kind", "void_reason"}
            ),
            pairs=frozenset(),
            set_once=frozenset({"voided_at", "voided_by", "voided_by_kind", "void_reason"}),
        ),
        # 04 T-PLT-29: IM-A with a DB-03 allow-list; retention flags change by retention commands,
        # the shredding columns once from NULL by ``file.shred`` — the decision — and
        # ``shred_completed_at`` once from NULL when the store's part is recorded (rev 1.237).
        "file_object": TableTransitions(
            table="file_object",
            status_column=None,
            updatable_columns=frozenset(
                {
                    "legal_hold",
                    "retention_until",
                    "shred_completed_at",
                    "shred_reason",
                    "shredded_at",
                    "shredded_by",
                    "shredded_by_kind",
                }
            ),
            pairs=frozenset(),
            set_once=frozenset(
                {
                    "shred_completed_at",
                    "shred_reason",
                    "shredded_at",
                    "shredded_by",
                    "shredded_by_kind",
                }
            ),
        ),
        # 04 T-IMP-02, E-40 and PRD SM-05: upload → validate → dry-run diff → approval → commit;
        # UPLOADED to DIFF_READY → CANCELLED (L4-1-Q-27). The commit time is set once.
        "import_upload": TableTransitions(
            table="import_upload",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "approval_request_id",
                    "committed_at",
                    "control_totals",
                    "diff_file_id",
                    "diff_summary",
                    "error_count",
                    "job_id",
                    "named_entity_ids",  # 04 rev 1.107 (R-29): set once by the validation job
                    "row_count",
                    "valid_row_count",
                    "warning_count",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("UPLOADED", "VALIDATING"),
                    ("VALIDATING", "INVALID"),
                    ("VALIDATING", "VALIDATED"),
                    ("VALIDATED", "DIFFING"),
                    ("DIFFING", "DIFF_READY"),
                    # 04 T-IMP-02 rev 1.270, PRD SM-05 rev 1.186 (revision 0122): a dry run whose
                    # job ended FAILED ends its upload, as a validation does.
                    ("DIFFING", "INVALID"),
                    ("DIFF_READY", "SUBMITTED"),
                    ("SUBMITTED", "APPROVED"),
                    ("SUBMITTED", "REJECTED"),
                    ("APPROVED", "COMMITTING"),
                    ("COMMITTING", "COMMITTED"),
                    ("COMMITTING", "FAILED"),
                    ("UPLOADED", "CANCELLED"),
                    ("VALIDATING", "CANCELLED"),
                    ("VALIDATED", "CANCELLED"),
                    ("DIFFING", "CANCELLED"),
                    ("DIFF_READY", "CANCELLED"),
                }
            ),
            set_once=frozenset({"committed_at", "named_entity_ids"}),
        ),
        # 04 T-PLT-27: QUEUED → RUNNING → SUCCEEDED, SUCCEEDED_WITH_EXCEPTIONS or FAILED; QUEUED or
        # RUNNING → CANCELLED; and RUNNING → QUEUED when a failed attempt is retried (DG-KRN-JOB-05;
        # SPEC-Q-162).
        "job": TableTransitions(
            table="job",
            status_column="state",
            updatable_columns=frozenset(
                {
                    "cancel_requested_at",
                    "finished_at",
                    "problem",
                    "procrastinate_job_id",
                    "progress_done",
                    "progress_total",
                    "result",
                    "row_version",
                    "started_at",
                    "updated_at",
                    "updated_by",
                    "updated_by_kind",
                }
            ),
            pairs=frozenset(
                {
                    ("QUEUED", "RUNNING"),
                    ("RUNNING", "SUCCEEDED"),
                    ("RUNNING", "SUCCEEDED_WITH_EXCEPTIONS"),
                    ("RUNNING", "FAILED"),
                    ("QUEUED", "CANCELLED"),
                    ("RUNNING", "CANCELLED"),
                    ("RUNNING", "QUEUED"),
                }
            ),
        ),
        # 04 T-SL-07 and E-34 (CLO-1): the export columns change along the E-34 pairs; the
        # acknowledgement instant is set once. The run rolls up from its batches (SMAP-08).
        "journal_batch": TableTransitions(
            table="journal_batch",
            status_column="state",
            updatable_columns=frozenset(
                {
                    "acknowledged_at",
                    "attempt_count",
                    "export_file_id",
                    "export_sha256",
                    "exported_at",
                    "last_error",
                    "outbox_message_id",
                }
            )
            | _SC_M,
            pairs=_JOURNAL_STATE_PAIRS,
            set_once=frozenset({"acknowledged_at"}),
        ),
        # 04 T-SL-06 and E-34 (CLO-1): the request and the lifecycle instants change along the E-34
        # pairs; approval, acknowledgement and cancellation are set once, and a retried export
        # moves ``exported_at``.
        "journal_run": TableTransitions(
            table="journal_run",
            status_column="state",
            updatable_columns=frozenset(
                {
                    "acknowledged_at",
                    "approval_request_id",
                    "approved_at",
                    "cancelled_at",
                    "exported_at",
                }
            )
            | _SC_M,
            pairs=_JOURNAL_STATE_PAIRS,
            set_once=frozenset({"acknowledged_at", "approved_at", "cancelled_at"}),
        ),
        # 04 T-CON-19, E-57 and PRD SM-10 (CTR-7): editable while DRAFT; DRAFT → SUBMITTED →
        # REVIEWED; SUBMITTED → REJECTED → DRAFT; REVIEWED → SUPERSEDED; DRAFT → VOIDED (discard;
        # 04 rev 1.242, revision 0118). Afterwards only the review columns, the request and SC-M
        # change; the reviewer and review time are set once.
        "judgement_record": TableTransitions(
            table="judgement_record",
            status_column="status",
            updatable_columns=frozenset({"approval_request_id", "reviewed_at", "reviewer_id"})
            | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "SUBMITTED"),
                    ("SUBMITTED", "REVIEWED"),
                    ("SUBMITTED", "REJECTED"),
                    ("REJECTED", "DRAFT"),
                    ("REVIEWED", "SUPERSEDED"),
                    ("DRAFT", "VOIDED"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
            set_once=frozenset({"reviewed_at", "reviewer_id"}),
        ),
        # 04 T-SL-05, E-94 and PRD SM-10 (CLO-1; rev 1.120 / PRD 1.49 amended for CLO-12, ruling
        # R-51 (b), revision 0093): editable while DRAFT; DRAFT → SUBMITTED → APPROVED → POSTED;
        # SUBMITTED → REJECTED; SUBMITTED → DRAFT (the request withdrawn, or voided as stale);
        # REJECTED → DRAFT (revise and resubmit); DRAFT → VOIDED (discard); POSTED → VOIDED through
        # an approved reversal. The applied event and the posting are set once.
        "manual_adjustment": TableTransitions(
            table="manual_adjustment",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "applied_event_id",
                    "approval_request_id",
                    "is_deferred_past_lock",
                    "subledger_posting_id",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "SUBMITTED"),
                    ("SUBMITTED", "DRAFT"),
                    ("SUBMITTED", "APPROVED"),
                    ("APPROVED", "POSTED"),
                    ("SUBMITTED", "REJECTED"),
                    ("REJECTED", "DRAFT"),
                    ("DRAFT", "VOIDED"),
                    ("POSTED", "VOIDED"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
            set_once=frozenset({"applied_event_id", "subledger_posting_id"}),
        ),
        # 04 T-PLT-24: a notification is read once and emailed once.
        # 04 T-MIG-01 (LMG-1): the IM-S columns of the table header change along E-76; the status
        # pairs are the PRD SM-12 chain with FAILED / CANCELLED from every non-terminal status.
        "migration_batch": TableTransitions(
            table="migration_batch",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "approval_request_id",
                    "capture_operation_id",  # 04 rev 1.60: the import's durable operation identity
                    "cutover_date",  # 04 rev 1.60 (D-98 cand. 128): set once at /import
                    "finished_at",
                    "import_upload_ids",
                    "job_id",
                    "problem",
                    "profile",
                    "reconciliation_id",
                    "reconciliation_report_run_id",
                    "registry_version_id",
                    "started_at",
                }
            )
            | _SC_M,
            pairs=_MIGRATION_STATUS_PAIRS,
            set_once=frozenset({"cutover_date"}),
        ),
        # 04 T-INT-02 (DIN-12) and E-72: QUEUED → RUNNING → SUCCEEDED, CONTROL_TOTAL_MISMATCH or
        # FAILED; QUEUED → FAILED when the run is refused before it starts. The IM-S columns are the
        # header's ledger members.
        "sync_run": TableTransitions(
            table="sync_run",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "checkpoint_after",
                    "exception_count",
                    "finished_at",
                    "loaded_totals",
                    "problem",
                    "record_count",
                    "source_totals",
                    "started_at",
                }
            )
            | _SC_M,
            pairs=frozenset(
                {
                    ("QUEUED", "RUNNING"),
                    ("RUNNING", "SUCCEEDED"),
                    ("RUNNING", "CONTROL_TOTAL_MISMATCH"),
                    ("RUNNING", "FAILED"),
                    ("QUEUED", "FAILED"),
                }
            ),
        ),
        # 04 T-INT-04 (DIN-12): ``valid_to`` is the only mutable column and is set once — a re-link
        # inserts a new row (SC-C only, no SC-M).
        "external_id_map": TableTransitions(
            table="external_id_map",
            status_column=None,
            updatable_columns=frozenset({"valid_to"}),
            pairs=frozenset(),
            set_once=frozenset({"valid_to"}),
        ),
        "notification": TableTransitions(
            table="notification",
            status_column=None,
            updatable_columns=frozenset({"email_sent_at", "read_at"}),
            pairs=frozenset(),
            set_once=frozenset({"email_sent_at", "read_at"}),
        ),
        # 04 T-INT-03 and dev-guide DG-KRN-EVT-05: a due message is claimed (PENDING or FAILED →
        # DISPATCHING), then DISPATCHED, FAILED with a backoff, or DEAD after the last attempt
        # (E-71).
        "outbox_message": TableTransitions(
            table="outbox_message",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "attempt_count",
                    "dispatched_at",
                    "last_error",
                    "next_attempt_at",
                    "row_version",
                    "updated_at",
                    "updated_by",
                    "updated_by_kind",
                }
            ),
            pairs=frozenset(
                {
                    ("PENDING", "DISPATCHING"),
                    ("FAILED", "DISPATCHING"),
                    ("DISPATCHING", "DISPATCHED"),
                    ("DISPATCHING", "FAILED"),
                    ("DISPATCHING", "DEAD"),
                }
            ),
            set_once=frozenset({"dispatched_at"}),
        ),
        # 04 T-CON-23 and E-12 (CTR-15): editable while DRAFT; afterwards the status, the request
        # and the approval instant change only. DRAFT → SUBMITTED → APPROVED → SUPERSEDED;
        # SUBMITTED → REJECTED → DRAFT or SUBMITTED → WITHDRAWN → DRAFT (a new edit round).
        "policy_override": TableTransitions(
            table="policy_override",
            status_column="status",
            updatable_columns=frozenset({"approval_request_id", "approved_at"}) | _SC_M,
            pairs=frozenset(
                {
                    ("DRAFT", "SUBMITTED"),
                    ("SUBMITTED", "APPROVED"),
                    ("SUBMITTED", "REJECTED"),
                    ("SUBMITTED", "WITHDRAWN"),
                    ("APPROVED", "SUPERSEDED"),
                    ("REJECTED", "DRAFT"),
                    ("WITHDRAWN", "DRAFT"),
                }
            ),
            editable_while=frozenset({"DRAFT"}),
            set_once=frozenset({"approved_at"}),
        ),
        # 04 T-CLS-06, E-59 and PRD SM-09 (CLO-2): DRAFT → PREPARED → REVIEWED → CERTIFIED; DRAFT →
        # AUTO_CERTIFIED → CERTIFIED; PREPARED, REVIEWED or CERTIFIED → REOPENED. Nothing changes
        # after CERTIFIED except the move to REOPENED. 04 rev 1.121 (revision 0095; supervisor
        # ruling R-54): a REOPENED row is history — every regeneration inserts a new DRAFT row,
        # so REOPENED → DRAFT is no pair (D-98 79) — and the trial balance is attached once
        # (``source_file_id`` or ``sync_run_id``).
        "reconciliation": TableTransitions(
            table="reconciliation",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "certified_at",
                    "period_lock_id",  # write-once at lock certification (04 rev 1.23; D-98 63)
                    "report_run_id",
                    "source_file_id",  # write-once at attach-trial-balance (04 rev 1.121)
                    "sync_run_id",  # write-once at attach-trial-balance (04 rev 1.121)
                    "totals",
                    "unexplained_other_amount",
                    "variance_count",
                }
            )
            | _SC_M,
            set_once=frozenset({"period_lock_id", "source_file_id", "sync_run_id"}),
            pairs=frozenset(
                {
                    ("DRAFT", "PREPARED"),
                    ("DRAFT", "AUTO_CERTIFIED"),
                    ("PREPARED", "REVIEWED"),
                    ("REVIEWED", "CERTIFIED"),
                    ("AUTO_CERTIFIED", "CERTIFIED"),
                    ("PREPARED", "REOPENED"),
                    ("REVIEWED", "REOPENED"),
                    ("CERTIFIED", "REOPENED"),
                }
            ),
            frozen_while=frozenset({"CERTIFIED"}),
        ),
        # 04 T-CLS-07 (CLO-2): the explanation and resolution columns change while the parent
        # reconciliation is not CERTIFIED.
        "reconciliation_item": TableTransitions(
            table="reconciliation_item",
            status_column=None,
            updatable_columns=frozenset(
                {"explanation", "resolved_at", "resolved_by", "resolved_by_kind"}
            )
            | _SC_M,
            pairs=frozenset(),
            parent=ParentStatus(
                table="reconciliation",
                column="reconciliation_id",
                status_column="status",
                statuses=frozenset({"CERTIFIED"}),
            ),
        ),
        # 04 T-RPT-02 and E-67 (RPS-1): QUEUED → RUNNING → SUCCEEDED or FAILED, and QUEUED → FAILED
        # when the job fails before the run starts. The output, totals, tie-outs, ledger heads,
        # child runs, snapshots, start, finish and problem change while QUEUED or RUNNING; a
        # SUCCEEDED or FAILED run changes in SC-M only. The start and finish are set once.
        "report_run": TableTransitions(
            table="report_run",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "child_report_run_ids",
                    "control_totals",
                    "disclosure_snapshot_ids",
                    "finished_at",
                    "ledger_heads",
                    "manifest_file_id",
                    "output_file_id",
                    "output_sha256",
                    "problem",
                    "row_count",
                    "source_binding",  # frps3b (04 T-RPT-02 rev 1.55): written once at SUCCEEDED
                    "started_at",
                    "tie_out_results",
                }
            )
            | _SC_M,
            pairs=_RUN_STATUS_PAIRS,
            frozen_while=frozenset({"SUCCEEDED", "FAILED"}),
            set_once=frozenset({"finished_at", "started_at"}),
        ),
        # 04 T-RPT-04 and E-67 (RPS-1): the E-67 pairs of report runs. The manifest, file and
        # report runs change while the pack is not SUCCEEDED; a SUCCEEDED pack changes in SC-M only.
        "evidence_pack": TableTransitions(
            table="evidence_pack",
            status_column="status",
            updatable_columns=frozenset(
                {"file_id", "manifest", "manifest_sha256", "report_run_ids"}
            )
            | _SC_M,
            pairs=_RUN_STATUS_PAIRS,
            frozen_while=frozenset({"SUCCEEDED"}),
        ),
        # 04 T-PLT-10: no status column; SMAP-14 derives active and revoked from ``revoked_at``.
        "role_assignment": TableTransitions(
            table="role_assignment",
            status_column=None,
            updatable_columns=frozenset(
                {"revoked_at", "revoked_by", "revoked_by_kind", "valid_to"}
            ),
            pairs=frozenset(),
        ),
        # 04 T-PLT-14 and PRD SM-13: REQUESTED → APPROVED → EXPIRED or REVOKED; REQUESTED →
        # REJECTED (E-96).
        "sod_exception": TableTransitions(
            table="sod_exception",
            status_column="status",
            updatable_columns=frozenset(
                {"approved_at", "revoked_at", "revoked_by", "revoked_by_kind"}
            ),
            pairs=frozenset(
                {
                    ("REQUESTED", "APPROVED"),
                    ("REQUESTED", "REJECTED"),
                    ("APPROVED", "EXPIRED"),
                    ("APPROVED", "REVOKED"),
                }
            ),
        ),
        # 04 T-PLT-33 and REQ-PLT-036: REQUESTED → APPROVED or REJECTED; an approved grant ends
        # EXPIRED or REVOKED (E-96). The decision and revocation columns are set once.
        # 04 T-REF-32 and E-67: QUEUED → RUNNING → SUCCEEDED or FAILED, and QUEUED → FAILED when
        # the job fails before the run starts. An exclusion recomputes the observation count and
        # the result file of a SUCCEEDED run; the start, finish and draft version are set once.
        "ssp_calculator_run": TableTransitions(
            table="ssp_calculator_run",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "draft_ssp_book_version_id",
                    "finished_at",
                    "observation_count",
                    "result_file_id",
                    "started_at",
                }
            ),
            pairs=frozenset(
                {
                    ("QUEUED", "RUNNING"),
                    ("RUNNING", "SUCCEEDED"),
                    ("RUNNING", "FAILED"),
                    ("QUEUED", "FAILED"),
                }
            ),
            set_once=frozenset({"draft_ssp_book_version_id", "finished_at", "started_at"}),
        ),
        "support_grant": TableTransitions(
            table="support_grant",
            status_column="status",
            updatable_columns=frozenset(
                {"approved_at", "revoked_at", "revoked_by", "revoked_by_kind"}
            ),
            pairs=frozenset(
                {
                    ("REQUESTED", "APPROVED"),
                    ("REQUESTED", "REJECTED"),
                    ("APPROVED", "EXPIRED"),
                    ("APPROVED", "REVOKED"),
                }
            ),
            set_once=frozenset({"approved_at", "revoked_at", "revoked_by", "revoked_by_kind"}),
        ),
        # 04 T-PLT-05: ``used_at`` only, from NULL to a value.
        # 04 T-PLT-34 and E-67 (SNP-1): QUEUED → RUNNING → SUCCEEDED or FAILED, and QUEUED → FAILED
        # when the job fails before the export starts; the manifest and the instants are set once;
        # target_tenant_id is set by the load (SNP-2) and may be repointed by a reset (SBX-07).
        "tenant_snapshot": TableTransitions(
            table="tenant_snapshot",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "target_tenant_id",
                    "manifest_file_id",
                    "manifest_sha256",
                    "row_counts",
                    "started_at",
                    "finished_at",
                }
            ),
            pairs=_RUN_STATUS_PAIRS,
            set_once=frozenset(
                {"manifest_file_id", "manifest_sha256", "started_at", "finished_at"}
            ),
        ),
        "user_recovery_code": TableTransitions(
            table="user_recovery_code",
            status_column=None,
            updatable_columns=frozenset({"used_at"}),
            pairs=frozenset(),
            set_once=frozenset({"used_at"}),
        ),
        # 04 T-PLT-36 and REQ-PLT-034: a due delivery is attempted until it succeeds or reaches
        # ``abandon_at``; FAILED stays FAILED between retries (E-97).
        "webhook_delivery": TableTransitions(
            table="webhook_delivery",
            status_column="status",
            updatable_columns=frozenset(
                {
                    "attempt_count",
                    "last_error",
                    "last_response_status",
                    "next_attempt_at",
                    "succeeded_at",
                }
            ),
            pairs=frozenset(
                {
                    ("PENDING", "SUCCEEDED"),
                    ("PENDING", "FAILED"),
                    ("PENDING", "ABANDONED"),
                    ("FAILED", "SUCCEEDED"),
                    ("FAILED", "ABANDONED"),
                }
            ),
            set_once=frozenset({"succeeded_at"}),
        ),
    }
)


def _array(values: frozenset[str]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in sorted(values)) + "]::text[]"


def frozen_columns(spec: TableTransitions) -> frozenset[str]:
    """The columns that may change while ``spec`` is in a ``frozen_while`` status: the status
    column, SC-M and the column of the frozen element."""
    allowed = spec.updatable_columns & _SC_M
    if spec.status_column is not None:
        allowed |= {spec.status_column}
    if spec.frozen_element is not None:
        allowed |= {spec.frozen_element.column}
    return allowed


def _parent_lines(parent: ParentStatus) -> list[str]:
    return [
        f"  SELECT p.{parent.status_column}::text INTO parent_status",
        f"    FROM erev.{parent.table} p",
        f"   WHERE p.tenant_id = OLD.tenant_id AND p.id = OLD.{parent.column};",
        f"  IF parent_status IS NULL OR parent_status = ANY ({_array(parent.statuses)}) THEN",
        "    RAISE EXCEPTION USING ERRCODE = 'P0001',",
        "      MESSAGE = format('EREV-TRN-001: %I.%I cannot change while its "
        f"{parent.table} is %s',",
        "                       TG_TABLE_SCHEMA, TG_TABLE_NAME,",
        "                       coalesce(parent_status, 'not visible'));",
        "  END IF;",
    ]


def _frozen_lines(spec: TableTransitions, status: str) -> list[str]:
    lines = [
        f"  IF OLD.{status}::text = ANY ({_array(spec.frozen_while)}) THEN",
        "    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed",
        "      FROM jsonb_each(new_row) n",
        f"     WHERE n.key <> ALL ({_array(frozen_columns(spec))})",
        "       AND n.value IS DISTINCT FROM old_row -> n.key;",
        "    IF changed IS NOT NULL THEN",
        "      RAISE EXCEPTION USING ERRCODE = 'P0001',",
        f"        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while {status} "
        "is %s',",
        f"                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.{status});",
        "    END IF;",
    ]
    element = spec.frozen_element
    if element is not None:
        column, key, value = element.column, element.key, element.value
        lines += [
            f"    IF jsonb_typeof(NEW.{column}) IS DISTINCT FROM 'array' THEN",
            "      RAISE EXCEPTION USING ERRCODE = 'P0001',",
            f"        MESSAGE = format('EREV-TRN-001: {column} of %I.%I must stay an array',",
            "                         TG_TABLE_SCHEMA, TG_TABLE_NAME);",
            "    END IF;",
            f"    IF jsonb_array_length(NEW.{column}) <> jsonb_array_length(OLD.{column})",
            "       OR EXISTS (",
            "         SELECT 1",
            f"           FROM jsonb_array_elements(OLD.{column}) WITH ORDINALITY o(item, ordinal)",
            f"           JOIN jsonb_array_elements(NEW.{column}) WITH ORDINALITY n(item, ordinal)",
            "             USING (ordinal)",
            "          WHERE o.item IS DISTINCT FROM n.item",
            f"            AND NOT (o.item ->> '{key}' = '{value}' "
            f"AND n.item ->> '{key}' = '{value}')) THEN",
            "      RAISE EXCEPTION USING ERRCODE = 'P0001',",
            f"        MESSAGE = format('EREV-TRN-001: {column} of %I.%I change only in element "
            f"{value} while {status} is %s',",
            f"                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.{status});",
            "    END IF;",
        ]
    return [*lines, "  END IF;"]


def render_trigger_body(spec: TableTransitions) -> str:
    """The plpgsql body for ``spec``; deterministic, so DG-ARC-07 can compare installed sources.

    Order (DG-KRN-DB-09; D-98 candidate 143 GUARD-TRN-1): the parent-status check; for a spec with
    an editable status the status-pair guard, then the ``editable_while`` early-return (an editable
    row may change any column); the ``frozen_while`` checks; the column-freeze check; the set-once
    checks; for a spec without an editable status the pair guard last (unchanged rendering)."""
    fixed = frozenset(spec.updatable_columns) | (
        {spec.status_column} if spec.status_column is not None else frozenset()
    )
    lines = [
        "",
        "DECLARE",
        "  old_row jsonb := to_jsonb(OLD);",
        "  new_row jsonb := to_jsonb(NEW);",
        "  changed text;",
    ]
    if spec.parent is not None:
        lines.append("  parent_status text;")
    lines.append("BEGIN")
    if spec.parent is not None:
        lines += _parent_lines(spec.parent)
    status = spec.status_column
    if status is not None and spec.editable_while:
        # D-98 candidate 143 GUARD-TRN-1 (DG-KRN-DB-09): the status pairs are enforced in EVERY
        # status — for a spec with an editable status the pair guard precedes the editable
        # early-return, so ``editable_while`` relaxes only the column freeze, never the state
        # machine. A spec without an editable status keeps the guard in its original place (every
        # check runs before RETURN NEW there; its installed function is unchanged).
        lines += _pair_guard_lines(spec, status)
        lines += [
            f"  IF OLD.{status}::text = ANY ({_array(spec.editable_while)}) THEN",
            "    RETURN NEW;",
            "  END IF;",
        ]
    if status is not None and spec.frozen_while:
        lines += _frozen_lines(spec, status)
    lines += [
        "  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed",
        "    FROM jsonb_each(new_row) n",
        f"   WHERE n.key <> ALL ({_array(fixed)})",
        "     AND n.value IS DISTINCT FROM old_row -> n.key;",
        "  IF changed IS NOT NULL THEN",
        "    RAISE EXCEPTION USING ERRCODE = 'P0001',",
        "      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',",
        "                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);",
        "  END IF;",
    ]
    for column in sorted(spec.set_once):
        lines += [
            f"  IF OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM OLD.{column} THEN",
            "    RAISE EXCEPTION USING ERRCODE = 'P0001',",
            f"      MESSAGE = format('EREV-TRN-001: {column} of %I.%I is already set',",
            "                       TG_TABLE_SCHEMA, TG_TABLE_NAME);",
            "  END IF;",
        ]
    if status is not None and not spec.editable_while:
        lines += _pair_guard_lines(spec, status)
    lines += ["  RETURN NEW;", "END", ""]
    return "\n".join(lines)


def _pair_guard_lines(spec: TableTransitions, status: str) -> list[str]:
    """The status-pair guard: a change of ``status`` must be one of the spec's pairs."""
    allowed = frozenset(f"{source}>{target}" for source, target in spec.pairs)
    guard = f"  IF NEW.{status} IS DISTINCT FROM OLD.{status}"
    if allowed:
        pair = f"(OLD.{status}::text || '>' || NEW.{status}::text)"
        guard += f"\n     AND {pair} <> ALL ({_array(allowed)})"
    return [
        guard + " THEN",
        "    RAISE EXCEPTION USING ERRCODE = 'P0001',",
        f"      MESSAGE = format('EREV-TRN-001: {status} of %I.%I cannot change from %s to %s',",
        f"                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.{status}, NEW.{status});",
        "  END IF;",
    ]


def transition_trigger_sql(table: str) -> str:
    """The body of ``erev.tg_<table>__transition()`` generated from ``TRANSITIONS`` (DB-03)."""
    return render_trigger_body(TRANSITIONS[table])


def _error(field: str | None, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=RULE_ID, message=message)


def violations(
    spec: TableTransitions,
    *,
    to_status: str | None,
    set_values: Mapping[str, Any],
    expected_status: str | None,
) -> list[ProblemError]:
    """Every DB-03 violation of a proposed change, in column order; no SQL (DG-SM-02)."""
    errors: list[ProblemError] = []
    if to_status is not None:
        if spec.status_column is None:
            errors.append(_error(None, f"{spec.table} has no status to change."))
        elif (expected_status, to_status) not in spec.pairs:
            errors.append(
                _error(
                    spec.status_column,
                    f"{spec.table} cannot move from {expected_status} to {to_status}.",
                )
            )
    if expected_status is None or expected_status not in spec.editable_while:
        for column in sorted(set_values):
            if column not in spec.updatable_columns:
                errors.append(_error(column, f"{column} of {spec.table} cannot change."))
    if expected_status is not None and expected_status in spec.frozen_while:
        allowed = frozen_columns(spec)
        for column in sorted(set_values):
            if column in spec.updatable_columns and column not in allowed:
                errors.append(
                    _error(
                        column, f"{column} of {spec.table} cannot change while {expected_status}."
                    )
                )
    return errors


def apply(
    session: Session,
    table: str,
    row_id: UUID,
    *,
    to_status: str | None,
    set_values: Mapping[str, Any],
    expected_status: str | None = None,
    expected_row_version: int | None = None,
) -> Mapping[str, Any]:
    """Change one IM-S row along DB-03; returns the updated row.

    Python validation raises 409 ``invalid-transition`` before any SQL. Afterwards the UPDATE is
    conditional on ``expected_status``, ``expected_row_version`` and a NULL value of every set-once
    column it sets: a row that is not visible is 404 ``not-found``, a version mismatch 412
    ``precondition-failed``, and a status mismatch or a set-once column already set 409
    ``invalid-transition``. The database trigger and the grants map through ``from_db_error``.
    """
    spec = TRANSITIONS[table]
    if to_status is None and not set_values:
        raise ValueError("apply needs a status change or column values")
    if to_status is not None and spec.status_column is not None and expected_status is None:
        raise ValueError("a status change names the expected current status")
    errors = violations(
        spec, to_status=to_status, set_values=set_values, expected_status=expected_status
    )
    if errors:
        raise Problem("invalid-transition", errors=errors)

    target = metadata.tables[f"erev.{table}"]
    values = dict(set_values)
    conditions = [target.c.id == row_id]
    if spec.status_column is not None:
        if to_status is not None:
            values[spec.status_column] = to_status
        if expected_status is not None:
            conditions.append(target.c[spec.status_column] == expected_status)
    if expected_row_version is not None:
        conditions.append(target.c.row_version == expected_row_version)
    set_once = sorted(spec.set_once.intersection(set_values))
    conditions += [target.c[column].is_(None) for column in set_once]
    statement = update(target).where(*conditions).values(**values).returning(*target.c)
    try:
        result = cast(CursorResult[Any], session.execute(statement))
        row = result.mappings().one_or_none()
    except DBAPIError as error:
        problem = from_db_error(error)
        if problem is None:
            raise
        raise problem from error
    if row is not None:
        return MappingProxyType(dict(row))
    current = session.execute(select(target).where(target.c.id == row_id)).mappings().one_or_none()
    if current is None:
        raise Problem("not-found")
    if expected_row_version is not None and current["row_version"] != expected_row_version:
        raise Problem("precondition-failed")
    already_set = [column for column in set_once if current[column] is not None]
    if already_set:
        raise Problem(
            "invalid-transition",
            errors=[
                _error(column, f"{column} of {table} is already set.") for column in already_set
            ],
        )
    raise Problem(
        "invalid-transition",
        errors=[_error(spec.status_column, f"{table} is no longer {expected_status}.")],
    )
