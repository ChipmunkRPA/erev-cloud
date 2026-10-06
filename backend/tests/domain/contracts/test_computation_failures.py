"""What a computation stores and what it lets through (COMPUTE-TRANSIENT-NOT-FAILURE-1; 05 RCP-20
rev 1.82; dev-guide DG-CMD-09 rev 1.126; supervisor rulings R-97 (5) and R-105).

``compute_group`` decides by the class of what the computation raised:

- an ``EngineError`` — the engine's answer about the group — is stored QUARANTINED with its item;
- a ``Problem`` is the command's answer: rolled back and re-raised, never stored;
- a TRANSIENT database error (``db.errors.is_transient``: a lock timeout, a deadlock, a cancelled
  statement, resources, the connection, the period guard's refusal, a class nobody listed) says
  nothing about the group: the savepoint is rolled back and the error propagates. No computation
  row, no exception item, no control execution; a command answers through ``from_db_error`` and
  saves nothing, a job fails its attempt and is retried;
- a DETERMINISTIC database error (a constraint, a trigger other than the period guard) and any
  other exception are a crash on this group that a retry would meet again: stored FAILED with
  its BLOCKING item, the command's fact recorded, the groups beside it computed.

As built before the item (measured by the independent review of revision 0084, R-97 (5)) every
exception but a ``Problem`` was stored FAILED with a BLOCKING ``ENGINE_INVARIANT_VIOLATION`` item
and a failed CTL-012 execution — a lock timeout, a deadlock and the guard's refusal included; the
group stayed dirty and nothing retried.

Worlds: ``support.factories.seat_world`` (AVM-US, USD; a seat contract booked and activated and
not computed, so that its next computation posts September) and, for the period guard, August of
AVM-US under a lock decision (``tests/domain/close/test_lock_freeze_db.py``).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import errors as db_errors
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_computation,
    contract_event,
    control_execution,
    exception_item,
    job,
    ledger_chain_head,
    period,
    period_state,
    subledger_line,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates as close_gates
from erev_api.domain.contracts import computation, compute_job
from erev_api.enums import ComputationStatus
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.problems import RULE_LOCK_TIMEOUT, Problem, from_db_error
from erev_api.uow import UnitOfWork
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from support.close_world import close_run_succeeded_for
from support.db import TestDatabase
from support.factories import (
    SeatWorld,
    Workspace,
    activated_contract,
    booked_contract,
    engine,
    seat_body,
    seat_line,
    seat_world,
)
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import approve, post, slug
from support.worlds import SEPTEMBER_2026
from tests.domain.close import test_lock_freeze_db as close_flows
from tests.domain.close.test_lock_freeze_db import close  # noqa: F401 - the fixture

EVENTS: Final = "/api/v1/contracts/{contract_id}/events"
BILLING: Final = {
    "event_type": "BILLING_RECORDED",
    "effective_date": "2026-09-01",
    "payload": {
        "invoice_number": "INV-US-4101",
        "line_external_id": "INV-US-4101-1",
        "amount": {"amount": "1000.00", "currency": "USD"},
        "issue_date": "2026-09-01",
    },
}
QUARANTINE: Final = "ENGINE_INVARIANT_VIOLATION"
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
GUARD: Final = (
    "EREV-LED-003: period 01900000-0000-7000-8000-000000000001 of entity "
    "01900000-0000-7000-8000-000000000002 is closed in book ASC606"
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files)


@pytest.fixture
def runtime(keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


def _pending(world: SeatWorld, external_id: str) -> tuple[UUID, UUID]:
    """A seat contract from 1 September, booked and activated as SYSTEM and NOT computed: its
    (contract id, group id). Its next computation posts September."""
    line = seat_line("O1", seats="30", price="36000.00", start="2026-09-01", end="2027-08-31")
    body = seat_body(
        world.customers["C-09"], external_id=external_id, inception="2026-09-01", lines=[line]
    )
    booked = activated_contract(
        world.place, booked_contract(world.place, body, activate=False), compute=False
    )
    return UUID(str(booked.contract["id"])), UUID(str(booked.combination_group["id"]))


class _Diag:
    def __init__(self, message: str) -> None:
        self.message_primary = message


class _Orig(Exception):
    """A driver error as psycopg raises it: a SQLSTATE and a primary message."""

    def __init__(self, sqlstate: str | None, message: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = _Diag(message)


def database_error(sqlstate: str | None, message: str = "raised by a test") -> DBAPIError:
    return DBAPIError("INSERT INTO erev.subledger_line", {}, _Orig(sqlstate, message))


def raising(error: BaseException) -> computation.Engine:
    def run(bundle: InputBundle) -> OutputBundle:
        raise error

    return run


def _stored_in(session: Session, group_id: UUID) -> dict[str, list[tuple[Any, ...]]]:
    """What the transaction holds of the group's computations, exception items and executions."""
    computations = session.execute(
        select(contract_computation.c.id, contract_computation.c.status).where(
            contract_computation.c.combination_group_id == group_id
        )
    ).all()
    return {
        "computations": sorted((str(row.status),) for row in computations),
        "items": sorted(
            (str(row.code), str(row.severity))
            for row in session.execute(
                select(exception_item.c.code, exception_item.c.severity).where(
                    exception_item.c.combination_group_id == group_id
                )
            )
        ),
        "controls": sorted(
            (str(row.control_id), str(row.result))
            for row in session.execute(
                select(control_execution.c.control_id, control_execution.c.result).where(
                    control_execution.c.run_ref_id.in_([row.id for row in computations])
                )
            )
        ),
    }


NOTHING: Final = {"computations": [], "items": [], "controls": []}
QUARANTINED: Final = {
    "computations": [("QUARANTINED",)],
    "items": [(QUARANTINE, "BLOCKING")],
    "controls": [("CTL-012", "FAIL")],
}
FAILED: Final = {
    "computations": [("FAILED",)],
    "items": [(QUARANTINE, "BLOCKING")],
    "controls": [("CTL-012", "FAIL")],
}
# What the computation raised → what is stored (None: it propagates and nothing is stored).
PARTITION: Final[tuple[tuple[str, Callable[[], BaseException], Mapping[str, Any] | None], ...]] = (
    (
        "the engine refuses the group",
        lambda: EngineError("ENGINE_INVARIANT_VIOLATED", "allocation does not sum", detail={}),
        QUARANTINED,
    ),
    ("a crash of the engine", lambda: IndexError("list index out of range"), FAILED),
    ("a crash of the orchestrator", lambda: ValueError("computed from another bundle"), FAILED),
    ("23505 unique violation", lambda: database_error("23505"), FAILED),
    ("23514 check violation", lambda: database_error("23514"), FAILED),
    ("22003 numeric out of range", lambda: database_error("22003"), FAILED),
    ("42501 row-level security", lambda: database_error("42501"), FAILED),
    (
        "P0001 immutability trigger",
        lambda: database_error("P0001", "EREV-IMM-001 row is append-only"),
        FAILED,
    ),
    ("a problem", lambda: Problem("lock-conflict"), None),
    ("55P03 lock not available", lambda: database_error("55P03"), None),
    ("40P01 deadlock detected", lambda: database_error("40P01"), None),
    ("40001 serialization failure", lambda: database_error("40001"), None),
    ("57014 statement timeout", lambda: database_error("57014"), None),
    ("57P01 admin shutdown", lambda: database_error("57P01"), None),
    ("08006 connection failure", lambda: database_error("08006"), None),
    ("53200 out of memory", lambda: database_error("53200"), None),
    ("53300 too many connections", lambda: database_error("53300"), None),
    ("58030 io error", lambda: database_error("58030"), None),
    ("25P02 in failed transaction", lambda: database_error("25P02"), None),
    ("XX000 internal error", lambda: database_error("XX000"), None),
    ("3D000 a class nobody listed", lambda: database_error("3D000"), None),
    ("no SQLSTATE", lambda: database_error(None), None),
    ("the period guard", lambda: database_error("P0001", GUARD), None),
)


def test_what_a_computation_raised_decides_what_is_stored(world: SeatWorld) -> None:
    """Every row of the partition against one committed stream, each in a unit of work that is
    rolled back. A stored refusal answers its status; what propagates is the error itself, and
    the transaction it leaves is usable and holds nothing of the computation."""
    _, group_id = _pending(world, "SF-ORD-10601")
    for name, make, expected in PARTITION:
        error = make()
        with world.place.uow() as uow:
            if expected is None:
                with pytest.raises(type(error)) as raised:
                    compute_job.compute_group(uow, group_id, engine=raising(error))
                assert raised.value is error, name
                assert _stored_in(uow.session, group_id) == NOTHING, name
            else:
                outcome = compute_job.compute_group(uow, group_id, engine=raising(error))
                assert outcome.status is not None, name
                assert [(outcome.status.value,)] == expected["computations"], name
                assert _stored_in(uow.session, group_id) == expected, name
            # the savepoint is rolled back either way: nothing of the engine's run is left
            assert (
                uow.session.execute(
                    select(func.count())
                    .select_from(subledger_line)
                    .where(subledger_line.c.contract_id.is_not(None))
                ).scalar_one()
                == 0
            ), name
            uow.discard()


def _held_heads(session: Session) -> None:
    """Take every ledger chain head of the tenant ``FOR UPDATE``: a posting waits for it inside
    the computation's savepoint (``subledger.post``)."""
    assert session.execute(select(ledger_chain_head.c.book_code).with_for_update()).all()


def test_a_wait_inside_the_savepoint_is_not_a_failed_computation(world: SeatWorld) -> None:
    """Two real waits met inside ``computation.persist``. A holder keeps the ledger chain heads:
    the posting waits beyond ``lock_timeout`` and PostgreSQL answers 55P03. Then a statement of
    the computation runs beyond ``statement_timeout``: 57014. Each propagates as the database
    raised it, the transaction is usable afterwards and holds nothing of the computation; the
    group stays dirty, and computed again without the obstacle it succeeds."""
    place = world.place
    _, group_id = _pending(world, "SF-ORD-10602")
    ctx = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as holder:
        _held_heads(holder)
        with place.uow() as uow:
            uow.session.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError) as waited:
                compute_job.compute_group(uow, group_id)
            assert db_errors.sqlstate(waited.value) == db_errors.LOCK_NOT_AVAILABLE
            assert db_errors.is_transient(waited.value)
            assert _stored_in(uow.session, group_id) == NOTHING
            uow.commit()  # the command's own writes would commit; nothing of the computation
        holder.rollback()

    def slow(uow: UnitOfWork) -> computation.Engine:
        def run(bundle: InputBundle) -> OutputBundle:
            uow.session.execute(text("SELECT pg_sleep(2)"))
            return engine()(bundle)

        return run

    with place.uow() as uow:
        uow.session.execute(text("SET LOCAL statement_timeout = '300ms'"))
        with pytest.raises(DBAPIError) as cancelled:
            compute_job.compute_group(uow, group_id, engine=slow(uow))
        assert db_errors.sqlstate(cancelled.value) == "57014"
        assert db_errors.is_transient(cancelled.value)
        assert _stored_in(uow.session, group_id) == NOTHING
        uow.commit()
    assert place.rows(select(contract_computation.c.id)) == []
    assert place.rows(select(exception_item.c.id)) == []
    assert (
        place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is not None
    )
    with place.uow() as uow:
        again = compute_job.compute_group(uow, group_id)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED


def _state_row(world: SeatWorld, period_key: str) -> tuple[UUID, UUID]:
    """(period id, ASC606 state row id) of a period of the world's entity."""
    (row,) = world.place.rows(
        select(period_state.c.period_id, period_state.c.id)
        .select_from(
            period_state.join(
                period,
                (period.c.tenant_id == period_state.c.tenant_id)
                & (period.c.id == period_state.c.period_id),
            )
        )
        .where(
            period_state.c.entity_id == world.entity_id,
            period_state.c.book_code == "ASC606",
            period.c.period_key == period_key,
        )
    )
    return UUID(str(row["period_id"])), UUID(str(row["id"]))


def test_a_wait_for_the_state_row_a_lock_decision_holds_is_not_a_failed_computation(
    world: SeatWorld,
) -> None:
    """The wait a computation meets while a period lock is being decided (04 DB-07; dev-guide
    DG-KRN-DB-08 (1c)). September of AVM-US has a finished close run and is still postable, so a
    computation of the entity's contracts is inside a window and asks for September's state row
    ``FOR SHARE`` before it writes anything. The lock decision holds that row ``FOR UPDATE`` from
    its first read (``close.gates.period_scope``) to its commit. Held beyond ``lock_timeout``,
    PostgreSQL answers 55P03 on that row: the error is transient and propagates, a command
    answers 409 ``lock-conflict`` with rule ``LOCK_TIMEOUT``, and nothing of the computation is
    stored — no computation row, no exception item, no control execution; the group stays dirty
    and is computed once the decision is over.

    The independent review of the close merges (finding F2, on the head before class 55 was
    transient) read this wait as a computation stored FAILED with a false control exception and a
    BLOCKING item. This is the witness that it is not."""
    place = world.place
    _, group_id = _pending(world, "SF-ORD-10604")
    period_id, state_id = _state_row(world, SEPTEMBER_2026)
    ctx = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        close_run_succeeded_for(
            session,
            tenant_id=place.tenant_id,
            entity_id=world.entity_id,
            period_id=period_id,
            now=place.clock.now(),
        )
    before = (len(place.rows(select(exception_item.c.id))), _executions(place))
    with tenant_session(ctx) as decision:
        assert close_gates.period_scope(decision, state_id, lock=True) is not None
        with place.uow() as uow:
            uow.session.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError) as waited:
                compute_job.compute_group(uow, group_id)
            assert db_errors.sqlstate(waited.value) == db_errors.LOCK_NOT_AVAILABLE
            assert 'relation "period_state"' in str(waited.value)  # the row it waited for
            assert db_errors.is_transient(waited.value)
            answer = from_db_error(waited.value)
            assert answer is not None
            assert (answer.status, answer.slug) == (409, "lock-conflict")
            assert [error.rule_id for error in answer.errors] == [RULE_LOCK_TIMEOUT]
            assert _stored_in(uow.session, group_id) == NOTHING
            uow.commit()  # the command's own writes would commit; nothing of the computation
        decision.rollback()
    assert _committed(place, group_id) == NOTHING
    assert (len(place.rows(select(exception_item.c.id))), _executions(place)) == before
    assert (
        place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is not None
    )
    with place.uow() as uow:
        again = compute_job.compute_group(uow, group_id)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED


def _executions(place: Workspace) -> int:
    return len(place.rows(select(control_execution.c.id)))


def _head(place: Workspace, contract_id: UUID) -> int:
    return int(
        place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    )


def _committed(place: Workspace, group_id: UUID) -> dict[str, list[tuple[Any, ...]]]:
    ctx = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        return _stored_in(session, group_id)


def test_an_event_command_that_meets_a_lock_timeout_answers_409_and_saves_nothing(
    world: SeatWorld,
) -> None:
    """Through ``POST /contracts/{id}/events``: the ledger chain heads are held past the
    platform's ``lock_timeout`` while the command's computation posts. The command answers 409
    ``lock-conflict`` with rule ``LOCK_TIMEOUT``; the event is not recorded and no computation,
    exception item or control execution exists. As built it answered 201 with a FAILED
    computation and a BLOCKING item, the invoice recorded and nothing to retry."""
    place = world.place
    contract_id, group_id = _pending(world, "SF-ORD-10603")
    head = _head(place, contract_id)
    ctx = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as holder:
        _held_heads(holder)
        sent = post(
            world.app,
            EVENTS.format(contract_id=contract_id),
            place.author,
            {"events": [BILLING]},
            if_match=f'"s{head}"',
        )
        holder.rollback()
    assert (sent.status_code, slug(sent)) == (409, "lock-conflict"), sent.text
    assert [error["rule_id"] for error in sent.json()["errors"]] == [RULE_LOCK_TIMEOUT]
    assert _head(place, contract_id) == head
    assert _committed(place, group_id) == NOTHING
    # the same command again, the heads free: recorded and computed
    again = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        place.author,
        {"events": [BILLING]},
        if_match=f'"s{head}"',
    )
    assert again.status_code == 201, again.text
    assert again.json()["computation"]["status"] == "SUCCEEDED"


def test_a_constraint_violation_inside_persist_is_a_failed_computation_and_the_fact_is_recorded(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deterministic database refusal, provoked inside ``computation.persist`` by a second
    insert of the computation's own row (23505). The event command answers 201 — its invoice is
    recorded — with ``computation.status`` FAILED, a BLOCKING item and a failed CTL-012; the
    group stays dirty. A retry would meet the same refusal, so nothing is gained by propagating.

    The stand-in passes on whatever ``persist`` hands ``_update_heads`` and records what the
    database raised: a stand-in that fails by itself is stored FAILED as well, and would pass."""
    place = world.place
    contract_id, group_id = _pending(world, "SF-ORD-10604")
    head = _head(place, contract_id)
    update_heads = computation._update_heads
    raised: list[str | None] = []

    def colliding(uow: UnitOfWork, found: Any, *, computation_id: UUID, **settings: Any) -> bool:
        try:
            uow.session.execute(
                text(
                    "INSERT INTO erev.contract_computation "
                    "SELECT * FROM erev.contract_computation WHERE id = :id"
                ),
                {"id": computation_id},
            )
        except DBAPIError as error:
            raised.append(db_errors.sqlstate(error))
            raise
        return update_heads(uow, found, computation_id=computation_id, **settings)

    monkeypatch.setattr(computation, "_update_heads", colliding)
    sent = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        place.author,
        {"events": [BILLING]},
        if_match=f'"s{head}"',
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["computation"]["status"] == "FAILED", sent.text
    assert raised == ["23505"]
    assert _head(place, contract_id) == head + 1
    assert _committed(place, group_id) == FAILED
    assert (
        place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is not None
    )


def test_a_statement_timeout_inside_persist_saves_nothing(
    world: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A statement of the computation is cancelled at ``statement_timeout`` (57014) inside
    ``computation.persist``. The event command is refused and saves nothing: no event, no
    computation row, no exception item. The answer is the kernel's for that SQLSTATE: 503
    ``statement-timeout`` with ``Retry-After`` (PRD ERR-66; ruling R-97 (6), lane OPS's mapping).
    Before that mapping was on main this test asked for any refusal but a 422."""
    place = world.place
    contract_id, group_id = _pending(world, "SF-ORD-10605")
    head = _head(place, contract_id)
    update_heads = computation._update_heads
    raised: list[str | None] = []

    def cancelled(uow: UnitOfWork, found: Any, **settings: Any) -> bool:
        uow.session.execute(text("SET LOCAL statement_timeout = '200ms'"))
        try:
            uow.session.execute(text("SELECT pg_sleep(2)"))
        except DBAPIError as error:
            raised.append(db_errors.sqlstate(error))
            raise
        return update_heads(uow, found, **settings)

    monkeypatch.setattr(computation, "_update_heads", cancelled)
    sent = post(
        world.app,
        EVENTS.format(contract_id=contract_id),
        place.author,
        {"events": [BILLING]},
        if_match=f'"s{head}"',
    )
    assert (sent.status_code, slug(sent)) == (503, "statement-timeout"), sent.text
    assert sent.headers.get("retry-after"), dict(sent.headers)
    assert raised == [db_errors.QUERY_CANCELED]
    assert _head(place, contract_id) == head
    assert _committed(place, group_id) == NOTHING
    assert (
        place.rows(
            select(contract_event.c.id).where(
                contract_event.c.contract_id == contract_id,
                contract_event.c.event_type == "BILLING_RECORDED",
            )
        )
        == []
    )


def _work(place: Workspace, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    ctx = DbContext(tenant_id=place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, place.tenant_id, attempt=1, runtime=runtime)


def test_a_wait_fails_the_jobs_attempt_and_a_crash_does_not(
    world: SeatWorld, runtime: JobRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``CONTRACT_COMPUTE`` job over two groups. The first group's computation meets a lock
    timeout: the attempt fails, nothing is stored for either group and both stay dirty. The job
    is then FAILED while its kind keeps the default policy of one attempt, and queued again for
    its retry once the retry predicate of JOB-COMPUTE-RETRY-1 (lane OPS) exists. With a crash on
    the first group instead, the job goes on: that group is stored FAILED with its item, the
    second is computed, and the job ends SUCCEEDED_WITH_EXCEPTIONS."""
    place = world.place
    first = _pending(world, "SF-ORD-10606")
    second = _pending(world, "SF-ORD-10607")
    groups = [first[1], second[1]]

    def deferred() -> UUID:
        with place.uow() as uow:
            queued = uow.defer(
                compute_job.JobKind.CONTRACT_COMPUTE,
                {"combination_group_ids": [str(value) for value in groups], "trigger": "COMMAND"},
            )
            uow.commit()
        return UUID(str(queued["id"]))

    def failing_on_the_first(error: BaseException) -> Callable[[], computation.Engine]:
        def run(bundle: InputBundle) -> OutputBundle:
            if "SF-ORD-10606" in bundle.group.member_contract_keys:
                raise error
            return engine()(bundle)

        return lambda: run

    default_engine = computation.default_engine
    monkeypatch.setattr(
        computation, "default_engine", failing_on_the_first(database_error("55P03"))
    )
    waiting = deferred()
    _work(place, waiting, runtime)
    (row,) = place.rows(select(job.c.state, job.c.result).where(job.c.id == waiting))
    assert str(row["state"]) in ("FAILED", "QUEUED") and row["result"] is None, row
    assert [_committed(place, group_id) for group_id in groups] == [NOTHING, NOTHING]
    dirty = place.rows(
        select(combination_group.c.dirty_since).where(combination_group.c.id.in_(groups))
    )
    assert all(item["dirty_since"] is not None for item in dirty)

    monkeypatch.setattr(
        computation, "default_engine", failing_on_the_first(IndexError("list index out of range"))
    )
    crashing = deferred()
    _work(place, crashing, runtime)
    (row,) = place.rows(select(job.c.state, job.c.result).where(job.c.id == crashing))
    assert str(row["state"]) == "SUCCEEDED_WITH_EXCEPTIONS", row
    assert row["result"]["counts"] == {"groups": 2, "succeeded": 1, "quarantined": 0, "failed": 1}
    assert _committed(place, groups[0]) == FAILED
    assert _committed(place, groups[1])["computations"] == [("SUCCEEDED",)]
    monkeypatch.setattr(computation, "default_engine", default_engine)


def test_the_period_guards_refusal_propagates_and_the_next_attempt_posts_into_the_open_period(
    close: close_flows.Close,  # noqa: F811 - the imported fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-97 (5), on the lock decision of August (the world of SC-1). The decision has frozen its
    datasets and holds the period's state row; ``compute_group`` of a second contract asks for
    that row, waits for the decision and is refused by the DB-07 guard with ``EREV-LED-003`` once
    August is closed. The refusal propagates: no computation row, no exception item, no control
    execution, and the group stays dirty. Computed again, the plan is new: SUCCEEDED, August's
    amounts in September with August as their origin period.

    Where it waits (04 rev 1.172, item CLO-GATE-RUN-1; dev-guide DG-KRN-DB-08 (1c)): in the read
    that finds the window of the period's close run and takes its state rows ``FOR SHARE``,
    before it writes anything. Until then it waited for the same row in its INSERT of subledger
    lines (STALE EXPECTATION, as in ``test_lock_freeze_db``'s witness of the same order).

    As built the refusal was stored: a FAILED computation with a BLOCKING item without a period —
    counted against every period of the entity — and nothing retried."""
    world = close.world
    close_flows._setup_completed(world)
    freeze_datasets = close_commands.snapshots.freeze_datasets
    posting: dict[str, Any] = {}
    seen: dict[str, Any] = {}

    def compute_late() -> None:
        try:
            with world.place.uow() as uow:
                posting["outcome"] = compute_job.compute_group(uow, seen["group_id"])
                uow.commit()
        except Exception as error:  # noqa: BLE001 - the refusal under test
            posting["error"] = error

    poster = threading.Thread(target=compute_late, name="late-computation")

    def freeze_then_meet_the_computation(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(uow, *args, **kwargs)
        if poster.ident is None:  # once: the computation arrives after the gates and the freeze
            seen["contract_id"], seen["group_id"] = close_flows._late_contract(close)
            with observing_checkouts() as backends:
                decision_pid = backend_pid(uow.session)
                poster.start()
                _, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=decision_pid,
                    backends=backends,
                    timeout=close_flows.WAIT_SECONDS,
                    expect="period_state",
                )
            seen["waiting"] = poster.is_alive() and not posting
        return datasets

    monkeypatch.setattr(
        close_commands.snapshots, "freeze_datasets", freeze_then_meet_the_computation
    )
    try:
        decided = approve(world.app, str(close.request_id), close.controller)
    finally:
        if poster.ident is not None:
            poster.join(timeout=close_flows.JOIN_SECONDS)
    assert decided.status_code == 200, decided.text
    assert not poster.is_alive() and seen["waiting"] is True, (seen, posting)
    assert "for share" in seen["blocked_in"].lower(), seen["blocked_in"]
    refused = posting.get("error")
    assert isinstance(refused, DBAPIError), posting
    assert db_errors.erev_code(refused) == db_errors.PERIOD_GUARD
    assert db_errors.is_transient(refused)
    group_id = seen["group_id"]
    assert _committed(world.place, group_id) == NOTHING
    assert close_flows._lines_of(close, seen["contract_id"]) == []
    assert (
        world.place.scalar(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        )
        is not None
    )
    # the next attempt: planned again, into the period that is open
    with world.place.uow() as uow:
        again = compute_job.compute_group(uow, group_id)
        uow.commit()
    assert again.status is ComputationStatus.SUCCEEDED
    september = UUID(str(close_flows._period(close, SEPTEMBER_2026)["period"]["id"]))
    placed = close_flows._lines_of(close, seen["contract_id"])
    assert placed and all(period_id != close.period_id for period_id, _ in placed)
    late = [item for item in placed if item[1] == close.period_id]
    assert late and {period_id for period_id, _ in late} == {september}
    assert _committed(world.place, group_id)["computations"] == [("SUCCEEDED",)]
