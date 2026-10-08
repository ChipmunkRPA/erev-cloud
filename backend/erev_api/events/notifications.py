"""Notifications KRN-EVT (dev-guide §5.11 DG-KRN-EVT-06; 04 T-PLT-24, T-PLT-25; 05 NTR-01 to
NTR-04; PRD §5.4 NTF-01 to NTF-12, NTF-R1 to NTF-R3; REQ-PLT-021).

``notify`` inserts one in-app row per ACTIVE recipient membership in the transaction of its cause,
and enqueues topic ``EMAIL`` for each recipient whose preference asks for email. A notification of
the same kind and subject that the recipient received within 10 minutes absorbs a new one, so
nothing is written (NTF-R1). A membership without stored preferences gets the PRD §5.4 defaults,
and ``CHAIN_VERIFICATION_FAILED`` is always delivered in the app and by email (NTF-R2). The email
names the recipient and carries the title and a link, never the body, which may show amounts
(NTF-R3, NTR-04). ``notify_permission_holders`` notifies the ACTIVE memberships whose role
assignments in force grant a permission for the entity, plus the active delegates of those holders
(NTF-01). ``role_holders`` names the recipients a notification addresses by role — the holders
whose assignments cover the event's entity, or all entities for an event of the whole workspace
such as NTF-09's, for its Tenant Admins and Controllers (05 NTR-02 rev 1.180).

A sandbox reaches no external system (05 SBX-08 rev 1.116, NTR-04; item SBX-EMAIL-1): a
notification raised in a sandbox is delivered in the app only. ``notify`` enqueues no ``EMAIL``
there, whatever the preference says and for the mandatory kind as for every other.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, Join, Uuid, and_, any_, insert, literal, or_, select
from sqlalchemy.orm import Session

from erev_api.db import new_id
from erev_api.db.session import of_session_tenant
from erev_api.db.tables import (
    app_user,
    approval_delegation,
    notification,
    notification_preference,
    role,
    role_assignment,
    role_permission,
    tenant_membership,
)
from erev_api.enums import MembershipStatus, NotificationKind, OutboxTopic, TenantKind
from erev_api.events import outbox

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# PRD §5.4 "Email default" column, which 04 T-PLT-25 seeds.
EMAIL_DEFAULTS: Final[Mapping[NotificationKind, bool]] = MappingProxyType(
    {
        NotificationKind.APPROVAL_ASSIGNED: True,
        NotificationKind.APPROVAL_UNASSIGNED: True,
        NotificationKind.ITEM_REJECTED: True,
        NotificationKind.APPROVAL_VOIDED: True,
        NotificationKind.JOB_FAILED: True,
        NotificationKind.CLOSE_BLOCKER_RAISED: False,
        NotificationKind.CHAIN_VERIFICATION_FAILED: True,
        NotificationKind.EXPORT_FAILED: True,
        NotificationKind.EXCEPTION_ASSIGNED: False,
        NotificationKind.SUPPORT_GRANT_REQUESTED: True,
        NotificationKind.ITEM_APPROVED: False,
        NotificationKind.PERIOD_LOCKED: False,
        NotificationKind.PERIOD_REOPENED: True,
    }
)
# PRD NTF-R2: NTF-09 cannot be turned off (04 ck_notification_preference__mandatory).
MANDATORY_KINDS: Final = frozenset({NotificationKind.CHAIN_VERIFICATION_FAILED})
MERGE_WINDOW: Final = timedelta(minutes=10)
TITLE_LENGTH: Final = 400  # erev.label (TY-07)
BODY_LENGTH: Final = 4000  # erev.memo
AGGREGATE_TYPE: Final = "notification"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def email_text(recipient_name: str, title: str, *, has_link: bool) -> str:
    """NTR-04: the recipient's name, the title and a pointer to the link; no amounts."""
    closing = "Open it in eRev:" if has_link else "Sign in to eRev to see it."
    return f"Hello {recipient_name},\n\n{title}\n\n{closing}"


def _merged(
    session: Session,
    *,
    membership_id: UUID,
    kind: NotificationKind,
    subject_type: str | None,
    subject_id: UUID | None,
    title: str,
    now: datetime,
) -> bool:
    """Whether the recipient has an identical notification from the last 10 minutes (NTF-R1).
    Without a subject, identical means the same title."""
    conditions = [
        notification.c.recipient_membership_id == membership_id,
        notification.c.kind == kind.value,
        notification.c.created_at > now - MERGE_WINDOW,
        notification.c.subject_type.is_not_distinct_from(subject_type),
        notification.c.subject_id.is_not_distinct_from(subject_id),
    ]
    if subject_id is None:
        conditions.append(notification.c.title == title)
    exists = select(notification.c.id).where(*conditions).exists()
    return bool(session.execute(select(exists)).scalar_one())


def notify(
    uow: UnitOfWork,
    *,
    recipient_membership_ids: Sequence[UUID],
    kind: NotificationKind,
    title: str,
    body: str | None = None,
    link_path: str | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
) -> None:
    """Notify each ACTIVE membership once, in the app and by email as its preferences say; in a
    sandbox in the app only (05 SBX-08)."""
    kind = NotificationKind(kind)
    wanted = sorted(set(recipient_membership_ids))
    if not wanted:
        return
    session = uow.session
    principal = uow.principal
    title = _clip(title, TITLE_LENGTH)
    recipients = session.execute(
        select(tenant_membership.c.id, app_user.c.email, app_user.c.display_name)
        .select_from(tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id))
        .where(
            of_session_tenant(tenant_membership),
            tenant_membership.c.id.in_(wanted),
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(tenant_membership.c.id)
    ).all()
    stored = session.execute(
        select(
            notification_preference.c.membership_id,
            notification_preference.c.in_app,
            notification_preference.c.email,
        ).where(
            notification_preference.c.membership_id.in_(wanted),
            notification_preference.c.kind == kind.value,
        )
    ).all()
    preferences = {
        UUID(str(row.membership_id)): (bool(row.in_app), bool(row.email)) for row in stored
    }
    in_app_only = uow.ctx.tenant_kind is TenantKind.SANDBOX
    for recipient in recipients:
        membership_id = UUID(str(recipient.id))
        in_app, email = preferences.get(membership_id, (True, EMAIL_DEFAULTS[kind]))
        if kind in MANDATORY_KINDS:
            in_app = email = True
        if in_app_only:
            email = False
        if _merged(
            session,
            membership_id=membership_id,
            kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            title=title,
            now=uow.now,
        ):
            continue
        notification_id = new_id()
        if in_app:
            session.execute(
                insert(notification).values(
                    tenant_id=principal.tenant_id,
                    id=notification_id,
                    recipient_membership_id=membership_id,
                    kind=kind.value,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    title=title,
                    body=None if body is None else _clip(body, BODY_LENGTH),
                    link_path=link_path,
                    created_at=uow.now,
                    created_by=principal.id,
                    created_by_kind=principal.kind.value,
                )
            )
        if email:
            outbox.enqueue(
                uow,
                topic=OutboxTopic.EMAIL,
                aggregate_type=AGGREGATE_TYPE,
                aggregate_id=notification_id,
                dedupe_key=f"{AGGREGATE_TYPE}:{notification_id}",
                payload={
                    "to": str(recipient.email),
                    "subject": title,
                    "text": email_text(
                        str(recipient.display_name), title, has_link=link_path is not None
                    ),
                    "link_path": link_path,
                    "reference": str(notification_id),
                    "notification_id": str(notification_id) if in_app else None,
                },
            )


def _assignments_in_force(at: datetime) -> tuple[Join, list[ColumnElement[bool]]]:
    """Role assignments joined to their active role and ACTIVE membership, in force at ``at``."""
    joined = role_assignment.join(
        role,
        and_(
            role.c.tenant_id == role_assignment.c.tenant_id,
            role.c.id == role_assignment.c.role_id,
        ),
    ).join(
        tenant_membership,
        and_(
            tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
            tenant_membership.c.id == role_assignment.c.membership_id,
        ),
    )
    conditions = [
        role_assignment.c.revoked_at.is_(None),
        role_assignment.c.valid_from <= at,
        or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
        role.c.is_active.is_(True),
        tenant_membership.c.status == MembershipStatus.ACTIVE.value,
    ]
    return joined, conditions


def role_holders(
    session: Session, *, role_codes: Sequence[str], entity_id: UUID | None, at: datetime
) -> list[UUID]:
    """ACTIVE memberships that hold a role of ``role_codes`` through an assignment in force at
    ``at`` whose scope covers the event; sorted.

    ``entity_id`` is the event's scope and every caller states it (PRD §5.4 "with the entity in
    scope"; 05 NTR-02; supervisor's ruling of 2026-10-01, item NOTIFY-ROLE-HOLDERS-SCOPE-1). An
    entity's event — a lock, a reopen, a monitor's item, a failed export of its batch — is
    covered by an assignment for all entities or one that names the entity, so a member who
    holds the role for several entities, this one among them, is told. An event of the whole
    workspace — the chain's failed verification, an operator's request for access — is ``None``
    and is covered by an assignment for all entities alone. Measured before: the reader took no
    scope, and the Controller, the Revenue Reviewer and the Auditor of one entity alone were
    told of another entity's lock and reopen."""
    joined, conditions = _assignments_in_force(at)
    covers: ColumnElement[bool] = role_assignment.c.is_all_entities.is_(True)
    if entity_id is not None:
        covers = or_(covers, literal(entity_id, Uuid()) == any_(role_assignment.c.entity_ids))
    statement = (
        select(role_assignment.c.membership_id)
        .select_from(joined)
        .where(role.c.code.in_(sorted(role_codes)), covers, *conditions)
        .distinct()
    )
    return sorted({UUID(str(value)) for value in session.scalars(statement)})


def _covering(
    scopes: Mapping[Any, tuple[bool, set[UUID]]], entity_ids: Collection[UUID], all_entities: bool
) -> list[Any]:
    """The keys of ``scopes`` — (an all-entities assignment exists, the union of the scoped
    assignments' entities) — that cover every entity of a subject: an all-entities assignment
    always does; a scoped union does when the subject names entities and holds them all, and
    whenever the subject is tenant-level. A subject that spans every entity needs the former."""
    wanted = set(entity_ids)
    return [
        key
        for key, (wide, entities) in scopes.items()
        if wide or (not all_entities and wanted <= entities)
    ]


def role_codes_of(
    session: Session,
    *,
    membership_ids: Sequence[UUID],
    at: datetime,
    entity_ids: Collection[UUID] = (),
    all_entities: bool = False,
) -> dict[UUID, frozenset[str]]:
    """The role codes each of ``membership_ids`` holds through an ACTIVE membership and
    assignments in force at ``at`` that cover every entity of ``entity_ids`` (every entity of the
    tenant when ``all_entities``); without either, every role the membership holds. A membership
    without one maps to the empty set (BUILD_SPEC CLO-7 / CTL-018: the approvals engine reads the
    roles of a step's approvers; 04 T-PLT-18 rev 1.104: for the subject's entities)."""
    wanted = sorted(set(membership_ids))
    held: dict[UUID, set[str]] = {membership_id: set() for membership_id in wanted}
    if not wanted:
        return {}
    joined, conditions = _assignments_in_force(at)
    rows = session.execute(
        select(
            role_assignment.c.membership_id,
            role.c.code,
            role_assignment.c.is_all_entities,
            role_assignment.c.entity_ids,
        )
        .select_from(joined)
        .where(role_assignment.c.membership_id.in_(wanted), *conditions)
    ).all()
    scopes: dict[tuple[UUID, str], tuple[bool, set[UUID]]] = {}
    for membership_id, code, is_all, assigned in rows:
        key = (UUID(str(membership_id)), str(code))
        wide, entities = scopes.get(key, (False, set()))
        scopes[key] = (
            wide or bool(is_all),
            entities | {UUID(str(value)) for value in assigned or ()},
        )
    for membership_id, code in _covering(scopes, entity_ids, all_entities):
        held[membership_id].add(code)
    return {membership_id: frozenset(codes) for membership_id, codes in held.items()}


def permission_holders_direct(
    session: Session,
    *,
    permission: str,
    entity_ids: Collection[UUID],
    all_entities: bool,
    at: datetime,
) -> set[UUID]:
    """ACTIVE memberships whose OWN assignments in force at ``at`` grant ``permission`` for EVERY
    entity of ``entity_ids`` (for every entity of the tenant when ``all_entities``): the people
    who can decide a step in person. No delegate is among them."""
    joined, conditions = _assignments_in_force(at)
    rows = session.execute(
        select(
            role_assignment.c.membership_id,
            role_assignment.c.is_all_entities,
            role_assignment.c.entity_ids,
        )
        .select_from(
            joined.join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
        )
        .where(role_permission.c.permission_code == permission, *conditions)
    ).all()
    return set(_covering(_scopes(rows), entity_ids, all_entities))


def _scopes(rows: Iterable[Any]) -> dict[UUID, tuple[bool, set[UUID]]]:
    """Membership → (an all-entities assignment exists, the union of the scoped assignments'
    entities) over rows of (membership id, ``is_all_entities``, ``entity_ids``)."""
    scopes: dict[UUID, tuple[bool, set[UUID]]] = {}
    for membership_id, is_all, assigned in rows:
        key = UUID(str(membership_id))
        wide, entities = scopes.get(key, (False, set()))
        scopes[key] = (
            wide or bool(is_all),
            entities | {UUID(str(value)) for value in assigned or ()},
        )
    return scopes


def entity_scope_covering(
    session: Session,
    *,
    membership_ids: Collection[UUID],
    entity_ids: Collection[UUID],
    all_entities: bool,
    at: datetime,
    readers: Collection[str] | Literal["*"] | None = None,
) -> set[UUID]:
    """The memberships of ``membership_ids`` that themselves read a subject bound to
    ``entity_ids`` (every entity of the tenant when ``all_entities``) in full. A delegation
    conveys a permission, not the view (R-41 (1)): a delegate decides, is listed and is notified
    only for what it may itself read. A tenant-level subject names no entity, so every membership
    covers it — one without any assignment too (``engine.own_scope_covers``).

    ``readers`` are the permissions that read the subject (04 §16.10 rev 1.319 "Who reads a
    subject in full"; ``approvals.readers``): the membership's OWN assignments in force at
    ``at`` grant ONE of them for every entity — scopes of several permissions are never added
    up. ``"*"`` is the subject no read permission names: the entities of every permission the
    membership holds, added up. None asks the membership's entity scope instead — the union of
    every assignment in force, whatever the role — as every caller did until that revision: it
    stays for an event that is no approval subject (``permission_holders``)."""
    wanted = sorted(set(membership_ids))
    if not wanted:
        return set()
    if not all_entities and not entity_ids:
        return set(wanted)
    joined, conditions = _assignments_in_force(at)
    if readers is None:
        rows = session.execute(
            select(
                role_assignment.c.membership_id,
                role_assignment.c.is_all_entities,
                role_assignment.c.entity_ids,
            )
            .select_from(joined)
            .where(role_assignment.c.membership_id.in_(wanted), *conditions)
        ).all()
        return set(_covering(_scopes(rows), entity_ids, all_entities))
    statement = (
        select(
            role_assignment.c.membership_id,
            role_permission.c.permission_code,
            role_assignment.c.is_all_entities,
            role_assignment.c.entity_ids,
        )
        .select_from(
            joined.join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
        )
        .where(role_assignment.c.membership_id.in_(wanted), *conditions)
    )
    if not isinstance(readers, str):
        statement = statement.where(role_permission.c.permission_code.in_(sorted(set(readers))))
    # (membership, permission) → its scope: ONE permission covers every entity. For ``"*"`` the
    # permissions are one key, so their entities add up.
    scopes: dict[tuple[UUID, str], tuple[bool, set[UUID]]] = {}
    for membership_id, code, is_all, assigned in session.execute(statement):
        key = (UUID(str(membership_id)), "*" if isinstance(readers, str) else str(code))
        wide, entities = scopes.get(key, (False, set()))
        scopes[key] = (
            wide or bool(is_all),
            entities | {UUID(str(value)) for value in assigned or ()},
        )
    return {membership_id for membership_id, _ in _covering(scopes, entity_ids, all_entities)}


def permission_holders_covering(
    session: Session,
    *,
    permission: str,
    entity_ids: Collection[UUID],
    all_entities: bool,
    at: datetime,
    barred: Collection[UUID] = (),
    readers: Collection[str] | Literal["*"] | None = None,
) -> list[UUID]:
    """The ACTIVE memberships that can decide a step of ``permission`` over ``entity_ids`` (over
    every entity when ``all_entities``): the holders whose own assignments grant the permission
    for EVERY entity (``permission_holders_direct``), and the ACTIVE delegates of those holders
    whose delegation names it and who themselves read the subject over the same entities
    (``entity_scope_covering`` with ``readers``, the permissions that read the subject; R-41
    (1); 04 §16.10 rev 1.319); sorted. The approvals engine notifies them of a step
    they can decide and of its void (NTF-01, NTF-04; dev-guide DG-KRN-APR-06): a membership that
    covers only some entities of a subject decides nothing, so it is not told. ``barred`` are the
    memberships that may not decide the request at hand (its preparer, its earlier deciders, the
    deciders its subject excludes): they are left out, and so is a delegate whose only delegators
    are among them (R-64 (5): a delegation of a barred person conveys nothing for this request)."""
    unbarred = permission_holders_direct(
        session, permission=permission, entity_ids=entity_ids, all_entities=all_entities, at=at
    ) - set(barred)
    delegates = entity_scope_covering(
        session,
        membership_ids=_delegates(session, unbarred, permission=permission, at=at),
        entity_ids=entity_ids,
        all_entities=all_entities,
        at=at,
        readers=readers,
    )
    return sorted((unbarred | delegates) - set(barred))


def _delegates(
    session: Session, holders: Collection[UUID], *, permission: str, at: datetime
) -> set[UUID]:
    """The ACTIVE delegates of ``holders`` whose delegation in force at ``at`` names
    ``permission`` (T-PLT-21; BR-PLT-07)."""
    if not holders:
        return set()
    delegate = tenant_membership.alias("delegate")
    delegates = (
        select(approval_delegation.c.delegate_membership_id)
        .select_from(
            approval_delegation.join(
                delegate,
                and_(
                    delegate.c.tenant_id == approval_delegation.c.tenant_id,
                    delegate.c.id == approval_delegation.c.delegate_membership_id,
                ),
            )
        )
        .where(
            approval_delegation.c.delegator_membership_id.in_(sorted(holders)),
            approval_delegation.c.revoked_at.is_(None),
            approval_delegation.c.valid_from <= at,
            approval_delegation.c.valid_to > at,
            literal(permission) == any_(approval_delegation.c.permissions),
            delegate.c.status == MembershipStatus.ACTIVE.value,
        )
    )
    return {UUID(str(value)) for value in session.scalars(delegates)}


def permission_holders(
    session: Session, *, permission: str, entity_id: UUID | None, at: datetime
) -> list[UUID]:
    """Who is told of a subject by ``permission`` (05 NTR-02; PRD NTF-05), sorted: the ACTIVE
    memberships whose assignments in force at ``at`` grant the permission and cover the subject,
    and the ACTIVE delegates of those holders whose delegation names the permission and whose OWN
    entity scope covers the same subject.

    The subject's scope is ``entity_id``: an entity's subject is covered by an assignment for all
    entities or by one that names the entity; a subject of the whole workspace — no entity — by
    an assignment for all entities alone, as ``role_holders`` has it. A delegation conveys the
    permission, not the view (ruling R-41 (1); ``entity_scope_covering``): a delegate is told
    only of what the delegate may itself read, as the approvals' reader
    (``permission_holders_covering``) tells it. Until item NOTIFY-DELEGATE-SCOPE-1 every delegate
    of a holder was told — a delegate without the entity of a failed close run read "Job
    failed: Close run" — and a subject without an entity went to every holder, whatever
    entities the role named (no caller passed one)."""
    joined, conditions = _assignments_in_force(at)
    covers: ColumnElement[bool] = role_assignment.c.is_all_entities.is_(True)
    if entity_id is not None:
        covers = or_(covers, literal(entity_id, Uuid()) == any_(role_assignment.c.entity_ids))
    statement = (
        select(role_assignment.c.membership_id)
        .select_from(
            joined.join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
        )
        .where(role_permission.c.permission_code == permission, covers, *conditions)
        .distinct()
    )
    holders = {UUID(str(value)) for value in session.scalars(statement)}
    delegates = entity_scope_covering(
        session,
        membership_ids=_delegates(session, holders, permission=permission, at=at),
        entity_ids=() if entity_id is None else (entity_id,),
        all_entities=entity_id is None,
        at=at,
    )
    return sorted(holders | delegates)


def notify_permission_holders(
    uow: UnitOfWork,
    *,
    permission: str,
    entity_id: UUID | None,
    kind: NotificationKind,
    title: str,
    link_path: str | None,
    body: str | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    exclude_membership_ids: Iterable[UUID] = (),
) -> None:
    """``notify`` the holders of ``permission`` for the entity, less ``exclude_membership_ids``
    (NTR-02; SPEC-Q-179)."""
    excluded = set(exclude_membership_ids)
    holders = permission_holders(
        uow.session, permission=permission, entity_id=entity_id, at=uow.now
    )
    notify(
        uow,
        recipient_membership_ids=[holder for holder in holders if holder not in excluded],
        kind=kind,
        title=title,
        body=body,
        link_path=link_path,
        subject_type=subject_type,
        subject_id=subject_id,
    )
