"""Test database support (docs/dev-guide.md §9.3 DG-TST-10, DG-TST-11; §2.4 DG-ENV-13)."""

from __future__ import annotations

import functools
import io
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from erev_api.clock import FrozenClock
from erev_api.config import get_settings
from erev_api.db import migration_ops as ops
from erev_api.db.session import (
    OWNER_ROLE,
    DestructiveResetRefused,
    app_engine,
    build_engine,
    database_of,
    owner_engine,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

# DG-TST-11: "erevTEST" as a bigint, held by the session fixture on a dedicated owner connection.
TEST_DB_LOCK_KEY: Final = 0x6572657654455354
ALEMBIC_INI: Final = Path(__file__).resolve().parents[2] / "alembic.ini"
# DG-ENV-13: test support resets only these databases (make db-reset owns `erev`).
_RESETTABLE: Final = re.compile(r"^(erev_test|erev_e2e|erev_rv_[a-z0-9_]+)$")
# The PostgreSQL server of this machine is shared by every suite that runs on it and has ONE lock
# table for all of its databases (``max_locks_per_transaction`` 64 x ``max_connections`` 100
# entries; DG-ENV-14 forbids changing server settings). A transaction that drops or creates a few
# hundred relations needs as many entries, so a reset beside other suites used to die with
# SQLSTATE 53200 "out of shared memory" and every test of the session errored at setup (supervisor
# note of 2026-09-29: eleven lanes plus another product's suites held 5,300 of the 6,400 entries).
# Two measures, neither of which changes what a session starts from (an empty schema at head):
# ordinary tables are dropped a few per transaction before the schema itself, as the partitions
# already are (L3-1-Q-24), and a reset or upgrade refused for that one cause waits and starts
# over.
_LOCK_TABLE_FULL: Final = "53200"
_TABLE_BATCH: Final = 10
_FRESH_ATTEMPTS: Final = 30
_FRESH_WAIT_SECONDS: Final = 10.0
_ORDINARY_TABLES: Final = text(
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND c.relkind = 'r' ORDER BY c.relname LIMIT :batch"
)


@dataclass(frozen=True, slots=True)
class TestDatabase:
    """What the session fixture yields (DG-TST-10). It keeps no engine: ``app_engine`` and
    ``owner_engine`` answer the engines of the process's factories at each use (dev-guide rev
    1.269; register index 249). A test that reaches ``dispose_engines()`` — the CLI's switch
    of environment, the end of ``worker.main`` — makes the factories build new engines; a
    value that kept the first ones left every module after it disposing a pool the product
    no longer used, and a connection opened before a schema rebuild then answered ``cache
    lookup failed for type <oid>`` in whatever ran next."""

    __test__ = False  # not a test class

    clock: FrozenClock

    @property
    def app_engine(self) -> Engine:
        return app_engine()

    @property
    def owner_engine(self) -> Engine:
        return owner_engine()


def _refuse_unless_resettable(database: str) -> None:
    if not _RESETTABLE.fullmatch(database):
        raise DestructiveResetRefused(
            f"schema reset refused on database {database!r}; allowed: erev_test, erev_e2e, "
            "erev_rv_* (DG-ENV-13)"
        )


def alembic_config(stdout: io.StringIO | None = None) -> Config:
    """Alembic configuration of ``backend/alembic.ini``; env.py reads the owner URL (DG-MIG-01)."""
    if stdout is None:
        return Config(str(ALEMBIC_INI))
    return Config(str(ALEMBIC_INI), stdout=stdout)


def reset_schema(owner_url: str) -> None:
    """Drop schema ``erev`` with CASCADE and the Procrastinate objects of ``public`` as
    ``erev_owner`` (DG-TST-10; DG-MIG-09); migrations recreate both.

    The URL's database is checked before any engine exists, and ``current_database()`` again
    before the drop.
    """
    _refuse_unless_resettable(database_of(owner_url))
    engine = build_engine(owner_url, role=OWNER_ROLE, component="tests")
    try:
        with engine.connect() as connection:
            _refuse_unless_resettable(
                connection.execute(text("SELECT current_database()")).scalar_one()
            )
        # The monthly partitions go first, one partitioned table per transaction (L3-1-Q-24).
        ops.drop_partitioned_tables(engine)
        # Then the ordinary tables, a few per transaction (the shared lock table, see above).
        _drop_tables_in_batches(engine)
        with engine.begin() as connection:
            _refuse_unless_resettable(
                connection.execute(text("SELECT current_database()")).scalar_one()
            )
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS erev CASCADE")
            with ops.bound_to(connection):
                ops.drop_procrastinate_schema()
    finally:
        engine.dispose()


def lock_table_full(error: BaseException) -> bool:
    """True when ``error`` is PostgreSQL's SQLSTATE 53200 (the server-wide lock table is full)."""
    origin = getattr(error, "orig", error)
    return getattr(origin, "sqlstate", None) == _LOCK_TABLE_FULL


def _drop_tables_in_batches(engine: Engine) -> None:
    """Drop the ordinary tables of schema ``erev``, ``_TABLE_BATCH`` per transaction, so that no
    transaction asks the shared lock table for more than a few hundred entries. CASCADE removes
    the foreign keys that point at a dropped table; ``DROP SCHEMA`` then removes what is left
    (types, domains, functions, sequences)."""
    while True:
        with engine.begin() as connection:
            names = [
                str(name)
                for (name,) in connection.execute(_ORDINARY_TABLES, {"batch": _TABLE_BATCH})
            ]
            for name in names:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {ops.qualified(name)} CASCADE")
        if not names:
            return


def _waiting_out_a_full_lock_table(function: Callable[[], None]) -> Callable[[], None]:
    """Run ``function`` again, from its start, while PostgreSQL refuses it because the server's
    shared lock table is full (SQLSTATE 53200); every other error raises at once. ``function``
    must be restartable: ``fresh_head`` resets the schema first, so a partly migrated schema
    never survives an attempt."""

    @functools.wraps(function)
    def waiting() -> None:
        for attempt in range(1, _FRESH_ATTEMPTS + 1):
            try:
                function()
                return
            except OperationalError as error:
                if not lock_table_full(error) or attempt == _FRESH_ATTEMPTS:
                    raise
                time.sleep(_FRESH_WAIT_SECONDS)

    return waiting


@_waiting_out_a_full_lock_table
def fresh_head() -> None:
    """The migration walks' FIRST step (DG-MIG-05: "reset schema, ``upgrade head``, …" — performed
    by the walk itself, not left to the DG-TST-10 session fixture): drop the schema and re-create
    head, so the walk descends from a DATA-FREE database. Earlier tests of the session commit
    rows (DG-TST-13), and a row carrying an enum label that a later revision added makes that
    revision's downgrade refuse — DG-MIG-06, by design (integrated batch #9 on 8b304854:
    ``approval_request.subject_type = 'MIGRATION_SSP_REPLAY'`` blocked 0071's downgrade and every
    later pg test cascaded on the part-migrated schema). Safe by construction: a walk to base
    drops every table anyway, so resetting first removes no data a later test could rely on.

    The DG-TST-10 session fixture starts through this function too. A reset or upgrade refused
    because the server's shared lock table is full (SQLSTATE 53200) is waited out and started
    over from the reset; every other error raises at once.
    """
    reset_schema(get_settings().owner_database_url())
    command.upgrade(alembic_config(), "head")
