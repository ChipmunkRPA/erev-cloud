"""RCP-28a lock lifetime uses the real app-role PostgreSQL transaction."""

from __future__ import annotations

from uuid import uuid4

import pytest
from erev_api.db.session import DbContext, app_engine, tenant_session
from erev_api.domain.contracts.release_validation import execution_lock_key
from erev_api.domain.contracts.verification_lock import TransactionExecutionLock
from sqlalchemy import text
from sqlalchemy.orm import Session
from support.db import TestDatabase

pytestmark = pytest.mark.pg
TRY_LOCK = text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))")


class _RollbackProbe(Exception):
    pass


def _available(ctx: DbContext, key: str) -> bool:
    with tenant_session(ctx) as other:
        return bool(other.execute(TRY_LOCK, {"key": key}).scalar_one())


@pytest.mark.parametrize("rollback", [False, True], ids=["commit", "rollback"])
def test_verification_lock_lasts_until_writer_transaction_ends(
    test_database: TestDatabase, rollback: bool
) -> None:
    attempt, group = uuid4(), uuid4()
    key = execution_lock_key(attempt, group)
    ctx = DbContext(tenant_id=uuid4(), user_id=None, entity_scope="*")
    try:
        with tenant_session(ctx) as writer:
            with TransactionExecutionLock(writer).acquire(key):
                assert not _available(ctx, key)
                for independent in (
                    execution_lock_key(attempt, uuid4()),
                    execution_lock_key(uuid4(), group),
                ):
                    assert _available(ctx, independent)
            # Ending the Python block must not expose a not-yet-committed result.
            assert not _available(ctx, key)
            if rollback:
                raise _RollbackProbe
    except _RollbackProbe:
        pass
    assert _available(ctx, key)


def test_verification_lock_requires_existing_writer_transaction(
    test_database: TestDatabase,
) -> None:
    with Session(app_engine()) as writer:
        with pytest.raises(RuntimeError, match="active transaction"):
            with TransactionExecutionLock(writer).acquire(execution_lock_key(uuid4(), uuid4())):
                pytest.fail("lock opened its own transaction")
        assert not writer.in_transaction()
