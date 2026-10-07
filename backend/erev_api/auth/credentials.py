"""Password change and password reset KRN-AUTH (04 T-PLT-42 rules 1 to 3, §16.12; 05 SAR-06,
SAR-10; 03 REQ-PLT-004; SCREENS_B §12.3; BUILD_SPEC PLF-15).

``change_password`` verifies the current password, applies the policy, ends the user's other
sessions and rotates the presented session token. ``request_reset`` always answers the same way:
an excess request per client address or per user writes ``PASSWORD_RESET_REQUESTED`` with outcome
``DENIED`` and sends nothing; a matching
ACTIVE user with a password gets a 60-minute token, the earlier open tokens are superseded, and the
link email waits in the outbox of the workspace the user opened last. The token travels only in
the email link fragment; the row keeps its SHA-256. ``confirm_reset`` spends a token once, sets the
password, clears the lockout and ends every session of the user.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, case, func, insert, or_, select, update
from sqlalchemy.orm import Session

from erev_api.auth import passwords, sessions
from erev_api.auth.keyring import KeyRing
from erev_api.auth.ratelimit import PasswordResetRateLimiter
from erev_api.auth.security_events import record_security_event
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, set_tenant_context
from erev_api.db.tables.platform import app_user, password_reset_token, tenant, tenant_membership
from erev_api.enums import (
    AuditOutcome,
    MembershipStatus,
    OutboxTopic,
    PrincipalKind,
    SecurityEventKind,
    SessionEndReason,
    UserStatus,
)
from erev_api.events import outbox
from erev_api.problems import Problem, ProblemError

RESET_LIFETIME: Final = timedelta(minutes=60)  # T-PLT-42 token_expires_at
RESET_RETENTION: Final = timedelta(days=30)  # T-PLT-42 expires_at
RESET_TOKENS_PER_USER: Final = 5  # T-PLT-42 rule 2
RESET_WINDOW: Final = timedelta(hours=1)
# SCREENS_B §12.3: the token travels in the fragment, never in a query parameter.
# The link of the reset email; the place is filled when the email is sent (05 NTR-04).
RESET_LINK: Final = "/password/reset/confirm#token={token}"
# ``KeyRing.link_token`` purpose of a reset link; its reference is the T-PLT-42 row id.
RESET_PURPOSE: Final = "password-reset"
RESET_AGGREGATE: Final = "password_reset_token"
# SCREENS_B §12.3 "Wrong current password".
WRONG_CURRENT_PASSWORD: Final = "The current password is incorrect."
CURRENT_PASSWORD_FIELD: Final = "current_password"
NEW_PASSWORD_FIELD: Final = "new_password"


def _record(
    db: Session,
    keyring: KeyRing,
    facts: RequestFacts,
    kind: SecurityEventKind,
    outcome: AuditOutcome,
    **fields: Any,
) -> None:
    record_security_event(
        db,
        keyring=keyring,
        kind=kind,
        outcome=outcome,
        request_id=facts.request_id,
        ip_address=facts.source_ip,
        user_agent=facts.user_agent,
        **fields,
    )


def _new_password_values(password: str, *, user_id: UUID, now: datetime) -> dict[str, Any]:
    return {
        "password_hash": passwords.hash_password(password),
        "password_changed_at": now,
        "updated_by": user_id,
        "updated_by_kind": PrincipalKind.USER.value,
    }


def change_password(
    auth: AuthenticatedSession, *, current_password: str, new_password: str, keyring: KeyRing
) -> AuthenticatedSession:
    """``POST /me/password``: a wrong current password is 422 ``validation-failed`` on
    ``current_password`` until the shared fifth failure or an active lock answers 423.
    Failure evidence commits before refusal. A weak new password is 422 ``password-policy``.
    Success ends the other sessions
    with ``PASSWORD_CHANGED`` and keeps the user signed in under a rotated token: the presented
    session ends ``REVOKED`` and its successor is returned (04 §16.12; 05 SAR-09; D-80). The
    user's open password-reset tokens are superseded: a link issued before the change stops
    working (04 T-PLT-42 rule 4, rev 1.151)."""
    facts = auth.facts
    refusal: Problem | None = None
    with identity_session(request_id=facts.request_id, user_id=auth.user.id) as db:
        user = (
            db.execute(
                select(
                    app_user.c.id,
                    app_user.c.email,
                    app_user.c.password_hash,
                    app_user.c.status,
                    app_user.c.failed_login_count,
                    app_user.c.locked_until,
                )
                .where(app_user.c.id == auth.user.id)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one()
        )
        refusal = sessions.check_locked_password(
            db, user, current_password, facts=facts, keyring=keyring, purpose="password_change"
        )
        if refusal is not None and refusal.spec.slug == "unauthenticated":
            refusal = Problem(
                "validation-failed",
                WRONG_CURRENT_PASSWORD,
                errors=[ProblemError(field=CURRENT_PASSWORD_FIELD, message=WRONG_CURRENT_PASSWORD)],
            )
        if refusal is None:
            try:
                passwords.check_policy(
                    new_password, email=str(user["email"]), field=NEW_PASSWORD_FIELD
                )
            except Problem as exc:
                refusal = exc
        if refusal is None:
            db.execute(
                update(app_user)
                .where(app_user.c.id == auth.user.id)
                .values(**_new_password_values(new_password, user_id=auth.user.id, now=facts.now))
            )
            db.execute(
                update(password_reset_token)
                .where(
                    password_reset_token.c.user_id == auth.user.id,
                    password_reset_token.c.used_at.is_(None),
                    password_reset_token.c.superseded_at.is_(None),
                )
                .values(superseded_at=facts.now)
            )
            sessions.end_user_sessions(
                db,
                auth.user.id,
                reason=SessionEndReason.PASSWORD_CHANGED,
                now=facts.now,
                keep_session_id=auth.session.id,
            )
            row, token = sessions.reissue(
                db,
                auth,
                active_tenant_id=auth.session.active_tenant_id,
                mfa_verified_at=auth.session.mfa_verified_at,
            )
            _record(
                db,
                keyring,
                facts,
                SecurityEventKind.PASSWORD_CHANGED,
                AuditOutcome.SUCCESS,
                user_id=auth.user.id,
                session_id=row.id,
            )
    if refusal is not None:
        raise refusal
    return AuthenticatedSession(
        session=row, token=token, user=auth.user, active_tenant=auth.active_tenant, facts=facts
    )


def _email_workspace(request_id: str, user_id: UUID, now: datetime) -> UUID | None:
    """The workspace the reset email is written in (T-PLT-42 rule 1): the tenant of the user's
    ACTIVE membership opened last; ties and never-opened memberships by ascending
    ``tenant.code``. A person with NO active membership is answered in the workspace of an open
    invitation — an ``INVITED`` membership whose ``invitation_expires_at`` lies after ``now`` —
    the one invited last, ties by ascending tenant id (04 rev 1.308; item
    RESET-EMAIL-OPEN-INVITATION-1). Before the item such a person got no email: someone removed
    from a workspace and invited again — there or to another — who had forgotten the earlier
    password could neither accept the invitation, which asks for it, nor reset it. None for a
    person with neither: no email, as before. One statement: the function's one read across
    tenants (dev-guide DG-KRN-DB-12). The directory is joined OUTER: RLS-TN shows a user the
    tenants of their ACTIVE memberships alone, so the workspace of an invitation has no readable
    ``tenant`` row here — an inner join dropped the invitation — and no code to order by.
    "Open" is what the acceptance reads: ``INVITED``, a token hash present, not expired. The hash
    is named although no row can lack it — T-PLT-07's checks give every ``INVITED`` membership a
    token hash and an expiry, which is why a sandbox copy carries an open invitation as REMOVED.
    A plain read: the request holds the person's row FOR KEY SHARE in its own transaction, this
    one locks none."""
    active = tenant_membership.c.status == MembershipStatus.ACTIVE.value
    invited = and_(
        tenant_membership.c.status == MembershipStatus.INVITED.value,
        tenant_membership.c.invitation_token_sha256.is_not(None),
        tenant_membership.c.invitation_expires_at > now,
    )
    with identity_session(request_id=request_id, user_id=user_id) as db:
        found = db.execute(
            select(tenant_membership.c.tenant_id)
            .outerjoin(tenant, tenant.c.id == tenant_membership.c.tenant_id)
            .where(tenant_membership.c.user_id == user_id, or_(active, invited))
            .order_by(
                case((active, 0), else_=1),  # a member is answered as a member, as before
                tenant_membership.c.last_opened_at.desc().nulls_last(),
                # among invitations (never opened): the one sent last
                case((active, None), else_=tenant_membership.c.invited_at).desc().nulls_last(),
                tenant.c.code,
                tenant_membership.c.tenant_id,
            )
            .limit(1)
        ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def reset_message(
    *, tenant_id: UUID, token_id: UUID, email: str, key_id: str, now: datetime
) -> Mapping[str, Any]:
    """The reset ``outbox_message`` of topic ``EMAIL``, written by SYSTEM. The row holds neither
    the token nor its hash: it names the token by the T-PLT-42 row id and the key it was derived
    with, and the link is composed when the email is sent (04 T-INT-03 ``payload`` rev 1.151)."""
    text = (
        "Hello,\n\nWe received a request to reset your eRev password. The link expires in 60 "
        "minutes. If you did not ask for it, ignore this email and your password stays the same."
        "\n\nReset the password:"
    )
    return outbox.message_values(
        tenant_id=tenant_id,
        topic=OutboxTopic.EMAIL,
        aggregate_type=RESET_AGGREGATE,
        aggregate_id=token_id,
        dedupe_key=f"password-reset:{token_id}",
        payload={
            "to": email,
            "subject": "Reset your eRev password",
            "text": text,
            "link_path": RESET_LINK,
            outbox.LINK_TOKEN: outbox.link_token_reference(RESET_PURPOSE, token_id, key_id),
            "reference": str(token_id),
            "notification_id": None,
        },
        now=now,
        created_by=None,
        created_by_kind=PrincipalKind.SYSTEM,
    )


def request_reset(
    email: str, *, facts: RequestFacts, keyring: KeyRing, limiter: PasswordResetRateLimiter
) -> None:
    """``POST /session/password-reset`` (T-PLT-42 rules 1 and 2); the route answers 202 whatever
    happens here, so the response never reveals whether an account exists."""
    normalised = sessions.normalise_email(email)
    if not limiter.admit(address=facts.source_ip or "unknown", now=facts.now):
        with identity_session(request_id=facts.request_id) as db:
            _record(
                db,
                keyring,
                facts,
                SecurityEventKind.PASSWORD_RESET_REQUESTED,
                AuditOutcome.DENIED,
                email_sha256=sessions.sha256_hex(normalised),
                detail={"limit": "address"},
            )
        return
    with identity_session(request_id=facts.request_id) as db:
        user = (
            db.execute(
                select(app_user.c.id, app_user.c.status, app_user.c.password_hash)
                .where(app_user.c.email == normalised)
                .with_for_update(key_share=True)
            )
            .mappings()
            .one_or_none()
        )
        if user is None or user["status"] != UserStatus.ACTIVE or user["password_hash"] is None:
            return
        user_id: UUID = user["id"]
        issued = db.execute(
            select(func.count())
            .select_from(password_reset_token)
            .where(
                password_reset_token.c.user_id == user_id,
                password_reset_token.c.created_at > facts.now - RESET_WINDOW,
            )
        ).scalar_one()
        if issued >= RESET_TOKENS_PER_USER:
            _record(
                db,
                keyring,
                facts,
                SecurityEventKind.PASSWORD_RESET_REQUESTED,
                AuditOutcome.DENIED,
                user_id=user_id,
                detail={"limit": "user"},
            )
            return
        workspace = _email_workspace(facts.request_id, user_id, facts.now)
        # The token is derived from the row's id, so that it need not be stored to be emailed.
        token_id = new_id()
        link = keyring.link_token(RESET_PURPOSE, token_id)
        db.execute(
            update(password_reset_token)
            .where(
                password_reset_token.c.user_id == user_id,
                password_reset_token.c.used_at.is_(None),
                password_reset_token.c.superseded_at.is_(None),
            )
            .values(superseded_at=facts.now)
        )
        db.execute(
            insert(password_reset_token).values(
                id=token_id,
                user_id=user_id,
                token_sha256=sessions.sha256_hex(link.token),
                created_at=facts.now,
                token_expires_at=facts.now + RESET_LIFETIME,
                request_id=facts.request_id,
                ip_address=facts.source_ip,
                expires_at=facts.now + RESET_LIFETIME + RESET_RETENTION,
            )
        )
        _record(
            db,
            keyring,
            facts,
            SecurityEventKind.PASSWORD_RESET_REQUESTED,
            AuditOutcome.SUCCESS,
            user_id=user_id,
            # ``email_tenant_id``: the workspace the email is written in, or null with ``email``
            # false (04 rev 1.308) — the pre-tenant log says where the link went.
            detail={
                "password_reset_token_id": str(token_id),
                "email": workspace is not None,
                "email_tenant_id": None if workspace is None else str(workspace),
            },
        )
        if workspace is not None:
            # The last writes of the transaction run in the workspace's tenant context (RLS-T);
            # the minute outbox sweeper relays the message (SCH-03; SPEC-Q-179).
            set_tenant_context(db, DbContext(tenant_id=workspace, user_id=None, entity_scope="*"))
            outbox.insert_message(
                db,
                reset_message(
                    tenant_id=workspace,
                    token_id=token_id,
                    email=normalised,
                    key_id=link.key_id,
                    now=facts.now,
                ),
            )


def confirm_reset(token: str, new_password: str, *, facts: RequestFacts, keyring: KeyRing) -> None:
    """``POST /session/password-reset/confirm`` (T-PLT-42 rule 3): 404 ``not-found`` for an
    unknown, expired, used or superseded token, 422 ``password-policy`` for a weak password."""
    with identity_session(request_id=facts.request_id) as db:
        found = (
            db.execute(
                select(
                    password_reset_token.c.id,
                    password_reset_token.c.user_id,
                    password_reset_token.c.token_expires_at,
                    password_reset_token.c.used_at,
                    password_reset_token.c.superseded_at,
                    app_user.c.email,
                    app_user.c.status,
                )
                .join(app_user, app_user.c.id == password_reset_token.c.user_id)
                .where(password_reset_token.c.token_sha256 == sessions.sha256_hex(token))
                .with_for_update(of=password_reset_token)
            )
            .mappings()
            .one_or_none()
        )
        if (
            found is None
            or found["used_at"] is not None
            or found["superseded_at"] is not None
            or found["token_expires_at"] <= facts.now
            or found["status"] != UserStatus.ACTIVE
        ):
            raise Problem("not-found")
        user_id: UUID = found["user_id"]
        passwords.check_policy(new_password, email=str(found["email"]), field=NEW_PASSWORD_FIELD)
        db.execute(
            update(password_reset_token)
            .where(password_reset_token.c.id == found["id"])
            .values(used_at=facts.now)
        )
        db.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(
                **_new_password_values(new_password, user_id=user_id, now=facts.now),
                failed_login_count=0,
                locked_until=None,
            )
        )
        sessions.end_user_sessions(
            db, user_id, reason=SessionEndReason.PASSWORD_CHANGED, now=facts.now
        )
        _record(
            db,
            keyring,
            facts,
            SecurityEventKind.PASSWORD_RESET_COMPLETED,
            AuditOutcome.SUCCESS,
            user_id=user_id,
            detail={"password_reset_token_id": str(found["id"])},
        )
        _record(
            db,
            keyring,
            facts,
            SecurityEventKind.PASSWORD_CHANGED,
            AuditOutcome.SUCCESS,
            user_id=user_id,
        )
