"""Browser sessions KRN-AUTH (04 T-PLT-08, API-R-01; 05 SAR-06, SAR-09 to SAR-11; 03 REQ-PLT-004).

The identity repositories behind the session routes (dev-guide DG-KRN-DB-02): sign-in with
lockout, cookie authentication with idle and absolute expiry and the synchronizer check
(DG-KRN-AUTH-01, DG-KRN-AUTH-02), sign-out and workspace selection. Password sign-in opens the
workspace of the user's only ACTIVE membership; with none or several the session stays without one
and the client shows workspace selection (D-83). Each flow writes its security events in the
transaction that changes the session; a refused request commits its evidence first and raises its
problem afterwards.

Session tokens are 32 random bytes, base64url without padding (43 characters), and the row keeps
the SHA-256 of the cookie value (DG-KRN-AUTH-06). The synchronizer token is HMAC-SHA256 keyed by
the session token, so ``GET /session`` can return it again while the row keeps only its SHA-256
(SPEC-Q-125).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from sqlalchemy import RowMapping, Select, insert, select, update
from sqlalchemy.orm import Session

from erev_api.auth import passwords
from erev_api.auth.keyring import KeyRing
from erev_api.auth.security_events import (
    USER_AGENT_MAX_CHARS,
    hold_chain_lock,
    record_security_event,
)
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables.platform import (
    app_user,
    identity_provider,
    security_event,
    support_grant,
    tenant,
    tenant_membership,
    user_session,
)
from erev_api.enums import (
    AuditOutcome,
    GrantStatus,
    IdentityProviderKind,
    MembershipStatus,
    PrincipalKind,
    SecurityEventKind,
    SessionEndReason,
    TenantKind,
    TenantStatus,
    UserStatus,
)
from erev_api.problems import Problem, ProblemError
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.resolve import setting

COOKIE_NAME: Final = "erev_session"
CSRF_HEADER: Final = "X-CSRF-Token"
ABSOLUTE_LIFETIME: Final = timedelta(hours=12)  # SAR-10
TOUCH_INTERVAL: Final = timedelta(seconds=60)  # 05 §2.5 step 4
RETENTION: Final = timedelta(days=30)  # T-PLT-08 expires_at
MAX_FAILED_LOGINS: Final = 5  # REQ-PLT-004
LOCKOUT: Final = timedelta(minutes=15)
# ``security_event.detail`` of a failed password sign-in: the running count of the account, or of
# the email when no account matches; and the end of the lockout of such an email.
FAILED_LOGIN_COUNT: Final = "failed_login_count"
LOCKED_UNTIL: Final = "locked_until"
IDLE_MINUTES_KEY: Final = "platform.session_idle_minutes"
_CSRF_CONTEXT: Final = b"erev-csrf-v1"

# PRD §5.5 and SCREENS_B §12.1 copy.
SIGN_IN_REQUIRED: Final = "Sign in to continue."
WRONG_CREDENTIALS: Final = "The email or password is incorrect."
ACCOUNT_LOCKED: Final = (
    "Too many failed sign-in attempts. Try again in 15 minutes or ask a workspace administrator."
)
IDLE_EXPIRED: Final = "Your session ended after {minutes} minutes without activity. Sign in again."
ABSOLUTE_EXPIRED: Final = "Your session reached the 12-hour limit. Sign in again."
CSRF_REFUSED: Final = "Send the CSRF token of this session from the eRev origin."
# [J] SPEC-Q-192: the documents give no copy for a refused OIDC sign-in.
OIDC_REFUSED: Final = (
    "Sign-in through your identity provider did not complete. Try again or sign in with your email "
    "and password."
)
# The reason of ``LOGIN_FAILED`` when a sign-in names a provider the operator disabled (05 SAR-27).
PROVIDER_DISABLED: Final = "provider_disabled"


@dataclass(frozen=True, slots=True)
class RequestFacts:
    request_id: str
    source_ip: str | None
    user_agent: str | None
    now: datetime  # Clock.now() captured once at request start


@dataclass(frozen=True, slots=True)
class CsrfEvidence:
    """What a state-changing cookie request presents: the header token and the origin verdict."""

    token: str | None
    origin_allowed: bool


@dataclass(frozen=True, slots=True)
class SessionRow:
    id: UUID
    user_id: UUID
    csrf_token_sha256: str
    auth_method: IdentityProviderKind
    mfa_verified_at: datetime | None
    active_tenant_id: UUID | None
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    # T-PLT-08: set while an operator session acts under a support grant (REQ-PLT-036).
    operator_support_grant_id: UUID | None = None

    def expiry_reason(self, now: datetime) -> SessionEndReason | None:
        if now >= self.absolute_expires_at:
            return SessionEndReason.ABSOLUTE_TIMEOUT
        if now >= self.idle_expires_at:
            return SessionEndReason.IDLE_TIMEOUT
        return None


@dataclass(frozen=True, slots=True)
class UserRef:
    id: UUID
    email: str
    display_name: str
    preferences: Mapping[str, Any]
    is_operator: bool = False


@dataclass(frozen=True, slots=True)
class ActiveTenant:
    id: UUID
    code: str
    display_name: str
    kind: TenantKind
    default_locale: str
    membership_id: UUID | None  # None for an operator acting under a support grant
    # E-101 (05 SBX-07): a session may still be inside a tenant that is no longer ACTIVE
    status: TenantStatus = TenantStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session: SessionRow
    token: str
    user: UserRef
    active_tenant: ActiveTenant | None
    facts: RequestFacts

    @property
    def csrf_token(self) -> str:
        return csrf_token_for(self.token)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def new_token() -> str:
    return _b64url(secrets.token_bytes(32))


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_token_for(session_token: str) -> str:
    return _b64url(hmac.new(session_token.encode("ascii"), _CSRF_CONTEXT, hashlib.sha256).digest())


def normalise_email(email: str) -> str:
    return email.strip().lower()


def cookie_header(token: str, *, secure: bool) -> str:
    """``Set-Cookie`` of DG-KRN-AUTH-07: HttpOnly, SameSite=Lax, Path=/, no Domain."""
    header = f"{COOKIE_NAME}={token}; HttpOnly; Path=/; SameSite=Lax"
    return header + "; Secure" if secure else header


def cleared_cookie_header(*, secure: bool) -> str:
    return cookie_header("", secure=secure) + "; Max-Age=0"


def idle_timeout(tenant_ids: Iterable[UUID], *, known_at: datetime) -> timedelta:
    """``platform.session_idle_minutes`` (SAR-10): the shortest value among ``tenant_ids``, or the
    T-PLT-31 default when there is none.

    [J] SPEC-Q-178: a session with an active workspace takes that workspace's value; before a
    workspace is chosen, the shortest value of the user's ACTIVE memberships applies.
    """
    minutes: list[int] = []
    for tenant_id in tenant_ids:
        context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as db:
            minutes.append(int(setting(db, IDLE_MINUTES_KEY, known_at=known_at)))
    default = int(PLATFORM_PARAMETERS[IDLE_MINUTES_KEY].default_asc606)
    return timedelta(minutes=min(minutes, default=default))


def _idle_tenants(request_id: str, *, user_id: UUID, active_tenant_id: UUID | None) -> list[UUID]:
    """The tenants whose idle timeout governs a session: the active one, else every tenant of an
    ACTIVE membership (RLS-TM user policy)."""
    if active_tenant_id is not None:
        return [active_tenant_id]
    with identity_session(request_id=request_id, user_id=user_id) as db:
        found = db.scalars(
            select(tenant_membership.c.tenant_id)
            .where(
                tenant_membership.c.user_id == user_id,
                tenant_membership.c.status == MembershipStatus.ACTIVE.value,
            )
            .order_by(tenant_membership.c.tenant_id)
        )
        return [UUID(str(tenant_id)) for tenant_id in found]


_SESSION_COLUMNS: Final = (
    user_session.c.id,
    user_session.c.user_id,
    user_session.c.csrf_token_sha256,
    user_session.c.auth_method,
    user_session.c.mfa_verified_at,
    user_session.c.active_tenant_id,
    user_session.c.created_at,
    user_session.c.last_seen_at,
    user_session.c.idle_expires_at,
    user_session.c.absolute_expires_at,
    user_session.c.operator_support_grant_id,
)


def _session_row(values: RowMapping) -> SessionRow:
    return SessionRow(
        id=values["id"],
        user_id=values["user_id"],
        csrf_token_sha256=str(values["csrf_token_sha256"]),
        auth_method=IdentityProviderKind(values["auth_method"]),
        mfa_verified_at=values["mfa_verified_at"],
        active_tenant_id=values["active_tenant_id"],
        created_at=values["created_at"],
        last_seen_at=values["last_seen_at"],
        idle_expires_at=values["idle_expires_at"],
        absolute_expires_at=values["absolute_expires_at"],
        operator_support_grant_id=values["operator_support_grant_id"],
    )


def _find(db: Session, token: str) -> SessionRow | None:
    found = (
        db.execute(
            select(*_SESSION_COLUMNS).where(
                user_session.c.token_sha256 == sha256_hex(token), user_session.c.ended_at.is_(None)
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if found is None else _session_row(found)


def _open(
    db: Session,
    *,
    user_id: UUID,
    auth_method: IdentityProviderKind,
    facts: RequestFacts,
    mfa_verified_at: datetime | None = None,
    active_tenant_id: UUID | None = None,
    absolute_expires_at: datetime | None = None,
    operator_support_grant_id: UUID | None = None,
) -> tuple[SessionRow, str]:
    tenants = _idle_tenants(facts.request_id, user_id=user_id, active_tenant_id=active_tenant_id)
    token = new_token()
    row = SessionRow(
        id=new_id(),
        user_id=user_id,
        csrf_token_sha256=sha256_hex(csrf_token_for(token)),
        auth_method=auth_method,
        mfa_verified_at=mfa_verified_at,
        active_tenant_id=active_tenant_id,
        created_at=facts.now,
        last_seen_at=facts.now,
        idle_expires_at=facts.now + idle_timeout(tenants, known_at=facts.now),
        absolute_expires_at=absolute_expires_at or facts.now + ABSOLUTE_LIFETIME,
        operator_support_grant_id=operator_support_grant_id,
    )
    db.execute(
        insert(user_session).values(
            id=row.id,
            user_id=row.user_id,
            token_sha256=sha256_hex(token),
            csrf_token_sha256=row.csrf_token_sha256,
            auth_method=row.auth_method.value,
            mfa_verified_at=row.mfa_verified_at,
            active_tenant_id=row.active_tenant_id,
            operator_support_grant_id=row.operator_support_grant_id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            idle_expires_at=row.idle_expires_at,
            absolute_expires_at=row.absolute_expires_at,
            ip_address=facts.source_ip,
            user_agent=None
            if facts.user_agent is None
            else facts.user_agent[:USER_AGENT_MAX_CHARS],
        )
    )
    return row, token


def _end(db: Session, session_id: UUID, *, reason: SessionEndReason, now: datetime) -> bool:
    """End the session unless it has ended; whether this statement ended it."""
    ended = db.execute(
        update(user_session)
        .where(user_session.c.id == session_id, user_session.c.ended_at.is_(None))
        .values(ended_at=now, end_reason=reason.value, expires_at=now + RETENTION)
        .returning(user_session.c.id)
    ).first()
    return ended is not None


def _hold_identity(db: Session, user_id: UUID) -> None:
    """Take the identity's ``app_user`` row without its key, to the end of the transaction
    (dev-guide DG-KRN-AUTH-08): what a rotation and every act that ends an identity's sessions
    hold before they touch a session, so that the two run one after the other. Inserts that
    reference the identity go on."""
    db.execute(
        select(app_user.c.id).where(app_user.c.id == user_id).with_for_update(key_share=True)
    )


def _touch(db: Session, row: SessionRow, facts: RequestFacts) -> SessionRow:
    """Move ``last_seen_at`` and the idle expiry forward, at most once per minute."""
    now = facts.now
    if now - row.last_seen_at < TOUCH_INTERVAL:
        return row
    tenants = _idle_tenants(
        facts.request_id, user_id=row.user_id, active_tenant_id=row.active_tenant_id
    )
    idle_expires_at = now + idle_timeout(tenants, known_at=now)
    db.execute(
        update(user_session)
        .where(user_session.c.id == row.id)
        .values(last_seen_at=now, idle_expires_at=idle_expires_at)
    )
    return SessionRow(
        id=row.id,
        user_id=row.user_id,
        csrf_token_sha256=row.csrf_token_sha256,
        auth_method=row.auth_method,
        mfa_verified_at=row.mfa_verified_at,
        active_tenant_id=row.active_tenant_id,
        created_at=row.created_at,
        last_seen_at=now,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=row.absolute_expires_at,
        operator_support_grant_id=row.operator_support_grant_id,
    )


def _event(
    db: Session,
    keyring: KeyRing,
    facts: RequestFacts,
    kind: SecurityEventKind,
    outcome: AuditOutcome,
    *,
    user_id: UUID | None = None,
    email_sha256: str | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    detail: Mapping[str, Any] | None = None,
) -> None:
    record_security_event(
        db,
        keyring=keyring,
        kind=kind,
        outcome=outcome,
        request_id=facts.request_id,
        user_id=user_id,
        email_sha256=email_sha256,
        session_id=session_id,
        tenant_id=tenant_id,
        ip_address=facts.source_ip,
        user_agent=facts.user_agent,
        detail=detail,
    )


def _user_ref(values: RowMapping) -> UserRef:
    preferences = values["preferences"]
    return UserRef(
        id=values["id"],
        email=str(values["email"]),
        display_name=str(values["display_name"]),
        preferences=dict(preferences) if isinstance(preferences, Mapping) else {},
        is_operator=bool(values.get("is_operator", False)),
    )


# 05 SBX-07 rev 1.64: what a tenant that is not ACTIVE answers, to a selection and to a command.
WORKSPACE_NOT_ACTIVE: Final[Mapping[TenantStatus, str]] = MappingProxyType(
    {
        TenantStatus.ARCHIVED: "This workspace is archived. It cannot be opened or changed.",
        TenantStatus.SUSPENDED: "This workspace is not ready. Its copy has not completed.",
    }
)
# 04 §16.12 API-S-Me rev 1.125: the tenant facts of a membership beside id, code, name and kind.
MEMBERSHIP_TENANT_FACTS: Final = (
    tenant.c.status.label("tenant_status"),
    tenant.c.source_tenant_id,
    tenant.c.source_known_at,
)


def _workspace_query(user_id: UUID) -> Select[Any]:
    """The workspaces of the user's ACTIVE memberships (RLS-TN and the RLS-TM user policy)."""
    return (
        select(
            tenant.c.id,
            tenant.c.code,
            tenant.c.display_name,
            tenant.c.kind,
            tenant.c.default_locale,
            tenant.c.status.label("tenant_status"),
            tenant_membership.c.id.label("membership_id"),
        )
        .join(tenant_membership, tenant_membership.c.tenant_id == tenant.c.id)
        .where(
            tenant_membership.c.user_id == user_id,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
    )


def _workspace(found: RowMapping) -> ActiveTenant:
    return ActiveTenant(
        id=found["id"],
        code=str(found["code"]),
        display_name=str(found["display_name"]),
        kind=TenantKind(found["kind"]),
        default_locale=str(found["default_locale"]),
        membership_id=found["membership_id"],
        status=TenantStatus(found["tenant_status"]),
    )


def _active_tenant(facts: RequestFacts, *, user_id: UUID, tenant_id: UUID) -> ActiveTenant | None:
    """The tenant with the user's ACTIVE membership, through RLS-TN and the RLS-TM user policy."""
    with identity_session(request_id=facts.request_id, user_id=user_id) as db:
        found = (
            db.execute(_workspace_query(user_id).where(tenant.c.id == tenant_id))
            .mappings()
            .one_or_none()
        )
    return None if found is None else _workspace(found)


def _only_workspace(facts: RequestFacts, *, user_id: UUID) -> ActiveTenant | None:
    """The workspace a password sign-in opens (D-83): the user's only ACTIVE membership; None with
    none or several, so the session stays without a workspace.

    [J] L4-4-Q-1: T-PLT-07 has no default marker, so the "membership marked default" of D-83 has no
    representation and only the single-membership rule applies.
    """
    selectable = _workspace_query(user_id).where(tenant.c.status == TenantStatus.ACTIVE.value)
    with identity_session(request_id=facts.request_id, user_id=user_id) as db:
        found = db.execute(selectable.limit(2)).mappings().all()
    return _workspace(found[0]) if len(found) == 1 else None


def _mark_opened(facts: RequestFacts, *, user_id: UUID, opened: ActiveTenant) -> None:
    """Set the membership's ``last_opened_at`` (04 T-PLT-07; AUD-OPS) inside the workspace."""
    context = DbContext(tenant_id=opened.id, user_id=user_id, entity_scope=())
    with tenant_session(context) as db:
        db.execute(
            update(tenant_membership)
            .where(
                tenant_membership.c.tenant_id == opened.id,
                tenant_membership.c.id == opened.membership_id,
            )
            .values(
                last_opened_at=facts.now,
                updated_by=user_id,
                updated_by_kind=PrincipalKind.USER.value,
            )
        )


def memberships(auth: AuthenticatedSession) -> list[dict[str, Any]]:
    """The user's memberships not REMOVED, joined to the workspaces RLS-TN shows the user, by
    ``last_opened_at`` descending (NULLs last), then tenant code (04 API-S-Me).

    Without an active workspace RLS-TN shows only the ACTIVE ones (SPEC-Q-186); ``GET /me`` of a
    session without a workspace lists them (D-83).
    """
    with identity_session(request_id=auth.facts.request_id, user_id=auth.user.id) as db:
        rows = db.execute(
            select(
                tenant_membership.c.id.label("membership_id"),
                tenant_membership.c.status,
                tenant_membership.c.last_opened_at,
                tenant.c.id.label("tenant_id"),
                tenant.c.code,
                tenant.c.display_name,
                tenant.c.kind,
                tenant.c.is_demo,
                *MEMBERSHIP_TENANT_FACTS,
            )
            .join(tenant, tenant.c.id == tenant_membership.c.tenant_id)
            .where(
                tenant_membership.c.user_id == auth.user.id,
                tenant_membership.c.status != MembershipStatus.REMOVED.value,
            )
            .order_by(tenant_membership.c.last_opened_at.desc().nulls_last(), tenant.c.code)
        ).mappings()
        return [dict(row) for row in rows]


def _expired(row: SessionRow, reason: SessionEndReason) -> Problem:
    if reason is SessionEndReason.ABSOLUTE_TIMEOUT:
        return Problem("session-expired", ABSOLUTE_EXPIRED)
    # The idle period the session was granted at its last touch.
    minutes = int((row.idle_expires_at - row.last_seen_at).total_seconds()) // 60
    return Problem("session-expired", IDLE_EXPIRED.format(minutes=minutes))


def _csrf_valid(row: SessionRow, csrf: CsrfEvidence) -> bool:
    return (
        csrf.origin_allowed
        and csrf.token is not None
        and hmac.compare_digest(sha256_hex(csrf.token), row.csrf_token_sha256)
    )


def identity_providers(request_id: str) -> list[tuple[str, str]]:
    """``(code, display_name)`` of the enabled identity providers, ordered by code."""
    with identity_session(request_id=request_id) as db:
        rows = db.execute(
            select(identity_provider.c.code, identity_provider.c.display_name)
            .where(identity_provider.c.is_enabled.is_(True))
            .order_by(identity_provider.c.code)
        ).all()
    return [(str(code), str(name)) for code, name in rows]


def authenticate(
    token: str, *, facts: RequestFacts, keyring: KeyRing, csrf: CsrfEvidence | None
) -> AuthenticatedSession:
    """The valid session of a cookie; ``csrf`` is None for requests that change nothing.

    An expired session ends with its reason and writes ``SESSION_EXPIRED`` (401
    ``session-expired``); an unknown or ended token gives 401 ``unauthenticated``; a failed
    synchronizer or origin check gives 403 ``forbidden`` with ``rule_id`` ``API-C-02``.
    """
    refusal: Problem | None = None
    valid: tuple[SessionRow, UserRef] | None = None
    with identity_session(request_id=facts.request_id) as db:
        row = _find(db, token)
        user = (
            None
            if row is None
            else db.execute(
                select(
                    app_user.c.id,
                    app_user.c.email,
                    app_user.c.display_name,
                    app_user.c.preferences,
                    app_user.c.status,
                    app_user.c.is_operator,
                ).where(app_user.c.id == row.user_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None or user is None:
            refusal = Problem("unauthenticated", SIGN_IN_REQUIRED)
        elif (reason := row.expiry_reason(facts.now)) is not None:
            _end(db, row.id, reason=reason, now=facts.now)
            _event(
                db,
                keyring,
                facts,
                SecurityEventKind.SESSION_EXPIRED,
                AuditOutcome.SUCCESS,
                user_id=row.user_id,
                session_id=row.id,
                detail={"end_reason": reason.value},
            )
            refusal = _expired(row, reason)
        elif user["status"] != UserStatus.ACTIVE:
            _end(db, row.id, reason=SessionEndReason.REVOKED, now=facts.now)
            refusal = Problem("unauthenticated", SIGN_IN_REQUIRED)
        elif csrf is not None and not _csrf_valid(row, csrf):
            refusal = Problem(
                "forbidden",
                CSRF_REFUSED,
                errors=[ProblemError(field=CSRF_HEADER, rule_id="API-C-02", message=CSRF_REFUSED)],
            )
        else:
            valid = (_touch(db, row, facts), _user_ref(user))
    if refusal is not None:
        raise refusal
    assert valid is not None
    session_row, user_ref = valid
    active: ActiveTenant | None = None
    if session_row.active_tenant_id is not None and user_ref.is_operator:
        # SAR-29: an operator's workspace holds only while its support grant is in force.
        active = support_tenant(
            facts,
            user_id=user_ref.id,
            tenant_id=session_row.active_tenant_id,
            grant_id=session_row.operator_support_grant_id,
        )
        if active is None:
            with identity_session(request_id=facts.request_id, user_id=user_ref.id) as db:
                _end(db, session_row.id, reason=SessionEndReason.REVOKED, now=facts.now)
            raise Problem("unauthenticated", SIGN_IN_REQUIRED)
    elif session_row.active_tenant_id is not None:
        active = _active_tenant(facts, user_id=user_ref.id, tenant_id=session_row.active_tenant_id)
    return AuthenticatedSession(
        session=session_row, token=token, user=user_ref, active_tenant=active, facts=facts
    )


def _password_valid(user: RowMapping, password: str) -> bool:
    if user["status"] != UserStatus.ACTIVE or user["password_hash"] is None:
        return passwords.verify_dummy(password)
    return passwords.verify_password(str(user["password_hash"]), password)


def _record_failure(
    db: Session,
    user: RowMapping,
    facts: RequestFacts,
    keyring: KeyRing,
    *,
    purpose: str | None = None,
) -> Problem:
    """Count a consecutive failure; the fifth locks the account for 15 minutes (REQ-PLT-004)."""
    # A lock that has run out starts a new run of failures.
    previous = 0 if user["locked_until"] is not None else int(user["failed_login_count"])
    failures = previous + 1
    locked_until = facts.now + LOCKOUT if failures >= MAX_FAILED_LOGINS else None
    db.execute(
        update(app_user)
        .where(app_user.c.id == user["id"])
        .values(
            failed_login_count=failures,
            locked_until=locked_until,
            updated_by=user["id"],
            updated_by_kind=PrincipalKind.USER.value,
        )
    )
    _event(
        db,
        keyring,
        facts,
        SecurityEventKind.LOGIN_FAILED,
        AuditOutcome.FAILED,
        user_id=user["id"],
        detail={FAILED_LOGIN_COUNT: failures, **({"purpose": purpose} if purpose else {})},
    )
    if locked_until is None:
        return Problem("unauthenticated", WRONG_CREDENTIALS)
    _event(
        db,
        keyring,
        facts,
        SecurityEventKind.ACCOUNT_LOCKED,
        AuditOutcome.SUCCESS,
        user_id=user["id"],
        detail={"lockout_minutes": int(LOCKOUT.total_seconds()) // 60},
    )
    return Problem("account-locked", ACCOUNT_LOCKED)


def _unknown_email_state(db: Session, email_sha256: str) -> tuple[int, datetime | None]:
    """(consecutive failed sign-ins, end of the lockout) of an email without an account, read
    from its last counted event (04 T-PLT-06 ``email_sha256``): a ``LOGIN_FAILED`` that carries
    its count, or the ``ACCOUNT_LOCKED`` that ended a run of five."""
    last = db.execute(
        select(security_event.c.kind, security_event.c.detail)
        .where(
            security_event.c.email_sha256 == email_sha256,
            security_event.c.user_id.is_(None),
            (security_event.c.kind == SecurityEventKind.ACCOUNT_LOCKED.value)
            | (
                (security_event.c.kind == SecurityEventKind.LOGIN_FAILED.value)
                & security_event.c.detail.has_key(FAILED_LOGIN_COUNT)
            ),
        )
        .order_by(security_event.c.chain_seq.desc())
        .limit(1)
    ).one_or_none()
    if last is None:
        return 0, None
    if last.kind == SecurityEventKind.ACCOUNT_LOCKED.value:
        until = last.detail.get(LOCKED_UNTIL)
        return 0, None if until is None else datetime.fromisoformat(str(until))
    return int(last.detail[FAILED_LOGIN_COUNT]), None


def _refuse_unknown_email(
    db: Session, email_sha256: str, password: str, facts: RequestFacts, keyring: KeyRing
) -> Problem:
    """The refusal of a sign-in whose email matches no account, answer for answer what an account
    gets (03 REQ-PLT-004 rev 1.66; 05 SAR-06 rev 1.90; ruling R-48 (e)): one argon2 verification
    against the dummy hash and ``LOGIN_FAILED`` with the email's hash; the fifth consecutive
    failure also writes ``ACCOUNT_LOCKED`` and answers 423; while that lock lasts the answer is
    423 without a verification and without an event; afterwards a new run starts. The count
    lives in the security log, read and appended under the chain lock."""
    _, locked_until = _unknown_email_state(db, email_sha256)
    if locked_until is not None and locked_until > facts.now:
        return Problem("account-locked", ACCOUNT_LOCKED)
    passwords.verify_dummy(password)
    hold_chain_lock(db)
    # Read again under the lock: a concurrent attempt may have counted, or locked, meanwhile.
    previous, locked_until = _unknown_email_state(db, email_sha256)
    if locked_until is not None and locked_until > facts.now:
        return Problem("account-locked", ACCOUNT_LOCKED)
    failures = previous + 1
    _event(
        db,
        keyring,
        facts,
        SecurityEventKind.LOGIN_FAILED,
        AuditOutcome.FAILED,
        email_sha256=email_sha256,
        detail={FAILED_LOGIN_COUNT: failures},
    )
    if failures < MAX_FAILED_LOGINS:
        return Problem("unauthenticated", WRONG_CREDENTIALS)
    _event(
        db,
        keyring,
        facts,
        SecurityEventKind.ACCOUNT_LOCKED,
        AuditOutcome.SUCCESS,
        email_sha256=email_sha256,
        detail={
            "lockout_minutes": int(LOCKOUT.total_seconds()) // 60,
            LOCKED_UNTIL: (facts.now + LOCKOUT).isoformat(),
        },
    )
    return Problem("account-locked", ACCOUNT_LOCKED)


def sign_in(
    *,
    email: str,
    password: str,
    facts: RequestFacts,
    keyring: KeyRing,
    previous_token: str | None,
) -> AuthenticatedSession:
    """Password sign-in (SAR-06): a new session and ``LOGIN_SUCCEEDED``, or the refusal.

    An unknown email is refused as an account would be (``_refuse_unknown_email``): one argon2
    verification against the dummy hash, ``LOGIN_FAILED`` with ``email_sha256`` only, and the
    lockout of the fifth failure. A locked account is refused with 423 without verifying the
    password. A session presented with the request ends ``REVOKED`` (SAR-09).

    D-83: a user with exactly one ACTIVE membership gets that workspace in the new session, with
    ``TENANT_SELECTED`` and the membership's ``last_opened_at``; an MFA challenge keeps it. An
    operator opens a workspace only under a support grant (SAR-29), so its session opens none.
    """
    normalised = normalise_email(email)
    refusal: Problem | None = None
    issued: tuple[SessionRow, str, UserRef, ActiveTenant | None] | None = None
    with identity_session(request_id=facts.request_id) as db:
        user = (
            db.execute(
                select(
                    app_user.c.id,
                    app_user.c.email,
                    app_user.c.display_name,
                    app_user.c.preferences,
                    app_user.c.password_hash,
                    app_user.c.status,
                    app_user.c.failed_login_count,
                    app_user.c.locked_until,
                    app_user.c.is_operator,
                )
                .where(app_user.c.email == normalised)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one_or_none()
        )
        if user is None:
            refusal = _refuse_unknown_email(db, sha256_hex(normalised), password, facts, keyring)
        elif user["locked_until"] is not None and user["locked_until"] > facts.now:
            refusal = Problem("account-locked", ACCOUNT_LOCKED)
        elif not _password_valid(user, password):
            refusal = _record_failure(db, user, facts, keyring)
        else:
            values: dict[str, Any] = {
                "failed_login_count": 0,
                "locked_until": None,
                "last_login_at": facts.now,
                "updated_by": user["id"],
                "updated_by_kind": PrincipalKind.USER.value,
            }
            if passwords.needs_rehash(str(user["password_hash"])):
                values["password_hash"] = passwords.hash_password(password)
            db.execute(update(app_user).where(app_user.c.id == user["id"]).values(**values))
            previous = None if previous_token is None else _find(db, previous_token)
            if previous is not None:
                _end(db, previous.id, reason=SessionEndReason.REVOKED, now=facts.now)
            opened = None if user["is_operator"] else _only_workspace(facts, user_id=user["id"])
            row, token = _open(
                db,
                user_id=user["id"],
                auth_method=IdentityProviderKind.PASSWORD,
                facts=facts,
                active_tenant_id=None if opened is None else opened.id,
            )
            _event(
                db,
                keyring,
                facts,
                SecurityEventKind.LOGIN_SUCCEEDED,
                AuditOutcome.SUCCESS,
                user_id=user["id"],
                session_id=row.id,
            )
            if opened is not None:
                _event(
                    db,
                    keyring,
                    facts,
                    SecurityEventKind.TENANT_SELECTED,
                    AuditOutcome.SUCCESS,
                    user_id=user["id"],
                    session_id=row.id,
                    tenant_id=opened.id,
                )
            issued = (row, token, _user_ref(user), opened)
    if refusal is not None:
        raise refusal
    assert issued is not None
    row, token, user_ref, opened = issued
    if opened is not None:
        _mark_opened(facts, user_id=user_ref.id, opened=opened)
    return AuthenticatedSession(
        session=row, token=token, user=user_ref, active_tenant=opened, facts=facts
    )


def sign_in_external(
    *,
    email: str,
    subject: str,
    provider_id: UUID,
    provider_code: str,
    facts: RequestFacts,
    keyring: KeyRing,
    previous_token: str | None,
) -> AuthenticatedSession:
    """OIDC sign-in of the identity a provider vouches for (REQ-PLT-006; THR-05; ruling R-48
    (d)): a new session and ``LOGIN_SUCCEEDED`` for the existing ACTIVE user, or the refusal.

    The provider's verified email finds the identity; it never links one. The identity must have
    been invited for this provider (``app_user.identity_provider_id``, set by ``erev idp
    invite``). Its first sign-in records the provider's ``subject`` and writes ``OIDC_LINKED``;
    every later one must present that subject. Refused with 401 after ``LOGIN_FAILED`` commits,
    each with its reason: a provider that is not enabled, an unknown email, a user who is not
    ACTIVE, an identity that was not invited for the provider or belongs to another, a subject
    other than the linked one, and a subject another identity of the provider holds. A locked
    account gets 423. Memberships and role assignments never change, and no user is created.

    The provider's row is read here a second time (05 SAR-27 rev 1.178; item OPS-IDP-SESSIONS-1):
    the callback read it before it went to the provider, and the operator may have disabled the
    provider since. The read stands behind the identity's row lock, the lock
    ``end_provider_sessions`` takes before it ends a session - so a sign-in either commits before
    that command reaches the identity, and its session is ended by it, or reads the disabled
    provider and opens none.
    """
    normalised = normalise_email(email)
    detail = {"auth_method": IdentityProviderKind.OIDC.value, "provider": provider_code}
    refusal: Problem | None = None
    issued: tuple[SessionRow, str, UserRef] | None = None
    with identity_session(request_id=facts.request_id) as db:
        user = (
            db.execute(
                select(
                    app_user.c.id,
                    app_user.c.email,
                    app_user.c.display_name,
                    app_user.c.preferences,
                    app_user.c.status,
                    app_user.c.locked_until,
                    app_user.c.identity_provider_id,
                    app_user.c.identity_provider_subject,
                    app_user.c.is_operator,
                )
                .where(app_user.c.email == normalised)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one_or_none()
        )
        if not _provider_enabled(db, provider_id):
            reason: str | None = PROVIDER_DISABLED
        elif user is None:
            reason = "unknown_user"
        elif user["status"] != UserStatus.ACTIVE:
            reason = "user_not_active"
        elif user["identity_provider_id"] is None:
            # Never by email alone: the identity was not invited for this provider.
            reason = "not_invited_for_provider"
        elif user["identity_provider_id"] != provider_id:
            reason = "linked_to_another_provider"
        elif user["identity_provider_subject"] is None:
            reason = _subject_taken(db, provider_id, subject)
        elif user["identity_provider_subject"] != subject:
            reason = "subject_mismatch"
        else:
            reason = None
        if reason is not None:
            _event(
                db,
                keyring,
                facts,
                SecurityEventKind.LOGIN_FAILED,
                AuditOutcome.FAILED,
                user_id=None if user is None else user["id"],
                email_sha256=sha256_hex(normalised) if user is None else None,
                detail={**detail, "reason": reason},
            )
            refusal = Problem("unauthenticated", OIDC_REFUSED)
        elif (
            user is not None
            and user["locked_until"] is not None
            and user["locked_until"] > facts.now
        ):
            refusal = Problem("account-locked", ACCOUNT_LOCKED)
        elif user is not None:
            linking = user["identity_provider_subject"] is None
            values: dict[str, Any] = {
                "last_login_at": facts.now,
                "updated_by": user["id"],
                "updated_by_kind": PrincipalKind.USER.value,
            }
            if linking:
                values["identity_provider_subject"] = subject
            db.execute(update(app_user).where(app_user.c.id == user["id"]).values(**values))
            if linking:
                _event(
                    db,
                    keyring,
                    facts,
                    SecurityEventKind.OIDC_LINKED,
                    AuditOutcome.SUCCESS,
                    user_id=user["id"],
                    detail={"provider": provider_code},
                )
            previous = None if previous_token is None else _find(db, previous_token)
            if previous is not None:
                _end(db, previous.id, reason=SessionEndReason.REVOKED, now=facts.now)
            row, token = _open(
                db, user_id=user["id"], auth_method=IdentityProviderKind.OIDC, facts=facts
            )
            _event(
                db,
                keyring,
                facts,
                SecurityEventKind.LOGIN_SUCCEEDED,
                AuditOutcome.SUCCESS,
                user_id=user["id"],
                session_id=row.id,
                detail=detail,
            )
            issued = (row, token, _user_ref(user))
    if refusal is not None:
        raise refusal
    assert issued is not None
    row, token, user_ref = issued
    return AuthenticatedSession(
        session=row, token=token, user=user_ref, active_tenant=None, facts=facts
    )


def _provider_enabled(db: Session, provider_id: UUID) -> bool:
    """Whether the provider is a way to sign in at this statement, in the caller's transaction."""
    enabled = db.execute(
        select(identity_provider.c.is_enabled).where(identity_provider.c.id == provider_id)
    ).scalar_one_or_none()
    return enabled is True


def _subject_taken(db: Session, provider_id: UUID, subject: str) -> str | None:
    """The refusal reason when another identity of the provider already holds ``subject``; a
    subject names one identity (``ux_app_user__idp_subject``)."""
    taken = db.execute(
        select(app_user.c.id)
        .where(
            app_user.c.identity_provider_id == provider_id,
            app_user.c.identity_provider_subject == subject,
        )
        .limit(1)
    ).first()
    return None if taken is None else "subject_linked_to_another_identity"


def check_password(
    user_id: UUID, password: str, *, facts: RequestFacts, keyring: KeyRing
) -> Problem | None:
    """Verify an existing user's password with the sign-in lockout (REQ-PLT-004).

    None when it matches, which resets the failure count. Otherwise the refusal, returned after
    its evidence commits: 423 ``account-locked`` during a lock, else the sign-in failure of
    ``_record_failure``, which counts towards the lockout.
    """
    refusal: Problem | None = None
    with identity_session(request_id=facts.request_id) as db:
        user = (
            db.execute(
                select(
                    app_user.c.id,
                    app_user.c.password_hash,
                    app_user.c.status,
                    app_user.c.failed_login_count,
                    app_user.c.locked_until,
                )
                .where(app_user.c.id == user_id)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one()
        )
        refusal = check_locked_password(db, user, password, facts=facts, keyring=keyring)
    return refusal


def check_locked_password(
    db: Session,
    user: RowMapping,
    password: str,
    *,
    facts: RequestFacts,
    keyring: KeyRing,
    purpose: str | None = None,
) -> Problem | None:
    """Verify under the caller's identity-row write lock; return a refusal without raising.

    The caller must commit failure evidence before raising the returned problem. Holding the
    lock through a successful password mutation prevents another check/reset interleaving.
    """
    if user["locked_until"] is not None and user["locked_until"] > facts.now:
        return Problem("account-locked", ACCOUNT_LOCKED)
    if not _password_valid(user, password):
        return _record_failure(db, user, facts, keyring, purpose=purpose)
    db.execute(
        update(app_user)
        .where(app_user.c.id == user["id"])
        .values(
            failed_login_count=0,
            locked_until=None,
            updated_by=user["id"],
            updated_by_kind=PrincipalKind.USER.value,
        )
    )
    return None


def hold_password(db: Session, user_id: UUID, password: str) -> bool:
    """Take the identity's row as ``_hold_identity`` does, in the caller's transaction, and answer
    whether ``password`` is the identity's at that instant (dev-guide DG-KRN-AUTH-08 rev 1.267;
    item INVITE-ACCEPT-SESSION-1): the second look of a transaction that opens a session on a
    password which ``check_password`` verified in a transaction before it.

    A password change, a reset and every other act that ends the identity's sessions take the
    same row, so each ran wholly before this read or waits for the caller's commit. The password
    is verified, not compared with the hash the check saw: a sign-in rewrites the hash of an
    unchanged password when its parameters are out of date. Nothing is counted here; the
    verification that counts towards the lockout is ``check_password``'s. An identity that is not
    ACTIVE or has no password answers False."""
    user = (
        db.execute(
            select(app_user.c.id, app_user.c.password_hash, app_user.c.status)
            .where(app_user.c.id == user_id)
            .with_for_update(key_share=True)
        )
        .mappings()
        .one_or_none()
    )
    return user is not None and _password_valid(user, password)


def end_user_sessions(
    db: Session,
    user_id: UUID,
    *,
    reason: SessionEndReason,
    now: datetime,
    keep_session_id: UUID | None = None,
) -> None:
    """End every open session of ``user_id`` except ``keep_session_id`` (SAR-10; E-104). The
    identity's row is taken first: a rotation of one of the sessions holds it, so its successor
    is either committed and ended here or never opened (``reissue``)."""
    _hold_identity(db, user_id)
    statement = update(user_session).where(
        user_session.c.user_id == user_id, user_session.c.ended_at.is_(None)
    )
    if keep_session_id is not None:
        statement = statement.where(user_session.c.id != keep_session_id)
    db.execute(statement.values(ended_at=now, end_reason=reason.value, expires_at=now + RETENTION))


def end_provider_sessions(db: Session, provider_id: UUID, *, now: datetime) -> tuple[int, int]:
    """End every open session that was opened through the provider with ``REVOKED``: the open
    ``oidc`` rows of the identities bound to it (04 T-PLT-08 rev 1.249; 05 SAR-27 rev 1.178). A
    session names its method and no provider; an identity has one provider for good (DB-20), so
    its ``oidc`` sessions are that provider's. Sessions the identities opened with a password
    stay.

    The identities' rows are locked first, in id order and without their keys (inserts that
    reference an identity go on) - the row ``sign_in_external`` holds while it opens a session,
    and ``reissue`` while it opens a successor. Returns how many identities had such a session,
    and how many sessions ended."""
    identities = select(app_user.c.id).where(app_user.c.identity_provider_id == provider_id)
    db.execute(identities.order_by(app_user.c.id).with_for_update(key_share=True))
    ended = (
        db.execute(
            update(user_session)
            .where(
                user_session.c.user_id.in_(identities),
                user_session.c.auth_method == IdentityProviderKind.OIDC.value,
                user_session.c.ended_at.is_(None),
            )
            .values(
                ended_at=now,
                end_reason=SessionEndReason.REVOKED.value,
                expires_at=now + RETENTION,
            )
            .returning(user_session.c.user_id)
        )
        .scalars()
        .all()
    )
    return len(set(ended)), len(ended)


def end_support_grant_sessions(db: Session, grant_id: UUID, *, now: datetime) -> None:
    """End every open operator session under a support grant with ``REVOKED`` (05 SCH-15)."""
    db.execute(
        update(user_session)
        .where(
            user_session.c.operator_support_grant_id == grant_id,
            user_session.c.ended_at.is_(None),
        )
        .values(ended_at=now, end_reason=SessionEndReason.REVOKED.value, expires_at=now + RETENTION)
    )


def _grants_in_force(user_id: UUID, now: datetime) -> Select[Any]:
    """The APPROVED support grants of operator ``user_id`` whose validity holds ``now``."""
    return select(support_grant.c.id).where(
        support_grant.c.operator_user_id == user_id,
        support_grant.c.status == GrantStatus.APPROVED.value,
        support_grant.c.valid_from <= now,
        support_grant.c.valid_to > now,
    )


def support_grant_in_force(facts: RequestFacts, *, user_id: UUID, tenant_id: UUID) -> UUID | None:
    """The support grant of operator ``user_id`` in force in ``tenant_id`` that ends last; None
    without one (REQ-PLT-036)."""
    context = DbContext(tenant_id=tenant_id, user_id=user_id, entity_scope=())
    statement = (
        _grants_in_force(user_id, facts.now)
        .order_by(support_grant.c.valid_to.desc(), support_grant.c.id)
        .limit(1)
    )
    with tenant_session(context, read_only=True) as db:
        found = db.execute(statement).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def support_tenant(
    facts: RequestFacts, *, user_id: UUID, tenant_id: UUID, grant_id: UUID | None
) -> ActiveTenant | None:
    """The workspace an operator session acts in while ``grant_id`` is in force; None otherwise."""
    if grant_id is None:
        return None
    in_force = _grants_in_force(user_id, facts.now).where(support_grant.c.id == grant_id).exists()
    context = DbContext(tenant_id=tenant_id, user_id=user_id, entity_scope=())
    with tenant_session(context, read_only=True) as db:
        found = (
            db.execute(
                select(
                    tenant.c.id,
                    tenant.c.code,
                    tenant.c.display_name,
                    tenant.c.kind,
                    tenant.c.default_locale,
                    tenant.c.status,
                ).where(tenant.c.id == tenant_id, in_force)
            )
            .mappings()
            .one_or_none()
        )
    if found is None:
        return None
    return ActiveTenant(
        id=found["id"],
        code=str(found["code"]),
        display_name=str(found["display_name"]),
        kind=TenantKind(found["kind"]),
        default_locale=str(found["default_locale"]),
        membership_id=None,
        status=TenantStatus(found["status"]),
    )


def open_workspace_session(
    db: Session,
    *,
    user_id: UUID,
    tenant_id: UUID,
    facts: RequestFacts,
    keyring: KeyRing,
    previous_token: str | None,
) -> tuple[SessionRow, str]:
    """A password session with ``tenant_id`` active and its ``TENANT_SELECTED`` event, in the
    caller's transaction (04 T-PLT-07 invitation acceptance). A session presented with the request
    ends ``REVOKED`` (SAR-09)."""
    previous = None if previous_token is None else _find(db, previous_token)
    if previous is not None:
        _end(db, previous.id, reason=SessionEndReason.REVOKED, now=facts.now)
    row, token = _open(
        db,
        user_id=user_id,
        auth_method=IdentityProviderKind.PASSWORD,
        facts=facts,
        active_tenant_id=tenant_id,
    )
    _event(
        db,
        keyring,
        facts,
        SecurityEventKind.TENANT_SELECTED,
        AuditOutcome.SUCCESS,
        user_id=user_id,
        session_id=row.id,
        tenant_id=tenant_id,
    )
    return row, token


def reissue(
    db: Session,
    auth: AuthenticatedSession,
    *,
    active_tenant_id: UUID | None,
    mfa_verified_at: datetime | None,
    operator_support_grant_id: UUID | None = None,
) -> tuple[SessionRow, str]:
    """End the presented session ``REVOKED`` and open its successor with a new token (SAR-09).

    The successor keeps the authentication method and the absolute expiry, so a rotation never
    extends the 12-hour limit (SPEC-Q-126). A rotation in the same workspace keeps the session's
    support grant unless another one is named.

    A rotation is the one way a session comes by a successor, so it carries no session past an
    act that ends sessions (item SESSION-ROTATION-END-1; 05 SAR-09 rev 1.178). The request was
    authenticated in an earlier transaction: the identity's row is taken first, and the
    successor is opened only when this transaction ended the presented session - one that has
    ended since answers 401 ``unauthenticated`` and nothing is written.
    """
    grant_id = operator_support_grant_id
    if grant_id is None and active_tenant_id == auth.session.active_tenant_id:
        grant_id = auth.session.operator_support_grant_id
    _hold_identity(db, auth.user.id)
    if not _end(db, auth.session.id, reason=SessionEndReason.REVOKED, now=auth.facts.now):
        raise Problem("unauthenticated", SIGN_IN_REQUIRED)
    return _open(
        db,
        user_id=auth.user.id,
        auth_method=auth.session.auth_method,
        facts=auth.facts,
        mfa_verified_at=mfa_verified_at,
        active_tenant_id=active_tenant_id,
        absolute_expires_at=auth.session.absolute_expires_at,
        operator_support_grant_id=None if active_tenant_id is None else grant_id,
    )


def sign_out(auth: AuthenticatedSession, *, keyring: KeyRing) -> None:
    """End the session server-side with ``LOGOUT`` (REQ-PLT-004)."""
    with identity_session(request_id=auth.facts.request_id, user_id=auth.user.id) as db:
        _end(db, auth.session.id, reason=SessionEndReason.LOGOUT, now=auth.facts.now)
        _event(
            db,
            keyring,
            auth.facts,
            SecurityEventKind.LOGOUT,
            AuditOutcome.SUCCESS,
            user_id=auth.user.id,
            session_id=auth.session.id,
        )


def select_tenant(
    auth: AuthenticatedSession, tenant_id: UUID, *, keyring: KeyRing
) -> AuthenticatedSession:
    """Open the workspace of an ACTIVE membership in a new session (SAR-09; 04 T-PLT-07).

    The membership's ``last_opened_at`` is set, the previous session ends ``REVOKED`` and the new
    one keeps its authentication method, MFA verification and absolute expiry (SPEC-Q-126).
    Without an ACTIVE membership the tenant is 404 ``not-found``.
    """
    facts = auth.facts
    selected = _active_tenant(facts, user_id=auth.user.id, tenant_id=tenant_id)
    if selected is None:
        raise Problem("not-found")
    if selected.status is not TenantStatus.ACTIVE:
        # 05 SBX-07: an archived sandbox, or one whose load has not completed, is not opened
        raise Problem("invalid-transition", WORKSPACE_NOT_ACTIVE[selected.status])
    _mark_opened(facts, user_id=auth.user.id, opened=selected)
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        row, token = reissue(
            db,
            auth,
            active_tenant_id=selected.id,
            mfa_verified_at=auth.session.mfa_verified_at,
        )
        _event(
            db,
            keyring,
            facts,
            SecurityEventKind.TENANT_SELECTED,
            AuditOutcome.SUCCESS,
            user_id=auth.user.id,
            session_id=row.id,
            tenant_id=selected.id,
        )
    return AuthenticatedSession(
        session=row, token=token, user=auth.user, active_tenant=selected, facts=facts
    )


def move_sessions(
    *,
    user_id: UUID,
    from_tenant_id: UUID,
    to_tenant_id: UUID,
    facts: RequestFacts,
    keyring: KeyRing,
) -> int:
    """05 SBX-07 (rev 1.64): the live sessions of ``user_id`` whose active tenant is
    ``from_tenant_id`` continue in ``to_tenant_id`` — the server's own step when a reset
    supersedes a sandbox; returns how many moved.

    Nothing moves unless the user holds an ACTIVE membership of an ACTIVE target, the rule of
    ``select_tenant``. Each moved session records ``TENANT_SELECTED`` for the target, naming the
    tenant it left, and the membership's ``last_opened_at`` is set. The token is NOT rotated: this
    is the one tenant change SAR-09's rotation cannot cover, because no request of the user is in
    flight to carry a new cookie. The user, the authentication method, the MFA verification and
    both expiries are unchanged; a session under a support grant is never moved.
    """
    target = _active_tenant(facts, user_id=user_id, tenant_id=to_tenant_id)
    if target is None or target.status is not TenantStatus.ACTIVE:
        return 0
    with identity_session(request_id=facts.request_id, user_id=user_id) as db:
        moved = [
            UUID(str(session_id))
            for session_id in db.scalars(
                update(user_session)
                .where(
                    user_session.c.user_id == user_id,
                    user_session.c.active_tenant_id == from_tenant_id,
                    user_session.c.ended_at.is_(None),
                    user_session.c.operator_support_grant_id.is_(None),
                )
                .values(active_tenant_id=to_tenant_id)
                .returning(user_session.c.id)
            )
        ]
        for session_id in moved:
            _event(
                db,
                keyring,
                facts,
                SecurityEventKind.TENANT_SELECTED,
                AuditOutcome.SUCCESS,
                user_id=user_id,
                session_id=session_id,
                tenant_id=to_tenant_id,
                detail={"moved_from_tenant_id": str(from_tenant_id), "reason": "SANDBOX_RESET"},
            )
    if moved:
        _mark_opened(facts, user_id=user_id, opened=target)
    return len(moved)
