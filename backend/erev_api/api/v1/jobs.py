"""API-R-11 Jobs: long operations and their cancellation.

04 §15.3 API-R-11, §16.0 API-S-Job, API-C-12, T-PLT-27; 05 JOB-05; BUILD_SPEC PLF-22. A job is
visible to its initiator and to holders of ``audit.read`` for all entities; only the initiator
cancels it.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select
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
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require_authenticated
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import job
from erev_api.domain.platform import jobs
from erev_api.enums import JobKind, JobState
from erev_api.schemas.common import JobOut, ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-11 Jobs"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
JOB_LIST: Final = ListSpec(
    resource="jobs",
    sort_keys={"id": job.c.id, "created_at": job.c.created_at},
    default_sort="-id",
    filters={
        "kind": FilterSpec(
            name="kind",
            column=job.c.kind,
            kind="exact",
            choices=frozenset(kind.value for kind in JobKind),
        ),
        "state": FilterSpec(
            name="state",
            column=job.c.state,
            kind="exact",
            choices=frozenset(state.value for state in JobState),
        ),
        "subject_type": FilterSpec(name="subject_type", column=job.c.subject_type, kind="exact"),
        "subject_id": FilterSpec(name="subject_id", column=job.c.subject_id, kind="exact"),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/jobs",
    operation_id="jobs_list",
    response_model=ListOut[JobOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def jobs_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    params: Annotated[ListParams, Depends(list_params)],
    kind: Annotated[list[JobKind] | None, Query(description="Repeat for IN")] = None,
    state: Annotated[list[JobState] | None, Query(description="Repeat for IN")] = None,
    subject_type: Annotated[str | None, Query()] = None,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ListOut[JobOut]:
    """The caller's jobs, or every job for holders of ``audit.read`` for all entities; sort
    ``id`` (default ``-id``) or ``created_at``."""

    def page(session: Session, statement: Select[Any]) -> tuple[ListResult, list[JobOut]]:
        result = paginate(session, statement, JOB_LIST, params)
        return result, jobs.job_outs(session, result.items, reader=ctx.principal)

    result, items = jobs.list_jobs(ctx, page=page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[JobOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/jobs/{job_id}",
    operation_id="jobs_get",
    response_model=JobOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def jobs_get(
    job_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
) -> JobOut:
    """One job: state, progress, result link and failure problem."""
    return jobs.get_job(ctx, job_id)


@router.post(
    "/jobs/{job_id}/cancel",
    operation_id="jobs_cancel",
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def jobs_cancel(
    job_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Cancel a job the caller started: a queued job at once, a running job after its current
    chunk."""

    def handle(uow: UnitOfWork) -> JobOut:
        return jobs.cancel_job(uow, job_id)

    return run_command(cmd, deps, handle)
