"""KRN-DB guards on PostgreSQL (dev-guide §5.2, §2.4 DG-ENV-12, 13; §9.3; BUILD_SPEC FND-5)."""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Callable, Sequence
from typing import Any, Final
from uuid import UUID

import pytest
import support.db as support_db
from erev_api.config import get_settings
from erev_api.db import session as session_module
from erev_api.db.session import (
    APP_ROLE,
    OWNER_ROLE,
    DbContext,
    DestructiveResetRefused,
    RoleGuardError,
    TenantContextMissing,
    build_engine,
    every_entity_scope,
    identity_session,
    migration_engine,
    system_entity_scope,
    system_user,
    tenant_session,
)
from erev_api.jobs.pool import worker_pool
from erev_api.problems import unhandled_error_response
from sqlalchemy import exc, text
from sqlalchemy.orm import Session
from starlette.requests import Request
from support.db import TEST_DB_LOCK_KEY, TestDatabase, reset_schema

pytestmark = pytest.mark.pg

TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
USER = UUID("0191e0a0-0000-7000-8000-000000000101")
E1 = UUID("0191e0a0-0000-7000-8000-00000000000a")
E2 = UUID("0191e0a0-0000-7000-8000-00000000000b")
ALL_ENTITIES = DbContext(tenant_id=TENANT, user_id=None, entity_scope="*")

ROLE_QUERY = text(
    "SELECT current_user, r.rolsuper, r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user"
)
# 05 TXN-03 rev 1.193: the value a connection holds, and where it came from.
JIT_SETTING: Final = "SELECT setting, source FROM pg_settings WHERE name = 'jit'"
# Statements whose driver errors would quote or carry the bound values (DG-LOG-03).
DB_ERROR_STATEMENTS = (
    ("SELECT CAST(:amount AS text), 1/0", {"amount": "146000.00"}, "22012"),
    ("SELECT CAST(:v AS numeric)", {"v": "USD 98765.43"}, "22P02"),
)


class Boom(Exception):
    pass


def _pair(row: Sequence[Any]) -> tuple[str, str]:
    return (str(row[0]), str(row[1]))


def test_dg_env_12_app_role_guard(test_database: TestDatabase) -> None:
    with tenant_session(ALL_ENTITIES) as session:
        assert tuple(session.execute(ROLE_QUERY).one()) == (APP_ROLE, False, False)

    settings = get_settings()
    misbuilt = [
        (
            settings.owner_database_url(),
            APP_ROLE,
            "role guard: expected erev_app, found erev_owner",
        ),
        (
            settings.app_database_url(),
            OWNER_ROLE,
            "role guard: expected erev_owner, found erev_app",
        ),
    ]
    for url, role, message in misbuilt:
        engine = build_engine(url, role=role, component="tests")
        try:
            with pytest.raises(RoleGuardError) as excinfo:
                engine.connect()
            assert str(excinfo.value) == message
            # The guard runs on every new connection, not only the first.
            with pytest.raises(RoleGuardError):
                engine.connect()
        finally:
            engine.dispose()


def test_dg_env_13_connected_database_matches_url(
    test_database: TestDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    url = settings.app_database_url()
    connected = settings.database_name()
    with monkeypatch.context() as patch:
        patch.setattr(session_module, "database_of", lambda _: "erev_rv_other")
        mismatched = build_engine(url, role=APP_ROLE, component="tests")
    try:
        with pytest.raises(RoleGuardError) as excinfo:
            mismatched.connect()
        assert "erev_rv_other" in str(excinfo.value)
        assert connected in str(excinfo.value)
    finally:
        mismatched.dispose()

    engine = build_engine(url, role=APP_ROLE, component="tests")
    try:
        with engine.connect() as connection:
            assert not connection.closed
    finally:
        engine.dispose()


def test_dg_log_03_db_error_logs_no_bound_parameters(
    test_database: TestDatabase, log_stream: io.StringIO
) -> None:
    states = []
    for statement, parameters, state in DB_ERROR_STATEMENTS:
        with (
            pytest.raises(exc.DBAPIError) as caught,
            identity_session(request_id="req-dg-log-03") as session,
        ):
            session.execute(text(statement), parameters)
        states.append(state)
        request = Request(
            {"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}
        )
        response = unhandled_error_response(request, caught.value)
        assert response.status_code == 500
        assert json.loads(bytes(response.body))["type"] == "about:blank"

    output = log_stream.getvalue()
    assert "146000.00" not in output
    assert "98765.43" not in output
    lines = [json.loads(line) for line in output.splitlines() if line.strip()]
    errors = [line for line in lines if line["event"] == "http.unhandled_error"]
    assert [line["sqlstate"] for line in errors] == states
    for line in errors:
        assert line["error_class"] == "sqlalchemy.exc.DataError"
        assert str(line["driver_error_class"]).startswith("psycopg.errors.")
        assert "constraint_name" in line
        trace = str(line["exception"])
        assert "Traceback (most recent call last):" in trace
        assert 'File "' in trace
        assert trace.endswith("sqlalchemy.exc.DataError: [message hidden]\n")

    engine = build_engine(get_settings().app_database_url(), role=APP_ROLE, component="tests")
    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


def test_krn_db_04_context_free_sql_refused(test_database: TestDatabase) -> None:
    with test_database.app_engine.connect() as connection, pytest.raises(TenantContextMissing):
        connection.execute(text("SELECT 1"))
    with Session(test_database.app_engine) as session, pytest.raises(TenantContextMissing):
        session.execute(text("SELECT 1"))


def test_krn_db_04_context_ends_with_the_transaction(test_database: TestDatabase) -> None:
    with tenant_session(ALL_ENTITIES) as session:
        session.execute(text("SELECT 1"))
        session.commit()
        with pytest.raises(TenantContextMissing):
            session.execute(text("SELECT 1"))


def test_krn_db_01_tenant_session_sets_transaction_local_settings(
    test_database: TestDatabase,
) -> None:
    ctx = DbContext(tenant_id=TENANT, user_id=None, entity_scope=(E2, E1))
    with tenant_session(ctx) as session:
        row = session.execute(
            text(
                "SELECT current_setting('app.tenant_id'), current_setting('app.user_id'), "
                "current_setting('app.entity_scope'), current_setting('statement_timeout'), "
                "current_setting('lock_timeout'), pg_backend_pid()"
            )
        ).one()
    assert tuple(row[:5]) == (str(TENANT), "", f"{E1},{E2}", "1min", "10s")

    # The pool is LIFO, so the following session reuses the same backend; nothing survives.
    with identity_session(request_id="req-following") as session:
        following = session.execute(
            text("SELECT coalesce(current_setting('app.tenant_id', true), ''), pg_backend_pid()")
        ).one()
    assert following[1] == row[5]
    assert following[0] == ""


def test_txn_03_every_engine_of_the_application_starts_with_jit_off(
    test_database: TestDatabase,
) -> None:
    """05 TXN-03 rev 1.193 (dev-guide DG-KRN-DB-11; the supervisor's ruling of 2026-10-02): a
    connection of the application starts with ``jit=off``, and the value is the client's own —
    ``pg_settings.source`` reads ``client``, what the startup options give — so it holds
    whatever the server, the database or the role says. The engines: the app engine through two
    of its context factories, the owner engine, and an engine built for one run. Before, each
    answered the server's default."""
    found: dict[str, tuple[str, str]] = {}
    with tenant_session(ALL_ENTITIES) as session:
        found["tenant_session"] = _pair(session.execute(text(JIT_SETTING)).one())
    with identity_session(request_id="req-txn-03-jit") as session:
        found["identity_session"] = _pair(session.execute(text(JIT_SETTING)).one())
    with test_database.owner_engine.connect() as connection:
        found["owner_engine"] = _pair(connection.execute(text(JIT_SETTING)).one())
        connection.rollback()
    migration = migration_engine()
    try:
        with migration.connect() as connection:
            found["migration_engine"] = _pair(connection.execute(text(JIT_SETTING)).one())
            connection.rollback()
    finally:
        migration.dispose()
    assert found == {
        "tenant_session": ("off", "client"),
        "identity_session": ("off", "client"),
        "owner_engine": ("off", "client"),
        "migration_engine": ("off", "client"),
    }


def test_txn_03_the_workers_pool_starts_with_jit_off(test_database: TestDatabase) -> None:
    """The other road (05 TXN-03 rev 1.193; dev-guide DG-KRN-DB-11): the pool the worker's
    Procrastinate works on, built by the builder the worker calls (``jobs.pool.worker_pool``)
    and opened here. Its connection passes the worker's role guard and starts with the same
    setting from the same source. The builder's module registers no job handler: importing
    ``erev_api.worker`` here would register every one, for every test after this."""

    async def of_the_worker() -> tuple[str, str]:
        pool = worker_pool(get_settings().app_database_url(), min_size=1, max_size=2)
        await pool.open(wait=True)
        try:
            async with pool.connection() as connection:
                cursor = await connection.execute(JIT_SETTING)
                row = await cursor.fetchone()
                assert row is not None
                return _pair(row)
        finally:
            await pool.close()

    assert asyncio.run(of_the_worker()) == ("off", "client")


def test_krn_db_05_a_wide_block_gives_back_the_scope_in_force_when_it_began(
    test_database: TestDatabase,
) -> None:
    """DG-KRN-DB-05 (rev 1.87 part 11; supervisor rulings R-42 (d) and R-64 (1)): the two blocks
    that widen ``app.entity_scope`` are one implementation. Each sets ``*`` and gives back the
    scope it found — the caller's own when it stands alone, the SYSTEM scope when it is nested:
    the ``PERIOD_LOCK`` approval hook runs under ``system_entity_scope`` and evaluates the gates
    under ``every_entity_scope``, and the rest of the hook must still read every entity.

    Fail-first: an inner block that re-issues the context's own scope leaves ``E1`` in force
    inside the outer block."""
    ctx = DbContext(tenant_id=TENANT, user_id=USER, entity_scope=(E1,))
    scope = text("SELECT current_setting('app.entity_scope')")
    with tenant_session(ctx) as session:

        def in_force() -> str:
            return str(session.execute(scope).scalar_one())

        assert in_force() == str(E1)
        # Each block alone: wide inside, the caller's own scope afterwards.
        with every_entity_scope(session, ctx):
            assert in_force() == "*"
        assert in_force() == str(E1)
        with system_entity_scope(session):
            assert in_force() == "*"
        assert in_force() == str(E1)
        # Nested either way: the inner block ends and the outer one still reads every entity.
        with system_entity_scope(session):
            with every_entity_scope(session, ctx):
                assert in_force() == "*"
            assert in_force() == "*"
            with system_entity_scope(session):
                assert in_force() == "*"
            assert in_force() == "*"
        assert in_force() == str(E1)
        with every_entity_scope(session, ctx), system_entity_scope(session):
            assert in_force() == "*"
        assert in_force() == str(E1)
        # A refusal raised inside leaves the transaction usable and the caller's scope in force.
        with pytest.raises(Boom), system_entity_scope(session), every_entity_scope(session, ctx):
            raise Boom
        assert in_force() == str(E1)
        # The tenant, the user and the timeouts never moved.
        kept = session.execute(
            text(
                "SELECT current_setting('app.tenant_id'), current_setting('app.user_id'), "
                "current_setting('statement_timeout'), current_setting('lock_timeout')"
            )
        ).one()
        assert tuple(kept) == (str(TENANT), str(USER), "1min", "10s")
        # The user half of a group computation (``system_user``; DG-KRN-UOW-05, supervisor ruling
        # R-95) nests inside and around both blocks: each gives back its own setting and leaves
        # the other's alone, whichever ends first.
        user = text("SELECT current_setting('app.user_id')")

        def acting() -> tuple[str, str]:
            return str(session.execute(user).scalar_one()), in_force()

        with system_user(session):
            assert acting() == ("", str(E1))
            with system_entity_scope(session), every_entity_scope(session, ctx):
                assert acting() == ("", "*")
            assert acting() == ("", str(E1))
        assert acting() == (str(USER), str(E1))
        with every_entity_scope(session, ctx), system_entity_scope(session):
            with system_user(session):
                assert acting() == ("", "*")
                with system_user(session):
                    assert acting() == ("", "*")
                assert acting() == ("", "*")
            assert acting() == (str(USER), "*")
        assert acting() == (str(USER), str(E1))
        with pytest.raises(Boom), system_entity_scope(session), system_user(session):
            raise Boom
        assert acting() == (str(USER), str(E1))
    # A context that is already tenant-wide is left alone.
    with tenant_session(ALL_ENTITIES) as session:
        with every_entity_scope(session, ALL_ENTITIES), system_entity_scope(session):
            assert str(session.execute(scope).scalar_one()) == "*"
        assert str(session.execute(scope).scalar_one()) == "*"


def test_krn_db_02_identity_session_sets_only_user(test_database: TestDatabase) -> None:
    with identity_session(request_id="req-identity", user_id=USER) as session:
        row = session.execute(
            text(
                "SELECT current_setting('app.user_id', true), "
                "coalesce(current_setting('app.tenant_id', true), '')"
            )
        ).one()
    assert tuple(row) == (str(USER), "")


def test_krn_db_01_normal_exit_commits_and_exception_rolls_back(
    test_database: TestDatabase,
) -> None:
    xact_id = text("SELECT pg_current_xact_id()::text")
    with tenant_session(ALL_ENTITIES) as session:
        committed = session.execute(xact_id).scalar_one()
    aborted = ""
    with pytest.raises(Boom), tenant_session(ALL_ENTITIES) as session:
        aborted = session.execute(xact_id).scalar_one()
        raise Boom
    with identity_session(request_id="req-status") as session:
        statuses = session.execute(
            text("SELECT pg_xact_status(CAST(:c AS xid8)), pg_xact_status(CAST(:a AS xid8))"),
            {"c": committed, "a": aborted},
        ).one()
    assert tuple(statuses) == ("committed", "aborted")


def test_krn_db_01_read_only_rejects_writes(test_database: TestDatabase) -> None:
    with (
        pytest.raises(exc.DBAPIError) as excinfo,
        tenant_session(ALL_ENTITIES, read_only=True) as session,
    ):
        session.execute(text("CREATE TEMP TABLE t (x int)"))
    assert getattr(excinfo.value.orig, "sqlstate", None) == "25006"


def test_dg_tst_11_advisory_lock_serialises_sessions(test_database: TestDatabase) -> None:
    # DG-TST-11 key 0x6572657654455354 ("erevTEST"); BUILD_SPEC's decimal differs (SPEC-Q-18).
    assert TEST_DB_LOCK_KEY == 0x6572657654455354 == 7310016704070112084
    with test_database.owner_engine.connect() as other:
        acquired = other.execute(
            text("SELECT pg_try_advisory_lock(7310016704070112084)")
        ).scalar_one()
        if acquired:
            other.execute(text("SELECT pg_advisory_unlock(7310016704070112084)"))
        other.commit()
    assert acquired is False


def test_dg_tst_10_a_schema_rebuilt_after_dispose_engines_leaves_the_product_no_stale_pool(
    test_database: TestDatabase,
) -> None:
    """DG-TST-10 rev 1.269 (register index 249, TEST-ORDER-DEPENDENCIES-1). A unit test of the
    CLI's switch of environment reaches ``dispose_engines()``: the factories build new engines
    for every module after it. A module that rebuilds the schema then disposes through the
    fixture, so that no pooled connection keeps a statement prepared over the dropped types.
    The fixture's value answers the factories' engines, so that is the pool the product
    uses.

    Measured before, when the value kept the engines it was made with: the dispose closed
    the fixture's forgotten pool, the product's kept its connections, and the next statement
    over a type of the schema — in one process with that unit test two nodes of
    tests/pg/test_doctor.py at their setup, and test_jobs.py::test_krn_job_03 in its body —
    answered ``cache lookup failed for type <oid>``."""
    probe = text("SELECT CAST(:value AS erev.config_status)::text")

    def stated() -> str:
        with tenant_session(ALL_ENTITIES) as session:
            return str(session.execute(probe, {"value": "DRAFT"}).scalar_one())

    first = (test_database.app_engine, test_database.owner_engine)
    session_module.dispose_engines()  # what that unit test does to every module after it
    assert test_database.app_engine is session_module.app_engine()
    assert test_database.owner_engine is session_module.owner_engine()
    assert test_database.app_engine is not first[0]
    assert test_database.owner_engine is not first[1]
    # the session's lock is still held, on the connection the fixture took it with
    with test_database.owner_engine.connect() as other:
        acquired = other.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": TEST_DB_LOCK_KEY}
        ).scalar_one()
        if acquired:
            other.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": TEST_DB_LOCK_KEY})
        other.commit()
    assert acquired is False
    # the product's pooled connection prepares the statement (the driver does from the sixth
    # execution on), over a type of the schema
    assert [stated() for _ in range(8)] == ["DRAFT"] * 8
    used = session_module.app_engine().pool
    assert used.checkedin() >= 1
    support_db.fresh_head()  # every type of the schema has a new oid
    test_database.app_engine.dispose()
    test_database.owner_engine.dispose()
    assert session_module.app_engine().pool is not used  # the product's pool was closed
    assert stated() == "DRAFT"


def test_dg_tst_12_db_fixture_commits_release_savepoints(
    db: Callable[[DbContext], Session],
) -> None:
    session = db(ALL_ENTITIES)
    outer_xact = session.execute(text("SELECT pg_current_xact_id()::text")).scalar_one()
    session.commit()
    # The commit released a savepoint: same outer transaction, context still in force.
    row = session.execute(
        text("SELECT pg_current_xact_id()::text, current_setting('app.tenant_id')")
    ).one()
    assert tuple(row) == (outer_xact, str(TENANT))


def test_dg_env_13_destructive_reset_refused_outside_test_databases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_settings().env == "test"
    built: list[str] = []

    def spy(url: str, **_: object) -> None:
        built.append("engine")
        raise AssertionError("reset_schema created an engine before refusing")

    monkeypatch.setattr(support_db, "build_engine", spy)
    url = "postgresql+psycopg://erev_owner:placeholder-credential@127.0.0.1:5432/erev"
    with pytest.raises(DestructiveResetRefused, match="'erev'"):
        reset_schema(url)
    assert built == []
