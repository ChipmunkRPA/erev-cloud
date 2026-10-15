"""API-R-47: number-explanation submission and authorized retained proposal reads."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

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
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.domain.ai import commands, queries
from erev_api.domain.platform.jobs import job_out_of
from erev_api.schemas.ai import AIExplanationIn, AIProposalOut, AIProposalRejectIn
from erev_api.schemas.common import JobOut
from erev_api.uow import UnitOfWork

router = APIRouter(prefix=API_PREFIX, tags=["API-R-47 AI"], route_class=GuardedRoute)


@router.post(
    "/ai/explanations",
    operation_id="ai_explanations_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "validation-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
        "ai-disabled",
    ),
)
def explanations_create(
    body: AIExplanationIn,
    cmd: Annotated[CommandContext, Depends(command("ai.use"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Queue a number explanation after checking the human's current source access."""

    def handle(uow: UnitOfWork) -> JobOut:
        job_id = commands.request_explanation(
            uow,
            object_type=body.object_type,
            object_id=body.id,
            measure=body.measure,
            period=body.period,
            platform_kill_switch=deps.settings.ai_kill_switch,
        )
        return job_out_of(uow.session, job_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda result: f"{API_PREFIX}/jobs/{result.id}",
    )


@router.get(
    "/ai/proposals/{id}",
    operation_id="ai_proposals_get",
    response_model=AIProposalOut,
    responses=problem_responses("unauthenticated", "session-expired", "forbidden", "not-found"),
)
def proposals_get(
    id: UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
) -> AIProposalOut:
    """Read retained number explanations under the caller's current source permissions."""
    out = queries.proposal(ctx.principal, id)
    response.headers["ETag"] = row_etag(out.row_version)
    return out


def _proposal_reject_access(
    id: UUID,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
) -> None:
    """Check current source access before command middleware can replay a saved response."""
    queries.proposal(ctx.principal, id)


@router.post(
    "/ai/proposals/{id}/reject",
    operation_id="ai_proposals_reject",
    dependencies=[Depends(_proposal_reject_access)],
    response_model=AIProposalOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "validation-failed",
        "invalid-transition",
        "precondition-required",
        "precondition-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
    ),
)
def proposals_reject(
    id: UUID,
    body: AIProposalRejectIn,
    cmd: Annotated[CommandContext, Depends(command("ai.use", precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Reject a number explanation with a reason and its current row-version ETag."""

    def handle(uow: UnitOfWork) -> AIProposalOut:
        return commands.reject_proposal(
            uow,
            id,
            reason=body.reason,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=lambda result: row_etag(result.row_version))
