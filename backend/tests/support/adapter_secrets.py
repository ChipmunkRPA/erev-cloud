"""Adapter credentials in tests (05 KEY-09, ADP-14; dev-guide DG-KRN-KEY-01, DG-KRN-KEY-03).

Under the local key provider ``EnvSecretStore`` serves exactly the three master keys, so no
``integration_connection.secret_ref`` resolves through the process key ring (05 KEY-09, local
column: none). A scenario that needs a resolvable reference — the ``/test`` probe of a connection
with a secret, the ADP-01 webhook signature — gives the app a key ring over ``FixtureSecretStore``:
the settings' master keys plus the named fixture secrets, served through the same ``SecretStore``
protocol the hosted provider reads Secret Manager through. Nothing here reads the process
environment and no value is a credential (the mocks' shared secrets are fixture text).

``serve_hosted_adapter_secrets`` is the same app with its adapter secrets on the HOSTED path: the
real ``GcpKeyProvider.secret`` over ``GcpSecretManagerStore`` and the fake Secret Manager of
``support.fake_gcp`` — pinned ``<name>@<version>`` references, the refused names, the identity's
permissions and injected faults — for the scenarios that must hold on both providers (ADP-01).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final
from uuid import UUID

from erev_api.adapters.keys.provider import GcpKeyProvider, HmacPurpose, LocalKeyProvider
from erev_api.adapters.secrets.store import EnvSecretStore, GcpSecretManagerStore
from erev_api.auth.keyring import KeyRing, adapter_secret_namespace
from erev_api.config import Settings
from fastapi import FastAPI
from pydantic import SecretStr
from support.fake_gcp import ACCESSOR_PERMISSIONS, FakeKms, FakeSecretManager

__all__ = [
    "HOSTED_PROJECT",
    "FixtureSecretStore",
    "keyring_with",
    "serve_adapter_secrets",
    "serve_hosted_adapter_secrets",
    "tenant_ref",
]

HOSTED_PROJECT: Final = "erev-tests"
_HOSTED_KMS_KEY: Final = (
    f"projects/{HOSTED_PROJECT}/locations/test/keyRings/erev/cryptoKeys/erev-app-kek"
)


def tenant_ref(tenant_id: UUID, name: str) -> str:
    """The name of the tenant's secret ``name``: inside the tenant's own namespace of the secret
    store, the only place an ``integration_connection.secret_ref`` may point to (05 KEY-09 rev
    1.47; supervisor ruling R-48 (f)). Hosted, the reference is this name with ``@<version>``."""
    return f"{adapter_secret_namespace(tenant_id)}{name}"


class FixtureSecretStore:
    """``SecretStore``: the fixture secrets by reference name, else the settings' master keys."""

    def __init__(self, settings: Settings, secrets: Mapping[str, str]) -> None:
        self._base = EnvSecretStore(settings)
        self._secrets = {name: SecretStr(value) for name, value in secrets.items()}

    def get(self, name: str) -> SecretStr:
        found = self._secrets.get(name)
        return self._base.get(name) if found is None else found  # KeyError when absent

    def __repr__(self) -> str:
        return f"FixtureSecretStore(names={sorted(self._secrets)!r})"


def keyring_with(settings: Settings, secrets: Mapping[str, str]) -> KeyRing:
    """``build_keyring(settings)`` for the local provider, whose ``secret(ref)`` also resolves
    ``secrets`` (reference name → value). Every derived key is unchanged: both rings derive from
    the settings' master keys."""
    provider = LocalKeyProvider(
        FixtureSecretStore(settings, secrets),
        security_hmac_version=settings.security_hmac_version(),
    )
    return KeyRing(provider)


def serve_adapter_secrets(app: FastAPI, secrets: Mapping[str, str]) -> None:
    """Give ``app`` a key ring that resolves ``secrets``; the probe and the webhook receiver read
    ``app.state.keyring`` on every request."""
    app.state.keyring = keyring_with(app.state.settings, secrets)


class _LocalKeysHostedSecrets:
    """``KeyProvider`` of a test app whose adapter secrets take the hosted path. Every key comes
    from the local provider — the fixtures provision tenants, seal rows and run jobs with the
    session's local key ring, so the app has to derive the same keys — and ``secret(ref)`` is the
    hosted provider's."""

    def __init__(self, local: LocalKeyProvider, hosted: GcpKeyProvider) -> None:
        self._local = local
        self._hosted = hosted

    def hmac_key(self, key_id: str) -> bytes:
        return self._local.hmac_key(key_id)

    def current_hmac_key_id(self, purpose: HmacPurpose, tenant_id: UUID | None) -> str:
        return self._local.current_hmac_key_id(purpose, tenant_id)

    def wrap(self, dek: bytes, context: Mapping[str, str]) -> bytes:
        return self._local.wrap(dek, context)

    def unwrap(self, blob: bytes, context: Mapping[str, str]) -> bytes:
        return self._local.unwrap(blob, context)

    def secret(self, ref: str) -> SecretStr:
        return self._hosted.secret(ref)


def serve_hosted_adapter_secrets(
    app: FastAPI,
    secrets: Mapping[str, str],
    *,
    permissions: frozenset[str] = ACCESSOR_PERMISSIONS,
) -> FakeSecretManager:
    """Give ``app`` a key ring whose adapter secrets resolve as they do hosted. ``secrets`` maps a
    Secret Manager secret NAME to the payload of its version 1 (so the reference that resolves is
    ``<name>@1``); the store's client holds ``permissions`` — the accessor role by default, an
    empty set for an identity the store denies. Returns the fake Secret Manager, for a test that
    seeds further versions or injects a fault."""
    manager = FakeSecretManager()
    for name, value in secrets.items():
        manager.seed(f"projects/{HOSTED_PROJECT}/secrets/{name}", [(value.encode(), "ENABLED")])
    store = GcpSecretManagerStore(HOSTED_PROJECT, client=manager.client(permissions))
    hosted = GcpKeyProvider(store, kms_key=_HOSTED_KMS_KEY, kms_client=FakeKms())
    settings: Settings = app.state.settings
    local = LocalKeyProvider(
        EnvSecretStore(settings), security_hmac_version=settings.security_hmac_version()
    )
    app.state.keyring = KeyRing(_LocalKeysHostedSecrets(local, hosted))
    return manager
