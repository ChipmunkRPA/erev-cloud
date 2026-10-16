"""RCP-28a transaction-scoped execution lock for the verification writer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session


class TransactionExecutionLock:
    """Hold the shared-state lock through the caller's commit or rollback.

    Construct with the same session used by VerificationStore. Exiting acquire does not
    release the database lock: result insertion and pointer/state updates must commit together.
    This adapter neither opens a separate transaction nor commits the caller's work.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def acquire(self, key: str) -> Iterator[None]:
        if not self._session.in_transaction():
            raise RuntimeError("verification lock requires the writer's active transaction")
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )
        yield
