"""Tenant-wide role/permission matrix captured at the requested ACCESS instant.

Role definitions have no complete version table. Refuse a role changed after the instant
rather than presenting its current definition as historical. The snapshot contains definitions,
not memberships, passwords, tokens or other authentication material.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Literal, Self
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator
from sqlalchemy import select

from erev_api.db.tables import role, role_permission
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.problems import Problem
from erev_api.schemas.evidence_packs import AccessPackCreateIn
from erev_api.uow import UnitOfWork

PERMISSIONS = frozenset({"report.run", "report.export", "audit.read", "evidence.export"})


class RoleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    code: str
    name: str
    is_active: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    permissions: tuple[str, ...]


class RoleMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["erev.access-role-matrix.v1"] = "erev.access-role-matrix.v1"
    tenant_id: UUID
    as_of: AwareDatetime
    known_at: AwareDatetime
    roles: tuple[RoleDefinition, ...]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.as_of > self.known_at
            or len({item.id for item in self.roles}) != len(self.roles)
            or len({item.code for item in self.roles}) != len(self.roles)
            or any(
                item.created_at > self.as_of
                or item.updated_at > self.as_of
                or item.updated_at < item.created_at
                or len(set(item.permissions)) != len(item.permissions)
                for item in self.roles
            )
        ):
            raise ValueError("Role definitions cannot establish the selected access instant.")
        return self


def instant(request: AccessPackCreateIn, known_at: datetime) -> datetime:
    return min(datetime.combine(request.as_of, time.max, tzinfo=UTC), known_at)


def authorize(uow: UnitOfWork) -> None:
    # Definitions apply tenant-wide; enumerating every currently existing entity is not a
    # substitute for the all-entities grant, including entities created after capture.
    if uow.principal.entity_scope != "*" or any(
        permission not in uow.principal.permissions
        or uow.principal.permission_scopes.get(permission) != "*"
        for permission in PERMISSIONS
    ):
        raise Problem("forbidden", "A complete role matrix requires tenant-wide evidence access.")


def capture(uow: UnitOfWork, request: AccessPackCreateIn) -> RoleMatrix:
    authorize(uow)
    if request.as_of > uow.now.astimezone(UTC).date():
        raise Problem("validation-failed", "Access evidence cannot be in the future.")
    at = instant(request, uow.now)
    rows = (
        uow.session.execute(
            select(
                role.c.id,
                role.c.code,
                role.c.name,
                role.c.is_active,
                role.c.created_at,
                role.c.updated_at,
            )
            .where(role.c.tenant_id == uow.principal.tenant_id, role.c.created_at <= at)
            .order_by(role.c.code, role.c.id)
        )
        .mappings()
        .all()
    )
    if any(row["updated_at"] > at for row in rows):
        raise Problem(
            "validation-failed",
            "A role changed after the selected instant; its historical definition is unavailable.",
        )
    permissions: dict[UUID, list[str]] = {row["id"]: [] for row in rows}
    for identity, code in uow.session.execute(
        select(
            role_permission.c.role_id,
            role_permission.c.permission_code,
        )
        .where(
            role_permission.c.tenant_id == uow.principal.tenant_id,
            role_permission.c.role_id.in_(permissions),
        )
        .order_by(role_permission.c.permission_code)
    ):
        permissions[identity].append(code)
    return RoleMatrix(
        tenant_id=uow.principal.tenant_id,
        as_of=at,
        known_at=uow.now,
        roles=tuple(
            RoleDefinition(**dict(row), permissions=tuple(permissions[row["id"]])) for row in rows
        ),
    )


def files(source: RoleMatrix) -> tuple[PackFile, ...]:
    return (
        PackFile(
            "access/role_permission_matrix.json", canonical_bytes(source.model_dump(mode="json"))
        ),
    )
