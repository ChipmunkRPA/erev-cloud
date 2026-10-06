"""API-R-29 Obligations: obligation reads and the SSP override request.

04 §15.3 API-R-29, §16.2 API-S-Obligation, API-S-ScheduleLine and the obligation commands, §16.3
API-S-Event, API-C-09 to API-C-11; PRD ACT-21, BR-SSP-03; BUILD_SPEC CTR-15. Reads need
``contract.read``; ``request-ssp-override`` needs ``contract.create``, which the handler checks for
the contracting entity, and takes ``Idempotency-Key``. Computed reads take ``book``, ``as_of`` and
``known_at`` (API-C-10, API-C-11); ``known_at`` needs an offset, else 422 API-C-09.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    run_command,
)
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
from erev_api.clock import Clock, get_clock
from erev_api.db.tables import contract_event, obligation_version, schedule_line
from erev_api.domain.contracts import obligations, queries
from erev_api.domain.policies import overrides
from erev_api.enums import BookCode
from erev_api.schemas.common import ListOut
from erev_api.schemas.contracts import ObligationOut, ScheduleLineOut
from erev_api.schemas.events import EventOut
from erev_api.schemas.obligations import MaterialRightOut, SspOverrideIn, SspOverrideOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-29 Obligations"
READ: Final = "contract.read"
CREATE: Final = "contract.create"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_TIME_TRAVEL: Final = frozenset({"book", "as_of", "known_at"})
VERSION_LIST: Final = ListSpec(
    resource="obligation-versions",
    sort_keys={"id": obligation_version.c.id, "version_no": obligation_version.c.version_no},
    default_sort="-version_no",
    filters={},
    custom_filters=frozenset({"book"}),
)
SCHEDULE_LIST: Final = ListSpec(
    resource="obligation-schedule",
    sort_keys={"id": schedule_line.c.id, "period_end_date": schedule_line.c.period_end_date},
    default_sort="period_end_date",
    filters={},
    custom_filters=_TIME_TRAVEL,
)
EVENT_LIST: Final = ListSpec(
    resource="obligation-events",
    sort_keys={"id": contract_event.c.id, "record_seq": contract_event.c.record_seq},
    default_sort="record_seq",
    filters={},
    custom_filters=frozenset({"known_at"}),
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type AppClock = Annotated[Clock, Depends(get_clock)]
type Params = Annotated[ListParams, Depends(list_params)]
type Book = Annotated[BookCode | None, Query(description="Default the primary book (API-C-11)")]
type AsOf = Annotated[date | None, Query(description="Effective cut-off (API-C-10)")]
type KnownAt = Annotated[
    datetime | None, Query(description="Record cut-off, RFC 3339 with an offset (API-C-10)")
]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _read_params(
    book: BookCode | None, as_of: date | None, known_at: datetime | None
) -> queries.ReadParams:
    if known_at is not None and known_at.utcoffset() is None:
        raise invalid("known_at", "Send known_at as an RFC 3339 timestamp with an offset.")
    return queries.ReadParams(
        book=None if book is None else book.value, as_of=as_of, known_at=known_at
    )


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


@router.get(
    "/contracts/{contract_id}/obligations",
    operation_id="contract_obligations_list",
    response_model=ListOut[ObligationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_obligations_list(
    contract_id: uuid.UUID,
    ctx: ReadContext,
    clock: AppClock,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ListOut[ObligationOut]:
    """API-S-Obligation of every obligation of the contract at the version in context; one page."""
    params = _read_params(book, as_of, known_at)
    items = queries.read(
        ctx,
        lambda session: obligations.contract_obligations(
            session, contract_id, params=params, now=clock.now()
        ),
    )
    return ListOut[ObligationOut](items=items, next_cursor=None)


@router.get(
    "/obligations/{obligation_id}",
    operation_id="obligations_get",
    response_model=ObligationOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def obligations_get(
    obligation_id: uuid.UUID,
    ctx: ReadContext,
    clock: AppClock,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ObligationOut:
    """API-S-Obligation at the version in context (API-C-10); 404 while the book has no version."""
    params = _read_params(book, as_of, known_at)
    return queries.read(
        ctx,
        lambda session: obligations.obligation_out(
            session, obligation_id, params=params, now=clock.now()
        ),
    )


@router.get(
    "/obligations/{obligation_id}/versions",
    operation_id="obligation_versions_list",
    response_model=ListOut[ObligationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def obligation_versions_list(
    obligation_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    clock: AppClock,
    params: Params,
    book: Book = None,
) -> ListOut[ObligationOut]:
    """One API-S-Obligation per contract version of the book; sort ``version_no`` (default
    ``-version_no``) or ``id``."""

    def load(session: Session) -> tuple[ListResult, list[ObligationOut]]:
        statement = obligations.versions_statement(
            session, obligation_id, book=None if book is None else book.value
        )
        result = paginate(session, statement, VERSION_LIST, params)
        return result, obligations.version_items(
            session, obligation_id, result.items, now=clock.now()
        )

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[ObligationOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/obligations/{obligation_id}/schedule",
    operation_id="obligation_schedule_list",
    response_model=ListOut[ScheduleLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def obligation_schedule_list(
    obligation_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ListOut[ScheduleLineOut]:
    """API-S-ScheduleLine rows of the obligation at the version in context; sort
    ``period_end_date`` (default) or ``id``."""
    read_params = _read_params(book, as_of, known_at)

    def load(session: Session) -> tuple[ListResult, list[ScheduleLineOut]]:
        statement = obligations.schedule_statement(session, obligation_id, params=read_params)
        result = paginate(session, statement, SCHEDULE_LIST, params)
        return result, queries.schedule_items(result.items)

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[ScheduleLineOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/obligations/{obligation_id}/events",
    operation_id="obligation_events_list",
    response_model=ListOut[EventOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def obligation_events_list(
    obligation_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    known_at: KnownAt = None,
) -> ListOut[EventOut]:
    """API-S-Event of the stream events naming the obligation, recorded by ``known_at``; sort
    ``record_seq`` (default) or ``id``. Each item is the event as ``GET /events/{id}`` answers
    it; ``obligation_keys`` also names the obligation of an event that names it only in its
    payload."""
    read_params = _read_params(None, None, known_at)

    def load(session: Session) -> tuple[ListResult, list[EventOut]]:
        statement = obligations.events_statement(
            session, obligation_id, known_at=read_params.known_at
        )
        result = paginate(session, statement, EVENT_LIST, params)
        return result, obligations.event_items(session, result.items)

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[EventOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/obligations/{obligation_id}/material-right",
    operation_id="obligation_material_right_get",
    response_model=MaterialRightOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def obligation_material_right_get(obligation_id: uuid.UUID, ctx: ReadContext) -> MaterialRightOut:
    """The obligation's material right (T-CON-14); 404 while none exists (L4-2-Q-7)."""
    return queries.read(ctx, lambda session: obligations.material_right_out(session, obligation_id))


@router.post(
    "/obligations/{obligation_id}/request-ssp-override",
    operation_id="obligations_request_ssp_override",
    response_model=SspOverrideOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def obligations_request_ssp_override(
    obligation_id: uuid.UUID,
    body: SspOverrideIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request approval of subject ``SSP_OVERRIDE`` for an APPROVED SSP book version with a
    justification (REQ-SSP-006; PRD BR-SSP-03); 200 ``{approval_request_id}``."""

    def handle(uow: UnitOfWork) -> SspOverrideOut:
        request_id = overrides.request_ssp_override(
            uow,
            obligation_id,
            ssp_book_version_id=body.ssp_book_version_id,
            justification=body.justification,
        )
        return SspOverrideOut(approval_request_id=request_id)

    return run_command(cmd, deps, handle)
