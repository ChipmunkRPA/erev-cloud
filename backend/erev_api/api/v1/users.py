"""API-R-05 Users: members of the workspace, invitations and membership commands.

04 §15.3 API-R-05, T-PLT-07, T-PLT-10, SMAP-14, API-C-08, API-C-09; SCREENS_B §9.10 bindings; PRD
SM-13, BR-PLT-02, BR-PLT-06; BUILD_SPEC PLF-17. Every route needs ``user.manage``; resetting a
member's MFA also needs a TOTP verification at most five minutes old, and so does
``POST /users/{membership_id}/anonymise`` (05 PRV-07 a; BUILD_SPEC SOP-5).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Request, Response

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
from erev_api.db.tables import app_user, tenant_membership
from erev_api.domain.platform import privacy, users
from erev_api.enums import MembershipStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.users import (
    MembershipReasonIn,
    UserAnonymiseOut,
    UserInviteIn,
    UserOut,
    UserUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-05 Users"
PERMISSION: Final = "user.manage"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_MEMBER_PROBLEMS: Final = (*_COMMAND_PROBLEMS, "not-found", "invalid-transition")
USER_LIST: Final = ListSpec(
    resource="users",
    sort_keys={
        "id": tenant_membership.c.id,
        "invited_at": tenant_membership.c.invited_at,
        # D-80: sort and search see the name API-S-User shows, never a withheld one.
        "display_name": users.SHOWN_DISPLAY_NAME,
        "email": app_user.c.email,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=tenant_membership.c.status,
            kind="exact",
            choices=frozenset(status.value for status in MembershipStatus),
        )
    },
    search_columns=(users.SHOWN_DISPLAY_NAME, app_user.c.email),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def user_etag(out: UserOut) -> str:
    """API-C-08: the membership is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _location(out: UserOut) -> str:
    return f"{API_PREFIX}/users/{out.id}"


def _user(uow: UnitOfWork, membership_id: uuid.UUID) -> UserOut:
    return UserOut.model_validate(users.user_out(uow, membership_id))


@router.get(
    "/users",
    operation_id="users_list",
    response_model=ListOut[UserOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def users_list(
    request: Request,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[MembershipStatus] | None, Query()] = None,
) -> ListOut[UserOut]:
    """Members with their active and requested roles; ``q`` searches name and email; sort
    ``display_name``, ``email``, ``invited_at`` or ``id``."""
    result, items = users.list_users(
        ctx,
        page=lambda session, statement: paginate(session, statement, USER_LIST, params),
        files=request.app.state.file_store,
        keyring=request.app.state.keyring,
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[UserOut](
        items=[UserOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/users",
    operation_id="users_invite",
    status_code=201,
    response_model=UserOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "sod-conflict"),
)
def users_invite(
    body: UserInviteIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Invite a person with roles; each role waits for approval unless rule AUTO-BOOTSTRAP
    approves it during setup (BR-PLT-02). A person who was removed from this workspace is
    invited again on the same membership (PRD SM-13): the answer carries its id, and its earlier
    roles stay revoked."""

    def handle(uow: UnitOfWork) -> UserOut:
        membership_id = users.invite_user(
            uow,
            email=body.email,
            display_name=body.display_name,
            roles=[
                users.RoleGrant(
                    role_id=item.role_id,
                    is_all_entities=item.is_all_entities,
                    entity_codes=tuple(item.entity_codes),
                )
                for item in body.roles
            ],
        )
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, status_code=201, location=_location, etag=user_etag)


@router.get(
    "/users/{membership_id}",
    operation_id="users_get",
    response_model=UserOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def users_get(
    membership_id: uuid.UUID,
    request: Request,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
) -> UserOut:
    """API-S-User with every role, revoked ones included."""
    out = UserOut.model_validate(
        users.get_user(
            ctx,
            membership_id,
            files=request.app.state.file_store,
            keyring=request.app.state.keyring,
        )
    )
    response.headers["ETag"] = user_etag(out)
    return out


@router.patch(
    "/users/{membership_id}",
    operation_id="users_update",
    response_model=UserOut,
    responses=problem_responses(*_MEMBER_PROBLEMS, "precondition-failed", "precondition-required"),
)
def users_update(
    membership_id: uuid.UUID,
    body: UserUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Correct the display name of an invitation whose person has not signed in yet."""

    def handle(uow: UnitOfWork) -> UserOut:
        users.update_user(
            uow,
            membership_id,
            display_name=body.display_name,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, etag=user_etag)


@router.post(
    "/users/{membership_id}/suspend",
    operation_id="users_suspend",
    response_model=UserOut,
    responses=problem_responses(*_MEMBER_PROBLEMS),
)
def users_suspend(
    membership_id: uuid.UUID,
    body: MembershipReasonIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Suspend an active member; every session of the member in this workspace ends."""

    def handle(uow: UnitOfWork) -> UserOut:
        users.suspend_membership(uow, membership_id, reason=body.reason)
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, etag=user_etag)


@router.post(
    "/users/{membership_id}/reactivate",
    operation_id="users_reactivate",
    response_model=UserOut,
    responses=problem_responses(*_MEMBER_PROBLEMS),
)
def users_reactivate(
    membership_id: uuid.UUID,
    body: MembershipReasonIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Make a suspended member active again."""

    def handle(uow: UnitOfWork) -> UserOut:
        users.reactivate_membership(uow, membership_id, reason=body.reason)
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, etag=user_etag)


@router.post(
    "/users/{membership_id}/remove",
    operation_id="users_remove",
    response_model=UserOut,
    responses=problem_responses(*_MEMBER_PROBLEMS),
)
def users_remove(
    membership_id: uuid.UUID,
    body: MembershipReasonIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Remove a member: roles are revoked and sessions end; the history is kept."""

    def handle(uow: UnitOfWork) -> UserOut:
        users.remove_membership(uow, membership_id, reason=body.reason)
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, etag=user_etag)


@router.post(
    "/users/{membership_id}/reset-mfa",
    operation_id="users_reset_mfa",
    response_model=UserOut,
    responses=problem_responses(*_MEMBER_PROBLEMS, "mfa-step-up-required"),
)
def users_reset_mfa(
    membership_id: uuid.UUID,
    body: MembershipReasonIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Disable the member's factor so they enrol again; every session of the person ends."""

    def handle(uow: UnitOfWork) -> UserOut:
        users.reset_mfa(uow, membership_id, reason=body.reason)
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, etag=user_etag)


def _erasure_progress(result: privacy.AnonymiseResult) -> dict[str, Any]:
    pending = list(result.completion_pending)
    return {
        "status": "COMPLETION_PENDING" if pending else "COMPLETE",
        "other_workspaces_removed_now": [
            tenant_id for tenant_id, _ in result.other_memberships_removed
        ],
        "other_workspaces_completion_pending": pending,
        "other_workspaces_completed_now": list(result.completion_events_delivered),
        "next_step": privacy.completion_next_step(pending),
    }


@router.post(
    "/users/{membership_id}/anonymise",
    operation_id="users_anonymise",
    response_model=UserAnonymiseOut,
    responses=problem_responses(*_MEMBER_PROBLEMS, "mfa-step-up-required"),
)
def users_anonymise(
    membership_id: uuid.UUID,
    body: MembershipReasonIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Erase the person behind this membership (05 PRV-07 a; runbook RB-14): the identity becomes
    ``Erased user <8 hex>`` / ``erased+<user id>@invalid.erev`` with no password or external id
    and status ``DISABLED``, every session ends and every membership of the person is removed.
    Needs a step-up at most five minutes old and a reason of at least 10 characters. The 200 body
    carries ``erasure``: whether other workspaces are still owed their ``app_user.anonymise``
    completion event and the next step (run again with a new ``Idempotency-Key``, from this
    workspace or from an owed one through the removed membership); when the identity is already
    erased the command delivers what is owed and answers 200, or 409 ``PRV-07`` when nothing is."""

    def handle(uow: UnitOfWork) -> UserAnonymiseOut:
        result = privacy.anonymise_user(uow, membership_id, reason=body.reason)
        return UserAnonymiseOut.model_validate(
            {**dict(users.user_out(uow, membership_id)), "erasure": _erasure_progress(result)}
        )

    return run_command(cmd, deps, handle, etag=user_etag)


@router.post(
    "/users/{membership_id}/resend-invitation",
    operation_id="users_resend_invitation",
    response_model=UserOut,
    responses=problem_responses(*_MEMBER_PROBLEMS),
)
def users_resend_invitation(
    membership_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Send the invitation again with a new link that expires in 7 days."""

    def handle(uow: UnitOfWork) -> UserOut:
        users.resend_invitation(uow, membership_id)
        return _user(uow, membership_id)

    return run_command(cmd, deps, handle, etag=user_etag)
