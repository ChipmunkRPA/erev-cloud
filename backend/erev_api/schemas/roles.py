"""API-R-06 Roles and permissions schemas (04 §15.3 API-R-06, T-PLT-09 to T-PLT-12, SMAP-14;
SCREENS_B §9.10 and §9.11 data bindings; BUILD_SPEC PLF-18)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.schemas.common import ActorOut, RefOut
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

CODE_LENGTH: Final = 128  # TY-06
PERMISSIONS_LENGTH: Final = 100


class PermissionOut(BaseModel):
    """A T-PLT-11 catalogue row."""

    code: str
    area: str
    description: str
    is_approval: bool
    is_access_admin: bool
    requires_mfa: bool


class RoleCreateIn(BaseModel):
    """``POST /roles``: a custom role and the permissions its approval grants."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)
    permissions: list[str] = Field(max_length=PERMISSIONS_LENGTH)


class RoleChangeIn(BaseModel):
    """``POST /roles/{id}/propose-change``: the complete proposed permission list."""

    model_config = ConfigDict(extra="forbid")

    permissions: list[str] = Field(max_length=PERMISSIONS_LENGTH)
    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class RoleOut(BaseModel):
    """API-S-Role: a role with its permission codes, members and pending change."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    content_sha256: str
    permissions: list[str]
    member_count: int
    pending_approval_request_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class RoleAssignmentIn(BaseModel):
    """``POST /role-assignments``: one role for one member, for all entities or named entities,
    optionally with the approved SoD exception that covers the combination."""

    model_config = ConfigDict(extra="forbid")

    membership_id: uuid.UUID
    role_id: uuid.UUID
    is_all_entities: bool = True
    entity_codes: list[str] = Field(default_factory=list, max_length=500)
    sod_exception_id: uuid.UUID | None = None


class RoleAssignmentRevokeIn(BaseModel):
    """``POST /role-assignments/{id}/revoke``: the reason, at least 10 characters."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MEMO_LENGTH)


class RoleAssignmentOut(BaseModel):
    """API-S-RoleAssignment: requested (a pending request, no row yet), active or revoked;
    ``id`` is the assignment id, which a requested assignment takes on approval."""

    id: uuid.UUID
    membership_id: uuid.UUID
    member_name: str
    role: RefOut
    is_all_entities: bool
    entities: list[RefOut]
    entity_count: int = Field(
        description=(
            "How many entities the assignment names: 0 for all entities. `entities` lists those "
            "the caller's session sees, so a greater count says it reaches beyond them."
        )
    )
    status: Literal["REQUESTED", "ACTIVE", "REVOKED"]
    approval_request_id: uuid.UUID | None
    valid_from: datetime | None
    valid_to: datetime | None
    granted_by: ActorOut | None
    setup_grant: bool
    sod_exception_id: uuid.UUID | None
    revoked_at: datetime | None
    revoked_by: ActorOut | None
