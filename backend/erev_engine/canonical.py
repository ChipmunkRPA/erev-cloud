"""Canonical serialisation and hashing (docs/dev-guide.md §5.17, DG-KRN-CAN-01 to DG-KRN-CAN-15).

Every content hash in eRev (approval subjects, idempotency requests, engine bundles, calculation
traces, report outputs, ledger seals, audit HMAC input) is computed over these bytes, so the API,
the engine and verification jobs always agree. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.money import format_exact

__all__ = ["canonical_bytes", "sha256_hex"]


def canonical_bytes(obj: Any) -> bytes:
    """UTF-8 bytes of the canonical JSON encoding of ``obj``."""
    parts: list[str] = []
    _encode(obj, parts)
    return "".join(parts).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    """Lowercase hex SHA-256 of ``canonical_bytes(obj)``."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _string(value: str, parts: list[str]) -> None:
    parts.append(json.dumps(value, ensure_ascii=False))


def _encode(obj: Any, parts: list[str]) -> None:
    # Order matters: bool before int (CAN-03); Enum before str and int (CAN-10);
    # datetime before date (CAN-08).
    if obj is None:
        parts.append("null")
    elif isinstance(obj, bool):
        parts.append("true" if obj else "false")
    elif isinstance(obj, Enum):
        _encode(obj.value, parts)
    elif isinstance(obj, int):
        parts.append(str(int(obj)))
    elif isinstance(obj, str):
        _string(obj, parts)
    elif isinstance(obj, float):
        raise TypeError("canonical encoding rejects float; use Decimal or Fraction")
    elif isinstance(obj, Decimal):
        if not obj.is_finite():
            raise ValueError("canonical encoding rejects NaN and infinite Decimal values")
        _string(format(obj, "f"), parts)
    elif isinstance(obj, Fraction):
        _string(format_exact(obj), parts)
    elif isinstance(obj, datetime):
        _string(_datetime(obj), parts)
    elif isinstance(obj, date):
        _string(f"{obj.year:04d}-{obj.month:02d}-{obj.day:02d}", parts)
    elif isinstance(obj, UUID):
        _string(str(obj), parts)
    elif isinstance(obj, Mapping):
        _mapping(obj.items(), parts)
    elif isinstance(obj, list | tuple):
        _array(obj, parts)
    elif isinstance(obj, set | frozenset):
        _array(sorted(obj, key=canonical_bytes), parts)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        _mapping(((f.name, getattr(obj, f.name)) for f in dataclasses.fields(obj)), parts)
    else:
        raise TypeError(f"canonical encoding does not support {type(obj).__qualname__}")


def _datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical encoding requires a timezone-aware datetime")
    u = value.astimezone(UTC)
    return (
        f"{u.year:04d}-{u.month:02d}-{u.day:02d}T"
        f"{u.hour:02d}:{u.minute:02d}:{u.second:02d}.{u.microsecond:06d}Z"
    )


def _mapping(items: Any, parts: list[str]) -> None:
    pairs: list[tuple[str, Any]] = []
    for key, value in items:
        if not isinstance(key, str):
            raise TypeError(f"canonical mapping keys must be str, not {type(key).__qualname__}")
        pairs.append((key, value))
    pairs.sort(key=lambda pair: pair[0])
    parts.append("{")
    for index, (key, value) in enumerate(pairs):
        if index:
            parts.append(",")
        _string(key, parts)
        parts.append(":")
        _encode(value, parts)
    parts.append("}")


def _array(values: Any, parts: list[str]) -> None:
    parts.append("[")
    for index, value in enumerate(values):
        if index:
            parts.append(",")
        _encode(value, parts)
    parts.append("]")
