"""API-R-30 Events: fact capture, previews, voids and event submissions.

04 §15.3 API-R-30, §16.3 API-S-EventAppend and API-S-Event, T-CON-24, table 3.4-R, API-C-04,
API-C-08, API-C-12; dev-guide DG-CMD-09, DG-CMD-12; BUILD_SPEC CTR-5. Reads need
``contract.read``; commands need ``event.record``, which the handlers check for the contracting
entity. ``POST /contracts/{id}/events`` and ``…/preview`` take ``If-Match:
"s<head_stream_version>"``. An append answers 201, or 202 API-S-Job when the computation is
deferred (RCP-18); a preview answers 202.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    contract_etag,
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
from erev_api.db.tables import contract_event, event_submission
from erev_api.domain.contracts import events, queries, repo
from erev_api.enums import ContractEventType, ModificationStatus
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.events import (
    EventAppendIn,
    EventOut,
    EventsAppendedOut,
    EventSubmissionOut,
    EventVoidRequestIn,
    SubmissionCreatedOut,
    SubmissionWithdrawIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-30 Events"
READ: Final = "contract.read"
RECORD: Final = "event.record"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
)
_PRECONDITION_PROBLEMS: Final = ("precondition-failed", "precondition-required")
EVENT_LIST: Final = ListSpec(
    resource="contract-events",
    sort_keys={
        "id": contract_event.c.id,
        "stream_version": contract_event.c.stream_version,
        "effective_date": contract_event.c.effective_date,
        "recorded_at": contract_event.c.recorded_at,
    },
    default_sort="stream_version",
    filters={},
    custom_filters=frozenset(
        {"known_at", "effective_from", "effective_to", "event_type", "obligation"}
    ),
)
SUBMISSION_LIST: Final = ListSpec(
    resource="event-submissions",
    sort_keys={"id": event_submission.c.id, "created_at": event_submission.c.created_at},
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"contract", "status"}),
)
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


def _job_headers(job: JobOut) -> dict[str, str]:
    """API-C-12: ``Location`` of the job."""
    return {"Location": JOB_PATH.format(job_id=job.id)}


@router.get(
    "/contracts/{contract_id}/events",
    operation_id="contract_events_list",
    response_model=ListOut[EventOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_events_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    known_at: Annotated[
        datetime | None, Query(description="Events recorded by then (API-C-10)")
    ] = None,
    effective_from: Annotated[date | None, Query()] = None,
    effective_to: Annotated[date | None, Query()] = None,
    event_type: Annotated[list[ContractEventType] | None, Query(description="E-03")] = None,
    obligation: Annotated[str | None, Query(description="Obligation key")] = None,
) -> ListOut[EventOut]:
    """The contract's events; sort ``stream_version`` (default), ``effective_date``,
    ``recorded_at`` or ``id``."""
    if known_at is not None and known_at.utcoffset() is None:
        raise invalid("known_at", "Send known_at as an RFC 3339 timestamp with an offset.")

    def page(session: Session) -> tuple[ListResult, list[EventOut]]:
        repo.get_contract(session, contract_id)
        statement = events.events_statement(
            contract_id,
            known_at=known_at,
            effective_from=effective_from,
            effective_to=effective_to,
            event_types=tuple(event_type or ()),
            obligation_key=obligation,
        )
        result = paginate(session, statement, EVENT_LIST, params)
        return result, events.event_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[EventOut](items=items, next_cursor=result.next_cursor)


def _append_status(result: Any) -> int:
    return 202 if isinstance(result, JobOut) else 201


def _append_headers(contract_id: uuid.UUID, result: Any) -> dict[str, str]:
    if isinstance(result, JobOut):
        return _job_headers(result)
    if isinstance(result, SubmissionCreatedOut):
        return {"Location": f"{API_PREFIX}/event-submissions/{result.event_submission_id}"}
    assert isinstance(result, EventsAppendedOut)
    return {
        "Location": f"{API_PREFIX}/contracts/{contract_id}/events",
        "ETag": contract_etag(result.contract.head_stream_version),
    }


@router.post(
    "/contracts/{contract_id}/events",
    operation_id="contract_events_append",
    status_code=201,
    response_model=EventsAppendedOut | SubmissionCreatedOut,
    responses={
        **problem_responses(*_COMMAND_PROBLEMS, *_PRECONDITION_PROBLEMS),
        202: {"model": JobOut, "description": "The computation runs as a job (API-C-12)"},
    },
)
def contract_events_append(
    contract_id: uuid.UUID,
    body: EventAppendIn,
    cmd: Annotated[CommandContext, Depends(command(RECORD, precondition="contract"))],
    deps: Deps,
) -> Response:
    """Append 1 to 500 events atomically and compute the group (DG-CMD-09): 201 with
    ``computation.status``, or 202 API-S-Job when the group has more than 200 obligations or the
    engine takes more than 30 seconds (RCP-18). An append naming ``LINE_ATTRIBUTES_CHANGED`` appends
    nothing and answers 201 ``{event_submission_id, approval_request_id}`` (ATTRIBUTE_CHANGE); a
    locked field of an active contract answers 409 ``field-locked-after-activation`` (CTR-10), and
    a change that names an SSP version answers 422 ``REQ-SSP-006``: the SSP override command sets
    it (04 §16.3 rev 1.231). A
    delivery, progress, milestone, usage, cost or return event sent by a signed-in person appends
    nothing either: the request waits whole for another user's approval (MANUAL_EVENT; 04 §16.3
    "Manual events"), with ``evidence_file_ids`` for a progress, milestone, cost or acceptance
    event (422 ``REQ-DAT-014`` without). An API client's events are appended directly (CTR-6)."""

    def handle(uow: UnitOfWork) -> EventsAppendedOut | JobOut | SubmissionCreatedOut:
        recorded = events.record_events(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )
        if recorded.submission is not None:
            return recorded.submission
        if recorded.job is not None:
            return recorded.job
        assert recorded.appended is not None
        return recorded.appended

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        status_of=_append_status,
        extra_headers=lambda result: _append_headers(contract_id, result),
    )


@router.post(
    "/contracts/{contract_id}/events/preview",
    operation_id="contract_events_preview",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, *_PRECONDITION_PROBLEMS),
)
def contract_events_preview(
    contract_id: uuid.UUID,
    body: EventAppendIn,
    cmd: Annotated[CommandContext, Depends(command(RECORD, precondition="contract"))],
    deps: Deps,
) -> Response:
    """Validate the events as an append would, append nothing and defer the dry run; the job's
    ``result.summary`` is API-S-ImpactSummary (04 §16.3; SCREENS R-16)."""

    def handle(uow: UnitOfWork) -> JobOut:
        return events.request_preview(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )

    return run_command(cmd, deps, handle, status_code=202, extra_headers=_job_headers)


@router.get(
    "/events/{event_id}",
    operation_id="events_get",
    response_model=EventOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def events_get(event_id: uuid.UUID, ctx: ReadContext) -> EventOut:
    """API-S-Event with the computation that first included it."""
    return queries.read(ctx, lambda session: events.get_event(session, event_id))


@router.post(
    "/events/{event_id}/request-void",
    operation_id="events_request_void",
    status_code=201,
    response_model=SubmissionCreatedOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def events_request_void(
    event_id: uuid.UUID,
    body: EventVoidRequestIn,
    cmd: Annotated[CommandContext, Depends(command(RECORD))],
    deps: Deps,
) -> Response:
    """Store ``EVENT_VOIDED`` in an event submission and submit it for approval (subject
    ``MANUAL_EVENT``); a reason outside table 3.4-R answers 422 ``REASON_CODE_NOT_ALLOWED``. The
    void is taken for the twelve fact-capture types the events route records; an event of another
    type has a command of its own and answers 409 ``invalid-transition`` with the sentence that
    names what undoes it (04 §16.3 "Voids on this route", rev 1.231)."""

    def handle(uow: UnitOfWork) -> SubmissionCreatedOut:
        return events.request_void(uow, event_id=event_id, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/event-submissions/{out.event_submission_id}",
    )


@router.get(
    "/event-submissions",
    operation_id="event_submissions_list",
    response_model=ListOut[EventSubmissionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def event_submissions_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    contract: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[list[ModificationStatus] | None, Query()] = None,
) -> ListOut[EventSubmissionOut]:
    """Event submissions (T-CON-24); sort ``id`` (default ``-id``) or ``created_at``."""

    def page(session: Session) -> tuple[ListResult, list[EventSubmissionOut]]:
        statement = events.submissions_statement(contract_id=contract, statuses=tuple(status or ()))
        result = paginate(session, statement, SUBMISSION_LIST, params)
        return result, events.submission_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[EventSubmissionOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/event-submissions/{submission_id}",
    operation_id="event_submissions_get",
    response_model=EventSubmissionOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def event_submissions_get(submission_id: uuid.UUID, ctx: ReadContext) -> EventSubmissionOut:
    return queries.read(ctx, lambda session: events.get_submission(session, submission_id))


@router.post(
    "/event-submissions/{submission_id}/withdraw",
    operation_id="event_submissions_withdraw",
    response_model=EventSubmissionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def event_submissions_withdraw(
    submission_id: uuid.UUID,
    body: SubmissionWithdrawIn,
    cmd: Annotated[CommandContext, Depends(command(RECORD))],
    deps: Deps,
) -> Response:
    """The preparer withdraws a draft or submitted submission; it becomes ``VOIDED``."""

    def handle(uow: UnitOfWork) -> EventSubmissionOut:
        return events.withdraw_submission(uow, submission_id=submission_id, body=body)

    return run_command(cmd, deps, handle)
