"""Support grants (04 T-PLT-33, §15.3 API-R-14; 05 SAR-29, TB-7, THR-20, SCH-15; PRD NTF-12, §2.5
routing row ``SUPPORT_GRANT``; SCREENS_B §9.14 SF-14:support-access; REQ-PLT-036; BUILD_SPEC
PLF-26, BS1-D-27).

``request_support_grant`` asks for read-only operator access to a workspace for at most 72 hours:
a REQUESTED grant under a ``SUPPORT_GRANT`` approval routed to ``support_grant.approve``, and
NTF-12 for every Tenant Admin. An operator asks through ``erev support-grant request``
(``request_as_operator``, principal kind ``OPERATOR``); ``POST /support-grants`` records a request
on an operator's behalf. Approval by another holder sets the grant APPROVED, and the operator may
then open the workspace (``auth.operators``). ``revoke_support_grant`` ends an approved grant and
its operator sessions at once; ``expire_due`` (SCH-15) sets EXPIRED on approved grants past
``valid_to`` and ends their sessions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, insert, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.auth import sessions
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import Clock
from erev_api.db import new_id, transitions
from erev_api.db.session import DbContext, platform_session, tenant_session
from erev_api.db.tables import app_user, support_grant, tenant
from erev_api.domain.platform import users
from erev_api.domain.platform.approval_queries import Page, actor, display_names
from erev_api.enums import (
    ApprovalSubjectType,
    GrantStatus,
    NotificationKind,
    PrincipalKind,
    TenantKind,
    UserStatus,
)
from erev_api.events import notifications
from erev_api.files.store import FileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.problems import Problem, ProblemError
from erev_api.uow import unit_of_work

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

REQUEST_ACTION: Final = "support_grant.request"
REVOKE_ACTION: Final = "support_grant.revoke"
EXPIRE_ACTION: Final = "support_grant.expire"
RULE_GRANT: Final = "T-PLT-33"
READ_ONLY_SCOPE: Final = "READ_ONLY"
MAX_VALIDITY: Final = timedelta(hours=72)  # T-PLT-33 ck_support_grant__validity; THR-20
TICKET_LENGTH: Final = 128
ADMIN_ROLE: Final = "tenant_admin"
EXPIRY_REQUEST_ID: Final = "support-grant-expiry"
CLI_LOCALE: Final = "en-US"

# PRD NTF-12; SCREENS_B §9.14 names the scope "read-only".
NOTIFICATION_TITLE: Final = "Support access requested"
NOTIFICATION_BODY: Final = "{operator} requests {scope} access from {start} to {end} UTC."
SCOPE_COPY: Final = "read-only"
# [J] SPEC-Q-191: copy the documents leave open.
OPERATOR_UNKNOWN: Final = "Choose a platform operator."
TENANT_UNKNOWN: Final = "Choose an existing workspace."
TICKET_TOO_LONG: Final = "Use at most 128 characters."
END_BEFORE_START: Final = "Choose a validity that ends after it starts."
VALIDITY_TOO_LONG: Final = "Choose a validity of at most 72 hours."
ALREADY_ENDED: Final = "Choose a validity that ends in the future."
NOT_APPROVED: Final = "Only approved support access can be revoked."


@dataclass(frozen=True, slots=True)
class OperatorRequest:
    """The flags of ``erev support-grant request`` (BS1-D-27)."""

    tenant_code: str
    operator_email: str
    reason: str
    ticket_ref: str | None
    valid_from: datetime
    valid_to: datetime


def _utc(instant: datetime) -> str:
    return f"{instant.astimezone(UTC):%d %b %Y %H:%M}"


def _operator(session: Session, email: str) -> Any:
    return session.execute(
        select(app_user.c.id, app_user.c.display_name).where(
            app_user.c.email == sessions.normalise_email(email),
            app_user.c.is_operator.is_(True),
            app_user.c.status == UserStatus.ACTIVE.value,
        )
    ).one_or_none()


def request_support_grant(
    uow: UnitOfWork,
    *,
    operator_email: str,
    reason: str,
    ticket_ref: str | None,
    valid_from: datetime,
    valid_to: datetime,
) -> UUID:
    """A REQUESTED grant under a ``SUPPORT_GRANT`` request; returns its id.

    422 ``validation-failed`` collects the operator (an ACTIVE ``app_user`` with ``is_operator``),
    the reason (at least 10 characters, SB-R-05), the ticket (at most 128 characters) and the
    validity (after its start, at most 72 hours, ending in the future). Audits
    ``support_grant.request`` and notifies every Tenant Admin but the requester (NTF-12).
    """
    session = uow.session
    principal = uow.principal
    errors: list[ProblemError] = []
    operator = _operator(session, operator_email)
    if operator is None:
        errors.append(
            ProblemError(field="operator_email", rule_id=RULE_GRANT, message=OPERATOR_UNKNOWN)
        )
    text = reason.strip()
    if len(text) < users.MIN_REASON_LENGTH:
        errors.append(
            ProblemError(field="reason", rule_id=users.RULE_REASON, message=users.REASON_SHORT)
        )
    ticket = (ticket_ref or "").strip() or None
    if ticket is not None and len(ticket) > TICKET_LENGTH:
        errors.append(ProblemError(field="ticket_ref", rule_id=RULE_GRANT, message=TICKET_TOO_LONG))
    if valid_to <= valid_from:
        errors.append(ProblemError(field="valid_to", rule_id=RULE_GRANT, message=END_BEFORE_START))
    elif valid_to - valid_from > MAX_VALIDITY:
        errors.append(ProblemError(field="valid_to", rule_id=RULE_GRANT, message=VALIDITY_TOO_LONG))
    elif valid_to <= uow.now:
        errors.append(ProblemError(field="valid_to", rule_id=RULE_GRANT, message=ALREADY_ENDED))
    if errors or operator is None:
        raise Problem("validation-failed", errors=errors)

    grant_id = new_id()
    operator_id = UUID(str(operator.id))
    approved = session.execute(
        select(support_grant.c.id, support_grant.c.valid_from, support_grant.c.valid_to)
        .where(
            support_grant.c.operator_user_id == operator_id,
            support_grant.c.status == GrantStatus.APPROVED.value,
            support_grant.c.valid_to > uow.now,
        )
        .order_by(support_grant.c.valid_from, support_grant.c.id)
    ).all()
    before = {
        "object_type": subjects.SUPPORT_GRANT_OBJECT,
        "operator_user_id": str(operator_id),
        "approved_grants": [
            {
                "support_grant_id": str(row.id),
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat(),
            }
            for row in approved
        ],
    }
    after = subjects.support_grant_proposal(
        grant_id=grant_id,
        operator_user_id=operator_id,
        reason=text,
        ticket_ref=ticket,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.SUPPORT_GRANT,
        subject_id=grant_id,
        summary=f"Support access for {operator.display_name}",
        impact_preview=approvals.ImpactPreview(before=before, after=after),
        comment=text,
    )
    values = {
        "operator_user_id": operator_id,
        "scope": READ_ONLY_SCOPE,
        "reason": text,
        "ticket_ref": ticket,
        "status": GrantStatus.REQUESTED.value,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "approval_request_id": request["id"],
    }
    session.execute(
        insert(support_grant).values(
            tenant_id=principal.tenant_id,
            id=grant_id,
            **values,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=REQUEST_ACTION,
        object_type=subjects.SUPPORT_GRANT_OBJECT,
        object_id=grant_id,
        after=values,
        approval_request_id=request["id"],
    )
    # an operator's access reaches every entity: the Tenant Admins of all entities (NTF-12)
    admins = notifications.role_holders(
        session, role_codes=[ADMIN_ROLE], entity_id=None, at=uow.now
    )
    notifications.notify(
        uow,
        recipient_membership_ids=[admin for admin in admins if admin != principal.membership_id],
        kind=NotificationKind.SUPPORT_GRANT_REQUESTED,
        title=NOTIFICATION_TITLE,
        body=NOTIFICATION_BODY.format(
            operator=operator.display_name,
            scope=SCOPE_COPY,
            start=_utc(valid_from),
            end=_utc(valid_to),
        ),
        link_path=subjects.SUPPORT_GRANT_LINK,
        subject_type=subjects.SUPPORT_GRANT_OBJECT,
        subject_id=grant_id,
    )
    return grant_id


def request_as_operator(
    request: OperatorRequest, *, request_id: str, clock: Clock, keyring: KeyRing, files: FileStore
) -> dict[str, Any]:
    """``erev support-grant request``: ``request_support_grant`` in the tenant of ``tenant_code``
    as principal kind ``OPERATOR``; returns API-S-SupportGrant. 422 for an unknown tenant code.

    The principal is built here: no permission of the workspace, no session, every entity,
    ``auth_method`` ``"system"``. It prepares the grant's ``SUPPORT_GRANT`` request, and the
    approvals kernel asks a preparer whether she reads the subject in full — by permission, of
    which this one holds none. So the kernel asks this principal's entity scope, as it asks
    SYSTEM's (``approvals.asked_by_entity_scope``; 04 §16.10 rev 1.321): its kind, its
    ``auth_method`` and that it holds no permission are what that predicate reads, and
    ``tests/domain/platform/test_support_grants.py`` runs the command."""
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=keyring
    ) as db:
        found = db.execute(
            select(tenant.c.id, tenant.c.kind).where(tenant.c.code == request.tenant_code)
        ).one_or_none()
    if found is None:
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="tenant", rule_id=RULE_GRANT, message=TENANT_UNKNOWN)],
        )
    tenant_id = UUID(str(found.id))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
        operator = _operator(db, request.operator_email)
    principal = Principal(
        kind=PrincipalKind.OPERATOR,
        id=None if operator is None else UUID(str(operator.id)),
        tenant_id=tenant_id,
        membership_id=None,
        display_name=request.operator_email if operator is None else str(operator.display_name),
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind(found.kind),
        request_id=request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale=CLI_LOCALE,
    )
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        grant_id = request_support_grant(
            uow,
            operator_email=request.operator_email,
            reason=request.reason,
            ticket_ref=request.ticket_ref,
            valid_from=request.valid_from,
            valid_to=request.valid_to,
        )
        out = grant_out(uow.session, grant_id)
        uow.commit()
    return out


def revoke_support_grant(uow: UnitOfWork, grant_id: UUID, *, reason: str | None) -> None:
    """``POST /support-grants/{id}/revoke``: the grant ends now, and so do its operator sessions.

    404 ``not-found``; 422 without a reason of at least 10 characters (SB-R-05); 409
    ``invalid-transition`` unless the grant is APPROVED. Audits ``support_grant.revoke``.
    """
    session = uow.session
    principal = uow.principal
    current = session.execute(
        select(support_grant.c.status).where(support_grant.c.id == grant_id).with_for_update()
    ).scalar_one_or_none()
    if current is None:
        raise Problem("not-found")
    comment = users.require_reason(reason)
    if current != GrantStatus.APPROVED.value:
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(field="status", rule_id=RULE_GRANT, message=NOT_APPROVED)],
        )
    revoked = {
        "revoked_at": uow.now,
        "revoked_by": principal.id,
        "revoked_by_kind": principal.kind.value,
    }
    transitions.apply(
        session,
        subjects.SUPPORT_GRANT_OBJECT,
        grant_id,
        to_status=GrantStatus.REVOKED.value,
        expected_status=GrantStatus.APPROVED.value,
        set_values=revoked,
    )
    sessions.end_support_grant_sessions(session, grant_id, now=uow.now)
    uow.audit(
        action=REVOKE_ACTION,
        object_type=subjects.SUPPORT_GRANT_OBJECT,
        object_id=grant_id,
        before={
            "status": GrantStatus.APPROVED.value,
            "revoked_at": None,
            "revoked_by": None,
            "revoked_by_kind": None,
        },
        after={"status": GrantStatus.REVOKED.value, **revoked},
        comment=comment,
    )


def expire_due(runtime: JobRuntime, *, request_id: str = EXPIRY_REQUEST_ID) -> int:
    """SCH-15: APPROVED grants whose ``valid_to`` has passed become EXPIRED and their operator
    sessions end ``REVOKED``, one SYSTEM unit of work per tenant; returns the number expired."""
    now = runtime.clock.now()
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=runtime.keyring
    ) as db:
        tenant_ids = [
            UUID(str(value)) for value in db.scalars(select(tenant.c.id).order_by(tenant.c.id))
        ]
    expired = 0
    for tenant_id in tenant_ids:
        principal = system_principal(tenant_id)
        with tenant_session(principal.db_context, read_only=True) as db:
            due = [
                UUID(str(value))
                for value in db.scalars(
                    select(support_grant.c.id)
                    .where(
                        support_grant.c.status == GrantStatus.APPROVED.value,
                        support_grant.c.valid_to <= now,
                    )
                    .order_by(support_grant.c.id)
                )
            ]
        if not due:
            continue
        with system_unit_of_work(runtime, principal, request_id=request_id) as uow:
            for grant_id in due:
                transitions.apply(
                    uow.session,
                    subjects.SUPPORT_GRANT_OBJECT,
                    grant_id,
                    to_status=GrantStatus.EXPIRED.value,
                    expected_status=GrantStatus.APPROVED.value,
                    set_values={},
                )
                sessions.end_support_grant_sessions(uow.session, grant_id, now=uow.now)
                uow.audit(
                    action=EXPIRE_ACTION,
                    object_type=subjects.SUPPORT_GRANT_OBJECT,
                    object_id=grant_id,
                    before={"status": GrantStatus.APPROVED.value},
                    after={"status": GrantStatus.EXPIRED.value},
                )
            uow.commit()
        expired += len(due)
    return expired


def list_support_grants[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of support grants in every status."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(support_grant))
        return result, grant_outs(session, result.items)


def grant_out(session: Session, grant_id: UUID) -> dict[str, Any]:
    """API-S-SupportGrant of one grant."""
    row = (
        session.execute(select(support_grant).where(support_grant.c.id == grant_id))
        .mappings()
        .one()
    )
    return grant_outs(session, [dict(row)])[0]


def grant_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-SupportGrant of each ``support_grant`` row: the T-PLT-33 columns with the operator,
    requester and revoker as API-S-Actor."""
    names = display_names(
        session,
        [row["operator_user_id"] for row in rows]
        + [row["created_by"] for row in rows]
        + [row["revoked_by"] for row in rows],
    )
    return [
        {
            "id": row["id"],
            "operator": actor(row["operator_user_id"], PrincipalKind.OPERATOR.value, names),
            "scope": row["scope"],
            "reason": row["reason"],
            "ticket_ref": row["ticket_ref"],
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
