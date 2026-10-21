"""Archive PostgreSQL commit timestamps after the accounting transaction commits."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import historical_source_commit, subledger_posting_commit
from erev_api.logging import get_logger, register_logger_fields
from erev_api.uow import UnitOfWork

_LOGGER = __name__
register_logger_fields(_LOGGER, ("tenant_id", "posting_id", "retained", "failed"))


def _capture(session: Session, posting_id: UUID) -> None:
    session.execute(text("SELECT erev.capture_subledger_commit(:posting)"), {"posting": posting_id})


def retain_after_commit(uow: UnitOfWork, posting_id: UUID) -> None:
    tenant_id = uow.principal.tenant_id

    def retain() -> None:
        # Metadata is tenant-scoped, like the posting seal. The SQL function reads
        # the actual source transaction and accepts no caller-supplied timestamp.
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            _capture(session, posting_id)

    uow.after_commit(retain)


def recover_pending(tenant_id: UUID, *, batch_size: int = 256) -> tuple[int, int]:
    """Retry committed evidence in bounded transactions; return (retained, failed).

    Keyset pagination visits a failing row only once per sweep, so expired evidence cannot
    starve later postings. Row locks coordinate concurrent sweepers and after-commit hooks.
    Savepoints isolate individual failures; a connection failure is left to the next sweep.
    """
    if not 1 <= batch_size <= 4096:
        raise ValueError("batch_size must be between 1 and 4096")
    table = subledger_posting_commit
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    after: UUID | None = None
    retained = failed = 0
    while True:
        with tenant_session(context) as session:
            query = (
                select(table.c.subledger_posting_id)
                .where(table.c.tenant_id == tenant_id, table.c.committed_server_at.is_(None))
                .order_by(table.c.subledger_posting_id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            if after is not None:
                query = query.where(table.c.subledger_posting_id > after)
            postings = list(session.scalars(query))
            if not postings:
                break
            batch_retained = batch_failed = 0
            for posting_id in postings:
                try:
                    with session.begin_nested():
                        _capture(session, posting_id)
                    batch_retained += 1
                except Exception:
                    batch_failed += 1
                    get_logger(_LOGGER).exception(
                        "ledger.commit_evidence_recovery_failed",
                        tenant_id=str(tenant_id),
                        posting_id=str(posting_id),
                    )
        # Count success only after the batch transaction has actually committed.
        retained += batch_retained
        failed += batch_failed
        after = postings[-1]
    if retained or failed:
        get_logger(_LOGGER).info(
            "ledger.commit_evidence_recovered",
            tenant_id=str(tenant_id),
            retained=retained,
            failed=failed,
        )
    return retained, failed


def _capture_source(session: Session, kind: str, source_id: UUID) -> None:
    session.execute(
        text("SELECT erev.capture_source_commit(:kind, :source)"),
        {"kind": kind, "source": source_id},
    )


def retain_sources_after_commit(uow: UnitOfWork, kind: str, ids: Sequence[UUID]) -> None:
    sources = tuple(ids)
    tenant_id = uow.principal.tenant_id

    def retain() -> None:
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            for source_id in sources:
                _capture_source(session, kind, source_id)

    uow.after_commit(retain)


def recover_pending_sources(tenant_id: UUID, *, batch_size: int = 256) -> tuple[int, int]:
    """Retry committed evidence in bounded transactions; return (retained, failed).

    Keyset pagination visits a failing row only once per sweep, so expired evidence cannot
    starve later postings. Row locks coordinate concurrent sweepers and after-commit hooks.
    Savepoints isolate individual failures; a connection failure is left to the next sweep.
    """
    if not 1 <= batch_size <= 4096:
        raise ValueError("batch_size must be between 1 and 4096")
    table = historical_source_commit
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    after: tuple[str, UUID] | None = None
    retained = failed = 0
    while True:
        with tenant_session(context) as session:
            query = (
                select(table.c.source_kind, table.c.source_id)
                .where(table.c.tenant_id == tenant_id, table.c.committed_server_at.is_(None))
                .order_by(table.c.source_kind, table.c.source_id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            if after is not None:
                query = query.where(tuple_(table.c.source_kind, table.c.source_id) > after)
            postings = list(session.execute(query).tuples())
            if not postings:
                break
            batch_retained = batch_failed = 0
            for kind, source_id in postings:
                try:
                    with session.begin_nested():
                        _capture_source(session, kind, source_id)
                    batch_retained += 1
                except Exception:
                    batch_failed += 1
                    get_logger(_LOGGER).exception(
                        "source.commit_evidence_recovery_failed",
                        tenant_id=str(tenant_id),
                        posting_id=f"{kind}:{source_id}",
                    )
        # Count success only after the batch transaction has actually committed.
        retained += batch_retained
        failed += batch_failed
        after = (postings[-1][0], postings[-1][1])
    if retained or failed:
        get_logger(_LOGGER).info(
            "source.commit_evidence_recovered",
            tenant_id=str(tenant_id),
            retained=retained,
            failed=failed,
        )
    return retained, failed
