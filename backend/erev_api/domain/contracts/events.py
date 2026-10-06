"""Fact-capture events, voids and previews (04 §15.3 API-R-30, §16.3, T-CON-05, T-CON-24, table
3.4-R, table 15.4-A; 05 TZ-03, RCP-18, §3.9; dev-guide DG-CMD-09, DG-KRN-EVT-01, DG-KRN-EVT-02; PRD
IMP-22, IMP-24, IMP-25; 03 REQ-REC-024, REQ-TP-009, REQ-CST-001, REQ-CLS-004, REQ-CLS-005;
BUILD_SPEC CTR-5).

``record_events`` (``POST /contracts/{id}/events``) is a fact-capture command (DG-CMD-09):

1. The contract row is locked; ``If-Match`` must name its head (412 ``precondition-failed``), and
   the caller needs ``event.record`` for the contracting entity (404 otherwise).
2. Every item is validated, collecting the findings (422 ``validation-failed``): a type this route
   records, exactly one of ``effective_date`` and ``effective_at``, the payload as the latest model
   of its type, and one obligation key. ``effective_at`` becomes the date in the contracting
   entity's time zone and stays in the payload as evidence (TZ-03).
3. The batch folds over the stream in order: cumulative delivered net of returns ≤ the quantity
   in force (``PROGRESS_OVER_DELIVERY``, PRD IMP-22; ``quantities_in_force``: the booking as the
   applied modifications and regroups left it — 04 §16.3 rev 1.232), returns ≤ delivered
   (``RETURN_EXCEEDS_DELIVERED``, IMP-24) and credits ≤ billing per ledger subject
   (``REFUND_EXCEEDS_BILLED``, IMP-25), as stage 01 folds them (S01-R-16, S01-R-17). A finding
   answers 422 with nothing appended. One finding needs no stream: a usage report or royalty
   statement whose usage period ends after the event's effective date
   (``USAGE_PERIOD_NOT_ENDED``, PRD IMP-148; 04 §16.3 "The usage period of a report", rev 1.320;
   item USAGE-REPORT-PERIOD-ENDED-1). It is asked where the bounds are, because ``check_bounds``
   is what every channel passes and what the approval of a stored request passes again.
4. Unit of work A appends the events (``events.stream.append_events``: head raised, group dirty).
5. Unit of work B computes the group (``compute_job.compute_group``). More than 200 obligations, or
   more than 30 seconds of engine time before persisting, defer ``CONTRACT_COMPUTE`` and answer 202
   API-S-Job (RCP-18); a refused computation still answers 201 with ``computation.status``.

[J] L4-1-Q-4: the route records the measure, billing, cost, payment, memo and flag types, and
since CTR-7 the Step 1 assessment ``COLLECTIBILITY_ASSESSED`` with its judgement record
(``step1_events``); bookings, voids, holds, modifications, estimates, combination changes, material
rights, openings, manual adjustments and line attribute changes have their own commands (422 rule
``API-R-30``).

Manual events (BUILD_SPEC CTR-6; 03 REQ-DAT-014; PRD BR-REC-01, ACT-09, ACT-10; control CTL-009;
04 §16.3 "Manual events" and T-CON-24, rev 1.194; supervisor ruling R-120 (a)): a request of a
signed-in person — any principal that is not an API client — that holds a ``MANUAL_TYPES`` event
appends nothing. ``_submit`` validates it as an append would, stores it whole as ONE
``event_submission`` under subject ``MANUAL_EVENT`` (``ATTRIBUTE_CHANGE`` when it names
``LINE_ATTRIBUTES_CHANGED``), asks for evidence where REQ-DAT-014 does and attaches the files to
the approval request. The approval of another user checks the stored batch again against the
stream as it stands (``check_stored``: a finding voids the request as stale), appends it as
SYSTEM for the preparer with ``is_manual`` true, and computes the group. An API client's events
are appended directly with ``is_manual`` false (PRD ACT-10); so are a person's events of the
types whose E-03 approval is none, with ``is_manual`` true. A usage report is a manual event
since 04 rev 1.238 (item EVT-USAGE-MANUAL-1): entered by a person it moved revenue with no second
person; its evidence, the usage statement, is offered and not required.

The evidence of a record (item EVT-EVIDENCE-1; the supervisor's ruling of 2026-10-02; 04 §16.3
"Manual events", T-CON-24 and T-PLT-29, rev 1.268). While a request waits its evidence is the
request's: attached to it, read by its readers, and held against a shred by one person while the
submission is submitted, approved or applied (``platform.file_evidence``). The approval locks the
files of the request's live attachments under the submission's locks, before the basis is read
again (``attachments.readable_evidence``): a file that was shredded makes the request stale, and
an event that needs evidence with no readable file left is refused (REQ-DAT-014) while the
request stays pending. It then attaches every readable file to every event it appends (T-PLT-30
subject ``contract_event``), as the SYSTEM principal acting for the preparer, so that whoever
reads the event on its contract opens what supported it; measured before, the Controller, the
Auditor and a second accountant read the event and were answered 404 for its evidence. A direct
append attaches the files its caller sent to the events it appends, as the caller. A live
attachment of a contract event holds its file, whichever road wrote it.

Step 1 (supervisor ruling R-20 on security findings SN-13 / SN-12; 04 rev 1.105; PRD SM-02 rev
1.34): the engine is a function of the events (ENGINE_SPEC Table 2.2-A), so the control is who may
append the events that move a book's status. ``CONTRACT_CRITERIA_MET`` and ``CONTRACT_ACTIVATED``
are appended only by the approved activation (``activation.activate``); this route, its preview
and the void route refuse them for every caller (409 ``invalid-transition``). An assessment names
an ENABLED book of the contracting entity and, once the stream holds a ``CONTRACT_ACTIVATED``,
is dated on or after it (422 ``validation-failed``, the Step 1 rule id ``REQ-POL-008``). The
not-a-contract gate of L4-1-Q-10 — a ``CONTRACT_ACTIVATED`` the route itself appends behind a
not-probable assessment of a DRAFT contract — is appended only when the assessment in force of
EVERY enabled book is not probable AND the dry run of the batch gives the contract the status
NOT_A_CONTRACT in every book the group is computed in, each an enabled book of the contracting
entity; otherwise the assessment is recorded and the contract stays DRAFT, where the only way to a
status is the approved activation. A Step 1 assessment, the gate and the activation events are not
voided through ``request_void``, and an assessment does not ride in an attribute-change submission.

Supervisor rulings R-77 and R-80 (independent review of that fix): the table reads the events in
ENG-06 order, so their DATES are controlled too — once the stream holds a ``CONTRACT_ACTIVATED``
an assessment or a ``SIGNIFICANT_CHANGE_FLAGGED`` is not dated before the latest Step 1 event it
acts on (a back-dated probable assessment cancelled a 606-10-25-5 transition); the criteria-met
re-assessment rests on a COLLECTIBILITY record reviewed after the gate; the enabled books are read
under the shared ``book`` lock; the answer says what became of the gate (``Step1Gate``; API
``step1_gate``), the preview decides it as the append does, and neither an assessment nor a flag
rides in an attribute-change submission.

Supervisor ruling R-102: an assessment cites a REVIEWED record on every channel (b) — a record
cited while its review was pending made that review stale; the record was reviewed at or after
the latest standing booking (c) — a judgement is made on the booking it judges, and
``commands.replace_draft`` voids the assessments of the booking it replaces; and the
criteria-met re-assessment is read per book (a): a probable assessment of a book that is out as
not probable, under a NOT_A_CONTRACT or an ACTIVE header (``step1.Step1Stream.out``), rests on
a COLLECTIBILITY record reviewed after the event that put the book out.

Item STEP1-HOLD-RELEASE-1 (the supervisor's ruling of 2026-10-01; 04 §16.3 (g), T-CON-20
"Judgement holds", rev 1.209): a not-probable assessment of a book that is active by the Step 1
replay is refused unless a significant-change flag stands that no assessment of the book has
followed (422, ``STEP1_CHANGE_NOT_FLAGGED``, PRD IMP-136) — Table 2.2-A would read it and move
nothing; and the unit of work that appends a not-probable assessment also releases, as SYSTEM,
the REQ-POL-010 hold of the ``NOT_A_CONTRACT`` record it cites, which the record's review no
longer releases (``_release_assessed_holds``; the preview computes the same,
``_pending_hold_releases``).

``request_void`` (``POST /events/{id}/request-void``) stores an ``EVENT_VOIDED`` in an
``event_submission`` and submits it under subject ``MANUAL_EVENT`` (T-CON-24; DG-KRN-EVT-02). A
``MANUAL_ADJUSTMENT_APPLIED`` event is not voided through it (item ADJ-VOID-REFUSE-1; supervisor
ruling R-112 (b) (1); 409 ``invalid-transition``, PRD ERR-70): the next computation would take
the adjustment back while its T-SL-05 row stayed ``POSTED`` — two truths.
A posted adjustment is corrected by a further adjustment; the reversal of PRD SM-10 is not built
in 1.0.
``request_preview`` (``POST /contracts/{id}/events/preview``) validates as ``record_events`` and
defers ``CONTRACT_COMPUTE`` in mode ``PREVIEW``, whose ``run_preview`` computes the group in
``DRY_RUN`` with the events pending and answers API-S-ImpactSummary in ``result.summary``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from erev_engine import billing_identity
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, minor_to_decimal
from erev_engine.stages.s01_canonicalize import contract_subject_key
from pydantic import ValidationError
from sqlalchemy import Select, and_, any_, insert, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    SubjectEntities,
    SubjectLifecycle,
    apply_event_submission,
    register_lifecycle,
    reject_event_submission,
    void_event_submission,
)
from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id, transitions
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_hold,
    event_submission,
    gl_account,
    import_row,
    import_row_lineage,
    job,
    legal_entity,
    obligation,
    obligation_version,
    period,
    period_state,
    schedule,
    schedule_line,
)
from erev_api.domain.contracts import bundles, computation, holds, locks, queries, repo
from erev_api.domain.contracts.compute_job import (
    ENGINE_BUDGET_SECONDS,
    OBLIGATION_BUDGET,
    PREVIEW_MODE,
    compute_group,
    defer_compute,
    obligation_count,
)
from erev_api.domain.platform import actors, approval_queries, attachments, file_access
from erev_api.domain.platform.jobs import JOB_COLUMNS, job_outs
from erev_api.domain.reference.books import BOOK_NAMES
from erev_api.domain.ssp import resolution
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalSubjectType,
    BookCode,
    ComputationStatus,
    ContractEventType,
    ContractStatus,
    JobKind,
    JudgementStatus,
    ModificationStatus,
    PrincipalKind,
    Step1GateReason,
)
from erev_api.events import payloads, step1
from erev_api.events.stream import EVT_CODE, STALE_MESSAGE, EventIn, append_events
from erev_api.explain.narratives import format_date
from erev_api.jobs.registry import JobOutcome
from erev_api.money import money_out
from erev_api.periods import POSTABLE_STATES, posting_period, refuse_closed_postings
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut, RefOut
from erev_api.schemas.events import (
    AppendComputationOut,
    EventAppendIn,
    EventAppendItemIn,
    EventComputationOut,
    EventOut,
    EventsAppendedOut,
    EventSourceRowOut,
    EventSubmissionOut,
    EventVoidRequestIn,
    ImpactCatchUpOut,
    ImpactJournalLineOut,
    ImpactObligationAmountOut,
    ImpactRevenuePeriodOut,
    ImpactSummaryOut,
    Step1GateOut,
    SubmissionCreatedOut,
    SubmissionWithdrawIn,
)

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "MANUAL_TYPES",
    "RECORDED_TYPES",
    "Recorded",
    "check_stored",
    "event_outs",
    "events_statement",
    "get_event",
    "get_submission",
    "preparer_entities",
    "record_events",
    "request_preview",
    "request_void",
    "run_preview",
    "submission_outs",
    "submissions_statement",
    "to_events",
    "usage_period_refusal",
    "void_refusals",
    "withdraw_submission",
]

RECORD_PERMISSION: Final = "event.record"
RULE_ROUTE: Final = "API-R-30"
RULE_EFFECTIVE: Final = "API-C-07"
RULE_OBLIGATION: Final = "T-CON-10"
RULE_REASON: Final = "REASON_CODE_NOT_ALLOWED"
OVER_DELIVERY: Final = "PROGRESS_OVER_DELIVERY"
RETURN_EXCEEDS: Final = "RETURN_EXCEEDS_DELIVERED"
REFUND_EXCEEDS: Final = "REFUND_EXCEEDS_BILLED"
# 04 §16.3 "The usage period of a report" and table 15.4-B (rev 1.320; item
# USAGE-REPORT-PERIOD-ENDED-1; the supervisor's rulings of 2026-10-03): a usage report states usage
# that has occurred. PRD §5.5 IMP-148 copy, one sentence for the usage report and the royalty
# statement.
USAGE_PERIOD: Final = "USAGE_PERIOD_NOT_ENDED"
USAGE_PERIOD_MESSAGE: Final = (
    "The usage period {start} to {end} ends after the report's date, {date}. A usage report "
    "states usage that has occurred: end the period on or before {date}."
)
# 04 table 15.4-B (rev 1.45): the S10-R-07 billing-identity refusals at the channel (D-97 (30);
# PR-1.3). The engine keeps its stream behaviour for stored history (ENGINE_SPEC_B S10-R-07).
IDENTITY_REPEATED: Final = "INVOICE_IDENTITY_REPEATED"
STATUS_MISMATCH: Final = "INVOICE_STATUS_UPDATE_MISMATCH"
IDENTITY_REPEATED_MESSAGE: Final = (
    "Invoice {invoice}, line {line} is already recorded on {contract}; a re-issued cancellable "
    "invoice carries a new invoice number or line reference."
)
# PRD §5.5 IMP-94 copy; the obligation variant names the keys (04 table 15.4-B detail member).
AMOUNT_MISMATCH_MESSAGE: Final = (
    "Invoice {invoice}, line {line}: the status update carries {after}, but the original line is "
    "{before}. A status update cannot change the amount; send a credit memo or a new invoice."
)
OBLIGATION_MISMATCH_MESSAGE: Final = (
    "Invoice {invoice}, line {line}: the status update names obligation {after}, but the original "
    "line is on {before}. A status update cannot move the line; send a credit memo of the original "
    "line and a new invoice."
)
RECORD_ACTION: Final = "contract.record_events"
# The audit action of a refused preview (04 §16.10 rev 1.295): a preview that is taken writes
# ``job.start``, nothing of its own.
PREVIEW_ACTION: Final = "contract.preview_events"
VOID_ACTION: Final = "event_submission.request_void"
WITHDRAW_ACTION: Final = "event_submission.withdraw"
CONTRACT_OBJECT: Final = "contract"
SUBMISSION_OBJECT: Final = "event_submission"
CONTRACT_HREF: Final = "/api/v1/contracts/{contract_id}"
DRY_RUN: Final = "DRY_RUN"
REVENUE: Final = "REVENUE"
SUMMARY_PERIODS: Final = 6  # API-S-ImpactSummary revenue_by_period: six periods
# CV-47 (a): the members of a ``MEMO_UPDATED`` payload a writer can supply; the presence set
# ``named`` is derived from the submitted members and a contradicting client value is a finding
# (04 §16.3).
MEMO_MEMBERS: Final = payloads.MEMO_UPDATED_MEMBERS
RULE_MEMO_NAMED: Final = "CV-47"
MEMO_NAMED: Final = (
    "payload.named must list exactly the members submitted in this payload (the presence set is "
    "derived by the server; a submitted null clears a memo or empties the attribute set)."
)
# [J] L4-1-Q-4: the E-03 types this route records directly.
RECORDED_TYPES: Final = frozenset(
    {
        ContractEventType.DELIVERY_RECORDED,
        ContractEventType.RETURN_RECORDED,
        ContractEventType.PROGRESS_RECORDED,
        ContractEventType.MILESTONE_ACHIEVED,
        ContractEventType.USAGE_REPORTED,
        ContractEventType.COST_INCURRED,
        ContractEventType.BILLING_RECORDED,
        ContractEventType.CREDIT_MEMO_RECORDED,
        ContractEventType.PAYMENT_RECEIVED,
        ContractEventType.PRE_STANDARD_REVENUE_RECORDED,
        ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
        ContractEventType.MEMO_UPDATED,
        ContractEventType.COLLECTIBILITY_ASSESSED,
    }
)
# BUILD_SPEC CTR-6 (04 E-03 "MANUAL_EVENT when manual"; PRD BR-REC-01; 03 REQ-DAT-014): the types a
# signed-in person's request does not append — another user approves them first. A usage report
# is one of them since 04 rev 1.238 (item EVT-USAGE-MANUAL-1; PRD BR-REC-01 rev 1.166): measured,
# 50,000 calls rated 5,000.00 entered by one person posted the revenue with the append.
MANUAL_TYPES: Final = frozenset(
    {
        ContractEventType.DELIVERY_RECORDED,
        ContractEventType.RETURN_RECORDED,
        ContractEventType.PROGRESS_RECORDED,
        ContractEventType.MILESTONE_ACHIEVED,
        ContractEventType.USAGE_REPORTED,
        ContractEventType.COST_INCURRED,
    }
)
# The words of a ``MANUAL_EVENT`` request's summary, in E-03 order.
MANUAL_LABELS: Final[Mapping[ContractEventType, str]] = {
    ContractEventType.DELIVERY_RECORDED: "delivery",
    ContractEventType.PROGRESS_RECORDED: "progress",
    ContractEventType.MILESTONE_ACHIEVED: "milestone",
    ContractEventType.USAGE_REPORTED: "usage",
    ContractEventType.COST_INCURRED: "cost",
    ContractEventType.RETURN_RECORDED: "return",
}
# 04 §16.3 ``evidence_file_ids`` (rev 1.194; SCREENS §4.9.3): the manual events that carry evidence
# — progress, milestone and cost events, and a delivery recorded on acceptance. A usage report is
# not among them: its evidence is offered, not required (rev 1.238).
EVIDENCE_TYPES: Final = frozenset(
    {
        ContractEventType.PROGRESS_RECORDED,
        ContractEventType.MILESTONE_ACHIEVED,
        ContractEventType.COST_INCURRED,
    }
)
ACCEPTANCE_TRIGGER: Final = "ACCEPTANCE"
RULE_EVIDENCE: Final = "REQ-DAT-014"
EVIDENCE_REQUIRED: Final = "Attach at least one evidence file."
RULE_FILE: Final = "T-PLT-29"
# 04 T-PLT-30: the evidence of a request that waits for approval is attached to the request.
EVIDENCE_SUBJECT: Final = "approval_request"
# 04 T-PLT-30 (rev 1.268; item EVT-EVIDENCE-1): the evidence of appended events is attached to
# each of them — by the approval of their request, or by the caller of a direct append.
EVENT_SUBJECT: Final = "contract_event"
# REQ-DAT-014 at the approval (04 T-CON-24 rev 1.268): the person who reads this sentence is the
# approver, who cannot attach to another person's request — so it says what she can do and
# names the preparer's two roads, each of which exists: to attach to the pending request (04
# T-PLT-30, ruling R-100 (b): ``POST /attachments`` as its requester; no screen offers it yet)
# or to withdraw it (the approval pane's own action) and record the events again.
# ``EVIDENCE_REQUIRED`` tells the preparer what to do. The approval pane shows a refusal's detail.
EVIDENCE_GONE: Final = (
    "This request no longer has an evidence file attached. Reject it, or ask the preparer to "
    "attach a file to it or withdraw it."
)
# CTR-7 (L4-1-Q-10, narrowed by ruling R-20): the Step 1 type this route records, with a judgement
# record of the contract, for an enabled book of the contracting entity.
STEP1_TYPES: Final = step1.ASSESSMENT_TYPES
# Ruling R-77 (1): the Step 1 events this route records whose DATE decides what Table 2.2-A reads —
# the assessment and the significant-change flag (REQ-CON-004).
STEP1_DATED_TYPES: Final = step1.RECORDED_TYPES
# Ruling R-20 (c) (04 E-03 rev 1.105; PRD SM-02): the events that move a book into recognition are
# appended by the approved activation alone.
ACTIVATION_TYPES: Final = step1.ACTIVATION_TYPES
ACTIVATION_ONLY: Final = step1.ACTIVATION_ONLY
# The Step 1 events whose void would replay the gate or the activation under another approval.
STATUS_TYPES: Final = step1.STATUS_TYPES
ASSESSMENT_NOT_VOIDABLE: Final = step1.ASSESSMENT_NOT_VOIDABLE
ACTIVATION_NOT_VOIDABLE: Final = step1.ACTIVATION_NOT_VOIDABLE
STEP1_OWN_REQUEST: Final = step1.OWN_REQUEST
RULE_STEP1: Final = "REQ-POL-008"
# Ruling R-20 (a) and its family (04 §16.3 rev 1.105): refusals of the Step 1 rule id.
BOOK_NOT_ENABLED: Final = "Book {book} is not enabled for {entity}."
# Ruling R-77 (1): an event dated before the latest Step 1 event it would be read before.
# Supervisor ruling R-118 (e) (the copy point of lane WEB-QA): the sentences say "entry" — an
# activation, a review or an assessment, without naming a gate —, the assessment's sentence
# names the book by its label, and every date of the family reads DD MMM YYYY (DS-FMT-16;
# ``_day``).
# The sentence that named "the contract's activation event" is gone: the first
# ``CONTRACT_ACTIVATED`` is itself a Step 1 entry of every book (``step1.read``), so this
# limit is never earlier than its date and refuses everything that sentence refused.
ASSESSMENT_BEFORE_STEP1: Final = (
    "This assessment is dated before the contract's latest Step 1 entry in {book_label} "
    "({date}). Date it on or after that date."
)
FLAG_BEFORE_STEP1: Final = (
    "This significant-change flag is dated before the contract's latest Step 1 entry ({date}). "
    "Date it on or after that date."
)
STEP1_TOPICS: Final = step1.PROBABLE_TOPICS | step1.NOT_PROBABLE_TOPICS
NO_RECORD: Final = "No judgement record of this contract has this id."
WRONG_TOPIC: Final = "Use a judgement record of topic {topics}."
WRONG_BOOK: Final = "The judgement record applies to another book."
# Ruling R-102 (b): an assessment cites a REVIEWED record (before it: submitted or reviewed).
NOT_REVIEWED: Final = "Use a reviewed judgement record."
# Ruling R-102 (c): a Step 1 judgement is made on the booking it judges.
REVIEWED_BEFORE_BOOKING: Final = (
    "Use a judgement record reviewed after the draft was last replaced."
)
# Ruling R-77 (3): criteria are met on a new judgement, reviewed after the not-a-contract gate.
REVIEWED_BEFORE_GATE: Final = (
    "Use a judgement record reviewed after the contract was assessed as not a contract."
)
# Item STEP1-CITE-LATEST-1 (the supervisor's ruling of 2026-10-02): an assessment cites the
# newest reviewed Step 1 record of its subject and book — COLLECTIBILITY and NOT_A_CONTRACT are
# one judgement with two outcomes, and a later review of either overtakes the other
# (``step1.overtaken``) — and, where a significant-change flag stands, a record reviewed at or
# after the time the flag was recorded: a review made before it did not look at the change.
RECORD_OVERTAKEN: Final = (
    "This judgement record was overtaken by the review of judgement record {judgement_no}. Use "
    "the latest reviewed Step 1 record."
)
REVIEWED_BEFORE_FLAG: Final = (
    "Use a judgement record reviewed after the significant change was flagged."
)
STEP1_GATE_DETAIL: Final = "Step 1 criteria not met (606-10-25-1)."
# Rulings R-82 (c) and R-84 (a): a Step 1 judgement is not dated ahead of the day it is recorded —
# nor, for a contract booked ahead of its inception, ahead of that inception.
STEP1_AHEAD: Final = (
    "This {what} is dated after {date}, the later of today and the contract's inception date. "
    "Date it on or before that date."
)
# 04 table 3.4-R: the reasons of ``POST /events/{id}/request-void``.
VOID_REASONS: Final = frozenset(
    {
        "DUPLICATE",
        "CREATED_IN_ERROR",
        "CUSTOMER_CANCELLED",
        "DATA_CORRECTION",
        "ESTIMATE_CORRECTION",
        "OTHER",
    }
)
REASON_LABELS: Final[Mapping[str, str]] = {  # 04 table 3.4-R labels
    "ERROR_CORRECTION": "Error correction",
    "LATE_SOURCE_DATA": "Late source data",
    "AUDIT_ADJUSTMENT": "Audit adjustment",
    "CLOSE_RESTARTED": "Close restarted",
    "DATA_CORRECTION_PENDING": "Data correction pending",
}
BOOKED: Final = ContractEventType.CONTRACT_BOOKED.value
VOIDED: Final = ContractEventType.EVENT_VOIDED.value
OWN_COMMAND: Final = "Record {event_type} through its own command."
ONE_DATE: Final = "Send effective_date or effective_at, not both."
NO_DATE: Final = "Send effective_date or effective_at."
TWO_KEYS: Final = "The item's obligation_key differs from the payload's."
NOT_VOIDABLE: Final = "This event is a void or is already voided."
# Item ADJ-VOID-REFUSE-1 (supervisor ruling R-112 (b) (1); PRD ERR-70, a convention row of
# ``invalid-transition`` under the rule id of PRD SM-10): the event of a posted manual adjustment
# (04 T-SL-05 ``applied_event_id``).
ADJUSTMENT_APPLIED: Final = ContractEventType.MANUAL_ADJUSTMENT_APPLIED.value
RULE_ADJUSTMENT: Final = "SM-10"
ADJUSTMENT_NOT_VOIDABLE: Final = (
    "A posted manual adjustment cannot be voided. Correct it with a further adjustment."
)
# 04 §16.3 "Voids on this route" (rev 1.231; item EVT-VOID-OWN-COMMANDS-1; dev-guide DG-KRN-EVT-02
# rev 1.222): a void undoes a FACT that was captured wrongly — the twelve fact-capture types this
# route records. An event of another type is the trace of a command with its own object, preview
# and approval; its void would undo that command under one ``event.approve`` step while the
# command's object still read applied (measured: the approved void of an applied
# ``CONTRACT_AMENDED`` took K-02's allocation back while the modification read ``APPLIED``).
VOIDABLE_TYPES: Final = RECORDED_TYPES - STEP1_TYPES
OWN_COMMAND_VOIDS: Final[Mapping[ContractEventType, str]] = {
    ContractEventType.CONTRACT_BOOKED: (
        "A booking is not voided as an event. Replace the draft, or void the contract."
    ),
    ContractEventType.CONTRACT_AMENDED: (
        "An applied modification is not voided as an event. Record a modification that reverses it."
    ),
    ContractEventType.ESTIMATE_CHANGED: (
        "An applied estimate change is not voided as an event. Submit a new estimate version."
    ),
    ContractEventType.REGROUPED: (
        "A regroup is not voided as an event. Regroup the obligations back."
    ),
    ContractEventType.CONTRACT_VOIDED: (
        "A contract void is not voided as an event. A voided contract stays voided."
    ),
    ContractEventType.COMBINATION_CHANGED: (
        "A combination decision is not voided as an event. Change the combination with a new "
        "combination request."
    ),
    ContractEventType.HOLD_APPLIED: "A hold is not voided as an event. Release the hold.",
    ContractEventType.HOLD_RELEASED: (
        "The release of a hold is not voided as an event. Apply the hold again."
    ),
    ContractEventType.LINE_ATTRIBUTES_CHANGED: (
        "An attribute change is not voided as an event. Record a further attribute change, or "
        "request an SSP override."
    ),
    # No command of 1.0 records a termination or an option event, and an opening balance is
    # established by its import or its migration batch and stands with its contract: nothing
    # undoes these, and the sentences say so.
    ContractEventType.CONTRACT_TERMINATED: (
        "A termination is not voided as an event. No command undoes it."
    ),
    ContractEventType.MATERIAL_RIGHT_EXERCISED: (
        "An option event is not voided as an event. No command undoes it."
    ),
    ContractEventType.MATERIAL_RIGHT_EXPIRED: (
        "An option event is not voided as an event. No command undoes it."
    ),
    ContractEventType.OPENING_BALANCE_ESTABLISHED: (
        "An opening balance is not voided as an event. No command undoes it."
    ),
}
TYPE_NOT_VOIDED: Final = "An event of this type is not voided as an event."

type Origin = Literal["API", "UI", "IMPORT", "ADAPTER", "SYSTEM", "MIGRATION"]


@dataclass(frozen=True, slots=True)
class Recorded:
    """``record_events``: the 201 body, the 202 job of a deferred computation, or the 201 event
    submission of an append that needs approval (04 §16.3; BUILD_SPEC CTR-10)."""

    appended: EventsAppendedOut | None
    job: JobOut | None
    submission: SubmissionCreatedOut | None = None


def _error(field: str, rule_id: str | None, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _failed(errors: Sequence[ProblemError]) -> Problem:
    detail = errors[0].message if len(errors) == 1 else f"{len(errors)} fields need attention."
    return Problem("validation-failed", detail, errors=errors)


def _origin(uow: UnitOfWork) -> Origin:
    return "API" if uow.principal.kind is PrincipalKind.API_CLIENT else "UI"


def _quantity(value: Decimal | Fraction) -> str:
    return format_exact(Fraction(value))


# --- validation ----------------------------------------------------------------------------------


def _payload_errors(index: int, error: ValidationError) -> list[ProblemError]:
    found: list[ProblemError] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        ctx = item.get("ctx")
        rule_id = ctx.get("rule_id") if isinstance(ctx, Mapping) else None
        field = f"events.{index}.payload" + (f".{location}" if location else "")
        found.append(
            _error(field, rule_id if isinstance(rule_id, str) else None, str(item.get("msg", "")))
        )
    return found


def _effective(
    index: int, item: EventAppendItemIn, zone: ZoneInfo, errors: list[ProblemError]
) -> date | None:
    """TZ-03: ``effective_at`` converted once to the contracting entity's date."""
    if item.effective_date is not None and item.effective_at is not None:
        errors.append(_error(f"events.{index}.effective_at", RULE_EFFECTIVE, ONE_DATE))
        return None
    if item.effective_at is not None:
        return item.effective_at.astimezone(zone).date()
    if item.effective_date is None:
        errors.append(_error(f"events.{index}.effective_date", RULE_EFFECTIVE, NO_DATE))
    return item.effective_date


def to_events(
    items: Sequence[EventAppendItemIn],
    *,
    time_zone: str,
    is_manual: bool,
    allowed: frozenset[ContractEventType] = RECORDED_TYPES,
) -> list[EventIn]:
    """Validate API-S-EventAppend items as ``EventIn``, collecting every finding (422)."""
    zone = ZoneInfo(time_zone)
    errors: list[ProblemError] = []
    found: list[EventIn] = []
    for index, item in enumerate(items):
        event_type = item.event_type
        if event_type not in allowed:
            errors.append(
                _error(
                    f"events.{index}.event_type",
                    RULE_ROUTE,
                    OWN_COMMAND.format(event_type=event_type.value),
                )
            )
            continue
        effective = _effective(index, item, zone, errors)
        data = dict(item.payload)
        if item.effective_at is not None:
            data["effective_at"] = item.effective_at.isoformat()
        try:
            payload = payloads.parse_payload(
                event_type, payloads.LATEST_SCHEMA_VERSION[event_type], data
            )
        except ValidationError as error:
            errors += _payload_errors(index, error)
            continue
        if event_type is ContractEventType.MEMO_UPDATED:
            # CV-47 (a) / 04 §16.3: the presence set is server-derived from the members the
            # client actually submitted (a submitted null clears); a client-supplied ``named``
            # must equal it — it never overrides the submitted members.
            derived = tuple(name for name in MEMO_MEMBERS if name in data)
            supplied = data.get("named")
            if supplied is not None and tuple(supplied) != derived:
                errors.append(_error(f"events.{index}.payload.named", RULE_MEMO_NAMED, MEMO_NAMED))
                continue
            payload = payload.model_copy(update={"named": derived})
        named = getattr(payload, "obligation_key", None)
        if named is not None and item.obligation_key is not None and named != item.obligation_key:
            errors.append(_error(f"events.{index}.obligation_key", RULE_OBLIGATION, TWO_KEYS))
            continue
        key = named or item.obligation_key
        if effective is None:
            continue
        found.append(
            EventIn(
                event_type=event_type,
                effective_date=effective,
                payload=payload,
                obligation_keys=() if key is None else (key,),
                is_manual=is_manual,
            )
        )
    if errors:
        raise _failed(errors)
    return found


@dataclass(frozen=True, slots=True)
class FirstLine:
    """The first-seen line of a billing identity (``invoice_number``, ``line_external_id``) at
    contract scope: what a later status update of that identity must repeat (S10-R-07; D-91)."""

    amount: Decimal
    currency: str
    obligation_key: str | None


@dataclass(frozen=True, slots=True)
class PayloadView:
    """A pending ``BILLING_RECORDED`` payload read as the kernel's ``BillingEvent``, so the channel
    takes the ``is_cancellable`` literal rule from its one home, ``erev_engine.billing_identity``
    (D-91 "One identity rule, one home"). Only ``payload`` carries information here."""

    payload: Mapping[str, object]
    event_key: str = ""
    contract_key: str = ""
    event_type: str = billing_identity.BILLING_RECORDED
    effective_date: date = date.min

    @property
    def order_key(self) -> tuple[date, int, str]:
        return (self.effective_date, 0, self.event_key)


@dataclass(slots=True)
class _Ledger:
    """Stage 01 ledger totals of one contract (S01-R-16, S01-R-17) beside the quantities in force
    (``quantities_in_force``), and the first line of every billing identity of its stream
    (S10-R-07; 04 table 15.4-B rev 1.45)."""

    external_id: str
    currency: str
    in_force: dict[str, Decimal]
    ended: frozenset[str]
    products: dict[str, str]
    delivered: defaultdict[str, Decimal]
    returned: defaultdict[str, Decimal]
    billed: defaultdict[str, Decimal]
    credited: defaultdict[str, Decimal]
    lines: dict[tuple[str, str], FirstLine]
    # D-98 103: the parity VC-line obligation keys (S03-R-18; empty outside LEGACY_PARITY) and the
    # obligation id → key map that resolves a stored event's single obligation (ledger.subject_of).
    vc: frozenset[str]
    keys_by_id: dict[str, str]


def _amount(payload: Mapping[str, Any], name: str) -> Decimal:
    value = payload.get(name)
    if isinstance(value, Mapping):
        value = value.get("amount")
    return Decimal(str(value)) if value is not None else Decimal(0)


PARITY_PRESET: Final = "LEGACY_PARITY"
VC_STRATIFICATION: Final = "VC"
# S03-R-18 / stage 01 ``_ADDED_LINE_MEMBERS``: the boundary payload members that add lines.
ADDED_LINE_MEMBERS: Final[Mapping[str, str]] = {
    "CONTRACT_AMENDED": "lines",
    "MATERIAL_RIGHT_EXERCISED": "new_lines",
}


def _vc_keys(lines: Iterable[Mapping[str, Any]]) -> set[str]:
    """The obligation keys of VC-stratified lines (stage 01 ``_vc_lines``)."""
    return {
        str(line["obligation_key"])
        for line in lines
        if isinstance(line, Mapping)
        and line.get("obligation_key") is not None
        and str(line.get("stratification") or "") == VC_STRATIFICATION
    }


def _added_lines(event_type: str, payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    member = ADDED_LINE_MEMBERS.get(event_type)
    lines = () if member is None else payload.get(member, ())
    return lines if isinstance(lines, list | tuple) else ()


AMENDED: Final = ContractEventType.CONTRACT_AMENDED.value
REGROUPED: Final = ContractEventType.REGROUPED.value
LINE_ADD: Final = "ADD"
LINE_REMOVE: Final = "REMOVE"
MOVED_IN: Final = "IN"
MOVED_OUT: Final = "OUT"


@dataclass(frozen=True, slots=True)
class InForce:
    """The terms a delivery is checked against (04 §16.3 "The quantity a delivery is checked
    against", rev 1.232): per obligation key the quantity in force and the product, and the keys
    that take no further delivery."""

    quantities: Mapping[str, Decimal]
    products: Mapping[str, str]
    ended: frozenset[str]


def _event_kind(row: Mapping[str, Any]) -> str:
    return str(getattr(row["event_type"], "value", row["event_type"]))


def _line_items(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def quantities_in_force(live: Sequence[Mapping[str, Any]]) -> InForce:
    """The quantity in force of every obligation of one contract, folded from its live events —
    the stream in its order without the events a void names (item EVT-BOUND-AFTER-MOD-1; 03
    REQ-REC-024 "unless a modification is processed first"; ENGINE_SPEC table 0.8-A
    ``PROGRESS_OVER_DELIVERY``: "the contracted quantity in force"). Pure.

    1. The lines of the last ``CONTRACT_BOOKED``.
    2. Every ``REGROUPED``, wherever it stands in the stream, as bundle assembly moves the lines
       (``bundles._apply_regroups``; S06-R-27): an ``OUT`` event takes its keys away; an ``IN``
       event gives each moved line its booked quantity unless the booking names the key itself.
    3. In stream order, the lines of every ``CONTRACT_AMENDED`` after that booking, as the legacy
       progress import folds them (``imports.legacy_v1.progress._amended``; S06-R-08): an ``ADD``
       line starts its obligation at its ``quantity_delta`` with its product, a ``CHANGE`` line
       adds its ``quantity_delta``, and a ``REMOVE`` line ends the obligation (S06-R-21: the line
       removes the remaining quantity or term).

    ``ended`` holds the keys that take no further delivery: removed, moved out, or brought from
    above zero to zero or below. A key whose quantity was never above zero (a line that states no
    unit quantity) and a key whose quantity no event states are not bound, as before. The two
    types that no command of 1.0 records — ``CONTRACT_TERMINATED``, ``MATERIAL_RIGHT_EXERCISED``
    — change nothing here."""
    quantities: dict[str, Decimal] = {}
    products: dict[str, str] = {}
    removed: set[str] = set()
    stated: set[str] = set()  # the keys whose quantity was above zero at some point

    def state(key: str, quantity: Decimal, product: object) -> None:
        quantities[key] = quantity
        if product is not None:
            products[key] = str(product)
        if quantity > 0:
            stated.add(key)

    booked_at = max((i for i, row in enumerate(live) if _event_kind(row) == BOOKED), default=None)
    if booked_at is not None:
        for line in _line_items(live[booked_at]["payload"].get("lines")):
            state(str(line["obligation_key"]), Decimal(str(line["quantity"])), line["product_code"])
    for row in live:
        if _event_kind(row) != REGROUPED:
            continue
        payload = row["payload"]
        keys = [str(key) for key in payload.get("obligation_keys") or ()]
        if payload.get("direction") == MOVED_OUT:
            for key in keys:
                quantities.pop(key, None)
                removed.add(key)
        elif payload.get("direction") == MOVED_IN:
            removed.difference_update(keys)
            for line in _line_items(payload.get("lines")):
                key = str(line["obligation_key"])
                if key not in quantities:
                    state(key, Decimal(str(line["quantity"])), line.get("product_code"))
    for row in live[0 if booked_at is None else booked_at + 1 :]:
        if _event_kind(row) != AMENDED:
            continue
        for line in _line_items(row["payload"].get("lines")):
            key = str(line["obligation_key"])
            delta = Decimal(str(line.get("quantity_delta") or 0))
            action = line.get("action")
            if action == LINE_ADD:
                removed.discard(key)
                state(key, delta, line.get("product_code"))
            elif action == LINE_REMOVE:
                removed.add(key)
            elif key in quantities:
                state(key, quantities[key] + delta, None)
    exhausted = {key for key in stated if key in quantities and quantities[key] <= 0}
    return InForce(quantities, products, frozenset(removed | exhausted))


def _ledger(
    session: Session,
    contract_row: Mapping[str, Any],
    *,
    known_at: datetime,
    pending: Sequence[EventIn] = (),
) -> _Ledger:
    """The stage 01 view of the contract's live stream at the channel (D-98 103: the same subjects,
    the same VC scope under the effective ``LEGACY_PARITY`` preset, the same cover rule), with the
    quantities in force a delivery is checked against (``quantities_in_force``)."""
    contract_id = UUID(str(contract_row["id"]))
    stream = repo.stream(session, contract_id)
    voided = {row["supersedes_event_id"] for row in stream if row["supersedes_event_id"]}
    live = [row for row in stream if row["id"] not in voided]
    bookings = [row for row in live if _event_kind(row) == BOOKED]
    terms = quantities_in_force(live)
    vc: set[str] = set()
    parity = resolution.tenant_preset(session, known_at=known_at) == PARITY_PRESET
    if bookings and parity:
        vc |= _vc_keys(bookings[-1]["payload"].get("lines", ()))
    if parity:
        for row in live:
            kind = str(getattr(row["event_type"], "value", row["event_type"]))
            vc |= _vc_keys(_added_lines(kind, row["payload"]))
        for event in pending:
            vc |= _vc_keys(
                _added_lines(event.event_type.value, payloads.payload_json(event.payload))
            )
    keys_by_id = {
        str(row["id"]): str(row["obligation_key"]) for row in repo.obligations(session, contract_id)
    }
    ledger = _Ledger(
        external_id=str(contract_row["external_id"]),
        currency=str(contract_row["transaction_currency"]).strip(),
        in_force=dict(terms.quantities),
        ended=terms.ended,
        products=dict(terms.products),
        delivered=defaultdict(Decimal),
        returned=defaultdict(Decimal),
        billed=defaultdict(Decimal),
        credited=defaultdict(Decimal),
        lines={},
        vc=frozenset(vc),
        keys_by_id=keys_by_id,
    )
    for row in live:
        kind = str(getattr(row["event_type"], "value", row["event_type"]))
        keys = tuple(keys_by_id.get(str(value), "") for value in (row["obligation_ids"] or ()))
        _fold(ledger, kind, row["payload"], _subject_of(row["payload"], keys))
    return ledger


def _member_text(payload: Mapping[str, Any], member: str) -> str:
    value = payload.get(member)
    return "" if value is None else str(value)


def line_identity(payload: Mapping[str, Any]) -> tuple[str, str]:
    """(``invoice_number``, ``line_external_id``) of a ``BILLING_RECORDED`` payload; the contract
    is the ledger's scope (ENGINE_SPEC_B S10-R-07: the ``obligation_key`` is not part of it)."""
    return (_member_text(payload, "invoice_number"), _member_text(payload, "line_external_id"))


def first_line(payload: Mapping[str, Any]) -> FirstLine:
    """What the first line of an identity fixes for its status updates."""
    money = payload.get("amount")
    currency = ""
    if isinstance(money, Mapping) and money.get("currency") is not None:
        currency = str(money["currency"]).strip()
    key = _member_text(payload, "obligation_key")
    return FirstLine(
        amount=_amount(payload, "amount"), currency=currency, obligation_key=key or None
    )


def repeat_finding(first: FirstLine, payload: Mapping[str, Any]) -> tuple[str, str] | None:
    """The refusal a repeated identity earns at the channel, as (payload member, rule id), or None
    when the repeat is a valid status update (S10-R-07; 04 table 15.4-B rev 1.45; D-97 (30)).

    A repeat flagged cancellable (the kernel's literal rule) is ``INVOICE_IDENTITY_REPEATED``: a
    re-issued cancellable invoice carries a new identity. Otherwise the repeat is a status update,
    which must keep the first line's amount and may not move it between two non-null obligation
    keys (``INVOICE_STATUS_UPDATE_MISMATCH``); a null key on either side preserves the attribution.
    """
    if billing_identity.is_cancellable(PayloadView(payload)):
        return ("invoice_number", IDENTITY_REPEATED)
    if _amount(payload, "amount") != first.amount:
        return ("amount", STATUS_MISMATCH)
    key = _member_text(payload, "obligation_key") or None
    if key is not None and first.obligation_key is not None and key != first.obligation_key:
        return ("obligation_key", STATUS_MISMATCH)
    return None


def _subject_of(payload: Mapping[str, Any], obligation_keys: Sequence[str]) -> str:
    """The ledger subject as stage 01 derives it (``ledger.subject_of``): the payload's
    ``obligation_key``, else the event's single obligation; ``""`` is the contract itself
    (unreferenced billing and credits)."""
    key = payload.get("obligation_key")
    if key is not None and str(key) != "":
        return str(key)
    named = [item for item in obligation_keys if item]
    return named[0] if len(named) == 1 else ""


def _fold(ledger: _Ledger, event_type: str, payload: Mapping[str, Any], subject: str) -> None:
    match event_type:
        case "DELIVERY_RECORDED":
            ledger.delivered[subject] += Decimal(str(payload["quantity"]))
        case "RETURN_RECORDED":
            ledger.returned[subject] += Decimal(str(payload["quantity"]))
        case "BILLING_RECORDED":
            identity = line_identity(payload)
            # Kept lines only (billing_identity.kept_lines): the first-seen event of an identity and
            # every cancellable repeat add billing; a status update moves nothing here either
            # (S10-R-07; 04 §16.3 CREDIT_MEMO_RECORDED note; VOID-3a).
            if identity not in ledger.lines or billing_identity.is_cancellable(
                PayloadView(payload)
            ):
                ledger.billed[subject] += _amount(payload, "amount")
            ledger.lines.setdefault(identity, first_line(payload))
        case "CREDIT_MEMO_RECORDED":
            ledger.credited[subject] += _amount(payload, "amount")
        case _:
            pass


def _at(bucket: Mapping[str, Decimal], key: str) -> Decimal:
    """A ledger read that never creates a bucket (the maps are defaultdicts for the folds only;
    Codex packet 1150 ``credit_100_credited``: a cover lookup must not leave an empty-string
    contract bucket behind)."""
    return bucket.get(key, Decimal(0))


def _money_text(value: Decimal, currency: str) -> str:
    return money_out(value, currency, ISO_4217).amount


def _named_obligation(ledger: _Ledger, key: str) -> str:
    product = ledger.products.get(key)
    return f"{ledger.external_id}, obligation {key}" + ("" if product is None else f" ({product})")


def _bound_finding(ledger: _Ledger, index: int, event: EventIn) -> ProblemError | None:
    """The stage 01 bound the event would break after the earlier ones (IMP-22 to IMP-25)."""
    body = payloads.payload_json(event.payload)
    subject = _subject_of(body, event.obligation_keys)
    field = f"events.{index}.payload"
    match event.event_type:
        case ContractEventType.DELIVERY_RECORDED:
            requested = Decimal(str(body["quantity"]))
            net = _at(ledger.delivered, subject) - _at(ledger.returned, subject)
            in_force = ledger.in_force.get(subject)
            # An ended obligation — removed, moved out, or reduced to nothing — takes no further
            # delivery; the others are bound by the quantity in force (04 §16.3 rev 1.232).
            ended = subject in ledger.ended
            if ended or (in_force is not None and 0 < in_force < net + requested):
                remaining = Decimal(0) if ended or in_force is None else in_force - net
                message = (
                    f"{_named_obligation(ledger, subject)}: requested {_quantity(requested)}, "
                    f"remaining {_quantity(remaining)}."
                )
                return _error(f"{field}.quantity", OVER_DELIVERY, message)
        case ContractEventType.RETURN_RECORDED:
            requested = Decimal(str(body["quantity"]))
            if _at(ledger.returned, subject) + requested > _at(ledger.delivered, subject):
                message = (
                    f"Return of {_quantity(requested)} units exceeds the "
                    f"{_quantity(_at(ledger.delivered, subject) - _at(ledger.returned, subject))} "
                    "units "
                    f"delivered on {_named_obligation(ledger, subject)}."
                )
                return _error(f"{field}.quantity", RETURN_EXCEEDS, message)
        case ContractEventType.BILLING_RECORDED:
            identity = line_identity(body)
            first = ledger.lines.get(identity)
            refusal = None if first is None else repeat_finding(first, body)
            if first is not None and refusal is not None:
                member, rule_id = refusal
                names = {
                    "invoice": identity[0],
                    "line": identity[1],
                    "contract": ledger.external_id,
                }
                if rule_id == IDENTITY_REPEATED:
                    message = IDENTITY_REPEATED_MESSAGE.format(**names)
                elif member == "amount":
                    currency = first.currency or ledger.currency
                    message = AMOUNT_MISMATCH_MESSAGE.format(
                        **names,
                        before=f"{_money_text(first.amount, currency)} {currency}",
                        after=f"{_money_text(_amount(body, 'amount'), currency)} {currency}",
                    )
                else:
                    message = OBLIGATION_MISMATCH_MESSAGE.format(
                        **names, before=first.obligation_key, after=_member_text(body, member)
                    )
                return _error(f"{field}.{member}", rule_id, message)
        case ContractEventType.CREDIT_MEMO_RECORDED if subject not in ledger.vc:
            # D-98 103 / D-87 L6-5-Q-15 (stage 01 ledger.build): an unreferenced credit draws on the
            # whole non-VC stream; a referenced one on its obligation's billing, then on the
            # unreferenced billing not yet drawn (``referenced_cover``); a parity VC line is not
            # checked and stays out of the stream.
            requested = _amount(body, "amount")
            if subject == "":
                billed = sum(
                    (ledger.billed[key] for key in ledger.billed if key not in ledger.vc),
                    Decimal(0),
                )
                credited = sum(
                    (ledger.credited[key] for key in ledger.credited if key not in ledger.vc),
                    Decimal(0),
                )
            else:
                billed = _at(ledger.billed, subject) + _referenced_cover(ledger, subject)
                credited = _at(ledger.credited, subject)
            if credited + requested > billed:
                target = ledger.external_id if subject == "" else _named_obligation(ledger, subject)
                message = (
                    f"Credit of {_money_text(requested, ledger.currency)} exceeds the "
                    f"{_money_text(billed - credited, ledger.currency)} billed on {target}."
                )
                return _error(f"{field}.amount", REFUND_EXCEEDS, message)
        case _:
            pass
    _fold(ledger, event.event_type.value, body, subject)
    return None


def _referenced_cover(ledger: _Ledger, subject: str) -> Decimal:
    """The unreferenced billing a referenced credit of ``subject`` may still draw on (stage 01
    ``ledger.referenced_cover``; D-87 L6-5-Q-15): the contract's unreferenced billing less its
    unreferenced credits, less the other non-VC obligations' credits in excess of their billing;
    never negative."""
    drawn = sum(
        (
            max(Decimal(0), _at(ledger.credited, other) - _at(ledger.billed, other))
            for other in set(ledger.billed) | set(ledger.credited)
            if other not in ("", subject) and other not in ledger.vc
        ),
        Decimal(0),
    )
    return max(Decimal(0), _at(ledger.billed, "") - _at(ledger.credited, "") - drawn)


def usage_period_refusal(start: date, end: date, effective: date) -> str | None:
    """04 §16.3 "The usage period of a report" (rev 1.320; item USAGE-REPORT-PERIOD-ENDED-1; PRD
    BR-REC-01, IMP-148): the sentence for a usage report or royalty statement whose usage period
    ``start`` to ``end`` ends after the report's date — ``effective``, the event's effective date
    in the contracting entity's zone — and None for a period that has ended by it, equal dates
    included. A report states usage that has occurred.

    The date is the effective date and not the instant of recording: the engine dates a version at
    the latest effective date it includes (T-CON-11 ``effective_date``) and counts a rated fee
    from its usage period's end (ENGINE_SPEC_B S09-R-19), so with ``end <= effective`` every
    version that includes the report has realised it. Measured before the rule, on main: a report
    for 1 to 31 August dated 24 August left the RPO report, the waterfall and the contract read
    short by its fee from 31 August, and a lock froze the short figure. Pure: the CSV template
    ``usage`` states the same sentence for a row from the row's own dates."""
    if end <= effective:
        return None
    return USAGE_PERIOD_MESSAGE.format(start=_day(start), end=_day(end), date=_day(effective))


def _period_finding(index: int, event: EventIn) -> ProblemError | None:
    """``usage_period_refusal`` of a ``USAGE_REPORTED`` event — the usage report and the royalty
    statement are one payload — at its ``usage_period_end``; no other type has a usage period."""
    if event.event_type is not ContractEventType.USAGE_REPORTED:
        return None
    body = payloads.payload_json(event.payload)
    message = usage_period_refusal(
        date.fromisoformat(str(body["usage_period_start"])),
        date.fromisoformat(str(body["usage_period_end"])),
        event.effective_date,
    )
    if message is None:
        return None
    return _error(f"events.{index}.payload.usage_period_end", USAGE_PERIOD, message)


def check_bounds(
    session: Session,
    contract_row: Mapping[str, Any],
    events: Sequence[EventIn],
    *,
    known_at: datetime,
) -> None:
    """05 §3.9: a bound detected before append answers 422 and appends nothing. ``known_at``
    resolves the effective tenant preset for the parity VC scope (D-98 103). The usage period of
    a report is held here too (``_period_finding``; 04 §16.3 rev 1.320): every channel and the
    approval of a stored request pass this function."""
    ledger = _ledger(session, contract_row, known_at=known_at, pending=events)
    errors = [
        finding
        for index, event in enumerate(events)
        if (finding := _period_finding(index, event) or _bound_finding(ledger, index, event))
        is not None
    ]
    if errors:
        raise _failed(errors)


def _locked_visible(uow: UnitOfWork, contract_id: UUID) -> dict[str, Any]:
    # DG-KRN-DB-08 rev 1.36 (D-98 101b): the group row first, then the contract row — the events
    # appended below update the contract (_raise_head) and the group (_mark_dirty) under held locks.
    _, current = repo.lock_group_then_contract(uow.session, contract_id)
    require_for_entity(uow.ctx, RECORD_PERMISSION, current["contracting_entity_id"])
    return current


def _require_head(current: Mapping[str, Any], expected: int | None) -> None:
    if expected != int(current["head_stream_version"]):
        raise Problem(
            "precondition-failed",
            STALE_MESSAGE,
            code=EVT_CODE,
            errors=[_error("If-Match", EVT_CODE, STALE_MESSAGE)],
        )


def _locked_contract(uow: UnitOfWork, contract_id: UUID, expected: int | None) -> dict[str, Any]:
    current = _locked_visible(uow, contract_id)
    _require_head(current, expected)
    return current


def _time_zone(session: Session, entity_id: UUID) -> str:
    return str(
        session.execute(
            select(legal_entity.c.time_zone).where(legal_entity.c.id == entity_id)
        ).scalar_one()
    )


def _day(value: date) -> str:
    """A date as copy prints it: ``DD MMM YYYY`` (DESIGN_SYSTEM DS-FMT-16; PRD NFR-40)."""
    return format_date(value.isoformat())


def _step1_errors(
    index: int,
    event: EventIn,
    record: step1.Record | None,
    contract_id: UUID,
    *,
    gate_at: datetime | None = None,
    booked_at: datetime | None = None,
    overtaken_by: step1.Record | None = None,
    flag_at: datetime | None = None,
    flag_here: bool = False,
) -> list[ProblemError]:
    """The judgement record a Step 1 assessment names (L4-1-Q-10; ``step1.serves``, ruling R-77
    (7)): a record of the contract for the event's book (04 T-CON-19: a record without a book is
    of every book), of topic NOT_A_CONTRACT when collectibility is not probable (PRD SM-02 guard)
    and COLLECTIBILITY otherwise (item STEP1-HOLD-RELEASE-1, 04 §16.3 (b) rev 1.209: before, a
    probable assessment could also cite a NOT_A_CONTRACT record); REVIEWED (ruling R-102 (b)) and
    reviewed at or after ``booked_at``, the time the latest standing booking was written (ruling
    R-102 (c): not strict — the legacy composer reviews in the transaction that books).
    ``gate_at`` is given for a probable assessment of a book that is out as not probable — the
    criteria-met re-assessment (rulings R-77 (3), R-102 (a)): its record was reviewed after the
    event that put the book out was written (``step1.criteria_met`` decides). A probable
    assessment is also refused, by name, for every criterion its record answers No to
    (``step1.unmet``): (a), (b), (c), (e), and (d) for the criteria-met re-assessment.

    Item STEP1-CITE-LATEST-1 (the supervisor's ruling of 2026-10-02): a record that serves — its
    topic and book fit — is the NEWEST review of the judgement: ``overtaken_by`` is the record
    of the other Step 1 topic, of the same subject and book, that was reviewed after it
    (``step1.overtaken``), and the refusal names it. And a PROBABLE assessment that answers a
    significant-change flag rests on a record reviewed at or after the time the flag was
    recorded (``flag_at``; not strict, as for the booking) — a review made before the flag did
    not look at the change, and with it the preparer alone dismissed the flag. ``flag_here``:
    the flag is of the same request, so no record can have been reviewed after it. One finding
    a record about its review: not reviewed, before the booking, before the gate, overtaken,
    before the flag."""
    field = f"events.{index}.payload.judgement_record_id"
    payload = event.payload
    if record is None or record.contract_id != contract_id:
        return [_error(field, RULE_STEP1, NO_RECORD)]
    errors: list[ProblemError] = []
    probable = not (
        isinstance(payload, payloads.CollectibilityAssessedV1) and not payload.is_probable
    )
    topics = step1.PROBABLE_TOPICS if probable else step1.NOT_PROBABLE_TOPICS
    if record.topic not in topics:
        errors.append(
            _error(field, RULE_STEP1, WRONG_TOPIC.format(topics=", ".join(sorted(topics))))
        )
    payload_book = getattr(payload, "book", None)
    if record.book is not None and record.book != str(getattr(payload_book, "value", payload_book)):
        errors.append(_error(field, RULE_STEP1, WRONG_BOOK))
    serves = not errors  # the topic and the book fit: only then is "which review" a question
    if record.status != JudgementStatus.REVIEWED.value:
        errors.append(_error(field, RULE_STEP1, NOT_REVIEWED))
    elif booked_at is not None and (record.reviewed_at is None or record.reviewed_at < booked_at):
        errors.append(_error(field, RULE_STEP1, REVIEWED_BEFORE_BOOKING))
    elif (
        probable
        and gate_at is not None
        and (record.reviewed_at is None or record.reviewed_at <= gate_at)
    ):
        errors.append(_error(field, RULE_STEP1, REVIEWED_BEFORE_GATE))
    elif serves and overtaken_by is not None:
        errors.append(
            _error(
                field,
                RULE_STEP1,
                RECORD_OVERTAKEN.format(judgement_no=overtaken_by.judgement_no),
            )
        )
    elif (
        serves
        and probable
        and (
            flag_here
            or (
                flag_at is not None and (record.reviewed_at is None or record.reviewed_at < flag_at)
            )
        )
    ):
        errors.append(_error(field, RULE_STEP1, REVIEWED_BEFORE_FLAG))
    if probable:
        # Rulings R-113 (f), R-115 (f) (04 T-CON-19): a review that answers No to criterion (a),
        # (b) or (c) — or to (d), for the criteria-met re-assessment — carries no probable
        # assessment; a not-probable one may cite it. Item STEP1-HOLD-RELEASE-1 (the supervisor's
        # ruling of 2026-10-01): nor does a review that answers No to (e).
        errors += [
            _error(
                field,
                RULE_STEP1,
                step1.CRITERION_NOT_MET.format(criterion_label=step1.CRITERION_LABELS[key]),
            )
            for key in step1.unmet(record, criteria_met=gate_at is not None)
        ]
    return errors


def _gate(event: EventIn) -> EventIn:
    """[J] L4-1-Q-10: ENGINE_SPEC Table 2.2-A reaches NOT_A_CONTRACT only at the activation gate, so
    an assessment of a DRAFT contract as not probable is followed by ``CONTRACT_ACTIVATED``; the
    engine then gives NOT_PROBABLE and receipts post to the deposit liability (S02-R-08). Ruling
    R-20 (b) narrows when: ``step1_outcome`` and ``_confirmed``."""
    return EventIn(
        event_type=ContractEventType.CONTRACT_ACTIVATED,
        effective_date=event.effective_date,
        payload=payloads.ContractActivatedV1(
            checklist=(
                payloads.ChecklistItemV1(
                    code="STEP1_RECORD", passed=True, detail=STEP1_GATE_DETAIL
                ),
            )
        ),
    )


def refuse_activation_events(items: Sequence[EventAppendItemIn]) -> None:
    """Ruling R-20 (c) (PRD SM-02; 04 E-03 rev 1.105): ``CONTRACT_CRITERIA_MET`` and
    ``CONTRACT_ACTIVATED`` move a book into recognition, so only the approved activation appends
    them — 409 ``invalid-transition`` for every caller, naming the command."""
    errors = [
        ProblemError(
            field=f"events.{index}.event_type",
            rule_id=transitions.RULE_ID,
            message=ACTIVATION_ONLY.format(event_type=item.event_type.value),
        )
        for index, item in enumerate(items)
        if item.event_type in ACTIVATION_TYPES
    ]
    if errors:
        raise Problem("invalid-transition", errors[0].message, errors=errors)


def _inception(current: Mapping[str, Any]) -> date:
    value = current["inception_date"]
    return value if isinstance(value, date) else date.fromisoformat(str(value))


@dataclass(frozen=True, slots=True)
class Step1Gate:
    """What became of the not-a-contract gate of a request that assesses a DRAFT contract as not
    probable (04 §16.3 (c); rulings R-77 (6), R-84 (b)): appended, or withheld for ``reason``
    (E-132) — the assessment is recorded and the contract stays DRAFT, never silently. The answer
    carries the code alone; the copy is the screen's."""

    appended: bool
    reason: Step1GateReason | None = None

    def out(self) -> Step1GateOut:
        return Step1GateOut(appended=self.appended, reason=self.reason)


def _withheld(reason: Step1GateReason) -> Step1Gate:
    return Step1Gate(appended=False, reason=reason)


def step1_outcome(
    uow: UnitOfWork,
    current: Mapping[str, Any],
    events: Sequence[EventIn],
    *,
    engine: computation.Engine | None = None,
    confirm: bool = True,
    lock: bool = True,
) -> tuple[list[EventIn], Step1Gate | None]:
    """Validate the Step 1 events of an append and add the not-a-contract gate when ruling R-20 (b)
    admits it (module docstring). An assessment: its judgement record (``_step1_errors``), an
    enabled book of the contracting entity, and its date. A significant-change flag: its date.
    Once the stream holds a ``CONTRACT_ACTIVATED`` neither is dated before the latest Step 1 event
    it acts on (ruling R-77 (1)): Table 2.2-A reads the events in ENG-06 order, so an earlier date
    would be read before events already recorded — a probable assessment slipped between a flag
    and the not-probable re-assessment cancels a 606-10-25-5 transition, and the mirror moves a
    book out retroactively. A not-probable assessment of a book that is active by the Step 1
    replay follows a significant-change flag that no assessment of the book has answered —
    stored, or earlier in the request — or is refused (``STEP1_CHANGE_NOT_FLAGGED``, PRD
    IMP-136; item STEP1-HOLD-RELEASE-1): without the flag the table reads it and moves nothing.
    For a not-probable assessment of a DRAFT contract that leaves every
    enabled book not probable, the gate follows right behind it and is kept only when the engine
    confirms it (``_confirmed``); the second value says what became of it (``Step1Gate``; None
    when the request decides no gate). Every path that records events for a caller goes through
    here (the events route, its preview, the CSV import, the integration documents);
    ``confirm = False`` serves the preview REQUEST, which validates and appends nothing, and
    ``lock = False`` the preview JOB, which decides the gate as the append would and appends
    nothing. A recording path reads the enabled books under the shared ``book`` lock (rulings
    R-77 (5) and R-80), so a book is not kept or disabled between the reading and the appended
    gate."""
    if not any(event.event_type in STEP1_DATED_TYPES for event in events):
        return list(events), None
    session = uow.session
    contract_id = UUID(str(current["id"]))
    entity_id = UUID(str(current["contracting_entity_id"]))
    status = str(getattr(current["status"], "value", current["status"]))
    if confirm and lock:
        step1.lock_books(session)
    books = step1.enabled_books(session, entity_id)
    stream = step1.read(session, contract_id)
    assessments, gate_date = list(stream.assessments), stream.gate_date
    dated = list(stream.dated)
    entity = session.execute(
        select(legal_entity.c.code, legal_entity.c.time_zone).where(legal_entity.c.id == entity_id)
    ).one()
    entity_code = str(entity.code)
    # Rulings R-82 (c) and R-84 (a): nothing of Step 1 is dated ahead of the later of the
    # contracting entity's current date (05 TZ-03) and the contract's inception date — a wrong
    # future date could be neither preceded (R-77 (1)) nor voided, and a contract booked ahead of
    # its inception is still assessed at that inception.
    latest_day = max(
        uow.now.astimezone(ZoneInfo(str(entity.time_zone))).date(), _inception(current)
    )
    known = step1.records(
        session,
        [
            event.payload.judgement_record_id
            for event in events
            if isinstance(event.payload, payloads.CollectibilityAssessedV1)
        ],
    )
    # Item STEP1-CITE-LATEST-1: the cited records a later review of the other topic overtook.
    overtaken = step1.overtaken(session, known.values())
    errors: list[ProblemError] = []
    found: list[EventIn] = []
    undecided: EventIn | None = None  # a not-probable assessment of a DRAFT contract, no gate yet
    # Where the replay of Table 2.2-A stands per book once the request's own events so far are
    # read behind the stored ones (``_standing``; item STEP1-HOLD-RELEASE-1).
    moved: dict[str, step1.Standing] = {}
    flagged_here = False
    for index, event in enumerate(events):
        found.append(event)
        if event.event_type is ContractEventType.SIGNIFICANT_CHANGE_FLAGGED:
            limit = None if gate_date is None else step1.latest_date(dated, None)
            if event.effective_date > latest_day:
                errors.append(
                    _error(
                        f"events.{index}.effective_date",
                        RULE_STEP1,
                        STEP1_AHEAD.format(what="significant-change flag", date=_day(latest_day)),
                    )
                )
                continue
            if limit is not None and event.effective_date < limit:
                errors.append(
                    _error(
                        f"events.{index}.effective_date",
                        RULE_STEP1,
                        FLAG_BEFORE_STEP1.format(date=_day(limit)),
                    )
                )
                continue
            dated.append((None, event.effective_date))
            flagged_here = True
            moved = {
                code: step1.Standing(active=item.active, flagged=True)
                for code, item in moved.items()
            }
            continue
        payload = event.payload
        if event.event_type not in STEP1_TYPES or not isinstance(
            payload, payloads.CollectibilityAssessedV1
        ):
            continue
        book = str(getattr(payload.book, "value", payload.book))
        # The criteria-met re-assessment (rulings R-77 (3), R-102 (a)): a probable assessment of
        # a book that is out as not probable — behind the gate, or under an ACTIVE header.
        put_out = stream.out.get(book) if payload.is_probable else None
        stands = moved.get(book)
        if stands is None:
            stands = step1.standing(stream, book)
            if flagged_here:
                stands = step1.Standing(active=stands.active, flagged=True)
        cited = known.get(str(payload.judgement_record_id))
        invalid = _step1_errors(
            index,
            event,
            cited,
            contract_id,
            gate_at=None if put_out is None else put_out.recorded_at,
            booked_at=stream.booked_at,
            overtaken_by=None if cited is None or cited.id is None else overtaken.get(cited.id),
            # The flag this assessment answers (item STEP1-CITE-LATEST-1): the stored one, by
            # the time it was recorded — or a flag of this request, which has no time yet.
            flag_at=stands.flagged_at if stands.flagged else None,
            flag_here=stands.flagged and stands.flagged_at is None,
        )
        if book not in books:
            invalid.append(
                _error(
                    f"events.{index}.payload.book",
                    RULE_STEP1,
                    BOOK_NOT_ENABLED.format(book=book, entity=entity_code),
                )
            )
        limit = None if gate_date is None else step1.latest_date(dated, book)
        if event.effective_date > latest_day:
            invalid.append(
                _error(
                    f"events.{index}.effective_date",
                    RULE_STEP1,
                    STEP1_AHEAD.format(what="assessment", date=_day(latest_day)),
                )
            )
        elif limit is not None and event.effective_date < limit:
            # The limit is the book's latest Step 1 entry; the first activation event is
            # one, so a date before the activation is refused here too.
            invalid.append(
                _error(
                    f"events.{index}.effective_date",
                    RULE_STEP1,
                    ASSESSMENT_BEFORE_STEP1.format(
                        book_label=BOOK_NAMES[BookCode(book)], date=_day(limit)
                    ),
                )
            )
        if not payload.is_probable and stands.active and not stands.flagged:
            # Item STEP1-HOLD-RELEASE-1 (04 §16.3 (g) rev 1.209; table 15.4-I
            # ``STEP1_CHANGE_NOT_FLAGGED``, PRD IMP-136): Table 2.2-A takes an active book out
            # only on a not-probable assessment that follows a significant-change flag
            # (606-10-25-5). Without the flag the assessment was recorded and did nothing — the
            # book went on recognising under a reviewed "not a contract" — so it is refused.
            invalid.append(
                _error(
                    f"events.{index}.payload.is_probable",
                    step1.CHANGE_NOT_FLAGGED,
                    step1.CHANGE_NOT_FLAGGED_MESSAGE,
                )
            )
        if invalid:
            errors += invalid
            continue
        # Behind this assessment the book is out when it was active, flagged and is now not
        # probable; any assessment of the book answers the flag that stood.
        moved[book] = step1.Standing(
            active=stands.active and (payload.is_probable or not stands.flagged), flagged=False
        )
        assessments.append(
            step1.Assessment(
                book=book,
                is_probable=payload.is_probable,
                effective_date=event.effective_date,
                order=(1, index),
                judgement_record_id=str(payload.judgement_record_id),
            )
        )
        dated.append((book, event.effective_date))
        if payload.is_probable or status != ContractStatus.DRAFT.value:
            continue
        if step1.every_book_not_probable(books, assessments, event.effective_date):
            found.append(_gate(event))
            status = ContractStatus.NOT_A_CONTRACT.value
            gate_date = event.effective_date
            dated.append((None, event.effective_date))
            undecided = None
        else:
            undecided = event
    if errors:
        raise _failed(errors)
    if any(_is_gate(event) for event in found):
        if not confirm:
            return found, Step1Gate(appended=True)
        return _confirmed(uow, current, found, engine)
    if undecided is None:
        return found, None
    return found, _withheld(Step1GateReason.BOOK_NOT_ASSESSED)


def step1_events(
    uow: UnitOfWork,
    current: Mapping[str, Any],
    events: Sequence[EventIn],
    *,
    engine: computation.Engine | None = None,
    confirm: bool = True,
) -> list[EventIn]:
    """``step1_outcome`` for a caller that answers no gate outcome (the CSV import, the
    integration documents): the events to append."""
    return step1_outcome(uow, current, events, engine=engine, confirm=confirm)[0]


def _is_gate(event: EventIn) -> bool:
    return event.event_type is ContractEventType.CONTRACT_ACTIVATED


def _confirmed(
    uow: UnitOfWork,
    current: Mapping[str, Any],
    events: list[EventIn],
    engine: computation.Engine | None,
) -> tuple[list[EventIn], Step1Gate]:
    """Ruling R-20 (b), confirmed by the engine: a batch that carries the not-a-contract gate is
    appended with it only when its dry run gives this contract the status NOT_A_CONTRACT in EVERY
    book the group is computed in, and each of those books is an enabled book of the contracting
    entity. Table 2.2-A decides per book: a book another entity of the group keeps has no
    assessment, so the gate would activate the contract there — or leave it NOT_A_CONTRACT for
    want of performance (606-10-25-4), which the first receipt, invoice or delivery ends without
    any approval. A group over the obligation budget, or a dry run the engine refuses, confirms
    nothing. Without confirmation the gate is dropped: the assessment is recorded and the contract
    stays DRAFT (``events.stream.header_projection`` moves the header only with the gate), where
    the only way to a status is the approved activation — and the answer says why (ruling R-77
    (6): ``Step1Gate``)."""
    session = uow.session
    contract_id = UUID(str(current["id"]))
    group_id = UUID(str(current["combination_group_id"]))
    without = [event for event in events if not _is_gate(event)]
    if obligation_count(session, group_id) > OBLIGATION_BUDGET:
        return without, _withheld(Step1GateReason.GROUP_TOO_LARGE)
    run = engine if engine is not None else computation.default_engine()
    try:
        bundle = bundles.build(
            session, group_id, uow.now, events, DRY_RUN, pending_contract_id=contract_id
        )
        output = run(bundle)
    except EngineError:
        return without, _withheld(Step1GateReason.ENGINE_REFUSED)
    external_id = str(current["external_id"])
    books = set(step1.enabled_books(session, UUID(str(current["contracting_entity_id"]))))
    statuses = [
        (book.book_code, status)
        for book in output.books
        for key, status in book.status_in_book
        if key == external_id
    ]
    if statuses and all(
        code in books and status == ContractStatus.NOT_A_CONTRACT.value for code, status in statuses
    ):
        return events, Step1Gate(appended=True)
    return without, _withheld(Step1GateReason.BOOK_NOT_CONFIRMED)


def _assessed_holds(session: Session, events: Sequence[EventIn]) -> list[tuple[str, str]]:
    """Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" (b), rev 1.209; the supervisor's
    ruling of 2026-10-01): the REQ-POL-010 hold of a ``NOT_A_CONTRACT`` record outlives its
    review and is released by the first NOT-PROBABLE ``COLLECTIBILITY_ASSESSED`` that cites the
    record — the assessment the reviewed record stands for, which takes the book out (a
    not-probable assessment that would take no effect is refused, ``STEP1_CHANGE_NOT_FLAGGED``).
    Answers, per record the request's not-probable assessments cite, in request order and once
    each, the reason its hold is found by (``holds.judgement_hold_reason``) and the comment of
    the release. A probable assessment releases nothing: it cites no ``NOT_A_CONTRACT`` record
    — the route refuses the one that does (04 §16.3 (b), ``_step1_errors``)."""
    cited = [
        str(event.payload.judgement_record_id)
        for event in events
        if isinstance(event.payload, payloads.CollectibilityAssessedV1)
        and not event.payload.is_probable
    ]
    known = step1.records(session, cited)
    found: list[tuple[str, str]] = []
    for record_id in dict.fromkeys(cited):
        record = known.get(record_id)
        if record is not None:
            found.append(
                (
                    holds.judgement_hold_reason(record.judgement_no, record.topic),
                    holds.STEP1_RELEASE_COMMENT.format(judgement_no=record.judgement_no),
                )
            )
    return found


def _release_assessed_holds(
    uow: UnitOfWork, contract_id: UUID, events: Sequence[EventIn]
) -> list[dict[str, Any]]:
    """Release the holds of ``_assessed_holds`` as SYSTEM, behind the caller's append and in its
    unit of work (the caller computes once); answers the ``HOLD_RELEASED`` rows in stream
    order."""
    session = uow.session
    released: list[UUID] = []
    for reason, comment in _assessed_holds(session, events):
        released += holds.release_system_holds(uow, contract_id, reason=reason, comment=comment)
    if not released:
        return []
    statement = (
        select(contract_event)
        .join(
            contract_hold,
            and_(
                contract_hold.c.tenant_id == contract_event.c.tenant_id,
                contract_hold.c.released_event_id == contract_event.c.id,
            ),
        )
        .where(contract_hold.c.id.in_(released))
        .order_by(contract_event.c.stream_version)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _pending_hold_releases(
    session: Session, current: Mapping[str, Any], now: datetime, events: Sequence[EventIn]
) -> list[EventIn]:
    """What ``_release_assessed_holds`` would append, for the preview's dry run (ruling R-77 (8):
    the preview computes what recording would append)."""
    pending: list[EventIn] = []
    for reason, comment in _assessed_holds(session, events):
        pending += holds.pending_system_releases(
            session, current, now, reason=reason, comment=comment
        )
    return pending


def _validated(
    uow: UnitOfWork,
    current: Mapping[str, Any],
    body: EventAppendIn,
    *,
    engine: computation.Engine | None = None,
    confirm: bool = True,
) -> tuple[list[EventIn], Step1Gate | None]:
    session = uow.session
    events = to_events(
        body.events,
        time_zone=_time_zone(session, UUID(str(current["contracting_entity_id"]))),
        is_manual=uow.principal.kind is PrincipalKind.USER,
    )
    # DG-CMD-03 DB-07 mirror (BUILD_SPEC CLO-3; ERR-15).
    refuse_closed_postings(
        session,
        entity_id=UUID(str(current["contracting_entity_id"])),
        effective_dates=[event.effective_date for event in events],
    )
    events, gate = step1_outcome(uow, current, events, engine=engine, confirm=confirm)  # R-20
    check_bounds(session, current, events, known_at=uow.now)
    return events, gate


# --- reads ---------------------------------------------------------------------------------------


def _first_computations(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[UUID, EventComputationOut]:
    """Per event, the earliest computation whose ``stream_heads`` include it (API-S-Event)."""
    contract_ids = sorted({UUID(str(row["contract_id"])) for row in rows})
    if not contract_ids:
        return {}
    groups = select(combination_group_member.c.combination_group_id).where(
        combination_group_member.c.contract_id.in_(contract_ids)
    )
    computations = session.execute(
        select(
            contract_computation.c.id,
            contract_computation.c.status,
            contract_computation.c.stream_heads,
        )
        .where(contract_computation.c.combination_group_id.in_(groups))
        .order_by(contract_computation.c.created_at, contract_computation.c.id)
    ).all()
    found: dict[UUID, EventComputationOut] = {}
    for row in rows:
        contract_key = str(row["contract_id"])
        for item in computations:
            heads = item.stream_heads or {}
            if int(heads.get(contract_key, 0)) >= int(row["stream_version"]):
                found[UUID(str(row["id"]))] = EventComputationOut(
                    id=item.id,
                    status=ComputationStatus(str(getattr(item.status, "value", item.status))),
                )
                break
    return found


def _source_rows(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[UUID, EventSourceRowOut]:
    """``source_row`` of each imported event: the first import row whose lineage names it (04
    T-IMP-04; BUILD_SPEC DIN-3)."""
    ids = [row["id"] for row in rows if row["import_upload_id"] is not None]
    if not ids:
        return {}
    statement = (
        select(
            import_row_lineage.c.target_id,
            import_row.c.import_upload_id,
            import_row.c.sheet_name,
            import_row.c.row_number,
        )
        .select_from(
            import_row_lineage.join(
                import_row,
                and_(
                    import_row.c.tenant_id == import_row_lineage.c.tenant_id,
                    import_row.c.id == import_row_lineage.c.import_row_id,
                ),
            )
        )
        .where(
            import_row_lineage.c.target_type == "contract_event",
            import_row_lineage.c.target_id.in_(ids),
        )
        .order_by(import_row_lineage.c.target_id, import_row.c.row_number)
    )
    found: dict[UUID, EventSourceRowOut] = {}
    for target_id, upload_id, sheet_name, row_number in session.execute(statement):
        found.setdefault(
            UUID(str(target_id)),
            EventSourceRowOut(
                import_upload_id=upload_id, sheet=str(sheet_name), row_number=int(row_number)
            ),
        )
    return found


APPROVING: Final = (
    ApprovalDecisionKind.APPROVE.value,
    ApprovalDecisionKind.AUTO_APPROVE.value,
)


def _request_actors(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[UUID, tuple[dict[str, Any], dict[str, Any] | None]]:
    """Per approval request the rows name: its preparer and the principal whose decision
    completed its approval — the last approving decision — as API-S-Actor (04 API-S-Event
    ``prepared_by``, ``approved_by``, rev 1.194; BUILD_SPEC CTR-6). An event applied from an
    event submission is appended by the SYSTEM principal, so its row names neither person; the
    request it names does (PRD J-08-AC-3; control CTL-009). Read under the reader's own scope: a
    request the reader cannot see names nobody."""
    request_ids = sorted(
        {
            UUID(str(row["approval_request_id"]))
            for row in rows
            if row["approval_request_id"] is not None
        },
        key=str,
    )
    if not request_ids:
        return {}
    approvers: dict[UUID, dict[str, Any]] = {}
    for decided in session.execute(
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            actors.named(
                approval_decision.c.approver_id, tenant_id=approval_decision.c.tenant_id
            ).label("named"),
        )
        .where(
            approval_decision.c.approval_request_id.in_(request_ids),
            approval_decision.c.decision.in_(APPROVING),
        )
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    ).mappings():
        # the later decision replaces the earlier: the one that completed the approval stays
        approvers[UUID(str(decided["approval_request_id"]))] = actors.actor(
            decided["approver_id"], decided["approver_kind"], decided["named"]
        )
    found: dict[UUID, tuple[dict[str, Any], dict[str, Any] | None]] = {}
    for request in session.execute(
        select(
            approval_request.c.id,
            approval_request.c.preparer_id,
            approval_request.c.preparer_kind,
            actors.named(
                approval_request.c.preparer_id, tenant_id=approval_request.c.tenant_id
            ).label("named"),
        ).where(approval_request.c.id.in_(request_ids))
    ).mappings():
        request_id = UUID(str(request["id"]))
        found[request_id] = (
            actors.actor(request["preparer_id"], request["preparer_kind"], request["named"]),
            approvers.get(request_id),
        )
    return found


def event_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[EventOut]:
    """API-S-Event of each stored row: the one builder of the one model — the reads of the
    events resource, the answer of an append and the obligation's own event list
    (``obligations.event_items``) all answer what this function builds (04 rev 1.273)."""
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    obligation_ids = sorted({value for row in rows for value in row["obligation_ids"] or ()})
    keys = (
        {
            UUID(str(obligation_id)): str(key)
            for obligation_id, key in session.execute(
                select(obligation.c.id, obligation.c.obligation_key).where(
                    obligation.c.id.in_(obligation_ids)
                )
            )
        }
        if obligation_ids
        else {}
    )
    computations = _first_computations(session, rows)
    sources = _source_rows(session, rows)
    requests = _request_actors(session, rows)
    refusals = void_refusals(session, rows)

    def by_request(row: Mapping[str, Any]) -> tuple[Any, Any]:
        """(``prepared_by``, ``approved_by``) of the request the row names."""
        request_id = row["approval_request_id"]
        if request_id is None:
            return None, None
        return requests.get(UUID(str(request_id)), (None, None))

    return [
        EventOut(
            id=row["id"],
            contract_id=row["contract_id"],
            stream_version=row["stream_version"],
            event_type=ContractEventType(
                str(getattr(row["event_type"], "value", row["event_type"]))
            ),
            schema_version=row["schema_version"],
            effective_date=row["effective_date"],
            recorded_at=row["recorded_at"],
            record_seq=row["record_seq"],
            origin=str(row["origin"]),
            is_manual=bool(row["is_manual"]),
            obligation_keys=[keys[UUID(str(value))] for value in row["obligation_ids"] or ()],
            payload=dict(row["payload"]),
            payload_sha256=str(row["payload_sha256"]).strip(),
            supersedes_event_id=row["supersedes_event_id"],
            approval_request_id=row["approval_request_id"],
            modification_id=row["modification_id"],
            estimate_version_id=row["estimate_version_id"],
            manual_adjustment_id=row["manual_adjustment_id"],
            import_upload_id=row["import_upload_id"],
            source_record_id=row["source_record_id"],
            source_row=sources.get(UUID(str(row["id"]))),
            created_by=approval_queries.actor(
                row["created_by"],
                str(getattr(row["created_by_kind"], "value", row["created_by_kind"])),
                names,
            ),
            prepared_by=by_request(row)[0],
            approved_by=by_request(row)[1],
            void_refusal=refusals[UUID(str(row["id"]))],
            computation=computations.get(UUID(str(row["id"]))),
        )
        for row in rows
    ]


def events_statement(
    contract_id: UUID,
    *,
    known_at: datetime | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    event_types: Sequence[ContractEventType] = (),
    obligation_key: str | None = None,
) -> Select[Any]:
    """``GET /contracts/{id}/events``: the stream filtered by API-R-30 parameters."""
    statement = select(contract_event).where(contract_event.c.contract_id == contract_id)
    if known_at is not None:
        statement = statement.where(contract_event.c.recorded_at <= known_at)
    if effective_from is not None:
        statement = statement.where(contract_event.c.effective_date >= effective_from)
    if effective_to is not None:
        statement = statement.where(contract_event.c.effective_date <= effective_to)
    if event_types:
        statement = statement.where(
            contract_event.c.event_type.in_([value.value for value in event_types])
        )
    if obligation_key is not None:
        named = select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == obligation_key
        )
        statement = statement.where(
            named.scalar_subquery() == any_(contract_event.c.obligation_ids)
        )
    return statement


def get_event(session: Session, event_id: UUID) -> EventOut:
    row = (
        session.execute(select(contract_event).where(contract_event.c.id == event_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    (item,) = event_outs(session, [dict(row)])
    return item


# --- record_events -------------------------------------------------------------------------------


def _job_out(session: Session, job_id: UUID) -> JobOut:
    row = session.execute(select(*JOB_COLUMNS).where(job.c.id == job_id)).mappings().one()
    (item,) = job_outs(session, [dict(row)])
    return item


EVIDENCE_FILE_RULE: Final = "T-PLT-29"
EVIDENCE_FILE_MISSING: Final = "Upload the evidence file first."


def evidence_errors(uow: UnitOfWork, file_ids: Sequence[UUID]) -> list[ProblemError]:
    """The evidence files a record of events names (04 API-S-EventAppend ``evidence_file_ids``):
    each must be a file the caller may read — their own upload, as a rule. An id that names no
    file and a file the caller may not read are refused alike (04 T-PLT-29 Binding; ruling R-111
    (1)): the ids are kept in the audit event of the record, so a member could otherwise put
    another member's file id on record as the evidence of their own event."""
    return [
        ProblemError(
            field=f"evidence_file_ids[{index}]",
            rule_id=EVIDENCE_FILE_RULE,
            message=EVIDENCE_FILE_MISSING,
        )
        for index, file_id in enumerate(file_ids)
        if file_access.bound(uow.session, uow.ctx, file_id) is None
    ]


def _attach_to_events(
    uow: UnitOfWork,
    file_ids: Sequence[UUID],
    rows: Sequence[Mapping[str, Any]],
    *,
    contract_id: UUID,
    approval_request_id: UUID | None = None,
) -> None:
    """04 §16.3 (rev 1.268; item EVT-EVIDENCE-1): every evidence file of a record is attached to
    every event the record appends (T-PLT-30 subject ``contract_event``), so that a reader of the
    event on its contract — ``contract.read`` for its entity — lists and opens what supported it.
    Each file once, at its first index; a file that cannot be attached is refused on the member
    the caller sent (``evidence_file_ids[i]``, 04 T-PLT-29 Binding), as ``_submit`` refuses it.
    ``uow`` is the caller's on a direct append, and the SYSTEM principal's, acting for the
    preparer, at the approval of a request."""
    event_ids = [UUID(str(row["id"])) for row in rows]
    attached: set[UUID] = set()
    for index, file_id in enumerate(file_ids):
        if file_id in attached:
            continue
        attached.add(file_id)
        try:
            attachments.attach_evidence(
                uow,
                file_object_id=file_id,
                subject_type=EVENT_SUBJECT,
                subject_ids=event_ids,
                contract_id=contract_id,
                approval_request_id=approval_request_id,
            )
        except Problem as problem:
            if problem.slug != "validation-failed":
                raise
            message = problem.errors[0].message if problem.errors else str(problem.detail)
            raise _failed([_error(f"evidence_file_ids[{index}]", RULE_FILE, message)]) from problem


def record_events(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int | None,
    body: EventAppendIn,
    engine: computation.Engine | None = None,
) -> Recorded:
    """``POST /contracts/{id}/events`` (API-R-30; DG-CMD-09)."""
    session = uow.session
    current = _locked_contract(uow, contract_id, expected_stream_version)
    evidence = evidence_errors(uow, body.evidence_file_ids)
    if evidence:
        raise Problem("validation-failed", errors=evidence)
    refuse_activation_events(body.events)  # ruling R-20 (c)
    locks.refuse_locked_fields(uow, current, body.events, permission=RECORD_PERMISSION)
    locks.refuse_version_pin(body.events)  # item ATTR-SSP-PIN-1: the SSP override command's
    subject = _submission_subject(uow, body.events)
    if subject is not None:
        submission = _submit(uow, current, body, subject_type=subject)
        return Recorded(appended=None, job=None, submission=submission)
    events, gate = _validated(uow, current, body, engine=engine)
    rows = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=events,
        origin=_origin(uow),
    )
    # Item EVT-EVIDENCE-1 (04 §16.3 rev 1.268): the files the caller sent are attached to the
    # events of the record, as the caller.
    _attach_to_events(uow, body.evidence_file_ids, rows, contract_id=contract_id)
    # Item STEP1-HOLD-RELEASE-1 (04 T-CON-20 "Judgement holds" (b)): the assessment, then the
    # SYSTEM release of the hold of the record it cites, one computation behind both. Of the
    # channels that record events for a caller this route alone takes an assessment (the CSV
    # v2 templates and the integration documents carry none).
    released = _release_assessed_holds(uow, contract_id, events)
    head = int(current["head_stream_version"]) + len(events) + len(released)
    group_id = UUID(str(current["combination_group_id"]))
    outcome = None
    if obligation_count(session, group_id) <= OBLIGATION_BUDGET:
        outcome = compute_group(uow, group_id, engine=engine, budget_seconds=ENGINE_BUDGET_SECONDS)
    detail: dict[str, Any] = {
        "event_ids": [str(row["id"]) for row in rows],
        "comment": body.comment,
        "evidence_file_ids": [str(value) for value in body.evidence_file_ids],
    }
    if released:
        detail["released_hold_event_ids"] = [str(row["id"]) for row in released]
    step1_gate = None if gate is None else gate.out()
    if step1_gate is not None:
        detail["step1_gate"] = step1_gate.model_dump(mode="json")
    if outcome is None or outcome.deferred:
        deferred = defer_compute(
            uow,
            group_id,
            contract_id=contract_id,
            result=None if step1_gate is None else {"step1_gate": detail["step1_gate"]},
        )
        uow.audit(
            action=RECORD_ACTION,
            object_type=CONTRACT_OBJECT,
            object_id=contract_id,
            object_version=str(head),
            detail={**detail, "job_id": str(deferred["id"])},
            contract_id=contract_id,
        )
        return Recorded(appended=None, job=_job_out(session, UUID(str(deferred["id"]))))
    stored = outcome.computation or {}
    status = outcome.status or ComputationStatus.FAILED
    uow.audit(
        action=RECORD_ACTION,
        object_type=CONTRACT_OBJECT,
        object_id=contract_id,
        object_version=str(head),
        detail={**detail, "contract_computation_id": str(stored.get("id")), "status": status.value},
        contract_id=contract_id,
    )
    appended = EventsAppendedOut(
        contract=queries.contract_out(session, contract_id, now=uow.now),
        events=event_outs(session, [*(dict(row) for row in rows), *released]),
        computation=AppendComputationOut(
            id=stored["id"],
            status=status,
            contract_version_ids={
                str(book): UUID(str(value))
                for book, value in dict(stored.get("contract_version_ids") or {}).items()
            },
        ),
        step1_gate=step1_gate,
    )
    return Recorded(appended=appended, job=None)


ATTRIBUTE_ACTION: Final = "event_submission.submit_attribute_change"
MANUAL_ACTION: Final = "event_submission.submit_manual_events"
SUBMIT_ACTIONS: Final[Mapping[ApprovalSubjectType, str]] = {
    ApprovalSubjectType.ATTRIBUTE_CHANGE: ATTRIBUTE_ACTION,
    ApprovalSubjectType.MANUAL_EVENT: MANUAL_ACTION,
}


def _by_person(uow: UnitOfWork) -> bool:
    """BUILD_SPEC CTR-6: every caller but an API client is a signed-in person (PRD BR-REC-01,
    ACT-10) — the rule fails closed for a principal kind this route was not written for."""
    return uow.principal.kind is not PrincipalKind.API_CLIENT


def _submission_subject(
    uow: UnitOfWork, items: Sequence[EventAppendItemIn]
) -> ApprovalSubjectType | None:
    """The approval a request waits for instead of being appended (04 §16.3; DG-KRN-EVT-02), or
    None for a direct append: ``ATTRIBUTE_CHANGE`` when it names ``LINE_ATTRIBUTES_CHANGED``
    ([J] L4-1-Q-23, whoever sends it), else ``MANUAL_EVENT`` when a signed-in person sends one of
    ``MANUAL_TYPES`` (CTR-6)."""
    if any(item.event_type in locks.ATTRIBUTE_TYPES for item in items):
        return ApprovalSubjectType.ATTRIBUTE_CHANGE
    if _by_person(uow) and any(item.event_type in MANUAL_TYPES for item in items):
        return ApprovalSubjectType.MANUAL_EVENT
    return None


def _needs_evidence(event: EventIn) -> bool:
    """04 §16.3 ``evidence_file_ids`` (rev 1.194): a progress, milestone or cost event, or a
    delivery whose trigger is acceptance."""
    if event.event_type in EVIDENCE_TYPES:
        return True
    if event.event_type is not ContractEventType.DELIVERY_RECORDED:
        return False
    trigger = getattr(event.payload, "trigger", None)
    return str(getattr(trigger, "value", trigger)) == ACCEPTANCE_TRIGGER


def _manual_summary(external_id: object, events: Sequence[EventIn]) -> str:
    named = [
        label
        for event_type, label in MANUAL_LABELS.items()
        if any(event.event_type is event_type for event in events)
    ]
    what = named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"
    suffix = "" if len(events) == 1 else f" ({len(events)} events)"
    return f"Record {what} of {external_id}{suffix}"


def _check_batch(uow: UnitOfWork, current: Mapping[str, Any], events: Sequence[EventIn]) -> None:
    """What a batch that waits for approval satisfies where it is stored AND where it is appended
    (04 T-CON-24 rev 1.194): the closed-period mirror (ERR-15), the bounds of table 15.4-A against
    the stream as it stands, and obligation keys the contract has."""
    session = uow.session
    refuse_closed_postings(
        session,
        entity_id=UUID(str(current["contracting_entity_id"])),
        effective_dates=[event.effective_date for event in events],
    )
    check_bounds(session, current, events, known_at=uow.now)
    known = {
        str(row["obligation_key"]) for row in repo.obligations(session, UUID(str(current["id"])))
    }
    errors = [
        _error(
            f"events.{index}.obligation_key",
            RULE_OBLIGATION,
            f"The contract has no obligation {key}.",
        )
        for index, event in enumerate(events)
        for key in event.obligation_keys
        if key not in known
    ]
    if errors:
        raise _failed(errors)


def _submit(
    uow: UnitOfWork,
    current: Mapping[str, Any],
    body: EventAppendIn,
    *,
    subject_type: ApprovalSubjectType,
) -> SubmissionCreatedOut:
    """A request that waits for approval appends nothing: its items are validated as an append
    would be and stored as ONE ``event_submission`` (04 §16.3 API-S-EventAppend, T-CON-24; PRD
    §2.5; DG-KRN-EVT-02 rev 1.177) — routed ``ATTRIBUTE_CHANGE`` for a request that names
    ``LINE_ATTRIBUTES_CHANGED`` ([J] L4-1-Q-23; REQ-MOD-021) and ``MANUAL_EVENT`` for the manual
    events of a signed-in person (BUILD_SPEC CTR-6; REQ-DAT-014). The evidence a person's manual
    progress, milestone, cost or acceptance event needs is asked for here and attached to the
    approval request, where the approver reads it."""
    session = uow.session
    contract_id = UUID(str(current["id"]))
    attribute = subject_type is ApprovalSubjectType.ATTRIBUTE_CHANGE
    # Ruling R-20: a Step 1 assessment is validated where it is recorded (its judgement record,
    # an enabled book, the gate); stored in a submission it would be appended at approval without
    # any of that. Ruling R-77 (1): the same holds for the DATE of a significant-change flag —
    # another Step 1 event may be recorded between the submission and its approval.
    riding = [
        _error(
            f"events.{index}.event_type",
            RULE_ROUTE,
            STEP1_OWN_REQUEST if item.event_type in STEP1_TYPES else step1.FLAG_OWN_REQUEST,
        )
        for index, item in enumerate(body.events)
        if item.event_type in STEP1_DATED_TYPES
    ]
    if riding:
        raise _failed(riding)
    by_person = _by_person(uow)
    events = to_events(
        body.events,
        time_zone=_time_zone(session, UUID(str(current["contracting_entity_id"]))),
        is_manual=by_person,
        allowed=RECORDED_TYPES | locks.ATTRIBUTE_TYPES if attribute else RECORDED_TYPES,
    )
    if by_person and not body.evidence_file_ids and any(_needs_evidence(event) for event in events):
        raise _failed([_error("evidence_file_ids", RULE_EVIDENCE, EVIDENCE_REQUIRED)])
    _check_batch(uow, current, events)
    items = [
        {
            "event_type": event.event_type.value,
            "effective_date": event.effective_date.isoformat(),
            "obligation_key": event.obligation_keys[0] if event.obligation_keys else None,
            "payload": payloads.payload_json(event.payload),
        }
        for event in events
    ]
    submission_id = new_id()
    principal = uow.principal
    session.execute(
        insert(event_submission).values(
            tenant_id=principal.tenant_id,
            id=submission_id,
            contract_id=contract_id,
            contracting_entity_id=current["contracting_entity_id"],
            events=items,
            status=ModificationStatus.DRAFT.value,
            comment=body.comment,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **_stamps(uow),
        )
    )
    transitions.apply(
        session,
        SUBMISSION_OBJECT,
        submission_id,
        to_status=ModificationStatus.SUBMITTED.value,
        expected_status=ModificationStatus.DRAFT.value,
        set_values=_stamps(uow),
    )
    request = approvals.submit(
        uow,
        subject_type=subject_type,
        subject_id=submission_id,
        summary=(
            f"Change line attributes of {current['external_id']}"
            if attribute
            else _manual_summary(current["external_id"], events)
        ),
        comment=body.comment,
    )
    request_id = UUID(str(request["id"]))
    transitions.apply(
        session,
        SUBMISSION_OBJECT,
        submission_id,
        to_status=None,
        set_values={"approval_request_id": request_id, **_stamps(uow)},
    )
    attached: set[UUID] = set()
    for index, file_id in enumerate(body.evidence_file_ids):
        if file_id in attached:
            continue  # each file once, at its first index
        attached.add(file_id)
        try:
            attachments.attach(
                uow,
                file_object_id=file_id,
                subject_type=EVIDENCE_SUBJECT,
                subject_id=request_id,
                description=None,
            )
        except Problem as problem:
            if problem.slug != "validation-failed":
                raise
            # ``attach`` names its own field; this route names the member the caller sent, in
            # the form of 04 T-PLT-29 Binding (``evidence_file_ids[i]``).
            message = problem.errors[0].message if problem.errors else str(problem.detail)
            raise _failed([_error(f"evidence_file_ids[{index}]", RULE_FILE, message)]) from problem
    after: dict[str, Any] = {
        "contract_id": str(contract_id),
        "event_types": [item["event_type"] for item in items],
        "approval_request_id": str(request_id),
    }
    if body.evidence_file_ids:
        after["evidence_file_ids"] = [str(value) for value in dict.fromkeys(body.evidence_file_ids)]
    uow.audit(
        action=SUBMIT_ACTIONS[subject_type],
        object_type=SUBMISSION_OBJECT,
        object_id=submission_id,
        object_version="1",
        after=after,
        comment=body.comment,
        approval_request_id=request_id,
        contract_id=contract_id,
    )
    return SubmissionCreatedOut(event_submission_id=submission_id, approval_request_id=request_id)


# --- preview -------------------------------------------------------------------------------------


def request_preview(
    uow: UnitOfWork, *, contract_id: UUID, expected_stream_version: int | None, body: EventAppendIn
) -> JobOut:
    """``POST /contracts/{id}/events/preview``: validate, append nothing, defer the dry run.

    The dry run reads the contract's group whole and its summary holds the group's figures, so
    the caller covers every entity the events of this contract are bound to (04 §16.10 rev
    1.295 "Who may ask for a preview"; supervisor ruling R-103 (b) (5)): 403 by name otherwise,
    after the 404 of a contract the caller cannot read and before the precondition and the
    validation, and nothing is deferred."""
    current = _locked_visible(uow, contract_id)
    approvals.require_contract_preview_scope(
        uow, contract_id, action=PREVIEW_ACTION, permission=RECORD_PERMISSION
    )
    _require_head(current, expected_stream_version)
    refuse_activation_events(body.events)  # ruling R-20 (c): no preview of what is never recorded
    locks.refuse_version_pin(body.events)  # item ATTR-SSP-PIN-1: nor of an SSP version pin
    _validated(uow, current, body, confirm=False)  # findings only; the job decides the gate
    deferred = uow.defer(
        JobKind.CONTRACT_COMPUTE,
        {
            "mode": PREVIEW_MODE,
            "contract_id": str(contract_id),
            "expected_stream_version": int(current["head_stream_version"]),
            "events": [item.model_dump(mode="json") for item in body.events],
            "is_manual": uow.principal.kind is PrincipalKind.USER,
        },
        subject_type=CONTRACT_OBJECT,
        subject_id=contract_id,
    )
    return _job_out(uow.session, UUID(str(deferred["id"])))


def _to_amount(value: object, minor: int) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, bool):
        raise TypeError("money is not a boolean")
    if isinstance(value, int):
        return minor_to_decimal(value, minor)
    if isinstance(value, Fraction):
        return Decimal(format_exact(value))
    return Decimal(str(value))


def _money(value: Decimal, currency: str) -> Any:
    return money_out(
        value.quantize(Decimal(1).scaleb(-ISO_4217[currency].minor_unit)), currency, ISO_4217
    )


def _obligation_key(external_id: str, subject_key: str) -> str | None:
    prefix = contract_subject_key(external_id) + "/"
    return subject_key[len(prefix) :] if subject_key.startswith(prefix) else None


def _before_obligations(
    session: Session, version_id: object | None, contract_id: UUID
) -> dict[str, tuple[Decimal, Decimal]]:
    if version_id is None:
        return {}
    statement = (
        select(
            obligation.c.obligation_key,
            obligation_version.c.allocated_amount,
            obligation_version.c.revenue_cum,
        )
        .select_from(
            obligation_version.join(
                obligation,
                and_(
                    obligation.c.tenant_id == obligation_version.c.tenant_id,
                    obligation.c.id == obligation_version.c.obligation_id,
                ),
            )
        )
        .where(
            obligation_version.c.contract_version_id == version_id,
            obligation_version.c.contract_id == contract_id,
        )
    )
    return {
        str(key): (Decimal(allocated), Decimal(revenue))
        for key, allocated, revenue in session.execute(statement)
    }


def _before_revenue(
    session: Session, version_id: object | None, contract_id: UUID
) -> dict[str, Decimal]:
    if version_id is None:
        return {}
    statement = (
        select(period.c.period_key, schedule_line.c.amount)
        .select_from(
            schedule_line.join(
                schedule,
                and_(
                    schedule.c.tenant_id == schedule_line.c.tenant_id,
                    schedule.c.id == schedule_line.c.schedule_id,
                ),
            ).join(
                period,
                and_(
                    period.c.tenant_id == schedule_line.c.tenant_id,
                    period.c.id == schedule_line.c.period_id,
                ),
            )
        )
        .where(
            schedule_line.c.contract_version_id == version_id,
            schedule_line.c.contract_id == contract_id,
            schedule.c.schedule_kind == REVENUE,
        )
    )
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for key, amount in session.execute(statement):
        totals[str(key)] += Decimal(amount)
    return dict(totals)


def _six_periods(bundle: InputBundle, entity_code: str, replay_from: date) -> list[str]:
    entity = next((item for item in bundle.entities if item.code == entity_code), None)
    if entity is None:
        return []
    periods = sorted(entity.periods, key=lambda item: item.start_date)
    start = next(
        (index for index, item in enumerate(periods) if item.end_date >= replay_from), len(periods)
    )
    return [item.period_key for item in periods[start : start + SUMMARY_PERIODS]]


def _journal_lines(
    session: Session, output: OutputBundle, book_code: str, currency: str
) -> list[ImpactJournalLineOut]:
    minor = ISO_4217[currency].minor_unit
    totals: dict[tuple[str, str], list[Decimal]] = {}
    for book in output.books:
        if book.book_code != book_code:
            continue
        for intent in book.posting_intents:
            for line in intent.lines:
                if line.txn_currency != currency:
                    continue
                entry = totals.setdefault(
                    (line.account_role, line.account_code), [Decimal(0), Decimal(0)]
                )
                amount = minor_to_decimal(line.amount_txn, minor)
                entry[0 if line.side == "D" else 1] += amount
    codes = sorted({code for _, code in totals})
    accounts = (
        {
            str(code): RefOut(id=account_id, code=str(code), name=str(name))
            for account_id, code, name in session.execute(
                select(gl_account.c.id, gl_account.c.code, gl_account.c.name).where(
                    gl_account.c.code.in_(codes)
                )
            )
        }
        if codes
        else {}
    )
    return [
        ImpactJournalLineOut(
            gl_account=accounts.get(code),
            account_role=role,
            debit=_money(debit, currency),
            credit=_money(credit, currency),
        )
        for (role, code), (debit, credit) in sorted(totals.items())
    ]


def _book_obligations(
    output: OutputBundle, book_code: str, external_id: str
) -> dict[str, Mapping[str, object]]:
    """Obligation key → the T-CON-11 columns of the dry run's version in ``book_code``."""
    book = next((item for item in output.books if item.book_code == book_code), None)
    found: dict[str, Mapping[str, object]] = {}
    for item in () if book is None else book.obligation_versions:
        key = _obligation_key(external_id, item.subject_key)
        if key is not None:
            found[key] = item.columns
    return found


def step1_catch_up(
    session: Session, current: Mapping[str, Any], output: OutputBundle, book_code: str
) -> dict[str, Decimal]:
    """The POL-013 catch-up of a criteria-met activation in ``book_code``, per obligation key (04
    API-S-ImpactSummary rev 1.105; ENGINE_SPEC S02-R-04; supervisor ruling R-20 (c)).

    The engine states the revenue of a contract whose Step 1 criteria are met as the obligation's
    posted target, net of the 606-10-25-7 revenue attributed to it: max(C_p(d) − R25_p, 0), with
    the inception segments kept under ``CATCH_UP_AT_TRANSITION`` and a first segment opened at the
    transition under ``PROSPECTIVE_FROM_TRANSITION``. Stage 09 classes ``CONTRACT_CRITERIA_MET``
    as ``NORMAL`` (ENGINE_SPEC_B S09-R-35), so T-CON-11 ``catch_up_amount`` is 0 for it and the
    figure is read where the engine publishes it: ``revenue_cum`` of the dry-run version — the
    target at the version's date, which is the transition date unless the stream already holds a
    later-dated event — less ``revenue_cum`` of the stored version (a book that is not a contract
    recognises nothing, V4). ``PROSPECTIVE_FROM_TRANSITION`` therefore shows the revenue since the
    transition, 0.00 at the transition date.
    """
    contract_id = UUID(str(current["id"]))
    currency = str(current["transaction_currency"]).strip()
    minor = ISO_4217[currency].minor_unit
    before = bundles.previous_version(
        session, UUID(str(current["combination_group_id"])), book_code
    )
    stored = _before_obligations(session, None if before is None else before["id"], contract_id)
    found: dict[str, Decimal] = {}
    for key, columns in _book_obligations(output, book_code, str(current["external_id"])).items():
        after = _to_amount(columns.get("revenue_cum"), minor)
        found[key] = after - stored.get(key, (Decimal(0), Decimal(0)))[1]
    return found


def step1_catch_up_totals(
    session: Session, current: Mapping[str, Any], output: OutputBundle, books: Sequence[str]
) -> dict[str, Any]:
    """Book → Σ ``step1_catch_up`` as Money (wire form), for the ``criteria_met`` members of a
    criteria-met activation's impact preview (04 §16.10 rev 1.105)."""
    currency = str(current["transaction_currency"]).strip()
    return {
        code: _money(
            sum(step1_catch_up(session, current, output, code).values(), Decimal(0)), currency
        ).model_dump(mode="json")
        for code in books
    }


def latest_postable_period(session: Session, entity_id: UUID, book_code: str) -> str | None:
    """The key of the latest period of the entity's calendar that is postable for ``book_code``
    (E-04 ``open``, ``closing`` or ``reopened``) — the last period a computation posts into: the
    posting stage stops at the first ``future`` period (ENGINE_SPEC_B S14-R-06). None when the
    entity keeps no postable period of the book."""
    statement = (
        select(period.c.period_key)
        .select_from(
            period.join(
                period_state,
                and_(
                    period_state.c.tenant_id == period.c.tenant_id,
                    period_state.c.period_id == period.c.id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == entity_id,
            period_state.c.book_code == book_code,
            period_state.c.state.in_([member.value for member in POSTABLE_STATES]),
        )
        .order_by(period.c.start_date.desc())
        .limit(1)
    )
    found = session.execute(statement).scalar_one_or_none()
    return None if found is None else str(found)


def impact_summary(
    session: Session,
    current: Mapping[str, Any],
    bundle: InputBundle,
    output: OutputBundle,
    events: Sequence[EventIn],
    *,
    computed_at: datetime,
    book_code: str | None = None,
    criteria_met: bool = False,
) -> ImpactSummaryOut:
    """API-S-ImpactSummary of a dry run against the latest stored version of the primary book —
    or of ``book_code``, the book a manual adjustment names (04 T-SL-05; BUILD_SPEC CLO-12).

    Catch-up is the engine's: each obligation's ``catch_up_amount`` of the dry-run version, the
    catch-ups of the events first included in it (04 T-CON-11; ENGINE_SPEC_B S09-R-36) — never
    the change in cumulative revenue between the stored and the dry-run version, which counts the
    revenue recognised between their dates as a catch-up (PRD WLD-X-06: the K-02 prospective
    modification has catch-up 0.00). ``criteria_met`` (the activation of a NOT_A_CONTRACT
    contract; rev 1.105) reads the POL-013 catch-up instead — ``step1_catch_up``.

    [J] L4-1-Q-5: ``rpo_date`` is the latest effective date of the events; balances are empty and
    progress null until a cost-to-cost measure exists; ``journal_lines`` total the dry run's
    posting intents in the contract currency.

    Item MOD-PREVIEW-JOURNAL-RULE-1 (04 API-S-ImpactSummary rev 1.210): those intents are the
    cumulative targets of every postable period less what the subledger holds, so the lines are
    the entries the approval would post if it computed NOW — the change's effect together with
    any period amount not posted yet — and they move when a later period opens. The summary
    therefore states its instant (``computed_at``: the application clock of the request or job
    that ran the dry run — not the bundle's record-time cutoff, which is the later of that and
    the database's transaction timestamp) and the last period that computation could post into
    (``computed_period_key``).
    """
    contract_id = UUID(str(current["id"]))
    external_id = str(current["external_id"])
    currency = str(current["transaction_currency"]).strip()
    minor = ISO_4217[currency].minor_unit
    book_code = queries.primary_book(session) if book_code is None else book_code
    group_id = UUID(str(current["combination_group_id"]))
    before = bundles.previous_version(session, group_id, book_code)
    before_id = None if before is None else before["id"]
    book = next((item for item in output.books if item.book_code == book_code), None)
    after_version = None if book is None else book.contract_version
    replay_from = min(event.effective_date for event in events)
    rpo_date = max(event.effective_date for event in events)
    before_obligations = _before_obligations(session, before_id, contract_id)
    after_obligations: dict[str, tuple[Decimal, Decimal]] = {}
    after_catch_up: dict[str, Decimal] = {}
    scheduled_after = Decimal(0)
    for item in () if book is None else book.obligation_versions:
        key = _obligation_key(external_id, item.subject_key)
        if key is None:
            continue
        columns = item.columns
        after_obligations[key] = (
            _to_amount(columns.get("allocated_amount"), minor),
            _to_amount(columns.get("revenue_cum"), minor),
        )
        after_catch_up[key] = _to_amount(columns.get("catch_up_amount"), minor)
        scheduled_after += _to_amount(columns.get("scheduled_amount"), minor) + _to_amount(
            columns.get("awaiting_trigger_amount"), minor
        )
    if criteria_met:
        after_catch_up = step1_catch_up(session, current, output, book_code)
    keys = sorted(set(before_obligations) | set(after_obligations))
    catch_up = [
        ImpactCatchUpOut(
            obligation_key=key,
            treatment=None,
            amount=_money(after_catch_up.get(key, Decimal(0)), currency),
        )
        for key in keys
    ]
    entity_code = str(
        session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == current["contracting_entity_id"])
        ).scalar_one()
    )
    six = _six_periods(bundle, entity_code, replay_from)
    # Item PREVIEW-INLINE-SCOPE-1 (04 API-S-ImpactSummary rev 1.319; supervisor ruling R-64 (1)):
    # the stored schedule of the subject's own contract is read under the tenant's scope, as a
    # preview job reads it. A schedule line is a row of the entity that PERFORMS, and three
    # commands summarise in their caller's transaction — a void, an activation, an estimate
    # version's submission. Measured before: the void of a contract another entity performs,
    # asked by a preparer of the contracting entity alone, stored a preview with revenue before
    # 0.00 in six periods where it was 4,790.61 a month — the preview its approver certifies.
    with system_entity_scope(session):
        before_revenue = _before_revenue(session, before_id, contract_id)
    after_revenue: defaultdict[str, Decimal] = defaultdict(Decimal)
    for line in () if book is None else book.schedules:
        if str(getattr(line.schedule_kind, "value", line.schedule_kind)) != REVENUE:
            continue
        if not (
            line.subject_key == contract_subject_key(external_id)
            or line.subject_key.startswith(contract_subject_key(external_id) + "/")
        ):
            continue
        after_revenue[line.period_key] += minor_to_decimal(line.amount, minor)
    revenue = [
        ImpactRevenuePeriodOut(
            period_key=key,
            before=_money(before_revenue.get(key, Decimal(0)), currency),
            after=_money(after_revenue.get(key, Decimal(0)), currency),
            change=_money(
                after_revenue.get(key, Decimal(0)) - before_revenue.get(key, Decimal(0)), currency
            ),
        )
        for key in six
    ]
    after_columns = {} if after_version is None else dict(after_version.columns)
    price_after = _to_amount(after_columns.get("transaction_price"), minor)
    rpo_after = (
        _to_amount(after_columns["rpo_amount"], minor)
        if after_columns.get("rpo_amount") is not None
        else scheduled_after
    )
    try:
        posting, origin = posting_period(
            session,
            entity_id=UUID(str(current["contracting_entity_id"])),
            book_code=BookCode(book_code),
            effective_date=replay_from,
        )
        posting_key: str | None = posting.period_key
        origin_key = None if origin is None else origin.period_key
    except Problem:
        posting_key, origin_key = None, None
    return ImpactSummaryOut(
        transaction_price_before=_money(
            Decimal(0) if before is None else Decimal(before["transaction_price"]), currency
        ),
        transaction_price_after=_money(price_after, currency),
        catch_up_total=_money(
            sum((Decimal(item.amount.amount) for item in catch_up), Decimal(0)), currency
        ),
        catch_up_by_obligation=catch_up,
        remaining_allocation_before=[
            ImpactObligationAmountOut(
                obligation_key=key, amount=_money(allocated - revenue_cum, currency)
            )
            for key, (allocated, revenue_cum) in sorted(before_obligations.items())
        ],
        remaining_allocation_after=[
            ImpactObligationAmountOut(
                obligation_key=key, amount=_money(allocated - revenue_cum, currency)
            )
            for key, (allocated, revenue_cum) in sorted(after_obligations.items())
        ],
        revenue_by_period=revenue,
        rpo_before=_money(
            Decimal(0)
            if before is None or before["rpo_amount"] is None
            else Decimal(before["rpo_amount"]),
            currency,
        ),
        rpo_after=_money(rpo_after, currency),
        rpo_date=rpo_date,
        balances_before=[],
        balances_after=[],
        journal_lines=_journal_lines(session, output, book_code, currency),
        progress_before=None,
        progress_after=None,
        replay_from_date=replay_from,
        posting_period_key=posting_key,
        origin_period_key=origin_key,
        computed_at=computed_at,
        computed_period_key=latest_postable_period(
            session, UUID(str(current["contracting_entity_id"])), book_code
        ),
    )


def dry_run_summary(
    session: Session,
    current: Mapping[str, Any],
    known_at: datetime,
    pending: Sequence[EventIn],
    *,
    pending_contract_id: UUID,
    pending_modifications: Sequence[Mapping[str, Any]] = (),
    engine: computation.Engine | None = None,
    summarise: bool = True,
    book_code: str | None = None,
) -> tuple[InputBundle, OutputBundle, ImpactSummaryOut | None]:
    """DG-CMD-15 (D-98 140 Q-1): the ONE single-group dry run every preview uses — the group's
    bundle at ``known_at`` with ``pending`` appended to ``pending_contract_id`` (and, for CTR-17,
    the T-CON-06 rows of ``pending_modifications``), the engine once in ``DRY_RUN``, then
    API-S-ImpactSummary against the latest stored version. It writes nothing: the callers
    (``run_preview``, ``modifications.classify`` / ``run_preview``, CTR-16's contract provider
    iterating it per affected group) discard or store the summary themselves; a dry run's
    provenance is the bundle's ``input_sha256`` and the engine version, never a
    ``contract_computation`` row."""
    bundle = bundles.build(
        session,
        UUID(str(current["combination_group_id"])),
        known_at,
        pending,
        DRY_RUN,
        pending_contract_id=pending_contract_id,
        pending_modifications=pending_modifications,
    )
    run = engine if engine is not None else computation.default_engine()
    output = run(bundle)
    if not summarise:
        # D-98 140-A12 CLASSIFY-EMPTY-EVENTS-1: an event-free dry run (a classification carrying a
        # pending T-CON-06 row and NO applying event) has no replay window to summarise — the
        # proposal in ``output`` is its result; no event or amount is fabricated for a summary.
        return bundle, output, None
    return (
        bundle,
        output,
        impact_summary(
            session, current, bundle, output, pending, computed_at=known_at, book_code=book_code
        ),
    )


def run_preview(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``CONTRACT_COMPUTE`` in mode ``PREVIEW``: a dry run of the pending events; writes nothing."""
    contract_id = UUID(str(params["contract_id"]))
    items = [EventAppendItemIn.model_validate(item) for item in params["events"]]
    with ctx.unit_of_work() as uow:
        session = uow.session
        current = repo.get_contract(session, contract_id)
        if int(current["head_stream_version"]) != int(params["expected_stream_version"]):
            raise Problem("precondition-failed", STALE_MESSAGE, code=EVT_CODE)
        events = to_events(
            items,
            time_zone=_time_zone(session, UUID(str(current["contracting_entity_id"]))),
            is_manual=bool(params.get("is_manual", False)),
        )
        # Ruling R-77 (8): the preview computes what recording would append — for a not-probable
        # assessment of a DRAFT contract the not-a-contract gate, decided as the append decides it
        # (no lock: nothing is appended) — and says what became of the gate.
        events, gate = step1_outcome(uow, current, events, lock=False)
        check_bounds(session, current, events, known_at=uow.now)
        # ... and, behind a not-probable assessment, the release of the hold of the record it
        # cites (item STEP1-HOLD-RELEASE-1), counted like the gate.
        events = [*events, *_pending_hold_releases(session, current, uow.now, events)]
        _, _, summary = dry_run_summary(
            session, current, uow.now, events, pending_contract_id=contract_id
        )
        assert summary is not None  # a dry run with pending events summarises
        uow.discard()
    result: dict[str, Any] = {
        "href": CONTRACT_HREF.format(contract_id=contract_id),
        "counts": {"events": len(events)},
        "summary": summary.model_dump(mode="json"),
    }
    if gate is not None:
        result["step1_gate"] = gate.out().model_dump(mode="json")
    return JobOutcome(state="SUCCEEDED", result=result)


# --- voids and submissions -----------------------------------------------------------------------


def _event_type_text(value: object) -> str:
    return str(getattr(value, "value", value))


def void_refusal(event_type: object) -> str | None:
    """Why an event of ``event_type`` is not voided as an event — the sentence of 04 §16.3 "Voids
    on this route" (rev 1.231) — or None for one of ``VOIDABLE_TYPES``. The route and the approval
    of a stored void read it (``request_void``, ``check_stored``); a literal on no list is
    refused, so a type E-03 gains is not voidable until it is put on ``VOIDABLE_TYPES``."""
    text = _event_type_text(event_type)
    if text in {member.value for member in VOIDABLE_TYPES}:
        return None
    if text == VOIDED:
        return NOT_VOIDABLE
    if text == ADJUSTMENT_APPLIED:
        return ADJUSTMENT_NOT_VOIDABLE
    try:
        kind = ContractEventType(text)
    except ValueError:
        return TYPE_NOT_VOIDED
    return step1.not_voidable(kind) or OWN_COMMAND_VOIDS.get(kind, TYPE_NOT_VOIDED)


def void_refusals(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[UUID, str | None]:
    """API-S-Event ``void_refusal`` of each stored row (04 §16.3 "Voids on this route", rev
    1.273): None where ``request_void`` would take the event; else the sentence the route
    answers — ``NOT_VOIDABLE`` for an event a void already names (and, by its type, for a void),
    else ``void_refusal`` of its type. The two reads of an event answer it, so a screen asks the
    product whether a void can be requested and the list of voidable types keeps its one home; a
    type E-03 gains reads as refused until it is put on ``VOIDABLE_TYPES``. The route's own 409
    stays the backstop."""
    ids = [UUID(str(row["id"])) for row in rows]
    named = (
        {
            UUID(str(value))
            for value in session.scalars(
                select(contract_event.c.supersedes_event_id).where(
                    contract_event.c.supersedes_event_id.in_(ids)
                )
            )
        }
        if ids
        else set()
    )
    return {
        event_id: NOT_VOIDABLE if event_id in named else void_refusal(row["event_type"])
        for event_id, row in zip(ids, rows, strict=True)
    }


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def request_void(
    uow: UnitOfWork, *, event_id: UUID, body: EventVoidRequestIn
) -> SubmissionCreatedOut:
    """``POST /events/{id}/request-void`` (04 table 3.4-R; T-CON-24; DG-KRN-EVT-02)."""
    session = uow.session
    target = (
        session.execute(select(contract_event).where(contract_event.c.id == event_id))
        .mappings()
        .one_or_none()
    )
    if target is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, RECORD_PERMISSION, target["contracting_entity_id"])
    reason = body.reason_code.value
    if reason not in VOID_REASONS:
        label = REASON_LABELS.get(reason, reason)
        raise _failed(
            [
                _error(
                    "reason_code",
                    RULE_REASON,
                    f"The reason {label} cannot be used to void an event.",
                )
            ]
        )
    voided = session.execute(
        select(contract_event.c.id).where(contract_event.c.supersedes_event_id == event_id)
    ).first()
    if _event_type_text(target["event_type"]) == VOIDED or voided is not None:
        raise Problem("invalid-transition", NOT_VOIDABLE)
    not_voidable = step1.not_voidable(target["event_type"])
    if not_voidable is not None:
        # Ruling R-20 (family): a void of an assessment the gate read, of the gate or of the
        # activation replays Table 2.2-A under the MANUAL_EVENT approval — another book status
        # without the activation's checklist, routing and second step. The copy names what works
        # instead (ruling R-77 (1)).
        raise Problem("invalid-transition", not_voidable)
    if _event_type_text(target["event_type"]) == ADJUSTMENT_APPLIED:
        # The void would be replayed as "the adjustment never applied" while the adjustment's own
        # row, the register and the gate still read it as posted (module docstring).
        raise Problem(
            "invalid-transition",
            ADJUSTMENT_NOT_VOIDABLE,
            errors=[_error("event_type", RULE_ADJUSTMENT, ADJUSTMENT_NOT_VOIDABLE)],
        )
    own_command = void_refusal(target["event_type"])
    if own_command is not None:
        # Item EVT-VOID-OWN-COMMANDS-1: the event is the trace of a command with an approval of
        # its own; the sentence names what undoes it. Nothing is stored or routed.
        raise Problem(
            "invalid-transition",
            own_command,
            errors=[_error("event_type", RULE_ROUTE, own_command)],
        )
    item = {
        "event_type": VOIDED,
        "effective_date": target["effective_date"].isoformat(),
        "obligation_key": None,
        "payload": {"reason_code": reason, "comment": body.comment},
        "supersedes_event_id": str(event_id),
    }
    submission_id = new_id()
    principal = uow.principal
    session.execute(
        insert(event_submission).values(
            tenant_id=principal.tenant_id,
            id=submission_id,
            contract_id=target["contract_id"],
            contracting_entity_id=target["contracting_entity_id"],
            events=[item],
            status=ModificationStatus.DRAFT.value,
            comment=body.comment,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **_stamps(uow),
        )
    )
    transitions.apply(
        session,
        SUBMISSION_OBJECT,
        submission_id,
        to_status=ModificationStatus.SUBMITTED.value,
        expected_status=ModificationStatus.DRAFT.value,
        set_values=_stamps(uow),
    )
    external_id = session.execute(
        select(contract.c.external_id).where(contract.c.id == target["contract_id"])
    ).scalar_one()
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.MANUAL_EVENT,
        subject_id=submission_id,
        summary=(
            f"Void {_event_type_text(target['event_type'])} #{target['stream_version']} "
            f"of {external_id}"
        ),
        comment=body.comment,
        reason_code=reason,
    )
    request_id = UUID(str(request["id"]))
    transitions.apply(
        session,
        SUBMISSION_OBJECT,
        submission_id,
        to_status=None,
        set_values={"approval_request_id": request_id, **_stamps(uow)},
    )
    uow.audit(
        action=VOID_ACTION,
        object_type=SUBMISSION_OBJECT,
        object_id=submission_id,
        object_version="1",
        after={
            "event_id": str(event_id),
            "reason_code": reason,
            "approval_request_id": str(request_id),
        },
        reason_code=reason,
        comment=body.comment,
        approval_request_id=request_id,
        contract_id=UUID(str(target["contract_id"])),
    )
    return SubmissionCreatedOut(event_submission_id=submission_id, approval_request_id=request_id)


def submission_outs(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> list[EventSubmissionOut]:
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    return [
        EventSubmissionOut(
            id=row["id"],
            contract_id=row["contract_id"],
            contracting_entity_id=row["contracting_entity_id"],
            events=list(row["events"]),
            status=ModificationStatus(_event_type_text(row["status"])),
            comment=row["comment"],
            content_sha256=None
            if row["content_sha256"] is None
            else str(row["content_sha256"]).strip(),
            approval_request_id=row["approval_request_id"],
            applied_event_ids=list(row["applied_event_ids"] or ()),
            created_by=approval_queries.actor(
                row["created_by"], _event_type_text(row["created_by_kind"]), names
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def submissions_statement(
    *, contract_id: UUID | None = None, statuses: Iterable[ModificationStatus] = ()
) -> Select[Any]:
    statement = select(event_submission)
    if contract_id is not None:
        statement = statement.where(event_submission.c.contract_id == contract_id)
    wanted = [value.value for value in statuses]
    if wanted:
        statement = statement.where(event_submission.c.status.in_(wanted))
    return statement


def get_submission(session: Session, submission_id: UUID) -> EventSubmissionOut:
    row = (
        session.execute(select(event_submission).where(event_submission.c.id == submission_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    (item,) = submission_outs(session, [dict(row)])
    return item


def withdraw_submission(
    uow: UnitOfWork, *, submission_id: UUID, body: SubmissionWithdrawIn
) -> EventSubmissionOut:
    """``POST /event-submissions/{id}/withdraw``: the preparer withdraws (T-CON-24 → VOIDED)."""
    session = uow.session
    row = (
        session.execute(
            select(event_submission).where(event_submission.c.id == submission_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, RECORD_PERMISSION, row["contracting_entity_id"])
    status = _event_type_text(row["status"])
    if status == ModificationStatus.SUBMITTED.value and row["approval_request_id"] is not None:
        approvals.withdraw(
            uow,
            approval_request_id=UUID(str(row["approval_request_id"])),
            comment=body.comment,
            through_subject=True,
        )
    elif status == ModificationStatus.DRAFT.value:
        if uow.principal.id is None or uow.principal.id != row["created_by"]:
            raise Problem("forbidden", "Only the preparer can withdraw this submission.")
        transitions.apply(
            session,
            SUBMISSION_OBJECT,
            submission_id,
            to_status=ModificationStatus.VOIDED.value,
            expected_status=ModificationStatus.DRAFT.value,
            set_values=_stamps(uow),
        )
    else:
        raise Problem(
            "invalid-transition", "Only a draft or submitted submission can be withdrawn."
        )
    uow.audit(
        action=WITHDRAW_ACTION,
        object_type=SUBMISSION_OBJECT,
        object_id=submission_id,
        before={"status": status},
        after={"status": ModificationStatus.VOIDED.value},
        comment=body.comment,
        contract_id=UUID(str(row["contract_id"])),
    )
    return get_submission(session, submission_id)


# --- the lifecycle of an event submission (DG-KRN-EVT-02 rev 1.177) -------------------------------


def check_stored(uow: UnitOfWork, current: Mapping[str, Any], events: Sequence[EventIn]) -> None:
    """A stored batch is checked again where it is appended (04 T-CON-24 rev 1.194; BUILD_SPEC
    CTR-6; ``subjects.apply_event_submission`` calls it under the submission, group and contract
    locks). The batch was validated against the stream as it stood when it was stored; by the
    approval another request may have been approved, an integration may have delivered, a
    period locked, the event a void names voided. The field locks need no second look: a
    stored payload cannot name a locked member (``locks.LOCKED_MEMBERS`` are no members of the
    payload model). Measured before this check: two pending deliveries of 60 units against 80
    remaining were both approved — 240 of 200 delivered, a quarantined computation (control
    CTL-008 by-passed through the approval).

    Rev 1.231 (04 §16.3; dev-guide DG-KRN-EVT-02 rev 1.222): what the route no longer stores is
    not appended either — the void of an event that has a command of its own (``void_refusal``)
    and an attribute change that names an SSP version (``locks.names_version_pin``) — so a
    submission stored before either rule, or built below the route, is stale.

    A finding raises ``StaleBasis``: ``decide`` undoes the decision, voids the request
    ``STALE_SUBJECT`` and answers 409 ``stale-approval`` (PRD ERR-04); the preparer records the
    events again and meets the finding by name at the route."""
    session = uow.session
    voided = [event.supersedes_event_id for event in events if event.supersedes_event_id]
    try:
        if voided and (
            session.execute(
                select(contract_event.c.id)
                .where(
                    or_(
                        contract_event.c.supersedes_event_id.in_(voided),
                        and_(
                            contract_event.c.id.in_(voided),
                            contract_event.c.event_type == VOIDED,
                        ),
                    )
                )
                .limit(1)
            ).first()
            is not None
        ):
            raise Problem("invalid-transition", NOT_VOIDABLE)
        if voided:
            for event_type in session.scalars(
                select(contract_event.c.event_type).where(contract_event.c.id.in_(voided))
            ):
                own_command = void_refusal(event_type)
                if own_command is not None:
                    raise Problem("invalid-transition", own_command)
        if locks.names_version_pin(events):
            raise Problem("validation-failed", locks.VERSION_PIN_DETAIL)
        _check_batch(uow, current, events)
    except approvals.StaleBasis:
        raise
    except Problem as problem:
        raise approvals.StaleBasis() from problem


def _approve_submission(uow: UnitOfWork, submission_id: UUID, request_id: UUID) -> None:
    """``on_approved`` of ``MANUAL_EVENT`` and ``ATTRIBUTE_CHANGE``: the stored batch is checked
    again (``check_stored``), appended by the SYSTEM principal on behalf of the preparer, and the
    group is computed as after an append — at once, or by ``CONTRACT_COMPUTE`` beyond the budget
    (05 RCP-18). A void's reversal is therefore posted with its approval.

    The evidence (item EVT-EVIDENCE-1; 04 T-CON-24 and T-PLT-29 rev 1.268). Under the submission's
    locks and before the basis is read again, the files of the request's live attachments are
    locked and read (``attachments.readable_evidence``): one that was shredded — only an approved
    shred reaches the evidence of a pending request — makes the request stale, as for a manual
    adjustment. Where the stored batch is checked again, a person's event that needs evidence
    (REQ-DAT-014) with no readable file left — its requester voided the attachment while the
    request waited — is refused 422 and the request stays pending: she attaches again. The
    evidence that can be read is then attached to every appended event by the SYSTEM principal
    that appended them, acting for the preparer."""
    session = uow.session
    contract_id, preparer_kind = session.execute(
        select(event_submission.c.contract_id, event_submission.c.created_by_kind).where(
            event_submission.c.id == submission_id
        )
    ).one()
    by_person = (
        str(getattr(preparer_kind, "value", preparer_kind)) != PrincipalKind.API_CLIENT.value
    )
    evidence: list[UUID] = []

    def locked(inner: UnitOfWork) -> None:
        files, intact = attachments.readable_evidence(inner.session, EVIDENCE_SUBJECT, request_id)
        if not intact:
            raise approvals.StaleBasis()
        evidence.extend(files)

    def checked(inner: UnitOfWork, current: Mapping[str, Any], events: Sequence[EventIn]) -> None:
        check_stored(inner, current, events)
        if by_person and not evidence and any(_needs_evidence(event) for event in events):
            raise _failed([_error("evidence_file_ids", RULE_EVIDENCE, EVIDENCE_GONE)])

    def attached(system: UnitOfWork, rows: Sequence[Mapping[str, Any]]) -> None:
        _attach_to_events(
            system,
            evidence,
            rows,
            contract_id=UUID(str(contract_id)),
            approval_request_id=request_id,
        )

    apply_event_submission(
        uow, submission_id, request_id, check=checked, before_basis=locked, applied=attached
    )
    holds.compute(uow, repo.get_contract(session, UUID(str(contract_id))))


def preparer_entities(session: Session, submission_id: UUID) -> SubjectEntities:
    """The entity the preparer of an event submission is held to (item
    MANUAL-EVENT-PREPARER-SCOPE-1; 04 §16.10 rev 1.269; ``SubjectSpec.preparer_entities``): the
    contracting entity of the contract the events are recorded on (T-CON-24
    ``contracting_entity_id``), read from the stored submission — never from the caller — where
    the engine reads it, under the tenant's SYSTEM scope. The request stays bound to the
    contracting entities of the contract's group, for its readers and its deciders. Measured
    before the rule: a Revenue Accountant of one entity of a combination group of two could not
    record her own contract's progress — 403, "This item belongs to legal entities outside your
    roles" — which she did before BUILD_SPEC CTR-6 made a manual event a request."""
    found = session.execute(
        select(event_submission.c.contracting_entity_id).where(
            event_submission.c.id == submission_id
        )
    ).scalar_one_or_none()
    if found is None:
        raise Problem("not-found")
    return SubjectEntities(frozenset({UUID(str(found))}))


for _subject in (ApprovalSubjectType.MANUAL_EVENT, ApprovalSubjectType.ATTRIBUTE_CHANGE):
    register_lifecycle(
        _subject,
        SubjectLifecycle(
            on_approved=_approve_submission,
            on_rejected=reject_event_submission,
            on_voided=void_event_submission,
            preparer_entities=preparer_entities,
        ),
    )
