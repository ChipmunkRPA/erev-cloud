"""Tenant setup completion (PRD BR-PLT-02; 04 T-PLT-01 ``setup_completed_at``, §14.3 rules 1 to 3;
BUILD_SPEC PLF-12, RFD-19).

Setup completes when at least one legal entity has an ``open`` period and the permissions to prepare
and to approve contracts (``contract.create``, ``contract.approve``) are held by two different
ACTIVE memberships. ``evaluate_setup_completion`` runs after the commands that can make these
conditions true: entity creation, period opening, role-assignment approval (automatic through
rule ``AUTO-BOOTSTRAP`` at submission, or decided in SF-12) and a membership becoming ACTIVE — the
acceptance of an invitation and a reactivation. The first command that finds them true sets
``tenant.setup_completed_at`` once and audits ``tenant.setup_completed``; from then on rule
``AUTO-BOOTSTRAP`` stops matching (04 §14.3 item 3) and ``settings.manage`` no longer opens periods
(API-R-18).

The rule ends when the conditions hold (04 T-PLT-01 rev 1.224; the supervisor's ruling of
2026-10-01 on the independent review of the setup rule, item APR-SETUP-RULE-2). A role request
therefore reads them BEFORE it is routed as well (``completion_due``, asked by
``users.request_role_assignment``): whatever made the conditions true — a command of this list,
two of them that committed beside each other, or rows no command of it wrote — the grant that
follows is kept from a rule whose end is due, and the command's evaluation sets the stamp. The
other command that decides by the setup state reads the same way: ``POST /periods/{id}/open``
asks ``rule_ended``, so ``settings.manage`` opens no period once the conditions hold. The
evaluation stays the last lock a command takes (dev-guide DG-KRN-DB-08 (3a)). And the conditions
are the tenant's: the open period is read under the tenant's SYSTEM entity scope
(``open_period_exists``), so the result is the same whoever's command evaluates it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    legal_entity,
    period_state,
    role,
    role_assignment,
    role_permission,
    tenant,
    tenant_membership,
)
from erev_api.enums import MembershipStatus, PeriodState

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

COMPLETED_ACTION: Final = "tenant.setup_completed"
OBJECT_TYPE: Final = "tenant"
PREPARE_PERMISSION: Final = "contract.create"
APPROVE_PERMISSION: Final = "contract.approve"


def setup_completed(session: Session, tenant_id: UUID) -> bool:
    """Whether setup of the tenant is complete (PRD BR-PLT-02): ``setup_completed_at`` is set."""
    completed_at = session.execute(
        select(tenant.c.setup_completed_at).where(tenant.c.id == tenant_id)
    ).scalar_one()
    return completed_at is not None


def open_period_exists(session: Session) -> bool:
    """At least one legal entity of the TENANT has a period in state ``open`` in some book.

    Read under the tenant's SYSTEM entity scope (dev-guide DG-KRN-DB-05; supervisor ruling R-42
    (d): a control's result does not depend on who asks). ``period_state`` and ``legal_entity``
    are entity-scoped rows, and the command that evaluates setup is whoever's makes the last
    condition true: a reviewer of AVM-US who accepts an invitation while the only open period is
    AVM-DE's would find none, and a workspace that meets BR-PLT-02 would stay in setup. The read
    answers a truth value and shows the caller no row."""
    statement = (
        select(period_state.c.id)
        .select_from(
            period_state.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
        )
        .where(period_state.c.state == PeriodState.OPEN.value)
        .limit(1)
    )
    with system_entity_scope(session):
        return session.execute(statement).first() is not None


def permission_holders(session: Session, permission: str, *, at: datetime) -> frozenset[UUID]:
    """The ACTIVE memberships that hold ``permission`` through a role assignment in force at ``at``
    whose role is active (the ``effective_grants`` rule, REQ-PLT-008), in any entity scope."""
    statement = (
        select(role_assignment.c.membership_id)
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            )
            .join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
            .join(
                tenant_membership,
                and_(
                    tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
                    tenant_membership.c.id == role_assignment.c.membership_id,
                ),
            )
        )
        .where(
            role_permission.c.permission_code == permission,
            role.c.is_active.is_(True),
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
            role_assignment.c.revoked_at.is_(None),
            role_assignment.c.valid_from <= at,
            or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
        )
        .distinct()
    )
    return frozenset(UUID(str(value)) for value in session.scalars(statement))


def held_by_two_people(preparers: frozenset[UUID], approvers: frozenset[UUID]) -> bool:
    """Whether some preparer and some approver are different memberships (PRD BR-PLT-02)."""
    return any(preparer != approver for preparer in preparers for approver in approvers)


def conditions_hold(session: Session, *, at: datetime) -> bool:
    """The BR-PLT-02 completion conditions as the command's transaction sees them: the tenant's
    rows, whoever the caller is (``open_period_exists``)."""
    if not open_period_exists(session):
        return False
    return held_by_two_people(
        permission_holders(session, PREPARE_PERMISSION, at=at),
        permission_holders(session, APPROVE_PERMISSION, at=at),
    )


def completion_due(uow: UnitOfWork) -> bool:
    """Whether the BR-PLT-02 conditions hold in a tenant whose ``setup_completed_at`` is not set:
    the completion is due, and the next ``evaluate_setup_completion`` sets the stamp.

    A role request asks this before it is routed and keeps a request of such a workspace from rule
    ``AUTO-BOOTSTRAP`` (``users.request_role_assignment``; 04 T-PLT-01 rev 1.224): the rule ends
    when the conditions hold, not one grant later. It reads and takes no lock, so the order of
    DG-KRN-DB-08 stands — the stamp is set by the command's evaluation, its last lock."""
    session = uow.session
    if setup_completed(session, uow.principal.tenant_id):
        return False
    return conditions_hold(session, at=uow.now)


def rule_ended(uow: UnitOfWork) -> bool:
    """Whether what setup allows has ended for the tenant: ``setup_completed_at`` is set, or the
    BR-PLT-02 conditions hold and the stamp is only due (``completion_due``). A command that
    decides by the setup state and is no role request asks this, not the stamp alone (04
    T-PLT-01, API-R-18): ``POST /periods/{id}/open`` takes ``settings.manage`` only while setup
    is incomplete, and two commands that each made one condition true beside each other leave
    the stamp behind the conditions. It reads and takes no lock."""
    session = uow.session
    if setup_completed(session, uow.principal.tenant_id):
        return True
    return conditions_hold(session, at=uow.now)


def evaluate_setup_completion(uow: UnitOfWork) -> bool:
    """Set ``tenant.setup_completed_at`` once when BR-PLT-02 holds; True when this call set it.

    A tenant whose setup is complete returns at once. Otherwise the conditions are evaluated, and
    when they hold the tenant row is locked and read again, so two concurrent commands set the
    timestamp once and audit ``tenant.setup_completed`` once (04 T-PLT-01 "immutable once set").

    The row is locked ``FOR NO KEY UPDATE`` (dev-guide DG-KRN-DB-08 rev 1.165; supervisor ruling
    R-119 (d), item SETUP-COMPLETION-LOCK-1): it serialises two completions, and the update that
    follows changes no key column. ``FOR UPDATE`` did more than that. Every table of a tenant
    references ``tenant``, so a transaction that has inserted a row holds the tenant's row ``FOR
    KEY SHARE`` to its end, and ``FOR UPDATE`` waits for each of them. The callers run this as
    their last step, holding what they locked — the approval of a period lock holds the state
    rows of the period and of the earlier ones — so an inserting transaction that waited for one
    of those rows closed a cycle, and PostgreSQL ended one of the two (40P01).
    """
    session = uow.session
    tenant_id = uow.principal.tenant_id
    if setup_completed(session, tenant_id):
        return False
    if not conditions_hold(session, at=uow.now):
        return False
    locked = session.execute(
        select(tenant.c.setup_completed_at)
        .where(tenant.c.id == tenant_id)
        .with_for_update(key_share=True)
    ).scalar_one()
    if locked is not None:
        return False
    principal = uow.principal
    session.execute(
        update(tenant)
        .where(tenant.c.id == tenant_id, tenant.c.setup_completed_at.is_(None))
        .values(
            setup_completed_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=COMPLETED_ACTION,
        object_type=OBJECT_TYPE,
        object_id=tenant_id,
        before={"setup_completed_at": None},
        after={"setup_completed_at": uow.now},
    )
    return True
