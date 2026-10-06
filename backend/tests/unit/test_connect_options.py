"""05 TXN-03 rev 1.193 (dev-guide DG-KRN-DB-11 rev 1.255; the supervisor's ruling of 2026-10-02):
the session settings every connection of the application starts with are one string,
``db.session.connect_options``, stated to the letter in 05; ``jit=off`` is one of them; and the
application opens a PostgreSQL connection in three places only — the engines of ``build_engine``
and the worker's Procrastinate pool (``jobs.pool``), both with that string, and the recovery
preflight, which asks a server who it is.

No database: ``tests/pg/test_session_guards.py`` reads the setting on a connection of each road.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import erev_api
from erev_api.config import get_settings
from erev_api.db import session as db_session
from erev_api.jobs.pool import worker_pool
from support.guides import ROOT

PACKAGE = Path(erev_api.__file__).parent
# Where the application opens a PostgreSQL connection, and the keyword that carries the options.
# The preflight of a recovery reads one row of the server's identity from each URL it is given
# (``SERVER_IDENTITY_SQL``) and does none of the application's work: it sends no options.
OPENERS = {
    ("db/session.py", "create_engine"): "connect_args",
    ("jobs/pool.py", "psycopg_pool.AsyncConnectionPool"): "kwargs",
    ("controls/recovery_preflight.py", "psycopg.connect"): None,
}


def _documented() -> str:
    architecture = (ROOT / "docs" / "05-ARCHITECTURE.md").read_text(encoding="utf-8")
    (row,) = [line for line in architecture.splitlines() if line.startswith("| TXN-03 |")]
    found = re.search(r"through libpq `options`: `(-c [^`]+)`", row)
    assert found is not None, row[:200]
    return found.group(1)


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _opens_a_connection(name: str) -> bool:
    return (
        name.split(".")[-1] in {"create_engine", "create_async_engine"}
        or (name.startswith("psycopg_pool.") and name.endswith("Pool"))
        or (name.startswith("psycopg.") and name.endswith(".connect"))
        or name in {"psycopg.connect", "AsyncConnection.connect"}
    )


def _openers() -> dict[tuple[str, str], ast.Call]:
    found: dict[tuple[str, str], ast.Call] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        if relative.startswith("db/migrations/versions/"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and _opens_a_connection(_dotted(node.func)):
                assert (relative, _dotted(node.func)) not in found, (relative, "opens twice")
                found[(relative, _dotted(node.func))] = node
    return found


def test_txn_03_the_options_are_the_documents_to_the_letter() -> None:
    documented = _documented()
    assert "<component>" in documented
    for component in ("api", "worker", "migrate", "cli"):
        assert db_session.connect_options(component) == documented.replace("<component>", component)


def test_txn_03_jit_is_off_and_set_once() -> None:
    options = db_session.connect_options("api").removeprefix("-c ").split(" -c ")
    assert [option for option in options if option.split("=")[0] == "jit"] == ["jit=off"]


def test_dg_krn_db_11_the_application_opens_a_connection_in_three_places() -> None:
    """A new place that opens a PostgreSQL connection is a decision: it sends
    ``connect_options`` or it is named here with its reason."""
    found = _openers()
    assert set(found) == set(OPENERS)
    for site, keyword in OPENERS.items():
        if keyword is None:
            continue
        (carrier,) = [word.value for word in found[site].keywords if word.arg == keyword]
        assert isinstance(carrier, ast.Dict), site
        ((key, value),) = zip(carrier.keys, carrier.values, strict=True)
        assert isinstance(key, ast.Constant) and key.value == "options", site
        assert isinstance(value, ast.Call) and _dotted(value.func) == "connect_options", site


def test_dg_krn_db_11_the_workers_pool_is_built_with_the_options_of_its_component() -> None:
    pool = worker_pool(get_settings().app_database_url(), min_size=1, max_size=2)
    assert pool.kwargs == {"options": db_session.connect_options("worker")}
    assert pool.closed, "the pool is handed over not yet open"
