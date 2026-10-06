"""Write-once audit digest export and its independent verifier (05 SAR-31, DPL-33, DPL-35;
hosted runtime contract §"Shredding and retained digests").

``GcsDigestExporter`` runs in the worker under ``roles/storage.objectCreator``: it can create an
object but never read, overwrite or delete one. It uploads the digest bytes create-only
(``if_generation_match=0``) under the deterministic content-derived name of
``erev_api.audit.digests``. A 412 means an object of that name exists; the creator cannot read it
to compare, so the export is reported ``pending_verification`` and never retried unconditionally.
Transient failures retry with the same precondition; a lost success surfaces as that 412.

``GcsDigestVerifier`` runs under a separate identity holding ``roles/storage.objectViewer`` (the
api service account in the Terraform module): it reads the live object at its exact generation
and reconciles its SHA-256 with the expected digest hash. Neither class holds a delete or
overwrite path, so a generic retry helper can never be made to alter a retained digest.
"""

from __future__ import annotations

import io
import time
from typing import Any, Final

from erev_api.adapters import gcp
from erev_api.adapters.gcp import GcpError, Sleep, call_with_retry
from erev_api.audit.digests import (
    DigestExport,
    DigestExporter,
    DigestVerification,
    DigestVerifier,
    VerificationStatus,
    digest_object_name,
    digest_sha256,
)
from erev_api.config import Settings
from erev_api.logging import get_logger, register_logger_fields

DIGEST_CONTENT_TYPE: Final = "application/json"
_LOGGER: Final = "erev_api.adapters.storage.digests"

register_logger_fields(_LOGGER, ("bucket", "object", "status", "generation", "sha256"))


class GcsDigestExporter:
    """Create-only digest writer; ``client`` is injected by tests (DG-KRN-FILE-05)."""

    def __init__(
        self, bucket: str, *, client: Any | None = None, sleep: Sleep = time.sleep
    ) -> None:
        self._client = gcp.make_client("storage") if client is None else client
        self._bucket_name = bucket
        self._bucket = self._client.bucket(bucket)
        self._sleep = sleep

    def export(self, *, tenant_id: Any, digest: bytes, verified_at: Any) -> DigestExport:
        name = digest_object_name(tenant_id, verified_at, digest)
        sha256 = digest_sha256(digest)
        resource = f"gs://{self._bucket_name}/{name}"
        blob = self._bucket.blob(name)
        log = get_logger(_LOGGER)

        def upload() -> None:
            blob.upload_from_file(
                io.BytesIO(digest),
                size=len(digest),
                content_type=DIGEST_CONTENT_TYPE,
                if_generation_match=0,
                retry=None,
            )

        try:
            call_with_retry("upload", resource, upload, sleep=self._sleep)
        except GcpError as error:
            if error.kind != "precondition_failed":
                raise
            # An object of this content-derived name exists. The creator identity cannot read it,
            # so verification is left to the viewer identity (never an overwrite or a delete).
            log.warning(
                "audit.digest_pending_verification",
                bucket=self._bucket_name,
                object=name,
                status="pending_verification",
                sha256=sha256,
            )
            return DigestExport(self._bucket_name, name, sha256, "pending_verification", None)
        generation = getattr(blob, "generation", None)
        log.info(
            "audit.digest_exported",
            bucket=self._bucket_name,
            object=name,
            status="created",
            generation=None if generation is None else int(generation),
            sha256=sha256,
        )
        return DigestExport(
            self._bucket_name,
            name,
            sha256,
            "created",
            None if generation is None else int(generation),
        )


class GcsDigestVerifier:
    """Read-only reconciliation of a retained digest by name, generation and hash."""

    def __init__(
        self, bucket: str, *, client: Any | None = None, sleep: Sleep = time.sleep
    ) -> None:
        self._client = gcp.make_client("storage") if client is None else client
        self._bucket_name = bucket
        self._bucket = self._client.bucket(bucket)
        self._sleep = sleep

    def verify(self, *, name: str, expected_sha256: str) -> DigestVerification:
        resource = f"gs://{self._bucket_name}/{name}"
        live = call_with_retry(
            "get", resource, lambda: self._bucket.get_blob(name), sleep=self._sleep
        )
        if live is None:
            return DigestVerification(self._bucket_name, name, "missing", None, None, None)
        generation = int(live.generation)
        blob = self._bucket.blob(name, generation=generation)
        data = bytes(
            call_with_retry(
                "download",
                resource,
                lambda: blob.download_as_bytes(if_generation_match=generation, retry=None),
                sleep=self._sleep,
            )
        )
        sha256 = digest_sha256(data)
        status: VerificationStatus = "verified" if sha256 == expected_sha256 else "mismatch"
        get_logger(_LOGGER).info(
            "audit.digest_verified",
            bucket=self._bucket_name,
            object=name,
            status=status,
            generation=generation,
            sha256=sha256,
        )
        return DigestVerification(self._bucket_name, name, status, generation, len(data), sha256)


def build_digest_exporter(
    settings: Settings, *, client: Any | None = None
) -> DigestExporter | None:
    """Composition roots only (DG-KRN-CFG-01). Local backends keep the ``AUDIT_DIGEST`` file as the
    retained copy and export nothing (``None``); the hosted worker exports to the digest bucket."""
    if settings.file_backend != "gcs" or settings.gcs_audit_digest_bucket is None:
        return None
    return GcsDigestExporter(settings.gcs_audit_digest_bucket, client=client)


def build_digest_verifier(
    settings: Settings, *, client: Any | None = None
) -> DigestVerifier | None:
    if settings.file_backend != "gcs" or settings.gcs_audit_digest_bucket is None:
        return None
    return GcsDigestVerifier(settings.gcs_audit_digest_bucket, client=client)
