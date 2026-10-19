"""API-R-46 scenario listing; creation and refresh are separate workflows."""

from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
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
from erev_api.db.tables import scenario
from erev_api.domain.forecast import scenarios
from erev_api.enums import ScenarioStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.scenarios import ScenarioOut

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
