"""Database sessions and tenant context KRN-DB (docs/dev-guide.md §5.2, §2.4; 05 TXN-01 to TXN-03).

Two engines exist per process: ``app_engine()`` connects as ``erev_app`` and serves every runtime
statement; ``owner_engine()`` connects as ``erev_owner`` for the operator's provider commands and
the test schema reset, and no statement of the api or the worker uses it (05 TXN-02 rev 1.162
lists every reader of an owner URL; a migration takes ``migration_engine()``).
Both refuse to connect as any other role (DG-ENV-12). The app engine refuses SQL issued outside
``tenant_session``, ``identity_session`` and ``platform_session`` (DG-KRN-DB-04), so tenant data is
never read without the transaction-local settings that row-level security keys on (REQ-PLT-001;
04 §1.4).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Connection,
    Engine,
    FromClause,
    create_engine,
    event,
    func,
    make_url,
    select,
    text,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry

from erev_api.auth.keyring import KeyRing, build_keyring
from erev_api.auth.security_events import record_security_event
from erev_api.config import database_of_url, get_settings
from erev_api.enums import AuditOutcome, SecurityEventKind
from erev_api.logging import get_logger, register_logger_fields

APP_ROLE: Final = "erev_app"
OWNER_ROLE: Final = "erev_owner"
# connection.info key that marks a connection as inside a context factory (DG-KRN-DB-04).
CONTEXT_INFO_KEY: Final = "erev.context"
_COMPONENT: Final = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
_LOGGER: Final = "erev_api.db.session"

register_logger_fields(_LOGGER, ("engine", "host", "port", "database"))

_SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true), "
    "set_config('app.user_id', :user_id, true), "
    "set_config('app.entity_scope', :scope, true), "
    "set_config('statement_timeout', :statement_timeout, true), "
    "set_config('lock_timeout', :lock_timeout, true)"
)
_SET_USER = text("SELECT set_config('app.user_id', :user_id, true)")
_USER = text("SELECT current_setting('app.user_id', true)")
_ENTITY_SCOPE = text("SELECT current_setting('app.entity_scope', true)")
_SET_IDLE_TIMEOUT = text(
    "SELECT set_config('idle_in_transaction_session_timeout', :idle_timeout, true)"
)
_SET_ENTITY_SCOPE = text("SELECT set_config('app.entity_scope', :scope, true)")
TENANT_SCOPE: Final = "*"


class ScopeNotTenantWide(RuntimeError):
    """A writer that needs the tenant's scope was called under an entity scope (05 TXN-10)."""


_SET_PLATFORM_SCOPE = text("SELECT set_config('app.platform_scope', :scope, true)")
PLATFORM_SCOPES: Final = ("tenant_directory", "provisioning")
# Session.info key through which a provisioning session names the tenant it created, so that its
# PLATFORM_SCOPE_USED event carries that tenant_id (04 T-PLT-06; DG-KRN-DB-03).
PLATFORM_TENANT_INFO_KEY: Final = "erev.platform_tenant_id"
_ROLE_QUERY: Final = (
    "SELECT current_user, r.rolsuper, r.rolbypassrls, current_database() "
    "FROM pg_roles r WHERE r.rolname = current_user"
)

Role = Literal["erev_app", "erev_owner"]


@dataclass(frozen=True, slots=True)
class DbContext:
    tenant_id: UUID
    user_id: UUID | None  # principal id; None for SYSTEM
    entity_scope: Literal["*"] | tuple[UUID, ...]

    def scope_setting(self) -> str:
        """``'*'`` or the entity ids ascending and comma-separated (DG-KRN-DB-01)."""
        if self.entity_scope == "*":
            return "*"
        return ",".join(str(entity) for entity in sorted(self.entity_scope))


@dataclass(frozen=True, slots=True)
class IdentityContext:
    request_id: str
    user_id: UUID | None


@dataclass(frozen=True, slots=True)
class PlatformContext:
    scope: Literal["tenant_directory", "provisioning"]
    request_id: str
    actor_user_id: UUID | None


@dataclass(frozen=True, slots=True)
class ReleaseContext:
    """The context of ``release_session``: no tenant, user or platform scope (05 REL-03)."""

    request_id: str


class TenantContextMissing(RuntimeError):
    """SQL reached the app engine outside the context factories (DG-KRN-DB-04)."""


class RoleGuardError(RuntimeError):
    """A connection authenticated as a role other than the engine's expected role (DG-ENV-12)."""


class DestructiveResetRefused(RuntimeError):
    """A schema reset targeted a database outside the DG-ENV-13 reset allow-list."""


_component = "api"


def set_component(name: str) -> None:
    """Set ``application_name`` ``erev-<component>`` (TXN-03); call before engines exist."""
    global _component
    if not _COMPONENT.fullmatch(name):
        raise ValueError("component must match ^[a-z][a-z0-9-]{0,40}$")
    _component = name


# 05 TXN-03: the statement timeout a connection starts with — the bound of a request.
STATEMENT_TIMEOUT_MS: Final = 30_000


def connect_options(component: str, *, statement_timeout_ms: int = STATEMENT_TIMEOUT_MS) -> str:
    """Session settings sent through libpq ``options`` at connect time (TXN-03): what every
    connection of the application starts with — the engines of ``build_engine`` and the worker's
    Procrastinate pool (dev-guide DG-KRN-DB-11).

    ``statement_timeout_ms`` is the request's 30 s on every connection but a migration's
    (``migration_engine``; TXN-03 rev 1.199). The lock timeout and the idle-in-transaction bound
    are the same on every connection.

    ``jit=off`` (05 TXN-03 rev 1.193; the supervisor's ruling of 2026-10-02): the application is
    transaction processing, and PostgreSQL compiles a plan whose estimated cost passes
    ``jit_above_cost`` before it runs it, at every execution. The exception queue's count for a
    member of one entity of two took 684 ms that way, 670 ms of them compilation, against 36 ms
    without. The setting is the application's own, not a role's or an instance's: the
    application depends on no setting outside its repository."""
    return (
        "-c TimeZone=UTC -c search_path=erev,public "
        f"-c statement_timeout={statement_timeout_ms} "
        "-c idle_in_transaction_session_timeout=60000 -c lock_timeout=10000 -c jit=off "
        f"-c application_name=erev-{component}"
    )


def database_of(url: str) -> str:
    """Database named by a URL, checked against the DG-ENV-13 allow-list; safe to log.

    Delegates to ``erev_api.config.database_of_url``, the single URL-to-database helper (D-78).
    """
    return database_of_url(url)


ROLE_QUERY: Final = _ROLE_QUERY


def role_guard_failure(role: Role, database: str, row: Sequence[Any] | None) -> str | None:
    """The DG-ENV-12 or DG-ENV-13 refusal for a ``ROLE_QUERY`` row; None when the row passes."""
    if row is None:
        return f"role guard: expected {role}, found unknown"
    found = str(row[0])
    privileged = row[1] is not False or (role == APP_ROLE and row[2] is not False)
    if found != role:
        return f"role guard: expected {role}, found {found}"
    if privileged:
        return f"role guard: {role} must not have SUPERUSER or BYPASSRLS"
    connected = str(row[3])
    if connected != database:
        return (
            f"database guard: the URL names {database}, but the connection reached "
            f"{connected} (DG-ENV-13)"
        )
    return None


def _role_guard(role: Role, database: str) -> Callable[[Any, ConnectionPoolEntry], None]:
    """Refuse a connection whose role (DG-ENV-12) or current database (DG-ENV-13) is unexpected."""

    def guard(dbapi_connection: Any, _: ConnectionPoolEntry) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(_ROLE_QUERY)
            row = cursor.fetchone()
        finally:
            cursor.close()
            dbapi_connection.rollback()
        failure = role_guard_failure(role, database, row)
        if failure is not None:
            dbapi_connection.close()
            raise RoleGuardError(failure)

    return guard


def _refuse_context_free(conn: Connection, *_: Any) -> None:
    if conn.info.get(CONTEXT_INFO_KEY) is None:
        raise TenantContextMissing(
            "SQL on the app engine requires tenant_session or identity_session (DG-KRN-DB-04)"
        )


def _clear_context(conn: Connection) -> None:
    # The context lives exactly as long as the transaction that set it (DG-KRN-DB-04).
    conn.info.pop(CONTEXT_INFO_KEY, None)


def build_engine(
    url: str,
    *,
    role: Role,
    component: str | None = None,
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
) -> Engine:
    """Engine with the TXN-03 options and role guard; the app role adds the DB-04 listener.
    Only ``migration_engine`` passes a ``statement_timeout_ms`` of its own."""
    database = database_of(url)
    parsed = make_url(url)
    engine = create_engine(
        url,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        # The most recently returned connection is reused first, so idle extras age out.
        pool_use_lifo=True,
        # Bound values never reach exception messages or logs (DG-LOG-03; D-78).
        hide_parameters=True,
        connect_args={
            "options": connect_options(
                component or _component, statement_timeout_ms=statement_timeout_ms
            )
        },
    )
    event.listen(engine, "connect", _role_guard(role, database))
    if role == APP_ROLE:
        event.listen(engine, "before_cursor_execute", _refuse_context_free)
        event.listen(engine, "commit", _clear_context)
        event.listen(engine, "rollback", _clear_context)
    get_logger(_LOGGER).info(
        "db.engine_created",
        engine="app" if role == APP_ROLE else "owner",
        host=parsed.host,
        port=parsed.port,
        database=database,
    )
    return engine


@lru_cache(maxsize=1)
def app_engine() -> Engine:
    """``erev_app`` engine for the selected environment (DG-ENV-10, DG-ENV-12)."""
    return build_engine(get_settings().app_database_url(), role=APP_ROLE)


@lru_cache(maxsize=1)
def owner_engine() -> Engine:
    """The cached ``erev_owner`` engine. In the product it serves the operator's provider
    commands alone (``erev idp …``; ``auth.oidc``); the test session resets its schema through
    it. Every other reader of an owner URL builds an engine of its own: Alembic
    (``migration_engine``), ``erev db reset``, ``erev doctor --analyze`` and the preflight of a
    review database (05 TXN-02 rev 1.162)."""
    return build_engine(get_settings().owner_database_url(), role=OWNER_ROLE)


def migration_engine() -> Engine:
    """Uncached ``erev_owner`` engine for one Alembic run (DG-MIG-01); the caller disposes it.

    Its connections are the one exception to the request's statement timeout (05 TXN-03 rev 1.199;
    DG-MIG-01 rev 1.264; item MIGRATION-STATEMENT-TIMEOUT-1): a revision's statement may run for
    ``Settings.migration_statement_timeout_seconds`` — a foreign key added over a partitioned
    table checks every partition in one statement — while its wait for a lock stays at the 10 s
    of every connection, so that an ``ALTER TABLE`` never holds the requests on its table behind
    itself. Every road of a migration takes this engine through Alembic's ``env.py``: ``erev
    migrate``, ``make migrate``, the migration job, the schema build of a test session."""
    settings = get_settings()
    return build_engine(
        settings.owner_database_url(),
        role=OWNER_ROLE,
        component="migrate",
        statement_timeout_ms=settings.migration_statement_timeout_seconds * 1000,
    )


def dispose_engines() -> None:
    """Close pooled connections and forget both engines (tests and process shutdown)."""
    for factory in (app_engine, owner_engine):
        if factory.cache_info().currsize:
            factory().dispose()
        factory.cache_clear()


def _context_parameters(
    ctx: DbContext, *, statement_timeout_ms: int, lock_timeout_ms: int
) -> dict[str, str]:
    return {
        "tenant_id": str(ctx.tenant_id),
        "user_id": "" if ctx.user_id is None else str(ctx.user_id),
        "scope": ctx.scope_setting(),
        "statement_timeout": str(statement_timeout_ms),
        "lock_timeout": str(lock_timeout_ms),
    }


@contextmanager
def _context_session(
    context: DbContext | IdentityContext | PlatformContext | ReleaseContext,
    setup: Callable[[Connection], None],
) -> Iterator[Session]:
    # The session owns the transaction, so a unit of work's session.commit() really commits
    # (DG-KRN-UOW-02). Statements after that commit reach a connection without context and fail.
    session = Session(bind=app_engine(), autoflush=False, expire_on_commit=False)
    try:
        connection = session.connection()
        connection.info[CONTEXT_INFO_KEY] = context
        setup(connection)
        yield session
        if session.in_transaction():
            session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


IsolationLevel = Literal["REPEATABLE READ"]
_SET_REPEATABLE_READ: Final = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"


def transaction_setup(
    connection: Connection,
    ctx: DbContext,
    *,
    read_only: bool,
    isolation_level: IsolationLevel | None,
    statement_timeout_ms: int = 60_000,
    lock_timeout_ms: int = 10_000,
) -> None:
    """The first statements of a tenant transaction, in the order PostgreSQL requires: the isolation
    level (only before any query — the context ``set_config`` SELECT is a query), the transaction-
    local context, then the access mode (SNP-1 slice I-2.1: readers establish REPEATABLE READ
    explicitly)."""
    if isolation_level is not None:
        connection.exec_driver_sql(_SET_REPEATABLE_READ)
    connection.execute(
        _SET_CONTEXT,
        _context_parameters(
            ctx, statement_timeout_ms=statement_timeout_ms, lock_timeout_ms=lock_timeout_ms
        ),
    )
    if read_only:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")


@contextmanager
def tenant_session(
    ctx: DbContext,
    *,
    read_only: bool = False,
    statement_timeout_ms: int = 60_000,
    lock_timeout_ms: int = 10_000,
    isolation_level: IsolationLevel | None = None,
) -> Iterator[Session]:
    """A tenant transaction on ``erev_app`` with transaction-local context (DG-KRN-DB-01);
    ``isolation_level`` raises the default READ COMMITTED to REPEATABLE READ for a consistent
    multi-statement read (SBX-04)."""

    def setup(connection: Connection) -> None:
        transaction_setup(
            connection,
            ctx,
            read_only=read_only,
            isolation_level=isolation_level,
            statement_timeout_ms=statement_timeout_ms,
            lock_timeout_ms=lock_timeout_ms,
        )

    with _context_session(ctx, setup) as session:
        yield session


@contextmanager
def lock_connection(ctx: DbContext) -> Iterator[Connection]:
    """An autocommit ``erev_app`` connection for session-level advisory locks (DG-KRN-JOB-03).

    A job holds its per-tenant slot across the handler's own transactions, so the lock lives on a
    connection outside any transaction, which ``idle_in_transaction_session_timeout`` would end.
    The caller releases every lock it takes before the connection returns to the pool.
    """
    with app_engine().connect() as connection:
        connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.info[CONTEXT_INFO_KEY] = ctx
        try:
            yield connection
        finally:
            connection.info.pop(CONTEXT_INFO_KEY, None)


@contextmanager
def identity_session(*, request_id: str, user_id: UUID | None = None) -> Iterator[Session]:
    """A transaction for the identity repositories; sets only ``app.user_id`` (DG-KRN-DB-02)."""

    def setup(connection: Connection) -> None:
        if user_id is not None:
            connection.execute(_SET_USER, {"user_id": str(user_id)})

    with _context_session(
        IdentityContext(request_id=request_id, user_id=user_id), setup
    ) as session:
        yield session


@contextmanager
def release_session(*, request_id: str) -> Iterator[Session]:
    """A transaction for the startup release stamping on the global ``engine_release`` (05 REL-03).

    It sets no tenant, user or platform scope; ``erev_api.controls.release`` is its only importer.
    """

    def setup(connection: Connection) -> None:
        return None

    with _context_session(ReleaseContext(request_id=request_id), setup) as session:
        yield session


@lru_cache(maxsize=1)
def process_keyring() -> KeyRing:
    """The process key ring for platform sessions not handed one (a DG-KRN-CFG-01 root)."""
    return build_keyring(get_settings())


def name_platform_tenant(session: Session, tenant_id: UUID) -> None:
    """Name the tenant a provisioning session created in its PLATFORM_SCOPE_USED event."""
    session.info[PLATFORM_TENANT_INFO_KEY] = tenant_id


@contextmanager
def platform_session(
    scope: Literal["tenant_directory", "provisioning"],
    *,
    actor_user_id: UUID | None,
    request_id: str,
    keyring: KeyRing | None = None,
) -> Iterator[Session]:
    """A platform-scope transaction that records its use as ``PLATFORM_SCOPE_USED`` (DG-KRN-DB-03).

    ``tenant_directory`` records the event first and is then read-only. ``provisioning`` records
    it last, before the commit, so the event names the tenant the session created
    (``name_platform_tenant``); a failed provisioning rolls the event back with everything else.
    """
    if scope not in PLATFORM_SCOPES:
        raise ValueError(f"unknown platform scope {scope!r}")
    ring = process_keyring() if keyring is None else keyring

    def record(bind: Session | Connection, tenant_id: UUID | None) -> None:
        record_security_event(
            bind,
            keyring=ring,
            kind=SecurityEventKind.PLATFORM_SCOPE_USED,
            outcome=AuditOutcome.SUCCESS,
            request_id=request_id,
            user_id=actor_user_id,
            tenant_id=tenant_id,
            detail={"scope": scope},
        )

    def setup(connection: Connection) -> None:
        connection.execute(_SET_PLATFORM_SCOPE, {"scope": scope})
        if scope == "tenant_directory":
            record(connection, None)
            # Allowed after writes: only the change to READ WRITE must precede the first query.
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    context = PlatformContext(scope=scope, request_id=request_id, actor_user_id=actor_user_id)
    with _context_session(context, setup) as session:
        yield session
        if scope == "provisioning" and session.in_transaction():
            named = session.info.get(PLATFORM_TENANT_INFO_KEY)
            record(session, named if isinstance(named, UUID) else None)


@contextmanager
def system_entity_scope(session: Session) -> Iterator[None]:
    """Inside the caller's transaction, read and write under the tenant's SYSTEM entity scope —
    tenant isolation only — and give the caller's entity scope back on the way out (supervisor
    rulings R-42 (d) and R-64 (1): what a control reads, hashes or recomputes must not depend on
    who decides). Only ``app.entity_scope`` changes: the tenant, the user and the timeouts of the
    transaction stay, so every write is still attributed to the caller. Nested uses keep the wide
    scope: the block gives back the scope that was in force when it began, read from the
    transaction. When the block raises, the scope is given back only if the transaction can still
    run a statement; a failed transaction is rolled back by its owner, and the setting with it."""
    previous = session.execute(_ENTITY_SCOPE).scalar_one()
    if previous == "*":
        yield
        return
    session.execute(_SET_ENTITY_SCOPE, {"scope": "*"})
    try:
        yield
    except BaseException:
        # A failed statement aborts the transaction; its rollback discards the local setting, and
        # re-issuing the scope would only mask the error. A refusal raised by the block leaves
        # the transaction usable, so the scope is restored for whatever the caller does next.
        with suppress(Exception):
            if session.in_transaction():
                session.execute(_SET_ENTITY_SCOPE, {"scope": previous or ""})
        raise
    session.execute(_SET_ENTITY_SCOPE, {"scope": previous or ""})


@contextmanager
def every_entity_scope(session: Session, ctx: DbContext) -> Iterator[None]:
    """Read and write the rows of EVERY entity of the tenant for the statements of the block,
    inside the current transaction, then give back the entity scope that was in force when the
    block began (dev-guide DG-KRN-DB-05 rev 1.89; supervisor ruling R-42 (d), item
    CLO-GATE-SCOPE-1).

    A control's result must not depend on who asks: the close gates count rows that carry another
    entity (a failure item of a connection that serves every entity, a contract of another entity
    with lines in the period), and row-level security would hide them from a caller whose roles
    name the period's entity only. Only ``app.entity_scope`` changes — the tenant, the user and
    the timeouts stay — and the setting is transaction-local, so a rollback discards it. The
    caller must have authorised the principal for the subject first; the block is for a control's
    own reads and the rows it stores, never for data returned to the caller. A context that is
    already tenant-wide is left alone.

    It is ``system_entity_scope`` for a caller that holds its context — one implementation
    (dev-guide rev 1.87 part 11): the scope given back is ``ctx``'s own, or the SYSTEM scope of an
    enclosing block. The approvals kernel runs an approval hook under the SYSTEM scope
    (supervisor ruling R-64 (1)), and the ``PERIOD_LOCK`` hook evaluates the gates; re-issuing
    ``ctx``'s scope there would narrow the rest of the hook to the decider's entities."""
    if ctx.entity_scope == "*":
        yield
        return
    with system_entity_scope(session):
        yield


@contextmanager
def system_user(session: Session) -> Iterator[None]:
    """Inside the caller's transaction, attribute the statements of the block to SYSTEM —
    ``app.user_id`` empty, as a job's transaction has it — and give the caller's user back on the
    way out (dev-guide DG-KRN-UOW-05; 05 TXN-10; supervisor ruling R-95). Only ``app.user_id``
    changes. It is the user half of ``UnitOfWork.as_system`` and has no other caller: the block
    that widens the entity scope is ``system_entity_scope``, and a group computation takes both.
    The user is given back as that block gives the scope back — after a refusal when the
    transaction can still run a statement, by the owner's rollback otherwise; a block that ended
    normally and whose setting cannot be re-issued raises."""
    previous = session.execute(_USER).scalar_one()
    if not previous:
        yield
        return
    session.execute(_SET_USER, {"user_id": ""})
    try:
        yield
    except BaseException:
        with suppress(Exception):
            if session.in_transaction():
                session.execute(_SET_USER, {"user_id": previous})
        raise
    session.execute(_SET_USER, {"user_id": previous})


def of_session_tenant(table: FromClause) -> ColumnElement[bool]:
    """The rows of ``table`` that are the transaction's tenant's: ``tenant_id`` is
    ``erev.current_tenant_id()``, as the tenant policy of every table states it (04 §1.4).

    Row-level security does this alone for an RLS-T table. ``tenant_membership`` is RLS-TM: a
    second, permissive SELECT policy shows a user their own memberships of EVERY tenant — the
    rows the workspace picker reads — in any transaction that carries the user, a tenant's
    included. A statement that reads memberships as the members of the workspace therefore names
    the tenant itself: by the key of a row it joins, by a tenant id it holds, or by this
    condition where it holds none (dev-guide DG-KRN-DB-12, rev 1.256; item USERS-MEMBER-TENANT-1;
    ``tests/architecture/test_membership_reads_name_the_tenant.py``). Without it a member of two
    workspaces was listed in each once per membership, and a read by an id that a loaded sandbox
    shares with its source returned two rows.

    A lock or a write needs no such condition: a row that ``FOR UPDATE``, ``FOR SHARE`` or
    ``UPDATE`` reaches passes the policies of UPDATE too, and the tenant policy is the only one
    (``tests/pg/test_rls_isolation.py::test_rls_tm_in_a_tenant_transaction_of_a_user``). In a
    transaction without a tenant the condition holds for no row."""
    return table.c.tenant_id == select(func.erev.current_tenant_id()).scalar_subquery()


def require_tenant_scope(session: Session) -> None:
    """Refuse by name unless the transaction runs under the tenant's scope (05 TXN-10).

    The writer of a computation calls it before its first statement: a computation that wrote
    under an entity scope would leave out, without an error, the rows of a performing entity its
    caller cannot see (supervisor ruling R-95)."""
    scope = session.execute(_ENTITY_SCOPE).scalar_one()
    if scope != TENANT_SCOPE:
        raise ScopeNotTenantWide(
            "a group computation writes under the tenant's scope (05 TXN-10); the transaction "
            "is under an entity scope"
        )


def allow_idle_in_transaction(session: Session) -> None:
    """Set ``idle_in_transaction_session_timeout`` for the session's CURRENT transaction to
    ``Settings.dataset_freeze_idle_seconds`` (05 TXN-03 rev 1.121, CFG-29; DG-KRN-DB-01 rev
    1.165; supervisor rulings R-116 (h) and R-119 (d)). Every connection carries 60 s from its
    connect options; a transaction that is idle while ANOTHER connection of the same command
    works — a dataset freeze's caller while the SYSTEM reader produces a dataset, a held reader
    while its caller stores the files and writes — was ended by it. The one caller is
    ``close.freeze.allow_idle``. The setting is transaction-local, as the context is, and leaves
    with the transaction; each statement stays under ``statement_timeout``."""
    seconds = get_settings().dataset_freeze_idle_seconds
    session.execute(_SET_IDLE_TIMEOUT, {"idle_timeout": str(seconds * 1000)})


def set_tenant_context(
    bind: Session | Connection,
    ctx: DbContext,
    *,
    statement_timeout_ms: int = 60_000,
    lock_timeout_ms: int = 10_000,
) -> None:
    """Re-issue the DG-KRN-DB-01 settings inside the current transaction (DG-KRN-DB-05).

    The connection must already be marked by a context factory or a test fixture; otherwise the
    app engine refuses the statement (DG-KRN-DB-04).
    """
    bind.execute(
        _SET_CONTEXT,
        _context_parameters(
            ctx, statement_timeout_ms=statement_timeout_ms, lock_timeout_ms=lock_timeout_ms
        ),
    )
