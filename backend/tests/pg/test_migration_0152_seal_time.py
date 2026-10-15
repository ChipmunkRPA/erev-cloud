"""Historical sealing instants cannot be fabricated on upgrade or discarded on downgrade."""

from __future__ import annotations

from typing import Any

import pytest
from alembic import command
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import subledger_line, subledger_posting_seal
from sqlalchemy import exc, func, select, text, update
from support import rows
from support.db import TestDatabase, alembic_config, fresh_head
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_ledger_rows
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_sealing_time_migration_preserves_populated_ledger(
    test_database: TestDatabase, keyring: KeyRing, direction: str
) -> None:
    fresh_head()
    try:
        if direction == "upgrade":
            command.downgrade(alembic_config(), "0151")
        test_database.app_engine.dispose()
        test_database.owner_engine.dispose()
        tenant = tenant_id_of(tenant_factory(keyring=keyring))
        context = DbContext(tenant, None, "*")
        with tenant_session(context) as session:
            insert_ledger_rows(session, tenant)
            before = session.execute(text("SELECT * FROM erev.subledger_line ORDER BY id")).all()
            seals = session.execute(text("SELECT * FROM erev.subledger_posting_seal")).all()
        with pytest.raises(exc.DBAPIError) as refused:
            if direction == "upgrade":
                command.upgrade(alembic_config(), "head")
            else:
                command.downgrade(alembic_config(), "0151")
        assert getattr(refused.value.orig, "sqlstate", None) == "23514"
        assert "ck_subledger_seal__0152_empty" in str(refused.value.orig)
        with test_database.owner_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM erev.alembic_version")) == (
                "0151" if direction == "upgrade" else "0152"
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname='ck_subledger_seal__0152_empty'"
                    )
                )
                == 0
            )
        with tenant_session(context, read_only=True) as session:
            after = session.execute(text("SELECT * FROM erev.subledger_line ORDER BY id")).all()
            assert after == before
            assert session.execute(text("SELECT * FROM erev.subledger_posting_seal")).all() == seals
            assert ("sealed_server_at" in seals[0]._mapping) == (direction == "downgrade")
    finally:
        fresh_head()
        test_database.app_engine.dispose()
        test_database.owner_engine.dispose()


def test_sealing_timestamp_overrides_callers_and_is_immutable(
    committed_db: TestDatabase, keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant, None, "*")
    original = rows.ledger_seal_values

    def forged(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return original(*args, **kwargs) | {"sealed_server_at": rows.PROBE_RECORDED_AT}

    monkeypatch.setattr(rows, "ledger_seal_values", forged)
    statement = update(subledger_posting_seal).values(sealed_server_at=rows.PROBE_RECORDED_AT)
    with tenant_session(context) as session:
        inserted = insert_ledger_rows(session, tenant)
        stamp = session.scalar(
            select(subledger_posting_seal.c.sealed_server_at).where(
                subledger_posting_seal.c.subledger_posting_id == inserted.posting_id
            )
        )
        last_line = session.scalar(select(func.max(subledger_line.c.recorded_server_at)))
        assert stamp is not None and last_line is not None
        assert stamp >= last_line and stamp > rows.PROBE_RECORDED_AT
        assert _fails(session, statement)[0] == "42501"
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(
                "ALTER TABLE erev.subledger_posting_seal NO FORCE ROW LEVEL SECURITY"
            )
            assert "EREV-IMM-001" in _owner_failure(connection, statement)
        finally:
            transaction.rollback()
    with tenant_session(context, read_only=True) as session:
        assert session.scalar(select(subledger_posting_seal.c.sealed_server_at)) == stamp
