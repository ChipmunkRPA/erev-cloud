"""Redaction and pseudonymisation of audit payloads (dev-guide §5.5 DG-KRN-AUD-05, DG-KRN-AUD-06;
04 T-PLT-19; 05 PRV-04).

``before``, ``after``, ``diff`` and ``detail`` pass through ``json_value`` first, so the buffered
event equals what ``jsonb`` returns and the HMAC computed before the insert verifies afterwards.
Credential keys at any depth become ``"[REDACTED]"`` when the event is recorded. Personal keys
become ``{"hmac", "length"}`` when the event is appended, because the tenant audit key (05 KEY-05)
is known only then.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes

REDACTED: Final = "[REDACTED]"
# dev-guide §5.5: keys replaced by "[REDACTED]" at any depth.
REDACT: Final[frozenset[str]] = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "secret_hash",
        "token",
        "token_sha256",
        "csrf_token_sha256",
        "code_hash",
        "secret_ciphertext",
        "client_secret_ref",
        "api_key",
        "authorization",
    }
)
# [J] REQ-SEC-007 contact data held on master records; the full C3 catalogue arrives with the
# privacy classification (05 PRV-01; SPEC-Q-131).
PERSONAL: Final[frozenset[str]] = frozenset({"email", "phone"})


def json_value(value: Any) -> Any:
    """``value`` as JSON-native data: money and decimals as strings (DG-KRN-AUD-05), timestamps in
    the canonical UTC form (§5.17), sets sorted by canonical bytes; floats are refused."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, float):
        raise TypeError("audit payloads reject float; use Decimal")
    if isinstance(value, Decimal | datetime | date | UUID):
        return canonical_bytes(value).decode("utf-8")[1:-1]
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_value(item) for item in value]
    if isinstance(value, set | frozenset):
        return [json_value(item) for item in sorted(value, key=canonical_bytes)]
    raise TypeError(f"audit payloads do not support {type(value).__qualname__}")


def redact(value: Any) -> Any:
    """Replace the value of every ``REDACT`` key, at any depth, with ``"[REDACTED]"``."""
    if isinstance(value, Mapping):
        return {key: REDACTED if key in REDACT else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def pseudonym(key: bytes, value: Any) -> dict[str, Any]:
    """05 PRV-04: HMAC-SHA256 with the tenant audit key over the value, and its length."""
    text = value if isinstance(value, str) else canonical_bytes(value).decode("utf-8")
    digest = hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"hmac": digest, "length": len(text)}


def pseudonymise(key: bytes, value: Any) -> Any:
    """Replace every non-null ``PERSONAL`` value, at any depth, with its ``pseudonym``."""
    if isinstance(value, Mapping):
        return {
            name: pseudonym(key, item)
            if name in PERSONAL and item is not None
            else pseudonymise(key, item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [pseudonymise(key, item) for item in value]
    return value


def pseudonymise_diff(key: bytes, diff: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Diff entries whose last path segment is a ``PERSONAL`` key carry pseudonyms."""
    if diff is None:
        return None
    entries: list[dict[str, Any]] = []
    for entry in diff:
        if str(entry["path"]).rsplit(".", 1)[-1] in PERSONAL:
            entry = {
                "path": entry["path"],
                "before": None if entry["before"] is None else pseudonym(key, entry["before"]),
                "after": None if entry["after"] is None else pseudonym(key, entry["after"]),
            }
        entries.append(pseudonymise(key, entry))
    return entries
