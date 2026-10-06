"""API-R-52 Control evidence and releases: ``GET /control-executions``, ``GET /releases``.

04 §15.3 API-R-52, T-PLT-39, T-PLT-38; 03 REQ-CTL-002; BUILD_SPEC SOP-1. Both routes require
``audit.read``; the executions for all entities, because an execution of the workspace — a
report run's, an import's, the chain's — carries no entity (supervisor ruling R-28; item
SCOPE-WORKSPACE-LISTS-1). Executions are read through a read-only tenant session (RLS-T, RLS-TE
when ``entity_id`` is set); releases come from the global T-PLT-38 table, newest first.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require, require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.controls.evidence import RunRefType
from erev_api.db.session import tenant_session
from erev_api.db.tables import control_execution, engine_release
from erev_api.enums import ControlResult
from erev_api.schemas.common import ListOut
from erev_api.schemas.controls import ControlExecutionOut, ReleaseOut

TAG: Final = "API-R-52 Control evidence"
AUDIT_READ: Final = "audit.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "validation-failed")
_EXECUTION_COLUMNS: Final = tuple(
    column for column in control_execution.c if column.name != "tenant_id"
)
EXECUTION_LIST: Final = ListSpec(
    resource="control-executions",
    sort_keys={
        "id": control_execution.c.id,
        "executed_at": control_execution.c.executed_at,
        "control_id": control_execution.c.control_id,
    },
    default_sort="-executed_at",
    filters={
        "control_id": FilterSpec(
            name="control_id", column=control_execution.c.control_id, kind="exact"
        ),
        "run_ref_type": FilterSpec(
            name="run_ref_type",
            column=control_execution.c.run_ref_type,
            kind="exact",
            choices=frozenset(kind.value for kind in RunRefType),
        ),
        "result": FilterSpec(
            name="result",
            column=control_execution.c.result,
            kind="exact",
            choices=frozenset(result.value for result in ControlResult),
        ),
        "from": FilterSpec(name="from", column=control_execution.c.executed_at, kind="from"),
        "to": FilterSpec(name="to", column=control_execution.c.executed_at, kind="to"),
    },
)
RELEASE_LIST: Final = ListSpec(
    resource="releases",
    sort_keys={"id": engine_release.c.id, "deployed_at": engine_release.c.deployed_at},
    default_sort="-deployed_at",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/control-executions",
    operation_id="control_executions_list",
    response_model=ListOut[ControlExecutionOut],
    responses=problem_responses(*_READ_PROBLEMS),
)
def control_executions_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(AUDIT_READ))],
    params: Annotated[ListParams, Depends(list_params)],
    control_id: Annotated[str | None, Query()] = None,
    run_ref_type: Annotated[RunRefType | None, Query()] = None,
    result: Annotated[ControlResult | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from", description="Inclusive")] = None,
    to: Annotated[datetime | None, Query(description="Exclusive")] = None,
) -> ListOut[ControlExecutionOut]:
    """The workspace's control executions (04 T-PLT-39); sort ``executed_at`` (default
    ``-executed_at``, newest first), ``control_id`` or ``id``; filters ``control_id``,
    ``run_ref_type``, ``result``, ``from`` and ``to``."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        page = paginate(session, select(*_EXECUTION_COLUMNS), EXECUTION_LIST, params)
    if page.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = page.total_count
    items = [ControlExecutionOut.model_validate(dict(row)) for row in page.items]
    return ListOut[ControlExecutionOut](items=items, next_cursor=page.next_cursor)


@router.get(
    "/releases",
    operation_id="releases_list",
    response_model=ListOut[ReleaseOut],
    responses=problem_responses(*_READ_PROBLEMS),
)
def releases_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(AUDIT_READ))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[ReleaseOut]:
    """The engine releases stamped on this database (04 T-PLT-38) with their gate results
    (05 REL-03, REL-04); sort ``deployed_at`` (default newest first) or ``id``."""
    columns: tuple[Any, ...] = (
        engine_release.c.id,
        engine_release.c.engine_version,
        engine_release.c.build_sha,
        engine_release.c.schema_revision,
        engine_release.c.control_impact_tags,
        engine_release.c.gate_results,
        engine_release.c.deployed_at,
    )
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        page = paginate(session, select(*columns), RELEASE_LIST, params)
    if page.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = page.total_count
    items = [ReleaseOut.model_validate(dict(row)) for row in page.items]
    return ListOut[ReleaseOut](items=items, next_cursor=page.next_cursor)
