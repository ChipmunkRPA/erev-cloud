"""The connection pool the worker's Procrastinate works on (05 TXN-03 rev 1.193; dev-guide
DG-KRN-DB-11, DG-ENV-12).

Every connection of the pool starts with the session settings of ``db.session.connect_options``
— the string the engines send — and passes the role guard of the app role. The builder stands
apart from ``erev_api.worker`` so that the pool can be built, and read by a test, without
importing the handler modules the worker registers. How many connections the pool holds is
the worker's to say (05 §2.7): it passes the sizes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import psycopg_pool
from psycopg import AsyncConnection
from sqlalchemy import make_url

from erev_api.db.session import (
    APP_ROLE,
    ROLE_QUERY,
    RoleGuardError,
    connect_options,
    database_of,
    role_guard_failure,
)

__all__ = ["worker_pool"]


def _configure_connection(database: str) -> Callable[[AsyncConnection[Any]], Awaitable[None]]:
    """The DG-ENV-12 role guard for every connection of the worker's Procrastinate pool."""

    async def configure(connection: AsyncConnection[Any]) -> None:
        cursor = await connection.execute(ROLE_QUERY)
        row = await cursor.fetchone()
        await connection.rollback()
        failure = role_guard_failure(APP_ROLE, database, row)
        if failure is not None:
            await connection.close()
            raise RoleGuardError(failure)

    return configure


def worker_pool(
    url: str, *, min_size: int, max_size: int
) -> psycopg_pool.AsyncConnectionPool[AsyncConnection[Any]]:
    """The pool Procrastinate works on, not yet open, on the app role's ``url``. Every
    connection of it starts with the TXN-03 settings of ``connect_options`` and passes the
    DG-ENV-12 role guard; the worker gives the sizes."""
    return psycopg_pool.AsyncConnectionPool(
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False),
        kwargs={"options": connect_options("worker")},
        configure=_configure_connection(database_of(url)),
        min_size=min_size,
        max_size=max_size,
        open=False,
        check=psycopg_pool.AsyncConnectionPool.check_connection,
    )
