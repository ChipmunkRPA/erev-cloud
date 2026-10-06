"""Hosted composition root: ``EREV_ENV=production`` with ``EREV_KEY_PROVIDER=gcp`` and
``EREV_FILE_BACKEND=gcs`` starts against injected fake clients, fails closed on malformed or
missing configuration and on provider outage, and logs no secret value (05 CFG-05, CFG-11,
CFG-13, SAR-21, SAR-25; DG-ENV-17; deployment audit DEP-B; lane P2)."""

from __future__ import annotations

import io
import json
import os
import sys
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api import worker
from erev_api.adapters import gcp
from erev_api.adapters.gcp import GcpError
from erev_api.adapters.keys.provider import GcpKeyProvider
from erev_api.adapters.secrets.provision import TenantKeyProvisioningError
from erev_api.adapters.secrets.store import (
    GcpSecretManagerStore,
    SecretRef,
    SecretRefError,
    SecretVersionMismatch,
    parse_secret_ref,
)
from erev_api.adapters.storage.digests import GcsDigestExporter
from erev_api.adapters.storage.gcs import GcsFileStore
from erev_api.api.v1.health import PROBE_BYTES, PROBE_KEY
from erev_api.auth.keyring import (
    STORE_UNAVAILABLE,
    UNSERVED_REFERENCE,
    DerivedTenantKeyProvisioner,
    HostedTenantKeyProvisioner,
    SecretUnavailable,
    build_keyring,
    build_tenant_key_provisioner,
    in_adapter_namespace,
    kms_key_location,
)
from erev_api.cli import CliServices
from erev_api.config import Settings, SettingsError
from erev_api.domain.integrations import sync
from erev_api.files.store import LocalFileStore, build_file_store
from erev_api.main import create_app
from pydantic import ValidationError
from support import log_guard
from support.clock import frozen_clock
from support.fake_gcp import (
    ACCESSOR_PERMISSIONS,
    PROVISIONER_PERMISSIONS,
    FakeKms,
    FakeSecretManager,
    ServiceUnavailable,
)
from support.fake_gcs import OBJECT_ADMIN, FakeGcsBackend
from support.http import call

PROJECT = "erev-staging-example"
PREFIX = "erev-"
LOCATION = "europe-west1"
KMS_KEK = f"projects/{PROJECT}/locations/{LOCATION}/keyRings/erev/cryptoKeys/erev-app-kek"
SECURITY_KEY = "8796a5b4c3d2e1f0" * 4
SECURITY_KEY_V2 = "1f0e2d3c4b5a6978" * 4
SECURITY_KEY_ID = "security-hmac:1"
SECURITY_SECRET = f"projects/{PROJECT}/secrets/{PREFIX}security-hmac"
FILES_BUCKET = "erev-files-staging"
DIGEST_BUCKET = "erev-audit-digests-staging"
TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
APP_CREDENTIAL = "hosted-app-credential-placeholder"
HOSTED = {
    "EREV_ENV": "production",
    "EREV_KEY_PROVIDER": "gcp",
    "EREV_GCP_PROJECT": PROJECT,
    "EREV_GCP_KMS_KEK": KMS_KEK,
    "EREV_GCP_SECRET_PREFIX": PREFIX,
    "EREV_SECURITY_HMAC_SECRET_VERSION": "1",
    "EREV_PUBLIC_ORIGIN": "https://erev.example.com",
    "EREV_FILE_BACKEND": "gcs",
    "EREV_GCS_FILES_BUCKET": FILES_BUCKET,
    "EREV_GCS_AUDIT_DIGEST_BUCKET": DIGEST_BUCKET,
    "EREV_DB_APP_URL": f"postgresql://erev_app:{APP_CREDENTIAL}@127.0.0.1:5432/erev_rv_p2",
    "EREV_LOG_FORMAT": "json",
}
LOCAL = {
    "EREV_ENV": "production",
    "EREV_KEY_PROVIDER": "local",
    "EREV_PUBLIC_ORIGIN": "http://127.0.0.1:8195",
    "EREV_DB_APP_URL": f"postgresql://erev_app:{APP_CREDENTIAL}@127.0.0.1:5432/erev_rv_p2",
    "EREV_DB_OWNER_URL": "postgresql://erev_owner:owner-credential-placeholder@127.0.0.1:5432/erev_rv_p2",
    "EREV_ENCRYPTION_KEY": "2468ace013579bdf" * 4,
    "EREV_AUDIT_HMAC_MASTER_KEY": "0f1e2d3c4b5a6978" * 4,
    "EREV_SECURITY_EVENT_HMAC_KEY": SECURITY_KEY,
    "EREV_SECURITY_HMAC_SECRET_VERSION": "1",
}


def settings_from(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, str], **overrides: str
) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    for name, value in {**values, **overrides}.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


class Fakes:
    """One backend per Google service, handed out by the patched ``gcp.make_client``."""

    def __init__(self) -> None:
        self.storage = FakeGcsBackend()
        self.kms = FakeKms()
        self.secrets = FakeSecretManager()
        self.secrets.seed(
            SECURITY_SECRET,
            [(SECURITY_KEY.encode(), "ENABLED"), (SECURITY_KEY_V2.encode(), "ENABLED")],
            location=LOCATION,
        )
        self.secret_permissions = PROVISIONER_PERMISSIONS
        self.storage_permissions = OBJECT_ADMIN
        self.made: list[str] = []

    def make_client(self, kind: str) -> Any:
        self.made.append(kind)
        if kind == "storage":
            return self.storage.client(self.storage_permissions)
        if kind == "kms":
            return self.kms
        return self.secrets.client(self.secret_permissions)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    instance = Fakes()
    monkeypatch.setattr(gcp, "make_client", instance.make_client)
    return instance


def test_hosted_keyring_needs_no_master_key_and_reads_pinned_versions(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_from(monkeypatch, HOSTED)
    keyring = build_keyring(settings)
    assert keyring.current_security_key_id() == SECURITY_KEY_ID
    assert keyring.verify_current_security_key() == SECURITY_KEY_ID
    assert keyring.security_event_key(SECURITY_KEY_ID) == bytes.fromhex(SECURITY_KEY)
    accessed = [req["name"] for op, req in fakes.secrets.calls if op == "access_secret_version"]
    assert accessed == [f"{SECURITY_SECRET}/versions/1"]
    blob = keyring.encrypt(b"totp seed", context={"tenant_id": str(TENANT), "t": "x"})
    assert keyring.decrypt(blob, context={"tenant_id": str(TENANT), "t": "x"}) == b"totp seed"
    assert [kind for kind, _ in fakes.kms.calls] == ["encrypt", "decrypt"]
    assert sorted(fakes.made) == ["kms", "secretmanager"]
    assert not any(name.startswith("google.cloud") for name in sys.modules)


def test_create_app_hosted_composition_root(fakes: Fakes, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_from(monkeypatch, HOSTED)
    with log_guard.capture() as events:
        app = create_app(settings, clock=frozen_clock())
    log_guard.check(events)
    file_store = app.state.file_store
    assert isinstance(file_store, GcsFileStore) and file_store.bucket_name == FILES_BUCKET
    assert isinstance(app.state.key_provisioner, HostedTenantKeyProvisioner)
    # The readyz files probe is a real bucket write under gcs (OPR-23), and keys resolve KEY-03.
    file_store.put(PROBE_KEY, io.BytesIO(PROBE_BYTES))
    live = fakes.storage.live(FILES_BUCKET, PROBE_KEY)
    assert live is not None and live.data == PROBE_BYTES
    file_store.put(PROBE_KEY, io.BytesIO(PROBE_BYTES))  # every later probe meets the winner
    assert len(fakes.storage.versions_of(FILES_BUCKET, PROBE_KEY)) == 1
    assert app.state.keyring.verify_current_security_key() == SECURITY_KEY_ID
    assert call(app, "GET", "/api/v1/healthz").status_code == 200
    assert APP_CREDENTIAL not in json.dumps(events, default=str)


def test_worker_runtime_follows_the_backends(fakes: Fakes, monkeypatch: pytest.MonkeyPatch) -> None:
    hosted = worker.build_runtime(settings_from(monkeypatch, HOSTED), frozen_clock())
    assert isinstance(hosted.files, GcsFileStore) and isinstance(hosted.digests, GcsDigestExporter)
    assert hosted.keyring is not None
    local = worker.build_runtime(settings_from(monkeypatch, LOCAL), frozen_clock())
    assert isinstance(local.files, LocalFileStore) and local.digests is None


def test_build_file_store_selection(fakes: Fakes, monkeypatch: pytest.MonkeyPatch) -> None:
    local = settings_from(monkeypatch, LOCAL)
    assert isinstance(build_file_store(local), LocalFileStore)
    hosted = settings_from(monkeypatch, HOSTED)
    store = build_file_store(hosted)
    assert isinstance(store, GcsFileStore) and store.backend == "gcs"
    # Settings refuse this shape already; the factory stays fail-closed on its own.
    with pytest.raises(SettingsError, match="EREV_GCS_FILES_BUCKET"):
        build_file_store(hosted.model_copy(update={"gcs_files_bucket": None}))
    assert CliServices.__dataclass_fields__["key_provisioner"].default is None


def test_secret_references_are_pinned_never_latest(fakes: Fakes) -> None:
    assert parse_secret_ref(" smtp-password@3 ") == SecretRef("smtp-password", 3)
    for malformed in ("smtp-password", "smtp-password@latest", "smtp-password@0", "@3", "a b@1"):
        with pytest.raises(SecretRefError) as excinfo:
            parse_secret_ref(malformed)
        assert malformed.strip() not in str(excinfo.value)
    store = GcpSecretManagerStore(
        PROJECT, prefix=PREFIX, client=fakes.secrets.client(ACCESSOR_PERMISSIONS)
    )
    with pytest.raises(SecretRefError):
        store.get("security-hmac")
    assert store.get("security-hmac@1").get_secret_value() == SECURITY_KEY
    with pytest.raises(KeyError):
        store.get("security-hmac@7")
    with pytest.raises(KeyError):
        store.get_version("absent-secret", 1)
    with pytest.raises(SecretRefError):
        store.get_version("security-hmac", 0)
    accessed = [req["name"] for op, req in fakes.secrets.calls if op == "access_secret_version"]
    assert accessed and all(name.rsplit("/", 1)[1].isdigit() for name in accessed)
    provider = GcpKeyProvider(store, kms_key=KMS_KEK, kms_client=fakes.kms)
    for refused in ("db-app-url@2", "db-owner-url@1", f"audit-hmac-{TENANT}@1", "app-kek@3"):
        with pytest.raises(KeyError):
            provider.secret(refused)
    fakes.secrets.seed(
        f"projects/{PROJECT}/secrets/{PREFIX}smtp-password", [(b"relay-credential", "ENABLED")]
    )
    assert provider.secret("smtp-password@1").get_secret_value() == "relay-credential"
    assert "GcpSecretManagerStore(project=" in repr(store) and SECURITY_KEY not in repr(store)


# The tenant's own namespace of the secret store (05 KEY-09 rev 1.47; ruling R-48 (f)): every
# secret its connections may name begins with it.
NAMESPACE = f"tenant-{TENANT}-"
SERVED = f"{NAMESPACE}sf-client-secret@1"
ADAPTER_SECRET = f"projects/{PROJECT}/secrets/{PREFIX}{NAMESPACE}sf-client-secret"
# References the hosted store will not serve. Not pinned as <name>@<version>: the store cannot
# parse them, so no error may repeat them.
NOT_PINNED = (f"{NAMESPACE}sf-client-secret", f"{NAMESPACE}sf-client-secret@latest")
# Outside the tenant's namespace: the literal BUILD_SPEC DIN-12 name, a secret of the old
# unprefixed form, and a refused name. None reaches the store.
OUTSIDE = ("EREV_SF_CLIENT_SECRET", "sf-client-secret@1", "db-app-url@1")
# Pinned and inside the namespace, and still not served: an absent secret and an absent version.
UNSERVED = (*NOT_PINNED, *OUTSIDE, f"{NAMESPACE}sf-absent@1", f"{NAMESPACE}sf-client-secret@7")


def test_adapter_secret_refuses_alike_on_both_providers(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05 ADP-01, ADP-14, KEY-09: ``KeyRing.adapter_secret`` is ``KeyError`` for every reference
    the provider will not serve — hosted: outside the tenant's namespace, not pinned
    (``SecretRefError``), absent, or denied to the identity; local: everything — and never names
    a reference the store could not parse. An outage or a mis-served version is no refusal and
    propagates (fail closed)."""
    fakes.secrets.seed(ADAPTER_SECRET, [(b"fixture-credential", "ENABLED")], location=LOCATION)
    fakes.secret_permissions = ACCESSOR_PERMISSIONS
    hosted = build_keyring(settings_from(monkeypatch, HOSTED))
    assert hosted.adapter_secret(SERVED, tenant_id=TENANT) == "fixture-credential"
    for reference in UNSERVED:
        with pytest.raises(KeyError) as refused:
            hosted.adapter_secret(reference, tenant_id=TENANT)
        if reference in NOT_PINNED:
            assert reference not in str(refused.value), reference
    # ``secret`` keeps the store's own error for its other callers; only the tenant path maps it.
    with pytest.raises(SecretRefError):
        hosted.secret("EREV_SF_CLIENT_SECRET")

    # An outage is no refusal: it is ``SecretUnavailable`` — a fixed text, the provider's error as
    # the cause — so the webhook receiver still answers 5xx and the probe can report it (R-45 (c)).
    fakes.secrets.faults.fail_next("access_secret_version", ServiceUnavailable())
    with pytest.raises(SecretUnavailable) as outage:
        hosted.adapter_secret(SERVED, tenant_id=TENANT)
    assert isinstance(outage.value.__cause__, GcpError)
    assert outage.value.__cause__.kind == "transient"
    assert str(outage.value) == STORE_UNAVAILABLE and "sf-client-secret" not in str(outage.value)
    assert not isinstance(outage.value, KeyError)
    fakes.secrets.returned_version_override[ADAPTER_SECRET] = 2
    with pytest.raises(SecretUnavailable) as mismatch:
        hosted.adapter_secret(SERVED, tenant_id=TENANT)
    assert isinstance(mismatch.value.__cause__, SecretVersionMismatch)
    del fakes.secrets.returned_version_override[ADAPTER_SECRET]
    # ``secret`` itself keeps the provider's own errors for its other callers
    fakes.secrets.faults.fail_next("access_secret_version", ServiceUnavailable())
    with pytest.raises(GcpError):
        hosted.secret(SERVED)

    fakes.secret_permissions = frozenset()  # an identity without the accessor grant
    denied = build_keyring(settings_from(monkeypatch, HOSTED))
    with pytest.raises(GcpError) as raw:
        denied.secret(SERVED)
    assert raw.value.kind == "denied"
    with pytest.raises(KeyError):
        denied.adapter_secret(SERVED, tenant_id=TENANT)

    local = build_keyring(settings_from(monkeypatch, LOCAL))
    for reference in (*UNSERVED, SERVED, "EREV_ENCRYPTION_KEY"):
        with pytest.raises(KeyError):
            local.adapter_secret(reference, tenant_id=TENANT)


def test_probe_records_a_failure_for_every_reference_the_hosted_store_refuses(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test-connection probe (04 §16.14 API-R-45; PRD ERR-57) on the hosted provider: a
    refused ``secret_ref`` is a FAILURE naming the reference before any adapter is built — it was
    an unhandled ``SecretRefError`` (a 500) while the probe caught the local ``KeyError`` only."""
    fakes.secrets.seed(ADAPTER_SECRET, [(b"fixture-credential", "ENABLED")], location=LOCATION)
    fakes.secret_permissions = ACCESSOR_PERMISSIONS
    principal = SimpleNamespace(tenant_id=TENANT)
    uow: Any = SimpleNamespace(
        keyring=build_keyring(settings_from(monkeypatch, HOSTED)), principal=principal
    )
    for reference in UNSERVED:
        outcome = sync.probe_connection(uow, {"secret_ref": reference, "base_url": "/mock"})
        assert outcome == sync.ProbeResult(
            "FAILURE", f"secret reference {reference} is not resolvable"
        )
    # 04 §16.14 rev 1.115 (ruling R-45 (c)): a secret store that does not answer is a FAILURE of
    # the probe too — the person asked a question — and the detail never carries the store's words
    fakes.secrets.faults.fail_next("access_secret_version", ServiceUnavailable())
    outcome = sync.probe_connection(uow, {"secret_ref": SERVED, "base_url": "/mock"})
    assert outcome == sync.ProbeResult(
        "FAILURE", f"the secret store did not answer for secret reference {SERVED}"
    )
    fakes.secret_permissions = frozenset()
    uow = SimpleNamespace(
        keyring=build_keyring(settings_from(monkeypatch, HOSTED)), principal=principal
    )
    outcome = sync.probe_connection(uow, {"secret_ref": SERVED, "base_url": "/m"})
    assert outcome.result == "FAILURE" and SERVED in outcome.detail


def secret_reads(fakes: Fakes) -> int:
    """How many secret versions the store was asked for."""
    return sum(1 for name, _ in fakes.secrets.calls if name == "access_secret_version")


def test_p3_23_an_adapter_secret_resolves_only_inside_the_tenants_namespace(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Security review P3-23 and the lead's finding 4 (ruling R-48 (f)). The key ring served a
    connection ANY secret name the service identity could read: an Integration Admin of one
    workspace could name another workspace's credential — or a platform secret — and have it sent
    to a ``base_url`` of its own. A reference resolves only inside the tenant's namespace,
    ``tenant-<tenant id>-…``; outside it nothing reaches the store."""
    other = UUID("0191e0a0-0000-7000-8000-000000000002")
    theirs = f"tenant-{other}-stripe-api-key"
    fakes.secrets.seed(ADAPTER_SECRET, [(b"our-credential", "ENABLED")], location=LOCATION)
    fakes.secrets.seed(
        f"projects/{PROJECT}/secrets/{PREFIX}{theirs}",
        [(b"their-credential", "ENABLED")],
        location=LOCATION,
    )
    fakes.secrets.seed(
        f"projects/{PROJECT}/secrets/{PREFIX}smtp-password",
        [(b"platform-credential", "ENABLED")],
        location=LOCATION,
    )
    fakes.secret_permissions = ACCESSOR_PERMISSIONS
    hosted = build_keyring(settings_from(monkeypatch, HOSTED))
    # The store holds all three and the identity may read them: only the namespace stands between.
    assert hosted.secret(f"{theirs}@1") == "their-credential"
    assert hosted.secret("smtp-password@1") == "platform-credential"
    reads_before = secret_reads(fakes)

    outside = (
        f"{theirs}@1",  # another workspace's credential
        "smtp-password@1",  # a platform secret
        f"{NAMESPACE}@1",  # the bare prefix names nothing
        f"tenant-{TENANT}@1",  # no separator: another name that merely starts alike
        f" TENANT-{str(TENANT).upper()}-sf-client-secret@1",  # the namespace is exact, in its case
        f"x-{NAMESPACE}sf-client-secret@1",  # the prefix must begin the name
    )
    for reference in outside:
        assert not in_adapter_namespace(reference, TENANT), reference
        with pytest.raises(KeyError) as refused:
            hosted.adapter_secret(reference, tenant_id=TENANT)
        assert str(refused.value) == repr(UNSERVED_REFERENCE), reference
    assert secret_reads(fakes) == reads_before  # nothing outside the namespace was read

    # Positive controls: each tenant reads its own secret, under both readings of the reference.
    assert hosted.adapter_secret(SERVED, tenant_id=TENANT) == "our-credential"
    assert hosted.adapter_secret(f" {SERVED} ", tenant_id=TENANT) == "our-credential"
    assert hosted.adapter_secret(f"{theirs}@1", tenant_id=other) == "their-credential"
    with pytest.raises(KeyError):
        hosted.adapter_secret(SERVED, tenant_id=other)


def test_provider_outage_and_denial_fail_closed(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_from(monkeypatch, HOSTED)
    fakes.secrets.faults.fail_next("access_secret_version", ServiceUnavailable())
    with pytest.raises(GcpError) as outage:
        build_keyring(settings).security_event_key(SECURITY_KEY_ID)
    assert outage.value.kind == "transient" and SECURITY_KEY not in str(outage.value)
    fakes.secret_permissions = frozenset()
    with pytest.raises(GcpError) as denied:
        build_keyring(settings).security_event_key(SECURITY_KEY_ID)
    assert denied.value.kind == "denied"
    fakes.secret_permissions = PROVISIONER_PERMISSIONS
    fakes.kms.faults.fail_next("encrypt", ServiceUnavailable())
    with pytest.raises(ServiceUnavailable):
        build_keyring(settings).encrypt(b"x", context={"t": "x"})


def test_pinned_security_key_version_is_the_signing_version(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3b interface: EREV_SECURITY_HMAC_SECRET_VERSION pins `security-hmac:<n>`; startup verifies
    requested == returned; historical versions still load by id (05 KEY-03 rotation)."""
    pinned = settings_from(monkeypatch, HOSTED, EREV_SECURITY_HMAC_SECRET_VERSION="2")
    assert pinned.security_hmac_version() == 2
    keyring = build_keyring(pinned)
    assert keyring.current_security_key_id() == "security-hmac:2"
    assert keyring.verify_current_security_key() == "security-hmac:2"
    assert keyring.security_event_key("security-hmac:2") == bytes.fromhex(SECURITY_KEY_V2)
    assert keyring.security_event_key("security-hmac:1") == bytes.fromhex(SECURITY_KEY)
    accessed = [req["name"] for op, req in fakes.secrets.calls if op == "access_secret_version"]
    assert accessed == [f"{SECURITY_SECRET}/versions/2", f"{SECURITY_SECRET}/versions/1"]
    assert not any(name.endswith("/latest") for name in accessed)

    # A pin no version satisfies fails closed at startup, as does a mis-served version.
    with pytest.raises(KeyError):
        build_keyring(
            settings_from(monkeypatch, HOSTED, EREV_SECURITY_HMAC_SECRET_VERSION="3")
        ).verify_current_security_key()
    fakes.secrets.returned_version_override[SECURITY_SECRET] = 1
    with pytest.raises(SecretVersionMismatch) as excinfo:
        build_keyring(pinned).verify_current_security_key()
    assert (excinfo.value.requested, excinfo.value.returned) == (2, "1")
    assert SECURITY_KEY_V2 not in str(excinfo.value)
    with pytest.raises(ValidationError, match="EREV_SECURITY_HMAC_SECRET_VERSION"):
        settings_from(monkeypatch, HOSTED, EREV_SECURITY_HMAC_SECRET_VERSION="")
    with pytest.raises(ValidationError, match="EREV_SECURITY_HMAC_SECRET_VERSION"):
        settings_from(monkeypatch, HOSTED, EREV_SECURITY_HMAC_SECRET_VERSION="0")
    # Locally the derivation version follows the same setting, 1 by default.
    local = settings_from(monkeypatch, LOCAL)
    assert build_keyring(local).current_security_key_id() == "security-hmac:1"
    rotated = settings_from(monkeypatch, LOCAL, EREV_SECURITY_HMAC_SECRET_VERSION="2")
    assert build_keyring(rotated).current_security_key_id() == "security-hmac:2"
    assert build_keyring(rotated).security_event_key("security-hmac:2") != build_keyring(
        local
    ).security_event_key("security-hmac:1")


def test_malformed_or_missing_configuration_fails_closed(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValidationError, match="EREV_GCP_KMS_KEK"):
        settings_from(monkeypatch, HOSTED, EREV_GCP_KMS_KEK="")
    with pytest.raises(ValidationError, match="EREV_GCS_AUDIT_DIGEST_BUCKET"):
        settings_from(monkeypatch, HOSTED, EREV_GCS_AUDIT_DIGEST_BUCKET="")
    with pytest.raises(ValidationError, match="EREV_DB_APP_URL"):
        settings_from(monkeypatch, HOSTED, EREV_DB_APP_URL="")
    with pytest.raises(ValidationError) as excinfo:
        settings_from(monkeypatch, HOSTED, EREV_GCP_KMS_KEK="global-key-zzz")
    assert "global-key-zzz" not in str(excinfo.value)
    settings = settings_from(monkeypatch, HOSTED)
    with pytest.raises(SettingsError, match="EREV_GCP_PROJECT"):
        build_keyring(settings.model_copy(update={"gcp_project": None}))
    assert kms_key_location(KMS_KEK) == LOCATION
    with pytest.raises(SettingsError, match="global"):
        kms_key_location(KMS_KEK.replace(LOCATION, "global"))
    with pytest.raises(SettingsError, match="global"):
        build_tenant_key_provisioner(
            settings.model_copy(update={"gcp_kms_kek": KMS_KEK.replace(LOCATION, "global")}),
            build_keyring(settings),
        )


def test_tenant_key_provisioner_selection(fakes: Fakes, monkeypatch: pytest.MonkeyPatch) -> None:
    local = settings_from(monkeypatch, LOCAL)
    derived = build_tenant_key_provisioner(local, build_keyring(local))
    assert isinstance(derived, DerivedTenantKeyProvisioner)
    assert derived.provision_audit_key(TENANT) == f"audit-hmac:{TENANT}:1"

    hosted = settings_from(monkeypatch, HOSTED)
    keyring = build_keyring(hosted)
    with log_guard.capture() as events:
        provisioner = build_tenant_key_provisioner(hosted, keyring)
        assert isinstance(provisioner, HostedTenantKeyProvisioner)
        key_id = provisioner.provision_audit_key(TENANT)
        assert key_id == f"audit-hmac:{TENANT}:1"
        assert provisioner.provision_audit_key(TENANT) == key_id  # idempotent
    log_guard.check(events)
    path = f"projects/{PROJECT}/secrets/{PREFIX}audit-hmac-{TENANT}"
    (material,) = fakes.secrets.version_payloads(path)
    assert keyring.tenant_audit_key(key_id) == bytes.fromhex(material.decode())
    dump = json.dumps(events, default=str)
    assert material.decode() not in dump and SECURITY_KEY not in dump

    # The api and worker identities are accessor-only: provisioning through them fails closed.
    fakes.secret_permissions = ACCESSOR_PERMISSIONS
    other_tenant = UUID("0191e0a0-0000-7000-8000-000000000002")
    with pytest.raises(TenantKeyProvisioningError) as excinfo:
        build_tenant_key_provisioner(hosted, keyring).provision_audit_key(other_tenant)
    assert excinfo.value.kind == "denied"
    assert (
        f"projects/{PROJECT}/secrets/{PREFIX}audit-hmac-{other_tenant}" not in fakes.secrets.secrets
    )
