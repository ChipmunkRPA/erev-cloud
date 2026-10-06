"""Invitation lookup and acceptance credentials KRN-AUTH (04 T-PLT-07 invitation acceptance,
§16.12; 05 SAR-06; PRD BR-PLT-01, ERR-21; BUILD_SPEC PLF-15).

``find_invitation`` resolves a token through ``app.platform_scope = 'tenant_directory'``. RLS-TM
gives that scope no membership policy, so the read-only directory transaction visits each tenant
under its own context until the token hash matches (SPEC-Q-180). An unknown, expired or already
accepted token, or a user who is not ACTIVE, is 404 ``not-found``. ``check_acceptance_password``
applies the password policy for a user without a password and verifies an existing user's password
with the sign-in lockout; ``set_initial_password`` stores the new password in the acceptance
transaction. A refused token (malformed, unknown, expired, used, or an inactive user) writes
``security_event`` ``INVITATION_LOOKUP_FAILED`` in its own identity transaction after the read-only
directory read, naming the reason and the route (04 T-PLT-07 rev 1.38, E-79; D-98 candidate 20).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.auth import passwords, sessions
from erev_api.auth.keyring import KeyRing
from erev_api.auth.security_events import record_security_event
from erev_api.auth.sessions import RequestFacts
from erev_api.db.session import (
    DbContext,
    identity_session,
    of_session_tenant,
    platform_session,
    set_tenant_context,
)
from erev_api.db.tables.platform import app_user, tenant, tenant_membership
from erev_api.enums import (
    AuditOutcome,
    MembershipStatus,
    PrincipalKind,
    SecurityEventKind,
    TenantKind,
    UserStatus,
)
from erev_api.problems import Problem, ProblemError

PASSWORD_FIELD: Final = "password"
# T-PLT-07: the 256-bit token of ``secrets.token_urlsafe(32)`` is 43 URL-safe characters.
TOKEN_PATTERN: Final = re.compile(r"[A-Za-z0-9_-]{43}")
FailureReason = Literal["malformed", "unknown", "expired", "used", "inactive"]
FAILURE_REASONS: Final[tuple[FailureReason, ...]] = (
    "malformed",
    "unknown",
    "expired",
    "used",
    "inactive",
)
LookupRoute = Literal["lookup", "accept"]
# [J] SPEC-Q-180: SCREENS_B §12.3 states no copy for these two refusals.
WRONG_PASSWORD: Final = "The password is incorrect."
PROVIDER_ONLY: Final = "Sign in with your identity provider to accept this invitation."


@dataclass(frozen=True, slots=True)
class Invitation:
    tenant_id: UUID
    tenant_kind: TenantKind
    workspace_display_name: str
    default_locale: str
    membership_id: UUID
    token_sha256: str
    expires_at: datetime
    inviter_display_name: str | None
    user_id: UUID
    email: str
    display_name: str
    format_locale: str | None
    has_password: bool
    has_identity_provider: bool


def well_formed_token(token: str) -> bool:
    """True for the 43 URL-safe characters of an invitation token (T-PLT-07)."""
    return TOKEN_PATTERN.fullmatch(token) is not None


def failure_reason(
    *,
    membership_status: MembershipStatus | str,
    expires_at: datetime | None,
    user_status: UserStatus | str | None,
    now: datetime,
) -> FailureReason | None:
    """Why a membership carrying the token hash admits no invitation, else None.

    A membership that is no longer ``INVITED`` is ``used`` even when its token has also expired;
    an ``INVITED`` one at or past ``invitation_expires_at`` is ``expired``; an ``INVITED``,
    unexpired one whose user is not ``ACTIVE`` is ``inactive``. ``user_status`` is None before the
    user row is read.
    """
    if MembershipStatus(membership_status) != MembershipStatus.INVITED:
        return "used"
    if expires_at is None or expires_at <= now:
        return "expired"
    if user_status is not None and UserStatus(user_status) != UserStatus.ACTIVE:
        return "inactive"
    return None


class InvitationRefused(Problem):
    """404 ``not-found`` for a token that admits no invitation, naming why (E-79 ``detail``)."""

    def __init__(self, reason: FailureReason) -> None:
        if reason not in FAILURE_REASONS:
            raise ValueError(f"unknown invitation failure reason {reason!r}")
        super().__init__("not-found")
        self.reason: FailureReason = reason


def failure_event_fields(reason: FailureReason, *, route: LookupRoute) -> dict[str, Any]:
    """The ``INVITATION_LOOKUP_FAILED`` fields: anonymous, naming the reason and the route."""
    return {
        "kind": SecurityEventKind.INVITATION_LOOKUP_FAILED,
        "outcome": AuditOutcome.FAILED,
        "user_id": None,
        "detail": {"reason": reason, "route": route},
    }


def record_lookup_failure(
    reason: FailureReason, *, route: LookupRoute, facts: RequestFacts, keyring: KeyRing
) -> None:
    """Write the failure event in its own identity transaction; the directory read is read-only
    (DG-KRN-DB-03), so it cannot carry the write."""
    with identity_session(request_id=facts.request_id) as db:
        record_security_event(
            db,
            keyring=keyring,
            request_id=facts.request_id,
            ip_address=facts.source_ip,
            user_agent=facts.user_agent,
            **failure_event_fields(reason, route=route),
        )


def _refuse(
    reason: FailureReason, *, route: LookupRoute, facts: RequestFacts, keyring: KeyRing
) -> InvitationRefused:
    record_lookup_failure(reason, route=route, facts=facts, keyring=keyring)
    return InvitationRefused(reason)


def find_invitation(
    token: str, *, facts: RequestFacts, keyring: KeyRing, route: LookupRoute
) -> Invitation:
    """The open invitation of ``token``, or 404 ``not-found`` (04 §16.12). A refusal first writes
    ``security_event`` ``INVITATION_LOOKUP_FAILED`` with its reason and ``route`` (T-PLT-07 rev
    1.38)."""
    if not well_formed_token(token):
        raise _refuse("malformed", route=route, facts=facts, keyring=keyring)
    digest = sessions.sha256_hex(token)
    found: Invitation | None = None
    reason: FailureReason = "unknown"
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=facts.request_id
    ) as db:
        tenants = db.execute(
            select(
                tenant.c.id, tenant.c.kind, tenant.c.display_name, tenant.c.default_locale
            ).order_by(tenant.c.id)
        ).all()
        for tenant_id, kind, workspace_name, default_locale in tenants:
            set_tenant_context(db, DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*"))
            membership = (
                db.execute(
                    select(
                        tenant_membership.c.id,
                        tenant_membership.c.user_id,
                        tenant_membership.c.status,
                        tenant_membership.c.invitation_expires_at,
                        tenant_membership.c.created_by,
                        tenant_membership.c.created_by_kind,
                    ).where(
                        of_session_tenant(tenant_membership),
                        tenant_membership.c.invitation_token_sha256 == digest,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if membership is None:
                continue
            expires_at = membership["invitation_expires_at"]
            refused = failure_reason(
                membership_status=membership["status"],
                expires_at=expires_at,
                user_status=None,
                now=facts.now,
            )
            if refused is not None:
                reason = refused
                break
            user = (
                db.execute(
                    select(
                        app_user.c.email,
                        app_user.c.display_name,
                        app_user.c.password_hash,
                        app_user.c.identity_provider_id,
                        app_user.c.status,
                        app_user.c.preferences,
                    ).where(app_user.c.id == membership["user_id"])
                )
                .mappings()
                .one()
            )
            if user["status"] != UserStatus.ACTIVE:
                reason = "inactive"
                break
            inviter: str | None = None
            if membership["created_by_kind"] == PrincipalKind.USER:
                inviter = db.execute(
                    select(app_user.c.display_name).where(app_user.c.id == membership["created_by"])
                ).scalar_one_or_none()
            preferences = user["preferences"]
            locale = preferences.get("format_locale") if isinstance(preferences, dict) else None
            found = Invitation(
                tenant_id=tenant_id,
                tenant_kind=TenantKind(kind),
                workspace_display_name=str(workspace_name),
                default_locale=str(default_locale),
                membership_id=membership["id"],
                token_sha256=digest,
                expires_at=expires_at,
                inviter_display_name=inviter,
                user_id=membership["user_id"],
                email=str(user["email"]),
                display_name=str(user["display_name"]),
                format_locale=locale if isinstance(locale, str) else None,
                has_password=user["password_hash"] is not None,
                has_identity_provider=user["identity_provider_id"] is not None,
            )
            break
    if found is None:
        raise _refuse(reason, route=route, facts=facts, keyring=keyring)
    return found


def check_acceptance_password(
    invitation: Invitation, password: str, *, facts: RequestFacts, keyring: KeyRing
) -> None:
    """Refuse the acceptance password before anything changes.

    A user without a password gets the policy (422 ``password-policy``). An existing user's
    password is verified with the sign-in lockout: a wrong one is 422 ``validation-failed`` on
    ``password``, a lock 423 ``account-locked``. A user linked to an identity provider without a
    password is refused (XR-12), because this route cannot authenticate through the provider.
    """
    if invitation.has_password:
        refusal = sessions.check_password(
            invitation.user_id, password, facts=facts, keyring=keyring
        )
        if refusal is None:
            return
        if refusal.status == 423:
            raise refusal
        raise Problem(
            "validation-failed",
            WRONG_PASSWORD,
            errors=[ProblemError(field=PASSWORD_FIELD, message=WRONG_PASSWORD)],
        )
    if invitation.has_identity_provider:
        raise Problem(
            "validation-failed",
            PROVIDER_ONLY,
            errors=[ProblemError(field=PASSWORD_FIELD, message=PROVIDER_ONLY)],
        )
    passwords.check_policy(password, email=invitation.email, field=PASSWORD_FIELD)


def set_initial_password(
    db: Session, invitation: Invitation, password: str, *, now: datetime
) -> None:
    """Store the first password of the invited user in the caller's transaction; a password set
    in the meantime makes the acceptance 404 ``not-found``."""
    stored = db.execute(
        update(app_user)
        .where(app_user.c.id == invitation.user_id, app_user.c.password_hash.is_(None))
        .values(
            password_hash=passwords.hash_password(password),
            password_changed_at=now,
            updated_by=invitation.user_id,
            updated_by_kind=PrincipalKind.USER.value,
        )
        .returning(app_user.c.id)
    ).scalar_one_or_none()
    if stored is None:
        raise Problem("not-found")


def claim_identity(db: Session, invitation: Invitation, password: str, *, now: datetime) -> None:
    """The identity's row in the acceptance's transaction, taken after the membership's
    (dev-guide DG-KRN-AUTH-08 rev 1.267; 05 SAR-09 rev 1.201; item INVITE-ACCEPT-SESSION-1).

    A user without a password gets the first one (``set_initial_password``). An existing user's
    password was verified by ``check_acceptance_password`` in a transaction of its own, which has
    to commit whatever follows: it counts a wrong password and sets the lockout. That transaction
    is over when this one opens the session, so the password is looked at a second time here,
    under the identity's row (``sessions.hold_password``): a password changed or reset in between,
    or an identity that is no longer active, is 404 ``not-found``, as a first password set in the
    meantime is. A change or a reset takes the same row before it ends the identity's sessions,
    so it ran wholly before this look or runs after this transaction's commit and ends the
    session opened here with the others.
    """
    if not invitation.has_password:
        set_initial_password(db, invitation, password, now=now)
    elif not sessions.hold_password(db, invitation.user_id, password):
        raise Problem("not-found")
