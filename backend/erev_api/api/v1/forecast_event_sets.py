"""API-R-46 versioned forecast input sets."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

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
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import forecast_event_set as sets
from erev_api.domain.forecast import event_sets
from erev_api.enums import ConfigStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.forecast_event_sets import EventSetCreateIn, EventSetOut, EventSetUpdateIn
from erev_api.uow import UnitOfWork

router = APIRouter(
    prefix=API_PREFIX, tags=["API-R-46 Scenarios and forecasts"], route_class=GuardedRoute
)
PROBLEMS = problem_responses(
    "unauthenticated",
    "session-expired",
    "forbidden",
    "sandbox-restricted",
    "validation-failed",
    "not-found",
    "invalid-transition",
    "precondition-required",
    "precondition-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
SPEC = ListSpec(
    resource="forecast-event-sets",
    sort_keys={
        "id": sets.c.id,
        "code": sets.c.code,
        "version_no": sets.c.version_no,
        "created_at": sets.c.created_at,
    },
    default_sort="code",
    filters={"status": FilterSpec(name="status", column=sets.c.status, kind="exact")},
)
type ReadContext = Annotated[RequestContext, Depends(require_all_entities("scenario.use"))]
type Command = Annotated[CommandContext, Depends(command("scenario.use", all_entities=True))]
type UpdateCommand = Annotated[
    CommandContext, Depends(command("scenario.use", all_entities=True, precondition="row"))
]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]


@router.get(
    "/forecast-event-sets",
    operation_id="forecast_event_sets_list",
    response_model=ListOut[EventSetOut],
    responses=PROBLEMS,
)
def list_sets(
    response: Response,
    ctx: ReadContext,
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[ConfigStatus | None, Query()] = None,
) -> ListOut[EventSetOut]:
    result = event_sets.listing(
        ctx, page=lambda session, statement: paginate(session, statement, SPEC, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[EventSetOut](
        items=[EventSetOut.model_validate(row) for row in result.items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/forecast-event-sets/{event_set_id}",
    operation_id="forecast_event_sets_get",
    response_model=EventSetOut,
    responses=PROBLEMS,
)
def get_set(event_set_id: UUID, response: Response, ctx: ReadContext) -> EventSetOut:
    out = EventSetOut.model_validate(event_sets.get(ctx, event_set_id))
    response.headers["ETag"] = row_etag(out.row_version)
    return out


@router.post(
    "/forecast-event-sets",
    operation_id="forecast_event_sets_create",
    status_code=201,
    response_model=EventSetOut,
    responses=PROBLEMS,
)
def create_set(body: EventSetCreateIn, cmd: Command, deps: Deps) -> Response:
    def handle(uow: UnitOfWork) -> EventSetOut:
        return EventSetOut.model_validate(event_sets.create(uow, body.model_dump()))

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        etag=lambda out: row_etag(out.row_version),
        location=lambda out: f"{API_PREFIX}/forecast-event-sets/{out.id}",
    )


@router.patch(
    "/forecast-event-sets/{event_set_id}",
    operation_id="forecast_event_sets_update",
    response_model=EventSetOut,
    responses=PROBLEMS,
)
def update_set(
    event_set_id: UUID, body: EventSetUpdateIn, cmd: UpdateCommand, deps: Deps
) -> Response:
    def handle(uow: UnitOfWork) -> EventSetOut:
        assert cmd.expected_version is not None
        return EventSetOut.model_validate(
            event_sets.change(
                uow,
                event_set_id,
                expected_version=cmd.expected_version,
                values=body.model_dump(exclude_unset=True),
            )
        )

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))


@router.post(
    "/forecast-event-sets/{event_set_id}/publish",
    operation_id="forecast_event_sets_publish",
    response_model=EventSetOut,
    responses=PROBLEMS,
)
def publish_set(event_set_id: UUID, cmd: UpdateCommand, deps: Deps) -> Response:
    def handle(uow: UnitOfWork) -> EventSetOut:
        assert cmd.expected_version is not None
        return EventSetOut.model_validate(
            event_sets.change(
                uow, event_set_id, expected_version=cmd.expected_version, publish=True
            )
        )

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))
