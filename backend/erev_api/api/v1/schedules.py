"""API-R-35 Schedules: schedule lines across contracts.

04 §15.3 API-R-35, §16.2 API-S-ScheduleLine, API-C-09 to API-C-11; BUILD_SPEC CTR-5. Reads need
``contract.read``; row-level security scopes lines to the caller's entities. ``GET /schedule-lines``
filters by ``contract``, ``obligation`` (key or id), ``book`` (default the primary book), ``entity``
(code or id), ``from_period`` and ``to_period`` (period keys), ``line_type``, ``schedule_kind``,
``as_of`` and ``known_at`` (the latest version of each group recorded by then).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    ListParams,
    ListResult,
    ListSpec,
    invalid,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import schedule_line
from erev_api.domain.contracts import queries
from erev_api.enums import BookCode, ScheduleKind, ScheduleLineType
from erev_api.schemas.common import ListOut
from erev_api.schemas.contracts import ScheduleLineOut

TAG: Final = "API-R-35 Schedules"
READ: Final = "contract.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
SCHEDULE_LINE_LIST: Final = ListSpec(
    resource="schedule-lines",
    sort_keys={"id": schedule_line.c.id, "period_end_date": schedule_line.c.period_end_date},
    default_sort="period_end_date",
    filters={},
    custom_filters=frozenset(
        {
            "contract",
            "obligation",
            "book",
            "entity",
            "from_period",
            "to_period",
            "line_type",
            "schedule_kind",
            "as_of",
            "known_at",
        }
    ),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/schedule-lines",
    operation_id="schedule_lines_list",
    response_model=ListOut[ScheduleLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def schedule_lines_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    contract: Annotated[uuid.UUID | None, Query()] = None,
    obligation: Annotated[str | None, Query(description="Obligation key or id")] = None,
    book: Annotated[BookCode | None, Query(description="Default the primary book")] = None,
    entity: Annotated[str | None, Query(description="Entity code or id")] = None,
    from_period: Annotated[str | None, Query(description="Period key")] = None,
    to_period: Annotated[str | None, Query(description="Period key")] = None,
    line_type: Annotated[ScheduleLineType | None, Query(description="E-28")] = None,
    schedule_kind: Annotated[ScheduleKind | None, Query(description="E-27")] = None,
    as_of: Annotated[date | None, Query(description="Effective cut-off (API-C-10)")] = None,
    known_at: Annotated[
        datetime | None, Query(description="Record cut-off, RFC 3339 with an offset (API-C-10)")
    ] = None,
) -> ListOut[ScheduleLineOut]:
    """Schedule lines of the latest versions in context; sort ``period_end_date`` (default) or
    ``id``."""
    if known_at is not None and known_at.utcoffset() is None:
        raise invalid("known_at", "Send known_at as an RFC 3339 timestamp with an offset.")
    filters = queries.ScheduleLineFilters(
        contract_id=contract,
        obligation=obligation,
        entity=entity,
        from_period=from_period,
        to_period=to_period,
        line_type=None if line_type is None else line_type.value,
        schedule_kind=None if schedule_kind is None else schedule_kind.value,
    )
    read_params = queries.ReadParams(
        book=None if book is None else book.value, as_of=as_of, known_at=known_at
    )

    def page(session: Session) -> tuple[ListResult, list[ScheduleLineOut]]:
        statement = queries.schedule_lines_statement(session, filters, params=read_params)
        result = paginate(session, statement, SCHEDULE_LINE_LIST, params)
        return result, queries.schedule_items(result.items)

    result, items = queries.read(ctx, page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ScheduleLineOut](items=items, next_cursor=result.next_cursor)
