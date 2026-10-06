"""Key ring KRN-KEY (dev-guide §5.19 DG-KRN-KEY-03, DG-KRN-KEY-04, DG-KRN-KEY-06; 05 SAR-22).

Envelope blob, for both providers: ``b"erev1"`` ‖ KEK id length (1 byte) ‖ KEK id ‖ wrapped DEK
length (2 bytes, big-endian) ‖ wrapped DEK ‖ nonce ‖ ciphertext with tag (DG-KRN-KEY-04 as amended
by D-78). The associated data of the data layer and of the DEK wrap is the canonical bytes of
``context`` (§5.17), so a blob decrypts only under the context it was written with.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api import clock
from erev_api.adapters.gcp import GcpError
from erev_api.adapters.keys.provider import (
    KEY_BYTES,
    NONCE_BYTES,
    TAG_BYTES,
    GcpKeyProvider,
    KeyId,
    KeyProvider,
    LocalKeyProvider,
    open_sealed,
    parse_key_id,
    seal,
    unpack_wrapped_dek,
)
from erev_api.adapters.secrets.provision import (
    GcpTenantKeyProvisioner,
    TenantKeyProvisioningError,
)
from erev_api.adapters.secrets.store import (
    EnvSecretStore,
    GcpSecretManagerStore,
    SecretRefError,
    SecretVersionMismatch,
)
from erev_api.config import Settings, SettingsError

BLOB_MAGIC: Final = b"erev1"
# The location segment of a Cloud KMS key resource name; tenant secrets replicate there (PRV-10).
_KMS_LOCATION: Final = re.compile(r"^projects/[^/]+/locations/(?P<location>[^/]+)/")
# Unwrapped DEKs: at most 5 minutes in an LRU of 1,000 entries (05 SAR-22).
DEK_CACHE_ENTRIES: Final = 1000
DEK_CACHE_SECONDS: Final = 300.0
# The argument of the ``KeyError`` of ``KeyRing.adapter_secret`` for a reference the hosted store
# refuses: a fixed text, never the reference.
UNSERVED_REFERENCE: Final = "the secret store does not serve this reference"
# The message of ``SecretUnavailable``: a fixed text, never the reference or the provider's words.
STORE_UNAVAILABLE: Final = "the secret store did not answer"
# 05 KEY-09 / ADP-14 rev 1.47 (ruling R-48 (f)): the name of every secret a tenant's integration
# connections may reference begins with this prefix carrying the tenant's id.
ADAPTER_NAMESPACE: Final = "tenant-{tenant_id}-"


def adapter_secret_namespace(tenant_id: UUID) -> str:
    """The tenant's own namespace of the secret store: the prefix of the secret names its
    connections may reference."""
    return ADAPTER_NAMESPACE.format(tenant_id=tenant_id)


def in_adapter_namespace(ref: str, tenant_id: UUID) -> bool:
    """Whether ``ref`` — ``<name>`` or ``<name>@<version>`` — names a secret inside the tenant's
    namespace: the name begins with the prefix and goes on after it. The rule is the same under
    both providers and is checked when a connection is saved and when its secret is read."""
    name = ref.strip().partition("@")[0]
    prefix = adapter_secret_namespace(tenant_id)
    return name.startswith(prefix) and len(name) > len(prefix)


# 05 KEY-03 rev 1.90: the label under which the platform security key derives the token of an
# emailed link, apart from everything else the key signs.
LINK_TOKEN_LABEL: Final = b"erev-link-token-v1"


@dataclass(frozen=True, slots=True)
class LinkToken:
    """The secret of an emailed link and the id of the key it was derived with."""

    token: str  # 43 URL-safe characters: 256 bits
    key_id: str  # security-hmac:<n>

    def __repr__(self) -> str:
        return f"LinkToken(key_id={self.key_id!r})"


class SecretUnavailable(RuntimeError):
    """The secret store could not answer for an adapter reference: an outage, an unclassified
    provider failure, or a version it did not return as asked. It is no refusal — the reference
    may be perfectly good — so a caller that must fail closed lets it propagate (the webhook
    receiver answers 5xx and the source retries), and a caller that answers a person's question
    reports it (the test-connection probe records FAILURE; ruling R-45 (c)). The provider's error
    is the cause, for the log; the message is a fixed text."""


def _require_purpose(key_id: str, purpose: str) -> str:
    if parse_key_id(key_id).purpose != purpose:
        raise ValueError(f"{key_id!r} is not a {purpose} key id")
    return key_id


class KeyRing:
    def __init__(
        self, provider: KeyProvider, *, monotonic: Callable[[], float] = clock.monotonic
    ) -> None:
        self._provider = provider
        self._monotonic = monotonic
        self._deks: OrderedDict[tuple[bytes, bytes], tuple[float, bytes]] = OrderedDict()

    def tenant_audit_key(self, audit_hmac_key_id: str) -> bytes:
        return self._provider.hmac_key(_require_purpose(audit_hmac_key_id, "audit-hmac"))

    def security_event_key(self, hmac_key_id: str) -> bytes:
        return self._provider.hmac_key(_require_purpose(hmac_key_id, "security-hmac"))

    def current_security_key_id(self) -> str:
        """``security-hmac:<n>`` new security events are signed with (05 KEY-03, pinned hosted)."""
        return self._provider.current_hmac_key_id("security-hmac", None)

    def verify_current_security_key(self) -> str:
        """Load the current platform security key and return its id; raises when the provider
        cannot serve exactly the pinned version (startup and readiness fail closed)."""
        key_id = self.current_security_key_id()
        if len(self.security_event_key(key_id)) != KEY_BYTES:
            raise ValueError(f"{key_id} did not resolve to 32 bytes")
        return key_id

    def link_token(self, purpose: str, reference: UUID, *, key_id: str | None = None) -> LinkToken:
        """The 256-bit token of an emailed link — a password reset, an invitation — derived, so
        that no table has to hold it (05 KEY-03, NTR-04; rulings R-48 (g), R-53 (h)): HMAC-SHA256
        under the platform security key over a label of its own, the link's ``purpose`` and the
        16 bytes of its ``reference``, as 43 URL-safe characters. The command that issues the
        link stores the token's SHA-256 and hands the email its purpose, reference and key id;
        the dispatcher derives the same token again. ``key_id`` names the key of a link issued
        earlier; without it the current key is used, and its id answered."""
        used = self.current_security_key_id() if key_id is None else key_id
        message = b"\x00".join((LINK_TOKEN_LABEL, purpose.encode("ascii"), reference.bytes))
        digest = hmac.new(self.security_event_key(used), message, hashlib.sha256).digest()
        return LinkToken(base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"), used)

    def new_tenant_audit_key_id(self, tenant_id: UUID) -> str:
        """``audit-hmac:<tenant id>:1``; provisioning stores only this id (DG-KRN-KEY-06)."""
        return str(KeyId("audit-hmac", 1, tenant_id))

    def encrypt(self, plaintext: bytes, *, context: Mapping[str, str]) -> bytes:
        dek = os.urandom(KEY_BYTES)
        wrapped = self._provider.wrap(dek, context)
        return BLOB_MAGIC + wrapped + seal(dek, plaintext, canonical_bytes(dict(context)))

    def new_file_key(self, *, context: Mapping[str, str]) -> tuple[bytes, bytes]:
        """A random 256-bit file data key and its sidecar blob (05 PRV-06, KEY-07).

        The sidecar is ``b"erev1"`` ‖ KEK id length ‖ KEK id ‖ wrapped DEK length ‖ wrapped DEK: the
        envelope head without data. It lives in the file store, never in the database, so
        destroying it shreds the file.
        """
        dek = os.urandom(KEY_BYTES)
        return dek, BLOB_MAGIC + self._provider.wrap(dek, context)

    def file_key(self, sidecar: bytes, *, context: Mapping[str, str]) -> bytes:
        """The data key of a sidecar written by ``new_file_key`` under the same context."""
        if not sidecar.startswith(BLOB_MAGIC):
            raise ValueError("not an erev1 sidecar")
        return self._unwrap(sidecar[len(BLOB_MAGIC) :], context, canonical_bytes(dict(context)))

    def wrap_file_key(self, dek: bytes, *, context: Mapping[str, str]) -> bytes:
        """The sidecar of an existing data key under the current KEK: KEY-04 rotation re-wraps the
        same DEK and never re-encrypts the immutable payload (SAR-07)."""
        if len(dek) != KEY_BYTES:
            raise ValueError("a DEK holds 32 bytes")
        return BLOB_MAGIC + self._provider.wrap(dek, context)

    @staticmethod
    def seal_file(dek: bytes, plaintext: bytes, *, context: Mapping[str, str]) -> bytes:
        """nonce ‖ ciphertext ‖ tag of a file under its data key (SAR-07)."""
        return seal(dek, plaintext, canonical_bytes(dict(context)))

    @staticmethod
    def open_file(dek: bytes, sealed: bytes, *, context: Mapping[str, str]) -> bytes:
        """Inverse of ``seal_file``; raises ``InvalidTag`` under another key or context."""
        return open_sealed(dek, sealed, canonical_bytes(dict(context)))

    def secret(self, ref: str) -> str:
        """An adapter credential by secret store reference (05 KEY-09); never a master key."""
        return self._provider.secret(ref).get_secret_value()

    def adapter_secret(self, ref: str, *, tenant_id: UUID) -> str:
        """The credential a tenant's ``integration_connection.secret_ref`` names (05 ADP-14,
        KEY-09), or ``KeyError`` when this provider will not serve the reference: it lies outside
        the tenant's namespace of the secret store (``in_adapter_namespace``; checked before the
        store is asked, so one tenant's connection never reads another tenant's secret or a
        platform secret, R-48 (f)), the store has
        no such secret or version, the name is refused (key material, database URLs), the hosted
        store does not accept the reference (``SecretRefError``: not pinned as
        ``<name>@<version>``) or denies it to this identity. Both providers refuse alike, so the
        test-connection probe records FAILURE and the webhook receiver answers ADP-01's one 401
        whichever provider runs. The ``KeyError`` never carries a reference the store could not
        parse — it may be a pasted value. An outage is no refusal: a transient or unclassified
        provider failure, and a version the store did not return as asked, are
        ``SecretUnavailable`` with the provider's error as the cause."""
        if not in_adapter_namespace(ref, tenant_id):
            raise KeyError(UNSERVED_REFERENCE)
        try:
            return self.secret(ref)
        except SecretRefError:
            raise KeyError(UNSERVED_REFERENCE) from None
        except GcpError as error:
            if error.kind == "denied":
                raise KeyError(UNSERVED_REFERENCE) from None
            raise SecretUnavailable(STORE_UNAVAILABLE) from error
        except SecretVersionMismatch as error:
            raise SecretUnavailable(STORE_UNAVAILABLE) from error

    def envelope_key_id(self, blob: bytes) -> str:
        """The KEK id an envelope is wrapped under (T-PLT-04 ``secret_key_id``)."""
        if not blob.startswith(BLOB_MAGIC):
            raise ValueError("not an erev1 envelope")
        kek_id, _, _ = unpack_wrapped_dek(blob[len(BLOB_MAGIC) :])
        return kek_id

    def decrypt(self, blob: bytes, *, context: Mapping[str, str]) -> bytes:
        start = len(BLOB_MAGIC)
        if not blob.startswith(BLOB_MAGIC):
            raise ValueError("not an erev1 envelope")
        _, _, read = unpack_wrapped_dek(blob[start:])
        wrapped_end = start + read
        if len(blob) < wrapped_end + NONCE_BYTES + TAG_BYTES:
            raise ValueError("truncated erev1 envelope")
        associated_data = canonical_bytes(dict(context))
        dek = self._unwrap(blob[start:wrapped_end], context, associated_data)
        return open_sealed(dek, blob[wrapped_end:], associated_data)

    def _unwrap(self, wrapped: bytes, context: Mapping[str, str], associated_data: bytes) -> bytes:
        # Keyed by the context too, so a cached DEK never bypasses context binding.
        cache_key = (wrapped, associated_data)
        now = self._monotonic()
        entry = self._deks.get(cache_key)
        if entry is not None and now - entry[0] < DEK_CACHE_SECONDS:
            self._deks.move_to_end(cache_key)
            return entry[1]
        dek = self._provider.unwrap(wrapped, context)
        self._deks[cache_key] = (now, dek)
        self._deks.move_to_end(cache_key)
        while len(self._deks) > DEK_CACHE_ENTRIES:
            self._deks.popitem(last=False)
        return dek


def build_keyring(
    settings: Settings, *, secret_client: Any | None = None, kms_client: Any | None = None
) -> KeyRing:
    """Composition roots only (DG-KRN-CFG-01); the provider follows EREV_KEY_PROVIDER.

    ``Settings`` already refuses a ``gcp`` selection without its project and KMS key
    (DG-KRN-CFG-02); the check here keeps the factory fail-closed on its own. The client
    arguments exist for tests, which never construct a real Google client (DG-ENV-17).
    Constructing the hosted providers performs no network call: a provider outage surfaces on
    the first key use, which the readiness probe and every command treat as a failure.
    """
    version = settings.security_hmac_version()
    if settings.key_provider == "local":
        return KeyRing(LocalKeyProvider(EnvSecretStore(settings), security_hmac_version=version))
    if settings.gcp_project is None or settings.gcp_kms_kek is None:
        raise SettingsError("EREV_KEY_PROVIDER=gcp requires EREV_GCP_PROJECT and EREV_GCP_KMS_KEK")
    store = GcpSecretManagerStore(
        settings.gcp_project, prefix=settings.gcp_secret_prefix, client=secret_client
    )
    return KeyRing(
        GcpKeyProvider(
            store,
            kms_key=settings.gcp_kms_kek,
            kms_client=kms_client,
            security_hmac_version=version,
        )
    )


class TenantKeyProvisioner(Protocol):
    """The provisioning authority of KEY-05: makes a tenant's audit HMAC key exist and readable,
    then returns its key id. Separate from ``KeyRing``, whose identity only reads keys
    (DPL-33 accessor versus the provisioning identity of the hosted runtime contract)."""

    def provision_audit_key(self, tenant_id: UUID) -> str: ...


class DerivedTenantKeyProvisioner:
    """Local provider: the key derives from the master key (DG-KRN-KEY-02), so provisioning only
    proves the derivation and returns ``audit-hmac:<tenant id>:1`` (DG-KRN-KEY-06)."""

    def __init__(self, keyring: KeyRing) -> None:
        self._keyring = keyring

    def provision_audit_key(self, tenant_id: UUID) -> str:
        key_id = self._keyring.new_tenant_audit_key_id(tenant_id)
        if len(self._keyring.tenant_audit_key(key_id)) != KEY_BYTES:
            raise ValueError(f"{key_id} did not derive to 32 bytes")
        return key_id


class HostedTenantKeyProvisioner:
    """Hosted provider: creates the tenant secret and its first version through the provisioning
    identity, then reads the key back through the key ring before returning the id, so a tenant
    row never names a key that cannot be read (hosted runtime contract)."""

    def __init__(self, provisioner: GcpTenantKeyProvisioner, keyring: KeyRing) -> None:
        self._provisioner = provisioner
        self._keyring = keyring

    def provision_audit_key(self, tenant_id: UUID) -> str:
        provisioned = self._provisioner.provision_audit_key(tenant_id)
        key_id = str(KeyId("audit-hmac", provisioned.version, tenant_id))
        read_back = self._keyring.tenant_audit_key(key_id)
        if read_back != provisioned.material:
            raise ProvisioningReadbackError(key_id)
        return key_id


def provisioning_denied(error: BaseException) -> bool:
    """Whether a provisioning authority failed because the provider DENIES this process identity
    — hosted, the api and worker identities hold the accessor set and not the provisioning role
    (hosted runtime contract; 05 KEY-05). That is a standing refusal, unlike an outage or a
    malformed secret, and a job that creates a tenant names it instead of failing unexpectedly
    (``sandboxes.provision_audit_key``). Asked here so that the domain layer does not import the
    adapter's error (DG-LAY-03)."""
    return isinstance(error, TenantKeyProvisioningError) and error.kind == "denied"


class ProvisioningReadbackError(RuntimeError):
    """The key read back through the accessor path differs from the provisioned material."""

    def __init__(self, key_id: str) -> None:
        super().__init__(f"{key_id} read back with different material than was provisioned")


def kms_key_location(kms_key: str) -> str:
    """The location of a Cloud KMS key resource name; ``global`` is refused because tenant secrets
    replicate to one region (05 PRV-10, DPL-36)."""
    match = _KMS_LOCATION.match(kms_key)
    if match is None:
        raise SettingsError("EREV_GCP_KMS_KEK must name a location")
    location = match["location"]
    if location == "global":
        raise SettingsError("EREV_GCP_KMS_KEK names location global; tenant secrets need a region")
    return location


def build_tenant_key_provisioner(
    settings: Settings, keyring: KeyRing, *, secret_client: Any | None = None
) -> TenantKeyProvisioner:
    """Composition roots only (DG-KRN-CFG-01). Hosted, the process identity must hold the
    provisioning role (the ``erev-tenant-provision`` job); an api or worker identity fails closed
    with ``denied`` on the first secret create."""
    if settings.key_provider == "local":
        return DerivedTenantKeyProvisioner(keyring)
    if settings.gcp_project is None or settings.gcp_kms_kek is None:
        raise SettingsError("EREV_KEY_PROVIDER=gcp requires EREV_GCP_PROJECT and EREV_GCP_KMS_KEK")
    provisioner = GcpTenantKeyProvisioner(
        settings.gcp_project,
        prefix=settings.gcp_secret_prefix,
        location=kms_key_location(settings.gcp_kms_kek),
        client=secret_client,
    )
    return HostedTenantKeyProvisioner(provisioner, keyring)
