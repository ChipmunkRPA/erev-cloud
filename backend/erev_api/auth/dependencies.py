"""Authentication dependencies KRN-AUTH (dev-guide §5.3; 05 §2.5 steps 4 and 5; 04 API-C-02,
API-C-03).

``authenticate_session`` turns the request into an ``AuthenticatedSession``: the ``erev_session``
cookie is checked for idle and absolute expiry, and state-changing requests must carry the
synchronizer token from the public origin (DG-KRN-AUTH-01 step 2, DG-KRN-AUTH-02; SAR-11). It
also demands the second factor, which is the user's rule and not the route's (REQ-PLT-005;
SAR-26): a session that owes MFA enrolment or the sign-in challenge is refused with 403 on every
route except the session read, sign-out and the routes that settle the step it owes.
``require_authenticated()`` guards routes that act in the active tenant;
``require_authenticated(tenant=False)`` guards the session routes, which act before a tenant is
chosen (SPEC-Q-124) and take cookies only; ``require_authenticated(tenant="optional")`` passes a
session without an active tenant through as its ``AuthenticatedSession`` (D-83; ``GET /me``). A
principal in the active tenant holds the grants of its
membership's role assignments (dev-guide §5.4 ``effective_grants``). A tenant route called with
``Authorization: Bearer`` acts as the token's API client in the token's tenant, with the token's
scopes as grants and without the CSRF check (DG-KRN-AUTH-01 step 1; T-PLT-16). An operator session
acts as principal kind ``OPERATOR`` only under the support grant it carries, with read-only grants
and one audit event per request; ``refuse_operator_command`` answers its commands with 403
(REQ-PLT-036; SAR-29). ``require`` checks
one permission and its MFA requirement and audits a denial (DG-KRN-AUTH-03, DG-KRN-AUTH-05), and
hands on the context of a transaction of that permission: the entity scope its sessions carry is
the scope the permission is held for, not the union of the principal's roles (``admitted_by``;
04 API-C-03 rev 1.319);
``require_all_entities`` is ``require`` for a tenant-wide list or act, which a holder of named
entities is refused (supervisor ruling R-28);
``require_step_up`` needs a recent MFA verification (BS1-D-19); ``require_for_entity`` answers an
object outside the permission's entity scope with 404 (DG-KRN-AUTH-04).
"""

from __future__ import annotations

import dataclasses
import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Final, Literal, overload
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, Request
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from erev_api.audit.writer import record_denied
from erev_api.auth import api_clients, entity_scope, mfa, operators, sessions
from erev_api.auth.permissions import Grants, spec
from erev_api.auth.principal import OperatorContext, Principal, RequestContext
from erev_api.auth.ratelimit import LoginRateLimiter, RequestRateLimiter, RouteClass
from erev_api.auth.sessions import ActiveTenant, AuthenticatedSession, CsrfEvidence, RequestFacts
from erev_api.clock import Clock, get_clock
from erev_api.config import Settings
from erev_api.enums import IdentityProviderKind, PrincipalKind
from erev_api.problems import Problem, request_id_for

UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FORWARDED_FOR: Final = "X-Forwarded-For"
BEARER_SCHEME: Final = "bearer"
# DG-KRN-AUTH-03: the OpenAPI extension naming a route's permission.
PERMISSION_EXTENSION: Final = "x-erev-permission"
_PERMISSION_ATTRIBUTE: Final = "erev_permission"
# [J] A guard denial concerns the route, not a record (SPEC-Q-142).
DENIED_OBJECT_TYPE: Final = "route"
# The ``scope`` a denial's detail states when the route asks for all entities (ruling R-28), as
# the report guard states it (``reports.framework.require_report``).
ALL_ENTITIES_SCOPE: Final = "*"
# [J] SPEC-Q-194: copy of the operator guard's refusal.
OPERATOR_ONLY: Final = "Only a platform operator can do this."
# REQ-PLT-005 (DG-KRN-AUTH-03): the second-factor steps a route answers while the session still
# owes them. Every other cookie route refuses such a session.
NO_PENDING_STEP: Final[frozenset[mfa.PendingStep]] = frozenset()
ENROLMENT_PENDING: Final[frozenset[mfa.PendingStep]] = frozenset({"enrolment"})
CHALLENGE_PENDING: Final[frozenset[mfa.PendingStep]] = frozenset({"challenge"})
ANY_PENDING_STEP: Final[frozenset[mfa.PendingStep]] = ENROLMENT_PENDING | CHALLENGE_PENDING
# The attribute a session guard carries when its route is open to a pending step (DG-ARC-04).
OPEN_TO_ATTRIBUTE: Final = "erev_open_to"
# The audit action of a second-factor refusal on a route that declares no permission.
SECOND_FACTOR_ACTION: Final = "session.second_factor"
_GRANTS_ATTRIBUTE: Final = "membership_grants"
_STEP_ATTRIBUTE: Final = "second_factor_step"
# What the identity store answered for the request's credential, kept on ``request.state`` so
# that the store is asked once per request (DG-KRN-AUTH-09; 05 §2.5; item AUTH-BEFORE-BODY-1):
# the route class asks the route's session question before the body is read, and FastAPI asks
# it again when it solves the route's dependencies.
_SESSION_ATTRIBUTE: Final = "authenticated_session"
_BEARER_ATTRIBUTE: Final = "bearer_context"
_OPERATOR_ATTRIBUTE: Final = "operator_context"
# How long an answer is kept. The two questions of a request are milliseconds apart when its
# body arrives with its headers; a body that takes longer must not carry an answer past it — a
# session ended while the body arrived is refused when the command starts, as it was while the
# guard ran after the body. A question asked later than this asks the store again.
KEPT_FOR: Final = timedelta(seconds=1)
# The mark of a session question: a function of ``(request, clock)`` that answers whose request
# this is, or refuses it. ``session_questions`` finds it in a route's dependency tree.
_SESSION_QUESTION_ATTRIBUTE: Final = "erev_session_question"


@dataclass(frozen=True, slots=True)
class _KeptSession:
    """The cookie session the identity store answered for ``token``, and whether the
    synchronizer token and the origin were checked with it (DG-KRN-AUTH-02). The instant of
    the answer is ``auth.facts.now``."""

    token: str
    csrf_checked: bool
    auth: AuthenticatedSession


def _fresh(answered_at: datetime, now: datetime) -> bool:
    """Whether an answer of ``answered_at`` still serves a question asked at ``now``."""
    return timedelta(0) <= now - answered_at <= KEPT_FOR


def forget_session(request: Request) -> None:
    """Drop what the identity store answered for this request's cookie. A handler that ends
    the session it was called with — a rotation (``POST /session/tenant``, ``/session/mfa``,
    ``/me/mfa/confirm``, ``/me/password``) or the sign-out — calls it once the session is
    ended: a guard asked later in the same request asks the store again and reads its answer,
    the refusal of the ended session. A kept answer never outlives the session it was given
    for (``tests/architecture/test_routes.py`` holds the callers)."""
    for name in (_SESSION_ATTRIBUTE, _OPERATOR_ATTRIBUTE):
        if hasattr(request.state, name):
            delattr(request.state, name)


def client_ip(request: Request, trusted_proxy_hops: int) -> str | None:
    """The client address: ``X-Forwarded-For`` counted ``trusted_proxy_hops`` from the right, or
    the peer address without trusted proxies (SAR-13; CFG-25). Anything that is not an IP address
    is None."""
    candidate: str | None = request.client.host if request.client is not None else None
    if trusted_proxy_hops > 0:
        forwarded = [
            part.strip() for part in request.headers.get(FORWARDED_FOR, "").split(",") if part
        ]
        forwarded = [part for part in forwarded if part]
        if len(forwarded) >= trusted_proxy_hops:
            candidate = forwarded[-trusted_proxy_hops]
    if candidate is None:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def origin_allowed(request: Request, public_origin: str) -> bool:
    """``Origin``, or the origin of ``Referer`` when ``Origin`` is absent, equals the public origin.

    A request with neither header comes from a non-browser client and passes (SPEC-Q-127).
    """
    origin = request.headers.get("origin")
    if origin is not None:
        return origin == public_origin
    referer = request.headers.get("referer")
    if referer is not None:
        parts = urlsplit(referer)
        return f"{parts.scheme}://{parts.netloc}" == public_origin
    return True


def request_facts(request: Request, clock: Clock) -> RequestFacts:
    settings: Settings = request.app.state.settings
    return RequestFacts(
        request_id=request_id_for(request),
        source_ip=client_ip(request, settings.trusted_proxy_hops),
        user_agent=request.headers.get("user-agent"),
        now=clock.now(),
    )


def authenticate_session(
    request: Request,
    clock: Clock,
    *,
    enforce_csrf: bool = True,
    open_to: frozenset[mfa.PendingStep] = NO_PENDING_STEP,
) -> AuthenticatedSession:
    """The cookie session of the request, or the 401 or 403 problem (DG-KRN-AUTH-01, -02).

    Every cookie route passes through here, so this is where the second factor is demanded
    (REQ-PLT-005; DG-KRN-AUTH-03): a session that owes enrolment or the challenge is refused with
    403 unless the route names that step in ``open_to``. Bearer tokens never come this way: an API
    client is not a user and carries no second factor.
    """
    # Session routes are cookie routes: a bearer token authenticates tenant routes only.
    if request.headers.get("authorization") is not None:
        raise Problem("unauthenticated", sessions.SIGN_IN_REQUIRED)
    token = request.cookies.get(sessions.COOKIE_NAME)
    if not token:
        raise Problem("unauthenticated", sessions.SIGN_IN_REQUIRED)
    settings: Settings = request.app.state.settings
    csrf = (
        CsrfEvidence(
            token=request.headers.get(sessions.CSRF_HEADER),
            origin_allowed=origin_allowed(request, settings.public_origin),
        )
        if enforce_csrf and request.method in UNSAFE_METHODS
        else None
    )
    # The store is asked once per request (``_SESSION_ATTRIBUTE``). An answer kept without the
    # synchronizer check does not serve a call that needs it, and an answer older than
    # ``KEPT_FOR`` serves nobody: such a call asks again.
    facts = request_facts(request, clock)
    kept: _KeptSession | None = getattr(request.state, _SESSION_ATTRIBUTE, None)
    if (
        kept is not None
        and kept.token == token
        and (kept.csrf_checked or csrf is None)
        and _fresh(kept.auth.facts.now, facts.now)
    ):
        auth = kept.auth
    else:
        auth = sessions.authenticate(
            token, facts=facts, keyring=request.app.state.keyring, csrf=csrf
        )
        setattr(request.state, _SESSION_ATTRIBUTE, _KeptSession(token, csrf is not None, auth))
    # SAR-13 / SOP-4: every authenticated browser path — active workspace, no workspace, tenant-free
    # and operator routes alike — enters the session's bucket here, exactly once per request
    # (Codex P4-SOP4-BROWSER-1). Login and MFA challenges keep their own address / email limits.
    _admit_browser_session(request, auth)
    if auth.active_tenant is not None:
        # DG-API-06: the middleware echoes the kind on the response.
        request.state.tenant_kind = auth.active_tenant.kind.value
    _require_second_factor(request, auth, open_to)
    return auth


def _membership_grants(
    request: Request, auth: AuthenticatedSession, tenant_id: UUID, membership_id: UUID
) -> Grants:
    """The grants of one of the user's memberships in force at the request time, read once per
    request: the second-factor rule and the request context ask for the same membership."""
    memo: dict[UUID, Grants] | None = getattr(request.state, _GRANTS_ATTRIBUTE, None)
    if memo is None:
        memo = {}
        setattr(request.state, _GRANTS_ATTRIBUTE, memo)
    if membership_id not in memo:
        memo[membership_id] = mfa.membership_grants(auth, tenant_id, membership_id)
    return memo[membership_id]


def second_factor_step(request: Request, auth: AuthenticatedSession) -> mfa.NextStep:
    """The second-factor step ``auth`` still owes (``mfa.next_step``), read once per request and
    session: the guard and the session answers (``GET /session``, the sign-in answers) state the
    same step."""
    cached: tuple[UUID, mfa.NextStep] | None = getattr(request.state, _STEP_ATTRIBUTE, None)
    if cached is not None and cached[0] == auth.session.id:
        return cached[1]
    step = mfa.next_step(
        auth,
        grants=lambda tenant_id, membership_id: _membership_grants(
            request, auth, tenant_id, membership_id
        ),
    )
    setattr(request.state, _STEP_ATTRIBUTE, (auth.session.id, step))
    return step


def _require_second_factor(
    request: Request, auth: AuthenticatedSession, open_to: frozenset[mfa.PendingStep]
) -> None:
    """REQ-PLT-005 for the session: 403 while it owes a step the route does not settle.

    A session that owes enrolment gets the ERR-27 enrolment copy, one that owes the challenge the
    verification copy. In an open workspace the refusal first writes its ``DENIED`` audit event, as
    a ``require`` denial does (DG-KRN-AUTH-05); its ``detail.step`` names the step owed. With no
    workspace membership open — a user of several workspaces, an operator — it first writes the
    security event ``MFA_PENDING_DENIED`` (05 SAR-26 rev 1.128; ruling R-111 (6)): every refusal
    is in exactly one of the two logs."""
    pending = second_factor_step(request, auth).pending
    if pending is None or pending in open_to:
        return
    active = auth.active_tenant
    if active is not None and active.membership_id is not None:
        route = request.scope.get("route")
        codes = (
            declared_permissions(route.dependant) if isinstance(route, APIRoute) else frozenset()
        )
        permission = ",".join(sorted(codes))
        record_denied(
            _session_context(request, auth, active),
            action=permission or SECOND_FACTOR_ACTION,
            object_type=DENIED_OBJECT_TYPE,
            object_id=None,
            permission=permission,
            detail={
                "method": request.method,
                "path": _route_path(request),
                "reason": mfa.SECOND_FACTOR_SLUG,
                "step": pending,
            },
            keyring=request.app.state.keyring,
        )
    else:
        mfa.record_pending_denied(
            auth,
            keyring=request.app.state.keyring,
            method=request.method,
            path=_route_path(request),
            step=pending,
        )
    raise Problem(
        mfa.SECOND_FACTOR_SLUG,
        mfa.ENROLMENT_REQUIRED if pending == "enrolment" else mfa.VERIFICATION_REQUIRED,
    )


RATE_LIMITED_DETAIL: Final = "Too many requests. Try again in {seconds} seconds."


def admit_request(
    request: Request,
    route_class: RouteClass,
    *,
    now: datetime,
    client_id: str | None = None,
    session_id: str | None = None,
    api_client_id: str | None = None,
    api_client_limit: int | None = None,
) -> None:
    """SAR-13 / API-C-16 (SOP-4): count the request in its bucket or refuse it with 429
    ``rate-limited`` and ``Retry-After``. The limiter is the api process's own
    (``app.state.request_rate_limiter``, DG-API-07); a refusal is raised before any handler runs,
    so it is never stored as an idempotent response (DG-KRN-IDEM-03)."""
    limiter: RequestRateLimiter = request.app.state.request_rate_limiter
    decision = limiter.admit(
        route_class,
        now=now,
        client_id=client_id,
        session_id=session_id,
        api_client_id=api_client_id,
        api_client_limit=api_client_limit,
    )
    if not decision.allowed:
        raise Problem(
            "rate-limited",
            RATE_LIMITED_DETAIL.format(seconds=decision.retry_after),
            headers=decision.headers,
        )


def admit_address(request: Request, facts: RequestFacts) -> None:
    """05 SAR-13 rev 1.90 (ruling R-48 (e)): count the request in the per-address bucket of the
    login class — 50 per minute per client address, shared with sign-in and the MFA challenge —
    or refuse it with 429 ``rate-limited`` and ``Retry-After``. Every unauthenticated route of the
    sign-in surface calls it before it looks at what the request carries: the token endpoint,
    the invitation lookup and acceptance, the password-reset confirmation, the OIDC start and
    callback. A refused request is not counted."""
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    retry_after = limiter.admit(address=facts.source_ip or "unknown", email=None, now=facts.now)
    if retry_after is not None:
        raise Problem(
            "rate-limited",
            RATE_LIMITED_DETAIL.format(seconds=retry_after),
            headers={"Retry-After": str(retry_after)},
        )


_ADMITTED_ATTRIBUTE: Final = "browser_session_admitted"
_CLIENT_ADMITTED_ATTRIBUTE: Final = "api_client_admitted"


def _admit_browser_session(request: Request, auth: AuthenticatedSession) -> None:
    """The BROWSER_SESSION bucket (1,200 per minute) keyed on the real session identity, counted
    once per request however many session dependencies the route resolves."""
    session_id = str(auth.session.id)
    if getattr(request.state, _ADMITTED_ATTRIBUTE, None) == session_id:
        return
    admit_request(request, "BROWSER_SESSION", now=auth.facts.now, session_id=session_id)
    setattr(request.state, _ADMITTED_ATTRIBUTE, session_id)


def _bearer_context(request: Request, clock: Clock, authorization: str) -> RequestContext:
    """The request context of an API client access token; CSRF does not apply (DG-KRN-AUTH-02).
    Resolved once per request: the answer for the header's own text is kept
    (``_BEARER_ATTRIBUTE``) for ``KEPT_FOR``."""
    facts = request_facts(request, clock)
    kept: tuple[str, RequestContext] | None = getattr(request.state, _BEARER_ATTRIBUTE, None)
    if kept is not None and kept[0] == authorization and _fresh(kept[1].now, facts.now):
        return kept[1]
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != BEARER_SCHEME or not token.strip():
        raise api_clients.bearer_refusal()
    resolved = api_clients.token_principal(token.strip(), now=facts.now)
    # Counted once per request, as a browser session is: the upload route resolves the context
    # before it reads the body and again when the command starts (``api.uploads``).
    client_id = str(resolved.principal.id)
    if getattr(request.state, _CLIENT_ADMITTED_ATTRIBUTE, None) != client_id:
        admit_request(
            request,
            "API_CLIENT",
            now=facts.now,
            api_client_id=client_id,
            api_client_limit=resolved.rate_limit_per_minute,
        )
        setattr(request.state, _CLIENT_ADMITTED_ATTRIBUTE, client_id)
    # DG-API-06: the middleware echoes the kind on the response.
    request.state.tenant_kind = resolved.tenant_kind.value
    ctx = RequestContext(
        principal=resolved.principal,
        tenant_kind=resolved.tenant_kind,
        request_id=facts.request_id,
        source_ip=facts.source_ip,
        user_agent=facts.user_agent,
        idempotency_key=request.headers.get("idempotency-key"),
        if_match=request.headers.get("if-match"),
        now=facts.now,
        format_locale=resolved.default_locale,
        tenant_status=resolved.tenant_status,
    )
    setattr(request.state, _BEARER_ATTRIBUTE, (authorization, ctx))
    return ctx


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))


def _operator_context(request: Request, auth: AuthenticatedSession) -> RequestContext:
    """An operator under its support grant: read-only grants and one audit event per request —
    the context is kept with the session it was built for (``_OPERATOR_ATTRIBUTE``), so a
    second question of the same request writes no second event (SAR-29), however long the
    request's body took."""
    kept: tuple[UUID, RequestContext] | None = getattr(request.state, _OPERATOR_ATTRIBUTE, None)
    if kept is not None and kept[0] == auth.session.id:
        return kept[1]
    ctx = operators.operator_context(
        auth,
        idempotency_key=request.headers.get("idempotency-key"),
        if_match=request.headers.get("if-match"),
    )
    operators.record_access(
        ctx, method=request.method, path=_route_path(request), keyring=request.app.state.keyring
    )
    setattr(request.state, _OPERATOR_ATTRIBUTE, (auth.session.id, ctx))
    return ctx


def refuse_operator_command(request: Request, ctx: RequestContext) -> None:
    """403 ``forbidden`` for every tenant command of an operator, audited as a denial.

    Support access is read-only (T-PLT-33 scope ``READ_ONLY``; REQ-PLT-036; DG-KRN-AUTH-05).
    """
    if ctx.principal.kind is not PrincipalKind.OPERATOR:
        return
    route = request.scope.get("route")
    codes = declared_permissions(route.dependant) if isinstance(route, APIRoute) else frozenset()
    record_denied(
        ctx,
        action=operators.COMMAND_DENIED_ACTION,
        object_type=DENIED_OBJECT_TYPE,
        object_id=None,
        permission=",".join(sorted(codes)),
        detail={
            "method": request.method,
            "path": _route_path(request),
            "reason": "support-grant-read-only",
        },
        keyring=request.app.state.keyring,
    )
    raise Problem("forbidden", operators.READ_ONLY_DETAIL)


def get_request_context(
    request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> RequestContext:
    """The request context in the session's active tenant; without one, 401 ``unauthenticated``.

    Roles, permissions and entity scope come from the membership's assignments in force at the
    request time (``effective_grants``); a membership without assignments holds nothing, so every
    permission check fails closed (XR-12). An ``Authorization`` header selects the API client of a
    bearer token instead (``api_clients.token_principal``).
    """
    authorization = request.headers.get("authorization")
    if authorization is not None:
        return _bearer_context(request, clock, authorization)
    auth = authenticate_session(request, clock)
    if auth.active_tenant is None:
        raise Problem("unauthenticated", sessions.SIGN_IN_REQUIRED)
    return _session_context(request, auth, auth.active_tenant)


def get_optional_request_context(
    request: Request, clock: Annotated[Clock, Depends(get_clock)]
) -> RequestContext | AuthenticatedSession:
    """``get_request_context``, except that a cookie session without an active tenant passes as its
    ``AuthenticatedSession`` instead of 401 (D-83)."""
    authorization = request.headers.get("authorization")
    if authorization is not None:
        return _bearer_context(request, clock, authorization)
    auth = authenticate_session(request, clock)
    if auth.active_tenant is None:
        return auth
    return _session_context(request, auth, auth.active_tenant)


setattr(get_request_context, _SESSION_QUESTION_ATTRIBUTE, True)  # noqa: B010 - a mark
setattr(get_optional_request_context, _SESSION_QUESTION_ATTRIBUTE, True)  # noqa: B010 - a mark


def session_questions(dependant: Dependant) -> tuple[Callable[[Request, Clock], object], ...]:
    """The session questions in a route's dependency tree, each once, in the order found: the
    functions of ``(request, clock)`` that carry the mark — ``get_request_context`` (under
    ``require`` and every guard built on it), ``get_optional_request_context`` and the
    questions of ``require_authenticated`` and ``require_operator``. Empty for a route without
    a guard (API-C-01). ``api.deps.GuardedRoute`` asks them before the route's body is read
    (05 §2.5; DG-KRN-AUTH-09)."""
    found: list[Callable[[Request, Clock], object]] = []
    pending = list(dependant.dependencies)
    while pending:
        current = pending.pop(0)
        call = current.call
        if call is not None and getattr(call, _SESSION_QUESTION_ATTRIBUTE, False):
            if not any(call is known for known in found):
                found.append(call)
        pending.extend(current.dependencies)
    return tuple(found)


def _session_context(
    request: Request, auth: AuthenticatedSession, active: ActiveTenant
) -> RequestContext:
    """The request context of a cookie session in its active tenant (the session was admitted to
    its SAR-13 bucket by ``authenticate_session``)."""
    if active.membership_id is None:
        return _operator_context(request, auth)
    grants = _membership_grants(request, auth, active.id, active.membership_id)
    principal = Principal(
        kind=PrincipalKind.USER,
        id=auth.user.id,
        tenant_id=active.id,
        membership_id=active.membership_id,
        display_name=auth.user.display_name,
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope=grants.entity_scope,
        auth_method="oidc" if auth.session.auth_method is IdentityProviderKind.OIDC else "password",
        mfa_verified_at=auth.session.mfa_verified_at,
        session_id=auth.session.id,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=grants.role_scopes,
    )
    locale = auth.user.preferences.get("format_locale")
    return RequestContext(
        principal=principal,
        tenant_kind=active.kind,
        request_id=auth.facts.request_id,
        source_ip=auth.facts.source_ip,
        user_agent=auth.facts.user_agent,
        idempotency_key=request.headers.get("idempotency-key"),
        if_match=request.headers.get("if-match"),
        now=auth.facts.now,
        format_locale=locale if isinstance(locale, str) else active.default_locale,
        tenant_status=active.status,
    )


def _record_guard_denial(
    request: Request, ctx: RequestContext, permission: str, **detail: str
) -> None:
    record_denied(
        ctx,
        action=permission,
        object_type=DENIED_OBJECT_TYPE,
        object_id=None,
        permission=permission,
        detail={"method": request.method, "path": _route_path(request), **detail},
        keyring=request.app.state.keyring,
    )


def admitted_by(ctx: RequestContext, permission: str) -> RequestContext:
    """``ctx`` as the context of a transaction of ``permission`` (04 API-C-03 rev 1.319; 03
    REQ-PLT-012 rev 1.146; DG-KRN-AUTH-03 rev 1.295; item READ-SCOPE-BY-PERMISSION-1, register
    index 301): the principal's ``entity_scope`` — what ``db_context`` hands every session and
    unit of work, and so what row-level security reads from ``app.entity_scope`` — is the scope
    the principal holds ``permission`` for, not the union of the entities of all its roles.

    A guarded transaction is a transaction of the permission that admitted it: R-28's sentence —
    a command on a row of an entity needs its permission FOR that entity, not the permission for
    another entity and some role on this one — said of the transaction instead of the row.
    Measured before, with default roles alone: a Viewer of one entity who held the Service
    Account role for a second read the second entity's periods, books and entity row
    (``config.read`` is the Viewer's, for the first entity only); a Revenue Accountant of one
    entity who was a Viewer of a second wrote the second entity's posting rule
    (``config.author`` is the accountant's, for the first only). ``permission_scopes`` and
    ``role_scopes`` are left whole: a handler that asks another permission's scope still reads
    it. A principal whose permissions share one scope — an API client, an operator under its
    grant — is handed back unchanged. A permission the principal does not hold names no entity
    (fail closed); ``require`` refuses such a caller before it asks."""
    principal = ctx.principal
    held = principal.permission_scopes.get(permission, frozenset())
    scope: Literal["*"] | tuple[UUID, ...] = (
        tuple(sorted(held)) if isinstance(held, frozenset) else "*"
    )
    if scope == principal.db_context.entity_scope:
        return ctx
    return dataclasses.replace(ctx, principal=dataclasses.replace(principal, entity_scope=scope))


def require(permission: str) -> Callable[..., RequestContext]:
    """Guard of routes that need ``permission`` (DG-KRN-AUTH-03).

    A principal without it gets 403 ``forbidden``; a principal holding a ``requires_mfa``
    permission in a session without MFA verification gets 403 ``mfa-required``, with the ERR-27
    copy for a user not yet enrolled or not yet verified (REQ-PLT-005). Each denial first writes one
    ``DENIED`` audit event in a transaction of its own (DG-KRN-AUTH-05). The code travels on the
    dependency, so ``api.deps.GuardedRoute`` records it as ``openapi_extra["x-erev-permission"]``.
    An unknown code raises ``KeyError`` when the route is declared.

    The context it hands on is the context of a transaction of ``permission`` (``admitted_by``;
    rev 1.295): every session and unit of work the route opens from it reads and writes under
    the scope the principal holds the route's OWN permission for. ``require_all_entities`` and
    ``api.deps.command`` build on this guard, so reads and commands follow alike; a route
    without a permission guard keeps the union of the principal's roles.

    A user who holds a ``requires_mfa`` permission never reaches this check with an unverified
    session: ``authenticate_session`` refuses the session first (the second-factor rule is the
    user's). The check stays for API clients, which carry no second factor, and as a second line.
    """
    requires_mfa = spec(permission).requires_mfa

    def dependency(
        request: Request, ctx: Annotated[RequestContext, Depends(get_request_context)]
    ) -> RequestContext:
        principal = ctx.principal
        if permission not in principal.permissions:
            _record_guard_denial(request, ctx, permission)
            raise Problem("forbidden")
        if requires_mfa and principal.mfa_verified_at is None:
            enrolled = (
                principal.kind is PrincipalKind.USER
                and principal.id is not None
                and mfa.has_confirmed_factor(principal.id, request_id=ctx.request_id)
            )
            _record_guard_denial(request, ctx, permission, reason="mfa-required")
            raise Problem(
                "mfa-required",
                mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED,
            )
        return admitted_by(ctx, permission)

    setattr(dependency, _PERMISSION_ATTRIBUTE, permission)
    return dependency


def require_all_entities(permission: str) -> Callable[..., RequestContext]:
    """Guard of a tenant-wide list or act (supervisor ruling R-28; 03 REQ-PLT-012;
    DG-KRN-AUTH-03): ``require(permission)`` and, for a principal that holds the permission for
    named entities only, 403 ``forbidden`` after one ``DENIED`` audit event whose detail states
    the scope the route asks for (``scope`` ``"*"``; DG-KRN-AUTH-05).

    The rows behind such a list carry no entity and may hold the data of any — the audit log
    and who acted in it, the workspace's control evidence — and such an act reaches every entity:
    the tenant's settings, a snapshot, a webhook endpoint, an operator's grant, a verification of
    the chain. A holder restricted to named entities is refused rather than shown a list that
    looks filtered. The code travels on the dependency as it does on ``require``."""
    guard = require(permission)

    def dependency(
        request: Request,
        ctx: RequestContext = Depends(guard),  # noqa: B008 - the guard is local to this factory
    ) -> RequestContext:
        if not entity_scope.holds_all(ctx.principal, permission):
            _record_guard_denial(request, ctx, permission, scope=ALL_ENTITIES_SCOPE)
            raise Problem("forbidden")
        return ctx

    setattr(dependency, _PERMISSION_ATTRIBUTE, permission)
    return dependency


def declared_permissions(dependant: Dependant) -> frozenset[str]:
    """The codes of every ``require`` guard in a route's dependency tree."""
    codes: set[str] = set()
    pending = list(dependant.dependencies)
    while pending:
        current = pending.pop()
        code = getattr(current.call, _PERMISSION_ATTRIBUTE, None)
        if isinstance(code, str):
            codes.add(code)
        pending.extend(current.dependencies)
    return frozenset(codes)


def require_for_entity(ctx: RequestContext, permission: str, entity_id: UUID | None) -> None:
    """Pass when ``permission`` is held for ``entity_id``; otherwise 404 ``not-found``.

    ``None`` names a tenant-wide object, which passes when the permission is held for any entity
    (DG-KRN-AUTH-04; REQ-PLT-012).
    """
    scope = ctx.principal.permission_scopes.get(permission)
    if scope is None:
        raise Problem("not-found")
    if entity_id is not None and isinstance(scope, frozenset) and entity_id not in scope:
        raise Problem("not-found")


@overload
def require_authenticated() -> Callable[..., RequestContext]: ...


@overload
def require_authenticated(
    *, tenant: Literal[False], open_to: frozenset[mfa.PendingStep] = ...
) -> Callable[..., AuthenticatedSession]: ...


@overload
def require_authenticated(
    *, tenant: Literal["optional"]
) -> Callable[..., RequestContext | AuthenticatedSession]: ...


def require_authenticated(
    *,
    tenant: bool | Literal["optional"] = True,
    open_to: frozenset[mfa.PendingStep] = NO_PENDING_STEP,
) -> Callable[..., Any]:
    """Guard of routes open to any signed-in user (DG-KRN-AUTH-03).

    ``tenant="optional"`` gives the request context in the active tenant, or the session itself
    while no workspace is open (D-83). ``open_to`` names the second-factor steps a session route
    answers while the session still owes them — sign-out, the enrolment routes and the challenge
    (REQ-PLT-005); only a ``tenant=False`` route takes it, and every other route refuses a session
    that owes a step.
    """
    if open_to and tenant is not False:
        raise ValueError("only a session route (tenant=False) is open to a pending second factor")
    if tenant == "optional":

        def optional_dependency(
            request: Request, clock: Annotated[Clock, Depends(get_clock)]
        ) -> RequestContext | AuthenticatedSession:
            return get_optional_request_context(request, clock)

        setattr(optional_dependency, _SESSION_QUESTION_ATTRIBUTE, True)  # noqa: B010 - a mark
        return optional_dependency
    if tenant:

        def dependency(
            request: Request, clock: Annotated[Clock, Depends(get_clock)]
        ) -> RequestContext:
            return get_request_context(request, clock)

        setattr(dependency, _SESSION_QUESTION_ATTRIBUTE, True)  # noqa: B010 - a mark
        return dependency

    def session_dependency(
        request: Request, clock: Annotated[Clock, Depends(get_clock)]
    ) -> AuthenticatedSession:
        return authenticate_session(request, clock, open_to=open_to)

    if open_to:
        setattr(session_dependency, OPEN_TO_ATTRIBUTE, open_to)
    setattr(session_dependency, _SESSION_QUESTION_ATTRIBUTE, True)  # noqa: B010 - a mark
    return session_dependency


def open_steps(dependant: Dependant) -> frozenset[mfa.PendingStep]:
    """The pending second-factor steps the session guards of a route's dependency tree answer;
    empty for a route that refuses every pending session."""
    steps: set[mfa.PendingStep] = set()
    pending = list(dependant.dependencies)
    while pending:
        current = pending.pop()
        steps |= getattr(current.call, OPEN_TO_ATTRIBUTE, frozenset())
        pending.extend(current.dependencies)
    return frozenset(steps)


def require_operator() -> Callable[..., OperatorContext]:
    """Guard of the operator routes, which act outside any tenant (DG-KRN-TEN-05; 04 API-R-54).

    Only a cookie session of an ``app_user`` with ``is_operator`` passes, and only once MFA is
    verified: a bearer token or another user gets 403 ``forbidden``; an operator's unverified
    session is refused by ``authenticate_session`` like any session that owes its second factor
    (MFA is mandatory for an operator). The CSRF check of ``authenticate_session`` applies; no
    active tenant and no support grant is needed, because the routes read no tenant data.
    """

    def dependency(
        request: Request, clock: Annotated[Clock, Depends(get_clock)]
    ) -> OperatorContext:
        if request.headers.get("authorization") is not None:
            raise Problem("forbidden", OPERATOR_ONLY)
        auth = authenticate_session(request, clock)
        if not auth.user.is_operator:
            raise Problem("forbidden", OPERATOR_ONLY)
        if auth.session.mfa_verified_at is None:
            enrolled = mfa.has_confirmed_factor(auth.user.id, request_id=auth.facts.request_id)
            raise Problem(
                "mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED
            )
        return OperatorContext(
            operator_user_id=auth.user.id,
            session_id=auth.session.id,
            request_id=auth.facts.request_id,
            now=auth.facts.now,
        )

    setattr(dependency, _SESSION_QUESTION_ATTRIBUTE, True)  # noqa: B010 - a mark
    return dependency


def require_step_up() -> Callable[..., AuthenticatedSession]:
    """Guard of commands that need a TOTP verification at most five minutes old (BS1-D-19; PRD
    BR-PLT-06); an older or absent ``mfa_verified_at`` gives 403 ``mfa-step-up-required``.

    It builds on ``require_authenticated(tenant=False)``, so the route keeps exactly one guard
    (DG-ARC-04).
    """

    def dependency(
        auth: Annotated[AuthenticatedSession, Depends(require_authenticated(tenant=False))],
    ) -> AuthenticatedSession:
        if not mfa.step_up_fresh(auth):
            raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
        return auth

    return dependency
