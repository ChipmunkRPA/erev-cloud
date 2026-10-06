"""Retained audit digests (05 SAR-31; hosted runtime contract §"Shredding and retained digests").

A PASS of the daily chain verification stores its digest as a ``file_object`` of purpose
``AUDIT_DIGEST`` (``audit.verify``). Hosted, the worker also copies the digest bytes to the
write-once digest bucket (7-year retention, DPL-35) through a ``DigestExporter``. The object name
is deterministic and content-derived, so a retried export after a lost response names the same
object and a create-only write (``if_generation_match=0``) either creates it or meets a 412.

The writer identity holds ``roles/storage.objectCreator`` only (DPL-33): it cannot read the object
it collided with, so a 412 yields ``pending_verification`` rather than a silent success. A separate
verifier identity (``roles/storage.objectViewer``) reconciles name, generation and SHA-256 through
``DigestVerifier``; nothing here ever overwrites or deletes a digest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol
from uuid import UUID

DIGEST_OBJECT_SUFFIX: Final = ".json"
ExportStatus = Literal["created", "pending_verification"]
VerificationStatus = Literal["verified", "missing", "mismatch"]


def digest_sha256(digest: bytes) -> str:
    return hashlib.sha256(digest).hexdigest()


def digest_object_name(tenant_id: UUID, verified_at: datetime, digest: bytes) -> str:
    """``<tenant id>/<YYYY>/<MM>/<DD>/<sha256 of the digest bytes>.json``: the date groups the daily
    exports for RB-13 review; the hash is the immutable content identity."""
    return f"{tenant_id}/{verified_at:%Y/%m/%d}/{digest_sha256(digest)}{DIGEST_OBJECT_SUFFIX}"


@dataclass(frozen=True, slots=True)
class DigestExport:
    bucket: str
    name: str
    sha256: str
    status: ExportStatus
    generation: int | None  # the created generation; None while verification is pending


@dataclass(frozen=True, slots=True)
class DigestVerification:
    bucket: str
    name: str
    status: VerificationStatus
    generation: int | None
    size: int | None
    sha256: str | None  # of the bytes read at that exact generation


class DigestExporter(Protocol):
    def export(self, *, tenant_id: UUID, digest: bytes, verified_at: datetime) -> DigestExport: ...


class DigestVerifier(Protocol):
    def verify(self, *, name: str, expected_sha256: str) -> DigestVerification: ...
