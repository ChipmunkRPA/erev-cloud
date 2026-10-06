"""``erev db reset``: which database is a development database (dev-guide DG-ENV-13 rev 1.200,
DG-MK-db-reset; supervisor ruling R-120 (i)).

The rule is a function of four things - the environment's name, the database's name, the name the
server answers and the tenants without the demo marker - and the command asks them in that order
and drops nothing before the last one holds. The real command drops a database, so it is driven
here over stand-ins of the engine and of the count; the count itself is measured on the database
in ``tests/domain/platform/test_db_reset_tenants.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from erev_api import cli
from erev_api.config import ALLOWED_DATABASE, Environment
from erev_api.controls import reset
from typer.testing import CliRunner

LANE = "erev_rv_l2_dev"


def test_dg_env_13_the_environment_and_the_name_of_a_development_database() -> None:
    assert reset.refused_before_connecting(Environment.DEV, "erev") is None
    assert reset.refused_before_connecting(Environment.DEV, LANE) is None
    for env in (Environment.TEST, Environment.E2E, Environment.PRODUCTION):
        refusal = reset.refused_before_connecting(env, "erev")
        assert refusal == (
            f"erev db reset runs only with EREV_ENV=dev; this environment is {env.value}"
        )
    # The databases their gates rebuild, and names outside the DG-ENV-13 allow-list.
    for database in ("erev_test", "erev_e2e", "erev_rv_", "erev_prod", "postgres", "EREV"):
        refusal = reset.refused_before_connecting(Environment.DEV, database)
        assert refusal is not None and refusal.endswith(f"the environment names {database}")
    # What the command may reset is the allow-list without the two gate databases.
    for database in ("erev", "erev_test", "erev_e2e", LANE, "erev_rv_reset_probe"):
        assert ALLOWED_DATABASE.fullmatch(database)
        assert bool(reset.RESETTABLE.fullmatch(database)) is (
            database not in ("erev_test", "erev_e2e")
        )


def test_dg_env_13_the_server_and_the_tenants_of_a_development_database() -> None:
    assert reset.refused_by_server(LANE, LANE) is None
    assert reset.refused_by_server(LANE, "erev") == (
        f"refusing to reset: the server answers database erev, not {LANE}"
    )
    assert reset.refused_for_tenants(LANE, 0) is None
    assert reset.refused_for_tenants(LANE, 2) == (
        f"refusing to reset {LANE}: 2 tenant(s) carry no demo marker, so it is not a "
        "development database"
    )


class _Engine:
    """The owner's engine as the command uses it: one read connection, then the drops."""

    def __init__(self, answered: str, statements: list[str]) -> None:
        self.answered = answered
        self.statements = statements

    @contextmanager
    def connect(self) -> Iterator[Any]:
        yield SimpleNamespace(
            execute=lambda statement: SimpleNamespace(scalar_one=lambda: self.answered)
        )

    @contextmanager
    def begin(self) -> Iterator[Any]:
        yield SimpleNamespace(exec_driver_sql=self.statements.append)

    def dispose(self) -> None:
        self.statements.append("disposed")


@contextmanager
def _bound(connection: Any) -> Iterator[None]:
    yield


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    env: Environment = Environment.DEV,
    database: str = LANE,
    answered: str = LANE,
    table: bool = True,
    unmarked: int | Exception = 0,
) -> tuple[int, str, list[str]]:
    """``erev db reset`` over stand-ins; returns its exit code, its output and what it ran."""
    from erev_api.auth import keyring
    from erev_api.db import migration_ops, session

    ran: list[str] = []
    settings = SimpleNamespace(
        env=env, database_name=lambda: database, owner_database_url=lambda: "owner-url"
    )

    def count(**_: Any) -> int:
        ran.append("counted")
        if isinstance(unmarked, Exception):
            raise unmarked
        return unmarked

    monkeypatch.setattr(cli, "_cli_settings", lambda: settings)
    monkeypatch.setattr(session, "build_engine", lambda *_, **__: _Engine(answered, ran))
    monkeypatch.setattr(keyring, "build_keyring", lambda _: object())
    monkeypatch.setattr(reset, "tenant_table_exists", lambda _: table)
    monkeypatch.setattr(reset, "unmarked_tenants", count)
    monkeypatch.setattr(
        migration_ops, "drop_partitioned_tables", lambda _: ran.append("partitions dropped")
    )
    monkeypatch.setattr(migration_ops, "bound_to", _bound)
    monkeypatch.setattr(
        migration_ops, "drop_procrastinate_schema", lambda: ran.append("procrastinate dropped")
    )
    result = CliRunner().invoke(cli.app, ["db", "reset"])
    return result.exit_code, result.output.strip(), ran


DROPPED = [
    "partitions dropped",
    "DROP SCHEMA IF EXISTS erev CASCADE",
    "procrastinate dropped",
    "disposed",
]


def test_dg_mk_db_reset_resets_the_development_database_the_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lane's own development database is an ``erev_rv_*`` name; the command admitted ``erev``
    alone, so a lane could not reseed its own. Fail-first: exit 1, "erev db reset runs only with
    EREV_ENV=dev on database erev"."""
    for database in ("erev", LANE):
        code, output, ran = _run(monkeypatch, database=database, answered=database)
        assert (code, ran) == (0, ["counted", *DROPPED]), output
        assert output == f"schema erev and the Procrastinate objects dropped in {database}"
    # A database without the tenant table holds no tenant: nothing is counted, and it is reset.
    code, output, ran = _run(monkeypatch, table=False, unmarked=RuntimeError("never asked"))
    assert (code, ran) == (0, DROPPED), output


@pytest.mark.parametrize(
    ("case", "arguments", "says", "ran"),
    [
        ("another environment", {"env": Environment.TEST}, "runs only with EREV_ENV=dev", []),
        ("a gate's database", {"database": "erev_test"}, "the environment names erev_test", []),
        (
            "another database on the server",
            {"answered": "erev"},
            f"the server answers database erev, not {LANE}",
            ["disposed"],
        ),
        (
            "a tenant without the demo marker",
            {"unmarked": 1},
            "1 tenant(s) carry no demo marker",
            ["counted", "disposed"],
        ),
        (
            "tenants that cannot be counted",
            {"unmarked": RuntimeError("a message that names customer Pellworth")},
            f"refusing to reset {LANE}: its tenants could not be counted (RuntimeError)",
            ["counted", "disposed"],
        ),
    ],
)
def test_dg_mk_db_reset_names_what_does_not_hold_and_drops_nothing(
    case: str,
    arguments: dict[str, Any],
    says: str,
    ran: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, output, did = _run(monkeypatch, **arguments)
    assert (code, did) == (1, ran), (case, output)
    assert says in output and "Pellworth" not in output, (case, output)
