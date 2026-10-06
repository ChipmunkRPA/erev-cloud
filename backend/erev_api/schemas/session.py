"""API-R-01 Session schemas (04 §16.12 API-S-Session; BS1-D-30; DG-API-03, DG-KRN-AUTH-07)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from erev_api.enums import TenantKind


class SessionLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class SessionTenantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID


class IdentityProviderRefOut(BaseModel):
    code: str
    name: str


class SessionCapabilitiesOut(BaseModel):
    identity_providers: list[IdentityProviderRefOut]


class SessionUserOut(BaseModel):
    id: UUID
    email: str
    display_name: str


class SessionTenantOut(BaseModel):
    id: UUID
    code: str
    display_name: str
    kind: TenantKind


class AnonymousSessionOut(BaseModel):
    """``GET /session`` without a valid session: ``authenticated`` false and capabilities only."""

    authenticated: Literal[False]
    capabilities: SessionCapabilitiesOut


class SessionOut(BaseModel):
    """API-S-Session of a valid session, with the synchronizer token of DG-KRN-AUTH-07 and the
    second-factor step the session still owes (REQ-PLT-005): ``mfa_required`` while it must answer
    the challenge, ``mfa_enrolment_required`` while its user must enrol. A session that owes a step
    reaches only the routes that settle it."""

    authenticated: Literal[True]
    user: SessionUserOut
    active_tenant: SessionTenantOut | None
    mfa_verified_at: datetime | None
    mfa_required: bool
    mfa_enrolment_required: bool
    idle_expires_at: datetime
    absolute_expires_at: datetime
    capabilities: SessionCapabilitiesOut
    csrf_token: str


class SessionLoginOut(SessionOut):
    """``POST /session/login``, ``POST /session/accept-invitation`` and ``POST /session/tenant``:
    the new session, with the step it owes next (BS1-D-30)."""


class SessionMfaIn(BaseModel):
    """``POST /session/mfa``: exactly one of a TOTP code and a recovery code (BS1-D-30)."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=16)
    recovery_code: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _one_factor(self) -> SessionMfaIn:
        if (self.code is None) == (self.recovery_code is None):
            raise ValueError("Send either code or recovery_code.")
        return self


class InvitationLookupIn(BaseModel):
    """``POST /session/invitations/lookup``: the token travels only in the body (SCREENS_B
    OQ-B-28)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)


class InvitationLookupOut(BaseModel):
    """The heading and form of SF-22:accept-invitation (04 §16.12 rev 1.38): ``has_password`` is
    true when the invitee already holds a password, so the screen asks for it instead of a new one
    (SCREENS_B §12.3 "Your eRev password"; D-98 candidate 24)."""

    workspace_display_name: str
    inviter_display_name: str | None
    email: str
    expires_at: datetime
    has_password: bool


class SessionAcceptInvitationIn(BaseModel):
    """``POST /session/accept-invitation`` (04 T-PLT-07)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class PasswordResetIn(BaseModel):
    """``POST /session/password-reset`` (04 T-PLT-42 rules 1 and 2)."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)


class PasswordResetConfirmIn(BaseModel):
    """``POST /session/password-reset/confirm`` (04 T-PLT-42 rule 3)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=1024)


class SessionMfaOut(SessionOut):
    """``POST /session/mfa``: the rotated, MFA-verified session (SAR-09). After a recovery code,
    the count of unused codes left in the batch (SCREENS_B §12.1 "Recovery code used")."""

    recovery_codes_remaining: int | None
