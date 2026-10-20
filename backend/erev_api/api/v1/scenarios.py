"""API-R-46 scenario catalogue and asynchronous creation."""

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    expected_version,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import forecast_event_set, scenario, scenario_refresh
from erev_api.domain.forecast import archive, creation, refresh_request, scenarios
from erev_api.enums import ScenarioStatus
from erev_api.idempotency.store import Replay
from erev_api.schemas.common import ListOut
from erev_api.schemas.scenarios import (
    ScenarioCreateIn,
    ScenarioInputSummaryOut,
    ScenarioOut,
    ScenarioRefreshIn,
    ScenarioRefreshOut,
    ScenarioRefreshRequestedOut,
    ScenarioRequestedOut,
)
from erev_api.uow import UnitOfWork

SCENARIO_LIST: Final = ListSpec(
    resource="scenarios",
    sort_keys={"id": scenario.c.id, "name": scenario.c.name, "created_at": scenario.c.created_at},
    default_sort="name",
    filters={"status": FilterSpec(name="status", column=scenario.c.status, kind="exact")},
)
router = APIRouter(
    prefix=API_PREFIX, tags=["API-R-46 Scenarios and forecasts"], route_class=GuardedRoute
)


@router.get(
    "/scenarios",
    operation_id="scenarios_list",
    response_model=ListOut[ScenarioOut],
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "validation-failed"
    ),
)
def scenarios_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities("scenario.use"))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[ScenarioStatus | None, Query()] = None,
) -> ListOut[ScenarioOut]:
    """List this workspace's scenarios; filter by status and page by name, created_at or id."""
    result = scenarios.list_scenarios(
        ctx, page=lambda session, statement: paginate(session, statement, SCENARIO_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ScenarioOut](
        items=[ScenarioOut.model_validate(scenarios.scenario_out(row)) for row in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/scenarios",
    operation_id="scenarios_create",
    status_code=202,
    response_model=ScenarioRequestedOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "validation-failed",
        "sandbox-restricted",
        "idempotency-key-reused",
        "idempotency-in-progress",
    ),
)
def scenarios_create(
    body: ScenarioCreateIn,
    cmd: Annotated[CommandContext, Depends(command("scenario.use", all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Copy a production snapshot into a scenario; register it only after the load succeeds."""

    def handle(uow: UnitOfWork) -> ScenarioRequestedOut:
        scenario_id, snapshot_id, job = creation.request(
            uow, name=body.name, purpose=body.purpose, known_at=body.known_at or uow.now
        )
        return ScenarioRequestedOut(
            **job.model_dump(), scenario_id=scenario_id, tenant_snapshot_id=snapshot_id
        )

    return run_command(
        cmd, deps, handle, status_code=202, location=lambda out: f"{API_PREFIX}/jobs/{out.id}"
    )


def _archive_replay(request: Request, ctx: RequestContext, replay: Replay) -> None:
    archive.authorize_replay(ctx, UUID(str(request.path_params["scenario_id"])))


@router.post(
    "/scenarios/{scenario_id}/archive",
    operation_id="scenarios_archive",
    response_model=ScenarioOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "invalid-transition",
        "precondition-required",
        "precondition-failed",
        "validation-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
    ),
)
def scenarios_archive(
    scenario_id: UUID,
    cmd: Annotated[
        CommandContext, Depends(command(per_subject=True, replay_guard=_archive_replay))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Archive an idle scenario as its creator or a Controller; preserve sandbox read access."""

    def handle(uow: UnitOfWork) -> ScenarioOut:
        version = expected_version(cmd.ctx.if_match, "row")
        assert version is not None
        return ScenarioOut.model_validate(
            scenarios.scenario_out(archive.archive(uow, scenario_id, expected_version=version))
        )

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))


@router.post(
    "/scenarios/{scenario_id}/refresh",
    operation_id="scenarios_refresh",
    status_code=202,
    response_model=ScenarioRefreshRequestedOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "invalid-transition",
        "precondition-required",
        "precondition-failed",
        "validation-failed",
        "sandbox-restricted",
        "idempotency-key-reused",
        "idempotency-in-progress",
    ),
)
def scenarios_refresh(
    scenario_id: UUID,
    body: ScenarioRefreshIn,
    cmd: Annotated[CommandContext, Depends(command("scenario.use", all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Refresh from current production and replay one published set before replacing the copy."""

    def handle(uow: UnitOfWork) -> ScenarioRefreshRequestedOut:
        version = expected_version(cmd.ctx.if_match, "row")
        assert version is not None
        return refresh_request.request(
            uow,
            scenario_id=scenario_id,
            input_set_id=body.forecast_event_set_id,
            expected_version=version,
        )

    return run_command(
        cmd, deps, handle, status_code=202, location=lambda out: f"{API_PREFIX}/jobs/{out.id}"
    )


@router.get(
    "/scenarios/{scenario_id}/published-inputs",
    operation_id="scenarios_published_inputs",
    response_model=ListOut[ScenarioInputSummaryOut],
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "not-found", "validation-failed"
    ),
)
def scenarios_published_inputs(
    scenario_id: UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities("scenario.use"))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[ScenarioInputSummaryOut]:
    spec = ListSpec(
        resource="scenario-published-inputs",
        filters={},
        default_sort="-created_at",
        sort_keys={
            "id": forecast_event_set.c.id,
            "created_at": forecast_event_set.c.created_at,
        },
    )
    result = scenarios.published_inputs(
        ctx, scenario_id, page=lambda session, statement: paginate(session, statement, spec, params)
    )
    response.headers["Cache-Control"] = "no-store"
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut(
        items=[ScenarioInputSummaryOut.model_validate(row) for row in result.items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/scenarios/{scenario_id}/refreshes",
    operation_id="scenarios_refreshes",
    response_model=ListOut[ScenarioRefreshOut],
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "not-found", "validation-failed"
    ),
)
def scenarios_refreshes(
    scenario_id: UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities("scenario.use"))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[ScenarioRefreshOut]:
    spec = ListSpec(
        resource="scenario-refreshes",
        filters={},
        default_sort="-created_at",
        sort_keys={"id": scenario_refresh.c.id, "created_at": scenario_refresh.c.created_at},
    )
    result = scenarios.refreshes(
        ctx, scenario_id, page=lambda session, statement: paginate(session, statement, spec, params)
    )
    response.headers["Cache-Control"] = "no-store"
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut(
        items=[ScenarioRefreshOut.model_validate(row) for row in result.items],
        next_cursor=result.next_cursor,
    )
