"""Separation-of-duties rules and exceptions (04 §15.3 API-R-07, T-PLT-13, T-PLT-14; PRD SM-04
configuration row, SM-13, §2.5 routing row, ERR-22; SCREENS_B §9.10 exception drawer, §9.12;
REQ-PLT-010; BUILD_SPEC PLF-19, BS1-D-24, BS1-D-26, BS1-D-29).

``request_sod_exception`` asks for a ``SOD_EXCEPTION`` approval: a member may hold a combination a
published rule forbids, with a compensating control and a validity of at most 366 days. Approval by
another ``access.approve`` holder sets the exception APPROVED, and the SoD check then accepts the
combination while the exception is in force. ``revoke_sod_exception`` ends an approved exception at
once. ``create_sod_rule_version`` records the next version of a rule as DRAFT, tests and submits it,
and requests a ``ROLE_CHANGE`` approval that publishes it and supersedes the published version.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import Select, and_, func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.auth import permissions as catalogue
from erev_api.db import new_id, transitions
from erev_api.db.session import of_session_tenant, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_request,
    sod_exception,
    sod_rule,
    tenant_membership,
)
from erev_api.domain.platform import provisioning, users
from erev_api.domain.platform.approval_queries import Page, actor, display_names
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ConfigStatus,
    GrantStatus,
    MembershipStatus,
)
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

REQUEST_ACTION: Final = "sod_exception.request"
REVOKE_ACTION: Final = "sod_exception.revoke"
VERSION_ACTION: Final = "sod_rule.create"
MANAGE_PERMISSION: Final = "role.manage"  # 04 API-R-07: every SoD route
RULE_RULE: Final = "T-PLT-13"
RULE_EXCEPTION: Final = "T-PLT-14"
RULE_CONFIG: Final = "SM-04"
MAX_VALIDITY: Final = timedelta(days=366)  # T-PLT-14 ck_sod_exception__validity
OPEN_VERSION_STATUSES: Final = (
    ConfigStatus.DRAFT.value,
    ConfigStatus.TESTED.value,
    ConfigStatus.SUBMITTED.value,
)

# [J] SPEC-Q-184: copy the documents leave open; SCREENS_B §9.10 gives the validity message.
RULE_UNKNOWN: Final = "Choose a published SoD rule."
MEMBER_UNKNOWN: Final = "Choose a member of this workspace."
END_BEFORE_START: Final = "Choose a validity that ends after it starts."
VALIDITY_TOO_LONG: Final = "Choose a validity of at most 366 days."
COMMENT_EMPTY: Final = "Enter a comment."
ALREADY_REQUESTED: Final = "An exception for this member and rule already waits for approval."
NOT_APPROVED: Final = "Only an approved exception can be revoked."
# The comment of the revocation an invitation makes (``end_for_invitation``): the audit trail's.
INVITED_AGAIN: Final = "The member was removed and is invited again."
EXCEPTION_UNUSABLE: Final = "Choose an approved exception of this member that is in force."
EXCEPTION_NOT_NEEDED: Final = "This exception covers no conflict of this role."
PERMISSIONS_EMPTY: Final = "Choose at least one permission."
PERMISSION_UNKNOWN: Final = "Choose permissions from the catalogue."
PERMISSION_TWICE: Final = "Add each permission once."
FUNCTIONS_OVERLAP: Final = "Keep each permission in one function only."
RATIONALE_EMPTY: Final = "Enter a rationale."
VERSION_UNCHANGED: Final = "Change the name, functions or rationale of the rule."
VERSION_OPEN: Final = "Another version of this rule waits for approval."


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _permission_errors(codes: Sequence[str], field: str) -> list[ProblemError]:
    """Every finding on one function's permission list: empty, unknown and repeated codes."""
    if not codes:
        return [ProblemError(field=field, rule_id=RULE_RULE, message=PERMISSIONS_EMPTY)]
    errors: list[ProblemError] = []
    seen: set[str] = set()
    for index, code in enumerate(codes):
        try:
            catalogue.spec(code)
        except KeyError:
            message = PERMISSION_UNKNOWN
        else:
            message = PERMISSION_TWICE if code in seen else ""
        if message:
            errors.append(
                ProblemError(field=f"{field}[{index}]", rule_id=RULE_RULE, message=message)
            )
        seen.add(code)
    return errors


def _member(session: Session, membership_id: UUID) -> Any:
    """The member's status and the name this workspace is shown of the person
    (``users.SHOWN_NAME``; D-80 rule 5): the name goes into the stored summary of a request."""
    return session.execute(
        select(tenant_membership.c.status, users.SHOWN_DISPLAY_NAME)
        .select_from(tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id))
        .where(of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id)
    ).one_or_none()


def request_sod_exception(
    uow: UnitOfWork,
    *,
    sod_rule_code: str,
    membership_id: UUID,
    compensating_control: str,
    valid_from: datetime,
    valid_to: datetime,
    comment: str,
) -> UUID:
    """``POST /sod-exceptions``: the new exception id, REQUESTED under a ``SOD_EXCEPTION`` request.

    422 ``validation-failed`` collects the rule, member, compensating control (at least 10
    characters, SB-R-05), validity (after its start and at most 366 days, T-PLT-14) and comment
    findings; 409 ``invalid-transition`` when an exception of the member and rule already waits.
    An exception is asked for a member the actor's ``role.manage`` covers — every entity of the
    member's role assignments — else 403 ``forbidden`` by name after a DENIED event
    (``users.require_member_scope``; rule T-PLT-10): the refusal comes before the other findings.
    """
    session = uow.session
    errors: list[ProblemError] = []
    published = session.execute(
        select(sod_rule.c.id).where(
            sod_rule.c.code == sod_rule_code, sod_rule.c.status == ConfigStatus.PUBLISHED.value
        )
    ).first()
    if published is None:
        errors.append(ProblemError(field="sod_rule_code", rule_id=RULE_RULE, message=RULE_UNKNOWN))
    member = _member(session, membership_id)
    if member is None or member.status == MembershipStatus.REMOVED.value:
        errors.append(
            ProblemError(field="membership_id", rule_id=RULE_EXCEPTION, message=MEMBER_UNKNOWN)
        )
    else:
        users.require_member_scope(
            uow, membership_id, action=REQUEST_ACTION, permission=MANAGE_PERMISSION
        )
    control = compensating_control.strip()
    if len(control) < users.MIN_REASON_LENGTH:
        errors.append(
            ProblemError(
                field="compensating_control", rule_id=users.RULE_REASON, message=users.REASON_SHORT
            )
        )
    if valid_to <= valid_from:
        errors.append(
            ProblemError(field="valid_to", rule_id=RULE_EXCEPTION, message=END_BEFORE_START)
        )
    elif valid_to - valid_from > MAX_VALIDITY:
        errors.append(
            ProblemError(field="valid_to", rule_id=RULE_EXCEPTION, message=VALIDITY_TOO_LONG)
        )
    text = comment.strip()
    if not text:
        errors.append(ProblemError(field="comment", rule_id=RULE_EXCEPTION, message=COMMENT_EMPTY))
    if errors or member is None:
        raise Problem("validation-failed", errors=errors)

    waiting = session.execute(
        select(sod_exception.c.id).where(
            sod_exception.c.membership_id == membership_id,
            sod_exception.c.sod_rule_code == sod_rule_code,
            sod_exception.c.status == GrantStatus.REQUESTED.value,
        )
    ).first()
    if waiting is not None:
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(
                    field="sod_rule_code", rule_id=users.RULE_LIFECYCLE, message=ALREADY_REQUESTED
                )
            ],
        )

    exception_id = new_id()
    in_force = session.execute(
        select(sod_exception.c.id, sod_exception.c.valid_from, sod_exception.c.valid_to)
        .where(
            sod_exception.c.membership_id == membership_id,
            sod_exception.c.sod_rule_code == sod_rule_code,
            sod_exception.c.status == GrantStatus.APPROVED.value,
        )
        .order_by(sod_exception.c.valid_from, sod_exception.c.id)
    ).all()
    before = {
        "object_type": subjects.SOD_EXCEPTION_OBJECT,
        "membership_id": str(membership_id),
        "sod_rule_code": sod_rule_code,
        "approved_exceptions": [
            {
                "sod_exception_id": str(row.id),
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat(),
            }
            for row in in_force
        ],
    }
    after = subjects.sod_exception_proposal(
        exception_id=exception_id,
        sod_rule_code=sod_rule_code,
        membership_id=membership_id,
        compensating_control=control,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.SOD_EXCEPTION,
        subject_id=exception_id,
        summary=f"Allow {sod_rule_code} for {member.display_name}",
        impact_preview=approvals.ImpactPreview(before=before, after=after),
        comment=text,
    )
    values = {
        "sod_rule_code": sod_rule_code,
        "membership_id": membership_id,
        "compensating_control": control,
        "status": GrantStatus.REQUESTED.value,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "approval_request_id": request["id"],
    }
    session.execute(
        insert(sod_exception).values(
            tenant_id=uow.principal.tenant_id, id=exception_id, **values, **_created(uow)
        )
    )
    uow.audit(
        action=REQUEST_ACTION,
        object_type=subjects.SOD_EXCEPTION_OBJECT,
        object_id=exception_id,
        after=values,
        comment=text,
        approval_request_id=request["id"],
    )
    return exception_id


def revoke_sod_exception(uow: UnitOfWork, exception_id: UUID, *, reason: str | None) -> None:
    """``POST /sod-exceptions/{id}/revoke``: the exception stops covering conflicts now.

    404 ``not-found``; 403 ``forbidden`` by name, after a DENIED event, when the actor's
    ``role.manage`` does not cover the member of the exception (``users.require_member_scope``);
    422 without a reason of at least 10 characters (SB-R-05); 409 ``invalid-transition`` unless
    the exception is APPROVED (PRD SM-13). Role assignments that it covered stay; the SoD report
    lists them as conflicts without an exception.
    """
    session = uow.session
    current = (
        session.execute(
            select(sod_exception.c.status, sod_exception.c.membership_id)
            .where(sod_exception.c.id == exception_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if current is None:
        raise Problem("not-found")
    users.require_member_scope(
        uow,
        UUID(str(current["membership_id"])),
        action=REVOKE_ACTION,
        permission=MANAGE_PERMISSION,
    )
    comment = users.require_reason(reason)
    if current["status"] != GrantStatus.APPROVED.value:
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(field="status", rule_id=users.RULE_LIFECYCLE, message=NOT_APPROVED)
            ],
        )
    _revoke(uow, exception_id, comment=comment)


def _revoke(uow: UnitOfWork, exception_id: UUID, *, comment: str) -> None:
    """APPROVED → REVOKED by the command's actor, with its audit event."""
    principal = uow.principal
    revoked = {
        "revoked_at": uow.now,
        "revoked_by": principal.id,
        "revoked_by_kind": principal.kind.value,
    }
    transitions.apply(
        uow.session,
        subjects.SOD_EXCEPTION_OBJECT,
        exception_id,
        to_status=GrantStatus.REVOKED.value,
        expected_status=GrantStatus.APPROVED.value,
        set_values=revoked,
    )
    uow.audit(
        action=REVOKE_ACTION,
        object_type=subjects.SOD_EXCEPTION_OBJECT,
        object_id=exception_id,
        before={
            "status": GrantStatus.APPROVED.value,
            "revoked_at": None,
            "revoked_by": None,
            "revoked_by_kind": None,
        },
        after={"status": GrantStatus.REVOKED.value, **revoked},
        comment=comment,
    )


def end_for_invitation(uow: UnitOfWork, membership_id: UUID) -> list[UUID]:
    """The exceptions of a REMOVED membership, before its person is invited again (PRD SM-13 rev
    1.201; 04 T-PLT-14 rev 1.293): none passes from the membership's first life into its second.

    An exception was granted to circumstances that ended with the removal. A removal leaves an
    APPROVED one standing, and the SoD check takes whatever is in force as cover without being
    named (``auth.sod``), so each one still in force by its dates — begun or not — is revoked
    here by the inviter, with its audit event. One still REQUESTED hashed "the membership is not
    removed" into its request, which has been stale since the removal: the request is voided
    while it is (DG-KRN-APR-05), and with it the exception; left pending, its hash would match
    again once the membership is INVITED. Returns the revoked ids."""
    session = uow.session
    requested = session.scalars(
        select(sod_exception.c.id)
        .where(
            sod_exception.c.membership_id == membership_id,
            sod_exception.c.status == GrantStatus.REQUESTED.value,
        )
        .order_by(sod_exception.c.id)
    ).all()
    for exception_id in requested:
        approvals.void_if_stale(
            uow,
            subject_type=ApprovalSubjectType.SOD_EXCEPTION,
            subject_id=UUID(str(exception_id)),
        )
    in_force = session.scalars(
        select(sod_exception.c.id)
        .where(
            sod_exception.c.membership_id == membership_id,
            sod_exception.c.status == GrantStatus.APPROVED.value,
            sod_exception.c.revoked_at.is_(None),
            sod_exception.c.valid_to > uow.now,
        )
        .order_by(sod_exception.c.id)
        .with_for_update()
    ).all()
    revoked = [UUID(str(exception_id)) for exception_id in in_force]
    for exception_id in revoked:
        _revoke(uow, exception_id, comment=INVITED_AGAIN)
    return revoked


def exception_rule_in_force(
    session: Session, exception_id: UUID, membership_id: UUID, *, at: datetime
) -> str | None:
    """The rule code of an APPROVED, unrevoked exception of the membership whose validity holds
    ``at``; None otherwise."""
    value = session.execute(
        select(sod_exception.c.sod_rule_code).where(
            sod_exception.c.id == exception_id,
            sod_exception.c.membership_id == membership_id,
            sod_exception.c.status == GrantStatus.APPROVED.value,
            sod_exception.c.revoked_at.is_(None),
            sod_exception.c.valid_from <= at,
            sod_exception.c.valid_to > at,
        )
    ).scalar_one_or_none()
    return None if value is None else str(value)


def _rule_content_sha256(
    *, code: str, name: str, function_a: Sequence[str], function_b: Sequence[str], rationale: str
) -> str:
    """SC-V ``content_sha256`` of a rule version, in the shape of the seeded versions."""
    return sha256_hex(
        {
            "code": code,
            "function_a_permissions": sorted(function_a),
            "function_b_permissions": sorted(function_b),
            "name": name,
            "rationale": rationale,
        }
    )


def create_sod_rule_version(
    uow: UnitOfWork,
    code: str,
    *,
    name: str,
    function_a_permissions: Sequence[str],
    function_b_permissions: Sequence[str],
    rationale: str,
    comment: str | None,
) -> UUID:
    """``POST /sod-rules/{code}/versions``: the next version of a rule under approval (BS1-D-29).

    The version is inserted DRAFT, tested (DRAFT → TESTED with its content hash) and submitted
    (TESTED → SUBMITTED) in this command, because API-R-07 catalogues no separate test or submit
    route (SPEC-Q-184). 404 ``not-found`` for an unknown code; 409 ``invalid-transition`` while
    another version of the code is DRAFT, TESTED or SUBMITTED; 422 for the name, functions and
    rationale, and for a version equal to the published one. Audits ``sod_rule.create``.
    """
    session = uow.session
    principal = uow.principal
    latest = session.execute(
        select(func.max(sod_rule.c.version_no)).where(sod_rule.c.code == code)
    ).scalar_one_or_none()
    if latest is None:
        raise Problem("not-found")
    open_version = session.execute(
        select(sod_rule.c.id).where(
            sod_rule.c.code == code, sod_rule.c.status.in_(OPEN_VERSION_STATUSES)
        )
    ).first()
    if open_version is not None:
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(field="code", rule_id=RULE_CONFIG, message=VERSION_OPEN)],
        )
    errors: list[ProblemError] = []
    label = name.strip()
    if len(label) not in provisioning.LABEL_LENGTH:
        errors.append(ProblemError(field="name", rule_id=RULE_RULE, message=users.NAME_LENGTH))
    function_a = list(function_a_permissions)
    function_b = list(function_b_permissions)
    errors += _permission_errors(function_a, "function_a_permissions")
    errors += _permission_errors(function_b, "function_b_permissions")
    if not errors and set(function_a) & set(function_b):
        errors.append(
            ProblemError(
                field="function_b_permissions", rule_id=RULE_RULE, message=FUNCTIONS_OVERLAP
            )
        )
    text = rationale.strip()
    if not text:
        errors.append(ProblemError(field="rationale", rule_id=RULE_RULE, message=RATIONALE_EMPTY))
    published = (
        session.execute(
            select(sod_rule).where(
                sod_rule.c.code == code, sod_rule.c.status == ConfigStatus.PUBLISHED.value
            )
        )
        .mappings()
        .one_or_none()
    )
    digest = _rule_content_sha256(
        code=code, name=label, function_a=function_a, function_b=function_b, rationale=text
    )
    if not errors and published is not None and published["content_sha256"] == digest:
        errors.append(ProblemError(rule_id=RULE_CONFIG, message=VERSION_UNCHANGED))
    if errors:
        raise Problem("validation-failed", errors=errors)

    version_id = new_id()
    version_no = int(latest) + 1
    content = {
        "code": code,
        "name": label,
        "function_a_permissions": sorted(function_a),
        "function_b_permissions": sorted(function_b),
        "rationale": text,
    }
    stamp = {"updated_by": principal.id, "updated_by_kind": principal.kind.value}
    where = sod_rule.c.id == version_id
    session.execute(
        insert(sod_rule).values(
            tenant_id=principal.tenant_id,
            id=version_id,
            **content,
            **_created(uow),
            updated_at=uow.now,
            **stamp,
            version_no=version_no,
            status=ConfigStatus.DRAFT.value,
            supersedes_version_id=None if published is None else published["id"],
        )
    )
    session.execute(
        update(sod_rule)
        .where(where)
        .values(status=ConfigStatus.TESTED.value, content_sha256=digest, **stamp)
    )
    session.execute(update(sod_rule).where(where).values(status=ConfigStatus.SUBMITTED.value))
    uow.audit(
        action=VERSION_ACTION,
        object_type=subjects.SOD_RULE_OBJECT,
        object_id=version_id,
        after={
            **content,
            "version_no": version_no,
            "status": ConfigStatus.SUBMITTED.value,
            "content_sha256": digest,
            "supersedes_version_id": None if published is None else published["id"],
        },
        detail={
            "lifecycle": [
                ConfigStatus.DRAFT.value,
                ConfigStatus.TESTED.value,
                ConfigStatus.SUBMITTED.value,
            ]
        },
        comment=comment,
    )
    before: dict[str, Any] = {"object_type": subjects.SOD_RULE_OBJECT, "code": code}
    if published is not None:
        before |= {
            "sod_rule_id": str(published["id"]),
            "version_no": int(published["version_no"]),
            "name": str(published["name"]),
            "function_a_permissions": sorted(published["function_a_permissions"]),
            "function_b_permissions": sorted(published["function_b_permissions"]),
            "rationale": str(published["rationale"]),
        }
    approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.ROLE_CHANGE,
        subject_id=version_id,
        summary=f"Publish version {version_no} of SoD rule {code}",
        impact_preview=approvals.ImpactPreview(
            before=before,
            after=subjects.sod_rule_proposal(
                version_id=version_id,
                code=code,
                version_no=version_no,
                name=label,
                function_a_permissions=function_a,
                function_b_permissions=function_b,
                rationale=text,
            ),
        ),
        comment=comment,
    )
    return version_id


def list_sod_rules[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of SoD rule versions with their pending approval request."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(sod_rule))
        return result, rule_outs(session, result.items)


def rule_out(uow: UnitOfWork, version_id: UUID) -> dict[str, Any]:
    """API-S-SodRule of a version the command just wrote, in the command's transaction."""
    row = uow.session.execute(select(sod_rule).where(sod_rule.c.id == version_id)).mappings().one()
    return rule_outs(uow.session, [dict(row)])[0]


def rule_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-SodRule of each ``sod_rule`` row: the T-PLT-13 and SC-V columns and the id of its
    pending ``ROLE_CHANGE`` request."""
    if not rows:
        return []
    pending = {
        subject_id: request_id
        for subject_id, request_id in session.execute(
            select(approval_request.c.subject_id, approval_request.c.id).where(
                approval_request.c.subject_type == ApprovalSubjectType.ROLE_CHANGE.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.subject_id.in_([row["id"] for row in rows]),
            )
        ).tuples()
    }
    return [
        {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "function_a_permissions": sorted(row["function_a_permissions"]),
            "function_b_permissions": sorted(row["function_b_permissions"]),
            "rationale": row["rationale"],
            "version_no": row["version_no"],
            "status": row["status"],
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
            "content_sha256": row["content_sha256"],
            "approval_request_id": row["approval_request_id"],
            "pending_approval_request_id": pending.get(row["id"]),
            "published_at": row["published_at"],
            "published_by": row["published_by"],
            "supersedes_version_id": row["supersedes_version_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "row_version": row["row_version"],
        }
        for row in rows
    ]


def exception_select() -> Select[Any]:
    """The ``sod_exception`` columns with the member's name, as this workspace is shown the
    person (``users.SHOWN_NAME``; D-80 rule 5)."""
    return select(sod_exception, users.SHOWN_NAME.label("member_name")).select_from(
        sod_exception.join(
            tenant_membership,
            and_(
                tenant_membership.c.tenant_id == sod_exception.c.tenant_id,
                tenant_membership.c.id == sod_exception.c.membership_id,
            ),
        ).join(app_user, app_user.c.id == tenant_membership.c.user_id)
    )


def list_sod_exceptions[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of SoD exceptions in every status."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, exception_select())
        return result, exception_outs(session, result.items)


def exception_out(uow: UnitOfWork, exception_id: UUID) -> dict[str, Any]:
    """API-S-SodException of an exception, in the command's transaction."""
    row = (
        uow.session.execute(exception_select().where(sod_exception.c.id == exception_id))
        .mappings()
        .one()
    )
    return exception_outs(uow.session, [dict(row)])[0]


def exception_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-SodException of each row of ``exception_select``: the T-PLT-14 columns, the member's
    name and who requested and revoked it."""
    names = display_names(
        session, [row["created_by"] for row in rows] + [row["revoked_by"] for row in rows]
    )
    return [
        {
            "id": row["id"],
            "sod_rule_code": row["sod_rule_code"],
            "membership_id": row["membership_id"],
            "member_name": row["member_name"],
            "compensating_control": row["compensating_control"],
            "status": row["status"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "approval_request_id": row["approval_request_id"],
            "approved_at": row["approved_at"],
            "revoked_at": row["revoked_at"],
            "revoked_by": None
            if row["revoked_by_kind"] is None
            else actor(row["revoked_by"], str(row["revoked_by_kind"]), names),
            "created_at": row["created_at"],
            "created_by": actor(row["created_by"], str(row["created_by_kind"]), names),
        }
        for row in rows
    ]
