"""RFD-17 industry tenant reference data and draft industry policy templates (docs/02-PRD.md §2.4,
§2.10; §5.3 BR-POL-03; 03 REQ-POL-009, REQ-DEMO-001; BUILD_SPEC RFD-17, BS3-D-10; D-14a).

As the RFD-16 module: the test database is shared by the session and the persona users are global
identities, so the module seeds WLD-T-02 to WLD-T-07 through ``seed_demo`` under stand-in tenant
codes, with the PRD §2.3 cast at module-unique ``demo.erev`` addresses, and reads what the persona
commands wrote.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pyotp
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, platform_session, tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    entity_book,
    fiscal_calendar,
    legal_entity,
    pob_template,
    pob_template_version,
    registry_version,
    tenant,
    tenant_currency,
)
from erev_api.domain.demo import builders, personas, seed, tenants
from erev_api.domain.demo.industry import CLUSTER_BY_WLD
from erev_api.domain.demo.industry import reference as industry_reference
from erev_api.domain.demo.personas import Persona
from erev_api.domain.policies import industry
from erev_api.enums import BookCode
from erev_api.files.store import LocalFileStore
from erev_api.registry.resolve import resolve
from sqlalchemy import and_, select
from support.clock import frozen_clock
from support.db import TestDatabase

# Seeding six tenants through the persona commands takes well over ten seconds (DG-TST-08).
pytestmark = pytest.mark.slow

REQUEST_ID = "tests-rfd-17"
INDUSTRY = tuple(demo for demo in tenants.CATALOGUE if demo.group == "industry")
# PRD §2.10: entity code → (functional currency, books).
ENTITIES: Mapping[str, Mapping[str, tuple[str, frozenset[str]]]] = {
    "WLD-T-02": {
        "FS-US": ("USD", frozenset({"ASC606"})),
        "FS-UK": ("GBP", frozenset({"ASC606", "IFRS15"})),
    },
    "WLD-T-03": {
        "BR-US": ("USD", frozenset({"ASC606"})),
        "BR-DE": ("EUR", frozenset({"ASC606"})),
        "BR-JP": ("JPY", frozenset({"ASC606"})),
    },
    "WLD-T-04": {
        "GE-US": ("USD", frozenset({"ASC606"})),
        "GE-CA": ("CAD", frozenset({"ASC606"})),
    },
    "WLD-T-05": {
        "JS-US": ("USD", frozenset({"ASC606"})),
        "JS-CA": ("CAD", frozenset({"ASC606"})),
    },
    "WLD-T-06": {"RB-US": ("USD", frozenset({"ASC606"}))},
    "WLD-T-07": {
        "WM-US": ("USD", frozenset({"ASC606"})),
        "WM-IE": ("EUR", frozenset({"ASC606"})),
        "WM-UK": ("GBP", frozenset({"ASC606", "IFRS15"})),
    },
}
RIVERBEND = "WLD-T-06"


@dataclass(frozen=True, slots=True)
class World:
    tenant_ids: Mapping[str, UUID]  # WLD id → tenant id
    codes: Mapping[str, str]  # WLD id → stand-in code
    cast: tuple[Persona, ...]
    clock: FrozenClock


def _read(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_read(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _cast(suffix: str) -> tuple[Persona, ...]:
    """The PRD §2.3 personas at addresses of this module only (WLD-R-04 domain kept)."""
    return tuple(
        replace(persona, email=f"{persona.key}.{suffix}@{personas.DEMO_DOMAIN}")
        for persona in personas.PERSONAS
    )


def _build(keyring: KeyRing, root: Path, cast: tuple[Persona, ...], env: tuple[str, str]) -> World:
    """Seed stand-ins of WLD-T-02 to WLD-T-07 under fresh codes through ``seed_demo``."""
    codes = {demo.wld_id: f"ind-{secrets.token_hex(4)}" for demo in INDUSTRY}
    stand_ins = tuple(replace(demo, code=codes[demo.wld_id]) for demo in INDUSTRY)
    clock = frozen_clock()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, *stand_ins))
        patch.setattr(
            builders,
            "BUILDERS",
            {demo.wld_id: (industry_reference.build,) for demo in INDUSTRY},
        )
        result = seed.seed_demo(
            [demo.code for demo in stand_ins],
            clock,
            keyring=keyring,
            files=LocalFileStore(root / "files"),
            secrets=seed.DemoSecrets(password=env[0], totp_secret=env[1]),
            credentials_path=root / "run" / seed.CREDENTIALS_FILE,
            request_id=REQUEST_ID,
            personas=cast,
        )
    assert result.outcomes == tuple((demo.code, "seeded") for demo in stand_ins)
    with platform_session("tenant_directory", actor_user_id=None, request_id=REQUEST_ID) as db:
        found = db.execute(
            select(tenant.c.code, tenant.c.id).where(tenant.c.code.in_(sorted(codes.values())))
        ).all()
    by_code = {str(code): UUID(str(tenant_id)) for code, tenant_id in found}
    return World(
        tenant_ids={wld_id: by_code[code] for wld_id, code in codes.items()},
        codes=codes,
        cast=cast,
        clock=clock,
    )


@pytest.fixture(scope="module")
def demo_env() -> tuple[str, str]:
    return (f"Seed-{secrets.token_urlsafe(12)}", pyotp.random_base32())


@pytest.fixture(scope="module")
def cast() -> tuple[Persona, ...]:
    return _cast(secrets.token_hex(3))


@pytest.fixture(scope="module")
def world(
    test_database: TestDatabase,
    keyring: KeyRing,
    demo_env: tuple[str, str],
    cast: tuple[Persona, ...],
    tmp_path_factory: pytest.TempPathFactory,
) -> World:
    return _build(keyring, tmp_path_factory.mktemp("rfd-17"), cast, demo_env)


def _template_rows(tenant_id: UUID) -> list[dict[str, Any]]:
    joined = pob_template_version.join(
        pob_template,
        and_(
            pob_template.c.tenant_id == pob_template_version.c.tenant_id,
            pob_template.c.id == pob_template_version.c.pob_template_id,
        ),
    )
    return _rows(
        tenant_id,
        select(
            pob_template.c.code,
            pob_template_version.c.status,
            pob_template_version.c.effective_from,
        ).select_from(joined),
    )


def test_industry_entities_and_books(world: World) -> None:
    assert set(world.tenant_ids) == set(ENTITIES) == set(CLUSTER_BY_WLD)
    for wld_id, expected in ENTITIES.items():
        tenant_id = world.tenant_ids[wld_id]
        entities = _rows(
            tenant_id,
            select(
                legal_entity.c.id,
                legal_entity.c.code,
                legal_entity.c.functional_currency,
                legal_entity.c.parent_entity_id,
                legal_entity.c.is_active,
                fiscal_calendar.c.fiscal_year_start_month,
            ).select_from(
                legal_entity.join(
                    fiscal_calendar,
                    and_(
                        fiscal_calendar.c.tenant_id == legal_entity.c.tenant_id,
                        fiscal_calendar.c.id == legal_entity.c.calendar_id,
                    ),
                )
            ),
        )
        by_code = {row["code"]: row for row in entities}
        books = _rows(
            tenant_id,
            select(legal_entity.c.code, entity_book.c.book_code)
            .select_from(
                entity_book.join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == entity_book.c.tenant_id,
                        legal_entity.c.id == entity_book.c.entity_id,
                    ),
                )
            )
            .where(entity_book.c.is_enabled.is_(True)),
        )
        enabled: dict[str, set[str]] = {}
        for row in books:
            enabled.setdefault(str(row["code"]), set()).add(str(row["book_code"]))
        assert {
            code: (row["functional_currency"], frozenset(enabled.get(code, ())))
            for code, row in by_code.items()
        } == dict(expected), wld_id
        assert all(row["is_active"] for row in entities), wld_id
        assert {row["fiscal_year_start_month"] for row in entities} == {1}, wld_id
        # The first PRD §2.10 entity is the reporting parent of the others.
        first = industry_reference.entity_codes(wld_id)[0]
        parent_id = by_code[first]["id"]
        assert {code: row["parent_entity_id"] for code, row in by_code.items()} == {
            code: (None if code == first else parent_id) for code in by_code
        }, wld_id
        currencies = {
            str(row["currency_code"])
            for row in _rows(
                tenant_id,
                select(tenant_currency.c.currency_code).where(
                    tenant_currency.c.is_enabled.is_(True)
                ),
            )
        }
        assert currencies == {"USD", *(currency for currency, _ in expected.values())}, wld_id


def test_each_cluster_has_draft_templates(world: World) -> None:
    for wld_id, cluster_code in CLUSTER_BY_WLD.items():
        tenant_id = world.tenant_ids[wld_id]
        cluster = industry.cluster_of(cluster_code)
        expected = {template.code for template in cluster.templates}
        assert expected, cluster_code
        rows = _template_rows(tenant_id)
        drafts = {
            str(row["code"])
            for row in rows
            if str(row["status"]) == "DRAFT" and str(row["code"]).startswith("IND-")
        }
        assert drafts == expected, wld_id
        assert all(row["effective_from"] is None for row in rows), wld_id
        # BR-POL-03: the drafts hold the cluster prefix and nothing of the cluster is published.
        assert all(code.startswith(f"IND-{cluster_code}-") for code in drafts), wld_id
        assert not any(
            str(row["status"]) == "PUBLISHED" and str(row["code"]).startswith("IND-")
            for row in rows
        ), wld_id
        policy_drafts = _rows(
            tenant_id,
            select(registry_version.c.status, registry_version.c["values"]).where(
                registry_version.c.scope == "TENANT",
                registry_version.c.category == "ACCOUNTING_POLICY",
                registry_version.c.status == "DRAFT",
            ),
        )
        assert [row["values"] for row in policy_drafts] == [dict(cluster.tenant_values)], wld_id


def test_riverbend_engine_billing_policy(world: World) -> None:
    tenant_id = world.tenant_ids[RIVERBEND]
    published = _rows(
        tenant_id,
        select(registry_version.c["values"], registry_version.c.effective_from).where(
            registry_version.c.scope == "TENANT",
            registry_version.c.category == "ACCOUNTING_POLICY",
            registry_version.c.status == "PUBLISHED",
        ),
    )
    assert [row["values"] for row in published] == [{"billing.posting": "ENGINE"}]
    effective_from = published[0]["effective_from"]
    assert isinstance(effective_from, datetime)
    assert effective_from > world.clock.now()
    with tenant_session(_read(tenant_id), read_only=True) as session:
        before = resolve(
            session, "billing.posting", book_code=BookCode.ASC606, known_at=world.clock.now()
        )
        after = resolve(
            session, "billing.posting", book_code=BookCode.ASC606, known_at=effective_from
        )
    # POL-004 is period-scoped: the framework default until the version's first period, then ENGINE.
    assert (before.value, after.value) == ("ERP", "ENGINE")

    # D-14a: RECEIVABLE_CONTRA is mapped for implicit price concessions (JET-04c).
    rules = _rows(
        tenant_id,
        select(account_mapping_rule.c.account_role, account_mapping_version.c.status)
        .select_from(
            account_mapping_rule.join(
                account_mapping_version,
                and_(
                    account_mapping_version.c.tenant_id == account_mapping_rule.c.tenant_id,
                    account_mapping_version.c.id
                    == account_mapping_rule.c.account_mapping_version_id,
                ),
            )
        )
        .where(account_mapping_version.c.status == "PUBLISHED"),
    )
    roles = {str(row["account_role"]) for row in rules}
    assert "RECEIVABLE_CONTRA" in roles
    assert "REVENUE" in roles
    # The other industry tenants post billing through the ERP (PRD §2.10 GL targets) and map no
    # receivable contra.
    for wld_id, other_id in world.tenant_ids.items():
        if wld_id == RIVERBEND:
            continue
        other_rules = _rows(
            other_id,
            select(account_mapping_rule.c.account_role).where(
                account_mapping_rule.c.account_role == "RECEIVABLE_CONTRA"
            ),
        )
        assert other_rules == [], wld_id
        with tenant_session(_read(other_id), read_only=True) as session:
            other = resolve(
                session,
                "billing.posting",
                book_code=BookCode.ASC606,
                known_at=datetime(2027, 1, 1, tzinfo=UTC),
            )
        assert other.value == "ERP", wld_id
