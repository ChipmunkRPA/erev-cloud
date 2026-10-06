"""Shared fixtures of the platform domain tests (BUILD_SPEC PLF-3, PLF-14)."""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.domain.platform.provisioning import TenantProvisionResult, provision_tenant
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import ACME, ACME_ACTOR


@pytest.fixture(scope="session")
def acme(test_database: TestDatabase, keyring: KeyRing) -> TenantProvisionResult:
    """``acme-test``, provisioned once per session: the provisioning tests read its rows, the
    outbox test relays its invitation, and the duplicate test does not depend on order."""
    return provision_tenant(ACME, actor=ACME_ACTOR, clock=frozen_clock(), keyring=keyring)
