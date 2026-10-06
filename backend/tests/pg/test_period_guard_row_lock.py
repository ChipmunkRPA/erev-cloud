"""DB-07: the two period guards hold the period's state row (04 §14.1 DB-07 rev 1.113; revision
0084; supervisor rulings R-31 and R-40 (b) of 2026-09-30; security finding SC-1; REQ-CLS-002;
CTL-015). PostgreSQL-bound: two ``erev_app`` sessions per case.

``tg_subledger_line__period_guard`` and ``tg_journal_line__period_guard`` read the ``period_state``
row of the line's entity, book and period ``FOR SHARE``. Until revision 0084 they read it without
a lock: a line inserted while the period was ``closing`` committed after the transaction that
closed the period, and the period closed with lines its lock did not hold. Probe rows are written
through ``support.rows``; the lock decision's own witnesses are in
``tests/domain/close/test_lock_freeze_db.py``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    journal_line,
    period_lock,
    period_state,
    period_state_transition,
    subledger_line,
    subledger_posting,
)
from sqlalchemy import exc, insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.interleave import (
    BLOCKED_BY_HOLDER,
    LOCKS_OF,
    backend_pid,
    format_lock_rows,
    fresh_activity,
)
from support.rows import (
    CloseParts,
    insert_approval_request,
    insert_journal_rows,
    insert_ledger_parts,
    insert_reopen_record,
    journal_line_values,
    period_lock_values,
    period_state_transition_values,
    subledger_line_values,
    subledger_posting_values,
)

pytestmark = pytest.mark.pg

TABLES: Final = ("subledger_line", "journal_line")
LOCK_NOT_AVAILABLE: Final = "55P03"
WAIT_SECONDS: Final = 8.0  # under the sessions' lock_timeout of 10 s
PROBE: Final = UUID(int=0)
# the states a journal run cannot be inserted into; a journal probe reaches them by its moves
CLOSED_PROBES: Final = ("closed", "permanently_locked")


@dataclass(frozen=True, slots=True)
class Probe:
    """One tenant with a period of one entity and book, and what a line of ``table`` needs."""

    table: str
    context: DbContext
    tenant_id: UUID
    entity_id: UUID
    period_id: UUID
    state_id: UUID
    insert_line: Callable[[Session], UUID]  # inserts one line in the session's transaction


def _state_row(session: Session, entity_id: UUID, period_id: UUID) -> UUID:
    return UUID(
        str(
            session.execute(
                select(period_state.c.id).where(
                    period_state.c.entity_id == entity_id, period_state.c.period_id == period_id
                )
            ).scalar_one()
        )
    )


def _probe(table: str, keyring: KeyRing, *, state: str = "closing") -> Probe:
    """The committed rows of a probe whose period is in ``state``."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        if table == "subledger_line":
            parts = insert_ledger_parts(session, tenant_id, state=state)
            entity_id, period_id = parts.chain.entity_id, parts.period_id

            def insert_line(poster: Session) -> UUID:
                # DB-06 (1): a line joins a posting of its own transaction
                posting = subledger_posting_values(
                    tenant_id, parts=parts, idempotency_key=f"probe:{new_id()}"
                )
                poster.execute(insert(subledger_posting).values(**posting))
                line = subledger_line_values(tenant_id, posting=posting, parts=parts)
                poster.execute(insert(subledger_line).values(**line))
                return UUID(str(line["id"]))

        else:
            # A journal run is not inserted into a closed period (04 DB-07 rev 1.205; revision
            # 0104, ``tg_journal_run__period_guard``): the run and batch of a closed probe are
            # written while its period is in soft close, which the moves of T-REF-07 then close
            # (STALE TEST WORLD under supervisor ruling R-97 (7): the run inserted straight
            # into a ``closed`` period).
            closes = state in CLOSED_PROBES
            rows = insert_journal_rows(
                session, tenant_id, lines=(), state="closing" if closes else state
            )
            entity_id, period_id = rows.parts.entity_id, rows.parts.period_id

            def insert_line(poster: Session) -> UUID:
                line = journal_line_values(
                    tenant_id,
                    parts=rows.parts,
                    entry_id=rows.entries[0]["id"],
                    batch_id=rows.batch["id"],
                )
                poster.execute(insert(journal_line).values(**line))
                return UUID(str(line["id"]))

        if state == "reopened":
            # a reopened period is under its REOPEN record (T-REF-06 `current_lock_id`), which
            # DB-07 reads for `is_post_reopen` (04 rev 1.184; revision 0113)
            insert_reopen_record(session, tenant_id, entity_id=entity_id, period_id=period_id)
        state_id = _state_row(session, entity_id, period_id)
        probe = Probe(table, context, tenant_id, entity_id, period_id, state_id, insert_line)
        if table == "journal_line" and state in CLOSED_PROBES:
            _move(session, probe, MOVES["the-period-closes"])
            if state == "permanently_locked":
                _move(session, probe, MOVES["the-period-is-permanently-locked"])
        session.commit()
    return probe


def _sqlstate(error: exc.DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _message(error: exc.DBAPIError) -> str:
    diag = getattr(error.orig, "diag", None)
    return str(getattr(diag, "message_primary", "") or "")


def _row_lock(probe: Probe, *, share: bool) -> Any:
    """The probe's state row ``FOR UPDATE`` (a change of the state) or ``FOR SHARE``, NOWAIT."""
    return (
        select(period_state.c.state)
        .where(period_state.c.id == probe.state_id)
        .with_for_update(read=share, nowait=True)
    )


@contextmanager
def _other(probe: Probe) -> Iterator[Session]:
    """A second ``erev_app`` transaction of the tenant, rolled back at the end."""
    with tenant_session(probe.context) as session:
        try:
            yield session
        finally:
            session.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("state", ["open", "closing", "reopened"])
def test_db_07_a_line_insert_holds_the_period_state_row_until_its_transaction_ends(
    committed_db: TestDatabase, keyring: KeyRing, table: str, state: str
) -> None:
    """A line inserted into a postable period — ``open``, ``closing`` (the lock and the re-lock
    start there) or ``reopened`` — holds the state row ``FOR SHARE``: while its transaction is
    open a change of the state cannot take the row (``FOR UPDATE NOWAIT`` answers 55P03), a
    second poster can (``FOR SHARE`` is granted beside it), and once the first transaction ends
    the row is free. Fail-first (the 0040 / 0046 bodies): ``FOR UPDATE NOWAIT`` is granted while
    the line is uncommitted — the lock decision did not wait for it."""
    probe = _probe(table, keyring, state=state)
    with tenant_session(probe.context) as poster:
        probe.insert_line(poster)  # in flight: inserted, not committed
        with _other(probe) as closer, pytest.raises(exc.DBAPIError) as refused:
            closer.execute(_row_lock(probe, share=False))
        assert _sqlstate(refused.value) == LOCK_NOT_AVAILABLE, _message(refused.value)
        assert "period_state" in _message(refused.value)
        with _other(probe) as second:
            assert second.execute(_row_lock(probe, share=True)).scalar_one() == state
        poster.rollback()
    with _other(probe) as closer:  # the posting ended: the state can change again
        assert closer.execute(_row_lock(probe, share=False)).scalar_one() == state


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("state", ["closed", "permanently_locked", "future"])
def test_db_07_a_refused_line_leaves_no_lock_on_the_period_state_row(
    committed_db: TestDatabase, keyring: KeyRing, table: str, state: str
) -> None:
    """A line for a period that is not postable is refused (``EREV-LED-003``) and, once its
    statement is rolled back, holds nothing: the permanent lock, the reopen and the opening of the
    period take the row at once. No posting is in flight into such a period."""
    probe = _probe(table, keyring, state=state)
    with tenant_session(probe.context) as poster:
        attempt = poster.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            probe.insert_line(poster)
        attempt.rollback()
        assert _sqlstate(refused.value) == "P0001"
        assert f"is {state} in book ASC606" in _message(refused.value), _message(refused.value)
        with _other(probe) as changer:
            assert changer.execute(_row_lock(probe, share=False)).scalar_one() == state
        poster.rollback()


@dataclass(frozen=True, slots=True)
class Move:
    """One T-REF-07 move of the probe's period and what a line that waited for it meets."""

    from_state: str
    to_state: str
    lock_kind: str | None  # the ``period_lock`` the move writes; None for a move without one
    reason_code: str | None
    commits: bool
    accepted: bool  # the line is admitted into the state the move leaves
    # an admitted subledger line is stored as a post-reopen line: the period is under a REOPEN
    # record when the line's wait ends (04 DB-07 rev 1.184), whatever state the move leaves
    post_reopen: bool = False


MOVES: Final = {
    # the lock decision (SC-1): the line is refused once the period is closed
    "the-period-closes": Move("closing", "closed", "LOCK", None, True, False),
    # the positive control: the same close rolled back leaves the period postable
    "the-close-is-undone": Move("closing", "closed", "LOCK", None, False, True),
    # the permanent lock starts from closed: the line is refused on either side of it
    "the-period-is-permanently-locked": Move(
        "closed", "permanently_locked", "PERMANENT_LOCK", None, True, False
    ),
    # a reopen: the line reads the committed ``reopened`` and is admitted as post-reopen
    "the-period-reopens": Move(
        "closed", "reopened", "REOPEN", "ERROR_CORRECTION", True, True, post_reopen=True
    ),
    # a reopened period is soft-closed again: the line that waited reads `closing` and stays a
    # post-reopen line, because start-close leaves the period under its REOPEN record
    # (supervisor ruling R-117 (c); until revision 0113 the guard stored `state = 'reopened'`)
    "a-reopened-period-is-soft-closed-again": Move(
        "reopened", "closing", None, None, True, True, post_reopen=True
    ),
    # start-close freezes nothing: the period is postable on both sides of it
    "soft-close-starts": Move("open", "closing", None, None, True, True),
}


def _move(session: Session, probe: Probe, move: Move) -> None:
    """One move as DB-07 and T-REF-07 require it: the lock row of the move's kind first, its
    transition, then the state — the statements of ``close.commands._persist_lock``; a move
    without a lock (start-close) writes the transition and the state."""
    transition_id = new_id()
    lock_id = None
    approval_request_id = None
    if move.lock_kind is not None:
        parts = CloseParts(
            calendar_id=PROBE,
            entity_id=probe.entity_id,
            period_id=probe.period_id,
            period_state_transition_id=transition_id,
            approval_request_id=insert_approval_request(
                session, tenant_id=probe.tenant_id, entity_id=probe.entity_id
            ),
            file_id=PROBE,
        )
        lock = period_lock_values(
            probe.tenant_id, parts=parts, kind=move.lock_kind, reason_code=move.reason_code
        )
        session.execute(insert(period_lock).values(**lock))
        lock_id, approval_request_id = lock["id"], parts.approval_request_id
    session.execute(
        insert(period_state_transition).values(
            **period_state_transition_values(
                probe.tenant_id,
                period_state_id=probe.state_id,
                entity_id=probe.entity_id,
                period_id=probe.period_id,
                from_state=move.from_state,
                to_state=move.to_state,
                id=transition_id,
                reason_code=move.reason_code,
                approval_request_id=approval_request_id,
                period_lock_id=lock_id,
            )
        )
    )
    moved: dict[str, Any] = {"state": move.to_state, "updated_by_kind": "SYSTEM"}
    if lock_id is not None:
        moved["current_lock_id"] = lock_id  # the record the move wrote, as the commands set it
    session.execute(update(period_state).where(period_state.c.id == probe.state_id).values(**moved))


def _await_blocked(holder: Session, holder_pid: int, waiter_pid: int) -> str:
    """The statement ``waiter_pid`` waits in once it is blocked by ``holder_pid`` — a Lock wait
    read from a fresh activity snapshot on the holder's session (``support.interleave``)."""
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        found = fresh_activity(
            holder, BLOCKED_BY_HOLDER, {"pids": [waiter_pid], "holder": holder_pid}
        ).first()
        if found is not None:
            return str(found.query)
        time.sleep(0.05)
    locks = format_lock_rows(
        fresh_activity(holder, LOCKS_OF, {"pids": [holder_pid, waiter_pid]}).all()
    )
    raise AssertionError(f"backend {waiter_pid} was not blocked by {holder_pid}; locks:\n{locks}")


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("case", sorted(MOVES))
def test_db_07_a_line_that_reaches_the_guard_while_the_state_changes_waits_for_the_outcome(
    committed_db: TestDatabase, keyring: KeyRing, table: str, case: str
) -> None:
    """A change of the period's state holds the state row ``FOR UPDATE`` and is not committed. A
    line inserted by another transaction is observed WAITING — its backend blocked by the
    changer's, holding the tuple lock of ``period_state`` and waiting for the changer's
    transaction — and then meets the state the changer LEAVES: refused ``EREV-LED-003`` after the
    lock (``closed``) and after the permanent lock; admitted after the same close rolled back
    (the positive control), after a reopen — as a post-reopen line — and after start-close, which
    leaves the period postable: a period never locked stores an ordinary line, a reopened period
    soft-closed again a post-reopen line, because it stays under its REOPEN record (04 DB-07 rev
    1.184; revision 0113). Fail-first (the 0040 / 0046 bodies): the insert does not wait —
    it decides on the state as it was and is over before the change commits, which is how a line
    reached a period that closed beside it."""
    move = MOVES[case]
    probe = _probe(table, keyring, state=move.from_state)
    outcome: dict[str, Any] = {}
    ready = threading.Event()

    def post() -> None:
        try:
            with tenant_session(probe.context) as poster:
                outcome["pid"] = backend_pid(poster)
                ready.set()
                try:
                    line_id = probe.insert_line(poster)
                    outcome["result"] = "accepted"
                    if table == "subledger_line":
                        outcome["post_reopen"] = poster.execute(
                            select(subledger_line.c.is_post_reopen).where(
                                subledger_line.c.id == line_id
                            )
                        ).scalar_one()
                except exc.DBAPIError as error:
                    outcome["result"] = (_sqlstate(error), _message(error))
                poster.rollback()
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error
            ready.set()

    thread = threading.Thread(target=post, name=f"db-07-{table}-{case}")
    with tenant_session(probe.context) as changer:
        changer_pid = backend_pid(changer)
        held = changer.execute(
            select(period_state.c.state)
            .where(period_state.c.id == probe.state_id)
            .with_for_update()
        ).scalar_one()
        assert held == move.from_state
        _move(changer, probe, move)
        thread.start()
        try:
            assert ready.wait(WAIT_SECONDS) and "error" not in outcome, outcome
            blocked_in = _await_blocked(changer, changer_pid, int(outcome["pid"]))
            assert table in blocked_in, blocked_in  # the INSERT whose guard takes the row lock
            locks = fresh_activity(changer, LOCKS_OF, {"pids": [int(outcome["pid"])]}).all()
            evidence = format_lock_rows(locks)
            assert any(
                row.locktype == "tuple" and str(row.relation).endswith("period_state")
                for row in locks
            ), evidence
            assert any(row.locktype == "transactionid" and not row.granted for row in locks), (
                evidence
            )
            assert thread.is_alive() and "result" not in outcome
            if move.commits:
                changer.commit()
            else:
                changer.rollback()
        finally:
            if changer.in_transaction():
                changer.rollback()
            thread.join(timeout=WAIT_SECONDS * 3)
    assert not thread.is_alive() and "error" not in outcome, outcome
    left = move.to_state if move.commits else move.from_state
    if move.accepted:
        assert outcome["result"] == "accepted", outcome
        if table == "subledger_line":
            assert outcome["post_reopen"] is (move.post_reopen and move.commits)
    else:
        sqlstate, message = outcome["result"]
        assert sqlstate == "P0001", outcome
        assert message.startswith(
            f"EREV-LED-003: period {probe.period_id} of entity {probe.entity_id} is {left} in "
            "book ASC606"
        ), message
    with tenant_session(probe.context, read_only=True) as session:
        state = session.execute(
            select(period_state.c.state).where(period_state.c.id == probe.state_id)
        ).scalar_one()
        lines = subledger_line if table == "subledger_line" else journal_line
        stored = session.execute(
            select(lines.c.id).where(lines.c.period_id == probe.period_id)
        ).all()
    # nothing of either outcome is kept: the refused line never was, the admitted one rolled back
    assert (state, stored) == (left, [])
