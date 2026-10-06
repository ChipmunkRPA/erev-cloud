"""API-R-14 support grant schemas (04 §15.3 API-R-14, T-PLT-33, E-96; SCREENS_B §9.14
SF-14:support-access grid columns; BUILD_SPEC PLF-26)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import GrantStatus
from erev_api.schemas.common import ActorOut
from erev_api.schemas.users import EMAIL_LENGTH, MEMO_LENGTH

TICKET_LENGTH: Final = 128


class SupportGrantIn(BaseModel):
    """``POST /support-grants``: read-only access for an operator, at most 72 hours."""

    model_config = ConfigDict(extra="forbid")

    operator_email: str = Field(max_length=EMAIL_LENGTH)
    reason: str = Field(max_length=MEMO_LENGTH)
    ticket_ref: str | None = Field(default=None, max_length=TICKET_LENGTH)
    valid_from: AwareDatetime
    valid_to: AwareDatetime


class SupportGrantRevokeIn(BaseModel):
    """``POST /support-grants/{id}/revoke``: the reason, at least 10 characters."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MEMO_LENGTH)


class SupportGrantOut(BaseModel):
    """API-S-SupportGrant: the T-PLT-33 row with the operator, requester and revoker."""

    id: uuid.UUID
    operator: ActorOut
    scope: str
    reason: str
    ticket_ref: str | None
    status: GrantStatus
    valid_from: datetime
    valid_to: datetime
    approval_request_id: uuid.UUID | None
    approved_at: datetime | None
    revoked_at: datetime | None
    revoked_by: ActorOut | None
    created_at: datetime
    created_by: ActorOut
