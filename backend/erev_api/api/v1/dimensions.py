"""API-R-21 Dimensions: built-in and custom dimensions and their values.

04 §15.3 API-R-21, T-REF-16, T-REF-17, DB-12, API-C-08, API-C-09; SCREENS_B §9.5 data bindings;
BUILD_SPEC RFD-6. Reading needs ``config.read``; the commands need ``masterdata.maintain``, and
``PATCH`` needs ``If-Match``. API-R-21 has no single-dimension or single-value read, so the 201
responses carry an ``ETag`` and no ``Location`` (DG-CMD-12; L1-1-Q-6).
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
from erev_api.db.tables import dimension_definition, dimension_value
from erev_api.domain.reference import commands, queries
from erev_api.schemas.common import ListOut
from erev_api.schemas.dimensions import (
    DimensionIn,
    DimensionOut,
    DimensionValueIn,
    DimensionValueOut,
    DimensionValueUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-21 Dimensions"
READ_PERMISSION: Final = "config.read"
MAINTAIN_PERMISSION: Final = "masterdata.maintain"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
DIMENSION_LIST: Final = ListSpec(
    resource="dimensions",
    sort_keys={
        "id": dimension_definition.c.id,
        "code": dimension_definition.c.code,
        "name": dimension_definition.c.name,
        "position": dimension_definition.c.position,
    },
    default_sort="position",
    filters={
        "is_active": FilterSpec(
            name="is_active", column=dimension_definition.c.is_active, kind="bool"
        ),
    },
)
DIMENSION_VALUE_LIST: Final = ListSpec(
    resource="dimension values",
    sort_keys={
        "id": dimension_value.c.id,
        "code": dimension_value.c.code,
        "name": dimension_value.c.name,
    },
    default_sort="code",
    filters={
        "is_active": FilterSpec(name="is_active", column=dimension_value.c.is_active, kind="bool"),
    },
    search_columns=(dimension_value.c.code, dimension_value.c.name),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def dimension_etag(out: DimensionOut) -> str:
    """API-C-08: a dimension is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def dimension_value_etag(out: DimensionValueOut) -> str:
    """API-C-08: a dimension value is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/dimensions",
    operation_id="dimensions_list",
    response_model=ListOut[DimensionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def dimensions_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[DimensionOut]:
    """The built-in and custom dimensions; sort ``position`` (default), ``code``, ``name`` or
    ``id``."""
    result = queries.list_dimensions(
        ctx, page=lambda session, statement: paginate(session, statement, DIMENSION_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[DimensionOut](
        items=[DimensionOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/dimensions",
    operation_id="dimensions_create",
    status_code=201,
    response_model=DimensionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def dimensions_create(
    body: DimensionIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Define a custom dimension; a workspace defines at most five (DB-12)."""

    def handle(uow: UnitOfWork) -> DimensionOut:
        return commands.create_dimension(uow, body=body)

    return run_command(cmd, deps, handle, status_code=201, etag=dimension_etag)


@router.get(
    "/dimensions/{code}/values",
    operation_id="dimension_values_list",
    response_model=ListOut[DimensionValueOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def dimension_values_list(
    code: str,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[DimensionValueOut]:
    """The stored values of one dimension; sort ``code`` (default), ``name`` or ``id``. Product and
    customer values are not stored here (T-REF-17), so their lists are empty."""
    result = queries.list_dimension_values(
        ctx,
        code,
        page=lambda session, statement: paginate(session, statement, DIMENSION_VALUE_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[DimensionValueOut](
        items=[DimensionValueOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/dimensions/{code}/values",
    operation_id="dimension_values_create",
    status_code=201,
    response_model=DimensionValueOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def dimension_values_create(
    code: str,
    body: DimensionValueIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Add an allowed value to a dimension other than product and customer."""

    def handle(uow: UnitOfWork) -> DimensionValueOut:
        return commands.create_dimension_value(uow, dimension_code=code, body=body)

    return run_command(cmd, deps, handle, status_code=201, etag=dimension_value_etag)


@router.patch(
    "/dimensions/{code}/values/{value_id}",
    operation_id="dimension_values_update",
    response_model=DimensionValueOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "precondition-failed", "precondition-required"
    ),
)
def dimension_values_update(
    code: str,
    value_id: uuid.UUID,
    body: DimensionValueUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Rename a value, change its parent, or (de)activate it; the code does not change."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> DimensionValueOut:
        return commands.update_dimension_value(
            uow,
            dimension_code=code,
            value_id=value_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=dimension_value_etag)
