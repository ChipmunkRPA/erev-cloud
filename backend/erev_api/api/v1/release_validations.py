"""Advance the current engine release's tenant validation without bypassing approval."""

from dataclasses import asdict
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
from erev_api.domain.contracts import validation_orchestration
from erev_api.schemas.release_validations import (
    ReleaseValidationAdvanceIn,
    ReleaseValidationAdvanceOut,
)
from erev_api.uow import UnitOfWork

router = APIRouter(prefix=API_PREFIX, tags=["API-R-41 Reports"], route_class=GuardedRoute)
type AdvanceCommand = Annotated[CommandContext, Depends(command("report.run", all_entities=True))]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]


@router.post(
    "/release-validations/current/advance",
    operation_id="release_validations_advance",
    response_model=ReleaseValidationAdvanceOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "mfa-required",
        "validation-failed",
        "invalid-transition",
        "idempotency-key-reused",
        "idempotency-in-progress",
        "release-mismatch",
        "lock-conflict",
    ),
)
def release_validations_advance(
    body: ReleaseValidationAdvanceIn, cmd: AdvanceCommand, deps: Deps
) -> Response:
    """Advance one durable stage for the running release, with report.run across all entities.

    Use the same idempotency key for delivery retries and a new key for the next stage.
    PREPARATION_REQUIRED never enables a historical tenant or a same-version rebuild.
    MAJOR differences wait for the existing independent approval workflow.
    """

    def advance(uow: UnitOfWork) -> ReleaseValidationAdvanceOut:
        result = validation_orchestration.advance(uow, retry_report=body.retry_report)
        return ReleaseValidationAdvanceOut.model_validate(asdict(result))

    return run_command(cmd, deps, advance)
