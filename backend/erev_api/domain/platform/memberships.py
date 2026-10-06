"""Tenant memberships (04 T-PLT-07, T-PLT-25, §14.3 item 4; PRD §5.4, BR-PLT-01; REQ-PLT-021,
REQ-PLT-038).

``on_membership_activated`` runs in the transaction that makes a membership ACTIVE. It seeds one
``notification_preference`` per E-69 kind with the PRD §5.4 email defaults; rows that already exist
are kept, so a membership that becomes ACTIVE again keeps its choices.

``accept_invitation`` is T-PLT-07 invitation acceptance, run as the invited user. It resolves the
token and checks the password first; then one unit of work sets the first password, makes the
membership ACTIVE with both invitation columns cleared — ``activated_at`` is set once: a
membership invited again after a removal (PRD SM-13 rev 1.201) keeps its first acceptance —,
seeds the preferences, audits ``membership.accept``, evaluates setup completion — an accepted
invitation can make the second of the two people of PRD BR-PLT-02
(``setup.evaluate_setup_completion``; 04 T-PLT-01 rev 1.224) — and opens a session with the
workspace active (``TENANT_SELECTED``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert

from erev_api.auth import invitations, sessions
from erev_api.auth.invitations import Invitation
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import effective_grants
from erev_api.auth.principal import Principal, RequestContext
from erev_api.auth.sessions import AuthenticatedSession, RequestFacts
from erev_api.clock import Clock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import notification_preference, tenant_membership
from erev_api.domain.platform import setup
from erev_api.enums import MembershipStatus, NotificationKind, PrincipalKind
from erev_api.events.notifications import EMAIL_DEFAULTS
from erev_api.files.store import FileStore
from erev_api.problems import Problem
from erev_api.uow import unit_of_work

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "tenant_membership"
ACCEPT_ACTION: Final = "membership.accept"  # 04 T-PLT-07


def on_membership_activated(uow: UnitOfWork, membership_id: UUID) -> int:
    """Insert the 12 default preferences of ``membership_id``; returns the rows inserted."""
    principal = uow.principal
    rows = [
        {
            "tenant_id": principal.tenant_id,
            "id": new_id(),
            "membership_id": membership_id,
            "kind": kind.value,
            "in_app": True,
            "email": EMAIL_DEFAULTS[kind],
            "updated_at": uow.now,
            "updated_by": principal.id,
            "updated_by_kind": principal.kind.value,
        }
        for kind in NotificationKind
    ]
    statement = (
        insert(notification_preference)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["tenant_id", "membership_id", "kind"])
        .returning(notification_preference.c.id)
    )
    return len(uow.session.execute(statement).all())


def _member_context(invitation: Invitation, facts: RequestFacts) -> RequestContext:
    """The invited user as the principal of the acceptance, with the grants the membership's
    assignments confer at the request time."""
    lookup = DbContext(tenant_id=invitation.tenant_id, user_id=invitation.user_id, entity_scope="*")
    with tenant_session(lookup, read_only=True) as db:
        grants = effective_grants(db, invitation.membership_id, at=facts.now)
    principal = Principal(
        kind=PrincipalKind.USER,
        id=invitation.user_id,
        tenant_id=invitation.tenant_id,
        membership_id=invitation.membership_id,
        display_name=invitation.display_name,
        roles=grants.roles,
        permissions=grants.permissions,
        permission_scopes=grants.permission_scopes,
        entity_scope=grants.entity_scope,
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
        role_scopes=grants.role_scopes,
    )
    return RequestContext(
        principal=principal,
        tenant_kind=invitation.tenant_kind,
        request_id=facts.request_id,
        source_ip=facts.source_ip,
        user_agent=facts.user_agent,
        idempotency_key=None,
        if_match=None,
        now=facts.now,
        format_locale=invitation.format_locale or invitation.default_locale,
    )


def accept_invitation(
    *,
    token: str,
    password: str,
    facts: RequestFacts,
    keyring: KeyRing,
    clock: Clock,
    files: FileStore,
    previous_token: str | None,
) -> AuthenticatedSession:
    """``POST /session/accept-invitation`` (04 T-PLT-07): the new session with the workspace
    active, or 404 ``not-found``, 422 ``password-policy`` or ``validation-failed``, 423
    ``account-locked``.

    The password is refused, counted and locked out in a transaction of its own
    (``check_acceptance_password``); the session is opened in the next. That one takes the
    membership's row and then the identity's (dev-guide DG-KRN-AUTH-08) and looks at the password
    again under it (``invitations.claim_identity``; item INVITE-ACCEPT-SESSION-1): a password
    changed or reset between the two is 404 ``not-found``, and nothing of the acceptance is
    kept."""
    invitation = invitations.find_invitation(token, facts=facts, keyring=keyring, route="accept")
    invitations.check_acceptance_password(invitation, password, facts=facts, keyring=keyring)
    ctx = _member_context(invitation, facts)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        activated = uow.session.execute(
            update(tenant_membership)
            .where(
                tenant_membership.c.tenant_id == invitation.tenant_id,
                tenant_membership.c.id == invitation.membership_id,
                tenant_membership.c.status == MembershipStatus.INVITED.value,
                tenant_membership.c.invitation_token_sha256 == invitation.token_sha256,
                tenant_membership.c.invitation_expires_at > uow.now,
            )
            .values(
                status=MembershipStatus.ACTIVE.value,
                # Set once (04 T-PLT-07 rev 1.293): a membership invited again after a removal
                # keeps its FIRST acceptance. ``routing._other_holders`` measures a past holder's
                # assignments from it, and the copy's load holds back a membership by it.
                activated_at=func.coalesce(tenant_membership.c.activated_at, uow.now),
                invitation_token_sha256=None,
                invitation_expires_at=None,
                updated_by=invitation.user_id,
                updated_by_kind=PrincipalKind.USER.value,
            )
            .returning(tenant_membership.c.activated_at)
        ).scalar_one_or_none()
        if activated is None:
            raise Problem("not-found")
        # The membership's row is held; the identity's follows it, and the session the identity's.
        invitations.claim_identity(uow.session, invitation, password, now=uow.now)
        on_membership_activated(uow, invitation.membership_id)
        uow.audit(
            action=ACCEPT_ACTION,
            object_type=OBJECT_TYPE,
            object_id=invitation.membership_id,
            before={"status": MembershipStatus.INVITED.value},
            after={
                "status": MembershipStatus.ACTIVE.value,
                "activated_at": uow.now if activated == uow.now else activated,
            },
        )
        # The member who accepts may be the second of the two people of PRD BR-PLT-02: setup
        # completes with the command that makes its conditions true (04 T-PLT-01 rev 1.224).
        setup.evaluate_setup_completion(uow)
        _, session_token = sessions.open_workspace_session(
            uow.session,
            user_id=invitation.user_id,
            tenant_id=invitation.tenant_id,
            facts=facts,
            keyring=keyring,
            previous_token=previous_token,
        )
        uow.commit()
    return sessions.authenticate(session_token, facts=facts, keyring=keyring, csrf=None)
