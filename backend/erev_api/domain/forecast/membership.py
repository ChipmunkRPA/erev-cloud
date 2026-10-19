"""Minimum scenario access for a creator absent from the historical snapshot (BR-FC-01)."""

from uuid import UUID

from sqlalchemy import insert, select

from erev_api.auth.permissions import role_content_sha256
from erev_api.db import new_id
from erev_api.db.tables import role, role_assignment, role_permission, tenant_membership
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def ensure_creator(uow: UnitOfWork, user_id: UUID) -> None:
    """Preserve copied memberships; add only Viewer and scenario.use when absent."""
    session = uow.session
    present = (
        session.execute(select(tenant_membership).where(tenant_membership.c.user_id == user_id))
        .mappings()
        .one_or_none()
    )
    if present is not None:
        if present["status"] != "ACTIVE":
            raise Problem("forbidden", "The scenario creator's copied membership is inactive.")
        return
    viewer = session.execute(
        select(role.c.id).where(
            role.c.code == "viewer", role.c.is_system.is_(True), role.c.is_active.is_(True)
        )
    ).scalar_one_or_none()
    if viewer is None:
        raise Problem("precondition-failed", "The snapshot has no active Viewer role.")
    tenant_id = uow.principal.tenant_id
    member_id, role_id = new_id(), new_id()
    stamp = {"created_at": uow.now, "created_by_kind": "SYSTEM"}
    mutable = {**stamp, "updated_at": uow.now, "updated_by_kind": "SYSTEM"}
    session.execute(
        insert(tenant_membership).values(
            tenant_id=tenant_id,
            id=member_id,
            user_id=user_id,
            status="ACTIVE",
            activated_at=uow.now,
            **mutable,
        )
    )
    session.execute(
        insert(role).values(
            tenant_id=tenant_id,
            id=role_id,
            code="scenario_" + role_id.hex.translate(str.maketrans("0123456789", "ghijklmnop")),
            name="Scenario creator",
            description="Minimum scenario access (BR-FC-01)",
            is_system=False,
            is_active=True,
            content_sha256=role_content_sha256(("scenario.use",)),
            **mutable,
        )
    )
    session.execute(
        insert(role_permission).values(
            tenant_id=tenant_id, role_id=role_id, permission_code="scenario.use", **stamp
        )
    )
    for assigned in (viewer, role_id):
        session.execute(
            insert(role_assignment).values(
                tenant_id=tenant_id,
                id=new_id(),
                membership_id=member_id,
                role_id=assigned,
                is_all_entities=True,
                valid_from=uow.now,
                **stamp,
            )
        )
    uow.audit(
        action="scenario.creator_added",
        object_type="tenant_membership",
        object_id=member_id,
        after={"user_id": str(user_id), "status": "ACTIVE"},
        detail={"role_ids": [str(viewer), str(role_id)], "rule_id": "BR-FC-01"},
    )
