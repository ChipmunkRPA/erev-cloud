"""SM-07 period state machine as a pure decision function (PRD §5.2 SM-07; §5.3 BR-CLS-01 to -05,
BR-CLS-08; BR-PLT-06, BR-PLT-08; §5.5 ERR-02, ERR-14, ERR-16, ERR-28, ERR-42, ERR-65; 04 §14.1
DB-07, E-110 table 3.4-R; 04 §16.8 ``request-lock``, ``request-reopen``,
``request-permanent-lock``).

``decide(state, command, guards, ctx)`` returns, without reading a session:

- ``Refusal`` (``certification.Refusal``) for a pair outside ``TRANSITIONS`` (409
  ``invalid-transition``, rule DB-07, code ``EREV-PER-001``, the command's message) or a failed
  guard (422 ``validation-failed`` with the field and rule; 409 ``close-gates-failed`` ERR-14; 409
  ``later-period-closed`` ERR-16; 409 ``earlier-period-open`` ERR-65; 403 ``self-approval``
  ERR-02; 403 ``mfa-step-up-required`` ERR-28);
- ``Accepted`` with the state ``Transition`` (None for a request, whose approval executes the
  change) and the ``Effect`` rows the DB-bound handler performs;
- ``Pending`` or ``Rejected`` for an execution whose approval quorum (``approvals.quorum``) is not
  met or was rejected.

The ``TRANSITIONS`` pairs equal ``domain/reference/periods.ALLOWED_TRANSITIONS`` (creation aside)
and the DB-07 trigger pairs; ``close/commands.py`` and ``reference/periods.py`` keep the messages
this module repeats, and ``tests/unit/close/test_period_machine.py`` pins them equal. The commands
of CLO-3 (``start_close``, ``cancel_close``, ``open``) already behave as this table states; CLO-6
and CLO-7 wire the lock, reopen and permanent-lock rows (F-CLO preparation record
``docs/reviews/loop/prod/F-CLO-prep.md`` §5).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from erev_api.approvals import quorum
from erev_api.auth import mfa
from erev_api.domain.close import certification, gates
from erev_api.domain.close.certification import Refusal
from erev_api.enums import PeriodState, ReasonCode
from erev_api.problems import ProblemError

__all__ = [
    "Accepted",
    "Command",
    "Context",
    "Effect",
    "Guards",
    "Pending",
    "Refusal",
    "Rejected",
    "Transition",
    "decide",
    "pairs",
]


class Command(StrEnum):
    OPEN = "open"
    START_CLOSE = "start_close"
    CANCEL_CLOSE = "cancel_close"
    REQUEST_LOCK = "request_lock"
    LOCK = "lock"
    REQUEST_REOPEN = "request_reopen"
    REOPEN = "reopen"
    REQUEST_PERMANENT_LOCK = "request_permanent_lock"
    PERMANENT_LOCK = "permanent_lock"


class Effect(StrEnum):
    """What the DB-bound handler performs for an accepted outcome (SM-07 effects column)."""

    TRANSITION_AUDITED = "audit:period_state_transition"  # REQ-CLS-001
    SOFT_CLOSE_RESTRICTIONS = "soft_close:BR-CLS-04"
    REQUEST_PERIOD_LOCK = "approval_request:PERIOD_LOCK:LOCK"
    REQUEST_PERMANENT_LOCK = "approval_request:PERIOD_LOCK:PERMANENT_LOCK"
    REQUEST_PERIOD_REOPEN = "approval_request:PERIOD_REOPEN"
    CONTROLLER_CERTIFIED = "gate:CONTROLLER_CERTIFIED:PASSED"
    PERIOD_LOCK_LOCK = "period_lock:LOCK"
    PERIOD_LOCK_REOPEN = "period_lock:REOPEN"
    PERIOD_LOCK_PERMANENT = "period_lock:PERMANENT_LOCK"
    LOCK_SNAPSHOTS = "lock_snapshot:12"
    SNAPSHOTS_KEPT = "lock_snapshot:kept"
    RECONCILIATIONS_CERTIFIED = "reconciliation:CERTIFIED"
    NEXT_PERIOD_OPEN = "next_period:future->open"  # BR-CLS-03
    NOTIFY_PERIOD_LOCKED = "notification:PERIOD_LOCKED"  # NTF-06
    NOTIFY_PERIOD_REOPENED = "notification:PERIOD_REOPENED"  # NTF-07


# SM-07 rows: the states a command executes from and the state it reaches.
TRANSITIONS: Final[Mapping[Command, tuple[frozenset[PeriodState], PeriodState]]] = {
    Command.OPEN: (frozenset({PeriodState.FUTURE}), PeriodState.OPEN),
    Command.START_CLOSE: (frozenset({PeriodState.OPEN, PeriodState.REOPENED}), PeriodState.CLOSING),
    Command.CANCEL_CLOSE: (frozenset({PeriodState.CLOSING}), PeriodState.OPEN),
    Command.LOCK: (frozenset({PeriodState.CLOSING}), PeriodState.CLOSED),
    Command.REOPEN: (frozenset({PeriodState.CLOSED}), PeriodState.REOPENED),
    Command.PERMANENT_LOCK: (frozenset({PeriodState.CLOSED}), PeriodState.PERMANENTLY_LOCKED),
}
# SM-07 "End soft close" has two targets (PRD rev 1.99; 04 §16.8 rev 1.170): a soft close returns
# to the state it started from. TRANSITIONS names ``open``, where a period that was never locked
# returns; a period that has been locked before was soft-closed from ``reopened`` and returns
# there, so that BR-CLS-06 and DB-07's ``is_post_reopen`` keep holding for it.
CANCEL_CLOSE_AFTER_LOCK: Final = PeriodState.REOPENED
# A request is refused from the states its execution cannot start from.
EXECUTES: Final[Mapping[Command, Command]] = {
    Command.REQUEST_LOCK: Command.LOCK,
    Command.REQUEST_REOPEN: Command.REOPEN,
    Command.REQUEST_PERMANENT_LOCK: Command.PERMANENT_LOCK,
}


def pairs() -> frozenset[tuple[PeriodState, PeriodState]]:
    """The (from, to) pairs of SM-07, equal to DB-07 and ``periods.ALLOWED_TRANSITIONS``."""
    listed = frozenset(
        (from_state, to_state)
        for allowed_from, to_state in TRANSITIONS.values()
        for from_state in allowed_from
    )
    return listed | {(PeriodState.CLOSING, CANCEL_CLOSE_AFTER_LOCK)}


def cancel_close_target(*, locked_before: bool) -> PeriodState:
    """Where an ended soft close returns the period (SM-07): ``reopened`` when the period has been
    locked before, else ``open``."""
    return CANCEL_CLOSE_AFTER_LOCK if locked_before else TRANSITIONS[Command.CANCEL_CLOSE][1]


# Messages. The first three and PREVIOUS_FUTURE repeat ``reference/periods.py`` and
# ``close/commands.py`` verbatim.
NOT_FUTURE: Final = "Only a future period opens. {period_key} is {state}."
NOT_STARTABLE: Final = "Soft close starts from an open or reopened period. {period_key} is {state}."
NOT_CLOSING: Final = "Only a period in soft close returns to open. {period_key} is {state}."
NOT_LOCKABLE: Final = "Only a period in soft close locks. {period_key} is {state}."
NOT_REOPENABLE: Final = "Only a closed period reopens. {period_key} is {state}."
NOT_PERMANENTLY_LOCKABLE: Final = (
    "Only a closed period is permanently locked. {period_key} is {state}."
)
PREVIOUS_FUTURE: Final = (
    "The previous period of {entity} in book {book} is future, so {period_key} does not open yet."
)
_PAIR_MESSAGES: Final[Mapping[Command, str]] = {
    Command.OPEN: NOT_FUTURE,
    Command.START_CLOSE: NOT_STARTABLE,
    Command.CANCEL_CLOSE: NOT_CLOSING,
    Command.LOCK: NOT_LOCKABLE,
    Command.REOPEN: NOT_REOPENABLE,
    Command.PERMANENT_LOCK: NOT_PERMANENTLY_LOCKABLE,
}
RULE_TRANSITION: Final = "DB-07"
TRANSITION_CODE: Final = "EREV-PER-001"
RULE_REASON: Final = "REASON_CODE_NOT_ALLOWED"
# 04 table 3.4-R subsets (E-110).
CANCEL_CLOSE_REASONS: Final[frozenset[ReasonCode]] = frozenset(
    {ReasonCode.CLOSE_RESTARTED, ReasonCode.DATA_CORRECTION_PENDING, ReasonCode.OTHER}
)
REASON_NOT_ALLOWED: Final = (
    "End soft close with the reason CLOSE_RESTARTED, DATA_CORRECTION_PENDING or OTHER."
)
REOPEN_REASONS: Final[frozenset[ReasonCode]] = frozenset(
    {
        ReasonCode.ERROR_CORRECTION,
        ReasonCode.LATE_SOURCE_DATA,
        ReasonCode.AUDIT_ADJUSTMENT,
        ReasonCode.OTHER,
    }
)
REOPEN_REASON_NOT_ALLOWED: Final = (
    "Reopen with the reason ERROR_CORRECTION, LATE_SOURCE_DATA, AUDIT_ADJUSTMENT or OTHER."
)
RULE_COMMENT: Final = "BR-PLT-08"
MIN_COMMENT: Final = 10
COMMENT_TOO_SHORT: Final = "Enter a comment of at least 10 characters."
RULE_START_COMMENT: Final = "SM-07"
COMMENT_REQUIRED: Final = "Enter a comment."
RULE_LATER_PERIOD: Final = "BR-CLS-05"
LATER_PERIOD_CLOSED: Final = (  # ERR-16, verbatim
    "Reopen {later} first. A later period of {entity} in book {book} is closed."
)
# BR-CLS-08 (supervisor ruling R-6, CLO-LOCK-ORDER-1): the ordinary lock is chronological.
RULE_EARLIER_PERIOD: Final = "BR-CLS-08"
EARLIER_PERIOD_OPEN: Final = (  # ERR-65, verbatim
    "Lock {earlier} first. An earlier period of {entity} in book {book} is not closed."
)
RULE_PERMANENT_ORDER: Final = "SM-07"
PERMANENT_LOCK_ORDER: Final = (
    "Permanently lock {earlier} first. Every earlier period of {entity} in book {book} must be "
    "permanently locked."
)
RULE_SUBMITTER: Final = "BR-CLS-02"
SELF_APPROVAL_CODE: Final = "EREV-APR-001"
SELF_APPROVAL_DETAIL: Final = "You prepared this item, so another user must approve it."  # ERR-02
RULE_STEP_UP: Final = "BR-PLT-06"
ONE_FIELD: Final = "1 field needs attention."  # ERR-08 for one field
REOPEN_PENDING: Final = "Two approvals holding period.reopen_approve, at least one a Controller."
REOPEN_REJECTED: Final = "The reopen request was rejected."


@dataclass(frozen=True, slots=True)
class Context:
    period_key: str
    entity_code: str
    book_code: str


@dataclass(frozen=True, slots=True)
class Guards:
    """The facts a command's guards read. A handler raises ``ValueError`` when a fact it needs is
    missing (gate results for a lock; the clock for a step-up check)."""

    comment: str | None = None
    reason_code: ReasonCode | None = None
    gate_results: Sequence[gates.GateResult] | None = None
    later_closed_period_key: str | None = (
        None  # BR-CLS-05: a later closed or permanently locked period
    )
    earlier_unlocked_period_key: str | None = (
        None  # SM-07: an earlier period not permanently locked
    )
    earlier_postable_period: str | None = (
        None  # BR-CLS-08: the name of an earlier open, closing or reopened period
    )
    previous_period_future: bool = False  # SM-07 future → open guard
    locked_before: bool = False  # SM-07 End soft close: the period is under a REOPEN record
    requester_id: UUID | None = None
    approver_id: UUID | None = None
    mfa_verified_at: datetime | None = None
    now: datetime | None = None
    approvals: Sequence[quorum.Decision] = ()


@dataclass(frozen=True, slots=True)
class Transition:
    from_state: PeriodState
    to_state: PeriodState
    command: Command


@dataclass(frozen=True, slots=True)
class Accepted:
    transition: Transition | None
    effects: tuple[Effect, ...]


@dataclass(frozen=True, slots=True)
class Pending:
    reason: str


@dataclass(frozen=True, slots=True)
class Rejected:
    reason: str


Outcome = Accepted | Pending | Rejected | Refusal
_Handler = Callable[[PeriodState, Guards, Context], Outcome]


def decide(state: PeriodState, command: Command, guards: Guards, *, ctx: Context) -> Outcome:
    """The SM-07 outcome of ``command`` from ``state`` under ``guards``."""
    state = PeriodState(state)
    command = Command(command)
    executed = EXECUTES.get(command, command)
    allowed_from, _ = TRANSITIONS[executed]
    if state not in allowed_from:
        message = _PAIR_MESSAGES[executed].format(period_key=ctx.period_key, state=state.value)
        return Refusal(
            "invalid-transition",
            message,
            rule_id=RULE_TRANSITION,
            code=TRANSITION_CODE,
            errors=(ProblemError(rule_id=RULE_TRANSITION, message=message),),
        )
    return _HANDLERS[command](state, guards, ctx)


def _field(field: str, rule_id: str, message: str) -> Refusal:
    return Refusal(
        "validation-failed",
        ONE_FIELD,
        rule_id=rule_id,
        errors=(ProblemError(field=field, rule_id=rule_id, message=message),),
    )


def _comment_ok(comment: str | None) -> bool:
    return len((comment or "").strip()) >= MIN_COMMENT  # BR-PLT-08


def _transition(state: PeriodState, command: Command) -> Transition:
    _, to_state = TRANSITIONS[command]
    return Transition(state, to_state, command)


def _gate_results(guards: Guards) -> Sequence[gates.GateResult]:
    if guards.gate_results is None:
        raise ValueError("a lock decision needs the fourteen gate results")
    return guards.gate_results


def _step_up(guards: Guards) -> Refusal | None:
    if guards.now is None:
        raise ValueError("a step-up check needs the clock")
    if not mfa.step_up_fresh_at(guards.mfa_verified_at, guards.now):
        return Refusal("mfa-step-up-required", mfa.STEP_UP_REQUIRED, rule_id=RULE_STEP_UP)
    return None


def _later_period_closed(guards: Guards, ctx: Context) -> Refusal | None:
    """BR-CLS-05 (ERR-16): a later closed or permanently locked period refuses the reopen request
    and its execution alike."""
    if guards.later_closed_period_key is None:
        return None
    message = LATER_PERIOD_CLOSED.format(
        later=guards.later_closed_period_key, entity=ctx.entity_code, book=ctx.book_code
    )
    return Refusal("later-period-closed", message, rule_id=RULE_LATER_PERIOD)


def _earlier_period_open(guards: Guards, ctx: Context) -> Refusal | None:
    """BR-CLS-08 (ERR-65; supervisor ruling R-6): an earlier postable period — ``open``,
    ``closing`` or ``reopened`` — refuses the lock request and its execution alike. A posting into
    it would move the opening balance of the period being locked after its figures were frozen."""
    if guards.earlier_postable_period is None:
        return None
    message = EARLIER_PERIOD_OPEN.format(
        earlier=guards.earlier_postable_period, entity=ctx.entity_code, book=ctx.book_code
    )
    return Refusal("earlier-period-open", message, rule_id=RULE_EARLIER_PERIOD)


def _self_approval(rule_id: str) -> Refusal:
    return Refusal("self-approval", SELF_APPROVAL_DETAIL, rule_id=rule_id, code=SELF_APPROVAL_CODE)


def _open(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if guards.previous_period_future:
        message = PREVIOUS_FUTURE.format(
            entity=ctx.entity_code, book=ctx.book_code, period_key=ctx.period_key
        )
        return Refusal("invalid-transition", message, rule_id=RULE_TRANSITION, code=TRANSITION_CODE)
    return Accepted(_transition(state, Command.OPEN), (Effect.TRANSITION_AUDITED,))


def _start_close(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if not (guards.comment or "").strip():
        return _field("comment", RULE_START_COMMENT, COMMENT_REQUIRED)
    return Accepted(
        _transition(state, Command.START_CLOSE),
        (Effect.SOFT_CLOSE_RESTRICTIONS, Effect.TRANSITION_AUDITED),
    )


def _cancel_close(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if guards.reason_code not in CANCEL_CLOSE_REASONS:
        return _field("reason_code", RULE_REASON, REASON_NOT_ALLOWED)
    if not _comment_ok(guards.comment):
        return _field("comment", RULE_COMMENT, COMMENT_TOO_SHORT)
    returned = Transition(
        state, cancel_close_target(locked_before=guards.locked_before), Command.CANCEL_CLOSE
    )
    return Accepted(returned, (Effect.TRANSITION_AUDITED,))


def _request_lock(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if not _comment_ok(guards.comment):
        return _field("certification_comment", RULE_COMMENT, COMMENT_TOO_SHORT)
    refused = _earlier_period_open(guards, ctx)
    if refused is not None:
        return refused
    results = _gate_results(guards)
    if not certification.lock_allowed(results):
        return certification.refusal(results)
    return Accepted(None, (Effect.REQUEST_PERIOD_LOCK,))


def _lock(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if guards.approver_id is not None and guards.approver_id == guards.requester_id:
        return _self_approval(RULE_SUBMITTER)
    refused = _step_up(guards)
    if refused is not None:
        return refused
    # BR-CLS-08 holds at execution too, on the fact supplied for that moment: a request can
    # outlive the state of an earlier period (supervisor ruling R-6).
    refused = _earlier_period_open(guards, ctx)
    if refused is not None:
        return refused
    results = _gate_results(guards)
    if not certification.lock_allowed(results):
        return certification.refusal(results)
    return Accepted(
        _transition(state, Command.LOCK),
        (
            Effect.CONTROLLER_CERTIFIED,
            Effect.PERIOD_LOCK_LOCK,
            Effect.LOCK_SNAPSHOTS,
            Effect.RECONCILIATIONS_CERTIFIED,
            Effect.NEXT_PERIOD_OPEN,
            Effect.NOTIFY_PERIOD_LOCKED,
            Effect.TRANSITION_AUDITED,
        ),
    )


def _request_reopen(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if guards.reason_code not in REOPEN_REASONS:
        return _field("reason_code", RULE_REASON, REOPEN_REASON_NOT_ALLOWED)
    if not _comment_ok(guards.comment):
        return _field("comment", RULE_COMMENT, COMMENT_TOO_SHORT)
    refused = _later_period_closed(guards, ctx)
    if refused is not None:
        return refused
    return Accepted(None, (Effect.REQUEST_PERIOD_REOPEN,))


def _reopen(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if guards.requester_id is not None and any(
        guards.requester_id in decision.acting() for decision in guards.approvals
    ):
        return _self_approval(RULE_SUBMITTER)
    # F-CLO-R2: BR-CLS-05 holds at execution too, on the fact supplied for that moment (a later
    # period may have closed between the request and the final decision).
    refused = _later_period_closed(guards, ctx)
    if refused is not None:
        return refused
    outcome = quorum.step_outcome(guards.approvals, quorum.REOPEN_QUORUM)
    if outcome is quorum.StepOutcome.REJECTED:
        return Rejected(REOPEN_REJECTED)
    if outcome is quorum.StepOutcome.PENDING:
        return Pending(REOPEN_PENDING)
    return Accepted(
        _transition(state, Command.REOPEN),
        (
            Effect.PERIOD_LOCK_REOPEN,
            Effect.SNAPSHOTS_KEPT,
            Effect.NOTIFY_PERIOD_REOPENED,
            Effect.TRANSITION_AUDITED,
        ),
    )


def _request_permanent_lock(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if not _comment_ok(guards.comment):
        return _field("comment", RULE_COMMENT, COMMENT_TOO_SHORT)
    if guards.earlier_unlocked_period_key is not None:
        message = PERMANENT_LOCK_ORDER.format(
            earlier=guards.earlier_unlocked_period_key, entity=ctx.entity_code, book=ctx.book_code
        )
        return Refusal("invalid-transition", message, rule_id=RULE_PERMANENT_ORDER)
    return Accepted(None, (Effect.REQUEST_PERMANENT_LOCK,))


def _permanent_lock(state: PeriodState, guards: Guards, ctx: Context) -> Outcome:
    if guards.approver_id is not None and guards.approver_id == guards.requester_id:
        return _self_approval(RULE_SUBMITTER)
    refused = _step_up(guards)
    if refused is not None:
        return refused
    return Accepted(
        _transition(state, Command.PERMANENT_LOCK),
        (Effect.PERIOD_LOCK_PERMANENT, Effect.TRANSITION_AUDITED),
    )


_HANDLERS: Final[Mapping[Command, _Handler]] = {
    Command.OPEN: _open,
    Command.START_CLOSE: _start_close,
    Command.CANCEL_CLOSE: _cancel_close,
    Command.REQUEST_LOCK: _request_lock,
    Command.LOCK: _lock,
    Command.REQUEST_REOPEN: _request_reopen,
    Command.REOPEN: _reopen,
    Command.REQUEST_PERMANENT_LOCK: _request_permanent_lock,
    Command.PERMANENT_LOCK: _permanent_lock,
}
