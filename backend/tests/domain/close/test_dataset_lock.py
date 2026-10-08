"""The lock whose datasets stand, on a database (item PERMLOCK-DATASETS-1 — PRODUCT DEFECT, a
release blocker; the supervisor's ruling of 2026-10-02 16:16; 04 API-S-Period ``dataset_lock`` and
§16.9 rev 1.301; ENGINE_SPEC_B S15-R-19 rev 1.167).

MEASURED before the item (``worlds.k01_pellworth`` through 31 Aug 2026; August locked through
the product and then permanently locked by a second Controller's decision): the period's
``current_lock`` is its ``PERMANENT_LOCK`` record, which holds no dataset and names the ``LOCK``
as ``previous_lock_id``; a ``contract_balances`` run given the current lock was created, queued
and ended ``FAILED`` — "Lock <id> holds no CONTRACT_BALANCES dataset for contract_balances." —
while the same run given the ``LOCK`` succeeded. API-S-Period named the current record alone, so
every report "as locked" of a permanently locked period — the periods that are final — ended in
a failed run.

- A permanently locked period names the ``LOCK`` whose datasets stand, and is read as locked
  through it; the record that froze nothing is refused where the run is created and where a
  stored run that names it is rerun.
- The member through a period's life: never locked, closed, reopened, closed again, permanently
  locked — and the refusal names the lock that stands in each.
- Over rows no writer of the product leaves: a permanent lock that follows no ``LOCK`` of its
  own period names none.

DB-bound; the first test stands on the record clock (the lock freezes its datasets at an instant
that has to follow the contract versions' record stamps: ``worlds.on_record_clock``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, period_lock, period_state, period_state_transition
from erev_api.db.tables import report_run as report_run_table
from erev_api.domain.close import commands as close_commands
from erev_api.domain.reports import locked
from erev_api.enums import LockKind, PeriodState, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.schemas.periods import PeriodLockRequestIn
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.orm import Session
from support.close_world import (
    CloseWorld,
    acknowledged_run,
    actor_with_role,
    close_run_succeeded,
    close_world,
    earlier_periods_closed,
    periods_closed_before,
    reviewed_error_judgement,
    reviewed_reconciliations,
    system_session,
)
from support.db import TestDatabase
from support.principals import Actor
from support.reference import PERIODS, approve, assign, get, periods, post
from support.rows import (
    CloseParts,
    insert_approval_request,
    insert_reopen_record,
    period_lock_values,
    period_state_transition_values,
)
from support.worlds import (
    AUGUST_2026,
    AVM_US,
    JOBS,
    K01,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    ReportWorld,
    k01_pellworth,
    on_record_clock,
    period_locked,
    report_run,
    run_now,
    verified,
)

CODE: Final = "contract_balances"
BOOK: Final = "ASC606"
SEPTEMBER: Final = "FY2026-P09"
K01_ROW: Final = f"contract:{K01}:{AVM_US}"
REASON: Final = "Costs of 20,500.00 on PRJ-CB-2026-01 incurred on 29 Sep 2026 were omitted."
NOT_A_LOCK: Final = "Lock {lock} is {record} of {period}: it froze no dataset (E-63 {kind})."
PASS: Final = "The datasets of {period} are those of lock {dataset_lock}; pass that lock."
NONE_STANDS: Final = (
    "No lock's datasets stand for {period}: run the report current (known_at) instead, or pass "
    "a LOCK record of the period (GET /periods/{{id}}/locks)."
)
MISSING_DATASET: Final = "Lock {lock} holds no CONTRACT_BALANCES dataset for contract_balances."
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _row(app: FastAPI, actor: Actor, period_key: str) -> dict[str, Any]:
    """The row of AVM-US's period in ``GET /periods``."""
    (row,) = [
        item
        for item in periods(app, actor, entity=AVM_US)
        if item["period"]["period_key"] == period_key
    ]
    return dict(row)


def _period(app: FastAPI, actor: Actor, period_key: str) -> dict[str, Any]:
    """API-S-Period of AVM-US's period as ``GET /periods/{id}`` states it — and as its row of
    ``GET /periods`` states the two lock members, which is asserted equal here: the list reads
    them for a page in one statement, the single read for one period."""
    row = _row(app, actor, period_key)
    shown = get(app, f"{PERIODS}/{row['id']}", actor)
    assert shown.status_code == 200, shown.text
    found = dict(shown.json())
    assert (row["current_lock"], row["dataset_lock"]) == (
        found["current_lock"],
        found["dataset_lock"],
    )
    return found


def _sentence(kind: LockKind, lock_id: Any, period_key: str, dataset_lock_id: Any) -> str:
    """The refusal of S15-R-19 rev 1.167 for a record that froze nothing, written out here: the
    record, what it is and its period, then the lock that stands or that none does."""
    named = NOT_A_LOCK.format(
        lock=lock_id,
        record={LockKind.REOPEN: "a reopen record", LockKind.PERMANENT_LOCK: "the permanent lock"}[
            kind
        ],
        period=period_key,
        kind=kind.value,
    )
    if dataset_lock_id is None:
        return f"{named} {NONE_STANDS.format(period=period_key)}"
    return f"{named} {PASS.format(period=period_key, dataset_lock=dataset_lock_id)}"


def _as_locked(app: FastAPI, actor: Actor, period_key: str, lock_id: Any) -> Any:
    """``POST /report-runs``: ``contract_balances`` of AVM-US's period, as locked under
    ``lock_id``."""
    parameters = {
        "entity_codes": [AVM_US],
        "book": BOOK,
        "period_key": period_key,
        "period_lock_id": str(lock_id),
    }
    return post(
        app,
        REPORT_RUNS,
        actor,
        {"report_code": CODE, "parameters": parameters, "output_format": "JSON"},
    )


def _refused(response: Any, sentence: str) -> None:
    """422 ``validation-failed``: one finding on ``parameters.period_lock_id`` under S15-R-19."""
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["type"].endswith("/validation-failed")
    (error,) = problem["errors"]
    assert (error["field"], error["rule_id"]) == (locked.FIELD, locked.RULE)
    assert error["message"] == sentence


def _runs(tenant_id: UUID) -> int:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return int(session.execute(select(func.count()).select_from(report_run_table)).scalar_one())


def _locks(app: FastAPI, actor: Actor, state_id: Any) -> list[tuple[str, int, Any]]:
    """``GET /periods/{id}/locks``, newest first: kind, datasets held, the record it follows."""
    listed = get(app, f"{PERIODS}/{state_id}/locks", actor)
    assert listed.status_code == 200, listed.text
    return [
        (item["kind"], len(item["snapshots"]), item["previous_lock_id"])
        for item in listed.json()["items"]
    ]


# --- a permanently locked period, through the product ---------------------------------------------


def _settled(world: ReportWorld, started: Any) -> dict[str, Any]:
    """The worker's attempts on a created run until its job settles (a refused build ends
    ``FAILED`` after the second of the job's attempts); API-S-ReportRun."""
    assert started.status_code == 202, started.text
    job_id = UUID(str(started.json()["id"]))
    state = run_now(world, job_id)
    if state["state"] not in ("SUCCEEDED", "FAILED"):
        context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_FETCHED, {"id": task_id})
        run_job(job_id, world.tenant_id, attempt=2, runtime=world.runtime)
        state = dict(get(world.app, f"{JOBS}/{job_id}", world.maya).json())
    assert state["state"] in ("SUCCEEDED", "FAILED"), state
    shown = get(world.app, f"{REPORT_RUNS}/{started.headers[REPORT_RUN_ID_HEADER]}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def test_a_permanently_locked_period_is_read_as_locked_through_its_last_lock(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WLD-K-01 through 31 Aug 2026. August is locked through the product — the lock freezes the
    twelve datasets — and then permanently locked: requested by one Controller, decided by a
    second (SM-07), every earlier period permanently locked first.

    The period's current record is then its ``PERMANENT_LOCK``, which froze nothing. A run "as
    locked" that names it is refused where it is created, by the sentence that names the ``LOCK``
    to pass; before the item it was created, queued and ended ``FAILED`` — kept below as the
    control, with the refusal switched off. API-S-Period names that ``LOCK`` as ``dataset_lock``,
    in the single read and in the list, and the run given it returns what the lock froze:
    SF-ORD-10001's contract liability of 39,708.49 (PRD WLD-X-03)."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31))
    assign(world.priya.member, "revenue_reviewer")  # PRD §2.5: a journal run is hers to approve
    world = on_record_clock(world, clock)
    _, world = period_locked(world, clock, entity_code=AVM_US, period_key=AUGUST_2026)
    closed = _row(app, world.maya, AUGUST_2026)
    lock = closed["current_lock"]
    assert (closed["state"], lock["kind"]) == (PeriodState.CLOSED.value, LockKind.LOCK.value)
    frozen_run, frozen_rows = report_run(
        world,
        CODE,
        {
            "entity_codes": [AVM_US],
            "book": BOOK,
            "period_key": AUGUST_2026,
            "period_lock_id": lock["id"],
        },
    )
    (frozen,) = [row for row in frozen_rows if row["row_key"] == K01_ROW]
    assert frozen["contract_liability"] == "39708.49"

    # The permanent lock: the earlier periods first (SM-07, Q-6: fixture state), then Marcus
    # requests it and Elena, a second Controller, decides.
    periods_closed_before(
        world.place,
        app,
        world.maya,
        entity_id=world.entity_id,
        before=AUGUST_2026,
        permanently=True,
    )
    world = verified(world, clock, "marcus")
    requested = post(
        app,
        f"{PERIODS}/{closed['id']}/request-permanent-lock",
        world.marcus,
        {"comment": "August 2026 is final"},
        if_match=f'"r{closed["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    elena = actor_with_role(app, clock, world.tenant_id, "controller", name="elena")
    decided = approve(app, str(requested.json()["approval_request_id"]), elena)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    row = _row(app, world.maya, AUGUST_2026)
    permanent = row["current_lock"]
    assert (row["state"], permanent["kind"]) == (
        PeriodState.PERMANENTLY_LOCKED.value,
        LockKind.PERMANENT_LOCK.value,
    )
    assert permanent["id"] != lock["id"] and permanent["created_at"] > lock["created_at"]
    assert _locks(app, world.maya, row["id"]) == [
        (LockKind.PERMANENT_LOCK.value, 0, lock["id"]),
        (LockKind.LOCK.value, 12, None),
    ]

    # THE MEASURED CASE: the run that names the period's current record is refused where it is
    # created — nothing is queued to fail on a dataset the record never held.
    before = _runs(world.tenant_id)
    sentence = _sentence(LockKind.PERMANENT_LOCK, permanent["id"], AUGUST_2026, lock["id"])
    _refused(_as_locked(app, world.maya, AUGUST_2026, permanent["id"]), sentence)
    assert _runs(world.tenant_id) == before

    # The period names the lock whose datasets stand — the LOCK, member for member, with the
    # instant it was written at and not the permanent lock's — in both reads.
    final = _period(app, world.maya, AUGUST_2026)
    assert final["current_lock"] == permanent
    assert final["dataset_lock"] == lock
    again, rows = report_run(
        world,
        CODE,
        {
            "entity_codes": [AVM_US],
            "book": BOOK,
            "period_key": AUGUST_2026,
            "period_lock_id": final["dataset_lock"]["id"],
        },
    )
    assert again["period_lock_id"] == lock["id"]
    assert rows == frozen_rows and again["control_totals"] == frozen_run["control_totals"]

    # THE CONTROL — the application before the item, the refusal switched off: the run is
    # created, queued and ends FAILED on the missing dataset, as measured. Its rerun is refused
    # as its creation is, and creates no run.
    with monkeypatch.context() as earlier:
        earlier.setattr(locked, "froze_nothing", lambda session, scope: None)
        failed = _settled(world, _as_locked(app, world.maya, AUGUST_2026, permanent["id"]))
    assert (failed["status"], failed["period_lock_id"]) == ("FAILED", permanent["id"])
    assert failed["problem"]["detail"] == MISSING_DATASET.format(lock=permanent["id"])
    stored = _runs(world.tenant_id)
    _refused(post(app, f"{REPORT_RUNS}/{failed['id']}/rerun", world.maya, {}), sentence)
    assert _runs(world.tenant_id) == stored


# --- the member through a period's life -----------------------------------------------------------


def _decided(world: CloseWorld, comment: str, approver: Actor) -> None:
    """September's lock requested by the domain command and decided by ``approver``."""
    with world.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=world.state_id,
            body=PeriodLockRequestIn(certification_comment=comment),
            check_version=lambda actual: None,
        )
        uow.commit()
    decided = approve(world.app, str(out.approval_request_id), approver)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def _commanded(world: CloseWorld, actor: Actor, command: str, body: Mapping[str, Any]) -> Any:
    shown = _period(world.app, world.maya, SEPTEMBER)
    answered = post(
        world.app,
        f"{PERIODS}/{shown['id']}/{command}",
        actor,
        dict(body),
        if_match=f'"r{shown["row_version"]}"',
    )
    assert answered.status_code == 200, answered.text
    return answered


def test_the_dataset_lock_through_a_lock_a_reopen_a_second_lock_and_the_permanent_lock(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """September of the close world through every state a period takes, each decision the real
    one. ``dataset_lock`` is null for a period never locked and in its soft close; the ``LOCK``
    while it is closed; null from the reopen until the next lock — the period is not locked, and
    its current record is a ``REOPEN``; the SECOND lock once it is closed again; and that second
    lock still, with its own instant, once the period is permanently locked.

    The refusal follows the same rule: a reopen record names no lock while none stands and the
    second lock afterwards; the permanent lock names the second lock; and a ``LOCK`` record of
    the period — the first one, reopened since — is still accepted: it holds what it froze."""
    app, maya = world.app, world.maya
    earlier_periods_closed(world)

    # 1. never locked, and in its first soft close
    opened = _period(app, maya, SEPTEMBER)
    assert (opened["state"], opened["current_lock"], opened["dataset_lock"]) == ("open", None, None)
    _commanded(world, maya, "start-close", {"comment": "September close in progress"})
    closing = _period(app, maya, SEPTEMBER)
    assert (closing["state"], closing["current_lock"], closing["dataset_lock"]) == (
        "closing",
        None,
        None,
    )

    # 2. closed: the lock is both records
    acknowledged_run(world)
    with system_session(world) as session:
        reviewed_reconciliations(session, world)
        close_run_succeeded(session, world)
    marcus = actor_with_role(app, clock, world.tenant_id, "controller", name="marcus")
    _decided(world, "September 2026 close complete", marcus)
    closed = _period(app, maya, SEPTEMBER)
    first = closed["current_lock"]
    assert (closed["state"], first["kind"]) == ("closed", LockKind.LOCK.value)
    assert closed["dataset_lock"] == first

    # 3. reopened (Priya requests, Marcus and Elena approve): no lock's datasets stand
    priya = actor_with_role(app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    elena = actor_with_role(app, clock, world.tenant_id, "controller", name="elena")
    asked = _commanded(
        world,
        priya,
        "request-reopen",
        {
            "judgement_record_id": str(reviewed_error_judgement(world)),
            "reason_code": "ERROR_CORRECTION",
            "comment": REASON,
        },
    )
    request_id = str(asked.json()["approval_request_id"])
    assert approve(app, request_id, marcus).status_code == 200
    assert approve(app, request_id, elena).status_code == 200
    reopened = _period(app, maya, SEPTEMBER)
    reopen = reopened["current_lock"]
    assert (reopened["state"], reopen["kind"]) == ("reopened", LockKind.REOPEN.value)
    assert reopened["dataset_lock"] is None
    _refused(
        _as_locked(app, maya, SEPTEMBER, reopen["id"]),
        _sentence(LockKind.REOPEN, reopen["id"], SEPTEMBER, None),
    )
    # the lock that was reopened is a LOCK record and holds what it froze: accepted
    assert _as_locked(app, maya, SEPTEMBER, first["id"]).status_code == 202

    # ... and through the soft close that follows the reopen
    _commanded(world, maya, "start-close", {"comment": "September close restarted"})
    again = _period(app, maya, SEPTEMBER)
    assert (again["state"], again["current_lock"], again["dataset_lock"]) == (
        "closing",
        reopen,
        None,
    )

    # 4. closed again: the second lock, not the first
    with system_session(world) as session:
        reviewed_reconciliations(session, world)
    _decided(world, "September 2026 re-lock complete", marcus)
    relocked = _period(app, maya, SEPTEMBER)
    second = relocked["current_lock"]
    assert (relocked["state"], second["kind"]) == ("closed", LockKind.LOCK.value)
    assert second["id"] not in (first["id"], reopen["id"])
    assert relocked["dataset_lock"] == second
    _refused(
        _as_locked(app, maya, SEPTEMBER, reopen["id"]),
        _sentence(LockKind.REOPEN, reopen["id"], SEPTEMBER, second["id"]),
    )

    # 5. permanently locked (Marcus requests, Elena decides): the second lock still
    earlier_periods_closed(world, permanently=True)
    final_request = _commanded(
        world, marcus, "request-permanent-lock", {"comment": "September 2026 is final"}
    )
    decided = approve(app, str(final_request.json()["approval_request_id"]), elena)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    final = _period(app, maya, SEPTEMBER)
    permanent = final["current_lock"]
    assert (final["state"], permanent["kind"]) == (
        "permanently_locked",
        LockKind.PERMANENT_LOCK.value,
    )
    assert final["dataset_lock"] == second
    assert _locks(app, maya, final["id"]) == [
        (LockKind.PERMANENT_LOCK.value, 0, second["id"]),
        (LockKind.LOCK.value, 12, reopen["id"]),
        (LockKind.REOPEN.value, 0, first["id"]),
        (LockKind.LOCK.value, 12, None),
    ]
    _refused(
        _as_locked(app, maya, SEPTEMBER, permanent["id"]),
        _sentence(LockKind.PERMANENT_LOCK, permanent["id"], SEPTEMBER, second["id"]),
    )
    _refused(
        _as_locked(app, maya, SEPTEMBER, reopen["id"]),
        _sentence(LockKind.REOPEN, reopen["id"], SEPTEMBER, second["id"]),
    )
    assert _as_locked(app, maya, SEPTEMBER, second["id"]).status_code == 202


# --- over rows: fail closed -----------------------------------------------------------------------


def _record(
    session: Session,
    world: CloseWorld,
    state: Mapping[str, Any],
    *,
    kind: LockKind,
    previous: UUID | None = None,
) -> UUID:
    """One T-CLS-04 row of ``state``'s period written as its current record, with the transition
    it names — rows as the test makes them, not as a decision leaves them: the state literal
    stays what it was."""
    transition_id = new_id()
    period_id = UUID(str(state["period"]["id"]))
    parts = CloseParts(
        calendar_id=UUID(int=0),
        entity_id=world.entity_id,
        period_id=period_id,
        period_state_transition_id=transition_id,
        approval_request_id=insert_approval_request(
            session, tenant_id=world.tenant_id, entity_id=world.entity_id
        ),
        file_id=UUID(int=0),
    )
    lock = period_lock_values(
        world.tenant_id, parts=parts, kind=kind.value, previous_lock_id=previous
    )
    session.execute(insert(period_lock).values(**lock))
    pair = ("closing", "closed") if kind is LockKind.LOCK else ("closed", "permanently_locked")
    session.execute(
        insert(period_state_transition).values(
            **period_state_transition_values(
                world.tenant_id,
                period_state_id=UUID(str(state["id"])),
                entity_id=world.entity_id,
                period_id=period_id,
                from_state=pair[0],
                to_state=pair[1],
                id=transition_id,
                approval_request_id=parts.approval_request_id,
                period_lock_id=lock["id"],
            )
        )
    )
    session.execute(
        update(period_state)
        .where(period_state.c.id == UUID(str(state["id"])))
        .values(current_lock_id=lock["id"], updated_by_kind=PrincipalKind.SYSTEM.value)
    )
    return UUID(str(lock["id"]))


def test_a_permanent_lock_that_follows_no_lock_of_its_period_names_no_dataset_lock(
    world: CloseWorld,
) -> None:
    """Fail closed, over rows no writer of the product leaves. A ``PERMANENT_LOCK`` record that
    names no record, one that names a ``REOPEN`` record, and one that names a ``LOCK`` of ANOTHER
    period each stand for a period without a dataset lock — and the refusal of each says that
    no lock's datasets stand, naming none. The control beside them: a ``LOCK`` written the same
    way is its period's dataset lock."""
    app, maya = world.app, world.maya
    states = {item["period"]["period_key"]: item for item in periods(app, maya, entity=AVM_US)}
    january, february, march, april = (states[f"FY2026-P0{number}"] for number in (1, 2, 3, 4))
    with system_session(world) as session:
        elsewhere = _record(session, world, april, kind=LockKind.LOCK)
        unnamed = _record(session, world, january, kind=LockKind.PERMANENT_LOCK)
        reopen = insert_reopen_record(
            session,
            world.tenant_id,
            entity_id=world.entity_id,
            period_id=UUID(str(february["period"]["id"])),
        )
        after_reopen = _record(
            session, world, february, kind=LockKind.PERMANENT_LOCK, previous=reopen
        )
        of_another = _record(
            session, world, march, kind=LockKind.PERMANENT_LOCK, previous=elsewhere
        )
    for key, record in (
        ("FY2026-P01", unnamed),
        ("FY2026-P02", after_reopen),
        ("FY2026-P03", of_another),
    ):
        shown = _period(app, maya, key)
        assert (shown["current_lock"]["id"], shown["current_lock"]["kind"]) == (
            str(record),
            LockKind.PERMANENT_LOCK.value,
        ), key
        assert shown["dataset_lock"] is None, key
        _refused(
            _as_locked(app, maya, key, record),
            _sentence(LockKind.PERMANENT_LOCK, record, key, None),
        )
    control = _period(app, maya, "FY2026-P04")
    assert control["current_lock"]["id"] == str(elsewhere)
    assert control["dataset_lock"] == control["current_lock"]
