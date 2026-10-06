"""SCH-05 / SCH-06 pure rules (record §4.29): the due predicate, the TZ-06 local date, the
05 SCH-05 comment literal and, since rev 1.83, which errors of an opening leave the period for the
next tick. The database path is measured by
``tests/domain/reference/test_period_auto_open_db.py``."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import psycopg
import pytest
from erev_api.clock import FrozenClock, entity_today
from erev_api.db import errors as db_errors
from erev_api.domain.reference import period_auto_open, period_redirty_job
from erev_api.jobs.context import JobRuntime
from erev_api.problems import PROBLEMS, Problem, from_db_error
from psycopg import errors as pg
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError


def _raised(code: str) -> DBAPIError:
    """What SQLAlchemy raises for the driver's error of ``code``."""
    orig = pg.lookup(code)("probe")
    wrapped = DBAPIError.instance("SELECT 1 FROM erev.probe", None, orig, psycopg.Error)
    assert isinstance(wrapped, DBAPIError) and db_errors.sqlstate(wrapped) == code
    return wrapped


def _mapped(error: DBAPIError) -> Problem:
    """The problem a mapper raises from ``error`` - the commit's (``uow.py``) and every
    ``except DBAPIError`` around a statement (``transitions.apply``)."""
    problem = from_db_error(error)
    assert problem is not None
    try:
        raise problem from error
    except Problem as raised:
        return raised


def test_a_period_is_due_on_and_after_its_start_date() -> None:
    start = date(2026, 10, 1)
    assert period_auto_open.due(start, date(2026, 9, 30)) is False
    assert period_auto_open.due(start, date(2026, 10, 1)) is True
    assert period_auto_open.due(start, date(2026, 10, 2)) is True


def test_tz_06_the_entity_local_date_decides_not_the_utc_date() -> None:
    """At 2026-10-01T03:00Z New York is still 30 September while Auckland is 1 October."""
    clock = FrozenClock(datetime(2026, 10, 1, 3, 0, tzinfo=UTC))
    october = date(2026, 10, 1)
    assert entity_today(clock, "America/New_York") == date(2026, 9, 30)
    assert entity_today(clock, "Pacific/Auckland") == october
    assert period_auto_open.due(october, entity_today(clock, "America/New_York")) is False
    assert period_auto_open.due(october, entity_today(clock, "Pacific/Auckland")) is True


def test_the_comment_is_the_05_sch_05_literal_and_the_report_starts_empty() -> None:
    assert period_auto_open.AUTO_OPEN_COMMENT == "Opened automatically on the period start date"
    assert period_auto_open.AutoOpenReport() == period_auto_open.AutoOpenReport(0, 0, 0, 0, 0, 0, 0)


def test_sch_05_the_two_not_now_answers_and_their_log_events() -> None:
    """05 SCH-05 rev 1.83 (supervisor ruling R-97 (6)): the kernel's two answers that say "this
    transaction, not now" while the server is serving, and the event the tick logs for each."""
    assert dict(period_auto_open.NOT_NOW_EVENTS) == {
        "lock-conflict": "period_auto_open.lock_conflict",
        "statement-timeout": "period_auto_open.statement_timeout",
    }
    assert {PROBLEMS[slug].status for slug in period_auto_open.NOT_NOW_EVENTS} == {409, 503}
    # The tick's other unit of work per period state, the re-deferral of a failed re-marking
    # (05 SCH-06), is isolated on the same two answers under its own events.
    assert dict(period_auto_open.REDEFER_NOT_NOW_EVENTS) == {
        "lock-conflict": "period_open_redirty.lock_conflict",
        "statement-timeout": "period_open_redirty.statement_timeout",
    }


@pytest.mark.parametrize(
    ("code", "slug"),
    [
        ("55P03", "lock-conflict"),
        ("40P01", "lock-conflict"),
        ("40001", "lock-conflict"),
        ("57014", "statement-timeout"),
    ],
)
def test_sch_05_an_opening_that_could_not_be_done_now_is_named_raw_and_mapped(
    code: str, slug: str
) -> None:
    """The tick settles the database error and the problem a mapper raised from it alike: a
    cancelled statement was logged as a refusal of the period in one form and ended the tick in
    the other."""
    raw = _raised(code)
    assert period_auto_open.not_now(raw) == (slug, code)
    assert period_auto_open.not_now(_mapped(raw)) == (slug, code)


def test_sch_05_every_other_error_is_neither_of_the_two_answers() -> None:
    """``not_now`` names the two answers and nothing else. What the tick does with every other
    error - passes over it at error level, unless it is the server's own state (rev 1.106) - is
    ``test_sch_05_only_the_servers_own_state_ends_the_tick``."""
    # The server's own state - the 503 set - is neither answer: it ends the tick.
    for code in ("53200", "08006", "57P01"):
        assert db_errors.server_unavailable(_raised(code))
        assert period_auto_open.not_now(_raised(code)) == (None, code)
    # An error the mapper names otherwise (42501) or does not name at all (23505, XX000).
    for code in ("42501", "23505", "XX000"):
        assert period_auto_open.not_now(_raised(code)) == (None, code)
    assert period_auto_open.not_now(_mapped(_raised("42501"))) == (None, "42501")
    # A refusal of the opening itself is no database error and is settled where it is raised.
    assert period_auto_open.not_now(Problem("invalid-transition")) == (None, None)
    # The problem without a database error behind it carries no SQLSTATE.
    assert period_auto_open.not_now(Problem("lock-conflict")) == ("lock-conflict", None)


def test_sch_05_only_the_servers_own_state_ends_the_tick() -> None:
    """05 SCH-05 rev 1.106 (supervisor ruling R-118 (k); as R-50 (a) for the fan-out and the
    sweeper): the tick ends on an error that says the server cannot serve - the slug-less 503 set
    of 04 API-C-05, the pool timeout included - found as the error itself or as what it was raised
    from. Every other exception is one period's alone: logged and passed over."""
    for code in ("53200", "08006", "57P01"):
        assert period_auto_open.ends_the_tick(_raised(code))
    lost = OperationalError(
        "SELECT 1", None, Exception("server closed the connection unexpectedly")
    )
    assert db_errors.sqlstate(lost) is None and period_auto_open.ends_the_tick(lost)
    pool = PoolTimeoutError("QueuePool limit of size 10 overflow 10 reached")
    assert period_auto_open.ends_the_tick(pool)
    try:
        try:
            raise _raised("53200")
        except DBAPIError as error:
            raise RuntimeError("the opening could not read its period") from error
    except RuntimeError as wrapped:
        assert period_auto_open.ends_the_tick(wrapped)
    # The two "not now" answers, a deterministic refusal, a defect and a refusal of the period.
    for code in ("55P03", "40P01", "40001", "57014", "23505", "XX000", "58030"):
        assert not period_auto_open.ends_the_tick(_raised(code)), code
    for code in ("55P03", "40P01", "40001", "57014"):
        assert not period_auto_open.ends_the_tick(_mapped(_raised(code))), code
    assert not period_auto_open.ends_the_tick(RuntimeError("a defect"))
    assert not period_auto_open.ends_the_tick(Problem("invalid-transition"))
    # What is passed over without being one of the two named answers has no "not now" event.
    assert period_auto_open.not_now(RuntimeError("a defect")) == (None, None)
    assert (period_auto_open.FAILED_EVENT, period_auto_open.REDEFER_FAILED_EVENT) == (
        "period_auto_open.failed",
        "period_open_redirty.failed",
    )


FIRST: UUID = UUID("00000000-0000-4000-8000-000000000001")
SECOND: UUID = UUID("00000000-0000-4000-8000-000000000002")
OCTOBER = period_auto_open.Candidate(
    state_id=UUID("00000000-0000-4000-8000-0000000000a1"),
    entity_id=UUID("00000000-0000-4000-8000-0000000000e1"),
    entity_code="AVM-US",
    time_zone="America/New_York",
    book_code="GAAP",
    period_id=UUID("00000000-0000-4000-8000-0000000000b1"),
    period_key="FY2026-P10",
    start_date=date(2026, 10, 1),
    end_date=date(2026, 10, 31),
)


class _Tenants:
    """The tick over tenants without a database: ``tenant_session`` hands out the tenant's id as
    its session, and the two reads answer per tenant - a list, or an exception to raise."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *tenants: UUID) -> None:
        self.due: dict[UUID, Any] = {tenant: [] for tenant in tenants}
        self.failed_jobs: dict[UUID, Any] = {tenant: [] for tenant in tenants}

        @contextmanager
        def session(context: Any, *, read_only: bool) -> Iterator[UUID]:
            assert read_only
            yield context.tenant_id

        def answer(table: dict[UUID, Any], tenant: UUID) -> Any:
            if isinstance(table[tenant], BaseException):
                raise table[tenant]
            return table[tenant]

        monkeypatch.setattr(period_auto_open, "eligible_tenants", lambda *_, **__: list(tenants))
        monkeypatch.setattr(period_auto_open, "tenant_session", session)
        monkeypatch.setattr(
            period_auto_open, "candidates", lambda db, *, clock: answer(self.due, db)
        )
        monkeypatch.setattr(
            period_redirty_job, "failed_states", lambda db: answer(self.failed_jobs, db)
        )

    def run(self) -> period_auto_open.AutoOpenReport:
        clock = FrozenClock(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))
        return period_auto_open.run(JobRuntime(clock=clock, keyring=None, files=None))


def _events(log_stream: io.StringIO, prefix: str = "period_") -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    return [line for line in lines if str(line["event"]).startswith(prefix)]


def test_sch_05_a_tenants_read_that_fails_skips_its_step_and_the_tick_goes_on(
    monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    """05 SCH-05 rev 1.139 (supervisor ruling of 2026-10-01 on R-118 (k)): the two reads per tenant
    are isolated like an opening. A read that raises anything but the server's own state is logged
    at error level with the tenant, its class and the place it was raised; that step is skipped for
    the tenant, its other step still runs, and the next tenant is served. The report counts
    tenants, not steps. Fail-first: the exception left ``run`` and no tenant after this one was
    served."""
    world = _Tenants(monkeypatch, FIRST, SECOND)
    world.due[FIRST] = KeyError("No time zone found with key Mars/Olympus_Mons")
    world.failed_jobs[SECOND] = RuntimeError("a defect that names customer Pellworth")
    report = world.run()
    assert report == period_auto_open.AutoOpenReport(tenants=2, tenants_skipped=2)
    assert (period_auto_open.READ_FAILED_EVENT, period_auto_open.REDEFER_READ_FAILED_EVENT) == (
        "period_auto_open.read_failed",
        "period_open_redirty.read_failed",
    )
    module = "erev_api.domain.reference.period_auto_open"
    assert [
        (line["event"], line["level"], line["tenant_id"], line["error_class"])
        for line in _events(log_stream)
        if line["event"].endswith("read_failed")
    ] == [
        ("period_auto_open.read_failed", "error", str(FIRST), "KeyError"),
        ("period_open_redirty.read_failed", "error", str(SECOND), "RuntimeError"),
    ]
    # The place is the tick's own line that made the read; the reads are stand-ins of this test.
    assert {line["error_at"].rpartition(":")[0] for line in _events(log_stream, "period_")[:2]} == {
        module
    }
    (completed,) = [line for line in _events(log_stream) if line["event"].endswith(".completed")]
    assert (completed["tenants"], completed["tenants_skipped"]) == (2, 2)
    assert "Olympus" not in log_stream.getvalue() and "Pellworth" not in log_stream.getvalue()


def test_sch_05_both_steps_of_one_tenant_skipped_count_one_tenant(
    monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    world = _Tenants(monkeypatch, FIRST, SECOND)
    world.due[FIRST] = RuntimeError("the due periods")
    world.failed_jobs[FIRST] = RuntimeError("the failed jobs")
    assert world.run() == period_auto_open.AutoOpenReport(tenants=2, tenants_skipped=1)
    assert [line["event"] for line in _events(log_stream)] == [
        "period_auto_open.read_failed",
        "period_open_redirty.read_failed",
        "period_auto_open.completed",
    ]


@pytest.mark.parametrize("read", ["due", "failed_jobs"])
def test_sch_05_the_servers_own_state_in_a_tenants_read_ends_the_tick(
    read: str, monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    world = _Tenants(monkeypatch, FIRST, SECOND)
    getattr(world, read)[FIRST] = _raised("53200")
    with pytest.raises(DBAPIError):
        world.run()
    assert [line["event"] for line in _events(log_stream)] == []


def test_sch_05_a_refused_opening_whose_unit_of_work_fails_to_discard_is_counted_once(
    monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    """05 SCH-05 rev 1.139: an opening is counted once. A period refused by its own rules was
    counted as failed inside its unit of work, and a second time when discarding that unit of
    work raised an error that is not the server's own state. Fail-first: ``failed == 2`` for one
    candidate."""
    world = _Tenants(monkeypatch, FIRST)
    world.due[FIRST] = [OCTOBER]

    @contextmanager
    def unit_of_work(runtime: Any, principal: Any, *, request_id: str) -> Iterator[object]:
        yield object()
        raise RuntimeError("the transaction could not be rolled back")

    def refuse(uow: object, *, state_id: UUID, comment: str | None) -> Any:
        raise Problem("invalid-transition")

    monkeypatch.setattr(period_auto_open, "system_unit_of_work", unit_of_work)
    monkeypatch.setattr(period_auto_open, "open_future_period", refuse)
    report = world.run()
    assert report == period_auto_open.AutoOpenReport(tenants=1, candidates=1, failed=1)
    assert [(line["event"], line["level"]) for line in _events(log_stream)] == [
        ("period_auto_open.refused", "warning"),
        ("period_auto_open.failed", "error"),
        ("period_auto_open.completed", "info"),
    ]
