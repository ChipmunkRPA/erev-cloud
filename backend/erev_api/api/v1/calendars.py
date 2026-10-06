"""API-R-18 Calendars and periods: fiscal calendars and period generation.

04 §15.3 API-R-18, T-REF-04, T-REF-05, API-C-08, API-C-09; BUILD_SPEC RFD-1. Reading calendars needs
``config.read``. Creating a calendar and ``generate-year`` need any of ``masterdata.maintain`` and
``settings.manage``; a single-code guard cannot express a permission set, so the routes use
``command(per_subject=True)`` and the handlers authorise (as API-R-12 does; SPEC-Q-157). The period
reads and period commands of API-R-18 belong to RFD-2 and CLO.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response

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
from erev_api.api.lists import TOTAL_COUNT_HEADER, ListParams, ListSpec, list_params, paginate
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import fiscal_calendar
from erev_api.domain.reference import commands, queries
from erev_api.schemas.calendars import CalendarIn, CalendarOut, GenerateYearIn, GenerateYearOut
from erev_api.schemas.common import ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-18 Calendars and periods"
READ_PERMISSION: Final = "config.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
CALENDAR_LIST: Final = ListSpec(
    resource="calendars",
    sort_keys={
        "id": fiscal_calendar.c.id,
        "code": fiscal_calendar.c.code,
        "name": fiscal_calendar.c.name,
    },
    default_sort="code",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def calendar_etag(out: CalendarOut) -> str:
    """API-C-08: a calendar is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/calendars",
    operation_id="calendars_list",
    response_model=ListOut[CalendarOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def calendars_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[CalendarOut]:
    """The tenant's fiscal calendars; sort ``code`` (default), ``name`` or ``id``."""
    result = queries.list_calendars(
        ctx, page=lambda session, statement: paginate(session, statement, CALENDAR_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[CalendarOut](
        items=[CalendarOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/calendars",
    operation_id="calendars_create",
    status_code=201,
    response_model=CalendarOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def calendars_create(
    body: CalendarIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a fiscal calendar; ``generate-year`` then creates its periods."""

    def handle(uow: UnitOfWork) -> CalendarOut:
        return commands.create_calendar(uow, body=body)

    return run_command(cmd, deps, handle, status_code=201, etag=calendar_etag)


@router.post(
    "/calendars/{calendar_id}/generate-year",
    operation_id="calendars_generate_year",
    response_model=GenerateYearOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def calendars_generate_year(
    calendar_id: uuid.UUID,
    body: GenerateYearIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create the periods of one fiscal year; a generated year is returned unchanged."""

    def handle(uow: UnitOfWork) -> GenerateYearOut:
        return commands.generate_year(uow, calendar_id=calendar_id, body=body)

    return run_command(cmd, deps, handle)
