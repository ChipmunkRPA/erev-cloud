"""API-R-01 Session: session state, sign-in, sign-out, workspace selection, invitation acceptance
and password reset.

04 §15.3 API-R-01, §16.12 API-S-Session, T-PLT-07 invitation acceptance, T-PLT-42; 05 SAR-06,
SAR-09 to SAR-11, SAR-13; BUILD_SPEC BS1-D-22, BS1-D-30, PLF-15. ``GET /session``,
``POST /session/login``, the invitation lookup and acceptance and both password reset routes are
API-C-01 unauthenticated routes: their tokens travel only in request bodies, and like sign-in they
take no ``Idempotency-Key`` (SPEC-Q-180). The MFA challenge, logout and tenant selection are cookie
commands guarded by ``require_authenticated(tenant=False)``. A platform operator selects a tenant
only under an approved support grant (BUILD_SPEC PLF-26; CTL-035). OIDC sign-in starts and returns
through the unauthenticated ``/session/oidc/*`` routes (05 SAR-27, THR-05; BUILD_SPEC PLF-27).
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from erev_api.api.deps import (
    API_PREFIX,
    GuardedRoute,
    command,
    cookie_secure,
    problem_responses,
)
from erev_api.auth import credentials, invitations, mfa, oidc, operators, sessions
from erev_api.auth.dependencies import (
    ANY_PENDING_STEP,
    CHALLENGE_PENDING,
    admit_address,
    authenticate_session,
    forget_session,
    origin_allowed,
    request_facts,
    require_authenticated,
    second_factor_step,
)
from erev_api.auth.ratelimit import LoginRateLimiter, PasswordResetRateLimiter
from erev_api.auth.sessions import AuthenticatedSession
from erev_api.clock import Clock, get_clock
from erev_api.config import Settings
from erev_api.domain.platform import memberships
from erev_api.problems import Problem, ProblemError, request_id_for
from erev_api.schemas.session import (
    AnonymousSessionOut,
    IdentityProviderRefOut,
    InvitationLookupIn,
    InvitationLookupOut,
    PasswordResetConfirmIn,
    PasswordResetIn,
    SessionAcceptInvitationIn,
    SessionCapabilitiesOut,
    SessionLoginIn,
    SessionLoginOut,
    SessionMfaIn,
    SessionMfaOut,
    SessionOut,
    SessionTenantIn,
    SessionTenantOut,
    SessionUserOut,
)

TAG: Final = "API-R-01 Session"
# SCREENS_B §12.1 "Rate limited (429)".
LOGIN_RETRY: Final = "Too many sign-in attempts. Try again in {seconds} seconds."
ORIGIN_REFUSED: Final = "Sign in from the eRev origin."

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _capabilities(request: Request) -> SessionCapabilitiesOut:
    providers = sessions.identity_providers(request_id_for(request))
    return SessionCapabilitiesOut(
        identity_providers=[
            IdentityProviderRefOut(code=code, name=name) for code, name in providers
        ]
    )


def _session_fields(auth: AuthenticatedSession, request: Request) -> dict[str, Any]:
    """API-S-Session of ``auth`` with the second-factor step it still owes (REQ-PLT-005): the
    same step the session guard enforces, on the sign-in answers and on ``GET /session`` alike."""
    active = auth.active_tenant
    step = second_factor_step(request, auth)
    return {
        "authenticated": True,
        "user": SessionUserOut(
            id=auth.user.id, email=auth.user.email, display_name=auth.user.display_name
        ),
        "active_tenant": None
        if active is None
        else SessionTenantOut(
            id=active.id, code=active.code, display_name=active.display_name, kind=active.kind
        ),
        "mfa_verified_at": auth.session.mfa_verified_at,
        "mfa_required": step.mfa_required,
        "mfa_enrolment_required": step.mfa_enrolment_required,
        "idle_expires_at": auth.session.idle_expires_at,
        "absolute_expires_at": auth.session.absolute_expires_at,
        "capabilities": _capabilities(request),
        "csrf_token": auth.csrf_token,
    }


def _login_out(auth: AuthenticatedSession, request: Request) -> SessionLoginOut:
    return SessionLoginOut(**_session_fields(auth, request))


def _refuse_foreign_origin(request: Request) -> None:
    """403 ``forbidden`` with ``rule_id`` ``API-C-02`` for a browser request from another origin."""
    settings: Settings = request.app.state.settings
    if not origin_allowed(request, settings.public_origin):
        raise Problem(
            "forbidden",
            ORIGIN_REFUSED,
            errors=[ProblemError(field="Origin", rule_id="API-C-02", message=ORIGIN_REFUSED)],
        )


@router.get(
    "/session",
    operation_id="session_get",
    response_model=SessionOut | AnonymousSessionOut,
    responses=problem_responses(),
)
def session_get(
    request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> SessionOut | AnonymousSessionOut:
    """The current session with its CSRF token and the second-factor step it still owes, or
    capabilities only without a valid session. A session that owes a step reads itself here."""
    if sessions.COOKIE_NAME in request.cookies:
        try:
            auth = authenticate_session(
                request, clock, enforce_csrf=False, open_to=ANY_PENDING_STEP
            )
        except Problem as problem:
            # An invalid or expired cookie is an anonymous session; a rate limit is not (SOP-4).
            if problem.slug == "rate-limited":
                raise
        else:
            return SessionOut(**_session_fields(auth, request))
    return AnonymousSessionOut(authenticated=False, capabilities=_capabilities(request))


@router.post(
    "/session/login",
    operation_id="session_login",
    response_model=SessionLoginOut,
    responses=problem_responses(
        "validation-failed", "unauthenticated", "forbidden", "account-locked", "rate-limited"
    ),
)
def session_login(
    body: SessionLoginIn,
    request: Request,
    response: Response,
    clock: Annotated[Clock, Depends(get_clock)],
) -> SessionLoginOut:
    """Password sign-in: a new session cookie and the CSRF token (BS1-D-30). A user with exactly one
    ACTIVE membership gets that workspace opened; otherwise ``active_tenant`` is null (D-83)."""
    facts = request_facts(request, clock)
    _refuse_foreign_origin(request)
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    retry_after = limiter.admit(
        address=facts.source_ip or "unknown",
        email=sessions.normalise_email(body.email),
        now=facts.now,
    )
    if retry_after is not None:
        raise Problem(
            "rate-limited",
            LOGIN_RETRY.format(seconds=retry_after),
            headers={"Retry-After": str(retry_after)},
        )
    auth = sessions.sign_in(
        email=body.email,
        password=body.password,
        facts=facts,
        keyring=request.app.state.keyring,
        previous_token=request.cookies.get(sessions.COOKIE_NAME),
    )
    if auth.active_tenant is not None:
        request.state.tenant_kind = auth.active_tenant.kind.value
    response.headers.append(
        "set-cookie", sessions.cookie_header(auth.token, secure=cookie_secure(request))
    )
    return _login_out(auth, request)


ProviderCode = Annotated[str, Path(min_length=1, max_length=63)]


@router.get(
    "/session/oidc/{provider}/start",
    operation_id="session_oidc_start",
    status_code=302,
    response_class=Response,
    responses={
        302: {"description": "Redirect to the identity provider's authorization endpoint"},
        **problem_responses("unauthenticated", "not-found", "rate-limited"),
    },
)
def session_oidc_start(
    provider: ProviderCode, request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> Response:
    """Start OIDC sign-in: a redirect with PKCE S256, ``state`` and ``nonce``, and a flow cookie."""
    settings: Settings = request.app.state.settings
    facts = request_facts(request, clock)
    admit_address(request, facts)
    started = oidc.begin(
        provider,
        facts=facts,
        keyring=request.app.state.keyring,
        http=request.app.state.oidc_http,
        public_origin=settings.public_origin,
    )
    response = Response(status_code=302, headers={"Location": started.location})
    response.headers.append(
        "set-cookie", oidc.flow_cookie_header(started.flow_token, secure=cookie_secure(request))
    )
    return response


@router.get(
    "/session/oidc/{provider}/callback",
    operation_id="session_oidc_callback",
    status_code=302,
    response_class=Response,
    responses={
        302: {"description": "Signed in: redirect to the sign-in page, which chooses the landing"},
        **problem_responses("unauthenticated", "not-found", "account-locked", "rate-limited"),
    },
)
def session_oidc_callback(
    provider: ProviderCode,
    request: Request,
    clock: Annotated[Clock, Depends(get_clock)],
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=512)] = None,
) -> Response:
    """Complete OIDC sign-in: the existing user with the verified email gets a new session."""
    settings: Settings = request.app.state.settings
    facts = request_facts(request, clock)
    admit_address(request, facts)
    auth = oidc.complete(
        provider,
        code=code,
        state=state,
        flow_token=request.cookies.get(oidc.FLOW_COOKIE),
        facts=facts,
        keyring=request.app.state.keyring,
        http=request.app.state.oidc_http,
        public_origin=settings.public_origin,
        previous_token=request.cookies.get(sessions.COOKIE_NAME),
    )
    secure = cookie_secure(request)
    response = Response(
        status_code=302, headers={"Location": settings.public_origin + oidc.SIGNED_IN_PATH}
    )
    response.headers.append("set-cookie", sessions.cookie_header(auth.token, secure=secure))
    response.headers.append("set-cookie", oidc.cleared_flow_cookie_header(secure=secure))
    return response


@router.post(
    "/session/invitations/lookup",
    operation_id="session_lookup_invitation",
    response_model=InvitationLookupOut,
    responses=problem_responses("validation-failed", "not-found", "rate-limited"),
)
def session_lookup_invitation(
    body: InvitationLookupIn, request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> InvitationLookupOut:
    """The workspace, inviter, email and password state of an open invitation; 404 for a malformed,
    unknown, expired or used token, which writes ``security_event`` ``INVITATION_LOOKUP_FAILED``
    (04 §16.12, T-PLT-07 rev 1.38; D-98 candidates 20 and 24). Counted per client address before
    the token is looked at (05 SAR-13)."""
    facts = request_facts(request, clock)
    admit_address(request, facts)
    invitation = invitations.find_invitation(
        body.token,
        facts=facts,
        keyring=request.app.state.keyring,
        route="lookup",
    )
    return InvitationLookupOut(
        workspace_display_name=invitation.workspace_display_name,
        inviter_display_name=invitation.inviter_display_name,
        email=invitation.email,
        expires_at=invitation.expires_at,
        has_password=invitation.has_password,
    )


@router.post(
    "/session/accept-invitation",
    operation_id="session_accept_invitation",
    response_model=SessionLoginOut,
    responses=problem_responses(
        "validation-failed",
        "forbidden",
        "not-found",
        "password-policy",
        "account-locked",
        "rate-limited",
    ),
)
def session_accept_invitation(
    body: SessionAcceptInvitationIn,
    request: Request,
    response: Response,
    clock: Annotated[Clock, Depends(get_clock)],
) -> SessionLoginOut:
    """Accept an invitation: the membership becomes ACTIVE and a new session opens with the
    workspace active (04 T-PLT-07)."""
    facts = request_facts(request, clock)
    _refuse_foreign_origin(request)
    admit_address(request, facts)
    auth = memberships.accept_invitation(
        token=body.token,
        password=body.password,
        facts=facts,
        keyring=request.app.state.keyring,
        clock=clock,
        files=request.app.state.file_store,
        previous_token=request.cookies.get(sessions.COOKIE_NAME),
    )
    if auth.active_tenant is not None:
        request.state.tenant_kind = auth.active_tenant.kind.value
    response.headers.append(
        "set-cookie", sessions.cookie_header(auth.token, secure=cookie_secure(request))
    )
    return _login_out(auth, request)


@router.post(
    "/session/password-reset",
    operation_id="session_request_password_reset",
    status_code=202,
    response_class=Response,
    responses=problem_responses("validation-failed", "forbidden"),
)
def session_request_password_reset(
    body: PasswordResetIn, request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> Response:
    """Always 202 with an empty body, whether or not the account exists (04 T-PLT-42)."""
    facts = request_facts(request, clock)
    _refuse_foreign_origin(request)
    limiter: PasswordResetRateLimiter = request.app.state.password_reset_rate_limiter
    credentials.request_reset(
        body.email, facts=facts, keyring=request.app.state.keyring, limiter=limiter
    )
    return Response(status_code=202)


@router.post(
    "/session/password-reset/confirm",
    operation_id="session_confirm_password_reset",
    status_code=204,
    response_class=Response,
    responses=problem_responses(
        "validation-failed", "forbidden", "not-found", "password-policy", "rate-limited"
    ),
)
def session_confirm_password_reset(
    body: PasswordResetConfirmIn, request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> Response:
    """Set a new password with a reset token; every session of the user ends (04 T-PLT-42)."""
    facts = request_facts(request, clock)
    _refuse_foreign_origin(request)
    admit_address(request, facts)
    credentials.confirm_reset(
        body.token, body.new_password, facts=facts, keyring=request.app.state.keyring
    )
    return Response(status_code=204)


@router.post(
    "/session/mfa",
    operation_id="session_verify_mfa",
    response_model=SessionMfaOut,
    responses=problem_responses(
        "validation-failed",
        "unauthenticated",
        "session-expired",
        "forbidden",
        "invalid-transition",
        "account-locked",
        "rate-limited",
    ),
)
def session_verify_mfa(
    body: SessionMfaIn,
    request: Request,
    response: Response,
    auth: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated(tenant=False, open_to=CHALLENGE_PENDING)),
    ],
    idempotency_key: Annotated[str, Depends(command())],
) -> SessionMfaOut:
    """Verify a TOTP or recovery code: the session rotates with ``mfa_verified_at`` set (SAR-09;
    BS1-D-19, BS1-D-30). The attempt shares the sign-in rate limits (429), and five wrong codes
    lock the account for 15 minutes (423; D-80)."""
    facts = auth.facts
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    retry_after = limiter.admit(
        address=facts.source_ip or "unknown",
        email=sessions.normalise_email(auth.user.email),
        now=facts.now,
    )
    if retry_after is not None:
        raise Problem(
            "rate-limited",
            LOGIN_RETRY.format(seconds=retry_after),
            headers={"Retry-After": str(retry_after)},
        )
    verified = mfa.verify(
        auth,
        code=body.code,
        recovery_code=body.recovery_code,
        keyring=request.app.state.keyring,
    )
    forget_session(request)  # the presented session is ended: its kept answer goes with it
    response.headers.append(
        "set-cookie", sessions.cookie_header(verified.auth.token, secure=cookie_secure(request))
    )
    return SessionMfaOut(
        **_session_fields(verified.auth, request),
        recovery_codes_remaining=verified.recovery_codes_remaining,
    )


@router.post(
    "/session/logout",
    operation_id="session_logout",
    status_code=204,
    response_class=Response,
    responses=problem_responses(
        "validation-failed", "unauthenticated", "session-expired", "forbidden"
    ),
)
def session_logout(
    request: Request,
    auth: Annotated[
        AuthenticatedSession,
        Depends(require_authenticated(tenant=False, open_to=ANY_PENDING_STEP)),
    ],
    idempotency_key: Annotated[str, Depends(command())],
) -> Response:
    """End the session server-side and clear the cookie."""
    sessions.sign_out(auth, keyring=request.app.state.keyring)
    forget_session(request)  # the presented session is ended: its kept answer goes with it
    response = Response(status_code=204)
    response.headers.append(
        "set-cookie", sessions.cleared_cookie_header(secure=cookie_secure(request))
    )
    return response


@router.post(
    "/session/tenant",
    operation_id="session_select_tenant",
    response_model=SessionLoginOut,
    responses=problem_responses(
        "validation-failed",
        "unauthenticated",
        "session-expired",
        "forbidden",
        "mfa-required",
        "not-found",
        "invalid-transition",
    ),
)
def session_select_tenant(
    body: SessionTenantIn,
    request: Request,
    response: Response,
    auth: Annotated[AuthenticatedSession, Depends(require_authenticated(tenant=False))],
    idempotency_key: Annotated[str, Depends(command())],
) -> SessionLoginOut:
    """Open a workspace in a new session (SAR-09): through an ACTIVE membership, or for an
    operator through an approved support grant in force (SAR-29). A workspace that is not ACTIVE
    — an archived sandbox, or one whose copy has not completed — answers 409
    ``invalid-transition`` (05 SBX-07)."""
    keyring = request.app.state.keyring
    if auth.user.is_operator:
        selected = operators.select_support_tenant(auth, body.tenant_id, keyring=keyring)
    else:
        selected = sessions.select_tenant(auth, body.tenant_id, keyring=keyring)
    forget_session(request)  # the presented session is ended: its kept answer goes with it
    if selected.active_tenant is not None:
        request.state.tenant_kind = selected.active_tenant.kind.value
    response.headers.append(
        "set-cookie", sessions.cookie_header(selected.token, secure=cookie_secure(request))
    )
    return _login_out(selected, request)
