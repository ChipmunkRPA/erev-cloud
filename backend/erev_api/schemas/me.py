"""API-R-03 Me schemas: API-S-Me, display preferences, multi-factor enrolment, recovery codes,
notifications and notification preferences (04 §15.3 API-R-03, §16.12, T-PLT-02, T-PLT-24,
T-PLT-25, E-123, E-124; SCREENS_B §12.2, SF-15 data bindings, OQ-B-20, OQ-B-24; 05 SAR-26)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import (
    MembershipStatus,
    NotificationKind,
    TenantKind,
    TenantStatus,
    UiDensity,
    UiTheme,
    UserStatus,
)

LOCALE_LENGTH: Final = 35
LOCALE_PATTERN: Final = r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
TOUR_VARIANT_LENGTH: Final = 64


class MeUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    status: UserStatus


class MeTenantOut(BaseModel):
    """A membership's workspace (04 §16.12 rev 1.125): selectable when the membership and the
    workspace are both ACTIVE; ``source_*`` are set on a sandbox copied from a production
    workspace (T-PLT-01)."""

    id: uuid.UUID
    code: str
    display_name: str
    kind: TenantKind
    is_demo: bool
    status: TenantStatus
    source_tenant_id: uuid.UUID | None
    source_known_at: datetime | None


class MeMembershipOut(BaseModel):
    """A membership not REMOVED, in a workspace the user may see."""

    membership_id: uuid.UUID
    tenant: MeTenantOut
    status: MembershipStatus
    last_opened_at: datetime | None


class MfaStatusOut(BaseModel):
    enrolled: bool
    verified_at: datetime | None


class TourCompletedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant: str = Field(min_length=1, max_length=TOUR_VARIANT_LENGTH)
    completed_at: AwareDatetime


class TourCompletedOut(BaseModel):
    variant: str
    completed_at: datetime


class PreferencesOut(BaseModel):
    """``app_user.preferences`` with the T-PLT-02 defaults applied."""

    format_locale: str
    theme: UiTheme
    density: UiDensity
    shortcuts_enabled: bool
    tour_completed: TourCompletedOut | None


class PreferencesIn(BaseModel):
    """``PATCH /me/preferences``: any of the members; a null member returns to its default and an
    unknown member is 422 ``validation-failed`` (04 §16.12)."""

    model_config = ConfigDict(extra="forbid")

    format_locale: str | None = Field(
        default=None, max_length=LOCALE_LENGTH, pattern=LOCALE_PATTERN
    )
    theme: UiTheme | None = None
    density: UiDensity | None = None
    shortcuts_enabled: bool | None = None
    tour_completed: TourCompletedIn | None = None


class PreferencesUpdateOut(BaseModel):
    """``PATCH /me/preferences``: the preferences after the change."""

    preferences: PreferencesOut


class TenantSettingsOut(BaseModel):
    """The resolved ``ui.negative_number_style``, ``tenant.default_locale`` and the AI switch."""

    negative_number_style: Literal["PARENTHESES", "MINUS"]
    default_locale: str
    ai_enabled: bool


class EngineReleaseOut(BaseModel):
    """The T-PLT-38 row the running process stamped at startup (BS1-D-32)."""

    engine_version: str
    build_sha: str
    schema_revision: str


class MeOut(BaseModel):
    """API-S-Me (04 §16.12)."""

    user: MeUserOut
    memberships: list[MeMembershipOut]
    active_membership_id: uuid.UUID | None
    permissions: list[str]
    entity_scope: Literal["*"] | list[str]
    # ME-SCOPE-PER-PERMISSION-1 (04 §16.12): per held permission, "*" or the ids of the entities
    # it is held for; a client offers a command on an entity's row by this member.
    permission_scopes: dict[str, Literal["*"] | list[str]]
    mfa: MfaStatusOut
    preferences: PreferencesOut
    tenant_settings: TenantSettingsOut
    engine_release: EngineReleaseOut
    unread_notification_count: int


class MfaEnrolmentOut(BaseModel):
    """``POST /me/mfa/enroll``: the pending factor's seed for the authenticator app."""

    otpauth_uri: str
    secret_base32: str


class MfaConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=16)


class PasswordChangeIn(BaseModel):
    """``POST /me/password`` (04 §16.12)."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class RecoveryCodesOut(BaseModel):
    """Ten single-use recovery codes, shown once and never returned again (J-22-AC-2)."""

    recovery_codes: list[str]


class NotificationOut(BaseModel):
    """One T-PLT-24 notification of the caller."""

    id: uuid.UUID
    kind: NotificationKind
    subject_type: str | None
    subject_id: uuid.UUID | None
    title: str
    body: str | None
    link_path: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationReadAllIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: AwareDatetime


class NotificationReadAllOut(BaseModel):
    """``POST /me/notifications/read-all``: the number of notifications marked read."""

    marked: int


class NotificationPreferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: NotificationKind
    in_app: bool
    email: bool


class NotificationPreferencesIn(BaseModel):
    """``PUT /me/notification-preferences``: the preferences to store, one per kind."""

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationPreferenceIn] = Field(min_length=1, max_length=12)


class NotificationPreferenceOut(BaseModel):
    kind: NotificationKind
    in_app: bool
    email: bool


class NotificationPreferencesOut(BaseModel):
    """One entry per E-69 kind in 04 order; kinds without a stored row show the defaults."""

    items: list[NotificationPreferenceOut]
