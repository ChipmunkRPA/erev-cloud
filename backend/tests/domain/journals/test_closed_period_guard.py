"""Item JR-CLOSED-PERIOD-GUARD-1 (supervisor ruling R-97 (7) on gap G2 of the independent review
of revision 0084; 04 §14.1 DB-07 and "DB-07 row lock and lock order", §16.7 rev 1.205; PRD SM-08
and ERR-86 rev 1.134; dev-guide DG-KRN-DB-08 rev 1.188; Alembic revision 0104; CTL-015): a journal
run is neither calculated nor cancelled in a period that is ``closed`` or ``permanently_locked``.

Until this item a journal run had no period read of its own — only its lines met the DB-07 guard.
Measured on the tree before it: a period whose only run was a ``draft`` run without batches
locked; that run was then cancelled (200), which left a locked period without a run that is not
cancelled; and ``POST /journal-runs`` put a new ``draft`` run into the closed period (202, its job
SUCCEEDED with no line).

World: the close world — AVM-US, FY2026-P09 (September 2026), no sealed activity, so a calculated
run has no batch. The two interleavings run against the real approval of the period's lock; the
triggers themselves are witnessed at the database in ``tests/pg/test_journal_guards.py``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import approval_request, job, journal_run
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import gates
from erev_api.domain.journals import failed_exits
from erev_api.enums import ApprovalRequestStatus, JobKind, LockKind, PeriodState
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import TYPE_BASE, Problem
from erev_api.schemas.journals import JournalRunCancelIn
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.close_world import (
    JOURNAL_RUN_ID_HEADER,
    JOURNAL_RUNS,
    CloseWorld,
    actor_with_role,
    close_run_succeeded,
    close_world,
    earlier_periods_closed,
    requested_journal_run,
    reviewed_error_judgement,
    reviewed_reconciliations,
    run_journal_job,
    system_session,
)
from support.db import TestDatabase
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor
from support.reference import PERIODS, approve, get, periods, post, slug
from support.rows import approval_request_values

KEY: Final = "FY2026-P09"
CLOSED: Final = "Sep 2026 is closed for AVM-US in book ASC606."
NOT_CALCULATED: Final = f"{CLOSED} A journal run cannot be calculated for a closed period."
NOT_CANCELLED: Final = f"{CLOSED} A journal run of a closed period cannot be cancelled."
PERIOD_CLOSED: Final = f"{TYPE_BASE}period-closed"
RULE: Final = "RUN_PERIOD_CLOSED"
REASON: Final = "Not needed."
WAIT_SECONDS: Final = 8.0  # under the sessions' lock_timeout of 10 s
JOIN_SECONDS: Final = 30.0


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


# --- helpers --------------------------------------------------------------------------------------


def _state(world: CloseWorld) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == KEY
    ]
    return found


def _runs(world: CloseWorld) -> list[tuple[str, str, int]]:
    """(run no, state, line count) of September's journal runs, oldest first."""
    with system_session(world) as session:
        rows = session.execute(
            select(journal_run.c.run_no, journal_run.c.state, journal_run.c.line_count)
            .where(journal_run.c.period_id == world.period_id)
            .order_by(journal_run.c.created_at, journal_run.c.run_no)
        ).all()
    return [
        (str(row.run_no), str(getattr(row.state, "value", row.state)), int(row.line_count))
        for row in rows
    ]


def _calculations(world: CloseWorld) -> int:
    """The number of ``JOURNAL_RUN_CALCULATE`` jobs of the tenant."""
    with system_session(world) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(job)
                .where(job.c.kind == JobKind.JOURNAL_RUN_CALCULATE.value)
            ).scalar_one()
        )


def _calculated(world: CloseWorld) -> str:
    """September's journal run as the product calculates it — a ``draft`` run without batches,
    the period holding no sealed activity; its id."""
    job_id, run_id = requested_journal_run(world)
    finished = run_journal_job(world, job_id)
    assert finished["state"] == "SUCCEEDED", finished
    return str(run_id)


def _soft_close(world: CloseWorld) -> None:
    """September in soft close; the earlier periods of AVM-US are closed first (BR-CLS-08)."""
    earlier_periods_closed(world, before=KEY)
    shown = _state(world)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": "September 2026 close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text


def _lock_by_writer(world: CloseWorld) -> None:
    """``closing`` → ``closed`` through the close domain's own writer, with an APPROVED request
    (T-REF-07): fixture state for a rule about a closed period. No gate is evaluated and nothing
    is frozen; the two interleavings below use the real decision."""
    state_id = world.state_id
    with world.place.uow() as uow:
        session = uow.session
        scope = gates.period_scope(session, state_id, lock=True)
        assert scope is not None and scope.state == PeriodState.CLOSING.value
        request = approval_request_values(
            world.tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            entity_id=world.entity_id,
            subject_type="PERIOD_LOCK",
            subject_id=state_id,
            summary="Fixture lock request",
        )
        session.execute(insert(approval_request).values(**request))
        close_commands._persist_lock(
            uow,
            scope,
            kind=LockKind.LOCK,
            lock_id=new_id(),
            transition_id=new_id(),
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=close_commands.LOCK_ACTION,
            approval_request_id=UUID(str(request["id"])),
            comment="Fixture lock",
            certification=[],
            snapshot_manifest_sha256=None,
            heads=close_commands._heads(session, scope),
            cutoff_known_at=uow.now,
        )
        uow.commit()
    assert _state(world)["state"] == PeriodState.CLOSED.value


def _pending_lock(world: CloseWorld, clock: FrozenClock) -> tuple[str, Actor]:
    """September ready for its lock decision, its gates passing on the product's own run: the
    reconciliations reviewed and the close run succeeded (fixture rows), the lock requested by
    one Controller; (the request, another Controller with a fresh TOTP)."""
    with system_session(world) as session:
        reviewed_reconciliations(session, world, None)
        close_run_succeeded(session, world, None)
    submitter = actor_with_role(world.app, clock, world.tenant_id, "controller", name="marcus")
    shown = _state(world)
    requested = post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-lock",
        submitter,
        {"certification_comment": "September 2026 close complete"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    decider = actor_with_role(world.app, clock, world.tenant_id, "controller", name="cora")
    return str(requested.json()["approval_request_id"]), decider


def _cancel(world: CloseWorld, run_id: str) -> Any:
    return post(world.app, f"{JOURNAL_RUNS}/{run_id}/cancel", world.maya, {"reason": REASON})


def _errors(response: Any) -> list[tuple[str | None, str, str]]:
    return [(e["field"], e["rule_id"], e["message"]) for e in response.json()["errors"]]


# --- the two refusals by name ---------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_a_journal_run_is_not_calculated_for_a_closed_period(world: CloseWorld) -> None:
    """PRD ERR-86 (04 §16.7 API-S-JournalRunCreate rev 1.205): ``POST /journal-runs`` for a
    period that is ``closed`` answers 409 ``period-closed`` under rule ``RUN_PERIOD_CLOSED`` on
    ``period_key``, defers no job and writes no run. Before the item it answered 202 and its job
    put a ``draft`` run without lines into the locked period."""
    _soft_close(world)
    _calculated(world)
    _lock_by_writer(world)
    runs, jobs = _runs(world), _calculations(world)
    assert [(state, lines) for _, state, lines in runs] == [("draft", 0)]

    refused = post(
        world.app, JOURNAL_RUNS, world.maya, {"entity_code": "AVM-US", "period_key": KEY}
    )
    assert refused.status_code == 409, refused.text  # before the item: 202
    assert (slug(refused), refused.json()["detail"]) == ("period-closed", NOT_CALCULATED)
    assert _errors(refused) == [("period_key", RULE, NOT_CALCULATED)]
    assert JOURNAL_RUN_ID_HEADER not in refused.headers
    assert (_runs(world), _calculations(world)) == (runs, jobs)


@pytest.mark.slow
def test_a_journal_run_is_not_calculated_for_a_future_period(world: CloseWorld) -> None:
    """PRD SM-08 "Run journals": its guard — the period is ``open``, ``closing`` or ``reopened``
    — was stated and never enforced (the supervisor's ruling of 2026-10-01 08:31). ``POST
    /journal-runs`` for a period that is not open yet answers 422 ``validation-failed`` on
    ``period_key`` and defers no job: no posting can stand in such a period, so a run there has
    no line. Before the item it answered 202 and its job put a run into the ``future`` period."""
    future = sorted(
        item["period"]["period_key"]
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["state"] == PeriodState.FUTURE.value
    )
    assert future, "the close world has no future period of AVM-US"
    jobs = _calculations(world)

    refused = post(
        world.app, JOURNAL_RUNS, world.maya, {"entity_code": "AVM-US", "period_key": future[0]}
    )
    assert refused.status_code == 422, refused.text  # before the item: 202
    sentence = (
        f"{future[0]} is not open yet for AVM-US in book ASC606. Open the period before running "
        "journals."
    )
    assert slug(refused) == "validation-failed"
    assert _errors(refused) == [("period_key", "T-SL-06", sentence)]
    assert JOURNAL_RUN_ID_HEADER not in refused.headers
    assert _calculations(world) == jobs


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_a_calculation_that_meets_a_lock_fails_by_name_and_writes_nothing(
    world: CloseWorld,
) -> None:
    """The command's read is a plain one; the job reads the period again under its state row
    (``summarise.hold_period``). A calculation accepted while September was in soft close and run
    after the lock ends ``FAILED`` with the problem of PRD ERR-86 and writes no run. Before the
    item the job SUCCEEDED and the run stood in the closed period."""
    _soft_close(world)
    # asked for while September has no run: beside a run, with nothing for a new one to summarize,
    # the command itself answers 409 since item JRN-EMPTY-RUN-1 (PRD ERR-96). The run follows it.
    job_id, run_id = requested_journal_run(world)  # accepted: the period is in soft close
    _calculated(world)
    _lock_by_writer(world)
    runs = _runs(world)

    finished = run_journal_job(world, job_id)
    assert finished["state"] == "FAILED", finished  # before the item: SUCCEEDED
    problem = finished["problem"]
    assert (problem["type"], problem["status"], problem["detail"]) == (
        PERIOD_CLOSED,
        409,
        NOT_CALCULATED,
    )
    assert [(e["field"], e["rule_id"]) for e in problem["errors"]] == [("period_key", RULE)]
    assert _runs(world) == runs
    missing = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_the_only_run_of_a_closed_period_is_not_cancelled(world: CloseWorld) -> None:
    """PRD ERR-86 (04 §16.7 ``cancel`` (d) rev 1.205): the cancel of a run whose period is
    ``closed`` answers 409 ``period-closed`` under rule ``RUN_PERIOD_CLOSED`` and the run stands.
    A period needs a run that is not cancelled to lock (the gates' "Journal run not calculated");
    before the item its only run was cancelled after the lock, 200."""
    _soft_close(world)
    run_id = _calculated(world)
    _lock_by_writer(world)
    runs = _runs(world)

    refused = _cancel(world, run_id)
    assert refused.status_code == 409, refused.text  # before the item: 200
    assert (slug(refused), refused.json()["detail"]) == ("period-closed", NOT_CANCELLED)
    assert _errors(refused) == [(None, RULE, NOT_CANCELLED)]
    assert _runs(world) == runs and runs[0][1] == "draft"
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert (shown.status_code, shown.json()["state"]) == (200, "draft")


# --- beside the real lock decision ----------------------------------------------------------------


def _meeting_the_decision(
    monkeypatch: pytest.MonkeyPatch, late: Callable[[], None], name: str
) -> tuple[threading.Thread, dict[str, Any]]:
    """Arrange that ``late`` starts on a thread of its own once the lock decision has judged its
    gates and frozen its datasets, and that the decision goes on only after that thread is
    observed WAITING for a lock the decision's backend holds, in a statement that reads
    ``period_state``. Returns the thread and what was seen."""
    freeze_datasets = close_commands.snapshots.freeze_datasets
    thread = threading.Thread(target=late, name=name)
    seen: dict[str, Any] = {}

    def freeze_then_meet(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        datasets = freeze_datasets(uow, *args, **kwargs)
        if thread.ident is None:  # once
            with observing_checkouts() as backends:
                decision_pid = backend_pid(uow.session)
                thread.start()
                _, seen["blocked_in"] = await_lock_wait(
                    uow.session,
                    holder_pid=decision_pid,
                    backends=backends,
                    timeout=WAIT_SECONDS,
                    expect="period_state",
                )
            seen["waiting"] = thread.is_alive()
        return datasets

    monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_meet)
    return thread, seen


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_a_cancel_that_arrives_while_the_lock_is_decided_waits_and_is_refused(
    world: CloseWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Gap G2, the cancel: the lock decision holds September's state row ``FOR UPDATE`` from its
    first read, judges its gates on the period's only run and freezes its datasets. The cancel of
    that run then arrives: it is observed WAITING — blocked by the decision's backend in its
    ``FOR SHARE`` read of the state row — and writes nothing. The decision completes with the run
    it counted, and the cancel is refused by name (PRD ERR-86); the run stands in the closed
    period. Before the item the cancel did not wait: it committed beside the decision, which
    locked a period whose only run was cancelled — or refused itself on its count of the runs,
    depending on which side of that count the cancel fell."""
    _soft_close(world)
    run_id = _calculated(world)
    request_id, controller = _pending_lock(world, clock)
    outcome: dict[str, Any] = {}

    def cancel_late() -> None:
        try:
            with world.place.uow() as uow:
                failed_exits.cancel_run(uow, UUID(run_id), JournalRunCancelIn(reason=REASON))
                uow.commit()
            outcome["result"] = "cancelled"
        except Problem as problem:
            outcome["result"] = (problem.slug, problem.detail)
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    thread, seen = _meeting_the_decision(monkeypatch, cancel_late, "g2-late-cancel")
    try:
        decided = approve(world.app, request_id, controller)
    finally:
        if thread.ident is not None:
            thread.join(timeout=JOIN_SECONDS)
    assert decided.status_code == 200, decided.text
    assert not thread.is_alive() and seen["waiting"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    assert "for share" in seen["blocked_in"].lower(), seen["blocked_in"]
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert outcome["result"] == ("period-closed", NOT_CANCELLED)  # before the item: "cancelled"
    assert [(state, lines) for _, state, lines in _runs(world)] == [("draft", 0)]


@pytest.mark.slow
@pytest.mark.control("CTL-015")
def test_a_calculation_that_arrives_while_the_lock_is_decided_waits_and_is_refused(
    world: CloseWorld, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    """Gap G2, the calculation: a second calculation was accepted in soft close; its job starts
    while the lock is being decided. It is observed WAITING for September's state row — after the
    coverage key of its entity, book and period and before it has read the key's runs or taken a
    number from a series — and writes nothing. The decision completes; the job then reads
    ``closed`` and ends ``FAILED`` with the problem of PRD ERR-86. Before the item a calculation
    without lines met no guard: its run was inserted beside the decision."""
    _soft_close(world)
    # accepted while September has no run (PRD ERR-96 refuses it beside one, item
    # JRN-EMPTY-RUN-1); the period's run, on which the lock is decided, is calculated after it
    job_id, run_id = requested_journal_run(world)
    _calculated(world)
    request_id, controller = _pending_lock(world, clock)
    runs = _runs(world)
    outcome: dict[str, Any] = {}

    def calculate_late() -> None:
        try:
            outcome["job"] = dict(run_journal_job(world, job_id, attempts=1))
        except Exception as error:  # noqa: BLE001 - surfaced by the assertions below
            outcome["error"] = error

    thread, seen = _meeting_the_decision(monkeypatch, calculate_late, "g2-late-calculation")
    try:
        decided = approve(world.app, request_id, controller)
    finally:
        if thread.ident is not None:
            thread.join(timeout=JOIN_SECONDS)
    assert decided.status_code == 200, decided.text
    assert not thread.is_alive() and seen["waiting"] is True and "error" not in outcome, (
        seen,
        outcome,
    )
    assert "for share" in seen["blocked_in"].lower(), seen["blocked_in"]
    assert _state(world)["state"] == PeriodState.CLOSED.value
    finished = outcome["job"]
    assert finished["state"] == "FAILED", finished  # before the item: SUCCEEDED
    assert (finished["problem"]["type"], finished["problem"]["detail"]) == (
        PERIOD_CLOSED,
        NOT_CALCULATED,
    )
    assert _runs(world) == runs
    missing = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert missing.status_code == 404, missing.text


# --- the rule ends with a reopen ------------------------------------------------------------------


@pytest.mark.slow
def test_a_run_is_calculated_and_cancelled_in_a_reopened_period(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """The rule is about a closed period, not about a period that was closed once: after the
    reopen (two Controllers, PRD BR-CLS-06) September takes postings again, so a journal run is
    calculated for it and cancelled in it as in any open period."""
    _soft_close(world)
    first = _calculated(world)
    _lock_by_writer(world)
    assert _cancel(world, first).status_code == 409

    requester = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    shown = _state(world)
    requested = post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-reopen",
        requester,
        {
            "judgement_record_id": str(reviewed_error_judgement(world)),
            "reason_code": "ERROR_CORRECTION",
            "comment": "A late credit memo for September.",
        },
        if_match=f'"r{shown["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    for name in ("marcus", "elena"):
        controller = actor_with_role(world.app, clock, world.tenant_id, "controller", name=name)
        decided = approve(world.app, request_id, controller)
        assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.REOPENED.value

    # the run of the closed period is cancelled now, and the period calculated again. (Until item
    # JRN-EMPTY-RUN-1 a second run was calculated beside the first and two drafts stood here; a
    # run that would summarize nothing is no longer made, PRD ERR-96.)
    reopened = _cancel(world, first)
    assert (reopened.status_code, reopened.json()["state"]) == (200, "cancelled")
    second = _calculated(world)  # 202, and its job SUCCEEDED
    assert [(state, lines) for _, state, lines in _runs(world)] == [("cancelled", 0), ("draft", 0)]
    cancelled = _cancel(world, second)
    assert (cancelled.status_code, cancelled.json()["state"]) == (200, "cancelled")
