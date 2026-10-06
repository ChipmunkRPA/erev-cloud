"""Activation checklist, submit-activation, the approved activation and distinct reviews (04 table
15.4-I, §16.1 contract commands, §16.14 API-S-ActivationChecklist, §15.2
``activation-checklist-failed``; PRD SM-02, BR-CON-01, §2.5 routing rows ``CONTRACT_ACTIVATION``,
IMP-09, IMP-100 to IMP-105, ERR-31; dev-guide DG-CMD-04, DG-CMD-09, DG-KRN-APR-01; 03 REQ-CON-004
to REQ-CON-006, REQ-REF-014, REQ-POB-001; BUILD_SPEC CTR-7, CTR-9, BS3-D-12, BS3-D-19).

``evaluate(session, contract)`` answers the seven items of table 15.4-I in table order without
storing them:

- ``MANDATORY_FIELDS``: the header and line members of the latest booking are set;
- ``SOURCE_REFERENCE``: ``document_ref`` is not blank (IMP-100);
- ``PRODUCT_TEMPLATE_SSP``: every obligation's product is active and its default template has a
  PUBLISHED version; while the group's latest computation was refused, an open
  ``SSP_KEY_NOT_FOUND`` or ``PRODUCT_UNMAPPED`` item of the group fails the obligation it names,
  with the IMP-09 key (IMP-101; REQ-REF-014; TC-setup-20);
- ``DISTINCT_REVIEW``: [J] L4-1-Q-19: in a contract of two or more obligations, an obligation whose
  template concludes ``distinct`` or ``nondistinct`` needs a REVIEWED ``POB_DISTINCT_OVERRIDE``
  record of the obligation; a ``series`` template records its conclusion itself (PRD J-03.4,
  J-03-ALT-1) (IMP-102);
- ``COMBINATION_SUGGESTIONS``: no open ``COMBINATION_SUGGESTED`` item names the contract (IMP-103);
  the line of an open one names the other contract to a session that reads it, and a stored
  line to the readers of the contract's own entity (item ACT-CHECKLIST-SUGGESTION-SCOPE-1);
- ``JUDGEMENT_RECORDS``: no judgement record of the contract is DRAFT, SUBMITTED or REJECTED
  (IMP-104);
- ``STEP1_RECORD``: every enabled book has a ``COLLECTIBILITY_ASSESSED`` event with a REVIEWED
  record that serves it (its contract, topic and book), and a ``SIGNIFICANT_CHANGE_FLAGGED``
  after it needs a new assessment (CTR-7; IMP-105); a contract that is NOT_A_CONTRACT also needs
  the criteria-met re-assessment of at least one enabled book; and for a DRAFT contract the
  assessment in force at the inception date is each book's latest (rulings R-20 (c), R-77 (2),
  (3), (7); ``erev_api.events.step1``).

``submit_activation`` is the decision command of DG-CMD-09: it evaluates the checklist (409
``activation-checklist-failed`` naming each failed code), computes a dry run with the pending
``CONTRACT_ACTIVATED`` (an ``EngineError`` is 422 ``validation-failed`` with the engine code and
nothing is written), and routes ``CONTRACT_ACTIVATION`` with the dry run as impact preview. [J]
L4-1-Q-18: SM-02 DRAFT → PENDING_REVIEW appends no event, and DB-18 admits no header change without
one, so the stored status stays DRAFT and the read model answers PENDING_REVIEW while the request is
PENDING; ``contract.pending_review`` and ``contract.draft`` are audited. [J] L4-1-Q-20: only a
request without routing flags is offered to the auto-approval rules. On approval ``activate`` runs
in the deciding transaction: the gate again, ``CONTRACT_ACTIVATED`` appended by SYSTEM on behalf of
the preparer (the header projection stores the checklist), and the computation persisted, failing
closed.

Supervisor ruling R-20 (c) (security findings SN-12 / SN-13; PRD SM-02 rev 1.34; 04 E-03 and §16.1
rev 1.105): ``CONTRACT_CRITERIA_MET`` is appended by the approved activation alone. The command
admits a contract that is NOT_A_CONTRACT whose criteria-met re-assessment is recorded — for each
book that moves, its latest ``COLLECTIBILITY_ASSESSED``: probable, dated on or after the
not-a-contract gate, with a REVIEWED judgement record. The same checklist, routing flags and second
step apply; the dry run carries ``CONTRACT_CRITERIA_MET`` per moving book (effective the
re-assessment's date) and ``CONTRACT_ACTIVATED`` pending; the preview shows the books that move and
the POL-013 catch-up; the request's subject content states the criteria-met events (REQ-PLT-014).
The stored status stays NOT_A_CONTRACT while the request is pending (read model PENDING_REVIEW)
and after a rejection or a void.

Supervisor ruling R-61 (c) (04 §16.1, §16.10 rev 1.126; PRD §2.5 rev 1.55): a criteria-met
activation is not a standard item (REQ-PLT-016), so its request is never offered to the
auto-approval rules — a person decides it, whatever the routing flags and whoever wrote the stream.
Ruling R-77 (2): nor is an activation that leaves a book NOT_A_CONTRACT on a not-probable
assessment (``books_left_not_a_contract``). Ruling R-77 (9): the stored status of a contract in
review is DRAFT or NOT_A_CONTRACT, so a stored PENDING_REVIEW is neither submitted nor activated.

Supervisor ruling R-102 (a) (04 §16.1, §16.10, table 15.4-I rev 1.150; PRD SM-02 rev 1.79; item
CTR-STEP1-REENTRY-1): a book that Table 2.2-A put out as not probable under an ACTIVE header —
books that differed at the activation, a 606-10-25-5 reassessment — returns to recognition by the
same approved path. ``submit_activation`` admits the ACTIVE contract when a book moves
(``step1.criteria_met``); the request is never auto-approved; its dry run confirms each book from
the engine's status trace (``_confirm_reentry``): the pending ``CONTRACT_CRITERIA_MET`` takes the
book from NOT_A_CONTRACT / NOT_PROBABLE — the segment the event of the Step 1 replay began — to
ACTIVE / CRITERIA_MET. ``activate`` confirms again under its locks and appends the
``CONTRACT_CRITERIA_MET`` events alone: no ``CONTRACT_ACTIVATED``, and the header does not move.
A book that is not a contract for another reason (no commercial substance; mutual termination
rights, unperformed) is refused by name (``STEP1_REENTRY_OTHER_REASON``, PRD IMP-133): a known
limitation.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

from erev_engine.bundle import FxRateInput, InputBundle, OutputBundle
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, minor_to_decimal
from erev_engine.stages.s01_canonicalize import contract_subject_key
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    ABOVE_CONTROLLER_THRESHOLD,
    ABOVE_THRESHOLD,
    ACTIVATION_THRESHOLD,
    CONTROLLER_THRESHOLD,
    RATE_NOT_PUBLISHED,
    THRESHOLD_CURRENCY,
    SubjectLifecycle,
    contract_activation_total,
    register_lifecycle,
)
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.db import transitions
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_request,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    estimate,
    exception_item,
    import_upload,
    judgement_record,
    obligation,
    obligation_version,
    pob_template_version,
    policy_override,
    product,
)
from erev_api.domain.contracts import bundles, computation, queries, repo
from erev_api.domain.contracts.events import impact_summary, step1_catch_up_totals
from erev_api.domain.imports.exceptions import OPEN_STATUSES, finding_title
from erev_api.domain.policies import judgements
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ComputationStatus,
    ComputationTrigger,
    ConfigStatus,
    ContractEventType,
    ContractStatus,
    Distinctness,
    EstimateKind,
    JudgementStatus,
    JudgementTopic,
    ObligationKind,
    PrincipalKind,
    ScopeFlag,
    SourceSystem,
)
from erev_api.events import step1
from erev_api.events.payloads import (
    ChecklistItemV1,
    ContractActivatedV1,
    ContractCriteriaMetV1,
)
from erev_api.events.step1 import CriteriaMet
from erev_api.events.stream import EventIn, append_events
from erev_api.explain.narratives import format_date
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.contracts import (
    ActivationChecklistItemOut,
    ActivationChecklistOut,
    ContractOut,
    DistinctReviewIn,
    DistinctReviewOut,
    SubmitActivationIn,
)
from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn
from erev_api.uow import UnitOfWork

__all__ = [
    "CODES",
    "STEP1_RECORD",
    "Checklist",
    "ChecklistItem",
    "Judged",
    "Measured",
    "RoutingFacts",
    "Submitted",
    "activate",
    "activation_amount",
    "activation_flags",
    "booked_amount",
    "books_left_not_a_contract",
    "checklist_out",
    "checklist_problem",
    "criteria_met",
    "evaluate",
    "judged",
    "measured_by",
    "record_distinct_review",
    "routing_facts",
    "step1_record",
    "stored_measure",
    "submit_activation",
    "threshold_flags",
]

CREATE_PERMISSION: Final = "contract.create"
OBJECT_TYPE: Final = "contract"
MANDATORY_FIELDS: Final = "MANDATORY_FIELDS"
SOURCE_REFERENCE: Final = "SOURCE_REFERENCE"
PRODUCT_TEMPLATE_SSP: Final = "PRODUCT_TEMPLATE_SSP"
DISTINCT_REVIEW: Final = "DISTINCT_REVIEW"
COMBINATION_SUGGESTIONS: Final = "COMBINATION_SUGGESTIONS"
JUDGEMENT_RECORDS: Final = "JUDGEMENT_RECORDS"
STEP1_RECORD: Final = "STEP1_RECORD"
CODES: Final = (
    MANDATORY_FIELDS,
    SOURCE_REFERENCE,
    PRODUCT_TEMPLATE_SSP,
    DISTINCT_REVIEW,
    COMBINATION_SUGGESTIONS,
    JUDGEMENT_RECORDS,
    STEP1_RECORD,
)
# PRD §5.5 IMP copy (SCREENS §4.9.8).
MANDATORY_MESSAGE: Final = "Mandatory fields not set: {labels}."
SOURCE_MESSAGE: Final = "No contract reference is recorded."  # IMP-100
TEMPLATE_MESSAGE: Final = "No product, template or SSP for {key} ({product})."  # IMP-101
SSP_MESSAGE: Final = "No approved SSP for {product} / {stratification} / {version}."  # IMP-09
DISTINCT_MESSAGE: Final = "Distinct review not recorded for {key} ({product})."  # IMP-102
SUGGESTION_MESSAGE: Final = "Combination suggestion with {external_id} is open."  # IMP-103
# IMP-103's two substitutions for the other contract's external id (PRD rev 1.181; item
# ACT-CHECKLIST-SUGGESTION-SCOPE-1): for a session that does not read that contract (the
# phrase of ruling R-28, SN-2), and in a stored line when the contract is of another
# contracting entity than the one the line is stored for.
CONTRACT_OUTSIDE: Final = "a contract outside your entities"
CONTRACT_OF_ANOTHER_ENTITY: Final = "a contract of another entity"
JUDGEMENT_MESSAGE: Final = "Judgement record required: {topic}."  # IMP-104
# Item JDG-REJECTED-EXIT-1 (04 table 15.4-I ``JUDGEMENT_RECORD_REJECTED``): a rejected record is
# named by its number, with its two roads. "Required" was true of it and sent nobody to it — a
# contract with a newer reviewed record of the same topic read as if that review were missing.
JUDGEMENT_REJECTED_MESSAGE: Final = (  # IMP-145
    "Judgement record {judgement_no} ({topic}) was rejected. Discard it, or have its author "
    "revise it and send it for review again."
)
STEP1_MESSAGE: Final = "Step 1 review not recorded."  # IMP-105
STEP1_NOT_IN_FORCE_MESSAGE: Final = (  # IMP-131 (supervisor rulings R-77 (2), R-82 (g))
    "The Step 1 assessment of {book} is not the one in force at the inception date "
    "({inception_date}). Record it again, dated on or before that date."
)
# Item STEP1-CITE-LATEST-1, the activation's half (04 table 15.4-I ``STEP1_RECORD_OVERTAKEN``): the
# events route asks for the newest review when an assessment is recorded; a record can be
# overtaken after that, and an overtaken record is still REVIEWED.
STEP1_OVERTAKEN_MESSAGE: Final = (
    "The Step 1 assessment of {book} rests on judgement record {judgement_no}, which the review "
    "of judgement record {later_judgement_no} has overtaken. Record the assessment on the latest "
    "review."
)
FAILED_DETAIL: Final = "{count} checklist {noun} not passed: {codes}."  # ERR-31
# PRD ERR-07.
STALE_CONTRACT: Final = (
    "This record changed since you opened it. Reload to see the latest version, then try again."
)
NOT_SUBMITTABLE: Final = (
    "Only a draft contract, a contract that is not a contract, or an active contract with a book "
    "that is not a contract can be submitted for activation."
)
ALREADY_IN_REVIEW: Final = "This contract is already waiting for activation approval."
NOT_ACTIVATABLE: Final = (
    "Only a draft contract, a contract that is not a contract, or an active contract with a book "
    "that is not a contract can be activated."
)
# Supervisor ruling R-102 (a), Q1 (04 table 15.4-I ``STEP1_REENTRY_OTHER_REASON``; PRD IMP-133).
STEP1_OTHER_REASON_MESSAGE: Final = (
    "{book} is not a contract for a reason other than collectibility ({reason}). Recording "
    "criteria met does not activate it."
)
# ENGINE_SPEC §2.1 ``StatusSegment.reason`` of a NOT_A_CONTRACT segment, as the copy names it.
OTHER_REASONS: Final[Mapping[str, str]] = {
    "NO_COMMERCIAL_SUBSTANCE": "no commercial substance",
    "MUTUAL_TERMINATION_UNPERFORMED": (
        "both parties can end it without penalty and nothing is performed"
    ),
}
NOT_CONFIRMED: Final = (
    "The computation does not confirm that {books} would leave the not-a-contract status. "
    "Nothing was submitted."
)
# The engine's status trace (ENGINE_SPEC §2.1; stage 02 ``_status_node``): one node per status
# segment, measure ``status@<event key>``, params ``status`` and ``reason``.
STATUS_FORMULA: Final = "step1.status.v1"
STATUS_MEASURE: Final = "status@"
REASON_NOT_PROBABLE: Final = "NOT_PROBABLE"
REASON_CRITERIA_MET: Final = "CRITERIA_MET"
CRITERIA_NOT_MET: Final = (
    "No book of this contract has a reviewed criteria-met assessment. Record the assessment first."
)
REGROUPED: Final = repo.REGROUPED  # D-98 candidate 101a; the message lives with the helper
OBLIGATION_UNKNOWN: Final = "The contract has no obligation {key}."
INTEGRATES_REQUIRED: Final = "Name the obligation this one integrates into."
RULE_REVIEW: Final = "T-CON-19"
DRY_RUN: Final = "DRY_RUN"
SSP_CODES: Final = ("SSP_KEY_NOT_FOUND", "PRODUCT_UNMAPPED")
SUGGESTED: Final = "COMBINATION_SUGGESTED"
REVIEWABLE: Final = frozenset({Distinctness.DISTINCT.value, Distinctness.NONDISTINCT.value})
UNREVIEWED: Final = (
    JudgementStatus.DRAFT.value,
    JudgementStatus.SUBMITTED.value,
    JudgementStatus.REJECTED.value,
)
# SM-02: DRAFT → PENDING_REVIEW → ACTIVE and, since ruling R-20 (c), NOT_A_CONTRACT →
# PENDING_REVIEW → ACTIVE — the criteria-met activation (PRD rev 1.34; 04 §16.1 rev 1.105). The
# STORED status of a contract in review is DRAFT or NOT_A_CONTRACT (L4-1-Q-18; T-CON-01): no path
# stores PENDING_REVIEW outside the approved activation's own two appends, so a stored
# PENDING_REVIEW is not admitted (ruling R-77 (9)). Ruling R-102 (a): an ACTIVE contract is
# admitted for the criteria-met path of a book that is not a contract (SM-02 ACTIVE → ACTIVE,
# unchanged); the commands refuse one of which no book moves.
SUBMITTABLE: Final = (
    ContractStatus.DRAFT.value,
    ContractStatus.NOT_A_CONTRACT.value,
    ContractStatus.ACTIVE.value,
)
# [J] L4-1-Q-20: routing flags of CONTRACT_ACTIVATION (04 T-PLT-17 examples and PRD §2.5 rows).
MANUAL_ENTRY: Final = "MANUAL_ENTRY"
NON_STANDARD_TERMS: Final = "NON_STANDARD_TERMS"
# Item ACT-FLAGS-1 (04 T-PLT-17, §16.10 rev 1.287; PRD §2.5 rev 1.194): the flags 04 names and no
# request carried, and ``TERMS_NOT_STATED`` for what a booking does not say. The flag of an amount
# that cannot be stated, ``RATE_NOT_PUBLISHED``, is the subject registry's: it is a second-step
# flag of the subject.
MATERIAL_RIGHT: Final = "MATERIAL_RIGHT"
VARIABLE_CONSIDERATION: Final = "VARIABLE_CONSIDERATION"
NEW_SKU: Final = "NEW_SKU"
SIDE_LETTER: Final = "SIDE_LETTER"
TERMS_NOT_STATED: Final = "TERMS_NOT_STATED"
CONVENIENCE_PARTIES: Final = frozenset({"CUSTOMER", "BOTH"})
# The E-09 kinds that estimate consideration (ASC 606-10-32-6; breakage 606-10-55-48): each sets
# VARIABLE_CONSIDERATION, whatever the status of the element's versions.
CONSIDERATION_ESTIMATES: Final = (
    EstimateKind.VARIABLE_CONSIDERATION.value,
    EstimateKind.RETURN_RATE.value,
    EstimateKind.IMPLICIT_PRICE_CONCESSION.value,
    EstimateKind.BREAKAGE.value,
    EstimateKind.ROYALTY_ACCRUAL.value,
)
# A product is known to the workspace once a contract that was activated holds a line of it; a
# draft, a contract that is not a contract and a voided one make no product known.
ACTIVATED: Final = (
    ContractStatus.ACTIVE.value,
    ContractStatus.COMPLETED.value,
    ContractStatus.TERMINATED.value,
)
HEADER_FIELDS: Final = (
    ("external_id", "external id"),
    ("customer_id", "customer"),
    ("contracting_entity_code", "contracting entity"),
    ("transaction_currency", "currency"),
    ("inception_date", "inception date"),
)
LINE_FIELDS: Final = (
    ("product_code", "product"),
    ("quantity", "quantity"),
    ("total_price", "total price"),
)
CONCLUSIONS: Final[Mapping[str, str]] = {
    Distinctness.DISTINCT.value: "{key} ({product}) is a distinct performance obligation.",
    Distinctness.NONDISTINCT.value: (
        "{key} ({product}) is not distinct and integrates into {other}."
    ),
    Distinctness.SERIES.value: "{key} ({product}) is a series of distinct goods or services.",
}


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    """One API-S-ActivationChecklist item."""

    code: str
    passed: bool
    detail: str | None


@dataclass(frozen=True, slots=True)
class Checklist:
    """API-S-ActivationChecklist: the items of table 15.4-I in table order."""

    items: tuple[ChecklistItem, ...]
    evaluated_at: datetime

    @property
    def failed(self) -> tuple[ChecklistItem, ...]:
        return tuple(item for item in self.items if not item.passed)

    def payload(self) -> tuple[ChecklistItemV1, ...]:
        """The ``CONTRACT_ACTIVATED.checklist`` members (04 §16.3)."""
        return tuple(
            ChecklistItemV1(code=item.code, passed=item.passed, detail=item.detail)
            for item in self.items
        )


@dataclass(frozen=True, slots=True)
class Submitted:
    contract: ContractOut
    approval_request_id: UUID


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _item(code: str, lines: Sequence[str]) -> ChecklistItem:
    return ChecklistItem(code=code, passed=not lines, detail=" ".join(lines) if lines else None)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


# --- checklist items -----------------------------------------------------------------------------


# The books enabled for the tenant and the entity; every Step 1 reader shares ``events.step1``.
enabled_books = step1.enabled_books


def criteria_met(session: Session, contract_row: Mapping[str, Any]) -> list[CriteriaMet]:
    """The books the approved activation of a NOT_A_CONTRACT contract moves, in book order (ruling
    R-20 (c); ``erev_api.events.step1``); empty for a contract in any other stored status."""
    return step1.criteria_met(
        session,
        contract_id=_uuid(contract_row["id"]),
        status=contract_row["status"],
        entity_id=_uuid(contract_row["contracting_entity_id"]),
    )


def step1_record(session: Session, contract_row: Mapping[str, Any]) -> ChecklistItem:
    """04 table 15.4-I ``STEP1_RECORD`` of a visible contract (BUILD_SPEC CTR-7): every enabled
    book's latest assessment rests on a REVIEWED record that serves it — a record of the contract,
    of that book or of no book, of a topic that fits the outcome (ruling R-77 (7):
    ``step1.reviewed``). Ruling R-20 (c): a contract that is NOT_A_CONTRACT also needs the
    criteria-met re-assessment of at least one enabled book (``step1.criteria_met``), since its
    activation moves exactly those books. Ruling R-77 (2): a DRAFT contract is activated at its
    inception date, where Table 2.2-A reads the assessment in force; per enabled book that
    assessment must be the book's latest — one dated after inception would sort behind the
    activation event and the engine would activate the book against it. The item then says so
    per book (IMP-131, ``STEP1_ASSESSMENT_NOT_IN_FORCE``; ruling R-82 (g)); IMP-105 keeps its copy
    for a review that is not recorded. Ruling R-102 (a): for an ACTIVE contract of which a book
    is out as not probable (``Step1Stream.out``) the item reads "at least one such book has its
    criteria-met re-assessment" and asks nothing of the books that stay as they are — a book
    kept after the activation has no assessment at all. Item STEP1-CITE-LATEST-1: the latest
    assessment of a book does not rest on a record that a later review of the other Step 1
    topic has overtaken (``step1.overtaken``) — the route refuses such a record when the
    assessment is recorded, and this item when the record was overtaken afterwards; it says so
    per book (``STEP1_RECORD_OVERTAKEN``)."""
    contract_id = _uuid(contract_row["id"])
    stream = step1.read(session, contract_id)
    known = step1.records(
        session, [item.judgement_record_id for item in stream.latest.values() if item is not None]
    )
    overtaking = step1.overtaken(session, known.values())

    def overtaken_line(code: str) -> str | None:
        """The sentence for ``code`` when its latest assessment rests on an overtaken record."""
        item = stream.latest.get(code)
        record = None if item is None else known.get(str(item.judgement_record_id))
        by = None if record is None or record.id is None else overtaking.get(record.id)
        if record is None or by is None:
            return None
        return STEP1_OVERTAKEN_MESSAGE.format(
            book=code, judgement_no=record.judgement_no, later_judgement_no=by.judgement_no
        )

    books = step1.enabled_books(session, _uuid(contract_row["contracting_entity_id"]))
    status = _text(contract_row["status"])
    # Rulings R-113 (f), R-115 (f) (04 T-CON-19; table 15.4-I ``STEP1_CRITERION_NOT_MET``, PRD
    # IMP-135): no activation while the latest assessment of ANY enabled book — a not-probable
    # one too — rests on a review that answers No to criterion (a), (b) or (c), or, for the
    # re-assessment of a book that is out, to (d). One sentence per criterion, by its label.
    # Item STEP1-HOLD-RELEASE-1 (04 §16.3 (b) rev 1.209): a PROBABLE assessment is also read for
    # (e) — one that rests on a review answering "collection not probable" activates nothing.
    answered_no: set[str] = set()
    for code in books:
        item = stream.latest.get(code)
        if item is not None:
            answered_no.update(
                step1.unmet(
                    known.get(str(item.judgement_record_id)),
                    criteria_met=item.is_probable and code in stream.out,
                    probable=item.is_probable,
                )
            )
    named = [
        step1.CRITERION_NOT_MET.format(criterion_label=step1.CRITERION_LABELS[key])
        for key in sorted(answered_no)
    ]
    if status == ContractStatus.ACTIVE.value and any(code in stream.out for code in books):
        if named:
            return _item(STEP1_RECORD, named)
        if criteria_met(session, contract_row):
            return _item(STEP1_RECORD, [])
        # No book moves. Where a book that is out rests on an overtaken record, that is why.
        stale = [
            line
            for code in books
            if code in stream.out and (line := overtaken_line(code)) is not None
        ]
        return _item(STEP1_RECORD, stale or [STEP1_MESSAGE])
    inception = contract_row["inception_date"]
    lines: list[str] = []
    missing = not books
    for code in books:
        item = stream.latest.get(code)
        if item is None or not step1.reviewed(
            known.get(str(item.judgement_record_id)),
            contract_id=contract_id,
            book_code=code,
            probable=item.is_probable,
        ):
            missing = True
        elif (line := overtaken_line(code)) is not None:
            lines.append(line)
        elif status == ContractStatus.DRAFT.value and not step1.current_at(stream, code, inception):
            lines.append(
                STEP1_NOT_IN_FORCE_MESSAGE.format(
                    book=code, inception_date=format_date(inception.isoformat())
                )
            )
    if not missing and not lines and not named and status == ContractStatus.NOT_A_CONTRACT.value:
        missing = not criteria_met(session, contract_row)
    if missing:
        lines.insert(0, STEP1_MESSAGE)
    return _item(STEP1_RECORD, [*lines, *named])


def books_left_not_a_contract(session: Session, contract_row: Mapping[str, Any]) -> list[str]:
    """Ruling R-77 (2): the enabled books whose latest assessment is not probable — the books an
    approved activation leaves NOT_A_CONTRACT. An activation that carries one is not a standard
    item (REQ-PLT-016): ``submit_activation`` withholds it from the auto-approval rules."""
    stream = step1.read(session, _uuid(contract_row["id"]))
    books = step1.enabled_books(session, _uuid(contract_row["contracting_entity_id"]))
    return step1.not_probable_books(stream, books)


def _latest_booking(session: Session, contract_id: UUID) -> Mapping[str, Any]:
    rows = repo.stream(session, contract_id)
    voided = {row["supersedes_event_id"] for row in rows if row["supersedes_event_id"]}
    bookings = [
        row
        for row in rows
        if _text(row["event_type"]) == ContractEventType.CONTRACT_BOOKED.value
        and row["id"] not in voided
    ]
    return dict(bookings[-1]["payload"] or {}) if bookings else {}


def mandatory_fields(session: Session, contract_row: Mapping[str, Any]) -> ChecklistItem:
    """``MANDATORY_FIELDS``: the header and line members of the latest booking."""
    booking = _latest_booking(session, _uuid(contract_row["id"]))
    labels = [label for name, label in HEADER_FIELDS if _blank(booking.get(name))]
    lines = booking.get("lines") or []
    if not lines:
        labels.append("lines")
    for index, line in enumerate(lines, start=1):
        key = line.get("obligation_key") or f"line {index}"
        labels += [f"{key} {label}" for name, label in LINE_FIELDS if _blank(line.get(name))]
    return _item(
        MANDATORY_FIELDS, [MANDATORY_MESSAGE.format(labels=", ".join(labels))] if labels else []
    )


def source_reference(contract_row: Mapping[str, Any]) -> ChecklistItem:
    """``SOURCE_REFERENCE``: a CRM, CPQ or e-signature reference is recorded."""
    return _item(SOURCE_REFERENCE, [SOURCE_MESSAGE] if _blank(contract_row["document_ref"]) else [])


def _products(session: Session, product_ids: set[UUID]) -> dict[UUID, Mapping[str, Any]]:
    if not product_ids:
        return {}
    statement = select(
        product.c.id, product.c.code, product.c.is_active, product.c.default_pob_template_id
    ).where(product.c.id.in_(sorted(product_ids)))
    return {_uuid(row["id"]): dict(row) for row in session.execute(statement).mappings()}


def _template_distinctness(session: Session, template_ids: set[UUID]) -> dict[UUID, str]:
    """The distinctness of each template's PUBLISHED version (DB-04: one at a time)."""
    if not template_ids:
        return {}
    statement = (
        select(pob_template_version.c.pob_template_id, pob_template_version.c.distinctness)
        .where(
            pob_template_version.c.pob_template_id.in_(sorted(template_ids)),
            pob_template_version.c.status == ConfigStatus.PUBLISHED.value,
        )
        .order_by(pob_template_version.c.pob_template_id, pob_template_version.c.version_no)
    )
    return {_uuid(template_id): _text(value) for template_id, value in session.execute(statement)}


def _template_of(products: Mapping[UUID, Mapping[str, Any]], product_id: Any) -> UUID | None:
    found = products.get(_uuid(product_id))
    if found is None or found["default_pob_template_id"] is None:
        return None
    return _uuid(found["default_pob_template_id"])


def _code_of(products: Mapping[UUID, Mapping[str, Any]], product_id: Any) -> str:
    found = products.get(_uuid(product_id))
    return "-" if found is None else str(found["code"])


def _refused_findings(session: Session, group_id: UUID) -> list[Mapping[str, Any]]:
    """The open SSP and product items of the group while its latest computation was refused."""
    latest = session.execute(
        select(contract_computation.c.status)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None or _text(latest) == ComputationStatus.SUCCEEDED.value:
        return []
    statement = (
        select(
            exception_item.c.code, exception_item.c.obligation_id, exception_item.c.source_payload
        )
        .where(
            exception_item.c.combination_group_id == group_id,
            exception_item.c.code.in_(SSP_CODES),
            exception_item.c.status.in_(OPEN_STATUSES),
        )
        .order_by(exception_item.c.exception_no)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _open_unmapped_naming(session: Session, contract_id: UUID) -> list[Mapping[str, Any]]:
    """04 table 15.4-I rev 1.81 (DIN-12 partial booking): the open ``PRODUCT_UNMAPPED`` items that
    name the contract — the adapter booked the DRAFT from its mapped lines and left the unmapped
    ones as candidate rows — fail the item whether or not the group's computation was refused."""
    statement = (
        select(
            exception_item.c.code, exception_item.c.obligation_id, exception_item.c.source_payload
        )
        .where(
            exception_item.c.contract_id == contract_id,
            exception_item.c.code == SSP_CODES[1],
            exception_item.c.status.in_(OPEN_STATUSES),
        )
        .order_by(exception_item.c.exception_no)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def product_template_ssp(
    session: Session,
    contract_row: Mapping[str, Any],
    obligations: Sequence[Mapping[str, Any]],
    products: Mapping[UUID, Mapping[str, Any]],
    distinctness: Mapping[UUID, str],
) -> ChecklistItem:
    """``PRODUCT_TEMPLATE_SSP`` (REQ-REF-014; 04 table 15.4-I rev 1.81)."""
    lines: list[str] = []
    for row in obligations:
        found = products.get(_uuid(row["product_id"]))
        template_id = _template_of(products, row["product_id"])
        if found is None or not found["is_active"] or template_id not in distinctness:
            key = str(row["obligation_key"])
            lines.append(
                TEMPLATE_MESSAGE.format(key=key, product=_code_of(products, row["product_id"]))
            )
    by_id = {_uuid(row["id"]): row for row in obligations}
    findings = _refused_findings(session, _uuid(contract_row["combination_group_id"]))
    booked = {
        str(line.get("obligation_key")): line
        for line in (_latest_booking(session, _uuid(contract_row["id"])).get("lines") or ())
        if findings
    }
    for finding in findings:
        payload = finding["source_payload"] or {}
        detail = payload.get("detail") or {}
        product_code = str(detail.get("product_code") or "")
        named = (
            None if finding["obligation_id"] is None else by_id.get(_uuid(finding["obligation_id"]))
        )
        if named is None:
            named = next(
                (
                    row
                    for row in obligations
                    if _code_of(products, row["product_id"]) == product_code
                ),
                None,
            )
        if named is None:
            continue
        code = product_code or _code_of(products, named["product_id"])
        line = TEMPLATE_MESSAGE.format(key=named["obligation_key"], product=code)
        if line not in lines:
            lines.append(line)
        if finding["code"] == SSP_CODES[0]:
            # The IMP-09 key: the finding's members, else the booked line's.
            line_members = booked.get(str(named["obligation_key"])) or {}
            lines.append(
                SSP_MESSAGE.format(
                    product=code,
                    stratification=detail.get("stratification")
                    or line_members.get("stratification")
                    or "-",
                    version=detail.get("ssp_version_label")
                    or line_members.get("ssp_version_label")
                    or "-",
                )
            )
    # 04 table 15.4-I rev 1.81 (owner note F-CTR 1: AFTER the refused-findings lines, so a refused
    # computation reports as before and these lines only add): an open PRODUCT_UNMAPPED item naming
    # the contract — a line the adapter left unbooked — fails the item on its own, each named line
    # in the TEMPLATE_MESSAGE shape with its source product code (owner note 3: one shape for the
    # checklist UI).
    for named_item in _open_unmapped_naming(session, _uuid(contract_row["id"])):
        detail = (named_item["source_payload"] or {}).get("detail") or {}
        code = str(detail.get("product_code") or SSP_CODES[1])
        for key in detail.get("line_external_ids") or ["-"]:
            line = TEMPLATE_MESSAGE.format(key=key, product=code)
            if line not in lines:
                lines.append(line)
    return _item(PRODUCT_TEMPLATE_SSP, lines)


def distinct_review(
    session: Session,
    obligations: Sequence[Mapping[str, Any]],
    products: Mapping[UUID, Mapping[str, Any]],
    distinctness: Mapping[UUID, str],
) -> ChecklistItem:
    """``DISTINCT_REVIEW`` (REQ-POB-001; [J] L4-1-Q-19)."""
    if len(obligations) < 2:
        return _item(DISTINCT_REVIEW, [])
    ids = [_uuid(row["id"]) for row in obligations]
    reviewed = {
        _uuid(value)
        for value in session.execute(
            select(judgement_record.c.subject_id).where(
                judgement_record.c.topic == JudgementTopic.POB_DISTINCT_OVERRIDE.value,
                judgement_record.c.subject_type == "obligation",
                judgement_record.c.subject_id.in_(ids),
                judgement_record.c.status == JudgementStatus.REVIEWED.value,
            )
        ).scalars()
    }
    lines: list[str] = []
    for row in obligations:
        template_id = _template_of(products, row["product_id"])
        value = None if template_id is None else distinctness.get(template_id)
        if value in REVIEWABLE and _uuid(row["id"]) not in reviewed:
            lines.append(
                DISTINCT_MESSAGE.format(
                    key=row["obligation_key"], product=_code_of(products, row["product_id"])
                )
            )
    return _item(DISTINCT_REVIEW, lines)


def _entities_read(session: Session, contract_ids: Sequence[str]) -> dict[str, str]:
    """The contracting entity of each of ``contract_ids`` the session reads: a contract outside
    its entity scope is not visible to it, exactly as a missing one is (``repo``; REQ-PLT-012)."""
    wanted: set[UUID] = set()
    for value in contract_ids:
        try:
            wanted.add(UUID(value))
        except ValueError:  # a payload this module did not write: named to nobody
            continue
    if not wanted:
        return {}
    statement = select(contract.c.id, contract.c.contracting_entity_id).where(
        contract.c.id.in_(sorted(wanted, key=str))
    )
    return {str(found): str(entity_id) for found, entity_id in session.execute(statement)}


def combination_suggestions(
    session: Session, contract_row: Mapping[str, Any], *, stored: bool = False
) -> ChecklistItem:
    """``COMBINATION_SUGGESTIONS`` (REQ-CON-010; PRD BR-CON-03): one line for each open suggestion
    that names the contract (PRD IMP-103 rev 1.181; 04 table 15.4-I; item
    ACT-CHECKLIST-SUGGESTION-SCOPE-1).

    A pair of two contracting entities is stored without an entity, so its item is in the session
    of every reader of either contract; until this item the reader of one was told the other's
    external id. The line stays — that a suggestion is open is a fact its reader needs — and who
    can end one is a member who reads every contract it names
    (``combination.suggestions_read_by``).

    - Read by a session (the checklist's read; the 409 of ``submit-activation`` and of the
      activation's approval): the line names the other contract by its external id when the
      session reads that contract, and says ``CONTRACT_OUTSIDE`` when it does not.
    - ``stored`` (a line kept for others to read: the message of the exception item a Contract
      Setup commit raises): a stored line has readers, not a session. It names the other contract
      only when that contract is of the contract's own contracting entity, whose readers read
      both, and says ``CONTRACT_OF_ANOTHER_ENTITY`` otherwise — true for every reader; a member
      who reads both contracts finds the id on the checklist itself.
    """
    contract_id = str(contract_row["id"])
    statement = (
        select(exception_item.c.source_payload)
        .where(
            exception_item.c.code == SUGGESTED,
            exception_item.c.status.in_(OPEN_STATUSES),
            exception_item.c.source_payload["contract_ids"].contains([contract_id]),
        )
        .order_by(exception_item.c.exception_no)
    )
    others: list[tuple[str, str]] = []
    for payload in session.execute(statement).scalars():
        ids = [str(value) for value in (payload or {}).get("contract_ids") or ()]
        externals = [str(value) for value in (payload or {}).get("contract_external_ids") or ()]
        others += [
            (value, external)
            for value, external in zip(ids, externals, strict=False)
            if value != contract_id
        ]
    read = _entities_read(session, [value for value, _ in others])
    if stored:
        own = str(contract_row["contracting_entity_id"])
        named = {value for value, entity_id in read.items() if entity_id == own}
        substitute = CONTRACT_OF_ANOTHER_ENTITY
    else:
        named = set(read)
        substitute = CONTRACT_OUTSIDE
    lines = [
        SUGGESTION_MESSAGE.format(external_id=external if value in named else substitute)
        for value, external in others
    ]
    return _item(COMBINATION_SUGGESTIONS, lines)


def judgement_records(session: Session, contract_row: Mapping[str, Any]) -> ChecklistItem:
    """``JUDGEMENT_RECORDS`` (REQ-POL-008): no judgement record of the contract is DRAFT,
    SUBMITTED or REJECTED. A record that waits — a draft, or one in review — is named by its
    topic, one line a topic (PRD IMP-104). Item JDG-REJECTED-EXIT-1: a REJECTED record is named
    by its number, one line a record, with the discard as its road (04 table 15.4-I
    ``JUDGEMENT_RECORD_REJECTED``): it is a reviewer's No that nobody answered, and it stays
    counted until it is discarded or revised."""
    rejected = JudgementStatus.REJECTED.value
    rows = session.execute(
        select(
            judgement_record.c.judgement_no,
            judgement_record.c.topic,
            judgement_record.c.status,
        )
        .where(
            judgement_record.c.contract_id == contract_row["id"],
            judgement_record.c.status.in_(UNREVIEWED),
        )
        .order_by(judgement_record.c.judgement_no)
    ).all()
    waiting = list(dict.fromkeys(_text(row.topic) for row in rows if _text(row.status) != rejected))
    return _item(
        JUDGEMENT_RECORDS,
        [
            *(JUDGEMENT_MESSAGE.format(topic=finding_title(topic)) for topic in waiting),
            *(
                JUDGEMENT_REJECTED_MESSAGE.format(
                    judgement_no=row.judgement_no, topic=finding_title(_text(row.topic))
                )
                for row in rows
                if _text(row.status) == rejected
            ),
        ],
    )


def evaluate(
    session: Session, contract_row: Mapping[str, Any], *, now: datetime, stored: bool = False
) -> Checklist:
    """04 table 15.4-I of a visible contract, evaluated without storing
    (API-S-ActivationChecklist). ``stored`` is the caller's word that it keeps the lines for
    others to read (``combination_suggestions``)."""
    contract_id = _uuid(contract_row["id"])
    obligations = repo.obligations(session, contract_id)
    products = _products(session, {_uuid(row["product_id"]) for row in obligations})
    templates = {
        _uuid(row["default_pob_template_id"])
        for row in products.values()
        if row["default_pob_template_id"] is not None
    }
    distinctness = _template_distinctness(session, templates)
    items = (
        mandatory_fields(session, contract_row),
        source_reference(contract_row),
        product_template_ssp(session, contract_row, obligations, products, distinctness),
        distinct_review(session, obligations, products, distinctness),
        combination_suggestions(session, contract_row, stored=stored),
        judgement_records(session, contract_row),
        step1_record(session, contract_row),
    )
    return Checklist(items=items, evaluated_at=now)


def checklist_problem(checklist: Checklist) -> Problem:
    """409 ``activation-checklist-failed``: each failed code in ``errors[].rule_id`` (ERR-31)."""
    failed = checklist.failed
    noun = "item has" if len(failed) == 1 else "items have"
    detail = FAILED_DETAIL.format(
        count=len(failed), noun=noun, codes=", ".join(item.code for item in failed)
    )
    return Problem(
        "activation-checklist-failed",
        detail,
        errors=[
            ProblemError(rule_id=item.code, message=item.detail or item.code) for item in failed
        ],
    )


def checklist_out(
    ctx: RequestContext, contract_id: UUID, *, now: datetime
) -> ActivationChecklistOut:
    """``GET /contracts/{id}/activation-checklist``."""

    def load(session: Session) -> ActivationChecklistOut:
        checklist = evaluate(session, repo.get_contract(session, contract_id), now=now)
        return ActivationChecklistOut(
            items=[
                ActivationChecklistItemOut(code=item.code, passed=item.passed, detail=item.detail)
                for item in checklist.items
            ],
            evaluated_at=checklist.evaluated_at,
        )

    return queries.read(ctx, load)


# --- routing flags -------------------------------------------------------------------------------


# E-15 kinds that originate integration content; every other author of a stream event is a person.
SYSTEM_ORIGINATED_KINDS: Final = (PrincipalKind.API_CLIENT.value, PrincipalKind.SYSTEM.value)


def written_by_a_person(session: Session, contract_id: UUID) -> bool:
    """Supervisor ruling R-38 (i): "system-originated" is a fact of the CONTENT, not only of who
    submits the activation. True when anything the contract's stream holds up to now — the
    booking, a replacement of the draft, a memo or line change, a hold, any recorded event — is a
    person's content. The stream keeps every author (T-CON-05 ``created_by_kind``; a replaced
    booking stays in it), while ``contract.source_system`` names only the first booking's source.

    A person's content reaches the stream in five ways, and each counts:

    - an event a signed-in person (or an operator) wrote, or one marked ``is_manual`` (PRD
      ACT-10) — a manual event keeps the mark when the SYSTEM principal appends it on approval;
    - an event the SYSTEM principal wrote while committing an import a person uploaded;
    - an event an approval put in force (``approval_request_id``) unless an API client prepared
      that request: an SSP override, an estimate version, an attribute change. The SYSTEM
      principal appends them on behalf of the people who prepared and approved them (R-41 (7): a
      system job acting for a user is not an integration), and a request the caller cannot read
      counts as a person's;
    - a ``COMBINATION_CHANGED`` event: a combination is always a person's proposal;
    - a policy override of the contract that was approved — it changes what the contract computes
      and writes no event.
    """
    own = contract_event.c.contract_id == contract_id
    by_person = session.execute(
        select(contract_event.c.id)
        .where(
            own,
            or_(
                contract_event.c.created_by_kind.not_in(SYSTEM_ORIGINATED_KINDS),
                contract_event.c.is_manual.is_(True),
                contract_event.c.event_type == ContractEventType.COMBINATION_CHANGED.value,
            ),
        )
        .limit(1)
    ).first()
    if by_person is not None:
        return True
    uploaded = session.execute(
        select(contract_event.c.id)
        .select_from(
            contract_event.join(
                import_upload,
                and_(
                    import_upload.c.tenant_id == contract_event.c.tenant_id,
                    import_upload.c.id == contract_event.c.import_upload_id,
                ),
            )
        )
        .where(own, import_upload.c.created_by_kind != PrincipalKind.API_CLIENT.value)
        .limit(1)
    ).first()
    if uploaded is not None:
        return True
    approved = session.execute(
        select(contract_event.c.id)
        .select_from(
            contract_event.outerjoin(
                approval_request,
                and_(
                    approval_request.c.tenant_id == contract_event.c.tenant_id,
                    approval_request.c.id == contract_event.c.approval_request_id,
                ),
            )
        )
        .where(
            own,
            contract_event.c.approval_request_id.is_not(None),
            or_(
                approval_request.c.id.is_(None),
                approval_request.c.preparer_kind != PrincipalKind.API_CLIENT.value,
            ),
        )
        .limit(1)
    ).first()
    if approved is not None:
        return True
    overridden = session.execute(
        select(policy_override.c.id)
        .where(
            policy_override.c.contract_id == contract_id,
            policy_override.c.status.in_(
                (ConfigStatus.APPROVED.value, ConfigStatus.SUPERSEDED.value)
            ),
        )
        .limit(1)
    ).first()
    return overridden is not None


@dataclass(frozen=True, slots=True)
class Measured:
    """What a computation of the contract's combination group states for the routing of its
    activation (item ACT-FLAGS-1; supervisor ruling R-66 (4)): the transaction price — the largest
    of the books that hold a contract version, in the transaction currency; the GROUP's price,
    since a contract version is the group's (T-CON-08) —, whether the price build-up of any book
    holds a financing adjustment, and the E-18 kinds of the obligations of THIS contract: the
    kind of the template the engine gave each of its lines — by a ``POB_ASSIGNMENT`` rule, under
    the parity preset by S03-R-18, or the product's default. ``submit_activation`` reads it from
    its dry run; a reader with a Session alone reads the group's latest stored versions
    (``stored_measure``)."""

    transaction_price: Decimal | None
    financing: bool
    kinds: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Judged:
    """The amount an activation is judged by, and what the routing thresholds read of it: the
    amount in the transaction currency, its T-PLT-17 ``amount_functional`` (None: no rate to the
    functional currency) and the same amount in the threshold currency (None: no rate to it)."""

    amount: Decimal
    currency: str
    functional: tuple[Decimal, str] | None
    in_threshold_currency: Decimal | None

    @property
    def rate_missing(self) -> bool:
        return self.functional is None or self.in_threshold_currency is None


@dataclass(frozen=True, slots=True)
class RoutingFacts:
    """The routing facts of a ``CONTRACT_ACTIVATION`` request: T-PLT-17 ``flags`` and
    ``amount_functional`` with its currency."""

    flags: frozenset[str]
    amount: tuple[Decimal, str] | None


def measured_by(output: OutputBundle, currency: str, external_id: str) -> Measured:
    """``Measured`` of a computation's output — the activation's dry run — for the member contract
    ``external_id``: the price and the financing are the group's, the kinds are those of the
    contract's own obligations (their subject keys begin with the contract's)."""
    minor = ISO_4217[currency].minor_unit
    own = contract_subject_key(external_id) + "/"
    price: Decimal | None = None
    financing = False
    kinds: set[str] = set()
    for book in output.books:
        version = book.contract_version
        if version is None:  # the LEGACY book carries posting intents and no contract version
            continue
        columns = version.columns
        value = abs(_amount_of(columns.get("transaction_price"), minor))
        price = value if price is None else max(price, value)
        financing = financing or _amount_of(columns.get("financing_adjustment_amount"), minor) != 0
        for item in book.obligation_versions:
            kind = item.columns.get("obligation_kind")
            if kind is not None and item.subject_key.startswith(own):
                kinds.add(_text(kind))
    return Measured(transaction_price=price, financing=financing, kinds=frozenset(kinds))


def _amount_of(value: object, minor: int) -> Decimal:
    """A T-CON-08 money column of an engine output as a decimal amount (integer minor units, an
    exact fraction, or the decimal a stored row holds)."""
    if value is None:
        return Decimal(0)
    if isinstance(value, bool):
        raise TypeError("money is not a boolean")
    if isinstance(value, int):
        return minor_to_decimal(value, minor)
    if isinstance(value, Fraction):
        return Decimal(format_exact(value))
    return Decimal(str(value))


def stored_measure(session: Session, contract_id: UUID) -> Measured | None:
    """``Measured`` of the latest stored version of the contract's group in each book — for a
    draft, its provisional version (``commands.provisional_compute``) — with the kinds of the
    contract's own obligation versions in them; None when no version is stored. The reader of a
    caller that holds no dry run: the import of a legacy contract setup, which states the
    activation its commit performs (``contract_setup.underlying``)."""
    group_id = session.execute(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if group_id is None:
        return None
    rows = session.execute(
        select(
            contract_version.c.id,
            contract_version.c.transaction_price,
            contract_version.c.financing_adjustment_amount,
        )
        .where(contract_version.c.combination_group_id == group_id)
        .distinct(contract_version.c.book_code)
        .order_by(contract_version.c.book_code, contract_version.c.version_no.desc())
    ).all()
    if not rows:
        return None
    kinds = session.execute(
        select(obligation_version.c.obligation_kind)
        .where(
            obligation_version.c.contract_id == contract_id,
            obligation_version.c.contract_version_id.in_([row.id for row in rows]),
        )
        .distinct()
    ).scalars()
    return Measured(
        transaction_price=max(abs(Decimal(row.transaction_price)) for row in rows),
        financing=any(Decimal(row.financing_adjustment_amount) != 0 for row in rows),
        kinds=frozenset(_text(kind) for kind in kinds),
    )


def _converted(amount: Decimal, rate: Decimal, currency: str) -> Decimal:
    """``amount × rate`` rounded half up at ``currency``'s minor unit (S12-R-02's rounding; the
    rounding of the other routing thresholds, ``estimates.routing_facts``)."""
    unit = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    return (amount * rate).quantize(unit, rounding=ROUND_HALF_UP)


# The record cutoff of a caller that holds no clock: every rate set version published so far.
EVER_PUBLISHED: Final = datetime(9999, 1, 1, tzinfo=UTC)


def _spot_rate(rates: Sequence[FxRateInput], *, base: str, quote: str, on: date) -> Decimal | None:
    """The engine's ``spot`` rate from ``base`` to ``quote`` on ``on`` among the pinned rows — the
    latest on or before the day, an explicit pair, no triangulation (ENGINE_SPEC_B S12-R-01;
    ``Rates.spot``; the rate rule of the other routing thresholds, 04 §16.14 ``fx_basis``): 1 for
    equal currencies, None when no row qualifies. No rate-selection rule is added."""
    if base == quote:
        return Decimal(1)
    try:
        return Decimal(Rates(rates, base, quote).spot(on).text)
    except RateMissing:
        return None


def judged(
    session: Session,
    contract_id: UUID,
    transaction_price: Decimal | None,
    *,
    known_at: datetime | None = None,
) -> Judged:
    """THE reading of the amount an activation is judged by (item ACT-FLAGS-1; PRD §2.5 rev 1.194;
    04 §16.10 rev 1.287) — every reader of an activation threshold and of the request's amount
    comes through here.

    The amount is the LARGER of the booked consideration (``contract_activation_total``: the
    absolute sum of the line prices of the latest booking no void names) and ``transaction_price``,
    the price a computation of the group states (supervisor ruling R-66 (4): an estimate version
    approved on a DRAFT contract recognises nothing, so its weight reaches the approval of the
    activation) — both in the transaction currency, compared before any conversion.

    It is converted at the ``spot`` rate in force for the contract's inception date, as the engine
    reads a spot rate for a day (``_spot_rate``) from the rate rows a bundle of the three
    currencies carries at ``known_at`` (``bundles.fx_rate_inputs``; a caller that holds no clock
    reads every version published so far): to the contracting entity's functional currency for
    ``amount_functional``, and to ``THRESHOLD_CURRENCY`` for the two thresholds. A rate that is
    not published leaves its amount unstated. An amount of zero needs no rate."""
    booked, currency, functional_currency = contract_activation_total(session, contract_id)
    amount = booked if transaction_price is None else max(booked, abs(transaction_price))
    if amount == 0:
        to_functional: Decimal | None = Decimal(1)
        to_threshold: Decimal | None = Decimal(1)
    else:
        on = session.execute(
            select(contract.c.inception_date).where(contract.c.id == contract_id)
        ).scalar_one()
        rates = bundles.fx_rate_inputs(
            session,
            {currency, functional_currency, THRESHOLD_CURRENCY},
            EVER_PUBLISHED if known_at is None else known_at,
        )
        to_functional = _spot_rate(rates, base=currency, quote=functional_currency, on=on)
        to_threshold = _spot_rate(rates, base=currency, quote=THRESHOLD_CURRENCY, on=on)
    return Judged(
        amount=amount,
        currency=currency,
        functional=(
            None
            if to_functional is None
            else (_converted(amount, to_functional, functional_currency), functional_currency)
        ),
        in_threshold_currency=(
            None if to_threshold is None else _converted(amount, to_threshold, THRESHOLD_CURRENCY)
        ),
    )


def threshold_flags(amounts: Judged) -> frozenset[str]:
    """PRD §2.5: ``ABOVE_THRESHOLD`` from USD 100,000.00 and ``ABOVE_CONTROLLER_THRESHOLD`` from
    USD 1,000,000.00 — a second-step flag of the subject. A flag is a fact an approver reads, so
    an amount known in the threshold currency is judged by its value; an amount that cannot be
    judged there — no rate to the threshold currency — is treated as above, never as below, and
    carries both (the supervisor's rulings of 2026-10-02).

    ``RATE_NOT_PUBLISHED`` says that a rate is missing — that one, or the rate to the functional
    currency, without which the request states no ``amount_functional``. It is a second-step
    flag of the subject by itself (``subjects.RATE_NOT_PUBLISHED``): a request without a
    functional amount is one no tenant's amount rule can read."""
    flags: set[str] = {RATE_NOT_PUBLISHED} if amounts.rate_missing else set()
    if amounts.in_threshold_currency is None:
        return frozenset(flags | {ABOVE_THRESHOLD, ABOVE_CONTROLLER_THRESHOLD})
    if amounts.in_threshold_currency >= ACTIVATION_THRESHOLD:
        flags.add(ABOVE_THRESHOLD)
    if amounts.in_threshold_currency >= CONTROLLER_THRESHOLD:
        flags.add(ABOVE_CONTROLLER_THRESHOLD)
    return frozenset(flags)


def _booking_flags(booking: Mapping[str, Any]) -> set[str]:
    """What the latest booking states beside the header's terms: consideration payable to the
    customer or noncash consideration; a line outside the scope of ASC 606 or with an amount
    outside it; a line that states an SSP override's justification or its own accounts — whoever
    booked it. The activation's approval is the only decision on those line members: the
    computation prices the line and posts to the accounts as booked."""
    flags: set[str] = set()
    if booking.get("consideration_payable") or booking.get("noncash_consideration"):
        flags.add(NON_STANDARD_TERMS)
    for line in booking.get("lines") or ():
        scope = line.get("scope_flag") or ScopeFlag.IN_SCOPE_606.value
        if scope != ScopeFlag.IN_SCOPE_606.value or line.get("out_of_scope_amount") is not None:
            flags.add(NON_STANDARD_TERMS)
        if not _blank(line.get("ssp_override_justification")) or line.get("account_overrides"):
            flags.add(NON_STANDARD_TERMS)
    return flags


def _line_products(session: Session, booking: Mapping[str, Any]) -> dict[UUID, UUID | None]:
    """The products of the latest booking's lines, each with its default template."""
    codes = sorted({str(line.get("product_code")) for line in booking.get("lines") or ()})
    if not codes:
        return {}
    statement = select(product.c.id, product.c.default_pob_template_id).where(
        product.c.code.in_(codes)
    )
    return {
        _uuid(product_id): None if template_id is None else _uuid(template_id)
        for product_id, template_id in session.execute(statement)
    }


def _template_kinds(session: Session, template_ids: set[UUID]) -> set[str]:
    """The E-18 kinds of the templates' PUBLISHED versions (DB-04: one at a time) — an obligation
    holds no kind before a computation, so the kind is read as the checklist reads distinctness."""
    if not template_ids:
        return set()
    statement = select(pob_template_version.c.obligation_kind).where(
        pob_template_version.c.pob_template_id.in_(sorted(template_ids)),
        pob_template_version.c.status == ConfigStatus.PUBLISHED.value,
    )
    return {_text(kind) for kind in session.execute(statement).scalars()}


def _estimate_kinds(session: Session, contract_id: UUID) -> set[str]:
    """The E-09 kinds of the contract's estimated elements (T-CON-12 — an element of the
    contract or of one of its obligations names the contract, ``ck_estimate__scope``), whatever
    the status of their versions: an element is a statement that the amount is estimated, also
    before a version of it is approved."""
    statement = select(estimate.c.estimate_kind).where(estimate.c.contract_id == contract_id)
    return {_text(kind) for kind in session.execute(statement).scalars()}


def _unknown_products(session: Session, contract_id: UUID, product_ids: set[UUID]) -> set[UUID]:
    """The products of which no OTHER contract of the workspace that was activated holds a line.
    One probe a product, ended by its first hit (``ix_obligation__product``)."""
    if not product_ids:
        return set()
    held = exists().where(
        obligation.c.tenant_id == product.c.tenant_id,
        obligation.c.product_id == product.c.id,
        obligation.c.contract_id != contract_id,
        exists().where(
            contract.c.tenant_id == obligation.c.tenant_id,
            contract.c.id == obligation.c.contract_id,
            contract.c.status.in_(ACTIVATED),
        ),
    )
    known = {
        _uuid(value)
        for value in session.execute(
            select(product.c.id).where(product.c.id.in_(sorted(product_ids)), held)
        ).scalars()
    }
    return product_ids - known


def routing_facts(
    session: Session,
    contract_id: UUID,
    measured: Measured | None,
    *,
    known_at: datetime | None = None,
) -> RoutingFacts:
    """The routing facts of a ``CONTRACT_ACTIVATION`` request (PRD §2.5; 04 T-PLT-17, §16.10 rev
    1.287; [J] L4-1-Q-20; item ACT-FLAGS-1, the supervisor's rulings of 2026-10-02). Any flag
    withholds the request from the auto-approval rules (``submit_activation``):

    - ``ABOVE_THRESHOLD``, ``ABOVE_CONTROLLER_THRESHOLD``, ``RATE_NOT_PUBLISHED``: ``judged`` and
      ``threshold_flags``, on the larger of the booked consideration and ``measured``'s price;
    - ``MANUAL_ENTRY``: a contract a person created or changed. It reads the stream's authorship,
      not ``contract.source_system`` alone (R-38 (i); 04 §16.10 rev 1.104): a draft an
      integration booked and a person then replaced, edited or recorded an event on is a manual
      entry (``written_by_a_person``);
    - ``TERMS_NOT_STATED``: the booking states neither whether the contract holds an acceptance
      clause nor whether a side letter exists — one of T-CON-01 ``acceptance_clause`` and
      ``side_letter`` is NULL. The record cannot tell, so nothing is presumed;
    - ``SIDE_LETTER``: ``side_letter`` is true;
    - ``NON_STANDARD_TERMS``: termination for convenience; ``acceptance_clause`` true; what the
      booking states (``_booking_flags``); a financing adjustment in ``measured`` — a significant
      financing component;
    - ``MATERIAL_RIGHT``: a line whose template is of the kind ``MATERIAL_RIGHT`` — the template
      ``measured`` states for it, which the engine chose (a ``POB_ASSIGNMENT`` rule, S03-R-18 of
      the parity preset, or the product's default), and the product's default template beside
      it, read also where no computation is at hand —, or an ``EXERCISE_LIKELIHOOD`` element, the
      built record of an option's terms (T-CON-14 is not built);
    - ``VARIABLE_CONSIDERATION``: an estimated element of one of ``CONSIDERATION_ESTIMATES``, or
      a line whose template, read in the same two ways, is of the kind ``VC_LINE``;
    - ``NEW_SKU``: a line's product that no other activated contract of the workspace holds.

    The reads follow the caller's entity scope: ``submit_activation`` widens it to the tenant's
    (R-64 (1): what a request states does not depend on who submits), as the approvals kernel
    does for the functions registered below."""
    row = session.execute(
        select(
            contract.c.source_system,
            contract.c.termination_party,
            contract.c.acceptance_clause,
            contract.c.side_letter,
        ).where(contract.c.id == contract_id)
    ).one()
    amounts = judged(
        session,
        contract_id,
        None if measured is None else measured.transaction_price,
        known_at=known_at,
    )
    flags: set[str] = set(threshold_flags(amounts))
    if _text(row.source_system) == SourceSystem.MANUAL_UI.value or written_by_a_person(
        session, contract_id
    ):
        flags.add(MANUAL_ENTRY)
    if row.acceptance_clause is None or row.side_letter is None:
        flags.add(TERMS_NOT_STATED)
    if row.side_letter:
        flags.add(SIDE_LETTER)
    if row.termination_party in CONVENIENCE_PARTIES or row.acceptance_clause:
        flags.add(NON_STANDARD_TERMS)
    if measured is not None and measured.financing:
        flags.add(NON_STANDARD_TERMS)
    booking = _latest_booking(session, contract_id)
    flags |= _booking_flags(booking)
    products = _line_products(session, booking)
    template_kinds = _template_kinds(
        session, {template_id for template_id in products.values() if template_id is not None}
    )
    if measured is not None:
        # The template a line computes under is the engine's choice, and a rule may give a line
        # another one than its product's default: the kinds of the computation count as well.
        template_kinds |= measured.kinds
    estimate_kinds = _estimate_kinds(session, contract_id)
    if (
        ObligationKind.MATERIAL_RIGHT.value in template_kinds
        or EstimateKind.EXERCISE_LIKELIHOOD.value in estimate_kinds
    ):
        flags.add(MATERIAL_RIGHT)
    if ObligationKind.VC_LINE.value in template_kinds or estimate_kinds.intersection(
        CONSIDERATION_ESTIMATES
    ):
        flags.add(VARIABLE_CONSIDERATION)
    if _unknown_products(session, contract_id, set(products)):
        flags.add(NEW_SKU)
    return RoutingFacts(flags=frozenset(flags), amount=amounts.functional)


def activation_flags(session: Session, contract_id: UUID) -> frozenset[str]:
    """The subject's registered ``flags``: ``routing_facts`` on the group's stored versions, for a
    caller that holds no dry run."""
    return routing_facts(session, contract_id, stored_measure(session, contract_id)).flags


def activation_amount(session: Session, contract_id: UUID) -> tuple[Decimal, str] | None:
    """The subject's registered ``amount``: T-PLT-17 ``amount_functional`` of an activation, for
    a caller that holds no dry run."""
    measured = stored_measure(session, contract_id)
    price = None if measured is None else measured.transaction_price
    return judged(session, contract_id, price).functional


def booked_amount(session: Session, contract_id: UUID) -> tuple[Decimal, str] | None:
    """T-PLT-17 ``amount_functional`` of a ``CONTRACT_VOID`` request (registered by ``void``):
    the booked consideration in the entity's functional currency, at the same rate rule; none
    while that rate is not published."""
    return judged(session, contract_id, None).functional


# --- submit-activation and the approved activation -----------------------------------------------


def engine_problem(error: EngineError) -> Problem:
    """DG-CMD-04: an ``EngineError`` of a decision command is 422 ``validation-failed`` with
    ``rule_id`` = the engine code, and the command's writes roll back (DG-CMD-09)."""
    return Problem(
        "validation-failed",
        error.message,
        code=error.code,
        errors=[ProblemError(field=error.subject_key, rule_id=error.code, message=error.message)],
    )


def _refuse(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=message)],
    )


def _activated(
    contract_row: Mapping[str, Any],
    checklist: Checklist,
    approval_request_id: UUID | None = None,
    *,
    criteria: Sequence[CriteriaMet] = (),
) -> EventIn:
    """``CONTRACT_ACTIVATED`` of the approved activation: at the inception date, or — behind the
    ``CONTRACT_CRITERIA_MET`` events of a criteria-met activation — at the latest criteria-met
    date. Dated at inception it would sort BEFORE the not-a-contract gate in ENG-06 order and
    activate the contract from inception as if Step 1 had never failed (ENGINE_SPEC Table 2.2-A);
    behind the criteria-met events it finds every book past DRAFT and carries the approval and the
    checklist only."""
    effective = (
        max(item.effective_date for item in criteria)
        if criteria
        else contract_row["inception_date"]
    )
    return EventIn(
        event_type=ContractEventType.CONTRACT_ACTIVATED,
        effective_date=effective,
        payload=ContractActivatedV1(checklist=checklist.payload()),
        approval_request_id=approval_request_id,
    )


def _criteria_events(
    criteria: Sequence[CriteriaMet], approval_request_id: UUID | None = None
) -> list[EventIn]:
    """``CONTRACT_CRITERIA_MET`` per moving book, effective the date the preparer recorded
    (ruling R-20 (c); POL-013 decides the transition in the engine, S02-R-04)."""
    return [
        EventIn(
            event_type=ContractEventType.CONTRACT_CRITERIA_MET,
            effective_date=item.effective_date,
            payload=ContractCriteriaMetV1(
                book=BookCode(item.book), judgement_record_id=item.judgement_record_id
            ),
            approval_request_id=approval_request_id,
        )
        for item in criteria
    ]


def _pending_request(session: Session, contract_id: UUID) -> UUID | None:
    found = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.subject_type == ApprovalSubjectType.CONTRACT_ACTIVATION.value,
            approval_request.c.subject_id == contract_id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
    ).scalar_one_or_none()
    return None if found is None else _uuid(found)


def _preview(
    status: str,
    summary: Mapping[str, Any],
    criteria: Sequence[CriteriaMet] = (),
    totals: Mapping[str, Any] | None = None,
) -> approvals.ImpactPreview:
    """The dry run of the activation as the request's impact preview (REQ-PLT-015). A criteria-met
    activation also shows what the approver decides beyond an ordinary activation (04 §16.10 rev
    1.105): the books that move, each with its criteria-met date, its judgement record and its
    POL-013 catch-up (``totals``), and the primary book's catch-up per obligation (ENGINE_SPEC
    S02-R-04; ``events.step1_catch_up``)."""
    revenue = summary["revenue_by_period"]
    after: dict[str, Any] = {
        "status": ContractStatus.ACTIVE.value,
        "transaction_price": summary["transaction_price_after"],
        "rpo": summary["rpo_after"],
        "revenue_by_period": [
            {"period_key": row["period_key"], "amount": row["after"]} for row in revenue
        ],
        "balances": summary["balances_after"],
        "journal_lines": summary["journal_lines"],
    }
    if criteria:
        after["criteria_met"] = [
            {**item.members(), "catch_up_total": (totals or {}).get(item.book)} for item in criteria
        ]
        after["catch_up_total"] = summary["catch_up_total"]
        after["catch_up_by_obligation"] = summary["catch_up_by_obligation"]
    return approvals.ImpactPreview(
        before={
            "status": status,
            "transaction_price": summary["transaction_price_before"],
            "rpo": summary["rpo_before"],
            "revenue_by_period": [
                {"period_key": row["period_key"], "amount": row["before"]} for row in revenue
            ],
            "balances": summary["balances_before"],
        },
        after=after,
    )


@dataclass(frozen=True, slots=True)
class _Segment:
    """One status segment of a contract in a book, as the engine traced it (ENGINE_SPEC §2.1
    ``StatusSegment``): the stream version of the event that began it, its status and its reason."""

    stream_version: int
    status: str
    reason: str


def _segments(
    bundle: InputBundle, output: OutputBundle, external_id: str
) -> dict[str, list[_Segment]]:
    """Per book, the status segments of the contract in ENG-06 order, read from the computation's
    status trace: stage 02 writes one node per segment — formula ``step1.status.v1``, measure
    ``status@<event key>``, params ``status`` and ``reason``. ``BookOutput.status_in_book`` gives a
    member's final status only; the reason of a segment, and the event that began it, are here."""
    order = {
        event.event_key: (event.effective_date, event.record_seq, event.stream_version)
        for event in bundle.events
        if event.contract_key == external_id
    }
    found: dict[str, list[_Segment]] = {}
    for book in output.books:
        rows: list[tuple[tuple[Any, int, int], _Segment]] = []
        for node in book.trace.nodes:
            if node.formula_id != STATUS_FORMULA or not node.measure.startswith(STATUS_MEASURE):
                continue
            position = order.get(node.measure.removeprefix(STATUS_MEASURE))
            if position is None:
                continue  # an event of another member of the group
            rows.append(
                (
                    position,
                    _Segment(
                        stream_version=position[2],
                        status=str(node.params["status"]),
                        reason=str(node.params["reason"]),
                    ),
                )
            )
        rows.sort(key=lambda item: item[0])
        found[str(book.book_code)] = [segment for _, segment in rows]
    return found


def _other_reason(other: Mapping[str, str], *, now: datetime) -> Problem:
    """409 ``activation-checklist-failed`` on ``STEP1_RECORD`` with one IMP-133 sentence per book
    that is not a contract for a reason other than collectibility (ruling R-102 (a), Q1)."""
    lines = [
        STEP1_OTHER_REASON_MESSAGE.format(
            book=code, reason=OTHER_REASONS.get(reason, reason.replace("_", " ").lower())
        )
        for code, reason in sorted(other.items())
    ]
    return checklist_problem(Checklist(items=(_item(STEP1_RECORD, lines),), evaluated_at=now))


def _confirm_reentry(
    session: Session,
    current: Mapping[str, Any],
    bundle: InputBundle,
    output: OutputBundle,
    criteria: Sequence[CriteriaMet],
    *,
    now: datetime,
) -> None:
    """Ruling R-102 (a): the engine confirms the criteria-met path of each book under an ACTIVE
    header, from the status trace of the dry run that carries the pending ``CONTRACT_CRITERIA_MET``
    events. A book moves when the pending event began a segment with reason CRITERIA_MET and the
    segment before it is NOT_A_CONTRACT with reason NOT_PROBABLE, begun by the very event the Step
    1 replay names (``Step1Stream.out``) — so the judgement that is cited was reviewed after the
    event the ENGINE left recognition at. Refused otherwise, before anything is written: by name
    (PRD IMP-133) when an enabled book of the contract — one that would move, or any other — is not
    a contract for another reason: Table 2.2-A leaves NOT_A_CONTRACT on ``CONTRACT_CRITERIA_MET``
    whatever the reason and does not test commercial substance again, so the platform does not
    append it for a contract the engine holds out on 606-10-25-1(d) or 606-10-25-4; and as
    unconfirmed when the pending event moves nothing. With no criteria (nothing moves by the Step 1
    events) the contract is not submittable."""
    external_id = str(current["external_id"])
    head = int(current["head_stream_version"])
    out_of_recognition = ContractStatus.NOT_A_CONTRACT.value
    segments = _segments(bundle, output, external_id)
    stream = step1.read(session, _uuid(current["id"]))
    other: dict[str, str] = {}
    for code in step1.enabled_books(session, _uuid(current["contracting_entity_id"])):
        rows = segments.get(code, [])
        if (
            rows
            and rows[-1].status == out_of_recognition
            and rows[-1].reason != REASON_NOT_PROBABLE
        ):
            other[code] = rows[-1].reason
    unconfirmed: list[str] = []
    for item in criteria:
        rows = segments.get(item.book, [])
        put_out = stream.out.get(item.book)
        index = next(
            (
                position
                for position, row in enumerate(rows)
                if row.stream_version > head and row.reason == REASON_CRITERIA_MET
            ),
            None,
        )
        before = rows[index - 1] if index else None
        if before is None or before.status != out_of_recognition:
            unconfirmed.append(item.book)
        elif before.reason != REASON_NOT_PROBABLE:
            other[item.book] = before.reason
        elif put_out is None or before.stream_version != put_out.stream_version:
            unconfirmed.append(item.book)
    if other:
        raise _other_reason(other, now=now)
    if unconfirmed:
        raise _refuse(NOT_CONFIRMED.format(books=", ".join(unconfirmed)))
    if not criteria:
        raise _refuse(NOT_SUBMITTABLE)


def _nothing_out(session: Session, group_id: UUID, current: Mapping[str, Any]) -> bool:
    """Ruling R-102 (a), the supervisor's word on the slice (2026-10-01): a refused
    ``submit-activation`` does not cost a computation of the group. Whether what is stored already
    answers that no enabled book of an ACTIVE contract is out: nothing by the Step 1 replay
    (``Step1Stream.out``), and the engine's own last answer — T-CON-08 ``status_in_book`` of the
    group's latest version in every enabled book — is another status than NOT_A_CONTRACT. That
    answer counts only while it is the head's: the group has a head computation and is not dirty
    (RCP-17). The LEGACY book has no contract version and no status ([J] L3-1-Q-22). ``False``
    leaves the answer to the dry run, which alone knows the reason a book is out for (PRD
    IMP-133). T-CON-08 holds ONE status for the group — the latest segment across its members
    — so for a member of a combined group the stored answer is the group's."""
    group = repo.get_group(session, group_id)
    if group["head_computation_id"] is None or group["dirty_since"] is not None:
        return False
    books = step1.enabled_books(session, _uuid(current["contracting_entity_id"]))
    stream = step1.read(session, _uuid(current["id"]))
    if any(code in stream.out for code in books):
        return False
    for code in books:
        if code == BookCode.LEGACY.value:
            continue
        version = bundles.previous_version(session, group_id, code)
        if version is None or (
            _text(version["status_in_book"]) == ContractStatus.NOT_A_CONTRACT.value
        ):
            return False
    return True


def submit_activation(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int | None,
    body: SubmitActivationIn,
    engine: computation.Engine | None = None,
) -> Submitted:
    """``POST /contracts/{id}/submit-activation`` (04 §16.1; SM-02; REQ-CON-005, REQ-CON-006)."""
    session = uow.session
    group_id, current = repo.lock_group_then_contract(session, contract_id)
    require_for_entity(uow.ctx, CREATE_PERMISSION, current["contracting_entity_id"])
    head = int(current["head_stream_version"])
    if expected_stream_version != head:
        raise Problem("precondition-failed", STALE_CONTRACT)
    status = _text(current["status"])
    if status not in SUBMITTABLE:
        raise _refuse(NOT_SUBMITTABLE)
    if _pending_request(session, contract_id) is not None:
        raise _refuse(ALREADY_IN_REVIEW)
    checklist = evaluate(session, current, now=uow.now)
    if checklist.failed:
        raise checklist_problem(checklist)
    # Ruling R-20 (c): a NOT_A_CONTRACT contract is activated with its criteria-met events pending
    # beside the activation — the dry run is the one the approval will persist. Ruling R-102 (a):
    # under an ACTIVE header the request is the criteria-met path of a book — the criteria-met
    # events alone, no activation event — and the engine confirms every book before it is made.
    criteria = criteria_met(session, current)
    reentry = status == ContractStatus.ACTIVE.value
    if reentry and not criteria and _nothing_out(session, group_id, current):
        # Nothing moves and nothing is out: refused as ``_confirm_reentry`` refuses it, without
        # the dry run that function reads.
        raise _refuse(NOT_SUBMITTABLE)
    pending = _criteria_events(criteria)
    if not reentry:
        pending.append(_activated(current, checklist, criteria=criteria))
    run = engine if engine is not None else computation.default_engine()
    try:
        bundle = (
            bundles.build(
                session, group_id, uow.now, pending, DRY_RUN, pending_contract_id=contract_id
            )
            if pending
            else bundles.build(session, group_id, uow.now, (), DRY_RUN)
        )
        output = run(bundle)
    except EngineError as error:
        raise engine_problem(error) from error
    if reentry:
        _confirm_reentry(session, current, bundle, output, criteria, now=uow.now)
    summary = impact_summary(
        session, current, bundle, output, pending, computed_at=uow.now, criteria_met=bool(criteria)
    ).model_dump(mode="json")
    totals = step1_catch_up_totals(session, current, output, [item.book for item in criteria])
    with system_entity_scope(session):
        # Item ACT-FLAGS-1 (04 §16.10 rev 1.287; dev-guide DG-KRN-APR-01 rev 1.273): the command
        # holds the dry run, so it states the request's flags and amount itself — the financing
        # adjustment and ruling R-66 (4)'s price are in no row a Session reads — and hands them
        # to ``approvals.submit``. What a request states must not depend on who submits (R-64
        # (1)): they are read under the tenant's scope, as the kernel reads a subject's own.
        stated = routing_facts(
            session,
            contract_id,
            measured_by(
                output,
                str(current["transaction_currency"]).strip(),
                str(current["external_id"]),
            ),
            known_at=uow.now,
        )
    flags = stated.flags
    left = books_left_not_a_contract(session, current)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.CONTRACT_ACTIVATION,
        subject_id=contract_id,
        summary=(
            f"Criteria met: {current['external_id']} ({', '.join(i.book for i in criteria)})"
            if reentry
            else f"Activate {current['external_id']}"
        ),
        impact_preview=_preview(status, summary, criteria, totals),
        comment=body.comment,
        # Ruling R-61 (c): a request that carries criteria-met books is never offered to the
        # auto-approval rules, whatever its flags and whoever wrote the stream. Ruling R-77 (2):
        # nor is an activation that leaves a book NOT_A_CONTRACT on a not-probable assessment.
        auto_approval=not flags and not criteria and not left,
        amount=stated.amount,
        flags=flags,
    )
    request_id = _uuid(request["id"])
    # An ACTIVE contract stays ACTIVE in the read model while its request is pending (no status
    # moves, DG-SM-03 has nothing to audit); the request itself is audited by the kernel.
    if _text(request["status"]) == ApprovalRequestStatus.PENDING.value and not reentry:
        uow.audit(
            action=f"{OBJECT_TYPE}.{ContractStatus.PENDING_REVIEW.value.lower()}",
            object_type=OBJECT_TYPE,
            object_id=contract_id,
            object_version=str(head),
            before={"status": status},
            after={"status": ContractStatus.PENDING_REVIEW.value},
            comment=body.comment,
            approval_request_id=request_id,
            contract_id=contract_id,
        )
    return Submitted(
        contract=queries.contract_out(session, contract_id, now=uow.now),
        approval_request_id=request_id,
    )


def _system_unit(uow: UnitOfWork, on_behalf_of: UUID | None) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, on behalf of the preparer."""
    principal = system_principal(uow.principal.tenant_id, on_behalf_of_id=on_behalf_of)
    ctx = dataclasses.replace(uow.ctx, principal=principal)
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def activate(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    approval_request_id: UUID | None,
    on_behalf_of: UUID | None,
    engine: computation.Engine | None = None,
    gate: bool = True,
    compute: bool = True,
    consumed: approvals.ConsumedBasis | None = None,
    stored_lines: bool = False,
) -> Mapping[str, Any] | None:
    """The approved activation (SM-02 PENDING_REVIEW → ACTIVE; DG-CMD-09 decision command).

    The checklist is evaluated again (409 when an item fails and ``gate``), SYSTEM appends
    ``CONTRACT_ACTIVATED`` at the inception date on behalf of the preparer with the request id, and
    the group is computed and persisted; an ``EngineError`` raises 422 and rolls everything back.
    A contract that is NOT_A_CONTRACT (ruling R-20 (c); 04 §16.1 rev 1.105) takes both SM-02 steps
    here: SYSTEM first appends ``CONTRACT_CRITERIA_MET`` for each book that moves (stored
    NOT_A_CONTRACT → PENDING_REVIEW), then ``CONTRACT_ACTIVATED`` dated the latest criteria-met
    date (PENDING_REVIEW → ACTIVE), each with the request id — two appends, because DB-03 holds
    the two pairs and no pair NOT_A_CONTRACT → ACTIVE.
    A contract that is ACTIVE (ruling R-102 (a); 04 §16.1 rev 1.150) takes the criteria-met path
    of a book: the engine confirms each book again under the locks (``_confirm_reentry``), SYSTEM
    appends the ``CONTRACT_CRITERIA_MET`` events and NO ``CONTRACT_ACTIVATED``, and the header
    does not move.
    ``gate = False`` serves the BS3-D-19 test factory, which activates fixtures without Step 1
    records, and ``compute = False`` the fixtures whose figures count the postings of a later
    computation (L4-1-Q-21). ``consumed`` is the composition of an import approval that stands as
    this activation's approval (BR-DAT-06; DG-KRN-APR-05 rev 1.51): the IMPORT_COMMIT job consumed
    that basis fresh under the authoritative locks before any effect, and the relationship is
    verified here instead of re-hashing a subject this hook does not apply.
    ``stored_lines`` is the caller's word that it keeps the lines of a failing checklist for
    others to read — a Contract Setup commit stores them as the message of an exception item of
    the contract's entity — so they are written for those readers and not for this session
    (``combination_suggestions``; item ACT-CHECKLIST-SUGGESTION-SCOPE-1). Returns the stored
    computation, or None without one.
    """
    session = uow.session
    group_id, current = repo.lock_group_then_contract(session, contract_id)
    if consumed is not None:
        # DG-KRN-APR-05 rev 1.51 (D-98 candidate 119): the import approval stands as this
        # activation's approval (BR-DAT-06); its basis was consumed fresh under the locks before the
        # job's first effect, and the composition must be this transaction's, cover this contract's
        # key and name the same request — the job's own booking moved the heads the import content
        # pins, so re-hashing that subject here refused every legacy import (P5-RET-1).
        if not consumed.covers(
            uow, key=str(current["external_id"]), approval_request_id=approval_request_id
        ):
            raise LookupError(
                f"contract {contract_id} is activated outside its consumed import composition"
            )
    elif approval_request_id is not None:
        # The hook's own CONTRACT_ACTIVATION request (D-98 candidate 101d, R3d-b): under the group
        # and contract locks, before the first write, the contract must still hash to the basis the
        # approver reviewed (contract_activation_content pins its head and group). A request for
        # another subject is refused here, never skipped — provenance needs its composition.
        approvals.assert_own_fresh_basis(
            uow,
            approval_request_id,
            subject_type=ApprovalSubjectType.CONTRACT_ACTIVATION,
            subject_id=contract_id,
        )
    status = _text(current["status"])
    if status not in SUBMITTABLE:
        raise _refuse(NOT_ACTIVATABLE)
    checklist = evaluate(session, current, now=uow.now, stored=stored_lines)
    if gate and checklist.failed:
        raise checklist_problem(checklist)
    criteria = criteria_met(session, current)
    reentry = status == ContractStatus.ACTIVE.value
    if status != ContractStatus.DRAFT.value and not criteria:
        # Without a book that moves there is nothing to activate (``gate = False`` included).
        raise _refuse(CRITERIA_NOT_MET)
    if reentry:
        # Ruling R-102 (a): confirmed again by the engine, under the locks and before the first
        # write — the approval appends only what its dry run moves.
        run = engine if engine is not None else computation.default_engine()
        try:
            bundle = bundles.build(
                session,
                group_id,
                uow.now,
                _criteria_events(criteria, approval_request_id),
                DRY_RUN,
                pending_contract_id=contract_id,
            )
            output = run(bundle)
        except EngineError as error:
            raise engine_problem(error) from error
        _confirm_reentry(session, current, bundle, output, criteria, now=uow.now)
    system = _system_unit(uow, on_behalf_of)
    head = int(current["head_stream_version"])
    if criteria:
        append_events(
            system,
            contract_id=contract_id,
            expected_stream_version=head,
            events=_criteria_events(criteria, approval_request_id),
            origin="SYSTEM",
        )
        head += len(criteria)
    if not reentry:
        append_events(
            system,
            contract_id=contract_id,
            expected_stream_version=head,
            events=[_activated(current, checklist, approval_request_id, criteria=criteria)],
            origin="SYSTEM",
        )
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    if not compute:
        return None
    try:
        return computation.recompute(
            uow, group_id, trigger=ComputationTrigger.COMMAND, engine=engine
        )
    except EngineError as error:
        raise engine_problem(error) from error


def _approved(uow: UnitOfWork, contract_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``CONTRACT_ACTIVATION``."""
    preparer = (
        uow.session.execute(
            select(approval_request.c.preparer_id, approval_request.c.preparer_kind).where(
                approval_request.c.id == approval_request_id
            )
        )
        .mappings()
        .one_or_none()
    )
    on_behalf_of = (
        _uuid(preparer["preparer_id"])
        if preparer is not None
        and preparer["preparer_id"] is not None
        and _text(preparer["preparer_kind"]) == PrincipalKind.USER.value
        else None
    )
    activate(
        uow,
        contract_id=contract_id,
        approval_request_id=approval_request_id,
        on_behalf_of=on_behalf_of,
    )


RETURNS_TO: Final = (ContractStatus.DRAFT.value, ContractStatus.NOT_A_CONTRACT.value)


def _returned(uow: UnitOfWork, contract_id: UUID, approval_request_id: UUID) -> None:
    """``on_rejected`` and ``on_voided``: SM-02 PENDING_REVIEW → DRAFT appends nothing
    (L4-1-Q-18), and neither does the return of a criteria-met activation to NOT_A_CONTRACT (SM-02
    rev 1.34): the stored status never left it, and the read model answers it again."""
    status = uow.session.execute(
        select(contract.c.status).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if status is None or _text(status) not in RETURNS_TO:
        return
    uow.audit(
        action=f"{OBJECT_TYPE}.{_text(status).lower()}",
        object_type=OBJECT_TYPE,
        object_id=contract_id,
        before={"status": ContractStatus.PENDING_REVIEW.value},
        after={"status": _text(status)},
        approval_request_id=approval_request_id,
        contract_id=contract_id,
    )


register_lifecycle(
    ApprovalSubjectType.CONTRACT_ACTIVATION,
    SubjectLifecycle(
        on_approved=_approved,
        on_rejected=_returned,
        on_voided=_returned,
        flags=activation_flags,
        amount=activation_amount,
    ),
)


# --- distinct review -----------------------------------------------------------------------------


def record_distinct_review(
    uow: UnitOfWork, *, contract_id: UUID, obligation_key: str, body: DistinctReviewIn
) -> DistinctReviewOut:
    """``POST /contracts/{id}/obligations/{obligation_key}/distinct-review``: a
    ``POB_DISTINCT_OVERRIDE`` judgement record of the obligation, submitted for review (04 §16.1;
    REQ-POB-001; SCREENS R-17)."""
    session = uow.session
    repo.get_contract(session, contract_id)
    rows = {str(row["obligation_key"]): row for row in repo.obligations(session, contract_id)}
    found = rows.get(obligation_key)
    if found is None:
        raise Problem("not-found", OBLIGATION_UNKNOWN.format(key=obligation_key))
    integrates = body.integrates_into_obligation_key
    errors: list[ProblemError] = []
    if body.distinctness is Distinctness.NONDISTINCT and integrates is None:
        errors.append(
            ProblemError(
                field="integrates_into_obligation_key",
                rule_id=RULE_REVIEW,
                message=INTEGRATES_REQUIRED,
            )
        )
    if integrates is not None and (integrates not in rows or integrates == obligation_key):
        errors.append(
            ProblemError(
                field="integrates_into_obligation_key",
                rule_id=RULE_REVIEW,
                message=OBLIGATION_UNKNOWN.format(key=integrates),
            )
        )
    if errors:
        raise Problem("validation-failed", errors[0].message, errors=errors)
    product_code = str(
        session.execute(
            select(product.c.code).where(product.c.id == found["product_id"])
        ).scalar_one()
    )
    questionnaire: dict[str, Any] = {
        "obligation_key": obligation_key,
        "distinctness": body.distinctness.value,
    }
    if integrates is not None:
        questionnaire["integrates_into_obligation_key"] = integrates
    created = judgements.create_judgement(
        uow,
        body=JudgementCreateIn(
            topic=JudgementTopic.POB_DISTINCT_OVERRIDE,
            subject_type="obligation",
            subject_id=_uuid(found["id"]),
            contract_id=contract_id,
            conclusion=CONCLUSIONS[body.distinctness.value].format(
                key=obligation_key, product=product_code, other=integrates
            ),
            rationale=body.rationale,
            codification_refs=list(body.codification_refs),
            questionnaire=questionnaire,
        ),
    )
    submitted = judgements.submit_judgement(uow, judgement_id=created.id, body=JudgementSubmitIn())
    return DistinctReviewOut(
        judgement_record_id=created.id, approval_request_id=submitted.approval_request_id
    )
