"""Approval delegations (04 §15.3 API-R-09, T-PLT-21; PRD BR-PLT-07; SCREENS §15.7; REQ-PLT-013;
BUILD_SPEC PLF-16).

A member delegates approval permissions they hold to another ACTIVE member for at most 90 days.
While the delegation is in force and the delegator still holds a permission, the delegate decides
"on behalf of" the delegator (``approvals.engine.find_authority``). The delegator revokes a
delegation, and so does an access administrator. A member lists the delegations they gave and
received; an access administrator lists, beside those, the delegations they may end — every
delegation of the workspace for an administrator of all entities, and for an administrator of
named entities those whose delegator's access lies within their own (item DELEG-LIST-SCOPE-1;
ruling R-28: a list of the workspace is not answered to a holder of named entities).

Giving approval authority away, and taking it back, is access administration (PRD BR-PLT-06,
BR-PLT-07): both commands need an MFA-verified session with a verification at most five minutes
old, as approving does. The commands enforce it themselves, so no caller of them can leave it
out, and a refusal for want of either is audited (ruling R-111 (6)).

The limits of a delegation are the command's too (PRD BR-PLT-07 rev 1.118; rulings R-111 (2) and
(4)): it ends no later than 90 days after the command that creates it; it is given only to a
member with a confirmed second factor, so that it never turns a password-only account into an
approver; and it is checked for separation of duties as a role assignment is — the delegate's
grants and standing delegations with the delegated permissions (``sod.assert_delegation_allowed``).
A delegation whose delegator loses the permission or the membership ends
(``approvals.delegations.end_unsupported``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, exists, insert, not_, or_, select
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope, mfa, sod
from erev_api.auth.permissions import spec as permission_spec
from erev_api.db import new_id
from erev_api.db.session import of_session_tenant, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_delegation,
    role_assignment,
    tenant_membership,
)
from erev_api.db.transitions import apply
from erev_api.domain.platform import users
from erev_api.domain.platform.approval_queries import Page, actor, display_names
from erev_api.enums import MembershipStatus, PrincipalKind
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "approval_delegation"
CREATE_ACTION: Final = "approval_delegation.create"
REVOKE_ACTION: Final = "approval_delegation.revoke"
MAX_DURATION: Final = timedelta(days=90)  # T-PLT-21 CHECK; BR-PLT-07
MIN_REASON_LENGTH: Final = 10  # SCREENS §15.7 "Reason (minimum 10 characters)"
RULE_TABLE: Final = "T-PLT-21"
RULE_DURATION: Final = "BR-PLT-07"
NO_MEMBERSHIP: Final = "Only a workspace member can delegate approvals."
PERMISSION_NOT_APPROVAL: Final = "Choose approval permissions only."
PERMISSION_NOT_HELD: Final = "You can delegate only approval permissions you hold."
PERMISSION_TWICE: Final = "Send each permission once."
DELEGATE_SELF: Final = "Choose another member as the delegate."
DELEGATE_INACTIVE: Final = "Choose an active member of this workspace."
END_BEFORE_START: Final = "The end must be after the start."
DURATION_MESSAGE: Final = "A delegation lasts at most 90 days."  # SCREENS §15.7
REASON_SHORT: Final = "Enter a reason of at least 10 characters."
# PRD BR-PLT-07 rev 1.118: who ends a delegation besides its delegator — the holder of the
# permission that grants and revokes role assignments (API-R-06), for the delegator's entities.
ADMINISTER: Final = "role.manage"
REVOKE_DETAIL: Final = "Only the delegator or an access administrator can end this delegation."
ALREADY_REVOKED: Final = "This delegation is already revoked."
# [J] Copy of the three refusals of rev 1.118, which the documents word here first (SCREENS
# §15.7 rev 1.27 repeats it).
ENDS_MESSAGE: Final = "A delegation ends within 90 days of today."
DELEGATE_NO_FACTOR: Final = "Choose a member who has set up multi-factor authentication."
DELEGATION_BEYOND_SCOPE: Final = (
    "The delegator of this delegation holds access for entities beyond your own. An "
    "administrator whose access covers every entity of the delegator's roles must end it."
)


def _membership_id(principal: Principal) -> UUID:
    if principal.kind is not PrincipalKind.USER or principal.membership_id is None:
        raise Problem("forbidden", NO_MEMBERSHIP)
    return principal.membership_id


def _administering(uow: UnitOfWork, *, action: str, delegation_id: UUID | None) -> UUID:
    """The caller's membership, once the session may administer approval authority (BR-PLT-06,
    BR-PLT-07): a member's session, MFA-verified — 403 ``mfa-required`` otherwise — and verified
    within the last five minutes — 403 ``mfa-step-up-required`` otherwise. Either refusal is
    audited first, as the ``DENIED`` event of ``action`` (ruling R-111 (6); DG-KRN-AUTH-05)."""
    principal = uow.principal
    membership_id = _membership_id(principal)

    def denied(reason: str) -> None:
        audit_writer.record_denied(
            uow.ctx,
            action=action,
            object_type=OBJECT_TYPE,
            object_id=delegation_id,
            permission="",
            detail={"reason": reason},
            keyring=uow.keyring,
        )

    if principal.mfa_verified_at is None:
        enrolled = principal.id is not None and mfa.has_confirmed_factor(
            principal.id, request_id=uow.ctx.request_id
        )
        denied("mfa-required")
        raise Problem(
            "mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED
        )
    if not mfa.step_up_fresh_at(principal.mfa_verified_at, uow.now):
        denied("mfa-step-up-required")
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
    return membership_id


def _is_approval(code: str) -> bool:
    try:
        return permission_spec(code).is_approval
    except KeyError:
        return False


def _within(held: frozenset[UUID]) -> ColumnElement[bool]:
    """The delegations an administrator of the entities ``held`` may end: no role assignment of
    the delegator that is not revoked is for all entities or names an entity beyond ``held`` —
    ``entity_scope.covers`` over ``entity_scope.assigned``, as ``revoke_delegation`` asks it, in
    the list's own statement."""
    beyond = or_(
        role_assignment.c.is_all_entities,
        not_(role_assignment.c.entity_ids.contained_by(sorted(held, key=str))),
    )
    return not_(
        exists().where(
            role_assignment.c.membership_id == approval_delegation.c.delegator_membership_id,
            role_assignment.c.revoked_at.is_(None),
            beyond,
        )
    )


def list_delegations[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the delegations the caller gave or received and, for an access administrator
    (``role.manage``), of those they may end (PRD BR-PLT-07 rev 1.118; DG-LST): every delegation
    of the workspace for an administrator of all entities; for an administrator of named
    entities the ones whose delegator's role assignments name no entity beyond theirs, and
    nothing else (04 T-PLT-21 "Limits and end" rev 1.225; item DELEG-LIST-SCOPE-1 — ruling
    R-28: a holder of named entities is not answered a list of the workspace)."""
    principal = ctx.principal
    membership_id = _membership_id(principal)
    statement = select(approval_delegation)
    held = (
        entity_scope.held_scope(principal, ADMINISTER)
        if ADMINISTER in principal.permissions
        else frozenset()
    )
    if held != "*":
        own = or_(
            approval_delegation.c.delegator_membership_id == membership_id,
            approval_delegation.c.delegate_membership_id == membership_id,
        )
        statement = statement.where(or_(own, _within(held)) if held else own)
    with tenant_session(principal.db_context, read_only=True) as session:
        result = page(session, statement)
        return result, delegation_outs(session, result.items)


def create_delegation(
    uow: UnitOfWork,
    *,
    delegate_membership_id: UUID,
    permissions: Sequence[str],
    valid_from: datetime,
    valid_to: datetime,
    reason: str,
) -> dict[str, Any]:
    """Insert a delegation after collecting every finding (DG-CMD-03); 422 ``validation-failed``.

    The delegator's session is MFA-verified with a fresh step-up (``_administering``). Each
    permission must be an approval permission the delegator holds by role — not one held through
    a delegation — once; the delegate an ACTIVE other member with a confirmed second factor;
    ``valid_to`` after ``valid_from``, at most 90 days later and no later than 90 days from now;
    the reason at least 10 characters. Then the separation of duties, as for a role assignment:
    409 ``sod-conflict`` naming ``permissions[i]`` when the delegate's grants with these
    permissions meet a rule no approved exception covers. Audits ``approval_delegation.create``.
    """
    principal = uow.principal
    membership_id = _administering(uow, action=CREATE_ACTION, delegation_id=None)
    session = uow.session
    errors: list[ProblemError] = []
    seen: set[str] = set()
    for index, code in enumerate(permissions):
        field = f"permissions[{index}]"
        if code in seen:
            errors.append(ProblemError(field=field, rule_id=RULE_TABLE, message=PERMISSION_TWICE))
        elif not _is_approval(code):
            errors.append(
                ProblemError(field=field, rule_id=RULE_TABLE, message=PERMISSION_NOT_APPROVAL)
            )
        elif code not in principal.permissions:
            errors.append(
                ProblemError(field=field, rule_id=RULE_TABLE, message=PERMISSION_NOT_HELD)
            )
        seen.add(code)
    if delegate_membership_id == membership_id:
        errors.append(
            ProblemError(field="delegate_membership_id", rule_id=RULE_TABLE, message=DELEGATE_SELF)
        )
    else:
        # DG-CMD-02: the delegate's membership is locked, so that a grant to the delegate and
        # this delegation are checked for separation of duties one after the other.
        delegate = session.execute(
            select(tenant_membership.c.status, tenant_membership.c.user_id)
            .where(tenant_membership.c.id == delegate_membership_id)
            .with_for_update()
        ).one_or_none()
        if delegate is None or delegate.status != MembershipStatus.ACTIVE.value:
            errors.append(
                ProblemError(
                    field="delegate_membership_id", rule_id=RULE_TABLE, message=DELEGATE_INACTIVE
                )
            )
        elif not mfa.has_confirmed_factor(
            UUID(str(delegate.user_id)), request_id=uow.ctx.request_id
        ):
            # Ruling R-111 (2): a delegation never turns a password-only account into an approver.
            errors.append(
                ProblemError(
                    field="delegate_membership_id",
                    rule_id=RULE_DURATION,
                    message=DELEGATE_NO_FACTOR,
                )
            )
    if valid_to <= valid_from:
        errors.append(ProblemError(field="valid_to", rule_id=RULE_TABLE, message=END_BEFORE_START))
    elif valid_to - valid_from > MAX_DURATION:
        errors.append(
            ProblemError(field="valid_to", rule_id=RULE_DURATION, message=DURATION_MESSAGE)
        )
    elif valid_to > uow.now + MAX_DURATION:
        # T-PLT-21 ``ck_approval_delegation__ends``: 90 days from the command, not from a start
        # of any date.
        errors.append(ProblemError(field="valid_to", rule_id=RULE_DURATION, message=ENDS_MESSAGE))
    if len(reason.strip()) < MIN_REASON_LENGTH:
        errors.append(ProblemError(field="reason", rule_id=RULE_TABLE, message=REASON_SHORT))
    if errors:
        raise Problem("validation-failed", errors=errors)
    sod.assert_delegation_allowed(
        session, delegate_membership_id, list(permissions), at=uow.now, field="permissions"
    )

    delegation_id = new_id()
    session.execute(
        insert(approval_delegation).values(
            tenant_id=principal.tenant_id,
            id=delegation_id,
            delegator_membership_id=membership_id,
            delegate_membership_id=delegate_membership_id,
            permissions=list(permissions),
            valid_from=valid_from,
            valid_to=valid_to,
            reason=reason,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=delegation_id,
        after={
            "delegate_membership_id": str(delegate_membership_id),
            "permissions": list(permissions),
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
        },
        comment=reason,
    )
    return _one(session, delegation_id)


def revoke_delegation(
    uow: UnitOfWork, delegation_id: UUID, *, reason: str | None
) -> dict[str, Any]:
    """The delegator, or an access administrator, ends a delegation now (PRD BR-PLT-07 rev
    1.118; ruling R-111 (4)). Audits ``approval_delegation.revoke``.

    In order: a delegation the caller is no party to and may not administer answers 404
    ``not-found``, as an id that names none; its delegate, who sees it and may not end it, 403
    ``forbidden``; then the MFA-verified session with a fresh step-up (``_administering``); for an
    administrator the scope of ``role.manage`` — every entity the delegator's role assignments
    name (REQ-PLT-012, as a command on the delegator's membership; 403 by name with its
    ``DENIED`` event); a delegation already revoked 409 ``invalid-transition``."""
    principal = uow.principal
    membership_id = _membership_id(principal)
    session = uow.session
    row = (
        session.execute(
            select(approval_delegation)
            .where(approval_delegation.c.id == delegation_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    own = row is not None and row["delegator_membership_id"] == membership_id
    administrator = not own and ADMINISTER in principal.permissions
    if row is None or not (own or administrator or row["delegate_membership_id"] == membership_id):
        raise Problem("not-found")
    if not (own or administrator):
        raise Problem("forbidden", REVOKE_DETAIL)
    _administering(uow, action=REVOKE_ACTION, delegation_id=delegation_id)
    if administrator and not entity_scope.covers(
        entity_scope.held_scope(principal, ADMINISTER),
        entity_scope.assigned(session, UUID(str(row["delegator_membership_id"]))),
    ):
        audit_writer.record_denied(
            uow.ctx,
            action=REVOKE_ACTION,
            object_type=OBJECT_TYPE,
            object_id=delegation_id,
            permission=ADMINISTER,
            detail=users.scope_denial(),
            keyring=uow.keyring,
        )
        raise users.beyond_scope(DELEGATION_BEYOND_SCOPE)
    if row["revoked_at"] is not None:
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(field="revoked_at", rule_id=RULE_TABLE, message=ALREADY_REVOKED)],
        )
    apply(
        session,
        OBJECT_TYPE,
        delegation_id,
        to_status=None,
        set_values={
            "revoked_at": uow.now,
            "revoked_by": principal.id,
            "revoked_by_kind": principal.kind.value,
        },
    )
    uow.audit(
        action=REVOKE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=delegation_id,
        before={"revoked_at": None},
        after={"revoked_at": uow.now.isoformat()},
        comment=reason,
    )
    return _one(session, delegation_id)


def _one(session: Session, delegation_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(
            select(approval_delegation).where(approval_delegation.c.id == delegation_id)
        )
        .mappings()
        .one()
    )
    return delegation_outs(session, [dict(row)])[0]


def delegation_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each delegation with its delegator, delegate, creator and revoker as API-S-Actor. The
    two parties are named as this workspace is shown them (``users.SHOWN_NAME``; dev-guide
    DG-KRN-DB-13): the row of an ENDED delegation shows the email of a party who has been removed
    and whose identity this workspace did not create — the name's expression, never a condition,
    so no party is missing from the read."""
    if not rows:
        return []
    membership_ids = sorted(
        {row["delegator_membership_id"] for row in rows}
        | {row["delegate_membership_id"] for row in rows}
    )
    members: dict[UUID, tuple[UUID, str]] = {
        UUID(str(membership)): (UUID(str(user_id)), str(name))
        for membership, user_id, name in session.execute(
            select(tenant_membership.c.id, app_user.c.id, users.SHOWN_NAME)
            .select_from(
                tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
            )
            .where(of_session_tenant(tenant_membership), tenant_membership.c.id.in_(membership_ids))
        ).tuples()
    }
    names = display_names(
        session, [row["created_by"] for row in rows] + [row["revoked_by"] for row in rows]
    )

    def member(membership_id: UUID) -> dict[str, Any]:
        user_id, name = members[membership_id]
        return {"id": user_id, "kind": PrincipalKind.USER.value, "display_name": name}

    return [
        {
            "id": row["id"],
            "delegator_membership_id": row["delegator_membership_id"],
            "delegator": member(row["delegator_membership_id"]),
            "delegate_membership_id": row["delegate_membership_id"],
            "delegate": member(row["delegate_membership_id"]),
            "permissions": list(row["permissions"]),
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "reason": row["reason"],
            "revoked_at": row["revoked_at"],
            "revoked_by": None
            if row["revoked_by_kind"] is None
            else actor(row["revoked_by"], str(row["revoked_by_kind"]), names),
            "created_at": row["created_at"],
            "created_by": actor(row["created_by"], str(row["created_by_kind"]), names),
        }
        for row in rows
    ]
