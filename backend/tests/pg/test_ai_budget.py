"""Concurrent AI admissions serialize across committed attempt-log transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_model_log
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard, month_window
from sqlalchemy import insert, text
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, ai_model_log_row

pytestmark = pytest.mark.pg
NOW = datetime(2026, 10, 15, tzinfo=UTC)


def record(target: UUID, tokens: int, at: datetime, *, outcome: str = "SUCCESS") -> None:
    with tenant_session(DbContext(target, None, "*")) as session:
        row = ai_model_log_row(RowContext(target, new_id()), session)
        session.execute(
            insert(ai_model_log).values(
                **(
                    row
                    | {
                        "input_tokens": tokens,
                        "output_tokens": 0,
                        "created_at": at,
                        "outcome": outcome,
                    }
                )
            )
        )


def test_busy_job_cannot_pass_stale_usage_then_sees_committed_exhaustion(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    ctx = DbContext(target, None, "*")
    record(target, 1900, NOW)
    with budget_guard(ctx) as first:
        assert first is not None
        pid = first._connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
        with tenant_session(ctx, read_only=True) as observer:
            state = observer.execute(
                text("SELECT state, xact_start FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            ).one()
            assert tuple(state) == ("idle", None)
        assert first.require_available(now=NOW, monthly_budget=2000).tokens == 1900
        with budget_guard(ctx) as competing:
            assert competing is None
        record(target, 100, NOW)
        with budget_guard(ctx) as still_competing:
            assert still_competing is None
    with pytest.raises(AIBudgetRefused, match="AI_BUDGET_LEASE_LOST"):
        first.require_available(now=NOW, monthly_budget=2000)
    with budget_guard(ctx) as next_job:
        assert next_job is not None
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
            next_job.require_available(now=NOW, monthly_budget=2000)


def test_other_tenant_has_independent_slot_and_usage(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    first, second = [tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(2)]
    record(first, 2000, NOW)
    with budget_guard(DbContext(first, None, "*")) as one:
        with budget_guard(DbContext(second, None, "*")) as two:
            assert one is not None and two is not None
            assert two.require_available(now=NOW, monthly_budget=2000).tokens == 0
            with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
                one.require_available(now=NOW, monthly_budget=2000)


def test_month_boundaries_and_error_usage_are_counted(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    start, end = month_window(NOW)
    record(target, 1000, start - timedelta(microseconds=1))
    record(target, 100, start)
    record(target, 200, end - timedelta(microseconds=1), outcome="ERROR")
    record(target, 1000, end)
    with budget_guard(DbContext(target, None, "*")) as guard:
        assert guard is not None
        usage = guard.require_available(now=NOW, monthly_budget=301)
        assert usage.tokens == 300
        assert (usage.start, usage.end) == (start, end)
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
            guard.require_available(now=NOW, monthly_budget=300)


def test_exception_releases_slot_and_zero_budget_stops_empty_month(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    ctx = DbContext(target, None, "*")
    with pytest.raises(RuntimeError, match="injected failure"):
        with budget_guard(ctx) as guard:
            assert guard is not None
            raise RuntimeError("injected failure")
    with budget_guard(ctx) as next_guard:
        assert next_guard is not None
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
            next_guard.require_available(now=NOW, monthly_budget=0)
        for invalid in (True, -1):
            with pytest.raises(AIBudgetRefused, match="AI_INVALID_TOKEN_BUDGET"):
                next_guard.require_available(now=NOW, monthly_budget=invalid)


def test_utc_window_across_local_month_and_year_boundary() -> None:
    instant = datetime(2027, 1, 1, 1, tzinfo=timezone(timedelta(hours=14)))
    assert month_window(instant) == (
        datetime(2026, 12, 1, tzinfo=UTC),
        datetime(2027, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(AIBudgetRefused, match="AI_INVALID_BUDGET_CLOCK"):
        month_window(NOW.replace(tzinfo=None))


def test_lost_connection_cannot_continue_admission(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    ctx = DbContext(target, None, "*")
    with pytest.raises(AIBudgetRefused, match="AI_BUDGET_LEASE_LOST"):
        with budget_guard(ctx) as guard:
            assert guard is not None
            guard._connection.invalidate()
            with pytest.raises(AIBudgetRefused, match="AI_BUDGET_LEASE_LOST"):
                guard.require_available(now=NOW, monthly_budget=2000)
    with budget_guard(ctx) as fresh:
        assert fresh is not None
        assert fresh.require_available(now=NOW, monthly_budget=2000).tokens == 0
