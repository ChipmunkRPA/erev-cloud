"""API-R-03 Me: the profile, display preferences, password change, multi-factor enrolment,
recovery codes, notifications and notification preferences.

04 §15.3 API-R-03, §16.12; SCREENS_B §12.2, §12.3, SF-15, OQ-B-20, OQ-B-24; SCREENS SCR-IA-06
bindings; 05 SAR-09, SAR-10, SAR-26, NTR-06; BUILD_SPEC BS1-D-19, BS1-D-32, PLF-14, PLF-15, PLF-21.
Password change and enrolment act on the signed-in user before a workspace is chosen, through
``require_authenticated(tenant=False)``; regenerating recovery codes needs a fresh step-up. The
profile, notifications and preferences belong to the caller's membership in the active tenant.
``GET /me`` serves the release the process stamped in the lifespan startup (``app.state``), and
answers a session without a workspace too, with its memberships and no grants (D-83).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Request, Response

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    cookie_secure,
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
from erev_api.auth import credentials, mfa, sessions
from erev_api.auth.dependencies import (
    ENROLMENT_PENDING,
    forget_session,
    require_authenticated,
    require_step_up,
)
from erev_api.auth.principal import RequestContext
from erev_api.auth.sessions import AuthenticatedSession
from erev_api.db.tables import notification
from erev_api.domain.platform import me, me_notifications
from erev_api.schemas.common import ListOut
from erev_api.schemas.me import (
    MeOut,
    MfaConfirmIn,
    MfaEnrolmentOut,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferencesIn,
    NotificationPreferencesOut,
    NotificationReadAllIn,
    NotificationReadAllOut,
    PasswordChangeIn,
    PreferencesIn,
    PreferencesOut,
    PreferencesUpdateOut,
    RecoveryCodesOut,
)

TAG: Final = "API-R-03 Me"
_SESSION_PROBLEMS: Final = ("validation-failed", "unauthenticated", "session-expired", "forbidden")
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
NOTIFICATION_LIST: Final = ListSpec(
    resource="notifications",
    sort_keys={"id": notification.c.id, "created_at": notification.c.created_at},
    default_sort="-created_at",
    filters={
        "unread": FilterSpec(name="unread", column=notification.c.read_at.is_(None), kind="bool")
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/me",
    operation_id="me_get",
    response_model=MeOut,
    responses=problem_responses(*_READ_PROBLEMS),
)
def me_get(
    request: Request,
    caller: Annotated[
        RequestContext | AuthenticatedSession, Depends(require_authenticated(tenant="optional"))
    ],
) -> MeOut:
    """API-S-Me: the user, memberships, grants, MFA status, preferences, workspace settings, the
    engine release and the unread notification count. A session that has not opened a workspace
    gets 200 with its memberships, ``active_membership_id`` null and no grants (D-83)."""
    state = request.app.state
    if isinstance(caller, AuthenticatedSession):
        return MeOut.model_validate(
            me.me_without_workspace(caller, engine_release=state.engine_release)
        )
    ctx = caller
    return MeOut.model_validate(
        me.me(
            ctx,
            engine_release=state.engine_release,
            ai_kill_switch=state.settings.ai_kill_switch,
        )
    )


@router.patch(
    "/me/preferences",
    operation_id="me_preferences_update",
    response_model=PreferencesUpdateOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def me_preferences_update(
    body: PreferencesIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change any display preference; a null member returns to its default (04 §16.12)."""
    changes = body.model_dump(mode="json", include=body.model_fields_set)
    return run_command(
        cmd,
        deps,
        lambda uow: PreferencesUpdateOut(
            preferences=PreferencesOut.model_validate(me.update_preferences(uow, changes))
        ),
    )


@router.post(
    "/me/password",
    operation_id="me_change_password",
    status_code=204,
    response_class=Response,
    responses=problem_responses(*_SESSION_PROBLEMS, "password-policy", "account-locked"),
)
def me_change_password(
    body: PasswordChangeIn,
    request: Request,
    auth: Annotated[AuthenticatedSession, Depends(require_authenticated(tenant=False))],
    idempotency_key: Annotated[str, Depends(command())],
) -> Response:
    """Change the password; the user's other sessions end, and this one continues under a new
    ``erev_session`` cookie while the presented token stops working (04 §16.12; 05 SAR-09)."""
    rotated = credentials.change_password(
        auth,
        current_password=body.current_password,
        new_password=body.new_password,
        keyring=request.app.state.keyring,
    )
    forget_session(request)  # the presented session is ended: its kept answer goes with it
    response = Response(status_code=204)
    response.headers.append(
        "set-cookie", sessions.cookie_header(rotated.token, secure=cookie_secure(request))
    )
    return response


@router.post(
    "/me/mfa/enroll",
    operation_id="me_mfa_enroll",
    response_model=MfaEnrolmentOut,
    responses=problem_responses(*_SESSION_PROBLEMS, "invalid-transition"),
)
def me_mfa_enroll(
    request: Request,
    auth: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated(tenant=False, open_to=ENROLMENT_PENDING)),
    ],
    idempotency_key: Annotated[str, Depends(command())],
) -> MfaEnrolmentOut:
    """Start or restart TOTP enrolment: a new seed for the authenticator app."""
    enrolment = mfa.enroll(auth, keyring=request.app.state.keyring)
    return MfaEnrolmentOut(otpauth_uri=enrolment.otpauth_uri, secret_base32=enrolment.secret_base32)


@router.post(
    "/me/mfa/confirm",
    operation_id="me_mfa_confirm",
    response_model=RecoveryCodesOut,
    responses=problem_responses(*_SESSION_PROBLEMS, "invalid-transition"),
)
def me_mfa_confirm(
    body: MfaConfirmIn,
    request: Request,
    response: Response,
    auth: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated(tenant=False, open_to=ENROLMENT_PENDING)),
    ],
    idempotency_key: Annotated[str, Depends(command())],
) -> RecoveryCodesOut:
    """Confirm enrolment with a first valid code; the verified session rotates (SAR-09)."""
    confirmed, codes = mfa.confirm(auth, body.code, keyring=request.app.state.keyring)
    forget_session(request)  # the presented session is ended: its kept answer goes with it
    response.headers.append(
        "set-cookie", sessions.cookie_header(confirmed.token, secure=cookie_secure(request))
    )
    return RecoveryCodesOut(recovery_codes=codes)


@router.post(
    "/me/recovery-codes",
    operation_id="me_regenerate_recovery_codes",
    response_model=RecoveryCodesOut,
    responses=problem_responses(*_SESSION_PROBLEMS, "mfa-step-up-required", "invalid-transition"),
)
def me_regenerate_recovery_codes(
    request: Request,
    auth: Annotated[AuthenticatedSession, Depends(require_step_up())],
    idempotency_key: Annotated[str, Depends(command())],
) -> RecoveryCodesOut:
    """Ten new recovery codes; every earlier batch stops working (T-PLT-05)."""
    codes = mfa.regenerate_recovery_codes(auth, keyring=request.app.state.keyring)
    return RecoveryCodesOut(recovery_codes=codes)


def notification_out(row: Mapping[str, Any]) -> NotificationOut:
    return NotificationOut.model_validate(dict(row))


def preferences_out(entries: Sequence[Mapping[str, Any]]) -> NotificationPreferencesOut:
    return NotificationPreferencesOut(
        items=[NotificationPreferenceOut.model_validate(dict(entry)) for entry in entries]
    )


@router.get(
    "/me/notifications",
    operation_id="me_notifications_list",
    response_model=ListOut[NotificationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def me_notifications_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    params: Annotated[ListParams, Depends(list_params)],
    unread: Annotated[bool | None, Query(description="true: unread notifications only")] = None,
) -> ListOut[NotificationOut]:
    """The caller's notifications, newest first; the web app polls ``unread=true`` (NTR-06)."""
    result = me_notifications.list_notifications(
        ctx, page=lambda session, statement: paginate(session, statement, NOTIFICATION_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[NotificationOut](
        items=[notification_out(row) for row in result.items], next_cursor=result.next_cursor
    )


@router.post(
    "/me/notifications/read-all",
    operation_id="me_notifications_read_all",
    response_model=NotificationReadAllOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def me_notifications_read_all(
    body: NotificationReadAllIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Mark read every unread notification created at or before ``before`` (04 §16.12)."""
    return run_command(
        cmd,
        deps,
        lambda uow: NotificationReadAllOut(
            marked=me_notifications.read_all(uow, before=body.before)
        ),
    )


@router.post(
    "/me/notifications/{notification_id}/read",
    operation_id="me_notifications_read",
    response_model=NotificationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def me_notifications_read(
    notification_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Mark one of the caller's notifications read; reading it again changes nothing."""
    return run_command(
        cmd, deps, lambda uow: notification_out(me_notifications.mark_read(uow, notification_id))
    )


@router.get(
    "/me/notification-preferences",
    operation_id="me_notification_preferences_get",
    response_model=NotificationPreferencesOut,
    responses=problem_responses(*_READ_PROBLEMS),
)
def me_notification_preferences_get(
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
) -> NotificationPreferencesOut:
    """Every E-69 kind with its in-app and email switches (SCREENS_B SF-15)."""
    return preferences_out(me_notifications.get_preferences(ctx))


@router.put(
    "/me/notification-preferences",
    operation_id="me_notification_preferences_put",
    response_model=NotificationPreferencesOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def me_notification_preferences_put(
    body: NotificationPreferencesIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Store the preferences sent; audit chain failures cannot be turned off (NTF-R2)."""
    items = [(item.kind, item.in_app, item.email) for item in body.items]
    return run_command(
        cmd, deps, lambda uow: preferences_out(me_notifications.put_preferences(uow, items))
    )
