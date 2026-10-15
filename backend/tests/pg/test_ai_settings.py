"""Effective AI switches and settings are read from actual tenant registry versions."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import tenant
from erev_api.domain.ai.settings import AISettingsRefused, load_settings
from erev_api.enums import RegistryCategory
from sqlalchemy import update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_registry_version, publish_registry_version

pytestmark = pytest.mark.pg
VALUES: dict[str, Any] = {
    "ai.enabled": True,
    "ai.send_contract_text": True,
    "ai.model": "configured-test-model",
    "ai.monthly_token_budget": 2000,
    "ai.redact_contact_details": True,
}


@pytest.fixture
def world(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> Iterator[tuple[Session, UUID]]:
    target = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with tenant_session(DbContext(target, None, "*")) as session:
        yield session, target


def test_default_off_and_draft_enablement_ignored(
    world: tuple[Session, UUID], clock: FrozenClock
) -> None:
    session, target = world
    before = load_settings(session, tenant_id=target, now=clock.now(), platform_kill_switch=False)
    assert not before.enabled
    assert not before.send_contract_text
    assert before.redact_contact_details
    with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
        before.require_available()
    insert_registry_version(session, tenant_id=target, category=RegistryCategory.AI, values=VALUES)
    assert (
        load_settings(session, tenant_id=target, now=clock.now(), platform_kill_switch=False)
        == before
    )


def test_published_values_and_provenance(world: tuple[Session, UUID], clock: FrozenClock) -> None:
    session, target = world
    version = publish_registry_version(
        session, tenant_id=target, category=RegistryCategory.AI, values=VALUES, at=clock.now()
    )
    settings = load_settings(session, tenant_id=target, now=clock.now(), platform_kill_switch=False)
    settings.require_available()
    assert settings.model == "configured-test-model"
    assert settings.monthly_token_budget == 2000
    assert settings.send_contract_text and settings.redact_contact_details
    assert {source for _, source in settings.sources} == {version}
    disabled = load_settings(session, tenant_id=target, now=clock.now(), platform_kill_switch=True)
    assert not disabled.enabled
    assert disabled.model == settings.model


def test_immediate_tenant_turnoff_overrides_published_enablement(
    world: tuple[Session, UUID], clock: FrozenClock
) -> None:
    session, target = world
    publish_registry_version(
        session, tenant_id=target, category=RegistryCategory.AI, values=VALUES, at=clock.now()
    )
    session.execute(
        update(tenant)
        .where(tenant.c.id == target)
        .values(ai_disabled_at=clock.now(), ai_disabled_by_kind="SYSTEM", updated_by_kind="SYSTEM")
    )
    settings = load_settings(session, tenant_id=target, now=clock.now(), platform_kill_switch=False)
    assert settings.registry_enabled and not settings.enabled
    assert settings.tenant_disabled_at == clock.now()


def test_future_publication_is_not_used_early(
    world: tuple[Session, UUID], clock: FrozenClock
) -> None:
    session, target = world
    later = clock.now() + timedelta(days=1)
    publish_registry_version(
        session, tenant_id=target, category=RegistryCategory.AI, values=VALUES, at=later
    )
    assert not load_settings(
        session, tenant_id=target, now=clock.now(), platform_kill_switch=False
    ).enabled
    assert load_settings(session, tenant_id=target, now=later, platform_kill_switch=False).enabled


def test_inactive_workspace_cannot_enable_ai(
    world: tuple[Session, UUID], clock: FrozenClock
) -> None:
    session, target = world
    publish_registry_version(
        session, tenant_id=target, category=RegistryCategory.AI, values=VALUES, at=clock.now()
    )
    session.execute(
        update(tenant)
        .where(tenant.c.id == target)
        .values(status="SUSPENDED", updated_by_kind="SYSTEM")
    )
    assert not load_settings(
        session, tenant_id=target, now=clock.now(), platform_kill_switch=False
    ).enabled


@pytest.mark.parametrize(
    "changes",
    [
        {"ai.enabled": "true"},
        {"ai.send_contract_text": 1},
        {"ai.redact_contact_details": None},
        {"ai.monthly_token_budget": True},
        {"ai.monthly_token_budget": -1},
        {"ai.monthly_token_budget": 1.5},
        {"ai.model": " "},
    ],
)
def test_invalid_configuration_never_coerced(
    world: tuple[Session, UUID], clock: FrozenClock, changes: dict[str, Any]
) -> None:
    session, target = world
    publish_registry_version(
        session,
        tenant_id=target,
        category=RegistryCategory.AI,
        values=VALUES | changes,
        at=clock.now(),
    )
    with pytest.raises(AISettingsRefused, match="AI_INVALID_CONFIGURATION"):
        load_settings(session, tenant_id=target, now=clock.now(), platform_kill_switch=False)


def test_wrong_tenant_and_naive_clock_refused(
    world: tuple[Session, UUID], clock: FrozenClock, keyring: KeyRing
) -> None:
    session, target = world
    other = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with pytest.raises(AISettingsRefused, match="AI_WORKSPACE_UNAVAILABLE"):
        load_settings(session, tenant_id=other, now=clock.now(), platform_kill_switch=False)
    with pytest.raises(AISettingsRefused, match="AI_INVALID_CONFIGURATION"):
        load_settings(
            session,
            tenant_id=target,
            now=clock.now().replace(tzinfo=None),
            platform_kill_switch=False,
        )
