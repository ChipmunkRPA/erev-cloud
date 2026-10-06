"""In-process stand-ins for the Google clients the hosted adapters call (DG-ENV-17, DG-KRN-FILE-05).

No ``google.cloud`` import and no network: the exception classes carry the names and HTTP codes
the adapters classify on (``erev_api.adapters.gcp.error_kind``). Every fake records its calls,
enforces a per-client permission set (an IAM stand-in) and injects faults on demand, including
the "ambiguous success" where the operation is applied and the response is lost.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Final

from erev_api.adapters.keys.provider import open_sealed, seal


class FakeApiError(Exception):
    code: int = 0

    def __init__(self, message: str = "") -> None:
        super().__init__(message or type(self).__name__)


class NotFound(FakeApiError):
    code = 404


class PreconditionFailed(FakeApiError):
    code = 412


class Forbidden(FakeApiError):
    code = 403


class PermissionDenied(Forbidden):
    code = 403


class AlreadyExists(FakeApiError):
    code = 409


class ServiceUnavailable(FakeApiError):
    code = 503


@dataclass(slots=True)
class Fault:
    operation: str
    error: Exception
    ambiguous: bool = False  # apply the operation, then raise (lost response)


class FaultInjector:
    def __init__(self) -> None:
        self._faults: list[Fault] = []

    def fail_next(self, operation: str, error: Exception, *, ambiguous: bool = False) -> None:
        self._faults.append(Fault(operation, error, ambiguous))

    def run(self, operation: str, do: Callable[[], Any]) -> Any:
        for index, fault in enumerate(self._faults):
            if fault.operation == operation:
                del self._faults[index]
                if not fault.ambiguous:
                    raise fault.error
                do()  # applied, then the response is lost
                raise fault.error
        return do()

    @property
    def pending(self) -> int:
        return len(self._faults)


class FakeKms:
    """Cloud KMS stand-in: AES-256-GCM under a fixed key, so the AAD binding really holds."""

    PREFIX: Final = b"fake-kms:"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.faults = FaultInjector()
        self._key = bytes(range(32))

    def encrypt(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self.calls.append(("encrypt", dict(request)))

        def do() -> SimpleNamespace:
            sealed = seal(self._key, request["plaintext"], request["additional_authenticated_data"])
            return SimpleNamespace(ciphertext=self.PREFIX + sealed)

        return self.faults.run("encrypt", do)

    def decrypt(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self.calls.append(("decrypt", dict(request)))

        def do() -> SimpleNamespace:
            ciphertext = request["ciphertext"]
            assert ciphertext.startswith(self.PREFIX)
            plaintext = open_sealed(
                self._key,
                ciphertext[len(self.PREFIX) :],
                request["additional_authenticated_data"],
            )
            return SimpleNamespace(plaintext=plaintext)

        return self.faults.run("decrypt", do)


# Secret Manager permission names, as the two Terraform custom roles (lane P3b) and the accessor
# role grant them: `erevTenantSecretCreator` may only create; `erevTenantSecretInitializer` may
# get, list, add and access versions, only under the tenant audit-key prefix (scope infix).
CREATOR_PERMISSIONS: Final = frozenset({"secrets.create"})
INITIALIZER_PERMISSIONS: Final = frozenset(
    {"secrets.get", "versions.add", "versions.access", "versions.get", "versions.list"}
)
PROVISIONER_PERMISSIONS: Final = CREATOR_PERMISSIONS | INITIALIZER_PERMISSIONS
ACCESSOR_PERMISSIONS: Final = frozenset({"versions.access"})
TENANT_SECRET_INFIX: Final = "audit-hmac-"
_VERSION_OF: Final = re.compile(r"^(?P<secret>.+)/versions/(?P<version>[^/]+)$")


@dataclass(slots=True)
class _SecretVersion:
    number: int
    data: bytes
    state: str = "ENABLED"


@dataclass(slots=True)
class _Secret:
    replication: dict[str, Any]
    versions: list[_SecretVersion] = field(default_factory=list)


class FakeSecretManager:
    """Secret Manager state shared by every client built from it."""

    def __init__(self) -> None:
        self.secrets: dict[str, _Secret] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.faults = FaultInjector()
        self._lock = threading.RLock()
        # A hook run before a version is added, so a test can interleave a competing writer.
        self.before_add_version: Callable[[str], None] | None = None
        # Version numbers Secret Manager should claim to have returned, per secret path.
        self.returned_version_override: dict[str, int] = {}

    def client(
        self,
        permissions: frozenset[str] = PROVISIONER_PERMISSIONS,
        *,
        scope_infix: str | None = None,
    ) -> FakeSecretManagerClient:
        """A client with an IAM permission set; ``scope_infix`` narrows the initializer
        permissions (all but ``versions.access``, which the accessor grants cover) to secret paths
        containing it, like the resource-name condition of the Terraform role."""
        return FakeSecretManagerClient(self, permissions, scope_infix=scope_infix)

    def seed(self, path: str, versions: list[tuple[bytes, str]], *, location: str = "r") -> None:
        secret = _Secret({"user_managed": {"replicas": [{"location": location}]}})
        secret.versions = [
            _SecretVersion(index + 1, data, state) for index, (data, state) in enumerate(versions)
        ]
        self.secrets[path] = secret

    def version_payloads(self, path: str) -> list[bytes]:
        return [version.data for version in self.secrets[path].versions]


class FakeSecretManagerClient:
    def __init__(
        self,
        backend: FakeSecretManager,
        permissions: frozenset[str],
        *,
        scope_infix: str | None = None,
    ) -> None:
        self._backend = backend
        self._permissions = permissions
        self._scope_infix = scope_infix

    def _require(self, permission: str, path: str | None = None) -> None:
        if permission not in self._permissions:
            raise PermissionDenied(f"permission {permission} denied")
        scoped = INITIALIZER_PERMISSIONS - {"versions.access"}
        if (
            self._scope_infix is not None
            and permission in scoped
            and path is not None
            and self._scope_infix not in path
        ):
            raise PermissionDenied(f"permission {permission} denied outside the tenant prefix")

    def _record(self, operation: str, request: Mapping[str, Any]) -> None:
        self._backend.calls.append((operation, dict(request)))

    def create_secret(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self._record("create_secret", request)
        self._require("secrets.create")
        path = f"{request['parent']}/secrets/{request['secret_id']}"

        def do() -> SimpleNamespace:
            with self._backend._lock:
                if path in self._backend.secrets:
                    raise AlreadyExists(path)
                self._backend.secrets[path] = _Secret(dict(request["secret"]["replication"]))
            return SimpleNamespace(name=path)

        return self._backend.faults.run("create_secret", do)

    def get_secret(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self._record("get_secret", request)
        self._require("secrets.get", request["name"])

        def do() -> SimpleNamespace:
            if request["name"] not in self._backend.secrets:
                raise NotFound(request["name"])
            return SimpleNamespace(name=request["name"])

        return self._backend.faults.run("get_secret", do)

    def list_secret_versions(self, *, request: Mapping[str, Any]) -> list[SimpleNamespace]:
        self._record("list_secret_versions", request)
        self._require("versions.list", request["parent"])

        def do() -> list[SimpleNamespace]:
            secret = self._backend.secrets.get(request["parent"])
            if secret is None:
                raise NotFound(request["parent"])
            return [
                SimpleNamespace(
                    name=f"{request['parent']}/versions/{version.number}",
                    state=SimpleNamespace(name=version.state),
                )
                for version in secret.versions
            ]

        return self._backend.faults.run("list_secret_versions", do)

    def add_secret_version(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self._record("add_secret_version", request)
        self._require("versions.add", request["parent"])
        path = request["parent"]

        def do() -> SimpleNamespace:
            if self._backend.before_add_version is not None:
                hook, self._backend.before_add_version = self._backend.before_add_version, None
                hook(path)
            with self._backend._lock:
                secret = self._backend.secrets.get(path)
                if secret is None:
                    raise NotFound(path)
                number = len(secret.versions) + 1
                secret.versions.append(_SecretVersion(number, bytes(request["payload"]["data"])))
            return SimpleNamespace(name=f"{path}/versions/{number}")

        return self._backend.faults.run("add_secret_version", do)

    def access_secret_version(self, *, request: Mapping[str, Any]) -> SimpleNamespace:
        self._record("access_secret_version", request)
        self._require("versions.access")

        def do() -> SimpleNamespace:
            match = _VERSION_OF.fullmatch(request["name"])
            assert match is not None, request["name"]
            secret = self._backend.secrets.get(match["secret"])
            if secret is None:
                raise NotFound(request["name"])
            if match["version"] == "latest":
                raise AssertionError("latest is never read (05 SAR-25)")
            for version in secret.versions:
                if version.number == int(match["version"]):
                    if version.state != "ENABLED":
                        raise FakeApiError(f"version is {version.state}")
                    reported = self._backend.returned_version_override.get(
                        match["secret"], version.number
                    )
                    return SimpleNamespace(
                        name=f"{match['secret']}/versions/{reported}",
                        payload=SimpleNamespace(data=version.data),
                    )
            raise NotFound(request["name"])

        return self._backend.faults.run("access_secret_version", do)


def random_hex_key() -> str:
    return os.urandom(32).hex()
