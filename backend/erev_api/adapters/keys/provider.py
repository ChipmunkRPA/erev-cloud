"""Key providers KRN-KEY (dev-guide §5.19 DG-KRN-KEY-02 to DG-KRN-KEY-05; 05 SAR-21 to SAR-23).

Key ids follow 05 KEY-03 to KEY-05: ``audit-hmac:<tenant id>:<n>``, ``security-hmac:<n>`` and
``kek:<n>``. ``LocalKeyProvider`` derives every key with HKDF-SHA256 over one of the three master
keys, so there is no keyring file and rotation only increments ``<n>``. ``GcpKeyProvider`` wraps
DEKs through Cloud KMS and never holds the KEK (D-78). HMAC keys are cached for the process
lifetime (SAR-22). Key material is never logged; only key ids are.

Both providers write one wrapped-DEK layout: KEK id length (1 byte) ‖ KEK id ‖ wrapped DEK length
(2 bytes, big-endian) ‖ wrapped DEK (DG-KRN-KEY-04 as amended by D-78).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from erev_engine.canonical import canonical_bytes
from pydantic import SecretStr

from erev_api.adapters import gcp
from erev_api.adapters.secrets.store import MASTER_KEY_NAMES, GcpSecretManagerStore, SecretStore
from erev_api.logging import get_logger

Purpose = Literal["audit-hmac", "security-hmac", "kek"]
HmacPurpose = Literal["audit-hmac", "security-hmac"]

KEY_BYTES: Final = 32
NONCE_BYTES: Final = 12
TAG_BYTES: Final = 16
# Local wrap: AES-256-GCM of a 32-byte DEK, nonce ‖ encrypted DEK ‖ tag (DG-KRN-KEY-04).
LOCAL_WRAPPED_DEK_BYTES: Final = NONCE_BYTES + KEY_BYTES + TAG_BYTES
# Width of the big-endian wrapped-DEK length field (D-78 amending DG-KRN-KEY-04).
WRAPPED_LENGTH_BYTES: Final = 2
CURRENT_KEK_ID: Final = "kek:1"
CURRENT_HMAC_VERSION: Final = 1
# Secret Manager names holding key material or database credentials; secret() never reads them.
GCP_REFUSED_SECRETS: Final = frozenset(
    {"app-kek", "security-hmac", "audit-hmac", "db-owner-url", "db-app-url"}
)
GCP_REFUSED_SECRET_PREFIX: Final = "audit-hmac-"

MASTER_KEY_OF: Final[Mapping[Purpose, str]] = {
    "audit-hmac": "EREV_AUDIT_HMAC_MASTER_KEY",
    "security-hmac": "EREV_SECURITY_EVENT_HMAC_KEY",
    "kek": "EREV_ENCRYPTION_KEY",
}

_VERSION = "[1-9][0-9]*"
_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_KEY_ID_PATTERNS: Final[tuple[tuple[Purpose, re.Pattern[str]], ...]] = (
    ("audit-hmac", re.compile(f"audit-hmac:(?P<tenant>{_UUID}):(?P<version>{_VERSION})")),
    ("security-hmac", re.compile(f"security-hmac:(?P<version>{_VERSION})")),
    ("kek", re.compile(f"kek:(?P<version>{_VERSION})")),
)


@dataclass(frozen=True, slots=True)
class KeyId:
    purpose: Purpose
    version: int
    tenant_id: UUID | None = None

    def __str__(self) -> str:
        if self.purpose == "audit-hmac":
            return f"audit-hmac:{self.tenant_id}:{self.version}"
        return f"{self.purpose}:{self.version}"


def parse_key_id(key_id: str) -> KeyId:
    """Parse a canonical key id; any other form raises ``ValueError`` (DG-KRN-KEY-02)."""
    for purpose, pattern in _KEY_ID_PATTERNS:
        match = pattern.fullmatch(key_id)
        if match is not None:
            tenant = match.groupdict().get("tenant")
            return KeyId(purpose, int(match["version"]), UUID(tenant) if tenant else None)
    raise ValueError(f"malformed key id {key_id!r} (DG-KRN-KEY-02)")


def hkdf_sha256(ikm: bytes, info: bytes, length: int = KEY_BYTES) -> bytes:
    """RFC 5869 HKDF-SHA256 with a zero-length salt (``salt=None``), as DG-KRN-KEY-02 fixes."""
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)


def seal(key: bytes, plaintext: bytes, associated_data: bytes) -> bytes:
    """AES-256-GCM under a random 96-bit nonce; returns nonce ‖ ciphertext with tag."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, associated_data)


def open_sealed(key: bytes, sealed: bytes, associated_data: bytes) -> bytes:
    """Inverse of ``seal``; raises ``cryptography.exceptions.InvalidTag`` on any mismatch."""
    return AESGCM(key).decrypt(sealed[:NONCE_BYTES], sealed[NONCE_BYTES:], associated_data)


def pack_wrapped_dek(kek_id: str, wrapped: bytes) -> bytes:
    """``KEK id length ‖ KEK id ‖ wrapped DEK length (2 bytes, big-endian) ‖ wrapped DEK``."""
    encoded = kek_id.encode("ascii")
    if not 0 < len(wrapped) < 1 << (8 * WRAPPED_LENGTH_BYTES) or len(encoded) > 0xFF:
        raise ValueError("a wrapped DEK holds 1 to 65535 bytes under a KEK id of at most 255")
    length = len(wrapped).to_bytes(WRAPPED_LENGTH_BYTES, "big")
    return bytes([len(encoded)]) + encoded + length + wrapped


def unpack_wrapped_dek(data: bytes) -> tuple[str, bytes, int]:
    """(KEK id, wrapped DEK, bytes read) from the head of ``data``; malformed input: ValueError."""
    if not data:
        raise ValueError("empty wrapped DEK")
    id_end = 1 + data[0]
    length_end = id_end + WRAPPED_LENGTH_BYTES
    if len(data) < length_end:
        raise ValueError("truncated wrapped DEK")
    kek_id = data[1:id_end].decode("ascii", errors="replace")
    if parse_key_id(kek_id).purpose != "kek":
        raise ValueError("malformed wrapped DEK")
    end = length_end + int.from_bytes(data[id_end:length_end], "big")
    if end == length_end or len(data) < end:
        raise ValueError("truncated wrapped DEK")
    return kek_id, data[length_end:end], end


class KeyProvider(Protocol):
    def hmac_key(self, key_id: str) -> bytes: ...
    def current_hmac_key_id(self, purpose: HmacPurpose, tenant_id: UUID | None) -> str: ...
    def wrap(self, dek: bytes, context: Mapping[str, str]) -> bytes: ...
    def unwrap(self, blob: bytes, context: Mapping[str, str]) -> bytes: ...
    def secret(self, ref: str) -> SecretStr: ...


class _CachingKeyProvider:
    """HMAC key cache, current key ids and the wrapped-DEK layout shared by both providers.

    ``security_hmac_version`` is the version of ``security-hmac:<n>`` new security events are
    signed with (05 KEY-03; hosted: the pinned Secret Manager version); historical events keep
    verifying under their own version, which the providers load by id.
    """

    def __init__(self, *, security_hmac_version: int = CURRENT_HMAC_VERSION) -> None:
        if security_hmac_version < 1:
            raise ValueError("security-hmac versions are numbered from 1")
        self._keys: dict[str, bytes] = {}
        self._security_hmac_version = security_hmac_version

    def _load(self, key_id: KeyId) -> bytes:
        raise NotImplementedError

    def _wrap_dek(self, kek_id: str, dek: bytes, associated_data: bytes) -> bytes:
        raise NotImplementedError

    def _unwrap_dek(self, kek_id: str, wrapped: bytes, associated_data: bytes) -> bytes:
        raise NotImplementedError

    def hmac_key(self, key_id: str) -> bytes:
        key = self._keys.get(key_id)
        if key is None:
            key = self._load(parse_key_id(key_id))
            self._keys[key_id] = key
            get_logger(__name__).info("keys.key_loaded", key_id=key_id)
        return key

    def current_hmac_key_id(self, purpose: HmacPurpose, tenant_id: UUID | None) -> str:
        if purpose == "audit-hmac":
            if tenant_id is None:
                raise ValueError("audit-hmac key ids need a tenant id")
            return str(KeyId("audit-hmac", CURRENT_HMAC_VERSION, tenant_id))
        if tenant_id is not None:
            raise ValueError("security-hmac key ids take no tenant id")
        return str(KeyId("security-hmac", self._security_hmac_version))

    def wrap(self, dek: bytes, context: Mapping[str, str]) -> bytes:
        """The wrapped-DEK layout under the current KEK, so ``unwrap`` selects the KEK by id."""
        if len(dek) != KEY_BYTES:
            raise ValueError("a DEK holds 32 bytes")
        wrapped = self._wrap_dek(CURRENT_KEK_ID, dek, canonical_bytes(dict(context)))
        return pack_wrapped_dek(CURRENT_KEK_ID, wrapped)

    def unwrap(self, blob: bytes, context: Mapping[str, str]) -> bytes:
        kek_id, wrapped, read = unpack_wrapped_dek(blob)
        if read != len(blob):
            raise ValueError("malformed wrapped DEK")
        dek = self._unwrap_dek(kek_id, wrapped, canonical_bytes(dict(context)))
        if len(dek) != KEY_BYTES:
            raise ValueError("an unwrapped DEK must hold 32 bytes")
        return dek


class LocalKeyProvider(_CachingKeyProvider):
    """Adapter over ``SecretStore``: HKDF-SHA256 over the master keys; no keyring file."""

    def __init__(
        self, store: SecretStore, *, security_hmac_version: int = CURRENT_HMAC_VERSION
    ) -> None:
        super().__init__(security_hmac_version=security_hmac_version)
        self._store = store

    def _load(self, key_id: KeyId) -> bytes:
        master = bytes.fromhex(self._store.get(MASTER_KEY_OF[key_id.purpose]).get_secret_value())
        return hkdf_sha256(master, b"erev:" + str(key_id).encode("ascii"))

    def _wrap_dek(self, kek_id: str, dek: bytes, associated_data: bytes) -> bytes:
        return seal(self.hmac_key(kek_id), dek, associated_data)

    def _unwrap_dek(self, kek_id: str, wrapped: bytes, associated_data: bytes) -> bytes:
        if len(wrapped) != LOCAL_WRAPPED_DEK_BYTES:
            raise ValueError(f"a locally wrapped DEK holds {LOCAL_WRAPPED_DEK_BYTES} bytes")
        return open_sealed(self.hmac_key(kek_id), wrapped, associated_data)

    def secret(self, ref: str) -> SecretStr:
        """Adapter credentials (05 KEY-09); the master keys are never served (D-78)."""
        if ref in MASTER_KEY_NAMES:
            raise KeyError(ref)
        return self._store.get(ref)

    def __repr__(self) -> str:
        return "LocalKeyProvider()"


class GcpKeyProvider(_CachingKeyProvider):
    """Hosted adapter over Cloud KMS and Secret Manager (05 KEY-03 to KEY-05, SAR-21).

    DEKs are wrapped and unwrapped by the Cloud KMS ``encrypt`` and ``decrypt`` calls, with the
    canonical bytes of the context as additional authenticated data. KEK id ``kek:1`` names the
    KMS key ``kms_key`` and KMS selects the key version, so the KEK never enters process memory
    (05 KEY-04; D-78). HMAC keys are numbered versions of the secrets ``security-hmac`` and
    ``audit-hmac-<tenant id>``, each 64 hexadecimal characters. Tests exercise this class with
    fake clients and no network (D-78 amending DG-ENV-17).
    """

    def __init__(
        self,
        store: GcpSecretManagerStore,
        kms_key: str,
        kms_client: Any | None = None,
        *,
        security_hmac_version: int = CURRENT_HMAC_VERSION,
    ) -> None:
        super().__init__(security_hmac_version=security_hmac_version)
        self._store = store
        self._kms_key = kms_key
        self._kms = gcp.make_client("kms") if kms_client is None else kms_client

    def _load(self, key_id: KeyId) -> bytes:
        if key_id.purpose == "kek":
            raise ValueError(f"{key_id} names the Cloud KMS key; its material never leaves KMS")
        name = (
            "security-hmac"
            if key_id.purpose == "security-hmac"
            else f"audit-hmac-{key_id.tenant_id}"
        )
        key = bytes.fromhex(self._store.get_version(name, key_id.version).get_secret_value())
        if len(key) != KEY_BYTES:
            raise ValueError(f"{key_id} must hold 32 bytes of key material")
        return key

    def _wrap_dek(self, kek_id: str, dek: bytes, associated_data: bytes) -> bytes:
        request = {
            "name": self._kms_key,
            "plaintext": dek,
            "additional_authenticated_data": associated_data,
        }
        return bytes(self._kms.encrypt(request=request).ciphertext)

    def _unwrap_dek(self, kek_id: str, wrapped: bytes, associated_data: bytes) -> bytes:
        if kek_id != CURRENT_KEK_ID:
            raise ValueError(f"{kek_id} does not name the Cloud KMS key")
        request = {
            "name": self._kms_key,
            "ciphertext": wrapped,
            "additional_authenticated_data": associated_data,
        }
        return bytes(self._kms.decrypt(request=request).plaintext)

    def secret(self, ref: str) -> SecretStr:
        """Adapter credentials (05 KEY-09) by pinned reference ``<name>@<version>``; key material
        and database URLs are refused unread, whatever version the reference names."""
        normalised = ref.strip().lower().split("@", 1)[0]
        if normalised in GCP_REFUSED_SECRETS or normalised.startswith(GCP_REFUSED_SECRET_PREFIX):
            raise KeyError(ref)
        return self._store.get(ref)

    def __repr__(self) -> str:
        return "GcpKeyProvider()"
