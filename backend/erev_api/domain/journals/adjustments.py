"""Manual adjustments (04 T-SL-05, E-93, E-94, §15.3 API-R-37, §16.14 "API-R-37 shapes", T-PLT-17
flag ``DEFER_PAST_LOCK``; PRD SM-10, §2.5 routing rows ``MANUAL_ADJUSTMENT``, BR-CLS-04, BR-CLS-06;
ENGINE_SPEC_B §9.2.11 S09-R-38 to R-41, S14-R-09a; 03 REQ-JE-019, REQ-REC-023, REQ-CLS-003;
CTL-014, CTL-015; dev-guide DG-CMD-09, DG-CMD-10; BUILD_SPEC CLO-12; supervisor ruling R-51).

An adjustment is prepared for one contract, book and posting period: a schedule override, a manual
release or deferral of one obligation, or a manual journal or account reclassification of lines.
``create`` and ``update`` store a DRAFT after validating the payload against its kind (every
finding collected, 422 ``validation-failed``; lines that do not balance answer 422
``ledger-unbalanced``). The posting period is the period of the effective date, or the first later
postable one (DG-KRN-TIME-04). ``amount_functional_abs`` is derived by the server, never sent: for
a schedule kind the absolute change of the obligation's revenue in the periods the adjustment
names (its period for a release or a deferral, the listed periods for an override), measured by a
dry run of the group with the adjustment applied; for a journal kind the debit total — converted
to the entity's functional currency at the spot rate of the effective date.

``submit`` routes a DRAFT under subject ``MANUAL_ADJUSTMENT`` with the dry run as its impact
preview (REQ-PLT-015). From USD 10,000.00 the request needs an attachment (422 naming
``attachments``) and takes a second step held by a Controller (PRD §2.5). In a ``closing`` period
the submitter holds ``period.lock`` for the entity, in place of ``adjustment.create`` (BR-CLS-04);
no auto-approval rule ever applies (BR-CLS-06; REQ-PLT-016). ``withdraw`` lets the preparer take
the request back, and a request voided as stale returns the adjustment to DRAFT alike; a REJECTED
adjustment returns to DRAFT through ``update`` (revise and resubmit); ``discard`` voids a DRAFT.
``update`` is the creator's alone (item ADJ-VOID-REFUSE-1; supervisor ruling R-112 (b) (2)): the
self-approval rule excludes the creator and the submitter of a request, and the row keeps no list
of editors, so a second editor could otherwise approve what they wrote. ``submit`` and ``discard``
add nothing to the content and stay with whoever holds the permission for the entity — a discard
keeps an absent creator's draft from standing in a close's way.
``withdraw`` and ``request_defer_past_lock`` post nothing, so they take either permission for the
entity. Every command locks the combination group, the contract and then the adjustment
(DG-KRN-DB-08, the order of a T-CON-06 modification).

``request_defer_past_lock`` replaces the pending posting request of a SUBMITTED adjustment with a
request flagged ``DEFER_PAST_LOCK`` on the same routing rows. Its approval marks the adjustment
deferred past lock: it stays SUBMITTED without a pending request and holds neither the
``MANUAL_ADJUSTMENTS_CLEARED`` nor the ``APPROVALS_CLEARED`` gate (REQ-JE-019); a later ``submit``
routes it for posting. Its rejection leaves the adjustment SUBMITTED and counted.

The approval of a posting request is a decision command (DG-CMD-09): under the group and contract
locks and a fresh basis it appends ``MANUAL_ADJUSTMENT_APPLIED`` as SYSTEM, posts the approved
lines of a journal kind itself — posting kind ``MANUAL_ADJUSTMENT``, key ``adjustment:<id>``, the
accounts as approved, in the adjustment period or, once that is closed, in the first open period
with the adjustment period as origin — and recomputes the group, failing closed. The engine reads
the adjustment from the event (the bundle builder resolves the row): a schedule kind changes the
stage 09 targets, and the lines of a journal kind are stage 14 role targets, so the computation
finds the posted lines equal to their targets and emits nothing for them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.bundle import OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError
from erev_engine.money import minor_to_decimal
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    obligation_subject_key,
)
from sqlalchemy import Select, and_, func, insert, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import preview as previews
from erev_api.approvals import quorum
from erev_api.approvals.subjects import (
    ABOVE_THRESHOLD,
    DEFER_PAST_LOCK,
    THRESHOLD_CURRENCY,
    SubjectLifecycle,
    manual_adjustment_content,
    register_lifecycle,
)
from erev_api.audit import writer as audit_writer
from erev_api.auth import mfa
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.permissions import spec as permission_spec
from erev_api.auth.principal import Principal, system_principal
from erev_api.db import new_id, transitions
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_request,
    combination_group,
    contract,
    file_attachment,
    file_object,
    gl_account,
    job,
    legal_entity,
    manual_adjustment,
    obligation,
    period,
    product,
    schedule,
    schedule_line,
)
from erev_api.domain.contracts import bundles, computation, period_ends, repo
from erev_api.domain.contracts import queries as contract_queries
from erev_api.domain.contracts.activation import engine_problem
from erev_api.domain.contracts.compute_job import ADJUSTMENT_PREVIEW_MODE
from erev_api.domain.contracts.events import dry_run_summary
from erev_api.domain.contracts.modifications import spot_basis
from erev_api.domain.journals import subledger
from erev_api.domain.platform import approval_queries, file_access
from erev_api.domain.platform.jobs import JOB_COLUMNS, job_outs
from erev_api.enums import (
    AccountRole,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ComputationTrigger,
    ContractEventType,
    ContractStatus,
    JobKind,
    ManualAdjustmentKind,
    ManualAdjustmentStatus,
    PeriodState,
    ScheduleKind,
    SubledgerPostingKind,
)
from erev_api.events.payloads import ManualAdjustmentAppliedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.files.store import lock_readable
from erev_api.jobs.registry import JobOutcome
from erev_api.money import money_out
from erev_api.numbering import next_number
from erev_api.periods import PeriodRef, period_state, posting_period
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut, RefOut
from erev_api.schemas.events import ImpactJournalLineOut, ImpactSummaryOut
from erev_api.schemas.manual_adjustments import (
    AdjustmentPayloadIn,
    ManualAdjustmentCreateIn,
    ManualAdjustmentDeferIn,
    ManualAdjustmentDiscardIn,
    ManualAdjustmentOut,
    ManualAdjustmentSubmitIn,
    ManualAdjustmentUpdateIn,
    ManualAdjustmentWithdrawIn,
)
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from erev_api.jobs.context import JobContext

__all__ = [
    "ADJUSTMENT_PREVIEW_MODE",
    "CREATE_PERMISSION",
    "LOCK_PERMISSION",
    "OBJECT",
    "PREVIEW_JOB_SUBJECT",
    "READ_PERMISSION",
    "AccountFacts",
    "adjustment_outs",
    "adjustments_statement",
    "create",
    "discard",
    "get_adjustment",
    "payload_errors",
    "preview",
    "request_defer_past_lock",
    "run_preview",
    "stored_payload",
    "submit",
    "unbalanced",
    "update",
    "withdraw",
]

OBJECT: Final = "manual_adjustment"
# 04 T-PLT-27 ``ck_job__subject_type`` admits a fixed list that does not name the adjustment: the
# preview job is a dry run of the adjustment's contract and works on that contract, as the
# preview of the events route does. The job's params name the adjustment.
PREVIEW_JOB_SUBJECT: Final = "contract"
CREATE_PERMISSION: Final = "adjustment.create"  # PRD ACT-14; 04 API-R-37
LOCK_PERMISSION: Final = "period.lock"  # PRD BR-CLS-04: the submitters of a closing period
READ_PERMISSION: Final = "contract.read"
SERIES: Final = "ADJUSTMENT"
RULE: Final = "T-SL-05"
RULE_STATUS: Final = "E-94"
RULE_BOOK: Final = "T-SL-05"
RULE_FOREIGN: Final = "S14-R-09a"  # the engine rule a foreign-currency journal would meet
HREF: Final = "/api/v1/manual-adjustments/{adjustment_id}"
ENTRY_KIND: Final = "MANUAL_ADJUSTMENT"  # 04 E-29
LATE_REASON: Final = "LATE_EVENT"  # the reason a line posted with an origin carries (S08-R-08)
REVENUE: Final = ScheduleKind.REVENUE.value

DRAFT: Final = ManualAdjustmentStatus.DRAFT.value
SUBMITTED: Final = ManualAdjustmentStatus.SUBMITTED.value
APPROVED: Final = ManualAdjustmentStatus.APPROVED.value
POSTED: Final = ManualAdjustmentStatus.POSTED.value
REJECTED: Final = ManualAdjustmentStatus.REJECTED.value
VOIDED: Final = ManualAdjustmentStatus.VOIDED.value
PENDING: Final = ApprovalRequestStatus.PENDING.value
OVERRIDE: Final = ManualAdjustmentKind.SCHEDULE_OVERRIDE.value
RELEASE: Final = ManualAdjustmentKind.MANUAL_RELEASE.value
DEFER: Final = ManualAdjustmentKind.MANUAL_DEFER.value
MOVE_KINDS: Final = frozenset({RELEASE, DEFER})
SCHEDULE_KINDS: Final = frozenset({OVERRIDE, RELEASE, DEFER})
JOURNAL_KINDS: Final = frozenset(
    {ManualAdjustmentKind.MANUAL_JOURNAL.value, ManualAdjustmentKind.ACCOUNT_RECLASS.value}
)
EDITABLE: Final = frozenset({DRAFT, REJECTED})
PREVIEWABLE: Final = frozenset({DRAFT, SUBMITTED, REJECTED})
# A contract whose stream an adjustment can extend: booked drafts and voided contracts cannot.
ADJUSTABLE_CONTRACTS: Final = frozenset(
    {
        ContractStatus.ACTIVE.value,
        ContractStatus.COMPLETED.value,
        ContractStatus.TERMINATED.value,
    }
)
# Roles a T-SL-05 line cannot carry: the reserved ones (04 D-14a), the rounding role (S14-R-11)
# and the roles whose line needs a clearing purpose or a counterparty the line shape lacks.
REFUSED_ROLES: Final = frozenset(
    {
        AccountRole.RETAINED_EARNINGS.value,
        AccountRole.FINANCING_OBLIGATION.value,
        AccountRole.ROUNDING.value,
        AccountRole.BILLING_CLEARING.value,
        AccountRole.INTERCOMPANY_DUE_TO.value,
        AccountRole.INTERCOMPANY_DUE_FROM.value,
    }
)
# ENGINE_SPEC_B S14-R-13 identity dimensions: set by the posting, never by a line.
IDENTITY_DIMENSIONS: Final = ("contract", "contract_key", "obligation_key")
MIN_LINES: Final = 2

# Audit actions (AUD-CMD).
CREATE_ACTION: Final = "manual_adjustment.create"
UPDATE_ACTION: Final = "manual_adjustment.update"
SUBMIT_ACTION: Final = "manual_adjustment.submit"
WITHDRAW_ACTION: Final = "manual_adjustment.withdraw"
DISCARD_ACTION: Final = "manual_adjustment.discard"
DEFER_REQUEST_ACTION: Final = "manual_adjustment.request_defer_past_lock"
DEFER_ACTION: Final = "manual_adjustment.defer_past_lock"
DEFER_REJECT_ACTION: Final = "manual_adjustment.defer_past_lock_rejected"
POST_ACTION: Final = "manual_adjustment.post"
REJECT_ACTION: Final = "manual_adjustment.reject"
RETURN_ACTION: Final = "manual_adjustment.return_to_draft"
# The action of a refused preview (04 §16.10 rev 1.295); a preview that is taken writes
# ``job.start``, nothing of its own.
PREVIEW_ACTION: Final = "manual_adjustment.preview"

# [J] Copy the documents leave open (PRD §5.5 names no row for these findings).
NOT_ADJUSTABLE: Final = (
    "Only an active, completed or terminated contract takes a manual adjustment; "
    "{external_id} is {status}."
)
NOT_COMPUTED: Final = "{external_id} has no computed version in book {book} to adjust."
LEGACY_BOOK: Final = (
    "A manual adjustment names a posting book. Choose ASC606 or IFRS15, not LEGACY."
)
BOOK_NOT_KEPT: Final = "{entity} keeps no {book} state for {period}."
OBLIGATION_REQUIRED: Final = "Choose the obligation the adjustment applies to."
OBLIGATION_UNKNOWN: Final = "Choose an obligation of the contract."
NOT_FOR_KIND: Final = "{member} does not apply to a {kind} adjustment."
ONE_BASIS: Final = "Send exactly one of amount, ratio and remaining."
AMOUNT_POSITIVE: Final = "Enter an amount greater than 0."
RATIO_RANGE: Final = "Enter a ratio greater than 0 and at most 1."
CURRENCY_MISMATCH: Final = "Amounts are in the contract currency {currency}."
DECIMALS: Final = "{currency} amounts have at most {places} decimal places."
PERIODS_REQUIRED: Final = "List at least one period with its amount."
PERIOD_UNKNOWN: Final = "Choose a period of the entity's calendar."
PERIOD_REPEATED: Final = "A period is listed once."
LINES_REQUIRED: Final = "A journal has at least two lines."
LINE_ZERO: Final = "A line carries an amount other than 0."
ROLE_REFUSED: Final = "Role {role} cannot be used on a manual line."
ACCOUNT_UNKNOWN: Final = "Choose a GL account of this workspace."
ACCOUNT_INACTIVE: Final = "Account {code} is inactive."
ACCOUNT_OTHER_ENTITY: Final = "Account {code} does not apply to {entity}."
DIMENSION_RESERVED: Final = "Dimension {code} is set by the posting and cannot be sent."
DIMENSIONS_MISSING: Final = "Account {code} needs the dimension(s) {dimensions}."
FOREIGN_JOURNAL: Final = (
    "A manual journal or reclassification is available for contracts in the entity's functional "
    "currency ({functional}); this contract is in {currency}."
)
UNBALANCED: Final = (
    "The lines do not balance: debits {debit} and credits {credit} differ by {difference} "
    "{currency}."
)
RATE_MISSING: Final = "No spot rate from {base} to {quote} is published for {date}."
NOT_EDITABLE: Final = "Only a draft or rejected adjustment can be edited."
# Item ADJ-VOID-REFUSE-1 (supervisor ruling R-112 (b) (2); PRD ERR-71, a convention row of
# ``forbidden`` under the rule id of PRD SM-10): T-SL-05 keeps no list of editors, and the
# self-approval rule excludes the creator and the submitter — so nobody else shapes what is
# approved.
RULE_CREATOR: Final = "SM-10"
NOT_CREATOR: Final = "Only {creator} can change this adjustment."
NOT_SUBMITTABLE: Final = (
    "Only a draft adjustment, or a submitted one without a pending request, can be submitted."
)
NOT_WITHDRAWABLE: Final = "Only a submitted adjustment can be withdrawn."
NOT_DISCARDABLE: Final = "Only a draft adjustment can be discarded; withdraw a submitted one first."
NOT_DEFERRABLE: Final = (
    "Only a submitted adjustment that is not yet deferred can be deferred past lock."
)
DEFERRAL_PENDING: Final = "A request to defer this adjustment past lock is already pending."
NOT_PREVIEWABLE: Final = "A posted or voided adjustment has no preview."
SOFT_CLOSE_DETAIL: Final = (
    "{period} is in soft close: only users with the lock permission may submit manual adjustments."
)
PERIOD_CLOSED: Final = (
    "{period} is closed for {entity} in book {book}. Change the effective date to an open period, "
    "or discard the adjustment."
)
REPLACED_COMMENT: Final = "Replaced by a request to defer the adjustment past lock."


# --- small helpers -------------------------------------------------------------------------------


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _error(field: str, message: str, rule_id: str = RULE) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _failed(errors: Sequence[ProblemError]) -> Problem:
    count = len(errors)
    detail = "1 field needs attention." if count == 1 else f"{count} fields need attention."
    return Problem("validation-failed", detail, errors=list(errors))


def _state(message: str) -> Problem:
    return Problem("invalid-transition", message, errors=[_error("status", message, RULE_STATUS)])


def _not_creator(session: Session, row: Mapping[str, Any]) -> Problem:
    """403 ``forbidden`` naming the person who created ``row`` (PRD ERR-71): the edit of an
    adjustment is its creator's alone."""
    kind = _text(row["created_by_kind"])
    names = approval_queries.display_names(session, [row["created_by"]])
    creator = approval_queries.actor(row["created_by"], kind, names)["display_name"]
    message = NOT_CREATOR.format(creator=creator)
    return Problem("forbidden", message, errors=[_error("created_by", message, RULE_CREATOR)])


def _bump(uow: UnitOfWork, row: Mapping[str, Any]) -> dict[str, Any]:
    """SC-M of an IM-S row: no touch trigger raises ``row_version`` (04 DB-02)."""
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
        "row_version": int(row["row_version"]) + 1,
    }


def _minor(currency: str) -> int:
    return ISO_4217[currency].minor_unit


def _quantized(value: Decimal, currency: str) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-_minor(currency)), rounding=ROUND_HALF_UP)


def _money(value: Decimal, currency: str) -> Any:
    return money_out(_quantized(value, currency), currency, ISO_4217)


def _row(session: Session, adjustment_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    """The visible adjustment (RLS-TE), optionally ``FOR UPDATE``; else 404 ``not-found``."""
    statement = select(manual_adjustment).where(manual_adjustment.c.id == adjustment_id)
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _locked(uow: UnitOfWork, adjustment_id: UUID) -> tuple[dict[str, Any], UUID, dict[str, Any]]:
    """The row, its group id and its contract row under the kernel lock order (DG-KRN-DB-08: the
    combination group, then the contract row, then the T-SL-05 row ``FOR UPDATE`` — the order of a
    T-CON-06 modification); 404 ``not-found`` for an adjustment outside the caller's entities."""
    peek = _row(uow.session, adjustment_id)
    group_id, current = repo.lock_group_then_contract(uow.session, _uuid(peek["contract_id"]))
    return _row(uow.session, adjustment_id, lock=True), group_id, current


def _authorize(
    uow: UnitOfWork,
    permission: str,
    entity_id: UUID,
    adjustment_id: UUID,
    *,
    action: str,
    contract_id: UUID,
) -> None:
    """The guard of a command whose permission depends on the adjustment (BR-CLS-04): 403
    ``forbidden`` (or ``mfa-required``) with one ``DENIED`` event when ``permission`` is not held
    (DG-KRN-AUTH-05), 404 ``not-found`` when it is not held for the entity (DG-KRN-AUTH-04; ruling
    R-28)."""
    ctx = uow.ctx
    principal = ctx.principal
    if permission not in principal.permissions:
        audit_writer.record_denied(
            ctx,
            action=action,
            object_type=OBJECT,
            object_id=adjustment_id,
            permission=permission,
            keyring=uow.keyring,
            contract_id=contract_id,
        )
        raise Problem("forbidden")
    if permission_spec(permission).requires_mfa and principal.mfa_verified_at is None:
        enrolled = principal.id is not None and mfa.has_confirmed_factor(
            principal.id, request_id=ctx.request_id
        )
        audit_writer.record_denied(
            ctx,
            action=action,
            object_type=OBJECT,
            object_id=adjustment_id,
            permission=permission,
            detail={"reason": "mfa-required"},
            keyring=uow.keyring,
            contract_id=contract_id,
        )
        raise Problem(
            "mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED
        )
    require_for_entity(ctx, permission, entity_id)


# --- facts a payload is validated against --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountFacts:
    """What a manual line needs of its T-REF-13 account (the facts ``journals.validation`` reads
    before a journal run is written, REQ-JE-022)."""

    code: str
    is_active: bool
    entity_ids: frozenset[UUID]  # empty = every entity
    required_dimensions: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Facts:
    """The rows behind one adjustment of a contract, read once per command."""

    contract: Mapping[str, Any]
    entity_id: UUID
    entity_code: str
    functional_currency: str
    calendar_id: UUID
    currency: str
    book: BookCode
    posting: PeriodRef
    obligations: Mapping[UUID, Mapping[str, Any]]  # obligation id -> row
    periods: Mapping[UUID, PeriodRef]  # the entity's calendar
    accounts: Mapping[UUID, AccountFacts]


def _periods(session: Session, calendar_id: UUID) -> dict[UUID, PeriodRef]:
    rows = session.execute(
        select(
            period.c.id,
            period.c.calendar_id,
            period.c.period_key,
            period.c.fiscal_year,
            period.c.period_no,
            period.c.start_date,
            period.c.end_date,
        ).where(period.c.calendar_id == calendar_id)
    ).mappings()
    return {
        _uuid(row["id"]): PeriodRef(
            id=_uuid(row["id"]),
            calendar_id=_uuid(row["calendar_id"]),
            period_key=str(row["period_key"]),
            fiscal_year=int(row["fiscal_year"]),
            period_no=int(row["period_no"]),
            start_date=row["start_date"],
            end_date=row["end_date"],
        )
        for row in rows
    }


def _accounts(session: Session, payload: AdjustmentPayloadIn | None) -> dict[UUID, AccountFacts]:
    ids = sorted({line.gl_account_id for line in (payload.lines or ())} if payload else set())
    if not ids:
        return {}
    rows = session.execute(
        select(
            gl_account.c.id,
            gl_account.c.code,
            gl_account.c.is_active,
            gl_account.c.entity_ids,
            gl_account.c.required_dimensions,
        ).where(gl_account.c.id.in_(ids))
    )
    return {
        _uuid(row[0]): AccountFacts(
            code=str(row[1]),
            is_active=bool(row[2]),
            entity_ids=frozenset(_uuid(value) for value in (row[3] or ())),
            required_dimensions=frozenset(str(value) for value in (row[4] or ())),
        )
        for row in rows
    }


def _facts(
    session: Session,
    current: Mapping[str, Any],
    *,
    book: BookCode | None,
    effective_date: date,
    payload: AdjustmentPayloadIn | None,
) -> _Facts:
    """The facts of an adjustment of ``current`` dated ``effective_date``: 422 for a book that is
    not a posting book or that the entity does not keep; the period problems of
    ``posting_period`` (422 no period; 409 ``period-closed``)."""
    entity_id = _uuid(current["contracting_entity_id"])
    entity = (
        session.execute(
            select(
                legal_entity.c.code, legal_entity.c.functional_currency, legal_entity.c.calendar_id
            ).where(legal_entity.c.id == entity_id)
        )
        .mappings()
        .one_or_none()
    )
    if entity is None:
        raise Problem("not-found")
    chosen = BookCode(contract_queries.primary_book(session)) if book is None else book
    if chosen is BookCode.LEGACY:
        raise _failed([_error("book", LEGACY_BOOK, RULE_BOOK)])
    posting, _origin = posting_period(
        session, entity_id=entity_id, book_code=chosen, effective_date=effective_date
    )
    return _Facts(
        contract=current,
        entity_id=entity_id,
        entity_code=str(entity["code"]),
        functional_currency=str(entity["functional_currency"]).strip(),
        calendar_id=_uuid(entity["calendar_id"]),
        currency=str(current["transaction_currency"]).strip(),
        book=chosen,
        posting=posting,
        obligations={_uuid(row["id"]): row for row in repo.obligations(session, current["id"])},
        periods=_periods(session, _uuid(entity["calendar_id"])),
        accounts=_accounts(session, payload),
    )


# --- payload validation (pure; CPU-tested) -------------------------------------------------------


def _amount_errors(field: str, amount: Any, currency: str) -> list[ProblemError]:
    """Currency and minor-unit findings of one API-S-Money member."""
    if amount.currency != currency:
        return [_error(field, CURRENCY_MISMATCH.format(currency=currency))]
    exponent = Decimal(amount.amount).as_tuple().exponent
    places = _minor(currency)
    if isinstance(exponent, int) and -exponent > places:
        return [_error(field, DECIMALS.format(currency=currency, places=places), "API-C-06")]
    return []


def _absent(kind: str, payload: AdjustmentPayloadIn, members: Sequence[str]) -> list[ProblemError]:
    return [
        _error(f"payload.{member}", NOT_FOR_KIND.format(member=member, kind=kind))
        for member in members
        if getattr(payload, member) is not None
    ]


def payload_errors(
    kind: str,
    payload: AdjustmentPayloadIn,
    *,
    currency: str,
    functional_currency: str,
    entity_id: UUID,
    entity_code: str,
    obligations: Mapping[UUID, Any],
    periods: Mapping[UUID, Any],
    accounts: Mapping[UUID, AccountFacts],
) -> list[ProblemError]:
    """Every finding of a T-SL-05 payload against its kind, in member order. ``currency`` is the
    contract's and ``functional_currency`` its entity's; ``obligations`` are the contract's,
    ``periods`` the entity calendar's, ``accounts`` the named GL accounts. A journal kind needs a
    contract in the entity's functional currency (1.0 limit, ruling R-51; ENGINE_SPEC_B S14-R-09a:
    a line states one amount and no rate reference). The balance of a journal is ``unbalanced``'s
    (its own problem, 422 ``ledger-unbalanced``)."""
    errors: list[ProblemError] = []
    if kind in JOURNAL_KINDS and currency != functional_currency:
        message = FOREIGN_JOURNAL.format(functional=functional_currency, currency=currency)
        errors.append(_error("kind", message, RULE_FOREIGN))
    obligation_id = payload.obligation_id
    if obligation_id is not None and obligation_id not in obligations:
        errors.append(_error("payload.obligation_id", OBLIGATION_UNKNOWN))
    if kind in SCHEDULE_KINDS and obligation_id is None:
        errors.append(_error("payload.obligation_id", OBLIGATION_REQUIRED))
    if kind in MOVE_KINDS:
        errors += _absent(kind, payload, ("periods", "lines"))
        sent = [
            name for name in ("amount", "ratio", "remaining") if getattr(payload, name) is not None
        ]
        if len(sent) != 1:
            errors.append(_error("payload", ONE_BASIS))
        if payload.amount is not None:
            found = _amount_errors("payload.amount", payload.amount, currency)
            if not found and Decimal(payload.amount.amount) <= 0:
                found = [_error("payload.amount", AMOUNT_POSITIVE)]
            errors += found
        if payload.ratio is not None and not 0 < Decimal(payload.ratio) <= 1:
            errors.append(_error("payload.ratio", RATIO_RANGE))
    elif kind == OVERRIDE:
        errors += _absent(kind, payload, ("amount", "ratio", "remaining", "lines"))
        if not payload.periods:
            errors.append(_error("payload.periods", PERIODS_REQUIRED))
        seen: set[UUID] = set()
        for index, item in enumerate(payload.periods or ()):
            if item.period_id not in periods:
                errors.append(_error(f"payload.periods.{index}.period_id", PERIOD_UNKNOWN))
            elif item.period_id in seen:
                errors.append(_error(f"payload.periods.{index}.period_id", PERIOD_REPEATED))
            seen.add(item.period_id)
            errors += _amount_errors(f"payload.periods.{index}.amount", item.amount, currency)
    else:
        errors += _absent(kind, payload, ("amount", "ratio", "remaining", "periods"))
        lines = payload.lines or ()
        if len(lines) < MIN_LINES:
            errors.append(_error("payload.lines", LINES_REQUIRED))
        for index, line in enumerate(lines):
            where = f"payload.lines.{index}"
            found = _amount_errors(f"{where}.amount_txn", line.amount_txn, currency)
            if not found and Decimal(line.amount_txn.amount) == 0:
                found = [_error(f"{where}.amount_txn", LINE_ZERO)]
            errors += found
            role = line.account_role.value
            if role in REFUSED_ROLES:
                errors.append(_error(f"{where}.account_role", ROLE_REFUSED.format(role=role)))
            for code in sorted(set(line.dimensions) & set(IDENTITY_DIMENSIONS)):
                errors.append(_error(f"{where}.dimensions", DIMENSION_RESERVED.format(code=code)))
            account = accounts.get(line.gl_account_id)
            if account is None:
                errors.append(_error(f"{where}.gl_account_id", ACCOUNT_UNKNOWN))
                continue
            if not account.is_active:
                errors.append(
                    _error(f"{where}.gl_account_id", ACCOUNT_INACTIVE.format(code=account.code))
                )
            if account.entity_ids and entity_id not in account.entity_ids:
                errors.append(
                    _error(
                        f"{where}.gl_account_id",
                        ACCOUNT_OTHER_ENTITY.format(code=account.code, entity=entity_code),
                    )
                )
            carried = {*line.dimensions, "contract", "contract_key"}
            if obligation_id is not None:
                carried.add("obligation_key")
            missing = sorted(account.required_dimensions - carried)
            if missing:
                errors.append(
                    _error(
                        f"{where}.dimensions",
                        DIMENSIONS_MISSING.format(code=account.code, dimensions=", ".join(missing)),
                    )
                )
    return errors


def unbalanced(kind: str, payload: AdjustmentPayloadIn, currency: str) -> Problem | None:
    """422 ``ledger-unbalanced`` when the lines of a journal kind do not sum to 0 (04 §15.2;
    T-SL-05 "lines must balance"), naming debits, credits and their difference."""
    if kind not in JOURNAL_KINDS:
        return None
    amounts = [Decimal(line.amount_txn.amount) for line in payload.lines or ()]
    debit = sum((value for value in amounts if value > 0), Decimal(0))
    credit = -sum((value for value in amounts if value < 0), Decimal(0))
    if debit == credit:
        return None
    detail = UNBALANCED.format(
        debit=_money(debit, currency).amount,
        credit=_money(credit, currency).amount,
        difference=_money(abs(debit - credit), currency).amount,
        currency=currency,
    )
    return Problem("ledger-unbalanced", detail, errors=[_error("payload.lines", detail)])


def stored_payload(kind: str, payload: AdjustmentPayloadIn) -> dict[str, Any]:
    """The jsonb of T-SL-05 ``payload`` for ``kind``: exactly the members the kind carries, ids as
    text and money as API-S-Money."""
    stored: dict[str, Any] = {}
    if payload.obligation_id is not None:
        stored["obligation_id"] = str(payload.obligation_id)
    if kind in MOVE_KINDS:
        if payload.amount is not None:
            stored["amount"] = payload.amount.model_dump(mode="json")
        elif payload.ratio is not None:
            stored["ratio"] = payload.ratio
        else:
            stored["remaining"] = True
    elif kind == OVERRIDE:
        stored["periods"] = [
            {"period_id": str(item.period_id), "amount": item.amount.model_dump(mode="json")}
            for item in payload.periods or ()
        ]
    else:
        stored["lines"] = [
            {
                "account_role": line.account_role.value,
                "gl_account_id": str(line.gl_account_id),
                "amount_txn": line.amount_txn.model_dump(mode="json"),
                "dimensions": dict(sorted(line.dimensions.items())),
            }
            for line in payload.lines or ()
        ]
    return stored


def _validated(kind: str, payload: AdjustmentPayloadIn, facts: _Facts) -> None:
    """Raise the contract, payload and balance problems of an adjustment, in that order."""
    current = facts.contract
    errors: list[ProblemError] = []
    status = _text(current["status"])
    if status not in ADJUSTABLE_CONTRACTS:
        message = NOT_ADJUSTABLE.format(external_id=current["external_id"], status=status)
        errors.append(_error("contract_id", message))
    errors += payload_errors(
        kind,
        payload,
        currency=facts.currency,
        functional_currency=facts.functional_currency,
        entity_id=facts.entity_id,
        entity_code=facts.entity_code,
        obligations=facts.obligations,
        periods=facts.periods,
        accounts=facts.accounts,
    )
    if errors:
        raise _failed(errors)
    refused = unbalanced(kind, payload, facts.currency)
    if refused is not None:
        raise refused


# --- the measured impact (dry run) ---------------------------------------------------------------


def _event(row: Mapping[str, Any], obligations: Mapping[UUID, Mapping[str, Any]]) -> EventIn:
    """The ``MANUAL_ADJUSTMENT_APPLIED`` of ``row``: pending for a dry run, appended at approval."""
    adjustment_id = _uuid(row["id"])
    obligation_id = row["obligation_id"]
    keys = (
        () if obligation_id is None else (str(obligations[_uuid(obligation_id)]["obligation_key"]),)
    )
    return EventIn(
        event_type=ContractEventType.MANUAL_ADJUSTMENT_APPLIED,
        effective_date=row["effective_date"],
        payload=ManualAdjustmentAppliedV1(manual_adjustment_id=adjustment_id),
        obligation_keys=keys,
        manual_adjustment_id=adjustment_id,
    )


def _stored_revenue(session: Session, version_id: Any, obligation_id: UUID) -> dict[str, Decimal]:
    """The obligation's revenue by period key in a stored contract version."""
    if version_id is None:
        return {}
    statement = (
        select(period.c.period_key, func.sum(schedule_line.c.amount))
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
            schedule_line.c.subject_id == obligation_id,
            schedule.c.schedule_kind == REVENUE,
        )
        .group_by(period.c.period_key)
    )
    return {str(key): Decimal(amount) for key, amount in session.execute(statement)}


def _output_revenue(
    output: OutputBundle, book_code: str, subject_key: str, minor: int
) -> dict[str, Decimal]:
    """The obligation's revenue by period key in a dry-run output."""
    book = next((item for item in output.books if item.book_code == book_code), None)
    totals: dict[str, Decimal] = {}
    for line in () if book is None else book.schedules:
        if _text(line.schedule_kind) != REVENUE or line.subject_key != subject_key:
            continue
        totals[line.period_key] = totals.get(line.period_key, Decimal(0)) + minor_to_decimal(
            line.amount, minor
        )
    return totals


def _approved_lines(session: Session, row: Mapping[str, Any]) -> list[ImpactJournalLineOut]:
    """The lines of a journal kind as the approver reads them: the account as approved."""
    currency = str(row["currency"]).strip()
    lines = list((row["payload"] or {}).get("lines") or ())
    ids = sorted({_uuid(line["gl_account_id"]) for line in lines})
    accounts = (
        {
            _uuid(account_id): RefOut(id=account_id, code=str(code), name=str(name))
            for account_id, code, name in session.execute(
                select(gl_account.c.id, gl_account.c.code, gl_account.c.name).where(
                    gl_account.c.id.in_(ids)
                )
            )
        }
        if ids
        else {}
    )
    out: list[ImpactJournalLineOut] = []
    for line in lines:
        amount = Decimal(str(line["amount_txn"]["amount"]))
        out.append(
            ImpactJournalLineOut(
                gl_account=accounts.get(_uuid(line["gl_account_id"])),
                account_role=str(line["account_role"]),
                debit=_money(max(amount, Decimal(0)), currency),
                credit=_money(max(-amount, Decimal(0)), currency),
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class _Measured:
    """The dry run of one adjustment: its API-S-ImpactSummary and its absolute impact in the
    contract currency."""

    summary: ImpactSummaryOut
    impact: Decimal


def _measure(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    current: Mapping[str, Any],
    obligations: Mapping[UUID, Mapping[str, Any]],
) -> _Measured:
    """Compute the group in ``DRY_RUN`` with the adjustment applied (its row is read by the bundle
    builder; nothing is persisted by the run) and measure the adjustment: for a schedule kind the
    sum of the absolute revenue changes of the obligation in the periods the adjustment names; for
    a journal kind the debit total. An engine refusal answers 422 (DG-CMD-04)."""
    session = uow.session
    kind = _text(row["kind"])
    currency = str(row["currency"]).strip()
    book_code = _text(row["book_code"])
    contract_id = _uuid(current["id"])
    try:
        _bundle, output, summary = dry_run_summary(
            session,
            current,
            uow.now,
            [_event(row, obligations)],
            pending_contract_id=contract_id,
            book_code=book_code,
        )
    except EngineError as error:
        raise engine_problem(error) from error
    assert summary is not None  # a dry run with a pending event summarises
    payload = row["payload"] or {}
    if kind in JOURNAL_KINDS:
        lines = _approved_lines(session, row)
        impact = sum((Decimal(line.debit.amount) for line in lines), Decimal(0))
        return _Measured(summary.model_copy(update={"journal_lines": lines}), impact)
    obligation_id = _uuid(row["obligation_id"])
    group_id = _uuid(current["combination_group_id"])
    before_version = bundles.previous_version(session, group_id, book_code)
    # Item PREVIEW-INLINE-SCOPE-1 (04 §16.14 rev 1.319; supervisor ruling R-64 (1)): what the
    # adjustment measures — the amount its request states and routes on — does not depend on who
    # measures it. A schedule line is a row of the entity that PERFORMS; read under the caller's
    # scope, the stored revenue of an obligation another entity performs was nothing, and the
    # impact was the whole period amount. Measured before: a release of 100.00 on such an
    # obligation was stored and routed as 4,890.61 for a preparer of the contracting entity alone.
    with system_entity_scope(session):
        before = _stored_revenue(
            session, None if before_version is None else before_version["id"], obligation_id
        )
    subject = obligation_subject_key(
        str(current["external_id"]), str(obligations[obligation_id]["obligation_key"])
    )
    after = _output_revenue(output, book_code, subject, _minor(currency))
    period_key = session.execute(
        select(period.c.period_key).where(period.c.id == row["period_id"])
    ).scalar_one()
    if kind == OVERRIDE:
        listed = sorted({_uuid(item["period_id"]) for item in payload.get("periods") or ()})
        named = [
            str(key)
            for (key,) in session.execute(
                select(period.c.period_key).where(period.c.id.in_(listed))
            )
        ]
    else:
        named = [str(period_key)]
    impact = sum(
        (abs(after.get(key, Decimal(0)) - before.get(key, Decimal(0))) for key in named),
        Decimal(0),
    )
    return _Measured(summary, impact)


def _spot(session: Session, uow: UnitOfWork, *, base: str, quote: str, on: date) -> Decimal:
    """The pinned spot rate from ``base`` to ``quote`` on ``on`` (S12-R-01; 1 for one currency);
    422 naming the missing rate otherwise."""
    if base == quote:
        return Decimal(1)
    rates = bundles.fx_rate_inputs(session, {base, quote}, uow.now)
    found = spot_basis(rates, base=base, quote=quote, on=on)
    if found.get("rate") is None:
        message = RATE_MISSING.format(base=base, quote=quote, date=on.isoformat())
        raise _failed([_error("effective_date", message, "REQ-FX-006")])
    return Decimal(str(found["rate"]))


def _functional(
    uow: UnitOfWork, impact: Decimal, *, currency: str, functional: str, on: date
) -> Decimal:
    """``impact`` in the entity's functional currency at the spot rate of ``on``, half up."""
    rate = _spot(uow.session, uow, base=currency, quote=functional, on=on)
    return _quantized(impact * rate, functional)


def _routing_flags(
    uow: UnitOfWork, row: Mapping[str, Any], amount_functional: Decimal, *, functional: str
) -> list[str]:
    """The PRD §2.5 routing of a manual adjustment (``quorum.route``) as request flags. The
    absolute amount is compared in USD — the functional amount converted at the spot rate of the
    effective date when the entity's functional currency is not USD. Below USD 10,000.00 one step;
    from it the adjustment needs an attachment (422 ``validation-failed`` naming ``attachments``)
    — a document whose file can still be read (``_supporting_documents``) — and
    ``ABOVE_THRESHOLD`` gives the second step, held by a Controller."""
    session = uow.session
    rate = _spot(session, uow, base=functional, quote=THRESHOLD_CURRENCY, on=row["effective_date"])
    try:
        steps = quorum.route(
            ApprovalSubjectType.MANUAL_ADJUSTMENT,
            amount_functional_abs=_quantized(amount_functional * rate, THRESHOLD_CURRENCY),
            has_attachment=_supporting_documents(session, _uuid(row["id"])) > 0,
        )
    except quorum.AttachmentRequired as refused:
        raise _failed([_error(refused.field, str(refused), refused.rule_id)]) from refused
    return [ABOVE_THRESHOLD] if len(steps) > 1 else []


def _impact_preview(summary: ImpactSummaryOut) -> tuple[dict[str, Any], dict[str, Any]]:
    """The dry run as the ``before`` and ``after`` members of the request's impact preview
    (REQ-PLT-015): revenue by period, RPO and transaction price, and the journal lines."""
    data = summary.model_dump(mode="json")
    revenue = data["revenue_by_period"]
    before = {
        "transaction_price": data["transaction_price_before"],
        "rpo": data["rpo_before"],
        "revenue_by_period": [
            {"period_key": item["period_key"], "amount": item["before"]} for item in revenue
        ],
    }
    after = {
        "transaction_price": data["transaction_price_after"],
        "rpo": data["rpo_after"],
        "revenue_by_period": [
            {"period_key": item["period_key"], "amount": item["after"]} for item in revenue
        ],
        "catch_up_total": data["catch_up_total"],
        "journal_lines": data["journal_lines"],
        "posting_period_key": data["posting_period_key"],
        "origin_period_key": data["origin_period_key"],
    }
    return before, after


# --- create and update ---------------------------------------------------------------------------


def _audited(row: Mapping[str, Any]) -> dict[str, Any]:
    """The authored members of a row for an audit event."""
    return {
        "adjustment_no": str(row["adjustment_no"]),
        "kind": _text(row["kind"]),
        "status": _text(row["status"]),
        "contract_id": str(row["contract_id"]),
        "obligation_id": None if row["obligation_id"] is None else str(row["obligation_id"]),
        "entity_id": str(row["entity_id"]),
        "book_code": _text(row["book_code"]),
        "period_id": str(row["period_id"]),
        "effective_date": row["effective_date"].isoformat(),
        "payload": row["payload"],
        "amount_functional_abs": str(row["amount_functional_abs"]),
        "currency": str(row["currency"]).strip(),
        "reason_code": str(row["reason_code"]),
    }


def _remeasured(
    uow: UnitOfWork, row: Mapping[str, Any], facts: _Facts
) -> tuple[Mapping[str, Any], _Measured]:
    """Measure a DRAFT ``row`` and store its ``amount_functional_abs``; the updated row."""
    measured = _measure(uow, row, facts.contract, facts.obligations)
    amount = _functional(
        uow,
        measured.impact,
        currency=facts.currency,
        functional=facts.functional_currency,
        on=row["effective_date"],
    )
    updated = transitions.apply(
        uow.session,
        OBJECT,
        _uuid(row["id"]),
        to_status=None,
        expected_status=DRAFT,
        set_values={"amount_functional_abs": amount},
    )
    return updated, measured


def create(uow: UnitOfWork, *, body: ManualAdjustmentCreateIn) -> ManualAdjustmentOut:
    """``POST /manual-adjustments`` (201): a DRAFT of a visible contract; the preparer holds
    ``adjustment.create`` for the contracting entity (404 outside it, ruling R-28)."""
    session = uow.session
    current = repo.get_contract(session, body.contract_id)
    entity_id = _uuid(current["contracting_entity_id"])
    require_for_entity(uow.ctx, CREATE_PERMISSION, entity_id)
    facts = _facts(
        session,
        current,
        book=body.book,
        effective_date=body.effective_date,
        payload=body.payload,
    )
    kind = body.kind.value
    _validated(kind, body.payload, facts)
    principal = uow.principal
    adjustment_id = new_id()
    values: dict[str, Any] = {
        "tenant_id": principal.tenant_id,
        "id": adjustment_id,
        "adjustment_no": next_number(uow, SERIES),
        "kind": kind,
        "status": DRAFT,
        "contract_id": _uuid(current["id"]),
        "obligation_id": body.payload.obligation_id,
        "entity_id": entity_id,
        "book_code": facts.book.value,
        "period_id": facts.posting.id,
        "effective_date": body.effective_date,
        "payload": stored_payload(kind, body.payload),
        "amount_functional_abs": Decimal(0),
        "currency": facts.currency,
        "reason_code": body.reason_code.value,
        "memo": body.memo,
        "is_deferred_past_lock": False,
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
        "row_version": 1,
    }
    session.execute(insert(manual_adjustment).values(**values))
    row, _ = _remeasured(uow, _row(session, adjustment_id), facts)
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version="1",
        after=_audited(row),
        contract_id=_uuid(row["contract_id"]),
    )
    return get_adjustment(session, adjustment_id, reader=uow.principal)


def update(
    uow: UnitOfWork,
    *,
    adjustment_id: UUID,
    body: ManualAdjustmentUpdateIn,
    expected_version: int | None,
) -> ManualAdjustmentOut:
    """``PATCH /manual-adjustments/{id}`` (If-Match): the members sent replace the stored ones of
    a DRAFT; a REJECTED adjustment returns to DRAFT with them (revise and resubmit, PRD SM-10).
    Only the adjustment's creator edits it — 403 ``forbidden`` naming the creator for anyone else
    (item ADJ-VOID-REFUSE-1; PRD ERR-71)."""
    session = uow.session
    row, _group_id, current = _locked(uow, adjustment_id)
    entity_id = _uuid(row["entity_id"])
    require_for_entity(uow.ctx, CREATE_PERMISSION, entity_id)
    principal = uow.principal
    if (row["created_by"], _text(row["created_by_kind"])) != (principal.id, principal.kind.value):
        raise _not_creator(session, row)
    if expected_version is not None and int(row["row_version"]) != expected_version:
        raise Problem("precondition-failed")
    status = _text(row["status"])
    if status not in EDITABLE:
        raise _state(NOT_EDITABLE)
    kind = _text(row["kind"])
    sent = body.model_fields_set
    effective_date = (
        body.effective_date
        if "effective_date" in sent and body.effective_date is not None
        else row["effective_date"]
    )
    payload = body.payload if "payload" in sent and body.payload is not None else None
    facts = _facts(
        session,
        current,
        book=BookCode(_text(row["book_code"])),
        effective_date=effective_date,
        payload=payload,
    )
    changes: dict[str, Any] = {"effective_date": effective_date, "period_id": facts.posting.id}
    if payload is not None:
        _validated(kind, payload, facts)
        changes["payload"] = stored_payload(kind, payload)
        changes["obligation_id"] = payload.obligation_id
    if "reason_code" in sent and body.reason_code is not None:
        changes["reason_code"] = body.reason_code.value
    if "memo" in sent and body.memo is not None:
        changes["memo"] = body.memo
    before = _audited(row)
    if status == REJECTED:
        # A draft is editable, so it counts as pending again: an earlier deferral ends (as in
        # ``_to_draft``; REQ-JE-019).
        row = dict(
            transitions.apply(
                session,
                OBJECT,
                adjustment_id,
                to_status=DRAFT,
                expected_status=REJECTED,
                set_values={"is_deferred_past_lock": False, **_bump(uow, row)},
            )
        )
    edited = transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=None,
        expected_status=DRAFT,
        set_values={**changes, **_bump(uow, row)},
    )
    updated, _ = _remeasured(uow, edited, facts)
    uow.audit(
        action=UPDATE_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before=before,
        after=_audited(updated),
        contract_id=_uuid(row["contract_id"]),
    )
    return get_adjustment(session, adjustment_id, reader=uow.principal)


# --- preview (202) -------------------------------------------------------------------------------


def preview(uow: UnitOfWork, *, adjustment_id: UUID) -> JobOut:
    """``POST /manual-adjustments/{id}/preview``: defer the dry run; 202 API-S-Job whose
    ``result.summary`` is API-S-ImpactSummary.

    A preview is asked by who could submit the adjustment (04 §16.10 rev 1.295 "Who may ask
    for a preview"; supervisor ruling R-103 (b) (5)): 403 by name for a caller who does not read
    every entity it is bound to — the group of its contract; rev 1.319: one permission that
    reads an adjustment, for each, where it was the entities of her roles — before the
    adjustment's state is asked, and nothing is deferred."""
    session = uow.session
    row = _row(session, adjustment_id)
    require_for_entity(uow.ctx, CREATE_PERMISSION, _uuid(row["entity_id"]))
    approvals.require_preview_scope(
        uow,
        ApprovalSubjectType.MANUAL_ADJUSTMENT,
        adjustment_id,
        action=PREVIEW_ACTION,
        permission=CREATE_PERMISSION,
    )
    if _text(row["status"]) not in PREVIEWABLE:
        raise _state(NOT_PREVIEWABLE)
    deferred = uow.defer(
        JobKind.CONTRACT_COMPUTE,
        {"mode": ADJUSTMENT_PREVIEW_MODE, "manual_adjustment_id": str(adjustment_id)},
        subject_type=PREVIEW_JOB_SUBJECT,
        subject_id=_uuid(row["contract_id"]),
    )
    job_row = session.execute(select(*JOB_COLUMNS).where(job.c.id == deferred["id"])).mappings()
    (item,) = job_outs(session, [dict(job_row.one())])
    return item


def run_preview(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``CONTRACT_COMPUTE`` in mode ``ADJUSTMENT_PREVIEW``: the dry run of one adjustment; writes
    nothing."""
    adjustment_id = UUID(str(params["manual_adjustment_id"]))
    with ctx.unit_of_work() as uow:
        session = uow.session
        row = _row(session, adjustment_id)
        current = repo.get_contract(session, _uuid(row["contract_id"]))
        obligations = {_uuid(item["id"]): item for item in repo.obligations(session, current["id"])}
        measured = _measure(uow, row, current, obligations)
        uow.discard()
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": HREF.format(adjustment_id=adjustment_id),
            "counts": {"events": 1},
            "summary": measured.summary.model_dump(mode="json"),
        },
    )


# --- submit, withdraw, discard, defer ------------------------------------------------------------


def _pending_request(session: Session, row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The adjustment's own PENDING request, or None."""
    if row["approval_request_id"] is None:
        return None
    found = (
        session.execute(
            select(
                approval_request.c.id, approval_request.c.status, approval_request.c.flags
            ).where(approval_request.c.id == row["approval_request_id"])
        )
        .mappings()
        .one_or_none()
    )
    if found is None or _text(found["status"]) != PENDING:
        return None
    return dict(found)


def _supporting_documents(session: Session, adjustment_id: UUID) -> int:
    """The live attachments of the adjustment whose file can still be read: the documents the
    threshold rule counts (04 T-PLT-29 "A document a rule asks for"; rulings R-119 (g), R-120
    (g)). An attachment row outlives the shred of its file and supports nothing then. The files'
    rows are locked to the end of the transaction, so that this command and a shred of one of
    them see each other (``files.store.lock_readable``)."""
    file_ids = [
        _uuid(file_id)
        for file_id in session.scalars(
            select(file_attachment.c.file_object_id).where(
                file_attachment.c.subject_type == OBJECT,
                file_attachment.c.subject_id == adjustment_id,
                file_attachment.c.voided_at.is_(None),
            )
        )
    ]
    readable = lock_readable(session, file_ids)
    return sum(1 for file_id in file_ids if file_id in readable)


def _period_names(session: Session, row: Mapping[str, Any]) -> tuple[str, str]:
    """(period name, entity code) of an adjustment, for copy."""
    found = session.execute(
        select(period.c.name, legal_entity.c.code)
        .select_from(period.join(legal_entity, legal_entity.c.tenant_id == period.c.tenant_id))
        .where(period.c.id == row["period_id"], legal_entity.c.id == row["entity_id"])
    ).one()
    return str(found[0]), str(found[1])


def _submitter(uow: UnitOfWork, row: Mapping[str, Any]) -> PeriodState | None:
    """Authorise the submitter of ``row`` and return its period's state (None when the entity
    keeps no state of the book for the period): ``adjustment.create`` for the entity, or, in a
    ``closing`` period, ``period.lock`` in its place (PRD BR-CLS-04; REQ-CLS-003; CTL-015)."""
    entity_id = _uuid(row["entity_id"])
    try:
        state: PeriodState | None = period_state(
            uow.session,
            entity_id=entity_id,
            book_code=BookCode(_text(row["book_code"])),
            period_id=_uuid(row["period_id"]),
        )
    except LookupError:
        state = None
    permission = LOCK_PERMISSION if state is PeriodState.CLOSING else CREATE_PERMISSION
    _authorize(
        uow,
        permission,
        entity_id,
        _uuid(row["id"]),
        action=SUBMIT_ACTION,
        contract_id=_uuid(row["contract_id"]),
    )
    return state


def _holds(uow: UnitOfWork, permission: str, entity_id: UUID) -> bool:
    scope = uow.principal.permission_scopes.get(permission)
    return scope is not None and (scope == "*" or entity_id in scope)


def _requester(uow: UnitOfWork, row: Mapping[str, Any], *, action: str) -> None:
    """The guard of ``withdraw`` and ``request-defer-past-lock``, which post nothing to the period:
    ``adjustment.create`` for the entity, or ``period.lock`` for it — the permission the submitter
    of a ``closing`` period holds (BR-CLS-04), who withdraws or defers what they submitted."""
    entity_id = _uuid(row["entity_id"])
    lock_only = not _holds(uow, CREATE_PERMISSION, entity_id) and _holds(
        uow, LOCK_PERMISSION, entity_id
    )
    permission = LOCK_PERMISSION if lock_only else CREATE_PERMISSION
    _authorize(
        uow,
        permission,
        entity_id,
        _uuid(row["id"]),
        action=action,
        contract_id=_uuid(row["contract_id"]),
    )


def _routed(
    uow: UnitOfWork,
    row: Mapping[str, Any],
    *,
    summary: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    retained: tuple[UUID, str] | None,
    flags: Sequence[str],
    comment: str | None,
) -> Mapping[str, Any]:
    """Open a ``MANUAL_ADJUSTMENT`` request of ``row`` with ``flags``; never auto-approved
    (PRD §2.5 names no rule; BR-CLS-06; REQ-PLT-016)."""
    adjustment_id = _uuid(row["id"])
    decision = approvals.route_submission(
        uow,
        ApprovalSubjectType.MANUAL_ADJUSTMENT,
        adjustment_id,
        auto_approval=False,
        flags=flags,
    )
    return approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.MANUAL_ADJUSTMENT,
        subject_id=adjustment_id,
        summary=summary,
        impact_preview=approvals.ImpactPreview(
            before=before,
            after=after,
            retained_file_id=None if retained is None else retained[0],
            retained_sha256=None if retained is None else retained[1],
        ),
        comment=comment,
        reason_code=str(row["reason_code"]),
        auto_approval=False,
        routing_decision=decision,
    )


def _summary(session: Session, row: Mapping[str, Any], verb: str) -> str:
    external_id = session.execute(
        select(contract.c.external_id).where(contract.c.id == row["contract_id"])
    ).scalar_one()
    kind = _text(row["kind"]).replace("_", " ").lower()
    return f"{verb} {kind} {row['adjustment_no']} of {external_id}"


def _facts_of(session: Session, row: Mapping[str, Any]) -> _Facts:
    current = repo.get_contract(session, _uuid(row["contract_id"]))
    return _facts(
        session,
        current,
        book=BookCode(_text(row["book_code"])),
        effective_date=row["effective_date"],
        payload=None,
    )


def submit(
    uow: UnitOfWork, *, adjustment_id: UUID, body: ManualAdjustmentSubmitIn
) -> ManualAdjustmentOut:
    """``POST /manual-adjustments/{id}/submit``: measure, preview, hash and route a DRAFT — or
    route again for posting a SUBMITTED adjustment that has no pending request (after a decision
    on its deferral). A resubmission passes through DRAFT, so it is measured, previewed and hashed
    as a first submission is; an approved deferral stands, and lets the adjustment of a period
    closed since be routed (its approval posts late, with the period as origin)."""
    session = uow.session
    row, _group_id, current = _locked(uow, adjustment_id)
    state = _submitter(uow, row)
    status = _text(row["status"])
    resubmitted = status == SUBMITTED and _pending_request(session, row) is None
    if status != DRAFT and not resubmitted:
        raise _state(NOT_SUBMITTABLE)
    entity_id = _uuid(row["entity_id"])
    book = BookCode(_text(row["book_code"]))
    name, entity_code = _period_names(session, row)
    postable = state in (PeriodState.OPEN, PeriodState.CLOSING, PeriodState.REOPENED)
    if not postable and not (resubmitted and bool(row["is_deferred_past_lock"])):
        detail = PERIOD_CLOSED.format(period=name, entity=entity_code, book=book.value)
        raise Problem("period-closed", detail, code="EREV-LED-003")
    if resubmitted:
        row = dict(
            transitions.apply(
                session,
                OBJECT,
                adjustment_id,
                to_status=DRAFT,
                expected_status=SUBMITTED,
                set_values=_bump(uow, row),
            )
        )
    obligations = {_uuid(item["id"]): item for item in repo.obligations(session, current["id"])}
    functional = str(
        session.execute(
            select(legal_entity.c.functional_currency).where(legal_entity.c.id == entity_id)
        ).scalar_one()
    ).strip()
    currency = str(row["currency"]).strip()
    measured = _measure(uow, row, current, obligations)
    amount = _functional(
        uow,
        measured.impact,
        currency=currency,
        functional=functional,
        on=row["effective_date"],
    )
    flags = _routing_flags(uow, row, amount, functional=functional)
    before, after = _impact_preview(measured.summary)
    stored = previews.store_preview(uow, before=before, after=after)
    retained = (_uuid(stored["id"]), str(stored["sha256"]))
    transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=None,
        expected_status=DRAFT,
        set_values={"amount_functional_abs": amount, "impact_preview_file_id": retained[0]},
    )
    digest = sha256_hex(manual_adjustment_content(session, adjustment_id))
    row = dict(
        transitions.apply(
            session,
            OBJECT,
            adjustment_id,
            to_status=SUBMITTED,
            expected_status=DRAFT,
            set_values={"content_sha256": digest, **_bump(uow, row)},
        )
    )
    request = _routed(
        uow,
        row,
        summary=_summary(session, row, "Approve"),
        before=before,
        after=after,
        retained=retained,
        flags=flags,
        comment=body.comment,
    )
    request_id = _uuid(request["id"])
    updated = transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=None,
        expected_status=SUBMITTED,
        set_values={"approval_request_id": request_id, **_bump(uow, row)},
    )
    uow.audit(
        action=SUBMIT_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before={"status": status},
        after={
            "status": SUBMITTED,
            "approval_request_id": str(request_id),
            "amount_functional_abs": str(amount),
            "flags": flags,
            "content_sha256": updated["content_sha256"],
            "period_state": None if state is None else state.value,
            "is_deferred_past_lock": bool(updated["is_deferred_past_lock"]),
        },
        comment=body.comment,
        approval_request_id=request_id,
        contract_id=_uuid(row["contract_id"]),
    )
    return get_adjustment(session, adjustment_id, reader=uow.principal)


def _to_draft(
    uow: UnitOfWork, row: Mapping[str, Any], *, approval_request_id: UUID | None
) -> Mapping[str, Any]:
    """SUBMITTED → DRAFT: the request withdrawn or voided as stale (PRD SM-10). A deferral does
    not outlive it — a draft is editable, so it counts as pending again (REQ-JE-019)."""
    adjustment_id = _uuid(row["id"])
    updated = transitions.apply(
        uow.session,
        OBJECT,
        adjustment_id,
        to_status=DRAFT,
        expected_status=SUBMITTED,
        set_values={"is_deferred_past_lock": False, **_bump(uow, row)},
    )
    uow.audit(
        action=RETURN_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before={
            "status": SUBMITTED,
            "is_deferred_past_lock": bool(row["is_deferred_past_lock"]),
        },
        after={"status": DRAFT, "is_deferred_past_lock": False},
        approval_request_id=approval_request_id,
        contract_id=_uuid(row["contract_id"]),
    )
    return updated


def withdraw(
    uow: UnitOfWork, *, adjustment_id: UUID, body: ManualAdjustmentWithdrawIn
) -> ManualAdjustmentOut:
    """``POST /manual-adjustments/{id}/withdraw``: the preparer withdraws the pending request
    (``on_voided`` returns the adjustment to DRAFT); a SUBMITTED adjustment without a pending
    request returns to DRAFT directly."""
    session = uow.session
    row, _group_id, _current = _locked(uow, adjustment_id)
    _requester(uow, row, action=WITHDRAW_ACTION)
    if _text(row["status"]) != SUBMITTED:
        raise _state(NOT_WITHDRAWABLE)
    pending = _pending_request(session, row)
    if pending is None:
        _to_draft(uow, row, approval_request_id=None)
    else:
        approvals.withdraw(
            uow,
            approval_request_id=_uuid(pending["id"]),
            comment=body.comment,
            through_subject=True,
        )
    uow.audit(
        action=WITHDRAW_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        before={"status": SUBMITTED},
        after={
            "status": DRAFT,
            "approval_request_id": None if pending is None else str(pending["id"]),
        },
        comment=body.comment,
        contract_id=_uuid(row["contract_id"]),
    )
    return get_adjustment(session, adjustment_id, reader=uow.principal)


def discard(
    uow: UnitOfWork, *, adjustment_id: UUID, body: ManualAdjustmentDiscardIn
) -> ManualAdjustmentOut:
    """``POST /manual-adjustments/{id}/discard``: a DRAFT becomes VOIDED with the reason (PRD
    SM-10; BR-PLT-08), so a mistaken draft stops counting as pending."""
    session = uow.session
    row, _group_id, _current = _locked(uow, adjustment_id)
    require_for_entity(uow.ctx, CREATE_PERMISSION, _uuid(row["entity_id"]))
    if _text(row["status"]) != DRAFT:
        raise _state(NOT_DISCARDABLE)
    updated = transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=VOIDED,
        expected_status=DRAFT,
        set_values=_bump(uow, row),
    )
    uow.audit(
        action=DISCARD_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before={"status": DRAFT},
        after={"status": VOIDED},
        comment=body.reason,
        contract_id=_uuid(row["contract_id"]),
    )
    return get_adjustment(session, adjustment_id, reader=uow.principal)


def _stored_preview(uow: UnitOfWork, row: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """The ``{before, after}`` document the adjustment retained at submission and its hash."""
    file_id = _uuid(row["impact_preview_file_id"])
    document = previews.read_preview(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    sha256 = uow.session.execute(
        select(file_object.c.sha256).where(file_object.c.id == file_id)
    ).scalar_one()
    return document, str(sha256)


def request_defer_past_lock(
    uow: UnitOfWork, *, adjustment_id: UUID, body: ManualAdjustmentDeferIn
) -> ManualAdjustmentOut:
    """``POST /manual-adjustments/{id}/request-defer-past-lock`` (REQ-JE-019; ruling R-51 (c)): the
    pending posting request of a SUBMITTED adjustment is replaced by a request flagged
    ``DEFER_PAST_LOCK`` on the same routing rows; its approval marks the adjustment deferred."""
    session = uow.session
    row, _group_id, _current = _locked(uow, adjustment_id)
    _requester(uow, row, action=DEFER_REQUEST_ACTION)
    if _text(row["status"]) != SUBMITTED or bool(row["is_deferred_past_lock"]):
        raise _state(NOT_DEFERRABLE)
    pending = _pending_request(session, row)
    if pending is not None and DEFER_PAST_LOCK in (pending["flags"] or ()):
        raise _state(DEFERRAL_PENDING)
    replaced: UUID | None = None
    if pending is not None:
        # Detach first: ``on_voided`` returns an adjustment to DRAFT only for ITS request.
        row = dict(
            transitions.apply(
                session,
                OBJECT,
                adjustment_id,
                to_status=None,
                expected_status=SUBMITTED,
                set_values={"approval_request_id": None, **_bump(uow, row)},
            )
        )
        approvals.void_subject(
            uow,
            subject_type=ApprovalSubjectType.MANUAL_ADJUSTMENT,
            subject_id=adjustment_id,
            comment=REPLACED_COMMENT,
        )
        replaced = _uuid(pending["id"])
    document, sha256 = _stored_preview(uow, row)
    entity_id = _uuid(row["entity_id"])
    functional = str(
        session.execute(
            select(legal_entity.c.functional_currency).where(legal_entity.c.id == entity_id)
        ).scalar_one()
    ).strip()
    # The same routing rows as the posting request (ruling R-51 (c)).
    flags = [
        DEFER_PAST_LOCK,
        *_routing_flags(uow, row, Decimal(row["amount_functional_abs"]), functional=functional),
    ]
    request = _routed(
        uow,
        row,
        summary=_summary(session, row, "Defer past lock:"),
        before=document["before"],
        after=document["after"],
        retained=(_uuid(row["impact_preview_file_id"]), sha256),
        flags=sorted(flags),
        comment=body.comment,
    )
    request_id = _uuid(request["id"])
    updated = transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=None,
        expected_status=SUBMITTED,
        set_values={"approval_request_id": request_id, **_bump(uow, row)},
    )
    uow.audit(
        action=DEFER_REQUEST_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before={"approval_request_id": None if replaced is None else str(replaced)},
        after={"approval_request_id": str(request_id), "flags": sorted(flags)},
        comment=body.comment,
        approval_request_id=request_id,
        contract_id=_uuid(row["contract_id"]),
    )
    return get_adjustment(session, adjustment_id, reader=uow.principal)


# --- lifecycle (the approval handler of subject MANUAL_ADJUSTMENT) -------------------------------


def _system_unit(uow: UnitOfWork) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, stamped with the caller's instant."""
    ctx = dataclasses.replace(uow.ctx, principal=system_principal(uow.principal.tenant_id))
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _is_deferral(session: Session, approval_request_id: UUID) -> bool:
    flags = session.execute(
        select(approval_request.c.flags).where(approval_request.c.id == approval_request_id)
    ).scalar_one_or_none()
    return DEFER_PAST_LOCK in (flags or ())


def _placement(session: Session, row: Mapping[str, Any]) -> tuple[PeriodRef, PeriodRef | None]:
    """(posting period, origin period) of lines posted now: the adjustment period while it is
    postable, else the first later postable period with the adjustment period as origin — the
    engine's late assignment of a target in a closed period (S08-R-08)."""
    end_date = session.execute(
        select(period.c.end_date).where(period.c.id == row["period_id"])
    ).scalar_one()
    return posting_period(
        session,
        entity_id=_uuid(row["entity_id"]),
        book_code=BookCode(_text(row["book_code"])),
        effective_date=end_date,
    )


def _ledger_lines(
    session: Session,
    row: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    event_id: UUID,
) -> list[dict[str, Any]]:
    """The T-SL-04 values of the approved lines: one balanced entry of kind ``MANUAL_ADJUSTMENT``,
    each line on its approved role and account, with the S14-R-13 identity dimensions."""
    posting, origin = _placement(session, row)
    currency = str(row["currency"]).strip()
    external_id = str(current["external_id"])
    group_code = session.execute(
        select(combination_group.c.code).where(
            combination_group.c.id == current["combination_group_id"]
        )
    ).scalar_one()
    identity: dict[str, str] = {"contract": str(group_code), "contract_key": external_id}
    obligation_id = row["obligation_id"]
    legacy_key: str | None = None
    if obligation_id is not None:
        found = session.execute(
            select(obligation.c.obligation_key, obligation.c.legacy_record_key, product.c.code)
            .select_from(
                obligation.outerjoin(
                    product,
                    and_(
                        product.c.tenant_id == obligation.c.tenant_id,
                        product.c.id == obligation.c.product_id,
                    ),
                )
            )
            .where(obligation.c.id == obligation_id)
        ).one()
        identity["obligation_key"] = str(found[0])
        legacy_key = None if found[1] is None else str(found[1])
        if found[2] is not None:
            identity["product"] = str(found[2])
    # 04 T-SL-04 ``subject_key`` (rev 1.282; supervisor ruling R-11 as amended): the subject stage
    # 14 gives the adjustment's role target (ENGINE_SPEC_B S14-R-09a; ``s14_posting.manual``) —
    # the obligation's, else the contract's in the adjustment's entity — built with the engine's
    # own key functions, so the posted amount is read back under the key it has a target for.
    if obligation_id is None:
        entity_code = session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == row["entity_id"])
        ).scalar_one()
        subject_key = contract_entity_subject_key(external_id, str(entity_code))
    else:
        subject_key = obligation_subject_key(external_id, identity["obligation_key"])
    lines: list[dict[str, Any]] = []
    for line in (row["payload"] or {}).get("lines") or ():
        amount = Decimal(str(line["amount_txn"]["amount"]))
        dimensions = dict(sorted({**dict(line.get("dimensions") or {}), **identity}.items()))
        role = str(line["account_role"])
        lines.append(
            {
                "period_end_date": posting.end_date,
                "entity_id": _uuid(row["entity_id"]),
                "period_id": posting.id,
                "origin_period_id": None if origin is None else origin.id,
                "effective_date": row["effective_date"],
                "entry_no": 1,
                "entry_kind": ENTRY_KIND,
                "subject_key": subject_key,
                "account_role": role,
                "clearing_purpose": None,
                "gl_account_id": _uuid(line["gl_account_id"]),
                "dimensions": dimensions,
                "dimension_set_sha256": subledger.dimension_set_sha256(dimensions),
                "txn_currency": currency,
                "amount_txn": amount,
                "functional_currency": currency,
                "amount_functional": amount,
                "contract_id": _uuid(row["contract_id"]),
                "obligation_id": obligation_id,
                "contract_event_id": event_id,
                "reason_code": None if origin is None else LATE_REASON,
                "legacy_key": legacy_key
                if role == AccountRole.REVENUE.value and legacy_key is not None
                else external_id,
                "description": f"Manual adjustment {row['adjustment_no']}",
            }
        )
    return lines


def _approved(uow: UnitOfWork, adjustment_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``MANUAL_ADJUSTMENT`` (module docstring; DG-CMD-09)."""
    session = uow.session
    # DG-KRN-DB-08: group row first, then the contract row, then the adjustment; then the basis
    # under those locks (an append to the contract changes what the approver reviewed).
    row, group_id, current = _locked(uow, adjustment_id)
    if _text(row["status"]) != SUBMITTED:
        raise LookupError(f"manual adjustment {adjustment_id} is not submitted")
    # The basis names the documents that can still be read: their files' rows are locked before
    # it is read again, so an approved shred of one and this decision see each other (04 T-PLT-29
    # "A document a rule asks for"; ruling R-120 (g)).
    _supporting_documents(session, adjustment_id)
    approvals.assert_fresh_basis(uow, approval_request_id)
    if _is_deferral(session, approval_request_id):
        updated = transitions.apply(
            session,
            OBJECT,
            adjustment_id,
            to_status=None,
            expected_status=SUBMITTED,
            set_values={"is_deferred_past_lock": True, **_bump(uow, row)},
        )
        uow.audit(
            action=DEFER_ACTION,
            object_type=OBJECT,
            object_id=adjustment_id,
            object_version=str(updated["row_version"]),
            before={"is_deferred_past_lock": False},
            after={"is_deferred_past_lock": True},
            approval_request_id=approval_request_id,
            contract_id=_uuid(row["contract_id"]),
        )
        return
    row = dict(
        transitions.apply(
            session,
            OBJECT,
            adjustment_id,
            to_status=APPROVED,
            expected_status=SUBMITTED,
            set_values={"approval_request_id": approval_request_id, **_bump(uow, row)},
        )
    )
    obligations = {_uuid(item["id"]): item for item in repo.obligations(session, current["id"])}
    system = _system_unit(uow)
    applied = dataclasses.replace(_event(row, obligations), approval_request_id=approval_request_id)
    (appended,) = append_events(
        system,
        contract_id=_uuid(current["id"]),
        expected_stream_version=int(current["head_stream_version"]),
        events=[applied],
        origin="SYSTEM",
    )
    for audit_event in system.drain_audit_events():
        uow.buffer_audit_event(audit_event)
    event_id = _uuid(appended["id"])
    posted: dict[str, Any] = {"applied_event_id": event_id}
    kind = _text(row["kind"])
    if kind in JOURNAL_KINDS:
        # DG-KRN-DB-08 (1c) rev 1.218 (finding F4): the manual posting takes the book's chain head
        # and the recomputation below reads the window, so the window's rows are held first.
        period_ends.hold_windows(uow, [group_id])
        posting = subledger.post(
            uow,
            book_code=_text(row["book_code"]),
            posting_kind=SubledgerPostingKind.MANUAL_ADJUSTMENT,
            idempotency_key=subledger.adjustment_key(adjustment_id),
            description=f"Manual adjustment {row['adjustment_no']} of {current['external_id']}",
            lines=_ledger_lines(session, row, current, event_id=event_id),
            combination_group_id=group_id,
            manual_adjustment_id=adjustment_id,
            require_subject_key=True,
        )
        posted["subledger_posting_id"] = posting.posting_id
    updated = transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=POSTED,
        expected_status=APPROVED,
        set_values={**posted, **_bump(uow, row)},
    )
    uow.audit(
        action=POST_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before={"status": SUBMITTED},
        after={"status": POSTED, **{key: str(value) for key, value in posted.items()}},
        approval_request_id=approval_request_id,
        contract_id=_uuid(row["contract_id"]),
    )
    try:
        computation.recompute(uow, group_id, trigger=ComputationTrigger.COMMAND)
    except EngineError as error:
        raise engine_problem(error) from error


def _rejected(uow: UnitOfWork, adjustment_id: UUID, approval_request_id: UUID) -> None:
    """``on_rejected``: a rejected posting request rejects the adjustment, which changes nothing
    else; a rejected deferral leaves it SUBMITTED, not deferred and counted."""
    session = uow.session
    row, _group_id, _current = _locked(uow, adjustment_id)
    if _text(row["status"]) != SUBMITTED or row["approval_request_id"] != approval_request_id:
        return
    if _is_deferral(session, approval_request_id):
        uow.audit(
            action=DEFER_REJECT_ACTION,
            object_type=OBJECT,
            object_id=adjustment_id,
            before={"is_deferred_past_lock": False},
            after={"is_deferred_past_lock": False, "status": SUBMITTED},
            approval_request_id=approval_request_id,
            contract_id=_uuid(row["contract_id"]),
        )
        return
    updated = transitions.apply(
        session,
        OBJECT,
        adjustment_id,
        to_status=REJECTED,
        expected_status=SUBMITTED,
        set_values=_bump(uow, row),
    )
    uow.audit(
        action=REJECT_ACTION,
        object_type=OBJECT,
        object_id=adjustment_id,
        object_version=str(updated["row_version"]),
        before={"status": SUBMITTED},
        after={"status": REJECTED},
        approval_request_id=approval_request_id,
        contract_id=_uuid(row["contract_id"]),
    )


def _voided(uow: UnitOfWork, adjustment_id: UUID, approval_request_id: UUID) -> None:
    """``on_voided``: the adjustment's own request withdrawn or voided as stale returns it to
    DRAFT; a request the adjustment no longer names (replaced by a deferral request) changes
    nothing."""
    row, _group_id, _current = _locked(uow, adjustment_id)
    if _text(row["status"]) != SUBMITTED or row["approval_request_id"] != approval_request_id:
        return
    _to_draft(uow, row, approval_request_id=approval_request_id)


register_lifecycle(
    ApprovalSubjectType.MANUAL_ADJUSTMENT,
    SubjectLifecycle(on_approved=_approved, on_rejected=_rejected, on_voided=_voided),
)


# --- reads ---------------------------------------------------------------------------------------

_COLUMNS: Final = (
    *manual_adjustment.c,
    contract.c.external_id.label("contract_external_id"),
    contract.c.contract_no,
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.name.label("entity_name"),
    legal_entity.c.functional_currency,
    period.c.period_key,
    period.c.name.label("period_name"),
    period.c.start_date,
    period.c.end_date,
)


def adjustments_statement(
    *,
    entities: Sequence[str] = (),
    book: BookCode | None = None,
    period_key: str | None = None,
) -> Select[Any]:
    """Adjustments with their contract, entity and period; the route adds its list filters."""
    tenant = manual_adjustment.c.tenant_id
    joined = (
        manual_adjustment.join(
            contract,
            and_(contract.c.tenant_id == tenant, contract.c.id == manual_adjustment.c.contract_id),
        )
        .join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == tenant,
                legal_entity.c.id == manual_adjustment.c.entity_id,
            ),
        )
        .join(
            period, and_(period.c.tenant_id == tenant, period.c.id == manual_adjustment.c.period_id)
        )
    )
    statement = select(*_COLUMNS).select_from(joined)
    if entities:
        statement = statement.where(legal_entity.c.code.in_(list(entities)))
    if book is not None:
        statement = statement.where(manual_adjustment.c.book_code == book.value)
    if period_key is not None:
        statement = statement.where(period.c.period_key == period_key)
    return statement


def adjustment_outs(
    session: Session, rows: Sequence[Mapping[str, Any]], *, reader: Principal
) -> list[ManualAdjustmentOut]:
    """API-S-ManualAdjustment of each ``adjustments_statement`` row, as ``reader`` is answered
    it: the preview an adjustment retains is the dry run of its contract's whole group, so its
    file id is answered to who reads that document and withheld by name from every other
    reader of the row (04 §16.10 "Who reads a stored preview", rev 1.300; item
    MOD-PREVIEW-READ-SCOPE-1; ``file_access.stored_preview_readable``)."""
    ids = [_uuid(row["id"]) for row in rows]
    attachments: dict[UUID, int] = {}
    requests: dict[UUID, Mapping[str, Any]] = {}
    keys: dict[UUID, str] = {}
    if ids:
        for subject_id, count in session.execute(
            select(file_attachment.c.subject_id, func.count())
            .where(
                file_attachment.c.subject_type == OBJECT,
                file_attachment.c.subject_id.in_(ids),
                file_attachment.c.voided_at.is_(None),
            )
            .group_by(file_attachment.c.subject_id)
        ):
            attachments[_uuid(subject_id)] = int(count)
        request_ids = sorted(
            {_uuid(row["approval_request_id"]) for row in rows if row["approval_request_id"]}
        )
        if request_ids:
            for found in session.execute(
                select(
                    approval_request.c.id, approval_request.c.status, approval_request.c.flags
                ).where(approval_request.c.id.in_(request_ids))
            ).mappings():
                requests[_uuid(found["id"])] = dict(found)
        obligation_ids = sorted(
            {_uuid(row["obligation_id"]) for row in rows if row["obligation_id"]}
        )
        if obligation_ids:
            for obligation_id, key in session.execute(
                select(obligation.c.id, obligation.c.obligation_key).where(
                    obligation.c.id.in_(obligation_ids)
                )
            ):
                keys[_uuid(obligation_id)] = str(key)
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    outs: list[ManualAdjustmentOut] = []
    for row in rows:
        adjustment_id = _uuid(row["id"])
        retained = row["impact_preview_file_id"]
        withheld = retained is not None and not file_access.stored_preview_readable(
            session, reader, ApprovalSubjectType.MANUAL_ADJUSTMENT, adjustment_id
        )
        request = (
            None
            if row["approval_request_id"] is None
            else requests.get(_uuid(row["approval_request_id"]))
        )
        pending = None
        if request is not None and _text(request["status"]) == PENDING:
            deferral = DEFER_PAST_LOCK in (request["flags"] or ())
            pending = {
                "id": request["id"],
                "purpose": "DEFER_PAST_LOCK" if deferral else "POSTING",
            }
        obligation_id = row["obligation_id"]
        functional = str(row["functional_currency"]).strip()
        outs.append(
            ManualAdjustmentOut.model_validate(
                {
                    "id": adjustment_id,
                    "adjustment_no": row["adjustment_no"],
                    "kind": _text(row["kind"]),
                    "status": _text(row["status"]),
                    "contract": {
                        "id": row["contract_id"],
                        "external_id": row["contract_external_id"],
                        "contract_no": row["contract_no"],
                    },
                    "obligation": None
                    if obligation_id is None
                    else {
                        "id": obligation_id,
                        "obligation_key": keys.get(_uuid(obligation_id), ""),
                    },
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
                    "effective_date": row["effective_date"],
                    "payload": row["payload"],
                    "amount_functional_abs": _money(
                        Decimal(row["amount_functional_abs"]), functional
                    ),
                    "currency": str(row["currency"]).strip(),
                    "reason_code": row["reason_code"],
                    "memo": row["memo"],
                    "impact_preview_file_id": None if withheld else retained,
                    "impact_preview_withheld": withheld,
                    "content_sha256": None
                    if row["content_sha256"] is None
                    else str(row["content_sha256"]).strip(),
                    "approval_request_id": row["approval_request_id"],
                    "pending_request": pending,
                    "applied_event_id": row["applied_event_id"],
                    "subledger_posting_id": row["subledger_posting_id"],
                    "is_deferred_past_lock": bool(row["is_deferred_past_lock"]),
                    "attachment_count": attachments.get(adjustment_id, 0),
                    "created_by": approval_queries.actor(
                        row["created_by"], _text(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "row_version": int(row["row_version"]),
                }
            )
        )
    return outs


def get_adjustment(
    session: Session, adjustment_id: UUID, *, reader: Principal
) -> ManualAdjustmentOut:
    """API-S-ManualAdjustment of one visible adjustment as ``reader`` is answered it; 404
    otherwise."""
    rows = session.execute(
        adjustments_statement().where(manual_adjustment.c.id == adjustment_id)
    ).mappings()
    found = [dict(row) for row in rows]
    if not found:
        raise Problem("not-found")
    return adjustment_outs(session, found, reader=reader)[0]
