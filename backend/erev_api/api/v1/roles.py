"""API-R-06 Roles and permissions: the permission catalogue, roles and role assignments.

04 §15.3 API-R-06, T-PLT-09 to T-PLT-12, SMAP-14, API-C-08, API-C-09; SCREENS_B §9.10 and §9.11
bindings; PRD SM-04, SM-13, ERR-22; BUILD_SPEC PLF-18, BS1-D-31. Every route needs ``role.manage``;
role changes and assignments take effect once another ``access.approve`` holder approves them.
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
    assert_version,
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
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import role, role_assignment
from erev_api.domain.platform import roles
from erev_api.schemas.common import ListOut
from erev_api.schemas.roles import (
    PermissionOut,
    RoleAssignmentIn,
    RoleAssignmentOut,
    RoleAssignmentRevokeIn,
    RoleChangeIn,
    RoleCreateIn,
    RoleOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-06 Roles and permissions"
PERMISSION: Final = "role.manage"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
ROLE_LIST: Final = ListSpec(
    resource="roles",
    sort_keys={"id": role.c.id, "code": role.c.code, "name": role.c.name},
    default_sort="id",
    filters={
        "is_system": FilterSpec(name="is_system", column=role.c.is_system, kind="bool"),
        "is_active": FilterSpec(name="is_active", column=role.c.is_active, kind="bool"),
    },
    search_columns=(role.c.name, role.c.code),
)
ASSIGNMENT_LIST: Final = ListSpec(
    resource="role-assignments",
    sort_keys={"id": role_assignment.c.id, "valid_from": role_assignment.c.valid_from},
    default_sort="-id",
    filters={
        "membership_id": FilterSpec(
            name="membership_id", column=role_assignment.c.membership_id, kind="exact"
        ),
        "role_id": FilterSpec(name="role_id", column=role_assignment.c.role_id, kind="exact"),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def role_etag(out: RoleOut) -> str:
    """API-C-08: the role is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _role_location(out: RoleOut) -> str:
    return f"{API_PREFIX}/roles/{out.id}"


@router.get(
    "/permissions",
    operation_id="permissions_list",
    response_model=ListOut[PermissionOut],
    responses=problem_responses(*_READ_PROBLEMS),
)
def permissions_list(
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
) -> ListOut[PermissionOut]:
    """The whole permission catalogue by code, in one page."""
    return ListOut[PermissionOut](
        items=[PermissionOut.model_validate(item) for item in roles.list_permissions(ctx)],
        next_cursor=None,
    )


@router.get(
    "/roles",
    operation_id="roles_list",
    response_model=ListOut[RoleOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def roles_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    is_system: Annotated[bool | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[RoleOut]:
    """Roles with their permissions; ``q`` searches name and code; sort ``id`` (default),
    ``code`` or ``name``."""
    result, items = roles.list_roles(
        ctx, page=lambda session, statement: paginate(session, statement, ROLE_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RoleOut](
        items=[RoleOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/roles",
    operation_id="roles_create",
    status_code=201,
    response_model=RoleOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def roles_create(
    body: RoleCreateIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create an inactive custom role; approving its ``ROLE_CHANGE`` request grants the
    permissions and activates it."""

    def handle(uow: UnitOfWork) -> RoleOut:
        role_id = roles.create_role(
            uow,
            code=body.code,
            name=body.name,
            description=body.description,
            permissions=body.permissions,
        )
        return RoleOut.model_validate(roles.role_out(uow, role_id))

    return run_command(cmd, deps, handle, status_code=201, location=_role_location, etag=role_etag)


@router.get(
    "/roles/{role_id}",
    operation_id="roles_get",
    response_model=RoleOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def roles_get(
    role_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
) -> RoleOut:
    """API-S-Role with its permission codes."""
    out = RoleOut.model_validate(roles.get_role(ctx, role_id))
    response.headers["ETag"] = role_etag(out)
    return out


@router.post(
    "/roles/{role_id}/propose-change",
    operation_id="roles_propose_change",
    response_model=RoleOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "sod-conflict",
        "precondition-failed",
        "precondition-required",
    ),
)
def roles_propose_change(
    role_id: uuid.UUID,
    body: RoleChangeIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Propose another permission list for a custom role; system roles cannot change."""

    def handle(uow: UnitOfWork) -> RoleOut:
        roles.propose_role_change(
            uow,
            role_id,
            permissions=body.permissions,
            comment=body.comment,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return RoleOut.model_validate(roles.role_out(uow, role_id))

    return run_command(cmd, deps, handle, etag=role_etag)


@router.get(
    "/role-assignments",
    operation_id="role_assignments_list",
    response_model=ListOut[RoleAssignmentOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def role_assignments_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    membership_id: Annotated[uuid.UUID | None, Query()] = None,
    role_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ListOut[RoleAssignmentOut]:
    """Active and revoked role assignments; sort ``id`` (default ``-id``) or ``valid_from``."""
    result, items = roles.list_role_assignments(
        ctx, page=lambda session, statement: paginate(session, statement, ASSIGNMENT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RoleAssignmentOut](
        items=[RoleAssignmentOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/role-assignments",
    operation_id="role_assignments_create",
    status_code=201,
    response_model=RoleAssignmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition", "sod-conflict"),
)
def role_assignments_create(
    body: RoleAssignmentIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request a role for a member; it waits for approval unless rule AUTO-BOOTSTRAP approves it
    during setup."""

    def handle(uow: UnitOfWork) -> RoleAssignmentOut:
        request = roles.assign_role(
            uow,
            membership_id=body.membership_id,
            role_id=body.role_id,
            is_all_entities=body.is_all_entities,
            entity_codes=body.entity_codes,
            sod_exception_id=body.sod_exception_id,
        )
        return RoleAssignmentOut.model_validate(roles.requested_assignment_out(uow, request))

    return run_command(cmd, deps, handle, status_code=201)


@router.post(
    "/role-assignments/{assignment_id}/revoke",
    operation_id="role_assignments_revoke",
    response_model=RoleAssignmentOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def role_assignments_revoke(
    assignment_id: uuid.UUID,
    body: RoleAssignmentRevokeIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Revoke a role now; the member's permissions no longer include it."""

    def handle(uow: UnitOfWork) -> RoleAssignmentOut:
        roles.revoke_role_assignment(uow, assignment_id, reason=body.reason)
        return RoleAssignmentOut.model_validate(roles.assignment_out(uow, assignment_id))

    return run_command(cmd, deps, handle)
