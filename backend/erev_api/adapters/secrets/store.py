"""Secret stores KRN-KEY (docs/dev-guide.md §5.19 DG-KRN-KEY-01, DG-KRN-KEY-03; DG-ENV-17).

Locally the three master keys come from ``.env`` through ``EnvSecretStore``. Hosted deployments
read Secret Manager through ``GcpSecretManagerStore``, whose client library comes from the ``gcp``
extra of ``backend/pyproject.toml`` (05 SAR-21) and which tests exercise only with fake clients
(D-78 amending DG-ENV-17). Neither class ever logs, prints or represents a secret value.

Every hosted read is pinned to a numbered version (05 SAR-25, DPL-36; hosted runtime contract):
key material by the version inside the key id, adapter credentials by a reference of the form
``<name>@<version>``. ``latest`` is never read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol

from pydantic import SecretStr

from erev_api.adapters import gcp
from erev_api.adapters.gcp import GcpError, error_kind
from erev_api.config import SettingsError

if TYPE_CHECKING:
    from erev_api.config import Settings

MASTER_KEY_NAMES: Final[tuple[str, ...]] = (
    "EREV_AUDIT_HMAC_MASTER_KEY",
    "EREV_SECURITY_EVENT_HMAC_KEY",
    "EREV_ENCRYPTION_KEY",
)
# A Secret Manager secret id plus the pinned version it is read at (05 KEY-09 hosted form).
SECRET_REF: Final = re.compile(r"^(?P<name>[A-Za-z0-9_-]{1,255})@(?P<version>[1-9][0-9]*)$")


class SecretStore(Protocol):
    def get(self, name: str) -> SecretStr: ...  # KeyError when the secret is absent


class SecretVersionMismatch(RuntimeError):
    """Secret Manager answered with a different version than the one requested; the process must
    not sign or decrypt with material whose version it cannot vouch for (fail closed)."""

    def __init__(self, name: str, requested: int, returned: str) -> None:
        super().__init__(
            f"{name}: requested version {requested}, Secret Manager returned {returned}"
        )
        self.name = name
        self.requested = requested
        self.returned = returned


class SecretRefError(ValueError):
    """A hosted secret reference is not pinned as ``<name>@<version>``; the message never holds
    the reference itself, because a malformed reference could be a pasted value."""


@dataclass(frozen=True, slots=True)
class SecretRef:
    name: str
    version: int

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


def parse_secret_ref(ref: str) -> SecretRef:
    """``<name>@<version>`` with a positive version number; anything else is refused."""
    match = SECRET_REF.fullmatch(ref.strip())
    if match is None:
        raise SecretRefError(
            "a hosted secret reference is <secret name>@<version number>; latest is never read"
        )
    return SecretRef(match["name"], int(match["version"]))


class EnvSecretStore:
    """Local provider: serves exactly the three master keys from Settings (DG-KRN-KEY-01)."""

    def __init__(self, settings: Settings) -> None:
        values = {
            "EREV_AUDIT_HMAC_MASTER_KEY": settings.audit_hmac_master_key,
            "EREV_SECURITY_EVENT_HMAC_KEY": settings.security_event_hmac_key,
            "EREV_ENCRYPTION_KEY": settings.encryption_key,
        }
        missing = sorted(name for name, value in values.items() if value is None)
        if missing:
            raise SettingsError(f"{', '.join(missing)} must be set when EREV_KEY_PROVIDER is local")
        self._values: dict[str, SecretStr] = {
            name: value for name, value in values.items() if value is not None
        }

    def get(self, name: str) -> SecretStr:
        try:
            return self._values[name]
        except KeyError:
            raise KeyError(name) from None

    def __repr__(self) -> str:
        return f"EnvSecretStore(names={list(MASTER_KEY_NAMES)!r})"


class GcpSecretManagerStore:
    """Hosted store over Google Secret Manager; exercised only with fake clients in tests.

    ``get(ref)`` reads the pinned version of a ``<name>@<version>`` reference (05 KEY-09);
    ``get_version(name, n)`` reads version ``n`` of secret ``<prefix><name>``, which is how rotated
    HMAC keys stay derivable (05 KEY-03, KEY-05). Absent secrets raise ``KeyError``; a denied or
    failing call raises ``GcpError`` naming the secret, never its payload. The client library is
    imported only on construction.
    """

    def __init__(self, project: str, prefix: str = "", client: Any | None = None) -> None:
        self._project = project
        self._prefix = prefix
        self._client = gcp.make_client("secretmanager") if client is None else client

    def secret_path(self, name: str) -> str:
        return f"projects/{self._project}/secrets/{self._prefix}{name}"

    def get(self, ref: str) -> SecretStr:
        parsed = parse_secret_ref(ref)
        return self._access(parsed.name, parsed.version)

    def get_version(self, name: str, version: int) -> SecretStr:
        if version < 1:
            raise SecretRefError("secret versions are numbered from 1")
        return self._access(name, version)

    def _access(self, name: str, version: int) -> SecretStr:
        path = f"{self.secret_path(name)}/versions/{version}"
        try:
            response = self._client.access_secret_version(request={"name": path})
        except Exception as exc:
            kind = error_kind(exc)
            if kind == "not_found":
                raise KeyError(name) from None
            raise GcpError(kind, "access_secret_version", path, exc) from None
        returned = str(getattr(response, "name", path)).rsplit("/", 1)[-1]
        if returned != str(version):
            raise SecretVersionMismatch(name, version, returned)
        return SecretStr(bytes(response.payload.data).decode("utf-8"))

    def __repr__(self) -> str:
        return f"GcpSecretManagerStore(project={self._project!r})"
