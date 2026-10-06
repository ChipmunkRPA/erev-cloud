"""The audit key of a tenant a job creates (05 KEY-05; DG-KRN-KEY-06; 05 SBX-02, SBX-07; supervisor
rulings R-43 (d) and R-60 (d)): ``sandboxes.provision_audit_key`` goes through the job runtime's
provisioning authority. Hosted, that is the Secret Manager provisioner — here the in-process fake
of ``tests/support/fake_gcp.py`` with the provisioning identity's permission set, and with the
accessor-only set of the api and worker identities, which must fail closed BY NAME (412
``precondition-failed`` ``SANDBOX_KEY_PROVISIONING_DENIED``) and not as an unexpected error; an
outage keeps its own error. Without an authority the key derives from the master key, as
``tenant.provision`` does locally.

The database witness that the sandbox load calls this seam and commits no tenant when it refuses
is ``tests/domain/platform/test_sandbox_load.py``."""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.adapters.keys.provider import GcpKeyProvider
from erev_api.adapters.secrets.provision import (
    GcpTenantKeyProvisioner,
    TenantKeyProvisioningError,
)
from erev_api.adapters.secrets.store import GcpSecretManagerStore
from erev_api.auth.keyring import HostedTenantKeyProvisioner, KeyRing, provisioning_denied
from erev_api.clock import FrozenClock
from erev_api.domain.platform import sandboxes as sb
from erev_api.jobs.context import JobRuntime
from erev_api.problems import Problem
from support.clock import FROZEN_AT
from support.fake_gcp import (
    ACCESSOR_PERMISSIONS,
    PROVISIONER_PERMISSIONS,
    TENANT_SECRET_INFIX,
    FakeKms,
    FakeSecretManager,
    ServiceUnavailable,
)

PROJECT = "erev-staging-example"
PREFIX = "erev-"
LOCATION = "europe-west1"
KMS_KEY = f"projects/{PROJECT}/locations/{LOCATION}/keyRings/erev/cryptoKeys/erev-app-kek"
SANDBOX = UUID("0191e0a0-0000-7000-8000-0000000000b1")
SECRET_PATH = f"projects/{PROJECT}/secrets/{PREFIX}audit-hmac-{SANDBOX}"


def _hosted(secrets: FakeSecretManager, permissions: frozenset[str]) -> JobRuntime:
    """A worker runtime whose key ring reads through the accessor path and whose provisioning
    authority creates tenant secrets with ``permissions`` (``worker.build_runtime`` hosted)."""
    store = GcpSecretManagerStore(
        PROJECT, prefix=PREFIX, client=secrets.client(ACCESSOR_PERMISSIONS)
    )
    keyring = KeyRing(GcpKeyProvider(store, kms_key=KMS_KEY, kms_client=FakeKms()))
    provisioner = GcpTenantKeyProvisioner(
        PROJECT,
        prefix=PREFIX,
        location=LOCATION,
        client=secrets.client(permissions, scope_infix=TENANT_SECRET_INFIX),
    )
    return JobRuntime(
        clock=FrozenClock(FROZEN_AT),
        keyring=keyring,
        files=None,
        key_provisioner=HostedTenantKeyProvisioner(provisioner, keyring),
    )


def test_hosted_the_sandbox_key_is_created_and_read_back() -> None:
    secrets = FakeSecretManager()
    runtime = _hosted(secrets, PROVISIONER_PERMISSIONS)
    keyring = runtime.keyring
    assert keyring is not None
    key_id = sb.provision_audit_key(runtime, keyring, SANDBOX)
    # the id the loader stamped on the tenant row before it asked for the key (DG-KRN-KEY-06)
    assert key_id == keyring.new_tenant_audit_key_id(SANDBOX) == f"audit-hmac:{SANDBOX}:1"
    (payload,) = secrets.version_payloads(SECRET_PATH)
    assert keyring.tenant_audit_key(key_id) == bytes.fromhex(payload.decode())
    # a second load attempt for the same id provisions nothing new
    assert sb.provision_audit_key(runtime, keyring, SANDBOX) == key_id
    assert len(secrets.version_payloads(SECRET_PATH)) == 1


def test_hosted_an_identity_without_the_provisioning_role_fails_closed_by_name() -> None:
    """The api and worker identities hold the accessor set (hosted runtime contract): asked to
    create a sandbox's key they are denied, nothing is created, and the loader — which asks
    inside the transaction that inserts the tenant row — commits no tenant. Ruling R-60 (d): the
    denial is a NAMED refusal of the load, so the job's problem says what has to change in the
    deployment (item OPS-SBX-KEY-1) instead of "unexpected error"."""
    secrets = FakeSecretManager()
    runtime = _hosted(secrets, ACCESSOR_PERMISSIONS)
    keyring = runtime.keyring
    assert keyring is not None
    with pytest.raises(Problem) as refused:
        sb.provision_audit_key(runtime, keyring, SANDBOX)
    problem = refused.value
    assert (problem.slug, problem.status) == ("precondition-failed", 412)
    [error] = problem.errors
    assert (error.field, error.rule_id) == (None, "SANDBOX_KEY_PROVISIONING_DENIED")
    assert error.message == sb.KEY_DENIED and str(SANDBOX) not in error.message
    # The provider's own error is the cause, for the log; it is what the kernel classified.
    cause = problem.__cause__
    assert isinstance(cause, TenantKeyProvisioningError) and cause.kind == "denied"
    assert provisioning_denied(cause) and not provisioning_denied(problem)
    assert secrets.secrets == {}


def test_hosted_an_outage_is_not_the_named_refusal() -> None:
    """Only the standing denial is named. While Secret Manager does not answer, the provisioner's
    own error reaches the job, whose retry policy applies; nothing is created."""
    secrets = FakeSecretManager()
    runtime = _hosted(secrets, PROVISIONER_PERMISSIONS)
    keyring = runtime.keyring
    assert keyring is not None
    secrets.faults.fail_next("create_secret", ServiceUnavailable("planted outage"))
    with pytest.raises(TenantKeyProvisioningError) as failed:
        sb.provision_audit_key(runtime, keyring, SANDBOX)
    assert failed.value.kind == "transient" and not provisioning_denied(failed.value)
    assert secrets.secrets == {}


def test_without_an_authority_the_key_derives_locally(keyring: KeyRing) -> None:
    runtime = JobRuntime(clock=FrozenClock(FROZEN_AT), keyring=keyring, files=None)
    assert runtime.key_provisioner is None
    key_id = sb.provision_audit_key(runtime, keyring, SANDBOX)
    assert key_id == keyring.new_tenant_audit_key_id(SANDBOX)
    assert len(keyring.tenant_audit_key(key_id)) == 32
