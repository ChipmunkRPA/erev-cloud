"""DB-07 for journal runs and DB-16 for journal lines (04 §14.1 rev 1.205; revision 0104; item
JR-CLOSED-PERIOD-GUARD-1, supervisor ruling R-97 (7) on gap G2 of the independent review of
revision 0084; the line guard of supervisor ruling R-112 (b) (6), security finding N2; CTL-015).
PostgreSQL-bound: the two triggers at the database, as any writer meets them.

``tg_journal_run__period_guard``: a ``journal_run`` is neither inserted nor moved to ``cancelled``
while the period of its entity and book is ``closed`` or ``permanently_locked``
(``EREV-LED-003``); it reads the period's state row ``FOR SHARE``, as the line guards do, so a
change of that state waits for a run's writer in flight and a writer that arrives later waits and
meets the state the change leaves. Until revision 0104 a run had no period read of its own.

``tg_journal_line__batch_draft``: a line joins a batch only while the batch is ``draft``
(``EREV-JE-003``); it reads the batch row ``FOR SHARE``, so an approval waits for a line in
flight and counts it. The deferred check of an approved batch stands behind it.

Probe rows are written through ``support.rows``; the period moves are those of
``test_period_guard_row_lock`` (T-REF-07, as ``close.commands._persist_lock`` writes them). The
commands' own witnesses, against the real lock decision, are in
``tests/domain/journals/test_closed_period_guard.py``.

The module's FIRST test is a sentinel and stays first: both triggers are enabled before any
witness here runs, so that a trigger left disabled by a test that died is named as that
(``tests/unit/journals/test_closed_period_guard_revision.py`` pins the place).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.lint import run_lint
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import journal_batch, journal_line, journal_run, period_state
from sqlalchemy import exc, func, insert, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import Executable
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.interleave import backend_pid
from support.journal_lines import GUARD as LINE_GUARD
from support.journal_lines import guard_disabled
from support.rows import (
    JournalParts,
    JournalRows,
    insert_journal_parts,
    insert_journal_rows,
    journal_line_values,
    journal_run_values,
)
from test_period_guard_row_lock import (
    LOCK_NOT_AVAILABLE,
    MOVES,
    PROBE,
    WAIT_SECONDS,
    Probe,
    _await_blocked,
    _message,
    _move,
    _other,
    _probe,
    _row_lock,
    _sqlstate,
)

pytestmark = pytest.mark.pg

RUN_GUARD: Final = "tg_journal_run__period_guard"
CLOSED: Final = ("closed", "permanently_locked")
NOW: Final = datetime(2026, 2, 3, 9, tzinfo=UTC)
_ENABLED: Final = text("SELECT tgenabled::text FROM pg_trigger WHERE tgname = :name")


def _fails(session: Session, statement: Executable) -> tuple[str | None, str]:
    """SQLSTATE and message of a statement that must fail; only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(statement)
    savepoint.rollback()
    return _sqlstate(refused.value), _message(refused.value)


def _run_of(probe: Probe) -> UUID:
    """The id of the probe's journal run."""
    with tenant_session(probe.context, read_only=True) as session:
        return UUID(
            str(
                session.execute(
                    select(journal_run.c.id).where(journal_run.c.entity_id == probe.entity_id)
                ).scalar_one()
            )
        )


def _cancel(run_id: UUID) -> Executable:
    return (
        update(journal_run)
        .where(journal_run.c.id == run_id)
        .values(state="cancelled", cancelled_at=NOW)
    )


def _second_run(probe: Probe) -> dict[str, Any]:
    """A further draft run of the probe's entity, book and period, covering (0, 0] as its first."""
    parts = JournalParts(
        calendar_id=PROBE,
        entity_id=probe.entity_id,
        period_id=probe.period_id,
        account_id=PROBE,
        release_id=PROBE,
    )
    return journal_run_values(probe.tenant_id, parts=parts)


def _refusal(probe: Probe, state: str, run_id: Any, verb: str) -> tuple[str, str]:
    return (
        "P0001",
        f"EREV-LED-003: period {probe.period_id} of entity {probe.entity_id} is {state} in book "
        f"ASC606, so journal run {run_id} cannot be {verb} in it",
    )


def _enabled(database: TestDatabase, trigger: str) -> str:
    """``pg_trigger.tgenabled`` of ``trigger``: ``O`` when it fires, ``D`` when it is disabled."""
    with database.owner_engine.connect() as connection:
        return str(connection.execute(_ENABLED, {"name": trigger}).scalar_one())


# --- the sentinel: this module's first test -------------------------------------------------------


def test_both_guards_are_enabled_before_anything_else_here_runs(
    test_database: TestDatabase,
) -> None:
    """Both triggers of revision 0104 fire when this module starts: its first test, which reads
    and does nothing else (the supervisor's condition of 2026-10-01 on the acceptance of item
    JR-CLOSED-PERIOD-GUARD-1). ``support.journal_lines`` lets a test disable either guard for a
    block — what stands behind a guard is witnessed only in the state the guard prevents — and
    enables it again when the block ends. A test that dies in such a block without reaching its
    end leaves the trigger disabled for the rest of the session (the schema is rebuilt only where
    a session starts and where the migrations are walked), and every refusal asserted after it
    would read as a defect of the product. The modules that use those blocks —
    ``tests/domain/close/test_lock_decision_db``, ``tests/domain/journals/test_export`` and
    ``test_failed_run_exit``, ``test_db_invariants`` — are collected before this one, so a
    trigger one of them left disabled is named here, before the guards' own witnesses run."""
    assert {name: _enabled(test_database, name) for name in (RUN_GUARD, LINE_GUARD)} == {
        RUN_GUARD: "O",
        LINE_GUARD: "O",
    }


# --- DB-07: a journal run and its period ----------------------------------------------------------


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize(
    "state", ["open", "closing", "reopened", "future", "closed", "permanently_locked"]
)
def test_db_07_a_journal_run_is_inserted_only_while_its_period_is_not_closed(
    committed_db: TestDatabase, keyring: KeyRing, state: str
) -> None:
    """A run is inserted while the period of its entity and book is ``open``, ``closing``,
    ``reopened`` or ``future`` — a run of a ``future`` period has no line and touches no closed
    evidence — and refused, ``EREV-LED-003``, once the period is ``closed`` or
    ``permanently_locked``. Fail-first (before revision 0104): the insert passed in every state;
    a run without lines met no guard at all."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_journal_parts(session, tenant_id, state=state)
        run = journal_run_values(tenant_id, parts=parts)
        statement = insert(journal_run).values(**run)
        if state in CLOSED:
            assert _fails(session, statement) == (
                "P0001",
                f"EREV-LED-003: period {parts.period_id} of entity {parts.entity_id} is {state} "
                f"in book ASC606, so journal run {run['id']} cannot be calculated in it",
            )
        else:
            session.execute(statement)
        stored = session.execute(select(func.count()).select_from(journal_run)).scalar_one()
        assert stored == (0 if state in CLOSED else 1)


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("state", ["closing", "future", "closed", "permanently_locked"])
def test_db_07_a_journal_run_is_cancelled_only_while_its_period_is_not_closed(
    committed_db: TestDatabase, keyring: KeyRing, state: str
) -> None:
    """A run that stands in a period is moved to ``cancelled`` while the period is postable —
    and in a ``future`` period, so that a run which stands there can be removed — and refused,
    ``EREV-LED-003``, once the period is ``closed`` or ``permanently_locked``. Every other
    change of the run's state is left to the DB-03 pairs: the guard reads nothing for it.
    Fail-first (before revision 0104): the cancel passed in a closed period."""
    probe = _probe("journal_line", keyring, state=state)  # the run was written in soft close
    run_id = _run_of(probe)
    with tenant_session(probe.context) as session:
        if state not in CLOSED:
            session.execute(_cancel(run_id))
            stored = session.execute(
                select(journal_run.c.state).where(journal_run.c.id == run_id)
            ).scalar_one()
            assert str(stored) == "cancelled"
            return
        assert _fails(session, _cancel(run_id)) == _refusal(probe, state, run_id, "cancelled")
        approve = update(journal_run).where(journal_run.c.id == run_id)
        session.execute(approve.values(state="approved", approved_at=NOW))
        stored = session.execute(
            select(journal_run.c.state).where(journal_run.c.id == run_id)
        ).scalar_one()
        assert str(stored) == "approved"
        session.rollback()


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("writer", ["insert", "cancel"])
def test_db_07_a_run_written_into_a_postable_period_holds_the_state_row(
    committed_db: TestDatabase, keyring: KeyRing, writer: str
) -> None:
    """A run inserted into, or cancelled in, a period in soft close holds the period's state row
    ``FOR SHARE`` until its transaction ends: a change of the state cannot take the row meanwhile
    (``FOR UPDATE NOWAIT`` answers 55P03), a posting can (``FOR SHARE`` is granted beside it),
    and once the writer's transaction ends the row is free. Fail-first (before revision 0104):
    ``FOR UPDATE NOWAIT`` was granted beside the run's writer — the lock decision did not wait
    for it."""
    probe = _probe("journal_line", keyring, state="closing")
    run_id = _run_of(probe)
    statement = (
        insert(journal_run).values(**_second_run(probe)) if writer == "insert" else _cancel(run_id)
    )
    with tenant_session(probe.context) as holder:
        holder.execute(statement)  # in flight: written, not committed
        with _other(probe) as closer, pytest.raises(exc.DBAPIError) as refused:
            closer.execute(_row_lock(probe, share=False))
        assert _sqlstate(refused.value) == LOCK_NOT_AVAILABLE, _message(refused.value)
        assert "period_state" in _message(refused.value)
        with _other(probe) as poster:
            assert poster.execute(_row_lock(probe, share=True)).scalar_one() == "closing"
        holder.rollback()
    with _other(probe) as closer:  # the writer ended: the state can change again
        assert closer.execute(_row_lock(probe, share=False)).scalar_one() == "closing"


@pytest.mark.control("CTL-015")
@pytest.mark.parametrize("writer", ["insert", "cancel"])
@pytest.mark.parametrize("case", ["the-period-closes", "the-close-is-undone"])
def test_db_07_a_run_written_while_the_period_closes_waits_for_the_outcome(
    committed_db: TestDatabase, keyring: KeyRing, writer: str, case: str
) -> None:
    """The lock of the period holds the state row ``FOR UPDATE`` and is not committed. A run
    inserted, or cancelled, by another transaction is observed WAITING — blocked by the
    changer's backend in the statement whose guard takes the row — and then meets the state the
    changer LEAVES: refused ``EREV-LED-003`` once the period is ``closed``, admitted after the
    same close rolled back (the positive control). Fail-first (before revision 0104): the
    statement did not wait — it was over before the change committed, which is how the only run
    of a period was cancelled beside its lock."""
    move = MOVES[case]
    probe = _probe("journal_line", keyring, state=move.from_state)
    run_id = _run_of(probe)
    second = _second_run(probe)
    written = second["id"] if writer == "insert" else run_id
    statement = insert(journal_run).values(**second) if writer == "insert" else _cancel(run_id)
    outcome: dict[str, Any] = {}
    ready = threading.Event()

    def write() -> None:
        try:
            with tenant_session(probe.context) as session:
                outcome["pid"] = backend_pid(session)
                ready.set()
                try:
                    session.execute(statement)
                    outcome["result"] = "accepted"
                except exc.DBAPIError as error:
                    outcome["result"] = (_sqlstate(error), _message(error))
                session.rollback()
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error
            ready.set()

    thread = threading.Thread(target=write, name=f"db-07-run-{writer}-{case}")
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
            assert "journal_run" in blocked_in, blocked_in  # the statement whose guard waits
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
    if move.accepted:
        assert outcome["result"] == "accepted", outcome
    else:
        verb = "calculated" if writer == "insert" else "cancelled"
        assert outcome["result"] == _refusal(probe, move.to_state, written, verb), outcome


def test_db_14_the_lint_names_a_journal_run_without_its_period_guard(
    test_database: TestDatabase,
) -> None:
    """DB-14 check (i) (04 rev 1.205): ``journal_run`` is a table whose inserts a DB-07 period
    guard decides, so a guard that is disabled is named as the line guards' are."""
    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            assert run_lint(connection, checks=("i",)) == []
            connection.exec_driver_sql(f"ALTER TABLE erev.journal_run DISABLE TRIGGER {RUN_GUARD}")
            findings = run_lint(connection, checks=("i",))
            assert [(found.check, found.object_name) for found in findings] == [
                ("i", "journal_run")
            ]
            assert "DB-07 period guard of journal_run" in findings[0].message
        finally:
            connection.rollback()


# --- DB-16: a line and its batch ------------------------------------------------------------------


def _move_batch(rows: JournalRows, state: str, **values: Any) -> Executable:
    target = journal_batch.c.id == rows.batch["id"]
    return update(journal_batch).where(target).values(state=state, **values)


def _late_line(tenant_id: UUID, rows: JournalRows, **values: Any) -> dict[str, Any]:
    """A third line for the two-line probe batch of ``rows``."""
    return journal_line_values(
        tenant_id,
        parts=rows.parts,
        entry_id=rows.entries[0]["id"],
        batch_id=rows.batch["id"],
        line_no=3,
        **values,
    )


@pytest.mark.parametrize("state", ["draft", "approved", "cancelled"])
def test_db_16_a_line_joins_a_batch_only_while_the_batch_is_draft(
    committed_db: TestDatabase, keyring: KeyRing, state: str
) -> None:
    """A line is inserted into a ``draft`` batch and refused, ``EREV-JE-003``, for a batch in
    any other state: ``journal_line`` is append-only, so this is the one way a batch's lines
    could change after the approval that covered its count and totals (security finding N2).
    Fail-first (before revision 0104): the line reached an approved batch."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id)
        if state != "draft":
            session.execute(_move_batch(rows, state))
        session.commit()
    line = _late_line(tenant_id, rows, debit=Decimal("1.00"))
    with tenant_session(context) as session:
        if state == "draft":
            session.execute(insert(journal_line).values(**line))
        else:
            assert _fails(session, insert(journal_line).values(**line)) == (
                "P0001",
                f"EREV-JE-003: journal batch {rows.batch['id']} is {state}, so journal line "
                f"{line['id']} cannot join it: a batch takes lines only while it is draft",
            )
        stored = session.execute(
            select(func.count())
            .select_from(journal_line)
            .where(journal_line.c.journal_batch_id == rows.batch["id"])
        ).scalar_one()
        assert stored == (3 if state == "draft" else 2)
        session.rollback()


@pytest.mark.parametrize("commits", [True, False], ids=["the-line-commits", "the-line-is-undone"])
def test_db_16_an_approval_waits_for_a_line_in_flight_and_counts_it(
    committed_db: TestDatabase, keyring: KeyRing, commits: bool
) -> None:
    """A line is inserted into a ``draft`` batch and not committed: it holds the batch row ``FOR
    SHARE``. The approval of the batch by another transaction is observed WAITING — blocked by
    the inserter's backend in its UPDATE of ``journal_batch`` — and then decides on the lines as
    they stand: with the line committed its balance check counts three lines against the
    batch's stored two and refuses (``EREV-JE-001``); with the insert rolled back it approves.
    Fail-first (before revision 0104): the approval did not wait — it counted two lines and
    committed ``approved`` beside a line that then committed into the approved batch."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id)
        session.commit()
    outcome: dict[str, Any] = {}
    ready = threading.Event()

    def approve() -> None:
        try:
            with tenant_session(context) as session:
                outcome["pid"] = backend_pid(session)
                ready.set()
                try:
                    session.execute(_move_batch(rows, "approved"))
                    session.commit()
                    outcome["result"] = "approved"
                except exc.DBAPIError as error:
                    outcome["result"] = (_sqlstate(error), _message(error))
                    session.rollback()
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error
            ready.set()

    thread = threading.Thread(target=approve, name="db-16-approval")
    with tenant_session(context) as inserter:
        inserter_pid = backend_pid(inserter)
        inserter.execute(insert(journal_line).values(**_late_line(tenant_id, rows)))
        thread.start()
        try:
            assert ready.wait(WAIT_SECONDS) and "error" not in outcome, outcome
            blocked_in = _await_blocked(inserter, inserter_pid, int(outcome["pid"]))
            assert "journal_batch" in blocked_in, blocked_in
            assert thread.is_alive() and "result" not in outcome
            if commits:
                inserter.commit()
            else:
                inserter.rollback()
        finally:
            if inserter.in_transaction():
                inserter.rollback()
            thread.join(timeout=WAIT_SECONDS * 3)
    assert not thread.is_alive() and "error" not in outcome, outcome
    expected: Any = "approved"
    if commits:
        expected = (
            "P0001",
            f"EREV-JE-001: batch {rows.batch['external_id']} counts 2 lines, but has 3",
        )
    assert outcome["result"] == expected, outcome
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(journal_batch.c.state).where(journal_batch.c.id == rows.batch["id"])
        ).scalar_one()
    assert str(stored) == ("draft" if commits else "approved")


def test_db_16_the_deferred_check_stands_behind_the_line_guard(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """Behind ``tg_journal_line__batch_draft`` the deferred constraint trigger of DB-16 still
    checks an approved batch's lines at commit: with the guard disabled by the owner role
    (``support.journal_lines.guard_disabled``) a line the application's role adds after the
    approval rolls the transaction back, "counts 2 lines, but has 3". Until revision 0104 the
    application's role reached that check without help
    (``test_db_invariants.test_ctl_022_batch_approve_rejects_unbalanced``); now the guard answers
    first, and is enabled again when the block ends."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    probe: dict[str, Any] = {}
    assert _enabled(committed_db, LINE_GUARD) == "O"
    with guard_disabled(committed_db):
        assert _enabled(committed_db, LINE_GUARD) == "D"
        with pytest.raises(exc.DBAPIError) as refused, tenant_session(context) as session:
            late = insert_journal_rows(session, tenant_id)
            probe["external_id"] = late.batch["external_id"]
            session.execute(_move_batch(late, "approved"))
            line = _late_line(tenant_id, late, debit=Decimal("1.00"))
            session.execute(insert(journal_line).values(**line))
    assert (_sqlstate(refused.value), _message(refused.value)) == (
        "P0001",
        f"EREV-JE-001: batch {probe['external_id']} counts 2 lines, but has 3",
    )
    assert (_enabled(committed_db, LINE_GUARD), _enabled(committed_db, RUN_GUARD)) == ("O", "O")
    with tenant_session(context, read_only=True) as session:
        assert session.execute(select(func.count()).select_from(journal_batch)).scalar_one() == 0
