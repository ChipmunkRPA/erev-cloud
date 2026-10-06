"""The lock the setup completion takes on the tenant's row (dev-guide DG-KRN-DB-08 rev 1.165;
supervisor ruling R-119 (d), item SETUP-COMPLETION-LOCK-1; PRD BR-PLT-02; 04 T-PLT-01). No database:
the statements ``setup.evaluate_setup_completion`` emits over a statement-capturing session,
compiled for PostgreSQL.

Every table of a tenant references ``tenant``, so a transaction that has inserted a row holds the
tenant's row ``FOR KEY SHARE`` to its end. ``FOR UPDATE`` conflicts with that lock; ``FOR NO KEY
UPDATE`` does not, and is all the completion needs — it serialises two completions and the update
that follows changes no key column. The interleaving this ended is witnessed on PostgreSQL in
``tests/domain/close/test_lock_decision_db.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from erev_api.domain.platform import setup
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
TENANT = UUID("00000000-0000-0000-0000-00000000aa01")
ACTOR = UUID("00000000-0000-0000-0000-0000000000a2")
PREPARER = UUID("00000000-0000-0000-0000-0000000000b1")
APPROVER = UUID("00000000-0000-0000-0000-0000000000b2")


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def first(self) -> Any:
        return self.value


class _Session:
    """A tenant whose setup is not complete and for which BR-PLT-02 holds: a period is open, and
    the preparing and the approving permission are held by two memberships."""

    def __init__(self) -> None:
        self.statements: list[Any] = []
        self._holders = [[PREPARER], [APPROVER]]

    def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        if isinstance(statement, Update):
            return _Result(None)
        if "FROM erev.tenant" in _sql(statement):
            return _Result(None)  # setup_completed_at IS NULL, read plainly and under the lock
        if "app.entity_scope" in _sql(statement):
            # The open period is read under the tenant's SYSTEM scope (04 T-PLT-01 rev 1.224):
            # this caller's scope is tenant-wide already, so the block issues no setting.
            return _Result("*")
        return _Result((UUID(int=1),))  # an open period exists

    def scalars(self, statement: Any) -> list[UUID]:
        self.statements.append(statement)
        return self._holders.pop(0)


class _Uow:
    def __init__(self) -> None:
        self.session = _Session()
        self.now = NOW
        self.principal = SimpleNamespace(
            tenant_id=TENANT, id=ACTOR, kind=SimpleNamespace(value="USER")
        )
        self.audits: list[dict[str, Any]] = []

    def audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)


def test_the_completion_locks_the_tenant_row_for_no_key_update() -> None:
    """The one locking read of the completion is ``FOR NO KEY UPDATE`` on the tenant's row, taken
    after the conditions were found true; the update and the audit event follow. Fail-first: the
    read was ``FOR UPDATE``, which waits for every transaction of the tenant that has inserted a
    row and has not ended."""
    uow = _Uow()
    assert setup.evaluate_setup_completion(uow) is True  # type: ignore[arg-type]
    emitted = [_sql(statement) for statement in uow.session.statements]
    locking = [sql for sql in emitted if " FOR " in sql]
    assert len(locking) == 1 and locking[0].endswith("FOR NO KEY UPDATE")
    assert "FROM erev.tenant" in locking[0]
    assert emitted.index(locking[0]) == len(emitted) - 2  # the conditions first, the update last
    assert isinstance(uow.session.statements[-1], Update)
    assert [event["action"] for event in uow.audits] == [setup.COMPLETED_ACTION]
