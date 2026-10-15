"""Serialize AI admission and read committed UTC-month usage (05 §5.10 step 3).

The gateway must hold the slot through the provider call and committed attempt
log. Busy callers must requeue without calling a provider. This does not reserve
unknown provider usage or recover an unlogged call after a process crash.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import BigInteger, cast, func, select, text
from sqlalchemy.engine import Connection

from erev_api.db.session import DbContext, lock_connection, tenant_session
from erev_api.db.tables import ai_model_log

_TRY_LOCK = text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))")
_UNLOCK = text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))")


class AIBudgetRefused(ValueError):
    """Fixed safe admission error."""


@dataclass(frozen=True, slots=True)
class MonthlyUsage:
    start: datetime
    end: datetime
    tokens: int


def month_window(now: datetime) -> tuple[datetime, datetime]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise AIBudgetRefused("AI_INVALID_BUDGET_CLOCK")
    utc = now.astimezone(UTC)
    start = utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


class BudgetGuard:
    """A live process-local lease; the admission read must happen inside its block."""

    def __init__(self, context: DbContext, connection: Connection) -> None:
        self._context = context
        self._connection = connection
        self._active = True

    def require_available(self, *, now: datetime, monthly_budget: int) -> MonthlyUsage:
        if not self._active or self._connection.closed or self._connection.invalidated:
            raise AIBudgetRefused("AI_BUDGET_LEASE_LOST")
        if type(monthly_budget) is not int or monthly_budget < 0:
            raise AIBudgetRefused("AI_INVALID_TOKEN_BUDGET")
        # Never silently reconnect an invalidated session and continue without its lock.
        self._connection.execute(select(1)).scalar_one()
        start, end = month_window(now)
        with tenant_session(self._context, read_only=True) as session:
            tokens = session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            cast(ai_model_log.c.input_tokens, BigInteger)
                            + cast(ai_model_log.c.output_tokens, BigInteger)
                        ),
                        0,
                    )
                ).where(
                    ai_model_log.c.tenant_id == self._context.tenant_id,
                    ai_model_log.c.created_at >= start,
                    ai_model_log.c.created_at < end,
                )
            ).scalar_one()
        usage = MonthlyUsage(start, end, int(tokens))
        if usage.tokens >= monthly_budget:
            raise AIBudgetRefused("AI_BUDGET_EXHAUSTED")
        return usage


@contextmanager
def budget_guard(context: DbContext) -> Iterator[BudgetGuard | None]:
    """One session lock per tenant, across months and short database transactions.

    A busy slot yields None without waiting. The lock connection uses autocommit,
    so no database transaction stays open while a provider is working. The caller
    must commit its usage log before leaving this context, including failed calls
    for which the provider returned usage. The release discards a suspect connection.
    """
    key = f"erev-ai-budget:{context.tenant_id}"
    with lock_connection(context) as connection:
        try:
            held = bool(connection.execute(_TRY_LOCK, {"key": key}).scalar_one())
        except BaseException:
            connection.invalidate()
            raise
        if not held:
            yield None
            return
        guard = BudgetGuard(context, connection)
        try:
            yield guard
        finally:
            guard._active = False
            try:
                if connection.closed or connection.invalidated:
                    raise AIBudgetRefused("AI_BUDGET_LEASE_LOST")
                if not connection.execute(_UNLOCK, {"key": key}).scalar_one():
                    connection.invalidate()
                    raise AIBudgetRefused("AI_BUDGET_LEASE_LOST")
            except BaseException:
                connection.invalidate()
                raise
