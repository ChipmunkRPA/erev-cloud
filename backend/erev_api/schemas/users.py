"""API-R-05 Users schemas: API-S-User and the membership commands (04 §15.3 API-R-05, T-PLT-07,
T-PLT-10, SMAP-14; SCREENS_B §9.10 data bindings; BUILD_SPEC PLF-17)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import MembershipStatus
from erev_api.schemas.common import ActorOut, RefOut

MEMO_LENGTH: Final = 4000
LABEL_LENGTH: Final = 400  # TY-07
EMAIL_LENGTH: Final = 320


class UserRoleIn(BaseModel):
    """One role row of the invite drawer: all entities, or named entity codes."""

    model_config = ConfigDict(extra="forbid")

    role_id: uuid.UUID
    is_all_entities: bool = True
    entity_codes: list[str] = Field(default_factory=list, max_length=500)


class UserInviteIn(BaseModel):
    """``POST /users``: the person and the roles their membership requests."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=EMAIL_LENGTH)
    display_name: str = Field(max_length=LABEL_LENGTH)
    roles: list[UserRoleIn] = Field(max_length=20)


class UserUpdateIn(BaseModel):
    """``PATCH /users/{membership_id}``: the display name of an invitation not yet accepted."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(max_length=LABEL_LENGTH)


ErasureStatus = Literal["COMPLETE", "COMPLETION_PENDING"]


class ErasureProgressOut(BaseModel):
    """What one run of ``POST /users/{membership_id}/anonymise`` completed and what a further run
    still owes (05 PRV-07 a; runbook RB-14; 04 T-PLT-02 completion events). eRev delivers nothing
    in the background: ``next_step`` is null exactly when ``status`` is ``COMPLETE``."""

    status: ErasureStatus
    other_workspaces_removed_now: list[uuid.UUID]
    other_workspaces_completion_pending: list[uuid.UUID]
    other_workspaces_completed_now: list[uuid.UUID]
    next_step: str | None


class MembershipReasonIn(BaseModel):
    """The reason of a membership command; suspend and remove need at least 10 characters."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MEMO_LENGTH)


class UserRoleOut(BaseModel):
    """A role of the member: requested (a pending request, no row yet), active or revoked."""

    assignment_id: uuid.UUID | None
    approval_request_id: uuid.UUID | None
    role: RefOut
    is_all_entities: bool
    entities: list[RefOut]
    entity_count: int = Field(
        description=(
            "How many entities the role names: 0 for all entities. `entities` lists those the "
            "caller's session sees, so a greater count says the role reaches beyond them."
        )
    )
    status: Literal["REQUESTED", "ACTIVE", "REVOKED"]
    granted_at: datetime | None
    granted_by: ActorOut | None
    setup_grant: bool
    sod_exception_id: uuid.UUID | None
    revoked_at: datetime | None
    revoked_by: ActorOut | None


class UserOut(BaseModel):
    """API-S-User: a membership with the person and their roles; ``id`` is the membership id."""

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    status: MembershipStatus
    invited_at: datetime
    invitation_expires_at: datetime | None
    activated_at: datetime | None
    removed_at: datetime | None
    last_login_at: datetime | None
    mfa_enrolled: bool | None = Field(
        description="Null, with last_login_at null, while sign_in_withheld is true (D-80)"
    )
    sign_in_withheld: bool = Field(
        description=(
            "True while the membership is INVITED or REMOVED: the person's last sign-in and MFA"
            " state are not shown to the workspace, and display_name is the email unless this"
            " membership's invitation created the identity or the identity is erased (D-80)"
        )
    )
    roles: list[UserRoleOut]
    created_at: datetime
    updated_at: datetime
    row_version: int


class UserAnonymiseOut(UserOut):
    """API-S-User plus the erasure progress of this run (the 200 of ``…/anonymise``)."""

    erasure: ErasureProgressOut
