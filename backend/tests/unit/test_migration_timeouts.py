"""Item MIGRATION-STATEMENT-TIMEOUT-1 (05 TXN-03 and CFG-29 rev 1.199; dev-guide DG-MIG-01 rev
1.264; the supervisor's ruling of 2026-10-02): a migration's connection carries a statement
timeout of its own — ``Settings.migration_statement_timeout_seconds``, 30 minutes by default — and
the 10 s lock timeout of every connection. No other connection carries it, and no revision sets
either timeout: a revision's statement may run long, its wait for a lock may not.

Until this item every road of a migration — ``erev migrate``, ``make migrate``, the migration
job, the schema build of a test session — ran under the request's 30 s, which the connect options
of every engine carried (``erev_api.db.session.connect_options``). A foreign key added over a
partitioned table checks every partition in one statement; on a loaded server two such statements
of an EMPTY schema were cancelled.

No test of this module reaches a server. The driver's ``connect`` is replaced by a recorder that
keeps the ``options`` it is handed and raises, and both URLs name a port nobody listens on, so a
test that lost its recorder could not migrate a database either. What PostgreSQL itself answers
on those connections is read in ``tests/pg/test_migration_timeouts_pg.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import erev_api
import psycopg
import pytest
from alembic import command
from alembic.script import ScriptDirectory
from erev_api.config import settings_override
from erev_api.db import session as db_session
from erev_api.db.session import APP_ROLE, OWNER_ROLE, build_engine
from sqlalchemy import Engine
from support.db import alembic_config

# Databases the allow-list accepts (DG-ENV-13), on a port nobody listens on.
OWNER_URL = "postgresql+psycopg://erev_owner:placeholder-credential@127.0.0.1:1/erev_test"
APP_URL = "postgresql+psycopg://erev_app:placeholder-credential@127.0.0.1:1/erev_test"
REQUEST = "30000"  # 05 TXN-03: every connection but a migration's
MIGRATION = "1800000"  # 05 CFG-29: 1800 s unless configured
LOCK = "10000"
IDLE = "60000"
DB = Path(erev_api.__file__).parent / "db"


class Reached(Exception):
    """The driver was asked for a connection."""


def _settings(options: str) -> dict[str, str]:
    """The session settings a libpq ``options`` string leaves in force: its ``-c name=value``
    items in the order given, a later one replacing an earlier one of its name, as the server
    applies them."""
    items = [item.strip() for item in f" {options}".split(" -c ") if item.strip()]
    return dict(item.split("=", 1) for item in items)


@pytest.fixture
def handed(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """The ``options`` of every connection the driver is asked for, in order. Each request ends
    in ``Reached``: no connection exists afterwards."""
    seen: list[str] = []

    def connect(*_: Any, **parameters: Any) -> None:
        seen.append(str(parameters["options"]))
        raise Reached

    monkeypatch.setattr(psycopg, "connect", connect)
    with settings_override(test_db_owner_url=OWNER_URL, test_db_app_url=APP_URL):
        yield seen


def _asked(engine: Engine, handed: list[str]) -> dict[str, str]:
    """The session settings ``engine`` asks the driver for when it opens a connection now."""
    with pytest.raises(Reached):
        engine.connect()
    return _settings(handed[-1])


def test_a_migrations_connection_carries_its_own_statement_timeout_and_the_requests_lock_timeout(
    handed: list[str],
) -> None:
    """``migration_engine``: the statement timeout is the setting's, in milliseconds, set once;
    the lock timeout, the idle bound and everything else are those of every connection."""
    asked = _asked(db_session.migration_engine(), handed)
    assert asked == {
        "TimeZone": "UTC",
        "search_path": "erev,public",
        "statement_timeout": MIGRATION,
        "idle_in_transaction_session_timeout": IDLE,
        "lock_timeout": LOCK,
        # 05 TXN-03 rev 1.193 (the join with lane API-GAPS's head): every connection, a
        # migration's among them, turns JIT off.
        "jit": "off",
        "application_name": "erev-migrate",
    }
    assert handed[-1].count("statement_timeout") == handed[-1].count("lock_timeout") == 1
    # the options differ from a request's in that one value
    assert handed[-1] == db_session.connect_options("migrate").replace(
        f"statement_timeout={REQUEST}", f"statement_timeout={MIGRATION}"
    )


def test_alembics_environment_opens_that_connection(handed: list[str]) -> None:
    """The road every migration takes: an Alembic command runs the product's ``env.py``, which
    builds its engine through ``migration_engine`` and asks for its one connection — under the
    migration's statement timeout and the request's lock timeout. ``erev migrate``, ``make
    migrate`` and the schema build of a test session all run this command."""
    with pytest.raises(Reached):
        command.upgrade(alembic_config(), "head")
    (options,) = handed
    asked = _settings(options)
    assert (asked["application_name"], asked["statement_timeout"], asked["lock_timeout"]) == (
        "erev-migrate",
        MIGRATION,
        LOCK,
    )


def test_no_other_connection_carries_a_migrations_statement_timeout(handed: list[str]) -> None:
    """An application connection keeps the request's 30 s: the app engine and the owner engine
    as the process builds them, the engines the CLI and the test schema reset build for
    themselves, and the options of the worker's own pool."""
    engines = {
        "app_engine": db_session.app_engine.__wrapped__(),  # as built, outside the cache
        "owner_engine": db_session.owner_engine.__wrapped__(),
        "erev db reset, erev doctor --analyze": build_engine(
            OWNER_URL, role=OWNER_ROLE, component="cli"
        ),
        "the test schema reset": build_engine(OWNER_URL, role=OWNER_ROLE, component="tests"),
        "an engine built with no component": build_engine(APP_URL, role=APP_ROLE),
    }
    asked = {name: _asked(engine, handed) for name, engine in engines.items()}
    assert {name: found["statement_timeout"] for name, found in asked.items()} == dict.fromkeys(
        engines, REQUEST
    )
    assert {found["lock_timeout"] for found in asked.values()} == {LOCK}
    worker = _settings(db_session.connect_options("worker"))
    assert (worker["statement_timeout"], worker["lock_timeout"]) == (REQUEST, LOCK)
    assert len(handed) == len(engines)


def test_the_setting_moves_the_migrations_statement_timeout_and_nothing_else(
    handed: list[str],
) -> None:
    """An operator raises the bound for one run through
    ``EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS``: the migration's statement timeout follows, its
    lock timeout does not, and an application connection keeps the request's values."""
    with settings_override(migration_statement_timeout_seconds=7200):
        migration = _asked(db_session.migration_engine(), handed)
        application = _asked(db_session.app_engine.__wrapped__(), handed)
    assert (migration["statement_timeout"], migration["lock_timeout"]) == ("7200000", LOCK)
    assert (application["statement_timeout"], application["lock_timeout"]) == (REQUEST, LOCK)
    assert _asked(db_session.migration_engine(), handed)["statement_timeout"] == MIGRATION


def test_no_revision_and_no_migration_helper_sets_a_timeout() -> None:
    """DG-MIG-01 rev 1.264: the two bounds of a migration are its connection's. A revision that
    set ``lock_timeout`` would wait for a table with the requests queued behind it, and one that
    set ``statement_timeout`` would take the operator's setting away: neither word occurs in
    Alembic's environment, in a revision or in ``migration_ops``."""
    revisions = sorted((DB / "migrations" / "versions").glob("*.py"))
    # every revision Alembic knows is one of the files read
    known = list(ScriptDirectory.from_config(alembic_config()).walk_revisions())
    assert len(revisions) == len(known) > 0
    sources = [DB / "migrations" / "env.py", DB / "migration_ops.py", *revisions]
    named = [
        f"{path.name}: {word}"
        for path in sources
        for word in ("statement_timeout", "lock_timeout")
        if word in path.read_text(encoding="utf-8").lower()
    ]
    assert named == []
