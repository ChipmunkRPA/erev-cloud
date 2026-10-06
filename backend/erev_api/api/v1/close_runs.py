"""API-R-39 Close runs: the resumable close state machine of an entity, book and period.

04 §15.3 API-R-39, §16.8 API-S-CloseRunCreate, API-S-CloseRun, "Close run commands"; T-CLS-01;
PRD SM-14, NFR-14; SCREENS_B §1.2; BUILD_SPEC CLO-19. Reads need ``contract.read`` and answer the
runs of the entities that permission covers. ``POST /close-runs``, ``resume`` and ``cancel`` need
``period.close`` for the run's entity. A start answers 202 API-S-Job with the job's ``Location``
and the run id header, or 200 API-S-CloseRun when the entity, book and period already have an
active run; ``resume`` answers 202 API-S-Job likewise; ``cancel`` answers the run.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

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
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import close_run, legal_entity, period
from erev_api.domain.close import close_runs
from erev_api.enums import BookCode, CloseRunStatus
from erev_api.schemas.close_runs import CloseRunCancelIn, CloseRunCreateIn, CloseRunOut
from erev_api.schemas.common import JobOut, ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-39 Close runs"
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
CLOSE_RUN_ID_HEADER: Final = "X-Erev-Close-Run-Id"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "invalid-transition",
)

CLOSE_RUN_LIST: Final = ListSpec(
    resource="close-runs",
    sort_keys={
        "id": close_run.c.id,
        "created_at": close_run.c.created_at,
        "close_run_no": close_run.c.close_run_no,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=close_run.c.status,
            kind="in",
            choices=frozenset(member.value for member in CloseRunStatus),
        ),
    },
    custom_filters=frozenset({"entity", "book", "period"}),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)
ReadContext = Annotated[RequestContext, Depends(require(close_runs.READ_PERMISSION))]
Params = Annotated[ListParams, Depends(list_params)]
CloseCommand = Annotated[CommandContext, Depends(command(close_runs.CLOSE_PERMISSION))]
Deps = Annotated[KernelDeps, Depends(kernel_deps)]


def _etag(out: CloseRunOut) -> str:
    return row_etag(out.row_version)


@router.get(
    "/close-runs",
    operation_id="close_runs_list",
    response_model=ListOut[CloseRunOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def close_runs_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    entity: Annotated[list[str] | None, Query(description="Entity code; repeatable")] = None,
    book: Annotated[BookCode | None, Query()] = None,
    period_key: Annotated[str | None, Query(alias="period", description="Period key")] = None,
    status: Annotated[list[CloseRunStatus] | None, Query()] = None,
) -> ListOut[CloseRunOut]:
    """The close runs of the caller's ``contract.read`` entities, newest first; sort ``id``
    (default ``-id``), ``created_at`` or ``close_run_no``."""
    del status  # applied by ``paginate`` through CLOSE_RUN_LIST
    statement = close_runs.statement(ctx.principal)
    if entity:
        statement = statement.where(legal_entity.c.code.in_(entity))
    if book is not None:
        statement = statement.where(close_run.c.book_code == book.value)
    if period_key is not None:
        statement = statement.where(period.c.period_key == period_key)

    def page(session: Session) -> tuple[ListResult, list[CloseRunOut]]:
        result = paginate(session, statement, CLOSE_RUN_LIST, params)
        return result, close_runs.outs(session, [dict(row) for row in result.items])

    result, items = close_runs.read(ctx, page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[CloseRunOut](items=items, next_cursor=result.next_cursor)


def _started_status(result: Any) -> int:
    return 202 if isinstance(result, JobOut) else 200


@router.post(
    "/close-runs",
    operation_id="close_runs_create",
    status_code=202,
    response_model=JobOut,
    responses={
        **problem_responses(*_COMMAND_PROBLEMS),
        200: {
            "model": CloseRunOut,
            "description": "The run that is already active for the entity, book and period",
        },
    },
)
def close_runs_create(body: CloseRunCreateIn, cmd: CloseCommand, deps: Deps) -> Response:
    """Start the close run of an entity, book and period: 202 API-S-Job ``CLOSE_RUN``; the job
    executes the steps of T-CLS-01 in order. While a run of the entity, book and period is
    ``PENDING``, ``RUNNING`` or ``BLOCKED`` no second run starts: 200 API-S-CloseRun of that run.
    """
    started: dict[str, uuid.UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut | CloseRunOut:
        found = close_runs.start(uow, body)
        started["run_id"] = found.run_id
        if found.job is not None:
            return found.job
        return close_runs.get(uow.session, uow.principal, found.run_id)

    def headers(result: Any) -> dict[str, str]:
        found = {CLOSE_RUN_ID_HEADER: str(started["run_id"])}
        if isinstance(result, JobOut):
            found["Location"] = JOB_PATH.format(job_id=result.id)
        return found

    return run_command(
        cmd, deps, handle, status_code=202, status_of=_started_status, extra_headers=headers
    )


@router.get(
    "/close-runs/{close_run_id}",
    operation_id="close_runs_get",
    response_model=CloseRunOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def close_runs_get(close_run_id: uuid.UUID, response: Response, ctx: ReadContext) -> CloseRunOut:
    """API-S-CloseRun with its steps, counts and newest job, and its ``ETag``."""
    out = close_runs.read(ctx, lambda session: close_runs.get(session, ctx.principal, close_run_id))
    response.headers["ETag"] = _etag(out)
    return out


@router.post(
    "/close-runs/{close_run_id}/resume",
    operation_id="close_runs_resume",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def close_runs_resume(close_run_id: uuid.UUID, cmd: CloseCommand, deps: Deps) -> Response:
    """Resume a ``FAILED`` or ``BLOCKED`` run: 202 API-S-Job ``CLOSE_RUN``; the job continues at
    the first step that has not succeeded, and the steps that have are not executed again."""

    def handle(uow: UnitOfWork) -> JobOut:
        return close_runs.resume(uow, close_run_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {
            "Location": JOB_PATH.format(job_id=job.id),
            CLOSE_RUN_ID_HEADER: str(close_run_id),
        },
    )


@router.post(
    "/close-runs/{close_run_id}/cancel",
    operation_id="close_runs_cancel",
    response_model=CloseRunOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def close_runs_cancel(
    close_run_id: uuid.UUID, body: CloseRunCancelIn, cmd: CloseCommand, deps: Deps
) -> Response:
    """Cancel a close run that has not ended: a running one stops after its current step, and the
    steps already completed stay recorded; one whose job has not started, and a blocked one, is
    cancelled at once."""

    def handle(uow: UnitOfWork) -> CloseRunOut:
        return close_runs.cancel(uow, close_run_id, body)

    return run_command(cmd, deps, handle, etag=_etag)
