"""Users and memberships (04 §15.3 API-R-05, T-PLT-07, T-PLT-10, SMAP-14, §14.3 item 3; PRD SM-13,
BR-PLT-02, BR-PLT-06, BR-PLT-08; SCREENS_B §9.10; REQ-PLT-008, REQ-PLT-010, REQ-PLT-012;
BUILD_SPEC PLF-17, BS1-D-06, BS1-D-24).

``invite_user`` creates an ``INVITED`` membership, reusing the ``app_user`` of a known email, queues
the invitation email and requests one ``ROLE_ASSIGNMENT`` per role. The combined roles pass the SoD
check before anything is written. Each request routes to an ``access.approve`` holder other than the
inviter, or rule ``AUTO-BOOTSTRAP`` approves it while setup is incomplete. A role is granted for
all entities or for named entity codes (``erev_api.auth.entity_scope``: the codes name legal
entities of the workspace, and nobody grants beyond their own access — REQ-PLT-012; supervisor
ruling R-63 (e)).

Suspension and removal need a reason of at least 10 characters and end the member's sessions in the
workspace; removal also revokes the member's role assignments and keeps the history. ``reset_mfa``
needs a fresh step-up, disables the member's factor, writes ``MFA_RESET`` and ends every session of
the user. ``resend_invitation`` replaces the token and restarts the 7-day lifetime. ``update_user``
corrects the display name of an invitation whose person has not signed in yet and was added by that
invitation. Until an invitation of a person who already had an identity is accepted, API-S-User
withholds the person's name, last sign-in and MFA status (D-80). An administrator
never suspends, removes, reactivates or resets their own membership.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Select,
    Text,
    and_,
    case,
    cast,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session

from erev_api.approvals import delegations, preview, subjects
from erev_api.approvals import engine as approvals
from erev_api.audit import writer as audit_writer
from erev_api.audit.writer import actor_of
from erev_api.auth import entity_scope, mfa, sod
from erev_api.auth.security_events import record_security_event
from erev_api.auth.sessions import RETENTION, end_user_sessions, normalise_email, sha256_hex
from erev_api.db import new_id
from erev_api.db.session import of_session_tenant, system_entity_scope, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    role,
    role_assignment,
    rule,
    tenant,
    tenant_membership,
    user_mfa_factor,
    user_session,
)
from erev_api.domain.platform import memberships, provisioning, setup
from erev_api.domain.platform.approval_queries import Page, actor, display_names
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    AuditOutcome,
    MembershipStatus,
    SecurityEventKind,
    SessionEndReason,
    UserStatus,
)
from erev_api.events import outbox
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import RequestContext
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "tenant_membership"
FACTOR_OBJECT: Final = mfa.FACTOR_OBJECT
INVITE_ACTION: Final = "tenant_membership.invite"
UPDATE_ACTION: Final = "tenant_membership.update"
SUSPEND_ACTION: Final = "tenant_membership.suspend"
REACTIVATE_ACTION: Final = "tenant_membership.reactivate"
REMOVE_ACTION: Final = "tenant_membership.remove"
RESEND_ACTION: Final = "tenant_membership.resend_invitation"
RESET_MFA_ACTION: Final = mfa.RESET_ACTION
REVOKE_ASSIGNMENT_ACTION: Final = "role_assignment.revoke"
RULE_USER: Final = "T-PLT-02"
RULE_MEMBERSHIP: Final = "T-PLT-07"
RULE_ASSIGNMENT: Final = "T-PLT-10"
RULE_LIFECYCLE: Final = "SM-13"
RULE_REASON: Final = "BR-PLT-08"
RULE_ENTITY: Final = entity_scope.RULE_ENTITY  # 04 DB-12
# API-R-05: the permission an invitation's roles are requested under (the grantor's own scope).
GRANT_PERMISSION: Final = "user.manage"
MIN_REASON_LENGTH: Final = 10  # SCREENS_B SB-R-05
# SMAP-14 derived assignment states.
REQUESTED: Final = "REQUESTED"
ACTIVE: Final = "ACTIVE"
REVOKED: Final = "REVOKED"

# [J] SPEC-Q-182: copy the documents leave open; SB-R-05 gives the reason error.
EMAIL_INVALID: Final = "Enter an email address."
NAME_LENGTH: Final = "Use 1 to 400 characters."
ROLES_EMPTY: Final = "Add at least one role."
ROLE_UNKNOWN: Final = "Choose an active role of this workspace."
ROLE_TWICE: Final = "Add each role once."
ENTITY_UNKNOWN: Final = entity_scope.ENTITY_UNKNOWN
ENTITIES_EMPTY: Final = entity_scope.ENTITIES_EMPTY
ALREADY_MEMBER: Final = "This person is already a member of this workspace."
REASON_SHORT: Final = "Enter at least 10 characters."
SELF_DETAIL: Final = "Another administrator must change your own membership."
# REQ-PLT-012 on what is already granted (supervisor ruling R-63 (e) as refined by R-115 (c)): a
# command on a membership needs the actor's permission for every entity of the member's role
# assignments.
MEMBER_BEYOND_SCOPE: Final = (
    "This member holds access for entities beyond your own. An administrator whose access covers "
    "every entity of the member's roles must make this change."
)
NOT_ACTIVE: Final = "Only an active membership can be suspended."
NOT_SUSPENDED: Final = "Only a suspended membership can be reactivated."
ALREADY_REMOVED: Final = "This membership is already removed."
NOT_INVITED: Final = "Only an open invitation can be sent again."
NO_FACTOR: Final = "This member has not set up multi-factor authentication."
NAME_LOCKED: Final = "Only an invitation whose person has not signed in yet can be renamed."
# D-80 copy; [J] SPEC-Q-207 for the reset refusal, which no document words.
OPERATOR_EMAIL: Final = "This email cannot be invited to a workspace."
NOT_RESETTABLE: Final = (
    "Only an active or suspended member's multi-factor authentication can be reset."
)
RESETTABLE: Final = frozenset({MembershipStatus.ACTIVE.value, MembershipStatus.SUSPENDED.value})
# D-80 rule 6 copy; [J] SPEC-Q-215.
NAME_NOT_OWNED: Final = "Only a person this invitation added to eRev can be renamed."
# D-80 rule 5, by the membership's status (04 T-PLT-02 rev 1.316; item
# IDENTITY-WITHHELD-BY-STATUS-1): a person who is not a member NOW — the invitation is open, or
# the membership is removed — is shown to the workspace as little as a person it has only
# invited. The last sign-in and the MFA state are the person's own facts: withheld whoever
# created the identity (``SIGN_IN_WITHHELD``). The name is the email unless this membership's
# invitation created the identity (``app_user.created_at`` and ``created_by`` equal the
# membership's ``invited_at`` and ``created_by``): that name the workspace typed itself
# (``IDENTITY_WITHHELD``). ``activated_at`` is no part of the rule — it was until this revision
# ([J] SPEC-Q-211), and a removed member's row showed the person's current name, last sign-in
# and MFA state, a sign-in made after the removal among them (measured).
# An erased identity is not withheld (05 PRV-07 a). The erasure removes every membership of the
# person and leaves the product's own label and address on the row (``privacy.erased_display_name``,
# ``erased_email``), the same in every workspace: no name of a person is left to withhold, and a
# membership's row and an actor read by user id say the same of the person. ``ERASED`` is the
# erasure's own mark, the address of the row's id — the one form the guard of ``app_user`` admits
# a rewrite of ``email`` to, and one no invitation can type: the id is not known before the row.
WITHHELD_STATUSES: Final = (MembershipStatus.INVITED.value, MembershipStatus.REMOVED.value)
ERASED: Final[ColumnElement[bool]] = app_user.c.email == func.concat(
    "erased+", cast(app_user.c.id, Text), "@invalid.erev"
)
SIGN_IN_WITHHELD: Final[ColumnElement[bool]] = tenant_membership.c.status.in_(WITHHELD_STATUSES)
IDENTITY_WITHHELD: Final[ColumnElement[bool]] = and_(
    tenant_membership.c.status.in_(WITHHELD_STATUSES),
    ~ERASED,
    or_(
        app_user.c.created_at != tenant_membership.c.invited_at,
        app_user.c.created_by.is_distinct_from(tenant_membership.c.created_by),
    ),
)
# What a workspace is shown of the person behind a membership: the email in place of the name,
# and no last sign-in, while the identity is withheld. ONE expression for every reader (04
# T-PLT-02 rev 1.315; item IDENTITY-BEFORE-ACCEPTANCE-READERS-1): a statement that joins a
# membership to its person selects these — or calls ``shown_name`` — and never the two columns
# themselves (``tests/architecture/test_shown_identity.py``). Measured before the item: the rule
# was read by API-S-User alone, and a role request's summary, a role assignment, an audit
# event's label and an access review named a person the workspace had only invited.
SHOWN_NAME: Final = case((IDENTITY_WITHHELD, app_user.c.email), else_=app_user.c.display_name)
SHOWN_LAST_LOGIN: Final = case((~SIGN_IN_WITHHELD, app_user.c.last_login_at))
# The name API-S-User shows, under its member's name.
SHOWN_DISPLAY_NAME: Final = SHOWN_NAME.label("display_name")


@dataclass(frozen=True, slots=True)
class RoleGrant:
    """One role of an invitation: all entities, or the named entity codes."""

    role_id: UUID
    is_all_entities: bool
    entity_codes: tuple[str, ...]


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _updated(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {"updated_by": principal.id, "updated_by_kind": principal.kind.value}


def _lock_membership(session: Session, membership_id: UUID) -> Mapping[str, Any]:
    row = (
        session.execute(
            select(tenant_membership)
            .where(tenant_membership.c.id == membership_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def _another_member(uow: UnitOfWork, membership: Mapping[str, Any]) -> None:
    if membership["id"] == uow.principal.membership_id:
        raise Problem("forbidden", SELF_DETAIL)


def beyond_scope(message: str) -> Problem:
    """403 ``forbidden`` by name: the actor's own access does not cover the grant it would change
    (rule ``T-PLT-10``; REQ-PLT-012). The command records the refusal first (``scope_denial``)."""
    return Problem(
        "forbidden", message, errors=[ProblemError(rule_id=RULE_ASSIGNMENT, message=message)]
    )


def scope_denial(*, all_entities: bool = False) -> dict[str, str]:
    """The detail of the ``DENIED`` audit event a scope refusal writes before it answers, in a
    transaction of its own (DG-KRN-AUTH-05): the rule and, for a command that needs the
    permission for all entities, the scope. Like the answer it names no entity."""
    return {"rule_id": RULE_ASSIGNMENT, **({"scope": "*"} if all_entities else {})}


def require_member_scope(
    uow: UnitOfWork, membership_id: UUID, *, action: str, permission: str = GRANT_PERMISSION
) -> None:
    """A command on a membership needs the actor's ``permission`` — ``user.manage`` for the
    membership's own commands — for every entity any of the member's role assignments names, and
    for all entities when one of them is for all entities: an administrator of AVM-DE does not
    suspend, remove or reset the Controller of every entity, and does not ask for or revoke an
    SoD exception of a member of another entity (``role.manage``; supervisor ruling R-119 (b)
    and the ruling of 2026-10-01 on item SCOPE-WORKSPACE-LISTS-1 (c3)). A member without a role
    assignment is covered by every administrator. ``action`` is the command's audit action, under
    which a refusal is recorded."""
    held = entity_scope.held_scope(uow.principal, permission)
    if not entity_scope.covers(held, entity_scope.assigned(uow.session, membership_id)):
        audit_writer.record_denied(
            uow.ctx,
            action=action,
            object_type=OBJECT_TYPE,
            object_id=membership_id,
            permission=permission,
            detail=scope_denial(),
            keyring=uow.keyring,
        )
        raise beyond_scope(MEMBER_BEYOND_SCOPE)


def require_reason(reason: str | None) -> str:
    """SB-R-05: suspending or removing a member needs a reason of at least 10 characters."""
    text = (reason or "").strip()
    if len(text) < MIN_REASON_LENGTH:
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="reason", rule_id=RULE_REASON, message=REASON_SHORT)],
        )
    return text


def _transition_refused(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        errors=[ProblemError(field="status", rule_id=RULE_LIFECYCLE, message=message)],
    )


def _set_status(uow: UnitOfWork, membership_id: UUID, **values: Any) -> None:
    """Write a membership's status. A delegation rests on its delegator's ACTIVE membership (PRD
    BR-PLT-07): one that is unsupported is ended before the change, so that a reactivation
    revives none, and after it, so that a suspension or removal leaves none standing. A removal
    ends what was delegated TO the member as well; a delegate removed before the sweep learned
    that is met by the sweep before the change, when the person is invited again."""
    delegations.end_unsupported(uow, cause=delegations.MEMBERSHIP_STATUS)
    uow.session.execute(
        update(tenant_membership)
        .where(tenant_membership.c.id == membership_id)
        .values(**values, **_updated(uow))
    )
    delegations.end_unsupported(uow, cause=delegations.MEMBERSHIP_STATUS)


def _end_workspace_sessions(uow: UnitOfWork, user_id: UUID) -> int:
    """End the user's open sessions in this workspace ``REVOKED``; returns how many ended."""
    ended = uow.session.execute(
        update(user_session)
        .where(
            user_session.c.user_id == user_id,
            user_session.c.active_tenant_id == uow.principal.tenant_id,
            user_session.c.ended_at.is_(None),
        )
        .values(
            ended_at=uow.now,
            end_reason=SessionEndReason.REVOKED.value,
            expires_at=uow.now + RETENTION,
        )
        .returning(user_session.c.id)
    )
    return len(ended.all())


def _queue_invitation(
    uow: UnitOfWork,
    *,
    membership_id: UUID,
    email: str,
    invitation: provisioning.InvitationToken,
    expires_at: Any,
    dedupe_key: str | None,
) -> None:
    principal = uow.principal
    workspace = uow.session.execute(
        select(tenant.c.display_name).where(tenant.c.id == principal.tenant_id)
    ).scalar_one()
    outbox.insert_message(
        uow.session,
        provisioning.invitation_message(
            tenant_id=principal.tenant_id,
            membership_id=membership_id,
            email=email,
            workspace_name=str(workspace),
            link_reference=invitation.reference,
            key_id=invitation.key_id,
            expires_at=expires_at,
            created_by=principal.id,
            created_by_kind=principal.kind,
            now=uow.now,
            dedupe_key=dedupe_key,
        ),
    )


def request_role_assignment(
    uow: UnitOfWork,
    *,
    membership_id: UUID,
    role_id: UUID,
    role_code: str,
    role_name: str,
    scope: entity_scope.EntityScope = entity_scope.ALL_ENTITIES,
    sod_exception_id: UUID | None = None,
) -> Mapping[str, Any]:
    """Submit one ``ROLE_ASSIGNMENT`` request for ``scope`` (BS1-D-24): the proposal is the
    preview's ``after`` and the membership's current assignments its ``before``. Both name their
    entities by id and by code, and the summary names the entities of a grant that is not for all
    entities (PRD J-22.1; ruling R-63 (e)): the approver reads what is granted, and for where.

    The summary names the member as this workspace is shown the person when the request is
    submitted (``shown_name``; D-80 rule 5): it is stored with the request, and an invitation's
    own requests are submitted before the invitation is accepted. No caller hands the name in."""
    current = uow.session.execute(
        select(role.c.code, role_assignment.c.is_all_entities, role_assignment.c.entity_ids)
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            )
        )
        .where(
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.revoked_at.is_(None),
        )
        .order_by(role.c.code, role_assignment.c.id)
    ).all()
    known = entity_scope.names(
        uow.session, [value for _, _, entity_ids in current for value in entity_ids or ()]
    )
    before = {
        "membership_id": str(membership_id),
        "assignments": [
            {
                "role_code": str(code),
                "is_all_entities": bool(is_all),
                "entity_ids": sorted(str(value) for value in entity_ids or ()),
                "entity_codes": [
                    str(item["code"]) for item in entity_scope.refs(known, entity_ids or ())
                ],
            }
            for code, is_all, entity_ids in current
        ],
    }
    after = subjects.role_assignment_proposal(
        membership_id=membership_id,
        role_id=role_id,
        role_code=role_code,
        is_all_entities=scope.is_all_entities,
        entity_ids=scope.entity_ids,
        entity_codes=scope.entity_codes,
        sod_exception_id=sod_exception_id,
    )
    summary = f"Grant {role_name} to {shown_name(uow.session, membership_id)}"
    # The rule ends when the conditions of PRD BR-PLT-02 hold (04 T-PLT-01 rev 1.224), whatever
    # made them true. They are read before the request is routed: in a workspace whose completion
    # is due the request is kept from rule AUTO-BOOTSTRAP and waits for a person. The stamp is
    # set by the evaluation below, the command's last lock (dev-guide DG-KRN-DB-08 (3a)).
    due = setup.completion_due(uow)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT,
        subject_id=new_id(),
        summary=summary if scope.is_all_entities else f"{summary} for {scope.label}",
        impact_preview=approvals.ImpactPreview(before=before, after=after),
        auto_approval=not due,
    )
    # Rule AUTO-BOOTSTRAP may have approved the assignment at submission (BR-PLT-02; RFD-19).
    setup.evaluate_setup_completion(uow)
    return request


def _already_member() -> ProblemError:
    return ProblemError(field="email", rule_id=RULE_MEMBERSHIP, message=ALREADY_MEMBER)


def _void_stale_role_requests(uow: UnitOfWork, membership_id: UUID) -> None:
    """Void each PENDING role request for the membership whose content no longer holds
    (DG-KRN-APR-05; 04 T-PLT-07 rev 1.293). The read is the invitation's own control, not the
    inviter's view: a request for ONE entity is a row the inviter's entity scope may hide
    (RLS-TE on ``approval_request.entity_id``), and what an invitation ends does not depend on
    who invites (supervisor rulings R-42 (d) and R-64 (1)) — so it runs under the tenant's
    SYSTEM scope (dev-guide DG-KRN-DB-05 rev 1.286; the door of DG-ARC-16 lists it). Nothing it
    reads is returned: the inviter's answer is read outside the block."""
    with system_entity_scope(uow.session):
        pending = pending_proposals(
            uow.session, {str(membership_id)}, files=uow.files, keyring=uow.keyring
        )
        for request, _ in pending:
            approvals.void_if_stale(
                uow,
                subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT,
                subject_id=UUID(str(request["subject_id"])),
            )


def _end_first_life(uow: UnitOfWork, membership_id: UUID) -> None:
    """Before a removed person is invited again (PRD SM-13 rev 1.201; 04 T-PLT-07 rev 1.293):
    nothing asked or granted for the membership's first life passes into its second.

    A role request for the member that was still PENDING at the removal hashed "the membership
    is not removed" into its content, so it has been stale since: it is voided now, while it is
    (DG-KRN-APR-05) — whoever invites, and whatever entity the request names
    (``_void_stale_role_requests``). Left pending, its hash would match again once the status is
    INVITED, and a role asked for the first life could be decided for the second. The SoD
    exceptions of the membership end the same way (``sod.end_for_invitation``). The role
    assignments were revoked by the removal and stay so; none is revived. And what was delegated
    to the member ended with the removal (``delegations.end_unsupported_rows``).

    An assignment can stand on the removed row all the same (04 T-PLT-07 rev 1.306; item
    INVITE-ENDS-STANDING-ASSIGNMENTS-1): an approval that passed its check before the removal
    committed inserts after it. It was inert while REMOVED was the last state of a membership,
    and would be in force from the acceptance of the new invitation. Whatever stands on the row
    is revoked here, with its ``role_assignment.revoke`` event, whatever left it there."""
    # Imported where it is used: the SoD module imports this one.
    from erev_api.domain.platform import sod as sod_exceptions  # noqa: PLC0415

    _void_stale_role_requests(uow, membership_id)
    sod_exceptions.end_for_invitation(uow, membership_id)
    principal = uow.principal
    standing = uow.session.execute(
        update(role_assignment)
        .where(
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.revoked_at.is_(None),
        )
        .values(revoked_at=uow.now, revoked_by=principal.id, revoked_by_kind=principal.kind.value)
        .returning(role_assignment.c.id)
    ).all()
    for (assignment_id,) in sorted(standing):
        uow.audit(
            action=REVOKE_ASSIGNMENT_ACTION,
            object_type=subjects.ROLE_ASSIGNMENT_OBJECT,
            object_id=assignment_id,
            before={"revoked_at": None},
            after={"revoked_at": uow.now},
            comment=sod_exceptions.INVITED_AGAIN,
        )
    if standing:
        # As after every revocation (PRD BR-PLT-07): the member gave no delegation since the
        # removal, so the sweep finds nothing of theirs to end.
        delegations.end_unsupported(uow, cause=delegations.ROLE_ASSIGNMENT_REVOKED)


def invite_user(
    uow: UnitOfWork, *, email: str, display_name: str, roles: Sequence[RoleGrant]
) -> UUID:
    """``POST /users``: the membership id after collecting every finding (DG-CMD-03) — a new
    membership, or the person's REMOVED membership of this workspace, invited again on its row
    (PRD SM-13 rev 1.201): INVITED with a new token and expiry, ``removed_at`` null, while
    ``invited_at`` and ``activated_at`` stay; what the first life left pending or in force is
    ended first (``_end_first_life``), and the roles are requested as for any invitation.

    422 ``validation-failed`` for the email — a person who is INVITED, ACTIVE or SUSPENDED here
    is already a member —, display name and roles; 409 ``sod-conflict`` naming every uncovered
    rule the combined roles meet. Audits ``tenant_membership.invite``; the role requests audit
    their submission and, once approved, ``role_assignment.create``.
    """
    session = uow.session
    principal = uow.principal
    normalised = normalise_email(email)
    name = display_name.strip()
    errors: list[ProblemError] = []
    if not provisioning.EMAIL.fullmatch(normalised):
        errors.append(ProblemError(field="email", rule_id=RULE_MEMBERSHIP, message=EMAIL_INVALID))
    user = session.execute(
        select(app_user.c.id, app_user.c.is_operator, app_user.c.status).where(
            app_user.c.email == normalised
        )
    ).one_or_none()
    former: UUID | None = None  # the person's REMOVED membership of this workspace
    if user is not None and user.is_operator:
        # D-80: a platform operator acts in a workspace only under a support grant (REQ-PLT-036).
        errors.append(ProblemError(field="email", rule_id=RULE_USER, message=OPERATOR_EMAIL))
    elif user is not None:
        standing = session.execute(
            select(tenant_membership.c.id, tenant_membership.c.status).where(
                of_session_tenant(tenant_membership), tenant_membership.c.user_id == user.id
            )
        ).one_or_none()
        # An identity the erasure of 05 PRV-07 a left (DISABLED, under the address the members
        # list shows for it) is not invited again: its membership stays REMOVED.
        erased = user.status == UserStatus.DISABLED.value
        if standing is None:
            pass  # not yet a member: a new membership
        elif standing.status == MembershipStatus.REMOVED.value and not erased:
            former = UUID(str(standing.id))
        else:
            errors.append(_already_member())
    if len(name) not in provisioning.LABEL_LENGTH:
        errors.append(
            ProblemError(field="display_name", rule_id=RULE_MEMBERSHIP, message=NAME_LENGTH)
        )
    if not roles:
        errors.append(ProblemError(field="roles", rule_id=RULE_ASSIGNMENT, message=ROLES_EMPTY))
    granted = {
        UUID(str(row.id)): row
        for row in session.execute(
            select(role.c.id, role.c.code, role.c.name, role.c.is_active).where(
                role.c.id.in_(sorted({grant.role_id for grant in roles}))
            )
        )
    }
    seen: set[UUID] = set()
    held = entity_scope.held_scope(principal, GRANT_PERMISSION)
    scopes: list[entity_scope.EntityScope] = []
    beyond: list[bool] = []  # per role whose scope reached beyond the inviter's own: all entities?
    for index, grant in enumerate(roles):
        prefix = f"roles[{index}]"
        found = granted.get(grant.role_id)
        if found is None or not found.is_active:
            errors.append(
                ProblemError(
                    field=f"{prefix}.role_id", rule_id=RULE_ASSIGNMENT, message=ROLE_UNKNOWN
                )
            )
        elif grant.role_id in seen:
            errors.append(
                ProblemError(field=f"{prefix}.role_id", rule_id=RULE_ASSIGNMENT, message=ROLE_TWICE)
            )
        seen.add(grant.role_id)
        scope, findings = entity_scope.resolve(
            session,
            held=held,
            is_all_entities=grant.is_all_entities,
            entity_codes=grant.entity_codes,
            field=f"{prefix}.entity_codes",
            shape_field=f"{prefix}.is_all_entities",
        )
        errors += findings
        if entity_scope.reaches_beyond(
            held,
            is_all_entities=grant.is_all_entities,
            entity_codes=grant.entity_codes,
            scope=scope,
        ):
            beyond.append(grant.is_all_entities)
        scopes.append(entity_scope.ALL_ENTITIES if scope is None else scope)
    if errors:
        if beyond:
            # The request asked for more than the inviter's own access: recorded as a denial of
            # the invitation, whatever else is wrong with it. The answer stays the 422.
            audit_writer.record_denied(
                uow.ctx,
                action=INVITE_ACTION,
                object_type=OBJECT_TYPE,
                object_id=None,
                permission=GRANT_PERMISSION,
                detail=scope_denial(all_entities=any(beyond)),
                keyring=uow.keyring,
            )
        raise Problem("validation-failed", errors=errors)

    removed: Mapping[str, Any] | None = None
    if former is None:
        membership_id = new_id()
    else:
        # Invited again (PRD SM-13 rev 1.201; 04 T-PLT-07 rev 1.293): a person has one
        # membership of a workspace, and a removed one goes back to INVITED on its row. The row
        # is locked as every command on a membership locks it; an invitation that came first
        # has made the person a member again.
        membership_id = former
        removed = _lock_membership(session, former)
        if removed["status"] != MembershipStatus.REMOVED.value:
            raise Problem("validation-failed", errors=[_already_member()])
    if user is not None:
        # Erasure takes membership then identity locks. Re-read after acquiring the
        # same locks: the initial email lookup may predate a committed erasure.
        # A new membership has no existing row to lock, but still pins its identity.
        identity = session.execute(
            select(app_user.c.email, app_user.c.status, app_user.c.is_operator)
            .where(app_user.c.id == user.id)
            .with_for_update(key_share=True)
        ).one()
        if (
            identity.status == UserStatus.DISABLED.value
            or normalise_email(str(identity.email)) != normalised
            or identity.is_operator
        ):
            raise Problem("validation-failed", errors=[_already_member()])
    if former is not None:
        _end_first_life(uow, former)
    # REQ-PLT-010: the SoD check at request covers the roles together, before any write of the
    # invitation (what ended the first life above is undone with a refusal here).
    sod.assert_assignments_allowed(
        session, membership_id, [grant.role_id for grant in roles], at=uow.now, field="roles"
    )
    created = _created(uow)
    if user is None:
        user_id = new_id()
        session.execute(
            insert(app_user).values(
                id=user_id, email=normalised, display_name=name, password_hash=None, **created
            )
        )
    else:
        # A person who has an identity already keeps the name it carries; the one typed here is
        # not written.
        user_id = UUID(str(user.id))
    invitation = provisioning.invitation_token(uow.keyring)
    digest = sha256_hex(invitation.token)
    expires_at = uow.now + provisioning.INVITATION_LIFETIME
    if removed is None:
        session.execute(
            insert(tenant_membership).values(
                tenant_id=principal.tenant_id,
                id=membership_id,
                user_id=user_id,
                status=MembershipStatus.INVITED.value,
                invited_at=uow.now,
                invitation_token_sha256=digest,
                invitation_expires_at=expires_at,
                **created,
            )
        )
    else:
        # ``invited_at`` stays, as a re-send leaves it (D-80 rules 5 and 6 read it), and
        # ``activated_at`` stays the first acceptance: ``routing._other_holders`` and the copy's
        # load read it as set once. ``removed_at`` goes: the row is no longer removed, and the
        # removal stands in the audit trail.
        _set_status(
            uow,
            membership_id,
            status=MembershipStatus.INVITED.value,
            invitation_token_sha256=digest,
            invitation_expires_at=expires_at,
            removed_at=None,
        )
    _queue_invitation(
        uow,
        membership_id=membership_id,
        email=normalised,
        invitation=invitation,
        expires_at=expires_at,
        dedupe_key=None if removed is None else f"invitation:{membership_id}:{digest[:16]}",
    )
    uow.audit(
        action=INVITE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=membership_id,
        before=None
        if removed is None
        else {"status": MembershipStatus.REMOVED.value, "removed_at": removed["removed_at"]},
        after={
            "user_id": str(user_id),
            "email_sha256": sha256_hex(normalised),
            "status": MembershipStatus.INVITED.value,
            "invitation_expires_at": expires_at,
            **({} if removed is None else {"removed_at": None}),
        },
    )
    for grant, scope in zip(roles, scopes, strict=True):
        found = granted[grant.role_id]
        request_role_assignment(
            uow,
            membership_id=membership_id,
            role_id=grant.role_id,
            role_code=str(found.code),
            role_name=str(found.name),
            scope=scope,
        )
    return membership_id


def update_user(
    uow: UnitOfWork,
    membership_id: UUID,
    *,
    display_name: str,
    check_version: Callable[[int], None],
) -> None:
    """``PATCH /users/{membership_id}``: rename the person of an open invitation who has never
    signed in and whose identity this invitation created (D-80 rule 6); ``check_version`` applies
    the ``If-Match`` precondition to the locked row."""
    session = uow.session
    membership = _lock_membership(session, membership_id)
    require_member_scope(uow, membership_id, action=UPDATE_ACTION)
    check_version(int(membership["row_version"]))
    name = display_name.strip()
    if len(name) not in provisioning.LABEL_LENGTH:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field="display_name", rule_id=RULE_MEMBERSHIP, message=NAME_LENGTH)
            ],
        )
    person = (
        session.execute(
            select(
                app_user.c.display_name,
                app_user.c.password_hash,
                app_user.c.identity_provider_id,
                app_user.c.created_at,
                app_user.c.created_by,
            )
            .where(app_user.c.id == membership["user_id"])
            .with_for_update(key_share=True)
        )
        .mappings()
        .one()
    )
    if (
        membership["status"] != MembershipStatus.INVITED.value
        or person["password_hash"] is not None
        or person["identity_provider_id"] is not None
    ):
        raise _transition_refused(NAME_LOCKED)
    # The name is global: another workspace, or provisioning, created this identity.
    if (person["created_at"], person["created_by"]) != (
        membership["invited_at"],
        membership["created_by"],
    ):
        raise _transition_refused(NAME_NOT_OWNED)
    session.execute(
        update(app_user)
        .where(app_user.c.id == membership["user_id"])
        .values(display_name=name, **_updated(uow))
    )
    _set_status(uow, membership_id)
    # DG-KRN-AUD-06: personal fields are recorded as SHA-256 values.
    uow.audit(
        action=UPDATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=membership_id,
        before={"display_name_sha256": sha256_hex(str(person["display_name"]))},
        after={"display_name_sha256": sha256_hex(name)},
    )


def suspend_membership(uow: UnitOfWork, membership_id: UUID, *, reason: str | None) -> None:
    """``POST /users/{id}/suspend``: ACTIVE → SUSPENDED; the member's workspace sessions end."""
    membership = _lock_membership(uow.session, membership_id)
    _another_member(uow, membership)
    require_member_scope(uow, membership_id, action=SUSPEND_ACTION)
    comment = require_reason(reason)
    if membership["status"] != MembershipStatus.ACTIVE.value:
        raise _transition_refused(NOT_ACTIVE)
    _set_status(uow, membership_id, status=MembershipStatus.SUSPENDED.value)
    ended = _end_workspace_sessions(uow, membership["user_id"])
    uow.audit(
        action=SUSPEND_ACTION,
        object_type=OBJECT_TYPE,
        object_id=membership_id,
        before={"status": MembershipStatus.ACTIVE.value},
        after={"status": MembershipStatus.SUSPENDED.value},
        comment=comment,
        detail={"sessions_ended": ended},
    )


def reactivate_membership(uow: UnitOfWork, membership_id: UUID, *, reason: str | None) -> None:
    """``POST /users/{id}/reactivate``: SUSPENDED → ACTIVE, keeping the notification choices. A
    member who is active again can be the second of the two people of PRD BR-PLT-02, so setup
    completion is evaluated (04 T-PLT-01 rev 1.224)."""
    membership = _lock_membership(uow.session, membership_id)
    _another_member(uow, membership)
    require_member_scope(uow, membership_id, action=REACTIVATE_ACTION)
    if membership["status"] != MembershipStatus.SUSPENDED.value:
        raise _transition_refused(NOT_SUSPENDED)
    _set_status(uow, membership_id, status=MembershipStatus.ACTIVE.value)
    memberships.on_membership_activated(uow, membership_id)
    uow.audit(
        action=REACTIVATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=membership_id,
        before={"status": MembershipStatus.SUSPENDED.value},
        after={"status": MembershipStatus.ACTIVE.value},
        comment=reason,
    )
    setup.evaluate_setup_completion(uow)


def remove_membership(uow: UnitOfWork, membership_id: UUID, *, reason: str | None) -> None:
    """``POST /users/{id}/remove``: any state → REMOVED. The invitation lapses, every role
    assignment is revoked and the workspace sessions end; the rows stay as history."""
    session = uow.session
    principal = uow.principal
    membership = _lock_membership(session, membership_id)
    _another_member(uow, membership)
    require_member_scope(uow, membership_id, action=REMOVE_ACTION)
    comment = require_reason(reason)
    if membership["status"] == MembershipStatus.REMOVED.value:
        raise _transition_refused(ALREADY_REMOVED)
    _set_status(
        uow,
        membership_id,
        status=MembershipStatus.REMOVED.value,
        removed_at=uow.now,
        invitation_token_sha256=None,
        invitation_expires_at=None,
    )
    revoked = session.execute(
        update(role_assignment)
        .where(
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.revoked_at.is_(None),
        )
        .values(revoked_at=uow.now, revoked_by=principal.id, revoked_by_kind=principal.kind.value)
        .returning(role_assignment.c.id)
    ).all()
    for (assignment_id,) in sorted(revoked):
        uow.audit(
            action=REVOKE_ASSIGNMENT_ACTION,
            object_type=subjects.ROLE_ASSIGNMENT_OBJECT,
            object_id=assignment_id,
            before={"revoked_at": None},
            after={"revoked_at": uow.now},
            comment=comment,
        )
    # The status change ended what the member had delegated and what was delegated to the member
    # (``_set_status``); the revocations change nobody else's grants, and the sweep after them
    # finds nothing more to end.
    delegations.end_unsupported(uow, cause=delegations.ROLE_ASSIGNMENT_REVOKED)
    ended = _end_workspace_sessions(uow, membership["user_id"])
    uow.audit(
        action=REMOVE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=membership_id,
        before={"status": membership["status"]},
        after={"status": MembershipStatus.REMOVED.value, "removed_at": uow.now},
        comment=comment,
        detail={"sessions_ended": ended, "assignments_revoked": len(revoked)},
    )


def reset_mfa(uow: UnitOfWork, membership_id: UUID, *, reason: str | None) -> None:
    """``POST /users/{id}/reset-mfa``: 403 ``mfa-step-up-required`` without a verification at most
    five minutes old (BR-PLT-06); then the member's factor is disabled, ``MFA_RESET`` is written and
    every session of the user ends, so the member enrols again at the next sign-in.

    D-80: a platform operator's membership answers 404 ``not-found``, and a membership that is
    neither ACTIVE nor SUSPENDED 409 ``invalid-transition``, before any write. The reset is audited
    here and, once committed, in the tenant of each other ACTIVE membership of the user (T-PLT-04).
    """
    principal = uow.principal
    if not mfa.step_up_fresh_at(principal.mfa_verified_at, uow.now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
    session = uow.session
    membership = _lock_membership(session, membership_id)
    user_id = membership["user_id"]
    if session.execute(select(app_user.c.is_operator).where(app_user.c.id == user_id)).scalar_one():
        raise Problem("not-found")
    _another_member(uow, membership)
    require_member_scope(uow, membership_id, action=RESET_MFA_ACTION)
    if membership["status"] not in RESETTABLE:
        raise _transition_refused(NOT_RESETTABLE)
    factor_id = session.execute(
        select(user_mfa_factor.c.id)
        .where(user_mfa_factor.c.user_id == user_id, user_mfa_factor.c.disabled_at.is_(None))
        .with_for_update()
    ).scalar_one_or_none()
    if factor_id is None:
        raise Problem("invalid-transition", NO_FACTOR)
    session.execute(
        update(user_mfa_factor)
        .where(user_mfa_factor.c.id == factor_id)
        .values(disabled_at=uow.now, **_updated(uow))
    )
    end_user_sessions(session, user_id, reason=SessionEndReason.REVOKED, now=uow.now)
    ctx = uow.ctx
    record_security_event(
        session,
        keyring=uow.keyring,
        kind=SecurityEventKind.MFA_RESET,
        outcome=AuditOutcome.SUCCESS,
        request_id=ctx.request_id,
        user_id=user_id,
        tenant_id=principal.tenant_id,
        ip_address=ctx.source_ip,
        user_agent=ctx.user_agent,
        detail={"factor_id": str(factor_id), "reset_by": str(principal.id)},
    )
    uow.audit(
        action=RESET_MFA_ACTION,
        object_type=FACTOR_OBJECT,
        object_id=factor_id,
        before={"disabled_at": None},
        after={"disabled_at": uow.now},
        comment=reason,
        detail={"membership_id": str(membership_id)},
    )
    actor = actor_of(ctx)
    now = uow.now
    keyring = uow.keyring

    def audit_reset_in_active_workspaces() -> None:
        mfa.audit_reset(
            user_id=user_id,
            factor_id=factor_id,
            actor=actor,
            occurred_at=now,
            comment=reason,
            acting_tenant_id=principal.tenant_id,
            keyring=keyring,
            request_id=ctx.request_id,
        )

    uow.after_commit(audit_reset_in_active_workspaces)


def resend_invitation(uow: UnitOfWork, membership_id: UUID) -> None:
    """``POST /users/{membership_id}/resend-invitation`` (API-R-05), a member's command: the
    actor's ``user.manage`` covers every entity of the invitation's roles (T-PLT-10); then the
    invitation is issued again (``issue_invitation_again``)."""
    _lock_membership(uow.session, membership_id)
    require_member_scope(uow, membership_id, action=RESEND_ACTION)
    issue_invitation_again(uow, membership_id)


def issue_invitation_again(
    uow: UnitOfWork, membership_id: UUID, *, detail: Mapping[str, Any] | None = None
) -> None:
    """A new token and email for an open invitation: it expires 7 days from now (T-PLT-07) and
    the earlier link stops working.

    Two commands end here, each under its own rule. A member's ``resend_invitation`` asks for the
    scope of the actor's ``user.manage`` first. The platform operator's command of 04 §14.3 step 5
    (``provisioning.reissue_admin_invitation``: the first Tenant Admin's invitation, which an
    operator created) calls this directly: the operator holds no permission of the workspace, so
    the scope of a member's permission is not a question to put to it — put to it, the one
    command that lets a workspace be entered at all was refused. ``detail`` is the audit event's,
    given by the operator command (channel and OS user)."""
    session = uow.session
    membership = _lock_membership(session, membership_id)
    if membership["status"] != MembershipStatus.INVITED.value:
        raise _transition_refused(NOT_INVITED)
    email = session.execute(
        select(app_user.c.email).where(app_user.c.id == membership["user_id"])
    ).scalar_one()
    invitation = provisioning.invitation_token(uow.keyring)
    digest = sha256_hex(invitation.token)
    expires_at = uow.now + provisioning.INVITATION_LIFETIME
    _set_status(
        uow, membership_id, invitation_token_sha256=digest, invitation_expires_at=expires_at
    )
    _queue_invitation(
        uow,
        membership_id=membership_id,
        email=str(email),
        invitation=invitation,
        expires_at=expires_at,
        dedupe_key=f"invitation:{membership_id}:{digest[:16]}",
    )
    uow.audit(
        action=RESEND_ACTION,
        object_type=OBJECT_TYPE,
        object_id=membership_id,
        before={"invitation_expires_at": membership["invitation_expires_at"]},
        after={"invitation_expires_at": expires_at},
        **({} if detail is None else {"detail": dict(detail)}),
    )


def member_select() -> Select[Any]:
    """The membership columns of API-S-User with the person's email, name and last sign-in: the
    name is the email while ``IDENTITY_WITHHELD`` holds, the last sign-in null while
    ``SIGN_IN_WITHHELD`` does (D-80 rule 5, by the membership's status).

    The members are the workspace's: the statement names the session's tenant, because the
    caller's own memberships of other workspaces are rows a user's transaction reads too
    (``of_session_tenant``; RLS-TM)."""
    return (
        select(
            tenant_membership.c.id,
            tenant_membership.c.user_id,
            tenant_membership.c.status,
            tenant_membership.c.invited_at,
            tenant_membership.c.invitation_expires_at,
            tenant_membership.c.activated_at,
            tenant_membership.c.removed_at,
            tenant_membership.c.created_at,
            tenant_membership.c.updated_at,
            tenant_membership.c.row_version,
            app_user.c.email,
            SHOWN_DISPLAY_NAME,
            SHOWN_LAST_LOGIN.label("last_login_at"),
            IDENTITY_WITHHELD.label("identity_withheld"),
            SIGN_IN_WITHHELD.label("sign_in_withheld"),
        )
        .select_from(tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id))
        .where(of_session_tenant(tenant_membership))
    )


def shown_name(session: Session, membership_id: UUID) -> str:
    """The name this workspace is shown of the person behind ``membership_id`` now
    (``SHOWN_NAME``): what a text written about the member carries — a request's summary."""
    return str(
        session.execute(
            select(SHOWN_NAME)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
            )
            .where(of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id)
        ).scalar_one()
    )


def list_users[P: Page](
    ctx: RequestContext,
    *,
    page: Callable[[Session, Select[Any]], P],
    files: FileStore,
    keyring: KeyRing,
) -> tuple[P, list[dict[str, Any]]]:
    """One page of members with their active and requested roles (SCREENS_B §9.10 grid)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, member_select())
        items = user_outs(session, result.items, with_revoked=False, files=files, keyring=keyring)
        return result, items


def get_user(
    ctx: RequestContext, membership_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    """API-S-User with every role, revoked ones included; 404 ``not-found`` otherwise."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return _one_user(session, membership_id, files=files, keyring=keyring)


def user_out(uow: UnitOfWork, membership_id: UUID) -> dict[str, Any]:
    """API-S-User of a membership the command just changed, in the command's transaction."""
    return _one_user(uow.session, membership_id, files=uow.files, keyring=uow.keyring)


def _one_user(
    session: Session, membership_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    row = (
        session.execute(member_select().where(tenant_membership.c.id == membership_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return user_outs(session, [dict(row)], with_revoked=True, files=files, keyring=keyring)[0]


def pending_proposals(
    session: Session, membership_ids: set[str], *, files: FileStore, keyring: KeyRing
) -> list[tuple[Mapping[str, Any], dict[str, Any]]]:
    """(request, proposal) of each PENDING ``ROLE_ASSIGNMENT`` request of the memberships."""
    requests = (
        session.execute(
            select(approval_request)
            .where(
                approval_request.c.subject_type == ApprovalSubjectType.ROLE_ASSIGNMENT.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.impact_preview_file_id.is_not(None),
            )
            .order_by(approval_request.c.submitted_at, approval_request.c.id)
        )
        .mappings()
        .all()
    )
    found: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
    for request in requests:
        document = preview.read_preview(
            session, request["impact_preview_file_id"], files=files, keyring=keyring
        )
        proposal = dict(document["after"])
        if str(proposal.get("membership_id")) in membership_ids:
            found.append((dict(request), proposal))
    return found


def granting_decisions(
    session: Session, request_ids: Iterable[UUID | None]
) -> dict[Any, Mapping[str, Any]]:
    """The final approving decision of each request, with the rule key of an auto-approval."""
    ids = sorted({value for value in request_ids if value is not None})
    granting: dict[Any, Mapping[str, Any]] = {}
    if not ids:
        return granting
    for approving in session.execute(
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            approval_decision.c.decision,
            rule.c.rule_key,
        )
        .select_from(
            approval_decision.outerjoin(
                rule,
                and_(
                    rule.c.tenant_id == approval_decision.c.tenant_id,
                    rule.c.id == approval_decision.c.auto_rule_id,
                ),
            )
        )
        .where(
            approval_decision.c.approval_request_id.in_(ids),
            approval_decision.c.decision.in_(
                [ApprovalDecisionKind.APPROVE.value, ApprovalDecisionKind.AUTO_APPROVE.value]
            ),
        )
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    ).mappings():
        granting[approving["approval_request_id"]] = dict(approving)  # the final approval wins
    return granting


def is_setup_grant(decision: Mapping[str, Any] | None) -> bool:
    """Whether rule AUTO-BOOTSTRAP approved the grant while setup was incomplete."""
    return (
        decision is not None
        and decision["decision"] == ApprovalDecisionKind.AUTO_APPROVE.value
        and decision["rule_key"] == provisioning.AUTO_BOOTSTRAP
    )


def user_outs(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    with_revoked: bool,
    files: FileStore,
    keyring: KeyRing,
) -> list[dict[str, Any]]:
    """API-S-User of each membership row of ``member_select``: SMAP-14 roles (requested, active
    and, with ``with_revoked``, revoked), who granted each and whether rule AUTO-BOOTSTRAP did."""
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    statement = (
        select(
            role_assignment,
            role.c.code.label("role_code"),
            role.c.name.label("role_name"),
        )
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            )
        )
        .where(role_assignment.c.membership_id.in_(ids))
        .order_by(role.c.code, role_assignment.c.valid_from, role_assignment.c.id)
    )
    if not with_revoked:
        statement = statement.where(role_assignment.c.revoked_at.is_(None))
    assignments = session.execute(statement).mappings().all()
    granting = granting_decisions(session, [row["approval_request_id"] for row in assignments])
    pending = pending_proposals(
        session, {str(value) for value in ids}, files=files, keyring=keyring
    )
    pending_roles = {
        UUID(str(row.id)): row
        for row in session.execute(
            select(role.c.id, role.c.code, role.c.name).where(
                role.c.id.in_(sorted({UUID(str(proposal["role_id"])) for _, proposal in pending}))
            )
        )
    }
    names = display_names(
        session,
        [decision["approver_id"] for decision in granting.values()]
        + [row["revoked_by"] for row in assignments],
    )
    enrolled = set(
        session.scalars(
            select(user_mfa_factor.c.user_id).where(
                user_mfa_factor.c.user_id.in_([row["user_id"] for row in rows]),
                user_mfa_factor.c.disabled_at.is_(None),
                user_mfa_factor.c.confirmed_at.is_not(None),
            )
        )
    )
    entities = entity_scope.names(
        session,
        [value for item in assignments for value in item["entity_ids"] or ()]
        + [value for _, proposal in pending for value in proposal["entity_ids"]],
    )
    roles: dict[Any, list[dict[str, Any]]] = {}
    for item in assignments:
        decision = granting.get(item["approval_request_id"])
        roles.setdefault(item["membership_id"], []).append(
            {
                "assignment_id": item["id"],
                "approval_request_id": item["approval_request_id"],
                "role": {
                    "id": item["role_id"],
                    "code": item["role_code"],
                    "name": item["role_name"],
                },
                "is_all_entities": item["is_all_entities"],
                "entities": entity_scope.refs(entities, item["entity_ids"] or ()),
                "entity_count": len(item["entity_ids"] or ()),
                "status": ACTIVE if item["revoked_at"] is None else REVOKED,
                "granted_at": item["valid_from"],
                "granted_by": None
                if decision is None
                else actor(decision["approver_id"], str(decision["approver_kind"]), names),
                "setup_grant": is_setup_grant(decision),
                "sod_exception_id": item["sod_exception_id"],
                "revoked_at": item["revoked_at"],
                "revoked_by": None
                if item["revoked_by_kind"] is None
                else actor(item["revoked_by"], str(item["revoked_by_kind"]), names),
            }
        )
    for request, proposal in pending:
        requested = pending_roles.get(UUID(str(proposal["role_id"])))
        exception = proposal.get("sod_exception_id")
        roles.setdefault(UUID(str(proposal["membership_id"])), []).append(
            {
                "assignment_id": None,
                "approval_request_id": request["id"],
                "role": {
                    "id": UUID(str(proposal["role_id"])),
                    "code": str(proposal["role_code"]),
                    "name": str(proposal["role_code"])
                    if requested is None
                    else str(requested.name),
                },
                "is_all_entities": bool(proposal["is_all_entities"]),
                "entities": entity_scope.refs(entities, proposal["entity_ids"]),
                "entity_count": len(proposal["entity_ids"]),
                "status": REQUESTED,
                "granted_at": None,
                "granted_by": None,
                "setup_grant": False,
                "sod_exception_id": None if exception is None else UUID(str(exception)),
                "revoked_at": None,
                "revoked_by": None,
            }
        )
    return [
        {
            "id": row["id"],
            "user_id": row["user_id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "status": row["status"],
            "invited_at": row["invited_at"],
            "invitation_expires_at": row["invitation_expires_at"],
            "activated_at": row["activated_at"],
            "removed_at": row["removed_at"],
            "last_login_at": row["last_login_at"],
            "mfa_enrolled": None if row["sign_in_withheld"] else row["user_id"] in enrolled,
            "sign_in_withheld": bool(row["sign_in_withheld"]),
            "roles": roles.get(row["id"], []),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "row_version": row["row_version"],
        }
        for row in rows
    ]
