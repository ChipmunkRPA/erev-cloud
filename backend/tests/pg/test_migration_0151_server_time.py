"""Changing the sealed line document refuses populated ledgers in either direction."""

from __future__ import annotations

import pytest
from alembic import command
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import subledger_line
from erev_api.domain.journals import subledger
from erev_api.enums import ControlResult
from sqlalchemy import exc, func, text, update
from support.db import TestDatabase, alembic_config, fresh_head
from support.factories import tenant_factory, tenant_id_of
from support.legacy_ledger_0150 import insert_legacy_ledger
from support.rows import insert_ledger_rows
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_server_time_migration_preserves_populated_ledger(
    test_database: TestDatabase, keyring: KeyRing, direction: str
) -> None:
    fresh_head()
    try:
        command.downgrade(alembic_config(), "0151")
        if direction == "upgrade":
            command.downgrade(alembic_config(), "0150")
        test_database.app_engine.dispose()
        test_database.owner_engine.dispose()
        tenant = tenant_id_of(tenant_factory(keyring=keyring))
        context = DbContext(tenant, None, "*")
        with tenant_session(context) as session:
            if direction == "upgrade":
                insert_legacy_ledger(session, tenant)
            else:
                insert_ledger_rows(session, tenant)
            before = session.execute(text("SELECT * FROM erev.subledger_line ORDER BY id")).all()
            seals = session.execute(text("SELECT * FROM erev.subledger_posting_seal")).all()
        with pytest.raises(exc.DBAPIError) as refused:
            if direction == "upgrade":
                command.upgrade(alembic_config(), "head")
            else:
                command.downgrade(alembic_config(), "0150")
        assert getattr(refused.value.orig, "sqlstate", None) == "23514"
        assert "ck_subledger_line__0151_empty" in str(refused.value.orig)
        with test_database.owner_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM erev.alembic_version")) == (
                "0150" if direction == "upgrade" else "0151"
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint "
                        "WHERE conname='ck_subledger_line__0151_empty'"
                    )
                )
                == 0
            )
        with tenant_session(context, read_only=True) as session:
            after = session.execute(text("SELECT * FROM erev.subledger_line ORDER BY id")).all()
            assert after == before
            assert session.execute(text("SELECT * FROM erev.subledger_posting_seal")).all() == seals
            assert ("recorded_server_at" in after[0]._mapping) == (direction == "downgrade")
    finally:
        fresh_head()
        test_database.app_engine.dispose()
        test_database.owner_engine.dispose()


def test_server_timestamp_is_sealed_and_immutable(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant, None, "*")
    statement = update(subledger_line).values(recorded_server_at=func.clock_timestamp())
    with tenant_session(context) as session:
        insert_ledger_rows(session, tenant)
        assert _fails(session, statement)[0] == "42501"
        assert (
            subledger.verify_ledger_chain(session, book_code="ASC606").result is ControlResult.PASS
        )
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(
                "ALTER TABLE erev.subledger_line NO FORCE ROW LEVEL SECURITY"
            )
            assert "EREV-IMM-001" in _owner_failure(connection, statement)
        finally:
            transaction.rollback()
    with tenant_session(context, read_only=True) as session:
        assert (
            subledger.verify_ledger_chain(session, book_code="ASC606").result is ControlResult.PASS
        )
