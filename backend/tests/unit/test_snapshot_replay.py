"""Replay plan for period states and locks (F-SNP preparation; ruling D-98 candidate 25 on Q-3;
SBX-04; T-REF-07, T-CLS-04; DB-07). No database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.platform import snapshot_replay as sr
from erev_api.enums import LockKind, PeriodState
from hypothesis import given
from hypothesis import strategies as st

T0 = datetime(2026, 1, 1, tzinfo=UTC)
ENTITY = UUID(int=0xE)
PERIOD_1 = UUID(int=0x10)
PERIOD_2 = UUID(int=0x20)
STATE_1 = UUID(int=0x11)
STATE_2 = UUID(int=0x21)
BOOK = "ASC606"


def _u(n: int) -> UUID:
    return UUID(int=n)


def _transition(
    n: int,
    state: UUID,
    period: UUID,
    from_state: str | None,
    to_state: str,
    minutes: int,
    lock: UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": _u(n),
        "period_state_id": state,
        "entity_id": ENTITY,
        "book_code": BOOK,
        "period_id": period,
        "from_state": from_state,
        "to_state": to_state,
        "reason_code": None,
        "approval_request_id": None,
        "period_lock_id": lock,
        "created_at": T0 + timedelta(minutes=minutes),
    }


def _lock(
    n: int, kind: str, transition: UUID, minutes: int, previous: UUID | None = None
) -> dict[str, Any]:
    return {
        "id": _u(n),
        "kind": kind,
        "entity_id": ENTITY,
        "book_code": BOOK,
        "period_id": PERIOD_1,
        "period_state_transition_id": transition,
        "approval_request_id": _u(900 + n),
        "reason_code": None,
        "previous_lock_id": previous,
        "created_at": T0 + timedelta(minutes=minutes),
    }


TRANSITIONS = [
    _transition(1, STATE_1, PERIOD_1, None, "future", 0),
    _transition(2, STATE_1, PERIOD_1, "future", "open", 10),
    _transition(3, STATE_1, PERIOD_1, "open", "closing", 20),
    _transition(4, STATE_1, PERIOD_1, "closing", "closed", 30, lock=_u(101)),
    _transition(5, STATE_1, PERIOD_1, "closed", "reopened", 40, lock=_u(102)),
    _transition(6, STATE_1, PERIOD_1, "reopened", "closing", 50),
    _transition(7, STATE_1, PERIOD_1, "closing", "closed", 60, lock=_u(103)),
    _transition(8, STATE_2, PERIOD_2, None, "future", 5),
    _transition(9, STATE_2, PERIOD_2, "future", "open", 15),
]
LOCKS = [
    _lock(101, "LOCK", _u(4), 30),
    _lock(102, "REOPEN", _u(5), 40, previous=_u(101)),
    _lock(103, "LOCK", _u(7), 60, previous=_u(102)),
]
STATES = [
    {
        "id": STATE_1,
        "entity_id": ENTITY,
        "book_code": BOOK,
        "period_id": PERIOD_1,
        "state": "closed",
        "current_lock_id": _u(103),
    },
    {
        "id": STATE_2,
        "entity_id": ENTITY,
        "book_code": BOOK,
        "period_id": PERIOD_2,
        "state": "open",
        "current_lock_id": None,
    },
]


def test_plan_orders_by_time_then_id_and_emits_each_lock_after_its_transition() -> None:
    plan = sr.replay_plan(STATES, TRANSITIONS, LOCKS)
    assert [(s.kind, s.id) for s in plan] == [
        ("transition", _u(1)),
        ("transition", _u(8)),
        ("transition", _u(2)),
        ("transition", _u(9)),
        ("transition", _u(3)),
        ("transition", _u(4)),
        ("lock", _u(101)),
        ("transition", _u(5)),
        ("lock", _u(102)),
        ("transition", _u(6)),
        ("transition", _u(7)),
        ("lock", _u(103)),
    ]
    assert [s.at for s in plan] == sorted(s.at for s in plan)
    lock = plan[6]
    assert lock.lock_kind is LockKind.LOCK and lock.transition_id == _u(4)
    assert plan[8].previous_lock_id == _u(101) and plan[8].lock_kind is LockKind.REOPEN
    assert plan[5].from_state is PeriodState.CLOSING and plan[5].to_state is PeriodState.CLOSED
    assert plan[0].from_state is None and plan[0].to_state is PeriodState.FUTURE


def test_ties_in_time_break_by_id() -> None:
    a = _transition(0x51, STATE_1, PERIOD_1, None, "future", 0)
    b = _transition(0x52, STATE_2, PERIOD_2, None, "future", 0)
    plan = sr.replay_plan(
        [
            {**STATES[0], "state": "future", "current_lock_id": None},
            {**STATES[1], "state": "future", "current_lock_id": None},
        ],
        [b, a],
        [],
    )
    assert [s.id for s in plan] == [_u(0x51), _u(0x52)]


@given(
    st.permutations(list(range(len(TRANSITIONS)))),
    st.permutations(list(range(len(LOCKS)))),
    st.permutations(list(range(len(STATES)))),
)
def test_plan_does_not_depend_on_input_order(
    t_order: list[int], l_order: list[int], s_order: list[int]
) -> None:
    shuffled = sr.replay_plan(
        [STATES[i] for i in s_order],
        [TRANSITIONS[i] for i in t_order],
        [LOCKS[i] for i in l_order],
    )
    assert shuffled == sr.replay_plan(STATES, TRANSITIONS, LOCKS)


def test_end_state_ties_with_the_source_period_states() -> None:
    plan = sr.replay_plan(STATES, TRANSITIONS, LOCKS)
    end = sr.end_state(plan)
    assert end[STATE_1] == sr.EndState(PeriodState.CLOSED, _u(103), ENTITY, BOOK, PERIOD_1)
    assert end[STATE_2] == sr.EndState(PeriodState.OPEN, None, ENTITY, BOOK, PERIOD_2)
    assert sr.verify_end_state(plan, STATES) == ()
    wrong = [{**STATES[0], "state": "reopened", "current_lock_id": _u(102)}, STATES[1]]
    findings = sr.verify_end_state(plan, wrong)
    assert len(findings) == 2 and all(str(STATE_1) in f for f in findings)
    # A future period without transitions is consistent; an open one without them is not.
    quiet = {
        "id": _u(0x31),
        "entity_id": ENTITY,
        "book_code": BOOK,
        "period_id": _u(0x30),
        "state": "future",
        "current_lock_id": None,
    }
    assert sr.verify_end_state(plan, [quiet]) == ()
    assert sr.verify_end_state(plan, [{**quiet, "state": "open"}]) == (
        f"period_state {_u(0x31)}: no transition replayed",
    )


def test_an_ended_soft_close_of_a_reopened_period_is_planned_without_a_lock() -> None:
    """04 T-REF-07 rev 1.170 (CLO-CANCEL-CLOSE-REOPENED-1): the source ended the soft close of a
    reopened period, which returned it to ``reopened``. The pair is allowed, its row names no lock
    record — the period stays under its REOPEN record — and the plan carries it as a transition
    of its own; a row of that pair that names a lock record is refused, as any row that names a
    record it did not write."""
    back = _transition(10, STATE_1, PERIOD_1, "closing", "reopened", 52)
    again = _transition(11, STATE_1, PERIOD_1, "reopened", "closing", 54)
    relock = TRANSITIONS[6]
    history = [*TRANSITIONS[:6], back, again, relock, *TRANSITIONS[7:]]
    plan = sr.replay_plan(STATES, history, LOCKS)
    steps = [
        (step.from_state, step.to_state)
        for step in plan
        if step.kind == "transition" and step.period_state_id == STATE_1
    ]
    assert steps[-4:] == [
        (PeriodState.REOPENED, PeriodState.CLOSING),
        (PeriodState.CLOSING, PeriodState.REOPENED),
        (PeriodState.REOPENED, PeriodState.CLOSING),
        (PeriodState.CLOSING, PeriodState.CLOSED),
    ]
    assert sr.end_state(plan)[STATE_1] == sr.EndState(
        PeriodState.CLOSED, _u(103), ENTITY, BOOK, PERIOD_1
    )
    assert sr.verify_end_state(plan, STATES) == ()
    named = [*TRANSITIONS[:6], {**back, "period_lock_id": _u(102)}, again, relock, *TRANSITIONS[7:]]
    with pytest.raises(ValueError, match="period_lock_id"):
        sr.replay_plan(STATES, named, LOCKS)


def test_invalid_pairs_broken_chains_and_first_steps_are_refused() -> None:
    bad_pair = [TRANSITIONS[0], _transition(2, STATE_1, PERIOD_1, "future", "closed", 10)]
    with pytest.raises(ValueError, match="not an allowed transition"):
        sr.replay_plan(STATES, bad_pair, [])
    broken = [
        TRANSITIONS[0],
        TRANSITIONS[1],
        _transition(3, STATE_1, PERIOD_1, "future", "open", 20),
    ]
    with pytest.raises(ValueError, match="breaks the chain"):
        sr.replay_plan(STATES, broken, [])
    late_start = [_transition(1, STATE_1, PERIOD_1, "future", "open", 0)]
    with pytest.raises(ValueError, match="starts from NULL"):
        sr.replay_plan(STATES, late_start, [])
    with pytest.raises(ValueError, match="unknown period_state"):
        sr.replay_plan([], TRANSITIONS[:1], [])
    with pytest.raises(ValueError, match="duplicated"):
        sr.replay_plan(STATES, [TRANSITIONS[0], TRANSITIONS[0]], [])
    with pytest.raises(ValueError, match="unknown period state"):
        sr.replay_plan(STATES, [_transition(1, STATE_1, PERIOD_1, None, "frozen", 0)], [])
    naive = {**TRANSITIONS[0], "created_at": datetime(2026, 1, 1)}
    with pytest.raises(ValueError, match="timezone-aware"):
        sr.replay_plan(STATES, [naive], [])


def test_locks_must_fit_their_transitions() -> None:
    wrong_kind = [{**LOCKS[0], "kind": "REOPEN"}, *LOCKS[1:]]
    with pytest.raises(ValueError, match="does not fit a transition to"):
        sr.replay_plan(STATES, TRANSITIONS, wrong_kind)
    wrong_previous = [LOCKS[0], {**LOCKS[1], "previous_lock_id": _u(103)}, LOCKS[2]]
    with pytest.raises(ValueError, match="not an earlier lock of the same period state"):
        sr.replay_plan(STATES, TRANSITIONS, wrong_previous)
    orphan = [*LOCKS, _lock(104, "LOCK", _u(77), 70)]
    with pytest.raises(ValueError, match="unknown transitions"):
        sr.replay_plan(STATES, TRANSITIONS, orphan)
    doubled = [*LOCKS, _lock(105, "LOCK", _u(4), 31)]
    with pytest.raises(ValueError, match="carries two locks"):
        sr.replay_plan(STATES, TRANSITIONS, doubled)
    mismatch = [{**t, "period_lock_id": _u(103)} if t["id"] == _u(4) else t for t in TRANSITIONS]
    with pytest.raises(ValueError, match="is not the lock attached to it"):
        sr.replay_plan(STATES, mismatch, LOCKS)
    other_period = [{**LOCKS[0], "period_id": PERIOD_2}, *LOCKS[1:]]
    with pytest.raises(ValueError, match="differs from its transition"):
        sr.replay_plan(STATES, TRANSITIONS, other_period)
    assert sr.LOCK_TARGETS[LockKind.PERMANENT_LOCK] is PeriodState.PERMANENTLY_LOCKED


# --- Codex review of 1a41066: F-SNP-R4 (the identity tuple is joined) -----------------------------


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("entity_id", UUID(int=0xEE), "transition"),
        ("book_code", "IFRS15", "transition"),
        ("period_id", PERIOD_2, "transition"),
        ("entity_id", UUID(int=0xEE), "lock"),
        ("book_code", "IFRS15", "lock"),
    ],
)
def test_history_identity_must_match_its_period_state(field: str, value: object, kind: str) -> None:
    """Five mutations of a coherent closed history: a transition or lock whose entity, book or
    period differs from its period state is refused before any step is emitted."""
    transitions = [dict(t) for t in TRANSITIONS]
    locks = [dict(lock) for lock in LOCKS]
    if kind == "transition":
        transitions[3][field] = value  # closing → closed of STATE_1
    else:
        locks[0][field] = value  # its LOCK
    with pytest.raises(
        ValueError, match="differs from its period state|differs from its transition"
    ):
        sr.replay_plan(STATES, transitions, locks)


def test_verify_end_state_checks_the_identity_tuple_too() -> None:
    plan = sr.replay_plan(STATES, TRANSITIONS, LOCKS)
    assert sr.verify_end_state(plan, STATES) == ()
    moved = [{**STATES[0], "period_id": PERIOD_2}, STATES[1]]
    findings = sr.verify_end_state(plan, moved)
    assert len(findings) == 1 and "identity" in findings[0] and str(STATE_1) in findings[0]
