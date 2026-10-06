"""Numbering series KRN-NUM (dev-guide §5.14 DG-KRN-NUM-01, DG-KRN-NUM-02; 04 T-PLT-26; BUILD_SPEC
PLF-9)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import numbering_series
from erev_api.enums import TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.numbering import ensure_entity_series, next_number, next_numbers
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of


@pytest.fixture
def tenant_id(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    return tenant_id_of(tenant_factory(keyring=keyring))


@contextmanager
def _uow(
    tenant_id: UUID, *, clock: FrozenClock, keyring: KeyRing, settings: Settings
) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-numbering",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        yield uow


def test_krn_num_01_allocation_and_format(
    tenant_id: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    # Provisioning numbered the bootstrap admin grant APR-000001 (04 §14.3 item 2).
    with _uow(tenant_id, clock=clock, keyring=keyring, settings=app_settings) as uow:
        assert next_number(uow, "APPROVAL") == "APR-000002"
        assert next_number(uow, "APPROVAL") == "APR-000003"
        assert next_numbers(uow, "CONTRACT", 3) == ["CON-000001", "CON-000002", "CON-000003"]
        uow.commit()
    with _uow(tenant_id, clock=clock, keyring=keyring, settings=app_settings) as uow:
        assert next_number(uow, "CONTRACT") == "CON-000004"
        with pytest.raises(ValueError):
            next_numbers(uow, "CONTRACT", 0)
        with pytest.raises(LookupError):
            next_number(uow, "INVOICE")
        uow.commit()


def test_krn_num_02_rollback_releases_number(
    tenant_id: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    with _uow(tenant_id, clock=clock, keyring=keyring, settings=app_settings) as uow:
        assert next_number(uow, "APPROVAL") == "APR-000002"
        # Left without commit: the unit of work rolls back.
    with _uow(tenant_id, clock=clock, keyring=keyring, settings=app_settings) as uow:
        assert next_number(uow, "APPROVAL") == "APR-000002"
        uow.commit()


def test_krn_num_01_entity_je_series(
    tenant_id: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    entity_id = new_id()
    with _uow(tenant_id, clock=clock, keyring=keyring, settings=app_settings) as uow:
        with pytest.raises(LookupError):
            next_number(uow, "JE", str(entity_id))
        ensure_entity_series(uow, entity_id, "US01")
        ensure_entity_series(uow, entity_id, "US01")
        assert next_number(uow, "JE", str(entity_id)) == "JE-US01-000001"
        assert next_numbers(uow, "JE", 2, str(entity_id)) == ["JE-US01-000002", "JE-US01-000003"]
        row = uow.session.execute(
            select(numbering_series).where(numbering_series.c.scope_key == str(entity_id))
        ).mappings()
        rows = list(row)
        uow.commit()
    assert len(rows) == 1
    assert (rows[0]["series_code"], rows[0]["is_gapless"], rows[0]["next_value"]) == ("JE", True, 4)
