"""CTR-17 Modifications: object, guided classification, impact preview and approval (BUILD_SPEC
CTR-17; D-98 140 — the supervisor's engineering rulings on the design note
``docs/reviews/loop/prod/F-CTR-CTR17-DESIGN-NOTE.md``; 04 T-CON-06, §16.10, §16.14
API-S-Modification; PRD SM-03, §2.5 routing row ``MODIFICATION``, ERR-53 / ERR-54; ENGINE_SPEC §6.2
S06-R-01 to S06-R-05, S06-R-19; 03 REQ-MOD-001, -002, -013, -022, REQ-PLT-015).

Lifecycle (SM-03). ``create_modification`` opens a DRAFT on an ACTIVE contract;
``update_modification`` edits a DRAFT (an edit of a SUBMITTED row returns it to DRAFT and voids its
request STALE_SUBJECT, CTL-007). ``classify`` runs the engine over the group with the row carried
as a pending T-CON-06 object and no event: stage 13 proposes for it (S06-R-01;
``_pending_proposals``) and the proposal is stored as ``proposed_treatments`` /
``treatment_summary`` — the classification is the engine's S06-R-04 / S06-R-05 reading, never the
platform's; its response also proposes the questionnaire answers the system can compute
(BR-MOD-01; ``questionnaire_prefill`` over the engine's proposal nodes) and stores none of them —
a stored answer is the preparer's. ``request_preview`` defers ``CONTRACT_COMPUTE`` in mode
``MODIFICATION_PREVIEW``; ``run_preview`` is the DG-CMD-15 dry run with the candidate
``CONTRACT_AMENDED`` pending (S06-R-02), measured AT that boundary (``boundary_summary``: PRD
WLD-X-05 / WLD-X-06), whose API-S-ImpactSummary and provenance (engine version, input hash, the
contract's head) are stored as an ``IMPACT_PREVIEW`` file and hashed into
``impact_preview_sha256``. ``submit`` refuses without that preview (422 ``rule_id = "REQ-PLT-015"``,
PRD ERR-53) and refuses a ``chosen_treatments`` departure from the proposal without a REVIEWED
``MODIFICATION_TREATMENT_OVERRIDE`` judgement (422 ``rule_id = "REQ-MOD-002"``, ERR-54); it hashes
the §16.10 content, routes the ``MODIFICATION`` request with the PRD §2.5 facts derived from the
stored preview (D-98 140 Q-5: the two second-step flags and ``amount_functional`` = the absolute
transaction-price change when the contract currency is the entity's functional currency — the
preview's basis; None otherwise, no FX conversion at submission) and hands the retained preview —
the same file and hash — to the request as its impact preview (04 §16.14 rev 1.92).

Approval (``_approved``, DG-CMD-09 decision command): the protecting locks in the kernel order —
``lock_group_then_contract`` for one row, ``lock_groups_then_contracts`` for a regroup-after-posting
pair (D-98 140 Q-4: ONE spanning request applies both amendments or neither) — then
``approvals.assert_fresh_basis`` (DG-KRN-APR-05), then SYSTEM appends ``CONTRACT_AMENDED`` on behalf
of the preparer with ``modification_id`` and ``approval_request_id`` (a ``SEPARATE_CONTRACT`` choice
books a new contract instead, S06-R-03 — its own commit), the row becomes APPLIED with
``applied_event_id`` and each group recomputes; an ``EngineError`` rolls the decision back (422),
so neither amendment applies (SM-03's "Quarantined" presentation is the computation path's).
"""

from __future__ import annotations

import dataclasses
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.bundle import FxRateInput, InputBundle, OutputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.money import cumulative_posted, minor_to_decimal
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    encode_key,
    obligation_subject_key,
)
from erev_engine.stages.s12_fx_entities.rates import SPOT, RateMissing, Rates
from erev_engine.trace import TraceNode
from sqlalchemy import and_, func, insert, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from erev_api import numbering
from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    MODIFICATION_CATCH_UP_FLAG,
    MODIFICATION_TP_CHANGE_FLAG,
    THRESHOLD_CURRENCY,
    SubjectLifecycle,
    modification_content,
    modification_rows,
    register_lifecycle,
)
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import Principal, system_principal
from erev_api.db import new_id, transitions
from erev_api.db.locking import lock_group_then_contract, lock_groups_then_contracts
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    contract,
    estimate,
    estimate_version,
    job,
    judgement_record,
    legal_entity,
    modification,
    obligation,
    obligation_version,
    product,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.contracts import bundles, commands, computation, queries, repo
from erev_api.domain.contracts.activation import engine_problem
from erev_api.domain.contracts.compute_job import MODIFICATION_PREVIEW_MODE
from erev_api.domain.contracts.events import DRY_RUN, dry_run_summary, impact_summary
from erev_api.domain.platform import approval_queries, file_access
from erev_api.domain.platform.jobs import JOB_COLUMNS, job_outs
from erev_api.domain.reference.products import required_attribute_errors
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ComputationTrigger,
    ConfigStatus,
    ContractEventType,
    ContractStatus,
    FilePurpose,
    JobKind,
    JudgementStatus,
    JudgementTopic,
    ModificationKind,
    ModificationStatus,
    ModificationTreatment,
    PrincipalKind,
)
from erev_api.events.payloads import (
    ContractAmendedV1,
    ContractBookedV1,
    RegroupedV1,
    payload_json,
)
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import open_file, store_file
from erev_api.jobs.registry import JobOutcome
from erev_api.money import money_out
from erev_api.problems import Problem, ProblemError
from erev_api.registry import resolve as registry
from erev_api.schemas.common import ActorOut, JobOut
from erev_api.schemas.events import (
    ImpactCatchUpOut,
    ImpactObligationAmountOut,
    ImpactSummaryOut,
)
from erev_api.schemas.modifications import (
    ModificationCreateIn,
    ModificationImpactOut,
    ModificationListItemOut,
    ModificationOut,
    ModificationSubmitIn,
    ModificationUpdateIn,
    ModificationWithdrawIn,
)
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext

__all__ = [
    "APPROVE_PERMISSION",
    "CREATE_PERMISSION",
    "OBJECT",
    "boundary_measure",
    "boundary_summary",
    "classify",
    "create_modification",
    "discard",
    "get_modification",
    "modification_outs",
    "modifications_statement",
    "override_applies",
    "override_version_errors",
    "preview_basis",
    "price_tests",
    "questionnaire_prefill",
    "request_sides",
    "separate_choice",
    "separate_errors",
    "ssp_basis_mismatches",
    "ssp_selection_mismatches",
    "stored_classification",
    "booking_body",
    "request_preview",
    "routing_facts",
    "spot_basis",
    "strip_preview_hashes",
    "run_preview",
    "submit",
    "update_modification",
    "withdraw",
]

CREATE_PERMISSION: Final = "modification.create"  # PRD ACT; 04 API-R-31
APPROVE_PERMISSION: Final = "modification.approve"  # PRD §2.5 routing row MODIFICATION
OBJECT: Final = "modification"
SERIES: Final = "MODIFICATION"  # 04 T-CON-06 modification_no
HREF: Final = "/api/v1/modifications/{modification_id}"
DRAFT: Final = ModificationStatus.DRAFT.value
SUBMITTED: Final = ModificationStatus.SUBMITTED.value
APPROVED: Final = ModificationStatus.APPROVED.value
APPLIED: Final = ModificationStatus.APPLIED.value
REJECTED: Final = ModificationStatus.REJECTED.value
VOIDED: Final = ModificationStatus.VOIDED.value
PROPOSAL_KIND: Final = "MODIFICATION_TREATMENT"  # engine ProposalOut.kind (CV-16)
# Rule ids of the 422 refusals (04 §16.14 rev 1.70; PRD ERR-53 / ERR-54; BUILD_SPEC CTR-17 tests).
RULE_PREVIEW: Final = "REQ-PLT-015"
RULE_TREATMENT: Final = "REQ-MOD-002"
RULE_REFERENCE: Final = "ux_modification__reference"
RULE_OBLIGATION: Final = "T-CON-10"
RULE_STATE: Final = "SM-03"
RULE_CLASSIFIED: Final = "REQ-MOD-001"
RULE_SEPARATE: Final = "S06-R-03"  # D-98 140-A6 SEPARATE-CHOICE-1 / SEPARATE-INPUT-1
RULE_WEIGHTS: Final = "S06-R-11"  # 01-DECISIONS D-18: the version a weight is priced from
RULE_LINE_CURRENCY: Final = "T-CON-06"  # D-98 140-A6 NATIVE-MONEY-1
RULE_LINE_SHAPE: Final = "S06-R-19"  # MAIN DEFECT 3: PRD 1.18 ERR-55; 04 1.84
CATCH_UP_MEASURE: Final = "catch_up@"  # ENGINE_SPEC CV-50: catch_up@<event key>:<ob>:- (S06-R-17)
# BR-MOD-01 (04 §16.14 rev 1.92; SCREENS §7.5): the questionnaire answers the system can compute,
# read from the engine's own proposal nodes of the row (CV-50 ``mod_class@<position>`` with the
# S06-R-05 reason, ``mod_price_test@<position>`` with the POL-101 test) — never re-derived here.
CLASS_MEASURE: Final = "mod_class@"
PRICE_TEST_MEASURE: Final = "mod_price_test@"
QUESTION_ADDED: Final = "added_goods_distinct"
QUESTION_PRICED: Final = "priced_at_ssp"
QUESTION_REMAINING: Final = "remaining_goods_distinct_from_transferred"
PREFILL_KEY: Final = "modifications.prefill.{question}.{reason}"  # the caption's catalogue key
# T-CON-06 ``classification`` (04 rev 1.286; item MOD-CLASSIFICATION-KEYS-1): three members and
# no other — the engine's proposal detail (CV-16), the per-obligation proposals and the engine's
# price tests (item MOD-PRICE-TEST-FACT-1; 04 §16.14 rev 1.250). An obligation key is free text,
# so it stands only INSIDE ``obligations`` and ``price_tests``. Before, the obligations' entries
# lay beside the other two members: an obligation keyed ``proposal`` took the detail's place and
# one keyed ``price_tests`` lost its proposals to the member written last.
PROPOSAL_KEY: Final = "proposal"
OBLIGATIONS_KEY: Final = "obligations"
PRICE_TESTS_KEY: Final = "price_tests"
_ENTRY_MEMBERS: Final = frozenset({"value", "reason_key", "params"})
# S06-R-05 reason of an existing obligation's class → the prefilled "remaining goods distinct"
# answer (class D true, class N false); SATISFIED leaves nothing remaining and QUESTIONNAIRE is
# the preparer's own answer, so neither is prefilled.
_REMAINING_REASONS: Final[Mapping[str, tuple[bool, str]]] = MappingProxyType(
    {
        "UNSTARTED": (True, "unstarted"),
        "SERIES": (True, "series"),
        "DISTINCT_UNITS": (True, "distinct_units"),
        "PARTIALLY_SATISFIED": (False, "partially_satisfied"),
    }
)
# S06-R-05 reason of an added line's class → the prefilled "added goods distinct" answer. A line
# the engine gave no class of its own (it integrates into an existing obligation, S03-R-05, or
# stage 03 built no draft) is not prefilled: the system cannot compute that answer.
_ADDED_REASONS: Final[Mapping[str, tuple[bool, str]]] = MappingProxyType(
    {"NEW_DISTINCT": (True, "new_distinct"), "NEW_UNSTARTED": (False, "new_unstarted")}
)
# The engine's S06-R-19 refusals (erev_engine/stages/s06_modifications/subscriptions.py,
# ``_require`` / ``check``) all end with this literal; a line refusal names its key as
# "line <key> does not have the".
_S06_R19_SUFFIX: Final = "(S06-R-19)"
_S06_R19_SHAPES: Final = (
    re.compile(r"^.+?: line (?P<key>.+?) does not have the [A-Z_]+ shape \(S06-R-19\)$"),
    re.compile(r"^.+?: a [A-Z_]+ modification has lines \(S06-R-19\)$"),
    re.compile(r"^.+?: an early renewal adds a renewal line \(S06-R-19\)$"),
)
SSP_VERSION_BASIS: Final = "ssp.version_basis"  # POL-070
# PRD §2.5 second-step thresholds (D-98 140 Q-5), evaluated from the stored preview at submit.
CATCH_UP_THRESHOLD: Final = Decimal("50000.00")
TP_CHANGE_THRESHOLD: Final = Decimal("250000.00")
AMOUNT_BASIS_FUNCTIONAL: Final = "transaction_currency_is_functional_currency"
AMOUNT_BASIS_RETAINED: Final = "retained_preview_spot_rate"  # 04 §16.14 fx_basis (D-98 140-A5)
# Audit actions (AUD-CMD).
CREATE_ACTION: Final = "modification.create"
UPDATE_ACTION: Final = "modification.update"
CLASSIFY_ACTION: Final = "modification.classify"
PREVIEW_ACTION: Final = "modification.preview_stored"
# The audit action of a refused preview request (04 §16.10 rev 1.295): a request that is taken
# writes ``job.start``, and the job the action above.
PREVIEW_REQUEST_ACTION: Final = "modification.preview"
SUBMIT_ACTION: Final = "modification.submit"
WITHDRAW_ACTION: Final = "modification.withdraw"
DISCARD_ACTION: Final = "modification.discard"
APPLY_ACTION: Final = "modification.applied"
CLOSE_ACTION: Final = "modification.request_closed"
# Copy (PRD §5.5; ERR-53 / ERR-54; CPY-01 to CPY-03).
PREVIEW_REQUIRED: Final = (
    "Run the impact preview of this modification before submitting it; approvers decide on the "
    "stored preview snapshot."
)
TREATMENT_OVERRIDE: Final = (
    "Choosing a treatment other than the proposed one for {key} needs a reviewed judgement record "
    "of topic MODIFICATION_TREATMENT_OVERRIDE. Link one or keep the proposal."
)
NOT_ACTIVE: Final = "Only an active contract can be modified; {external_id} is {status}."
REFERENCE_REPEATED: Final = (
    "Reference {reference} is already used by modification {modification_no} of this contract."
)
UNKNOWN_OBLIGATION: Final = "{external_id} has no obligation {key}; use ADD for a new obligation."
ADD_NEEDS_PRODUCT: Final = "An ADD line names the product of the new obligation."
# Item MOD-REJECTED-REVISE-1 (the supervisor's ruling of 2026-10-01; PRD SM-03 "Revise"; 04
# §16.14 rev 1.236): a rejected modification is edited too — the edit returns it to DRAFT.
NOT_EDITABLE: Final = "Only a draft, submitted or rejected modification can be edited."
NOT_CLASSIFIABLE: Final = "Only a draft modification can be classified."
NOT_PREVIEWABLE: Final = "Only a draft modification takes a new preview; withdraw it first."
NOT_SUBMITTABLE: Final = "Only a draft modification can be submitted."
NOT_WITHDRAWABLE: Final = "Only a submitted modification with a pending request can be withdrawn."
# Item MOD-DISCARD-1 (supervisor ruling R-118 (e); PRD SM-03 "Discard draft"; 04 §16.14).
NOT_DISCARDABLE: Final = "Only a draft modification can be discarded."
# PRD ERR-82: a convention row of ``invalid-transition`` under the rule id of SM-03.
REVIEW_PENDING: Final = (
    "Judgement record {judgement_no} of this modification is waiting for review. Its preparer "
    "withdraws the review request first."
)
# Item MOD-LINKED-ESTIMATES-1 (supervisor rulings R-118 (e), R-119 (e); 04 §16.14 rev 1.210; PRD
# BR-MOD-02): convention rows of ``invalid-transition`` under the rule id of SM-03, one entry a
# version. PRD ERR-83 — the discard waits for a linked version that is waiting for approval.
LINKED_PENDING: Final = (
    "Estimate version {element_code} v{version_no} of this modification is waiting for approval. "
    "Its preparer withdraws it first."
)
# PRD ERR-87 — the linked versions are approved first. The submission says so; the approval's
# check is the backstop and ends on the approval.
LINKED_NOT_APPROVED: Final = (
    "Estimate version {element_code} v{version_no} of this modification is not approved. "
    "It is approved before the modification is submitted."
)
LINKED_NOT_APPROVED_AT_APPROVAL: Final = (
    "Estimate version {element_code} v{version_no} of this modification is not approved. "
    "The modification is approved after it."
)
# Item MOD-LINKED-JUDGEMENTS-1 (the supervisor's ruling of 2026-10-01; 04 §16.14 rev 1.242; PRD
# ERR-95): convention rows of ``invalid-transition`` under the rule id of SM-03, one entry a
# record. A judgement record whose subject is the modification is reviewed, or discarded, before
# the modification is submitted; the approval's check is the backstop and ends on the approval.
RECORD_NOT_REVIEWED: Final = (
    "Judgement record {judgement_no} of this modification is not reviewed. It is reviewed, or "
    "discarded, before the modification is submitted."
)
RECORD_NOT_REVIEWED_AT_APPROVAL: Final = (
    "Judgement record {judgement_no} of this modification is not reviewed. The modification is "
    "approved after it."
)
# E-57 statuses of a record that holds its modification; REVIEWED passes, and a REJECTED, a
# SUPERSEDED and a discarded (VOIDED) record hold nothing.
RECORD_OPEN: Final = frozenset({JudgementStatus.DRAFT.value, JudgementStatus.SUBMITTED.value})
# E-12 statuses of a linked version that is not approved; APPROVED and SUPERSEDED pass, and a
# discarded (VOIDED) version does not count.
LINKED_UNAPPROVED: Final = frozenset(
    {
        ConfigStatus.DRAFT.value,
        ConfigStatus.SUBMITTED.value,
        ConfigStatus.REJECTED.value,
        ConfigStatus.WITHDRAWN.value,
    }
)
UNCLASSIFIED: Final = "Classify the modification before submitting it; the proposal is required."
ANSWER_REQUIRED: Final = "Confirm this questionnaire answer before submitting the modification."
ANSWER_BOOLEAN: Final = "Answer this questionnaire question with true or false."
PREVIEW_STALE: Final = (
    "The stored preview is not of this modification as it stands; run the preview again."
)
PROPOSAL_MISSING: Final = (
    "The engine returned no treatment proposal for {modification_no}; the row cannot be classified."
)
SYSTEM_EDIT_COMMENT: Final = "Edited by the preparer after submission (SM-03; CTL-007)."
PREVIEW_BASIS_MISSING: Final = (
    "The stored preview retains no {rate_type} rate from {base} to {quote} on {date}; approve an "
    "FX rate set version covering the modification date and run the preview again."
)
PREVIEW_CURRENCY_MISMATCH: Final = (
    "The stored preview is in {found} while the modification is in {expected}; run the preview "
    "again."
)
SEPARATE_EXTERNAL_ID: Final = "separate_contract_external_id"  # questionnaire contract-level member
SEPARATE: Final = ModificationTreatment.SEPARATE_CONTRACT.value
LINE_CURRENCY_MISMATCH: Final = (
    "Line {key} states its consideration in {found}; the modification is in {expected}. Restate "
    "the line in {expected}."
)
SEPARATE_MIXED: Final = (
    "SEPARATE_CONTRACT applies to every line of a modification or to none; {key} is {treatment}."
)
SEPARATE_NEEDS_ADD: Final = "A separate contract books ADD lines only; {key} is {action}."
SEPARATE_UNSUPPORTED: Final = (
    "A separate contract cannot carry {member}; remove it or choose another treatment."
)
# D-98 140-A9 INPUT-1 (SSP basis): the booking pins SSP by label under POL-070 NAMED_VERSION only.
SSP_VERSION_UNKNOWN: Final = (
    "ssp_basis.{key} names no approved SSP book version; choose an approved version or remove the "
    "override."
)
SSP_LABEL_MISMATCH: Final = (
    "ssp_basis.{key} names version {version} while line {key} is labelled {label!r}; a separate "
    "contract pins SSP by the line's label, so the two must agree."
)
SSP_SELECTION_MISMATCH: Final = (
    "The booking's SSP selection for {key} is {selected}, not the override's {version}: another "
    "approved book shares the label, so the override cannot be honoured. Remove the override or "
    "choose another treatment."
)
SSP_SELECTION_UNRESOLVED: Final = (
    "The booking made no SSP selection for {key}, so the ssp_basis override cannot be verified."
)
MEMBER_CURRENCY_MISMATCH: Final = (
    "{member} is stated in {found}; the modification is in {expected}. Restate it in {expected}."
)
SSP_POLICY_NOT_NAMED: Final = (
    "The entity's SSP version basis is {option}; a separate contract can honour an ssp_basis "
    "override only under NAMED_VERSION (POL-070). Remove the override or choose another treatment."
)
PRODUCT_UNKNOWN: Final = "No product has the code {code}."
RULE_PRODUCT: Final = "T-REF-13"
BOOK_ACTION: Final = "modification.separate_contract_booked"
ADD: Final = "ADD"
REMOVE: Final = "REMOVE"


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _bump(uow: UnitOfWork) -> dict[str, Any]:
    """The SC-M stamps of an UPDATE with ``row_version`` advanced in the same statement (D-98
    140-A5 ROWVERSION-1): an IM-S table carries no ``tg_touch``, so every command of the row
    increments the version itself and audits the version of the resulting row (API-C-08)."""
    return {**_stamps(uow), "row_version": modification.c.row_version + 1}


def _error(field: str | None, rule_id: str, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _failed(*errors: ProblemError) -> Problem:
    return Problem("validation-failed", errors=list(errors))


def _invalid(message: str) -> Problem:
    return Problem("invalid-transition", errors=[_error(None, RULE_STATE, message)])


def linked_estimate_versions(
    session: Session, modification_ids: Sequence[UUID]
) -> list[dict[str, Any]]:
    """The estimate versions created inside the rows (T-CON-13 ``modification_id``) with their
    element's code and kind, by element code and version number (04 §16.14 rev 1.210). One read
    a row (a regroup pair has two): the equality proves the predicate of
    ``ix_estimate_version__modification`` and bounds its scan."""
    found: list[dict[str, Any]] = []
    for modification_id in modification_ids:
        statement = (
            select(
                estimate_version.c.id,
                estimate_version.c.estimate_id,
                estimate.c.element_code,
                estimate.c.estimate_kind,
                estimate_version.c.version_no,
                estimate_version.c.status,
                estimate_version.c.effective_date,
                estimate_version.c.modification_id,
            )
            .select_from(
                estimate_version.join(
                    estimate,
                    and_(
                        estimate.c.tenant_id == estimate_version.c.tenant_id,
                        estimate.c.id == estimate_version.c.estimate_id,
                    ),
                )
            )
            .where(estimate_version.c.modification_id == modification_id)
        )
        found.extend(dict(row) for row in session.execute(statement).mappings())
    return sorted(
        found, key=lambda row: (str(row["element_code"]), int(row["version_no"]), str(row["id"]))
    )


def _linked_errors(
    session: Session, modification_ids: Sequence[UUID], statuses: frozenset[str], template: str
) -> list[ProblemError]:
    """One SM-03 entry for every linked version in one of ``statuses``."""
    return [
        _error(
            None,
            RULE_STATE,
            template.format(element_code=found["element_code"], version_no=found["version_no"]),
        )
        for found in linked_estimate_versions(session, modification_ids)
        if _text(found["status"]) in statuses
    ]


def _record_errors(
    session: Session, modification_ids: Sequence[UUID], template: str
) -> list[ProblemError]:
    """One SM-03 entry for every judgement record whose subject is one of the modifications and
    that is DRAFT or SUBMITTED, in number order (item MOD-LINKED-JUDGEMENTS-1; PRD ERR-95).
    Measured before the rule: a modification was submitted, approved and applied beside such a
    record, and the record's review then answered 409 ``stale-approval`` — the applied event had
    moved the head its request pins — so a record that waited could never be reviewed."""
    waiting = session.execute(
        select(judgement_record.c.judgement_no)
        .where(
            judgement_record.c.subject_type == OBJECT,
            judgement_record.c.subject_id.in_(list(modification_ids)),
            judgement_record.c.status.in_(sorted(RECORD_OPEN)),
        )
        .order_by(judgement_record.c.judgement_no)
    ).scalars()
    return [_error(None, RULE_STATE, template.format(judgement_no=number)) for number in waiting]


def _row(session: Session, modification_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    statement = select(modification).where(modification.c.id == modification_id)
    if lock:
        statement = statement.with_for_update()
    found = session.execute(statement).mappings().one_or_none()
    if found is None:
        raise Problem("not-found")
    return dict(found)


def _require_prepare(uow: UnitOfWork, current: Mapping[str, Any]) -> None:
    require_for_entity(uow.ctx, CREATE_PERMISSION, _uuid(current["contracting_entity_id"]))


def _locked(uow: UnitOfWork, modification_id: UUID) -> tuple[dict[str, Any], UUID, dict[str, Any]]:
    """The row, its group id and its contract row under the kernel lock order (DG-KRN-DB-08: the
    combination group, then the contract row, then the T-CON-06 row ``FOR UPDATE``)."""
    peek = _row(uow.session, modification_id)
    group_id, current = lock_group_then_contract(uow.session, _uuid(peek["contract_id"]))
    _require_prepare(uow, current)
    return _row(uow.session, modification_id, lock=True), group_id, current


def _json(value: Any) -> Any:
    """JSON-safe copy of a pydantic model, tuple or mapping for a jsonb column."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json(item) for item in value]
    if isinstance(value, Decimal | UUID):
        return str(value)
    return value


def s06_r19_refusal(error: ValueError, row: Mapping[str, Any]) -> Problem | None:
    """MAIN DEFECT 3 (PRD 1.18 ERR-55; 04 1.84): the engine's S06-R-19 shape refusal — the CV-45
    programming-error guard ``subscriptions.check`` raises as a bare ``ValueError`` before any
    figure — translated BY ORIGIN into the named 422 at classify / preview: only a ``ValueError``
    whose text ends with the literal ``(S06-R-19)`` AND matches one of the three pinned shapes
    (subscriptions.py:241 / :249-252 / :254) is translated (``validation-failed``, ``rule_id``
    "S06-R-19", the engine's text as the message); the field is ``lines[<n>]`` of the named line
    key, else ``lines``. Any other ``ValueError`` is not ours and returns None — the boundary
    re-raises it unchanged (S06R19-TYPED-ERR-1: this message-origin coupling is retired by a typed
    engine exception at the next engine version step)."""
    text = str(error).strip()
    if not text.endswith(_S06_R19_SUFFIX):
        return None
    match = next((m for m in (p.match(text) for p in _S06_R19_SHAPES) if m is not None), None)
    if match is None:
        return None  # the literal alone is not the origin: one of the three pinned shapes is
    field = "lines"
    key = match.groupdict().get("key")
    if key is not None:
        keys = [
            str(line.get("obligation_key"))
            for line in (row.get("lines") or ())
            if isinstance(line, Mapping)
        ]
        if key in keys:
            field = f"lines[{keys.index(key)}]"
    return _failed(_error(field, RULE_LINE_SHAPE, text))


def _line_errors(
    session: Session, current: Mapping[str, Any], lines: Sequence[Any], *, at: date
) -> list[ProblemError]:
    """REMOVE and CHANGE lines name an obligation of the contract (T-CON-10); an ADD line names its
    product (S06-R-07). The engine judges the treatment (S06-R-04 / S06-R-05). The S06-R-19 line
    shape of a subscription kind is a bundle-assembly precondition (CV-45), checked by the
    platform at classify / preview (``s06_r19_refusal``; PRD ERR-55); create / PATCH shape
    validation is open item MOD-SHAPE-AT-CREATE-1."""
    keys = sorted({str(line.obligation_key) for line in lines})
    known = {
        str(value)
        for value in session.scalars(
            select(obligation.c.obligation_key).where(
                obligation.c.contract_id == _uuid(current["id"]),
                obligation.c.obligation_key.in_(keys),
            )
        )
    }
    errors = required_attribute_errors(
        session,
        {str(line.product_code) for line in lines if line.action == "ADD" and line.product_code},
        at=at,
    )
    for index, line in enumerate(lines):
        field = f"lines[{index}]"
        if line.action != "ADD" and str(line.obligation_key) not in known:
            errors.append(
                _error(
                    f"{field}.obligation_key",
                    RULE_OBLIGATION,
                    UNKNOWN_OBLIGATION.format(
                        external_id=current["external_id"], key=line.obligation_key
                    ),
                )
            )
        if line.action == "ADD" and line.product_code is None:
            errors.append(_error(f"{field}.product_code", RULE_OBLIGATION, ADD_NEEDS_PRODUCT))
        delta = getattr(line, "consideration_delta", None)
        found = None if delta is None else str(getattr(delta, "currency", "")).strip()
        expected = str(current["transaction_currency"]).strip()
        if found is not None and found != expected:
            # D-98 140-A6 NATIVE-MONEY-1 / SEPARATE-INPUT-1: never retagged, refused by name
            errors.append(
                _error(
                    f"{field}.consideration_delta.currency",
                    RULE_LINE_CURRENCY,
                    LINE_CURRENCY_MISMATCH.format(
                        key=line.obligation_key, found=found, expected=expected
                    ),
                )
            )
    return errors


def _reference_error(
    session: Session, contract_id: UUID, reference: str | None, *, except_id: UUID | None
) -> ProblemError | None:
    if reference is None:
        return None
    statement = select(modification.c.id, modification.c.modification_no).where(
        modification.c.contract_id == contract_id,
        modification.c.reference == reference,
        # 04 T-CON-06 rev 1.210 (``ux_modification__reference``): a discarded draft — VOIDED and
        # never applied — does not hold its reference; an applied modification that was voided
        # does.
        or_(modification.c.status != VOIDED, modification.c.applied_event_id.is_not(None)),
    )
    for found_id, number in session.execute(statement):
        if except_id is None or _uuid(found_id) != except_id:
            return _error(
                "reference",
                RULE_REFERENCE,
                REFERENCE_REPEATED.format(reference=reference, modification_no=number),
            )
    return None


def _member_currency_errors(
    body: ModificationCreateIn | ModificationUpdateIn, currency: str
) -> list[ProblemError]:
    """D-98 140-A12 (4): every Money member of ``consideration_payable`` (amount, distinct-good
    fair value, committed purchases) is validated against the modification's currency at the
    input boundary — a foreign currency is a named field refusal (T-CON-06), never an adapter
    error at classify. Pure."""
    errors: list[ProblemError] = []
    payable = getattr(body, "consideration_payable", None)
    for index, item in enumerate(payable or ()):
        for member in ("amount", "distinct_good_fair_value", "committed_purchases"):
            money = getattr(item, member, None)
            found = None if money is None else str(getattr(money, "currency", "")).strip()
            if found is not None and found != currency:
                path = f"consideration_payable[{index}].{member}"
                errors.append(
                    _error(
                        f"{path}.currency",
                        RULE_LINE_CURRENCY,
                        MEMBER_CURRENCY_MISMATCH.format(
                            member=path, found=found, expected=currency
                        ),
                    )
                )
    return errors


# 04 T-CON-06: the authored members whose column is nullable. ``PATCH`` clears one of them when
# the request SENDS it as null (04 §16.14 rev 1.188; item MOD-PATCH-CLEAR-1, supervisor ruling
# R-119 (e)): before, null meant "left out", so no client could remove a price-change amount, a
# judgement record or a reference from a draft.
CLEARABLE: Final = frozenset(
    {
        "reference",
        "price_change_amount",
        "noncash_consideration",
        "consideration_payable",
        "scope_605_35",
        "rationale",
        "judgement_record_id",
    }
)


def _authored_values(body: ModificationCreateIn | ModificationUpdateIn) -> dict[str, Any]:
    """The T-CON-06 members a request sets, JSON-safe. A member that is None is left out — the
    stored value stays — except a ``CLEARABLE`` member that a ``PATCH`` sends as null, which is
    set to null. Null for a member that cannot be null leaves the stored value, as before."""
    values: dict[str, Any] = {}
    sent = body.model_fields_set if isinstance(body, ModificationUpdateIn) else frozenset()
    for name in (
        "effective_date",
        "kind",
        "reference",
        "lines",
        "questionnaire",
        "price_change_amount",
        "noncash_consideration",
        "consideration_payable",
        "scope_605_35",
        "chosen_treatments",
        "ssp_basis",
        "rationale",
        "judgement_record_id",
    ):
        value = getattr(body, name)
        if value is None:
            if name in CLEARABLE and name in sent:
                values[name] = None
            continue
        if name in ("kind",):
            values[name] = _text(value)
        elif name in ("lines", "noncash_consideration", "consideration_payable"):
            values[name] = _json(value)
        elif name in ("chosen_treatments",):
            values[name] = {str(key): _text(item) for key, item in sorted(value.items())}
        elif name in ("ssp_basis",):
            values[name] = {str(key): _json(item) for key, item in sorted(value.items())}
        elif name in ("questionnaire",):
            values[name] = _json(value)
        elif name in ("price_change_amount",):
            values[name] = Decimal(str(value))
        else:
            values[name] = value
    return values


# --- commands ------------------------------------------------------------------------------------


def create_modification(
    uow: UnitOfWork, *, contract_id: UUID, body: ModificationCreateIn
) -> ModificationOut:
    """``POST /contracts/{id}/modifications``: a DRAFT T-CON-06 row of an ACTIVE contract
    (SM-03)."""
    session = uow.session
    _, current = lock_group_then_contract(session, contract_id)
    _require_prepare(uow, current)
    status = _text(current["status"])
    if status != ContractStatus.ACTIVE.value:
        raise _invalid(NOT_ACTIVE.format(external_id=current["external_id"], status=status))
    errors = _line_errors(
        session,
        current,
        body.lines,
        at=repo.product_reference_date(session, _uuid(current["combination_group_id"])),
    )
    errors += questionnaire_value_errors(body.questionnaire)
    errors += _member_currency_errors(body, str(current["transaction_currency"]).strip())
    repeated = _reference_error(session, contract_id, body.reference, except_id=None)
    if repeated is not None:
        errors.append(repeated)
    if errors:
        raise _failed(*errors)
    principal = uow.principal
    modification_id = new_id()
    values = _authored_values(body)
    number = numbering.next_number(uow, SERIES)
    session.execute(
        insert(modification).values(
            tenant_id=principal.tenant_id,
            id=modification_id,
            modification_no=number,
            contract_id=contract_id,
            contracting_entity_id=_uuid(current["contracting_entity_id"]),
            status=DRAFT,
            currency=str(current["transaction_currency"]).strip(),
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **values,
            **_stamps(uow),
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT,
        object_id=modification_id,
        object_version="1",
        after={
            "modification_no": number,
            "contract_id": str(contract_id),
            "status": DRAFT,
            **{key: _json(item) for key, item in values.items()},
        },
        comment=body.rationale,
        contract_id=contract_id,
    )
    return get_modification(session, modification_id)


def update_modification(
    uow: UnitOfWork, *, modification_id: UUID, body: ModificationUpdateIn
) -> ModificationOut:
    """``PATCH /modifications/{id}``: edit a DRAFT; an edit of a SUBMITTED row returns it to DRAFT
    and voids its pending request STALE_SUBJECT (SM-03 "Submit → Draft: edit"; CTL-007). Every edit
    invalidates the classification and the stored preview: both are redone before submission.

    An edit of a REJECTED row returns it to DRAFT as well (SM-03 REJECTED → DRAFT, "Revise"; item
    MOD-REJECTED-REVISE-1, the supervisor's ruling of 2026-10-01; 04 §16.14 rev 1.236). Measured
    before: a rejected modification was a dead end — it was not edited, not discarded (only a
    draft is) and its reference stayed taken, so the change order could not be entered again
    either. The rejected request was decided and stays closed: the next submission makes a new
    one, and ``approval_request_id`` names the old one until then. The estimate versions
    created inside the modification stay linked; those that were approved for the first
    attempt took effect by their own events and stay in effect whatever becomes of the
    modification. A revised draft that is given up is discarded, which frees its reference.
    The rows of one subject move together, as they were submitted and rejected together (the
    pair of a regroup after posting, D-98 140 Q-4): each REJECTED row returns to DRAFT."""
    session = uow.session
    row, current, pair = _locked_subject(uow, modification_id)
    status = _text(row["status"])
    if status not in (DRAFT, SUBMITTED, REJECTED):
        raise _invalid(NOT_EDITABLE)
    values = _authored_values(body)
    errors: list[ProblemError] = []
    if body.lines is not None:
        errors += _line_errors(
            session,
            current,
            body.lines,
            at=repo.product_reference_date(session, _uuid(current["combination_group_id"])),
        )
    errors += questionnaire_value_errors(body.questionnaire)
    errors += _member_currency_errors(body, str(current["transaction_currency"]).strip())
    if body.reference is not None:
        repeated = _reference_error(
            session, _uuid(current["id"]), body.reference, except_id=modification_id
        )
        if repeated is not None:
            errors.append(repeated)
    if errors:
        raise _failed(*errors)
    request_id = None if row["approval_request_id"] is None else _uuid(row["approval_request_id"])
    if status in (SUBMITTED, REJECTED):
        transitions.apply(
            session,
            OBJECT,
            modification_id,
            to_status=DRAFT,
            expected_status=status,
            set_values=_bump(uow),
        )
    if status == REJECTED:
        _revise_others(uow, modification_id, pair)
    reset: dict[str, Any] = {
        "proposed_treatments": {},
        "treatment_summary": None,
        "classification": None,
        "impact_preview_file_id": None,
        "impact_preview_sha256": None,
        "content_sha256": None,
    }
    updated = transitions.apply(
        session,
        OBJECT,
        modification_id,
        to_status=None,
        expected_status=DRAFT,
        set_values={**values, **reset, **_bump(uow)},
    )
    if request_id is not None:
        approvals.void_if_stale(
            uow, subject_type=ApprovalSubjectType.MODIFICATION, subject_id=modification_id
        )
        pending = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one_or_none()
        if pending is not None and _text(pending) == ApprovalRequestStatus.PENDING.value:
            approvals.withdraw(
                uow,
                approval_request_id=request_id,
                comment=SYSTEM_EDIT_COMMENT,
                through_subject=True,
            )
    uow.audit(
        action=UPDATE_ACTION,
        object_type=OBJECT,
        object_id=modification_id,
        object_version=str(updated["row_version"]),
        before={"status": status},
        after={"status": DRAFT, **{key: _json(item) for key, item in values.items()}},
        contract_id=_uuid(row["contract_id"]),
    )
    return get_modification(session, modification_id)


def _revise_others(
    uow: UnitOfWork, modification_id: UUID, pair: Sequence[Mapping[str, Any]]
) -> None:
    """The other REJECTED rows of the subject return to DRAFT with the revised one (item
    MOD-REJECTED-REVISE-1): half a pair can be neither submitted nor discarded. Each row writes
    its own audit event; its content is not touched. The caller holds the rows' locks
    (``_locked_subject``)."""
    for other in pair:
        other_id = _uuid(other["id"])
        if other_id == modification_id or _text(other["status"]) != REJECTED:
            continue
        updated = transitions.apply(
            uow.session,
            OBJECT,
            other_id,
            to_status=DRAFT,
            expected_status=REJECTED,
            set_values=_bump(uow),
        )
        uow.audit(
            action=UPDATE_ACTION,
            object_type=OBJECT,
            object_id=other_id,
            object_version=str(updated["row_version"]),
            before={"status": REJECTED},
            after={"status": DRAFT},
            contract_id=_uuid(other["contract_id"]),
        )


def _proposal(
    output: OutputBundle, row: Mapping[str, Any]
) -> tuple[dict[str, str], str | None, dict[str, str]]:
    """The engine's S06-R-01 proposal for the row (stage 13 ``_pending_proposals``): the treatments
    per obligation key, the E-23 summary and the proposal detail (CV-16)."""
    key = str(row["id"])
    proposals = [proposal for book in output.books for proposal in book.proposals]
    for proposal in proposals:
        if proposal.kind != PROPOSAL_KIND:
            continue
        if proposal.detail.get("modification_key") == key or proposal.subject_key.endswith(key):
            return (
                {str(k): str(v) for k, v in sorted(proposal.treatments.items())},
                proposal.summary,
                dict(proposal.detail),
            )
    raise Problem(
        "validation-failed",
        errors=[
            _error(
                None,
                RULE_CLASSIFIED,
                PROPOSAL_MISSING.format(modification_no=row["modification_no"]),
            )
        ],
    )


def _proposal_nodes(output: OutputBundle, book_code: str) -> dict[str, TraceNode]:
    """The ``mod_class@`` and ``mod_price_test@`` nodes of ``book_code``'s trace, by node id."""
    book = next((item for item in output.books if item.book_code == book_code), None)
    if book is None:
        return {}
    return {
        node.id: node
        for node in book.trace.nodes
        if node.measure.startswith((CLASS_MEASURE, PRICE_TEST_MEASURE))
    }


def _answered(row: Mapping[str, Any], key: str, question: str) -> bool:
    """The preparer answered ``question`` for obligation ``key`` (04 T-CON-06 ``questionnaire``:
    a per-obligation object) — the answer the engine reads as the preparer's (S06-R-04,
    S06-R-05)."""
    section = (row.get("questionnaire") or {}).get(key)
    return isinstance(section, Mapping) and isinstance(section.get(question), bool)


def questionnaire_value_errors(questionnaire: Mapping[str, Any] | None) -> list[ProblemError]:
    """Classification answers are explicit booleans; unrelated contract-level members remain."""
    errors: list[ProblemError] = []
    for key, section in (questionnaire or {}).items():
        if not isinstance(section, Mapping):
            continue
        for question in (QUESTION_ADDED, QUESTION_PRICED, QUESTION_REMAINING):
            value = section.get(question)
            if value is not None and not isinstance(value, bool):
                errors.append(
                    _error(f"questionnaire.{key}.{question}", RULE_TREATMENT, ANSWER_BOOLEAN)
                )
    return errors


def questionnaire_confirmation_errors(row: Mapping[str, Any]) -> list[ProblemError]:
    """BR-MOD-01: proposals are not the preparer's answers, including a proposed false.

    Use the retained classification, never derive accounting answers in the command. A
    pre-existing classification whose shape is no longer readable must be regenerated.
    """
    detail, proposed, _ = stored_classification(row.get("classification"))
    if not detail:
        return [_error("classification", RULE_CLASSIFIED, UNCLASSIFIED)]
    errors = questionnaire_value_errors(row.get("questionnaire"))
    for key, questions in sorted(proposed.items()):
        for question in sorted(questions):
            if not _answered(row, key, question):
                errors.append(
                    _error(f"questionnaire.{key}.{question}", RULE_TREATMENT, ANSWER_REQUIRED)
                )
    return errors


def _price_reason(params: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """The POL-101 outcome of one ``mod_price_test`` node as (reason, caption params). A test the
    engine passed on the preparer's own answer (S06-R-04 basis ``ATTESTED``) is ``attested``: the
    engine compared nothing, and the params still state the price and the entry's range or point
    where the entry resolves — facts the node carries whatever the answer. Nothing is computed
    here and no conclusion is drawn from the two figures (item MOD-PRICE-TEST-FACT-1; 04 §16.14
    rev 1.250). ``questionnaire_prefill`` never reads an attested test: it names a question only
    while the preparer has not answered it."""
    price, basis = Decimal(params["value"]), params.get("basis")
    shown = {"price": params["value"], "ssp_version_key": params.get("version_key", "")}
    if basis == "ATTESTED":
        if params.get("point"):
            shown.update(point=params["point"], point_tolerance_pct=params["point_tolerance_pct"])
        elif params.get("low") and params.get("high"):
            low, high = sorted((Decimal(params["low"]), Decimal(params["high"])))
            shown.update(low=str(low), high=str(high))
        return "attested", shown
    if basis == "RANGE":
        low, high = sorted((Decimal(params["low"]), Decimal(params["high"])))
        shown.update(low=str(low), high=str(high))
        if price < low:
            return "below_range", shown
        return ("above_range" if price > high else "within_range"), shown
    if basis == "POINT":
        shown.update(point=params["point"], point_tolerance_pct=params["point_tolerance_pct"])
        return ("at_point" if params.get("passed") == "true" else "off_point"), shown
    return "no_ssp", shown


def questionnaire_prefill(
    row: Mapping[str, Any],
    nodes: Mapping[str, TraceNode],
    *,
    external_id: str,
    classified: Iterable[str],
) -> dict[str, dict[str, dict[str, Any]]]:
    """BR-MOD-01: the questionnaire answers the system can compute for the DRAFT, as 04 §16.14
    ``prefill_reasons`` — obligation key → question → ``{value, reason_key, params}`` — read
    from the engine's proposal nodes of the row at its CV-50 position (``nodes``: the primary
    book's trace by node id; ``classified``: the obligation keys the proposal classified).

    An added line: ``added_goods_distinct`` from its S06-R-05 class reason (the template's
    distinctness; a line without a class of its own is not prefilled) and ``priced_at_ssp``
    from its POL-101 price test (the modification-date SSP range or point). An
    existing obligation: ``remaining_goods_distinct_from_transferred`` true for class D, false
    for class N. A question the preparer answered is NOT prefilled: the engine read that answer
    (reason ``QUESTIONNAIRE``, basis ``ATTESTED``), and a prefill is a proposal the preparer
    confirms, never a stored answer (the engine would read it back as the preparer's). That
    holds for the price test as for the class questions (item MOD-PREFILL-STORED-ANSWER-1; 04
    §16.14 rev 1.235): what this member names, a client takes for a proposal still to confirm —
    named beside a stored answer, the answer was left out of the client's next save and lost.
    Pure."""
    position = f"{contract_subject_key(external_id)}/{encode_key(str(row['id']))}"

    def node(measure: str, key: str) -> TraceNode | None:
        return nodes.get(f"{measure}{position}:{obligation_subject_key(external_id, key)}:-")

    def entry(question: str, value: bool, reason: str, params: Mapping[str, str]) -> dict[str, Any]:
        return {
            "value": value,
            "reason_key": PREFILL_KEY.format(question=question, reason=reason),
            "params": dict(params),
        }

    found: dict[str, dict[str, dict[str, Any]]] = {}
    added = [str(line["obligation_key"]) for line in _added_lines(row)]
    for key in added:
        answers: dict[str, dict[str, Any]] = {}
        class_node = node(CLASS_MEASURE, key)
        known = (
            None if class_node is None else _ADDED_REASONS.get(str(class_node.params.get("reason")))
        )
        if known is not None and not _answered(row, key, QUESTION_ADDED):
            answers[QUESTION_ADDED] = entry(QUESTION_ADDED, known[0], known[1], {})
        price_node = node(PRICE_TEST_MEASURE, key)
        if price_node is not None and not _answered(row, key, QUESTION_PRICED):
            literal, shown = _price_reason(price_node.params)
            answers[QUESTION_PRICED] = entry(
                QUESTION_PRICED, price_node.params.get("passed") == "true", literal, shown
            )
        if answers:
            found[key] = answers
    for key in sorted(set(classified) - set(added)):
        class_node = node(CLASS_MEASURE, key)
        if class_node is None or _answered(row, key, QUESTION_REMAINING):
            continue
        remaining = _REMAINING_REASONS.get(str(class_node.params.get("reason")))
        if remaining is None:
            continue
        found[key] = {
            QUESTION_REMAINING: entry(
                QUESTION_REMAINING,
                remaining[0],
                remaining[1],
                {
                    "progress": str(class_node.params.get("value", "")),
                    "progress_measure": str(class_node.params.get("progress_measure", "")),
                },
            )
        }
    return dict(sorted(found.items()))


def price_tests(
    row: Mapping[str, Any], nodes: Mapping[str, TraceNode], *, external_id: str
) -> dict[str, dict[str, Any]]:
    """Item MOD-PRICE-TEST-FACT-1 (04 §16.14 rev 1.250; the supervisor's ruling of 2026-10-01):
    the engine's price test of each added line of the row, WHATEVER the preparer answered —
    obligation key → ``{value, reason_key, params}``, the shape of a ``prefill_reasons`` entry,
    read from the same ``mod_price_test@`` node the proposal reads. A fact of the classification
    and never a proposal: it is answered beside ``prefill_reasons``, not inside it, so a reader
    that confirms what is proposed does not meet it. With ``priced_at_ssp`` answered true the
    engine passes the test on that attestation: value true, reason ``attested``, and the params
    still state the price and the entry's range or point — an attestation beside a price outside
    the range is exactly the row a reviewer must be able to read. An added line the engine does
    not test — one it integrates into an existing obligation, one that is not distinct — has no
    entry, and neither has a bundle line, whose tests sit on its components' keys. Pure."""
    position = f"{contract_subject_key(external_id)}/{encode_key(str(row['id']))}"
    found: dict[str, dict[str, Any]] = {}
    for line in _added_lines(row):
        key = str(line["obligation_key"])
        node = nodes.get(
            f"{PRICE_TEST_MEASURE}{position}:{obligation_subject_key(external_id, key)}:-"
        )
        if node is None:
            continue
        literal, shown = _price_reason(node.params)
        found[key] = {
            "value": node.params.get("passed") == "true",
            "reason_key": PREFILL_KEY.format(question=QUESTION_PRICED, reason=literal),
            "params": dict(shown),
        }
    return dict(sorted(found.items()))


def _is_entry(value: Any) -> bool:
    return isinstance(value, Mapping) and set(value) == _ENTRY_MEMBERS


def stored_classification(
    value: Any,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    """What a row's T-CON-06 ``classification`` holds (04 rev 1.286; item
    MOD-CLASSIFICATION-KEYS-1): the engine's proposal detail, the per-obligation proposals —
    obligation key → question → ``{value, reason_key, params}`` — and the price tests —
    obligation key → ``{value, reason_key, params}`` — as ``classify`` wrote them under the
    three members. Anything else reads as NONE, three empty mappings (the supervisor's ruling of
    2026-10-02, by D-99 (3)): a row classified before the item holds the obligations' entries
    beside ``proposal`` and ``price_tests``, no revision can rewrite a tenant's rows (DG-MIG-13)
    and there is no reader of two shapes. The members are read by their shape and not by their
    names alone, so a flat row whose only obligation is keyed ``obligations`` is none too: its
    member holds one obligation's questions where the three-member row holds obligations. The
    row's own columns — the proposed and the chosen treatments, the summary, the SSP basis —
    are not read from here, and the next ``/classify`` writes the three members. Pure."""
    none: tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]] = ({}, {}, {})
    if not isinstance(value, Mapping) or set(value) != {
        PROPOSAL_KEY,
        OBLIGATIONS_KEY,
        PRICE_TESTS_KEY,
    }:
        return none
    detail, obligations, tests = value[PROPOSAL_KEY], value[OBLIGATIONS_KEY], value[PRICE_TESTS_KEY]
    if not (
        isinstance(detail, Mapping)
        and isinstance(obligations, Mapping)
        and isinstance(tests, Mapping)
        and all(
            isinstance(answers, Mapping) and all(_is_entry(entry) for entry in answers.values())
            for answers in obligations.values()
        )
        and all(_is_entry(entry) for entry in tests.values())
    ):
        return none
    return (
        dict(detail),
        {str(key): dict(answers) for key, answers in obligations.items()},
        dict(tests),
    )


def _prefilled(
    questionnaire: Mapping[str, Any] | None, reasons: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> dict[str, Any]:
    """The classify response's ``questionnaire``: the stored answers with every prefilled answer
    beside them (SCREENS §7.5 "returns ``questionnaire`` prefilled per obligation key"). Pure."""
    merged: dict[str, Any] = dict(questionnaire or {})
    for key, questions in reasons.items():
        section = merged.get(key)
        answers = dict(section) if isinstance(section, Mapping) else {}
        for question, item in questions.items():
            answers.setdefault(question, item["value"])
        merged[key] = answers
    return merged


def classify(
    uow: UnitOfWork, *, modification_id: UUID, engine: computation.Engine | None = None
) -> ModificationOut:
    """``POST /modifications/{id}/classify``: the engine's proposal for the DRAFT (S06-R-01,
    S06-R-04, S06-R-05), stored as ``proposed_treatments`` / ``treatment_summary``;
    ``chosen_treatments`` defaults to the proposal where the preparer chose nothing. The dry run
    carries the row as a pending T-CON-06 object and no event (DG-CMD-15), so it changes no
    accounting (CV-16)."""
    session = uow.session
    row, _, current = _locked(uow, modification_id)
    if _text(row["status"]) != DRAFT:
        raise _invalid(NOT_CLASSIFIABLE)
    try:
        _, output, _ = dry_run_summary(
            session,
            current,
            uow.now,
            (),
            pending_contract_id=_uuid(current["id"]),
            pending_modifications=(row,),
            engine=engine,
            summarise=False,  # D-98 140-A12 CLASSIFY-EMPTY-EVENTS-1: no event, no summary window
        )
    except bundles.NativeCurrencyMismatch as error:
        raise _failed(_error(error.member, RULE_LINE_CURRENCY, str(error))) from error
    except ValueError as error:  # MAIN DEFECT 3: only the S06-R-19 shape refusal, by origin
        refused = s06_r19_refusal(error, row)
        if refused is None:
            raise
        raise refused from error
    except EngineError as error:
        raise engine_problem(error) from error
    proposed, summary, detail = _proposal(output, row)
    chosen = {str(k): _text(v) for k, v in (row["chosen_treatments"] or {}).items()}
    for key, treatment in proposed.items():
        chosen.setdefault(key, treatment)
    # D-98 140 AMENDMENT 15 (CTR-17b): the classification defaults — the version the dry run
    # ACTUALLY selected per line of the row: an existing obligation's ``ssp_book_version_key`` in
    # the output, an added line's price-test selection in the proposal detail ``ssp_version[<key>]``
    # (CV-16) — written with ``is_override`` false; an authored override is kept as it is.
    line_keys = {
        str(line["obligation_key"]) for line in (row["lines"] or ()) if isinstance(line, Mapping)
    }
    selected: dict[str, str] = {
        key: version_key
        for key, version_key in selected_ssp_versions(
            output, external_id=str(current["external_id"]), book_code=queries.primary_book(session)
        ).items()
        if version_key and key in line_keys
    }
    for line in _added_lines(row):
        found = detail.get(f"ssp_version[{line['obligation_key']}]")
        if found:
            selected[str(line["obligation_key"])] = str(found)
    ids = _version_ids_by_key(session, selected.values())
    basis = classification_defaults(
        row["ssp_basis"], {key: ids[vk] for key, vk in selected.items() if vk in ids}
    )
    # BR-MOD-01 (04 §16.14; SCREENS §7.5): the answers the system can compute, from the engine's
    # proposal nodes of this row — returned for the preparer to confirm, never stored as answers.
    nodes = _proposal_nodes(output, queries.primary_book(session))
    reasons = questionnaire_prefill(
        row,
        nodes,
        external_id=str(current["external_id"]),
        classified=[
            name[len("class[") : -1]
            for name in detail
            if name.startswith("class[") and name.endswith("]")
        ],
    )
    # Item MOD-PREFILL-READ-1 (04 T-CON-06 ``classification``, §16.14 rev 1.210): what this
    # classification answers is kept on the row, so that a read answers it. Item
    # MOD-CLASSIFICATION-KEYS-1 (rev 1.286): under three members and no other — the engine's
    # proposal detail (CV-16; ``proposal_detail``), the per-obligation proposals
    # (``prefill_reasons``) and the engine's price tests (``price_tests``; item
    # MOD-PRICE-TEST-FACT-1, rev 1.250) — so that no obligation key meets a member's name.
    classification = {
        PROPOSAL_KEY: detail,
        OBLIGATIONS_KEY: reasons,
        PRICE_TESTS_KEY: price_tests(row, nodes, external_id=str(current["external_id"])),
    }
    updated = transitions.apply(
        session,
        OBJECT,
        modification_id,
        to_status=None,
        expected_status=DRAFT,
        set_values={
            "proposed_treatments": proposed,
            "chosen_treatments": dict(sorted(chosen.items())),
            "treatment_summary": summary,
            "ssp_basis": basis,
            "classification": classification,
            "impact_preview_file_id": None,
            "impact_preview_sha256": None,
            **_bump(uow),
        },
    )
    uow.audit(
        action=CLASSIFY_ACTION,
        object_type=OBJECT,
        object_id=modification_id,
        object_version=str(updated["row_version"]),
        after={
            "proposed_treatments": proposed,
            "treatment_summary": summary,
            "ssp_basis": basis,
            "detail": detail,
            "prefill": reasons,
        },
        contract_id=_uuid(row["contract_id"]),
    )
    out = get_modification(session, modification_id)
    # ``prefill_reasons`` is the stored classification; this answer alone also shows the prefilled
    # answers beside the stored ones (SCREENS §7.5).
    return out.model_copy(update={"questionnaire": _prefilled(row["questionnaire"], reasons)})


def _amended_event(row: Mapping[str, Any], *, approval_request_id: UUID | None) -> EventIn:
    """The candidate (preview) or approved ``CONTRACT_AMENDED`` of the row (04 §16.3 payload): the
    row's members copied; the treatments are the chosen ones (S06-R-01)."""
    treatments = {
        str(key): ModificationTreatment(_text(value))
        for key, value in sorted((row["chosen_treatments"] or {}).items())
    }
    questionnaire = row["questionnaire"] or {}
    settlement = questionnaire.get("price_change_settlement")
    payload = ContractAmendedV1.model_validate(
        {
            "modification_id": str(row["id"]),
            "treatments": {key: value.value for key, value in treatments.items()},
            "lines": list(row["lines"] or ()),
            "ssp_basis": dict(row["ssp_basis"] or {}),
            "price_change_settlement": settlement,
            "noncash_consideration": row["noncash_consideration"],
            "consideration_payable": row["consideration_payable"],
            "scope_605_35": row["scope_605_35"],
        }
    )
    added = tuple(
        str(line["obligation_key"])
        for line in (row["lines"] or ())
        if isinstance(line, Mapping) and line.get("action") == "ADD"
    )
    return EventIn(
        event_type=ContractEventType.CONTRACT_AMENDED,
        effective_date=row["effective_date"],
        payload=payload,
        obligation_keys=added,
        modification_id=_uuid(row["id"]),
        approval_request_id=approval_request_id,
    )


def request_preview(uow: UnitOfWork, *, modification_id: UUID) -> JobOut:
    """``POST /modifications/{id}/preview``: defer the dry run of the DRAFT; 202 API-S-Job whose
    ``result.summary`` is API-S-ImpactSummary and whose run stores the preview on the row.

    A preview is asked by who could submit the modification (04 §16.10 rev 1.295 "Who may ask
    for a preview"; supervisor ruling R-103 (b) (5)): 403 by name for a caller who does not read
    every entity it is bound to (rev 1.319: ``contract.read`` for each; until then the entities
    of her roles), before the row's state is asked, and nothing is deferred."""
    session = uow.session
    row, _, current = _locked(uow, modification_id)
    approvals.require_preview_scope(
        uow,
        ApprovalSubjectType.MODIFICATION,
        modification_id,
        action=PREVIEW_REQUEST_ACTION,
        permission=CREATE_PERMISSION,
    )
    if _text(row["status"]) != DRAFT:
        raise _invalid(NOT_PREVIEWABLE)
    deferred = uow.defer(
        JobKind.CONTRACT_COMPUTE,
        {
            "mode": MODIFICATION_PREVIEW_MODE,
            "modification_id": str(modification_id),
            "row_version": int(row["row_version"]),
            "contract_id": str(current["id"]),
            "expected_stream_version": int(current["head_stream_version"]),
        },
        subject_type=OBJECT,
        subject_id=modification_id,
    )
    return _job_out(session, _uuid(deferred["id"]))


def _job_out(session: Session, job_id: UUID) -> JobOut:
    row = session.execute(select(*JOB_COLUMNS).where(job.c.id == job_id)).mappings().one()
    (item,) = job_outs(session, [dict(row)])
    return item


def _preview_document(
    summary: ImpactSummaryOut,
    *,
    bundle_sha256: str,
    engine_version: str,
    known_at: datetime,
    current: Mapping[str, Any],
    row: Mapping[str, Any],
    event: EventIn,
    basis: Mapping[str, Any],
    fx_basis: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The stored ``IMPACT_PREVIEW`` document (04 §16.14): the summary and its provenance — the
    engine and bundle identity, the candidate event (reproducible inputs), the target head, the
    retained basis (``basis_sha256`` over the §16.10 content without preview hashes) and the FX
    basis the submission converts with (D-98 140-A5 DOMAIN-R1 / ROUTING-FX-1) — beside the
    ``before`` / ``after`` members an approval request shows (04 §16.10; rev 1.92): ``/submit``
    hands this file and its hash to the request, so ONE hashed snapshot is what the preparer
    ran and what the approver decides on (REQ-PLT-015)."""
    data = summary.model_dump(mode="json")
    before, after = request_sides(data)
    return {
        "before": before,
        "after": after,
        "summary": data,
        "provenance": {
            "engine_version": engine_version,
            "input_sha256": bundle_sha256,
            "known_at": known_at.isoformat(),
            "contract_id": str(current["id"]),
            "head_stream_version": int(current["head_stream_version"]),
            "modification_id": str(row["id"]),
            "row_version": int(row["row_version"]),
            "candidate": {
                "event_type": event.event_type.value,
                "effective_date": event.effective_date.isoformat(),
                "payload": payload_json(event.payload),
                "obligation_keys": list(event.obligation_keys),
            },
            "basis_sha256": sha256_hex(basis),
            "basis": dict(basis),
            "fx_basis": dict(fx_basis),
            **dict(extra or {}),
        },
    }


def _separate_dry_run(
    uow: UnitOfWork, row: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[EventIn, InputBundle, OutputBundle, ImpactSummaryOut, dict[str, Any]]:
    """D-98 140-A6 SEPARATE-PREVIEW-1: book the 25-12 separate contract in its own combination
    group inside a savepoint, run the single-group dry run over it and read the summary of the NEW
    contract (transaction price before 0), then roll the savepoint back — nothing of the booking
    persists, the original stream is untouched (S06-R-03; CV-45 untouched: no ``CONTRACT_AMENDED``
    is built). The booking runs in a separate SYSTEM unit whose buffers are discarded; a numbering
    sequence may advance (the external id is the row's, deterministic).

    D-98 140-A14 (Codex 2029 §2) INPUT-1 preview admission: the ``ssp_basis`` override is verified
    at the record cutoff BEFORE the booking — an APPROVED id, the line's label, POL-070
    ``NAMED_VERSION`` (``_ssp_basis_errors``, the check ``/submit`` re-runs) — and the version the
    booking ACTUALLY selected is compared AFTER the dry run (A12 (1)); either failure FAILS the job
    by name and no preview is retained. An unknown or unapproved id therefore never yields a
    SUCCEEDED preview (``ssp_selection_mismatches`` alone is silent for a version it cannot
    name)."""
    session = uow.session
    body = _booking_of(session, row, current)
    candidate = EventIn(
        event_type=ContractEventType.CONTRACT_BOOKED,
        effective_date=body.inception_date,
        payload=body,
        obligation_keys=tuple(line.obligation_key for line in body.lines),
    )
    # A14: the instant the bundle will carry (bundles.build → record_cutoff, this transaction)
    known_at = bundles.record_cutoff(session, uow.now)
    basis_errors = _ssp_basis_errors(session, row, known_at)
    if basis_errors:
        raise _failed(*basis_errors)
    unit = _system_unit(uow, None)
    savepoint = session.begin_nested()
    try:
        booked = commands.book_contract(unit, body=body, origin="SYSTEM")
        new_contract = dict(booked.contract)
        bundle = bundles.build(session, _uuid(booked.combination_group["id"]), uow.now, (), DRY_RUN)
        output = computation.default_engine()(bundle)
        summary = impact_summary(
            session, new_contract, bundle, output, [candidate], computed_at=uow.now
        )
        selection = selected_ssp_versions(
            output, external_id=body.external_id, book_code=queries.primary_book(session)
        )
    except EngineError as error:
        savepoint.rollback()
        raise engine_problem(error) from error
    finally:
        if savepoint.is_active:
            savepoint.rollback()
    unit.drain_audit_events()  # discarded with the savepoint
    # D-98 140-A12 (1): the override must be the version the booking ACTUALLY selects (two approved
    # books may share a legacy label); a mismatch is refused here, at submit (retained selection)
    # and at apply (persisted selection) — by name, never silently honoured.
    mismatches = ssp_selection_mismatches(
        row, selection=selection, versions=_ssp_versions(session, row)
    )
    if mismatches:
        raise _failed(*mismatches)
    extra = {
        "separate_contract": {
            "external_id": body.external_id,
            "dry_run_booking": True,
            "own_combination_group": True,
            "ssp_selection": dict(selection),
        }
    }
    return candidate, bundle, output, summary, extra


def selected_ssp_versions(
    output: OutputBundle, *, external_id: str, book_code: str
) -> dict[str, str | None]:
    """The SSP book version key the engine ACTUALLY selected per obligation key of ``external_id``
    in ``book_code`` (S05 ``select_book`` / ``select_version``; the persisted
    ``obligation_version.ssp_book_version_id`` derives from the same ``ssp_book_version_key``
    column). Pure over the output bundle."""
    book = next((item for item in output.books if item.book_code == book_code), None)
    if book is None:
        return {}
    prefix = contract_subject_key(external_id) + "/"  # events._obligation_key's shape (CV-21)
    found: dict[str, str | None] = {}
    for item in book.obligation_versions:
        if not item.subject_key.startswith(prefix):
            continue
        key = item.subject_key[len(prefix) :]
        selected = item.columns.get("ssp_book_version_key")
        found[key] = None if selected is None else str(selected)
    return found


def ssp_selection_mismatches(
    row: Mapping[str, Any],
    *,
    selection: Mapping[str, str | None],
    versions: Mapping[str, tuple[str | None, str]],
) -> list[ProblemError]:
    """D-98 140-A12 (1): for a SEPARATE_CONTRACT choice, every ``ssp_basis`` override naming an
    ``ssp_book_version_id`` must equal the version the booking actually selected for that line
    (``selection``: obligation key → selected version key; ``versions``: id → (legacy label, version
    key)); an unresolved or different selection is refused by name. Pure."""
    if not separate_choice(row):
        return []
    errors: list[ProblemError] = []
    for key, basis in override_entries(row).items():
        named = versions.get(str(basis["ssp_book_version_id"]))
        if named is None:
            # ssp_basis_mismatches names the unknown version; it runs FIRST at preview (A14) and
            # at submit, so this silence never admits an unknown or unapproved id
            continue
        selected = selection.get(str(key))
        if selected is None:
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SSP_SELECTION_UNRESOLVED.format(key=key),
                )
            )
        elif selected != named[1]:
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SSP_SELECTION_MISMATCH.format(key=key, selected=selected, version=named[1]),
                )
            )
    return errors


def ssp_applied_mismatches(
    row: Mapping[str, Any], *, persisted: Mapping[str, UUID | None]
) -> list[ProblemError]:
    """A12 (1) at apply: the persisted ``ssp_book_version_id`` per obligation key of the booked
    contract must equal each override's id. Pure."""
    if not separate_choice(row):
        return []
    errors: list[ProblemError] = []
    for key, basis in override_entries(row).items():
        actual = persisted.get(str(key))
        if actual is None or str(actual) != str(basis["ssp_book_version_id"]):
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SSP_SELECTION_MISMATCH.format(
                        key=key,
                        selected="none" if actual is None else str(actual),
                        version=str(basis["ssp_book_version_id"]),
                    ),
                )
            )
    return errors


def _overrides(basis: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    """The AUTHORED OVERRIDE entries of an ``ssp_basis`` map — ``is_override`` true and naming an
    ``ssp_book_version_id`` — by key, sorted. A classification default (``is_override`` false; D-98
    140 AMENDMENT 15) is informational: the S06-R-03 checks and the booking pin never read it."""
    found: dict[str, Mapping[str, Any]] = {}
    for key, entry in sorted((basis or {}).items()):
        if (
            isinstance(entry, Mapping)
            and entry.get("is_override")
            and entry.get("ssp_book_version_id") is not None
        ):
            found[str(key)] = entry
    return found


def override_entries(row: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """``_overrides`` of the row's ``ssp_basis``."""
    return _overrides(row.get("ssp_basis"))


def _authored_true(basis: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    """EVERY authored ``is_override`` true entry of an ``ssp_basis`` map, by key, sorted — a draft
    override whose ``ssp_book_version_id`` is still null included (CTR17B-NULL-OVERRIDE-1, Codex
    production-20260922-0610: 04 T-CON-06 ``ssp_basis`` says a true entry is left untouched; the
    non-null filter of ``_overrides`` belongs to version selection and the pin checks only)."""
    return {
        str(key): entry
        for key, entry in sorted((basis or {}).items())
        if isinstance(entry, Mapping) and entry.get("is_override")
    }


def classification_defaults(
    current: Mapping[str, Any] | None, selected: Mapping[str, UUID]
) -> dict[str, dict[str, Any]]:
    """D-98 140 AMENDMENT 15 (CTR-17b): the ``ssp_basis`` map ``/classify`` writes — every authored
    override (``is_override`` true, a null-id draft included; CTR17B-NULL-OVERRIDE-1) kept as it
    is; for every other key the dry run selected a version for, the default
    ``{ssp_book_version_id, is_override: false, justification: null}``; a former default whose key
    resolved no version is dropped. Pure."""
    out: dict[str, dict[str, Any]] = {
        key: dict(entry) for key, entry in _authored_true(current).items()
    }
    for key, version_id in sorted(selected.items()):
        out.setdefault(
            str(key),
            {"ssp_book_version_id": str(version_id), "is_override": False, "justification": None},
        )
    return dict(sorted(out.items()))


def _version_ids_by_key(session: Session, keys: Iterable[str]) -> dict[str, UUID]:
    """``<book code>@v<no>`` → ``ssp_book_version.id`` for the keys the dry run selected (the
    bundle carries APPROVED versions only, so the key names one row)."""
    wanted = {str(key) for key in keys if "@v" in str(key)}
    if not wanted:
        return {}
    codes = {key.split("@v", 1)[0] for key in wanted}
    found: dict[str, UUID] = {}
    for version_id, code, number in session.execute(
        select(ssp_book_version.c.id, ssp_book.c.code, ssp_book_version.c.version_no)
        .select_from(
            ssp_book_version.join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(ssp_book.c.code.in_(sorted(codes)))
    ):
        key = f"{code}@v{int(number)}"
        if key in wanted:
            found[key] = UUID(str(version_id))
    return found


def _persisted_ssp_versions(session: Session, contract_id: UUID) -> dict[str, UUID | None]:
    """The latest primary-book obligation version's ``ssp_book_version_id`` per obligation key.

    "Latest" is the highest ``version_no``, which counts within one combination group (04
    T-CON-08): right only for a contract that has been in one group. The one caller reads the
    contract a SEPARATE-contract modification booked in the same unit of work — its own
    singleton group, one computation — so it cannot meet a former group (item
    MOD-SSP-PIN-CHAIN-1; ``subjects.obligation_ssp_pins`` reads along the chain of
    memberships). A second caller takes that reader's order."""
    book_code = queries.primary_book(session)
    found: dict[str, UUID | None] = {}
    for key, version_id in session.execute(
        select(obligation_version.c.obligation_key, obligation_version.c.ssp_book_version_id)
        .where(
            obligation_version.c.contract_id == contract_id,
            obligation_version.c.book_code == book_code,
        )
        .order_by(obligation_version.c.version_no.desc())
    ):
        found.setdefault(str(key), None if version_id is None else UUID(str(version_id)))
    return found


def _ssp_versions(session: Session, row: Mapping[str, Any]) -> dict[str, tuple[str | None, str]]:
    """The APPROVED versions the row's ``ssp_basis`` names: id → (legacy label, version key)."""
    ids = sorted({str(basis["ssp_book_version_id"]) for basis in override_entries(row).values()})
    versions: dict[str, tuple[str | None, str]] = {}
    if not ids:
        return versions
    for version_id, label, code, number in session.execute(
        select(
            ssp_book_version.c.id,
            ssp_book_version.c.legacy_version_label,
            ssp_book.c.code,
            ssp_book_version.c.version_no,
        )
        .select_from(
            ssp_book_version.join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(
            ssp_book_version.c.id.in_([UUID(item) for item in ids]),
            ssp_book_version.c.status == ConfigStatus.APPROVED.value,
        )
    ):
        versions[str(version_id)] = (
            None if label is None else str(label),
            f"{code}@v{int(number)}",
        )
    return versions


def strip_preview_hashes(content: Mapping[str, Any]) -> dict[str, Any]:
    """The §16.10 ``MODIFICATION`` content without each row's ``impact_preview_sha256``: the
    preview basis (04 §16.14 ``basis_sha256``) — the authored members, the judgement record's hash,
    the contract's group and head and every group member's head, for one row or the regroup pair.
    A later preview of the pair's other row therefore does not move it; an authored edit, a linked
    judgement's change or any member's appended event does (D-98 140-A5 DOMAIN-R1). Pure."""
    return {
        **content,
        "modifications": [
            {key: value for key, value in item.items() if key != "impact_preview_sha256"}
            for item in content.get("modifications", ())
        ],
    }


def preview_basis(session: Session, modification_id: UUID) -> dict[str, Any]:
    """The preview basis of the row (or its pair) as it stands now (``strip_preview_hashes`` over
    ``subjects.modification_content``); the caller holds the kernel locks when it compares."""
    return strip_preview_hashes(modification_content(session, modification_id))


def spot_basis(rates: Sequence[FxRateInput], *, base: str, quote: str, on: date) -> dict[str, Any]:
    """One retained conversion of the preview's FX basis (04 §16.14 ``fx_basis``): the S12-R-01
    ``spot`` rate — the latest on or before ``on`` among the pinned rows in force — from ``base``
    to ``quote``; rate 1 for equal currencies; an explicit absence (``rate`` None, ``missing``)
    when no row qualifies. No rate-selection rule is added: the engine's ``Rates.spot``. Pure."""
    if base == quote:
        return {"base": base, "quote": quote, "rate": "1", "rate_type": SPOT}
    try:
        view = Rates(rates, base, quote).spot(on)
    except RateMissing as missing:
        return {
            "base": base,
            "quote": quote,
            "rate": None,
            "rate_type": SPOT,
            "missing": missing.detail,
        }
    return {
        "base": base,
        "quote": quote,
        "rate": view.text,
        "rate_type": view.rate_type,
        "rate_key": view.rate_key,
        "version_key": view.version_key,
    }


def _fx_basis(
    session: Session,
    *,
    currency: str,
    functional_currency: str,
    effective_date: date,
    known_at: datetime,
) -> dict[str, Any]:
    """The FX basis retained with the preview: the pinned ``spot`` rates in force at ``known_at``
    (the bundle's rows, T-REF-11 / T-REF-12) from the transaction currency to the entity's
    functional currency and to the PRD §2.5 threshold currency, on the modification date."""
    rates = bundles.fx_rate_inputs(
        session, {currency, functional_currency, THRESHOLD_CURRENCY}, known_at
    )
    return {
        "transaction_currency": currency,
        "functional_currency": functional_currency,
        "threshold_currency": THRESHOLD_CURRENCY,
        "effective_date": effective_date.isoformat(),
        "to_functional": spot_basis(
            rates, base=currency, quote=functional_currency, on=effective_date
        ),
        "to_threshold": spot_basis(
            rates, base=currency, quote=THRESHOLD_CURRENCY, on=effective_date
        ),
    }


def boundary_measure(node: TraceNode) -> tuple[Decimal, Decimal, Decimal]:
    """(unrecognised allocation before, unrecognised allocation after, catch-up) of one
    obligation at a stage 06 boundary, read from its ``catch_up@<event key>:<ob>:-`` node (formula
    ``mod.catch_up.v1``; ENGINE_SPEC S06-R-17, CV-50): A − C on each side, with C the posted
    cumulative revenue at the boundary point — CV-63 ``cumulative_posted`` over the side's ``x_``,
    ``a_``, ``exact_`` and ``complete_`` members, the node formula's own reading — and
    C_after − C_before. An obligation the boundary adds has A = C = 0 before. Pure."""
    params = node.params
    minor = int(params["minor_unit"])

    def side(name: str) -> tuple[int, int]:
        allocated = int(params[f"a_{name}"])
        x_exact = Fraction(params[f"x_{name}"])
        if x_exact == 0:
            return allocated, 0
        complete = params.get(f"complete_{name}") == "true"
        ratio = Fraction(1) if complete else Fraction(params[f"exact_{name}"]) / x_exact
        return allocated, cumulative_posted(x_exact, allocated, ratio, minor)

    (a_before, c_before), (a_after, c_after) = side("before"), side("after")
    return (
        minor_to_decimal(a_before - c_before, minor),
        minor_to_decimal(a_after - c_after, minor),
        minor_to_decimal(c_after - c_before, minor),
    )


def boundary_summary(
    summary: ImpactSummaryOut,
    nodes: Mapping[str, TraceNode],
    *,
    external_id: str,
    event_key: str,
    treatments: Mapping[str, str],
) -> ImpactSummaryOut:
    """The preview of ONE candidate boundary (the row's ``CONTRACT_AMENDED``) measured AT the
    boundary (PRD WLD-X-05 / WLD-X-06, J-05.3; SCREENS §7.7): for every obligation the candidate
    gives a segment, ``remaining_allocation_before`` is A_p − R_p and
    ``remaining_allocation_after`` what stays unrecognised of its new allocation, both before the
    boundary date's own revenue; ``rpo_before`` / ``rpo_after`` are the RPO immediately before and
    after the boundary at ``rpo_date`` (T-CON-08 ``rpo_amount`` with those obligations at their
    boundary amounts); ``catch_up_by_obligation`` names the chosen treatment and the boundary's
    catch-up. The dry-run version's state is dated the END of the boundary date and the stored
    version's an earlier date, so their difference would count ordinary revenue as a change of
    allocation and of RPO. An obligation without a boundary node keeps the version-state figures.
    ``nodes`` are the primary book's trace nodes by id. Pure."""
    found: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    for item in summary.catch_up_by_obligation:
        key = item.obligation_key
        node = nodes.get(
            f"{CATCH_UP_MEASURE}{event_key}:{obligation_subject_key(external_id, key)}:-"
        )
        if node is not None:
            found[key] = boundary_measure(node)
    currency = summary.catch_up_total.currency

    def money(value: Decimal) -> Any:
        return money_out(value, currency, ISO_4217)

    catch_up = [
        ImpactCatchUpOut(
            obligation_key=item.obligation_key,
            treatment=treatments.get(item.obligation_key),
            amount=money(found[item.obligation_key][2])
            if item.obligation_key in found
            else item.amount,
        )
        for item in summary.catch_up_by_obligation
    ]
    update: dict[str, Any] = {
        "catch_up_by_obligation": catch_up,
        "catch_up_total": money(
            sum((Decimal(item.amount.amount) for item in catch_up), Decimal(0))
        ),
    }
    if found:
        state_after = {
            item.obligation_key: Decimal(item.amount.amount)
            for item in summary.remaining_allocation_after
        }
        # the boundary date's own revenue of the re-measured obligations, added back
        rpo_after = Decimal(summary.rpo_after.amount) + sum(
            (after - state_after.get(key, after) for key, (_, after, _) in found.items()),
            Decimal(0),
        )
        rpo_before = rpo_after - sum(
            (after - before for before, after, _ in found.values()), Decimal(0)
        )
        update.update(
            remaining_allocation_before=[
                ImpactObligationAmountOut(
                    obligation_key=item.obligation_key,
                    amount=money(found[item.obligation_key][0]),
                )
                if item.obligation_key in found
                else item
                for item in summary.remaining_allocation_before
            ],
            remaining_allocation_after=[
                ImpactObligationAmountOut(
                    obligation_key=item.obligation_key,
                    amount=money(found[item.obligation_key][1]),
                )
                if item.obligation_key in found
                else item
                for item in summary.remaining_allocation_after
            ],
            rpo_before=money(rpo_before),
            rpo_after=money(rpo_after),
        )
    return summary.model_copy(update=update)


def _candidate_nodes(
    session: Session, bundle: InputBundle, output: OutputBundle, current: Mapping[str, Any]
) -> tuple[str, dict[str, TraceNode]]:
    """The candidate boundary's event key — the one pending event, appended at head + 1 of the
    row's contract (``bundles.build``) — and its ``catch_up@`` nodes in the primary book's trace,
    by node id."""
    external_id, head = str(current["external_id"]), int(current["head_stream_version"])
    event_key = next(
        (
            event.event_key
            for event in bundle.events
            if event.contract_key == external_id and event.stream_version == head + 1
        ),
        None,
    )
    book_code = queries.primary_book(session)
    book = next((item for item in output.books if item.book_code == book_code), None)
    if event_key is None or book is None:
        return "", {}
    measure = f"{CATCH_UP_MEASURE}{event_key}"
    return event_key, {node.id: node for node in book.trace.nodes if node.measure == measure}


def run_preview(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``CONTRACT_COMPUTE`` in mode ``MODIFICATION_PREVIEW``: the DG-CMD-15 dry run with the
    candidate ``CONTRACT_AMENDED`` pending (S06-R-02); the summary and its provenance are stored as
    an ``IMPACT_PREVIEW`` file and hashed into the row (REQ-PLT-015). A row edited since the request
    (``row_version``) is not previewed."""
    modification_id = UUID(str(params["modification_id"]))
    with ctx.unit_of_work() as uow:
        session = uow.session
        # D-98 140-A8 DOMAIN-R1 capture: the governed lock order (group → contract → row,
        # DG-KRN-DB-08) BEFORE the bundle is built, so every member append serialises behind this
        # preview and the basis captured after the compute is the exact consumed state.
        peek = _row(session, modification_id)
        _, current = lock_group_then_contract(session, _uuid(peek["contract_id"]))
        row = _row(session, modification_id, lock=True)
        if int(row["row_version"]) != int(params["row_version"]) or _text(row["status"]) != DRAFT:
            raise Problem("precondition-failed", PREVIEW_STALE)
        if int(current["head_stream_version"]) != int(params["expected_stream_version"]):
            raise Problem("precondition-failed", PREVIEW_STALE)
        extra: dict[str, Any] = {}
        # D-98 140-A12 (2): the structural separate choice (a mix, a non-ADD line, an unsupported
        # member) is refused BEFORE dispatch — a mixed map never reaches the CONTRACT_AMENDED path
        # and no successful preview is retained for it.
        structural = separate_errors(row)
        if structural:
            raise _failed(*structural)
        try:
            if separate_choice(row):
                # D-98 140-A6 SEPARATE-PREVIEW-1: a genuine dry-run booking in the new contract's
                # own group; the original stream and the database are unchanged (savepoint rolled
                # back); the actual SSP selection is bound and verified (A12 (1)).
                event, bundle, output, summary, extra = _separate_dry_run(uow, row, current)
            else:
                # MOD-SSP-OVERRIDE-PREVIEW-1: an override the engine weighs from (D-18) names an
                # APPROVED version, by name, before the dry run is built.
                unknown = override_version_errors(row, versions=_ssp_versions(session, row))
                if unknown:
                    raise _failed(*unknown)
                event = _amended_event(row, approval_request_id=None)
                bundle, output, maybe = dry_run_summary(
                    session,
                    current,
                    uow.now,
                    [event],
                    pending_contract_id=_uuid(current["id"]),
                    pending_modifications=(row,),
                )
                assert maybe is not None  # a dry run with an applying event summarises
                event_key, nodes = _candidate_nodes(session, bundle, output, current)
                summary = boundary_summary(
                    maybe,
                    nodes,
                    external_id=str(current["external_id"]),
                    event_key=event_key,
                    treatments={
                        str(key): _text(value)
                        for key, value in (row["chosen_treatments"] or {}).items()
                    },
                )
        except bundles.NativeCurrencyMismatch as error:
            raise _failed(_error(error.member, RULE_LINE_CURRENCY, str(error))) from error
        except ValueError as error:  # MAIN DEFECT 3: only the S06-R-19 shape refusal, by origin
            refused = s06_r19_refusal(error, row)
            if refused is None:
                raise
            raise refused from error
        except EngineError as error:
            raise engine_problem(error) from error
        currency = str(row["currency"]).strip()
        document = _preview_document(
            summary,
            bundle_sha256=output.input_sha256,
            engine_version=output.engine_version,
            known_at=bundle.known_at,
            current=current,
            row=row,
            event=event,
            basis=preview_basis(session, modification_id),
            fx_basis=_fx_basis(
                session,
                currency=currency,
                functional_currency=_functional_currency(
                    session, _uuid(row["contracting_entity_id"])
                ),
                effective_date=row["effective_date"],
                known_at=bundle.known_at,
            ),
            extra=extra,
        )
        stored = store_file(
            uow,
            purpose=FilePurpose.IMPACT_PREVIEW,
            stream=io.BytesIO(canonical_bytes(document)),
            original_filename=f"{row['modification_no']}-impact-preview.json",
            media_type="application/json",
        )
        updated = transitions.apply(
            session,
            OBJECT,
            modification_id,
            to_status=None,
            expected_status=DRAFT,
            set_values={
                "impact_preview_file_id": _uuid(stored["id"]),
                "impact_preview_sha256": str(stored["sha256"]),
                **_bump(uow),
            },
        )
        uow.audit(
            action=PREVIEW_ACTION,
            object_type=OBJECT,
            object_id=modification_id,
            object_version=str(updated["row_version"]),
            after={
                "impact_preview_file_id": str(stored["id"]),
                "impact_preview_sha256": str(stored["sha256"]),
                "engine_version": output.engine_version,
                "input_sha256": output.input_sha256,
                "basis_sha256": document["provenance"]["basis_sha256"],
            },
            contract_id=_uuid(row["contract_id"]),
        )
        result = {
            "href": HREF.format(modification_id=modification_id),
            "summary": summary.model_dump(mode="json"),
            "impact_preview_sha256": str(stored["sha256"]),
        }
        # D-98 140-A8 PREVIEW-COMMIT-1: the successful preview — file row, pointer and hash, the
        # version bump and the audit — commits as one transaction before SUCCEEDED; a failure above
        # leaves the unit's rollback in place.
        uow.commit()
    return JobOutcome(state="SUCCEEDED", result=result)


def _stored_preview(uow: UnitOfWork, row: Mapping[str, Any]) -> dict[str, Any]:
    """The stored ``IMPACT_PREVIEW`` document of the row; 422 REQ-PLT-015 when absent, when the
    file's hash moved, when the target head moved, or when the retained basis (04 §16.14
    ``basis_sha256``) differs from the basis re-derived now under the caller's locks — a stale
    preview is refused, never relabelled with the current heads (D-98 140-A5 DOMAIN-R1).

    The basis is re-derived under the tenant's scope (04 §16.10 rev 1.319; ruling R-64 (1)): it
    names every member of the group with its head, the job that retained it read them as SYSTEM,
    and the submission runs under the scope of ``modification.create`` — which need not hold
    every contracting entity of the group, though its preparer reads them all (the kernel's
    question, asked first). Measured before: the submission of a Revenue Accountant of one
    contracting entity who is a Viewer of the other answered "The stored preview is not of this
    modification as it stands" for a preview that was not stale."""
    if row["impact_preview_file_id"] is None or row["impact_preview_sha256"] is None:
        raise _failed(_error("impact_preview", RULE_PREVIEW, PREVIEW_REQUIRED))
    found, stream = open_file(
        uow.session, _uuid(row["impact_preview_file_id"]), files=uow.files, keyring=uow.keyring
    )
    if str(found["sha256"]) != str(row["impact_preview_sha256"]):
        raise _failed(_error("impact_preview", RULE_PREVIEW, PREVIEW_STALE))
    with stream:
        document: dict[str, Any] = json.loads(stream.read().decode("utf-8"))
    provenance = document.get("provenance") or {}
    if int(provenance.get("head_stream_version", -1)) != int(_head_of(uow.session, row)):
        raise _failed(_error("impact_preview", RULE_PREVIEW, PREVIEW_STALE))
    retained = provenance.get("basis_sha256")
    with system_entity_scope(uow.session):
        basis = sha256_hex(preview_basis(uow.session, _uuid(row["id"])))
    if retained is None or str(retained) != basis:
        raise _failed(_error("impact_preview", RULE_PREVIEW, PREVIEW_STALE))
    if not all(isinstance(document.get(side), Mapping) for side in ("before", "after")):
        raise _failed(_error("impact_preview", RULE_PREVIEW, PREVIEW_STALE))
    return document


def _head_of(session: Session, row: Mapping[str, Any]) -> int:
    return int(
        session.execute(
            select(contract.c.head_stream_version).where(contract.c.id == row["contract_id"])
        ).scalar_one()
    )


def _functional_currency(session: Session, entity_id: UUID) -> str:
    return str(
        session.execute(
            select(legal_entity.c.functional_currency).where(legal_entity.c.id == entity_id)
        ).scalar_one()
    ).strip()


def _retained_rate(fx_basis: Mapping[str, Any], key: str, *, base: str, quote: str) -> Decimal:
    """The retained ``spot`` rate of ``fx_basis[key]`` from ``base`` to ``quote``; 422 REQ-PLT-015
    ``PREVIEW_BASIS_MISSING`` when the preview retained no such rate or a different pair — no rate
    is read at submission (04 §16.14; D-98 140-A5 ROUTING-FX-1)."""
    entry = fx_basis.get(key) if isinstance(fx_basis, Mapping) else None
    entry = entry if isinstance(entry, Mapping) else {}
    rate = entry.get("rate")
    if rate is None or (entry.get("base"), entry.get("quote")) != (base, quote):
        raise _failed(
            _error(
                "impact_preview",
                RULE_PREVIEW,
                PREVIEW_BASIS_MISSING.format(
                    rate_type=SPOT,
                    base=base,
                    quote=quote,
                    date=str(fx_basis.get("effective_date") or "the modification date"),
                ),
            )
        )
    return Decimal(str(rate))


def _converted(amount: Decimal, rate: Decimal, currency: str) -> Decimal:
    """``amount × rate`` rounded half up at ``currency``'s minor unit (S12-R-02's rounding)."""
    unit = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    return (amount * rate).quantize(unit, rounding=ROUND_HALF_UP)


def routing_facts(
    summary: Mapping[str, Any],
    *,
    currency: str,
    functional_currency: str,
    fx_basis: Mapping[str, Any],
) -> tuple[tuple[Decimal, str], frozenset[str], str]:
    """D-98 140 Q-5 as amended by 140-A5 ROUTING-FX-1: the PRD §2.5 second-step flags and
    ``amount_functional`` from a stored API-S-ImpactSummary and the preview's retained FX basis.
    ``amount_functional`` = |TP after − TP before| × the retained transaction→functional ``spot``
    rate (1 when equal), in the functional currency; the flags compare |catch_up_total| ≥ USD
    50,000.00 (``CATCH_UP_GE_50K``) and |ΔTP| ≥ USD 250,000.00 (``TP_CHANGE_GE_250K``) in the
    threshold currency at the retained transaction→USD rate — USD stays distinct from a non-USD
    functional currency. A summary in another currency than the row, or a retained absence, is
    refused by name (422 REQ-PLT-015). Returns (amount, flags, basis name). Pure: CPU-testable."""
    for member in ("transaction_price_before", "transaction_price_after", "catch_up_total"):
        found = str(summary[member]["currency"]).strip()
        if found != currency:
            raise _failed(
                _error(
                    "impact_preview",
                    RULE_PREVIEW,
                    PREVIEW_CURRENCY_MISMATCH.format(found=found, expected=currency),
                )
            )
    before = Decimal(str(summary["transaction_price_before"]["amount"]))
    after = Decimal(str(summary["transaction_price_after"]["amount"]))
    catch_up = abs(Decimal(str(summary["catch_up_total"]["amount"])))
    change = abs(after - before)
    to_functional = _retained_rate(
        fx_basis, "to_functional", base=currency, quote=functional_currency
    )
    to_threshold = _retained_rate(fx_basis, "to_threshold", base=currency, quote=THRESHOLD_CURRENCY)
    amount = _converted(change, to_functional, functional_currency)
    flags: set[str] = set()
    if _converted(catch_up, to_threshold, THRESHOLD_CURRENCY) >= CATCH_UP_THRESHOLD:
        flags.add(MODIFICATION_CATCH_UP_FLAG)
    if _converted(change, to_threshold, THRESHOLD_CURRENCY) >= TP_CHANGE_THRESHOLD:
        flags.add(MODIFICATION_TP_CHANGE_FLAG)
    basis = AMOUNT_BASIS_FUNCTIONAL if currency == functional_currency else AMOUNT_BASIS_RETAINED
    return (amount, functional_currency), frozenset(flags), basis


def override_applies(found: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    """REQ-MOD-002 as read by D-98 140-A5 JUDGEMENT-1: the linked judgement record reviews THIS
    row's departure — topic ``MODIFICATION_TREATMENT_OVERRIDE``, status ``REVIEWED``, subject
    ``('modification', this row)`` and this row's contract (04 T-CON-06 ``judgement_record_id``).
    Another modification's reviewed override, even on the same contract, does not apply. Pure."""
    return (
        _text(found["topic"]) == JudgementTopic.MODIFICATION_TREATMENT_OVERRIDE.value
        and _text(found["status"]) == JudgementStatus.REVIEWED.value
        and _text(found["subject_type"]) == OBJECT
        and str(found["subject_id"]) == str(row["id"])
        and found.get("contract_id") is not None
        and str(found["contract_id"]) == str(row["contract_id"])
    )


def _override_errors(session: Session, row: Mapping[str, Any]) -> list[ProblemError]:
    """REQ-MOD-002 / S06-R-01: every ``chosen_treatments`` departure from the proposal needs a
    REVIEWED judgement record of topic ``MODIFICATION_TREATMENT_OVERRIDE`` whose subject is this
    modification (``override_applies``)."""
    proposed = {str(k): _text(v) for k, v in (row["proposed_treatments"] or {}).items()}
    chosen = {str(k): _text(v) for k, v in (row["chosen_treatments"] or {}).items()}
    departures = sorted(key for key, value in chosen.items() if proposed.get(key) != value)
    if not departures:
        return []
    reviewed = False
    if row["judgement_record_id"] is not None:
        found = (
            session.execute(
                select(
                    judgement_record.c.topic,
                    judgement_record.c.status,
                    judgement_record.c.subject_type,
                    judgement_record.c.subject_id,
                    judgement_record.c.contract_id,
                ).where(judgement_record.c.id == row["judgement_record_id"])
            )
            .mappings()
            .one_or_none()
        )
        reviewed = found is not None and override_applies(dict(found), row)
    if reviewed:
        return []
    return [
        _error(f"chosen_treatments.{key}", RULE_TREATMENT, TREATMENT_OVERRIDE.format(key=key))
        for key in departures
    ]


def request_sides(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ``before`` and ``after`` members of an approval request's impact preview (04 §16.10:
    revenue by period, balances, journal lines, with the price, RPO, allocation and catch-up
    beside them) from an API-S-ImpactSummary document. Pure."""
    revenue = data["revenue_by_period"]
    before = {
        "transaction_price": data["transaction_price_before"],
        "rpo": data["rpo_before"],
        "revenue_by_period": [
            {"period_key": item["period_key"], "amount": item["before"]} for item in revenue
        ],
        "balances": data["balances_before"],
        "remaining_allocation": data["remaining_allocation_before"],
    }
    after = {
        "transaction_price": data["transaction_price_after"],
        "rpo": data["rpo_after"],
        "revenue_by_period": [
            {"period_key": item["period_key"], "amount": item["after"]} for item in revenue
        ],
        "balances": data["balances_after"],
        "remaining_allocation": data["remaining_allocation_after"],
        "catch_up_total": data["catch_up_total"],
        "catch_up_by_obligation": data["catch_up_by_obligation"],
        "journal_lines": data["journal_lines"],
    }
    return before, after


def _impact_preview(row: Mapping[str, Any], document: Mapping[str, Any]) -> approvals.ImpactPreview:
    """The row's retained preview as the request's impact preview (REQ-PLT-015; 04 §16.14 rev
    1.92): the SAME ``IMPACT_PREVIEW`` file and hash — never a second document derived from it."""
    return approvals.ImpactPreview(
        before=document["before"],
        after=document["after"],
        retained_file_id=_uuid(row["impact_preview_file_id"]),
        retained_sha256=str(row["impact_preview_sha256"]),
    )


def _locked_subject(
    uow: UnitOfWork, modification_id: UUID
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """D-98 140-A6 REGROUP-R5: discover the subject's rows (one, or the regroup pair), lock the full
    sorted set of their groups and contracts in the kernel order (``lock_groups_then_contracts``;
    DG-KRN-DB-08), then the rows ``FOR UPDATE``, then re-read them under the locks — the caller
    revalidates statuses on the re-read rows. Returns (the subject row, its contract, every row)."""
    session = uow.session
    contract_ids = sorted(
        {_uuid(r["contract_id"]) for r in modification_rows(session, modification_id)}
    )
    if len(contract_ids) == 1:
        _, current = lock_group_then_contract(session, contract_ids[0])
        currents = {contract_ids[0]: current}
    else:
        currents = lock_groups_then_contracts(session, contract_ids)
    for locked_contract in currents.values():
        _require_prepare(uow, locked_contract)
    pair = [
        _row(session, _uuid(item["id"]), lock=True)
        for item in modification_rows(session, modification_id)
    ]
    row = next(item for item in pair if _uuid(item["id"]) == modification_id)
    return row, currents[_uuid(row["contract_id"])], pair


def submit(
    uow: UnitOfWork, *, modification_id: UUID, body: ModificationSubmitIn
) -> ModificationOut:
    """``POST /modifications/{id}/submit`` (SM-03 DRAFT → SUBMITTED): classified, previewed with a
    preview whose retained basis still holds (``_stored_preview``; D-98 140-A5 DOMAIN-R1), the
    departures reviewed by this row's own judgement (JUDGEMENT-1); the §16.10 content hashed; the
    ``MODIFICATION`` request routed with the facts of the stored preview converted at its retained
    FX basis (Q-5; ROUTING-FX-1) and that preview as its impact preview."""
    session = uow.session
    # D-98 140 Q-4 / 140-A6 R5: a regroup-after-posting pair is ONE spanning request — both groups
    # and contracts are locked in the kernel order, then the rows; every row of the pair must be
    # classified and previewed, and every row moves to SUBMITTED with the request.
    row, current, pair = _locked_subject(uow, modification_id)
    # 04 §16.10 rev 1.295 ("A modification's submission asks first"; R-64 (1), (6)): the
    # preparer's question comes before every finding below. They read the group — the basis of
    # the stored preview holds every member's head — and under the scope of a preparer who
    # cannot read a member they answered a stale preview where none was stale.
    approvals.require_preparer_scope(uow, ApprovalSubjectType.MODIFICATION, modification_id)
    if any(_text(item["status"]) != DRAFT for item in pair):
        raise _invalid(NOT_SUBMITTABLE)
    # Item MOD-LINKED-ESTIMATES-1 (04 §16.10, §16.14 rev 1.210; PRD ERR-87): the estimate
    # versions created inside the modification are approved FIRST. It is the only order the
    # kernel admits — a version's approval appends ESTIMATE_CHANGED, which moves the head this
    # request's content pins, so a request made before it would go stale — and it is asked before
    # the preview: a preview taken before the versions are approved is stale with the first of
    # those approvals.
    unapproved = _linked_errors(
        session, [_uuid(item["id"]) for item in pair], LINKED_UNAPPROVED, LINKED_NOT_APPROVED
    )
    if unapproved:
        raise Problem("invalid-transition", errors=unapproved)
    for item in pair:
        if not item["proposed_treatments"]:
            raise _failed(_error("proposed_treatments", RULE_CLASSIFIED, UNCLASSIFIED))
    # D-98 140-A9 CHOICE-1 order: the structural choice (a mix, a non-ADD line, an unsupported
    # member) is refused BEFORE the preview prerequisite, so a wrong shape answers S06-R-03 and not
    # a missing-preview REQ-PLT-015; a valid candidate still needs its preview.
    structural = [error for item in pair for error in separate_errors(item)]
    if structural:
        raise _failed(*structural)
    documents = {_uuid(item["id"]): _stored_preview(uow, item) for item in pair}
    errors = [error for item in pair for error in _override_errors(session, item)]
    errors += [error for item in pair for error in questionnaire_confirmation_errors(item)]
    errors += [
        error
        for item in pair
        for error in required_attribute_errors(
            session,
            {
                str(line["product_code"])
                for line in item["lines"]
                if line.get("action") == "ADD" and line.get("product_code")
            },
            at=repo.product_reference_date(
                session,
                _uuid(
                    repo.get_contract(session, _uuid(item["contract_id"]))["combination_group_id"]
                ),
            ),
        )
    ]
    errors += [
        error
        for item in pair
        for error in _ssp_basis_errors(
            session, item, uow.now, document=documents[_uuid(item["id"])]
        )
    ]
    if errors:
        raise _failed(*errors)
    # Item MOD-LINKED-JUDGEMENTS-1 (04 §16.14 rev 1.242; PRD ERR-95): a judgement record whose
    # subject is this modification is reviewed, or discarded, FIRST — its request pins the
    # contract's head, which the applied modification moves. Asked behind the row's own
    # findings, so a departure whose record is not reviewed still answers REQ-MOD-002 (ERR-54).
    unreviewed = _record_errors(session, [_uuid(item["id"]) for item in pair], RECORD_NOT_REVIEWED)
    if unreviewed:
        raise Problem("invalid-transition", errors=unreviewed)
    facts: dict[UUID, tuple[tuple[Decimal, str], frozenset[str], str]] = {}
    for item in pair:
        item_id = _uuid(item["id"])
        provenance = documents[item_id].get("provenance") or {}
        facts[item_id] = routing_facts(
            documents[item_id]["summary"],
            currency=str(item["currency"]).strip(),
            functional_currency=_functional_currency(session, _uuid(item["contracting_entity_id"])),
            fx_basis=provenance.get("fx_basis") or {},
        )
    # The request's amount is the subject row's (its functional currency); the flags are USD
    # facts and union over the pair (the second preview can only widen the routing).
    amount, flags, basis = facts[modification_id]
    for item_id, (_, other_flags, _) in facts.items():
        if item_id != modification_id:
            flags = flags | other_flags
    # The row's own digest is the content the kernel hashes for the request, read as the kernel
    # reads it: under the tenant's scope (04 §16.10 rev 1.319; R-64 (1)).
    with system_entity_scope(session):
        digest = sha256_hex(modification_content(session, modification_id))
    latest: dict[UUID, Mapping[str, Any]] = {}
    for item in pair:
        latest[_uuid(item["id"])] = transitions.apply(
            session,
            OBJECT,
            _uuid(item["id"]),
            to_status=SUBMITTED,
            expected_status=DRAFT,
            set_values={"content_sha256": digest, **_bump(uow)},
        )
    decision = approvals.route_submission(
        uow, ApprovalSubjectType.MODIFICATION, modification_id, amount=amount, flags=flags
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.MODIFICATION,
        subject_id=modification_id,
        summary=f"Approve modification {row['modification_no']} of {current['external_id']}",
        impact_preview=_impact_preview(row, documents[modification_id]),
        comment=body.comment,
        routing_decision=decision,
    )
    request_id = _uuid(request["id"])
    for item in pair:
        stored = _row(session, _uuid(item["id"]))
        if _text(stored["status"]) == SUBMITTED:
            latest[_uuid(item["id"])] = transitions.apply(
                session,
                OBJECT,
                _uuid(item["id"]),
                to_status=None,
                expected_status=SUBMITTED,
                set_values={"approval_request_id": request_id, **_bump(uow)},
            )
    uow.audit(
        action=SUBMIT_ACTION,
        object_type=OBJECT,
        object_id=modification_id,
        object_version=str(latest[modification_id]["row_version"]),
        before={"status": DRAFT},
        after={
            "status": SUBMITTED,
            "content_sha256": digest,
            "impact_preview_sha256": str(row["impact_preview_sha256"]),
            "approval_request_id": str(request_id),
            "flags": sorted(flags),
            "amount_functional": str(amount[0]),
            "amount_currency": amount[1],
            "amount_basis": basis,
        },
        approval_request_id=request_id,
        comment=body.comment,
        contract_id=_uuid(row["contract_id"]),
    )
    return get_modification(session, modification_id)


def withdraw(
    uow: UnitOfWork, *, modification_id: UUID, body: ModificationWithdrawIn
) -> ModificationOut:
    """``POST /modifications/{id}/withdraw``: the preparer withdraws the pending request;
    ``on_voided`` returns the row to DRAFT (SM-03)."""
    session = uow.session
    row, _, _ = _locked(uow, modification_id)
    if _text(row["status"]) != SUBMITTED or row["approval_request_id"] is None:
        raise _invalid(NOT_WITHDRAWABLE)
    approvals.withdraw(
        uow,
        approval_request_id=_uuid(row["approval_request_id"]),
        comment=body.comment,
        through_subject=True,
    )
    after = _row(session, modification_id)  # on_voided returned it to DRAFT and bumped the version
    uow.audit(
        action=WITHDRAW_ACTION,
        object_type=OBJECT,
        object_id=modification_id,
        object_version=str(after["row_version"]),
        before={"status": SUBMITTED},
        after={"status": _text(after["status"])},
        comment=body.comment,
        contract_id=_uuid(row["contract_id"]),
    )
    return get_modification(session, modification_id)


def discard(uow: UnitOfWork, *, modification_id: UUID) -> ModificationOut:
    """``POST /modifications/{id}/discard`` (PRD SM-03 DRAFT → VOIDED, "Discard draft"; item
    MOD-DISCARD-1, supervisor ruling R-118 (e)): a draft that will not be submitted leaves the
    preparer's work. ANY draft without a pending request is discarded — one that was never
    submitted and one that was withdrawn, edited back, or rejected and revised: the request's
    history stays on the row (``approval_request_id``) and in the audit trail. The pair of a
    regroup after posting (one ``regroup_id``; D-98 140 Q-4) is discarded whole or not at all:
    half a pair can never be submitted.

    Refused, 409 ``invalid-transition`` under SM-03: a row that is not DRAFT or has a pending
    request; and by name (PRD ERR-82) while a review of one of the modification's own judgement
    records is pending, or (PRD ERR-83) while an estimate version created inside the
    modification is waiting for approval — no request is left to be decided for a voided
    modification, so the request's preparer withdraws it first (``POST /approvals/{id}/withdraw``).
    ``judgements.submit_judgement`` is the mirror: it requests no review for a record of a
    VOIDED modification. Both hold the contract's group and row locks, so neither passes the
    other.

    Nothing else is written: the retained preview stays, a judgement record stays as it is.
    The reference is free for the contract again — ``ux_modification__reference`` does not count
    a VOIDED row that was never applied (04 rev 1.210, revision 0114). Every holder
    of ``modification.create`` for the contracting entity may discard: a discard writes no
    content and keeps an absent creator's draft from standing in the way."""
    session = uow.session
    _, _, pair = _locked_subject(uow, modification_id)
    if any(_text(item["status"]) != DRAFT for item in pair):
        raise _invalid(NOT_DISCARDABLE)
    ids = [_uuid(item["id"]) for item in pair]
    pending = session.execute(
        select(approval_request.c.id)
        .where(
            approval_request.c.subject_type == ApprovalSubjectType.MODIFICATION.value,
            approval_request.c.subject_id.in_(ids),
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
        .limit(1)
    ).first()
    if pending is not None:
        raise _invalid(NOT_DISCARDABLE)
    waiting = (
        session.execute(
            select(judgement_record.c.judgement_no)
            .where(
                judgement_record.c.subject_type == OBJECT,
                judgement_record.c.subject_id.in_(ids),
                judgement_record.c.status == JudgementStatus.SUBMITTED.value,
            )
            .order_by(judgement_record.c.judgement_no)
        )
        .scalars()
        .all()
    )
    held = [
        _error(None, RULE_STATE, REVIEW_PENDING.format(judgement_no=number)) for number in waiting
    ]
    # Item MOD-LINKED-ESTIMATES-1 (PRD ERR-83): a linked estimate version that is waiting for
    # approval holds the discard the same way — its preparer withdraws it first.
    # ``estimates.submit_version`` is the mirror (PRD ERR-88), under the same locks. Linked
    # versions that are DRAFT, REJECTED or WITHDRAWN go with the modification as they are.
    held += _linked_errors(session, ids, frozenset({ConfigStatus.SUBMITTED.value}), LINKED_PENDING)
    if held:
        raise Problem("invalid-transition", errors=held)
    for item in pair:
        updated = transitions.apply(
            session,
            OBJECT,
            _uuid(item["id"]),
            to_status=VOIDED,
            expected_status=DRAFT,
            set_values=_bump(uow),
        )
        uow.audit(
            action=DISCARD_ACTION,
            object_type=OBJECT,
            object_id=_uuid(item["id"]),
            object_version=str(updated["row_version"]),
            before={"status": DRAFT},
            after={"status": VOIDED},
            contract_id=_uuid(item["contract_id"]),
        )
    return get_modification(session, modification_id)


# --- obligations the applied events create (stream CREATING_TYPES; L3-1-Q-16) -------------------


def _product_ids(session: Session, codes: Sequence[str]) -> dict[str, UUID]:
    wanted = sorted({code for code in codes if code})
    if not wanted:
        return {}
    found = {
        str(code): _uuid(product_id)
        for code, product_id in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(wanted))
        )
    }
    missing = [code for code in wanted if code not in found]
    if missing:
        raise _failed(
            *(_error("lines", RULE_PRODUCT, PRODUCT_UNKNOWN.format(code=code)) for code in missing)
        )
    return found


def _next_line_sequence(session: Session, contract_id: UUID) -> int:
    found = session.execute(
        select(func.coalesce(func.max(obligation.c.line_sequence), 0)).where(
            obligation.c.contract_id == contract_id
        )
    ).scalar_one()
    return int(found)


def _insert_created_obligations(
    uow: UnitOfWork,
    *,
    current: Mapping[str, Any],
    event: Mapping[str, Any],
    keys: Sequence[str],
    products: Mapping[str, UUID],
    product_codes: Mapping[str, str],
    regrouped_from: Mapping[str, UUID] | None = None,
) -> list[UUID]:
    """One ``obligation`` row per key the event created an id for
    (``obligation.created_by_event_id``; the stream minted the ids, the command inserts the rows —
    as the booking does)."""
    ids = dict(zip(keys, event["obligation_ids"], strict=True))
    known = {
        str(key)
        for key in uow.session.scalars(
            select(obligation.c.obligation_key).where(obligation.c.contract_id == current["id"])
        )
    }
    errors = required_attribute_errors(
        uow.session,
        {product_codes[key] for key in keys if key not in known},
        at=repo.product_reference_date(uow.session, _uuid(current["combination_group_id"])),
    )
    if errors:
        raise _failed(*errors)
    sequence = _next_line_sequence(uow.session, _uuid(current["id"]))
    principal = uow.principal
    rows: list[dict[str, Any]] = []
    for key in keys:
        if key in known:
            continue
        sequence += 1
        code = product_codes[key]
        rows.append(
            {
                "tenant_id": principal.tenant_id,
                "id": _uuid(ids[key]),
                "contract_id": _uuid(current["id"]),
                "obligation_key": key,
                "product_id": products[code],
                # LM-CL-70: <Contract Unique Name> <POB Unique ID> <SKU Name>.
                "legacy_record_key": f"{current['external_id']} {key} {code}",
                "created_by_event_id": _uuid(event["id"]),
                "parent_obligation_id": None,
                "regrouped_from_obligation_id": None
                if regrouped_from is None
                else regrouped_from.get(key),
                "line_sequence": sequence,
                "created_at": uow.now,
                "created_by": principal.id,
                "created_by_kind": principal.kind.value,
            }
        )
    if rows:
        uow.session.execute(insert(obligation), rows)
    return [_uuid(row["id"]) for row in rows]


def _added_lines(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        line
        for line in (row["lines"] or ())
        if isinstance(line, Mapping) and line.get("action") == ADD
    ]


def _source_obligations(session: Session, contract_id: UUID) -> dict[str, dict[str, Any]]:
    """The contract's obligations with their product codes, by obligation key."""
    rows = session.execute(
        select(obligation, product.c.code.label("product_code"))
        .select_from(obligation.join(product, product.c.id == obligation.c.product_id))
        .where(obligation.c.contract_id == contract_id)
    ).mappings()
    return {str(row["obligation_key"]): dict(row) for row in rows}


def _regrouped_event(
    row: Mapping[str, Any],
    counterpart: Mapping[str, Any],
    *,
    approval_request_id: UUID | None,
    lines: Sequence[Mapping[str, Any]] = (),
) -> EventIn:
    """The ``REGROUPED`` of a regroup row (04 §16.3; S06-R-27): ``OUT`` on the REMOVE row's
    contract, ``IN`` on the ADD row's; the pair shares ``regroup_id``. ``lines`` (an IN event
    before posting; D-98 140-A6 REGROUP-R1) are the moved obligations' booked lines, the evidence
    the target group's bundle reconstructs the move from without the source group."""
    direction = "OUT" if _text(row["kind"]) == ModificationKind.REMOVE_OBLIGATION.value else "IN"
    keys = tuple(
        str(line["obligation_key"]) for line in (row["lines"] or ()) if isinstance(line, Mapping)
    )
    payload = RegroupedV1.model_validate(
        {
            "regroup_id": _uuid(row["regroup_id"]),
            "direction": direction,
            "obligation_keys": keys,
            "counterpart_contract_id": _uuid(counterpart["contract_id"]),
            "modification_id": _uuid(row["id"]),
            "lines": [dict(line) for line in lines] if direction == "IN" else [],
        }
    )
    return EventIn(
        event_type=ContractEventType.REGROUPED,
        effective_date=row["effective_date"],
        payload=payload,
        obligation_keys=keys if direction == "IN" else (),
        modification_id=_uuid(row["id"]),
        approval_request_id=approval_request_id,
    )


def separate_choice(row: Mapping[str, Any]) -> bool:
    """D-98 140-A6 SEPARATE-CHOICE-1: the execution mode is read from the (approved)
    ``chosen_treatments`` — every line's chosen treatment is ``SEPARATE_CONTRACT`` — never from the
    proposal's ``treatment_summary``. Pure."""
    chosen = {str(k): _text(v) for k, v in (row["chosen_treatments"] or {}).items()}
    return bool(chosen) and all(value == SEPARATE for value in chosen.values())


def separate_errors(row: Mapping[str, Any]) -> list[ProblemError]:
    """D-98 140-A6 SEPARATE-CHOICE-1 / SEPARATE-INPUT-1, refused by name BEFORE approval (at
    ``/submit``): a mix of ``SEPARATE_CONTRACT`` with another treatment, a non-``ADD`` line under
    it, a ``price_change_amount`` or ``price_change_settlement`` (the booking has no such members),
    an ``ssp_basis`` entry naming an ``ssp_book_version_id`` without the line's
    ``ssp_version_label`` (the booking pins SSP by label), or an override without justification.
    ``noncash_consideration`` and ``consideration_payable`` map onto the booking and pass. Pure."""
    chosen = {str(k): _text(v) for k, v in (row["chosen_treatments"] or {}).items()}
    if SEPARATE not in chosen.values():
        return []
    errors: list[ProblemError] = []
    for key, value in sorted(chosen.items()):
        if value != SEPARATE:
            errors.append(
                _error(
                    f"chosen_treatments.{key}",
                    RULE_SEPARATE,
                    SEPARATE_MIXED.format(key=key, treatment=value),
                )
            )
    lines = [line for line in (row["lines"] or ()) if isinstance(line, Mapping)]
    for index, line in enumerate(lines):
        if line.get("action") != ADD:
            errors.append(
                _error(
                    f"lines[{index}].action",
                    RULE_SEPARATE,
                    SEPARATE_NEEDS_ADD.format(
                        key=line.get("obligation_key"), action=line.get("action")
                    ),
                )
            )
    if row.get("price_change_amount") is not None:
        errors.append(
            _error(
                "price_change_amount",
                RULE_SEPARATE,
                SEPARATE_UNSUPPORTED.format(member="price_change_amount"),
            )
        )
    if (row.get("questionnaire") or {}).get("price_change_settlement") is not None:
        errors.append(
            _error(
                "questionnaire.price_change_settlement",
                RULE_SEPARATE,
                SEPARATE_UNSUPPORTED.format(member="price_change_settlement"),
            )
        )
    labels = {str(line.get("obligation_key")): line.get("ssp_version_label") for line in lines}
    for key, basis in sorted((row.get("ssp_basis") or {}).items()):
        if not isinstance(basis, Mapping):
            continue
        if (
            basis.get("is_override")
            and basis.get("ssp_book_version_id") is not None
            and not labels.get(str(key))
        ):
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SEPARATE_UNSUPPORTED.format(
                        member=(
                            f"ssp_basis.{key}.ssp_book_version_id without the line's "
                            "ssp_version_label"
                        )
                    ),
                )
            )
        if basis.get("is_override") and not str(basis.get("justification") or "").strip():
            errors.append(
                _error(
                    f"ssp_basis.{key}.justification",
                    RULE_SEPARATE,
                    SEPARATE_UNSUPPORTED.format(
                        member=f"an ssp_basis.{key} override without justification"
                    ),
                )
            )
    return errors


def ssp_basis_mismatches(
    row: Mapping[str, Any], *, versions: Mapping[str, tuple[str | None, str]], option: str
) -> list[ProblemError]:
    """D-98 140-A9 INPUT-1 (SSP basis) for a SEPARATE_CONTRACT choice: every ``ssp_basis`` entry
    naming an ``ssp_book_version_id`` must name an APPROVED version (``versions`` = id → (legacy
    label, version key)) whose label or key equals the line's ``ssp_version_label`` — the value the
    engine matches under POL-070 ``NAMED_VERSION`` (S05 ``select_version``) — and the entity's
    version basis must BE ``NAMED_VERSION``, else the override has no policy consumer in the booking
    and is refused before approval. Pure."""
    if not separate_choice(row):
        return []
    labels = {
        str(line.get("obligation_key")): line.get("ssp_version_label")
        for line in (row["lines"] or ())
        if isinstance(line, Mapping)
    }
    errors: list[ProblemError] = []
    for key, basis in override_entries(row).items():
        version_id = str(basis["ssp_book_version_id"])
        named = versions.get(version_id)
        if named is None:
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SSP_VERSION_UNKNOWN.format(key=key),
                )
            )
            continue
        label = labels.get(str(key))
        if label is None or label not in {value for value in named if value is not None}:
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SSP_LABEL_MISMATCH.format(key=key, version=named[1], label=label),
                )
            )
        if option != "NAMED_VERSION":
            errors.append(
                _error(
                    f"ssp_basis.{key}.ssp_book_version_id",
                    RULE_SEPARATE,
                    SSP_POLICY_NOT_NAMED.format(option=option),
                )
            )
    return errors


def override_version_errors(
    row: Mapping[str, Any], *, versions: Mapping[str, tuple[str | None, str]]
) -> list[ProblemError]:
    """01-DECISIONS D-18 for a modification that stays in its contract (item
    MOD-SSP-OVERRIDE-PREVIEW-1): every authored ``ssp_basis`` override names an APPROVED SSP book
    version (``versions`` = id → (legacy label, version key)) — the engine prices the obligation's
    weight from it (ENGINE_SPEC S06-R-11) and is handed the key of an approved version only. An
    override without a version, or naming one that is not approved, is refused by name before the
    dry run instead of failing it. Pure."""
    return [
        _error(
            f"ssp_basis.{key}.ssp_book_version_id",
            RULE_WEIGHTS,
            SSP_VERSION_UNKNOWN.format(key=key),
        )
        for key, basis in _authored_true(row.get("ssp_basis")).items()
        if str(basis.get("ssp_book_version_id")) not in versions
    ]


def _ssp_basis_errors(
    session: Session,
    row: Mapping[str, Any],
    known_at: datetime,
    *,
    document: Mapping[str, Any] | None = None,
) -> list[ProblemError]:
    """``ssp_basis_mismatches`` with the facts read: the APPROVED versions the row names (legacy
    label and ``<book code>@v<no>`` key) and the entity's POL-070 value in the primary book at
    ``known_at``."""
    if not separate_choice(row):
        return []
    ids = sorted({str(basis["ssp_book_version_id"]) for basis in override_entries(row).values()})
    if not ids:
        return []
    versions = _ssp_versions(session, row)
    found = registry.resolve(
        session,
        SSP_VERSION_BASIS,
        book_code=BookCode(queries.primary_book(session)),
        entity_id=_uuid(row["contracting_entity_id"]),
        known_at=known_at,
    )
    value = found.value
    option = str(value.get("option", "")) if isinstance(value, Mapping) else str(value)
    errors = ssp_basis_mismatches(row, versions=versions, option=option)
    if document is not None:
        # A12 (1) at submit: the RETAINED selection of the stored preview must still equal the
        # override (the preview basis freezes the row; the selection travels in its provenance)
        retained = ((document.get("provenance") or {}).get("separate_contract") or {}).get(
            "ssp_selection"
        )
        errors += ssp_selection_mismatches(
            row, selection=retained if isinstance(retained, Mapping) else {}, versions=versions
        )
    return errors


def booking_body(
    row: Mapping[str, Any], current: Mapping[str, Any], *, entity_code: str
) -> ContractBookedV1:
    """S06-R-03 / D-98 140-A6 SEPARATE-INPUT-1: the 25-12 separate contract — every ADD line of the
    modification booked as a new contract of the same customer, entity and currency; the external
    id is the questionnaire's contract-level ``separate_contract_external_id`` or
    ``<external id>-<modification no>``; ``noncash_consideration`` and ``consideration_payable``
    carried as the booking's own; an ``ssp_basis`` override becomes the line's
    ``ssp_override_justification``; a line in another currency is refused by name, never retagged.
    Pure (the entity code is supplied)."""
    questionnaire = row["questionnaire"] or {}
    external_id = str(
        questionnaire.get(SEPARATE_EXTERNAL_ID)
        or f"{current['external_id']}-{row['modification_no']}"
    )
    currency = str(row["currency"]).strip()
    basis = row.get("ssp_basis") or {}
    lines = []
    for index, line in enumerate(_added_lines(row)):
        delta = line.get("consideration_delta") or {}
        found = (
            str(delta.get("currency") or currency).strip()
            if isinstance(delta, Mapping)
            else currency
        )
        if found != currency:
            raise _failed(
                _error(
                    f"lines[{index}].consideration_delta.currency",
                    RULE_LINE_CURRENCY,
                    LINE_CURRENCY_MISMATCH.format(
                        key=line["obligation_key"], found=found, expected=currency
                    ),
                )
            )
        key = str(line["obligation_key"])
        override = basis.get(key) if isinstance(basis, Mapping) else None
        justification = (
            str(override.get("justification"))
            if isinstance(override, Mapping) and override.get("is_override")
            else None
        )
        lines.append(
            {
                "obligation_key": key,
                "product_code": str(line["product_code"]),
                "stratification": line.get("stratification"),
                "quantity": str(line.get("quantity_delta") or "0"),
                "total_price": {
                    "amount": str(delta.get("amount", "0")) if isinstance(delta, Mapping) else "0",
                    "currency": currency,
                },
                "start_date": line.get("start_date"),
                "end_date": line.get("end_date"),
                "performing_entity_code": line.get("selling_entity_code"),
                "ssp_version_label": line.get("ssp_version_label"),
                "ssp_override_justification": justification,
                # D-98 140-A9 INPUT-1: the approved version id and book of the override travel as
                # provenance on the booked line (the booking pins SSP by label under POL-070).
                "custom_attributes": (
                    {
                        "ssp_book_version_id": str(override["ssp_book_version_id"]),
                        "ssp_basis_source": "modification_ssp_basis",
                    }
                    if isinstance(override, Mapping)
                    and override.get("is_override")
                    and override.get("ssp_book_version_id")
                    else None
                ),
                "account_overrides": line.get("account_codes"),
                "memo_1": line.get("memo_1"),
                "memo_2": line.get("memo_2"),
                "memo_3": line.get("memo_3"),
            }
        )
    return ContractBookedV1.model_validate(
        {
            "external_id": external_id,
            "customer_id": str(current["customer_id"]),
            "contracting_entity_code": entity_code,
            "transaction_currency": currency,
            "inception_date": row["effective_date"],
            "lines": lines,
            "noncash_consideration": list(row.get("noncash_consideration") or ()),
            "consideration_payable": list(row.get("consideration_payable") or ()),
            "scope_605_35": bool(row["scope_605_35"]) if row["scope_605_35"] is not None else False,
        }
    )


def _booking_of(
    session: Session, row: Mapping[str, Any], current: Mapping[str, Any]
) -> ContractBookedV1:
    """``booking_body`` with the contracting entity's code read from the database."""
    entity_code = str(
        session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == current["contracting_entity_id"])
        ).scalar_one()
    )
    return booking_body(row, current, entity_code=entity_code)


# --- approval callbacks (registered lifecycle) --------------------------------------------------


def _system_unit(uow: UnitOfWork, on_behalf_of: UUID | None) -> UnitOfWork:
    principal = system_principal(uow.principal.tenant_id, on_behalf_of_id=on_behalf_of)
    ctx = dataclasses.replace(uow.ctx, principal=principal)
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _preparer(session: Session, approval_request_id: UUID) -> UUID | None:
    found = (
        session.execute(
            select(approval_request.c.preparer_id, approval_request.c.preparer_kind).where(
                approval_request.c.id == approval_request_id
            )
        )
        .mappings()
        .one()
    )
    if found["preparer_id"] is None or _text(found["preparer_kind"]) != PrincipalKind.USER.value:
        return None
    return _uuid(found["preparer_id"])


def _apply_row(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    approval_request_id: UUID,
    on_behalf_of: UUID | None,
    counterpart: Mapping[str, Any] | None = None,
) -> None:
    """SUBMITTED → APPROVED → APPLIED for one row: SYSTEM appends its ``CONTRACT_AMENDED``
    (S06-R-01); a ``SEPARATE_CONTRACT`` choice books a new contract instead (S06-R-03; its own
    commit)."""
    session = uow.session
    modification_id = _uuid(row["id"])
    approved = transitions.apply(
        session,
        OBJECT,
        modification_id,
        to_status=APPROVED,
        expected_status=SUBMITTED,
        set_values={"approval_request_id": approval_request_id, **_bump(uow)},
    )
    system = _system_unit(uow, on_behalf_of)
    if separate_choice(row):
        # S06-R-03 (D-98 140-A6 SEPARATE-CHOICE-1: the mode is the APPROVED chosen_treatments,
        # never the proposal summary): the platform books the new contract in its own group and
        # appends nothing to the original stream; the modification's approval covers the booking,
        # the new contract's activation follows the ordinary CONTRACT_ACTIVATION path (D-98 140
        # Q-6). The link is the
        # booking event as ``applied_event_id`` (04 OQ-13: T-CON-01 has no origin_modification_id).
        booked = commands.book_contract(
            system, body=_booking_of(session, row, current), origin="SYSTEM"
        )
        for audit_event in system.drain_audit_events():
            uow.buffer_audit_event(audit_event)
        commands.provisional_compute(uow, _uuid(booked.combination_group["id"]))
        # A12 (1) at apply: the persisted selection (obligation_version.ssp_book_version_id of the
        # new contract's latest versions in the primary book) must equal the override; a mismatch
        # refuses and rolls the decision back.
        applied_mismatch = ssp_applied_mismatches(
            row, persisted=_persisted_ssp_versions(session, _uuid(booked.contract["id"]))
        )
        if applied_mismatch:
            raise _failed(*applied_mismatch)
        event_id = _uuid(booked.event["id"])
        uow.audit(
            action=BOOK_ACTION,
            object_type=OBJECT,
            object_id=modification_id,
            object_version=str(approved["row_version"]),
            after={
                "separate_contract_id": str(booked.contract["id"]),
                "external_id": str(booked.contract["external_id"]),
                "combination_group_id": str(booked.combination_group["id"]),
            },
            approval_request_id=approval_request_id,
            contract_id=_uuid(row["contract_id"]),
        )
    elif row["regroup_id"] is not None and counterpart is not None:
        (appended,) = append_events(
            system,
            contract_id=_uuid(current["id"]),
            expected_stream_version=int(current["head_stream_version"]),
            events=[_regrouped_event(row, counterpart, approval_request_id=approval_request_id)],
            origin="SYSTEM",
        )
        for audit_event in system.drain_audit_events():
            uow.buffer_audit_event(audit_event)
        event_id = _uuid(appended["id"])
        if _text(row["kind"]) == ModificationKind.ADD_OBLIGATION.value:
            source = _source_obligations(session, _uuid(counterpart["contract_id"]))
            keys = [str(line["obligation_key"]) for line in _added_lines(row)]
            _insert_created_obligations(
                system,
                current=current,
                event=appended,
                keys=keys,
                products={source[k]["product_code"]: _uuid(source[k]["product_id"]) for k in keys},
                product_codes={k: str(source[k]["product_code"]) for k in keys},
                regrouped_from={k: _uuid(source[k]["id"]) for k in keys},
            )
    else:
        (appended,) = append_events(
            system,
            contract_id=_uuid(current["id"]),
            expected_stream_version=int(current["head_stream_version"]),
            events=[_amended_event(row, approval_request_id=approval_request_id)],
            origin="SYSTEM",
        )
        for audit_event in system.drain_audit_events():
            uow.buffer_audit_event(audit_event)
        event_id = _uuid(appended["id"])
        added = _added_lines(row)
        if added:
            codes = {str(line["obligation_key"]): str(line["product_code"]) for line in added}
            _insert_created_obligations(
                system,
                current=current,
                event=appended,
                keys=list(codes),
                products=_product_ids(session, list(codes.values())),
                product_codes=codes,
            )
    applied = transitions.apply(
        session,
        OBJECT,
        modification_id,
        to_status=APPLIED,
        expected_status=APPROVED,
        set_values={"applied_event_id": event_id, **_bump(uow)},
    )
    uow.audit(
        action=APPLY_ACTION,
        object_type=OBJECT,
        object_id=modification_id,
        object_version=str(applied["row_version"]),
        before={"status": SUBMITTED},
        after={
            "status": APPLIED,
            "applied_event_id": str(event_id),
            "approval_request_id": str(approval_request_id),
        },
        approval_request_id=approval_request_id,
        contract_id=_uuid(row["contract_id"]),
    )


def _approved(uow: UnitOfWork, modification_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``MODIFICATION`` (DG-CMD-09; DG-KRN-APR-05 rev 1.40; D-98 140 Q-4): the
    protecting locks in the kernel order, the fresh-basis check, then every row of the subject —
    one, or the regroup pair under ``lock_groups_then_contracts`` — applied in this unit of work and
    every group recomputed; an ``EngineError`` rolls the decision back, so neither applies."""
    session = uow.session
    rows = modification_rows(session, modification_id)
    contract_ids = sorted({_uuid(row["contract_id"]) for row in rows})
    if len(contract_ids) == 1:
        group_id, current = lock_group_then_contract(session, contract_ids[0])
        currents = {contract_ids[0]: current}
        group_ids = {group_id}
    else:
        currents = lock_groups_then_contracts(session, contract_ids)
        group_ids = {_uuid(row["combination_group_id"]) for row in currents.values()}
    locked = [_row(session, _uuid(row["id"]), lock=True) for row in rows]
    if any(_text(row["status"]) != SUBMITTED for row in locked):
        raise LookupError(f"modification {modification_id} is not submitted")
    approvals.assert_fresh_basis(uow, approval_request_id)
    # The backstop of PRD ERR-87, not the rule: the submission refuses while a linked estimate
    # version is not approved, nothing links to a modification once it is submitted, and an
    # approved version does not go back — so the commands produce no such state.
    unapproved = _linked_errors(
        session,
        [_uuid(row["id"]) for row in locked],
        LINKED_UNAPPROVED,
        LINKED_NOT_APPROVED_AT_APPROVAL,
    )
    if unapproved:
        raise Problem("invalid-transition", errors=unapproved)
    # PRD ERR-95 where the approval meets it: a record added to the modification after its
    # submission is reviewed, or discarded, before the modification is approved.
    unreviewed = _record_errors(
        session, [_uuid(row["id"]) for row in locked], RECORD_NOT_REVIEWED_AT_APPROVAL
    )
    if unreviewed:
        raise Problem("invalid-transition", errors=unreviewed)
    on_behalf_of = _preparer(session, approval_request_id)
    # Requests submitted before BR-MOD-01 was enforced must not apply unanswered proposals.
    unanswered = [error for row in locked for error in questionnaire_confirmation_errors(row)]
    if unanswered:
        raise _failed(*unanswered)
    # A regroup pair applies OUT (the REMOVE row) before IN (the ADD row): the IN event copies the
    # moved obligations' products from the source contract.
    ordered = sorted(
        locked,
        key=lambda r: 0 if _text(r["kind"]) == ModificationKind.REMOVE_OBLIGATION.value else 1,
    )
    for row in ordered:
        current = currents[_uuid(row["contract_id"])]
        counterpart = (
            next((o for o in ordered if o["id"] != row["id"]), None) if len(ordered) == 2 else None
        )
        _apply_row(
            uow,
            row,
            current,
            approval_request_id=approval_request_id,
            on_behalf_of=on_behalf_of,
            counterpart=counterpart,
        )
        current["head_stream_version"] = int(current["head_stream_version"]) + 1
    for group_id in sorted(group_ids):
        try:
            computation.recompute(uow, group_id, trigger=ComputationTrigger.COMMAND)
        except EngineError as error:
            raise engine_problem(error) from error


def _closer(to_status: str, action: str) -> Any:
    """``on_rejected`` (REJECTED) or ``on_voided`` (back to DRAFT) of the subject's rows."""

    def close(uow: UnitOfWork, modification_id: UUID, approval_request_id: UUID) -> None:
        session = uow.session
        for row in modification_rows(session, modification_id):
            locked = _row(session, _uuid(row["id"]), lock=True)
            if _text(locked["status"]) != SUBMITTED:
                continue
            updated = transitions.apply(
                session,
                OBJECT,
                _uuid(row["id"]),
                to_status=to_status,
                expected_status=SUBMITTED,
                set_values=_bump(uow),
            )
            uow.audit(
                action=action,
                object_type=OBJECT,
                object_id=_uuid(row["id"]),
                object_version=str(updated["row_version"]),
                before={"status": SUBMITTED},
                after={"status": to_status, "approval_request_id": str(approval_request_id)},
                approval_request_id=approval_request_id,
                contract_id=_uuid(row["contract_id"]),
            )

    return close


def _flags(_session: Session, _modification_id: UUID) -> frozenset[str]:
    """The routing flags a Session can derive: none — ``submit`` supplies the preview-derived
    PRD §2.5 flags to ``route_submission`` (D-98 140 Q-5) and the request row keeps them."""
    return frozenset()


register_lifecycle(
    ApprovalSubjectType.MODIFICATION,
    SubjectLifecycle(
        on_approved=_approved,
        on_rejected=_closer(REJECTED, CLOSE_ACTION),
        on_voided=_closer(DRAFT, CLOSE_ACTION),
        flags=_flags,
    ),
)


# --- reads ---------------------------------------------------------------------------------------


def modifications_statement(
    *,
    contract_id: UUID,
    statuses: Sequence[ModificationStatus] = (),
    effective_from: Any = None,
    effective_to: Any = None,
) -> Select[Any]:
    statement = select(modification).where(modification.c.contract_id == contract_id)
    if statuses:
        statement = statement.where(modification.c.status.in_([s.value for s in statuses]))
    if effective_from is not None:
        statement = statement.where(modification.c.effective_date >= effective_from)
    if effective_to is not None:
        statement = statement.where(modification.c.effective_date <= effective_to)
    return statement


def _approvals(
    session: Session, request_ids: Sequence[UUID]
) -> dict[UUID, tuple[UUID | None, str, datetime]]:
    wanted = sorted(set(request_ids))
    if not wanted:
        return {}
    found: dict[UUID, tuple[UUID | None, str, datetime]] = {}
    statement = (
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            approval_decision.c.decided_at,
        )
        .where(
            approval_decision.c.approval_request_id.in_(wanted),
            approval_decision.c.decision.in_(
                [ApprovalDecisionKind.APPROVE.value, ApprovalDecisionKind.AUTO_APPROVE.value]
            ),
        )
        .order_by(approval_decision.c.decided_at)
    )
    for request_id, approver_id, kind, decided_at in session.execute(statement):
        found[_uuid(request_id)] = (
            None if approver_id is None else _uuid(approver_id),
            _text(kind),
            decided_at,
        )
    return found


def _catch_up_total(preview: Mapping[str, Any] | None) -> Any:
    """``impact_summary.catch_up_total`` of a list item: the retained preview's, else null."""
    if preview is None:
        return None
    summary = preview.get("summary") if isinstance(preview, Mapping) else None
    return None if not isinstance(summary, Mapping) else summary.get("catch_up_total")


def _item(
    row: Mapping[str, Any],
    decisions: Mapping[UUID, tuple[UUID | None, str, datetime]],
    names: Mapping[UUID, str],
    preview: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    approver: dict[str, Any] | None = None
    approved_at: datetime | None = None
    if _text(row["status"]) in (APPROVED, APPLIED) and row["approval_request_id"] is not None:
        decision = decisions.get(_uuid(row["approval_request_id"]))
        if decision is not None:
            approver_id, kind, decided_at = decision
            approver = approval_queries.actor(approver_id, kind, names)
            approved_at = decided_at
    preparer = approval_queries.actor(
        None if row["created_by"] is None else _uuid(row["created_by"]),
        _text(row["created_by_kind"]),
        names,
    )
    return {
        "id": row["id"],
        "modification_no": row["modification_no"],
        "contract_id": row["contract_id"],
        "contracting_entity_id": row["contracting_entity_id"],
        "effective_date": row["effective_date"],
        "kind": _text(row["kind"]),
        "template_mode": None if row["template_mode"] is None else _text(row["template_mode"]),
        "status": _text(row["status"]),
        "reference": row["reference"],
        "currency": str(row["currency"]).strip(),
        "proposed_treatments": {
            str(k): _text(v) for k, v in (row["proposed_treatments"] or {}).items()
        },
        "chosen_treatments": {
            str(k): _text(v) for k, v in (row["chosen_treatments"] or {}).items()
        },
        "treatment_summary": None
        if row["treatment_summary"] is None
        else _text(row["treatment_summary"]),
        "rationale": row["rationale"],
        "judgement_record_id": row["judgement_record_id"],
        "impact_preview_sha256": row["impact_preview_sha256"],
        "content_sha256": row["content_sha256"],
        "approval_request_id": row["approval_request_id"],
        "applied_event_id": row["applied_event_id"],
        "regroup_id": row["regroup_id"],
        "impact_summary": ModificationImpactOut(catch_up_total=_catch_up_total(preview)),
        "preparer": ActorOut.model_validate(preparer),
        "approver": None if approver is None else ActorOut.model_validate(approver),
        "approved_at": approved_at,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "row_version": int(row["row_version"]),
    }


def modification_outs(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    previews: Mapping[UUID, Mapping[str, Any]] | None = None,
) -> list[ModificationListItemOut]:
    """API-R-31 list items (04 §16.14: without ``lines``, ``questionnaire`` and the preview;
    ``impact_summary.catch_up_total`` from the row's retained preview document in ``previews``,
    read by the route through the file store — D-98 140-A4)."""
    decisions = _approvals(
        session, [_uuid(r["approval_request_id"]) for r in rows if r["approval_request_id"]]
    )
    names = approval_queries.display_names(
        session,
        [
            *(None if r["created_by"] is None else _uuid(r["created_by"]) for r in rows),
            *(item[0] for item in decisions.values()),
        ],
    )
    stored = previews or {}
    return [
        ModificationListItemOut.model_validate(
            _item(row, decisions, names, stored.get(_uuid(row["id"])))
        )
        for row in rows
    ]


def preview_answered(session: Session, principal: Principal, modification_id: UUID) -> bool:
    """Whether ``principal`` is answered the stored preview of the modification (04 §16.10 "Who
    reads a stored preview", rev 1.300): the question the file's own routes ask of the same
    document (``file_access.stored_preview_readable``)."""
    return file_access.stored_preview_readable(
        session, principal, ApprovalSubjectType.MODIFICATION, modification_id
    )


def get_modification(
    session: Session,
    modification_id: UUID,
    *,
    preview: Mapping[str, Any] | None = None,
    preview_withheld: bool = False,
) -> ModificationOut:
    """API-S-Modification of one row; ``preview`` is the stored preview's document as the route
    read it (or None). ``preview_withheld``: the caller is not answered the stored preview (04
    §16.10 "Who reads a stored preview", rev 1.300) — the answer names neither its summary nor
    its file and says so in ``impact_preview_withheld``. ``impact_summary.catch_up_total``, the
    catch-up of the contract's own obligations, is stated to every reader of the row, as a
    list item states it."""
    row = _row(session, modification_id)
    repo.get_contract(session, _uuid(row["contract_id"]))  # 404 when the contract is not visible
    (item,) = modification_outs(
        session, [row], previews=None if preview is None else {modification_id: preview}
    )
    proposal_detail, proposals, tests = stored_classification(row["classification"])
    detail = {
        **item.model_dump(),
        "lines": [dict(line) for line in (row["lines"] or ())],
        "questionnaire": dict(row["questionnaire"] or {}),
        "price_change_amount": None
        if row["price_change_amount"] is None
        else str(row["price_change_amount"]),
        "noncash_consideration": row["noncash_consideration"],
        "consideration_payable": row["consideration_payable"],
        "scope_605_35": row["scope_605_35"],
        "ssp_basis": dict(row["ssp_basis"] or {}),
        "impact_preview_file_id": None if preview_withheld else row["impact_preview_file_id"],
        "impact_preview": None
        if preview is None or preview_withheld
        else ImpactSummaryOut.model_validate(preview["summary"]),
        "impact_preview_withheld": preview_withheld,
        # 04 T-CON-06 ``classification`` (rev 1.210): what the latest ``/classify`` answered —
        # the proposals of the obligations, and each under a member of its own the engine's
        # proposal detail and its price tests (rev 1.250, rev 1.286).
        "prefill_reasons": proposals,
        "proposal_detail": proposal_detail,
        "price_tests": tests,
        "linked_estimate_versions": [
            {
                "id": found["id"],
                "estimate_id": found["estimate_id"],
                "element_code": str(found["element_code"]),
                "estimate_kind": _text(found["estimate_kind"]),
                "version_no": int(found["version_no"]),
                "status": _text(found["status"]),
                "effective_date": found["effective_date"],
            }
            for found in linked_estimate_versions(session, [modification_id])
        ],
    }
    return ModificationOut.model_validate(detail)


def read_preview(
    uow_or_session: Any, row: Mapping[str, Any], *, files: Any, keyring: Any
) -> dict[str, Any] | None:
    """The stored preview document of a row for a read route, or None when none is stored."""
    if row["impact_preview_file_id"] is None:
        return None
    session = getattr(uow_or_session, "session", uow_or_session)
    _, stream = open_file(
        session, _uuid(row["impact_preview_file_id"]), files=files, keyring=keyring
    )
    with stream:
        document: dict[str, Any] = json.loads(stream.read().decode("utf-8"))
    return document
