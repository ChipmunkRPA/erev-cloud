"""Soft close and close checklist commands (PRD §5.2 SM-07, §5.3 BR-CLS-01, BR-CLS-04, §2.5 routing
row ``EXCEPTION_WAIVER``; 04 §16.8 "Period commands", T-REF-06, T-REF-07, T-CLS-02, T-CLS-03,
T-CLS-08, table 3.4-R, DB-07, DB-10; dev-guide DG-CMD-01 to DG-CMD-08; BUILD_SPEC CLO-3, CLO-4,
BS4-D-06, BS4-D-07).

``start_close`` moves ``open`` or ``reopened`` to ``closing``; ``cancel_close`` moves ``closing``
back to ``open`` with a reason of the table 3.4-R subset. Each command locks the state, checks its
``row_version`` through ``check_version`` (API-C-08), writes one ``period_state_transition`` with
the actor, the comment and the UTC time, updates the ``period_state`` projection in the same
transaction (DB-07) and writes one audit event (DG-CMD-06).

``materialise_checklist`` brings the checklist items of a period up to date for a reader, without
audit events but for the lapse of a waiver its gate has outgrown (``gates.materialise_for_view``,
``gates._store``; 04 T-CLS-03 rev 1.305); ``run_period_monitors`` runs the data-quality
monitors before a period command evaluates;
``sign_checklist_item`` signs a manual close task as PREPARER in an MFA-verified session;
``waive_checklist_item`` opens an ``EXCEPTION_WAIVER`` request for an item that has not passed, and
approval sets it WAIVED. ``create_close_task`` and ``update_close_task`` maintain the tenant's close
tasks (T-CLS-02).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, and_, func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.auth import mfa
from erev_api.auth.dependencies import require_for_entity
from erev_api.controls.evidence import ControlRefusal, RunRefType, validate_execution
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    app_user,
    approval_request,
    audit_chain_head,
    book,
    close_checklist_item,
    close_checklist_template,
    entity_book,
    ledger_chain_head,
    legal_entity,
    period,
    period_lock,
    period_reopen_basis,
    period_state,
    period_state_transition,
    reconciliation,
    role,
    signoff,
)
from erev_api.domain.close import (
    certification,
    close_runs,
    dependencies,
    freeze,
    gates,
    monitors,
    period_machine,
    rate_changes,
    relock_diff,
    reopen_judgements,
    snapshots,
)
from erev_api.domain.close import queries as close_queries
from erev_api.domain.reference import period_redirty_job
from erev_api.domain.reference import periods as period_rules
from erev_api.domain.reference import queries as reference_queries
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalSubjectType,
    BookCode,
    ChecklistGateKind,
    ChecklistStatus,
    ControlResult,
    LockKind,
    NotificationKind,
    PeriodState,
    ReasonCode,
    ReconciliationStatus,
    SignoffRole,
)
from erev_api.events.notifications import notify, role_holders
from erev_api.periods import POSTABLE_STATES, followed_book, lock_kind
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.close import (
    ChecklistItemOut,
    ChecklistSignIn,
    ChecklistWaiveIn,
    ChecklistWaiverOut,
    CloseChecklistTemplateCreateIn,
    CloseChecklistTemplateOut,
)
from erev_api.schemas.periods import (
    PeriodCancelCloseIn,
    PeriodGateResultOut,
    PeriodLockRequestIn,
    PeriodLockRequestOut,
    PeriodOut,
    PeriodPermanentLockRequestIn,
    PeriodPermanentLockRequestOut,
    PeriodReopenRequestIn,
    PeriodReopenRequestOut,
    PeriodStartCloseIn,
)

if TYPE_CHECKING:
    from datetime import datetime

    from erev_api.uow import UnitOfWork

# The advisory key of ``_pinned_scope(one_request=True)``: one request per period state at a time.
REQUEST_LOCK_KEY: Final = "erev:period-request:{state_id}"
START_CLOSE_ACTION: Final = "period.start_close"
CANCEL_CLOSE_ACTION: Final = "period.cancel_close"
TRANSITION_CODE: Final = "EREV-PER-001"
# 04 table 3.4-R: the reasons that end soft close.
CANCEL_CLOSE_REASONS: Final[frozenset[ReasonCode]] = frozenset(
    {ReasonCode.CLOSE_RESTARTED, ReasonCode.DATA_CORRECTION_PENDING, ReasonCode.OTHER}
)
RULE_REASON: Final = "REASON_CODE_NOT_ALLOWED"
REASON_NOT_ALLOWED: Final = (
    "End soft close with the reason CLOSE_RESTARTED, DATA_CORRECTION_PENDING or OTHER."
)
NOT_STARTABLE: Final = "Soft close starts from an open or reopened period. {period_key} is {state}."
# PRD §5.5 ERR-78 (04 §14.1 DB-07 rev 1.182; supervisor ruling R-116 (h); review finding F8): the
# lock decision's refusal when the `future` next period, which it would open, is held.
RULE_NEXT_PERIOD_HELD: Final = "NEXT_PERIOD_HELD"
NEXT_PERIOD_HELD: Final = (
    "{next_period} is in use by another request, so {period} was not locked. Nothing was saved. "
    "Decide again."
)
LOCK_NOT_AVAILABLE: Final = "55P03"  # PostgreSQL: a row lock asked NOWAIT is held
# PRD §5.5 ERR-85 (04 §14.1 DB-07 rev 1.182; supervisor ruling R-119 (d)): the refusal of a lock
# request, and of a lock decision, when an EARLIER period's row is held — BR-CLS-08's read does
# not wait either, and until rev 1.182 answered with the copy of a lock wait.
RULE_EARLIER_PERIOD_HELD: Final = "EARLIER_PERIOD_HELD"
EARLIER_PERIOD_HELD: Final = (
    "{earlier_period} is in use by another request, so {period} was not locked. Nothing was "
    "saved. Decide again."
)
# PRD §5.5 ERR-76 (04 T-REF-06 and §16.8 rev 1.155; supervisor rulings R-112 (e) and R-114 (d)).
RULE_LEGACY: Final = "LEGACY_FOLLOWS_PRIMARY"
LEGACY_FOLLOWS: Final = "The legacy book follows the close of {primary_book}."
NOT_CLOSING: Final = "Only a period in soft close returns to open. {period_key} is {state}."
SOFT_CLOSE_UNDER_LOCK: Final = (
    "The period is in soft close under a {kind} record, which no command writes; its soft close "
    "cannot be ended."
)
START_FROM: Final[frozenset[PeriodState]] = frozenset({PeriodState.OPEN, PeriodState.REOPENED})

# --- checklist (CLO-4) ---------------------------------------------------------------------------
ITEM_OBJECT: Final = "close_checklist_item"
TEMPLATE_OBJECT: Final = "close_checklist_template"
SIGN_ACTION: Final = "close_checklist_item.sign"
SIGNOFF_CLEARED_ACTION: Final = "close_checklist_item.signoff_cleared"
REQUEST_WAIVER_ACTION: Final = "close_checklist_item.request_waiver"
WAIVE_ACTION: Final = "close_checklist_item.waive"
WAIVER_CLEARED_ACTION: Final = "close_checklist_item.waiver_cleared"
CREATE_TASK_ACTION: Final = "close_checklist_template.create"
UPDATE_TASK_ACTION: Final = "close_checklist_template.update"
RULE_ITEM: Final = "T-CLS-03"
RULE_TEMPLATE: Final = "T-CLS-02"
RULE_STATEMENT: Final = "STATEMENT_NOT_ACCEPTED"
# SCREENS_B §1.1 "Sign task": the fixed statement of a close task sign-off (T-CLS-08).
SIGN_STATEMENT: Final = "I completed this close task for {entity} {period}."
STATEMENT_REQUIRED: Final = "Confirm the statement before signing."
NOT_MANUAL: Final = "{name} is evaluated automatically. Only a manual close task is signed."
ALREADY_CLEARED: Final = "{name} has already cleared ({status})."
NOT_WAIVABLE: Final = "A waiver is requested only for a close gate or task that has not passed."
# R-55 (c): JE_BALANCED, JE_COMPLETE and CONTROLLER_CERTIFIED; R-114 (b): CLOSE_RUN_COMPLETED
# (``gates.NEVER_WAIVABLE``).
NEVER_WAIVABLE: Final = "{name} cannot be waived. The period locks only when this gate passes."
WAIVER_SUMMARY: Final = "Waiver of close gate {name} for {entity} {period}"
CLEARED: Final = frozenset(
    {
        ChecklistStatus.PASSED.value,
        ChecklistStatus.WAIVED.value,
        ChecklistStatus.NOT_APPLICABLE.value,
    }
)
TASK_MANUAL_ONLY: Final = "A tenant-defined close task is manual. System gates are automatic."
TASK_CODE_TAKEN: Final = "A close task or gate with the code {code} exists."
ROLE_UNKNOWN: Final = "Choose a role of the workspace."
SYSTEM_GATE_FIELDS: Final = frozenset({"owner_role_id", "due_offset_days"})
SYSTEM_GATE_FIXED: Final = "A system gate changes only in its owner role and due offset."
VALUE_REQUIRED: Final = "Enter a value."
NON_NULLABLE: Final = frozenset({"name", "is_blocking", "is_active"})


def _record_transition(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    current: Mapping[Any, Any],
    from_state: PeriodState,
    to_state: PeriodState,
    action: str,
    reason_code: ReasonCode | None,
    comment: str | None,
    approval_request_id: UUID | None = None,
    period_lock_id: UUID | None = None,
    set_current_lock: bool = False,
    transition_id: UUID | None = None,
) -> tuple[UUID, int]:
    """Write the T-REF-07 transition row (DB-07 needs it in the same transaction), move the state
    and audit it (REQ-CLS-001); returns the transition id and the new ``row_version``. A lock passes
    the ``transition_id`` it allocated up front, because its ``period_lock`` row, inserted first
    (D-98 61), already names it."""
    session = uow.session
    principal = uow.principal
    entity_id = UUID(str(current["entity_id"]))
    transition_id = new_id() if transition_id is None else transition_id
    new_version = int(current["row_version"]) + 1
    session.execute(
        insert(period_state_transition).values(
            tenant_id=principal.tenant_id,
            id=transition_id,
            period_state_id=state_id,
            entity_id=entity_id,
            book_code=current["book_code"],
            period_id=current["period_id"],
            from_state=from_state.value,
            to_state=to_state.value,
            reason_code=None if reason_code is None else reason_code.value,
            comment=comment,
            approval_request_id=approval_request_id,
            period_lock_id=period_lock_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
    )
    values: dict[str, Any] = {
        "state": to_state.value,
        "state_changed_at": uow.now,
        "row_version": new_version,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    if set_current_lock:
        values["current_lock_id"] = period_lock_id
    session.execute(update(period_state).where(period_state.c.id == state_id).values(**values))
    uow.audit(
        action=action,
        object_type=period_rules.STATE_OBJECT,
        object_id=state_id,
        object_version=str(new_version),
        before={"state": from_state.value},
        after={
            "state": to_state.value,
            "period_state_transition_id": str(transition_id),
            "entity_id": str(entity_id),
            "book_code": str(current["book_code"]),
            "period_id": str(current["period_id"]),
            "approval_request_id": None
            if approval_request_id is None
            else str(approval_request_id),
            "period_lock_id": None if period_lock_id is None else str(period_lock_id),
        },
        reason_code=None if reason_code is None else reason_code.value,
        comment=comment,
    )
    return transition_id, new_version


def soft_close_target(session: Session, current_lock_id: UUID | None) -> PeriodState:
    """Where an ended soft close returns a period (PRD SM-07 rev 1.99; 04 §16.8 rev 1.170): to the
    state its soft close started from. A period that was never locked has no current lock record
    and returns to ``open``. A period that has been locked before reaches a soft close only from
    ``reopened`` and is still under the ``REOPEN`` record (``period_state.current_lock_id``): it
    returns to ``reopened``, so that its postings stay post-reopen activity (BR-CLS-06; DB-07
    ``is_post_reopen``). Read under the state row's lock. No command leaves a period in soft close
    under another kind of record; that state is refused by name."""
    if current_lock_id is None:
        return period_machine.cancel_close_target(locked_before=False)
    kind = lock_kind(session, current_lock_id)  # the one reading of the record (R-117 (c))
    if kind is not LockKind.REOPEN:
        message = SOFT_CLOSE_UNDER_LOCK.format(kind="missing" if kind is None else kind.value)
        error = ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)
        raise Problem("invalid-transition", message, errors=[error], code=TRANSITION_CODE)
    return period_machine.cancel_close_target(locked_before=True)


def _refuse_legacy_book(session: Session, book_code: str) -> None:
    """The LEGACY book has no close of its own in 1.0 — no journal run exists for it (04 T-SL-06),
    so no lock could follow a soft close — and follows the primary book's (04 T-REF-06 rev 1.155;
    supervisor rulings R-112 (e) and R-114 (d)). ``start-close``, ``request-lock``,
    ``request-reopen`` and ``request-permanent-lock`` refuse a period of it by name, whatever its
    state: 409 ``invalid-transition``, rule ``LEGACY_FOLLOWS_PRIMARY`` (PRD ERR-76). ``open`` and
    ``cancel-close`` do not ask."""
    if book_code != BookCode.LEGACY.value:
        return
    name = session.execute(select(book.c.name).where(book.c.is_primary.is_(True))).scalar()
    message = LEGACY_FOLLOWS.format(primary_book="the primary book" if name is None else str(name))
    error = ProblemError(rule_id=RULE_LEGACY, message=message)
    raise Problem("invalid-transition", message, errors=[error], code=TRANSITION_CODE)


def _move(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    check_version: Callable[[int], None],
    allowed_from: frozenset[PeriodState],
    to_state: PeriodState | None,
    refusal: str,
    action: str,
    reason_code: ReasonCode | None,
    comment: str | None,
    own_close: bool = False,
) -> PeriodOut:
    """Move a period between its postable states. ``to_state`` None is the end of a soft close:
    the target is read from the period's current lock record under the row lock
    (``soft_close_target``)."""
    session = uow.session
    locked = (
        select(
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            period_state.c.state,
            period_state.c.row_version,
            period_state.c.current_lock_id,
        )
        .where(period_state.c.id == state_id)
        .with_for_update()
    )
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    entity_id = UUID(str(current["entity_id"]))
    require_for_entity(uow.ctx, period_rules.CLOSE_PERMISSION, entity_id)
    check_version(int(current["row_version"]))
    if own_close:  # the move begins a close of the period's own book
        _refuse_legacy_book(session, _text(current["book_code"]))
    shown = reference_queries.period_row(session, state_id)
    if shown is None:
        raise Problem("not-found")
    state = PeriodState(str(current["state"]))
    if state not in allowed_from:
        message = refusal.format(period_key=shown["period"]["period_key"], state=state.value)
        error = ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)
        raise Problem("invalid-transition", message, errors=[error], code=TRANSITION_CODE)
    if to_state is None:
        lock_id = current["current_lock_id"]
        to_state = soft_close_target(session, None if lock_id is None else UUID(str(lock_id)))

    _record_transition(
        uow,
        state_id=state_id,
        current=current,
        from_state=state,
        to_state=to_state,
        action=action,
        reason_code=reason_code,
        comment=comment,
    )
    moved = close_queries.period_view(session, state_id)
    if moved is None:
        raise Problem("not-found")
    return PeriodOut.model_validate(moved)


def start_close(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    body: PeriodStartCloseIn,
    check_version: Callable[[int], None],
) -> PeriodOut:
    """``POST /periods/{id}/start-close``: ``open`` or ``reopened`` → ``closing`` (SM-07). From here
    imports affecting the period wait for human review (BR-CLS-04, BR-DAT-07). A period of the
    LEGACY book is refused by name (``_refuse_legacy_book``; PRD ERR-76)."""
    return _move(
        uow,
        state_id=state_id,
        check_version=check_version,
        allowed_from=START_FROM,
        to_state=PeriodState.CLOSING,
        refusal=NOT_STARTABLE,
        action=START_CLOSE_ACTION,
        reason_code=None,
        comment=body.comment,
        own_close=True,
    )


def cancel_close(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    body: PeriodCancelCloseIn,
    check_version: Callable[[int], None],
) -> PeriodOut:
    """``POST /periods/{id}/cancel-close``: the soft close ends and the period returns to the state
    it was soft-closed from — ``closing`` → ``open``, or ``closing`` → ``reopened`` for a period
    that has been locked before (PRD SM-07 rev 1.99; 04 §16.8 rev 1.170; ``soft_close_target``) —
    with a reason of the table 3.4-R subset; another E-110 literal is 422
    ``REASON_CODE_NOT_ALLOWED``. Until rev 1.170 every period returned to ``open``: a reopened
    period then lost ``is_post_reopen`` on its later lines and the human approval of BR-CLS-06."""
    if body.reason_code not in CANCEL_CLOSE_REASONS:
        error = ProblemError(field="reason_code", rule_id=RULE_REASON, message=REASON_NOT_ALLOWED)
        raise Problem("validation-failed", "1 field needs attention.", errors=[error])
    return _move(
        uow,
        state_id=state_id,
        check_version=check_version,
        allowed_from=frozenset({PeriodState.CLOSING}),
        to_state=None,
        refusal=NOT_CLOSING,
        action=CANCEL_CLOSE_ACTION,
        reason_code=body.reason_code,
        comment=body.comment,
    )


# --- checklist items (CLO-4) ---------------------------------------------------------------------


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def materialise_checklist(uow: UnitOfWork, *, state_id: UUID) -> bool:
    """The checklist of a period as its readers must find it (``gates.materialise_for_view``): the
    route of ``GET /periods/{id}/cockpit`` and ``GET /periods/{id}/checklist`` runs it as the
    SYSTEM principal after checking that the reader sees the period, and commits only when it
    returns True. No audit event, no monitor run, nothing written when nothing changed (security
    finding SC-8; supervisor ruling R-32)."""
    return gates.materialise_for_view(uow, state_id)


def run_period_monitors(uow: UnitOfWork, *, state_id: UUID) -> None:
    """Run the data-quality monitors (CLO-5 ``close.run_monitors``) of a period in an evaluated
    state, so that the gates a period command evaluates next read current findings. The routes of
    ``start-close`` and ``request-lock`` run it as the SYSTEM principal in its own unit of work
    before their command — the findings stay recorded when the command is refused — and the
    scheduled sweep runs the same monitors daily (05 SCH-10). A GET never runs them (security
    finding SC-8). 404 ``not-found`` for an unknown period state; a period in another state is
    not evaluated."""
    scope = gates.period_scope(uow.session, state_id)
    if scope is None:
        raise Problem("not-found")
    if scope.state in gates.EVALUATED_STATES:
        monitors.run_monitors(uow, scope.entity_id, scope.book_code, scope.period_id)


def _pinned_scope(
    uow: UnitOfWork,
    state_id: UUID,
    *,
    permission: str = period_rules.CLOSE_PERMISSION,
    one_request: bool = False,
) -> gates.PeriodScope:
    """The scope of a close command that leaves the period's state as it is — a checklist sign-off
    or waiver, a request for a lock, a permanent lock or a reopen: the state row ``FOR SHARE``
    (04 DB-07 rev 1.113; dev-guide DG-KRN-DB-08 (1a)). The command needs the state to stay what it
    read, which a share lock gives — a change of the state takes the row ``FOR UPDATE`` — and the
    DB-07 guards hold the same row ``FOR SHARE`` for every line a posting inserts, so the command
    neither waits for the postings in flight nor makes one wait. ``one_request`` first takes a
    transaction-level advisory lock on the period state: two requests for one period are decided
    one after the other, as the row lock ``FOR UPDATE`` did, and the second one reads the first
    one's pending request. The pending reopen basis is stored separately so submission
    never upgrades this shared period lock."""
    session = uow.session
    if one_request:
        key = REQUEST_LOCK_KEY.format(state_id=state_id)
        session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
    row = (
        session.execute(
            gates.scope_select()
            .where(period_state.c.id == state_id)
            .with_for_update(read=True, of=period_state)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise Problem("not-found")
    scope = gates.scope_of(row)
    require_for_entity(uow.ctx, permission, scope.entity_id)
    return scope


def _require_mfa(uow: UnitOfWork) -> None:
    """A sign-off needs an MFA-verified session (04 §16.8 ``sign``; T-CLS-08
    ``mfa_verified_at``)."""
    principal = uow.principal
    if principal.mfa_verified_at is not None:
        return
    enrolled = principal.id is not None and mfa.has_confirmed_factor(
        principal.id, request_id=uow.ctx.request_id
    )
    raise Problem("mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED)


def _item(uow: UnitOfWork, scope: gates.PeriodScope, item_id: UUID) -> dict[str, Any]:
    """The locked item of the period with its template; 404 for an item of another period."""
    row = (
        uow.session.execute(
            select(
                close_checklist_item.c.id,
                close_checklist_item.c.status,
                close_checklist_item.c.result,
                close_checklist_item.c.row_version,
                close_checklist_template.c.code,
                close_checklist_template.c.name,
                close_checklist_template.c.gate_kind,
                close_checklist_template.c.gate_check_code,
                close_checklist_template.c.owner_role_id,
            )
            .join(
                close_checklist_template,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            )
            .where(
                close_checklist_item.c.id == item_id,
                close_checklist_item.c.entity_id == scope.entity_id,
                close_checklist_item.c.book_code == scope.book_code,
                close_checklist_item.c.period_id == scope.period_id,
            )
            .with_for_update(of=(close_checklist_item, close_checklist_template))
        )
        .mappings()
        .first()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _refused(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=RULE_ITEM, message=message)],
    )


def _item_out(uow: UnitOfWork, scope: gates.PeriodScope, item_id: UUID) -> ChecklistItemOut:
    (found,) = [
        item for item in close_queries.checklist_items(uow.session, scope) if item["id"] == item_id
    ]
    return ChecklistItemOut.model_validate(found)


def sign_checklist_item(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    item_id: UUID,
    body: ChecklistSignIn,
    check_version: Callable[[int], None],
) -> ChecklistItemOut:
    """``POST /periods/{id}/checklist/{item_id}/sign``: a manual close task becomes PASSED with a
    PREPARER sign-off of the fixed statement and the task's content hash (T-CLS-08; REQ-CLS-021).
    403 ``mfa-required`` without an MFA-verified session; 409 for an automatic gate or a cleared
    item."""
    scope = _pinned_scope(uow, state_id)
    _require_mfa(uow)
    check_version(scope.row_version)
    if not body.statement_accepted:
        error = ProblemError(
            field="statement_accepted", rule_id=RULE_STATEMENT, message=STATEMENT_REQUIRED
        )
        raise Problem("validation-failed", "1 field needs attention.", errors=[error])
    gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id)
    item = _item(uow, scope, item_id)
    name = str(item["name"])
    status = _text(item["status"])
    if _text(item["gate_kind"]) != ChecklistGateKind.MANUAL.value:
        raise _refused(NOT_MANUAL.format(name=name))
    if status in CLEARED:
        raise _refused(ALREADY_CLEARED.format(name=name, status=status))
    if scope.state not in {
        PeriodState.OPEN.value,
        PeriodState.CLOSING.value,
        PeriodState.REOPENED.value,
    }:
        raise _refused(
            "Close tasks cannot be signed while the period is closed or permanently locked."
        )
    principal = uow.principal
    owner_role_id = item["owner_role_id"]
    if owner_role_id is not None:
        owner = uow.session.execute(
            select(role.c.code, role.c.name).where(role.c.id == owner_role_id)
        ).one()
        role_scope = principal.role_scopes.get(str(owner.code))
        if role_scope != "*" and (role_scope is None or scope.entity_id not in role_scope):
            raise Problem(
                "forbidden",
                f"Signing this close task requires the {owner.name} role for {scope.entity_code}.",
            )
    assert principal.id is not None and principal.mfa_verified_at is not None  # _require_mfa
    statement = SIGN_STATEMENT.format(entity=scope.entity_code, period=scope.period_name)
    content = {
        "close_checklist_item_id": str(item_id),
        "period_lock_id": None if scope.current_lock_id is None else str(scope.current_lock_id),
        "owner_role_id": None if owner_role_id is None else str(owner_role_id),
        "code": str(item["code"]),
        "name": name,
        "entity_code": scope.entity_code,
        "book_code": scope.book_code,
        "period_key": scope.period_key,
        "statement": statement,
    }
    signoff_id = new_id()
    uow.session.execute(
        insert(signoff).values(
            tenant_id=principal.tenant_id,
            id=signoff_id,
            subject_type=ITEM_OBJECT,
            subject_id=item_id,
            role=SignoffRole.PREPARER.value,
            signer_id=principal.id,
            statement=statement,
            subject_content_sha256=sha256_hex(content),
            mfa_verified_at=principal.mfa_verified_at,
            signed_at=uow.now,
        )
    )
    transitions.apply(
        uow.session,
        ITEM_OBJECT,
        item_id,
        to_status=ChecklistStatus.PASSED.value,
        expected_status=status,
        set_values={"signoff_id": signoff_id, **_stamps(uow)},
    )
    uow.audit(
        action=SIGN_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        object_version=str(int(item["row_version"]) + 1),
        before={"status": status},
        after={
            "status": ChecklistStatus.PASSED.value,
            "signoff_id": str(signoff_id),
            "role": SignoffRole.PREPARER.value,
            "statement": statement,
        },
    )
    return _item_out(uow, scope, item_id)


def waive_checklist_item(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    item_id: UUID,
    body: ChecklistWaiveIn,
    check_version: Callable[[int], None],
) -> ChecklistWaiverOut:
    """``POST /periods/{id}/checklist/{item_id}/waive``: an ``EXCEPTION_WAIVER`` request for an item
    that has not passed, approved by an ``exception.waive`` holder other than the requester and the
    item owner (BS4-D-07; PRD §2.5). The item keeps its status and names the request until the
    decision; once approved the waiver clears the item for the lock request and the lock decision
    (supervisor ruling R-55 (b)). Journal balancing, journal completeness, the close run and the
    controller certification are never waivable: 409 ``invalid-transition`` naming the gate (R-55
    (c), R-114 (b); 04 §16.8 rev 1.106, 1.172). ``NO_DIRTY_GROUPS`` is not waivable while the
    re-marking of a period a lock opened has not succeeded: 409 with the gate's own detail (R-106
    (a); 04 §16.8 rev 1.164)."""
    scope = _pinned_scope(uow, state_id)
    check_version(scope.row_version)
    gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id)
    item = _item(uow, scope, item_id)
    if item["gate_check_code"] in gates.NEVER_WAIVABLE:
        raise _refused(NEVER_WAIVABLE.format(name=item["name"]))
    status = _text(item["status"])
    if status in CLEARED:
        raise _refused(NOT_WAIVABLE)
    if not gates.waivable(
        item["gate_check_code"], remark_pending=gates.remark_pending(uow.session, scope)
    ):
        # R-106 (a): not waivable while the opened period's re-marking has not succeeded
        raise _refused(gates.REMARK_PENDING_DETAIL)
    # Preserve the exact approved subject before submission changes pending-approval counts.
    # A later reopen may overwrite the checklist result; the request hash alone cannot
    # recover the reviewed member population.
    waiver_basis = subjects.exception_waiver_content(uow.session, item_id)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.EXCEPTION_WAIVER,
        subject_id=item_id,
        summary=WAIVER_SUMMARY.format(
            name=item["name"], entity=scope.entity_code, period=scope.period_name
        ),
        comment=body.reason,
        auto_approval=False,
    )
    request_id = UUID(str(request["id"]))
    values: dict[str, Any] = {"waiver_approval_request_id": request_id, **_stamps(uow)}
    if item["gate_check_code"] == gates.APPROVALS_CLEARED:
        # submit hashed the current result. Retain that same scope across later reads while
        # other requests are decided; final approval checks the live population is a subset.
        values["result"] = {**item["result"], subjects.CHECKLIST_WAIVER_BASIS: dict(item["result"])}
    transitions.apply(
        uow.session,
        ITEM_OBJECT,
        item_id,
        to_status=None,
        set_values=values,
    )
    uow.audit(
        action=REQUEST_WAIVER_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        object_version=str(int(item["row_version"]) + 1),
        before={"status": status, "waiver_approval_request_id": None},
        after={
            "status": status,
            "waiver_approval_request_id": str(request_id),
            "waiver_basis": waiver_basis,
        }
        | ({"members": item["result"].get("members")} if item["result"] else {}),
        comment=body.reason,
        approval_request_id=request_id,
    )
    return ChecklistWaiverOut(approval_request_id=request_id, request_no=str(request["request_no"]))


def _locked_item_row(uow: UnitOfWork, item_id: UUID) -> Mapping[Any, Any]:
    row = (
        uow.session.execute(
            select(
                close_checklist_item.c.id,
                close_checklist_item.c.status,
                close_checklist_item.c.result,
                close_checklist_item.c.waiver_approval_request_id,
                close_checklist_item.c.row_version,
            )
            .where(close_checklist_item.c.id == item_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return row


def _checklist_waived(uow: UnitOfWork, item_id: UUID, approval_request_id: UUID) -> None:
    """``EXCEPTION_WAIVER`` of a checklist item approved: WAIVED with the request and its
    comment."""
    item = subjects.checklist_waiver_row(uow.session, item_id)
    if item is None:
        raise Problem("not-found")
    scope = gates.scope_of_period(
        uow.session, item["entity_id"], _text(item["book_code"]), item["period_id"], share=True
    )
    if scope is None or scope.state not in gates.EVALUATED_STATES:
        raise approvals.StaleBasis()
    if _text(item["gate_kind"]) == ChecklistGateKind.AUTOMATIC.value:
        # Refresh even when nobody opened the cockpit since this waiver was requested.
        # The period precedes checklist rows in the lock order. The approval kernel runs
        # this hook under tenant scope and rolls these writes back on a stale basis.
        gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id)
    row = _locked_item_row(uow, item_id)
    result = row["result"]
    if item["gate_check_code"] == gates.APPROVALS_CLEARED:
        basis = subjects.checklist_waiver_basis(result or {}, item["gate_check_code"])
        current_members = (result or {}).get("members")
        reviewed_members = basis.get("members")
        if (
            current_members is None
            or reviewed_members is None
            or not set(current_members).issubset(reviewed_members)
        ):
            raise approvals.StaleBasis()
        result = basis
    approvals.assert_own_fresh_basis(
        uow,
        approval_request_id,
        subject_type=ApprovalSubjectType.EXCEPTION_WAIVER,
        subject_id=item_id,
    )
    status = _text(row["status"])
    if status in CLEARED:
        raise _refused(NOT_WAIVABLE)
    comment = uow.session.execute(
        select(approval_request.c.comment).where(approval_request.c.id == approval_request_id)
    ).scalar_one_or_none()
    transitions.apply(
        uow.session,
        ITEM_OBJECT,
        item_id,
        to_status=ChecklistStatus.WAIVED.value,
        expected_status=status,
        set_values={
            "waiver_approval_request_id": approval_request_id,
            "comment": None if comment is None else str(comment),
            "result": None if result is None else gates.renewed_waiver_result(result),
            **_stamps(uow),
        },
    )
    uow.audit(
        action=WAIVE_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        object_version=str(int(row["row_version"]) + 1),
        before={"status": status},
        after={
            "status": ChecklistStatus.WAIVED.value,
            "waiver_approval_request_id": str(approval_request_id),
        },
        approval_request_id=approval_request_id,
    )


def _checklist_waiver_cleared(uow: UnitOfWork, item_id: UUID, approval_request_id: UUID) -> None:
    """A rejected or voided checklist waiver leaves the item as it was and forgets the request."""
    row = _locked_item_row(uow, item_id)
    if row["waiver_approval_request_id"] != approval_request_id:
        return
    if _text(row["status"]) == ChecklistStatus.WAIVED.value:
        return
    result = None if row["result"] is None else dict(row["result"])
    if result is not None:
        result.pop(subjects.CHECKLIST_WAIVER_BASIS, None)
    transitions.apply(
        uow.session,
        ITEM_OBJECT,
        item_id,
        to_status=None,
        set_values={"waiver_approval_request_id": None, "result": result, **_stamps(uow)},
    )
    uow.audit(
        action=WAIVER_CLEARED_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        object_version=str(int(row["row_version"]) + 1),
        before={"waiver_approval_request_id": str(approval_request_id)},
        after={"waiver_approval_request_id": None},
        approval_request_id=approval_request_id,
    )


def checklist_item_link(session: Session, item_id: UUID) -> str | None:
    """The SF-05 task drawer of a checklist item, ``/close/<entity code>/<book code>/<period key>
    ?drawer=task&task=<gate check code, or the template code of a manual task>``, or None when
    ``item_id`` is not a checklist item the session can read ([J] D-88 L7-2-Q-7, L7-2-Q-15 vii)."""
    row = (
        session.execute(
            select(
                legal_entity.c.code.label("entity_code"),
                close_checklist_item.c.book_code,
                period.c.period_key,
                close_checklist_template.c.gate_check_code,
                close_checklist_template.c.code.label("template_code"),
            )
            .select_from(
                close_checklist_item.join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == close_checklist_item.c.tenant_id,
                        legal_entity.c.id == close_checklist_item.c.entity_id,
                    ),
                )
                .join(
                    period,
                    and_(
                        period.c.tenant_id == close_checklist_item.c.tenant_id,
                        period.c.id == close_checklist_item.c.period_id,
                    ),
                )
                .join(
                    close_checklist_template,
                    and_(
                        close_checklist_template.c.tenant_id == close_checklist_item.c.tenant_id,
                        close_checklist_template.c.id
                        == close_checklist_item.c.close_checklist_template_id,
                    ),
                )
            )
            .where(close_checklist_item.c.id == item_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    task = row["gate_check_code"] or row["template_code"]
    path = "/".join(
        quote(_text(value), safe="")
        for value in (row["entity_code"], row["book_code"], row["period_key"])
    )
    return f"/close/{path}?drawer=task&task={quote(_text(task), safe='')}"


subjects.register_covered_lifecycle(
    ApprovalSubjectType.EXCEPTION_WAIVER,
    subjects.CoveredLifecycle(
        table=subjects.CHECKLIST_ITEM_TABLE,
        owns=subjects.is_checklist_item,
        lifecycle=subjects.SubjectLifecycle(
            on_approved=_checklist_waived,
            on_rejected=_checklist_waiver_cleared,
            on_voided=_checklist_waiver_cleared,
        ),
        link=checklist_item_link,
    ),
)


# --- tenant-defined close tasks (BS4-D-06) -------------------------------------------------------

TEMPLATE_COLUMNS: Final = (
    close_checklist_template.c.id,
    close_checklist_template.c.code,
    close_checklist_template.c.name,
    close_checklist_template.c.description,
    close_checklist_template.c.gate_kind,
    close_checklist_template.c.gate_check_code,
    close_checklist_template.c.is_blocking,
    close_checklist_template.c.is_system,
    close_checklist_template.c.owner_role_id,
    close_checklist_template.c.due_offset_days,
    close_checklist_template.c.sequence,
    close_checklist_template.c.is_active,
    close_checklist_template.c.created_at,
    close_checklist_template.c.updated_at,
    close_checklist_template.c.row_version,
)


def template_out(uow: UnitOfWork, template_id: UUID) -> CloseChecklistTemplateOut:
    row = (
        uow.session.execute(
            select(*TEMPLATE_COLUMNS).where(close_checklist_template.c.id == template_id)
        )
        .mappings()
        .one()
    )
    return CloseChecklistTemplateOut.model_validate(
        {**dict(row), "gate_kind": _text(row["gate_kind"])}
    )


def _invalid(*errors: ProblemError) -> Problem:
    count = len(errors)
    title = f"{count} field needs attention." if count == 1 else f"{count} fields need attention."
    return Problem("validation-failed", title, errors=list(errors))


def _check_role(uow: UnitOfWork, role_id: UUID | None) -> None:
    if role_id is None:
        return
    found = uow.session.execute(select(role.c.id).where(role.c.id == role_id)).scalar_one_or_none()
    if found is None:
        raise _invalid(
            ProblemError(field="owner_role_id", rule_id=RULE_TEMPLATE, message=ROLE_UNKNOWN)
        )


def create_close_task(
    uow: UnitOfWork, *, body: CloseChecklistTemplateCreateIn
) -> CloseChecklistTemplateOut:
    """``POST /close-checklist-templates``: a tenant-defined manual close task after every existing
    gate and task (T-CLS-02; REQ-CLS-021). The periods' checklists take it when they are next
    evaluated."""
    session = uow.session
    if body.gate_kind is not ChecklistGateKind.MANUAL:
        raise _invalid(
            ProblemError(field="gate_kind", rule_id=RULE_TEMPLATE, message=TASK_MANUAL_ONLY)
        )
    taken = session.execute(
        select(close_checklist_template.c.id).where(close_checklist_template.c.code == body.code)
    ).scalar_one_or_none()
    if taken is not None:
        raise _invalid(
            ProblemError(
                field="code", rule_id=RULE_TEMPLATE, message=TASK_CODE_TAKEN.format(code=body.code)
            )
        )
    _check_role(uow, body.owner_role_id)
    sequence = int(
        session.execute(
            select(func.coalesce(func.max(close_checklist_template.c.sequence), 0))
        ).scalar_one()
    )
    principal = uow.principal
    template_id = new_id()
    values = {
        "code": body.code,
        "name": body.name,
        "description": body.description,
        "gate_kind": ChecklistGateKind.MANUAL.value,
        "gate_check_code": None,
        "is_blocking": body.is_blocking,
        "is_system": False,
        "owner_role_id": body.owner_role_id,
        "due_offset_days": body.due_offset_days,
        "sequence": sequence + 1,
        "is_active": body.is_active,
    }
    session.execute(
        insert(close_checklist_template).values(
            tenant_id=principal.tenant_id,
            id=template_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **_stamps(uow),
            **values,
        )
    )
    uow.audit(
        action=CREATE_TASK_ACTION,
        object_type=TEMPLATE_OBJECT,
        object_id=template_id,
        object_version="1",
        after={
            key: str(value) if isinstance(value, UUID) else value for key, value in values.items()
        },
    )
    return template_out(uow, template_id)


def update_close_task(
    uow: UnitOfWork,
    *,
    template_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> CloseChecklistTemplateOut:
    """``PATCH /close-checklist-templates/{id}`` (``If-Match``): a tenant task changes in its name,
    description, blocking flag, owner role, due offset and activity; a system gate only in its owner
    role and due offset (T-CLS-02 IM-M)."""
    session = uow.session
    row = (
        session.execute(
            select(*TEMPLATE_COLUMNS)
            .where(close_checklist_template.c.id == template_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    check_version(int(row["row_version"]))
    errors: list[ProblemError] = []
    if row["is_system"]:
        errors += [
            ProblemError(field=name, rule_id=RULE_TEMPLATE, message=SYSTEM_GATE_FIXED)
            for name in sorted(set(changes) - SYSTEM_GATE_FIELDS)
        ]
    errors += [
        ProblemError(field=name, rule_id=RULE_TEMPLATE, message=VALUE_REQUIRED)
        for name in sorted(NON_NULLABLE & set(changes))
        if changes[name] is None
    ]
    if errors:
        raise _invalid(*errors)
    if "owner_role_id" in changes:
        _check_role(uow, changes["owner_role_id"])
    if changes:
        session.execute(
            update(close_checklist_template)
            .where(close_checklist_template.c.id == template_id)
            .values(**changes, **_stamps(uow))
        )

        def shown(value: Any) -> Any:
            return str(value) if isinstance(value, UUID) else value

        uow.audit(
            action=UPDATE_TASK_ACTION,
            object_type=TEMPLATE_OBJECT,
            object_id=template_id,
            object_version=str(int(row["row_version"]) + 1),
            before={name: shown(row[name]) for name in sorted(changes)},
            after={name: shown(changes[name]) for name in sorted(changes)},
        )
    return template_out(uow, template_id)


# --- lock, permanent lock and the PERIOD_LOCK approval (CLO-6) -----------------------------------

LOCK_PERMISSION: Final = period_rules.LOCK_PERMISSION
REQUEST_LOCK_ACTION: Final = "period.request_lock"
REQUEST_PERMANENT_LOCK_ACTION: Final = "period.request_permanent_lock"
LOCK_ACTION: Final = "period.lock"
PERMANENT_LOCK_ACTION: Final = "period.permanent_lock"
LOCK_OBJECT: Final = "period_lock"
CONTROL_CLOSE_GATES: Final = "CTL-016"
LOCK_SUMMARY: Final = "Lock {period_key} for {entity} in book {book}"
PERMANENT_LOCK_SUMMARY: Final = "Permanently lock {period_key} for {entity} in book {book}"
NEXT_OPENED: Final = "Opened when {period_key} locked (BR-CLS-03)."
LOCK_NOTIFIED_ROLES: Final = ("controller", "revenue_reviewer", "auditor")  # NTF-06 recipients
LOCKED_TITLE: Final = "{entity} {period_key} locked"  # PRD NTF-06
LOCKED_BODY: Final = (
    "{period_key} for {entity} in book {book} was locked. The lock snapshots are stored."
)
CERTIFY_FROM: Final = frozenset(
    {ReconciliationStatus.REVIEWED.value, ReconciliationStatus.AUTO_CERTIFIED.value}
)
REQUEST_REOPEN_ACTION: Final = "period.request_reopen"  # CLO-7
REOPEN_ACTION: Final = "period.reopen"
REOPEN_SUMMARY: Final = "Reopen {period_key} for {entity} in book {book}"
REOPENED_TITLE: Final = "{entity} {period_key} reopened"  # PRD NTF-07
REOPENED_BODY: Final = "{requester} reopened {period_key}: {reason}. Approved by {approvers}."
REOPEN_INCONSISTENT: Final = (
    "The approvals engine completed the reopen request but SM-07 does not accept it: {reason}"
)
# SM-09: the reconciliation statuses a reopen moves to REOPENED (the CERTIFIED ones of a locked
# period; PREPARED and REVIEWED for completeness).
REOPEN_RECONCILIATIONS_FROM: Final = frozenset(
    {
        ReconciliationStatus.PREPARED.value,
        ReconciliationStatus.REVIEWED.value,
        ReconciliationStatus.CERTIFIED.value,
    }
)
RULE_WRITE_ONCE: Final = "D-98 63"
RECONCILIATION_LOCKED: Final = (
    "Reconciliation {no} already certifies lock {lock}; period_lock_id is written once "
    "(T-CLS-06; D-98 63) and a re-lock certifies only reconciliations generated after the reopen."
)


def _context(scope: gates.PeriodScope) -> period_machine.Context:
    return period_machine.Context(
        period_key=scope.period_key, entity_code=scope.entity_code, book_code=scope.book_code
    )


def _gate_out(result: gates.GateResult) -> PeriodGateResultOut:
    return PeriodGateResultOut(
        gate_check_code=result.gate_check_code,
        status=result.status,
        count=result.count,
        detail=result.detail,
        evaluated_at=result.evaluated_at,
        waiver_approval_request_id=result.waiver_approval_request_id,
        waived_count=result.waived_count,
    )


def _earlier_unlocked(session: Session, scope: gates.PeriodScope) -> str | None:
    """SM-07 permanent-lock guard (ruled Q-6): the earliest earlier period of the entity and book
    that is not ``permanently_locked``, by key; None when every earlier period is."""
    row = session.execute(
        select(period.c.period_key)
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period.c.start_date < scope.start_date,
            period_state.c.state != PeriodState.PERMANENTLY_LOCKED.value,
        )
        .order_by(period.c.start_date)
        .limit(1)
    ).scalar_one_or_none()
    return None if row is None else str(row)


def _earlier_postable(session: Session, scope: gates.PeriodScope) -> str | None:
    """BR-CLS-08 (ERR-65; supervisor ruling R-6): the name of the earliest earlier period of the
    entity and book that is postable — ``open``, ``closing`` or ``reopened`` — or None. An earlier
    ``future`` period does not count: nothing posts into it, and it opens only in order (SM-07
    guard on ``future → open``).

    Every earlier state row is read ``FOR SHARE NOWAIT``, whatever its state, so the answer holds
    until this transaction ends: a reopen or a lock of an earlier period that is being decided
    holds its row ``FOR UPDATE``, and this read then fails at once with 55P03 instead of deciding
    on a state that is about to change. It never waits, so it cannot join a lock cycle with the
    earlier period's own lock decision, which locks the next period's row (BR-CLS-03). Posters
    hold the row of their posting period ``FOR SHARE`` and are not disturbed.

    The 55P03 is answered by name (rev 1.182; supervisor ruling R-119 (d); PRD ERR-85): 409
    ``lock-conflict`` under rule ``EARLIER_PERIOD_HELD``, naming the earliest held period — the
    request and the decision alike. The read runs in a savepoint so that the transaction can
    still ask which row it was (``_shared_or_refused``)."""
    statement = (
        select(period.c.name, period_state.c.state, period_state.c.id)
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period.c.start_date < scope.start_date,
        )
        .order_by(period.c.start_date)
    )
    try:
        with session.begin_nested():
            rows = session.execute(
                statement.with_for_update(read=True, nowait=True, of=period_state)
            ).all()
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
            raise
        rows = _shared_or_refused(session, scope, statement, error)
    for name, state, _ in rows:
        if PeriodState(str(getattr(state, "value", state))) in POSTABLE_STATES:
            return str(name)
    return None


def _shared_or_refused(
    session: Session, scope: gates.PeriodScope, statement: Select[Any], error: DBAPIError
) -> Sequence[Any]:
    """After ``_earlier_postable``'s ``NOWAIT`` read met a held row: which one. Every earlier row
    is read without a lock, then again ``FOR SHARE SKIP LOCKED`` — the rows another transaction
    holds are the ones the second read leaves out. The earliest of them is named in the refusal
    (PRD ERR-85). When none is left out the holder has ended since: every earlier row is shared
    now, exactly as the first read wanted, and those rows are returned for the rule."""
    seen = session.execute(statement).all()
    rows = session.execute(
        statement.with_for_update(read=True, skip_locked=True, of=period_state)
    ).all()
    shared = {row[2] for row in rows}
    held = next((str(row[0]) for row in seen if row[2] not in shared), None)
    if held is None:
        return rows
    message = EARLIER_PERIOD_HELD.format(earlier_period=held, period=scope.period_name)
    refused = ProblemError(rule_id=RULE_EARLIER_PERIOD_HELD, message=message)
    raise Problem("lock-conflict", message, errors=[refused]) from error


def _refuse(outcome: period_machine.Refusal | period_machine.Accepted | Any) -> None:
    if isinstance(outcome, period_machine.Refusal):
        raise outcome.problem()


def _refuse_lock(
    uow: UnitOfWork,
    outcome: period_machine.Refusal | period_machine.Accepted | Any,
    scope: gates.PeriodScope,
    results: gates.GateResults,
) -> None:
    if not isinstance(outcome, period_machine.Refusal):
        return
    problem = outcome.problem()
    failed = next(
        (
            item
            for item in results
            if item.gate_check_code == gates.JE_COMPLETE and item.status is ChecklistStatus.FAILED
        ),
        None,
    )
    if problem.slug == "close-gates-failed" and failed is not None:
        record = validate_execution(
            control_id="CTL-019",
            run_ref_type=RunRefType.PERIOD_STATE,
            run_ref_id=scope.state_id,
            population_count=max(1, failed.count or 0),
            exception_count=max(1, failed.count or 0),
            result=ControlResult.FAIL,
            entity_id=scope.entity_id,
            book_code=scope.book_code,
            period_id=scope.period_id,
            detail={
                "gate": gates.JE_COMPLETE,
                "status": failed.status.value,
                "finding_count": failed.count,
                "detail": failed.detail,
                "evaluated_at": failed.evaluated_at.isoformat(),
                "period_row_version": scope.row_version,
                "population_basis": "completeness findings; one if unavailable",
                "request_id": uow.ctx.request_id,
            },
        )
        raise ControlRefusal(problem, (record,))
    raise problem


def request_lock(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    body: PeriodLockRequestIn,
    check_version: Callable[[int], None],
) -> PeriodLockRequestOut:
    """``POST /periods/{id}/request-lock`` (04 §16.8; BS4-D-08): with every automatic gate passed
    and a certification comment, open the ``PERIOD_LOCK`` approval whose decision locks the
    period; 409 ``close-gates-failed`` (ERR-14) names each failing gate; 409
    ``earlier-period-open`` (ERR-65, BR-CLS-08) while an earlier period of the entity and book is
    postable; 422 ``validation-failed`` for a comment under 10 characters (BR-PLT-08); 409
    ``invalid-transition`` outside ``closing``, and for a period of the LEGACY book whatever its
    state (``_refuse_legacy_book``; PRD ERR-76)."""
    scope = _pinned_scope(uow, state_id, one_request=True)
    check_version(scope.row_version)
    _refuse_legacy_book(uow.session, scope.book_code)
    results = gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id)
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.REQUEST_LOCK,
        period_machine.Guards(
            comment=body.certification_comment,
            gate_results=results,
            earlier_postable_period=_earlier_postable(uow.session, scope),
        ),
        ctx=_context(scope),
    )
    _refuse_lock(uow, outcome, scope, results)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.PERIOD_LOCK,
        subject_id=state_id,
        summary=LOCK_SUMMARY.format(
            period_key=scope.period_key, entity=scope.entity_code, book=scope.book_code
        ),
        comment=body.certification_comment,
        auto_approval=False,
    )
    request_id = UUID(str(request["id"]))
    uow.audit(
        action=REQUEST_LOCK_ACTION,
        object_type=period_rules.STATE_OBJECT,
        object_id=state_id,
        object_version=str(scope.row_version),
        after={"approval_request_id": str(request_id), "lock_kind": LockKind.LOCK.value},
        comment=body.certification_comment,
    )
    return PeriodLockRequestOut(
        approval_request_id=request_id, gate_results=[_gate_out(result) for result in results]
    )


def request_permanent_lock(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    body: PeriodPermanentLockRequestIn,
    check_version: Callable[[int], None],
) -> PeriodPermanentLockRequestOut:
    """``POST /periods/{id}/request-permanent-lock``: from ``closed``, once every earlier period of
    the entity and book is ``permanently_locked`` (ruled Q-6), open the ``PERIOD_LOCK`` approval a
    second Controller decides. The request itself is a Controller's: ``period.lock`` for the
    period's entity (PRD ACT-27, SM-07; 04 §15.3 API-R-18 rev 1.156; supervisor ruling R-83 (a)) —
    with ``period.close`` a Revenue Accountant requested it and one Controller sufficed. The
    requester's own decision is the approval kernel's 403 ``self-approval``. A period of the
    LEGACY book is refused by name (``_refuse_legacy_book``; PRD ERR-76)."""
    scope = _pinned_scope(uow, state_id, permission=LOCK_PERMISSION, one_request=True)
    check_version(scope.row_version)
    _refuse_legacy_book(uow.session, scope.book_code)
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.REQUEST_PERMANENT_LOCK,
        period_machine.Guards(
            comment=body.comment,
            earlier_unlocked_period_key=_earlier_unlocked(uow.session, scope),
        ),
        ctx=_context(scope),
    )
    _refuse(outcome)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.PERIOD_LOCK,
        subject_id=state_id,
        summary=PERMANENT_LOCK_SUMMARY.format(
            period_key=scope.period_key, entity=scope.entity_code, book=scope.book_code
        ),
        comment=body.comment,
        auto_approval=False,
    )
    request_id = UUID(str(request["id"]))
    uow.audit(
        action=REQUEST_PERMANENT_LOCK_ACTION,
        object_type=period_rules.STATE_OBJECT,
        object_id=state_id,
        object_version=str(scope.row_version),
        after={"approval_request_id": str(request_id), "lock_kind": LockKind.PERMANENT_LOCK.value},
        comment=body.comment,
    )
    return PeriodPermanentLockRequestOut(approval_request_id=request_id)


def _current(session: Session, scope: gates.PeriodScope) -> dict[str, Any]:
    return {
        "entity_id": scope.entity_id,
        "book_code": scope.book_code,
        "period_id": scope.period_id,
        "row_version": scope.row_version,
    }


def _heads(session: Session, scope: gates.PeriodScope) -> dict[str, Any]:
    """T-CLS-04 ledger and audit heads at lock."""
    ledger = session.execute(
        select(ledger_chain_head.c.last_chain_seq, ledger_chain_head.c.last_seal_sha256).where(
            ledger_chain_head.c.book_code == scope.book_code
        )
    ).one_or_none()
    audit = session.execute(
        select(audit_chain_head.c.last_chain_seq, audit_chain_head.c.last_hmac)
    ).one_or_none()
    return {
        "ledger_head_chain_seq": 0 if ledger is None else int(ledger.last_chain_seq),
        "ledger_head_sha256": None if ledger is None else ledger.last_seal_sha256,
        "audit_head_chain_seq": 0 if audit is None else int(audit.last_chain_seq),
        "audit_head_hmac": None if audit is None else audit.last_hmac,
    }


def _certify_reconciliations(uow: UnitOfWork, scope: gates.PeriodScope, lock_id: UUID) -> int:
    """The current ``REVIEWED`` and ``AUTO_CERTIFIED`` reconciliations of the period become
    ``CERTIFIED`` with ``certified_at`` and the lock's ``period_lock_id``, written once (SM-09; 04
    T-CLS-06 rev 1.23, D-98 63) in the lock transaction. A reconciliation a later generation
    replaced is history and is not certified (04 rev 1.121; supervisor ruling R-54 (b))."""
    rows = uow.session.execute(
        select(
            reconciliation.c.id,
            reconciliation.c.status,
            reconciliation.c.reconciliation_no,
            reconciliation.c.period_lock_id,
        ).where(
            reconciliation.c.entity_id == scope.entity_id,
            reconciliation.c.book_code == scope.book_code,
            reconciliation.c.period_id == scope.period_id,
            ~gates.superseded(),
        )
    ).all()
    certified = 0
    for row in rows:
        current = str(getattr(row.status, "value", row.status))
        if current not in CERTIFY_FROM:
            continue
        existing = None if row.period_lock_id is None else UUID(str(row.period_lock_id))
        if existing is not None and existing != lock_id:
            # 04 T-CLS-06 rev 1.25 (D-98 63): written once — a re-lock certifies only the
            # reconciliations generated after the reopen; a row of an earlier lock refuses by name.
            message = RECONCILIATION_LOCKED.format(no=row.reconciliation_no, lock=existing)
            raise Problem(
                "invalid-transition",
                message,
                errors=[
                    ProblemError(field="period_lock_id", rule_id=RULE_WRITE_ONCE, message=message)
                ],
            )
        set_values: dict[str, Any] = {"certified_at": uow.now, **gates._stamps(uow)}
        if existing is None:
            set_values["period_lock_id"] = lock_id
        transitions.apply(
            uow.session,
            "reconciliation",
            UUID(str(row.id)),
            to_status=ReconciliationStatus.CERTIFIED.value,
            expected_status=current,
            set_values=set_values,
        )
        certified += 1
    return certified


def _later_closed(session: Session, scope: gates.PeriodScope) -> str | None:
    """BR-CLS-05 (ERR-16): the name of the earliest later period of the entity and book that is
    ``closed`` or ``permanently_locked``; None when none is."""
    row = session.execute(
        select(period.c.name)
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period.c.start_date > scope.end_date,
            period_state.c.state.in_(
                [PeriodState.CLOSED.value, PeriodState.PERMANENTLY_LOCKED.value]
            ),
        )
        .order_by(period.c.start_date)
        .limit(1)
    ).scalar_one_or_none()
    return None if row is None else str(row)


def _previous_lock(session: Session, scope: gates.PeriodScope) -> UUID | None:
    """The ``LOCK`` a re-lock compares with: when the period's current lock record is a ``REOPEN``,
    the ``LOCK`` it (or an earlier ``REOPEN``) names as ``previous_lock_id``; None for a first
    lock."""
    current = scope.current_lock_id
    seen: set[UUID] = set()
    while current is not None and current not in seen:
        seen.add(current)
        row = session.execute(
            select(period_lock.c.kind, period_lock.c.previous_lock_id).where(
                period_lock.c.id == current
            )
        ).one_or_none()
        if row is None:
            return None
        kind = str(getattr(row.kind, "value", row.kind))
        if kind == LockKind.LOCK.value:
            return current if current != scope.current_lock_id else None
        if kind != LockKind.REOPEN.value:
            return None
        current = None if row.previous_lock_id is None else UUID(str(row.previous_lock_id))
    return None


def _display_name(session: Session, user_id: UUID | None) -> str:
    if user_id is None:
        return "System"
    value = session.execute(
        select(app_user.c.display_name).where(app_user.c.id == user_id)
    ).scalar_one_or_none()
    return "System" if value is None else str(value)


def request_reopen(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    body: PeriodReopenRequestIn,
    check_version: Callable[[int], None],
) -> PeriodReopenRequestOut:
    """``POST /periods/{id}/request-reopen`` (04 §16.8; SM-07 ``REQUEST_REOPEN``; BUILD_SPEC CLO-7):
    from ``closed``, with a reason of the request-reopen subset (422 ``REASON_CODE_NOT_ALLOWED``
    otherwise), a comment of at least 10 characters and no later closed or permanently locked
    period (409 ``later-period-closed``, ERR-16), open the ``PERIOD_REOPEN`` request two approvers
    other than the requester decide; no auto-approval (D-98 55). A period of the LEGACY book is
    refused by name (``_refuse_legacy_book``; PRD ERR-76)."""
    scope = _pinned_scope(
        uow,
        state_id,
        permission=period_rules.REOPEN_REQUEST_PERMISSION,
        one_request=True,
    )
    check_version(scope.row_version)
    _refuse_legacy_book(uow.session, scope.book_code)
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.REQUEST_REOPEN,
        period_machine.Guards(
            comment=body.comment,
            reason_code=body.reason_code,
            later_closed_period_key=_later_closed(uow.session, scope),
        ),
        ctx=_context(scope),
    )
    _refuse(outcome)
    basis = None
    if body.reason_code is ReasonCode.ERROR_CORRECTION:
        basis = reopen_judgements.reviewed_basis(
            uow.session,
            tenant_id=uow.principal.tenant_id,
            entity_id=scope.entity_id,
            book_code=scope.book_code,
            judgement_id=body.judgement_record_id,
        )
    elif body.judgement_record_id is not None:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="judgement_record_id",
                    rule_id="REOPEN_JUDGEMENT_REASON",
                    message="A judgement citation is only accepted for an error-correction reopen.",
                )
            ],
        )
    # The per-period advisory lock serializes requests. Keep the period FOR SHARE:
    # upgrading it here would block behind a later period's close decision.
    current_basis = uow.session.execute(
        select(period_reopen_basis.c.id).where(period_reopen_basis.c.period_state_id == state_id)
    ).scalar_one_or_none()
    if current_basis is None:
        uow.session.execute(
            insert(period_reopen_basis).values(
                tenant_id=uow.principal.tenant_id,
                id=new_id(),
                period_state_id=state_id,
                entity_id=scope.entity_id,
                judgement_record_id=body.judgement_record_id,
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
                **_stamps(uow),
            )
        )
    else:
        uow.session.execute(
            update(period_reopen_basis)
            .where(period_reopen_basis.c.id == current_basis)
            .values(judgement_record_id=body.judgement_record_id, **_stamps(uow))
        )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.PERIOD_REOPEN,
        subject_id=state_id,
        summary=REOPEN_SUMMARY.format(
            period_key=scope.period_key, entity=scope.entity_code, book=scope.book_code
        )
        + ("" if basis is None else f" — {basis['content']['judgement_no']}"),
        comment=body.comment,
        reason_code=body.reason_code.value,
        auto_approval=False,
    )
    request_id = UUID(str(request["id"]))
    uow.audit(
        action=REQUEST_REOPEN_ACTION,
        object_type=period_rules.STATE_OBJECT,
        object_id=state_id,
        object_version=str(scope.row_version),
        after={
            "approval_request_id": str(request_id),
            "lock_kind": LockKind.REOPEN.value,
            "judgement": basis,
        },
        reason_code=body.reason_code.value,
        comment=body.comment,
        approval_request_id=request_id,
    )
    return PeriodReopenRequestOut(approval_request_id=request_id)


def _reopen_reconciliations(uow: UnitOfWork, scope: gates.PeriodScope) -> int:
    """SM-09: the PREPARED, REVIEWED and CERTIFIED reconciliations of a reopened period move to
    ``REOPENED`` (regeneration required before the re-lock); ``period_lock_id`` stays as written."""
    rows = uow.session.execute(
        select(reconciliation.c.id, reconciliation.c.status).where(
            reconciliation.c.entity_id == scope.entity_id,
            reconciliation.c.book_code == scope.book_code,
            reconciliation.c.period_id == scope.period_id,
        )
    ).all()
    moved = 0
    for row in rows:
        current = str(getattr(row.status, "value", row.status))
        if current not in REOPEN_RECONCILIATIONS_FROM:
            continue
        transitions.apply(
            uow.session,
            "reconciliation",
            UUID(str(row.id)),
            to_status=ReconciliationStatus.REOPENED.value,
            expected_status=current,
            set_values=gates._stamps(uow),
        )
        moved += 1
    return moved


def _end_waivers(uow: UnitOfWork, scope: gates.PeriodScope, approval_request_id: UUID) -> int:
    """The reopen of a period ends the waivers of the close it reopens (04 T-CLS-03 rev 1.305;
    item CLO-WAIVER-COVERS-LATER-1): every ``WAIVED`` item of the period — a gate's and a task's
    — returns to ``NOT_STARTED`` with no request and no result, each with its own audit event
    under the reopen's request; the next evaluation states what stands. The number ended."""
    rows = list(
        uow.session.execute(
            select(
                close_checklist_item.c.id,
                close_checklist_item.c.waiver_approval_request_id,
                close_checklist_item.c.row_version,
            )
            .where(
                close_checklist_item.c.entity_id == scope.entity_id,
                close_checklist_item.c.book_code == scope.book_code,
                close_checklist_item.c.period_id == scope.period_id,
                close_checklist_item.c.status == ChecklistStatus.WAIVED.value,
            )
            .order_by(close_checklist_item.c.id)
            .with_for_update()
        ).mappings()
    )
    for row in rows:
        item_id = UUID(str(row["id"]))
        transitions.apply(
            uow.session,
            ITEM_OBJECT,
            item_id,
            to_status=ChecklistStatus.NOT_STARTED.value,
            expected_status=ChecklistStatus.WAIVED.value,
            set_values={"waiver_approval_request_id": None, "result": None, **_stamps(uow)},
        )
        waiver = row["waiver_approval_request_id"]
        uow.audit(
            action=WAIVER_CLEARED_ACTION,
            object_type=ITEM_OBJECT,
            object_id=item_id,
            object_version=str(int(row["row_version"]) + 1),
            before={
                "status": ChecklistStatus.WAIVED.value,
                "waiver_approval_request_id": None if waiver is None else str(waiver),
            },
            after={"status": ChecklistStatus.NOT_STARTED.value, "waiver_approval_request_id": None},
            approval_request_id=approval_request_id,
        )
    return len(rows)


def _end_task_signoffs(uow: UnitOfWork, scope: gates.PeriodScope, request_id: UUID) -> int:
    """Reopened periods require fresh manual-task attestations; immutable signoffs remain."""
    rows = list(
        uow.session.execute(
            select(
                close_checklist_item.c.id,
                close_checklist_item.c.signoff_id,
                close_checklist_item.c.row_version,
            )
            .join(
                close_checklist_template,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            )
            .where(
                close_checklist_item.c.entity_id == scope.entity_id,
                close_checklist_item.c.book_code == scope.book_code,
                close_checklist_item.c.period_id == scope.period_id,
                close_checklist_template.c.gate_kind == ChecklistGateKind.MANUAL.value,
                close_checklist_item.c.status == ChecklistStatus.PASSED.value,
            )
            .order_by(close_checklist_item.c.id)
            .with_for_update(of=close_checklist_item)
        ).mappings()
    )
    for row in rows:
        item_id = UUID(str(row["id"]))
        transitions.apply(
            uow.session,
            ITEM_OBJECT,
            item_id,
            to_status=ChecklistStatus.NOT_STARTED.value,
            expected_status=ChecklistStatus.PASSED.value,
            set_values={"signoff_id": None, "result": None, **_stamps(uow)},
        )
        uow.audit(
            action=SIGNOFF_CLEARED_ACTION,
            object_type=ITEM_OBJECT,
            object_id=item_id,
            object_version=str(int(row["row_version"]) + 1),
            before={
                "status": ChecklistStatus.PASSED.value,
                "signoff_id": None if row["signoff_id"] is None else str(row["signoff_id"]),
            },
            after={"status": ChecklistStatus.NOT_STARTED.value, "signoff_id": None},
            approval_request_id=request_id,
        )
    return len(rows)


def _period_reopen_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """The ``PERIOD_REOPEN`` decision that completes the step executes the reopen (BUILD_SPEC CLO-7;
    SM-07 ``closed → reopened``; REQ-CLS-011).

    Through the pure ``period_machine`` with the recorded decisions and their roles: the requester
    is no approver (BR-CLS-02), two distinct approvers with at least one Controller (D-75 Q12;
    the engine's ``_advance`` already held the request PENDING otherwise), BR-CLS-05 at execution
    too. Then the ``REOPEN`` record through ``_persist_lock`` (lock first, D-98 61) with
    ``previous_lock_id`` = the lock reopened, the request's reason and comment; the reconciliations
    to ``REOPENED`` (SM-09); the waivers of the close end (``_end_waivers``); the snapshots stay;
    NTF-07; audit. The open items of a rate that
    changed after the period's lock are settled with it (``rate_changes.settle_reopened``; 04
    T-REF-11 "A rate changed after a lock", rev 1.291).
    """
    session = uow.session
    scope = gates.period_scope(session, subject_id, lock=True)
    if scope is None:
        raise Problem("not-found")
    request = (
        session.execute(
            select(
                approval_request.c.preparer_id,
                approval_request.c.comment,
                approval_request.c.reason_code,
            ).where(approval_request.c.id == approval_request_id)
        )
        .mappings()
        .one_or_none()
    )
    if request is None:
        raise Problem("not-found")
    reason = (
        None
        if request["reason_code"] is None
        else ReasonCode(str(getattr(request["reason_code"], "value", request["reason_code"])))
    )
    citation = session.execute(
        select(period_reopen_basis.c.judgement_record_id).where(
            period_reopen_basis.c.period_state_id == subject_id
        )
    ).scalar_one_or_none()
    if reason is ReasonCode.ERROR_CORRECTION:
        try:
            reopen_judgements.reviewed_basis(
                session,
                tenant_id=uow.principal.tenant_id,
                entity_id=scope.entity_id,
                book_code=scope.book_code,
                judgement_id=citation,
            )
        except Problem as error:
            if error.slug != "validation-failed":
                raise
            raise approvals.StaleBasis() from error
    elif citation is not None:
        raise approvals.StaleBasis()
    approvals.assert_own_fresh_basis(
        uow,
        approval_request_id,
        subject_type=ApprovalSubjectType.PERIOD_REOPEN,
        subject_id=subject_id,
    )
    requester = None if request["preparer_id"] is None else UUID(str(request["preparer_id"]))
    decisions = approvals.decisions_of(
        session, approval_request_id, tenant_id=uow.principal.tenant_id, at=uow.now
    )
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.REOPEN,
        period_machine.Guards(
            comment=request["comment"],
            reason_code=reason,
            requester_id=requester,
            approvals=decisions,
            later_closed_period_key=_later_closed(session, scope),
        ),
        ctx=_context(scope),
    )
    _refuse(outcome)
    if isinstance(outcome, period_machine.Pending | period_machine.Rejected):
        # The engine completed the step but SM-07 does not: never a reopen on a lesser quorum.
        raise Problem("invalid-transition", REOPEN_INCONSISTENT.format(reason=outcome.reason))
    if not isinstance(outcome, period_machine.Accepted):  # pragma: no cover - _refuse raised
        raise Problem("invalid-transition", REOPEN_INCONSISTENT.format(reason=outcome.slug))
    lock_id, transition_id = new_id(), new_id()
    reopened_lock_id = scope.current_lock_id
    _persist_lock(
        uow,
        scope,
        kind=LockKind.REOPEN,
        lock_id=lock_id,
        transition_id=transition_id,
        from_state=PeriodState.CLOSED,
        to_state=PeriodState.REOPENED,
        action=REOPEN_ACTION,
        approval_request_id=approval_request_id,
        comment=request["comment"],
        certification=[],
        snapshot_manifest_sha256=None,
        heads=_heads(session, scope),
        reason_code=reason,
        judgement_record_id=citation,
    )
    reconciliations_reopened = _reopen_reconciliations(uow, scope)
    # 04 T-CLS-03 rev 1.305 (item CLO-WAIVER-COVERS-LATER-1): a waiver accepts what stood before
    # ONE certification; the lock reopened keeps what it certified
    waivers_ended = _end_waivers(uow, scope, approval_request_id)
    task_signoffs_ended = _end_task_signoffs(uow, scope, approval_request_id)
    # 04 T-REF-11 "A rate changed after a lock" (rev 1.291): the period is no longer closed, and
    # its next lock needs a close run that read the rates in force; each item settled has its
    # own audit event
    rate_changes.settle_reopened(uow, scope)
    approvers = [
        decision.actor_id for decision in decisions if decision.kind is ApprovalDecisionKind.APPROVE
    ]
    notify(
        uow,
        recipient_membership_ids=role_holders(
            session, role_codes=LOCK_NOTIFIED_ROLES, entity_id=scope.entity_id, at=uow.now
        ),
        kind=NotificationKind.PERIOD_REOPENED,
        title=REOPENED_TITLE.format(entity=scope.entity_code, period_key=scope.period_key),
        body=REOPENED_BODY.format(
            requester=_display_name(session, requester),
            period_key=scope.period_key,
            reason=request["comment"] or (reason.value if reason is not None else ""),
            approvers=" and ".join(_display_name(session, approver) for approver in approvers),
        ),
        link_path=subjects.PERIOD_LINK.format(state_id=subject_id),
        subject_type=period_rules.STATE_OBJECT,
        subject_id=subject_id,
    )
    uow.audit(
        action=REOPEN_ACTION,
        object_type=LOCK_OBJECT,
        object_id=lock_id,
        object_version="1",
        after={
            "kind": LockKind.REOPEN.value,
            "period_state_id": str(subject_id),
            "approval_request_id": str(approval_request_id),
            "previous_lock_id": None if reopened_lock_id is None else str(reopened_lock_id),
            "reason_code": None if reason is None else reason.value,
            "approvers": [str(approver) for approver in approvers],
            "reconciliations_reopened": reconciliations_reopened,
            "waivers_ended": waivers_ended,
            "task_signoffs_ended": task_signoffs_ended,
            "snapshots": "kept",
        },
        reason_code=None if reason is None else reason.value,
        comment=request["comment"],
    )


def _next_period_state(
    session: Session, scope: gates.PeriodScope, *, lock: bool, book_code: str | None = None
) -> Mapping[Any, Any] | None:
    """The state row of the entity's and book's first period after ``scope``'s, with the period's
    name; ``lock`` takes it ``FOR UPDATE NOWAIT`` — the caller holds the closing period's row and
    does not wait for another period's (04 DB-07 rev 1.113, third row): a row another transaction
    holds is SQLSTATE 55P03 (``_hold_future_next_period`` answers it by name). ``book_code``
    names another book of the same entity (the book that follows, ``_hold_future_legacy_period``);
    without it the row is of ``scope``'s book."""
    statement = (
        select(
            period_state.c.id,
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            period_state.c.state,
            period_state.c.row_version,
            period.c.name.label("period_name"),
        )
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == (scope.book_code if book_code is None else book_code),
            period.c.start_date > scope.end_date,
        )
        .order_by(period.c.start_date)
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update(of=period_state, nowait=True)
    return session.execute(statement).mappings().first()


class _OpenedSince(Exception):
    """The next period's row, locked ``NOWAIT``, is no longer ``future``: an opening committed
    between the decision's two reads. Raised inside the savepoint of the locking read, so that
    the row is given back with it (``_hold_future_next_period``; finding F11)."""


def _hold_future_next_period(
    session: Session, scope: gates.PeriodScope, *, book_code: str | None = None
) -> Mapping[Any, Any] | None:
    """BR-CLS-03's row lock, taken FIRST: directly after the closing period's row and before the
    gates, the read of the earlier periods and the freeze (04 §14.1 DB-07 rev 1.182; supervisor
    ruling R-116 (h); finding F8 of the independent review of revision 0084). Returns the
    ``future`` next period's state row, held ``FOR UPDATE`` to the decision's commit, or None when
    the next period is not ``future`` — nothing is locked then: the locking read runs inside a
    savepoint, and a row it locked that is no longer ``future`` — an opening committed between
    the two reads — is given back with the savepoint (dev-guide DG-KRN-DB-08 (1a) rev 1.218; 04
    DB-07 rev 1.229; finding F11 of the independent review of 2026-10-01). Until then such a row
    stayed locked to the decision's end, and every posting into the period that had just opened
    waited for the whole decision.

    The row is read without a lock first and locked only when it is ``future``: a posting holds
    the state row of every period it posts into ``FOR SHARE``, so a row lock on a next period that
    is already open would make the decision wait for every posting in flight there, and deadlock
    with a posting that holds lines of both periods. And it is taken ``NOWAIT``:
    ``reference.commands.open_future_period`` holds a ``future`` row while its SCH-06 re-dirtying
    takes ``combination_group`` rows, which a posting that waits for the closing period's row may
    hold — a wait here would close that cycle. Any lock on the row refuses — an opening in flight,
    or the share pin of a close command addressed to that period — and the refusal is answered by
    name (409 ``lock-conflict``, rule ``NEXT_PERIOD_HELD``; PRD ERR-78): nothing was waited for,
    and at this point nothing has been produced or stored. Until rev 1.182 this was the
    decision's LAST lock, learned after twelve datasets had been stored.

    ``book_code`` names the book that follows ``scope``'s (``_hold_future_legacy_period``; rev
    1.214): its row of the next period is taken by this rule and refused by this name — the
    sentence names the period, which the rows of the two books share."""
    seen = _next_period_state(session, scope, lock=False, book_code=book_code)
    if seen is None or _text(seen["state"]) != PeriodState.FUTURE.value:
        return None
    # A row lock lasts to the end of the transaction — or of the savepoint that took it:
    # PostgreSQL gives back the locks of a savepoint that is rolled back. Released, the
    # savepoint leaves the lock to the decision's transaction, held to its commit.
    try:
        with session.begin_nested():
            row = _next_period_state(session, scope, lock=True, book_code=book_code)
            if row is None or _text(row["state"]) != PeriodState.FUTURE.value:
                raise _OpenedSince  # leaves the savepoint by its rollback: the row is given back
    except _OpenedSince:
        return None
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
            raise
        message = NEXT_PERIOD_HELD.format(next_period=seen["period_name"], period=scope.period_name)
        refused = ProblemError(rule_id=RULE_NEXT_PERIOD_HELD, message=message)
        raise Problem("lock-conflict", message, errors=[refused]) from error
    return row


def _open_next_period(
    uow: UnitOfWork, scope: gates.PeriodScope, held: Mapping[Any, Any] | None
) -> UUID | None:
    """BR-CLS-03: the next period of the entity and book moves ``future → open`` so late events
    always have a first open period. ``held`` is that period's state row as
    ``_hold_future_next_period`` took it at the decision's start (04 DB-07 rev 1.182), or None
    when the next period was not ``future``: nothing is opened then, and no row is read here.

    The decision does not re-mark the opened period's combination groups (05 SCH-06) itself — it
    holds the closing period's state row, and the re-marking takes ``combination_group`` rows,
    which a posting may hold while it waits for that state row. It defers one
    ``PERIOD_OPEN_REDIRTY`` job for the opened period state (``period_redirty_job.defer_single``;
    supervisor rulings R-101 (a) and R-106 (a)), whose handler marks the groups in a transaction
    of its own. Until a job has succeeded the opened period's ``NO_DIRTY_GROUPS`` gate fails by
    name (``gates.gate_results``)."""
    if held is None:
        return None
    next_id = UUID(str(held["id"]))
    _record_transition(
        uow,
        state_id=next_id,
        current=held,
        from_state=PeriodState.FUTURE,
        to_state=PeriodState.OPEN,
        action=period_rules.OPEN_ACTION,
        reason_code=None,
        comment=NEXT_OPENED.format(period_key=scope.period_key),
    )
    period_redirty_job.defer_single(uow, state_id=next_id)
    return next_id


def _hold_future_legacy_period(
    session: Session, scope: gates.PeriodScope
) -> Mapping[Any, Any] | None:
    """BR-CLS-03 for the book that follows (PRD rev 1.143; 04 §14.1 DB-07 rev 1.214; supervisor
    ruling of 2026-10-01 on item PER-LEGACY-POSTING-PERIOD-1): a lock of a period of the tenant's
    primary book also opens the ``LEGACY`` book's next period. The LEGACY book has no close of
    its own (PRD ERR-76), so no lock of its own would open that period, and a LEGACY amount posts
    only in a period postable in both books (dev-guide DG-KRN-TIME-04): with the LEGACY row left
    ``future`` an amount dated in the period this decision locks finds none — until this revision
    the event was accepted and its LEGACY amount was posted in no period.

    Returns the LEGACY state row of the next period, held ``FOR UPDATE`` to the decision's
    commit, or None — nothing is locked then — unless all of these hold:

    - ``scope`` is a period of the primary book the LEGACY book follows (``followed_book``);
    - the entity keeps the LEGACY book (04 T-REF-03 ``is_enabled``): a book it does not keep
      opens no period (``reference.commands.open_future_period``);
    - the LEGACY row of the period being locked exists and is not ``future``: the periods of a
      book open in order (PRD SM-07), so a LEGACY book that begins later, or whose periods up to
      this one were never opened, is not opened ahead of them;
    - the LEGACY row of the next period is ``future``.

    The row is taken as the primary's is (``_hold_future_next_period``), directly after it:
    read without a lock first, then ``FOR UPDATE NOWAIT``, and a held row is refused by the same
    name (PRD ERR-78). A ``future`` row is no row of a window (``period_ends.window_held`` shares
    postable rows), so the hold meets no computation's share lock."""
    legacy = BookCode.LEGACY
    followed = followed_book(session, legacy)
    if followed is None or followed.value != scope.book_code:
        return None
    kept = session.execute(
        select(entity_book.c.is_enabled).where(
            entity_book.c.entity_id == scope.entity_id, entity_book.c.book_code == legacy.value
        )
    ).scalar_one_or_none()
    if kept is not True:
        return None
    own = session.execute(
        select(period_state.c.state).where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == legacy.value,
            period_state.c.period_id == scope.period_id,
        )
    ).scalar_one_or_none()
    if own is None or _text(own) == PeriodState.FUTURE.value:
        return None
    return _hold_future_next_period(session, scope, book_code=legacy.value)


def _open_legacy_period(
    uow: UnitOfWork, scope: gates.PeriodScope, held: Mapping[Any, Any] | None
) -> UUID | None:
    """The opening of the LEGACY book's next period on the row ``_hold_future_legacy_period``
    took: the transition, the audit event and the re-marking job of ``_open_next_period``, for a
    period state of its own. None when no row was held — nothing is opened then."""
    return _open_next_period(uow, scope, held)


def _persist_lock(
    uow: UnitOfWork,
    scope: gates.PeriodScope,
    *,
    kind: LockKind,
    lock_id: UUID,
    transition_id: UUID,
    from_state: PeriodState,
    to_state: PeriodState,
    action: str,
    approval_request_id: UUID,
    comment: str | None,
    certification: Sequence[Mapping[str, Any]],
    snapshot_manifest_sha256: str | None,
    heads: Mapping[str, Any],
    reason_code: ReasonCode | None = None,
    diff_report_file_id: UUID | None = None,
    cutoff_known_at: datetime | None = None,
    judgement_record_id: UUID | None = None,
) -> None:
    """Write a lock in the order the keys allow (D-98 61): the ``period_lock`` row first — its
    ``period_state_transition_id`` edge is the 0047 deferred key — then the T-REF-07 transition row
    and the ``period_state.current_lock_id`` update, both of which reference the lock through
    immediate keys. Both ids are allocated by the caller before any write. A ``REOPEN`` carries the
    request's ``reason_code``; a re-lock carries its diff report (CLO-7); a ``LOCK`` — and no other
    kind — carries the cutoff its datasets are frozen at (04 T-CLS-04 ``cutoff_known_at``;
    S15-R-18c; supervisor ruling R-40 (c))."""
    if (kind is LockKind.LOCK) != (cutoff_known_at is not None):
        raise ValueError("a LOCK record, and no other kind, names its freeze cutoff (T-CLS-04)")
    principal = uow.principal
    uow.session.execute(
        insert(period_lock).values(
            tenant_id=principal.tenant_id,
            id=lock_id,
            kind=kind.value,
            entity_id=scope.entity_id,
            book_code=scope.book_code,
            period_id=scope.period_id,
            period_state_transition_id=transition_id,
            approval_request_id=approval_request_id,
            reason_code=None if reason_code is None else reason_code.value,
            comment=comment,
            certification=list(certification),
            snapshot_manifest_sha256=snapshot_manifest_sha256,
            previous_lock_id=scope.current_lock_id,
            diff_report_file_id=diff_report_file_id,
            judgement_record_id=judgement_record_id,
            cutoff_known_at=cutoff_known_at,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            **dict(heads),
        )
    )
    _record_transition(
        uow,
        state_id=scope.state_id,
        current=_current(uow.session, scope),
        from_state=from_state,
        to_state=to_state,
        action=action,
        reason_code=reason_code,
        comment=comment,
        approval_request_id=approval_request_id,
        period_lock_id=lock_id,
        set_current_lock=True,
        transition_id=transition_id,
    )


def _request_row(session: Session, approval_request_id: UUID) -> Mapping[Any, Any]:
    row = (
        session.execute(
            select(approval_request.c.preparer_id, approval_request.c.comment).where(
                approval_request.c.id == approval_request_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return row


def _period_lock_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """The ``PERIOD_LOCK`` decision executes the lock (BUILD_SPEC CLO-6; SM-07 ``closing → closed``
    and ``closed → permanently_locked``; BR-CLS-01 to -03; REQ-CLS-009, -010).

    Checks before any write, through the pure ``period_machine``: the approver is not the
    requester (BR-CLS-02), the approver's TOTP is fresh (BR-PLT-06 for the lock decision), the
    gates still pass (the request stays ``PENDING`` otherwise, ruled Q-3). A ``LOCK`` then
    resolves the producers of other lanes by name (P4 ``record_execution`` for CTL-016; F-RPS
    registry and the EDS-6 engine for the twelve datasets) and refuses when any is absent (record
    §17): never a stub.

    Serialisation against postings (04 DB-07 rev 1.113; supervisor rulings R-31, R-40 (b) and
    R-42 (e)): the first read below takes the period's state row ``FOR UPDATE``, and the DB-07
    guards hold that row ``FOR SHARE`` for every line a transaction inserts. The decision
    therefore waits for the postings in flight and then sees their lines — in the gates, in the
    datasets and in the ledger head it records — and a posting that arrives while the lock is
    decided waits and is refused once the period is ``closed``.
    """
    session = uow.session
    scope = gates.period_scope(session, subject_id, lock=True)
    if scope is None:
        raise Problem("not-found")
    # DG-KRN-APR-05 rev 1.165 (review gap G3): the basis the approver reviewed, compared again
    # now that the row is held — a change committed while this read waited ends the decision 409
    # ``stale-approval``.
    approvals.assert_own_fresh_basis(
        uow,
        approval_request_id,
        subject_type=ApprovalSubjectType.PERIOD_LOCK,
        subject_id=subject_id,
    )
    request = _request_row(session, approval_request_id)
    principal = uow.principal
    state = PeriodState(scope.state)
    kind = LockKind.LOCK if state is PeriodState.CLOSING else LockKind.PERMANENT_LOCK
    command = (
        period_machine.Command.LOCK
        if kind is LockKind.LOCK
        else period_machine.Command.PERMANENT_LOCK
    )
    # 04 DB-07 rev 1.182 (review finding F8): the ``future`` next period's row before the gates
    # and the freeze — a held row is refused by name before anything is produced.
    next_period = _hold_future_next_period(session, scope) if kind is LockKind.LOCK else None
    # 04 DB-07 rev 1.214 (PRD BR-CLS-03 rev 1.143): for a period of the primary book, the LEGACY
    # book's row of that next period by the same rule — the book that follows has no lock of its
    # own to open it.
    legacy_period = _hold_future_legacy_period(session, scope) if kind is LockKind.LOCK else None
    results = gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id)
    outcome = period_machine.decide(
        state,
        command,
        period_machine.Guards(
            comment=request["comment"],
            gate_results=results,
            # BR-CLS-08 at execution: the request may have outlived an earlier period's state.
            earlier_postable_period=(
                _earlier_postable(session, scope) if kind is LockKind.LOCK else None
            ),
            requester_id=None
            if request["preparer_id"] is None
            else UUID(str(request["preparer_id"])),
            approver_id=principal.id,
            mfa_verified_at=principal.mfa_verified_at,
            now=uow.now,
        ),
        ctx=_context(scope),
    )
    _refuse_lock(uow, outcome, scope, results)
    if kind is LockKind.PERMANENT_LOCK:
        earlier = _earlier_unlocked(session, scope)
        if earlier is not None:
            raise Problem(
                "invalid-transition",
                period_machine.PERMANENT_LOCK_ORDER.format(
                    earlier=earlier, entity=scope.entity_code, book=scope.book_code
                ),
                errors=[
                    ProblemError(
                        rule_id=period_machine.RULE_PERMANENT_ORDER,
                        message=period_machine.PERMANENT_LOCK_ORDER.format(
                            earlier=earlier, entity=scope.entity_code, book=scope.book_code
                        ),
                    )
                ],
            )
        _execute_permanent_lock(uow, scope, results, approval_request_id, request["comment"])
        return
    # Resolve every producer another lane owns before the first write: refuse by name (record §17).
    evidence = dependencies.control_evidence()
    engine = dependencies.snapshot_engine()
    registry = dependencies.snapshot_registry()
    certified = certification.certify(results, at=uow.now)
    # D-98 candidate 139 amendment 3: the freeze instant is passed explicitly beside ``known_at``
    # (JE_POPULATION cuts and reconstructs at the freeze — S15-R-18b Q5); both are the lock's
    # freeze cutoff here (CLO-20 integration). S15-R-18c (supervisor ruling R-19 (a)): the cutoff
    # is the later of the decision's application instant and its transaction timestamp — the rule
    # contract versions are stamped by — never the application clock alone.
    cutoff = freeze.freeze_cutoff(session, uow.now)
    # 05 TXN-03 rev 1.121 (supervisor ruling R-116 (h)): the decision's transaction is idle
    # while its reader produces a dataset, and the reader's while the decision stores the files
    # and writes the lock; the connection default of 60 s ended either one.
    freeze.allow_idle(session)
    # 04 §14.1 rev 1.182 (review finding F7 (c)): ONE SYSTEM reader for the whole freeze phase —
    # the activity read, the twelve producers and both coverage reads — so the decision holds
    # two pooled connections at its peak and checks the second one out once.
    with freeze.system_unit(uow) as reader:
        freeze.allow_idle(reader.session)
        at_freeze = freeze.activity_before_freeze(principal.tenant_id, scope, reader=reader.session)
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
                engine=engine,
                reader=freeze.held(reader),
            )
        except registry.refusal as refused:
            # R-19 (c): a dataset the registry will not freeze is a named refusal, never a bare 500
            raise freeze.dataset_refused(
                scope, str(getattr(refused, "kind", "")), str(getattr(refused, "reason", refused))
            ) from refused
        except snapshots.MachineArtefactRefused as refused:
            raise freeze.artefact_refused(scope, str(refused)) from refused
        # R-19 (b): nothing of the period lies beyond the cutoff the datasets were frozen at, and
        # nothing was committed into the period since the freeze began — asked here, before any lock
        # write, and again as the decision's last read; R-42 (d): under the tenant's SYSTEM scope
        freeze.assert_covered(principal.tenant_id, scope, cutoff, at_freeze, reader=reader.session)
        manifest = snapshots.manifest_of(datasets, engine=engine)
        lock_id, transition_id = new_id(), new_id()
        certified_rows = certification.certification(certified)
        # BR-CLS-07 / S15-R-20 (CLO-7): after a reopen the re-lock stores the diff against the
        # last LOCK.
        previous_lock_id = _previous_lock(session, scope)
        diff_report_file_id = None
        if previous_lock_id is not None:
            diff_report_file_id = relock_diff.store_report(
                uow,
                relock_diff.report(
                    uow,
                    previous_lock_id=previous_lock_id,
                    lock_id=lock_id,
                    manifest_sha256=manifest,
                    certification=certified_rows,
                    datasets=datasets,
                ),
                period_key=scope.period_key,
            )
        _persist_lock(
            uow,
            scope,
            kind=kind,
            lock_id=lock_id,
            transition_id=transition_id,
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=LOCK_ACTION,
            approval_request_id=approval_request_id,
            comment=request["comment"],
            certification=certified_rows,
            snapshot_manifest_sha256=manifest,
            # R-42 (e): read inside the decision, under the row lock taken above — every seal that
            # holds a line of the period is at or before this head
            heads=_heads(session, scope),
            diff_report_file_id=diff_report_file_id,
            cutoff_known_at=cutoff,
        )
        snapshots.write_lock_snapshots(uow, lock_id, datasets)
        # BS4-D-03 (BUILD_SPEC CLO-20): the LOCK step of the period's latest succeeded close run is
        # marked in this transaction, so a decision that is refused below, or answered 409 and
        # decided again, leaves that step PENDING.
        close_runs.lock_marked(uow, scope, lock_id)
        gates.store_results(uow, certified, scope)
        reconciliations_certified = _certify_reconciliations(uow, scope, lock_id)
        next_period_id = _open_next_period(uow, scope, next_period)
        legacy_period_id = _open_legacy_period(uow, scope, legacy_period)
        evidence.record_execution(
            uow,
            control_id=CONTROL_CLOSE_GATES,
            run_ref_type=evidence.run_ref_type.PERIOD_LOCK,
            run_ref_id=approval_request_id,
            population_count=len(certified),
            exception_count=0,
            result=ControlResult.PASS,
            detail={
                "gates": [
                    {
                        "gate_check_code": r.gate_check_code,
                        "status": r.status.value,
                        "count": r.count,
                    }
                    for r in certified
                ],
                "evaluated_at": uow.now.isoformat(),
                "cutoff_known_at": cutoff.isoformat(),
                "period_lock_id": str(lock_id),
            },
            entity_id=scope.entity_id,
            book_code=scope.book_code,
            period_id=scope.period_id,
        )
        # again, after every lock write
        freeze.assert_covered(principal.tenant_id, scope, cutoff, at_freeze, reader=reader.session)
    notify(
        uow,
        recipient_membership_ids=role_holders(
            session, role_codes=LOCK_NOTIFIED_ROLES, entity_id=scope.entity_id, at=uow.now
        ),
        kind=NotificationKind.PERIOD_LOCKED,
        title=LOCKED_TITLE.format(entity=scope.entity_code, period_key=scope.period_key),
        body=LOCKED_BODY.format(
            period_key=scope.period_key, entity=scope.entity_code, book=scope.book_code
        ),
        link_path=subjects.PERIOD_LINK.format(state_id=subject_id),
        subject_type=period_rules.STATE_OBJECT,
        subject_id=subject_id,
    )
    uow.audit(
        action=LOCK_ACTION,
        object_type=LOCK_OBJECT,
        object_id=lock_id,
        object_version="1",
        after={
            "kind": kind.value,
            "period_state_id": str(subject_id),
            "approval_request_id": str(approval_request_id),
            "snapshot_manifest_sha256": manifest,
            "datasets": len(datasets),
            # S15-R-18c: the instant the datasets are frozen at (the lock row's ``created_at`` is
            # the decision's application instant)
            "cutoff_known_at": cutoff.isoformat(),
            "reconciliations_certified": reconciliations_certified,
            "next_period_opened": None if next_period_id is None else str(next_period_id),
            # rev 1.214: the LEGACY book's state of the next period, opened with the primary's
            "legacy_next_period_opened": (
                None if legacy_period_id is None else str(legacy_period_id)
            ),
            "previous_lock_id": None
            if scope.current_lock_id is None
            else str(scope.current_lock_id),
            "relock_of": None if previous_lock_id is None else str(previous_lock_id),
            "diff_report_file_id": None
            if diff_report_file_id is None
            else str(diff_report_file_id),
        },
        comment=request["comment"],
    )


def _execute_permanent_lock(
    uow: UnitOfWork,
    scope: gates.PeriodScope,
    results: Sequence[gates.GateResult],
    approval_request_id: UUID,
    comment: str | None,
) -> None:
    """``closed → permanently_locked`` with a ``PERMANENT_LOCK`` record; no snapshots and no CTL-016
    row (the lock already certified the period)."""
    session = uow.session
    lock_id, transition_id = new_id(), new_id()
    _persist_lock(
        uow,
        scope,
        kind=LockKind.PERMANENT_LOCK,
        lock_id=lock_id,
        transition_id=transition_id,
        from_state=PeriodState.CLOSED,
        to_state=PeriodState.PERMANENTLY_LOCKED,
        action=PERMANENT_LOCK_ACTION,
        approval_request_id=approval_request_id,
        comment=comment,
        certification=certification.certification(results),
        snapshot_manifest_sha256=None,
        heads=_heads(session, scope),
    )
    uow.audit(
        action=PERMANENT_LOCK_ACTION,
        object_type=LOCK_OBJECT,
        object_id=lock_id,
        object_version="1",
        after={
            "kind": LockKind.PERMANENT_LOCK.value,
            "period_state_id": str(scope.state_id),
            "approval_request_id": str(approval_request_id),
            "previous_lock_id": None
            if scope.current_lock_id is None
            else str(scope.current_lock_id),
        },
        comment=comment,
    )


def _period_lock_unchanged(_: UnitOfWork, __: UUID, ___: UUID) -> None:
    """A rejected or voided lock request changes nothing: the period stays where it was."""


subjects.register_lifecycle(
    ApprovalSubjectType.PERIOD_LOCK,
    subjects.SubjectLifecycle(
        on_approved=_period_lock_approved,
        on_rejected=_period_lock_unchanged,
        on_voided=_period_lock_unchanged,
    ),
)
subjects.register_lifecycle(
    ApprovalSubjectType.PERIOD_REOPEN,
    subjects.SubjectLifecycle(
        on_approved=_period_reopen_approved,
        on_rejected=_period_lock_unchanged,
        on_voided=_period_lock_unchanged,
    ),
)
