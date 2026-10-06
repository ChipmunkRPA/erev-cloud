"""API-R-45 reads: integration connections, sync runs and external ids (04 §15.3 API-R-45;
T-INT-01, T-INT-02, T-INT-04; §16.14 "Integration connections add ``last_sync_run`` … sync runs
add ``duration_seconds``"; SCREENS SF-16 bindings; BUILD_SPEC DIN-12).

Every read runs in a read-only tenant session of the request's principal (RLS-T) through
``read``; the routes compose one page (``api.lists.paginate`` over ``connection_statement`` and
the other statements) with the shaping functions here inside that session, as ``auth.api_clients``
hands its statement to the caller's ``page``. ``connection_out`` adds the connection's newest sync
run (by ``created_at``, then id) or null; ``sync_run_out`` adds ``duration_seconds`` =
``finished_at`` − ``started_at`` in whole seconds, null while the run is queued or running.
``secret_ref`` is the reference NAME (REQ-INT-006): nothing here can reach a secret value.

**The reach of a connection (04 API-C-03 and API-R-45 rev 1.243; supervisor rulings R-28 and
R-115 (c); the supervisor's ruling of 2026-10-01 on item SCOPE-WORKSPACE-LISTS-1 (c2)).** A
connection serves the entities of ``entity_ids``, and every entity when the list is empty
(T-INT-01). The three tables are RLS-T — no row policy knows a connection's entities — so the
readers here decide: a principal reaches a connection when its scope of the route's permission
covers EVERY entity the connection serves, and a connection that serves every entity only when
it holds the permission for all entities (``in_reach`` in SQL, ``reaches`` for one row; the
kernel's ``entity_scope.covers``). A sync run and an external id are reached through their
connection. Out of reach a row is absent: the lists leave it out and ``get_connection_in_reach``
answers 404 ``not-found``, for a read and for a command alike. Measured before: an Integration
Admin of one entity listed, renamed, tested, synced and re-pointed the connection of another.
``get_connection_row`` stays the unscoped read of the worker's paths, which act as SYSTEM.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, Uuid, and_, func, literal, select, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.auth import entity_scope
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import external_id_map, integration_connection, sync_run
from erev_api.problems import Problem

__all__ = [
    "CONNECTION_OBJECT",
    "EXTERNAL_ID_OBJECT",
    "SYNC_RUN_OBJECT",
    "connection_out",
    "connection_statement",
    "duration_seconds",
    "external_id_out",
    "external_id_statement",
    "get_connection",
    "get_connection_in_reach",
    "get_connection_row",
    "get_sync_run",
    "get_sync_run_row",
    "in_reach",
    "last_sync_run_out",
    "latest_sync_runs",
    "reaches",
    "read",
    "served",
    "sync_run_out",
    "sync_run_statement",
]

CONNECTION_OBJECT: Final = "integration_connection"
SYNC_RUN_OBJECT: Final = "sync_run"
EXTERNAL_ID_OBJECT: Final = "external_id_map"


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """``fn`` in a read-only tenant session of the request's principal."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


# --- the reach of a connection --------------------------------------------------------------------


def served(entity_ids: Iterable[Any] | None) -> tuple[bool, tuple[UUID, ...]]:
    """The scope a connection serves, as the kernel states a grant's scope: every entity when
    ``entity_ids`` is empty (04 T-INT-01), else the entities it names."""
    ids = tuple(UUID(str(value)) for value in entity_ids or ())
    return (not ids, ids)


def reaches(principal: Principal, permission: str, connection: Mapping[str, Any]) -> bool:
    """Whether ``principal`` reaches the connection under ``permission``: its scope of the
    permission covers every entity the connection serves (module docstring)."""
    held = entity_scope.held_scope(principal, permission)
    return entity_scope.covers(held, [served(connection["entity_ids"])])


def in_reach(principal: Principal, permission: str) -> ColumnElement[bool]:
    """``reaches`` in SQL, over ``integration_connection``."""
    held = entity_scope.held_scope(principal, permission)
    if held == "*":
        return true()
    return and_(
        func.cardinality(integration_connection.c.entity_ids) > 0,
        integration_connection.c.entity_ids.contained_by(literal(sorted(held), ARRAY(Uuid()))),
    )


def _through_connection(
    column: ColumnElement[Any], principal: Principal, permission: str
) -> ColumnElement[bool]:
    """The rows whose connection (``column``) the principal reaches."""
    if entity_scope.holds_all(principal, permission):
        return true()
    return column.in_(select(integration_connection.c.id).where(in_reach(principal, permission)))


# --- statements the routes page -------------------------------------------------------------------


def connection_statement(principal: Principal, permission: str) -> Select[Any]:
    """The connections ``principal`` reaches under ``permission``."""
    return select(integration_connection).where(in_reach(principal, permission))


def sync_run_statement(principal: Principal, permission: str) -> Select[Any]:
    """The sync runs of the connections ``principal`` reaches."""
    return select(sync_run).where(
        _through_connection(sync_run.c.integration_connection_id, principal, permission)
    )


def external_id_statement(principal: Principal, permission: str) -> Select[Any]:
    """The external ids kept under the connections ``principal`` reaches."""
    return select(external_id_map).where(
        _through_connection(external_id_map.c.integration_connection_id, principal, permission)
    )


# --- rows -----------------------------------------------------------------------------------------


def _one(session: Session, statement: Select[Any], *, lock: bool) -> Mapping[str, Any]:
    row = (
        session.execute(statement.with_for_update() if lock else statement).mappings().one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def get_connection_row(
    session: Session, connection_id: UUID, *, lock: bool = False
) -> Mapping[str, Any]:
    """The T-INT-01 row, or 404 ``not-found``; ``lock`` takes ``FOR UPDATE`` for a command."""
    return _one(
        session,
        select(integration_connection).where(integration_connection.c.id == connection_id),
        lock=lock,
    )


def get_connection_in_reach(
    session: Session,
    principal: Principal,
    permission: str,
    connection_id: UUID,
    *,
    lock: bool = False,
) -> Mapping[str, Any]:
    """The T-INT-01 row for a read or a command of ``principal`` under ``permission``: 404
    ``not-found`` when no connection has the id or the principal does not reach it — one answer
    for both (03 REQ-PLT-012)."""
    row = get_connection_row(session, connection_id, lock=lock)
    if not reaches(principal, permission, row):
        raise Problem("not-found")
    return row


def get_sync_run_row(
    session: Session, sync_run_id: UUID, *, lock: bool = False
) -> Mapping[str, Any]:
    """The T-INT-02 row, or 404 ``not-found``."""
    return _one(session, select(sync_run).where(sync_run.c.id == sync_run_id), lock=lock)


def latest_sync_runs(
    session: Session, connection_ids: Iterable[UUID]
) -> dict[UUID, Mapping[str, Any]]:
    """The newest sync run of each connection (``created_at`` descending, then id), for
    ``last_sync_run`` (04 §16.14); connections without a run are absent."""
    ids = sorted({UUID(str(value)) for value in connection_ids})
    if not ids:
        return {}
    statement = (
        select(sync_run)
        .where(sync_run.c.integration_connection_id.in_(ids))
        .order_by(
            sync_run.c.integration_connection_id,
            sync_run.c.created_at.desc(),
            sync_run.c.id.desc(),
        )
        .distinct(sync_run.c.integration_connection_id)
    )
    return {
        UUID(str(row["integration_connection_id"])): MappingProxyType(dict(row))
        for row in session.execute(statement).mappings()
    }


# --- shapes ---------------------------------------------------------------------------------------


def duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    """04 §16.14: ``finished_at`` − ``started_at`` in whole seconds; null while running."""
    if started_at is None or finished_at is None:
        return None
    return int((finished_at - started_at).total_seconds())


def _without_tenant(row: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out.pop("tenant_id", None)
    return out


def last_sync_run_out(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """04 §16.14 ``last_sync_run`` ``{id, status, finished_at, result: {record_count,
    exception_count}}`` or null."""
    if row is None:
        return None
    return {
        "id": row["id"],
        "status": row["status"],
        "finished_at": row["finished_at"],
        "result": {
            "record_count": int(row["record_count"]),
            "exception_count": int(row["exception_count"]),
        },
    }


def connection_out(row: Mapping[str, Any], last_run: Mapping[str, Any] | None) -> dict[str, Any]:
    """API-S-IntegrationConnection of a T-INT-01 row and its newest sync run."""
    out = _without_tenant(row)
    out["entity_ids"] = [UUID(str(value)) for value in (row["entity_ids"] or ())]
    out["last_sync_run"] = last_sync_run_out(last_run)
    return out


def sync_run_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """API-S-SyncRun of a T-INT-02 row (with ``duration_seconds``)."""
    out = _without_tenant(row)
    out["duration_seconds"] = duration_seconds(row["started_at"], row["finished_at"])
    return out


def external_id_out(row: Mapping[str, Any]) -> dict[str, Any]:
    """API-S-ExternalIdMap of a T-INT-04 row."""
    return _without_tenant(row)


# --- single reads ---------------------------------------------------------------------------------


def get_connection(ctx: RequestContext, permission: str, connection_id: UUID) -> dict[str, Any]:
    """``GET /integrations/{id}``: the connection in the caller's reach, else 404."""

    def fn(session: Session) -> dict[str, Any]:
        row = get_connection_in_reach(session, ctx.principal, permission, connection_id)
        latest = latest_sync_runs(session, [connection_id])
        return connection_out(row, latest.get(connection_id))

    return read(ctx, fn)


def get_sync_run(ctx: RequestContext, permission: str, sync_run_id: UUID) -> dict[str, Any]:
    """``GET /sync-runs/{id}``: a run of a connection in the caller's reach, else 404."""

    def fn(session: Session) -> dict[str, Any]:
        row = get_sync_run_row(session, sync_run_id)
        get_connection_in_reach(
            session, ctx.principal, permission, UUID(str(row["integration_connection_id"]))
        )
        return sync_run_out(row)

    return read(ctx, fn)
