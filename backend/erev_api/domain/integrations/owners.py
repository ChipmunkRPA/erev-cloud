"""The active, tenant-local member designated to handle a connection's exceptions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.permissions import effective_grants
from erev_api.db.tables import tenant_membership
from erev_api.enums import MembershipStatus, PrincipalKind
from erev_api.problems import ProblemError
from erev_api.uow import UnitOfWork


def eligible(uow: UnitOfWork, owner_id: UUID | None, entity_ids: Sequence[UUID]) -> bool:
    if owner_id is None:
        return False
    member = uow.session.execute(
        select(tenant_membership.c.id).where(
            tenant_membership.c.tenant_id == uow.principal.tenant_id,
            tenant_membership.c.id == owner_id,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
    ).scalar_one_or_none()
    if member is None:
        return False
    scopes = effective_grants(uow.session, owner_id, at=uow.now).permission_scopes
    # A recipient must reach the whole connection and read its financial exception details.
    return all(
        (held := scopes.get(permission)) == "*"
        or (held is not None and bool(entity_ids) and set(entity_ids) <= set(held))
        for permission in ("integration.manage", "contract.read")
    )


def errors(
    uow: UnitOfWork, owner_id: UUID | None, entity_ids: Sequence[UUID]
) -> list[ProblemError]:
    if owner_id is None or eligible(uow, owner_id, entity_ids):
        return []
    return [
        ProblemError(
            field="owner_membership_id",
            rule_id="INTEGRATION_OWNER_SCOPE",
            message=(
                "Choose an active member who can manage and read every entity of this connection."
            ),
        )
    ]


def recipient(uow: UnitOfWork, connection: Mapping[str, Any]) -> UUID | None:
    """Prefer the configured owner; fall back to the eligible human creator of the connection.

    Connection creation already defaults ownership to that member. Resolve current membership
    and grants again when raising a failure; never change the configured owner implicitly.
    """
    owner_id = connection["owner_membership_id"]
    entities = connection["entity_ids"]
    if eligible(uow, owner_id, entities):
        return UUID(str(owner_id))
    if (
        connection["created_by_kind"] != PrincipalKind.USER.value
        or connection["created_by"] is None
    ):
        return None
    creator_id = uow.session.execute(
        select(tenant_membership.c.id).where(
            tenant_membership.c.tenant_id == uow.principal.tenant_id,
            tenant_membership.c.user_id == connection["created_by"],
        )
    ).scalar_one_or_none()
    return UUID(str(creator_id)) if eligible(uow, creator_id, entities) else None
