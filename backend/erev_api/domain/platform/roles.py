"""Roles, permissions and role assignments (04 §15.3 API-R-06, T-PLT-09 to T-PLT-12, SMAP-14; PRD
SM-04 configuration row, SM-13, §2.5 routing row, ERR-22; SCREENS_B §9.10 role bindings, §9.11;
REQ-PLT-008 to REQ-PLT-010; BUILD_SPEC PLF-18, BS1-D-24, BS1-D-31).

``create_role`` inserts an inactive custom role without permissions and requests a ``ROLE_CHANGE``;
its approval grants the proposed permissions and activates the role. ``propose_role_change``
requests another permission list for a custom role, and system roles never change. A list that
would give a holder of the role an SoD combination without an exception is refused when proposed
and again at approval. ``assign_role`` requests one ``ROLE_ASSIGNMENT`` after the SoD check, for
all entities or for named entity codes (``erev_api.auth.entity_scope``; REQ-PLT-012; supervisor
ruling R-63 (e)), and may name the approved SoD exception that covers the combination
(BUILD_SPEC PLF-19).
``revoke_role_assignment`` ends an assignment at once.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, and_, func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import delegations, preview, subjects
from erev_api.approvals import engine as approvals
from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope, sod
from erev_api.auth import permissions as catalogue
from erev_api.db import new_id
from erev_api.db.session import of_session_tenant, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_request,
    permission,
    role,
    role_assignment,
    role_permission,
    tenant_membership,
)
from erev_api.domain.platform import provisioning, users
from erev_api.domain.platform import sod as sod_exceptions
from erev_api.domain.platform.approval_queries import Page, actor, display_names
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType, MembershipStatus
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

CREATE_ACTION: Final = "role.create"
# API-R-06: the permission a role assignment is requested under (the grantor's own scope).
GRANT_PERMISSION: Final = "role.manage"
RULE_ROLE: Final = "T-PLT-09"
RULE_PERMISSION: Final = "T-PLT-12"
# TY-06 bounds the length; SCREENS_B §9.11 asks for lowercase letters and underscores.
CODE_PATTERN: Final = re.compile(r"[a-z][a-z_]{0,127}")

# [J] SPEC-Q-183: copy the documents leave open; SCREENS_B §9.11 gives the code help text.
CODE_FORMAT: Final = "Use lowercase letters and underscores."
CODE_TAKEN: Final = "Another role of this workspace uses this code."
PERMISSIONS_EMPTY: Final = "Choose at least one permission."
PERMISSION_UNKNOWN: Final = "Choose permissions from the catalogue."
PERMISSION_TWICE: Final = "Add each permission once."
PERMISSIONS_UNCHANGED: Final = "Change at least one permission."
MEMBER_UNKNOWN: Final = "Choose a member of this workspace."
ALREADY_HELD: Final = "This member already holds this role."
ALREADY_REQUESTED: Final = "This role already waits for approval for this member."
ALREADY_REVOKED: Final = "This role assignment is already revoked."
SELF_REVOKE: Final = "Another administrator must revoke your own roles."
ASSIGNMENT_BEYOND_SCOPE: Final = (
    "This role assignment covers entities beyond your own access. An administrator whose access "
    "covers every entity it names must change it."
)


# Supervisor ruling R-115 (c): a change of a role's definition is a tenant-wide act — the role is
# held, or may be held, for every entity — so it needs `role.manage` for all entities.
DEFINITION_BEYOND_SCOPE: Final = (
    "A role's definition applies to every entity. Your own access covers named entities only; an "
    "administrator of all entities must make this change."
)


def require_all_entities(uow: UnitOfWork, *, action: str, role_id: UUID | None = None) -> None:
    """403 ``forbidden`` by name (rule ``T-PLT-10``) unless the actor holds ``role.manage`` for all
    entities: the guard of the role-definition commands. ``action`` is the command's audit action,
    under which the refusal is recorded (DG-KRN-AUTH-05)."""
    if not entity_scope.holds_all(uow.principal, GRANT_PERMISSION):
        audit_writer.record_denied(
            uow.ctx,
            action=action,
            object_type=subjects.ROLE_OBJECT,
            object_id=role_id,
            permission=GRANT_PERMISSION,
            detail=users.scope_denial(all_entities=True),
            keyring=uow.keyring,
        )
        raise users.beyond_scope(DEFINITION_BEYOND_SCOPE)


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


def _permission_errors(codes: Sequence[str]) -> list[ProblemError]:
    """Every finding on a permission list: empty, unknown codes and repeated codes."""
    if not codes:
        return [
            ProblemError(field="permissions", rule_id=RULE_PERMISSION, message=PERMISSIONS_EMPTY)
        ]
    errors: list[ProblemError] = []
    seen: set[str] = set()
    for index, code in enumerate(codes):
        field = f"permissions[{index}]"
        try:
            catalogue.spec(code)
        except KeyError:
            errors.append(
                ProblemError(field=field, rule_id=RULE_PERMISSION, message=PERMISSION_UNKNOWN)
            )
        else:
            if code in seen:
                errors.append(
                    ProblemError(field=field, rule_id=RULE_PERMISSION, message=PERMISSION_TWICE)
                )
        seen.add(code)
    return errors


def _held(session: Session, role_id: UUID) -> list[str]:
    return sorted(
        str(code)
        for code in session.scalars(
            select(role_permission.c.permission_code).where(role_permission.c.role_id == role_id)
        )
    )


def _request_change(
    uow: UnitOfWork,
    *,
    role_id: UUID,
    code: str,
    held: Sequence[str],
    is_active: bool,
    permissions: Sequence[str],
    summary: str,
    comment: str | None,
) -> Mapping[str, Any]:
    """Submit one ``ROLE_CHANGE`` request (BS1-D-24): the proposed permissions are the preview's
    ``after`` and the role's current permissions its ``before``."""
    before = {
        "object_type": subjects.ROLE_OBJECT,
        "role_id": str(role_id),
        "role_code": code,
        "permissions": sorted(held),
        "is_active": is_active,
    }
    after = subjects.role_change_proposal(role_id=role_id, role_code=code, permissions=permissions)
    return approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.ROLE_CHANGE,
        subject_id=role_id,
        summary=summary,
        impact_preview=approvals.ImpactPreview(before=before, after=after),
        comment=comment,
    )


def create_role(
    uow: UnitOfWork,
    *,
    code: str,
    name: str,
    description: str | None,
    permissions: Sequence[str],
) -> UUID:
    """``POST /roles``: the new role id after collecting every finding (DG-CMD-03).

    403 ``forbidden`` by name for an actor whose ``role.manage`` covers named entities only (a
    role's definition is tenant-wide; ruling R-115 (c)); 422 ``validation-failed`` for the code,
    name and permissions. Audits ``role.create``; the request audits its submission and, once
    approved, ``role.change``.
    """
    require_all_entities(uow, action=CREATE_ACTION)
    session = uow.session
    errors: list[ProblemError] = []
    if not CODE_PATTERN.fullmatch(code):
        errors.append(ProblemError(field="code", rule_id=RULE_ROLE, message=CODE_FORMAT))
    elif session.execute(select(role.c.id).where(role.c.code == code)).first() is not None:
        errors.append(ProblemError(field="code", rule_id=RULE_ROLE, message=CODE_TAKEN))
    label = name.strip()
    if len(label) not in provisioning.LABEL_LENGTH:
        errors.append(ProblemError(field="name", rule_id=RULE_ROLE, message=users.NAME_LENGTH))
    errors += _permission_errors(permissions)
    if errors:
        raise Problem("validation-failed", errors=errors)

    role_id = new_id()
    empty = catalogue.role_content_sha256(())
    text = (description or "").strip() or None
    session.execute(
        insert(role).values(
            tenant_id=uow.principal.tenant_id,
            id=role_id,
            code=code,
            name=label,
            description=text,
            is_system=False,
            is_active=False,
            content_sha256=empty,
            **_created(uow),
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=subjects.ROLE_OBJECT,
        object_id=role_id,
        after={
            "code": code,
            "name": label,
            "description": text,
            "is_system": False,
            "is_active": False,
            "content_sha256": empty,
        },
    )
    _request_change(
        uow,
        role_id=role_id,
        code=code,
        held=(),
        is_active=False,
        permissions=permissions,
        summary=f"Add the custom role {label}",
        comment=None,
    )
    return role_id


def propose_role_change(
    uow: UnitOfWork,
    role_id: UUID,
    *,
    permissions: Sequence[str],
    comment: str | None,
    check_version: Callable[[int], None],
) -> Mapping[str, Any]:
    """``POST /roles/{id}/propose-change``: request another permission list for a custom role.

    403 ``forbidden`` by name for an actor whose ``role.manage`` covers named entities only
    (ruling R-115 (c)); 404 ``not-found``; 409 ``invalid-transition`` for a system role
    (BS1-D-31) or a role with a pending change; ``check_version`` applies ``If-Match``; 422 for
    the list; 409 ``sod-conflict`` when a holder of the role would meet an uncovered rule.
    """
    require_all_entities(uow, action=approvals.SUBMIT_ACTION, role_id=role_id)
    session = uow.session
    current = (
        session.execute(select(role).where(role.c.id == role_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if current is None:
        raise Problem("not-found")
    if current["is_system"]:
        raise Problem("invalid-transition", subjects.SYSTEM_ROLE_DETAIL)
    check_version(int(current["row_version"]))
    held = _held(session, role_id)
    errors = _permission_errors(permissions)
    if not errors and sorted(permissions) == held:
        errors.append(
            ProblemError(
                field="permissions", rule_id=RULE_PERMISSION, message=PERMISSIONS_UNCHANGED
            )
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    sod.assert_role_change_allowed(session, role_id, permissions, at=uow.now)
    return _request_change(
        uow,
        role_id=role_id,
        code=str(current["code"]),
        held=held,
        is_active=bool(current["is_active"]),
        permissions=permissions,
        summary=f"Change the permissions of {current['name']}",
        comment=comment,
    )


def assign_role(
    uow: UnitOfWork,
    *,
    membership_id: UUID,
    role_id: UUID,
    is_all_entities: bool,
    entity_codes: Sequence[str],
    sod_exception_id: UUID | None = None,
) -> Mapping[str, Any]:
    """``POST /role-assignments``: one ``ROLE_ASSIGNMENT`` request; returns the request row.

    422 for the member, the role and the entity scope (``entity_scope.resolve``: the shape, codes
    that name no legal entity, a scope beyond the grantor's own), and for a named exception that
    is not an APPROVED exception
    of the member in force now or covers no conflict of the combination (T-PLT-14); 409
    ``invalid-transition`` when the role already waits for approval for the member; 409
    ``sod-conflict`` naming every uncovered rule (REQ-PLT-010, CTL-034). Nothing is written before
    these checks pass.
    """
    session = uow.session
    errors: list[ProblemError] = []
    member = session.execute(
        select(tenant_membership.c.status).where(
            of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id
        )
    ).one_or_none()
    if member is None or member.status == MembershipStatus.REMOVED.value:
        errors.append(
            ProblemError(
                field="membership_id", rule_id=users.RULE_ASSIGNMENT, message=MEMBER_UNKNOWN
            )
        )
    granted = session.execute(
        select(role.c.code, role.c.name, role.c.is_active).where(role.c.id == role_id)
    ).one_or_none()
    if granted is None or not granted.is_active:
        errors.append(
            ProblemError(field="role_id", rule_id=users.RULE_ASSIGNMENT, message=users.ROLE_UNKNOWN)
        )
    elif (
        session.execute(
            select(role_assignment.c.id).where(
                role_assignment.c.membership_id == membership_id,
                role_assignment.c.role_id == role_id,
                role_assignment.c.revoked_at.is_(None),
            )
        ).first()
        is not None
    ):
        errors.append(
            ProblemError(field="role_id", rule_id=users.RULE_ASSIGNMENT, message=ALREADY_HELD)
        )
    held = entity_scope.held_scope(uow.principal, GRANT_PERMISSION)
    scope, findings = entity_scope.resolve(
        session,
        held=held,
        is_all_entities=is_all_entities,
        entity_codes=entity_codes,
        field="entity_codes",
        shape_field="is_all_entities",
    )
    errors += findings
    if entity_scope.reaches_beyond(
        held, is_all_entities=is_all_entities, entity_codes=entity_codes, scope=scope
    ):
        # The request asked for more than the grantor's own access: recorded as a denial of the
        # assignment for that member, whatever else is wrong with it. The answer stays the 422.
        audit_writer.record_denied(
            uow.ctx,
            action=subjects.ROLE_ASSIGNMENT_CREATE,
            object_type=subjects.ROLE_ASSIGNMENT_OBJECT,
            object_id=None,
            permission=GRANT_PERMISSION,
            detail={
                **users.scope_denial(all_entities=is_all_entities),
                "membership_id": str(membership_id),
            },
            keyring=uow.keyring,
        )
    exception_rule: str | None = None
    if sod_exception_id is not None:
        exception_rule = sod_exceptions.exception_rule_in_force(
            session, sod_exception_id, membership_id, at=uow.now
        )
        if exception_rule is None:
            errors.append(
                ProblemError(
                    field="sod_exception_id",
                    rule_id=sod_exceptions.RULE_EXCEPTION,
                    message=sod_exceptions.EXCEPTION_UNUSABLE,
                )
            )
    if errors or member is None or granted is None or scope is None:
        raise Problem("validation-failed", errors=errors)

    pending = users.pending_proposals(
        session, {str(membership_id)}, files=uow.files, keyring=uow.keyring
    )
    if any(str(proposal.get("role_id")) == str(role_id) for _, proposal in pending):
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    field="role_id", rule_id=users.RULE_LIFECYCLE, message=ALREADY_REQUESTED
                )
            ],
        )
    if exception_rule is not None and exception_rule not in {
        conflict.rule_code
        for conflict in sod.conflicts_for(
            session, membership_id, adding_role_ids=(role_id,), at=uow.now
        )
    }:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="sod_exception_id",
                    rule_id=sod_exceptions.RULE_EXCEPTION,
                    message=sod_exceptions.EXCEPTION_NOT_NEEDED,
                )
            ],
        )
    sod.assert_assignment_allowed(session, membership_id, role_id, at=uow.now)
    return users.request_role_assignment(
        uow,
        membership_id=membership_id,
        role_id=role_id,
        role_code=str(granted.code),
        role_name=str(granted.name),
        scope=scope,
        sod_exception_id=sod_exception_id,
    )


def revoke_role_assignment(uow: UnitOfWork, assignment_id: UUID, *, reason: str | None) -> None:
    """``POST /role-assignments/{id}/revoke``: the assignment ends now; the row stays as history.

    404 ``not-found``; 403 ``forbidden`` for one's own assignment, and by name (rule ``T-PLT-10``)
    when the actor's ``role.manage`` does not cover every entity the assignment names — all
    entities for an all-entities assignment (REQ-PLT-012); 422 without a reason of at least 10
    characters (SB-R-05); 409 ``invalid-transition`` when already revoked.
    """
    session = uow.session
    principal = uow.principal
    current = (
        session.execute(
            select(role_assignment).where(role_assignment.c.id == assignment_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if current is None:
        raise Problem("not-found")
    if current["membership_id"] == principal.membership_id:
        raise Problem("forbidden", SELF_REVOKE)
    held = entity_scope.held_scope(principal, GRANT_PERMISSION)
    if not entity_scope.covers(
        held, [(bool(current["is_all_entities"]), current["entity_ids"] or ())]
    ):
        audit_writer.record_denied(
            uow.ctx,
            action=users.REVOKE_ASSIGNMENT_ACTION,
            object_type=subjects.ROLE_ASSIGNMENT_OBJECT,
            object_id=assignment_id,
            permission=GRANT_PERMISSION,
            detail=users.scope_denial(),
            keyring=uow.keyring,
        )
        raise users.beyond_scope(ASSIGNMENT_BEYOND_SCOPE)
    comment = users.require_reason(reason)
    if current["revoked_at"] is not None:
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(field="status", rule_id=users.RULE_LIFECYCLE, message=ALREADY_REVOKED)
            ],
        )
    session.execute(
        update(role_assignment)
        .where(role_assignment.c.id == assignment_id)
        .values(revoked_at=uow.now, revoked_by=principal.id, revoked_by_kind=principal.kind.value)
    )
    uow.audit(
        action=users.REVOKE_ASSIGNMENT_ACTION,
        object_type=subjects.ROLE_ASSIGNMENT_OBJECT,
        object_id=assignment_id,
        before={"revoked_at": None, "revoked_by": None, "revoked_by_kind": None},
        after={
            "revoked_at": uow.now,
            "revoked_by": principal.id,
            "revoked_by_kind": principal.kind.value,
        },
        comment=comment,
    )
    # PRD BR-PLT-07: a delegation this member gave of a permission the role carried ends with it.
    delegations.end_unsupported(uow, cause=delegations.ROLE_ASSIGNMENT_REVOKED)


def list_permissions(ctx: RequestContext) -> list[dict[str, Any]]:
    """The T-PLT-11 catalogue by code."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return [
            dict(row)
            for row in session.execute(select(permission).order_by(permission.c.code)).mappings()
        ]


def list_roles[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of roles with their permissions, member counts and pending change."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(role))
        return result, role_outs(session, result.items)


def get_role(ctx: RequestContext, role_id: UUID) -> dict[str, Any]:
    """API-S-Role; 404 ``not-found`` otherwise."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return _one_role(session, role_id)


def role_out(uow: UnitOfWork, role_id: UUID) -> dict[str, Any]:
    """API-S-Role of a role the command just changed, in the command's transaction."""
    return _one_role(uow.session, role_id)


def _one_role(session: Session, role_id: UUID) -> dict[str, Any]:
    row = session.execute(select(role).where(role.c.id == role_id)).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return role_outs(session, [dict(row)])[0]


def role_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-Role of each ``role`` row: sorted permission codes, the number of members holding the
    role and the id of its pending ``ROLE_CHANGE`` request."""
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    granted: dict[Any, list[str]] = {}
    for role_id, code in session.execute(
        select(role_permission.c.role_id, role_permission.c.permission_code)
        .where(role_permission.c.role_id.in_(ids))
        .order_by(role_permission.c.permission_code)
    ).tuples():
        granted.setdefault(role_id, []).append(str(code))
    members = {
        role_id: int(count)
        for role_id, count in session.execute(
            select(
                role_assignment.c.role_id,
                func.count(func.distinct(role_assignment.c.membership_id)),
            )
            .where(role_assignment.c.role_id.in_(ids), role_assignment.c.revoked_at.is_(None))
            .group_by(role_assignment.c.role_id)
        ).tuples()
    }
    pending = {
        subject_id: request_id
        for subject_id, request_id in session.execute(
            select(approval_request.c.subject_id, approval_request.c.id).where(
                approval_request.c.subject_type == ApprovalSubjectType.ROLE_CHANGE.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.subject_id.in_(ids),
            )
        ).tuples()
    }
    return [
        {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "is_system": row["is_system"],
            "is_active": row["is_active"],
            "content_sha256": row["content_sha256"],
            "permissions": granted.get(row["id"], []),
            "member_count": members.get(row["id"], 0),
            "pending_approval_request_id": pending.get(row["id"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "row_version": row["row_version"],
        }
        for row in rows
    ]


def assignment_select() -> Select[Any]:
    """The ``role_assignment`` columns with the role's code and name and the member's name — the
    name this workspace is shown of the person (``users.SHOWN_NAME``; D-80 rule 5): an assignment
    can stand on a membership whose invitation is not accepted yet."""
    return select(
        role_assignment,
        role.c.code.label("role_code"),
        role.c.name.label("role_name"),
        users.SHOWN_NAME.label("member_name"),
    ).select_from(
        role_assignment.join(
            role,
            and_(
                role.c.tenant_id == role_assignment.c.tenant_id,
                role.c.id == role_assignment.c.role_id,
            ),
        )
        .join(
            tenant_membership,
            and_(
                tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
                tenant_membership.c.id == role_assignment.c.membership_id,
            ),
        )
        .join(app_user, app_user.c.id == tenant_membership.c.user_id)
    )


def list_role_assignments[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of active and revoked role assignments."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, assignment_select())
        return result, assignment_outs(session, result.items)


def assignment_out(uow: UnitOfWork, assignment_id: UUID) -> dict[str, Any]:
    """API-S-RoleAssignment of a row, in the command's transaction; 404 ``not-found`` otherwise."""
    row = (
        uow.session.execute(assignment_select().where(role_assignment.c.id == assignment_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return assignment_outs(uow.session, [dict(row)])[0]


def assignment_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-RoleAssignment of each row of ``assignment_select`` (SMAP-14 active or revoked), with
    who granted it and whether rule AUTO-BOOTSTRAP did."""
    decisions = users.granting_decisions(session, [row["approval_request_id"] for row in rows])
    names = display_names(
        session,
        [decision["approver_id"] for decision in decisions.values()]
        + [row["revoked_by"] for row in rows],
    )
    entities = entity_scope.names(
        session, [value for row in rows for value in row["entity_ids"] or ()]
    )
    outs: list[dict[str, Any]] = []
    for row in rows:
        decision = decisions.get(row["approval_request_id"])
        outs.append(
            {
                "id": row["id"],
                "membership_id": row["membership_id"],
                "member_name": row["member_name"],
                "role": {"id": row["role_id"], "code": row["role_code"], "name": row["role_name"]},
                "is_all_entities": row["is_all_entities"],
                "entities": entity_scope.refs(entities, row["entity_ids"] or ()),
                "entity_count": len(row["entity_ids"] or ()),
                "status": users.ACTIVE if row["revoked_at"] is None else users.REVOKED,
                "approval_request_id": row["approval_request_id"],
                "valid_from": row["valid_from"],
                "valid_to": row["valid_to"],
                "granted_by": None
                if decision is None
                else actor(decision["approver_id"], str(decision["approver_kind"]), names),
                "setup_grant": users.is_setup_grant(decision),
                "sod_exception_id": row["sod_exception_id"],
                "revoked_at": row["revoked_at"],
                "revoked_by": None
                if row["revoked_by_kind"] is None
                else actor(row["revoked_by"], str(row["revoked_by_kind"]), names),
            }
        )
    return outs


def requested_assignment_out(uow: UnitOfWork, request: Mapping[str, Any]) -> dict[str, Any]:
    """The assignment a ``ROLE_ASSIGNMENT`` request stands for: the row once approved, otherwise
    the proposal as ``REQUESTED`` with the id the row will take."""
    if request["status"] == ApprovalRequestStatus.APPROVED.value:
        return assignment_out(uow, request["subject_id"])
    session = uow.session
    proposal = preview.request_proposal(uow, request["id"])
    membership_id = UUID(str(proposal["membership_id"]))
    role_id = UUID(str(proposal["role_id"]))
    granted = session.execute(select(role.c.code, role.c.name).where(role.c.id == role_id)).one()
    exception = proposal.get("sod_exception_id")
    return {
        "id": request["subject_id"],
        "membership_id": membership_id,
        "member_name": users.shown_name(session, membership_id),
        "role": {"id": role_id, "code": str(granted.code), "name": str(granted.name)},
        "is_all_entities": bool(proposal["is_all_entities"]),
        "entities": entity_scope.refs(
            entity_scope.names(session, proposal["entity_ids"]), proposal["entity_ids"]
        ),
        "entity_count": len(proposal["entity_ids"]),
        "status": users.REQUESTED,
        "approval_request_id": request["id"],
        "valid_from": None,
        "valid_to": None,
        "granted_by": None,
        "setup_grant": False,
        "sod_exception_id": None if exception is None else UUID(str(exception)),
        "revoked_at": None,
        "revoked_by": None,
    }
