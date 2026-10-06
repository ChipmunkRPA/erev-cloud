"""CLO-LOCK-OPEN-REDIRTY-1: the period a lock decision opens is re-marked by a deferred job, and
cannot be locked before that job has succeeded (supervisor rulings R-101 (a) and R-106 (a) of
2026-09-30; 04 E-14 and §14.1 DB-07 note rev 1.164; 05 SCH-06 and §5.6 rev 1.79; PRD BR-CLS-03 rev
1.69; SCREENS_B §1.1 rev 1.38; REQ-CLS-004). PostgreSQL-bound.

The lock decision opens the next period when it is ``future`` (BR-CLS-03). 05 SCH-06 re-marks
dirty the clean combination groups with an effect in an opened period; until this slice the
opening inside the lock decision did not: the group stayed clean, the selection of dirty groups
found nothing and the opened period's scheduled revenue was not posted (the lane's witness of
R-94 (b), red on main: ``1 failed, 1 passed``). The decision cannot re-mark in its own transaction
— it holds the closing period's state row and the re-marking takes ``combination_group`` rows (04
DB-07) — so it defers a ``PERIOD_OPEN_REDIRTY`` job for the opened period state.

World: WLD-K-01 through the product's commands on the frozen clock, FY2026-P01 to P09 open, October
``future``. O1 is recognised rateably over 2026, so Pellworth's group holds schedule lines in
October: 118,800.00 allocated × 304 ÷ 365 less × 273 ÷ 365, each cumulatively rounded —
98,945.75 − 88,855.89 = 10,089.86. The world's computation evaluates the periods up to the last
open one (05 RCP-03), so nothing of October is posted while it is ``future``. "The next recompute"
is what the close run's RECOMPUTE_DIRTY step selects (05 RCP-19): the groups whose ``dirty_since``
is set.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    audit_event,
    combination_group,
    job,
    subledger_line,
    tenant,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.platform import setup
from erev_api.domain.reference import period_auto_open, period_redirty_job
from erev_api.enums import ApprovalRequestStatus, JobKind, JobState, PeriodState
from erev_api.files.store import LocalFileStore
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.schemas.periods import PeriodLockRequestIn
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text
from support.close_world import (
    JOURNAL_RUN_ID_HEADER,
    JOURNAL_RUNS,
    acknowledge_run,
    close_run_succeeded_for,
    periods_closed_before,
    reviewed_reconciliations_for,
)
from support.db import TestDatabase
from support.factories import computed
from support.principals import colleague, enrolled
from support.reference import PERIODS, approve, assign, get, periods, post, slug
from support.rows import approval_request_values
from support.worlds import AVM_US, K01, SEPTEMBER_2026, ReportWorld, k01_pellworth, run_now

BOOK: Final = "ASC606"
OCTOBER_2026: Final = "FY2026-P10"
NOVEMBER_2026: Final = "FY2026-P11"
# O1 of WLD-K-01 in October: 98,945.75 − 88,855.89 (PRD WLD-X-01 / WLD-X-02 rounding).
OCTOBER_REVENUE: Final = Decimal("10089.86")
NOT_RE_MARKED: Final = "Contracts not re-marked since the period was opened"  # SCREENS_B §1.1
ONE_DIRTY: Final = "Contracts changed since the last close run: 1"
GATE: Final = "NO_DIRTY_GROUPS"
_TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _session(world: ReportWorld) -> Any:
    return tenant_session(DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*"))


def _state(world: ReportWorld, key: str) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity=AVM_US)
        if item["period"]["period_key"] == key
    ]
    return dict(found)


def _state_id(world: ReportWorld, key: str) -> UUID:
    return UUID(str(_state(world, key)["id"]))


def _group_id(world: ReportWorld) -> UUID:
    return UUID(str(world.contracts[K01].combination_group["id"]))


def _dirty_since(world: ReportWorld) -> datetime | None:
    with _session(world) as session:
        value = session.execute(
            select(combination_group.c.dirty_since).where(
                combination_group.c.id == _group_id(world)
            )
        ).scalar_one()
    return None if value is None else value.astimezone(UTC)


def _dirty_groups(world: ReportWorld) -> list[UUID]:
    """What RECOMPUTE_DIRTY selects (05 RCP-19): the groups whose ``dirty_since`` is set."""
    with _session(world) as session:
        return [
            UUID(str(found))
            for found in session.execute(
                select(combination_group.c.id).where(combination_group.c.dirty_since.is_not(None))
            ).scalars()
        ]


def _recompute_the_dirty_groups(world: ReportWorld) -> list[UUID]:
    """The next recompute: each dirty group is computed once, as RECOMPUTE_DIRTY would."""
    dirty = _dirty_groups(world)
    for group_id in dirty:
        computed(world.place, group_id)
    return dirty


def _revenue(world: ReportWorld, period_key: str) -> list[Decimal]:
    """The REVENUE subledger lines of the period, as amounts (a credit is negative)."""
    period_id = UUID(str(_state(world, period_key)["period"]["id"]))
    with _session(world) as session:
        return [
            Decimal(amount)
            for amount in session.execute(
                select(subledger_line.c.amount_txn)
                .where(
                    subledger_line.c.period_id == period_id,
                    subledger_line.c.account_role == "REVENUE",
                )
                .order_by(subledger_line.c.amount_txn)
            ).scalars()
        ]


def _jobs(world: ReportWorld, state_id: UUID) -> list[Mapping[str, Any]]:
    """The ``PERIOD_OPEN_REDIRTY`` jobs of the period state, oldest first."""
    with _session(world) as session:
        return [
            dict(row)
            for row in session.execute(
                select(job)
                .where(
                    job.c.kind == JobKind.PERIOD_OPEN_REDIRTY.value,
                    job.c.params[period_redirty_job.STATE_PARAM].astext == str(state_id),
                )
                .order_by(job.c.created_at, job.c.id)
            ).mappings()
        ]


def _subjects(rows: list[Mapping[str, Any]]) -> list[tuple[Any, Any]]:
    return [(row["subject_type"], row["subject_id"]) for row in rows]


def _job_events(world: ReportWorld, job_id: UUID) -> list[tuple[str, str, str, Any]]:
    """``(action, actor kind, request id, after)`` of the job's audit events, in chain order."""
    with _session(world) as session:
        rows = session.execute(
            select(
                audit_event.c.action,
                audit_event.c.actor_kind,
                audit_event.c.request_id,
                audit_event.c.after,
            )
            .where(audit_event.c.object_type == "job", audit_event.c.object_id == job_id)
            .order_by(audit_event.c.chain_seq)
        ).all()
    return [
        (str(action), str(getattr(kind, "value", kind)), str(request), after)
        for action, kind, request, after in rows
    ]


def _states(rows: list[Mapping[str, Any]]) -> list[str]:
    return [str(getattr(row["state"], "value", row["state"])) for row in rows]


def _setup_completed(world: ReportWorld) -> None:
    """Tenant setup complete: the scheduler's period tick visits such tenants only (SCH-05)."""
    with world.place.uow() as uow:
        setup.evaluate_setup_completion(uow)
        uow.commit()
    with _session(world) as session:
        completed = session.execute(
            select(tenant.c.setup_completed_at).where(tenant.c.id == world.tenant_id)
        ).scalar_one()
    assert completed is not None


def _lock_september(world: ReportWorld, clock: FrozenClock) -> UUID:
    """September through the public path — soft close, the product's journal run acknowledged, the
    two reconciliations reviewed, the request and another Controller's decision — while October is
    ``future``: the decision opens October (BR-CLS-03). Returns October's period state id."""
    app, maya = world.app, world.maya
    assert _state(world, OCTOBER_2026)["state"] == PeriodState.FUTURE.value
    # PRD BR-CLS-08 (supervisor ruling R-6): January to August are closed before September is
    # brought to its lock — fixture state; their sealed lines stay as they are.
    periods_closed_before(world.place, app, maya, entity_id=world.entity_id, before=SEPTEMBER_2026)
    september = _state(world, SEPTEMBER_2026)
    started = post(
        app,
        f"{PERIODS}/{september['id']}/start-close",
        maya,
        {"comment": "September close"},
        if_match=f'"r{september["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    period_id = UUID(str(september["period"]["id"]))
    requested = post(app, JOURNAL_RUNS, maya, {"entity_code": AVM_US, "period_key": SEPTEMBER_2026})
    assert requested.status_code == 202, requested.text
    assert run_now(world, UUID(str(requested.json()["id"])))["state"] == "SUCCEEDED"
    with _session(world) as session:
        acknowledge_run(
            session, UUID(str(requested.headers[JOURNAL_RUN_ID_HEADER])), now=clock.now()
        )
        reviewed_reconciliations_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=world.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
        # fixture state for the gate CLOSE_RUN_COMPLETED (supervisor ruling R-114 (b))
        close_run_succeeded_for(
            session,
            tenant_id=world.tenant_id,
            entity_id=world.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
    with world.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=UUID(str(september["id"])),
            body=PeriodLockRequestIn(certification_comment="September 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    someone = colleague(world.tenant_id, "cora")
    assign(someone, "controller")
    decided = approve(app, str(out.approval_request_id), enrolled(app, clock, someone))
    assert decided.status_code == 200, decided.text
    assert _state(world, SEPTEMBER_2026)["state"] == PeriodState.CLOSED.value
    october = _state(world, OCTOBER_2026)
    assert october["state"] == PeriodState.OPEN.value
    return UUID(str(october["id"]))


def _cockpit(world: ReportWorld, state_id: UUID) -> dict[str, Any]:
    shown = get(world.app, f"{PERIODS}/{state_id}/cockpit", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _item(world: ReportWorld, state_id: UUID) -> dict[str, Any]:
    """The period's ``NO_DIRTY_GROUPS`` checklist item, as the cockpit shows it."""
    (item,) = [
        item for item in _cockpit(world, state_id)["checklist"] if item["gate_check_code"] == GATE
    ]
    return dict(item)


def _gate(world: ReportWorld, state_id: UUID) -> tuple[str, int | None, str | None]:
    """(status, count, detail) of the period's ``NO_DIRTY_GROUPS`` item, as the cockpit shows it."""
    item = _item(world, state_id)
    result = item["result"] or {}
    return str(item["status"]), result.get("count"), result.get("detail")


def _lock_refusals(world: ReportWorld, state_id: UUID) -> dict[str, str]:
    """``POST /periods/{id}/request-lock`` of a period in soft close, refused 409
    ``close-gates-failed``: rule id → message of every entry."""
    shown = _state_by_id(world, state_id)
    requested = post(
        world.app,
        f"{PERIODS}/{state_id}/request-lock",
        world.maya,
        {"certification_comment": f"{shown['period']['name']} close complete"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert (requested.status_code, slug(requested)) == (409, "close-gates-failed"), requested.text
    return {error["rule_id"]: error["message"] for error in requested.json()["errors"]}


def _state_by_id(world: ReportWorld, state_id: UUID) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity=AVM_US)
        if UUID(str(item["id"])) == state_id
    ]
    return dict(found)


def _soft_close(world: ReportWorld, state_id: UUID) -> None:
    shown = _state_by_id(world, state_id)
    started = post(
        world.app,
        f"{PERIODS}/{state_id}/start-close",
        world.maya,
        {"comment": f"{shown['period']['name']} close"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text


def _failed_jobs(world: ReportWorld, period_key: str) -> int:
    """SCREENS_B BLK-08: API-S-Period ``blockers.jobs_failed`` of the period, from ``GET
    /periods/{id}`` — a row of the list answers the counts null (04 §16.8 rev 1.199)."""
    shown = get(world.app, f"{PERIODS}/{_state_id(world, period_key)}", world.maya)
    assert shown.status_code == 200, shown.text
    return int(shown.json()["blockers"]["jobs_failed"])


def _run_attempt(world: ReportWorld, job_id: UUID, *, attempt: int) -> str:
    """The worker fetches the job's task and runs attempt ``attempt``; returns the job's state."""
    with _session(world) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=attempt, runtime=world.runtime)
    with _session(world) as session:
        state = session.execute(select(job.c.state).where(job.c.id == job_id)).scalar_one()
    return str(getattr(state, "value", state))


def test_r101_a_the_lock_that_opens_the_next_period_defers_its_re_marking(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-101 (a). September is locked through the public path while October is ``future``. The
    decision opens October and defers ONE ``PERIOD_OPEN_REDIRTY`` job for October's period state,
    in its own transaction: queue ``close``, ``QUEUED``. Until the job has run Pellworth's group
    is clean — the window. The job, run as the worker runs it, marks the group; a second marking
    marks nothing more; and the next recompute posts October's scheduled revenue, 10,089.86.

    Fail-first (main, where the decision's opening wrote the transition only): the group stays
    clean after the decision, the dirty selection is empty and October holds no revenue."""
    assert (_dirty_since(world), _revenue(world, OCTOBER_2026)) == (None, [])
    october_id = _lock_september(world, clock)
    jobs = _jobs(world, october_id)
    assert _states(jobs) == [JobState.QUEUED.value], jobs
    (deferred,) = jobs
    assert deferred["queue"] == "close"
    assert (_dirty_since(world), _dirty_groups(world)) == (None, [])  # the window
    finished = run_now(world, UUID(str(deferred["id"])))
    assert finished["state"] == JobState.SUCCEEDED.value, finished
    assert finished["result"]["counts"] == {"redirtied": 1}, finished
    marked_at = _dirty_since(world)
    assert marked_at is not None and _dirty_groups(world) == [_group_id(world)]
    with world.place.uow() as uow:  # the handler's marking again: only clean groups are stamped
        assert period_redirty_job.remark(uow, state_id=october_id) == 0
        uow.commit()
    assert _dirty_since(world) == marked_at
    assert _revenue(world, OCTOBER_2026) == []
    assert _recompute_the_dirty_groups(world) == [_group_id(world)]
    assert _revenue(world, OCTOBER_2026) == [-OCTOBER_REVENUE]
    assert _states(_jobs(world, october_id)) == [JobState.SUCCEEDED.value]


def test_r106_a_the_opened_period_is_not_locked_before_its_re_marking_has_succeeded(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-106 (a) (1), (3). While October's re-marking job is ``QUEUED`` the gate ``NO_DIRTY_GROUPS``
    of October FAILS by name — count unknown, "Contracts not re-marked since the period was
    opened" — in the cockpit and at the lock request, which is refused 409 ``close-gates-failed``
    with that entry; the gate cannot be waived for that reason (409 by name). The period's "Failed
    jobs" blocker stays 0: a waiting job is not a failed one, the gate names it. Once the job has
    succeeded the gate counts the dirty group as any other, and passes after the recompute.

    Fail-first (R-101 (a) as first ruled, a blocker that feeds no gate): the gate PASSED with the
    job waiting, and nothing held the lock of the opened period."""
    october_id = _lock_september(world, clock)
    (deferred,) = _jobs(world, october_id)
    assert _gate(world, october_id) == ("FAILED", None, NOT_RE_MARKED)
    assert _failed_jobs(world, OCTOBER_2026) == 0  # queued: the gate fails, the blocker does not
    # the lock request of the opened period is refused by the gate, by name
    _soft_close(world, october_id)
    refusals = _lock_refusals(world, october_id)
    assert refusals[GATE] == NOT_RE_MARKED, refusals
    # never waivable for this reason: the item says so and the command refuses by name
    cockpit = _cockpit(world, october_id)
    (item,) = [found for found in cockpit["checklist"] if found["gate_check_code"] == GATE]
    assert item["is_waivable"] is False
    waived = post(
        world.app,
        f"{PERIODS}/{october_id}/checklist/{item['id']}/waive",
        world.maya,
        {"reason": "The October contracts are known to be unchanged."},
        if_match=f'"r{cockpit["period"]["row_version"]}"',
    )
    assert (waived.status_code, slug(waived)) == (409, "invalid-transition"), waived.text
    assert waived.json()["detail"] == NOT_RE_MARKED
    # the job succeeds: the gate is the count of dirty groups again, and the blocker is gone
    assert run_now(world, UUID(str(deferred["id"])))["state"] == JobState.SUCCEEDED.value
    assert _gate(world, october_id) == ("FAILED", 1, ONE_DIRTY)
    assert _item(world, october_id)["is_waivable"] is True  # a dirty group is waivable (R-55 (c))
    assert _failed_jobs(world, OCTOBER_2026) == 0
    assert _recompute_the_dirty_groups(world) == [_group_id(world)]
    assert _gate(world, october_id) == ("PASSED", 0, None)


def test_r112_j_a_waived_item_does_not_clear_the_gate_before_the_re_marking_has_succeeded(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-106 (a) (1), R-112 (j): the waiver overlay of R-55 (b) does not clear ``NO_DIRTY_GROUPS``
    while it fails because the period's re-marking has not succeeded. The product refuses such a
    waiver request, so the item is waived here through the decision's own writer
    (``_checklist_waived`` with an APPROVED ``EXCEPTION_WAIVER`` request): the lock request of
    October is still refused by that gate, by name. Once the job has succeeded the same waived
    item clears the gate, as any waiver does.

    Fail-first (the overlay as lane SECFIX-CLO's integration left it): the waived item cleared the
    gate while the job was still queued."""
    october_id = _lock_september(world, clock)
    (deferred,) = _jobs(world, october_id)
    _soft_close(world, october_id)
    item_id = UUID(str(_item(world, october_id)["id"]))
    with world.place.uow() as uow:
        request = approval_request_values(
            world.tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            entity_id=world.entity_id,
            subject_type="EXCEPTION_WAIVER",
            subject_id=item_id,
            summary="Fixture waiver of All contracts computed",
        )
        uow.session.execute(insert(approval_request).values(**request))
        close_commands._checklist_waived(uow, item_id, UUID(str(request["id"])))
        uow.commit()
    assert _item(world, october_id)["status"] == "WAIVED"
    assert _lock_refusals(world, october_id).get(GATE) == NOT_RE_MARKED
    assert run_now(world, UUID(str(deferred["id"])))["state"] == JobState.SUCCEEDED.value
    # the waiver clears the gate once it is a count of dirty groups again
    assert GATE not in _lock_refusals(world, october_id)


def test_r106_a_a_failed_re_marking_is_deferred_again_by_the_period_tick(
    world: ReportWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-106 (a) (2), (3), (4c), (4d). October's job fails its last attempt and ends ``FAILED``:
    the gate stays failed by name and the "Failed jobs" blocker of October counts it — of October
    alone. The scheduler's period tick defers the re-marking again — one job, and the blocker is
    clear again while the gate still fails; a second tick beside that ``QUEUED`` job defers
    nothing. The new job succeeds: the group is marked, the recompute posts October's revenue, the
    gate passes, and a further tick defers nothing."""
    _setup_completed(world)
    october_id = _lock_september(world, clock)
    (first,) = _jobs(world, october_id)

    def refuse(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("the re-marking could not take its rows")

    with monkeypatch.context() as patched:
        patched.setattr(period_redirty_job, "remark", refuse)
        ended = _run_attempt(
            world, UUID(str(first["id"])), attempt=period_redirty_job.RETRY.max_attempts
        )
    assert ended == JobState.FAILED.value
    assert _gate(world, october_id) == ("FAILED", None, NOT_RE_MARKED)
    assert (_failed_jobs(world, OCTOBER_2026), _dirty_since(world)) == (1, None)
    assert _failed_jobs(world, SEPTEMBER_2026) == 0  # the job is the opened period's
    with _session(world) as session:
        assert period_redirty_job.failed_states(session) == [(october_id, 1)]
    ticked = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
    assert (ticked.redeferred, ticked.opened, ticked.failed) == (1, 0, 0), ticked
    assert _states(_jobs(world, october_id)) == [JobState.FAILED.value, JobState.QUEUED.value]
    # the job the tick defers works on the same period state (04 T-PLT-27 rev 1.164)
    assert _subjects(_jobs(world, october_id)) == [("period_state", october_id)] * 2
    again = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
    assert again.redeferred == 0, again  # one live job per period state
    assert _states(_jobs(world, october_id)) == [JobState.FAILED.value, JobState.QUEUED.value]
    # the newest job waits: the failed one is history for the blocker, the gate still fails
    assert _failed_jobs(world, OCTOBER_2026) == 0
    assert _gate(world, october_id) == ("FAILED", None, NOT_RE_MARKED)
    second = _jobs(world, october_id)[1]
    assert run_now(world, UUID(str(second["id"])))["state"] == JobState.SUCCEEDED.value
    assert _failed_jobs(world, OCTOBER_2026) == 0
    assert _gate(world, october_id) == ("FAILED", 1, ONE_DIRTY)
    assert _recompute_the_dirty_groups(world) == [_group_id(world)]
    assert _revenue(world, OCTOBER_2026) == [-OCTOBER_REVENUE]
    assert _gate(world, october_id) == ("PASSED", 0, None)
    after = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
    assert after.redeferred == 0, after
    assert len(_jobs(world, october_id)) == 2


def test_sch_05_a_re_deferral_that_meets_a_lock_conflict_is_left_for_the_next_tick(
    world: ReportWorld,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """05 SCH-05 rev 1.83 (lane OPS; supervisor ruling R-97 (6)): the tick isolates the
    re-deferral of a failed re-marking as it isolates an opening. Another transaction holds the
    deferral's advisory lock of October past ``lock_timeout`` - the lock decision that opens a
    period holds it until it ends. The tick defers nothing for October, logs
    ``period_open_redirty.lock_conflict`` with the period state and the SQLSTATE and returns its
    report; the newest job is still the failed one, and the next tick defers it. Fail-first: the
    55P03 left ``run`` and ended the tick for every tenant after this one."""
    _setup_completed(world)
    october_id = _lock_september(world, clock)
    (first,) = _jobs(world, october_id)

    def refuse(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("the re-marking could not take its rows")

    with monkeypatch.context() as patched:
        patched.setattr(period_redirty_job, "remark", refuse)
        ended = _run_attempt(
            world, UUID(str(first["id"])), attempt=period_redirty_job.RETRY.max_attempts
        )
    assert ended == JobState.FAILED.value
    key = period_redirty_job.LOCK_KEY.format(state_id=october_id)
    with _session(world) as holder:
        holder.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
        log_stream.seek(0)
        log_stream.truncate()
        held = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
        holder.rollback()
    assert (held.redeferred, held.opened, held.failed) == (0, 0, 0), held
    assert _states(_jobs(world, october_id)) == [JobState.FAILED.value]
    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    conflicts = [event for event in events if event["event"].startswith("period_open_redirty.")]
    assert [
        (event["event"], event["level"], event["state_id"], event["failed_jobs"], event["sqlstate"])
        for event in conflicts
    ] == [("period_open_redirty.lock_conflict", "warning", str(october_id), 1, "55P03")]
    # The next tick finds the lock free and the newest job still ended: it defers it.
    ticked = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
    assert (ticked.redeferred, ticked.opened, ticked.failed) == (1, 0, 0), ticked
    assert _states(_jobs(world, october_id)) == [JobState.FAILED.value, JobState.QUEUED.value]


def test_sch_05_a_defect_in_one_re_deferral_is_logged_and_the_tick_goes_on(
    world: ReportWorld,
    clock: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
    log_stream: io.StringIO,
) -> None:
    """05 SCH-05 rev 1.106 (lane OPS; supervisor ruling R-118 (k)): an exception of one
    re-deferral that is neither "not now" nor the server's own state is logged at error level
    with its class - ``period_open_redirty.failed`` - and the tick returns its report; the next
    tick, without the defect, defers the job. Fail-first: the exception left ``run``."""
    _setup_completed(world)
    october_id = _lock_september(world, clock)
    (first,) = _jobs(world, october_id)

    def refuse(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("the re-marking could not take its rows")

    with monkeypatch.context() as patched:
        patched.setattr(period_redirty_job, "remark", refuse)
        ended = _run_attempt(
            world, UUID(str(first["id"])), attempt=period_redirty_job.RETRY.max_attempts
        )
    assert ended == JobState.FAILED.value

    def defective(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("a defect that names customer Pellworth")

    log_stream.seek(0)
    log_stream.truncate()
    with monkeypatch.context() as patched:
        patched.setattr(period_redirty_job, "defer_single", defective)
        held = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
    assert (held.redeferred, held.opened, held.failed) == (0, 0, 0), held
    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    failures = [event for event in events if event["event"].startswith("period_open_redirty.")]
    assert [
        (event["event"], event["level"], event["state_id"], event["error_class"])
        for event in failures
    ] == [("period_open_redirty.failed", "error", str(october_id), "RuntimeError")]
    # Rev 1.139: the place the exception was raised - the tick's own call of the stand-in.
    assert failures[0]["error_at"].rpartition(":")[0] == (
        "erev_api.domain.reference.period_auto_open"
    )
    assert "Pellworth" not in log_stream.getvalue()
    assert _states(_jobs(world, october_id)) == [JobState.FAILED.value]
    ticked = period_auto_open.run(world.runtime, only_tenants=[world.tenant_id])
    assert (ticked.redeferred, ticked.opened, ticked.failed) == (1, 0, 0), ticked


def test_the_re_marking_job_names_its_period_state_as_its_subject(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """04 T-PLT-27 rev 1.164 (the supervisor's answer of 2026-09-30 to observation 1 of the item's
    report): the job the lock decision defers works on October's period state and says so —
    ``subject_type`` ``period_state``, ``subject_id`` the state id — on its row and in
    ``job.start``, which the decision's transaction writes as the decider. ``job.finish`` is the
    terminal event of the same job, as SYSTEM under ``job-<id>``; its payload is the kind, the
    state and the problem (T-PLT-27), so the period is read from the job it names.

    Fail-first (the item as first built): the job named its period state in ``params`` alone —
    ``subject_type`` and ``subject_id`` null on the row and in ``job.start`` — and the audit trail
    of the re-marking did not name the period."""
    october_id = _lock_september(world, clock)
    (deferred,) = _jobs(world, october_id)
    job_id = UUID(str(deferred["id"]))
    assert _subjects([deferred]) == [("period_state", october_id)]
    ((action, actor_kind, request_id, after),) = _job_events(world, job_id)
    assert (action, actor_kind) == ("job.start", "USER")
    assert not request_id.startswith("job-")  # the decision's own request
    assert after == {
        "kind": JobKind.PERIOD_OPEN_REDIRTY.value,
        "state": JobState.QUEUED.value,
        "queue": "close",
        "priority": 0,
        "parent_job_id": None,
        "subject_type": "period_state",
        "subject_id": str(october_id),
    }
    assert run_now(world, job_id)["state"] == JobState.SUCCEEDED.value
    events = _job_events(world, job_id)
    assert [(action, kind, request) for action, kind, request, _ in events] == [
        ("job.start", "USER", request_id),
        ("job.finish", "SYSTEM", f"job-{job_id}"),
    ]
    assert events[1][3] == {
        "kind": JobKind.PERIOD_OPEN_REDIRTY.value,
        "state": JobState.SUCCEEDED.value,
        "problem": None,
    }


def test_r106_a_two_deferrals_of_one_period_state_leave_one_live_job(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """R-106 (a) (4d), where the rule can bite — a period state is opened once, so two lock
    decisions never open the same one (04 T-REF-07 has no pair into ``future``): a second deferral
    for a period state whose job is ``QUEUED`` returns nothing and inserts nothing, in another
    transaction and in the same one."""
    october_id = _lock_september(world, clock)
    assert len(_jobs(world, october_id)) == 1
    with world.place.uow() as uow:
        assert period_redirty_job.defer_single(uow, state_id=october_id) is None
        uow.commit()
    assert len(_jobs(world, october_id)) == 1
    november_id = _state_id(world, NOVEMBER_2026)
    with world.place.uow() as uow:
        first = period_redirty_job.defer_single(uow, state_id=november_id)
        assert first is not None and first["kind"] == JobKind.PERIOD_OPEN_REDIRTY.value
        assert period_redirty_job.defer_single(uow, state_id=november_id) is None
        uow.session.rollback()
    assert _jobs(world, november_id) == []


def test_r101_a_control_the_manual_opening_re_marks_in_its_own_transaction(
    world: ReportWorld,
) -> None:
    """The control, on the route 05 SCH-06 names: October opened through
    ``POST /periods/{id}/open`` while September stays open. The group is re-marked in the
    opening's transaction, no job is deferred and no gate waits for one."""
    october = _state(world, OCTOBER_2026)
    opened = post(
        world.app,
        f"{PERIODS}/{october['id']}/open",
        world.maya,
        {"comment": "Open October"},
        if_match=f'"r{october["row_version"]}"',
    )
    assert opened.status_code == 200, opened.text
    october_id = UUID(str(october["id"]))
    assert _dirty_since(world) is not None
    assert _jobs(world, october_id) == []
    assert _gate(world, october_id) == ("FAILED", 1, ONE_DIRTY)
    assert _failed_jobs(world, OCTOBER_2026) == 0
    assert _recompute_the_dirty_groups(world) == [_group_id(world)]
    assert _revenue(world, OCTOBER_2026) == [-OCTOBER_REVENUE]
