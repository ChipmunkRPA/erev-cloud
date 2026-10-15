"""Read effective AI configuration without constructing a provider or changing settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import registry_version, tenant
from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, TenantStatus
from erev_api.registry.resolve import resolve_among

CODES = (
    "ai.enabled",
    "ai.send_contract_text",
    "ai.model",
    "ai.monthly_token_budget",
    "ai.redact_contact_details",
)


class AISettingsRefused(ValueError):
    """Safe configuration failure, without source values."""


@dataclass(frozen=True, slots=True)
class AISettings:
    model: str
    monthly_token_budget: int
    send_contract_text: bool
    redact_contact_details: bool
    registry_enabled: bool
    tenant_disabled_at: datetime | None
    platform_disabled: bool
    workspace_active: bool
    sources: tuple[tuple[str, UUID | None], ...]

    @property
    def enabled(self) -> bool:
        return (
            self.registry_enabled
            and self.workspace_active
            and self.tenant_disabled_at is None
            and not self.platform_disabled
        )

    def require_available(self) -> None:
        if not self.enabled:
            raise AISettingsRefused("AI_DISABLED")


def load_settings(
    session: Session, *, tenant_id: UUID, now: datetime, platform_kill_switch: bool
) -> AISettings:
    """Resolve all settings from one retained-version read at the job's aware clock.

    Only published versions effective at that instant count. Explicit tenant
    predicates prevent mixing another workspace's directory row with settings.
    The gateway must re-read before each attempt; this object is not a durable
    authorization, budget reservation or provider capability.
    """
    if now.tzinfo is None or now.utcoffset() is None or type(platform_kill_switch) is not bool:
        raise AISettingsRefused("AI_INVALID_CONFIGURATION")
    workspace = (
        session.execute(
            select(tenant.c.status, tenant.c.ai_disabled_at).where(tenant.c.id == tenant_id)
        )
        .mappings()
        .one_or_none()
    )
    if workspace is None:
        raise AISettingsRefused("AI_WORKSPACE_UNAVAILABLE")
    versions = tuple(
        dict(row)
        for row in session.execute(
            select(registry_version)
            .where(
                registry_version.c.tenant_id == tenant_id,
                registry_version.c.category == RegistryCategory.AI.value,
                registry_version.c.status.in_(
                    [ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value]
                ),
                registry_version.c.published_at <= now,
            )
            .order_by(
                registry_version.c.published_at.desc(),
                registry_version.c.version_no.desc(),
                registry_version.c.id,
            )
        ).mappings()
    )
    resolved = {
        code: resolve_among(versions, code, book_code=BookCode.ASC606, at=now) for code in CODES
    }
    values = {code: item.value for code, item in resolved.items()}
    if (
        any(
            type(values[code]) is not bool
            for code in ("ai.enabled", "ai.send_contract_text", "ai.redact_contact_details")
        )
        or not isinstance(values["ai.model"], str)
        or not values["ai.model"].strip()
        or type(values["ai.monthly_token_budget"]) is not int
        or values["ai.monthly_token_budget"] < 0
    ):
        raise AISettingsRefused("AI_INVALID_CONFIGURATION")
    return AISettings(
        model=values["ai.model"],
        monthly_token_budget=values["ai.monthly_token_budget"],
        send_contract_text=values["ai.send_contract_text"],
        redact_contact_details=values["ai.redact_contact_details"],
        registry_enabled=values["ai.enabled"],
        tenant_disabled_at=workspace["ai_disabled_at"],
        platform_disabled=platform_kill_switch,
        workspace_active=workspace["status"] == TenantStatus.ACTIVE.value,
        sources=tuple((code, item.source_id) for code, item in resolved.items()),
    )
