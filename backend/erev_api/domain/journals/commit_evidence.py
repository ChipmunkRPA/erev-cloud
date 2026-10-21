"""Archive PostgreSQL commit timestamps after the accounting transaction commits."""

from uuid import UUID

from sqlalchemy import text

from erev_api.db.session import DbContext, tenant_session
from erev_api.uow import UnitOfWork


def retain_after_commit(uow: UnitOfWork, posting_id: UUID) -> None:
    tenant_id = uow.principal.tenant_id

    def retain() -> None:
        # Metadata is tenant-scoped, like the posting seal. The SQL function reads
        # the actual source transaction and accepts no caller-supplied timestamp.
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            session.execute(
                text("SELECT erev.capture_subledger_commit(:posting)"), {"posting": posting_id}
            )

    uow.after_commit(retain)
