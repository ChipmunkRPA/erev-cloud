"""Concurrent AI admissions serialize across committed attempt-log transactions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_call_intent, ai_model_log
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard, month_window
from sqlalchemy import insert, text
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, ai_call_intent_row, ai_model_log_row

pytestmark = pytest.mark.pg
NOW = datetime(2026, 10, 15, tzinfo=UTC)


def record(
    target: UUID,
    tokens: int,
    at: datetime,
    *,
    outcome: str = "SUCCESS",
    intent_id: UUID | None = None,
    marker: str | None = None,
    has_response: bool = True,
) -> None:
    with tenant_session(DbContext(target, None, "*")) as session:
        row = ai_model_log_row(RowContext(target, new_id()), session)
        session.execute(
            insert(ai_model_log).values(
                **(
                    row
                    | {
                        "input_tokens": tokens,
                        "intent_id": intent_id,
                        "output_tokens": 0,
                        "created_at": at,
                        "outcome": outcome,
                        "parameters": {} if marker is None else {"usage_evidence": marker},
                        "response_sha256": "b" * 64 if has_response else None,
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


def intent(target: UUID, user: UUID, at: datetime) -> UUID:
    with tenant_session(DbContext(target, user, "*")) as session:
        row = ai_call_intent_row(RowContext(target, user), session) | {"created_at": at}
        session.execute(insert(ai_call_intent).values(**row))
        return UUID(str(row["id"]))


def test_unobserved_call_blocks_tenant_admission_without_monthly_expiry(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target, other = [tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(2)]
    user = new_id()
    pending = intent(target, user, NOW - timedelta(days=370))
    ctx = DbContext(target, user, "*")
    with budget_guard(ctx) as guard:
        assert guard is not None
        for at in (NOW, NOW + timedelta(days=400)):
            with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
                guard.require_available(now=at, monthly_budget=2000)
        # An old unknown call cannot be claimed as this lease's new call.
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_INTENT_BINDING_REFUSED"):
            guard.bind_intent(pending)
        with budget_guard(DbContext(other, user, "*")) as independent:
            assert independent is not None
            assert independent.require_available(now=NOW, monthly_budget=2000).tokens == 0
    # Only recorded outcome evidence clears the uncertainty; known usage is still counted.
    record(target, 40, NOW, intent_id=pending)
    with budget_guard(ctx) as guard:
        assert guard is not None
        assert guard.require_available(now=NOW, monthly_budget=41).tokens == 40
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
            guard.require_available(now=NOW, monthly_budget=40)


def test_only_the_admitted_lease_can_ignore_its_current_start(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    user = new_id()
    ctx = DbContext(target, user, "*")
    with budget_guard(ctx) as guard:
        assert guard is not None
        assert guard.require_available(now=NOW, monthly_budget=2000).tokens == 0
        pending = intent(target, user, NOW)
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_INTENT_BINDING_REFUSED"):
            guard.bind_intent(new_id())
        guard.bind_intent(pending)
        assert guard.require_available(now=NOW, monthly_budget=2000).tokens == 0
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_INTENT_BINDING_REFUSED"):
            guard.bind_intent(pending)
        # This exemption never hides a second unresolved start.
        second = intent(target, user, NOW)
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            guard.require_available(now=NOW, monthly_budget=2000)
        record(target, 10, NOW, intent_id=second)
        assert guard.require_available(now=NOW, monthly_budget=2000).tokens == 10
    with budget_guard(ctx) as fresh:
        assert fresh is not None
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            fresh.require_available(now=NOW, monthly_budget=2000)
    with pytest.raises(AIBudgetRefused, match="AI_BUDGET_LEASE_LOST"):
        guard.bind_intent(pending)


@pytest.mark.parametrize("anonymous", [False, True])
def test_current_lease_cannot_bind_another_humans_intent(
    committed_db: TestDatabase,
    keyring: KeyRing,
    anonymous: bool,
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    ctx = DbContext(target, None if anonymous else new_id(), "*")
    with budget_guard(ctx) as guard:
        assert guard is not None
        guard.require_available(now=NOW, monthly_budget=2000)
        pending = intent(target, new_id(), NOW)
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_INTENT_BINDING_REFUSED"):
            guard.bind_intent(pending)
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            guard.require_available(now=NOW, monthly_budget=2000)


@pytest.mark.parametrize("marker", [None, "UNKNOWN", "NOT_SENT", "invalid"])
def test_response_less_errors_quarantine_usage_across_months(
    committed_db: TestDatabase, keyring: KeyRing, marker: str | None
) -> None:
    target, other = [tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(2)]
    record(target, 0, NOW - timedelta(days=370), outcome="ERROR", marker=marker, has_response=False)
    with budget_guard(DbContext(target, None, "*")) as guard:
        assert guard is not None
        for at in (NOW, NOW + timedelta(days=400)):
            with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
                guard.require_available(now=at, monthly_budget=2000)
    with budget_guard(DbContext(other, None, "*")) as guard:
        assert guard is not None
        assert guard.require_available(now=NOW, monthly_budget=2000).tokens == 0


@pytest.mark.parametrize("tokens", [0, 40])
def test_reported_error_usage_without_response_is_counted(
    committed_db: TestDatabase, keyring: KeyRing, tokens: int
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    record(target, tokens, NOW, outcome="ERROR", marker="REPORTED", has_response=False)
    with budget_guard(DbContext(target, None, "*")) as guard:
        assert guard is not None
        assert guard.require_available(now=NOW, monthly_budget=tokens + 1).tokens == tokens
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
            guard.require_available(now=NOW, monthly_budget=tokens)


@pytest.mark.parametrize("marker", [None, "NOT_SENT"])
@pytest.mark.parametrize("outcome", ["BUDGET_EXCEEDED", "DISABLED"])
def test_unsent_admission_records_do_not_quarantine(
    committed_db: TestDatabase, keyring: KeyRing, marker: str | None, outcome: str
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    record(target, 0, NOW, outcome=outcome, marker=marker, has_response=False)
    with budget_guard(DbContext(target, None, "*")) as guard:
        assert guard is not None
        assert guard.require_available(now=NOW, monthly_budget=100).tokens == 0


def test_bound_intent_does_not_exempt_a_committed_unknown_usage_error(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    target = tenant_id_of(tenant_factory(keyring=keyring))
    ctx = DbContext(target, new_id(), "*")
    assert ctx.user_id is not None
    with budget_guard(ctx) as guard:
        assert guard is not None
        guard.require_available(now=NOW, monthly_budget=2000)
        started = intent(target, ctx.user_id, NOW)
        guard.bind_intent(started)
        record(
            target, 0, NOW, outcome="ERROR", marker="UNKNOWN", has_response=False, intent_id=started
        )
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            guard.require_available(now=NOW, monthly_budget=2000)
