"""Replay plan for period states and locks in a sandbox load, pure part (ruling D-98 candidate 25 on
the lane's Q-3; 05 §10 SBX-04; 04 T-REF-06, T-REF-07, T-CLS-04; DB-07).

SBX-04 loads every period ``open`` and then replays the source's period states and locks "through
the normal transitions to match the source". The three REPLAY_REFERENCE datasets (``period_state``,
``period_state_transition``, ``period_lock``) are the replay source; this module turns them into an
ordered plan without a database:

* **ordering contract** — transitions by (``created_at``, ``id``); a lock is emitted right after
  the transition that created it (``period_lock.period_state_transition_id``);
* **validation** — every (``from_state``, ``to_state``) pair is one of
  ``domain.reference.periods.ALLOWED_TRANSITIONS``; the chain of each ``period_state`` is
  contiguous (the first transition starts from NULL, each later one from the previous ``to_state``);
  a lock's kind agrees with its transition (``LOCK`` → ``closed``, ``REOPEN`` → ``reopened``,
  ``PERMANENT_LOCK`` → ``permanently_locked``); ``previous_lock_id`` names an earlier lock of the
  same period state; a transition's ``period_lock_id`` names the lock attached to it;
* **end state** — the last ``to_state`` and the last lock per period state, compared with the source
  ``period_state`` rows so the replay driver can prove it reached the source's state.

Executing the transitions (the normal commands under the sandbox tenant context) belongs to the
integration lane after GATE-RPS / GATE-PLF.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

from erev_api.domain.reference.periods import ALLOWED_TRANSITIONS
from erev_api.enums import LockKind, PeriodState

__all__ = [
    "LOCK_TARGETS",
    "EndState",
    "ReplayStep",
    "end_state",
    "replay_plan",
    "verify_end_state",
]

# E-63 lock kind → the ``to_state`` of the transition that carries it (T-CLS-04, DB-07).
LOCK_TARGETS: Final[Mapping[LockKind, PeriodState]] = MappingProxyType(
    {
        LockKind.LOCK: PeriodState.CLOSED,
        LockKind.REOPEN: PeriodState.REOPENED,
        LockKind.PERMANENT_LOCK: PeriodState.PERMANENTLY_LOCKED,
    }
)
StepKind = Literal["transition", "lock"]


@dataclass(frozen=True, slots=True)
class BlockedPeriod:
    """A period whose replay a normal close command refused (D-98 137 ruling (3)): it stays at
    ``reached``; ``attempted`` names the step and ``reason`` the refusal."""

    period_state_id: UUID
    entity_id: UUID
    book_code: str
    period_id: UUID
    attempted: str
    reached: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReplayStep:
    """One replayed transition or lock, in plan order."""

    kind: StepKind
    at: datetime
    id: UUID
    period_state_id: UUID
    entity_id: UUID
    book_code: str
    period_id: UUID
    from_state: PeriodState | None  # transitions
    to_state: PeriodState | None  # transitions
    reason_code: str | None
    approval_request_id: UUID | None
    lock_kind: LockKind | None  # locks
    transition_id: UUID | None  # locks: the transition that created the lock
    previous_lock_id: UUID | None  # locks


@dataclass(frozen=True, slots=True)
class EndState:
    state: PeriodState
    current_lock_id: UUID | None
    entity_id: UUID | None = None
    book_code: str | None = None
    period_id: UUID | None = None

    @property
    def identity(self) -> tuple[UUID | None, str | None, UUID | None]:
        return (self.entity_id, self.book_code, self.period_id)


def _aware(value: Any, what: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what}: a timezone-aware datetime is required")
    return value


def _state(value: Any, what: str) -> PeriodState | None:
    if value is None:
        return None
    try:
        return PeriodState(str(value))
    except ValueError as error:
        raise ValueError(f"{what}: unknown period state {value!r}") from error


def _uuid(value: Any, what: str) -> UUID:
    if not isinstance(value, UUID):
        raise ValueError(f"{what}: a UUID is required")
    return value


def _identity(row: Mapping[str, Any], what: str) -> tuple[UUID, str, UUID]:
    """The (entity, book, period) tuple a period state, transition or lock belongs to."""
    return (_uuid(row["entity_id"], what), str(row["book_code"]), _uuid(row["period_id"], what))


def replay_plan(
    states: Iterable[Mapping[str, Any]],
    transitions: Iterable[Mapping[str, Any]],
    locks: Iterable[Mapping[str, Any]],
) -> tuple[ReplayStep, ...]:
    """The ordered, validated plan; ``ValueError`` names the first inconsistency. The result does
    not depend on the input order of the three datasets."""
    state_rows = {_uuid(row["id"], "period_state.id"): row for row in states}
    identity = {
        state_id: _identity(row, f"period_state {state_id}") for state_id, row in state_rows.items()
    }
    lock_rows = {_uuid(row["id"], "period_lock.id"): row for row in locks}
    locks_by_transition: dict[UUID, UUID] = {}
    for lock_id, lock in lock_rows.items():
        transition_id = _uuid(lock["period_state_transition_id"], f"period_lock {lock_id}")
        if transition_id in locks_by_transition:
            raise ValueError(f"period_state_transition {transition_id}: carries two locks")
        locks_by_transition[transition_id] = lock_id
    ordered = sorted(
        transitions,
        key=lambda row: (
            _aware(row["created_at"], "period_state_transition.created_at"),
            str(_uuid(row["id"], "period_state_transition.id")),
        ),
    )
    plan: list[ReplayStep] = []
    last_state: dict[UUID, PeriodState | None] = {}
    seen_transitions: set[UUID] = set()
    lock_position: dict[UUID, tuple[UUID, int]] = {}  # lock id → (period_state_id, index)
    for row in ordered:
        transition_id = _uuid(row["id"], "period_state_transition.id")
        if transition_id in seen_transitions:
            raise ValueError(f"period_state_transition {transition_id}: duplicated")
        seen_transitions.add(transition_id)
        state_id = _uuid(row["period_state_id"], f"period_state_transition {transition_id}")
        if state_id not in state_rows:
            raise ValueError(
                f"period_state_transition {transition_id}: unknown period_state {state_id}"
            )
        from_state = _state(row.get("from_state"), f"period_state_transition {transition_id}")
        to_state = _state(row["to_state"], f"period_state_transition {transition_id}")
        if to_state is None:
            raise ValueError(f"period_state_transition {transition_id}: to_state is required")
        if (from_state, to_state) not in ALLOWED_TRANSITIONS:
            raise ValueError(
                f"period_state_transition {transition_id}: {from_state} → {to_state} is not an "
                "allowed transition (DB-07)"
            )
        previous = last_state.get(state_id, None)
        if state_id in last_state and previous != from_state:
            raise ValueError(
                f"period_state_transition {transition_id}: from_state {from_state} breaks the "
                f"chain after {previous}"
            )
        if state_id not in last_state and from_state is not None:
            raise ValueError(
                f"period_state_transition {transition_id}: the first transition of a period "
                "state starts from NULL"
            )
        last_state[state_id] = to_state
        at = _aware(row["created_at"], "period_state_transition.created_at")
        entity_id, book_code, period_id = _identity(row, f"period_state_transition {transition_id}")
        if (entity_id, book_code, period_id) != identity[state_id]:
            raise ValueError(
                f"period_state_transition {transition_id}: (entity, book, period) differs from "
                f"its period state {state_id} (F-SNP-R4)"
            )
        attached = locks_by_transition.get(transition_id)
        declared = row.get("period_lock_id")
        if declared is not None and declared != attached:
            raise ValueError(
                f"period_state_transition {transition_id}: period_lock_id {declared} is not the "
                "lock attached to it"
            )
        plan.append(
            ReplayStep(
                "transition",
                at,
                transition_id,
                state_id,
                entity_id,
                book_code,
                period_id,
                from_state,
                to_state,
                None if row.get("reason_code") is None else str(row["reason_code"]),
                row.get("approval_request_id"),
                None,
                None,
                None,
            )
        )
        if attached is None:
            continue
        lock = lock_rows[attached]
        kind = LockKind(str(lock["kind"]))
        if LOCK_TARGETS[kind] is not to_state:
            raise ValueError(
                f"period_lock {attached}: kind {kind} does not fit a transition to {to_state}"
            )
        if _identity(lock, f"period_lock {attached}") != (entity_id, book_code, period_id):
            raise ValueError(
                f"period_lock {attached}: (entity, book, period) differs from its transition "
                f"{transition_id} (F-SNP-R4)"
            )
        previous_lock = lock.get("previous_lock_id")
        if previous_lock is not None:
            earlier = lock_position.get(previous_lock)
            if earlier is None or earlier[0] != state_id:
                raise ValueError(
                    f"period_lock {attached}: previous_lock_id {previous_lock} is not an earlier "
                    "lock of the same period state"
                )
        lock_position[attached] = (state_id, len(plan))
        plan.append(
            ReplayStep(
                "lock",
                _aware(lock["created_at"], "period_lock.created_at"),
                attached,
                state_id,
                _uuid(lock["entity_id"], f"period_lock {attached}"),
                str(lock["book_code"]),
                period_id,
                None,
                None,
                None if lock.get("reason_code") is None else str(lock["reason_code"]),
                lock.get("approval_request_id"),
                kind,
                transition_id,
                previous_lock,
            )
        )
    orphan = sorted(str(t) for t in set(locks_by_transition) - seen_transitions)
    if orphan:
        raise ValueError(f"period_lock rows name unknown transitions {orphan}")
    return tuple(plan)


def end_state(plan: Iterable[ReplayStep]) -> Mapping[UUID, EndState]:
    """Per period state: the last ``to_state`` and the last lock the plan produces."""
    states: dict[UUID, PeriodState] = {}
    locks: dict[UUID, UUID | None] = {}
    identities: dict[UUID, tuple[UUID, str, UUID]] = {}
    for step in plan:
        identities[step.period_state_id] = (step.entity_id, step.book_code, step.period_id)
        if step.kind == "transition" and step.to_state is not None:
            states[step.period_state_id] = step.to_state
        elif step.kind == "lock":
            locks[step.period_state_id] = step.id
    return MappingProxyType(
        {
            state_id: EndState(state, locks.get(state_id), *identities[state_id])
            for state_id, state in states.items()
        }
    )


def verify_end_state(
    plan: Iterable[ReplayStep], states: Iterable[Mapping[str, Any]]
) -> tuple[str, ...]:
    """The findings where the replayed end state differs from the source ``period_state`` rows
    (``state``, ``current_lock_id``); empty when the replay reaches the source's state."""
    reached = end_state(plan)
    findings: list[str] = []
    for row in states:
        state_id = _uuid(row["id"], "period_state.id")
        expected = _state(row["state"], f"period_state {state_id}")
        got = reached.get(state_id)
        if got is None:
            if expected is not PeriodState.FUTURE or row.get("current_lock_id") is not None:
                findings.append(f"period_state {state_id}: no transition replayed")
            continue
        if got.identity != _identity(row, f"period_state {state_id}"):
            findings.append(
                f"period_state {state_id}: replay identity (entity, book, period) {got.identity} "
                f"differs from the source row (F-SNP-R4)"
            )
        if got.state is not expected:
            findings.append(f"period_state {state_id}: replay ends {got.state}, source {expected}")
        if got.current_lock_id != row.get("current_lock_id"):
            findings.append(
                f"period_state {state_id}: replay lock {got.current_lock_id}, source "
                f"{row.get('current_lock_id')}"
            )
    return tuple(findings)
