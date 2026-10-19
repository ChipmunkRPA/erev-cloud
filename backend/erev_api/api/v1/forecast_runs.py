"""API-R-46 scenario forecast execution and saved output catalogue."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

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
from erev_api.api.lists import TOTAL_COUNT_HEADER, ListParams, ListSpec, list_params, paginate
from erev_api.auth.dependencies import require_all_entities, require_for_entity
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import forecast_run
from erev_api.domain.forecast import event_sets, runs
from erev_api.problems import Problem
from erev_api.schemas.common import ListOut
from erev_api.schemas.forecast_runs import (
    ForecastRunCreateIn,
    ForecastRunOut,
    ForecastRunRequestedOut,
)
from erev_api.uow import UnitOfWork

router = APIRouter(
    prefix=API_PREFIX, tags=["API-R-46 Scenarios and forecasts"], route_class=GuardedRoute
)
PROBLEMS = problem_responses(
    "unauthenticated",
    "session-expired",
    "forbidden",
    "not-found",
    "invalid-transition",
    "sandbox-restricted",
    "precondition-failed",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
type Reader = Annotated[RequestContext, Depends(require_all_entities("scenario.use"))]
SPEC = ListSpec(
    resource="forecast-runs",
    sort_keys={"id": forecast_run.c.id, "created_at": forecast_run.c.created_at},
    default_sort="-created_at",
    filters={},
)


def visible(ctx: RequestContext, row: dict[str, Any]) -> ForecastRunOut:
    for entity in row["parameters"]["entity_ids"]:
        require_for_entity(ctx, "report.run", UUID(entity))
    return ForecastRunOut.model_validate(row)


@router.post(
    "/forecast-runs",
    operation_id="forecast_runs_create",
    status_code=202,
    response_model=ForecastRunRequestedOut,
    responses=PROBLEMS,
)
def create_run(
    body: ForecastRunCreateIn,
    cmd: Annotated[CommandContext, Depends(command("scenario.use", all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    def handle(uow: UnitOfWork) -> ForecastRunRequestedOut:
        return runs.request(uow, body)

    return run_command(
        cmd, deps, handle, status_code=202, location=lambda out: f"{API_PREFIX}/jobs/{out.id}"
    )


@router.get(
    "/forecast-runs/{run_id}",
    operation_id="forecast_runs_get",
    response_model=ForecastRunOut,
    responses=PROBLEMS,
)
def get_run(run_id: UUID, ctx: Reader) -> ForecastRunOut:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        event_sets._scenario(session, ctx.principal.db_context)
        row = (
            session.execute(select(forecast_run).where(forecast_run.c.id == run_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found")
        return visible(ctx, dict(row))


@router.get(
    "/forecast-runs",
    operation_id="forecast_runs_list",
    response_model=ListOut[ForecastRunOut],
    responses=PROBLEMS,
)
def list_runs(
    response: Response, ctx: Reader, params: Annotated[ListParams, Depends(list_params)]
) -> ListOut[ForecastRunOut]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        event_sets._scenario(session, ctx.principal.db_context)
        scope = ctx.principal.permission_scopes.get("report.run")
        statement = select(forecast_run)
        if scope is None:
            raise Problem("forbidden")
        if scope != "*":
            # JSONB containment: every requested entity must still be in the reader's scope.
            from sqlalchemy import cast
            from sqlalchemy.dialects.postgresql import JSONB

            statement = statement.where(
                forecast_run.c.parameters["entity_ids"].contained_by(
                    cast([str(e) for e in scope], JSONB)
                )
            )
        result = paginate(session, statement, SPEC, params)
        if result.total_count is not None:
            response.headers[TOTAL_COUNT_HEADER] = str(result.total_count)
        return ListOut[ForecastRunOut](
            items=[visible(ctx, dict(row)) for row in result.items], next_cursor=result.next_cursor
        )
