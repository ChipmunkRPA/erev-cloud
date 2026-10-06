"""API-R-07 SoD schemas (04 §15.3 API-R-07, T-PLT-13, T-PLT-14, E-12, E-96; SCREENS_B §9.10
exception drawer and §9.12 data bindings; BUILD_SPEC PLF-19)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import ConfigStatus, GrantStatus
from erev_api.schemas.common import ActorOut
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

CODE_LENGTH: Final = 128  # TY-06
PERMISSIONS_LENGTH: Final = 100


class SodRuleVersionIn(BaseModel):
    """``POST /sod-rules/{code}/versions``: the complete content of the next rule version."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=LABEL_LENGTH)
    function_a_permissions: list[str] = Field(max_length=PERMISSIONS_LENGTH)
    function_b_permissions: list[str] = Field(max_length=PERMISSIONS_LENGTH)
    rationale: str = Field(max_length=MEMO_LENGTH)
    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class SodRuleOut(BaseModel):
    """API-S-SodRule: one version of a rule with its pending approval request."""

    id: uuid.UUID
    code: str
    name: str
    function_a_permissions: list[str]
    function_b_permissions: list[str]
    rationale: str
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    effective_to: datetime | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    pending_approval_request_id: uuid.UUID | None
    published_at: datetime | None
    published_by: uuid.UUID | None
    supersedes_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class SodExceptionIn(BaseModel):
    """``POST /sod-exceptions``: an exception for a member and rule, valid at most 366 days."""

    model_config = ConfigDict(extra="forbid")

    sod_rule_code: str = Field(max_length=CODE_LENGTH)
    membership_id: uuid.UUID
    compensating_control: str = Field(max_length=MEMO_LENGTH)
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    comment: str = Field(max_length=MEMO_LENGTH)


class SodExceptionRevokeIn(BaseModel):
    """``POST /sod-exceptions/{id}/revoke``: the reason, at least 10 characters."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MEMO_LENGTH)


class SodExceptionOut(BaseModel):
    """API-S-SodException: the T-PLT-14 row with the member's name."""

    id: uuid.UUID
    sod_rule_code: str
    membership_id: uuid.UUID
    member_name: str
    compensating_control: str
    status: GrantStatus
    valid_from: datetime
    valid_to: datetime
    approval_request_id: uuid.UUID | None
    approved_at: datetime | None
    revoked_at: datetime | None
    revoked_by: ActorOut | None
    created_at: datetime
    created_by: ActorOut
