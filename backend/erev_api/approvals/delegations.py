"""Approval delegations in the kernel: the end of a delegation that lost its support (04 T-PLT-21;
PRD BR-PLT-07 rev 1.118; dev-guide DG-KRN-APR-09; supervisor ruling R-111 (4)).

A delegation rests on what its delegator holds. The approval engine honours one only while its
delegator is an ACTIVE member who still holds the permission (``engine.find_authority``), so a
delegation whose delegator lost either used to lie dormant — and came back to life when the access
returned. It ENDS instead: ``end_unsupported`` stamps ``revoked_at`` on every delegation that has
not ended and whose delegator is not an ACTIVE member or does not hold every permission it names,
and audits each end with its cause (``approval_delegation.end``).

A delegation is also given TO a member, and a removal ends that too (PRD BR-PLT-07 rev 1.201; 04
T-PLT-21 rev 1.293; dev-guide rev 1.286; item SBX-COPY-OPEN-INVITATION-1, the independent review
of its head): the same sweep ends every delegation whose DELEGATE is a REMOVED member. The engine
honours a delegation for the session of an ACTIVE member, so one given to a removed member lay
inert — and a removed person is invited again on the same membership (PRD SM-13): active once
more, that person would have decided on the delegator's behalf with authority nobody gave for the
second life. A suspended delegate keeps what was given, as a suspended member keeps the roles.

Every command that changes what a member holds calls it — after a change that takes access away (a
role assignment revoked, a role changed, a membership suspended or removed, an identity erased) and
before a change that gives access (a role assignment approved, a role changed, a membership
reactivated) — so that no delegation is unsupported across a command, and none returns with a
later grant. ``backend/tests/architecture/test_delegation_end.py`` holds every function of the
application that writes ``role_assignment``, ``role_permission`` or ``tenant_membership`` to a
call of ``end_unsupported`` or to its list of exemptions.

The tables read are RLS-T (04 T-PLT-07 is read through the delegator's and the delegate's rows of
the tenant): the sweep sees every delegation and every grant of the workspace whatever the entity
scope of the member whose command runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.auth.permissions import effective_grants
from erev_api.db import transitions
from erev_api.db.tables import approval_delegation, tenant_membership
from erev_api.enums import MembershipStatus

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "approval_delegation"
END_ACTION: Final = "approval_delegation.end"
# ``detail.cause`` of the end: the command whose change left the delegation unsupported, or met
# it so.
ROLE_ASSIGNMENT_REVOKED: Final = "role-assignment-revoked"
ROLE_ASSIGNMENT_GRANTED: Final = "role-assignment-granted"
ROLE_CHANGED: Final = "role-changed"
MEMBERSHIP_STATUS: Final = "membership-status"
IDENTITY_ERASED: Final = "identity-erased"


@dataclass(frozen=True, slots=True)
class Ended:
    """One delegation ``end_unsupported_rows`` ended, with what its audit event states."""

    id: UUID
    delegator_status: str
    lost_permissions: tuple[str, ...]
    delegate_status: str | None = None  # ``REMOVED`` where the delegate's removal ended it

    def detail(self, cause: str) -> dict[str, Any]:
        """``detail`` of the ``approval_delegation.end`` event; ``delegate_status`` is a member
        of it only where the delegate's removal ended the delegation."""
        stated: dict[str, Any] = {
            "cause": cause,
            "delegator_status": self.delegator_status,
            "lost_permissions": list(self.lost_permissions),
        }
        if self.delegate_status is not None:
            stated["delegate_status"] = self.delegate_status
        return stated


def end_unsupported_rows(
    session: Session, *, now: datetime, revoked_by: UUID | None, revoked_by_kind: str
) -> list[Ended]:
    """End every delegation of the workspace that has not ended — neither revoked nor past its
    ``valid_to``, started or not — and is no longer supported: its delegator is not an ACTIVE
    member, or does not hold every permission the delegation names; or its delegate is a REMOVED
    member. Returns what was ended, in id order; the caller audits each (``end_unsupported`` does
    both for a unit of work). A delegation names its permissions once and for all (IM-S), so the
    loss of one ends the whole delegation; its delegator gives a new one for what they still
    hold. Rows are locked in id order."""
    delegate = tenant_membership.alias("delegate")
    rows = session.execute(
        select(
            approval_delegation.c.id,
            approval_delegation.c.delegator_membership_id,
            approval_delegation.c.permissions,
            tenant_membership.c.status,
            delegate.c.status.label("delegate_status"),
        )
        .select_from(
            approval_delegation.join(
                tenant_membership,
                and_(
                    tenant_membership.c.tenant_id == approval_delegation.c.tenant_id,
                    tenant_membership.c.id == approval_delegation.c.delegator_membership_id,
                ),
            ).join(
                delegate,
                and_(
                    delegate.c.tenant_id == approval_delegation.c.tenant_id,
                    delegate.c.id == approval_delegation.c.delegate_membership_id,
                ),
            )
        )
        .where(approval_delegation.c.revoked_at.is_(None), approval_delegation.c.valid_to > now)
        .order_by(approval_delegation.c.id)
        .with_for_update(of=approval_delegation)
    ).all()
    held: dict[UUID, frozenset[str]] = {}
    ended: list[Ended] = []
    for row in rows:
        delegator = UUID(str(row.delegator_membership_id))
        if delegator not in held:
            held[delegator] = effective_grants(session, delegator, at=now).permissions
        lost = tuple(sorted({str(code) for code in row.permissions} - held[delegator]))
        status = str(row.status)
        removed = str(row.delegate_status) == MembershipStatus.REMOVED.value
        if status == MembershipStatus.ACTIVE.value and not lost and not removed:
            continue
        delegation_id = UUID(str(row.id))
        transitions.apply(
            session,
            OBJECT_TYPE,
            delegation_id,
            to_status=None,
            set_values={
                "revoked_at": now,
                "revoked_by": revoked_by,
                "revoked_by_kind": revoked_by_kind,
            },
        )
        ended.append(
            Ended(
                id=delegation_id,
                delegator_status=status,
                lost_permissions=lost,
                delegate_status=MembershipStatus.REMOVED.value if removed else None,
            )
        )
    return ended


def end_unsupported(uow: UnitOfWork, *, cause: str) -> list[UUID]:
    """``end_unsupported_rows`` in a unit of work: each end is stamped with the principal of the
    command that runs the sweep and audited as ``approval_delegation.end`` with ``detail.cause``,
    the delegator's membership status and the permissions no longer held — and the delegate's
    status where the delegate's removal ended it. Returns the ids ended."""
    principal = uow.principal
    ended = end_unsupported_rows(
        uow.session, now=uow.now, revoked_by=principal.id, revoked_by_kind=principal.kind.value
    )
    for item in ended:
        uow.audit(
            action=END_ACTION,
            object_type=OBJECT_TYPE,
            object_id=item.id,
            before={"revoked_at": None},
            after={"revoked_at": uow.now.isoformat()},
            detail=item.detail(cause),
        )
    return [item.id for item in ended]
