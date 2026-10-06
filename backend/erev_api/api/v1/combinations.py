"""API-R-28 Contracts, combination groups and combination suggestions.

04 §15.3 API-R-28, §16.14 combination suggestions, T-CON-03, T-CON-04, table 15.4-C; ENGINE_SPEC
S02-R-09, S02-R-10, S02-R-14; PRD BR-CON-03, §2.5 routing row ``COMBINATION_GROUP``; 03 REQ-CON-009,
REQ-CON-010, REQ-CON-019; BUILD_SPEC CTR-8. Reads need ``contract.read``; commands need
``contract.create``, which the handlers check for each contracting entity. No route takes
``If-Match``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

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
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import combination_group, exception_item
from erev_api.domain.contracts import combination, queries
from erev_api.enums import CombinationStatus
from erev_api.schemas.combinations import (
    CombinationGroupCreateIn,
    CombinationGroupDetailOut,
    CombinationGroupSubmitIn,
    CombinationSuggestionOut,
    SuggestionDismissIn,
)
from erev_api.schemas.common import ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-28 Contracts"
READ: Final = "contract.read"
CREATE: Final = combination.CREATE_PERMISSION
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
)
GROUP_LIST: Final = ListSpec(
    resource="combination-groups",
    sort_keys={
        "id": combination_group.c.id,
        "code": combination_group.c.code,
        "inception_date": combination_group.c.inception_date,
    },
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"status", "contract"}),
)
SUGGESTION_LIST: Final = ListSpec(
    resource="combination-suggestions",
    sort_keys={"id": exception_item.c.id, "created_at": exception_item.c.created_at},
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"contract"}),
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


@router.get(
    "/combination-groups",
    operation_id="combination_groups_list",
    response_model=ListOut[CombinationGroupDetailOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def combination_groups_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    status: Annotated[list[CombinationStatus] | None, Query(description="E-95")] = None,
    contract: Annotated[uuid.UUID | None, Query(description="A current member")] = None,
) -> ListOut[CombinationGroupDetailOut]:
    """Combination groups; sort ``id`` (default ``-id``), ``code`` or ``inception_date``."""

    def page(session: Session) -> tuple[ListResult, list[CombinationGroupDetailOut]]:
        statement = combination.groups_statement(statuses=tuple(status or ()), contract_id=contract)
        result = paginate(session, statement, GROUP_LIST, params)
        return result, combination.group_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[CombinationGroupDetailOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/combination-groups",
    operation_id="combination_groups_create",
    status_code=201,
    response_model=CombinationGroupDetailOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def combination_groups_create(
    body: CombinationGroupCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Propose a group of contracts in one currency with the 606-10-25-9 criterion (REQ-CON-009,
    REQ-CON-019)."""

    def handle(uow: UnitOfWork) -> CombinationGroupDetailOut:
        return combination.create_group(uow, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/combination-groups/{out.id}",
    )


@router.get(
    "/combination-groups/{group_id}",
    operation_id="combination_groups_get",
    response_model=CombinationGroupDetailOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def combination_groups_get(group_id: uuid.UUID, ctx: ReadContext) -> CombinationGroupDetailOut:
    return queries.read(ctx, lambda session: combination.get_group(session, group_id))


@router.post(
    "/combination-groups/{group_id}/submit",
    operation_id="combination_groups_submit",
    response_model=CombinationGroupDetailOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def combination_groups_submit(
    group_id: uuid.UUID,
    body: CombinationGroupSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Route a proposed combination, or members leaving an applied group as a data correction
    (subject ``COMBINATION_GROUP``, ``contract.approve``)."""

    def handle(uow: UnitOfWork) -> CombinationGroupDetailOut:
        return combination.submit_group(uow, group_id=group_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/combination-groups/{group_id}/discard",
    operation_id="combination_groups_discard",
    response_model=CombinationGroupDetailOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def combination_groups_discard(
    group_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Give up a proposed combination that was not submitted (04 API-R-28 rev 1.289): no
    body; the group goes ``PROPOSED`` → ``VOIDED`` with its draft record. A submitted group
    and every other state answer 409 ``invalid-transition``."""

    def handle(uow: UnitOfWork) -> CombinationGroupDetailOut:
        return combination.discard_group(uow, group_id=group_id)

    return run_command(cmd, deps, handle)


@router.get(
    "/combination-suggestions",
    operation_id="combination_suggestions_list",
    response_model=ListOut[CombinationSuggestionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def combination_suggestions_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    contract: Annotated[uuid.UUID | None, Query(description="A suggested contract")] = None,
) -> ListOut[CombinationSuggestionOut]:
    """Open ``COMBINATION_SUGGESTED`` items (04 §16.14); sort ``id`` (default ``-id``) or
    ``created_at``."""

    def page(session: Session) -> tuple[ListResult, list[CombinationSuggestionOut]]:
        statement = combination.suggestions_read_by(ctx.principal, contract)
        result = paginate(session, statement, SUGGESTION_LIST, params)
        return result, combination.suggestion_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[CombinationSuggestionOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/combination-suggestions/{item_id}/dismiss",
    operation_id="combination_suggestions_dismiss",
    response_model=CombinationSuggestionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def combination_suggestions_dismiss(
    item_id: uuid.UUID,
    body: SuggestionDismissIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Dismiss a suggestion with a rationale of at least 10 characters (PRD WLD-K-11)."""

    def handle(uow: UnitOfWork) -> CombinationSuggestionOut:
        return combination.dismiss_suggestion(uow, item_id=item_id, body=body)

    return run_command(cmd, deps, handle)
