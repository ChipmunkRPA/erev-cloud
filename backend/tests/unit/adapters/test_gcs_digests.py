"""SAR-31 retained digests: create-only export under the creator identity and independent
verification under the viewer identity (05 DPL-33, DPL-35; hosted runtime contract §"Shredding and
retained digests"; lane P2)."""

from __future__ import annotations

import hashlib
import io
import json
from uuid import UUID

import pytest
from erev_api.adapters.gcp import GcpError
from erev_api.adapters.storage.digests import (
    GcsDigestExporter,
    GcsDigestVerifier,
    build_digest_exporter,
    build_digest_verifier,
)
from erev_api.audit.digests import digest_object_name
from erev_api.config import Settings
from support import log_guard
from support.clock import FROZEN_AT
from support.fake_gcp import ServiceUnavailable
from support.fake_gcs import OBJECT_ADMIN, OBJECT_CREATOR, OBJECT_VIEWER, FakeGcsBackend

BUCKET = "erev-audit-digests-test"
TENANT = UUID("0191e0a0-0000-7000-8000-000000000001")
DIGEST = json.dumps(
    {
        "tenant_id": str(TENANT),
        "last_chain_seq": 4120,
        "last_hmac": "ab" * 32,
        "hmac_key_id": f"audit-hmac:{TENANT}:1",
        "events_checked": 4120,
        "verified_at": FROZEN_AT.isoformat(),
    },
    sort_keys=True,
).encode()
SHA = hashlib.sha256(DIGEST).hexdigest()


def exporter(
    backend: FakeGcsBackend, permissions: frozenset[str] = OBJECT_CREATOR
) -> GcsDigestExporter:
    return GcsDigestExporter(BUCKET, client=backend.client(permissions), sleep=lambda _: None)


def verifier(backend: FakeGcsBackend) -> GcsDigestVerifier:
    return GcsDigestVerifier(BUCKET, client=backend.client(OBJECT_VIEWER), sleep=lambda _: None)


def test_export_is_create_only_and_the_verifier_reconciles() -> None:
    backend = FakeGcsBackend()
    with log_guard.capture() as events:
        export = exporter(backend).export(tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT)
    log_guard.check(events)
    assert export.status == "created" and export.generation is not None
    assert (
        export.name
        == f"{TENANT}/2026/09/12/{SHA}.json"
        == digest_object_name(TENANT, FROZEN_AT, DIGEST)
    )
    assert export.sha256 == SHA and export.bucket == BUCKET

    # A retry of the same digest meets a 412; the creator cannot read past it and reports so.
    again = exporter(backend).export(tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT)
    assert again.status == "pending_verification" and again.generation is None
    assert [operation for operation, _, _ in backend.calls if operation == "get"] == []
    assert len(backend.versions_of(BUCKET, export.name)) == 1

    verification = verifier(backend).verify(name=export.name, expected_sha256=SHA)
    assert verification.status == "verified"
    assert verification.generation == export.generation and verification.size == len(DIGEST)
    assert (
        verifier(backend)
        .verify(name=f"{TENANT}/2026/09/12/missing.json", expected_sha256=SHA)
        .status
        == "missing"
    )

    # Tampering by an identity that can overwrite is detected by the hash reconciliation.
    admin = backend.client(OBJECT_ADMIN).bucket(BUCKET).blob(export.name)
    admin.upload_from_file(io.BytesIO(b"{}"), size=2)
    tampered = verifier(backend).verify(name=export.name, expected_sha256=SHA)
    assert tampered.status == "mismatch" and tampered.generation != export.generation


def test_export_retries_transient_failures_and_reports_a_lost_response() -> None:
    backend = FakeGcsBackend()
    backend.faults.fail_next("upload", ServiceUnavailable())
    export = exporter(backend).export(tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT)
    assert export.status == "created"
    uploads = [kwargs for operation, _, kwargs in backend.calls if operation == "upload"]
    assert [upload["if_generation_match"] for upload in uploads] == [0, 0]

    other = FakeGcsBackend()
    other.faults.fail_next("upload", ServiceUnavailable(), ambiguous=True)
    lost = exporter(other).export(tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT)
    assert lost.status == "pending_verification"
    assert len(other.versions_of(BUCKET, lost.name)) == 1
    assert verifier(other).verify(name=lost.name, expected_sha256=SHA).status == "verified"


def test_export_without_create_permission_fails_closed() -> None:
    backend = FakeGcsBackend()
    with pytest.raises(GcpError) as excinfo:
        exporter(backend, OBJECT_VIEWER).export(
            tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT
        )
    assert excinfo.value.kind == "denied"
    assert backend.object_names(BUCKET) == []
    for _ in range(4):
        backend.faults.fail_next("upload", ServiceUnavailable())
    with pytest.raises(GcpError) as outage:
        exporter(backend).export(tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT)
    assert outage.value.kind == "transient"


def test_factories_follow_the_file_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    base = {
        "EREV_ENV": "production",
        "EREV_PUBLIC_ORIGIN": "https://erev.example.com",
        "EREV_DB_APP_URL": "postgresql://erev_app:app-credential@127.0.0.1:5432/erev",
        "EREV_KEY_PROVIDER": "gcp",
        "EREV_GCP_PROJECT": "p",
        "EREV_GCP_KMS_KEK": "projects/p/locations/l/keyRings/r/cryptoKeys/k",
        "EREV_SECURITY_HMAC_SECRET_VERSION": "1",
    }
    for name, value in base.items():
        monkeypatch.setenv(name, value)
    local = Settings(_env_file=None)
    assert build_digest_exporter(local) is None and build_digest_verifier(local) is None
    monkeypatch.setenv("EREV_FILE_BACKEND", "gcs")
    monkeypatch.setenv("EREV_GCS_FILES_BUCKET", "erev-files-x")
    monkeypatch.setenv("EREV_GCS_AUDIT_DIGEST_BUCKET", BUCKET)
    hosted = Settings(_env_file=None)
    backend = FakeGcsBackend()
    built = build_digest_exporter(hosted, client=backend.client(OBJECT_CREATOR))
    assert isinstance(built, GcsDigestExporter)
    assert built.export(tenant_id=TENANT, digest=DIGEST, verified_at=FROZEN_AT).status == "created"
    assert isinstance(
        build_digest_verifier(hosted, client=backend.client(OBJECT_VIEWER)), GcsDigestVerifier
    )
