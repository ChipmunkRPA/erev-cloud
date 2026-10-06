"""SCH-05 ``period_auto_open`` / SCH-06 ``period_open_redirty`` database witnesses (record §4.29).

NOT RUN on the lane (database-bound; the integrated batch measures them). Every run is scoped to
the test's own tenant through ``only_tenants``, so the worlds of other tests keep their ``future``
periods. Setup completion (BR-PLT-02) is reached the governed way: two people holding
``contract.create`` and ``contract.approve`` and a first period opened through the API. Every
test moves the shared clock weeks past maya's sign-in, beyond SAR-10's 12-hour absolute session
lifetime (``auth/sessions.py``), so she signs in again before reading the API (batch #8 ci).
"""

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_event,
    customer,
    legal_entity,
    period_state,
    period_state_transition,
)
from erev_api.domain.reference import period_auto_open, period_redirty_job
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.problems import from_db_error
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from psycopg import errors as pg
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from support.db import TestDatabase
from support.factories import open_periods, world_calendar
from support.principals import Actor, Member, colleague, member, sign_in, workspace
from support.reference import ENTITIES, calendar, entity, holding, periods, put
from support.rows import (
    combination_group_values,
    contract_event_values,
    contract_values,
    customer_values,
)

COMMENT = period_auto_open.AUTO_OPEN_COMMENT


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _runtime(clock: FrozenClock, keyring: KeyRing, tmp_path: Path) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(tmp_path / "files"))


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _setup_complete_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, *, is_demo: bool = False
) -> tuple[Actor, Member, str, UUID]:
    """Maya (``revenue_accountant``: ``contract.create``, ``period.close``) and Omar
    (``controller``: ``contract.approve``) are the two BR-PLT-02 people; AVM-US (New York) with
    FY2026 P01 to P09 opened through the API completes the tenant's setup at the last opening.
    With ``is_demo`` the tenant carries the demo marker."""
    maya_member = member(keyring, clock, is_demo=is_demo)
    maya = holding(app, maya_member, "revenue_accountant")
    holding(app, colleague(maya_member.tenant_id, "omar"), "controller")
    calendar_id, entity_id = world_calendar(app, maya)
    return maya, maya_member, calendar_id, entity_id


def _signed_in_again(app: FastAPI, someone: Member) -> Actor:
    """The clock has moved past the 12-hour absolute session limit (SAR-10): sign in again."""
    return workspace(app, someone, sign_in(app, someone.email))


def _states(app: FastAPI, actor: Actor, **params: Any) -> dict[str, dict[str, Any]]:
    return {item["period"]["period_key"]: item for item in periods(app, actor, **params)}


def _group_with_event(
    tenant_id: UUID, entity_id: UUID, effective: date, *, dirty_since: datetime | None = None
) -> UUID:
    """A singleton group whose contract (of the entity) has one event on ``effective``."""
    with tenant_session(_context(tenant_id)) as session:
        buyer = customer_values(tenant_id)
        session.execute(insert(customer).values(**buyer))
        group = combination_group_values(tenant_id, dirty_since=dirty_since)
        session.execute(insert(combination_group).values(**group))
        row = contract_values(
            tenant_id,
            customer_id=buyer["id"],
            contracting_entity_id=entity_id,
            combination_group_id=group["id"],
            head_stream_version=1,
        )
        session.execute(insert(contract).values(**row))
        session.execute(
            insert(contract_event).values(
                **contract_event_values(
                    tenant_id,
                    contract_id=row["id"],
                    contracting_entity_id=entity_id,
                    stream_version=1,
                    effective_date=effective,
                )
            )
        )
        session.commit()
    return UUID(str(group["id"]))


def _dirty_since(tenant_id: UUID, group_id: UUID) -> datetime | None:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        value = session.execute(
            select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
        ).scalar_one()
    return None if value is None else value.astimezone(UTC)


def test_due_future_periods_open_as_system_and_redirty_their_groups(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    maya, maya_member, _, entity_id = _setup_complete_world(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    in_october = _group_with_event(tenant_id, entity_id, date(2026, 10, 15))
    in_november = _group_with_event(tenant_id, entity_id, date(2026, 11, 10))
    earlier = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    already_dirty = _group_with_event(tenant_id, entity_id, date(2026, 10, 20), dirty_since=earlier)
    clock.set(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))  # 1 October, 01:00 in New York
    runtime = _runtime(clock, keyring, tmp_path)

    report = period_auto_open.run(runtime, only_tenants=[tenant_id])

    assert report == period_auto_open.AutoOpenReport(
        tenants=1, candidates=1, opened=1, redirtied=1, failed=0
    )
    maya = _signed_in_again(app, maya_member)
    states = _states(app, maya, entity="AVM-US")
    assert (states["FY2026-P10"]["state"], states["FY2026-P11"]["state"]) == ("open", "future")
    with tenant_session(_context(tenant_id), read_only=True) as session:
        history = session.execute(
            select(
                period_state_transition.c.from_state,
                period_state_transition.c.to_state,
                period_state_transition.c.reason_code,
                period_state_transition.c.comment,
                period_state_transition.c.created_by,
                period_state_transition.c.created_by_kind,
            )
            .where(period_state_transition.c.period_state_id == UUID(states["FY2026-P10"]["id"]))
            .order_by(period_state_transition.c.created_at, period_state_transition.c.id)
        ).all()
    # 04 T-REF-07: a state's history begins with its creation row (``from_state`` "NULL on
    # creation"; "Allowed: NULL→future, future→open, …"), written with the state when the entity's
    # book was kept; the run adds exactly one row, the SYSTEM opening.
    creation, transition = history
    assert (creation.from_state, creation.to_state) == (None, "future")
    assert tuple(transition) == ("future", "open", None, COMMENT, None, "SYSTEM")
    # SCH-06 in the same transaction: the October group is dirty from the opening instant, the
    # November group stays clean (its period is still future), the already-dirty group keeps
    # its earlier stamp.
    assert _dirty_since(tenant_id, in_october) == clock.now()
    assert _dirty_since(tenant_id, in_november) is None
    assert _dirty_since(tenant_id, already_dirty) == earlier
    # A second run a minute later finds nothing due: idempotent.
    clock.advance(timedelta(seconds=60))
    assert period_auto_open.run(runtime, only_tenants=[tenant_id]) == (
        period_auto_open.AutoOpenReport(tenants=1, candidates=0, opened=0, redirtied=0, failed=0)
    )


def test_the_entity_local_date_decides_and_a_disabled_book_is_skipped(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """TZ-06: at 2026-10-01T03:00Z New York is still 30 September (AVM-US P10 not due) while
    Auckland is 1 October (every AVM-NZ FY2026 period through P10 is due); a book the entity
    disabled is never opened automatically."""
    maya, maya_member, calendar_id, _ = _setup_complete_world(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    nz = entity(app, maya, code="AVM-NZ", calendar_id=calendar_id, time_zone="Pacific/Auckland")
    enabled = put(app, f"{ENTITIES}/{nz['id']}/books/IFRS15", maya, {"is_enabled": True})
    assert enabled.status_code == 200, enabled.text
    disabled = put(app, f"{ENTITIES}/{nz['id']}/books/IFRS15", maya, {"is_enabled": False})
    assert disabled.status_code == 200, disabled.text
    clock.set(datetime(2026, 10, 1, 3, 0, tzinfo=UTC))

    report = period_auto_open.run(_runtime(clock, keyring, tmp_path), only_tenants=[tenant_id])

    assert (report.tenants, report.opened, report.failed) == (1, 10, 0)
    maya = _signed_in_again(app, maya_member)
    assert _states(app, maya, entity="AVM-US")["FY2026-P10"]["state"] == "future"
    nz_states = _states(app, maya, entity="AVM-NZ")
    assert [nz_states[f"FY2026-P{month:02d}"]["state"] for month in range(1, 13)] == (
        ["open"] * 10 + ["future"] * 2
    )
    ifrs15 = _states(app, maya, entity="AVM-NZ", book="IFRS15")
    assert {item["state"] for item in ifrs15.values()} == {"future"}


def test_a_tenant_whose_setup_is_incomplete_is_left_alone(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """BR-PLT-02: with one person only the setup is incomplete, so the first opening stays a
    setup step of the tenant's own people; nothing opens automatically."""
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    entity(app, maya, code="AVM-US", calendar_id=calendar(app, maya))
    clock.set(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))

    report = period_auto_open.run(
        _runtime(clock, keyring, tmp_path), only_tenants=[maya_member.tenant_id]
    )

    assert report == period_auto_open.AutoOpenReport()
    maya = _signed_in_again(app, maya_member)
    assert {item["state"] for item in _states(app, maya, entity="AVM-US").values()} == {"future"}


def test_a_demo_tenant_keeps_its_month(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> None:
    """05 SCH-05 rev 1.163 (item DEMO-CLOCK-1; PRD WLD-P-02): the clock opens no period of a
    demo tenant. Its due period stays ``future`` and the run counts no candidate for it, though
    the tenant is listed; the same period of a production tenant opens in the same run; and the
    demo tenant's period still opens by hand."""
    _, demo_member, _, _ = _setup_complete_world(app, keyring, clock, is_demo=True)
    _, maya_member, _, _ = _setup_complete_world(app, keyring, clock)
    clock.set(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))  # 1 October, 01:00 in New York
    with tenant_session(_context(demo_member.tenant_id), read_only=True) as session:
        assert period_auto_open.candidates(session, clock=clock) == []

    report = period_auto_open.run(
        _runtime(clock, keyring, tmp_path),
        only_tenants=[demo_member.tenant_id, maya_member.tenant_id],
    )

    assert report == period_auto_open.AutoOpenReport(
        tenants=2, candidates=1, opened=1, redirtied=0, failed=0
    )
    maya = _signed_in_again(app, maya_member)
    assert _states(app, maya, entity="AVM-US")["FY2026-P10"]["state"] == "open"
    demo_maya = _signed_in_again(app, demo_member)
    assert _states(app, demo_maya, entity="AVM-US")["FY2026-P10"]["state"] == "future"
    # API-R-18 ``POST /periods/{id}/open``: by hand the period opens as in any tenant.
    open_periods(app, demo_maya, entity_code="AVM-US", keys=["FY2026-P10"])
    assert _states(app, demo_maya, entity="AVM-US")["FY2026-P10"]["state"] == "open"


def _logged(log_stream: io.StringIO, name: str) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    return [event for event in events if event["event"] == name]


def _two_entities_due(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> tuple[Member, list[period_auto_open.Candidate]]:
    """AVM-NZ (FY2026 P01 to P10 ``future``) beside AVM-US (P10 ``future``) on 1 October in both
    time zones: eleven due periods, AVM-NZ's ten first."""
    maya, maya_member, calendar_id, _ = _setup_complete_world(app, keyring, clock)
    entity(app, maya, code="AVM-NZ", calendar_id=calendar_id, time_zone="Pacific/Auckland")
    clock.set(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))  # 1 October in New York and in Auckland
    with tenant_session(_context(maya_member.tenant_id), read_only=True) as session:
        due_now = period_auto_open.candidates(session, clock=clock)
    assert [(found.entity_code, found.period_key) for found in due_now] == [
        *(("AVM-NZ", f"FY2026-P{month:02d}") for month in range(1, 11)),
        ("AVM-US", "FY2026-P10"),
    ]
    return maya_member, due_now


def test_a_period_held_by_another_transaction_is_left_for_the_next_tick(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, tmp_path: Path, log_stream: io.StringIO
) -> None:
    """SCH-05 rev 1.83 (review finding F7 (e); supervisor ruling R-97 (6)): the tick isolates each
    period. Another transaction holds the state row of the first candidate past ``lock_timeout``:
    that opening is logged as a lock conflict and left for the next tick, and the tick goes on.
    The later periods of the same entity and book are refused by name - a period opens only after
    the one before it (PRD SM-07; ruling R-58 (d)) - and the due period of the entity after them
    opens. The next tick opens the ten in order. Fail-first: the 55P03 left ``run`` and ended the
    tick with nothing after the first candidate attempted."""
    maya_member, due_now = _two_entities_due(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    held = due_now[0]
    runtime = _runtime(clock, keyring, tmp_path)
    with tenant_session(_context(tenant_id)) as holder:
        holder.execute(
            select(period_state.c.id).where(period_state.c.id == held.state_id).with_for_update()
        ).scalar_one()
        report = period_auto_open.run(runtime, only_tenants=[tenant_id])
        holder.rollback()

    assert report == period_auto_open.AutoOpenReport(
        tenants=1, candidates=11, opened=1, redirtied=0, failed=10
    )
    maya = _signed_in_again(app, maya_member)
    nz_states = _states(app, maya, entity="AVM-NZ")
    assert {nz_states[f"FY2026-P{month:02d}"]["state"] for month in range(1, 11)} == {"future"}
    assert _states(app, maya, entity="AVM-US")["FY2026-P10"]["state"] == "open"
    assert [
        (event["level"], event["entity"], event["period_key"], event["sqlstate"])
        for event in _logged(log_stream, "period_auto_open.lock_conflict")
    ] == [("warning", "AVM-NZ", "FY2026-P01", "55P03")]
    assert [
        (event["entity"], event["period_key"], event["slug"])
        for event in _logged(log_stream, "period_auto_open.refused")
    ] == [("AVM-NZ", f"FY2026-P{month:02d}", "invalid-transition") for month in range(2, 11)]
    assert _logged(log_stream, "period_auto_open.statement_timeout") == []
    # The next tick finds the row free and opens the period that was left, and those behind it.
    clock.advance(timedelta(seconds=60))
    assert period_auto_open.run(runtime, only_tenants=[tenant_id]) == (
        period_auto_open.AutoOpenReport(tenants=1, candidates=10, opened=10, redirtied=0, failed=0)
    )
    maya = _signed_in_again(app, maya_member)
    nz_states = _states(app, maya, entity="AVM-NZ")
    assert {nz_states[f"FY2026-P{month:02d}"]["state"] for month in range(1, 11)} == {"open"}


def test_a_period_whose_statement_is_cancelled_is_left_for_the_next_tick(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SCH-05 rev 1.83: a statement of an opening that PostgreSQL cancels (SQLSTATE 57014) leaves
    the period for the next tick like a lock conflict, whether the error reaches the tick as the
    database error or as the ``statement-timeout`` problem a mapper raised from it.

    Another transaction holds the state row of the last due period of each entity. For those two
    openings the unit of work's statement timeout is shortened below the lock timeout, so that
    PostgreSQL cancels the opening's own first statement - the row lock of
    ``open_future_period`` - instead of the wait ending in a 55P03: the server's error in the
    opening's transaction, the limit shortened. AVM-NZ's reaches the tick raw; AVM-US's is raised
    as its problem, the way ``transitions.apply`` and the commit raise theirs.

    Fail-first: the raw error ended the tick (``run`` raised) and the mapped one was logged
    ``period_auto_open.refused`` as if the period had refused the opening."""
    maya_member, due_now = _two_entities_due(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    raw, mapped = due_now[9], due_now[10]
    assert (raw.entity_code, raw.period_key) == ("AVM-NZ", "FY2026-P10")
    runtime = _runtime(clock, keyring, tmp_path)
    opening = period_auto_open.open_future_period

    def cancelled(uow: UnitOfWork, *, state_id: UUID, comment: str | None) -> Any:
        if state_id not in (raw.state_id, mapped.state_id):
            return opening(uow, state_id=state_id, comment=comment)
        uow.session.execute(text("SET LOCAL statement_timeout = 200"))
        if state_id == raw.state_id:
            return opening(uow, state_id=state_id, comment=comment)
        try:
            return opening(uow, state_id=state_id, comment=comment)
        except DBAPIError as error:
            problem = from_db_error(error)
            assert problem is not None and problem.slug == "statement-timeout"
            raise problem from error

    with tenant_session(_context(tenant_id)) as holder, monkeypatch.context() as shortened:
        shortened.setattr(period_auto_open, "open_future_period", cancelled)
        holder.execute(
            select(period_state.c.id)
            .where(period_state.c.id.in_([raw.state_id, mapped.state_id]))
            .with_for_update()
        ).all()
        report = period_auto_open.run(runtime, only_tenants=[tenant_id])
        holder.rollback()

    assert report == period_auto_open.AutoOpenReport(
        tenants=1, candidates=11, opened=9, redirtied=0, failed=2
    )
    assert [
        (event["level"], event["entity"], event["period_key"], event["sqlstate"])
        for event in _logged(log_stream, "period_auto_open.statement_timeout")
    ] == [
        ("warning", "AVM-NZ", "FY2026-P10", "57014"),
        ("warning", "AVM-US", "FY2026-P10", "57014"),
    ]
    assert _logged(log_stream, "period_auto_open.refused") == []
    assert _logged(log_stream, "period_auto_open.lock_conflict") == []
    maya = _signed_in_again(app, maya_member)
    nz_states = _states(app, maya, entity="AVM-NZ")
    assert [nz_states[f"FY2026-P{month:02d}"]["state"] for month in range(1, 11)] == (
        ["open"] * 9 + ["future"]
    )
    assert _states(app, maya, entity="AVM-US")["FY2026-P10"]["state"] == "future"
    # The next tick, with the rows free and the platform's own limit, opens the two that were left.
    clock.advance(timedelta(seconds=60))
    assert period_auto_open.run(runtime, only_tenants=[tenant_id]) == (
        period_auto_open.AutoOpenReport(tenants=1, candidates=2, opened=2, redirtied=0, failed=0)
    )


def test_a_defect_in_one_opening_is_logged_and_the_tick_goes_on(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SCH-05 rev 1.106 (supervisor ruling R-118 (k); as R-50 (a) for the scheduler fan-out
    and the sweeper): an exception of one opening that is neither of the two "not now" answers
    nor the server's own state - a defect - is logged at error level with its class, never its
    message, the period is counted as failed, and the tick opens the periods after it.
    Fail-first: the exception left ``run`` and ended the tick for every period and tenant after
    this one, at every run."""
    maya_member, due_now = _two_entities_due(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    broken = due_now[9]  # AVM-NZ FY2026-P10: no later period of its book waits behind it
    runtime = _runtime(clock, keyring, tmp_path)
    opening = period_auto_open.open_future_period

    def defective(uow: UnitOfWork, *, state_id: UUID, comment: str | None) -> Any:
        if state_id == broken.state_id:
            raise RuntimeError("a defect that names customer Pellworth")
        return opening(uow, state_id=state_id, comment=comment)

    with monkeypatch.context() as patched:
        patched.setattr(period_auto_open, "open_future_period", defective)
        report = period_auto_open.run(runtime, only_tenants=[tenant_id])
    assert report == period_auto_open.AutoOpenReport(
        tenants=1, candidates=11, opened=10, redirtied=0, failed=1
    )
    assert [
        (event["level"], event["entity"], event["period_key"], event["error_class"])
        for event in _logged(log_stream, "period_auto_open.failed")
    ] == [("error", "AVM-NZ", "FY2026-P10", "RuntimeError")]
    # Rev 1.139: the event names where the exception was raised - here the tick's own call,
    # because the defect is this test's stand-in - and still nothing of its message.
    (failed,) = _logged(log_stream, "period_auto_open.failed")
    assert failed["error_at"].rpartition(":")[0] == "erev_api.domain.reference.period_auto_open"
    assert "Pellworth" not in log_stream.getvalue()
    maya = _signed_in_again(app, maya_member)
    assert _states(app, maya, entity="AVM-NZ")["FY2026-P10"]["state"] == "future"
    assert _states(app, maya, entity="AVM-US")["FY2026-P10"]["state"] == "open"
    # The next tick, without the defect, opens the period that was left.
    clock.advance(timedelta(seconds=60))
    assert period_auto_open.run(runtime, only_tenants=[tenant_id]) == (
        period_auto_open.AutoOpenReport(tenants=1, candidates=1, opened=1, redirtied=0, failed=0)
    )


def _server_out_of_memory() -> DBAPIError:
    orig = pg.lookup("53200")("out of shared memory")
    wrapped = DBAPIError.instance("SELECT 1 FROM erev.period_state", None, orig, psycopg.Error)
    assert isinstance(wrapped, DBAPIError)
    return wrapped


@pytest.mark.parametrize(
    "state_of_the_server",
    [_server_out_of_memory, lambda: PoolTimeoutError("QueuePool limit of size 10 reached")],
    ids=["53200", "pool-timeout"],
)
def test_the_servers_own_state_still_ends_the_tick(
    state_of_the_server: Any,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SCH-05 rev 1.106: the errors that say the server cannot serve - the slug-less 503 set
    of 04 API-C-05 and the pool timeout - are no period's own; the tick ends on the first and
    the periodic fails, as before the ruling. Nothing after that opening is attempted."""
    maya_member, due_now = _two_entities_due(app, keyring, clock)
    tenant_id = maya_member.tenant_id
    first = due_now[0]
    attempted: list[UUID] = []
    opening = period_auto_open.open_future_period

    def unserved(uow: UnitOfWork, *, state_id: UUID, comment: str | None) -> Any:
        attempted.append(state_id)
        if state_id == first.state_id:
            raise state_of_the_server()
        return opening(uow, state_id=state_id, comment=comment)

    monkeypatch.setattr(period_auto_open, "open_future_period", unserved)
    with pytest.raises((DBAPIError, PoolTimeoutError)):
        period_auto_open.run(_runtime(clock, keyring, tmp_path), only_tenants=[tenant_id])
    assert attempted == [first.state_id]
    assert _logged(log_stream, "period_auto_open.failed") == []
    assert _logged(log_stream, "period_auto_open.completed") == []


def test_a_tenant_whose_due_periods_cannot_be_read_is_skipped_and_the_next_is_served(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    log_stream: io.StringIO,
) -> None:
    """05 SCH-05 rev 1.139 (supervisor ruling of 2026-10-01 on R-118 (k)): the read of a tenant's
    due periods is isolated as an opening is. The read computes each entity's local date from
    ``legal_entity.time_zone``; the column's domain holds the shape of a zone name (04 TY-10) and
    the API holds it to the zone database, so a row written past the API - here by this test - can
    name a zone the worker does not know. That tenant's openings are skipped and logged at error
    level with the tenant, the class and the place; the tenant after it is served, and the report
    counts the skip. Fail-first: the exception left ``run`` and the second tenant's period stayed
    ``future``."""
    worlds = sorted(
        (_setup_complete_world(app, keyring, clock) for _ in range(2)),
        key=lambda world: str(world[1].tenant_id),  # the tick serves tenants in id order
    )
    (_, unread_member, _, unread_entity), (_, served_member, _, _) = worlds
    unread, served = unread_member.tenant_id, served_member.tenant_id
    with tenant_session(_context(unread)) as session:
        session.execute(
            update(legal_entity)
            .where(legal_entity.c.id == unread_entity)
            .values(time_zone="Mars/Olympus_Mons")
        )
        session.commit()
    clock.set(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))  # 1 October in New York

    report = period_auto_open.run(_runtime(clock, keyring, tmp_path), only_tenants=[served, unread])

    assert report == period_auto_open.AutoOpenReport(
        tenants=2, candidates=1, opened=1, redirtied=0, failed=0, tenants_skipped=1
    )
    (event,) = _logged(log_stream, "period_auto_open.read_failed")
    assert (event["level"], event["tenant_id"], event["error_class"], event["sqlstate"]) == (
        "error",
        str(unread),
        "ZoneInfoNotFoundError",
        None,
    )
    assert event["error_at"].rpartition(":")[0] == "erev_api.clock"
    assert "Olympus" not in log_stream.getvalue()
    (completed,) = _logged(log_stream, "period_auto_open.completed")
    assert (completed["tenants"], completed["tenants_skipped"]) == (2, 1)
    served_actor = _signed_in_again(app, served_member)
    assert _states(app, served_actor, entity="AVM-US")["FY2026-P10"]["state"] == "open"
    with tenant_session(_context(unread), read_only=True) as session:
        states = session.execute(
            select(period_state.c.state).where(period_state.c.entity_id == unread_entity)
        ).scalars()
        assert sorted({str(state) for state in states}) == ["future", "open"]


def test_a_tenant_whose_failed_re_marking_jobs_cannot_be_read_keeps_its_openings(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    log_stream: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SCH-05 rev 1.139: the tick's other read per tenant, the failed re-marking jobs
    (SCH-06), is isolated on its own. When it raises, the tenant's re-deferrals are skipped and
    logged; the openings of the same tenant, which stand behind the other read, are made."""
    maya_member, _ = _two_entities_due(app, keyring, clock)
    tenant_id = maya_member.tenant_id

    def unreadable(session: Any) -> Any:
        raise RuntimeError("a defect that names customer Pellworth")

    monkeypatch.setattr(period_redirty_job, "failed_states", unreadable)
    report = period_auto_open.run(_runtime(clock, keyring, tmp_path), only_tenants=[tenant_id])
    assert report == period_auto_open.AutoOpenReport(
        tenants=1, candidates=11, opened=11, redirtied=0, failed=0, tenants_skipped=1
    )
    (event,) = _logged(log_stream, "period_open_redirty.read_failed")
    assert (event["level"], event["tenant_id"], event["error_class"]) == (
        "error",
        str(tenant_id),
        "RuntimeError",
    )
    assert event["error_at"].rpartition(":")[0] == "erev_api.domain.reference.period_auto_open"
    assert "Pellworth" not in log_stream.getvalue()
