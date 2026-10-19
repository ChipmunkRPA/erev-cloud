"""Transaction fence for the last population check and release acceptance."""

from sqlalchemy import text

from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def hold(uow: UnitOfWork) -> None:
    """Reserve this tenant's population until commit/rollback, before taking validation locks.

    Migration 0165 gives every population-table writer the shared side. Try-locking both
    sides avoids a deadlock with callers that already hold group, period or parent rows.
    Acceptance must re-read the population after acquiring this fence under READ COMMITTED.
    It must not perform remote work or publish files while holding the fence.
    """
    if uow.principal.db_context.entity_scope != "*":
        raise Problem("forbidden")
    if uow.session.scalar(text("SHOW transaction_isolation")) != "read committed":
        raise Problem("invalid-transition", "Population acceptance requires a fresh read snapshot.")
    acquired = uow.session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"erev:validation-population:{uow.principal.tenant_id}"},
    )
    if not acquired:
        raise Problem("lock-conflict", "The validation population is being changed; retry.")
