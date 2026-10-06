"""Hosted tenant audit-key bootstrap (05 KEY-05, DPL-33, DPL-36; DG-KRN-KEY-06; hosted runtime
contract §"Persistent key and secret providers"; deployment audit DEP-C; lane P2).

Every test runs against the in-process Secret Manager fake with the provisioning identity's
permission set (the Terraform custom role) or the accessor-only set of the api and worker."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.keys.provider import GcpKeyProvider
from erev_api.adapters.secrets.provision import (
    GcpTenantKeyProvisioner,
    TenantKeyProvisioningError,
)
from erev_api.adapters.secrets.store import GcpSecretManagerStore
from erev_api.auth.keyring import HostedTenantKeyProvisioner, KeyRing, ProvisioningReadbackError
from support import log_guard
from support.fake_gcp import (
    ACCESSOR_PERMISSIONS,
    CREATOR_PERMISSIONS,
    INITIALIZER_PERMISSIONS,
    PROVISIONER_PERMISSIONS,
    TENANT_SECRET_INFIX,
    FakeKms,
    FakeSecretManager,
    PermissionDenied,
    ServiceUnavailable,
    random_hex_key,
)

PROJECT = "erev-staging-example"
PREFIX = "erev-"
LOCATION = "europe-west1"
TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
SECRET_ID = f"{PREFIX}audit-hmac-{TENANT}"
PATH = f"projects/{PROJECT}/secrets/{SECRET_ID}"
KMS_KEY = f"projects/{PROJECT}/locations/{LOCATION}/keyRings/erev/cryptoKeys/erev-app-kek"


def provisioner(
    secrets: FakeSecretManager, permissions: frozenset[str] = PROVISIONER_PERMISSIONS
) -> GcpTenantKeyProvisioner:
    # The provisioning identity of lane P3b: creator role (project-wide create) plus initializer
    # role conditioned on the tenant audit-key prefix.
    return GcpTenantKeyProvisioner(
        PROJECT,
        prefix=PREFIX,
        location=LOCATION,
        client=secrets.client(permissions, scope_infix=TENANT_SECRET_INFIX),
    )


def operations(secrets: FakeSecretManager) -> list[str]:
    return [operation for operation, _ in secrets.calls]


def test_fresh_tenant_gets_a_secret_and_version_1() -> None:
    secrets = FakeSecretManager()
    result = provisioner(secrets).provision_audit_key(TENANT)
    assert result.created and result.version == 1 and result.secret == SECRET_ID
    assert len(result.material) == 32
    assert secrets.version_payloads(PATH) == [result.material.hex().encode("ascii")]
    assert secrets.secrets[PATH].replication == {
        "user_managed": {"replicas": [{"location": LOCATION}]}
    }
    assert operations(secrets) == [
        "create_secret",
        "list_secret_versions",
        "add_secret_version",
        "access_secret_version",
    ]
    accessed = [request["name"] for op, request in secrets.calls if op == "access_secret_version"]
    assert accessed == [f"{PATH}/versions/1"], "read back at the pinned version, never latest"


def test_repeated_provisioning_is_idempotent() -> None:
    secrets = FakeSecretManager()
    first = provisioner(secrets).provision_audit_key(TENANT)
    again = provisioner(secrets).provision_audit_key(TENANT)
    assert not again.created and again.version == 1 and again.material == first.material
    assert len(secrets.version_payloads(PATH)) == 1
    assert operations(secrets)[-4:] == [
        "create_secret",  # already exists
        "get_secret",
        "list_secret_versions",
        "access_secret_version",
    ]


def test_partial_failure_resumes_where_it_stopped() -> None:
    secrets = FakeSecretManager()
    secrets.seed(PATH, [], location=LOCATION)  # the secret exists, the version add never happened
    result = provisioner(secrets).provision_audit_key(TENANT)
    assert result.created and result.version == 1
    assert len(secrets.version_payloads(PATH)) == 1

    interrupted = FakeSecretManager()
    interrupted.faults.fail_next("add_secret_version", ServiceUnavailable())
    with pytest.raises(TenantKeyProvisioningError) as excinfo:
        provisioner(interrupted).provision_audit_key(TENANT)
    assert excinfo.value.kind == "transient" and PATH in interrupted.secrets
    resumed = provisioner(interrupted).provision_audit_key(TENANT)
    assert resumed.created and len(interrupted.version_payloads(PATH)) == 1


def test_existing_enabled_version_1_is_reused_unchanged() -> None:
    secrets = FakeSecretManager()
    material = random_hex_key()
    secrets.seed(PATH, [(material.encode(), "ENABLED")])
    result = provisioner(secrets).provision_audit_key(TENANT)
    assert not result.created and result.material == bytes.fromhex(material)
    assert "add_secret_version" not in operations(secrets)


@pytest.mark.parametrize(
    "versions",
    [
        [(b"not-hexadecimal-material", "ENABLED")],
        [(random_hex_key()[:-2].encode(), "ENABLED")],
        [(random_hex_key().encode(), "DISABLED")],
        [(random_hex_key().encode(), "DESTROYED"), (random_hex_key().encode(), "ENABLED")],
    ],
)
def test_malformed_or_unusable_secret_fails_closed(versions: list[tuple[bytes, str]]) -> None:
    secrets = FakeSecretManager()
    secrets.seed(PATH, versions)
    before = secrets.version_payloads(PATH)
    with pytest.raises(TenantKeyProvisioningError) as excinfo:
        provisioner(secrets).provision_audit_key(TENANT)
    assert excinfo.value.kind == "malformed" and excinfo.value.secret == SECRET_ID
    assert secrets.version_payloads(PATH) == before, "nothing is added, disabled or destroyed"
    for payload, _ in versions:
        assert payload.decode("utf-8", "replace") not in str(excinfo.value)


def test_accessor_identity_cannot_provision() -> None:
    secrets = FakeSecretManager()
    with pytest.raises(TenantKeyProvisioningError) as excinfo:
        provisioner(secrets, ACCESSOR_PERMISSIONS).provision_audit_key(TENANT)
    assert excinfo.value.kind == "denied" and excinfo.value.secret == SECRET_ID
    assert secrets.secrets == {}


def test_provider_outage_fails_closed() -> None:
    secrets = FakeSecretManager()
    secrets.faults.fail_next("create_secret", ServiceUnavailable())
    with pytest.raises(TenantKeyProvisioningError) as excinfo:
        provisioner(secrets).provision_audit_key(TENANT)
    assert excinfo.value.kind == "transient"
    assert secrets.secrets == {}


def test_concurrent_provisioner_keeps_version_1_and_preserves_the_surplus() -> None:
    secrets = FakeSecretManager()
    competitor = random_hex_key().encode()

    def race(path: str) -> None:
        secrets.client().add_secret_version(
            request={"parent": path, "payload": {"data": competitor}}
        )

    secrets.before_add_version = race
    with log_guard.capture() as events:
        result = provisioner(secrets).provision_audit_key(TENANT)
    assert result.version == 1 and result.material == bytes.fromhex(competitor.decode())
    assert not result.created
    payloads = secrets.version_payloads(PATH)
    assert len(payloads) == 2 and payloads[0] == competitor, "historic versions are never destroyed"
    surplus = [
        event for event in events if event.get("event") == "keys.tenant_secret_surplus_version"
    ]
    assert [(event["secret_id"], event["version"]) for event in surplus] == [(SECRET_ID, 2)]


def test_hosted_provisioner_reads_back_through_the_key_ring() -> None:
    secrets = FakeSecretManager()
    store = GcpSecretManagerStore(
        PROJECT, prefix=PREFIX, client=secrets.client(ACCESSOR_PERMISSIONS)
    )
    keyring = KeyRing(GcpKeyProvider(store, kms_key=KMS_KEY, kms_client=FakeKms()))
    hosted = HostedTenantKeyProvisioner(provisioner(secrets), keyring)
    key_id = hosted.provision_audit_key(TENANT)
    assert key_id == f"audit-hmac:{TENANT}:1"
    assert keyring.tenant_audit_key(key_id) == bytes.fromhex(
        secrets.version_payloads(PATH)[0].decode()
    )

    # The read-back goes through the accessor path and must return the provisioned material.
    other = FakeSecretManager()
    other.seed(PATH, [(random_hex_key().encode(), "ENABLED")])
    foreign = KeyRing(
        GcpKeyProvider(
            GcpSecretManagerStore(
                PROJECT, prefix=PREFIX, client=other.client(ACCESSOR_PERMISSIONS)
            ),
            kms_key=KMS_KEY,
            kms_client=FakeKms(),
        )
    )
    with pytest.raises(ProvisioningReadbackError):
        HostedTenantKeyProvisioner(provisioner(secrets), foreign).provision_audit_key(TENANT)


def test_no_key_material_in_logs_or_errors() -> None:
    secrets = FakeSecretManager()
    with log_guard.capture() as events:
        result = provisioner(secrets).provision_audit_key(TENANT)
    log_guard.check(events)
    dump = json.dumps(events, default=str)
    assert result.material.hex() not in dump
    assert "keys.tenant_secret_provisioned" in dump and SECRET_ID in dump
    denied: Any = None
    try:
        provisioner(secrets, frozenset()).provision_audit_key(TENANT)
    except TenantKeyProvisioningError as error:
        denied = error
    assert denied is not None and result.material.hex() not in str(denied)


def test_two_role_boundary_is_exactly_what_the_workflow_needs() -> None:
    """P3b interface: erevTenantSecretCreator (secrets.create) + erevTenantSecretInitializer
    (get, versions.add/access/get/list under the tenant prefix) together complete the workflow;
    either role alone fails closed, and the initializer never reaches another secret."""
    secrets = FakeSecretManager()
    both = CREATOR_PERMISSIONS | INITIALIZER_PERMISSIONS
    assert provisioner(secrets, both).provision_audit_key(TENANT).created
    used = {op for op, _ in secrets.calls}
    assert used == {
        "create_secret",
        "list_secret_versions",
        "add_secret_version",
        "access_secret_version",
    }

    creator_only = FakeSecretManager()
    with pytest.raises(TenantKeyProvisioningError) as excinfo:
        provisioner(creator_only, CREATOR_PERMISSIONS).provision_audit_key(TENANT)
    assert excinfo.value.kind == "denied"
    assert PATH in creator_only.secrets and creator_only.version_payloads(PATH) == []
    resumed = provisioner(creator_only).provision_audit_key(TENANT)  # a later run with both roles
    assert resumed.created and len(creator_only.version_payloads(PATH)) == 1

    initializer_only = FakeSecretManager()
    with pytest.raises(TenantKeyProvisioningError) as denied:
        provisioner(initializer_only, INITIALIZER_PERMISSIONS).provision_audit_key(TENANT)
    assert denied.value.kind == "denied" and initializer_only.secrets == {}

    # The initializer's conditional grant does not reach a secret outside the tenant prefix.
    scoped = secrets.client(INITIALIZER_PERMISSIONS, scope_infix=TENANT_SECRET_INFIX)
    with pytest.raises(PermissionDenied):
        scoped.list_secret_versions(
            request={"parent": f"projects/{PROJECT}/secrets/{PREFIX}security-hmac"}
        )
    assert scoped.list_secret_versions(request={"parent": PATH})


def test_provisioner_refuses_global_replication() -> None:
    with pytest.raises(ValueError):
        GcpTenantKeyProvisioner(PROJECT, prefix=PREFIX, location="global", client=object())
