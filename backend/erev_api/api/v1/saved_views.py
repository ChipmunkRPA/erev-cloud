"""API-R-16 Saved views: grid views and favourites of the signed-in member.

04 §15.3 API-R-16, T-PLT-37, API-C-08; SCREENS SCR-IA-07, SCR-IA-08, SF-01 favourites and SF-02
saved views bindings; BUILD_SPEC PLF-21. Any member may save views; only the owner changes or
deletes one.
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
from erev_api.auth.dependencies import require_authenticated
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import saved_view
from erev_api.domain.platform import saved_views
from erev_api.schemas.common import ListOut
from erev_api.schemas.saved_views import SavedViewIn, SavedViewOut, SavedViewUpdateIn
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-16 Saved views"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
SAVED_VIEW_LIST: Final = ListSpec(
    resource="saved-views",
    sort_keys={
        "id": saved_view.c.id,
        "name": saved_view.c.name,
        "screen_code": saved_view.c.screen_code,
    },
    default_sort="name",
    filters={
        "screen_code": FilterSpec(
            name="screen_code", column=saved_view.c.screen_code, kind="exact"
        ),
        "is_favourite": FilterSpec(
            name="is_favourite", column=saved_view.c.is_favourite, kind="bool"
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def saved_view_etag(out: SavedViewOut) -> str:
    """API-C-08: a saved view is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/saved-views",
    operation_id="saved_views_list",
    response_model=ListOut[SavedViewOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def saved_views_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    params: Annotated[ListParams, Depends(list_params)],
    screen_code: Annotated[str | None, Query(description="SCR-IA-07 screen code")] = None,
    is_favourite: Annotated[bool | None, Query()] = None,
) -> ListOut[SavedViewOut]:
    """The caller's views and the views other members share; sort ``name`` (default),
    ``screen_code`` or ``id``."""
    result = saved_views.list_saved_views(
        ctx, page=lambda session, statement: paginate(session, statement, SAVED_VIEW_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SavedViewOut](
        items=[SavedViewOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/saved-views",
    operation_id="saved_views_create",
    status_code=201,
    response_model=SavedViewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def saved_views_create(
    body: SavedViewIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Save a grid view or a favourite; a name is unique per member and screen."""

    def handle(uow: UnitOfWork) -> SavedViewOut:
        row = saved_views.create_saved_view(
            uow,
            screen_code=body.screen_code,
            name=body.name,
            config=body.config,
            is_shared=body.is_shared,
            is_favourite=body.is_favourite,
        )
        return SavedViewOut.model_validate(dict(row))

    return run_command(cmd, deps, handle, status_code=201, etag=saved_view_etag)


@router.patch(
    "/saved-views/{view_id}",
    operation_id="saved_views_update",
    response_model=SavedViewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def saved_views_update(
    view_id: uuid.UUID,
    body: SavedViewUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Rename a view, change its config, share it, or pin or unpin it as a favourite."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> SavedViewOut:
        row = saved_views.update_saved_view(uow, view_id, changes)
        return SavedViewOut.model_validate(dict(row))

    return run_command(cmd, deps, handle, etag=saved_view_etag)


@router.delete(
    "/saved-views/{view_id}",
    operation_id="saved_views_delete",
    status_code=204,
    response_class=Response,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def saved_views_delete(
    view_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Delete one of the caller's views."""
    return run_command(
        cmd, deps, lambda uow: saved_views.delete_saved_view(uow, view_id), status_code=204
    )
