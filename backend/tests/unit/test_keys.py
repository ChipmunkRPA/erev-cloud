"""KRN-KEY contract (dev-guide §5.19 DG-KRN-KEY-01 to 07; 05 SAR-22; BUILD_SPEC FND-4)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from cryptography.exceptions import InvalidTag
from erev_api.adapters.keys.provider import (
    GcpKeyProvider,
    LocalKeyProvider,
    hkdf_sha256,
    open_sealed,
    seal,
)
from erev_api.adapters.secrets.store import EnvSecretStore
from erev_api.auth.keyring import DEK_CACHE_SECONDS, KeyRing, build_keyring
from erev_api.config import Settings, SettingsError
from erev_engine.canonical import canonical_bytes
from pydantic import SecretStr, ValidationError
from support import log_guard

ENCRYPTION_KEY = "2468ace013579bdf" * 4
AUDIT_KEY = "0f1e2d3c4b5a6978" * 4
SECURITY_KEY = "8796a5b4c3d2e1f0" * 4
MASTER_VALUES = (ENCRYPTION_KEY, AUDIT_KEY, SECURITY_KEY)
TENANT_A = UUID("0191e0a0-0000-7000-8000-000000000001")
TENANT_B = UUID("0191e0a0-0000-7000-8000-000000000002")
BACKEND_ROOT = Path(__file__).resolve().parents[2]
KMS_KEY = "projects/p/locations/l/keyRings/erev/cryptoKeys/erev-app-kek"


class FakeSecretStore:
    """Secret Manager stand-in that records every read; no google.cloud import, no network."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self.values = dict(values)
        self.calls: list[tuple[str, int | None]] = []

    def get(self, name: str) -> SecretStr:
        self.calls.append((name, None))
        return SecretStr(self.values[name])

    def get_version(self, name: str, version: int) -> SecretStr:
        self.calls.append((name, version))
        return SecretStr(self.values[name])


class FakeKms:
    """Cloud KMS stand-in: AES-256-GCM under a fixed key, so the AAD binding really holds.

    The ciphertext carries a prefix, so its length differs from the local 60-byte wrap.
    """

    PREFIX = b"fake-kms:"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._key = bytes(range(32))

    def encrypt(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self.calls.append(("encrypt", dict(request)))
        sealed = seal(self._key, request["plaintext"], request["additional_authenticated_data"])
        return SimpleNamespace(ciphertext=self.PREFIX + sealed)

    def decrypt(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self.calls.append(("decrypt", dict(request)))
        ciphertext = request["ciphertext"]
        assert ciphertext.startswith(self.PREFIX)
        plaintext = open_sealed(
            self._key, ciphertext[len(self.PREFIX) :], request["additional_authenticated_data"]
        )
        return SimpleNamespace(plaintext=plaintext)


def _environment(**overrides: str) -> dict[str, str]:
    database = "127.0.0.1:5432/erev_test"
    return {
        "EREV_ENV": "test",
        "EREV_TEST_DB_OWNER_URL": f"postgresql://erev_owner:unit-owner-credential@{database}",
        "EREV_TEST_DB_APP_URL": f"postgresql://erev_app:unit-app-credential@{database}",
        "EREV_ENCRYPTION_KEY": ENCRYPTION_KEY,
        "EREV_AUDIT_HMAC_MASTER_KEY": AUDIT_KEY,
        "EREV_SECURITY_EVENT_HMAC_KEY": SECURITY_KEY,
        **overrides,
    }


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    for name, value in _environment(**overrides).items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    return _settings(monkeypatch)


SUBPROCESS_SCRIPT = """
import hashlib, sys
from erev_api.adapters.keys.provider import LocalKeyProvider
from erev_api.adapters.secrets.store import EnvSecretStore
from erev_api.config import Settings
provider = LocalKeyProvider(EnvSecretStore(Settings(_env_file=None)))
print("sha256=" + hashlib.sha256(provider.hmac_key(sys.argv[1])).hexdigest())
"""


def test_krn_key_07_hkdf_rfc5869_case_3() -> None:
    derived = hkdf_sha256(bytes([0x0B]) * 22, b"", length=42)
    assert derived.hex() == (
        "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"
    )


def test_krn_key_02_per_tenant_keys_differ_and_are_stable(settings: Settings) -> None:
    provider = LocalKeyProvider(EnvSecretStore(settings))
    key_id = f"audit-hmac:{TENANT_A}:1"
    key_a = provider.hmac_key(key_id)
    key_b = provider.hmac_key(f"audit-hmac:{TENANT_B}:1")
    assert len(key_a) == 32
    assert key_a != key_b
    assert key_a != provider.hmac_key(f"audit-hmac:{TENANT_A}:2")

    result = subprocess.run(
        [sys.executable, "-c", SUBPROCESS_SCRIPT, key_id],
        env={**_environment(), "PATH": os.environ.get("PATH", "")},
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    (line,) = [line for line in result.stdout.splitlines() if line.startswith("sha256=")]
    assert line == "sha256=" + hashlib.sha256(key_a).hexdigest()

    for malformed in (
        f"audit-hmac:{str(TENANT_A).upper()}:1",
        f"audit-hmac:{TENANT_A}:01",
        f"audit-hmac:{TENANT_A}:0",
        "security-hmac:1\n",
        "kek:one",
    ):
        with pytest.raises(ValueError):
            provider.hmac_key(malformed)


def test_krn_key_02_purposes_select_master_keys(settings: Settings) -> None:
    provider = LocalKeyProvider(EnvSecretStore(settings))
    for key_id, master in (
        (f"audit-hmac:{TENANT_A}:1", AUDIT_KEY),
        ("security-hmac:1", SECURITY_KEY),
        ("kek:1", ENCRYPTION_KEY),
    ):
        expected = hkdf_sha256(bytes.fromhex(master), b"erev:" + key_id.encode("ascii"))
        assert provider.hmac_key(key_id) == expected
    assert provider.current_hmac_key_id("audit-hmac", TENANT_A) == f"audit-hmac:{TENANT_A}:1"
    assert provider.current_hmac_key_id("security-hmac", None) == "security-hmac:1"
    with pytest.raises(ValueError):
        provider.current_hmac_key_id("audit-hmac", None)
    keyring = KeyRing(provider)
    with pytest.raises(ValueError):
        keyring.tenant_audit_key("security-hmac:1")
    with pytest.raises(ValueError):
        keyring.security_event_key(f"audit-hmac:{TENANT_A}:1")


def test_krn_key_01_env_store_serves_three_names(settings: Settings) -> None:
    store = EnvSecretStore(settings)
    for name, value in (
        ("EREV_AUDIT_HMAC_MASTER_KEY", AUDIT_KEY),
        ("EREV_SECURITY_EVENT_HMAC_KEY", SECURITY_KEY),
        ("EREV_ENCRYPTION_KEY", ENCRYPTION_KEY),
    ):
        secret = store.get(name)
        assert isinstance(secret, SecretStr)
        assert secret.get_secret_value() == value
    with pytest.raises(KeyError):
        store.get("EREV_DEMO_PASSWORD")


def test_krn_key_04_envelope_roundtrip_and_context_binding(settings: Settings) -> None:
    keyring = build_keyring(settings)
    blob = keyring.encrypt(b"seed", context={"t": "x"})
    assert keyring.decrypt(blob, context={"t": "x"}) == b"seed"
    assert blob[:5] == b"erev1"
    assert blob[5] == 5
    assert blob[6:11] == b"kek:1"
    with pytest.raises(InvalidTag):
        keyring.decrypt(blob, context={"t": "y"})
    # A fresh process (no DEK cache) reads the blob through the same master key.
    fresh = KeyRing(LocalKeyProvider(EnvSecretStore(settings)))
    assert fresh.decrypt(blob, context={"t": "x"}) == b"seed"
    assert keyring.encrypt(b"seed", context={"t": "x"}) != blob
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(InvalidTag):
        fresh.decrypt(tampered, context={"t": "x"})
    with pytest.raises(ValueError):
        keyring.decrypt(b"erev0" + blob[5:], context={"t": "x"})


def test_krn_key_04_blob_carries_wrapped_dek_length(settings: Settings) -> None:
    provider = LocalKeyProvider(EnvSecretStore(settings))
    blob = KeyRing(provider).encrypt(b"seed", context={"t": "x"})
    assert blob[:5] == b"erev1"
    assert blob[5] == 0x05
    assert blob[6:11] == b"kek:1"
    assert blob[11:13] == (60).to_bytes(2, "big")
    wrapped, nonce_and_ciphertext = blob[13:73], blob[73:]
    assert len(nonce_and_ciphertext) == 12 + len(b"seed") + 16
    associated_data = canonical_bytes({"t": "x"})
    dek = open_sealed(provider.hmac_key("kek:1"), wrapped, associated_data)
    assert len(dek) == 32
    assert open_sealed(dek, nonce_and_ciphertext, associated_data) == b"seed"

    short = blob[:11] + (59).to_bytes(2, "big") + blob[13:]
    with pytest.raises(ValueError):
        KeyRing(LocalKeyProvider(EnvSecretStore(settings))).decrypt(short, context={"t": "x"})
    for truncated in (blob[:12], blob[:13], blob[:80]):
        with pytest.raises(ValueError):
            KeyRing(provider).decrypt(truncated, context={"t": "x"})


def test_key_04_gcp_provider_wraps_deks_through_kms() -> None:
    store = FakeSecretStore({"security-hmac": SECURITY_KEY})
    kms = FakeKms()
    provider = GcpKeyProvider(store, kms_key=KMS_KEY, kms_client=kms)  # type: ignore[arg-type]
    keyring = KeyRing(provider)
    context = {"t": "a"}

    blob = keyring.encrypt(b"x", context=context)
    ((kind, request),) = kms.calls
    assert kind == "encrypt"
    assert request["name"] == KMS_KEY
    assert len(request["plaintext"]) == 32
    assert request["additional_authenticated_data"] == canonical_bytes(context)
    assert store.calls == []
    # The blob layout is the local one; the length field names the KMS ciphertext length.
    assert blob[:11] == b"erev1\x05kek:1"
    wrapped_length = int.from_bytes(blob[11:13], "big")
    assert wrapped_length == len(FakeKms.PREFIX) + 60
    wrapped = blob[13 : 13 + wrapped_length]
    assert wrapped.startswith(FakeKms.PREFIX)

    assert keyring.decrypt(blob, context=context) == b"x"
    assert [kind for kind, _ in kms.calls] == ["encrypt", "decrypt"]
    decrypt_request = kms.calls[1][1]
    assert decrypt_request["name"] == KMS_KEY
    assert decrypt_request["ciphertext"] == wrapped
    assert decrypt_request["additional_authenticated_data"] == canonical_bytes(context)
    with pytest.raises(InvalidTag):
        KeyRing(provider).decrypt(blob, context={"t": "b"})

    with pytest.raises(ValueError):
        provider.hmac_key("kek:1")
    assert store.calls == []
    assert provider.hmac_key("security-hmac:1") == bytes.fromhex(SECURITY_KEY)
    assert store.calls == [("security-hmac", 1)]
    assert not any(name.startswith("google.cloud") for name in sys.modules)


def test_krn_key_01_secret_refuses_key_material(settings: Settings) -> None:
    local = LocalKeyProvider(EnvSecretStore(settings))
    for name in (
        "EREV_ENCRYPTION_KEY",
        "EREV_AUDIT_HMAC_MASTER_KEY",
        "EREV_SECURITY_EVENT_HMAC_KEY",
    ):
        with pytest.raises(KeyError):
            local.secret(name)

    store = FakeSecretStore({"sf-client-secret": "sf-placeholder-value"})
    kms = FakeKms()
    hosted = GcpKeyProvider(store, kms_key="k", kms_client=kms)  # type: ignore[arg-type]
    for ref in (
        "app-kek",
        "security-hmac",
        f"audit-hmac-{TENANT_A}",
        "db-owner-url",
        "db-app-url",
        " App-KEK ",
    ):
        with pytest.raises(KeyError):
            hosted.secret(ref)
    assert store.calls == []
    value = hosted.secret("sf-client-secret")
    assert isinstance(value, SecretStr)
    assert value.get_secret_value() == "sf-placeholder-value"
    assert store.calls == [("sf-client-secret", None)]
    assert kms.calls == []


def test_sar_22_unwrapped_dek_cache_expires(settings: Settings) -> None:
    class CountingProvider(LocalKeyProvider):
        unwraps = 0

        def unwrap(self, blob: bytes, context: Mapping[str, str]) -> bytes:
            CountingProvider.unwraps += 1
            return super().unwrap(blob, context)

    now = [1000.0]
    keyring = KeyRing(CountingProvider(EnvSecretStore(settings)), monotonic=lambda: now[0])
    blob = keyring.encrypt(b"seed", context={"t": "x"})
    for _ in range(3):
        assert keyring.decrypt(blob, context={"t": "x"}) == b"seed"
    assert CountingProvider.unwraps == 1
    now[0] += DEK_CACHE_SECONDS
    assert keyring.decrypt(blob, context={"t": "x"}) == b"seed"
    assert CountingProvider.unwraps == 2


def test_krn_key_06_new_tenant_audit_key_id(settings: Settings) -> None:
    keyring = build_keyring(settings)
    tenant = UUID("0191e0a0-0000-7000-8000-000000000001")
    assert (
        keyring.new_tenant_audit_key_id(tenant)
        == "audit-hmac:0191e0a0-0000-7000-8000-000000000001:1"
    )


def test_krn_key_03_gcp_provider_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    # Lane P2: Settings refuse the selection without its CFG-13 configuration (DG-KRN-CFG-02) ...
    with pytest.raises(ValidationError, match="EREV_GCP_PROJECT"):
        _settings(monkeypatch, EREV_ENV="production", EREV_KEY_PROVIDER="gcp")
    # ... and the factory stays fail-closed on its own.
    hosted = _settings(
        monkeypatch,
        EREV_ENV="production",
        EREV_KEY_PROVIDER="gcp",
        EREV_GCP_PROJECT="p",
        EREV_GCP_KMS_KEK=KMS_KEY,
        EREV_SECURITY_HMAC_SECRET_VERSION="1",
        EREV_DB_APP_URL="postgresql://erev_app:unit-app-credential@127.0.0.1:5432/erev",
    )
    with pytest.raises(SettingsError, match="EREV_GCP_PROJECT"):
        build_keyring(hosted.model_copy(update={"gcp_project": None}))


def test_krn_key_07_no_key_material_in_repr_or_logs(settings: Settings) -> None:
    store = EnvSecretStore(settings)
    provider = LocalKeyProvider(store)
    assert not any(value in repr(store) or value in repr(provider) for value in MASTER_VALUES)
    with log_guard.capture() as events:
        keyring = KeyRing(provider)
        derived = [
            keyring.tenant_audit_key(f"audit-hmac:{TENANT_A}:1"),
            keyring.security_event_key("security-hmac:1"),
        ]
        keyring.decrypt(keyring.encrypt(b"seed", context={"t": "x"}), context={"t": "x"})
    assert {event.get("key_id") for event in events} >= {f"audit-hmac:{TENANT_A}:1", "kek:1"}
    logged = repr(events)
    secrets = [*MASTER_VALUES, *(key.hex() for key in derived)]
    assert not any(value in logged for value in secrets)
