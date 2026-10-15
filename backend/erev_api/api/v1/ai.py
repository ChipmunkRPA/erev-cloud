"""API-R-47: enqueue number explanations; all provider work belongs to the worker."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

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
from erev_api.domain.ai import commands
from erev_api.domain.platform.jobs import job_out_of
from erev_api.schemas.ai import AIExplanationIn
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
