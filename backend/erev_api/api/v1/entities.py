"""API-R-17 Entities and books.

04 §15.3 API-R-17, T-REF-01 to T-REF-03, API-C-03, API-C-08, API-C-09; SCREENS_B SF-15:entities;
BUILD_SPEC RFD-2. Reads need ``config.read`` and return only entities in the principal's scope; an
id outside it is 404 (REQ-PLT-012). Commands need any of ``masterdata.maintain`` and
``settings.manage``; a single-code guard cannot express a permission set, so the routes use
``command(per_subject=True)`` and the handlers authorise, then check ``If-Match`` where the
command updates a row (API-R-12 precedent; L1-1-Q-4).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    assert_version,
    command,
    expected_version,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import book, legal_entity
from erev_api.domain.reference import commands, queries
from erev_api.enums import BookCode
from erev_api.schemas.common import ListOut
from erev_api.schemas.entities import (
    BookOut,
    BookUpdateIn,
    EntityBookIn,
    EntityBookOut,
    EntityIn,
    EntityOut,
    EntityUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-17 Entities and books"
READ_PERMISSION: Final = "config.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_UPDATE_PROBLEMS: Final = (
    *_COMMAND_PROBLEMS,
    "not-found",
    "precondition-failed",
    "precondition-required",
)
ENTITY_LIST: Final = ListSpec(
    resource="entities",
    sort_keys={
        "id": legal_entity.c.id,
        "code": legal_entity.c.code,
        "name": legal_entity.c.name,
    },
    default_sort="code",
    filters={
        "is_active": FilterSpec(name="is_active", column=legal_entity.c.is_active, kind="bool"),
    },
)
BOOK_LIST: Final = ListSpec(
    resource="books",
    sort_keys={"id": book.c.id, "code": book.c.code},
    default_sort="code",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def entity_etag(out: EntityOut) -> str:
    """API-C-08: an entity is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def entity_location(out: EntityOut) -> str:
    return f"{API_PREFIX}/entities/{out.id}"


def book_etag(out: BookOut) -> str:
    return row_etag(out.row_version)


def entity_book_etag(out: EntityBookOut) -> str:
    return row_etag(out.row_version)


def _version_check(cmd: CommandContext) -> commands.VersionCheck:
    """``If-Match`` of a per-subject command, checked once the handler has authorised."""
    return lambda actual: assert_version(expected_version(cmd.ctx.if_match, "row"), actual)


@router.get(
    "/entities",
    operation_id="entities_list",
    response_model=ListOut[EntityOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def entities_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[EntityOut]:
    """The entities in the principal's scope with the books they keep; sort ``code`` (default),
    ``name`` or ``id``."""
    result, items = queries.list_entities(
        ctx, page=lambda session, statement: paginate(session, statement, ENTITY_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[EntityOut](
        items=[EntityOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/entities",
    operation_id="entities_create",
    status_code=201,
    response_model=EntityOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def entities_create(
    body: EntityIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a legal entity; it keeps the primary book and gets its journal entry series."""

    def handle(uow: UnitOfWork) -> EntityOut:
        return commands.create_entity(uow, body=body)

    return run_command(
        cmd, deps, handle, status_code=201, location=entity_location, etag=entity_etag
    )


@router.get(
    "/entities/{entity_id}",
    operation_id="entities_get",
    response_model=EntityOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def entities_get(
    entity_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> EntityOut:
    """One entity with its ``ETag``; 404 outside the principal's entity scope."""
    out = EntityOut.model_validate(queries.get_entity(ctx, entity_id))
    response.headers["ETag"] = entity_etag(out)
    return out


@router.patch(
    "/entities/{entity_id}",
    operation_id="entities_update",
    response_model=EntityOut,
    responses=problem_responses(*_UPDATE_PROBLEMS),
)
def entities_update(
    entity_id: uuid.UUID,
    body: EntityUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Rename an entity, change its functional currency, time zone, parent, country or tax id, or
    (de)activate it; ``If-Match`` required. The code and calendar do not change."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> EntityOut:
        return commands.update_entity(
            uow, entity_id=entity_id, changes=changes, check_version=_version_check(cmd)
        )

    return run_command(cmd, deps, handle, etag=entity_etag)


@router.get(
    "/books",
    operation_id="books_list",
    response_model=ListOut[BookOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def books_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[BookOut]:
    """The tenant's three books (E-02); sort ``code`` (default) or ``id``."""
    result = queries.list_books(
        ctx, page=lambda session, statement: paginate(session, statement, BOOK_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[BookOut](
        items=[BookOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.patch(
    "/books/{code}",
    operation_id="books_update",
    response_model=BookOut,
    responses=problem_responses(*_UPDATE_PROBLEMS),
)
def books_update(
    code: BookCode,
    body: BookUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Rename a book, change its posting target or (de)activate it; ``If-Match`` required."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> BookOut:
        return commands.update_book(
            uow, code=code, changes=changes, check_version=_version_check(cmd)
        )

    return run_command(cmd, deps, handle, etag=book_etag)


@router.put(
    "/entities/{entity_id}/books/{code}",
    operation_id="entities_put_book",
    response_model=EntityBookOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def entities_put_book(
    entity_id: uuid.UUID,
    code: BookCode,
    body: EntityBookIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Keep, re-enable or disable a book for an entity; a newly kept book gets its period states
    from ``first_period_key``."""

    def handle(uow: UnitOfWork) -> EntityBookOut:
        return commands.put_entity_book(uow, entity_id=entity_id, code=code, body=body)

    return run_command(cmd, deps, handle, etag=entity_book_etag)
