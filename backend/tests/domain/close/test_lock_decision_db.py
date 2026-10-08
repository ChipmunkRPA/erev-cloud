"""The lock decision's own locks, connections and basis (supervisor ruling R-116 (h) of
2026-09-30; findings F7 (c) and F8 and gap G3 of the independent review of revision 0084, ruling
R-97 (7); 04 §14.1 DB-07 rev 1.182; 05 TXN-03 rev 1.121; dev-guide DG-KRN-DB-08, DG-KRN-APR-05 and
DG-AK-60 rev 1.165; PRD ERR-78 rev 1.111; REQ-CLS-009, REQ-CLS-011). PostgreSQL-bound.

World: ``support.close_world`` — AVM-US with FY2026-P01 to P09 open and October ``future``;
January to August closed as fixture state (PRD WLD-P-02), September in soft close with every
automatic gate green and Maya's lock request pending; the decisions are real approvals through
the API.

- F8: the ``future`` next period's row is the decision's SECOND lock, taken ``NOWAIT`` before the
  gates and the freeze. Until rev 1.182 it was the last one: a held row was learned after the
  twelve datasets had been produced and stored, and answered with the copy of a lock wait.
- F7 (c): one SYSTEM reader for the whole freeze phase — four checkouts of a second connection
  before. The reader is READ COMMITTED: its coverage reads still see what another transaction
  commits while the datasets are produced.
- 05 TXN-03: the decision's transaction is idle while its reader produces a dataset, and the
  reader's while the decision writes; both set ``idle_in_transaction_session_timeout`` for
  themselves. Until rev 1.121 the connection default ended the decision's session.
- G3: the approved basis is compared again under the row lock, and a reopen never passes a later
  period's lock decision in flight (PRD BR-CLS-05 with BR-CLS-08).
- Supervisor ruling R-119 (d) of 2026-10-01: a held EARLIER period is refused by name on the request
  and on the decision (PRD ERR-85), and the setup completion at the end of the approve command
  takes the tenant's row ``FOR NO KEY UPDATE`` (item SETUP-COMPLETION-LOCK-1) — the witness of
  G3's third order runs in a tenant whose setup is not complete.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db import session as db_session
from erev_api.db.session import app_engine
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_chain_head,
    audit_event,
    file_object,
    journal_run,
    lock_snapshot,
    period_lock,
    period_state,
    period_state_transition,
    reconciliation,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import dependencies as close_dependencies
from erev_api.domain.close import freeze, snapshots
from erev_api.domain.platform import setup
from erev_api.enums import FilePurpose, PeriodState, ReasonCode
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.periods import PeriodCancelCloseIn
from fastapi import FastAPI
from sqlalchemy import event, func, insert, select, text
from support.close_world import (
    CloseWorld,
    acknowledged_run,
    actor_with_role,
    close_run_succeeded,
    close_world,
    earlier_periods_closed,
    reviewed_error_judgement,
    reviewed_reconciliations,
    system_session,
)
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.journal_lines import run_guard_disabled
from support.principals import Actor, cookie_headers
from support.reference import APPROVALS, PERIODS, approve, get, periods, post, slug
from support.rows import PROBE_RECORDED_AT, JournalParts, journal_run_values

AUGUST: Final = "FY2026-P08"
SEPTEMBER: Final = "FY2026-P09"
OCTOBER: Final = "FY2026-P10"
COMMENT: Final = "September 2026 close complete"
RULE_HELD: Final = "NEXT_PERIOD_HELD"
RULE_EARLIER_HELD: Final = "EARLIER_PERIOD_HELD"
# PRD §5.5 ERR-78, with the two period names
HELD: Final = "{next_period} is in use by another request, so {period} was not locked. " + (
    "Nothing was saved. Decide again."
)
# PRD §5.5 ERR-85, with the two period names
EARLIER_HELD: Final = "{earlier_period} is in use by another request, so {period} was not " + (
    "locked. Nothing was saved. Decide again."
)
WAIT_SECONDS: Final = 30.0
JOIN_SECONDS: Final = 120.0
# 05 TXN-03 in the witness: every tenant transaction starts with 2 s instead of the connection's
# 60 s, and one producer takes 4.5 s — the proportions of a dataset that outlasts the default.
LOWERED_IDLE_MS: Final = 2000
SLOW_PRODUCER_SECONDS: Final = 4.5


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _state(world: CloseWorld, key: str = SEPTEMBER) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == key
    ]
    return dict(found)


def _value(stored: Any) -> str:
    return str(getattr(stored, "value", stored))


def _lock_requested(world: CloseWorld) -> str:
    """September on its way to the lock through the product: ``_ready_for_lock`` and Maya's lock
    request. Returns the pending request's id."""
    requested = _request_lock(world, _ready_for_lock(world))
    assert requested.status_code == 200, requested.text
    return str(requested.json()["approval_request_id"])


def _request_lock(world: CloseWorld, shown: dict[str, Any]) -> HttpResponse:
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-lock",
        world.maya,
        {"certification_comment": COMMENT},
        if_match=f'"r{shown["row_version"]}"',
    )


def _ready_for_lock(world: CloseWorld) -> dict[str, Any]:
    """September ready to be submitted for lock: January to August closed (fixture state,
    BR-CLS-08), the soft close, an acknowledged journal run, the two reconciliations reviewed and
    the period's close run (fixture rows of ``support.close_world``; the run's row is written
    last, as ``close_run_succeeded_for`` asks — item CLO-GATE-RUN-1, 04 §16.8 "The close-run
    gate": a period locks only on its close run). Returns September's API-S-Period."""
    earlier_periods_closed(world)
    shown = _state(world)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    with system_session(world) as session:
        acknowledged_run(session, world)
        reviewed_reconciliations(session, world)
        close_run_succeeded(session, world)
    return _state(world)


def _controller(world: CloseWorld, clock: FrozenClock, name: str = "cora") -> Actor:
    return actor_with_role(world.app, clock, world.tenant_id, "controller", name=name)


def _written(world: CloseWorld, request_id: str) -> dict[str, Any]:
    """What a lock decision writes, read back for a before / after comparison."""
    shown = _state(world)
    with system_session(world) as session:
        count = lambda table, *where: int(  # noqa: E731
            session.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
        )
        return {
            "state": shown["state"],
            "row_version": shown["row_version"],
            "next_state": _state(world, OCTOBER)["state"],
            "transitions": count(
                period_state_transition, period_state_transition.c.period_state_id == world.state_id
            ),
            "locks": count(period_lock, period_lock.c.period_id == world.period_id),
            "snapshots": count(lock_snapshot),
            "dataset_files": count(
                file_object, file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value
            ),
            "decisions": count(
                approval_decision, approval_decision.c.approval_request_id == UUID(request_id)
            ),
            "request": _request(world, request_id),
        }


def _request(world: CloseWorld, request_id: str) -> tuple[str, str | None]:
    """(status, void reason) of the approval request."""
    with system_session(world) as session:
        status, reason = session.execute(
            select(approval_request.c.status, approval_request.c.void_reason).where(
                approval_request.c.id == UUID(request_id)
            )
        ).one()
    return _value(status), None if reason is None else _value(reason)


def _one_approval(app: FastAPI, request_id: str, approver: Actor) -> Callable[[], HttpResponse]:
    """ONE ``POST /approvals/{id}/approve`` — the hash the request shows the approver and one
    ``Idempotency-Key`` — that each call sends again as it is."""
    detail = get(app, f"{APPROVALS}/{request_id}", approver)
    assert detail.status_code == 200, detail.text
    request = detail.json()
    body = {"subject_content_sha256": request["subject"]["content_sha256"], "comment": "OK"}
    if request["impact_preview"] is not None:
        body["impact_preview_sha256"] = request["impact_preview"]["sha256"]
    headers = cookie_headers(approver.token, approver.csrf_token, key=True)
    path = f"{APPROVALS}/{request_id}/approve"
    return lambda: call(app, "POST", path, json=dict(body), headers=dict(headers))


def _stored_objects(settings: Settings) -> int:
    """The number of objects in the test's file store (a rolled-back decision removes its
    ``file_object`` rows; the objects it stored stay until the orphan sweep)."""
    return sum(1 for found in Path(settings.file_root).rglob("*") if found.is_file())


def test_f8_a_share_pin_on_the_future_next_period_refuses_the_decision_before_anything_is_stored(
    world: CloseWorld, clock: FrozenClock, app_settings: Settings
) -> None:
    """Another transaction holds October's ``future`` row ``FOR SHARE`` — the pin a close command
    addressed to October takes. The lock decision of September is refused at once and by name:
    409 ``lock-conflict``, rule ``NEXT_PERIOD_HELD``, the detail of PRD ERR-78 with both period
    names. Nothing is written, no decision is recorded, and NO object reaches the file store —
    the refusal comes before the gates and the freeze. Once the pin is gone the SAME request, sent
    again as it is — its ``Idempotency-Key`` and its body unchanged — locks September and opens
    October: the refusal is not kept for the key (04 API-C-04 rev 1.144), which is what "Decide
    again" promises.

    Fail-first (the next period's row as the decision's last lock): the decision produced and
    stored its twelve datasets, then met the held row and answered with the copy of a lock wait
    ("held … for longer than the platform waits"), rule ``LOCK_TIMEOUT``."""
    request_id = _lock_requested(world)
    controller = _controller(world, clock)
    october, september = _state(world, OCTOBER), _state(world)
    assert october["state"] == PeriodState.FUTURE.value
    detail = HELD.format(next_period=october["period"]["name"], period=september["period"]["name"])
    before, objects = _written(world, request_id), _stored_objects(app_settings)
    decide = _one_approval(world.app, request_id, controller)
    with system_session(world) as holder:
        held = holder.execute(
            select(period_state.c.state)
            .where(period_state.c.id == UUID(str(october["id"])))
            .with_for_update(read=True)
        ).scalar_one()
        assert _value(held) == PeriodState.FUTURE.value
        refused = decide()
        assert (refused.status_code, slug(refused)) == (409, "lock-conflict"), refused.text
        problem = refused.json()
        assert problem["detail"] == detail
        assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
            (RULE_HELD, detail)
        ]
        assert _stored_objects(app_settings) == objects  # nothing was produced
        assert _written(world, request_id) == before
        holder.rollback()
    decided = decide()  # the same key and body: decided again, not answered the stored refusal
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert _state(world, OCTOBER)["state"] == PeriodState.OPEN.value
    assert _stored_objects(app_settings) > objects  # the control: a decision does store objects


class _Pool:
    """The app engine's pool as one request sees it: how many connections are out at once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.out = 0
        self.peak = 0
        self.checkouts = 0

    def checkout(self, *_: Any) -> None:
        with self._lock:
            self.out += 1
            self.checkouts += 1
            self.peak = max(self.peak, self.out)

    def checkin(self, *_: Any) -> None:
        with self._lock:
            self.out -= 1


@contextmanager
def _observed_pool() -> Iterator[_Pool]:
    pool, engine = _Pool(), app_engine()
    event.listen(engine, "checkout", pool.checkout)
    event.listen(engine, "checkin", pool.checkin)
    try:
        yield pool
    finally:
        event.remove(engine, "checkout", pool.checkout)
        event.remove(engine, "checkin", pool.checkin)


def _counting_readers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every SYSTEM reader the freeze code opens from here on, by the function that opened it."""
    opened: list[str] = []
    real_unit, real_reads = freeze.system_unit, freeze.system_reads

    @contextmanager
    def unit(uow: Any) -> Iterator[Any]:
        opened.append("system_unit")
        with real_unit(uow) as reader:
            yield reader

    @contextmanager
    def reads(tenant_id: UUID) -> Iterator[Any]:
        opened.append("system_reads")
        with real_reads(tenant_id) as session:
            yield session

    monkeypatch.setattr(freeze, "system_unit", unit)
    monkeypatch.setattr(freeze, "system_reads", reads)
    return opened


def test_f7_c_a_lock_decision_holds_two_connections_at_its_peak_and_opens_one_reader(
    world: CloseWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real approval of September's lock, with the app engine's pool observed from the request
    to its answer: at no moment are more than TWO connections out — the command's own and its
    SYSTEM reader — and the freeze opens that reader ONCE, for the activity read, the twelve
    producers and both coverage reads.

    Fail-first: four readers per decision — ``system_reads`` for the activity, ``system_unit``
    for the producers, ``system_reads`` for each of the two coverage reads — each a checkout of a
    second connection while the decision holds the period's state row."""
    request_id = _lock_requested(world)
    controller = _controller(world, clock)
    opened = _counting_readers(monkeypatch)
    with _observed_pool() as pool:
        decided = approve(world.app, request_id, controller)
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert opened == ["system_unit"]
    assert (pool.peak, pool.out) == (2, 0), (pool.peak, pool.out, pool.checkouts)


def test_f7_c_the_one_reader_sees_a_run_committed_while_the_datasets_are_produced(
    world: CloseWorld,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
    committed_db: TestDatabase,
) -> None:
    """The coverage guard (S15-R-18c; supervisor ruling R-19 (b)) through the decision's ONE
    reader. While the first dataset is produced — the reader's transaction has begun and has read
    the period's activity — another transaction commits a journal run of September, stamped
    before the freeze cutoff: the case that only the comparison of the period's activity catches.
    The reader is READ COMMITTED, so the coverage read that follows the datasets sees the run:
    409 ``invalid-transition`` under ``S15-R-18c``, "1 at the freeze, 2 now", nothing written.

    The refusal is the same before and after rev 1.182 — each coverage read had a transaction of
    its own before. The witness is here because one reader for the whole freeze phase makes the
    guard depend on that reader's isolation level: with the reader raised to REPEATABLE READ the
    read repeats what it saw before the freeze and the decision locks September over a journal
    population that is not the period's (measured: 200).

    Since revision 0104 (04 DB-07 rev 1.205; item JR-CLOSED-PERIOD-GUARD-1; supervisor ruling
    R-97 (7)) a journal run cannot be committed beside the decision: the run's period guard,
    ``tg_journal_run__period_guard``, reads the period's state row ``FOR SHARE``, so the insert
    waits for the decision's lock on that row and is refused once September is closed. The
    comparison of the runs now stands behind that guard, and its witness needs the state the
    guard prevents: the guard is disabled for the decision
    (``support.journal_lines.run_guard_disabled``), every expectation kept.
    STALE TEST WORLD under that ruling — measured with the guard on: the insert below waited for
    the decision that was waiting for it and ended at its lock timeout; no run was committed and
    the decision answered 409 ``lock-conflict``."""
    request_id = _lock_requested(world)
    controller = _controller(world, clock)
    registry = close_dependencies.snapshot_registry()
    first_kind = close_dependencies.snapshot_engine().kinds[0]
    parts = JournalParts(
        calendar_id=new_id(),
        entity_id=world.entity_id,
        period_id=world.period_id,
        account_id=new_id(),
        release_id=new_id(),
    )
    committed: list[UUID] = []

    def beside(reader: Any, scope: Any) -> Any:
        if not committed:
            run = journal_run_values(world.tenant_id, parts=parts, created_at=PROBE_RECORDED_AT)
            with system_session(world) as other:
                other.execute(insert(journal_run).values(**run))
                other.commit()
            committed.append(UUID(str(run["id"])))
        return registry.datasets[first_kind](reader, scope)

    produced = dataclasses.replace(registry, datasets={**registry.datasets, first_kind: beside})
    before = _written(world, request_id)
    with monkeypatch.context() as patched, run_guard_disabled(committed_db):
        patched.setattr(close_dependencies, "snapshot_registry", lambda: produced)
        refused = approve(world.app, request_id, controller)
    assert len(committed) == 1
    assert refused.status_code == 409, refused.text  # 200: the reader did not see the run
    assert slug(refused) == "invalid-transition", refused.text
    assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
        (freeze.RULE_COVERAGE, freeze.RUNS_DURING_DECISION.format(before=1, after=2))
    ]
    assert _written(world, request_id) == before


def test_txn_03_a_lock_decision_outlives_the_connections_idle_timeout(
    world: CloseWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 TXN-03 rev 1.121. Every tenant transaction of the request starts with an
    idle-in-transaction timeout of 2 s — the connection default of 60 s, lowered — and one
    producer takes 4.5 s, during which the decision's transaction and the reader's are both idle.
    The decision locks September all the same: it set the timeout for both transactions, to the
    setting (900 s), before the first dataset was produced.

    Fail-first: PostgreSQL ended both sessions after 2 s ("terminating connection due to
    idle-in-transaction timeout", SQLSTATE 25P03); the decision answered 500 and September stayed
    in soft close — with the real default, any dataset that takes more than 60 s to produce."""
    request_id = _lock_requested(world)
    controller = _controller(world, clock)
    real_setup = db_session.transaction_setup

    def lowered(connection: Any, *args: Any, **kwargs: Any) -> None:
        real_setup(connection, *args, **kwargs)
        connection.exec_driver_sql(
            f"SET LOCAL idle_in_transaction_session_timeout = {LOWERED_IDLE_MS}"
        )

    registry = close_dependencies.snapshot_registry()
    first_kind = close_dependencies.snapshot_engine().kinds[0]
    seen: dict[str, str] = {}
    show = text("SHOW idle_in_transaction_session_timeout")
    real_store = snapshots.store_file

    def slow(reader: Any, scope: Any) -> Any:
        seen["reader"] = str(reader.session.execute(show).scalar_one())
        time.sleep(SLOW_PRODUCER_SECONDS)
        return registry.datasets[first_kind](reader, scope)

    def stored(uow: Any, **kwargs: Any) -> Any:
        seen.setdefault("decision", str(uow.session.execute(show).scalar_one()))
        return real_store(uow, **kwargs)

    delayed = dataclasses.replace(registry, datasets={**registry.datasets, first_kind: slow})
    with monkeypatch.context() as patched:
        patched.setattr(db_session, "transaction_setup", lowered)
        patched.setattr(close_dependencies, "snapshot_registry", lambda: delayed)
        patched.setattr(snapshots, "store_file", stored)
        decided = approve(world.app, request_id, controller)
    assert decided.status_code == 200, decided.text
    assert seen == {"reader": "15min", "decision": "15min"}
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert _state(world, OCTOBER)["state"] == PeriodState.OPEN.value


def _in_thread(call: Any, name: str) -> tuple[threading.Thread, dict[str, Any]]:
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["response"] = call()
        except Exception as error:  # noqa: BLE001 - surfaced by the caller's assertions
            outcome["error"] = error

    return threading.Thread(target=run, name=name), outcome


def test_g3_a_period_changed_while_the_lock_decision_waited_ends_it_stale(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Review gap G3, the basis. T1 — Maya's cancel-close of September — has moved the period to
    ``open`` and is NOT committed: it holds the state row. T2 — the Controller's approval of the
    pending lock request — passes the approval kernel's comparison of the basis (the committed
    row is still the one the request was made on) and is observed WAITING for the row. T1 commits.
    The decision then compares the basis again, under the row: 409 ``stale-approval``, and the
    request is VOIDED ``STALE_SUBJECT``.

    Fail-first: the hook decided on the changed row by its state alone — 409
    ``invalid-transition`` — and left the request PENDING, to be decided again on a period the
    approver had not reviewed in that state."""
    request_id = _lock_requested(world)
    controller = _controller(world, clock)
    decision, outcome = _in_thread(
        lambda: approve(world.app, request_id, controller), "lock-decision"
    )
    held = world.place.uow()
    uow = held.__enter__()
    started = False
    try:
        close_commands.cancel_close(
            uow,
            state_id=world.state_id,
            body=PeriodCancelCloseIn(
                reason_code=ReasonCode.DATA_CORRECTION_PENDING, comment="One invoice is missing"
            ),
            check_version=lambda actual: None,
        )
        uow.session.flush()  # T1: the row is held, the move is not committed
        with observing_checkouts() as backends:
            holder_pid = backend_pid(uow.session)
            decision.start()
            started = True
            blocked_pid, blocked_in = await_lock_wait(
                uow.session,
                holder_pid=holder_pid,
                backends=backends,
                timeout=WAIT_SECONDS,
                expect="period_state",
            )
        assert blocked_pid != holder_pid and "for update" in blocked_in.lower(), blocked_in
        assert decision.is_alive() and "response" not in outcome
        uow.commit()
    finally:
        held.__exit__(None, None, None)
        if started:
            decision.join(timeout=JOIN_SECONDS)
    assert not decision.is_alive() and "error" not in outcome, outcome
    refused = outcome["response"]
    assert (refused.status_code, slug(refused)) == (409, "stale-approval"), refused.text
    assert _request(world, request_id) == ("VOIDED", "STALE_SUBJECT")
    assert _state(world)["state"] == PeriodState.OPEN.value
    with system_session(world) as session:
        locks = session.execute(
            select(func.count())
            .select_from(period_lock)
            .where(period_lock.c.period_id == world.period_id)
        ).scalar_one()
    assert int(locks) == 0


@dataclasses.dataclass(frozen=True)
class Beside:
    """September's lock request pending beside a reopen request of August that needs one more
    approval."""

    lock_request_id: str
    reopen_request_id: str
    marcus: Actor
    elena: Actor


def _reopen_beside_the_lock(world: CloseWorld, clock: FrozenClock) -> Beside:
    """September's lock is requested (January to August closed); Priya requests the reopen of
    August — admitted, no later period is closed (BR-CLS-05) — and Marcus has approved it, one of
    two. Elena's approval completes the reopen; Marcus's decides September's lock."""
    lock_request_id = _lock_requested(world)
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    marcus = _controller(world, clock, "marcus")
    elena = _controller(world, clock, "elena")
    august = _state(world, AUGUST)
    requested = post(
        world.app,
        f"{PERIODS}/{august['id']}/request-reopen",
        priya,
        {
            "judgement_record_id": str(reviewed_error_judgement(world)),
            "reason_code": "ERROR_CORRECTION",
            "comment": "An August invoice was omitted.",
        },
        if_match=f'"r{august["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    reopen_request_id = str(requested.json()["approval_request_id"])
    assert approve(world.app, reopen_request_id, marcus).status_code == 200
    assert _request(world, reopen_request_id)[0] == "PENDING"
    return Beside(lock_request_id, reopen_request_id, marcus, elena)


@contextmanager
def _audit_head_held(world: CloseWorld) -> Iterator[Any]:
    """A transaction that holds the tenant's audit chain head: every command of the tenant does
    all its work and then waits at its commit (the head is the last lock of DG-KRN-DB-08)."""
    with system_session(world) as holder:
        holder.execute(
            select(audit_chain_head.c.tenant_id)
            .where(audit_chain_head.c.tenant_id == world.tenant_id)
            .with_for_update()
        ).all()
        try:
            yield holder
        finally:
            holder.rollback()


def test_g3_a_later_periods_lock_decision_is_refused_beside_and_after_a_reopen(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """PRD BR-CLS-05 with BR-CLS-08, the reopen first. Elena's approval of August's reopen has
    done its work — it holds August's state row ``FOR UPDATE`` — and waits at its commit. Marcus's
    decision of September's lock reads the earlier rows ``FOR SHARE NOWAIT``: 409 ``lock-conflict``
    at once, nothing written (its ``APPROVALS_CLEARED`` gate fails as well while the reopen
    request reads PENDING — BR-CLS-01 — and the held row answers first). The reopen commits; the
    same decision is then 409 ``earlier-period-open``. In neither order is September locked above
    a reopened August.

    The first refusal is by name (supervisor ruling R-119 (d); PRD ERR-85): rule
    ``EARLIER_PERIOD_HELD``, the detail naming August and September. Fail-first: rule
    ``LOCK_TIMEOUT`` and the copy of a lock wait — "held … for longer than the platform waits" —
    for a read that waits for nothing."""
    beside = _reopen_beside_the_lock(world, clock)
    names = {key: _state(world, key)["period"]["name"] for key in (AUGUST, SEPTEMBER)}
    detail = EARLIER_HELD.format(earlier_period=names[AUGUST], period=names[SEPTEMBER])
    reopen, outcome = _in_thread(
        lambda: approve(world.app, beside.reopen_request_id, beside.elena), "reopen-decision"
    )
    started = False
    with _audit_head_held(world) as holder:
        try:
            with observing_checkouts() as backends:
                holder_pid = backend_pid(holder)
                reopen.start()
                started = True
                await_lock_wait(
                    holder,
                    holder_pid=holder_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="audit_chain_head",
                )
            assert reopen.is_alive() and "response" not in outcome
            refused = approve(world.app, beside.lock_request_id, beside.marcus)
            assert (refused.status_code, slug(refused)) == (409, "lock-conflict"), refused.text
            problem = refused.json()
            assert problem["detail"] == detail
            assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
                (RULE_EARLIER_HELD, detail)
            ]
            assert _request(world, beside.lock_request_id) == ("PENDING", None)
            holder.rollback()  # the reopen commits
        finally:
            if started:
                reopen.join(timeout=JOIN_SECONDS)
    assert not reopen.is_alive() and "error" not in outcome, outcome
    assert outcome["response"].status_code == 200, outcome["response"].text
    assert _state(world, AUGUST)["state"] == PeriodState.REOPENED.value
    after = approve(world.app, beside.lock_request_id, beside.marcus)
    assert (after.status_code, slug(after)) == (409, "earlier-period-open"), after.text
    assert _state(world)["state"] == PeriodState.CLOSING.value
    assert _request(world, beside.lock_request_id) == ("PENDING", None)


@contextmanager
def _september_reconciliations_held(world: CloseWorld) -> Iterator[Any]:
    """A transaction that holds September's reconciliations. The lock decision certifies them
    after its lock row, so it reads the earlier periods, freezes, writes the lock and then waits
    there; no other command of this test touches those rows."""
    with system_session(world) as holder:
        held = holder.execute(
            select(reconciliation.c.id)
            .where(
                reconciliation.c.entity_id == world.entity_id,
                reconciliation.c.period_id == world.period_id,
            )
            .with_for_update()
        ).all()
        assert held
        try:
            yield holder
        finally:
            holder.rollback()


def _setup_completed_events(world: CloseWorld) -> int:
    """The tenant's ``tenant.setup_completed`` audit events (04 T-PLT-01: at most one, ever)."""
    with system_session(world) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == setup.COMPLETED_ACTION)
            ).scalar_one()
        )


def test_g3_a_reopen_waits_for_a_later_periods_lock_decision_and_is_refused(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """PRD BR-CLS-05 with BR-CLS-08, the lock first — the order review gap G3 names. Marcus's
    decision of September's lock has judged its gates, read August's row ``FOR SHARE`` and written
    the lock; it is in flight, not committed. Only now is August's reopen requested: the request
    is admitted — September is still ``closing`` for every other transaction — and approved once.
    Elena's completing approval is observed WAITING for August's row, held by the lock decision.
    The lock commits; the reopen then reads the later periods under its row: September is
    ``closed``, 409 ``later-period-closed``, and August stays closed. A later period's lock
    decision in flight is invisible to the reopen REQUEST and not to the reopen.

    Item SETUP-COMPLETION-LOCK-1 (supervisor ruling R-119 (d); dev-guide DG-KRN-DB-08 (3a)). The
    world's tenant has NOT completed its setup (PRD BR-PLT-02): its roles are fixture grants, and
    no period is ``open`` until this lock decision opens October. Marcus's approval is therefore
    the command that completes the setup — its last step, after the hook, on the tenant's row —
    while Elena's approval, which has inserted its decision row and so holds the tenant's row
    ``FOR KEY SHARE``, waits for August's row. ``FOR NO KEY UPDATE`` does not wait for her; the
    interleaving ends as above and the setup is completed once.

    Fail-first (the tenant's row ``FOR UPDATE``): the lock decision waited for the reopen
    decision's transaction and the reopen decision for the lock decision's — PostgreSQL ended
    one of the two, 40P01, answered 409 ``lock-conflict`` ("Another change to the same records
    was being saved at the same moment"); in three measured runs it was the reopen."""
    marcus = _controller(world, clock, "marcus")
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    nora = _controller(world, clock, "nora")
    elena = _controller(world, clock, "elena")
    lock_request_id = _lock_requested(world)
    with system_session(world) as session:
        assert not setup.setup_completed(session, world.tenant_id)
    assert _setup_completed_events(world) == 0
    lock, locked = _in_thread(lambda: approve(world.app, lock_request_id, marcus), "lock-decision")
    reopened: dict[str, Any] = {}
    reopen: threading.Thread | None = None
    lock_started = False
    with _september_reconciliations_held(world) as holder:
        try:
            with observing_checkouts() as lock_backends:
                holder_pid = backend_pid(holder)
                lock.start()
                lock_started = True
                lock_pid, _ = await_lock_wait(
                    holder,
                    holder_pid=holder_pid,
                    backends=lock_backends,
                    timeout=WAIT_SECONDS,
                    expect="reconciliation",
                )
            august = _state(world, AUGUST)
            requested = post(
                world.app,
                f"{PERIODS}/{august['id']}/request-reopen",
                priya,
                {
                    "judgement_record_id": str(reviewed_error_judgement(world)),
                    "reason_code": "ERROR_CORRECTION",
                    "comment": "An August invoice was omitted.",
                },
                if_match=f'"r{august["row_version"]}"',
            )
            assert requested.status_code == 200, requested.text  # September reads `closing`
            reopen_request_id = str(requested.json()["approval_request_id"])
            assert approve(world.app, reopen_request_id, nora).status_code == 200  # one of two
            reopen, reopened = _in_thread(
                lambda: approve(world.app, reopen_request_id, elena), "reopen-decision"
            )
            with observing_checkouts() as reopen_backends:
                reopen.start()
                blocked_pid, blocked_in = await_lock_wait(
                    holder,
                    holder_pid=lock_pid,
                    backends=reopen_backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
            assert blocked_pid != lock_pid and "for update" in blocked_in.lower(), blocked_in
            assert lock.is_alive() and reopen.is_alive()
            holder.rollback()  # the lock decision commits; the reopen gets August's row
        finally:
            if lock_started:
                lock.join(timeout=JOIN_SECONDS)
            if reopen is not None and reopen.ident is not None:
                reopen.join(timeout=JOIN_SECONDS)
    assert not lock.is_alive() and "error" not in locked, locked
    assert locked["response"].status_code == 200, locked["response"].text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert reopen is not None and not reopen.is_alive() and "error" not in reopened, reopened
    refused = reopened["response"]
    assert (refused.status_code, slug(refused)) == (409, "later-period-closed"), refused.text
    assert _state(world, AUGUST)["state"] == PeriodState.CLOSED.value
    # the lock decision's command completed the setup, once, beside the waiting reopen
    with system_session(world) as session:
        assert setup.setup_completed(session, world.tenant_id)
    assert _setup_completed_events(world) == 1


def test_br_cls_08_a_lock_request_names_the_earlier_period_another_request_holds(
    world: CloseWorld,
) -> None:
    """Supervisor ruling R-119 (d) (PRD ERR-85; 04 §16.8 "Chronological lock and opening"), the
    request path. Another transaction holds August's state row for a change. Maya's lock request
    for September reads the earlier rows ``FOR SHARE NOWAIT``: 409 ``lock-conflict`` at once
    under rule ``EARLIER_PERIOD_HELD``, the detail naming August and September; no request is
    created. Once the holder has ended the SAME request — its ``Idempotency-Key`` and body
    unchanged — is accepted (04 API-C-04 rev 1.144: the refusal is not kept for the key).

    Fail-first: rule ``LOCK_TIMEOUT`` and the copy of a lock wait, for a read that does not
    wait."""
    shown = _ready_for_lock(world)
    august = _state(world, AUGUST)
    detail = EARLIER_HELD.format(
        earlier_period=august["period"]["name"], period=shown["period"]["name"]
    )
    headers = cookie_headers(world.maya.token, world.maya.csrf_token, key=True)
    headers["If-Match"] = f'"r{shown["row_version"]}"'

    def request_lock() -> HttpResponse:
        return call(
            world.app,
            "POST",
            f"{PERIODS}/{shown['id']}/request-lock",
            json={"certification_comment": COMMENT},
            headers=dict(headers),
        )

    def requests() -> int:
        with system_session(world) as session:
            return int(
                session.execute(
                    select(func.count())
                    .select_from(approval_request)
                    .where(approval_request.c.subject_id == world.state_id)
                ).scalar_one()
            )

    with system_session(world) as holder:
        held = holder.execute(
            select(period_state.c.state)
            .where(period_state.c.id == UUID(str(august["id"])))
            .with_for_update()
        ).scalar_one()
        assert _value(held) == PeriodState.CLOSED.value
        refused = request_lock()
        assert (refused.status_code, slug(refused)) == (409, "lock-conflict"), refused.text
        problem = refused.json()
        assert problem["detail"] == detail
        assert [(error["rule_id"], error["message"]) for error in problem["errors"]] == [
            (RULE_EARLIER_HELD, detail)
        ]
        assert requests() == 0
        holder.rollback()
    accepted = request_lock()
    assert accepted.status_code == 200, accepted.text
    assert requests() == 1
