"""Item MIGRATION-STATEMENT-TIMEOUT-1 on PostgreSQL (05 TXN-03 rev 1.199; dev-guide DG-MIG-01 rev
1.264): what the server answers.

``tests/unit/test_migration_timeouts.py`` reads the ``options`` the driver is handed. This module
reads the settings on the connections themselves: on Alembic's own, as the product's ``env.py``
opens it for a command, and on the session's engines, which serve every test body.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from alembic import command
from erev_api.config import settings_override
from erev_api.db import session as db_session
from erev_api.db.session import identity_session
from sqlalchemy import Engine, event, text
from support.db import TestDatabase, alembic_config

pytestmark = pytest.mark.pg

SETTINGS = (
    "application_name",
    "statement_timeout",
    "lock_timeout",
    "idle_in_transaction_session_timeout",
)
READ = "SELECT " + ", ".join(f"current_setting('{name}')" for name in SETTINGS)
BOUNDS = text("SELECT current_setting('statement_timeout'), current_setting('lock_timeout')")


def _alembic_reads() -> list[tuple[str, ...]]:
    """Run ``alembic current`` — ``env.py`` whole, no revision — and return what each connection
    of the engine ``env.py`` built answered to ``READ`` when it was opened."""
    seen: list[tuple[str, ...]] = []
    product = db_session.build_engine

    def reading(url: str, **keywords: Any) -> Engine:
        engine = product(url, **keywords)

        @event.listens_for(engine, "connect")
        def read(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(READ)
                seen.append(tuple(str(value) for value in cursor.fetchone()))
            finally:
                cursor.close()
                dbapi_connection.rollback()

        return engine

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db_session, "build_engine", reading)
        command.current(alembic_config(stdout=io.StringIO()))
    return seen


def test_alembics_connection_answers_the_migrations_statement_timeout_and_the_requests_lock_timeout(
    test_database: TestDatabase,
) -> None:
    """The one connection ``env.py`` opens answers 30 minutes for a statement — the setting's
    default — and the 10 s and 1 min of every connection for a lock and for an idle transaction.
    Raised for one run, the statement timeout follows the setting and the lock timeout stays."""
    assert _alembic_reads() == [("erev-migrate", "30min", "10s", "1min")]
    with settings_override(migration_statement_timeout_seconds=7200):
        assert _alembic_reads() == [("erev-migrate", "2h", "10s", "1min")]
    assert _alembic_reads() == [("erev-migrate", "30min", "10s", "1min")]


def test_the_sessions_engines_answer_the_requests_statement_timeout(
    test_database: TestDatabase,
) -> None:
    """This session's schema was built by a migration under its own statement timeout; the
    engines every test body uses answer the request's 30 s (05 TXN-03) — the owner engine, and
    the app engine in a transaction that sets no timeout of its own."""
    with test_database.owner_engine.connect() as connection:
        assert tuple(connection.execute(BOUNDS).one()) == ("30s", "10s")
    with identity_session(request_id="req-migration-timeouts") as session:
        assert tuple(session.execute(BOUNDS).one()) == ("30s", "10s")
