"""``erev db reset`` counts the tenants without the demo marker (dev-guide DG-ENV-13 rev 1.200;
supervisor ruling R-120 (i)): the count the command refuses on, measured on the database through
the platform session it uses. The test database holds the tenants of other tests, so every
assertion is a difference."""

from __future__ import annotations

import secrets
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.controls import reset
from erev_api.db import new_id
from erev_api.db.session import (
    identity_session,
    name_platform_tenant,
    owner_engine,
    platform_session,
)
from erev_api.db.tables import security_event, tenant
from erev_api.domain.platform.provisioning import (
    OperatorActor,
    TenantProvisionRequest,
    provision_tenant,
)
from erev_api.enums import PrincipalKind, TenantKind, TenantStatus
from sqlalchemy import func, insert, select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_sandbox_tenant

SYSTEM = {
    "created_by_kind": PrincipalKind.SYSTEM.value,
    "updated_by_kind": PrincipalKind.SYSTEM.value,
}


def _demo_tenant(keyring: KeyRing, clock: FrozenClock) -> UUID:
    code = f"demo-{secrets.token_hex(6)}"
    request = TenantProvisionRequest(
        code=code,
        display_name=f"Tenant {code}",
        reporting_currency="USD",
        is_demo=True,
        admin_email=f"admin@{code}.test",
    )
    actor = OperatorActor(
        channel="CLI", operator_user_id=None, os_user="tests", request_id=f"r-reset-{code}"
    )
    return tenant_id_of(provision_tenant(request, actor=actor, clock=clock, keyring=keyring))


def _sandbox_of(source: UUID, keyring: KeyRing) -> UUID:
    """A tenant row of kind ``sandbox`` that names its source, as a sandbox load writes it:
    without the demo marker of its own."""
    tenant_id = new_id()
    code = f"sandbox-{secrets.token_hex(6)}"
    with platform_session(
        "provisioning", actor_user_id=None, request_id=f"tests-{code}", keyring=keyring
    ) as session:
        session.execute(
            insert(tenant).values(
                id=tenant_id,
                code=code,
                kind=TenantKind.SANDBOX.value,
                status=TenantStatus.ACTIVE.value,
                display_name=f"Tenant {code}",
                reporting_currency="USD",
                is_demo=False,
                source_tenant_id=source,
                audit_hmac_key_id=keyring.new_tenant_audit_key_id(tenant_id),
                setup_completed_at=None,
                **SYSTEM,
            )
        )
        name_platform_tenant(session, tenant_id)
    return tenant_id


def _uses_of_the_scope() -> int:
    with identity_session(request_id="tests-reset-scope") as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(security_event)
                .where(security_event.c.kind == "PLATFORM_SCOPE_USED")
            ).scalar_one()
        )


def test_a_tenant_counts_by_its_demo_marker_and_a_sandbox_by_its_source(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    with owner_engine().connect() as connection:
        assert reset.tenant_table_exists(connection) is True
    before = reset.unmarked_tenants(keyring=keyring)

    demo = _demo_tenant(keyring, clock)
    assert reset.unmarked_tenants(keyring=keyring) == before, "a tenant with the marker"
    _sandbox_of(demo, keyring)
    assert reset.unmarked_tenants(keyring=keyring) == before, "its sandbox counts by its source"

    plain = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    assert reset.unmarked_tenants(keyring=keyring) == before + 1, "a tenant without the marker"
    _sandbox_of(plain, keyring)
    assert reset.unmarked_tenants(keyring=keyring) == before + 2, "and its sandbox"
    insert_sandbox_tenant(keyring)
    assert reset.unmarked_tenants(keyring=keyring) == before + 3, "a sandbox without a source"

    # The count goes through the one door across tenants, which records every use (05 TXN-07).
    uses = _uses_of_the_scope()
    reset.unmarked_tenants(keyring=keyring)
    assert _uses_of_the_scope() == uses + 1
