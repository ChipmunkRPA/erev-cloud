"""The signed-in member's profile and display preferences (04 API-R-03, §16.12 API-S-Me and
``PATCH /me/preferences``, T-PLT-02 ``preferences``, E-123, E-124; SCREENS_B OQ-B-20, OQ-B-24;
DESIGN_SYSTEM DS-FMT-06; BUILD_SPEC PLF-21, BS1-D-32).

``me`` reads API-S-Me in one read-only tenant transaction. Memberships come through the RLS-TM self
policy joined to the tenants RLS-TN shows the user: the active tenant and those where the membership
is ACTIVE, so a membership of another workspace that is not ACTIVE stays hidden (SPEC-Q-186).
``me_without_workspace`` answers a session that has not opened a workspace (D-83): the memberships
through the identity repositories, no active membership, permissions or entity scope, and the
platform defaults where API-S-Me names the active tenant's values. ``update_preferences`` merges
the members sent into ``app_user.preferences``; a null member returns to its default. Preferences
are AUD-OPS, so no audit event is written.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import func, select, update

from erev_api.auth import mfa, sessions
from erev_api.db.session import tenant_session
from erev_api.db.tables import app_user, notification, tenant, tenant_membership
from erev_api.enums import MembershipStatus, PrincipalKind, UiDensity, UiTheme, UserStatus
from erev_api.problems import Problem
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.resolve import setting

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.auth.sessions import AuthenticatedSession
    from erev_api.controls.release import EngineRelease
    from erev_api.uow import UnitOfWork

NO_MEMBERSHIP: Final = "Only a workspace member has a profile."
NEGATIVE_NUMBER_STYLE: Final = "ui.negative_number_style"
AI_ENABLED: Final = "ai.enabled"
# [J] L4-4-Q-2: without a workspace, `default_locale` is the 04 T-PLT-01 column default.
NO_WORKSPACE_LOCALE: Final = "en-US"
# 04 T-PLT-02: the values of absent members; an absent format_locale is the workspace's locale.
PREFERENCE_DEFAULTS: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "theme": UiTheme.SYSTEM.value,
        "density": UiDensity.COMFORTABLE.value,
        "shortcuts_enabled": True,
        "tour_completed": None,
    }
)


def _member(principal: Principal) -> tuple[UUID, UUID]:
    """The user id and membership id of a signed-in member; other principals are refused."""
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or principal.membership_id is None
    ):
        raise Problem("forbidden", NO_MEMBERSHIP)
    return principal.id, principal.membership_id


def preferences_view(stored: Mapping[str, Any], *, default_locale: str) -> dict[str, Any]:
    """``app_user.preferences`` with the T-PLT-02 defaults applied (04 API-S-Me)."""
    view: dict[str, Any] = {"format_locale": stored.get("format_locale", default_locale)}
    for key, default in PREFERENCE_DEFAULTS.items():
        view[key] = stored.get(key, default)
    return view


def me(
    ctx: RequestContext, *, engine_release: EngineRelease, ai_kill_switch: bool
) -> dict[str, Any]:
    """API-S-Me of the caller in the active tenant."""
    principal = ctx.principal
    user_id, membership_id = _member(principal)
    with tenant_session(principal.db_context, read_only=True) as session:
        user = (
            session.execute(
                select(
                    app_user.c.id,
                    app_user.c.email,
                    app_user.c.display_name,
                    app_user.c.status,
                    app_user.c.preferences,
                ).where(app_user.c.id == user_id)
            )
            .mappings()
            .one()
        )
        memberships = (
            session.execute(
                select(
                    tenant_membership.c.id.label("membership_id"),
                    tenant_membership.c.status,
                    tenant_membership.c.last_opened_at,
                    tenant.c.id.label("tenant_id"),
                    tenant.c.code,
                    tenant.c.display_name,
                    tenant.c.kind,
                    tenant.c.is_demo,
                    *sessions.MEMBERSHIP_TENANT_FACTS,
                )
                .join(tenant, tenant.c.id == tenant_membership.c.tenant_id)
                .where(
                    tenant_membership.c.user_id == user_id,
                    tenant_membership.c.status != MembershipStatus.REMOVED.value,
                )
                .order_by(tenant_membership.c.last_opened_at.desc().nulls_last(), tenant.c.code)
            )
            .mappings()
            .all()
        )
        workspace = (
            session.execute(
                select(tenant.c.default_locale, tenant.c.ai_disabled_at).where(
                    tenant.c.id == principal.tenant_id
                )
            )
            .mappings()
            .one()
        )
        negative_number_style = setting(session, NEGATIVE_NUMBER_STYLE, known_at=ctx.now)
        ai_setting = setting(session, AI_ENABLED, known_at=ctx.now)
        unread = session.execute(
            select(func.count())
            .select_from(notification)
            .where(
                notification.c.recipient_membership_id == membership_id,
                notification.c.read_at.is_(None),
            )
        ).scalar_one()
    stored = user["preferences"] if isinstance(user["preferences"], Mapping) else {}
    default_locale = str(workspace["default_locale"])
    scope = principal.entity_scope
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "status": user["status"],
        },
        "memberships": [_membership_view(row) for row in memberships],
        "active_membership_id": membership_id,
        "permissions": sorted(principal.permissions),
        "entity_scope": "*" if scope == "*" else [str(entity_id) for entity_id in scope],
        # ME-SCOPE-PER-PERMISSION-1: the entities each permission is held for. `entity_scope` is
        # the union of the roles' entities — what the session sees — and says nothing of which
        # permission reaches which entity (REQ-PLT-012).
        "permission_scopes": {
            code: "*" if held == "*" else sorted(str(entity_id) for entity_id in held)
            for code, held in sorted(principal.permission_scopes.items())
        },
        "mfa": {
            "enrolled": mfa.has_confirmed_factor(user_id, request_id=ctx.request_id),
            "verified_at": principal.mfa_verified_at,
        },
        "preferences": preferences_view(stored, default_locale=default_locale),
        "tenant_settings": {
            "negative_number_style": negative_number_style,
            "default_locale": default_locale,
            "ai_enabled": ai_setting is True
            and workspace["ai_disabled_at"] is None
            and not ai_kill_switch,
        },
        "engine_release": _release_view(engine_release),
        "unread_notification_count": int(unread),
    }


def me_without_workspace(
    auth: AuthenticatedSession, *, engine_release: EngineRelease
) -> dict[str, Any]:
    """API-S-Me of a session that has not opened a workspace (D-83).

    The memberships are those RLS-TN shows without an active tenant, the ACTIVE ones. Nothing is
    held, so ``permissions`` and ``entity_scope`` are empty and no notification is unread. Where
    API-S-Me names the active tenant's values, the platform defaults apply: the T-PLT-01 locale, the
    T-PLT-31 ``ui.negative_number_style`` default and AI off. A valid session belongs to an ACTIVE
    user, because ``sessions.authenticate`` ends the session of any other.
    """
    user = auth.user
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "status": UserStatus.ACTIVE.value,
        },
        "memberships": [_membership_view(row) for row in sessions.memberships(auth)],
        "active_membership_id": None,
        "permissions": [],
        "entity_scope": [],
        "permission_scopes": {},
        "mfa": {
            "enrolled": mfa.has_confirmed_factor(user.id, request_id=auth.facts.request_id),
            "verified_at": auth.session.mfa_verified_at,
        },
        "preferences": preferences_view(user.preferences, default_locale=NO_WORKSPACE_LOCALE),
        "tenant_settings": {
            "negative_number_style": PLATFORM_PARAMETERS[NEGATIVE_NUMBER_STYLE].default_asc606,
            "default_locale": NO_WORKSPACE_LOCALE,
            "ai_enabled": False,
        },
        "engine_release": _release_view(engine_release),
        "unread_notification_count": 0,
    }


def _membership_view(row: Mapping[Any, Any]) -> dict[str, Any]:
    """One API-S-Me membership from a membership row joined to its tenant."""
    return {
        "membership_id": row["membership_id"],
        "tenant": {
            "id": row["tenant_id"],
            "code": row["code"],
            "display_name": row["display_name"],
            "kind": row["kind"],
            "is_demo": row["is_demo"],
            "status": row["tenant_status"],
            "source_tenant_id": row["source_tenant_id"],
            "source_known_at": row["source_known_at"],
        },
        "status": row["status"],
        "last_opened_at": row["last_opened_at"],
    }


def _release_view(engine_release: EngineRelease) -> dict[str, Any]:
    return {
        "engine_version": engine_release.engine_version,
        "build_sha": engine_release.build_sha,
        "schema_revision": engine_release.schema_revision,
    }


def update_preferences(uow: UnitOfWork, changes: Mapping[str, Any]) -> dict[str, Any]:
    """Merge the members sent into the caller's preferences and return them with the defaults.

    ``changes`` holds JSON-native values; a None value removes the member, so it returns to its
    default.
    """
    principal = uow.principal
    user_id, _ = _member(principal)
    session = uow.session
    stored = session.execute(
        select(app_user.c.preferences)
        .where(app_user.c.id == user_id)
        .with_for_update(key_share=True)
    ).scalar_one()
    current: dict[str, Any] = dict(stored) if isinstance(stored, Mapping) else {}
    merged = dict(current)
    for key, value in changes.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    if merged != current:
        session.execute(
            update(app_user)
            .where(app_user.c.id == user_id)
            .values(preferences=merged, updated_by=user_id, updated_by_kind=principal.kind.value)
        )
    default_locale = session.execute(
        select(tenant.c.default_locale).where(tenant.c.id == principal.tenant_id)
    ).scalar_one()
    return preferences_view(merged, default_locale=str(default_locale))
