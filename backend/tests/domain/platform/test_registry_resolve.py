"""Registry versions and setting resolution (dev-guide §5.15 DG-KRN-REG-01, DG-KRN-REG-06; 04
T-PLT-31, T-PLT-32; POLICIES §0.5; 05 SAR-10; BUILD_SPEC PLF-13)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.auth import sessions
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import audit_event, registry_version, user_session
from erev_api.enums import BookCode, RegistryCategory, RegistryScope, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.registry.resolve import PARAMETERS, resolve, setting
from erev_api.registry.versions import VERSION_SCOPES, mark_tested, schema_errors
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import select
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.principals import PASSWORD, member
from support.rows import insert_registry_version, publish_registry_version

CONCURRENCY = "platform.job_concurrency"
# Before the frozen clock and before any wall-clock transaction timestamp of a test run.
PUBLISHED_AT = datetime(2026, 9, 1, tzinfo=UTC)
LATER = FROZEN_AT + timedelta(hours=1)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring))


@contextmanager
def _uow(
    tenant_id: UUID, *, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=system_principal(tenant_id, on_behalf_of_id=None),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-registry-versions",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        yield uow


def test_krn_reg_01_tenant_version_over_default(tenant_id: UUID) -> None:
    with tenant_session(_context(tenant_id)) as session:
        assert setting(session, CONCURRENCY) == 4
        default = resolve(session, CONCURRENCY, book_code=BookCode.ASC606, known_at=FROZEN_AT)
        version_id = publish_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.PLATFORM,
            values={CONCURRENCY: 2},
            at=PUBLISHED_AT,
        )
    with tenant_session(_context(tenant_id)) as session:
        assert setting(session, CONCURRENCY) == 2
        resolved = resolve(session, CONCURRENCY, book_code=BookCode.ASC606, known_at=FROZEN_AT)
    assert (default.code, default.value, default.level, default.source_id) == (
        CONCURRENCY,
        4,
        "DEFAULT",
        None,
    )
    assert (resolved.value, resolved.level, resolved.source_id) == (2, "T", version_id)


def test_krn_reg_01_known_at_cutoff(tenant_id: UUID) -> None:
    with tenant_session(_context(tenant_id)) as session:
        publish_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.PLATFORM,
            values={CONCURRENCY: 2},
            at=LATER,
        )
    with tenant_session(_context(tenant_id)) as session:
        before = resolve(session, CONCURRENCY, book_code=BookCode.ASC606, known_at=FROZEN_AT)
        after = resolve(session, CONCURRENCY, book_code=BookCode.ASC606, known_at=LATER)
    assert (before.value, before.level) == (4, "DEFAULT")
    assert (after.value, after.level) == (2, "T")


def test_krn_reg_01_ifrs_default_by_book(tenant_id: UUID) -> None:
    with tenant_session(_context(tenant_id)) as session:
        ifrs = resolve(session, "books.enabled", book_code=BookCode.IFRS15, known_at=FROZEN_AT)
        asc = resolve(session, "books.enabled", book_code=BookCode.ASC606, known_at=FROZEN_AT)
    spec = PARAMETERS["books.enabled"]
    assert (ifrs.value, ifrs.level) == (spec.default_ifrs15, "DEFAULT")
    assert ifrs.value == {"set": ["IFRS15"], "primary": "IFRS15"}
    assert (asc.value, asc.level) == (spec.default_asc606, "DEFAULT")
    assert asc.value == {"set": ["ASC606"], "primary": "ASC606"}


def test_krn_reg_06_level_and_value_validation(
    tenant_id: UUID, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    with tenant_session(_context(tenant_id)) as session:
        tenant_level = insert_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values={"je.posting_mode": "DELTA"},
        )
        entity_level = insert_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.ENTITY,
            entity_id=new_id(),
            values={"billing.posting": "ENGINE"},
        )
        brackets = insert_registry_version(
            session,
            tenant_id=tenant_id,
            category=RegistryCategory.PLATFORM,
            values={"ui.negative_number_style": "BRACKETS"},
        )
    opened = {"app_settings": app_settings, "keyring": keyring, "clock": clock}
    with _uow(tenant_id, **opened) as uow:
        digest = mark_tested(uow, tenant_level)
        uow.commit()
    refusals: dict[str, Problem] = {}
    for name, version_id in (("level", entity_level), ("value", brackets)):
        with _uow(tenant_id, **opened) as uow, pytest.raises(Problem) as excinfo:
            mark_tested(uow, version_id)
        refusals[name] = excinfo.value

    ids = [tenant_level, entity_level, brackets]
    with tenant_session(_context(tenant_id)) as session:
        rows = session.execute(
            select(
                registry_version.c.id, registry_version.c.status, registry_version.c.content_sha256
            ).where(registry_version.c.id.in_(ids))
        ).all()
        actions = session.scalars(
            select(audit_event.c.action).where(audit_event.c.object_id.in_(ids))
        ).all()
    stored = {row.id: (row.status, row.content_sha256) for row in rows}
    assert stored == {
        tenant_level: ("TESTED", digest),
        entity_level: ("DRAFT", None),
        brackets: ("DRAFT", None),
    }
    assert actions == ["registry_version.test"]
    level = refusals["level"]
    assert (level.slug, level.status) == ("policy-level-not-allowed", 422)
    assert [(error.field, error.rule_id) for error in level.errors] == [
        ("values.billing.posting", "POLICY_LEVEL_NOT_ALLOWED")
    ]
    value = refusals["value"]
    assert (value.slug, value.status) == ("validation-failed", 422)
    assert [(error.field, error.rule_id) for error in value.errors] == [
        ("values.ui.negative_number_style", "POLICY_VALUE_INVALID")
    ]


def test_session_idle_minutes_from_registry(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    lena = member(keyring, clock)
    with tenant_session(_context(lena.tenant_id)) as session:
        publish_registry_version(
            session,
            tenant_id=lena.tenant_id,
            category=RegistryCategory.SECURITY,
            values={"platform.session_idle_minutes": 5},
            at=PUBLISHED_AT,
        )
    facts = sessions.RequestFacts(
        request_id="r-registry-idle", source_ip=None, user_agent=None, now=clock.now()
    )
    auth = sessions.sign_in(
        email=lena.email, password=PASSWORD, facts=facts, keyring=keyring, previous_token=None
    )
    with identity_session(request_id="tests-registry-idle") as db:
        row = db.execute(
            select(user_session.c.last_seen_at, user_session.c.idle_expires_at).where(
                user_session.c.id == auth.session.id
            )
        ).one()
    assert row.idle_expires_at == row.last_seen_at + timedelta(minutes=5)
    assert auth.session.idle_expires_at == clock.now() + timedelta(minutes=5)


def test_catalogue_defaults_validate_against_their_schemas() -> None:
    # Every value_schema uses only the keywords schema_errors implements (it raises otherwise),
    # and the defaults and parity values of parameters a registry version can hold validate.
    # Contract-only parameters keep partial defaults: POL-047's annual_rate comes from each
    # contract (SPEC-Q-178).
    checked = 0
    for code, spec in PARAMETERS.items():
        storable = bool(spec.allowed_levels & VERSION_SCOPES)
        for value in (spec.default_asc606, spec.default_ifrs15, spec.legacy_parity_value):
            if value is None:
                continue
            errors = schema_errors(spec.value_schema, value)
            if storable:
                assert errors == [], code
                checked += 1
    assert checked > 100


def test_schema_errors_shapes() -> None:
    relief = PARAMETERS["pob.immaterial_promise_relief"].value_schema
    assert schema_errors(relief, "ASSESS_ALL") == []
    assert (
        schema_errors(relief, {"option": "APPLY_RELIEF", "immaterial_threshold_pct": "0.05"}) == []
    )
    assert schema_errors(relief, {"option": "ASSESS_ALL"}) == [
        "value matches none of the allowed shapes"
    ]
    idle = PARAMETERS["platform.session_idle_minutes"].value_schema
    assert schema_errors(idle, 4) == ["value must be at least 5"]
    assert schema_errors(idle, True) == ["value must be of type integer"]
    tolerance = PARAMETERS["vc.targeted_allocation_tolerance"].value_schema
    assert schema_errors(tolerance, "0.5") == []
    assert schema_errors(tolerance, "1.5") == ["value matches none of the allowed shapes"]
    grouping = PARAMETERS["integration.grouping_fields"].value_schema
    assert schema_errors(grouping, ["a", "a"]) == ["value must not repeat items"]
    with pytest.raises(ValueError, match="unsupported value_schema keywords"):
        schema_errors({"pattern": "^a$"}, "a")
