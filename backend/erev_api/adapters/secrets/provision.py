"""Hosted tenant audit-key provisioning (05 KEY-05, DPL-36; hosted runtime contract §"Persistent
key and secret providers").

``secretAccessor`` only reads payloads, so the api and worker identities cannot create the
per-tenant secret ``<prefix>audit-hmac-<tenant id>`` or add its first version. This adapter runs
under the separate provisioning identity (custom role: secrets.create, secrets.get, versions.add,
versions.access, versions.get, versions.list; no delete, destroy or IAM permission) and is
idempotent: every step tolerates having been done before, and every outcome is verified by
reading the version back.

The workflow, per tenant:

1. create the secret with user-managed replication in one region (PRV-10); ``already_exists``
   means a previous attempt got this far;
2. list its versions; when version 1 exists and is ENABLED, read it back and verify the format;
3. when no version exists at all, add one holding 32 random bytes as 64 lowercase hex
   characters (the KEY-05 material), which becomes version 1 unless a concurrent provisioner won;
4. read version 1 back and verify it (``bytes.fromhex`` of 64 characters). Any other state
   (version 1 DISABLED or DESTROYED, or material of the wrong shape) fails closed without adding,
   disabling, destroying or overwriting anything, so historic material is always preserved.

Denied permission, provider outage and malformed state raise ``TenantKeyProvisioningError``
whose message names the secret and the failure kind, never a payload. Nothing is logged here
beyond the secret name and the version number.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from erev_api.adapters import gcp
from erev_api.adapters.gcp import GcpError, error_kind
from erev_api.logging import get_logger

KEY_BYTES: Final = 32
HEX_KEY: Final = re.compile(r"^[0-9a-f]{64}$")
INITIAL_VERSION: Final = 1
_VERSION_SUFFIX: Final = re.compile(r"/versions/(?P<version>[1-9][0-9]*)$")
_LOGGER: Final = "erev_api.adapters.secrets.provision"


class TenantKeyProvisioningError(RuntimeError):
    """Provisioning cannot complete; ``kind`` classifies why. No payload appears anywhere."""

    def __init__(self, kind: str, secret: str, detail: str) -> None:
        super().__init__(f"tenant key provisioning of {secret} failed: {kind}: {detail}")
        self.kind = kind
        self.secret = secret


@dataclass(frozen=True, slots=True)
class ProvisionedTenantKey:
    secret: str  # the secret id, `<prefix>audit-hmac-<tenant id>`
    version: int  # always INITIAL_VERSION for a fresh or repeated provisioning
    material: bytes  # the 32 key bytes read back from Secret Manager
    created: bool  # False when an earlier attempt had already stored version 1


def _version_number(name: str) -> int:
    match = _VERSION_SUFFIX.search(name)
    if match is None:
        raise ValueError("a secret version name ends in /versions/<n>")
    return int(match["version"])


def _state_name(state: object) -> str:
    """The ENABLED / DISABLED / DESTROYED name of a version state, for enums and strings."""
    name = getattr(state, "name", state)
    return str(name).rsplit(".", 1)[-1].upper()


class GcpTenantKeyProvisioner:
    """Creates and initialises tenant audit HMAC secrets; exercised only with fake clients."""

    def __init__(
        self, project: str, *, prefix: str, location: str, client: Any | None = None
    ) -> None:
        if not location or location == "global":
            raise ValueError("tenant secrets replicate to one named region (PRV-10)")
        self._project = project
        self._prefix = prefix
        self._location = location
        self._client = gcp.make_client("secretmanager") if client is None else client

    def secret_id(self, tenant_id: UUID) -> str:
        return f"{self._prefix}audit-hmac-{tenant_id}"

    def _secret_path(self, secret_id: str) -> str:
        return f"projects/{self._project}/secrets/{secret_id}"

    def _call(self, operation: str, secret_id: str, request: dict[str, Any]) -> Any:
        try:
            return getattr(self._client, operation)(request=request)
        except Exception as exc:
            raise GcpError(error_kind(exc), operation, secret_id, exc) from None

    def provision_audit_key(self, tenant_id: UUID) -> ProvisionedTenantKey:
        secret_id = self.secret_id(tenant_id)
        path = self._secret_path(secret_id)
        log = get_logger(_LOGGER)
        try:
            self._ensure_secret(secret_id, path)
            states = self._version_states(secret_id, path)
            created = False
            if not states:
                added = self._add_initial_version(secret_id, path)
                created = added == INITIAL_VERSION
                if not created:
                    # A concurrent provisioner stored version 1 first; ours is surplus but is never
                    # destroyed here (the role cannot, and nothing may erase material blindly).
                    log.warning(
                        "keys.tenant_secret_surplus_version",
                        secret_id=secret_id,
                        version=added,
                        key_version=INITIAL_VERSION,
                    )
            elif states.get(INITIAL_VERSION) != "ENABLED":
                raise TenantKeyProvisioningError(
                    "malformed", secret_id, "version 1 is not ENABLED; manual review required"
                )
            material = self._read_back(secret_id, path, INITIAL_VERSION)
        except GcpError as error:
            raise TenantKeyProvisioningError(error.kind, secret_id, error.operation) from None
        log.info(
            "keys.tenant_secret_provisioned",
            secret_id=secret_id,
            version=INITIAL_VERSION,
            created=created,
        )
        return ProvisionedTenantKey(secret_id, INITIAL_VERSION, material, created)

    def _ensure_secret(self, secret_id: str, path: str) -> None:
        request = {
            "parent": f"projects/{self._project}",
            "secret_id": secret_id,
            "secret": {
                "replication": {"user_managed": {"replicas": [{"location": self._location}]}}
            },
        }
        try:
            self._call("create_secret", secret_id, request)
        except GcpError as error:
            if error.kind != "already_exists":
                raise
            # Idempotent: an earlier attempt created it. It must still be readable.
            self._call("get_secret", secret_id, {"name": path})

    def _version_states(self, secret_id: str, path: str) -> dict[int, str]:
        """Every version of the secret by number with its ENABLED / DISABLED / DESTROYED state."""
        versions = self._call("list_secret_versions", secret_id, {"parent": path})
        return {
            _version_number(str(version.name)): _state_name(getattr(version, "state", "ENABLED"))
            for version in versions
        }

    def _add_initial_version(self, secret_id: str, path: str) -> int:
        payload = os.urandom(KEY_BYTES).hex().encode("ascii")
        response = self._call(
            "add_secret_version", secret_id, {"parent": path, "payload": {"data": payload}}
        )
        return _version_number(str(response.name))

    def _read_back(self, secret_id: str, path: str, version: int) -> bytes:
        response = self._call(
            "access_secret_version", secret_id, {"name": f"{path}/versions/{version}"}
        )
        text = bytes(response.payload.data).decode("utf-8", errors="replace").strip()
        if not HEX_KEY.fullmatch(text):
            raise TenantKeyProvisioningError(
                "malformed", secret_id, f"version {version} is not 64 lowercase hex characters"
            )
        return bytes.fromhex(text)
