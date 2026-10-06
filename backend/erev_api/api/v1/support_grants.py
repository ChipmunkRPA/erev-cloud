"""API-R-14 Support grants: tenant-approved, time-boxed, read-only operator access.

04 §15.3 API-R-14, T-PLT-33; SCREENS_B §9.14 SF-14:support-access; PRD NTF-12; REQ-PLT-036;
BUILD_SPEC PLF-26, BS1-D-27. Every route requires ``support_grant.approve`` for all entities: an
operator's access reaches the whole workspace (04 API-C-03 rev 1.219; supervisor rulings R-28 and
R-115 (c); item SCOPE-WORKSPACE-LISTS-1). ``POST /support-grants`` records a request on an
operator's behalf, which another holder for all entities decides in the approval inbox; there is
no read route for one grant, so the 201 carries no ``Location``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response

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
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import support_grant
from erev_api.domain.platform import support_grants
from erev_api.enums import GrantStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.support_grants import SupportGrantIn, SupportGrantOut, SupportGrantRevokeIn
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-14 Support grants"
PERMISSION: Final = "support_grant.approve"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
GRANT_LIST: Final = ListSpec(
    resource="support-grants",
    sort_keys={
        "id": support_grant.c.id,
        "valid_from": support_grant.c.valid_from,
        "valid_to": support_grant.c.valid_to,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=support_grant.c.status,
            kind="exact",
            choices=frozenset(status.value for status in GrantStatus),
        )
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/support-grants",
    operation_id="support_grants_list",
    response_model=ListOut[SupportGrantOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def support_grants_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[GrantStatus] | None, Query()] = None,
) -> ListOut[SupportGrantOut]:
    """Support grants in every status; sort ``id`` (default ``-id``), ``valid_from`` or
    ``valid_to``."""
    result, items = support_grants.list_support_grants(
        ctx, page=lambda session, statement: paginate(session, statement, GRANT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SupportGrantOut](
        items=[SupportGrantOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/support-grants",
    operation_id="support_grants_create",
    status_code=201,
    response_model=SupportGrantOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def support_grants_create(
    body: SupportGrantIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request read-only support access for an operator; it takes effect once approved."""

    def handle(uow: UnitOfWork) -> SupportGrantOut:
        grant_id = support_grants.request_support_grant(
            uow,
            operator_email=body.operator_email,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
        )
        return SupportGrantOut.model_validate(support_grants.grant_out(uow.session, grant_id))

    return run_command(cmd, deps, handle, status_code=201)


@router.post(
    "/support-grants/{support_grant_id}/revoke",
    operation_id="support_grants_revoke",
    response_model=SupportGrantOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def support_grants_revoke(
    support_grant_id: uuid.UUID,
    body: SupportGrantRevokeIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Revoke approved support access with a reason; the operator's sessions end immediately."""

    def handle(uow: UnitOfWork) -> SupportGrantOut:
        support_grants.revoke_support_grant(uow, support_grant_id, reason=body.reason)
        return SupportGrantOut.model_validate(
            support_grants.grant_out(uow.session, support_grant_id)
        )

    return run_command(cmd, deps, handle)
